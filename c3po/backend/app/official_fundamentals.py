from __future__ import annotations

import copy
import math
from datetime import datetime, timezone
from typing import Any

from .database import Database


ANALYSIS_TYPE = "official_fundamentals"
METHODOLOGY_KEY = "official_fundamentals_overlay"
METHODOLOGY_VERSION = 1

UNIP6_2T26_RELEASE_URL = (
    "https://api.mziq.com/mzfilemanager/v2/d/"
    "3c0b3516-7dff-44a5-946f-20e7ec87dfa0/"
    "bd18e23a-20cf-5455-dc94-ecb4f607acce?origin=2"
)

# Values are consolidated and expressed in BRL. The official quarter rows are
# intentionally separated from provider estimates so provenance remains clear.
BUILTIN_OFFICIAL_FUNDAMENTALS: tuple[dict[str, Any], ...] = (
    {
        "market": "B3",
        "symbol": "UNIP6",
        "as_of": "2026-06-30",
        "published_at": "2026-08-06T12:00:00+00:00",
        "source_name": "Unipar RI - Release de Resultados 2T26",
        "source_url": UNIP6_2T26_RELEASE_URL,
        "currency": "BRL",
        "unit": "BRL",
        "sharesOutstanding": 113_173_265,
        "quarterlyIncome": [
            {
                "date": "2026-06-30",
                "totalRevenue": 1_495_676_000,
                "grossProfit": 497_588_000,
                "operatingIncome": 300_481_000,
                "incomeBeforeTax": 213_775_000,
                "incomeTaxExpense": 90_454_000,
                "netIncome": 123_321_000,
                "ebitda": 386_000_000,
                "adjustedRecurringEbitda": 402_000_000,
            },
            {
                "date": "2026-03-31",
                "totalRevenue": 1_238_235_000,
                "grossProfit": 254_188_000,
                "operatingIncome": 84_970_000,
                "incomeBeforeTax": 52_317_000,
                "incomeTaxExpense": 15_069_000,
                "netIncome": 37_248_000,
                "ebitda": 154_000_000,
                "adjustedRecurringEbitda": 145_000_000,
            },
            {
                "date": "2025-06-30",
                "totalRevenue": 1_273_920_000,
                "grossProfit": 381_509_000,
                "operatingIncome": 311_776_000,
                "incomeBeforeTax": 314_116_000,
                "incomeTaxExpense": 82_614_000,
                "netIncome": 231_502_000,
                "ebitda": 389_000_000,
                "adjustedRecurringEbitda": 306_000_000,
            },
        ],
        "quarterlyCashFlow": [
            {
                "date": "2026-06-30",
                "totalCashFromOperatingActivities": 432_660_000,
                "capitalExpenditures": -150_876_000,
                "freeCashFlow": 281_784_000,
                "operationalCashGeneration": 347_000_000,
            },
            {
                "date": "2026-03-31",
                "totalCashFromOperatingActivities": 185_177_000,
                "capitalExpenditures": -167_251_000,
                "freeCashFlow": 17_926_000,
                "operationalCashGeneration": 316_000_000,
            },
        ],
        "quarterlyBalance": [
            {
                "date": "2026-06-30",
                "cash": 635_751_000,
                "cashAndShortTermInvestments": 1_375_373_000,
                "shortLongTermDebtTotal": 3_691_000_000,
                "netDebt": 2_316_000_000,
                "totalAssets": 7_759_771_000,
                "totalStockholderEquity": 1_998_822_000,
                "totalEquity": 2_010_867_000,
            }
        ],
        "official_metrics": {
            "adjustedRecurringEbitda": 402_000_000,
            "adjustedRecurringEbitdaMargin": 0.27,
            "netDebtToEbitdaLtm": 2.50,
        },
    },
)


def ensure_builtin_official_fundamentals(database: Database) -> int:
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY,
        METHODOLOGY_VERSION,
        {
            "priority": "Official RI/CVM statements override stale provider periods",
            "scope": "Reported historical fundamentals only; consensus and estimates remain provider data",
        },
        "Audited overlay of official issuer filings over delayed third-party fundamentals.",
    )
    inserted = 0
    for payload in BUILTIN_OFFICIAL_FUNDAMENTALS:
        entity_key = _entity_key(str(payload["market"]), str(payload["symbol"]))
        existing = database.latest_analysis_snapshot(ANALYSIS_TYPE, entity_key)
        existing_output = existing.get("outputs") if existing else None
        if isinstance(existing_output, dict) and existing_output == payload:
            continue
        database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            entity_key,
            methodology_id,
            {
                "source_name": payload["source_name"],
                "source_url": payload["source_url"],
                "period": payload["as_of"],
            },
            copy.deepcopy(payload),
            datetime.now(timezone.utc),
        )
        inserted += 1
    return inserted


