"""The SERVED internal TP re-executed point-in-time (``official_internal_pit``): the second source of the US PIT backtest
(PREREG_VALUATION_PIT_BACKTEST_US_V1 rev 2). DIAGNOSTIC: nothing here is served, selectable, a gate or a promotion.

Why (owner, 19/10/2026): from Tue 20/10 the TP SERVED is ``official_internal_v1`` — the US producer's internal TP, the
mean of the five One Pager methods × the calibration factor (``market_data.us_screener.USScreeningService._analyze_stock``
→ ``one_pager.OnePagerService._analyze(role="producer")``), consensus never inside. ``valuation_pit_rerun`` re-executes
the V3.2 SHADOW engine instead; the Friday verdict must answer about the TP that is served. This module re-executes THAT
producer at each grid ``T``:

* **The same point-in-time inputs as the V3 run** — the re-executor's own resolver (``valuation_pit_rerun.PitSourceResolver``,
  subclassed only to keep the statements payload it already reads): the pinned price vintage (as-traded close, the PIT beta
  against the equal-weight proxy), the as-filed statements of ``statement_vintages`` accepted at or before ``T``
  (``--statements vintages``), the pinned catalogue's classification, the US curve at ``T``; the same names are evaluable
  (the resolver's refusals are this run's refusals) and the same screen inputs are recorded.
* **The provider shape, rebuilt from PIT data only** — an EODHD-shaped payload (``General`` from the catalogue,
  ``Highlights``/``Valuation``/``Technicals``/``SharesStats`` recomputed from the statements eligible at ``T`` and the price at
  ``T``, ``Financials`` = the eligible rows only, ``Earnings.History`` = the dated rows reported by the session of ``T`` when
  the statements payload carries them) normalised by the LIVE normaliser (``EodhdClient._normalize_fundamentals``), then
  the LIVE producer (``USScreeningService._analyze_stock`` on a store view that answers the calibration snapshot published
  before ``T``) — by import, never a copy of a formula.
* **Peer medians at ``T``** — ``OnePagerService._us_peer_medians`` over the PIT fundamentals of the run's own stocks (one
  exchange, as the live build of that exchange).
* **Absent, declared and counted** (``PIT_ABSENT_INPUTS``): analyst estimates (forward EPS → the One Pager's trailing EPS,
  earnings trend, EPS revisions), the consensus and the ratings (never inside the internal TP anyway), news sentiment,
  insider activity, institutional positions, recent grades; the earnings surprise when the statements payload carries no
  dated history (always under ``--statements vintages``: the as-filed payload has none).

Records (``SOURCE`` = ``official_internal_pit``): the canonical record shape of ``valuation_official.prediction_from_row``
for the INTERNAL source (``tp`` = the internal TP, ``buy_in`` = its own buy-in, consensus weight 0), relabelled to this
source and re-hashed — and kept INSIDE this run's snapshot (``outputs.records``), never in ``valuation_predictions``:
``RECORDABLE_SOURCES`` lives in ``valuation_official.py``, a file of the V3 producer's identity (``valuation_pit_rerun.
IMPLEMENTATION_FILES``, in every V3 ``run_key``) — making the table accept this source would change every V3 run. The
report reads them from the snapshots of the grid manifest; nothing selects them (the official selection reads
``OFFICIAL_SOURCES`` from the table only).

Identity (as the V3 run's): ``run_key = sha256(canonical([source_version, market, T, manifest]))``, the manifest naming the
producer (``IMPLEMENTATION_FILES`` — ``one_pager.py`` and ``market_data/us_screener.py`` among them, hashed only —, the
reader objects), every source reference, the price vintage, the macro, the risk-free rate, the calibration at ``T``, the
peer medians and the declared gaps; one snapshot per run (``ANALYSIS_TYPE``), idempotent by ``run_key``, a changed input
supersedes. No network, no clock in the economic computation.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, cast
from uuid import uuid4

from . import valuation_pit_rerun as pit
from .config import Settings, get_settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.us_screener import CALIBRATION_FACTOR_LIMIT, USMarket, USScreeningService, clamp
from .one_pager import OnePagerService
from .source_identity import objects_sha256
from .valuation_official import SOURCE_INTERNAL, canonical_sha256, prediction_from_row

SOURCE = "official_internal_pit"  # the served internal TP re-executed point-in-time: recorded in its runs' snapshots, never selectable
SERVED_SOURCE = SOURCE_INTERNAL  # the source it re-executes: official_internal_v1, the TP served from 20/10/2026
ANALYSIS_TYPE = "valuation_pit_served"  # one snapshot per run (inputs: run_key, market, as_of, supersedes?)
SCHEMA_VERSION = "VALUATION-PIT-SERVED-v1"
SOURCE_VERSION_PREFIX = "pit-served-v1"
METHODOLOGY_KEY = "valuation_pit_served"
METHODOLOGY_VERSION = 1
ENGINE_PATH = "market_data.us_screener.USScreeningService._analyze_stock -> one_pager.OnePagerService._analyze(role='producer')"
STOCK = "Stock"  # the producer path of a stock; the ETF path (_analyze_etf) is not re-executed (an ETF has no as-filed statements)
CALIBRATION_ANALYSIS_TYPE = "valuation_calibration"  # the US screener's own snapshot (<M>_POWER_MODEL), read as published BEFORE T
RISK_FREE_SYMBOL = "US10Y.GBOND"  # the live rate is the 10-year Treasury close (OnePagerService._us_risk_free_rate) ...
RISK_FREE_BOUNDS = (0.02, 0.08)  # ... clamped to [2 %, 8 %] there (inline literals of that method, mirrored and declared)
YOY_DAYS = (350, 380)  # the quarter one year before the latest one (EODHD's Quarterly…GrowthYOY): period ends one year apart
IMPLEMENTATION_FILES: tuple[str, ...] = (  # the producer a served run names (engine.implementation_file_sha256, in run_key): this module, the live producer
    # it calls (one_pager.py and market_data/us_screener.py — hashed only, one_pager.py is pinned by ORIGIN_ONE_PAGER_SHA256), the live normaliser,
    # the record writer and the buy-in rule, and the re-executor's resolver with its as-filed reader pieces, macro and price reader
    "valuation_pit_served.py", "one_pager.py", "market_data/us_screener.py", "market_data/eodhd.py", "valuation_official.py", "valuation_official_engine.py",
    "valuation_pit_rerun.py", "valuation_v3_macro.py", "sec_xbrl.py", "valuation_asfiled.py", "statement_vintages.py", "valuation_price_history.py",
)
IMPLEMENTATION_OBJECTS: tuple[str, ...] = pit.IMPLEMENTATION_OBJECTS  # the same Database readers (catalogue, sources, macro, calibration, prices, runs)
PIT_ABSENT_INPUTS: dict[str, str] = {  # what the live producer reads and no point-in-time history exists for: ABSENT, counted per name
    "forward_eps": "Highlights.EPSEstimateNextYear/EPSEstimateCurrentYear (analyst estimates): the One Pager's normalized EPS falls back to the trailing EPS",
    "earnings_trend": "Earnings.Trend (estimates and their 30-day revisions): eps_revision = 0 in method 4; the next-quarter estimate texts N/D",
    "consensus": "AnalystRatings / WallStreetTargetPrice / FMP price targets: never inside the internal TP; blend weight 0; confidence without it",
    "news_sentiment": "the weekly news sentiment: confidence only (never the TP)",
    "insider_activity": "the insider net signal: risk score -> risk_adjustment of methods 3 and 5 (neutral 0 here)",
    "institutional_positions": "the 13F conviction signal: risk score -> risk_adjustment (neutral 0 here)",
    "recent_grades": "the broker grades momentum: risk score -> risk_adjustment (neutral 0 here)",
    "earnings_surprise": "Earnings.History: only the rows reported by the session of T, when the statements payload carries them (never as filed: surprise 0)",
}
SERVED_ASSUMPTIONS: dict[str, str] = {  # how the provider shape is rebuilt from point-in-time data (declared, in the manifest)
    "provider_shape": "an EODHD-shaped payload rebuilt from PIT data only (General from the pinned catalogue; Highlights, Valuation, Technicals and "
                      "SharesStats recomputed at T; Financials = the statements rows eligible at T) normalised by EodhdClient._normalize_fundamentals",
    "highlights": "MarketCapitalization = close(T) x shares(T); DilutedEpsTTM = TTM net income / shares(T) (the cover-page count, not diluted); BookValue = "
                  "equity / shares; ReturnOnEquityTTM = TTM net income / latest equity; ProfitMargin and OperatingMarginTTM = TTM net / operating income "
                  "over TTM revenue; EBITDA and RevenueTTM = the TTM; Quarterly{Revenue,Earnings}GrowthYOY = the latest eligible quarter over the quarter one "
                  "year before (period ends 350-380 days apart), null without it or with a non-positive base",
    "valuation": "TrailingPE = close / EPS (EPS > 0); EnterpriseValueEbitda = (market cap + net debt) / TTM EBITDA (EBITDA > 0)",
    "beta": "the re-executor's OLS beta of daily log returns against the equal-weight proxy of the run's catalogue (live: the provider's Technicals.Beta)",
    "balance": "as filed the balance rows carry cashAndEquivalents and the debt split of valuation_asfiled.total_debt: the One Pager reads total cash "
               "and total debt from them (live EODHD rows: cashAndShortTermInvestments and shortLongTermDebtTotal)",
    "risk_free": "the 10-year point of the re-executor's US curve at T (the latest observation date with both tenors), clamped to [0.02, 0.08] as "
                 "OnePagerService._us_risk_free_rate clamps the live close",
    "peer_medians": "OnePagerService._us_peer_medians over the PIT fundamentals of the run's own stocks (one exchange, as the live build of an exchange)",
    "calibration": "the US screener's valuation_calibration/<M>_POWER_MODEL snapshot published strictly before T, read by its own loader "
                   "(USScreeningService._load_calibration_factors); none -> absent_at_T, factor 1.0",
    "history": "the price history is not passed to the producer: it feeds volatility_90d only (never the TP, never recorded)",
    "watchlist_inputs": "live, a watchlist name may also carry news sentiment and grades (+/-): the PIT version is the fundamentals-only served TP",
}
_PROVIDER_TYPE = "Common Stock"


class PitServedError(RuntimeError):
    pass


# ------------------------------------------------------------------ identity
def _file_sha256(name: str) -> str:
    return hashlib.sha256((Path(__file__).resolve().parent / name).read_bytes()).hexdigest()


@functools.cache
def _implementation_identity() -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """The producer of THIS process, computed once: the sha256 of every ``IMPLEMENTATION_FILES`` file and of every reader
    object (``source_identity``, from ``database.py``'s text — as the V3 re-executor hashes them)."""
    files = tuple((name, _file_sha256(name)) for name in IMPLEMENTATION_FILES)
    names = [qualified.split(".", 2)[2] for qualified in IMPLEMENTATION_OBJECTS]
    digests = objects_sha256((Path(__file__).resolve().parent / "database.py").read_text(encoding="utf-8"), names)
    return files, tuple((qualified, digests[qualified.split(".", 2)[2]]) for qualified in IMPLEMENTATION_OBJECTS)


def implementation_files() -> dict[str, str]:
    return dict(_implementation_identity()[0])


def implementation_objects() -> dict[str, str]:
    return dict(_implementation_identity()[1])


def producer() -> dict[str, Any]:
    """The served producer of this code: its files and reader objects, ``engine_sha256`` = canonical sha256 of both."""
    files, objects = implementation_files(), implementation_objects()
    return {"source_version": source_version(), "engine_files": files, "engine_objects": objects,
            "engine_sha256": canonical_sha256({"files": files, "objects": objects})}


def source_version() -> str:
    return f"{SOURCE_VERSION_PREFIX}+{_file_sha256('valuation_pit_served.py')[:12]}"


def engine_identity() -> str:
    """The producer the record names: the One Pager's and the US screener's bytes."""
    return f"official_internal_v1@one_pager:{_file_sha256('one_pager.py')[:12]}+us_screener:{_file_sha256('market_data/us_screener.py')[:12]}"


# ------------------------------------------------------------------ the provider shape, from point-in-time data
def _quarter_year_before(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> float | None:
    """EODHD's ``Quarterly…GrowthYOY`` at ``T``: the latest eligible quarter over the eligible quarter one year before it
    (period ends ``YOY_DAYS`` apart); ``None`` without either value or with a non-positive base."""
    if not rows:
        return None
    latest = rows[0]
    now = pit._first_number(latest["data"], *fields)
    low, high = YOY_DAYS
    before = next((pit._first_number(row["data"], *fields) for row in rows[1:] if low <= (latest["period_end"] - row["period_end"]).days <= high), None)
    if now is None or before is None or before <= 0:
        return None
    return now / before - 1


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def earnings_history_at(payload: Mapping[str, Any], *, session_date: str, excluded: Counter[str]) -> dict[str, Any]:
    """The dated earnings history the statements payload carries (``Earnings.History``, the provider payload only — the
    as-filed payload has none), restricted to the rows REPORTED by the session of ``T`` (``reportDate ≤ session``); a row
    without a report date is dropped and counted. ``{}`` (absent, counted) otherwise."""
    history = pit._mapping(pit._mapping(payload.get("Earnings")).get("History"))
    if not history:
        excluded["earnings_surprise:no_dated_history_in_the_statements_payload"] += 1
        return {}
    kept: dict[str, Any] = {}
    for key, entry in history.items():
        data = pit._mapping(entry)
        reported = pit._parse_date(data.get("reportDate"))
        if reported is None:
            excluded["earnings_surprise:row_without_report_date"] += 1
        elif reported.isoformat() > session_date:
            excluded["earnings_surprise:reported_after_T"] += 1
        else:
            kept[str(key)] = dict(data)
    return kept


def provider_payload_at(symbol: str, payload: Mapping[str, Any], item: Mapping[str, Any], *, market: str, economic_date: date, session_date: str,
                        excluded: Counter[str]) -> dict[str, Any]:
    """The EODHD-shaped payload of ONE name at ``T``, from point-in-time data only (``SERVED_ASSUMPTIONS``): the statements
    payload the resolver read (as filed, or the provider's), cut to the rows eligible at ``T`` by the re-executor's own rule
    (``eligible_statements``), and the derived blocks recomputed from them and from the resolver's row (price at ``T``,
    shares, EPS, book value, ROE, beta, P/E, EV/EBITDA). No current block of any provider payload is read."""
    statements = pit.eligible_statements(payload, market=market, economic_date=economic_date, excluded=Counter())  # the resolver already counted them
    fundamentals = pit.pit_fundamentals(payload, market=market, economic_date=economic_date)
    row = item["row"]
    ttm = fundamentals["ttm"]
    income_q = statements["Income_Statement"]["quarterly"]
    financials = {statement: {frequency: {entry["period_end"].isoformat(): dict(entry["data"]) for entry in rows} for frequency, rows in by_frequency.items()}
                  for statement, by_frequency in statements.items()}
    highlights = {"MarketCapitalization": row.get("market_cap"), "DilutedEpsTTM": row.get("eps"), "BookValue": row.get("book_value"),
                  "ReturnOnEquityTTM": row.get("roe"), "ProfitMargin": _ratio(ttm.get("net_income"), ttm.get("revenue")),
                  "OperatingMarginTTM": _ratio(ttm.get("operating_income"), ttm.get("revenue")), "EBITDA": ttm.get("ebitda"), "RevenueTTM": ttm.get("revenue"),
                  "QuarterlyRevenueGrowthYOY": _quarter_year_before(income_q, pit.INCOME_FIELDS["revenue"]),
                  "QuarterlyEarningsGrowthYOY": _quarter_year_before(income_q, pit.INCOME_FIELDS["net_income"])}
    return {"General": {"Code": symbol, "Name": symbol, "Sector": row.get("sector") or "", "Industry": row.get("industry") or "", "Type": _PROVIDER_TYPE},
            "Highlights": highlights, "Valuation": {"TrailingPE": row.get("pe"), "EnterpriseValueEbitda": row.get("ev_ebitda")},
            "Technicals": {"Beta": row.get("beta")}, "SharesStats": {"SharesOutstanding": row.get("shares")}, "AnalystRatings": {},
            "Earnings": {"History": earnings_history_at(payload, session_date=session_date, excluded=excluded)}, "Financials": financials}


def fundamentals_at(symbol: str, payload: Mapping[str, Any], item: Mapping[str, Any], *, market: str, economic_date: date, session_date: str,
                    excluded: Counter[str]) -> dict[str, Any]:
    """The provider-normalised fundamentals the live producer reads (``EodhdClient._normalize_fundamentals``, by import) of
    the point-in-time payload (``provider_payload_at``)."""
    return EodhdClient._normalize_fundamentals(provider_payload_at(symbol, payload, item, market=market, economic_date=economic_date,
                                                                   session_date=session_date, excluded=excluded))


# ------------------------------------------------------------------ the live producer, on point-in-time inputs
class _StoreAtT:
    """The store as the US screener's calibration loader reads it at ``T``: ``latest_analysis_snapshot`` answers the
    snapshot published STRICTLY before ``T`` (``latest_analysis_snapshot_before``) and remembers it; nothing else."""

    def __init__(self, database: Database, as_of: datetime) -> None:
        self._database = database
        self._as_of = pit._utc(as_of)
        self.read: dict[str, Any] | None = None

    def latest_analysis_snapshot(self, analysis_type: str, entity_key: str) -> dict[str, Any] | None:
        self.read = self._database.latest_analysis_snapshot_before(analysis_type, entity_key, self._as_of)
        return self.read


def live_producer(store: Any = None, *, calibration_factors: Mapping[str, Mapping[str, float]] | None = None) -> USScreeningService:
    """The live US producer with no provider behind it: ``USScreeningService`` and ``OnePagerService`` instances whose only
    state is what ``_analyze_stock`` reads (the calibration factors per exchange, the One Pager in the producer role — which
    reads no settings, store or network). Every number comes from their own methods."""
    one_pager = OnePagerService.__new__(OnePagerService)
    one_pager._us_risk_free_cache = None
    screener = USScreeningService.__new__(USScreeningService)
    screener.one_pagers = one_pager
    screener.database = cast(Database, store)
    screener._calibration_factors = {"NASDAQ": dict((calibration_factors or {}).get("NASDAQ", {})), "NYSE": dict((calibration_factors or {}).get("NYSE", {}))}
    return screener


def calibration_at(database: Database, market: str, as_of: datetime) -> tuple[dict[str, Any], dict[str, float]]:
    """The calibration factors the live build at ``T`` would have read: the US screener's own loader on the store at ``T``
    (the snapshot published strictly before ``T``, clamped there to ±``CALIBRATION_FACTOR_LIMIT``). ``absent_at_T`` → none
    (factor 1.0)."""
    view = _StoreAtT(database, as_of)
    screener = live_producer(view)
    screener._load_calibration_factors(cast(USMarket, market))
    factors = dict(screener._calibration_factors[cast(USMarket, market)])
    if view.read is None:
        return {"status": "absent_at_T", "snapshot_id": None, "published_at": None, "factors": {}, "factor_limit": CALIBRATION_FACTOR_LIMIT}, factors
    return {"status": "applied" if factors else "empty_at_T", "snapshot_id": str(view.read["id"]), "published_at": pit._instant(view.read["published_at"]).isoformat(),
            "factors": dict(sorted(factors.items())), "factor_limit": CALIBRATION_FACTOR_LIMIT}, factors


def calibration_factor(factors: Mapping[str, float], profile: str) -> float:
    """The factor ``_analyze_stock`` applies for ``profile`` (the profile's, else the global one, else 1.0, clamped)."""
    return clamp(factors.get(profile, factors.get("global", 1.0)), 1 - CALIBRATION_FACTOR_LIMIT, 1 + CALIBRATION_FACTOR_LIMIT)


def one_pager_profile(fundamentals: Mapping[str, Any]) -> str:
    """The valuation profile ``OnePagerService._analyze`` derives (its sector/industry fallbacks, then ``_valuation_profile``):
    the key ``_analyze_stock`` reads the calibration factor by (the row's ``valuation_profile`` is the screener's own taxonomy)."""
    sector = str(fundamentals.get("sector") or fundamentals.get("industry") or "Setor não informado")
    return OnePagerService._valuation_profile(sector, str(fundamentals.get("industry") or sector))


def risk_free_at(macro: pit.MacroAtT) -> dict[str, Any]:
    """The live producer's risk-free rate at ``T``: the 10-year point of the re-executor's US curve package at ``T``,
    clamped as ``OnePagerService._us_risk_free_rate`` clamps the live close."""
    package = macro.curve_package or {}
    point = next((item for item in package.get("points") or [] if item.get("symbol") == RISK_FREE_SYMBOL), None)
    if point is None:
        raise pit.PitRerunInputError(f"no {RISK_FREE_SYMBOL} point in the US curve at T")
    rate = OnePagerService._clamp(float(point["annual_rate"]), *RISK_FREE_BOUNDS)
    return {"rate": rate, "observed": float(point["annual_rate"]), "observation_date": point["observation_date"], "symbol": RISK_FREE_SYMBOL,
            "bounds": list(RISK_FREE_BOUNDS), "source": package.get("source"), "derived_payload_sha256": package.get("payload_sha256")}


def analyze(screener: USScreeningService, market: str, symbol: str, price: float, fundamentals: dict[str, Any], *, as_of: datetime,
            risk_free_rate: float, peer_medians: dict[str, dict[str, float]], cash_volume: float = 0.0) -> dict[str, Any]:
    """The live producer's row for one stock (``_analyze_stock``, by import) with every point-in-time-absent input absent:
    no consensus, insider activity, news sentiment, institutional positions or grades."""
    quote = {"symbol": symbol, "price": price, "currency": "USD", "as_of": pit._utc(as_of).isoformat(), "change_percent": None, "volume": None}
    return screener._analyze_stock(cast(USMarket, market), quote, fundamentals, [], cash_volume, risk_free_rate=risk_free_rate, peer_medians=peer_medians)


# ------------------------------------------------------------------ the resolver: the V3 run's, keeping the payload it reads
class ServedSourceResolver(pit.PitSourceResolver):
    """``valuation_pit_rerun.PitSourceResolver`` unchanged but for two things: it keeps the statements payload of every name
    (the one it reads anyway), and it never reads the price-target history (the consensus never enters the internal TP)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.payloads: dict[str, dict[str, Any]] = {}

    def _statements_payload(self, market: str, symbol: str) -> tuple[dict[str, Any] | None, str]:
        payload, basis = super()._statements_payload(market, symbol)
        if payload is not None:
            self.payloads[symbol] = payload
        return payload, basis

    def _consensus_for(self, symbol: str) -> None:
        self.excluded["consensus:never_in_the_internal_tp"] += 1


# ------------------------------------------------------------------ one run
class ServedComputation:
    """The economic result of one served run — everything but the persistence clock."""

    def __init__(self, *, market: str, as_of: datetime, resolver: ServedSourceResolver, macro: pit.MacroAtT, results: dict[str, dict[str, Any]],
                 fundamentals_as_of: dict[str, Any], not_evaluable: dict[str, str], excluded: Counter[str], calibration: dict[str, Any],
                 factors: dict[str, float], profiles: dict[str, str], manifest: dict[str, Any], run_key: str, version: str, price_pin: dict[str, Any]) -> None:
        self.market = market
        self.profiles = profiles  # the One Pager's valuation profile of each name: the key of the calibration factor _analyze_stock applies
        self.as_of = pit._utc(as_of)
        self.resolver = resolver
        self.macro = macro
        self.results = results
        self.fundamentals_as_of = fundamentals_as_of
        self.not_evaluable = not_evaluable
        self.excluded = excluded
        self.calibration = calibration
        self.factors = factors
        self.manifest = manifest
        self.run_key = run_key
        self.source_version = version
        self.price_pin = price_pin
        self.entity_key = f"{market}_PITSERVED_{run_key[:16]}"

    def provenance_for(self, symbol: str, factor: float) -> dict[str, Any]:
        item = self.resolver.per_symbol.get(symbol) or {}
        return {"engine": engine_identity(), "engine_path": ENGINE_PATH, "served_tp_source": SERVED_SOURCE, "run_key": self.run_key,
                "statements_basis": item.get("statements_basis"), "calibration": {"status": self.calibration["status"], "factor": factor},
                "pit_absent_inputs": sorted(PIT_ABSENT_INPUTS), "consensus_in_engine": False, "diagnostic_only": True, "snapshot_resident": True}

    def records(self, *, cycle_id: str, published_at: datetime) -> list[dict[str, Any]]:
        """The run's records: the internal record of ``prediction_from_row`` (``official_internal_v1`` semantics — tp = the
        internal TP, buy-in = its own, consensus weight 0), relabelled ``SOURCE`` and re-hashed; deterministic but for ``id``."""
        records: list[dict[str, Any]] = []
        for symbol in sorted(self.results):
            result = self.results[symbol]
            factor = calibration_factor(self.factors, self.profiles.get(symbol, "general"))
            row = {**result, "calibration_factor": factor, "status": "retrospective", "signal_quality": "retrospective_point_in_time",
                   "tp_validation_status": "diagnostic_only", "source_name": engine_identity(), "fundamentals_as_of": self.fundamentals_as_of.get(symbol),
                   "as_of": self.as_of.isoformat()}
            record = prediction_from_row(row, market=self.market, scope="universe", cycle_id=cycle_id, source_version=self.source_version,
                                         prediction_instant=self.as_of, source_manifest_sha256=self.manifest["manifest_sha256"], published_at=published_at,
                                         rerun_of=None, source=SERVED_SOURCE, extra_provenance=self.provenance_for(symbol, factor))
            if record is not None:
                records.append(relabelled(record))
        return records

    def screen_inputs(self) -> dict[str, dict[str, Any]]:
        """The point-in-time screen inputs of every evaluated name — the re-executor's own (``PitComputation.screen_inputs``)."""
        return pit.PitComputation.screen_inputs(cast(pit.PitComputation, SimpleNamespace(resolver=self.resolver)))

    def rows(self) -> dict[str, dict[str, Any]]:
        """Per name, the producer's internal numbers (no consensus exists here): kept in the run's outputs."""
        keys = ("internal_tp", "internal_buy_in", "methods", "valuation_profile", "risk_score", "valuation_confidence", "method_dispersion_percent", "price")
        return {symbol: {key: result.get(key) for key in keys} for symbol, result in sorted(self.results.items())}

    def summary(self) -> dict[str, Any]:
        resolver = self.resolver
        pins = {"catalogue_pin": dict(resolver.catalogue_pin)} if resolver.catalogue_pin is not None else {}
        excluded = Counter(dict(resolver.excluded))
        excluded.update(self.excluded)
        return {**pins, "evaluated": len(self.results) + sum(1 for reason in self.not_evaluable.values() if reason.startswith("producer_refused")),
                "with_internal_tp": len(self.results), "not_evaluable": dict(Counter(self.not_evaluable.values())),
                "pit_excluded_inputs": dict(sorted(excluded.items())), "hypotheses": sum(len(items) for items in resolver.hypotheses.values()),
                "calibration": self.calibration["status"], "risk_free_rate": self.manifest["risk_free"]["rate"],
                "macro_as_of": self.macro.macro_as_of(self.market).isoformat(), "price_vintage": self.manifest["price_vintage"]["publication_id"],
                "price_basis_evidence": dict(resolver.price_basis_evidence),
                "statements": {"mode": resolver.statements, "table_present": resolver.vintages_present, "basis": dict(sorted(resolver.statements_basis.items())),
                               "coverage": resolver.vintages_coverage},
                "price_pin": dict(self.price_pin), "catalogue_snapshot_id": resolver.catalogue_snapshot_id}


def relabelled(record: Mapping[str, Any]) -> dict[str, Any]:
    """A record of ``prediction_from_row`` relabelled to ``SOURCE`` and re-hashed: the canonical shape, another source."""
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    core["source"] = SOURCE
    return {**core, "id": str(record["id"]), "row_sha256": canonical_sha256(core)}


def record_verifies(record: Mapping[str, Any]) -> bool:
    """Whether a snapshot-resident record's ``row_sha256`` recomputes from its own fields."""
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    return bool(record.get("row_sha256")) and canonical_sha256(core) == record.get("row_sha256")


class PitServedService:
    """``--rerun`` of the served internal TP: the store only (no network), one snapshot per run."""

    def __init__(self, database: Database, *, settings: Settings | None = None, price_history: Any = None) -> None:
        self.database = database
        self._rerun = pit.PitRerunService(database, settings=settings, price_history=price_history)
        self.http = self._rerun.http

    def compute(self, market: str, *, as_of: datetime, prices: pit.PinnedPrices, statements: str = pit.STATEMENTS_DEFAULT,
                catalogue_pinned_at: datetime | None = None, vintages: pit.AsFiledReader | None = None) -> ServedComputation:
        """The economic computation (no ``now``): the V3 run's resolver over the same pins, then the live producer on the
        point-in-time provider shape of every evaluated stock."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise pit.PitRerunInputError("T must carry a time zone")
        if market not in ("NASDAQ", "NYSE"):
            raise pit.PitRerunInputError(f"the served internal TP is the US producer's: {market!r} is not a US exchange")
        resolver = ServedSourceResolver(self.database, market=market, as_of=as_of, prices=prices, statements=statements, vintages=vintages,
                                        catalogue_pinned_at=catalogue_pinned_at)
        resolver.resolve()
        macro = resolver.macro()
        risk_free = risk_free_at(macro)
        calibration, factors = calibration_at(self.database, market, as_of)
        excluded: Counter[str] = Counter()
        not_evaluable = dict(resolver.not_evaluable)
        fundamentals: dict[str, dict[str, Any]] = {}
        fundamentals_as_of: dict[str, Any] = {}
        for symbol in sorted(resolver.per_symbol):
            item = resolver.per_symbol[symbol]
            if item["row"].get("security_type") != STOCK:
                not_evaluable[symbol] = "not_a_stock:the_etf_path_is_not_re_executed"
                continue
            fundamentals[symbol] = fundamentals_at(symbol, resolver.payloads[symbol], item, market=market, economic_date=resolver.economic_date,
                                                   session_date=prices.session_date, excluded=excluded)
            fundamentals_as_of[symbol] = pit._mapping(item.get("fundamentals")).get("fundamentals_as_of")
        peer_medians = OnePagerService._us_peer_medians(fundamentals)
        screener = live_producer(calibration_factors={market: factors})
        results: dict[str, dict[str, Any]] = {}
        profiles: dict[str, str] = {}
        for symbol, normalized in fundamentals.items():
            for name in PIT_ABSENT_INPUTS:
                if name != "earnings_surprise":
                    excluded[f"{name}:no_point_in_time_history"] += 1
            if OnePagerService._positive(normalized.get("trailingEps")) is not None:
                excluded["forward_eps:absent_trailing_eps_used"] += 1
            try:
                results[symbol] = analyze(screener, market, symbol, float(resolver.per_symbol[symbol]["row"]["price"]), normalized, as_of=as_of,
                                          risk_free_rate=risk_free["rate"], peer_medians=peer_medians)
                profiles[symbol] = one_pager_profile(normalized)
            except Exception as error:  # the live build's fundamental_quality_gate: the name has no row (counted by the error's type, never its message)
                not_evaluable[symbol] = "producer_refused"
                excluded[f"producer_refused:{type(error).__name__}"] += 1
        version = source_version()
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "source": SOURCE, "market": market, "as_of": pit._utc(as_of).isoformat(),
            "economic_date": resolver.economic_date.isoformat(), "session_date": prices.session_date,
            "engine": {"identity": engine_identity(), "path": ENGINE_PATH, "served_tp_source": SERVED_SOURCE,
                       "implementation_file_sha256": implementation_files(), "implementation_object_sha256": implementation_objects()},
            "sources": sorted(resolver.references, key=lambda item: json.dumps(item, sort_keys=True)),
            "price_vintage": prices.manifest(), "price_basis": dict(pit.PRICE_BASIS), "macro": macro.references, "risk_free": risk_free,
            "calibration": calibration, "peer_medians": peer_medians, "availability_rule": pit.AVAILABILITY_RULE,
            "declared_assumptions": {**pit.DECLARED_ASSUMPTIONS, **SERVED_ASSUMPTIONS}, "pit_absent_inputs": dict(PIT_ABSENT_INPUTS), "external_api_calls": 0,
        }
        manifest["manifest_sha256"] = canonical_sha256({key: value for key, value in manifest.items() if key != "manifest_sha256"})
        run_key = pit.run_key_of(source_version_text=version, market=market, as_of=as_of, manifest=manifest)
        return ServedComputation(market=market, as_of=as_of, resolver=resolver, macro=macro, results=results, fundamentals_as_of=fundamentals_as_of,
                                 not_evaluable=not_evaluable, excluded=excluded, calibration=calibration, factors=factors, profiles=profiles, manifest=manifest,
                                 run_key=run_key,
                                 version=version, price_pin=prices.pin())

    def persist(self, computation: ServedComputation, *, clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """Find-or-write under the run's lock: ONE snapshot holds the run and its records (no second commit)."""
        tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        market, run_key = computation.market, computation.run_key
        with pit._run_lock(self.database, run_key):
            existing = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, computation.entity_key)
            supersedes: str | None = None
            if existing is not None and str(pit._mapping(existing.get("inputs")).get("run_key")) == run_key:
                cycle_id, published_at, idempotent = str(existing["id"]), pit._instant(existing["published_at"]), True
                stored = pit._mapping(existing.get("outputs"))
                expected = {(record["symbol"], record["row_sha256"]) for record in computation.records(cycle_id=cycle_id, published_at=published_at)}
                held = {(str(symbol), str(digest)) for symbol, digest in stored.get("prediction_identities") or []}
                records = [record for record in stored.get("records") or [] if isinstance(record, dict)]
                if held != expected or {(str(r.get("symbol")), str(r.get("row_sha256"))) for r in records} != expected or not all(map(record_verifies, records)):
                    raise pit.PitRerunIntegrityError(f"served run {run_key[:16]} holds records the computation does not reproduce")
            else:
                previous = self.database.latest_analysis_snapshot_by_inputs(ANALYSIS_TYPE, {"market": market, "as_of": computation.as_of.isoformat()})
                if previous is not None and str(pit._mapping(previous.get("inputs")).get("run_key")) != run_key:
                    supersedes = str(pit._mapping(previous.get("inputs")).get("run_key"))
                cycle_id, published_at, idempotent = str(uuid4()), pit._utc(tick()), False
                if published_at < computation.as_of:
                    raise pit.PitRerunInputError(f"the persistence clock {published_at.isoformat()} precedes T {computation.as_of.isoformat()}")
                records = computation.records(cycle_id=cycle_id, published_at=published_at)
                methodology_id = self.database.ensure_methodology_version(
                    METHODOLOGY_KEY, METHODOLOGY_VERSION, {"schema_version": SCHEMA_VERSION, "served_tp_source": SERVED_SOURCE, "external_api_calls": 0,
                                                           "diagnostic_only": True, "official_tp_replacement_authorized": False},
                    "Point-in-time re-execution of the served internal TP (official_internal_v1); diagnostic only.")
                inputs: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "run_key": run_key, "market": market, "as_of": computation.as_of.isoformat(),
                                          "source": SOURCE, "source_version": computation.source_version, "manifest": computation.manifest,
                                          "price_pin": dict(computation.price_pin), "external_api_calls": 0}
                if supersedes:
                    inputs["supersedes"] = supersedes
                if computation.resolver.catalogue_pin is not None:
                    inputs["catalogue_pin"] = dict(computation.resolver.catalogue_pin)
                outputs = {"schema_version": SCHEMA_VERSION, "run_key": run_key, "market": market, "as_of": computation.as_of.isoformat(),
                           "published_at": published_at.isoformat(), "rows": computation.rows(), "summary": computation.summary(),
                           "not_evaluable": dict(computation.not_evaluable), "records": records,
                           "prediction_identities": [[record["symbol"], record["row_sha256"]] for record in records], "screen": computation.screen_inputs(),
                           "catalogue_counts": {"rows": computation.resolver.catalogue_rows, "stocks": computation.resolver.catalogue_stocks},
                           "governance": {"diagnostic_only": True, "decision_consumer": False, "selectable": False, "official_tp_replacement_authorized": False,
                                          "external_api_calls": 0}}
                self.database.save_analysis_snapshot(ANALYSIS_TYPE, computation.entity_key, methodology_id, inputs, outputs, published_at, snapshot_id=cycle_id)
        return {"schema_version": SCHEMA_VERSION, "source": SOURCE, "market": market, "as_of": computation.as_of.isoformat(), "run_key": run_key,
                "cycle_id": cycle_id, "entity_key": computation.entity_key, "published_at": published_at.isoformat(), "idempotent": idempotent,
                "supersedes": supersedes, "records": {"expected": len(records), "complete": True}, "source_version": computation.source_version,
                "manifest_sha256": computation.manifest["manifest_sha256"], **computation.summary()}

    def rerun(self, market: str, *, as_of: datetime, clock: Callable[[], datetime] | None = None, price_pinned_at: datetime | None = None,
              statements: str = pit.STATEMENTS_DEFAULT, catalogue_pinned_at: datetime | None = None, prices: pit.PinnedPrices | None = None,
              vintages: pit.AsFiledReader | None = None) -> tuple[dict[str, Any], ServedComputation]:
        """One run. ``prices`` (and ``vintages``): the pinned vintage (and the as-filed reader) of the V3 run of the same
        ``(exchange, T)`` just computed — its caches serve this run; refused when it is not the same pin."""
        tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        started_at = pit._utc(tick())
        for name, pin in (("price", price_pinned_at), ("catalogue", catalogue_pinned_at)):
            if pin is not None and (pin.tzinfo is None or pin.utcoffset() is None):
                raise pit.PitRerunInputError(f"the {name} pin must carry a time zone")
            if pin is not None and pit._utc(pin) > started_at:
                raise pit.PitRerunInputError(f"the {name} pin {pit._utc(pin).isoformat()} is after the run start {started_at.isoformat()}")
        if prices is None:
            prices = self._rerun.pin_vintage(market, as_of=as_of, pinned_at=started_at if price_pinned_at is None else price_pinned_at, explicit=price_pinned_at is not None)
        elif (prices.market != market or prices.as_of != pit._utc(as_of)
              or prices.pinned_at != (pit._utc(price_pinned_at) if price_pinned_at is not None else prices.pinned_at)):
            raise pit.PitRerunInputError("the shared price vintage is not this run's (exchange, T, pin)")
        computation = self.compute(market, as_of=as_of, prices=prices, statements=statements, catalogue_pinned_at=catalogue_pinned_at, vintages=vintages)
        return self.persist(computation, clock=tick), computation


