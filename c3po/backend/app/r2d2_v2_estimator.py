"""R2D2 V2 — pure decision estimator for the shadow certification (spec V1 rev 2, §§4-5, §7).

Contract (manifest 01d25890…): three mandatory positive hypotheses read on the
same mature cohort — R1 (p_E - p_C > 0), H1 (p_E > 0.5), H3 (mean net P&L per
portfolio episode > 0 USD) — with two readings (first 20 and first 30 scheduled
entry sessions, maturing at sessions 29 and 39), one-sided alpha 1/120 per
test, joint approval only, no partial GO carried across cohorts, no third
reading. Inference resamples *sufficient statistics of the finalized cohort*
with a circular block bootstrap (L = 5 entry sessions, 10,000 replicas, seed
20260824, common draws for every arm/hypothesis of a reading). Undefined
replicas are never removed: the approval LCB uses the least favourable value
(-1 for R1, 0 for H1, -inf for H3); fewer than 9,000 defined replicas make the
hypothesis NOT_ESTIMABLE. Every decision LCB is the Hyndman-Fan type 7 quantile
over the full sorted vector of 10,000 values (-inf propagates in H3). Original
counts and every reason for non-approval are published.

RNG pin: the internal bootstrap uses CPython `random.Random` (MT19937) seeded
with 20260824 and `randrange(n)` for the block starts. No I/O, no app imports,
no price logic: the caller proves the cohort statistics; this module decides.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

BOOTSTRAP_SEED = 20260824
BOOTSTRAP_ITERATIONS = 10_000
BLOCK_LENGTH = 5
MIN_DEFINED_REPLICAS = 9_000
ALPHA = 1.0 / 120.0
HORIZON_SESSIONS = 10
COHORT_SESSIONS = (20, 30)
HYPOTHESES = ("R1", "H1", "H3")
NULL_THRESHOLDS = {"R1": 0.0, "H1": 0.5, "H3": 0.0}
UNDEFINED_VALUES = {"R1": -1.0, "H1": 0.0, "H3": -math.inf}
INTERNAL_RNG = "CPython random.Random (MT19937) seed 20260824, randrange(n) block starts"

STATE_CERTIFIED = "V2_SHADOW_CERTIFIED_CANDIDATE"
STATE_CONTINUE = "CONTINUE_TO_COHORT30"
STATE_FAILED = "V2_CERTIFICATION_FAILED"
STATE_NOT_ESTIMABLE = "V2_CERTIFICATION_NOT_ESTIMABLE"
STATE_GATE_BLOCKED = "V2_DATA_GATE_BLOCKED"


class EstimatorError(ValueError):
    """Controlled codes only; never interpolates private values."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EstimatorError(code)


def maturation_session(cohort_sessions: int, horizon: int = HORIZON_SESSIONS) -> int:
    """Entry session N matures at session N + horizon - 1 (the horizon includes the entry)."""
    return cohort_sessions + horizon - 1


def circular_block_weights(
    n_sessions: int,
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    block_length: int = BLOCK_LENGTH,
    seed: int = BOOTSTRAP_SEED,
) -> np.ndarray:
    """Session multiplicity weights for a circular block bootstrap.

    ceil(n / L) uniform block starts per replica; each block is L consecutive
    session indices with circular wrap; the concatenation is truncated to n
    sessions. Draws are deterministic for (n, iterations, L, seed) and shared by
    every arm and endpoint of the reading.
    """
    _require(n_sessions > 0 and block_length > 0 and iterations > 0, "BOOTSTRAP_SHAPE")
    rng = random.Random(seed)
    blocks = math.ceil(n_sessions / block_length)
    weights = np.zeros((iterations, n_sessions), dtype=np.int32)
    for replica in range(iterations):
        picked = 0
        for _ in range(blocks):
            start = rng.randrange(n_sessions)
            for offset in range(block_length):
                if picked == n_sessions:
                    break
                weights[replica, (start + offset) % n_sessions] += 1
                picked += 1
    return weights


