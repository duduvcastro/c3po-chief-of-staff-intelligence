from __future__ import annotations

import json
from pathlib import Path


C3PO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = C3PO_ROOT / "docs" / "day_d" / "replay_signal_spec_v1.json"
STAGE0_PATH = C3PO_ROOT / "docs" / "day_d" / "stage0_contract.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_signal_spec_is_versioned_research_only() -> None:
    spec = _load(SPEC_PATH)

    assert spec["schema_version"] == "1.0.0"
    assert spec["spec_version"] == "DAY-D-SIGNAL-UNIVERSE-v1"
    assert spec["status"] == "frozen_on_merge_after_six_hands_review"
    assert spec["production_behavior_change_authorized"] is False
    assert spec["capital_use_authorized"] is False
    assert spec["harness_implementation_in_scope"] is False
    assert spec["versions"] == {
        "feature_version": "DAY-D-FEATURES-v1",
        "universe_version": "DAY-D-UNIVERSE-v1",
        "s3_version": "S3-v1",
        "s5_version": "S5-v1",
        "risk_policy_version": "DAY-D-RISK-v1",
    }

    stage0 = _load(STAGE0_PATH)
    reference = stage0["signal_and_universe_contract"]
    assert reference["path"] == "day_d/replay_signal_spec_v1.json"
    assert reference["spec_version"] == spec["spec_version"]
    assert reference["production_behavior_change_authorized"] is False
    assert reference["capital_use_authorized"] is False


def test_temporal_contract_forbids_lookahead() -> None:
    spec = _load(SPEC_PATH)
    clock = spec["temporal_contract"]

    assert clock["timezone"] == "America/New_York"
    assert clock["calendar_source"] == "exchange_calendar"
    assert clock["regular_session_only"] is True
    assert clock["bar_interval_seconds"] == 60
    assert clock["bar_interval_semantics"] == "left_closed_right_open"
    assert clock["bar_available_only_at_or_after_interval_end"] is True
    assert clock["same_bar_signal_and_fill_forbidden"] is True
    assert clock["feature_event_at_must_be_lte_decision_at"] is True
    assert clock["feature_available_at_must_be_lte_decision_at"] is True

    invariants = set(spec["anti_lookahead_invariants"])
    assert {
        "every_input_has_event_at_and_available_at",
        "event_at_and_available_at_are_not_after_decision_at",
        "one_minute_bar_is_unavailable_before_its_end",
        "signal_bar_cannot_fill_itself",
        "universe_and_rank_are_computed_only_from_information_available_by_D1",
        "cross_sectional_values_use_only_the_frozen_D1_observable_universe",
        "historical_adjustments_never_use_a_future_corporate_action",
        "cost_cells_for_session_D_use_only_sessions_before_D",
        "provider_corrections_do_not_rewrite_prior_decisions",
        "randomized_components_use_a_persisted_deterministic_seed",
    } == invariants


def test_universe_is_d1_point_in_time_and_deterministic() -> None:
    universe = _load(SPEC_PATH)["universe"]

    assert universe["selection_count"] == 60
    assert universe["benchmark_symbols"] == ["QQQ"]
    assert universe["benchmark_is_tradeable_by_generation_one"] is False
    assert universe["selection_information_cutoff"] == "D-1_official_close"
    assert universe["selection_is_immutable_intraday"] is True
    assert universe["eligible_listing_mics"] == ["XNAS", "XNYS"]
    assert universe["minimum_d1_official_close_usd"] == 3.0
    assert universe["ranking_lookback_completed_sessions"] == 20
    assert universe["minimum_complete_ranking_sessions"] == 20
    assert universe["ranking_statistic"] == "median_session_dollar_volume"
    assert universe["ranking_direction"] == "descending"
    assert universe["issuer_deduplication"]["enabled"] is True
    assert universe["issuer_deduplication"]["tie_break"] == (
        "normalized_ticker_ascending"
    )
    assert universe["historical_membership"]["survivorship_free_required"] is True
    assert universe["historical_membership"]["future_corporate_actions_forbidden"] is True

    substitution = universe["preopen_substitution"]
    assert substitution["cutoff_local_time"] == "09:25:00"
    assert substitution[
        "allowed_only_for_permanent_administrative_unavailability_known_by_cutoff"
    ] is True
    assert set(substitution["allowed_reason_codes"]) == {
        "DELISTING_EFFECTIVE_BEFORE_REGULAR_OPEN",
        "MERGER_OR_SECURITY_CANCELLATION_EFFECTIVE_BEFORE_REGULAR_OPEN",
        "POINT_IN_TIME_SYMBOL_MAPPING_RETIRED_BEFORE_REGULAR_OPEN",
    }
    assert "MISSING_LIVE_QUOTE" in substitution["forbidden_reason_codes"]
    assert "TRADING_HALT" in substitution["forbidden_reason_codes"]
    assert substitution["source_order"] == "continue_down_frozen_d1_ranking"
    assert substitution["intraday_replacement_for_halt_or_missing_data_forbidden"] is True
    assert substitution["recompute_ranking_with_d_information_forbidden"] is True


