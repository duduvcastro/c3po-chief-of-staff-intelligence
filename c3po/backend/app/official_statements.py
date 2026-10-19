"""Complete official statements (CVM ITR/DFP) and their field-by-field overlay over provider fundamentals.

The legacy overlay (``official_fundamentals.apply_official_fundamentals``) replaces a provider quarter row with the
official row wholesale and sums whatever rows carry a field. A CVM ITR row carries no EBITDA, so two official quarters
plus two provider quarters gave half a TTM EBITDA and twice the EV/EBITDA. Here an official row overrides only the
fields it carries, and every trailing-twelve-month figure needs four consecutive quarters that ALL carry the field;
otherwise the provider's own figure stays — except EODHD's top-level operating and free cash flow, which are ONE quarter
(``PROVIDER_QUARTERLY_TOP_LEVEL``): those fall back to the provider's own complete TTM, else are left out.
``official_fundamentals.py`` is pinned byte for byte by the R2D2 V2 risk differential
(``r2d2_v2_risk_differential.ORIGIN_PINS``) and keeps its behaviour for every caller that imports it.

Point in time (``official_overlays``): a snapshot is read only if it was stored by the build instant and every document
behind it was received (CVM ``DT_RECEB``) by that instant's date in Sao Paulo. ``fieldwise_sources`` says, per served
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
from datetime import datetime, timezone
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
    statements whenever the symbol has them, else the legacy overlay itself — only what was received by ``as_of``
    (default: now; ``official_overlays``)."""
    overlays = official_overlays(database, list(fundamentals_by_symbol), market=market, as_of=as_of)
    return {
        symbol: apply_official_statements(fundamentals, overlays[symbol].overlay)
        for symbol, fundamentals in fundamentals_by_symbol.items()
    }


class OfficialOverlay(NamedTuple):
    """The one overlay a symbol gets (``select_official_overlay``), where it came from (``statements``, ``legacy`` or
    ``None``) and whether complete statements were set aside because a document in them post-dates ``as_of``."""

    overlay: dict[str, Any] | None
    origin: str | None
    pit_excluded: bool


def official_overlays(
    database: Database,
    symbols: list[str],
    *,
    market: str,
    as_of: datetime | None = None,
) -> dict[str, OfficialOverlay]:
    """The overlay of each symbol as of ``as_of`` (point in time). A snapshot is a candidate only if it was stored by
    ``as_of`` and every document behind it was received (CVM ``DT_RECEB``, a date) by ``as_of``'s date in Sao Paulo:
    a live build reads snapshots the IR worker wrote before it, so this never drops anything there; it makes the rule
    explicit and refuses a future-dated filing, or a snapshot written after the cut, instead of serving it."""
    instant = _aware(as_of) or datetime.now(timezone.utc)
    keys = {symbol: _entity_key(market, symbol.upper()) for symbol in symbols}
    statements = database.latest_analysis_snapshots(ANALYSIS_TYPE, list(keys.values()))
    legacy = database.latest_analysis_snapshots(LEGACY_ANALYSIS_TYPE, list(keys.values()))
    output: dict[str, OfficialOverlay] = {}
    for symbol, key in keys.items():
        statements_snapshot = statements.get(key) or {}
        legacy_snapshot = legacy.get(key) or {}
        statements_outputs = statements_snapshot.get("outputs") if isinstance(statements_snapshot.get("outputs"), dict) else None
        pit_excluded = statements_outputs is not None and not _received_by(statements_snapshot, instant)
        legacy_outputs = legacy_snapshot.get("outputs") if _stored_by(legacy_snapshot, instant) else None
        overlay = select_official_overlay(None if pit_excluded else statements_outputs, legacy_outputs)
        origin = None
        if overlay is not None:
            origin = "statements" if statements_outputs is not None and not pit_excluded and _valid_date(statements_outputs.get("as_of")) else "legacy"
        output[symbol] = OfficialOverlay(overlay, origin, pit_excluded)
    return output


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _stored_by(snapshot: dict[str, Any], instant: datetime) -> bool:
    """The snapshot was stored by ``instant`` (a snapshot without a readable instant is trusted: the store always has one)."""
    stored = _aware(snapshot.get("published_at"))
    return stored is None or stored <= instant


