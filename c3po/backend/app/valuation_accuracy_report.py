"""The realized accuracy of the official TP sources as the buy/no-buy decider reads them — PREREG_VALUATION_DECISOR_V1
(``c3po/docs/PREREG_VALUATION_DECISOR_V1.md``), v1: the first realized-accuracy number, read-only.

MEASUREMENT, NEVER A GATE: nothing served changes, nothing is written, nothing is fetched. The report reads exactly what
the §7.3 panel reads (``valuation_panel``: the immutable prediction records of ``valuation_predictions`` by source, the
persisted price series of ``valuation_price_history`` through ``PriceHistoryService`` with the cut as
``available_before``, the exchange calendars) and REUSES its admissibility (``admissible_records``: one record per
(source, symbol, session), ``published_at < C``), its live cohort (§2.2 R3 a), its observation (basis check, ``a(T)``,
labels of the same vintage) and its attrition (``horizon_metrics``). On top of that it publishes, per market group
(``B3``; ``US`` = NASDAQ ∪ NYSE, one calendar and one currency), source and horizon in sessions (21 primary; 63/126),
split into the development partition (sessions before the holdout start ``H0``) and the holdout (``T ≥ H0``):

* the rank IC — per session, Spearman between the upside served at night ``T`` (``tp / price − 1``) and the total return
  ``adjusted_close(T + h) / adjusted_close(T) − 1`` over the names of the session (≥ ``MIN_NAMES_PER_SESSION``), then
  averaged; and the same IC on the EXECUTABLE return ``adjusted_close(T + 1 + h) / adjusted_close(T + 1) − 1`` (the
  robustness the prereg demands: a TP produced at night may already know an after-hours filing);
* the decile spread — top minus bottom decile of upside, mean total return (sessions with ≥ ``MIN_NAMES_DECILES``);
* the log-MSE of the TP PRO-RATED to the horizon (``P̂ = price · (tp / price)^(h / 252)``: a 12-month target read at
  ``h`` sessions) against the random walk (``tp = price``) and, on the common mask, against the persisted consensus
  pro-rated the same way — pooled ratio plus a per-session Diebold–Mariano difference;
* the return of the buy list against the universe of the session — the decider's COMPRA_PERMITIDA does not exist in the
  store yet, so v1 reads the PROXY ``decomposition.status == "full_match"`` (the producer's own buy class, persisted in
  the record), labelled ``decisory: false``;
* block standard errors for overlapping horizons: the per-session statistics are grouped in consecutive blocks of ``h``
  calendar sessions from the partition's anchor; only COMPLETE blocks (every session of the block matured) count; the
  estimate is the mean of the block means and its variance is inflated by ``1 + 2ρ₁ = 1.5`` (ρ₁ = 1/4, the lag-1
  correlation of adjacent block means under overlapping h-session returns); Student t with ``B − 1`` degrees of
  freedom (implemented here: no scipy in the image). Newey–West (Bartlett, lag ``h``) is reported beside it,
  diagnostic only;
* the pre-registered verdict on the HOLDOUT at the primary horizon (``verdict``): UNMEASURED → HARM → INSUFFICIENT →
  SIGNAL_PASS / CONTINUE / INCONCLUSIVE, Haybittle–Peto alpha (0.001 interim, 0.025 at the final look of ``FINAL_BLOCKS``
  blocks). The development partition never has a verdict.

The receipt carries NO symbol (aggregates only, canonical JSON, ``payload_sha256``) and no wall clock in its payload:
it is a function of (cut, store, parameters). The process forces a read-only database session
(``PGOPTIONS=-c default_transaction_read_only=on``) and talks to the store through ``ReadOnlyStore``, which exposes the
four readers the report needs and nothing else; the price reader's HTTP client raises on any call (the panel's).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
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
DEFAULT_SOURCES: tuple[str, ...] = (SOURCE_BLEND, SOURCE_INTERNAL)
MARKET_GROUPS: dict[str, tuple[str, ...]] = {"B3": ("B3",), "US": ("NASDAQ", "NYSE")}  # one calendar and one currency per group
# --- protocol constants, pre-registered (PREREG_VALUATION_DECISOR_V1); every one of them travels inside the hashed payload
HORIZONS: tuple[int, ...] = (21, 63, 126)  # sessions
PRIMARY_HORIZON = 21
EXECUTION_LAG_SESSIONS = 1  # the executable return enters at the close of T + 1
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
FINAL_BLOCKS = 12
FINAL_DEADLINE = date(2027, 12, 31)  # a look whose cut is on/after this date is FINAL whatever B (producer gaps cannot stretch the protocol)
ADJACENT_BLOCK_VARIANCE_FACTOR = 1.5  # 1 + 2ρ₁ with ρ₁ = 1/4 (block length = h, triangular autocorrelation of overlapping returns)
ALPHA_INTERIM = 0.001
ALPHA_FINAL = 0.025
ALPHA_HARM = 0.025
IC_MIN = 0.02
READ_ONLY_PGOPTION = "-c default_transaction_read_only=on"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def protocol() -> dict[str, Any]:
    """The pre-registered constants, as the receipt carries them (inside the hashed payload)."""
    return {
        "schema": SCHEMA_VERSION,
        "prereg": PREREG,
        "market_groups": {group: list(markets) for group, markets in MARKET_GROUPS.items()},
        "horizons_sessions": list(HORIZONS),
        "primary_horizon": PRIMARY_HORIZON,
        "execution_lag_sessions": EXECUTION_LAG_SESSIONS,
        "tp_horizon_sessions": TP_HORIZON_SESSIONS,
        "consensus_horizon": CONSENSUS_HORIZON,
        "scope": SCOPE,
        "min_names_per_session": MIN_NAMES_PER_SESSION,
        "min_names_deciles": MIN_NAMES_DECILES,
        "deciles": DECILES,
        "buy_list": BUY_LIST_PROXY,
        "buy_list_decisory": False,
        "attrition_cap": ATTRITION_CAP,
        "min_blocks": MIN_BLOCKS,
        "final_blocks": FINAL_BLOCKS,
        "final_deadline": FINAL_DEADLINE.isoformat(),
        "block_length": "h sessions of the market calendar from the partition anchor; complete blocks only",
        "adjacent_block_variance_factor": ADJACENT_BLOCK_VARIANCE_FACTOR,
        "alpha_interim": ALPHA_INTERIM,
        "alpha_final": ALPHA_FINAL,
        "alpha_harm": ALPHA_HARM,
        "ic_min": IC_MIN,
        "upside": "tp / price - 1 (the record's tp and price)",
        "return": "adjusted_close(T + h) / adjusted_close(T) - 1, same vintage (total return)",
        "return_executable": "adjusted_close(T + 1 + h) / adjusted_close(T + 1) - 1",
        "log_error": "ln(price * (tp / price)^(h / 252) * a(T)) - ln(adjusted_close(T + h)); random walk: tp = price",
        "cohort": "live (valuation_panel R3 a)",
        "admissibility": "valuation_panel.admissible_records",
        "label_convention": panel.LABEL_CONVENTION,
        "tol_basis": panel.TOL_BASIS,
        "calendar": {"markets": dict(panel.CALENDARS), "exchange_calendars": getattr(xcals, "__version__", "unknown")},
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


def block_statistics(points: Iterable[tuple[int, float]], *, block_length: int, mature_through: int | None,
                     partition_last: int | None = None) -> dict[str, Any]:
    """Batch means for a per-session statistic of an overlapping horizon. ``points`` are ``(session index from the
    partition's anchor, value)``; block ``b`` holds the indices ``[b·m, (b+1)·m)`` with ``m = block_length``. A block is
    COMPLETE when its last session that belongs to the partition (``partition_last`` caps it) is at or before
    ``mature_through`` (the last session whose target closed before the cut); the others are ``blocks_pending``, and a
    complete block without any value is ``blocks_empty`` (not counted). ``estimate`` = mean of the complete block means;
    ``se = sqrt(ADJACENT_BLOCK_VARIANCE_FACTOR) · sd(block means) / sqrt(B)``; Student t with ``B − 1`` degrees of
    freedom (``p_greater`` = P(T ≥ t), ``p_less`` = P(T ≤ t)); ``mean_per_session`` over every point, pending included
    (each session's value is final once measured). Newey–West over the points of the complete blocks, lag = m."""
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
    result: dict[str, Any] = {
        "block_length": block_length, "blocks": len(complete), "blocks_pending": sum(1 for block in by_block if block > last_complete),
        "blocks_empty": max(0, last_complete + 1 - len(complete)), "sessions": sum(len(by_block[block]) for block in complete),
        "mean_per_session": _mean([value for _index, value in ordered]), "estimate": _mean(means), "se": None, "t": None,
        "df": max(0, len(complete) - 1), "p_greater": None, "p_less": None, "variance_factor": ADJACENT_BLOCK_VARIANCE_FACTOR,
        "newey_west": newey_west([value for index, value in ordered if index // block_length <= last_complete], block_length),
    }
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


def _ratio(numerator: float | None, denominator: float | None) -> float | str:
    if numerator is None or denominator is None or denominator == 0.0:
        return "N/D"
    return _finite(numerator / denominator)


# ------------------------------------------------------------------ one observation at one horizon (the report's quantities)
def point(row: Mapping[str, Any], horizon: int) -> dict[str, Any] | None:
    """The report's quantities for a panel observation at ``horizon`` — ``None`` unless the label is there with the
    basis verified (the panel's ``e_source`` is set): upside, total return T → T+h, the executable return T+1 → T+1+h
    (``None`` without both labels), the pro-rated log-errors of the source, of the random walk and — when the persisted
    consensus is ``present`` and declares ``12m`` — of the consensus (else its exclusion cause), and the buy-list flag."""
    entry = row["horizons"][str(horizon)]
    if entry.get("e_source") is None:
        return None
    tp, price, adjustment, close = float(row["tp"]), float(row["price"]), float(row["adjustment"]), float(row["close_at_session"])
    realized = float(entry["realized"])
    exponent = horizon / TP_HORIZON_SESSIONS
    e_random_walk = math.log(price * adjustment) - math.log(realized)
    e_consensus: float | None = None
    consensus_cause = str(row.get("consensus_status"))
    consensus = row.get("consensus") or {}
    if consensus_cause == panel.CONSENSUS_PRESENT:
        if str(consensus.get("horizon")) != CONSENSUS_HORIZON:
            consensus_cause = "consensus_horizon_not_12m"
        else:
            e_consensus = _finite(e_random_walk + exponent * math.log(float(consensus["tp"]) / price))
    entry_lag = row["horizons"].get(str(EXECUTION_LAG_SESSIONS)) or {}
    entry_exit = row["horizons"].get(str(horizon + EXECUTION_LAG_SESSIONS)) or {}
    executable: float | None = None
    if entry_lag.get("e_source") is not None and entry_exit.get("e_source") is not None:
        executable = _finite(float(entry_exit["realized"]) / float(entry_lag["realized"]) - 1.0)
    return {
        "symbol": str(row["symbol"]), "session": str(row["session"]),
        "upside": _finite(tp / price - 1.0),
        "return": _finite(realized / (close * adjustment) - 1.0),
        "return_executable": executable,
        "e_model": _finite(e_random_walk + exponent * math.log(tp / price)),
        "e_random_walk": _finite(e_random_walk),
        "e_consensus": e_consensus,
        "consensus_cause": consensus_cause,
        "listed": row.get("producer_status") == BUY_LIST_PROXY_STATUS,
    }


# ------------------------------------------------------------------ per-session statistics and the metrics of one horizon
def _session_statistic(points: Sequence[Mapping[str, Any]], statistic: str) -> tuple[float | None, str]:
    """One session's value of ``statistic`` and, without one, why: ``below_min_names`` / ``degenerate`` / ``no_list``."""
    if statistic == "ic":
        if len(points) < MIN_NAMES_PER_SESSION:
            return None, "below_min_names"
        value = spearman([p["upside"] for p in points], [p["return"] for p in points])
        return value, "ok" if value is not None else "degenerate"
    if statistic == "ic_executable":
        usable = [p for p in points if p["return_executable"] is not None]
        if len(usable) < MIN_NAMES_PER_SESSION:
            return None, "below_min_names"
        value = spearman([p["upside"] for p in usable], [p["return_executable"] for p in usable])
        return value, "ok" if value is not None else "degenerate"
    if statistic == "decile_spread":
        if len(points) < MIN_NAMES_DECILES:
            return None, "below_min_names"
        value = decile_spread([p["upside"] for p in points], [p["return"] for p in points])
        return value, "ok" if value is not None else "degenerate"
    if statistic == "buy_list_excess":
        if len(points) < MIN_NAMES_PER_SESSION:
            return None, "below_min_names"
        listed = [p["return"] for p in points if p["listed"]]
        if not listed:
            return None, "no_list"
        return _finite(math.fsum(listed) / len(listed) - math.fsum(p["return"] for p in points) / len(points)), "ok"
    if statistic == "mse_vs_random_walk":
        return _finite(math.fsum(p["e_model"] ** 2 for p in points) / len(points) - math.fsum(p["e_random_walk"] ** 2 for p in points) / len(points)), "ok"
    if statistic == "mse_vs_consensus":
        common = [p for p in points if p["e_consensus"] is not None]
        if not common:
            return None, "no_consensus"
        return _finite(math.fsum(p["e_model"] ** 2 for p in common) / len(common) - math.fsum(p["e_consensus"] ** 2 for p in common) / len(common)), "ok"
    raise ValueError(f"unknown statistic {statistic!r}")


def _series(by_session: Mapping[str, Sequence[Mapping[str, Any]]], statistic: str, index_of: Mapping[str, int], *, block_length: int,
            mature_through: int | None, partition_last: int | None) -> dict[str, Any]:
    values: list[tuple[int, float]] = []
    causes: Counter[str] = Counter()
    for session in sorted(by_session):
        value, cause = _session_statistic(by_session[session], statistic)
        causes[cause] += 1
        if value is not None:
            values.append((index_of[session], value))
    return {"sessions_measured": causes.pop("ok", 0), "sessions_not_measured": panel._counts(causes),
            "blocks": block_statistics(values, block_length=block_length, mature_through=mature_through, partition_last=partition_last)}


def _mse_label(ratio: float | str) -> str:
    if not isinstance(ratio, float):
        return "UNMEASURED"
    return "BETTER" if ratio < 1.0 else "NOT_BETTER"


def horizon_report(rows: Sequence[Mapping[str, Any]], horizon: int, *, index_of: Mapping[str, int], mature_through: Mapping[int, int | None],
                   partition_last: int | None) -> dict[str, Any]:
    """Every metric of PREREG_VALUATION_DECISOR_V1 at one horizon over one partition's live universe observations.
    ``index_of`` maps a session (ISO) to its calendar index from the partition's anchor; ``mature_through[h]`` is the
    index of the last session whose target ``T + h`` closed before the cut (``None``/negative: none). Aggregates only."""
    attrition_view = panel.horizon_metrics(rows, horizon)
    points = [p for p in (point(row, horizon) for row in rows) if p is not None]
    by_session: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(points, key=lambda p: (p["session"], p["symbol"])):
        by_session.setdefault(item["session"], []).append(item)
    series = {name: _series(by_session, name, index_of, block_length=horizon,
                            mature_through=mature_through.get(horizon + EXECUTION_LAG_SESSIONS if name == "ic_executable" else horizon),
                            partition_last=partition_last)
              for name in ("ic", "ic_executable", "decile_spread", "buy_list_excess", "mse_vs_random_walk", "mse_vs_consensus")}
    common = [p for p in points if p["e_consensus"] is not None]
    mse_model = _mean([p["e_model"] ** 2 for p in points])
    mse_random_walk = _mean([p["e_random_walk"] ** 2 for p in points])
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
        "observations": panel._mask_stats(points),
        "ic": series["ic"],
        "ic_executable": {**series["ic_executable"], "labelled_without_executable_return": sum(1 for p in points if p["return_executable"] is None)},
        "decile_spread": series["decile_spread"],
        "buy_list_excess": {**series["buy_list_excess"], "list": BUY_LIST_PROXY, "decisory": False,
                            "mean_listed_per_session": _mean([float(count) for count in listed_per_session])},
        "log_mse_vs_random_walk": {"n": len(points), "mse_model": mse_model, "mse_random_walk": mse_random_walk, "ratio": ratio_random_walk,
                                   "label": _mse_label(ratio_random_walk), "decisory": False, "per_session_difference": series["mse_vs_random_walk"]},
        "log_mse_vs_consensus": {"n": len(common), "excluded": panel._counts(Counter(p["consensus_cause"] for p in points if p["e_consensus"] is None)),
                                 "mse_model": mse_model_common, "mse_consensus": mse_consensus, "ratio": ratio_consensus, "label": _mse_label(ratio_consensus),
                                 "decisory": False, "per_session_difference": series["mse_vs_consensus"]},
        "log_mse_raw_tp": attrition_view["source"],  # the panel's §2.6 error of the unscaled 12-month TP at h: diagnostic
    }


# ------------------------------------------------------------------ the pre-registered verdict (holdout, primary horizon)
def verdict(horizons: Mapping[str, Mapping[str, Any]], *, final_by_deadline: bool = False) -> dict[str, Any]:
    """PREREG_VALUATION_DECISOR_V1 §7, in order, over the HOLDOUT: attrition at the primary horizon above the cap (or no
    eligible observation) → ``UNMEASURED``; the IC significantly NEGATIVE at any horizon with ``B ≥ MIN_BLOCKS``
    complete blocks and attrition within the cap (``p_less ≤ ALPHA_HARM``) → ``HARM``; fewer than ``MIN_BLOCKS`` blocks
    of the primary IC → ``INSUFFICIENT`` (``INCONCLUSIVE`` at the deadline); then the look is ``FINAL`` with
    ``B ≥ FINAL_BLOCKS`` or ``final_by_deadline`` (the cut on/after ``FINAL_DEADLINE``; alpha 0.025), else ``INTERIM``
    (alpha 0.001), and the signal passes when the IC estimate ≥ ``IC_MIN``, its ``p_greater ≤ alpha``, the decile spread
    estimate > 0 and the executable IC estimate > 0 → ``SIGNAL_PASS`` (the buy list is not decisory in v1: a full
    ``PASS`` needs the decider's own list); otherwise ``CONTINUE`` at an interim look, ``INCONCLUSIVE`` at the final
    one. Never a gate: the mesa acts on it."""
    primary = horizons[str(PRIMARY_HORIZON)]
    result: dict[str, Any] = {"status": "UNMEASURED", "look": None, "alpha": None, "reasons": [], "horizon_sessions": PRIMARY_HORIZON,
                              "blocks": primary["ic"]["blocks"]["blocks"], "ic_estimate": primary["ic"]["blocks"]["estimate"],
                              "ic_p_greater": primary["ic"]["blocks"]["p_greater"], "buy_list_decisory": False, "gate": False}
    rate = primary["attrition"]["rate"]
    if rate is None:
        result["reasons"].append("no_eligible_observations")
        return result
    if rate > ATTRITION_CAP:
        result["reasons"].append(f"attrition_above_cap:{rate:.4f}>{ATTRITION_CAP}")
        return result
    harms = []
    for key in sorted(horizons, key=int):
        metrics = horizons[key]
        blocks = metrics["ic"]["blocks"]
        attrition = metrics["attrition"]["rate"]
        if attrition is None or attrition > ATTRITION_CAP or blocks["blocks"] < MIN_BLOCKS or blocks["p_less"] is None:
            continue
        if blocks["p_less"] <= ALPHA_HARM:
            harms.append(f"ic_negative:h{key}:p_less={blocks['p_less']:.6f}")
    if harms:
        result.update({"status": "HARM", "reasons": harms})
        return result
    blocks = primary["ic"]["blocks"]
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
        failures.append(f"ic_below_min:{blocks['estimate']}<{IC_MIN}")
    if blocks["p_greater"] is None or blocks["p_greater"] > alpha:
        failures.append(f"ic_not_significant:p_greater={blocks['p_greater']}>{alpha}")
    spread = primary["decile_spread"]["blocks"]["estimate"]
    if spread is None or spread <= 0.0:
        failures.append("decile_spread_unmeasured" if spread is None else "decile_spread_not_positive")
    executable = primary["ic_executable"]["blocks"]["estimate"]
    if executable is None or executable <= 0.0:
        failures.append("ic_executable_unmeasured" if executable is None else "ic_executable_not_positive")
    status = "SIGNAL_PASS" if not failures else ("INCONCLUSIVE" if final else "CONTINUE")
    result.update({"status": status, "look": "FINAL" if final else "INTERIM", "alpha": alpha, "reasons": failures})
    return result


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
                      holdout_start: date | None, reader: PriceHistoryService) -> dict[str, Any]:
        """One (market group, source) cell: the observations of every market of the group, the live universe split at
        ``H0``, every horizon's metrics per partition and the holdout's verdict. Aggregates only."""
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
               prereg_sha256: str | None = None) -> dict[str, Any]:
        """The receipt as of ``cut`` (aware, explicit): ``{schema, payload, payload_sha256}`` — no symbol anywhere."""
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
        reader = self._reader()  # ONE memo for this run (the panel's C396-2 rule)
        results = {group: {source: self.measure_group(group, source, cut=cut_utc, since=lower, until=upper, holdout_start=holdout_start, reader=reader)
                           for source in source_list} for group in group_list}
        payload = {"schema": SCHEMA_VERSION, "protocol": protocol(), "cut": cut_utc.isoformat(),
                   "window": {"since": lower.isoformat() if lower else None, "until": upper.isoformat() if upper else None},
                   "holdout_start": holdout_start.isoformat() if holdout_start else None, "prereg_sha256": prereg_sha256,
                   "market_groups": group_list, "sources": source_list, "results": results}
        return {"schema": SCHEMA_VERSION, "payload": payload, "payload_sha256": canonical_sha256(payload)}


# ------------------------------------------------------------------ CLI
def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    parser.add_argument("--prereg", type=Path, default=None, help="path of the pre-registration document: its sha256 travels inside the payload")
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
    if args.prereg is not None:
        if not args.prereg.is_file():
            parser.error(f"--prereg {args.prereg} is not a file")
        prereg_sha256 = _file_sha256(args.prereg)
    force_read_only_session()
    settings = get_settings()
    service = AccuracyReportService(cast(Database, ReadOnlyStore(Database(settings))), settings=settings)
    result = service.report(cut=cut, groups=groups, sources=sources, since=since, until=until, holdout_start=holdout_start, prereg_sha256=prereg_sha256)
    result["provenance"] = {"module_sha256": _file_sha256(Path(__file__)), "build_sha": os.environ.get("C3PO_BUILD_SHA"),
                            "generated_at": datetime.now(timezone.utc).isoformat()}  # outside the payload: the payload is (cut, store, parameters) alone
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
