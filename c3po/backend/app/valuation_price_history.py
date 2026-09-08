"""The persisted daily price series of the Valuation Engine V3.2 (rev 7, §2.2 "Série de rótulos", §9.2).

The V2/V3 engines never consumed a price series (``price`` is the spot of the universe row). V3.2 needs one for the
realized-error labels ``P_real(T + h)``, for the weekly panel and — with the 36-month backfill the owner ordered on
07/09/2026 — for the point-in-time re-execution (B2). This module PRODUCES and READS that series; it computes no
label arithmetic beyond locating the bar ``h`` sessions after a session on the exchange calendar.

Contract (rev 7 §2.2), rev 2 of the implementation (Codex C394-1..5):
* one bar per (market, symbol, session) with ``close`` and ``adjusted_close`` (both mandatory), ``currency``,
  ``source`` (EODHD ``/api/eod`` for every market — the single source declared in the inventory), ``fetched_at`` and a
  canonical CONTENT hash (``bar_sha256`` excludes the clock, so an unchanged bar is recognised across runs);
* **one vintage per market and cut.** Every run (backfill or nightly) re-fetches the WHOLE window for the whole coverage
  set and leaves a manifest snapshot ``valuation_price_history/<M>`` whose ``published_at`` = ``fetched_at`` of the run
  = the instant the vintage became available (stamped AFTER the last provider answer, never before the requests). The
  manifest carries one series hash per symbol. A reader with cut ``C`` resolves the single vintage ``S`` = the manifest
  with the greatest ``fetched_at < C`` and serves a symbol only if the bars reproduce the series hash ``S`` recorded
  for it — a symbol absent from ``S`` is refused, never completed from an older vintage (§2.2: both dates of a label
  come from the same snapshot);
* storage is content-deduplicated: a run inserts only bars whose content differs from the latest row of the same
  (market, symbol, session, source); the vintage is reproduced by "latest row with ``fetched_at`` ≤ ``S.fetched_at``"
  inside the run's window and verified by the per-symbol hash (a provider that silently drops a session makes that
  symbol ``unreproducible`` in ``S``: recorded in the manifest, refused by the readers);
* the manifest and the bars are written in ONE transaction (the bars reference the manifest by FK);
* coverage = the current universe of the market ∪ every symbol that has V3 shadow evaluations (labels still to come);
* a label is only ``labelled`` when the target session has CLOSED before the cut (exchange calendar close, not the
  civil date) and the vintage has a bar for it;
* OFF by default: the worker phase runs only with ``C3PO_VALUATION_PRICE_HISTORY_ENABLED=true``; the backfill is an
  explicit, one-shot CLI invocation under the mesa's order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

import exchange_calendars as xcals
from exchange_calendars.errors import RequestedSessionOutOfBounds

from .config import Settings, get_settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_price_history"
SCHEMA_VERSION = "VALUATION-PRICE-HISTORY-v2"
SOURCE = "eodhd:/api/eod"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
CALENDARS = {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"}
PROVIDER_SUFFIX = {"B3": "SA", "NASDAQ": "US", "NYSE": "US"}
CURRENCY = {"B3": "BRL", "NASDAQ": "USD", "NYSE": "USD"}
DEFAULT_BACKFILL_MONTHS = 36
_SERIES_CACHE_SIZE = 256
_calendars: dict[str, Any] = {}


def _calendar(market: str) -> Any:
    name = CALENDARS[market]
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def _utc(value: datetime) -> datetime:
    """Always UTC: a naive value is taken as UTC; an aware value is converted (never left in its own zone)."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def bar_record(market: str, symbol: str, provider_symbol: str, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """One immutable bar without its clock: ``bar_sha256`` hashes the CONTENT (market, symbol, session, both closes, volume,
    currency, source, provider symbol), so the same bar fetched twice has the same hash and is stored once. ``None`` when
    the provider row is unusable (both closes are mandatory, §2.2). ``fetched_at``/``snapshot_id`` are stamped by the run."""
    close, adjusted = _number(raw.get("close")), _number(raw.get("adjusted_close"))
    session = str(raw.get("date") or "")[:10]
    if not session or close is None or close <= 0 or adjusted is None or adjusted <= 0:
        return None
    try:
        date.fromisoformat(session)
    except ValueError:
        return None
    core = {"schema": SCHEMA_VERSION, "market": market, "symbol": symbol, "session_date": session, "close": close, "adjusted_close": adjusted,
            "volume": _number(raw.get("volume")), "currency": CURRENCY[market], "source": SOURCE, "provider_symbol": provider_symbol}
    return {**core, "id": str(uuid4()), "bar_sha256": canonical_sha256(core)}


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


class PriceHistoryService:
    """Producer and reader of `valuation_price_history/<M>`."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient, *, eodhd: EodhdClient | None = None) -> None:
        self.settings = settings
        self.database = database
        self.eodhd = eodhd or EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self._series_cache: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    # ------------------------------------------------------------------ coverage
    def coverage_symbols(self, market: str) -> list[str]:
        """Current universe rows ∪ every symbol with V3 shadow evaluations (labels still to come) — never fewer (§2.2)."""
        symbols: set[str] = set()
        universe = self.database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        outputs = universe.get("outputs") if universe and isinstance(universe.get("outputs"), dict) else {}
        raw_rows = outputs.get("rows") if isinstance(outputs, dict) else None
        rows: list[Any] = raw_rows if isinstance(raw_rows, list) else []
        for row in rows:
            if isinstance(row, dict) and row.get("symbol"):
                symbols.add(str(row["symbol"]).strip().upper())
        symbols.update(self.database.v3_shadow_symbols(market))
        return sorted(symbols)

    def window_months(self) -> int:
        return int(getattr(self.settings, "valuation_price_history_backfill_months", DEFAULT_BACKFILL_MONTHS))

    # ------------------------------------------------------------------ producer
    def fetch_bars(self, market: str, symbol: str, *, start: date, end: date) -> tuple[list[dict[str, Any]], int]:
        """Bars for one symbol plus the count of provider rows REJECTED as incomplete (a close missing): the provider answered,
        the series refused — recorded in the manifest, never a silent gap. The provider symbol used in the request is the one
        persisted (a ticker with a dot is passed already suffixed, so both agree). Rows outside [start, end] are dropped."""
        provider_symbol = f"{symbol}.{PROVIDER_SUFFIX[market]}"
        raw_rows = self.eodhd.daily_bars(provider_symbol, exchange=PROVIDER_SUFFIX[market], start=start, end=end) or []
        bars: list[dict[str, Any]] = []
        rejected = 0
        for raw in raw_rows:
            bar = bar_record(market, symbol, provider_symbol, raw)
            if bar is None:
                rejected += 1
            elif start.isoformat() <= bar["session_date"] <= end.isoformat():
                bars.append(bar)
        return bars, rejected

    def persist_run(self, market: str, *, start: date, end: date, symbols: Iterable[str], now: datetime | None = None, workers: int = 8,
                    mode: str = "nightly", clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """Fetch the whole window for ``symbols`` and persist ONE vintage: manifest + changed bars in a single transaction.
        ``started_at`` is read before the first request and ``fetched_at`` (= availability of the vintage, the clock every
        reader compares with its cut) AFTER the last answer — a cut between the two never sees this vintage."""
        tick: Callable[[], datetime] = clock or ((lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)))  # type: ignore[return-value]
        started_at = _utc(tick())
        wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        fetched: dict[str, list[dict[str, Any]]] = {}
        missing: list[str] = []
        errors: dict[str, str] = {}
        rejected: dict[str, int] = {}

        def fetch(symbol: str) -> tuple[str, list[dict[str, Any]], int, str | None]:
            try:
                rows, incomplete = self.fetch_bars(market, symbol, start=start, end=end)
                return symbol, rows, incomplete, None
            except Exception as error:  # the provider's failure is evidence, never a silent gap
                return symbol, [], 0, f"{type(error).__name__}"

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
        snapshot_id = str(uuid4())
        # content dedup against the latest stored row per (symbol, session); a session the provider DROPPED from a symbol
        # would survive in the chain read and break the series hash — recorded as unreproducible, refused by the readers
        latest = self.database.latest_price_bar_hashes(market, list(fetched), source=SOURCE)
        to_insert: list[dict[str, Any]] = []
        unchanged = 0
        series_hashes: dict[str, str] = {}
        series_bars: dict[str, int] = {}
        unreproducible: dict[str, list[str]] = {}
        for symbol, rows in fetched.items():
            by_session: dict[str, dict[str, Any]] = {}
            for bar in rows:  # a duplicate session in one provider answer: the first row wins (same rule as ON CONFLICT DO NOTHING)
                by_session.setdefault(bar["session_date"], bar)
            stale = sorted(session for (sym, session) in latest if sym == symbol and start.isoformat() <= session <= end.isoformat()
                           and session not in by_session)
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
        all_bars = [bar for rows in fetched.values() for bar in rows]
        sessions = sorted({bar["session_date"] for bar in all_bars})
        manifest_inputs = {"schema_version": SCHEMA_VERSION, "market": market, "source": SOURCE, "mode": mode, "from": start.isoformat(), "to": end.isoformat(),
                           "symbols_requested": len(wanted), "started_at": started_at.isoformat(), "fetched_at": fetched_at.isoformat(),
                           "calendar": {"name": CALENDARS[market], "exchange_calendars": getattr(xcals, "__version__", "unknown")}}
        manifest_outputs = {"schema_version": SCHEMA_VERSION, "price_snapshot_id": snapshot_id, "bars": sum(series_bars.values()),
                            "bars_inserted": len(to_insert), "bars_unchanged": unchanged,
                            "symbols_with_bars": len(fetched), "symbols_missing": sorted(missing), "errors": errors,
                            "rows_rejected_incomplete": dict(sorted(rejected.items())), "rows_rejected_total": sum(rejected.values()),
                            "symbols_unreproducible": dict(sorted(unreproducible.items())),
                            "first_session": sessions[0] if sessions else None, "last_session": sessions[-1] if sessions else None,
                            "series_sha256": dict(sorted(series_hashes.items())), "series_bars": dict(sorted(series_bars.items())),
                            "bars_sha256": canonical_sha256(sorted(series_hashes.items()))}
        inserted = self.database.persist_price_history_run(ANALYSIS_TYPE, market, self._methodology_id(), manifest_inputs, manifest_outputs, fetched_at,
                                                           snapshot_id, to_insert)
        logger.info("valuation_price_history %s %s: %s bars (%s inserted, %s unchanged), %s symbols missing, %s rows rejected, %s unreproducible",
                    market, mode, manifest_outputs["bars"], inserted, unchanged, len(missing), sum(rejected.values()), len(unreproducible))
        return {"market": market, "mode": mode, "started_at": started_at.isoformat(), "fetched_at": fetched_at.isoformat(), **manifest_outputs,
                "bars_inserted": inserted}

    def _methodology_id(self) -> str:
        return self.database.ensure_methodology_version("valuation_price_history", 2, {"schema": SCHEMA_VERSION, "source": SOURCE},
                                                        "Persisted daily price series for V3.2 labels (rev 7 §2.2): one vintage per run")

    def backfill(self, market: str, *, months: int | None = None, now: datetime | None = None, symbols: Iterable[str] | None = None,
                 clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """The one-shot history (owner's decision of 07/09/2026): bars persisted now carry ``fetched_at`` = now, so only
        packages cut AFTER it may consume them (rev 7 §2.2) — history for training, never a look-ahead. The window defaults
        to ``settings.valuation_price_history_backfill_months``."""
        months = int(months if months is not None else self.window_months())
        end = _utc(now if now is not None else (clock() if clock else datetime.now(timezone.utc))).date()
        return self.persist_run(market, start=window_start(end, months), end=end, symbols=symbols if symbols is not None else self.coverage_symbols(market),
                                now=now, mode="backfill", clock=clock)

    def nightly(self, market: str, *, now: datetime | None = None, clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """The nightly vintage: the WHOLE window again (one provider call per symbol, as the backfill), so that every cut has
        one self-contained vintage; unchanged bars cost no storage."""
        end = _utc(now if now is not None else (clock() if clock else datetime.now(timezone.utc))).date()
        return self.persist_run(market, start=window_start(end, self.window_months()), end=end, symbols=self.coverage_symbols(market), now=now,
                                mode="nightly", clock=clock)

    def run_all(self, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        return {market: self.nightly(market, now=now) for market in MARKETS}

    def last_run_at(self) -> datetime | None:
        stamps = [self.database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, market) for market in MARKETS]
        present = [stamp for stamp in stamps if stamp is not None]
        return min(present) if len(present) == len(MARKETS) else None

    # ------------------------------------------------------------------ readers (the clock is a parameter, never "now")
    def vintage(self, market: str, *, fetched_before: datetime) -> dict[str, Any] | None:
        """The single vintage a cut sees: the manifest with the greatest ``fetched_at < fetched_before`` (rev 7 §2.2 rule)."""
        manifest = self.database.latest_analysis_snapshot_before(ANALYSIS_TYPE, market, _utc(fetched_before))
        if not manifest:
            return None
        inputs = manifest.get("inputs") if isinstance(manifest.get("inputs"), dict) else {}
        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
        if not isinstance(inputs, dict) or not isinstance(outputs, dict) or outputs.get("schema_version") != SCHEMA_VERSION:
            return None
        return {"price_snapshot_id": str(manifest["id"]), "fetched_at": str(inputs.get("fetched_at")), "from": str(inputs.get("from")), "to": str(inputs.get("to")),
                "series_sha256": dict(outputs.get("series_sha256") or {}), "series_bars": dict(outputs.get("series_bars") or {}),
                "symbols_unreproducible": dict(outputs.get("symbols_unreproducible") or {}), "bars_sha256": outputs.get("bars_sha256")}

    def series(self, market: str, symbol: str, *, fetched_before: datetime) -> dict[str, Any]:
        """One symbol's bars from the single vintage the cut sees, verified against the hash that vintage recorded for it.
        Statuses: ``ok``; ``no_vintage`` (nothing fetched before the cut); ``symbol_not_in_vintage`` (the vintage has no
        series for it — never completed from an older one); ``vintage_unreproducible`` (declared by the run itself);
        ``vintage_mismatch`` (the stored rows do not reproduce the recorded hash: refused)."""
        symbol = symbol.strip().upper()
        vintage = self.vintage(market, fetched_before=fetched_before)
        if vintage is None:
            return {"status": "no_vintage", "price_snapshot_id": None, "fetched_at": None, "bars": {}}
        key = (vintage["price_snapshot_id"], f"{market}:{symbol}")
        cached = self._series_cache.get(key)
        if cached is not None:
            self._series_cache.move_to_end(key)
            return dict(cached)
        header = {"price_snapshot_id": vintage["price_snapshot_id"], "fetched_at": vintage["fetched_at"]}
        expected = vintage["series_sha256"].get(symbol)
        if expected is None:
            result = {"status": "symbol_not_in_vintage", **header, "bars": {}}
        elif symbol in vintage["symbols_unreproducible"]:
            result = {"status": "vintage_unreproducible", **header, "bars": {}}
        else:
            bars = self.database.price_bars(market, symbol, as_of=datetime.fromisoformat(vintage["fetched_at"]),
                                            since=date.fromisoformat(vintage["from"]), until=date.fromisoformat(vintage["to"]))
            if series_sha256(bars.values()) != expected:
                result = {"status": "vintage_mismatch", **header, "bars": {}}
            else:
                result = {"status": "ok", **header, "bars": bars}
        self._series_cache[key] = result
        while len(self._series_cache) > _SERIES_CACHE_SIZE:
            self._series_cache.popitem(last=False)
        return dict(result)

    def bars(self, market: str, symbol: str, *, fetched_before: datetime) -> dict[str, dict[str, Any]]:
        """Bars by session as the cut sees them (empty when the vintage refuses the symbol — use ``series`` for the reason)."""
        return self.series(market, symbol, fetched_before=fetched_before)["bars"]

    def label_bar(self, market: str, symbol: str, session: date, horizon_sessions: int, *, fetched_before: datetime) -> dict[str, Any]:
        """The bar ``h`` sessions after ``session`` (the label of a prediction made at ``session``), as known before the cut.
        ``not_yet_mature`` until the target session has CLOSED before the cut; then the vintage's status; ``missing_bar``
        when the exchange had the session and the vintage has the symbol but no bar for it. Never a price from elsewhere."""
        cut = _utc(fetched_before)
        target, reason = sessions_after(market, session, horizon_sessions)
        if target is None:
            return {"session": None, "status": reason}
        if session_close(market, target) >= cut:
            return {"session": target.isoformat(), "status": "not_yet_mature"}
        known = self.series(market, symbol, fetched_before=cut)
        header = {"session": target.isoformat(), "price_snapshot_id": known["price_snapshot_id"]}
        if known["status"] != "ok":
            return {**header, "status": known["status"]}
        bar = known["bars"].get(target.isoformat())
        if not bar:
            return {**header, "status": "missing_bar"}
        return {**header, "status": "labelled", "close": bar["close"], "adjusted_close": bar["adjusted_close"], "bar_sha256": bar["bar_sha256"],
                "fetched_at": bar["fetched_at"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 price series (rev 7 §2.2): backfill or nightly vintage; OFF unless invoked.")
    parser.add_argument("--market", choices=MARKETS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true", help="one-shot history (months from --months), bars stamped fetched_at = now")
    group.add_argument("--nightly", action="store_true", help="the nightly vintage (whole window, coverage set)")
    parser.add_argument("--months", type=int, default=None, help="defaults to C3PO_VALUATION_PRICE_HISTORY_BACKFILL_MONTHS (36)")
    parser.add_argument("--symbols", default="", help="comma-separated override of the coverage set (tests/dry runs)")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.eodhd_api_token:
        print(json.dumps({"error": "EODHD token not configured"}))
        return 2
    database = Database(settings)
    from .market_data.service import MarketDataService  # the same HTTP client (timeouts/retries) the workers use
    service = PriceHistoryService(settings, database, MarketDataService(settings, database).http)
    symbols = [s for s in args.symbols.split(",") if s.strip()] or None
    result = service.backfill(args.market, months=args.months, symbols=symbols) if args.backfill else service.nightly(args.market)
    summary = {key: value for key, value in result.items() if key not in {"series_sha256", "series_bars"}}
    print(json.dumps(summary, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
