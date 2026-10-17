"""Passo 1 of the official target price (Valuation Engine V3.2 rev 7, §7.5 item 5 and §7-bis item 4; I-TP4): the
consensus leaves the official TP by a NEW selection line. A second official source (``official_internal_v1``) is
recorded from the SAME producer cycles beside the blend; the selection is source-aware (the automatic pass follows the
selected source); the switch is an explicit order refused while the lock is false and requires the before/after
receipt's hash; the rollback is the same path; consumers are untouched and their stamps say the source; the
before/after receipt aggregates per market and keeps the per-symbol detail private; ``one_pager.py`` stays pinned.
The residuals of the internal adversarial verification (Q1–Q6) are the tests marked "Q", last: the cited hash is checked
against the receipt of the generation in force; the served ``buy_in_models`` are the record's; an unknown source is refused
at write time and served nothing, loudly, at read time; a pre-P1 cycle under an internal head triggers no re-record per
pass; the private detail file is exclusive and owner-only; a switch without ``source_version`` stamps the cycles' versions."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_official as official
from app.config import Settings
from app.database import Database
from app.r2d2_v2_risk_source import ORACLE_ONE_PAGER_SHA256
from app.valuation_accuracy import calls_by_source, load_prediction_calls
from app.valuation_official_engine import OFFICIAL_SOURCES, SOURCE_BLEND, SOURCE_INTERNAL

NOW = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
APP = Path(__file__).resolve().parents[1] / "app"
PRODUCER = "a" * 40  # the deployed revision the producing process reads (C3PO_BUILD_SHA)


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


def _wall() -> datetime:
    """The wall clock, as the automatic path reads it and as the mesa's order carries it (W2) — consecutive instants differ."""
    time.sleep(0.001)
    return datetime.now(timezone.utc)


def _row(symbol: str, *, tp: float, buy_in: float, price: float, internal_tp: float, internal_buy_in: float | None = None, view: bool = True,
         **extra: Any) -> dict[str, Any]:
    """A producer row of Passo 1: the blend (``our_tp``/``buy_in``), the internal TP and — unless omitted, which mimics a
    cycle produced BEFORE Passo 1 — the internal buy-in the producer derived from it; the display fields the producer
    computes over the blend (upside, distance, weight, score, status) travel with the row. With an internal buy-in the row
    carries the producer's INTERNAL VIEW too (rev 9: score/status/expected return on the internal TP, deliberately
    different from the blend's so a test sees which one is served) unless ``view=False`` — a cycle produced by the P1 code
    before rev 9."""
    row: dict[str, Any] = {
        "symbol": symbol, "our_tp": tp, "buy_in": buy_in, "price": price, "internal_tp": internal_tp, "public_consensus_tp": tp * 1.1,
        "analyst_count": 12, "consensus_weight_percent": 25.0, "consensus_origin_source": "brapi", "consensus_as_of": "2026-09-01",
        "methods": {"dcf": tp * 1.01, "multiples": tp * 0.99}, "buy_in_models": {"Bridgewater": buy_in * 1.02, "Market Structure": buy_in * 0.98},
        "calibration_factor": 1.02, "risk_score": 40.0, "valuation_confidence": 70.0, "method_dispersion_percent": 3.0, "signal_quality": "validated",
        "bear_tp": tp * 0.8, "bull_tp": tp * 1.2, "upside_percent": (tp / price - 1) * 100, "price_vs_buy_in_percent": (price / buy_in - 1) * 100,
        "expected_total_return_percent": 21.5, "score": 80.0, "status": "full_match", "as_of": "2026-09-07T22:00:00+00:00",
    }
    if internal_buy_in is not None:
        row["internal_buy_in"] = internal_buy_in
        row["internal_buy_in_models"] = {"Bridgewater": internal_buy_in * 1.02, "Market Structure": buy_in * 0.98}
        if view:
            row.update({"internal_score": 79.0, "internal_status": "near_buy", "internal_expected_total_return_percent": 20.5})
    return {**row, **extra}


def _publish_universe(database: Database, market: str, rows: list[dict[str, Any]], at: datetime, version: int = 7) -> str:
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1",
                                           {"methodology_version": version, "market": market, "source_manifest_sha256": "a" * 64},
                                           {"rows": rows, "universe_size": len(rows) + 1}, at)


def _targeted(database: Database, symbol: str, row: dict[str, Any], at: datetime) -> str:
    return database.save_analysis_snapshot("security_valuation", symbol, "mv-1", {"methodology_version": 7}, {"row": row}, at)


def _three_markets(database: Database, at: datetime = NOW) -> dict[str, str]:
    return {
        "B3": _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0),
                                                 _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0, internal_buy_in=59.0)], at),
        "NASDAQ": _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], at + timedelta(minutes=1)),
        "NYSE": _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], at + timedelta(minutes=2)),
    }


def _authorize(monkeypatch: pytest.MonkeyPatch, report_sha256: str) -> None:
    """The lock commit as it will be merged (rev 9): the lock flipped AND the receipt the owner accepted named beside it."""
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", report_sha256)


def _switch(database: Database, monkeypatch: pytest.MonkeyPatch, *, cycles: dict[str, str], targeted: dict[str, str] | None = None,
            reason: str = "P1 switch") -> tuple[dict[str, Any], dict[str, Any]]:
    """The mesa's order as it will be executed once the lock is flipped by the receipt's commit: the before/after receipt,
    then ``select_generation(source=SOURCE_INTERNAL, before_after_sha256=<its hash>)``. Returns ``(generation, report)``."""
    report = official.before_after_report(database, cycles=cycles, targeted=targeted or {})  # C395-1: the receipt is of THIS proposal
    _authorize(monkeypatch, report["report_sha256"])
    generation = official.select_generation(database, cycles=cycles, targeted=targeted, now=_wall(), activated_by="mesa", reason=reason,
                                            source=SOURCE_INTERNAL, source_version="7", before_after_sha256=report["report_sha256"])
    return generation, report


def test_the_constants_the_lock_and_the_pinned_one_pager() -> None:
    assert official.SOURCE_OFFICIAL == SOURCE_BLEND == "official_blend_v1" and official.SOURCE_INTERNAL == SOURCE_INTERNAL == "official_internal_v1"
    assert OFFICIAL_SOURCES == (SOURCE_BLEND, SOURCE_INTERNAL)
    # the lock is a literal in the module, flipped by THE LOCK COMMIT together with the receipt it names (rev 9): this tree has it
    # TRUE, and the receipt is either the placeholder (the owner has not accepted yet: nothing switches) or the accepted hex-64 hash
    source = (APP / "valuation_official.py").read_text(encoding="utf-8")
    assert official.OFFICIAL_TP_REPLACEMENT_AUTHORIZED is True and "\nOFFICIAL_TP_REPLACEMENT_AUTHORIZED = True" in source
    receipt = official.OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256
    assert official.RECEIPT_PLACEHOLDER == "PENDING-OWNER-ACCEPTANCE" and not official._SHA256.match(official.RECEIPT_PLACEHOLDER)
    assert isinstance(receipt, str) and (receipt == official.RECEIPT_PLACEHOLDER or official._SHA256.match(receipt))
    assert ("\nOFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256: str | None = RECEIPT_PLACEHOLDER" in source
            or f'\nOFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256: str | None = "{receipt}"' in source)
    # the pinned producer framework is not edited by Passo 1 (the mirror of its entry hurdle lives in the engine module)
    assert hashlib.sha256((APP / "one_pager.py").read_bytes()).hexdigest() == ORACLE_ONE_PAGER_SHA256


def test_one_cycle_is_recorded_in_both_official_sources_from_the_same_rows() -> None:
    database = _database()
    row = _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0)
    b3 = _publish_universe(database, "B3", [row], NOW)
    blend = database.valuation_predictions_for_cycle(b3, source=SOURCE_BLEND)["PETR4"]
    internal = database.valuation_predictions_for_cycle(b3, source=SOURCE_INTERNAL)["PETR4"]
    # two records per symbol, distinct identities, the same cycle and clocks and version (the "v1" lives in the source name)
    assert blend["source"] == SOURCE_BLEND and internal["source"] == SOURCE_INTERNAL and blend["row_sha256"] != internal["row_sha256"]
    assert blend["id"] != internal["id"] and blend["cycle_id"] == internal["cycle_id"] == b3 and blend["source_version"] == internal["source_version"] == "7"
    assert blend["prediction_instant"] == internal["prediction_instant"] and blend["published_at"] == internal["published_at"] and blend["session_date"] == internal["session_date"]
    # the blend record is what Passo 0 wrote; the internal record's tp IS the row's internal_tp, its buy-in the row's internal_buy_in, weight 0
    assert blend["tp"] == 40.0 and blend["buy_in"] == 32.0 and blend["consensus_weight_percent"] == 25.0 and blend["decomposition"]["weights"]["consensus_weight_percent"] == 25.0
    assert internal["tp"] == 39.0 == row["internal_tp"] and internal["buy_in"] == 31.0 == row["internal_buy_in"] and internal["internal_tp"] == 39.0
    assert internal["consensus_weight_percent"] == 0.0 and internal["decomposition"]["weights"] == {"calibration_factor": 1.02, "convergence_weight": None, "consensus_weight_percent": 0.0}
    # the consensus is persisted BESIDE, identically (its own identity and hash), as reference — never inside the number (I-TP4)
    assert internal["consensus_tp"] == blend["consensus_tp"] == 44.0 and internal["consensus_source"] == "brapi" and internal["analyst_count"] == 12
    assert internal["decomposition"]["consensus"] == blend["decomposition"]["consensus"] and internal["decomposition"]["consensus"]["payload_sha256"] == blend["decomposition"]["consensus"]["payload_sha256"]
    # methods, calibration and provenance identical; the models are the internal ones; the bands are the producer's INTERNAL bands (none today → null, never rescaled)
    assert internal["decomposition"]["methods"] == blend["decomposition"]["methods"] and internal["decomposition"]["provenance"] == blend["decomposition"]["provenance"]
    assert internal["decomposition"]["buy_in_models"] == {"Bridgewater": 31.0 * 1.02, "Market Structure": 32.0 * 0.98} and blend["decomposition"]["buy_in_models"] == {"Bridgewater": 32.0 * 1.02, "Market Structure": 32.0 * 0.98}
    assert blend["bear_tp"] == 32.0 and blend["bull_tp"] == 48.0 and internal["bear_tp"] is None and internal["bull_tp"] is None
    assert internal["decomposition"]["bands"] == {"bear_tp": None, "bull_tp": None}
    # the internal identity recomputes, the PostgreSQL-shaped reader round-trips it, and the recording is idempotent
    core = {key: value for key, value in internal.items() if key not in ("id", "row_sha256")}
    assert internal["row_sha256"] == official.canonical_sha256(core)
    assert official.record_cycle_predictions(database, database.analysis_snapshot_by_id(b3) or {}) == 0
    assert database.latest_valuation_prediction("B3", "PETR4", source=SOURCE_INTERNAL) == internal
    # a row that names its internal bands and models is recorded with them
    banded = _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0,
                                                        internal_bear_tp=55.0, internal_bull_tp=80.0)], NOW + timedelta(minutes=1))
    ko = database.valuation_prediction_record(banded, "KO", source=SOURCE_INTERNAL)
    assert ko is not None and ko["bear_tp"] == 55.0 and ko["bull_tp"] == 80.0 and ko["decomposition"]["bands"] == {"bear_tp": 55.0, "bull_tp": 80.0}
    # a row without internal models keeps the producer's models in the internal record; an unknown source is refused
    plain = {key: value for key, value in _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0).items() if key != "internal_buy_in_models"}
    record = official.prediction_from_row(plain, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, source=SOURCE_INTERNAL)
    assert record is not None and record["decomposition"]["buy_in_models"] == {"Bridgewater": 200.0 * 1.02, "Market Structure": 200.0 * 0.98}
    with pytest.raises(ValueError, match="unknown recordable source"):  # v3_2_shadow became RECORDABLE (valuation_pit_rerun); an unknown source is still refused
        official.prediction_from_row(plain, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, source="made_up_v9")
    # the recording counts both sources: three rows → six records
    assert official.record_snapshot(database, {"id": "c-six", "analysis_type": "valuation_universe", "entity_key": "NASDAQ_UNIVERSE", "methodology_version_id": "mv-1",
                                               "inputs": {"methodology_version": 7}, "published_at": NOW,
                                               "outputs": {"rows": [_row(s, tp=100.0, buy_in=80.0, price=90.0, internal_tp=98.0, internal_buy_in=78.0) for s in ("A", "B", "C")]}})["recorded"] == 6