def _received_by(snapshot: dict[str, Any], instant: datetime) -> bool:
    """Stored by ``instant`` and every period document received by ``instant``'s calendar date in Sao Paulo (CVM files a
    receipt DATE; a document received that day is one the IR worker could only have collected on or after it)."""
    if not _stored_by(snapshot, instant):
        return False
    outputs = snapshot.get("outputs")
    metrics = outputs.get("official_metrics") if isinstance(outputs, dict) else None
    cut = instant.astimezone(SAO_PAULO).date().isoformat()
    documents = metrics.get("periodDocuments") if isinstance(metrics, dict) else None
    for document in documents.values() if isinstance(documents, dict) else []:
        received = _valid_date((document or {}).get("receivedOn")) if isinstance(document, dict) else None
        if received is not None and received > cut:
            return False
    return True


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


def apply_official_statements(
    fundamentals: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    official_period = _applied_period(fundamentals, overlay)
    if official_period is None or overlay is None:
        return dict(fundamentals)

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
    operating_cash = complete_ttm(cash_flow, "totalCashFromOperatingActivities")
    capex = complete_ttm(cash_flow, "capitalExpenditures", magnitude=True)
    free_cash_flow = complete_ttm(cash_flow, "freeCashFlow")

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
            "overlay": "fieldwise",
            "ttmQuarters": ttm_window(income),
            "appliedAt": datetime.now(timezone.utc).isoformat(),
        },
    })
    _set_if_number(result, "totalRevenue", revenue)
    _set_if_number(result, "ebitda", ebitda)
    provider_cash_flow = merge_rows_fieldwise(fundamentals.get("quarterlyCashFlow"), None)
    for key, value in (("operatingCashflow", operating_cash), ("freeCashflow", free_cash_flow)):
        if value is None:  # EODHD's top-level cash flow is its latest QUARTER (eodhd._latest_statement): never served as a year
            value = complete_ttm(provider_cash_flow, PROVIDER_QUARTERLY_TOP_LEVEL[key])  # the provider's own TTM, when complete
            if value is None:
                result.pop(key, None)
        _set_if_number(result, key, value)
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
# Provider top-level figures that are ONE QUARTER, not a trailing year (``eodhd._normalize_fundamentals`` reads them from the
# latest quarterly cash-flow statement): without a complete window they fall back to the provider's own complete TTM, else
# they are left out — never a quarter read as a year once the screener takes the overlay's figures.
PROVIDER_QUARTERLY_TOP_LEVEL: dict[str, str] = {"operatingCashflow": "totalCashFromOperatingActivities", "freeCashflow": "freeCashFlow"}


def fieldwise_sources(fundamentals: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, str]:
    """Where each field ``apply_official_statements(fundamentals, overlay)`` serves comes from: ``cvm`` (every quarter of
    the TTM window, or the balance/share figure, from the official rows), ``mixed`` (a complete window of official and
    provider quarters), ``eodhd`` (the provider's: a window without the official field, or no complete window — then the
    provider's own figure stays) or ``absent`` (neither has it). Mirrors that function's reads exactly; it serves nothing."""

    def provided(field: str) -> bool:
        if field == "netIncome":  # not a top-level provider field: the ratios built on it stay the provider's
            return any(isinstance(row, dict) and _number(row.get("netIncome")) is not None for row in fundamentals.get("quarterlyIncome") or [])
        if field == "capexTtm":
            return any(isinstance(row, dict) and _number(row.get("capitalExpenditures")) is not None for row in fundamentals.get("quarterlyCashFlow") or [])
        return _number(fundamentals.get(field)) is not None

    def fallback(field: str) -> str:
        return SOURCE_PROVIDER if provided(field) else SOURCE_ABSENT

    if _applied_period(fundamentals, overlay) is None or overlay is None:
        return {field: fallback(field) for field in SOURCE_FIELDS}
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
        rows = merged[statement]
        if complete_ttm(rows, column, magnitude=magnitude) is None:
            if field in PROVIDER_QUARTERLY_TOP_LEVEL:
                provider_rows = merge_rows_fieldwise(fundamentals.get(statement), None)
                output[field] = SOURCE_PROVIDER if complete_ttm(provider_rows, column) is not None else SOURCE_ABSENT
            else:
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
    if _number(overlay.get("sharesOutstanding")):
        output["sharesOutstanding"] = SOURCE_OFFICIAL
    else:
        output["sharesOutstanding"] = fallback("sharesOutstanding")
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
