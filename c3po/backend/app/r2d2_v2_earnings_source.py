"""Pure earnings parsing and a coverage-verification boundary, without feed access.

Dates and market-timing labels are retained; they never become event timestamps.
The optional verifier is an independently audited dependency, not implemented
here. A caller's HTTP success, boolean or checksum cannot replace that verifier.
No file, database, provider, application settings or wall clock is accessed.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Protocol

OBSERVATION_SCHEMA = "R2D2_V2_EARNINGS_OBSERVATION_V2"
COVERAGE_SCHEMA = "R2D2_V2_EARNINGS_COVERAGE_V1"
MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
MAX_BODY_BYTES = 64 * 1024 * 1024
COVERAGE_SCOPE = "ALL_KNOWN_ANNOUNCEMENTS_FOR_SYMBOL_AND_WINDOW"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,47}\.[A-Z][A-Z0-9]{0,7}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class EarningsInputError(ValueError):
    """Controlled code only; input, provider errors and credentials are omitted."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EarningsInputError(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _symbol(value: Any) -> bool:
    return isinstance(value, str) and _SYMBOL.fullmatch(value) is not None


def _utc(value: datetime) -> datetime:
    _require(isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None, "CLOCK_NOT_AWARE")
    return value.astimezone(timezone.utc)


def _day(value: Any) -> date:
    _require(isinstance(value, str), "DATE_INVALID")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise EarningsInputError("DATE_INVALID") from None
    _require(parsed.isoformat() == value, "DATE_NOT_CANONICAL")
    return parsed


@dataclass(frozen=True)
class EarningsReceipt:
    """Private factual receipt. Complete refers only to receiving the HTTP body."""

    request_symbols: tuple[str, ...] = field(repr=False)
    request_from: date
    request_to: date
    request_started_at: datetime
    response_received_at: datetime
    available_at: datetime
    http_status: int
    body_sha256: str
    transport_complete: bool
    content_type: str = field(repr=False)

    def to_private_dict(self) -> dict[str, Any]:
        return {"endpoint": "/api/calendar/earnings", "fmt": "json",
                "request_symbols": list(self.request_symbols), "request_from": self.request_from.isoformat(),
                "request_to": self.request_to.isoformat(), "request_started_at": _utc(self.request_started_at).isoformat(),
                "response_received_at": _utc(self.response_received_at).isoformat(),
                "available_at": _utc(self.available_at).isoformat(), "http_status": self.http_status,
                "body_sha256": self.body_sha256, "transport_complete": self.transport_complete,
                "content_type": self.content_type}


def _validate_receipt(receipt: EarningsReceipt, raw: bytes) -> None:
    _require(isinstance(receipt, EarningsReceipt), "RECEIPT_TYPE")
    _require(type(raw) is bytes and len(raw) <= MAX_BODY_BYTES, "BODY_TYPE_OR_SIZE")
    _require(type(receipt.request_symbols) is tuple and all(_symbol(s) for s in receipt.request_symbols)
             and len(set(receipt.request_symbols)) == len(receipt.request_symbols), "REQUEST_SYMBOLS_INVALID")
    _require(type(receipt.request_from) is date and type(receipt.request_to) is date
             and receipt.request_from <= receipt.request_to, "REQUEST_WINDOW_INVALID")
    _require(_utc(receipt.request_started_at) <= _utc(receipt.response_received_at) <= _utc(receipt.available_at), "RECEIPT_CLOCK_ORDER")
    _require(type(receipt.http_status) is int and 100 <= receipt.http_status <= 599, "HTTP_STATUS_INVALID")
    _require(type(receipt.transport_complete) is bool, "TRANSPORT_COMPLETE_INVALID")
    _require(isinstance(receipt.content_type, str) and len(receipt.content_type) <= 128
             and "\n" not in receipt.content_type and "\r" not in receipt.content_type, "CONTENT_TYPE_INVALID")
    _require(_hash(receipt.body_sha256) and _sha(raw) == receipt.body_sha256, "BODY_HASH_MISMATCH")


@dataclass(frozen=True)
class EarningsEvent:
    symbol: str = field(repr=False)
    report_date: date
    fiscal_period_end: date
    market_timing: str | None
    raw_record: bytes = field(repr=False)

    def to_private_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "report_date": self.report_date.isoformat(),
                "fiscal_period_end": self.fiscal_period_end.isoformat(), "market_timing": self.market_timing,
                "granularity": "DATE_AND_MARKET_TIMING" if self.market_timing else "DATE",
                "event_at": None, "timezone": None, "provider_announced_at": None,
                "provider_updated_at": None, "announcement_status": None,
                "raw_record": json.loads(self.raw_record)}


