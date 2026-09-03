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
    MassiveFlatFileArchive,
    _build_store,
)
from .massive_campaign import (
    EXTENSION_MINUTE_SESSIONS,
    EXTENSION_SCOPE_BYTES,
    EXTENSION_SCOPE_REPORT_SHA256,
    MassiveCampaignGuard,
)


class MassiveExtensionDownloadError(RuntimeError):
    pass


EXTENSION_SESSIONS = tuple(sorted(EXTENSION_MINUTE_SESSIONS))


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
    args = parser.parse_args(argv)
    settings = get_settings()
    root = settings.day_d_dataset_root.resolve()
    output = args.output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise MassiveExtensionDownloadError("output escaped the Day-D root") from exc

    archive = MassiveFlatFileArchive(
        _build_store(
            settings.massive_flat_files_access_key,
            settings.massive_flat_files_secret_key,
            settings.massive_flat_files_endpoint,
        ),
        root=root,
        bucket=settings.massive_flat_files_bucket,
        minimum_free_bytes=int(settings.day_d_dataset_min_free_disk_gb * 1024**3),
        campaign_guard=MassiveCampaignGuard(
            root=root,
            download_authorized=settings.day_d_historical_download_authorized,
        ),
    )
    session_manifests = [
        archive.download(
            session_date=session_date,
            datasets=(FlatFileDataset.MINUTE_AGGREGATES,),
        )
        for session_date in EXTENSION_SESSIONS
    ]
    generated_at = datetime.now(timezone.utc)
    manifest = build_extension_manifest(
        root=root,
        session_manifests=session_manifests,
        generated_at=generated_at,
        head_revision=args.head_revision,
        workflow_run_id=args.workflow_run_id,
        workflow_run_attempt=args.workflow_run_attempt,
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
