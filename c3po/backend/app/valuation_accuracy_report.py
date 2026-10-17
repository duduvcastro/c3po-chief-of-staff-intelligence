"""The realized accuracy of the official TP sources as the buy/no-buy decider reads them — PREREG_VALUATION_DECISOR_V1
(``c3po/docs/PREREG_VALUATION_DECISOR_V1.md``), rev 2: the first realized-accuracy number, read-only.

MEASUREMENT, NEVER A GATE: nothing served changes, nothing is written, nothing is fetched. The report reads exactly what
the §7.3 panel reads (``valuation_panel``: the immutable prediction records of ``valuation_predictions`` by source, the
persisted price series of ``valuation_price_history`` through ``PriceHistoryService`` with the cut as
``available_before``, the exchange calendars) and REUSES its admissibility (``admissible_records``: one record per
(source, symbol, session), ``published_at < C``), its live cohort (§2.2 R3 a), its observation (basis check, ``a(T)``,
labels of the same vintage) and its attrition (``horizon_metrics``). On top of that it publishes, per market group
(``B3``; ``US`` = NASDAQ ∪ NYSE, one calendar and one currency), source and horizon in sessions (21 primary; 63/126
descriptive), split into the development partition (sessions before the holdout start ``H0``) and the holdout
(``T ≥ H0``):

* the rank IC — per session, Spearman between the upside served at night ``T`` (``tp / price − 1``) and a return over
  the names of the session (≥ ``MIN_NAMES_PER_SESSION``), then averaged — on two returns: the EXECUTABLE one
  ``adjusted_close(T + 1 + h) / adjusted_close(T + 1) − 1`` (entry at the close of ``T + 1``: what a buyer acting on the
  night's list can earn; DECISORY since rev 2) and the total return ``adjusted_close(T + h) / adjusted_close(T) − 1``
  (descriptive: it starts at the close of ``T`` and may see what was published after that close — an after-hours
  filing, a Radar event, a record published up to the close of ``T + 1``);
* the decile spread — top minus bottom decile of upside, mean return (sessions with ≥ ``MIN_NAMES_DECILES``), on both
  returns (the executable one is a condition of the pass);
* the log-MSE of the TP PRO-RATED to the horizon (``P̂ = price · (tp / price)^(h / 252)``: a 12-month target read at
  ``h`` sessions) against the random walk (``tp = price``) and, on the common mask, against the persisted consensus
  pro-rated the same way — pooled ratio plus a per-session Diebold–Mariano difference (descriptive);
* the return of the buy list against the universe of the session, on both returns — the decider's COMPRA_PERMITIDA
  does not exist in the store yet, so v1 reads the PROXY ``decomposition.status == "full_match"`` (the producer's own
  buy class, persisted in the record), labelled ``decisory: false``;
* block standard errors for overlapping horizons: the per-session statistics are grouped in consecutive blocks of ``h``
  calendar sessions from the partition's anchor; only COMPLETE blocks (every session of the block matured) count; the
  estimate is the mean of the block means and its variance is inflated by ``1 + 2ρ₁ = 1.5`` (ρ₁ = 1/4, the lag-1
  correlation of adjacent block means under overlapping h-session returns); Student t with ``B − 1`` degrees of
  freedom (implemented here: no scipy in the image). Newey–West (Bartlett, lag ``h``) is reported beside it,
  diagnostic only;
* the pre-registered verdict on the HOLDOUT at the primary horizon on the executable IC (``verdict``): NOT_YET_MATURE →
  UNMEASURED → HARM → INSUFFICIENT → SIGNAL_PASS / CONTINUE / INCONCLUSIVE, alpha 0.003 at every interim look and 0.04
  at the final look of ``FINAL_BLOCKS`` blocks (total size ≈ 0.05 under the overlap model: ``simulate_design``, which
  also gives the power and the minimum detectable IC the prereg publishes). The development partition never has a
  verdict.

The receipt carries NO symbol (aggregates only, canonical JSON, ``payload_sha256``) and no wall clock in its payload:
it is a function of (cut, store, parameters, code). The CODE is bound to the prereg (§10): the payload carries the
sha256 of every pinned module and object (``code_fingerprint``) and the comparison with the pins the prereg lists
(``code_binding``); a reading whose code is not the pinned one is VOID. The process forces a read-only database session
(``PGOPTIONS=-c default_transaction_read_only=on``) and talks to the store through ``ReadOnlyStore``, which exposes the
four readers the report needs and nothing else; the price reader's HTTP client raises on any call (the panel's).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import logging
import math
import os
import random
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence, cast

import exchange_calendars as xcals

from . import valuation_panel as panel
from . import valuation_price_history as price_history_module
from .config import get_settings
from .database import Database
from .valuation_official import canonical_sha256
from .valuation_official_engine import SOURCE_BLEND, SOURCE_INTERNAL
from .valuation_price_history import PriceHistoryService

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "VALUATION-ACCURACY-REPORT-v1"
PREREG = "PREREG_VALUATION_DECISOR_V1"
PREREG_REVISION = 2
DEFAULT_SOURCES: tuple[str, ...] = (SOURCE_BLEND, SOURCE_INTERNAL)
MARKET_GROUPS: dict[str, tuple[str, ...]] = {"B3": ("B3",), "US": ("NASDAQ", "NYSE")}  # one calendar and one currency per group
# --- protocol constants, pre-registered (PREREG_VALUATION_DECISOR_V1 §15); every one of them travels inside the hashed payload
HORIZONS: tuple[int, ...] = (21, 63, 126)  # sessions; 63/126 descriptive only
PRIMARY_HORIZON = 21
EXECUTION_LAG_SESSIONS = 1  # the executable return enters at the close of T + 1
DECISORY_STATISTIC = "ic_executable"  # rev 2: the verdict reads the EXECUTABLE return; the T → T + h one may see the night after T's close
TP_HORIZON_SESSIONS = 252  # the 12-month horizon a TP (and the consensus, "12m") declares: the pro-rata exponent is h / 252
CONSENSUS_HORIZON = "12m"
SCOPE = "universe"  # targeted (on-demand) records are a selection by request: outside the cross-section, counted
MIN_NAMES_PER_SESSION = 10
MIN_NAMES_DECILES = 30
DECILES = 10
BUY_LIST_PROXY = "proxy:decomposition.status=full_match"
BUY_LIST_PROXY_STATUS = "full_match"
ATTRITION_CAP = panel.ATTRITION_CAP
MIN_BLOCKS = 5
FINAL_BLOCKS = 24  # rev 2: two years of 21-session blocks — one year cannot detect a useful IC (the power table of the prereg)
FINAL_DEADLINE = date(2029, 1, 31)  # a look whose cut is on/after this date is FINAL whatever B (producer gaps cannot stretch the protocol)
ADJACENT_BLOCK_VARIANCE_FACTOR = 1.5  # 1 + 2ρ₁ with ρ₁ = 1/4 (block length = h, triangular autocorrelation of overlapping returns)
ALPHA_INTERIM = 0.003  # at every look B = MIN_BLOCKS … FINAL_BLOCKS − 1; with ALPHA_FINAL the total size is ≈ 0.05 (simulate_design)
ALPHA_FINAL = 0.04
ALPHA_HARM = 0.025  # per look, uncorrected: the cumulative false HARM under IC = 0 is ≈ 0.11 (declared in the prereg, simulate_design)
IC_MIN = 0.02
READ_ONLY_PGOPTION = "-c default_transaction_read_only=on"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# --- the code the numbers come from, bound to the prereg (§10 and §17): the prereg lists one pin per line,
#     ``file <path> <sha256>`` / ``object <name> <sha256>``; the payload carries the fingerprint of the running code; a
#     reading whose fingerprint is not the pinned one is VOID (and the workflow refuses to publish it).
#     Whole files for the instrument (this report, the panel, the price series and its readers); single objects of the
#     modules shared with the producer (valuation_official: the producer's changes are part of the object measured) and
#     with the whole app (database: the four readers and what they call).
PINNED_FILES: tuple[str, ...] = ("valuation_accuracy_report.py", "valuation_panel.py", "valuation_price_history.py")
PINNED_OBJECTS: tuple[str, ...] = (
    "valuation_official.CALENDARS", "valuation_official.SESSION_ZONES", "valuation_official.PREDICTION_SCHEMA",
    "valuation_official.LEGACY_PREDICTION_SCHEMA", "valuation_official._calendar", "valuation_official._utc",
    "valuation_official.canonical_sha256", "valuation_official.session_date_of", "valuation_official.stored_prediction",
    "valuation_official._stored_as_legacy",
    "database.Database._PREDICTION_KEYS", "database.Database._PREDICTION_ORDER", "database.Database._PRICE_BAR_KEYS",
    "database.Database._prediction_record", "database.Database._stored_prediction", "database.Database._prediction_order_key",
    "database.Database._selection_instant", "database.Database._price_bar_instant", "database.Database.list_valuation_predictions_in_window",
    "database.Database.latest_analysis_snapshot_before", "database.Database.analysis_snapshot_by_id", "database.Database.price_bars",
)
_PIN_LINE = re.compile(r"^(file|object) (\S+) ([0-9a-f]{64})$")
# --- the operating characteristics the prereg publishes (§9-bis): reproducible with ``design_table()`` from this module
DESIGN_SEED = 20261017
DESIGN_REPS = 20000
DESIGN_SDS: tuple[float, ...] = (0.06, 0.08, 0.10, 0.12)  # sd of the per-session decisory IC (sampling + time variation)
DESIGN_ICS: tuple[float, ...] = (-0.05, -0.03, 0.0, 0.02, 0.03, 0.05, 0.08)
DESIGN_POWER = 0.80


def protocol() -> dict[str, Any]:
    """The pre-registered constants, as the receipt carries them (inside the hashed payload)."""
    return {
        "schema": SCHEMA_VERSION,
        "prereg": PREREG,
        "prereg_revision": PREREG_REVISION,
        "market_groups": {group: list(markets) for group, markets in MARKET_GROUPS.items()},
        "horizons_sessions": list(HORIZONS),
        "primary_horizon": PRIMARY_HORIZON,
        "execution_lag_sessions": EXECUTION_LAG_SESSIONS,
        "decisory_statistic": DECISORY_STATISTIC,
        "tp_horizon_sessions": TP_HORIZON_SESSIONS,
        "consensus_horizon": CONSENSUS_HORIZON,
        "scope": SCOPE,
        "min_names_per_session": MIN_NAMES_PER_SESSION,
        "min_names_deciles": MIN_NAMES_DECILES,
        "deciles": DECILES,
        "buy_list": BUY_LIST_PROXY,
        "buy_list_decisory": False,
        "attrition_cap": ATTRITION_CAP,
        "attrition_decisory": "executable pair: denominator = target T + 1 + h closed before the cut; unavailable = either label of the pair missing",
        "min_blocks": MIN_BLOCKS,
        "final_blocks": FINAL_BLOCKS,
        "final_deadline": FINAL_DEADLINE.isoformat(),
        "block_length": "h sessions of the market calendar from the partition anchor; complete blocks only",
        "look": "every reading whose B (complete blocks of the decisory statistic) is new; B >= min_blocks",
        "adjacent_block_variance_factor": ADJACENT_BLOCK_VARIANCE_FACTOR,
        "alpha_interim": ALPHA_INTERIM,
        "alpha_final": ALPHA_FINAL,
        "alpha_harm": ALPHA_HARM,
        "harm": "decisory statistic at the primary horizon only, p_less <= alpha_harm at every look (uncorrected)",
        "ic_min": IC_MIN,
        "pass": "decisory IC estimate >= ic_min, its p_greater <= the look's alpha, executable decile spread estimate > 0",
        "verdict_order": ["NOT_YET_MATURE", "UNMEASURED", "HARM", "INSUFFICIENT", "SIGNAL_PASS|CONTINUE|INCONCLUSIVE"],
        "upside": "tp / price - 1 (the record's tp and price)",
        "return": "adjusted_close(T + h) / adjusted_close(T) - 1, same vintage (total return): descriptive",
        "return_executable": "adjusted_close(T + 1 + h) / adjusted_close(T + 1) - 1: decisory",
        "log_error": "ln(price * (tp / price)^(h / 252) * a(T)) - ln(adjusted_close(T + h)); random walk: tp = price",
        "cohort": "live (valuation_panel R3 a)",
        "admissibility": "valuation_panel.admissible_records",
        "label_convention": panel.LABEL_CONVENTION,
        "tol_basis": panel.TOL_BASIS,
        "calendar": {"markets": dict(panel.CALENDARS)},  # the library's version is a fact of the running code: payload.code
        "code_pins": {"files": list(PINNED_FILES), "objects": list(PINNED_OBJECTS)},
        "gate": False,
    }


# ------------------------------------------------------------------ pure statistics (no store, no clock)
def _finite(value: float) -> float:
    return panel._finite(value)


def _mean(values: Sequence[float]) -> float | None:
    return _finite(math.fsum(values) / len(values)) if values else None


def average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks 1..n, ties at their average rank (the Spearman convention)."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        rank = (start + end) / 2 + 1
        for index in order[start:end + 1]:
            ranks[index] = rank
        start = end + 1
    return ranks


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation; ``None`` below two points or when either side has no variance (the session is degenerate)."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x, mean_y = math.fsum(xs) / n, math.fsum(ys) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    syy = math.fsum((y - mean_y) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return _finite(max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy))))


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman's rank correlation: Pearson on average ranks (ties handled)."""
    return pearson(average_ranks(xs), average_ranks(ys))


