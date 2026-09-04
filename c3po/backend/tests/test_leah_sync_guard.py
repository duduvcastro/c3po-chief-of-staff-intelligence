from __future__ import annotations

import threading

import pytest

from app.leah_sync_guard import (
    LeahSyncBackoff,
    LeahSyncBusy,
    LeahSyncGuard,
    LeahSyncTimeout,
    payload_fingerprint,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now


def _guard(clock: FakeClock, **overrides: float) -> LeahSyncGuard:
    options = {"dedupe_window_seconds": 30.0, "deadline_seconds": 10.0, "cooldown_seconds": 30.0}
    options.update(overrides)
    return LeahSyncGuard(clock=clock, **options)


def test_identical_payload_inside_the_window_returns_the_computed_result_once() -> None:
    clock = FakeClock()
    guard = _guard(clock)
    calls: list[int] = []

    def work() -> dict[str, int]:
        calls.append(1)
        return {"cursor": len(calls)}

    payload = {"items": [{"id": "a"}], "cursor": "2026-09-04T10:00:00+00:00"}
    first = guard.run("device-1", payload, work)
    clock.now += 29.0
    second = guard.run("device-1", dict(payload), work)
    assert first is second
    assert calls == [1]
    clock.now += 2.0
    third = guard.run("device-1", payload, work)
    assert third == {"cursor": 2}
    assert guard.counters.deduplicated == 1
    assert guard.counters.executed == 2


def test_changed_payload_is_never_discarded() -> None:
    clock = FakeClock()
    guard = _guard(clock)
    seen: list[str] = []

    def make(tag: str):
        def work() -> str:
            seen.append(tag)
            return tag
        return work

    assert guard.run("device-1", {"items": [{"id": "a"}]}, make("a")) == "a"
    assert guard.run("device-1", {"items": [{"id": "b"}]}, make("b")) == "b"
    assert seen == ["a", "b"]
    assert guard.counters.deduplicated == 0


def test_identities_do_not_share_dedupe_results() -> None:
    clock = FakeClock()
    guard = _guard(clock)
    payload = {"items": []}
    assert guard.run("device-1", payload, lambda: "one") == "one"
    assert guard.run("device-2", payload, lambda: "two") == "two"
    assert guard.snapshot()["identities"] == 2


def test_deadline_returns_timeout_with_retry_after_and_blocks_retries_while_running() -> None:
    clock = FakeClock()
    guard = _guard(clock, deadline_seconds=0.05)
    release = threading.Event()

    def slow() -> str:
        release.wait(timeout=5)
        return "late"

    payload = {"items": [{"id": "slow"}]}
    with pytest.raises(LeahSyncTimeout) as timeout:
        guard.run("device-1", payload, slow)
    assert timeout.value.status_code == 504
    assert timeout.value.retry_after == 30
    # The original work is still running: a retry must not start a second execution.
    with pytest.raises(LeahSyncBusy) as busy:
        guard.run("device-1", {"items": [{"id": "other"}]}, lambda: "never")
    assert busy.value.status_code == 503
    assert guard.counters.timeouts == 1
    assert guard.counters.busy_rejected == 1
    release.set()
    # Once the late work completes it is ACCOUNTED (executed + late) and reusable.
    for _ in range(200):
        if guard.counters.late_completions == 1:
            break
        threading.Event().wait(0.01)
    assert guard.counters.executed == 1
    assert guard.counters.late_completions == 1
    assert guard.counters.last_duration_ms >= 0.0  # fake clock: duration is measured, not asserted
    assert guard.run("device-1", payload, lambda: "fresh") == "late"
    assert guard.counters.deduplicated == 1


def test_error_opens_a_cooldown_only_for_the_same_fingerprint() -> None:
    clock = FakeClock()
    guard = _guard(clock)

    def boom() -> None:
        raise RuntimeError("db unavailable")

    payload = {"items": [{"id": "x"}]}
    with pytest.raises(RuntimeError):
        guard.run("device-1", payload, boom)
    with pytest.raises(LeahSyncBackoff) as backoff:
        guard.run("device-1", payload, lambda: "retry")
    assert backoff.value.status_code == 429
    assert 1 <= backoff.value.retry_after <= 30
    assert guard.run("device-1", {"items": [{"id": "y"}]}, lambda: "changed") == "changed"
    clock.now += 31.0
    assert guard.run("device-1", payload, lambda: "after cooldown") == "after cooldown"
    assert guard.counters.errors == 1
    assert guard.counters.backoff_rejected == 1


def test_concurrent_calls_for_one_identity_execute_one_at_a_time() -> None:
    guard = LeahSyncGuard(dedupe_window_seconds=0.0, deadline_seconds=5.0)
    active = 0
    peak = 0
    state_lock = threading.Lock()

    def work() -> str:
        nonlocal active, peak
        with state_lock:
            active += 1
            peak = max(peak, active)
        threading.Event().wait(0.02)
        with state_lock:
            active -= 1
        return "ok"

    threads = [
        threading.Thread(target=lambda i=i: guard.run("device-1", {"n": i}, work))
        for i in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert peak == 1
    assert guard.counters.executed == 5
    assert guard.counters.queued >= 1  # distinct payloads waited for the lock
    assert guard.counters.coalesced == 0


def test_fingerprint_is_canonical() -> None:
    assert payload_fingerprint({"b": 1, "a": [1, 2]}) == payload_fingerprint({"a": [1, 2], "b": 1})
    assert payload_fingerprint({"a": 1}) != payload_fingerprint({"a": 2})


def test_deadline_covers_the_wait_for_the_identity_lock() -> None:
    import time as _time

    # First caller: deadline 0.3 s, work sleeps 1.5 s -> it times out (504) and releases
    # the identity lock at ~0.3 s while its work keeps running (in flight).
    # Second caller (different payload) arrives while the lock is held: its budget must
    # bound the QUEUE wait too, so it answers 503 well before the slow work completes.
    guard = LeahSyncGuard(dedupe_window_seconds=0.0, deadline_seconds=0.3, cooldown_seconds=30.0)
    holding = threading.Event()

    def slow() -> str:
        holding.set()
        _time.sleep(1.5)
        return "slow"

    first_outcome: list[object] = []

    def first_caller() -> None:
        try:
            first_outcome.append(guard.run("device-1", {"items": [{"id": "a"}]}, slow))
        except BaseException as error:  # noqa: BLE001
            first_outcome.append(error)

    thread = threading.Thread(target=first_caller)
    thread.start()
    assert holding.wait(timeout=5)
    started = _time.monotonic()
    with pytest.raises(LeahSyncBusy):
        guard.run("device-1", {"items": [{"id": "b"}]}, lambda: "never")
    elapsed = _time.monotonic() - started
    assert elapsed < 1.2, f"queue wait was not bounded by the deadline: {elapsed:.3f}s"
    thread.join(timeout=5)
    assert first_outcome, f"first caller never finished: {guard.snapshot()}"
    assert isinstance(first_outcome[0], LeahSyncTimeout), first_outcome
    assert guard.counters.busy_rejected == 1
    assert guard.counters.timeouts == 1
    # The slow work still completes and is accounted as a late completion.
    for _ in range(400):
        if guard.counters.late_completions == 1:
            break
        _time.sleep(0.01)
    assert guard.counters.late_completions == 1


def test_coalesced_and_queued_are_counted_separately() -> None:
    guard = LeahSyncGuard(dedupe_window_seconds=30.0, deadline_seconds=5.0)
    gate = threading.Event()

    def work() -> str:
        gate.wait(timeout=5)
        return "done"

    same = {"items": [{"id": "same"}]}
    results: list[str] = []
    leader = threading.Thread(target=lambda: results.append(guard.run("device-1", same, work)))
    leader.start()
    for _ in range(100):
        if guard._state("device-1").lock.locked():
            break
        threading.Event().wait(0.005)
    follower_same = threading.Thread(target=lambda: results.append(guard.run("device-1", dict(same), lambda: "unused")))
    follower_other = threading.Thread(target=lambda: results.append(guard.run("device-1", {"items": [{"id": "other"}]}, lambda: "other")))
    follower_same.start()
    follower_other.start()
    threading.Event().wait(0.05)
    gate.set()
    for thread in (leader, follower_same, follower_other):
        thread.join(timeout=5)
    assert sorted(results) == ["done", "done", "other"]
    assert guard.counters.coalesced == 1
    assert guard.counters.queued == 1
    assert guard.counters.deduplicated == 1
    assert guard.counters.executed == 2
