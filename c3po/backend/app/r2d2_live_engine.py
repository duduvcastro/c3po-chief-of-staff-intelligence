"""The live R2D2 inside the C3PO server, on the EODHD real-time stream (owner, 27/10/2026: "claro que tem que mudar
para dentro do servidor do C3PO, não quero nada rodando no GitHub"; "a cada segundo").

The rule in force is the one the owner chose on 26/10 (TIT-2S3): stocks that open at least 1% below the previous close,
20-session dollar volume of at least US$ 15 M, price of at least US$ 5; a buy when a MINUTE CLOSE crosses back above
the session VWAP (the measured signal), executed at once at the real ask, with a quoted spread of at most 3 bps, up to
15:29:59 ET, 20 positions of NAV/20, re-entry allowed after an exit. Every second each open position is checked at the real bid: hard stop at -0.5% net,
profit lock armed at +0.15% net trailing the peak by 0.10, every positive position sold from 15:59:30 ET; the
negatives carry to the next session. Paper only: no broker, no order. Fills, book and scan counts are the same
documents the screen already reads (``r2d2_lab_live``), written straight to the database.

Universe: the 550 most liquid US common stocks (the stream's capacity), from EODHD's end-of-day bulk files of the
last 20 sessions; the open of each is its first regular-session trade on the stream.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time as clock_time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from . import r2d2_lab_live
from .market_data.eodhd_stream import EodhdRealtimeStream

logger = logging.getLogger(__name__)

NEW_YORK = ZoneInfo("America/New_York")
CONFIG = "TIT-2S3-RT"
STATE_TYPE = "r2d2_live_engine_state"
STATE_KEY = "TIT-2S3"
STREAM_GROUP = "r2d2-live"
# The stream's capacity is per account (550 on this plan, EODHD's default is 50): the api's own stream keeps the rest
UNIVERSE_SIZE = int(os.environ.get("C3PO_R2D2_LIVE_UNIVERSE_SIZE", "500"))
ADV_DAYS = 20
MIN_ADV_DAYS = 15
FEE_SIDE = 0.00005  # 0.5 bp per side: commission and SEC/FINRA fees (the lab's cost model)
RULE = {
    "gap_min_percent": 1.0, "adv_min_usd": 15e6, "price_min": 5.0, "slots": 20, "spread_max_bps": 3.0,
    "stop_percent": 0.5, "lock_min_percent": 0.15, "pullback_percent": 0.10,
}
SESSION_OPEN = time(9, 30)
OPENING_WINDOW_END = time(9, 31)  # the candidates are fixed once every subscribed name had a chance to print
LAST_ENTRY = time(15, 29, 59)
SELL_POSITIVES_FROM = time(15, 59, 30)
SESSION_CLOSE = time(16, 0)
QUOTE_MAX_AGE_SECONDS = 5.0
MARKS_EVERY_SECONDS = 60.0


# ------------------------------------------------------------------ the stream: last trade, last NBBO, session VWAP
@dataclass
class Tape:
    """One symbol's regular session on the stream: the VWAP accumulators, the open, the last trade, and the close and
    VWAP of the last COMPLETED minute (the buy signal reads only completed minutes, Codex #500 P2-1)."""
    pv: float = 0.0
    volume: float = 0.0
    opening: float | None = None
    opening_at: float | None = None  # epoch seconds of the opening print (the earliest one, not the first to arrive)
    last_price: float | None = None
    last_at: float | None = None  # epoch seconds of the last trade (the ordering guard)
    minute: int = -1
    closed_minute: int = -1
    closed_price: float | None = None
    closed_at: float | None = None  # epoch seconds of the trade that closed the completed minute
    closed_pv: float = 0.0  # every trade up to the END of the completed minute, late ones included (Codex #500 P2-4)
    closed_volume: float = 0.0

    @property
    def vwap(self) -> float | None:
        return self.pv / self.volume if self.volume > 0 else None

    @property
    def closed_vwap(self) -> float | None:
        return self.closed_pv / self.closed_volume if self.closed_volume > 0 else None

    def add(self, price: float, size: float, minute: int, stamp: float) -> None:
        """One regular-session trade, in arrival order. In time order it moves the last price, and its minute's first trade
        closes the previous minute; a LATE trade (older than the last) counts in the VWAP and, when it belongs to an already
        completed minute, in that minute's close and VWAP — the same state the trades would have built in time order."""
        if self.opening is None or (self.opening_at is not None and stamp < self.opening_at):
            self.opening, self.opening_at = price, stamp
        late = self.last_at is not None and stamp < self.last_at
        if not late:
            if self.minute >= 0 and minute > self.minute:  # the first trade of a new minute closes the previous one
                self.closed_minute, self.closed_price, self.closed_at = self.minute, self.last_price, self.last_at
                self.closed_pv, self.closed_volume = self.pv, self.volume
            self.minute, self.last_price, self.last_at = max(self.minute, minute), price, stamp
        elif minute < self.minute:  # a late trade of a completed minute
            if size > 0:
                self.closed_pv += price * size
                self.closed_volume += size
            if (minute, stamp) >= (self.closed_minute, self.closed_at if self.closed_at is not None else float("-inf")):
                self.closed_minute, self.closed_price, self.closed_at = minute, price, stamp
        if size > 0:
            self.pv += price * size
            self.volume += size


class LiveEngineStream(EodhdRealtimeStream):
    """The EODHD stream (read-only use of the frozen module) keeping, per symbol, a ``Tape`` of the session being traded
    and the last quote with its bid and ask. Late messages never overwrite newer ones (Codex #500 P2-5): a trade older
    than the last one still counts in the VWAP but does not move the last price; an older quote is dropped."""

    def __init__(self, api_token: str, *, max_symbols: int = 550) -> None:
        super().__init__(api_token, max_symbols=max_symbols)
        self._view_lock = Lock()
        self.session: date | None = None
        self.tapes: dict[str, Tape] = {}
        self.nbbo: dict[str, tuple[float, float, datetime]] = {}
        self._pending: list[tuple[str, float, float, int, float]] | None = None
        self.restored_minute: int | None = None  # the minute of a restore: earlier minutes may miss the trades of the gap

    def start_session(self, day: date, *, restoring: bool = False) -> None:
        """A new session's tapes. ``restoring``: the trades the feed delivers until ``restore`` are HELD, then applied on top
        of the saved prefix in arrival order — none lost, none counted twice, no signal from a partial tape (Codex #500 P2-2)."""
        with self._view_lock:
            self.session = day
            self.tapes = {}
            self._pending = [] if restoring else None
            self.restored_minute = None

    @property
    def opening(self) -> dict[str, float]:
        with self._view_lock:
            return {symbol: tape.opening for symbol, tape in self.tapes.items() if tape.opening is not None}

    @property
    def last_trade(self) -> dict[str, Tape]:
        with self._view_lock:
            return {symbol: tape for symbol, tape in self.tapes.items() if tape.last_price is not None}

    def export(self, symbols: set[str]) -> dict[str, dict[str, Any]]:
        """The tapes of ``symbols`` for the engine's checkpoint: a restart continues them (Codex #500 P2-3)."""
        with self._view_lock:
            return {symbol: asdict(tape) for symbol, tape in self.tapes.items() if symbol in symbols}

    @property
    def restoring(self) -> bool:
        with self._view_lock:
            return self._pending is not None

    def restore(self, context: dict[str, dict[str, Any]], now: datetime | None = None) -> None:
        """Install the saved tapes, then the trades held since ``start_session(restoring=True)``, atomically. Minutes up to
        the restore's may miss the trades of the gap: ``signal_view`` reads only later ones (a full minute observed live).
        Only a PENDING restore installs anything: tapes already live are never replaced."""
        local = (now or datetime.now(timezone.utc)).astimezone(NEW_YORK)
        with self._view_lock:
            if self._pending is None:
                return
            self.restored_minute = local.hour * 60 + local.minute
            known = set(Tape.__dataclass_fields__)
            self.tapes = {symbol: Tape(**{key: value for key, value in values.items() if key in known})
                          for symbol, values in context.items()}
            held, self._pending = self._pending, None
            for symbol, price, size, minute, stamp in held:
                self.tapes.setdefault(symbol, Tape()).add(price, size, minute, stamp)

    def _record(self, payload: str | bytes) -> None:
        super()._record(payload)
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        try:
            item = json.loads(text)
            symbol = str(item.get("s") or "").strip().upper()
            price, size, stamp = float(item.get("p")), float(item.get("v") or 0.0), int(item.get("t"))
        except (TypeError, ValueError, AttributeError):
            return
        if not symbol or price <= 0 or stamp <= 0 or item.get("dp") is True or str(item.get("ms") or "open") != "open":
            return
        self.record_trade(symbol, price, size, datetime.fromtimestamp(stamp / 1000, tz=timezone.utc))

    def record_trade(self, symbol: str, price: float, size: float, at: datetime) -> None:
        local = at.astimezone(NEW_YORK)
        minute = local.hour * 60 + local.minute
        with self._view_lock:
            if self.session is None or local.date() != self.session or local.time() < SESSION_OPEN:
                return
            if self._pending is not None:  # a restart: held until the saved prefix is installed (Codex #500 P2-2)
                self._pending.append((symbol, price, size, minute, at.timestamp()))
                return
            self.tapes.setdefault(symbol, Tape()).add(price, size, minute, at.timestamp())

    def _record_quote(self, payload: str | bytes) -> None:
        super()._record_quote(payload)
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        try:
            item = json.loads(text)
            symbol = str(item.get("s") or "").strip().upper()
            bid, ask, stamp = float(item.get("bp") or 0.0), float(item.get("ap") or 0.0), int(item.get("t"))
        except (TypeError, ValueError, AttributeError):
            return
        if not symbol or bid <= 0 or ask <= 0 or ask < bid or stamp <= 0:
            return
        self.record_quote(symbol, bid, ask, datetime.fromtimestamp(stamp / 1000, tz=timezone.utc))

    def record_quote(self, symbol: str, bid: float, ask: float, at: datetime) -> None:
        with self._view_lock:
            current = self.nbbo.get(symbol)
            if current is None or at >= current[2]:
                self.nbbo[symbol] = (bid, ask, at)

    def view(self, symbol: str) -> "MarketView":
        with self._view_lock:
            tape = self.tapes.get(symbol)
            quote = self.nbbo.get(symbol)
            price, vwap = (tape.last_price, tape.vwap) if tape else (None, None)
            trade_at = datetime.fromtimestamp(tape.last_at, tz=timezone.utc) if tape and tape.last_at else None
        return MarketView(price=price, trade_at=trade_at, vwap=vwap,
                          bid=quote[0] if quote else None, ask=quote[1] if quote else None, quote_at=quote[2] if quote else None)

    def signal_view(self, symbol: str, minute: int) -> tuple[float, float] | None:
        """(close, VWAP) of the last minute COMPLETED before ``minute`` (minutes after midnight ET), or None."""
        with self._view_lock:
            tape = self.tapes.get(symbol)
            if tape is None or tape.last_price is None:
                return None
            # after a restore, a minute at or before the restore may miss the trades of the gap: no signal from it
            floor = self.restored_minute + 1 if self.restored_minute is not None else -1
            if tape.minute < minute:  # no trade yet in the current minute: the last trade closed a completed minute
                vwap = tape.vwap
                return (tape.last_price, vwap) if vwap is not None and tape.minute >= floor else None
            if (tape.closed_minute < 0 or tape.closed_minute >= minute or tape.closed_minute < floor or tape.closed_price is None
                    or tape.closed_vwap is None):
                return None
            return tape.closed_price, tape.closed_vwap


@dataclass
class MarketView:
    price: float | None = None
    trade_at: datetime | None = None
    vwap: float | None = None
    bid: float | None = None
    ask: float | None = None
    quote_at: datetime | None = None

    def quote_fresh(self, now: datetime) -> bool:
        return (self.bid is not None and self.ask is not None and self.quote_at is not None
                and 0 < self.bid <= self.ask and (now - self.quote_at).total_seconds() <= QUOTE_MAX_AGE_SECONDS)


# ------------------------------------------------------------------ the universe (before the open)
@dataclass
class Member:
    symbol: str
    market: str  # NASDAQ or NYSE
    prev_close: float
    adv_usd: float


def previous_sessions(day: date, count: int) -> list[date]:
    import exchange_calendars as xcals
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(day - timedelta(days=count * 2 + 15), day - timedelta(days=1))
    return [date.fromisoformat(str(stamp)[:10]) for stamp in sessions[-count:]]


def build_universe(get_json: Callable[..., Any], base_url: str, token: str, day: date, cache_dir: Path) -> list[Member]:
    """The 550 most liquid US common stocks at the open of ``day``: 20-session mean of close × volume ≥ US$ 15 M,
    last close ≥ US$ 5, from EODHD's end-of-day bulk files (cached per session) and its US symbol list."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    catalog_rows = get_json(f"{base_url}/api/exchange-symbol-list/US", params={"api_token": token, "fmt": "json"}) or []
    listing: dict[str, str] = {}
    for row in catalog_rows:
        code = str(row.get("Code") or "").strip().upper()
        exchange = str(row.get("Exchange") or "").upper()
        if row.get("Type") != "Common Stock" or not code or not exchange:
            continue
        if exchange.startswith("NASDAQ"):
            listing[code] = "NASDAQ"
        elif exchange.startswith("NYSE") or exchange in {"AMEX", "BATS", "NYSE ARCA", "NYSE MKT"}:
            listing[code] = "NYSE"
    dollar: dict[str, list[float]] = {}
    last_close: dict[str, float] = {}
    sessions = previous_sessions(day, ADV_DAYS)
    for session in sessions:
        path = cache_dir / f"{session.isoformat()}.json"
        if path.exists():
            rows = json.loads(path.read_text())
        else:
            raw = get_json(f"{base_url}/api/eod-bulk-last-day/US",
                           params={"api_token": token, "fmt": "json", "date": session.isoformat()}) or []
            rows = [{"code": r.get("code"), "close": r.get("close"), "volume": r.get("volume")} for r in raw if isinstance(r, dict)]
            path.write_text(json.dumps(rows))
        for row in rows:
            code = str(row.get("code") or "").strip().upper()
            try:
                close, volume = float(row.get("close") or 0.0), float(row.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if code in listing and close > 0 and volume >= 0:
                dollar.setdefault(code, []).append(close * volume)
                if session == sessions[-1]:
                    last_close[code] = close
    members = [Member(code, listing[code], last_close[code], sum(values) / len(values))
               for code, values in dollar.items()
               if len(values) >= MIN_ADV_DAYS and code in last_close and last_close[code] >= RULE["price_min"]
               and sum(values) / len(values) >= RULE["adv_min_usd"]]
    members.sort(key=lambda member: (-member.adv_usd, member.symbol))
    return members[:UNIVERSE_SIZE]


# ------------------------------------------------------------------ the engine (pure: decisions from views)
@dataclass
class Position:
    symbol: str
    market: str
    shares: float
    entry_price: float  # the ask paid
    cost_usd: float  # shares × ask × (1 + fee)
    opened_at: str
    peak_percent: float | None = None
    armed: bool = False
    days_held: int = 0
    last_mark: float | None = None

    def net_percent(self, bid: float) -> float:
        return (self.shares * bid * (1 - FEE_SIDE) / self.cost_usd - 1) * 100


@dataclass
class EngineState:
    nav_realized: float
    positions: dict[str, Position] = field(default_factory=dict)
    last_session: str = ""  # the last session CLOSED
    # the session in progress, so a restart of the service resumes it instead of starting it over
    session: str = ""
    nav_start: float | None = None
    candidates: dict[str, float] = field(default_factory=dict)
    below: dict[str, bool] = field(default_factory=dict)
    signals: int = 0
    fills: list[dict[str, Any]] = field(default_factory=list)
    last_signal_minute: int = -1  # minutes after midnight ET of the last minute close the entries were checked on
    candidates_fixed: bool = False  # the selection at the open happened (even when it found none)
    stream_context: dict[str, dict[str, Any]] = field(default_factory=dict)  # the tapes, for a restart

    def to_json(self) -> dict[str, Any]:
        return {"nav_realized": self.nav_realized, "last_session": self.last_session,
                "positions": [asdict(position) for position in self.positions.values()], "session": self.session,
                "nav_start": self.nav_start, "candidates": self.candidates, "below": self.below, "signals": self.signals,
                "fills": self.fills, "last_signal_minute": self.last_signal_minute,
                "candidates_fixed": self.candidates_fixed, "stream_context": self.stream_context}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "EngineState":
        positions = {row["symbol"]: Position(**row) for row in data.get("positions") or []}
        return cls(nav_realized=float(data["nav_realized"]), positions=positions, last_session=str(data.get("last_session") or ""),
                   session=str(data.get("session") or ""), nav_start=data.get("nav_start"),
                   candidates=dict(data.get("candidates") or {}), below=dict(data.get("below") or {}),
                   signals=int(data.get("signals") or 0), fills=list(data.get("fills") or []),
                   last_signal_minute=int(data.get("last_signal_minute", -1)),
                   candidates_fixed=bool(data.get("candidates_fixed")), stream_context=dict(data.get("stream_context") or {}))


class Engine:
    """One session of the rule: candidates at the open, then a decision every call of ``step``."""

    def __init__(self, state: EngineState, day: date, universe: list[Member]):
        self.state, self.day = state, day
        self.members = {member.symbol: member for member in universe}
        for symbol, position in state.positions.items():  # a carried name stays tradeable for its exit
            self.members.setdefault(symbol, Member(symbol, position.market, 0.0, 0.0))
        self.resumed = state.session == day.isoformat()
        if not self.resumed:  # a new session: the opening NAV is the last close marked at the last known prices
            state.session, state.candidates, state.below, state.signals, state.fills = day.isoformat(), {}, {}, 0, []
            state.last_signal_minute, state.candidates_fixed, state.stream_context = -1, False, {}
            state.nav_start = state.nav_realized + sum(
                p.cost_usd * (p.net_percent(p.last_mark) / 100 if p.last_mark else 0.0) for p in state.positions.values())

    @property
    def nav_start(self) -> float:
        return float(self.state.nav_start if self.state.nav_start is not None else self.state.nav_realized)

    @property
    def candidates(self) -> dict[str, float]:  # symbol -> gap %
        return self.state.candidates

    @property
    def below(self) -> dict[str, bool]:
        return self.state.below

    @property
    def fills(self) -> list[dict[str, Any]]:
        return self.state.fills

    @property
    def signals(self) -> int:
        return self.state.signals

    @signals.setter
    def signals(self, value: int) -> None:
        self.state.signals = value

    def set_candidates(self, opening: dict[str, float]) -> None:
        if self.state.candidates_fixed:
            return  # fixed once at the open, even when empty: a restart never selects again (Codex #500 P2-3)
        self.state.candidates_fixed = True
        for symbol, member in self.members.items():
            price = opening.get(symbol)
            if price and member.prev_close > 0:
                gap = (price / member.prev_close - 1) * 100
                if gap <= -RULE["gap_min_percent"]:
                    self.candidates[symbol] = gap

    def step(self, now: datetime, view: Callable[[str], MarketView],
             signal: Callable[[str, int], tuple[float, float] | None] | None = None) -> list[dict[str, Any]]:
        """``view``: the live price and quote (exits and execution). ``signal``: (close, VWAP) of the last COMPLETED
        minute before the given one (the buy signal); without it, the view's last price and VWAP stand in (tests)."""
        local = now.astimezone(NEW_YORK).time()
        new: list[dict[str, Any]] = []
        for symbol, position in list(self.state.positions.items()):
            market = view(symbol)
            if not market.quote_fresh(now):
                continue
            assert market.bid is not None
            net = position.net_percent(market.bid)
            position.last_mark = market.bid
            position.peak_percent = net if position.peak_percent is None else max(position.peak_percent, net)
            if position.peak_percent >= RULE["lock_min_percent"]:
                position.armed = True
            reason = None
            if net <= -RULE["stop_percent"]:
                reason = "hard_stop"
            elif position.armed and net <= max(RULE["lock_min_percent"], position.peak_percent - RULE["pullback_percent"]):
                reason = "lock"
            elif local >= SELL_POSITIVES_FROM and net > 0:
                reason = "t30_positive"
            if reason:
                new.append(self._sell(position, market.bid, net, reason, now))
        # The buy signal is the measured one: the cross back above the VWAP on a MINUTE CLOSE (the first check of each
        # new minute reads the previous minute's last trade), executed at once at the real ask; checking every
        # second would buy the noise around the VWAP. The exits above run every second.
        minute = local.hour * 60 + local.minute
        if local <= LAST_ENTRY and minute != self.state.last_signal_minute:
            self.state.last_signal_minute = minute
            for symbol, gap in self.candidates.items():
                market = view(symbol)
                if signal is not None:
                    closed = signal(symbol, minute)
                    close, vwap = closed if closed else (None, None)
                else:
                    close, vwap = market.price, market.vwap
                if close is None or vwap is None:
                    continue
                if close < vwap:
                    self.below[symbol] = True
                    continue
                if close <= vwap or not self.below.get(symbol):
                    continue
                self.below[symbol] = False
                self.signals += 1
                if symbol in self.state.positions or len(self.state.positions) >= RULE["slots"] or not market.quote_fresh(now):
                    continue
                assert market.bid is not None and market.ask is not None
                spread_bps = (market.ask - market.bid) / ((market.ask + market.bid) / 2) * 1e4
                if spread_bps > RULE["spread_max_bps"]:
                    continue
                new.append(self._buy(symbol, market.ask, gap, spread_bps, now))
        return new

    def _buy(self, symbol: str, ask: float, gap: float, spread_bps: float, now: datetime) -> dict[str, Any]:
        size = self.state.nav_realized / RULE["slots"]
        shares = size / (ask * (1 + FEE_SIDE))
        member = self.members[symbol]
        self.state.positions[symbol] = Position(symbol, member.market, shares, ask, size, now.isoformat(), last_mark=ask)
        fill = {"side": "BUY", "symbol": symbol, "market": member.market, "quantity": shares, "price": ask,
                "executed_at": now.isoformat(), "fees_usd": shares * ask * FEE_SIDE, "realized_pnl_usd": None,
                "realized_return_percent": None,
                "reason": "compra: abertura %+.2f%% sobre o fechamento anterior, voltou acima do VWAP, spread %.1f bps" % (gap, spread_bps)}
        self.fills.append(fill)
        return fill

    def _sell(self, position: Position, bid: float, net: float, reason: str, now: datetime) -> dict[str, Any]:
        pnl = position.cost_usd * net / 100
        self.state.nav_realized += pnl
        del self.state.positions[position.symbol]
        held = " (posição de %d pregão(ões) atrás)" % position.days_held if position.days_held else ""
        fill = {"side": "SELL", "symbol": position.symbol, "market": position.market, "quantity": position.shares,
                "price": bid, "executed_at": now.isoformat(), "fees_usd": position.shares * bid * FEE_SIDE,
                "realized_pnl_usd": pnl, "realized_return_percent": net,
                "reason": "venda: %s, %+.3f%% líquido de custos%s" % (r2d2_lab_live_reason(reason), net, held)}
        self.fills.append(fill)
        return fill

    def close_session(self) -> None:
        for position in self.state.positions.values():
            position.days_held += 1
        self.state.last_session = self.day.isoformat()
        self.state.session = ""

    def book(self, now: datetime) -> dict[str, Any]:
        positions, unrealized = [], 0.0
        for position in self.state.positions.values():
            mark = position.last_mark or position.entry_price
            net = position.net_percent(mark)
            result = position.cost_usd * net / 100
            unrealized += result
            positions.append({"symbol": position.symbol, "market": position.market, "quantity": position.shares,
                              "average_cost": position.entry_price, "last_price": mark, "cost_usd": position.cost_usd,
                              "unrealized_pnl_usd": result, "unrealized_return_percent": net,
                              "stop_price": position.cost_usd * (1 - RULE["stop_percent"] / 100) / (position.shares * (1 - FEE_SIDE)),
                              "opened_at": position.opened_at})
        cash = self.state.nav_realized - sum(position.cost_usd for position in self.state.positions.values())
        return {"nav_start_usd": self.nav_start, "nav_usd": self.state.nav_realized + unrealized,
                "realized_nav_usd": self.state.nav_realized, "cash_usd": cash, "as_of": now.isoformat(), "positions": positions}

    def document(self, now: datetime) -> dict[str, Any]:
        trades = []
        for index, fill in enumerate(self.fills):
            stamp = int(datetime.fromisoformat(fill["executed_at"]).timestamp())
            trades.append({"id": "%s:%s:%s:%s:%d:%d" % (CONFIG, self.day.isoformat(), fill["symbol"], fill["side"].lower(), stamp, index),
                           **{key: _rounded(key, value) for key, value in fill.items()}})
        sells = sum(1 for fill in self.fills if fill["side"] == "SELL")
        return {"schema": r2d2_lab_live.SCHEMA, "day": self.day.isoformat(), "config": CONFIG, "trades": trades,
                "book": {key: _rounded(key, value) for key, value in self.book(now).items()},
                "cycle": {"candidates": len(self.candidates), "signals": self.signals,
                          "entries": sum(1 for fill in self.fills if fill["side"] == "BUY"), "closed": sells}}


def r2d2_lab_live_reason(reason: str) -> str:
    return {"lock": "trava de lucro", "hard_stop": "stop", "t30_positive": "positiva nos últimos 30 s"}.get(reason, reason)


def _rounded(key: str, value: Any) -> Any:
    if isinstance(value, float) and math.isfinite(value):
        return round(value, 2 if key.endswith("_usd") else 6)
    if isinstance(value, list):
        return [{k: _rounded(k, v) for k, v in item.items()} for item in value]
    return value


# ------------------------------------------------------------------ persistence of the engine's own state
def load_state(database: Any, opening_nav: Callable[[], EngineState | None]) -> EngineState:
    snapshot = database.latest_analysis_snapshot(STATE_TYPE, STATE_KEY)
    outputs = (snapshot or {}).get("outputs")
    if isinstance(outputs, dict) and "nav_realized" in outputs:
        return EngineState.from_json(outputs)
    seeded = opening_nav()
    if seeded is None:
        raise RuntimeError("no engine state and no lab book to start from")
    return seeded


def save_state(database: Any, state: EngineState, now: datetime) -> None:
    methodology = database.ensure_methodology_version(
        "r2d2_live_engine", 1, {"rule": RULE, "config": CONFIG, "fee_side": FEE_SIDE},
        "The live R2D2 inside the C3PO server on the EODHD real-time stream (owner 27/10/2026)")
    database.save_analysis_snapshot(STATE_TYPE, STATE_KEY, methodology, {"config": CONFIG}, state.to_json(), now)


def seed_from_lab_book(database: Any, now: datetime) -> EngineState | None:
    """The first start: the NAV and positions of the latest lab book (the GitHub engine's close, owner 26/10 book)."""
    found = r2d2_lab_live.latest_book(database, now=now)
    if found is None:
        return None
    book = found[2]
    positions = {}
    for item in book["positions"]:
        positions[item["symbol"]] = Position(item["symbol"], item["market"], item["quantity"], item["average_cost"],
                                             item["cost_usd"], item["opened_at"], last_mark=item["last_price"], days_held=1)
    return EngineState(nav_realized=book["realized_nav_usd"], positions=positions, last_session=found[0])


ENGINE_MAX_TRADES = 20_000  # a whole session at any cadence (Codex #500 P2-6); the public route keeps its own cap


def publish(database: Any, engine: Engine, now: datetime, *, as_of: datetime | None = None) -> dict[str, Any]:
    return r2d2_lab_live.store(database, engine.document(as_of or now), now=now, max_trades=ENGINE_MAX_TRADES)


def reconcile_previous(database: Any, state: EngineState, day: date, now: datetime) -> bool:
    """Before a NEW session clears the fills: the previous session's document as its checkpoint holds it (Codex #500 P2-3).
    A session the checkpoint never closed (a crash before the close) is closed first; then its public document is
    published again unless the stored one already carries exactly these fills. True when anything was written."""
    prior = state.session or state.last_session
    if not prior or prior == day.isoformat():
        return False
    prior_day = date.fromisoformat(prior)
    unclosed = state.session == prior
    if not unclosed and not state.fills:
        return False
    keep = state.session
    state.session = prior  # an Engine on the prior day that keeps its fills
    engine = Engine(state, prior_day, [])
    if unclosed:
        engine.close_session()
    else:
        state.session = keep
    close_at = datetime.combine(prior_day, SESSION_CLOSE, tzinfo=NEW_YORK).astimezone(timezone.utc)
    stored = ((database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, prior) or {}).get("outputs") or {}).get("trades")
    pending = bool(state.fills) and stored != engine.document(close_at)["trades"]
    if not unclosed and not pending:
        return False
    if unclosed:
        save_state(database, state, now)
    if pending:
        try:
            publish(database, engine, now, as_of=close_at)
        except r2d2_lab_live.LabLiveRefused:  # a document too old for the screen (a long holiday): the state is consistent
            logger.info("R2D2 live: previous session %s not republished (refused by the screen)", prior)
    return True


