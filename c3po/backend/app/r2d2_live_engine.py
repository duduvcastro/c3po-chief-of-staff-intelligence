"""The live R2D2 inside the C3PO server, on the EODHD real-time stream (owner, 27/10/2026: "claro que tem que mudar
para dentro do servidor do C3PO, não quero nada rodando no GitHub"; "a cada segundo").

The rule in force grew from the one the owner chose on 26/10 (TIT-2S3; TIT-2S5-RT from 30/10): stocks that open at least 1% below the previous close,
20-session dollar volume of at least US$ 15 M, price of at least US$ 5; a buy when the last trade, checked every second,
crosses back above the session VWAP (owner 29/10; until then a minute close, the lab's candles), executed at once at the
real ask, with a quoted spread of at most 5 bps (owner 29/10; 3 bps until then), up to
15:29:59 ET — the ask and the spread of the NBBO prevailing at that instant, read from Massive as the lab measured them
(``lab/massive.py`` quote_at, ``lab/cost_real.py`` touch: at most 60 s old), the stream's quote only when Massive does
not answer, 20 positions of NAV/20, re-entry allowed after an exit. Every second each open position is checked at the real bid:
stop at -0.4% net until a step profit lock arms at +0.10% net, whose floor is the last step the peak reached (every 0.05 up
to +0.30%, every 0.10 above; owner 29/10, it was a +0.15% lock trailing the peak), every positive position sold from 15:59:30 ET; the
negatives carry to the next session. Paper only: no broker, no order. Fills, book and scan counts are the same
documents the screen already reads (``r2d2_lab_live``), written straight to the database.

Universe: the 900 most liquid US common stocks (owner 29/10; 500 until then), from EODHD's end-of-day bulk files of the
last 20 sessions; the open of each is its first regular-session trade on the stream. The trade feed carries the universe
until the candidates are fixed, then the candidates and the held names; the quote feed only the held names.
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
from threading import Event, Lock, Thread
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

import websockets

from . import r2d2_lab_live
from .market_data.eodhd_stream import EodhdRealtimeStream

logger = logging.getLogger(__name__)

NEW_YORK = ZoneInfo("America/New_York")
CONFIG = "TIT-2S5-RT"  # owner 29/10: spread <= 5 bps from 30/10 (TIT-2S3-RT until then)
STATE_TYPE = "r2d2_live_engine_state"
STATE_KEY = "TIT-2S3"  # the ONE book since 27/10: the key stays whatever rule is in force (a new key = a new book)
STREAM_GROUP = "r2d2-live"
# The stream's capacity is per account (~1,050 slots on this plan, one per name per feed; EODHD's default is 50)
# owner 29/10/2026 ~17:3x BRT: "então aumenta o universo do R2D2 para mais papéis" — 900 (it was 500): the trade feed
# carries the universe until the candidates are fixed, the quote feed only the held names (each name costs one WebSocket
# slot per feed; the account has ~1,050), so the same slots follow ~900 names
UNIVERSE_SIZE = int(os.environ.get("C3PO_R2D2_LIVE_UNIVERSE_SIZE", "900"))
ADV_DAYS = 20
MIN_ADV_DAYS = 15
FEE_SIDE = 0.00005  # 0.5 bp per side: commission and SEC/FINRA fees (the lab's cost model)
RULE = {
    # owner 29/10/2026 ~17:2x BRT: "vamos mudar para até 5 bps para amanhã também" (it was 3 bps)
    "gap_min_percent": 1.0, "adv_min_usd": 15e6, "price_min": 5.0, "slots": 20, "spread_max_bps": 5.0,
    # owner 29/10/2026 ~17:0x BRT: "a trava arma se ela chegar a 0,10%, aí a cada 0,05% ela gera uma nova trava. Se passar
    # de 0,3% de lucro a trava sobe a cada 0,10pp" — the floor ON the step reached ("no degrau") — "e coloca o stop sem
    # trava em -0,4%". Until then: stop -0.5%, a lock armed at +0.15% trailing the peak by 0.05 (0.10 before 13:51 BRT)
    "stop_percent": 0.4, "lock_min_percent": 0.10, "lock_step_percent": 0.05, "lock_wide_from_percent": 0.30,
    "lock_wide_step_percent": 0.10,
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
NBBO_STEP_BUDGET_SECONDS = 3.0  # Massive time per step's entries: the exits run on this loop; past it, the stream's quote
# Massive failed this many times IN A ROW: not asked for NBBO_PAUSE_AFTER_FAILURE_SECONDS (the stream's quote stands in).
# Until 30/10 one failure paused it 30 s; at that open a burst failure left 58 crosses without a quote (the quote feed
# carries only the held names since #516) and the exits, which mark on Massive since 30/10, would fall back to the feed
NBBO_FAILURES_BEFORE_PAUSE = 3  # the owner's instruction, 30/10 (Codex 6524471382): 3 failures in a row, a 5 s pause
NBBO_PAUSE_AFTER_FAILURE_SECONDS = 5.0
# the held names' marks (the exits), asked of Massive every second before the entries' own budget: 0.2 s above a
# request's own timeout, so an answer inside it is never left for the feed
NBBO_EXIT_BUDGET_SECONDS = 1.7
# an exit's NBBO at most this old (the entries keep the lab's 60 s): a lagging Massive never hides a stop the market printed
NBBO_EXIT_MAX_AGE_SECONDS = 10.0
# Massive requests in flight at once for one step's crosses. Asked one after the other (~0.7 s each from the host),
# the 3 s budget answered ~3 of the ~13 crosses a minute at the 29/10 open: 120 of 156 fell back to the stream's late quote
NBBO_PARALLEL = 32
# owner 29/10/2026 ~17:4x BRT: "coloca o registro por faixa de spread e quanto cada faixa teria gerado de lucro/prejuízo" —
# every signal refused by the spread limit, by band of its spread, and a shadow trade per refused name that follows the
# same exits (no money, no slot): bought at the real ask it was refused at; marked on the last trade less half that spread
# (no quote subscription for the shadows: the WebSocket slots go to the universe); closed at the session's close if open
SHADOW_BANDS = (("5_8", 8.0), ("8_10", 10.0), ("gt10", math.inf))  # the refused spreads above the 5 bps limit, in bps
SHADOW_TRADE_MAX_AGE_SECONDS = 10.0  # a shadow is marked only on a trade this recent
NBBO_MAX_DEVIATION = 0.02  # a quote whose mid is further than this from the signal's own price is another
# instrument's (a share-class or mapping error) or absurd: never bought on (pre-review of e8ce1f3)
FUTURE_TOLERANCE_SECONDS = 5.0  # a stream message stamped further ahead than this is refused (it would pin the book)
MARKS_EVERY_SECONDS = 60.0
# owner 30/10/2026: "com o papel na carteira acompanhar em 0,1 s" — between the full checks of a second, the held names
# are judged this often on the NBBO Massive pushes (the stop, the lock, T30); the full check stays once a second
FAST_EXIT_SECONDS = 0.1


# ------------------------------------------------------------------ the stream: last trade, last NBBO, session VWAP
@dataclass
class Tape:
    """One symbol's regular session on the stream: the VWAP accumulators, the open, the last trade, and the close and
    VWAP of the last COMPLETED minute (``signal_view``; the entries read the live last trade every second since 29/10)."""
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


def refusal_code(payload: str | bytes) -> int | None:
    """A feed's status frame other than 200 (EODHD answers an over-limit subscription with {"status_code": 422, "message":
    "Symbols limit reached"} and no acknowledgement otherwise): its code, else None (a trade or a quote)."""
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    if '"status_code"' not in text:
        return None
    try:
        item = json.loads(text)
        raw = item.get("status_code") if isinstance(item, dict) and "s" not in item else None
        code = int(raw) if isinstance(raw, (int, str)) else None
    except (TypeError, ValueError, AttributeError):
        return None
    return code if code is not None and code != 200 else None


class LiveEngineStream(EodhdRealtimeStream):
    """The EODHD stream (read-only use of the frozen module) keeping, per symbol, a ``Tape`` of the session being traded
    and the last quote with its bid and ask. Late messages never overwrite newer ones (Codex #500 P2-5): a trade older
    than the last one still counts in the VWAP but does not move the last price; an older quote is dropped."""

    def __init__(self, api_token: str, *, max_symbols: int = UNIVERSE_SIZE + 50) -> None:  # the universe and the held names
        super().__init__(api_token, max_symbols=max_symbols)
        self._view_lock = Lock()
        self.session: date | None = None
        self.tapes: dict[str, Tape] = {}
        self.nbbo: dict[str, tuple[float, float, datetime]] = {}
        self._pending: list[tuple[str, float, float, int, float]] | None = None
        self.restored_minute: int | None = None  # the minute of a restore: earlier minutes may miss the trades of the gap
        self._groups_version = 0  # bumped by every ``set_group``: the feed loop recomputes its subscription only then
        self._quote_symbols: frozenset[str] | None = None  # the quote feed's names (None: every grouped name, as trades)
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

    def set_quote_symbols(self, symbols: Any) -> None:
        """The names the quote feed subscribes (the held names: their exits read the bid; the entries read Massive's
        NBBO); None = every grouped name. The trade feed keeps every grouped name. A name counts one WebSocket slot per
        feed, so the universe can be almost twice as large on the same slots."""
        names = None if symbols is None else frozenset(symbols)
        with self._lock:
            before = self._quote_symbols
        if names is not None and before is not None:
            # a name entering or leaving the quote feed drops its last quote BEFORE the feed resubscribes: a quote
            # received before a gap in the subscription is never the mark of a later position (a re-buy) nor an
            # entry's fallback (pre-review of 568737c: a phantom lock or stop on a name re-bought within ~4 s)
            with self._view_lock:
                for symbol in names ^ before:
                    self.nbbo.pop(symbol, None)
        with self._lock:
            self._quote_symbols = names
            self._groups_version += 1

    def feed_symbols(self, feed: str) -> set[str]:
        """The names one feed subscribes: every grouped name for trades; for quotes, only the quote names among them."""
        with self._lock:
            desired = set(self._desired_symbols())
            quotes = self._quote_symbols
        return desired & quotes if feed == "quote" and quotes is not None else desired

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
                                desired = self.feed_symbols(feed)
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
                        refused = refusal_code(payload)
                        if refused is not None:  # e.g. 422 "Symbols limit reached": a name of this feed was not subscribed
                            logger.error("EODHD realtime %s refused a subscription: status %d", feed, refused)
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

    def live_signal(self, symbol: str) -> tuple[float, float] | None:
        """(last trade, VWAP) now — the entries' signal, read every second — or None. After a restore, a trade of the
        restore's minute or earlier may sit among the gap's missing ones: no signal until a later minute is observed live."""
        with self._view_lock:
            tape = self.tapes.get(symbol)
            if tape is None or tape.last_price is None or tape.vwap is None:
                return None
            if self.restored_minute is not None and tape.minute <= self.restored_minute:
                return None
            return tape.last_price, tape.vwap

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
    """The UNIVERSE_SIZE most liquid US common stocks at the open of ``day``: 20-session mean of close × volume ≥ US$ 15 M,
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
def shadow_band(spread_bps: float) -> str:
    """The band of a spread refused by the limit (in bps): 5_8, 8_10, gt10."""
    return next(name for name, upper in SHADOW_BANDS if spread_bps <= upper)


def shadow_line(engine: "Engine") -> str:
    """Per spread band, numbers only (published by the status workflow): signals refused, shadows closed, open and
    positive, and the net they made in USD at the real positions' size."""
    parts = []
    for name, _ in SHADOW_BANDS:
        stats = engine.state.bands.get(name) or {}
        parts.append("%s vetoed=%d closed=%d open=%d wins=%d net_usd=%.2f" % (
            name, int(stats.get("vetoed", 0)), int(stats.get("closed", 0)),
            sum(1 for row in engine.state.shadow.values() if row["band"] == name), int(stats.get("wins", 0)),
            float(stats.get("net_usd", 0.0))))
    return "R2D2 live shadow: limit_bps=%.1f %s" % (RULE["spread_max_bps"], " ".join(parts))


def lock_floor(peak: float) -> float:
    """The armed lock's floor: the last step the peak reached (owner 29/10, "no degrau"): +0.10% net, then every 0.05 up
    to +0.30%, then every 0.10 (+0.40, +0.50, ...). A peak a hair under a step (float error) still counts that step."""
    low, step = RULE["lock_min_percent"], RULE["lock_step_percent"]
    wide_from, wide_step = RULE["lock_wide_from_percent"], RULE["lock_wide_step_percent"]
    reached = peak + 1e-9  # one tolerance for the band and the step (pre-review: two made a gap just under +0.30%)
    if reached < wide_from:
        return low + step * math.floor((reached - low) / step)
    return wide_from + wide_step * math.floor((reached - wide_from) / wide_step)


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

    def exit_price(self) -> float:
        """The bid at which the rule sells now: the armed lock's floor (``lock_floor`` of the peak), else the stop —
        the level the screen shows as the position's stop (owner 29/10: "o stop não tá mexendo")."""
        floor = lock_floor(self.peak_percent or RULE["lock_min_percent"]) if self.armed else -RULE["stop_percent"]
        return self.cost_usd * (1 + floor / 100) / (self.shares * (1 - FEE_SIDE))


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
    last_signal_minute: int = -1  # minutes after midnight ET of the last minute the entries were checked in (every second)
    candidates_fixed: bool = False  # the selection at the open happened (even when it found none)
    stream_context: dict[str, dict[str, Any]] = field(default_factory=dict)  # the tapes, for a restart
    config: str = ""  # the rule the session in the state ran under (its documents keep it when the rule changes)
    shadow: dict[str, dict[str, Any]] = field(default_factory=dict)  # the open shadow trades (never published by name)
    bands: dict[str, dict[str, float]] = field(default_factory=dict)  # per spread band: refused, closed, wins, net USD
    bands_closed: dict[str, Any] = field(default_factory=dict)  # the last CLOSED session's bands: {"session", "bands"}

    def to_json(self) -> dict[str, Any]:
        return {"nav_realized": self.nav_realized, "last_session": self.last_session,
                "positions": [asdict(position) for position in self.positions.values()], "session": self.session,
                "nav_start": self.nav_start, "candidates": self.candidates, "below": self.below, "signals": self.signals,
                "fills": self.fills, "last_signal_minute": self.last_signal_minute,
                "candidates_fixed": self.candidates_fixed, "stream_context": self.stream_context, "config": self.config,
                "shadow": self.shadow, "bands": self.bands, "bands_closed": self.bands_closed}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "EngineState":
        positions = {row["symbol"]: Position(**row) for row in data.get("positions") or []}
        return cls(nav_realized=float(data["nav_realized"]), positions=positions, last_session=str(data.get("last_session") or ""),
                   session=str(data.get("session") or ""), nav_start=data.get("nav_start"),
                   candidates=dict(data.get("candidates") or {}), below=dict(data.get("below") or {}),
                   signals=int(data.get("signals") or 0), fills=list(data.get("fills") or []),
                   last_signal_minute=int(data.get("last_signal_minute", -1)),
                   candidates_fixed=bool(data.get("candidates_fixed")), stream_context=dict(data.get("stream_context") or {}),
                   config=str(data.get("config") or ""),
                   shadow=dict(data.get("shadow") or {}), bands=dict(data.get("bands") or {}),
                   bands_closed=dict(data.get("bands_closed") or {}))


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
        # what each exit check of a held name marked on: Massive's NBBO, the feed's fresh quote, or nothing (this process)
        self.exit_sources = {"massive": 0, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 0, "fast": 0}
        self.marked_moment: dict[str, datetime] = {}  # when the exits last marked each held name (the screen's marks only)
        if not self.resumed:  # a new session: the opening NAV is the last close marked at the last known prices
            state.session, state.candidates, state.below, state.signals, state.fills = day.isoformat(), {}, {}, 0, []
            state.last_signal_minute, state.candidates_fixed, state.stream_context = -1, False, {}
            state.config = CONFIG
            state.shadow, state.bands = {}, {}
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
             signal: Callable[[str], tuple[float, float] | None] | None = None,
             nbbo: Callable[[str, datetime], tuple[float, float, datetime] | None] | None = None,
             pushed: Callable[[str], tuple[float, float, datetime] | None] | None = None) -> list[dict[str, Any]]:
        """``view``: the live price and quote (exits; the entries' fallback). ``signal``: (last trade, VWAP) now (the buy
        signal, ``LiveEngineStream.live_signal``); without it, the view's last price and VWAP stand in (tests). ``nbbo``:
        (bid, ask, time) of the NBBO prevailing at the instant (Massive), or None when it does not answer. ``pushed``: a
        held name's last NBBO pushed by Massive's stream (``MassiveQuoteStream.quote``), or None."""
        local = now.astimezone(NEW_YORK).time()
        started_step = clock_time.monotonic()
        new: list[dict[str, Any]] = []
        # The exits mark on Massive's NBBO, as the entries buy on it (30/10/2026): the quote feed (EODHD) gave ASX a bid
        # 0.5% under the NBBO seconds after its buy — a stop at -0.75% the market never printed (the minute's low was above
        # the NBBO bid) — and left AMD unarmed at +0.175% net. Since the afternoon of 30/10 (owner: "já faz a troca pro
        # stream da Massive hoje") a held name's NBBO pushed by Massive's stream is read and used at ONE instant, nothing
        # in between: a quote that is no usable mark at that instant (too old, or the stream silent or reconnecting) sends
        # the name down the whole chain, never a copy taken earlier (Codex 6526033042). The chain: Massive asked at once
        # for every such name, then the feed's fresh quote, whose bid never sells alone.
        pending: list[str] = []
        for symbol in list(self.state.positions):
            position = self.state.positions[symbol]
            if pushed is None:
                pending.append(symbol)
                continue
            market = view(symbol)
            quote = pushed(symbol)
            # the effective instant, sampled after the reads that may block (the view takes the stream's lock; as the
            # entries, Codex 6499564395): the quote's age, the T30 rule and the sell's stamp read this one instant
            moment = now + timedelta(seconds=clock_time.monotonic() - started_step)
            if self._after_close(moment):  # a read that crossed 16:00 never marks nor sells (as the fast pass)
                pending.clear()
                break
            bid = exit_bid(quote, market, position, moment)
            if bid is None:
                pending.append(symbol)
                continue
            self.exit_sources["pushed"] += 1  # Massive's NBBO, pushed: counted among "massive" too
            fill = self._exit(position, market, moment, bid, "massive")
            if fill is not None:
                new.append(fill)
        answers: dict[str, tuple[float, float, datetime]] = {}
        if nbbo is not None and pending:
            answers = ask_nbbo(nbbo, pending, now + timedelta(seconds=clock_time.monotonic() - started_step),
                               budget=NBBO_EXIT_BUDGET_SECONDS)
        for symbol in pending:
            position = self.state.positions[symbol]
            market = view(symbol)
            moment = now + timedelta(seconds=clock_time.monotonic() - started_step)
            if self._after_close(moment):  # Massive's wait or a read that crossed 16:00: no mark, no sale
                break
            bid, source = exit_bid(answers.get(symbol), market, position, moment), "massive"
            if bid is None:
                if not market.quote_fresh(moment):
                    self.exit_sources["none"] += 1
                    continue
                assert market.bid is not None
                bid, source = market.bid, "stream"
            fill = self._exit(position, market, moment, bid, source)
            if fill is not None:
                new.append(fill)
        try:
            self._shadow_exits(now, view)
        except Exception:  # the measurement never breaks the step (the real exits ran above, the entries run below)
            logger.error("R2D2 live: the shadows could not be marked; the open ones are dropped")
            self.state.shadow.clear()  # once, not an error every second (pre-review of cb42462)
        # The buy signal, checked EVERY SECOND like the exits (owner 29/10/2026: "esse cheque tem que ser por segundo e
        # não por minuto"): the last trade back above the VWAP after being below it, executed at once at the real ask.
        # Until 29/10 it was the close of each completed minute (the lab's candles): a cross the minute's close no longer
        # showed was never seen.
        minute = local.hour * 60 + local.minute
        if local <= LAST_ENTRY:
            self.state.last_signal_minute = minute
            crosses: list[tuple[str, float, float]] = []  # (symbol, gap, signal price): this second's crosses, in order
            for symbol, gap in self.candidates.items():
                if symbol not in self.members:  # a restored candidate the rebuilt universe no longer lists: never bought
                    continue
                market = view(symbol)
                if signal is not None:
                    live = signal(symbol)
                    close, vwap = live if live else (None, None)
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
            # Massive is asked for every cross of the second AT ONCE, at the effective instant (Codex P2-2); each request
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
                    try:
                        self._shadow_open(symbol, ask, spread_bps, moment)
                    except Exception:  # the measurement never breaks the step
                        logger.error("R2D2 live: a shadow could not be opened")
                    continue
                if (source == "massive" and market.quote_fresh(moment) and market.bid is not None and market.ask is not None
                        and (market.ask - market.bid) / ((market.ask + market.bid) / 2) * 1e4 > RULE["spread_max_bps"]):
                    # the evidence: a buy the stream's fresh quote alone refused (a candidate without a stream quote, the
                    # usual case since the quote feed carries only the held names, is not counted)
                    self.sources["stream_would_refuse"] += 1
                new.append(self._buy(symbol, ask, gap, spread_bps, moment, source))
        return new

    def _shadow_open(self, symbol: str, ask: float, spread_bps: float, moment: datetime) -> None:
        """A signal refused by the spread limit: counted in its band, and followed as a shadow trade unless the name is
        held or already followed."""
        band = shadow_band(spread_bps)
        stats = self.state.bands.setdefault(band, {"vetoed": 0, "closed": 0, "wins": 0, "net_usd": 0.0})
        stats["vetoed"] += 1
        if symbol in self.state.shadow or symbol in self.state.positions:
            return
        self.state.shadow[symbol] = {"band": band, "ask": ask, "spread_bps": spread_bps, "size_usd": self.state.nav_realized / RULE["slots"],
                                     "peak": None, "armed": False, "last_net": None, "opened_at": moment.isoformat()}

    def _shadow_close(self, symbol: str, net: float) -> None:
        row = self.state.shadow.pop(symbol)
        stats = self.state.bands.setdefault(row["band"], {"vetoed": 0, "closed": 0, "wins": 0, "net_usd": 0.0})
        stats["closed"] += 1
        stats["wins"] += 1 if net > 0 else 0
        stats["net_usd"] += row["size_usd"] * net / 100

    def _shadow_exits(self, now: datetime, view: Callable[[str], MarketView]) -> None:
        """The same exits as a position (stop, step lock, positives sold in the last 30 s), on the last trade less half
        the spread the shadow was refused at — an estimate of the bid (the shadows have no quote subscription)."""
        late = now.astimezone(NEW_YORK).time() >= SELL_POSITIVES_FROM
        for symbol, row in list(self.state.shadow.items()):
            market = view(symbol)
            if market.price is None or market.trade_at is None or (now - market.trade_at).total_seconds() > SHADOW_TRADE_MAX_AGE_SECONDS:
                continue
            bid = market.price * (1 - row["spread_bps"] / 2 / 1e4)
            net = (bid * (1 - FEE_SIDE) / (row["ask"] * (1 + FEE_SIDE)) - 1) * 100
            row["last_net"] = net
            row["peak"] = net if row["peak"] is None else max(row["peak"], net)
            if net >= RULE["lock_min_percent"]:
                row["armed"] = True
            if (net <= -RULE["stop_percent"] or (row["armed"] and net <= lock_floor(row["peak"])) or (late and net > 0)):
                self._shadow_close(symbol, net)

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

    def _after_close(self, moment: datetime) -> bool:
        """At or past this session's close (16:00 New York on its own date): an exit check never marks nor sells then —
        every path samples its effective instant after its reads and asks this first (Codex 6527492839)."""
        return moment >= datetime.combine(self.day, SESSION_CLOSE, tzinfo=NEW_YORK)

    def marks(self) -> list[dict[str, Any]]:
        """The held names as the exits last marked them, for the screen (migration 055; display only, never read back): the
        bid, the net at that bid, the lock armed or not, the level the rule sells at and the instant of the mark."""
        rows = []
        for symbol, position in sorted(self.state.positions.items()):
            if position.last_mark is None:
                continue
            marked = self.marked_moment.get(symbol)
            # the level the rule sells at, as the net of a sale there: the lock's floor once armed, else the stop
            level = lock_floor(position.peak_percent or RULE["lock_min_percent"]) if position.armed else -RULE["stop_percent"]
            rows.append({"symbol": symbol, "bid": position.last_mark, "net_percent": position.net_percent(position.last_mark),
                         "armed": position.armed, "stop_price": position.exit_price(), "stop_percent": level,
                         "marked_at": marked.isoformat() if marked is not None else None})
        return rows

    def fast_exits(self, now: datetime, view: Callable[[str], MarketView],
                   pushed: Callable[[str], tuple[float, float, datetime] | None]) -> list[dict[str, Any]]:
        """Between the full checks of a second (owner 30/10/2026: "com o papel na carteira acompanhar em 0,1 s"): every
        held name with a usable NBBO pushed by Massive is judged on it, read and used at one instant as in ``step``; a name
        without one waits for the next full check (Massive asked, then the feed). Never the entries, never the shadows."""
        started = clock_time.monotonic()
        fills: list[dict[str, Any]] = []
        for symbol in list(self.state.positions):
            position = self.state.positions[symbol]
            market = view(symbol)
            quote = pushed(symbol)
            moment = now + timedelta(seconds=clock_time.monotonic() - started)
            # the close checked again at the effective instant, after the reads that may block: a read that crossed
            # 16:00 never marks nor sells (Codex 6527492839)
            if self._after_close(moment):
                break
            bid = exit_bid(quote, market, position, moment)
            if bid is None:
                continue
            fill = self._exit(position, market, moment, bid, "fast")
            if fill is not None:
                fills.append(fill)
        return fills

    def _exit(self, position: Position, market: MarketView, moment: datetime, bid: float, source: str) -> dict[str, Any] | None:
        """One exit check of a held name on ``bid`` (``source``: "massive" for Massive's NBBO, pushed or asked; "fast" for
        the pushed NBBO between the full checks; "stream" for the feed's quote): the mark, the peak and the arming, then a
        sale on the stop, the lock or the T30 rule. A sale
        on the feed's bid stands only when the name's fresh last trade confirms it (the owner, 30/10, Codex 6525745563)."""
        self.exit_sources[source] += 1
        net = position.net_percent(bid)
        position.last_mark = bid
        self.marked_moment[position.symbol] = moment
        position.peak_percent = net if position.peak_percent is None else max(position.peak_percent, net)
        if net >= RULE["lock_min_percent"]:  # armed by the net now, never by a peak stored under an earlier rule
            position.armed = True
        reason = None
        if net <= -RULE["stop_percent"]:
            reason = "hard_stop"
        elif position.armed and net <= lock_floor(position.peak_percent):
            reason = "lock"
        elif moment.astimezone(NEW_YORK).time() >= SELL_POSITIVES_FROM and net > 0:
            reason = "t30_positive"
        if reason and source == "stream" and not trade_confirms(position, market, moment, reason):
            # the feed's bid alone never sells (30/10: off the market by 0.5%): the name's fresh last trade must be at the
            # same level, else Massive decides at the next check. A confirmed sale is booked at the feed's quoted bid,
            # never at an estimate (Codex 6525240030 P2-1)
            self.exit_sources["unconfirmed"] += 1
            return None
        return self._sell(position, bid, net, reason, moment) if reason else None

    def _sell(self, position: Position, bid: float, net: float, reason: str, now: datetime) -> dict[str, Any]:
        pnl = position.cost_usd * net / 100
        self.state.nav_realized += pnl
        del self.state.positions[position.symbol]
        self.marked_moment.pop(position.symbol, None)  # a re-buy is shown from its own marks
        # a new entry needs a new dip below the VWAP, seen in a check: the same step never sells at the stream's bid and
        # buys back at once on a last trade still above the VWAP (pre-review of 81cf1ae P2-B)
        self.below[position.symbol] = False
        held = " (posição de %d pregão(ões) atrás)" % position.days_held if position.days_held else ""
        fill = {"side": "SELL", "symbol": position.symbol, "market": position.market, "quantity": position.shares,
                "price": bid, "executed_at": now.isoformat(), "fees_usd": position.shares * bid * FEE_SIDE,
                "realized_pnl_usd": pnl, "realized_return_percent": net,
                "reason": "venda: %s, %+.3f%% líquido de custos%s" % (r2d2_lab_live_reason(reason), net, held)}
        self.fills.append(fill)
        return fill

    def close_session(self) -> None:
        for symbol, row in list(self.state.shadow.items()):  # the shadows never carry: closed at their last mark
            if row.get("last_net") is None:
                self.state.shadow.pop(symbol)
            else:
                self._shadow_close(symbol, row["last_net"])
        # the day's final per band, kept past the next session's reset (pre-review of 65ceb97 D1)
        self.state.bands_closed = {"session": self.day.isoformat(), "bands": json.loads(json.dumps(self.state.bands))}
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
                              "stop_price": position.exit_price(),  # the lock's floor once armed, else the stop
                              "opened_at": position.opened_at})
        cash = self.state.nav_realized - sum(position.cost_usd for position in self.state.positions.values())
        return {"nav_start_usd": self.nav_start, "nav_usd": self.state.nav_realized + unrealized,
                "realized_nav_usd": self.state.nav_realized, "cash_usd": cash, "as_of": now.isoformat(), "positions": positions}

    def document(self, now: datetime, *, config: str | None = None) -> dict[str, Any]:
        """``config``: the rule the day ran under; default: the session's own (``state.config``), else the one in force."""
        config = config or self.state.config or CONFIG
        trades = []
        for index, fill in enumerate(self.fills):
            stamp = int(datetime.fromisoformat(fill["executed_at"]).timestamp())
            trades.append({"id": "%s:%s:%s:%s:%d:%d" % (config, self.day.isoformat(), fill["symbol"], fill["side"].lower(), stamp, index),
                           **{key: _rounded(key, value) for key, value in fill.items()}})
        sells = sum(1 for fill in self.fills if fill["side"] == "SELL")
        return {"schema": r2d2_lab_live.SCHEMA, "day": self.day.isoformat(), "config": config, "trades": trades,
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
        state = EngineState.from_json(outputs)
        if not state.config:  # a checkpoint written before the field: its own rule, recorded in its inputs (Codex 6508087909)
            state.config = str(((snapshot or {}).get("inputs") or {}).get("config") or "")
        return state
    seeded = opening_nav()
    if seeded is None:
        raise RuntimeError("no engine state and no lab book to start from")
    return seeded


def save_state(database: Any, state: EngineState, now: datetime) -> None:
    # version 3 from 30/10/2026 (owner, 29/10): the stop at -0.4% and the step lock from +0.10%; version 2 (29/10
    # afternoon) was the lock trailing the peak by 0.05, version 1 before it
    methodology = database.ensure_methodology_version(
        "r2d2_live_engine", 3, {"rule": RULE, "config": CONFIG, "fee_side": FEE_SIDE, "universe_size": UNIVERSE_SIZE},
        "The live R2D2 inside the C3PO server on the EODHD real-time stream (owner 27/10/2026); entries every second, "
        "the stop at -0.4%, the step profit lock from +0.10% and the spread at most 5 bps (owner 29/10/2026)")
    database.save_analysis_snapshot(STATE_TYPE, STATE_KEY, methodology, {"config": state.config or CONFIG}, state.to_json(), now)


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


def publish(database: Any, engine: Engine, now: datetime, *, as_of: datetime | None = None,
            config: str | None = None) -> dict[str, Any]:
    return r2d2_lab_live.store(database, engine.document(as_of or now, config=config), now=now, max_trades=ENGINE_MAX_TRADES)


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
    stored_doc = (database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, prior) or {}).get("outputs") or {}
    stored = stored_doc.get("trades")
    # the day keeps the rule it ran under: a rule changed since then (a new CONFIG) never rewrites it (pre-review b84a436),
    # even when its public document is missing (a publish that failed after the checkpoint: Codex 6508087909)
    config = str(stored_doc.get("config") or state.config or "")
    if state.fills and not config:  # never written under a rule it did not run under; the close and its save still happen
        logger.error("R2D2 live: previous session %s has no recorded rule; not republished", prior)
    pending = bool(state.fills) and bool(config) and stored != engine.document(close_at, config=config)["trades"]
    if not unclosed and not pending:
        return False
    if unclosed:
        save_state(database, state, now)
    if pending:
        try:
            publish(database, engine, now, as_of=close_at, config=config)
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
    ``NBBO_MAX_DEVIATION`` of the signal's own price (another instrument's or an absurd quote is never bought on)."""
    bid, ask, _ = quote
    if not (math.isfinite(bid) and math.isfinite(ask) and math.isfinite(close)) or not 0 < bid <= ask <= r2d2_lab_live.MAX_PRICE:
        return False
    return close > 0 and abs((bid + ask) / 2 / close - 1) <= NBBO_MAX_DEVIATION


def exit_bid(quote: tuple[float, float, datetime] | None, market: "MarketView", position: Position,
             moment: datetime) -> float | None:
    """Massive's bid a held name is marked on, or None (the feed's quote stands in): a usable NBBO of that very name —
    finite, ordered, within the screen's price bound — at most ``NBBO_EXIT_MAX_AGE_SECONDS`` old. No distance to an
    earlier price: a percentage filter refused a real move of the name against its own stale mark and kept the stop off
    (Codex 6525240030 P2-2); the NBBO prevailing at the instant is the market a sale meets."""
    if quote is None:
        return None
    bid, ask, quoted_at = quote
    age = (moment - quoted_at).total_seconds()
    if (not (math.isfinite(bid) and math.isfinite(ask)) or not 0 < bid <= ask <= r2d2_lab_live.MAX_PRICE
            or not -FUTURE_TOLERANCE_SECONDS <= age <= NBBO_EXIT_MAX_AGE_SECONDS):
        return None
    return bid


def trade_confirms(position: Position, market: "MarketView", moment: datetime, reason: str) -> bool:
    """A sale the feed's bid triggers stands only when the name's fresh last trade (at most ``QUOTE_MAX_AGE_SECONDS``
    old) is at the same level: at or under the stop, at or under the lock's floor, or positive for the T30 rule."""
    if (market.price is None or market.trade_at is None
            or not -FUTURE_TOLERANCE_SECONDS <= (moment - market.trade_at).total_seconds() <= QUOTE_MAX_AGE_SECONDS):
        return False
    net = position.net_percent(market.price)
    if reason == "hard_stop":
        return net <= -RULE["stop_percent"]
    if reason == "lock":
        return net <= lock_floor(position.peak_percent if position.peak_percent is not None else RULE["lock_min_percent"])
    return net > 0


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
    BRK.B). After ``NBBO_FAILURES_BEFORE_PAUSE`` failures in a row Massive is not asked for
    ``NBBO_PAUSE_AFTER_FAILURE_SECONDS``: the stream stands in."""
    from threading import Lock
    from urllib.parse import quote as quoted
    paused_until, failures, lock = [0.0], [0], Lock()  # one step's requests run in parallel threads

    def nbbo(symbol: str, now: datetime) -> tuple[float, float, datetime] | None:
        if monotonic() < paused_until[0]:
            return None
        try:
            payload = get_json(f"{base_url.rstrip('/')}/v3/quotes/{quoted(symbol.replace('-', '.'), safe='')}",
                               params={"timestamp.lte": int(now.timestamp() * 1e9), "order": "desc", "sort": "timestamp",
                                       "limit": 1, "apiKey": token})
            row = (payload.get("results") or [None])[0] if isinstance(payload, dict) else None
        except Exception:
            with lock:
                failures[0] += 1
                if failures[0] >= NBBO_FAILURES_BEFORE_PAUSE:
                    paused_until[0], failures[0] = monotonic() + NBBO_PAUSE_AFTER_FAILURE_SECONDS, 0
            return None
        with lock:
            failures[0] = 0  # Massive answered: whatever it said, it is up
        if not isinstance(row, dict):
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
             at: datetime, *, budget: float | None = None) -> dict[str, tuple[float, float, datetime]]:
    """Every cross of one step asked of Massive at once (up to ``NBBO_PARALLEL`` in flight), each at ``at``: the
    answers that came within ``budget`` (default ``NBBO_STEP_BUDGET_SECONDS``) of the first asking (starting the threads counts). One that
    has not answered by then is never waited for (its thread ends on its own request's deadline) and one that raised
    is no answer: the stream's quote stands in."""
    deadline = clock_time.monotonic() + (NBBO_STEP_BUDGET_SECONDS if budget is None else budget)
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


MASSIVE_STREAM_URL = "wss://socket.massive.com/stocks"
MASSIVE_STREAM_ALIVE_SECONDS = 2.0  # the pushed NBBO is read only while the socket delivered something this recently
MASSIVE_STREAM_STATES = ("idle", "connecting", "connected", "error", "stopped")
MASSIVE_STREAM_BACKOFF_SECONDS = (3.0, 60.0)  # a reconnect waits 3 s, doubling up to 60 s while it keeps failing
# the websockets library's own logger for this socket: disabled, never a frame (the auth frame carries the key), as the
# V2 transport does (r2d2_v2_massive_transport); main() runs at INFO today, this holds whatever the level becomes
_MASSIVE_SOCKET_LOGGER = logging.Logger("r2d2.live.massive-quotes")
_MASSIVE_SOCKET_LOGGER.disabled = True


class MassiveQuoteStream:
    """The NBBO of the held names, pushed by Massive (owner 30/10/2026: "já faz a troca pro stream da Massive hoje e
    para o nosso servidor"). One WebSocket (the quotes channel ``Q.``) follows the names the engine holds and keeps each
    one's last NBBO (bid, ask, SIP time) in memory; the exits read it at once instead of asking Massive every second
    (~0.1 s late against ~0.3-0.7 s per request: the lab's ws_probe, 30/10 run 41070059948). The account allows one such
    connection and this process holds it. The key travels only in the auth frame: never in the URL, a log or an error."""

    def __init__(self, api_key: str, url: str = MASSIVE_STREAM_URL) -> None:
        self.api_key, self.url = api_key, url
        self._lock = Lock()
        self._symbols: frozenset[str] = frozenset()
        self._spelled: dict[str, str] = {}  # Massive's spelling (BRK.B) -> the engine's (EODHD's BRK-B)
        self._version = 0
        self._quotes: dict[str, tuple[float, float, datetime]] = {}
        self._last_message = 0.0  # monotonic instant of the socket's last message
        self.status = "idle"
        self.messages = 0
        self.lag_ms = 0
        self.lag_max_ms = 0
        self.reconnects = 0
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=lambda: asyncio.run(self._run()), name="massive-quotes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_symbols(self, symbols: Any) -> None:
        """The names to follow (the held ones). A name entering or leaving drops its last NBBO first: a quote from before
        a gap in the subscription is never the mark of a later position (as the quote feed, pre-review of 568737c)."""
        names = frozenset(symbols)
        with self._lock:
            for symbol in names ^ self._symbols:
                self._quotes.pop(symbol, None)
            self._symbols = names
            self._spelled = {symbol.replace("-", "."): symbol for symbol in names}
            self._version += 1

    def quote(self, symbol: str) -> tuple[float, float, datetime] | None:
        """The name's last pushed NBBO, or None while the socket is not connected or has been silent for
        ``MASSIVE_STREAM_ALIVE_SECONDS`` (Massive is then asked, as before)."""
        with self._lock:
            if self.status != "connected" or clock_time.monotonic() - self._last_message > MASSIVE_STREAM_ALIVE_SECONDS:
                return None
            return self._quotes.get(symbol)

    def take_gauges(self) -> tuple[int, int, int, int]:
        """(quotes recorded, last lag ms, worst lag ms, names followed) since the last call; both counts reset."""
        with self._lock:
            taken = self.messages, self.lag_ms, self.lag_max_ms, len(self._symbols)
            self.messages, self.lag_max_ms = 0, 0
        return taken

    def _record(self, raw: Any) -> None:
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return
        received = clock_time.time() * 1000
        with self._lock:
            self._last_message = clock_time.monotonic()
            for item in payload if isinstance(payload, list) else [payload]:
                spelled = item.get("sym") if isinstance(item, dict) and item.get("ev") == "Q" else None
                symbol = self._spelled.get(spelled) if isinstance(spelled, str) else None
                if symbol is None:
                    continue
                try:
                    bid, ask, stamp = float(item.get("bp") or 0.0), float(item.get("ap") or 0.0), float(item.get("t") or 0)
                except (TypeError, ValueError):
                    continue
                if not (math.isfinite(bid) and math.isfinite(ask) and 0 < stamp <= received + FUTURE_TOLERANCE_SECONDS * 1000):
                    continue
                quoted_at = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
                held = self._quotes.get(symbol)
                if held is not None and held[2] > quoted_at:  # an update older than the one held never replaces it
                    continue
                # kept as received, even crossed or one-sided: exit_bid refuses it and the name is asked of Massive — a
                # last good quote never outlives the market that replaced it (pre-review of 20002f04 P2-3)
                self._quotes[symbol] = (bid, ask, quoted_at)
                self.messages += 1
                self.lag_ms = int(received - stamp)
                self.lag_max_ms = max(self.lag_max_ms, self.lag_ms)

    def _forget(self) -> None:
        """Every connection starts blind: no quote and no message from before it is ever served as live (pre-review of
        20002f04 P1-2: a reconnect inside the 5 s window re-served the pre-drop quotes)."""
        with self._lock:
            self._quotes.clear()
            self._last_message = 0.0

    async def _run(self) -> None:
        backoff = MASSIVE_STREAM_BACKOFF_SECONDS[0]
        while not self._stop.is_set():
            self.status = "connecting"
            self._forget()
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20, close_timeout=2,
                                              max_size=4_000_000, logger=_MASSIVE_SOCKET_LOGGER) as socket:
                    await asyncio.wait_for(socket.recv(), timeout=10)  # the server's "connected" status
                    await asyncio.wait_for(socket.send(json.dumps({"action": "auth", "params": self.api_key})), timeout=2)
                    answer = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                    if not any(isinstance(item, dict) and item.get("status") == "auth_success"
                               for item in (answer if isinstance(answer, list) else [answer])):
                        raise PermissionError("not authorized")
                    self.status = "connected"
                    backoff = MASSIVE_STREAM_BACKOFF_SECONDS[0]
                    subscribed: set[str] = set()
                    version = -1  # a new connection subscribes from scratch
                    while not self._stop.is_set():
                        if version != self._version:
                            with self._lock:
                                version, desired = self._version, {symbol.replace("-", ".") for symbol in self._symbols}
                            removed, added = sorted(subscribed - desired), sorted(desired - subscribed)
                            if removed:
                                await asyncio.wait_for(socket.send(json.dumps(
                                    {"action": "unsubscribe", "params": ",".join("Q." + name for name in removed)})), timeout=2)
                            if added:
                                await asyncio.wait_for(socket.send(json.dumps(
                                    {"action": "subscribe", "params": ",".join("Q." + name for name in added)})), timeout=2)
                            subscribed = desired
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1)
                        except TimeoutError:
                            continue
                        self._record(raw)
            except Exception as exc:  # the type only: a server's or a library's text never reaches the logs
                if self._stop.is_set():
                    break
                self._forget()
                self.status = "error"
                self.reconnects += 1
                logger.warning("Massive stream reconnect: %s", type(exc).__name__)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MASSIVE_STREAM_BACKOFF_SECONDS[1])
        self._forget()
        self.status = "stopped"


