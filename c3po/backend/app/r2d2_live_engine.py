"""The live R2D2 inside the C3PO server, on the EODHD real-time stream (owner, 27/10/2026: "claro que tem que mudar
para dentro do servidor do C3PO, não quero nada rodando no GitHub"; "a cada segundo").

The rule in force is the one the owner chose on 26/10 (TIT-2S3): stocks that open at least 1% below the previous close,
20-session dollar volume of at least US$ 15 M, price of at least US$ 5; a buy when a MINUTE CLOSE crosses back above
the session VWAP (the measured signal), executed at once at the real ask, with a quoted spread of at most 3 bps, up to
15:29:59 ET — the ask and the spread of the NBBO prevailing at that instant, read from Massive as the lab measured them
(``lab/massive.py`` quote_at, ``lab/cost_real.py`` touch: at most 60 s old), the stream's quote only when Massive does
not answer, 20 positions of NAV/20, re-entry allowed after an exit. Every second each open position is checked at the real bid: hard stop at -0.5% net,
profit lock armed at +0.15% net trailing the peak by 0.10, every positive position sold from 15:59:30 ET; the
negatives carry to the next session. Paper only: no broker, no order. Fills, book and scan counts are the same
documents the screen already reads (``r2d2_lab_live``), written straight to the database.

Universe: the 550 most liquid US common stocks (the stream's capacity), from EODHD's end-of-day bulk files of the
last 20 sessions; the open of each is its first regular-session trade on the stream.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time as clock_time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from threading import Lock
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import websockets

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
QUOTE_MAX_AGE_SECONDS = 5.0  # the exits: a position is marked only on a quote this recent
# the entries: the NBBO prevailing at the instant, at most this old — the lab's bound (lab/cost_real.py STALE_NS). The
# stream's per-name age is no staleness test: a quiet name's NBBO stands unchanged for many seconds (28/10: the 5 s
# bound and the stream's own quote refused the signals the lab's Massive NBBO took)
NBBO_MAX_AGE_SECONDS = 60.0
NBBO_TIMEOUT_SECONDS = 1.5  # the WHOLE request (DeadlineJsonHttpClient), no retry
NBBO_STEP_BUDGET_SECONDS = 3.0  # Massive time per minute's entries: the exits run on this loop; past it, the stream's quote
NBBO_PAUSE_AFTER_FAILURE_SECONDS = 30.0  # Massive failed: the stream's quote for this long, then Massive again
# Massive requests in flight at once for one minute's crosses. Asked one after the other (~0.7 s each from the host),
# the 3 s budget answered ~3 of the ~13 crosses a minute at the 29/10 open: 120 of 156 fell back to the stream's late quote
NBBO_PARALLEL = 32
NBBO_MAX_DEVIATION = 0.02  # a quote whose mid is further than this from the signal's own minute close is another
# instrument's (a share-class or mapping error) or absurd: never bought on (pre-review of e8ce1f3)
FUTURE_TOLERANCE_SECONDS = 5.0  # a stream message stamped further ahead than this is refused (it would pin the book)
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
        self._groups_version = 0  # bumped by every ``set_group``: the feed loop recomputes its subscription only then
        # how late the feed is: receipt time minus the message's own time (ms), the last message and the worst since the
        # last heartbeat, and the messages since the last heartbeat (0 = a silent feed, not a punctual one), per feed;
        # numbers only, published by the status workflow
        self.lag_ms = {"trade": 0, "quote": 0}
        self.lag_max_ms = {"trade": 0, "quote": 0}
        self.messages = {"trade": 0, "quote": 0}
        self._gauge_lock = Lock()  # the feed thread updates, the heartbeat takes and resets: every message in ONE interval

    def set_group(self, name: str, symbols: list[str], *, priority: int = 50) -> None:
        super().set_group(name, symbols, priority=priority)
        with self._lock:
            self._groups_version += 1

    async def _run_feed(self, feed: str, endpoint: str, recorder: Any) -> None:
        """The frozen module's feed loop, connection and errors unchanged, without its per-message bookkeeping: the module
        recomputes the whole subscription and the V2 lease evidence before EVERY message (~40 us each), which a 500-name
        quote feed cannot afford — the reader fell behind and every quote reached the engine stale (28/10: 164 signals,
        no buy). Here the subscription is recomputed only when a group changed; this process holds no V2 lease."""
        url = f"wss://ws.eodhistoricaldata.com/ws/{endpoint}?api_token={self.api_token}"
        while not self._stop.is_set():
            self._set_feed_state(feed, "connecting")
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=2,
                    max_size=1_000_000,
                ) as socket:
                    authorization = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                    status_code = authorization.get("status_code", authorization.get("status"))
                    if status_code != 200:
                        raise RuntimeError(str(authorization.get("message") or "authorization failed"))
                    self._set_feed_state(feed, "connected")
                    subscribed: set[str] = set()
                    version = -1  # a new connection subscribes from scratch
                    while not self._stop.is_set():
                        if version != self._groups_version:
                            with self._lock:
                                version = self._groups_version
                                desired = set(self._desired_symbols())
                            removed = sorted(subscribed - desired)
                            added = sorted(desired - subscribed)
                            if removed:
                                await asyncio.wait_for(socket.send(json.dumps({"action": "unsubscribe", "symbols": ",".join(removed)})), timeout=2)
                            if added:
                                await asyncio.wait_for(socket.send(json.dumps({"action": "subscribe", "symbols": ",".join(added)})), timeout=2)
                            subscribed = desired
                        try:
                            payload = await asyncio.wait_for(socket.recv(), timeout=1)
                        except TimeoutError:
                            continue
                        recorder(payload)
            except Exception as exc:
                if self._stop.is_set():
                    break
                safe_error = str(exc).replace(self.api_token, "[redacted]")[:180]
                logger.warning("EODHD realtime %s reconnect: %s", feed, safe_error)
                self._set_feed_state(feed, "error", safe_error)
                await asyncio.sleep(3)
        self._set_feed_state(feed, "stopped")

    def _lag(self, feed: str, stamp: int) -> None:
        lag = int(clock_time.time() * 1000) - stamp
        with self._gauge_lock:
            self.lag_ms[feed] = lag
            self.messages[feed] += 1
            if lag > self.lag_max_ms[feed]:
                self.lag_max_ms[feed] = lag

    def take_gauges(self) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        """(last lag, worst lag, messages) of the interval that ends now, read and reset in one step under the lock the
        feed updates them with (Codex 6473172399): a message counts in exactly one interval, its lag in that one's worst."""
        with self._gauge_lock:
            taken = dict(self.lag_ms), self.lag_max_ms, self.messages
            self.lag_max_ms, self.messages = {"trade": 0, "quote": 0}, {"trade": 0, "quote": 0}
        return taken

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
        if (not symbol or not math.isfinite(price) or price <= 0 or not math.isfinite(size) or stamp <= 0 or item.get("dp") is True
                or str(item.get("ms") or "open") != "open" or stamp > (clock_time.time() + FUTURE_TOLERANCE_SECONDS) * 1000):
            return
        self._lag("trade", stamp)
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
        if (not symbol or not (math.isfinite(bid) and math.isfinite(ask)) or bid <= 0 or ask <= 0 or ask < bid or stamp <= 0
                or stamp > (clock_time.time() + FUTURE_TOLERANCE_SECONDS) * 1000):
            return
        self._lag("quote", stamp)
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
        # why a signal did not buy, since this process started (``signals`` is the session's, restored on a restart)
        self.skips = {"held": 0, "slots": 0, "noquote": 0, "stale": 0, "spread": 0, "late": 0, "implausible": 0}
        # where the entries' NBBO came from (Massive, the stream's fallback, Massive not answering) and how many buys the
        # stream's own quote under the old 5 s rule would have refused (this process only)
        self.sources = {"massive": 0, "stream": 0, "unanswered": 0, "mismatch": 0, "stream_would_refuse": 0}
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
             signal: Callable[[str, int], tuple[float, float] | None] | None = None,
             nbbo: Callable[[str, datetime], tuple[float, float, datetime] | None] | None = None) -> list[dict[str, Any]]:
        """``view``: the live price and quote (exits; the entries' fallback). ``signal``: (close, VWAP) of the last
        COMPLETED minute before the given one (the buy signal); without it, the view's last price and VWAP stand in
        (tests). ``nbbo``: (bid, ask, time) of the NBBO prevailing at the instant (Massive), or None when it does not answer."""
        local = now.astimezone(NEW_YORK).time()
        started_step = clock_time.monotonic()
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
            crosses: list[tuple[str, float, float]] = []  # (symbol, gap, signal close): this minute's crosses, in order
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
                if symbol in self.state.positions:
                    self.skips["held"] += 1
                else:
                    crosses.append((symbol, gap, close))
            # Massive is asked for every cross of the minute AT ONCE, at the effective instant (Codex P2-2); each request
            # is bounded by NBBO_TIMEOUT_SECONDS and the whole set by NBBO_STEP_BUDGET_SECONDS (Codex P2-1): the entries
            # never hold the exits' loop longer than that, and what has not answered by then is unanswered
            answers: dict[str, tuple[float, float, datetime]] = {}
            if nbbo is not None and crosses and len(self.state.positions) < RULE["slots"]:
                answers = ask_nbbo(nbbo, [symbol for symbol, _, _ in crosses],
                                   now + timedelta(seconds=clock_time.monotonic() - started_step))
            for symbol, gap, close in crosses:
                if len(self.state.positions) >= RULE["slots"]:
                    self.skips["slots"] += 1
                    continue
                market = view(symbol)
                # the effective clock: the instant ``now`` plus the time this step has waited (Codex P2-2), sampled AFTER
                # the reads that may block (the view takes the stream's lock; Codex 6499564395): the last entry, the
                # quote's age and the fill all read this one instant
                moment = now + timedelta(seconds=clock_time.monotonic() - started_step)
                quote, source = None, "stream"
                if nbbo is not None:
                    quote = answers.get(symbol)
                    if quote is not None and not plausible(quote, close):
                        self.sources["mismatch"] += 1  # far from the signal's own close: never bought on, the stream stands in
                        quote = None
                    elif quote is None:
                        self.sources["unanswered"] += 1
                    else:
                        source = "massive"
                if quote is None and market.bid is not None and market.ask is not None and market.quote_at is not None:
                    quote = (market.bid, market.ask, market.quote_at)
                if quote is None:
                    self.skips["noquote"] += 1
                    continue
                if not plausible(quote, close):
                    self.skips["implausible"] += 1
                    continue
                if moment.astimezone(NEW_YORK).time() > LAST_ENTRY:  # the answer came after the last entry: no buy
                    self.skips["late"] += 1
                    break
                self.sources[source] += 1
                bid, ask, quoted_at = quote
                # the lab's 60 s on the NBBO; the stream's own quote keeps its 5 s (a fallback never loosens the old rule)
                max_age = NBBO_MAX_AGE_SECONDS if source == "massive" else QUOTE_MAX_AGE_SECONDS
                if (not (math.isfinite(bid) and math.isfinite(ask)) or not 0 < bid <= ask
                        or (moment - quoted_at).total_seconds() > max_age):
                    self.skips["stale"] += 1
                    continue
                spread_bps = (ask - bid) / ((ask + bid) / 2) * 1e4
                if spread_bps > RULE["spread_max_bps"]:
                    self.skips["spread"] += 1
                    continue
                if source == "massive" and not (market.quote_fresh(moment) and market.bid is not None and market.ask is not None
                                                and (market.ask - market.bid) / ((market.ask + market.bid) / 2) * 1e4
                                                <= RULE["spread_max_bps"]):
                    self.sources["stream_would_refuse"] += 1  # the evidence: a buy the stream's quote alone refused
                new.append(self._buy(symbol, ask, gap, spread_bps, moment, source))
        return new

    def _buy(self, symbol: str, ask: float, gap: float, spread_bps: float, now: datetime, source: str = "stream") -> dict[str, Any]:
        size = self.state.nav_realized / RULE["slots"]
        shares = size / (ask * (1 + FEE_SIDE))
        member = self.members[symbol]
        self.state.positions[symbol] = Position(symbol, member.market, shares, ask, size, now.isoformat(), last_mark=ask)
        fill = {"side": "BUY", "symbol": symbol, "market": member.market, "quantity": shares, "price": ask,
                "executed_at": now.isoformat(), "fees_usd": shares * ask * FEE_SIDE, "realized_pnl_usd": None,
                "realized_return_percent": None,
                "reason": "compra: abertura %+.2f%% sobre o fechamento anterior, voltou acima do VWAP, spread %.1f bps (%s)"
                          % (gap, spread_bps, "NBBO Massive" if source == "massive" else "cotação do stream")}
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