def hf7_quantile(values: np.ndarray, probability: float) -> float:
    """Hyndman-Fan type 7 quantile over the full sorted vector; -inf propagates."""
    ordered = np.sort(np.asarray(values, dtype=float))
    n = ordered.size
    _require(n > 0 and 0.0 <= probability <= 1.0, "QUANTILE_INPUT")
    h = (n - 1) * probability
    lower, upper = math.floor(h), math.ceil(h)
    low_value, high_value = float(ordered[lower]), float(ordered[upper])
    if low_value == -math.inf or high_value == -math.inf:
        return -math.inf
    if math.isinf(low_value) or math.isinf(high_value):
        return math.inf
    return low_value + (h - lower) * (high_value - low_value)


@dataclass(frozen=True)
class CohortStatistics:
    """Sufficient statistics per scheduled entry session of one finalized cohort.

    Arrays are aligned by scheduled entry session (index 0 = first session);
    sessions without candidates carry zeros. Research arms: eligible (E) and
    valid-risk controls (C), counts of upper_first / lower_first among resolved
    episodes. Portfolio: sum of net P&L in USD and number of episodes with a
    known P&L. Data-gate inputs (§3.4) are counted, never imputed.
    """

    upper_e: np.ndarray
    lower_e: np.ndarray
    upper_c: np.ndarray
    lower_c: np.ndarray
    pnl_sum_usd: np.ndarray
    pnl_count: np.ndarray
    unobservable_e: int = 0
    unobservable_c: int = 0
    indeterminate_pnl: int = 0

    def __post_init__(self) -> None:
        arrays = (self.upper_e, self.lower_e, self.upper_c, self.lower_c, self.pnl_sum_usd, self.pnl_count)
        n = self.upper_e.shape[0]
        _require(all(a.ndim == 1 and a.shape[0] == n for a in arrays), "COHORT_SHAPE")
        _require(n in COHORT_SESSIONS, "COHORT_SIZE")
        for a in (self.upper_e, self.lower_e, self.upper_c, self.lower_c, self.pnl_count):
            _require(bool(np.all(a >= 0)), "NEGATIVE_COUNT")
        _require(bool(np.all(np.isfinite(self.pnl_sum_usd))), "PNL_NOT_FINITE")
        _require(min(self.unobservable_e, self.unobservable_c, self.indeterminate_pnl) >= 0, "NEGATIVE_COUNT")

    @property
    def sessions(self) -> int:
        return int(self.upper_e.shape[0])

    def data_gate_open(self) -> bool:
        """§3.4: zero unobservable post-eligibility in both arms, zero indeterminate P&L/NAV."""
        return self.unobservable_e == 0 and self.unobservable_c == 0 and self.indeterminate_pnl == 0

    def swapped_arms(self) -> "CohortStatistics":
        """Relabel E<->C (counter-proof: the R1 contrast must flip sign under common draws)."""
        return CohortStatistics(self.upper_c, self.lower_c, self.upper_e, self.lower_e, self.pnl_sum_usd, self.pnl_count,
                                self.unobservable_c, self.unobservable_e, self.indeterminate_pnl)


