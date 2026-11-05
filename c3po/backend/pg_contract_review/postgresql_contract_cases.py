"""DORMANT real-PostgreSQL cases: explicitly named file, never auto-discovered.

Prepared only. No case was executed while writing this suite. A future run needs
an externally verified local throwaway cluster/roles/base schema and explicit
0600 descriptor. Commits below affect synthetic fixture data ONLY in that guarded
database; they do not enable the application's structurally closed committer.
"""
from contextlib import contextmanager
import copy
import json
from uuid import uuid4

import pytest

from app import listed_universe_pg as adapter
from app import valuation_official as official
from .harness import MARKETS, OWNER, record_params, synthetic_row


@contextmanager
def rejected(connection, states):
    try:
        with connection.transaction():
            yield
    except Exception as error:
        assert getattr(error, "sqlstate", None) in states, "unexpected real database error class"
    else:
        raise AssertionError("the real PostgreSQL operation was unexpectedly accepted")


def snapshot(connection, cycle):
    value = adapter.TransactionReadDatabase(connection).analysis_snapshot_by_id(str(cycle))
    assert value is not None
    return value


def snapshot_values(value, *, analysis_type=None, entity_key=None):
    return (str(uuid4()), analysis_type or value["analysis_type"], entity_key or value["entity_key"], value["methodology_version_id"],
            json.dumps(value["inputs"]), json.dumps(value["outputs"]), value["published_at"], value["id"])


def legacy_writes_are_fenced(harness, old_snapshot):
    with harness.connect("legacy") as connection:
        # Correct ordinary INSERT privileges must exist in the external fixture;
        # otherwise permission denial would not exercise the installed trigger.
        for action in ("INSERT", "UPDATE", "DELETE"):
            assert connection.execute("SELECT has_table_privilege(current_user,'public.analysis_snapshots',%s)", (action,)).fetchone()[0]
        with rejected(connection, {"PZ001"}):
            connection.execute(adapter.INSERT_SNAPSHOT, snapshot_values(old_snapshot))
        with rejected(connection, {"PZ006"}):
            connection.execute("UPDATE public.analysis_snapshots SET outputs=outputs||'{\"forged\":true}'::jsonb WHERE id=%s", (old_snapshot["id"],))
        with rejected(connection, {"PZ006"}):
            connection.execute("DELETE FROM public.analysis_snapshots WHERE id=%s", (old_snapshot["id"],))
        with rejected(connection, {"42501"}):
            connection.execute("SET ROLE c3po_full_universe_publisher")
        # A startup/ownership gate, not proof that current migrations work under
        # the handed-off app role: replacing the owned guard must be forbidden.
        with rejected(connection, {"42501"}):
            connection.execute("""CREATE OR REPLACE FUNCTION public.valuation_official_append_only()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$""")


def unrelated_namespaces_stay_outside_the_fence(harness, old_snapshot):
    namespaces = ("valuation_pit_rerun", "valuation_pit_served", "valuation_pit_source", "full_universe_stage", "one_pager_valuation")
    with harness.connect("legacy") as connection:
        for name in namespaces:
            with connection.transaction(force_rollback=True):
                values = snapshot_values(old_snapshot, analysis_type=name, entity_key="SYNTHETIC_NAMESPACE_PROBE")
                connection.execute(adapter.INSERT_SNAPSHOT, values)
                connection.execute("UPDATE public.analysis_snapshots SET outputs=outputs||'{\"synthetic_probe\":true}'::jsonb WHERE id=%s", (values[0],))
                connection.execute("DELETE FROM public.analysis_snapshots WHERE id=%s", (values[0],))
                # A second probe carries a prediction FK. The first already
                # established that unrelated namespace DELETE is not fenced.
                values = snapshot_values(old_snapshot, analysis_type=name, entity_key="SYNTHETIC_PREDICTION_PROBE")
                connection.execute(adapter.INSERT_SNAPSHOT, values)
                # Prediction source alone must not fence PIT: use a genuine
                # synthetic canonical record with a noncanonical snapshot FK.
                record = official.prediction_from_row(synthetic_row("PIT_PROBE"), market="B3", scope="universe", cycle_id=values[0],
                    source_version="test-fixture", prediction_instant=values[6], published_at=values[6], source=official.SOURCE_OFFICIAL)
                assert record is not None
                connection.execute(adapter.INSERT_RECORD, record_params(record))
                # Existing append-only record rules still apply. Roll back the
                # whole probe; do not delete its referenced snapshot artificially.


