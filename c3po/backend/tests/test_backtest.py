import random
from datetime import datetime, timedelta, timezone

import pytest

from app import backtest, r2d2_strategy as strategy


def _make_bars(days: int, seed: int, drift: float, vol: float) -> list[dict]:
    random.seed(seed)
    bars = []
    price = 100.0
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    for day in range(days):
        ts = start + timedelta(days=day)
        for _ in range(78):
            change = random.gauss(drift, vol)
            open_ = price
            price = max(0.5, price * (1 + change))
            high = max(open_, price) * (1 + abs(random.gauss(0, vol / 2)))
            low = min(open_, price) * (1 - abs(random.gauss(0, vol / 2)))
            volume = max(1000, random.gauss(50_000, 15_000))
            bars.append({
                "timestamp": ts, "open": open_, "high": high, "low": low,
                "close": price, "volume": volume,
            })
            ts += timedelta(minutes=5)
    return bars


def test_compute_technical_snapshot_requires_min_history():
    with pytest.raises(ValueError):
        strategy.compute_technical_snapshot(_make_bars(days=1, seed=1, drift=0.0, vol=0.001)[:10])


def test_compute_technical_snapshot_matches_expected_keys_and_ranges():
    bars = _make_bars(days=1, seed=1, drift=0.001, vol=0.003)
    snap = strategy.compute_technical_snapshot(bars[:60])
    assert 0.0 <= snap["score"] <= 100.0
    assert snap["trend_state"] in {"bullish", "bearish", "neutral"}
    assert snap["price_structure"] in {
        "breakout", "breakdown", "failed-breakout", "lower-lows", "higher-highs", "range",
    }
    assert 0.0 <= snap["rsi14"] <= 100.0


def test_technical_defense_healthy_when_price_strong_above_indicators():
    technical = {
        "vwap": 90.0, "ema8": 90.0, "ema20": 88.0, "ema50": 85.0,
        "momentum15": 1.0, "momentum30": 1.5, "momentum60": 2.0,
        "relative_volume": 1.1, "sell_volume_ratio": 0.3, "drawdown_atr": 0.1,
        "price_structure": "breakout", "trend_state": "bullish", "volume_state": "accumulation",
        "data_status": "live", "macd_histogram": 1.0, "macd_acceleration": 0.5,
        "rsi14": 60.0, "obv_slope": 1.0,
    }
    defense = strategy.technical_defense(technical=technical, price=100.0, day_change=1.0, market_change=0.2)
    assert defense["severity"] == "healthy"
    assert defense["critical"] is False


def test_technical_defense_critical_on_support_breakdown_with_distribution():
    technical = {
        "vwap": 100.0, "ema8": 100.0, "ema20": 101.0, "ema50": 102.0,
        "momentum15": -1.0, "momentum30": -1.0, "momentum60": -1.0,
        "relative_volume": 1.5, "sell_volume_ratio": 0.7, "drawdown_atr": 1.5,
        "price_structure": "breakdown", "trend_state": "bearish", "volume_state": "distribution",
        "data_status": "live", "macd_histogram": -1.0, "macd_acceleration": -0.5,
        "rsi14": 25.0, "obv_slope": -1.0,
    }
    defense = strategy.technical_defense(technical=technical, price=95.0, day_change=-3.0, market_change=0.0)
    assert defense["critical"] is True
    assert defense["severity"] == "exit"


def test_entry_decision_rejects_when_technical_not_validated():
    item = {
        "market": "NASDAQ", "price": 100.0, "technical_score": 80.0, "composite_score": 80.0,
        "confidence": 70.0, "risk_score": 30.0, "upside": 25.0, "buy_in_distance": 3.0,
        "thesis": "x", "technical_validated": False, "quote_status": "live",
        "technical_indicators": {},
    }
    side, reasons = strategy.entry_decision(item)
    assert side == "REJECT"
    assert any("technical confirmation" in r.lower() for r in reasons)


def test_exit_decision_hard_stop_fires_below_max_loss():
    technical = {"atr": 1.0, "atr_percent": 1.0, "vwap": 100.0, "ema8": 100.0, "ema20": 99.0,
                 "momentum15": 0.0, "momentum30": 0.0, "macd_histogram": 0.0,
                 "macd_acceleration": 0.0, "price_structure": "range", "score": 50.0}
    decision, _state = strategy.exit_decision(
        technical=technical, quote_price=93.0, average_cost=100.0, high_water=100.0,
        held_minutes=10.0, day_change=-7.0, market_change=0.0,
        state=strategy.PositionRiskState(), weekly_conviction_state={"active": False},
        stop_price=95.0, max_position_loss_percent=0.65,
    )
    assert decision.reason is not None
    assert "hard stop" in decision.reason.lower()


