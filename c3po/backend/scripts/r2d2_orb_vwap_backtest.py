"""Research-only replay for alternative R2D2 entry theses.

This script is intentionally disconnected from the production worker.  It
compares the current tactical/intraday routes with two pure entry functions:

* F: 15-minute opening-range breakout with an extension guard.
* G: a VWAP pullback/reclaim inside an established bullish regime.

Run inside the API container so it can use the configured EODHD token and the
historical fundamental snapshots already stored in Postgres.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app import backtest
from app.config import get_settings
from app.database import Database
from app.market_data.service import MarketDataService

SYMBOLS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA",
    "JPM", "V", "MA", "BAC", "WMT", "COST", "HD", "KO", "PEP", "MCD",
    "XOM", "CVX", "COP", "LLY", "UNH", "ABBV", "MRK", "JNJ", "CAT",
    "GE", "RTX", "BA", "ORCL", "CRM", "AMD", "QCOM", "NFLX", "CSCO",
    "IBM", "DIS", "NKE", "INTC",
)
CACHE_DIR = Path("/tmp/r2d2_orb_vwap_cache")
UTC = timezone.utc
SESSION_OPEN = time(13, 30)  # 09:30 New York during EDT
OR_END = time(13, 45)
ENTRY_CUTOFF = time(15, 30)  # first two hours
SESSION_CLOSE = time(20, 0)
FEE_BPS = 4.0
SLIPPAGE_BPS = 10.0
ROUND_TRIP_COST_PERCENT = 2 * (FEE_BPS + SLIPPAGE_BPS) / 100
EDGE_BUFFER_PERCENT = 0.10
TARGET_R = 1.5


@dataclass(frozen=True)
class EntrySignal:
    entry: float
    stop: float
    timestamp: datetime
    route: str
    modeled_edge_percent: float


@dataclass(frozen=True)
class Outcome:
    symbol: str
    session: date
    route: str
    entry_at: datetime
    exit_at: datetime
    r_multiple: float
    pnl_percent: float
    held_minutes: float
    reason: str


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _vwap(bars: Iterable[dict[str, Any]]) -> float:
    numerator = 0.0
    denominator = 0.0
    for bar in bars:
        volume = _float(bar.get("volume"))
        typical = (_float(bar.get("high")) + _float(bar.get("low")) + _float(bar.get("close"))) / 3
        numerator += typical * volume
        denominator += volume
    return numerator / denominator if denominator else 0.0


def _atr(bars: list[dict[str, Any]], length: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    ranges: list[float] = []
    for previous, current in zip(bars, bars[1:]):
        prev_close = _float(previous.get("close"))
        ranges.append(max(
            _float(current.get("high")) - _float(current.get("low")),
            abs(_float(current.get("high")) - prev_close),
            abs(_float(current.get("low")) - prev_close),
        ))
    return statistics.fmean(ranges[-length:]) if ranges else 0.0


def _ema(values: list[float], length: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (length + 1.0)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def _rsi(values: list[float], length: int = 14) -> float:
    if len(values) <= length:
        return 50.0
    changes = [b - a for a, b in zip(values, values[1:])][-length:]
    gains = sum(max(change, 0.0) for change in changes) / length
    losses = sum(max(-change, 0.0) for change in changes) / length
    if losses == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def candidate_f_signal(
    session_bars: list[dict[str, Any]], index: int, *, extension_atr: float = 0.5,
) -> EntrySignal | None:
    """Return the first valid ORB signal at ``index``, otherwise ``None``.

    The function has no I/O or mutable state, making the extension rule easy
    to unit-test and later suitable for shadow-mode without production wiring.
    """
    current = session_bars[index]
    at = current["timestamp"]
    if not (OR_END <= at.time() <= ENTRY_CUTOFF):
        return None
    opening = [bar for bar in session_bars if SESSION_OPEN <= bar["timestamp"].time() < OR_END]
    if len(opening) < 10:
        return None
    or_high = max(_float(bar["high"]) for bar in opening)
    or_low = min(_float(bar["low"]) for bar in opening)
    or_range = or_high - or_low
    previous = session_bars[index - 1] if index else current
    price = _float(current["close"])
    session_vwap = _vwap(session_bars[: index + 1])
    first_cross = _float(previous["close"]) <= or_high < price
    not_extended = price <= or_high + extension_atr * or_range
    if not (first_cross and price > session_vwap and not_extended):
        return None
    stop = max(or_low, session_vwap)
    if stop <= 0 or stop >= price:
        return None
    modeled_edge = TARGET_R * (price - stop) / price * 100
    if modeled_edge < ROUND_TRIP_COST_PERCENT + EDGE_BUFFER_PERCENT:
        return None
    return EntrySignal(price, stop, at, "F_ORB_VWAP", modeled_edge)


def candidate_g_signal(session_bars: list[dict[str, Any]], index: int) -> EntrySignal | None:
    """VWAP pullback/reclaim after a bullish 5-minute regime is established."""
    if index < 35:
        return None
    current = session_bars[index]
    at = current["timestamp"]
    if not (OR_END <= at.time() <= ENTRY_CUTOFF):
        return None
    closes = [_float(bar["close"]) for bar in session_bars[: index + 1]]
    price = closes[-1]
    session_vwap = _vwap(session_bars[: index + 1])
    previous = session_bars[index - 1]
    rsi = _rsi(closes)
    bullish_regime = _ema(closes, 8) > _ema(closes, 20)
    touched_zone = abs(_float(previous["close"]) / session_vwap - 1.0) <= 0.003
    reclaimed = price > session_vwap and price > _float(previous["high"])
    if not (bullish_regime and touched_zone and reclaimed and 40.0 <= rsi <= 55.0):
        return None
    stop = min(_float(previous["low"]), session_vwap * 0.997)
    if stop <= 0 or stop >= price:
        return None
    modeled_edge = TARGET_R * (price - stop) / price * 100
    if modeled_edge < ROUND_TRIP_COST_PERCENT + EDGE_BUFFER_PERCENT:
        return None
    return EntrySignal(price, stop, at, "G_VWAP_PULLBACK", modeled_edge)


def _simulate_signal(
    symbol: str, session: date, bars: list[dict[str, Any]], signal: EntrySignal,
    *, target_r: float = TARGET_R,
) -> Outcome:
    slip = SLIPPAGE_BPS / 10_000
    fee = FEE_BPS / 10_000
    entry = signal.entry * (1.0 + slip)
    risk = entry - signal.stop
    target = entry + target_r * risk
    entry_index = next(i for i, bar in enumerate(bars) if bar["timestamp"] == signal.timestamp)
    exit_price = _float(bars[-1]["close"])
    exit_at = bars[-1]["timestamp"]
    reason = "session_close"
    for bar in bars[entry_index + 1:]:
        # Stop-first is deliberately conservative when both levels occur in one minute.
        if _float(bar["low"]) <= signal.stop:
            exit_price, exit_at, reason = signal.stop, bar["timestamp"], "natural_stop"
            break
        if _float(bar["high"]) >= target:
            exit_price, exit_at, reason = target, bar["timestamp"], f"target_{target_r:.1f}R"
            break
    exit_fill = exit_price * (1.0 - slip)
    net = exit_fill * (1.0 - fee) - entry * (1.0 + fee)
    return Outcome(
        symbol=symbol, session=session, route=signal.route, entry_at=signal.timestamp,
        exit_at=exit_at, r_multiple=net / risk, pnl_percent=net / entry * 100,
        held_minutes=(exit_at - signal.timestamp).total_seconds() / 60, reason=reason,
    )


def replay_candidate(
    bars_by_symbol: dict[str, list[dict[str, Any]]], route: str,
) -> list[Outcome]:
    outcomes: list[Outcome] = []
    decision = candidate_f_signal if route == "F" else candidate_g_signal
    for symbol, all_bars in bars_by_symbol.items():
        by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for bar in all_bars:
            if SESSION_OPEN <= bar["timestamp"].time() <= SESSION_CLOSE:
                by_day[bar["timestamp"].date()].append(bar)
        for session, bars in sorted(by_day.items()):
            bars.sort(key=lambda bar: bar["timestamp"])
            for index in range(1, len(bars)):
                signal = decision(bars, index)
                if signal:
                    outcomes.append(_simulate_signal(symbol, session, bars, signal))
                    break  # one clean, first-trigger trade per symbol/session
    return outcomes


def _aggregate_five_minute(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for bar in bars:
        ts = bar["timestamp"]
        bucket = ts.replace(minute=ts.minute - ts.minute % 5, second=0, microsecond=0)
        buckets[bucket].append(bar)
    result = []
    for timestamp, rows in sorted(buckets.items()):
        result.append({
            "timestamp": timestamp, "open": _float(rows[0]["open"]),
            "high": max(_float(row["high"]) for row in rows),
            "low": min(_float(row["low"]) for row in rows),
            "close": _float(rows[-1]["close"]),
            "volume": sum(_float(row["volume"]) for row in rows),
        })
    return result


def _summary(outcomes: list[Outcome]) -> dict[str, Any]:
    wins = [o for o in outcomes if o.r_multiple > 0]
    losses = [o for o in outcomes if o.r_multiple < 0]
    gross_profit = sum(o.r_multiple for o in wins)
    gross_loss = abs(sum(o.r_multiple for o in losses))
    avg_win = statistics.fmean(o.r_multiple for o in wins) if wins else 0.0
    avg_loss = abs(statistics.fmean(o.r_multiple for o in losses)) if losses else 0.0
    return {
        "trades": len(outcomes),
        "win_rate_percent": round(100 * len(wins) / len(outcomes), 2) if outcomes else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else 0.0,
        "expectancy_r": round(statistics.fmean(o.r_multiple for o in outcomes), 4) if outcomes else 0.0,
        "payoff_ratio": round(avg_win / avg_loss, 3) if avg_loss else 0.0,
        "avg_win_r": round(avg_win, 3), "avg_loss_r": round(avg_loss, 3),
        "avg_pnl_percent": round(statistics.fmean(o.pnl_percent for o in outcomes), 4) if outcomes else 0.0,
        "failed_under_10m": sum(o.held_minutes < 10 and o.r_multiple < 0 for o in outcomes),
    }


def _baseline_summary(report: backtest.BacktestReport) -> dict[str, Any]:
    buys: dict[str, list[Any]] = defaultdict(list)
    multiples: list[float] = []
    for trade in sorted(report.trades, key=lambda trade: trade.timestamp):
        if trade.side == "BUY":
            buys[trade.symbol].append(trade)
        elif buys[trade.symbol] and trade.realized_pnl_usd is not None:
            buy = buys[trade.symbol].pop(0)
            capital = buy.price * buy.quantity
            multiples.append(trade.realized_pnl_usd / capital * 100 if capital else 0.0)
    wins = [value for value in multiples if value > 0]
    losses = [value for value in multiples if value < 0]
    gp, gl = sum(wins), abs(sum(losses))
    return {
        **report.summary(), "expectancy_percent_per_exit": round(statistics.fmean(multiples), 4) if multiples else 0.0,
        "payoff_ratio": round(statistics.fmean(wins) / abs(statistics.fmean(losses)), 3) if wins and losses else 0.0,
        "profit_factor_recomputed": round(gp / gl, 3) if gl else 0.0,
    }


def _fetch_day(market_data: MarketDataService, symbol: str, session: date) -> list[dict[str, Any]]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{symbol}-{session.isoformat()}.json"
    if path.exists():
        payload = json.loads(path.read_text())
    else:
        settings = get_settings()
        start = int(datetime.combine(session, time(13, 0), UTC).timestamp())
        end = int(datetime.combine(session, time(21, 0), UTC).timestamp())
        payload = market_data.http.get_json(
            f"{settings.eodhd_base_url.rstrip('/')}/api/intraday/{symbol}.US",
            params={"api_token": settings.eodhd_api_token, "fmt": "json", "interval": "1m", "from": start, "to": end},
        )
        path.write_text(json.dumps(payload))
    result = []
    for row in payload if isinstance(payload, list) else []:
        timestamp = datetime.fromtimestamp(int(row["timestamp"]), UTC) if row.get("timestamp") else datetime.fromisoformat(row["datetime"]).replace(tzinfo=UTC)
        result.append({
            "timestamp": timestamp, "open": _float(row.get("open")), "high": _float(row.get("high")),
            "low": _float(row.get("low")), "close": _float(row.get("close")), "volume": _float(row.get("volume")),
        })
    return sorted(result, key=lambda bar: bar["timestamp"])


def main() -> None:
    settings = get_settings()
    database = Database(settings)
    market_data = MarketDataService(settings, database)
    sessions = [date(2026, 8, 6) + timedelta(days=offset) for offset in range(15)]
    sessions = [session for session in sessions if session.weekday() < 5 and session <= date(2026, 8, 20)]
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    coverage: dict[str, int] = {}
    for position, symbol in enumerate(SYMBOLS, 1):
        bars = [bar for session in sessions for bar in _fetch_day(market_data, symbol, session)]
        complete_days = {bar["timestamp"].date() for bar in bars if SESSION_OPEN <= bar["timestamp"].time() <= SESSION_CLOSE}
        if len(complete_days) >= 6:
            bars_by_symbol[symbol] = bars
            coverage[symbol] = len(complete_days)
        print(f"DATA {position:02d}/{len(SYMBOLS)} {symbol}: {len(bars)} bars, {len(complete_days)} sessions", flush=True)

    five_minute = {symbol: _aggregate_five_minute(bars) for symbol, bars in bars_by_symbol.items()}
    baseline = backtest.run_backtest(
        five_minute, starting_capital=1_000_000, max_positions=20,
        fees_bps=FEE_BPS, slippage_bps=SLIPPAGE_BPS,
    )
    f_outcomes = replay_candidate(bars_by_symbol, "F")
    g_outcomes = replay_candidate(bars_by_symbol, "G")
    result = {
        "dataset": {
            "requested_symbols": len(SYMBOLS), "usable_symbols": len(bars_by_symbol),
            "sessions": [session.isoformat() for session in sessions], "coverage": coverage,
            "one_minute_bars": sum(len(rows) for rows in bars_by_symbol.values()),
            "fees_bps_each_side": FEE_BPS, "slippage_bps_each_side": SLIPPAGE_BPS,
            "round_trip_cost_percent": ROUND_TRIP_COST_PERCENT,
            "minimum_modeled_edge_percent": ROUND_TRIP_COST_PERCENT + EDGE_BUFFER_PERCENT,
        },
        "baseline_current_routes": _baseline_summary(baseline),
        "candidate_f": _summary(f_outcomes),
        "candidate_g": _summary(g_outcomes),
    }
    print("RESULT_JSON")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
