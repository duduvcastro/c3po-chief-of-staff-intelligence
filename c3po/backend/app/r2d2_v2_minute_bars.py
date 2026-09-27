"""Strict conversion of provider CLOSED minute history; no live activation.

Transport must retain the raw response and receipt before committing events.
This module never closes rolling WebSocket candles or invents empty minutes.
An upstream aggregate describes its own venue, not a consolidated market tape.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

from .r2d2_v2_sources import SourceUnavailable, _load_json, _require, _validate_event

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 4096
_FIELDS = {"s", "i", "t", "o", "h", "l", "c", "v"}
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")
PROVENANCE = "EODHD_REALTIME_CLOSED_HISTORY_CBOE_EDGX_V1"
MASSIVE_PROVENANCE = "MASSIVE_REST_UNADJUSTED_MINUTE_AGGREGATES_V1"


def _price(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def closed_minute(data: bytes, *, symbol: str, minute: datetime,
                  request_started: datetime, received_at: datetime,
                  now: datetime, calendar: Any, provider: str = "eodhd") -> dict[str, Any]:
    """Return a validated BAR or explicit gap for ONE requested closed minute.

    Called only for a successful authenticated response from the allowlisted
    history transport. Receipt clocks are local observations, never inferred
    from provider timestamps. Invalid history raises SourceUnavailable so the
    scheduler must record a gap, not silently omit the failure. Reconciliation
    of repeated/conflicting minutes belongs to the durable commit boundary.
    """
    _require(type(data) is bytes and 0 < len(data) <= MAX_RESPONSE_BYTES,
             "MINUTE_RESPONSE_SIZE")
    _require(isinstance(symbol, str) and _SYMBOL.fullmatch(symbol) is not None,
             "MINUTE_SYMBOL")
    _require(all(isinstance(t, datetime) and t.utcoffset() is not None
                 for t in (minute, request_started, received_at, now)), "MINUTE_CLOCK")
    minute = minute.astimezone(timezone.utc)
    _require(minute.second == 0 and minute.microsecond == 0, "MINUTE_ALIGNMENT")
    end = minute + timedelta(minutes=1)
    _require(end <= request_started <= received_at <= now, "MINUTE_NOT_CLOSED_OR_CLOCK")
    day = minute.astimezone(ZoneInfo("America/New_York")).date()
    _require(calendar.is_session(day), "MINUTE_NOT_SESSION")
    session = calendar.details(day)
    _require(session["open"] <= minute < end <= session["close"], "MINUTE_NOT_REGULAR")
    _require(provider in ("eodhd", "massive"), "MINUTE_PROVIDER")
    if provider == "massive":
        envelope = _load_json(data)
        _require(envelope.get("status") == "OK" and envelope.get("ticker") == symbol,
                 "MINUTE_PROVIDER_STATUS_OR_IDENTITY")
        _require(envelope.get("adjusted") is False and not envelope.get("next_url"),
                 "MINUTE_ADJUSTMENT_OR_PAGINATION")
        original = envelope.get("results", [])
        _require(type(original) is list and len(original) <= MAX_ROWS,
                 "MINUTE_RESPONSE_SCHEMA")
        _require(type(envelope.get("resultsCount")) is int
                 and envelope["resultsCount"] == len(original), "MINUTE_RESULTS_COUNT")
        rows = []
        for item in original:
            _require(type(item) is dict and {"t", "o", "h", "l", "c", "v"} <= set(item)
                     and set(item) <= {"t", "o", "h", "l", "c", "v", "vw", "n", "otc"},
                     "MINUTE_ROW_SCHEMA")
            _require(item.get("otc", False) is False, "MINUTE_OTC")
            rows.append({**{k: item[k] for k in ("t", "o", "h", "l", "c", "v")},
                         "s": symbol, "i": "1m"})
    else:
        # Only the parser wrapper is synthetic; exact provider bytes are hashed below.
        parsed = _load_json(b'{"rows":' + data + b'}')
        _require(set(parsed) == {"rows"}, "MINUTE_RESPONSE_SCHEMA")
        rows = parsed["rows"]
    _require(type(rows) is list and len(rows) <= MAX_ROWS, "MINUTE_RESPONSE_SCHEMA")
    selected = None
    previous = -1
    for row in rows:
        _require(type(row) is dict and set(row) == _FIELDS, "MINUTE_ROW_SCHEMA")
        _require(row["s"] == symbol and row["i"] == "1m", "MINUTE_IDENTITY")
        timestamp = row["t"]
        _require(type(timestamp) is int and timestamp > 0 and timestamp % 60000 == 0,
                 "MINUTE_PROVIDER_TIMESTAMP")
        _require(timestamp > previous, "MINUTE_DUPLICATE_OR_OUT_OF_ORDER")
        previous = timestamp
        try:
            opened = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        except (OverflowError, ValueError, OSError):
            raise SourceUnavailable("MINUTE_PROVIDER_TIMESTAMP") from None
        _require(opened + timedelta(minutes=1) <= request_started, "MINUTE_PROVIDER_OPEN_BAR")
        _require(all(_price(row[k]) for k in ("o", "h", "l", "c")), "MINUTE_PRICE")
        _require(row["l"] <= min(row["o"], row["c"])
                 <= max(row["o"], row["c"]) <= row["h"], "MINUTE_OHLC")
        _require(_price(row["v"]) and (provider == "massive" or type(row["v"]) is int),
                 "MINUTE_VOLUME")
        if opened == minute:
            selected = row
    event: dict[str, Any] = {"at": minute.isoformat(), "available_at": received_at.isoformat(),
                             "session": day.isoformat(), "instrument_key": "US:" + symbol}
    # Never extend the motor's 90-second allowance. Late backfill is evidence
    # of a missed LIVE observation, even when the historical OHLC is valid.
    if selected is None or now - minute > timedelta(seconds=90):
        event.update(type="DATA_GAP", reason="MINUTE_ABSENT" if selected is None else "MINUTE_LATE")
    else:
        event.update(type="BAR", end_at=end.isoformat(), open=selected["o"], high=selected["h"],
                     low=selected["l"], close=selected["c"], regular=True, coverage_complete=True)
    _validate_event(event, now)
    return {"event": event, "raw_sha256": hashlib.sha256(data).hexdigest(),
            "raw_bytes": len(data), "provenance": MASSIVE_PROVENANCE if provider == "massive" else PROVENANCE,
            "volume": selected["v"] if selected is not None else None,
            "request_started": request_started.isoformat(), "received_at": received_at.isoformat(),
            "end_to_receive_seconds": (received_at - end).total_seconds(),
            "request_seconds": (received_at - request_started).total_seconds(),
            "receive_to_consume_seconds": (now - received_at).total_seconds()}


def massive_stream_minute(data: bytes, *, symbol: str, minute: datetime,
                          received_at: datetime, now: datetime, calendar: Any,
                          connected_at: datetime) -> dict[str, Any]:
    """Validate an AM frame from an authenticated, uninterrupted connection.

    The caller supplies real receipt/connection clocks, persists the original
    frame, and invalidates coverage on connection loss. A reconnect cannot
    retroactively establish observation of a minute that began before it.
    """
    _require(type(data) is bytes and 0 < len(data) <= MAX_RESPONSE_BYTES,
             "MINUTE_RESPONSE_SIZE")
    _require(isinstance(connected_at, datetime) and connected_at.utcoffset() is not None
             and isinstance(minute, datetime) and minute.utcoffset() is not None
             and connected_at <= minute, "MINUTE_CONNECTION_GAP")
    parsed = _load_json(b'{"rows":' + data + b'}')
    _require(set(parsed) == {"rows"} and type(parsed["rows"]) is list
             and 0 < len(parsed["rows"]) <= MAX_ROWS, "MINUTE_STREAM_SCHEMA")
    rows = []
    allowed = {"ev", "sym", "v", "dv", "av", "dav", "op", "vw", "o", "c", "h",
               "l", "a", "z", "s", "e", "otc"}
    for row in parsed["rows"]:
        _require(type(row) is dict and {"ev", "sym", "v", "o", "c", "h", "l", "s", "e"}
                 <= set(row) and set(row) <= allowed, "MINUTE_STREAM_ROW")
        _require(row["ev"] == "AM" and row["sym"] == symbol, "MINUTE_IDENTITY")
        _require(type(row["s"]) is int and type(row["e"]) is int
                 and row["e"] - row["s"] == 60000, "MINUTE_STREAM_INTERVAL")
        _require(row.get("otc", False) is False, "MINUTE_OTC")
        rows.append({"t": row["s"], **{k: row[k] for k in ("o", "h", "l", "c", "v")}})
    # Normalization reuses validation only. It is not provider evidence and is
    # never stored/hashed as the original frame; the returned receipt binds data.
    from .r2d2_v2_sources import canonical
    normalized = canonical({"status": "OK", "ticker": symbol, "adjusted": False,
                            "resultsCount": len(rows), "results": rows})
    result = closed_minute(normalized, symbol=symbol, minute=minute,
                           request_started=received_at, received_at=received_at,
                           now=now, calendar=calendar, provider="massive")
    result.update(raw_sha256=hashlib.sha256(data).hexdigest(), raw_bytes=len(data),
                  provenance="MASSIVE_WEBSOCKET_AM_V1", connected_at=connected_at.isoformat())
    result.pop("request_started")
    result.pop("request_seconds")
    return result
