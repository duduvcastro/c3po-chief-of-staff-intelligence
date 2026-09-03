from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence

from .massive_archive import (
    FlatFileDataset,
    MassiveArchiveError,
    MassiveFlatFileArchive,
    PlannedArtifact,
    _build_store,
    assert_massive_local_capacity,
)
from .massive_campaign import (
    CampaignGuardError,
    EXTENSION_MINUTE_SESSIONS,
    EXTENSION_SCOPE_BYTES,
    EXTENSION_SCOPE_REPORT_SHA256,
    MassiveCampaignGuard,
)
from .massive_extension_write_preflight import (
    STATIC_CROSS_DIRECTORY_PAIR_COUNT,
    STATIC_WRITE_TARGET_COUNT,
    run_write_preflight,
)


class MassiveExtensionDownloadError(RuntimeError):
    pass


EXTENSION_SESSIONS = tuple(sorted(EXTENSION_MINUTE_SESSIONS))


def _frozen_local_plan(
    *,
    root: Path,
    write_preflight: dict[str, Any],
) -> tuple[PlannedArtifact, ...]:
    rows = write_preflight.get("frozen_artifacts")
    if not isinstance(rows, list) or len(rows) != len(EXTENSION_SESSIONS):
        raise MassiveExtensionDownloadError(
            "write preflight has no complete frozen artifact plan"
        )
    artifacts: list[PlannedArtifact] = []
    for expected_session, row in zip(EXTENSION_SESSIONS, rows, strict=True):
        if not isinstance(row, dict):
            raise MassiveExtensionDownloadError(
                "write preflight frozen artifact is malformed"
            )
        relative = Path(str(row.get("local_path_relative") or ""))
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise MassiveExtensionDownloadError(
                "write preflight frozen artifact path is unsafe"
            )
        local_path = (root / relative).resolve()
        try:
            local_path.relative_to(root.resolve())
        except ValueError as exc:
            raise MassiveExtensionDownloadError(
                "write preflight frozen artifact escaped the Day-D root"
            ) from exc
        expected_key = (
            "us_stocks_sip/minute_aggs_v1/"
            f"{expected_session:%Y/%m}/{expected_session.isoformat()}.csv.gz"
        )
        artifact = PlannedArtifact(
            dataset=str(row.get("dataset") or ""),
            session_date=str(row.get("session_date") or ""),
            bucket=str(row.get("bucket") or ""),
            object_key=str(row.get("object_key") or ""),
            content_length=int(row.get("content_length") or 0),
            remote_etag=str(row.get("remote_etag") or ""),
            local_path=str(local_path),
        )
        if (
            artifact.dataset != "minute_aggregates"
            or artifact.session_date != expected_session.isoformat()
            or artifact.bucket != "flatfiles"
            or artifact.object_key != expected_key
            or artifact.content_length <= 0
            or not artifact.remote_etag
        ):
            raise MassiveExtensionDownloadError(
                "write preflight frozen artifact differs from the authorized plan"
            )
        artifacts.append(artifact)
    if sum(item.content_length for item in artifacts) != EXTENSION_SCOPE_BYTES:
        raise MassiveExtensionDownloadError(
            "write preflight frozen artifact bytes differ from the authorization"
        )
    return tuple(artifacts)


