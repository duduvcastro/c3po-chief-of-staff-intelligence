import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app.auth import AuthService, AuthenticationError, RateLimitError
from app.config import Settings
from app.database import Database


def test_login_code_email_uses_parser_friendly_plain_text(monkeypatch) -> None:
    settings = Settings(
        auth_code_minutes=10,
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    service = AuthService(settings, Database(settings))
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        service,
        "_send_text_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    service.send_code_email("123456", "member@example.com")

    assert sent == [
        (
            "123456 é seu código de acesso ao C3PO",
            "123456 é seu código de verificação para c3po.eduardocastro.com.br.\n\n"
            "Use este código para concluir seu login no C3PO. "
            "Ele expira em 10 minutos e funciona uma única vez.\n\n"
            "Se você não solicitou este acesso, ignore esta mensagem.",
            "member@example.com",
        )
    ]
    assert "<" not in sent[0][1]


def test_one_time_code_creates_session_and_cannot_be_reused(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
    )
    database = Database(settings)
    service = AuthService(settings, database)
    sent_codes: list[str] = []

    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda code, _email: sent_codes.append(code))

    challenge_id, expires_in, method, delivery = service.request_code(settings.auth_email, "127.0.0.1")
    assert delivery == ("123456", settings.auth_email)
    service.send_code_email(*delivery)
    assert expires_in == 600
    assert method == "email"
    assert sent_codes == ["123456"]

    token, expires_at, email = service.verify_code(challenge_id, "123456", "127.0.0.1")
    assert email == settings.auth_email
    assert expires_at > service.now()
    assert service.authenticate(token)["email"] == settings.auth_email

    with pytest.raises(AuthenticationError):
        service.verify_code(challenge_id, "123456", "127.0.0.1")


def test_invalid_code_is_rejected(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    service = AuthService(settings, database)
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda _code, _email: None)

    challenge_id, _, _, _ = service.request_code(settings.auth_email, "127.0.0.1")
    with pytest.raises(AuthenticationError):
        service.verify_code(challenge_id, "654321", "127.0.0.1")


def test_new_login_request_invalidates_previous_pending_challenge(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    service = AuthService(settings, database)
    codes = iter((111111, 222222))
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: next(codes))

    first, _, _, _ = service.request_code(settings.auth_email, "127.0.0.1")
    second, _, _, _ = service.request_code(settings.auth_email, "127.0.0.1")

    with pytest.raises(AuthenticationError):
        service.verify_code(first, "111111", "127.0.0.1")
    assert service.verify_code(second, "222222", "127.0.0.1")[2] == settings.auth_email


def test_login_request_rate_limit_is_enforced_independently_by_ip() -> None:
    settings = Settings(
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_request_limit_per_email=5,
        auth_request_limit_per_ip=2,
    )
    service = AuthService(settings, Database(settings))

    service.request_code("first@example.com", "203.0.113.10")
    service.request_code("second@example.com", "203.0.113.10")
    with pytest.raises(RateLimitError):
        service.request_code("third@example.com", "203.0.113.10")


def test_parallel_valid_verification_can_create_only_one_session(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    service = AuthService(settings, database)
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    challenge_id, _, _, _ = service.request_code(settings.auth_email, "127.0.0.1")

    def verify() -> bool:
        try:
            service.verify_code(challenge_id, "123456", "203.0.113.20")
            return True
        except AuthenticationError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _: verify(), range(8)))

    assert outcomes.count(True) == 1
    assert database.get_login_code(challenge_id)["attempts"] == 1


def test_login_requests_and_failures_are_audited(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    service = AuthService(settings, database)
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)

    challenge_id, _, _, _ = service.request_code(settings.auth_email, "203.0.113.30")
    with pytest.raises(AuthenticationError):
        service.verify_code(challenge_id, "654321", "203.0.113.30")

    requested = database.list_audit_events(action="auth.otp_requested")
    failed = database.list_audit_events(action="auth.otp_failed")
    assert requested[0]["detail"]["requested_ip"] == "203.0.113.30"
    assert failed[0]["detail"]["requested_ip"] == "203.0.113.30"


def test_login_verification_failure_limit_is_enforced_by_ip(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_verify_failure_limit_per_ip=2,
    )
    database = Database(settings)
    service = AuthService(settings, database)
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    challenge_id, _, _, _ = service.request_code(settings.auth_email, "203.0.113.31")

    for _ in range(2):
        with pytest.raises(AuthenticationError):
            service.verify_code(challenge_id, "654321", "203.0.113.31")
    with pytest.raises(RateLimitError):
        service.verify_code(challenge_id, "654321", "203.0.113.31")


