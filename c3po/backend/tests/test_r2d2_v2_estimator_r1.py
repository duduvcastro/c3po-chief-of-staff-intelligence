from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest

from app import r2d2_v2_calibration_r1 as cal
from app import r2d2_v2_estimator_r1 as est
from app.r2d2_v2_estimator import EstimatorError


def _rows(n: int, upper_e: int, lower_e: int, upper_c: int, lower_c: int, pnl: float) -> list[dict]:
    return [{"upper_e": upper_e, "lower_e": lower_e, "upper_c": upper_c, "lower_c": lower_c,
             "pnl_sum_usd": pnl, "pnl_count": 1, "unobservable_e": 0, "unobservable_c": 0, "indeterminate_pnl": 0}
            for _ in range(n)]


def _noisy(n: int, seed: int, delta: float = 0.0) -> list[dict]:
    """Session counts with variation between batches so that s > 0."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        ue = int(rng.binomial(16, 0.5 + delta)); uc = int(rng.binomial(16, 0.5))
        rows.append({"upper_e": ue, "lower_e": 16 - ue, "upper_c": uc, "lower_c": 16 - uc,
                     "pnl_sum_usd": float(rng.normal(0, 100)), "pnl_count": 1,
                     "unobservable_e": 0, "unobservable_c": 0, "indeterminate_pnl": 0})
    return rows


# ---------------------------------------------------------------- exact Student t

def test_student_t_quantiles_match_independent_values() -> None:
    assert est.student_t_quantile(3, 1 - 1 / 120) == pytest.approx(4.856657272769, abs=2e-9)  # Codex, 5562202789
    assert est.student_t_quantile(5, 1 - 1 / 120) == pytest.approx(3.534110704058, abs=2e-9)
    assert est.student_t_quantile(3, 0.975) == pytest.approx(3.182446305284, abs=1e-9)  # tables
    assert est.student_t_quantile(5, 0.975) == pytest.approx(2.570581835636, abs=1e-9)
    assert est.student_t_quantile(1, 0.95) == pytest.approx(6.313751514675, abs=1e-8)
    assert est.student_t_quantile(10, 0.99) == pytest.approx(2.763769457447, abs=1e-9)
    assert est.student_t_cdf(0.0, 7) == pytest.approx(0.5)
    assert est.student_t_cdf(-2.0, 4) == pytest.approx(1 - est.student_t_cdf(2.0, 4))
    with pytest.raises(EstimatorError, match="T_QUANTILE_INPUT"):
        est.student_t_quantile(3, 0.3)
    with pytest.raises(EstimatorError, match="T_DF_INVALID"):
        est.student_t_cdf(1.0, 0)


def test_maturation_49_and_69() -> None:
    assert est.maturation_session(40) == 49 and est.maturation_session(60) == 69


# ---------------------------------------------------------------- batches, estimand, decision

def test_batches_are_contiguous_calendar_blocks_with_equal_weights() -> None:
    rows = _rows(40, 10, 10, 10, 10, 0.0)
    rows[0].update(upper_e=20, lower_e=0)  # batch 1: p_E = 110/200
    for row in rows[10:20]:
        row.update(upper_e=1, lower_e=1)  # batch 2: p_E = 10/20 with a small denominator
    stats = est.cohort_from_sessions(rows, 40)
    batches = est.batch_statistics(stats)
    assert [b["sessions"] for b in batches] == [[1, 10], [11, 20], [21, 30], [31, 40]]
    assert batches[0]["upper_e"] == 110 and batches[0]["lower_e"] == 90 and batches[1]["upper_e"] == 10
    reading = est.read_cohort(stats)
    # equal batch weights: mean of the four contrasts (0.05, 0, 0, 0) = 0.0125;
    # the pooled contrast weights by denominators: 320/620 - 0.5 = 0.0161...
    assert reading["r1"]["point"] == pytest.approx(0.0125)
    assert reading["descriptive"]["pooled_contrast"] == pytest.approx(320 / 620 - 0.5)
    assert reading["r1"]["point"] != pytest.approx(reading["descriptive"]["pooled_contrast"])


def test_degenerate_null_cohort_is_not_approved_and_lcb_is_published() -> None:
    reading = est.read_cohort(est.cohort_from_sessions(_rows(40, 10, 10, 10, 10, 0.0), 40))
    r1 = reading["r1"]
    assert r1["status"] == "NOT_APPROVED" and r1["reasons"] == ["LCB_NOT_ABOVE_THRESHOLD"]
    assert r1["point"] == 0.0 and r1["lcb_one_sided"] == 0.0 and r1["sd_batches"] == 0.0
    assert reading["approved"] is False


def test_strong_contrast_is_approved_with_t3_and_t5() -> None:
    for n, df in ((40, 3), (60, 5)):
        reading = est.read_cohort(est.cohort_from_sessions(_noisy(n, 1, delta=0.2), n), sessions_completed=n + 9)
        r1 = reading["r1"]
        assert r1["k"] == n // 10 and r1["t_quantile"] == pytest.approx(est.student_t_quantile(df, 1 - 1 / 120))
        assert r1["status"] == "APPROVED" and reading["approved"] is True
        assert r1["lcb_one_sided"] == pytest.approx(r1["point"] - r1["t_quantile"] * r1["sd_batches"] / math.sqrt(r1["k"]))
        assert reading["go_scope"].startswith("Filter discrimination")


def test_batch_without_denominator_is_not_estimable_without_imputation_or_dropping() -> None:
    rows = _noisy(40, 2, delta=0.3)
    for row in rows[10:20]:  # batch 2 has no controls at all
        row.update(upper_c=0, lower_c=0)
    reading = est.read_cohort(est.cohort_from_sessions(rows, 40))
    r1 = reading["r1"]
    assert r1["status"] == "NOT_ESTIMABLE" and r1["reasons"] == ["NOT_ESTIMABLE_BATCH_DENOMINATOR"]
    assert r1["batches_without_denominator"] == [2] and r1["estimability_event_holds"] is False
    assert r1["point"] is None and r1["lcb_one_sided"] is None
    assert reading["batches"][1]["d"] is None and len(reading["batches"]) == 4  # batch kept, not dropped, not zero
    assert reading["approved"] is False
    # a single control anywhere in the batch restores the denominator (one resolved episode)
    rows[15].update(upper_c=0, lower_c=1)
    assert est.read_cohort(est.cohort_from_sessions(rows, 40))["r1"]["estimability_event_holds"] is True


def test_data_gate_blocks_approval_and_is_aggregated_within_prefix() -> None:
    rows = _noisy(60, 3, delta=0.3)
    rows[45]["unobservable_c"] = 1  # only in sessions 41-60
    c40, c60 = est.cohort_from_sessions(rows, 40), est.cohort_from_sessions(rows, 60)
    assert c40.data_gate_open() and not c60.data_gate_open()
    reading = est.read_cohort(c60)
    assert reading["r1"]["status"] == "DATA_GATE_BLOCKED" and "DATA_GATE_BLOCKED" in reading["r1"]["reasons"]
    pending = _noisy(40, 4, delta=0.3)
    pending[0]["indeterminate_pnl"] = 2
    assert est.read_cohort(est.cohort_from_sessions(pending, 40))["r1"]["status"] == "DATA_GATE_BLOCKED"


def test_descriptive_h1_h3_never_decide() -> None:
    reading = est.read_cohort(est.cohort_from_sessions(_noisy(40, 5, delta=0.3), 40))
    assert reading["descriptive"]["h1"]["decisive"] is False and reading["descriptive"]["h3"]["decisive"] is False
    assert reading["descriptive"]["h1"]["mean"] > 0.5 and len(reading["descriptive"]["h3"]["interval_95"]) == 2
    rows = _noisy(40, 6, delta=0.3)
    for row in rows[:10]:
        row.update(pnl_count=0, pnl_sum_usd=0.0)
    reading = est.read_cohort(est.cohort_from_sessions(rows, 40))
    assert reading["descriptive"]["h3"]["point"] is None and reading["r1"]["status"] == "APPROVED"


def test_swapping_arms_negates_the_batch_estimate() -> None:
    stats = est.cohort_from_sessions(_noisy(40, 7, delta=0.2), 40)
    base, swapped = est.read_cohort(stats)["r1"], est.read_cohort(stats.swapped_arms())["r1"]
    assert base["point"] == pytest.approx(-swapped["point"]) and base["sd_batches"] == pytest.approx(swapped["sd_batches"])


def test_immature_cohort_and_input_discipline() -> None:
    stats = est.cohort_from_sessions(_rows(40, 8, 8, 8, 8, 1.0), 40)
    with pytest.raises(EstimatorError, match="COHORT_NOT_MATURE"):
        est.read_cohort(stats, sessions_completed=48)
    assert est.read_cohort(stats, sessions_completed=49)["sessions_completed"] == 49
    with pytest.raises(EstimatorError, match="COHORT_SIZE"):
        est.cohort_from_sessions(_rows(50, 1, 1, 1, 1, 0.0), 50)
    rows = _rows(40, 8, 8, 8, 8, 1.0)
    del rows[3]["lower_c"]
    with pytest.raises(EstimatorError, match="MISSING_FIELD"):
        est.cohort_from_sessions(rows, 40)
    rows = _rows(40, 8, 8, 8, 8, 1.0)
    rows[3]["unobservable_e"] = 0.9
    with pytest.raises(EstimatorError, match="INVALID_COUNT_TYPE"):
        est.cohort_from_sessions(rows, 40)
    rows = _rows(40, 8, 8, 8, 8, 1.0)
    rows[3]["pnl_sum_usd"] = float("nan")
    with pytest.raises(EstimatorError, match="PNL_NOT_FINITE"):
        est.cohort_from_sessions(rows, 40)


# ---------------------------------------------------------------- certification sequence

def test_certify_sequence_states_and_checks() -> None:
    strong = _noisy(60, 11, delta=0.3)
    result = est.certify({40: est.cohort_from_sessions(strong, 40), 60: est.cohort_from_sessions(strong, 60)}, sessions_completed=69)
    assert result["state"] == est.STATE_CERTIFIED and result["certified_at_cohort"] == 40 and result["readings_executed"] == [40]
    assert result["promotion_authorized"] is False and result["third_reading_allowed"] is False
    weak = _noisy(60, 12, delta=0.0)
    result = est.certify({40: est.cohort_from_sessions(weak, 40)}, sessions_completed=49)
    assert result["state"] == est.STATE_CONTINUE
    result = est.certify({40: est.cohort_from_sessions(weak, 40), 60: est.cohort_from_sessions(weak, 60)}, sessions_completed=69)
    assert result["state"] == est.STATE_FAILED and result["readings_executed"] == [40, 60] and result["reasons"] == ["LCB_NOT_ABOVE_THRESHOLD"]
    sparse = _noisy(60, 13, delta=0.0)
    for row in sparse[50:60]:
        row.update(upper_c=0, lower_c=0)
    result = est.certify({40: est.cohort_from_sessions(sparse, 40), 60: est.cohort_from_sessions(sparse, 60)}, sessions_completed=69)
    assert result["state"] == est.STATE_NOT_ESTIMABLE
    gated = _noisy(60, 14, delta=0.0)
    gated[0]["unobservable_e"] = 1
    result = est.certify({40: est.cohort_from_sessions(gated, 40), 60: est.cohort_from_sessions(gated, 60)}, sessions_completed=69)
    assert result["state"] == est.STATE_GATE_BLOCKED
    c40, c60 = est.cohort_from_sessions(strong, 40), est.cohort_from_sessions(strong, 60)
    with pytest.raises(EstimatorError, match="SESSIONS_COMPLETED_REQUIRED"):
        est.certify({40: c40}, sessions_completed=None)  # type: ignore[arg-type]
    with pytest.raises(EstimatorError, match="COHORT_NOT_MATURE"):
        est.certify({40: c40}, sessions_completed=48)
    with pytest.raises(EstimatorError, match="COHORT_NOT_MATURE"):  # not approved at 40 -> reading 60 needs session 69
        est.certify({40: est.cohort_from_sessions(weak, 40), 60: est.cohort_from_sessions(weak, 60)}, sessions_completed=68)
    with pytest.raises(EstimatorError, match="COHORT_KEY_MISMATCH"):
        est.certify({40: c60}, sessions_completed=69)
    other = _noisy(60, 11, delta=0.3)
    other[0]["upper_e"] = (other[0]["upper_e"] + 1) % 17
    with pytest.raises(EstimatorError, match="COHORT_PREFIX_MISMATCH"):
        est.certify({40: c40, 60: est.cohort_from_sessions(other, 60)}, sessions_completed=69)
    with pytest.raises(EstimatorError, match="UNKNOWN_COHORT"):
        est.certify({40: c40, 20: c40}, sessions_completed=69)


# ---------------------------------------------------------------- calibration rev 2 (annex B rev 2)

def test_frozen_matrix_and_k_27() -> None:
    assert list(cal.FROZEN_SCENARIO_IDS) == ["D0_000", "D1_000", "D2_000", "D0_100", "D1_100", "D2_100",
                                             "D2_S1", "D2_S2", "D2_S3", "D2_S5", "D2_S6", "D2_S7"]
    assert list(cal.NULL_SCENARIO_IDS) == ["D0_000", "D1_000", "D2_000", "D2_S1", "D2_S2", "D2_S3", "D2_S5", "D2_S6", "D2_S7"]
    assert 3 * len(cal.NULL_SCENARIO_IDS) == cal.K_METRICS == 27
    assert cal.scenario_by_id("D2_S7").truth == pytest.approx(-0.05)
    with pytest.raises(KeyError):
        cal.scenario_by_id("D2_S4")


def test_cal2_seed_rule() -> None:
    digest = hashlib.sha256(b"C3PO-V2-CAL-2|D2_S5|17").digest()
    assert cal.external_seed("D2_S5", 17) == int.from_bytes(digest[:16], "big")
    assert cal.PROTOCOL_ID == "C3PO-V2-CAL-2"


def test_trajectory_shape_and_draw_order() -> None:
    rows = cal.simulate_repetition(cal.scenario_by_id("D2_000"), 0)
    assert len(rows) == 60 and cal.SESSIONS_TRAJECTORY == 69
    for row in rows:
        assert all(key in row for key in est.SESSION_FIELDS)
        assert row["upper_e"] + row["lower_e"] + row["ambiguous_e"] + row["time_event_e"] == row["names_e"] == 20
        assert row["pnl_count"] == 1 and not row["empty_session"]
    assert cal.simulate_repetition(cal.scenario_by_id("D2_000"), 0) == rows
    # S5 draws come after every other draw: outcomes of the first n names coincide with the full-name scenario
    s5 = cal.simulate_repetition(cal.scenario_by_id("D2_S5"), 0)
    assert any(row["names_e"] != 20 or row["names_c"] != 20 for row in s5)
    assert all(2 <= row["names_e"] <= 20 and 2 <= row["names_c"] <= 20 for row in s5)
    s6 = cal.simulate_repetition(cal.scenario_by_id("D2_S6"), 0)
    empties = [row for row in s6 if row["empty_session"]]
    assert 3 <= len(empties) <= 25 and all(row["upper_e"] + row["lower_e"] + row["upper_c"] + row["lower_c"] == 0 and row["pnl_count"] == 0 for row in empties)
    s2 = cal.simulate_repetition(cal.scenario_by_id("D2_S2"), 0)
    assert [row["names_c"] for row in s2] == [2 if (t + 1) % 10 == 0 else 0 for t in range(60)]


def test_iid_marginals_match_truth() -> None:
    iid = cal.scenario_by_id("D0_100")
    up = low = 0
    for r in range(30):
        for row in cal.simulate_repetition(iid, r):
            up += row["upper_e"]; low += row["lower_e"]
    assert up / (up + low) == pytest.approx(0.6, abs=0.015)  # 28,800 resolved draws


def test_procedure_reads_both_cohorts_mature_and_chunks_merge() -> None:
    readings = cal.run_procedure(cal.simulate_repetition(cal.scenario_by_id("D0_000"), 1))
    assert all(reading["sessions_completed"] == 69 for reading in readings.values())
    whole = cal.run_chunk("D0_000", 0, 6)
    parts = cal.merge_counters([cal.run_chunk("D0_000", 0, 2), cal.run_chunk("D0_000", 2, 6)])
    assert whole == parts and whole["repetitions"] == 6


def test_small_run_report_shape_and_certifying_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    report = cal.run_calibration(repetitions=3, scenario_ids=["D0_000", "D0_100"], chunk=2, adverse_repetitions=2)
    null_scenario = next(r for r in report["scenarios"] if r["scenario_id"] == "D0_000")
    assert set(null_scenario["error_metrics"]) == {"false_go@40", "false_go@60", "sequence"}
    alt = next(r for r in report["scenarios"] if r["scenario_id"] == "D0_100")
    assert alt["error_metrics"] is None and alt["all_error_checks_pass"] is None
    assert report["acceptance"]["full_matrix"] is False and report["acceptance"]["certifying_run"] is False
    assert report["adverse_missingness_check"]["pass"] is True
    assert report["method"]["t_quantiles"]["df3"] == pytest.approx(4.856657272769, abs=2e-9)
    with pytest.raises(KeyError):
        cal.run_calibration(repetitions=1, scenario_ids=["D2_S4"])

    def stub(scenario_id: str, start: int, stop: int) -> dict[str, int]:
        counters = cal._empty_counters()
        counters["repetitions"] = stop - start
        return counters

    monkeypatch.setattr(cal, "run_chunk", stub)
    for reps, expected in ((50_000, True), (50_001, False), (49_999, False)):
        report = cal.run_calibration(repetitions=reps, chunk=reps)
        assert report["scenario_count"] == 12 and report["k_metrics_observed"] == 27
        assert report["acceptance"]["full_matrix"] is expected
        assert report["acceptance"]["k_matches_declared"] is (True if expected else None)
        assert report["acceptance"]["certifying_run"] is False  # no adverse check in this stubbed run
    report = cal.run_calibration(repetitions=50_000, chunk=50_000, scenario_ids=list(cal.FROZEN_SCENARIO_IDS)[:11])
    assert report["acceptance"]["full_matrix"] is False and report["frozen_list_used"] is False


def test_adverse_gate_blocks_exactly_the_prefixes_with_hidden_episodes() -> None:
    trial = cal.adverse_missingness_trial(3)
    assert trial["pass"] is True and trial["gate_blocked_by_reading"] == {40: 3, 60: 3}
    late = cal.adverse_missingness_trial(4, hide_sessions=range(40, 60))
    assert late["pass"] is True and late["gate_blocked_by_reading"][40] == 0
    assert late["readings_executed"][60] >= 1 and late["gate_blocked_by_reading"][60] == late["readings_executed"][60]