def test_a_reader_names_the_source_and_the_cache_is_keyed_by_it() -> None:
    # R1 (proved on the double before this step): a per-cycle reader blind to the source served the internal row under a blend generation
    database = _database()
    cycles = _three_markets(database)
    aapl = cycles["NASDAQ"]
    assert database.valuation_predictions_for_cycle(aapl, source=SOURCE_BLEND)["AAPL"]["tp"] == 250.0
    assert database.valuation_predictions_for_cycle(aapl, source=SOURCE_INTERNAL)["AAPL"]["tp"] == 245.0
    assert database.valuation_prediction_record(aapl, "AAPL", source=SOURCE_BLEND)["buy_in"] == 200.0  # type: ignore[index]
    assert database.valuation_prediction_record(aapl, "AAPL", source=SOURCE_INTERNAL)["buy_in"] == 196.0  # type: ignore[index]
    with pytest.raises(TypeError):
        database.valuation_predictions_for_cycle(aapl)  # type: ignore[call-arg]  # the source is required
    with pytest.raises(TypeError):
        database.valuation_prediction_record(aapl, "AAPL")  # type: ignore[call-arg]
    assert (aapl, SOURCE_BLEND) in database._cycle_records_cache and (aapl, SOURCE_INTERNAL) in database._cycle_records_cache
    # an insert into ONE source invalidates that source's entry only
    late = official.prediction_from_row(_row("MSFT", tp=500.0, buy_in=400.0, price=450.0, internal_tp=490.0, internal_buy_in=392.0), market="NASDAQ", scope="universe",
                                        cycle_id=aapl, source_version="7", prediction_instant=NOW + timedelta(minutes=1), source=SOURCE_INTERNAL)
    assert late is not None and database.insert_valuation_predictions([late]) == 1
    assert (aapl, SOURCE_BLEND) in database._cycle_records_cache and (aapl, SOURCE_INTERNAL) not in database._cycle_records_cache
    assert set(database.valuation_predictions_for_cycle(aapl, source=SOURCE_INTERNAL)) == {"AAPL", "MSFT"} and set(database.valuation_predictions_for_cycle(aapl, source=SOURCE_BLEND)) == {"AAPL"}
    # a blend generation serves the blend records, and the served display identities are bit for bit the producer's own values
    served = official.official_row(database, "US", "AAPL")
    assert served is not None and served["tp_source"] == SOURCE_BLEND and served["our_tp"] == 250.0 and served["buy_in"] == 200.0
    assert served["upside_percent"] == (250.0 / 220.0 - 1) * 100 and served["price_vs_buy_in_percent"] == (220.0 / 200.0 - 1) * 100 and served["consensus_weight_percent"] == 25.0
    assert served["official_row_sha256"] == database.valuation_prediction_record(aapl, "AAPL", source=SOURCE_BLEND)["row_sha256"]  # type: ignore[index]


def test_a_cycle_is_selectable_per_source_and_a_pre_p1_cycle_is_never_selectable_for_the_internal_source(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None and g0["source"] == SOURCE_BLEND
    # a cycle produced before Passo 1 (no internal_buy_in): valid and recorded for the blend, INVALID for the internal source (0 internal records)
    legacy = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], NOW + timedelta(minutes=10))
    assert database.valuation_predictions_for_cycle(legacy, source=SOURCE_INTERNAL) == {} and database.valuation_predictions_for_cycle(legacy, source=SOURCE_BLEND)["KO"]["tp"] == 75.0
    blend_view = official.selectable_cycles(database, source=SOURCE_BLEND)["NYSE"]
    internal_view = official.selectable_cycles(database, source=SOURCE_INTERNAL)["NYSE"]
    assert blend_view["valid"] is True and blend_view["source"] == SOURCE_BLEND and official.current_generation(database)["cycles"]["NYSE"] == legacy  # type: ignore[index]
    assert internal_view["valid"] is False and internal_view["invalid_count"] == 1 and internal_view["invalid_rows"] == ["KO"] and internal_view["source"] == SOURCE_INTERNAL
    # a cycle whose rows are complete but whose internal records were never written: UNRECORDED for the internal source (selection never precedes records)
    pending = {"id": "cycle-blend-only", "analysis_type": "valuation_universe", "entity_key": "NASDAQ_UNIVERSE", "methodology_version_id": "mv-1",
               "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0, internal_buy_in=204.0)], "universe_size": 1},
               "published_at": NOW + timedelta(minutes=11)}
    database._analysis_snapshots.append(pending)
    blend_only = official.prediction_from_row(pending["outputs"]["rows"][0], market="NASDAQ", scope="universe", cycle_id="cycle-blend-only", source_version="7",
                                              prediction_instant=pending["published_at"], source=SOURCE_BLEND)
    assert blend_only is not None and database.insert_valuation_predictions([blend_only]) == 1
    recorded = database.valuation_predictions_for_cycle("cycle-blend-only", source=SOURCE_INTERNAL)
    validation = official.cycle_validation(pending, recorded=recorded, source=SOURCE_INTERNAL)
    assert validation["valid"] is False and validation["invalid_count"] == 0 and validation["unrecorded_count"] == 1
    assert official.cycle_validation(pending, recorded=database.valuation_predictions_for_cycle("cycle-blend-only", source=SOURCE_BLEND), source=SOURCE_BLEND)["valid"] is True
    # the explicit order validates against the records OF THE SOURCE IT SELECTS: the legacy NYSE cycle is refused for the internal source
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    report = official.before_after_report(database)
    with pytest.raises(ValueError, match=f"not complete/valid/recorded for source {SOURCE_INTERNAL}"):
        official.select_generation(database, cycles={**cycles, "NYSE": legacy}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=report["report_sha256"])
    # a targeted cycle produced before Passo 1 named by the order is refused for the internal source too — and admitted for the blend
    wege_legacy = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0), _wall())
    assert official.official_row(database, "B3", "WEGE3")["tp_source"] == SOURCE_BLEND  # type: ignore[index]  # admitted into the blend generation
    report = official.before_after_report(database, cycles=cycles, targeted={})  # the admission moved the head: the order cites the receipt of the generation in force (Q1), computed over the composition it proposes — the legacy targeted cycle purged (C395-1)
    with pytest.raises(ValueError, match=f"targeted cycle for WEGE3 is not complete/valid/recorded for source {SOURCE_INTERNAL}"):
        official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege_legacy}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=report["report_sha256"])
    # the same cycles ARE selectable for the internal source once complete: the order lands (the legacy targeted cycle purged)
    _authorize(monkeypatch, report["report_sha256"])
    switched = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                          source_version="7", before_after_sha256=report["report_sha256"])
    assert switched["source"] == SOURCE_INTERNAL and switched["cycles"] == cycles and official.official_row(database, "B3", "WEGE3") is None


def test_the_switch_is_refused_while_the_lock_is_false_and_without_the_receipt_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    report = official.before_after_report(database)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)  # the lock as it stood before the lock commit
    with pytest.raises(ValueError, match="official_tp_replacement_authorized is false"):
        official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    with pytest.raises(ValueError, match="unknown official source"):
        official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source="v3_2_shadow")
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    for hash_value in (None, "", "abc", "x" * 64, report["report_sha256"].upper()):
        with pytest.raises(ValueError, match="must cite the before/after receipt"):
            official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=hash_value)
    # nothing was written by any refusal: the chain is still G0, served numbers are the blend's
    assert official.current_generation(database) == g0 and len(database._valuation_official_selections) == 1
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    # the rollback path is never locked: the blend can be re-selected with the lock false and no hash
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    rolled = official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="drill", source=official.SOURCE_OFFICIAL)
    assert rolled["source"] == SOURCE_BLEND and "source_switch" not in rolled["receipt"]  # no source changed: a plain rollback


def test_the_switch_by_explicit_order_serves_the_internal_tp_to_every_consumer_with_its_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"WEGE3": wege} and admitted["source"] == SOURCE_BLEND
    before = _wall()
    g1, report = _switch(database, monkeypatch, cycles=cycles, targeted={"WEGE3": wege})
    # a NEW selection line: the same cycles, the internal source, the order's marker and the receipt's hash
    assert g1["source"] == SOURCE_INTERNAL and g1["source_version"] == "7" and g1["cycles"] == cycles and g1["targeted"] == {"WEGE3": wege}
    assert g1["previous_generation_id"] == admitted["generation_id"] and g1["receipt"]["explicit"] is True
    assert g1["receipt"]["source_switch"] == {"from": SOURCE_BLEND, "to": SOURCE_INTERNAL, "before_after_sha256": report["report_sha256"]}
    assert official.current_generation(database) == g1
    internal = database.valuation_prediction_record(cycles["NASDAQ"], "AAPL", source=SOURCE_INTERNAL)
    assert internal is not None
    # One Pager / R2D2 read `official_row`: the internal TP and buy-in, the consensus beside, the stamp names the source
    row = official.official_row(database, "US", "AAPL")
    assert row is not None and row["our_tp"] == 245.0 and row["buy_in"] == 196.0 and row["tp_source"] == SOURCE_INTERNAL and row["tp_source_version"] == "7"
    assert row["generation_id"] == g1["generation_id"] and row["official_cycle_id"] == cycles["NASDAQ"] and row["official_row_sha256"] == internal["row_sha256"]
    assert row["public_consensus_tp"] == 275.0 and row["internal_tp"] == 245.0 and row["consensus_weight_percent"] == 0.0
    assert row["upside_percent"] == (245.0 / 220.0 - 1) * 100 and row["price_vs_buy_in_percent"] == (220.0 / 196.0 - 1) * 100
    # rev 9 (the residue closed): the status, score and expected return served are the producer's INTERNAL view, never the blend's
    assert row["score"] == 79.0 and row["status"] == "near_buy" and row["expected_total_return_percent"] == 20.5
    assert official.official_row(database, "US", "AAPL", generation=admitted)["status"] == "full_match"  # type: ignore[index]  # the blend generation: the blend's, as before
    # the screeners read `official_rows` / `official_stamp` / `item_stamp`
    rows = official.official_rows(database, "B3")
    assert {symbol: item["our_tp"] for symbol, item in rows.items()} == {"PETR4": 39.0, "VALE3": 69.0} and all(item["tp_source"] == SOURCE_INTERNAL for item in rows.values())
    assert official.item_stamp(rows["PETR4"]) == {"tp_source": SOURCE_INTERNAL, "official_generation_id": g1["generation_id"], "official_cycle_id": cycles["B3"],
                                                  "tp_source_version": "7", "official_session_date": "2026-09-04", "prediction_instant": NOW.isoformat(),
                                                  "official_row_sha256": rows["PETR4"]["official_row_sha256"], "official_published_at": NOW.isoformat()}
    assert official.official_stamp(database, "NASDAQ") == {"tp_source": SOURCE_INTERNAL, "tp_source_version": "7", "official_generation_id": g1["generation_id"],
                                                           "official_cycle_id": cycles["NASDAQ"], "official_session_date": "2026-09-04"}
    # the targeted admission carried by the order is served from ITS internal record
    targeted = official.official_row(database, "B3", "WEGE3")
    assert targeted is not None and targeted["our_tp"] == 49.0 and targeted["buy_in"] == 41.0 and targeted["official_scope"] == "targeted" and targeted["tp_source"] == SOURCE_INTERNAL
    # the studies' arm and the health follow the generation's source; a study replaying a decision taken BEFORE the switch still sees the blend
    snapshot = official.official_prediction_snapshot(database, "B3")
    assert snapshot is not None and snapshot["outputs"]["source"] == SOURCE_INTERNAL and snapshot["outputs"]["results"]["PETR4"]["tp"] == 39.0
    assert snapshot["outputs"]["results"]["WEGE3"]["tp"] == 49.0 and snapshot["outputs"]["targeted_cycles"] == {"WEGE3": wege}
    assert official.selection_health(database, now=_wall())["source"] == SOURCE_INTERNAL
    past = official.generation_at(database, before)
    assert past is not None and past["generation_id"] == admitted["generation_id"]
    assert official.official_row(database, "US", "AAPL", generation=past)["our_tp"] == 250.0  # type: ignore[index]
    assert official.official_prediction_snapshot(database, "NASDAQ", generation=past)["outputs"]["results"]["AAPL"]["tp"] == 250.0  # type: ignore[index]
    # grading by source: the internal records are calls of their own producer/version, the blend's remain readable
    calls = load_prediction_calls(official.prediction_records(database, "US", "AAPL", source=SOURCE_INTERNAL))
    assert [call.target_price for call in calls] == [245.0] and list(calls_by_source(calls)) == [f"{SOURCE_INTERNAL}:7"]
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=SOURCE_BLEND)["tp"] == 250.0  # type: ignore[index]


def test_the_rollback_to_the_blend_is_the_same_path_never_locked_and_survives_the_automatic_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    g1, _ = _switch(database, monkeypatch, cycles=cycles)
    assert official.official_row(database, "US", "AAPL")["tp_source"] == SOURCE_INTERNAL  # type: ignore[index]
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)  # the lock as committed: the rollback does not need it
    g2 = official.select_generation(database, cycles=g0["cycles"], now=_wall(), activated_by="mesa", reason="rollback to the blend", source=official.SOURCE_OFFICIAL)
    assert g2["source"] == SOURCE_BLEND and g2["cycles"] == g0["cycles"] and g2["previous_generation_id"] == g1["generation_id"]
    assert g2["receipt"]["explicit"] is True and g2["receipt"]["source_switch"] == {"from": SOURCE_INTERNAL, "to": SOURCE_BLEND, "before_after_sha256": None}
    row = official.official_row(database, "US", "AAPL")
    assert row is not None and row["our_tp"] == 250.0 and row["buy_in"] == 200.0 and row["tp_source"] == SOURCE_BLEND and row["consensus_weight_percent"] == 25.0
    assert official.official_stamp(database, "B3")["tp_source"] == SOURCE_BLEND and official.selection_health(database, now=_wall())["source"] == SOURCE_BLEND
    # nothing is deleted: both earlier generations and both sources' records stay readable
    assert database.valuation_official_selection(g1["generation_id"]) == g1 and database.valuation_official_selection(g0["generation_id"]) == g0
    assert official.official_row(database, "US", "AAPL", generation=g1)["our_tp"] == 245.0  # type: ignore[index]
    # the automatic pass and the bootstrap keep the rollback (the order stands over the cycles predicted before it, W1)
    assert official.activate_generation_if_changed(database) is None
    assert official.bootstrap_official_selection(database)["generation"] == g2 and official.current_generation(database) == g2


