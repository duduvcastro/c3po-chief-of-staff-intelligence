"""Valuation — the earnings calendar the Decisor V1 reads (``EARNINGS_WITHIN_N``), in shadow.

* ``EarningsCalendarService.run`` — the nightly phase (``valuation_worker``, flag ``C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED``,
  default OFF): ONE EODHD ``/api/calendar/earnings`` call for the whole market window ``[today − 7 d, today + 30 d]`` (no
  symbol list: every exchange the provider carries), parsed by the R2D2 V2 parser
  (``r2d2_v2_earnings_source.parse_earnings_response`` — imported, never modified; it is not in the R2D2 V2 package
  fingerprint), stored as an append-only analysis snapshot ``valuation_earnings_calendar/EODHD_EARNINGS_CALENDAR`` dated
  by its ``received_at``, with the body's SHA-256. A failed call or an unusable body stores nothing: the phase fails
  (its ingestion run names why) and retries inside the window. The body itself is not kept — its hash and the parsed
  events (code, report date, fiscal period, BMO/AMC marker) are.
* ``calendar_at(database, at)`` — the latest snapshot received at or before ``at`` (causal), indexed by provider code.
* ``filings_known_at(database, at)`` — the fallback when the calendar is absent or stale: per US symbol, the latest
  8-K item 2.02 and the latest 10-Q/10-K (migration 051) accepted AND registered (``first_seen_at``) by ``at``.

Nothing here changes a served number or decides anything: the decisor applies its own thresholds.
"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .config import Settings
from .database import Database
from .r2d2_v2_earnings_source import EarningsInputError, EarningsReceipt, parse_earnings_response
from .sec_xbrl import FILING_SOURCE, MARKET as US_FILINGS_MARKET, RESULTS_FORMS, filing_items, is_trigger_filing
from .statement_vintages import StatementVintageStore, utc_instant

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_earnings_calendar"
ENTITY_KEY = "EODHD_EARNINGS_CALENDAR"
SCHEMA = "VALUATION_EARNINGS_CALENDAR_V1"
METHODOLOGY_KEY = "valuation_earnings_calendar"
METHODOLOGY_VERSION = 1
ENDPOINT = "/api/calendar/earnings"
WINDOW_BACK_DAYS = 7
WINDOW_AHEAD_DAYS = 30
USABLE_PARSE_STATUSES = ("OBSERVED", "OBSERVED_WITH_DIAGNOSTICS")
FILINGS_TABLE = "statement_filings"
FILINGS_LOOKBACK_DAYS = 400  # the fallback reads the filings accepted in the last 400 days (a quarter's cadence, four times over)


class EarningsCalendarError(RuntimeError):
    """Controlled message only: never the URL (it carries the token), never the body."""


def _utc(value: Any) -> datetime:
    return utc_instant(value)


def fetch_calendar(base_url: str, token: str, *, start: date, end: date, timeout: float, transport: httpx.BaseTransport | None = None,
                   clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[bytes, EarningsReceipt]:
    """ONE GET of the whole-market calendar for ``[start, end]``: the exact bytes and the receipt the parser validates
    (status, content type, the body's hash, the request and receipt instants)."""
    if not token.strip():
        raise EarningsCalendarError("EODHD token missing: the earnings calendar is not fetched")
    started = clock()
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True) as client:
            response = client.get(base_url.rstrip("/") + ENDPOINT,
                                  params={"from": start.isoformat(), "to": end.isoformat(), "api_token": token.strip(), "fmt": "json"})
            raw = response.content
    except httpx.HTTPError as error:
        raise EarningsCalendarError(f"earnings calendar request failed: {type(error).__name__}") from None
    received = clock()
    content_type = str(response.headers.get("content-type") or "")[:128].replace("\r", " ").replace("\n", " ")
    receipt = EarningsReceipt(request_symbols=(), request_from=start, request_to=end, request_started_at=started, response_received_at=received,
                              available_at=received, http_status=response.status_code, body_sha256=hashlib.sha256(raw).hexdigest(),
                              transport_complete=True, content_type=content_type)
    return raw, receipt