def test_request_code_response_does_not_disclose_verification_method(monkeypatch) -> None:
    calls = iter((
        (str(uuid4()), 600, "totp", None),
        (str(uuid4()), 600, "email", None),
    ))
    monkeypatch.setattr(app_main.auth_service, "request_code", lambda *_args, **_kwargs: next(calls))

    with TestClient(app_main.app) as client:
        totp = client.post("/api/v1/auth/request-code", json={"email": "one@example.com"})
        email = client.post("/api/v1/auth/request-code", json={"email": "two@example.com"})

    assert totp.status_code == email.status_code == 200
    assert set(totp.json()) == set(email.json()) == {"challenge_id", "expires_in_seconds", "message"}
    assert totp.json()["message"] == email.json()["message"]


def test_request_ip_uses_valid_cloudflare_ip_and_ignores_forwarded_header() -> None:
    with TestClient(app_main.app) as client:
        request = client.build_request(
            "POST",
            "/api/v1/auth/request-code",
            headers={
                "CF-Connecting-IP": "203.0.113.41",
                "X-Forwarded-For": "198.51.100.99",
            },
            json={"email": "unknown@example.com"},
        )
        response = client.send(request)

    assert response.status_code == 200
    events = app_main.database.list_audit_events(action="auth.otp_requested")
    assert events[0]["detail"]["requested_ip"] == "203.0.113.41"


def test_totp_setup_login_replay_protection_and_email_recovery(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])
    sent_codes: list[str] = []
    monkeypatch.setattr(service, "send_code_email", lambda code, _email: sent_codes.append(code))

    setup = service.begin_totp_setup(settings.auth_email)
    assert setup["otpauth_uri"].startswith("otpauth://totp/C3PO%3A")
    assert setup["qr_code_data_url"].startswith("data:image/svg+xml;base64,")
    setup_step = int(clock["now"].timestamp()) // 30
    service.confirm_totp_setup(settings.auth_email, service.totp_code(str(setup["secret"]), setup_step))
    assert service.totp_enabled(settings.auth_email)

    clock["now"] += timedelta(seconds=30)
    challenge_id, _, method, delivery = service.request_code(settings.auth_email, "127.0.0.1")
    assert method == "totp"
    assert delivery is None
    assert sent_codes == []
    login_step = int(clock["now"].timestamp()) // 30
    login_code = service.totp_code(str(setup["secret"]), login_step)
    token, _, _ = service.verify_code(challenge_id, login_code, "127.0.0.1")
    assert service.authenticate(token) is not None

    replay_challenge, _, replay_method, _ = service.request_code(settings.auth_email, "127.0.0.2")
    assert replay_method == "totp"
    with pytest.raises(AuthenticationError):
        service.verify_code(replay_challenge, login_code, "127.0.0.2")

    email_challenge, _, email_method, email_delivery = service.request_code(
        settings.auth_email,
        "127.0.0.3",
        delivery_method="email",
    )
    assert email_method == "email"
    assert email_delivery is not None
    service.send_code_email(*email_delivery)
    assert len(sent_codes) == 1
    recovered_token, _, _ = service.verify_code(email_challenge, sent_codes[0], "127.0.0.3")
    assert service.authenticate(recovered_token) is not None


def test_totp_setup_rejects_invalid_code_and_expires(monkeypatch) -> None:
    settings = Settings(
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])

    service.begin_totp_setup(settings.auth_email)
    with pytest.raises(AuthenticationError):
        service.confirm_totp_setup(settings.auth_email, "000000")
    clock["now"] += timedelta(minutes=11)
    with pytest.raises(AuthenticationError, match="expirou"):
        service.confirm_totp_setup(settings.auth_email, "000000")


def test_totp_reconfiguration_keeps_old_secret_until_new_code_is_confirmed(monkeypatch) -> None:
    settings = Settings(
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    service = AuthService(settings, database)
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: now)

    original = service.begin_totp_setup(settings.auth_email)
    step = int(now.timestamp()) // 30
    service.confirm_totp_setup(settings.auth_email, service.totp_code(str(original["secret"]), step))

    replacement = service.begin_totp_setup(settings.auth_email, replace=True)
    credential = database.get_totp_credential(settings.auth_email)
    assert credential is not None
    assert service.decrypt_totp_secret(credential["encrypted_secret"]) == original["secret"]
    assert service.totp_enabled(settings.auth_email)

    service.confirm_totp_setup(settings.auth_email, service.totp_code(str(replacement["secret"]), step))
    credential = database.get_totp_credential(settings.auth_email)
    assert credential is not None
    assert service.decrypt_totp_secret(credential["encrypted_secret"]) == replacement["secret"]
    assert credential["pending_encrypted_secret"] is None


