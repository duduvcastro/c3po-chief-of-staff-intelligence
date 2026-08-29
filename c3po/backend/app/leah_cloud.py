from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .config import Settings
from .database import Database


class LeahAuthenticationError(Exception):
    pass


class LeahCloudService:
    PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def _pairing_hash(self, code: str) -> str:
        return hmac.new(
            self.settings.auth_secret.encode("utf-8"),
            code.strip().upper().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_pairing(self, owner_email: str) -> dict[str, Any]:
        now = self.now()
        code = "".join(secrets.choice(self.PAIRING_ALPHABET) for _ in range(8))
        payload = {
            "id": str(uuid4()),
            "owner_email": owner_email.strip().lower(),
            "code_hash": self._pairing_hash(code),
            "expires_at": now + timedelta(minutes=10),
            "created_at": now,
        }
        self.database.create_leah_pairing(payload)
        return {"code": code, "expires_at": payload["expires_at"]}

    def pair_device(self, code: str, name: str, platform: str) -> dict[str, Any]:
        now = self.now()
        pairing = self.database.consume_leah_pairing(self._pairing_hash(code), now)
        if not pairing:
            raise LeahAuthenticationError("Código de pareamento inválido ou expirado.")
        token = secrets.token_urlsafe(48)
        device = self.database.create_leah_device(
            {
                "id": str(uuid4()),
                "owner_email": pairing["owner_email"],
                "name": name.strip() or "Mac",
                "platform": platform.strip() or "macOS",
                "token_hash": self._token_hash(token),
                "created_at": now,
            }
        )
        return {"device": device, "token": token}

    def authenticate_device(self, authorization: str | None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise LeahAuthenticationError("Credencial do agente ausente.")
        token = authorization.removeprefix("Bearer ").strip()
        device = self.database.get_leah_device_by_token(self._token_hash(token))
        if not device or device.get("revoked_at"):
            raise LeahAuthenticationError("Dispositivo não autorizado.")
        return device

    def sync(self, device: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        now = self.now()
        self.database.touch_leah_device(
            device["id"],
            calendar_authorized=bool(payload.get("calendar_authorized")),
            reminders_authorized=bool(payload.get("reminders_authorized")),
            at=now,
        )
        for item in payload.get("items", []):
            self.database.upsert_leah_item(
                {
                    **item,
                    "owner_email": device["owner_email"],
                    "source": "icloud",
                    "source_device_id": device["id"],
                    "updated_at": now,
                }
            )
        calendar_snapshot = payload.get("calendar_snapshot")
        snapshot_start = payload.get("calendar_snapshot_start")
        snapshot_end = payload.get("calendar_snapshot_end")
        if (
            calendar_snapshot is not None
            and snapshot_start is not None
            and snapshot_end is not None
            and payload.get("calendar_authorized")
        ):
            self.database.reconcile_leah_event_snapshot(
                device["owner_email"],
                device["id"],
                calendar_snapshot,
                snapshot_start,
                snapshot_end,
                now,
            )
        since = payload.get("cursor")
        changes = self.database.list_leah_changes(device["owner_email"], since=since)
        replay_deleted_since = payload.get("replay_deleted_since")
        if replay_deleted_since is not None:
            known_ids = {str(item["id"]) for item in changes}
            changes += [
                item for item in self.database.list_leah_deleted_changes(
                    device["owner_email"], replay_deleted_since
                )
                if str(item["id"]) not in known_ids
            ]
            changes.sort(key=lambda item: item["updated_at"])
        return {"cursor": now, "items": changes}
