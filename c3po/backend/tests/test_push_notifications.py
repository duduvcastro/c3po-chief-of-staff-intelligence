import json
from datetime import datetime, timezone
from pathlib import Path

from pywebpush import WebPushException

from app.config import Settings
from app.database import Database
from app.access_control import required_capability
from app.push_notifications import PushNotificationService


def _settings() -> Settings:
    return Settings(
        database_url="",
        push_vapid_private_key="private-vapid-key",
        push_vapid_public_key="public-vapid-key",
        push_vapid_subject="mailto:alerts@example.com",
        push_timeout_seconds=2.5,
    )


def _subscribe(
    service: PushNotificationService,
    endpoint: str,
    categories: list[str],
) -> None:
    service.subscribe(
        user_email="owner@example.com",
        endpoint=endpoint,
        p256dh="p256dh-value-long-enough",
        auth_key="auth-value-long-enough",
        categories=categories,
    )


def test_push_delivery_is_filtered_idempotent_and_uses_short_timeout() -> None:
    calls: list[dict] = []

    def sender(**kwargs):
        calls.append(kwargs)
        return type("Response", (), {"status_code": 201})()

    service = PushNotificationService(_settings(), Database(_settings()), sender=sender)
    _subscribe(service, "https://push.example/one", ["job_failure"])
    _subscribe(service, "https://push.example/two", ["mesa_reading"])

    first = service.notify(
        category="job_failure",
        title="Backup failed",
        body="Review the evidence",
        deep_link="/?view=health",
        event_key="backup:2026-08-28",
    )
    duplicate = service.notify(
        category="job_failure",
        title="Backup failed",
        body="Review the evidence",
        deep_link="/?view=health",
        event_key="backup:2026-08-28",
    )

    assert first == {
        "configured": True,
        "attempted": 1,
        "sent": 1,
        "failed": 0,
        "expired": 0,
    }
    assert duplicate["attempted"] == 0
    assert len(calls) == 1
    assert calls[0]["timeout"] == 2.5
    assert calls[0]["ttl"] == 300
    assert calls[0]["vapid_claims"] == {"sub": "mailto:alerts@example.com"}
    assert json.loads(calls[0]["data"])["deep_link"] == "/?view=health"


def test_expired_subscription_is_revoked_without_raising() -> None:
    response = type("Response", (), {"status_code": 410})()

    def sender(**_kwargs):
        raise WebPushException("expired", response=response)

    settings = _settings()
    database = Database(settings)
    service = PushNotificationService(settings, database, sender=sender)
    _subscribe(service, "https://push.example/expired", ["governance_critical"])

    result = service.notify(
        category="governance_critical",
        title="Governance requires action",
        body="One high advisory is open",
        deep_link="/?view=health",
    )

    assert result["expired"] == 1
    assert result["failed"] == 0
    assert database.list_active_push_subscriptions() == []
    assert database._push_delivery_events[0]["status"] == "expired"


def test_sender_failure_never_escapes_to_the_calling_job() -> None:
    def sender(**_kwargs):
        raise RuntimeError("provider unavailable")

    service = PushNotificationService(_settings(), Database(_settings()), sender=sender)
    _subscribe(service, "https://push.example/failure", ["job_failure"])

    result = service.notify(
        category="job_failure",
        title="Job failed",
        body="Raw failure remains in the evidence",
        deep_link="/?view=health",
    )

    assert result["attempted"] == 1
    assert result["failed"] == 1


def test_subscription_updates_are_append_only_with_logical_revocation() -> None:
    settings = _settings()
    database = Database(settings)
    service = PushNotificationService(settings, database, sender=lambda **_kwargs: None)
    _subscribe(service, "https://push.example/device", ["job_failure"])
    _subscribe(service, "https://push.example/device", ["mesa_reading"])

    assert len(database._push_subscriptions) == 2
    assert database._push_subscriptions[0]["revoked_at"] is not None
    assert database.list_active_push_subscriptions()[0]["categories"] == ["mesa_reading"]


def test_mobile_push_contract_has_no_fetch_or_cache_handler() -> None:
    root = Path(__file__).resolve().parents[2]
    worker = (root / "frontend" / "public" / "push-sw.js").read_text(encoding="utf-8")
    page = (root / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    migration = (root / "db" / "033_push_notifications.sql").read_text(encoding="utf-8")
    workflow = (root.parent / ".github" / "workflows" / "c3po-pipeline.yml").read_text(encoding="utf-8")

    assert 'addEventListener("push"' in worker
    assert 'addEventListener("notificationclick"' in worker
    assert 'addEventListener("fetch"' not in worker
    assert "caches." not in worker
    assert "Notification.requestPermission()" in page
    assert "Ativar alertas" in page
    assert "WHERE revoked_at IS NULL" in migration
    assert "C3PO_PUSH_VAPID_PRIVATE_KEY" in workflow
    assert "C3PO_PUSH_VAPID_PUBLIC_KEY" in workflow
    assert 'required_capability("/api/v1/push/subscribe", "POST")' not in workflow
    assert required_capability("/api/v1/push/subscribe", "POST") == "read"
    assert required_capability("/api/v1/push/unsubscribe", "POST") == "read"
    assert required_capability("/api/v1/push/test", "POST") == "owner"


def test_frozen_contract_is_byte_identical_to_the_signed_hash() -> None:
    import hashlib

    path = Path(__file__).resolve().parents[2] / "docs" / "C3PO_MOBILE_PUSH_V2.md"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "901971e5d0941e98cf18b80f22940241c54dc082ef4d707ce666aaa4f85bc4fa"
    )


def test_database_delivery_diagnostics_do_not_store_endpoint_or_keys() -> None:
    database = Database(_settings())
    database.record_push_delivery(
        event_key=None,
        subscription_id="subscription-id",
        category="test",
        delivery_status="sent",
        response_status=201,
        error_class=None,
        attempted_at=datetime.now(timezone.utc),
    )
    assert set(database._push_delivery_events[0]) == {
        "id",
        "event_key",
        "subscription_id",
        "category",
        "status",
        "response_status",
        "error_class",
        "attempted_at",
    }
