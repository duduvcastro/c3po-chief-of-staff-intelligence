"""Process identity of ingestion runs and the startup reaper of runs orphaned by a restart.

A deploy (``docker compose up -d``) restarts every worker; a run in progress at that moment would stay
``status='running'`` in ``ingestion_runs`` forever (health cards, the PIT grid preflight and the security reboot
controller all read ``running``). Two pieces close that:

* **The marker.** ``Database.begin_ingestion_run`` stamps every new run's metadata with this process's identity:
  ``process_instance`` (a uuid4 drawn once per process, redrawn after a fork), ``process_pid``, ``process_started_at``,
  ``process_host`` (the hostname: the short container id under Docker) and, when the process is a worker that claimed
  one, ``process_role``.
* **The reaper.** A worker, at startup and BEFORE its first run, claims its role and marks ``failed`` (error summary
  ``ORPHAN_ERROR_SUMMARY``, ``metadata.reaped_at`` / ``metadata.reaped_by``) every run still ``running`` that
  started before this process did and that is

  - marked with THIS worker's role and another ``process_instance`` (a previous process of the same worker), or
  - unmarked (written before the marker existed) and of a source only this worker writes (``WorkerOwnership.legacy_*``).

  Runs of another role, of a process that claimed no role (the API, one-off CLIs), of this very process, and unmarked
  runs of shared sources are never touched. One atomic ``UPDATE ... WHERE status = 'running' ... RETURNING id``.

The rule assumes ONE live process per worker role (one container per worker service in compose.yml): a second
process claiming the same role at startup would reap the first one's in-flight runs.

* **The stale-run reaper.** The valuation worker alone (one process applies it) also marks ``failed`` (error summary
  ``STALE_ERROR_SUMMARY``, the same ``reaped_at`` / ``reaped_by``) every run still ``running`` more than
  ``STALE_RUNNING_AFTER`` after it started, whatever its role (or none: the API, a one-off CLI) and its source — the
  orphans the rule above leaves alone. Both sides of the age on the database clock (``now()``); one atomic, idempotent
  ``UPDATE ... WHERE status = 'running' AND started_at < now() - interval ... RETURNING id``. It runs at startup and
  then at most once per ``STALE_SWEEP_INTERVAL_SECONDS`` while the worker idles (``PeriodicReaper``), so an orphan is
  cleared without a deploy. No ingestion of this system runs for 24 h (the longest ones are bounded well below it); a
  live run it reaped by mistake is not lost: its own ``finish_ingestion_run`` still records the real outcome.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from .valuation_worker_contract import VALUATION_WORKER_SOURCE_TYPE

logger = logging.getLogger(__name__)

ORPHAN_ERROR_SUMMARY = "orphaned: process restarted"
STALE_ERROR_SUMMARY = "orphaned: running for more than 24 h"
STALE_RUNNING_AFTER = timedelta(hours=24)  # no ingestion of this system legitimately runs this long
STALE_SWEEP_INTERVAL_SECONDS = 3600.0  # the stale-run reaper runs at most hourly
MARKER_INSTANCE = "process_instance"
MARKER_ROLE = "process_role"
MARKER_PID = "process_pid"
MARKER_STARTED_AT = "process_started_at"
MARKER_HOST = "process_host"
REAPED_AT = "reaped_at"
REAPED_BY = "reaped_by"


@dataclass(frozen=True)
class ProcessIdentity:
    instance: str
    pid: int
    started_at: datetime  # UTC; no run of this process starts before it
    host: str | None


@dataclass(frozen=True)
class WorkerOwnership:
    """Which runs a worker may reap: its role (marked runs) and the sources only it writes (unmarked, legacy runs)."""
    role: str
    legacy_source_types: tuple[str, ...] = ()
    legacy_source_codes: tuple[str, ...] = ()


# The nightly valuation worker: its phases are the only writers of source_type 'valuation_worker'
# (valuation_worker_contract). The IR sources it also polls inside the nightly (cvm/sec/ri/finnhub) are shared with the
# Investor Relations worker and the API, so their unmarked runs are left alone.
VALUATION_WORKER = WorkerOwnership("valuation_worker", legacy_source_types=(VALUATION_WORKER_SOURCE_TYPE,))
# The Investor Relations worker: 'sec_asfiled' is written only by the SEC-header-reading process (this worker); its
# other sources (cvm, sec, ri, cvm_statements) are shared with the valuation worker's nightly and the API.
IR_WORKER = WorkerOwnership("investor_relations_worker", legacy_source_codes=("sec_asfiled",))


class ReapingDatabase(Protocol):
    def reap_orphaned_ingestion_runs(
        self,
        *,
        role: str,
        process_instance: str,
        process_started_at: datetime,
        legacy_source_types: tuple[str, ...],
        legacy_source_codes: tuple[str, ...],
        reaped_at: datetime,
        reaped_by: str,
        error_summary: str,
    ) -> list[str]: ...


class StaleReapingDatabase(Protocol):
    def reap_stale_ingestion_runs(
        self,
        *,
        max_age: timedelta,
        reaped_by: str,
        error_summary: str,
        now: datetime | None = None,
    ) -> list[str]: ...


_lock = threading.Lock()
_identity: ProcessIdentity | None = None
_role: str | None = None


def _host() -> str | None:
    try:
        return socket.gethostname() or None
    except OSError:
        return None


def _new_identity() -> ProcessIdentity:
    return ProcessIdentity(instance=str(uuid4()), pid=os.getpid(), started_at=datetime.now(timezone.utc), host=_host())


def current() -> ProcessIdentity:
    """This process's identity: drawn once, redrawn in a forked child (a new pid is a new process)."""
    global _identity, _role
    with _lock:
        if _identity is None or _identity.pid != os.getpid():
            if _identity is not None:
                _role = None  # a forked child is not the worker its parent claimed to be
            _identity = _new_identity()
        return _identity


