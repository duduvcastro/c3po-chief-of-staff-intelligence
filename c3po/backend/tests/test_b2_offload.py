from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.day_d_replay.b2_offload import B2OffloadError, DayDB2Offload


class MissingObject(Exception):
    response = {"Error": {"Code": "404"}}


class FakeB2:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.versions: dict[str, str] = {}
        self.uploads: list[str] = []
        self.downloads: list[str] = []

    def head_object(self, *, Bucket: str, Key: str):  # noqa: ANN201
        assert Bucket == "day-d"
        if Key not in self.objects:
            raise MissingObject
        return {
            "ContentLength": len(self.objects[Key]),
            "Metadata": self.metadata[Key],
            "VersionId": self.versions[Key],
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
        self.versions[Key] = f"version-{len(self.uploads)}"

    def download_fileobj(
        self,
        Bucket: str,
        Key: str,
        Fileobj,  # noqa: ANN001
        ExtraArgs=None,  # noqa: ANN001
    ) -> None:
        assert Bucket == "day-d"
        if ExtraArgs:
            assert ExtraArgs == {"VersionId": self.versions[Key]}
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


def _qualification_manifest(root: Path) -> Path:
    manifest = _manifest(root, payload=b"trade-data")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    quote_source = (
        root
        / "provider=massive"
        / "dataset=quotes"
        / "session_date=2026-08-21"
        / "source.csv.gz"
    )
    quote_source.parent.mkdir(parents=True)
    quote_source.write_bytes(b"quote-data-is-larger")
    payload["artifacts"].append({
        "dataset": "quotes",
        "session_date": "2026-08-21",
        "bucket": "flatfiles",
        "object_key": "us_stocks_sip/quotes_v1/2026/08/2026-08-21.csv.gz",
        "content_length": quote_source.stat().st_size,
        "remote_etag": "quote-etag",
        "local_path": str(quote_source),
        "sha256": hashlib.sha256(quote_source.read_bytes()).hexdigest(),
        "reused_existing_file": False,
    })
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return manifest


def _qualified_offload(
    tmp_path: Path,
) -> tuple[FakeB2, DayDB2Offload, Path, list[Path]]:
    store = FakeB2()
    manifest = _qualification_manifest(tmp_path)
    offload = DayDB2Offload(
        store,
        root=tmp_path,
        bucket="day-d",
        minimum_free_bytes=0,
        disk_usage=lambda _path: SimpleNamespace(free=10_000),
    )
    report = offload.offload(
        [manifest],
        lot_id="qualification-001",
        measured_at=datetime(2026, 8, 23, 5, tzinfo=timezone.utc),
    )
    sources = [
        Path(item["source_path"])
        for item in json.loads(report.read_text(encoding="utf-8"))["objects"]
    ]
    return store, offload, report, sources


def _passed_deletion_evidence(
    offload: DayDB2Offload,
    report: Path,
) -> tuple[Path, Path]:
    raw_restore = offload.restore_raw_object(
        report,
        measured_at=datetime(2026, 8, 23, 6, tzinfo=timezone.utc),
    )
    cap = offload.record_billing_cap_cycle(
        raw_restore,
        elevated_at=datetime(2026, 8, 23, 5, 59, tzinfo=timezone.utc),
        restored_at=datetime(2026, 8, 23, 6, 1, tzinfo=timezone.utc),
        temporary_cap_usd_per_day=0.5,
        operator="Dudu",
        measured_at=datetime(2026, 8, 23, 6, 2, tzinfo=timezone.utc),
    )
    return raw_restore, cap


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


def test_raw_drill_selects_largest_object_and_cleans_restored_copy(
    tmp_path: Path,
) -> None:
    _store, offload, report, _sources = _qualified_offload(tmp_path)

    plan = offload.plan_raw_restore(report)
    evidence_path = offload.restore_raw_object(
        report,
        measured_at=datetime(2026, 8, 23, 6, tzinfo=timezone.utc),
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert plan["execute"] is False
    assert plan["selected_object"]["dataset"] == "quotes"
    assert evidence["passed"] is True
    assert evidence["restored_sample_removed"] is True
    assert not Path(evidence["restored_sample_path"]).exists()


def test_delete_lot_is_plan_first_and_preserves_nonlisted_files(
    tmp_path: Path,
) -> None:
    _store, offload, report, sources = _qualified_offload(tmp_path)
    raw_restore, cap = _passed_deletion_evidence(offload, report)
    unrelated = tmp_path / "provider=massive" / "dataset=minute_aggregates" / "keep.csv.gz"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"never-delete")

    plan = offload.plan_delete_lot(
        report,
        raw_restore_report_path=raw_restore,
        billing_cap_evidence_path=cap,
    )
    assert plan["execute"] is False
    assert plan["status"] == "ready"
    assert all(source.exists() for source in sources)

    record_path = offload.delete_lot(
        report,
        raw_restore_report_path=raw_restore,
        billing_cap_evidence_path=cap,
        measured_at=datetime(2026, 8, 23, 6, 3, tzinfo=timezone.utc),
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "completed"
    assert record["minute_aggregates_deleted"] is False
    assert all(not source.exists() for source in sources)
    assert unrelated.read_bytes() == b"never-delete"
    assert len(record["lot_report"]["sha256"]) == 64
    assert len(record["raw_restore_report"]["sha256"]) == 64


def test_delete_lot_rejects_requested_path_outside_immutable_report(
    tmp_path: Path,
) -> None:
    _store, offload, report, sources = _qualified_offload(tmp_path)
    raw_restore, cap = _passed_deletion_evidence(offload, report)
    outside = tmp_path / "provider=massive" / "outside.csv.gz"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"outside")

    with pytest.raises(B2OffloadError, match="exactly match immutable lot report"):
        offload.plan_delete_lot(
            report,
            raw_restore_report_path=raw_restore,
            billing_cap_evidence_path=cap,
            requested_paths=(*sources, outside),
        )

    assert all(source.exists() for source in sources)
    assert outside.exists()


def test_execute_with_path_outside_report_quarantines_without_deleting(
    tmp_path: Path,
) -> None:
    _store, offload, report, sources = _qualified_offload(tmp_path)
    raw_restore, cap = _passed_deletion_evidence(offload, report)
    outside = tmp_path / "provider=massive" / "outside.csv.gz"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"outside")

    with pytest.raises(B2OffloadError, match="preflight failed.*quarantined"):
        offload.delete_lot(
            report,
            raw_restore_report_path=raw_restore,
            billing_cap_evidence_path=cap,
            requested_paths=(*sources, outside),
            measured_at=datetime(2026, 8, 23, 6, 3, tzinfo=timezone.utc),
        )

    assert all(source.exists() for source in sources)
    assert outside.exists()
    failures = list(tmp_path.glob("provider=backblaze/deletion-records/**/*.json"))
    quarantine = list(tmp_path.glob("provider=backblaze/quarantine/**/*.json"))
    assert any(
        json.loads(path.read_text())["status"] == "preflight_failed_quarantined"
        for path in failures
    )
    assert len(quarantine) == 1