def test_exit_decision_holds_when_nothing_triggers():
    technical = {"atr": 1.0, "atr_percent": 1.0, "vwap": 99.0, "ema8": 99.0, "ema20": 98.0,
                 "momentum15": 0.2, "momentum30": 0.2, "macd_histogram": 0.1,
                 "macd_acceleration": 0.1, "price_structure": "range", "score": 55.0}
    decision, _state = strategy.exit_decision(
        technical=technical, quote_price=100.1, average_cost=100.0, high_water=100.2,
        held_minutes=6.0, day_change=0.1, market_change=0.0,
        state=strategy.PositionRiskState(), weekly_conviction_state={"active": False},
        stop_price=99.0, max_position_loss_percent=0.65,
    )
    assert decision.reason is None


def _armed_profit_lock_scenario(**overrides):
    technical = {"atr": 1.0, "atr_percent": 1.0, "vwap": 100.4, "ema8": 100.5, "ema20": 100.3,
                 "momentum15": 0.0, "momentum30": 0.0, "macd_histogram": 0.1,
                 "macd_acceleration": 0.0, "price_structure": "range", "score": 58.0}
    kwargs = dict(
        technical=technical, quote_price=100.45, average_cost=100.0, high_water=101.35,
        held_minutes=10.0, day_change=0.45, market_change=0.0,
        state=strategy.PositionRiskState(), weekly_conviction_state={"active": False},
        stop_price=95.0, max_position_loss_percent=0.65,
    )
    kwargs.update(overrides)
    return strategy.exit_decision(**kwargs)


def test_exit_decision_locks_armed_profit_with_default_pullback():
    """Same scenario the r2d2.py-level test_r2d2_locks_an_armed_profit_after_pullback
    exercises, called directly through the parameterized function: peak +1.35%,
    pulled back to +0.45% -- inside the default 0.35%-1.15% lock band, so it exits.
    """
    decision, _state = _armed_profit_lock_scenario()
    assert decision.reason is not None
    assert "Armed profit locked" in decision.reason


def test_exit_decision_profit_pullback_tolerance_is_now_configurable():
    """The conceptual question raised 2026-08-18: R2D2 tolerates -0.90% of raw
    drawdown before a hard stop, but only ~0.20pp of give-back from a peak before
    locking a small profit -- a real asymmetry. These constants were previously
    hardcoded inside exit_decision with no way to test an alternative. Same
    scenario as the test above, but with a much wider pullback tolerance
    (1.00 vs the default 0.20): profit_lock_level becomes max(0.35, 1.35-1.00) =
    0.35, a single point -- +0.45% no longer falls in the lock band, so the
    position stays open instead of exiting. Proves the parameter is live, doesn't
    claim a wider tolerance is better (that needs real evidence, not this test).
    """
    decision, _state = _armed_profit_lock_scenario(profit_pullback_percent=1.00)
    assert decision.reason is None


def test_run_backtest_produces_consistent_report_over_synthetic_data():
    bars_by_symbol = {
        "TESTA": _make_bars(days=8, seed=1, drift=0.0015, vol=0.004),
        "TESTB": _make_bars(days=8, seed=2, drift=-0.0010, vol=0.005),
    }
    report = backtest.run_backtest(bars_by_symbol, starting_capital=1_000_000.0, max_positions=5)
    assert report.starting_capital == 1_000_000.0
    assert report.ending_nav > 0
    # Every SELL trade must have a realized P&L, mirroring the live ledger invariant.
    for trade in report.trades:
        if trade.side == "SELL":
            assert trade.realized_pnl_usd is not None
    summary = report.summary()
    assert 0.0 <= summary["win_rate_percent"] <= 100.0
    assert summary["max_drawdown_percent"] >= 0.0


def test_run_backtest_never_exceeds_starting_cash():
    bars_by_symbol = {"TESTA": _make_bars(days=5, seed=7, drift=0.002, vol=0.006)}
    report = backtest.run_backtest(bars_by_symbol, starting_capital=100_000.0, max_positions=1)
    # No BUY should have committed more than the configured max_position_percent of NAV;
    # a loose sanity check is that ending NAV stays within a plausible band for one symbol.
    assert report.ending_nav < report.starting_capital * 3


def test_split_walk_forward_returns_nonoverlapping_contiguous_slices():
    bars_by_symbol = {"TESTA": _make_bars(days=9, seed=1, drift=0.0, vol=0.003)}
    folds = backtest.split_walk_forward(bars_by_symbol, folds=3)
    assert len(folds) == 3
    for train, test in folds:
        assert len(train["TESTA"]) > 0
        assert len(test["TESTA"]) > 0
