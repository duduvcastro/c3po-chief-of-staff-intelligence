"""The persisted daily price series of the Valuation Engine V3.2 (rev 7, §2.2 "Série de rótulos", §9.2).

The V2/V3 engines never consumed a price series (``price`` is the spot of the universe row). V3.2 needs one for the
realized-error labels ``P_real(T + h)``, for the weekly panel and — with the 36-month backfill the owner ordered on
07/09/2026 — for the point-in-time re-execution (B2). This module PRODUCES and READS that series; it computes no
label arithmetic beyond locating the bar ``h`` sessions after a session on the exchange calendar.

Contract (rev 7 §2.2), rev 4 of the implementation (Codex C394-1..5, C394-2/9 residuals, C394-12..14; rev 4 closes the two P2
residuals of the rev 3 audit: A1 = C394-14 for a symbol with no series, A2 = one capture per market and phase ACROSS processes):
* one bar per (market, symbol, session) with ``close`` and ``adjusted_close`` (both mandatory), ``currency``,
  ``source`` (EODHD ``/api/eod`` for every market — the single source declared in the inventory), ``fetched_at`` and a
  canonical CONTENT hash (``bar_sha256`` excludes the clock, so an unchanged bar is recognised across runs; prices are
  canonicalised to 6 decimals so the hash survives the NUMERIC round-trip and can be RECOMPUTED on read);
* **capture and publication are two facts with two clocks.** A run reads ``started_at`` before the first request and
  ``fetched_at`` = the CAPTURE after the last provider answer; it persists the manifest ``valuation_price_history/<M>``
  (``published_at`` = ``fetched_at``) and the changed bars in ONE transaction; and only AFTER that transaction committed it
  appends the PUBLICATION ``valuation_price_history_publication/<M>`` whose ``published_at`` = ``available_at`` = a clock
  read immediately before that insert. §2.2: nothing is available before its first persistence, and availability is
  never retro-dated — so a reader with cut ``C`` resolves the single vintage ``S`` by the PUBLICATIONS (the greatest
  ``available_at < C`` of this schema), never by the capture; a cut between capture and availability sees nothing, now
  or later. A manifest without publication is captured-never-published: invisible forever;
* **one vintage per market and cut, written under one critical section per market:** the clock re-check (the capture
  must advance beyond the previous manifest AND the previous publication), the dedupe read, the manifest + bars and the
  publication happen under the market's lock (in memory a re-entrant lock; in PostgreSQL a transaction-level advisory
  lock taken as the first statement of each writer's transaction — the dedupe read is a ``DISTINCT ON`` inside the
  capture's own transaction, AFTER the lock and the clock re-checks, so two processes can never both see "no row yet" for
  the same bar: the store hands the producer the latest hashes and the producer hands back the manifest and the bars to
  insert, committed together). Two runs racing on the same clock leave exactly one vintage; the other is refused with
  nothing written;
* **an empty vintage never hides the previous one:** a run whose wanted set is EMPTY (no coverage: no universe row, no
  V3 shadow symbol) is REFUSED before any clock tick, any provider request and any write (``ValueError``: "no symbols to
  fetch for M" — ``persist_run``, ``backfill`` and ``nightly`` alike, through one ``_wanted`` check), and a run whose
  wanted set is non-empty but yields ZERO symbols with bars (provider fully down: every symbol an error, every row refused
  or an empty answer — counted separately in the message) is REFUSED before anything is written (``ValueError``:
  "provider returned no bars for N symbols"); the previous vintage stays the one every cut sees. ``run_all`` gives every
  market its turn AT MOST ONCE per phase: a market whose latest publication is at/after the phase's due instant (by
  default 01:00 America/Sao_Paulo of the local date of ``now`` — the worker's ``OffhoursPhase`` convention; a naive
  ``now``/``due_at`` is São Paulo wall time, as the worker reads it, T2) already published tonight and is skipped without
  a request or a write — and the due travels to the capture writer, which re-checks it INSIDE the market's lock right
  before the write (``AlreadyPublishedError``: a market that published since the due while this run was fetching is a
  skip with nothing written, whichever process published, T5) —, a refused market never stops the others, and the phase
  fails at the end naming the refused markets only (so a worker retry re-runs the failed market alone);
* **at most ONE capture per market and phase, across processes (A2):** the advisory lock ends at the capture's commit and
  is re-taken for the publication, so two processes with the same due could interleave A-capture → B-capture → A-publish →
  B-publish and leave two vintages for one night (both consistent; the whole-cycle exclusion broken). The capture writer
  therefore refuses — inside the lock, after the clock re-reads, before the dedupe read — a capture when the market's
  latest MANIFEST was captured at/after the due and no publication since the due is visible (``AlreadyCapturedError``:
  another process holds this phase's vintage; nothing written; the memory double applies the same rule under the market
  lock — with a publication since the due it is ``AlreadyPublishedError`` instead: the publication check runs first).
  ``run_all`` reads it as a skip carrying the capture clock it found — and checks, at the END of the run, that the vintage
  it deferred to became visible: if the market still has no publication since the due, the phase FAILS naming it (the
  process that captured died or failed — any exception — between its capture and its publication, is still publishing, or had its publication
  refused by the availability stamp — a ``ValueError`` in the log of the run that captured: the clock went backwards, or
  the availability/capture did not advance beyond the previous publication, e.g. a backfill run inside the phase window
  — and the night is captured-never-published: loud, the retry is refused without a request or a write until the next
  due, the previous vintage keeps serving — runbook in the docs). The CLI ``--nightly`` carries the same due
  (``offhours_due_at`` of the real clock), so an operator obeys the once-per-phase rule — and is REFUSED by the parser
  before that due (between 00:00 and 01:00 America/Sao_Paulo the due of the local date is still in the future, so the
  rule would be empty: a vintage captured then would not count for tonight's phase and the worker would capture another
  after 01:00) and, once the market published since the due, for the REST of the local day (``AlreadyPublishedError``,
  not only inside the 01:00–08:00 window); ``--symbols`` is ``--backfill`` only (the parser refuses it with
  ``--nightly``); ``--backfill`` is exempt BY DESIGN (the manual, ordered path: never inside the phase window);
* **the in-memory double is the DDL and the JSONB column:** it refuses what migration 049 refuses (columns, market, ISO
  ``session_date``, prices > 0 compared in their own type — a huge int is a NUMERIC, never an OverflowError, T3 —, a finite
  ``volume``, the hash, the clock, T4) before any write, and stores the JSON round-trip of every snapshot's inputs/outputs
  (a datetime becomes its string, as it would in PostgreSQL), never the caller's dicts;
* the manifest carries one series hash per symbol; a reader serves a symbol only if the stored bars, each with its
  content hash RECOMPUTED from the fields read, reproduce the series hash ``S`` recorded for it — a symbol absent from
  ``S`` is refused, never completed from an older vintage (§2.2: both dates of a label come from the same snapshot);
* storage is content-deduplicated: a run inserts only bars whose content differs from the latest row of the same
  (market, symbol, session, source); the vintage is reproduced by "latest row with ``fetched_at`` ≤ ``S.fetched_at``"
  inside the run's window MINUS the sessions ``S`` refused for that symbol, and verified by the per-symbol hash (a
  provider that silently drops a session — no row at all, not a refused one — makes that symbol ``unreproducible`` in
  ``S``: recorded in the manifest, refused by the readers; that check covers the symbols the run FETCHED bars for — the
  dedupe read and the stale check — never a symbol known only by its refusals). Three clocks travel with every served bar: ``available_at``
  (publication of ``S``), ``fetched_at`` (capture of ``S``) and ``first_captured_at`` (the stored row's own clock — the
  first capture of that content);
* a provider row the series refuses (a close missing) is recorded per symbol WITH its session and missing fields; the
  series of ``S`` for the symbol excludes that session even when an older vintage stored a bar for it (the provider
  answered: it is not a vanished session), and a label whose target session was refused is
  ``label_unavailable:adjustment_unknown`` (§2.2), never ``missing_bar`` and never ``vintage_unreproducible`` — ALSO when
  the run refused EVERY row of the symbol, so ``S`` has no series hash for it (A1): the cause is in the manifest
  (``rows_rejected``) and in ``series().rejected_sessions``, and ``label_bar`` reads it before saying
  ``symbol_not_in_vintage``, which stays only when the vintage has neither a series nor a refusal (with a session) for the
  symbol; a symbol the vintage knows only by its refusals gets ``outside_window`` outside the window and ``missing_bar``
  for any other session in it — EVEN when an earlier vintage stored that session: the run does not check the dropped
  sessions of a symbol without a series (the dedupe read and the stale check only cover the symbols it fetched bars for),
  so such a symbol is never ``vintage_unreproducible`` (honest wording, not a guarantee a symbol with a series gives);
* a publication is attested only when its manifest exists, agrees with it (type, market, schema, snapshot id, bars hash,
  capture clock), carries parseable clocks (``fetched_at``, ``from``, ``to``, and the publication's ``available_at``) AND
  its ``available_at`` is the instant of its own ``published_at`` (the clock a cut is compared with is never a claim);
  anything else is ``manifest_mismatch``, never an exception in a reader. Only ``ok`` series are cached, so a refused
  read is re-evaluated next time (a manifest that appears later is served);
* coverage = the current universe of the market ∪ every symbol that has V3 shadow evaluations (labels still to come);
* a label is only ``labelled`` when the target session has CLOSED before the cut (exchange calendar close, not the
  civil date) and the vintage has a bar for it; every reader returns its own copies, never the cache's dicts — and the
  producer's result is a deep copy too, never the stored manifest's dicts;
* OFF by default: the worker phase runs only with ``C3PO_VALUATION_PRICE_HISTORY_ENABLED=true``; the backfill is an
  explicit, one-shot CLI invocation under the mesa's order (no due), and the CLI ``--nightly`` is a phase run with the
  real clock's due. A scripted ``clock`` is read exactly THREE times per run
  (``started_at``, ``fetched_at``, ``available_at``); ``backfill``/``nightly`` derive the window's end from the first of
  those ticks, never from an extra one.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as wall_time, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
from exchange_calendars.errors import RequestedSessionOutOfBounds

from .config import Settings, get_settings
from .price_coverage import PriceCoverageCatalog
from .database import AlreadyCapturedError, AlreadyPublishedError, Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_price_history"
PUBLICATION_TYPE = "valuation_price_history_publication"
SCHEMA_VERSION = "VALUATION-PRICE-HISTORY-v3"
SOURCE = "eodhd:/api/eod"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
CALENDARS = {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"}
PROVIDER_SUFFIX = {"B3": "SA", "NASDAQ": "US", "NYSE": "US"}
CURRENCY = {"B3": "BRL", "NASDAQ": "USD", "NYSE": "USD"}
DEFAULT_BACKFILL_MONTHS = 36
PRICE_DECIMALS = 6  # ≤ 15 significant digits for any realistic price/volume: PostgreSQL's float8 → NUMERIC cast keeps exactly that many
LABEL_ADJUSTMENT_UNKNOWN = "label_unavailable:adjustment_unknown"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")  # the worker's clock (valuation_worker.SAO_PAULO)
OFFHOURS_DUE_HOUR = 1  # = valuation_worker.OFFHOURS_START_HOUR: the off-hours phase comes due at 01:00 America/Sao_Paulo (pinned by a test)
_SERIES_CACHE_SIZE = 256
_calendars: dict[str, Any] = {}


def _calendar(market: str) -> Any:
    name = CALENDARS[market]
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def _utc(value: datetime) -> datetime:
    """Always UTC: a naive value is taken as UTC; an aware value is converted (never left in its own zone). The convention
    of the run API (``persist_run``/``backfill``/``nightly``, ``clock``/``now``) and of every stored clock; the phase entry
    points read naive values the worker's way instead (``_worker_instant``)."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _worker_instant(value: datetime) -> datetime:
    """A clock as the worker reads it, as a UTC instant (T2): a NAIVE value is America/Sao_Paulo wall time — exactly
    ``valuation_worker._phase_is_due`` (``replace(tzinfo=SAO_PAULO)``) and ``start_of_today`` (the naive date is the local
    date) — and an aware value is converted. ``run_all``/``offhours_due_at`` read ``now`` and ``due_at`` through this, so
    a naive 01:30 is 01:30 in São Paulo (the phase of that date came due at 01:00), never 01:30 UTC (22:30 of the eve)."""
    return _utc(value.replace(tzinfo=SAO_PAULO) if value.tzinfo is None else value)


