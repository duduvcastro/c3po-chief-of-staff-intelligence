import json
import logging
import re
import threading
from datetime import date, datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .config import Settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.database_url = settings.database_url
        self.migrations_dir = settings.migrations_dir
        self.fallback_path = Path(__file__).resolve().parents[2] / "data" / "feedback.jsonl"
        self._login_codes: dict[str, dict[str, Any]] = {}
        self._auth_lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._audit_events: list[dict[str, Any]] = []
        self._alert_reads: dict[tuple[str, str], datetime] = {}
        self._navigation_feed_views: dict[tuple[str, str], datetime] = {}
        self._access_users: dict[str, dict[str, Any]] = {}
        self._totp_credentials: dict[str, dict[str, Any]] = {}
        self._data_sources: dict[str, dict[str, Any]] = {}
        self._ingestion_runs: dict[str, dict[str, Any]] = {}
        self._observations: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._methodologies: dict[tuple[str, int], dict[str, Any]] = {}
        self._analysis_snapshots: list[dict[str, Any]] = []
        self._valuation_changes: list[dict[str, Any]] = []
        self._server_usage_samples: list[dict[str, Any]] = []
        self._realtime_portfolio: dict[str, dict[str, Any]] = {}
        self._ir_companies: dict[tuple[str, str], dict[str, Any]] = {}
        self._ir_security_map: dict[tuple[str, str], str] = {}
        self._ir_events: dict[tuple[str, str], dict[str, Any]] = {}
        self._ir_valuation_queue: dict[tuple[str, str], dict[str, Any]] = {}
        self._leah_pairings: dict[str, dict[str, Any]] = {}
        self._leah_devices: dict[str, dict[str, Any]] = {}
        self._leah_items: dict[str, dict[str, Any]] = {}

    @contextmanager
    def connection(self) -> Iterator[Any]:
        if not self.database_url:
            yield None
            return

        import psycopg

        with psycopg.connect(self.database_url) as connection:
            yield connection

    def initialize(self) -> None:
        if not self.database_url:
            return

        with self.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext('c3po_schema_migrations'))")
            migrations = (
                path for path in self.migrations_dir.glob("*.sql")
                if path.name[:1].isdigit()
            )
            for migration in sorted(migrations):
                connection.execute(migration.read_text(encoding="utf-8"))
            connection.commit()
        self.backfill_valuation_change_baseline()

    def save_feedback(self, payload: dict[str, Any]) -> str:
        if not self.database_url:
            self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with self.fallback_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return payload["id"]

        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO user_feedback
                    (id, subject_type, subject_id, rating, comment, context, created_at)
                VALUES (%(id)s, %(subject_type)s, %(subject_id)s, %(rating)s,
                        %(comment)s, %(context)s::jsonb, %(created_at)s)
                """,
                {**payload, "context": json.dumps(payload.get("context", {}))},
            )
            connection.commit()
        return payload["id"]

    def create_leah_pairing(self, payload: dict[str, Any]) -> None:
        if not self.database_url:
            self._leah_pairings[payload["code_hash"]] = payload.copy()
            return
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO leah_pairing_codes
                    (id, owner_email, code_hash, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    payload["id"], payload["owner_email"], payload["code_hash"],
                    payload["expires_at"], payload["created_at"],
                ),
            )
            connection.commit()

    def consume_leah_pairing(self, code_hash: str, at: datetime) -> dict[str, Any] | None:
        if not self.database_url:
            item = self._leah_pairings.get(code_hash)
            if not item or item.get("used_at") or item["expires_at"] <= at:
                return None
            item["used_at"] = at
            return item.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                UPDATE leah_pairing_codes
                SET used_at = %s
                WHERE code_hash = %s AND used_at IS NULL AND expires_at > %s
                RETURNING id, owner_email, expires_at, used_at, created_at
                """,
                (at, code_hash, at),
            ).fetchone()
            connection.commit()
        if not row:
            return None
        return dict(zip(("id", "owner_email", "expires_at", "used_at", "created_at"), row))

    @staticmethod
    def _leah_device_from_row(row: Any) -> dict[str, Any]:
        return dict(zip(
            (
                "id", "owner_email", "name", "platform", "calendar_authorized",
                "reminders_authorized", "last_seen_at", "revoked_at", "created_at", "updated_at",
            ),
            row,
        ))

    def create_leah_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            **payload,
            "calendar_authorized": False,
            "reminders_authorized": False,
            "last_seen_at": None,
            "revoked_at": None,
            "updated_at": payload["created_at"],
        }
        if not self.database_url:
            self._leah_devices[payload["id"]] = normalized.copy()
            return normalized.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO leah_devices (id, owner_email, name, platform, token_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, owner_email, name, platform, calendar_authorized,
                          reminders_authorized, last_seen_at, revoked_at, created_at, updated_at
                """,
                (
                    payload["id"], payload["owner_email"], payload["name"], payload["platform"],
                    payload["token_hash"], payload["created_at"],
                ),
            ).fetchone()
            connection.commit()
        return self._leah_device_from_row(row)

    def get_leah_device_by_token(self, token_hash: str) -> dict[str, Any] | None:
        if not self.database_url:
            for device in self._leah_devices.values():
                if device.get("token_hash") == token_hash:
                    return device.copy()
            return None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id, owner_email, name, platform, calendar_authorized,
                       reminders_authorized, last_seen_at, revoked_at, created_at, updated_at
                FROM leah_devices WHERE token_hash = %s
                """,
                (token_hash,),
            ).fetchone()
        return self._leah_device_from_row(row) if row else None

    def list_leah_devices(self, owner_email: str) -> list[dict[str, Any]]:
        if not self.database_url:
            return [
                item.copy() for item in self._leah_devices.values()
                if item["owner_email"] == owner_email and not item.get("revoked_at")
            ]
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, owner_email, name, platform, calendar_authorized,
                       reminders_authorized, last_seen_at, revoked_at, created_at, updated_at
                FROM leah_devices
                WHERE owner_email = %s AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                (owner_email,),
            ).fetchall()
        return [self._leah_device_from_row(row) for row in rows]

    def touch_leah_device(
        self,
        device_id: str,
        *,
        calendar_authorized: bool,
        reminders_authorized: bool,
        at: datetime,
    ) -> None:
        if not self.database_url:
            item = self._leah_devices.get(str(device_id))
            if item:
                item.update({
                    "calendar_authorized": calendar_authorized,
                    "reminders_authorized": reminders_authorized,
                    "last_seen_at": at,
                    "updated_at": at,
                })
            return
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE leah_devices
                SET calendar_authorized = %s, reminders_authorized = %s,
                    last_seen_at = %s, updated_at = %s
                WHERE id = %s AND revoked_at IS NULL
                """,
                (calendar_authorized, reminders_authorized, at, at, device_id),
            )
            connection.commit()

    def revoke_leah_device(self, owner_email: str, device_id: str, at: datetime) -> bool:
        if not self.database_url:
            item = self._leah_devices.get(str(device_id))
            if not item or item["owner_email"] != owner_email:
                return False
            item["revoked_at"] = at
            item["updated_at"] = at
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE leah_devices SET revoked_at = %s, updated_at = %s
                WHERE id = %s AND owner_email = %s AND revoked_at IS NULL
                """,
                (at, at, device_id, owner_email),
            )
            connection.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _leah_item_from_row(row: Any) -> dict[str, Any]:
        return dict(zip(
            (
                "id", "kind", "external_id", "container_id", "title", "notes", "starts_at",
                "ends_at", "due_at", "is_all_day", "is_completed", "source",
                "source_device_id", "source_modified_at", "deleted_at", "version", "updated_at",
            ),
            row,
        ))

    def upsert_leah_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item_id = str(payload.get("id") or uuid4())
        now = payload.get("updated_at") or datetime.now().astimezone()
        normalized = {
            "id": item_id,
            "kind": payload["kind"],
            "external_id": payload.get("external_id"),
            "container_id": payload.get("container_id"),
            "title": payload.get("title", "").strip(),
            "notes": payload.get("notes", ""),
            "starts_at": payload.get("starts_at"),
            "ends_at": payload.get("ends_at"),
            "due_at": payload.get("due_at"),
            "is_all_day": bool(payload.get("is_all_day")),
            "is_completed": bool(payload.get("is_completed")),
            "source": payload.get("source", "c3po"),
            "source_device_id": payload.get("source_device_id"),
            "source_modified_at": payload.get("source_modified_at"),
            "deleted_at": payload.get("deleted_at"),
            "version": 1,
            "updated_at": now,
            "owner_email": payload["owner_email"],
        }
        if not self.database_url:
            existing_id = next((
                key for key, item in self._leah_items.items()
                if normalized["external_id"] and item["owner_email"] == normalized["owner_email"]
                and item["kind"] == normalized["kind"] and item.get("external_id") == normalized["external_id"]
                and (normalized["kind"] != "event" or item.get("starts_at") == normalized["starts_at"])
            ), None)
            key = existing_id or item_id
            existing = self._leah_items.get(key, {})
            normalized["id"] = key
            normalized["version"] = int(existing.get("version", 0)) + 1
            self._leah_items[key] = normalized.copy()
            return {key: value for key, value in normalized.items() if key != "owner_email"}
        with self.connection() as connection:
            if payload.get("id"):
                updated = connection.execute(
                    """
                    UPDATE leah_items SET
                        external_id = COALESCE(%(external_id)s, external_id),
                        container_id = %(container_id)s, title = %(title)s, notes = %(notes)s,
                        starts_at = %(starts_at)s, ends_at = %(ends_at)s, due_at = %(due_at)s,
                        is_all_day = %(is_all_day)s, is_completed = %(is_completed)s,
                        source = %(source)s, source_device_id = %(source_device_id)s,
                        source_modified_at = %(source_modified_at)s, deleted_at = %(deleted_at)s,
                        version = version + 1, updated_at = %(updated_at)s
                    WHERE id = %(id)s AND owner_email = %(owner_email)s
                    RETURNING id, kind, external_id, container_id, title, notes, starts_at,
                              ends_at, due_at, is_all_day, is_completed, source, source_device_id,
                              source_modified_at, deleted_at, version, updated_at
                    """,
                    normalized,
                ).fetchone()
                if updated:
                    connection.commit()
                    return self._leah_item_from_row(updated)
            if normalized["kind"] == "event":
                conflict_target = """
                ON CONFLICT (owner_email, external_id, starts_at)
                    WHERE external_id IS NOT NULL AND kind = 'event'
                """
            else:
                conflict_target = """
                ON CONFLICT (owner_email, external_id)
                    WHERE external_id IS NOT NULL AND kind = 'task'
                """
            row = connection.execute(
                f"""
                INSERT INTO leah_items
                    (id, owner_email, kind, external_id, container_id, title, notes, starts_at,
                     ends_at, due_at, is_all_day, is_completed, source, source_device_id,
                     source_modified_at, deleted_at, updated_at)
                VALUES
                    (%(id)s, %(owner_email)s, %(kind)s, %(external_id)s, %(container_id)s,
                     %(title)s, %(notes)s, %(starts_at)s, %(ends_at)s, %(due_at)s,
                     %(is_all_day)s, %(is_completed)s, %(source)s, %(source_device_id)s,
                     %(source_modified_at)s, %(deleted_at)s, %(updated_at)s)
                {conflict_target}
                DO UPDATE SET
                    container_id = EXCLUDED.container_id, title = EXCLUDED.title,
                    notes = EXCLUDED.notes, starts_at = EXCLUDED.starts_at,
                    ends_at = EXCLUDED.ends_at, due_at = EXCLUDED.due_at,
                    is_all_day = EXCLUDED.is_all_day, is_completed = EXCLUDED.is_completed,
                    source = EXCLUDED.source, source_device_id = EXCLUDED.source_device_id,
                    source_modified_at = EXCLUDED.source_modified_at,
                    deleted_at = EXCLUDED.deleted_at, version = leah_items.version + 1,
                    updated_at = EXCLUDED.updated_at
                RETURNING id, kind, external_id, container_id, title, notes, starts_at,
                          ends_at, due_at, is_all_day, is_completed, source, source_device_id,
                          source_modified_at, deleted_at, version, updated_at
                """,
                normalized,
            ).fetchone()
            connection.commit()
        return self._leah_item_from_row(row)

    def list_leah_changes(self, owner_email: str, since: datetime | None = None) -> list[dict[str, Any]]:
        if not self.database_url:
            items = [item for item in self._leah_items.values() if item["owner_email"] == owner_email]
            if since:
                items = [item for item in items if item["updated_at"] > since]
            return [
                {key: value for key, value in item.items() if key != "owner_email"}
                for item in sorted(items, key=lambda item: item["updated_at"])
            ]
        query = """
            SELECT id, kind, external_id, container_id, title, notes, starts_at,
                   ends_at, due_at, is_all_day, is_completed, source, source_device_id,
                   source_modified_at, deleted_at, version, updated_at
            FROM leah_items WHERE owner_email = %s
        """
        params: list[Any] = [owner_email]
        if since:
            query += " AND updated_at > %s"
            params.append(since)
        query += " ORDER BY updated_at"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._leah_item_from_row(row) for row in rows]

    def get_leah_item(self, owner_email: str, item_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_leah_changes(owner_email) if str(item["id"]) == item_id), None)

    def reconcile_leah_event_snapshot(
        self,
        owner_email: str,
        source_device_id: str,
        occurrences: list[dict[str, Any]],
        window_start: datetime,
        window_end: datetime,
        at: datetime,
    ) -> int:
        visible = {(item["external_id"], item["starts_at"]) for item in occurrences}
        if not self.database_url:
            reconciled = 0
            for item in self._leah_items.values():
                identity = (item.get("external_id"), item.get("starts_at"))
                if (
                    item["owner_email"] == owner_email
                    and item["kind"] == "event"
                    and item.get("source") == "icloud"
                    and item.get("source_device_id") == source_device_id
                    and item.get("deleted_at") is None
                    and item.get("starts_at") is not None
                    and window_start <= item["starts_at"] < window_end
                    and identity not in visible
                ):
                    item.update({"deleted_at": at, "updated_at": at, "version": int(item["version"]) + 1})
                    reconciled += 1
            return reconciled
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, external_id, starts_at
                FROM leah_items
                WHERE owner_email = %s AND kind = 'event' AND source = 'icloud'
                  AND source_device_id = %s AND deleted_at IS NULL
                  AND starts_at >= %s AND starts_at < %s
                """,
                (owner_email, source_device_id, window_start, window_end),
            ).fetchall()
            stale_ids = [row[0] for row in rows if (row[1], row[2]) not in visible]
            if stale_ids:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        UPDATE leah_items
                        SET deleted_at = %s, updated_at = %s, version = version + 1
                        WHERE id = %s
                        """,
                        [(at, at, item_id) for item_id in stale_ids],
                    )
                connection.commit()
        return len(stale_ids)

    def delete_leah_item(self, owner_email: str, item_id: str, at: datetime) -> bool:
        if not self.database_url:
            item = self._leah_items.get(item_id)
            if not item or item["owner_email"] != owner_email:
                return False
            item.update({"deleted_at": at, "updated_at": at, "version": int(item["version"]) + 1, "source": "c3po"})
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE leah_items
                SET deleted_at = %s, updated_at = %s, version = version + 1, source = 'c3po'
                WHERE id = %s AND owner_email = %s
                """,
                (at, at, item_id, owner_email),
            )
            connection.commit()
        return cursor.rowcount > 0

    def ensure_access_owner(
        self,
        email: str,
        permissions: list[str],
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_email = email.strip().lower()
        now = datetime.now().astimezone()
        payload = {
            "email": normalized_email,
            "display_name": "Eduardo Castro",
            "role": "owner",
            "is_active": True,
            "permissions": list(permissions),
            "capabilities": list(capabilities or ("read", "onepager_generate", "delete")),
            "created_by": "system",
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
        }
        if not self.database_url:
            existing = self._access_users.get(normalized_email, {})
            payload["created_at"] = existing.get("created_at", now)
            payload["last_login_at"] = existing.get("last_login_at")
            self._access_users[normalized_email] = payload
            return payload.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO access_users
                    (email, display_name, role, is_active, permissions, capabilities, created_by)
                VALUES (%s, %s, 'owner', TRUE, %s::jsonb, %s::jsonb, 'system')
                ON CONFLICT (email) DO UPDATE
                SET role = 'owner', is_active = TRUE,
                    permissions = EXCLUDED.permissions,
                    capabilities = EXCLUDED.capabilities, updated_at = now()
                RETURNING email, display_name, role, is_active, permissions, capabilities,
                          created_by, created_at, updated_at, last_login_at
                """,
                (
                    normalized_email,
                    payload["display_name"],
                    json.dumps(permissions),
                    json.dumps(payload["capabilities"]),
                ),
            ).fetchone()
            connection.commit()
        return self._access_user_from_row(row)

    @staticmethod
    def _access_user_from_row(row: Any) -> dict[str, Any]:
        keys = (
            "email", "display_name", "role", "is_active", "permissions", "capabilities",
            "created_by", "created_at", "updated_at", "last_login_at",
        )
        item = dict(zip(keys, row))
        item["permissions"] = list(item.get("permissions") or [])
        item["capabilities"] = list(item.get("capabilities") or ["read"])
        return item

    def get_access_user(self, email: str) -> dict[str, Any] | None:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._access_users.get(normalized_email)
            return item.copy() if item else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT email, display_name, role, is_active, permissions, capabilities,
                       created_by, created_at, updated_at, last_login_at
                FROM access_users WHERE email = %s
                """,
                (normalized_email,),
            ).fetchone()
        return self._access_user_from_row(row) if row else None

    def list_access_users(self) -> list[dict[str, Any]]:
        if not self.database_url:
            return sorted(
                (item.copy() for item in self._access_users.values()),
                key=lambda item: (item["role"] != "owner", item["email"]),
            )
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT email, display_name, role, is_active, permissions, capabilities,
                       created_by, created_at, updated_at, last_login_at
                FROM access_users
                ORDER BY CASE WHEN role = 'owner' THEN 0 ELSE 1 END, email
                """
            ).fetchall()
        return [self._access_user_from_row(row) for row in rows]

    def upsert_access_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_email = payload["email"].strip().lower()
        now = datetime.now().astimezone()
        normalized = {
            **payload,
            "email": normalized_email,
            "role": payload.get("role", "member"),
            "is_active": bool(payload.get("is_active", True)),
            "permissions": list(payload.get("permissions", [])),
            "capabilities": list(payload.get("capabilities", ["read"])),
            "created_by": payload.get("created_by", ""),
            "updated_at": now,
        }
        if not self.database_url:
            existing = self._access_users.get(normalized_email, {})
            normalized["created_at"] = existing.get("created_at", now)
            normalized["last_login_at"] = existing.get("last_login_at")
            self._access_users[normalized_email] = normalized
            return normalized.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO access_users
                    (email, display_name, role, is_active, permissions, capabilities, created_by)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (email) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    is_active = EXCLUDED.is_active,
                    permissions = EXCLUDED.permissions,
                    capabilities = EXCLUDED.capabilities,
                    updated_at = now()
                RETURNING email, display_name, role, is_active, permissions, capabilities,
                          created_by, created_at, updated_at, last_login_at
                """,
                (
                    normalized_email,
                    normalized.get("display_name", ""),
                    normalized["role"],
                    normalized["is_active"],
                    json.dumps(normalized["permissions"]),
                    json.dumps(normalized["capabilities"]),
                    normalized["created_by"],
                ),
            ).fetchone()
            connection.commit()
        return self._access_user_from_row(row)

    def delete_access_user(self, email: str) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            return self._access_users.pop(normalized_email, None) is not None
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM access_users WHERE email = %s", (normalized_email,))
            connection.commit()
        return cursor.rowcount > 0

    def touch_access_user_login(self, email: str, at: datetime) -> None:
        normalized_email = email.strip().lower()
        if not self.database_url:
            if normalized_email in self._access_users:
                self._access_users[normalized_email]["last_login_at"] = at
            return
        with self.connection() as connection:
            connection.execute(
                "UPDATE access_users SET last_login_at = %s WHERE email = %s",
                (at, normalized_email),
            )
            connection.commit()

    def revoke_sessions_for_email(self, email: str, at: datetime) -> None:
        normalized_email = email.strip().lower()
        if not self.database_url:
            for session in self._sessions.values():
                if session["email"] == normalized_email:
                    session["revoked_at"] = at
            return
        with self.connection() as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = %s WHERE email = %s AND revoked_at IS NULL",
                (at, normalized_email),
            )
            connection.commit()

    def record_audit_event(
        self,
        actor: str,
        action: str,
        subject_type: str,
        subject_id: str,
        detail: dict[str, Any],
    ) -> None:
        if not self.database_url:
            self._audit_events.append(
                {
                    "id": str(uuid4()),
                    "actor": actor,
                    "action": action,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "detail": detail.copy(),
                    "occurred_at": datetime.now().astimezone(),
                }
            )
            return
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (id, actor, action, subject_type, subject_id, detail)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (str(uuid4()), actor, action, subject_type, subject_id, json.dumps(detail)),
            )
            connection.commit()

    def list_audit_events(self, *, action: str, limit: int = 50) -> list[dict[str, Any]]:
        if not self.database_url:
            rows = [item.copy() for item in self._audit_events if item["action"] == action]
            return sorted(rows, key=lambda item: item["occurred_at"], reverse=True)[:limit]
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id::text, actor, action, subject_type, subject_id, detail, occurred_at
                FROM audit_events
                WHERE action = %s
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                (action, limit),
            ).fetchall()
        keys = ("id", "actor", "action", "subject_type", "subject_id", "detail", "occurred_at")
        return [dict(zip(keys, row)) for row in rows]

    def alert_read_ids(self, email: str, alert_ids: list[str]) -> set[str]:
        normalized_email = email.strip().lower()
        unique_ids = list(dict.fromkeys(alert_id for alert_id in alert_ids if alert_id))
        if not unique_ids:
            return set()
        if not self.database_url:
            return {
                alert_id for alert_id in unique_ids
                if (normalized_email, alert_id) in self._alert_reads
            }
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT alert_id
                FROM alert_reads
                WHERE user_email = %s AND alert_id = ANY(%s)
                """,
                (normalized_email, unique_ids),
            ).fetchall()
        return {row[0] for row in rows}

    def mark_alerts_read(self, email: str, alert_ids: list[str], read_at: datetime) -> int:
        normalized_email = email.strip().lower()
        unique_ids = list(dict.fromkeys(alert_id for alert_id in alert_ids if alert_id))
        if not unique_ids:
            return 0
        if not self.database_url:
            for alert_id in unique_ids:
                self._alert_reads[(normalized_email, alert_id)] = read_at
            return len(unique_ids)
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO alert_reads (user_email, alert_id, read_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_email, alert_id)
                    DO UPDATE SET read_at = EXCLUDED.read_at
                    """,
                    [(normalized_email, alert_id, read_at) for alert_id in unique_ids],
                )
            connection.commit()
        return len(unique_ids)

    def navigation_feed_seen_at(self, email: str, feed_keys: list[str]) -> dict[str, datetime]:
        normalized_email = email.strip().lower()
        unique_keys = list(dict.fromkeys(key for key in feed_keys if key in {"relations", "intelligence"}))
        if not unique_keys:
            return {}
        if not self.database_url:
            return {
                key: self._navigation_feed_views[(normalized_email, key)]
                for key in unique_keys
                if (normalized_email, key) in self._navigation_feed_views
            }
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT feed_key, last_seen_at
                FROM navigation_feed_views
                WHERE user_email = %s AND feed_key = ANY(%s)
                """,
                (normalized_email, unique_keys),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def mark_navigation_feed_seen(
        self,
        email: str,
        feed_key: str,
        seen_at: datetime,
    ) -> datetime:
        if feed_key not in {"relations", "intelligence"}:
            raise ValueError(f"Unsupported navigation feed: {feed_key}")
        normalized_email = email.strip().lower()
        if not self.database_url:
            self._navigation_feed_views[(normalized_email, feed_key)] = seen_at
            return seen_at
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO navigation_feed_views (user_email, feed_key, last_seen_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_email, feed_key)
                DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at
                RETURNING last_seen_at
                """,
                (normalized_email, feed_key, seen_at),
            ).fetchone()
            connection.commit()
        return row[0]

    def navigation_feed_activity(
        self,
        feed_key: str,
        *,
        after: datetime | None = None,
    ) -> tuple[datetime | None, int]:
        if feed_key not in {"relations", "intelligence"}:
            raise ValueError(f"Unsupported navigation feed: {feed_key}")
        if not self.database_url:
            if feed_key == "relations":
                monitored_ids = set(self._ir_security_map.values())
                rows = [
                    item for item in self._ir_events.values()
                    if item.get("company_id") in monitored_ids
                ]
                timestamps = [item.get("collected_at") for item in rows]
            else:
                timestamps = [item.get("changed_at") for item in self._valuation_changes]
            normalized = [
                datetime.fromisoformat(value) if isinstance(value, str) else value
                for value in timestamps if value
            ]
            latest = max(normalized) if normalized else None
            unseen = sum(1 for value in normalized if after is None or value > after)
            return latest, unseen

        if feed_key == "relations":
            source_table = "ir_events event"
            timestamp_column = "event.collected_at"
            where = "EXISTS (SELECT 1 FROM ir_security_map security WHERE security.company_id = event.company_id)"
        else:
            source_table = "valuation_change_records"
            timestamp_column = "changed_at"
            where = "TRUE"
        count_clause = "count(*)" if after is None else f"count(*) FILTER (WHERE {timestamp_column} > %s)"
        params: tuple[Any, ...] = () if after is None else (after,)
        with self.connection() as connection:
            row = connection.execute(
                f"""
                SELECT max({timestamp_column}), {count_clause}
                FROM {source_table}
                WHERE {where}
                """,
                params,
            ).fetchone()
        return row[0], int(row[1] or 0)

    def recent_login_code_counts(self, email: str, requested_ip: str, since: datetime) -> tuple[int, int]:
        if not self.database_url:
            with self._auth_lock:
                email_count = sum(
                    1 for item in self._login_codes.values()
                    if item["email"] == email and item["created_at"] >= since
                )
                ip_count = sum(
                    1 for item in self._login_codes.values()
                    if item["requested_ip"] == requested_ip and item["created_at"] >= since
                )
                return email_count, ip_count
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT count(*) FILTER (WHERE email = %s),
                       count(*) FILTER (WHERE requested_ip = %s)
                FROM auth_login_codes WHERE created_at >= %s
                """,
                (email, requested_ip, since),
            ).fetchone()
        return int(row[0]), int(row[1])

    def create_login_code(self, payload: dict[str, Any]) -> None:
        if not self.database_url:
            with self._auth_lock:
                for item in self._login_codes.values():
                    if item["email"] == payload["email"] and not item.get("used_at"):
                        item["used_at"] = payload["created_at"]
                self._login_codes[payload["id"]] = payload.copy()
            return
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE auth_login_codes SET used_at = %s
                WHERE email = %s AND used_at IS NULL
                """,
                (payload["created_at"], payload["email"]),
            )
            connection.execute(
                """
                INSERT INTO auth_login_codes
                    (id, email, code_hash, expires_at, attempts, max_attempts,
                     requested_ip, created_at, verification_method)
                VALUES (%(id)s, %(email)s, %(code_hash)s, %(expires_at)s,
                        %(attempts)s, %(max_attempts)s, %(requested_ip)s, %(created_at)s,
                        %(verification_method)s)
                """,
                payload,
            )
            connection.commit()

    def claim_login_attempt(
        self,
        challenge_id: str,
        *,
        code_valid: bool,
        requested_ip: str,
        at: datetime,
        since: datetime,
        ip_failure_limit: int,
    ) -> tuple[str, dict[str, Any] | None]:
        """Atomically consume one challenge attempt and enforce the IP failure budget."""
        if not self.database_url:
            with self._auth_lock:
                failures = sum(
                    1 for event in self._audit_events
                    if event["action"] == "auth.otp_failed"
                    and event["detail"].get("requested_ip") == requested_ip
                    and event["occurred_at"] >= since
                )
                if failures >= ip_failure_limit:
                    return "rate_limited", None
                item = self._login_codes.get(challenge_id)
                active = bool(
                    item and not item.get("used_at") and item["expires_at"] > at
                    and item["attempts"] < item["max_attempts"]
                )
                if not active:
                    self.record_audit_event(
                        item["email"] if item else "anonymous",
                        "auth.otp_failed", "auth_challenge", challenge_id,
                        {"requested_ip": requested_ip, "reason": "inactive_challenge"},
                    )
                    return "invalid", item.copy() if item else None
                item["attempts"] += 1
                if code_valid:
                    item["used_at"] = at
                    return "accepted", item.copy()
                self.record_audit_event(
                    item["email"], "auth.otp_failed", "auth_challenge", challenge_id,
                    {"requested_ip": requested_ip, "reason": "invalid_code", "attempts": item["attempts"]},
                )
                return "invalid", item.copy()

        with self.connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"auth-verify:{requested_ip}",))
            failures = connection.execute(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'auth.otp_failed' AND occurred_at >= %s
                  AND detail->>'requested_ip' = %s
                """,
                (since, requested_ip),
            ).fetchone()[0]
            if int(failures) >= ip_failure_limit:
                connection.commit()
                return "rate_limited", None
            row = connection.execute(
                """
                SELECT id::text, email, code_hash, expires_at, attempts, max_attempts,
                       used_at, requested_ip, created_at, verification_method
                FROM auth_login_codes WHERE id = %s FOR UPDATE
                """,
                (challenge_id,),
            ).fetchone()
            keys = ("id", "email", "code_hash", "expires_at", "attempts", "max_attempts", "used_at", "requested_ip", "created_at", "verification_method")
            challenge = dict(zip(keys, row)) if row else None
            active = bool(
                challenge and not challenge["used_at"] and challenge["expires_at"] > at
                and challenge["attempts"] < challenge["max_attempts"]
            )
            accepted = bool(active and code_valid)
            if active:
                row = connection.execute(
                    """
                    UPDATE auth_login_codes
                    SET attempts = attempts + 1,
                        used_at = CASE WHEN %s THEN %s ELSE used_at END
                    WHERE id = %s AND used_at IS NULL AND expires_at > %s
                      AND attempts < max_attempts
                    RETURNING id::text, email, code_hash, expires_at, attempts, max_attempts,
                              used_at, requested_ip, created_at, verification_method
                    """,
                    (accepted, at, challenge_id, at),
                ).fetchone()
                challenge = dict(zip(keys, row)) if row else challenge
                accepted = bool(row and accepted)
            if not accepted:
                actor = challenge["email"] if challenge else "anonymous"
                reason = "invalid_code" if active else "inactive_challenge"
                connection.execute(
                    """
                    INSERT INTO audit_events (id, actor, action, subject_type, subject_id, detail)
                    VALUES (%s, %s, 'auth.otp_failed', 'auth_challenge', %s, %s::jsonb)
                    """,
                    (
                        str(uuid4()), actor, challenge_id,
                        json.dumps({"requested_ip": requested_ip, "reason": reason}),
                    ),
                )
            connection.commit()
        return ("accepted" if accepted else "invalid"), challenge

    def get_login_code(self, challenge_id: str) -> dict[str, Any] | None:
        if not self.database_url:
            item = self._login_codes.get(challenge_id)
            return item.copy() if item else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id::text, email, code_hash, expires_at, attempts,
                       max_attempts, used_at, requested_ip, created_at, verification_method
                FROM auth_login_codes WHERE id = %s
                """,
                (challenge_id,),
            ).fetchone()
        if not row:
            return None
        keys = ("id", "email", "code_hash", "expires_at", "attempts", "max_attempts", "used_at", "requested_ip", "created_at", "verification_method")
        return dict(zip(keys, row))

    def upsert_totp_setup(self, email: str, encrypted_secret: str, expires_at: datetime, at: datetime) -> None:
        normalized_email = email.strip().lower()
        payload = {
            "email": normalized_email,
            "encrypted_secret": encrypted_secret,
            "confirmed_at": None,
            "setup_expires_at": expires_at,
            "last_used_step": None,
            "created_at": at,
            "updated_at": at,
            "pending_encrypted_secret": None,
            "pending_setup_expires_at": None,
        }
        if not self.database_url:
            self._totp_credentials[normalized_email] = payload
            return
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO auth_totp_credentials
                    (email, encrypted_secret, setup_expires_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE
                SET encrypted_secret = EXCLUDED.encrypted_secret,
                    confirmed_at = NULL,
                    setup_expires_at = EXCLUDED.setup_expires_at,
                    last_used_step = NULL,
                    updated_at = EXCLUDED.updated_at
                """,
                (normalized_email, encrypted_secret, expires_at, at, at),
            )
            connection.commit()

    def get_totp_credential(self, email: str) -> dict[str, Any] | None:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._totp_credentials.get(normalized_email)
            return item.copy() if item else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT email, encrypted_secret, confirmed_at, setup_expires_at,
                       last_used_step, created_at, updated_at,
                       pending_encrypted_secret, pending_setup_expires_at
                FROM auth_totp_credentials WHERE email = %s
                """,
                (normalized_email,),
            ).fetchone()
        if not row:
            return None
        return dict(zip(
            ("email", "encrypted_secret", "confirmed_at", "setup_expires_at", "last_used_step", "created_at", "updated_at", "pending_encrypted_secret", "pending_setup_expires_at"),
            row,
        ))

    def stage_totp_reconfiguration(self, email: str, encrypted_secret: str, expires_at: datetime, at: datetime) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._totp_credentials.get(normalized_email)
            if not item or not item.get("confirmed_at"):
                return False
            item.update({
                "pending_encrypted_secret": encrypted_secret,
                "pending_setup_expires_at": expires_at,
                "updated_at": at,
            })
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_totp_credentials
                SET pending_encrypted_secret = %s,
                    pending_setup_expires_at = %s,
                    updated_at = %s
                WHERE email = %s AND confirmed_at IS NOT NULL
                """,
                (encrypted_secret, expires_at, at, normalized_email),
            )
            connection.commit()
        return cursor.rowcount == 1

    def confirm_totp_reconfiguration(self, email: str, step: int, at: datetime) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._totp_credentials.get(normalized_email)
            if (
                not item
                or not item.get("confirmed_at")
                or not item.get("pending_encrypted_secret")
                or not item.get("pending_setup_expires_at")
                or item["pending_setup_expires_at"] <= at
            ):
                return False
            item.update({
                "encrypted_secret": item["pending_encrypted_secret"],
                "setup_expires_at": item["pending_setup_expires_at"],
                "confirmed_at": at,
                "last_used_step": step,
                "pending_encrypted_secret": None,
                "pending_setup_expires_at": None,
                "updated_at": at,
            })
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_totp_credentials
                SET encrypted_secret = pending_encrypted_secret,
                    setup_expires_at = pending_setup_expires_at,
                    confirmed_at = %s,
                    last_used_step = %s,
                    pending_encrypted_secret = NULL,
                    pending_setup_expires_at = NULL,
                    updated_at = %s
                WHERE email = %s
                  AND confirmed_at IS NOT NULL
                  AND pending_encrypted_secret IS NOT NULL
                  AND pending_setup_expires_at > %s
                """,
                (at, step, at, normalized_email, at),
            )
            connection.commit()
        return cursor.rowcount == 1

    def confirm_totp(self, email: str, step: int, at: datetime) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._totp_credentials.get(normalized_email)
            if not item or item["setup_expires_at"] <= at or item.get("confirmed_at"):
                return False
            item.update({"confirmed_at": at, "last_used_step": step, "updated_at": at})
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_totp_credentials
                SET confirmed_at = %s, last_used_step = %s, updated_at = %s
                WHERE email = %s AND confirmed_at IS NULL AND setup_expires_at > %s
                """,
                (at, step, at, normalized_email, at),
            )
            connection.commit()
        return cursor.rowcount == 1

    def claim_totp_step(self, email: str, step: int, at: datetime) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            item = self._totp_credentials.get(normalized_email)
            if not item or not item.get("confirmed_at") or (item.get("last_used_step") or -1) >= step:
                return False
            item.update({"last_used_step": step, "updated_at": at})
            return True
        with self.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_totp_credentials
                SET last_used_step = %s, updated_at = %s
                WHERE email = %s AND confirmed_at IS NOT NULL
                  AND (last_used_step IS NULL OR last_used_step < %s)
                """,
                (step, at, normalized_email, step),
            )
            connection.commit()
        return cursor.rowcount == 1

    def delete_totp_credential(self, email: str) -> bool:
        normalized_email = email.strip().lower()
        if not self.database_url:
            return self._totp_credentials.pop(normalized_email, None) is not None
        with self.connection() as connection:
            cursor = connection.execute("DELETE FROM auth_totp_credentials WHERE email = %s", (normalized_email,))
            connection.commit()
        return cursor.rowcount == 1

    def create_session(self, payload: dict[str, Any]) -> None:
        if not self.database_url:
            self._sessions[payload["token_hash"]] = payload.copy()
            return
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions
                    (id, email, token_hash, expires_at, created_at, last_seen_at, created_ip)
                VALUES (%(id)s, %(email)s, %(token_hash)s, %(expires_at)s,
                        %(created_at)s, %(last_seen_at)s, %(created_ip)s)
                """,
                payload,
            )
            connection.commit()

    def get_session(
        self,
        token_hash: str,
        now: datetime,
        *,
        idle_cutoff: datetime,
        touch_activity: bool = False,
    ) -> dict[str, Any] | None:
        if not self.database_url:
            item = self._sessions.get(token_hash)
            if not item or item["expires_at"] <= now or item.get("revoked_at"):
                return None
            if item["last_seen_at"] <= idle_cutoff:
                item["revoked_at"] = now
                return None
            if touch_activity:
                item["last_seen_at"] = now
            return item.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                UPDATE auth_sessions
                SET last_seen_at = CASE WHEN %s THEN %s ELSE last_seen_at END
                WHERE token_hash = %s
                  AND expires_at > %s
                  AND revoked_at IS NULL
                  AND last_seen_at > %s
                RETURNING id::text, email, expires_at, created_at, last_seen_at, created_ip
                """,
                (touch_activity, now, token_hash, now, idle_cutoff),
            ).fetchone()
            connection.commit()
        if not row:
            return None
        return dict(zip(("id", "email", "expires_at", "created_at", "last_seen_at", "created_ip"), row))

    def revoke_session(self, token_hash: str, now: datetime) -> None:
        if not self.database_url:
            item = self._sessions.get(token_hash)
            if item:
                item["revoked_at"] = now
            return
        with self.connection() as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = %s WHERE token_hash = %s",
                (now, token_hash),
            )
            connection.commit()

    def ensure_data_source(self, code: str, name: str, source_type: str) -> str:
        now = datetime.now().astimezone()
        if not self.database_url:
            existing = self._data_sources.get(code)
            if existing:
                existing.update({"name": name, "source_type": source_type, "updated_at": now})
                return existing["id"]
            source_id = str(uuid4())
            self._data_sources[code] = {
                "id": source_id,
                "code": code,
                "name": name,
                "source_type": source_type,
                "updated_at": now,
            }
            return source_id
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO data_sources (id, code, name, source_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET name = EXCLUDED.name, source_type = EXCLUDED.source_type, updated_at = now()
                RETURNING id::text
                """,
                (str(uuid4()), code, name, source_type),
            ).fetchone()
            connection.commit()
        return str(row[0])

    def begin_ingestion_run(self, code: str, name: str, source_type: str, metadata: dict[str, Any]) -> str:
        source_id = self.ensure_data_source(code, name, source_type)
        run_id = str(uuid4())
        started_at = datetime.now().astimezone()
        payload = {
            "id": run_id,
            "source_id": source_id,
            "source_code": code,
            "status": "running",
            "started_at": started_at,
            "metadata": metadata,
        }
        if not self.database_url:
            self._ingestion_runs[run_id] = payload
            return run_id
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_runs (id, source_id, status, started_at, metadata)
                VALUES (%s, %s, 'running', %s, %s::jsonb)
                """,
                (run_id, source_id, started_at, json.dumps(metadata)),
            )
            connection.commit()
        return run_id

    def finish_ingestion_run(
        self,
        run_id: str,
        status: str,
        records_read: int,
        records_written: int,
        error_summary: str | None = None,
    ) -> None:
        completed_at = datetime.now().astimezone()
        if not self.database_url:
            run = self._ingestion_runs.get(run_id)
            if run:
                run.update({
                    "status": status,
                    "completed_at": completed_at,
                    "records_read": records_read,
                    "records_written": records_written,
                    "error_summary": error_summary,
                })
            return
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE ingestion_runs
                SET status = %s, completed_at = %s, records_read = %s,
                    records_written = %s, error_summary = %s
                WHERE id = %s
                """,
                (status, completed_at, records_read, records_written, error_summary, run_id),
            )
            connection.commit()

    def save_quotes(self, source_code: str, run_id: str, quotes: list[Any]) -> None:
        if not quotes:
            return
        if not self.database_url:
            for quote in quotes:
                key = (source_code, quote.symbol, quote.as_of.isoformat())
                self._observations[key] = quote.model_dump(mode="json")
            return
        source_id = self.ensure_data_source(source_code, source_code.upper(), "market_data")
        rows = []
        for quote in quotes:
            rows.append((
                str(uuid4()),
                source_id,
                quote.symbol,
                json.dumps(quote.model_dump(mode="json")),
                quote.as_of,
                quote.collected_at,
                quote.quality_score,
                f"{source_code}:{quote.provider_symbol}",
                run_id,
            ))
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO observations
                        (id, source_id, entity_type, entity_key, metric, value, as_of,
                         collected_at, quality_score, raw_reference, ingestion_run_id)
                    VALUES (%s, %s, 'security', %s, 'quote_snapshot', %s::jsonb, %s,
                            %s, %s, %s, %s)
                    ON CONFLICT (source_id, entity_type, entity_key, metric, as_of)
                    DO UPDATE SET value = EXCLUDED.value,
                                  collected_at = EXCLUDED.collected_at,
                                  quality_score = EXCLUDED.quality_score,
                                  raw_reference = EXCLUDED.raw_reference,
                                  ingestion_run_id = EXCLUDED.ingestion_run_id
                    """,
                    rows,
                )
            connection.commit()

    def save_server_usage_samples(self, samples: list[dict[str, Any]]) -> int:
        if not samples:
            return 0
        if not self.database_url:
            keyed = {
                (item["server_id"], item["collected_at"]): item.copy()
                for item in self._server_usage_samples
            }
            for sample in samples:
                keyed[(sample["server_id"], sample["collected_at"])] = sample.copy()
            self._server_usage_samples = sorted(keyed.values(), key=lambda item: item["collected_at"])
            return len(samples)
        rows = [(
            sample["server_id"],
            sample["server_name"],
            sample["region"],
            sample["collected_at"],
            sample.get("cpu_percent"),
            sample.get("disk_total_bytes"),
            sample.get("disk_used_bytes"),
            sample.get("disk_free_bytes"),
            sample.get("source", "procfs"),
        ) for sample in samples]
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO server_usage_samples
                        (server_id, server_name, region, collected_at, cpu_percent,
                         disk_total_bytes, disk_used_bytes, disk_free_bytes, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (server_id, collected_at) DO UPDATE
                    SET server_name = EXCLUDED.server_name,
                        region = EXCLUDED.region,
                        cpu_percent = COALESCE(EXCLUDED.cpu_percent, server_usage_samples.cpu_percent),
                        disk_total_bytes = COALESCE(EXCLUDED.disk_total_bytes, server_usage_samples.disk_total_bytes),
                        disk_used_bytes = COALESCE(EXCLUDED.disk_used_bytes, server_usage_samples.disk_used_bytes),
                        disk_free_bytes = COALESCE(EXCLUDED.disk_free_bytes, server_usage_samples.disk_free_bytes),
                        source = EXCLUDED.source
                    """,
                    rows,
                )
            connection.commit()
        return len(rows)

    def list_server_usage_samples(
        self,
        since: datetime,
        server_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.database_url:
            return [
                item.copy() for item in self._server_usage_samples
                if item["collected_at"] >= since and (not server_id or item["server_id"] == server_id)
            ]
        query = """
            SELECT server_id, server_name, region, collected_at, cpu_percent,
                   disk_total_bytes, disk_used_bytes, disk_free_bytes, source
            FROM server_usage_samples
            WHERE collected_at >= %s
        """
        params: list[Any] = [since]
        if server_id:
            query += " AND server_id = %s"
            params.append(server_id)
        query += " ORDER BY server_id, collected_at"
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        keys = (
            "server_id", "server_name", "region", "collected_at", "cpu_percent",
            "disk_total_bytes", "disk_used_bytes", "disk_free_bytes", "source",
        )
        return [dict(zip(keys, row)) for row in rows]

    def purge_server_usage_samples(self, before: datetime) -> int:
        if not self.database_url:
            original = len(self._server_usage_samples)
            self._server_usage_samples = [item for item in self._server_usage_samples if item["collected_at"] >= before]
            return original - len(self._server_usage_samples)
        with self.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM server_usage_samples WHERE collected_at < %s",
                (before,),
            )
            connection.commit()
            return cursor.rowcount

    def market_data_provider_health(self) -> dict[str, dict[str, Any]]:
        if not self.database_url:
            output: dict[str, dict[str, Any]] = {}
            for run in sorted(self._ingestion_runs.values(), key=lambda item: item["started_at"]):
                code = run["source_code"]
                state = output.setdefault(code, {})
                state["last_status"] = run["status"]
                if run["status"] == "succeeded":
                    state["last_success_at"] = run.get("completed_at")
                    state["last_error"] = None
                elif run["status"] == "failed":
                    state["last_error"] = run.get("error_summary")
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (source.code)
                    source.code,
                    run.status,
                    max(run.completed_at) FILTER (WHERE run.status = 'succeeded')
                        OVER (PARTITION BY source.code) AS last_success_at,
                    CASE WHEN run.status = 'failed' THEN run.error_summary END AS last_error
                FROM data_sources source
                JOIN ingestion_runs run ON run.source_id = source.id
                WHERE source.source_type = 'market_data'
                ORDER BY source.code, run.started_at DESC
                """
            ).fetchall()
        return {
            row[0]: {
                "last_status": row[1],
                "last_success_at": row[2],
                "last_error": row[3],
            }
            for row in rows
        }

    def list_realtime_portfolio(self) -> list[dict[str, Any]]:
        if not self.database_url:
            return sorted(
                (item.copy() for item in self._realtime_portfolio.values()),
                key=lambda item: (item["market"], item["symbol"]),
            )
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT symbol, name, market, created_at, updated_at
                FROM realtime_portfolio
                ORDER BY market, symbol
                """
            ).fetchall()
        keys = ("symbol", "name", "market", "created_at", "updated_at")
        return [dict(zip(keys, row)) for row in rows]

    def add_realtime_portfolio(self, symbol: str, name: str, market: str) -> dict[str, Any]:
        now = datetime.now().astimezone()
        payload = {"symbol": symbol, "name": name, "market": market, "created_at": now, "updated_at": now}
        if not self.database_url:
            existing = self._realtime_portfolio.get(symbol)
            if existing:
                payload["created_at"] = existing["created_at"]
            self._realtime_portfolio[symbol] = payload
            return payload.copy()
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO realtime_portfolio (symbol, name, market)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE
                SET name = EXCLUDED.name, market = EXCLUDED.market, updated_at = now()
                RETURNING symbol, name, market, created_at, updated_at
                """,
                (symbol, name, market),
            ).fetchone()
            connection.commit()
        return dict(zip(("symbol", "name", "market", "created_at", "updated_at"), row))

    def delete_realtime_portfolio(self, symbol: str) -> bool:
        if not self.database_url:
            return self._realtime_portfolio.pop(symbol, None) is not None
        with self.connection() as connection:
            row = connection.execute(
                "DELETE FROM realtime_portfolio WHERE symbol = %s RETURNING symbol",
                (symbol,),
            ).fetchone()
            connection.commit()
        return row is not None

    def register_ir_securities(self, items: list[dict[str, Any]]) -> int:
        """Register the issuer/security bridge used to map regulator filings to tickers."""
        if not items:
            return 0
        if not self.database_url:
            for item in items:
                market = str(item["market"]).upper()
                name_key = str(item["name_key"])
                company_key = (market, name_key)
                regulator_id = item.get("regulator_id") or None
                regulator_company = next(
                    (
                        candidate
                        for candidate in self._ir_companies.values()
                        if regulator_id
                        and candidate["market"] == market
                        and candidate.get("regulator_id") == regulator_id
                    ),
                    None,
                )
                name_company = self._ir_companies.get(company_key)
                company = regulator_company or name_company
                if regulator_company and name_company and regulator_company["id"] != name_company["id"]:
                    duplicate_id = name_company["id"]
                    for security_key, mapped_company_id in list(self._ir_security_map.items()):
                        if mapped_company_id == duplicate_id:
                            self._ir_security_map[security_key] = regulator_company["id"]
                    for event in self._ir_events.values():
                        if event.get("company_id") == duplicate_id:
                            event["company_id"] = regulator_company["id"]
                    self._ir_companies.pop(company_key, None)
                    company = regulator_company
                if not company:
                    company = {
                        "id": str(uuid4()),
                        "market": market,
                        "company_name": item["company_name"],
                        "name_key": name_key,
                        "regulator_id": item.get("regulator_id"),
                        "tax_id": item.get("tax_id"),
                        "exchange": item.get("exchange"),
                        "ri_url": item.get("ri_url"),
                        "active": True,
                        "updated_at": datetime.now().astimezone(),
                    }
                    self._ir_companies[company_key] = company
                else:
                    old_key = (market, str(company["name_key"]))
                    for field in ("company_name", "regulator_id", "tax_id", "exchange", "ri_url"):
                        if item.get(field):
                            company[field] = item[field]
                    company["name_key"] = name_key
                    company["updated_at"] = datetime.now().astimezone()
                    if old_key != company_key:
                        self._ir_companies.pop(old_key, None)
                        self._ir_companies[company_key] = company
                symbol = str(item.get("symbol") or "").upper()
                if symbol:
                    self._ir_security_map[(market, symbol)] = company["id"]
            return len(items)

        with self.connection() as connection:
            for item in items:
                market = str(item["market"]).upper()
                name_key = str(item["name_key"])
                regulator_id = item.get("regulator_id") or None
                regulator_company = None
                if regulator_id:
                    regulator_company = connection.execute(
                        "SELECT id FROM ir_companies WHERE market = %s AND regulator_id = %s",
                        (market, regulator_id),
                    ).fetchone()
                name_company = connection.execute(
                    "SELECT id FROM ir_companies WHERE market = %s AND name_key = %s",
                    (market, name_key),
                ).fetchone()
                if regulator_company and name_company and regulator_company[0] != name_company[0]:
                    company_id = str(regulator_company[0])
                    duplicate_id = str(name_company[0])
                    connection.execute(
                        "UPDATE ir_security_map SET company_id = %s, updated_at = now() WHERE company_id = %s",
                        (company_id, duplicate_id),
                    )
                    connection.execute(
                        "UPDATE ir_events SET company_id = %s, updated_at = now() WHERE company_id = %s",
                        (company_id, duplicate_id),
                    )
                    connection.execute("DELETE FROM ir_companies WHERE id = %s", (duplicate_id,))
                    company = regulator_company
                else:
                    company = regulator_company or name_company
                if company:
                    company_id = str(company[0])
                    connection.execute(
                        """
                        UPDATE ir_companies
                        SET company_name = %s,
                            name_key = %s,
                            regulator_id = COALESCE(%s, regulator_id),
                            tax_id = COALESCE(%s, tax_id),
                            exchange = COALESCE(%s, exchange),
                            ri_url = COALESCE(%s, ri_url),
                            active = TRUE,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            item["company_name"], name_key, regulator_id,
                            item.get("tax_id") or None, item.get("exchange") or None,
                            item.get("ri_url") or None, company_id,
                        ),
                    )
                else:
                    company_id = str(uuid4())
                    connection.execute(
                        """
                        INSERT INTO ir_companies
                            (id, market, company_name, name_key, regulator_id, tax_id, exchange, ri_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            company_id, market, item["company_name"], name_key, regulator_id,
                            item.get("tax_id") or None, item.get("exchange") or None,
                            item.get("ri_url") or None,
                        ),
                    )
                symbol = str(item.get("symbol") or "").upper()
                if symbol:
                    connection.execute(
                        """
                        INSERT INTO ir_security_map (market, symbol, company_id)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (market, symbol) DO UPDATE
                        SET company_id = EXCLUDED.company_id, updated_at = now()
                        """,
                        (market, symbol, company_id),
                    )
            connection.commit()
        return len(items)

    def list_ir_companies(self, market: str | None = None) -> list[dict[str, Any]]:
        if not self.database_url:
            companies = []
            for company in self._ir_companies.values():
                if market and company["market"] != market:
                    continue
                payload = company.copy()
                payload["symbols"] = sorted(
                    symbol for (item_market, symbol), company_id in self._ir_security_map.items()
                    if item_market == company["market"] and company_id == company["id"]
                )
                companies.append(payload)
            return companies
        params: list[Any] = []
        where = ""
        if market:
            where = "WHERE company.market = %s"
            params.append(market)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT company.id::text, company.market, company.company_name,
                       company.name_key, company.regulator_id, company.tax_id,
                       company.exchange, company.ri_url, company.active,
                       company.updated_at,
                       COALESCE(array_agg(security.symbol ORDER BY security.symbol)
                           FILTER (WHERE security.symbol IS NOT NULL), ARRAY[]::text[]) AS symbols
                FROM ir_companies company
                LEFT JOIN ir_security_map security ON security.company_id = company.id
                {where}
                GROUP BY company.id
                ORDER BY company.market, company.company_name
                """,
                params,
            ).fetchall()
        keys = (
            "id", "market", "company_name", "name_key", "regulator_id", "tax_id",
            "exchange", "ri_url", "active", "updated_at", "symbols",
        )
        return [dict(zip(keys, row)) for row in rows]

    def save_ir_events(self, events: list[dict[str, Any]]) -> int:
        if not events:
            return 0
        if not self.database_url:
            for event in events:
                key = (event["source_code"], event["external_id"])
                existing = self._ir_events.get(key, {})
                event_id = existing.get("id", event.get("id", str(uuid4())))
                first_collected_at = existing.get("collected_at") or event.get("collected_at") or datetime.now().astimezone()
                valuation_status = (
                    existing.get("valuation_status")
                    if existing.get("reviewed_at") or existing.get("valuation_status") == "incorporated"
                    else event.get("valuation_status", "informational")
                )
                self._ir_events[key] = {
                    **existing,
                    **event,
                    "id": event_id,
                    "collected_at": first_collected_at,
                    "valuation_status": valuation_status,
                }
                if event.get("valuation_relevant"):
                    market = str(event.get("market") or "").upper()
                    company_id = event.get("company_id")
                    symbols = {
                        symbol for (item_market, symbol), mapped_company in self._ir_security_map.items()
                        if item_market == market and mapped_company == company_id
                    }
                    if event.get("symbol"):
                        symbols.add(str(event["symbol"]).upper())
                    for symbol in symbols:
                        if market == "B3" and re.search(r"[0-9]F$", symbol):
                            continue
                        self._ir_valuation_queue.setdefault(
                            (str(event_id), symbol),
                            {
                                "event_id": str(event_id),
                                "market": market,
                                "symbol": symbol,
                                "status": "queued",
                                "attempts": 0,
                                "queued_at": datetime.now().astimezone(),
                                "last_error": "",
                            },
                        )
            return len(events)
        rows = []
        for event in events:
            rows.append((
                event.get("id") or str(uuid4()), event["source_code"], event["external_id"],
                event.get("company_id"), event["market"], event.get("symbol"), event["company_name"],
                event.get("regulator_id"), event["event_type"], event.get("form"), event["title"],
                event.get("summary", ""), event["published_at"], event.get("published_time_precision", "datetime"),
                event.get("reference_date"), event["official_url"], event.get("document_url"),
                event.get("materiality", "medium"), bool(event.get("valuation_relevant")),
                event.get("valuation_status", "informational"),
                json.dumps(event.get("raw_metadata", {}), ensure_ascii=False),
                event.get("collected_at") or datetime.now().astimezone(),
            ))
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO ir_events
                        (id, source_code, external_id, company_id, market, symbol, company_name,
                         regulator_id, event_type, form, title, summary, published_at,
                         published_time_precision, reference_date, official_url, document_url,
                         materiality, valuation_relevant, valuation_status, raw_metadata, collected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (source_code, external_id) DO UPDATE
                    SET company_id = COALESCE(EXCLUDED.company_id, ir_events.company_id),
                        symbol = COALESCE(EXCLUDED.symbol, ir_events.symbol),
                        company_name = EXCLUDED.company_name,
                        regulator_id = COALESCE(EXCLUDED.regulator_id, ir_events.regulator_id),
                        event_type = EXCLUDED.event_type,
                        form = EXCLUDED.form,
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        published_at = EXCLUDED.published_at,
                        published_time_precision = EXCLUDED.published_time_precision,
                        reference_date = EXCLUDED.reference_date,
                        official_url = EXCLUDED.official_url,
                        document_url = EXCLUDED.document_url,
                        materiality = EXCLUDED.materiality,
                        valuation_relevant = EXCLUDED.valuation_relevant,
                        valuation_status = CASE
                            WHEN ir_events.reviewed_at IS NOT NULL
                              OR ir_events.valuation_status = 'incorporated'
                            THEN ir_events.valuation_status
                            ELSE EXCLUDED.valuation_status
                        END,
                        raw_metadata = EXCLUDED.raw_metadata,
                        collected_at = LEAST(ir_events.collected_at, EXCLUDED.collected_at),
                        updated_at = now()
                    """,
                    rows,
                )
                relevant_rows = [row for row in rows if row[18]]
                if relevant_rows:
                    cursor.execute(
                        """
                        WITH incoming(source_code, external_id) AS (
                            SELECT * FROM unnest(%s::text[], %s::text[])
                        )
                        INSERT INTO ir_valuation_queue (event_id, market, symbol)
                        SELECT event.id, security.market, security.symbol
                        FROM ir_events event
                        JOIN incoming
                          ON incoming.source_code = event.source_code
                         AND incoming.external_id = event.external_id
                        JOIN ir_security_map security ON security.company_id = event.company_id
                        WHERE event.valuation_relevant
                          AND NOT (security.market = 'B3' AND security.symbol ~ '[0-9]F$')
                        ON CONFLICT (event_id, market, symbol) DO NOTHING
                        """,
                        (
                            [row[1] for row in relevant_rows],
                            [row[2] for row in relevant_rows],
                        ),
                    )
            connection.commit()
        return len(events)

    def claim_ir_valuation_updates(self, limit: int = 12) -> list[dict[str, Any]]:
        now = datetime.now().astimezone()
        if not self.database_url:
            claimed = []
            for item in sorted(self._ir_valuation_queue.values(), key=lambda row: row["queued_at"]):
                if item["status"] not in {"queued", "processing"}:
                    continue
                item.update({"status": "processing", "updated_at": now})
                claimed.append(item.copy())
                if len(claimed) >= limit:
                    break
            return claimed
        with self.connection() as connection:
            rows = connection.execute(
                """
                WITH pending AS (
                    SELECT event_id, market, symbol
                    FROM ir_valuation_queue
                    WHERE status = 'queued'
                       OR (status = 'processing' AND updated_at < now() - interval '30 minutes')
                    ORDER BY queued_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE ir_valuation_queue queue
                SET status = 'processing', updated_at = now()
                FROM pending
                WHERE queue.event_id = pending.event_id
                  AND queue.market = pending.market
                  AND queue.symbol = pending.symbol
                RETURNING queue.event_id::text, queue.market, queue.symbol,
                          queue.attempts, queue.queued_at
                """,
                (limit,),
            ).fetchall()
            connection.commit()
        keys = ("event_id", "market", "symbol", "attempts", "queued_at")
        return [dict(zip(keys, row)) for row in rows]

    def finish_ir_valuation_updates(
        self,
        updates: list[dict[str, Any]],
        *,
        succeeded: bool,
        error: str = "",
        incorporate_events: bool = False,
    ) -> None:
        if not updates:
            return
        now = datetime.now().astimezone()
        keys = [(str(item["event_id"]), str(item["symbol"]).upper()) for item in updates]
        if not self.database_url:
            for key in keys:
                item = self._ir_valuation_queue.get(key)
                if not item:
                    continue
                attempts = int(item.get("attempts") or 0) + (0 if succeeded else 1)
                item.update({
                    "status": "applied" if succeeded else ("failed" if attempts >= 3 else "queued"),
                    "attempts": attempts,
                    "processed_at": now if succeeded else None,
                    "last_error": error[:500],
                    "updated_at": now,
                })
            if succeeded and incorporate_events:
                event_ids = {event_id for event_id, _ in keys}
                for event_id in event_ids:
                    event_updates = [
                        item for item in self._ir_valuation_queue.values()
                        if str(item.get("event_id")) == event_id
                    ]
                    if event_updates and all(item.get("status") == "applied" for item in event_updates):
                        event = next(
                            (item for item in self._ir_events.values() if str(item.get("id")) == event_id),
                            None,
                        )
                        if event:
                            event.update({
                                "valuation_status": "incorporated",
                                "review_note": (
                                    event.get("review_note")
                                    or "Automatically incorporated after successful valuation refresh."
                                ),
                                "updated_at": now,
                            })
            return
        with self.connection() as connection:
            for event_id, symbol in keys:
                if succeeded:
                    connection.execute(
                        """
                        UPDATE ir_valuation_queue
                        SET status = 'applied', processed_at = now(), last_error = '', updated_at = now()
                        WHERE event_id = %s AND symbol = %s
                        """,
                        (event_id, symbol),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE ir_valuation_queue
                        SET attempts = attempts + 1,
                            status = CASE WHEN attempts + 1 >= 3 THEN 'failed' ELSE 'queued' END,
                            last_error = %s,
                            updated_at = now()
                        WHERE event_id = %s AND symbol = %s
                        """,
                        (error[:500], event_id, symbol),
                    )
            if succeeded and incorporate_events:
                event_ids = sorted({event_id for event_id, _ in keys})
                connection.execute(
                    """
                    UPDATE ir_events event
                    SET valuation_status = 'incorporated',
                        review_note = CASE
                            WHEN event.review_note = ''
                            THEN 'Automatically incorporated after successful valuation refresh.'
                            ELSE event.review_note
                        END,
                        updated_at = now()
                    WHERE event.id = ANY(%s::uuid[])
                      AND NOT EXISTS (
                          SELECT 1
                          FROM ir_valuation_queue queue
                          WHERE queue.event_id = event.id
                            AND queue.status <> 'applied'
                      )
                    """,
                    (event_ids,),
                )
            connection.commit()

    def queue_ir_event_for_valuation(self, event_id: str) -> int:
        if not self.database_url:
            event = next((row for row in self._ir_events.values() if row.get("id") == event_id), None)
            if not event:
                return 0
            market = str(event.get("market") or "").upper()
            company_id = event.get("company_id")
            symbols = {
                symbol for (item_market, symbol), mapped_company in self._ir_security_map.items()
                if item_market == market and mapped_company == company_id
            }
            for symbol in symbols:
                if market == "B3" and re.search(r"[0-9]F$", symbol):
                    continue
                self._ir_valuation_queue[(event_id, symbol)] = {
                    "event_id": event_id, "market": market, "symbol": symbol,
                    "status": "queued", "attempts": 0, "queued_at": datetime.now().astimezone(),
                    "last_error": "",
                }
            return len(symbols)
        with self.connection() as connection:
            result = connection.execute(
                """
                INSERT INTO ir_valuation_queue (event_id, market, symbol)
                SELECT event.id, security.market, security.symbol
                FROM ir_events event
                JOIN ir_security_map security ON security.company_id = event.company_id
                WHERE event.id = %s AND event.valuation_relevant
                  AND NOT (security.market = 'B3' AND security.symbol ~ '[0-9]F$')
                ON CONFLICT (event_id, market, symbol) DO UPDATE
                SET status = 'queued', attempts = 0, queued_at = now(),
                    processed_at = NULL, last_error = '', updated_at = now()
                """,
                (event_id,),
            )
            connection.commit()
        return result.rowcount

    def list_ir_events(
        self,
        *,
        limit: int = 100,
        market: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        query: str | None = None,
        monitored_only: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.database_url:
            rows = list(self._ir_events.values())
            if monitored_only:
                monitored_ids = set(self._ir_security_map.values())
                rows = [row for row in rows if row.get("company_id") in monitored_ids]
            if market:
                rows = [row for row in rows if row.get("market") == market]
            if source:
                rows = [row for row in rows if row.get("source_code") == source]
            if event_type:
                rows = [row for row in rows if row.get("event_type") == event_type]
            if query:
                needle = query.casefold()
                rows = [row for row in rows if needle in f"{row.get('symbol', '')} {row.get('company_name', '')} {row.get('title', '')}".casefold()]
            return sorted(rows, key=lambda row: row["published_at"], reverse=True)[:limit]
        clauses: list[str] = []
        params: list[Any] = []
        if monitored_only:
            clauses.append("EXISTS (SELECT 1 FROM ir_security_map security WHERE security.company_id = event.company_id)")
        if market:
            clauses.append("event.market = %s")
            params.append(market)
        if source:
            clauses.append("event.source_code = %s")
            params.append(source)
        if event_type:
            clauses.append("event.event_type = %s")
            params.append(event_type)
        if query:
            clauses.append("(event.symbol ILIKE %s OR event.company_name ILIKE %s OR event.title ILIKE %s)")
            term = f"%{query}%"
            params.extend((term, term, term))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT event.id::text, event.source_code, event.market, event.symbol,
                       event.company_name, event.regulator_id, event.event_type, event.form,
                       event.title, event.summary, event.published_at,
                       event.published_time_precision, event.reference_date::text,
                       event.official_url, event.document_url, event.materiality,
                       event.valuation_relevant, event.valuation_status,
                       event.reviewed_at, event.review_note, event.collected_at
                FROM ir_events event
                {where}
                ORDER BY event.published_at DESC, event.created_at DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        keys = (
            "id", "source_code", "market", "symbol", "company_name", "regulator_id",
            "event_type", "form", "title", "summary", "published_at",
            "published_time_precision", "reference_date", "official_url", "document_url",
            "materiality", "valuation_relevant", "valuation_status", "reviewed_at",
            "review_note", "collected_at",
        )
        return [dict(zip(keys, row)) for row in rows]

    def ir_overview_stats(self, monitored_only: bool = True) -> dict[str, int]:
        now = datetime.now().astimezone()
        if not self.database_url:
            events = list(self._ir_events.values())
            if monitored_only:
                monitored_ids = set(self._ir_security_map.values())
                events = [event for event in events if event.get("company_id") in monitored_ids]
            latest_relevant: dict[str, dict[str, Any]] = {}
            for event in events:
                company_id = str(event.get("company_id") or "")
                if not company_id or not event.get("valuation_relevant"):
                    continue
                prior = latest_relevant.get(company_id)
                if not prior or event["published_at"] > prior["published_at"]:
                    latest_relevant[company_id] = event
            return {
                "total_events": len(events),
                "today_events": sum(event["published_at"].date() == now.date() for event in events),
                "pending_reviews": sum(event.get("valuation_status") == "pending_review" for event in latest_relevant.values()),
                "high_materiality": sum(event.get("materiality") == "high" for event in events),
                "monitored_companies": len(set(self._ir_security_map.values())),
            }
        with self.connection() as connection:
            row = connection.execute(
                f"""
                SELECT count(*),
                       count(*) FILTER (WHERE published_at::date = CURRENT_DATE),
                       count(*) FILTER (WHERE materiality = 'high'),
                       (SELECT count(DISTINCT company_id) FROM ir_security_map)
                FROM ir_events event
                {"WHERE EXISTS (SELECT 1 FROM ir_security_map security WHERE security.company_id = event.company_id)" if monitored_only else ""}
                """
            ).fetchone()
            pending = connection.execute(
                f"""
                SELECT count(*) FROM (
                    SELECT DISTINCT ON (event.company_id) event.valuation_status
                    FROM ir_events event
                    WHERE event.valuation_relevant
                      {"AND EXISTS (SELECT 1 FROM ir_security_map security WHERE security.company_id = event.company_id)" if monitored_only else ""}
                    ORDER BY event.company_id, event.published_at DESC
                ) latest
                WHERE latest.valuation_status = 'pending_review'
                """
            ).fetchone()
        return {
            "total_events": int(row[0]),
            "today_events": int(row[1]),
            "pending_reviews": int(pending[0]),
            "high_materiality": int(row[2]),
            "monitored_companies": int(row[3]),
        }

    def ir_source_health(self) -> dict[str, dict[str, Any]]:
        if not self.database_url:
            output: dict[str, dict[str, Any]] = {}
            for run in sorted(self._ingestion_runs.values(), key=lambda item: item["started_at"]):
                code = run.get("source_code")
                if code not in {"cvm", "sec", "ri", "finnhub"}:
                    continue
                output[code] = {
                    "last_status": run.get("status"),
                    "last_success_at": run.get("completed_at") if run.get("status") == "succeeded" else output.get(code, {}).get("last_success_at"),
                    "last_error": run.get("error_summary") if run.get("status") == "failed" else None,
                }
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (source.code)
                       source.code, run.status,
                       max(run.completed_at) FILTER (WHERE run.status = 'succeeded')
                           OVER (PARTITION BY source.code) AS last_success_at,
                       CASE WHEN run.status = 'failed' THEN run.error_summary END
                FROM data_sources source
                JOIN ingestion_runs run ON run.source_id = source.id
                WHERE source.code IN ('cvm', 'sec', 'ri', 'finnhub')
                ORDER BY source.code, run.started_at DESC
                """
            ).fetchall()
        return {row[0]: {"last_status": row[1], "last_success_at": row[2], "last_error": row[3]} for row in rows}

    def latest_valuation_ir_events(self, symbols: list[str], market: str = "B3") -> dict[str, dict[str, Any]]:
        clean = [symbol.upper() for symbol in symbols if symbol]
        if not clean:
            return {}
        if not self.database_url:
            output: dict[str, dict[str, Any]] = {}
            for symbol in clean:
                company_id = self._ir_security_map.get((market, symbol))
                matches = [
                    event for event in self._ir_events.values()
                    if event.get("company_id") == company_id and event.get("valuation_relevant")
                ]
                if matches:
                    output[symbol] = max(matches, key=lambda event: event["published_at"]).copy()
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (security.symbol)
                       security.symbol, event.id::text, event.event_type, event.title,
                       event.published_at, event.reference_date::text,
                       event.valuation_status, event.reviewed_at, event.source_code,
                       event.collected_at, event.summary, event.official_url,
                       event.document_url, event.company_name, event.materiality
                FROM ir_security_map security
                JOIN ir_events event ON event.company_id = security.company_id
                WHERE security.market = %s
                  AND security.symbol = ANY(%s)
                  AND event.valuation_relevant
                ORDER BY security.symbol, event.published_at DESC
                """,
                (market, clean),
            ).fetchall()
        keys = (
            "symbol", "id", "event_type", "title", "published_at", "reference_date",
            "valuation_status", "reviewed_at", "source_code", "collected_at",
            "summary", "official_url", "document_url", "company_name", "materiality",
        )
        return {row[0]: dict(zip(keys, row)) for row in rows}

    @staticmethod
    def _insider_transaction_direction(metadata: dict[str, Any]) -> int:
        """+1 buy, -1 sell, 0 unknown. Handles the two raw_metadata shapes
        insider Tatooine Updates events are stored with: CVM VLMO
        ({"movement": "Compra ..."/"Venda ..."}) and Finnhub/SEC Form 4
        ({"is_purchase": bool, "is_sale": bool, ...raw transaction})."""
        if metadata.get("source") == "cvm_vlmo":
            movement = str(metadata.get("movement") or "")
            return 1 if movement.startswith("Compra") else -1 if movement.startswith("Venda") else 0
        if metadata.get("is_purchase"):
            return 1
        if metadata.get("is_sale"):
            return -1
        return 0

    def insider_transaction_activity(
        self, symbols: list[str], market: str, since: datetime,
    ) -> dict[str, dict[str, int]]:
        """Buy/sell transaction counts per symbol over the lookback window, from
        CVM VLMO (B3) or Finnhub Form 4 (US) insider events -- both stored as
        source_code-tagged Tatooine Updates events with valuation_relevant=False
        (informational only), so this deliberately bypasses that filter and
        latest_valuation_ir_events entirely."""
        clean = [symbol.upper() for symbol in symbols if symbol]
        if not clean:
            return {}
        source_codes = ("cvm",) if market == "B3" else ("sec",)
        buckets: dict[str, dict[str, int]] = {}

        def accumulate(symbol: str, metadata: dict[str, Any]) -> None:
            direction = self._insider_transaction_direction(metadata)
            if direction == 0:
                return
            bucket = buckets.setdefault(symbol, {"buy_count": 0, "sell_count": 0})
            bucket["buy_count" if direction > 0 else "sell_count"] += 1

        if not self.database_url:
            for event in self._ir_events.values():
                symbol = event.get("symbol")
                published_at = event.get("published_at")
                if (
                    symbol not in clean
                    or event.get("market") != market
                    or event.get("source_code") not in source_codes
                    or event.get("event_type") != "Insider Transaction"
                    or not isinstance(published_at, datetime)
                    or published_at < since
                ):
                    continue
                accumulate(symbol, event.get("raw_metadata") or {})
        else:
            with self.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT symbol, raw_metadata
                    FROM ir_events
                    WHERE market = %s AND source_code = ANY(%s) AND event_type = 'Insider Transaction'
                      AND symbol = ANY(%s) AND published_at >= %s
                    """,
                    (market, list(source_codes), clean, since),
                ).fetchall()
            for symbol, raw_metadata in rows:
                metadata = raw_metadata if isinstance(raw_metadata, dict) else (json.loads(raw_metadata) if raw_metadata else {})
                accumulate(symbol, metadata)
        return {
            symbol: {**bucket, "total_count": bucket["buy_count"] + bucket["sell_count"]}
            for symbol, bucket in buckets.items()
        }

    def latest_news_sentiment(self, symbols: list[str], market: str = "US") -> dict[str, dict[str, Any]]:
        """Latest weekly Finnhub news-sentiment snapshot per symbol (raw_metadata
        with bullish_percent/bearish_percent/articles_last_week). US-only source."""
        clean = [symbol.upper() for symbol in symbols if symbol]
        if not clean:
            return {}
        if not self.database_url:
            output: dict[str, dict[str, Any]] = {}
            for symbol in clean:
                matches = [
                    event for event in self._ir_events.values()
                    if event.get("symbol") == symbol
                    and event.get("market") == market
                    and event.get("source_code") == "finnhub"
                    and event.get("event_type") == "News Sentiment"
                ]
                if matches:
                    output[symbol] = dict(max(matches, key=lambda event: event["published_at"]).get("raw_metadata") or {})
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, raw_metadata
                FROM ir_events
                WHERE market = %s AND source_code = 'finnhub' AND event_type = 'News Sentiment'
                  AND symbol = ANY(%s)
                ORDER BY symbol, published_at DESC
                """,
                (market, clean),
            ).fetchall()
        return {
            symbol: (raw_metadata if isinstance(raw_metadata, dict) else (json.loads(raw_metadata) if raw_metadata else {}))
            for symbol, raw_metadata in rows
        }

    def reconcile_ir_results(self, fundamentals_by_symbol: dict[str, str | None], market: str = "B3") -> None:
        """Auto-incorporate only financial-result filings covered by an equal/newer reporting period."""
        valid_fundamentals: dict[str, str] = {}
        for symbol, as_of in fundamentals_by_symbol.items():
            if not as_of:
                continue
            try:
                valid_fundamentals[symbol] = date.fromisoformat(str(as_of)[:10]).isoformat()
            except ValueError:
                logger.warning("Ignoring invalid fundamentals date for %s: %s", symbol, as_of)
        if not self.database_url:
            for symbol, as_of in valid_fundamentals.items():
                company_id = self._ir_security_map.get((market, symbol))
                for event in self._ir_events.values():
                    if (
                        event.get("company_id") == company_id
                        and event.get("event_type") == "Financial Results"
                        and event.get("reference_date")
                        and str(event["reference_date"])[:10] <= str(as_of)[:10]
                        and not event.get("reviewed_at")
                    ):
                        event["valuation_status"] = "incorporated"
            return
        with self.connection() as connection:
            for symbol, as_of in valid_fundamentals.items():
                connection.execute(
                    """
                    UPDATE ir_events event
                    SET valuation_status = 'incorporated', updated_at = now()
                    FROM ir_security_map security
                    WHERE security.company_id = event.company_id
                      AND security.market = %s AND security.symbol = %s
                      AND event.event_type = 'Financial Results'
                      AND event.reference_date IS NOT NULL
                      AND event.reference_date <= %s::date
                      AND event.reviewed_at IS NULL
                    """,
                    (market, symbol, str(as_of)[:10]),
                )
            connection.commit()

    def review_ir_event(self, event_id: str, note: str) -> bool:
        now = datetime.now().astimezone()
        if not self.database_url:
            for event in self._ir_events.values():
                if event.get("id") == event_id:
                    event.update({"valuation_status": "incorporated", "reviewed_at": now, "review_note": note})
                    self.queue_ir_event_for_valuation(event_id)
                    return True
            return False
        with self.connection() as connection:
            row = connection.execute(
                """
                UPDATE ir_events
                SET valuation_status = 'incorporated', reviewed_at = %s,
                    review_note = %s, updated_at = now()
                WHERE id = %s RETURNING id
                """,
                (now, note, event_id),
            ).fetchone()
            connection.commit()
        if row is not None:
            self.queue_ir_event_for_valuation(event_id)
        return row is not None

    def ir_watch_symbols(self) -> list[dict[str, Any]]:
        if not self.database_url:
            output = []
            for (market, symbol), company_id in self._ir_security_map.items():
                company = next((item for item in self._ir_companies.values() if item["id"] == company_id), None)
                if company:
                    output.append({**company, "market": market, "symbol": symbol})
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT security.market, security.symbol, company.company_name,
                       company.regulator_id, company.exchange, company.ri_url
                FROM ir_security_map security
                JOIN ir_companies company ON company.id = security.company_id
                WHERE company.active
                ORDER BY security.market, security.symbol
                """
            ).fetchall()
        return [dict(zip(("market", "symbol", "company_name", "regulator_id", "exchange", "ri_url"), row)) for row in rows]

    def save_ir_report_export(self, filename: str, event_count: int, filters: dict[str, Any]) -> None:
        if not self.database_url:
            return
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO ir_report_exports (id, filename, generated_at, event_count, filters)
                VALUES (%s, %s, now(), %s, %s::jsonb)
                """,
                (str(uuid4()), filename, event_count, json.dumps(filters)),
            )
            connection.commit()

    def ensure_methodology_version(
        self,
        methodology_key: str,
        version: int,
        parameters: dict[str, Any],
        rationale: str,
    ) -> str:
        key = (methodology_key, version)
        if not self.database_url:
            existing = self._methodologies.get(key)
            if existing:
                existing.update({"parameters": parameters, "rationale": rationale})
                return existing["id"]
            methodology_id = str(uuid4())
            self._methodologies[key] = {
                "id": methodology_id,
                "methodology_key": methodology_key,
                "version": version,
                "status": "active",
                "parameters": parameters,
                "rationale": rationale,
            }
            return methodology_id
        with self.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO methodology_versions
                    (id, methodology_key, version, status, parameters, rationale, activated_at)
                VALUES (%s, %s, %s, 'active', %s::jsonb, %s, now())
                ON CONFLICT (methodology_key, version) DO UPDATE
                SET parameters = EXCLUDED.parameters,
                    rationale = EXCLUDED.rationale,
                    status = 'active',
                    activated_at = COALESCE(methodology_versions.activated_at, now())
                RETURNING id::text
                """,
                (str(uuid4()), methodology_key, version, json.dumps(parameters), rationale),
            ).fetchone()
            connection.commit()
        return str(row[0])

    def active_methodology_version_id(self, methodology_key: str, version: int) -> str | None:
        if not self.database_url:
            item = self._methodologies.get((methodology_key, version))
            return str(item["id"]) if item else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id::text
                FROM methodology_versions
                WHERE methodology_key = %s AND version = %s
                ORDER BY activated_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """,
                (methodology_key, version),
            ).fetchone()
        return str(row[0]) if row else None

    def save_analysis_snapshot(
        self,
        analysis_type: str,
        entity_key: str,
        methodology_version_id: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        published_at: datetime,
    ) -> str:
        snapshot_id = str(uuid4())
        prior_snapshot: dict[str, Any] | None = None
        if not self.database_url:
            prior_snapshot = self.latest_analysis_snapshot(analysis_type, entity_key)
            current_snapshot = {
                "id": snapshot_id,
                "analysis_type": analysis_type,
                "entity_key": entity_key,
                "methodology_version_id": methodology_version_id,
                "inputs": inputs,
                "outputs": outputs,
                "published_at": published_at,
            }
            self._analysis_snapshots.append(current_snapshot)
            self._capture_valuation_changes(current_snapshot, prior_snapshot)
            return snapshot_id
        with self.connection() as connection:
            prior = connection.execute(
                """
                SELECT id::text, inputs, outputs, published_at, methodology_version_id::text
                FROM analysis_snapshots
                WHERE analysis_type = %s AND entity_key = %s
                ORDER BY published_at DESC LIMIT 1
                """,
                (analysis_type, entity_key),
            ).fetchone()
            if prior:
                prior_snapshot = dict(zip(
                    ("id", "inputs", "outputs", "published_at", "methodology_version_id"),
                    prior,
                ))
            connection.execute(
                """
                INSERT INTO analysis_snapshots
                    (id, analysis_type, entity_key, methodology_version_id,
                     inputs, outputs, published_at, supersedes_id)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    snapshot_id,
                    analysis_type,
                    entity_key,
                    methodology_version_id,
                    json.dumps(inputs),
                    json.dumps(outputs),
                    published_at,
                    prior[0] if prior else None,
                ),
            )
            connection.commit()
        self._capture_valuation_changes(
            {
                "id": snapshot_id,
                "analysis_type": analysis_type,
                "entity_key": entity_key,
                "methodology_version_id": methodology_version_id,
                "inputs": inputs,
                "outputs": outputs,
                "published_at": published_at,
            },
            prior_snapshot,
        )
        return snapshot_id

    def latest_analysis_snapshot_published_at(self, analysis_type: str, entity_key: str) -> datetime | None:
        """Timestamp-only counterpart of latest_analysis_snapshot(), for
        callers that need to check freshness without paying for the full
        outputs payload (e.g. a ~325-row valuation_universe snapshot) on
        every check."""
        if not self.database_url:
            matches = [
                item for item in self._analysis_snapshots
                if item.get("analysis_type") == analysis_type and item.get("entity_key") == entity_key
            ]
            return max((item["published_at"] for item in matches), default=None)
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT published_at FROM analysis_snapshots
                WHERE analysis_type = %s AND entity_key = %s
                ORDER BY published_at DESC LIMIT 1
                """,
                (analysis_type, entity_key),
            ).fetchone()
        return row[0] if row else None

    def latest_analysis_snapshot(self, analysis_type: str, entity_key: str) -> dict[str, Any] | None:
        if not self.database_url:
            matches = [
                item for item in self._analysis_snapshots
                if item.get("analysis_type") == analysis_type and item.get("entity_key") == entity_key
            ]
            return max(matches, key=lambda item: item["published_at"]).copy() if matches else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id::text, inputs, outputs, published_at, methodology_version_id::text
                FROM analysis_snapshots
                WHERE analysis_type = %s AND entity_key = %s
                ORDER BY published_at DESC LIMIT 1
                """,
                (analysis_type, entity_key),
            ).fetchone()
        if not row:
            return None
        return dict(zip(("id", "inputs", "outputs", "published_at", "methodology_version_id"), row))

    def latest_analysis_snapshots(
        self,
        analysis_type: str,
        entity_keys: list[str],
    ) -> dict[str, dict[str, Any]]:
        clean_keys = list(dict.fromkeys(key for key in entity_keys if key))
        if not clean_keys:
            return {}
        if not self.database_url:
            output: dict[str, dict[str, Any]] = {}
            for key in clean_keys:
                snapshot = self.latest_analysis_snapshot(analysis_type, key)
                if snapshot:
                    output[key] = snapshot
            return output
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (entity_key)
                       entity_key, id::text, inputs, outputs, published_at,
                       methodology_version_id::text
                FROM analysis_snapshots
                WHERE analysis_type = %s AND entity_key = ANY(%s)
                ORDER BY entity_key, published_at DESC
                """,
                (analysis_type, clean_keys),
            ).fetchall()
        keys = ("id", "inputs", "outputs", "published_at", "methodology_version_id")
        return {row[0]: dict(zip(keys, row[1:])) for row in rows}

    def analysis_snapshot_at_or_before(
        self,
        analysis_type: str,
        entity_key: str,
        cutoff: datetime,
    ) -> dict[str, Any] | None:
        if not self.database_url:
            matches = [
                item for item in self._analysis_snapshots
                if item.get("analysis_type") == analysis_type
                and item.get("entity_key") == entity_key
                and item.get("published_at") <= cutoff
            ]
            return max(matches, key=lambda item: item["published_at"]).copy() if matches else None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id::text, inputs, outputs, published_at, methodology_version_id::text
                FROM analysis_snapshots
                WHERE analysis_type = %s AND entity_key = %s AND published_at <= %s
                ORDER BY published_at DESC LIMIT 1
                """,
                (analysis_type, entity_key, cutoff),
            ).fetchone()
        if not row:
            return None
        return dict(zip(("id", "inputs", "outputs", "published_at", "methodology_version_id"), row))

    def backfill_valuation_change_baseline(self) -> None:
        if not self.database_url:
            return
        with self.connection() as connection:
            count = int(connection.execute("SELECT count(*) FROM valuation_change_records").fetchone()[0])
        if count:
            return
        snapshot = self.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
        if not snapshot:
            return
        self._capture_valuation_changes(
            {
                **snapshot,
                "analysis_type": "valuation_universe",
                "entity_key": "B3_UNIVERSE",
            },
            None,
        )

    def _valuation_logo_lookup(self) -> dict[tuple[str, str], str]:
        """{(market, symbol): logo_url} from each market's latest bulk universe
        snapshot. Ben Kenobi Records' valuation_change_records never stored its
        own logo_url (no column, no migration needed for this), but the B3/US
        screeners already capture one per company in their universe rows -- read
        it from there instead of a broken/nonexistent proxy endpoint or a
        market-agnostic external logo CDN guess."""
        snapshots = self.latest_analysis_snapshots(
            "valuation_universe", ["B3_UNIVERSE", "NASDAQ_UNIVERSE", "NYSE_UNIVERSE"],
        )
        market_by_entity_key = {"B3_UNIVERSE": "B3", "NASDAQ_UNIVERSE": "NASDAQ", "NYSE_UNIVERSE": "NYSE"}
        lookup: dict[tuple[str, str], str] = {}
        for entity_key, snapshot in snapshots.items():
            rows = (snapshot.get("outputs") or {}).get("rows")
            if not isinstance(rows, list):
                continue
            market_for_key = market_by_entity_key[entity_key]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                logo_url = row.get("logo_url")
                symbol = str(row.get("symbol") or "").upper()
                if symbol and logo_url:
                    lookup[(market_for_key, symbol)] = logo_url
        return lookup

    def list_valuation_changes(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        symbol: str | None = None,
        market: str | None = None,
        trigger_type: str | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        clean_symbol = (symbol or "").strip().upper()
        logo_lookup = self._valuation_logo_lookup()
        if not self.database_url:
            records = [
                item.copy() for item in self._valuation_changes
                if (not clean_symbol or clean_symbol in item["symbol"] or clean_symbol in item["company_name"].upper())
                and (not market or item["market"] == market)
                and (not trigger_type or item["trigger_type"] == trigger_type)
            ]
            records.sort(key=lambda item: (item["changed_at"], item["id"]), reverse=True)
            page = records[offset:offset + limit]
            for item in page:
                item["logo_url"] = logo_lookup.get((item["market"], item["symbol"]))
            return len(records), page

        conditions: list[str] = []
        params: list[Any] = []
        if clean_symbol:
            conditions.append("(symbol ILIKE %s OR company_name ILIKE %s)")
            params.extend((f"%{clean_symbol}%", f"%{clean_symbol}%"))
        if market:
            conditions.append("market = %s")
            params.append(market)
        if trigger_type:
            conditions.append("trigger_type = %s")
            params.append(trigger_type)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connection() as connection:
            total = int(connection.execute(
                f"SELECT count(*) FROM valuation_change_records {where}",
                params,
            ).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT id::text, snapshot_id::text, market, symbol, company_name,
                       changed_at, trigger_type, trigger_title, trigger_summary,
                       source_name, source_url, currency, old_tp, new_tp,
                       tp_change_percent, old_buy_in, new_buy_in,
                       old_consensus_tp, new_consensus_tp, price,
                       old_confidence, new_confidence, methodology_name,
                       methodology_version, metadata
                FROM valuation_change_records
                {where}
                ORDER BY changed_at DESC, created_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                [*params, limit, offset],
            ).fetchall()
        keys = (
            "id", "snapshot_id", "market", "symbol", "company_name", "changed_at",
            "trigger_type", "trigger_title", "trigger_summary", "source_name",
            "source_url", "currency", "old_tp", "new_tp", "tp_change_percent",
            "old_buy_in", "new_buy_in", "old_consensus_tp", "new_consensus_tp",
            "price", "old_confidence", "new_confidence", "methodology_name",
            "methodology_version", "metadata",
        )
        items = [dict(zip(keys, row)) for row in rows]
        for item in items:
            item["logo_url"] = logo_lookup.get((item["market"], item["symbol"]))
        return total, items

    def _capture_valuation_changes(
        self,
        current_snapshot: dict[str, Any],
        prior_snapshot: dict[str, Any] | None,
    ) -> None:
        analysis_type = str(current_snapshot.get("analysis_type") or "")
        if analysis_type not in {"valuation_universe", "security_valuation", "one_pager_valuation"}:
            return
        current_rows = self._valuation_rows(analysis_type, current_snapshot.get("outputs"))
        if not current_rows:
            return
        prior_rows = self._valuation_rows(analysis_type, (prior_snapshot or {}).get("outputs"))
        previous_by_symbol = {
            str(item.get("symbol") or "").upper(): item
            for item in prior_rows if item.get("symbol")
        }
        changed_rows: list[tuple[dict[str, Any], dict[str, Any] | None, list[str]]] = []
        for current in current_rows:
            symbol = str(current.get("symbol") or "").upper()
            new_tp = self._valuation_number(current.get("our_tp") or current.get("c3po_tp"))
            if not symbol or not new_tp or new_tp <= 0:
                continue
            previous = previous_by_symbol.get(symbol)
            fields = self._valuation_changed_fields(previous, current)
            if previous is None or fields:
                changed_rows.append((current, previous, fields or ["initial_valuation"]))
        if not changed_rows:
            return

        inputs = current_snapshot.get("inputs") if isinstance(current_snapshot.get("inputs"), dict) else {}
        entity_key = str(current_snapshot.get("entity_key") or "")
        if entity_key in {"NASDAQ_UNIVERSE", "NYSE_UNIVERSE"}:
            # The bulk US screener snapshot's own entity_key names the exact
            # exchange -- authoritative, unlike inputs.market (which historically
            # carried the same "NASDAQ"/"NYSE" string but got collapsed to a
            # generic "US" or mislabeled "B3" by earlier fallback logic; see
            # db/018_correct_us_valuation_change_markets.sql for the backfill).
            market = entity_key.split("_")[0]
        elif entity_key == "B3_UNIVERSE":
            market = "B3"
        else:
            raw_market = str(inputs.get("market") or ("B3" if analysis_type != "one_pager_valuation" else "US")).upper()
            market = raw_market if raw_market in {"B3", "NASDAQ", "NYSE", "US"} else "B3"
        events = self.latest_valuation_ir_events(
            [str(current.get("symbol") or "") for current, _, _ in changed_rows],
            market=market,
        )
        changed_at = current_snapshot.get("published_at")
        if not isinstance(changed_at, datetime):
            changed_at = datetime.now().astimezone()
        prior_at = (prior_snapshot or {}).get("published_at")
        records: list[dict[str, Any]] = []
        for current, previous, changed_fields in changed_rows:
            symbol = str(current.get("symbol") or "").upper()
            event = events.get(symbol)
            event_at = self._latest_datetime(
                event.get("published_at") if event else None,
                event.get("collected_at") if event else None,
            )
            event_is_new = previous is not None and self._is_after(event_at, prior_at)
            change_event = event if event_is_new else None
            methodology_changed = bool(
                prior_snapshot
                and prior_snapshot.get("methodology_version_id") != current_snapshot.get("methodology_version_id")
            )
            if previous is None:
                trigger_type = "initial"
                trigger_title = "Registro inicial do valuation canônico"
            elif event_is_new and str((event or {}).get("event_type") or "") == "Financial Results":
                trigger_type = "financial_results"
                trigger_title = str((event or {}).get("title") or "Novo resultado financeiro incorporado")
            elif event_is_new:
                trigger_type = "material_event"
                trigger_title = str((event or {}).get("title") or "Novo material relevante incorporado")
            elif methodology_changed:
                trigger_type = "methodology"
                trigger_title = "Metodologia de valuation atualizada"
            elif analysis_type == "one_pager_valuation":
                trigger_type = "web_research"
                trigger_title = str(inputs.get("trigger_title") or "One Pager recalculado com novas evidências")
            else:
                trigger_type = "market_data"
                trigger_title = "Recalibração com dados de mercado e fundamentos"

            old_tp = self._valuation_number((previous or {}).get("our_tp") or (previous or {}).get("c3po_tp"))
            new_tp = self._valuation_number(current.get("our_tp") or current.get("c3po_tp")) or 0.0
            old_buy_in = self._valuation_number((previous or {}).get("buy_in"))
            new_buy_in = self._valuation_number(current.get("buy_in"))
            old_consensus = self._valuation_number((previous or {}).get("public_consensus_tp") or (previous or {}).get("consensus_tp"))
            new_consensus = self._valuation_number(current.get("public_consensus_tp") or current.get("consensus_tp"))
            old_confidence = self._valuation_number((previous or {}).get("valuation_confidence") or (previous or {}).get("confidence"))
            new_confidence = self._valuation_number(current.get("valuation_confidence") or current.get("confidence"))
            change_percent = ((new_tp / old_tp) - 1) * 100 if old_tp and old_tp > 0 else None
            currency = str(current.get("currency") or ("BRL" if market == "B3" else "USD"))
            source_name = str(
                (change_event or {}).get("source_code")
                or inputs.get("source")
                or current.get("source")
                or "C3PO valuation engine"
            )
            source_url = (
                (change_event or {}).get("document_url")
                or (change_event or {}).get("official_url")
                or inputs.get("source_url")
            )
            company_name = str(
                current.get("name")
                or current.get("company_name")
                or (event or {}).get("company_name")
                or symbol
            )
            summary = str((change_event or {}).get("summary") or "").strip()
            if not summary:
                summary = self._valuation_change_summary(
                    currency,
                    old_tp,
                    new_tp,
                    old_buy_in,
                    new_buy_in,
                    changed_fields,
                )
            records.append({
                "id": str(uuid4()),
                "snapshot_id": current_snapshot.get("id"),
                "market": market,
                "symbol": symbol,
                "company_name": company_name,
                "changed_at": changed_at,
                "trigger_type": trigger_type,
                "trigger_title": trigger_title,
                "trigger_summary": summary[:2000],
                "source_name": source_name.upper() if source_name.lower() in {"cvm", "sec", "ri"} else source_name,
                "source_url": str(source_url) if source_url else None,
                "currency": currency,
                "old_tp": old_tp,
                "new_tp": new_tp,
                "tp_change_percent": change_percent,
                "old_buy_in": old_buy_in,
                "new_buy_in": new_buy_in,
                "old_consensus_tp": old_consensus,
                "new_consensus_tp": new_consensus,
                "price": self._valuation_number(current.get("price")),
                "old_confidence": old_confidence,
                "new_confidence": new_confidence,
                "methodology_name": str(inputs.get("methodology_name") or "C3PO Valuation Model"),
                "methodology_version": self._valuation_integer(inputs.get("methodology_version")),
                "metadata": {
                    "changed_fields": changed_fields,
                    "event_id": (change_event or {}).get("id"),
                    "fundamentals_as_of": current.get("fundamentals_as_of"),
                    "analyst_count": current.get("analyst_count"),
                    "consensus_weight_percent": current.get("consensus_weight_percent"),
                    "analysis_type": analysis_type,
                },
            })
        self._store_valuation_changes(records)

    def _store_valuation_changes(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        if not self.database_url:
            existing = {
                (item.get("snapshot_id"), item["market"], item["symbol"])
                for item in self._valuation_changes
            }
            self._valuation_changes.extend(
                item for item in records
                if (item.get("snapshot_id"), item["market"], item["symbol"]) not in existing
            )
            return
        values = [(
            item["id"], item.get("snapshot_id"), item["market"], item["symbol"],
            item["company_name"], item["changed_at"], item["trigger_type"],
            item["trigger_title"], item["trigger_summary"], item["source_name"],
            item.get("source_url"), item["currency"], item.get("old_tp"), item["new_tp"],
            item.get("tp_change_percent"), item.get("old_buy_in"), item.get("new_buy_in"),
            item.get("old_consensus_tp"), item.get("new_consensus_tp"), item.get("price"),
            item.get("old_confidence"), item.get("new_confidence"), item["methodology_name"],
            item.get("methodology_version"), json.dumps(item.get("metadata", {}), ensure_ascii=False),
        ) for item in records]
        with self.connection() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO valuation_change_records
                        (id, snapshot_id, market, symbol, company_name, changed_at,
                         trigger_type, trigger_title, trigger_summary, source_name,
                         source_url, currency, old_tp, new_tp, tp_change_percent,
                         old_buy_in, new_buy_in, old_consensus_tp, new_consensus_tp,
                         price, old_confidence, new_confidence, methodology_name,
                         methodology_version, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (snapshot_id, market, symbol) WHERE snapshot_id IS NOT NULL
                    DO NOTHING
                    """,
                    values,
                )
            connection.commit()

    @staticmethod
    def _valuation_rows(analysis_type: str, outputs: Any) -> list[dict[str, Any]]:
        if not isinstance(outputs, dict):
            return []
        if analysis_type == "valuation_universe":
            rows = outputs.get("rows")
            return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
        row = outputs.get("row")
        return [row] if isinstance(row, dict) else []

    @classmethod
    def _valuation_changed_fields(cls, previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
        if previous is None:
            return []
        fields = (
            ("c3po_tp", "our_tp", "c3po_tp", 2),
            ("buy_in", "buy_in", "buy_in", 2),
            ("consensus_tp", "public_consensus_tp", "consensus_tp", 2),
            ("confidence", "valuation_confidence", "confidence", 1),
        )
        changed: list[str] = []
        for label, b3_key, pager_key, decimals in fields:
            old_value = cls._valuation_number(previous.get(b3_key) if b3_key in previous else previous.get(pager_key))
            new_value = cls._valuation_number(current.get(b3_key) if b3_key in current else current.get(pager_key))
            if old_value is None and new_value is None:
                continue
            if old_value is None or new_value is None or round(old_value, decimals) != round(new_value, decimals):
                changed.append(label)
        return changed

    @staticmethod
    def _valuation_change_summary(
        currency: str,
        old_tp: float | None,
        new_tp: float,
        old_buy_in: float | None,
        new_buy_in: float | None,
        changed_fields: list[str],
    ) -> str:
        prefix = "R$" if currency.upper() == "BRL" else "US$" if currency.upper() == "USD" else currency.upper()
        if old_tp is None:
            return f"Valuation canônico registrado em {prefix} {new_tp:,.2f}, com trilha de fontes e metodologia."
        parts = [f"C3PO TP passou de {prefix} {old_tp:,.2f} para {prefix} {new_tp:,.2f}"]
        if "buy_in" in changed_fields and old_buy_in is not None and new_buy_in is not None:
            parts.append(f"buy-in de {prefix} {old_buy_in:,.2f} para {prefix} {new_buy_in:,.2f}")
        return "; ".join(parts) + "."

    @staticmethod
    def _valuation_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    @staticmethod
    def _valuation_integer(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _latest_datetime(*values: Any) -> datetime | None:
        dates = [value for value in values if isinstance(value, datetime)]
        return max(dates) if dates else None

    @staticmethod
    def _is_after(candidate: Any, reference: Any) -> bool:
        if not isinstance(candidate, datetime) or not isinstance(reference, datetime):
            return False
        if candidate.tzinfo is None:
            candidate = candidate.astimezone()
        if reference.tzinfo is None:
            reference = reference.astimezone()
        return candidate > reference
