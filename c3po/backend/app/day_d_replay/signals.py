from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .features import require_monotonic_feature_availability
from .models import BarFeature, SetupEvaluation, SetupSignal

NEW_YORK = ZoneInfo("America/New_York")
MAX_QQQ_FEATURE_AGE = timedelta(minutes=1)


def _session_date(features: list[BarFeature]):
    if not features:
        raise ValueError("features are required")
    return features[0].bar.start_at.astimezone(NEW_YORK).date()


def _deadline(features: list[BarFeature], value: time) -> datetime:
    return datetime.combine(_session_date(features), value, tzinfo=NEW_YORK)


def _regular_minute(feature: BarFeature) -> tuple[int, int]:
    local = feature.bar.start_at.astimezone(NEW_YORK)
    return local.hour, local.minute


def _three_completed_bars_expiry(
    features: list[BarFeature], *, signal_event_at: datetime, deadline: datetime
) -> datetime:
    completed_after_decision = sorted(
        (
            item.event_at
            for item in features
            if signal_event_at < item.event_at <= deadline
        )
    )
    if len(completed_after_decision) >= 3:
        return completed_after_decision[2]
    if max(item.event_at for item in features) >= deadline:
        return deadline
    # Unit-sized or streaming prefixes may end before the future three-bar
    # window is present. The no-gap schedule remains the only causal fallback.
    return min(signal_event_at + timedelta(minutes=3), deadline)


def _evaluation(
    *,
    setup: str,
    feature: BarFeature | None,
    attempted: bool,
    reasons: list[str],
    signal: SetupSignal | None = None,
) -> SetupEvaluation:
    symbol = feature.bar.symbol if feature is not None else ""
    session_date = (
        feature.bar.start_at.astimezone(NEW_YORK).date()
        if feature is not None
        else None
    )
    return SetupEvaluation(
        setup_version=setup,
        symbol=symbol,
        session_date=session_date,
        attempted=attempted,
        accepted=signal is not None,
        decision_at=signal.decision_at if signal is not None else (
            feature.available_at if feature is not None else None
        ),
        reasons=tuple(reasons),
        signal=signal,
    )


def evaluate_s3(
    features: list[BarFeature],
    qqq_features: list[BarFeature],
    *,
    minimum_tick: float = 0.01,
) -> SetupEvaluation:
    """Evaluate the one-attempt S3-v1 contract over one completed session."""

    if not features:
        return _evaluation(
            setup="S3-v1", feature=None, attempted=False, reasons=["NO_SESSION_BARS"]
        )
    require_monotonic_feature_availability(features)
    require_monotonic_feature_availability(qqq_features)
    ordered = sorted(features, key=lambda item: item.event_at)
    opening_range = [
        item
        for item in ordered
        if (9, 30) <= _regular_minute(item) < (9, 45)
    ]
    expected_minutes = [(9, minute) for minute in range(30, 45)]
    if [_regular_minute(item) for item in opening_range] != expected_minutes:
        return _evaluation(
            setup="S3-v1",
            feature=ordered[0],
            attempted=False,
            reasons=["OPENING_RANGE_MISSING_OR_NONCONTIGUOUS_BAR"],
        )
    opening_high = max(item.bar.high for item in opening_range)
    opening_low = min(item.bar.low for item in opening_range)
    opening_width = opening_high - opening_low
    if opening_width <= 0:
        return _evaluation(
            setup="S3-v1",
            feature=opening_range[-1],
            attempted=False,
            reasons=["OPENING_RANGE_ZERO_WIDTH"],
        )

    raw = next(
        (
            item
            for item in ordered
            if item.bar.start_at.astimezone(NEW_YORK).time() >= time(9, 45)
            and item.bar.close > opening_high
        ),
        None,
    )
    if raw is None:
        return _evaluation(
            setup="S3-v1",
            feature=opening_range[-1],
            attempted=False,
            reasons=["NO_RAW_BREAKOUT"],
        )

    qqq_candidates = [
        item for item in qqq_features if item.event_at <= raw.event_at
    ]
    qqq = max(qqq_candidates, key=lambda item: item.event_at) if qqq_candidates else None
    causal_symbol_features = [item for item in ordered if item.event_at <= raw.event_at]
    causal_qqq_features = (
        [item for item in qqq_features if item.event_at <= qqq.event_at]
        if qqq is not None
        else []
    )
    decision_at = max(
        *(item.available_at for item in causal_symbol_features),
        *(item.available_at for item in causal_qqq_features),
    )
    deadline = _deadline(ordered, time(11, 45))
    expires_at = _three_completed_bars_expiry(
        ordered,
        signal_event_at=raw.event_at,
        deadline=deadline,
    )
    reasons: list[str] = []
    if raw.vwap is None or raw.bar.close <= raw.vwap:
        reasons.append("CLOSE_NOT_ABOVE_VWAP")
    if raw.rvol is None or raw.rvol < 1.5:
        reasons.append("RVOL_BELOW_1_5")
    if raw.atr is None:
        reasons.append("ATR_UNAVAILABLE")
    if qqq is None or qqq.vwap is None or qqq.bar.close <= qqq.vwap:
        reasons.append("QQQ_NOT_ABOVE_VWAP")
    elif raw.event_at - qqq.event_at > MAX_QQQ_FEATURE_AGE:
        reasons.append("QQQ_FEATURE_STALE")
    if raw.bar.close > opening_high + 0.5 * opening_width:
        reasons.append("BREAKOUT_TOO_EXTENDED")
    if raw.event_at.astimezone(NEW_YORK).time() >= time(11, 45):
        reasons.append("S3_DEADLINE_REACHED")
    if decision_at >= expires_at:
        reasons.append("SIGNAL_UNAVAILABLE_BEFORE_EXPIRY")
    if reasons:
        return _evaluation(
            setup="S3-v1", feature=raw, attempted=True, reasons=reasons
        )

    assert raw.vwap is not None
    assert raw.rvol is not None
    assert raw.atr is not None
    assert qqq is not None and qqq.vwap is not None
    signal = SetupSignal(
        setup_version="S3-v1",
        symbol=raw.bar.symbol,
        session_date=_session_date(ordered),
        signal_event_at=raw.event_at,
        signal_available_at=decision_at,
        decision_at=decision_at,
        activation_price=raw.bar.high,
        expires_at=expires_at,
        structural_stop=opening_low,
        stop_rule="max(opening_range_low, entry_time_vwap)",
        entry_atr=raw.atr,
        decision_vwap=raw.vwap,
        rvol=raw.rvol,
        minimum_tick=minimum_tick,
        gate_values={
            "opening_range_high": opening_high,
            "opening_range_low": opening_low,
            "opening_range_width": opening_width,
            "breakout_close": raw.bar.close,
            "breakout_high": raw.bar.high,
            "vwap": raw.vwap,
            "rvol": raw.rvol,
            "atr": raw.atr,
            "qqq_close": qqq.bar.close,
            "qqq_vwap": qqq.vwap,
            "feature_as_of": decision_at.isoformat(),
        },
    )
    return _evaluation(
        setup="S3-v1", feature=raw, attempted=True, reasons=[], signal=signal
    )