def role() -> str | None:
    current()  # a forked child drops the inherited role
    with _lock:
        return _role


def claim_worker_role(worker_role: str) -> ProcessIdentity:
    """Declare this process the (single) live process of ``worker_role``: its runs carry the role from now on, so the
    next process of the same worker reaps them if this one dies mid-run. Idempotent; a second, different role refuses."""
    global _role
    if not worker_role:
        raise ValueError("worker role required")
    identity = current()
    with _lock:
        if _role is not None and _role != worker_role:
            raise RuntimeError(f"process already claimed worker role {_role!r}")
        _role = worker_role
    return identity


def stamp(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """The run metadata with this process's marker (keys the caller already set win)."""
    identity = current()
    marker: dict[str, Any] = {
        MARKER_INSTANCE: identity.instance,
        MARKER_PID: identity.pid,
        MARKER_STARTED_AT: identity.started_at.isoformat(),
        MARKER_HOST: identity.host,
    }
    claimed = role()
    if claimed is not None:
        marker[MARKER_ROLE] = claimed
    return {**marker, **dict(metadata or {})}


def reap_orphans(database: ReapingDatabase, ownership: WorkerOwnership, *, identity: ProcessIdentity | None = None,
                 now: datetime | None = None) -> list[str]:
    """Mark ``failed`` the runs of ``ownership`` orphaned by a previous process (see the module docstring); returns their ids."""
    identity = identity or current()
    reaped_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reaped = database.reap_orphaned_ingestion_runs(
        role=ownership.role,
        process_instance=identity.instance,
        process_started_at=identity.started_at,
        legacy_source_types=ownership.legacy_source_types,
        legacy_source_codes=ownership.legacy_source_codes,
        reaped_at=reaped_at,
        reaped_by=f"{ownership.role}:{identity.instance}",
        error_summary=ORPHAN_ERROR_SUMMARY,
    )
    logger.info("ingestion orphan reaper: role=%s reaped=%d", ownership.role, len(reaped))
    return reaped


def reap_at_startup(database: ReapingDatabase, ownership: WorkerOwnership) -> list[str]:
    """The worker's startup step: claim the role, then reap. A failure is logged and never blocks the worker (the
    orphans then stay as they were before the reaper existed)."""
    identity = claim_worker_role(ownership.role)
    try:
        return reap_orphans(database, ownership, identity=identity)
    except Exception:
        logger.exception("ingestion orphan reaper failed: role=%s", ownership.role)
        return []


def reap_stale(database: StaleReapingDatabase, ownership: WorkerOwnership, *, identity: ProcessIdentity | None = None,
               now: datetime | None = None) -> list[str]:
    """Mark ``failed`` every run, of any role or none, still ``running`` more than ``STALE_RUNNING_AFTER`` after it
    started (the database clock; ``now`` is the in-memory double's); returns their ids. ``ownership`` names the reaper."""
    identity = identity or current()
    reaped = database.reap_stale_ingestion_runs(
        max_age=STALE_RUNNING_AFTER,
        reaped_by=f"{ownership.role}:{identity.instance}",
        error_summary=STALE_ERROR_SUMMARY,
        now=now,
    )
    logger.info("ingestion stale-run reaper: role=%s older_than=%s reaped=%d", ownership.role, STALE_RUNNING_AFTER, len(reaped))
    return reaped


def reap_stale_safely(database: StaleReapingDatabase, ownership: WorkerOwnership) -> list[str]:
    """``reap_stale`` for the worker: a failure is logged and never blocks it (the next sweep tries again)."""
    try:
        return reap_stale(database, ownership)
    except Exception:
        logger.exception("ingestion stale-run reaper failed: role=%s", ownership.role)
        return []


class PeriodicReaper:
    """Calls ``reap`` at most once per ``interval_seconds`` of a monotonic clock; the first call always runs."""

    def __init__(self, reap: Callable[[], Any], *, interval_seconds: float = STALE_SWEEP_INTERVAL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._reap = reap
        self._interval = interval_seconds
        self._clock = clock
        self._last: float | None = None

    def seconds_until_due(self) -> float:
        if self._last is None:
            return 0.0
        return max(0.0, self._last + self._interval - self._clock())

    def due(self) -> bool:
        return self.seconds_until_due() <= 0.0

    def __call__(self) -> bool:
        """Run ``reap`` if due; True when it ran."""
        if not self.due():
            return False
        self._last = self._clock()
        self._reap()
        return True
