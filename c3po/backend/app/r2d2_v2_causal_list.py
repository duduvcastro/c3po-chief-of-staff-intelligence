"""Offline D-1 selection and receipt validation; no provider, SQL or writes.

build_commitment consumes exact captured JSON bytes, preserves them privately,
recomputes the signed liquidity rule and creates an UNSIGNED commitment. It
cannot attest when audit_events occurred. A producer must persist the build
receipt, publish the commitment, persist the publication receipt, then publish
{commitment, audit_receipt, publication_receipt} atomically to the file port.
A trusted external verifier must compare each receipt with the durable event.
Self-reported timestamps/hashes, file mtimes and this builder are not authority.
"""
from __future__ import annotations

import base64
import binascii
from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal, localcontext
import hashlib
from typing import Any, Callable, Protocol

from .r2d2_v2_sources import (AMENDMENT_SHA, MANIFEST_SHA, MAX_SNAPSHOT_BYTES, NY, SourceUnavailable,
    _SYMBOL, _causal, _load_json, _now, _number, _require, _time, _token, canonical)

SCHEMA = "V2_CAUSAL_LIST_COMMITMENT_V1"
REGISTRY_SCHEMA = "V2_CAUSAL_REGISTRY_V1"
DAILY_SCHEMA = "V2_CAUSAL_DAILY_CONTRACT_V1"
N_CUT = 550
MAX_INPUT_BYTES = MAX_SNAPSHOT_BYTES
MAX_CAUSAL_ENVELOPE_BYTES = MAX_SNAPSHOT_BYTES
# The emitter's two UUID receipts, duplicated hash bindings, UTC clocks and
# <=512-character publication reference fit here, including JSON escaping.
# The full envelope is also checked, so this reservation is never a substitute
# for checking the actual bytes before publication/private-file persistence.
CAUSAL_RECEIPT_RESERVE_BYTES = 16 * 1024
MAX_REGISTRY = 10000
ReceiptVerifier = Callable[[dict[str, Any], dict[str, Any]], bool]