def _instant(value: Any) -> datetime:
    """The UTC instant of a stored clock (ISO string or datetime)."""
    return _utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value)))


def _mapping(value: Any) -> dict[str, Any]:
    """A stored JSON object, or an empty one when the field is absent or not an object."""
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    """A stored clock as text, ``None`` when absent (never the string "None")."""
    return None if value is None else str(value)


def _parses(value: Any, parse: Callable[[Any], Any]) -> bool:
    """Whether a stored clock/date field parses (R4): a reader refuses what it cannot parse instead of raising."""
    try:
        parse(value)
    except (TypeError, ValueError):
        return False
    return True


def _number(value: Any) -> float | None:
    """A provider/stored number as a float, ``None`` when it is not one — a NaN, an infinity, or an int too large for a float
    (``OverflowError``: the readers recompute hashes from stored fields and must never raise, T3)."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _canonical_number(value: Any) -> float | None:
    """A provider number as the series stores and hashes it: 6 decimals, so the value read back from NUMERIC is the same
    float that was hashed (the content hash is recomputed on every read, C394-13)."""
    number = _number(value)
    return None if number is None else round(number, PRICE_DECIMALS)


def _price(value: Any) -> float | None:
    number = _canonical_number(value)
    return None if number is None or number <= 0 else number


def _session(raw: Mapping[str, Any]) -> str | None:
    session = str(raw.get("date") or "")[:10]
    if not session:
        return None
    try:
        date.fromisoformat(session)
    except ValueError:
        return None
    return session


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _bar_core(market: str, symbol: str, session: str, close: float, adjusted: float, volume: float | None, currency: str, source: str,
              provider_symbol: str) -> dict[str, Any]:
    """The hashed content of a bar — every field a reader gets back from the store, and nothing about the clock."""
    return {"schema": SCHEMA_VERSION, "market": market, "symbol": symbol, "session_date": session, "close": close, "adjusted_close": adjusted,
            "volume": volume, "currency": currency, "source": source, "provider_symbol": provider_symbol}


def bar_defects(raw: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    """What a provider row lacks for the series: its session (``None`` when the date is unusable) and the missing fields
    among ``date``, ``close``, ``adjusted_close`` (absent, non-numeric or non-positive). Empty list = usable row."""
    session = _session(raw)
    missing = [field for field, present in (("date", session is not None), ("close", _price(raw.get("close")) is not None),
                                            ("adjusted_close", _price(raw.get("adjusted_close")) is not None)) if not present]
    return session, missing


def bar_record(market: str, symbol: str, provider_symbol: str, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One immutable bar without its clock: ``bar_sha256`` hashes the CONTENT (market, symbol, session, both closes, volume,
    currency, source, provider symbol), so the same bar fetched twice has the same hash and is stored once. ``None`` when
    the provider row is unusable (both closes are mandatory, §2.2 — see ``bar_defects`` for the reason). ``fetched_at``/
    ``snapshot_id`` are stamped by the run."""
    session, missing = bar_defects(raw)
    if session is None or missing:
        return None
    close, adjusted = _price(raw.get("close")), _price(raw.get("adjusted_close"))
    assert close is not None and adjusted is not None  # bar_defects said so
    core = _bar_core(market, symbol, session, close, adjusted, _canonical_number(raw.get("volume")), CURRENCY[market], SOURCE, provider_symbol)
    return {**core, "id": str(uuid4()), "bar_sha256": canonical_sha256(core)}


