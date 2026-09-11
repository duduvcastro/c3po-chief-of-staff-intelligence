"""Valuation V3.2 — point-in-time re-executor (36-month retrospective, DIAGNOSTIC), design rev 2 of 2026-09-11.

Nothing here is training, a PROMO-2 gate, a promotion or a change of the official source. The module RE-EXECUTES the
frozen ``ValuationV3Engine`` (rev 7) for an economic instant ``T`` in the past, through the very path the nightly
shadow uses (``valuation_v3_shadow._contexts`` → ``_evaluate_market``), fed only with inputs that were available at
``T`` — "available" meaning **as available per evidence or declared hypothesis** (design §2–§3), never "exactly what
the world knew": the original provider vintage is ``N/D`` for every input, and the record says so.

Three clocks per record (§2): ``T`` = ``prediction_instant`` (the economic date of the computation); ``published_at`` =
the real instant of persistence (never retro-dated; the panel classifies every record ``retrospective`` by construction);
and, per input, an availability with its kind — ``evidence`` (the provider's ``filing_date``, US) or ``hypothesis``
(B3: ``period_end + 90 d``, a declared lag; it is never called "the original publication").

The engine is fed, per symbol, with a universe row, a V2.1-shaped packet and a Chewie-shaped item REBUILT from the
eligible statements (§3): derived ratios are recomputed from those periods; the current blocks of the provider payload
(``General``, ``Highlights``, ``Valuation``, ``Technicals``, ``SharesStats``, ``AnalystRatings``, ``Earnings``, …) are
NEVER read (only ``Financials`` and ``outstandingShares`` are); the sector/industry/profile classification comes from the
universe catalogue (the only current fields admitted, declared per record); the consensus is the last eligible target
per house in ``(T − 90 d, T]``, ≥ 3 houses, currency checked field by field, horizon ``N/D``; everything without a
history (estimates, peer quality, insiders, news, grades, …) is passed as ABSENT and counted in
``provenance.pit_excluded_inputs``. The TP recorded is the engine's INTERNAL TP (the consensus never enters the row the
engine sees; the block is persisted beside it, spec rev 7 "TP sem consenso dentro"); ``buy_in`` comes from
``official_buy_in_v1`` with neutral, declared parameters (``provenance.buy_in_rule``).

Prices (§2): the run PINS the vintage it starts with — the latest publication of ``valuation_price_history`` at run
start (``publication_id`` + ``bars_sha256``), verified, recorded in the manifest and read for the whole run through a
cut equal to that publication's availability, so a publication that appears mid-run is never mixed in (a pinned
publication that stops resolving is a refusal, never a substitution). ``T`` filters ECONOMIC dates (``session_date ≤
T``); it is never used as the availability cut of the series (that would return nothing).

Identity and idempotency (§4): ``run_key = sha256(canonical_json([source_version, market, T, manifest]))`` (canonical
JSON — never Python ``hash()``); one snapshot per run (``analysis_type = valuation_pit_rerun``, ``entity_key =
<M>_PIT_<run_key[:16]>``, ``inputs = {run_key, T, manifest, supersedes?}``); the prediction records are inserted
EXPLICITLY (``insert_valuation_predictions``), ``published_at`` = the snapshot's own clock, so their identities are
deterministic given the run. Before writing, the run takes a lock derived from ``run_key`` (in memory a process lock;
in PostgreSQL a session-level advisory lock keyed by the first 8 bytes of ``run_key`` as a signed int64 — the snapshot
and the records are two commits, so a transaction-level lock could not span both) and compares the SET of
``(symbol, row_sha256)`` already stored for the cycle with the computed set: identical → nothing written; a subset → the
missing rows are completed under the same ``cycle_id`` (the UNIQUE key refuses duplicates); a stored identity outside the
computed set is an integrity failure. Changed inputs → a new ``run_key`` naming the previous run in ``inputs.supersedes``.

Phases (§5): ``--fetch`` (one read per symbol through the existing provider HTTP clients, persisted as dated, hashed
``valuation_pit_source`` snapshots; nothing nominal on stdout; requires the owner's authorization, never during a
session or a nightly phase) and ``--rerun`` (no network: ``_NoNetworkHttp``; reads snapshots and the price series only;
``--as-of`` with a mandatory time zone; the private per-symbol detail written ``O_EXCL | O_NOFOLLOW``, mode 0600;
stdout carries aggregates only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import statistics
import threading
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence, cast
from uuid import uuid4

from .config import Settings, get_settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.fmp import FmpClient
from .market_data.http import JsonHttpClient
from .valuation_official import (
    SESSION_ZONES,
    SOURCE_V3_2_SHADOW,
    CalendarUnavailable,
    canonical_sha256,
    prediction_from_row,
    session_date_of,
)
from .valuation_official_engine import official_buy_in_v1, official_entry_discount_v1
from .valuation_panel import _NoNetworkHttp
from .valuation_price_history import PriceHistoryService
from .valuation_v3_engine import ENGINE_VERSION, ValuationV3Engine
from .valuation_v3_macro import (
    SCHEMA_VERSION as MACRO_SCHEMA_VERSION,
    SELIC_SOURCE,
    US_CURVE_SOURCE,
    canonical_payload_sha256,
    interpolate_us_five_year_rate,
    validate_us_curve_package,
)
from .valuation_v3_shadow import MARKETS, ValuationV3ShadowService, _SOURCE_SPECS

logger = logging.getLogger(__name__)

SOURCE = SOURCE_V3_2_SHADOW
ANALYSIS_TYPE = "valuation_pit_rerun"
SOURCE_ANALYSIS_TYPE = "valuation_pit_source"
SCHEMA_VERSION = "VALUATION-PIT-RERUN-v1"
SOURCE_VERSION_PREFIX = "pit-rerun-v1"
METHODOLOGY_KEY = "valuation_pit_rerun"
METHODOLOGY_VERSION = 1
PROVIDER_EODHD = "EODHD_FUNDAMENTALS"
PROVIDER_FMP = "FMP_TARGETS"
MACRO_SELIC_KEY = "B3_BCB_SELIC_HISTORY"
MACRO_TREASURY_KEY = "US_EODHD_TREASURY_HISTORY"
LIVE_SELIC_SPEC = next(spec for spec in _SOURCE_SPECS if spec[0] == "selic_macro")  # ("selic_macro", "B3", "valuation_macro_history", "B3_SELIC_REGIME")
CALIBRATION_ANALYSIS_TYPE = "valuation_v3_calibration"  # interpretation: no calibration producer exists in this tree → "absent_at_T"
ENGINE_MARKET = {"B3": "B3", "NASDAQ": "US", "NYSE": "US"}
PEER_MARKETS = {"B3": ("B3",), "NASDAQ": ("NASDAQ", "NYSE"), "NYSE": ("NASDAQ", "NYSE")}
PROVIDER_SUFFIX = {"B3": "SA", "NASDAQ": "US", "NYSE": "US"}
CURRENCY = {"B3": "BRL", "NASDAQ": "USD", "NYSE": "USD"}
US_CURVE_SYMBOLS = ((3, "US3Y.GBOND"), (10, "US10Y.GBOND"))
BCB_SELIC_SERIES_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
B3_AVAILABILITY_LAG_DAYS = 90  # §2: a HYPOTHESIS (the B3 filing_date coincides with the period end in 346/348 payloads: not evidence)
CONSENSUS_WINDOW_DAYS = 90
MIN_CONSENSUS_HOUSES = 3
CONSENSUS_HORIZON = "N/D"  # the provider does not expose the horizon per target; the literal "12m" attests nothing (§3)
MIN_VALID_SESSIONS = 90  # §7: admissibility per symbol and T, verified in the run, never presumed from the calendar
TTM_QUARTERS = 4
TTM_MAX_SPAN_DAYS = 400
FISCAL_PRICE_TOLERANCE_DAYS = 30
BETA_WINDOW_SESSIONS = 252
BETA_MIN_SESSIONS = 60
ENTRY_RISK_SCORE = 50.0  # neutral, declared: no point-in-time risk model exists (provenance.buy_in_rule.parameters)
ENTRY_CONFIDENCE = 50.0
ALLOWED_PAYLOAD_BLOCKS: tuple[str, ...] = ("Financials", "outstandingShares")  # the closed list of §3: nothing else of the payload is read
FORBIDDEN_PAYLOAD_BLOCKS: tuple[str, ...] = ("General", "Highlights", "Valuation", "Technicals", "SharesStats", "AnalystRatings", "Earnings",
                                             "ESGScores", "Holders", "InsiderTransactions", "SplitsDividends", "ETF_Data")
CURRENT_FIELDS_ADMITTED: tuple[str, ...] = ("sector", "industry", "valuation_profile", "security_type")  # the catalogue's classification (§3), declared
AVAILABILITY_RULE = "as available per evidence (provider filing_date) or declared hypothesis (B3: period_end+90d); original vintage N/D"
_RUN_LOCKS: dict[str, threading.Lock] = {}
_RUN_LOCKS_GUARD = threading.Lock()


class PitRerunInputError(RuntimeError):
    pass


class PitRerunIntegrityError(RuntimeError):
    pass


# ------------------------------------------------------------------ small helpers (no clock)
def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _instant(value: Any) -> datetime:
    return _utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number + 0.0


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _parse_date(value: Any) -> date | None:
    text = str(value or "")[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def symbol_hash(symbol: str) -> str:
    """The non-nominal key of a symbol's source snapshots: ``sha256(SYMBOL)[:16]``."""
    return _sha256_text(symbol.strip().upper())[:16]


