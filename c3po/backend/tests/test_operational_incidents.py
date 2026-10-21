from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.operational_incidents import OperationalIncidentService, evidence_sha256
from app.push_notifications import PushNotificationService


def _service() -> OperationalIncidentService:
    return OperationalIncidentService(Database(Settings(database_url="")))


def test_incident_lifecycle_is_append_only_and_evidence_hashed() -> None:
    service = _service()
    opened_at = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    evidence = {"report_sha256": "a" * 64, "critical": 2}

    opened = service.signal(
        incident_key="governance-vulnerability",
        source="governance",
        severity="critical",
        title="Governance requires action",
        detail="2 critical findings",
        deep_link="/?view=health",
        evidence=evidence,
        at=opened_at,
    )
    acknowledged = service.acknowledge(opened["id"], "owner@example.com")
    resolved = service.resolve(opened["id"], "owner@example.com", "Images rebuilt")

    assert opened["status"] == "open"
    assert opened["evidence_sha256"] == evidence_sha256(evidence)
    assert acknowledged is not None and acknowledged["status"] == "acknowledged"
    assert resolved is not None and resolved["status"] == "resolved"
    assert resolved["event_count"] == 3
    assert resolved["detail"] == "Images rebuilt"


def test_identical_observation_is_idempotent_and_new_signal_reopens() -> None:
    service = _service()
    at = datetime.now(timezone.utc)
    kwargs = {
        "incident_key": "job:cash-yield",
        "source": "worker",
        "severity": "attention",
        "title": "Cash yield failed",
        "detail": "exit 1",
        "deep_link": "/?view=health",
        "evidence": {"exit_code": 1},
    }

    first = service.signal(**kwargs, at=at)
    duplicate = service.signal(**kwargs, at=at + timedelta(minutes=1))
    service.resolve(first["id"], "owner@example.com", "Retry completed")
    reopened = service.signal(**kwargs, at=at + timedelta(minutes=2))

    assert duplicate["event_count"] == 1
    assert reopened["status"] == "open"
    assert reopened["event_count"] == 3


def test_sensitive_evidence_keys_are_rejected() -> None:
    service = _service()
    with pytest.raises(ValueError, match="sensitive incident evidence key"):
        service.signal(
            incident_key="delivery",
            source="push",
            severity="attention",
            title="Delivery failed",
            detail="Provider rejected subscription",
            deep_link="/?view=health",
            evidence={"endpoint": "https://should-not-be-stored.example"},
        )


def test_critical_job_signal_reaches_ledger_even_without_vapid() -> None:
    settings = Settings(database_url="", push_vapid_private_key="", push_vapid_public_key="")
    database = Database(settings)
    push = PushNotificationService(settings, database)

    result = push.notify(
        category="job_failure",
        title="Backup failed",
        body="pg_dump exited with status 1",
        deep_link="/?view=health",
        event_key="backup:2026-08-29",
    )

    incidents = database.list_operational_incidents(limit=10)
    assert result["configured"] is False
    assert len(incidents) == 1
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["title"] == "Backup failed"


def test_open_since_tracks_the_current_unresolved_episode() -> None:
    service = _service()
    opened_at = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    kwargs = {
        "incident_key": "governance-vulnerability",
        "source": "governance",
        "severity": "attention",
        "title": "Governança requer ação",
        "detail": "Causas: lane",
        "deep_link": "/?view=health",
    }
    assert service.open_since("governance-vulnerability") is None

    opened = service.signal(**kwargs, evidence={"n": 1}, at=opened_at)
    service.signal(**kwargs, evidence={"n": 2}, at=opened_at + timedelta(hours=2))
    assert service.open_since("governance-vulnerability") == opened_at

    service.database.transition_operational_incident(
        incident_id=opened["id"], event_type="acknowledged", actor_email="owner@example.com",
        detail="seen", at=opened_at + timedelta(hours=3),
    )
    assert service.open_since("governance-vulnerability") == opened_at

    service.database.transition_operational_incident(
        incident_id=opened["id"], event_type="resolved", actor_email="owner@example.com",
        detail="fixed", at=opened_at + timedelta(hours=4),
    )
    assert service.open_since("governance-vulnerability") is None

    reopened_at = opened_at + timedelta(hours=30)
    service.signal(**kwargs, evidence={"n": 3}, at=reopened_at)
    assert service.open_since("governance-vulnerability") == reopened_at


def _signal(service: OperationalIncidentService, key: str, severity: str, at: datetime, n: int = 1):
    return service.signal(
        incident_key=key, source="worker", severity=severity, title="Phase failed",
        detail="RuntimeError", deep_link="/?view=health", evidence={"n": n}, at=at,
    )