def real_login_and_privilege_boundaries(harness):
    with harness.connect("legacy") as connection:
        assert not connection.execute("SELECT has_schema_privilege(current_user,'c3po_full_universe','CREATE')").fetchone()[0]
        for table in ("epochs", "cohorts"):
            assert not connection.execute("SELECT has_table_privilege(current_user,%s,'INSERT')", ("c3po_full_universe."+table,)).fetchone()[0]
        for role in (OWNER, adapter.PUBLISHER, "c3po_full_universe_operator"):
            assert not connection.execute("SELECT pg_has_role(current_user,%s,'MEMBER')", (role,)).fetchone()[0]
    with harness.connect("publisher") as connection:
        assert not connection.execute("SELECT has_table_privilege(current_user,'c3po_full_universe.epochs','INSERT')").fetchone()[0]
        for action in ("UPDATE", "DELETE", "TRUNCATE"):
            assert not connection.execute("SELECT has_table_privilege(current_user,'public.analysis_snapshots',%s)", (action,)).fetchone()[0]
    with harness.connect("operator") as connection:
        with rejected(connection, {"PZ005"}):
            # A real authenticated operator is still not a verified mesa order.
            head = harness.head(connection)
            connection.execute(adapter.INSERT_SELECTION, (str(uuid4()), head["source"], head["source_version"], json.dumps(head["cycles"]),
                json.dumps(head["targeted"]), json.dumps(head["session_dates"]), True, adapter._clock(connection), "forged-operator-label",
                head["generation_id"], '{"explicit":true}'))


def public_rehearsal_rolls_back(harness):
    with harness.connect("publisher") as connection:
        before = harness.head(connection)
        counts_before = connection.execute("SELECT (SELECT count(*) FROM public.analysis_snapshots), (SELECT count(*) FROM public.valuation_predictions), (SELECT count(*) FROM public.valuation_official_selection)").fetchone()
        result = adapter.rehearse(connection, harness.catalogues, harness.stages,
            expected_predecessor=str(before["generation_id"]), max_age_seconds=600)
        assert result["rolled_back"] is True and result["committed"] is False and result["production_release_allowed"] is False
        assert result["snapshots_considered"] == 3 and result["records_considered"] == 6
        assert harness.head(connection)["generation_id"] == before["generation_id"]
        counts_after = connection.execute("SELECT (SELECT count(*) FROM public.analysis_snapshots), (SELECT count(*) FROM public.valuation_predictions), (SELECT count(*) FROM public.valuation_official_selection)").fetchone()
        assert counts_before == counts_after
    with pytest.raises(adapter.ProductionReleaseClosed):
        adapter.commit_publication()


def direct_witness_is_rejected_by_postgresql(harness):
    with harness.connect("publisher") as connection:
        with connection.transaction(force_rollback=True):
            compiled, epoch = harness.compile(connection)
            adapter._write_cohort(connection, compiled, epoch)
            foreign = copy.deepcopy(next(item for item in compiled["records"] if item["market"] == "B3"))
            foreign.update(id=str(uuid4()), cycle_id=compiled["generation"]["cycles"]["NASDAQ"])
            foreign["row_sha256"] = official.canonical_sha256({k: v for k, v in foreign.items() if k not in {"id", "row_sha256"}})
            # Real direct INSERT intentionally bypasses Python's binding check
            # but uses the genuine publisher login/grants, never an auth bypass.
            with rejected(connection, {"PZ004"}):
                connection.execute(adapter.INSERT_RECORD, record_params(foreign))
            assert connection.execute("SELECT count(*) FROM public.valuation_predictions WHERE cycle_id=ANY(%s::uuid[])",
                                      (list(compiled["generation"]["cycles"].values()),)).fetchone()[0] == 6
            for field, value in (("market", None), ("market", "US"), ("cycle_id", None)):
                malformed = copy.deepcopy(foreign)
                malformed.update(id=str(uuid4()), **{field: value})
                with rejected(connection, {"PZ004", "PZ005", "23502", "23514"}):
                    connection.execute(adapter.INSERT_RECORD, record_params(malformed))


def every_write_phase_rolls_back(harness):
    # These are real PostgreSQL transaction rollbacks, not a mocked connection.
    # Inject a test exception only after real writes, without weakening a guard.
    class InjectedTestFailure(Exception):
        pass
    with harness.connect("publisher") as connection:
        original = harness.head(connection)
        for stop in ("registered", "first_snapshot", "complete_candidate"):
            compiled = None
            try:
                with connection.transaction():
                    compiled, epoch = harness.compile(connection)
                    if stop == "complete_candidate":
                        adapter._write_cohort(connection, compiled, epoch)
                    else:
                        preparation, generation = compiled["preparation"], compiled["generation"]
                        connection.execute(adapter.REGISTER, (preparation["transaction_id"], epoch["epoch_id"], preparation["expected_predecessor"],
                            json.dumps(generation["cycles"]), json.dumps(preparation["stage_ids"]),
                            json.dumps({m: c["manifest_sha256"] for m, c in preparation["catalogues"].items()}), preparation["preparation_sha256"]))
                        if stop == "first_snapshot":
                            item = compiled["snapshots"][0]
                            market = item["entity_key"].removesuffix("_UNIVERSE")
                            connection.execute(adapter.INSERT_SNAPSHOT, (item["id"], item["analysis_type"], item["entity_key"],
                                item["methodology_version_id"], json.dumps(item["inputs"]), json.dumps(item["outputs"]),
                                item["published_at"], compiled["superseded_cycles"][market]))
                    raise InjectedTestFailure()
            except InjectedTestFailure:
                pass
            assert compiled is not None
            assert harness.head(connection)["generation_id"] == original["generation_id"]
            assert connection.execute("SELECT count(*) FROM c3po_full_universe.cohorts WHERE transaction_id=%s", (compiled["preparation"]["transaction_id"],)).fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM public.analysis_snapshots WHERE id=ANY(%s::uuid[])",
                                      (list(compiled["generation"]["cycles"].values()),)).fetchone()[0] == 0
            assert connection.execute("SELECT count(*) FROM public.valuation_predictions WHERE cycle_id=ANY(%s::uuid[])",
                                      (list(compiled["generation"]["cycles"].values()),)).fetchone()[0] == 0


