from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.database import Database
from app.valuation_worker import (
    OffhoursPhase,
    next_midnight,
    run_worker_iteration,
    start_of_today,
)
from app.valuation_worker_contract import (
    VALUATION_WORKER_OFFHOURS_PHASES,
    VALUATION_WORKER_PHASES,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_worker_uses_sao_paulo_midnight() -> None:
    now = datetime(2026, 8, 6, 23, 58, 45, tzinfo=SAO_PAULO)

    assert start_of_today(now) == datetime(2026, 8, 6, 0, 0, tzinfo=SAO_PAULO)
    assert next_midnight(now) == datetime(2026, 8, 7, 0, 0, tzinfo=SAO_PAULO)


def _database() -> Database:
    return Database(Settings(database_url="", auth_cookie_secure=False))


def test_canonical_failure_does_not_block_any_offhours_phase() -> None:
    database = _database()
    now = datetime(2026, 8, 25, 1, 5, tzinfo=SAO_PAULO)
    calls: list[str] = []

    def fail_canonical() -> None:
        raise RuntimeError("canonical unavailable")

    phases = tuple(
        OffhoursPhase(
            key,
            lambda: None,
            lambda key=key: calls.append(key) or {key: 1},
        )
        for key in VALUATION_WORKER_OFFHOURS_PHASES
    )

    result = run_worker_iteration(
        database,
        now=now,
        canonical_due=True,
        canonical_operation=fail_canonical,
        offhours_phases=phases,
    )

    assert result.canonical_status == "failed"
    assert calls == list(VALUATION_WORKER_OFFHOURS_PHASES)
    assert result.phase_statuses == {key: "succeeded" for key in calls}
    assert result.next_wake_at == now + timedelta(minutes=15)
    runs = list(database._ingestion_runs.values())
    assert len(runs) == 1 + len(VALUATION_WORKER_OFFHOURS_PHASES)
    assert runs[0]["status"] == "failed"
    assert runs[0]["error_summary"] == "RuntimeError: canonical unavailable"
    assert all(
        run["metadata"]["uses_persisted_universe_fallback"] is True
        for run in runs[1:]
    )


def test_failed_offhours_phase_persists_error_and_retries_inside_window() -> None:
    database = _database()
    attempts = 0

    def flaky_phase() -> dict[str, int]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary provider outage")
        return {"B3": 1, "US": 1}

    phase = OffhoursPhase("peer_quality", lambda: None, flaky_phase)
    first_at = datetime(2026, 8, 25, 1, 10, tzinfo=SAO_PAULO)
    first = run_worker_iteration(
        database,
        now=first_at,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(phase,),
    )

    assert first.phase_statuses == {"peer_quality": "failed"}
    assert first.next_wake_at == first_at + timedelta(minutes=30)

    second = run_worker_iteration(
        database,
        now=first.next_wake_at,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(phase,),
    )

    assert second.phase_statuses == {"peer_quality": "succeeded"}
    assert second.next_wake_at == next_midnight(first.next_wake_at)
    code = VALUATION_WORKER_PHASES["peer_quality"]["code"]
    runs = [
        run for run in database._ingestion_runs.values()
        if run["source_code"] == code
    ]
    assert [run["status"] for run in runs] == ["failed", "succeeded"]
    assert runs[0]["error_summary"] == "RuntimeError: temporary provider outage"


def test_offhours_phase_never_runs_at_or_after_window_end() -> None:
    database = _database()
    calls: list[str] = []
    now = datetime(2026, 8, 25, 8, 0, tzinfo=SAO_PAULO)

    result = run_worker_iteration(
        database,
        now=now,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(
            OffhoursPhase("v2_data", lambda: None, lambda: calls.append("v2_data")),
        ),
    )

    assert calls == []
    assert result.phase_statuses == {"v2_data": "outside_window"}
    assert result.next_wake_at == next_midnight(now)
    assert database._ingestion_runs == {}


def test_pending_offhours_phase_wakes_at_one_without_running_early() -> None:
    database = _database()
    calls: list[str] = []
    now = datetime(2026, 8, 25, 0, 30, tzinfo=SAO_PAULO)

    result = run_worker_iteration(
        database,
        now=now,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(
            OffhoursPhase("chewie", lambda: None, lambda: calls.append("chewie")),
        ),
    )

    assert calls == []
    assert result.phase_statuses == {"chewie": "pending"}
    assert result.next_wake_at == datetime(2026, 8, 25, 1, 0, tzinfo=SAO_PAULO)
