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
from app.r2d2_v2_risk_source import ORIGIN_ONE_PAGER_SHA256
from app.valuation_accuracy import calls_by_source, load_prediction_calls
from app.valuation_official_engine import OFFICIAL_SOURCES, SOURCE_BLEND, SOURCE_INTERNAL

NOW = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)
APP = Path(__file__).resolve().parents[1] / "app"


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


def _wall() -> datetime:
    """The wall clock, as the automatic path reads it and as the mesa's order carries it (W2) — consecutive instants differ."""
    time.sleep(0.001)
    return datetime.now(timezone.utc)


def _row(symbol: str, *, tp: float, buy_in: float, price: float, internal_tp: float, internal_buy_in: float | None = None, **extra: Any) -> dict[str, Any]:
    """A producer row of Passo 1: the blend (``our_tp``/``buy_in``), the internal TP and — unless omitted, which mimics a
    cycle produced BEFORE Passo 1 — the internal buy-in the producer derived from it; the display fields the producer
    computes over the blend (upside, distance, weight, score, status) travel with the row."""
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


def _switch(database: Database, monkeypatch: pytest.MonkeyPatch, *, cycles: dict[str, str], targeted: dict[str, str] | None = None,
            reason: str = "P1 switch") -> tuple[dict[str, Any], dict[str, Any]]:
    """The mesa's order as it will be executed once the lock is flipped by the receipt's commit: the before/after receipt,
    then ``select_generation(source=SOURCE_INTERNAL, before_after_sha256=<its hash>)``. Returns ``(generation, report)``."""
    report = official.before_after_report(database)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    generation = official.select_generation(database, cycles=cycles, targeted=targeted, now=_wall(), activated_by="mesa", reason=reason,
                                            source=SOURCE_INTERNAL, source_version="7", before_after_sha256=report["report_sha256"])
    return generation, report


def test_the_constants_the_lock_and_the_pinned_one_pager() -> None:
    assert official.SOURCE_OFFICIAL == SOURCE_BLEND == "official_blend_v1" and official.SOURCE_INTERNAL == SOURCE_INTERNAL == "official_internal_v1"
    assert OFFICIAL_SOURCES == (SOURCE_BLEND, SOURCE_INTERNAL)
    # the lock is a literal in the module (it flips only by a commit citing the mesa's receipt), and this tree has it FALSE
    assert official.OFFICIAL_TP_REPLACEMENT_AUTHORIZED is False
    assert "\nOFFICIAL_TP_REPLACEMENT_AUTHORIZED = False" in (APP / "valuation_official.py").read_text(encoding="utf-8")
    # the pinned producer framework is not edited by Passo 1 (the mirror of its entry hurdle lives in the engine module)
    assert hashlib.sha256((APP / "one_pager.py").read_bytes()).hexdigest() == ORIGIN_ONE_PAGER_SHA256


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
    with pytest.raises(ValueError, match="unknown official source"):
        official.prediction_from_row(plain, market="NASDAQ", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, source="v3_2_shadow")
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
    report = official.before_after_report(database)  # the admission moved the head: the order cites the receipt of the generation in force (Q1)
    with pytest.raises(ValueError, match=f"targeted cycle for WEGE3 is not complete/valid/recorded for source {SOURCE_INTERNAL}"):
        official.select_generation(database, cycles=cycles, targeted={"WEGE3": wege_legacy}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                   before_after_sha256=report["report_sha256"])
    # the same cycles ARE selectable for the internal source once complete: the order lands (the legacy targeted cycle purged)
    switched = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL,
                                          source_version="7", before_after_sha256=report["report_sha256"])
    assert switched["source"] == SOURCE_INTERNAL and switched["cycles"] == cycles and official.official_row(database, "B3", "WEGE3") is None