def source_entity_key(market: str, provider: str, symbol: str) -> str:
    return f"{market}_{provider}_{symbol_hash(symbol)}"


def _file_sha256(name: str) -> str:
    return hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()


def module_sha256() -> str:
    return _file_sha256("valuation_pit_rerun.py")


def source_version() -> str:
    """``pit-rerun-v1+<sha of this module>``: the version a record carries (design §1)."""
    return f"{SOURCE_VERSION_PREFIX}+{module_sha256()[:12]}"


def engine_identity() -> str:
    return f"ValuationV3Engine@{_file_sha256('valuation_v3_engine.py')[:12]}"


def buy_in_identity() -> str:
    return f"official_buy_in_v1@{_file_sha256('valuation_official_engine.py')[:12]}"


def run_key_of(*, source_version_text: str, market: str, as_of: datetime, manifest: Mapping[str, Any]) -> str:
    """``sha256(canonical(source_version, market, T, manifest))`` — canonical JSON (sorted keys, no spaces), never ``hash()``."""
    return canonical_sha256([source_version_text, market, _utc(as_of).isoformat(), dict(manifest)])


def advisory_lock_key(run_key: str) -> int:
    """The PostgreSQL advisory-lock key of a run: the first 8 bytes of ``run_key`` as a signed int64 (deterministic)."""
    return int.from_bytes(bytes.fromhex(run_key[:16]), "big", signed=True)


def _available_after_day(observed: date) -> str:
    """The macro module's convention: a daily observation is available at the next UTC midnight."""
    return datetime.combine(observed + timedelta(days=1), wall_time.min, tzinfo=timezone.utc).isoformat()


def economic_date_of(market: str, as_of: datetime) -> date:
    return _utc(as_of).astimezone(SESSION_ZONES[market]).date()


# ------------------------------------------------------------------ availability (§2–§3): evidence or declared hypothesis
def availability_of(market: str, period_end: date, filing_date: date | None) -> dict[str, Any] | None:
    """When a statement became available, with its KIND. US: the provider's ``filing_date`` is EVIDENCE of the provider's
    availability (not the regulator's; ``published_at_original`` stays ``N/D``); without it the period is not eligible
    (``None``). B3: the ``filing_date`` is not evidence (it coincides with the period end), so the period enters under the
    declared HYPOTHESIS ``period_end + 90 d`` — a lag, never "the original publication"."""
    if market == "B3":
        return {"kind": "hypothesis", "rule": f"period_end+{B3_AVAILABILITY_LAG_DAYS}d", "period_end": period_end.isoformat(),
                "available_at": (period_end + timedelta(days=B3_AVAILABILITY_LAG_DAYS)).isoformat(), "published_at_original": "N/D"}
    if filing_date is None:
        return None
    return {"kind": "evidence", "rule": "provider_filing_date", "period_end": period_end.isoformat(), "available_at": filing_date.isoformat(),
            "published_at_original": "N/D"}


