from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.day_d_replay.massive_campaign import EXTENSION_SCOPE_REPORT_SHA256
from app.day_d_replay.massive_extension_download import (
    EXTENSION_SESSIONS,
    MassiveExtensionDownloadError,
    build_extension_manifest,
)


def _session_manifests(root: Path) -> list[Path]:
    manifests: list[Path] = []
    for index, session_date in enumerate(EXTENSION_SESSIONS):
        payload = bytes([index + 1])
        source_path = (
            root
            / "provider=massive"
            / "dataset=minute_aggregates"
            / f"session_date={session_date.isoformat()}"
            / "source.csv.gz"
        )
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(payload)
        manifest_path = root / "manifests" / f"{session_date.isoformat()}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "schema_version": "DAY-D-MASSIVE-ARCHIVE-v1",
            "session_date": session_date.isoformat(),
            "artifacts": [{
                "dataset": "minute_aggregates",
                "session_date": session_date.isoformat(),
                "bucket": "flatfiles",
                "object_key": (
                    "us_stocks_sip/minute_aggs_v1/"
                    f"{session_date:%Y/%m}/{session_date.isoformat()}.csv.gz"
                ),
                "content_length": len(payload),
                "remote_etag": f"etag-{index}",
                "local_path": str(source_path),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "reused_existing_file": False,
            }],
        }), encoding="utf-8")
        manifests.append(manifest_path)
    return manifests


def test_extension_manifest_rehashes_all_eight_sources_and_self_hashes(tmp_path: Path) -> None:
    generated_at = datetime(2026, 9, 3, 6, tzinfo=timezone.utc)
    manifest = build_extension_manifest(
        root=tmp_path,
        session_manifests=_session_manifests(tmp_path),
        generated_at=generated_at,
        head_revision="a" * 40,
        workflow_run_id=123,
        workflow_run_attempt=1,
        expected_total_bytes=8,
    )

    assert manifest["session_count"] == 8
    assert manifest["downloaded_bytes"] == 8
    assert manifest["raw_files_returned_to_ci"] is False
    assert manifest["plan_report_sha256"] == EXTENSION_SCOPE_REPORT_SHA256
    assert manifest["evidence_expires_at"] == "2026-10-03T06:00:00+00:00"
    expected_self_hash = manifest.pop("manifest_sha256")
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == expected_self_hash


def test_extension_manifest_rejects_source_tampering(tmp_path: Path) -> None:
    manifests = _session_manifests(tmp_path)
    first = json.loads(manifests[0].read_text(encoding="utf-8"))
    Path(first["artifacts"][0]["local_path"]).write_bytes(b"changed")

    with pytest.raises(MassiveExtensionDownloadError, match="artifact is invalid"):
        build_extension_manifest(
            root=tmp_path,
            session_manifests=manifests,
            generated_at=datetime.now(timezone.utc),
            head_revision="a" * 40,
            workflow_run_id=123,
            workflow_run_attempt=1,
            expected_total_bytes=8,
        )
