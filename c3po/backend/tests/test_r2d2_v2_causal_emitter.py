"""Offline authority, recovery and receipt-binding counterexamples.

The independent PostgreSQL lab exercises actual transactions and restart;
these focused stubs probe invalid boundaries without a database fallback.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace
from pathlib import Path

import pytest

from app import r2d2_v2_causal_emitter as module
from app import r2d2_v2_causal_list as causal_list
from app.r2d2_v2_causal_emitter import (PostgresCausalListEmitter, _authority,
    _transaction, _public, _binding, _IMMUTABLE_TRIGGERS, _APPEND_ONLY_BODY, BUILT, PUBLISHED)
from app.r2d2_v2_causal_list import MAX_INPUT_BYTES
from app.r2d2_v2_sources import SourceUnavailable
from app.r2d2_v2_store import ShadowIntegrityError

EPOCH, DAY = "R2D2-V2-DIAG-EMITTER", date(2026, 9, 8)


class Authority:
    autocommit = False

    def __init__(self, identity=None, tables=None, triggers=None):
        self.identity = identity if identity is not None else (True,) * 5
        self.tables = tables if tables is not None else [(str(i), *(True,) * 7) for i in range(4)]
        self.triggers = triggers if triggers is not None else [
            (table, trigger, True, True, True, True, _APPEND_ONLY_BODY, True)
            for table, trigger in _IMMUTABLE_TRIGGERS.items()]
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append(query)
        rows = self.triggers if "FROM pg_catalog.pg_trigger" in query else self.tables
        return SimpleNamespace(fetchone=lambda: self.identity, fetchall=lambda: rows)


@pytest.mark.parametrize("autocommit", [True, None, 0, 1, "false"])
def test_transaction_must_be_explicit_before_any_query(autocommit):
    db = Authority()
    db.autocommit = autocommit
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_TRANSACTION_REQUIRED"):
        PostgresCausalListEmitter._lock(db, EPOCH, DAY)
    assert not db.calls


def test_no_database_is_not_a_memory_fallback():
    with pytest.raises(ShadowIntegrityError, match="PERSISTENT_DATABASE_REQUIRED"):
        _transaction(None)


@pytest.mark.parametrize("index", range(5))
def test_privileged_or_delegated_role_rejected(index):
    identity = [True] * 5
    identity[index] = False
    db = Authority(identity=tuple(identity))
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_ROLE_NOT_RESTRICTED"):
        _authority(db)
    assert len(db.calls) == 1


@pytest.mark.parametrize("index", range(1, 8))
def test_missing_or_excess_table_authority_rejected(index):
    db = Authority()
    row = list(db.tables[2])
    row[index] = False
    db.tables[2] = tuple(row)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_TABLE_AUTHORITY_INVALID"):
        _authority(db)


def test_absent_migration_table_rejected():
    db = Authority(tables=[("one", *(True,) * 7)])
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_TABLE_AUTHORITY_INVALID"):
        _authority(db)


def test_append_only_body_is_exact_unchanged_manual_migration():
    migration = Path(__file__).resolve().parents[2] / "db/manual/046_r2d2_v2_causal_emission.sql"
    text = migration.read_text()
    assert text.split("LANGUAGE plpgsql AS $$", 1)[1].split("$$;", 1)[0] == _APPEND_ONLY_BODY


def test_all_four_enabled_exact_triggers_allow_authority():
    db = Authority()
    _authority(db)
    assert len(db.calls) == 3


@pytest.mark.parametrize("index", range(4))
def test_each_missing_append_only_trigger_blocks_before_lock(index):
    db = Authority()
    del db.triggers[index]
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_APPEND_ONLY_TRIGGERS_INVALID"):
        PostgresCausalListEmitter._lock(db, EPOCH, DAY)
    assert not any("pg_advisory_xact_lock" in query for query in db.calls)


@pytest.mark.parametrize("index", range(4))
def test_each_disabled_trigger_blocks_authority(index):
    db = Authority()
    changed = list(db.triggers[index])
    changed[2] = False
    db.triggers[index] = tuple(changed)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_APPEND_ONLY_TRIGGERS_INVALID"):
        _authority(db)


@pytest.mark.parametrize("column,value", [
    (0, "wrong_table"), (1, "wrong_trigger"),
    (3, False),  # UPDATE/DELETE, BEFORE ROW, arguments, WHEN or column predicate changed.
    (4, False),  # A different schema/function with the same body is not SQL046.
    (5, False),  # Different language/signature/security settings.
    (6, "\nBEGIN RETURN NEW; END;\n"),  # Original name with a no-op definition.
    (7, False),  # Session would not run ordinary origin triggers.
])
def test_changed_trigger_or_function_definition_blocks_authority(column, value):
    db = Authority()
    changed = list(db.triggers[0])
    changed[column] = value
    db.triggers[0] = tuple(changed)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_APPEND_ONLY_TRIGGERS_INVALID"):
        _authority(db)


def test_duplicate_trigger_metadata_cannot_replace_missing_table():
    db = Authority()
    db.triggers[0] = db.triggers[1]
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_APPEND_ONLY_TRIGGERS_INVALID"):
        _authority(db)


def test_off_and_invalid_input_fail_before_connection():
    def factory():
        raise AssertionError("connection forbidden")
    emitter = PostgresCausalListEmitter(factory, None)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_EMITTER_OFF"):
        emitter.build(epoch=EPOCH, day=DAY, registry_bytes=b"{}", daily_bytes=b"{}")
    emitter.enabled = True
    with pytest.raises(SourceUnavailable, match="CAUSAL_INPUT_SIZE_LIMIT"):
        emitter.build(epoch=EPOCH, day=DAY, registry_bytes=b"x" * (MAX_INPUT_BYTES + 1), daily_bytes=b"{}")


def test_combined_base64_and_receipt_reserve_checked_before_connection(monkeypatch):
    monkeypatch.setattr(causal_list, "MAX_CAUSAL_ENVELOPE_BYTES", 32 * 1024)
    raw = b"x" * (8 * 1024)  # Both raw inputs individually fit; their encoded sum does not.
    assert len(raw) < MAX_INPUT_BYTES
    def forbidden():
        pytest.fail("oversized combined envelope must not open the database")
    emitter = PostgresCausalListEmitter(forbidden, None, enabled=True)
    with pytest.raises(SourceUnavailable, match="CAUSAL_ENVELOPE_SIZE_LIMIT"):
        emitter.build(epoch=EPOCH, day=DAY, registry_bytes=raw, daily_bytes=raw)


def receipt_fixture():
    commitment = {"epoch": EPOCH, "session": DAY.isoformat(), "manifest_sha": "a" * 64,
        "amendment_sha": "b" * 64, "list_sha256": "c" * 64, "n_cut": 550,
        "built_at": "2026-09-06T22:00:00+00:00", "decision_at": "2026-09-08T14:00:00+00:00",
        "registry_sha256": "d" * 64, "daily_contract_sha256": "e" * 64,
        "counts": {"selected": 1}, "coverage": {"ratio": 1.0},
        "list": ["PRIVATE_SYMBOL"], "registry_raw_base64": "PRIVATE_RAW"}
    audit = {"event_id": "a", "event_type": BUILT, "occurred_at": commitment["built_at"], "payload": _binding(commitment)}
    publication = {"event_id": "p", "event_type": PUBLISHED, "occurred_at": "2026-09-07T12:00:00+00:00",
        "payload": {**_binding(commitment), "build_audit_event_id": "a", "channel": "relay",
            "publication_reference": "synthetic/receipt.json", "published_at": "2026-09-07T12:00:00+00:00"}}
    return commitment, audit, publication


def test_publication_binding_accepts_exact_receipt():
    PostgresCausalListEmitter._publication_binding(*receipt_fixture())


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(event_id="a"),
    lambda p: p.update(event_type=BUILT),
    lambda p: p["payload"].update(build_audit_event_id="foreign"),
    lambda p: p["payload"].update(commitment_sha256="f" * 64),
    lambda p: p["payload"].update(session="2026-09-09"),
    lambda p: p["payload"].update(extra="not allowed"),
    lambda p: p["payload"].update(channel="queued"),
    lambda p: p["payload"].update(publication_reference=""),
    lambda p: p["payload"].update(published_at="2026-09-07T12:00:01+00:00"),
    lambda p: (p.update(occurred_at="2026-09-08T14:00:00+00:00"), p["payload"].update(published_at="2026-09-08T14:00:00+00:00")),
])
def test_recovery_cannot_reuse_foreign_or_late_publication(mutation):
    commitment, audit, publication = receipt_fixture()
    mutation(publication)
    with pytest.raises(ShadowIntegrityError):
        PostgresCausalListEmitter._publication_binding(commitment, audit, publication)


def test_public_artifact_excludes_private_raw_and_symbols():
    commitment, audit, _ = receipt_fixture()
    public = _public(commitment, audit)
    assert "list" not in public and "registry_raw_base64" not in public
    assert "PRIVATE" not in str(public)


def test_build_witness_after_cutoff_is_not_relabelled():
    commitment, audit, _ = receipt_fixture()
    db = Authority()
    db.__class__.__enter__ = lambda self: self
    db.__class__.__exit__ = lambda *args: None
    db.commit = lambda: pytest.fail("late witness must not commit")
    prior = (None, datetime(2026, 9, 8, 4, tzinfo=timezone.utc))
    original = db.execute

    def execute(query, params=None):
        if "SELECT action,occurred_at,detail" in query:
            return SimpleNamespace(fetchone=lambda: (audit["event_type"], audit["occurred_at"], audit["payload"]))
        if "SELECT event_sha,confirmed_at" in query:
            return SimpleNamespace(fetchone=lambda: None)
        if "SELECT clock_timestamp()" in query:
            return SimpleNamespace(fetchone=lambda: (prior[1],))
        if query.lstrip().startswith("INSERT"):
            pytest.fail("late observation must not be inserted")
        return original(query, params)
    db.execute = execute
    emitter = PostgresCausalListEmitter(lambda: db, None, enabled=True)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_COMMIT_NOT_CONFIRMED_BEFORE_CUTOFF"):
        emitter._confirm(deepcopy(audit), prior[1])


@pytest.mark.parametrize("readback", [None, ("wrong_hash", "2026-09-07T12:00:00+00:00")])
def test_confirmation_insert_readback_missing_or_conflicting_does_not_commit(readback):
    _, audit, _ = receipt_fixture()
    class Connection(Authority):
        reads = 0
        inserts = 0
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def commit(self):
            pytest.fail("unconfirmed witness must not commit")
        def execute(self, query, params=None):
            if "SELECT action,occurred_at,detail" in query:
                return SimpleNamespace(fetchone=lambda: (audit["event_type"], audit["occurred_at"], audit["payload"]))
            if "SELECT event_sha,confirmed_at" in query:
                self.reads += 1
                return SimpleNamespace(fetchone=lambda: None if self.reads == 1 else readback)
            if "SELECT clock_timestamp()" in query:
                return SimpleNamespace(fetchone=lambda: ("2026-09-07T12:00:00+00:00",))
            if query.lstrip().startswith("INSERT"):
                self.inserts += 1
                return None
            return super().execute(query, params)
    db = Connection()
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_CONFIRMATION_CONFLICT"):
        PostgresCausalListEmitter(lambda: db, None, enabled=True)._confirm(audit)
    assert db.reads == 2 and db.inserts == 1


def test_complete_recovered_envelope_checked_before_validator_or_return(monkeypatch):
    commitment, audit, publication = receipt_fixture()
    # Simulate a stored/recovered envelope whose receipts exceed the final cap.
    commitment["cutoff_at"] = "2026-09-08T04:00:00+00:00"
    monkeypatch.setattr(causal_list, "MAX_CAUSAL_ENVELOPE_BYTES", 100)
    monkeypatch.setattr(module, "build_commitment", lambda **_: deepcopy(commitment))
    monkeypatch.setattr(module, "_decode", lambda _: b"{}")
    monkeypatch.setattr(module, "_event", lambda _, identity: audit if identity == "a" else publication)
    monkeypatch.setattr(PostgresCausalListEmitter, "_confirm", lambda *_: None)
    monkeypatch.setattr(module, "validate_commitment", lambda *_, **__: pytest.fail("size guard must run first"))
    commitment["daily_raw_base64"] = "PRIVATE_RAW"
    audit["payload"] = _binding(commitment)
    publication["payload"].update(_binding(commitment))
    class Connection(Authority):
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def commit(self):
            pass
        def execute(self, query, params=None):
            if "SELECT commitment,commitment_sha,build_event_id" in query:
                return SimpleNamespace(fetchone=lambda: (commitment, causal_list.digest(commitment), "a"))
            if "SELECT publication_event_id" in query:
                return SimpleNamespace(fetchone=lambda: ("p",))
            return super().execute(query, params)
    emitter = PostgresCausalListEmitter(Connection, None, enabled=True)
    with pytest.raises(SourceUnavailable, match="CAUSAL_ENVELOPE_SIZE_LIMIT"):
        emitter.publish(epoch=EPOCH, day=DAY, sink=lambda _: pytest.fail("recovery must not call the sink"))