def test_shared_features_have_exact_causal_formulas() -> None:
    features = _load(SPEC_PATH)["shared_features"]

    assert features["one_minute_bar"]["empty_bar_rule"] == (
        "bar_is_missing_and_cannot_trigger_a_signal"
    )
    assert features["vwap"] == {
        "reset": "each_regular_session",
        "typical_price_formula": "(high + low + close) / 3",
        "formula": "cumulative_sum(typical_price * volume) / cumulative_sum(volume)",
        "inputs": "completed_one_minute_bars_only",
        "zero_cumulative_volume_rule": "unavailable",
    }

    rvol = features["rvol"]
    assert rvol["historical_window_sessions"] == 20
    assert rvol["minimum_historical_observations_for_same_minute"] == 15
    assert rvol["current_session_excluded_from_baseline"] is True
    assert rvol["future_sessions_forbidden"] is True
    assert rvol["insufficient_history_rule"] == "unavailable"

    atr = features["atr"]
    assert atr["period_completed_one_minute_bars"] == 14
    assert atr["true_range_formula"] == (
        "max(high-low, abs(high-previous_close), abs(low-previous_close))"
    )
    assert atr["first_current_session_previous_close"] == "D-1_official_close"
    assert atr["seed"] == (
        "simple_mean_of_first_14_completed_current_session_true_ranges"
    )
    assert atr["update"] == "Wilder((previous_atr*13 + current_true_range)/14)"
    assert atr["available_after_completed_bar_count"] == 14
    assert atr["same_incomplete_bar_forbidden"] is True


def test_shared_risk_and_sizing_are_frozen() -> None:
    risk = _load(SPEC_PATH)["shared_risk_and_sizing"]

    assert risk["risk_budget_fraction_of_current_virtual_nav_at_entry"] == 0.0015
    assert risk["risk_budget_usd_frozen_for_trade_lifetime"] is True
    assert risk["maximum_simultaneous_positions"] == 5
    assert risk["maximum_aggregate_initial_stop_risk_fraction"] == 0.0075
    assert risk["maximum_position_notional_fraction_of_nav"] == 0.20
    assert risk["portfolio_leverage_allowed"] is False
    assert risk[
        "maximum_participation_fraction_of_prior_five_completed_minutes_volume"
    ] == 0.01
    assert risk["minimum_stop_distance_formula"] == (
        "max(0.50 * entry_atr, point_cost_model_full_spread_per_share, 2 * minimum_tick)"
    )
    assert risk["maximum_stop_distance_atr_multiple"] == 2.0
    assert risk["quantity_formula"] == (
        "floor(risk_budget_usd / risk_per_share_usd)"
    )
    assert risk["fractional_shares_allowed"] is False
    assert risk["oversized_notional_rule"] == "reject_not_resize"
    assert risk["participation_breach_rule"] == "reject_not_resize"