@dataclass(frozen=True)
class EarningsRowDiagnostic:
    row_index: int
    symbol: str | None = field(repr=False)
    code: str
    blocking: bool

    def to_private_dict(self) -> dict[str, Any]:
        return {"row_index": self.row_index, "symbol": self.symbol,
                "code": self.code, "blocking": self.blocking}


@dataclass(frozen=True)
class EarningsObservation:
    receipt: EarningsReceipt = field(repr=False)
    raw_body: bytes = field(repr=False)
    events: tuple[EarningsEvent, ...] = field(repr=False)
    parse_status: str
    diagnostics: tuple[str, ...]
    row_diagnostics: tuple[EarningsRowDiagnostic, ...] = field(default=(), repr=False)

    def blocking_diagnostics_for(self, symbol: str) -> tuple[str, ...]:
        # An invalid row with no trustworthy identity cannot be assigned to a
        # different name. Preserve that uncertainty without invalidating JSON.
        return tuple(dict.fromkeys(item.code for item in self.row_diagnostics
                                   if item.blocking and item.symbol in (None, symbol)))

    def status_for_symbol(self, symbol: str) -> str:
        _require(_symbol(symbol), "ASSESSMENT_SYMBOL_INVALID")
        if self.parse_status not in ("OBSERVED", "OBSERVED_WITH_DIAGNOSTICS"):
            return self.parse_status
        return "INVALID_ROWS" if self.blocking_diagnostics_for(symbol) else "OBSERVED"

    @property
    def receipt_sha256(self) -> str:
        return _sha(_canonical(self.receipt.to_private_dict()))

    def public_summary(self) -> dict[str, Any]:
        return {"schema": OBSERVATION_SCHEMA, "manifest_sha": MANIFEST_SHA, "amendment_sha": AMENDMENT_SHA,
                "body_sha256": self.receipt.body_sha256, "receipt_sha256": self.receipt_sha256,
                "http_status": self.receipt.http_status, "transport_complete": self.receipt.transport_complete,
                "parse_status": self.parse_status, "diagnostics": list(self.diagnostics),
                "row_diagnostic_count": len(self.row_diagnostics),
                "unattributed_invalid_row_count": len({item.row_index for item in self.row_diagnostics
                    if item.blocking and item.symbol is None}),
                "requested_symbol_count": len(self.receipt.request_symbols), "event_count": len(self.events),
                "timing_counts": {str(k): sum(e.market_timing == k for e in self.events)
                                  for k in ("BeforeMarket", "AfterMarket", None)},
                "response_received_at": _utc(self.receipt.response_received_at).isoformat(),
                "available_at": _utc(self.receipt.available_at).isoformat(),
                "feed_coverage": "UNKNOWN", "production_ready": False}

    def to_private_dict(self) -> dict[str, Any]:
        return {**self.public_summary(), "receipt": self.receipt.to_private_dict(),
                "raw_body_base64": base64.b64encode(self.raw_body).decode("ascii"),
                "row_diagnostics": [item.to_private_dict() for item in self.row_diagnostics],
                "events": [event.to_private_dict() for event in self.events]}


def _load(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(EarningsInputError("JSON_NONFINITE")))
    except EarningsInputError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise EarningsInputError("JSON_MALFORMED") from None
    _require(isinstance(value, dict), "RESPONSE_NOT_OBJECT")
    return value


def _event(row: Any) -> EarningsEvent:
    _require(isinstance(row, dict), "EVENT_NOT_OBJECT")
    _require({"code", "report_date", "date", "currency"} <= set(row), "EVENT_FIELDS_INVALID")
    _require(_symbol(row["code"]), "EVENT_SYMBOL_INVALID")
    timing = row.get("before_after_market")
    _require(timing is None or timing in ("BeforeMarket", "AfterMarket"), "EVENT_TIMING_INVALID")
    currency = row["currency"]
    _require(currency is None or (isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency) is not None), "EVENT_CURRENCY_INVALID")
    for key in ("actual", "estimate", "difference", "percent"):
        value = row.get(key)
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        _require(value is None or finite, "EVENT_NUMBER_INVALID")
    report_date, fiscal_period_end = _day(row["report_date"]), _day(row["date"])
    try:
        record = _canonical(row)
    except (ValueError, OverflowError, RecursionError):
        # JSON exponent overflow in an unknown extension can parse to inf.
        # Keep the original body and localize the error to this row/symbol.
        raise EarningsInputError("EVENT_VALUE_UNREPRESENTABLE") from None
    return EarningsEvent(row["code"], report_date, fiscal_period_end, timing, record)