def test_totp_setup_route_requires_and_receives_authenticated_session() -> None:
    email = "totp-route@example.com"
    app_main.database.upsert_access_user(
        {
            "email": email,
            "display_name": "TOTP Route",
            "role": "member",
            "is_active": True,
            "permissions": ["command"],
            "created_by": app_main.settings.auth_email,
        }
    )
    token = "totp-route-session-token"
    now = datetime.now(timezone.utc)
    app_main.database.create_session(
        {
            "id": str(uuid4()),
            "email": email,
            "token_hash": app_main.auth_service.session_hash(token),
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
            "last_seen_at": now,
            "created_ip": "127.0.0.1",
        }
    )
    previous_required = app_main.settings.auth_required
    app_main.settings.auth_required = True
    try:
        with TestClient(app_main.app) as client:
            denied = client.post("/api/v1/auth/totp/setup")
            client.cookies.set(app_main.SESSION_COOKIE, token)
            allowed = client.post("/api/v1/auth/totp/setup")

        assert denied.status_code == 401
        assert allowed.status_code == 200
        assert allowed.json()["qr_code_data_url"].startswith("data:image/svg+xml;base64,")
    finally:
        app_main.settings.auth_required = previous_required


def test_allowlisted_member_receives_code_and_permissions_follow_session(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command", "finance"])
    database.upsert_access_user(
        {
            "email": "member@example.com",
            "display_name": "Member",
            "role": "member",
            "is_active": True,
            "permissions": ["weather", "markets"],
            "created_by": settings.auth_email,
        }
    )
    service = AuthService(settings, database)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda code, email: sent.append((code, email)))

    challenge_id, _, _, delivery = service.request_code("MEMBER@example.com", "127.0.0.1")
    assert delivery is not None
    service.send_code_email(*delivery)
    assert sent == [("123456", "member@example.com")]
    token, _, _ = service.verify_code(challenge_id, "123456", "127.0.0.1")
    session = service.authenticate(token)
    assert session is not None
    assert session["role"] == "member"
    assert session["permissions"] == ["weather", "markets"]
    assert session["capabilities"] == ["read"]


def test_member_session_expires_after_thirty_minutes_without_human_activity(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
        auth_session_hours=24,
        auth_member_idle_minutes=30,
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    database.upsert_access_user(
        {
            "email": "member@example.com",
            "display_name": "Member",
            "role": "member",
            "is_active": True,
            "permissions": ["weather"],
            "created_by": settings.auth_email,
        }
    )
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda _code, _email: None)

    challenge_id, _, _, delivery = service.request_code("member@example.com", "127.0.0.1")
    assert delivery is not None
    service.send_code_email(*delivery)
    token, _, _ = service.verify_code(challenge_id, "123456", "127.0.0.1")
    clock["now"] += timedelta(minutes=29)
    assert service.authenticate(token) is not None
    clock["now"] += timedelta(minutes=2)
    assert service.authenticate(token) is None


def test_human_activity_renews_member_idle_window(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
        auth_session_hours=24,
        auth_member_idle_minutes=30,
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    database.upsert_access_user(
        {
            "email": "active@example.com",
            "display_name": "Active Member",
            "role": "member",
            "is_active": True,
            "permissions": ["markets"],
            "created_by": settings.auth_email,
        }
    )
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda _code, _email: None)

    challenge_id, _, _, delivery = service.request_code("active@example.com", "127.0.0.1")
    assert delivery is not None
    service.send_code_email(*delivery)
    token, _, _ = service.verify_code(challenge_id, "123456", "127.0.0.1")
    clock["now"] += timedelta(minutes=20)
    assert service.authenticate(token, touch_activity=True) is not None
    clock["now"] += timedelta(minutes=29)
    assert service.authenticate(token) is not None
    clock["now"] += timedelta(minutes=2)
    assert service.authenticate(token) is None


