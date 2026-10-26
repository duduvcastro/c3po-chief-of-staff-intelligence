"""Actual original-Decisor integration; no host, provider or database connection."""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app import listed_universe_decision as expanded
from app import valuation_decision as decisor
from app import valuation_official as official
from app.listed_universe import POPULATION_ANALYSIS, digest
from test_valuation_decision import CUT, RUN, _activated_at, _database, _night, _row, _switch_to_internal

TEST_REPORT = b"synthetic integration fixture; no external PIT result or GO"
TEST_PREREG = b"synthetic prereg fixture; no scientific look or horizon selection"


def synthetic_verifier(snapshot, original, at):
    """Test-only trusted adapter; inspect known bytes, not declared PASS alone."""
    outputs = snapshot["outputs"]
    if (outputs["receipt_sha256"] != hashlib.sha256(TEST_REPORT).hexdigest()
            or outputs["prereg_sha256"] != hashlib.sha256(TEST_PREREG).hexdigest()):
        return None
    return {"schema": "PIT-BUY-ARTIFACT-ATTESTATION-v1", "scope_snapshot_id": str(snapshot["id"]),
            "scope_outputs_sha256": expanded._hash(outputs), "report_sha256": hashlib.sha256(TEST_REPORT).hexdigest(),
            "prereg_sha256": hashlib.sha256(TEST_PREREG).hexdigest(), "population_sha256": digest(sorted(outputs["members"])),
            "tp_source_version": original["inputs"]["tp_record"]["source_version"],
            "market": original["market"], "symbol": original["symbol"], "tp_row_sha256": original["tp_row_sha256"],
            "generation_id": original["generation_id"], "as_of": at.isoformat(),
            "artifact_manifest_sha256": hashlib.sha256(TEST_REPORT + TEST_PREREG).hexdigest()}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):
    database = _database()
    symbols = [f"SMALL{index:04d}" for index in range(327)]
    rows = [_row(symbol, tp=45.0, buy_in=32.0, price=30.0) for symbol in symbols]
    rows += [_row("BADQUALITY", tp=45.0, buy_in=32.0, price=30.0, valuation_confidence=40),
             _row("NOENTRY", tp=45.0, buy_in=29.0, price=30.0)]
    cycles = _night(database, b3=rows)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return RUN.astimezone(tz or timezone.utc)

    monkeypatch.setattr(decisor, "datetime", Clock)
    monkeypatch.setattr(expanded, "datetime", Clock)
    generation = official.generation_at(database, RUN)
    source_version = official.official_rows(database, "B3", generation=generation)[symbols[0]]["tp_source_version"]
    return database, symbols, cycles, source_version


def scope(database, members, source_version, *, market="B3", verdict="PASS", at=RUN - timedelta(minutes=2), **changes):
    payload = {"schema": "PIT-BUY-POPULATION-v1", "market": market, "verdict": verdict,
               "approved_for_buy": True, "receipt_sha256": hashlib.sha256(TEST_REPORT).hexdigest(), "prereg_sha256": hashlib.sha256(TEST_PREREG).hexdigest(),
               "tp_source_version": source_version, "valid_from": (RUN - timedelta(days=1)).isoformat(),
               "valid_until": (RUN + timedelta(days=1)).isoformat(), "members": list(members),
               "population_sha256": digest(sorted(members)), **changes}
    return database.save_analysis_snapshot(POPULATION_ANALYSIS, market, "mv-test", {}, payload, at)


def saved(database, market="B3"):
    return next(item for item in reversed(database._analysis_snapshots)
                if item["analysis_type"] == expanded.ANALYSIS_TYPE and item["entity_key"] == market)


def rehash_payload(snapshot):
    payload = snapshot["outputs"]
    payload["payload_sha256"] = expanded._hash({key: value for key, value in payload.items() if key != "payload_sha256"})


def rehash_record(record):
    record["guarded_row_sha256"] = expanded._hash({key: value for key, value in record.items() if key != "guarded_row_sha256"})