def calendar_outputs(raw: bytes, receipt: EarningsReceipt) -> dict[str, Any]:
    """The snapshot's outputs: the parsed events of a USABLE observation (``EarningsCalendarError`` otherwise)."""
    try:
        observation = parse_earnings_response(raw, receipt)
    except EarningsInputError as error:
        raise EarningsCalendarError(f"earnings calendar receipt refused: {error}") from None
    if observation.parse_status not in USABLE_PARSE_STATUSES:
        raise EarningsCalendarError(f"earnings calendar not usable: {observation.parse_status} {list(observation.diagnostics)}")
    events = [{"code": event.symbol, "report_date": event.report_date.isoformat(), "fiscal_period_end": event.fiscal_period_end.isoformat(),
               "timing": event.market_timing} for event in observation.events]
    blocking: dict[str, list[str]] = {}
    for item in observation.row_diagnostics:
        if item.blocking and item.symbol is not None:
            blocking.setdefault(item.symbol, [])
            if item.code not in blocking[item.symbol]:
                blocking[item.symbol].append(item.code)
    by_exchange: dict[str, int] = {}
    for event in events:
        suffix = str(event["code"]).rsplit(".", 1)[-1]
        by_exchange[suffix] = by_exchange.get(suffix, 0) + 1
    summary = observation.public_summary()
    return {"schema": SCHEMA, "provider": "eodhd", "endpoint": ENDPOINT,
            "request": {"from": receipt.request_from.isoformat(), "to": receipt.request_to.isoformat()},
            "request_started_at": _utc(receipt.request_started_at).isoformat(), "received_at": _utc(receipt.response_received_at).isoformat(),
            "http_status": receipt.http_status, "payload_sha256": receipt.body_sha256, "receipt_sha256": summary["receipt_sha256"],
            "parse_status": observation.parse_status, "diagnostics": list(observation.diagnostics), "events": events,
            "blocking_codes": blocking, "unattributed_invalid_rows": summary["unattributed_invalid_row_count"],
            "counts": {"events": len(events), "by_exchange": dict(sorted(by_exchange.items()))}}


def record_calendar(database: Database, raw: bytes, receipt: EarningsReceipt) -> str:
    """Parse and store one calendar observation as an append-only snapshot dated by its receipt (``published_at`` =
    ``received_at``); nothing is stored for an unusable one."""
    outputs = calendar_outputs(raw, receipt)
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY, METHODOLOGY_VERSION,
        {"endpoint": ENDPOINT, "window_days": [-WINDOW_BACK_DAYS, WINDOW_AHEAD_DAYS], "parser": "r2d2_v2_earnings_source.parse_earnings_response",
         "schema": SCHEMA},
        "The whole-market earnings calendar (EODHD) as received each night; read causally by the Decisor V1 (EARNINGS_WITHIN_N).",
    )
    return database.save_analysis_snapshot(ANALYSIS_TYPE, ENTITY_KEY, methodology_id,
                                           {"schema": SCHEMA, "endpoint": ENDPOINT, "request": outputs["request"]}, outputs,
                                           _utc(receipt.response_received_at))


class EarningsCalendarService:
    """The nightly phase: one call, one snapshot. ``transport`` and ``clock`` are for tests (no network there)."""

    def __init__(self, settings: Settings, database: Database, *, transport: httpx.BaseTransport | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self.settings, self.database, self.transport, self.clock = settings, database, transport, clock

    def run(self) -> dict[str, Any]:
        today = self.clock().astimezone(timezone.utc).date()
        raw, receipt = fetch_calendar(self.settings.eodhd_base_url, self.settings.eodhd_api_token, start=today - timedelta(days=WINDOW_BACK_DAYS),
                                      end=today + timedelta(days=WINDOW_AHEAD_DAYS), timeout=self.settings.market_data_timeout_seconds,
                                      transport=self.transport, clock=self.clock)
        snapshot_id = record_calendar(self.database, raw, receipt)
        stored = self.database.analysis_snapshot_at_or_before(ANALYSIS_TYPE, ENTITY_KEY, _utc(receipt.response_received_at))
        counts = ((stored or {}).get("outputs") or {}).get("counts") or {}
        return {"snapshot_id": snapshot_id, "events": counts.get("events", 0), "by_exchange": counts.get("by_exchange", {})}

    def last_run_at(self) -> datetime | None:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, ENTITY_KEY)
        return _utc(snapshot["published_at"]) if snapshot and snapshot.get("published_at") else None


