from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .r2d2 import _paper_exit_execution
from .r2d2_exit_policy_engine import (
    BOOTSTRAP_ITERATIONS,
    BOOTSTRAP_SEED,
    CENT_TOLERANCE_USD,
    OHLC_BOUNDARY_TOLERANCE_MINUTES,
    OHLC_CLOCK_EXTENDED_BACKWARD_MINUTES,
    OHLC_VIOLATION_EPISODE_LIMIT_PERCENT,
    LedgerFill,
    StudyBar,
    classify_market_compatibility,
)


NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
HORIZONS_MINUTES = (15, 30, 60, 120)
BARRIER_CATEGORIES = (
    "upper_first",
    "lower_first",
    "ambiguous_same_bar",
    "censored",
)
MIN_HYPOTHESIS_SESSIONS = 15
MIN_HYPOTHESIS_EPISODES_PER_CELL = 30
CENSORSHIP_REVIEW_PERCENT = 20.0
ENTRY_MARKET_COMPATIBILITY_CLASSES = (
    "contained",
    "clock_extended",
    "bar_unavailable",
    "tolerance_band",
    "violation",
)


class EntryQualityStudyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EntryMeasurement:
    entry_id: str
    market: str
    symbol: str
    session_date: date
    policy_epoch: str
    executed_at: datetime
    quote_as_of: datetime
    valuation_basis: str
    route: str
    entry_hour_brt: int
    regime: str | None
    composite_score: float | None
    fundamental_score: float | None
    technical_score: float | None
    risk_score: float | None
    buy_in_distance_percent: float | None
    atr_percent: float | None
    quote_age_seconds: float | None
    stretch: float | None
    net0_percent: float
    risk_one_r_percent: float
    barrier_category: str
    primary_return_60m_percent: float | None
    endpoint_returns_percent: Mapping[str, float | None]
    mfe_percent: float | None
    mae_percent: float | None
    minutes_to_peak: int | None

    def __post_init__(self) -> None:
        if self.barrier_category not in BARRIER_CATEGORIES:
            raise ValueError(f"unsupported barrier category: {self.barrier_category}")
        if self.executed_at.tzinfo is None or self.quote_as_of.tzinfo is None:
            raise ValueError("entry timestamps must be timezone-aware")
        if self.risk_one_r_percent <= 0:
            raise ValueError("1R must be positive")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _technical(fill: LedgerFill) -> Mapping[str, Any]:
    value = fill.decision_snapshot.get("technical_indicators")
    return value if isinstance(value, Mapping) else {}


def _net_pnl_usd(fill: LedgerFill, quote_price: float) -> float:
    execution = _paper_exit_execution(
        market=fill.market,
        price=quote_price,
        quantity=fill.quantity,
        fx=fill.fx_to_usd,
    )
    entry_cost = fill.gross_value_usd + fill.fees_usd
    return execution["gross_value_usd"] - execution["fees_usd"] - entry_cost


def _net_return_percent(fill: LedgerFill, quote_price: float) -> float:
    entry_cost = fill.gross_value_usd + fill.fees_usd
    if entry_cost <= 0:
        raise EntryQualityStudyError(f"entry {fill.id} has non-positive cost basis")
    return _net_pnl_usd(fill, quote_price) / entry_cost * 100.0


def _same_session_path(fill: LedgerFill, bars: Sequence[StudyBar]) -> list[StudyBar]:
    session = fill.executed_at.astimezone(NEW_YORK).date()
    entry_minute = fill.executed_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return sorted(
        (
            bar for bar in bars
            if bar.session_date == session and bar.start_at.astimezone(timezone.utc) > entry_minute
        ),
        key=lambda bar: bar.start_at,
    )


