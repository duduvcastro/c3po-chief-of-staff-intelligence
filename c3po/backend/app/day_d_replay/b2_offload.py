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
from typing import Any, BinaryIO, Protocol, Sequence
from uuid import uuid4


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

    def download_fileobj(self, Bucket: str, Key: str, Fileobj: BinaryIO) -> None: ...


@dataclass(frozen=True, slots=True)
class OffloadedObject:
    key: str
    content_length: int
    sha256: str
    version_id: str | None
    reused_existing_object: bool
    source_path: str


class DayDB2Offload:
    """Immutable B2 offload with remote metadata verification and restore evidence.

    This class never removes a local source and never changes Backblaze billing
    caps. Those remain explicit operator actions under the frozen retention
    contract.
    """

    report_version = "DAY-D-B2-OFFLOAD-v1"
    restore_version = "DAY-D-B2-RESTORE-v1"

    def __init__(
        self,
        store: B2Store,
        *,
        root: Path,
        bucket: str,
        prefix: str = "day-d",
    ) -> None:
        if not bucket.strip():
            raise B2OffloadError("Backblaze bucket is not configured")
        self.store = store
        self.root = root.resolve()
        self.bucket = bucket.strip()
        self.prefix = prefix.strip("/")

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

    parser = argparse.ArgumentParser(description="Offload immutable Day D artifacts to Backblaze B2")
    parser.add_argument("--manifest", action="append", type=Path)
    parser.add_argument("--lot-id")
    parser.add_argument("--offload", action="store_true")
    parser.add_argument("--restore-report", type=Path)
    parser.add_argument("--restore", action="store_true")
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
