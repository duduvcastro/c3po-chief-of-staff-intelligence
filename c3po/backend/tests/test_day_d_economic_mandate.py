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
    target_return = mandate["target_net_return_fraction"]
    drawdown = mandate["maximum_drawdown_fraction"]

    assert mandate["target_net_profit_usd"] == capital * target_return
    assert mandate["target_ending_economic_value_usd"] == capital + mandate["target_net_profit_usd"]
    assert mandate["maximum_drawdown_usd_at_reference_capital"] == capital * drawdown
    assert mandate["drawdown_measurement"]["calendar_reset"] is False


def test_year_one_planning_translation_includes_forward_costs() -> None:
    mandate = _mandate()
    budget = mandate["budget"]
    planning = mandate["planning_translation"]

    recurring = budget["maximum_recurring_usd_per_month"] * 12
    forward_cost = recurring + budget["baseline_new_capex_usd"]
    gross_target = mandate["target_net_profit_usd"] + forward_cost

    assert budget["maximum_recurring_usd_per_year"] == recurring
    assert planning["maximum_planned_year_one_forward_cost_usd"] == forward_cost
    assert planning["required_gross_trading_profit_usd"] == gross_target
    assert math.isclose(
        planning["required_simple_average_gross_usd_per_session"],
        gross_target / planning["planning_sessions"],
    )
    assert math.isclose(
        planning["required_compounded_net_return_fraction_per_session"],
        (1 + mandate["target_net_return_fraction"]) ** (1 / planning["planning_sessions"]) - 1,
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


def test_r_normalized_threshold_remains_blocked_until_risk_is_frozen() -> None:
    planning = _mandate()["planning_translation"]

    assert planning["theta_econ_usd_per_session_status"] == (
        "provisional_until_exact_calendar_and_cost_inventory"
    )
    assert planning["theta_econ_r_per_session"] is None
    assert planning["theta_econ_r_requires_fixed_dollar_risk"] is True
