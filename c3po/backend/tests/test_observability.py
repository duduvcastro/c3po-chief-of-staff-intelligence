from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.config import Settings
from app.observability import (
    HealthcheckPing,
    _before_breadcrumb,
    _before_send,
    init_sentry,
)
from app.postgres_backup_upload import MAX_SINGLE_PUT_BYTES, upload_backup


def test_sentry_scrubber_removes_pii_secrets_and_query_strings() -> None:
    event = {
        "request": {
            "url": "https://example.test/path?token=secret",
            "query_string": "token=secret",
            "cookies": {"session": "secret"},
            "headers": {
                "Authorization": "Bearer secret",
                "Accept": "application/json",
            },
            "env": {"REMOTE_ADDR": "192.0.2.1"},
        },
        "user": {"email": "person@example.test"},
        "extra": {"api_key": "secret", "safe": "visible"},
    }

    scrubbed = _before_send(event, {})

    assert scrubbed["request"]["url"].endswith("?[Filtered]")
    assert scrubbed["request"]["query_string"] == "[Filtered]"
    assert "cookies" not in scrubbed["request"]
    assert "env" not in scrubbed["request"]
    assert scrubbed["request"]["headers"]["Authorization"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["Accept"] == "application/json"
    assert scrubbed["extra"]["api_key"] == "[Filtered]"
    assert scrubbed["extra"]["safe"] == "visible"
    assert "user" not in scrubbed

    crumb = _before_breadcrumb(
        {"data": {"url": "https://api.test/items?apiKey=secret"}}, {}
    )
    assert crumb["data"]["url"].endswith("?[Filtered]")


def test_sentry_is_default_off_and_rejects_non_saas_dsn(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr("app.observability.sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    assert init_sentry(Settings(sentry_dsn=""), service_name="test") is False
    assert calls == []

    with pytest.raises(RuntimeError, match="official sentry.io SaaS"):
        init_sentry(
            Settings(sentry_dsn="https://key@unexpected.example/1"),
            service_name="test",
        )


def test_sentry_has_no_traces_pii_or_local_variables(monkeypatch) -> None:
    calls = []
    tags = []
    monkeypatch.setattr("app.observability.sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        "app.observability.sentry_sdk.set_tag", lambda key, value: tags.append((key, value))
    )

    assert init_sentry(
        Settings(
            sentry_dsn="https://public@o1.ingest.us.sentry.io/123",
            environment="production",
            build_sha="abc123",
        ),
        service_name="valuation-worker",
    ) is True

    assert calls[0]["send_default_pii"] is False
    assert calls[0]["include_local_variables"] is False
    assert calls[0]["traces_sample_rate"] == 0.0
    assert calls[0]["release"] == "abc123"
    assert tags == [("c3po.service", "valuation-worker")]


def test_healthcheck_ping_uses_status_path_and_never_sends_payload(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    def fake_get(url, *, timeout):
        calls.append((url, timeout))
        return Response()

    monkeypatch.setattr("app.observability.httpx.get", fake_get)
    ping = HealthcheckPing("https://hc-ping.com/check-id", timeout_seconds=3.0)

    assert ping.ping("start") is True
    assert ping.ping("fail") is True
    assert ping.ping("success") is True
    assert calls == [
        ("https://hc-ping.com/check-id/start", 3.0),
        ("https://hc-ping.com/check-id/fail", 3.0),
        ("https://hc-ping.com/check-id", 3.0),
    ]
    assert HealthcheckPing("http://hc-ping.com/check-id").ping() is False
    assert HealthcheckPing("https://unexpected.example/check-id").ping() is False


class _FakeS3:
    def __init__(self) -> None:
        self.calls = []

    def put_object(self, **kwargs):
        body = kwargs["Body"]
        self.calls.append({**kwargs, "Body": body.read()})
        return {"ETag": '"etag"', "VersionId": "version-1"}


def test_backup_upload_is_content_addressed_append_only_and_monthly(
    tmp_path: Path, monkeypatch
) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"postgres-custom-dump")
    client = _FakeS3()
    monkeypatch.setattr("app.postgres_backup_upload._client", lambda _settings: client)
    settings = Settings(
        postgres_backup_bucket="c3po-backup",
        postgres_backup_access_key_id="write-only",
        postgres_backup_secret_access_key="secret",
        postgres_backup_prefix="postgres",
    )

    result = upload_backup(
        dump,
        session_date=date(2026, 9, 1),
        settings=settings,
    )

    assert len(client.calls) == 2
    assert "/daily/2026/09/01/" in client.calls[0]["Key"]
    assert "/monthly/2026/09/" in client.calls[1]["Key"]
    assert result["file_sha256"] in client.calls[0]["Key"]
    assert client.calls[0]["IfNoneMatch"] == "*"
    assert client.calls[0]["ServerSideEncryption"] == "AES256"
    assert client.calls[0]["StorageClass"] == "STANDARD"
    assert client.calls[0]["Metadata"]["sha256"] == result["file_sha256"]
    assert result["uploads"][0]["version_id"] == "version-1"


def test_backup_upload_rejects_missing_config_empty_and_oversized_files(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty.dump"
    empty.touch()
    with pytest.raises(RuntimeError, match="not configured"):
        upload_backup(
            empty,
            session_date=date(2026, 8, 27),
            settings=Settings(),
        )

    configured = Settings(
        postgres_backup_bucket="bucket",
        postgres_backup_access_key_id="key",
        postgres_backup_secret_access_key="secret",
    )
    with pytest.raises(RuntimeError, match="outside the single-PUT contract"):
        upload_backup(
            empty,
            session_date=date(2026, 8, 27),
            settings=configured,
        )

    oversized = tmp_path / "oversized.dump"
    with oversized.open("wb") as target:
        target.truncate(MAX_SINGLE_PUT_BYTES)
    with pytest.raises(RuntimeError, match="outside the single-PUT contract"):
        upload_backup(
            oversized,
            session_date=date(2026, 8, 27),
            settings=configured,
        )
