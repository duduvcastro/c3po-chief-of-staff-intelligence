from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, BinaryIO, Callable, Protocol, Sequence
from uuid import uuid4

from .qualification_scope import (
    QUALIFICATION_SESSION_DATES,
    QUALIFICATION_TICK_DATASETS,
    is_complete_qualification_tick_lot,
)


class B2OffloadError(RuntimeError):
    pass


class B2Store(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None: ...

    def download_fileobj(
        self,
        Bucket: str,
        Key: str,
        Fileobj: BinaryIO,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class OffloadedObject:
    key: str
    content_length: int
    sha256: str
    version_id: str | None
    reused_existing_object: bool
    source_path: str


class DayDB2Offload:
    """Immutable B2 offload and tightly-scoped qualification-lot retention.

    Local deletion is possible only for complete trades/quotes lots belonging
    to the twelve frozen qualification sessions. The delete list is derived
    exclusively from an immutable lot report and remains plan-first.
    """

    report_version = "DAY-D-B2-OFFLOAD-v1"
    restore_version = "DAY-D-B2-RESTORE-v1"
    raw_restore_version = "DAY-D-B2-RAW-RESTORE-v1"
    billing_cap_version = "DAY-D-B2-BILLING-CAP-v1"
    deletion_version = "DAY-D-B2-LOT-DELETION-v1"
    quarantine_version = "DAY-D-B2-LOT-QUARANTINE-v1"
    maximum_temporary_billing_cap_usd = 0.5

    def __init__(
        self,
        store: B2Store,
        *,
        root: Path,
        bucket: str,
        prefix: str = "day-d",
        minimum_free_bytes: int = 20 * 1024**3,
        disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
    ) -> None:
        if not bucket.strip():
            raise B2OffloadError("Backblaze bucket is not configured")
        self.store = store
        self.root = root.resolve()
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")
        self.minimum_free_bytes = max(0, minimum_free_bytes)
        self._disk_usage = disk_usage

    def plan(self, manifest_paths: Sequence[Path]) -> tuple[dict[str, Any], ...]:
        _parents, artifacts = self._load_manifests(manifest_paths)
        output = []
        for artifact in artifacts:
            source = self._source_path(artifact)
            output.append({
                "dataset": str(artifact["dataset"]),
                "session_date": str(artifact["session_date"]),
                "source_path": str(source),
                "content_length": int(artifact["content_length"]),
                "sha256": str(artifact["sha256"]),
                "remote_key": self._raw_key(artifact),
            })
        return tuple(output)

    def offload(
        self,
        manifest_paths: Sequence[Path],
        *,
        lot_id: str,
        measured_at: datetime | None = None,
    ) -> Path:
        safe_lot_id = self._safe_component(lot_id)
        observed_at = measured_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        with self._exclusive_lock():
            parent_manifests, artifacts = self._load_manifests(manifest_paths)
            parent_objects = tuple(
                self._offload_parent_manifest(item) for item in parent_manifests
            )
            objects = tuple(self._offload_artifact(item) for item in artifacts)
            report = {
                "schema_version": self.report_version,
                "lot_id": safe_lot_id,
                "provider": "Backblaze B2",
                "bucket": self.bucket,
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "parent_manifests": [asdict(item) for item in parent_objects],
                "objects": [asdict(item) for item in objects],
                "verified_object_count": len(parent_objects) + len(objects),
                "verified_bytes": sum(
                    item.content_length for item in (*parent_objects, *objects)
                ),
                "raw_verified_bytes": sum(item.content_length for item in objects),
                "local_source_deletion_authorized": False,
                "restore_drill_required_before_local_deletion": True,
            }
            report_path = self._report_path(safe_lot_id, observed_at)
            self._atomic_json(report_path, report)
            report_object = self._upload_verified(
                report_path,
                key=(
                    f"{self.prefix}/offload-lots/lot_id={safe_lot_id}/"
                    f"{report_path.name}"
                ),
                metadata={"artifact-kind": "offload-report"},
            )
            self._atomic_json(
                report_path.with_name(f"{report_path.name}.remote.json"),
                {
                    "schema_version": self.report_version,
                    "lot_id": safe_lot_id,
                    "bucket": self.bucket,
                    "report_object": asdict(report_object),
                },
            )
            return report_path

    def restore_report_sample(
        self,
        report_path: Path,
        *,
        measured_at: datetime | None = None,
    ) -> Path:
        observed_at = measured_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        report_path = report_path.resolve()
        self._assert_below_root(report_path)
        remote_path = report_path.with_name(f"{report_path.name}.remote.json")
        if not remote_path.exists():
            raise B2OffloadError("offload report has no verified remote evidence")
        remote = json.loads(remote_path.read_text(encoding="utf-8"))
        report_object = remote.get("report_object")
        if not isinstance(report_object, dict):
            raise B2OffloadError("offload report remote evidence is malformed")
        expected_sha = str(report_object.get("sha256") or "")
        expected_bytes = int(report_object.get("content_length") or 0)
        key = str(report_object.get("key") or "")
        if not key or len(expected_sha) != 64 or expected_bytes <= 0:
            raise B2OffloadError("offload report remote identity is invalid")

        suffix = observed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        restore_path = (
            self.root
            / "provider=backblaze"
            / "restore"
            / f"sample-{suffix}-{uuid4().hex}.json"
        )
        restore_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = restore_path.with_name(f".{restore_path.name}.part")
        try:
            with temporary.open("xb") as handle:
                self.store.download_fileobj(self.bucket, key, handle)
                handle.flush()
                os.fsync(handle.fileno())
            observed_sha = self.sha256_file(temporary)
            observed_bytes = temporary.stat().st_size
            passed = observed_sha == expected_sha and observed_bytes == expected_bytes
            if not passed:
                raise B2OffloadError("Backblaze restore sample checksum mismatch")
            os.link(temporary, restore_path)
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        report = json.loads(report_path.read_text(encoding="utf-8"))
        restore_report = self._restore_report_path(
            str(report.get("lot_id") or "unknown"), observed_at
        )
        self._atomic_json(restore_report, {
            "schema_version": self.restore_version,
            "lot_id": report.get("lot_id"),
            "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
            "bucket": self.bucket,
            "object_key": key,
            "expected_bytes": expected_bytes,
            "observed_bytes": observed_bytes,
            "expected_sha256": expected_sha,
            "observed_sha256": observed_sha,
            "passed": True,
            "restored_path": str(restore_path),
            "billing_cap_restoration_must_be_recorded_by_operator": True,
            "local_source_deletion_authorized": False,
        })
        return restore_report

    def plan_raw_restore(self, report_path: Path) -> dict[str, Any]:
        report_path, report, parent_manifests, objects = self._qualified_lot_context(
            report_path
        )
        lot_id = str(report["lot_id"])
        self._assert_lot_not_quarantined(lot_id)
        selected = max(objects, key=lambda item: int(item["content_length"]))
        return {
            "operation": "raw_restore_drill",
            "execute": False,
            "lot_id": lot_id,
            "lot_report": self._evidence_ref(report_path),
            "parent_manifests": [
                self._evidence_ref(Path(item["source_path"]))
                for item in parent_manifests
            ],
            "selection_rule": "largest_raw_object_in_lot",
            "selected_object": selected,
            "required_free_bytes": (
                int(selected["content_length"]) + self.minimum_free_bytes
            ),
            "minimum_free_reserve_bytes": self.minimum_free_bytes,
            "billing_cap_change_performed_by_code": False,
        }

    def restore_raw_object(
        self,
        report_path: Path,
        *,
        measured_at: datetime | None = None,
    ) -> Path:
        observed_at = self._aware_time(measured_at)
        with self._exclusive_lock():
            plan = self.plan_raw_restore(report_path)
            lot_id = str(plan["lot_id"])
            selected = dict(plan["selected_object"])
            free_bytes = int(self._disk_usage(self.root).free)
            required_bytes = int(plan["required_free_bytes"])
            if free_bytes < required_bytes:
                raise B2OffloadError(
                    "raw restore disk guard blocked drill: "
                    f"free={free_bytes}, required={required_bytes}"
                )

            sample_path = self._raw_restore_sample_path(lot_id, observed_at)
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            observed_bytes = 0
            observed_sha = ""
            passed = False
            error: Exception | None = None
            try:
                self._verify_remote_object(selected)
                with sample_path.open("xb") as handle:
                    self.store.download_fileobj(
                        self.bucket,
                        str(selected["key"]),
                        handle,
                        ExtraArgs={"VersionId": str(selected["version_id"])},
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                observed_bytes = sample_path.stat().st_size
                observed_sha = self.sha256_file(sample_path)
                passed = (
                    observed_bytes == int(selected["content_length"])
                    and observed_sha == str(selected["sha256"])
                )
                if not passed:
                    raise B2OffloadError("Backblaze raw restore checksum mismatch")
            except Exception as exc:  # Evidence must survive every failed drill.
                error = exc
            finally:
                sample_path.unlink(missing_ok=True)

            restore_report = self._raw_restore_report_path(lot_id, observed_at)
            evidence = {
                "schema_version": self.raw_restore_version,
                "lot_id": lot_id,
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "bucket": self.bucket,
                "lot_report": plan["lot_report"],
                "parent_manifests": plan["parent_manifests"],
                "selection_rule": plan["selection_rule"],
                "selected_object": selected,
                "expected_bytes": int(selected["content_length"]),
                "observed_bytes": observed_bytes,
                "expected_sha256": str(selected["sha256"]),
                "observed_sha256": observed_sha,
                "passed": passed,
                "restored_sample_path": str(sample_path),
                "restored_sample_removed": not sample_path.exists(),
                "billing_cap_elevation_and_return_evidence_required": True,
                "local_source_deletion_authorized": False,
                "error_type": type(error).__name__ if error else None,
                "error": str(error) if error else None,
            }
            self._atomic_json(restore_report, evidence)
            if error is not None:
                quarantine = self._quarantine_lot(
                    lot_id,
                    stage="raw_restore_drill",
                    reason=str(error),
                    measured_at=observed_at,
                    evidence={"raw_restore_report": self._evidence_ref(restore_report)},
                )
                raise B2OffloadError(
                    "raw restore drill failed and lot was quarantined: "
                    f"evidence={restore_report}, quarantine={quarantine}"
                ) from error
            return restore_report

    def record_billing_cap_cycle(
        self,
        raw_restore_report_path: Path,
        *,
        elevated_at: datetime,
        restored_at: datetime,
        temporary_cap_usd_per_day: float,
        operator: str,
        measured_at: datetime | None = None,
    ) -> Path:
        observed_at = self._aware_time(measured_at)
        elevated_at = self._aware_time(elevated_at)
        restored_at = self._aware_time(restored_at)
        if not operator.strip():
            raise B2OffloadError("billing cap evidence requires an operator")
        if not (
            0 < temporary_cap_usd_per_day
            <= self.maximum_temporary_billing_cap_usd
        ):
            raise B2OffloadError("temporary billing cap exceeds frozen allowance")
        if not elevated_at <= restored_at <= observed_at:
            raise B2OffloadError("billing cap evidence timestamps are inconsistent")

        with self._exclusive_lock():
            raw_path, raw = self._load_json_evidence(raw_restore_report_path)
            if (
                raw.get("schema_version") != self.raw_restore_version
                or raw.get("passed") is not True
                or raw.get("restored_sample_removed") is not True
            ):
                raise B2OffloadError("billing cap evidence requires a passed RAW drill")
            lot_id = self._safe_component(str(raw.get("lot_id") or ""))
            self._assert_lot_not_quarantined(lot_id)
            drill_at = datetime.fromisoformat(str(raw["measured_at"]))
            if not elevated_at <= drill_at <= restored_at:
                raise B2OffloadError("billing cap cycle does not enclose RAW drill")
            output = self._billing_cap_report_path(lot_id, observed_at)
            self._atomic_json(output, {
                "schema_version": self.billing_cap_version,
                "lot_id": lot_id,
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "operator": operator.strip(),
                "raw_restore_report": self._evidence_ref(raw_path),
                "original_cap_usd_per_day": 0.0,
                "temporary_cap_usd_per_day": temporary_cap_usd_per_day,
                "final_cap_usd_per_day": 0.0,
                "elevated_at": elevated_at.astimezone(timezone.utc).isoformat(),
                "restored_at": restored_at.astimezone(timezone.utc).isoformat(),
                "operator_attestation": True,
                "cap_change_performed_by_code": False,
            })
            return output

    def _qualified_lot_context(
        self,
        report_path: Path,
    ) -> tuple[
        Path,
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        report_path, report = self._load_json_evidence(report_path)
        if report.get("schema_version") != self.report_version:
            raise B2OffloadError("unsupported offload lot report")
        lot_id = self._safe_component(str(report.get("lot_id") or ""))
        remote_path = report_path.with_name(f"{report_path.name}.remote.json")
        _remote_path, remote = self._load_json_evidence(remote_path)
        report_object = remote.get("report_object")
        if not isinstance(report_object, dict):
            raise B2OffloadError("offload report remote evidence is malformed")
        if Path(str(report_object.get("source_path") or "")).resolve() != report_path:
            raise B2OffloadError("offload report remote evidence points elsewhere")
        self._verify_local_object(report_path, report_object)
        self._verify_remote_object(report_object)

        raw_objects = report.get("objects")
        if not isinstance(raw_objects, list) or not raw_objects:
            raise B2OffloadError("offload lot report has no RAW objects")
        objects = [self._qualification_object(item) for item in raw_objects]
        sessions = {date.fromisoformat(str(item["session_date"])) for item in objects}
        datasets = {str(item["dataset"]) for item in objects}
        if not is_complete_qualification_tick_lot(
            session_dates=sessions,
            datasets=datasets,
        ):
            raise B2OffloadError(
                "local deletion is restricted to one complete frozen trades/quotes lot"
            )
        identities = {(item["dataset"], item["session_date"]) for item in objects}
        if len(identities) != len(objects):
            raise B2OffloadError("offload lot report contains duplicate RAW objects")
        if str(report.get("lot_id")) != lot_id:
            raise B2OffloadError("offload lot id is not canonical")
        parent_manifests = self._qualification_parent_manifests(
            report,
            expected_sessions=sessions,
        )
        return report_path, report, parent_manifests, sorted(
            objects,
            key=lambda item: (str(item["dataset"]), str(item["session_date"])),
        )

    def _qualification_parent_manifests(
        self,
        report: dict[str, Any],
        *,
        expected_sessions: set[date],
    ) -> list[dict[str, Any]]:
        values = report.get("parent_manifests")
        if not isinstance(values, list) or not values:
            raise B2OffloadError("offload lot report has no parent manifests")
        output: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for value in values:
            if not isinstance(value, dict):
                raise B2OffloadError("offload parent manifest identity is malformed")
            key = str(value.get("key") or "")
            match = re.fullmatch(
                rf"{re.escape(self.prefix)}/manifests/provider=massive/"
                r"session_date=(?P<session>\d{4}-\d{2}-\d{2})/"
                r"(?P<filename>[^/]+\.json)",
                key,
            )
            if match is None:
                raise B2OffloadError("offload parent manifest is outside canonical path")
            session = date.fromisoformat(match.group("session"))
            if session not in expected_sessions:
                raise B2OffloadError("offload parent manifest session does not match lot")
            source = Path(str(value.get("source_path") or "")).resolve()
            canonical_parent = (
                self.root
                / "provider=massive"
                / "manifests"
                / f"session_date={session.isoformat()}"
            ).resolve()
            self._assert_below_root(source)
            if source.parent != canonical_parent or source.name != match.group("filename"):
                raise B2OffloadError("offload parent manifest source is not canonical")
            normalized = {
                "key": key,
                "content_length": int(value.get("content_length") or 0),
                "sha256": str(value.get("sha256") or ""),
                "version_id": str(value.get("version_id") or ""),
                "source_path": str(source),
                "session_date": session.isoformat(),
            }
            if (
                normalized["content_length"] <= 0
                or len(normalized["sha256"]) != 64
                or not normalized["version_id"]
                or source in seen
            ):
                raise B2OffloadError("offload parent manifest identity is incomplete")
            self._verify_local_object(source, normalized)
            self._verify_remote_object(normalized)
            seen.add(source)
            output.append(normalized)
        return sorted(output, key=lambda item: str(item["source_path"]))

    def _qualification_object(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise B2OffloadError("offload lot object is malformed")
        key = str(value.get("key") or "")
        match = re.fullmatch(
            rf"{re.escape(self.prefix)}/raw/provider=massive/"
            r"dataset=(?P<dataset>[^/]+)/session_date="
            r"(?P<session>\d{4}-\d{2}-\d{2})/source\.csv\.gz",
            key,
        )
        if match is None:
            raise B2OffloadError("offload lot object is outside canonical RAW path")
        dataset = match.group("dataset")
        session = date.fromisoformat(match.group("session"))
        if (
            dataset not in QUALIFICATION_TICK_DATASETS
            or session not in QUALIFICATION_SESSION_DATES
        ):
            raise B2OffloadError("offload lot object is outside frozen qualification scope")
        source = Path(str(value.get("source_path") or "")).resolve()
        canonical_source = (
            self.root
            / "provider=massive"
            / f"dataset={dataset}"
            / f"session_date={session.isoformat()}"
            / "source.csv.gz"
        ).resolve()
        self._assert_below_root(source)
        if source != canonical_source:
            raise B2OffloadError("offload lot source path is not canonical")
        content_length = int(value.get("content_length") or 0)
        sha256 = str(value.get("sha256") or "")
        version_id = str(value.get("version_id") or "")
        if content_length <= 0 or len(sha256) != 64 or not version_id:
            raise B2OffloadError("offload lot object identity is incomplete")
        return {
            "dataset": dataset,
            "session_date": session.isoformat(),
            "key": key,
            "content_length": content_length,
            "sha256": sha256,
            "version_id": version_id,
            "source_path": str(source),
        }

    def _validated_raw_restore(
        self,
        raw_restore_report_path: Path,
        *,
        report_path: Path,
        report: dict[str, Any],
        parent_manifests: list[dict[str, Any]],
        objects: list[dict[str, Any]],
    ) -> tuple[Path, dict[str, Any]]:
        raw_path, raw = self._load_json_evidence(raw_restore_report_path)
        if (
            raw.get("schema_version") != self.raw_restore_version
            or raw.get("passed") is not True
            or raw.get("restored_sample_removed") is not True
            or str(raw.get("lot_id")) != str(report.get("lot_id"))
        ):
            raise B2OffloadError("RAW restore evidence does not authorize deletion")
        if raw.get("lot_report") != self._evidence_ref(report_path):
            raise B2OffloadError("RAW restore evidence is not chained to lot report")
        expected_parents = [
            self._evidence_ref(Path(item["source_path"]))
            for item in parent_manifests
        ]
        if raw.get("parent_manifests") != expected_parents:
            raise B2OffloadError("RAW restore evidence is not chained to parent manifests")
        selected = raw.get("selected_object")
        largest = max(objects, key=lambda item: int(item["content_length"]))
        if not isinstance(selected, dict) or any(
            selected.get(field) != largest.get(field)
            for field in ("key", "content_length", "sha256", "version_id")
        ):
            raise B2OffloadError("RAW restore did not sample the largest lot object")
        restored_path = Path(str(raw.get("restored_sample_path") or "")).resolve()
        self._assert_below_root(restored_path)
        if restored_path.exists():
            raise B2OffloadError("RAW restore sample was not cleaned up")
        return raw_path, raw

    def _validated_billing_cap_evidence(
        self,
        billing_cap_evidence_path: Path,
        *,
        lot_id: str,
        raw_restore_path: Path,
    ) -> tuple[Path, dict[str, Any]]:
        cap_path, cap = self._load_json_evidence(billing_cap_evidence_path)
        if (
            cap.get("schema_version") != self.billing_cap_version
            or str(cap.get("lot_id")) != lot_id
            or cap.get("operator_attestation") is not True
            or float(cap.get("original_cap_usd_per_day", -1)) != 0.0
            or float(cap.get("final_cap_usd_per_day", -1)) != 0.0
            or not (
                0 < float(cap.get("temporary_cap_usd_per_day", 0))
                <= self.maximum_temporary_billing_cap_usd
            )
        ):
            raise B2OffloadError("billing cap evidence is incomplete or out of bounds")
        if cap.get("raw_restore_report") != self._evidence_ref(raw_restore_path):
            raise B2OffloadError("billing cap evidence is not chained to RAW restore")
        return cap_path, cap

    def _verify_local_object(self, source: Path, expected: dict[str, Any]) -> None:
        self._assert_below_root(source)
        if not source.is_file():
            raise B2OffloadError(f"local evidence object is missing: {source}")
        if source.stat().st_size != int(expected.get("content_length") or 0):
            raise B2OffloadError(f"local evidence object byte count changed: {source}")
        if self.sha256_file(source) != str(expected.get("sha256") or ""):
            raise B2OffloadError(f"local evidence object checksum changed: {source}")

    def _verify_remote_object(self, expected: dict[str, Any]) -> dict[str, Any]:
        key = str(expected.get("key") or "")
        remote = self._head_or_none(key)
        if remote is None:
            raise B2OffloadError(f"Backblaze object is missing: {key}")
        metadata = {
            str(name).lower(): str(value)
            for name, value in (remote.get("Metadata") or {}).items()
        }
        if (
            int(remote.get("ContentLength") or 0)
            != int(expected.get("content_length") or 0)
            or metadata.get("sha256") != str(expected.get("sha256") or "")
            or str(remote.get("VersionId") or "")
            != str(expected.get("version_id") or "")
        ):
            raise B2OffloadError(f"Backblaze immutable identity changed: {key}")
        return remote

    def _load_json_evidence(self, path: Path) -> tuple[Path, dict[str, Any]]:
        resolved = Path(path).resolve()
        self._assert_below_root(resolved)
        if not resolved.is_file():
            raise B2OffloadError(f"evidence file is missing: {resolved}")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise B2OffloadError(f"evidence file is malformed: {resolved}")
        return resolved, payload

    def _evidence_ref(self, path: Path) -> dict[str, str]:
        resolved = Path(path).resolve()
        self._assert_below_root(resolved)
        if not resolved.is_file():
            raise B2OffloadError(f"evidence file is missing: {resolved}")
        return {"path": str(resolved), "sha256": self.sha256_file(resolved)}

    def _assert_lot_not_quarantined(self, lot_id: str) -> None:
        quarantine_dir = self._lot_quarantine_dir(lot_id)
        if quarantine_dir.exists() and next(quarantine_dir.glob("quarantine-*.json"), None):
            raise B2OffloadError(
                "lot is quarantined; six-hands review is required before any retry"
            )

    def _quarantine_lot(
        self,
        lot_id: str,
        *,
        stage: str,
        reason: str,
        measured_at: datetime,
        evidence: dict[str, Any],
    ) -> Path:
        output = self._quarantine_record_path(lot_id, measured_at)
        self._atomic_json(output, {
            "schema_version": self.quarantine_version,
            "lot_id": lot_id,
            "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
            "stage": stage,
            "reason": reason,
            "evidence": evidence,
            "quarantined": True,
            "automatic_retry_allowed": False,
            "unlock_requires_six_hands": True,
        })
        return output

    def _latest_successful_deletion(
        self,
        lot_id: str,
        report_path: Path,
    ) -> Path | None:
        directory = self._deletion_record_dir(lot_id)
        if not directory.exists():
            return None
        expected_report = self._evidence_ref(report_path)
        for candidate in sorted(directory.glob("deletion-*.json"), reverse=True):
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if (
                payload.get("schema_version") == self.deletion_version
                and payload.get("status") == "completed"
                and payload.get("passed") is True
                and payload.get("lot_report") == expected_report
            ):
                return candidate.resolve()
        return None

    @staticmethod
    def _aware_time(value: datetime | None) -> datetime:
        observed = value or datetime.now(timezone.utc)
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return observed

    def plan_delete_lot(
        self,
        report_path: Path,
        *,
        raw_restore_report_path: Path,
        billing_cap_evidence_path: Path,
        requested_paths: Sequence[Path] | None = None,
    ) -> dict[str, Any]:
        report_path, report, parent_manifests, objects = self._qualified_lot_context(
            report_path
        )
        lot_id = str(report["lot_id"])
        self._assert_lot_not_quarantined(lot_id)
        raw_path, _raw = self._validated_raw_restore(
            raw_restore_report_path,
            report_path=report_path,
            report=report,
            parent_manifests=parent_manifests,
            objects=objects,
        )
        cap_path, cap = self._validated_billing_cap_evidence(
            billing_cap_evidence_path,
            lot_id=lot_id,
            raw_restore_path=raw_path,
        )
        report_sources = {Path(str(item["source_path"])).resolve() for item in objects}
        if requested_paths is not None:
            requested = {Path(path).resolve() for path in requested_paths}
            if requested != report_sources:
                raise B2OffloadError(
                    "requested deletion paths must exactly match immutable lot report"
                )

        entries = []
        for item in objects:
            source = Path(str(item["source_path"])).resolve()
            exists = source.exists()
            entries.append({
                **item,
                "source_path": str(source),
                "local_exists": exists,
                "planned_delete_bytes": int(item["content_length"]) if exists else 0,
            })
        existing_count = sum(bool(item["local_exists"]) for item in entries)
        prior = self._latest_successful_deletion(lot_id, report_path)
        if existing_count == 0:
            if prior is None:
                raise B2OffloadError(
                    "lot sources are missing without prior successful deletion evidence"
                )
            status = "already_deleted"
        elif existing_count != len(entries):
            raise B2OffloadError("lot is partially missing; refusing further deletion")
        else:
            status = "ready"
        return {
            "operation": "delete_qualification_tick_lot",
            "execute": False,
            "status": status,
            "lot_id": lot_id,
            "session_date": entries[0]["session_date"],
            "datasets": sorted(item["dataset"] for item in entries),
            "objects": entries,
            "planned_delete_bytes": sum(
                int(item["planned_delete_bytes"]) for item in entries
            ),
            "parent_manifests": [
                self._evidence_ref(Path(item["source_path"]))
                for item in parent_manifests
            ],
            "lot_report": self._evidence_ref(report_path),
            "raw_restore_report": self._evidence_ref(raw_path),
            "billing_cap_evidence": self._evidence_ref(cap_path),
            "prior_successful_deletion": (
                self._evidence_ref(prior) if prior is not None else None
            ),
            "billing_cap_final_usd_per_day": cap["final_cap_usd_per_day"],
            "minute_aggregates_authorized_for_deletion": False,
        }

    def delete_lot(
        self,
        report_path: Path,
        *,
        raw_restore_report_path: Path,
        billing_cap_evidence_path: Path,
        requested_paths: Sequence[Path] | None = None,
        measured_at: datetime | None = None,
    ) -> Path:
        observed_at = self._aware_time(measured_at)
        with self._exclusive_lock():
            identified_path, identified_lot_id = self._deletion_target_identity(
                report_path
            )
            try:
                plan = self.plan_delete_lot(
                    report_path,
                    raw_restore_report_path=raw_restore_report_path,
                    billing_cap_evidence_path=billing_cap_evidence_path,
                    requested_paths=requested_paths,
                )
            except Exception as exc:
                if (
                    identified_path is not None
                    and identified_lot_id is not None
                    and not self._lot_quarantine_dir(identified_lot_id).exists()
                ):
                    failure = self._deletion_record_path(identified_lot_id, observed_at)
                    self._atomic_json(failure, {
                        "schema_version": self.deletion_version,
                        "lot_id": identified_lot_id,
                        "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                        "status": "preflight_failed_quarantined",
                        "passed": False,
                        "lot_report": self._evidence_ref(identified_path),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    })
                    quarantine = self._quarantine_lot(
                        identified_lot_id,
                        stage="lot_deletion_preflight",
                        reason=str(exc),
                        measured_at=observed_at,
                        evidence={"failure": self._evidence_ref(failure)},
                    )
                    raise B2OffloadError(
                        "lot deletion preflight failed and lot was quarantined: "
                        f"failure={failure}, quarantine={quarantine}"
                    ) from exc
                raise
            lot_id = str(plan["lot_id"])
            if plan["status"] == "already_deleted":
                output = self._deletion_record_path(lot_id, observed_at)
                self._atomic_json(output, {
                    "schema_version": self.deletion_version,
                    "lot_id": lot_id,
                    "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                    "status": "no_op_already_deleted",
                    "passed": True,
                    "deleted_objects": [],
                    "parent_manifests": plan["parent_manifests"],
                    "lot_report": plan["lot_report"],
                    "raw_restore_report": plan["raw_restore_report"],
                    "billing_cap_evidence": plan["billing_cap_evidence"],
                    "prior_successful_deletion": plan["prior_successful_deletion"],
                    "minute_aggregates_deleted": False,
                })
                return output

            intent_path = self._deletion_intent_path(lot_id, observed_at)
            self._atomic_json(intent_path, {
                "schema_version": self.deletion_version,
                "lot_id": lot_id,
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "status": "authorized_pending_execution",
                "plan": plan,
            })
            deleted: list[dict[str, Any]] = []
            try:
                for item in plan["objects"]:
                    source = Path(str(item["source_path"])).resolve()
                    self._verify_local_object(source, item)
                    self._verify_remote_object(item)
                for item in plan["objects"]:
                    source = Path(str(item["source_path"])).resolve()
                    self._verify_remote_object(item)
                    source.unlink()
                    deleted.append({
                        "source_path": str(source),
                        "content_length": int(item["content_length"]),
                        "sha256": str(item["sha256"]),
                        "remote_key": str(item["key"]),
                        "version_id": str(item["version_id"]),
                    })
            except Exception as exc:
                failure = self._deletion_record_path(lot_id, observed_at)
                self._atomic_json(failure, {
                    "schema_version": self.deletion_version,
                    "lot_id": lot_id,
                    "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                    "status": "failed_quarantined",
                    "passed": False,
                    "intent": self._evidence_ref(intent_path),
                    "deleted_objects_before_failure": deleted,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })
                quarantine = self._quarantine_lot(
                    lot_id,
                    stage="lot_deletion",
                    reason=str(exc),
                    measured_at=observed_at,
                    evidence={
                        "intent": self._evidence_ref(intent_path),
                        "failure": self._evidence_ref(failure),
                    },
                )
                raise B2OffloadError(
                    "lot deletion failed and lot was quarantined: "
                    f"failure={failure}, quarantine={quarantine}"
                ) from exc

            output = self._deletion_record_path(lot_id, observed_at)
            self._atomic_json(output, {
                "schema_version": self.deletion_version,
                "lot_id": lot_id,
                "session_date": plan["session_date"],
                "datasets": plan["datasets"],
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "status": "completed",
                "passed": True,
                "intent": self._evidence_ref(intent_path),
                "parent_manifests": plan["parent_manifests"],
                "lot_report": plan["lot_report"],
                "raw_restore_report": plan["raw_restore_report"],
                "billing_cap_evidence": plan["billing_cap_evidence"],
                "deleted_objects": deleted,
                "deleted_bytes": sum(item["content_length"] for item in deleted),
                "parent_manifests_preserved": True,
                "metadata_sidecars_preserved": True,
                "minute_aggregates_deleted": False,
                "local_source_deletion_scope": "qualification_ticks_only",
                "backblaze_is_primary_archive_after_deletion": True,
                "catastrophic_fallback": "Massive re-download verified against frozen T0 metadata",
            })
            return output

    def _deletion_target_identity(
        self,
        report_path: Path,
    ) -> tuple[Path | None, str | None]:
        try:
            resolved, report = self._load_json_evidence(report_path)
            if report.get("schema_version") != self.report_version:
                return None, None
            return resolved, self._safe_component(str(report.get("lot_id") or ""))
        except Exception:
            return None, None

    def _offload_artifact(self, artifact: dict[str, Any]) -> OffloadedObject:
        source = self._source_path(artifact)
        expected_bytes = int(artifact["content_length"])
        expected_sha = str(artifact["sha256"])
        if source.stat().st_size != expected_bytes:
            raise B2OffloadError(f"local artifact byte count differs from manifest: {source}")
        if self.sha256_file(source) != expected_sha:
            raise B2OffloadError(f"local artifact checksum differs from manifest: {source}")
        return self._upload_verified(
            source,
            key=self._raw_key(artifact),
            metadata={
                "sha256": expected_sha,
                "source-provider": "massive",
                "source-dataset": str(artifact["dataset"]),
                "session-date": str(artifact["session_date"]),
            },
        )

    def _offload_parent_manifest(self, parent: dict[str, str]) -> OffloadedObject:
        source = Path(parent["path"]).resolve()
        self._assert_below_root(source)
        session_date = date.fromisoformat(parent["session_date"]).isoformat()
        expected_sha = parent["sha256"]
        if self.sha256_file(source) != expected_sha:
            raise B2OffloadError(f"parent manifest checksum changed: {source}")
        return self._upload_verified(
            source,
            key=(
                f"{self.prefix}/manifests/provider=massive/"
                f"session_date={session_date}/{source.name}"
            ),
            metadata={
                "sha256": expected_sha,
                "artifact-kind": "massive-source-manifest",
                "session-date": session_date,
            },
        )

    def _upload_verified(
        self,
        source: Path,
        *,
        key: str,
        metadata: dict[str, str],
    ) -> OffloadedObject:
        expected_bytes = source.stat().st_size
        expected_sha = self.sha256_file(source)
        expected_metadata = {**metadata, "sha256": expected_sha}
        existing = self._head_or_none(key)
        reused = existing is not None
        if existing is None:
            self.store.upload_file(
                str(source),
                self.bucket,
                key,
                ExtraArgs={"Metadata": expected_metadata},
            )
            existing = self._head_or_none(key)
        if existing is None:
            raise B2OffloadError(f"Backblaze object missing after upload: {key}")
        remote_metadata = {
            str(name).lower(): str(value)
            for name, value in (existing.get("Metadata") or {}).items()
        }
        if (
            int(existing.get("ContentLength") or 0) != expected_bytes
            or any(
                remote_metadata.get(name.lower()) != value
                for name, value in expected_metadata.items()
            )
        ):
            raise B2OffloadError(f"Backblaze object conflicts with immutable source: {key}")
        return OffloadedObject(
            key=key,
            content_length=expected_bytes,
            sha256=expected_sha,
            version_id=str(existing.get("VersionId") or "") or None,
            reused_existing_object=reused,
            source_path=str(source),
        )

    def _load_manifests(
        self,
        manifest_paths: Sequence[Path],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        if not manifest_paths:
            raise B2OffloadError("at least one Massive manifest is required")
        parents: list[dict[str, str]] = []
        artifacts_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
        for original_path in sorted({Path(path).resolve() for path in manifest_paths}):
            self._assert_below_root(original_path)
            payload = json.loads(original_path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "DAY-D-MASSIVE-ARCHIVE-v1":
                raise B2OffloadError(f"unsupported Massive manifest: {original_path}")
            if payload.get("official_replay_ready") is not False:
                raise B2OffloadError("source manifest must remain non-official")
            parent_sha = self.sha256_file(original_path)
            session_date = date.fromisoformat(str(payload.get("session_date"))).isoformat()
            parents.append({
                "path": str(original_path),
                "sha256": parent_sha,
                "session_date": session_date,
            })
            artifacts = payload.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                raise B2OffloadError(f"Massive manifest has no artifacts: {original_path}")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    raise B2OffloadError("Massive manifest artifact is malformed")
                normalized = {
                    key: artifact.get(key)
                    for key in (
                        "dataset",
                        "session_date",
                        "bucket",
                        "object_key",
                        "content_length",
                        "remote_etag",
                        "local_path",
                        "sha256",
                    )
                }
                identity = (
                    str(normalized.get("dataset")),
                    str(normalized.get("session_date")),
                )
                existing = artifacts_by_identity.get(identity)
                if existing is not None and existing != normalized:
                    raise B2OffloadError(f"conflicting Massive artifact manifests: {identity}")
                artifacts_by_identity[identity] = normalized
        return parents, [artifacts_by_identity[key] for key in sorted(artifacts_by_identity)]

    def _source_path(self, artifact: dict[str, Any]) -> Path:
        source = Path(str(artifact.get("local_path") or "")).resolve()
        self._assert_below_root(source)
        if not source.is_file():
            raise B2OffloadError(f"local artifact is missing: {source}")
        return source

    def _raw_key(self, artifact: dict[str, Any]) -> str:
        dataset = self._safe_component(str(artifact["dataset"]))
        session_date = date.fromisoformat(str(artifact["session_date"])).isoformat()
        return (
            f"{self.prefix}/raw/provider=massive/dataset={dataset}/"
            f"session_date={session_date}/source.csv.gz"
        )

    def _head_or_none(self, key: str) -> dict[str, Any] | None:
        try:
            return self.store.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def _assert_below_root(self, path: Path) -> None:
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise B2OffloadError(f"path is outside the Day D data root: {path}") from exc

    @contextmanager
    def _exclusive_lock(self):  # noqa: ANN202 - contextmanager iterator
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".b2-offload.lock"
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise B2OffloadError("another Backblaze offload is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _report_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "offload"
            / f"lot_id={lot_id}"
            / f"offload-{suffix}.json"
        )

    def _restore_report_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "restore-reports"
            / f"lot_id={self._safe_component(lot_id)}"
            / f"restore-{suffix}.json"
        )

    def _raw_restore_sample_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "raw-restore-samples"
            / f"lot_id={self._safe_component(lot_id)}"
            / f"sample-{suffix}-{uuid4().hex}.raw"
        )

    def _raw_restore_report_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "raw-restore-reports"
            / f"lot_id={self._safe_component(lot_id)}"
            / f"raw-restore-{suffix}.json"
        )

    def _billing_cap_report_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "billing-cap-evidence"
            / f"lot_id={self._safe_component(lot_id)}"
            / f"billing-cap-{suffix}.json"
        )

    def _deletion_record_dir(self, lot_id: str) -> Path:
        return (
            self.root
            / "provider=backblaze"
            / "deletion-records"
            / f"lot_id={self._safe_component(lot_id)}"
        )

    def _deletion_record_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return self._deletion_record_dir(lot_id) / f"deletion-{suffix}-{uuid4().hex}.json"

    def _deletion_intent_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=backblaze"
            / "deletion-intents"
            / f"lot_id={self._safe_component(lot_id)}"
            / f"intent-{suffix}-{uuid4().hex}.json"
        )

    def _lot_quarantine_dir(self, lot_id: str) -> Path:
        return (
            self.root
            / "provider=backblaze"
            / "quarantine"
            / f"lot_id={self._safe_component(lot_id)}"
        )

    def _quarantine_record_path(self, lot_id: str, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return self._lot_quarantine_dir(lot_id) / f"quarantine-{suffix}-{uuid4().hex}.json"

    @staticmethod
    def _safe_component(value: str) -> str:
        cleaned = value.strip()
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
        if not cleaned or any(character not in allowed for character in cleaned):
            raise B2OffloadError(f"unsafe object-key component: {value!r}")
        return cleaned

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.part")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _build_store(key_id: str, application_key: str, endpoint: str, region: str) -> B2Store:
    if not key_id or not application_key:
        raise B2OffloadError("Backblaze B2 credentials are not configured")
    import boto3
    from botocore.config import Config

    return boto3.Session(
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
        region_name=region,
    ).client(
        "s3",
        endpoint_url=endpoint,
        config=Config(signature_version="s3v4"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    from app.config import get_settings

    parser = argparse.ArgumentParser(
        description="Offload immutable Day D artifacts to Backblaze B2"
    )
    parser.add_argument("--manifest", action="append", type=Path)
    parser.add_argument("--lot-id")
    parser.add_argument("--offload", action="store_true")
    parser.add_argument("--restore-report", type=Path)
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--raw-drill-report", type=Path)
    parser.add_argument("--execute-raw-drill", action="store_true")
    parser.add_argument("--record-billing-cap-cycle", type=Path)
    parser.add_argument("--cap-elevated-at")
    parser.add_argument("--cap-restored-at")
    parser.add_argument("--temporary-cap-usd", type=float)
    parser.add_argument("--operator")
    parser.add_argument("--delete-lot", type=Path)
    parser.add_argument("--raw-restore-report", type=Path)
    parser.add_argument("--billing-cap-evidence", type=Path)
    parser.add_argument("--delete-path", action="append", type=Path)
    parser.add_argument("--execute-delete-lot", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    archive = DayDB2Offload(
        _build_store(
            settings.day_d_b2_key_id,
            settings.day_d_b2_application_key,
            settings.day_d_b2_endpoint,
            settings.day_d_b2_region,
        ),
        root=settings.day_d_dataset_root,
        bucket=settings.day_d_b2_bucket,
    )
    if args.raw_drill_report:
        if args.execute_raw_drill:
            path = archive.restore_raw_object(args.raw_drill_report)
            print(json.dumps({"raw_drill_executed": True, "report": str(path)}, sort_keys=True))
        else:
            print(json.dumps(
                archive.plan_raw_restore(args.raw_drill_report),
                indent=2,
                sort_keys=True,
            ))
        return 0
    if args.record_billing_cap_cycle:
        if not all((args.cap_elevated_at, args.cap_restored_at, args.operator)):
            parser.error(
                "--record-billing-cap-cycle requires --cap-elevated-at, "
                "--cap-restored-at and --operator"
            )
        if args.temporary_cap_usd is None:
            parser.error("--record-billing-cap-cycle requires --temporary-cap-usd")
        path = archive.record_billing_cap_cycle(
            args.record_billing_cap_cycle,
            elevated_at=datetime.fromisoformat(args.cap_elevated_at),
            restored_at=datetime.fromisoformat(args.cap_restored_at),
            temporary_cap_usd_per_day=args.temporary_cap_usd,
            operator=args.operator,
        )
        print(json.dumps({"billing_cap_cycle_recorded": True, "report": str(path)}, sort_keys=True))
        return 0
    if args.delete_lot:
        if not args.raw_restore_report or not args.billing_cap_evidence:
            parser.error(
                "--delete-lot requires --raw-restore-report and --billing-cap-evidence"
            )
        operation = archive.delete_lot if args.execute_delete_lot else archive.plan_delete_lot
        result = operation(
            args.delete_lot,
            raw_restore_report_path=args.raw_restore_report,
            billing_cap_evidence_path=args.billing_cap_evidence,
            requested_paths=args.delete_path,
        )
        if isinstance(result, Path):
            print(json.dumps({"lot_deleted": True, "report": str(result)}, sort_keys=True))
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.restore:
        if not args.restore_report:
            parser.error("--restore requires --restore-report")
        path = archive.restore_report_sample(args.restore_report)
        print(json.dumps({"restored": True, "report": str(path)}, sort_keys=True))
        return 0
    if not args.manifest or not args.lot_id:
        parser.error("plan/offload requires --manifest and --lot-id")
    if args.offload:
        path = archive.offload(args.manifest, lot_id=args.lot_id)
        print(json.dumps({"offloaded": True, "report": str(path)}, sort_keys=True))
    else:
        plan = archive.plan(args.manifest)
        print(json.dumps({
            "offloaded": False,
            "artifacts": plan,
            "total_bytes": sum(item["content_length"] for item in plan),
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
