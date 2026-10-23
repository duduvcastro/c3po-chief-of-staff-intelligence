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


# --- Incident hygiene (owner complaint 20/10/2026: one CRITICAL incident per night) ---

from datetime import date, timezone  # noqa: E402
from typing import Any  # noqa: E402

from app.r2d2_cash_yield import CashYieldDataError  # noqa: E402
from app.valuation_worker import (  # noqa: E402
    PHASE_FAILURE_CRITICAL_NIGHTS,
    phase_failure_severity,
    phase_incident_key,
)


class _PushRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def notify(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {}


def _phase_incidents(database: Database) -> list[dict[str, Any]]:
    return [
        item for item in database.list_operational_incidents(limit=100)
        if item["incident_key"].startswith("notification:job_failure:valuation-phase-failure:")
    ]


def _night(database: Database, phase: OffhoursPhase, day: date, push: Any = None,
           hours: tuple[int, ...] = (6,)) -> list[str]:
    statuses = []
    for hour in hours:
        result = run_worker_iteration(
            database,
            now=datetime(day.year, day.month, day.day, hour, 0, tzinfo=SAO_PAULO),
            canonical_due=False,
            canonical_operation=lambda: None,
            offhours_phases=(phase,),
            push_notifications=push,
        )
        statuses.append(result.phase_statuses.get(phase.key, ""))
    return statuses


def test_severity_rule_is_attention_then_critical_by_persistence_or_data_fault() -> None:
    assert PHASE_FAILURE_CRITICAL_NIGHTS == 2
    assert phase_failure_severity(consecutive_nights=1, data_fault=False) == "attention"
    assert phase_failure_severity(consecutive_nights=2, data_fault=False) == "critical"
    assert phase_failure_severity(consecutive_nights=7, data_fault=False) == "critical"
    assert phase_failure_severity(consecutive_nights=1, data_fault=True) == "critical"


def test_repeated_nightly_failures_collapse_into_one_incident_that_escalates() -> None:
    database = _database()
    push = _PushRecorder()

    def fail() -> None:
        raise RuntimeError("provider outage https://example.invalid/?api_token=x")

    phase = OffhoursPhase("cash_yield", lambda: None, fail, start_hour=6, end_hour=10)
    # Night 1: three attempts inside the window -> one incident, attention, no push.
    assert _night(database, phase, date(2026, 10, 13), push, hours=(6, 7, 9)) == ["failed"] * 3
    incidents = _phase_incidents(database)
    assert len(incidents) == 1
    assert incidents[0]["incident_key"] == phase_incident_key("cash_yield")
    assert incidents[0]["severity"] == "attention"
    assert incidents[0]["event_count"] == 1
    assert push.calls == []
    # The exception message (which may carry a URL) never reaches the ledger.
    assert "api_token" not in incidents[0]["detail"]
    assert "api_token" not in str(incidents[0]["evidence"])

    # Night 2: same incident escalates to critical and pushes once.
    _night(database, phase, date(2026, 10, 14), push, hours=(6, 7))
    incidents = _phase_incidents(database)
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["evidence"]["consecutive_nights"] == 2
    assert incidents[0]["evidence"]["episode_first_night"] == "2026-10-13"
    assert len(push.calls) == 2  # one call per failing attempt; claimed once by event_key
    assert {call["event_key"] for call in push.calls} == {
        "valuation-phase-failure:cash_yield:episode:2026-10-13"
    }
    assert all(call["record_incident"] is False for call in push.calls)

    # Nights 3..6 (with the weekend gap): still ONE incident; one event per night.
    for day in (15, 16, 19, 20):
        _night(database, phase, date(2026, 10, day), push)
    incidents = _phase_incidents(database)
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["evidence"]["consecutive_nights"] == 8
    assert incidents[0]["evidence"]["night"] == "2026-10-20"
    # opened + night 2 observed + escalation + 4 later nights
    assert incidents[0]["event_count"] == 7


def test_data_fault_is_critical_on_the_first_night() -> None:
    database = _database()

    def fault() -> None:
        raise CashYieldDataError("Treasury 13-week Coupon Equivalent is negative")

    phase = OffhoursPhase("cash_yield", lambda: None, fault, start_hour=6, end_hour=10)
    push = _PushRecorder()
    _night(database, phase, date(2026, 10, 13), push)
    incidents = _phase_incidents(database)
    assert [item["severity"] for item in incidents] == ["critical"]
    assert incidents[0]["evidence"]["fault"] == "data"
    assert len(push.calls) == 1


def test_recovery_resolves_the_open_incident_and_legacy_dated_ones() -> None:
    database = _database()
    for day in ("2026-10-13", "2026-10-14"):
        database.record_operational_incident(
            incident_key=f"notification:job_failure:valuation-phase-failure:cash_yield:{day}",
            source="worker", severity="critical", title="R2D2 cash-yield accounting cycle failed",
            detail="CashYieldDataError: off-hours phase will retry", deep_link="/?view=health",
            evidence={"category": "job_failure"}, evidence_sha256="0" * 64,
            at=datetime.fromisoformat(f"{day}T09:00:00+00:00"),
        )
    # Another phase's legacy incident must stay open.
    database.record_operational_incident(
        incident_key="notification:job_failure:valuation-phase-failure:v3_shadow:2026-10-14",
        source="worker", severity="critical", title="other", detail="other",
        deep_link="/?view=health", evidence={}, evidence_sha256="1" * 64,
        at=datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc),
    )
    attempts = 0

    def fail_then_recover() -> dict[str, str]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("feed unavailable")
        return {"status": "pending_data"}

    phase = OffhoursPhase("cash_yield", lambda: None, fail_then_recover, start_hour=6, end_hour=10)
    assert _night(database, phase, date(2026, 10, 21), hours=(6, 7)) == ["failed", "succeeded"]

    by_key = {item["incident_key"]: item for item in _phase_incidents(database)}
    cash_keys = [key for key in by_key if ":cash_yield" in key]
    assert len(cash_keys) == 3
    assert all(by_key[key]["status"] == "resolved" for key in cash_keys)
    assert all(by_key[key]["actor_email"] == "system" for key in cash_keys)
    assert by_key[
        "notification:job_failure:valuation-phase-failure:v3_shadow:2026-10-14"
    ]["status"] == "open"


