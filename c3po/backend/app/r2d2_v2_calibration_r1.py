"""R2D2 V2 — EMENDA 1 calibration (annex B rev 2): the batch-means R1 procedure on layer-A truth.

Contract: EMENDA 1 rev 2 §5 (sha256 3a25b992…). Protocol C3PO-V2-CAL-2; external seed per
(scenario, repetition r) = big-endian integer of the first 16 bytes of
SHA-256("C3PO-V2-CAL-2|<scenario_id>|<r>"), r = 0..M-1, in numpy.random.default_rng
(PCG64). Trajectories of 69 sessions (entries 1..60, observation to 69). Same
layer-A generator as the signed closure (Z moving sum of 10, stationary AR(1)
phi = 0.8, U marginal N(0,1), resolution 0.8 with 0.75/0.25 split, 20 names per
arm; H3 descriptive uses E01 with V_t = -U_E01,t). Fixed order of external draws
per repetition: eps, A, W_E, W_C, eta_E, eta_C, resolution E, resolution C,
ambiguous E, ambiguous C, then (S5 only) names per session n_E,t and n_C,t ~
discrete uniform {2..20} for t = 1..60, E first then C, then (S6 only) the empty
session indicator ~ Bernoulli(0.2) per scheduled session t = 1..60. Scenarios
without S5/S6 do not consume those draws.

Frozen scenario list (12): D0_000, D1_000, D2_000 (boundary nulls), D0_100,
D1_100, D2_100 (delta = +0.10), D2_S1 (0.4/0.6), D2_S2 (two controls only on
sessions divisible by 10), D2_S3 (resolution 0.2/0.9), D2_S5 (unequal
denominators), D2_S6 (empty sessions), D2_S7 (0.45/0.5, interior null).
Error metrics K = 27: for each of the 9 null scenarios, false GO at reading 40,
false GO at reading 60 (denominator = all repetitions) and sequence error (false
GO in any executed reading). Clopper-Pearson one-sided upper bounds at
confidence 1 - 0.01/27; acceptance requires upper <= 1/120 per reading and
upper <= 2/120 for the sequence in every null scenario. Power, estimability
P(A_n), coverage and stopping are published, never as criteria. Only exactly
M = 50,000 with the frozen list and the adverse gate check is a certifying run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from statistics import NormalDist
from typing import Callable, Iterable

import numpy as np

from . import r2d2_v2_estimator_r1 as est
from .r2d2_v2_calibration import STRUCTURES, EXTERNAL_RNG, _ar1, _rate, _source_sha256, clopper_pearson_upper

PROTOCOL_ID = "C3PO-V2-CAL-2"
SIGMA_USD = 100.0
NAMES_PER_ARM = 20
SESSIONS_ENTRY = 60
SESSIONS_TRAJECTORY = 69
READINGS = (40, 60)
MC_CONFIDENCE_ERROR = 0.01
K_METRICS = 27
PER_READING_LIMIT = 1.0 / 120.0
SEQUENCE_LIMIT = 2.0 / 120.0
CERTIFYING_REPETITIONS = 50_000
DEFAULT_REPETITIONS = CERTIFYING_REPETITIONS
RESOLUTION_DEFAULT = 0.8
AMBIGUOUS_CONDITIONAL = 0.25
UNEQUAL_NAMES_LOW, UNEQUAL_NAMES_HIGH = 2, 20
EMPTY_SESSION_PROBABILITY = 0.2
ADVERSE_HIDE_LOWER = 0.25
ADVERSE_HIDE_UPPER = 0.0


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    structure: str
    p_e: float
    p_c: float
    resolution_e: float = RESOLUTION_DEFAULT
    resolution_c: float = RESOLUTION_DEFAULT
    controls_only_every_10th: bool = False
    unequal_denominators: bool = False
    empty_sessions: bool = False

    @property
    def truth(self) -> float:
        return self.p_e - self.p_c

    @property
    def null(self) -> bool:
        return self.truth <= 0.0

    def describe(self) -> dict:
        rho, kappa, w, phi = STRUCTURES[self.structure]
        return {"scenario_id": self.scenario_id, "structure": self.structure, "rho": rho, "kappa": kappa, "w": w, "phi": phi,
                "p_e": self.p_e, "p_c": self.p_c, "resolution_e": self.resolution_e, "resolution_c": self.resolution_c,
                "controls_only_every_10th": self.controls_only_every_10th, "unequal_denominators": self.unequal_denominators,
                "empty_sessions": self.empty_sessions, "truth_r1": self.truth, "null": self.null}


FROZEN_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("D0_000", "D0", 0.5, 0.5), Scenario("D1_000", "D1", 0.5, 0.5), Scenario("D2_000", "D2", 0.5, 0.5),
    Scenario("D0_100", "D0", 0.6, 0.5), Scenario("D1_100", "D1", 0.6, 0.5), Scenario("D2_100", "D2", 0.6, 0.5),
    Scenario("D2_S1", "D2", 0.4, 0.6),
    Scenario("D2_S2", "D2", 0.5, 0.5, controls_only_every_10th=True),
    Scenario("D2_S3", "D2", 0.5, 0.5, resolution_e=0.2, resolution_c=0.9),
    Scenario("D2_S5", "D2", 0.5, 0.5, unequal_denominators=True),
    Scenario("D2_S6", "D2", 0.5, 0.5, empty_sessions=True),
    Scenario("D2_S7", "D2", 0.45, 0.5),
)
FROZEN_SCENARIO_IDS = tuple(s.scenario_id for s in FROZEN_SCENARIOS)
NULL_SCENARIO_IDS = tuple(s.scenario_id for s in FROZEN_SCENARIOS if s.null)
assert len(FROZEN_SCENARIOS) == 12 and 3 * len(NULL_SCENARIO_IDS) == K_METRICS, "frozen list disagrees with K = 27"


def scenario_by_id(scenario_id: str) -> Scenario:
    for scenario in FROZEN_SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def external_seed(scenario_id: str, repetition: int) -> int:
    digest = hashlib.sha256(f"{PROTOCOL_ID}|{scenario_id}|{repetition}".encode("utf-8")).digest()
    return int.from_bytes(digest[:16], "big")


def simulate_repetition(scenario: Scenario, repetition: int) -> list[dict]:
    """One trajectory: 60 scheduled entry sessions, observation to 69; nine explicit fields per row."""
    rho, kappa, w, phi = STRUCTURES[scenario.structure]
    rng = np.random.default_rng(external_seed(scenario.scenario_id, repetition))
    eps = rng.standard_normal(SESSIONS_TRAJECTORY + 9)
    z = np.convolve(eps, np.ones(10), mode="valid") / math.sqrt(10.0)
    a = _ar1(rng, phi, (SESSIONS_TRAJECTORY,)) if w < 1.0 else np.zeros(SESSIONS_TRAJECTORY)
    x = math.sqrt(w) * z + math.sqrt(1.0 - w) * a
    if kappa > 0.0:
        w_e = _ar1(rng, phi, (NAMES_PER_ARM, SESSIONS_TRAJECTORY))
        w_c = _ar1(rng, phi, (NAMES_PER_ARM, SESSIONS_TRAJECTORY))
    else:
        w_e = w_c = np.zeros((NAMES_PER_ARM, SESSIONS_TRAJECTORY))
    idio = math.sqrt(max(0.0, 1.0 - rho - kappa))
    eta_e = rng.standard_normal((NAMES_PER_ARM, SESSIONS_TRAJECTORY))
    eta_c = rng.standard_normal((NAMES_PER_ARM, SESSIONS_TRAJECTORY))
    u_e = math.sqrt(rho) * x + math.sqrt(kappa) * w_e + idio * eta_e
    u_c = math.sqrt(rho) * x + math.sqrt(kappa) * w_c + idio * eta_c
    thr_e, thr_c = NormalDist().inv_cdf(scenario.p_e), NormalDist().inv_cdf(scenario.p_c)
    resolved_e = rng.random((NAMES_PER_ARM, SESSIONS_TRAJECTORY)) < scenario.resolution_e
    resolved_c = rng.random((NAMES_PER_ARM, SESSIONS_TRAJECTORY)) < scenario.resolution_c
    ambiguous_e = rng.random((NAMES_PER_ARM, SESSIONS_TRAJECTORY)) < AMBIGUOUS_CONDITIONAL
    ambiguous_c = rng.random((NAMES_PER_ARM, SESSIONS_TRAJECTORY)) < AMBIGUOUS_CONDITIONAL
    names_e = np.full(SESSIONS_ENTRY, NAMES_PER_ARM)
    names_c = np.full(SESSIONS_ENTRY, NAMES_PER_ARM)
    if scenario.controls_only_every_10th:
        names_c = np.asarray([2 if (t + 1) % 10 == 0 else 0 for t in range(SESSIONS_ENTRY)])
    if scenario.unequal_denominators:  # S5 draws: E first, then C, t = 1..60
        names_e = rng.integers(UNEQUAL_NAMES_LOW, UNEQUAL_NAMES_HIGH + 1, size=SESSIONS_ENTRY)
        names_c = rng.integers(UNEQUAL_NAMES_LOW, UNEQUAL_NAMES_HIGH + 1, size=SESSIONS_ENTRY)
    empty = rng.random(SESSIONS_ENTRY) < EMPTY_SESSION_PROBABILITY if scenario.empty_sessions else np.zeros(SESSIONS_ENTRY, dtype=bool)
    pnl = SIGMA_USD * (-u_e[0])  # H3 descriptive: E01 only, unit quantity, mu = 0
    rows = []
    for t in range(SESSIONS_ENTRY):
        n_e, n_c = (0, 0) if empty[t] else (int(names_e[t]), int(names_c[t]))
        re, rc = resolved_e[:n_e, t], resolved_c[:n_c, t]
        upper_e, lower_e = int(np.sum(re & (u_e[:n_e, t] <= thr_e))), int(np.sum(re & (u_e[:n_e, t] > thr_e)))
        upper_c, lower_c = int(np.sum(rc & (u_c[:n_c, t] <= thr_c))), int(np.sum(rc & (u_c[:n_c, t] > thr_c)))
        amb_e, amb_c = int(np.sum(~re & ambiguous_e[:n_e, t])), int(np.sum(~rc & ambiguous_c[:n_c, t]))
        rows.append({"upper_e": upper_e, "lower_e": lower_e, "upper_c": upper_c, "lower_c": lower_c,
                     "ambiguous_e": amb_e, "time_event_e": n_e - upper_e - lower_e - amb_e,
                     "ambiguous_c": amb_c, "time_event_c": n_c - upper_c - lower_c - amb_c,
                     "names_e": n_e, "names_c": n_c, "empty_session": bool(empty[t]),
                     "unobservable_e": 0, "unobservable_c": 0, "indeterminate_pnl": 0,
                     "pnl_sum_usd": 0.0 if empty[t] else float(pnl[t]), "pnl_count": 0 if empty[t] else 1})
    return rows


def run_procedure(rows: list[dict]) -> dict[int, dict]:
    """Exact decision sequence on one full trajectory (both cohorts mature at 69)."""
    first = est.read_cohort(est.cohort_from_sessions(rows, 40), sessions_completed=SESSIONS_TRAJECTORY)
    executed = {40: first}
    if not first["approved"]:
        executed[60] = est.read_cohort(est.cohort_from_sessions(rows, 60), sessions_completed=SESSIONS_TRAJECTORY)
    return executed


def _empty_counters() -> dict[str, int]:
    counters = {"repetitions": 0, "reading_60_executed": 0, "sequence_false_go": 0}
    for k in READINGS:
        for key in ("approved", "false_go", "not_estimable", "estimable", "covered", "gate_blocked"):
            counters[f"{key}@{k}"] = 0
    return counters


def run_chunk(scenario_id: str, start: int, stop: int) -> dict[str, int]:
    scenario = scenario_by_id(scenario_id)
    counters = _empty_counters()
    for r in range(start, stop):
        readings = run_procedure(simulate_repetition(scenario, r))
        counters["repetitions"] += 1
        any_false = False
        for k, reading in readings.items():
            if k == 60:
                counters["reading_60_executed"] += 1
            r1 = reading["r1"]
            if r1["status"] == "APPROVED":
                counters[f"approved@{k}"] += 1
                if scenario.null:
                    counters[f"false_go@{k}"] += 1
                    any_false = True
            if r1["status"] == "NOT_ESTIMABLE":
                counters[f"not_estimable@{k}"] += 1
            else:
                counters[f"estimable@{k}"] += 1
                if r1["lcb_one_sided"] is not None and r1["lcb_one_sided"] <= scenario.truth:
                    counters[f"covered@{k}"] += 1
            if r1["status"] == "DATA_GATE_BLOCKED":
                counters[f"gate_blocked@{k}"] += 1
        counters["sequence_false_go"] += int(any_false)
    return counters


def merge_counters(parts: list[dict[str, int]]) -> dict[str, int]:
    total = _empty_counters()
    for part in parts:
        for key, value in part.items():
            total[key] += value
    return total


def summarize_scenario(scenario: Scenario, counters: dict[str, int], confidence: float) -> dict:
    m = counters["repetitions"]
    executed = {40: m, 60: counters["reading_60_executed"]}
    errors = None
    if scenario.null:
        errors = {}
        for k in READINGS:
            count = counters[f"false_go@{k}"]
            upper = clopper_pearson_upper(count, m, confidence)
            errors[f"false_go@{k}"] = {**_rate(count, m), "upper_mc": upper, "limit": PER_READING_LIMIT, "pass": upper <= PER_READING_LIMIT}
        upper = clopper_pearson_upper(counters["sequence_false_go"], m, confidence)
        errors["sequence"] = {**_rate(counters["sequence_false_go"], m), "upper_mc": upper, "limit": SEQUENCE_LIMIT, "pass": upper <= SEQUENCE_LIMIT}
    return {
        **scenario.describe(), "repetitions": m, "error_metrics": errors,
        "all_error_checks_pass": (all(v["pass"] for v in errors.values()) if errors else None),
        "power": {f"approved@{k}": counters[f"approved@{k}"] / m for k in READINGS} | {"certified_any": (counters["approved@40"] + counters["approved@60"]) / m},
        "stopping": {"stopped_at_40": _rate(counters["approved@40"], m), "reading_60_executed": _rate(counters["reading_60_executed"], m)},
        "estimability": {f"P(A_{k})": (counters[f"estimable@{k}"] / executed[k] if executed[k] else None) for k in READINGS}
                        | {f"not_estimable@{k}": counters[f"not_estimable@{k}"] for k in READINGS},
        "coverage_conditional_on_estimable": {f"@{k}": (counters[f"covered@{k}"] / counters[f"estimable@{k}"] if counters[f"estimable@{k}"] else None) for k in READINGS},
        "gate_blocked": {f"@{k}": counters[f"gate_blocked@{k}"] for k in READINGS},
    }


def adverse_missingness_trial(repetitions: int, *, hide_lower: float = ADVERSE_HIDE_LOWER, hide_upper: float = ADVERSE_HIDE_UPPER,
                              hide_sessions: Iterable[int] | None = None) -> dict:
    """D2_000 with each lower hidden with probability 0.25 on its own session; gate must block per prefix."""
    scenario = scenario_by_id("D2_000")
    allowed = set(range(SESSIONS_ENTRY)) if hide_sessions is None else set(hide_sessions)
    consistent = 0
    blocked_by_reading = {40: 0, 60: 0}
    executed_by_reading = {40: 0, 60: 0}
    hidden_total = 0
    for r in range(repetitions):
        rows = simulate_repetition(scenario, r)
        rng = np.random.default_rng(external_seed("D2_000_ADVERSE", r))
        for index, row in enumerate(rows):
            if index not in allowed:
                continue
            for arm in ("e", "c"):
                h_lower = int(rng.binomial(row[f"lower_{arm}"], hide_lower))
                h_upper = int(rng.binomial(row[f"upper_{arm}"], hide_upper))
                row[f"lower_{arm}"] -= h_lower
                row[f"upper_{arm}"] -= h_upper
                row[f"unobservable_{arm}"] += h_lower + h_upper
        hidden_total += sum(row["unobservable_e"] + row["unobservable_c"] for row in rows)
        ok = True
        for k, reading in run_procedure(rows).items():
            executed_by_reading[k] += 1
            hidden_in_prefix = sum(row["unobservable_e"] + row["unobservable_c"] for row in rows[:k])
            blocked = (not reading["data_gate"]["open"]) and "DATA_GATE_BLOCKED" in reading["r1"]["reasons"]
            blocked_by_reading[k] += int(blocked)
            ok &= blocked == (hidden_in_prefix > 0) and (not reading["approved"] or hidden_in_prefix == 0)
        consistent += int(ok)
    return {"scenario_id": "D2_000", "hide_lower": hide_lower, "hide_upper": hide_upper, "repetitions": repetitions,
            "hide_sessions": None if hide_sessions is None else sorted(allowed), "hidden_episodes_total": hidden_total,
            "gate_blocked_by_reading": blocked_by_reading, "readings_executed": executed_by_reading,
            "consistent_repetitions": consistent, "pass": consistent == repetitions}


def run_calibration(repetitions: int = DEFAULT_REPETITIONS, scenario_ids: list[str] | None = None, *,
                    workers: int = 1, chunk: int = 1_000, adverse_repetitions: int = 0,
                    log: Callable[[str], None] | None = None) -> dict:
    scenarios = list(FROZEN_SCENARIOS)
    if scenario_ids:
        wanted = set(scenario_ids)
        missing = wanted - set(FROZEN_SCENARIO_IDS)
        if missing:
            raise KeyError(sorted(missing))
        scenarios = [s for s in scenarios if s.scenario_id in wanted]
    started = time.monotonic()
    tasks = [(s.scenario_id, start, min(start + chunk, repetitions)) for s in scenarios for start in range(0, repetitions, chunk)]
    chunks_per_scenario = math.ceil(repetitions / chunk)
    parts: dict[str, list[dict[str, int]]] = {s.scenario_id: [] for s in scenarios}
    elapsed: dict[str, float] = {}

    def record(scenario_id: str, counters: dict[str, int]) -> None:
        parts[scenario_id].append(counters)
        if len(parts[scenario_id]) == chunks_per_scenario:
            elapsed[scenario_id] = round(time.monotonic() - started, 3)
            if log:
                log(f"{scenario_id} done at {elapsed[scenario_id]:.1f}s")

    if workers <= 1:
        for scenario_id, start, stop in tasks:
            record(scenario_id, run_chunk(scenario_id, start, stop))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_chunk, *task): task for task in tasks}
            for future in as_completed(futures):
                record(futures[future][0], future.result())
    confidence = 1.0 - MC_CONFIDENCE_ERROR / K_METRICS
    results = []
    for scenario in scenarios:
        summary = summarize_scenario(scenario, merge_counters(parts[scenario.scenario_id]), confidence)
        summary["wall_clock_seconds_since_start"] = elapsed.get(scenario.scenario_id)
        results.append(summary)
    nulls = [r for r in results if r["error_metrics"] is not None]
    k_observed = 3 * len(nulls)
    frozen_list = [s.scenario_id for s in scenarios] == list(FROZEN_SCENARIO_IDS)
    full_matrix = frozen_list and repetitions == CERTIFYING_REPETITIONS
    adverse = adverse_missingness_trial(adverse_repetitions) if adverse_repetitions > 0 else None
    return {
        "schema": "R2D2_V2_CALIBRATION_R1_REPORT_v1", "protocol_id": PROTOCOL_ID, "layer": "A",
        "emenda_1_sha256": est.EMENDA_1_REV2_SHA256,
        "repetitions_per_scenario": repetitions, "certifying_repetitions": CERTIFYING_REPETITIONS,
        "scenario_count": len(results), "frozen_scenario_ids": list(FROZEN_SCENARIO_IDS), "frozen_list_used": frozen_list,
        "k_metrics_declared": K_METRICS, "k_metrics_observed": k_observed, "mc_confidence_per_metric": confidence,
        "method": {"estimator": "batch-means Student t, batches of 10 scheduled sessions, equal batch weights",
                   "alpha": est.ALPHA, "cohorts": list(est.COHORT_SESSIONS), "maturation": [est.maturation_session(n) for n in est.COHORT_SESSIONS],
                   "t_quantiles": {"df3": est.student_t_quantile(3, 1 - est.ALPHA), "df5": est.student_t_quantile(5, 1 - est.ALPHA)}},
        "external_rng": {"engine": EXTERNAL_RNG, "seed_rule": "int.from_bytes(sha256(f'{PROTOCOL_ID}|{scenario_id}|{r}')[:16], 'big')",
                         "draw_order": ["eps", "A", "W_E", "W_C", "eta_E", "eta_C", "resolution_E", "resolution_C", "ambiguous_E", "ambiguous_C",
                                        "S5:n_E,t (t=1..60)", "S5:n_C,t (t=1..60)", "S6:empty_t (t=1..60)"]},
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform(),
                        "workers": workers, "chunk": chunk, "cpu_count": os.cpu_count()},
        "code": {"estimator_r1_sha256": _source_sha256(est), "calibration_r1_sha256": _source_sha256(sys.modules[__name__])},
        "acceptance": {
            "every_false_go_upper_le_1_over_120": all(v["pass"] for r in nulls for key, v in r["error_metrics"].items() if key != "sequence"),
            "every_sequence_upper_le_2_over_120": all(r["error_metrics"]["sequence"]["pass"] for r in nulls),
            "full_matrix": full_matrix,
            "k_matches_declared": (k_observed == K_METRICS) if full_matrix else None,
            "adverse_missingness_gate": adverse["pass"] if adverse else None,
            "certifying_run": bool(full_matrix and k_observed == K_METRICS and adverse is not None),
        },
        "adverse_missingness_check": adverse, "scenarios": results, "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EMENDA 1 calibration (C3PO-V2-CAL-2) of the batch-means R1 procedure; layer A, no real data.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help="M per scenario; only exactly 50,000 with the frozen list certifies")
    parser.add_argument("--scenario", action="append", help="restrict to frozen scenario ids (development only)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunk", type=int, default=1_000)
    parser.add_argument("--adverse-repetitions", type=int, default=0)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args(argv)
    report = run_calibration(args.repetitions, args.scenario, workers=args.workers, chunk=args.chunk,
                             adverse_repetitions=args.adverse_repetitions, log=lambda line: print(line, file=sys.stderr, flush=True))
    encoded = json.dumps(report, sort_keys=True, indent=2, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"scenarios": report["scenario_count"], "repetitions": args.repetitions, "elapsed_seconds": report["elapsed_seconds"],
                      "acceptance": report["acceptance"], "report_sha256": report["report_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