def reusable_run(database: Database, market: str, as_of: datetime, *, publication_id: str, statements: str) -> dict[str, Any] | None:
    """The LATEST served run of ``(market, T)`` when it is the run this code would compute — same ``source_version``, same
    producer files and reader objects, same pinned publication and statements mode — and its records are exactly its
    identities and verify; else ``None``. Read only."""
    snapshot = database.latest_analysis_snapshot_by_inputs(ANALYSIS_TYPE, {"market": market, "as_of": pit._utc(as_of).isoformat()})
    if snapshot is None:
        return None
    inputs, outputs = pit._mapping(snapshot.get("inputs")), pit._mapping(snapshot.get("outputs"))
    engine = pit._mapping(pit._mapping(inputs.get("manifest")).get("engine"))
    if str(inputs.get("source_version")) != source_version():
        return None
    if {"files": engine.get("implementation_file_sha256"), "objects": engine.get("implementation_object_sha256")} != {"files": implementation_files(),
                                                                                                                      "objects": implementation_objects()}:
        return None
    if str(pit._mapping(inputs.get("price_pin")).get("resolved_publication_id")) != publication_id:
        return None
    if pit._mapping(pit._mapping(outputs.get("summary")).get("statements")).get("mode") != statements:
        return None
    records = [record for record in outputs.get("records") or [] if isinstance(record, dict)]
    identities = {(str(symbol), str(digest)) for symbol, digest in outputs.get("prediction_identities") or []}
    if {(str(record.get("symbol")), str(record.get("row_sha256"))) for record in records} != identities or not all(map(record_verifies, records)):
        return None
    return snapshot


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None, *, database: Database | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description="The served internal TP (official_internal_v1) re-executed point-in-time at --as-of T from persisted "
                                                 "snapshots only (no network). Diagnostic; prints aggregates, never a symbol.")
    parser.add_argument("--market", choices=("NASDAQ", "NYSE"), required=True)
    parser.add_argument("--as-of", required=True, help="T, ISO-8601 WITH zone")
    parser.add_argument("--price-pinned-at", default=None, help="resolve the price vintage published before this ISO-8601 instant WITH zone")
    parser.add_argument("--catalogue-pinned-at", default=None, help="read the universe catalogue published before this ISO-8601 instant WITH zone")
    parser.add_argument("--statements", choices=pit.STATEMENTS_MODES, default=pit.STATEMENTS_DEFAULT)
    args = parser.parse_args(argv)
    as_of = pit._cli_instant(parser, "--as-of", str(args.as_of))
    price_pinned_at = pit._cli_instant(parser, "--price-pinned-at", str(args.price_pinned_at)) if args.price_pinned_at is not None else None
    catalogue_pinned_at = pit._cli_instant(parser, "--catalogue-pinned-at", str(args.catalogue_pinned_at)) if args.catalogue_pinned_at is not None else None
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings)
    service = PitServedService(database, settings=settings)
    receipt, _computation = service.rerun(args.market, as_of=as_of, price_pinned_at=price_pinned_at, statements=args.statements,
                                          catalogue_pinned_at=catalogue_pinned_at)
    if service.http is not None and service.http.calls != 0:
        raise pit.PitRerunIntegrityError(f"the served rerun made {service.http.calls} network call(s): it reads the store only")
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