# -- causal readers (the decisor's) ------------------------------------------------------------------------------------

def calendar_at(database: Database, at: datetime) -> dict[str, Any]:
    """The latest calendar snapshot RECEIVED at or before ``at`` (``published_at`` = its receipt), indexed by provider
    code — ``{"status": "ok", "snapshot_id", "received_at", "payload_sha256", "request_from", "request_to", "by_code",
    "blocking_codes", "unattributed_invalid_rows"}`` — or ``{"status": "absent"}``. A snapshot received later never
    reaches an earlier decision."""
    snapshot = database.analysis_snapshot_at_or_before(ANALYSIS_TYPE, ENTITY_KEY, _utc(at))
    outputs = snapshot.get("outputs") if snapshot and isinstance(snapshot.get("outputs"), Mapping) else None
    if not snapshot or not outputs or outputs.get("schema") != SCHEMA:
        return {"status": "absent"}
    by_code: dict[str, list[dict[str, Any]]] = {}
    for event in outputs.get("events") or []:
        if isinstance(event, Mapping) and event.get("code"):
            by_code.setdefault(str(event["code"]), []).append(dict(event))
    request = outputs.get("request") if isinstance(outputs.get("request"), Mapping) else {}
    blocking = outputs.get("blocking_codes") if isinstance(outputs.get("blocking_codes"), Mapping) else {}
    return {"status": "ok", "snapshot_id": str(snapshot["id"]), "received_at": _utc(snapshot["published_at"]).isoformat(),
            "payload_sha256": outputs.get("payload_sha256"), "request_from": request.get("from"), "request_to": request.get("to"),
            "by_code": by_code, "blocking_codes": {str(key): list(value or []) for key, value in blocking.items()},
            "unattributed_invalid_rows": outputs.get("unattributed_invalid_rows")}


def _filings_present(database: Database) -> bool:
    if not database.database_url:
        return isinstance(getattr(database, "_statement_filings", None), list)
    with database.connection() as connection:
        found = connection.execute("SELECT to_regclass(%s)::text", (FILINGS_TABLE,)).fetchone()
    return bool(found and found[0])


def _reference(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"doc_id": str(row["doc_id"]), "form": str(row["form"]), "items": str(row.get("items") or ""),
            "accepted_at": _utc(row["accepted_at"]).isoformat()}


def filings_known_at(database: Database, at: datetime) -> dict[str, Any]:
    """The fallback of the earnings rule: per US symbol (``statement_filings.symbols``), the latest earnings release
    (8-K/8-K/A item 2.02, ``release``) and the latest 10-Q/10-K or amendment (``statement``) accepted in the last
    ``FILINGS_LOOKBACK_DAYS`` and KNOWN at ``at`` — accepted AND registered (``first_seen_at``) by then, so a backfill
    never reaches an earlier night. ``{"status": "ok", "latest": {symbol: {"release", "statement"}}}`` or
    ``{"status": "absent"}`` (migration 051 not applied)."""
    clock = _utc(at)
    if not _filings_present(database):
        return {"status": "absent"}
    rows = StatementVintageStore(database).filings(US_FILINGS_MARKET, source=FILING_SOURCE, accepted_since=clock - timedelta(days=FILINGS_LOOKBACK_DAYS))
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:  # oldest acceptance first: a later one overrides
        seen = row.get("first_seen_at")
        if _utc(row["accepted_at"]) > clock or seen is None or _utc(seen) > clock:
            continue
        form, items = str(row["form"]), filing_items(row.get("items"))
        if not is_trigger_filing(form, items):
            continue
        slot = "statement" if form in RESULTS_FORMS else "release"
        for symbol in row.get("symbols") or ():
            latest.setdefault(str(symbol).strip().upper(), {"release": None, "statement": None})[slot] = _reference(row)
    return {"status": "ok", "latest": latest}
