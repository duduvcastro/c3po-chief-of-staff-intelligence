from __future__ import annotations

import math

import pytest

from app.day_d_feasibility import (
    FeasibilityAssumptions,
    feasibility_report,
    minimum_detectable_mean_r,
    risk_scenario,
)


def test_preliminary_mde_reproduces_the_burned_draft_math() -> None:
    assumptions = FeasibilityAssumptions()

    assert assumptions.per_decision_alpha == pytest.approx(0.05 / 6)
    assert minimum_detectable_mean_r(60, assumptions) == pytest.approx(
        1.0860571728
    )
    assert minimum_detectable_mean_r(120, assumptions) == pytest.approx(
        0.7679583917
    )


def test_four_thousand_dollar_risk_scenario_is_internally_consistent() -> None:
    scenario = risk_scenario(4_000, FeasibilityAssumptions())

    assert scenario.fixed_risk_fraction_of_capital == pytest.approx(0.004)
    assert scenario.full_book_initial_stop_risk_fraction == pytest.approx(0.02)
    assert scenario.theta_econ_r_per_session == pytest.approx(1.0069444444)
    assert scenario.full_r_losses_to_maximum_drawdown == pytest.approx(20)
    assert scenario.sessions_for_80pct_power_at_theta == 70
    assert scenario.independent_two_arm_h0_kill_probability_c2 == pytest.approx(
        0.9365150889
    )


def test_more_risk_lowers_theta_but_consumes_drawdown_capacity() -> None:
    assumptions = FeasibilityAssumptions()
    lower = risk_scenario(1_000, assumptions)
    higher = risk_scenario(5_000, assumptions)

    assert higher.theta_econ_r_per_session < lower.theta_econ_r_per_session
    assert (
        higher.full_r_losses_to_maximum_drawdown
        < lower.full_r_losses_to_maximum_drawdown
    )
    assert (
        higher.full_book_initial_stop_risk_fraction
        > lower.full_book_initial_stop_risk_fraction
    )
    assert (
        higher.sessions_for_80pct_power_at_theta
        > lower.sessions_for_80pct_power_at_theta
    )


def test_report_is_explicitly_preliminary_and_has_no_selected_scenario() -> None:
    report = feasibility_report([1_000, 2_000, 4_000])

    assert report["status"] == "preliminary_not_for_production"
    assert [item["fixed_risk_usd"] for item in report["scenarios"]] == [
        1_000,
        2_000,
        4_000,
    ]
    assert "selected_scenario" not in report
    assert len(report["limitations"]) == 5


@pytest.mark.parametrize("invalid", [0, -1, -100])
def test_non_positive_risk_is_rejected(invalid: float) -> None:
    with pytest.raises(ValueError):
        risk_scenario(invalid, FeasibilityAssumptions())


def test_power_calculation_is_finite() -> None:
    report = feasibility_report([500])

    assert math.isfinite(report["minimum_detectable_mean_r"]["c1"])
    assert math.isfinite(report["minimum_detectable_mean_r"]["c2"])
