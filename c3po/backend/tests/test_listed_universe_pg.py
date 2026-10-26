"""Local transaction-contract doubles, NOT PostgreSQL/DDL/concurrency proof."""
from contextlib import contextmanager
import copy
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import listed_universe_pg as pg
from app.listed_universe import digest
from app.listed_universe_runtime import producer_identity
from test_listed_universe_publication import world, PREPARE, COMMIT, tables


class ContractPgError(RuntimeError):
    def __init__(self, sqlstate):
        super().__init__("private raw error must never be included in routing receipts")
        self.sqlstate = sqlstate


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows


class ConnectionDouble:
    """Records DB-API calls and rollback boundaries; does not interpret SQL."""
    def __init__(self, *, fail=None):
        self.info = SimpleNamespace(transaction_status=0)
        self.roles = (pg.PUBLISHER, pg.PUBLISHER)
        self.isolation = "read committed"
        self.epoch = [str(uuid4()), "official_internal_v1", "32", digest(producer_identity()), "a" * 64,
                      PREPARE-timedelta(minutes=1), COMMIT+timedelta(minutes=1)]
        self.clocks = iter([PREPARE, COMMIT])
        self.calls, self.writes, self.counts = [], [], {}
        self.transactions = self.commits = self.rollbacks = 0
        self.fail = fail
        self.read_damage = None

    @contextmanager
    def transaction(self, *, force_rollback=False):
        assert force_rollback is True
        self.transactions += 1
        self.info.transaction_status = 2
        before = copy.deepcopy(self.writes)
        try:
            yield
        except BaseException:
            self.writes = before
            self.rollbacks += 1
            raise
        else:
            self.commits += 1
        finally:
            self.info.transaction_status = 0

    def execute(self, query, params=None):
        assert self.info.transaction_status == 2 or query.startswith("SELECT id::text")
        self.calls.append((query, params))
        if query == "SHOW transaction_isolation":
            return Cursor((self.isolation,))
        if query == "SELECT clock_timestamp()":
            return Cursor((next(self.clocks),))
        if query == "SELECT current_user::text, session_user::text":
            return Cursor(self.roles)
        if query == pg.READ_EPOCH:
            return Cursor(self.epoch)
        flat = " ".join(query.split())
        if "FROM analysis_snapshots WHERE id = %s" in flat:
            value = next(values for kind, values in self.writes if kind == "snapshot" and values[0] == params[0])
            row = (*value[:4], json.loads(value[4]), json.loads(value[5]), value[6])
            if self.read_damage == "snapshot":
                row[5]["universe_size"] += 1
            return Cursor(row)
        if "FROM valuation_predictions WHERE cycle_id = %s AND source = %s" in flat:
            rows = [list(values) for kind, values in self.writes if kind == "record" and values[7] == params[0] and values[1] == params[1]]
            if self.read_damage == "record":
                rows[0][10] += Decimal(1)
            return Cursor(rows=rows)
        kinds = {pg.REGISTER: "cohort", pg.INSERT_SNAPSHOT: "snapshot", pg.INSERT_RECORD: "record", pg.INSERT_SELECTION: "selection"}
        kind = kinds.get(query)
        if kind:
            self.counts[kind] = self.counts.get(kind, 0)+1
            if self.fail == (kind, self.counts[kind]):
                raise ContractPgError("40001")
            self.writes.append((kind, params))
        return Cursor()


@pytest.fixture
def compiled(world):
    database, catalogues, stages = world
    before = tables(database)
    value = pg.compile_locked(database, catalogues, stages,
        expected_predecessor=database.latest_valuation_official_selection()["generation_id"],
        max_age_seconds=3600, published_at=PREPARE)
    assert tables(database) == before
    return value


def rehearse(monkeypatch, connection, compiled):
    # Reuse the genuine canonical compiler result. The fake connection does not
    # emulate PostgreSQL SELECT/locking/trigger semantics and claims none.
    monkeypatch.setattr(pg, "compile_locked", lambda *args, **kwargs: copy.deepcopy(compiled))
    return pg.rehearse(connection, {}, {}, expected_predecessor=compiled["preparation"]["expected_predecessor"], max_age_seconds=3600)


def test_real_canonical_compiler_preserves_storage_basis_and_three_market_cohort(compiled):
    assert len(compiled["snapshots"]) == 3 and len(compiled["records"]) == 24
    assert {item["entity_key"] for item in compiled["snapshots"]} == {m+"_UNIVERSE" for m in pg.publication.MARKETS}
    assert {item["source"] for item in compiled["records"]} == {"official_blend_v1", "official_internal_v1"}
    assert compiled["generation"]["previous_generation_id"] == compiled["preparation"]["expected_predecessor"]
    assert compiled["preparation"]["production_release_allowed"] is False


