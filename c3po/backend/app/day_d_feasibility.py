from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class FeasibilityAssumptions:
    reference_capital_usd: float = 1_000_000.0
    maximum_drawdown_fraction: float = 0.08
    target_geometric_net_return_fraction_per_session: float = 0.005
    risk_fraction_per_trade: float = 0.0015
    planning_sessions: int = 252
    maximum_planned_forward_product_cost_usd: float = 15_000.0
    theta_kill_r_per_session: float = 0.15
    session_sigma_r: float = 2.6
    provisional_futility_alpha: float = 0.05
    placebo_alpha: float = 0.05
    placebo_delta_floor_r: float = 0.10
    target_power: float = 0.80
    joint_h0_kill_target: float = 0.80
    first_checkpoint_sessions: int = 60
    final_checkpoint_sessions: int = 120
    arm_count: int = 2
    maximum_positions: int = 5

    def __post_init__(self) -> None:
        if self.reference_capital_usd <= 0:
            raise ValueError("reference_capital_usd must be positive")
        for field_name in (
            "maximum_drawdown_fraction",
            "target_geometric_net_return_fraction_per_session",
            "risk_fraction_per_trade",
        ):
            value = getattr(self, field_name)
            if not 0 < value < 1:
                raise ValueError(f"{field_name} must be between zero and one")
        for field_name in ("provisional_futility_alpha", "placebo_alpha"):
            value = getattr(self, field_name)
            if not 0 < value < 0.5:
                raise ValueError(f"{field_name} must be between zero and 0.5")
        for field_name in ("target_power", "joint_h0_kill_target"):
            value = getattr(self, field_name)
            if not 0.5 < value < 1:
                raise ValueError(f"{field_name} must be between 0.5 and one")
        if self.theta_kill_r_per_session <= 0:
            raise ValueError("theta_kill_r_per_session must be positive")
        if self.session_sigma_r <= 0:
            raise ValueError("session_sigma_r must be positive")
        if self.placebo_delta_floor_r < 0:
            raise ValueError("placebo_delta_floor_r cannot be negative")
        if self.planning_sessions <= 0:
            raise ValueError("planning_sessions must be positive")
        if self.maximum_planned_forward_product_cost_usd < 0:
            raise ValueError(
                "maximum_planned_forward_product_cost_usd cannot be negative"
            )
        if self.first_checkpoint_sessions <= 0:
            raise ValueError("first_checkpoint_sessions must be positive")
        if self.final_checkpoint_sessions <= self.first_checkpoint_sessions:
            raise ValueError(
                "final_checkpoint_sessions must exceed first_checkpoint_sessions"
            )
        if self.arm_count <= 0:
            raise ValueError("arm_count must be positive")
        if self.maximum_positions <= 0:
            raise ValueError("maximum_positions must be positive")
        if self.maximum_aggregate_initial_stop_risk_fraction > 1:
            raise ValueError("aggregate initial stop risk cannot exceed NAV")
        if self.theta_kill_opportunity_cost_budget_r_per_session < 0:
            raise ValueError(
                "theta_kill cannot be below the operating-cost component"
            )

    @property
    def initial_risk_usd_at_reference_nav(self) -> float:
        return self.reference_capital_usd * self.risk_fraction_per_trade

    @property
    def maximum_aggregate_initial_stop_risk_fraction(self) -> float:
        return self.risk_fraction_per_trade * self.maximum_positions

    @property
    def maximum_aggregate_initial_stop_risk_usd_at_reference_nav(self) -> float:
        return (
            self.reference_capital_usd
            * self.maximum_aggregate_initial_stop_risk_fraction
        )

    @property
    def theta_meta_r_per_session(self) -> float:
        return (
            self.target_geometric_net_return_fraction_per_session
            / self.risk_fraction_per_trade
        )

    @property
    def target_log_return_per_session(self) -> float:
        return math.log1p(
            self.target_geometric_net_return_fraction_per_session
        )

    @property
    def theta_kill_operating_cost_component_r_per_session(self) -> float:
        cost_per_session = (
            self.maximum_planned_forward_product_cost_usd
            / self.planning_sessions
        )
        return cost_per_session / self.initial_risk_usd_at_reference_nav

    @property
    def theta_kill_opportunity_cost_budget_r_per_session(self) -> float:
        return (
            self.theta_kill_r_per_session
            - self.theta_kill_operating_cost_component_r_per_session
        )

    @property
    def theta_kill_implied_annual_opportunity_rate_fraction(self) -> float:
        return (
            self.theta_kill_opportunity_cost_budget_r_per_session
            * self.risk_fraction_per_trade
            * self.planning_sessions
        )

    @property
    def target_ending_virtual_nav_usd(self) -> float:
        return self.reference_capital_usd * (
            1 + self.target_geometric_net_return_fraction_per_session
        ) ** self.planning_sessions

    @property
    def target_virtual_trading_profit_usd(self) -> float:
        return self.target_ending_virtual_nav_usd - self.reference_capital_usd

    @property
    def target_project_economic_surplus_after_forward_costs_usd(self) -> float:
        return (
            self.target_virtual_trading_profit_usd
            - self.maximum_planned_forward_product_cost_usd
        )