def eligible_statements(payload: Mapping[str, Any], *, market: str, economic_date: date, excluded: Counter[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """The statements of the payload eligible at ``economic_date``, per statement and frequency, newest first. Reads ONLY
    ``Financials`` (the closed list of §3): a forbidden block is never touched, whatever the payload carries."""
    financials = _mapping(payload.get("Financials"))
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for statement in ("Income_Statement", "Balance_Sheet", "Cash_Flow"):
        section = _mapping(financials.get(statement))
        output[statement] = {}
        for frequency in ("quarterly", "yearly"):
            rows: list[dict[str, Any]] = []
            seen: set[date] = set()
            for key, entry in sorted(_mapping(section.get(frequency)).items(), reverse=True):
                data = _mapping(entry)
                period_end = _parse_date(data.get("date") or key)
                if period_end is None or period_end in seen:
                    excluded[f"{statement}.{frequency}:unparseable_or_duplicate_period"] += 1
                    continue
                availability = availability_of(market, period_end, _parse_date(data.get("filing_date")))
                if availability is None:
                    excluded[f"{statement}.{frequency}:filing_date_missing"] += 1
                    continue
                if date.fromisoformat(availability["available_at"]) > economic_date:
                    excluded[f"{statement}.{frequency}:not_available_at_T"] += 1
                    continue
                seen.add(period_end)
                rows.append({"period_end": period_end, "availability": availability, "data": data})
            rows.sort(key=lambda row: row["period_end"], reverse=True)
            output[statement][frequency] = rows
    return output


def _first_number(data: Mapping[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = _number(data.get(field))
        if value is not None:
            return value
    return None


def _ttm(rows: Sequence[Mapping[str, Any]], yearly: Sequence[Mapping[str, Any]], fields: Mapping[str, tuple[str, ...]], *, offset: int = 0
         ) -> tuple[dict[str, float | None], str | None]:
    """Sum of the four eligible quarters starting at ``offset`` (a span ≤ 400 days), else the latest eligible fiscal year."""
    quarters = list(rows[offset:offset + TTM_QUARTERS])
    if len(quarters) == TTM_QUARTERS and (quarters[0]["period_end"] - quarters[-1]["period_end"]).days <= TTM_MAX_SPAN_DAYS:
        totals: dict[str, float | None] = {}
        for name, candidates in fields.items():
            values = [_first_number(quarter["data"], *candidates) for quarter in quarters]
            totals[name] = sum(cast(list[float], values)) if all(value is not None for value in values) else None
        return totals, "four_quarters"
    if offset == 0 and yearly:
        return {name: _first_number(yearly[0]["data"], *candidates) for name, candidates in fields.items()}, "latest_fiscal_year"
    return {name: None for name in fields}, None


INCOME_FIELDS: dict[str, tuple[str, ...]] = {"revenue": ("totalRevenue",), "net_income": ("netIncome", "netIncomeApplicableToCommonShares"),
                                             "ebitda": ("ebitda",), "operating_income": ("operatingIncome",)}
CASH_FLOW_FIELDS: dict[str, tuple[str, ...]] = {"dividends_paid": ("dividendsPaid",), "free_cash_flow": ("freeCashFlow",),
                                                "operating_cash_flow": ("totalCashFromOperatingActivities",)}


def _balance_fields(data: Mapping[str, Any]) -> dict[str, float | None]:
    short_debt = _first_number(data, "shortTermDebt", "shortLongTermDebt") or 0.0
    long_debt = _first_number(data, "longTermDebt") or 0.0
    debt = short_debt + long_debt
    return {"equity": _first_number(data, "totalStockholderEquity", "totalEquity"), "debt": debt if debt > 0 else _first_number(data, "netDebt"),
            "cash": _first_number(data, "cashAndEquivalents", "cash"), "shares": _positive(data.get("commonStockSharesOutstanding"))}


def shares_at(payload: Mapping[str, Any], balance: Mapping[str, Any] | None, *, market: str, economic_date: date, excluded: Counter[str],
              hypotheses: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any] | None]:
    """The share count at ``T``: the latest eligible balance sheet's ``commonStockSharesOutstanding`` (its availability),
    else the latest ``outstandingShares`` observation whose period end + the declared lag ≤ ``T`` (a hypothesis for every
    market: the provider dates those observations by period, not by filing). Only ``outstandingShares`` is read."""
    if balance is not None and _balance_fields(balance["data"])["shares"] is not None:
        return _balance_fields(balance["data"])["shares"], balance["availability"]
    candidates: list[tuple[date, float]] = []
    for frequency in ("quarterly", "annual"):
        for key, entry in _mapping(_mapping(payload.get("outstandingShares")).get(frequency)).items():
            data = _mapping(entry)
            period_end = _parse_date(data.get("dateFormatted") or data.get("date") or key)
            shares = _positive(data.get("shares"))
            if period_end is None or shares is None:
                excluded[f"outstandingShares.{frequency}:unusable"] += 1
                continue
            if period_end + timedelta(days=B3_AVAILABILITY_LAG_DAYS) > economic_date:
                excluded[f"outstandingShares.{frequency}:not_available_at_T"] += 1
                continue
            candidates.append((period_end, shares))
    if not candidates:
        return None, None
    period_end, shares = max(candidates, key=lambda item: item[0])
    hypothesis = {"kind": "hypothesis", "rule": f"period_end+{B3_AVAILABILITY_LAG_DAYS}d", "input": "outstandingShares", "period_end": period_end.isoformat(),
                  "available_at": (period_end + timedelta(days=B3_AVAILABILITY_LAG_DAYS)).isoformat(), "published_at_original": "N/D"}
    hypotheses.append(hypothesis)
    return shares, hypothesis


def pit_fundamentals(payload: Mapping[str, Any], *, market: str, economic_date: date) -> dict[str, Any]:
    """Everything the engine needs from ONE provider payload, rebuilt from the periods eligible at ``T`` — trailing
    twelve months, the latest balance sheet, the share count, and the per-fiscal-year figures the ratio history is
    recomputed from — with every exclusion counted and every hypothesis listed. Pure: no price, no clock."""
    excluded: Counter[str] = Counter()
    hypotheses: list[dict[str, Any]] = []
    statements = eligible_statements(payload, market=market, economic_date=economic_date, excluded=excluded)
    income_q, income_y = statements["Income_Statement"]["quarterly"], statements["Income_Statement"]["yearly"]
    cash_q, cash_y = statements["Cash_Flow"]["quarterly"], statements["Cash_Flow"]["yearly"]
    balance_q, balance_y = statements["Balance_Sheet"]["quarterly"], statements["Balance_Sheet"]["yearly"]
    ttm, ttm_basis = _ttm(income_q, income_y, INCOME_FIELDS)
    prior, prior_basis = _ttm(income_q, [], INCOME_FIELDS, offset=TTM_QUARTERS)
    if prior_basis is None and len(income_y) >= 2:
        prior, prior_basis = {name: _first_number(income_y[1]["data"], *candidates) for name, candidates in INCOME_FIELDS.items()}, "previous_fiscal_year"
    cash_ttm, cash_basis = _ttm(cash_q, cash_y, CASH_FLOW_FIELDS)
    balance = balance_q[0] if balance_q else (balance_y[0] if balance_y else None)
    balance_fields = _balance_fields(balance["data"]) if balance is not None else {"equity": None, "debt": None, "cash": None, "shares": None}
    shares, shares_availability = shares_at(payload, balance, market=market, economic_date=economic_date, excluded=excluded, hypotheses=hypotheses)
    for row in (*income_q[:TTM_QUARTERS], *(income_y[:1] if ttm_basis == "latest_fiscal_year" else []), *([balance] if balance else [])):
        if row["availability"]["kind"] == "hypothesis":
            hypotheses.append(row["availability"])
    revenue_growth: float | None = None
    revenue_now, revenue_prior = ttm["revenue"], prior.get("revenue")
    if revenue_now is not None and revenue_prior is not None and revenue_prior > 0:
        revenue_growth = revenue_now / revenue_prior - 1
    elif prior_basis is None:
        excluded["revenue_growth:no_prior_period"] += 1
    balance_by_year = {row["period_end"]: row for row in balance_y}
    cash_by_year = {row["period_end"]: row for row in cash_y}
    fiscal_years: list[dict[str, Any]] = []
    for row in income_y:
        fields = _balance_fields(balance_by_year[row["period_end"]]["data"]) if row["period_end"] in balance_by_year else {"equity": None, "debt": None, "cash": None, "shares": None}
        net_debt = (fields["debt"] or 0.0) - (fields["cash"] or 0.0) if fields["debt"] is not None or fields["cash"] is not None else None
        dividends = _first_number(cash_by_year[row["period_end"]]["data"], "dividendsPaid") if row["period_end"] in cash_by_year else None
        fiscal_years.append({"fiscal_year_end": row["period_end"].isoformat(), "net_income": _first_number(row["data"], *INCOME_FIELDS["net_income"]),
                             "revenue": _first_number(row["data"], *INCOME_FIELDS["revenue"]), "ebitda": _first_number(row["data"], *INCOME_FIELDS["ebitda"]),
                             "equity": fields["equity"], "net_debt": net_debt, "shares": fields["shares"] or shares, "dividends_paid": dividends,
                             "availability": row["availability"]})
    periods = [row["period_end"] for rows in (income_q, income_y, balance_q, balance_y, cash_q, cash_y) for row in rows]
    net_debt_now = ((balance_fields["debt"] or 0.0) - (balance_fields["cash"] or 0.0)) if balance is not None else None
    return {
        "eligible": bool(income_q or income_y),
        "fundamentals_as_of": max(periods).isoformat() if periods else None,
        "ttm": {**ttm, "basis": ttm_basis},
        "cash_flow_ttm": {**cash_ttm, "basis": cash_basis},
        "balance": {**balance_fields, "net_debt": net_debt_now, "period_end": balance["period_end"].isoformat() if balance else None},
        "shares": shares,
        "shares_availability": shares_availability,
        "revenue_growth": revenue_growth,
        "fiscal_years": fiscal_years,
        "excluded": dict(sorted(excluded.items())),
        "hypotheses": hypotheses,
        "eligible_periods": {statement: {frequency: len(rows) for frequency, rows in by_frequency.items()} for statement, by_frequency in statements.items()},
    }


# ------------------------------------------------------------------ consensus (§3): last eligible target per house, ≥ 3 houses, currency by field
def consensus_at(rows: Sequence[Mapping[str, Any]], *, as_of: datetime, currency: str) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """The consensus that a reader could have formed at ``T`` from the provider's per-target history: the LAST eligible
    target of every house with ``publishedDate`` in ``(T − 90 d, T]``, at least ``MIN_CONSENSUS_HOUSES`` distinct houses,
    the target's ``currency`` field present and equal to the market's (a row without the field is refused: the currency
    is verified BY FIELD, never assumed). ``horizon`` is ``N/D`` — the provider exposes none per target. The block's
    ``published_at`` is the instant of the last target used. ``None`` (with the refusals counted) otherwise."""
    cut = _utc(as_of)
    floor = cut - timedelta(days=CONSENSUS_WINDOW_DAYS)
    refused: Counter[str] = Counter()
    latest: dict[str, tuple[datetime, float]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            refused["not_an_object"] += 1
            continue
        house = str(row.get("analystCompany") or row.get("analystName") or row.get("newsPublisher") or "").strip()
        target = _positive(row.get("priceTarget"))
        try:
            published = _instant(row.get("publishedDate"))
        except (TypeError, ValueError):
            refused["published_date_unparseable"] += 1
            continue
        if not house or target is None:
            refused["house_or_target_missing"] += 1
            continue
        if published > cut:
            refused["published_after_T"] += 1
            continue
        if published <= floor:
            refused["older_than_window"] += 1
            continue
        row_currency = row.get("currency")
        if row_currency in (None, ""):
            refused["currency_field_missing"] += 1
            continue
        if str(row_currency).strip().upper() != currency:
            refused["currency_mismatch"] += 1
            continue
        if house not in latest or published > latest[house][0]:
            latest[house] = (published, target)
    if len(latest) < MIN_CONSENSUS_HOUSES:
        refused["houses_below_minimum"] += 1
        return None, dict(sorted(refused.items()))
    targets = [target for _, target in latest.values()]
    return {"consensus_tp": statistics.median(targets), "analyst_count": len(latest), "source": "fmp:price-target-news",
            "published_at": max(published for published, _ in latest.values()).isoformat(), "horizon": CONSENSUS_HORIZON, "currency": currency,
            "window_days": CONSENSUS_WINDOW_DAYS}, dict(sorted(refused.items()))


# ------------------------------------------------------------------ prices: the pinned vintage, T as an ECONOMIC date
class PinnedPrices:
    """The price series of ONE run: the vintage pinned at run start (``publication_id`` + ``bars_sha256``), read for every
    symbol through a cut equal to the pinned publication's availability + 1 µs — so ``series()`` resolves exactly that
    publication for the whole run, whatever is published meanwhile — and verified on every read (a mismatch is a refusal,
    never a silent switch). Bars are filtered by ECONOMIC date (``session_date ≤ session of T``)."""

    def __init__(self, reader: PriceHistoryService, market: str, *, as_of: datetime, pinned_at: datetime) -> None:
        self.reader = reader
        self.market = market
        self.as_of = _utc(as_of)
        vintage = reader.vintage(market, available_before=_utc(pinned_at))
        if vintage is None or vintage["status"] != "ok":
            raise PitRerunInputError(f"no verifiable price vintage for {market} at run start ({'none' if vintage is None else vintage['status']})")
        self.publication_id = str(vintage["publication_id"])
        self.price_snapshot_id = str(vintage["price_snapshot_id"])
        self.available_at = _instant(vintage["available_at"])
        self.bars_sha256 = str(vintage["bars_sha256"])
        self.window = [vintage["from"], vintage["to"]]
        self._cut = self.available_at + timedelta(microseconds=1)
        try:
            self.session_date = session_date_of(market, self.as_of)
        except CalendarUnavailable as error:
            raise PitRerunInputError(f"{market} calendar cannot place T={self.as_of.isoformat()}: {error}") from error
        self._bars: dict[str, dict[str, dict[str, Any]]] = {}
        self._returns: dict[str, dict[str, float]] = {}
        self._proxy: dict[str, float] | None = None

    def manifest(self) -> dict[str, Any]:
        return {"publication_id": self.publication_id, "price_snapshot_id": self.price_snapshot_id, "available_at": self.available_at.isoformat(),
                "bars_sha256": self.bars_sha256, "window": list(self.window), "historical_vintage": "N/D"}

    def bars(self, symbol: str) -> dict[str, dict[str, Any]]:
        """The symbol's bars with ``session_date ≤ session of T`` from the PINNED publication (empty when the vintage refuses it)."""
        symbol = symbol.strip().upper()
        if symbol not in self._bars:
            series = self.reader.series(self.market, symbol, available_before=self._cut)
            if series["status"] not in ("ok", "symbol_not_in_vintage") or (series["status"] == "ok" and str(series["publication_id"]) != self.publication_id):
                raise PitRerunInputError(f"pinned price vintage {self.publication_id} of {self.market} no longer resolves as pinned "
                                         f"(status {series['status']}, publication {series.get('publication_id')}): the run refuses to mix vintages")
            self._bars[symbol] = {session: bar for session, bar in series["bars"].items() if session <= self.session_date}
        return self._bars[symbol]

    def valid_sessions(self, symbol: str) -> int:
        return sum(1 for bar in self.bars(symbol).values() if _positive(bar.get("close")) and _positive(bar.get("adjusted_close")))

    def price_at(self, symbol: str, on: date | None = None) -> tuple[float | None, str | None]:
        """The close of the last session ≤ ``on`` (default: the session of T); for a fiscal date, within the tolerance."""
        bars = self.bars(symbol)
        limit = on.isoformat() if on is not None else self.session_date
        sessions = [session for session in bars if session <= limit]
        if not sessions:
            return None, None
        session = max(sessions)
        if on is not None and (on - date.fromisoformat(session)).days > FISCAL_PRICE_TOLERANCE_DAYS:
            return None, None
        return _positive(bars[session].get("close")), session

    def _log_returns(self, symbol: str) -> dict[str, float]:
        if symbol not in self._returns:
            bars = self.bars(symbol)
            sessions = sorted(bars)[-(BETA_WINDOW_SESSIONS + 1):]
            returns: dict[str, float] = {}
            for previous, current in zip(sessions, sessions[1:]):
                before, after = _positive(bars[previous].get("adjusted_close")), _positive(bars[current].get("adjusted_close"))
                if before is not None and after is not None:
                    returns[current] = math.log(after / before)
            self._returns[symbol] = returns
        return self._returns[symbol]

    def build_proxy(self, symbols: Sequence[str]) -> None:
        """The equal-weight proxy of the universe's daily log returns up to T (declared: no index series is persisted)."""
        by_session: dict[str, list[float]] = {}
        for symbol in symbols:
            for session, value in self._log_returns(symbol).items():
                by_session.setdefault(session, []).append(value)
        self._proxy = {session: statistics.fmean(values) for session, values in by_session.items() if len(values) >= 2}

    def beta(self, symbol: str) -> tuple[float | None, dict[str, Any]]:
        """OLS beta of the symbol's daily log returns against the proxy over the last ``BETA_WINDOW_SESSIONS`` ≤ T."""
        if self._proxy is None:
            return None, {"status": "proxy_not_built"}
        own = self._log_returns(symbol)
        common = sorted(session for session in own if session in self._proxy)
        if len(common) < BETA_MIN_SESSIONS:
            return None, {"status": "insufficient_sessions", "sessions": len(common)}
        xs = [self._proxy[session] for session in common]
        ys = [own[session] for session in common]
        variance = statistics.pvariance(xs)
        if variance <= 0:
            return None, {"status": "proxy_without_variance", "sessions": len(common)}
        covariance = statistics.fmean((x - statistics.fmean(xs)) * (y - statistics.fmean(ys)) for x, y in zip(xs, ys))
        return covariance / variance, {"status": "recomputed", "method": "ols_daily_log_returns_vs_equal_weight_universe_proxy", "sessions": len(common),
                                       "window_sessions": BETA_WINDOW_SESSIONS}


# ------------------------------------------------------------------ macro at T (§3): dated packages ≤ T
def selic_package_at(history: Mapping[str, Any], *, as_of: datetime, economic_date: date) -> dict[str, Any] | None:
    """A Selic package the engine validates (schema v1, hash recomputed), holding ONLY the observations available at
    ``T`` (each observation's ``available_at`` ≤ T and ``observation_date`` ≤ the economic date), ``as_of`` = the economic
    date. ``history`` is the PIT macro snapshot's outputs (``--fetch``) or the live ``valuation_macro_history`` package —
    both carry dated observations; the provider's vintage of the series is ``N/D``."""
    cut = _utc(as_of)
    observations: list[dict[str, Any]] = []
    for item in history.get("observations") or []:
        data = _mapping(item)
        observed = _parse_date(data.get("observation_date"))
        rate = _number(data.get("annual_rate"))
        available_text = str(data.get("available_at") or (_available_after_day(observed) if observed else ""))
        if observed is None or rate is None or not 0 < rate < 1 or observed > economic_date:
            continue
        try:
            available = _instant(available_text)
        except ValueError:
            continue
        if available > cut:
            continue
        observations.append({"observation_date": observed.isoformat(), "annual_rate": rate, "available_at": available.isoformat()})
    if not observations:
        return None
    observations.sort(key=lambda item: str(item["observation_date"]))
    package: dict[str, Any] = {"schema_version": MACRO_SCHEMA_VERSION, "engine_version": ENGINE_VERSION, "source": SELIC_SOURCE, "series": "SGS 432",
                               "as_of": economic_date.isoformat(), "fetched_at": str(history.get("fetched_at") or ""), "observations": observations,
                               "derived_from": {"kind": "point_in_time_filter", "source_payload_sha256": history.get("payload_sha256")}}
    package["payload_sha256"] = canonical_payload_sha256(package)
    return package


def curve_package_at(history: Mapping[str, Any], *, as_of: datetime, economic_date: date) -> dict[str, Any] | None:
    """The US 3Y/10Y curve package at ``T``: the latest observation date ≤ the economic date with BOTH tenors, available
    (next UTC midnight) ≤ T; validated by ``validate_us_curve_package`` for ``as_of`` = that observation date."""
    cut = _utc(as_of)
    fetched_at = str(history.get("fetched_at") or "")
    by_tenor: dict[int, dict[date, float]] = {}
    series = _mapping(history.get("series"))
    for tenor, symbol in US_CURVE_SYMBOLS:
        by_tenor[tenor] = {}
        for item in series.get(symbol) or []:
            data = _mapping(item)
            observed = _parse_date(data.get("date"))
            rate = _number(data.get("close"))
            if observed is None or rate is None or observed > economic_date or _instant(_available_after_day(observed)) > cut:
                continue
            by_tenor[tenor][observed] = rate / 100 if rate > 1 else rate
    common = set(by_tenor[3]) & set(by_tenor[10])
    if not common:
        return None
    observed = max(common)
    points = [{"symbol": symbol, "tenor_years": tenor, "observation_date": observed.isoformat(), "annual_rate": by_tenor[tenor][observed],
               "available_at": _available_after_day(observed), "source": US_CURVE_SOURCE} for tenor, symbol in US_CURVE_SYMBOLS]
    package: dict[str, Any] = {"schema_version": MACRO_SCHEMA_VERSION, "engine_version": ENGINE_VERSION, "source": US_CURVE_SOURCE, "as_of": observed.isoformat(),
                               "fetched_at": fetched_at, "formula": "r3y + (2/7) * (r10y - r3y)", "points": points,
                               "interpolated_5y_rate": interpolate_us_five_year_rate(by_tenor[3][observed], by_tenor[10][observed]),
                               "derived_from": {"kind": "point_in_time_filter", "source_payload_sha256": history.get("payload_sha256")}}
    package["payload_sha256"] = canonical_payload_sha256(package)
    validate_us_curve_package(package, as_of=observed)
    return package


class MacroAtT:
    """The dated macro inputs of one run: the B3 Selic package (and the Selic rate at T as the B3 risk-free rate, declared)
    or the US curve package, with the snapshot they were derived from."""

    def __init__(self, *, selic_package: dict[str, Any] | None, curve_package: dict[str, Any] | None, b3_risk_free_rate: float | None,
                 references: dict[str, Any]) -> None:
        self.selic_package = selic_package
        self.curve_package = curve_package
        self.b3_risk_free_rate = b3_risk_free_rate
        self.references = references

    def macro_as_of(self, market: str) -> date:
        package = self.selic_package if market == "B3" else self.curve_package
        if package is None:
            raise PitRerunInputError(f"no dated macro package at T for {market}")
        return date.fromisoformat(str(package["as_of"]))


# ------------------------------------------------------------------ the resolver (§3): snapshots → the contexts the shadow path reads
class PitSourceResolver:
    """For a market and ``T``, the ``loaded`` mapping ``valuation_v3_shadow._contexts`` consumes — every role of
    ``_SOURCE_SPECS`` rebuilt from the PIT source snapshots (``valuation_pit_source/<M>_EODHD_FUNDAMENTALS_<hash>``,
    ``<M>_FMP_TARGETS_<hash>``), the pinned price series and the dated macro — plus the references, exclusions and
    hypotheses the manifest and the records declare. Reads the store only; never the network."""

    def __init__(self, database: Database, *, market: str, as_of: datetime, prices: PinnedPrices) -> None:
        if market not in MARKETS:
            raise PitRerunInputError(f"unknown market {market!r}")
        self.database = database
        self.market = market
        self.as_of = _utc(as_of)
        self.economic_date = economic_date_of(market, self.as_of)
        self.prices = prices
        self.references: list[dict[str, Any]] = []
        self.excluded: Counter[str] = Counter()
        self.hypotheses: dict[str, list[dict[str, Any]]] = {}
        self.per_symbol: dict[str, dict[str, Any]] = {}
        self.consensus: dict[str, dict[str, Any]] = {}
        self.not_evaluable: dict[str, str] = {}

    # ---- catalogue (the only current fields admitted: classification)
    def catalogue(self, market: str) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        if snapshot is None:
            return []
        rows = _mapping(snapshot.get("outputs")).get("rows")
        self.references.append({"role": "catalogue", "market": market, "snapshot_id": str(snapshot["id"]),
                                "published_at": _instant(snapshot["published_at"]).isoformat(), "fields_admitted": list(CURRENT_FIELDS_ADMITTED)})
        return [{"symbol": str(row["symbol"]).strip().upper(), **{field: row.get(field) for field in CURRENT_FIELDS_ADMITTED}}
                for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict) and row.get("symbol")]

    def _source_snapshot(self, market: str, provider: str, symbol: str) -> dict[str, Any] | None:
        snapshot = self.database.latest_analysis_snapshot(SOURCE_ANALYSIS_TYPE, source_entity_key(market, provider, symbol))
        if snapshot is None:
            return None
        inputs = _mapping(snapshot.get("inputs"))  # the provider's CURRENT payload, read now: the causal work is the availability filter, never the fetch clock
        self.references.append({"role": provider, "market": market, "symbol_sha256": symbol_hash(symbol), "snapshot_id": str(snapshot["id"]),
                                "payload_sha256": str(inputs.get("payload_sha256") or ""), "fetched_at": str(inputs.get("fetched_at") or ""),
                                "published_at": _instant(snapshot["published_at"]).isoformat()})
        return snapshot

    # ---- one symbol
    def _symbol_inputs(self, market: str, catalogue_row: Mapping[str, Any]) -> dict[str, Any] | None:
        symbol = str(catalogue_row["symbol"])
        snapshot = self._source_snapshot(market, PROVIDER_EODHD, symbol)
        if snapshot is None:
            self.not_evaluable[symbol] = "fundamentals_snapshot_missing"
            return None
        payload = _mapping(_mapping(snapshot.get("outputs")).get("payload"))
        fundamentals = pit_fundamentals(payload, market=market, economic_date=self.economic_date)
        for key, count in fundamentals["excluded"].items():
            self.excluded[key] += count
        if not fundamentals["eligible"]:
            self.not_evaluable[symbol] = "no_statement_available_at_T"
            return None
        if self.prices.valid_sessions(symbol) < MIN_VALID_SESSIONS:
            self.not_evaluable[symbol] = f"fewer_than_{MIN_VALID_SESSIONS}_valid_sessions_at_T"
            return None
        price, price_session = self.prices.price_at(symbol)
        shares = fundamentals["shares"]
        if price is None or shares is None:
            self.not_evaluable[symbol] = "price_or_shares_unavailable_at_T"
            return None
        ttm, balance = fundamentals["ttm"], fundamentals["balance"]
        eps = ttm["net_income"] / shares if ttm["net_income"] is not None else None
        equity = balance["equity"]
        book_value = equity / shares if equity is not None and equity > 0 else None
        market_cap = price * shares
        net_debt = balance["net_debt"]
        ev = market_cap + net_debt if net_debt is not None else None
        dividends = fundamentals["cash_flow_ttm"]["dividends_paid"]
        dividend_yield = abs(dividends) / shares / price if dividends else None
        beta, beta_audit = self.prices.beta(symbol)
        if beta is None:
            self.excluded["beta:not_recomputable"] += 1
        row = {"symbol": symbol, **{field: catalogue_row.get(field) for field in CURRENT_FIELDS_ADMITTED}, "price": price, "price_session": price_session,
               "market_cap": market_cap, "shares": shares, "eps": eps, "pe": price / eps if eps is not None and eps > 0 else None, "forward_pe": None,
               "ev_ebitda": ev / ttm["ebitda"] if ev is not None and ttm["ebitda"] is not None and ttm["ebitda"] > 0 else None,
               "book_value": book_value, "price_to_book": price / book_value if book_value else None,
               "roe": ttm["net_income"] / equity if ttm["net_income"] is not None and equity is not None and equity > 0 else None,
               "dividend_yield": dividend_yield, "beta": beta, "debt": balance["debt"], "cash": balance["cash"], "fundamentals_as_of": fundamentals["fundamentals_as_of"]}
        ratios: list[dict[str, Any]] = []
        key_metrics: list[dict[str, Any]] = []
        for year in fundamentals["fiscal_years"]:
            fiscal_end = date.fromisoformat(year["fiscal_year_end"])
            fy_price, _session = self.prices.price_at(symbol, on=fiscal_end)
            fy_shares = year["shares"]
            if fy_price is None or not fy_shares:
                self.excluded["fiscal_year:no_price_or_shares"] += 1
                continue
            fy_eps = year["net_income"] / fy_shares if year["net_income"] is not None else None
            fy_equity = year["equity"]
            fy_mcap = fy_price * fy_shares
            fy_ev = fy_mcap + year["net_debt"] if year["net_debt"] is not None else None
            fy_roe = year["net_income"] / fy_equity if year["net_income"] is not None and fy_equity is not None and fy_equity > 0 else None
            ratios.append({"fiscal_year_end": year["fiscal_year_end"], "pe": fy_price / fy_eps if fy_eps is not None and fy_eps > 0 else None,
                           "ev_ebitda": fy_ev / year["ebitda"] if fy_ev is not None and year["ebitda"] is not None and year["ebitda"] > 0 else None,
                           "price_to_book": fy_price / (fy_equity / fy_shares) if fy_equity is not None and fy_equity > 0 else None, "roe": fy_roe,
                           "dividend_yield": abs(year["dividends_paid"]) / fy_shares / fy_price if year["dividends_paid"] else None})
            key_metrics.append({"fiscal_year_end": year["fiscal_year_end"], "eps": fy_eps, "market_cap": fy_mcap, "enterprise_value": fy_ev, "roe": fy_roe})
        chewie = None
        if row["roe"] is not None and fundamentals["revenue_growth"] is not None:
            chewie = {"symbol": symbol, "profitability": {"roe_percent": row["roe"] * 100}, "growth": {"revenue_growth_percent": fundamentals["revenue_growth"] * 100},
                      "fundamentals_as_of": fundamentals["fundamentals_as_of"]}
        else:
            self.excluded["trailing_quality:not_recomputable"] += 1
        self.hypotheses[symbol] = list(fundamentals["hypotheses"])
        return {"row": row, "ratios_annual": ratios, "key_metrics_annual": key_metrics, "chewie": chewie, "beta_audit": beta_audit,
                "fundamentals": {key: fundamentals[key] for key in ("fundamentals_as_of", "eligible_periods", "excluded", "shares_availability")}}

    def _consensus_for(self, symbol: str) -> None:
        if self.market == "B3":
            self.excluded["consensus:not_covered_for_B3"] += 1
            return
        snapshot = self._source_snapshot(self.market, PROVIDER_FMP, symbol)
        if snapshot is None:
            self.excluded["consensus:targets_snapshot_missing"] += 1
            return
        rows = _mapping(snapshot.get("outputs")).get("payload")
        block, refused = consensus_at(rows if isinstance(rows, list) else [], as_of=self.as_of, currency=CURRENCY[self.market])
        for key, count in refused.items():
            self.excluded[f"consensus:{key}"] += count
        if block is not None:
            self.consensus[symbol] = block

    # ---- the whole market (and its peer markets)
    def resolve(self) -> dict[tuple[str, str], dict[str, Any]]:
        """The ``loaded`` mapping of ``_contexts`` (every role/market of ``_SOURCE_SPECS`` present; peer markets rebuilt when
        their snapshots exist, empty otherwise), with peers = the same-sector names of the peer markets."""
        catalogue = self.catalogue(self.market)
        self.prices.build_proxy([row["symbol"] for row in catalogue])
        inputs_by_market: dict[str, dict[str, dict[str, Any]]] = {market: {} for market in MARKETS}
        for catalogue_row in catalogue:
            symbol = catalogue_row["symbol"]
            resolved = self._symbol_inputs(self.market, catalogue_row)
            if resolved is not None:
                inputs_by_market[self.market][symbol] = resolved
                self.per_symbol[symbol] = resolved
                self._consensus_for(symbol)
        for market in PEER_MARKETS[self.market]:
            if market != self.market:  # the sibling US market has its OWN pinned vintage: its names are not peers of this run (declared, counted)
                self.excluded[f"peer_market_{market}:not_loaded_in_this_run"] += 1
        sectors = {symbol: str(item["row"].get("sector") or "") for market in MARKETS for symbol, item in inputs_by_market[market].items()}
        loaded: dict[tuple[str, str], dict[str, Any]] = {}
        for market in MARKETS:
            items = inputs_by_market[market]
            rows = [{key: value for key, value in item["row"].items() if key != "price_session"} for item in items.values()]
            packets = {symbol: {"symbol": symbol, "peers": [{"symbol": peer} for peer, sector in sorted(sectors.items())
                                                             if peer != symbol and sector and sector == sectors[symbol]],
                                "analyst_estimates_annual": [], "ratios_annual": item["ratios_annual"], "key_metrics_annual": item["key_metrics_annual"]}
                       for symbol, item in items.items()}
            chewie_items = [item["chewie"] for item in items.values() if item["chewie"] is not None]
            loaded[("universe", market)] = {"entity_key": f"{market}_UNIVERSE", "outputs": {"rows": rows}}
            loaded[("v2_data", market)] = {"entity_key": f"{market}_V2_DATA", "outputs": {"packets": packets}}
            loaded[("chewie", market)] = {"entity_key": f"{market}_FUNDAMENTALS", "outputs": {"items": chewie_items}}
            loaded[("v2_shadow", market)] = {"entity_key": f"{market}_V2_SHADOW", "outputs": {"results": {}}}
        for peer_market in ("B3", "US"):
            loaded[("peer_quality", peer_market)] = {"entity_key": f"{peer_market}_V2_PEER_QUALITY", "outputs": {"packets": {}}}  # ABSENT: no history (§3)
        self.excluded["analyst_estimates:no_history"] += len(self.per_symbol)
        self.excluded["peer_quality:no_history"] += len(self.per_symbol)
        return loaded

    def macro(self) -> MacroAtT:
        references: dict[str, Any] = {}
        selic_package: dict[str, Any] | None = None
        curve_package: dict[str, Any] | None = None
        b3_rate: float | None = None
        if self.market == "B3":
            snapshot = self.database.latest_analysis_snapshot(SOURCE_ANALYSIS_TYPE, MACRO_SELIC_KEY)
            origin = "pit_source"
            history = _mapping(_mapping((snapshot or {}).get("outputs")).get("payload"))  # a PIT source snapshot keeps the raw payload under outputs.payload
            if snapshot is None:
                snapshot = self.database.latest_analysis_snapshot(LIVE_SELIC_SPEC[2], LIVE_SELIC_SPEC[3])
                origin = "live_macro_history"
                history = _mapping((snapshot or {}).get("outputs"))  # the live package IS the outputs
            if snapshot is None:
                raise PitRerunInputError("no Selic history snapshot (PIT source or live macro history)")
            selic_package = selic_package_at(history, as_of=self.as_of, economic_date=self.economic_date)
            if selic_package is None:
                raise PitRerunInputError("no Selic observation available at T")
            b3_rate = float(selic_package["observations"][-1]["annual_rate"])
            references["selic"] = {"origin": origin, "snapshot_id": str(snapshot["id"]), "source_payload_sha256": history.get("payload_sha256"),
                                   "derived_payload_sha256": selic_package["payload_sha256"], "as_of": selic_package["as_of"],
                                   "b3_risk_free_source": "bcb_sgs_432_at_T", "historical_vintage": "N/D"}
        else:
            snapshot = self.database.latest_analysis_snapshot(SOURCE_ANALYSIS_TYPE, MACRO_TREASURY_KEY)
            if snapshot is None:
                raise PitRerunInputError("no US Treasury history snapshot (valuation_pit_source/US_EODHD_TREASURY_HISTORY)")
            history = _mapping(_mapping(snapshot.get("outputs")).get("payload"))
            curve_package = curve_package_at(history, as_of=self.as_of, economic_date=self.economic_date)
            if curve_package is None:
                raise PitRerunInputError("no US 3Y/10Y observation available at T")
            references["curve"] = {"origin": "pit_source", "snapshot_id": str(snapshot["id"]), "source_payload_sha256": history.get("payload_sha256"),
                                   "derived_payload_sha256": curve_package["payload_sha256"], "as_of": curve_package["as_of"], "historical_vintage": "N/D"}
        return MacroAtT(selic_package=selic_package, curve_package=curve_package, b3_risk_free_rate=b3_rate, references=references)

    def calibration(self) -> dict[str, Any]:
        """The calibration factor at T: the latest ``valuation_v3_calibration/<M>_CALIBRATION`` snapshot published BEFORE T,
        else ``absent_at_T`` → factor 1.0 (marked)."""
        snapshot = self.database.latest_analysis_snapshot_before(CALIBRATION_ANALYSIS_TYPE, f"{self.market}_CALIBRATION", self.as_of)
        factor = _positive(_mapping((snapshot or {}).get("outputs")).get("factor")) if snapshot else None
        if snapshot is None or factor is None:
            return {"status": "absent_at_T", "factor": 1.0, "snapshot_id": None}
        return {"status": "applied", "factor": factor, "snapshot_id": str(snapshot["id"]), "published_at": _instant(snapshot["published_at"]).isoformat()}


# ------------------------------------------------------------------ the engine, by the shadow path (§1)
def evaluate_loaded(market: str, loaded: Mapping[tuple[str, str], dict[str, Any]], *, as_of_date: date, macro: MacroAtT) -> dict[str, dict[str, Any]]:
    """EXACTLY the shadow's path: ``_contexts`` → one ``ValuationV3Engine`` (``today = T``, ``macro_as_of ≤ T``, the dated
    packages) → ``_evaluate_market``. Formulas, constants and ``h`` untouched. Shared by the run and the equivalence test."""
    contexts = ValuationV3ShadowService._contexts(loaded, as_of=as_of_date)
    engine_market = ENGINE_MARKET[market]
    engine = ValuationV3Engine(market=engine_market, risk_free_rate=macro.b3_risk_free_rate if market == "B3" else None, today=as_of_date,
                               macro_as_of=macro.macro_as_of(market), us_curve_package=macro.curve_package if market != "B3" else None,
                               selic_package=macro.selic_package if market == "B3" else None, enable_quality=True, enable_selic=True,
                               enable_treasury=market != "B3")
    return ValuationV3ShadowService._evaluate_market(engine, contexts[market])


# ------------------------------------------------------------------ the run
class PitComputation:
    """The ECONOMIC result of one run — everything but the persistence clock. Built by ``PitRerunService.compute`` with no
    access to ``now``; ``persist`` adds the clock."""

    def __init__(self, *, market: str, as_of: datetime, results: dict[str, dict[str, Any]], resolver: PitSourceResolver, macro: MacroAtT,
                 calibration: dict[str, Any], manifest: dict[str, Any], run_key: str, version: str) -> None:
        self.market = market
        self.as_of = _utc(as_of)
        self.results = results
        self.resolver = resolver
        self.macro = macro
        self.calibration = calibration
        self.manifest = manifest
        self.run_key = run_key
        self.source_version = version
        self.entity_key = f"{market}_PIT_{run_key[:16]}"

    def provenance_for(self, symbol: str) -> dict[str, Any]:
        item = self.resolver.per_symbol.get(symbol) or {}
        excluded: Counter[str] = Counter(dict(self.resolver.excluded))
        return {
            "engine": engine_identity(), "engine_version": ENGINE_VERSION, "engine_path": "valuation_v3_shadow._contexts/_evaluate_market",
            "buy_in_rule": buy_in_identity(), "buy_in_parameters": {"risk_score": ENTRY_RISK_SCORE, "valuation_confidence": ENTRY_CONFIDENCE, "declared": "neutral_constants:no_point_in_time_risk_model"},
            "price_vintage": {"publication_id": self.manifest["price_vintage"]["publication_id"], "available_at": self.manifest["price_vintage"]["available_at"],
                              "historical_vintage": "N/D"},
            "availability_rule": AVAILABILITY_RULE,
            "availability_hypotheses": list(self.resolver.hypotheses.get(symbol) or []),
            "pit_excluded_inputs": dict(sorted(excluded.items())),
            "current_fields_admitted": list(CURRENT_FIELDS_ADMITTED),
            "beta": item.get("beta_audit"),
            "eligible_periods": _mapping(item.get("fundamentals")).get("eligible_periods"),
            "macro": self.macro.references,
            "calibration": dict(self.calibration),
            "run_key": self.run_key,
            "consensus_in_engine": False,  # the TP is the engine's INTERNAL TP: the consensus never enters the row the engine sees
            "diagnostic_only": True,
        }

    def records(self, *, cycle_id: str, published_at: datetime) -> list[dict[str, Any]]:
        """The prediction records of the run for a cycle and its clock — deterministic but for ``id``."""
        records: list[dict[str, Any]] = []
        factor = float(self.calibration["factor"])
        for symbol in sorted(self.results):
            result = self.results[symbol]
            internal = _positive(result.get("v3_internal_tp"))
            models = {str(name): _positive(_mapping(model).get("tp")) for name, model in _mapping(result.get("models")).items()}
            model_tps = [tp for tp in models.values() if tp is not None]
            if internal is None or not model_tps:
                continue
            tp = internal * factor
            discount = official_entry_discount_v1(ENGINE_MARKET[self.market], ENTRY_RISK_SCORE, ENTRY_CONFIDENCE)
            buy_in = official_buy_in_v1(model_tps, discount, statistics.mean(model_tps))
            item = self.resolver.per_symbol.get(symbol) or {}
            row: dict[str, Any] = {
                "symbol": symbol, "our_tp": tp, "buy_in": buy_in, "internal_tp": internal, "price": _positive(result.get("price")),
                "bear_tp": _positive(result.get("bear_tp")), "bull_tp": _positive(result.get("bull_tp")), "methods": models,
                "calibration_factor": factor, "valuation_profile": result.get("profile"), "risk_score": ENTRY_RISK_SCORE, "valuation_confidence": ENTRY_CONFIDENCE,
                "method_dispersion_percent": ((_number(result.get("dispersion_ratio")) or 1.0) - 1) * 100,
                "signal_quality": "retrospective_point_in_time", "status": "retrospective", "tp_validation_status": "diagnostic_only",
                "source_name": engine_identity(), "fundamentals_as_of": _mapping(item.get("fundamentals")).get("fundamentals_as_of"), "as_of": self.as_of.isoformat(),
            }
            consensus = self.resolver.consensus.get(symbol)
            if consensus is not None:  # dated ≤ T by construction; persisted BESIDE the TP, never inside it
                row.update({"public_consensus_tp": consensus["consensus_tp"], "analyst_count": consensus["analyst_count"], "consensus_origin_source": consensus["source"],
                            "consensus_published_at": consensus["published_at"], "consensus_as_of": consensus["published_at"], "consensus_horizon": consensus["horizon"],
                            "consensus_currency": consensus["currency"], "consensus_gap_percent": (consensus["consensus_tp"] / tp - 1) * 100})
            record = prediction_from_row(row, market=self.market, scope="universe", cycle_id=cycle_id, source_version=self.source_version,
                                         prediction_instant=self.as_of, source_manifest_sha256=self.manifest["manifest_sha256"], published_at=published_at,
                                         rerun_of=None, source=SOURCE, extra_provenance=self.provenance_for(symbol))
            if record is not None:
                records.append(record)
        return records

    def summary(self) -> dict[str, Any]:
        with_tp = sum(1 for result in self.results.values() if _positive(result.get("v3_internal_tp")) is not None)
        return {"evaluated": len(self.results), "with_internal_tp": with_tp, "not_evaluable": dict(Counter(self.resolver.not_evaluable.values())),
                "with_consensus": len(self.resolver.consensus), "pit_excluded_inputs": dict(sorted(self.resolver.excluded.items())),
                "hypotheses": sum(len(items) for items in self.resolver.hypotheses.values()), "calibration": self.calibration["status"],
                "macro_as_of": self.macro.macro_as_of(self.market).isoformat(), "price_vintage": self.manifest["price_vintage"]["publication_id"]}


@contextmanager
def _run_lock(database: Database, run_key: str) -> Iterator[None]:
    """The critical section of one run's write (§4): a process lock keyed by ``run_key`` and, with PostgreSQL, a session-level
    advisory lock on ``advisory_lock_key(run_key)`` held on a dedicated connection across the snapshot and the records."""
    with _RUN_LOCKS_GUARD:
        lock = _RUN_LOCKS.setdefault(run_key, threading.Lock())
    with lock:
        if not database.database_url:
            yield
            return
        key = advisory_lock_key(run_key)
        with database.connection() as connection:
            connection.execute("SELECT pg_advisory_lock(%s)", (key,))
            try:
                yield
            finally:
                connection.execute("SELECT pg_advisory_unlock(%s)", (key,))
                connection.commit()


class PitRerunService:
    """``--rerun``: no network (the price reader is built on ``_NoNetworkHttp``), the store only."""

    def __init__(self, database: Database, *, settings: Settings | None = None, price_history: PriceHistoryService | None = None) -> None:
        self.database = database
        self.http: _NoNetworkHttp | None = None if price_history is not None else _NoNetworkHttp()
        self.price_history = price_history if price_history is not None else PriceHistoryService(settings if settings is not None else get_settings(), database,
                                                                                                     cast(JsonHttpClient, self.http))

    def pin_vintage(self, market: str, *, as_of: datetime, pinned_at: datetime) -> PinnedPrices:
        """Resolved ONCE at run start: the latest publication available before ``pinned_at`` (the persistence clock's reading at
        start — the ONLY clock read before the economic computation, and only to select the vintage)."""
        return PinnedPrices(self.price_history, market, as_of=as_of, pinned_at=pinned_at)

    def compute(self, market: str, *, as_of: datetime, prices: PinnedPrices) -> PitComputation:
        """The ECONOMIC computation: T, the filters, the engine's ``today``, the macro ``as_of``, the consensus cut — nothing
        here reads ``now`` (pinned by the exploding-clock test)."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise PitRerunInputError("T must carry a time zone")
        resolver = PitSourceResolver(self.database, market=market, as_of=as_of, prices=prices)
        loaded = resolver.resolve()
        macro = resolver.macro()
        calibration = resolver.calibration()
        results = evaluate_loaded(market, loaded, as_of_date=resolver.economic_date, macro=macro)
        version = source_version()
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "market": market, "as_of": _utc(as_of).isoformat(), "economic_date": resolver.economic_date.isoformat(),
            "session_date": prices.session_date, "engine": {"identity": engine_identity(), "engine_version": ENGINE_VERSION,
                                                            "implementation_file_sha256": {name: _file_sha256(name) for name in ("valuation_v3_engine.py", "valuation_v3_inputs.py", "valuation_v3_macro.py", "valuation_v3_shadow.py", "valuation_pit_rerun.py")}},
            "buy_in_rule": {"identity": buy_in_identity(), "risk_score": ENTRY_RISK_SCORE, "valuation_confidence": ENTRY_CONFIDENCE},
            "sources": sorted(resolver.references, key=lambda item: json.dumps(item, sort_keys=True)),
            "price_vintage": prices.manifest(), "macro": macro.references, "calibration": calibration,
            "availability_rule": AVAILABILITY_RULE, "consensus_rule": {"window_days": CONSENSUS_WINDOW_DAYS, "min_houses": MIN_CONSENSUS_HOUSES, "horizon": CONSENSUS_HORIZON},
            "external_api_calls": 0,
        }
        manifest["manifest_sha256"] = canonical_sha256({key: value for key, value in manifest.items() if key != "manifest_sha256"})
        run_key = run_key_of(source_version_text=version, market=market, as_of=as_of, manifest=manifest)
        return PitComputation(market=market, as_of=as_of, results=results, resolver=resolver, macro=macro, calibration=calibration, manifest=manifest,
                              run_key=run_key, version=version)

    def persist(self, computation: PitComputation, *, clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
        """§4: find-or-write under the run's lock; the set of prediction identities decides completeness."""
        tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        market, run_key = computation.market, computation.run_key
        with _run_lock(self.database, run_key):
            existing = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, computation.entity_key)
            supersedes: str | None = None
            if existing is not None and str(_mapping(existing.get("inputs")).get("run_key")) == run_key:
                cycle_id, published_at, idempotent = str(existing["id"]), _instant(existing["published_at"]), True
                records = computation.records(cycle_id=cycle_id, published_at=published_at)
            else:
                previous = self.database.latest_analysis_snapshot_by_inputs(ANALYSIS_TYPE, {"market": market, "as_of": computation.as_of.isoformat()})
                if previous is not None and str(_mapping(previous.get("inputs")).get("run_key")) != run_key:
                    supersedes = str(_mapping(previous.get("inputs")).get("run_key"))
                cycle_id, published_at, idempotent = str(uuid4()), _utc(tick()), False
                if published_at < computation.as_of:
                    raise PitRerunInputError(f"the persistence clock {published_at.isoformat()} precedes T {computation.as_of.isoformat()}: a retrospective run is never dated before T")
                records = computation.records(cycle_id=cycle_id, published_at=published_at)
                methodology_id = self.database.ensure_methodology_version(METHODOLOGY_KEY, METHODOLOGY_VERSION,
                                                                          {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION, "external_api_calls": 0,
                                                                           "diagnostic_only": True, "official_tp_replacement_authorized": False},
                                                                          "Point-in-time re-execution of the V3 engine (design rev 2 of 2026-09-11); diagnostic only.")
                inputs = {"schema_version": SCHEMA_VERSION, "run_key": run_key, "market": market, "as_of": computation.as_of.isoformat(), "source": SOURCE,
                          "source_version": computation.source_version, "manifest": computation.manifest, "external_api_calls": 0}
                if supersedes:
                    inputs["supersedes"] = supersedes
                outputs = {"schema_version": SCHEMA_VERSION, "run_key": run_key, "market": market, "as_of": computation.as_of.isoformat(), "published_at": published_at.isoformat(),
                           "rows": computation.results, "summary": computation.summary(), "not_evaluable": dict(computation.resolver.not_evaluable),
                           "prediction_identities": [[record["symbol"], record["row_sha256"]] for record in records],
                           "governance": {"diagnostic_only": True, "decision_consumer": False, "official_tp_replacement_authorized": False, "external_api_calls": 0}}
                self.database.save_analysis_snapshot(ANALYSIS_TYPE, computation.entity_key, methodology_id, inputs, outputs, published_at, snapshot_id=cycle_id)
            expected = {(str(record["symbol"]), str(record["row_sha256"])): record for record in records}
            stored = {(str(symbol), str(record["row_sha256"])) for symbol, record in self.database.valuation_predictions_for_cycle(cycle_id, source=SOURCE).items()}
            foreign = stored - set(expected)
            if foreign:
                raise PitRerunIntegrityError(f"cycle {cycle_id} of run {run_key[:16]} holds {len(foreign)} prediction identities the computation does not reproduce")
            missing = [expected[key] for key in sorted(set(expected) - stored)]
            inserted = self.database.insert_valuation_predictions(missing) if missing else 0
            self.database.drop_official_cycle_cache()
        return {"schema_version": SCHEMA_VERSION, "market": market, "as_of": computation.as_of.isoformat(), "run_key": run_key, "cycle_id": cycle_id,
                "entity_key": computation.entity_key, "published_at": published_at.isoformat(), "idempotent": idempotent, "supersedes": supersedes,
                "records": {"expected": len(expected), "stored_before": len(stored), "inserted": inserted, "complete": len(stored) + inserted == len(expected)},
                "source_version": computation.source_version, "manifest_sha256": computation.manifest["manifest_sha256"], **computation.summary()}

    def rerun(self, market: str, *, as_of: datetime, clock: Callable[[], datetime] | None = None) -> tuple[dict[str, Any], PitComputation]:
        tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        prices = self.pin_vintage(market, as_of=as_of, pinned_at=tick())
        computation = self.compute(market, as_of=as_of, prices=prices)
        return self.persist(computation, clock=tick), computation


# ------------------------------------------------------------------ --fetch (§5): one read per symbol, dated and hashed snapshots
class PitFetchService:
    """Reads the providers ONCE per symbol through the existing HTTP client and persists the RAW payloads as
    ``valuation_pit_source`` snapshots (``fetched_at`` real, ``payload_sha256``). Never runs during a session or a phase;
    only under the owner's authorization (design §7–§8). Nothing nominal leaves this class in its aggregate."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        self.eodhd = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self.fmp = FmpClient(settings.fmp_base_url, settings.fmp_api_token, http)

    def _methodology_id(self) -> str:
        return self.database.ensure_methodology_version(f"{METHODOLOGY_KEY}_source", METHODOLOGY_VERSION, {"schema_version": SCHEMA_VERSION, "raw_payloads": True},
                                                        "Raw provider payloads for the point-in-time re-execution; dated and hashed; read once per symbol.")

    def _persist(self, entity_key: str, *, provider: str, endpoint: str, market: str, symbol: str | None, payload: Any, fetched_at: datetime) -> str:
        payload_sha256 = canonical_sha256(payload)
        inputs: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "provider": provider, "endpoint": endpoint, "market": market, "fetched_at": fetched_at.isoformat(),
                                  "payload_sha256": payload_sha256}
        if symbol is not None:
            inputs.update({"symbol": symbol, "symbol_sha256": symbol_hash(symbol)})
        outputs: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "payload_sha256": payload_sha256, "fetched_at": fetched_at.isoformat(), "payload": payload}
        return self.database.save_analysis_snapshot(SOURCE_ANALYSIS_TYPE, entity_key, self._methodology_id(), inputs, outputs, fetched_at)

    def catalogue_symbols(self, market: str) -> list[str]:
        snapshot = self.database.latest_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE")
        rows = _mapping((snapshot or {}).get("outputs")).get("rows")
        return sorted({str(row["symbol"]).strip().upper() for row in (rows if isinstance(rows, list) else []) if isinstance(row, dict) and row.get("symbol")})

    def fetch_fundamentals(self, market: str, symbol: str) -> str:
        provider_symbol = f"{symbol}.{PROVIDER_SUFFIX[market]}"
        payload = self.http.get_json(f"{self.eodhd.base_url}/api/v1.1/fundamentals/{provider_symbol}", params={"api_token": self.eodhd.token, "fmt": "json"})
        if not isinstance(payload, dict) or not payload:
            raise PitRerunInputError("empty fundamentals payload")
        return self._persist(source_entity_key(market, PROVIDER_EODHD, symbol), provider="eodhd", endpoint="/api/v1.1/fundamentals", market=market, symbol=symbol,
                             payload=payload, fetched_at=datetime.now(timezone.utc))

    def fetch_targets(self, market: str, symbol: str, *, pages: int = 20, limit: int = 100) -> str:
        rows: list[dict[str, Any]] = []
        for page in range(pages):
            payload = self.http.get_json(f"{self.fmp.base_url}/stable/price-target-news", params={"symbol": symbol, "page": page, "limit": limit, "apikey": self.fmp.token})
            batch = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
            rows.extend(batch)
            if len(batch) < limit:
                break
        return self._persist(source_entity_key(market, PROVIDER_FMP, symbol), provider="fmp", endpoint="/stable/price-target-news", market=market, symbol=symbol,
                             payload=rows, fetched_at=datetime.now(timezone.utc))

    def fetch_macro(self, market: str, *, years: int = 15) -> str:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=years * 366)
        if market == "B3":
            observations: dict[str, dict[str, Any]] = {}
            chunk_start = start
            while chunk_start <= today:
                chunk_end = min(today, chunk_start + timedelta(days=4 * 365))
                raw = self.http.get_json(BCB_SELIC_SERIES_URL, params={"formato": "json", "dataInicial": chunk_start.strftime("%d/%m/%Y"), "dataFinal": chunk_end.strftime("%d/%m/%Y")})
                for item in raw if isinstance(raw, list) else []:
                    data = _mapping(item)
                    try:
                        observed = datetime.strptime(str(data.get("data") or ""), "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    rate = _number(data.get("valor"))
                    if rate is not None:
                        observations[observed.isoformat()] = {"observation_date": observed.isoformat(), "annual_rate": rate / 100, "available_at": _available_after_day(observed)}
                chunk_start = chunk_end + timedelta(days=1)
            fetched_at = datetime.now(timezone.utc)
            payload: dict[str, Any] = {"source": SELIC_SOURCE, "series": "SGS 432", "fetched_at": fetched_at.isoformat(), "observations": [observations[key] for key in sorted(observations)]}
            payload["payload_sha256"] = canonical_payload_sha256(payload)
            return self._persist(MACRO_SELIC_KEY, provider="bcb", endpoint="sgs.432", market=market, symbol=None, payload=payload, fetched_at=fetched_at)
        series = {symbol: self.eodhd.daily_bars(symbol, exchange="GBOND", start=start, end=today) for _tenor, symbol in US_CURVE_SYMBOLS}
        fetched_at = datetime.now(timezone.utc)
        payload = {"source": US_CURVE_SOURCE, "fetched_at": fetched_at.isoformat(), "series": {symbol: [{"date": row.get("date"), "close": row.get("close")} for row in rows]
                                                                                             for symbol, rows in series.items()}}
        payload["payload_sha256"] = canonical_payload_sha256(payload)
        return self._persist(MACRO_TREASURY_KEY, provider="eodhd", endpoint="/api/eod (GBOND)", market="US", symbol=None, payload=payload, fetched_at=fetched_at)

    def fetch(self, market: str, symbols: Sequence[str] | None = None, *, macro: bool = True) -> dict[str, Any]:
        """Aggregate only: counts, never a symbol."""
        wanted = sorted({s.strip().upper() for s in (symbols if symbols is not None else self.catalogue_symbols(market)) if s.strip()})
        counts: Counter[str] = Counter()
        for symbol in wanted:
            try:
                self.fetch_fundamentals(market, symbol)
                counts["fundamentals_persisted"] += 1
            except Exception as error:  # the provider's failure is evidence, counted; nothing nominal is logged
                counts[f"fundamentals_failed:{type(error).__name__}"] += 1
            if market != "B3":
                try:
                    self.fetch_targets(market, symbol)
                    counts["targets_persisted"] += 1
                except Exception as error:
                    counts[f"targets_failed:{type(error).__name__}"] += 1
        macro_snapshot: str | None = None
        if macro:
            macro_snapshot = self.fetch_macro(market)
        return {"schema_version": SCHEMA_VERSION, "market": market, "symbols_requested": len(wanted), **dict(sorted(counts.items())), "macro_snapshot_id": macro_snapshot}


# ------------------------------------------------------------------ CLI
def write_private_detail(path: Path, detail: Mapping[str, Any]) -> None:
    """``O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW``, mode 0600: an existing path or a symlink is refused, nothing written."""
    if path.is_symlink() or path.exists():
        raise FileExistsError(f"detail path {path} exists (or is a symlink): the private detail is written to a NEW path only")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(detail, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _cli_instant(parser: argparse.ArgumentParser, option: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parser.error(f"{option} must be an ISO-8601 instant with a zone, e.g. 2024-06-14T21:00:00-03:00, got {value!r}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parser.error(f"{option} must carry a time zone (no naive instant, no now()), got {value!r}")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None, *, database: Database | None = None, settings: Settings | None = None, http: JsonHttpClient | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valuation V3.2 point-in-time re-executor (diagnostic): --fetch the provider payloads once per symbol, or "
                                                 "--rerun the V3 engine at --as-of T from persisted snapshots only (no network). Prints aggregates, never a symbol.")
    parser.add_argument("--market", choices=MARKETS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fetch", action="store_true", help="read EODHD fundamentals (+ FMP price-target history for US markets, + the macro history) once per symbol")
    group.add_argument("--rerun", action="store_true", help="re-execute the engine at --as-of T (zone mandatory) from snapshots + the pinned price vintage")
    parser.add_argument("--symbols", default="", help="with --fetch: comma-separated override of the catalogue")
    parser.add_argument("--as-of", default=None, help="with --rerun: T, ISO-8601 WITH zone")
    parser.add_argument("--detail", type=Path, default=None, help="with --rerun: write the PRIVATE per-symbol detail to this NEW path (O_EXCL|O_NOFOLLOW, 0600)")
    parser.add_argument("--no-macro", action="store_true", help="with --fetch: skip the macro history")
    args = parser.parse_args(argv)
    if args.rerun and args.as_of is None:
        parser.error("--rerun requires --as-of")
    if args.fetch and (args.as_of or args.detail):
        parser.error("--as-of/--detail apply to --rerun only")
    if args.rerun and args.symbols:
        parser.error("--symbols applies to --fetch only")
    if args.detail is not None and (args.detail.is_symlink() or args.detail.exists()):
        parser.error(f"--detail {args.detail} exists (or is a symlink): the private detail is written to a NEW path only, nothing written")
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings)
    if args.fetch:
        if http is None:
            from .market_data.service import MarketDataService  # the same HTTP client (timeouts/retries) the workers use
            http = MarketDataService(settings, database).http
        symbols = [s for s in args.symbols.split(",") if s.strip()] or None
        result = PitFetchService(settings, database, http).fetch(args.market, symbols, macro=not args.no_macro)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    as_of = _cli_instant(parser, "--as-of", str(args.as_of))
    service = PitRerunService(database, settings=settings)
    receipt, computation = service.rerun(args.market, as_of=as_of)
    if args.detail is not None:
        write_private_detail(args.detail, {"schema": f"{SCHEMA_VERSION}:detail", "run_key": receipt["run_key"], "cycle_id": receipt["cycle_id"],
                                           "results": computation.results, "not_evaluable": dict(computation.resolver.not_evaluable),
                                           "consensus": computation.resolver.consensus, "hypotheses": computation.resolver.hypotheses})
    assert service.http is None or service.http.calls == 0
    print(json.dumps(receipt, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