def test_parent_manifest_chain_is_reverified_before_raw_drill(tmp_path: Path) -> None:
    store, offload, report, sources = _qualified_offload(tmp_path)
    lot = json.loads(report.read_text(encoding="utf-8"))
    parent = Path(lot["parent_manifests"][0]["source_path"])
    parent.write_text("{}\n", encoding="utf-8")

    with pytest.raises(B2OffloadError, match="parent manifest|byte count|checksum"):
        offload.plan_raw_restore(report)

    assert store.downloads == []
    assert all(source.exists() for source in sources)


def test_delete_lot_blocks_version_mismatch_and_quarantines_without_deleting(
    tmp_path: Path,
) -> None:
    store, offload, report, sources = _qualified_offload(tmp_path)
    raw_restore, cap = _passed_deletion_evidence(offload, report)
    lot = json.loads(report.read_text(encoding="utf-8"))
    for item in lot["objects"]:
        store.versions[item["key"]] = "unexpected-version"

    with pytest.raises(B2OffloadError, match="quarantined"):
        offload.delete_lot(
            report,
            raw_restore_report_path=raw_restore,
            billing_cap_evidence_path=cap,
            measured_at=datetime(2026, 8, 23, 6, 3, tzinfo=timezone.utc),
        )

    assert all(source.exists() for source in sources)
    quarantine = list(tmp_path.glob("provider=backblaze/quarantine/**/*.json"))
    assert len(quarantine) == 1
    assert json.loads(quarantine[0].read_text())["automatic_retry_allowed"] is False


def test_failed_raw_drill_persists_evidence_and_quarantines_lot(
    tmp_path: Path,
) -> None:
    store, offload, report, sources = _qualified_offload(tmp_path)
    lot = json.loads(report.read_text(encoding="utf-8"))
    largest = max(lot["objects"], key=lambda item: item["content_length"])
    store.objects[largest["key"]] = b"corrupt"

    with pytest.raises(B2OffloadError, match="lot was quarantined"):
        offload.restore_raw_object(
            report,
            measured_at=datetime(2026, 8, 23, 6, tzinfo=timezone.utc),
        )

    failures = list(tmp_path.glob("provider=backblaze/raw-restore-reports/**/*.json"))
    quarantine = list(tmp_path.glob("provider=backblaze/quarantine/**/*.json"))
    assert len(failures) == 1
    assert json.loads(failures[0].read_text())["passed"] is False
    assert len(quarantine) == 1
    assert all(source.exists() for source in sources)
    with pytest.raises(B2OffloadError, match="six-hands review"):
        offload.plan_raw_restore(report)


def test_delete_lot_is_idempotent_and_records_no_op(
    tmp_path: Path,
) -> None:
    _store, offload, report, _sources = _qualified_offload(tmp_path)
    raw_restore, cap = _passed_deletion_evidence(offload, report)
    first = offload.delete_lot(
        report,
        raw_restore_report_path=raw_restore,
        billing_cap_evidence_path=cap,
        measured_at=datetime(2026, 8, 23, 6, 3, tzinfo=timezone.utc),
    )

    second = offload.delete_lot(
        report,
        raw_restore_report_path=raw_restore,
        billing_cap_evidence_path=cap,
        measured_at=datetime(2026, 8, 23, 6, 4, tzinfo=timezone.utc),
    )

    assert json.loads(first.read_text())["status"] == "completed"
    second_record = json.loads(second.read_text())
    assert second_record["status"] == "no_op_already_deleted"
    assert second_record["prior_successful_deletion"] is not None


def test_minute_aggregates_and_unfrozen_sessions_never_gain_delete_authority(
    tmp_path: Path,
) -> None:
    store = FakeB2()
    manifest = _manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["artifacts"][0]["dataset"] = "minute_aggregates"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    offload = DayDB2Offload(store, root=tmp_path, bucket="day-d")
    report = offload.offload([manifest], lot_id="bars")

    with pytest.raises(B2OffloadError, match="outside frozen qualification scope"):
        offload.plan_raw_restore(report)
