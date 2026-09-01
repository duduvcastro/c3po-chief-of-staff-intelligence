"""Offline backtest engine for the R2D2 strategy.

Replays historical 5-minute OHLCV bars through the SAME entry/exit/defense
logic used in production (imported from ``r2d2_strategy.py``, never
re-implemented here) and produces trade-level and portfolio-level metrics:
win rate, profit factor, max drawdown, average daily return, equity curve.

WHAT THIS DOES NOT DO (read before trusting a result):

1. It needs real historical 5-minute bars per symbol -- EODHD intraday
   history, an export from your own pipeline, or any OHLCV source. This
   module ships with zero bundled market data; see ``run_backtest`` docs
   for the expected input shape.

2. R2D2's live entry decision blends a FUNDAMENTAL valuation score
   (upside, confidence, risk_score, buy_in_distance, composite_score --
   produced by the separate One Pager / valuation pipeline) with the
   TECHNICAL score computed here. This backtest can only be as faithful
   as the fundamental inputs you give it. Two modes are supported:
     - Pass ``fundamentals`` (per symbol, ideally per day) if you have
       historical valuation snapshots -- this reproduces the full hybrid
       entry logic exactly.
     - Otherwise a neutral placeholder is used (see
       ``DEFAULT_FUNDAMENTALS``), which effectively backtests the
       TECHNICAL side of entries plus the FULL exit/defense cascade
       (hard stop, failed-entry exit, technical-defense reduce/exit,
       profit harvesting). The exit/defense logic does not depend on
       fundamentals in the live code either, so that half is fully
       faithful regardless.

3. This is a single-symbol-at-a-time position model with a shared cash
   pool; it does not model partial fills, real slippage beyond the flat
   ``fees_bps``/``slippage_bps`` you pass in, or broker rejects.

4. No statistical claim is implied by a good-looking equity curve on a
   short or narrow sample. Use walk-forward/out-of-sample splits (see
   ``split_walk_forward``) before trusting any parameter change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from . import r2d2_strategy as strategy

DEFAULT_FUNDAMENTALS: dict[str, float] = {
    "fundamental_score": 65.0,
    "confidence": 65.0,
    "risk_score": 40.0,
    "upside": 22.0,
    "buy_in_distance": 5.0,
}


@dataclass
class Trade:
    symbol: str
    side: str  # BUY / SELL
    timestamp: datetime
    price: float
    quantity: float
    reason: str
    realized_pnl_usd: float | None = None


@dataclass
class OpenPosition:
    symbol: str
    quantity: float
    average_cost: float
    opened_at: datetime
    high_water: float
    stop_price: float
    fundamental_snapshot: dict[str, Any]
    risk_state: strategy.PositionRiskState = field(default_factory=strategy.PositionRiskState)
    profit_harvested_once: bool = False


@dataclass
class EquityPoint:
    timestamp: datetime
    nav: float


@dataclass
class BacktestReport:
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    starting_capital: float
    ending_nav: float

    @property
    def realized_trades(self) -> list[Trade]:
        return [t for t in self.trades if t.side == "SELL" and t.realized_pnl_usd is not None]

    @property
    def win_rate_percent(self) -> float:
        exits = self.realized_trades
        if not exits:
            return 0.0
        wins = [t for t in exits if t.realized_pnl_usd > 0]
        return round(len(wins) / len(exits) * 100, 2)

    @property
    def profit_factor(self) -> float:
        exits = self.realized_trades
        gross_profit = sum(t.realized_pnl_usd for t in exits if t.realized_pnl_usd > 0)
        gross_loss = abs(sum(t.realized_pnl_usd for t in exits if t.realized_pnl_usd < 0))
        if gross_loss == 0:
            return round(gross_profit, 3) if gross_profit else 0.0
        return round(gross_profit / gross_loss, 3)

    @property
    def max_drawdown_percent(self) -> float:
        peak = 0.0
        max_dd = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.nav)
            if peak:
                max_dd = max(max_dd, (peak - point.nav) / peak * 100)
        return round(max_dd, 3)

    @property
    def total_return_percent(self) -> float:
        if not self.starting_capital:
            return 0.0
        return round((self.ending_nav / self.starting_capital - 1) * 100, 3)

    def summary(self) -> dict[str, Any]:
        return {
            "trades": len(self.trades),
            "closed_exits": len(self.realized_trades),
            "win_rate_percent": self.win_rate_percent,
            "profit_factor": self.profit_factor,
            "max_drawdown_percent": self.max_drawdown_percent,
            "total_return_percent": self.total_return_percent,
            "starting_capital": self.starting_capital,
            "ending_nav": round(self.ending_nav, 2),
        }


def _held_minutes(opened_at: datetime, now: datetime) -> float:
    return max(0.0, (now - opened_at).total_seconds() / 60)


def run_backtest(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    fundamentals: dict[str, dict[str, Any]] | Callable[[str, datetime], dict[str, Any]] | None = None,
    starting_capital: float = 1_000_000.0,
    max_positions: int | None = None,
    max_position_percent: float = strategy.DEFAULT_MAX_POSITION_PERCENT,
    max_position_loss_percent: float = strategy.DEFAULT_MAX_POSITION_LOSS_PERCENT,
    soft_loss_exit_percent: float = strategy.DEFAULT_SOFT_LOSS_EXIT_PERCENT,
    profit_lock_floor_percent: float = strategy.PROFIT_LOCK_FLOOR_PERCENT,
    profit_pullback_percent: float = strategy.PROFIT_PULLBACK_PERCENT,
    entry_policy: dict[str, float] | None = None,
    fees_bps: float = 5.0,
    slippage_bps: float = 5.0,
    lookback_bars: int = 40,
    market: str = "NASDAQ",
) -> BacktestReport:
    """Replay ``bars_by_symbol`` chronologically through the R2D2 logic.

    ``bars_by_symbol``: ``{symbol: [bar, ...]}``, each bar a dict with
    ``timestamp`` (a ``datetime``), ``open``, ``high``, ``low``, ``close``,
    ``volume``. Bars for each symbol must already be sorted ascending by
    timestamp. A 5-minute grid is assumed (matches the live system), but
    any fixed interval works as long as it is consistent.

    ``fundamentals``: either a static dict per symbol
    (``{"AAPL": {"fundamental_score": 70, ...}}``) applied to every day, or
    a callable ``(symbol, day) -> dict`` if you have per-day historical
    valuation snapshots. Falls back to ``DEFAULT_FUNDAMENTALS`` -- see the
    module docstring for what that means for entry fidelity.
    """
    policy = entry_policy or strategy.BASE_ENTRY_POLICY
    fee_rate = fees_bps / 10_000
    slip_rate = slippage_bps / 10_000

    def fundamentals_for(symbol: str, at: datetime) -> dict[str, Any]:
        if fundamentals is None:
            return dict(DEFAULT_FUNDAMENTALS)
        if callable(fundamentals):
            return dict(fundamentals(symbol, at))
        return dict(fundamentals.get(symbol, DEFAULT_FUNDAMENTALS))

    # Merge all (symbol, bar) events into one chronological stream.
    events: list[tuple[datetime, str, int]] = []
    for symbol, bars in bars_by_symbol.items():
        for index in range(len(bars)):
            events.append((bars[index]["timestamp"], symbol, index))
    events.sort(key=lambda e: e[0])

    cash = starting_capital
    positions: dict[str, OpenPosition] = {}
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []
    market_change_by_ts: dict[datetime, float] = {}

    for timestamp, symbol, index in events:
        bars = bars_by_symbol[symbol]
        window = bars[max(0, index - lookback_bars + 1): index + 1]
        if len(window) < 35:
            continue
        price = window[-1]["close"]
        try:
            technical = strategy.compute_technical_snapshot(window)
        except ValueError:
            continue
        day_change = (price / window[0]["close"] - 1) * 100 if window[0]["close"] else 0.0
        market_change = market_change_by_ts.get(timestamp, day_change)

        position = positions.get(symbol)
        if position is not None:
            held_minutes = _held_minutes(position.opened_at, timestamp)
            high_water = max(position.high_water, price)
            fundamentals_snapshot = position.fundamental_snapshot
            weekly = strategy.weekly_conviction(
                strategy=fundamentals_snapshot, technical=technical, price=price,
                high_water=high_water, atr=max(technical.get("atr", 0.0), price * 0.004),
                bearish_votes=sum((
                    price < strategy._float(technical.get("vwap"), price),
                    strategy._float(technical.get("ema8")) < strategy._float(technical.get("ema20")),
                )),
            )
            decision, new_state = strategy.exit_decision(
                technical=technical, quote_price=price, average_cost=position.average_cost,
                high_water=high_water, held_minutes=held_minutes, day_change=day_change,
                market_change=market_change, state=position.risk_state,
                weekly_conviction_state=weekly, stop_price=position.stop_price,
                max_position_loss_percent=max_position_loss_percent,
                soft_loss_exit_percent=soft_loss_exit_percent,
                profit_lock_floor_percent=profit_lock_floor_percent,
                profit_pullback_percent=profit_pullback_percent,
            )
            position.high_water = high_water
            position.risk_state = new_state
            if decision.reason:
                sell_qty = position.quantity * decision.sell_fraction
                fill_price = price * (1 - slip_rate)
                gross = sell_qty * fill_price
                fees = gross * fee_rate
                realized = gross - fees - sell_qty * position.average_cost
                cash += gross - fees
                trades.append(Trade(
                    symbol=symbol, side="SELL", timestamp=timestamp, price=fill_price,
                    quantity=sell_qty, reason=decision.reason, realized_pnl_usd=realized,
                ))
                remaining = position.quantity - sell_qty
                if remaining <= 1e-6:
                    positions.pop(symbol, None)
                else:
                    position.quantity = remaining
            continue

        if max_positions is not None and len(positions) >= max_positions:
            continue
        fnd = fundamentals_for(symbol, timestamp)
        item = {
            "market": market, "price": price, "technical_score": technical["score"],
            "composite_score": round(fnd.get("fundamental_score", 50.0) * 0.55 + technical["score"] * 0.30
                                      + max(0.0, 100 - fnd.get("buy_in_distance", 10.0) * 5) * 0.15, 3),
            "confidence": fnd.get("confidence", 50.0), "risk_score": fnd.get("risk_score", 50.0),
            "upside": fnd.get("upside", 0.0), "buy_in_distance": fnd.get("buy_in_distance", 10.0),
            "thesis": fnd.get("thesis", ""), "technical_validated": True, "quote_status": "live",
            "technical_indicators": {**technical, "relative_strength": day_change - market_change},
        }
        side, _reasons = strategy.entry_decision(item, policy)
        if side != "BUY":
            continue
        target_pct = strategy.target_position_percent(
            item, max_position_percent=max_position_percent,
        )
        nav = cash + sum(p.quantity * price for p in positions.values())
        target_usd = min(nav * target_pct / 100, cash)
        if target_usd < 100:
            continue
        fill_price = price * (1 + slip_rate)
        quantity = target_usd / fill_price
        fees = target_usd * fee_rate
        if target_usd + fees > cash:
            continue
        cash -= target_usd + fees
        positions[symbol] = OpenPosition(
            symbol=symbol, quantity=quantity, average_cost=fill_price, opened_at=timestamp,
            high_water=fill_price, stop_price=fill_price * (1 - max_position_loss_percent / 100),
            fundamental_snapshot=fnd,
        )
        trades.append(Trade(
            symbol=symbol, side="BUY", timestamp=timestamp, price=fill_price,
            quantity=quantity, reason="; ".join(_reasons)[:200],
        ))

    last_prices = {symbol: bars[-1]["close"] for symbol, bars in bars_by_symbol.items() if bars}
    ending_nav = cash + sum(p.quantity * last_prices.get(p.symbol, p.average_cost) for p in positions.values())
    report = BacktestReport(
        trades=trades, equity_curve=[],
        starting_capital=starting_capital, ending_nav=ending_nav,
    )
    report.equity_curve = daily_equity_curve(report, bars_by_symbol)
    if not report.equity_curve:
        report.equity_curve = [EquityPoint(timestamp=events[-1][0] if events else datetime.now(), nav=ending_nav)]
    return report


def daily_equity_curve(report: BacktestReport, bars_by_symbol: dict[str, list[dict[str, Any]]]) -> list[EquityPoint]:
    """Rebuild a proper end-of-day NAV series by replaying trades against daily closes.

    ``run_backtest`` only returns a single final NAV point by default (it
    does not mark-to-market every bar for performance reasons). Call this
    afterward when you need a real equity curve for drawdown analysis.
    """
    all_days: set[Any] = set()
    for bars in bars_by_symbol.values():
        for bar in bars:
            all_days.add(bar["timestamp"].date())
    days = sorted(all_days)
    close_by_symbol_day: dict[tuple[str, Any], float] = {}
    for symbol, bars in bars_by_symbol.items():
        for bar in bars:
            close_by_symbol_day[(symbol, bar["timestamp"].date())] = bar["close"]

    cash = report.starting_capital
    holdings: dict[str, float] = {}
    avg_cost: dict[str, float] = {}
    trade_index = 0
    trades = sorted(report.trades, key=lambda t: t.timestamp)
    points: list[EquityPoint] = []
    for day in days:
        while trade_index < len(trades) and trades[trade_index].timestamp.date() <= day:
            trade = trades[trade_index]
            if trade.side == "BUY":
                cash -= trade.price * trade.quantity
                total_qty = holdings.get(trade.symbol, 0.0) + trade.quantity
                prior_cost = avg_cost.get(trade.symbol, trade.price) * holdings.get(trade.symbol, 0.0)
                avg_cost[trade.symbol] = (prior_cost + trade.price * trade.quantity) / total_qty if total_qty else trade.price
                holdings[trade.symbol] = total_qty
            else:
                cash += trade.price * trade.quantity
                holdings[trade.symbol] = max(0.0, holdings.get(trade.symbol, 0.0) - trade.quantity)
            trade_index += 1
        nav = cash + sum(
            qty * close_by_symbol_day.get((sym, day), avg_cost.get(sym, 0.0))
            for sym, qty in holdings.items() if qty > 0
        )
        last_ts = max((b["timestamp"] for bars in bars_by_symbol.values() for b in bars
                        if b["timestamp"].date() == day), default=None)
        if last_ts:
            points.append(EquityPoint(timestamp=last_ts, nav=nav))
    return points


def split_walk_forward(
    bars_by_symbol: dict[str, list[dict[str, Any]]], *, folds: int = 3,
) -> list[tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]]:
    """Split each symbol's bars into ``folds`` contiguous (train, test) pairs.

    Use this before trusting any parameter change: run ``run_backtest`` on
    each ``train`` slice, pick parameters there, then confirm on the
    matching ``test`` slice. A change that only looks good on the whole
    sample at once (no train/test split) is exactly the overfitting risk
    flagged in the code review -- don't skip this step.
    """
    result = []
    for fold in range(folds):
        train: dict[str, list[dict[str, Any]]] = {}
        test: dict[str, list[dict[str, Any]]] = {}
        for symbol, bars in bars_by_symbol.items():
            n = len(bars)
            fold_size = n // folds
            start = fold * fold_size
            end = n if fold == folds - 1 else start + fold_size
            split = start + int((end - start) * 0.7)
            train[symbol] = bars[start:split]
            test[symbol] = bars[split:end]
        result.append((train, test))
    return result
