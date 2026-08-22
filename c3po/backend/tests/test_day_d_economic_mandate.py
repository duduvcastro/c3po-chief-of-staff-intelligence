from __future__ import annotations

import json
import math
from pathlib import Path


C3PO_ROOT = Path(__file__).resolve().parents[2]
MANDATE_PATH = C3PO_ROOT / "docs" / "day_d" / "economic_mandate.json"


def _mandate() -> dict:
    return json.loads(MANDATE_PATH.read_text(encoding="utf-8"))


def test_owner_economic_targets_are_internally_consistent() -> None:
    mandate = _mandate()

    capital = mandate["reference_capital_usd"]
    daily_target = mandate["target_geometric_net_return_fraction_per_session"]
    sessions = mandate["planning_translation"]["planning_sessions"]
    drawdown = mandate["maximum_drawdown_fraction"]

    expected_ending_nav = capital * (1 + daily_target) ** sessions
    assert mandate["trading_capital_mode"] == "virtual_only"
    assert mandate["real_trading_capital_during_horizon_usd"] == 0
    assert mandate["real_product_investment_enabled"] is True
    assert mandate["target_is_mandatory_each_session"] is False
    assert mandate["no_trade_session_return_fraction"] == 0
    assert (
        mandate["sessions_cannot_be_excluded_for_no_trade_or_negative_return"]
        is True
    )
    assert math.isclose(
        mandate["planning_translation"]["target_ending_virtual_nav_usd"],
        expected_ending_nav,
    )
    assert math.isclose(
        mandate["planning_translation"]["target_virtual_trading_profit_usd"],
        expected_ending_nav - capital,
    )
    assert mandate["maximum_drawdown_usd_at_reference_capital"] == capital * drawdown
    assert mandate["drawdown_measurement"]["calendar_reset"] is False


def test_year_one_planning_translation_includes_forward_costs() -> None:
    mandate = _mandate()
    budget = mandate["budget"]
    planning = mandate["planning_translation"]

    recurring = budget["maximum_recurring_usd_per_month"] * 12
    forward_cost = recurring + budget["baseline_new_capex_usd"]
    virtual_profit = planning["target_virtual_trading_profit_usd"]

    assert budget["maximum_recurring_usd_per_year"] == recurring
    assert planning["maximum_planned_year_one_forward_cost_usd"] == forward_cost
    assert math.isclose(
        planning["target_project_economic_surplus_after_forward_costs_usd"],
        virtual_profit - forward_cost,
    )
    assert math.isclose(
        planning["required_compounded_net_return_fraction_per_session"],
        mandate["target_geometric_net_return_fraction_per_session"],
    )
    assert math.isclose(
        planning["equivalent_simple_average_virtual_profit_usd_per_session"],
        virtual_profit / planning["planning_sessions"],
    )


def test_additional_capex_requires_an_incremental_case() -> None:
    budget = _mandate()["budget"]

    assert budget["existing_sunk_capex_is_incremental"] is False
    assert budget["existing_recurring_services_count_toward_monthly_cap"] is True
    assert budget["capex_above_baseline_allowed"] is True
    assert budget["capex_above_baseline_requires_owner_approval"] is True
    assert set(budget["capex_approval_memo_requires"]) == {
        "incremental_capability_or_risk_reduction",
        "measurable_expected_benefit",
        "cheaper_alternatives",
        "break_even_analysis",
        "failure_or_cancellation_gate",
    }


def test_closed_trade_quality_gate_is_net_and_cannot_replace_expectancy() -> None:
    gate = _mandate()["success_12_months"]["closed_trade_quality_gate"]

    assert gate["pnl_basis"] == (
        "realized_net_after_entry_and_exit_slippage_and_fees"
    )
    assert gate["positive_count_must_strictly_exceed_negative_count"] is True
    assert gate["minimum_exclusive_non_flat_win_rate_fraction"] == 0.5
    assert gate["flat_trades_excluded_from_win_rate_denominator"] is True
    assert gate["necessary_but_not_sufficient"] is True
    assert gate["positive_expectancy_and_payoff_still_required"] is True


def test_target_can_only_be_revised_prospectively() -> None:
    policy = _mandate()["target_revision_policy"]

    assert policy["revision_allowed"] is True
    assert policy["prospective_only"] is True
    assert policy["versioned_owner_approval_required"] is True
    assert policy["historical_results_keep_the_mandate_active_when_generated"] is True
    assert policy["retroactive_goalpost_change_forbidden"] is True


def test_r_normalized_threshold_remains_blocked_until_risk_is_frozen() -> None:
    planning = _mandate()["planning_translation"]

    assert planning["theta_econ_usd_per_session_status"] == (
        "nav_dependent_not_a_fixed_daily_dollar_quota"
    )
    assert planning["theta_econ_r_per_session"] is None
    assert planning["theta_econ_r_requires_fixed_dollar_risk_and_nav_path"] is True
