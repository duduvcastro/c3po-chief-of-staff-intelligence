from datetime import date, datetime, timezone
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.day_d_replay.massive_archive import FlatFileDataset, MassiveFlatFileArchive
from app.day_d_replay.massive_plan_sweep import run_plan_sweep


class HeadOnlyStore:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.heads: list[str] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "flatfiles"
        self.heads.append(Key)
        if Key not in self.blobs:
            raise MissingObjectError
        payload = self.blobs[Key]
        etag = hashlib.md5(payload).hexdigest()  # noqa: S324 - provider fixture only
        return {"ContentLength": len(payload), "ETag": f'"{etag}"'}

    def download_fileobj(self, Bucket: str, Key: str, Fileobj) -> None:  # noqa: ANN001
        raise AssertionError("plan sweep must never download provider data")


class MissingObjectError(RuntimeError):
    response = {
        "Error": {"Code": "NoSuchKey", "Message": "missing"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


def _key(dataset: FlatFileDataset, session_date: date) -> str:
    return MassiveFlatFileArchive.object_key(dataset, session_date)


def test_massive_plan_sweep_is_head_only_and_preserves_every_session(tmp_path: Path) -> None:
    datasets = (
        FlatFileDataset.TRADES,
        FlatFileDataset.QUOTES,
        FlatFileDataset.MINUTE_AGGREGATES,
    )
    monday = date(2026, 8, 17)
    wednesday = date(2026, 8, 19)
    thursday = date(2026, 8, 20)
    friday = date(2026, 8, 21)
    blobs = {
        _key(FlatFileDataset.TRADES, monday): b"t" * 10,
        _key(FlatFileDataset.QUOTES, monday): b"q" * 20,
        _key(FlatFileDataset.MINUTE_AGGREGATES, monday): b"m" * 2,
        _key(FlatFileDataset.TRADES, wednesday): b"partial",
        _key(FlatFileDataset.TRADES, thursday): b"t" * 40,
        _key(FlatFileDataset.QUOTES, thursday): b"q" * 50,
        _key(FlatFileDataset.MINUTE_AGGREGATES, thursday): b"m" * 4,
        _key(FlatFileDataset.TRADES, friday): b"t" * 70,
        _key(FlatFileDataset.QUOTES, friday): b"q" * 80,
        _key(FlatFileDataset.MINUTE_AGGREGATES, friday): b"m" * 6,
    }
    store = HeadOnlyStore(blobs)
    archive = MassiveFlatFileArchive(
        store,
        root=tmp_path,
        disk_usage=lambda _path: SimpleNamespace(free=0),
    )

    report = run_plan_sweep(
        archive,
        start_date=monday,
        end_date=friday,
        datasets=datasets,
        measured_at=datetime(2026, 8, 22, 5, tzinfo=timezone.utc),
        workers=3,
        spot_dates=(monday, date(2026, 8, 18), wednesday, friday),
    )

    assert report["downloaded"] is False
    assert report["campaign"]["weekday_candidates"] == 5
    assert report["campaign"]["complete_sessions"] == 3
    assert report["campaign"]["head_requests"] == 15
    assert report["campaign"]["non_session_weekdays"] == ["2026-08-18"]
    assert report["campaign"]["partial_sessions"] == [{
        "session_date": "2026-08-19",
        "present": ["trades"],
        "missing": ["minute_aggregates", "quotes"],
    }]
    assert [row["session_date"] for row in report["sessions"]] == [
        "2026-08-17",
        "2026-08-20",
        "2026-08-21",
    ]
    assert report["raw_trades_quotes"]["p50_bytes"] == 90
    assert report["raw_trades_quotes"]["p95_bytes"] == 150
    assert report["maximum_session"] == {
        "session_date": "2026-08-21",
        "total_bytes": 156,
    }
    assert [item["status"] for item in report["spot_checks"]] == [
        "complete",
        "missing",
        "partial",
        "complete",
    ]
    assert len(store.heads) == 15
    assert not list(tmp_path.rglob("source.csv.gz"))


def test_massive_plan_sweep_rejects_naive_measurement_time(tmp_path: Path) -> None:
    archive = MassiveFlatFileArchive(HeadOnlyStore({}), root=tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        run_plan_sweep(
            archive,
            start_date=date(2026, 8, 21),
            end_date=date(2026, 8, 21),
            datasets=(FlatFileDataset.TRADES,),
            measured_at=datetime(2026, 8, 22, 5),
        )
