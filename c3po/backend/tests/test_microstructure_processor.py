from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from app.microstructure_capture import CompositeRawStreamCapture
from app.microstructure_processor import MicrostructureProcessor


def _timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _rows(root: Path, interval: int = 1) -> list[dict]:
    return [
        json.loads(line)
        for path in root.glob(f"session_date=*/interval={interval}s/part-*.ndjson")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_processor_classifies_trades_against_the_nearest_prior_fresh_bbo(tmp_path: Path) -> None:
    processor = MicrostructureProcessor(
        tmp_path, intervals_seconds=(1,), bbo_max_age_seconds=2, flush_every=1,
    )
    processor.start()
    base = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    processor.record("quote", json.dumps({
        "s": "AAPL", "bp": 100.0, "ap": 100.2, "t": _timestamp_ms(base),
    }), received_at=base)
    processor.record("trade", json.dumps({
        "s": "AAPL", "p": 100.2, "v": 300, "t": _timestamp_ms(base + timedelta(milliseconds=100)),
    }), received_at=base + timedelta(milliseconds=100))
    processor.record("trade", json.dumps({
        "s": "AAPL", "p": 100.0, "v": 125, "t": _timestamp_ms(base + timedelta(milliseconds=200)),
    }), received_at=base + timedelta(milliseconds=200))
    processor.stop()

    rows = _rows(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_count"] == 2
    assert row["quote_count"] == 1
    assert row["buy_trades"] == 1
    assert row["sell_trades"] == 1
    assert row["buy_volume"] == 300
    assert row["sell_volume"] == 125
    assert row["volume_delta"] == 175
    assert row["bbo_classified_trades"] == 2
    assert row["classification_coverage"] == 1.0
    assert row["mean_bbo_age_ms"] == 150.0


def test_processor_ignores_stale_bbo_and_falls_back_to_tick_rule(tmp_path: Path) -> None:
    processor = MicrostructureProcessor(
        tmp_path, intervals_seconds=(1,), bbo_max_age_seconds=2,
    )
    processor.start()
    base = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    processor.record("quote", json.dumps({
        "s": "JPM", "bp": 100.0, "ap": 100.2, "t": _timestamp_ms(base),
    }), received_at=base)
    processor.record("trade", json.dumps({
        "s": "JPM", "p": 100.1, "v": 50, "t": _timestamp_ms(base + timedelta(seconds=3)),
    }), received_at=base + timedelta(seconds=3))
    processor.record("trade", json.dumps({
        "s": "JPM", "p": 100.15, "v": 75, "t": _timestamp_ms(base + timedelta(seconds=3, milliseconds=100)),
    }), received_at=base + timedelta(seconds=3, milliseconds=100))
    processor.stop()

    trade_row = next(row for row in _rows(tmp_path) if row["trade_count"] == 2)
    assert trade_row["unknown_trades"] == 1
    assert trade_row["buy_trades"] == 1
    assert trade_row["tick_rule_trades"] == 1
    assert trade_row["bbo_classified_trades"] == 0
    assert trade_row["classification_coverage"] == 0.5


def test_processor_never_uses_a_quote_from_the_future(tmp_path: Path) -> None:
    processor = MicrostructureProcessor(tmp_path, intervals_seconds=(1,))
    processor.start()
    base = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    processor.record("quote", json.dumps({
        "s": "MSFT", "bp": 499.0, "ap": 501.0,
        "t": _timestamp_ms(base + timedelta(seconds=1)),
    }), received_at=base)
    processor.record("trade", json.dumps({
        "s": "MSFT", "p": 501.0, "v": 10, "t": _timestamp_ms(base),
    }), received_at=base + timedelta(milliseconds=10))
    processor.stop()

    trade_row = next(row for row in _rows(tmp_path) if row["trade_count"] == 1)
    assert trade_row["unknown_trades"] == 1
    assert trade_row["bbo_classified_trades"] == 0


def test_processor_emits_one_and_five_second_aggregates(tmp_path: Path) -> None:
    processor = MicrostructureProcessor(tmp_path, intervals_seconds=(1, 5))
    processor.start()
    base = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    for offset in (0.1, 1.1, 4.1):
        event_at = base + timedelta(seconds=offset)
        processor.record("trade", json.dumps({
            "s": "NVDA", "p": 180 + offset, "v": 10,
            "t": _timestamp_ms(event_at),
        }), received_at=event_at)
    processor.stop()

    one_second = [row for row in _rows(tmp_path, 1) if row["trade_count"]]
    five_second = [row for row in _rows(tmp_path, 5) if row["trade_count"]]
    assert len(one_second) == 3
    assert len(five_second) == 1
    assert five_second[0]["trade_count"] == 3
    assert five_second[0]["total_volume"] == 30


def test_processor_counts_delayed_and_too_late_events_without_aggregating_them(tmp_path: Path) -> None:
    processor = MicrostructureProcessor(
        tmp_path, intervals_seconds=(1,), allowed_lateness_seconds=2,
    )
    processor.start()
    base = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    processor.record("trade", json.dumps({
        "s": "META", "p": 700, "v": 10, "t": _timestamp_ms(base + timedelta(seconds=10)),
    }), received_at=base + timedelta(seconds=10))
    processor.record("trade", json.dumps({
        "s": "META", "p": 699, "v": 10, "t": _timestamp_ms(base),
    }), received_at=base + timedelta(seconds=10, milliseconds=10))
    processor.record("trade", json.dumps({
        "s": "META", "p": 701, "v": 10, "t": _timestamp_ms(base + timedelta(seconds=11)),
        "dp": True,
    }), received_at=base + timedelta(seconds=11))
    processor.stop()

    assert sum(row["trade_count"] for row in _rows(tmp_path)) == 1
    stats = processor.stats()
    assert stats.processed == 1
    assert stats.late == 1
    assert stats.ignored == 1


class _LifecycleCapture:
    def __init__(self, name: str, events: list[str]) -> None:
        self.name = name
        self.events = events

    def start(self) -> None:
        self.events.append(f"start:{self.name}")

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool:
        self.events.append(f"record:{self.name}:{feed}:{payload}")
        return True

    def stop(self) -> None:
        self.events.append(f"stop:{self.name}")


def test_composite_capture_fans_out_and_stops_in_reverse_order() -> None:
    events: list[str] = []
    first = _LifecycleCapture("raw", events)
    second = _LifecycleCapture("processor", events)
    composite = CompositeRawStreamCapture([first, second])
    now = datetime.now(timezone.utc)

    composite.start()
    assert composite.record("trade", "payload", received_at=now) is True
    composite.stop()

    assert events == [
        "start:raw", "start:processor",
        "record:raw:trade:payload", "record:processor:trade:payload",
        "stop:processor", "stop:raw",
    ]