def test_owner_session_also_expires_after_thirty_minutes_of_inactivity(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
        auth_session_hours=2,
        auth_owner_session_hours=24,
        auth_member_idle_minutes=30,
    )
    database = Database(settings)
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda _code, _email: None)

    challenge_id, _, _, delivery = service.request_code(settings.auth_email, "127.0.0.1")
    assert delivery is not None
    service.send_code_email(*delivery)
    token, expires_at, _ = service.verify_code(challenge_id, "123456", "127.0.0.1")
    assert expires_at == clock["now"] + timedelta(hours=24)
    clock["now"] += timedelta(minutes=29)
    assert service.authenticate(token) is not None
    clock["now"] += timedelta(minutes=2)
    assert service.authenticate(token) is None


def test_human_activity_renews_owner_idle_window(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
        auth_owner_session_hours=24,
        auth_member_idle_minutes=30,
    )
    database = Database(settings)
    service = AuthService(settings, database)
    clock = {"now": datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(service, "now", lambda: clock["now"])
    monkeypatch.setattr("app.auth.secrets.randbelow", lambda _: 123456)
    monkeypatch.setattr(service, "send_code_email", lambda _code, _email: None)

    challenge_id, _, _, delivery = service.request_code(settings.auth_email, "127.0.0.1")
    assert delivery is not None
    service.send_code_email(*delivery)
    token, _, _ = service.verify_code(challenge_id, "123456", "127.0.0.1")
    clock["now"] += timedelta(minutes=20)
    assert service.authenticate(token, touch_activity=True) is not None
    clock["now"] += timedelta(minutes=29)
    assert service.authenticate(token) is not None
    clock["now"] += timedelta(minutes=2)
    assert service.authenticate(token) is None


def test_unknown_and_suspended_emails_never_receive_code(monkeypatch) -> None:
    settings = Settings(
        auth_required=True,
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
    )
    database = Database(settings)
    database.ensure_access_owner(settings.auth_email, ["command"])
    database.upsert_access_user(
        {
            "email": "suspended@example.com",
            "display_name": "Suspended",
            "role": "member",
            "is_active": False,
            "permissions": ["weather"],
            "created_by": settings.auth_email,
        }
    )
    service = AuthService(settings, database)
    sent: list[str] = []
    monkeypatch.setattr(service, "send_code_email", lambda _code, email: sent.append(email))

    service.request_code("unknown@example.com", "127.0.0.1")
    service.request_code("suspended@example.com", "127.0.0.2")
    assert sent == []


def test_member_permissions_are_enforced_by_api_middleware() -> None:
    email = "weather-only@example.com"
    app_main.database.upsert_access_user(
        {
            "email": email,
            "display_name": "Weather Only",
            "role": "member",
            "is_active": True,
            "permissions": ["weather"],
            "created_by": app_main.settings.auth_email,
        }
    )
    token = "member-session-token"
    now = datetime.now(timezone.utc)
    app_main.database.create_session(
        {
            "id": str(uuid4()),
            "email": email,
            "token_hash": app_main.auth_service.session_hash(token),
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
            "last_seen_at": now,
            "created_ip": "127.0.0.1",
        }
    )
    previous_required = app_main.settings.auth_required
    app_main.settings.auth_required = True
    try:
        with TestClient(app_main.app) as client:
            client.cookies.set(app_main.SESSION_COOKIE, token)
            session = client.get("/api/v1/auth/session")
            finance = client.get("/api/v1/open-finance")
            command = client.get("/api/v1/command-center")
            alerts = client.get("/api/v1/alerts")
            health = client.get("/api/v1/integrations")
            admin = client.get("/api/v1/admin/access-users")
        assert session.status_code == 200
        assert session.json()["permissions"] == ["weather"]
        assert finance.status_code == 403
        assert command.status_code == 403
        assert alerts.status_code == 403
        assert health.status_code == 403
        assert admin.status_code == 403
    finally:
        app_main.settings.auth_required = previous_required


def test_member_action_capabilities_are_enforced_by_api_middleware() -> None:
    email = "capabilities@example.com"
    app_main.database.upsert_access_user(
        {
            "email": email,
            "display_name": "Capabilities",
            "role": "member",
            "is_active": True,
            "permissions": ["onepager", "realtime", "relations"],
            "capabilities": ["read"],
            "created_by": app_main.settings.auth_email,
        }
    )
    token = "capability-session-token"
    now = datetime.now(timezone.utc)
    app_main.database.create_session(
        {
            "id": str(uuid4()),
            "email": email,
            "token_hash": app_main.auth_service.session_hash(token),
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
            "last_seen_at": now,
            "created_ip": "127.0.0.1",
        }
    )
    previous_required = app_main.settings.auth_required
    app_main.settings.auth_required = True
    try:
        with TestClient(app_main.app) as client:
            client.cookies.set(app_main.SESSION_COOKIE, token)
            session = client.get("/api/v1/auth/session")
            history = client.get("/api/v1/one-pagers")
            generate_denied = client.post("/api/v1/one-pagers", json={})
            delete_denied = client.delete("/api/v1/realtime/portfolio/items/NOTHELD")
            manage_denied = client.post("/api/v1/investor-relations/sync")

            app_main.database.upsert_access_user(
                {
                    "email": email,
                    "display_name": "Capabilities",
                    "role": "member",
                    "is_active": True,
                    "permissions": ["onepager", "realtime", "relations"],
                    "capabilities": ["read", "onepager_generate", "delete"],
                    "created_by": app_main.settings.auth_email,
                }
            )
            generate_allowed = client.post("/api/v1/one-pagers", json={})
            delete_allowed = client.delete("/api/v1/realtime/portfolio/items/NOTHELD")
            manage_still_denied = client.post("/api/v1/investor-relations/sync")

        assert session.status_code == 200
        assert session.json()["capabilities"] == ["read"]
        assert history.status_code == 200
        assert generate_denied.status_code == 403
        assert delete_denied.status_code == 403
        assert manage_denied.status_code == 403
        assert generate_allowed.status_code == 422
        assert delete_allowed.status_code == 404
        assert manage_still_denied.status_code == 403
    finally:
        app_main.settings.auth_required = previous_required


def test_owner_can_manage_access_registry_and_cannot_delete_self() -> None:
    email = "helm-test@example.com"
    previous_required = app_main.settings.auth_required
    app_main.settings.auth_required = False
    try:
        with TestClient(app_main.app) as client:
            created = client.post(
                "/api/v1/admin/access-users",
                json={
                    "email": email,
                    "display_name": "Helm Test",
                    "is_active": True,
                    "permissions": ["weather", "markets"],
                    "capabilities": ["read", "onepager_generate"],
                },
            )
            updated = client.put(
                f"/api/v1/admin/access-users/{email}",
                json={
                    "display_name": "Helm Test Updated",
                    "is_active": False,
                    "permissions": ["weather"],
                    "capabilities": ["read", "delete"],
                },
            )
            owner_delete = client.delete(f"/api/v1/admin/access-users/{app_main.settings.auth_email}")
            deleted = client.delete(f"/api/v1/admin/access-users/{email}")
        assert created.status_code == 201
        created_user = next(item for item in created.json()["items"] if item["email"] == email)
        assert created_user["permissions"] == ["markets", "weather"]
        assert created_user["capabilities"] == ["read", "onepager_generate"]
        assert [item["key"] for item in created.json()["available_capabilities"]] == [
            "read", "onepager_generate", "delete",
        ]
        assert updated.status_code == 200
        updated_user = next(item for item in updated.json()["items"] if item["email"] == email)
        assert updated_user["is_active"] is False
        assert updated_user["permissions"] == ["weather"]
        assert updated_user["capabilities"] == ["read", "delete"]
        assert owner_delete.status_code == 422
        assert deleted.status_code == 200
        assert all(item["email"] != email for item in deleted.json()["items"])
    finally:
        app_main.settings.auth_required = previous_required


def test_login_notification_is_sent_to_security_owner(monkeypatch) -> None:
    settings = Settings(
        auth_email="eu@eduardocastro.com.br",
        auth_secret="a-secure-test-secret-with-more-than-32-characters",
        auth_cookie_secure=False,
    )
    service = AuthService(settings, Database(settings))
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        service,
        "_send_html_email",
        lambda subject, body, recipient: sent.append((subject, body, recipient)),
    )

    service.send_login_notification(
        email="member@example.com",
        display_name="Member Test",
        role="member",
        requested_ip="203.0.113.25",
        occurred_at=datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc),
        client_info={"device_type": "iPad", "os": "iPadOS 18.6", "browser": "Safari 18.6"},
    )

    assert len(sent) == 1
    assert sent[0][2] == settings.auth_email
    assert "Member Test" in sent[0][0]
    assert "member@example.com" in sent[0][1]
    assert "203.0.113.25" in sent[0][1]
    assert "12:30:00" in sent[0][1]
    assert "iPadOS 18.6" in sent[0][1]
    assert "Safari 18.6" in sent[0][1]


