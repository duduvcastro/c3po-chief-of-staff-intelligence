from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo

from .models import BarFeature, MinuteBar, PriorVolumeCurve

NEW_YORK = ZoneInfo("America/New_York")


def require_monotonic_feature_availability(
    features: list[BarFeature],
) -> None:
    """Fail closed when later market events became available before earlier ones."""

    ordered = sorted(features, key=lambda item: item.event_at)
    for previous, current in zip(ordered, ordered[1:]):
        if current.available_at < previous.available_at:
            raise ValueError(
                "feature availability must be monotonic in market-event order"
            )


def cumulative_volume_curve(bars: list[MinuteBar]) -> dict[int, float]:
    """Return cumulative volume keyed by zero-based regular-session minute."""

    if not bars:
        return {}
    ordered = sorted(bars, key=lambda bar: bar.start_at)
    session_open = ordered[0].start_at.astimezone(NEW_YORK).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    cumulative = 0.0
    curve: dict[int, float] = {}
    for bar in ordered:
        minute = int(
            (bar.start_at.astimezone(NEW_YORK) - session_open).total_seconds() // 60
        )
        if minute < 0:
            raise ValueError("regular-session curve cannot contain a pre-open bar")
        cumulative += bar.volume
        curve[minute] = cumulative
    return curve


def build_session_features(
    bars: list[MinuteBar],
    *,
    d1_official_close: float,
    prior_cumulative_volume_curves: list[PriorVolumeCurve],
) -> list[BarFeature]:
    """Build causal Day D VWAP, RVOL and Wilder ATR features.

    The caller supplies prior-session cumulative-volume curves. The current
    session is never included in the RVOL denominator.
    """

    if d1_official_close <= 0:
        raise ValueError("d1_official_close must be positive")
    ordered = sorted(bars, key=lambda bar: bar.start_at)
    if not ordered:
        return []
    if len({bar.start_at for bar in ordered}) != len(ordered):
        raise ValueError("duplicate one-minute bars are not allowed")
    if len({bar.start_at.astimezone(NEW_YORK).date() for bar in ordered}) != 1:
        raise ValueError("build_session_features accepts one session at a time")
    for previous, current in zip(ordered, ordered[1:]):
        if current.available_at < previous.available_at:
            raise ValueError(
                "bar availability must be monotonic in market-event order"
            )

    session_open = ordered[0].start_at.astimezone(NEW_YORK).replace(
        hour=9, minute=30, second=0, microsecond=0
    )
    cumulative_volume = 0.0
    cumulative_price_volume = 0.0
    true_ranges: list[float] = []
    prior_atr: float | None = None
    previous_close = d1_official_close
    features: list[BarFeature] = []

    for bar in ordered:
        minute = int(
            (bar.start_at.astimezone(NEW_YORK) - session_open).total_seconds() // 60
        )
        if minute < 0:
            raise ValueError("features cannot include pre-open bars")
        typical_price = (bar.high + bar.low + bar.close) / 3.0
        cumulative_volume += bar.volume
        cumulative_price_volume += typical_price * bar.volume
        vwap = (
            cumulative_price_volume / cumulative_volume
            if cumulative_volume > 0
            else None
        )

        prior_window = sorted(
            prior_cumulative_volume_curves,
            key=lambda curve: curve.session_date,
        )[-20:]
        same_minute_history = [
            value
            for curve in prior_window
            if (value := curve.value_at(minute)) is not None
        ]
        rvol = None
        if len(same_minute_history) >= 15:
            baseline = float(median(same_minute_history))
            if baseline > 0:
                rvol = cumulative_volume / baseline

        true_range = max(
            bar.high - bar.low,
            abs(bar.high - previous_close),
            abs(bar.low - previous_close),
        )
        true_ranges.append(true_range)
        atr = None
        if len(true_ranges) == 14:
            prior_atr = sum(true_ranges) / 14.0
            atr = prior_atr
        elif len(true_ranges) > 14:
            assert prior_atr is not None
            prior_atr = (prior_atr * 13.0 + true_range) / 14.0
            atr = prior_atr

        features.append(
            BarFeature(
                bar=bar,
                cumulative_volume=cumulative_volume,
                vwap=vwap,
                rvol=rvol,
                atr=atr,
            )
        )
        previous_close = bar.close
    return features


def latest_completed_feature(
    features: list[BarFeature], at: datetime
) -> BarFeature | None:
    """Return the latest feature whose data was available by ``at``."""

    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")
    require_monotonic_feature_availability(features)
    ordered = sorted(features, key=lambda item: item.available_at)
    available_times = [item.available_at for item in ordered]
    index = bisect_right(available_times, at) - 1
    if index < 0:
        return None
    feature = ordered[index]
    if feature.event_at > at:
        return None
    return feature