@dataclass(frozen=True)
class FrozenRiskScenario:
    risk_fraction_per_trade: float
    initial_risk_usd_at_reference_nav: float
    maximum_positions: int
    maximum_aggregate_initial_stop_risk_fraction: float
    maximum_aggregate_initial_stop_risk_usd_at_reference_nav: float
    theta_meta_r_per_session: float
    theta_kill_r_per_session: float
    theta_kill_operating_cost_component_r_per_session: float
    theta_kill_opportunity_cost_budget_r_per_session: float
    theta_kill_implied_annual_opportunity_rate_fraction: float
    target_log_return_per_session: float
    full_r_losses_to_maximum_drawdown: float
    full_book_stop_sessions_to_maximum_drawdown: float
    sessions_for_80pct_power_futility_only_at_theta_kill: int
    per_arm_futility_h0_kill_probability_c1: float
    per_arm_futility_h0_kill_probability_c2: float
    illustrative_joint_h0_class_kill_probability_c1: float
    illustrative_joint_h0_class_kill_probability_c2: float


@dataclass(frozen=True)
class TradeOutcomeClassification:
    realized_net_pnl_usd: float
    epsilon_trade_usd: float
    exact_ledger_outcome: str
    robust_outcome: str


def minimum_detectable_mean_r(
    sessions: int,
    assumptions: FeasibilityAssumptions,
) -> float:
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    normal = NormalDist()
    critical = normal.inv_cdf(1 - assumptions.provisional_futility_alpha)
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
    critical = normal.inv_cdf(1 - assumptions.provisional_futility_alpha)
    power_quantile = normal.inv_cdf(assumptions.target_power)
    required = (
        (critical + power_quantile)
        * assumptions.session_sigma_r
        / alternative_mean_r
    ) ** 2
    return math.ceil(required)


def h0_futility_kill_probability(
    theta_r: float,
    sessions: int,
    assumptions: FeasibilityAssumptions,
) -> float:
    """Approximate P(upper bound < theta) when true mean R is zero."""
    if theta_r <= 0:
        raise ValueError("theta_r must be positive")
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    normal = NormalDist()
    critical = normal.inv_cdf(1 - assumptions.provisional_futility_alpha)
    standardized = (
        theta_r * math.sqrt(sessions) / assumptions.session_sigma_r - critical
    )
    return normal.cdf(standardized)


def illustrative_joint_h0_class_kill_probability(
    theta_r: float,
    sessions: int,
    assumptions: FeasibilityAssumptions,
) -> float:
    """Conservative analytic illustration; Stage 2 must simulate the joint rule.

    This deliberately gives the damage blade no additional kill credit and
    treats the placebo pass probability as alpha. Arm dependence, the placebo
    delta floor and path-dependent damage rules remain for Stage 2.
    """
    futility_kill = h0_futility_kill_probability(
        theta_r, sessions, assumptions
    )
    per_arm_joint_survival = (
        (1 - futility_kill) * assumptions.placebo_alpha
    )
    return (1 - per_arm_joint_survival) ** assumptions.arm_count


def frozen_risk_scenario(
    assumptions: FeasibilityAssumptions | None = None,
) -> FrozenRiskScenario:
    active = assumptions or FeasibilityAssumptions()
    return FrozenRiskScenario(
        risk_fraction_per_trade=active.risk_fraction_per_trade,
        initial_risk_usd_at_reference_nav=(
            active.initial_risk_usd_at_reference_nav
        ),
        maximum_positions=active.maximum_positions,
        maximum_aggregate_initial_stop_risk_fraction=(
            active.maximum_aggregate_initial_stop_risk_fraction
        ),
        maximum_aggregate_initial_stop_risk_usd_at_reference_nav=(
            active.maximum_aggregate_initial_stop_risk_usd_at_reference_nav
        ),
        theta_meta_r_per_session=active.theta_meta_r_per_session,
        theta_kill_r_per_session=active.theta_kill_r_per_session,
        theta_kill_operating_cost_component_r_per_session=(
            active.theta_kill_operating_cost_component_r_per_session
        ),
        theta_kill_opportunity_cost_budget_r_per_session=(
            active.theta_kill_opportunity_cost_budget_r_per_session
        ),
        theta_kill_implied_annual_opportunity_rate_fraction=(
            active.theta_kill_implied_annual_opportunity_rate_fraction
        ),
        target_log_return_per_session=active.target_log_return_per_session,
        full_r_losses_to_maximum_drawdown=(
            active.maximum_drawdown_fraction / active.risk_fraction_per_trade
        ),
        full_book_stop_sessions_to_maximum_drawdown=(
            active.maximum_drawdown_fraction
            / active.maximum_aggregate_initial_stop_risk_fraction
        ),
        sessions_for_80pct_power_futility_only_at_theta_kill=(
            sessions_for_power(active.theta_kill_r_per_session, active)
        ),
        per_arm_futility_h0_kill_probability_c1=(
            h0_futility_kill_probability(
                active.theta_kill_r_per_session,
                active.first_checkpoint_sessions,
                active,
            )
        ),
        per_arm_futility_h0_kill_probability_c2=(
            h0_futility_kill_probability(
                active.theta_kill_r_per_session,
                active.final_checkpoint_sessions,
                active,
            )
        ),
        illustrative_joint_h0_class_kill_probability_c1=(
            illustrative_joint_h0_class_kill_probability(
                active.theta_kill_r_per_session,
                active.first_checkpoint_sessions,
                active,
            )
        ),
        illustrative_joint_h0_class_kill_probability_c2=(
            illustrative_joint_h0_class_kill_probability(
                active.theta_kill_r_per_session,
                active.final_checkpoint_sessions,
                active,
            )
        ),
    )


