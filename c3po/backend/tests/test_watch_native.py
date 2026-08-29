import hashlib
import struct
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import Settings
from app.database import Database
from app.push_notifications import PushNotificationService
from app.watch_apns import APNsClient, APNsResponse
from app.watch_native import WatchAuthenticationError, WatchNativeService


class FakeAPNs:
    def __init__(self, *, status_code: int = 200, error: Exception | None = None):
        self.configured = True
        self.status_code = status_code
        self.error = error
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return APNsResponse(self.status_code)


def test_apns_sender_uses_es256_http2_contract_and_three_second_ceiling(tmp_path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "AuthKey.p8"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    calls = []

    class Response:
        status_code = 200
        def json(self): return {}

    configured = Settings(
        watch_apns_private_key_path=key_path,
        watch_apns_key_id="KEY1234567",
        watch_apns_team_id="TEAM123456",
        watch_apns_bundle_id="com.eduardocastro.ecops.watch",
        watch_apns_timeout_seconds=3,
    )
    client = APNsClient(configured, transport=lambda **kwargs: calls.append(kwargs) or Response())
    response = client.send(device_token="ab" * 32, payload={"aps": {"alert": "test"}})

    assert response.status_code == 200
    assert calls[0]["timeout"] == 3
    assert calls[0]["headers"]["apns-topic"] == "com.eduardocastro.ecops.watch"
    assert calls[0]["headers"]["apns-push-type"] == "alert"
    jwt = calls[0]["headers"]["authorization"].removeprefix("bearer ")
    assert len(jwt.split(".")) == 3


def settings() -> Settings:
    return Settings(
        database_url="",
        push_vapid_private_key="web-private",
        push_vapid_public_key="web-public",
        r2d2_experiment_code="watch-test",
    )


def register_watch(database: Database, apns: FakeAPNs) -> PushNotificationService:
    native = WatchNativeService(settings(), database)
    issued = native.issue_device_token(user_email="owner@example.com", name="Dudu Watch")
    native.register(
        authorization=f"Bearer {issued['watch_device_token']}",
        device_token="ab" * 32,
        categories=["job_failure"],
    )
    return PushNotificationService(
        settings(), database, sender=lambda **_kwargs: None, watch_sender=apns
    )


def test_watch_token_is_returned_once_but_only_sha256_is_stored() -> None:
    database = Database(settings())
    service = WatchNativeService(settings(), database)
    issued = service.issue_device_token(user_email="owner@example.com", name="Dudu Watch")

    assert len(issued["watch_device_token"]) >= 32
    stored = database._watch_device_credentials[0]
    assert stored["token_sha256"] == hashlib.sha256(
        issued["watch_device_token"].encode()
    ).hexdigest()
    assert issued["watch_device_token"] not in repr(stored)


def test_watch_registration_is_append_only_and_revocable() -> None:
    database = Database(settings())
    service = WatchNativeService(settings(), database)
    issued = service.issue_device_token(user_email="owner@example.com", name="Dudu Watch")
    authorization = f"Bearer {issued['watch_device_token']}"

    service.register(
        authorization=authorization,
        device_token="ab" * 32,
        categories=["job_failure"],
    )
    service.register(
        authorization=authorization,
        device_token="cd" * 32,
        categories=["mesa_reading"],
    )

    assert len(database._watch_subscriptions) == 2
    assert database._watch_subscriptions[0]["revoked_at"] is not None
    assert database.list_active_watch_subscriptions()[0]["device_token"] == "cd" * 32
    assert service.revoke(user_email="owner@example.com", credential_id=issued["id"])
    with pytest.raises(WatchAuthenticationError):
        service.authenticate(authorization)


def test_web_and_watch_share_one_event_claim_and_identical_body() -> None:
    database = Database(settings())
    apns = FakeAPNs()
    service = register_watch(database, apns)
    service.subscribe(
        user_email="owner@example.com",
        endpoint="https://push.example/device",
        p256dh="p256dh-value-long-enough",
        auth_key="auth-value-long-enough",
        categories=["job_failure"],
    )

    first = service.notify(
        category="job_failure",
        title="Job failed",
        body="Review the evidence",
        deep_link="/?view=health",
        event_key="job:one",
    )
    duplicate = service.notify(
        category="job_failure",
        title="Job failed",
        body="Review the evidence",
        deep_link="/?view=health",
        event_key="job:one",
    )

    assert first["attempted"] == 2
    assert first["sent"] == 2
    assert duplicate["attempted"] == 0
    assert len(apns.calls) == 1
    assert apns.calls[0]["payload"]["aps"]["alert"]["body"] == "Review the evidence"


def test_apns_failure_never_blocks_web_push_or_caller() -> None:
    database = Database(settings())
    apns = FakeAPNs(error=TimeoutError("APNs unavailable"))
    service = register_watch(database, apns)
    service.subscribe(
        user_email="owner@example.com",
        endpoint="https://push.example/device",
        p256dh="p256dh-value-long-enough",
        auth_key="auth-value-long-enough",
        categories=["job_failure"],
    )

    result = service.notify(
        category="job_failure", title="Job failed", body="Evidence",
        deep_link="/?view=health",
    )
    assert result["sent"] == 1
    assert result["failed"] == 1


def test_complication_refresh_is_background_and_idempotent() -> None:
    database = Database(settings())
    apns = FakeAPNs()
    service = register_watch(database, apns)
    summary = {"positive_episodes": 4, "decided_episodes": 15, "win_rate_percent": 26.7}

    first = service.refresh_watch_complication(summary=summary, event_key="metric:one")
    duplicate = service.refresh_watch_complication(summary=summary, event_key="metric:one")

    assert first["sent"] == 1
    assert duplicate["attempted"] == 0
    assert apns.calls[0]["push_type"] == "background"
    assert apns.calls[0]["payload"]["metric"]["display"] == "4W/15 · 26,7%"


def test_watch_bundle_is_neutral_and_contract_is_frozen() -> None:
    root = Path(__file__).resolve().parents[2]
    watch = root / "watch"
    forbidden = ("star wars", "c3po", "r2d2", "falcon", "darth", "jedi", "sith")
    bundle_files = [
        path for path in watch.rglob("*")
        if path.is_file() and path.suffix.lower() in {".swift", ".plist", ".json", ".yml", ".entitlements"}
    ]
    payload = "\n".join(path.read_text(encoding="utf-8") for path in bundle_files).lower()
    assert all(mark not in payload for mark in forbidden)
    assert "EC Ops" in (watch / "ECOps" / "Info.plist").read_text(encoding="utf-8")

    icons = watch / "ECOps" / "Assets.xcassets" / "AppIcon.appiconset"
    expected_dimensions = {
        "icon-48.png": (48, 48), "icon-55.png": (55, 55),
        "icon-58.png": (58, 58), "icon-80.png": (80, 80),
        "icon-87.png": (87, 87), "icon-88.png": (88, 88),
        "icon-100.png": (100, 100), "icon-172.png": (172, 172),
        "icon-196.png": (196, 196), "icon-216.png": (216, 216),
        "icon-1024.png": (1024, 1024),
    }
    for filename, dimensions in expected_dimensions.items():
        image = (icons / filename).read_bytes()
        assert image[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", image[16:24]) == dimensions
        assert image[25] == 2  # RGB, no alpha channel accepted by Apple icons.
        lowered = image.lower()
        assert all(mark.encode() not in lowered for mark in forbidden)

    contract = root / "docs" / "C3PO_WATCH_NATIVE_APP_V1.md"
    assert hashlib.sha256(contract.read_bytes()).hexdigest() == (
        "59c9c82c8795f02dbbe74e4d944720759593eaf661485c849d049921e6cfda45"
    )


def test_pipeline_stages_p8_without_committing_it() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/c3po-pipeline.yml").read_text(encoding="utf-8")
    compose = (root / "c3po/compose.yml").read_text(encoding="utf-8")
    migration = (root / "c3po/db/037_watch_native_push.sql").read_text(encoding="utf-8")

    assert "C3PO_WATCH_APNS_PRIVATE_KEY" in workflow
    assert "umask 077" in workflow
    assert "install -m 600" in workflow
    assert "/run/secrets/c3po-watch-apns.p8:ro" in compose
    assert "token_sha256" in migration
    assert "watch_device_token" not in migration
    assert not list(root.rglob("*.p8"))
