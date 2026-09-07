from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration

from .config import Settings


logger = logging.getLogger("c3po.observability")

_FILTERED = "[Filtered]"
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|dsn|session)",
    re.IGNORECASE,
)
_SENSITIVE_FIELDS = {
    "query_string", "http.query", "http.fragment", "url.query", "url.fragment",
    "db.statement", "db.query.text", "db.params", "db.cursor",
}
_DIAGNOSTIC_HEADERS = {
    "accept", "accept-encoding", "content-type", "content-length",
    "content-encoding", "host", "user-agent", "cf-ray",
}
_ALLOWED_HEALTHCHECK_HOSTS = {"hc-ping.com", "healthchecks.io"}
# These endpoints are health probes, background badge/heartbeat polling, or
# our own performance telemetry. Their errors still pass through before_send.
_UNTRACED_PATHS = frozenset({
    "/api/v1/health",
    "/api/v1/system-health",
    "/api/v1/auth/session",
    "/api/v1/auth/activity",
    "/api/v1/alerts",
    "/api/v1/navigation-indicators",
    "/api/v1/server-usage",
    "/api/v1/server-usage/performance",
    "/api/v1/code-census",
    "/api/v1/telemetry/page-load",
})


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    return urlunsplit((
        parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path,
        _FILTERED if parsed.query else "", "",
    ))


def _scrub(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key) or key.lower() in _SENSITIVE_FIELDS:
        return _FILTERED
    if isinstance(value, dict):
        return {
            str(item_key): _scrub(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    if isinstance(value, str) and "://" in value:
        return _redact_url(value)
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    scrubbed = _scrub(event)
    request = scrubbed.get("request")
    if isinstance(request, dict):
        request["query_string"] = _FILTERED if request.get("query_string") else ""
        request.pop("cookies", None)
        request.pop("env", None)
        request.pop("data", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            # A denylist misses proxy-specific client IP and identity headers
            # (e.g. Cloudflare's CF-Connecting-IP). Keep diagnostic values only.
            request["headers"] = {
                name: value if name.lower() in _DIAGNOSTIC_HEADERS else _FILTERED
                for name, value in headers.items()
            }
    scrubbed.pop("user", None)
    breadcrumbs = scrubbed.get("breadcrumbs")
    if isinstance(breadcrumbs, dict) and isinstance(breadcrumbs.get("values"), list):
        breadcrumbs["values"] = [
            _before_breadcrumb(crumb, {}) if isinstance(crumb, dict) else crumb
            for crumb in breadcrumbs["values"]
        ]
    elif isinstance(breadcrumbs, list):
        scrubbed["breadcrumbs"] = [
            _before_breadcrumb(crumb, {}) if isinstance(crumb, dict) else crumb
            for crumb in breadcrumbs
        ]
    return scrubbed


def _before_breadcrumb(
    crumb: dict[str, Any], _hint: dict[str, Any]
) -> dict[str, Any]:
    scrubbed = _scrub(crumb)
    category = str(scrubbed.get("category", "")).lower()
    if category in {"query", "db"} or category.startswith(("query.", "db.")):
        # SDK database integrations also record SQL as breadcrumbs on errors,
        # independently of tracing. Keep timing/category, not SQL or parameters.
        scrubbed.pop("message", None)
        scrubbed.pop("data", None)
    return scrubbed


def _before_send_transaction(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any]:
    scrubbed = _before_send(event, hint)
    for span in scrubbed.get("spans", []):
        # Database timings remain useful without SQL text, which may contain
        # literal financial or personal data. Preserve operations and duration.
        if str(span.get("op", "")).startswith("db"):
            span.pop("description", None)
        data = span.get("data")
        if isinstance(data, dict):
            data.pop("db.statement", None)
            data.pop("db.query.text", None)
        description = span.get("description")
        if isinstance(description, str):
            # HTTP span descriptions can have a method before the URL.
            span["description"] = re.sub(
                r"https?://[^\s]+", lambda match: _redact_url(match.group()), description
            )
    return scrubbed


def _trace_sample_rate(settings: Settings, context: dict[str, Any]) -> float:
    scope = context.get("asgi_scope")
    if isinstance(scope, dict):
        path = str(scope.get("path", "")).rstrip("/")
        if path in _UNTRACED_PATHS or scope.get("method") == "OPTIONS":
            return 0.0
    # Do not inherit an upstream sampled=True decision: it could override both
    # our opt-out default and the configured 1% maximum.
    return min(max(settings.sentry_traces_sample_rate, 0.0), 0.01)


def init_sentry(settings: Settings, *, service_name: str) -> bool:
    """Initialize SaaS error reporting and opt-in, bounded performance tracing."""
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return False
    parsed_dsn = urlsplit(dsn)
    if (
        parsed_dsn.scheme != "https"
        or not (parsed_dsn.hostname or "").lower().endswith(".sentry.io")
    ):
        raise RuntimeError("C3PO_SENTRY_DSN must use the official sentry.io SaaS")
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.environment,
        release=settings.build_sha,
        sample_rate=settings.sentry_sample_rate,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        traces_sampler=lambda context: _trace_sample_rate(settings, context),
        profiles_sample_rate=0.0,
        profile_session_sample_rate=0.0,
        enable_logs=False,
        trace_propagation_targets=[],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        max_breadcrumbs=50,
        server_name=service_name,
        before_send=_before_send,
        before_send_transaction=_before_send_transaction,
        before_breadcrumb=_before_breadcrumb,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        ],
    )
    sentry_sdk.set_tag("c3po.service", service_name)
    return True


class HealthcheckPing:
    """Best-effort dead-man ping with no job output or exception payload."""

    def __init__(self, url: str, *, timeout_seconds: float = 5.0) -> None:
        self.url = url.strip().rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        if not self.url:
            return False
        parsed = urlsplit(self.url)
        hostname = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (
            hostname in _ALLOWED_HEALTHCHECK_HOSTS
            or hostname.endswith(".healthchecks.io")
        )

    def ping(self, status: str = "success") -> bool:
        if not self.configured:
            return False
        suffix = {"start": "/start", "fail": "/fail", "success": ""}.get(status)
        if suffix is None:
            raise ValueError(f"unsupported healthcheck status: {status}")
        try:
            response = httpx.get(
                f"{self.url}{suffix}", timeout=self.timeout_seconds
            )
            response.raise_for_status()
        except Exception:
            logger.warning(
                "Healthchecks ping failed for status=%s", status, exc_info=True
            )
            return False
        return True
