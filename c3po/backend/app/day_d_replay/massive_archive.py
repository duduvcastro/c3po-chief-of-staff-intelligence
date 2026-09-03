from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, BinaryIO, Callable, Protocol, Sequence
from uuid import uuid4

from .massive_campaign import CampaignGuardError, MassiveCampaignGuard
from .qualification_scope import (
    QUALIFICATION_SESSION_DATES,
    QUALIFICATION_TICK_DATASETS,
)


class MassiveArchiveError(RuntimeError):
    pass


class FlatFileDataset(StrEnum):
    TRADES = "trades"
    QUOTES = "quotes"
    MINUTE_AGGREGATES = "minute_aggregates"
    DAY_AGGREGATES = "day_aggregates"

    @property
    def provider_path(self) -> str:
        return {
            self.TRADES: "trades_v1",
            self.QUOTES: "quotes_v1",
            self.MINUTE_AGGREGATES: "minute_aggs_v1",
            self.DAY_AGGREGATES: "day_aggs_v1",
        }[self]


class ObjectStore(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...

    def download_fileobj(self, Bucket: str, Key: str, Fileobj: BinaryIO) -> None: ...


@dataclass(frozen=True, slots=True)
class PlannedArtifact:
    dataset: str
    session_date: str
    bucket: str
    object_key: str
    content_length: int
    remote_etag: str | None
    local_path: str


@dataclass(frozen=True, slots=True)
class ArchivedArtifact:
    dataset: str
    session_date: str
    bucket: str
    object_key: str
    content_length: int
    remote_etag: str | None
    local_path: str
    sha256: str
    reused_existing_file: bool


DEFAULT_PER_SESSION_ABORT_BYTES = 25_416_665_942
DEFAULT_LOCAL_SPOOL_CEILING_BYTES = 76_249_997_826


def current_massive_spool_bytes(root: Path) -> int:
    total = 0
    for metadata_path in root.glob(
        "provider=massive/dataset=*/session_date=*/source.csv.gz.metadata.json"
    ):
        source_path = metadata_path.with_name("source.csv.gz")
        if source_path.exists():
            total += source_path.stat().st_size
    return total


def assert_massive_local_capacity(
    *,
    root: Path,
    artifacts: Sequence[PlannedArtifact],
    minimum_free_bytes: int,
    per_session_abort_bytes: int = DEFAULT_PER_SESSION_ABORT_BYTES,
    local_spool_ceiling_bytes: int = DEFAULT_LOCAL_SPOOL_CEILING_BYTES,
    drill_headroom_bytes: int = 0,
    disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
) -> None:
    session_totals: dict[str, int] = {}
    required_by_path: dict[Path, int] = {}
    for artifact in artifacts:
        session_totals[artifact.session_date] = (
            session_totals.get(artifact.session_date, 0) + artifact.content_length
        )
        local_path = Path(artifact.local_path)
        if not local_path.exists():
            required_by_path[local_path] = artifact.content_length
    for session_date, planned_bytes in sorted(session_totals.items()):
        limit = max(0, per_session_abort_bytes)
        if planned_bytes > limit:
            raise MassiveArchiveError(
                "per-session byte guard blocked Massive download: "
                f"session={session_date}, planned={planned_bytes}, limit={limit}"
            )
    required_bytes = sum(required_by_path.values())
    current_spool_bytes = current_massive_spool_bytes(root)
    ceiling = max(0, local_spool_ceiling_bytes)
    if current_spool_bytes + required_bytes > ceiling:
        raise MassiveArchiveError(
            "local spool guard blocked Massive download: "
            f"current={current_spool_bytes}, download={required_bytes}, "
            f"ceiling={ceiling}"
        )
    free_bytes = int(disk_usage(root).free)
    reserve = max(0, minimum_free_bytes)
    if free_bytes - required_bytes - drill_headroom_bytes < reserve:
        raise MassiveArchiveError(
            "disk guard blocked Massive download: "
            f"free={free_bytes}, download={required_bytes}, "
            f"drill_headroom={drill_headroom_bytes}, reserve={reserve}"
        )


class MassiveFlatFileArchive:
    """Fail-closed local spool for immutable Massive Flat Files.

    Downloads are explicit, disk-guarded and atomic. Existing artifacts are
    never overwritten, and every completed batch receives a SHA-256 manifest.
    """

    manifest_version = "DAY-D-MASSIVE-ARCHIVE-v1"

    def __init__(
        self,
        store: ObjectStore,
        *,
        root: Path,
        bucket: str = "flatfiles",
        minimum_free_bytes: int = 20 * 1024**3,
        per_session_abort_bytes: int = DEFAULT_PER_SESSION_ABORT_BYTES,
        local_spool_ceiling_bytes: int = DEFAULT_LOCAL_SPOOL_CEILING_BYTES,
        campaign_guard: MassiveCampaignGuard | None = None,
        disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
        expected_orphan_parts: frozenset[str] | None = None,
        locked_write_preflight: Callable[[], None] | None = None,
    ) -> None:
        self.store = store
        self.root = root
        self.bucket = bucket
        self.minimum_free_bytes = max(0, minimum_free_bytes)
        self.per_session_abort_bytes = max(0, per_session_abort_bytes)
        self.local_spool_ceiling_bytes = max(0, local_spool_ceiling_bytes)
        self.campaign_guard = campaign_guard or MassiveCampaignGuard(
            root=root,
            download_authorized=False,
        )
        self._disk_usage = disk_usage
        if expected_orphan_parts is not None:
            for relative in expected_orphan_parts:
                path = Path(relative)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in {"", ".", ".."} for part in path.parts)
                ):
                    raise ValueError("expected orphan path is not a safe relative path")
        self._expected_orphan_parts = expected_orphan_parts
        self._locked_write_preflight = locked_write_preflight

    def plan(
        self,
        *,
        session_date: date,
        datasets: Sequence[FlatFileDataset],
    ) -> tuple[PlannedArtifact, ...]:
        unique_datasets = tuple(dict.fromkeys(datasets))
        if not unique_datasets:
            raise MassiveArchiveError("at least one Massive dataset is required")
        output: list[PlannedArtifact] = []
        for dataset in unique_datasets:
            key = self.object_key(dataset, session_date)
            metadata = self.store.head_object(Bucket=self.bucket, Key=key)
            try:
                content_length = int(metadata["ContentLength"])
            except (KeyError, TypeError, ValueError) as exc:
                raise MassiveArchiveError(f"Massive object has no valid size: {key}") from exc
            if content_length <= 0:
                raise MassiveArchiveError(f"Massive object is empty: {key}")
            output.append(PlannedArtifact(
                dataset=dataset.value,
                session_date=session_date.isoformat(),
                bucket=self.bucket,
                object_key=key,
                content_length=content_length,
                remote_etag=self._clean_etag(metadata.get("ETag")),
                local_path=str(self.local_path(dataset, session_date)),
            ))
        return tuple(output)

    def download(
        self,
        *,
        session_date: date,
        datasets: Sequence[FlatFileDataset],
        measured_at: datetime | None = None,
        expected_plan: Sequence[PlannedArtifact] | None = None,
    ) -> Path:
        observed_at = measured_at or datetime.now(timezone.utc)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("measured_at must be timezone-aware")
        self.root.mkdir(parents=True, exist_ok=True)
        with self._exclusive_download_lock():
            self._quarantine_orphan_parts(observed_at)
            try:
                self.campaign_guard.assert_download_authorized()
            except CampaignGuardError as exc:
                raise MassiveArchiveError(str(exc)) from exc
            if self._locked_write_preflight is not None:
                self._locked_write_preflight()
            local_plan = tuple(expected_plan) if expected_plan is not None else None
            requested_datasets = {dataset.value for dataset in datasets}
            if local_plan is not None:
                if (
                    not local_plan
                    or len(local_plan) != len(requested_datasets)
                    or {item.session_date for item in local_plan}
                    != {session_date.isoformat()}
                    or {item.dataset for item in local_plan} != requested_datasets
                ):
                    raise MassiveArchiveError(
                        "expected local plan differs from the requested session"
                    )
                self._assert_expected_local_artifacts(local_plan)
                try:
                    self.campaign_guard.assert_projected_bytes(local_plan)
                except CampaignGuardError as exc:
                    raise MassiveArchiveError(str(exc)) from exc
                drill_headroom_bytes = 0
                if (
                    session_date in QUALIFICATION_SESSION_DATES
                    and requested_datasets == QUALIFICATION_TICK_DATASETS
                ):
                    drill_headroom_bytes = max(
                        item.content_length for item in local_plan
                    )
                assert_massive_local_capacity(
                    root=self.root,
                    artifacts=local_plan,
                    minimum_free_bytes=self.minimum_free_bytes,
                    per_session_abort_bytes=self.per_session_abort_bytes,
                    local_spool_ceiling_bytes=self.local_spool_ceiling_bytes,
                    drill_headroom_bytes=drill_headroom_bytes,
                    disk_usage=self._disk_usage,
                )

            plan = self.plan(session_date=session_date, datasets=datasets)
            if local_plan is not None and plan != local_plan:
                raise MassiveArchiveError(
                    "remote Massive metadata differs from the frozen local preflight plan"
                )
            if local_plan is None:
                try:
                    self.campaign_guard.assert_projected_bytes(plan)
                except CampaignGuardError as exc:
                    raise MassiveArchiveError(str(exc)) from exc
                drill_headroom_bytes = 0
                if (
                    session_date in QUALIFICATION_SESSION_DATES
                    and requested_datasets == QUALIFICATION_TICK_DATASETS
                ):
                    drill_headroom_bytes = max(item.content_length for item in plan)
                assert_massive_local_capacity(
                    root=self.root,
                    artifacts=plan,
                    minimum_free_bytes=self.minimum_free_bytes,
                    per_session_abort_bytes=self.per_session_abort_bytes,
                    local_spool_ceiling_bytes=self.local_spool_ceiling_bytes,
                    drill_headroom_bytes=drill_headroom_bytes,
                    disk_usage=self._disk_usage,
                )

            archived_items: list[ArchivedArtifact] = []
            for item in plan:
                archived_item = self._download_one(item, observed_at=observed_at)
                try:
                    self.campaign_guard.record_verified(
                        archived_item,
                        verified_at=observed_at,
                    )
                except CampaignGuardError as exc:
                    raise MassiveArchiveError(str(exc)) from exc
                archived_items.append(archived_item)
            archived = tuple(archived_items)
            manifest = {
                "schema_version": self.manifest_version,
                "provider": "Massive",
                "asset_class": "stocks",
                "source_kind": "SIP Flat Files",
                "session_date": session_date.isoformat(),
                "measured_at": observed_at.astimezone(timezone.utc).isoformat(),
                "artifacts": [asdict(item) for item in archived],
                "raw_files_are_unadjusted": True,
                "corporate_action_adjustment_required": True,
                "official_replay_ready": False,
                "campaign_verified_bytes": self.campaign_guard.verified_bytes(),
            }
            manifest_path = self._manifest_path(session_date, observed_at)
            self._atomic_json(manifest_path, manifest)
            return manifest_path

    def _assert_expected_local_artifacts(
        self,
        plan: Sequence[PlannedArtifact],
    ) -> None:
        """Recheck frozen local state under the archive lock before remote I/O."""
        for item in plan:
            try:
                dataset = FlatFileDataset(item.dataset)
                session_date = date.fromisoformat(item.session_date)
            except (ValueError, TypeError) as exc:
                raise MassiveArchiveError(
                    "expected local plan contains an invalid artifact identity"
                ) from exc
            target = Path(item.local_path)
            expected_target = self.local_path(dataset, session_date)
            if target != expected_target:
                raise MassiveArchiveError(
                    "expected local plan contains a non-canonical path: "
                    f"{target}"
                )
            metadata_path = self._artifact_metadata_path(target)
            target_present = target.exists() or target.is_symlink()
            metadata_present = metadata_path.exists() or metadata_path.is_symlink()
            if target_present != metadata_present:
                raise MassiveArchiveError(
                    "local artifact and immutable metadata must coexist: "
                    f"{target}"
                )

            source_sha256: str | None = None
            if target_present:
                if target.is_symlink() or not target.is_file():
                    raise MassiveArchiveError(
                        f"local artifact is not a regular non-symlink file: {target}"
                    )
                if metadata_path.is_symlink() or not metadata_path.is_file():
                    raise MassiveArchiveError(
                        "local artifact metadata is not a regular non-symlink file: "
                        f"{metadata_path}"
                    )
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise MassiveArchiveError(
                        f"local artifact metadata is unreadable: {metadata_path}"
                    ) from exc
                if not isinstance(metadata, dict):
                    raise MassiveArchiveError(
                        f"local artifact metadata is malformed: {metadata_path}"
                    )
                expected_metadata = {
                    "schema_version": self.manifest_version,
                    "bucket": item.bucket,
                    "object_key": item.object_key,
                    "content_length": item.content_length,
                    "remote_etag": item.remote_etag,
                }
                if any(
                    metadata.get(key) != value
                    for key, value in expected_metadata.items()
                ):
                    raise MassiveArchiveError(
                        "local artifact metadata differs from the frozen plan: "
                        f"{target}"
                    )
                if target.stat().st_size != item.content_length:
                    raise MassiveArchiveError(
                        f"local artifact size differs from the frozen plan: {target}"
                    )
                source_sha256 = self.sha256_file(target)
                if metadata.get("sha256") != source_sha256:
                    raise MassiveArchiveError(
                        f"local artifact checksum mismatch: {target}"
                    )

            try:
                self.campaign_guard.assert_existing_verified_event(
                    item,
                    source_sha256=source_sha256,
                )
            except CampaignGuardError as exc:
                raise MassiveArchiveError(str(exc)) from exc

    def _download_one(self, item: PlannedArtifact, *, observed_at: datetime) -> ArchivedArtifact:
        target = Path(item.local_path)
        metadata_path = self._artifact_metadata_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.stat().st_size != item.content_length:
                raise MassiveArchiveError(f"existing artifact size mismatch; refusing overwrite: {target}")
            if not metadata_path.exists():
                raise MassiveArchiveError(f"existing artifact has no immutable metadata: {target}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            expected = {
                "bucket": item.bucket,
                "object_key": item.object_key,
                "content_length": item.content_length,
                "remote_etag": item.remote_etag,
            }
            if any(metadata.get(key) != value for key, value in expected.items()):
                raise MassiveArchiveError(f"remote metadata changed; refusing overwrite: {target}")
            archived = self._archived(item, target, reused=True)
            if metadata.get("sha256") != archived.sha256:
                raise MassiveArchiveError(f"existing artifact checksum mismatch: {target}")
            return archived

        temporary = target.with_name(f".{target.name}.{uuid4().hex}.part")
        try:
            with temporary.open("xb") as handle:
                self.store.download_fileobj(item.bucket, item.object_key, handle)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary.stat().st_size != item.content_length:
                raise MassiveArchiveError(f"downloaded artifact size mismatch: {item.object_key}")
            try:
                post_download = self._remote_metadata(item)
            except Exception as exc:
                quarantine = self._quarantine_file(
                    temporary,
                    category="remote-rehead-failed",
                    observed_at=observed_at,
                )
                self._atomic_json(quarantine.with_name(f"{quarantine.name}.metadata.json"), {
                    "schema_version": self.manifest_version,
                    "reason": "remote_metadata_rehead_failed_after_download",
                    "planned": asdict(item),
                    "error_type": type(exc).__name__,
                    "quarantined_at": observed_at.astimezone(timezone.utc).isoformat(),
                })
                raise MassiveArchiveError(
                    f"remote metadata could not be rechecked; artifact quarantined: {item.object_key}"
                ) from None
            if (
                post_download["content_length"] != item.content_length
                or post_download["remote_etag"] != item.remote_etag
            ):
                quarantine = self._quarantine_file(
                    temporary,
                    category="remote-changed",
                    observed_at=observed_at,
                )
                self._atomic_json(quarantine.with_name(f"{quarantine.name}.metadata.json"), {
                    "schema_version": self.manifest_version,
                    "reason": "remote_metadata_changed_between_plan_and_download",
                    "planned": asdict(item),
                    "post_download": post_download,
                    "quarantined_at": observed_at.astimezone(timezone.utc).isoformat(),
                })
                raise MassiveArchiveError(
                    f"remote metadata changed during download; artifact quarantined: {item.object_key}"
                )
            try:
                os.link(temporary, target)
            except FileExistsError as exc:
                raise MassiveArchiveError(f"artifact appeared concurrently; refusing overwrite: {target}") from exc
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        archived = self._archived(item, target, reused=False)
        self._atomic_json(metadata_path, {
            "schema_version": self.manifest_version,
            "bucket": item.bucket,
            "object_key": item.object_key,
            "content_length": item.content_length,
            "remote_etag": item.remote_etag,
            "sha256": archived.sha256,
        })
        return archived

    def _remote_metadata(self, item: PlannedArtifact) -> dict[str, Any]:
        metadata = self.store.head_object(Bucket=item.bucket, Key=item.object_key)
        try:
            content_length = int(metadata["ContentLength"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MassiveArchiveError(
                f"Massive object has no valid size after download: {item.object_key}"
            ) from exc
        return {
            "content_length": content_length,
            "remote_etag": self._clean_etag(metadata.get("ETag")),
        }

    @contextmanager
    def _exclusive_download_lock(self):  # noqa: ANN202 - contextmanager iterator
        # The Day-D mount root is intentionally not writable by the host identity
        # used by supervised one-offs. Keep the global archive lock in the shared
        # evidence namespace, which is writable without broadening mount access.
        lock_path = self.root / "evidence" / ".massive-download.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise MassiveArchiveError("another Massive download is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _quarantine_orphan_parts(self, observed_at: datetime) -> None:
        quarantine_root = self.root / "provider=massive" / "quarantine"
        orphan_parts = self._orphan_parts(quarantine_root)
        for orphan in orphan_parts:
            if orphan.is_symlink() or not orphan.is_file():
                raise MassiveArchiveError(
                    "orphan path is not a regular non-symlink file; refusing remote HEAD: "
                    f"{orphan.relative_to(self.root)}"
                )
        observed = frozenset(
            str(path.relative_to(self.root)) for path in orphan_parts
        )
        if (
            self._expected_orphan_parts is not None
            and observed != self._expected_orphan_parts
        ):
            added = sorted(observed - self._expected_orphan_parts)
            missing = sorted(self._expected_orphan_parts - observed)
            raise MassiveArchiveError(
                "orphan manifest changed after the write preflight; refusing remote HEAD: "
                f"added={added}, missing={missing}"
            )
        for orphan in orphan_parts:
            quarantine = self._quarantine_file(
                orphan,
                category="orphan-part",
                observed_at=observed_at,
            )
            self._atomic_json(quarantine.with_name(f"{quarantine.name}.metadata.json"), {
                "schema_version": self.manifest_version,
                "reason": "orphan_partial_discovered_before_download",
                "original_path": str(orphan),
                "quarantined_at": observed_at.astimezone(timezone.utc).isoformat(),
            })
        remaining = self._orphan_parts(quarantine_root)
        if remaining:
            raise MassiveArchiveError(
                "orphan parts appeared while the archive lock was held; refusing remote HEAD: "
                + ", ".join(
                    sorted(str(path.relative_to(self.root)) for path in remaining)
                )
            )
        if self._expected_orphan_parts is not None:
            self._expected_orphan_parts = frozenset()

    def _orphan_parts(self, quarantine_root: Path) -> tuple[Path, ...]:
        return tuple(sorted(
            path
            for path in self.root.rglob("*.part")
            if quarantine_root not in path.parents
        ))

    def _quarantine_file(
        self,
        source: Path,
        *,
        category: str,
        observed_at: datetime,
    ) -> Path:
        suffix = observed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        source_name = source.name.removeprefix(".")
        if source_name.endswith(".part"):
            source_name = f"{source_name.removesuffix('.part')}.quarantined"
        destination = (
            self.root
            / "provider=massive"
            / "quarantine"
            / f"category={category}"
            / f"{suffix}-{uuid4().hex}-{source_name}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, destination, follow_symlinks=False)
        source.unlink()
        return destination

    @staticmethod
    def _archived(item: PlannedArtifact, target: Path, *, reused: bool) -> ArchivedArtifact:
        return ArchivedArtifact(
            dataset=item.dataset,
            session_date=item.session_date,
            bucket=item.bucket,
            object_key=item.object_key,
            content_length=item.content_length,
            remote_etag=item.remote_etag,
            local_path=str(target),
            sha256=MassiveFlatFileArchive.sha256_file(target),
            reused_existing_file=reused,
        )

    @staticmethod
    def object_key(dataset: FlatFileDataset, session_date: date) -> str:
        return (
            f"us_stocks_sip/{dataset.provider_path}/{session_date:%Y/%m}/"
            f"{session_date.isoformat()}.csv.gz"
        )

    def local_path(self, dataset: FlatFileDataset, session_date: date) -> Path:
        return (
            self.root
            / "provider=massive"
            / f"dataset={dataset.value}"
            / f"session_date={session_date.isoformat()}"
            / "source.csv.gz"
        )

    def _manifest_path(self, session_date: date, measured_at: datetime) -> Path:
        suffix = measured_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        return (
            self.root
            / "provider=massive"
            / "manifests"
            / f"session_date={session_date.isoformat()}"
            / f"manifest-{suffix}.json"
        )

    @staticmethod
    def _artifact_metadata_path(target: Path) -> Path:
        return target.with_name(f"{target.name}.metadata.json")

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _clean_etag(value: Any) -> str | None:
        cleaned = str(value or "").strip().strip('"')
        return cleaned or None

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
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise MassiveArchiveError(f"immutable JSON artifact already exists: {path}") from exc
            temporary.unlink()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _build_store(access_key: str, secret_key: str, endpoint: str) -> ObjectStore:
    if not access_key or not secret_key:
        raise MassiveArchiveError("Massive Flat Files credentials are not configured")
    import boto3
    from botocore.config import Config

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    return session.client(
        "s3",
        endpoint_url=endpoint,
        config=Config(signature_version="s3v4"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Plan or download immutable Massive stock Flat Files")
    parser.add_argument("--session-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--dataset",
        action="append",
        choices=[dataset.value for dataset in FlatFileDataset],
        required=True,
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="execute the download; without this flag the command is read-only plan mode",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    archive = MassiveFlatFileArchive(
        _build_store(
            settings.massive_flat_files_access_key,
            settings.massive_flat_files_secret_key,
            settings.massive_flat_files_endpoint,
        ),
        root=settings.day_d_dataset_root,
        bucket=settings.massive_flat_files_bucket,
        minimum_free_bytes=int(settings.day_d_dataset_min_free_disk_gb * 1024**3),
        campaign_guard=MassiveCampaignGuard(
            root=settings.day_d_dataset_root,
            download_authorized=settings.day_d_historical_download_authorized,
        ),
    )
    datasets = tuple(FlatFileDataset(value) for value in args.dataset)
    if args.download:
        manifest_path = archive.download(session_date=args.session_date, datasets=datasets)
        print(json.dumps({"downloaded": True, "manifest": str(manifest_path)}, sort_keys=True))
    else:
        plan = archive.plan(session_date=args.session_date, datasets=datasets)
        print(json.dumps({
            "downloaded": False,
            "artifacts": [asdict(item) for item in plan],
            "total_bytes": sum(item.content_length for item in plan),
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