def decile_of(rank: float, n: int) -> int:
    """The decile (0 = lowest upside … ``DECILES − 1`` = highest) of an average rank among ``n``: tied names share it."""
    return min(DECILES - 1, max(0, int((rank - 0.5) * DECILES / n)))


def decile_spread(upsides: Sequence[float], returns: Sequence[float]) -> float | None:
    """Mean return of the top decile of upside minus the bottom decile's; ``None`` when either decile is empty."""
    ranks = average_ranks(upsides)
    n = len(upsides)
    top = [value for rank, value in zip(ranks, returns) if decile_of(rank, n) == DECILES - 1]
    bottom = [value for rank, value in zip(ranks, returns) if decile_of(rank, n) == 0]
    if not top or not bottom:
        return None
    return _finite(math.fsum(top) / len(top) - math.fsum(bottom) / len(bottom))


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    result = d
    for m in range(1, 400):
        m2 = 2 * m
        numerator = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + numerator * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + numerator / c
        c = c if abs(c) > tiny else tiny
        result *= d * c
        numerator = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + numerator * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + numerator / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return result


def regularized_beta(x: float, a: float, b: float) -> float:
    """``I_x(a, b)``, the regularized incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: float) -> float:
    """``P(T_df ≥ t)`` for Student's t with ``df`` degrees of freedom."""
    if df <= 0:
        raise ValueError(f"degrees of freedom must be positive, got {df}")
    tail = 0.5 * regularized_beta(df / (df + t * t), df / 2.0, 0.5)
    return _finite(tail if t >= 0 else 1.0 - tail)