def test_the_automatic_pass_after_the_switch_keeps_following_the_selected_source(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    database = _database()
    cycles = _three_markets(database)
    g1, _ = _switch(database, monkeypatch, cycles=cycles)
    assert official.activate_generation_if_changed(database) is None and official.current_generation(database) == g1  # the pass never undoes the switch
    # a new cycle WITH internal records (produced by Passo 1 code) is a new INTERNAL generation
    nyse_new = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0, internal_buy_in=62.0)], _wall())
    g2 = official.current_generation(database)
    assert g2 is not None and g2["source"] == SOURCE_INTERNAL and g2["previous_generation_id"] == g1["generation_id"] and g2["cycles"] == {**cycles, "NYSE": nyse_new}
    assert g2["receipt"]["changed_markets"] == ["NYSE"] and g2["receipt"]["source"] == SOURCE_INTERNAL and g2["receipt"]["validation"]["NYSE"]["source"] == SOURCE_INTERNAL
    assert g2["activated_by"] == official.ACTIVATED_BY and "explicit" not in g2["receipt"]
    ko = official.official_row(database, "NYSE", "KO")
    assert ko is not None and ko["our_tp"] == 74.0 and ko["buy_in"] == 62.0 and ko["tp_source"] == SOURCE_INTERNAL and ko["generation_id"] == g2["generation_id"]
    # a new cycle WITHOUT internal records (pre-Passo 1 shape) is not selectable for the internal source: carry-over, the served number stands
    nasdaq_legacy = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())
    assert official.current_generation(database) == g2 and official.official_row(database, "US", "AAPL")["our_tp"] == 245.0  # type: ignore[index]
    assert official.selectable_cycles(database, source=SOURCE_INTERNAL)["NASDAQ"]["valid"] is False and official.selectable_cycles(database, source=SOURCE_BLEND)["NASDAQ"]["valid"] is True
    assert official.selectable_cycles(database, source=SOURCE_INTERNAL)["NASDAQ"]["cycle_id"] == nasdaq_legacy
    assert official.bootstrap_official_selection(database)["generation"] == g2
    # a targeted cycle published after the switch: admitted when it carries internal records, refused (not admitted) when it does not
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    itub = _targeted(database, "ITUB4", _row("ITUB4", tp=30.0, buy_in=25.0, price=27.0, internal_tp=29.0), _wall())
    assert official.current_generation(database) == g2 and official.official_row(database, "B3", "ITUB4") is None
    assert any(f"targeted cycle {itub} for ITUB4 refused" in message for message in caplog.messages)
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    g3 = official.current_generation(database)
    assert g3 is not None and g3["source"] == SOURCE_INTERNAL and g3["targeted"] == {"WEGE3": wege} and g3["receipt"]["targeted_admission"]["validation"]["source"] == SOURCE_INTERNAL
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 49.0 and official.official_row(database, "B3", "WEGE3")["tp_source"] == SOURCE_INTERNAL  # type: ignore[index]
    # ...and the recovery pass of the next activation reads the internal source too: a re-run of ITUB4 with internal records is recovered
    itub_ok = _targeted(database, "ITUB4", _row("ITUB4", tp=31.0, buy_in=26.0, price=27.0, internal_tp=30.0, internal_buy_in=25.0), _wall())
    assert official.current_generation(database)["targeted"] == {"ITUB4": itub_ok, "WEGE3": wege}  # type: ignore[index]
    assert official.official_row(database, "B3", "ITUB4")["our_tp"] == 30.0  # type: ignore[index]


def test_the_before_after_report_aggregates_per_market_and_keeps_the_detail_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    database = _database()
    with pytest.raises(ValueError, match="no official generation"):
        official.before_after_report(database)
    b3 = _publish_universe(database, "B3", [
        _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0),   # tp −2.5 %, buy-in −3.125 %
        _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0, internal_buy_in=59.0),   # tp −1/70, buy-in −1/60
        _row("ITUB4", tp=30.0, buy_in=25.0, price=27.0, internal_tp=33.0, internal_buy_in=27.5),   # tp +10 %, buy-in +10 %
        _row("BBDC4", tp=20.0, buy_in=16.0, price=18.0, internal_tp=19.0),                          # no internal buy-in: missing in the internal source
    ], NOW)
    nasdaq = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], NOW + timedelta(minutes=1))
    nyse = _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], NOW + timedelta(minutes=2))
    generation = official.current_generation(database)
    assert generation is not None
    detail_path = tmp_path / "private" / "detail.json"
    detail_path.parent.mkdir()
    report = official.before_after_report(database, private_detail_path=detail_path)
    assert report["schema"] == "VALUATION_P1_BEFORE_AFTER_V3" and report["generation_id"] == generation["generation_id"] and report["generation_source"] == SOURCE_BLEND
    assert report["buy_status"] == official.BUY_STATUS == "full_match"
    assert report["rating_cuts"] == {"COMPRA": 25.0, "ACUMULAR": 10.0, "NEUTRO": -10.0, "REDUZIR": None}  # F3: the cuts the ratings were read with
    assert report["source_from"] == SOURCE_BLEND and report["source_to"] == SOURCE_INTERNAL and report["cycles"] == {"B3": b3, "NASDAQ": nasdaq, "NYSE": nyse}
    assert report["session_dates"] == {"B3": "2026-09-04", "NASDAQ": "2026-09-04", "NYSE": "2026-09-04"} and report["source_version"] == "7" and report["targeted_cycles"] == 0
    assert report["p90_method"] == "linear interpolation at (n-1)*0.9"
    b3_stats = report["markets"]["B3"]
    assert b3_stats["n"] == 3 and b3_stats["missing_internal"] == 1
    tp_ratios = sorted([-0.025, 69.0 / 70.0 - 1, 0.1])  # by hand: median = the middle one; p90 at position 1.8 = 0.2 × r[1] + 0.8 × r[2]
    assert b3_stats["tp"]["median"] == pytest.approx(tp_ratios[1]) and b3_stats["tp"]["p90"] == pytest.approx(0.2 * tp_ratios[1] + 0.8 * tp_ratios[2])
    assert b3_stats["tp"]["abs_median"] == pytest.approx(0.025) and b3_stats["tp"]["abs_p90"] == pytest.approx(0.2 * 0.025 + 0.8 * 0.1)
    buy_in_ratios = sorted([31.0 / 32.0 - 1, 59.0 / 60.0 - 1, 27.5 / 25.0 - 1])
    assert b3_stats["buy_in"]["median"] == pytest.approx(buy_in_ratios[1]) and b3_stats["buy_in"]["p90"] == pytest.approx(0.2 * buy_in_ratios[1] + 0.8 * buy_in_ratios[2])
    minus_two = {"median": pytest.approx(-0.02), "p10": pytest.approx(-0.02), "p90": pytest.approx(-0.02), "abs_median": pytest.approx(0.02), "abs_p90": pytest.approx(0.02)}
    upside_before, upside_after = (250.0 / 220.0 - 1) * 100, (245.0 / 220.0 - 1) * 100  # the served identities of each arm
    assert report["markets"]["NASDAQ"] == {
        "n": 1, "missing_internal": 0, "only_internal": 0, "served_pairs": 1, "before_unservable": 0, "after_unservable": 0,
        "tp": minus_two, "buy_in": minus_two,
        "tp_change_buckets": {"down": 1, "flat": 0, "up": 0, "abs": {"lt_1pct": 0, "1_to_5pct": 1, "5_to_10pct": 0, "10_to_25pct": 0, "ge_25pct": 0}},
        # rev 9 (V3): the SERVED view of both arms — the blend row's status/score, the internal record under the producer's internal view
        "status": {"before": {"full_match": 1}, "after": {"near_buy": 1}, "changed": 1, "transitions": {"full_match->near_buy": 1}},
        "rating": {"before": {"ACUMULAR": 1}, "after": {"ACUMULAR": 1}, "changed": 0, "transitions": {}},  # F3: the One Pager rating, +13,6 % and +11,4 %
        "buy": {"status": "full_match", "before": 1, "after": 0, "entered": 0, "left": 1},
        "upside_percent": {"before": {key: pytest.approx(upside_before) for key in ("p10", "p25", "median", "p75", "p90")},
                           "after": {key: pytest.approx(upside_after) for key in ("p10", "p25", "median", "p75", "p90")},
                           "change_pp": {"median": pytest.approx(upside_after - upside_before), "p10": pytest.approx(upside_after - upside_before),
                                         "p90": pytest.approx(upside_after - upside_before), "abs_median": pytest.approx(upside_before - upside_after),
                                         "abs_p90": pytest.approx(upside_before - upside_after)}},
        "score_change": {"median": -1.0, "p10": -1.0, "p90": -1.0, "abs_median": 1.0, "abs_p90": 1.0},
        "tp_validation": None,  # the US rows carry no TP validation
    }
    assert report["markets"]["B3"]["status"] == {"before": {"full_match": 3}, "after": {"near_buy": 3}, "changed": 3, "transitions": {"full_match->near_buy": 3}}
    assert report["markets"]["B3"]["buy"] == {"status": "full_match", "before": 3, "after": 0, "entered": 0, "left": 3} and report["markets"]["B3"]["served_pairs"] == 3
    assert report["markets"]["B3"]["tp_change_buckets"] == {"down": 2, "flat": 0, "up": 1, "abs": {"lt_1pct": 0, "1_to_5pct": 2, "5_to_10pct": 0, "10_to_25pct": 1, "ge_25pct": 0}}
    assert report["markets"]["NYSE"]["n"] == 1 and report["markets"]["NYSE"]["tp"]["median"] == pytest.approx(68.0 / 70.0 - 1)
    # the aggregate names no symbol; its hash is the canonical hash of everything but itself, and it is stable
    printable = json.dumps(report, sort_keys=True)
    assert not any(symbol in printable for symbol in ("PETR4", "VALE3", "ITUB4", "BBDC4", "AAPL", "KO"))
    assert report["report_sha256"] == official.canonical_sha256({key: value for key, value in report.items() if key != "report_sha256"}) and len(report["report_sha256"]) == 64
    assert official.before_after_report(database) == report
    # the detail exists only in the private file, named symbol by symbol, and its bytes hash to the aggregate's private_detail_sha256
    assert hashlib.sha256(detail_path.read_bytes()).hexdigest() == report["private_detail_sha256"]
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["schema"] == "VALUATION_P1_BEFORE_AFTER_V3_DETAIL" and detail["generation_id"] == generation["generation_id"]
    assert detail["markets"]["B3"]["missing_internal"] == ["BBDC4"] and set(detail["markets"]["B3"]["pairs"]) == {"PETR4", "VALE3", "ITUB4"}
    assert detail["markets"]["B3"]["only_internal"] == []
    assert detail["markets"]["B3"]["pairs"]["ITUB4"] == {"tp_blend": 30.0, "tp_internal": 33.0, "tp_ratio": pytest.approx(0.1), "buy_in_blend": 25.0, "buy_in_internal": 27.5,
                                                         "buy_in_ratio": pytest.approx(0.1), "status_blend": "full_match", "status_internal": "near_buy",
                                                         "upside_blend": pytest.approx((30.0 / 27.0 - 1) * 100), "upside_internal": pytest.approx((33.0 / 27.0 - 1) * 100),
                                                         "score_blend": 80.0, "score_internal": 79.0, "validated_blend": False, "validated_internal": False,
                                                         "rating_blend": "ACUMULAR", "rating_internal": "ACUMULAR"}
    # a market with NO pair reports n = 0 and null statistics (never a fabricated number)
    empty = _database()
    _publish_universe(empty, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], NOW)
    _publish_universe(empty, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], NOW + timedelta(minutes=1))
    _publish_universe(empty, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], NOW + timedelta(minutes=2))
    null_stats = {"median": None, "p10": None, "p90": None, "abs_median": None, "abs_p90": None}
    null_quantiles = {"p10": None, "p25": None, "median": None, "p75": None, "p90": None}
    assert official.before_after_report(empty)["markets"]["B3"] == {
        "n": 0, "missing_internal": 1, "only_internal": 0, "served_pairs": 0, "before_unservable": 0, "after_unservable": 0, "tp": null_stats, "buy_in": null_stats,
        "tp_change_buckets": {"down": 0, "flat": 0, "up": 0, "abs": {"lt_1pct": 0, "1_to_5pct": 0, "5_to_10pct": 0, "10_to_25pct": 0, "ge_25pct": 0}},
        "status": {"before": {}, "after": {}, "changed": 0, "transitions": {}}, "rating": {"before": {}, "after": {}, "changed": 0, "transitions": {}},
        "buy": {"status": "full_match", "before": 0, "after": 0, "entered": 0, "left": 0},
        "upside_percent": {"before": null_quantiles, "after": null_quantiles, "change_pp": null_stats}, "score_change": null_stats, "tp_validation": None,
    }
    # the CLI prints the aggregate only; the detail goes to --private-detail; --private-detail alone is refused
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    monkeypatch.setenv("C3PO_BUILD_SHA", PRODUCER)
    cli_detail = tmp_path / "cli_detail.json"
    assert official.main(["--before-after", "--private-detail", str(cli_detail)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(json.dumps(official.attest_before_after(report, producer_build_sha=PRODUCER))) and "PETR4" not in json.dumps(printed) and cli_detail.read_bytes() == detail_path.read_bytes()
    with pytest.raises(SystemExit):
        official.main(["--private-detail", str(cli_detail)])
    # the CLI publishes the receipt of a PROPOSAL too (C395-1): --cycles overlays the head's cycles, --targeted/--purge-targeted set the admissions,
    # --source-version the declared version; each equals the library call the order recomputes
    assert official.main(["--before-after", "--purge-targeted"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(official.attest_before_after(
        official.before_after_report(database, cycles=generation["cycles"], targeted={}), producer_build_sha=PRODUCER)))
    assert official.main(["--before-after", "--cycles", f"B3={b3}", "--source-version", "9"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(official.attest_before_after(
        official.before_after_report(database, cycles={**generation["cycles"], "B3": b3}, targeted={}, source_version="9"), producer_build_sha=PRODUCER)))
    for argv in (["--cycles", f"B3={b3}"], ["--before-after", "--targeted", "WEGE3=x", "--purge-targeted"], ["--before-after", "--cycles", "B3"],
                 ["--before-after", "--cycles", "B33=nonexistent-cycle"], ["--before-after", "--cycles", f"B3={b3}", "--cycles", f"B3={b3}"],
                 ["--before-after", "--targeted", "WEGE3=x", "--targeted", "wege3=y"]):  # unknown market / twice (case-insensitive): refused, never ignored
        with pytest.raises(SystemExit):
            official.main(argv)
    # a generation with a row missing in the internal source (BBDC4) cannot be switched — the receipt says so (`missing_internal`) and the order is refused
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    with pytest.raises(ValueError, match=f"cycle for B3 is not complete/valid/recorded for source {SOURCE_INTERNAL}"):
        official.select_generation(database, cycles=generation["cycles"], now=_wall(), activated_by="mesa", reason="P1", source=SOURCE_INTERNAL, source_version="7",
                                   before_after_sha256=report["report_sha256"])
    # on a complete generation the switch cites this hash (the receipt of the mesa) and the generation carries it; the comparison stays internal vs blend
    complete = _database()
    complete_cycles = _three_markets(complete)
    complete_report = official.before_after_report(complete)
    assert all(item["missing_internal"] == 0 for item in complete_report["markets"].values())
    _authorize(monkeypatch, complete_report["report_sha256"])
    switched = official.select_generation(complete, cycles=complete_cycles, now=_wall(), activated_by="mesa", reason="P1", source=SOURCE_INTERNAL, source_version="7",
                                          before_after_sha256=complete_report["report_sha256"])
    assert switched["receipt"]["source_switch"]["before_after_sha256"] == complete_report["report_sha256"]
    after = official.before_after_report(complete)
    assert after["generation_source"] == SOURCE_INTERNAL and after["source_from"] == SOURCE_BLEND and after["source_to"] == SOURCE_INTERNAL
    assert after["markets"] == complete_report["markets"] and after["generation_id"] == switched["generation_id"]


# ------------------------------------------------------------------------------------- P1 residuals (Q1–Q6), adversarial verification


def test_q1_the_switch_must_cite_the_receipt_of_the_generation_in_force_not_any_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    # Q1: any well-formed hex-64 landed the switch. Now the receipt is recomputed on the head read in the same attempt and the
    # cited hash must be ITS report_sha256: a bogus hex, or the receipt of a generation the chain moved past, is refused by name.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    report_g0 = official.before_after_report(database)
    assert report_g0 == official.before_after_report(database, generation=g0)  # deterministic: no clock inside the hashed aggregate
    for bogus in ("0" * 64, "a" * 64, hashlib.sha256(b"not the receipt").hexdigest()):
        with pytest.raises(ValueError, match="does not match its report_sha256") as refused:
            official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=bogus)
        assert bogus[:12] in str(refused.value) and report_g0["report_sha256"][:12] in str(refused.value) and g0["generation_id"] in str(refused.value)
    assert official.current_generation(database) == g0 and len(database._valuation_official_selections) == 1  # nothing written
    # the head moves (a targeted admission): the receipt the mesa read on G0 is a receipt of ANOTHER generation — refused
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    g1 = official.current_generation(database)
    assert g1 is not None and g1["targeted"] == {"WEGE3": wege} and g1["generation_id"] != g0["generation_id"]
    with pytest.raises(ValueError, match=f"receipt of the generation in force \\({g1['generation_id']}\\)"):
        official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=report_g0["report_sha256"])
    assert official.before_after_report(database, generation=g0) == report_g0  # G0's receipt still recomputes: it is simply not the head's
    # the receipt of the head is accepted, and the generation carries exactly that hash
    report_g1 = official.before_after_report(database)
    assert report_g1["report_sha256"] != report_g0["report_sha256"] and report_g1["generation_id"] == g1["generation_id"] and report_g1["targeted_cycles"] == 1
    _authorize(monkeypatch, report_g1["report_sha256"])
    switched = official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                          before_after_sha256=report_g1["report_sha256"])
    assert switched["source"] == SOURCE_INTERNAL and switched["receipt"]["source_switch"]["before_after_sha256"] == report_g1["report_sha256"]
    # without a generation in force there is no "before": a switch is refused before anything else is read
    empty = _database()
    with pytest.raises(ValueError, match="requires a generation in force"):
        official.select_generation(empty, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report_g1["report_sha256"])
    assert empty._valuation_official_selections == []


def test_q2_the_served_buy_in_models_are_the_records_after_the_switch_and_the_blends_bit_for_bit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Q2: after the switch `_served` overlaid our_tp/buy_in/upside/distance but left `buy_in_models` from the blend row — the
    # models shown beside the internal buy-in were the blend's. Now the record's decomposition.buy_in_models are served.
    database = _database()
    cycles = _three_markets(database)
    row = _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0)
    blend_record = database.valuation_prediction_record(cycles["B3"], "PETR4", source=SOURCE_BLEND)
    internal_record = database.valuation_prediction_record(cycles["B3"], "PETR4", source=SOURCE_INTERNAL)
    assert blend_record is not None and internal_record is not None
    # a blend generation: the served models are the row's own values, bit for bit (they are what the blend record stored)
    served = official.official_row(database, "B3", "PETR4")
    assert served is not None and served["buy_in_models"] == row["buy_in_models"] == {"Bridgewater": 32.0 * 1.02, "Market Structure": 32.0 * 0.98}
    assert served["buy_in_models"] == blend_record["decomposition"]["buy_in_models"]
    assert all(type(served["buy_in_models"][key]) is type(row["buy_in_models"][key]) for key in row["buy_in_models"])
    assert official.official_rows(database, "B3")["PETR4"]["buy_in_models"] == row["buy_in_models"]
    # after the switch: the internal record's models (the producer's internal_buy_in_models), the blend's gone from the served row
    g1, _ = _switch(database, monkeypatch, cycles=cycles)
    served = official.official_row(database, "B3", "PETR4")
    assert served is not None and served["tp_source"] == SOURCE_INTERNAL and served["buy_in"] == 31.0
    assert served["buy_in_models"] == row["internal_buy_in_models"] == {"Bridgewater": 31.0 * 1.02, "Market Structure": 32.0 * 0.98}
    assert served["buy_in_models"] == internal_record["decomposition"]["buy_in_models"] and served["buy_in_models"] != row["buy_in_models"]
    assert official.official_rows(database, "B3")["PETR4"]["buy_in_models"] == row["internal_buy_in_models"]
    # the served map is a copy: mutating it reaches neither the record cache nor the store
    served["buy_in_models"]["Bridgewater"] = 0.0
    assert official.official_row(database, "B3", "PETR4")["buy_in_models"]["Bridgewater"] == 31.0 * 1.02  # type: ignore[index]
    assert database.valuation_prediction_record(cycles["B3"], "PETR4", source=SOURCE_INTERNAL) == internal_record
    # a record WITHOUT models (a producer that emits none) leaves the row's field untouched; a targeted admission is served from ITS record
    nyse_plain = _publish_universe(database, "NYSE", [{key: value for key, value in _row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0, internal_buy_in=62.0).items()
                                                        if key not in ("buy_in_models", "internal_buy_in_models")}], _wall())
    assert official.current_generation(database)["cycles"]["NYSE"] == nyse_plain  # type: ignore[index]
    ko = official.official_row(database, "NYSE", "KO")
    assert ko is not None and "buy_in_models" not in ko and database.valuation_prediction_record(nyse_plain, "KO", source=SOURCE_INTERNAL)["decomposition"]["buy_in_models"] == {}  # type: ignore[index]
    wege_row = _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0)
    _targeted(database, "WEGE3", wege_row, _wall())
    wege = official.official_row(database, "B3", "WEGE3")
    assert wege is not None and wege["official_scope"] == "targeted" and wege["buy_in_models"] == wege_row["internal_buy_in_models"] != wege_row["buy_in_models"]