# ------------------------------------------------------------------ the service
def subscription(universe: list[Member], positions: Mapping[str, Any], size: int | None = None) -> list[str]:
    """EVERY held name first (its exits need its quote, inside or outside the new universe), then the universe's names
    without a position up to ``size`` (Codex #500 P2-1: a reservation never pushes another held name out)."""
    limit = UNIVERSE_SIZE if size is None else size
    held = sorted(positions)
    rest = [member.symbol for member in universe if member.symbol not in positions]
    return held + rest[: max(0, limit - len(held))]


STREAM_STATES = frozenset({"connecting", "connected", "error", "stopped", "idle"})


def heartbeat(stream: Any, engine: "Engine", moment: datetime) -> str:
    """The heartbeat line: numbers and a closed set of stream states only — never an error text (the status workflow
    publishes it in a public repository; Codex #500 P2-5)."""
    state = str(getattr(stream, "status", "") or "")
    return ("R2D2 live heartbeat: stream=%s error=%d trades=%d quotes=%d candidates=%d signals=%d positions=%d fills=%d nav=%.2f"
            % (state if state in STREAM_STATES else "other", 1 if getattr(stream, "last_error", "") else 0,
               len(getattr(stream, "last_trade", {})), len(getattr(stream, "nbbo", {})), len(engine.candidates), engine.signals,
               len(engine.state.positions), len(engine.fills), engine.book(moment)["nav_usd"]))


