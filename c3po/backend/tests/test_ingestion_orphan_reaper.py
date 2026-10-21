"""The startup reaper of ingestion runs orphaned by a restart (app/ingestion_process.py).

Runs on the in-memory double and, when C3PO_PROVIDER_HEALTH_TEST_DSN names a disposable local PostgreSQL (a socket
under /tmp — the backend-postgres.yml job), on connection-local TEMP tables with the production columns. No schema is
initialized and no production credential is read.
"""
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app import ingestion_process
from app.config import Settings
from app.database import Database
from app.ingestion_process import (
    IR_WORKER,
    ORPHAN_ERROR_SUMMARY,
    VALUATION_WORKER,
    ProcessIdentity,
    WorkerOwnership,
    reap_orphans,
)

APP = Path(__file__).resolve().parents[1] / "app"
MARKER_KEYS = ("process_instance", "process_pid", "process_started_at", "process_host", "process_role")


@pytest.fixture(autouse=True)
def _fresh_process_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    # the identity and the claimed role are process-wide: every test starts from an unclaimed process
    monkeypatch.setattr(ingestion_process, "_identity", None)
    monkeypatch.setattr(ingestion_process, "_role", None)


@pytest.fixture(params=["memory", "postgres"])
def database(request):
    db = Database(Settings(database_url=""))
    if request.param == "memory":
        yield db
        return
    dsn = os.environ.get("C3PO_PROVIDER_HEALTH_TEST_DSN")
    if not dsn:
        pytest.skip("disposable local PostgreSQL not configured")
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    assert str(info.get("host", "")).startswith("/tmp/"), "local test socket required"
    with psycopg.connect(dsn, client_encoding="utf8") as connection:
        connection.execute("""CREATE TEMP TABLE data_sources (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL,
            source_type text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())""")
        connection.execute("""CREATE TEMP TABLE ingestion_runs (
            id uuid PRIMARY KEY, source_id uuid REFERENCES data_sources(id),
            status text NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
            started_at timestamptz NOT NULL, completed_at timestamptz,
            records_read integer NOT NULL DEFAULT 0, records_written integer NOT NULL DEFAULT 0,
            error_summary text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb)""")
        connection.commit()
        db.database_url = dsn

        @contextmanager
        def local_connection():
            yield connection

        db.connection = local_connection  # type: ignore[method-assign]
        yield db


def _identity(name: str, started_at: datetime) -> ProcessIdentity:
    return ProcessIdentity(instance=f"instance-{name}", pid=4242, started_at=started_at, host="container")


def _run(db: Database, code: str, source_type: str, *, started_at: datetime, marker: dict[str, Any] | None,
         status: str = "running") -> str:
    """A run as a given process wrote it: ``marker`` None = an unmarked (legacy) row."""
    run_id = db.begin_ingestion_run(code, code.upper(), source_type, {"operation": "test"})
    metadata = {"operation": "test", **(marker or {})}
    if not db.database_url:
        db._ingestion_runs[run_id].update(started_at=started_at, metadata=metadata, status=status)
        return run_id
    with db.connection() as connection:
        connection.execute("UPDATE ingestion_runs SET started_at = %s, metadata = %s::jsonb, status = %s WHERE id = %s",
                           (started_at, json.dumps(metadata), status, run_id))
        connection.commit()
    return run_id


def _marker(identity: ProcessIdentity, role: str | None) -> dict[str, Any]:
    marker: dict[str, Any] = {"process_instance": identity.instance, "process_pid": identity.pid,
                              "process_started_at": identity.started_at.isoformat(), "process_host": identity.host}
    if role is not None:
        marker["process_role"] = role
    return marker


def _state(db: Database, run_id: str) -> dict[str, Any]:
    if not db.database_url:
        run = db._ingestion_runs[run_id]
        return {"status": run["status"], "error_summary": run.get("error_summary"), "completed_at": run.get("completed_at"),
                "metadata": run["metadata"]}
    with db.connection() as connection:
        row = connection.execute("SELECT status, error_summary, completed_at, metadata FROM ingestion_runs WHERE id = %s",
                                 (run_id,)).fetchone()
    assert row is not None
    return {"status": row[0], "error_summary": row[1], "completed_at": row[2], "metadata": row[3]}


def _assert_reaped(db: Database, run_id: str, *, by: str, at: datetime) -> None:
    state = _state(db, run_id)
    assert state["status"] == "failed" and state["error_summary"] == ORPHAN_ERROR_SUMMARY
    assert state["completed_at"] == at
    assert state["metadata"]["reaped_at"] == at.isoformat() and state["metadata"]["reaped_by"] == by
    assert state["metadata"]["operation"] == "test"  # the run's own metadata survives