def plausible(quote: tuple[float, float, datetime], close: float) -> bool:
    """A quote a buy may stand on: finite, ordered, within the screen's own bounds, and its mid within
    ``NBBO_MAX_DEVIATION`` of the signal's own minute close (another instrument's or an absurd quote is never bought on)."""
    bid, ask, _ = quote
    if not (math.isfinite(bid) and math.isfinite(ask) and math.isfinite(close)) or not 0 < bid <= ask <= r2d2_lab_live.MAX_PRICE:
        return False
    return close > 0 and abs((bid + ask) / 2 / close - 1) <= NBBO_MAX_DEVIATION


def quiet_request_logs() -> None:
    """httpx logs every request at INFO with its full URL — the Massive token is in the query: never in the logs, never a
    Sentry breadcrumb (as app/r2d2_worker.py and app/valuation_worker.py do)."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def massive_nbbo(get_json: Callable[..., Any], base_url: str, token: str, *,
                 monotonic: Callable[[], float] = clock_time.monotonic) -> Callable[[str, datetime], tuple[float, float, datetime] | None]:
    """The NBBO prevailing at an instant, as the lab reads it (``lab/massive.py`` quote_at: the last quote at or before
    the instant): (bid, ask, SIP time), or None — never an exception and never an error text (the token travels in the
    query: ``main`` keeps httpx's request lines out of the logs). Share classes in Massive's spelling (EODHD BRK-B →
    BRK.B). After a failure Massive is not asked for ``NBBO_PAUSE_AFTER_FAILURE_SECONDS``: the stream stands in."""
    from urllib.parse import quote as quoted
    paused_until = [0.0]

    def nbbo(symbol: str, now: datetime) -> tuple[float, float, datetime] | None:
        if monotonic() < paused_until[0]:
            return None
        try:
            payload = get_json(f"{base_url.rstrip('/')}/v3/quotes/{quoted(symbol.replace('-', '.'), safe='')}",
                               params={"timestamp.lte": int(now.timestamp() * 1e9), "order": "desc", "sort": "timestamp",
                                       "limit": 1, "apiKey": token})
            row = (payload.get("results") or [None])[0] if isinstance(payload, dict) else None
            if not isinstance(row, dict):
                return None
        except Exception:
            paused_until[0] = monotonic() + NBBO_PAUSE_AFTER_FAILURE_SECONDS
            return None
        try:  # an answer that is no usable NBBO is refused here, whole: the stream stands in (Codex 6478311166 P2-3)
            bid, ask, sip = float(row.get("bid_price") or 0.0), float(row.get("ask_price") or 0.0), int(row.get("sip_timestamp") or 0)
            if not (math.isfinite(bid) and math.isfinite(ask) and 0 < bid <= ask and sip > 0):
                return None
            quoted_at = datetime.fromtimestamp(sip / 1e9, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            return None
        if not now - timedelta(days=1) <= quoted_at <= now + timedelta(seconds=5):
            return None
        return bid, ask, quoted_at
    return nbbo


def ask_nbbo(nbbo: Callable[[str, datetime], tuple[float, float, datetime] | None], symbols: list[str],
             at: datetime) -> dict[str, tuple[float, float, datetime]]:
    """Every cross of one minute asked of Massive at once (up to ``NBBO_PARALLEL`` in flight), each at ``at``: the
    answers that came within ``NBBO_STEP_BUDGET_SECONDS`` of the first asking (starting the threads counts). One that
    has not answered by then is never waited for (its thread ends on its own request's deadline) and one that raised
    is no answer: the stream's quote stands in."""
    deadline = clock_time.monotonic() + NBBO_STEP_BUDGET_SECONDS
    pool = ThreadPoolExecutor(max_workers=max(1, min(NBBO_PARALLEL, len(symbols))), thread_name_prefix="r2d2-nbbo")
    try:
        asked = {pool.submit(nbbo, symbol, at): symbol for symbol in symbols}
        done, _ = wait_futures(asked, timeout=max(0.0, deadline - clock_time.monotonic()))
        answers: dict[str, tuple[float, float, datetime]] = {}
        for future in done:
            try:
                quote = future.result()
            except Exception:
                continue
            if quote is not None:
                answers[asked[future]] = quote
        return answers
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def feed_line(stream: Any, engine: "Engine") -> str:
    """How late the feed is and why signals did not buy: numbers only (published by the status workflow). Resets the
    worst lag of the interval."""
    take = getattr(stream, "take_gauges", None)
    lag, worst, count = take() if take is not None else ({}, {}, {})
    skips, sources = engine.skips, engine.sources
    return ("R2D2 live feed: trade_messages=%d quote_messages=%d trade_lag_ms=%d quote_lag_ms=%d trade_lag_max_ms=%d "
            "quote_lag_max_ms=%d skips held=%d slots=%d noquote=%d stale=%d spread=%d late=%d implausible=%d "
            "nbbo massive=%d stream=%d unanswered=%d mismatch=%d stream_would_refuse=%d"
            % (int(count.get("trade", 0)), int(count.get("quote", 0)), int(lag.get("trade", 0)), int(lag.get("quote", 0)),
               int(worst.get("trade", 0)), int(worst.get("quote", 0)),
               skips["held"], skips["slots"], skips["noquote"], skips["stale"], skips["spread"], skips["late"], skips["implausible"],
               sources["massive"], sources["stream"], sources["unanswered"], sources["mismatch"], sources["stream_would_refuse"]))


def run_session(*, stream: LiveEngineStream, database: Any, get_json: Callable[..., Any], base_url: str, token: str,
                day: date, cache_dir: Path, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                sleep: Callable[[float], None] = clock_time.sleep, job: Callable[[], Any] | None = None,
                nbbo: Callable[[str, datetime], tuple[float, float, datetime] | None] | None = None) -> EngineState:
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
        fills = engine.step(moment, stream.view, signal, nbbo)
        if fills or clock_time.monotonic() - last_marks >= MARKS_EVERY_SECONDS:
            guarded(lambda: commit(moment))
            if not fills:
                logger.info("%s", heartbeat(stream, engine, moment))
                logger.info("%s", feed_line(stream, engine))
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
    from .market_data.http import DeadlineJsonHttpClient, JsonHttpClient
    from .observability import init_sentry

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    quiet_request_logs()
    with startup_job():
        settings = get_settings()
        init_sentry(settings, service_name="r2d2-live")
        database = Database(settings)
        database.initialize()
    http = JsonHttpClient(timeout=60.0, max_retries=3)
    # the entries' NBBO (Massive, as the lab measured it): a short timeout and no retry — the exits wait on this loop
    nbbo = (massive_nbbo(DeadlineJsonHttpClient(timeout=NBBO_TIMEOUT_SECONDS).get_json, settings.massive_base_url,
                         settings.massive_api_token) if settings.massive_api_token else None)
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
                        token=settings.eodhd_api_token, day=day, cache_dir=cache_dir, job=job, nbbo=nbbo)
        except Exception:
            logger.exception("R2D2 live: the session failed")
            clock_time.sleep(60)


if __name__ == "__main__":
    main()