def test_supersession_points_to_latest_published_cycle_even_when_selection_carries_an_older_one(world):
    database, catalogues, stages = world
    older = database.latest_valuation_official_selection()["cycles"]["B3"]
    unselected = database.analysis_snapshot_by_id(older)
    unselected.update(id=str(uuid4()), published_at=PREPARE-timedelta(minutes=1), outputs={"rows": [], "universe_size": 5})
    database._analysis_snapshots.append(unselected)  # genuine invalid later cycle, not selected
    compiled = pg.compile_locked(database, catalogues, stages, expected_predecessor=database.latest_valuation_official_selection()["generation_id"],
                                 max_age_seconds=3600, published_at=PREPARE)
    assert compiled["superseded_cycles"]["B3"] == unselected["id"] and compiled["superseded_cycles"]["B3"] != older


def test_one_connection_one_transaction_and_complete_sql_batch_always_roll_back(monkeypatch, compiled):
    connection = ConnectionDouble()
    receipt = rehearse(monkeypatch, connection, compiled)
    assert connection.transactions == connection.rollbacks == 1 and connection.commits == 0 and connection.writes == []
    assert connection.counts == {"cohort": 1, "snapshot": 3, "record": 24, "selection": 1}
    assert connection.calls[0][0] == "SHOW transaction_isolation"
    assert connection.calls[1][0] == "SELECT c3po_full_universe.lock_cohort()"
    selection = next(params for query, params in connection.calls if query == pg.INSERT_SELECTION)
    assert selection[7] == COMMIT.isoformat()  # server clock read AFTER all records
    assert connection.calls[-2][0] == "SELECT clock_timestamp()" and connection.calls[-1][0] == pg.INSERT_SELECTION
    assert receipt["rolled_back"] is True and receipt["committed"] is False
    assert receipt["production_release_allowed"] is False and receipt["postgresql_behavior_proven_by_this_receipt"] is False
    assert receipt["post_commit_capture_performed"] is False


@pytest.mark.parametrize("phase", [("cohort", 1), ("snapshot", 2), ("record", 7), ("selection", 1)])
def test_failure_at_each_storage_phase_rolls_back_without_per_market_commits(monkeypatch, compiled, phase):
    connection = ConnectionDouble(fail=phase)
    with pytest.raises(ContractPgError):
        rehearse(monkeypatch, connection, compiled)
    assert connection.rollbacks == 1 and connection.commits == 0 and connection.writes == []


@pytest.mark.parametrize("roles", [("c3po", "c3po"), (pg.PUBLISHER, "c3po"), ("c3po", pg.PUBLISHER), None])
def test_authenticated_principal_cannot_be_replaced_by_set_role_or_flags(monkeypatch, compiled, roles):
    connection = ConnectionDouble()
    connection.roles = roles
    with pytest.raises(pg.ProductionReleaseClosed, match="authenticated"):
        rehearse(monkeypatch, connection, compiled)
    assert connection.writes == [] and connection.commits == 0 and connection.rollbacks == 1


@pytest.mark.parametrize("change", ["absent", "expired", "future_review", "code", "source", "version"])
def test_missing_or_wrong_database_epoch_never_reaches_commit(monkeypatch, compiled, change):
    connection = ConnectionDouble()
    if change == "absent":
        connection.epoch = None
    elif change == "expired":
        connection.epoch[-1] = PREPARE
    elif change == "future_review":
        connection.epoch[-2] = COMMIT
    elif change == "code":
        connection.epoch[3] = "0" * 64
    elif change == "source":
        connection.epoch[1] = "official_blend_v1"
    else:
        connection.epoch[2] = "33"
    with pytest.raises(pg.ProductionReleaseClosed):
        rehearse(monkeypatch, connection, compiled)
    assert connection.writes == [] and connection.commits == 0 and connection.rollbacks == 1


def test_nested_transaction_and_public_commit_have_no_release_option(monkeypatch, compiled):
    connection = ConnectionDouble()
    connection.info.transaction_status = 2
    with pytest.raises(pg.ProductionReleaseClosed, match="idle"):
        rehearse(monkeypatch, connection, compiled)
    assert connection.transactions == 0 and connection.calls == []
    with pytest.raises(pg.ProductionReleaseClosed, match="not_implemented"):
        pg.commit_publication()
    with pytest.raises(TypeError):
        pg.commit_publication(approved=True)