def _assert_untouched(db: Database, run_id: str, status: str = "running") -> None:
    state = _state(db, run_id)
    assert state["status"] == status and state["error_summary"] is None and state["completed_at"] is None
    assert "reaped_at" not in state["metadata"] and "reaped_by" not in state["metadata"]


T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_every_new_run_carries_the_process_marker(database: Database) -> None:
    unclaimed = database.begin_ingestion_run("cvm", "CVM", "regulatory_disclosure", {"operation": "ipe"})
    metadata = _state(database, unclaimed)["metadata"]
    identity = ingestion_process.current()
    assert metadata["operation"] == "ipe" and metadata["process_instance"] == identity.instance
    assert metadata["process_pid"] == os.getpid() and metadata["process_started_at"] == identity.started_at.isoformat()
    assert "process_role" not in metadata  # the API / a one-off CLI: no worker role, never reaped by role
    ingestion_process.claim_worker_role("valuation_worker")
    claimed = database.begin_ingestion_run("valuation-worker-canonical", "Canonical", "valuation_worker", {})
    assert _state(database, claimed)["metadata"]["process_role"] == "valuation_worker"
    assert _state(database, claimed)["metadata"]["process_instance"] == identity.instance


def test_a_run_of_a_previous_process_of_the_same_worker_is_reaped(database: Database) -> None:
    previous = _identity("previous", T0)
    orphan = _run(database, "valuation-worker-v2-data", "valuation_worker", started_at=T0 + timedelta(minutes=5),
                  marker=_marker(previous, "valuation_worker"))
    # an IR source polled INSIDE the previous valuation worker's nightly: marked with its role, reaped with it
    nightly_ir = _run(database, "sec", "regulatory_disclosure", started_at=T0 + timedelta(minutes=6),
                      marker=_marker(previous, "valuation_worker"))
    finished = _run(database, "valuation-worker-chewie", "valuation_worker", started_at=T0 + timedelta(minutes=1),
                    marker=_marker(previous, "valuation_worker"), status="succeeded")
    now = _identity("now", T0 + timedelta(hours=1))
    at = T0 + timedelta(hours=1, seconds=3)
    assert sorted(reap_orphans(database, VALUATION_WORKER, identity=now, now=at)) == sorted([orphan, nightly_ir])
    _assert_reaped(database, orphan, by="valuation_worker:instance-now", at=at)
    _assert_reaped(database, nightly_ir, by="valuation_worker:instance-now", at=at)
    _assert_untouched(database, finished, status="succeeded")


def test_other_workers_runs_and_roleless_runs_are_untouched(database: Database) -> None:
    previous = _identity("previous", T0)
    ir_run = _run(database, "sec", "regulatory_disclosure", started_at=T0, marker=_marker(previous, "investor_relations_worker"))
    api_run = _run(database, "eodhd", "market_data", started_at=T0, marker=_marker(previous, None))
    r2d2_legacy = _run(database, "b3", "market_data", started_at=T0, marker=None)
    shared_legacy = _run(database, "cvm", "regulatory_disclosure", started_at=T0, marker=None)  # IR source shared by both workers
    now = _identity("now", T0 + timedelta(hours=1))
    assert reap_orphans(database, VALUATION_WORKER, identity=now, now=T0 + timedelta(hours=1)) == []
    for run_id in (ir_run, api_run, r2d2_legacy, shared_legacy):
        _assert_untouched(database, run_id)
    assert reap_orphans(database, IR_WORKER, identity=now, now=T0 + timedelta(hours=1)) == [ir_run]
    for run_id in (api_run, r2d2_legacy, shared_legacy):
        _assert_untouched(database, run_id)


def test_a_run_of_the_current_process_is_untouched(database: Database) -> None:
    now = _identity("now", T0)
    own = _run(database, "valuation-worker-canonical", "valuation_worker", started_at=T0 - timedelta(seconds=1),
               marker=_marker(now, "valuation_worker"))  # even with a clock that put it before the start instant
    assert reap_orphans(database, VALUATION_WORKER, identity=now, now=T0 + timedelta(minutes=1)) == []
    _assert_untouched(database, own)


