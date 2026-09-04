"""Single-flight TTL cache for read-only API payloads (C3PO_CPU_RELIEF_V1, PR B).

The cache stops identical read-only computations from running once per poller
per second. It never stores mutations or commands: callers pass a pure
``compute`` callable and receive whatever it returned last, as long as the entry
is younger than the TTL supplied at lookup time. Concurrent misses on one key
share a single computation (single-flight); waiters receive the same result or
the same exception, and exceptions are never cached.

Invalidation is explicit (``invalidate``). Trades executed by the R2D2 worker
live in another process and cannot call ``invalidate`` here: the market-session
TTL, measured from the instant the cached computation STARTED, is the hard bound
on how stale a dashboard read can be while the market is open.
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
    __slots__ = ("done", "value", "error", "epoch", "generation")

    def __init__(self, epoch: int, generation: int) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None
        self.epoch = epoch          # bumped by invalidate() without a key
        self.generation = generation  # bumped by invalidate(key) for THIS key only


class SingleFlightReadCache:
    """Per-key TTL cache where concurrent misses share exactly one computation.

    Guarantees (audited on #373):
    * validity is anchored at the moment the computation STARTED, so an entry is
      never older than the TTL measured from its as-of instant, however long the
      computation took;
    * ``invalidate`` bumps a generation token; a computation that started before
      the invalidation returns its value to its waiters but never repopulates the
      key;
    * every exit path (compute error, TTL provider error) clears the in-flight
      marker and propagates the same failure to every waiter — nothing hangs.
    """

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
        self._epoch = 0
        self._generations: dict[str, int] = {}
        self.counters = ReadCacheCounters()

    def get(self, key: str, compute: Callable[[], T]) -> T:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > self._clock():
                self.counters.hits += 1
                return entry.value
            epoch = self._epoch
            generation = self._generations.get(key, 0)
            inflight = self._inflight.get(key)
            # Only a flight of the CURRENT epoch AND key generation may be joined: a caller
            # arriving after an invalidation of THIS key (or of everything) must never
            # receive the pre-invalidation result — while invalidating another key must
            # never break this key's single-flight (per-key generations).
            if inflight is not None and inflight.epoch == epoch and inflight.generation == generation:
                self.counters.coalesced += 1
                leader = False
            else:
                inflight = _InFlight(epoch, generation)
                self._inflight[key] = inflight
                self.counters.misses += 1
                leader = True
            started_at = self._clock()
        if not leader:
            inflight.done.wait()
            if inflight.error is not None:
                raise inflight.error
            return inflight.value
        try:
            ttl = max(0.0, float(self._ttl_seconds()))
            value = compute()
        except BaseException as error:  # noqa: BLE001 - propagated to every waiter
            self._fail_flight(key, inflight, error)
            raise
        with self._lock:
            if self._epoch == epoch and self._generations.get(key, 0) == generation:
                self._entries[key] = _Entry(value, started_at + ttl)
            if self._inflight.get(key) is inflight:  # never erase a newer flight
                self._inflight.pop(key, None)
        inflight.value = value
        inflight.done.set()
        return value

    def _fail_flight(self, key: str, inflight: _InFlight, error: BaseException) -> None:
        with self._lock:
            self.counters.errors += 1
            if self._inflight.get(key) is inflight:
                self._inflight.pop(key, None)
        inflight.error = error
        inflight.done.set()

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._entries.clear()
                self._inflight.clear()  # earlier waiters keep their own references
                self._epoch += 1
            else:
                self._entries.pop(key, None)
                self._inflight.pop(key, None)
                self._generations[key] = self._generations.get(key, 0) + 1
            self.counters.invalidations += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "keys": sorted(self._entries),
                "inflight": sorted(self._inflight),
                "epoch": self._epoch,
                "generations": dict(self._generations),
                **self.counters.snapshot(),
            }
