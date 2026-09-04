"""Single-flight TTL cache for read-only API payloads (C3PO_CPU_RELIEF_V1, PR B).

The cache stops identical read-only computations from running once per poller
per second. It never stores mutations or commands: callers pass a pure
``compute`` callable and receive whatever it returned last, as long as the entry
is younger than the TTL supplied at lookup time. Concurrent misses on one key
share a single computation (single-flight); waiters receive the same result or
the same exception, and exceptions are never cached.

Invalidation is explicit (``invalidate``). Trades executed by the R2D2 worker
live in another process and cannot call ``invalidate`` here: the market-session
TTL is the hard bound on how stale a dashboard read can be while the market is
open.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

NEW_YORK = ZoneInfo("America/New_York")

T = TypeVar("T")


class MarketSessionClock:
    """Regular-session awareness for one exchange calendar (default XNYS)."""

    def __init__(self, calendar_name: str = "XNYS") -> None:
        self._calendar = xcals.get_calendar(calendar_name)

    def is_open(self, now: datetime | None = None) -> bool:
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone(timezone.utc)
        session = moment.astimezone(NEW_YORK).date()
        if not self._calendar.is_session(session):
            return False
        open_at = self._calendar.session_open(session).to_pydatetime()
        close_at = self._calendar.session_close(session).to_pydatetime()
        return open_at <= moment < close_at


@dataclass
class ReadCacheCounters:
    hits: int = 0
    misses: int = 0
    coalesced: int = 0
    errors: int = 0
    invalidations: int = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "coalesced": self.coalesced,
            "errors": self.errors,
            "invalidations": self.invalidations,
        }


class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at


class _InFlight:
    __slots__ = ("done", "value", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None


class SingleFlightReadCache:
    """Per-key TTL cache where concurrent misses share exactly one computation."""

    def __init__(
        self,
        ttl_seconds: Callable[[], float],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}
        self._inflight: dict[str, _InFlight] = {}
        self.counters = ReadCacheCounters()

    def get(self, key: str, compute: Callable[[], T]) -> T:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > self._clock():
                self.counters.hits += 1
                return entry.value
            inflight = self._inflight.get(key)
            if inflight is not None:
                self.counters.coalesced += 1
                leader = False
            else:
                inflight = _InFlight()
                self._inflight[key] = inflight
                self.counters.misses += 1
                leader = True
        if not leader:
            inflight.done.wait()
            if inflight.error is not None:
                raise inflight.error
            return inflight.value
        try:
            value = compute()
        except BaseException as error:  # noqa: BLE001 - propagated to every waiter
            with self._lock:
                self.counters.errors += 1
                self._inflight.pop(key, None)
            inflight.error = error
            inflight.done.set()
            raise
        ttl = max(0.0, float(self._ttl_seconds()))
        with self._lock:
            self._entries[key] = _Entry(value, self._clock() + ttl)
            self._inflight.pop(key, None)
        inflight.value = value
        inflight.done.set()
        return value

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)
            self.counters.invalidations += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "keys": sorted(self._entries),
                "inflight": sorted(self._inflight),
                **self.counters.snapshot(),
            }