def massive_line(massive: MassiveQuoteStream, engine: "Engine") -> str:
    """The pushed NBBO's health, numbers and a closed set of states only (published by the status workflow)."""
    quotes, lag, worst, names = massive.take_gauges()
    return ("R2D2 live massive: state=%s symbols=%d quotes=%d lag_ms=%d lag_max_ms=%d pushed=%d fast=%d reconnects=%d"
            % (massive.status if massive.status in MASSIVE_STREAM_STATES else "other", names, quotes, lag, worst,
               engine.exit_sources["pushed"], engine.exit_sources["fast"], massive.reconnects))


MARKS_RETRY_SECONDS = 5.0  # after a failed write of the screen's marks, the writer waits this long before the next one


class MarksWriter:
    """The screen's marks written OFF the exits' loop (pre-review of 62bdbd3b P1-2: the loop waited on a database commit
    up to ten times a second): the loop only hands over its latest marks; one thread writes the newest it holds — never a
    queue — and after a failure waits MARKS_RETRY_SECONDS. A failure is logged once, and its recovery once."""

    def __init__(self, write: Callable[[str, datetime, list[dict[str, Any]]], Any]) -> None:
        self._write = write
        self._lock = Lock()
        self._latest: tuple[str, datetime, list[dict[str, Any]]] | None = None
        self._ready, self._stop = Event(), Event()
        self.failures = 0
        self._thread = Thread(target=self._run, name="r2d2-live-marks", daemon=True)
        self._thread.start()

    def submit(self, session: str, as_of: datetime, marks: list[dict[str, Any]]) -> None:
        with self._lock:
            self._latest = (session, as_of, marks)
        self._ready.set()

    def stop(self) -> None:
        self._stop.set()
        self._ready.set()

    def _run(self) -> None:
        failing = False
        while not self._stop.is_set():
            self._ready.wait()
            self._ready.clear()
            with self._lock:
                latest, self._latest = self._latest, None
            if latest is None or self._stop.is_set():
                continue
            try:
                self._write(*latest)
            except Exception:  # noqa: BLE001 - display only: the exits never depend on it
                self.failures += 1
                if not failing:
                    logger.error("R2D2 live: the screen's marks could not be written")
                failing = True
                self._stop.wait(MARKS_RETRY_SECONDS)
                continue
            if failing:
                logger.info("R2D2 live: the screen's marks are written again")
            failing = False


