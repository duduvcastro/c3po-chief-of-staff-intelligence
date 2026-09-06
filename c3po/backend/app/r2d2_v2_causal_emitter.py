"""Opt-in causal-list emission, committed audit receipts and private recovery.

No daemon, provider call, application initialization or publication on import.
The emitter defaults OFF. Its connection must use an audited, separate role;
DDL/role provisioning is a prerequisite, never performed here. A publication
sink is injected and must be audited separately. Only aggregates/hashes reach it.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
from typing import Any, Callable, Protocol
from uuid import uuid4

from .r2d2_v2_causal_list import (Calendar, MAX_INPUT_BYTES, _decode,
    build_commitment, digest, validate_commitment)
from .r2d2_v2_store import ShadowIntegrityError, canonical, utc, validate_epoch

BUILT = "r2d2.v2.causal_list_built"
PUBLISHED = "r2d2.v2.causal_list_published"


class PublicationSink(Protocol):
    def __call__(self, artifact: dict[str, Any]) -> tuple[str, str]:
        """Durably publish public aggregates, then return (channel, reference).

        Repeating the same artifact must be idempotent. A failure or an
        uncertain result must raise; do not claim success from a queued request.
        No timestamp is accepted from the sink or an old file's mtime.
        """
        ...


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ShadowIntegrityError(code)


def _day(value: date) -> date:
    _require(type(value) is date, "CAUSAL_SESSION_INVALID")
    return value


def _clock(connection) -> datetime:
    row = connection.execute("SELECT clock_timestamp()").fetchone()
    _require(row is not None, "CAUSAL_DATABASE_CLOCK_UNAVAILABLE")
    return utc(row[0])


def _transaction(connection) -> None:
    _require(connection is not None, "PERSISTENT_DATABASE_REQUIRED")
    _require(getattr(connection, "autocommit", None) is False, "CAUSAL_TRANSACTION_REQUIRED")


def _authority(connection) -> None:
    """Check effective privileges every connection; never provision a role here.

    This is an append-only ACL check, not proof that a stolen INSERT credential
    cannot fabricate a new receipt. The audited emitter/DB operator remain part
    of the timestamp authority. A separately audited deployment is still needed.
    """
    _transaction(connection)
    identity = connection.execute("""SELECT current_user = session_user,
        NOT (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls),
        NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid),
        NOT has_database_privilege(current_user,current_database(),'CREATE'),
        NOT has_database_privilege(current_user,current_database(),'TEMP')
        FROM pg_catalog.pg_roles r WHERE rolname=current_user""").fetchone()
    _require(identity is not None and all(value is True for value in identity), "CAUSAL_ROLE_NOT_RESTRICTED")
    rows = connection.execute("""SELECT c.relname,
        has_table_privilege(current_user,c.oid,'SELECT'),
        has_table_privilege(current_user,c.oid,'INSERT'),
        NOT has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'),
        NOT has_any_column_privilege(current_user,c.oid,'UPDATE'),
        NOT pg_has_role(current_user,c.relowner,'MEMBER'),
        NOT has_schema_privilege(current_user,n.oid,'CREATE'),
        NOT c.relrowsecurity
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind='r' AND c.relname = ANY(%s)""",
        (["audit_events", "r2d2_v2_causal_artifacts", "r2d2_v2_causal_publications", "r2d2_v2_causal_confirmations"],)).fetchall()
    _require(len(rows) == 4 and all(all(value is True for value in row[1:]) for row in rows),
             "CAUSAL_TABLE_AUTHORITY_INVALID")


def _binding(commitment: dict) -> dict:
    return {**{key: commitment[key] for key in
               ("epoch", "session", "manifest_sha", "amendment_sha", "list_sha256", "n_cut")},
            "commitment_sha256": digest(commitment)}


def _public(commitment: dict, audit: dict) -> dict:
    return {"schema": "V2_CAUSAL_LIST_PUBLICATION_V1", **_binding(commitment),
            "build_audit_event_id": audit["event_id"], "built_at": commitment["built_at"],
            "registry_sha256": commitment["registry_sha256"],
            "daily_contract_sha256": commitment["daily_contract_sha256"],
            "counts": commitment["counts"], "coverage": commitment["coverage"]}


def _event(connection, event_id: str) -> dict:
    row = connection.execute("SELECT action,occurred_at,detail FROM public.audit_events WHERE id=%s", (event_id,)).fetchone()
    _require(row is not None, "CAUSAL_AUDIT_EVENT_MISSING")
    return {"event_id": str(event_id), "event_type": row[0],
            "occurred_at": utc(row[1]).isoformat(), "payload": row[2]}


def _insert_event(connection, *, action: str, at: datetime, epoch: str, day: date, payload: dict) -> dict:
    event_id = str(uuid4())
    connection.execute("""INSERT INTO public.audit_events
        (id,actor,action,subject_type,subject_id,detail,occurred_at)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)""",
        (event_id, "C3PO_V2_CAUSAL_EMITTER", action, "r2d2_v2_causal_list",
         epoch + ":" + day.isoformat(), canonical(payload).decode(), at))
    return {"event_id": event_id, "event_type": action, "occurred_at": at.isoformat(), "payload": payload}


class PostgresCausalListEmitter:
    def __init__(self, connection_factory: Callable, calendar: Calendar, *, enabled: bool = False):
        _require(type(enabled) is bool, "CAUSAL_ENABLED_INVALID")
        self.connection_factory, self.calendar, self.enabled = connection_factory, calendar, enabled

    def _check(self, epoch: str, day: date) -> None:
        _require(self.enabled, "CAUSAL_EMITTER_OFF")
        validate_epoch(epoch)
        _day(day)

    @staticmethod
    def _lock(connection, epoch: str, day: date) -> None:
        _authority(connection)
        # Every build and publication for this slot takes the same transaction lock.
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                           ("V2_CAUSAL:" + epoch + ":" + day.isoformat(),))

    def _confirm(self, receipt: dict, deadline: datetime | None = None) -> dict:
        """Witness the previous transaction after commit; never infer from mtime.

        An uncertain commit is recovered by reading the event, not reinserting
        or relabeling it. A build without a timely post-commit observation cannot be
        recovered after the D-1 deadline as if it had been acknowledged earlier.
        confirmed_at is the observation time, not its own transaction's commit.
        """
        with self.connection_factory() as connection:
            _authority(connection)
            stored = _event(connection, receipt["event_id"])
            _require(canonical(stored) == canonical(receipt), "CAUSAL_AUDIT_EVENT_CONFLICT")
            prior = connection.execute("SELECT event_sha,confirmed_at FROM public.r2d2_v2_causal_confirmations WHERE event_id=%s",
                                       (receipt["event_id"],)).fetchone()
            if prior is not None:
                _require(prior[0] == digest(receipt), "CAUSAL_CONFIRMATION_CONFLICT")
                confirmed = utc(prior[1])
            else:
                confirmed = _clock(connection)
                _require(utc(receipt["occurred_at"]) <= confirmed, "CAUSAL_DATABASE_CLOCK_REVERSED")
                _require(deadline is None or confirmed < deadline, "CAUSAL_COMMIT_NOT_CONFIRMED_BEFORE_CUTOFF")
                connection.execute("""INSERT INTO public.r2d2_v2_causal_confirmations(event_id,event_sha,confirmed_at)
                    VALUES (%s,%s,%s) ON CONFLICT(event_id) DO NOTHING""", (receipt["event_id"], digest(receipt), confirmed))
                # A concurrent witness may win; use its actual immutable record.
                prior = connection.execute("SELECT event_sha,confirmed_at FROM public.r2d2_v2_causal_confirmations WHERE event_id=%s",
                                           (receipt["event_id"],)).fetchone()
                _require(prior is not None and prior[0] == digest(receipt), "CAUSAL_CONFIRMATION_CONFLICT")
                if prior is None:
                    raise ShadowIntegrityError("CAUSAL_CONFIRMATION_CONFLICT")
                confirmed = utc(prior[1])
            _require(utc(receipt["occurred_at"]) <= confirmed, "CAUSAL_DATABASE_CLOCK_REVERSED")
            _require(deadline is None or confirmed < deadline, "CAUSAL_COMMIT_NOT_CONFIRMED_BEFORE_CUTOFF")
            connection.commit()
        return receipt

    def build(self, *, epoch: str, day: date, registry_bytes: bytes, daily_bytes: bytes) -> dict:
        self._check(epoch, day)
        _require(isinstance(registry_bytes, bytes) and isinstance(daily_bytes, bytes), "CAUSAL_INPUT_BYTES_REQUIRED")
        _require(0 < len(registry_bytes) <= MAX_INPUT_BYTES and 0 < len(daily_bytes) <= MAX_INPUT_BYTES,
                 "CAUSAL_INPUT_SIZE_LIMIT")
        with self.connection_factory() as connection:
            self._lock(connection, epoch, day)
            previous = connection.execute("""SELECT commitment,commitment_sha,build_event_id
                FROM public.r2d2_v2_causal_artifacts WHERE epoch=%s AND session=%s""", (epoch, day)).fetchone()
            if previous is not None:
                commitment, expected_sha, event_id = previous
                _require(digest(commitment) == expected_sha, "CAUSAL_STORED_COMMITMENT_HASH_MISMATCH")
                _require(commitment["registry_sha256"] == hashlib.sha256(registry_bytes).hexdigest()
                         and commitment["daily_contract_sha256"] == hashlib.sha256(daily_bytes).hexdigest(),
                         "CAUSAL_SLOT_INPUT_CONFLICT")
                _require(commitment == build_commitment(epoch=epoch, day=day, built_at=utc(commitment["built_at"]),
                    registry_bytes=registry_bytes, daily_bytes=daily_bytes, calendar=self.calendar), "CAUSAL_COMMITMENT_MISMATCH")
                receipt = _event(connection, str(event_id))
                _require(receipt["event_type"] == BUILT and receipt["payload"] == _binding(commitment)
                         and utc(receipt["occurred_at"]) == utc(commitment["built_at"]), "CAUSAL_BUILD_RECEIPT_CONFLICT")
            else:
                started = _clock(connection)
                commitment = build_commitment(epoch=epoch, day=day, built_at=started,
                    registry_bytes=registry_bytes, daily_bytes=daily_bytes, calendar=self.calendar)
                finished = _clock(connection)
                _require(started <= finished < utc(commitment["cutoff_at"]), "CAUSAL_BUILD_CROSSED_CUTOFF")
                # Selection/validation has finished. Record the factual database
                # observation after that work, then seal/store its bytes.
                commitment["built_at"] = finished.isoformat()
                _require(commitment == build_commitment(epoch=epoch, day=day, built_at=finished,
                    registry_bytes=registry_bytes, daily_bytes=daily_bytes, calendar=self.calendar),
                    "CAUSAL_INPUT_NOT_STABLE_DURING_BUILD")
                _require(finished <= _clock(connection) < utc(commitment["cutoff_at"]),
                         "CAUSAL_BUILD_CROSSED_CUTOFF")
                receipt = _insert_event(connection, action=BUILT, at=finished, epoch=epoch, day=day, payload=_binding(commitment))
                connection.execute("""INSERT INTO public.r2d2_v2_causal_artifacts
                    (epoch,session,commitment,commitment_sha,build_event_id) VALUES (%s,%s,%s::jsonb,%s,%s)""",
                    (epoch, day, canonical(commitment).decode(), digest(commitment), receipt["event_id"]))
            connection.commit()
        self._confirm(receipt, utc(commitment["cutoff_at"]))
        return {"commitment": commitment, "audit_receipt": receipt}

    def publish(self, *, epoch: str, day: date, sink: PublicationSink) -> dict:
        self._check(epoch, day)
        # Confirm build visibility before calling the external publication sink.
        with self.connection_factory() as connection:
            _authority(connection)
            stored = connection.execute("""SELECT commitment,commitment_sha,build_event_id
                FROM public.r2d2_v2_causal_artifacts WHERE epoch=%s AND session=%s""", (epoch, day)).fetchone()
            _require(stored is not None, "CAUSAL_BUILD_REQUIRED")
            commitment, expected_sha, build_id = stored
            _require(digest(commitment) == expected_sha, "CAUSAL_STORED_COMMITMENT_HASH_MISMATCH")
            _require(commitment == build_commitment(epoch=epoch, day=day, built_at=utc(commitment["built_at"]),
                registry_bytes=_decode(commitment["registry_raw_base64"]), daily_bytes=_decode(commitment["daily_raw_base64"]),
                calendar=self.calendar), "CAUSAL_COMMITMENT_MISMATCH")
            audit = _event(connection, str(build_id))
            _require(audit["event_type"] == BUILT and audit["payload"] == _binding(commitment)
                     and utc(audit["occurred_at"]) == utc(commitment["built_at"]), "CAUSAL_BUILD_RECEIPT_CONFLICT")
        self._confirm(audit, utc(commitment["cutoff_at"]))
        with self.connection_factory() as connection:
            self._lock(connection, epoch, day)
            previous = connection.execute("SELECT publication_event_id FROM public.r2d2_v2_causal_publications WHERE build_event_id=%s",
                                          (build_id,)).fetchone()
            if previous is not None:
                publication = _event(connection, str(previous[0]))
                self._publication_binding(commitment, audit, publication)
            else:
                before = _clock(connection)
                _require(utc(commitment["built_at"]) <= before < utc(commitment["decision_at"]), "CAUSAL_PUBLICATION_LATE")
                channel, reference = sink(deepcopy(_public(commitment, audit)))
                _require(channel in ("relay", "github_issue_348") and isinstance(reference, str)
                         and 0 < len(reference) <= 512, "CAUSAL_PUBLICATION_REFERENCE_INVALID")
                # This is when publication was observed durable, not an invented
                # prior publication timestamp. A slow sink crossing 10:00 fails.
                observed = _clock(connection)
                _require(before <= observed < utc(commitment["decision_at"]), "CAUSAL_PUBLICATION_LATE")
                payload = {**_binding(commitment), "build_audit_event_id": audit["event_id"],
                           "channel": channel, "publication_reference": reference, "published_at": observed.isoformat()}
                publication = _insert_event(connection, action=PUBLISHED, at=observed, epoch=epoch, day=day, payload=payload)
                connection.execute("INSERT INTO public.r2d2_v2_causal_publications(build_event_id,publication_event_id) VALUES (%s,%s)",
                                   (build_id, publication["event_id"]))
            connection.commit()
        self._confirm(publication)
        envelope = {"commitment": commitment, "audit_receipt": audit, "publication_receipt": publication}
        # Independent reads observe committed events AND their confirmations;
        # recovery revalidates exact raw bytes/selection, not a saved status bit.
        with self.connection_factory() as connection:
            _authority(connection)
            now = _clock(connection)
        validate_commitment(envelope, epoch=epoch, day=day, now=now, calendar=self.calendar,
            receipt_verifier=ConfirmedCausalReceiptVerifier(self.connection_factory))
        return envelope

    @staticmethod
    def _publication_binding(commitment: dict, audit: dict, publication: dict) -> None:
        payload = publication.get("payload")
        if not isinstance(payload, dict):
            raise ShadowIntegrityError("CAUSAL_PUBLICATION_RECEIPT_CONFLICT")
        _require(publication["event_type"] == PUBLISHED
                 and publication["event_id"] != audit["event_id"]
                 and payload == {**_binding(commitment), "build_audit_event_id": audit["event_id"],
                     **{key: payload.get(key) for key in ("channel", "publication_reference", "published_at")}},
                 "CAUSAL_PUBLICATION_RECEIPT_CONFLICT")
        _require(payload["channel"] in ("relay", "github_issue_348")
                 and isinstance(payload["publication_reference"], str)
                 and 0 < len(payload["publication_reference"]) <= 512, "CAUSAL_PUBLICATION_REFERENCE_INVALID")
        _require(utc(commitment["built_at"]) <= utc(payload["published_at"])
                 == utc(publication["occurred_at"]) < utc(commitment["decision_at"]),
                 "CAUSAL_PUBLICATION_LATE")


class ConfirmedCausalReceiptVerifier:
    """Read actual committed rows and post-commit observations, fail closed.

    Use a separate SELECT-only connection; the emitter role may also read.
    This verifier is opt-in; it does not change the existing collector wiring.
    """
    def __init__(self, connection_factory: Callable):
        self.connection_factory = connection_factory

    def __call__(self, receipt: dict, expected: dict) -> bool:
        try:
            with self.connection_factory() as connection:
                _transaction(connection)
                actual = _event(connection, receipt["event_id"])
                if actual != receipt or {key: actual[key] for key in expected} != expected:
                    return False
                row = connection.execute("""SELECT event_sha,confirmed_at
                    FROM public.r2d2_v2_causal_confirmations WHERE event_id=%s""", (receipt["event_id"],)).fetchone()
                if row is None or row[0] != digest(actual):
                    return False
                observed = utc(row[1])
                if not utc(actual["occurred_at"]) <= observed <= _clock(connection):
                    return False
                if actual["event_type"] == BUILT:
                    from datetime import time
                    from .r2d2_v2_sources import NY
                    cutoff = datetime.combine(date.fromisoformat(actual["payload"]["session"]), time(), NY)
                    return observed < cutoff
                return actual["event_type"] == PUBLISHED
        except Exception:
            return False