def save_official_fundamentals(database: Database, payloads: list[dict[str, Any]]) -> int:
    """Persist regulator/issuer fundamentals while retaining richer prior fields."""
    if not payloads:
        return 0
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY,
        METHODOLOGY_VERSION,
        {
            "priority": "Official RI/CVM statements override stale provider periods",
            "scope": "Reported historical fundamentals only; consensus and estimates remain provider data",
        },
        "Audited overlay of official issuer filings over delayed third-party fundamentals.",
    )
    written = 0
    for incoming in payloads:
        market = str(incoming.get("market") or "").upper()
        symbol = str(incoming.get("symbol") or "").upper()
        if not market or not symbol or not _valid_date(incoming.get("as_of")):
            continue
        entity_key = _entity_key(market, symbol)
        existing = database.latest_analysis_snapshot(ANALYSIS_TYPE, entity_key)
        prior = existing.get("outputs") if existing else None
        merged = _merge_official_payloads(prior, incoming)
        if isinstance(prior, dict) and prior == merged:
            continue
        database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            entity_key,
            methodology_id,
            {
                "source_name": merged.get("source_name"),
                "source_url": merged.get("source_url"),
                "period": merged.get("as_of"),
            },
            merged,
            datetime.now(timezone.utc),
        )
        written += 1
    return written


def apply_official_fundamentals_map(
    database: Database,
    fundamentals_by_symbol: dict[str, dict[str, Any]],
    *,
    market: str,
) -> dict[str, dict[str, Any]]:
    symbols = [symbol.upper() for symbol in fundamentals_by_symbol]
    snapshots = database.latest_analysis_snapshots(
        ANALYSIS_TYPE,
        [_entity_key(market, symbol) for symbol in symbols],
    )
    output: dict[str, dict[str, Any]] = {}
    for symbol, fundamentals in fundamentals_by_symbol.items():
        snapshot = snapshots.get(_entity_key(market, symbol.upper()))
        overlay = snapshot.get("outputs") if snapshot else None
        output[symbol] = apply_official_fundamentals(fundamentals, overlay)
    return output


