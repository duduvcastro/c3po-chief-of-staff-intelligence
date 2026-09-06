from __future__ import annotations

import math

import numpy as np
import pytest

from app import r2d2_v2_calibration as cal
from app import r2d2_v2_estimator as est


def _rows(n: int, upper_e: int, lower_e: int, upper_c: int, lower_c: int, pnl: float) -> list[dict]:
    return [{"upper_e": upper_e, "lower_e": lower_e, "upper_c": upper_c, "lower_c": lower_c,
             "pnl_sum_usd": pnl, "pnl_count": 1} for _ in range(n)]


# ---------------------------------------------------------------- bootstrap mechanics (§5)

def test_block_weights_are_deterministic_and_follow_the_contract() -> None:
    w1 = est.circular_block_weights(20)
    w2 = est.circular_block_weights(20)
    assert w1.shape == (est.BOOTSTRAP_ITERATIONS, 20)
    assert np.array_equal(w1, w2)
    assert np.all(w1.sum(axis=1) == 20)
    w30 = est.circular_block_weights(30)
    assert np.all(w30.sum(axis=1) == 30)
    assert w1[0].max() <= math.ceil(20 / est.BLOCK_LENGTH)
    # first replica of n=20 reproduces four uniform starts from random.Random(20260824)
    import random
    rng = random.Random(est.BOOTSTRAP_SEED)
    expected = np.zeros(20, dtype=int)
    for _ in range(4):
        start = rng.randrange(20)
        for offset in range(5):
            expected[(start + offset) % 20] += 1
    assert np.array_equal(w1[0], expected)


def test_hf7_matches_numpy_linear_and_propagates_minus_infinity() -> None:
    values = np.arange(1.0, 11.0)
    assert est.hf7_quantile(values, 0.25) == pytest.approx(float(np.quantile(values, 0.25)))
    assert est.hf7_quantile(values, 1 / 120) == pytest.approx(float(np.quantile(values, 1 / 120)))
    assert est.hf7_quantile(np.array([-math.inf, 1.0, 2.0]), 0.1) == -math.inf
    assert est.hf7_quantile(np.array([-math.inf, 1.0, 2.0]), 0.75) == 1.5


def test_maturation_session_includes_entry_session() -> None:
    assert est.maturation_session(20) == 29
    assert est.maturation_session(30) == 39


# ---------------------------------------------------------------- readings and joint approval (§4)

def test_reading_approves_only_jointly_and_publishes_lcbs_and_reasons() -> None:
    strong = est.cohort_from_sessions(_rows(20, 14, 6, 6, 14, 60.0), 20)
    reading = est.read_cohort(strong)
    assert reading["joint_approval"] is True
    for h in reading["hypotheses"].values():
        assert h["status"] == "APPROVED" and h["reasons"] == []
        assert h["defined_replicas"] == est.BOOTSTRAP_ITERATIONS
    assert reading["hypotheses"]["R1"]["point"] == pytest.approx(0.4)
    assert reading["hypotheses"]["H1"]["lcb_one_sided"] > 0.5
    assert reading["hypotheses"]["H3"]["lcb_one_sided"] > 0.0
    weak = est.read_cohort(est.cohort_from_sessions(_rows(20, 10, 10, 10, 10, 0.0), 20))
    assert weak["joint_approval"] is False
    assert all(h["status"] == "NOT_APPROVED" and h["reasons"] == ["LCB_NOT_ABOVE_THRESHOLD"] for h in weak["hypotheses"].values())
    assert weak["hypotheses"]["R1"]["lcb_one_sided"] <= 0.0  # LCB still published when not approved (degenerate cohort: exactly 0)
    noisy = _rows(20, 10, 10, 10, 10, 0.0)
    noisy[0].update(upper_e=12, lower_e=8, upper_c=8, lower_c=12)
    noisy[1].update(upper_e=8, lower_e=12, upper_c=12, lower_c=8)
    assert est.read_cohort(est.cohort_from_sessions(noisy, 20))["hypotheses"]["R1"]["lcb_one_sided"] < 0.0


def test_partial_approval_never_becomes_joint() -> None:
    rows = _rows(20, 14, 6, 6, 14, -60.0)  # R1 and H1 strong, H3 negative
    reading = est.read_cohort(est.cohort_from_sessions(rows, 20))
    assert reading["hypotheses"]["R1"]["status"] == "APPROVED"
    assert reading["hypotheses"]["H1"]["status"] == "APPROVED"
    assert reading["hypotheses"]["H3"]["status"] == "NOT_APPROVED"
    assert reading["joint_approval"] is False


# ---------------------------------------------------------------- counter-proofs of states (annex B §3)

