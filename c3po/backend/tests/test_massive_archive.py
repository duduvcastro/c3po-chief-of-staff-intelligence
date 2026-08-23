from datetime import date, datetime, timezone
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


def _archive(tmp_path: Path, store: FakeStore, *, free: int = 10_000) -> MassiveFlatFileArchive:
    return MassiveFlatFileArchive(
        store,
        root=tmp_path,
        minimum_free_bytes=1_000,
        disk_usage=lambda _path: SimpleNamespace(free=free),
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

    with pytest.raises(MassiveArchiveError, match="remote metadata changed"):
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
