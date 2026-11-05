"""Local measured telemetry only; never infers a contracted quota or capacity."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic


def observation(*, complete_history: bool) -> dict:
    return {"schema": "FULL-UNIVERSE-OBSERVATIONS-v1", "history_complete": complete_history,
            "first_started_at": datetime.now(timezone.utc).isoformat(), "completed_invocations": 0,
            "interrupted_invocations": 0, "observed_duration_seconds": 0.0,
            "phase_duration_seconds": {}, "phase_calls": {}, "phase_failures": {},
            "cached_input_reads": 0, "cached_row_reads": 0, "input_transient_failures": 0}


def begin_invocation(state, path, save):
    stats = state.setdefault("observations", observation(complete_history=False))
    if state.get("active_invocation"):
        stats["interrupted_invocations"] += 1
        stats["history_complete"] = False  # the interrupted interval was not measured to its end
    state["active_invocation"] = {"started_at": datetime.now(timezone.utc).isoformat()}
    save(path, state)
    return monotonic()


def finish_invocation(state, path, save, started):
    stats = state["observations"]
    stats["completed_invocations"] += 1
    stats["observed_duration_seconds"] += max(0.0, monotonic() - started)
    stats["last_finished_at"] = datetime.now(timezone.utc).isoformat()
    state.pop("active_invocation", None)
    save(path, state)


@contextmanager
def phase(state, path, save, name):
    stats = state["observations"]
    started = monotonic()
    stats["phase_calls"][name] = stats["phase_calls"].get(name, 0) + 1
    try:
        yield
    except BaseException:
        stats["phase_failures"][name] = stats["phase_failures"].get(name, 0) + 1
        raise
    finally:
        stats["phase_duration_seconds"][name] = stats["phase_duration_seconds"].get(name, 0.0) + max(0.0, monotonic() - started)
        save(path, state)


def http_observation(*, complete_history: bool) -> dict:
    return {"schema": "FULL-UNIVERSE-HTTP-OBSERVATIONS-v1", "history_complete": complete_history,
            "attempts_started": 0, "responses": 0, "transport_failures": 0,
            "uncertain_inflight": 0, "response_bytes": 0, "observed_seconds": 0.0,
            "status_counts": {}, "by_provider": {}}


def http_started(state, provider):
    stats = state.setdefault("http_observations", http_observation(complete_history=False))
    stats["attempts_started"] += 1
    stats["uncertain_inflight"] += 1
    now = datetime.now(timezone.utc).isoformat()
    stats.setdefault("first_started_at", now)
    stats["last_started_at"] = now
    group = stats["by_provider"].setdefault(provider, {"attempts_started": 0, "responses": 0,
                                                    "transport_failures": 0, "response_bytes": 0})
    group["attempts_started"] += 1


def http_finished(state, provider, *, status, size, seconds):
    stats = state["http_observations"]
    group = stats["by_provider"][provider]
    stats["uncertain_inflight"] -= 1
    stats["observed_seconds"] += max(0.0, seconds)
    if status is None:
        stats["transport_failures"] += 1
        group["transport_failures"] += 1
    else:
        stats["responses"] += 1
        group["responses"] += 1
        stats["response_bytes"] += size
        group["response_bytes"] += size
        stats["status_counts"][str(status)] = stats["status_counts"].get(str(status), 0) + 1


def begin_stage(state, path, save):
    stats = state.setdefault("stage_observations", {"schema": "FULL-UNIVERSE-STAGE-OBSERVATIONS-v1",
                            "history_complete": True, "attempts": 0, "observed_seconds": 0.0,
                            "first_started_at": datetime.now(timezone.utc).isoformat()})
    if state.get("active_stage_attempt"):
        stats["history_complete"] = False
    state["active_stage_attempt"] = True
    stats["attempts"] += 1
    save(path, state)
    return monotonic()


def finish_stage(state, path, save, started, considered, inserted):
    stats = state["stage_observations"]
    stats["observed_seconds"] += max(0.0, monotonic() - started)
    stats["last_finished_at"] = datetime.now(timezone.utc).isoformat()
    stats["records_considered"] = considered
    stats["records_inserted_last_attempt"] = inserted
    state.pop("active_stage_attempt", None)
    save(path, state)