def bar_content_sha256(bar: Mapping[str, Any]) -> str | None:
    """The content hash RECOMPUTED from a stored bar's fields (the exact core ``bar_record`` hashed): what a reader compares
    with the stored ``bar_sha256`` before serving the bar, so a row whose content was altered under its old hash is refused
    (C394-13). ``None`` when the row is not even a bar (a close missing or non-positive)."""
    close, adjusted = _price(bar.get("close")), _price(bar.get("adjusted_close"))
    if close is None or adjusted is None:
        return None
    return canonical_sha256(_bar_core(str(bar["market"]), str(bar["symbol"]), str(bar["session_date"]), close, adjusted, _canonical_number(bar.get("volume")),
                                      str(bar["currency"]), str(bar["source"]), str(bar["provider_symbol"])))


def series_sha256(bars: Iterable[Mapping[str, Any]]) -> str:
    """The hash of one symbol's series in a vintage: its bar hashes in session order."""
    ordered = sorted(bars, key=lambda bar: str(bar["session_date"]))
    return canonical_sha256([[str(bar["session_date"]), str(bar["bar_sha256"])] for bar in ordered])


def sessions_after(market: str, session: date, count: int) -> tuple[date | None, str]:
    """The session ``count`` trading sessions after ``session`` on the market's calendar, with the reason when there is
    none: ``not_a_session`` (the input date is not a session of that market) or ``beyond_calendar``."""
    calendar = _calendar(market)
    if not calendar.is_session(session.isoformat()):
        return None, "not_a_session"
    try:
        return calendar.session_offset(session.isoformat(), count).date(), "ok"
    except (ValueError, IndexError, KeyError, RequestedSessionOutOfBounds):
        return None, "beyond_calendar"


def session_close(market: str, session: date) -> datetime:
    """The UTC instant the exchange closed that session (exchange_calendars): a bar exists only after it."""
    return _utc(_calendar(market).session_close(session.isoformat()).to_pydatetime())


def window_start(end: date, months: int) -> date:
    """The first day of the calendar month ``months`` before ``end`` (always covers at least the requested months)."""
    year, month = end.year, end.month - months
    while month <= 0:
        year, month = year - 1, month + 12
    return date(year, month, 1)


def offhours_due_at(now: datetime) -> datetime:
    """The UTC instant the worker's off-hours phase came due for the São Paulo local date of ``now``: midnight of that date
    plus ``OFFHOURS_DUE_HOUR`` hours (``valuation_worker.run_worker_iteration``: ``start_of_today(now) + start_hour``).
    A naive ``now`` is São Paulo wall time, as the worker reads it (``_worker_instant``, T2). A market whose latest
    publication is at/after the due has already published tonight (S1)."""
    local = _worker_instant(now).astimezone(SAO_PAULO)
    return _utc(datetime.combine(local.date(), wall_time.min, tzinfo=SAO_PAULO) + timedelta(hours=OFFHOURS_DUE_HOUR))