def parse_earnings_response(raw: bytes, receipt: EarningsReceipt) -> EarningsObservation:
    """Parse supplied bytes once, preserving failed bodies privately, never as []."""
    _validate_receipt(receipt, raw)
    def result(status: str, reasons: tuple[str, ...], events: tuple[EarningsEvent, ...] = (),
               rows: tuple[EarningsRowDiagnostic, ...] = ()) -> EarningsObservation:
        return EarningsObservation(receipt, raw, events, status, reasons, rows)
    if not receipt.transport_complete:
        return result("INCOMPLETE_TRANSPORT", ("TRANSPORT_INCOMPLETE",))
    if receipt.http_status != 200:
        return result("HTTP_ERROR", ("HTTP_NOT_200",))
    if receipt.content_type.split(";", 1)[0].strip().lower() != "application/json":
        return result("INVALID_BODY", ("CONTENT_TYPE_NOT_JSON",))
    events: list[EarningsEvent] = []
    try:
        body = _load(raw)
        _require(set(body) <= {"type", "description", "from", "to", "symbols", "earnings"}
                 and body.get("type") == "Earnings" and isinstance(body.get("earnings"), list), "RESPONSE_FIELDS_INVALID")
        _require("description" not in body or isinstance(body["description"], str), "RESPONSE_DESCRIPTION_INVALID")
        for key, expected in (("from", receipt.request_from), ("to", receipt.request_to)):
            if key in body:
                _require(_day(body[key]) == expected, "RESPONSE_WINDOW_MISMATCH")
        if "symbols" in body:
            _require(isinstance(body["symbols"], str), "RESPONSE_SYMBOLS_INVALID")
            echoed = body["symbols"].split(",") if body["symbols"] else []
            _require(len(set(echoed)) == len(echoed) and set(echoed) == set(receipt.request_symbols), "RESPONSE_SYMBOLS_MISMATCH")
    except EarningsInputError as exc:
        return result("INVALID_BODY", (str(exc),))
    row_diagnostics: list[EarningsRowDiagnostic] = []
    identities: set[tuple[str, date]] = set()
    allowed = {"code", "report_date", "date", "before_after_market", "currency", "actual", "estimate", "difference", "percent"}
    for index, row in enumerate(body["earnings"]):
        symbol = row.get("code") if isinstance(row, dict) and _symbol(row.get("code")) else None
        def diagnostic(code: str, *, blocking: bool = False) -> None:
            row_diagnostics.append(EarningsRowDiagnostic(index, symbol, code, blocking))
        if isinstance(row, dict) and set(row) - allowed:
            diagnostic("EVENT_UNKNOWN_FIELDS")
        try:
            event = _event(row)
            events.append(event)
            if receipt.request_symbols and event.symbol not in receipt.request_symbols:
                diagnostic("EVENT_UNREQUESTED_SYMBOL")
            if not receipt.request_from <= event.report_date <= receipt.request_to:
                diagnostic("EVENT_OUTSIDE_REQUEST_WINDOW")
            identity = (event.symbol, event.fiscal_period_end)
            if identity in identities:
                diagnostic("EVENT_DUPLICATE_FISCAL_PERIOD")
            # Keep every observed date/timing revision. Consumers must apply
            # the conservative union, never select a permissive last row.
            identities.add(identity)
        except EarningsInputError as exc:
            diagnostic(str(exc), blocking=True)
    diagnostics = tuple(dict.fromkeys(item.code for item in row_diagnostics))
    return result("OBSERVED_WITH_DIAGNOSTICS" if diagnostics else "OBSERVED",
                  diagnostics, tuple(events), tuple(row_diagnostics))


@dataclass(frozen=True)
class CoverageEvidence:
    """Untrusted reference until checked against independently held evidence."""

    attestation_id: str = field(repr=False)
    issuer: str = field(repr=False)
    contract_sha256: str
    evidence_sha256: str
    observation_body_sha256: str
    observation_receipt_sha256: str
    symbol: str = field(repr=False)
    window_start: datetime
    window_end: datetime
    known_as_of: datetime
    published_at: datetime
    scope: str = COVERAGE_SCOPE


@dataclass(frozen=True)
class CoverageExpectation:
    schema: str
    manifest_sha: str
    amendment_sha: str
    observation_body_sha256: str
    observation_receipt_sha256: str
    symbol: str = field(repr=False)
    request_symbols: tuple[str, ...] = field(repr=False)
    request_from: date
    request_to: date
    decision_at: datetime
    maturity_at: datetime
    response_received_at: datetime
    observation_available_at: datetime
    scope: str = COVERAGE_SCOPE


class CoverageVerifier(Protocol):
    """Trusted hook: independently verify authority, scope, clocks and bindings.

    Implementations must be separately audited; no feed-completeness verifier is
    provided here. Comparing an input hash with itself does not implement this.
    """

    def __call__(self, evidence: CoverageEvidence, expected: CoverageExpectation) -> bool: ...