def entry_route(fill: LedgerFill) -> str:
    reasons = fill.decision_snapshot.get("entry_decision_reasons")
    candidates = [str(value) for value in reasons] if isinstance(reasons, list) else []
    if not candidates and fill.reason:
        candidates = [fill.reason]
    joined = " ".join(candidates).lower()
    if "tactical quality-momentum route passed" in joined:
        return "tactical_quality_momentum"
    if "cost-aware intraday route passed" in joined:
        return "cost_aware_intraday"
    return "unclassified"


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2.0 / (period + 1.0)
    current = statistics.mean(values[:period])
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def entry_regime(fill: LedgerFill, qqq_bars: Sequence[StudyBar]) -> str | None:
    session = fill.executed_at.astimezone(NEW_YORK).date()
    decision_at = fill.executed_at.astimezone(timezone.utc)
    completed = sorted(
        (
            bar for bar in qqq_bars
            if bar.session_date == session
            and bar.start_at.astimezone(timezone.utc) + timedelta(minutes=1) <= decision_at
        ),
        key=lambda bar: bar.start_at,
    )
    if not completed:
        return None
    volume = sum(bar.volume for bar in completed)
    if volume <= 0:
        return None
    vwap = sum(
        ((bar.high + bar.low + bar.close) / 3.0) * bar.volume
        for bar in completed
    ) / volume

    grouped: dict[datetime, list[StudyBar]] = defaultdict(list)
    for bar in completed:
        local = bar.start_at.astimezone(NEW_YORK)
        open_at = local.replace(hour=9, minute=30, second=0, microsecond=0)
        offset = int((local - open_at).total_seconds() // 60)
        if offset < 0:
            continue
        group_at = open_at + timedelta(minutes=(offset // 5) * 5)
        grouped[group_at.astimezone(timezone.utc)].append(bar)
    five_minute_closes = [
        sorted(group, key=lambda bar: bar.start_at)[-1].close
        for group_at, group in sorted(grouped.items())
        if len(group) == 5 and group_at + timedelta(minutes=5) <= decision_at
    ]
    ema8 = _ema(five_minute_closes, 8)
    if ema8 is None:
        return None
    price = five_minute_closes[-1]
    if price > vwap and price > ema8:
        return "trend_up"
    if price < vwap and price < ema8:
        return "fade"
    return "mixed"


def entry_stretch(fill: LedgerFill) -> float | None:
    technical = _technical(fill)
    vwap = _number(technical.get("vwap"))
    ema8 = _number(technical.get("ema8"))
    if not vwap or not ema8 or vwap <= 0 or ema8 <= 0:
        return None
    return min(
        fill.signal_price_local / vwap - 1.0,
        fill.signal_price_local / ema8 - 1.0,
    )


def atr_class(value: float | None) -> str:
    """Use the volatility-score bands already versioned in the strategy."""
    if value is None:
        return "unavailable"
    if value < 0.25:
        return "below_strategy_band"
    if value <= 3.5:
        return "strategy_band_0_25_to_3_5"
    if value <= 5.0:
        return "elevated_3_5_to_5"
    return "extreme_above_5"


def quote_age_class(value: float | None) -> str:
    """Mirror the platform's existing fresh/aging/stale thresholds."""
    if value is None:
        return "unavailable"
    if value <= 5.0:
        return "fresh"
    if value <= 30.0:
        return "aging"
    return "stale"


def _endpoint_return(
    fill: LedgerFill,
    path: Sequence[StudyBar],
    minutes: int,
) -> float | None:
    local_entry = fill.executed_at.astimezone(NEW_YORK)
    target = fill.executed_at.astimezone(timezone.utc) + timedelta(minutes=minutes)
    close_at = local_entry.replace(
        hour=REGULAR_CLOSE.hour,
        minute=REGULAR_CLOSE.minute,
        second=0,
        microsecond=0,
    ).astimezone(timezone.utc)
    if target > close_at:
        return None
    completed = [
        bar for bar in path
        if bar.start_at.astimezone(timezone.utc) + timedelta(minutes=1) <= target
    ]
    if not completed:
        return None
    return _net_return_percent(fill, completed[-1].close)


def _barrier_category(
    fill: LedgerFill,
    path: Sequence[StudyBar],
    *,
    net0_percent: float,
    one_r_percent: float,
) -> str:
    upper = net0_percent + one_r_percent
    lower = net0_percent - one_r_percent
    for bar in path:
        touches_upper = _net_return_percent(fill, bar.high) >= upper
        touches_lower = _net_return_percent(fill, bar.low) <= lower
        if touches_upper and touches_lower:
            return "ambiguous_same_bar"
        if touches_upper:
            return "upper_first"
        if touches_lower:
            return "lower_first"
    return "censored"


def measure_entry(
    fill: LedgerFill,
    bars: Sequence[StudyBar],
    *,
    policy_epoch: str,
    qqq_bars: Sequence[StudyBar] = (),
) -> EntryMeasurement:
    if fill.side != "BUY":
        raise EntryQualityStudyError(f"entry measure requires BUY, observed {fill.side}")
    path = _same_session_path(fill, bars)
    if not path:
        raise EntryQualityStudyError(f"entry {fill.id} has no completed post-entry bars")
    stop = _number(fill.decision_snapshot.get("stop_price"))
    if stop is None or stop <= 0:
        raise EntryQualityStudyError(f"entry {fill.id} has no valid persisted stop")

    net0 = _net_return_percent(fill, fill.signal_price_local)
    one_r = abs(_net_return_percent(fill, stop) - net0)
    if one_r <= 1e-12:
        raise EntryQualityStudyError(f"entry {fill.id} has a degenerate 1R distance")
    endpoints = {
        f"plus_{minutes}m": _endpoint_return(fill, path, minutes)
        for minutes in HORIZONS_MINUTES
    }
    endpoints["session_close"] = _net_return_percent(fill, path[-1].close)
    high_returns = [_net_return_percent(fill, bar.high) for bar in path]
    low_returns = [_net_return_percent(fill, bar.low) for bar in path]
    peak_index = max(range(len(path)), key=lambda index: high_returns[index])

    technical = _technical(fill)
    stretch = entry_stretch(fill)
    quote_age = max(0.0, (fill.executed_at - fill.quote_as_of).total_seconds())
    return EntryMeasurement(
        entry_id=fill.id,
        market=fill.market,
        symbol=fill.symbol,
        session_date=fill.executed_at.astimezone(NEW_YORK).date(),
        policy_epoch=policy_epoch,
        executed_at=fill.executed_at,
        quote_as_of=fill.quote_as_of,
        valuation_basis=str(fill.decision_snapshot.get("valuation_basis") or "unclassified"),
        route=entry_route(fill),
        entry_hour_brt=fill.executed_at.astimezone(SAO_PAULO).hour,
        regime=entry_regime(fill, qqq_bars),
        composite_score=_number(fill.decision_snapshot.get("composite_score")),
        fundamental_score=_number(fill.decision_snapshot.get("fundamental_score")),
        technical_score=_number(fill.decision_snapshot.get("technical_score")),
        risk_score=_number(fill.decision_snapshot.get("risk_score")),
        buy_in_distance_percent=_number(fill.decision_snapshot.get("buy_in_distance")),
        atr_percent=_number(technical.get("atr_percent")),
        quote_age_seconds=quote_age,
        stretch=stretch,
        net0_percent=net0,
        risk_one_r_percent=one_r,
        barrier_category=_barrier_category(
            fill,
            path,
            net0_percent=net0,
            one_r_percent=one_r,
        ),
        primary_return_60m_percent=endpoints["plus_60m"],
        endpoint_returns_percent=endpoints,
        mfe_percent=max(high_returns),
        mae_percent=min(low_returns),
        minutes_to_peak=max(
            0,
            int(
                (
                    path[peak_index].start_at.astimezone(timezone.utc)
                    - fill.executed_at.astimezone(timezone.utc)
                ).total_seconds()
                // 60
            ),
        ),
    )


def reconcile_entry_gate(
    entries: Sequence[LedgerFill],
    bars_by_symbol: Mapping[str, Sequence[StudyBar]],
    *,
    constructed_entry_count: int | None = None,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    compatibility_counts = {
        name: 0 for name in ENTRY_MARKET_COMPATIBILITY_CLASSES
    }
    violation_ids: set[str] = set()
    violation_rows: list[dict[str, Any]] = []
    unavailable_ids: set[str] = set()
    unavailable_rows: list[dict[str, Any]] = []
    entry_count_by_session: dict[str, int] = defaultdict(int)
    unavailable_count_by_session: dict[str, int] = defaultdict(int)

    def candidate_bar_exists(
        fill: LedgerFill,
        bars: Mapping[datetime, StudyBar],
    ) -> bool:
        original_offsets = (
            0,
            -OHLC_BOUNDARY_TOLERANCE_MINUTES,
            OHLC_BOUNDARY_TOLERANCE_MINUTES,
        )
        candidate_minutes = {
            anchor.astimezone(timezone.utc).replace(second=0, microsecond=0)
            + timedelta(minutes=offset)
            for anchor in (fill.executed_at, fill.quote_as_of)
            for offset in original_offsets
        }
        candidate_minutes.update({
            fill.quote_as_of.astimezone(timezone.utc).replace(second=0, microsecond=0)
            + timedelta(minutes=offset)
            for offset in range(-OHLC_CLOCK_EXTENDED_BACKWARD_MINUTES, 2)
        })
        return any(minute in bars for minute in candidate_minutes)

    for fill in entries:
        if fill.side != "BUY":
            raise EntryQualityStudyError("entry gate accepts BUY rows only")
        expected_gross = fill.quantity * fill.fill_price_local * fill.fx_to_usd
        slip_rate = 0.0015 if fill.market == "B3" else 0.0010
        fee_rate = 0.0006 if fill.market == "B3" else 0.0004
        expected_fill = fill.signal_price_local * (1 + slip_rate)
        expected_fee = expected_gross * fee_rate
        expected_slippage = (
            fill.quantity
            * abs(fill.fill_price_local - fill.signal_price_local)
            * fill.fx_to_usd
        )
        for field, observed, expected in (
            ("gross_value_usd", fill.gross_value_usd, expected_gross),
            ("fees_usd", fill.fees_usd, expected_fee),
            ("slippage_usd", fill.slippage_usd, expected_slippage),
        ):
            if abs(observed - expected) > CENT_TOLERANCE_USD:
                failures.append({
                    "entry_id": fill.id,
                    "gate": field,
                    "observed": observed,
                    "expected": expected,
                })
        if not math.isclose(fill.fill_price_local, expected_fill, rel_tol=0, abs_tol=1e-7):
            failures.append({
                "entry_id": fill.id,
                "gate": "fill_friction",
                "observed": fill.fill_price_local,
                "expected": expected_fill,
            })
        session = fill.executed_at.astimezone(NEW_YORK).date()
        session_key = session.isoformat()
        entry_count_by_session[session_key] += 1
        minute_bars = {
            bar.start_at.astimezone(timezone.utc): bar
            for bar in bars_by_symbol.get(fill.symbol, ())
            if bar.session_date == session
        }
        if not minute_bars or not candidate_bar_exists(fill, minute_bars):
            compatibility_counts["bar_unavailable"] += 1
            unavailable_ids.add(fill.id)
            unavailable_count_by_session[session_key] += 1
            unavailable_rows.append({
                "entry_id": fill.id,
                "market": fill.market,
                "symbol": fill.symbol,
                "session_date": session_key,
                "executed_at": fill.executed_at.isoformat(),
                "quote_as_of": fill.quote_as_of.isoformat(),
                "reason": "no bar in original or extended compatibility windows",
            })
            continue
        compatibility = classify_market_compatibility(fill, minute_bars)
        classification = str(compatibility["classification"])
        compatibility_counts[classification] += 1
        if classification == "violation":
            violation_ids.add(fill.id)
            violation_rows.append({
                "entry_id": fill.id,
                "market": fill.market,
                "symbol": fill.symbol,
                "executed_at": fill.executed_at.isoformat(),
                "quote_as_of": fill.quote_as_of.isoformat(),
                "signal_price_local": fill.signal_price_local,
                "breach_bps": compatibility.get("breach_bps"),
                "matched_anchor": compatibility.get("matched_anchor"),
                "matched_offset_minutes": compatibility.get("matched_offset_minutes"),
                "matched_bar_start_at": compatibility.get("matched_bar_start_at"),
            })
    denominator = constructed_entry_count if constructed_entry_count is not None else len(entries)
    violation_percent = len(violation_ids) / denominator * 100.0 if denominator else 0.0
    unavailable_percent = len(unavailable_ids) / denominator * 100.0 if denominator else 0.0
    censored_ids = violation_ids | unavailable_ids
    coverage_by_session: list[dict[str, Any]] = []
    for session_key, session_entry_count in sorted(entry_count_by_session.items()):
        unavailable_count = unavailable_count_by_session.get(session_key, 0)
        percent = (
            unavailable_count / session_entry_count * 100.0
            if session_entry_count else 0.0
        )
        coverage_by_session.append({
            "session_date": session_key,
            "constructed_entry_count": session_entry_count,
            "bar_unavailable_count": unavailable_count,
            "bar_unavailable_percent": percent,
            "status": (
                "REVIEW_REQUIRED"
                if percent > CENSORSHIP_REVIEW_PERCENT
                else "ACCEPTABLE"
            ),
        })
    threshold_passed = violation_percent <= OHLC_VIOLATION_EPISODE_LIMIT_PERCENT
    if not threshold_passed:
        failures.append({
            "gate": "market_compatibility_violation_rate",
            "observed_percent": violation_percent,
            "maximum_percent": OHLC_VIOLATION_EPISODE_LIMIT_PERCENT,
        })
    return {
        "passed": not failures,
        "g1_ledger_and_friction": {
            "passed": not any(
                failure["gate"] != "market_compatibility_violation_rate"
                for failure in failures
            ),
            "checked_entry_count": len(entries),
            "cent_tolerance_usd": CENT_TOLERANCE_USD,
            "fill_price_absolute_tolerance": 1e-7,
        },
        "g2_market_compatibility": {
            "classes_in_precedence_order": list(ENTRY_MARKET_COMPATIBILITY_CLASSES),
            "counts": compatibility_counts,
            "bar_unavailable_outside_numeric_violation_ceiling": True,
        },
        "g3_coverage_censorship": {
            "censored_entry_ids": sorted(censored_ids),
            "censored_entry_count": len(censored_ids),
            "censored_percent_of_constructed_entries": (
                len(censored_ids) / denominator * 100.0 if denominator else 0.0
            ),
            "constructed_entry_count_denominator": denominator,
            "violation_entry_ids": sorted(violation_ids),
            "violation_entry_count": len(violation_ids),
            "violation_percent_of_constructed_entries": violation_percent,
            "bar_unavailable_entry_ids": sorted(unavailable_ids),
            "bar_unavailable_entry_count": len(unavailable_ids),
            "bar_unavailable_percent_of_constructed_entries": unavailable_percent,
            "maximum_percent": OHLC_VIOLATION_EPISODE_LIMIT_PERCENT,
            "threshold_passed": threshold_passed,
            "violations": violation_rows,
            "bar_unavailable": unavailable_rows,
            "bar_unavailable_review_threshold_percent": CENSORSHIP_REVIEW_PERCENT,
            "bar_unavailable_by_session": coverage_by_session,
            "bar_unavailable_review_required": any(
                row["status"] == "REVIEW_REQUIRED" for row in coverage_by_session
            ),
        },
        "failures": failures,
    }


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def frozen_stretch_upper_quartile(rows: Sequence[EntryMeasurement]) -> float | None:
    return _percentile(
        [row.stretch for row in rows if row.stretch is not None],
        0.75,
    )


def _bootstrap_estimates_by_session(
    rows: Sequence[EntryMeasurement],
    statistic: Callable[[Sequence[EntryMeasurement]], float | None],
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> list[float]:
    by_session: dict[date, list[EntryMeasurement]] = defaultdict(list)
    for row in rows:
        by_session[row.session_date].append(row)
    sessions = sorted(by_session)
    if not sessions:
        return []
    randomizer = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        sampled: list[EntryMeasurement] = []
        for session in randomizer.choices(sessions, k=len(sessions)):
            sampled.extend(by_session[session])
        value = statistic(sampled)
        if value is not None and math.isfinite(value):
            estimates.append(value)
    return estimates


def _bootstrap_by_session(
    rows: Sequence[EntryMeasurement],
    statistic: Callable[[Sequence[EntryMeasurement]], float | None],
    *,
    seed: int = BOOTSTRAP_SEED,
    iterations: int = BOOTSTRAP_ITERATIONS,
) -> tuple[float | None, float | None]:
    estimates = _bootstrap_estimates_by_session(
        rows,
        statistic,
        seed=seed,
        iterations=iterations,
    )
    return _percentile(estimates, 0.025), _percentile(estimates, 0.975)


def _mean_primary(rows: Sequence[EntryMeasurement]) -> float | None:
    values = [
        row.primary_return_60m_percent
        for row in rows
        if row.primary_return_60m_percent is not None
    ]
    return statistics.mean(values) if values else None


def _barrier_probability(rows: Sequence[EntryMeasurement]) -> float | None:
    upper = sum(row.barrier_category == "upper_first" for row in rows)
    lower = sum(row.barrier_category == "lower_first" for row in rows)
    return upper / (upper + lower) if upper + lower else None


def _barrier_probability_conservative(
    rows: Sequence[EntryMeasurement],
) -> float | None:
    upper = sum(row.barrier_category == "upper_first" for row in rows)
    lower = sum(row.barrier_category == "lower_first" for row in rows)
    ambiguous = sum(row.barrier_category == "ambiguous_same_bar" for row in rows)
    denominator = upper + lower + ambiguous
    return upper / denominator if denominator else None


def summarize_cell(rows: Sequence[EntryMeasurement]) -> dict[str, Any]:
    categories = {
        category: sum(row.barrier_category == category for row in rows)
        for category in BARRIER_CATEGORIES
    }
    resolved = categories["upper_first"] + categories["lower_first"]
    conservative_denominator = resolved + categories["ambiguous_same_bar"]
    primary_values = [
        row.primary_return_60m_percent
        for row in rows
        if row.primary_return_60m_percent is not None
    ]
    primary_ci = _bootstrap_by_session(rows, _mean_primary)
    barrier_estimates = _bootstrap_estimates_by_session(rows, _barrier_probability)
    barrier_conservative_estimates = _bootstrap_estimates_by_session(
        rows,
        _barrier_probability_conservative,
    )
    barrier_ci = (
        _percentile(barrier_estimates, 0.025),
        _percentile(barrier_estimates, 0.975),
    )
    censorship_percent = categories["censored"] / len(rows) * 100.0 if rows else 0.0
    return {
        "entry_count": len(rows),
        "session_count": len({row.session_date for row in rows}),
        "primary_plus_60m": {
            "observed_count": len(primary_values),
            "censored_count": len(rows) - len(primary_values),
            "mean_percent": statistics.mean(primary_values) if primary_values else None,
            "median_percent": statistics.median(primary_values) if primary_values else None,
            "bootstrap_ci95_percent": list(primary_ci),
        },
        "barrier": {
            "categories": categories,
            "resolved_count": resolved,
            "p_hat": categories["upper_first"] / resolved if resolved else None,
            "p_hat_conservative": (
                categories["upper_first"] / conservative_denominator
                if conservative_denominator else None
            ),
            "bootstrap_ci95": list(barrier_ci),
            "p_hat_ucb_98_75": _percentile(barrier_estimates, 0.9875),
            "p_hat_cons_ucb_98_75": _percentile(
                barrier_conservative_estimates,
                0.9875,
            ),
            "verdict_against_50_percent": (
                "EDGE_ABOVE_REFERENCE"
                if barrier_ci[0] is not None and barrier_ci[0] > 0.5
                else "EDGE_BELOW_REFERENCE"
                if barrier_ci[1] is not None and barrier_ci[1] < 0.5
                else "INCONCLUSIVE"
            ),
            "censorship_percent": censorship_percent,
            "censorship_status": (
                "REVIEW_REQUIRED"
                if censorship_percent > CENSORSHIP_REVIEW_PERCENT
                else "ACCEPTABLE"
            ),
        },
        "mfe_percent": statistics.mean(
            [row.mfe_percent for row in rows if row.mfe_percent is not None]
        ) if any(row.mfe_percent is not None for row in rows) else None,
        "mae_percent": statistics.mean(
            [row.mae_percent for row in rows if row.mae_percent is not None]
        ) if any(row.mae_percent is not None for row in rows) else None,
    }


def _hypothesis_result(
    name: str,
    cells: Mapping[str, Sequence[EntryMeasurement]],
) -> dict[str, Any]:
    summaries = {key: summarize_cell(value) for key, value in cells.items()}
    session_count = len({row.session_date for values in cells.values() for row in values})
    too_small = [
        key for key, value in summaries.items()
        if value["barrier"]["resolved_count"] < MIN_HYPOTHESIS_EPISODES_PER_CELL
    ]
    session_floor_met = session_count >= MIN_HYPOTHESIS_SESSIONS
    for key, value in summaries.items():
        value["hypothesis_sample_status"] = (
            "READY"
            if session_floor_met
            and value["barrier"]["resolved_count"] >= MIN_HYPOTHESIS_EPISODES_PER_CELL
            else "INSUFFICIENT_SAMPLE"
        )
    if session_count < MIN_HYPOTHESIS_SESSIONS or too_small:
        status = "INSUFFICIENT_SAMPLE"
    else:
        status = "DESCRIPTIVE_READY"
    return {
        "hypothesis": name,
        "status": status,
        "required_session_count": MIN_HYPOTHESIS_SESSIONS,
        "required_decided_entries_per_cell": MIN_HYPOTHESIS_EPISODES_PER_CELL,
        "observed_session_count": session_count,
        "insufficient_cells": too_small,
        "cells": summaries,
    }


def hypothesis_reports(
    rows: Sequence[EntryMeasurement],
    *,
    stretch_upper_quartile: float | None,
) -> dict[str, Any]:
    h1 = {
        "10_to_12_brt": [row for row in rows if 10 <= row.entry_hour_brt < 12],
        "12_to_15_brt": [row for row in rows if 12 <= row.entry_hour_brt < 15],
    }
    h2 = {
        "fade": [row for row in rows if row.regime == "fade"],
        "non_fade": [row for row in rows if row.regime in {"trend_up", "mixed"}],
    }

    scored = sorted(
        (row for row in rows if row.composite_score is not None),
        key=lambda row: (float(row.composite_score), row.entry_id),
    )
    decile_size = max(1, math.ceil(len(scored) / 10)) if scored else 1
    h3 = {
        "bottom_decile": scored[:decile_size],
        "top_decile": scored[-decile_size:] if scored else [],
    }
    h4 = {
        "upper_quartile_stretch": [
            row for row in rows
            if stretch_upper_quartile is not None
            and row.stretch is not None
            and row.stretch >= stretch_upper_quartile
        ],
        "other_stretch": [
            row for row in rows
            if stretch_upper_quartile is not None
            and row.stretch is not None
            and row.stretch < stretch_upper_quartile
        ],
    }
    return {
        "H1": _hypothesis_result("midday entries have worse edge", h1),
        "H2": _hypothesis_result("fade regime has negative edge", h2),
        "H3": _hypothesis_result("canonical composite does not separate forward edge", h3),
        "H4": _hypothesis_result("upper-quartile stretch has worse edge", h4),
    }


def report_by_dimension(
    rows: Sequence[EntryMeasurement],
    key: Callable[[EntryMeasurement], str],
) -> dict[str, Any]:
    grouped: dict[str, list[EntryMeasurement]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return {name: summarize_cell(values) for name, values in sorted(grouped.items())}