def test_set_severity_changes_only_unresolved_incidents_and_is_recorded() -> None:
    service = _service()
    at = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
    opened = _signal(service, "phase", "attention", at)
    raised = service.set_severity(
        incident_key="phase", severity="critical", detail="Severity critical",
        evidence={"n": 1}, at=at + timedelta(days=1),
    )
    assert raised is not None and raised["severity"] == "critical"
    assert raised["event_count"] == 2 and raised["detail"] == "Severity critical"
    unchanged = service.set_severity(
        incident_key="phase", severity="critical", detail="again", evidence={"n": 1},
        at=at + timedelta(days=2),
    )
    assert unchanged is not None and unchanged["event_count"] == 2
    service.database.transition_operational_incident(
        incident_id=opened["id"], event_type="resolved", actor_email="system",
        detail="ok", at=at + timedelta(days=3),
    )
    closed = service.set_severity(
        incident_key="phase", severity="attention", detail="x", evidence={"n": 1},
        at=at + timedelta(days=4),
    )
    assert closed is not None and closed["severity"] == "critical" and closed["status"] == "resolved"
    assert service.set_severity(incident_key="absent", severity="critical", detail="x", evidence={}) is None
    with pytest.raises(ValueError, match="invalid incident severity"):
        service.set_severity(incident_key="phase", severity="warning", detail="x", evidence={})
    with pytest.raises(ValueError, match="sensitive incident evidence key"):
        service.set_severity(incident_key="phase", severity="critical", detail="x",
                             evidence={"api_token": "x"})


def test_resolve_recovered_family_closes_key_and_dated_siblings_only_when_covered() -> None:
    service = _service()
    at = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
    _signal(service, "job:phase", "attention", at)
    _signal(service, "job:phase:2026-10-13", "critical", at)
    _signal(service, "job:phase_other", "critical", at)
    _signal(service, "job:phase:late", "critical", at)
    _signal(service, "job:phase:late", "critical", at + timedelta(hours=5), n=2)  # failed again later

    resolved = service.resolve_recovered_family(
        "job:phase", observed_at=at + timedelta(hours=1), detail="recovered",
    )

    by_key = {item["incident_key"]: item["status"] for item in service.database.list_operational_incidents()}
    assert resolved == 2
    assert by_key == {
        "job:phase": "resolved",
        "job:phase:2026-10-13": "resolved",
        "job:phase_other": "open",       # not a sibling: no ':' boundary
        "job:phase:late": "open",        # seen after the recovery evidence
    }


def test_push_can_skip_the_incident_when_the_caller_keeps_its_own() -> None:
    settings = Settings(database_url="", push_vapid_private_key="", push_vapid_public_key="")
    database = Database(settings)
    PushNotificationService(settings, database).notify(
        category="job_failure", title="Phase failed", body="x", deep_link="/?view=health",
        event_key="valuation-phase-failure:cash_yield:episode:2026-10-13", record_incident=False,
    )
    assert database.list_operational_incidents(limit=10) == []


class _RecordingConnection:
    def __init__(self, rows: list) -> None:
        self.rows = list(rows)
        self.statements: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql: str, params: tuple = ()):
        self.statements.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def commit(self) -> None:
        self.statements.append(("COMMIT", ()))


@pytest.mark.parametrize("severity,state,updates", [
    ("attention", "opened", True),
    ("attention", "acknowledged", True),
    ("attention", "resolved", False),
    ("critical", "opened", False),
])
def test_set_severity_postgres_path_updates_and_appends_only_when_allowed(
    monkeypatch: pytest.MonkeyPatch, severity: str, state: str, updates: bool,
) -> None:
    database = Database(Settings(database_url=""))
    database.database_url = "postgresql://recorded.invalid/never-connected"
    connection = _RecordingConnection([("incident-id", severity), (state,)])
    monkeypatch.setattr(database, "connection", lambda: connection)
    monkeypatch.setattr(database, "operational_incident_by_key", lambda key: {"incident_key": key})

    database.set_operational_incident_severity(
        incident_key="phase", severity="critical", detail="Severity critical",
        evidence={"n": 2}, evidence_sha256="a" * 64, at=datetime(2026, 10, 14, tzinfo=timezone.utc),
    )

    sql = [statement for statement, _ in connection.statements]
    assert sql[0].startswith("SELECT pg_advisory_xact_lock")
    assert connection.statements[0][1] == ("operational-incident:phase",)
    assert any(s.startswith("UPDATE operational_incidents SET severity") for s in sql) is updates
    inserts = [item for item in connection.statements if item[0].startswith("INSERT INTO operational_incident_events")]
    assert len(inserts) == int(updates)
    if updates:
        assert "'observed'" in inserts[0][0]
        assert connection.statements[sql.index(next(s for s in sql if s.startswith("UPDATE")))][1] == ("critical", "incident-id")
    assert sql[-1] == "COMMIT"
    assert not any("DELETE" in s or "UPDATE operational_incident_events" in s for s in sql)