@dataclass(frozen=True)
class EarningsAssessment:
    feed_coverage: str
    diagnostics: tuple[str, ...]
    port_temporal_fields_complete: bool
    observed_event_count: int
    expectation: CoverageExpectation = field(repr=False)
    evidence: CoverageEvidence | None = field(repr=False)

    def public_summary(self) -> dict[str, Any]:
        return {"schema": COVERAGE_SCHEMA, "feed_coverage": self.feed_coverage,
                "diagnostics": list(self.diagnostics), "port_temporal_fields_complete": self.port_temporal_fields_complete,
                "observed_event_count": self.observed_event_count,
                "body_sha256": self.expectation.observation_body_sha256,
                "receipt_sha256": self.expectation.observation_receipt_sha256,
                "decision_at": self.expectation.decision_at.isoformat(), "maturity_at": self.expectation.maturity_at.isoformat(),
                "production_ready": False, "port_payload_emitted": False}


def assess_earnings_coverage(observation: EarningsObservation, *, symbol: str,
                             decision_at: datetime, maturity_at: datetime,
                             evidence: CoverageEvidence | None = None,
                             verifier: CoverageVerifier | None = None) -> EarningsAssessment:
    """Assess one symbol, not the whole request. No verifier means UNKNOWN.

    Parser-produced immutable objects are expected; this is not an untrusted
    object deserializer. The hook is the only injected dependency and must be
    read-only. This module performs no external lookup itself.
    """
    _require(isinstance(observation, EarningsObservation), "OBSERVATION_TYPE")
    _require(_symbol(symbol), "ASSESSMENT_SYMBOL_INVALID")
    decision, maturity = _utc(decision_at), _utc(maturity_at)
    _require(decision <= maturity, "ASSESSMENT_WINDOW_INVALID")
    receipt = observation.receipt
    # The parser validated the immutable bytes once. A batch assessed for many
    # symbols must not hash the entire response again for each symbol.
    expected = CoverageExpectation(COVERAGE_SCHEMA, MANIFEST_SHA, AMENDMENT_SHA, receipt.body_sha256,
        observation.receipt_sha256, symbol, receipt.request_symbols, receipt.request_from, receipt.request_to,
        decision, maturity, _utc(receipt.response_received_at), _utc(receipt.available_at))
    reasons = list(observation.blocking_diagnostics_for(symbol))
    if observation.parse_status not in ("OBSERVED", "OBSERVED_WITH_DIAGNOSTICS"):
        reasons.extend(observation.diagnostics)
        reasons.append("OBSERVATION_NOT_VALID")
    if receipt.request_symbols and symbol not in receipt.request_symbols:
        reasons.append("SYMBOL_NOT_REQUESTED")
    if _utc(receipt.available_at) > decision:
        reasons.append("OBSERVATION_NOT_CAUSAL")
    if evidence is None:
        reasons.append("COVERAGE_EVIDENCE_MISSING")
    if verifier is None:
        reasons.append("COVERAGE_VERIFIER_MISSING")
    if evidence is not None:
        try:
            _require(isinstance(evidence, CoverageEvidence), "COVERAGE_EVIDENCE_INVALID")
            _require(all(isinstance(v, str) and _TOKEN.fullmatch(v) is not None for v in (evidence.attestation_id, evidence.issuer))
                     and _hash(evidence.contract_sha256) and _hash(evidence.evidence_sha256), "COVERAGE_EVIDENCE_INVALID")
            _require(evidence.scope == COVERAGE_SCOPE and evidence.symbol == symbol
                     and evidence.observation_body_sha256 == expected.observation_body_sha256
                     and evidence.observation_receipt_sha256 == expected.observation_receipt_sha256, "COVERAGE_BINDING_MISMATCH")
            _require(_utc(evidence.window_start) <= decision <= maturity <= _utc(evidence.window_end), "COVERAGE_WINDOW_INSUFFICIENT")
            _require(_utc(evidence.known_as_of) <= expected.response_received_at <= _utc(evidence.published_at) <= decision,
                     "COVERAGE_CLOCK_ORDER")
        except EarningsInputError as exc:
            reasons.append(str(exc))
    verified = False
    if not reasons and evidence is not None and verifier is not None:
        try:
            verified = verifier(evidence, expected) is True
            if not verified:
                reasons.append("COVERAGE_EXTERNAL_VERIFICATION_FAILED")
        except Exception:
            reasons.append("COVERAGE_EXTERNAL_VERIFIER_ERROR")
    events = tuple(event for event in observation.events if event.symbol == symbol)
    # Independent completeness does not upgrade day/BMO/AMC into precise clocks.
    if events:
        reasons.append("EVENT_PRECISE_TIME_UNAVAILABLE")
    return EarningsAssessment("VERIFIED" if verified else "UNKNOWN", tuple(dict.fromkeys(reasons)),
                              verified and not events, len(events), expected, evidence)