def test_q3_an_unknown_source_is_refused_at_write_time_and_served_nothing_loudly_at_read_time(caplog: pytest.LogCaptureFixture) -> None:
    # Q3: `_selected_source` did not validate the head's source — an unknown one silently served nothing. Now the writers refuse
    # it (nothing stored) and a head that carries one anyway (a hand edit) is not servable, with an ERROR and the health saying so.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    # write time: the storage layer and _new_generation both refuse, before anything is stored
    with pytest.raises(ValueError, match="is not an official source"):
        database.insert_valuation_official_selection({**g0, "generation_id": "bad-source", "source": "v3_2_shadow", "previous_generation_id": g0["generation_id"],
                                                      "activated_at": _wall().isoformat()})
    for bad in ("v3_2_shadow", "", None):
        with pytest.raises(ValueError, match="unknown official source"):
            official._new_generation(database, expected_previous=g0["generation_id"], cycles=g0["cycles"], targeted={}, source=bad,  # type: ignore[arg-type]
                                     source_version="7", session_dates=g0["session_dates"], activated_by="t", receipt={})
    assert official.current_generation(database) == g0 and len(database._valuation_official_selections) == 1
    # read time: a head with an unknown source (planted in the store, as a hand edit of the row would)
    corrupt = {**g0, "generation_id": "hand-edited", "source": "v3_2_shadow", "previous_generation_id": g0["generation_id"],
               "activated_at": (official._utc(g0["activated_at"]) + timedelta(microseconds=1)).isoformat()}
    database._valuation_official_selections.append(corrupt)
    database.drop_official_cycle_cache()
    assert official.current_generation(database) == corrupt
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    assert official.official_row(database, "US", "AAPL") is None and official.official_rows(database, "B3") == {} and official.official_prediction_snapshot(database, "B3") is None
    assert official.official_row(database, "B3", "PETR4", generation=g0)["our_tp"] == 40.0  # type: ignore[index]  # an earlier known generation still serves
    errors = [record for record in caplog.records if "selects an UNKNOWN source 'v3_2_shadow'" in record.getMessage()]
    assert len(errors) == 3 and {record.levelno for record in errors} == {logging.ERROR} and all("hand-edited" in record.getMessage() for record in errors)
    # the automatic pass and the direct admission activate NOTHING under it — never a blend generation composed over the corrupt head
    nyse_new = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0, internal_buy_in=62.0)], _wall())
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    assert official.activate_generation_if_changed(database) is None and official.admit_targeted_cycle(database, symbol="WEGE3", cycle_id=wege) is None
    assert official.bootstrap_official_selection(database)["generation"] == corrupt and official.current_generation(database) == corrupt
    assert database.valuation_predictions_for_cycle(nyse_new, source=SOURCE_BLEND)["KO"]["tp"] == 75.0  # the records were still written (records first)
    health = official.selection_health(database, now=_wall())
    assert health["status"] == "error" and health["source"] is None and health["unknown_source"] == "v3_2_shadow" and "UNKNOWN source 'v3_2_shadow'" in health["detail"]
    with pytest.raises(ValueError, match="selects an unknown source 'v3_2_shadow'"):
        official.before_after_report(database)
    assert official.official_stamp(database, "B3")["tp_source"] == "v3_2_shadow"  # the stamp reports the row as stored: nothing is served with it
    # the way out: the explicit rollback to the blend, never locked, no hash — the receipt names the unknown source it left
    rolled = official.select_generation(database, cycles={**g0["cycles"], "NYSE": nyse_new}, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="repair")
    assert rolled["source"] == SOURCE_BLEND and rolled["previous_generation_id"] == "hand-edited"
    assert rolled["receipt"]["source_switch"] == {"from": "v3_2_shadow", "to": SOURCE_BLEND, "before_after_sha256": None}
    assert official.official_row(database, "NYSE", "KO")["our_tp"] == 75.0 and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]
    # C395-2: the freshness is measured against a CONTROLLED clock, never the real one: at NOW + 1 h no market's session is behind
    # (B3/NASDAQ published at NOW; the NYSE re-run at _wall() is at or after it) — the real wall clock would make the head "stale"
    # two sessions after the fixture date; the rule is unchanged
    fixed = NOW + timedelta(hours=1)
    assert official.selection_health(database, now=fixed)["status"] == "ok" and official.selection_health(database, now=fixed)["unknown_source"] is None
    assert official.selection_health(_database(), now=fixed)["unknown_source"] is None  # every key explicit, without a generation too


def test_q4_a_pre_p1_cycle_under_an_internal_head_triggers_no_re_record_on_every_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    # Q4: under an internal head a newer pre-P1 cycle (rows without internal_buy_in) has 0 internal records, so every automatic
    # pass re-recorded it: N no-op inserts per pass, forever. Now the re-record needs at least one row usable for the source.
    database = _database()
    cycles = _three_markets(database)
    _switch(database, monkeypatch, cycles=cycles)
    inserts: list[int] = []
    original = database.insert_valuation_predictions

    def counted(records: list[dict[str, Any]]) -> int:
        inserts.append(len(records))
        return original(records)

    monkeypatch.setattr(database, "insert_valuation_predictions", counted)
    nasdaq_legacy = _publish_universe(database, "NASDAQ", [_row(symbol, tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0) for symbol in ("AAPL", "MSFT", "NVDA")], _wall())
    assert inserts == [3]  # the publication itself: three blend records (no internal row is recordable), then the activation pass — no re-record
    inserts.clear()
    for _ in range(3):
        assert official.activate_generation_if_changed(database) is None
    assert inserts == []  # three passes, zero inserts (before: 3 × N no-op inserts)
    nasdaq_view = official.selectable_cycles(database, source=SOURCE_INTERNAL)["NASDAQ"]
    assert nasdaq_view["cycle_id"] == nasdaq_legacy and nasdaq_view["valid"] is False and nasdaq_view["invalid_count"] == 3 and nasdaq_view["unrecorded_count"] == 0
    assert inserts == []  # selectable_cycles itself attempted nothing either
    assert official.bootstrap_official_selection(database)["recorded"] == {"B3": 0, "NASDAQ": 0, "NYSE": 0}
    inserts.clear()
    # the X4 recovery is intact: a latest cycle with usable rows and NO record of the selected source is recorded ONCE, then never again
    pending = {"id": "cycle-unrecorded", "analysis_type": "valuation_universe", "entity_key": "NYSE_UNIVERSE", "methodology_version_id": "mv-1",
               "inputs": {"methodology_version": 7}, "published_at": _wall(),
               "outputs": {"rows": [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0, internal_buy_in=62.0)], "universe_size": 1}}
    database._analysis_snapshots.append(pending)
    assert official.activate_generation_if_changed(database)["cycles"]["NYSE"] == "cycle-unrecorded"  # type: ignore[index]
    assert inserts == [2]  # one insert, both sources, at selection time
    for _ in range(3):
        assert official.activate_generation_if_changed(database) is None
    assert inserts == [2]