def student_t_isf(alpha: float, df: float) -> float:
    """The critical ``t`` with ``P(T_df ≥ t) = alpha`` (bisection on ``student_t_sf`` to 1e-12): ``p_greater ≤ alpha``
    exactly when ``t`` is at or above it — what the design simulation compares, instead of a p-value per look."""
    if not 0.0 < alpha < 0.5:
        raise ValueError(f"alpha must lie in (0, 0.5), got {alpha}")
    low, high = 0.0, 1.0
    while student_t_sf(high, df) > alpha:
        low, high = high, high * 2.0
    while high - low > 1e-12:
        middle = (low + high) / 2.0
        if student_t_sf(middle, df) > alpha:
            low = middle
        else:
            high = middle
    return high


def newey_west(values: Sequence[float], lag: int) -> dict[str, Any]:
    """The HAC standard error of the mean of a series (Bartlett kernel, ``lag``), positional: a gap in the sessions is
    not a lag. Diagnostic beside the block estimate; ``None`` when the series is not longer than ``lag + 1``."""
    n = len(values)
    result: dict[str, Any] = {"lag": lag, "n": n, "mean": _mean(values), "se": None, "t": None}
    if n <= lag + 1:
        return result
    mean = math.fsum(values) / n
    deviations = [value - mean for value in values]
    variance = math.fsum(d * d for d in deviations) / n
    for k in range(1, lag + 1):
        variance += 2.0 * (1.0 - k / (lag + 1.0)) * math.fsum(deviations[t] * deviations[t - k] for t in range(k, n)) / n
    if variance <= 0.0:
        return result
    se = math.sqrt(variance / n)
    result.update({"se": _finite(se), "t": _finite(mean / se)})
    return result


def batch_means_test(means: Sequence[float]) -> dict[str, Any]:
    """The test of PREREG §5 on the COMPLETE block means: ``estimate`` = their mean; ``se = sqrt(ADJACENT_BLOCK_VARIANCE_FACTOR)
    · sd(means) / sqrt(B)`` (sample sd, ``B − 1``); Student t with ``B − 1`` degrees of freedom (``p_greater`` =
    P(T ≥ t), ``p_less`` = P(T ≤ t)). Below two blocks there is no se; with ``se = 0`` there is no test (never an
    infinite t)."""
    result: dict[str, Any] = {"estimate": _mean(means), "se": None, "t": None, "df": max(0, len(means) - 1), "p_greater": None, "p_less": None}
    if len(means) >= 2:
        center = math.fsum(means) / len(means)
        sd = math.sqrt(math.fsum((mean - center) ** 2 for mean in means) / (len(means) - 1))
        se = math.sqrt(ADJACENT_BLOCK_VARIANCE_FACTOR) * sd / math.sqrt(len(means))
        if se > 0.0:
            t = center / se
            result.update({"se": _finite(se), "t": _finite(t), "p_greater": student_t_sf(t, len(means) - 1), "p_less": student_t_sf(-t, len(means) - 1)})
        else:
            result["se"] = 0.0
    return result