def test_real_decisor_runs_uncapped_then_population_guard_restricts_without_original_writes(world):
    database, symbols, _, version = world
    inside = [symbols[0], symbols[-1], "BADQUALITY", "NOENTRY"]
    scope(database, inside, version)
    before_generations = copy.deepcopy(database._valuation_official_selections)
    receipt = expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert receipt["captured"] == 331  # 329 B3 plus NASDAQ and NYSE; no 300 cap
    assert receipt["markets"]["B3"]["decided"] == 329
    assert receipt["original_capture_receipt"]["markets"]["B3"]["verdicts"][decisor.COMPRA_PERMITIDA] == 327
    assert receipt["original_capture_receipt"]["written"] is False
    assert receipt["original_capture_receipt"]["recorded"] == 0
    assert receipt["original_written"] is False and receipt["original_recorded"] == 0
    assert database._valuation_decisions == []
    assert database._valuation_official_selections == before_generations
    assert receipt["markets"]["B3"]["verdicts"] == {decisor.COMPRA_PERMITIDA: 2, decisor.OBSERVAR: 326, decisor.VETO: 1}
    records = saved(database)["outputs"]["records"]
    assert len(records) == 329
    for record in records:
        assert expanded.stored_guarded_decision(record, population=saved(database)["outputs"]["population"]) == record
        assert record["population"] is not None and "outputs" not in record["population"]
        assert decisor.stored_decision(record["original_decision"]) == record["original_decision"]
        assert record["original_decision"]["thresholds_sha256"] == decisor.thresholds_sha256()
    outside = next(item for item in records if item["symbol"] == symbols[100])
    assert outside["original_decision"]["verdict"] == decisor.COMPRA_PERMITIDA
    assert outside["verdict"] == decisor.OBSERVAR and outside["reason_codes"] == [expanded.PIT_SCOPE_UNVERIFIED]
    permissions = expanded.latest_permissions(database, "B3", symbols + ["BADQUALITY", "NOENTRY"], now=RUN, artifact_verifier=synthetic_verifier)
    assert len(permissions) == 329 and permissions[symbols[-1]]["buy_permission"] is True
    assert sum(item["buy_permission"] for item in permissions.values()) == 2
    assert permissions["BADQUALITY"]["effective_verdict"] == decisor.VETO
    assert permissions["NOENTRY"]["effective_verdict"] == decisor.OBSERVAR
    assert saved(database)["outputs"]["population"]["outputs"]["members"] == inside


@pytest.mark.parametrize("verdict", [None, "FAIL", "VOID", "NEGATIVE"])
def test_missing_or_failed_evidence_never_upgrades_actual_core_permission(world, verdict):
    database, symbols, _, version = world
    if verdict is not None:
        scope(database, symbols, version, verdict=verdict)
    receipt = expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert receipt["original_capture_receipt"]["markets"]["B3"]["verdicts"][decisor.COMPRA_PERMITIDA] == 327
    assert receipt["markets"]["B3"]["verdicts"][decisor.COMPRA_PERMITIDA] == 0
    assert all(not item["buy_permission"] for item in expanded.latest_permissions(database, "B3", symbols, now=RUN, artifact_verifier=synthetic_verifier).values())


def test_default_capture_is_dry_and_never_calls_original_insert(world, monkeypatch):
    database, symbols, _, version = world
    scope(database, symbols, version)
    before = copy.deepcopy(database._analysis_snapshots)

    def no_insert(*args, **kwargs):
        pytest.fail("the original migration 052 insert must never be invoked")

    monkeypatch.setattr(database, "insert_valuation_decisions", no_insert)
    receipt = expanded.run_full_universe_decisions(database, now=RUN)
    assert receipt["status"] == "dry_run" and receipt["written"] is False and receipt["recorded"] == 0
    assert receipt["captured"] > 300 and receipt["snapshot_ids"] == {}
    assert database._analysis_snapshots == before and database._valuation_decisions == []