class Calendar(Protocol):
    def details(self, day: date) -> dict: ...


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _base64_size(size: int) -> int:
    return 4 * ((size + 2) // 3)


def check_causal_input_sizes(registry_bytes: bytes, daily_bytes: bytes) -> int:
    """Reject raw/encoded impossibilities before parsing, database or sink I/O.

    Return the exact combined base64 length. Metadata is checked separately by
    build_commitment, before encoding or returning a persistable commitment.
    """
    _require(all(isinstance(value, bytes) and 0 < len(value) <= MAX_INPUT_BYTES
                 for value in (registry_bytes, daily_bytes)), "CAUSAL_INPUT_SIZE_LIMIT")
    encoded = _base64_size(len(registry_bytes)) + _base64_size(len(daily_bytes))
    _require(encoded <= MAX_CAUSAL_ENVELOPE_BYTES - CAUSAL_RECEIPT_RESERVE_BYTES,
             "CAUSAL_ENVELOPE_SIZE_LIMIT")
    return encoded


def check_causal_envelope_size(envelope: dict[str, Any]) -> int:
    """Check the actual canonical envelope, not just either raw input's cap."""
    item = envelope.get("commitment")
    if isinstance(item, dict):
        raw_length = sum(len(value) for key in ("registry_raw_base64", "daily_raw_base64")
                         if isinstance(value := item.get(key), str))
        _require(raw_length <= MAX_CAUSAL_ENVELOPE_BYTES, "CAUSAL_ENVELOPE_SIZE_LIMIT")
    size = len(canonical(envelope))
    _require(size <= MAX_CAUSAL_ENVELOPE_BYTES, "CAUSAL_ENVELOPE_SIZE_LIMIT")
    return size


def _day(value: date | str) -> date:
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        _require(parsed.isoformat() == value, "CAUSAL_SESSION_INVALID")
        return parsed
    _require(type(value) is date, "CAUSAL_SESSION_INVALID")
    return value


def _dates(day: date, calendar: Calendar) -> tuple[tuple[date, ...], datetime, datetime, datetime, str]:
    detail = calendar.details(day)
    prior = tuple(detail["previous_sessions"])
    _require(len(prior) == 61 and prior == tuple(sorted(set(prior))) and prior[-1] < day, "CAUSAL_CALENDAR_INVALID")
    return (prior, _now(calendar.details(prior[-1])["close"]),
            datetime.combine(day, time(), NY).astimezone(timezone.utc),
            datetime.combine(day, time(10), NY).astimezone(timezone.utc), detail["sha256"])


def _input(data: bytes, schema: str) -> dict[str, Any]:
    _require(isinstance(data, bytes) and 0 < len(data) <= MAX_INPUT_BYTES, "CAUSAL_INPUT_SIZE_LIMIT")
    result = _load_json(data)
    _require(result.get("schema") == schema and _token(result.get("source_id")), "CAUSAL_INPUT_SCHEMA")
    return result


def _liquidity(daily: Any, prior: tuple[date, ...], built: datetime, calendar: Calendar) -> tuple[Decimal, Decimal]:
    _require(isinstance(daily, dict), "ADV_WINDOW_INCOMPLETE")
    _require(set(daily) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}, "DAILY_CONTRACT_INVALID")
    _causal(daily, built)
    _require(daily["adjustment"] == "RAW_UNADJUSTED" and daily["coverage_verified"] is True and daily["split_coverage_verified"] is True,
             "DAILY_CONTRACT_INVALID")
    bars = daily["bars"]
    _require(isinstance(bars, list), "ADV_WINDOW_INCOMPLETE")
    expected20 = [item.isoformat() for item in prior[-20:]]
    actual = [bar.get("session_date") if isinstance(bar, dict) else None for bar in bars]
    _require(actual[-20:] == expected20, "ADV_WINDOW_INCOMPLETE")
    # Selection uses only the liquidity window. The later admission gate owns ATR61.
    for bar, session in zip(bars[-20:], prior[-20:]):
        _require(set(bar) == {"session_date", "open", "high", "low", "close", "volume", "complete", "regular_session", "source_at", "available_at"}, "DAILY_CONTRACT_INVALID")
        _require(bar["complete"] is True and bar["regular_session"] is True, "ADV_WINDOW_INCOMPLETE" if session in prior[-20:] else "DAILY_CONTRACT_INVALID")
        source, _ = _causal(bar, built)
        _require(_now(calendar.details(session)["close"]) <= source, "DAILY_NOT_OFFICIAL_CLOSE")
        _require(all(_number(bar[key], positive=True) for key in ("open", "high", "low", "close")) and _number(bar["volume"]), "DAILY_CONTRACT_INVALID")
        _require(bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"], "DAILY_CONTRACT_INVALID")
    _require(isinstance(daily["splits"], list), "DAILY_CONTRACT_INVALID")
    for split in daily["splits"]:
        _require(isinstance(split, dict) and set(split) == {"factor", "effective_at", "source_at", "available_at"} and _number(split["factor"], positive=True), "DAILY_CONTRACT_INVALID")
        _time(split["effective_at"])
        _causal(split, built)
    with localcontext() as context:
        context.prec = 800  # exact products/sums of finite native-number decimal representations
        adv = sum((Decimal(str(bar["close"])) * Decimal(str(bar["volume"])) for bar in bars[-20:]), Decimal(0)) / 20
    return Decimal(str(bars[-1]["close"])), adv


def build_commitment(*, epoch: str, day: date | str, built_at: datetime,
                     registry_bytes: bytes, daily_bytes: bytes, calendar: Calendar) -> dict[str, Any]:
    """Pure, bounded selection. Returned bytes are not an audit/publication receipt."""
    encoded_size = check_causal_input_sizes(registry_bytes, daily_bytes)
    _require(_token(epoch) and epoch not in {".", ".."}, "CAUSAL_EPOCH_INVALID")
    day, built = _day(day), _now(built_at)
    prior, after_close, cutoff, publication_deadline, calendar_sha = _dates(day, calendar)
    _require(after_close < built < cutoff, "CAUSAL_LIST_LATE")
    registry = _input(registry_bytes, REGISTRY_SCHEMA)
    daily = _input(daily_bytes, DAILY_SCHEMA)
    _require(set(registry) == {"schema", "source_id", "source_at", "available_at", "captured_at", "coverage_verified", "instruments"}, "REGISTRY_FIELDS")
    _require(set(daily) == {"schema", "source_id", "source_at", "available_at", "instruments"}, "DAILY_CONTRACT_FIELDS")
    _, registry_available = _causal(registry, built)
    _causal(daily, built)
    _require(after_close < _time(registry["captured_at"]) <= registry_available <= built, "REGISTRY_CAPTURE_NOT_D_MINUS_ONE")
    _require(registry["coverage_verified"] is True, "REGISTRY_COVERAGE_UNVERIFIED")
    records = registry["instruments"]
    daily_rows = daily["instruments"]
    _require(isinstance(records, list) and len(records) <= MAX_REGISTRY, "REGISTRY_SIZE_LIMIT")
    _require(isinstance(daily_rows, list) and len(daily_rows) <= MAX_REGISTRY, "DAILY_SIZE_LIMIT")
    by_symbol: dict[str, Any] = {}
    for row in daily_rows:
        _require(isinstance(row, dict) and set(row) == {"symbol", "daily"}, "DAILY_ROW_INVALID")
        symbol = row["symbol"]
        _require(isinstance(symbol, str) and _SYMBOL.fullmatch(symbol) is not None and symbol not in by_symbol, "DAILY_DUPLICATE_OR_INVALID_SYMBOL")
        by_symbol[symbol] = row["daily"]
    seen: set[str] = set()
    reasons: Counter[str] = Counter()
    excluded: list[dict[str, str]] = []
    ranked: list[tuple[Decimal, str]] = []
    filtered: list[str] = []
    for row in records:
        _require(isinstance(row, dict) and set(row) == {"symbol", "market", "security_type", "classification_verified"}, "REGISTRY_ROW_INVALID")
        symbol = row["symbol"]
        _require(isinstance(symbol, str) and _SYMBOL.fullmatch(symbol) is not None and symbol not in seen, "REGISTRY_DUPLICATE_OR_INVALID_SYMBOL")
        seen.add(symbol)
        reason = None
        if row["classification_verified"] is not True or not _token(row["security_type"]) or not _token(row["market"]):
            reason = "DATA_INELIGIBLE"
        elif row["market"] not in ("NYSE", "NASDAQ") or row["security_type"] not in ("COMMON_STOCK", "COMMON_STOCK_ADR"):
            reason = "CLASSIFICATION_EXCLUDED"
        else:
            filtered.append(symbol)
            try:
                close, adv = _liquidity(by_symbol.get(symbol), prior, built, calendar)
                reason = "CLOSE_BELOW_5" if close < 5 else "ADV_BELOW_15000000" if adv < 15000000 else None
                if reason is None:
                    ranked.append((adv, symbol))
            except SourceUnavailable as exc:
                reason = str(exc)
        if reason:
            reasons[reason] += 1
            excluded.append({"symbol": symbol, "reason": reason})
    ranked.sort(key=lambda pair: (pair[0].copy_negate(), pair[1]))
    selected = [symbol for _, symbol in ranked[:N_CUT]]
    for _, symbol in ranked[N_CUT:]:
        excluded.append({"symbol": symbol, "reason": "N_CUT_EXCLUDED"})
    reasons["N_CUT_EXCLUDED"] = max(0, len(ranked) - N_CUT)
    reasons["NOT_IN_CAUSAL_LIST"] = len(filtered) - len(selected)
    epoch_contract = {"epoch": epoch, "n_cut": N_CUT, "manifest_sha": MANIFEST_SHA, "amendment_sha": AMENDMENT_SHA}
    commitment = {"schema": SCHEMA, **epoch_contract, "epoch_contract_sha256": digest(epoch_contract),
            "session": day.isoformat(), "previous_session": prior[-1].isoformat(), "built_at": built.isoformat(),
            "cutoff_at": cutoff.isoformat(), "decision_at": publication_deadline.isoformat(), "calendar_sha256": calendar_sha,
            "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(), "daily_contract_sha256": hashlib.sha256(daily_bytes).hexdigest(),
            "registry_raw_base64": "", "daily_raw_base64": "",
            "list": selected, "list_sha256": digest(selected), "filtered_symbols": sorted(filtered),
            "ranked_liquidity": [{"symbol": symbol, "adv20_usd": str(adv)} for adv, symbol in ranked],
            "exclusions": sorted(excluded, key=lambda item: item["symbol"]),
            "counts": {"registry": len(records), "filtered": len(filtered), "liquidity_passed": len(ranked), "selected": len(selected), "reasons": dict(sorted(reasons.items()))},
            "coverage": {"numerator": len(selected), "denominator": len(filtered), "ratio": len(selected) / len(filtered) if filtered else None,
                         "scope": "FILTERED_PROVIDER_REGISTRY_ONLY", "outside_registry_observed": False, "complete_exchange_universe": False}}
    # Base64 is ASCII without JSON escapes. Empty placeholders let us measure
    # the exact final JSON size without first allocating both encoded inputs.
    projected_size = len(canonical(commitment)) + encoded_size
    _require(projected_size <= MAX_CAUSAL_ENVELOPE_BYTES - CAUSAL_RECEIPT_RESERVE_BYTES,
             "CAUSAL_ENVELOPE_SIZE_LIMIT")
    commitment["registry_raw_base64"] = base64.b64encode(registry_bytes).decode()
    commitment["daily_raw_base64"] = base64.b64encode(daily_bytes).decode()
    return commitment


def _decode(value: Any) -> bytes:
    _require(isinstance(value, str) and len(value) <= _base64_size(MAX_INPUT_BYTES), "CAUSAL_INPUT_SIZE_LIMIT")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise SourceUnavailable("CAUSAL_INPUT_ENCODING") from None
    _require(0 < len(decoded) <= MAX_INPUT_BYTES, "CAUSAL_INPUT_SIZE_LIMIT")
    return decoded


def validate_commitment(envelope: dict[str, Any], *, epoch: str, day: date | str, now: datetime,
                        calendar: Calendar, receipt_verifier: ReceiptVerifier | None) -> dict[str, Any]:
    _require(set(envelope) == {"commitment", "audit_receipt", "publication_receipt"}, "CAUSAL_ENVELOPE_FIELDS")
    check_causal_envelope_size(envelope)
    item = envelope["commitment"]
    _require(isinstance(item, dict), "CAUSAL_COMMITMENT_MISSING")
    _require(item.get("manifest_sha") == MANIFEST_SHA and item.get("amendment_sha") == AMENDMENT_SHA, "CAUSAL_MANIFEST_MISMATCH")
    now, day = _now(now), _day(day)
    built = _time(item.get("built_at"))
    _require(built <= now, "CAUSAL_BUILD_FUTURE")
    expected = build_commitment(epoch=epoch, day=day, built_at=built,
        registry_bytes=_decode(item.get("registry_raw_base64")), daily_bytes=_decode(item.get("daily_raw_base64")), calendar=calendar)
    _require(canonical(item) == canonical(expected), "CAUSAL_COMMITMENT_MISMATCH")
    commitment_sha = digest(item)
    binding = {key: item[key] for key in ("epoch", "session", "manifest_sha", "amendment_sha", "list_sha256", "n_cut")}
    binding["commitment_sha256"] = commitment_sha
    audit = envelope["audit_receipt"]
    publication = envelope["publication_receipt"]
    for receipt in (audit, publication):
        _require(isinstance(receipt, dict) and set(receipt) == {"event_id", "event_type", "occurred_at", "payload"}, "CAUSAL_RECEIPT_FIELDS")
        _require(_token(str(receipt["event_id"])) and type(receipt["event_id"]) in (int, str), "CAUSAL_RECEIPT_ID")
    audit_expected = {"event_type": "r2d2.v2.causal_list_built", "occurred_at": item["built_at"], "payload": binding}
    _require({key: audit[key] for key in audit_expected} == audit_expected, "AUDIT_RECEIPT_BINDING")
    _require(receipt_verifier is not None, "AUDIT_RECEIPT_UNVERIFIED")
    if receipt_verifier is None:  # type narrowing; default never certifies a self-reported event
        raise SourceUnavailable("AUDIT_RECEIPT_UNVERIFIED")
    try:
        audit_valid = receipt_verifier(audit, audit_expected) is True
    except Exception:
        audit_valid = False
    _require(audit_valid, "AUDIT_RECEIPT_UNVERIFIED")
    payload = publication["payload"]
    _require(isinstance(payload, dict), "PUBLICATION_RECEIPT_BINDING")
    published = _time(payload.get("published_at"))
    occurred = _time(publication["occurred_at"])
    _require(built <= published <= occurred <= now, "PUBLICATION_RECEIPT_FUTURE_OR_REVERSED")
    _require(published < _time(item["decision_at"]), "CAUSAL_LIST_LATE")
    _require(payload.get("channel") in ("relay", "github_issue_348") and isinstance(payload.get("publication_reference"), str)
             and 0 < len(payload["publication_reference"]) <= 512, "PUBLICATION_REFERENCE_INVALID")
    public_expected = {"event_type": "r2d2.v2.causal_list_published", "occurred_at": publication["occurred_at"],
        "payload": {**binding, "build_audit_event_id": audit["event_id"],
                    **{key: payload[key] for key in ("channel", "publication_reference", "published_at")}}}
    _require({key: publication[key] for key in public_expected} == public_expected, "PUBLICATION_RECEIPT_BINDING")
    _require(publication["event_id"] != audit["event_id"], "CAUSAL_RECEIPT_ID_REUSED")
    try:
        publication_valid = receipt_verifier(publication, public_expected) is True
    except Exception:
        publication_valid = False
    _require(publication_valid, "PUBLICATION_RECEIPT_UNVERIFIED")
    return {"status": "AVAILABLE", "symbols": item["list"],
        **{key: item[key] for key in ("epoch", "session", "manifest_sha", "amendment_sha", "epoch_contract_sha256", "n_cut", "built_at",
             "cutoff_at", "decision_at", "list_sha256", "registry_sha256", "daily_contract_sha256", "calendar_sha256", "counts", "coverage")},
        "commitment_sha256": commitment_sha, "publication_at": payload["published_at"],
        "audit_receipt_sha256": digest(audit), "publication_receipt_sha256": digest(publication), "diagnostics": []}