def evaluate_s5(
    features: list[BarFeature],
    *,
    minimum_tick: float = 0.01,
) -> SetupEvaluation:
    """Evaluate the one-attempt, completed-bar S5-v1 contract."""

    if not features:
        return _evaluation(
            setup="S5-v1", feature=None, attempted=False, reasons=["NO_SESSION_BARS"]
        )
    require_monotonic_feature_availability(features)
    ordered = sorted(features, key=lambda item: item.event_at)
    excursion_index = next(
        (
            index
            for index, item in enumerate(ordered)
            if item.atr is not None
            and item.vwap is not None
            and item.bar.low <= item.vwap - 1.5 * item.atr
        ),
        None,
    )
    if excursion_index is None:
        return _evaluation(
            setup="S5-v1",
            feature=ordered[-1],
            attempted=False,
            reasons=["NO_1_5_ATR_EXCURSION"],
        )

    excursion = ordered[excursion_index]
    reclaim: BarFeature | None = None
    excursion_low = excursion.bar.low
    for index in range(excursion_index + 1, len(ordered)):
        current = ordered[index]
        previous = ordered[index - 1]
        excursion_low = min(excursion_low, current.bar.low)
        prior_midpoint = (previous.bar.high + previous.bar.low) / 2.0
        if (
            current.bar.close > prior_midpoint
            and current.rvol is not None
            and current.rvol >= 1.5
        ):
            reclaim = current
            break
    if reclaim is None:
        return _evaluation(
            setup="S5-v1",
            feature=excursion,
            attempted=True,
            reasons=["NO_LATER_RECLAIM_WITH_RVOL"],
        )

    reclaim_index = ordered.index(reclaim)
    decision_at = max(item.available_at for item in ordered[: reclaim_index + 1])
    deadline = _deadline(ordered, time(14, 30))
    expires_at = _three_completed_bars_expiry(
        ordered,
        signal_event_at=reclaim.event_at,
        deadline=deadline,
    )
    reasons = []
    if reclaim.event_at.astimezone(NEW_YORK).time() >= time(14, 30):
        reasons.append("S5_DEADLINE_REACHED")
    if decision_at >= expires_at:
        reasons.append("SIGNAL_UNAVAILABLE_BEFORE_EXPIRY")
    if reclaim.atr is None or reclaim.vwap is None or reclaim.rvol is None:
        reasons.append("RECLAIM_FEATURE_UNAVAILABLE")
    elif reclaim.vwap <= reclaim.bar.high:
        reasons.append("S5_TARGET_NOT_ABOVE_EX_ANTE_ENTRY_REFERENCE")
    if reasons:
        return _evaluation(
            setup="S5-v1", feature=reclaim, attempted=True, reasons=reasons
        )

    assert reclaim.atr is not None
    assert reclaim.vwap is not None
    assert reclaim.rvol is not None
    previous = ordered[reclaim_index - 1]
    signal = SetupSignal(
        setup_version="S5-v1",
        symbol=reclaim.bar.symbol,
        session_date=_session_date(ordered),
        signal_event_at=reclaim.event_at,
        signal_available_at=decision_at,
        decision_at=decision_at,
        activation_price=reclaim.bar.high,
        expires_at=expires_at,
        structural_stop=excursion_low - minimum_tick,
        stop_rule="excursion_low_minus_minimum_tick",
        entry_atr=reclaim.atr,
        decision_vwap=reclaim.vwap,
        rvol=reclaim.rvol,
        minimum_tick=minimum_tick,
        gate_values={
            "excursion_event_at": excursion.event_at.isoformat(),
            "excursion_low": excursion_low,
            "reclaim_close": reclaim.bar.close,
            "preceding_bar_midpoint": (previous.bar.high + previous.bar.low) / 2.0,
            "reclaim_high": reclaim.bar.high,
            "ex_ante_entry_reference": reclaim.bar.high,
            "vwap": reclaim.vwap,
            "rvol": reclaim.rvol,
            "atr": reclaim.atr,
            "feature_as_of": decision_at.isoformat(),
        },
    )
    return _evaluation(
        setup="S5-v1", feature=reclaim, attempted=True, reasons=[], signal=signal
    )