def block_statistics(points: Iterable[tuple[int, float]], *, block_length: int, mature_through: int | None,
                     partition_last: int | None = None) -> dict[str, Any]:
    """Batch means for a per-session statistic of an overlapping horizon. ``points`` are ``(session index from the
    partition's anchor, value)``; block ``b`` holds the indices ``[b·m, (b+1)·m)`` with ``m = block_length``. A block is
    COMPLETE when its last session that belongs to the partition (``partition_last`` caps it) is at or before
    ``mature_through`` (the last session whose target closed before the cut); the others are ``blocks_pending``, and a
    complete block without any value is ``blocks_empty`` (not counted). The test is ``batch_means_test`` over the
    complete block means; ``mean_per_session`` over every point, pending included (each session's value is final once
    measured). Newey–West over the points of the complete blocks, lag = m."""
    if block_length <= 0:
        raise ValueError("block_length must be positive")
    ordered = sorted(points)
    by_block: dict[int, list[float]] = {}
    for index, value in ordered:
        if index < 0:
            raise ValueError(f"session index {index} precedes the partition anchor")
        by_block.setdefault(index // block_length, []).append(float(value))
    last_complete = -1
    if mature_through is not None and mature_through >= 0:
        if partition_last is not None and partition_last <= mature_through:
            last_complete = partition_last // block_length
        else:
            last_complete = (mature_through + 1) // block_length - 1
    complete = [block for block in sorted(by_block) if block <= last_complete]
    means = [math.fsum(by_block[block]) / len(by_block[block]) for block in complete]
    return {
        "block_length": block_length, "blocks": len(complete), "blocks_pending": sum(1 for block in by_block if block > last_complete),
        "blocks_empty": max(0, last_complete + 1 - len(complete)), "sessions": sum(len(by_block[block]) for block in complete),
        "mean_per_session": _mean([value for _index, value in ordered]), **batch_means_test(means), "variance_factor": ADJACENT_BLOCK_VARIANCE_FACTOR,
        "newey_west": newey_west([value for index, value in ordered if index // block_length <= last_complete], block_length),
    }


def _ratio(numerator: float | None, denominator: float | None) -> float | str:
    if numerator is None or denominator is None or denominator == 0.0:
        return "N/D"
    return _finite(numerator / denominator)


# ------------------------------------------------------------------ the design: operating characteristics of the verdict (prereg §9-bis)
def simulate_design(ic: float, sd: float, *, reps: int, seed: int, block_length: int | None = None) -> dict[str, Any]:
    """The operating characteristics of the pre-registered sequential test under the overlap model of §5: the daily
    decisory IC is ``ic + sd · N_t`` where ``N_t`` is the normalised moving sum of ``h`` independent standard normals
    (unit variance, autocorrelation ``1 − k/h`` — the triangular shape of overlapping h-session returns), ``h`` = the
    primary horizon, over ``FINAL_BLOCKS`` blocks of ``h`` sessions; at every look ``B = MIN_BLOCKS … FINAL_BLOCKS`` the
    verdict's own order on ``batch_means_test``'s statistic — HARM (``p_less ≤ ALPHA_HARM``) before a pass (estimate ≥
    ``IC_MIN`` and ``p_greater ≤`` the look's alpha: ``ALPHA_INTERIM`` before the last block, ``ALPHA_FINAL`` at it),
    compared through the critical ``t`` (``student_t_isf``). Neither attrition nor the decile-spread condition is
    modelled (the pass probabilities are upper bounds). Deterministic for a seed (Python's Mersenne Twister). Returns the
    probabilities of SIGNAL_PASS (and of a pass at an interim look), HARM and INCONCLUSIVE at the end of the protocol."""
    if reps <= 0 or sd <= 0.0:
        raise ValueError("reps and sd must be positive")
    h = block_length or PRIMARY_HORIZON
    rng = random.Random(seed)
    looks = range(MIN_BLOCKS, FINAL_BLOCKS + 1)
    critical_pass = {blocks: student_t_isf(ALPHA_FINAL if blocks == FINAL_BLOCKS else ALPHA_INTERIM, blocks - 1) for blocks in looks}
    critical_harm = {blocks: student_t_isf(ALPHA_HARM, blocks - 1) for blocks in looks}
    factor, scale, sessions = math.sqrt(ADJACENT_BLOCK_VARIANCE_FACTOR), sd / math.sqrt(h), FINAL_BLOCKS * h
    passed = passed_interim = harmed = 0
    for _ in range(reps):
        walk, total = [0.0], 0.0  # walk[j] = sum of the first j normals; N_t = (walk[t + h] − walk[t]) / sqrt(h)
        for _step in range(sessions + h - 1):
            total += rng.gauss(0.0, 1.0)
            walk.append(total)
        area, running = [0.0], 0.0  # area[j] = sum of walk[0 … j − 1]: a block mean in O(1)
        for value in walk:
            running += value
            area.append(running)
        means = [ic + scale * ((area[b * h + 2 * h] - area[b * h + h]) - (area[b * h + h] - area[b * h])) / h for b in range(FINAL_BLOCKS)]
        for blocks in looks:
            window = means[:blocks]
            center = math.fsum(window) / blocks
            se = factor * math.sqrt(math.fsum((m - center) ** 2 for m in window) / (blocks - 1)) / math.sqrt(blocks)
            if se <= 0.0:
                continue
            t = center / se
            if t <= -critical_harm[blocks]:
                harmed += 1
                break
            if center >= IC_MIN and t >= critical_pass[blocks]:
                passed += 1
                passed_interim += blocks < FINAL_BLOCKS
                break
    return {"ic": ic, "sd": sd, "reps": reps, "seed": seed, "block_length": h, "signal_pass": passed / reps, "signal_pass_interim": passed_interim / reps,
            "harm": harmed / reps, "inconclusive": (reps - passed - harmed) / reps}


def minimum_detectable_ic(sd: float, *, power: float = DESIGN_POWER, reps: int = DESIGN_REPS, seed: int = DESIGN_SEED) -> float:
    """The smallest IC (to 0.001) whose probability of SIGNAL_PASS reaches ``power`` — bisection over common random
    numbers (one seed: the pass is monotone in the IC for every simulated path)."""
    low, high = 0.0, 0.30
    while high - low > 0.0005:
        middle = (low + high) / 2.0
        if simulate_design(middle, sd, reps=reps, seed=seed)["signal_pass"] >= power:
            high = middle
        else:
            low = middle
    return round(high, 3)


def design_table(*, reps: int = DESIGN_REPS, seed: int = DESIGN_SEED, sds: Sequence[float] = DESIGN_SDS,
                 ics: Sequence[float] = DESIGN_ICS) -> dict[str, Any]:
    """The operating characteristics the prereg publishes (§9-bis): every (sd, IC) cell and the minimum detectable IC
    at ``DESIGN_POWER`` per sd. ``python -c "import json; from app.valuation_accuracy_report import design_table;
    print(json.dumps(design_table(), sort_keys=True))"`` reproduces it (minutes; no store, no network)."""
    return {"model": "daily IC = ic + sd * normalised moving sum of h normals (triangular autocorrelation)", "reps": reps, "seed": seed,
            "horizon": PRIMARY_HORIZON, "min_blocks": MIN_BLOCKS, "final_blocks": FINAL_BLOCKS, "alpha_interim": ALPHA_INTERIM,
            "alpha_final": ALPHA_FINAL, "alpha_harm": ALPHA_HARM, "ic_min": IC_MIN,
            "cells": [simulate_design(ic, sd, reps=reps, seed=seed) for sd in sds for ic in ics],
            "minimum_detectable_ic": {f"{sd:.2f}": minimum_detectable_ic(sd, reps=reps, seed=seed) for sd in sds}, "power": DESIGN_POWER}


# ------------------------------------------------------------------ one observation at one horizon (the report's quantities)
def point(row: Mapping[str, Any], horizon: int) -> dict[str, Any] | None:
    """The report's quantities for a panel observation at ``horizon`` — ``None`` when neither the label at ``h`` (the
    panel's ``e_source`` set: basis verified) nor the executable pair (labels at ``1`` and ``h + 1``) is there: the
    upside; the total return T → T+h, the pro-rated log-errors of the source, of the random walk and — when the
    persisted consensus is ``present`` and declares ``12m`` — of the consensus (else its exclusion cause), all ``None``
    without the label at ``h``; the executable return T+1 → T+1+h (``None`` without both labels of the pair); and the
    buy-list flag."""
    entry = row["horizons"][str(horizon)]
    entry_lag = row["horizons"].get(str(EXECUTION_LAG_SESSIONS)) or {}
    entry_exit = row["horizons"].get(str(horizon + EXECUTION_LAG_SESSIONS)) or {}
    executable: float | None = None
    if entry_lag.get("e_source") is not None and entry_exit.get("e_source") is not None:
        executable = _finite(float(entry_exit["realized"]) / float(entry_lag["realized"]) - 1.0)
    labelled = entry.get("e_source") is not None
    if not labelled and executable is None:
        return None
    tp, price = float(row["tp"]), float(row["price"])  # a label (any) implies the basis check passed: the price is there
    item: dict[str, Any] = {
        "symbol": str(row["symbol"]), "session": str(row["session"]), "upside": _finite(tp / price - 1.0), "return": None,
        "return_executable": executable, "e_model": None, "e_random_walk": None, "e_consensus": None, "consensus_cause": None,
        "listed": row.get("producer_status") == BUY_LIST_PROXY_STATUS,
    }
    if not labelled:
        return item
    adjustment, close = float(row["adjustment"]), float(row["close_at_session"])
    realized = float(entry["realized"])
    exponent = horizon / TP_HORIZON_SESSIONS
    e_random_walk = math.log(price * adjustment) - math.log(realized)
    consensus_cause = str(row.get("consensus_status"))
    consensus = row.get("consensus") or {}
    if consensus_cause == panel.CONSENSUS_PRESENT:
        if str(consensus.get("horizon")) != CONSENSUS_HORIZON:
            consensus_cause = "consensus_horizon_not_12m"
        else:
            item["e_consensus"] = _finite(e_random_walk + exponent * math.log(float(consensus["tp"]) / price))
    item.update({"return": _finite(realized / (close * adjustment) - 1.0), "e_model": _finite(e_random_walk + exponent * math.log(tp / price)),
                 "e_random_walk": _finite(e_random_walk), "consensus_cause": consensus_cause})
    return item


def executable_attrition(rows: Sequence[Mapping[str, Any]], horizon: int) -> dict[str, Any]:
    """The attrition of the DECISORY return (§10): denominator = the observations whose exit target ``T + 1 + h`` closed
    before the cut (eligible at ``h + 1``, the panel's sense — ``not_yet_mature``/``beyond_calendar`` stay outside);
    unavailable = those without both labels of the executable pair, by cause (the exit's own; else ``entry:<cause>``)."""
    exit_key, entry_key = str(horizon + EXECUTION_LAG_SESSIONS), str(EXECUTION_LAG_SESSIONS)
    eligible = [row for row in rows if row["horizons"][exit_key]["eligible"]]
    unavailable: Counter[str] = Counter()
    for row in eligible:
        exit_label, entry_label = row["horizons"][exit_key], row["horizons"][entry_key]
        if exit_label["e_source"] is None:
            unavailable[str(exit_label["status"])] += 1
        elif entry_label["e_source"] is None:
            unavailable[f"entry:{entry_label['status']}"] += 1
    missing = sum(unavailable.values())
    return {"eligible": len(eligible), "rate": _finite(missing / len(eligible)) if eligible else None, "unavailable": missing,
            "by_cause": panel._counts(unavailable)}


# ------------------------------------------------------------------ per-session statistics and the metrics of one horizon
_STATISTICS: dict[str, tuple[str, str]] = {  # name → (what is computed per session, the point's field it needs)
    "ic": ("rank_ic", "return"),
    "ic_executable": ("rank_ic", "return_executable"),
    "decile_spread": ("decile_spread", "return"),
    "decile_spread_executable": ("decile_spread", "return_executable"),
    "buy_list_excess": ("buy_list_excess", "return"),
    "buy_list_excess_executable": ("buy_list_excess", "return_executable"),
    "mse_vs_random_walk": ("mse_vs_random_walk", "e_model"),
    "mse_vs_consensus": ("mse_vs_consensus", "e_model"),
}


def _session_statistic(points: Sequence[Mapping[str, Any]], statistic: str) -> tuple[float | None, str]:
    """One session's value of ``statistic`` over the points that carry its return, and, without one, why:
    ``below_min_names`` / ``degenerate`` / ``no_list`` / ``no_label`` / ``no_consensus``."""
    if statistic not in _STATISTICS:
        raise ValueError(f"unknown statistic {statistic!r}")
    kind, field = _STATISTICS[statistic]
    usable = [p for p in points if p[field] is not None]
    if kind == "rank_ic":
        if len(usable) < MIN_NAMES_PER_SESSION:
            return None, "below_min_names"
        value = spearman([p["upside"] for p in usable], [p[field] for p in usable])
        return value, "ok" if value is not None else "degenerate"
    if kind == "decile_spread":
        if len(usable) < MIN_NAMES_DECILES:
            return None, "below_min_names"
        value = decile_spread([p["upside"] for p in usable], [p[field] for p in usable])
        return value, "ok" if value is not None else "degenerate"
    if kind == "buy_list_excess":
        if len(usable) < MIN_NAMES_PER_SESSION:
            return None, "below_min_names"
        listed = [p[field] for p in usable if p["listed"]]
        if not listed:
            return None, "no_list"
        return _finite(math.fsum(listed) / len(listed) - math.fsum(p[field] for p in usable) / len(usable)), "ok"
    if kind == "mse_vs_random_walk":
        if not usable:
            return None, "no_label"
        return _finite(math.fsum(p["e_model"] ** 2 for p in usable) / len(usable) - math.fsum(p["e_random_walk"] ** 2 for p in usable) / len(usable)), "ok"
    common = [p for p in usable if p["e_consensus"] is not None]
    if not common:
        return None, "no_consensus"
    return _finite(math.fsum(p["e_model"] ** 2 for p in common) / len(common) - math.fsum(p["e_consensus"] ** 2 for p in common) / len(common)), "ok"


def _series(by_session: Mapping[str, Sequence[Mapping[str, Any]]], statistic: str, index_of: Mapping[str, int], *, block_length: int,
            mature_through: int | None, partition_last: int | None) -> dict[str, Any]:
    values: list[tuple[int, float]] = []
    causes: Counter[str] = Counter()
    for session in sorted(by_session):
        value, cause = _session_statistic(by_session[session], statistic)
        causes[cause] += 1
        if value is not None:
            values.append((index_of[session], value))
    return {"sessions_measured": causes.pop("ok", 0), "sessions_not_measured": panel._counts(causes), "mature_through_index": mature_through,
            "blocks": block_statistics(values, block_length=block_length, mature_through=mature_through, partition_last=partition_last)}


def _mse_label(ratio: float | str) -> str:
    if not isinstance(ratio, float):
        return "UNMEASURED"
    return "BETTER" if ratio < 1.0 else "NOT_BETTER"


def horizon_report(rows: Sequence[Mapping[str, Any]], horizon: int, *, index_of: Mapping[str, int], mature_through: Mapping[int, int | None],
                   partition_last: int | None) -> dict[str, Any]:
    """Every metric of PREREG_VALUATION_DECISOR_V1 at one horizon over one partition's live universe observations.
    ``index_of`` maps a session (ISO) to its calendar index from the partition's anchor; ``mature_through[k]`` is the
    index of the last session whose target ``T + k`` closed before the cut (``None``: none) — ``h`` for the statistics of
    the total return, ``h + 1`` for the executable ones. Aggregates only."""
    attrition_view = panel.horizon_metrics(rows, horizon)
    points = [p for p in (point(row, horizon) for row in rows) if p is not None]
    by_session: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(points, key=lambda p: (p["session"], p["symbol"])):
        by_session.setdefault(item["session"], []).append(item)
    series = {name: _series(by_session, name, index_of, block_length=horizon,
                            mature_through=mature_through.get(horizon + EXECUTION_LAG_SESSIONS if field == "return_executable" else horizon),
                            partition_last=partition_last)
              for name, (_kind, field) in _STATISTICS.items()}
    labelled = [p for p in points if p["return"] is not None]
    executable = [p for p in points if p["return_executable"] is not None]
    common = [p for p in labelled if p["e_consensus"] is not None]
    mse_model = _mean([p["e_model"] ** 2 for p in labelled])
    mse_random_walk = _mean([p["e_random_walk"] ** 2 for p in labelled])
    mse_model_common = _mean([p["e_model"] ** 2 for p in common])
    mse_consensus = _mean([p["e_consensus"] ** 2 for p in common])
    ratio_random_walk, ratio_consensus = _ratio(mse_model, mse_random_walk), _ratio(mse_model_common, mse_consensus)
    listed_per_session = [sum(1 for p in items if p["listed"]) for items in by_session.values()]
    return {
        "horizon_sessions": horizon,
        "primary": horizon == PRIMARY_HORIZON,
        "eligible": attrition_view["eligible"],
        "ineligible": attrition_view["ineligible"],
        "labelled": attrition_view["labelled"],
        "attrition": attrition_view["attrition"],
        "attrition_executable": executable_attrition(rows, horizon),
        "observations": panel._mask_stats(labelled),
        "observations_executable": panel._mask_stats(executable),
        "ic": series["ic"],
        "ic_executable": {**series["ic_executable"], "labelled_without_executable_return": sum(1 for p in labelled if p["return_executable"] is None)},
        "decile_spread": series["decile_spread"],
        "decile_spread_executable": series["decile_spread_executable"],
        "buy_list_excess": {**series["buy_list_excess"], "list": BUY_LIST_PROXY, "decisory": False,
                            "mean_listed_per_session": _mean([float(count) for count in listed_per_session])},
        "buy_list_excess_executable": {**series["buy_list_excess_executable"], "list": BUY_LIST_PROXY, "decisory": False},
        "log_mse_vs_random_walk": {"n": len(labelled), "mse_model": mse_model, "mse_random_walk": mse_random_walk, "ratio": ratio_random_walk,
                                   "label": _mse_label(ratio_random_walk), "decisory": False, "per_session_difference": series["mse_vs_random_walk"]},
        "log_mse_vs_consensus": {"n": len(common), "excluded": panel._counts(Counter(str(p["consensus_cause"]) for p in labelled if p["e_consensus"] is None)),
                                 "mse_model": mse_model_common, "mse_consensus": mse_consensus, "ratio": ratio_consensus, "label": _mse_label(ratio_consensus),
                                 "decisory": False, "per_session_difference": series["mse_vs_consensus"]},
        "log_mse_raw_tp": attrition_view["source"],  # the panel's §2.6 error of the unscaled 12-month TP at h: diagnostic
    }


# ------------------------------------------------------------------ the pre-registered verdict (holdout, primary horizon, executable IC)
def verdict(horizons: Mapping[str, Mapping[str, Any]], *, final_by_deadline: bool = False) -> dict[str, Any]:
    """PREREG_VALUATION_DECISOR_V1 §7, in order, over the HOLDOUT, on the decisory statistic (the executable IC at the
    primary horizon): no exit target of the partition closed before the cut → ``NOT_YET_MATURE`` (not a reading); targets
    matured but no eligible observation, or the executable attrition above the cap → ``UNMEASURED``; the IC
    significantly NEGATIVE with ``B ≥ MIN_BLOCKS`` complete blocks (``p_less ≤ ALPHA_HARM``) → ``HARM``; fewer than
    ``MIN_BLOCKS`` blocks → ``INSUFFICIENT`` (``INCONCLUSIVE`` at the deadline); then the look is ``FINAL`` with ``B ≥
    FINAL_BLOCKS`` or ``final_by_deadline`` (the cut on/after ``FINAL_DEADLINE``; alpha ``ALPHA_FINAL``), else
    ``INTERIM`` (alpha ``ALPHA_INTERIM``), and the signal passes when the IC estimate ≥ ``IC_MIN``, its ``p_greater ≤
    alpha`` and the executable decile spread estimate > 0 → ``SIGNAL_PASS`` (the buy list is not decisory in v1: a full
    ``PASS`` needs the decider's own list); otherwise ``CONTINUE`` at an interim look, ``INCONCLUSIVE`` at the final
    one. The total return T → T+h, the other horizons and the log-MSE never enter. Never a gate: the mesa acts on it."""
    primary = horizons[str(PRIMARY_HORIZON)]
    decisory = primary[DECISORY_STATISTIC]
    blocks = decisory["blocks"]
    result: dict[str, Any] = {"status": "UNMEASURED", "statistic": DECISORY_STATISTIC, "look": None, "alpha": None, "reasons": [],
                              "horizon_sessions": PRIMARY_HORIZON, "blocks": blocks["blocks"], "blocks_pending": blocks["blocks_pending"],
                              "ic_estimate": blocks["estimate"], "ic_p_greater": blocks["p_greater"], "ic_p_less": blocks["p_less"],
                              "buy_list_decisory": False, "gate": False}
    attrition = primary["attrition_executable"]
    if not attrition["eligible"]:
        matured = decisory["mature_through_index"]
        if matured is None or matured < 0:
            result.update({"status": "NOT_YET_MATURE", "reasons": ["no_target_matured"]})
        else:
            result["reasons"].append("no_eligible_observations")
        return result
    if attrition["rate"] > ATTRITION_CAP:
        result["reasons"].append(f"attrition_above_cap:{attrition['rate']:.4f}>{ATTRITION_CAP}")
        return result
    if blocks["blocks"] >= MIN_BLOCKS and blocks["p_less"] is not None and blocks["p_less"] <= ALPHA_HARM:
        result.update({"status": "HARM", "reasons": [f"ic_executable_negative:p_less={blocks['p_less']:.6f}<={ALPHA_HARM}"]})
        return result
    if blocks["blocks"] < MIN_BLOCKS:
        if final_by_deadline:
            result.update({"status": "INCONCLUSIVE", "look": "FINAL", "reasons": [f"blocks_below_min:{blocks['blocks']}<{MIN_BLOCKS}", "final_deadline"]})
        else:
            result.update({"status": "INSUFFICIENT", "reasons": [f"blocks_below_min:{blocks['blocks']}<{MIN_BLOCKS}"]})
        return result
    final = blocks["blocks"] >= FINAL_BLOCKS or final_by_deadline
    alpha = ALPHA_FINAL if final else ALPHA_INTERIM
    failures = []
    if blocks["estimate"] is None or blocks["estimate"] < IC_MIN:
        failures.append(f"ic_executable_below_min:{blocks['estimate']}<{IC_MIN}")
    if blocks["p_greater"] is None or blocks["p_greater"] > alpha:
        failures.append(f"ic_executable_not_significant:p_greater={blocks['p_greater']}>{alpha}")
    spread = primary["decile_spread_executable"]["blocks"]["estimate"]
    if spread is None or spread <= 0.0:
        failures.append("decile_spread_executable_unmeasured" if spread is None else "decile_spread_executable_not_positive")
    status = "SIGNAL_PASS" if not failures else ("INCONCLUSIVE" if final else "CONTINUE")
    result.update({"status": status, "look": "FINAL" if final else "INTERIM", "alpha": alpha, "reasons": failures})
    return result


# ------------------------------------------------------------------ the code binding (prereg §10 and §17)
def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object_sha256(value: Any) -> str:
    """A function's (method's, class's) source text, else the ``repr`` of a constant — hashed."""
    text = inspect.getsource(value) if inspect.isfunction(value) or inspect.ismethod(value) or inspect.isclass(value) else repr(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_fingerprint(*, build_sha: str | None = None) -> dict[str, Any]:
    """The code the numbers of this run come from: the sha256 of every ``PINNED_FILES`` module (its bytes, as deployed)
    and of every ``PINNED_OBJECTS`` object (source text / constant ``repr``), plus — recorded, never pinned — the
    calendar library's and Python's versions and the deployed revision."""
    package = __package__ or "app"
    here = Path(__file__).resolve().parent
    objects: dict[str, str] = {}
    for qualified in PINNED_OBJECTS:
        module_name, _dot, path = qualified.partition(".")
        value: Any = importlib.import_module(f"{package}.{module_name}")
        for attribute in path.split("."):
            value = getattr(value, attribute)  # a staticmethod read through its class is the plain function
        objects[f"{package}.{qualified}"] = _object_sha256(value)
    return {"files": {f"{package}/{name}": _file_sha256(here / name) for name in PINNED_FILES}, "objects": objects,
            "exchange_calendars": getattr(xcals, "__version__", "unknown"), "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "build_sha": build_sha}


def pins_of(code: Mapping[str, Any]) -> dict[str, str]:
    """A fingerprint as the prereg pins it: ``file <path>`` / ``object <name>`` → sha256."""
    return {**{f"file {path}": digest for path, digest in code["files"].items()}, **{f"object {name}": digest for name, digest in code["objects"].items()}}


def render_pins(code: Mapping[str, Any]) -> str:
    """The pin lines of a fingerprint, sorted — the block §17 of the prereg carries."""
    return "\n".join(f"{key} {digest}" for key, digest in sorted(pins_of(code).items()))


def pins_from_prereg(text: str) -> dict[str, str]:
    """The pins a prereg lists: every line ``<file|object> <name> <sha256>``; the same name pinned twice with two
    hashes is refused."""
    pins: dict[str, str] = {}
    for line in text.splitlines():
        match = _PIN_LINE.match(line.strip())
        if match is None:
            continue
        key = f"{match.group(1)} {match.group(2)}"
        if pins.get(key, match.group(3)) != match.group(3):
            raise ValueError(f"the prereg pins {key} twice with different hashes")
        pins[key] = match.group(3)
    return pins


def bind_code(code: Mapping[str, Any], pins: Mapping[str, str] | None, *, prereg_sha256: str | None) -> dict[str, Any]:
    """The running code against the prereg's pins: ``BOUND`` when a prereg was given and its pins are EXACTLY the
    fingerprint (same names, same hashes); ``UNBOUND`` without a prereg or without pins in it; ``MISMATCH`` otherwise
    (``code_mismatch:<pin>`` — another hash —, ``code_not_fingerprinted:<pin>`` — pinned but not measured by this code
    —, ``code_not_pinned:<pin>`` — measured but not pinned). A reading that is not ``BOUND`` is VOID: every verdict of
    the receipt says so."""
    expected = dict(pins or {})
    actual = pins_of(code)
    if prereg_sha256 is None:
        return {"status": "UNBOUND", "pinned": len(expected), "reasons": ["prereg_not_given"]}
    if not expected:
        return {"status": "UNBOUND", "pinned": 0, "reasons": ["no_code_pins_in_prereg"]}
    reasons = ([f"code_mismatch:{key}" for key in sorted(expected.keys() & actual.keys()) if expected[key] != actual[key]]
               + [f"code_not_fingerprinted:{key}" for key in sorted(expected.keys() - actual.keys())]
               + [f"code_not_pinned:{key}" for key in sorted(actual.keys() - expected.keys())])
    return {"status": "MISMATCH" if reasons else "BOUND", "pinned": len(expected), "reasons": reasons}


# ------------------------------------------------------------------ the calendar grid of a partition
def _calendar_dates(market: str, start: date, end: date) -> list[str]:
    if end < start:
        return []
    return [stamp.date().isoformat() for stamp in price_history_module._calendar(market).sessions_in_range(start.isoformat(), end.isoformat())]


def _first_session_on_or_after(market: str, day: date) -> date:
    return price_history_module._calendar(market).date_to_session(day.isoformat(), direction="next").date()


def _mature_through(market: str, cut: datetime, horizon: int) -> date | None:
    """The last session ``T`` whose target ``T + horizon`` closed strictly before the cut (the maturity of ``label_bar``)."""
    last_closed = panel.last_closed_session(market, cut)
    if last_closed is None:
        return None
    target, _reason = price_history_module.sessions_after(market, date.fromisoformat(last_closed), -horizon)
    return target


# ------------------------------------------------------------------ read-only plumbing
class ReadOnlyStore:
    """The store as the report sees it: the four readers it needs (records by window, the publication/manifest of a
    vintage, the bars) — any other attribute is an ``AttributeError`` (no writer is reachable from the report)."""

    READERS: tuple[str, ...] = ("list_valuation_predictions_in_window", "latest_analysis_snapshot_before", "analysis_snapshot_by_id", "price_bars")

    def __init__(self, database: Any) -> None:
        self._database = database

    def __getattr__(self, name: str) -> Any:
        if name in ReadOnlyStore.READERS:
            return getattr(self._database, name)
        raise AttributeError(f"valuation_accuracy_report is read-only: {name!r} is not one of its readers {ReadOnlyStore.READERS}")


def force_read_only_session(environ: MutableMapping[str, str] | None = None) -> str:
    """Append ``-c default_transaction_read_only=on`` to ``PGOPTIONS`` (libpq reads it at connect time): every
    transaction of this process is read-only in PostgreSQL itself — a write would fail, not just be avoided. Last wins:
    the option is moved to the end whatever came before."""
    env: MutableMapping[str, str] = os.environ if environ is None else environ
    current = env.get("PGOPTIONS", "").replace(READ_ONLY_PGOPTION, " ").split()
    env["PGOPTIONS"] = " ".join([*current, READ_ONLY_PGOPTION])
    return env["PGOPTIONS"]


class _SymbolReader(PriceHistoryService):
    """``PriceHistoryService`` reading one series per symbol and run: ``label_bar`` re-reads the series (a deep copy) on
    every call and the report asks for seven labels per record, symbol after symbol — the last series read is kept and
    handed back (the same object; nothing here mutates it) while the (market, symbol, cut) does not change."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last: tuple[tuple[str, str, str], dict[str, Any]] | None = None

    def series(self, market: str, symbol: str, *, available_before: datetime) -> dict[str, Any]:
        key = (market, symbol.strip().upper(), price_history_module._utc(available_before).isoformat())
        if self._last is not None and self._last[0] == key:
            return self._last[1]
        result = super().series(market, symbol, available_before=available_before)
        self._last = (key, result)
        return result


def label_horizons() -> tuple[int, ...]:
    """Every label a record needs: ``h`` and the executable pair ``(1, h + 1)`` for each horizon."""
    return tuple(sorted({EXECUTION_LAG_SESSIONS, *HORIZONS, *(h + EXECUTION_LAG_SESSIONS for h in HORIZONS)}))


class AccuracyReportService(panel.PanelService):
    """Reads the store as of a cut (through the panel's machinery) and produces the aggregate receipt. Never writes,
    never fetches."""

    def _reader(self) -> PriceHistoryService:
        if self._caller_price_history is not None:
            return self._caller_price_history
        assert self.http is not None and self._settings is not None
        reads = panel._CutReads(self.database)
        reader = _SymbolReader(self._settings, cast(Database, reads), self.http)
        self.reads, self.price_history = reads, reader
        return reader

    def collect(self, market: str, source: str, *, cut: datetime, since: datetime | None, until: datetime | None,
                reader: PriceHistoryService) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """The panel's observations of one market and source (admissible records, labels of the cut's vintage at every
        horizon the report needs, live deadline), each with the record's ``scope`` and producer ``status`` (the buy-list
        proxy). Returns the rows (with symbols: never printed) and the record counts."""
        records = self.database.list_valuation_predictions_in_window(market, source=source, since=since, until=until)
        kept, refusals = panel.admissible_records(records, cut=cut, since=since, until=until)
        calendar_close = panel.calendar_horizon(market)
        horizons = label_horizons()
        rows: list[dict[str, Any]] = []
        current: str | None = None
        bars: dict[str, dict[str, Any]] = {}
        for record in kept:  # ordered by (symbol, session, instant): one series read per symbol
            symbol = str(record["symbol"])
            if symbol != current:
                bars, current = reader.bars(market, symbol, available_before=cut), symbol
            session = date.fromisoformat(str(record["session_date"])[:10])
            labels = {horizon: panel.resolve_label(reader.label_bar(market, symbol, session, horizon, available_before=cut), cut=cut, calendar_close=calendar_close)
                      for horizon in horizons}
            row = panel.observation(record, bars.get(session.isoformat()), labels, deadline=panel.live_deadline(market, panel._utc(record["prediction_instant"])))
            row["scope"] = str(record.get("scope") or "")
            row["producer_status"] = panel._mapping(record.get("decomposition")).get("status")  # the buy-list proxy (the producer's class at night T)
            rows.append(row)
        return rows, {"read": len(records), "admissible": len(kept), "refused": refusals}

    def measure_group(self, group: str, source: str, *, cut: datetime, since: datetime | None, until: datetime | None,
                      holdout_start: date | None, reader: PriceHistoryService, void: Sequence[str] = ()) -> dict[str, Any]:
        """One (market group, source) cell: the observations of every market of the group, the live universe split at
        ``H0``, every horizon's metrics per partition and the holdout's verdict — ``VOID`` with the binding's reasons
        when the code is not the pinned one (``void``). Aggregates only."""
        markets = MARKET_GROUPS[group]
        calendar_market = markets[0]
        rows: list[dict[str, Any]] = []
        read, admissible = 0, 0
        refused: Counter[str] = Counter()
        vintages: dict[str, Any] = {}
        for market in markets:
            market_rows, counts = self.collect(market, source, cut=cut, since=since, until=until, reader=reader)
            rows.extend(market_rows)
            read, admissible = read + counts["read"], admissible + counts["admissible"]
            refused.update(counts["refused"])
            vintages[market] = self._vintage_header(reader, market, cut)
        live = [row for row in rows if row["cohort"] == panel.COHORT_LIVE]
        universe = [row for row in live if row["scope"] == SCOPE]
        holdout_anchor = _first_session_on_or_after(calendar_market, holdout_start) if holdout_start is not None else None
        partitions: dict[str, Any] = {}
        mature = {horizon: _mature_through(calendar_market, cut, horizon) for horizon in label_horizons()}
        last_closed = panel.last_closed_session(calendar_market, cut)
        for name in ("development", "holdout"):
            if name == "development":
                members = [row for row in universe if holdout_anchor is None or row["session"] < holdout_anchor.isoformat()]
                anchor = date.fromisoformat(min(row["session"] for row in members)) if members else None
            else:
                members = [row for row in universe if holdout_anchor is not None and row["session"] >= holdout_anchor.isoformat()]
                anchor = holdout_anchor
            partitions[name] = self._partition(members, calendar_market, anchor=anchor, holdout_anchor=holdout_anchor if name == "development" else None,
                                               last_closed=last_closed, mature=mature)
        holdout = partitions["holdout"]
        if holdout_start is None:
            decided: dict[str, Any] = {"status": "NO_HOLDOUT", "reasons": ["holdout_start_not_given"], "gate": False}
        elif void:
            decided = {"status": "VOID", "reasons": list(void), "gate": False}  # §10: the code is not the pinned one — no verdict is read from it
        else:
            decided = verdict(holdout["horizons"], final_by_deadline=cut.date() >= FINAL_DEADLINE)
        return {
            "records": {"read": read, "admissible": admissible, "refused": panel._counts(refused),
                        "cohort": panel._counts(Counter(str(row["cohort"]) for row in rows)),
                        "scope_live": panel._counts(Counter(str(row["scope"]) for row in live)),
                        "source_versions_live_universe": panel._counts(Counter(str(row["source_version"]) for row in universe))},
            "vintages": vintages,
            "last_closed_session": last_closed,
            "partitions": partitions,
            "verdict": decided,
        }

    def _partition(self, members: list[dict[str, Any]], market: str, *, anchor: date | None, holdout_anchor: date | None,
                   last_closed: str | None, mature: Mapping[int, date | None]) -> dict[str, Any]:
        """One partition's metrics on the calendar grid anchored at ``anchor`` (the development partition: its first
        session, capped by ``holdout_anchor``; the holdout: ``H0``). Without an anchor or a calendar answer for the cut
        the partition is measured empty, never guessed."""
        sessions = sorted({row["session"] for row in members})
        index_of: dict[str, int] = {}
        mature_through: dict[int, int | None] = {}
        partition_last: int | None = None
        if anchor is not None and last_closed is not None:
            grid = _calendar_dates(market, anchor, max(date.fromisoformat(last_closed), date.fromisoformat(sessions[-1]) if sessions else anchor))
            index_of = {session: index for index, session in enumerate(grid)}
            if holdout_anchor is not None:  # the development partition ends at the session before H0
                partition_last = sum(1 for session in grid if session < holdout_anchor.isoformat()) - 1
            for horizon, through in mature.items():
                mature_through[horizon] = None if through is None or through < anchor else sum(1 for session in grid if session <= through.isoformat()) - 1
        measured = members if index_of else []
        return {"anchor": anchor.isoformat() if anchor else None, "first_session": sessions[0] if sessions else None,
                "last_session": sessions[-1] if sessions else None, "observations": len(members), "sessions": len(sessions),
                "partition_last_index": partition_last,
                "horizons": {str(horizon): horizon_report(measured, horizon, index_of=index_of, mature_through=mature_through, partition_last=partition_last)
                             for horizon in HORIZONS}}

    def report(self, *, cut: datetime, groups: Iterable[str] = tuple(MARKET_GROUPS), sources: Iterable[str] = DEFAULT_SOURCES,
               since: datetime | None = None, until: datetime | None = None, holdout_start: date | None = None,
               prereg_sha256: str | None = None, code_pins: Mapping[str, str] | None = None, build_sha: str | None = None) -> dict[str, Any]:
        """The receipt as of ``cut`` (aware, explicit): ``{schema, payload, payload_sha256}`` — no symbol anywhere. The
        payload carries the running code's fingerprint and its binding to the prereg's ``code_pins``; a holdout verdict
        is computed only when the binding is ``BOUND`` (else ``VOID``)."""
        cut_utc = panel._aware(cut, "cut")
        lower = panel._aware(since, "since") if since is not None else None
        upper = panel._aware(until, "until") if until is not None else None
        if lower is not None and upper is not None and lower >= upper:
            raise ValueError(f"since {lower.isoformat()} must precede until {upper.isoformat()}")
        group_list = [group.strip().upper() for group in groups]
        unknown = [group for group in group_list if group not in MARKET_GROUPS]
        if unknown or not group_list:
            raise ValueError(f"unknown market groups {unknown}: the report measures {list(MARKET_GROUPS)}")
        source_list = [source.strip() for source in sources if source.strip()]
        if not source_list:
            raise ValueError("no sources: name at least one prediction source (e.g. official_blend_v1)")
        if prereg_sha256 is not None and not _SHA256.match(prereg_sha256):
            raise ValueError("prereg_sha256 must be a lowercase hex sha256")
        code = code_fingerprint(build_sha=build_sha)
        binding = bind_code(code, code_pins, prereg_sha256=prereg_sha256)
        void = [] if binding["status"] == "BOUND" else [f"code_{binding['status'].lower()}", *binding["reasons"]]
        reader = self._reader()  # ONE memo for this run (the panel's C396-2 rule)
        results = {group: {source: self.measure_group(group, source, cut=cut_utc, since=lower, until=upper, holdout_start=holdout_start, reader=reader, void=void)
                           for source in source_list} for group in group_list}
        payload = {"schema": SCHEMA_VERSION, "protocol": protocol(), "cut": cut_utc.isoformat(),
                   "window": {"since": lower.isoformat() if lower else None, "until": upper.isoformat() if upper else None},
                   "holdout_start": holdout_start.isoformat() if holdout_start else None, "prereg_sha256": prereg_sha256,
                   "code": code, "code_binding": binding, "market_groups": group_list, "sources": source_list, "results": results}
        return {"schema": SCHEMA_VERSION, "payload": payload, "payload_sha256": canonical_sha256(payload)}


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PREREG_VALUATION_DECISOR_V1: realized accuracy of the official TP sources (rank IC, decile spread, "
                                                 "log-MSE vs random walk and consensus, buy-list proxy) — read-only, no network; prints the aggregate receipt "
                                                 "(no symbols).")
    parser.add_argument("--as-of", required=True, help="the cut C (ISO-8601 WITH zone; naive refused)")
    parser.add_argument("--groups", default=",".join(MARKET_GROUPS), help="comma-separated subset of B3,US (US = NASDAQ + NYSE)")
    parser.add_argument("--sources", default=",".join(DEFAULT_SOURCES), help="comma-separated prediction sources")
    parser.add_argument("--since", default=None, help="lower bound (inclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--until", default=None, help="upper bound (exclusive) of prediction_instant, ISO-8601 with zone")
    parser.add_argument("--holdout-start", default=None, help="H0 of the prereg (YYYY-MM-DD): sessions on/after it are the holdout; absent → development only")
    parser.add_argument("--prereg", type=Path, default=None, help="path of the pre-registration document: its sha256 and its code pins travel inside the payload")
    args = parser.parse_args(argv)
    cut = panel._cli_instant(parser, "--as-of", args.as_of)
    since, until = panel._cli_instant(parser, "--since", args.since), panel._cli_instant(parser, "--until", args.until)
    assert cut is not None
    groups = [group.strip().upper() for group in args.groups.split(",") if group.strip()]
    if not groups or any(group not in MARKET_GROUPS for group in groups):
        parser.error(f"--groups must be a non-empty subset of {','.join(MARKET_GROUPS)}, got {args.groups!r}")
    sources = [source.strip() for source in args.sources.split(",") if source.strip()]
    if not sources:
        parser.error("--sources must name at least one prediction source")
    if since is not None and until is not None and since >= until:
        parser.error("--since must precede --until")
    holdout_start: date | None = None
    if args.holdout_start is not None:
        try:
            holdout_start = date.fromisoformat(args.holdout_start)
        except ValueError:
            parser.error(f"--holdout-start must be YYYY-MM-DD, got {args.holdout_start!r}")
    prereg_sha256: str | None = None
    code_pins: dict[str, str] | None = None
    if args.prereg is not None:
        if not args.prereg.is_file():
            parser.error(f"--prereg {args.prereg} is not a file")
        content = args.prereg.read_bytes()
        prereg_sha256 = hashlib.sha256(content).hexdigest()
        try:
            code_pins = pins_from_prereg(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            parser.error(f"--prereg {args.prereg}: {error}")
    force_read_only_session()
    settings = get_settings()
    service = AccuracyReportService(cast(Database, ReadOnlyStore(Database(settings))), settings=settings)
    result = service.report(cut=cut, groups=groups, sources=sources, since=since, until=until, holdout_start=holdout_start, prereg_sha256=prereg_sha256,
                            code_pins=code_pins, build_sha=os.environ.get("C3PO_BUILD_SHA"))
    result["provenance"] = {"generated_at": datetime.now(timezone.utc).isoformat()}  # outside the payload: the payload is (cut, store, parameters, code) alone
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
