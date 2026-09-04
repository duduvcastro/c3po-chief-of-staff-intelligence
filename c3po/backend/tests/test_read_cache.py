from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from app.read_cache import MarketSessionClock, SingleFlightReadCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_entry_is_served_until_the_ttl_supplied_at_compute_time_expires() -> None:
    clock = FakeClock()
    ttl = {"value": 5.0}
    cache = SingleFlightReadCache(lambda: ttl["value"], clock=clock)
    calls: list[int] = []

    def compute() -> dict[str, int]:
        calls.append(1)
        return {"n": len(calls)}

    assert cache.get("dashboard", compute) == {"n": 1}
    clock.now += 4.999
    assert cache.get("dashboard", compute) == {"n": 1}
    clock.now += 0.002
    assert cache.get("dashboard", compute) == {"n": 2}
    assert cache.counters.snapshot() == {
        "hits": 1, "misses": 2, "coalesced": 0, "errors": 0, "invalidations": 0,
    }


def test_ttl_zero_never_serves_a_stale_entry() -> None:
    clock = FakeClock()
    cache = SingleFlightReadCache(lambda: 0.0, clock=clock)
    calls: list[int] = []

    def compute() -> int:
        calls.append(1)
        return len(calls)

    assert cache.get("k", compute) == 1
    assert cache.get("k", compute) == 2


def test_invalidate_drops_one_key_or_everything() -> None:
    cache = SingleFlightReadCache(lambda: 60.0, clock=FakeClock())
    cache.get("a", lambda: "a1")
    cache.get("b", lambda: "b1")
    cache.invalidate("a")
    assert cache.get("a", lambda: "a2") == "a2"
    assert cache.get("b", lambda: "b2") == "b1"
    cache.invalidate()
    assert cache.get("b", lambda: "b3") == "b3"
    assert cache.counters.invalidations == 2


def test_concurrent_misses_share_exactly_one_computation() -> None:
    cache = SingleFlightReadCache(lambda: 60.0)
    started = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def compute() -> str:
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return "payload"

    results: list[str] = []

    def worker() -> None:
        results.append(cache.get("dashboard", compute))

    leader = threading.Thread(target=worker)
    leader.start()
    assert started.wait(timeout=5)
    followers = [threading.Thread(target=worker) for _ in range(7)]
    for thread in followers:
        thread.start()
    # Followers must be blocked on the in-flight computation, not computing.
    for _ in range(50):
        if cache.counters.coalesced == 7:
            break
        threading.Event().wait(0.01)
    assert cache.counters.coalesced == 7
    release.set()
    leader.join(timeout=5)
    for thread in followers:
        thread.join(timeout=5)
    assert results == ["payload"] * 8
    assert calls == [1]
    assert cache.counters.misses == 1


def test_exceptions_reach_every_waiter_and_are_never_cached() -> None:
    cache = SingleFlightReadCache(lambda: 60.0)
    attempts: list[int] = []

    def failing() -> None:
        attempts.append(1)
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        cache.get("k", failing)
    with pytest.raises(RuntimeError):
        cache.get("k", failing)
    assert attempts == [1, 1]
    assert cache.counters.errors == 2
    assert cache.get("k", lambda: "recovered") == "recovered"


def test_market_session_clock_follows_the_xnys_regular_session() -> None:
    clock = MarketSessionClock()
    # Thursday 2026-09-03: regular session 13:30-20:00 UTC (EDT).
    assert clock.is_open(datetime(2026, 9, 3, 13, 30, tzinfo=timezone.utc)) is True
    assert clock.is_open(datetime(2026, 9, 3, 17, 45, tzinfo=timezone.utc)) is True
    assert clock.is_open(datetime(2026, 9, 3, 13, 29, tzinfo=timezone.utc)) is False
    assert clock.is_open(datetime(2026, 9, 3, 20, 0, tzinfo=timezone.utc)) is False
    # Saturday 2026-09-05 and Labor Day 2026-09-07 are not sessions.
    assert clock.is_open(datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)) is False
    assert clock.is_open(datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)) is False