def test_q5_the_private_detail_file_is_created_exclusively_with_owner_only_permissions(tmp_path: Path) -> None:
    # Q5: the detail was written with Path.write_text — umask-wide permissions, symlinks followed, an existing file overwritten.
    database = _database()
    _three_markets(database)
    target = tmp_path / "detail.json"
    report = official.before_after_report(database, private_detail_path=target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600 and hashlib.sha256(target.read_bytes()).hexdigest() == report["private_detail_sha256"]
    # a second write to the same path is refused and the bytes are untouched
    before = target.read_bytes()
    with pytest.raises(FileExistsError, match="already exists"):
        official.before_after_report(database, private_detail_path=target)
    assert target.read_bytes() == before
    # a symlink — dangling or pointing at a real file — is never followed nor replaced
    dangling = tmp_path / "dangling.json"
    dangling.symlink_to(tmp_path / "nowhere.json")
    with pytest.raises(FileExistsError, match="already exists"):
        official.before_after_report(database, private_detail_path=dangling)
    assert not (tmp_path / "nowhere.json").exists()
    victim = tmp_path / "victim.json"
    victim.write_text("keep me", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(victim)
    with pytest.raises(FileExistsError, match="already exists"):
        official.before_after_report(database, private_detail_path=link)
    assert victim.read_text(encoding="utf-8") == "keep me"
    # a permissive umask cannot widen the file: the mode is fixed after the open
    previous = os.umask(0)
    try:
        loose = tmp_path / "loose.json"
        official.before_after_report(database, private_detail_path=str(loose))
        assert stat.S_IMODE(loose.stat().st_mode) == 0o600
    finally:
        os.umask(previous)
    # the report is the same whether or not the detail is written, and it names no symbol
    assert official.before_after_report(database) == report and "PETR4" not in json.dumps(report)


def test_q6_a_switch_without_an_explicit_source_version_stamps_the_cycles_versions_never_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Q6: a switch without source_version stamped "rollback" as the internal generation's tp_source_version. Now it derives the
    # validated cycles' methodology versions ("+".join(sorted), as the automatic pass); a rollback to the blend keeps "rollback".
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None and g0["source_version"] == "7"
    report = official.before_after_report(database)
    _authorize(monkeypatch, report["report_sha256"])
    g1 = official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    assert g1["source"] == SOURCE_INTERNAL and g1["source_version"] == "7" and official.official_row(database, "US", "AAPL")["tp_source_version"] == "7"  # type: ignore[index]
    assert official.official_stamp(database, "B3")["tp_source_version"] == "7"
    # cycles of mixed methodology versions: the union, sorted, as the automatic pass stamps it
    nyse_v8 = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0, internal_buy_in=62.0)], _wall(), version=8)
    auto = official.current_generation(database)
    assert auto is not None and auto["cycles"]["NYSE"] == nyse_v8 and auto["source_version"] == "7+8"
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    rolled = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="rollback")
    assert rolled["source"] == SOURCE_BLEND and rolled["source_version"] == "rollback"  # Passo 0 behaviour, unchanged
    report = official.before_after_report(database)
    _authorize(monkeypatch, report["report_sha256"])
    mixed = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    assert mixed["source_version"] == "7+8"
    # the mesa's explicit declaration wins when given, on both paths
    report = official.before_after_report(database)
    rolled = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="rollback", source_version="7")
    assert rolled["source_version"] == "7"
    report = official.before_after_report(database)
    assert report["after_source_version"] == "7+8"  # the version the switch would stamp is in the receipt (C395-1)
    with pytest.raises(ValueError, match="EXACTLY the cycles and targeted admissions"):  # a receipt of the derived version does not authorize another one
        official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, source_version="8",
                                   before_after_sha256=report["report_sha256"])
    report = official.before_after_report(database, source_version="8")
    assert report["after_source_version"] == "8"
    _authorize(monkeypatch, report["report_sha256"])
    declared = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, source_version="8",
                                          before_after_sha256=report["report_sha256"])
    assert declared["source_version"] == "8" and declared["receipt"]["source_switch"]["from"] == SOURCE_BLEND


def test_c395_1_the_cited_hash_binds_the_proposed_cycles_and_targeted_admissions(monkeypatch: pytest.MonkeyPatch) -> None:
    # C395-1: the approved before/after receipt used to hash only the head (the "before"); the switch then validated and wrote the
    # order's cycles/targeted separately, so the SAME hash was accepted with another composition (a B3 cycle serving 100→10 instead
    # of 100→99). Now the aggregate binds the AFTER composition (after_cycles + after_targeted_sha256) and select_generation recomputes
    # the receipt over the exact cycles/targeted of the order: another cycle, a targeted admission added or dropped, is refused.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None and g0["cycles"] == cycles
    benign = _publish_universe(database, "B3", [_row("PETR4", tp=100.0, buy_in=80.0, price=90.0, internal_tp=99.0, internal_buy_in=79.0)], _wall())
    brutal = _publish_universe(database, "B3", [_row("PETR4", tp=100.0, buy_in=80.0, price=90.0, internal_tp=10.0, internal_buy_in=8.0)], _wall())
    rerun = _publish_universe(database, "B3", [_row("PETR4", tp=100.0, buy_in=80.0, price=90.0, internal_tp=99.0, internal_buy_in=79.0)], _wall())  # benign, re-run
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    head = official.current_generation(database)
    assert head is not None  # the automatic pass activated the latest B3 cycle; the mesa reads THIS head
    proposal = {**head["cycles"], "B3": benign}
    approved = official.before_after_report(database, cycles=proposal, targeted={})
    assert approved["after_cycles"] == proposal and approved["after_targeted_count"] == 0 and approved["markets"]["B3"]["tp"]["median"] == pytest.approx(-0.01)
    assert approved["after_source_version"] == "7" and approved == official.before_after_report(database, cycles=proposal)  # a proposal without targeted admits none, as the order
    # a re-run cycle with IDENTICAL rows: the statistics coincide, the hash does not — only the binding of after_cycles tells them apart
    twin = official.before_after_report(database, cycles={**proposal, "B3": rerun}, targeted={})
    assert twin["markets"] == approved["markets"] and twin["after_cycles"] != approved["after_cycles"] and twin["report_sha256"] != approved["report_sha256"]
    other = official.before_after_report(database, cycles={**proposal, "B3": brutal}, targeted={})
    assert other["report_sha256"] != approved["report_sha256"] and other["markets"]["B3"]["tp"]["median"] == pytest.approx(-0.9)
    with_targeted = official.before_after_report(database, cycles=proposal, targeted={"wege3": wege})
    assert with_targeted["report_sha256"] not in (approved["report_sha256"], other["report_sha256"]) and with_targeted["after_targeted_count"] == 1
    assert "WEGE3" not in json.dumps(with_targeted) and with_targeted["after_targeted_sha256"] == official.canonical_sha256({"WEGE3": wege})
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    for bad_cycles, bad_targeted in (({**proposal, "B3": brutal}, {}), (proposal, {"WEGE3": wege}), ({**proposal, "B3": brutal}, {"WEGE3": wege})):
        with pytest.raises(ValueError, match="EXACTLY the cycles and targeted admissions"):
            official.select_generation(database, cycles=bad_cycles, targeted=bad_targeted, now=_wall(), activated_by="mesa", reason="switch",
                                       source=SOURCE_INTERNAL, before_after_sha256=approved["report_sha256"])
    assert official.current_generation(database) == head  # nothing landed
    with pytest.raises(ValueError, match="EXACTLY the cycles and targeted admissions"):  # a receipt WITH the admission does not authorize dropping it
        official.select_generation(database, cycles=proposal, targeted={}, now=_wall(), activated_by="mesa", reason="switch",
                                   source=SOURCE_INTERNAL, before_after_sha256=with_targeted["report_sha256"])
    _authorize(monkeypatch, approved["report_sha256"])
    switched = official.select_generation(database, cycles=proposal, targeted={}, now=_wall(), activated_by="mesa", reason="switch",
                                          source=SOURCE_INTERNAL, before_after_sha256=approved["report_sha256"])
    assert switched["cycles"]["B3"] == benign and switched["source"] == SOURCE_INTERNAL and switched["receipt"]["source_switch"]["before_after_sha256"] == approved["report_sha256"]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 99.0  # type: ignore[index]  # the approved −1 %, never the −90 %
    # the receipt without a proposal is the head's own composition: it equals the proposal receipt only when they coincide
    same = official.before_after_report(database)
    assert same["after_cycles"] == official.current_generation(database)["cycles"]  # type: ignore[index]
    assert same == official.before_after_report(database, cycles=same["after_cycles"], targeted=official.current_generation(database)["targeted"])  # type: ignore[index]


# ------------------------------------------------------------------------------------- rev 9: the residue closed, the receipt V3, the order as a command


def test_r9_a_row_without_the_internal_view_is_never_selectable_for_the_internal_source_nor_served(monkeypatch: pytest.MonkeyPatch,
                                                                                                    caplog: pytest.LogCaptureFixture) -> None:
    # The declared residue of Passo 1: an internal TP served under the blend's status/score. Now the internal view is required —
    # a cycle of the P1 code before rev 9 (internal buy-in, no view) is recorded, but invalid for the internal source, refused by
    # the order, counted as unservable by the receipt; a hand-made internal generation over it serves NOTHING, loudly.
    database = _database()
    cycles = {
        "B3": _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0, view=False)], NOW),
        "NASDAQ": _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], NOW + timedelta(minutes=1)),
        "NYSE": _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], NOW + timedelta(minutes=2)),
    }
    record = database.valuation_prediction_record(cycles["B3"], "PETR4", source=SOURCE_INTERNAL)
    assert record is not None and record["tp"] == 39.0 and record["decomposition"]["status"] is None  # recorded; its status is NOT the blend's
    assert database.valuation_prediction_record(cycles["B3"], "PETR4", source=SOURCE_BLEND)["decomposition"]["status"] == "full_match"  # type: ignore[index]
    view = official.selectable_cycles(database, source=SOURCE_INTERNAL)["B3"]
    assert view["valid"] is False and view["invalid_rows"] == ["PETR4"] and official.selectable_cycles(database, source=SOURCE_BLEND)["B3"]["valid"] is True
    report = official.before_after_report(database)
    assert report["markets"]["B3"]["n"] == 1 and report["markets"]["B3"]["served_pairs"] == 0 and report["markets"]["B3"]["after_unservable"] == 1
    assert report["markets"]["B3"]["status"]["before"] == {} and report["markets"]["NASDAQ"]["served_pairs"] == 1
    assert "**Atenção:** 1 par(es) sem a visão interna" in official.before_after_markdown(report)
    _authorize(monkeypatch, report["report_sha256"])
    with pytest.raises(ValueError, match=f"cycle for B3 is not complete/valid/recorded for source {SOURCE_INTERNAL}"):
        official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    # a hand-made internal generation over that cycle (as a hand edit would plant it): the B3 record is not served, the others are
    head = official.current_generation(database)
    assert head is not None
    planted = {**head, "generation_id": "hand-made", "source": SOURCE_INTERNAL, "previous_generation_id": head["generation_id"],
               "activated_at": (official._utc(head["activated_at"]) + timedelta(microseconds=1)).isoformat()}
    database._valuation_official_selections.append(planted)
    database.drop_official_cycle_cache()
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    assert official.official_row(database, "B3", "PETR4") is None and official.official_rows(database, "B3") == {}
    aapl = official.official_row(database, "US", "AAPL")
    assert aapl is not None and aapl["our_tp"] == 245.0 and aapl["status"] == "near_buy" and aapl["score"] == 79.0 and aapl["expected_total_return_percent"] == 20.5
    messages = [(record.levelno, record.getMessage()) for record in caplog.records if "has no internal view" in record.getMessage()]
    assert [level for level, _ in messages] == [logging.WARNING, logging.INFO] and all("B3/PETR4" in message for _, message in messages)  # once per record, then INFO
    # the optional part of the view (B3: the TP validation its status depends on) is served when the producer emits it
    row = _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0, tp_validation_status="validated",
               internal_tp_validation_status="review_required", internal_tp_validation_reasons=["Target price is outside the plausibility range"])
    assert official.internal_view(row) == {"score": 79.0, "status": "near_buy", "expected_total_return_percent": 20.5, "tp_validation_status": "review_required",
                                           "tp_validation_reasons": ["Target price is outside the plausibility range"]}
    internal = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, source=SOURCE_INTERNAL)
    assert internal is not None and internal["decomposition"]["tp_validation_status"] == "review_required" and internal["decomposition"]["status"] == "near_buy"
    served = official._served(row, internal, generation=planted, cycle_id="c", scope="universe", market="B3")
    assert served is not None and served["tp_validation_status"] == "review_required" and served["tp_validation_reasons"] == row["internal_tp_validation_reasons"]
    served["tp_validation_reasons"].append("mutated")
    assert row["internal_tp_validation_reasons"] == ["Target price is outside the plausibility range"]  # a copy
    for broken in ({"internal_score": None}, {"internal_status": ""}, {"internal_expected_total_return_percent": float("nan")}):
        assert official.internal_view({**row, **broken}) is None and official._usable({**row, **broken}, SOURCE_INTERNAL) is False
        assert official._usable({**row, **broken}, SOURCE_BLEND) is True  # the blend never needs it


