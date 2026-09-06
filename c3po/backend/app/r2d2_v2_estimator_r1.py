"""R2D2 V2 — EMENDA 1 estimator: single confirmatory hypothesis R1, batch-means Student t.

Contract: EMENDA 1 revision 2 (sha256 3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4)
to spec V2 V1 rev 2 (manifest 01d25890…), signed by Codex, Dudu and Fable on 06/09/2026.

- Cohorts: the first 40 and the first 60 scheduled entry sessions (every scheduled
  session counts, with or without candidates), maturing at sessions 49 and 69.
- Batches: k = n/10 contiguous batches of 10 scheduled sessions, fixed by the
  calendar. For batch b and arm g: p_g,b = U_g,b / (U_g,b + L_g,b) among resolved
  episodes with entry session in the batch; d_b = p_E,b - p_C,b.
- Estimability event A_n: all 2k batch denominators positive. Outside A_n the
  reading is NOT_ESTIMABLE (decides the sample, never redefines the parameter);
  d_b is never imputed and batches are never dropped or merged.
- Estimand, one per cohort: theta_n = E[(1/k) sum_b d_b | A_n], equal batch
  weights. The pooled contrast (ratio of totals) is published as descriptive only.
- Decision: LCB = theta_hat - t_{k-1, 1-alpha} * s / sqrt(k), alpha = 1/120,
  exact Student t (regularized incomplete beta); approve iff LCB > 0, the data
  gate (§3.4) is open and the sample is in A_n. Two readings (40 then 60 once),
  no partial GO, no third reading. Approval means V2_FILTER_CERTIFIED_R1 only:
  filter discrimination, never economic expectancy or p_E > 0.5.
- H1 and H3 are descriptive (same batch scheme; informative intervals only).

Inputs are never coerced: every per-session field must be present, counts are
non-negative integers, P&L is finite, gate counters are explicit integers
aggregated within the cohort prefix (validators shared with the rev 2 module).
No I/O, no app imports, no price logic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence

import numpy as np

from .r2d2_v2_estimator import (  # shared strict validators and vocabulary
    COUNT_FIELDS, GATE_FIELDS, SESSION_FIELDS, EstimatorError, _as_count, _as_money, _is_int, _require,
)

EMENDA_1_REV2_SHA256 = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
ALPHA = 1.0 / 120.0
HORIZON_SESSIONS = 10
BATCH_SESSIONS = 10
COHORT_SESSIONS = (40, 60)
THRESHOLD = 0.0
DESCRIPTIVE_TWO_SIDED = 0.95

STATE_CERTIFIED = "V2_FILTER_CERTIFIED_R1"
STATE_CONTINUE = "CONTINUE_TO_COHORT60"
STATE_FAILED = "V2_CERTIFICATION_FAILED_R1"
STATE_NOT_ESTIMABLE = "V2_CERTIFICATION_NOT_ESTIMABLE"
STATE_GATE_BLOCKED = "V2_DATA_GATE_BLOCKED"
GO_SCOPE = ("Filter discrimination in shadow only (eligible vs valid-risk controls, same geometry and causal flow). "
            "Not p_E > 0.5, not positive P&L, not economic expectancy. A paper phase requires a separate pre-registered order.")


def maturation_session(cohort_sessions: int, horizon: int = HORIZON_SESSIONS) -> int:
    """Entry session N matures at session N + horizon - 1 (49 for 40, 69 for 60)."""
    return cohort_sessions + horizon - 1


# ---------------------------------------------------------------- exact Student t (no scipy)

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    max_iterations, eps, tiny = 1000, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1.0 / d
    h = d
    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, df: int) -> float:
    _require(_is_int(df) and df >= 1, "T_DF_INVALID")
    x = df / (df + t * t)
    tail = 0.5 * regularized_incomplete_beta(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0.0 else tail


@lru_cache(maxsize=256)
def student_t_quantile(df: int, probability: float) -> float:
    """Upper quantile t with P(T <= t) = probability, for 0.5 <= probability < 1 (pure; cached)."""
    _require(_is_int(df) and df >= 1 and 0.5 <= probability < 1.0, "T_QUANTILE_INPUT")
    lo, hi = 0.0, 1.0
    while student_t_cdf(hi, df) < probability:
        hi *= 2.0
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if student_t_cdf(mid, df) < probability:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-13 * max(1.0, hi):
            break
    return hi


# ---------------------------------------------------------------- cohort statistics

@dataclass(frozen=True)
class BatchCohortStatistics:
    """Per-session sufficient statistics of one finalized cohort of 40 or 60 scheduled sessions."""

    upper_e: np.ndarray
    lower_e: np.ndarray
    upper_c: np.ndarray
    lower_c: np.ndarray
    pnl_sum_usd: np.ndarray
    pnl_count: np.ndarray
    unobservable_e: int
    unobservable_c: int
    indeterminate_pnl: int

    def __post_init__(self) -> None:
        counts = (self.upper_e, self.lower_e, self.upper_c, self.lower_c, self.pnl_count)
        n = self.upper_e.shape[0] if isinstance(self.upper_e, np.ndarray) else -1
        _require(n in COHORT_SESSIONS, "COHORT_SIZE")
        for a in counts:
            _require(isinstance(a, np.ndarray) and a.ndim == 1 and a.shape[0] == n, "COHORT_SHAPE")
            _require(a.dtype.kind in "iu", "INVALID_COUNT_DTYPE")
            _require(bool(np.all(a >= 0)), "NEGATIVE_COUNT")
        _require(isinstance(self.pnl_sum_usd, np.ndarray) and self.pnl_sum_usd.ndim == 1 and self.pnl_sum_usd.shape[0] == n, "COHORT_SHAPE")
        _require(self.pnl_sum_usd.dtype.kind == "f", "INVALID_MONEY_DTYPE")
        _require(bool(np.all(np.isfinite(self.pnl_sum_usd))), "PNL_NOT_FINITE")
        for counter in (self.unobservable_e, self.unobservable_c, self.indeterminate_pnl):
            _as_count(counter, "INVALID_COUNTER")

    @property
    def sessions(self) -> int:
        return int(self.upper_e.shape[0])

    @property
    def batches(self) -> int:
        return self.sessions // BATCH_SESSIONS

    def data_gate_open(self) -> bool:
        return self.unobservable_e == 0 and self.unobservable_c == 0 and self.indeterminate_pnl == 0

    def swapped_arms(self) -> "BatchCohortStatistics":
        return BatchCohortStatistics(self.upper_c, self.lower_c, self.upper_e, self.lower_e, self.pnl_sum_usd, self.pnl_count,
                                     self.unobservable_c, self.unobservable_e, self.indeterminate_pnl)

    def extends(self, shorter: "BatchCohortStatistics") -> bool:
        m = shorter.sessions
        if m > self.sessions:
            return False
        pairs = ((self.upper_e, shorter.upper_e), (self.lower_e, shorter.lower_e), (self.upper_c, shorter.upper_c),
                 (self.lower_c, shorter.lower_c), (self.pnl_count, shorter.pnl_count), (self.pnl_sum_usd, shorter.pnl_sum_usd))
        if not all(np.array_equal(longer[:m], short) for longer, short in pairs):
            return False
        return (self.unobservable_e >= shorter.unobservable_e and self.unobservable_c >= shorter.unobservable_c
                and self.indeterminate_pnl >= shorter.indeterminate_pnl)


def cohort_from_sessions(rows: Sequence[Mapping[str, object]], cohort_sessions: int) -> BatchCohortStatistics:
    """Strict builder: nine explicit fields per scheduled session; gate counters summed in the prefix."""
    _require(_is_int(cohort_sessions), "COHORT_SIZE")
    _require(len(rows) >= cohort_sessions, "NOT_ENOUGH_SESSIONS")
    take = rows[:cohort_sessions]
    columns: dict[str, list[int]] = {key: [] for key in COUNT_FIELDS + GATE_FIELDS}
    money: list[float] = []
    for row in take:
        _require(isinstance(row, Mapping) and all(key in row for key in SESSION_FIELDS), "MISSING_FIELD")
        for key in COUNT_FIELDS + GATE_FIELDS:
            columns[key].append(_as_count(row[key]))
        money.append(_as_money(row["pnl_sum_usd"]))
    return BatchCohortStatistics(
        upper_e=np.asarray(columns["upper_e"], dtype=np.int64), lower_e=np.asarray(columns["lower_e"], dtype=np.int64),
        upper_c=np.asarray(columns["upper_c"], dtype=np.int64), lower_c=np.asarray(columns["lower_c"], dtype=np.int64),
        pnl_sum_usd=np.asarray(money, dtype=float), pnl_count=np.asarray(columns["pnl_count"], dtype=np.int64),
        unobservable_e=sum(columns["unobservable_e"]), unobservable_c=sum(columns["unobservable_c"]),
        indeterminate_pnl=sum(columns["indeterminate_pnl"]),
    )


# ---------------------------------------------------------------- batch statistics and readings

def batch_statistics(stats: BatchCohortStatistics) -> list[dict]:
    """Per-batch sums, proportions (None without denominator) and contrasts; nothing imputed."""
    out = []
    for b in range(stats.batches):
        sl = slice(b * BATCH_SESSIONS, (b + 1) * BATCH_SESSIONS)
        ue, le = int(stats.upper_e[sl].sum()), int(stats.lower_e[sl].sum())
        uc, lc = int(stats.upper_c[sl].sum()), int(stats.lower_c[sl].sum())
        pnl, cnt = float(stats.pnl_sum_usd[sl].sum()), int(stats.pnl_count[sl].sum())
        p_e = ue / (ue + le) if ue + le > 0 else None
        p_c = uc / (uc + lc) if uc + lc > 0 else None
        out.append({"batch": b + 1, "sessions": [b * BATCH_SESSIONS + 1, (b + 1) * BATCH_SESSIONS],
                    "upper_e": ue, "lower_e": le, "upper_c": uc, "lower_c": lc, "p_e": p_e, "p_c": p_c,
                    "d": (p_e - p_c) if p_e is not None and p_c is not None else None,
                    "pnl_sum_usd": pnl, "pnl_count": cnt, "pnl_mean_usd": (pnl / cnt) if cnt > 0 else None})
    return out


def _t_interval(values: list[float], alpha: float) -> dict:
    """Batch-means t statistics: mean, sd, one-sided LCB/UCB at alpha, two-sided 95 % interval."""
    k = len(values)
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    sd = float(arr.std(ddof=1)) if k > 1 else math.nan
    t_one = student_t_quantile(k - 1, 1.0 - alpha)
    t_two = student_t_quantile(k - 1, 1.0 - (1.0 - DESCRIPTIVE_TWO_SIDED) / 2.0)
    half_one, half_two = t_one * sd / math.sqrt(k), t_two * sd / math.sqrt(k)
    return {"k": k, "mean": mean, "sd": sd, "t_one_sided": t_one, "lcb_one_sided": mean - half_one, "ucb_one_sided": mean + half_one,
            "t_two_sided_95": t_two, "interval_95": [mean - half_two, mean + half_two]}


def read_cohort(stats: BatchCohortStatistics, *, sessions_completed: int | None = None) -> dict:
    """One reading of one cohort (40 or 60). Public aggregates only; R1 decides, H1/H3 describe."""
    n = stats.sessions
    if sessions_completed is not None:
        _require(_is_int(sessions_completed), "SESSIONS_COMPLETED_INVALID")
        _require(sessions_completed >= maturation_session(n), "COHORT_NOT_MATURE")
    batches = batch_statistics(stats)
    k = len(batches)
    missing = [b["batch"] for b in batches if b["d"] is None]
    estimable = not missing
    gate_open = stats.data_gate_open()
    reasons: list[str] = []
    r1: dict = {"hypothesis": "R1", "threshold": THRESHOLD, "alpha": ALPHA, "k": k, "batch_sessions": BATCH_SESSIONS,
                "estimand": "theta_n = E[(1/k) sum_b (p_E,b - p_C,b) | A_n] (equal batch weights, conditional on estimability)",
                "estimability_event_holds": estimable, "batches_without_denominator": missing}
    if estimable:
        interval = _t_interval([float(b["d"]) for b in batches], ALPHA)
        r1.update(point=interval["mean"], sd_batches=interval["sd"], t_quantile=interval["t_one_sided"],
                  lcb_one_sided=interval["lcb_one_sided"], interval_95=interval["interval_95"])
        if not interval["lcb_one_sided"] > THRESHOLD:
            reasons.append("LCB_NOT_ABOVE_THRESHOLD")
    else:
        r1.update(point=None, sd_batches=None, t_quantile=student_t_quantile(k - 1, 1.0 - ALPHA), lcb_one_sided=None, interval_95=None)
        reasons.append("NOT_ESTIMABLE_BATCH_DENOMINATOR")
    if not gate_open:
        reasons.append("DATA_GATE_BLOCKED")
    if not reasons:
        status = "APPROVED"
    elif "NOT_ESTIMABLE_BATCH_DENOMINATOR" in reasons:
        status = "NOT_ESTIMABLE"
    elif "DATA_GATE_BLOCKED" in reasons:
        status = "DATA_GATE_BLOCKED"
    else:
        status = "NOT_APPROVED"
    r1.update(reasons=reasons, status=status)
    total_e = int(stats.upper_e.sum() + stats.lower_e.sum())
    total_c = int(stats.upper_c.sum() + stats.lower_c.sum())
    pooled = (float(stats.upper_e.sum() / total_e - stats.upper_c.sum() / total_c) if total_e and total_c else None)
    # Descriptive H1/H3 with the same batch scheme; no decision power.
    p_e_values = [b["p_e"] for b in batches]
    h1 = ({"hypothesis": "H1", "decisive": False, "point": None, "reason": "BATCH_WITHOUT_E_DENOMINATOR"} if any(v is None for v in p_e_values)
          else {"hypothesis": "H1", "decisive": False, **_t_interval([float(v) for v in p_e_values], ALPHA)})
    pnl_values = [b["pnl_mean_usd"] for b in batches]
    h3 = ({"hypothesis": "H3", "decisive": False, "point": None, "reason": "BATCH_WITHOUT_PORTFOLIO_EPISODES"} if any(v is None for v in pnl_values)
          else {"hypothesis": "H3", "decisive": False, **_t_interval([float(v) for v in pnl_values], ALPHA)})
    return {
        "schema": "R2D2_V2_R1_COHORT_READING_v1",
        "emenda_1_sha256": EMENDA_1_REV2_SHA256,
        "cohort_sessions": n, "maturation_session": maturation_session(n), "sessions_completed": sessions_completed,
        "batches": batches,
        "resolved": {"E": total_e, "C": total_c, "portfolio_episodes": int(stats.pnl_count.sum())},
        "data_gate": {"open": gate_open, "unobservable_e": stats.unobservable_e, "unobservable_c": stats.unobservable_c,
                      "indeterminate_pnl": stats.indeterminate_pnl},
        "r1": r1,
        "descriptive": {"pooled_contrast": pooled, "pooled_note": "ratio of totals, weighted by denominators; descriptive only",
                        "h1": h1, "h3": h3},
        "approved": status == "APPROVED",
        "go_scope": GO_SCOPE,
    }


def certify(cohorts: Mapping[int, BatchCohortStatistics], *, sessions_completed: int) -> dict:
    """Sequential decision: read 40; stop if approved; else read 60 once. No partial GO, no third reading."""
    _require(_is_int(sessions_completed), "SESSIONS_COMPLETED_REQUIRED")
    _require(set(cohorts) <= set(COHORT_SESSIONS), "UNKNOWN_COHORT")
    _require(40 in cohorts, "COHORT_40_REQUIRED")
    for key, cohort in cohorts.items():
        _require(isinstance(cohort, BatchCohortStatistics) and cohort.sessions == key, "COHORT_KEY_MISMATCH")
    if 60 in cohorts:
        _require(cohorts[60].extends(cohorts[40]), "COHORT_PREFIX_MISMATCH")
    readings = {40: read_cohort(cohorts[40], sessions_completed=sessions_completed)}
    reasons: list[str] = []
    if readings[40]["approved"]:
        state, certified_at = STATE_CERTIFIED, 40
    elif 60 not in cohorts:
        state, certified_at = STATE_CONTINUE, None
    else:
        readings[60] = read_cohort(cohorts[60], sessions_completed=sessions_completed)
        if readings[60]["approved"]:
            state, certified_at = STATE_CERTIFIED, 60
        else:
            certified_at = None
            final = readings[60]["r1"]
            reasons = list(final["reasons"])
            if final["status"] == "NOT_APPROVED":
                state = STATE_FAILED
            elif final["status"] == "NOT_ESTIMABLE":
                state = STATE_NOT_ESTIMABLE
            else:
                state = STATE_GATE_BLOCKED
    return {"schema": "R2D2_V2_R1_CERTIFICATION_v1", "emenda_1_sha256": EMENDA_1_REV2_SHA256, "state": state,
            "certified_at_cohort": certified_at, "sessions_completed": sessions_completed,
            "readings_executed": sorted(readings), "readings": readings, "reasons": reasons,
            "no_partial_go_across_cohorts": True, "third_reading_allowed": False,
            "promotion_authorized": False, "go_scope": GO_SCOPE}
