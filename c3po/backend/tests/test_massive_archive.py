from datetime import date, datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.day_d_replay.massive_archive import (
    FlatFileDataset,
    MassiveArchiveError,
    MassiveFlatFileArchive,
)
from app.day_d_replay.massive_campaign import MassiveCampaignGuard


class FakeStore:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.downloads: list[str] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "flatfiles"
        etag = hashlib.md5(self.blobs[Key]).hexdigest()  # noqa: S324 - provider fixture only
        return {"ContentLength": len(self.blobs[Key]), "ETag": f'"{etag}"'}

    def download_fileobj(self, Bucket: str, Key: str, Fileobj) -> None:  # noqa: ANN001
        assert Bucket == "flatfiles"
        self.downloads.append(Key)
        Fileobj.write(self.blobs[Key])


def _key(dataset: FlatFileDataset) -> str:
    return MassiveFlatFileArchive.object_key(dataset, date(2026, 8, 21))


def _archive(
    tmp_path: Path,
    store: FakeStore,
    *,
    free: int = 10_000,
    disk_usage=None,
    download_authorized: bool = True,
    per_session_abort_bytes: int = 25_416_665_942,
    local_spool_ceiling_bytes: int = 76_249_997_826,
) -> MassiveFlatFileArchive:
    artifacts: dict[str, dict[str, object]] = {}
    for dataset in FlatFileDataset:
        key = _key(dataset)
        if key not in store.blobs:
            continue
        metadata = store.head_object(Bucket="flatfiles", Key=key)
        artifacts[dataset.value] = {
            "content_length": int(metadata["ContentLength"]),
            "remote_etag": str(metadata["ETag"]).strip('"'),
            "object_key": key,
        }
    if hasattr(store, "head_calls"):
        store.head_calls = 0
    scope_report = tmp_path / "scope.json"
    scope_report.parent.mkdir(parents=True, exist_ok=True)
    scope_report.write_text(json.dumps({
        "schema_version": "DAY-D-MASSIVE-T0-PLAN-SWEEP-v1",
        "downloaded": False,
        "source_csv_files": 0,
        "sessions": [{
            "session_date": "2026-08-21",
            "artifacts": artifacts,
        }],
    }), encoding="utf-8")
    return MassiveFlatFileArchive(
        store,
        root=tmp_path,
        minimum_free_bytes=1_000,
        per_session_abort_bytes=per_session_abort_bytes,
        local_spool_ceiling_bytes=local_spool_ceiling_bytes,
        campaign_guard=MassiveCampaignGuard(
            root=tmp_path,
            download_authorized=download_authorized,
            canonical_scope_report=scope_report,
            canonical_scope_report_sha256=hashlib.sha256(
                scope_report.read_bytes()
            ).hexdigest(),
            authorized_scope_bytes=sum(
                int(item["content_length"]) for item in artifacts.values()
            ),
            campaign_pause_bytes=10_000,
            require_complete_frozen_scope=False,
        ),
        disk_usage=disk_usage or (lambda _path: SimpleNamespace(free=free)),
    )


def test_massive_archive_plans_canonical_flat_file_paths_without_downloading(tmp_path: Path) -> None:
    blobs = {_key(FlatFileDataset.TRADES): b"trade-data"}
    store = FakeStore(blobs)

    plan = _archive(tmp_path, store).plan(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
    )

    assert len(plan) == 1
    assert plan[0].object_key == "us_stocks_sip/trades_v1/2026/08/2026-08-21.csv.gz"
    assert plan[0].content_length == len(b"trade-data")
    assert plan[0].remote_etag == hashlib.md5(b"trade-data").hexdigest()  # noqa: S324
    assert store.downloads == []


def test_massive_archive_keeps_download_disabled_until_reviewed_runtime_enablement(tmp_path: Path) -> None:
    store = FakeStore({_key(FlatFileDataset.TRADES): b"trade-data"})

    with pytest.raises(MassiveArchiveError, match="historical download remains disabled"):
        _archive(tmp_path, store, download_authorized=False).download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )

    assert store.downloads == []


def test_disk_guard_measures_the_configured_data_mount_root(tmp_path: Path) -> None:
    store = FakeStore({_key(FlatFileDataset.TRADES): b"trade-data"})
    observed_paths: list[Path] = []

    def disk_usage(path):  # noqa: ANN001
        observed_paths.append(Path(path))
        return SimpleNamespace(free=10_000)

    _archive(tmp_path, store, disk_usage=disk_usage).download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
    )

    assert observed_paths == [tmp_path]


def test_massive_archive_enforces_per_session_and_local_spool_limits(tmp_path: Path) -> None:
    store = FakeStore({_key(FlatFileDataset.TRADES): b"trade-data"})

    with pytest.raises(MassiveArchiveError, match="per-session byte guard"):
        _archive(tmp_path, store, per_session_abort_bytes=9).download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )
    with pytest.raises(MassiveArchiveError, match="local spool guard"):
        _archive(tmp_path, store, local_spool_ceiling_bytes=9).download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )

    assert store.downloads == []


