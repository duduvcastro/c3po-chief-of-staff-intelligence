from __future__ import annotations

import math

import pytest

from app.day_d_feasibility import (
    FeasibilityAssumptions,
    classify_trade_outcome,
    feasibility_report,
    frozen_risk_scenario,
    minimum_detectable_mean_r,
)


def test_frozen_nav_fraction_risk_is_internally_consistent() -> None:
    assumptions = FeasibilityAssumptions()
    scenario = frozen_risk_scenario(assumptions)

    assert scenario.risk_fraction_per_trade == pytest.approx(0.0015)
    assert scenario.initial_risk_usd_at_reference_nav == pytest.approx(1_500)
    assert scenario.maximum_positions == 5
    assert scenario.maximum_aggregate_initial_stop_risk_fraction == pytest.approx(
        0.0075
    )
    assert (
        scenario.maximum_aggregate_initial_stop_risk_usd_at_reference_nav
        == pytest.approx(7_500)
    )
    assert scenario.full_r_losses_to_maximum_drawdown == pytest.approx(
        53.3333333333
    )
    assert scenario.full_book_stop_sessions_to_maximum_drawdown == pytest.approx(
        10.6666666667
    )


def test_nav_fraction_risk_keeps_product_target_stationary_in_r() -> None:
    assumptions = FeasibilityAssumptions()
    scenario = frozen_risk_scenario(assumptions)

    assert scenario.theta_meta_r_per_session == pytest.approx(0.005 / 0.0015)
    assert scenario.theta_meta_r_per_session == pytest.approx(
        assumptions.target_geometric_net_return_fraction_per_session
        / assumptions.risk_fraction_per_trade
    )
    assert scenario.target_log_return_per_session == pytest.approx(
        math.log1p(0.005)
    )


def test_theta_kill_decomposition_matches_frozen_contract() -> None:
    scenario = frozen_risk_scenario()

    assert scenario.theta_kill_r_per_session == pytest.approx(0.15)
    assert (
        scenario.theta_kill_operating_cost_component_r_per_session
        == pytest.approx((15_000 / 252) / 1_500)
    )
    assert (
        scenario.theta_kill_opportunity_cost_budget_r_per_session
        == pytest.approx(0.15 - ((15_000 / 252) / 1_500))
    )
    assert (
        scenario.theta_kill_implied_annual_opportunity_rate_fraction
        == pytest.approx(0.0417)
    )


def test_joint_h0_kill_is_only_an_illustration_until_stage_two() -> None:
    report = feasibility_report()
    scenario = report["selected_scenario"]
    acceptance = report["joint_h0_kill_acceptance"]

    assert scenario["per_arm_futility_h0_kill_probability_c2"] == pytest.approx(
        0.1555620707
    )
    assert scenario[
        "illustrative_joint_h0_class_kill_probability_c2"
    ] == pytest.approx(0.9173388956)
    assert acceptance == {
        "binding_target_fraction": 0.8,
        "rule": "futility_and_damage_and_placebo",
        "placebo_pass_requires": {
            "p_value_lte": 0.05,
            "delta_r_gte": 0.10,
        },
        "analytic_independence_result_is_binding": False,
        "stage2_path_simulation_required": True,
    }


def test_provisional_futility_mde_is_reproducible() -> None:
    assumptions = FeasibilityAssumptions()

    assert minimum_detectable_mean_r(60, assumptions) == pytest.approx(
        0.8346065629
    )
    assert minimum_detectable_mean_r(120, assumptions) == pytest.approx(
        0.5901559602
    )


@pytest.mark.parametrize(
    ("pnl", "half_spread", "quantity", "epsilon", "exact", "robust"),
    [
        (10.01, 0.02, 100, 2.0, "win", "win"),
        (-10.01, 0.02, 100, 2.0, "loss", "loss"),
        (0.50, 0.002, 100, 1.0, "win", "tie"),
        (-0.50, 0.002, 100, 1.0, "loss", "tie"),
        (0.0, 0.02, 100, 2.0, "flat", "tie"),
        (2.0, 0.02, 100, 2.0, "win", "tie"),
        (-2.0, 0.02, 100, 2.0, "loss", "tie"),
    ],
)
def test_trade_outcome_keeps_exact_ledger_and_robust_classification_separate(
    pnl: float,
    half_spread: float,
    quantity: float,
    epsilon: float,
    exact: str,
    robust: str,
) -> None:
    outcome = classify_trade_outcome(pnl, half_spread, quantity)

    assert outcome.epsilon_trade_usd == pytest.approx(epsilon)
    assert outcome.exact_ledger_outcome == exact
    assert outcome.robust_outcome == robust


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reference_capital_usd", 0),
        ("target_geometric_net_return_fraction_per_session", 0),
        ("risk_fraction_per_trade", 0),
        ("planning_sessions", 0),
        ("maximum_planned_forward_product_cost_usd", -1),
        ("theta_kill_r_per_session", 0),
        ("provisional_futility_alpha", 1),
        ("placebo_alpha", 0),
        ("maximum_positions", 0),
    ],
)
def test_invalid_contract_assumptions_are_rejected(
    field: str, value: float
) -> None:
    with pytest.raises(ValueError):
        FeasibilityAssumptions(**{field: value})


@pytest.mark.parametrize(
    ("half_spread", "quantity", "tick_floor"),
    [(-0.01, 10, 0.01), (0.01, 0, 0.01), (0.01, 10, 0)],
)
def test_invalid_robust_trade_inputs_are_rejected(
    half_spread: float,
    quantity: float,
    tick_floor: float,
) -> None:
    with pytest.raises(ValueError):
        classify_trade_outcome(1, half_spread, quantity, tick_floor)


def test_report_is_paper_only_and_has_one_frozen_scenario() -> None:
    report = feasibility_report()

    assert report["status"] == "contract_frozen_paper_only"
    assert report["selected_scenario"]["risk_fraction_per_trade"] == 0.0015
    assert report["selected_scenario"]["theta_meta_r_per_session"] == pytest.approx(
        3.3333333333
    )
    assert len(report["limitations"]) == 7
    assert math.isfinite(
        report["minimum_detectable_mean_r_futility_only"]["c1"]
    )