def feed_line(stream: Any, engine: "Engine") -> str:
    """How late the feed is and why signals did not buy: numbers only (published by the status workflow). Resets the
    worst lag of the interval."""
    take = getattr(stream, "take_gauges", None)
    lag, worst, count = take() if take is not None else ({}, {}, {})
    skips, sources = engine.skips, engine.sources
    return ("R2D2 live feed: trade_messages=%d quote_messages=%d trade_lag_ms=%d quote_lag_ms=%d trade_lag_max_ms=%d "
            "quote_lag_max_ms=%d skips held=%d slots=%d noquote=%d stale=%d spread=%d late=%d implausible=%d "
            "nbbo massive=%d stream=%d unanswered=%d mismatch=%d stream_would_refuse=%d exits massive=%d stream=%d none=%d unconfirmed=%d"
            % (int(count.get("trade", 0)), int(count.get("quote", 0)), int(lag.get("trade", 0)), int(lag.get("quote", 0)),
               int(worst.get("trade", 0)), int(worst.get("quote", 0)),
               skips["held"], skips["slots"], skips["noquote"], skips["stale"], skips["spread"], skips["late"], skips["implausible"],
               sources["massive"], sources["stream"], sources["unanswered"], sources["mismatch"], sources["stream_would_refuse"],
               engine.exit_sources["massive"], engine.exit_sources["stream"], engine.exit_sources["none"],
               engine.exit_sources["unconfirmed"]))


