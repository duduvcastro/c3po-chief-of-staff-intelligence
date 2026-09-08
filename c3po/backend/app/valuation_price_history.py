"""The persisted daily price series of the Valuation Engine V3.2 (rev 7, §2.2 "Série de rótulos", §9.2).

The V2/V3 engines never consumed a price series (``price`` is the spot of the universe row). V3.2 needs one for the
realized-error labels ``P_real(T + h)``, for the weekly panel and — with the 36-month backfill the owner ordered on
07/09/2026 — for the point-in-time re-execution (B2). This module PRODUCES and READS that series; it computes no
label arithmetic beyond locating the bar ``h`` sessions after a session on the exchange calendar.

Contract (rev 7 §2.2):
* one bar per (market, symbol, session) with ``close`` and ``adjusted_close`` (both mandatory), ``currency``,
  ``source`` (EODHD ``/api/eod`` for every market — the single source declared in the inventory), ``fetched_at`` and a
  canonical hash; every run leaves a manifest snapshot ``valuation_price_history/<M>`` in ``analysis_snapshots``;
* coverage = the current universe of the market ∪ every symbol that has V3 shadow evaluations (labels still to come);
* a package cut ``C`` consumes only bars with ``fetched_at < C`` — the readers take that clock as a parameter and
  never fetch live; a re-fetch is a new row, never an update (append-only table, migration 049);
* OFF by default: the worker phase runs only with ``C3PO_VALUATION_PRICE_HISTORY_ENABLED=true``; the backfill is an
  explicit, one-shot CLI invocation under the mesa's order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4

import exchange_calendars as xcals

from .config import Settings, get_settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_price_history"
SCHEMA_VERSION = "VALUATION-PRICE-HISTORY-v1"
SOURCE = "eodhd:/api/eod"
MARKETS: tuple[str, ...] = ("B3", "NASDAQ", "NYSE")
CALENDARS = {"B3": "BVMF", "NASDAQ": "XNYS", "NYSE": "XNYS"}
PROVIDER_SUFFIX = {"B3": "SA", "NASDAQ": "US", "NYSE": "US"}
CURRENCY = {"B3": "BRL", "NASDAQ": "USD", "NYSE": "USD"}
NIGHTLY_LOOKBACK_SESSIONS = 10
DEFAULT_BACKFILL_MONTHS = 36
_calendars: dict[str, Any] = {}


def _calendar(market: str) -> Any:
    name = CALENDARS[market]
    if name not in _calendars:
        _calendars[name] = xcals.get_calendar(name)
    return _calendars[name]


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


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


def bar_record(market: str, symbol: str, provider_symbol: str, raw: Mapping[str, Any], *, fetched_at: datetime) -> dict[str, Any] | None:
    """One immutable bar. ``None`` when the provider row is unusable (both closes are mandatory, §2.2)."""
    close, adjusted = _number(raw.get("close")), _number(raw.get("adjusted_close"))
    session = str(raw.get("date") or "")[:10]
    if not session or close is None or close <= 0 or adjusted is None or adjusted <= 0:
        return None
    try:
        date.fromisoformat(session)
    except ValueError:
        return None
    core = {"schema": SCHEMA_VERSION, "market": market, "symbol": symbol, "session_date": session, "close": close, "adjusted_close": adjusted,
            "volume": _number(raw.get("volume")), "currency": CURRENCY[market], "source": SOURCE, "provider_symbol": provider_symbol,
            "fetched_at": _utc(fetched_at).isoformat()}
    return {**core, "id": str(uuid4()), "bar_sha256": canonical_sha256(core)}


def sessions_after(market: str, session: date, count: int) -> date | None:
    """The session ``count`` trading sessions after ``session`` on the market's calendar (``None`` beyond the calendar)."""
    calendar = _calendar(market)
    try:
        return calendar.session_offset(session.isoformat(), count).date()
    except (ValueError, IndexError, KeyError):
        return None
    except Exception:  # exchange_calendars raises its own error types for out-of-range dates
        return None


def previous_sessions(market: str, until: date, count: int) -> date:
    calendar = _calendar(market)
    try:
        anchor = calendar.date_to_session(until.isoformat(), direction="previous")
        return calendar.session_offset(anchor, -count).date()
    except Exception:
        return until - timedelta(days=count * 2)


