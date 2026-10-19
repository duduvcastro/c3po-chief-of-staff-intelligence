"""Complete official statements (CVM ITR/DFP) and their field-by-field overlay over provider fundamentals.

The legacy overlay (``official_fundamentals.apply_official_fundamentals``) replaces a provider quarter row with the
official row wholesale and sums whatever rows carry a field. A CVM ITR row carries no EBITDA, so two official quarters
plus two provider quarters gave half a TTM EBITDA and twice the EV/EBITDA. Here an official row overrides only the
fields it carries, and every trailing-twelve-month figure needs four consecutive quarters that ALL carry the field;
otherwise the provider's own figure stays — except EODHD's top-level operating and free cash flow, which are ONE quarter
(``PROVIDER_QUARTERLY_TOP_LEVEL``): those are replaced by the provider's own complete TTM when the cash-flow guard admits
it (not year-to-date looking; at a fiscal-year end within 5 % of the provider's annual figure), else left out.
``official_fundamentals.py`` is pinned byte for byte by the R2D2 V2 risk differential
(``r2d2_v2_risk_differential.ORIGIN_PINS``) and keeps its behaviour for every caller that imports it.

Receipt guard (``official_overlays``; a guard, not a point-in-time read): the latest snapshot is refused when it was stored
after the build instant or when any contributing document becomes available after it (end of the CVM receipt day in Sao
Paulo). ``fieldwise_sources`` says, per served
field, whether it came from the CVM, the provider or both; the nightly shadow (``valuation_cvm_overlay_shadow``,
``C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_SHADOW``) aggregates it.

Switches. ``config.py`` is hashed into the R2D2 V2 implementation package (``r2d2_v2_earnings_package.PACKAGE_FILES``),
so these are read from the environment here, as the R2D2 V2 producers read theirs, rather than added to ``Settings``:
- ``C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED`` (default off): the B3 screener serves the field-by-field overlay.
- ``C3PO_CVM_STATEMENTS_CAPTURE_ENABLED`` (default on): the IR worker collects the complete statements -- stored under
  their own analysis type, read only by the overlay above -- and captures as-filed vintages. Nothing it writes is served
  while the overlay switch is off.
- ``C3PO_CVM_STATEMENTS_INTERVAL_HOURS`` (default 24, 6 to 336): spacing of the collection runs.
"""
from __future__ import annotations

import copy
import math
import os
from datetime import datetime, time, timezone
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from .database import Database
from .official_fundamentals import (
    ANALYSIS_TYPE as LEGACY_ANALYSIS_TYPE,
    _entity_key,
    _number,
    _set_if_number,
    _valid_date,
    _yoy_growth,
)


ANALYSIS_TYPE = "official_statements"
METHODOLOGY_KEY = "official_statements_fieldwise"
METHODOLOGY_VERSION = 1
FIELDWISE_OVERLAY_ENV = "C3PO_VALUATION_CVM_FIELDWISE_OVERLAY_ENABLED"
STATEMENTS_CAPTURE_ENV = "C3PO_CVM_STATEMENTS_CAPTURE_ENABLED"
STATEMENTS_INTERVAL_ENV = "C3PO_CVM_STATEMENTS_INTERVAL_HOURS"
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
STATEMENT_FIELDS = ("quarterlyIncome", "quarterlyCashFlow", "quarterlyBalance")
HISTORY_QUARTERS = 8  # kept per statement across runs: two years covers every TTM and year-over-year read
AS_OF_DOCUMENT_FIELDS = ("published_at", "source_url")  # describe the as_of document only: never inherited from another
DOCUMENT_IDENTITY = ("document", "referenceDate", "version")
METHODOLOGY_PARAMETERS = {
    "scope": "CVM ITR and DFP: DRE, DVA, DFC, BPA/BPP and capital composition; individual statements only for an issuer with no consolidated statement",
    "accounts": "Matched by code and description; a missing or ambiguous account leaves the field out",
    "quarters": "Calendar-year cumulative rows are differenced; Q4 = DFP year minus ITR nine months; a standalone three-month row only fills a gap",
    "ebitda": "EBIT (DRE result before financial result and taxes) plus DVA depreciation, amortization and depletion",
    "as_filed": "Per period the issuer's own filing wins over a later comparative, then the highest version",
    "overlay": "Field by field over provider rows; TTM only from four consecutive quarters that all carry the field",
}