def _ratio(numerator: np.ndarray, denominator: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    defined = denominator > 0
    out = np.full(numerator.shape, np.nan, dtype=float)
    np.divide(numerator, denominator, out=out, where=defined)
    return out, defined


def bootstrap_replicas(stats: CohortStatistics, weights: np.ndarray) -> dict:
    """Replica vectors (with conservative undefined values), defined masks and point estimates."""
    _require(weights.shape == (BOOTSTRAP_ITERATIONS, stats.sessions), "WEIGHTS_SHAPE")
    w = weights.astype(float)
    up_e, low_e = w @ stats.upper_e, w @ stats.lower_e
    up_c, low_c = w @ stats.upper_c, w @ stats.lower_c
    pnl, cnt = w @ stats.pnl_sum_usd, w @ stats.pnl_count
    p_e, def_e = _ratio(up_e, up_e + low_e)
    p_c, def_c = _ratio(up_c, up_c + low_c)
    mean_pnl, def_h3 = _ratio(pnl, cnt)
    defined = {"R1": def_e & def_c, "H1": def_e, "H3": def_h3}
    vectors = {
        "R1": np.where(defined["R1"], p_e - p_c, UNDEFINED_VALUES["R1"]),
        "H1": np.where(defined["H1"], p_e, UNDEFINED_VALUES["H1"]),
        "H3": np.where(defined["H3"], mean_pnl, UNDEFINED_VALUES["H3"]),
    }
    total_e = int(stats.upper_e.sum() + stats.lower_e.sum())
    total_c = int(stats.upper_c.sum() + stats.lower_c.sum())
    episodes = int(stats.pnl_count.sum())
    point = {
        "R1": (float(stats.upper_e.sum() / total_e - stats.upper_c.sum() / total_c) if total_e and total_c else None),
        "H1": float(stats.upper_e.sum() / total_e) if total_e else None,
        "H3": float(stats.pnl_sum_usd.sum() / episodes) if episodes else None,
    }
    return {"vectors": vectors, "defined": defined, "point": point,
            "resolved": {"E": total_e, "C": total_c, "portfolio_episodes": episodes}}


def read_cohort(stats: CohortStatistics, weights: np.ndarray | None = None, *, sessions_completed: int | None = None) -> dict:
    """One reading of one mature cohort. Public aggregates only.

    `sessions_completed` (scheduled entry sessions already fully observed) lets
    the caller prove maturation: reading cohort N before session N + 9 is refused.
    """
    n = stats.sessions
    if sessions_completed is not None:
        _require(sessions_completed >= maturation_session(n), "COHORT_NOT_MATURE")
    if weights is None:
        weights = circular_block_weights(n)
    replicas = bootstrap_replicas(stats, weights)
    gate_open = stats.data_gate_open()
    hypotheses = {}
    for name in HYPOTHESES:
        n_defined = int(replicas["defined"][name].sum())
        point = replicas["point"][name]
        lcb = hf7_quantile(replicas["vectors"][name], ALPHA)  # always computed over the full vector; published
        reasons = []
        if point is None:
            reasons.append("NO_RESOLVED_OBSERVATIONS")
        if n_defined < MIN_DEFINED_REPLICAS:
            reasons.append("INSUFFICIENT_DEFINED_REPLICAS")
        if not gate_open:
            reasons.append("DATA_GATE_BLOCKED")
        if not lcb > NULL_THRESHOLDS[name]:
            reasons.append("LCB_NOT_ABOVE_THRESHOLD")
        if not reasons:
            status = "APPROVED"
        elif "INSUFFICIENT_DEFINED_REPLICAS" in reasons or "NO_RESOLVED_OBSERVATIONS" in reasons:
            status = "NOT_ESTIMABLE"
        elif "DATA_GATE_BLOCKED" in reasons:
            status = "DATA_GATE_BLOCKED"
        else:
            status = "NOT_APPROVED"
        hypotheses[name] = {
            "point": point,
            "lcb_one_sided": None if math.isinf(lcb) else lcb,
            "lcb_is_minus_infinity": lcb == -math.inf,
            "alpha": ALPHA,
            "threshold": NULL_THRESHOLDS[name],
            "defined_replicas": n_defined,
            "undefined_replicas": BOOTSTRAP_ITERATIONS - n_defined,
            "undefined_value_used": None if math.isinf(UNDEFINED_VALUES[name]) else UNDEFINED_VALUES[name],
            "reasons": reasons,
            "status": status,
        }
    return {
        "schema": "R2D2_V2_COHORT_READING_v1",
        "cohort_sessions": n,
        "maturation_session": maturation_session(n),
        "sessions_completed": sessions_completed,
        "bootstrap": {"seed": BOOTSTRAP_SEED, "iterations": BOOTSTRAP_ITERATIONS, "block_length": BLOCK_LENGTH,
                       "blocks_per_replica": math.ceil(n / BLOCK_LENGTH), "rng": INTERNAL_RNG,
                       "quantile": "Hyndman-Fan_type7_full_vector", "undefined_rule": "least_favourable_value_kept",
                       "minimum_defined": MIN_DEFINED_REPLICAS},
        "resolved": replicas["resolved"],
        "data_gate": {"open": gate_open, "unobservable_e": stats.unobservable_e,
                      "unobservable_c": stats.unobservable_c, "indeterminate_pnl": stats.indeterminate_pnl},
        "hypotheses": hypotheses,
        "joint_approval": all(h["status"] == "APPROVED" for h in hypotheses.values()),
    }


def certify(cohorts: Mapping[int, CohortStatistics], *, sessions_completed: int | None = None) -> dict:
    """Sequential decision (§4, §7): read cohort 20; stop if jointly approved; else read 30 once.

    Only cohorts 20 and 30 exist. With cohort 30 not yet available the state is
    CONTINUE_TO_COHORT30 (no partial GO carried over). The result never
    authorizes promotion: certification is a separate order of the desk.
    """
    _require(set(cohorts) <= set(COHORT_SESSIONS), "UNKNOWN_COHORT")
    _require(20 in cohorts, "COHORT_20_REQUIRED")
    readings = {20: read_cohort(cohorts[20], sessions_completed=sessions_completed)}
    reasons: list[str] = []
    if readings[20]["joint_approval"]:
        state, certified_at = STATE_CERTIFIED, 20
    elif 30 not in cohorts:
        state, certified_at = STATE_CONTINUE, None
    else:
        readings[30] = read_cohort(cohorts[30], sessions_completed=sessions_completed)
        if readings[30]["joint_approval"]:
            state, certified_at = STATE_CERTIFIED, 30
        else:
            certified_at = None
            final = readings[30]["hypotheses"]
            failed = [f"{STATE_FAILED}_{name}" for name, h in final.items() if h["status"] == "NOT_APPROVED"]
            not_estimable = [name for name, h in final.items() if h["status"] == "NOT_ESTIMABLE"]
            gate_blocked = [name for name, h in final.items() if "DATA_GATE_BLOCKED" in h["reasons"]]
            reasons = failed + ([f"{STATE_NOT_ESTIMABLE}:{','.join(not_estimable)}"] if not_estimable else []) \
                + ([f"{STATE_GATE_BLOCKED}:{','.join(gate_blocked)}"] if gate_blocked else [])
            state = STATE_FAILED if failed else (STATE_NOT_ESTIMABLE if not_estimable else STATE_GATE_BLOCKED)
    return {"schema": "R2D2_V2_CERTIFICATION_v1", "state": state, "certified_at_cohort": certified_at,
            "readings_executed": sorted(readings), "readings": readings, "reasons": reasons,
            "no_partial_go_across_cohorts": True, "third_reading_allowed": False, "promotion_authorized": False}


def cohort_from_sessions(rows: Sequence[Mapping[str, float]], cohort_sessions: int, **gate: int) -> CohortStatistics:
    """Build statistics from per-session dicts (keys: upper_e, lower_e, upper_c, lower_c, pnl_sum_usd, pnl_count)."""
    _require(len(rows) >= cohort_sessions, "NOT_ENOUGH_SESSIONS")
    take = rows[:cohort_sessions]

    def col(key: str, dtype) -> np.ndarray:
        return np.asarray([row.get(key, 0) for row in take], dtype=dtype)

    return CohortStatistics(
        upper_e=col("upper_e", np.int64), lower_e=col("lower_e", np.int64),
        upper_c=col("upper_c", np.int64), lower_c=col("lower_c", np.int64),
        pnl_sum_usd=col("pnl_sum_usd", float), pnl_count=col("pnl_count", np.int64),
        unobservable_e=int(gate.get("unobservable_e", 0)), unobservable_c=int(gate.get("unobservable_c", 0)),
        indeterminate_pnl=int(gate.get("indeterminate_pnl", 0)),
    )
