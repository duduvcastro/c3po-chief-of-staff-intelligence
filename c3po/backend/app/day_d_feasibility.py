from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Iterable


@dataclass(frozen=True)
class FeasibilityAssumptions:
    reference_capital_usd: float = 1_000_000.0
    maximum_drawdown_fraction: float = 0.08
    required_gross_usd_per_session: float = 4_027.777777777778
    session_sigma_r: float = 2.6
    family_alpha: float = 0.05
    multiplicity_cells: int = 6
    target_power: float = 0.80
    first_checkpoint_sessions: int = 60
    final_checkpoint_sessions: int = 120
    arm_count: int = 2
    maximum_positions: int = 5

    @property
    def per_decision_alpha(self) -> float:
        return self.family_alpha / self.multiplicity_cells


@dataclass(frozen=True)
class RiskScenario:
    fixed_risk_usd: float
    fixed_risk_fraction_of_capital: float
    full_book_initial_stop_risk_fraction: float
    theta_econ_r_per_session: float
    full_r_losses_to_maximum_drawdown: float
    sessions_for_80pct_power_at_theta: int
    per_arm_h0_kill_probability_c1: float
    per_arm_h0_kill_probability_c2: float
    independent_two_arm_h0_kill_probability_c2: float


def minimum_detectable_mean_r(
    sessions: int,
    assumptions: FeasibilityAssumptions,
) -> float:
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    if assumptions.session_sigma_r <= 0:
        raise ValueError("session_sigma_r must be positive")
    if not 0 < assumptions.per_decision_alpha < 0.5:
        raise ValueError("per-decision alpha must be between zero and 0.5")
    if not 0.5 < assumptions.target_power < 1:
        raise ValueError("target_power must be between 0.5 and 1")

    normal = NormalDist()
    critical = normal.inv_cdf(1 - assumptions.per_decision_alpha)
    power_quantile = normal.inv_cdf(assumptions.target_power)
    return (
        (critical + power_quantile)
        * assumptions.session_sigma_r
        / math.sqrt(sessions)
    )


def sessions_for_power(
    alternative_mean_r: float,
    assumptions: FeasibilityAssumptions,
) -> int:
    if alternative_mean_r <= 0:
        raise ValueError("alternative_mean_r must be positive")
    normal = NormalDist()
    critical = normal.inv_cdf(1 - assumptions.per_decision_alpha)
    power_quantile = normal.inv_cdf(assumptions.target_power)
    required = (
        (critical + power_quantile)
        * assumptions.session_sigma_r
        / alternative_mean_r
    ) ** 2
    return math.ceil(required)


def h0_kill_probability(
    theta_r: float,
    sessions: int,
    assumptions: FeasibilityAssumptions,
) -> float:
    """Approximate P(upper bound < theta) when the true mean is zero."""
    if theta_r <= 0:
        raise ValueError("theta_r must be positive")
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    normal = NormalDist()
    critical = normal.inv_cdf(1 - assumptions.per_decision_alpha)
    standardized = (
        theta_r * math.sqrt(sessions) / assumptions.session_sigma_r - critical
    )
    return normal.cdf(standardized)


def risk_scenario(
    fixed_risk_usd: float,
    assumptions: FeasibilityAssumptions,
) -> RiskScenario:
    if fixed_risk_usd <= 0:
        raise ValueError("fixed_risk_usd must be positive")
    theta_r = assumptions.required_gross_usd_per_session / fixed_risk_usd
    kill_c1 = h0_kill_probability(
        theta_r, assumptions.first_checkpoint_sessions, assumptions
    )
    kill_c2 = h0_kill_probability(
        theta_r, assumptions.final_checkpoint_sessions, assumptions
    )
    return RiskScenario(
        fixed_risk_usd=fixed_risk_usd,
        fixed_risk_fraction_of_capital=(
            fixed_risk_usd / assumptions.reference_capital_usd
        ),
        full_book_initial_stop_risk_fraction=(
            fixed_risk_usd
            * assumptions.maximum_positions
            / assumptions.reference_capital_usd
        ),
        theta_econ_r_per_session=theta_r,
        full_r_losses_to_maximum_drawdown=(
            assumptions.reference_capital_usd
            * assumptions.maximum_drawdown_fraction
            / fixed_risk_usd
        ),
        sessions_for_80pct_power_at_theta=sessions_for_power(theta_r, assumptions),
        per_arm_h0_kill_probability_c1=kill_c1,
        per_arm_h0_kill_probability_c2=kill_c2,
        independent_two_arm_h0_kill_probability_c2=kill_c2
        ** assumptions.arm_count,
    )


def feasibility_report(
    risk_budgets_usd: Iterable[float],
    assumptions: FeasibilityAssumptions | None = None,
) -> dict:
    active = assumptions or FeasibilityAssumptions()
    scenarios = [risk_scenario(value, active) for value in risk_budgets_usd]
    if not scenarios:
        raise ValueError("at least one risk budget is required")
    return {
        "status": "preliminary_not_for_production",
        "assumptions": asdict(active)
        | {"per_decision_alpha": active.per_decision_alpha},
        "minimum_detectable_mean_r": {
            "c1": minimum_detectable_mean_r(
                active.first_checkpoint_sessions, active
            ),
            "c2": minimum_detectable_mean_r(
                active.final_checkpoint_sessions, active
            ),
        },
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "limitations": [
            "Burned draft sigma is a placeholder until S3/S5 replay exists.",
            "Bonferroni alpha allocation is provisional, not the final joint calibration.",
            "Two-arm class-kill probability assumes independent arm statistics.",
            "Carry serial dependence is not modeled in this analytic screen.",
            "Statistical detectability does not establish economic attainability.",
        ],
    }


def main() -> None:
    report = feasibility_report([500, 1_000, 1_500, 2_000, 2_500, 3_000, 4_000, 5_000])
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
