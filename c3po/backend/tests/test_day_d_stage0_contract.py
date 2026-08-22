from __future__ import annotations

import json
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
    assert contract["authorized_stage"] == 0
    assert contract["production_behavior_change_authorized"] is False
    assert contract["capital_use_authorized"] is False
    assert contract["stage0"]["complete"] is False
    owner_inputs = contract["stage0"]["owner_inputs"]
    assert owner_inputs["economic_mandate"] == "day_d/economic_mandate.json"
    assert owner_inputs["theta_econ_from_npv"]["status"] == "provisional_usd_only"
    assert owner_inputs["theta_econ_from_npv"]["r_per_session"] is None
    assert owner_inputs["theta_econ_from_npv"]["requires_fixed_dollar_risk"] is True
    assert owner_inputs["success_definition_12_months"] == {
        "status": "recorded",
        "target_net_return_fraction": 1.0,
        "maximum_drawdown_fraction": 0.08,
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
    assert book["fixed_dollar_risk_per_trade"] is True
    assert book["max_simultaneous_positions"] == 5
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


def test_stage_zero_cannot_claim_completion_with_open_freeze_items() -> None:
    stage0 = _contract()["stage0"]

    assert stage0["preliminary_feasibility"] == {
        "status": "analytic_screen_only",
        "report": "day_d/STAGE_0_RISK_POWER_FEASIBILITY.md",
        "reproducer": "app.day_d_feasibility",
        "fixed_dollar_risk_frozen": False,
        "selected_scenario": None,
    }
    assert len(stage0["freeze_required_before_replay_eligible"]) >= 15
    assert {
        "enable_production_setup",
        "change_live_entry_or_exit_logic",
        "enable_raw_capture",
        "purchase_polygon",
        "promote_capital",
        "claim_final_preregistration",
    } == set(stage0["later_stage_actions_forbidden"])