def test_absent_control_arm_is_not_estimable_for_r1_only() -> None:
    reading = est.read_cohort(est.cohort_from_sessions(_rows(20, 14, 6, 0, 0, 60.0), 20))
    r1 = reading["hypotheses"]["R1"]
    assert r1["status"] == "NOT_ESTIMABLE" and r1["point"] is None
    assert set(r1["reasons"]) >= {"NO_RESOLVED_OBSERVATIONS", "INSUFFICIENT_DEFINED_REPLICAS", "LCB_NOT_ABOVE_THRESHOLD"}
    assert r1["defined_replicas"] == 0 and r1["undefined_replicas"] == est.BOOTSTRAP_ITERATIONS
    assert reading["hypotheses"]["H1"]["status"] == "APPROVED"
    assert reading["joint_approval"] is False


def test_defined_replica_boundary_9000_vs_8999() -> None:
    rows = _rows(20, 14, 6, 0, 0, 60.0)
    rows[0]["upper_c"], rows[0]["lower_c"] = 3, 7  # controls only on session 1
    stats = est.cohort_from_sessions(rows, 20)
    for defined, expected in ((9_000, "NOT_APPROVED"), (8_999, "NOT_ESTIMABLE")):
        weights = np.zeros((est.BOOTSTRAP_ITERATIONS, 20), dtype=np.int32)
        weights[:, 1] = 20  # every replica has E resolved
        weights[:defined, 0] = 1  # exactly `defined` replicas see the control session
        r1 = est.read_cohort(stats, weights)["hypotheses"]["R1"]
        assert r1["defined_replicas"] == defined
        assert r1["status"] == expected


def test_zero_portfolio_episodes_and_pending_pnl() -> None:
    rows = _rows(20, 14, 6, 6, 14, 0.0)
    for row in rows:
        row["pnl_count"] = 0
    reading = est.read_cohort(est.cohort_from_sessions(rows, 20))
    assert reading["hypotheses"]["H3"]["status"] == "NOT_ESTIMABLE"
    assert reading["hypotheses"]["H3"]["lcb_is_minus_infinity"] is True
    assert reading["hypotheses"]["H3"]["lcb_one_sided"] is None
    pending = est.read_cohort(est.cohort_from_sessions(_rows(20, 14, 6, 6, 14, 60.0), 20, indeterminate_pnl=1))
    assert pending["data_gate"]["open"] is False
    assert all(h["status"] == "DATA_GATE_BLOCKED" and "DATA_GATE_BLOCKED" in h["reasons"] for h in pending["hypotheses"].values())
    assert pending["joint_approval"] is False


def test_unobservable_episodes_block_the_gate_in_either_arm() -> None:
    for gate in ({"unobservable_e": 1}, {"unobservable_c": 1}):
        reading = est.read_cohort(est.cohort_from_sessions(_rows(20, 14, 6, 6, 14, 60.0), 20, **gate))
        assert reading["joint_approval"] is False
        assert reading["data_gate"]["open"] is False


def test_h3_minus_infinity_when_portfolio_episodes_are_sparse() -> None:
    rows = _rows(20, 14, 6, 6, 14, 60.0)
    for row in rows[1:]:
        row["pnl_count"], row["pnl_sum_usd"] = 0, 0.0
    h3 = est.read_cohort(est.cohort_from_sessions(rows, 20))["hypotheses"]["H3"]
    assert h3["status"] == "NOT_ESTIMABLE" and h3["lcb_is_minus_infinity"] is True
    assert h3["defined_replicas"] < est.MIN_DEFINED_REPLICAS


def test_immature_cohort_is_refused() -> None:
    stats = est.cohort_from_sessions(_rows(20, 14, 6, 6, 14, 60.0), 20)
    with pytest.raises(est.EstimatorError, match="COHORT_NOT_MATURE"):
        est.read_cohort(stats, sessions_completed=28)
    assert est.read_cohort(stats, sessions_completed=29)["sessions_completed"] == 29


def test_swapping_arms_negates_r1_replicas_under_common_draws() -> None:
    stats = est.cohort_from_sessions(_rows(20, 14, 6, 6, 14, 60.0), 20)
    weights = est.circular_block_weights(20)
    base = est.bootstrap_replicas(stats, weights)
    swapped = est.bootstrap_replicas(stats.swapped_arms(), weights)
    assert np.allclose(base["vectors"]["R1"], -swapped["vectors"]["R1"])
    assert base["point"]["R1"] == pytest.approx(-swapped["point"]["R1"])


# ---------------------------------------------------------------- certification sequence (§4, §7)

