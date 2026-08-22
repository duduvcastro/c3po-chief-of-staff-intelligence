from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.day_d_replay.features import build_session_features, latest_completed_feature
from app.day_d_replay.models import BarFeature, MinuteBar, PriorVolumeCurve
from app.day_d_replay.signals import evaluate_s3, evaluate_s5

NEW_YORK = ZoneInfo("America/New_York")


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 21, hour, minute, tzinfo=NEW_YORK)


def _bar(
    index: int,
    *,
    symbol: str = "AAA",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    volume: float = 200.0,
    available_delay_seconds: int = 0,
) -> MinuteBar:
    start = _at(9, 30) + timedelta(minutes=index)
    end = start + timedelta(minutes=1)
    return MinuteBar(
        symbol=symbol,
        start_at=start,
        end_at=end,
        available_at=end + timedelta(seconds=available_delay_seconds),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _feature(
    index: int,
    *,
    symbol: str = "AAA",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    vwap: float = 100.0,
    rvol: float = 2.0,
    atr: float = 1.0,
    available_delay_seconds: int = 0,
) -> BarFeature:
    bar = _bar(
        index,
        symbol=symbol,
        open_=open_,
        high=high,
        low=low,
        close=close,
        available_delay_seconds=available_delay_seconds,
    )
    return BarFeature(bar, 1000.0, vwap, rvol, atr)


def _prior_curves(symbol: str = "AAA") -> list[PriorVolumeCurve]:
    points = tuple((minute, (minute + 1) * 100.0) for minute in range(15))
    return [
        PriorVolumeCurve(
            symbol=symbol,
            session_date=date(2026, 8, 20) - timedelta(days=19 - index),
            available_at=datetime(2026, 8, 20, 16, tzinfo=NEW_YORK),
            cumulative_volume_by_minute=points,
        )
        for index in range(20)
    ]


def test_features_use_completed_bars_prior_sessions_and_wilder_atr() -> None:
    bars = tuple(_bar(index) for index in range(15))
    features = build_session_features(
        list(bars),
        d1_official_close=100.0,
        prior_cumulative_volume_curves=_prior_curves(),
    )

    assert features[0].rvol == pytest.approx(2.0)
    assert features[12].atr is None
    assert features[13].atr == pytest.approx(2.0)
    assert features[14].atr == pytest.approx(2.0)
    assert latest_completed_feature(features, _at(9, 44)) is features[13]


def test_features_normalize_utc_feed_timestamps_to_exchange_minutes() -> None:
    bars = tuple(
        MinuteBar(
            symbol=bar.symbol,
            start_at=bar.start_at.astimezone(timezone.utc),
            end_at=bar.end_at.astimezone(timezone.utc),
            available_at=bar.available_at.astimezone(timezone.utc),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in (_bar(index) for index in range(15))
    )
    features = build_session_features(
        list(bars),
        d1_official_close=100.0,
        prior_cumulative_volume_curves=_prior_curves(),
    )

    assert features[0].rvol == pytest.approx(2.0)
    assert features[14].rvol == pytest.approx(2.0)


def test_s3_uses_first_breakout_only_and_does_not_rearm() -> None:
    opening = [_feature(index) for index in range(15)]
    first_failed = _feature(
        15,
        high=101.4,
        low=99.8,
        close=101.2,
        vwap=100.0,
        rvol=1.2,
    )
    later_valid = _feature(
        16,
        high=101.5,
        low=99.9,
        close=101.3,
        vwap=100.0,
        rvol=2.0,
    )
    qqq = [
        _feature(index, symbol="QQQ", open_=500, high=501, low=499, close=500.5, vwap=500)
        for index in range(17)
    ]

    evaluation = evaluate_s3(opening + [first_failed, later_valid], qqq)

    assert evaluation.attempted is True
    assert evaluation.accepted is False
    assert evaluation.decision_at == first_failed.available_at
    assert "RVOL_BELOW_1_5" in evaluation.reasons


def test_s3_decision_waits_for_delayed_opening_range_input() -> None:
    opening = [_feature(index) for index in range(15)]
    opening[5] = _feature(5, available_delay_seconds=1400)
    breakout = _feature(15, high=101.4, low=99.8, close=101.2, vwap=100.0)
    qqq = [
        _feature(index, symbol="QQQ", open_=500, high=501, low=499, close=500.5, vwap=500)
        for index in range(16)
    ]

    evaluation = evaluate_s3(opening + [breakout], qqq)

    assert evaluation.signal is None
    assert "SIGNAL_UNAVAILABLE_BEFORE_EXPIRY" in evaluation.reasons


def test_s3_expiry_counts_three_completed_bars_instead_of_wall_minutes() -> None:
    opening = [_feature(index) for index in range(15)]
    breakout = _feature(
        15,
        high=101.4,
        low=99.8,
        close=101.2,
        vwap=100.0,
        rvol=2.0,
    )
    later_bars_with_gap = [_feature(index) for index in (17, 18, 19)]
    qqq = [
        _feature(
            index,
            symbol="QQQ",
            open_=500,
            high=501,
            low=499,
            close=500.5,
            vwap=500,
        )
        for index in range(20)
    ]

    evaluation = evaluate_s3(opening + [breakout] + later_bars_with_gap, qqq)

    assert evaluation.signal is not None
    assert evaluation.signal.decision_at == _at(9, 46)
    assert evaluation.signal.expires_at == _at(9, 50)


def test_s5_freezes_first_excursion_and_later_completed_reclaim() -> None:
    features = [
        _feature(index, high=100.1, low=99.95, close=100.0, atr=0.2, rvol=1.0)
        for index in range(13)
    ]
    excursion = _feature(
        13, high=100.0, low=99.6, close=99.8, vwap=100.0, atr=0.2, rvol=1.0
    )
    reclaim = _feature(
        14, high=100.1, low=99.8, close=100.01, vwap=99.98, atr=0.2, rvol=2.0
    )

    evaluation = evaluate_s5(features + [excursion, reclaim])

    assert evaluation.accepted is True
    assert evaluation.signal is not None
    assert evaluation.signal.session_date == date(2026, 8, 21)
    assert evaluation.signal.structural_stop == pytest.approx(99.59)
    assert evaluation.signal.activation_price == pytest.approx(100.1)
    assert evaluation.signal.target_hint is None