def test_the_switch_is_refused_while_the_lock_is_false_and_without_the_receipt_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    report = official.before_after_report(database)
    assert official.OFFICIAL_TP_REPLACEMENT_AUTHORIZED is False
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
    assert row["score"] == 80.0 and row["status"] == "full_match" and row["expected_total_return_percent"] == 21.5  # the producer's blend view: the declared residue
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
    assert report["schema"] == "VALUATION_P1_BEFORE_AFTER_V1" and report["generation_id"] == generation["generation_id"] and report["generation_source"] == SOURCE_BLEND
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
    assert report["markets"]["NASDAQ"] == {"n": 1, "missing_internal": 0, "tp": {"median": pytest.approx(-0.02), "p90": pytest.approx(-0.02), "abs_median": pytest.approx(0.02), "abs_p90": pytest.approx(0.02)},
                                           "buy_in": {"median": pytest.approx(-0.02), "p90": pytest.approx(-0.02), "abs_median": pytest.approx(0.02), "abs_p90": pytest.approx(0.02)}}
    assert report["markets"]["NYSE"]["n"] == 1 and report["markets"]["NYSE"]["tp"]["median"] == pytest.approx(68.0 / 70.0 - 1)
    # the aggregate names no symbol; its hash is the canonical hash of everything but itself, and it is stable
    printable = json.dumps(report, sort_keys=True)
    assert not any(symbol in printable for symbol in ("PETR4", "VALE3", "ITUB4", "BBDC4", "AAPL", "KO"))
    assert report["report_sha256"] == official.canonical_sha256({key: value for key, value in report.items() if key != "report_sha256"}) and len(report["report_sha256"]) == 64
    assert official.before_after_report(database) == report
    # the detail exists only in the private file, named symbol by symbol, and its bytes hash to the aggregate's private_detail_sha256
    assert hashlib.sha256(detail_path.read_bytes()).hexdigest() == report["private_detail_sha256"]
    detail = json.loads(detail_path.read_text(encoding="utf-8"))
    assert detail["schema"] == "VALUATION_P1_BEFORE_AFTER_V1_DETAIL" and detail["generation_id"] == generation["generation_id"]
    assert detail["markets"]["B3"]["missing_internal"] == ["BBDC4"] and set(detail["markets"]["B3"]["pairs"]) == {"PETR4", "VALE3", "ITUB4"}
    assert detail["markets"]["B3"]["pairs"]["ITUB4"] == {"tp_blend": 30.0, "tp_internal": 33.0, "tp_ratio": pytest.approx(0.1), "buy_in_blend": 25.0, "buy_in_internal": 27.5, "buy_in_ratio": pytest.approx(0.1)}
    # a market with NO pair reports n = 0 and null statistics (never a fabricated number)
    empty = _database()
    _publish_universe(empty, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], NOW)
    _publish_universe(empty, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0, internal_buy_in=196.0)], NOW + timedelta(minutes=1))
    _publish_universe(empty, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0, internal_buy_in=58.0)], NOW + timedelta(minutes=2))
    assert official.before_after_report(empty)["markets"]["B3"] == {"n": 0, "missing_internal": 1, "tp": {"median": None, "p90": None, "abs_median": None, "abs_p90": None},
                                                                     "buy_in": {"median": None, "p90": None, "abs_median": None, "abs_p90": None}}
    # the CLI prints the aggregate only; the detail goes to --private-detail; --private-detail alone is refused
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    cli_detail = tmp_path / "cli_detail.json"
    assert official.main(["--before-after", "--private-detail", str(cli_detail)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(json.dumps(report)) and "PETR4" not in json.dumps(printed) and cli_detail.read_bytes() == detail_path.read_bytes()
    with pytest.raises(SystemExit):
        official.main(["--private-detail", str(cli_detail)])
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
    assert official.selection_health(database, now=_wall())["status"] == "ok" and official.selection_health(database, now=_wall())["unknown_source"] is None
    assert official.selection_health(_database(), now=_wall())["unknown_source"] is None  # every key explicit, without a generation too


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
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    report = official.before_after_report(database)
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
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    report = official.before_after_report(database)
    mixed = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, before_after_sha256=report["report_sha256"])
    assert mixed["source_version"] == "7+8"
    # the mesa's explicit declaration wins when given, on both paths
    report = official.before_after_report(database)
    rolled = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="rollback", source_version="7")
    assert rolled["source_version"] == "7"
    report = official.before_after_report(database)
    declared = official.select_generation(database, cycles=auto["cycles"], now=_wall(), activated_by="mesa", reason="switch", source=SOURCE_INTERNAL, source_version="8",
                                          before_after_sha256=report["report_sha256"])
    assert declared["source_version"] == "8" and declared["receipt"]["source_switch"]["from"] == SOURCE_BLEND