def concurrent_sessions_atomic_visibility_and_stale_cas(harness):
    # Test-only fixture commit in the strongly guarded disposable database.
    # No application committer, role override or production waiver is enabled.
    with harness.connect("publisher") as first, harness.connect("publisher") as second, harness.connect("legacy") as reader:
        prior = harness.head(reader)
        with first.transaction():
            compiled, epoch = harness.compile(first)
            candidate = adapter._write_cohort(first, compiled, epoch)
            assert harness.head(reader)["generation_id"] == prior["generation_id"]
            with pytest.raises(Exception) as failure:
                adapter.rehearse(second, harness.catalogues, harness.stages,
                    expected_predecessor=str(prior["generation_id"]), max_age_seconds=600)
            assert getattr(failure.value, "sqlstate", None) == "55P03"
        # First transaction committed synthetic data in the disposable DB only.
        new = harness.head(reader)
        assert new["generation_id"] == candidate["generation_id"]
        assert new["previous_generation_id"] == prior["generation_id"] and set(new["cycles"]) == set(MARKETS)
        for market in MARKETS:
            cycle = snapshot(reader, new["cycles"][market])
            assert cycle["entity_key"] == market+"_UNIVERSE"
            assert reader.execute("SELECT count(*) FROM public.valuation_predictions WHERE cycle_id=%s", (cycle["id"],)).fetchone()[0] == 2
        with pytest.raises(ValueError, match="predecessor"):
            adapter.rehearse(second, harness.catalogues, harness.stages,
                expected_predecessor=str(prior["generation_id"]), max_age_seconds=600)
        assert harness.head(reader)["generation_id"] == new["generation_id"]


def test_real_postgresql_contract_only_when_explicitly_selected(review_harness):
    """Ordered phases avoid silently skipping absent/expired/MVCC preconditions."""
    harness = review_harness
    harness.seed_before_installation()
    with harness.connect("schema_admin") as connection:
        old_snapshot = snapshot(connection, harness.head(connection)["cycles"]["B3"])
    # Fix a real repeatable-read snapshot BEFORE installing the fence/epochs,
    # without holding a canonical table lock that would block trigger DDL.
    old_transaction = harness._open("legacy")
    old_transaction.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
    old_transaction.execute("SELECT count(*) FROM public.methodology_versions")
    harness.install_review_artifact()
    with rejected(old_transaction, {"PZ001"}):
        old_transaction.execute(adapter.INSERT_SNAPSHOT, snapshot_values(old_snapshot))
    old_transaction.rollback()
    old_transaction.close()
    harness.connections.remove(old_transaction)
    # No epoch: publisher cannot prepare, but the legacy fence is already on.
    with harness.connect("publisher") as connection:
        with pytest.raises(adapter.ProductionReleaseClosed, match="epoch_absent"):
            adapter.rehearse(connection, harness.catalogues, harness.stages,
                expected_predecessor=str(harness.head(connection)["generation_id"]), max_age_seconds=600)
    legacy_writes_are_fenced(harness, old_snapshot)
    unrelated_namespaces_stay_outside_the_fence(harness, old_snapshot)
    harness.append_synthetic_epoch(expired=True)
    with harness.connect("publisher") as connection:
        with pytest.raises(adapter.ProductionReleaseClosed, match="expired"):
            adapter.rehearse(connection, harness.catalogues, harness.stages,
                expected_predecessor=str(harness.head(connection)["generation_id"]), max_age_seconds=600)
    legacy_writes_are_fenced(harness, old_snapshot)
    harness.append_synthetic_epoch(expired=False)
    real_login_and_privilege_boundaries(harness)
    public_rehearsal_rolls_back(harness)
    direct_witness_is_rejected_by_postgresql(harness)
    every_write_phase_rolls_back(harness)
    concurrent_sessions_atomic_visibility_and_stale_cas(harness)