def run_session(*, stream: LiveEngineStream, database: Any, get_json: Callable[..., Any], base_url: str, token: str,
                day: date, cache_dir: Path, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                sleep: Callable[[float], None] = clock_time.sleep, job: Callable[[], Any] | None = None) -> EngineState:
    """One session, from the universe before the open to the close. Every database write goes through ``job`` (the
    host's maintenance gate) when given."""
    def guarded(action: Callable[[], Any]) -> Any:
        if job is None:
            return action()
        with job() as admitted:
            return action() if admitted else None

    universe = build_universe(get_json, base_url, token, day, cache_dir)
    state = load_state(database, lambda: seed_from_lab_book(database, now()))
    reconciled: list[bool] = []
    while not reconciled:  # never a new session over the previous one's pending state (the gate may refuse: wait)
        guarded(lambda: reconciled.append(reconcile_previous(database, state, day, now())))
        if not reconciled:
            sleep(5.0)
    engine = Engine(state, day, universe)
    stream.set_group(STREAM_GROUP, subscription(universe, state.positions), priority=200)
    if getattr(stream, "session", None) == day:
        # an in-process retry (with or without a durable checkpoint of today): the stream's own tapes of today are the most
        # complete; a restore a failed attempt left pending is finished first (its held trades applied, nothing cleared)
        if getattr(stream, "restoring", False):
            stream.restore(state.stream_context if engine.resumed else {}, now())
    elif engine.resumed and hasattr(stream, "restore"):
        stream.start_session(day, restoring=True)
        stream.restore(state.stream_context, now())  # a fresh process continues the tapes of the candidates and positions
    else:
        stream.start_session(day)
    logger.info("R2D2 live: session %s%s, universe %d, carried %d, NAV %.2f", day, " (resumed)" if engine.resumed else "",
                len(universe), len(state.positions), state.nav_realized)
    signal = getattr(stream, "signal_view", None)

    def commit(moment: datetime) -> None:
        """The checkpoint first, then the screen: the published book never runs ahead of a state a restart can load
        (Codex #500 P2-4). A failure after the checkpoint is repaired by the next publish from the resumed state."""
        if hasattr(stream, "export"):
            engine.state.stream_context = stream.export(set(engine.candidates) | set(engine.state.positions))
        save_state(database, engine.state, moment)
        publish(database, engine, moment)

    def at(moment: time) -> datetime:
        return datetime.combine(day, moment, tzinfo=NEW_YORK).astimezone(timezone.utc)

    while now() < at(OPENING_WINDOW_END):
        sleep(min(1.0, max(0.05, (at(OPENING_WINDOW_END) - now()).total_seconds())))
    engine.set_candidates(dict(stream.opening))
    logger.info("R2D2 live: %d candidates of %d with an opening print", len(engine.candidates), len(stream.opening))
    guarded(lambda: commit(now()))
    last_marks = clock_time.monotonic()
    while now() < at(SESSION_CLOSE):
        moment = now()
        fills = engine.step(moment, stream.view, signal)
        if fills or clock_time.monotonic() - last_marks >= MARKS_EVERY_SECONDS:
            guarded(lambda: commit(moment))
            if not fills:
                logger.info("%s", heartbeat(stream, engine, moment))
            last_marks = clock_time.monotonic()
        sleep(1.0)
    engine.close_session()
    guarded(lambda: commit(now()))
    stream.set_group(STREAM_GROUP, [])
    logger.info("R2D2 live: session %s closed, NAV %.2f, %d fills, %d carried", day, engine.state.nav_realized,
                len(engine.fills), len(engine.state.positions))
    return engine.state