def _assert_local_download_ready(
    *,
    root: Path,
    campaign_guard: MassiveCampaignGuard,
    artifacts: Sequence[PlannedArtifact],
    minimum_free_bytes: int,
) -> None:
    try:
        campaign_guard.assert_download_authorized()
        campaign_guard.assert_projected_bytes(artifacts)
        assert_massive_local_capacity(
            root=root,
            artifacts=artifacts,
            minimum_free_bytes=minimum_free_bytes,
        )
    except (CampaignGuardError, MassiveArchiveError, OSError) as exc:
        raise MassiveExtensionDownloadError(
            f"local Massive preflight failed before remote access: {exc}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_extension_manifest(
    *,
    root: Path,
    session_manifests: Sequence[Path],
    generated_at: datetime,
    head_revision: str,
    workflow_run_id: int,
    workflow_run_attempt: int,
    expected_total_bytes: int = EXTENSION_SCOPE_BYTES,
    write_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    if len(session_manifests) != len(EXTENSION_SESSIONS):
        raise MassiveExtensionDownloadError("extension requires exactly eight session manifests")

    resolved_root = root.resolve()
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for expected_session, manifest_path in zip(
        EXTENSION_SESSIONS,
        session_manifests,
        strict=True,
    ):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = payload.get("artifacts")
        if (
            payload.get("schema_version") != "DAY-D-MASSIVE-ARCHIVE-v1"
            or payload.get("session_date") != expected_session.isoformat()
            or not isinstance(artifacts, list)
            or len(artifacts) != 1
        ):
            raise MassiveExtensionDownloadError("session manifest coverage is invalid")
        artifact = artifacts[0]
        expected_key = (
            "us_stocks_sip/minute_aggs_v1/"
            f"{expected_session:%Y/%m}/{expected_session.isoformat()}.csv.gz"
        )
        source_path = Path(str(artifact.get("local_path") or "")).resolve()
        try:
            source_path.relative_to(resolved_root)
        except ValueError as exc:
            raise MassiveExtensionDownloadError("source file escaped the Day-D root") from exc
        content_length = int(artifact.get("content_length") or 0)
        source_sha256 = str(artifact.get("sha256") or "")
        if (
            artifact.get("dataset") != "minute_aggregates"
            or artifact.get("session_date") != expected_session.isoformat()
            or artifact.get("bucket") != "flatfiles"
            or artifact.get("object_key") != expected_key
            or content_length <= 0
            or not artifact.get("remote_etag")
            or len(source_sha256) != 64
            or not source_path.is_file()
            or source_path.stat().st_size != content_length
            or _sha256_file(source_path) != source_sha256
        ):
            raise MassiveExtensionDownloadError("downloaded extension artifact is invalid")
        total_bytes += content_length
        rows.append({
            "session_date": expected_session.isoformat(),
            "session_manifest_path": str(manifest_path),
            "session_manifest_sha256": _sha256_file(manifest_path),
            "object_key": expected_key,
            "content_length": content_length,
            "remote_etag": artifact["remote_etag"],
            "source_sha256": source_sha256,
            "reused_existing_file": bool(artifact.get("reused_existing_file")),
        })
    if total_bytes != expected_total_bytes:
        raise MassiveExtensionDownloadError(
            "downloaded extension byte total differs from the frozen plan"
        )

    generated_utc = generated_at.astimezone(timezone.utc)
    if write_preflight is not None:
        checked_directories = write_preflight.get("checked_directories")
        checked_targets = write_preflight.get("checked_targets")
        frozen_artifacts = write_preflight.get("frozen_artifacts")
        existing_orphans = write_preflight.get("existing_orphan_parts")
        cross_directory_checked = write_preflight.get("cross_directory_checked")
        if (
            write_preflight.get("status") != "ok"
            or write_preflight.get("frozen_plan_sha256")
            != EXTENSION_SCOPE_REPORT_SHA256
            or not isinstance(checked_directories, list)
            or write_preflight.get("checked_directory_count")
            != len(checked_directories)
            or len(checked_directories) < 22
            or not isinstance(checked_targets, list)
            or not isinstance(frozen_artifacts, list)
            or len(frozen_artifacts) != len(EXTENSION_SESSIONS)
            or not isinstance(existing_orphans, list)
            or not isinstance(cross_directory_checked, list)
            or write_preflight.get("checked_target_count") != len(checked_targets)
            or len(checked_targets)
            != STATIC_WRITE_TARGET_COUNT + len(existing_orphans)
            or write_preflight.get("cross_directory_probe_count")
            != len(cross_directory_checked)
            or len(cross_directory_checked)
            != STATIC_CROSS_DIRECTORY_PAIR_COUNT + len(existing_orphans)
            or write_preflight.get("network_calls_before_preflight") != 0
            or write_preflight.get("locked_preflight_recheck_count")
            != len(EXTENSION_SESSIONS)
        ):
            raise MassiveExtensionDownloadError("write preflight evidence is invalid")
    manifest: dict[str, Any] = {
        "schema_version": "DAY-D-MASSIVE-MINUTE-EXTENSION-DOWNLOAD-v1",
        "generated_at": generated_utc.isoformat(),
        "evidence_expires_at": (generated_utc + timedelta(days=30)).isoformat(),
        "head_revision": head_revision,
        "workflow_run_id": workflow_run_id,
        "workflow_run_attempt": workflow_run_attempt,
        "plan_report_sha256": EXTENSION_SCOPE_REPORT_SHA256,
        "dataset": "minute_aggregates",
        "sessions": rows,
        "session_count": len(rows),
        "downloaded_bytes": total_bytes,
        "raw_files_returned_to_ci": False,
        "raw_retention": "indefinite_no_local_deletion_authorized",
        "evidence_retention_days": 30,
        "official_replay_ready": False,
    }
    if write_preflight is not None:
        manifest["write_preflight"] = write_preflight
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    return manifest


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    from app.config import get_settings

    parser = argparse.ArgumentParser(
        description="Download the exact frozen Massive minute extension"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--head-revision", required=True)
    parser.add_argument("--workflow-run-id", type=int, required=True)
    parser.add_argument("--workflow-run-attempt", type=int, required=True)
    parser.add_argument("--expected-uid", type=int, required=True)
    parser.add_argument("--expected-gid", type=int, required=True)
    args = parser.parse_args(argv)
    settings = get_settings()
    root = settings.day_d_dataset_root.resolve()
    output = args.output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise MassiveExtensionDownloadError("output escaped the Day-D root") from exc

    preflight = run_write_preflight(
        root=root,
        output=output,
        expected_uid=args.expected_uid,
        expected_gid=args.expected_gid,
    )
    print(json.dumps({"write_preflight": preflight}, sort_keys=True), flush=True)

    minimum_free_bytes = int(settings.day_d_dataset_min_free_disk_gb * 1024**3)
    frozen_plan = _frozen_local_plan(root=root, write_preflight=preflight)
    campaign_guard = MassiveCampaignGuard(
        root=root,
        download_authorized=settings.day_d_historical_download_authorized,
    )
    _assert_local_download_ready(
        root=root,
        campaign_guard=campaign_guard,
        artifacts=frozen_plan,
        minimum_free_bytes=minimum_free_bytes,
    )
    locked_preflight_recheck_count = 0

    def locked_write_preflight() -> None:
        nonlocal locked_preflight_recheck_count
        run_write_preflight(
            root=root,
            output=output,
            expected_uid=args.expected_uid,
            expected_gid=args.expected_gid,
            archive_lock_held=True,
        )
        locked_preflight_recheck_count += 1

    archive = MassiveFlatFileArchive(
        _build_store(
            settings.massive_flat_files_access_key,
            settings.massive_flat_files_secret_key,
            settings.massive_flat_files_endpoint,
        ),
        root=root,
        bucket=settings.massive_flat_files_bucket,
        minimum_free_bytes=minimum_free_bytes,
        campaign_guard=campaign_guard,
        expected_orphan_parts=frozenset(preflight["existing_orphan_parts"]),
        locked_write_preflight=locked_write_preflight,
    )
    frozen_by_session = {
        item.session_date: item for item in frozen_plan
    }
    session_manifests = [
        archive.download(
            session_date=session_date,
            datasets=(FlatFileDataset.MINUTE_AGGREGATES,),
            expected_plan=(frozen_by_session[session_date.isoformat()],),
        )
        for session_date in EXTENSION_SESSIONS
    ]
    preflight["locked_preflight_recheck_count"] = locked_preflight_recheck_count
    generated_at = datetime.now(timezone.utc)
    manifest = build_extension_manifest(
        root=root,
        session_manifests=session_manifests,
        generated_at=generated_at,
        head_revision=args.head_revision,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
        write_preflight=preflight,
    )
    _atomic_json(output, manifest)
    print(json.dumps({
        "downloaded": True,
        "manifest": str(output),
        "manifest_sha256": manifest["manifest_sha256"],
        "session_count": manifest["session_count"],
        "downloaded_bytes": manifest["downloaded_bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
