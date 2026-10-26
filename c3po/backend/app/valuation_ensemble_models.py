"""Pure financial kernels for the new shadow ensemble, with explicit missingness.

These are construction formulas, not a signed study. Rates and growth are supplied design
premises, peer multiples use only the eligible cross-section at T. No current provider
fundamentals, analyst forecasts, network clients or served valuation functions are read.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Callable

from .valuation_ensemble_inputs import CompanyInputs, NotEvaluable, Premises, number, utc


MODEL_IDS = ("dcf_fcff", "dcf_fcfe", "ddm_gordon", "ddm_multistage", "residual_income", "earnings_power",
             "capitalized_operating_cash_flow", "pe", "ev_ebitda", "ev_ebit", "ev_sales", "price_book",
             "price_operating_cash_flow", "sector_regression", "ncav", "tangible_book")


@dataclass(frozen=True)
class ModelValue:
    model: str
    value: float | None
    status: str
    reason: str | None = None


def _tax(p: Premises) -> float:
    tax = p.get("tax_rate")
    if not 0 <= tax <= 1:
        raise NotEvaluable("tax_rate_out_of_range")
    return tax


def _net_debt(c: CompanyInputs) -> float:
    return c.get("debt", nonnegative=True) - c.get("cash", nonnegative=True)


def _enterprise_allowed(c: CompanyInputs) -> None:
    if c.financial_company:
        raise NotEvaluable("enterprise_model_not_applicable_to_financial_company")


def _discount(cash_flow: float, rate: float, p: Premises, *, multistage: bool) -> float:
    growth = p.get("terminal_growth")
    if growth <= -1 or rate <= growth or rate <= 0:
        raise NotEvaluable("discount_rate_not_above_terminal_growth")
    path = p.annual_growth_path if multistage else ()
    if multistage and not path:
        raise NotEvaluable("missing_explicit_growth_path")
    current = cash_flow
    present = 0.0
    for year, g in enumerate(path, 1):
        g = number(g, "growth")
        if g <= -1:
            raise NotEvaluable("growth_not_above_minus_one")
        current *= 1 + g
        present += current / (1 + rate) ** year
    terminal = current * (1 + growth) / (rate - growth)
    return present + terminal / (1 + rate) ** len(path)


def _fcff(c: CompanyInputs, p: Premises) -> float:
    _enterprise_allowed(c)
    # EBIT(1-t) + D&A - capex - change in non-cash working capital.
    cash = (c.get("operating_income_ttm") * (1 - _tax(p)) + c.get("d_and_a_ttm", nonnegative=True)
            - c.get("capex_ttm", nonnegative=True) - c.get("change_working_capital_ttm"))
    return (_discount(cash, p.get("wacc", positive=True), p, multistage=True) - _net_debt(c)) / c.get("shares", positive=True)


def _fcfe(c: CompanyInputs, p: Premises) -> float:
    # OCF is after interest/tax; debt cash flows are therefore added only as net borrowing.
    cash = c.get("operating_cash_flow_ttm") - c.get("capex_ttm", nonnegative=True) + c.get("net_borrowing_ttm")
    return _discount(cash, p.get("cost_of_equity", positive=True), p, multistage=True) / c.get("shares", positive=True)


def _ddm(c: CompanyInputs, p: Premises, *, multistage: bool) -> float:
    dividends = c.get("dividends_ttm", positive=True) / c.get("shares", positive=True)
    return _discount(dividends, p.get("cost_of_equity", positive=True), p, multistage=multistage)


def _residual_income(c: CompanyInputs, p: Premises) -> float:
    # Stable residual-income model. Beginning book and contemporaneous annual income
    # are explicit inputs; ending book is not substituted for the capital charge base.
    beginning = c.get("book_equity_beginning", positive=True)
    ke = p.get("cost_of_equity", positive=True)
    residual = c.get("net_income_ttm") - ke * beginning
    return (beginning + _discount(residual, ke, p, multistage=False)) / c.get("shares", positive=True)


def _earnings_power(c: CompanyInputs, p: Premises) -> float:
    _enterprise_allowed(c)
    # Normalization/maintenance choices must already be evidenced in the input adapter.
    sustainable = (c.get("normalized_operating_income") * (1 - _tax(p))
                   + c.get("d_and_a_ttm", nonnegative=True) - c.get("maintenance_capex", nonnegative=True))
    enterprise = sustainable / p.get("wacc", positive=True)
    return (enterprise - _net_debt(c)) / c.get("shares", positive=True)


def _capitalized_ocf(c: CompanyInputs, p: Premises) -> float:
    return c.get("operating_cash_flow_ttm", positive=True) / p.get("cost_of_equity", positive=True) / c.get("shares", positive=True)


def _metric(c: CompanyInputs, model: str) -> tuple[float, float]:
    """(market equity/enterprise value, the matching denominator), never mix bases."""
    equity = float(c.price.value) * c.get("shares", positive=True)
    if model == "pe":
        return equity, c.get("net_income_ttm", positive=True)
    if model == "price_book":
        return equity, c.get("book_equity", positive=True)
    if model == "price_operating_cash_flow":
        return equity, c.get("operating_cash_flow_ttm", positive=True)
    _enterprise_allowed(c)
    enterprise = equity + _net_debt(c)
    if enterprise <= 0:
        raise NotEvaluable("enterprise_value_not_positive")
    if model == "ev_sales" or model == "sector_regression":
        return enterprise, c.get("revenue_ttm", positive=True)
    income = c.get("operating_income_ttm", positive=True)
    if model == "ev_ebitda":
        income += c.get("d_and_a_ttm", nonnegative=True)
    return enterprise, income


def _peers(c: CompanyInputs, peers: tuple[CompanyInputs, ...], p: Premises) -> tuple[CompanyInputs, ...]:
    sector = c.sector_at_T()
    selected: dict[str, CompanyInputs] = {}
    for peer in peers:
        identity = peer.issuer_id
        if identity == c.issuer_id:
            continue
        try:
            peer.validate()
            if peer.currency != c.currency or utc(peer.as_of) != utc(c.as_of) or peer.sector_at_T() != sector:
                continue
            if peer.financial_company != c.financial_company:
                continue
            if identity in selected:
                raise NotEvaluable("duplicate_peer_identity")
            selected[identity] = peer
        except NotEvaluable as exc:
            if str(exc) == "duplicate_peer_identity":
                raise
            continue
    if len(selected) < p.minimum_peers:
        raise NotEvaluable("eligible_sector_peers_below_minimum")
    return tuple(selected[key] for key in sorted(selected))


def _multiple(c: CompanyInputs, p: Premises, peers: tuple[CompanyInputs, ...], model: str) -> float:
    _, denominator = _metric(c, model)
    ratios = []
    for peer in _peers(c, peers, p):
        try:
            value, metric = _metric(peer, model)
            ratios.append(value / metric)
        except NotEvaluable:
            continue
    if len(ratios) < p.minimum_peers:
        raise NotEvaluable("eligible_multiple_peers_below_minimum")
    fair = statistics.median(ratios) * denominator
    if model.startswith("ev_"):
        fair -= _net_debt(c)
    return fair / c.get("shares", positive=True)


def _sector_regression(c: CompanyInputs, p: Premises, peers: tuple[CompanyInputs, ...]) -> float:
    # OLS ln(EV/sales) on EBIT margin in the sector cross-section at T, leave-one-out.
    # Neither future prices nor analyst estimates are a regressor or training target.
    _, sales = _metric(c, "sector_regression")
    target_margin = c.get("operating_income_ttm") / sales
    pairs = []
    for peer in _peers(c, peers, p):
        try:
            ev, revenue = _metric(peer, "sector_regression")
            pairs.append((peer.get("operating_income_ttm") / revenue, math.log(ev / revenue)))
        except NotEvaluable:
            continue
    if len(pairs) < max(3, p.minimum_peers):
        raise NotEvaluable("eligible_regression_peers_below_minimum")
    xs, ys = zip(*pairs)
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    denominator = math.fsum((x - xbar) ** 2 for x in xs)
    if denominator <= 1e-20:
        raise NotEvaluable("sector_regression_singular")
    if not min(xs) <= target_margin <= max(xs):
        raise NotEvaluable("sector_regression_extrapolation")
    slope = math.fsum((x - xbar) * (y - ybar) for x, y in pairs) / denominator
    predicted_multiple = math.exp(ybar + slope * (target_margin - xbar))
    return (predicted_multiple * sales - _net_debt(c)) / c.get("shares", positive=True)


def _ncav(c: CompanyInputs, _: Premises) -> float:
    return (c.get("current_assets", nonnegative=True) - c.get("total_liabilities", nonnegative=True)) / c.get("shares", positive=True)


def _tangible_book(c: CompanyInputs, _: Premises) -> float:
    # intangible_assets_excluding_goodwill is deliberately distinct to avoid subtracting
    # goodwill twice when the filing's intangible total already contains it.
    return (c.get("book_equity") - c.get("goodwill", nonnegative=True)
            - c.get("intangible_assets_excluding_goodwill", nonnegative=True)) / c.get("shares", positive=True)


def evaluate_models(company: CompanyInputs, premises: Premises, *, peers: tuple[CompanyInputs, ...] = ()) -> tuple[ModelValue, ...]:
    company.validate()
    premises.receipt()
    kernels: dict[str, Callable[[], float]] = {
        "dcf_fcff": lambda: _fcff(company, premises), "dcf_fcfe": lambda: _fcfe(company, premises),
        "ddm_gordon": lambda: _ddm(company, premises, multistage=False),
        "ddm_multistage": lambda: _ddm(company, premises, multistage=True),
        "residual_income": lambda: _residual_income(company, premises),
        "earnings_power": lambda: _earnings_power(company, premises),
        "capitalized_operating_cash_flow": lambda: _capitalized_ocf(company, premises),
        "sector_regression": lambda: _sector_regression(company, premises, peers),
        "ncav": lambda: _ncav(company, premises), "tangible_book": lambda: _tangible_book(company, premises),
    }
    for model in ("pe", "ev_ebitda", "ev_ebit", "ev_sales", "price_book", "price_operating_cash_flow"):
        kernels[model] = lambda model=model: _multiple(company, premises, peers, model)
    results = []
    for model in MODEL_IDS:
        try:
            value = number(kernels[model](), model)
            if value <= 0:
                raise NotEvaluable("model_value_not_positive")
            results.append(ModelValue(model, value, "evaluated"))
        except (NotEvaluable, OverflowError) as exc:
            results.append(ModelValue(model, None, "not_evaluable", str(exc)))
    return tuple(results)