def test_a_legacy_row_is_reaped_only_when_older_than_the_process_and_of_an_owned_source(database: Database) -> None:
    start = T0 + timedelta(hours=2)
    older = _run(database, "valuation-worker-v3-shadow", "valuation_worker", started_at=start - timedelta(hours=1), marker=None)
    newer = _run(database, "valuation-worker-shadow", "valuation_worker", started_at=start + timedelta(seconds=1), marker=None)
    marked_after = _run(database, "valuation-worker-peer-quality", "valuation_worker", started_at=start + timedelta(seconds=2),
                        marker=_marker(_identity("other", start), "valuation_worker"))
    asfiled = _run(database, "sec_asfiled", "regulatory_disclosure", started_at=start - timedelta(hours=1), marker=None)
    now = _identity("now", start)
    at = start + timedelta(minutes=1)
    assert reap_orphans(database, VALUATION_WORKER, identity=now, now=at) == [older]
    _assert_reaped(database, older, by="valuation_worker:instance-now", at=at)
    for run_id in (newer, marked_after, asfiled):
        _assert_untouched(database, run_id)
    assert reap_orphans(database, IR_WORKER, identity=now, now=at) == [asfiled]
    _assert_reaped(database, asfiled, by="investor_relations_worker:instance-now", at=at)


def test_reaping_is_idempotent(database: Database) -> None:
    orphan = _run(database, "valuation-worker-v2-data", "valuation_worker", started_at=T0,
                  marker=_marker(_identity("previous", T0), "valuation_worker"))
    now = _identity("now", T0 + timedelta(hours=1))
    first_at = T0 + timedelta(hours=1, minutes=1)
    assert reap_orphans(database, VALUATION_WORKER, identity=now, now=first_at) == [orphan]
    assert reap_orphans(database, VALUATION_WORKER, identity=now, now=first_at + timedelta(minutes=5)) == []
    later = _identity("later", T0 + timedelta(hours=3))
    assert reap_orphans(database, VALUATION_WORKER, identity=later, now=T0 + timedelta(hours=3)) == []
    _assert_reaped(database, orphan, by="valuation_worker:instance-now", at=first_at)  # the first reaping stands