def run_session(*, stream: LiveEngineStream, database: Any, get_json: Callable[..., Any], base_url: str, token: str,
                day: date, cache_dir: Path, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                sleep: Callable[[float], None] = clock_time.sleep, job: Callable[[], Any] | None = None,
                nbbo: Callable[[str, datetime], tuple[float, float, datetime] | None] | None = None,
                massive: MassiveQuoteStream | None = None) -> EngineState:
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
    quotes_for = getattr(stream, "set_quote_symbols", None)
    if quotes_for is not None:  # BEFORE the group: the quote feed never sees the whole universe, even for an instant
        quotes_for(set(state.positions))  # the quote feed: the held names only (their exits); the entries read Massive
    if massive is not None:
        massive.set_symbols(set(state.positions))  # Massive's pushed NBBO: the held names (the exits)
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
    signal = getattr(stream, "live_signal", None)

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
    # once the candidates are fixed the trade feed needs only them and the held names (fewer messages, less lag)
    stream.set_group(STREAM_GROUP, subscription([member for member in universe if member.symbol in engine.candidates],
                                                engine.state.positions), priority=200)
    held = set(engine.state.positions)
    guarded(lambda: commit(now()))
    last_marks = last_lines = clock_time.monotonic()
    marks_writer = MarksWriter(lambda session, as_of, marks: guarded(lambda: database.save_r2d2_live_marks(session, as_of, marks)))

    def write_marks() -> None:
        """The engine's marks for the screen (owner 30/10: the screen shows what the robot decides on, every 0.1 s),
        handed to the writer stamped with the instant of the hand-over. Display only: the loop never waits on it."""
        marks_writer.submit(day.isoformat(), now(), engine.marks())
    try:
        while now() < at(SESSION_CLOSE):
            moment = now()
            began = clock_time.monotonic()
            fills = engine.step(moment, stream.view, signal, nbbo, pushed=massive.quote if massive is not None else None)
            if set(engine.state.positions) != held:  # a buy or a sale: the quote feeds follow
                held = set(engine.state.positions)
                if quotes_for is not None:
                    quotes_for(held)
                if massive is not None:
                    massive.set_symbols(held)
            if fills or clock_time.monotonic() - last_marks >= MARKS_EVERY_SECONDS:
                guarded(lambda: commit(moment))
                last_marks = clock_time.monotonic()
            write_marks()
            # the heartbeat and the feed line on their own clock: with entries checked every second fills come often, and
            # the skip and Massive counts must still come every minute
            if clock_time.monotonic() - last_lines >= MARKS_EVERY_SECONDS:
                logger.info("%s", heartbeat(stream, engine, moment))
                logger.info("%s", feed_line(stream, engine))
                logger.info("%s", shadow_line(engine))
                if massive is not None:
                    logger.info("%s", massive_line(massive, engine))
                last_lines = clock_time.monotonic()
            # between the full checks, the held names on Massive's pushed NBBO every FAST_EXIT_SECONDS (owner 30/10)
            while massive is not None and engine.state.positions and clock_time.monotonic() - began + FAST_EXIT_SECONDS < 1.0:
                sleep(FAST_EXIT_SECONDS)
                instant = now()
                if instant >= at(SESSION_CLOSE):  # never a check past the close (pre-review of e1149ca5 P1)
                    break
                fast = engine.fast_exits(instant, stream.view, massive.quote)
                write_marks()  # the screen follows every tenth of a second too (owner 30/10: "atualizada em 0,1 s")
                if fast:
                    if set(engine.state.positions) != held:  # a sale: the quote feeds follow
                        held = set(engine.state.positions)
                        if quotes_for is not None:
                            quotes_for(held)
                        massive.set_symbols(held)
                    stamp = now()
                    guarded(lambda: commit(stamp))
                    last_marks = clock_time.monotonic()
            # one pass a second: a step that waited on Massive does not add a whole second more before the exits run again
            sleep(max(0.0, 1.0 - (clock_time.monotonic() - began)))
    finally:
        marks_writer.stop()
    engine.close_session()
    if massive is not None:
        massive.set_symbols(())  # nothing held is followed past the close
    guarded(lambda: commit(now()))
    logger.info("%s", shadow_line(engine))  # the day's final per band: the T30 and the close's shadows included
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
            "today_nav": book.get("nav_usd"), "today_book_as_of": book.get("as_of"),
            "spread_bands": {name: {key: round(float(value), 2) for key, value in stats.items()}
                             for name, stats in (state.get("bands") or {}).items()},
            "spread_bands_last_session": {"session": (state.get("bands_closed") or {}).get("session"),
                                          "bands": {name: {key: round(float(value), 2) for key, value in stats.items()}
                                                    for name, stats in ((state.get("bands_closed") or {}).get("bands") or {}).items()}}}


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
    massive = MassiveQuoteStream(settings.massive_api_token) if settings.massive_api_token else None
    if massive is not None:
        massive.start()
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
                        token=settings.eodhd_api_token, day=day, cache_dir=cache_dir, job=job, nbbo=nbbo, massive=massive)
        except Exception:
            logger.exception("R2D2 live: the session failed")
            clock_time.sleep(60)


if __name__ == "__main__":
    main()