def test_notification_mailbox_overrides_legacy_exchange_credentials(monkeypatch) -> None:
    settings = Settings(
        exchange_server="legacy.example.com",
        exchange_user="eu@eduardocastro.com.br",
        exchange_app_password="legacy-password",
        notification_exchange_server="owa.intermedia.net",
        notification_exchange_user="c3po@eduardocastro.com.br",
        notification_exchange_app_password="notification-password",
    )
    service = AuthService(settings, Database(settings))
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return (
                b'<m:CreateItemResponse xmlns:m="http://schemas.microsoft.com/'
                b'exchange/services/2006/messages"><m:CreateItemResponseMessage '
                b'ResponseClass="Success" /></m:CreateItemResponse>'
            )

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.auth.urllib.request.urlopen", fake_urlopen)

    service._send_html_email("C3PO test", "Body", "recipient@example.com")

    expected_token = base64.b64encode(
        b"c3po@eduardocastro.com.br:notification-password"
    ).decode("ascii")
    assert captured == {
        "url": "https://owa.intermedia.net/EWS/Exchange.asmx",
        "authorization": f"Basic {expected_token}",
        "timeout": 20,
    }


@pytest.mark.parametrize(
    ("user_agent", "platform", "touch_points", "expected_device", "expected_os"),
    [
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.6 Mobile/15E148 Safari/604.1",
            "iPhone",
            5,
            "iPhone",
            "iOS 18.6",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/18.6 Mobile/15E148 Safari/604.1",
            "MacIntel",
            5,
            "iPad",
            "iPadOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
            "Win32",
            0,
            "Computador (desktop/laptop)",
            "Windows 10/11",
        ),
    ],
)
def test_client_device_description(
    user_agent: str,
    platform: str,
    touch_points: int,
    expected_device: str,
    expected_os: str,
) -> None:
    result = AuthService.describe_client(
        user_agent,
        platform=platform,
        max_touch_points=touch_points,
    )
    assert result["device_type"] == expected_device
    assert result["os"] == expected_os