def test_certify_stops_at_20_or_reads_30_once_without_partial_go() -> None:
    strong = _rows(30, 14, 6, 6, 14, 60.0)
    result = est.certify({20: est.cohort_from_sessions(strong, 20), 30: est.cohort_from_sessions(strong, 30)})
    assert result["state"] == est.STATE_CERTIFIED and result["certified_at_cohort"] == 20
    assert result["readings_executed"] == [20]
    weak = _rows(30, 10, 10, 10, 10, 0.0)
    result = est.certify({20: est.cohort_from_sessions(weak, 20)})
    assert result["state"] == est.STATE_CONTINUE and result["certified_at_cohort"] is None
    result = est.certify({20: est.cohort_from_sessions(weak, 20), 30: est.cohort_from_sessions(weak, 30)})
    assert result["state"] == est.STATE_FAILED and result["certified_at_cohort"] is None
    assert result["readings_executed"] == [20, 30]
    assert set(result["reasons"]) == {"V2_CERTIFICATION_FAILED_R1", "V2_CERTIFICATION_FAILED_H1", "V2_CERTIFICATION_FAILED_H3"}
    assert result["promotion_authorized"] is False and result["third_reading_allowed"] is False


def test_certify_reports_not_estimable_and_gate_states() -> None:
    rows = _rows(30, 14, 6, 0, 0, 60.0)
    result = est.certify({20: est.cohort_from_sessions(rows, 20), 30: est.cohort_from_sessions(rows, 30)})
    assert result["state"] == est.STATE_NOT_ESTIMABLE
    assert result["reasons"] == ["V2_CERTIFICATION_NOT_ESTIMABLE:R1"]
    strong = _rows(30, 14, 6, 6, 14, 60.0)
    result = est.certify({20: est.cohort_from_sessions(strong, 20, unobservable_e=2), 30: est.cohort_from_sessions(strong, 30, unobservable_e=2)})
    assert result["state"] == est.STATE_GATE_BLOCKED
    assert result["reasons"] == ["V2_DATA_GATE_BLOCKED:R1,H1,H3"]


def test_only_cohorts_20_and_30_exist() -> None:
    with pytest.raises(est.EstimatorError, match="COHORT_SIZE"):
        est.cohort_from_sessions(_rows(25, 1, 1, 1, 1, 0.0), 25)
    with pytest.raises(est.EstimatorError, match="UNKNOWN_COHORT"):
        est.certify({20: est.cohort_from_sessions(_rows(20, 1, 1, 1, 1, 0.0), 20), 40: object()})  # type: ignore[dict-item]


# ---------------------------------------------------------------- calibration design (annex B + closure)

def test_scenario_matrix_has_28_scenarios_and_121_metrics() -> None:
    scenarios = cal.scenario_matrix()
    assert len(scenarios) == 28
    assert [s.scenario_id for s in scenarios][-4:] == ["D2_S1", "D2_S2", "D2_S3", "D2_S4"]
    marginal = sum(2 * sum(s.nulls.values()) for s in scenarios)
    families = sum(1 for s in scenarios if any(s.nulls.values()))
    assert marginal == 96 and families == 25 and marginal + families == cal.K_METRICS


def test_external_seed_is_sha256_big_endian_of_16_bytes() -> None:
    import hashlib
    digest = hashlib.sha256(b"C3PO-V2-CAL-1|D0_000|0").digest()
    assert cal.external_seed("D0_000", 0) == int.from_bytes(digest[:16], "big")
    assert cal.external_seed("D0_000", 0) != cal.external_seed("D0_000", 1)


def test_simulation_is_reproducible_and_marginals_match_truth() -> None:
    scenario = cal.scenario_by_id("D1_110")
    rows_a = cal.simulate_repetition(scenario, 7)
    rows_b = cal.simulate_repetition(scenario, 7)
    assert rows_a == rows_b and len(rows_a) == 30
    for row in rows_a:
        assert row["upper_e"] + row["lower_e"] + row["ambiguous_e"] + row["time_event_e"] == cal.NAMES_PER_ARM
        assert row["upper_c"] + row["lower_c"] + row["ambiguous_c"] + row["time_event_c"] == cal.NAMES_PER_ARM
        assert row["pnl_count"] == 1 and row["unobservable_e"] == 0 and row["unobservable_c"] == 0
    # pooled over many iid repetitions (D0: no common factor, so the Monte Carlo error is tiny),
    # p among resolved is p_g, the mean P&L is mu and the resolution rate is 0.8
    iid = cal.scenario_by_id("D0_110")
    up = low = res = 0
    pnl = []
    for r in range(60):
        for row in cal.simulate_repetition(iid, r):
            up += row["upper_e"]; low += row["lower_e"]; res += row["upper_e"] + row["lower_e"]
            pnl.append(row["pnl_sum_usd"])
    assert up / (up + low) == pytest.approx(0.6, abs=0.015)  # 28,800 resolved draws: SE ~ 0.003
    assert res / (60 * 30 * cal.NAMES_PER_ARM) == pytest.approx(0.8, abs=0.01)
    assert np.mean(pnl) == pytest.approx(0.0, abs=12.0)  # mu = 0 in mask 110; sigma 100 over 1,800 draws


