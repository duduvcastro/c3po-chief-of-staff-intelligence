"""R2D2 V2 — synthetic calibration of the certification procedure (annex B + its closure; spec §5).

Layer A only: data-generating processes with known truth exercising the exact
decision algorithm of `r2d2_v2_estimator` (cohorts 20/30 on the same
trajectory, two readings, joint approval, alpha 1/120, circular block bootstrap
L = 5 with conservative undefined replicas). Nothing here touches prices, the
app, the database or production; no real input exists in this module.

Scenario matrix (28): structures D0/D1/D2 x eight null/alternative masks, plus
four stress scenarios on D2 (D2_S1..D2_S4). External seed per (scenario,
repetition r) = big-endian integer of the first 16 bytes of
SHA-256("C3PO-V2-CAL-1|<scenario_id>|<r>"), r = 0..M-1; the internal bootstrap
seed stays 20260824. RNG pin: numpy.random.Generator(PCG64) via
`numpy.random.default_rng(seed)`; numpy version recorded in the report.

Where the closure (FECHAMENTO_ANEXOS_PROPOSTA_CODEX.md) and annex B differ,
the closure prevails (addendum E3): H3 uses only record E01 per date with
unit quantity and V_t = -U_E01,t; D2_S2 has two controls only on sessions
divisible by 10; D2_S3 keeps the conditional 0.75/0.25 split of unresolved
episodes; heavy tails replace only the idiosyncratic noise of V by t5*sqrt(3/5).

Acceptance (closure): for every scenario with at least one true null, the
one-sided Clopper-Pearson upper bound (confidence 1 - 0.01/K, K = 121) of each
marginal false-GO rate must be <= 1/120 and of the family-wise error rate
<= 0.05. Estimability, coverage and power are published, never gate acceptance.
The adverse-missingness check of the data gate is separate and not part of K.
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

import numpy as np

from . import r2d2_v2_estimator as est

PROTOCOL_ID = "C3PO-V2-CAL-1"
SIGMA_USD = 100.0
NAMES_PER_ARM = 20
SESSIONS_ENTRY = 30
SESSIONS_TRAJECTORY = 39
MC_CONFIDENCE_ERROR = 0.01
K_METRICS = 121
MARGINAL_LIMIT = 1.0 / 120.0
FWER_LIMIT = 0.05
DEFAULT_REPETITIONS = 50_000
RESOLUTION_DEFAULT = 0.8
AMBIGUOUS_CONDITIONAL = 0.25  # of unresolved episodes; the rest are time/event exits
ADVERSE_HIDE_LOWER = 0.25
ADVERSE_HIDE_UPPER = 0.0
EXTERNAL_RNG = "numpy.random.Generator(PCG64) via default_rng(128-bit seed)"
READINGS = (20, 30)

MASKS = {  # R1/H1/H3 alternative flags -> (p_E, p_C, mu/sigma)
    "000": (0.5, 0.5, 0.0), "100": (0.5, 0.4, 0.0), "010": (0.6, 0.6, 0.0), "001": (0.5, 0.5, 0.2),
    "110": (0.6, 0.5, 0.0), "101": (0.5, 0.4, 0.2), "011": (0.6, 0.6, 0.2), "111": (0.6, 0.5, 0.2),
}
STRUCTURES = {  # rho, kappa, w, phi
    "D0": (0.0, 0.0, 1.0, 0.0), "D1": (0.5, 0.0, 1.0, 0.0), "D2": (0.7, 0.2, 0.5, 0.8),
}


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    structure: str
    p_e: float
    p_c: float
    mu_usd: float
    resolution_e: float = RESOLUTION_DEFAULT
    resolution_c: float = RESOLUTION_DEFAULT
    heavy_tail_h3: bool = False
    controls_only_every_10th: bool = False

    @property
    def truth(self) -> dict:
        return {"R1": self.p_e - self.p_c, "H1": self.p_e, "H3": self.mu_usd}

    @property
    def nulls(self) -> dict:
        return {"R1": self.p_e - self.p_c <= 0.0, "H1": self.p_e <= 0.5, "H3": self.mu_usd <= 0.0}

    def describe(self) -> dict:
        rho, kappa, w, phi = STRUCTURES[self.structure]
        return {"scenario_id": self.scenario_id, "structure": self.structure, "rho": rho, "kappa": kappa, "w": w, "phi": phi,
                "p_e": self.p_e, "p_c": self.p_c, "mu_usd": self.mu_usd, "resolution_e": self.resolution_e,
                "resolution_c": self.resolution_c, "heavy_tail_h3": self.heavy_tail_h3,
                "controls_only_every_10th": self.controls_only_every_10th, "truth": self.truth, "nulls": self.nulls}


def scenario_matrix() -> list[Scenario]:
    scenarios = [Scenario(f"{structure}_{mask}", structure, p_e, p_c, mu * SIGMA_USD)
                 for structure in STRUCTURES for mask, (p_e, p_c, mu) in MASKS.items()]
    scenarios += [
        Scenario("D2_S1", "D2", 0.4, 0.6, -0.2 * SIGMA_USD),
        Scenario("D2_S2", "D2", 0.5, 0.5, 0.0, controls_only_every_10th=True),
        Scenario("D2_S3", "D2", 0.5, 0.5, 0.0, resolution_e=0.2, resolution_c=0.9),
        Scenario("D2_S4", "D2", 0.5, 0.5, 0.0, heavy_tail_h3=True),
    ]
    assert len(scenarios) == 28
    return scenarios


def scenario_by_id(scenario_id: str) -> Scenario:
    for scenario in scenario_matrix():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(scenario_id)


def external_seed(scenario_id: str, repetition: int) -> int:
    digest = hashlib.sha256(f"{PROTOCOL_ID}|{scenario_id}|{repetition}".encode("utf-8")).digest()
    return int.from_bytes(digest[:16], "big")


def _ar1(rng: np.random.Generator, phi: float, shape: tuple[int, ...]) -> np.ndarray:
    """Stationary Gaussian AR(1), unit variance, stationary N(0,1) start; phi = 0 gives iid N(0,1)."""
    steps = shape[-1]
    out = np.empty(shape)
    out[..., 0] = rng.standard_normal(shape[:-1])
    if phi == 0.0:
        out[..., 1:] = rng.standard_normal(shape[:-1] + (steps - 1,))
        return out
    innovation_sd = math.sqrt(1.0 - phi * phi)
    for t in range(1, steps):
        out[..., t] = phi * out[..., t - 1] + innovation_sd * rng.standard_normal(shape[:-1])
    return out


def simulate_repetition(scenario: Scenario, repetition: int) -> list[dict]:
    """One trajectory: 30 scheduled entry sessions, observation to session 39, layer-A outcomes."""
    rho, kappa, w, phi = STRUCTURES[scenario.structure]
    rng = np.random.default_rng(external_seed(scenario.scenario_id, repetition))
    eps = rng.standard_normal(SESSIONS_TRAJECTORY + 9)
    z = np.convolve(eps, np.ones(10), mode="valid") / math.sqrt(10.0)  # Z_t = sum_{j=0..9} eps_{t+j} / sqrt(10)
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
    # H3 (closure): only record E01 per date, unit quantity, V_t = -U_E01,t; heavy tail replaces only zeta.
    if scenario.heavy_tail_h3:
        zeta = rng.standard_t(5, SESSIONS_TRAJECTORY) * math.sqrt(3.0 / 5.0)
        v = -(math.sqrt(rho) * x + math.sqrt(kappa) * w_e[0] + idio * zeta)
    else:
        v = -u_e[0]
    pnl = scenario.mu_usd + SIGMA_USD * v
    rows = []
    for t in range(SESSIONS_ENTRY):
        n_c = NAMES_PER_ARM
        if scenario.controls_only_every_10th:
            n_c = 2 if (t + 1) % 10 == 0 else 0
        re, rc = resolved_e[:, t], resolved_c[:n_c, t]
        upper_e, lower_e = int(np.sum(re & (u_e[:, t] <= thr_e))), int(np.sum(re & (u_e[:, t] > thr_e)))
        upper_c, lower_c = int(np.sum(rc & (u_c[:n_c, t] <= thr_c))), int(np.sum(rc & (u_c[:n_c, t] > thr_c)))
        amb_e = int(np.sum(~re & ambiguous_e[:, t]))
        amb_c = int(np.sum(~rc & ambiguous_c[:n_c, t]))
        rows.append({"upper_e": upper_e, "lower_e": lower_e, "upper_c": upper_c, "lower_c": lower_c,
                     "ambiguous_e": amb_e, "time_event_e": NAMES_PER_ARM - upper_e - lower_e - amb_e,
                     "ambiguous_c": amb_c, "time_event_c": n_c - upper_c - lower_c - amb_c,
                     "unobservable_e": 0, "unobservable_c": 0,
                     "pnl_sum_usd": float(pnl[t]), "pnl_count": 1})
    return rows


_WEIGHTS: dict[int, np.ndarray] = {}


def common_weights(n: int) -> np.ndarray:
    if n not in _WEIGHTS:
        _WEIGHTS[n] = est.circular_block_weights(n)
    return _WEIGHTS[n]


def run_procedure(rows: list[dict], **gate: int) -> dict[int, dict]:
    """Exact decision sequence on one trajectory (reading 30 only without joint approval at 20)."""
    first = est.read_cohort(est.cohort_from_sessions(rows, 20, **gate), common_weights(20))
    executed = {20: first}
    if not first["joint_approval"]:
        executed[30] = est.read_cohort(est.cohort_from_sessions(rows, 30, **gate), common_weights(30))
    return executed


def _empty_counters() -> dict[str, int]:
    counters = {"repetitions": 0, "reading_30_executed": 0, "joint_20": 0, "joint_30": 0, "fwer_events": 0, "false_certification": 0}
    for h in est.HYPOTHESES:
        for k in READINGS:
            counters[f"approved:{h}@{k}"] = 0
            counters[f"false_go:{h}@{k}"] = 0
            counters[f"not_estimable:{h}@{k}"] = 0
            counters[f"estimable:{h}@{k}"] = 0
            counters[f"covered:{h}@{k}"] = 0
            counters[f"minus_inf:{h}@{k}"] = 0
    return counters


def run_chunk(scenario_id: str, start: int, stop: int) -> dict[str, int]:
    """Counters for repetitions r in [start, stop) of one scenario; deterministic and order-free."""
    scenario = scenario_by_id(scenario_id)
    nulls, truth = scenario.nulls, scenario.truth
    counters = _empty_counters()
    for r in range(start, stop):
        readings = run_procedure(simulate_repetition(scenario, r))
        counters["repetitions"] += 1
        any_null_approved = False
        for k, reading in readings.items():
            if k == 30:
                counters["reading_30_executed"] += 1
            for h, result in reading["hypotheses"].items():
                status = result["status"]
                if status == "APPROVED":
                    counters[f"approved:{h}@{k}"] += 1
                    if nulls[h]:
                        counters[f"false_go:{h}@{k}"] += 1
                        any_null_approved = True
                if status == "NOT_ESTIMABLE":
                    counters[f"not_estimable:{h}@{k}"] += 1
                else:
                    counters[f"estimable:{h}@{k}"] += 1
                    if result["lcb_is_minus_infinity"]:
                        counters[f"minus_inf:{h}@{k}"] += 1
                    lcb = -math.inf if result["lcb_is_minus_infinity"] else result["lcb_one_sided"]
                    if lcb <= truth[h]:
                        counters[f"covered:{h}@{k}"] += 1
            if reading["joint_approval"]:
                counters["joint_20" if k == 20 else "joint_30"] += 1
                if any(nulls.values()):
                    counters["false_certification"] += 1
        counters["fwer_events"] += int(any_null_approved)
    return counters


def merge_counters(parts: list[dict[str, int]]) -> dict[str, int]:
    total = _empty_counters()
    for part in parts:
        for key, value in part.items():
            total[key] += value
    return total


def clopper_pearson_upper(successes: int, trials: int, confidence: float) -> float:
    """One-sided exact upper bound (binom.test convention): smallest p with P(X <= x | p) <= 1 - confidence."""
    if successes >= trials:
        return 1.0
    alpha = 1.0 - confidence
    log_choose = [math.lgamma(trials + 1) - math.lgamma(k + 1) - math.lgamma(trials - k + 1) for k in range(successes + 1)]

    def cdf(p: float) -> float:
        if p <= 0.0:
            return 1.0
        if p >= 1.0:
            return 0.0
        return sum(math.exp(lc + k * math.log(p) + (trials - k) * math.log1p(-p)) for k, lc in enumerate(log_choose))

    lo, hi = successes / trials, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def _rate(count: int, trials: int) -> dict:
    rate = count / trials if trials else None
    return {"count": count, "trials": trials, "rate": rate,
            "mc_standard_error": (math.sqrt(rate * (1.0 - rate) / trials) if trials else None)}


def summarize_scenario(scenario: Scenario, counters: dict[str, int], confidence: float) -> dict:
    m = counters["repetitions"]
    nulls = scenario.nulls
    marginal = {}
    all_pass = True
    for h in est.HYPOTHESES:
        if not nulls[h]:
            continue
        for k in READINGS:
            count = counters[f"false_go:{h}@{k}"]
            upper = clopper_pearson_upper(count, m, confidence)
            ok = upper <= MARGINAL_LIMIT
            all_pass &= ok
            marginal[f"{h}@{k}"] = {**_rate(count, m), "upper_mc": upper, "limit": MARGINAL_LIMIT, "pass": ok}
    fwer = None
    if any(nulls.values()):
        upper = clopper_pearson_upper(counters["fwer_events"], m, confidence)
        fwer = {**_rate(counters["fwer_events"], m), "upper_mc": upper, "limit": FWER_LIMIT, "pass": upper <= FWER_LIMIT}
        all_pass &= fwer["pass"]
    coverage = {}
    for h in est.HYPOTHESES:
        for k in READINGS:
            estimable = counters[f"estimable:{h}@{k}"]
            coverage[f"{h}@{k}"] = {"estimable": estimable, "covered": counters[f"covered:{h}@{k}"],
                                    "conditional_coverage": (counters[f"covered:{h}@{k}"] / estimable if estimable else None),
                                    "lcb_minus_infinity": counters[f"minus_inf:{h}@{k}"]}
    executed = {20: m, 30: counters["reading_30_executed"]}
    return {
        **scenario.describe(),
        "repetitions": m,
        "marginal_false_go": marginal,
        "fwer": fwer,
        "false_certification": _rate(counters["false_certification"], m) if any(nulls.values()) else None,
        "all_error_checks_pass": all_pass if any(nulls.values()) else None,
        "stopping": {"stopped_at_20": _rate(counters["joint_20"], m), "reading_30_executed": _rate(counters["reading_30_executed"], m)},
        "power": {"joint_certified_at_20": counters["joint_20"] / m, "joint_certified_at_30": counters["joint_30"] / m,
                  "joint_certified_any": (counters["joint_20"] + counters["joint_30"]) / m,
                  "approvals": {f"{h}@{k}": counters[f"approved:{h}@{k}"] / m for h in est.HYPOTHESES for k in READINGS}},
        "estimability": {f"{h}@{k}": {"not_estimable": counters[f"not_estimable:{h}@{k}"], "readings_executed": executed[k],
                                      "rate_of_executed": (counters[f"not_estimable:{h}@{k}"] / executed[k] if executed[k] else None)}
                         for h in est.HYPOTHESES for k in READINGS},
        "coverage_conditional_on_available_bounds": coverage,
    }


def adverse_missingness_trial(repetitions: int, *, hide_lower: float = ADVERSE_HIDE_LOWER, hide_upper: float = ADVERSE_HIDE_UPPER) -> dict:
    """Closure: D2 under 000, hide each lower with probability 0.25 (upper 0.0) after the fact.

    The oracle keeps the synthetic original as truth; the estimator receives the
    hidden version with the hidden episodes counted as `unobservable` and must
    block promotion through the data gate. The naive counterfactual (same
    hidden counts with the gate ignored) is published only to show the
    selection bias the gate prevents; it is not a legitimate inference.
    """
    scenario = scenario_by_id("D2_000")
    gate_blocked = 0
    hidden_total = 0
    naive_approvals = {f"{h}@{k}": 0 for h in est.HYPOTHESES for k in READINGS}
    naive_joint = 0
    for r in range(repetitions):
        rows = simulate_repetition(scenario, r)
        rng = np.random.default_rng(external_seed("D2_000_ADVERSE", r))
        for row in rows:
            for arm in ("e", "c"):
                h_lower = int(rng.binomial(row[f"lower_{arm}"], hide_lower))
                h_upper = int(rng.binomial(row[f"upper_{arm}"], hide_upper))
                row[f"lower_{arm}"] -= h_lower
                row[f"upper_{arm}"] -= h_upper
                row[f"unobservable_{arm}"] += h_lower + h_upper
        hidden_e = sum(row["unobservable_e"] for row in rows)
        hidden_c = sum(row["unobservable_c"] for row in rows)
        hidden_total += hidden_e + hidden_c
        gated = run_procedure(rows, unobservable_e=hidden_e, unobservable_c=hidden_c)
        blocked = all(not reading["joint_approval"] and all("DATA_GATE_BLOCKED" in h["reasons"] for h in reading["hypotheses"].values())
                      for reading in gated.values())
        gate_blocked += int(blocked)
        naive = run_procedure(rows)  # gate ignored: oracle diagnostic only
        for k, reading in naive.items():
            for h, result in reading["hypotheses"].items():
                naive_approvals[f"{h}@{k}"] += int(result["status"] == "APPROVED")
            naive_joint += int(reading["joint_approval"])
    return {"scenario_id": "D2_000", "hide_lower": hide_lower, "hide_upper": hide_upper, "repetitions": repetitions,
            "hidden_episodes_total": hidden_total, "gate_blocked": gate_blocked, "gate_blocked_rate": gate_blocked / repetitions,
            "pass": gate_blocked == repetitions,
            "naive_without_gate_diagnostic": {"approvals": {key: value / repetitions for key, value in naive_approvals.items()},
                                              "joint_certification_rate": naive_joint / repetitions}}


def _source_sha256(module) -> str:
    with open(module.__file__, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def run_calibration(repetitions: int = DEFAULT_REPETITIONS, scenario_ids: list[str] | None = None, *,
                    workers: int = 1, chunk: int = 1_000, adverse_repetitions: int = 0, log=None) -> dict:
    scenarios = scenario_matrix()
    if scenario_ids:
        wanted = set(scenario_ids)
        scenarios = [s for s in scenarios if s.scenario_id in wanted]
        missing = wanted - {s.scenario_id for s in scenarios}
        if missing:
            raise KeyError(sorted(missing))
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
    with_null = [r for r in results if r["fwer"] is not None]
    n_marginal = sum(len(r["marginal_false_go"]) for r in results)
    adverse = adverse_missingness_trial(adverse_repetitions) if adverse_repetitions > 0 else None
    full_matrix = len(results) == 28 and repetitions >= DEFAULT_REPETITIONS
    k_observed = n_marginal + len(with_null)
    return {
        "schema": "R2D2_V2_CALIBRATION_REPORT_v1",
        "protocol_id": PROTOCOL_ID,
        "layer": "A",
        "repetitions_per_scenario": repetitions,
        "scenario_count": len(results),
        "k_metrics_declared": K_METRICS,
        "k_metrics_observed": k_observed,
        "mc_confidence_per_metric": confidence,
        "bootstrap": {"seed": est.BOOTSTRAP_SEED, "iterations": est.BOOTSTRAP_ITERATIONS, "block_length": est.BLOCK_LENGTH,
                       "minimum_defined": est.MIN_DEFINED_REPLICAS, "alpha": est.ALPHA, "internal_rng": est.INTERNAL_RNG},
        "external_rng": {"engine": EXTERNAL_RNG, "seed_rule": "int.from_bytes(sha256(f'{PROTOCOL_ID}|{scenario_id}|{r}')[:16], 'big')"},
        "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform(),
                        "workers": workers, "chunk": chunk, "cpu_count": os.cpu_count()},
        "code": {"estimator_sha256": _source_sha256(est), "calibration_sha256": _source_sha256(sys.modules[__name__])},
        "acceptance": {
            "every_marginal_upper_le_1_over_120": all(m["pass"] for r in results for m in r["marginal_false_go"].values()),
            "every_fwer_upper_le_0_05": all(r["fwer"]["pass"] for r in with_null),
            "full_matrix": full_matrix,
            "k_matches_declared": (k_observed == K_METRICS) if full_matrix else None,
            "adverse_missingness_gate": adverse["pass"] if adverse else None,
            "certifying_run": bool(full_matrix and k_observed == K_METRICS and adverse is not None),
        },
        "adverse_missingness_check": adverse,
        "scenarios": results,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic calibration of the V2 certification procedure (layer A, no real data).")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help="external repetitions per scenario (M)")
    parser.add_argument("--scenario", action="append", help="restrict to scenario ids (repeatable); default: all 28")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunk", type=int, default=1_000)
    parser.add_argument("--adverse-repetitions", type=int, default=0, help="repetitions of the adverse-missingness gate check")
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