def test_two_workers_of_different_types_starting_together(database: Database) -> None:
    previous = _identity("previous", T0)
    valuation = [_run(database, f"valuation-worker-{n}", "valuation_worker", started_at=T0 + timedelta(minutes=n),
                      marker=_marker(previous, "valuation_worker")) for n in range(3)]
    ir = [_run(database, code, "regulatory_disclosure", started_at=T0 + timedelta(minutes=1),
               marker=_marker(_identity("previous-ir", T0), "investor_relations_worker")) for code in ("cvm", "sec")]
    start = T0 + timedelta(hours=1)
    results: dict[str, list[str]] = {}
    if database.database_url:  # TEMP tables live in one connection: the two startups run back to back on it
        for ownership, name in ((VALUATION_WORKER, "valuation"), (IR_WORKER, "ir")):
            results[name] = reap_orphans(database, ownership, identity=_identity(name, start), now=start)
    else:
        barrier = threading.Barrier(2)

        def startup(ownership: WorkerOwnership, name: str) -> None:
            barrier.wait()
            results[name] = reap_orphans(database, ownership, identity=_identity(name, start), now=start)

        threads = [threading.Thread(target=startup, args=(VALUATION_WORKER, "valuation")),
                   threading.Thread(target=startup, args=(IR_WORKER, "ir"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    assert sorted(results["valuation"]) == sorted(valuation) and sorted(results["ir"]) == sorted(ir)
    for run_id in valuation:
        _assert_reaped(database, run_id, by="valuation_worker:instance-valuation", at=start)
    for run_id in ir:
        _assert_reaped(database, run_id, by="investor_relations_worker:instance-ir", at=start)


def test_the_reaper_never_unblocks_a_finished_run_and_a_live_finish_still_lands(database: Database) -> None:
    """A run reaped while its process was in fact alive (two processes of one role — outside the rule) is not lost:
    the live process's finish_ingestion_run still records the real outcome."""
    orphan = _run(database, "valuation-worker-v2-data", "valuation_worker", started_at=T0,
                  marker=_marker(_identity("previous", T0), "valuation_worker"))
    assert reap_orphans(database, VALUATION_WORKER, identity=_identity("now", T0 + timedelta(hours=1)),
                        now=T0 + timedelta(hours=1)) == [orphan]
    database.finish_ingestion_run(orphan, "succeeded", 1, 1)
    assert _state(database, orphan)["status"] == "succeeded"


def test_claimed_roles_are_single_and_a_fork_is_a_new_process(monkeypatch: pytest.MonkeyPatch) -> None:
    parent = ingestion_process.claim_worker_role("valuation_worker")
    assert ingestion_process.claim_worker_role("valuation_worker") == parent  # idempotent
    with pytest.raises(RuntimeError):
        ingestion_process.claim_worker_role("investor_relations_worker")
    with pytest.raises(ValueError):
        ingestion_process.claim_worker_role("")
    monkeypatch.setattr(ingestion_process.os, "getpid", lambda: parent.pid + 1)
    child = ingestion_process.current()
    assert child.instance != parent.instance and child.pid == parent.pid + 1 and ingestion_process.role() is None
    assert "process_role" not in ingestion_process.stamp({})
    assert ingestion_process.stamp({"process_instance": "explicit"})["process_instance"] == "explicit"


def test_reap_at_startup_claims_the_role_and_never_blocks_the_worker(caplog: pytest.LogCaptureFixture) -> None:
    class Broken:
        def reap_orphaned_ingestion_runs(self, **_: Any) -> list[str]:
            raise RuntimeError("database unavailable")

    assert ingestion_process.reap_at_startup(Broken(), IR_WORKER) == []
    assert ingestion_process.role() == "investor_relations_worker"
    assert "ingestion orphan reaper failed" in caplog.text


def test_the_postgresql_statement_is_one_guarded_atomic_update() -> None:
    """The SQL text the PostgreSQL branch sends (no server needed): one UPDATE guarded by status = 'running', the start
    instant, the role/instance of a marked row or the owned sources of an unmarked one, RETURNING the ids."""
    calls: list[tuple[str, dict[str, Any]]] = []

    class Cursor:
        def fetchall(self) -> list[tuple[str]]:
            return [("11111111-1111-1111-1111-111111111111",)]

    class Connection:
        def execute(self, sql: str, params: dict[str, Any]) -> Cursor:
            calls.append((sql, params))
            return Cursor()

        def commit(self) -> None:
            calls.append(("COMMIT", {}))

    db = Database(Settings(database_url=""))
    db.database_url = "postgresql://unused"

    @contextmanager
    def fake_connection():
        yield Connection()

    db.connection = fake_connection  # type: ignore[method-assign]
    now = _identity("now", T0)
    at = T0 + timedelta(minutes=1)
    assert reap_orphans(db, VALUATION_WORKER, identity=now, now=at) == ["11111111-1111-1111-1111-111111111111"]
    assert [sql for sql, _ in calls].count("COMMIT") == 1 and len(calls) == 2
    sql, params = calls[0]
    flat = " ".join(sql.split())
    assert flat.startswith("UPDATE ingestion_runs AS run SET status = 'failed'")
    assert "WHERE run.status = 'running' AND run.started_at < %(process_started_at)s" in flat
    assert "run.metadata ->> 'process_role' = %(role)s AND run.metadata ->> 'process_instance' IS DISTINCT FROM %(process_instance)s" in flat
    assert "NOT (run.metadata ? 'process_instance')" in flat
    assert "source.source_type = ANY(%(legacy_source_types)s::text[]) OR source.code = ANY(%(legacy_source_codes)s::text[])" in flat
    assert "jsonb_build_object('reaped_at', %(reaped_at_text)s::text, 'reaped_by', %(reaped_by)s::text)" in flat
    assert flat.endswith("RETURNING run.id::text")
    assert params == {"role": "valuation_worker", "process_instance": "instance-now", "process_started_at": T0,
                      "legacy_source_types": ["valuation_worker"], "legacy_source_codes": [], "reaped_at": at,
                      "reaped_at_text": at.isoformat(), "reaped_by": "valuation_worker:instance-now",
                      "error_summary": ORPHAN_ERROR_SUMMARY}


@pytest.mark.parametrize(("module", "ownership"), [("valuation_worker", "VALUATION_WORKER"), ("ir_worker", "IR_WORKER")])
def test_the_workers_reap_at_startup_before_any_run(module: str, ownership: str) -> None:
    source = (APP / f"{module}.py").read_text(encoding="utf-8")
    main = source[source.index("def main() -> None:"):]
    call = f"ingestion_process.reap_at_startup(database, ingestion_process.{ownership})"
    assert main.count(call) == 1
    assert main.index("database.initialize()") < main.index(call) < main.index("while True:")
    # nothing that can begin a run is constructed or called before the reaper
    for later in ("InvestorRelationsService(", "MarketDataService(", "ensure_builtin_official_fundamentals(", "B3ScreenerService("):
        if later in main:
            assert main.index(call) < main.index(later), later
