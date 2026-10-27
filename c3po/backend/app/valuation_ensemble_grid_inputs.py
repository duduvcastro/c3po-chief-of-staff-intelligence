"""Protocol-grade inputs, distinct from the independently authenticated-original path.

Only the rev3 pinned readers and canonical SEC facts accepted by T feed this module.
Catalogue classification and a retrospective price publication are protocol conventions,
not evidence of historical issuer/class/action/original-source admissibility.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

from . import sec_xbrl, valuation_pit_rerun as pit
from .statement_vintages import vintage_row_hash
from .valuation_ensemble_adapters import _ni_window
from .valuation_ensemble_inputs import CompanyInputs, Evidence, NotEvaluable, OfficialFact, Premises, Price, canonical_hash, number, utc
from .valuation_v2_engine import EQUITY_RISK_PREMIUM, MIN_HISTORY_YEARS, US_DISCOUNT_MAX, US_DISCOUNT_MIN, US_TERMINAL_GROWTH


POLICY = "ensemble-grid-explicit-cashflow-v1"
YEARS = 5
FLOWS = {name: sec_xbrl.CONCEPT_LADDER[name] for name in
         ("revenue", "net_income", "operating_income", "d_and_a", "operating_cash_flow", "capex")}
FLOWS.update({
    "dividends": ("us-gaap:PaymentsOfDividendsCommonStock",),
    "income_tax": ("us-gaap:IncomeTaxExpenseBenefit",),
    "pretax_income": ("us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "interest_expense": ("us-gaap:InterestExpense", "us-gaap:InterestAndDebtExpense"),
    "long_debt_proceeds": ("us-gaap:ProceedsFromIssuanceOfLongTermDebt",),
    "long_debt_repayments": ("us-gaap:RepaymentsOfLongTermDebt",),
    "short_debt_net_proceeds": ("us-gaap:ProceedsFromRepaymentsForShortTermDebt",),
})
INSTANTS = {
    "cash": sec_xbrl.CONCEPT_LADDER["cash"],
    "book_equity": ("us-gaap:StockholdersEquity",),
    "debt_current": ("us-gaap:DebtCurrent",),
    "debt_noncurrent": ("us-gaap:LongTermDebtNoncurrent",),
    "current_assets": ("us-gaap:AssetsCurrent",),
    "current_liabilities": ("us-gaap:LiabilitiesCurrent",),
    "total_liabilities": ("us-gaap:Liabilities",),
    "goodwill": ("us-gaap:Goodwill",),
    "intangible_assets_excluding_goodwill": ("us-gaap:IntangibleAssetsNetExcludingGoodwill",),
    "intangible_assets_including_goodwill": ("us-gaap:IntangibleAssetsNetIncludingGoodwill",),
}


def _date(value: Any) -> date:
    return value if type(value) is date else date.fromisoformat(str(value))


def _instant(value: Any) -> datetime:
    return utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _row_ref(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"issuer_key": str(row["issuer_key"]), "source": str(row["source"]), "doc_id": str(row["doc_id"]),
            "concept": str(row["concept"]), "unit": str(row["unit"]), "row_hash": str(row["row_hash"]),
            "period_start": _date(row["period_start"]).isoformat() if row.get("period_start") else None,
            "period_end": _date(row["period_end"]).isoformat(), "accepted_at": _instant(row["accepted_at"]).isoformat()}


def _fact(value: float, end: date, rows: Sequence[Mapping[str, Any]], rule: str, *, unit: str = "USD") -> tuple[OfficialFact, dict[str, Any]]:
    refs = sorted({_row_ref(r)["row_hash"]: _row_ref(r) for r in rows}.values(), key=lambda r: (r["accepted_at"], r["row_hash"]))
    derivation = {"rule": rule, "value": value, "period_end": end.isoformat(), "rows": refs}
    evidence = Evidence("SEC", "+".join(sorted({str(r["doc_id"]) for r in rows})),
                        max(_instant(r["accepted_at"]) for r in rows), canonical_hash(derivation))
    return OfficialFact(value, unit, end, evidence), derivation


@dataclass(frozen=True)
class GridCompanyInputs(CompanyInputs):
    """The narrowly declared rev3 price/catalogue conventions, never fake SEC evidence.

    Official facts keep CompanyInputs.get's real accepted-at cutoff. Only the price
    publication clock and current pinned catalogue classification follow the signed
    grid's retrospective conventions instead of the originals path's stronger gate.
    """
    protocol: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        utc(self.as_of)
        if self.market not in {"NASDAQ", "NYSE"} or self.currency != "USD" or not self.symbol or not self.issuer_id:
            raise NotEvaluable("invalid_grid_company_identity")
        self.price.evidence.check(self.price.evidence.available_at, {"PRICE"})
        if (self.price.currency != self.currency or self.price.basis_id != self.basis_id
                or self.protocol.get("basis_id") != self.basis_id):
            raise NotEvaluable("grid_price_basis_mismatch")
        if type(self.price.session_date) is not date or self.price.session_date > self.economic_date() or number(self.price.value, "price") <= 0:
            raise NotEvaluable("invalid_or_future_price")
        if self.price.session_date.isoformat() != self.protocol.get("session_date"):
            raise NotEvaluable("grid_price_not_close_of_D")

    def sector_at_T(self) -> str:
        if not self.sector or self.protocol.get("catalogue_classification") != "current_pinned_catalogue_rev3_convention":
            raise NotEvaluable("grid_catalogue_sector_missing")
        return self.sector


def reduce_company_facts(rows: Sequence[Mapping[str, Any]], *, issuer: str, as_of: datetime,
                         front: Any) -> tuple[dict[str, OfficialFact], dict[str, Any]]:
    """Reduce canonical facts with the rev3 ladder/quarter helpers; absent is never0.

    Added concepts are read only if already present in the SAME canonical fact set.
    Debt requires both disjoint reported totals; finite-lived intangibles alone
    never become all intangibles. Beginning equity requires a unique exact NI path.
    """
    cut = utc(as_of)
    economic = pit.economic_date_of("NASDAQ", cut)
    valid: list[Mapping[str, Any]] = []
    refused: Counter[str] = Counter()
    for row in rows:
        try:
            accepted = _instant(row["accepted_at"])
            if accepted > cut:
                refused["fact_after_T"] += 1
                continue
            if row.get("market") != "US" or row.get("issuer_key") != issuer or row.get("source") != sec_xbrl.VINTAGE_SOURCE:
                raise NotEvaluable("canonical_fact_identity_mismatch")
            if row.get("row_hash") != vintage_row_hash(row):
                raise NotEvaluable("canonical_fact_hash_mismatch")
            if _date(row["period_end"]) > economic or (row.get("period_start") and _date(row["period_start"]) > _date(row["period_end"])):
                raise NotEvaluable("fact_period_invalid_or_after_T")
            value = float(row["value"])
            if isinstance(row["value"], bool) or not math.isfinite(value):
                raise NotEvaluable("canonical_fact_nonfinite")
            valid.append(row)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            refused[str(error) if isinstance(error, NotEvaluable) else "malformed_canonical_fact"] += 1
    # A bad eligible row cannot silently expose an older value of its concept.
    # A future row was cut before this check and cannot invalidate today's input.
    if any(key != "fact_after_T" for key in refused):
        return {}, {"derivations": {}, "refused": dict(sorted(refused.items())), "income_window": None,
                    "accepted_rows": len(valid), "accepted_rows_sha256": canonical_hash(sorted([_row_ref(r) for r in valid], key=canonical_hash)),
                    "historical_original_class_scope_basis_admissibility": False}
    valid = sorted(valid, key=lambda row: str(row["row_hash"]))
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for row in valid:
        grouped.setdefault((str(row["concept"]), str(row.get("period_start")), str(row["period_end"])), []).append(row)
    for candidates in grouped.values():
        rank = max((_instant(r["accepted_at"]), str(r["doc_id"])) for r in candidates)
        current = [r for r in candidates if (_instant(r["accepted_at"]), str(r["doc_id"])) == rank]
        if len({str(r["row_hash"]) for r in current}) > 1:
            refused["ambiguous_latest_canonical_fact"] += 1
    if refused.get("ambiguous_latest_canonical_fact"):
        return {}, {"derivations": {}, "refused": dict(sorted(refused.items())), "income_window": None,
                    "accepted_rows": len(valid), "accepted_rows_sha256": canonical_hash(sorted([_row_ref(r) for r in valid], key=canonical_hash)),
                    "historical_original_class_scope_basis_admissibility": False}
    view = front._point_in_time(valid)
    facts: dict[str, OfficialFact] = {}
    derivations: dict[str, Any] = {}
    instant_rows: dict[str, dict[date, Mapping[str, Any]]] = {}
    annual_rows: dict[str, dict[date, Mapping[str, Any]]] = {}
    income_window: dict[str, Any] | None = None
    # The same concept priority and year/quarter helpers as rev3; no hidden current
    # fundamentals block, model TP or analyst EPS is consulted.
    for name, concepts in FLOWS.items():
        spans: dict[tuple[date, date], Mapping[str, Any]] = {}
        for concept in concepts:
            for (tag, start, end), row in view.items():
                if tag == concept and start is not None and row["unit"] == "USD":
                    spans.setdefault((start, end), row)
        quarters = sec_xbrl.discrete_quarters(spans)
        chain = sec_xbrl.trailing_quarters(quarters)
        years: dict[date, Mapping[str, Any]] = {}
        annual_spans: dict[date, list[tuple[date, Mapping[str, Any]]]] = {}
        for (start, end), row in spans.items():
            if sec_xbrl.duration_months(start, end) == 12:
                annual_spans.setdefault(end, []).append((start, row))
        for end, candidates in annual_spans.items():
            if len(candidates) == 1:
                years[end] = candidates[0][1]
            else:
                refused[f"ambiguous_annual_span:{name}"] += 1
        annual_rows[name] = years
        if len(chain) == 4:
            used = [row for key in chain for row in quarters[key]["facts"]]
            value = math.fsum(float(quarters[key]["value"]) for key in chain)
            end = chain[0][1]
            rule = "rev3_four_contiguous_quarters"
            if name == "net_income":
                income_window = _ni_window(spans, quarters, chain)
        elif years:
            end = max(years)
            used = [years[end]]
            value = float(used[0]["value"])
            rule = "rev3_latest_fiscal_year_fallback"
            if name == "net_income":
                # Exact annual boundaries do not imply a unique four-quarter path.
                income_window = {"status": "not_determinable", "reason": "ni_four_quarter_support_missing"}
        else:
            refused[f"no_complete_flow:{name}"] += 1
            continue
        if name in {"capex", "dividends", "long_debt_proceeds", "long_debt_repayments"}:
            value = abs(value)
            rule += ":absolute_cash_outflow_or_proceeds"
        facts[name + "_ttm"], derivations[name + "_ttm"] = _fact(value, end, used, rule)
    for name, concepts in INSTANTS.items():
        available: dict[date, Mapping[str, Any]] = {}
        for concept in concepts:
            for (tag, start, end), row in view.items():
                if tag == concept and start is None and row["unit"] == "USD":
                    available.setdefault(end, row)
        instant_rows[name] = available
        if available:
            end = max(available)
            facts[name], derivations[name] = _fact(float(available[end]["value"]), end, [available[end]], "latest_reported_instant")

    def combine(name: str, components: Sequence[tuple[str, float]], *, at: date | None = None) -> None:
        chosen = [facts.get(key) for key, _ in components]
        if any(x is None for x in chosen):
            refused[f"missing_components:{name}"] += 1
            return
        ends = {x.period_end for x in chosen if x is not None}
        if len(ends) != 1 or (at is not None and at not in ends):
            refused[f"component_period_mismatch:{name}"] += 1
            return
        value = math.fsum(facts[key].value * sign for key, sign in components)
        rows_used = [r for key, _ in components for r in derivations[key]["rows"]]
        # Resolve references back to the already-read canonical rows, no reread.
        raw_used = [r for r in valid if str(r["row_hash"]) in {str(x["row_hash"]) for x in rows_used}]
        facts[name], derivations[name] = _fact(value, next(iter(ends)), raw_used,
                                               "signed_components:" + repr(list(components)))

    combine("debt", [("debt_current", 1), ("debt_noncurrent", 1)])
    combine("net_borrowing_ttm", [("long_debt_proceeds_ttm", 1), ("long_debt_repayments_ttm", -1), ("short_debt_net_proceeds_ttm", 1)])
    if "intangible_assets_excluding_goodwill" not in facts:
        combine("intangible_assets_excluding_goodwill", [("intangible_assets_including_goodwill", 1), ("goodwill", -1)])
    opening_date: date | None = None
    if income_window and income_window.get("status") == "boundary_determinable":
        opening_date = _date(income_window["required_opening_date"])
        opening = instant_rows["book_equity"].get(opening_date)
        if opening is not None:
            facts["book_equity_beginning"], derivations["book_equity_beginning"] = _fact(
                float(opening["value"]), opening_date, [opening], "exact_day_before_unique_signed_NI_support:protocol_canonical_issuer_USD")
        else:
            refused["exact_beginning_book_missing"] += 1
    else:
        refused["beginning_book_boundary_not_unique_or_exact"] += 1
    if opening_date is not None and "net_income_ttm" in facts:
        end = facts["net_income_ttm"].period_end
        dates = (opening_date, end)
        names = ("current_assets", "cash", "current_liabilities", "debt_current")
        if all(day in instant_rows[name] for day in dates for name in names):
            nwc = [sum(float(instant_rows[name][day]["value"]) * sign for name, sign in
                       (("current_assets", 1), ("cash", -1), ("current_liabilities", -1), ("debt_current", 1))) for day in dates]
            used = [instant_rows[name][day] for day in dates for name in names]
            facts["change_working_capital_ttm"], derivations["change_working_capital_ttm"] = _fact(
                nwc[1] - nwc[0], end, used, "delta_non_cash_non_debt_working_capital_at_exact_NI_boundaries")
    normalization_dates = sorted(set(annual_rows["operating_income"]) & set(annual_rows["capex"]), reverse=True)[:MIN_HISTORY_YEARS]
    if len(normalization_dates) == MIN_HISTORY_YEARS:
        for target, source in (("normalized_operating_income", "operating_income"), ("maintenance_capex", "capex")):
            used = [annual_rows[source][day] for day in normalization_dates]
            values = [float(row["value"]) for row in used]
            value = statistics.median([abs(v) for v in values] if source == "capex" else values)
            facts[target], derivations[target] = _fact(value, max(normalization_dates), used,
                "design_proxy:median_five_common_reported_fiscal_years:" + source)
    revenue_growth = None
    revenue_years = sorted(annual_rows["revenue"], reverse=True)[:2]
    if len(revenue_years) == 2:
        newer, older = (annual_rows["revenue"][day] for day in revenue_years)
        if _date(newer["period_start"]) == _date(older["period_end"]) + timedelta(days=1) and float(older["value"]) > 0:
            revenue_growth = float(newer["value"]) / float(older["value"]) - 1
    return facts, {"derivations": derivations, "refused": dict(sorted(refused.items())), "income_window": income_window,
                   "revenue_growth": revenue_growth,
                   "accepted_rows": len(valid), "accepted_rows_sha256": canonical_hash(sorted([_row_ref(r) for r in valid], key=canonical_hash)),
                   "historical_original_class_scope_basis_admissibility": False}


def derive_premises(company: GridCompanyInputs, *, curve: Mapping[str, Any] | None, beta: float | None,
                    beta_audit: Mapping[str, Any], facts_audit: Mapping[str, Any]) -> tuple[Premises, dict[str, Any]]:
    """Explicit CAPM/discount policy plus reported-data proxies, all in the receipt."""
    scalars: dict[str, float] = {"terminal_growth": US_TERMINAL_GROWTH}
    refused: Counter[str] = Counter()
    rate = pit._number((curve or {}).get("interpolated_5y_rate"))
    if rate is not None and beta is not None and math.isfinite(beta):
        scalars["cost_of_equity"] = max(US_DISCOUNT_MIN, min(US_DISCOUNT_MAX, rate + beta * EQUITY_RISK_PREMIUM))
    else:
        refused["dated_curve_or_recomputed_beta_missing"] += 1
    tax: float | None = None
    try:
        pretax = company.get("pretax_income_ttm", positive=True)
        income_tax = company.get("income_tax_ttm")
        if company.facts["income_tax_ttm"].period_end != company.facts["pretax_income_ttm"].period_end:
            raise NotEvaluable("reported_tax_period_mismatch")
        tax = income_tax / pretax
        if not 0 <= tax <= 1:
            raise NotEvaluable("reported_tax_ratio_out_of_range")
        scalars["tax_rate"] = tax
    except NotEvaluable as exc:
        tax = None
        refused[str(exc)] += 1
    try:
        debt = company.get("debt", nonnegative=True)
        equity = company.price.value * company.get("shares", positive=True)
        ke = scalars.get("cost_of_equity")
        if ke is None:
            raise NotEvaluable("missing_cost_of_equity_for_wacc")
        if debt == 0:
            scalars["wacc"] = ke
        else:
            if tax is None:
                raise NotEvaluable("missing_valid_tax_for_wacc")
            cost_debt = company.get("interest_expense_ttm", nonnegative=True) / debt
            scalars["wacc"] = equity / (equity + debt) * ke + debt / (equity + debt) * cost_debt * (1 - tax)
    except NotEvaluable as exc:
        refused[str(exc)] += 1
    growth_path: tuple[float, ...] = ()
    # Compare two observed annual revenue periods rather than a current forecast.
    # A missing previous year leaves multistage models explicitly unevaluable.
    growth = facts_audit.get("revenue_growth")
    if isinstance(growth, (int, float)) and not isinstance(growth, bool) and math.isfinite(growth) and growth > -1:
        growth_path = tuple(float(growth) + (US_TERMINAL_GROWTH - float(growth)) * year / YEARS for year in range(YEARS))
    else:
        refused["prior_observed_revenue_growth_missing"] += 1
    premises = Premises(POLICY, scalars, growth_path, minimum_peers=3)
    return premises, {"receipt": premises.receipt(), "risk_free": rate, "beta": beta, "beta_audit": dict(beta_audit),
        "formula": {"cost_of_equity": "clamp(r5y(T)+OLS_beta(T)*0.055,0.06,0.16):frozen_V3_CAPM_policy",
                    "tax_rate": "reported_income_tax_ttm/reported_positive_pretax_income_ttm; no clamp/fill",
                    "wacc": "E/(E+D)*ke+D/(E+D)*(reported_interest_expense_ttm/reported_debt)*(1-tax); D=0 =>ke",
                    "terminal_growth": "0.03:frozen_V3_US_design_ceiling_not_market_observation",
                    "growth_path": "five annual observed-revenue-growth steps linearly fading to0.03; no forecast/consensus EPS",
                    "normalization": "median five common reported fiscal years; reported capex is a declared maintenance proxy"},
        "refused": dict(sorted(refused.items())), "macroeconomic_original_vintage": "N/D"}
