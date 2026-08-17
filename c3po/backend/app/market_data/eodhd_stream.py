import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from threading import Event, RLock, Thread
from time import monotonic
from typing import Any

import websockets


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EodhdStreamQuote:
    symbol: str
    price: float
    as_of: datetime
    market_state: str
    bid: float | None = None
    ask: float | None = None
    source: str = "trade"


@dataclass
class EodhdStreamBar:
    timestamp: datetime
    updated_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int = 1


class EodhdRealtimeStream:
    """Maintains EODHD US trade and quote streams for one symbol set."""

    def __init__(self, api_token: str, *, max_symbols: int = 50) -> None:
        self.api_token = api_token.strip()
        self.max_symbols = max_symbols
        self._lock = RLock()
        self._groups: dict[str, tuple[int, float, tuple[str, ...]]] = {}
        self._quotes: dict[str, EodhdStreamQuote] = {}
        self._bars: dict[str, deque[EodhdStreamBar]] = {}
        self._feed_states = {"trade": "stopped", "quote": "stopped"}
        self._feed_errors = {"trade": "", "quote": ""}
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if not self.api_token or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = Thread(target=self._thread_main, name="eodhd-realtime", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)

    def set_group(self, name: str, symbols: list[str], *, priority: int = 50) -> None:
        cleaned = tuple(dict.fromkeys(
            symbol.strip().upper().removesuffix(".US")
            for symbol in symbols
            if symbol and symbol.strip()
        ))
        with self._lock:
            if cleaned:
                self._groups[name] = (priority, monotonic(), cleaned)
            else:
                self._groups.pop(name, None)

    def quote(self, symbol: str) -> EodhdStreamQuote | None:
        with self._lock:
            return self._quotes.get(symbol.strip().upper().removesuffix(".US"))

    def bars(self, symbol: str, *, limit: int = 180) -> list[dict[str, Any]]:
        """Returns five-minute candles aggregated from the live US trade stream."""
        clean = symbol.strip().upper().removesuffix(".US")
        with self._lock:
            return [
                {
                    "timestamp": row.timestamp,
                    "updated_at": row.updated_at,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                    "trades": row.trades,
                    "source": "EODHD Real-Time WebSocket",
                }
                for row in list(self._bars.get(clean, ()))[-max(1, limit):]
            ]

    @property
    def status(self) -> str:
        with self._lock:
            states = set(self._feed_states.values())
            if "connected" in states:
                return "connected"
            if "connecting" in states:
                return "connecting"
            if "error" in states:
                return "error"
            return "stopped"

    @property
    def last_error(self) -> str:
        with self._lock:
            return "; ".join(
                f"{feed}: {message}"
                for feed, message in self._feed_errors.items()
                if message
            )

    def _desired_symbols(self) -> tuple[str, ...]:
        with self._lock:
            groups = sorted(self._groups.values(), key=lambda item: (item[0], item[1]), reverse=True)
        selected: list[str] = []
        seen: set[str] = set()
        for _, _, symbols in groups:
            for symbol in symbols:
                if symbol in seen:
                    continue
                selected.append(symbol)
                seen.add(symbol)
                if len(selected) >= self.max_symbols:
                    return tuple(selected)
        return tuple(selected)

    def _set_feed_state(self, feed: str, status: str, error: str = "") -> None:
        with self._lock:
            self._feed_states[feed] = status
            self._feed_errors[feed] = error

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception:
            logger.exception("EODHD realtime stream stopped unexpectedly")
            self._set_feed_state("trade", "error", "stream stopped unexpectedly")
            self._set_feed_state("quote", "error", "stream stopped unexpectedly")

    async def _run(self) -> None:
        await asyncio.gather(
            self._run_feed("trade", "us", self._record),
            self._run_feed("quote", "us-quote", self._record_quote),
        )

    async def _run_feed(self, feed: str, endpoint: str, recorder: Any) -> None:
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
                    while not self._stop.is_set():
                        desired = set(self._desired_symbols())
                        removed = sorted(subscribed - desired)
                        added = sorted(desired - subscribed)
                        if removed:
                            await socket.send(json.dumps({"action": "unsubscribe", "symbols": ",".join(removed)}))
                        if added:
                            await socket.send(json.dumps({"action": "subscribe", "symbols": ",".join(added)}))
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

    def _record(self, payload: str | bytes) -> None:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        try:
            item: dict[str, Any] = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return
        symbol = str(item.get("s") or "").strip().upper()
        if item.get("dp") is True:
            return
        try:
            price = float(item.get("p"))
            timestamp_ms = int(item.get("t"))
        except (TypeError, ValueError):
            return
        if not symbol or price <= 0 or timestamp_ms <= 0:
            return
        quote = EodhdStreamQuote(
            symbol=symbol,
            price=price,
            as_of=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
            market_state=str(item.get("ms") or "open"),
            source="trade",
        )
        try:
            volume = max(0.0, float(item.get("v") or 0.0))
        except (TypeError, ValueError):
            volume = 0.0
        bar_at = quote.as_of.replace(
            minute=(quote.as_of.minute // 5) * 5,
            second=0,
            microsecond=0,
        )
        with self._lock:
            current = self._quotes.get(symbol)
            if not current or quote.as_of >= current.as_of:
                self._quotes[symbol] = quote
            bars = self._bars.setdefault(symbol, deque(maxlen=600))
            if bars and bars[-1].timestamp == bar_at:
                bar = bars[-1]
                bar.high = max(bar.high, price)
                bar.low = min(bar.low, price)
                bar.close = price
                bar.volume += volume
                bar.trades += 1
                bar.updated_at = max(bar.updated_at, quote.as_of)
            elif not bars or bar_at > bars[-1].timestamp:
                bars.append(EodhdStreamBar(
                    timestamp=bar_at,
                    updated_at=quote.as_of,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                ))

    def _record_quote(self, payload: str | bytes) -> None:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")
        try:
            item: dict[str, Any] = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return
        symbol = str(item.get("s") or "").strip().upper()
        try:
            bid = float(item.get("bp") or 0.0)
            ask = float(item.get("ap") or 0.0)
            timestamp_ms = int(item.get("t"))
        except (TypeError, ValueError):
            return
        if not symbol or timestamp_ms <= 0 or (bid <= 0 and ask <= 0):
            return
        if bid > 0 and ask > 0:
            if ask < bid or (ask - bid) / ((ask + bid) / 2) > 0.20:
                return
            price = (bid + ask) / 2
        else:
            price = bid if bid > 0 else ask
        as_of = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        with self._lock:
            current = self._quotes.get(symbol)
            if current and as_of < current.as_of:
                return
            self._quotes[symbol] = EodhdStreamQuote(
                symbol=symbol,
                price=price,
                as_of=as_of,
                market_state=current.market_state if current else "open",
                bid=bid if bid > 0 else None,
                ask=ask if ask > 0 else None,
                source="quote",
            )
