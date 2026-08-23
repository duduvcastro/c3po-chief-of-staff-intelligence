from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.day_d_replay.b2_offload import B2OffloadError, DayDB2Offload


class MissingObject(Exception):
    response = {"Error": {"Code": "404"}}


class FakeB2:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.uploads: list[str] = []
        self.downloads: list[str] = []

    def head_object(self, *, Bucket: str, Key: str):  # noqa: ANN201
        assert Bucket == "day-d"
        if Key not in self.objects:
            raise MissingObject
        return {
            "ContentLength": len(self.objects[Key]),
            "Metadata": self.metadata[Key],
            "VersionId": f"version-{len(self.uploads)}",
        }

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs=None,  # noqa: ANN001
    ) -> None:
        assert Bucket == "day-d"
        self.uploads.append(Key)
        self.objects[Key] = Path(Filename).read_bytes()
        self.metadata[Key] = dict((ExtraArgs or {}).get("Metadata") or {})

    def download_fileobj(self, Bucket: str, Key: str, Fileobj) -> None:  # noqa: ANN001
        assert Bucket == "day-d"
        self.downloads.append(Key)
        Fileobj.write(self.objects[Key])


def _manifest(root: Path, payload: bytes = b"massive-data") -> Path:
    source = (
        root
        / "provider=massive"
        / "dataset=trades"
        / "session_date=2026-08-21"
        / "source.csv.gz"
    )
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    manifest = (
        root
        / "provider=massive"
        / "manifests"
        / "session_date=2026-08-21"
        / "manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "schema_version": "DAY-D-MASSIVE-ARCHIVE-v1",
        "session_date": "2026-08-21",
        "official_replay_ready": False,
        "artifacts": [{
            "dataset": "trades",
            "session_date": "2026-08-21",
            "bucket": "flatfiles",
            "object_key": "us_stocks_sip/trades_v1/2026/08/2026-08-21.csv.gz",
            "content_length": len(payload),
            "remote_etag": "source-etag",
            "local_path": str(source),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "reused_existing_file": False,
        }],
    }), encoding="utf-8")
    return manifest


def test_plan_is_read_only_and_validates_local_artifact(tmp_path: Path) -> None:
    store = FakeB2()
    offload = DayDB2Offload(store, root=tmp_path, bucket="day-d")

    plan = offload.plan([_manifest(tmp_path)])

    assert len(plan) == 1
    assert plan[0]["content_length"] == len(b"massive-data")
    assert plan[0]["remote_key"].endswith(
        "dataset=trades/session_date=2026-08-21/source.csv.gz"
    )
    assert store.uploads == []


def test_offload_uploads_raw_and_report_then_verifies_remote_metadata(
    tmp_path: Path,
) -> None:
    store = FakeB2()
    manifest = _manifest(tmp_path)
    source = Path(json.loads(manifest.read_text())["artifacts"][0]["local_path"])
    offload = DayDB2Offload(store, root=tmp_path, bucket="day-d")

    report_path = offload.offload(
        [manifest],
        lot_id="qualification-001",
        measured_at=datetime(2026, 8, 23, 5, tzinfo=timezone.utc),
    )

    report = json.loads(report_path.read_text())
    assert report["verified_object_count"] == 2
    assert report["raw_verified_bytes"] == len(b"massive-data")
    assert report["verified_bytes"] > report["raw_verified_bytes"]
    assert report["local_source_deletion_authorized"] is False
    assert report["objects"][0]["version_id"]
    assert source.read_bytes() == b"massive-data"
    assert len(store.uploads) == 3
    assert report_path.with_name(f"{report_path.name}.remote.json").exists()
    raw_key = report["objects"][0]["key"]
    assert store.metadata[raw_key]["sha256"] == hashlib.sha256(b"massive-data").hexdigest()


def test_offload_reuses_matching_object_and_rejects_conflicting_remote(
    tmp_path: Path,
) -> None:
    store = FakeB2()
    manifest = _manifest(tmp_path)
    offload = DayDB2Offload(store, root=tmp_path, bucket="day-d")
    first = offload.offload([manifest], lot_id="first")
    first_report = json.loads(first.read_text())
    raw_key = first_report["objects"][0]["key"]

    second = offload.offload([manifest], lot_id="second")
    second_report = json.loads(second.read_text())
    assert second_report["objects"][0]["reused_existing_object"] is True

    store.metadata[raw_key]["sha256"] = "0" * 64
    with pytest.raises(B2OffloadError, match="conflicts with immutable source"):
        offload.offload([manifest], lot_id="third")


def test_restore_drill_redownloads_report_and_writes_pass_evidence(
    tmp_path: Path,
) -> None:
    store = FakeB2()
    offload = DayDB2Offload(store, root=tmp_path, bucket="day-d")
    report = offload.offload(
        [_manifest(tmp_path)],
        lot_id="qualification-001",
        measured_at=datetime(2026, 8, 23, 5, tzinfo=timezone.utc),
    )

    restore_report = offload.restore_report_sample(
        report,
        measured_at=datetime(2026, 8, 23, 6, tzinfo=timezone.utc),
    )

    evidence = json.loads(restore_report.read_text())
    assert evidence["passed"] is True
    assert evidence["expected_sha256"] == evidence["observed_sha256"]
    assert evidence["expected_bytes"] == evidence["observed_bytes"]
    assert evidence["local_source_deletion_authorized"] is False
    assert len(store.downloads) == 1


def test_offload_refuses_sources_outside_day_d_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.csv.gz"
    outside.write_bytes(b"data")
    manifest = _manifest(root)
    payload = json.loads(manifest.read_text())
    payload["artifacts"][0]["local_path"] = str(outside)
    payload["artifacts"][0]["content_length"] = 4
    payload["artifacts"][0]["sha256"] = hashlib.sha256(b"data").hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(B2OffloadError, match="outside the Day D data root"):
        DayDB2Offload(FakeB2(), root=root, bucket="day-d").plan([manifest])
