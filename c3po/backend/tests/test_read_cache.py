from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from app.read_cache import MarketSessionClock, ReadCacheWaitTimeout, SingleFlightReadCache


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
        "wait_timeouts": 0,
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


def test_ttl_provider_failure_clears_the_flight_and_reaches_every_waiter() -> None:
    calls = {"ttl": 0}

    def ttl() -> float:
        calls["ttl"] += 1
        if calls["ttl"] == 1:
            raise RuntimeError("calendar unavailable")
        return 60.0

    cache = SingleFlightReadCache(ttl)
    with pytest.raises(RuntimeError):
        cache.get("k", lambda: "value")
    assert cache.snapshot()["inflight"] == []
    assert cache.counters.errors == 1
    # The key is not poisoned: the next call computes normally.
    assert cache.get("k", lambda: "recovered") == "recovered"


def test_validity_is_anchored_at_the_start_of_the_computation() -> None:
    clock = FakeClock()
    cache = SingleFlightReadCache(lambda: 5.0, clock=clock)
    calls: list[int] = []

    def slow_compute() -> str:
        calls.append(1)
        clock.now += 10.0  # the computation itself took 10 s
        return f"snapshot-{len(calls)}"

    assert cache.get("dashboard", slow_compute) == "snapshot-1"
    # Anchored at start (t=1000, ttl 5): already expired when the compute finished at t=1010.
    assert cache.get("dashboard", slow_compute) == "snapshot-2"
    assert calls == [1, 1]


def test_invalidate_during_compute_prevents_the_stale_result_from_repopulating() -> None:
    cache = SingleFlightReadCache(lambda: 60.0)
    started = threading.Event()
    release = threading.Event()

    def compute() -> str:
        started.set()
        release.wait(timeout=5)
        return "old"

    results: list[str] = []
    leader = threading.Thread(target=lambda: results.append(cache.get("k", compute)))
    leader.start()
    assert started.wait(timeout=5)
    cache.invalidate()  # a trade/command happened while the old snapshot was computing
    release.set()
    leader.join(timeout=5)
    assert results == ["old"]  # the in-flight caller still gets its value
    assert cache.snapshot()["keys"] == []  # ...but the key was not repopulated
    assert cache.get("k", lambda: "fresh") == "fresh"


def test_caller_arriving_after_invalidate_never_joins_the_old_flight() -> None:
    cache = SingleFlightReadCache(lambda: 60.0)
    started = threading.Event()
    release = threading.Event()

    def old_compute() -> str:
        started.set()
        release.wait(timeout=5)
        return "old"

    early: list[str] = []
    leader = threading.Thread(target=lambda: early.append(cache.get("k", old_compute)))
    leader.start()
    assert started.wait(timeout=5)
    cache.invalidate()
    # Post-invalidation caller: must compute fresh, not coalesce onto the old flight.
    assert cache.get("k", lambda: "fresh") == "fresh"
    release.set()
    leader.join(timeout=5)
    assert early == ["old"]  # the earlier waiter keeps what it joined
    assert cache.get("k", lambda: "unused") == "fresh"  # the key holds the fresh value
    assert cache.snapshot()["inflight"] == []


def test_invalidating_one_key_keeps_the_single_flight_of_another_key() -> None:
    cache = SingleFlightReadCache(lambda: 60.0)
    started = threading.Event()
    release = threading.Event()
    computes = {"b": 0}

    def compute_b() -> str:
        computes["b"] += 1
        started.set()
        release.wait(timeout=5)
        return "b-value"

    results: list[str] = []
    leader = threading.Thread(target=lambda: results.append(cache.get("b", compute_b)))
    leader.start()
    assert started.wait(timeout=5)
    cache.invalidate("a")  # unrelated key
    follower = threading.Thread(target=lambda: results.append(cache.get("b", compute_b)))
    follower.start()
    for _ in range(100):
        if cache.counters.coalesced == 1:
            break
        threading.Event().wait(0.01)
    assert cache.counters.coalesced == 1  # the follower joined the in-flight computation
    release.set()
    leader.join(timeout=5)
    follower.join(timeout=5)
    assert results == ["b-value", "b-value"]
    assert computes["b"] == 1
    # ...whereas invalidating "b" itself does start a fresh computation.
    cache.invalidate("b")
    assert cache.get("b", lambda: "fresh") == "fresh"


def test_max_entries_bounds_dynamic_keys_and_purges_expired_first() -> None:
    clock = FakeClock()
    cache = SingleFlightReadCache(lambda: 10.0, clock=clock, max_entries=3)
    for i in range(3):
        cache.get(f"k{i}", lambda i=i: i)
    assert cache.snapshot()["keys"] == ["k0", "k1", "k2"]
    cache.get("k3", lambda: 3)  # evicts the soonest-expiring entry
    assert len(cache.snapshot()["keys"]) == 3
    assert "k3" in cache.snapshot()["keys"]
    clock.now += 11.0  # everything expired
    cache.get("k4", lambda: 4)
    assert cache.snapshot()["keys"] == ["k4"]


def test_follower_wait_timeout_raises_without_touching_the_flight() -> None:
    """A follower may bound how long it waits for a computation it did not start (#374 P2:
    every wait of an aggregate request spends only the remaining budget). The leader and the
    key it populates are unaffected; the timeout is neither an error nor a cached value."""
    started = threading.Event()
    release = threading.Event()
    results: list[str] = []

    def compute() -> str:
        started.set()
        assert release.wait(5)
        return "value"

    cache = SingleFlightReadCache(lambda: 60.0)
    leader = threading.Thread(target=lambda: results.append(cache.get("k", compute)))
    leader.start()
    assert started.wait(2)
    with pytest.raises(ReadCacheWaitTimeout) as raised:
        cache.get("k", compute, wait_timeout=0.05)
    assert raised.value.key == "k"
    assert cache.counters.wait_timeouts == 1
    assert cache.counters.errors == 0
    assert cache.snapshot()["inflight"] == ["k"]  # the flight is still the leader's
    release.set()
    leader.join(5)
    assert results == ["value"]
    assert cache.get("k", lambda: "other") == "value"  # populated by the leader, served as a hit
    assert cache.counters.hits == 1