def test_stress_scenarios_follow_the_closure() -> None:
    s2 = cal.simulate_repetition(cal.scenario_by_id("D2_S2"), 0)
    controls = [row["upper_c"] + row["lower_c"] + row["ambiguous_c"] + row["time_event_c"] for row in s2]
    assert controls == [2 if (t + 1) % 10 == 0 else 0 for t in range(30)]
    s3 = cal.simulate_repetition(cal.scenario_by_id("D2_S3"), 0)
    resolved_e = sum(row["upper_e"] + row["lower_e"] for row in s3) / (30 * cal.NAMES_PER_ARM)
    resolved_c = sum(row["upper_c"] + row["lower_c"] for row in s3) / (30 * cal.NAMES_PER_ARM)
    assert 0.1 < resolved_e < 0.3 and 0.8 < resolved_c < 1.0
    s4 = cal.scenario_by_id("D2_S4")
    assert s4.heavy_tail_h3 and s4.nulls == {"R1": True, "H1": True, "H3": True}
    s1 = cal.scenario_by_id("D2_S1")
    assert s1.truth == {"R1": pytest.approx(-0.2), "H1": 0.4, "H3": -20.0}


def test_h3_normal_case_uses_minus_u_of_e01() -> None:
    scenario = cal.scenario_by_id("D0_000")
    rows = cal.simulate_repetition(scenario, 3)
    # with rho = kappa = 0 and threshold 0, an E01 upper (U <= 0) implies V = -U >= 0 and P&L >= 0 when E01 resolved
    # cannot see E01 individually from aggregates; check the sign relation on the pooled correlation instead
    corr_num = 0.0
    for r in range(40):
        for row in cal.simulate_repetition(scenario, r):
            corr_num += (row["upper_e"] - row["lower_e"]) * row["pnl_sum_usd"]
    assert corr_num > 0.0


def test_clopper_pearson_upper_bound_matches_binom_test_convention() -> None:
    assert cal.clopper_pearson_upper(0, 100, 0.95) == pytest.approx(1 - 0.05 ** (1 / 100), rel=1e-6)
    assert cal.clopper_pearson_upper(100, 100, 0.95) == 1.0
    # x = 3, n = 50, 97.5% one-sided upper (R binom.test conf.int upper at 95% two-sided) = 0.1653
    assert cal.clopper_pearson_upper(3, 50, 0.975) == pytest.approx(0.16529, abs=2e-4)


def test_chunks_merge_deterministically() -> None:
    whole = cal.run_chunk("D0_000", 0, 6)
    parts = cal.merge_counters([cal.run_chunk("D0_000", 0, 2), cal.run_chunk("D0_000", 2, 6)])
    assert whole == parts and whole["repetitions"] == 6


def test_small_calibration_run_produces_report_shape() -> None:
    report = cal.run_calibration(repetitions=4, scenario_ids=["D0_000", "D0_111"], chunk=3, adverse_repetitions=2)
    assert report["scenario_count"] == 2 and report["k_metrics_declared"] == 121
    null_scenario = next(r for r in report["scenarios"] if r["scenario_id"] == "D0_000")
    assert set(null_scenario["marginal_false_go"]) == {"R1@20", "R1@30", "H1@20", "H1@30", "H3@20", "H3@30"}
    assert null_scenario["fwer"] is not None and null_scenario["repetitions"] == 4
    alt = next(r for r in report["scenarios"] if r["scenario_id"] == "D0_111")
    assert alt["marginal_false_go"] == {} and alt["fwer"] is None and alt["all_error_checks_pass"] is None
    assert report["acceptance"]["full_matrix"] is False and report["acceptance"]["certifying_run"] is False
    assert report["adverse_missingness_check"]["pass"] is True
    assert len(report["code"]["estimator_sha256"]) == 64
    with pytest.raises(KeyError):
        cal.run_calibration(repetitions=1, scenario_ids=["D9_000"])


def test_adverse_missingness_gate_blocks_every_repetition() -> None:
    trial = cal.adverse_missingness_trial(3)
    assert trial["pass"] is True and trial["gate_blocked"] == 3
    assert trial["hidden_episodes_total"] > 0
    assert "naive_without_gate_diagnostic" in trial
