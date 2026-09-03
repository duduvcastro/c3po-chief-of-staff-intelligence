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


def test_new_signal_updates_header_and_can_escalate_existing_incident() -> None:
    service = _service()
    at = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    opened = service.signal(
        incident_key="governance-vulnerability",
        source="governance",
        severity="attention",
        title="Governance needs review",
        detail="unknown findings",
        deep_link="/?view=health",
        evidence={"status": "attention"},
        at=at,
    )

    escalated = service.signal(
        incident_key="governance-vulnerability",
        source="governance",
        severity="critical",
        title="Governança e vulnerabilidades requerem ação",
        detail="1 critical pending",
        deep_link="/?view=health&severity=critical",
        evidence={"status": "offline", "critical": 1},
        at=at + timedelta(minutes=1),
    )

    assert escalated["id"] == opened["id"]
    assert escalated["severity"] == "critical"
    assert escalated["title"] == "Governança e vulnerabilidades requerem ação"
    assert escalated["deep_link"] == "/?view=health&severity=critical"
    assert escalated["event_count"] == 2


def test_resolve_key_accepts_fixed_clock() -> None:
    service = _service()
    opened_at = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    resolved_at = opened_at + timedelta(minutes=1)
    service.signal(
        incident_key="fixed-clock",
        source="test",
        severity="attention",
        title="Fixed clock",
        detail="open",
        deep_link="/",
        evidence={"state": "open"},
        at=opened_at,
    )

    resolved = service.resolve_key("fixed-clock", "done", at=resolved_at)

    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert resolved["last_seen_at"] == resolved_at


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
