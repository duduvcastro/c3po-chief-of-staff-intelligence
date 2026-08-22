from __future__ import annotations

import json
import math
from datetime import time, timedelta, datetime
from pathlib import Path


C3PO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = C3PO_ROOT / "docs" / "day_d" / "stage0_contract.json"


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _clock_datetime(value: str) -> datetime:
    parsed = time.fromisoformat(value)
    return datetime(2000, 1, 1, parsed.hour, parsed.minute, parsed.second)


def test_contract_authorizes_stage_zero_only() -> None:
    contract = _contract()

    assert contract["blueprint_version"] == "DAY-D-v1.2"
    assert contract["contract_status"] == "stage0_authorized"
    assert contract["economic_and_risk_contract_status"] == "frozen"
    assert contract["authorized_stage"] == 0
    assert contract["production_behavior_change_authorized"] is False
    assert contract["capital_use_authorized"] is False
    assert contract["signatures"]["fable"] == "signed_final_2026_08_22"
    assert contract["stage0"]["complete"] is False
    owner_inputs = contract["stage0"]["owner_inputs"]
    assert owner_inputs["economic_mandate"] == "day_d/economic_mandate.json"
    assert owner_inputs["risk_per_trade"] == {
        "status": "frozen",
        "basis": "fraction_of_current_virtual_nav_at_trade_entry",
        "fraction": 0.0015,
        "initial_reference_usd": 1500,
        "paper_dollar_cap_usd": None,
    }
    assert owner_inputs["theta_meta"] == {
        "status": "frozen_product_target",
        "required_geometric_net_return_fraction_per_session": 0.005,
        "r_per_session": 0.005 / 0.0015,
        "kill_authority": False,
    }
    assert owner_inputs["theta_kill"]["status"] == (
        "formula_frozen_pending_benchmark_snapshot_at_hash"
    )
    assert owner_inputs["theta_kill"]["r_per_session"] == 0.15
    assert owner_inputs["theta_kill"]["benchmark"] == (
        "US_3_MONTH_TREASURY_BILL"
    )
    assert owner_inputs["theta_kill"]["benchmark_rate_to_r_per_session_formula"] == (
        "(annual_rate_decimal / 252) / 0.0015"
    )
    assert owner_inputs["theta_kill"]["final_reconciliation_formula"] == (
        "max(0.15, operating_cost_component_r_per_session_at_initial_nav + benchmark_rate_r_per_session)"
    )
    assert owner_inputs["theta_kill"]["o1_reconciliation_rule_status"] == (
        "closed_and_frozen"
    )
    assert owner_inputs["success_definition_12_months"] == {
        "status": "recorded",
        "trading_capital_mode": "virtual_only",
        "real_trading_capital_during_horizon_usd": 0,
        "target_geometric_net_return_fraction_per_session": 0.005,
        "target_is_mandatory_each_session": False,
        "target_session_population": "all_preregistered_exchange_sessions",
        "no_trade_session_return_fraction": 0,
        "robust_win_rate_lower_bound_minimum_exclusive": 0.5,
        "robust_win_rate_binding_at": "final_12_month_verdict_only",
        "closed_trade_pnl_basis": "realized_net_after_all_simulated_costs",
        "target_revision_is_prospective_and_versioned_only": True,
        "maximum_drawdown_fraction": 0.08,
        "capex_and_opex_are_real_product_investments": True,
    }


def test_clock_keeps_screening_and_risk_windows_separate() -> None:
    clock = _contract()["clock"]
    open_at = _clock_datetime(clock["regular_open"])
    entry_cutoff = _clock_datetime(clock["new_entry_cutoff"])
    close_at = _clock_datetime(clock["regular_close"])
    risk_start = _clock_datetime(clock["risk_monitor_start"])
    risk_end = _clock_datetime(clock["risk_monitor_end"])

    assert clock["timezone"] == "America/New_York"
    assert clock["calendar_source"] == "exchange_calendar"
    assert open_at == risk_start
    assert open_at < entry_cutoff < close_at
    assert risk_end == close_at
    assert close_at - timedelta(seconds=clock["t30_seconds_before_official_close"]) == _clock_datetime(
        "15:59:30"
    )
    assert clock["early_close_hardcoding_forbidden"] is True