def test_massive_archive_downloads_atomically_and_hashes_every_artifact(tmp_path: Path) -> None:
    blobs = {
        _key(FlatFileDataset.TRADES): b"trade-data",
        _key(FlatFileDataset.QUOTES): b"quote-data",
    }
    store = FakeStore(blobs)
    archive = _archive(tmp_path, store)

    manifest_path = archive.download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES, FlatFileDataset.QUOTES),
        measured_at=datetime(2026, 8, 22, 2, tzinfo=timezone.utc),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "DAY-D-MASSIVE-ARCHIVE-v1"
    assert manifest["raw_files_are_unadjusted"] is True
    assert manifest["corporate_action_adjustment_required"] is True
    assert manifest["official_replay_ready"] is False
    assert len(manifest["artifacts"]) == 2
    checksums = {item["dataset"]: item["sha256"] for item in manifest["artifacts"]}
    assert checksums == {
        "trades": hashlib.sha256(b"trade-data").hexdigest(),
        "quotes": hashlib.sha256(b"quote-data").hexdigest(),
    }
    assert not list(tmp_path.rglob("*.part"))


def test_massive_archive_reuses_verified_existing_artifact_without_downloading(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)
    store = FakeStore({key: b"original"})
    archive = _archive(tmp_path, store)
    archive.download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
    )
    manifest_path = archive.download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = Path(manifest["artifacts"][0]["local_path"])
    assert target.read_bytes() == b"original"
    assert manifest["artifacts"][0]["reused_existing_file"] is True
    assert store.downloads == [key]


def test_massive_archive_refuses_changed_remote_metadata_without_overwriting(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)
    store = FakeStore({key: b"original"})
    archive = _archive(tmp_path, store)
    archive.download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
    )
    store.blobs[key] = b"changed!"

    with pytest.raises(MassiveArchiveError, match="metadata differs"):
        archive.download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )

    target = archive.local_path(FlatFileDataset.TRADES, date(2026, 8, 21))
    assert target.read_bytes() == b"original"
    assert store.downloads == [key]


def test_massive_archive_disk_guard_blocks_before_any_download(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)
    store = FakeStore({key: b"x" * 200})
    archive = _archive(tmp_path, store, free=1_100)

    with pytest.raises(MassiveArchiveError, match="disk guard blocked"):
        archive.download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )

    assert store.downloads == []


def test_massive_archive_removes_partial_file_after_size_mismatch(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)

    class ShortStore(FakeStore):
        def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            return {"ContentLength": 100, "ETag": '"remote"'}

    store = ShortStore({key: b"too-short"})
    archive = _archive(tmp_path, store)

    with pytest.raises(MassiveArchiveError, match="size mismatch"):
        archive.download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
        )

    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("source.csv.gz"))


def test_massive_archive_quarantines_download_when_rehead_changes(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)

    class ChangingStore(FakeStore):
        def __init__(self, blobs: dict[str, bytes]) -> None:
            super().__init__(blobs)
            self.head_calls = 0

        def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
            self.head_calls += 1
            metadata = super().head_object(Bucket=Bucket, Key=Key)
            if self.head_calls > 1:
                metadata["ETag"] = '"changed-after-plan"'
            return metadata

    store = ChangingStore({key: b"downloaded-once"})
    archive = _archive(tmp_path, store)

    with pytest.raises(MassiveArchiveError, match="changed during download"):
        archive.download(
            session_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
            measured_at=datetime(2026, 8, 22, 3, tzinfo=timezone.utc),
        )

    assert not archive.local_path(FlatFileDataset.TRADES, date(2026, 8, 21)).exists()
    quarantined = list(tmp_path.rglob("category=remote-changed/*source.csv.gz*"))
    assert len([path for path in quarantined if not path.name.endswith(".json")]) == 1
    assert len([path for path in quarantined if path.name.endswith(".metadata.json")]) == 1
    assert not list(tmp_path.rglob("*.part"))


def test_massive_archive_quarantines_orphan_parts_before_next_download(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)
    store = FakeStore({key: b"fresh"})
    archive = _archive(tmp_path, store)
    orphan = tmp_path / "provider=massive" / "dataset=trades" / ".old-download.part"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"incomplete")

    archive.download(
        session_date=date(2026, 8, 21),
        datasets=(FlatFileDataset.TRADES,),
        measured_at=datetime(2026, 8, 22, 4, tzinfo=timezone.utc),
    )

    assert not orphan.exists()
    quarantined = list(tmp_path.rglob("category=orphan-part/*old-download.quarantined*"))
    assert len([path for path in quarantined if not path.name.endswith(".json")]) == 1
    assert len([path for path in quarantined if path.name.endswith(".metadata.json")]) == 1
    assert archive.local_path(FlatFileDataset.TRADES, date(2026, 8, 21)).read_bytes() == b"fresh"


def test_massive_archive_refuses_concurrent_download_process(tmp_path: Path) -> None:
    key = _key(FlatFileDataset.TRADES)
    store = FakeStore({key: b"fresh"})
    archive = _archive(tmp_path, store)
    tmp_path.mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / ".massive-download.lock"

    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MassiveArchiveError, match="already running"):
            archive.download(
                session_date=date(2026, 8, 21),
                datasets=(FlatFileDataset.TRADES,),
            )

    assert store.downloads == []
