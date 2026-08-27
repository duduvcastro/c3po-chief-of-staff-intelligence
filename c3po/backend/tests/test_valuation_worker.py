from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.database import Database
from app.valuation_worker import (
    OffhoursPhase,
    _cash_yield_http_client,
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


def test_cash_yield_uses_a_dedicated_slow_feed_timeout() -> None:
    settings = Settings(
        market_data_timeout_seconds=15.0,
        market_data_max_retries=2,
        r2d2_cash_yield_http_timeout_seconds=45.0,
    )

    client = _cash_yield_http_client(settings)

    assert client.timeout == 45.0
    assert client.max_retries == 2
    assert client.timeout != settings.market_data_timeout_seconds


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


def test_cash_yield_phase_waits_until_six_and_retries_before_ten() -> None:
    database = _database()
    calls: list[str] = []
    phase = OffhoursPhase(
        "cash_yield",
        lambda: None,
        lambda: calls.append("cash_yield"),
        start_hour=6,
        end_hour=10,
    )

    before = run_worker_iteration(
        database,
        now=datetime(2026, 8, 26, 1, 5, tzinfo=SAO_PAULO),
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(phase,),
    )
    assert calls == []
    assert before.phase_statuses == {"cash_yield": "pending"}
    assert before.next_wake_at == datetime(2026, 8, 26, 6, 0, tzinfo=SAO_PAULO)

    due = run_worker_iteration(
        database,
        now=before.next_wake_at,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(phase,),
    )
    assert calls == ["cash_yield"]
    assert due.phase_statuses == {"cash_yield": "succeeded"}


def test_cash_yield_phase_does_not_run_at_or_after_ten() -> None:
    database = _database()
    calls: list[str] = []

    result = run_worker_iteration(
        database,
        now=datetime(2026, 8, 26, 10, 0, tzinfo=SAO_PAULO),
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(
            OffhoursPhase(
                "cash_yield",
                lambda: None,
                lambda: calls.append("cash_yield"),
                start_hour=6,
                end_hour=10,
            ),
        ),
    )

    assert calls == []
    assert result.phase_statuses == {"cash_yield": "outside_window"}


def test_cash_yield_failure_alert_is_deduplicated_and_recovery_is_recorded() -> None:
    database = _database()
    attempts = 0

    def recover_on_third_attempt() -> dict[str, str]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("Treasury feed unavailable")
        return {"status": "posted"}

    phase = OffhoursPhase(
        "cash_yield",
        lambda: None,
        recover_on_third_attempt,
        start_hour=6,
        end_hour=10,
    )
    for now in (
        datetime(2026, 8, 26, 6, 0, tzinfo=SAO_PAULO),
        datetime(2026, 8, 26, 6, 30, tzinfo=SAO_PAULO),
        datetime(2026, 8, 26, 7, 0, tzinfo=SAO_PAULO),
    ):
        run_worker_iteration(
            database,
            now=now,
            canonical_due=False,
            canonical_operation=lambda: None,
            offhours_phases=(phase,),
        )

    failures = database.list_audit_events(action="r2d2.cash_yield.failed")
    recoveries = database.list_audit_events(action="r2d2.cash_yield.recovered")
    assert len(failures) == 1
    assert failures[0]["subject_id"] == "2026-08-26"
    assert failures[0]["detail"]["error"] == "RuntimeError: Treasury feed unavailable"
    assert len(recoveries) == 1
    assert recoveries[0]["subject_id"] == "2026-08-26"


class _PingRecorder:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def ping(self, status: str = "success") -> bool:
        self.statuses.append(status)
        return True


def test_dead_man_pings_worker_and_cash_yield_without_changing_result() -> None:
    database = _database()
    worker = _PingRecorder()
    cash = _PingRecorder()
    phase = OffhoursPhase(
        "cash_yield",
        lambda: None,
        lambda: {"status": "posted"},
        start_hour=6,
        end_hour=10,
    )

    result = run_worker_iteration(
        database,
        now=datetime(2026, 8, 26, 6, 0, tzinfo=SAO_PAULO),
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(phase,),
        healthchecks={"valuation": worker, "cash_yield": cash},  # type: ignore[dict-item]
    )

    assert result.phase_statuses == {"cash_yield": "succeeded"}
    assert worker.statuses == ["start", "success"]
    assert cash.statuses == ["start", "success"]


def test_dead_man_failure_ping_never_suppresses_retry() -> None:
    database = _database()
    worker = _PingRecorder()
    cash = _PingRecorder()

    def fail() -> None:
        raise RuntimeError("feed unavailable")

    now = datetime(2026, 8, 26, 6, 0, tzinfo=SAO_PAULO)
    result = run_worker_iteration(
        database,
        now=now,
        canonical_due=False,
        canonical_operation=lambda: None,
        offhours_phases=(
            OffhoursPhase("cash_yield", lambda: None, fail, start_hour=6, end_hour=10),
        ),
        healthchecks={"valuation": worker, "cash_yield": cash},  # type: ignore[dict-item]
    )

    assert result.phase_statuses == {"cash_yield": "failed"}
    assert result.next_wake_at == now + timedelta(minutes=30)
    assert worker.statuses == ["start", "fail"]
    assert cash.statuses == ["start", "fail"]
