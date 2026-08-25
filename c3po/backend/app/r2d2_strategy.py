"""Pure R2D2 decision logic, extracted from ``r2d2.py``.

This module has ZERO external dependencies (stdlib only: ``statistics``).
That is deliberate: it lets the exact same entry/exit/defense math run
inside the live FastAPI service *and* inside an offline backtest, so the
two never drift apart. ``r2d2.py`` should import from here instead of
re-implementing this logic; ``backtest.py`` imports from here too.

IMPORTANT — fidelity note for whoever wires this into r2d2.py:
The functions below were ported line-for-line from the current
``R2D2PaperService`` methods (``_technical_defense``, ``_weekly_conviction``,
``_entry_decision``, the exit cascade inside ``_mark_and_exit``, ``_ema`` and
``_target_position_percent``) as of methodology version
R2D2-HYBRID-V16-ASYMMETRIC-DEFENSE. Every threshold that used to live on
``self`` (policy dict, ``self.settings.*``) is now an explicit parameter
with the same default the live code currently uses, so behaviour is
unchanged. Until ``r2d2.py`` is refactored to actually call these
functions instead of its own inline copies, THE TWO COPIES CAN DRIFT --
treat this module as the source of truth and port any future rule change
here first.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirrors the module-level constants in r2d2.py as of V16)
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION = "R2D2-HYBRID-V27-15M-LIQUIDITY-FLOOR"

RISK_BUDGET_PERCENT = 0.02  # % of NAV risked per trade (Turtle-style; backtested vs. 0.06/0.09)
# Lowered from 0.03 on 2026-08-20 for the test phase, deliberately in the
# opposite direction of widening the daily loss limit: the actual goal
# (accumulate enough real fills to learn from) is measured in trade count,
# not dollars. At 2/3 the risk per trade, the same daily loss-limit ceiling
# takes ~50% more losing trades to reach, so a wider limit doesn't have to
# mean proportionally more dollars at risk.

MIN_HOLD_MINUTES = 5
PROFIT_TRIGGER_PERCENT = 0.65
PROFIT_LOCK_FLOOR_PERCENT = 0.35
PROFIT_PULLBACK_PERCENT = 0.35
WEEKLY_PROFIT_HARVEST_FRACTION = 0.70
WEEKLY_CONVICTION_MIN_SCORE = 72.0
MIN_POSITION_PERCENT = 2.0
MAX_DYNAMIC_POSITION_PERCENT = 6.0
SIMULATED_ROUND_TRIP_COST_PERCENT = 0.28
US_EXIT_SLIPPAGE_RATE = 0.0010
US_EXIT_FEE_RATE = 0.0004
MIN_INTRADAY_EDGE_PERCENT = 0.55
# Raised from 1.05 on 2026-08-20 per an independent methodology review: 1.05
# is barely above "normal" volume and does almost nothing to confirm a
# breakout has real participation behind it. ORB/momentum literature treats
# a breakout on merely-average volume as a weak signal ("buyer's trap");
# 1.5x median volume is closer to what's actually used to confirm genuine
# institutional participation. Tightening only -- makes both entry routes
# more conservative, not less, so the downside is bounded to fewer trades.
ENTRY_RELATIVE_VOLUME_MIN = 1.5
FAILED_ENTRY_MINUTES = 3
FAILED_ENTRY_LOSS_PERCENT = 0.30
# Matches FAILED_ENTRY_LOSS_PERCENT on purpose (root-caused 2026-08-20 against
# real trades: RGA/HTHT realized only +0.08%/+0.13% via this exact rule while
# same-day failed-entry losses ran to -0.44%/-0.76% -- the old 0.15 floor let
# the fast, vote-based gain protection lock in almost nothing, while its
# mirror-image loss rule waited for a loss twice as deep before reacting).
GAIN_PROTECTION_MIN_PERCENT = 0.30
END_OF_DAY_PROFIT_EXIT_LEAD_SECONDS = 30

# Defaults for settings that live on Settings() in production.
DEFAULT_MAX_POSITION_LOSS_PERCENT = 0.65  # hard stop
DEFAULT_SOFT_LOSS_EXIT_PERCENT = 0.25
DEFAULT_MAX_POSITION_PERCENT = 5.0

BASE_ENTRY_POLICY: dict[str, float] = {
    "entry_upside_floor": 20.0,
    "max_risk_score": 48.0,
    "min_confidence": 60.0,
    "max_buy_in_distance": 15.0,
    "min_technical_score": 58.0,
    "min_composite_score": 62.0,
}
ENTRY_POLICY_BOUNDS: dict[str, tuple[float, float]] = {
    "entry_upside_floor": (18.0, 28.0),
    "max_risk_score": (40.0, 52.0),
    "min_confidence": (58.0, 72.0),
    "max_buy_in_distance": (8.0, 15.0),
    "min_technical_score": (55.0, 68.0),
    "min_composite_score": (60.0, 72.0),
}

ACTIVE_MARKETS = ("NASDAQ", "NYSE")


def estimated_net_exit_pnl_percent(
    quote_price: float,
    average_cost: float,
    *,
    slippage_rate: float = US_EXIT_SLIPPAGE_RATE,
    fee_rate: float = US_EXIT_FEE_RATE,
) -> float:
    """Return realizable P&L after the still-unpaid exit leg.

    ``average_cost`` already includes entry fill slippage and entry fees in
    the paper ledger. Subtracting the full round-trip cost here would count
    that entry friction twice. This mirrors ``R2D2PaperService._sell``:
    expected fill first, then the fee on those sale proceeds.
    """
    if quote_price <= 0 or average_cost <= 0:
        return 0.0
    expected_fill = quote_price * (1 - max(0.0, slippage_rate))
    net_proceeds = expected_fill * (1 - max(0.0, fee_rate))
    return (net_proceeds / average_cost - 1) * 100


def hard_stop_quote_price(
    average_cost: float,
    max_net_loss_percent: float,
    *,
    slippage_rate: float = US_EXIT_SLIPPAGE_RATE,
    fee_rate: float = US_EXIT_FEE_RATE,
) -> float:
    """Quote threshold whose simulated sale realizes the configured net loss."""
    net_exit_factor = (1 - max(0.0, slippage_rate)) * (1 - max(0.0, fee_rate))
    if average_cost <= 0 or net_exit_factor <= 0:
        return 0.0
    return average_cost * (1 - max_net_loss_percent / 100) / net_exit_factor


def entry_stop_quote_price(
    quote_price: float,
    atr: float,
    *,
    max_position_loss_percent: float = DEFAULT_MAX_POSITION_LOSS_PERCENT,
) -> float:
    """Return the entry technical stop anchored to the execution-time quote."""
    if quote_price <= 0:
        return 0.0
    stop_distance = min(
        quote_price * max(0.0, max_position_loss_percent) / 100,
        max(max(0.0, atr) * 0.45, quote_price * 0.004),
    )
    return quote_price - stop_distance


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Indicators (ported from R2D2PaperService._technical_snapshot / _ema)
# ---------------------------------------------------------------------------

def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def compute_technical_snapshot(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure port of ``_technical_snapshot``'s indicator math.

    ``bars`` must be pre-sorted ascending by timestamp, each a dict with
    ``open``, ``high``, ``low``, ``close``, ``volume`` and a ``timestamp``
    (``datetime.date``-compatible, only used to slice the current session
    for VWAP). Unlike the live method, this does NOT fetch data, cache
    anything, or apply a live-quote override -- callers (e.g. the
    backtest engine) are responsible for windowing the bars correctly
    before calling this.
    """
    if len(bars) < 35:
        raise ValueError("fewer than 35 valid five-minute candles")
    closes = [b["close"] for b in bars]
    volumes = [b["volume"] for b in bars]
    ema8 = ema(closes, 8)
    ema12 = ema(closes, 12)
    ema20 = ema(closes, 20)
    ema26 = ema(closes, 26)
    ema50 = ema(closes, 50)
    macd_series = [
        ema(closes[:index], 12) - ema(closes[:index], 26)
        for index in range(26, len(closes) + 1)
    ]
    macd = ema12 - ema26
    macd_signal = ema(macd_series, 9)
    macd_histogram = macd - macd_signal
    prior_macd_signal = ema(macd_series[:-1], 9) if len(macd_series) > 9 else macd_signal
    prior_macd = macd_series[-2] if len(macd_series) > 1 else macd
    macd_acceleration = macd_histogram - (prior_macd - prior_macd_signal)
    deltas = [current - prior for prior, current in zip(closes[-15:-1], closes[-14:])]
    gains = sum(max(delta, 0.0) for delta in deltas) / 14
    losses = sum(max(-delta, 0.0) for delta in deltas) / 14
    rsi = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    session_date = bars[-1]["timestamp"].date() if hasattr(bars[-1]["timestamp"], "date") else bars[-1]["timestamp"]
    session_bars = [
        b for b in bars
        if (b["timestamp"].date() if hasattr(b["timestamp"], "date") else b["timestamp"]) == session_date
    ] or bars[-78:]
    typical = [(b["high"] + b["low"] + b["close"]) / 3 for b in session_bars]
    session_volumes = [b["volume"] for b in session_bars]
    volume_sum = sum(session_volumes)
    vwap = (
        sum(price * volume for price, volume in zip(typical, session_volumes)) / volume_sum
        if volume_sum else statistics.mean([b["close"] for b in session_bars])
    )
    true_ranges = []
    for previous, bar in zip(bars[-15:-1], bars[-14:]):
        true_ranges.append(max(
            bar["high"] - bar["low"], abs(bar["high"] - previous["close"]),
            abs(bar["low"] - previous["close"]),
        ))
    atr = statistics.mean(true_ranges) if true_ranges else closes[-1] * 0.02
    median_volume = statistics.median(volumes[-23:-3]) or 1.0
    relative_volume = statistics.mean(volumes[-3:]) / median_volume
    momentum15 = (closes[-1] / closes[-4] - 1) * 100
    momentum30 = (closes[-1] / closes[-7] - 1) * 100
    momentum60 = (closes[-1] / closes[-13] - 1) * 100
    ema8_prior = ema(closes[:-3], 8)
    ema20_prior = ema(closes[:-3], 20)
    ema8_slope = (ema8 / ema8_prior - 1) * 100 if ema8_prior else 0.0
    ema20_slope = (ema20 / ema20_prior - 1) * 100 if ema20_prior else 0.0
    vwap_distance = (closes[-1] / vwap - 1) * 100 if vwap else 0.0
    prior_high = max(bar["high"] for bar in bars[-21:-1])
    recent = bars[-6:]
    previous_window = bars[-12:-6]
    older_window = bars[-21:-6]
    higher_high = max(bar["high"] for bar in recent) > max(bar["high"] for bar in previous_window)
    higher_low = min(bar["low"] for bar in recent) > min(bar["low"] for bar in previous_window)
    lower_high = max(bar["high"] for bar in recent) < max(bar["high"] for bar in previous_window)
    lower_low = min(bar["low"] for bar in recent) < min(bar["low"] for bar in previous_window)
    failed_breakout = (
        max(bar["high"] for bar in recent) > max(bar["high"] for bar in older_window)
        and closes[-1] < max(bar["high"] for bar in older_window)
        and momentum15 < 0
    )
    if closes[-1] >= prior_high:
        price_structure = "breakout"
    elif closes[-1] < min(bar["low"] for bar in previous_window):
        price_structure = "breakdown"
    elif failed_breakout:
        price_structure = "failed-breakout"
    elif lower_high and lower_low:
        price_structure = "lower-lows"
    elif higher_high and higher_low:
        price_structure = "higher-highs"
    else:
        price_structure = "range"
    obv = [0.0]
    for prior, current, volume in zip(closes[-25:-1], closes[-24:], volumes[-24:]):
        obv.append(obv[-1] + (volume if current > prior else -volume if current < prior else 0.0))
    obv_scale = max(sum(volumes[-12:]), 1.0)
    obv_slope = (obv[-1] - obv[-7]) / obv_scale * 100 if len(obv) >= 7 else 0.0
    positive_flow = negative_flow = 0.0
    flow_bars = bars[-15:]
    flow_typical = [(b["high"] + b["low"] + b["close"]) / 3 for b in flow_bars]
    for prior, current, bar in zip(flow_typical[:-1], flow_typical[1:], flow_bars[1:]):
        flow = current * bar["volume"]
        if current >= prior:
            positive_flow += flow
        else:
            negative_flow += flow
    mfi = 100.0 if negative_flow == 0 else 100 - 100 / (1 + positive_flow / negative_flow)
    atr_percent = atr / closes[-1] * 100
    recent_high = max(bar["high"] for bar in bars[-13:])
    drawdown_atr = max(0.0, (recent_high - closes[-1]) / max(atr, closes[-1] * 0.001))
    pressure_bars = bars[-6:]
    pressure_volume = sum(bar["volume"] for bar in pressure_bars)
    sell_volume_ratio = (
        sum(bar["volume"] for bar in pressure_bars if bar["close"] < bar["open"]) / pressure_volume
        if pressure_volume else 0.5
    )
    path = sum(abs(current - prior) for prior, current in zip(closes[-13:-1], closes[-12:]))
    trend_efficiency = abs(closes[-1] - closes[-13]) / path if path else 0.0
    trend_score = 50.0
    trend_score += 18 if closes[-1] > vwap else -18
    trend_score += 18 if ema8 > ema20 else -18
    trend_score += 10 if ema20 > ema50 else -10
    trend_score += min(10.0, trend_efficiency * 20) if momentum60 > 0 else -min(10.0, trend_efficiency * 20)
    momentum_score = 50.0
    momentum_score += 12 if 50 <= rsi <= 68 else 5 if 44 <= rsi < 50 else -15 if rsi < 38 or rsi > 78 else -4
    momentum_score += 14 if macd_histogram > 0 else -14
    momentum_score += 10 if macd_acceleration > 0 else -10
    momentum_score += 8 if momentum15 > 0 and momentum30 > 0 else -8
    flow_score = 50.0
    flow_score += (
        18 if relative_volume >= 1.2 and momentum15 > 0
        else -14 if relative_volume >= 1.2 and momentum15 < 0
        else 4 if relative_volume >= 0.8 else -8
    )
    flow_score += max(-15.0, min(15.0, obv_slope * 3.0))
    flow_score += 8 if 52 <= mfi <= 78 else -8 if mfi < 35 or mfi > 88 else 0
    structure_score = {
        "breakout": 90.0, "higher-highs": 75.0, "range": 50.0,
        "failed-breakout": 28.0, "lower-lows": 24.0, "breakdown": 12.0,
    }[price_structure]
    volatility_score = 72.0 if 0.25 <= atr_percent <= 3.5 else 48.0 if atr_percent <= 5 else 20.0
    score = (
        max(0.0, min(100.0, trend_score)) * 0.30
        + max(0.0, min(100.0, momentum_score)) * 0.25
        + max(0.0, min(100.0, flow_score)) * 0.20
        + structure_score * 0.15
        + volatility_score * 0.10
    )
    trend_state = "bullish" if trend_score >= 65 else "bearish" if trend_score < 42 else "neutral"
    volume_state = "accumulation" if flow_score >= 65 else "distribution" if flow_score < 40 else "neutral"
    return {
        "score": round(max(0.0, min(100.0, score)), 2), "vwap": round(vwap, 6),
        "ema8": round(ema8, 6), "ema20": round(ema20, 6), "ema50": round(ema50, 6),
        "rsi14": round(rsi, 3), "macd": round(macd, 6), "macd_signal": round(macd_signal, 6),
        "macd_histogram": round(macd_histogram, 6), "macd_acceleration": round(macd_acceleration, 6),
        "momentum15": round(momentum15, 3), "momentum30": round(momentum30, 3),
        "momentum60": round(momentum60, 3),
        "ema8_slope15": round(ema8_slope, 4), "ema20_slope15": round(ema20_slope, 4),
        "vwap_distance_percent": round(vwap_distance, 4),
        "relative_volume": round(relative_volume, 3), "atr": round(atr, 6),
        "atr_percent": round(atr_percent, 3), "obv_slope": round(obv_slope, 3),
        "sell_volume_ratio": round(sell_volume_ratio, 4),
        "drawdown_atr": round(drawdown_atr, 3),
        "mfi14": round(mfi, 3), "trend_efficiency": round(trend_efficiency, 3),
        "price_structure": price_structure, "trend_state": trend_state,
        "volume_state": volume_state, "data_status": "live",
        "trend_score": round(max(0.0, min(100.0, trend_score)), 2),
        "momentum_score": round(max(0.0, min(100.0, momentum_score)), 2),
        "flow_score": round(max(0.0, min(100.0, flow_score)), 2),
    }


