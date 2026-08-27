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
_ALLOWED_HEALTHCHECK_HOSTS = {"hc-ping.com", "healthchecks.io"}


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc or not parsed.query:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, _FILTERED, ""))


def _scrub(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY.search(key):
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
    scrubbed.pop("user", None)
    return scrubbed


def _before_breadcrumb(
    crumb: dict[str, Any], _hint: dict[str, Any]
) -> dict[str, Any]:
    return _scrub(crumb)


def init_sentry(settings: Settings, *, service_name: str) -> bool:
    """Initialize SaaS error reporting only when production has an explicit DSN."""
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
        traces_sample_rate=0.0,
        send_default_pii=False,
        include_local_variables=False,
        max_breadcrumbs=50,
        server_name=service_name,
        before_send=_before_send,
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
