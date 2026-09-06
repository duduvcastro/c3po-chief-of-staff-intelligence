"""Atomic V2 state + immutable hash-chained evidence, with no V1 dependencies.

Postgres transactions serialize collectors by epoch. The separate memory store
is explicit and used only by offline tests; the worker requires PostgreSQL.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from threading import RLock
from typing import Callable


class ShadowIntegrityError(ValueError):
    pass


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(value) -> str:
    return sha256(canonical(value)).hexdigest()


def utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ShadowIntegrityError("TIMESTAMP_NOT_AWARE")
    return value.astimezone(timezone.utc)


def validate_epoch(epoch: str) -> None:
    if not isinstance(epoch, str) or not re.fullmatch(r"R2D2-V2-SHADOW-[A-Za-z0-9_-]{1,80}", epoch):
        raise ShadowIntegrityError("EPOCH_INVALID")


def _namespace(epoch: str, state: dict) -> None:
    validate_epoch(epoch)
    if state.get("epoch") != epoch:
        raise ShadowIntegrityError("EPOCH_NAMESPACE_MISMATCH")


def _transition(row: dict, transition: Callable, now: datetime):
    if digest(row["state"]) != row["state_sha"]:
        raise ShadowIntegrityError("STATE_HASH_MISMATCH")
    state, payloads, response = transition(deepcopy(row["state"]))
    recorded_at = max(utc(now), utc(state["last_cycle_at"])) if state.get("last_cycle_at") else utc(now)
    if (state["epoch"], state["manifest_sha"], state["release_sha"]) != (
            row["state"]["epoch"], row["manifest_sha"], row["state"]["release_sha"]):
        raise ShadowIntegrityError("EPOCH_IDENTITY_CHANGED")
    head = row["journal_head"]
    sequence = row["sequence"]
    records = []
    for payload in payloads:
        sequence += 1
        record = {"epoch": state["epoch"], "sequence": sequence,
                  "journal_key": payload["journal_key"], "recorded_at": recorded_at.isoformat(),
                  "payload": payload, "previous_sha": head}
        record["record_sha"] = head = digest(record)
        records.append(record)
    state_sha = digest(state)
    updated = {**row, "state": state, "state_sha": state_sha,
               "version": row["version"] + 1, "journal_head": head, "sequence": sequence,
               "updated_at": recorded_at.isoformat()}
    return updated, records, response


def _initial(initial: dict) -> dict:
    return {"state": deepcopy(initial), "state_sha": digest(initial),
            "manifest_sha": initial["manifest_sha"], "version": 0,
            "sequence": 0, "journal_head": ""}


class MemoryShadowStore:
    """Inject this explicitly for synthetic fixtures, never as a DB fallback."""
    def __init__(self):
        self._lock = RLock()
        self._rows: dict[str, dict] = {}
        self._journal: dict[str, list] = {}

    def atomic(self, epoch: str, initial: dict, transition: Callable, now: datetime):
        _namespace(epoch, initial)
        with self._lock:
            row = self._rows.get(epoch, _initial(initial))
            _namespace(epoch, row["state"])
            if row["state"]["release_sha"] != initial["release_sha"]:
                raise ShadowIntegrityError("RELEASE_REQUIRES_NEW_EPOCH")
            updated, records, response = _transition(row, transition, now)
            existing = {r["journal_key"] for r in self._journal.get(epoch, [])}
            keys = [r["journal_key"] for r in records]
            if existing.intersection(keys) or len(keys) != len(set(keys)):
                raise ShadowIntegrityError("JOURNAL_KEY_CONFLICT")
            self._rows[epoch] = updated
            self._journal.setdefault(epoch, []).extend(deepcopy(records))
            return deepcopy(response)

    def read(self, epoch: str) -> dict | None:
        with self._lock:
            row = self._rows.get(epoch)
            if row is None:
                return None
            if digest(row["state"]) != row["state_sha"]:
                raise ShadowIntegrityError("STATE_HASH_MISMATCH")
            return deepcopy(row)

    def journal(self, epoch: str) -> list:
        with self._lock:
            return deepcopy(self._journal.get(epoch, []))


class PostgresShadowStore:
    def __init__(self, connection_factory: Callable):
        self.connection_factory = connection_factory

    def atomic(self, epoch: str, initial: dict, transition: Callable, now: datetime):
        _namespace(epoch, initial)
        with self.connection_factory() as connection:
            if connection is None:
                raise ShadowIntegrityError("PERSISTENT_DATABASE_REQUIRED")
            connection.execute("""INSERT INTO r2d2_v2_shadow_epochs
                (epoch,manifest_sha,state,state_sha,updated_at) VALUES (%s,%s,%s::jsonb,%s,%s)
                ON CONFLICT(epoch) DO NOTHING""",
                (epoch, initial["manifest_sha"], canonical(initial).decode(), digest(initial), utc(now)))
            raw = connection.execute("""SELECT state,state_sha,manifest_sha,version,journal_head
                FROM r2d2_v2_shadow_epochs WHERE epoch=%s FOR UPDATE""", (epoch,)).fetchone()
            state, state_sha, manifest, version, head = raw
            _namespace(epoch, state)
            if state["release_sha"] != initial["release_sha"]:
                raise ShadowIntegrityError("RELEASE_REQUIRES_NEW_EPOCH")
            sequence = connection.execute("""SELECT COALESCE(MAX(sequence),0)
                FROM r2d2_v2_shadow_journal WHERE epoch=%s""", (epoch,)).fetchone()[0]
            row = dict(state=state, state_sha=state_sha, manifest_sha=manifest,
                       version=version, journal_head=head, sequence=sequence)
            updated, records, response = _transition(row, transition, now)
            for record in records:
                connection.execute("""INSERT INTO r2d2_v2_shadow_journal
                    (epoch,sequence,journal_key,recorded_at,payload,previous_sha,record_sha)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (epoch, record["sequence"], record["journal_key"], utc(record["recorded_at"]),
                     canonical(record["payload"]).decode(), record["previous_sha"], record["record_sha"]))
            connection.execute("""UPDATE r2d2_v2_shadow_epochs SET
                state=%s::jsonb,state_sha=%s,version=%s,journal_head=%s,updated_at=%s WHERE epoch=%s""",
                (canonical(updated["state"]).decode(), updated["state_sha"], updated["version"],
                 updated["journal_head"], utc(updated["updated_at"]), epoch))
            connection.commit()
            return response

    def read(self, epoch: str) -> dict | None:
        validate_epoch(epoch)
        with self.connection_factory() as connection:
            if connection is None:
                raise ShadowIntegrityError("PERSISTENT_DATABASE_REQUIRED")
            raw = connection.execute("""SELECT state,state_sha,manifest_sha,version,journal_head
                FROM r2d2_v2_shadow_epochs WHERE epoch=%s""", (epoch,)).fetchone()
        if raw is None:
            return None
        row = dict(zip(("state", "state_sha", "manifest_sha", "version", "journal_head"), raw))
        if digest(row["state"]) != row["state_sha"]:
            raise ShadowIntegrityError("STATE_HASH_MISMATCH")
        return row
