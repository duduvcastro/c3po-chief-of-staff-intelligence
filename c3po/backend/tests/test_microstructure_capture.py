from datetime import datetime, timezone
import json
from pathlib import Path

from app.market_data.eodhd_stream import EodhdRealtimeStream
from app.microstructure_capture import AppendOnlyRawStreamCapture


class RecordingCapture:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, datetime]] = []

    def start(self) -> None:
        pass

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool:
        self.events.append((feed, payload, received_at))
        return True

    def stop(self) -> None:
        pass


def test_stream_forwards_exact_trade_and_quote_payloads_before_aggregation() -> None:
    capture = RecordingCapture()
    stream = EodhdRealtimeStream("token", raw_capture=capture)
    trade = '{"s":"AAPL","p":225.5,"v":100,"t":1787333400000}'
    quote = '{"s":"AAPL","bp":225.49,"ap":225.51,"t":1787333400100}'

    stream._record(trade)
    stream._record_quote(quote)

    assert [(feed, payload) for feed, payload, _ in capture.events] == [
        ("trade", trade),
        ("quote", quote),
    ]


def test_append_only_capture_preserves_raw_payload_and_partitions_by_market_session(tmp_path: Path) -> None:
    capture = AppendOnlyRawStreamCapture(tmp_path, flush_every=1)
    capture.start()
    received_at = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    payload = '{"s":"JPM","p":301.25,"v":250,"t":1787322600000}'

    assert capture.record("trade", payload, received_at=received_at) is True
    capture.stop()

    files = list(tmp_path.glob("session_date=*/feed=trade-part-*.ndjson"))
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8"))
    assert row["schema_version"] == 1
    assert row["provider"] == "EODHD"
    assert row["feed"] == "trade"
    assert row["payload_raw"] == payload
    assert row["event_at"].endswith("+00:00")
    assert capture.stats().accepted == 1
    assert capture.stats().written == 1
    assert capture.stats().dropped == 0


def test_append_only_capture_rotates_without_overwriting_prior_parts(tmp_path: Path) -> None:
    capture = AppendOnlyRawStreamCapture(
        tmp_path,
        rotate_bytes=1_024,
        flush_every=1,
    )
    capture.start()
    observed = datetime(2026, 8, 21, 15, tzinfo=timezone.utc)
    for index in range(20):
        payload = json.dumps({
            "s": "AAPL", "p": 200 + index, "v": index + 1,
            "t": 1787324400000 + index, "padding": "x" * 180,
        })
        assert capture.record("trade", payload, received_at=observed) is True
    capture.stop()

    files = sorted(tmp_path.glob("session_date=*/feed=trade-part-*.ndjson"))
    assert len(files) > 1
    rows = [
        json.loads(line)
        for path in files
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 20
    assert len({row["payload_raw"] for row in rows}) == 20


def test_append_only_capture_drops_instead_of_blocking_when_queue_is_full(tmp_path: Path) -> None:
    capture = AppendOnlyRawStreamCapture(tmp_path, queue_size=1)
    observed = datetime(2026, 8, 21, 15, tzinfo=timezone.utc)

    assert capture.record("trade", "first", received_at=observed) is True
    assert capture.record("trade", "second", received_at=observed) is False
    assert capture.stats().accepted == 1
    assert capture.stats().dropped == 1