def test_r9_the_switch_must_cite_exactly_the_receipt_the_lock_commit_names(monkeypatch: pytest.MonkeyPatch) -> None:
    # The lock commit names the receipt the owner accepted; the order must cite exactly it AND it must be the receipt recomputed
    # on the head over the order's proposal. A lock without a named receipt (None, a placeholder) switches nothing.
    database = _database()
    cycles = _three_markets(database)
    report = official.before_after_report(database)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)

    def order(cited: str) -> dict[str, Any]:
        return official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=cited)

    for named in (None, "PENDING-OWNER-ACCEPTANCE", report["report_sha256"].upper()):
        monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", named)
        with pytest.raises(ValueError, match="the lock commit names no accepted before/after receipt"):
            order(report["report_sha256"])
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", "f" * 64)  # another receipt accepted
    with pytest.raises(ValueError, match="is the receipt of the generation in force over this proposal but not the accepted one"):
        order(report["report_sha256"])
    with pytest.raises(ValueError, match="does not match its report_sha256"):  # citing the accepted hash on a head it is not the receipt of
        order("f" * 64)
    assert len(database._valuation_official_selections) == 1  # nothing written by any refusal
    # the head moves after the acceptance (a targeted admission): the accepted receipt no longer recomputes, and the new one is not accepted
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", report["report_sha256"])
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    moved = official.before_after_report(database)
    with pytest.raises(ValueError, match="does not match its report_sha256"):
        official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=report["report_sha256"])
    with pytest.raises(ValueError, match="not the accepted one"):
        official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=moved["report_sha256"])
    # a new acceptance (a new lock commit naming the new receipt) lands; the rollback never needs any of it
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", moved["report_sha256"])
    switched = official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege}, now=_wall(), activated_by="mesa", reason="switch",
                                          source=SOURCE_INTERNAL, before_after_sha256=moved["report_sha256"])
    assert switched["source"] == SOURCE_INTERNAL and switched["receipt"]["source_switch"]["before_after_sha256"] == moved["report_sha256"]
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", None)
    rolled = official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="rollback")
    assert rolled["source"] == SOURCE_BLEND


def test_r9_the_receipt_and_its_markdown_name_no_symbol_and_the_cli_appends_the_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                        capsys: pytest.CaptureFixture[str]) -> None:
    database = _database()
    _publish_universe(database, "B3", [
        _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0, internal_buy_in=31.0),                                 # full_match → near_buy (the default view)
        _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=80.0, internal_buy_in=66.0, status="near_buy", internal_status="full_match", internal_score=85.0),
        _row("ITUB4", tp=30.0, buy_in=25.0, price=27.0, internal_tp=30.0, internal_buy_in=25.0, status="watchlist", internal_status="watchlist", internal_score=80.0,
             tp_validation_status="validated", internal_tp_validation_status="validated"),
    ], NOW)
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], NOW + timedelta(minutes=1))
    _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], NOW + timedelta(minutes=2))
    report = official.before_after_report(database)
    b3 = report["markets"]["B3"]
    assert b3["status"] == {"before": {"full_match": 1, "near_buy": 1, "watchlist": 1}, "after": {"full_match": 1, "near_buy": 1, "watchlist": 1}, "changed": 2,
                            "transitions": {"full_match->near_buy": 1, "near_buy->full_match": 1}}
    assert b3["buy"] == {"status": "full_match", "before": 1, "after": 1, "entered": 1, "left": 1}
    assert b3["tp_change_buckets"] == {"down": 1, "flat": 1, "up": 1, "abs": {"lt_1pct": 1, "1_to_5pct": 1, "5_to_10pct": 0, "10_to_25pct": 1, "ge_25pct": 0}}
    assert b3["tp_validation"] == {"before_validated": 1, "after_validated": 1} and report["markets"]["NYSE"]["tp_validation"] is None
    assert b3["score_change"]["median"] == pytest.approx(0.0) and b3["score_change"]["p90"] == pytest.approx(0.2 * 0.0 + 0.8 * 5.0)  # −1, 0, +5 (the internal view)
    markdown = official.before_after_markdown(report)
    symbols = ("PETR4", "VALE3", "ITUB4", "AAPL", "KO")
    assert not any(symbol in json.dumps(report) or symbol in markdown for symbol in symbols)
    assert report["report_sha256"] in markdown and "| B3 | 3 | 0 | 3 | 0 | 1 → 1 | 1 | 1 | 2 | 0 → 1 | 2 |" in markdown and "`full_match → near_buy` 1" in markdown
    assert "| NASDAQ | 1 | 0 | 1 | 0 | 1 → 0 | 0 | 1 | 1 | 0 → 0 | 0 | -2,00 % | -2,00 % / -2,00 % |" in markdown and "**Atenção:**" not in markdown
    # F3: the One Pager rating of the served upside, per arm — the candidate gate is no longer called "COMPRA"
    assert b3["rating"] == {"before": {"ACUMULAR": 3}, "after": {"ACUMULAR": 1, "COMPRA": 1, "NEUTRO": 1}, "changed": 2,
                            "transitions": {"ACUMULAR->COMPRA": 1, "ACUMULAR->NEUTRO": 1}}  # +11,1/+12,9/+11,1 % → +8,3/+29,0/+11,1 %
    assert "Rating do One Pager — antes: ACUMULAR 3; depois: ACUMULAR 1, COMPRA 1, NEUTRO 1; mudanças: ACUMULAR → COMPRA 1, ACUMULAR → NEUTRO 1." in markdown
    assert "COMPRA ≥ 25 %, ACUMULAR ≥ 10 %, NEUTRO ≥ -10 %, REDUZIR abaixo" in markdown and "COMPRA = status" not in markdown
    assert "- **Candidato** = status `full_match`" in markdown and "**não** é o rating do One Pager" in markdown
    reordered = {**report, "rating_cuts": dict(sorted(report["rating_cuts"].items()))}  # a JSON reload keeps the cuts sorted by name: same text
    assert official.before_after_markdown(reordered) == markdown
    # the CLI prints the aggregate and APPENDS the summary (a CI step summary is an existing file); --markdown alone is refused
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    monkeypatch.setenv("C3PO_BUILD_SHA", PRODUCER)
    summary = tmp_path / "step_summary.md"
    summary.write_text("# earlier step\n", encoding="utf-8")
    assert official.main(["--before-after", "--markdown", str(summary)]) == 0
    attested = official.attest_before_after(report, producer_build_sha=PRODUCER)
    assert json.loads(capsys.readouterr().out) == json.loads(json.dumps(attested))
    assert official.main(["--before-after", "--markdown", str(summary)]) == 0
    capsys.readouterr()
    attested_markdown = official.before_after_markdown(attested)  # the CLI renders the ATTESTED receipt: it names its producer
    assert attested_markdown.replace(f"- Produzido pela revisão implantada `{PRODUCER}` (`receipt_sha256` `{attested['receipt_sha256']}`: "
                                     "o recibo com a identidade do produtor)\n", "") == markdown
    assert summary.read_text(encoding="utf-8") == "# earlier step\n" + attested_markdown + attested_markdown
    for argv in (["--markdown", str(summary)], ["--health", "--markdown", str(summary)]):
        with pytest.raises(SystemExit):
            official.main(argv)


def test_r9_the_order_commands_execute_the_switch_and_the_rollback_over_the_receipts_proposal(monkeypatch: pytest.MonkeyPatch,
                                                                                              capsys: pytest.CaptureFixture[str]) -> None:
    database = _database()
    cycles = _three_markets(database)
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": wege}
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    for argv in (["--switch-to-internal", "--reason", "P1"], ["--switch-to-internal", "--before-after-sha256", "a" * 64],
                 ["--rollback-to-blend"], ["--before-after", "--reason", "x"], ["--before-after", "--before-after-sha256", "a" * 64],
                 ["--rollback-to-blend", "--reason", "x", "--before-after-sha256", "a" * 64], ["--switch-to-internal", "--before-after-sha256", "a" * 64, "--reason", " "]):
        with pytest.raises(SystemExit):
            official.main(argv)
    # the receipt of the purge proposal, from the CLI; the order with the SAME proposal options cites it — refused while the lock is false
    assert official.main(["--before-after", "--purge-targeted"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["after_targeted_count"] == 0 and receipt["targeted_cycles"] == 1
    switch = ["--switch-to-internal", "--purge-targeted", "--before-after-sha256", receipt["report_sha256"], "--reason", "P1: owner accepted the receipt"]
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)  # the lock as it stood before the lock commit
    with pytest.raises(ValueError, match="official_tp_replacement_authorized is false"):
        official.main(switch)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", official.RECEIPT_PLACEHOLDER)  # the lock commit before the acceptance
    with pytest.raises(ValueError, match="the lock commit names no accepted before/after receipt"):
        official.main(switch)
    assert official.current_generation(database) == head  # nothing switched
    _authorize(monkeypatch, receipt["report_sha256"])
    assert official.main(switch) == 0
    printed = json.loads(capsys.readouterr().out)
    generation = official.current_generation(database)
    assert generation is not None and generation["source"] == SOURCE_INTERNAL and generation["targeted"] == {} and generation["cycles"] == cycles
    assert printed == {"generation_id": generation["generation_id"], "previous_generation_id": head["generation_id"], "source": SOURCE_INTERNAL, "source_version": "7",
                       "activated_at": generation["activated_at"], "cycles": cycles, "targeted_count": 0, "targeted_sha256": official.canonical_sha256({}),
                       "source_switch": {"from": SOURCE_BLEND, "to": SOURCE_INTERNAL, "before_after_sha256": receipt["report_sha256"]}, "explicit": True,
                       "freeze": None, "ended_freeze": None}
    assert generation["receipt"]["reason"] == "P1: owner accepted the receipt" and generation["activated_by"] == "mesa"
    assert official.official_row(database, "US", "AAPL")["status"] == "near_buy"  # type: ignore[index]  # served with the internal view
    # the rollback: the same path, never locked, no hash — over the head's own composition unless a proposal is given; no symbol printed
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", False)
    assert official.main(["--rollback-to-blend", "--targeted", f"WEGE3={wege}", "--reason", "drill"]) == 0
    printed = json.loads(capsys.readouterr().out)
    rolled = official.current_generation(database)
    assert rolled is not None and rolled["source"] == SOURCE_BLEND and rolled["targeted"] == {"WEGE3": wege} and rolled["source_version"] == "rollback"
    assert printed["source_switch"] == {"from": SOURCE_INTERNAL, "to": SOURCE_BLEND, "before_after_sha256": None} and printed["targeted_count"] == 1
    assert "WEGE3" not in json.dumps(printed) and printed["targeted_sha256"] == official.canonical_sha256({"WEGE3": wege})
    assert official.official_row(database, "US", "AAPL")["status"] == "full_match"  # type: ignore[index]  # the blend's view again


# ------------------------------------------------------------------------------------- cross-review of rev 9 (F1–F3)


def _noon_zone() -> timezone:
    """A fixed zone where the wall clock reads about noon: a freeze of a few hours never reaches ITS midnight, whenever the
    suite runs (the real ``FREEZE_NIGHTLY_ZONE`` bound is tested on its own)."""
    return timezone(timedelta(hours=12 - datetime.now(timezone.utc).hour))


def test_f1_the_freeze_holds_the_head_from_the_receipt_to_the_order(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # F1: the lock commit is reviewed, merged and deployed AFTER the owner accepts the receipt; meanwhile the IR worker republished
    # the B3 universe (a new cycle → a new head) and the accepted receipt no longer recomputed: the order was refused. The mesa's
    # freeze re-selects the head's own composition and holds every automatic writer; the order lands on it and ends it.
    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    database = _database()
    cycles = _three_markets(database)
    wege = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0), _wall())
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": wege}
    served = official.official_row(database, "B3", "PETR4")
    wall = _wall()
    frozen = official.freeze_selection(database, now=wall, until=wall + timedelta(hours=8), reason="P1: congela até a ordem", activated_by="mesa")
    # the head's own composition, a new generation id, an explicit order carrying the freeze — nothing served changes but the stamp
    assert {key: frozen[key] for key in ("cycles", "targeted", "source", "source_version", "session_dates")} == \
        {key: head[key] for key in ("cycles", "targeted", "source", "source_version", "session_dates")}
    assert frozen["previous_generation_id"] == head["generation_id"] and frozen["activated_by"] == "mesa"
    assert frozen["receipt"] == {"reason": "P1: congela até a ordem", "explicit": True,
                                 "freeze": {"until": official._utc(wall + timedelta(hours=8)).isoformat(), "of_generation": head["generation_id"]}}
    again = official.official_row(database, "B3", "PETR4")
    assert again is not None and served is not None and again["generation_id"] == frozen["generation_id"]
    assert {k: v for k, v in again.items() if k != "generation_id"} == {k: v for k, v in served.items() if k != "generation_id"}
    health = official.selection_health(database, now=_wall())
    assert health["freeze"] == {"generation_id": frozen["generation_id"], "until": frozen["receipt"]["freeze"]["until"], "reason": "P1: congela até a ordem"}
    assert "frozen by the mesa's order until" in health["detail"] and health["status"] in {"ok", "stale"}
    # the receipt on the frozen head, over the proposal the order will carry (the valid targeted admissions kept, F2)
    proposal = official.targeted_valid_for(database, frozen)
    assert proposal == {"WEGE3": wege}
    report = official.before_after_report(database, cycles=frozen["cycles"], targeted=proposal)
    assert report["generation_id"] == frozen["generation_id"]
    # the window: an IR republish of the B3 universe, a One Pager's targeted cycle, the deploy's bootstrap — nothing moves the head
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    b3_ir = _publish_universe(database, "B3", [_row("PETR4", tp=41.0, buy_in=33.0, price=36.0, internal_tp=40.0, internal_buy_in=32.0),
                                               _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0, internal_buy_in=59.0)], _wall())
    itsa = _targeted(database, "ITSA4", _row("ITSA4", tp=12.0, buy_in=10.0, price=11.0, internal_tp=11.8, internal_buy_in=9.8), _wall())
    assert official.bootstrap_official_selection(database)["generation"] == frozen
    assert official.current_generation(database) == frozen
    assert database.valuation_prediction_record(b3_ir, "PETR4", source=SOURCE_INTERNAL) is not None  # recorded all the same (records first)
    assert any("frozen by the mesa's order" in record.getMessage() and record.levelno == logging.INFO for record in caplog.records)
    assert any(f"targeted cycle {itsa} for ITSA4 not admitted — the selection is frozen" in record.getMessage() for record in caplog.records)
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    # the order (after the lock commit's deploy): the accepted receipt still recomputes on the frozen head — it lands and ends the freeze
    _authorize(monkeypatch, report["report_sha256"])
    switched = official.select_generation(database, cycles=frozen["cycles"], targeted=proposal, now=_wall(), activated_by="mesa", reason="P1 switch",
                                          source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    assert switched["source"] == SOURCE_INTERNAL and switched["previous_generation_id"] == frozen["generation_id"]
    assert switched["receipt"]["ended_freeze"] == {"generation_id": frozen["generation_id"], "until": frozen["receipt"]["freeze"]["until"]}
    assert official.selection_freeze(switched, now=_wall()) is None and official.selection_health(database, now=_wall())["freeze"] is None
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 49.0  # type: ignore[index]  # the kept targeted admission, internal
    # the automatic writers chain again: a cycle published after the order is activated in the internal source
    b3_after = _publish_universe(database, "B3", [_row("PETR4", tp=42.0, buy_in=33.0, price=36.0, internal_tp=41.5, internal_buy_in=32.5),
                                                  _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0, internal_buy_in=59.0)], _wall())
    latest = official.current_generation(database)
    assert latest is not None and latest["cycles"]["B3"] == b3_after and latest["source"] == SOURCE_INTERNAL
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 41.5  # type: ignore[index]
    assert cycles["NASDAQ"] == latest["cycles"]["NASDAQ"]


