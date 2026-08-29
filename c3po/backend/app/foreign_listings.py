from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PublicCoverageCall:
    firm: str
    target_local: float
    rating: str
    published_on: date


@dataclass(frozen=True)
class ForeignListingPolicy:
    symbol: str
    primary_ticker: str
    primary_currency: str
    fx_symbol: str
    yahoo_fx_symbol: str
    otc_to_primary_ratio: float
    reference_warning_percent: float
    issuer_ir_url: str
    consensus_local: float
    analyst_count: int
    consensus_as_of: date
    internal_method_targets_local: tuple[tuple[str, float], ...]
    internal_method_targets_registered_on: date
    buy_in_local: float
    coverage: tuple[PublicCoverageCall, ...]


# MHVYF is the 1:1 OTC ordinary share for 7011.T. EODHD labels the OTC quote in
# USD but returns most statement line items in JPY, so it must never enter the
# valuation engine without this currency bridge.
# This is an explicit allowlist. New OTC-to-primary relationships require a
# reviewed entry here; provider metadata must never auto-discover a mapping.
FOREIGN_LISTING_POLICIES = {
    "MHVYF": ForeignListingPolicy(
        symbol="MHVYF",
        primary_ticker="7011.T",
        primary_currency="JPY",
        fx_symbol="USDJPY.FOREX",
        yahoo_fx_symbol="JPY=X",
        otc_to_primary_ratio=1.0,
        reference_warning_percent=3.0,
        issuer_ir_url="https://www.mhi.com/finance/library/result",
        consensus_local=5_323.08,
        analyst_count=16,
        consensus_as_of=date(2026, 7, 28),
        internal_method_targets_local=(
            ("Múltiplos de Lucro + EV/EBITDA", 5_250.0),
            ("Fluxo de Caixa Descontado", 5_600.0),
            ("Blend Ajustado ao Risco", 4_750.0),
            ("Momentum de Lucro", 5_950.0),
            ("Qualidade & Fluxo de Caixa", 5_650.0),
        ),
        internal_method_targets_registered_on=date(2026, 8, 17),
        buy_in_local=3_110.0,
        coverage=(
            PublicCoverageCall("Goldman Sachs", 6_000.0, "Buy", date(2026, 6, 24)),
            PublicCoverageCall("Morgan Stanley", 5_700.0, "Buy", date(2026, 5, 29)),
            PublicCoverageCall("Nomura", 5_600.0, "Buy", date(2026, 3, 5)),
        ),
    ),
}


def policy_for(symbol: str) -> ForeignListingPolicy | None:
    return FOREIGN_LISTING_POLICIES.get(symbol.strip().upper())


def normalize_foreign_fundamentals(
    fundamentals: dict[str, Any],
    *,
    policy: ForeignListingPolicy,
    fx_rate: float,
    quote_price: float,
) -> dict[str, Any]:
    if not 0 < fx_rate < 1_000:
        raise ValueError(f"{policy.fx_symbol}: invalid FX rate {fx_rate!r}")

    output = deepcopy(fundamentals)
    output["primaryTicker"] = policy.primary_ticker
    output["financialCurrency"] = policy.primary_currency
    output["fxRate"] = fx_rate
    output["targetMeanPrice"] = policy.consensus_local / fx_rate
    output["numberOfAnalystOpinions"] = policy.analyst_count
    output["marketCap"] = _number(output.get("sharesOutstanding"), 0.0) * quote_price
    output["publicCoverage"] = [
        {
            "firm": call.firm,
            "target": call.target_local / fx_rate,
            "targetLocal": call.target_local,
            "rating": call.rating,
            "publishedOn": call.published_on.isoformat(),
        }
        for call in policy.coverage
    ]
    output["foreignListingPolicy"] = {
        "consensusAsOf": policy.consensus_as_of.isoformat(),
        "internalMethodTargets": {
            name: value / fx_rate for name, value in policy.internal_method_targets_local
        },
        "internalMethodTargetsRegisteredOn": policy.internal_method_targets_registered_on.isoformat(),
        "buyIn": policy.buy_in_local / fx_rate,
    }

    for key in (
        "ebitda",
        "totalRevenue",
        "freeCashflow",
        "operatingCashflow",
        "totalCash",
        "totalDebt",
        "totalEquity",
    ):
        output[key] = _converted(output.get(key), fx_rate)

    for section in ("quarterlyIncome", "annualIncome", "quarterlyCashFlow", "quarterlyBalance"):
        output[section] = [_convert_statement_row(row, fx_rate) for row in _rows(output.get(section))]

    trend_rows = []
    for row in _rows(output.get("earningsTrendQuarterly")):
        converted = dict(row)
        for key in (
            "revenueEstimateAvg",
            "revenueEstimateLow",
            "revenueEstimateHigh",
            "revenueEstimateYearAgoEps",
            "earningsEstimateAvg",
            "earningsEstimateLow",
            "earningsEstimateHigh",
            "earningsEstimateYearAgoEps",
            "epsTrendCurrent",
            "epsTrend7daysAgo",
            "epsTrend30daysAgo",
            "epsTrend60daysAgo",
            "epsTrend90daysAgo",
        ):
            converted[key] = _converted(converted.get(key), fx_rate)
        trend_rows.append(converted)
    output["earningsTrendQuarterly"] = trend_rows

    shares = _number(output.get("sharesOutstanding"))
    ttm_net_income = sum(
        value
        for row in _rows(output.get("quarterlyIncome"))[:4]
        if (value := _number(row.get("netIncome"))) is not None
    )
    if shares and ttm_net_income > 0:
        output["trailingEps"] = ttm_net_income / shares
    forward_pe = _number(output.get("forwardPE"))
    if forward_pe and forward_pe > 0:
        output["forwardEps"] = quote_price / forward_pe

    # The OTC earnings feed mixes USD actual EPS with JPY estimates. Financial
    # statements remain authoritative until a consistently denominated estimate
    # series is available.
    output["earningsHistory"] = []
    return output


def _convert_statement_row(row: dict[str, Any], fx_rate: float) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in row.items():
        folded = key.casefold()
        if key in {"date", "filing_date", "currency_symbol"} or "share" in folded:
            converted[key] = value
        else:
            converted[key] = _converted(value, fx_rate)
    converted["currency_symbol"] = "USD"
    return converted


def _converted(value: Any, fx_rate: float) -> Any:
    number = _number(value)
    return number / fx_rate if number is not None else value


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
