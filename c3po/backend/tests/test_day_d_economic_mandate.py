from __future__ import annotations

import json
import math
from pathlib import Path

from app.day_d_feasibility import feasibility_report


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


def test_risk_is_fixed_as_a_fraction_of_current_virtual_nav() -> None:
    mandate = _mandate()
    risk = mandate["risk_policy"]

    assert risk["basis"] == "fraction_of_current_virtual_nav_at_trade_entry"
    assert risk["risk_fraction_per_trade"] == 0.0015
    assert risk["initial_risk_usd_at_reference_nav"] == 1_500
    assert risk["dollar_cap_during_paper_usd"] is None
    assert risk["risk_budget_frozen_for_trade_lifetime"] is True
    assert risk["maximum_simultaneous_positions"] == 5
    assert risk["maximum_aggregate_initial_stop_risk_fraction"] == 0.0075
    assert risk["recalibration_required_before_real_capital"] is True


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


def test_closed_trade_quality_gate_keeps_exact_and_robust_metrics_separate() -> None:
    gate = _mandate()["success_12_months"]["closed_trade_quality_gate"]

    assert gate["pnl_basis"] == (
        "realized_net_after_entry_and_exit_slippage_and_fees"
    )
    exact = gate["exact_ledger_metric"]
    robust = gate["robust_classification"]
    binding = gate["binding_test"]

    assert exact["epsilon_applied"] is False
    assert exact["positive_definition"] == "realized_net_pnl_usd > 0"
    assert exact["negative_definition"] == "realized_net_pnl_usd < 0"
    assert exact["flat_definition"] == "realized_net_pnl_usd = 0"
    assert robust["epsilon_trade_formula"] == (
        "max(exit_half_spread_usd_per_share * quantity, 0.01 * quantity)"
    )
    assert robust["round_trip_cost_reused_as_epsilon"] is False
    assert robust["ties_excluded_from_win_rate_denominator"] is True
    assert binding["minimum_exclusive_fraction"] == 0.5
    assert binding["binding_at"] == "final_12_month_verdict_only"
    assert binding["checkpoint_status"] == "diagnostic_only"
    assert gate["necessary_but_not_sufficient"] is True
    assert gate["positive_expectancy_still_required"] is True


def test_payoff_and_profit_factor_are_diagnostics_only() -> None:
    diagnostics = _mandate()["success_12_months"][
        "diagnostic_trade_metrics"
    ]

    assert diagnostics["payoff_ratio_desired_range"] == [1.3, 1.5]
    assert diagnostics["profit_factor_desired_minimum"] == 1.5
    assert diagnostics["binding_gate"] is False
    assert diagnostics[
        "confidence_intervals_reported_at_c1_c2_and_final"
    ] is True


def test_target_can_only_be_revised_prospectively() -> None:
    policy = _mandate()["target_revision_policy"]

    assert policy["revision_allowed"] is True
    assert policy["prospective_only"] is True
    assert policy["versioned_owner_approval_required"] is True
    assert policy["historical_results_keep_the_mandate_active_when_generated"] is True
    assert policy["retroactive_goalpost_change_forbidden"] is True


def test_product_target_and_kill_threshold_are_separate() -> None:
    mandate = _mandate()
    thresholds = mandate["thresholds"]
    planning = mandate["planning_translation"]

    meta = thresholds["theta_meta"]
    kill = thresholds["theta_kill"]
    assert meta["r_per_session"] == 0.005 / 0.0015
    assert meta["status"] == "product_target_only"
    assert meta["kill_authority"] is False
    assert kill["r_per_session"] == 0.15
    assert math.isclose(
        kill["operating_cost_component_r_per_session_at_initial_nav"],
        (15_000 / 252) / 1_500,
    )
    assert math.isclose(
        kill["opportunity_cost_component_budget_r_per_session"],
        0.15 - ((15_000 / 252) / 1_500),
    )
    assert kill["benchmark_rate_fraction_annual"] is None
    assert kill["benchmark_rate_status"] == (
        "freeze_snapshot_on_final_preregistration_hash_date"
    )
    assert planning["theta_meta_r_per_session"] == meta["r_per_session"]
    assert planning["theta_kill_r_per_session"] == kill["r_per_session"]


def test_machine_contract_and_calculator_cannot_drift() -> None:
    mandate = _mandate()
    report = feasibility_report()
    scenario = report["selected_scenario"]
    risk = mandate["risk_policy"]
    thresholds = mandate["thresholds"]

    assert scenario["risk_fraction_per_trade"] == risk["risk_fraction_per_trade"]
    assert scenario["initial_risk_usd_at_reference_nav"] == risk[
        "initial_risk_usd_at_reference_nav"
    ]
    assert scenario["maximum_aggregate_initial_stop_risk_fraction"] == risk[
        "maximum_aggregate_initial_stop_risk_fraction"
    ]
    assert scenario["theta_meta_r_per_session"] == thresholds["theta_meta"][
        "r_per_session"
    ]
    assert scenario["theta_kill_r_per_session"] == thresholds["theta_kill"][
        "r_per_session"
    ]
    assert math.isclose(
        scenario["theta_kill_operating_cost_component_r_per_session"],
        thresholds["theta_kill"][
            "operating_cost_component_r_per_session_at_initial_nav"
        ],
    )
    assert math.isclose(
        scenario["theta_kill_opportunity_cost_budget_r_per_session"],
        thresholds["theta_kill"][
            "opportunity_cost_component_budget_r_per_session"
        ],
    )
