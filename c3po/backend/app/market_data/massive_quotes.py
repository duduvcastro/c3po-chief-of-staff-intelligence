"""The screens' live US prices from Massive's snapshot, in place of EODHD's WebSocket (owner 02/11/2026: "eliminar a
EODHD"; 03/11: the WebSockets add-on goes).

EODHD counts two WebSocket slots per name (``ws/us`` and ``ws/us-quote``) and its plan without the add-on has 50, fewer
than the screens' names. Massive's snapshot answers up to ``CHUNK`` names in one REST request, at no cost per call, so
the screens poll it while one of them is open (a group no screen renewed for ``GROUP_IDLE_SECONDS`` is dropped) and the
regular session runs (the screens show no other tick: ``usable_display_tick``). The interface and the ticks are the
EODHD stream's (``set_group``, ``quote``, ``bars``, ``EodhdStreamQuote``), so the screens read it unchanged. No WebSocket
is opened: the engine's Massive connection stays the account's only one.

A tick is shown only while Massive keeps answering for its name (``FRESH_SECONDS``): after an idle spell or during an
outage the screens fall back to their REST prices instead of an old tick marked live (pre-review of 0b2fe0fd). The last
price is the last lit-exchange trade of the regular session, as the engine reads its tapes: an off-exchange (FINRA
ADF/TRF) or a Form T print never becomes it. Known limit: a preferred share spelled ``BAC-PL`` by EODHD is ``BACpL`` at
Massive and gets no live price."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import logging
import math
from threading import Event, RLock, Thread
from time import monotonic
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import httpx

from .eodhd_stream import EodhdRealtimeStream, EodhdStreamQuote
from .http import JsonHttpClient


NEW_YORK = ZoneInfo("America/New_York")
POLL_SECONDS = 3.0  # the screens refresh every 3 s while a US price can be live (realtime.STREAM_REFRESH_SECONDS)
CLOSED_POLL_SECONDS = 30.0  # outside the regular session nothing is asked: the loop only looks at the clock
MAX_BACKOFF_SECONDS = 60.0  # failed rounds in a row double the pause up to this (a 429 is not hammered)
GROUP_IDLE_SECONDS = 600.0  # a group no screen renewed for 10 min is dropped, with its names' ticks: nobody is looking
FRESH_SECONDS = 15.0  # a tick is shown while a successful round answered for its name this recently (5 rounds)
CHUNK = 100  # names per snapshot request
REQUEST_TIMEOUT_SECONDS = 4.0
HEARTBEAT_SECONDS = 600.0
OFF_EXCHANGE = 4  # Massive's exchange id of the FINRA facilities (ADF/TRFs), as r2d2_live_engine.MASSIVE_OFF_EXCHANGE
EXTENDED_HOURS = frozenset({12, 13})  # Form T / extended-hours conditions, as r2d2_live_engine.MASSIVE_EXTENDED_HOURS
# Without a Massive token the api falls back to EODHD's stream, capped so its names (two slots each) and the engine's held
# names (at most 20, quotes only) fit the 50 slots of EODHD's plan without the WebSockets add-on
EODHD_FALLBACK_MAX_SYMBOLS = 15
LABEL = "Massive Real-Time"
EODHD_LABEL = "EODHD Real-Time WebSocket"
STATES = ("stopped", "idle", "closed", "connected", "error")

# The api runs under uvicorn, whose logging config leaves app loggers without a handler (only warnings reach stderr):
# the count-only heartbeat gets its own, so the status workflow can read it. Numbers and a closed state set only.
heartbeat = logging.getLogger("c3po.screen_quotes")
if not heartbeat.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    heartbeat.addHandler(_handler)
    heartbeat.setLevel(logging.INFO)
    heartbeat.propagate = False


class LiveQuoteStream(Protocol):
    """What the screens read from a live US source: EODHD's WebSocket stream or Massive's snapshot."""

    max_symbols: int

    def set_group(self, name: str, symbols: list[str], *, priority: int = 50) -> None: ...

    def quote(self, symbol: str) -> EodhdStreamQuote | None: ...

    def bars(self, symbol: str, *, limit: int = 180) -> list[dict[str, Any]]: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


def live_label(stream: Any) -> str:
    """The provider a screen names for a live tick: the source's own label, EODHD's for its stream (frozen module)."""
    return str(getattr(stream, "label", "") or EODHD_LABEL)


@lru_cache(maxsize=1)
def _calendar() -> Any:
    return xcals.get_calendar("XNYS")


def regular_session(moment: datetime) -> bool:
    try:
        return bool(_calendar().is_open_on_minute(moment))
    except (ValueError, TypeError, KeyError):
        return False


def _clean(symbol: str) -> str:
    return symbol.strip().upper().removesuffix(".US")


def _lit(trade: dict[str, Any]) -> bool:
    """A trade the screens may show as the last price: printed on an exchange, inside the session (not Form T)."""
    if trade.get("trfi") is not None or trade.get("x") == OFF_EXCHANGE:
        return False
    conditions = trade.get("c")
    return not (isinstance(conditions, list) and any(code in EXTENDED_HOURS for code in conditions))


class MassiveSnapshotStream:
    """Polls Massive's snapshot for the names the screens grouped; keeps the last lit trade of each as a display tick."""

    label = LABEL

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        get_json: Callable[..., Any],
        max_symbols: int = 550,
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        is_open: Callable[[datetime], bool] = regular_session,
        idle_clock: Callable[[], float] = monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.max_symbols = max_symbols
        self._get_json = get_json
        self._poll_seconds = poll_seconds
        self._clock = clock
        self._is_open = is_open
        self._idle_clock = idle_clock
        self._lock = RLock()
        self._groups: dict[str, tuple[int, float, tuple[str, ...]]] = {}
        self._quotes: dict[str, EodhdStreamQuote] = {}
        self._answered: dict[str, float] = {}  # name -> idle_clock() of the last successful round that answered for it
        self._state = "stopped"
        self._error = ""
        self._failed_rounds = 0
        self._counts = {"polls": 0, "failures": 0, "ticks": 0}
        self._stop = Event()
        self._thread: Thread | None = None

    def set_group(self, name: str, symbols: list[str], *, priority: int = 50) -> None:
        cleaned = tuple(dict.fromkeys(_clean(symbol) for symbol in symbols if symbol and symbol.strip()))
        with self._lock:
            if cleaned:
                self._groups[name] = (priority, self._idle_clock(), cleaned)  # every call renews the group
            else:
                self._groups.pop(name, None)

    def quote(self, symbol: str) -> EodhdStreamQuote | None:
        """The name's last lit trade, only while Massive keeps answering for it: an old tick is never shown as live."""
        clean = _clean(symbol)
        with self._lock:
            answered = self._answered.get(clean)
            if answered is None or self._idle_clock() - answered > FRESH_SECONDS:
                return None
            return self._quotes.get(clean)

    def bars(self, symbol: str, *, limit: int = 180) -> list[dict[str, Any]]:
        return []  # no live candles: the charts keep their REST bars and the live last price (``quote``)

    @property
    def status(self) -> str:
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._error

    def desired(self) -> tuple[str, ...]:
        """The names to ask, as EODHD's stream picks them: higher priority first, then the group renewed last, up to
        ``max_symbols``. Groups idle for ``GROUP_IDLE_SECONDS`` are dropped first, and so are the ticks of names no group
        holds any more."""
        with self._lock:
            now = self._idle_clock()
            for name in [name for name, (_, renewed, _) in self._groups.items() if now - renewed > GROUP_IDLE_SECONDS]:
                del self._groups[name]
            held = {symbol for _, _, symbols in self._groups.values() for symbol in symbols}
            for symbol in [symbol for symbol in self._quotes if symbol not in held]:
                del self._quotes[symbol]
            for symbol in [symbol for symbol in self._answered if symbol not in held]:
                del self._answered[symbol]
            groups = sorted(self._groups.values(), key=lambda item: (item[0], item[1]), reverse=True)
        selected: dict[str, None] = {}
        for _, _, symbols in groups:
            for symbol in symbols:
                selected.setdefault(symbol, None)
                if len(selected) >= self.max_symbols:
                    return tuple(selected)
        return tuple(selected)

    def poll_once(self) -> int:
        """One round: the snapshot of every wanted name, ``CHUNK`` names per request. A failed request answers for none
        of its names (their ticks age out of ``quote``) and counts one failure, by error type only: httpx's message
        carries the URL and its token."""
        names = self.desired()
        if not names:
            self._set_state("idle")
            return 0
        if not self._is_open(self._clock()):
            self._set_state("closed")
            return 0
        taken, failed, answered = 0, "", 0
        for start in range(0, len(names), CHUNK):
            chunk = names[start:start + CHUNK]
            try:
                payload = self._get_json(
                    f"{self.base_url}/v2/snapshot/locale/us/markets/stocks/tickers",
                    params={"tickers": ",".join(symbol.replace("-", ".") for symbol in chunk), "include_otc": "true",
                            "apiKey": self.api_token},
                )
            except Exception as error:
                failed = type(error).__name__
                continue
            answered += 1
            taken += self._take(payload, set(chunk))
        with self._lock:
            self._counts["polls"] += 1
            self._counts["ticks"] += taken
            if failed:
                self._counts["failures"] += 1
            # the pause backs off only when no request was answered: one failing chunk does not slow the healthy ones
            self._failed_rounds = self._failed_rounds + 1 if not answered else 0
            self._state, self._error = ("error", failed) if failed else ("connected", "")
        return taken

    def _take(self, payload: Any, wanted: set[str]) -> int:
        """Every wanted name in the answer counts as answered; its last trade becomes the tick (Massive spells share
        classes BRK.B, the screens BRK-B) only when it is a lit, positive trade of the current New York session: an older
        trade never replaces a newer one."""
        rows = payload.get("tickers") if isinstance(payload, dict) else None
        now = self._clock()  # per request: a slow round's later answers are not refused as future-dated
        session = now.astimezone(NEW_YORK).date()
        answered_at = self._idle_clock()
        taken = 0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            symbol = _clean(str(row.get("ticker") or "")).replace(".", "-")
            if symbol not in wanted:
                continue
            with self._lock:
                self._answered[symbol] = answered_at
                current = self._quotes.get(symbol)
                if current is not None and current.as_of.astimezone(NEW_YORK).date() != session:
                    del self._quotes[symbol]  # a screen left open overnight never shows yesterday's last trade as live
            trade = row.get("lastTrade")
            if not isinstance(trade, dict) or not _lit(trade):
                continue
            try:
                price, stamp = float(trade.get("p") or 0.0), int(trade.get("t") or 0)
                as_of = datetime.fromtimestamp(stamp / 1e9, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError, OSError):
                continue
            if not (math.isfinite(price) and price > 0 and stamp > 0) or as_of > now + timedelta(seconds=5):
                continue
            if as_of.astimezone(NEW_YORK).date() != session:
                continue
            tick = EodhdStreamQuote(symbol=symbol, price=price, as_of=as_of,
                                    market_state="open" if self._is_open(as_of) else "closed", source="trade")
            with self._lock:
                current = self._quotes.get(symbol)
                if current is None or current.as_of <= as_of:
                    self._quotes[symbol] = tick
                    taken += 1
        return taken

    def _set_state(self, state: str) -> None:
        with self._lock:
            self._state = state
            self._failed_rounds = 0

    def pause(self) -> float:
        """Seconds to the next round: the poll interval, 30 s outside the session, doubled per failed round in a row."""
        with self._lock:
            state, failed = self._state, self._failed_rounds
        if state == "closed":
            return CLOSED_POLL_SECONDS
        return min(MAX_BACKOFF_SECONDS, self._poll_seconds * (2 ** min(failed, 5)))

    def beat(self) -> str:
        """The count-only heartbeat since the last one (names asked now, polls, failed polls, ticks taken)."""
        names = len(self.desired())
        with self._lock:
            line = "Screen quotes (Massive): state=%s symbols=%d polls=%d failures=%d ticks=%d" % (
                self._state if self._state in STATES else "error", names, self._counts["polls"],
                self._counts["failures"], self._counts["ticks"])
            self._counts = {"polls": 0, "failures": 0, "ticks": 0}
        heartbeat.info("%s", line)
        return line

    def start(self) -> None:
        if not self.api_token or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._set_state("idle")
        self._thread = Thread(target=self._run, name="massive-screen-quotes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._set_state("stopped")

    def _run(self) -> None:
        beaten = monotonic() - HEARTBEAT_SECONDS
        while not self._stop.is_set():
            started = monotonic()
            try:
                self.poll_once()
            except Exception as error:  # never dies: the screens keep their REST prices
                with self._lock:
                    self._state, self._error = "error", type(error).__name__
                    self._counts["failures"] += 1
                    self._failed_rounds += 1
            if started - beaten >= HEARTBEAT_SECONDS:
                self.beat()
                beaten = started
            self._stop.wait(max(0.5, self.pause() - (monotonic() - started)))


def screen_stream(settings: Any) -> LiveQuoteStream:
    """The api's live US source: Massive's snapshot when its token is set (one kept-alive connection), else EODHD's
    WebSocket stream capped to ``EODHD_FALLBACK_MAX_SYMBOLS``."""
    if settings.massive_api_token:
        return MassiveSnapshotStream(
            settings.massive_base_url,
            settings.massive_api_token,
            get_json=JsonHttpClient(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0,
                                    client=httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)).get_json,
            max_symbols=settings.r2d2_ws_max_symbols,
        )
    return EodhdRealtimeStream(settings.eodhd_api_token,
                               max_symbols=min(settings.r2d2_ws_max_symbols, EODHD_FALLBACK_MAX_SYMBOLS))