def apply_official_fundamentals(
    fundamentals: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(overlay, dict) or not overlay.get("as_of"):
        return dict(fundamentals)
    base_period = _valid_date(fundamentals.get("financialsAsOf"))
    official_period = _valid_date(overlay.get("as_of"))
    if not official_period or (base_period and official_period < base_period):
        return dict(fundamentals)

    result = copy.deepcopy(fundamentals)
    for field in ("quarterlyIncome", "quarterlyCashFlow", "quarterlyBalance"):
        result[field] = _merge_rows(result.get(field), overlay.get(field))

    income = result.get("quarterlyIncome") or []
    cash_flow = result.get("quarterlyCashFlow") or []
    balance = result.get("quarterlyBalance") or []
    latest_balance = balance[0] if balance else {}
    revenue = _sum_rows(income, "totalRevenue", 4)
    net_income = _sum_rows(income, "netIncome", 4)
    ebitda = _sum_rows(income, "ebitda", 4)
    operating_income = _sum_rows(income, "operatingIncome", 4)
    operating_cash = _sum_rows(cash_flow, "totalCashFromOperatingActivities", 4)
    capex = _sum_rows(cash_flow, "capitalExpenditures", 4)
    free_cash_flow = _sum_rows(cash_flow, "freeCashFlow", 4)

    total_cash = _number(latest_balance.get("cashAndShortTermInvestments"))
    total_debt = _number(latest_balance.get("shortLongTermDebtTotal"))
    total_equity = _number(latest_balance.get("totalStockholderEquity")) or _number(latest_balance.get("totalEquity"))
    market_cap = _number(result.get("marketCap"))
    shares = _number(overlay.get("sharesOutstanding")) or _number(result.get("sharesOutstanding"))

    result.update({
        "financialsAsOf": official_period,
        "updated_at": max(filter(None, [_valid_date(result.get("updated_at")), official_period])),
        "officialFundamentals": {
            "asOf": official_period,
            "sourceName": overlay.get("source_name"),
            "sourceUrl": overlay.get("source_url"),
            "appliedAt": datetime.now(timezone.utc).isoformat(),
        },
    })
    _set_if_number(result, "totalRevenue", revenue)
    _set_if_number(result, "ebitda", ebitda)
    _set_if_number(result, "operatingCashflow", operating_cash)
    _set_if_number(result, "freeCashflow", free_cash_flow)
    _set_if_number(result, "totalCash", total_cash)
    _set_if_number(result, "totalDebt", total_debt)
    _set_if_number(result, "totalEquity", total_equity)
    _set_if_number(result, "sharesOutstanding", shares)

    if revenue and revenue > 0:
        _set_if_number(result, "profitMargins", net_income / revenue if net_income is not None else None)
        _set_if_number(result, "operatingMargins", operating_income / revenue if operating_income is not None else None)
        _set_if_number(result, "ebitdaMargins", ebitda / revenue if ebitda is not None else None)
    if total_equity and total_equity > 0:
        _set_if_number(result, "returnOnEquity", net_income / total_equity if net_income is not None else None)
        _set_if_number(result, "debtToEquity", total_debt / total_equity if total_debt is not None else None)
    if shares and shares > 0:
        _set_if_number(result, "trailingEps", net_income / shares if net_income is not None else None)
        _set_if_number(result, "bookValue", total_equity / shares if total_equity is not None else None)
    if market_cap and net_income and net_income > 0:
        _set_if_number(result, "trailingPE", market_cap / net_income)
    if market_cap and total_equity and total_equity > 0:
        _set_if_number(result, "priceToBook", market_cap / total_equity)
    if market_cap and ebitda and ebitda > 0:
        enterprise_value = market_cap + (total_debt or 0.0) - (total_cash or 0.0)
        _set_if_number(result, "enterpriseToEbitda", enterprise_value / ebitda)
    _set_if_number(result, "revenueGrowthAnnual", _yoy_growth(income, "totalRevenue"))
    _set_if_number(result, "earningsGrowthAnnual", _yoy_growth(income, "netIncome"))

    result["officialMetrics"] = copy.deepcopy(overlay.get("official_metrics") or {})
    result["officialMetrics"]["capexTtm"] = abs(capex) if capex is not None else None
    return result


def _entity_key(market: str, symbol: str) -> str:
    return f"{market.upper()}:{symbol.upper()}"


def _merge_rows(base: Any, official: Any) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in base if isinstance(base, list) else []:
        if isinstance(row, dict) and (period := _valid_date(row.get("date"))):
            merged[period] = copy.deepcopy(row)
    for row in official if isinstance(official, list) else []:
        if isinstance(row, dict) and (period := _valid_date(row.get("date"))):
            merged[period] = copy.deepcopy(row)
    return [merged[period] for period in sorted(merged, reverse=True)]


def _merge_official_payloads(base: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(base, dict):
        return copy.deepcopy(incoming)
    base_period = _valid_date(base.get("as_of"))
    incoming_period = _valid_date(incoming.get("as_of"))
    if base_period and incoming_period and incoming_period < base_period:
        return copy.deepcopy(base)
    merged = copy.deepcopy(base)
    merged.update({key: copy.deepcopy(value) for key, value in incoming.items() if value is not None})
    for field in ("quarterlyIncome", "quarterlyCashFlow", "quarterlyBalance"):
        merged[field] = _merge_rows(base.get(field), incoming.get(field))
    merged["official_metrics"] = {
        **copy.deepcopy(base.get("official_metrics") or {}),
        **copy.deepcopy(incoming.get("official_metrics") or {}),
    }
    return merged


def _sum_rows(rows: list[dict[str, Any]], field: str, limit: int) -> float | None:
    values = [_number(row.get(field)) for row in rows[:limit]]
    clean = [value for value in values if value is not None]
    return sum(clean) if clean else None


def _yoy_growth(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    latest_period = _valid_date(rows[0].get("date"))
    latest_value = _number(rows[0].get(field))
    if not latest_period or latest_value is None:
        return None
    latest_date = datetime.fromisoformat(latest_period).date()
    prior_period = latest_date.replace(year=latest_date.year - 1).isoformat()
    prior = next((row for row in rows if _valid_date(row.get("date")) == prior_period), None)
    prior_value = _number((prior or {}).get(field))
    if prior_value is None or prior_value == 0:
        return None
    return latest_value / prior_value - 1


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except ValueError:
        return None


def _set_if_number(payload: dict[str, Any], key: str, value: float | None) -> None:
    if value is not None and math.isfinite(value):
        payload[key] = value