def next_session(today: date) -> date:
    import exchange_calendars as xcals
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(today, today + timedelta(days=10))
    return date.fromisoformat(str(sessions[0])[:10])


def status(database: Any, now: datetime) -> dict[str, Any]:
    """A read-only summary for the operator (no symbols): the engine state and today's document."""
    snapshot = database.latest_analysis_snapshot(STATE_TYPE, STATE_KEY) or {}
    state = snapshot.get("outputs") or {}
    day = now.astimezone(NEW_YORK).date().isoformat()
    document = (database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, day) or {}).get("outputs") or {}
    book = document.get("book") or {}
    return {"now": now.isoformat(), "state_saved_at": str(snapshot.get("published_at")), "last_session": state.get("last_session"),
            "session_in_progress": state.get("session"), "nav_realized": state.get("nav_realized"),
            "positions": len(state.get("positions") or []), "today_config": document.get("config"),
            "today_fills": len(document.get("trades") or []), "today_cycle": document.get("cycle"),
            "today_nav": book.get("nav_usd"), "today_book_as_of": book.get("as_of")}


def main() -> None:
    import sys
    if "--status" in sys.argv:
        from .config import get_settings as settings_of
        from .database import Database as DatabaseOf
        print(json.dumps(status(DatabaseOf(settings_of()), datetime.now(timezone.utc)), default=str))
        return
    from .config import get_settings
    from .database import Database
    from .maintenance_gate import job, startup_job
    from .market_data.http import JsonHttpClient
    from .observability import init_sentry

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with startup_job():
        settings = get_settings()
        init_sentry(settings, service_name="r2d2-live")
        database = Database(settings)
        database.initialize()
    http = JsonHttpClient(timeout=60.0, max_retries=3)
    stream = LiveEngineStream(settings.eodhd_api_token)
    stream.start()
    cache_dir = Path(os.environ.get("C3PO_R2D2_LIVE_CACHE_DIR", "/app/day-d-data/r2d2-live/eod-bulk"))
    base_url = settings.eodhd_base_url.rstrip("/")
    while True:
        today_ny = datetime.now(NEW_YORK).date()
        day = next_session(today_ny)
        start = datetime.combine(day, time(9, 0), tzinfo=NEW_YORK)
        close = datetime.combine(day, SESSION_CLOSE, tzinfo=NEW_YORK)
        if datetime.now(NEW_YORK) >= close:
            day = next_session(today_ny + timedelta(days=1))
            start = datetime.combine(day, time(9, 0), tzinfo=NEW_YORK)
        wait = (start - datetime.now(NEW_YORK)).total_seconds()
        if wait > 0:
            logger.info("R2D2 live: next session %s, waiting %.0f s", day, wait)
            clock_time.sleep(min(wait, 3600))
            continue
        try:
            run_session(stream=stream, database=database, get_json=http.get_json, base_url=base_url,
                        token=settings.eodhd_api_token, day=day, cache_dir=cache_dir, job=job)
        except Exception:
            logger.exception("R2D2 live: the session failed")
            clock_time.sleep(60)


if __name__ == "__main__":
    main()
