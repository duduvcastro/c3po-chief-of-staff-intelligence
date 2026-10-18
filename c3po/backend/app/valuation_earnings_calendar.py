"""Valuation — the earnings calendar the Decisor V1 reads (``EARNINGS_WITHIN_N``), in shadow.

* ``EarningsCalendarService.run`` — the nightly phase (``valuation_worker``, flag ``C3PO_VALUATION_EARNINGS_CALENDAR_ENABLED``,
  default OFF; advisory: its failure never pages, at most ``MAX_FAILURES_PER_NIGHT`` attempts): ONE EODHD
  ``/api/calendar/earnings`` call for the whole market window ``[today − 7 d, today + 30 d]`` (no symbol list: every
  exchange the provider carries), streamed with a byte cap (the parser's ``MAX_BODY_BYTES``) and an overall deadline,
  parsed by the R2D2 V2 parser (``r2d2_v2_earnings_source.parse_earnings_response`` — imported, never modified; it is not
  in the R2D2 V2 package fingerprint), stored as an append-only analysis snapshot
  ``valuation_earnings_calendar/EODHD_EARNINGS_CALENDAR`` dated by its ``received_at``, with the body's SHA-256. A failed
  call or an unusable body stores nothing: the phase fails (its ingestion run names why). The body itself is not kept —
  its hash, the parsed events (code, report date, fiscal period, BMO/AMC marker) and the row counts are.
* ``calendars_at(database, at, ...)`` — every snapshot received in the decisor's window and the latest one before it,
  each with what the decisor needs to judge it (US events in the requested window, invalid rows, coverage).
* ``filings_known_at(database, at, ...)`` — the fallback: per US symbol, the ORIGINAL 8-K item 2.02 and 10-Q/10-K
  (migration 051; amendments excluded) accepted AND registered (``first_seen_at``) by the decisor's clock.

Nothing here changes a served number or decides anything: the decisor applies its own thresholds.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .config import Settings
from .database import Database
from .r2d2_v2_earnings_source import MAX_BODY_BYTES, EarningsInputError, EarningsReceipt, parse_earnings_response
from .sec_xbrl import EARNINGS_RELEASE_ITEM, FILING_SOURCE, MARKET as US_FILINGS_MARKET, filing_items
from .statement_vintages import StatementVintageStore, as_date, utc_instant

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_earnings_calendar"
ENTITY_KEY = "EODHD_EARNINGS_CALENDAR"
SCHEMA = "VALUATION_EARNINGS_CALENDAR_V1"
METHODOLOGY_KEY = "valuation_earnings_calendar"
METHODOLOGY_VERSION = 1
ENDPOINT = "/api/calendar/earnings"
WINDOW_BACK_DAYS = 7
WINDOW_AHEAD_DAYS = 30
DOWNLOAD_DEADLINE_SECONDS = 180.0  # the whole call, connection to last byte; a slower answer is a failed attempt
MAX_FAILURES_PER_NIGHT = 3  # the phase's retry cap (valuation_worker: an advisory phase)
USABLE_PARSE_STATUSES = ("OBSERVED", "OBSERVED_WITH_DIAGNOSTICS")
FILINGS_TABLE = "statement_filings"
ESTIMATE_FORMS = ("10-Q", "10-K", "8-K")  # originals only: an amendment re-files a period, it announces nothing


class EarningsCalendarError(RuntimeError):
    """Controlled message only: never the URL (it carries the token), never the body."""


def _utc(value: Any) -> datetime:
    return utc_instant(value)


def fetch_calendar(base_url: str, token: str, *, start: date, end: date, timeout: float, transport: httpx.BaseTransport | None = None,
                   clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), deadline_seconds: float = DOWNLOAD_DEADLINE_SECONDS,
                   max_bytes: int = MAX_BODY_BYTES, monotonic: Callable[[], float] = time.monotonic) -> tuple[bytes, EarningsReceipt]:
    """ONE streamed GET of the whole-market calendar for ``[start, end]``: the exact bytes and the receipt the parser
    validates (status, content type, the body's hash, the request and receipt instants). A body over ``max_bytes`` or a
    call past ``deadline_seconds`` is refused; no error message carries the URL (it holds the token)."""
    if not token.strip():
        raise EarningsCalendarError("EODHD token missing: the earnings calendar is not fetched")
    started, began = clock(), monotonic()
    chunks: list[bytes] = []
    size = 0
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True) as client:
            with client.stream("GET", base_url.rstrip("/") + ENDPOINT,
                               params={"from": start.isoformat(), "to": end.isoformat(), "api_token": token.strip(), "fmt": "json"}) as response:
                status = response.status_code
                content_type = str(response.headers.get("content-type") or "")[:128].replace("\r", " ").replace("\n", " ")
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise EarningsCalendarError(f"earnings calendar body exceeds {max_bytes} bytes")
                    if monotonic() - began > deadline_seconds:
                        raise EarningsCalendarError(f"earnings calendar download exceeded {deadline_seconds:.0f} s")
                    chunks.append(chunk)
    except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError, ValueError) as error:  # never the URL (it carries the token): a malformed
        # base URL surfaces as InvalidURL or as a ValueError that quotes it
        raise EarningsCalendarError(f"earnings calendar request failed: {type(error).__name__}") from None
    if monotonic() - began > deadline_seconds:
        raise EarningsCalendarError(f"earnings calendar download exceeded {deadline_seconds:.0f} s")
    raw = b"".join(chunks)
    received = clock()
    receipt = EarningsReceipt(request_symbols=(), request_from=start, request_to=end, request_started_at=started, response_received_at=received,
                              available_at=received, http_status=status, body_sha256=hashlib.sha256(raw).hexdigest(),
                              transport_complete=True, content_type=content_type)
    return raw, receipt


def calendar_outputs(raw: bytes, receipt: EarningsReceipt) -> dict[str, Any]:
    """The snapshot's outputs: the parsed events of a USABLE observation (``EarningsCalendarError`` otherwise) and the
    row counts the decisor judges a calendar by (``rows``, ``invalid_rows``, ``unattributed_invalid_rows``)."""
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
    invalid_rows = len({item.row_index for item in observation.row_diagnostics if item.blocking})
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
            "blocking_codes": blocking, "rows": len(events) + invalid_rows, "invalid_rows": invalid_rows,
            "unattributed_invalid_rows": summary["unattributed_invalid_row_count"],
            "counts": {"events": len(events), "by_exchange": dict(sorted(by_exchange.items()))}}


def record_calendar(database: Database, raw: bytes, receipt: EarningsReceipt) -> str:
    """Parse and store one calendar observation as an append-only snapshot dated by its receipt (``published_at`` =
    ``received_at``); nothing is stored for an unusable one."""
    return _store(database, calendar_outputs(raw, receipt), receipt)


def _store(database: Database, outputs: Mapping[str, Any], receipt: EarningsReceipt) -> str:
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY, METHODOLOGY_VERSION,
        {"endpoint": ENDPOINT, "window_days": [-WINDOW_BACK_DAYS, WINDOW_AHEAD_DAYS], "parser": "r2d2_v2_earnings_source.parse_earnings_response",
         "schema": SCHEMA},
        "The whole-market earnings calendar (EODHD) as received each night; read causally by the Decisor V1 (EARNINGS_WITHIN_N).",
    )
    return database.save_analysis_snapshot(ANALYSIS_TYPE, ENTITY_KEY, methodology_id,
                                           {"schema": SCHEMA, "endpoint": ENDPOINT, "request": outputs["request"]}, dict(outputs),
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
        outputs = calendar_outputs(raw, receipt)
        snapshot_id = _store(self.database, outputs, receipt)
        return {"snapshot_id": snapshot_id, "events": outputs["counts"]["events"], "by_exchange": outputs["counts"]["by_exchange"]}

    def last_run_at(self) -> datetime | None:
        """The phase's ``last_completed_at``: the latest snapshot's receipt — the clock only (read on every worker wake)."""
        published = self.database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, ENTITY_KEY)
        return _utc(published) if published is not None else None


# -- causal readers (the decisor's) ------------------------------------------------------------------------------------

def _parsed(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """One stored calendar as the decisor judges it: identity, request window, events by provider code, the names with an
    invalid row, the count of US events inside the request window and the share of unattributed invalid rows."""
    outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), Mapping) else None
    if not outputs or outputs.get("schema") != SCHEMA:
        return None
    request = outputs.get("request") if isinstance(outputs.get("request"), Mapping) else {}
    start, end = str(request.get("from") or ""), str(request.get("to") or "")
    by_code: dict[str, list[dict[str, Any]]] = {}
    us_events = 0
    for event in outputs.get("events") or []:
        if isinstance(event, Mapping) and event.get("code"):
            by_code.setdefault(str(event["code"]), []).append(dict(event))
            if str(event["code"]).endswith(".US") and start <= str(event.get("report_date") or "") <= end:
                us_events += 1
    blocking = outputs.get("blocking_codes") if isinstance(outputs.get("blocking_codes"), Mapping) else {}
    unattributed = int(outputs.get("unattributed_invalid_rows") or 0)
    rows = int(outputs.get("rows") or 0) or (sum(len(items) for items in by_code.values()) + int(outputs.get("invalid_rows") or unattributed))
    return {"snapshot_id": str(snapshot["id"]), "received_at": _utc(snapshot["published_at"]).isoformat(), "payload_sha256": outputs.get("payload_sha256"),
            "request_from": start or None, "request_to": end or None, "by_code": by_code,
            "blocking_codes": {str(key): list(value or []) for key, value in blocking.items()}, "us_events": us_events, "rows": rows,
            "unattributed_invalid_rows": unattributed, "invalid_share": (unattributed / rows) if rows else 1.0}


def calendars_at(database: Database, at: datetime, *, recent_hours: int, margin_seconds: int) -> dict[str, Any]:
    """The calendars a decision at ``at`` may read: every snapshot RECEIVED in [``at`` − ``recent_hours``, ``at`` − margin]
    (``recent``, oldest first) and the latest one received by ``at`` − margin whatever its age (``latest``) — a snapshot
    inserted later, or received inside the last ``margin_seconds``, never reaches the decision."""
    cutoff = _utc(at) - timedelta(seconds=margin_seconds)
    since = _utc(at) - timedelta(hours=recent_hours)
    recent = [parsed for snapshot in database.analysis_snapshots_published_between(ANALYSIS_TYPE, ENTITY_KEY, since, cutoff)
              if (parsed := _parsed(snapshot)) is not None]
    latest_snapshot = database.analysis_snapshot_at_or_before(ANALYSIS_TYPE, ENTITY_KEY, cutoff)
    latest = _parsed(latest_snapshot) if latest_snapshot else None
    return {"known_at": cutoff.isoformat(), "recent_hours": recent_hours, "recent": recent, "latest": latest}


def _filings_present(database: Database) -> bool:
    if not database.database_url:
        return isinstance(getattr(database, "_statement_filings", None), list)
    with database.connection() as connection:
        found = connection.execute("SELECT to_regclass(%s)::text", (FILINGS_TABLE,)).fetchone()
    return bool(found and found[0])


def filings_known_at(database: Database, at: datetime, *, lookback_days: int, margin_seconds: int) -> dict[str, Any]:
    """The fallback of the earnings rule: per US symbol (``statement_filings.symbols``), its ORIGINAL earnings filings —
    8-K item 2.02, 10-Q, 10-K; amendments excluded — accepted in the last ``lookback_days`` and KNOWN at ``at``: accepted
    by then AND registered (``first_seen_at``, an insert clock) by ``at`` − margin, so a backfill never reaches an earlier
    night. ``{"status": "ok", "by_symbol": {symbol: [filing, …]}}`` oldest acceptance first, or ``{"status": "absent"}``
    (migration 051 not applied)."""
    clock = _utc(at)
    seen_by = clock - timedelta(seconds=margin_seconds)
    if not _filings_present(database):
        return {"status": "absent"}
    rows = StatementVintageStore(database).filings(US_FILINGS_MARKET, source=FILING_SOURCE, accepted_since=clock - timedelta(days=lookback_days))
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:  # oldest acceptance first
        seen = row.get("first_seen_at")
        if _utc(row["accepted_at"]) > clock or seen is None or _utc(seen) > seen_by:
            continue
        form, items = str(row["form"]), filing_items(row.get("items"))
        if form not in ESTIMATE_FORMS or (form == "8-K" and EARNINGS_RELEASE_ITEM not in items):
            continue
        try:
            period = as_date(row.get("period_of_report"))
        except ValueError:
            period = None
        reference = {"doc_id": str(row["doc_id"]), "form": form, "items": ",".join(items), "accepted_at": _utc(row["accepted_at"]).isoformat(),
                     "period_of_report": period.isoformat() if period else None}
        for symbol in row.get("symbols") or ():
            by_symbol.setdefault(str(symbol).strip().upper(), []).append(reference)
    return {"status": "ok", "by_symbol": by_symbol}
