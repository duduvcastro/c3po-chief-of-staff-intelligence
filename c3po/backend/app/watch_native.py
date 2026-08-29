from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import Settings
from .database import Database
from .push_notifications import validate_push_categories
from .r2d2 import R2D2Repository


SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class WatchAuthenticationError(ValueError):
    pass


class WatchNativeService:
    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def issue_device_token(self, *, user_email: str, name: str) -> dict[str, Any]:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Watch device name is required")
        token = secrets.token_urlsafe(32)
        item = self.database.create_watch_device_credential(
            user_email=user_email,
            name=normalized_name,
            token_sha256=self._digest(token),
            at=datetime.now(timezone.utc),
        )
        return {"id": item["id"], "name": item["name"], "watch_device_token": token}

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or len(token) < 32:
            raise WatchAuthenticationError("Valid watch device bearer token required")
        item = self.database.authenticate_watch_device(
            self._digest(token), at=datetime.now(timezone.utc)
        )
        if not item:
            raise WatchAuthenticationError("Watch device token is invalid or revoked")
        return item

    def register(
        self,
        *,
        authorization: str | None,
        device_token: str,
        categories: list[str],
    ) -> dict[str, Any]:
        credential = self.authenticate(authorization)
        normalized_token = device_token.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64,200}", normalized_token):
            raise ValueError("Invalid APNs device token")
        normalized_categories = validate_push_categories(categories)
        item = self.database.save_watch_subscription(
            credential_id=credential["id"],
            user_email=credential["user_email"],
            device_token=normalized_token,
            categories=normalized_categories,
            at=datetime.now(timezone.utc),
        )
        return {"active": True, "categories": item["categories"]}

    def unregister(self, *, authorization: str | None) -> dict[str, Any]:
        credential = self.authenticate(authorization)
        self.database.revoke_watch_subscription(
            credential["id"], at=datetime.now(timezone.utc)
        )
        return {"active": False, "categories": []}

    def revoke(self, *, user_email: str, credential_id: str) -> bool:
        owned = {
            item["id"] for item in self.database.list_watch_devices(user_email=user_email)
        }
        if credential_id not in owned:
            return False
        return self.database.revoke_watch_device(
            credential_id, at=datetime.now(timezone.utc)
        )

    def list_devices(self, *, user_email: str) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in item.items() if key != "token_sha256"}
            for item in self.database.list_watch_devices(user_email=user_email)
        ]

    def complication(self, *, authorization: str | None) -> dict[str, Any]:
        self.authenticate(authorization)
        now = datetime.now(SAO_PAULO)
        repository = R2D2Repository(self.database)
        experiment = repository.experiment(self.settings.r2d2_experiment_code)
        if not experiment:
            return {
                "session_date": now.date(),
                "wins": 0,
                "decided": 0,
                "win_rate_percent": 0.0,
                "display": "0W/0 · 0,0%",
                "generated_at": datetime.now(timezone.utc),
            }
        summary = repository.episode_summary(str(experiment["id"]), now.date())
        wins = int(summary.get("positive_episodes") or 0)
        decided = int(summary.get("decided_episodes") or 0)
        percent = float(summary.get("win_rate_percent") or 0.0)
        return {
            "session_date": now.date(),
            "wins": wins,
            "decided": decided,
            "win_rate_percent": percent,
            "display": f"{wins}W/{decided} · {percent:.1f}%".replace(".", ","),
            "generated_at": datetime.now(timezone.utc),
        }