def test_declared_pass_with_correct_membership_hashes_has_no_permission_without_artifact_verifier(world):
    database, symbols, _, version = world
    scope(database, symbols, version)
    receipt = expanded.run_full_universe_decisions(database, now=RUN, record=True)
    assert receipt["artifact_verifier_configured"] is False and receipt["artifact_attestations"] == 0
    assert receipt["markets"]["B3"]["verdicts"][decisor.COMPRA_PERMITIDA] == 0
    record = next(item for item in saved(database)["outputs"]["records"] if item["symbol"] == symbols[0])
    assert record["original_decision"]["verdict"] == decisor.COMPRA_PERMITIDA
    assert record["reason_codes"] == [expanded.ARTIFACTS_UNATTESTED]
    view = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN)[symbols[0]]
    assert view["pit_population_member"] is True and view["pit_artifacts_attested"] is False
    assert view["buy_permission"] is False


def test_read_requires_new_trusted_attestation_and_json_boolean_cannot_enable_it(world):
    database, symbols, _, version = world
    scope(database, symbols, version)
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert not expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN)[symbols[0]]["buy_permission"]
    for verifier in (lambda *args: True, lambda *args: {"approved_for_buy": True}, lambda *args: {}):
        view = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN, artifact_verifier=verifier)[symbols[0]]
        assert not view["buy_permission"] and view["effective_reason_codes"] == [expanded.ARTIFACTS_UNATTESTED]
    def broken_verifier(*args):
        raise RuntimeError("artifact unavailable")
    assert not expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN,
                                            artifact_verifier=broken_verifier)[symbols[0]]["buy_permission"]


def test_future_population_is_not_read_and_later_pass_does_not_retroactively_upgrade(world):
    database, symbols, _, version = world
    scope(database, symbols, version, at=RUN + timedelta(seconds=1))
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    records = saved(database)["outputs"]["records"]
    assert all(item["population"] is None for item in records)
    views = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(seconds=2), artifact_verifier=synthetic_verifier)
    assert views[symbols[0]]["pit_buy_scope_verified"] is True
    assert views[symbols[0]]["effective_verdict"] == decisor.OBSERVAR and views[symbols[0]]["buy_permission"] is False


@pytest.mark.parametrize("change", [
    {"valid_until": RUN.isoformat()}, {"valid_from": (RUN + timedelta(seconds=1)).isoformat()},
    {"tp_source_version": "another-producer"}, {"approved_for_buy": False}, {"valid_until": None},
    {"population_sha256": "0" * 64},
])
def test_malformed_expired_future_or_other_source_population_denies_buy(world, change):
    database, symbols, _, version = world
    scope(database, symbols, version, **change)
    receipt = expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert receipt["markets"]["B3"]["verdicts"][decisor.COMPRA_PERMITIDA] == 0
    assert not expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN, artifact_verifier=synthetic_verifier)[symbols[0]]["buy_permission"]


def test_current_scope_revocation_expiry_and_session_are_rechecked(world):
    database, symbols, _, version = world
    scope(database, symbols, version, valid_until=(RUN + timedelta(seconds=10)).isoformat())
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN, artifact_verifier=synthetic_verifier)[symbols[0]]["buy_permission"]
    expired = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(seconds=10), artifact_verifier=synthetic_verifier)[symbols[0]]
    assert expired["effective_verdict"] == decisor.OBSERVAR
    assert expired["effective_reason_codes"] == [expanded.PIT_SCOPE_NO_LONGER_VALID]
    scope(database, symbols, version, verdict="FAIL", at=RUN + timedelta(seconds=2))
    revoked = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(seconds=3), artifact_verifier=synthetic_verifier)[symbols[0]]
    assert revoked["buy_permission"] is False
    stale = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(days=2), artifact_verifier=synthetic_verifier)[symbols[0]]
    assert stale["effective_verdict"] == decisor.VETO and decisor.VERDICT_NOT_CURRENT in stale["effective_reason_codes"]


def test_real_source_switch_invalidates_permission_and_causal_read_preserves_earlier_state(world, monkeypatch):
    database, symbols, cycles, version = world
    scope(database, symbols, version)
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    _switch_to_internal(database, cycles, monkeypatch, at=RUN + timedelta(hours=2))
    before = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(hours=1), artifact_verifier=synthetic_verifier)[symbols[0]]
    after = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(hours=3), artifact_verifier=synthetic_verifier)[symbols[0]]
    assert before["buy_permission"] is True
    assert after["buy_permission"] is False and after["effective_verdict"] == decisor.VETO
    assert after["tp_served"] is False and after["tp_source_current"] is False