def test_a_new_failure_after_recovery_starts_a_new_attention_episode() -> None:
    database = _database()
    outcomes = iter([RuntimeError("a"), RuntimeError("b"), None, RuntimeError("c")])

    def scripted() -> dict[str, int]:
        outcome = next(outcomes)
        if outcome:
            raise outcome
        return {"ok": 1}

    phase = OffhoursPhase("peer_quality", lambda: None, scripted)
    _night(database, phase, date(2026, 10, 13), hours=(1,))
    _night(database, phase, date(2026, 10, 14), hours=(1, 2))
    [incident] = _phase_incidents(database)
    assert incident["status"] == "resolved"
    assert incident["severity"] == "critical"  # the closed episode reached night 2
    _night(database, phase, date(2026, 10, 15), hours=(1,))
    [incident] = _phase_incidents(database)
    assert incident["status"] == "open"
    assert incident["severity"] == "attention"  # re-derived, not inherited
    assert incident["evidence"]["consecutive_nights"] == 1
    assert incident["evidence"]["episode_first_night"] == "2026-10-15"


def test_incident_ledger_failure_never_breaks_the_worker(monkeypatch) -> None:
    database = _database()

    def broken(**_kwargs: Any) -> None:
        raise RuntimeError("ledger down")

    monkeypatch.setattr(database, "record_operational_incident", broken)
    monkeypatch.setattr(database, "list_operational_incidents", broken)

    def fail() -> None:
        raise RuntimeError("phase down")

    phase = OffhoursPhase("chewie", lambda: None, fail)
    assert _night(database, phase, date(2026, 10, 13), hours=(1,)) == ["failed"]
    ok = OffhoursPhase("chewie", lambda: None, lambda: {"ok": 1})
    assert _night(database, ok, date(2026, 10, 14), hours=(1,)) == ["succeeded"]