def test_t30_policy_preserves_conditional_carry() -> None:
    policy = _contract()["close_policy"]

    assert policy["poll_interval_seconds"] == 1
    assert policy["event_driven_claim"] is False
    assert policy["decision_price"] == "fresh_executable_bid"
    assert policy["positive_test"] == "estimated_net_exit_pnl_pct > 0"
    assert policy["estimated_net_includes_entry_basis"] is True
    assert policy["estimated_net_includes_exit_slippage_and_fee"] is True
    assert policy["weekly_conviction_exemption"] is False
    assert policy["fill_must_precede_official_close"] is True
    assert policy["unfilled_event"] == "late_unfilled_exit"
    assert policy["carry_max_sessions"] is None
    assert policy["premarket_mode"] == "information_only"
    assert policy["regular_open_revalidation_required"] is True


def test_generation_one_cannot_silently_reenable_legacy_arms() -> None:
    book = _contract()["experimental_book"]

    assert book["active_setup_versions"] == ["S3-v1", "S5-v1"]
    assert book["equal_weight"] is True
    assert book["thompson_sampling_enabled"] is False
    assert book["s5_v1_uses_cvd"] is False
    assert book["risk_per_trade_basis"] == (
        "fraction_of_current_virtual_nav_at_trade_entry"
    )
    assert book["risk_fraction_per_trade"] == 0.0015
    assert book["initial_risk_usd_at_reference_nav"] == 1_500
    assert book["dollar_cap_during_paper_usd"] is None
    assert book["risk_budget_frozen_for_trade_lifetime"] is True
    assert book["max_simultaneous_positions"] == 5
    assert book["maximum_aggregate_initial_stop_risk_fraction"] == 0.0075
    assert book["risk_recalibration_required_before_real_capital"] is True
    assert book["duplicate_symbol_exposure_allowed"] is False
    assert book["weekly_conviction_affects_experiment"] is False


def test_ledger_identity_and_daily_carry_marking_are_explicit() -> None:
    ledger = _contract()["ledger"]

    assert ledger["identity"] == "R_consolidated = R_intraday + R_overnight"
    assert ledger["entry_session_transfer_mark"] == "official_close"
    assert ledger["transfer_mark_has_fictitious_fee"] is False
    assert ledger["daily_marking"] is True
    assert ledger["no_new_trade_with_open_carry_is_zero"] is False
    assert ledger["corporate_actions_required"] is True
    assert ledger["flat_at_close_is_independent_policy_complete_replay"] is True


def test_inference_does_not_treat_retention_as_evidence() -> None:
    inference = _contract()["inference"]

    assert inference["session_checkpoints"] == [60, 120]
    assert inference["burn_in_sessions"] == 30
    assert inference["decisions_outside_checkpoints_allowed"] is False
    assert inference["retained_is_approval"] is False
    assert inference["positive_evidence_requires_lower_bound"] is True
    assert inference["joint_multiplicity_calibration_required"] is True
    assert inference["serial_dependence_must_be_modeled"] is True
    assert inference["unadjusted_iid_t_test_is_sufficient"] is False
    assert inference["weekly_block_bootstrap_required"] is True