class PriceHistoryService:
    """Producer and reader of `valuation_price_history/<M>` (and of its publications)."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient, *, eodhd: EodhdClient | None = None) -> None:
        self.settings = settings
        self.database = database
        self.eodhd = eodhd or EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self.coverage_catalog = PriceCoverageCatalog(settings, http)
        self._series_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    # ------------------------------------------------------------------ coverage
    def coverage_symbols(self, market: str) -> list[str]:
        return self.coverage_plan(market)[0]

    def coverage_plan(self, market: str) -> tuple[list[str], dict[str, Any] | None]:
        """Monitored: universe ∪ V3 evaluations (§2.2). Expanded: classified catalog
        plus previously published stock/ETF identities. Catalog reads precede the
        three bar-run clocks; failures cannot silently publish smaller coverage."""
        symbols: set[str] = set()
        universe = self.database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        raw_rows = _mapping((universe or {}).get("outputs")).get("rows")
        rows: list[Any] = raw_rows if isinstance(raw_rows, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("symbol"):
                symbols.add(str(row["symbol"]).strip().upper())
        symbols.update(self.database.v3_shadow_symbols(market))
        if self.settings.valuation_price_history_scope == "monitored":
            return sorted(symbols), None
        # Only a published coverage decision can be carried into the next night.
        publication = self.database.latest_analysis_snapshot(PUBLICATION_TYPE, market)
        snapshot_id = _mapping((publication or {}).get("inputs")).get("price_snapshot_id")
        previous = self.database.analysis_snapshot_by_id(str(snapshot_id)) if snapshot_id else None
        outputs = _mapping((previous or {}).get("outputs"))
        symbols.update(_mapping(outputs.get("series_sha256")))
        selected = _mapping(_mapping(outputs.get("coverage")).get("selected"))
        coverage = self.coverage_catalog.plan(market, previous=selected, legacy=sorted(symbols))
        return list(coverage["selected"]), coverage

    def window_months(self) -> int:
        return int(getattr(self.settings, "valuation_price_history_backfill_months", DEFAULT_BACKFILL_MONTHS))

    @staticmethod
    def _wanted(market: str, symbols: Iterable[str]) -> list[str]:
        """The normalised, de-duplicated symbol set of a run — REFUSED when empty (R14, S2): no coverage is not a vintage
        either, and the refusal comes before any clock tick, any provider request and any write (``persist_run``,
        ``backfill`` and ``nightly`` all pass through here BEFORE they read their clock)."""
        wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not wanted:
            raise ValueError(f"no symbols to fetch for {market}: an empty vintage is refused, the previous one stays the one every cut sees")
        return wanted

    # ------------------------------------------------------------------ producer
    def fetch_bars(self, market: str, symbol: str, *, start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Bars for one symbol plus the provider rows REJECTED as incomplete (a close missing), each with its session and
        the missing fields: the provider answered, the series refused — recorded in the manifest, never a silent gap, and
        the reason a label becomes ``adjustment_unknown`` (C394-14). The provider symbol used in the request is the one
        persisted (a ticker with a dot is passed already suffixed, so both agree). Rows outside [start, end] are dropped,
        rejected ones included (a row with no usable date is kept: it has no session to be outside of). A session is
        refused only when the answer has NO usable row for it: an incomplete duplicate of a usable row is noise, not a
        refusal (the series of the vintage = its bars, and a refused session is never among them)."""
        provider_symbol = f"{symbol}.{PROVIDER_SUFFIX[market]}"
        raw_rows = self.eodhd.daily_bars(provider_symbol, exchange=PROVIDER_SUFFIX[market], start=start, end=end) or []
        bars: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for raw in raw_rows:
            session, missing = bar_defects(raw)
            if session is not None and not (start.isoformat() <= session <= end.isoformat()):
                continue
            if missing:
                rejected.append({"session": session, "missing": missing})
                continue
            bar = bar_record(market, symbol, provider_symbol, raw)
            if bar is not None:
                bars.append(bar)
        usable = {bar["session_date"] for bar in bars}
        return bars, sorted((row for row in rejected if row["session"] not in usable), key=lambda row: str(row["session"]))

    def persist_run(self, market: str, *, start: date, end: date, symbols: Iterable[str], now: datetime | None = None, workers: int = 8,
                    mode: str = "nightly", clock: Callable[[], datetime] | None = None, due: datetime | None = None,
                    coverage: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch the whole window for ``symbols`` and persist ONE vintage in two facts: the CAPTURE (manifest + changed bars in
        a single transaction, ``fetched_at`` read AFTER the last provider answer) and, once that transaction committed, the
        PUBLICATION (``available_at`` read immediately before its insert — the clock every reader compares with its cut).
        A cut before ``available_at`` never sees this vintage, now or later. From the capture (clock re-check, dedupe read,
        manifest + bars) to the publication the run holds the market's critical section (C394-9). ``clock`` is read exactly
        THREE times: ``started_at`` (before the first request), ``fetched_at`` (after the last answer) and ``available_at``
        (inside the publication writer). An EMPTY wanted set is REFUSED before any clock tick, any request and any write
        (R14, ``_wanted``), and a wanted set that yields no symbol with bars is REFUSED before any write (R8): an empty
        vintage would hide the previous one from every later cut. ``due`` (a phase's due instant, from ``run_all``) is
        re-checked INSIDE the market's lock right before the capture write: a publication of the market at/after it means
        the market already published since the phase came due (while this run was fetching) — refused with
        ``AlreadyPublishedError`` ("already published since <due>"), nothing written, a skip for ``run_all`` (T5) —, and,
        without such a publication, a MANIFEST captured at/after it means another process captured this phase's vintage
        and has not published it yet — refused with ``AlreadyCapturedError`` ("already captured since <due>"), nothing
        written, a skip for ``run_all`` that must be confirmed by a publication before the run ends (A2; the publication
        check runs first, so a published vintage always says "already published"). Like every clock of the run API, a
        naive ``due`` is UTC (``_utc``); ``run_all`` converts the worker's reading first."""
        wanted = self._wanted(market, symbols)
        if coverage is not None:
            coverage = copy.deepcopy(coverage)
            if sorted(wanted) != sorted(coverage["selected"]):
                raise ValueError("coverage manifest does not match requested symbols")
            coverage["allowance"] = self.coverage_catalog.allowance(len(wanted))
        due = None if due is None else _utc(due)
        tick: Callable[[], datetime] = clock or ((lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)))  # type: ignore[return-value]
        started_at = _utc(tick())
        fetched: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        errors: dict[str, str] = {}
        rejected: dict[str, list[dict[str, Any]]] = {}

        def fetch(symbol: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str | None]:
            try:
                if coverage is not None:
                    self.coverage_catalog.throttle()
                rows, incomplete = self.fetch_bars(market, symbol, start=start, end=end)
                return symbol, rows, incomplete, None
            except Exception as error:  # the provider's failure is evidence, never a silent gap
                return symbol, [], [], f"{type(error).__name__}"

        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
            for symbol, rows, incomplete, error in executor.map(fetch, wanted):
                if error:
                    errors[symbol] = error
                if incomplete:
                    rejected[symbol] = incomplete
                if not rows:
                    missing.append(symbol)
                else:
                    fetched[symbol] = rows
        fetched_at = _utc(tick())
        if fetched_at < started_at:
            raise ValueError("price history clock went backwards during the run")
        if not fetched:  # R8: nothing to publish is not a vintage — refuse before the first write, the previous vintage stays served
            refused = [symbol for symbol in missing if symbol not in errors and symbol in rejected]  # R13: the provider answered, the series refused every row
            empty = [symbol for symbol in missing if symbol not in errors and symbol not in rejected]
            raise ValueError(f"provider returned no bars for {len(wanted)} symbols of {market} ({len(errors)} errors, {len(refused)} symbols with every row refused, "
                             f"{len(empty)} empty answers): an empty vintage is refused, the previous one stays the one every cut sees")
        with self.database.price_history_lock(market):  # C394-9: due re-check, clock re-check, dedupe read, manifest + bars and publication — one section per market
            return self._persist_vintage(market, mode=mode, start=start, end=end, wanted=wanted, fetched=fetched, missing=missing, errors=errors,
                                         rejected=rejected, started_at=started_at, fetched_at=fetched_at, tick=tick, due=due, coverage=coverage)

    def _persist_vintage(self, market: str, *, mode: str, start: date, end: date, wanted: list[str], fetched: dict[str, list[dict[str, Any]]],
                         missing: list[str], errors: dict[str, str], rejected: dict[str, list[dict[str, Any]]], started_at: datetime, fetched_at: datetime,
                         tick: Callable[[], datetime], due: datetime | None, coverage: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot_id = str(uuid4())
        manifest_outputs: dict[str, Any] = {}
        publication_outputs: dict[str, Any] = {}

        def build(latest: dict[tuple[str, str], str]) -> tuple[dict[str, Any], dict[str, Any], datetime, str, list[dict[str, Any]]]:
            """Runs INSIDE the capture's critical section/transaction with the dedupe read the store just made (R2): content
            dedup against the latest stored row per (symbol, session). A session the provider DROPPED from a symbol (no row
            at all) would survive in the chain read and break the series hash — recorded as unreproducible, refused by the
            readers; a session the provider answered and the series REFUSED (a close missing) is not a vanished session:
            the readers drop it from the chain before hashing (R1), so it is never counted as stale."""
            to_insert: list[dict[str, Any]] = []
            unchanged = 0
            series_hashes: dict[str, str] = {}
            series_bars: dict[str, int] = {}
            unreproducible: dict[str, list[str]] = {}
            duplicates: dict[str, int] = {}
            # Index once; scanning all stored keys for each symbol is quadratic.
            latest_sessions: dict[str, set[str]] = defaultdict(set)
            start_text, end_text = start.isoformat(), end.isoformat()
            for sym, session in latest:
                if start_text <= session <= end_text:
                    latest_sessions[sym].add(session)
            for symbol, rows in fetched.items():
                by_session: dict[str, dict[str, Any]] = {}
                for bar in rows:  # a duplicate session in one provider answer: the first row wins (same rule as ON CONFLICT DO NOTHING) — counted, never silent (C394-10)
                    if bar["session_date"] in by_session:
                        duplicates[symbol] = duplicates.get(symbol, 0) + 1
                    else:
                        by_session[bar["session_date"]] = bar
                refused = {str(row["session"]) for row in rejected.get(symbol, ()) if row.get("session")}
                stale = sorted(latest_sessions[symbol] - by_session.keys() - refused)
                if stale:
                    unreproducible[symbol] = stale
                for session, bar in by_session.items():
                    bar["fetched_at"] = fetched_at.isoformat()
                    bar["snapshot_id"] = snapshot_id
                    if latest.get((symbol, session)) == bar["bar_sha256"]:
                        unchanged += 1
                    else:
                        to_insert.append(bar)
                series_hashes[symbol] = series_sha256(by_session.values())
                series_bars[symbol] = len(by_session)
            sessions = sorted({bar["session_date"] for rows in fetched.values() for bar in rows})
            bars_sha256 = canonical_sha256(sorted(series_hashes.items()))
            manifest_inputs = {"schema_version": SCHEMA_VERSION, "market": market, "source": SOURCE, "mode": mode, "from": start.isoformat(), "to": end.isoformat(),
                               "symbols_requested": len(wanted), "started_at": started_at.isoformat(), "fetched_at": fetched_at.isoformat(),
                               "calendar": {"name": CALENDARS[market], "exchange_calendars": getattr(xcals, "__version__", "unknown")}}
            manifest_outputs.update({"schema_version": SCHEMA_VERSION, "price_snapshot_id": snapshot_id, "bars": sum(series_bars.values()),
                                     "bars_inserted": len(to_insert), "bars_unchanged": unchanged,
                                     "symbols_with_bars": len(fetched), "symbols_missing": sorted(missing), "errors": errors,
                                     "rows_rejected": dict(sorted(rejected.items())),
                                     "rows_rejected_incomplete": {symbol: len(rows) for symbol, rows in sorted(rejected.items())},
                                     "rows_rejected_total": sum(len(rows) for rows in rejected.values()),
                                     "rows_duplicate_in_response": dict(sorted(duplicates.items())), "rows_duplicate_total": sum(duplicates.values()),
                                     "symbols_unreproducible": dict(sorted(unreproducible.items())),
                                     "first_session": sessions[0] if sessions else None, "last_session": sessions[-1] if sessions else None,
                                     "series_sha256": dict(sorted(series_hashes.items())), "series_bars": dict(sorted(series_bars.items())),
                                     "bars_sha256": bars_sha256})
            if coverage is not None:
                manifest_outputs["coverage"] = coverage
            publication_outputs.update({"schema_version": SCHEMA_VERSION, "bars_sha256": bars_sha256, "price_snapshot_id": snapshot_id})
            return manifest_inputs, manifest_outputs, fetched_at, snapshot_id, to_insert

        methodology_id = self._methodology_id()
        inserted = self.database.persist_price_history_run(ANALYSIS_TYPE, PUBLICATION_TYPE, market, methodology_id, fetched_at=fetched_at, symbols=list(fetched),
                                                           source=SOURCE, build=build, due=due)  # T5: the due is re-checked inside the writer's lock, before any write
        # the capture is committed; the publication is the SECOND fact, stamped as late as possible (inside the database's writer)
        publication_id, available_at = self.database.publish_price_history_run(
            PUBLICATION_TYPE, ANALYSIS_TYPE, market, methodology_id,
            {"schema_version": SCHEMA_VERSION, "price_snapshot_id": snapshot_id, "fetched_at": fetched_at.isoformat(), "started_at": started_at.isoformat()},
            publication_outputs, fetched_at=fetched_at, clock=tick)
        logger.info("valuation_price_history %s %s: %s bars (%s inserted, %s unchanged), %s symbols missing, %s rows rejected, %s unreproducible; "
                    "captured %s, available %s", market, mode, manifest_outputs["bars"], inserted, manifest_outputs["bars_unchanged"], len(missing),
                    manifest_outputs["rows_rejected_total"], len(manifest_outputs["symbols_unreproducible"]), fetched_at.isoformat(), available_at.isoformat())
        return copy.deepcopy({"market": market, "mode": mode, "started_at": started_at.isoformat(), "fetched_at": fetched_at.isoformat(), **manifest_outputs,
                              "bars_inserted": inserted, "publication_id": publication_id, "available_at": available_at.isoformat()})  # R3: never the store's dicts

    def _methodology_id(self) -> str:
        return self.database.ensure_methodology_version("valuation_price_history", 3, {"schema": SCHEMA_VERSION, "source": SOURCE},
                                                        "Persisted daily price series for V3.2 labels (rev 7 §2.2): one vintage per run, capture then publication")

    @staticmethod
    def _window_clock(now: datetime | None, clock: Callable[[], datetime] | None) -> tuple[date, Callable[[], datetime]]:
        """The window's end and the clock the run will read (R6): ONE tick is read here and replayed as the run's
        ``started_at``, so the end of the window and the start of the run are the same instant and a scripted clock needs
        exactly the three ticks ``persist_run`` documents — never a fourth for the window."""
        source: Callable[[], datetime] = clock or ((lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)))  # type: ignore[return-value]
        first = _utc(source())
        pending = [first]

        def replayed() -> datetime:
            return pending.pop() if pending else source()

        return first.date(), replayed

    def backfill(self, market: str, *, months: int | None = None, now: datetime | None = None, symbols: Iterable[str] | None = None,
                 clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """The one-shot history (owner's decision of 07/09/2026): bars persisted now carry ``fetched_at`` = now and become
        available at the run's publication, so only packages cut AFTER it may consume them (rev 7 §2.2) — history for
        training, never a look-ahead. The window defaults to ``settings.valuation_price_history_backfill_months``; its end
        is the run's first clock tick (``started_at``), and a scripted ``clock`` is read exactly three times in total. An
        empty symbol set (``--symbols`` empty, or no coverage) is refused BEFORE the first tick, any request and any write."""
        months = int(months if months is not None else self.window_months())
        chosen, coverage = (list(symbols), None) if symbols is not None else self.coverage_plan(market)
        wanted = self._wanted(market, chosen)  # S2: before the first tick
        end, tick = self._window_clock(now, clock)
        return self.persist_run(market, start=window_start(end, months), end=end, symbols=wanted, mode="backfill", clock=tick, coverage=coverage)

    def nightly(self, market: str, *, now: datetime | None = None, clock: Callable[[], datetime] | None = None, due: datetime | None = None) -> dict[str, Any]:
        """The nightly vintage: the WHOLE window again (one provider call per symbol, as the backfill), so that every cut has
        one self-contained vintage; unchanged bars cost no storage. The clock is read as in ``backfill`` (three ticks), and
        an empty coverage set is refused BEFORE the first tick, any request and any write. ``due`` travels to ``persist_run``
        (T5, A2): the phase's due instant, re-checked inside the market's lock before the capture write."""
        chosen, coverage = self.coverage_plan(market)
        wanted = self._wanted(market, chosen)  # S2: before the first tick
        end, tick = self._window_clock(now, clock)
        return self.persist_run(market, start=window_start(end, self.window_months()), end=end, symbols=wanted, mode="nightly", clock=tick, due=due, coverage=coverage)

    def run_all(self, now: datetime | None = None, *, due_at: datetime | None = None) -> dict[str, dict[str, Any]]:
        """The nightly vintage of EVERY market, each on its own (R9) and each AT MOST ONCE per phase (S1). A market whose
        latest PUBLICATION is at/after the phase's due instant — ``due_at``, by default ``offhours_due_at(now)``: 01:00
        America/Sao_Paulo of the local date of ``now`` (the worker's ``OffhoursPhase`` due; ``now`` defaults to the real
        clock) — already published tonight and is SKIPPED without a request or a write, recorded as
        ``{"skipped": "already published", "available_at": ...}``: a worker retry while one market keeps failing never
        re-fetches 36 months for, nor re-publishes, the markets that already did. That first check is per process; the
        STRONG guarantee is the writer's (T5): the due travels to ``persist_run`` and is re-checked INSIDE the market's lock
        right before the capture write, so a market that published since the due while this attempt was fetching (another
        process, another thread) is refused with ``AlreadyPublishedError`` — recorded as skipped too, with the availability
        the writer found, never as a failure. **One capture per market and phase, across processes (A2):** a market whose
        latest MANIFEST was captured at/after the due but has no publication since it belongs to another process's attempt
        (in flight, dead or failed — any exception — between its capture and its publication, or whose publication the availability stamp refused —
        a ``ValueError`` in that run's log) — skipped here without a request or a write, and
        refused by the writer with ``AlreadyCapturedError`` when the other process captured while this one was fetching —
        recorded as ``{"skipped": "already captured", "fetched_at": ...}`` with the capture clock found. That skip defers to
        a vintage that must become visible: at the END of the run every such market is re-read, and one that still has no
        publication since the due is a FAILURE of the phase, named in the final error (nothing to re-run: the retry is
        refused the same way, cheaply, until the next due; the previous vintage keeps serving; the night stays
        captured-never-published — see the runbook). A naive ``now``/``due_at`` is São Paulo wall time, exactly as the
        worker reads a naive clock (``_phase_is_due``/``start_of_today`` — ``_worker_instant``, T2); the run's clock gets
        the same instant. A market whose run is refused (no coverage, no bars, a clock that does not advance) or fails
        never stops the others — its failure is logged, the remaining markets still run and publish, and the failures are
        re-raised together at the end naming the failed markets only, so the worker phase still fails loudly (and retries
        inside its window, for the failed markets alone)."""
        run_now = None if now is None else _worker_instant(now)  # T2: the worker's reading of a naive clock, for the due AND the run
        due = _worker_instant(due_at) if due_at is not None else offhours_due_at(run_now if run_now is not None else datetime.now(timezone.utc))
        results: dict[str, dict[str, Any]] = {}
        failures: dict[str, str] = {}
        skipped: list[str] = []
        deferred: dict[str, AlreadyCapturedError] = {}  # A2: markets whose capture belongs to another process — confirmed by a publication at the end

        def defer(taken: AlreadyCapturedError, where: str) -> None:
            results[taken.entity_key] = {"skipped": "already captured", "fetched_at": taken.fetched_at.isoformat()}
            deferred[taken.entity_key] = taken
            logger.info("valuation_price_history %s already captured at %s (phase due %s) by another process, not published yet%s: skipped, nothing written",
                        taken.entity_key, taken.fetched_at.isoformat(), due.isoformat(), where)

        for market in MARKETS:
            try:
                latest = self.database.latest_analysis_snapshot_published_at(PUBLICATION_TYPE, market)
                if latest is not None and _instant(latest) >= due:  # published since the phase came due: this attempt is a retry for another market
                    results[market] = {"skipped": "already published", "available_at": _instant(latest).isoformat()}
                    skipped.append(market)
                    logger.info("valuation_price_history %s already published at %s (phase due %s): skipped", market, _instant(latest).isoformat(), due.isoformat())
                    continue
                captured = self.database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, market)
                if captured is not None and _instant(captured) >= due:  # A2: captured since the due by another process (not published yet): no request, no write
                    defer(AlreadyCapturedError(market, due, _instant(captured)), "")
                    continue
                results[market] = self.nightly(market, now=run_now, due=due)
            except AlreadyPublishedError as done:  # T5: the writer found a publication since the due inside the lock — a skip, not a failure
                results[market] = {"skipped": "already published", "available_at": done.available_at.isoformat()}
                skipped.append(market)
                logger.info("valuation_price_history %s already published at %s (phase due %s) while this run was fetching: skipped, nothing written",
                            market, done.available_at.isoformat(), due.isoformat())
            except AlreadyCapturedError as taken:  # A2: the writer found a manifest since the due inside the lock — the other process captured while this run was fetching
                defer(taken, " while this run was fetching")
            except Exception as error:  # every market gets its turn; the phase fails at the end, not at the first market
                failures[market] = f"{type(error).__name__}: {error}"
                logger.exception("valuation_price_history %s nightly failed; the other markets still run", market)
        for market, taken in deferred.items():  # A2: a skip is only a skip if the vintage it deferred to became visible; otherwise the phase fails, loudly
            latest = self.database.latest_analysis_snapshot_published_at(PUBLICATION_TYPE, market)
            if latest is not None and _instant(latest) >= due:
                results[market]["available_at"] = _instant(latest).isoformat()
                skipped.append(market)
                continue
            results.pop(market)
            failures[market] = (f"{type(taken).__name__}: {taken}; still not published at the end of this run — the process that captured it died or failed "
                                "(any exception) between its capture and its publication, is still publishing, or had its publication refused (ValueError of the "
                                "availability stamp: the clock "
                                "went backwards, or the availability/capture did not advance beyond the previous publication — in the log of the run that "
                                "captured): refused without a request or a write until the next due, the previous vintage keeps serving, the night stays "
                                "captured-never-published (runbook)")
            logger.error("valuation_price_history %s captured at %s (phase due %s) but not published by the end of this run: the phase fails until the next due",
                         market, taken.fetched_at.isoformat(), due.isoformat())
        if failures:
            note = f", {len(skipped)} already published since {due.isoformat()}" if skipped else ""
            raise ValueError(f"valuation_price_history nightly failed for {', '.join(failures)} ({len(results)} of {len(MARKETS)} markets published{note}): "
                             + "; ".join(f"{market}: {reason}" for market, reason in failures.items()))
        return results

    def last_run_at(self) -> datetime | None:
        """When the phase last completed for EVERY market: the earliest of the latest PUBLICATIONS (a captured-never-
        published vintage is not a completed run)."""
        stamps = [self.database.latest_analysis_snapshot_published_at(PUBLICATION_TYPE, market) for market in MARKETS]
        present = [stamp for stamp in stamps if stamp is not None]
        return min(present) if len(present) == len(MARKETS) else None

    # ------------------------------------------------------------------ readers (the clock is a parameter, never "now")
    def vintage(self, market: str, *, available_before: datetime) -> dict[str, Any] | None:
        """The single vintage a cut sees: the PUBLICATION of this schema with the greatest ``available_at < available_before``
        (rev 7 §2.2 rule, on the availability clock — never the capture), then its manifest loaded by id and checked against
        what the publication attests (``status`` = ``ok``, or ``manifest_mismatch`` when the manifest is missing, disagrees,
        either row lacks a parseable clock — ``fetched_at``/``from``/``to`` of the manifest, ``available_at`` of the
        publication (R4) — or the publication's ``available_at`` is not the instant of its own ``published_at`` (R11):
        refused, never replaced by an older publication, never an exception). ``None`` when nothing was published before
        the cut."""
        publication = self.database.latest_analysis_snapshot_before(PUBLICATION_TYPE, market, _utc(available_before), schema_version=SCHEMA_VERSION)
        if not publication:
            return None
        p_inputs, p_outputs = _mapping(publication.get("inputs")), _mapping(publication.get("outputs"))
        snapshot_id = str(p_inputs.get("price_snapshot_id") or "")
        header = {"publication_id": str(publication["id"]), "price_snapshot_id": snapshot_id or None, "available_at": _instant(publication["published_at"]).isoformat(),
                  "fetched_at": _text(p_inputs.get("fetched_at")), "started_at": _text(p_inputs.get("started_at"))}
        manifest = self.database.analysis_snapshot_by_id(snapshot_id) if snapshot_id else None
        inputs, outputs = _mapping((manifest or {}).get("inputs")), _mapping((manifest or {}).get("outputs"))
        attested = (manifest is not None and manifest.get("analysis_type") == ANALYSIS_TYPE and manifest.get("entity_key") == market
                    and outputs.get("schema_version") == SCHEMA_VERSION and outputs.get("price_snapshot_id") == snapshot_id
                    and outputs.get("bars_sha256") == p_outputs.get("bars_sha256") and inputs.get("fetched_at") == p_inputs.get("fetched_at")
                    and _parses(inputs.get("fetched_at"), _instant) and _parses(p_inputs.get("available_at"), _instant)
                    and _instant(p_inputs.get("available_at")) == _instant(publication["published_at"])  # R11: the attested availability IS the row's clock
                    and _parses(inputs.get("from"), date.fromisoformat) and _parses(inputs.get("to"), date.fromisoformat))
        if not attested:
            return {**header, "status": "manifest_mismatch", "from": None, "to": None, "series_sha256": {}, "series_bars": {}, "symbols_unreproducible": {},
                    "rows_rejected": {}, "bars_sha256": None}
        return {**header, "status": "ok", "from": str(inputs.get("from")), "to": str(inputs.get("to")),
                "series_sha256": dict(outputs.get("series_sha256") or {}), "series_bars": dict(outputs.get("series_bars") or {}),
                "symbols_unreproducible": copy.deepcopy(dict(outputs.get("symbols_unreproducible") or {})),
                "rows_rejected": copy.deepcopy(dict(outputs.get("rows_rejected") or {})), "bars_sha256": outputs.get("bars_sha256")}

    def series(self, market: str, symbol: str, *, available_before: datetime) -> dict[str, Any]:
        """One symbol's bars from the single vintage the cut sees, each bar's content hash recomputed and the series verified
        against the hash that vintage recorded for it. Statuses: ``ok``; ``no_vintage`` (nothing published before the cut);
        ``manifest_mismatch`` (the publication's manifest is missing or disagrees with it); ``symbol_not_in_vintage`` (the
        vintage has no series for it — never completed from an older one; when the run refused EVERY row of the symbol,
        ``rejected_sessions`` still says which sessions and why, and ``label_bar`` reads it — A1); ``vintage_unreproducible`` (declared by the run
        itself); ``bar_hash_mismatch`` (a stored row's content no longer reproduces its own hash: refused);
        ``vintage_mismatch`` (the rows do not reproduce the recorded series hash: refused). The chain read is "latest row
        with ``fetched_at`` ≤ the capture" inside the window MINUS the sessions the vintage refused for the symbol (the
        recorded hash never included them; an older vintage's bar for such a session is not this vintage's — R1). The
        header carries the three clocks — ``available_at`` (publication), ``fetched_at`` (capture) and ``first_captured_at``
        (the earliest first capture among the served bars; each bar's own ``fetched_at`` is ITS first capture) — plus
        ``window`` = the vintage's [from, to] (a label outside it is ``outside_window``, never ``missing_bar``) and
        ``rejected_sessions`` = the sessions the run refused for this symbol with their missing fields. Always a fresh deep
        copy: the cache is never shared, and only ``ok`` results are cached (R5)."""
        symbol = symbol.strip().upper()
        vintage = self.vintage(market, available_before=available_before)
        if vintage is None:
            return {"status": "no_vintage", "price_snapshot_id": None, "publication_id": None, "available_at": None, "fetched_at": None,
                    "first_captured_at": None, "window": None, "rejected_sessions": {}, "bars": {}}
        key = (vintage["publication_id"], f"{market}:{symbol}")
        cached = self._series_cache.get(key)
        if cached is not None:
            self._series_cache.move_to_end(key)
            return copy.deepcopy(cached)
        header = {"price_snapshot_id": vintage["price_snapshot_id"], "publication_id": vintage["publication_id"], "available_at": vintage["available_at"],
                  "fetched_at": vintage["fetched_at"], "first_captured_at": None, "window": [vintage["from"], vintage["to"]] if vintage["status"] == "ok" else None,
                  "rejected_sessions": {str(row.get("session")): list(row.get("missing") or []) for row in vintage["rows_rejected"].get(symbol) or []
                                        if isinstance(row, dict) and row.get("session")}}
        expected = vintage["series_sha256"].get(symbol)
        if vintage["status"] != "ok":
            result = {"status": vintage["status"], **header, "bars": {}}
        elif expected is None:
            result = {"status": "symbol_not_in_vintage", **header, "bars": {}}
        elif symbol in vintage["symbols_unreproducible"]:
            result = {"status": "vintage_unreproducible", **header, "bars": {}}
        else:
            bars = self.database.price_bars(market, symbol, as_of=_instant(vintage["fetched_at"]), since=date.fromisoformat(vintage["from"]),
                                            until=date.fromisoformat(vintage["to"]))
            for session in header["rejected_sessions"]:  # R1: S refused that session; an older row for it is not part of S's series
                bars.pop(session, None)
            if any(bar_content_sha256(bar) != bar.get("bar_sha256") for bar in bars.values()):
                result = {"status": "bar_hash_mismatch", **header, "bars": {}}
            elif series_sha256(bars.values()) != expected:
                result = {"status": "vintage_mismatch", **header, "bars": {}}
            else:
                first = min((_instant(bar["fetched_at"]) for bar in bars.values()), default=None)
                result = {"status": "ok", **header, "first_captured_at": first.isoformat() if first else None, "bars": bars}
        if result["status"] == "ok":  # R5: a refusal is re-evaluated on the next read (a manifest that appears later must be served)
            self._series_cache[key] = copy.deepcopy(result)
            while len(self._series_cache) > _SERIES_CACHE_SIZE:
                self._series_cache.popitem(last=False)
        return result

    def bars(self, market: str, symbol: str, *, available_before: datetime) -> dict[str, dict[str, Any]]:
        """Bars by session as the cut sees them (empty when the vintage refuses the symbol — use ``series`` for the reason)."""
        return self.series(market, symbol, available_before=available_before)["bars"]

    def label_bar(self, market: str, symbol: str, session: date, horizon_sessions: int, *, available_before: datetime) -> dict[str, Any]:
        """The bar ``h`` sessions after ``session`` (the label of a prediction made at ``session``), as known before the cut.
        ``not_yet_mature`` until the target session has CLOSED before the cut; then the vintage's status — except that a
        symbol with NO series in ``S`` whose rows the run REFUSED (``rejected_sessions`` non-empty) is a symbol the vintage
        knows, and goes on to the checks below instead of ``symbol_not_in_vintage`` (A1: the cause is recorded; the label
        must read it) —; ``outside_window``; ``label_unavailable:adjustment_unknown`` (with ``missing``) when the run refused
        the provider's row for that session (a close missing in ``S``, §2.2), whether or not the symbol has other, usable
        bars in ``S``; ``missing_bar`` only when the exchange had the session, the vintage knows the symbol (a series, or
        rows it refused — the provider answered for it), the window covers it and the provider gave no row for that
        session — for a symbol known only by its refusals this holds EVEN when an earlier vintage stored that session (the
        run does not check the dropped sessions of a symbol without a series, so it is never ``vintage_unreproducible``);
        ``symbol_not_in_vintage`` only when the vintage has neither a series nor a refusal with a session for the
        symbol. ``labelled`` carries the three clocks: ``available_at`` (the publication of ``S``), ``fetched_at`` (the
        capture of ``S``) and ``first_captured_at`` (the bar row's own clock: the content may have been first captured by
        an earlier run and deduplicated since). Never a price from elsewhere."""
        cut = _utc(available_before)
        target, reason = sessions_after(market, session, horizon_sessions)
        if target is None:
            return {"session": None, "status": reason}
        if session_close(market, target) >= cut:
            return {"session": target.isoformat(), "status": "not_yet_mature"}
        known = self.series(market, symbol, available_before=cut)
        header = {"session": target.isoformat(), "price_snapshot_id": known["price_snapshot_id"], "publication_id": known["publication_id"],
                  "available_at": known["available_at"], "fetched_at": known["fetched_at"]}
        known_by_refusal = known["status"] == "symbol_not_in_vintage" and bool(known["rejected_sessions"])  # A1: no series, but S refused rows of it: S knows the symbol
        if known["status"] != "ok" and not known_by_refusal:
            return {**header, "status": known["status"]}
        if not (known["window"][0] <= target.isoformat() <= known["window"][1]):
            return {**header, "status": "outside_window"}  # the vintage never asked for that session: not "the exchange had no bar" (C394-11)
        bar = known["bars"].get(target.isoformat())
        if bar:
            return {**header, "status": "labelled", "close": bar["close"], "adjusted_close": bar["adjusted_close"], "bar_sha256": bar["bar_sha256"],
                    "first_captured_at": _instant(bar["fetched_at"]).isoformat()}
        missing = known["rejected_sessions"].get(target.isoformat())
        if missing:
            return {**header, "status": LABEL_ADJUSTMENT_UNKNOWN, "missing": list(missing)}  # the provider answered; S has no usable close for it (C394-14)
        return {**header, "status": "missing_bar"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 price series (rev 7 §2.2): backfill or nightly vintage; OFF unless invoked.")
    parser.add_argument("--market", choices=MARKETS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true", help="one-shot history (months from --months), bars stamped fetched_at = now; no phase due BY DESIGN "
                                                               "(the manual, ordered path: never inside the phase window)")
    group.add_argument("--nightly", action="store_true", help="the nightly vintage (whole window, coverage set) under the phase's once-per-phase rule: the due is "
                                                              "01:00 America/Sao_Paulo of today, as for the worker phase — refused before 01:00 (the phase of today "
                                                              "has not come due yet) and, once the market published since the due, for the rest of the local day "
                                                              "(not only inside the 01:00-08:00 window)")
    parser.add_argument("--months", type=int, default=None, help="defaults to C3PO_VALUATION_PRICE_HISTORY_BACKFILL_MONTHS (36)")
    parser.add_argument("--symbols", default="", help="comma-separated override of the coverage set (--backfill only; tests/dry runs)")
    args = parser.parse_args(argv)
    symbols = [s for s in args.symbols.split(",") if s.strip()] or None
    if args.nightly and symbols:  # the phase run is the coverage set, as for the worker: an override is a dry run/test of the manual path only
        parser.error("--symbols applies to --backfill only")
    due: datetime | None = None
    if args.nightly:  # the same once-per-phase rule as the worker phase (A2): the due of the São Paulo local date of the real clock, re-checked inside the market's lock
        now = datetime.now(timezone.utc)
        due = offhours_due_at(now)
        if now < due:  # 00:00–01:00 São Paulo: the due of today is still in the future, so the rule would be empty and the phase would capture another vintage after it
            parser.error(f"--nightly: the phase of today ({due.astimezone(SAO_PAULO).date().isoformat()}) has not come due yet (due {due.isoformat()} = "
                         f"{OFFHOURS_DUE_HOUR:02d}:00 America/Sao_Paulo, now {now.isoformat()}); use --backfill outside the phase window")
    settings = get_settings()
    if not settings.eodhd_api_token:
        print(json.dumps({"error": "EODHD token not configured"}))
        return 2
    database = Database(settings)
    from .market_data.service import MarketDataService  # the same HTTP client (timeouts/retries) the workers use
    service = PriceHistoryService(settings, database, MarketDataService(settings, database).http)
    if args.backfill:  # the manual, ordered path: no due BY DESIGN (it must never run inside the phase window — docs)
        result = service.backfill(args.market, months=args.months, symbols=symbols)
    else:
        result = service.nightly(args.market, due=due)
    summary = {key: value for key, value in result.items() if key not in {"series_sha256", "series_bars", "rows_rejected"}}
    print(json.dumps(summary, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