def fieldwise_overlay_enabled() -> bool:
    return os.environ.get(FIELDWISE_OVERLAY_ENV, "").strip().lower() == "true"


def statements_capture_enabled() -> bool:
    return os.environ.get(STATEMENTS_CAPTURE_ENV, "true").strip().lower() != "false"


def statements_interval_hours() -> float:
    try:
        hours = float(os.environ.get(STATEMENTS_INTERVAL_ENV, "24"))
    except ValueError:
        return 24.0
    return min(max(hours, 6.0), 336.0) if math.isfinite(hours) else 24.0


def save_official_statements(database: Database, payloads: list[dict[str, Any]]) -> int:
    """Append one snapshot per symbol whose statements changed. Periods the new run did not see (a package that
    answered 404 this time) are kept from the previous snapshot; a run never moves ``as_of`` backwards."""
    if not payloads:
        return 0
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY,
        METHODOLOGY_VERSION,
        METHODOLOGY_PARAMETERS,
        "Complete CVM statements, overlaid field by field on delayed third-party fundamentals.",
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
        merged = _merge_statement_payloads(prior, incoming)
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


def apply_official_statements_map(
    database: Database,
    fundamentals_by_symbol: dict[str, dict[str, Any]],
    *,
    market: str,
    as_of: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Field-by-field counterpart of ``official_fundamentals.apply_official_fundamentals_map``: the complete
    statements whenever the symbol has them, else the legacy overlay itself — the overlays the receipt guard of
    ``official_overlays`` admits at ``as_of`` (default: now)."""
    overlays = official_overlays(database, list(fundamentals_by_symbol), market=market, as_of=as_of)
    return {
        symbol: apply_official_statements(fundamentals, overlays[symbol].overlay)
        for symbol, fundamentals in fundamentals_by_symbol.items()
    }


class OfficialOverlay(NamedTuple):
    """The one overlay a symbol gets (``select_official_overlay``), where it came from (``statements``, ``legacy`` or
    ``None``) and whether the latest complete statements were refused by the receipt guard."""

    overlay: dict[str, Any] | None
    origin: str | None
    receipt_guard_excluded: bool


RECEIPT_GUARD_LOOKBACK = 3  # refused latest statements: at most this many earlier snapshots are tried before the legacy


def official_overlays(
    database: Database,
    symbols: list[str],
    *,
    market: str,
    as_of: datetime | None = None,
) -> dict[str, OfficialOverlay]:
    """The overlay of each symbol behind a RECEIPT GUARD — not a point-in-time read: the LATEST snapshot is read, never
    the one that was current at a past instant, and it is refused when it was stored after ``as_of`` or when ANY document
    it was built from becomes available after ``as_of``: every contributing ITR/DFP version of every period (DRE, DVA,
    DFC, balance sheet, and the earlier cumulative a quarter was differenced against; ``periodDocuments[*].contributing``).
    Available = the END of its CVM receipt day (``DT_RECEB``) in Sao Paulo — the producer's own convention
    (``published_at``, the vintages' ``accepted_at``). A refused latest statements snapshot gives way to the newest
    earlier one the guard admits (up to ``RECEIPT_GUARD_LOOKBACK``), so a symbol does not swing to the legacy rows for
    the rest of a receipt day; else to the legacy snapshot, refused the same way on its ``published_at``; else to the
    provider. A document whose receipt is unknown is not refused (nothing proves it later). A live build reads
    snapshots written before it, so the guard only holds back what was received the same day, until that day ends."""
    instant = _aware(as_of) or datetime.now(timezone.utc)
    keys = {symbol: _entity_key(market, symbol.upper()) for symbol in symbols}
    statements = database.latest_analysis_snapshots(ANALYSIS_TYPE, list(keys.values()))
    legacy = database.latest_analysis_snapshots(LEGACY_ANALYSIS_TYPE, list(keys.values()))
    output: dict[str, OfficialOverlay] = {}
    for symbol, key in keys.items():
        snapshot = statements.get(key) or {}
        statements_outputs = snapshot.get("outputs") if isinstance(snapshot.get("outputs"), dict) else None
        excluded = statements_outputs is not None and not _statements_received_by(snapshot, instant)
        if excluded:
            statements_outputs = _earlier_admitted_statements(database, key, snapshot, instant)
        legacy_snapshot = legacy.get(key) or {}
        legacy_outputs = legacy_snapshot.get("outputs") if isinstance(legacy_snapshot.get("outputs"), dict) else None
        if legacy_outputs is not None and not _legacy_received_by(legacy_snapshot, instant):
            legacy_outputs = None
        overlay = select_official_overlay(statements_outputs, legacy_outputs)
        origin = None
        if overlay is not None:
            origin = "statements" if statements_outputs is not None and _valid_date(statements_outputs.get("as_of")) else "legacy"
        output[symbol] = OfficialOverlay(overlay, origin, excluded)
    return output


def _earlier_admitted_statements(database: Database, key: str, refused: dict[str, Any], instant: datetime) -> dict[str, Any] | None:
    before = _aware(refused.get("published_at"))
    for _ in range(RECEIPT_GUARD_LOOKBACK):
        if before is None:
            return None
        earlier = database.latest_analysis_snapshot_before(ANALYSIS_TYPE, key, before)
        if not earlier:
            return None
        if isinstance(earlier.get("outputs"), dict) and _statements_received_by(earlier, instant):
            return earlier["outputs"]
        before = _aware(earlier.get("published_at"))
    return None


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def available_at(received_on: Any) -> datetime | None:
    """A CVM receipt DATE as an instant: the end of that day in Sao Paulo (``cvm_fundamentals``' ``published_at``)."""
    day = _valid_date(received_on)
    return datetime.combine(datetime.fromisoformat(day).date(), time.max, tzinfo=SAO_PAULO) if day else None


def _stored_by(snapshot: dict[str, Any], instant: datetime) -> bool:
    """The snapshot was stored by ``instant`` (a snapshot without a readable instant is trusted: the store always has one)."""
    stored = _aware(snapshot.get("published_at"))
    return stored is None or stored <= instant


def _statements_received_by(snapshot: dict[str, Any], instant: datetime) -> bool:
    if not _stored_by(snapshot, instant):
        return False
    outputs = snapshot.get("outputs")
    if not isinstance(outputs, dict):
        return True
    published = _aware(outputs.get("published_at"))
    if published is not None and published > instant:
        return False
    metrics = outputs.get("official_metrics")
    documents = metrics.get("periodDocuments") if isinstance(metrics, dict) else None
    for document in documents.values() if isinstance(documents, dict) else []:
        if not isinstance(document, dict):
            continue
        contributing = document.get("contributing")
        for item in [document, *(contributing if isinstance(contributing, list) else [])]:
            available = available_at(item.get("receivedOn")) if isinstance(item, dict) else None
            if available is not None and available > instant:
                return False
    return True


def _legacy_received_by(snapshot: dict[str, Any], instant: datetime) -> bool:
    """Stored by ``instant`` and its ``published_at`` (an instant, or a receipt date read as the end of that day in Sao
    Paulo) not after it."""
    if not _stored_by(snapshot, instant):
        return False
    outputs = snapshot.get("outputs")
    raw = outputs.get("published_at") if isinstance(outputs, dict) else None
    published = available_at(raw) if isinstance(raw, str) and len(raw.strip()) == 10 else _aware(raw)
    return published is None or published <= instant


def select_official_overlay(statements: Any, legacy: Any) -> dict[str, Any] | None:
    """One overlay, never a blend of rows: the legacy CVM rows map bank and insurer accounts by code alone (3.05
    pre-tax as EBIT, 2.02.01 deposits as debt) and keep equity with minorities, so mixing them under the complete
    statements would leak those values back. A symbol with complete statements is served from them even while the
    legacy sync, which polls the same ITR every half hour, is a quarter ahead of the daily statements run: otherwise a
    bank's EV, ROE and P/B would swing to the legacy values after every ITR until that run caught up. Statements older
    than the provider's own quarter leave the provider in place (``apply_official_statements``), so the lag costs
    freshness, never correctness. Legacy official metrics (an issuer release's adjusted EBITDA, say) are kept under
    the statements' own."""
    statements_period = _valid_date(statements.get("as_of")) if isinstance(statements, dict) else None
    legacy_period = _valid_date(legacy.get("as_of")) if isinstance(legacy, dict) else None
    if statements_period and isinstance(statements, dict):
        selected = copy.deepcopy(statements)
        if isinstance(legacy, dict):
            selected["official_metrics"] = {
                **copy.deepcopy(legacy.get("official_metrics") or {}),
                **copy.deepcopy(statements.get("official_metrics") or {}),
            }
        return selected
    return copy.deepcopy(legacy) if legacy_period and isinstance(legacy, dict) else None


def _applied_period(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> str | None:
    """The overlay's period when it applies at all: a dated overlay not older than the provider's own quarter."""
    if not isinstance(overlay, dict) or not overlay.get("as_of"):
        return None
    base_period = _valid_date(fundamentals.get("financialsAsOf"))
    official_period = _valid_date(overlay.get("as_of"))
    if not official_period or (base_period and official_period < base_period):
        return None
    return official_period


def overlay_applies(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> bool:
    """False for no overlay and for one older than the provider's own quarter (then the provider stays in place)."""
    return _applied_period(fundamentals, overlay) is not None


# Provider top-level figures that are ONE QUARTER, not a trailing year (``eodhd._normalize_fundamentals`` reads them from the
# latest quarterly cash-flow statement). Wherever the field-wise overlay hands them on — with or without official rows —
# they are replaced by a trailing-twelve-month figure the guard admits (``provider_cash_flow_ttm``), or left out: never a
# quarter read as a year once the screener takes the overlay's figures.
PROVIDER_QUARTERLY_TOP_LEVEL: dict[str, str] = {"operatingCashflow": "totalCashFromOperatingActivities", "freeCashflow": "freeCashFlow"}
CASH_FLOW_GUARD_STATUSES = ("cumulative", "annual_missing", "annual_mismatch")
ANNUAL_AGREEMENT = 0.05  # a provider TTM ending at the fiscal-year end must be within 5 % of the provider's own annual figure
FISCAL_YEAR_END_MONTH = 12  # calendar fiscal years, as the CVM reader assumes (fiscal years not starting in January are skipped)
SHARES_SCALE_LIMIT = 100.0  # CVM shares that differ from the provider's by 100x or more: a thousands/units mix-up, skipped


def looks_cumulative(window: list[dict[str, Any]], column: str) -> bool:
    """Four quarters that look like year-to-date figures rather than single quarters: the size rises at every step inside
    a fiscal year and drops back at the first quarter of the next (Q1, H1, 9M, FY summed would be served as a year)."""
    points = sorted(((str(_valid_date(row.get("date"))), _number(row.get(column))) for row in window), key=lambda point: point[0])
    rises: list[bool] = []
    resets: list[bool] = []
    for (start, first), (end, second) in zip(points, points[1:]):
        if first is None or second is None:
            return False
        if start[:4] == end[:4]:
            rises.append(abs(second) > abs(first))
        else:
            resets.append(abs(second) < abs(first))
    return bool(rises) and all(rises) and all(resets)


def provider_annual_cash_flow(fundamentals: dict[str, Any], column: str, year: str) -> float | None:
    """The provider's own annual figure for ``year``: a normalized ``annualCashFlow`` row, or EODHD's raw
    ``Financials.Cash_Flow.yearly``. The normalized payload served today carries neither (``eodhd.py``, frozen this week)."""
    rows: list[Any] = list(fundamentals.get("annualCashFlow") or []) if isinstance(fundamentals.get("annualCashFlow"), list) else []
    financials = fundamentals.get("Financials")
    cash_flow = financials.get("Cash_Flow") if isinstance(financials, dict) else None
    yearly = cash_flow.get("yearly") if isinstance(cash_flow, dict) else None
    if isinstance(yearly, dict):
        rows.extend({"date": key, **value} for key, value in yearly.items() if isinstance(value, dict))
    for row in rows:
        period = _valid_date(row.get("date")) if isinstance(row, dict) else None
        if period and period[:4] == year and int(period[5:7]) == FISCAL_YEAR_END_MONTH:
            return _number(row.get(column))
    return None


def provider_cash_flow_ttm(fundamentals: dict[str, Any], column: str) -> tuple[float | None, str]:
    """The provider's own trailing-twelve-month cash-flow figure and why: ``complete`` (served), ``incomplete`` (no four
    consecutive quarters), ``cumulative`` (the window looks year-to-date), ``annual_missing`` / ``annual_mismatch`` (the
    window ends at the fiscal-year end and the provider's annual figure is absent / more than 5 % away). Only ``complete``
    returns a number."""
    rows = merge_rows_fieldwise(fundamentals.get("quarterlyCashFlow"), None)
    value = complete_ttm(rows, column)
    if value is None:  # no TTM of its own; still judged, since its quarters may complete a window with official ones
        return None, "cumulative" if len(rows) >= 3 and looks_cumulative(rows[:4], column) else "incomplete"
    if looks_cumulative(rows[:4], column):
        return None, "cumulative"
    newest = str(_valid_date(rows[0].get("date")))
    if int(newest[5:7]) == FISCAL_YEAR_END_MONTH:
        annual = provider_annual_cash_flow(fundamentals, column, newest[:4])
        if annual is None:
            return None, "annual_missing"
        if abs(value - annual) > ANNUAL_AGREEMENT * abs(annual):
            return None, "annual_mismatch"
    return value, "complete"


def resolve_cash_flow(fundamentals: dict[str, Any], overlay: dict[str, Any] | None, key: str) -> tuple[float | None, str, str | None]:
    """The operating/free cash flow ``apply_official_statements`` serves for ``key``: (value, source, guard status that
    dropped it). A complete window of official quarters serves (``cvm``); a window that needs provider quarters serves
    (``mixed``/``eodhd``) only if the provider's series passes the guard; else the provider's own guarded TTM
    (``eodhd``); else nothing (``absent``, with the guard status when the guard is why)."""
    column = PROVIDER_QUARTERLY_TOP_LEVEL[key]
    provider_value, provider_status = provider_cash_flow_ttm(fundamentals, column)
    untrusted = provider_status in CASH_FLOW_GUARD_STATUSES
    if overlay is not None and overlay_applies(fundamentals, overlay):
        official_rows = overlay.get("quarterlyCashFlow")
        merged = merge_rows_fieldwise(fundamentals.get("quarterlyCashFlow"), official_rows)
        value = complete_ttm(merged, column)
        if value is not None:
            official = {period: row for row in (official_rows if isinstance(official_rows, list) else [])
                        if isinstance(row, dict) and (period := _valid_date(row.get("date")))}
            carried = sum(1 for row in merged[:4] if official.get(_valid_date(row.get("date")) or "", {}).get(column) is not None)
            if carried == 4:
                return value, SOURCE_OFFICIAL, None
            if not untrusted:
                return value, SOURCE_MIXED if carried else SOURCE_PROVIDER, None
            return None, SOURCE_ABSENT, provider_status
    if provider_value is not None:
        return provider_value, SOURCE_PROVIDER, None
    return None, SOURCE_ABSENT, provider_status if untrusted else None


def _provider_cash_flow_in_place(result: dict[str, Any], fundamentals: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        value, _ = provider_cash_flow_ttm(fundamentals, PROVIDER_QUARTERLY_TOP_LEVEL[key])
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value


def _official_shares(fundamentals: dict[str, Any], overlay: dict[str, Any]) -> float | None:
    official = _number(overlay.get("sharesOutstanding"))
    provider = _number(fundamentals.get("sharesOutstanding"))
    if official and provider and not 1 / SHARES_SCALE_LIMIT < official / provider < SHARES_SCALE_LIMIT:
        return None
    return official or None


def shares_scale_skipped(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> bool:
    """The overlay applies and its share count was skipped as a scale mix-up (``SHARES_SCALE_LIMIT``)."""
    if overlay is None or not overlay_applies(fundamentals, overlay):
        return False
    return bool(_number(overlay.get("sharesOutstanding")) and _number(fundamentals.get("sharesOutstanding"))) and _official_shares(fundamentals, overlay) is None


def fix_provider_quarter_cash_flow(served: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    """``served`` with only the cash-flow fix of this module: where the provider's top-level quarter is still in place
    (the served value IS the provider's), the guarded provider TTM or nothing. No official row is read — the shadow's
    middle variant, so the fix is never attributed to the CVM rows."""
    result = dict(served)
    keys = tuple(key for key in PROVIDER_QUARTERLY_TOP_LEVEL
                 if _number(served.get(key)) is not None and served.get(key) == provider.get(key))
    _provider_cash_flow_in_place(result, provider, keys)
    return result


def apply_official_statements(
    fundamentals: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    official_period = _applied_period(fundamentals, overlay)
    if official_period is None or overlay is None:
        result = dict(fundamentals)  # the provider stays — but never its cash-flow QUARTER as a year
        _provider_cash_flow_in_place(result, fundamentals, tuple(PROVIDER_QUARTERLY_TOP_LEVEL))
        return result

    result = copy.deepcopy(fundamentals)
    for field in STATEMENT_FIELDS:
        result[field] = merge_rows_fieldwise(result.get(field), overlay.get(field))

    income = result.get("quarterlyIncome") or []
    cash_flow = result.get("quarterlyCashFlow") or []
    balance = result.get("quarterlyBalance") or []
    latest_balance = balance[0] if balance else {}
    revenue = complete_ttm(income, "totalRevenue")
    net_income = complete_ttm(income, "netIncome")
    ebitda = complete_ttm(income, "ebitda")
    operating_income = complete_ttm(income, "operatingIncome")
    capex = complete_ttm(cash_flow, "capitalExpenditures", magnitude=True)

    total_cash = _number(latest_balance.get("cashAndShortTermInvestments"))
    total_debt = _number(latest_balance.get("shortLongTermDebtTotal"))
    total_equity = _number(latest_balance.get("totalStockholderEquity")) or _number(latest_balance.get("totalEquity"))
    market_cap = _number(result.get("marketCap"))
    shares = _official_shares(fundamentals, overlay) or _number(result.get("sharesOutstanding"))

    result.update({
        "financialsAsOf": official_period,
        "updated_at": max(filter(None, [_valid_date(result.get("updated_at")), official_period])),
        "officialFundamentals": {
            "asOf": official_period,
            "sourceName": overlay.get("source_name"),
            "sourceUrl": overlay.get("source_url"),
            "overlay": "fieldwise",
            "ttmQuarters": ttm_window(income),
            "appliedAt": datetime.now(timezone.utc).isoformat(),
        },
    })
    _set_if_number(result, "totalRevenue", revenue)
    _set_if_number(result, "ebitda", ebitda)
    for key in PROVIDER_QUARTERLY_TOP_LEVEL:  # never the provider's quarter as a year, never a year-to-date sum
        value, _, _ = resolve_cash_flow(fundamentals, overlay, key)
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
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
    result["officialMetrics"]["capexTtm"] = capex
    return result


def merge_rows_fieldwise(base: Any, official: Any) -> list[dict[str, Any]]:
    """Rows by period, newest first. An official row overrides the fields it carries and leaves the provider's other
    fields of the same period in place."""
    merged: dict[str, dict[str, Any]] = {}
    for rows in (base, official):
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and (period := _valid_date(row.get("date"))):
                current = merged.setdefault(period, {})
                current.update({key: copy.deepcopy(value) for key, value in row.items() if value is not None})
    return [merged[period] for period in sorted(merged, reverse=True)]


def ttm_window(rows: list[dict[str, Any]]) -> list[str] | None:
    """The four newest rows' dates when they are four consecutive quarters, else None."""
    window = rows[:4]
    if len(window) < 4:
        return None
    dates = [_valid_date(row.get("date")) for row in window]
    months = [int(value[:4]) * 12 + int(value[5:7]) for value in dates if value]
    if len(months) < 4 or any(months[index] - months[index + 1] != 3 for index in range(3)):
        return None
    return [value for value in dates if value]


def complete_ttm(rows: list[dict[str, Any]], field: str, *, magnitude: bool = False) -> float | None:
    """Sum of ``field`` over the four newest rows, only when they are four consecutive quarters that all carry it.
    ``magnitude`` sums sizes (capex is negative in CVM and in issuer releases, positive in some provider rows)."""
    if ttm_window(rows) is None:
        return None
    values = [_number(row.get(field)) for row in rows[:4]]
    clean = [value for value in values if value is not None]
    if len(clean) < 4:
        return None
    return sum(abs(value) for value in clean) if magnitude else sum(clean)


SOURCE_OFFICIAL = "cvm"
SOURCE_PROVIDER = "eodhd"
SOURCE_MIXED = "mixed"
SOURCE_ABSENT = "absent"
SOURCES = (SOURCE_OFFICIAL, SOURCE_PROVIDER, SOURCE_MIXED, SOURCE_ABSENT)
# Every field ``apply_official_statements`` can set (or that its ratios are derived from): (statement, column, magnitude)
# for the trailing-twelve-month figures, the balance-sheet column(s) for the point figures.
TTM_SOURCE_FIELDS: dict[str, tuple[str, str, bool]] = {
    "totalRevenue": ("quarterlyIncome", "totalRevenue", False),
    "netIncome": ("quarterlyIncome", "netIncome", False),
    "ebitda": ("quarterlyIncome", "ebitda", False),
    "operatingCashflow": ("quarterlyCashFlow", "totalCashFromOperatingActivities", False),
    "freeCashflow": ("quarterlyCashFlow", "freeCashFlow", False),
    "capexTtm": ("quarterlyCashFlow", "capitalExpenditures", True),
}
BALANCE_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "totalCash": ("cashAndShortTermInvestments",),
    "totalDebt": ("shortLongTermDebtTotal",),
    "totalEquity": ("totalStockholderEquity", "totalEquity"),  # the order apply_official_statements reads them in
}
SOURCE_FIELDS: tuple[str, ...] = (*TTM_SOURCE_FIELDS, *BALANCE_SOURCE_FIELDS, "sharesOutstanding")


def cash_flow_guard(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, str | None]:
    """Per provider-quarter cash-flow field: the guard status (``CASH_FLOW_GUARD_STATUSES``) when the guard is why the
    field is left out, else ``None``."""
    return {key: resolve_cash_flow(fundamentals, overlay, key)[2] for key in PROVIDER_QUARTERLY_TOP_LEVEL}


def fieldwise_sources(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, str]:
    """Where each field ``apply_official_statements(fundamentals, overlay)`` serves comes from: ``cvm`` (every quarter of
    the TTM window, or the balance/share figure, from the official rows), ``mixed`` (a complete window of official and
    provider quarters), ``eodhd`` (the provider's: a window without the official field, or no complete window — then the
    provider's own figure stays; for operating/free cash flow only a TTM the guard admits) or ``absent`` (nothing is
    served). Mirrors that function's reads exactly; it serves nothing."""

    def provided(field: str) -> bool:
        if field == "netIncome":  # not a top-level provider field: the ratios built on it stay the provider's
            return any(isinstance(row, dict) and _number(row.get("netIncome")) is not None for row in fundamentals.get("quarterlyIncome") or [])
        return _number(fundamentals.get(field)) is not None

    def fallback(field: str) -> str:
        if field == "capexTtm":  # only an applied overlay sets it, and only from a complete window
            return SOURCE_ABSENT
        return SOURCE_PROVIDER if provided(field) else SOURCE_ABSENT

    cash_flow = {key: resolve_cash_flow(fundamentals, overlay, key)[1] for key in PROVIDER_QUARTERLY_TOP_LEVEL}
    if overlay is None or not overlay_applies(fundamentals, overlay):
        return {field: cash_flow.get(field) or fallback(field) for field in SOURCE_FIELDS}
    official: dict[str, dict[str, dict[str, Any]]] = {}
    merged: dict[str, list[dict[str, Any]]] = {}
    for statement in STATEMENT_FIELDS:
        rows = overlay.get(statement)
        official[statement] = {
            period: row for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict) and (period := _valid_date(row.get("date")))
        }
        merged[statement] = merge_rows_fieldwise(fundamentals.get(statement), overlay.get(statement))

    output: dict[str, str] = {}
    for field, (statement, column, magnitude) in TTM_SOURCE_FIELDS.items():
        if field in cash_flow:
            output[field] = cash_flow[field]
            continue
        rows = merged[statement]
        if complete_ttm(rows, column, magnitude=magnitude) is None:
            output[field] = fallback(field)
            continue
        carried = sum(1 for row in rows[:4] if official[statement].get(_valid_date(row.get("date")) or "", {}).get(column) is not None)
        output[field] = SOURCE_OFFICIAL if carried == 4 else SOURCE_PROVIDER if carried == 0 else SOURCE_MIXED

    balance = merged["quarterlyBalance"]
    latest = balance[0] if balance else {}
    latest_official = official["quarterlyBalance"].get(_valid_date(latest.get("date")) or "", {})
    for field, columns in BALANCE_SOURCE_FIELDS.items():
        # ``a or b`` as apply_official_statements reads it: the first column with a non-zero number wins, else the last
        chosen = next((column for column in columns if _number(latest.get(column))), columns[-1])
        if _number(latest.get(chosen)) is None:
            output[field] = fallback(field)
        else:
            output[field] = SOURCE_OFFICIAL if latest_official.get(chosen) is not None else SOURCE_PROVIDER
    output["sharesOutstanding"] = SOURCE_OFFICIAL if _official_shares(fundamentals, overlay) else fallback("sharesOutstanding")
    return output


def _merge_statement_payloads(base: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(base, dict):
        base = {}  # the first snapshot goes through the same normalization, so a rerun compares equal
    base_period = _valid_date(base.get("as_of"))
    incoming_period = _valid_date(incoming.get("as_of"))
    if base_period and incoming_period and incoming_period < base_period:
        return copy.deepcopy(base)
    merged = copy.deepcopy(base)
    merged.update({key: copy.deepcopy(value) for key, value in incoming.items() if value is not None})
    if not _same_as_of_document(base, incoming):
        for key in AS_OF_DOCUMENT_FIELDS:  # an unknown receipt of a new document stays unknown, never the prior one's
            merged[key] = copy.deepcopy(incoming.get(key))
    for field in STATEMENT_FIELDS:
        rows: dict[str, dict[str, Any]] = {}
        for source in (base.get(field), incoming.get(field)):  # same source: a period is replaced whole, never blended
            for row in source if isinstance(source, list) else []:
                if isinstance(row, dict) and (period := _valid_date(row.get("date"))):
                    rows[period] = copy.deepcopy(row)
        merged[field] = [rows[period] for period in sorted(rows, reverse=True)][:HISTORY_QUARTERS]
    base_metrics = base.get("official_metrics") or {}
    incoming_metrics = incoming.get("official_metrics") or {}
    merged["official_metrics"] = {**copy.deepcopy(base_metrics), **copy.deepcopy(incoming_metrics)}
    documents = copy.deepcopy(base_metrics.get("periodDocuments") or {})
    for period, document in (incoming_metrics.get("periodDocuments") or {}).items():
        document = copy.deepcopy(document)
        prior = documents.get(period)
        if prior is not None and _same_document(prior, document) and document.get("receivedOn") is None:
            document["receivedOn"] = prior.get("receivedOn")  # the same version: a receipt seen before is still true
        documents[period] = document
    kept = {row["date"] for field in STATEMENT_FIELDS for row in merged[field]}
    merged["official_metrics"]["periodDocuments"] = {period: documents[period] for period in sorted(documents) if period in kept}
    return merged


def _same_as_of_document(base: dict[str, Any], incoming: dict[str, Any]) -> bool:
    """Both payloads describe the same version of the same ``as_of`` document."""
    period = _valid_date(incoming.get("as_of"))
    if not period or _valid_date(base.get("as_of")) != period:
        return False
    return _same_document(
        ((base.get("official_metrics") or {}).get("periodDocuments") or {}).get(period),
        ((incoming.get("official_metrics") or {}).get("periodDocuments") or {}).get(period),
    )


def _same_document(first: Any, second: Any) -> bool:
    if not isinstance(first, dict) or not isinstance(second, dict):
        return False
    return all(first.get(key) is not None and first.get(key) == second.get(key) for key in DOCUMENT_IDENTITY)