def test_f1_a_freeze_ends_by_itself_and_the_cycles_of_its_window_are_then_activated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    database = _database()
    cycles = _three_markets(database)
    wall = _wall()
    frozen = official.freeze_selection(database, now=wall, until=wall + timedelta(milliseconds=300), reason="short", activated_by="mesa")
    b3_window = _publish_universe(database, "B3", [_row("PETR4", tp=41.0, buy_in=33.0, price=36.0, internal_tp=40.0, internal_buy_in=32.0)], _wall())
    assert official.current_generation(database) == frozen
    time.sleep(0.35)
    # past `until` the first pass composes the window's cycle — predicted AFTER the freeze order, so W1 lets it in
    activated = official.bootstrap_official_selection(database)["generation"]
    assert activated is not None and activated["cycles"] == {**cycles, "B3": b3_window} and activated["activated_by"] == official.ACTIVATED_BY
    assert activated["receipt"]["explicit_order"] == frozen["generation_id"] and "explicit" not in activated["receipt"]
    # the pure reading: bounded by until, by activated_at + FREEZE_MAX, explicit orders only
    at = official._utc(frozen["activated_at"])
    until = official._utc(frozen["receipt"]["freeze"]["until"])
    assert official.selection_freeze(frozen, now=until - timedelta(microseconds=1)) is not None and official.selection_freeze(frozen, now=until) is None
    unbounded = {**frozen, "receipt": {**frozen["receipt"], "freeze": {"until": (at + timedelta(days=3)).isoformat()}}}
    assert official.selection_freeze(unbounded, now=at + official.FREEZE_MAX - timedelta(seconds=1))["until"] == (at + official.FREEZE_MAX).isoformat()  # type: ignore[index]
    assert official.selection_freeze(unbounded, now=at + official.FREEZE_MAX) is None
    unreadable = {**frozen, "receipt": {**frozen["receipt"], "freeze": {"until": "tomorrow"}}}
    assert official.selection_freeze(unreadable, now=at)["until"] == (at + official.FREEZE_MAX).isoformat()  # type: ignore[index]
    automatic = {**frozen, "receipt": {key: value for key, value in frozen["receipt"].items() if key != "explicit"}}
    assert official.selection_freeze(automatic, now=at) is None and official.selection_freeze(None, now=at) is None


def test_f1_the_freeze_refusals_and_the_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    empty = _database()
    wall = _wall()
    with pytest.raises(ValueError, match="nothing to freeze"):
        official.freeze_selection(empty, now=wall, until=wall + timedelta(minutes=5), reason="x", activated_by="mesa")
    database = _database()
    _three_markets(database)
    head = official.current_generation(database)
    wall = _wall()
    for until, message in ((wall.replace(tzinfo=None) + timedelta(hours=1), "must be an aware instant"), (wall, "is not after the order's clock"),
                           (wall + official.FREEZE_MAX + timedelta(minutes=1), "is too far")):
        with pytest.raises(ValueError, match=message):
            official.freeze_selection(database, now=wall, until=until, reason="x", activated_by="mesa")
    # the real nightly bound: never past the next midnight in São Paulo, whatever FREEZE_MAX would allow
    local = wall.astimezone(official.FREEZE_NIGHTLY_ZONE)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=official.FREEZE_NIGHTLY_ZONE)
    with pytest.raises(ValueError, match="never past the nightly cycle"):
        official.freeze_selection(database, now=wall, until=midnight + timedelta(minutes=1), reason="x", activated_by="mesa")
    with pytest.raises(ValueError, match="is in the future"):
        official.freeze_selection(database, now=wall + timedelta(minutes=5), until=wall + timedelta(minutes=30), reason="x", activated_by="mesa")
    assert official.current_generation(database) == head  # nothing written by any refusal
    unknown = _database()
    _three_markets(unknown)
    unknown_head = official.current_generation(unknown)
    assert unknown_head is not None
    unknown._valuation_official_selections.append({**unknown_head, "generation_id": "unknown-source", "source": "v3_2_shadow",  # a hand edit (Q3)
                                                   "previous_generation_id": unknown_head["generation_id"],
                                                   "activated_at": (official._utc(unknown_head["activated_at"]) + timedelta(microseconds=1)).isoformat()})
    unknown.drop_official_cycle_cache()
    with pytest.raises(ValueError, match="roll back to the blend by explicit order first"):
        official.freeze_selection(unknown, now=_wall(), until=_wall() + timedelta(minutes=5), reason="x", activated_by="mesa")
    # the CLI: --freeze-selection --until (with its offset) --reason; prints the generation without symbols, with the freeze
    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    until = (datetime.now(timezone.utc) + timedelta(hours=2)).astimezone(timezone(timedelta(hours=-3))).replace(microsecond=0)
    for argv in (["--freeze-selection", "--reason", "x"], ["--freeze-selection", "--until", until.isoformat()], ["--health", "--until", until.isoformat()],
                 ["--freeze-selection", "--until", until.replace(tzinfo=None).isoformat(), "--reason", "x"],
                 ["--freeze-selection", "--until", "amanhã", "--reason", "x"],
                 ["--freeze-selection", "--until", until.isoformat(), "--reason", "x", "--purge-targeted"],
                 ["--before-after", "--purge-targeted", "--keep-internal-targeted"], ["--before-after", "--targeted", "WEGE3=x", "--keep-internal-targeted"]):
        with pytest.raises(SystemExit):
            official.main(argv)
    assert official.current_generation(database) == head
    assert official.main(["--freeze-selection", "--until", until.isoformat(), "--reason", "P1: recibo de terça"]) == 0
    printed = json.loads(capsys.readouterr().out)
    frozen = official.current_generation(database)
    assert frozen is not None and printed["generation_id"] == frozen["generation_id"] and printed["previous_generation_id"] == head["generation_id"]  # type: ignore[index]
    assert printed["freeze"] == {"until": official._utc(until).isoformat(), "of_generation": head["generation_id"]} and printed["explicit"] is True  # type: ignore[index]
    assert printed["ended_freeze"] is None and printed["source"] == SOURCE_BLEND and printed["targeted_count"] == 0
    assert official.main(["--health"]) == 0
    assert json.loads(capsys.readouterr().out)["freeze"]["generation_id"] == frozen["generation_id"]
    # the rollback (never locked) ends it too, over the head's composition
    assert official.main(["--rollback-to-blend", "--source-version", "7", "--reason", "libera o congelamento"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ended_freeze"]["generation_id"] == frozen["generation_id"] and printed["freeze"] is None
    assert official.selection_frozen(database) is None


def test_f1_the_ir_propagation_and_the_on_demand_b3_build_wait_while_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ir_valuation import InvestorRelationsValuationProcessor
    from app.market_data.b3_screener import B3ScreenerService

    monkeypatch.setattr(official, "FREEZE_NIGHTLY_ZONE", _noon_zone())
    database = _database()
    cycles = _three_markets(database)
    claims: list[int] = []

    def claim(limit: int = 12) -> list[dict[str, Any]]:
        claims.append(limit)
        return []

    monkeypatch.setattr(database, "claim_ir_valuation_updates", claim)
    screener = B3ScreenerService(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False), database, object())  # type: ignore[arg-type]
    built: list[str] = []
    monkeypatch.setattr(screener, "_build_targeted_valuation", lambda symbol: built.append(symbol) or {"symbol": symbol, "our_tp": 12.0})
    monkeypatch.setattr(screener, "refresh_symbols", lambda symbols: pytest.fail("no B3 universe is republished while frozen"))
    screener._matrix_rows = [{"symbol": "PETR4", "our_tp": 40.0}]
    processor = InvestorRelationsValuationProcessor(database, screener)
    assert processor.process() == {"claimed": 0, "updated": [], "targeted_only": [], "failed": []} and claims == [12]  # not frozen: claims as before
    assert screener.valuation_for("ITSA4", build_if_missing=True) == {"symbol": "ITSA4", "our_tp": 12.0} and built == ["ITSA4"]
    wall = _wall()
    frozen = official.freeze_selection(database, now=wall, until=wall + timedelta(hours=4), reason="P1", activated_by="mesa")
    until = frozen["receipt"]["freeze"]["until"]
    # frozen: the queue is not even claimed (it keeps every update for the first poll after the order) and nothing is built on demand
    assert processor.process() == {"claimed": 0, "updated": [], "targeted_only": [], "failed": [], "deferred_until": until} and claims == [12]
    assert screener.valuation_for("ITSA4", build_if_missing=True) is None and built == ["ITSA4"]
    assert screener.valuation_for("PETR4", build_if_missing=True) == {"symbol": "PETR4", "our_tp": 40.0}  # a current row is still answered
    # the order (here the rollback, never locked) ends the freeze: both resume
    official.select_generation(database, cycles=cycles, now=_wall(), activated_by="mesa", reason="libera", source_version="7")
    processor.process()
    assert claims == [12, 12]
    assert screener.valuation_for("ITSA4", build_if_missing=True) is not None and built == ["ITSA4", "ITSA4"]


def test_f2_keep_internal_targeted_keeps_the_valid_admissions_and_drops_only_the_ones_the_order_would_refuse(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # F2: `--purge-targeted` also dropped valid rev-9 targeted cycles; a same-day one is never rebuilt by the producer that day
    # (valuation_for answers the same-day snapshot), so its One Pager failed until the next day. The proposal now keeps them.
    database = _database()
    cycles = _three_markets(database)
    old = _targeted(database, "WEGE3", _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0, internal_buy_in=41.0, view=False), _wall())  # pre-rev 9
    new = _targeted(database, "ITSA4", _row("ITSA4", tp=12.0, buy_in=10.0, price=11.0, internal_tp=11.8, internal_buy_in=9.8), _wall())  # rev 9
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"ITSA4": new, "WEGE3": old}
    assert official.targeted_valid_for(database, head) == {"ITSA4": new} and official.targeted_valid_for(database, head, source=SOURCE_BLEND) == head["targeted"]
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    monkeypatch.setenv("C3PO_BUILD_SHA", PRODUCER)
    assert official.main(["--before-after", "--keep-internal-targeted"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == json.loads(json.dumps(official.attest_before_after(official.before_after_report(database, cycles=cycles, targeted={"ITSA4": new}),
                                                                         producer_build_sha=PRODUCER)))
    assert receipt["targeted_cycles"] == 2 and receipt["after_targeted_count"] == 1 and "ITSA4" not in json.dumps(receipt)
    assert receipt["markets"]["B3"]["missing_internal"] == 1  # the dropped pre-rev-9 admission: registered in the blend only
    _authorize(monkeypatch, receipt["report_sha256"])
    assert official.main(["--switch-to-internal", "--keep-internal-targeted", "--before-after-sha256", receipt["report_sha256"], "--reason", "P1"]) == 0
    capsys.readouterr()
    switched = official.current_generation(database)
    assert switched is not None and switched["source"] == SOURCE_INTERNAL and switched["targeted"] == {"ITSA4": new}
    assert official.official_row(database, "B3", "ITSA4")["our_tp"] == 11.8 and official.official_row(database, "B3", "WEGE3") is None  # type: ignore[index]


def test_f3_the_rating_mirrors_the_pinned_one_pager_rule() -> None:
    # the receipt's rating is the One Pager's: the same cuts, the same order, the floor below — read from the pinned file itself
    cuts = official.ONE_PAGER_RATING_CUTS
    expected = "rating = " + " else ".join(f'"{name}" if upside >= {cut:g}' for name, cut in cuts) + f' else "{official.ONE_PAGER_RATING_FLOOR}"'
    assert expected in (APP / "one_pager.py").read_text(encoding="utf-8")
    assert [official.one_pager_rating(value) for value in (25.0, 24.99, 10.0, 9.99, -10.0, -10.01, None, float("nan"), "12")] == \
        ["COMPRA", "ACUMULAR", "ACUMULAR", "NEUTRO", "NEUTRO", "REDUZIR", None, None, "ACUMULAR"]


# ------------------------------------------------------------------ the read-only workflow (report=before-after)
WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "valuation-readonly-report.yml"
BACKEND = Path(__file__).resolve().parents[1]


def _workflow_steps() -> dict[str, dict[str, Any]]:
    import yaml

    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    return {step["name"]: step for job in jobs.values() for step in job.get("steps", []) if step.get("name")}


def _runner_script(step: dict[str, Any]) -> str:
    """The Python a runner step carries in its ``<<'PY'`` heredoc, exactly as the workflow file has it."""
    return str(step["run"]).split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]


def test_the_readonly_workflow_publishes_the_before_after_receipt_aggregate_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                                capsys: pytest.CaptureFixture[str]) -> None:
    """``report=before-after`` of ``valuation-readonly-report.yml``: the receipt the CLI prints (``--before-after
    --keep-internal-targeted``) passes the workflow's own verifier (exact aggregate keys, ``report_sha256`` recomputed, the
    producer's identity a commit under a ``receipt_sha256`` that recomputes); the second read-only exec renders
    ``before_after_markdown`` from that receipt alone; the summary verifier binds it to the verified hashes and to the SAME
    deployed build that produced the receipt; nothing written for upload or the step summary names a symbol. Each script is
    run here as the workflow file carries it."""
    import subprocess
    import sys

    steps = _workflow_steps()
    database = _database()
    _three_markets(database)
    _targeted(database, "ITSA4", _row("ITSA4", tp=12.0, buy_in=10.0, price=11.0, internal_tp=11.8, internal_buy_in=9.8), _wall())
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    build = "b" * 40  # the deployed build, the same for both execs
    monkeypatch.setenv("C3PO_BUILD_SHA", build)
    assert official.main(["--before-after", "--keep-internal-targeted"]) == 0
    printed = capsys.readouterr().out
    symbols = ("PETR4", "VALE3", "AAPL", "KO", "ITSA4")
    assert printed.count("\n") == 1 and not any(symbol in printed for symbol in symbols)

    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    out.mkdir()
    (raw / "before_after.json").write_text(printed, encoding="utf-8")
    verify = _runner_script(steps["Verify the before/after receipt and keep the aggregate only"])

    def verified(text: str) -> subprocess.CompletedProcess[str]:
        (raw / "before_after.json").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, "-", str(raw / "before_after.json"), str(out)], input=verify, text=True, capture_output=True)

    accepted = verified(printed)
    assert accepted.returncode == 0, accepted.stderr
    receipt = json.loads(printed)
    assert receipt["producer_build_sha"] == build and receipt["after_targeted_count"] == 1
    assert json.loads((out / "report.json").read_text(encoding="utf-8")) == receipt
    assert receipt["report_sha256"] in accepted.stdout and build in accepted.stdout and not any(symbol in accepted.stdout for symbol in symbols)

    # the second exec, as the remote script carries it: the receipt in (stdin), the markdown and the renderer's build out
    remote = str(steps["Render the Portuguese summary in the running api container, read-only"]["run"])
    render = remote.split("render='", 1)[1].split("'\n", 1)[0]

    def rendered_under(renderer: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-c", render], input=(out / "report.json").read_text(encoding="utf-8"), text=True, capture_output=True,
                              cwd=BACKEND, env={**os.environ, "PYTHONPATH": str(BACKEND), "C3PO_BUILD_SHA": renderer})

    rendered = rendered_under(build)
    assert rendered.returncode == 0, rendered.stderr
    assert json.loads(rendered.stdout) == {"markdown": official.before_after_markdown(receipt), "renderer_build_sha": build}
    summarize = _runner_script(steps["Verify the summary and keep aggregates only"])
    env = {**os.environ, "RUN_ID": "7", "REVISION": "c" * 40, "GITHUB_STEP_SUMMARY": str(tmp_path / "step_summary.md")}

    def summarized(text: str) -> subprocess.CompletedProcess[str]:
        (raw / "summary.json").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, "-", str(raw / "summary.json"), str(out)], input=summarize, text=True, capture_output=True, env=env)

    done = summarized(rendered.stdout)
    assert done.returncode == 0, done.stderr
    metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert metadata == {"run_id": "7", "workflow_revision": "c" * 40, "producer_build_sha": build, "report": "before-after",
                        "schema": official.BEFORE_AFTER_SCHEMA, "report_sha256": receipt["report_sha256"], "receipt_sha256": receipt["receipt_sha256"],
                        "generation_id": receipt["generation_id"], "generation_source": SOURCE_BLEND, "after_source_version": receipt["after_source_version"]}
    assert (out / "summary.md").read_text(encoding="utf-8") == official.before_after_markdown(receipt)
    step_summary = (tmp_path / "step_summary.md").read_text(encoding="utf-8")
    assert receipt["report_sha256"] in step_summary and f"pela revisão implantada `{build}`" in step_summary
    published = [path.read_text(encoding="utf-8") for path in out.iterdir()] + [step_summary, done.stdout]
    assert not any(symbol in text for text in published for symbol in symbols)

    # the verifier refuses what is not exactly the aggregate, does not recompute, or does not name its producer — before anything is uploaded
    def reattested(report: dict[str, Any], producer: Any) -> dict[str, Any]:
        return official.attest_before_after({key: value for key, value in report.items() if key not in official.BEFORE_AFTER_ATTESTATION_KEYS},
                                            producer_build_sha=producer)

    bare = {key: value for key, value in receipt.items() if key not in official.BEFORE_AFTER_ATTESTATION_KEYS}
    detail = {**receipt, "detail": {"B3": ["PETR4"]}}
    tampered = {**receipt, "targeted_cycles": receipt["targeted_cycles"] + 1}
    keyed = {**receipt, "markets": {**receipt["markets"], "B3": {**receipt["markets"]["B3"], "pairs": {"PETR4": {}}}}}
    for text, message in ((json.dumps(detail), "keys are not exactly the aggregate's"), (json.dumps(tampered), "report_sha256 does not recompute"),
                          (json.dumps(keyed), "keys are not exactly the aggregate's"), (json.dumps({**receipt, "schema": "VALUATION_P1_BEFORE_AFTER_V2"}), "not Valuation P1 rev 9"),
                          (json.dumps({**receipt, "cycles": {"PETR4": "x"}}), "keyed by something other than a market"),
                          (json.dumps(bare), "does not name the build that produced it"),  # the receipt before the fix: no producer
                          (json.dumps(reattested(receipt, "development")), "not a commit sha"), (json.dumps(reattested(receipt, None)), "not a commit sha"),
                          (json.dumps({**receipt, "producer_build_sha": "a" * 40}), "receipt_sha256 does not recompute"),  # re-attributed by hand
                          (json.dumps({**receipt, "receipt_sha256": receipt["report_sha256"]}), "receipt_sha256 does not recompute"),
                          ("not json", "not a single JSON document"), (" " * 70000, "larger than an aggregate")):
        refused = verified(text)
        assert refused.returncode != 0 and message in refused.stderr, (message, refused.stderr)
        assert not any(symbol in refused.stdout + refused.stderr for symbol in symbols)
    assert verified(printed).returncode == 0  # the accepted receipt back in place for the summary checks
    unattributed = summarized(json.dumps({"markdown": official.before_after_markdown(receipt), "renderer_build_sha": "development"}))
    assert unattributed.returncode != 0 and "not a commit sha" in unattributed.stderr
    other = summarized(json.dumps({"markdown": official.before_after_markdown({**receipt, "report_sha256": "f" * 64}), "renderer_build_sha": build}))
    assert other.returncode != 0 and "not rendered from this receipt" in other.stderr
    unattested = summarized(json.dumps({"markdown": official.before_after_markdown(bare), "renderer_build_sha": build}))
    assert unattested.returncode != 0 and "not rendered from this receipt" in unattested.stderr
    legacy = summarized(json.dumps({"markdown": official.before_after_markdown(receipt), "build_sha": build}))  # the shape before the fix
    assert legacy.returncode != 0 and "unexpected summary shape" in legacy.stderr

    # Codex P2 on #451: the receipt produced under build A, a deploy, the summary rendered under build B — refused, nothing
    # published, and the receipt is never attributed to B (the second read only gates; the attribution is the receipt's own)
    under_a, under_b = "a" * 40, "d" * 40
    monkeypatch.setenv("C3PO_BUILD_SHA", under_a)
    assert official.main(["--before-after", "--keep-internal-targeted"]) == 0
    produced_a = capsys.readouterr().out
    out = tmp_path / "out_race"
    out.mkdir()
    (tmp_path / "step_summary.md").unlink()
    assert verified(produced_a).returncode == 0 and json.loads((out / "report.json").read_text(encoding="utf-8"))["producer_build_sha"] == under_a
    rendered_b = rendered_under(under_b)
    assert rendered_b.returncode == 0 and json.loads(rendered_b.stdout)["renderer_build_sha"] == under_b
    race = summarized(rendered_b.stdout)
    assert race.returncode != 0 and "the deployed build changed between the receipt and its summary" in race.stderr
    assert f"receipt produced by {under_a}, summary rendered by {under_b}" in race.stderr
    assert sorted(path.name for path in out.iterdir()) == ["report.json"] and not (tmp_path / "step_summary.md").exists()  # no summary, no metadata
    # the same receipt, re-attributed to B by hand on the runner, does not pass either verifier
    forged = {**json.loads(produced_a), "producer_build_sha": under_b}
    assert "receipt_sha256 does not recompute" in verified(json.dumps(forged)).stderr
    (out / "report.json").write_text(json.dumps(forged), encoding="utf-8")
    forged_summary = summarized(json.dumps({"markdown": official.before_after_markdown(forged), "renderer_build_sha": under_b}))
    assert forged_summary.returncode != 0 and "receipt_sha256 does not recompute" in forged_summary.stderr
    assert not (out / "metadata.json").exists() and not (out / "summary.md").exists()
    # rendered under A — the build that produced it — the receipt is published as A's, never as anything read later
    assert verified(produced_a).returncode == 0
    honest = summarized(rendered_under(under_a).stdout)
    assert honest.returncode == 0, honest.stderr
    assert json.loads((out / "metadata.json").read_text(encoding="utf-8"))["producer_build_sha"] == under_a
    assert json.loads(produced_a)["report_sha256"] == receipt["report_sha256"]  # the content hash the lock names is build-independent