def test_inference_separates_product_target_from_kill_threshold() -> None:
    inference = _contract()["inference"]

    assert inference["theta_meta"] == {
        "r_per_session": 0.005 / 0.0015,
        "status": "product_target_only",
        "kill_authority": False,
    }
    assert inference["theta_kill"]["r_per_session"] == 0.15
    assert inference["theta_kill"]["binding_at"] == ["C1", "C2"]
    assert inference["theta_kill"]["cost_assumption"] == "optimistic"
    assert inference["theta_kill"]["benchmark_rate_to_r_per_session_formula"] == (
        "(annual_rate_decimal / 252) / 0.0015"
    )
    assert inference["theta_kill"]["final_reconciliation_formula"] == (
        "max(0.15, operating_cost_r_per_session + benchmark_rate_r_per_session)"
    )
    assert set(inference["theta_kill"]["hash_must_record"]) == {
        "benchmark_source",
        "annual_rate_decimal",
        "observed_at",
        "benchmark_rate_r_per_session",
        "theta_kill_final_r_per_session",
    }

    joint = inference["joint_h0_kill_rule"]
    assert joint["blades"] == ["futility", "damage", "placebo"]
    assert joint["arm_survival_requires_all_blades_pass"] is True
    assert joint["placebo_p_value_maximum"] == 0.05
    assert joint["placebo_delta_r_minimum"] == 0.10
    assert joint["class_kill_probability_minimum"] == 0.80
    assert joint["stage2_path_simulation_required"] is True
    assert joint["analytic_independence_approximation_is_binding"] is False


def test_theta_kill_reconciliation_reproduces_the_approved_budget() -> None:
    theta = _contract()["stage0"]["owner_inputs"]["theta_kill"]

    benchmark_rate_r = (0.0417 / 252) / 0.0015
    assert math.isclose(
        benchmark_rate_r,
        theta["opportunity_cost_component_budget_r_per_session"],
        rel_tol=0,
        abs_tol=1e-15,
    )
    reconciled = max(
        theta["r_per_session"],
        theta["operating_cost_component_r_per_session_at_initial_nav"]
        + benchmark_rate_r,
    )
    assert math.isclose(reconciled, 0.15, rel_tol=0, abs_tol=1e-15)


def test_win_rate_is_robust_and_binding_only_at_final_verdict() -> None:
    inference = _contract()["inference"]
    outcomes = inference["closed_trade_outcomes"]

    assert outcomes["exact_ledger_sign_has_epsilon"] is False
    assert outcomes["robust_epsilon_formula"] == (
        "max(exit_half_spread_usd_per_share * quantity, 0.01 * quantity)"
    )
    assert outcomes["robust_ties_excluded_from_win_rate"] is True
    assert outcomes["round_trip_cost_is_epsilon"] is False
    assert outcomes["robust_win_rate_lower_bound_minimum_exclusive"] == 0.5
    assert outcomes["win_rate_bootstrap_unit"] == "session_block"
    assert outcomes["win_rate_binding_at"] == "final_12_month_verdict_only"
    assert outcomes["win_rate_checkpoint_status"] == "diagnostic_only"
    assert inference["payoff_and_profit_factor_are_binding"] is False


def test_stage_zero_cannot_claim_completion_with_open_freeze_items() -> None:
    stage0 = _contract()["stage0"]

    assert stage0["preliminary_feasibility"] == {
        "status": "analytic_screen_only",
        "report": "day_d/STAGE_0_RISK_POWER_FEASIBILITY.md",
        "reproducer": "app.day_d_feasibility",
        "fixed_nav_fraction_risk_frozen": True,
        "selected_risk_fraction_per_trade": 0.0015,
        "joint_h0_kill_calibration_status": "pending_stage2_path_simulation",
    }
    assert stage0["signal_and_universe_freeze"]["status"] == (
        "frozen_on_merge_after_six_hands_review"
    )
    assert stage0["signal_and_universe_freeze"]["contract"] == (
        "day_d/replay_signal_spec_v1.json"
    )
    assert len(stage0["signal_and_universe_freeze"]["resolved_items"]) == 10
    assert stage0["freeze_required_before_replay_eligible"] == [
        "fresh quote and eligible fill definitions",
        "corporate action, halt and delisting accounting",
        "session dependence-aware primary test",
        "T0 T1 T4 T5 numeric acceptance thresholds",
    ]
    assert "fixed dollar risk" not in " ".join(
        stage0["freeze_required_before_replay_eligible"]
    ).lower()
    assert {
        "enable_production_setup",
        "change_live_entry_or_exit_logic",
        "enable_raw_capture",
        "purchase_polygon",
        "promote_capital",
        "claim_final_preregistration",
    } == set(stage0["later_stage_actions_forbidden"])
