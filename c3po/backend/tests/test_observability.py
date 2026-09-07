from __future__ import annotations

from datetime import date
from pathlib import Path
import json

import pytest
from pydantic import ValidationError
import sentry_sdk
from sentry_sdk.transport import Transport
from sentry_sdk.tracing_utils import record_sql_queries

from app.config import Settings
from app.observability import (
    HealthcheckPing,
    _before_breadcrumb,
    _before_send,
    _trace_sample_rate,
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
                "CF-Connecting-IP": "192.0.2.125",
                "True-Client-IP": "192.0.2.125",
                "Forwarded": "for=192.0.2.125",
                "X-Internal-Identity": "private user",
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
    for header in ("CF-Connecting-IP", "True-Client-IP", "Forwarded", "X-Internal-Identity"):
        assert scrubbed["request"]["headers"][header] == "[Filtered]"
    assert scrubbed["extra"]["api_key"] == "[Filtered]"
    assert scrubbed["extra"]["safe"] == "visible"
    assert "user" not in scrubbed

    crumb = _before_breadcrumb(
        {"data": {
            "url": "https://api.test/items?apiKey=secret",
            "http.query": "email=person@example.test",
            "http.fragment": "private-fragment",
        }}, {}
    )
    assert crumb["data"]["url"].endswith("?[Filtered]")
    assert crumb["data"]["http.query"] == "[Filtered]"
    assert crumb["data"]["http.fragment"] == "[Filtered]"


def test_sentry_scrubber_removes_url_credentials_and_fragments() -> None:
    crumb = _before_breadcrumb({"data": {
        "url": "https://user:password@example.test/path#private-fragment",
    }}, {})

    assert crumb["data"]["url"] == "https://example.test/path"


@pytest.mark.parametrize("category", ["query", "db", "db.sql.query", "query.postgresql"])
def test_sentry_database_breadcrumbs_keep_timing_without_sql_or_parameters(category) -> None:
    crumb = {
        "category": category,
        "message": "SELECT 'private financial data'",
        "data": {"db.params": ["private financial data"]},
        "timestamp": 123,
    }
    expected = {"category": category, "timestamp": 123}

    assert _before_breadcrumb(crumb, {}) == expected
    # Defense for breadcrumbs attached to an event without going through the
    # add_breadcrumb hook (e.g. an event processor or a manually captured event).
    assert _before_send({"breadcrumbs": {"values": [crumb]}}, {}) == {
        "breadcrumbs": {"values": [expected]},
    }


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


def test_sentry_defaults_keep_tracing_off_even_with_a_sampled_parent(monkeypatch) -> None:
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
    assert calls[0]["traces_sampler"]({"parent_sampled": True}) == 0.0
    assert calls[0]["profiles_sample_rate"] == 0.0
    assert calls[0]["profile_session_sample_rate"] == 0.0
    assert calls[0]["enable_logs"] is False
    assert calls[0]["max_request_body_size"] == "never"
    assert calls[0]["trace_propagation_targets"] == []
    assert calls[0]["release"] == "abc123"
    assert tags == [("c3po.service", "valuation-worker")]


@pytest.mark.parametrize("rate", [-0.001, 0.0101, 1.0])
def test_sentry_rejects_trace_rates_outside_the_one_percent_limit(rate) -> None:
    with pytest.raises(ValidationError):
        Settings(sentry_traces_sample_rate=rate)


@pytest.mark.parametrize("parent_sampled", [None, False, True])
def test_sentry_trace_rate_is_not_overridden_by_upstream_sampling(parent_sampled) -> None:
    settings = Settings(sentry_traces_sample_rate=0.005)

    assert _trace_sample_rate(settings, {
        "asgi_scope": {"path": "/api/v1/one-pagers", "method": "POST"},
        "parent_sampled": parent_sampled,
    }) == 0.005


@pytest.mark.parametrize("path", [
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/system-health",
    "/api/v1/auth/session",
    "/api/v1/auth/activity",
    "/api/v1/alerts",
    "/api/v1/navigation-indicators",
    "/api/v1/server-usage",
    "/api/v1/server-usage/performance",
    "/api/v1/code-census",
    "/api/v1/telemetry/page-load",
])
def test_sentry_does_not_trace_health_polling_or_telemetry(path) -> None:
    assert _trace_sample_rate(Settings(sentry_traces_sample_rate=0.01), {
        "asgi_scope": {"path": path, "method": "GET"},
        "parent_sampled": True,
    }) == 0.0


def test_sentry_does_not_trace_cors_preflight() -> None:
    assert _trace_sample_rate(Settings(sentry_traces_sample_rate=0.01), {
        "asgi_scope": {"path": "/api/v1/one-pagers", "method": "OPTIONS"},
    }) == 0.0


def test_sentry_sdk_scrubs_errors_and_transactions_before_transport(monkeypatch) -> None:
    options = {}
    monkeypatch.setattr("app.observability.sentry_sdk.init", lambda **kwargs: options.update(kwargs))
    monkeypatch.setattr("app.observability.sentry_sdk.set_tag", lambda *_args: None)
    init_sentry(Settings(sentry_dsn="https://public@o1.ingest.us.sentry.io/123"), service_name="test")
    envelopes = []

    class LocalTransport(Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    # Use the real SDK and hooks, with an in-memory transport and no global
    # instrumentation. This validates the outbound envelopes without network.
    options.update(transport=LocalTransport, default_integrations=False, integrations=[])
    client = sentry_sdk.Client(**options)
    sql_marker = "-".join(("private", "financial", "account", "123"))
    try:
        with sentry_sdk.isolation_scope(), sentry_sdk.new_scope() as scope:
            scope.set_client(client)
            scope.set_user({"email": "person@example.test"})
            # This is the SDK helper used by its DB integrations. It records a
            # SQL breadcrumb even when transaction sampling is disabled.
            with record_sql_queries(None, f"SELECT '{sql_marker}'", None, None, False):
                pass
            try:
                raise RuntimeError("controlled local Sentry test")
            except RuntimeError as error:
                sentry_sdk.capture_exception(error)
            sentry_sdk.capture_event({
                "type": "transaction",
                "transaction": "/api/v1/one-pagers",
                "start_timestamp": 1,
                "timestamp": 2,
                "breadcrumbs": {"values": [{
                    "category": "query", "message": f"SELECT '{sql_marker}'",
                    "data": {"db.params": [sql_marker]},
                }]},
                "request": {
                    "url": "https://example.test/path?email=person@example.test",
                    "data": {"email": "person@example.test"},
                    "headers": {
                        "Authorization": "Bearer secret",
                        "cf-connecting-ip": "192.0.2.125",
                        "Accept": "application/json",
                    },
                },
                "spans": [
                    {"op": "db.sql.query", "description": "SELECT 'private data'",
                     "data": {"db.statement": "SELECT 'private data'"}},
                    {"op": "http.client", "description": "GET https://api.test/items?token=secret",
                     "data": {"url": "https://api.test/items?token=secret",
                              "http.query": "token=secret", "http.fragment": "private"}},
                ],
            })
    finally:
        client.close()

    events = [item.payload.json for envelope in envelopes for item in envelope.items
              if item.type in {"event", "transaction"}]
    error_event = next(event for event in events if "exception" in event)
    assert "user" not in error_event
    exception = error_event["exception"]["values"][0]
    assert exception["value"] == "controlled local Sentry test"
    assert exception["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in exception["stacktrace"]["frames"])
    query_crumb = next(crumb for crumb in error_event["breadcrumbs"]["values"]
                       if crumb["category"] == "query")
    assert "message" not in query_crumb
    assert "data" not in query_crumb
    transaction = next(event for event in events if event.get("type") == "transaction")
    assert "user" not in transaction
    assert "data" not in transaction["request"]
    assert transaction["request"]["url"].endswith("?[Filtered]")
    assert transaction["request"]["headers"]["Authorization"] == "[Filtered]"
    assert transaction["request"]["headers"]["cf-connecting-ip"] == "[Filtered]"
    assert transaction["request"]["headers"]["Accept"] == "application/json"
    database_span, http_span = transaction["spans"]
    assert "description" not in database_span
    assert "db.statement" not in database_span["data"]
    assert http_span["description"] == "GET https://api.test/items?[Filtered]"
    assert http_span["data"]["url"].endswith("?[Filtered]")
    assert http_span["data"]["http.query"] == "[Filtered]"
    assert http_span["data"]["http.fragment"] == "[Filtered]"
    assert sql_marker not in json.dumps(events)


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
