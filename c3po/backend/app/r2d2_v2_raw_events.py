"""Decode an existing raw-stream record; never subscribe, capture or write.

This is the conversion boundary for the already captured EODHD spool, not a
claim that the deployed collector consumes that spool. The caller must retain
the original bytes and locator and commit its cursor with event receipts.
Neither a trade nor a quote proves uninterrupted BAR/event-clock coverage.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

from .r2d2_v2_sources import (
    AMENDMENT_SHA, EVENT_SCHEMA, MANIFEST_SHA, SourceUnavailable,
    _load_json, _metadata, _require, _time, _validate_event, canonical,
)

MAX_RAW_RECORD_BYTES = 64 * 1024
_PATH = re.compile(r"session_date=(\d{4}-\d{2}-\d{2})/feed=(quote|trade)-part-(\d{5,})\.ndjson\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")
_FIELDS = {"schema_version", "provider", "feed", "received_at", "event_at", "payload_raw"}


def decode_record(data: bytes, *, relative_path: str, offset: int,
                  sequence: int, now: datetime, calendar: Any) -> dict[str, Any]:
    """Produce one validated envelope, retaining producer/collector clocks.

    QUOTE.at is the producer's local reception. Bid/ask clocks are the exact
    payload timestamp, including future timestamps: the economic gate rejects
    those quotes without concealing the next valid packet. TRADE.at is the
    exchange timestamp and must not be future at reception. No timestamp is
    supplied from a fallback or file mtime. A caller must treat malformed data
    as missing evidence, never skip it and assert a complete tape.
    """
    _require(type(data) is bytes and 0 < len(data) <= MAX_RAW_RECORD_BYTES
             and data.endswith(b"\n") and b"\n" not in data[:-1], "RAW_RECORD_FRAME_INVALID")
    match = _PATH.fullmatch(relative_path)
    _require(match is not None, "RAW_LOCATOR_INVALID")
    assert match is not None
    _require(type(offset) is int and offset >= 0 and type(sequence) is int
             and sequence >= 0, "RAW_POSITION_INVALID")
    _require(now.tzinfo is not None, "NOW_NOT_AWARE")
    row = _load_json(data)
    _require(set(row) == _FIELDS and type(row["schema_version"]) is int
             and row["schema_version"] == 1 and row["provider"] == "EODHD"
             and row["feed"] == match[2], "RAW_RECORD_SCHEMA_INVALID")
    _require(isinstance(row["payload_raw"], str), "RAW_PAYLOAD_INVALID")
    payload = _load_json(row["payload_raw"].encode("utf-8"))
    if "s" not in payload:
        raise SourceUnavailable("RAW_NON_TICK")
    symbol = payload.get("s")
    if not isinstance(symbol, str) or _SYMBOL.fullmatch(symbol) is None:
        raise SourceUnavailable("RAW_SYMBOL_INVALID")
    timestamp = payload.get("t")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
        raise SourceUnavailable("RAW_TIMESTAMP_INVALID")
    try:
        source = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise SourceUnavailable("RAW_TIMESTAMP_INVALID") from None
    received = _time(row["received_at"])
    _require(source == _time(row["event_at"]), "RAW_TIMESTAMP_FALLBACK_OR_MISMATCH")
    _require(received <= now, "RAW_RECEIPT_IN_FUTURE")
    ny = ZoneInfo("America/New_York")
    _require(source.astimezone(ny).date().isoformat() == match[1], "RAW_PARTITION_MISMATCH")
    at = received if row["feed"] == "quote" else source
    _require(at <= received, "RAW_TRADE_IN_FUTURE")
    # regular() includes close for daily bars; individual packets exclude it.
    day = at.astimezone(ny).date()
    regular = bool(calendar.is_session(day)
                   and calendar.details(day)["open"] <= at < calendar.details(day)["close"])
    event: dict[str, Any] = {"type": row["feed"].upper(), "at": at.isoformat(),
             "available_at": received.isoformat(), "session": day.isoformat(),
             "instrument_key": "US:" + symbol, "regular": regular}
    if row["feed"] == "quote":
        for key in ("bp", "ap"):
            value = payload.get(key)
            try:
                finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            except OverflowError:
                finite = False
            _require(finite, "RAW_QUOTE_PRICE_MISSING_OR_NONFINITE")
        event.update(bid=payload["bp"], ask=payload["ap"],
                     bid_at=source.isoformat(), ask_at=source.isoformat())
    else:
        price = payload.get("p")
        try:
            valid_price = (isinstance(price, (int, float)) and not isinstance(price, bool)
                           and math.isfinite(price) and price > 0)
        except OverflowError:
            valid_price = False
        _require(valid_price, "RAW_TRADE_PRICE_INVALID")
        event["price"] = price
    raw_hash = hashlib.sha256(data).hexdigest()
    locator = {"path": relative_path, "offset": offset, "raw_sha256": raw_hash}
    identity = hashlib.sha256(canonical(locator)).hexdigest()
    envelope: dict[str, Any] = {"schema": EVENT_SCHEMA, "manifest_sha": MANIFEST_SHA,
                "amendment_sha": AMENDMENT_SHA,
                "source_id": "raw-" + hashlib.sha256(relative_path.encode()).hexdigest(),
                "provenance": {"producer": "eodhd-existing-raw-stream", "version": "v1",
                               "payload_sha256": raw_hash},
                "source_at": received.isoformat(), "available_at": received.isoformat(),
                "sequence": sequence, "event_id": "raw-" + identity, "event": event}
    envelope["self_sha256"] = hashlib.sha256(canonical(envelope)).hexdigest()
    _metadata(envelope, EVENT_SCHEMA, now)
    _validate_event(event, received)
    return envelope


def inspect_record(data: bytes, *, relative_path: str, offset: int,
                   sequence: int, now: datetime, calendar: Any) -> dict[str, Any]:
    """Classify one complete frame; quarantine is evidence, not tape coverage.

    sequence counts decoded events only. Every consumed frame, including one
    skipped here, is covered by its byte range and SHA in the same cursor
    transaction. There is no fabricated SOURCE_EVENT or sequence gap for a
    provider status frame. No nominal payload is included in the receipt.
    """
    received = None
    try:
        candidate = _time(_load_json(data)["received_at"])
        if candidate <= now:
            received = candidate
    except (SourceUnavailable, KeyError, TypeError, ValueError, OverflowError):
        pass
    try:
        envelope = decode_record(data, relative_path=relative_path, offset=offset,
                                 sequence=sequence, now=now, calendar=calendar)
    except (SourceUnavailable, ValueError, TypeError, KeyError, OverflowError) as exc:
        code = str(exc) if isinstance(exc, SourceUnavailable) else "RAW_RECORD_MALFORMED"
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", code) is None:
            code = "RAW_RECORD_MALFORMED"
        return {"envelope": None, "received_at": received,
                "receipt": {"path": relative_path, "offset": offset, "bytes": len(data),
                            "raw_sha256": hashlib.sha256(data).hexdigest(), "code": code,
                            "disposition": "SKIPPED" if code == "RAW_NON_TICK" else "QUARANTINED"}}
    return {"envelope": envelope, "received_at": received, "receipt": None}