def test_the_attestation_binds_the_producer_and_leaves_the_content_hash_alone() -> None:
    """``attest_before_after`` (Codex P2 on #451): ``receipt_sha256`` covers the aggregate AND ``producer_build_sha``;
    ``report_sha256`` — the hash the owner accepts, the lock names and the order recomputes under the lock commit's build —
    does not change with the producer; a report is attested once."""
    database = _database()
    _three_markets(database)
    report = official.before_after_report(database)
    under_a = official.attest_before_after(report, producer_build_sha="a" * 40)
    under_b = official.attest_before_after(report, producer_build_sha="b" * 40)
    assert set(under_a) == set(report) | set(official.BEFORE_AFTER_ATTESTATION_KEYS) and under_a["producer_build_sha"] == "a" * 40
    assert under_a["report_sha256"] == under_b["report_sha256"] == report["report_sha256"] and under_a["receipt_sha256"] != under_b["receipt_sha256"]
    assert under_a["receipt_sha256"] == official.canonical_sha256({key: value for key, value in under_a.items() if key != "receipt_sha256"})
    assert official.canonical_sha256({key: value for key, value in under_a.items() if key not in official.BEFORE_AFTER_ATTESTATION_KEYS + ("report_sha256",)}) \
        == report["report_sha256"]
    with pytest.raises(ValueError, match="already attested"):
        official.attest_before_after(under_a, producer_build_sha="a" * 40)
    markdown = official.before_after_markdown(under_a)
    assert "a" * 40 in markdown and under_a["receipt_sha256"] in markdown and "Produzido pela revisão implantada" not in official.before_after_markdown(report)


def test_the_readonly_workflow_runs_the_before_after_read_only_and_never_writes_a_detail() -> None:
    """The dispatch input chooses the report (``accuracy`` by default, the PREREG reading unchanged); ``before-after`` runs
    the receipt's command exactly, both execs in the running api container under PGOPTIONS read-only, with the same four
    deploy secrets as the accuracy path — never ``--private-detail``, never a ``--markdown`` path inside the container."""
    import yaml

    text = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    trigger = parsed[True]
    assert set(trigger) == {"workflow_dispatch"}
    report_input = trigger["workflow_dispatch"]["inputs"]["report"]
    assert report_input["type"] == "choice" and report_input["default"] == "accuracy" and report_input["options"] == ["accuracy", "before-after"]
    steps = _workflow_steps()
    gated = {name: step.get("if") for name, step in steps.items()}
    for name in ("Run the report in the running api container, read-only", "Verify the receipt and keep aggregates only", "Publish the aggregate receipt"):
        assert gated[name] == "steps.inputs.outputs.report == 'accuracy'"
    for name in ("Run the before/after receipt in the running api container, read-only", "Verify the before/after receipt and keep the aggregate only",
                 "Render the Portuguese summary in the running api container, read-only", "Verify the summary and keep aggregates only",
                 "Publish the before/after receipt"):
        assert gated[name] == "steps.inputs.outputs.report == 'before-after'"
    receipt_run = str(steps["Run the before/after receipt in the running api container, read-only"]["run"])
    render_run = str(steps["Render the Portuguese summary in the running api container, read-only"]["run"])
    assert "api python -m app.valuation_official --before-after --keep-internal-targeted </dev/null" in receipt_run
    for run in (receipt_run, render_run):
        assert "exec -T \\\n  -e 'PGOPTIONS=-c default_transaction_read_only=on' \\\n  api python" in run
        assert "/run/c3po-security/reboot.pending" in run and "remote stderr lines (kept private, not printed)" in run
    commands = "\n".join(str(step.get("run") or "") for step in steps.values())
    assert "--private-detail" not in commands and "--markdown" not in commands  # only the header comment names them, to forbid them
    secrets = sorted(set(__import__("re").findall(r"secrets\.([A-Z0-9_]+)", text)))
    assert secrets == ["C3PO_AWS_HOST", "C3PO_AWS_KNOWN_HOSTS", "C3PO_AWS_SSH_KEY", "C3PO_AWS_USER"]
    assert steps["Publish the before/after receipt"]["with"]["path"] == "${{ runner.temp }}/valuation-p1-before-after"