@pytest.mark.parametrize("isolation", ["repeatable read", "serializable"])
def test_old_readiness_snapshots_cannot_be_used_for_rehearsal(monkeypatch, compiled, isolation):
    connection = ConnectionDouble()
    connection.isolation = isolation
    with pytest.raises(pg.ProductionReleaseClosed, match="read_committed"):
        rehearse(monkeypatch, connection, compiled)
    assert connection.calls == [("SHOW transaction_isolation", None)]
    assert connection.commits == 0 and connection.writes == []


def test_clock_recession_rolls_back_and_decimal_binding_keeps_float_identity(monkeypatch, compiled):
    connection = ConnectionDouble()
    connection.clocks = iter([PREPARE, PREPARE-timedelta(microseconds=1)])
    with pytest.raises(pg.PublicationContractError, match="clock_receded"):
        rehearse(monkeypatch, connection, compiled)
    assert connection.commits == 0 and connection.writes == []
    bindings = [params for query, params in connection.calls if query == pg.INSERT_RECORD]
    assert bindings and isinstance(bindings[0][10], Decimal)
    assert float(bindings[0][10]) == compiled["records"][0]["tp"]


@pytest.mark.parametrize("damage", ["snapshot", "record"])
def test_storage_projection_mismatch_rolls_back_before_selection(monkeypatch, compiled, damage):
    connection = ConnectionDouble()
    connection.read_damage = damage
    with pytest.raises(pg.PublicationContractError, match="round_trip"):
        rehearse(monkeypatch, connection, compiled)
    assert connection.commits == 0 and connection.writes == [] and "selection" not in connection.counts


def test_bound_database_reads_never_open_another_connection_and_committing_apis_are_refused():
    connection = ConnectionDouble()
    snapshot = (str(uuid4()), "full_universe_stage", "B3", str(uuid4()), {}, {}, PREPARE)
    connection.execute = lambda query, params=None: Cursor(snapshot)
    reader = pg.TransactionReadDatabase(connection)
    assert reader.analysis_snapshot_by_id(snapshot[0])["id"] == snapshot[0]
    with reader.connection() as bound:
        assert bound is connection
    assert connection.transactions == connection.commits == 0
    for operation in [lambda: reader.save_analysis_snapshot(), lambda: reader.insert_valuation_predictions([]),
                      lambda: reader.insert_valuation_official_selection({})]:
        with pytest.raises(pg.PublicationContractError, match="committing_"):
            operation()


@pytest.mark.parametrize("origin", ["nightly", "ir", "b3_targeted", "us_cache_build", "operator"])
def test_fenced_errors_keep_generation_and_ir_pending_without_false_success(origin):
    receipt = pg.legacy_write_disposition(ContractPgError("PZ001"), origin=origin)
    assert receipt["success"] is False and receipt["mark_ir_incorporated"] is False
    assert receipt["keep_current_generation"] is True and receipt["fallback_to_legacy_or_shadow"] is False
    assert receipt["keep_ir_update_pending"] is (origin == "ir")
    assert receipt["operator_order_not_executed"] is (origin == "operator")
    assert receipt["caller_integration_implemented"] is False and "private raw error" not in json.dumps(receipt)
    assert receipt["automatic_retry_allowed"] is False and receipt["requires_integration_or_fact_review"] is True
    assert pg.legacy_write_disposition(RuntimeError("PZ001 from an untrusted string"), origin=origin) is None


def test_actual_numbered_migration_enumerator_never_loads_dormant_review_ddl(world, monkeypatch):
    database = world[0]
    root = Path(__file__).resolve().parents[2]
    ddl = root/"deployment/full-universe/ownership.review.sql"
    assert ddl.is_file() and not ddl.name[0].isdigit()
    statements = []
    class MigrationDouble:
        def execute(self, query):
            statements.append(query)
        def commit(self):
            pass
    @contextmanager
    def connection():
        yield MigrationDouble()
    database.database_url = "no-real-connection"
    database.migrations_dir = root/"db"
    monkeypatch.setattr(database, "connection", connection)
    monkeypatch.setattr(database, "backfill_valuation_change_baseline", lambda: None)
    database.initialize()  # actual unchanged enumerator, fake execution only
    assert len(statements) > 40
    assert not any("CREATE SCHEMA c3po_full_universe" in item for item in statements)
    assert ddl.read_text() not in statements
