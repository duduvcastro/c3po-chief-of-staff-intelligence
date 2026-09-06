"""Offline authority, recovery and receipt-binding counterexamples.

The independent PostgreSQL lab exercises actual transactions and restart;
these focused stubs probe invalid boundaries without a database fallback.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.r2d2_v2_causal_emitter import (PostgresCausalListEmitter, _authority,
    _transaction, _public, _binding, BUILT, PUBLISHED)
from app.r2d2_v2_causal_list import MAX_INPUT_BYTES
from app.r2d2_v2_store import ShadowIntegrityError

EPOCH, DAY = "R2D2-V2-DIAG-EMITTER", date(2026, 9, 8)


class Authority:
    autocommit = False

    def __init__(self, identity=None, tables=None):
        self.identity = identity if identity is not None else (True,) * 5
        self.tables = tables if tables is not None else [(str(i), *(True,) * 7) for i in range(4)]
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append(query)
        return SimpleNamespace(fetchone=lambda: self.identity, fetchall=lambda: self.tables)


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


def test_off_and_invalid_input_fail_before_connection():
    def factory():
        raise AssertionError("connection forbidden")
    emitter = PostgresCausalListEmitter(factory, None)
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_EMITTER_OFF"):
        emitter.build(epoch=EPOCH, day=DAY, registry_bytes=b"{}", daily_bytes=b"{}")
    emitter.enabled = True
    with pytest.raises(ShadowIntegrityError, match="CAUSAL_INPUT_SIZE_LIMIT"):
        emitter.build(epoch=EPOCH, day=DAY, registry_bytes=b"x" * (MAX_INPUT_BYTES + 1), daily_bytes=b"{}")


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
