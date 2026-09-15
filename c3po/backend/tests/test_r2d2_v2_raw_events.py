"""Local producer-to-file-port counterproof; no provider or live host input."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from app.market_data import eodhd_stream
from app.microstructure_capture import AppendOnlyRawStreamCapture
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_raw_events import decode_record
from app.r2d2_v2_sources import FileShadowSource, SourceUnavailable, canonical

AT = datetime(2026, 9, 14, 19, 59, 40, tzinfo=timezone.utc)
PATH = "session_date=2026-09-14/feed=quote-part-00001.ndjson"


@pytest.fixture(scope="module")
def calendar():
    return ShadowCalendar()


def row(*, at=AT, received=AT, **payload):
    item = {"s": "SYNTH", "t": int(at.timestamp() * 1000), "bp": 100, "ap": 101, **payload}
    return canonical({"schema_version": 1, "provider": "EODHD", "feed": "quote",
                      "event_at": at.isoformat(), "received_at": received.isoformat(),
                      "payload_raw": json.dumps(item)}) + b"\n"


def decode(data, calendar, **kwargs):
    args = dict(relative_path=PATH, offset=0, sequence=0, now=AT + timedelta(seconds=3), calendar=calendar)
    return decode_record(data, **(args | kwargs))


def test_actual_stream_spool_and_file_port_preserve_all_packets(tmp_path, monkeypatch, calendar):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return AT

    def forbidden(*args, **kwargs):
        pytest.fail("No sockets or provider calls in the local integration test")

    monkeypatch.setattr(eodhd_stream, "datetime", Clock)
    monkeypatch.setattr(eodhd_stream.websockets, "connect", forbidden)
    raw = tmp_path.resolve() / "raw"
    capture = AppendOnlyRawStreamCapture(raw, minimum_free_bytes=0, flush_every=1)
    stream = eodhd_stream.EodhdRealtimeStream("unused", raw_capture=capture)
    capture.start()  # Deliberately do not start the stream network loop.
    try:
        for bid, ask in [(100, 101), (-1, 0), (102, 103), (99, 100)]:
            stream._record_quote(json.dumps({"s": "SYNTH", "bp": bid, "ap": ask,
                                             "t": int(AT.timestamp() * 1000)}))
    finally:
        capture.stop()
    # Legacy latest quote cannot prove the earlier profitable packet existed.
    assert stream.quote("SYNTH").bid == 99
    path = raw / PATH
    lines = path.read_bytes().splitlines(keepends=True)
    assert capture.stats().written == 4 and capture.stats().dropped == 0
    port_root = tmp_path.resolve() / "port"
    port_root.mkdir(mode=0o700)
    (port_root / "events").mkdir(mode=0o700)
    offset = 0
    for sequence, line in enumerate(lines):
        envelope = decode(line, calendar, offset=offset, sequence=sequence)
        assert envelope["provenance"]["payload_sha256"] == hashlib.sha256(line).hexdigest()
        destination = port_root / "events" / f"{envelope['event_id']}.{envelope['self_sha256']}.json"
        destination.write_bytes(canonical(envelope))
        destination.chmod(0o600)
        offset += len(line)
    port = FileShadowSource(port_root)
    events = port.events(AT + timedelta(seconds=3))
    assert not port.last_event_diagnostics
    assert [event["bid"] for event in events] == [100, -1, 102, 99]
    assert all(event["type"] == "QUOTE" and "coverage_complete" not in event for event in events)


def test_future_quote_keeps_payload_clock_for_economic_rejection(calendar):
    future = AT + timedelta(seconds=10)
    envelope = decode(row(at=future), calendar)
    assert envelope["event"]["at"] == AT.isoformat()
    assert envelope["event"]["bid_at"] == future.isoformat()
    assert envelope["source_at"] == AT.isoformat()


def test_raw_receipt_and_identity_are_stable_across_later_reads(calendar):
    data = row()
    first = decode(data, calendar)
    assert decode(data, calendar, now=AT + timedelta(hours=1)) == first
    assert decode(data, calendar, offset=len(data))["event_id"] != first["event_id"]
    assert decode(row(bp=99), calendar)["event_id"] != first["event_id"]


@pytest.mark.parametrize("bid,ask", [(0, 0), (-1, 5), (102, 101)])
def test_invalid_finite_quote_is_evidence_not_a_dropped_packet(calendar, bid, ask):
    event = decode(row(bp=bid, ap=ask), calendar)["event"]
    assert (event["bid"], event["ask"]) == (bid, ask)


@pytest.mark.parametrize("changes", [{"bp": None}, {"bp": True}, {"t": None}, {"t": 1.5}, {"s": "../bad"}])
def test_missing_or_malformed_data_is_not_fabricated(calendar, changes):
    with pytest.raises(SourceUnavailable):
        decode(row(**changes), calendar)


def test_partition_fallback_and_duplicate_keys_are_rejected(calendar):
    data = row()
    with pytest.raises(SourceUnavailable, match="PARTITION"):
        decode(data, calendar, relative_path=PATH.replace("09-14", "09-15"))
    parsed = json.loads(data)
    parsed["event_at"] = (AT + timedelta(seconds=1)).isoformat()
    with pytest.raises(SourceUnavailable, match="FALLBACK_OR_MISMATCH"):
        decode(canonical(parsed) + b"\n", calendar)
    with pytest.raises(SourceUnavailable, match="DUPLICATE"):
        decode(data.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'), calendar)
    with pytest.raises(SourceUnavailable, match="FRAME"):
        decode(data[:-1], calendar)


def test_short_session_excludes_exact_close(calendar):
    before = datetime(2026, 11, 27, 17, 59, 59, tzinfo=timezone.utc)
    close = before + timedelta(seconds=1)
    path = PATH.replace("2026-09-14", "2026-11-27")
    assert decode(row(at=before, received=before), calendar, relative_path=path,
                  now=close)["event"]["regular"] is True
    assert decode(row(at=close, received=close), calendar, relative_path=path,
                  now=close)["event"]["regular"] is False


def test_trade_remains_a_trade_never_a_complete_bar(calendar):
    parsed = json.loads(row())
    parsed["feed"] = "trade"
    parsed["payload_raw"] = json.dumps({"s": "SYNTH", "t": int(AT.timestamp() * 1000), "p": 100})
    data = canonical(parsed) + b"\n"
    event = decode(data, calendar, relative_path=PATH.replace("quote", "trade"))["event"]
    assert event["type"] == "TRADE" and event["price"] == 100
    assert "coverage_complete" not in event
    parsed["received_at"] = (AT - timedelta(seconds=1)).isoformat()
    with pytest.raises(SourceUnavailable, match="TRADE_IN_FUTURE"):
        decode(canonical(parsed) + b"\n", calendar, relative_path=PATH.replace("quote", "trade"))