def classify_trade_outcome(
    realized_net_pnl_usd: float,
    half_spread_usd_per_share_at_exit: float,
    quantity: float,
    tick_floor_usd_per_share: float = 0.01,
) -> TradeOutcomeClassification:
    if half_spread_usd_per_share_at_exit < 0:
        raise ValueError("half spread cannot be negative")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if tick_floor_usd_per_share <= 0:
        raise ValueError("tick floor must be positive")

    epsilon_trade_usd = max(
        half_spread_usd_per_share_at_exit * quantity,
        tick_floor_usd_per_share * quantity,
    )
    if realized_net_pnl_usd > 0:
        exact_outcome = "win"
    elif realized_net_pnl_usd < 0:
        exact_outcome = "loss"
    else:
        exact_outcome = "flat"

    if realized_net_pnl_usd > epsilon_trade_usd:
        robust_outcome = "win"
    elif realized_net_pnl_usd < -epsilon_trade_usd:
        robust_outcome = "loss"
    else:
        robust_outcome = "tie"

    return TradeOutcomeClassification(
        realized_net_pnl_usd=realized_net_pnl_usd,
        epsilon_trade_usd=epsilon_trade_usd,
        exact_ledger_outcome=exact_outcome,
        robust_outcome=robust_outcome,
    )


def feasibility_report(
    assumptions: FeasibilityAssumptions | None = None,
) -> dict:
    active = assumptions or FeasibilityAssumptions()
    scenario = frozen_risk_scenario(active)
    return {
        "status": "contract_frozen_paper_only",
        "assumptions": asdict(active)
        | {
            "initial_risk_usd_at_reference_nav": (
                active.initial_risk_usd_at_reference_nav
            ),
            "maximum_aggregate_initial_stop_risk_fraction": (
                active.maximum_aggregate_initial_stop_risk_fraction
            ),
            "theta_meta_r_per_session": active.theta_meta_r_per_session,
            "target_log_return_per_session": (
                active.target_log_return_per_session
            ),
            "theta_kill_operating_cost_component_r_per_session": (
                active.theta_kill_operating_cost_component_r_per_session
            ),
            "theta_kill_opportunity_cost_budget_r_per_session": (
                active.theta_kill_opportunity_cost_budget_r_per_session
            ),
            "theta_kill_implied_annual_opportunity_rate_fraction": (
                active.theta_kill_implied_annual_opportunity_rate_fraction
            ),
            "target_ending_virtual_nav_usd": (
                active.target_ending_virtual_nav_usd
            ),
            "target_virtual_trading_profit_usd": (
                active.target_virtual_trading_profit_usd
            ),
            "target_project_economic_surplus_after_forward_costs_usd": (
                active.target_project_economic_surplus_after_forward_costs_usd
            ),
        },
        "minimum_detectable_mean_r_futility_only": {
            "c1": minimum_detectable_mean_r(
                active.first_checkpoint_sessions, active
            ),
            "c2": minimum_detectable_mean_r(
                active.final_checkpoint_sessions, active
            ),
        },
        "selected_scenario": asdict(scenario),
        "joint_h0_kill_acceptance": {
            "binding_target_fraction": active.joint_h0_kill_target,
            "rule": "futility_and_damage_and_placebo",
            "placebo_pass_requires": {
                "p_value_lte": active.placebo_alpha,
                "delta_r_gte": active.placebo_delta_floor_r,
            },
            "analytic_independence_result_is_binding": False,
            "stage2_path_simulation_required": True,
        },
        "limitations": [
            "Burned draft sigma is a placeholder until official S3/S5 replay.",
            "Checkpoint N and alpha remain provisional until Stage 2.",
            "The analytic joint illustration assumes independent arms.",
            "The illustration gives the damage blade no extra kill credit.",
            "Carry serial dependence is not modeled in this analytic screen.",
            "Statistical detectability does not establish attainability of theta_meta.",
            "The T-bill rate is frozen only on the final preregistration hash date.",
        ],
    }


def main() -> None:
    print(json.dumps(feasibility_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