# ---------------------------------------------------------------------------
# Technical defense / weekly conviction (ported verbatim from r2d2.py)
# ---------------------------------------------------------------------------

def technical_defense(*, technical: dict[str, Any], price: float,
                       day_change: float, market_change: float) -> dict[str, Any]:
    """Weight trend, structure, flow and volatility instead of a raw loss percentage."""
    drivers: list[str] = []
    score = 0.0

    def add(condition: bool, weight: float, label: str) -> None:
        nonlocal score
        if condition:
            score += weight
            drivers.append(label)

    vwap = _float(technical.get("vwap"), price)
    ema8 = _float(technical.get("ema8"), price)
    ema20 = _float(technical.get("ema20"), price)
    ema50 = _float(technical.get("ema50"), price)
    momentum15 = _float(technical.get("momentum15"))
    momentum30 = _float(technical.get("momentum30"))
    momentum60 = _float(technical.get("momentum60"))
    relative_volume = _float(technical.get("relative_volume"), 1.0)
    sell_volume_ratio = _float(technical.get("sell_volume_ratio"), 0.5)
    drawdown_atr = _float(technical.get("drawdown_atr"))
    relative_strength = day_change - market_change
    structure = str(technical.get("price_structure") or "range")
    trend_state = str(technical.get("trend_state") or "neutral")
    volume_state = str(technical.get("volume_state") or "neutral")
    actionable = str(technical.get("data_status") or "unavailable") == "live"

    add(price < vwap, 6, "price below VWAP")
    add(price < ema8, 6, "price below EMA8")
    add(ema8 < ema20, 10, "EMA8 below EMA20")
    add(ema20 < ema50, 8, "EMA20 below EMA50")
    add(_float(technical.get("ema8_slope15")) < -0.05, 6, "EMA8 falling")
    add(_float(technical.get("ema20_slope15")) < -0.03, 6, "EMA20 falling")
    add(trend_state == "bearish", 8, "bearish trend regime")
    add(structure == "breakdown", 22, "support breakdown")
    add(structure == "failed-breakout", 16, "failed breakout")
    add(structure == "lower-lows", 14, "lower highs and lower lows")
    add(
        _float(technical.get("macd_histogram")) < 0
        and _float(technical.get("macd_acceleration")) < 0,
        8, "MACD weakening",
    )
    add(momentum15 < -0.15, 4, "15-minute momentum negative")
    add(momentum30 < -0.35, 6, "30-minute momentum negative")
    add(momentum60 < -0.60, 6, "60-minute momentum negative")
    add(_float(technical.get("rsi14"), 50.0) < 38, 4, "RSI below 38")
    add(volume_state == "distribution", 9, "volume distribution")
    add(relative_volume >= 1.2 and momentum15 < 0, 8, "selloff on elevated volume")
    add(_float(technical.get("obv_slope")) < -0.5, 4, "OBV declining")
    add(sell_volume_ratio >= 0.62, 6, "selling dominates recent volume")
    add(drawdown_atr >= 0.75, 4, "pullback exceeds 0.75 ATR")
    add(drawdown_atr >= 1.25, 5, "pullback exceeds 1.25 ATR")
    add(relative_strength <= -0.50, 4, "underperforming held-market peers")
    add(relative_strength <= -1.00, 4, "severe relative underperformance")

    score = round(min(100.0, score), 1)
    critical = actionable and (
        score >= 82
        or (
            structure == "breakdown"
            and (volume_state == "distribution" or sell_volume_ratio >= 0.62)
            and relative_volume >= 1.05
        )
    )
    severity = "exit" if critical or score >= 72 else "reduce" if score >= 55 else "watch" if score >= 40 else "healthy"
    return {
        "score": score, "severity": severity, "critical": critical, "actionable": actionable,
        "drivers": drivers, "relative_strength_percent": round(relative_strength, 3),
        "model": "weighted trend-structure-flow-volatility v1",
    }


