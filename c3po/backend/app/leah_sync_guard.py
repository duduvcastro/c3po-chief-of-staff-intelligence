"""Concurrency guard for ``POST /api/v1/leah/agent/sync`` (C3PO_CPU_RELIEF_V1, PR B).

Measured over five sessions the endpoint received 22,287 calls (mean 528 ms,
worst 709 s). The guard enforces, per device identity:

* one execution at a time (a concurrent caller waits for the running one);
* an identical payload within ``dedupe_window_seconds`` returns the result that
  was already computed, without touching the database again;
* a changed payload is never discarded;
* a hard END-TO-END deadline (``deadline_seconds``) that starts on entry and
  covers the wait for the per-identity lock plus the execution: the caller
  receives a timeout/busy error carrying ``retry_after``; running work is not
  killed (killing mid-upsert would leave partial state) but stays registered
  as in-flight, so retries cannot pile up behind it;
* timeouts and errors open a cooldown for the same fingerprint, so a client
  that retries immediately gets a backoff answer instead of a new execution.

Every outcome increments a counter; ``snapshot()`` exposes them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LeahSyncRejected(RuntimeError):
    """Base class for guard rejections; ``retry_after`` is in whole seconds."""

    status_code = 503

    def __init__(self, message: str, *, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


class LeahSyncTimeout(LeahSyncRejected):
    status_code = 504


class LeahSyncBusy(LeahSyncRejected):
    status_code = 503


class LeahSyncBackoff(LeahSyncRejected):
    status_code = 429


@dataclass
class LeahSyncCounters:
    executed: int = 0
    late_completions: int = 0
    deduplicated: int = 0
    coalesced: int = 0
    queued: int = 0
    busy_rejected: int = 0
    backoff_rejected: int = 0
    timeouts: int = 0
    cancelled: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    last_duration_ms: float = 0.0

    def snapshot(self) -> dict[str, float | int]:
        average = self.total_duration_ms / self.executed if self.executed else 0.0
        return {
            "executed": self.executed,
            "late_completions": self.late_completions,
            "deduplicated": self.deduplicated,
            "coalesced": self.coalesced,
            "queued": self.queued,
            "busy_rejected": self.busy_rejected,
            "backoff_rejected": self.backoff_rejected,
            "timeouts": self.timeouts,
            "cancelled": self.cancelled,
            "errors": self.errors,
            "average_duration_ms": round(average, 3),
            "max_duration_ms": round(self.max_duration_ms, 3),
            "last_duration_ms": round(self.last_duration_ms, 3),
        }


@dataclass
class _IdentityState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    result_lock: threading.Lock = field(default_factory=threading.Lock)
    inflight: Future | None = None
    inflight_fingerprint: str | None = None
    last_fingerprint: str | None = None
    last_result: Any = None
    last_completed_at: float | None = None
    cooldown_fingerprint: str | None = None
    cooldown_until: float | None = None


def payload_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LeahSyncGuard:
    """See module docstring. The deadline is END-TO-END: it starts when ``run`` is
    entered and covers the wait for the per-identity lock (queueing/coalescing)
    plus the execution itself. Work that finishes after its caller timed out is
    still accounted (``executed`` + ``late_completions`` + duration) and its
    result becomes reusable for identical payloads."""

    def __init__(
        self,
        *,
        dedupe_window_seconds: float = 30.0,
        deadline_seconds: float = 10.0,
        cooldown_seconds: float = 30.0,
        max_workers: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.dedupe_window_seconds = float(dedupe_window_seconds)
        self.deadline_seconds = float(deadline_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="leah-sync"
        )
        self._registry_lock = threading.Lock()
        self._states: dict[str, _IdentityState] = {}
        self.counters = LeahSyncCounters()

    def _state(self, identity: str) -> _IdentityState:
        with self._registry_lock:
            state = self._states.get(identity)
            if state is None:
                state = _IdentityState()
                self._states[identity] = state
            return state

    def _count(self, field_name: str, amount: int = 1) -> None:
        with self._registry_lock:
            setattr(self.counters, field_name, getattr(self.counters, field_name) + amount)

    def run(self, identity: str, payload: dict[str, Any], work: Callable[[], Any]) -> Any:
        entered_at = self._clock()
        deadline_at = entered_at + self.deadline_seconds
        fingerprint = payload_fingerprint(payload)
        state = self._state(identity)

        waited = not state.lock.acquire(blocking=False)
        if waited:
            remaining = deadline_at - self._clock()
            if remaining <= 0 or not state.lock.acquire(timeout=remaining):
                self._count("busy_rejected")
                raise LeahSyncBusy(
                    "Fila de sincronização deste dispositivo excedeu o prazo do servidor.",
                    retry_after=self.cooldown_seconds,
                )
        try:
            now = self._clock()
            inflight = state.inflight
            if inflight is not None and not inflight.done():
                self._count("busy_rejected")
                raise LeahSyncBusy(
                    "Sincronização anterior ainda em execução para este dispositivo.",
                    retry_after=self.cooldown_seconds,
                )
            with state.result_lock:
                same_recent = (
                    state.last_fingerprint == fingerprint
                    and state.last_completed_at is not None
                    and now - state.last_completed_at <= self.dedupe_window_seconds
                )
                last_result = state.last_result
                in_cooldown = (
                    state.cooldown_fingerprint == fingerprint
                    and state.cooldown_until is not None
                    and now < state.cooldown_until
                )
                cooldown_until = state.cooldown_until
            if waited:
                self._count("coalesced" if same_recent else "queued")
            if same_recent:
                self._count("deduplicated")
                return last_result
            if in_cooldown:
                self._count("backoff_rejected")
                raise LeahSyncBackoff(
                    "Payload idêntico rejeitado durante o período de espera.",
                    retry_after=(cooldown_until or now) - now,
                )
            remaining = deadline_at - self._clock()
            if remaining <= 0:
                self._count("busy_rejected")
                raise LeahSyncBusy(
                    "Prazo do servidor esgotado antes de iniciar a sincronização.",
                    retry_after=self.cooldown_seconds,
                )
            started = self._clock()
            future = self._executor.submit(work)
            # The deadline lives on the flight itself: classification of a completion as
            # late is a pure comparison (completed_at > deadline_at) and never depends on
            # which thread — caller or done-callback — gets there first.
            setattr(future, "_c3po_deadline_at", deadline_at)
            state.inflight = future
            state.inflight_fingerprint = fingerprint
            future.add_done_callback(
                lambda done, s=state, fp=fingerprint, t0=started: self._publish(s, fp, t0, done)
            )
            try:
                result = future.result(timeout=remaining)
            except FutureTimeout:
                settled = future.done() and not future.cancelled() and future.exception() is None
                if settled:
                    # Record the flight's real completion instant (idempotent) and decide by
                    # the flight's own clock: only a completion at or before the deadline may
                    # be delivered. A later one is a hard-deadline miss for THIS caller (504),
                    # while its publication stays accounted and reusable (Codex reaudit, P1).
                    self._publish(state, fingerprint, started, future)
                    completed_at = float(getattr(future, "_c3po_completed_at", float("inf")))
                    if completed_at <= deadline_at:
                        return future.result()
                else:
                    with state.result_lock:
                        state.cooldown_fingerprint = fingerprint
                        state.cooldown_until = self._clock() + self.cooldown_seconds
                self._count("timeouts")
                if future.cancel():
                    # Still queued: it never ran and never will (Codex reaudit, P1-1).
                    with state.result_lock:
                        if state.inflight is future:
                            state.inflight = None
                            state.inflight_fingerprint = None
                    self._count("cancelled")
                logger.warning(
                    "leah sync deadline exceeded identity=%s deadline_s=%.1f counters=%s",
                    identity, self.deadline_seconds, self.snapshot(),
                )
                raise LeahSyncTimeout(
                    "Sincronização excedeu o prazo do servidor.",
                    retry_after=self.cooldown_seconds,
                ) from None
            except BaseException as error:  # noqa: BLE001 - recorded by _publish
                if isinstance(error, LeahSyncRejected):
                    raise
                self._publish(state, fingerprint, started, future)
                logger.warning(
                    "leah sync failed identity=%s error=%s counters=%s",
                    identity, error.__class__.__name__, self.snapshot(),
                )
                raise
            # Publish synchronously BEFORE releasing the identity lock: the done-callback
            # may still be pending, and a second identical payload must dedupe against a
            # result that is already visible (Codex reaudit, P1-3). _publish is idempotent.
            self._publish(state, fingerprint, started, future)
            return result
        finally:
            state.lock.release()

    def _publish(
        self, state: _IdentityState, fingerprint: str, started: float, future: Future
    ) -> None:
        """Account one finished flight exactly once (caller path or done-callback,
        whichever comes first). ``late`` is derived from the flight's own state — its
        caller timed out — never from the momentary presence of a cooldown."""
        if not future.done():
            return
        completed = self._clock()
        duration_ms = max(0.0, (completed - started) * 1000.0)
        with state.result_lock:
            # Flags live on the Future object: immune to id() reuse after garbage collection.
            if getattr(future, "_c3po_published", False):
                return
            setattr(future, "_c3po_published", True)
            setattr(future, "_c3po_completed_at", completed)
            deadline_at = getattr(future, "_c3po_deadline_at", None)
            late = deadline_at is not None and completed > float(deadline_at)
            if state.inflight is future:
                state.inflight = None
                state.inflight_fingerprint = None
            if future.cancelled():
                outcome = "cancelled"
            else:
                error = future.exception()
                if error is None:
                    outcome = "ok"
                    state.last_fingerprint = fingerprint
                    state.last_result = future.result()
                    state.last_completed_at = completed
                    state.cooldown_fingerprint = None
                    state.cooldown_until = None
                else:
                    outcome = "error"
                    state.cooldown_fingerprint = fingerprint
                    state.cooldown_until = completed + self.cooldown_seconds
        with self._registry_lock:
            if outcome == "ok":
                self.counters.executed += 1
                if late:
                    self.counters.late_completions += 1
                self.counters.total_duration_ms += duration_ms
                self.counters.max_duration_ms = max(self.counters.max_duration_ms, duration_ms)
                self.counters.last_duration_ms = duration_ms
            elif outcome == "error":
                self.counters.errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._registry_lock:
            identities = len(self._states)
            counters = self.counters.snapshot()
        return {"identities": identities, **counters}
