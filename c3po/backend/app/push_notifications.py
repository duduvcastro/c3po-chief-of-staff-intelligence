from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from pywebpush import WebPushException, webpush

from .config import Settings, get_settings
from .database import Database


logger = logging.getLogger("c3po.push_notifications")

PUSH_CATEGORIES = (
    "kill_criterion",
    "job_failure",
    "governance_critical",
    "mesa_reading",
    "disk_threshold",
    "security_login",
    "sell_win",
    "hourly_win_rate",
)
TEST_CATEGORY = "test"


def validate_push_categories(categories: list[str]) -> list[str]:
    normalized = sorted(set(categories))
    if any(category not in PUSH_CATEGORIES for category in normalized):
        raise ValueError("Unsupported push notification category")
    return normalized


def validate_push_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Push endpoint must be an HTTPS URL")
    return normalized


def validate_deep_link(deep_link: str) -> str:
    normalized = deep_link.strip()
    if not normalized.startswith("/") or normalized.startswith("//"):
        raise ValueError("Push deep link must be an application-relative path")
    return normalized


class PushNotificationService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        *,
        sender: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.sender = sender or webpush

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.push_vapid_private_key.strip()
            and self.settings.push_vapid_public_key.strip()
        )

    def status(self, user_email: str) -> dict[str, Any]:
        subscriptions = self.database.list_active_push_subscriptions(
            user_email=user_email,
        )
        return {
            "configured": self.configured,
            "vapid_public_key": (
                self.settings.push_vapid_public_key.strip() if self.configured else None
            ),
            "active_subscription_count": len(subscriptions),
            "categories": sorted({
                category
                for subscription in subscriptions
                for category in subscription["categories"]
            }),
        }

    def subscribe(
        self,
        *,
        user_email: str,
        endpoint: str,
        p256dh: str,
        auth_key: str,
        categories: list[str],
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Push notifications are not configured")
        normalized_categories = validate_push_categories(categories)
        subscription = self.database.save_push_subscription(
            user_email=user_email,
            endpoint=validate_push_endpoint(endpoint),
            p256dh=p256dh.strip(),
            auth_key=auth_key.strip(),
            categories=normalized_categories,
            at=datetime.now(timezone.utc),
        )
        return {"active": True, "categories": subscription["categories"]}

    def unsubscribe(self, *, user_email: str, endpoint: str) -> dict[str, Any]:
        self.database.revoke_push_subscription(
            user_email=user_email,
            endpoint=validate_push_endpoint(endpoint),
            at=datetime.now(timezone.utc),
        )
        return {"active": False, "categories": []}

    def notify(
        self,
        *,
        category: str,
        title: str,
        body: str,
        deep_link: str,
        event_key: str | None = None,
        user_email: str | None = None,
        include_all_user_subscriptions: bool = False,
    ) -> dict[str, Any]:
        result = {
            "configured": self.configured,
            "attempted": 0,
            "sent": 0,
            "failed": 0,
            "expired": 0,
        }
        try:
            if not self.configured:
                logger.info("Push notification skipped: VAPID is not configured")
                return result
            if category != TEST_CATEGORY:
                validate_push_categories([category])
            deep_link = validate_deep_link(deep_link)
            created_at = datetime.now(timezone.utc)
            if event_key and not self.database.claim_push_notification_event(
                event_key=event_key,
                category=category,
                title=title,
                body=body,
                deep_link=deep_link,
                at=created_at,
            ):
                return result
            subscriptions = self.database.list_active_push_subscriptions(
                category=None if include_all_user_subscriptions else category,
                user_email=user_email,
            )
            payload = json.dumps(
                {
                    "category": category,
                    "title": title[:120],
                    "body": body[:500],
                    "deep_link": deep_link,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for subscription in subscriptions:
                result["attempted"] += 1
                self._deliver(
                    subscription=subscription,
                    payload=payload,
                    category=category,
                    event_key=event_key,
                    result=result,
                )
        except Exception as exc:
            result["failed"] += 1
            logger.warning(
                "Push notification emission degraded without blocking its caller: %s",
                type(exc).__name__,
            )
        return result

    def send_test(self, user_email: str) -> dict[str, Any]:
        return self.notify(
            category=TEST_CATEGORY,
            title="Alertas do C3PO ativos",
            body="O teste chegou com o aplicativo fechado.",
            deep_link="/?view=health",
            user_email=user_email,
            include_all_user_subscriptions=True,
        )

    def _deliver(
        self,
        *,
        subscription: dict[str, Any],
        payload: str,
        category: str,
        event_key: str | None,
        result: dict[str, Any],
    ) -> None:
        attempted_at = datetime.now(timezone.utc)
        delivery_status = "sent"
        response_status: int | None = None
        error_class: str | None = None
        try:
            response = self.sender(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {
                        "p256dh": subscription["p256dh"],
                        "auth": subscription["auth_key"],
                    },
                },
                data=payload,
                vapid_private_key=self.settings.push_vapid_private_key.strip(),
                vapid_claims={"sub": self.settings.push_vapid_subject},
                timeout=self.settings.push_timeout_seconds,
                ttl=300,
            )
            response_status = getattr(response, "status_code", None)
            result["sent"] += 1
        except WebPushException as exc:
            response_status = getattr(getattr(exc, "response", None), "status_code", None)
            error_class = type(exc).__name__
            if response_status in {404, 410}:
                delivery_status = "expired"
                result["expired"] += 1
                self.database.revoke_push_subscription(
                    user_email=subscription["user_email"],
                    endpoint=subscription["endpoint"],
                    at=attempted_at,
                )
            else:
                delivery_status = "failed"
                result["failed"] += 1
        except Exception as exc:
            delivery_status = "failed"
            error_class = type(exc).__name__
            result["failed"] += 1
        try:
            self.database.record_push_delivery(
                event_key=event_key,
                subscription_id=str(subscription["id"]),
                category=category,
                delivery_status=delivery_status,
                response_status=response_status,
                error_class=error_class,
                attempted_at=attempted_at,
            )
        except Exception as exc:
            logger.warning(
                "Push delivery diagnostics could not be persisted: %s",
                type(exc).__name__,
            )


def push_notify(
    service: PushNotificationService,
    *,
    category: str,
    title: str,
    body: str,
    deep_link: str,
    event_key: str | None = None,
) -> dict[str, Any]:
    """Named emitter from the frozen contract; always best-effort."""
    return service.notify(
        category=category,
        title=title,
        body=body,
        deep_link=deep_link,
        event_key=event_key,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description="Best-effort C3PO push emitter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    emit = subparsers.add_parser("emit")
    emit.add_argument("--category", choices=PUSH_CATEGORIES, required=True)
    emit.add_argument("--title", required=True)
    emit.add_argument("--body", required=True)
    emit.add_argument("--deep-link", required=True)
    emit.add_argument("--event-key")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings)
    database.initialize()
    result = PushNotificationService(settings, database).notify(
        category=args.category,
        title=args.title,
        body=args.body,
        deep_link=args.deep_link,
        event_key=args.event_key,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    _main()