def test_login_audit_event_is_available_to_radar_alerts(monkeypatch) -> None:
    email = "radar-login@example.com"
    now = datetime.now(timezone.utc)
    app_main.database.record_audit_event(
        email,
        "auth.login",
        "access_user",
        email,
        {
            "display_name": "Radar Login",
            "role": "member",
            "requested_ip": "198.51.100.17",
            "occurred_at": now.isoformat(),
            "client_info": {"device_type": "iPhone", "os": "iOS 18.6", "browser": "Safari 18.6"},
        },
    )
    monkeypatch.setattr(
        app_main.legacy,
        "read",
        lambda: {"generated_at": now.astimezone(), "decision_queue": []},
    )
    previous_required = app_main.settings.auth_required
    app_main.settings.auth_required = False
    try:
        with TestClient(app_main.app) as client:
            response = client.get("/api/v1/alerts")
        assert response.status_code == 200
        alert = next(item for item in response.json()["items"] if "Radar Login" in item["subject"])
        assert alert["severity"] == "Security"
        assert "198.51.100.17" in alert["action"]
        assert "iPhone" in alert["action"]
        assert "iOS 18.6" in alert["action"]
    finally:
        app_main.settings.auth_required = previous_required


def test_login_push_alert_identifies_only_the_user(monkeypatch) -> None:
    """EMENDA 2: o push de novo login diz apenas QUEM entrou; o detalhe de
    aparelho/IP/hora permanece no Radar Alerts (evento de auditoria)."""
    sent: list[dict] = []
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    monkeypatch.setattr(
        app_main.auth_service,
        "verify_code",
        lambda *_args, **_kwargs: ("token-login-push", expires, "login-push@example.com"),
    )
    monkeypatch.setattr(
        app_main.auth_service,
        "authenticate",
        lambda _token: {"email": "login-push@example.com", "display_name": "Dudu", "role": "owner"},
    )
    monkeypatch.setattr(
        app_main.database,
        "get_access_user",
        lambda _email: {"display_name": "Dudu", "role": "owner"},
    )
    monkeypatch.setattr(app_main, "deliver_login_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(
        app_main.push_notifications,
        "notify",
        lambda **kwargs: sent.append(kwargs) or {"status": "sent"},
    )

    with TestClient(app_main.app) as client:
        response = client.post(
            "/api/v1/auth/verify-code",
            json={"challenge_id": str(uuid4()), "code": "123456"},
        )

    assert response.status_code == 200
    login_pushes = [item for item in sent if item["category"] == "security_login"]
    assert len(login_pushes) == 1
    body = login_pushes[0]["body"]
    assert body == "Dudu (login-push@example.com)"
    assert "device_type" not in body and "\u00b7" not in body