class PriceHistoryService:
    """Producer and reader of `valuation_price_history/<M>`."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient, *, eodhd: EodhdClient | None = None) -> None:
        self.settings = settings
        self.database = database
        self.eodhd = eodhd or EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)

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

    # ------------------------------------------------------------------ producer
    def fetch_bars(self, market: str, symbol: str, *, start: date, end: date, fetched_at: datetime) -> list[dict[str, Any]]:
        provider_symbol = f"{symbol}.{PROVIDER_SUFFIX[market]}"
        raw_rows = self.eodhd.daily_bars(symbol, exchange=PROVIDER_SUFFIX[market], start=start, end=end) or []
        bars = [bar for bar in (bar_record(market, symbol, provider_symbol, raw, fetched_at=fetched_at) for raw in raw_rows) if bar is not None]
        return bars

    def persist_run(self, market: str, *, start: date, end: date, symbols: Iterable[str], now: datetime | None = None, workers: int = 8,
                    mode: str = "nightly") -> dict[str, Any]:
        """Fetch and persist the bars of ``symbols`` for [start, end]; one manifest snapshot per run, one ``fetched_at`` for the
        whole run (the clock every reader compares with its cut)."""
        fetched_at = _utc(now or datetime.now(timezone.utc))
        wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        bars: list[dict[str, Any]] = []
        missing: list[str] = []
        errors: dict[str, str] = {}

        def fetch(symbol: str) -> tuple[str, list[dict[str, Any]], str | None]:
            try:
                return symbol, self.fetch_bars(market, symbol, start=start, end=end, fetched_at=fetched_at), None
            except Exception as error:  # the provider's failure is evidence, never a silent gap
                return symbol, [], f"{type(error).__name__}"

        with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
            for symbol, rows, error in executor.map(fetch, wanted):
                if error:
                    errors[symbol] = error
                if not rows:
                    missing.append(symbol)
                bars.extend(rows)
        snapshot_id = str(uuid4())
        for bar in bars:
            bar["snapshot_id"] = snapshot_id
        inserted = self.database.insert_price_bars(bars)
        sessions = sorted({bar["session_date"] for bar in bars})
        manifest_inputs = {"schema_version": SCHEMA_VERSION, "market": market, "source": SOURCE, "mode": mode, "from": start.isoformat(), "to": end.isoformat(),
                           "symbols_requested": len(wanted), "fetched_at": fetched_at.isoformat()}
        manifest_outputs = {"schema_version": SCHEMA_VERSION, "price_snapshot_id": snapshot_id, "bars": len(bars), "bars_inserted": inserted,
                            "symbols_with_bars": len(wanted) - len(missing), "symbols_missing": sorted(missing), "errors": errors,
                            "first_session": sessions[0] if sessions else None, "last_session": sessions[-1] if sessions else None,
                            "bars_sha256": canonical_sha256(sorted(bar["bar_sha256"] for bar in bars))}
        self.database.save_analysis_snapshot(ANALYSIS_TYPE, market, self._methodology_id(), manifest_inputs, manifest_outputs, fetched_at,
                                             snapshot_id=snapshot_id)
        logger.info("valuation_price_history %s %s: %s bars (%s inserted), %s symbols missing", market, mode, len(bars), inserted, len(missing))
        return {"market": market, "mode": mode, "price_snapshot_id": snapshot_id, "fetched_at": fetched_at.isoformat(), **manifest_outputs}

    def _methodology_id(self) -> str:
        return self.database.ensure_methodology_version("valuation_price_history", 1, {"schema": SCHEMA_VERSION, "source": SOURCE},
                                                        "Persisted daily price series for V3.2 labels (rev 7 §2.2)")

    def backfill(self, market: str, *, months: int = DEFAULT_BACKFILL_MONTHS, now: datetime | None = None, symbols: Iterable[str] | None = None) -> dict[str, Any]:
        """The one-shot 36-month backfill (owner's decision of 07/09/2026): bars persisted now carry ``fetched_at`` = now,
        so only packages cut AFTER it may consume them (rev 7 §2.2) — history for training, never a look-ahead."""
        end = (_utc(now or datetime.now(timezone.utc))).date()
        start = date(end.year - (months // 12), end.month, 1) - timedelta(days=(months % 12) * 31)
        return self.persist_run(market, start=start, end=end, symbols=symbols if symbols is not None else self.coverage_symbols(market), now=now, mode="backfill")

    def nightly(self, market: str, *, now: datetime | None = None) -> dict[str, Any]:
        """The nightly persistence: the last sessions of the coverage set (late corrections included)."""
        end = (_utc(now or datetime.now(timezone.utc))).date()
        start = previous_sessions(market, end, NIGHTLY_LOOKBACK_SESSIONS)
        return self.persist_run(market, start=start, end=end, symbols=self.coverage_symbols(market), now=now, mode="nightly")

    def run_all(self, *, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        return {market: self.nightly(market, now=now) for market in MARKETS}

    def last_run_at(self) -> datetime | None:
        stamps = [self.database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, market) for market in MARKETS]
        present = [stamp for stamp in stamps if stamp is not None]
        return min(present) if len(present) == len(MARKETS) else None

    # ------------------------------------------------------------------ readers (the clock is a parameter, never "now")
    def bars(self, market: str, symbol: str, *, fetched_before: datetime, since: date | None = None, until: date | None = None) -> dict[str, dict[str, Any]]:
        """Bars by session for one symbol as they were known before ``fetched_before``: for each session the latest row with
        ``fetched_at < fetched_before`` — the reproducible view a package cut at that instant sees."""
        return self.database.price_bars(market, symbol.strip().upper(), fetched_before=_utc(fetched_before), since=since, until=until)

    def label_bar(self, market: str, symbol: str, session: date, horizon_sessions: int, *, fetched_before: datetime) -> dict[str, Any]:
        """The bar ``h`` sessions after ``session`` (the label of a prediction made at ``session``), as known before the cut.
        Never a price from elsewhere: ``missing_bar`` when the exchange had a session but the series has no bar for it."""
        target = sessions_after(market, session, horizon_sessions)
        if target is None:
            return {"session": None, "status": "beyond_calendar"}
        if target > _utc(fetched_before).date():
            return {"session": target.isoformat(), "status": "not_yet_mature"}
        known = self.bars(market, symbol, fetched_before=fetched_before, since=target, until=target)
        bar = known.get(target.isoformat())
        if not bar:
            return {"session": target.isoformat(), "status": "missing_bar"}
        return {"session": target.isoformat(), "status": "labelled", "close": bar["close"], "adjusted_close": bar["adjusted_close"],
                "bar_sha256": bar["bar_sha256"], "fetched_at": bar["fetched_at"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 price series (rev 7 §2.2): backfill or nightly persistence; OFF unless invoked.")
    parser.add_argument("--market", choices=MARKETS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backfill", action="store_true", help="one-shot history (months from --months), bars stamped fetched_at = now")
    group.add_argument("--nightly", action="store_true", help="last sessions of the coverage set")
    parser.add_argument("--months", type=int, default=DEFAULT_BACKFILL_MONTHS)
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
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
