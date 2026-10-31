"""Synthetic storage/selection integration; never a live publication or PIT look."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest

from app import listed_universe_publication as publication
from app import listed_universe_decision as expanded_decision
from app import valuation_decision as core_decision
from app import valuation_official as official
from app.database import Database
from app.listed_universe import Catalogue, Listing, digest
from app.listed_universe_runtime import STAGE_ANALYSIS, stage_predictions
from app.valuation_policy import METHODOLOGY_VERSION
from test_listed_universe_runtime import Adapter, run
from test_valuation_decision import CUT, _activated_at, _database, _night, _row, _switch_to_internal, _universe

STAGE = CUT + timedelta(minutes=40)
PREPARE = CUT + timedelta(minutes=50)
COMMIT = CUT + timedelta(minutes=51)


def tables(database):
    return copy.deepcopy((database._analysis_snapshots, database._valuation_predictions, database._valuation_official_selections))


def add_stage(database, market, size=5):
    source = {"NASDAQ": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
              "NYSE": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
              "B3": "https://bvmf.bmfbovespa.com.br/suplemento/ExecutaAcaoDownload.asp?arquivo=Titulos_Negociaveis.zip&server=L"}[market]
    listings = tuple(Listing(market, f"N{index:04d}", f"Stock {index}") for index in range(size))
    catalogue = Catalogue(market, source, "b3-titulos-220-v1" if market == "B3" else "nasdaq-trader-pipe-v1",
                          (STAGE - timedelta(minutes=10)).isoformat(),
                          STAGE.date().isoformat() if market == "B3" else STAGE.isoformat(), "a" * 64, size, {}, listings)
    rows = [_row(item.symbol, tp=45, buy_in=32, price=1, market=market) for item in listings[:-1]]
    run_identity, context = digest({"synthetic_run": market}), digest({"synthetic_context": market})
    stage_id = database.save_analysis_snapshot(
        STAGE_ANALYSIS, market, "synthetic-stage-method", {"canonical_methodology_version": 32,
            "run_identity": run_identity, "source_manifest_sha256": catalogue.payload()["manifest_sha256"]},
        {"rows": rows, "not_evaluable": {listings[-1].symbol: "statements_missing"}, "inventory_count": size,
         "context_sha256": context}, STAGE + timedelta(minutes=1))
    records = [official.prediction_from_row(row, market=market, scope="universe", cycle_id=stage_id,
        source_version="32", prediction_instant=STAGE, published_at=STAGE + timedelta(minutes=1), source=source,
        source_manifest_sha256=catalogue.payload()["manifest_sha256"],
        extra_provenance={"full_universe_stage": True, "run_identity": run_identity, "context_sha256": context})
        for source in official.OFFICIAL_SOURCES for row in rows]
    assert all(record is not None for record in records)
    database.insert_valuation_predictions(records)
    return catalogue, stage_id


@pytest.fixture
def world(monkeypatch):
    database = _database()
    cycles = _night(database)
    _switch_to_internal(database, cycles, monkeypatch, at=CUT + timedelta(minutes=20))
    catalogues, stages = {}, {}
    for market in publication.MARKETS:
        catalogues[market], stages[market] = add_stage(database, market)
    return database, catalogues, stages


def prepare(world, **changes):
    database, catalogues, stages = world
    return publication.prepare_publication(database, catalogues, stages,
        expected_predecessor=changes.pop("expected_predecessor", official.current_generation(database)["generation_id"]),
        max_age_seconds=changes.pop("max_age_seconds", 3600), now=changes.pop("now", PREPARE), **changes)


def test_real_canonical_records_promote_all_three_only_in_an_isolated_copy(world):
    database, catalogues, stages = world
    original = tables(database)
    receipt = prepare(world)
    assert tables(database) == original
    assert receipt["production_release_allowed"] is False
    sandbox = publication.AtomicPublicationSandbox(database)
    result = sandbox.apply(receipt, now=COMMIT)
    view, generation = sandbox.view(), result["generation"]
    assert tables(database) == original
    assert result["sandbox_only"] is True and result["production_release_allowed"] is False
    assert result["post_commit_served_capture_performed"] is False
    assert generation["previous_generation_id"] == original[2][-1]["generation_id"]
    assert generation["source"] == official.SOURCE_INTERNAL and generation["source_version"] == "32"
    assert generation["receipt"].get("explicit") is None and "source_switch" not in generation["receipt"]
    assert len(view._valuation_official_selections) == len(original[2]) + 1
    for market in publication.MARKETS:
        cycle = view.analysis_snapshot_by_id(generation["cycles"][market])
        assert cycle["analysis_type"] == "valuation_universe" and cycle["entity_key"] == market + "_UNIVERSE"
        assert cycle["published_at"] == COMMIT and cycle["inputs"]["prediction_instant"] == STAGE.isoformat()
        assert cycle["inputs"]["rerun_of"] == stages[market]
        assert len(cycle["outputs"]["rows"]) == 4 and cycle["outputs"]["not_evaluable"] == {"N0004": "statements_missing"}
        assert cycle["outputs"]["universe_size"] == 5  # missing data is counted, not hidden
        staged = database.valuation_predictions_for_cycle(stages[market], source=official.SOURCE_INTERNAL)
        served = official.official_rows(view, market, generation=generation)
        assert set(served) == set(staged)
        for name, record in staged.items():
            assert served[name]["our_tp"] == record["tp"] and served[name]["buy_in"] == record["buy_in"]
            assert served[name]["prediction_instant"] == record["prediction_instant"]
        assert catalogues[market].listings[-1].symbol not in served


def test_uncapped_catalogue_and_missing_names_reconcile_in_one_composition(world):
    database, catalogues, stages = world
    catalogues["NASDAQ"], stages["NASDAQ"] = add_stage(database, "NASDAQ", size=403)
    receipt = prepare(world)
    sandbox = publication.AtomicPublicationSandbox(database)
    generation = sandbox.apply(receipt, now=COMMIT)["generation"]
    assert len(official.official_rows(sandbox.view(), "NASDAQ", generation=generation)) == 402
    cycle = sandbox.view().analysis_snapshot_by_id(generation["cycles"]["NASDAQ"])
    assert cycle["outputs"]["universe_size"] == 403 and cycle["outputs"]["not_evaluable"] == {"N0402": "statements_missing"}


def test_isolated_composition_does_not_grant_scientific_buy_permission(world, monkeypatch):
    sandbox = publication.AtomicPublicationSandbox(world[0])
    sandbox.apply(prepare(world), now=COMMIT)
    view = sandbox.view()
    decided_at = COMMIT + timedelta(minutes=2)  # honour the unchanged core's 60 s availability margin
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return decided_at.astimezone(tz or timezone.utc)
    monkeypatch.setattr(core_decision, "datetime", Clock)
    monkeypatch.setattr(expanded_decision, "datetime", Clock)
    receipt = expanded_decision.run_full_universe_decisions(view, now=decided_at, record=True)
    assert receipt["captured"] == 12 and receipt["artifact_verifier_configured"] is False
    assert sum(receipt["markets"][market]["verdicts"].get("COMPRA_PERMITIDA", 0) for market in publication.MARKETS) == 0
    for market in publication.MARKETS:
        permissions = expanded_decision.latest_permissions(view, market, ["N0000", "N0004"], now=decided_at)
        assert set(permissions) == {"N0000"} and permissions["N0000"]["population_snapshot_id"] is None
        assert all(item["buy_permission"] is False for item in permissions.values())


def test_actual_resumable_runtime_stage_is_accepted_by_canonical_transaction_preparation(world, tmp_path, monkeypatch):
    # The historical decisor fixture is version 32; the current canonical
    # producer is version 33. Do not relabel that stage to fit the old fixture.
    database = _database()
    cycles = {}
    with _activated_at(database, CUT + timedelta(minutes=2)):
        for market in publication.MARKETS:
            cycles[market] = database.save_analysis_snapshot("valuation_universe", market + "_UNIVERSE", "current-canonical-method",
                {"methodology_version": METHODOLOGY_VERSION},
                {"rows": [_row("OLD", tp=40, buy_in=30, price=20, market=market)], "universe_size": 1}, CUT)
    report = official.before_after_report(database, cycles=cycles, targeted={}, source_version=str(METHODOLOGY_VERSION))
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", report["report_sha256"])
    official.select_generation(database, cycles=cycles, now=CUT + timedelta(minutes=20), activated_by="synthetic-owner",
                               reason="synthetic current-version fixture", source=official.SOURCE_INTERNAL,
                               source_version=str(METHODOLOGY_VERSION), before_after_sha256=report["report_sha256"])
    catalogues, stages = {}, {}
    for market in publication.MARKETS:
        before = datetime.now(timezone.utc)
        template, _ = add_stage(database, market)
        raw = template.payload()
        raw.update(received_at=before.isoformat(), source_date=before.date().isoformat() if market == "B3" else before.isoformat())
        raw.pop("manifest_sha256")
        raw["manifest_sha256"] = digest(raw)
        catalogue = publication.catalogue_from_payload(raw)
        directory = tmp_path / market
        assert run(catalogue, directory, Adapter(missing={"N0004"}))["complete"] is True
        catalogues[market], stages[market] = catalogue, stage_predictions(database, directory, act=True)["stage_snapshot_id"]
    at = datetime.now(timezone.utc)
    receipt = publication.prepare_publication(database, catalogues, stages, expected_predecessor=official.current_generation(database)["generation_id"],
                                               max_age_seconds=60, now=at)
    result = publication.AtomicPublicationSandbox(database).apply(receipt, now=at + timedelta(microseconds=1))
    assert set(result["generation"]["cycles"]) == set(publication.MARKETS)
    assert result["production_release_allowed"] is False


@pytest.mark.parametrize("phase", ["third_cycle_validation", "after_generation_insert"])
def test_failure_after_partial_work_discards_every_new_cycle_record_and_generation(world, monkeypatch, phase):
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(world[0])
    before = tables(sandbox.view())
    if phase == "third_cycle_validation":
        original = official.cycle_validation
        def fail(snapshot, **kwargs):
            result = original(snapshot, **kwargs)
            if snapshot.get("entity_key") == "NYSE_UNIVERSE" and snapshot.get("inputs", {}).get("rerun_of"):
                return {**result, "valid": False}
            return result
        monkeypatch.setattr(official, "cycle_validation", fail)
    else:
        original_new = official._new_generation
        def fail_after_insert(*args, **kwargs):
            original_new(*args, **kwargs)
            raise ValueError("synthetic failure after selection insertion")
        monkeypatch.setattr(official, "_new_generation", fail_after_insert)
    with pytest.raises(ValueError):
        sandbox.apply(receipt, now=COMMIT)
    assert tables(sandbox.view()) == before


def test_concurrent_same_predecessor_has_one_winner_and_no_partial_loser(world):
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(world[0])
    before = tables(sandbox.view())
    def attempt():
        try:
            return sandbox.apply(receipt, now=COMMIT)["generation"]
        except ValueError as exc:
            assert "predecessor" in str(exc)
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1
    after = tables(sandbox.view())
    assert len(after[0]) == len(before[0]) + 3 and len(after[1]) == len(before[1]) + 24
    assert len(after[2]) == len(before[2]) + 1


def test_reader_waits_for_whole_private_commit_and_source_remains_old(world, monkeypatch):
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(world[0])
    entered, proceed, reader_started = Event(), Event(), Event()
    original = official._new_generation
    def paused(*args, **kwargs):
        entered.set()
        assert proceed.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(official, "_new_generation", paused)
    def read():
        reader_started.set()
        return sandbox.view()
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(sandbox.apply, receipt, now=COMMIT)
        assert entered.wait(5)
        reader = pool.submit(read)
        assert reader_started.wait(5) and not reader.done()
        assert official.current_generation(world[0])["generation_id"] == receipt["expected_predecessor"]
        proceed.set()
        result, view = writer.result(timeout=5), reader.result(timeout=5)
    assert official.current_generation(view)["cycles"] == result["generation"]["cycles"]


@pytest.mark.parametrize("damage", ["omission", "record", "foreign_market", "version", "old_prediction", "future_publication"])
def test_damaged_or_wrong_stage_is_rejected_without_writes(world, damage):
    database, catalogues, stages = world
    stage = next(item for item in database._analysis_snapshots if item["id"] == stages["B3"])
    if damage == "omission":
        stage["outputs"]["not_evaluable"] = {}
    elif damage == "record":
        record = next(item for item in database._valuation_predictions if item["cycle_id"] == stages["B3"])
        record["tp"] += 1
        database.drop_official_cycle_cache()
    elif damage == "foreign_market":
        stages["B3"] = stages["NYSE"]
    elif damage == "version":
        stage["inputs"]["canonical_methodology_version"] = 33
    elif damage == "old_prediction":
        record = next(item for item in database._valuation_predictions if item["cycle_id"] == stages["B3"])
        record["prediction_instant"] = CUT.isoformat()
        database.drop_official_cycle_cache()
    else:
        stage["published_at"] = COMMIT + timedelta(minutes=1)
    before = tables(database)
    with pytest.raises(ValueError):
        prepare(world)
    assert tables(database) == before


@pytest.mark.parametrize("change", ["new_head", "new_order", "stage", "pending_targeted"])
def test_read_set_is_revalidated_at_the_atomic_boundary(world, change):
    database, _, stages = world
    receipt = prepare(world)
    if change in {"new_head", "new_order"}:
        generation = copy.deepcopy(official.current_generation(database))
        generation.update(generation_id=str(uuid4()), previous_generation_id=generation["generation_id"],
                          activated_at=(PREPARE + timedelta(seconds=1)).isoformat(), receipt={"explicit": change == "new_order"})
        database.insert_valuation_official_selection(generation)
    elif change == "stage":
        stage = next(item for item in database._analysis_snapshots if item["id"] == stages["B3"])
        stage["outputs"]["not_evaluable"]["N0004"] = "official_statement_missing"
    else:
        add_pending_targeted(database)
    sandbox = publication.AtomicPublicationSandbox(database)
    before = tables(sandbox.view())
    with pytest.raises(ValueError, match="predecessor|read set"):
        sandbox.apply(receipt, now=COMMIT)
    assert tables(sandbox.view()) == before


def add_pending_targeted(database):
    snapshot = {"id": str(uuid4()), "analysis_type": official.TARGETED_ANALYSIS, "entity_key": "OUTSIDE",
                "methodology_version_id": "mv-1", "inputs": {"methodology_version": 32},
                "outputs": {"row": _row("OUTSIDE", tp=40, buy_in=30, price=20)}, "published_at": STAGE}
    database._analysis_snapshots.append(snapshot)
    assert official.record_cycle_predictions(database, snapshot) == 2
    return snapshot["id"]


def test_registered_targeted_recovery_uses_the_existing_canonical_admission_policy(world):
    database, _, _ = world
    targeted = add_pending_targeted(database)
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(database)
    generation = sandbox.apply(receipt, now=COMMIT)["generation"]
    assert generation["targeted"] == {"OUTSIDE": targeted}
    assert generation["receipt"]["targeted_recovered"] == {"OUTSIDE": targeted}
    assert official.official_row(sandbox.view(), "B3", "OUTSIDE", generation=generation)["official_cycle_id"] == targeted


def test_freeze_and_explicit_order_hold_original_prediction_even_if_republished_later(world):
    database, _, _ = world
    head = database._valuation_official_selections[-1]
    original = copy.deepcopy(head)
    head["receipt"] = {"explicit": True, "freeze": {"until": COMMIT.isoformat()}}
    with pytest.raises(ValueError, match="freeze"):
        prepare(world)
    head.clear()
    head.update(original)
    head["activated_at"] = STAGE.isoformat()  # the staged prediction is at/before this order
    with pytest.raises(ValueError, match="explicit order"):
        prepare(world)


@pytest.mark.parametrize("value", [None, True, 0, -1, float("inf"), "3600"])
def test_freshness_is_explicit_and_closed_on_missing_or_malformed_limit(world, value):
    with pytest.raises(ValueError, match="freshness"):
        prepare(world, max_age_seconds=value)


def test_recheck_cannot_use_fresh_publication_to_hide_stale_original_prediction(world):
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(world[0])
    before = tables(sandbox.view())
    with pytest.raises(ValueError, match="stale"):
        sandbox.apply(receipt, now=COMMIT + timedelta(hours=2))
    assert tables(sandbox.view()) == before


def test_integrity_hash_and_json_flags_cannot_enable_production(world):
    receipt = prepare(world)
    for key in ["production_release_allowed", "legacy_writer_ownership_enforced", "production_sql_writer_implemented", "schedule_enabled"]:
        forged = {**receipt, key: True}
        forged["preparation_sha256"] = publication._hash({k: v for k, v in forged.items() if k != "preparation_sha256"})
        with pytest.raises(ValueError, match="closed production gates"):
            publication.AtomicPublicationSandbox(world[0]).apply(forged, now=COMMIT)
    with pytest.raises(TypeError):
        publication.production_preflight(writer_ownership=True)
    world[0].database_url = "postgresql://must-not-connect.invalid/db"
    with pytest.raises(ValueError, match="in-memory"):
        publication.AtomicPublicationSandbox(world[0])


def test_new_code_or_mutated_targeted_record_cannot_reuse_a_preparation(world, monkeypatch):
    receipt, sandbox = prepare(world), publication.AtomicPublicationSandbox(world[0])
    monkeypatch.setattr(publication, "producer_identity", lambda: {"synthetic_changed_file": "a" * 64})
    with pytest.raises(ValueError, match="integrity"):
        sandbox.apply(receipt, now=COMMIT)
    monkeypatch.undo()
    cycle = add_pending_targeted(world[0])
    record = next(item for item in world[0]._valuation_predictions if item["cycle_id"] == cycle and item["source"] == official.SOURCE_INTERNAL)
    record["tp"] += 1
    world[0].drop_official_cycle_cache()
    with pytest.raises(ValueError, match="targeted immutable"):
        prepare(world)


def test_real_legacy_writer_can_still_shrink_a_later_generation_so_ownership_stays_blocked(world):
    sandbox = publication.AtomicPublicationSandbox(world[0])
    expanded = sandbox.apply(prepare(world), now=COMMIT)["generation"]
    local = sandbox.view()
    with _activated_at(local, COMMIT + timedelta(minutes=5)):
        legacy = _universe(local, "B3", [_row("LEGACY", tp=20, buy_in=10, price=5)], COMMIT + timedelta(minutes=4))
    later = official.current_generation(local)
    assert later["cycles"]["B3"] == legacy and later["cycles"]["NASDAQ"] == expanded["cycles"]["NASDAQ"]
    assert len(official.official_rows(local, "B3", generation=expanded)) == 4
    assert set(official.official_rows(local, "B3", generation=later)) == {"LEGACY"}
    assert publication.production_preflight()["legacy_writer_ownership_enforced"] is False