def weekly_conviction(*, strategy: dict[str, Any], technical: dict[str, Any],
                       price: float, high_water: float, atr: float,
                       bearish_votes: int) -> dict[str, Any]:
    fundamental = max(0.0, min(100.0, _float(strategy.get("fundamental_score"), 50.0)))
    confidence = max(0.0, min(100.0, _float(strategy.get("confidence"), 50.0)))
    technical_score = max(0.0, min(100.0, _float(technical.get("score"), 50.0)))
    trend_state = str(technical.get("trend_state") or "neutral")
    volume_state = str(technical.get("volume_state") or "neutral")
    price_structure = str(technical.get("price_structure") or "neutral")
    data_status = str(technical.get("data_status") or "unavailable")
    trend_score = _float(
        technical.get("trend_score"),
        82.0 if trend_state == "bullish" else 30.0 if trend_state == "bearish" else 50.0,
    )
    flow_score = _float(
        technical.get("flow_score"),
        78.0 if volume_state == "accumulation" else 30.0 if volume_state == "distribution" else 50.0,
    )
    momentum_score = _float(technical.get("momentum_score"), 50.0)
    if "momentum_score" not in technical:
        momentum_score += 15.0 if _float(technical.get("momentum30")) > 0 else -15.0
        momentum_score += 10.0 if _float(technical.get("macd_histogram")) > 0 else -10.0
    momentum_score = max(0.0, min(100.0, momentum_score))
    score = round(
        fundamental * 0.25 + confidence * 0.15 + technical_score * 0.25
        + trend_score * 0.15 + flow_score * 0.10 + momentum_score * 0.10,
        2,
    )
    drawdown = max(0.0, high_water - price)
    drawdown_limit = max(atr * 1.75, high_water * 0.0175)
    gates = {
        "fresh market data": data_status == "live",
        "fundamental conviction": fundamental >= 68.0 and confidence >= 60.0,
        "bullish live trend": technical_score >= 65.0 and trend_state == "bullish",
        "constructive price structure": price_structure in {"higher-highs", "breakout"},
        "non-distributive flow": volume_state != "distribution" and flow_score >= 55.0,
        "positive momentum": momentum_score >= 60.0,
        "controlled pullback": drawdown <= drawdown_limit,
        "no confirmed reversal": bearish_votes <= 1,
    }
    reasons = [label for label, passed in gates.items() if passed]
    return {
        "active": score >= WEEKLY_CONVICTION_MIN_SCORE and all(gates.values()),
        "score": score, "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Entry decision (ported from R2D2PaperService._entry_decision)
# ---------------------------------------------------------------------------

def entry_decision(item: dict[str, Any], policy: dict[str, float] | None = None) -> tuple[str, list[str]]:
    policy = policy or BASE_ENTRY_POLICY
    indicators = dict(item.get("technical_indicators") or {})
    tactical_structure = (
        str(indicators.get("price_structure")) in {"higher-highs", "breakout"}
        or (
            str(indicators.get("volume_state")) == "accumulation"
            and item["technical_score"] >= 78.0
        )
    )
    tactical_route = all((
        bool(item.get("technical_validated")),
        item.get("market") not in ACTIVE_MARKETS or item.get("quote_status") == "live",
        item["upside"] >= 20.0,
        item["risk_score"] <= 55.0,
        item["confidence"] >= 65.0,
        item["buy_in_distance"] <= 20.0,
        item["technical_score"] >= 72.0,
        item["composite_score"] >= 72.0,
        str(indicators.get("data_status")) == "live",
        str(indicators.get("trend_state")) == "bullish",
        str(indicators.get("volume_state")) != "distribution",
        tactical_structure,
        _float(indicators.get("relative_volume"), 1.0) >= ENTRY_RELATIVE_VOLUME_MIN,
        _float(item.get("price")) >= _float(indicators.get("vwap")) > 0,
        _float(item.get("price")) >= _float(indicators.get("ema8")) > 0,
        _float(indicators.get("ema8")) > _float(indicators.get("ema20")) > 0,
        _float(indicators.get("momentum15")) >= 0.10,
        _float(indicators.get("momentum30")) >= 0.15,
        _float(indicators.get("macd_histogram")) > 0,
        _float(indicators.get("macd_acceleration")) >= 0,
        48.0 <= _float(indicators.get("rsi14")) <= 76.0,
        _float(indicators.get("relative_strength")) > 0,
    ))
    if tactical_route:
        return "BUY", [
            item.get("thesis", ""),
            "Tactical quality-momentum route passed with fresh data, bullish structure and controlled risk.",
        ]
    momentum15 = _float(indicators.get("momentum15"))
    momentum30 = _float(indicators.get("momentum30"))
    momentum60 = _float(indicators.get("momentum60"))
    relative_volume = _float(indicators.get("relative_volume"), 1.0)
    price = _float(item.get("price"))
    vwap = _float(indicators.get("vwap"))
    ema8 = _float(indicators.get("ema8"))
    ema20 = _float(indicators.get("ema20"))
    macd_histogram = _float(indicators.get("macd_histogram"))
    macd_acceleration = _float(indicators.get("macd_acceleration"))
    rsi14 = _float(indicators.get("rsi14"))
    relative_strength = _float(indicators.get("relative_strength"))
    modeled_edge = round(
        max(momentum15, 0.0) * 0.45
        + max(momentum30, 0.0) * 0.25
        + max(momentum60, 0.0) * 0.10
        + max(relative_volume - 1.0, 0.0) * 0.20
        + max(item["technical_score"] - 60.0, 0.0) * 0.015,
        3,
    )
    intraday_structure = str(indicators.get("price_structure")) in {"higher-highs", "breakout"}
    intraday_route = all((
        bool(item.get("technical_validated")),
        item.get("market") in ACTIVE_MARKETS,
        item.get("quote_status") == "live",
        item["upside"] >= 0.0,
        item["risk_score"] <= 55.0,
        item["confidence"] >= 55.0,
        item["buy_in_distance"] <= 25.0,
        item["technical_score"] >= 72.0,
        item["composite_score"] >= 62.0,
        str(indicators.get("data_status")) == "live",
        str(indicators.get("trend_state")) == "bullish",
        str(indicators.get("volume_state")) != "distribution",
        intraday_structure,
        momentum15 >= 0.15,
        momentum30 >= 0.20,
        momentum60 > 0,
        relative_volume >= ENTRY_RELATIVE_VOLUME_MIN,
        price > 0 and vwap > 0 and price >= vwap,
        ema8 > 0 and ema20 > 0 and price >= ema8 and ema8 > ema20,
        macd_histogram > 0 and macd_acceleration >= 0,
        48.0 <= rsi14 <= 74.0,
        relative_strength > 0,
        modeled_edge >= MIN_INTRADAY_EDGE_PERCENT,
    ))
    item["modeled_intraday_edge_percent"] = modeled_edge
    item["simulated_round_trip_cost_percent"] = SIMULATED_ROUND_TRIP_COST_PERCENT
    if intraday_route:
        return "BUY", [
            item.get("thesis", ""),
            (
                f"Cost-aware intraday route passed with {modeled_edge:.2f}% modeled edge "
                f"versus {SIMULATED_ROUND_TRIP_COST_PERCENT:.2f}% simulated round-trip friction."
            ),
        ]
    reasons: list[str] = []
    if item.get("market") in ACTIVE_MARKETS and item.get("quote_status") != "live":
        reasons.append("Current US quote is not live; paper entry blocked")
    if not item.get("technical_validated"):
        reasons.append("Five-minute technical confirmation is unavailable")
    if item["upside"] < policy["entry_upside_floor"]:
        reasons.append(f"C3PO TP upside below {policy['entry_upside_floor']:.2f}% adaptive paper-entry floor")
    if item["risk_score"] > policy["max_risk_score"]:
        reasons.append(f"Risk score above adaptive {policy['max_risk_score']:.2f}/100 ceiling")
    if item["confidence"] < policy["min_confidence"]:
        reasons.append(f"Valuation confidence below adaptive {policy['min_confidence']:.2f}% floor")
    if item["buy_in_distance"] > policy["max_buy_in_distance"]:
        reasons.append(f"Price is more than {policy['max_buy_in_distance']:.2f}% above disciplined buy-in")
    if item["technical_score"] < policy["min_technical_score"]:
        reasons.append("Intraday/day momentum confirmation is insufficient")
    if item["composite_score"] < policy["min_composite_score"]:
        reasons.append(f"Hybrid score below adaptive {policy['min_composite_score']:.2f}/100 floor")
    reasons.append(
        "Neither strict tactical nor cost-aware intraday entry route passed all technical gates"
    )
    return "REJECT", reasons


def target_position_percent(item: dict[str, Any], *, cash_overhang_percent: float = 0.0,
                             max_position_percent: float = DEFAULT_MAX_POSITION_PERCENT) -> float:
    """Turtle-style risk-normalized sizing: fix the dollars at risk, not the
    dollars deployed.

    Backtested 2026-08-20 against the old conviction-scored formula (which
    varied 2-6% of NAV by composite/confidence/technical/risk score, deployed
    idle cash more aggressively, but let position size drift independently of
    how far away the stop actually was): risking a flat RISK_BUDGET_PERCENT of
    NAV per trade, sized inversely to the ATR-derived stop distance, produced
    the best risk-adjusted profile of the three budgets tested (0.03/0.06/0.09%)
    -- best payoff ratio, lowest drawdown, best Sharpe. cash_overhang_percent
    is accepted for call-site compatibility but intentionally unused: the prior
    deployment-pressure boost is exactly the kind of conviction-independent
    sizing distortion this formula replaces.
    """
    indicators = dict(item.get("technical_indicators") or {})
    atr_percent = max(0.0, _float(indicators.get("atr_percent"), 2.5))
    stop_distance_percent = max(DEFAULT_MAX_POSITION_LOSS_PERCENT, min(1.5, atr_percent * 2.0))
    maximum = min(MAX_DYNAMIC_POSITION_PERCENT, max_position_percent)
    minimum = min(MIN_POSITION_PERCENT, maximum)
    target = RISK_BUDGET_PERCENT * 100 / stop_distance_percent
    return round(max(minimum, min(maximum, target)), 2)


# ---------------------------------------------------------------------------
# Exit cascade (ported from the elif chain inside R2D2PaperService._mark_and_exit)
# ---------------------------------------------------------------------------

@dataclass
class ExitDecision:
    reason: str | None
    sell_fraction: float = 1.0
    decision_state: str = "hold"


@dataclass
class PositionRiskState:
    """Mutable per-position bookkeeping the live cache also carries in ``strategy_snapshot``."""
    defense_streak: int = 0
    defense_reductions: int = 0
    stop_breach_count: int = 0
    profit_harvest_count: int = 0
    gain_protection_streak: int = 0


def exit_decision(
    *, technical: dict[str, Any], quote_price: float, average_cost: float,
    high_water: float, held_minutes: float, day_change: float, market_change: float,
    state: PositionRiskState, weekly_conviction_state: dict[str, Any],
    stop_price: float, max_position_loss_percent: float = DEFAULT_MAX_POSITION_LOSS_PERCENT,
    soft_loss_exit_percent: float = DEFAULT_SOFT_LOSS_EXIT_PERCENT,
    profit_lock_floor_percent: float = PROFIT_LOCK_FLOOR_PERCENT,
    profit_pullback_percent: float = PROFIT_PULLBACK_PERCENT,
    seconds_to_close: float | None = None,
    exit_slippage_rate: float = US_EXIT_SLIPPAGE_RATE,
    exit_fee_rate: float = US_EXIT_FEE_RATE,
) -> tuple[ExitDecision, PositionRiskState]:
    """Faithful port of the elif cascade in ``_mark_and_exit``.

    Mutates and returns a NEW ``PositionRiskState`` (streak/reduction/harvest
    counters) so callers can persist it for the next bar, mirroring how the
    live code stores these counters in ``strategy_snapshot``.
    """
    atr = max(_float(technical.get("atr")), quote_price * 0.004)
    # Chandelier-style trailing exit (backtested 2026-08-20 as "Candidato E"
    # against real 5-min bars, 40 NASDAQ/NYSE names, 06-19/08): 2.5x ATR off
    # the peak moved the win/loss payoff ratio from ~1.34x to ~1.58-1.63x and
    # cut max drawdown by roughly a third versus the previous tight
    # 0.45%-0.9%-of-price trailing band, which was locking in winners before
    # they could run.
    trailing_distance = atr * 2.5
    trailing = high_water - trailing_distance
    stop = max(stop_price, trailing)
    # mark_pnl_pct is a price-structure mark. It is NOT realizable P&L because
    # the exit fill slippage and sale fee have not happened yet. Profit rules
    # must use estimated_net_exit_pnl_pct so a friction-covered breakeven is
    # never described or treated as profit (CSTM, 2026-08-21).
    mark_pnl_pct = (quote_price / average_cost - 1) * 100
    estimated_net_exit_pnl_pct = estimated_net_exit_pnl_percent(
        quote_price, average_cost,
        slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
    )
    mark_peak_pnl_pct = (high_water / average_cost - 1) * 100
    estimated_net_peak_pnl_pct = estimated_net_exit_pnl_percent(
        high_water, average_cost,
        slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
    )
    atr_percent = max(0.0, _float(technical.get("atr_percent")))
    # A flat max_position_loss_percent gets run over by normal noise on a
    # volatile name (root-caused 2026-08-20: SOC's ATR alone was 1.6%, so a
    # fixed 0.65% stop sat inside 41% of one ATR and fired on ordinary chop,
    # not a real breakdown). Backtested 2x ATR (Turtle Trading's initial-stop
    # convention) outperformed 0.5x/1.0x/1.5x on profit factor, failed-entry
    # rate and max drawdown across all four multipliers tested, so that's now
    # the floor rather than half an ATR, still capped so the hard stop never
    # stops being meaningfully hard.
    effective_max_loss_percent = max(max_position_loss_percent, min(1.5, atr_percent * 2.0))
    hard_stop = hard_stop_quote_price(
        average_cost, effective_max_loss_percent,
        slippage_rate=exit_slippage_rate, fee_rate=exit_fee_rate,
    )
    stop = max(stop, hard_stop)
    soft_loss_threshold = max(soft_loss_exit_percent, min(0.7, atr_percent * 0.4))
    # 1R floor (root-caused 2026-08-20 against real fills: tactical harvests
    # averaged +$290 and early-gain-protection +$55 against a hard stop
    # averaging -$477 the same day): every profit-harvest rule below used to
    # gate on the same flat PROFIT_TRIGGER_PERCENT regardless of how wide this
    # position's own ATR-derived stop is. On a volatile name the stop can
    # reach 1.5%, while profit was still realized at 0.65% -- more than 2x
    # smaller than the loss the position was exposed to. The trigger now
    # never sits below the stop distance itself (1R), so a name wide enough
    # to need a 1.5% stop also needs a 1.5%+ gain before any harvest rule
    # locks it in.
    profit_trigger_percent = max(PROFIT_TRIGGER_PERCENT, effective_max_loss_percent)
    if estimated_net_peak_pnl_pct >= 8.0:
        stop = max(stop, average_cost * 1.04, high_water - max(atr * 1.5, high_water * 0.0175))
    elif estimated_net_peak_pnl_pct >= 4.0:
        stop = max(stop, average_cost * 1.015, high_water - max(atr * 2.0, high_water * 0.0225))
    elif estimated_net_peak_pnl_pct >= 1.0:
        stop = max(stop, average_cost * 1.003)

    bearish_votes = sum((
        quote_price < _float(technical.get("vwap"), quote_price),
        quote_price < _float(technical.get("ema8"), quote_price),
        _float(technical.get("ema8")) < _float(technical.get("ema20")),
        _float(technical.get("macd_histogram")) < 0 and _float(technical.get("macd_acceleration")) < 0,
        _float(technical.get("momentum30")) < -0.35,
        str(technical.get("price_structure")) == "breakdown",
    ))
    failed_entry_votes = sum((
        quote_price < _float(technical.get("vwap"), quote_price),
        quote_price < _float(technical.get("ema8"), quote_price),
        _float(technical.get("momentum15")) < 0,
        _float(technical.get("momentum30")) < 0,
        _float(technical.get("macd_histogram")) < 0 and _float(technical.get("macd_acceleration")) <= 0,
    ))
    defense = technical_defense(
        technical=technical, price=quote_price, day_change=day_change, market_change=market_change,
    )
    defense_streak = (
        state.defense_streak + 1
        if defense["actionable"] and defense["score"] >= 45
        else max(0, state.defense_streak - 1)
    )
    stop_breaches = state.stop_breach_count + 1 if quote_price <= stop else 0
    # 2-review persistence for the early-gain-protection rule (root-caused
    # 2026-08-20: once the 1R profit floor raised every OTHER harvest rule's
    # bar, exits are water and find the lowest open gate -- a winner pulling
    # back would just route through this rule instead at its unchanged 0.30%
    # floor, largely defeating the 1R floor's point). Mirrors defense_streak's
    # pattern exactly: requires the same read to hold for two consecutive
    # reviews before it fires, instead of on the first occurrence.
    gain_protection_streak = (
        state.gain_protection_streak + 1
        if estimated_net_exit_pnl_pct >= GAIN_PROTECTION_MIN_PERCENT and failed_entry_votes >= 3
        else max(0, state.gain_protection_streak - 1)
    )
    technical_score = _float(technical.get("score"))
    profit_lock_level = max(
        profit_lock_floor_percent,
        estimated_net_peak_pnl_pct - profit_pullback_percent,
    )
    pnl_audit = (
        f"mark {mark_pnl_pct:+.2f}%, estimated net {estimated_net_exit_pnl_pct:+.2f}%"
    )
    peak_audit = (
        f"mark peak {mark_peak_pnl_pct:+.2f}%, estimated net peak {estimated_net_peak_pnl_pct:+.2f}%"
    )

    reason: str | None = None
    sell_fraction = 1.0
    decision_state = "hold"
    profit_harvest_count = state.profit_harvest_count
    defense_reductions = state.defense_reductions

    if estimated_net_exit_pnl_pct <= -effective_max_loss_percent:
        reason = f"Immediate hard stop at {pnl_audit}; max realized position-loss policy is {effective_max_loss_percent:.2f}% (base {max_position_loss_percent:.2f}%, ATR-adjusted)."
    elif (
        seconds_to_close is not None
        and 0 <= seconds_to_close <= END_OF_DAY_PROFIT_EXIT_LEAD_SECONDS
        and estimated_net_exit_pnl_pct > 0
    ):
        # Exactly T-30s through the official close, every profitable position
        # is realized. Weekly conviction is intentionally not exempt: this is
        # a portfolio-wide close policy, not a tactical-conviction decision.
        # Losing positions continue through the regular exit cascade and are
        # carried overnight only if no stop/defense rule fires by 16:00 ET.
        reason = (
            f"End-of-day profit liquidation at {pnl_audit} with "
            f"{seconds_to_close:.0f} seconds to the official close: all positive positions, "
            "including weekly-conviction holdings, are realized before overnight risk."
        )
    elif held_minutes >= FAILED_ENTRY_MINUTES and estimated_net_exit_pnl_pct <= -FAILED_ENTRY_LOSS_PERCENT and failed_entry_votes >= 3:
        reason = f"Failed-entry fast exit at {pnl_audit} after {held_minutes:.1f} minutes: {failed_entry_votes}/5 live timing signals invalidated the setup."
    elif defense["critical"]:
        reason = f"Critical technical-defense exit at {pnl_audit}: {'; '.join(defense['drivers'][:4])}. Defense score {defense['score']:.0f}/100."
    elif held_minutes >= MIN_HOLD_MINUTES and defense["actionable"] and defense["score"] >= 72 and defense_streak >= 2:
        reason = f"Confirmed technical-defense exit at {pnl_audit} after {defense_streak} reviews: {'; '.join(defense['drivers'][:4])}. Defense score {defense['score']:.0f}/100."
    elif held_minutes >= MIN_HOLD_MINUTES and defense_reductions >= 1 and defense["actionable"] and defense["score"] >= 58 and defense_streak >= 3:
        reason = f"Technical deterioration persisted after risk reduction at {pnl_audit}: {'; '.join(defense['drivers'][:4])}. Remaining position exited."
    elif estimated_net_exit_pnl_pct <= -soft_loss_threshold and defense["actionable"] and defense["score"] >= 45 and defense_streak >= 2:
        reason = f"Defensive loss exit at {pnl_audit} on a live quote; dynamic net defense was {soft_loss_threshold:.2f}% and the multicriteria defense score reached {defense['score']:.0f}/100."
    elif quote_price <= stop and defense["actionable"] and defense["score"] >= 45 and stop_breaches >= 2:
        reason = f"Adaptive intraday stop executed at {stop:.2f} after two live confirmations ({pnl_audit}); defense score {defense['score']:.0f}/100."
    elif held_minutes >= MIN_HOLD_MINUTES and weekly_conviction_state["active"] and profit_harvest_count == 0 and estimated_net_peak_pnl_pct >= profit_trigger_percent and profit_lock_floor_percent <= estimated_net_exit_pnl_pct <= profit_lock_level:
        reason = f"Weekly-conviction profit locked at {pnl_audit} after a pullback from the {peak_audit} before the first harvest; the position was released for same-cycle replacement."
    elif held_minutes >= MIN_HOLD_MINUTES and weekly_conviction_state["active"] and profit_harvest_count == 0 and estimated_net_exit_pnl_pct >= profit_trigger_percent:
        sell_fraction = WEEKLY_PROFIT_HARVEST_FRACTION
        profit_harvest_count = 1
        reason = f"Weekly-conviction profit layer harvested at {pnl_audit}: {WEEKLY_PROFIT_HARVEST_FRACTION * 100:.0f}% of the position was realized and the remainder stays under the live profit lock."
    elif held_minutes >= MIN_HOLD_MINUTES and weekly_conviction_state["active"] and profit_harvest_count >= 1 and estimated_net_peak_pnl_pct >= profit_trigger_percent and profit_lock_floor_percent <= estimated_net_exit_pnl_pct <= profit_lock_level:
        reason = f"Weekly-conviction remainder locked at {pnl_audit} after a pullback from the {peak_audit}; the protected balance was released for replacement."
    elif held_minutes >= MIN_HOLD_MINUTES and not weekly_conviction_state["active"] and estimated_net_exit_pnl_pct >= profit_trigger_percent:
        reason = f"Tactical profit harvested at {pnl_audit} after reaching the {profit_trigger_percent:.2f}% net execution trigger (1R); capital released for same-cycle replacement."
    elif held_minutes >= MIN_HOLD_MINUTES and not weekly_conviction_state["active"] and estimated_net_peak_pnl_pct >= profit_trigger_percent and profit_lock_floor_percent <= estimated_net_exit_pnl_pct <= profit_lock_level:
        reason = f"Armed profit locked at {pnl_audit} after a pullback from the {peak_audit}; capital released for same-cycle replacement."
    elif held_minutes >= MIN_HOLD_MINUTES and estimated_net_exit_pnl_pct >= 0.75 and bearish_votes >= 1 and technical_score < 60:
        reason = f"Early tactical profit harvested at {pnl_audit} as live momentum weakened; technical score {technical_score:.0f}/100."
    elif held_minutes >= MIN_HOLD_MINUTES and estimated_net_exit_pnl_pct >= 2.5 and bearish_votes >= 3:
        reason = f"Profit harvested at {pnl_audit} after a {bearish_votes}-signal momentum reversal."
    elif held_minutes >= MIN_HOLD_MINUTES and estimated_net_exit_pnl_pct >= 1.0 and bearish_votes >= 2 and technical_score < 55:
        reason = f"Early profit harvested at {pnl_audit} after momentum weakened across {bearish_votes} signals; technical score {technical_score:.0f}/100."
    elif estimated_net_exit_pnl_pct >= GAIN_PROTECTION_MIN_PERCENT and failed_entry_votes >= 3 and gain_protection_streak >= 2:
        # Mirrors the failed-entry fast exit's vote-based read on the winning
        # side, deliberately with no held_minutes gate: a small unrealized gain
        # can round-trip into a loss faster than any fixed time window would
        # react, and every other profit rule above requires >=0.75% before it
        # offers any protection at all. Below that, a positive position had none.
        # 2-review persistence added 2026-08-20 alongside the 1R profit floor,
        # so this fast rule can't become the path of least resistance around it.
        reason = f"Early gain protection at {pnl_audit} after {gain_protection_streak} reviews: {failed_entry_votes}/5 live timing signals reversed before the position could round-trip into a loss."
    elif held_minutes >= MIN_HOLD_MINUTES and technical_score < 32 and bearish_votes >= 4:
        reason = f"Trend breakdown confirmed at {pnl_audit} by {bearish_votes} signals; technical score {technical_score:.0f}/100."
    elif held_minutes >= MIN_HOLD_MINUTES and estimated_net_exit_pnl_pct < profit_trigger_percent and defense_reductions == 0 and defense["actionable"] and defense["score"] >= 55 and defense_streak >= 2:
        sell_fraction = 0.5
        defense_reductions = 1
        reason = f"Progressive technical-defense reduction: 50% of the position released at {pnl_audit} after {defense_streak} reviews; {'; '.join(defense['drivers'][:3])}."
    elif held_minutes >= 180 and estimated_net_exit_pnl_pct < 0.5 and technical_score < 45:
        reason = f"Stagnation exit after {held_minutes / 60:.1f}h; {pnl_audit} and technical score {technical_score:.0f}/100."
    elif quote_price <= stop:
        decision_state = "stop armed"
    elif defense["severity"] == "reduce":
        decision_state = "defense reduction armed"
    elif defense["severity"] == "watch":
        decision_state = "technical defense watch"
    elif weekly_conviction_state["active"]:
        decision_state = "weekly conviction hold"
    elif estimated_net_peak_pnl_pct >= 4.0:
        decision_state = "profit protected"
    elif estimated_net_peak_pnl_pct >= 1.0:
        decision_state = "profit armed"
    elif technical_score < 45:
        decision_state = "trend under review"

    new_state = PositionRiskState(
        defense_streak=defense_streak, defense_reductions=defense_reductions,
        stop_breach_count=stop_breaches, profit_harvest_count=profit_harvest_count,
        gain_protection_streak=gain_protection_streak,
    )
    return ExitDecision(reason=reason, sell_fraction=sell_fraction, decision_state="exit" if reason else decision_state), new_state