def test_s3_v1_is_frozen_without_rearm_or_same_bar_fill() -> None:
    s3 = _load(SPEC_PATH)["setups"]["S3-v1"]

    assert s3["maximum_signal_attempts_per_symbol_per_session"] == 1
    assert s3["opening_range"] == {
        "start_local_time_inclusive": "09:30:00",
        "end_local_time_exclusive": "09:45:00",
        "required_completed_bars": 15,
        "high": "maximum_high_of_required_bars",
        "low": "minimum_low_of_required_bars",
        "range": "high-low",
        "zero_range_rule": "no_signal",
        "missing_bar_or_halt_rule": "no_signal_for_symbol_for_session",
    }
    assert s3["raw_breakout_event"] == (
        "first_completed_bar_after_opening_range_with_close > opening_range_high"
    )
    assert s3["decision_at"] == "raw_breakout_bar_end"
    assert s3["failed_first_breakout_rule"] == (
        "expire_setup_for_symbol_for_session_without_rearm"
    )
    assert s3["entry_activation"].startswith(
        "first_execution_eligible_observation_strictly_after_decision_at"
    )
    assert s3["entry_expiry"] == (
        "earlier_of_three_completed_bars_after_decision_or_11:45:00"
    )
    assert s3["entry_expiry_boundary"] == (
        "fill_at_must_be_strictly_before_entry_expiry_at"
    )
    assert s3["initial_structural_stop"] == "max(opening_range_low, entry_time_vwap)"

    gates = set(s3["all_entry_gates"])
    assert "raw_breakout_bar.rvol >= 1.5" in gates
    assert "QQQ.latest_completed_bar.close > QQQ.current_completed_bar.vwap" not in gates
    assert "QQQ.latest_completed_bar.close > QQQ.current_completed_bar_vwap" in gates
    assert (
        "raw_breakout_bar.event_at - QQQ.latest_completed_bar.event_at <= 1_minute"
        in gates
    )
    assert "raw_breakout_bar.close <= opening_range_high + 0.5 * opening_range_range" in gates

    profit = s3["profit_plan"]
    assert profit["partial_target_r"] == 1.5
    assert profit["partial_quantity_fraction"] == 0.50
    assert profit["runner_target_r"] == 2.0
    assert profit["chandelier_activates_after_partial_fill"] is True
    assert profit["chandelier_atr_multiple"] == 2.5
    assert profit["chandelier_is_monotonic"] is True
    assert s3["same_timestamp_exit_precedence"] == [
        "hard_or_initial_stop",
        "chandelier",
        "2R_target",
        "T30_or_other_portfolio_override",
    ]


def test_s5_v1_is_bar_based_with_frozen_target() -> None:
    s5 = _load(SPEC_PATH)["setups"]["S5-v1"]

    assert s5["uses_cvd"] is False
    assert s5["uses_order_flow"] is False
    assert s5["uses_qqq_gate"] is False
    assert s5["maximum_signal_attempts_per_symbol_per_session"] == 1
    assert s5["earliest_possible_evaluation"] == (
        "after_14_completed_regular_session_bars"
    )
    assert s5["excursion_event"] == (
        "first_completed_bar_with_low <= current_completed_bar_vwap - 1.5 * current_completed_bar_atr"
    )
    assert s5["reclaim_event"] == (
        "first_later_completed_bar_with_close > midpoint_of_immediately_preceding_completed_bar_and_rvol >= 1.5"
    )
    assert s5["decision_at"] == "reclaim_bar_end"
    assert s5["entry_activation"].startswith(
        "first_execution_eligible_observation_strictly_after_decision_at"
    )
    assert s5["entry_expiry"] == (
        "earlier_of_three_completed_bars_after_decision_or_14:30:00"
    )
    assert s5["entry_expiry_boundary"] == (
        "fill_at_must_be_strictly_before_entry_expiry_at"
    )
    assert s5["new_fill_at_or_after_14_30_forbidden"] is True
    assert s5["initial_structural_stop"] == "excursion_low - minimum_tick"
    assert s5["target"] == {
        "value": "completed_bar_vwap_observed_at_entry_fill_time",
        "frozen_for_trade_lifetime": True,
        "moving_vwap_after_entry_ignored": True,
        "ex_ante_validity_rule": (
            "decision_time_vwap_must_be_strictly_above_reclaim_bar_high"
        ),
        "ex_ante_entry_reference": "reclaim_bar_high",
        "target_must_be_strictly_above_entry_fill": False,
        "post_fill_above_target_rule": (
            "filled_trade_remains_real_and_exits_under_normal_rules_without_retroactive_veto"
        ),
        "invalid_target_rule": "reject_signal_at_decision_time_only",
    }
    assert s5["maximum_holding_seconds"] == 2700
    assert s5["failed_or_expired_attempt_rule"] == (
        "no_rearm_for_symbol_for_session"
    )


def test_harness_risks_remain_explicitly_deferred() -> None:
    spec = _load(SPEC_PATH)

    assert set(spec["separate_harness_contract_still_required"]) == {
        "fresh_quote_and_execution_eligible_observation",
        "latency_and_jitter",
        "marketable_entry_fill",
        "two_print_stop_confirmation_and_notional_floor",
        "halt_and_reopening_fill",
        "cost_quintile_time_bucket_table",
        "corporate_action_and_delisting_ledger_accounting",
        "synthetic_truth_ci_gate",
    }

    required_audit_fields = set(spec["required_signal_audit_fields"])
    assert {
        "signal_event_at",
        "signal_available_at",
        "decision_at",
        "feature_as_of",
        "all_gate_values",
        "gate_result",
        "suppression_or_rejection_reason",
    } <= required_audit_fields