def test_carried_identical_tp_in_successor_generation_remains_current(world):
    database, symbols, _, version = world
    scope(database, symbols, version)
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    with _activated_at(database, RUN + timedelta(hours=2)):
        database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 32},
                                        {"row": _row("WEGE3", tp=60.0, buy_in=45.0, price=44.0)}, RUN + timedelta(hours=2))
    view = expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN + timedelta(hours=3), artifact_verifier=synthetic_verifier)[symbols[0]]
    assert view["buy_permission"] is True and view["current"] is True


@pytest.mark.parametrize("tamper", ["outer", "original", "meaning", "scope_clock", "generation", "batch"])
def test_tampering_never_serves_permission_even_if_outer_hash_is_recomputed(world, tamper):
    database, symbols, _, version = world
    scope(database, symbols, version)
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    snapshot = saved(database)
    record = snapshot["outputs"]["records"][0]
    if tamper == "outer":
        record["verdict"] = "BUY"
    elif tamper == "original":
        record["original_decision"]["tp"] = 999.0
    elif tamper == "meaning":
        record["verdict"] = decisor.COMPRA_PERMITIDA
        record["pit_buy_scope_verified"] = False
    elif tamper == "scope_clock":
        record["population"]["published_at"] = (RUN + timedelta(seconds=1)).isoformat()
    elif tamper == "generation":
        record["original_decision"]["generation_id"] = "fabricated-generation"
        original = record["original_decision"]
        original["row_sha256"] = official.canonical_sha256({key: value for key, value in original.items() if key not in {"id", "row_sha256"}})
    else:
        snapshot["outputs"]["record_count"] += 1
    if tamper != "outer":
        rehash_record(record)
    rehash_payload(snapshot)
    assert expanded.latest_permissions(database, "B3", [record["symbol"]], now=RUN, artifact_verifier=synthetic_verifier) == {}


def test_future_decision_snapshot_is_ignored_without_falling_back_to_unguarded_052(world):
    database, symbols, _, version = world
    scope(database, symbols, version)
    expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    saved(database)["published_at"] = RUN + timedelta(seconds=1)
    assert expanded.latest_permissions(database, "B3", [symbols[0]], now=RUN, artifact_verifier=synthetic_verifier) == {}


def test_no_official_generation_means_no_decisions_even_with_population_pass():
    database = _database()
    scope(database, ["UNSELECTED"], "source-v1")
    database.save_analysis_snapshot("full_universe_stage", "B3", "mv-test", {},
                                    {"rows": [_row("UNSELECTED", tp=45, buy_in=32, price=30)]}, CUT)
    receipt = expanded.run_full_universe_decisions(database, now=RUN, record=True, artifact_verifier=synthetic_verifier)
    assert receipt["status"] == "no_generation" and receipt["captured"] == 0
    assert receipt["written"] is False and receipt["original_written"] is False
    assert database._valuation_official_selections == [] and database._valuation_decisions == []


def test_capture_proxy_exposes_no_mutator_and_sql_is_select_only(world):
    database, *_ = world
    proxy = expanded._CaptureDatabase(database)
    with pytest.raises(AttributeError):
        proxy.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", "m", {}, {}, RUN)
    with pytest.raises(AttributeError):
        proxy.insert_valuation_official_selection({})
    proxy._valuation_tp_staleness.append({"fake": True})
    assert database._valuation_tp_staleness == []

    class Connection:
        def execute(self, query, parameters):
            return "selected"

    connection = expanded._SelectConnection(Connection())
    assert connection.execute("SELECT to_regclass(%s)", ("table",)) == "selected"
    for query in ("INSERT INTO x VALUES (1)", "SELECT 1; DELETE FROM x", "WITH x AS (DELETE FROM y) SELECT 1"):
        with pytest.raises(ValueError):
            connection.execute(query)
