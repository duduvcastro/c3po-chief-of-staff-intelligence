"""Synthetic provider responses; real XNYS calendar and event validation."""
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_minute_bars import closed_minute
from app.r2d2_v2_sources import SourceUnavailable

MINUTE = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def calendar():
    return ShadowCalendar()


def row(**changes):
    value = dict(s="AAPL", i="1m", t=int(MINUTE.timestamp() * 1000),
                 o=100, h=102, l=99, c=101, v=25)
    value.update(changes)
    return value


def convert(calendar, rows=None, *, raw=None, **changes):
    kwargs = dict(symbol="AAPL", minute=MINUTE,
                  request_started=MINUTE + timedelta(seconds=62),
                  received_at=MINUTE + timedelta(seconds=63),
                  now=MINUTE + timedelta(seconds=64), calendar=calendar)
    kwargs.update(changes)
    return closed_minute(raw if raw is not None else json.dumps([row()] if rows is None else rows).encode(), **kwargs)


def test_closed_preserves_exact_receipt_and_values(calendar):
    raw = json.dumps([row()]).encode()
    got = convert(calendar, raw=raw)
    assert got["event"]["coverage_complete"] is True
    assert got["event"]["close"] == 101
    assert got["event"]["end_at"] == (MINUTE + timedelta(minutes=1)).isoformat()
    assert got["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert got["volume"] == 25
    assert got["end_to_receive_seconds"] == 3


@pytest.mark.parametrize("change", [dict(s="MSFT"), dict(i="5m"), dict(t=True),
    dict(t=int(MINUTE.timestamp()*1000)+1), dict(t=10**100), dict(v=0), dict(v=True),
    dict(v=1.5), dict(o=0), dict(h=99), dict(l=103), dict(c=float("nan"))])
def test_bad_provider_row_refused(calendar, change):
    with pytest.raises(SourceUnavailable):
        convert(calendar, [row(**change)])


@pytest.mark.parametrize("raw", [b'[] ,"extra": 1', b'{"status":403}', b'[',
    b'[{"s":"AAPL","s":"MSFT"}]'])
def test_malformed_or_error_response_refused(calendar, raw):
    with pytest.raises(SourceUnavailable):
        convert(calendar, raw=raw)


def test_missing_minute_does_not_manufacture_price(calendar):
    got = convert(calendar, [])
    assert got["event"]["type"] == "DATA_GAP"
    assert got["event"]["reason"] == "MINUTE_ABSENT"
    assert "close" not in got["event"]


def test_late_consumer_does_not_rehabilitate_live_coverage(calendar):
    got = convert(calendar, now=MINUTE + timedelta(seconds=151))
    assert got["event"]["reason"] == "MINUTE_LATE"


def test_ninety_second_boundary_unchanged(calendar):
    assert convert(calendar, now=MINUTE+timedelta(seconds=150))["event"]["type"] == "BAR"


@pytest.mark.parametrize("rows", [[row(), row()], [row(), row(t=int(MINUTE.timestamp()*1000)-60000)]])
def test_duplicate_and_reverse_order_refused(calendar, rows):
    with pytest.raises(SourceUnavailable, match="DUPLICATE_OR_OUT_OF_ORDER"):
        convert(calendar, rows)


def test_current_rolling_minute_is_not_complete(calendar):
    with pytest.raises(SourceUnavailable, match="PROVIDER_OPEN_BAR"):
        convert(calendar, [row(t=int(MINUTE.timestamp()*1000)+60000)])


def test_request_before_minute_closes_refused(calendar):
    with pytest.raises(SourceUnavailable, match="NOT_CLOSED"):
        convert(calendar, request_started=MINUTE+timedelta(seconds=59))


def test_non_regular_minute_refused(calendar):
    with pytest.raises(SourceUnavailable, match="NOT_REGULAR"):
        convert(calendar, minute=MINUTE-timedelta(hours=2))
