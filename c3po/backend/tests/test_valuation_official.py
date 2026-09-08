"""Passo 0 of the official target price (Valuation Engine V3.2 rev 7, §7-bis): every producer cycle becomes immutable
prediction records FIRST; the official TP is a SELECTION by generation (one complete, validated, recorded cycle per
market, plus targeted admissions); what is served comes from the records; switching and rolling back are new
selections; consumers resolve ONE generation per request and never compute a TP of their own.
Rev 2 answers Codex 5577072593 (F393-1..F393-8)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_official as official
from app.config import Settings
from app.database import Database

NOW = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)


def later(minutes: int = 0) -> datetime:
    """Explicit selections (rollback) carry an activation clock that must not precede the current generation's (D3),
    which the automatic path stamps with the wall clock."""
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


class PgShapedDatabase(Database):
    """The PostgreSQL reader of ``latest_analysis_snapshot`` returned no ``analysis_type``/``entity_key`` (F393-1);
    this double reproduces that shape on top of the in-memory store."""

    def latest_analysis_snapshot(self, analysis_type: str, entity_key: str) -> dict[str, Any] | None:
        snapshot = super().latest_analysis_snapshot(analysis_type, entity_key)
        if snapshot is None:
            return None
        return {key: value for key, value in snapshot.items() if key not in ("analysis_type", "entity_key")}


def _row(symbol: str, *, tp: float, buy_in: float, price: float, internal_tp: float, **extra: object) -> dict:
    return {"symbol": symbol, "our_tp": tp, "buy_in": buy_in, "price": price, "internal_tp": internal_tp, "public_consensus_tp": tp * 1.1,
            "analyst_count": 12, "consensus_weight_percent": 25.0, "methods": {"dcf": tp * 1.01, "multiples": tp * 0.99},
            "calibration_factor": 1.02, "risk_score": 40.0, "valuation_confidence": 70.0, "method_dispersion_percent": 3.0,
            "signal_quality": "validated", "bear_tp": tp * 0.8, "bull_tp": tp * 1.2, "as_of": "2026-09-07T22:00:00+00:00", **extra}


def _publish_universe(database: Database, market: str, rows: list[dict], at: datetime, version: int = 7) -> str:
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1",
                                           {"methodology_version": version, "market": market, "source_manifest_sha256": "a" * 64},
                                           {"rows": rows, "universe_size": len(rows) + 1}, at)


def _three_markets(database: Database, at: datetime = NOW) -> dict[str, str]:
    return {
        "B3": _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0),
                                                 _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0)], at),
        "NASDAQ": _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], at + timedelta(minutes=1)),
        "NYSE": _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], at + timedelta(minutes=2)),
    }


def test_records_come_first_and_three_recorded_markets_activate_one_generation() -> None:
    database = _database()
    b3 = _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], NOW)
    assert official.current_generation(database) is None  # two markets missing: an incomplete generation is never selectable
    record = database.latest_valuation_prediction("B3", "PETR4", source=official.SOURCE_OFFICIAL)
    assert record and record["tp"] == 40.0 and record["cycle_id"] == b3 and record["scope"] == "universe" and record["currency"] == "BRL"
    assert record["bear_tp"] == 32.0 and record["bull_tp"] == 48.0 and record["decomposition"]["provenance"]["source_manifest_sha256"] == "a" * 64
    assert record["decomposition"]["weights"] == {"calibration_factor": 1.02, "convergence_weight": None, "consensus_weight_percent": 25.0}
    assert official.official_row(database, "B3", "PETR4") is None  # no generation yet: no official TP, even though a record exists
    nasdaq = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], NOW + timedelta(minutes=1))
    assert official.current_generation(database) is None
    nyse = _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], NOW + timedelta(minutes=2))
    generation = official.current_generation(database)
    assert generation and generation["validated_complete"] and generation["cycles"] == {"B3": b3, "NASDAQ": nasdaq, "NYSE": nyse}
    assert generation["targeted"] == {} and generation["previous_generation_id"] is None and generation["source_version"] == "7"
    row = official.official_row(database, "US", "AAPL")
    assert row and row["our_tp"] == 250.0 and row["buy_in"] == 200.0 and row["tp_source"] == official.SOURCE_OFFICIAL
    assert row["generation_id"] == generation["generation_id"] and row["official_cycle_id"] == nasdaq and row["official_market"] == "NASDAQ"
    assert row["official_row_sha256"] == database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["row_sha256"]  # type: ignore[index]
    assert official.official_row(database, "US", "MSFT") is None  # outside the universe: no TP — never computed by a consumer
    assert set(official.official_rows(database, "US")) == {"AAPL", "KO"} and set(official.official_rows(database, "B3")) == {"PETR4"}
    record = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert record is not None
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    assert record["row_sha256"] == official.canonical_sha256(core)
    assert database.insert_valuation_predictions([record]) == 0


def test_the_postgresql_shaped_reader_still_forms_a_generation() -> None:
    # F393-1: the PG path of latest_analysis_snapshot omits analysis_type/entity_key; validation must not depend on them
    database = PgShapedDatabase(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))
    cycles = _three_markets(database)
    generation = official.current_generation(database)
    assert generation is not None and generation["cycles"] == cycles
    assert official.official_row(database, "NYSE", "KO")["our_tp"] == 70.0  # type: ignore[index]


def test_a_new_cycle_of_one_market_is_a_new_generation_and_a_batch_pins_one_generation() -> None:
    database = _database()
    cycles = _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    later = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], NOW + timedelta(minutes=10))
    second = official.current_generation(database)
    assert second is not None and second["generation_id"] != first["generation_id"]
    assert second["cycles"] == {**cycles, "NYSE": later} and second["previous_generation_id"] == first["generation_id"]
    assert second["receipt"]["changed_markets"] == ["NYSE"]
    # F393-3: a request/batch resolves ONE generation and reads every market through it — never NASDAQ of G1 with NYSE of G2
    pinned = official.official_rows(database, "NYSE", generation=first)["KO"]
    assert pinned["our_tp"] == 70.0 and pinned["generation_id"] == first["generation_id"] and pinned["official_cycle_id"] == cycles["NYSE"]
    current = official.official_rows(database, "NYSE")["KO"]
    assert current["our_tp"] == 75.0 and current["generation_id"] == second["generation_id"] and current["official_cycle_id"] == later
    assert official.official_rows(database, "NASDAQ", generation=first)["AAPL"]["generation_id"] == first["generation_id"]
    assert database.valuation_official_selection(first["generation_id"]) == first  # history is readable


def test_what_is_served_is_the_record_not_the_snapshot_and_selection_never_precedes_records() -> None:
    # F393-5 (a): the served number comes from the immutable record; an edited snapshot cannot change it
    database = _database()
    cycles = _three_markets(database)
    generation = official.current_generation(database)
    assert generation is not None
    stored = next(item for item in database._analysis_snapshots if item["id"] == cycles["NASDAQ"])
    stored["outputs"]["rows"][0]["our_tp"] = 999.0  # a mutated snapshot (memory) — the record still says 250
    database.drop_official_cycle_cache()
    assert official.official_row(database, "NASDAQ", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    assert official.official_rows(database, "NASDAQ")["AAPL"]["official_row_sha256"] == database.valuation_predictions_for_cycle(cycles["NASDAQ"])["AAPL"]["row_sha256"]
    # F393-5 (b): a cycle whose records are not yet written is NOT selectable, whatever thread looks at it
    unrecorded = {"id": "cycle-without-records", "analysis_type": "valuation_universe", "entity_key": "NYSE_UNIVERSE", "methodology_version_id": "mv-1",
                  "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("KO", tp=80.0, buy_in=66.0, price=67.0, internal_tp=79.0)], "universe_size": 2},
                  "published_at": NOW + timedelta(minutes=30)}
    database._analysis_snapshots.append(unrecorded)  # bypasses the hook: snapshot exists, records do not
    assert official.selectable_cycles(database)["NYSE"]["unrecorded_count"] == 1 and official.selectable_cycles(database)["NYSE"]["valid"] is False
    assert official.activate_generation_if_changed(database, now=NOW + timedelta(minutes=31)) is None
    assert official.current_generation(database) == generation and official.official_row(database, "NYSE", "KO")["our_tp"] == 70.0  # type: ignore[index]


def test_a_cycle_with_an_unusable_row_never_becomes_the_official_selection() -> None:
    database = _database()
    _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    broken = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=270.0, buy_in=215.0, price=230.0, internal_tp=265.0),
                                                     {**_row("NVDA", tp=900.0, buy_in=700.0, price=800.0, internal_tp=880.0), "buy_in": None}],
                               NOW + timedelta(minutes=20))
    assert official.current_generation(database) == first  # consistency wins: the whole cycle is not selectable
    assert database.latest_valuation_prediction("NASDAQ", "NVDA", source=official.SOURCE_OFFICIAL) is None
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["cycle_id"] == broken  # type: ignore[index]
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    validation = official.selectable_cycles(database)["NASDAQ"]
    assert validation["valid"] is False and validation["invalid_count"] == 1 and validation["invalid_rows"] == ["NVDA"]


def test_targeted_valuations_become_official_only_through_the_selection() -> None:
    # F393-4: a targeted (on-demand) B3 valuation is admitted by a NEW generation; a new number is a new generation id;
    # an old generation keeps serving its own value; nothing outside the generation is ever served
    database = _database()
    _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    assert official.official_row(database, "B3", "WEGE3") is None
    first_targeted = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                                     {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, NOW + timedelta(minutes=11))
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["generation_id"] != base["generation_id"] and admitted["targeted"] == {"WEGE3": first_targeted}
    assert admitted["cycles"] == base["cycles"] and admitted["receipt"]["targeted_admission"]["symbol"] == "WEGE3"
    assert admitted["receipt"]["targeted_admission"]["cycle_id"] == first_targeted and admitted["receipt"]["targeted_admission"]["validation"]["valid"] is True
    served = official.official_row(database, "B3", "wege3.sa")
    assert served and served["our_tp"] == 50.0 and served["official_scope"] == "targeted" and served["generation_id"] == admitted["generation_id"]
    assert official.official_row(database, "B3", "WEGE3", generation=base) is None  # the base generation never admitted it
    second_targeted = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                                      {"row": _row("WEGE3", tp=90.0, buy_in=70.0, price=80.0, internal_tp=88.0)}, NOW + timedelta(minutes=12))
    newest = official.current_generation(database)
    assert newest is not None and newest["generation_id"] != admitted["generation_id"] and newest["targeted"] == {"WEGE3": second_targeted}
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 90.0  # type: ignore[index]
    assert official.official_row(database, "B3", "WEGE3", generation=admitted)["our_tp"] == 50.0  # type: ignore[index]  # identity preserved
    assert official.official_row(database, "US", "WEGE3") is None  # a B3 targeted row is never served for a US request
    with pytest.raises(ValueError):  # a targeted cycle is not a universe cycle: rollback refuses it as a market cycle
        official.select_generation(database, cycles={**base["cycles"], "B3": first_targeted}, now=later(1), activated_by="mesa", reason="bad")
    rolled = official.select_generation(database, cycles=base["cycles"], targeted={"WEGE3": first_targeted}, now=later(2),
                                        activated_by="mesa", reason="rollback drill")
    assert official.current_generation(database) == rolled and rolled["targeted"] == {"WEGE3": first_targeted}
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]


def test_rollback_is_a_new_selection_over_existing_complete_recorded_cycles() -> None:
    database = _database()
    cycles = _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], NOW + timedelta(minutes=10))
    second = official.current_generation(database)
    assert second is not None
    rolled = official.select_generation(database, cycles=first["cycles"], now=later(1), activated_by="mesa", reason="rollback drill")
    current = official.current_generation(database)
    assert current is not None and current == rolled and current["cycles"] == cycles and current["previous_generation_id"] == second["generation_id"]
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    with pytest.raises(ValueError):
        official.select_generation(database, cycles={**cycles, "NASDAQ": "not-a-cycle"}, now=later(2), activated_by="mesa", reason="bad")
    with pytest.raises(ValueError, match="missing: NYSE"):  # F1: a partial cycle map is a ValueError, never a KeyError
        official.select_generation(database, cycles={"B3": cycles["B3"], "NASDAQ": cycles["NASDAQ"]}, now=later(2), activated_by="mesa", reason="bad")
    with pytest.raises(ValueError, match="earlier than the current generation"):  # D3: an explicit clock behind the chain is refused
        official.select_generation(database, cycles=first["cycles"], now=NOW, activated_by="mesa", reason="stale clock")
    assert official.current_generation(database) == rolled


def test_identity_uses_the_market_session_and_records_carry_history_for_studies() -> None:
    # F393-6: the session is the last COMPLETED session of the market's exchange calendar, not any civil date;
    # F393-7: records are the studies' history
    database = _database()
    late_night_utc = datetime(2026, 9, 8, 2, 30, tzinfo=timezone.utc)  # 23:30 in São Paulo, 22:30 in New York on Monday 2026-09-07
    _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], late_night_utc)
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], late_night_utc)
    _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], late_night_utc)
    generation = official.current_generation(database)
    # 2026-09-07 is Labor Day (XNYS) and Independence Day (BVMF): the last completed session is Friday 2026-09-04
    assert generation is not None and generation["session_dates"] == {"B3": "2026-09-04", "NASDAQ": "2026-09-04", "NYSE": "2026-09-04"}
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["session_date"] == "2026-09-04"  # type: ignore[index]
    assert official.session_date_of("NASDAQ", datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)) == "2026-09-04"  # Sunday is not a session
    assert official.session_date_of("NASDAQ", datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)) == "2026-09-08"  # intraday Wednesday: Tuesday closed
    assert official.session_date_of("NASDAQ", datetime(2026, 9, 9, 20, 0, tzinfo=timezone.utc)) == "2026-09-09"  # at the close: that session
    assert official.session_date_of("B3", datetime(2026, 9, 9, 20, 30, tzinfo=timezone.utc)) == "2026-09-08"  # B3 closes 21:00Z: still Tuesday
    assert official.session_date_of("B3", datetime(2026, 9, 9, 21, 0, tzinfo=timezone.utc)) == "2026-09-09"
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], late_night_utc + timedelta(days=1))
    history = official.prediction_records(database, "US", "AAPL", source=official.SOURCE_OFFICIAL)
    assert [record["tp"] for record in history] == [260.0, 250.0] and all(record["source"] == official.SOURCE_OFFICIAL for record in history)
    from app.valuation_accuracy import calls_by_source, load_prediction_calls
    calls = load_prediction_calls(history)
    assert [call.target_price for call in calls] == [260.0, 250.0] and calls[0].market == "US" and calls[0].price_at_call == 230.0
    assert calls[0].confidence == 70.0 and calls[0].changed_at.isoformat() == history[0]["prediction_instant"]
    # F393-7: the conversion keeps the identity of every call (producer, version, cycle, record hash) and grades by producer
    assert calls[0].source == official.SOURCE_OFFICIAL and calls[0].source_version == "7" and calls[0].cycle_id == history[0]["cycle_id"]
    assert calls[0].row_sha256 == history[0]["row_sha256"] and set(calls_by_source(calls)) == {"official_blend_v1:7"}
    snapshot = official.official_prediction_snapshot(database, "NASDAQ")
    assert snapshot and snapshot["outputs"]["results"]["AAPL"]["tp"] == 260.0 and snapshot["outputs"]["generation_id"] == official.current_generation(database)["generation_id"]  # type: ignore[index]
    assert snapshot["outputs"]["source_version"] == "7" and snapshot["outputs"]["session_date"] == "2026-09-08" and snapshot["outputs"]["cycle_id"]  # Tuesday 08/09 closed
    from app.r2d2_entry_score_adapter import _target_price
    assert _target_price("official_prediction", snapshot["outputs"]["results"]["AAPL"]) == 260.0


def test_the_migration_defines_two_append_only_tables_with_targeted_admissions() -> None:
    sql = (Path(__file__).resolve().parents[2] / "db" / "048_valuation_official_tp.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_predictions" in sql and "CREATE TABLE IF NOT EXISTS valuation_official_selection" in sql
    assert "UNIQUE (source, source_version, market, symbol, cycle_id)" in sql and sql.count("BEFORE UPDATE OR DELETE") == 2
    assert "targeted JSONB NOT NULL DEFAULT '{}'::jsonb" in sql and "REFERENCES analysis_snapshots(id)" in sql
    assert "valuation_predictions_by_cycle" in sql and "ON valuation_predictions (cycle_id)" in sql  # D2: the served read is by cycle
    assert "CREATE UNIQUE INDEX IF NOT EXISTS valuation_official_selection_chain" in sql and "WHERE previous_generation_id IS NOT NULL" in sql  # B2


def test_a_caller_that_resolved_no_generation_is_served_nothing_and_never_the_current_one() -> None:
    # F393-3: `None` is "resolved, none in force" — not "resolve it for me"; only UNRESOLVED (the default) reads the current generation
    database = _database()
    _three_markets(database)
    assert official.official_rows(database, "NASDAQ", generation=None) == {} and official.official_row(database, "US", "AAPL", generation=None) is None
    assert official.official_stamp(database, "NASDAQ", generation=None)["official_generation_id"] is None
    assert official.official_prediction_snapshot(database, "NASDAQ", generation=None) is None
    assert official.official_rows(database, "NASDAQ")["AAPL"]["our_tp"] == 250.0  # the default resolves the current generation
    stamp = official.official_stamp(database, "NASDAQ")
    assert stamp["tp_source_version"] == "7" and stamp["official_session_date"] == "2026-09-04" and stamp["official_cycle_id"]
    item = official.item_stamp(official.official_row(database, "US", "AAPL"))
    assert set(item) == {"tp_source", "official_generation_id", "official_cycle_id", "tp_source_version", "official_session_date", "prediction_instant", "official_row_sha256"}
    assert item["official_row_sha256"] and official.item_stamp(None) == {key: None for key in item}


def test_targeted_admission_requires_a_valid_cycle_and_a_symbol_the_universe_does_not_serve() -> None:
    # F393-4: automatic admission applies the validator; A1: a symbol already served by the universe cycle is not admitted
    database = _database()
    _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                    {"row": {**_row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0), "price": 0, "internal_tp": None}}, later(1))
    assert official.current_generation(database) == base and official.official_row(database, "B3", "WEGE3") is None  # price=0: refused, no generation
    database.save_analysis_snapshot("security_valuation", "PETR4", "mv-1", {"methodology_version": 7},
                                    {"row": _row("PETR4", tp=90.0, buy_in=70.0, price=80.0, internal_tp=88.0)}, later(2))
    assert official.current_generation(database) == base  # PETR4 is in the B3 universe cycle: the universe answers first, no churn
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0  # type: ignore[index]
    good = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7, "source_manifest_sha256": "b" * 64},
                                           {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(3))
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"WEGE3": good} and admitted["validated_complete"] is True
    served = official.official_row(database, "B3", "WEGE3")
    assert served and served["official_scope"] == "targeted" and served["official_row_sha256"] == database.valuation_prediction_record(good, "WEGE3")["row_sha256"]  # type: ignore[index]
    assert database.valuation_prediction_record(good, "WEGE3")["decomposition"]["provenance"]["source_manifest_sha256"] == "b" * 64  # type: ignore[index]


def test_activation_carries_a_market_over_when_its_new_cycle_is_invalid() -> None:
    # B1: one market's bad night no longer strips the other two of their official stamp — the old B3 cycle stays in force
    database = _database()
    cycles = _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    _publish_universe(database, "B3", [{**_row("PETR4", tp=41.0, buy_in=33.0, price=36.0, internal_tp=40.0), "buy_in": None}], later(1))  # invalid B3 cycle
    assert official.current_generation(database) == first  # nothing changed elsewhere: no new generation
    nasdaq2 = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=255.0, buy_in=205.0, price=222.0, internal_tp=250.0)], later(2))
    second = official.current_generation(database)
    assert second is not None and second["generation_id"] != first["generation_id"]
    assert second["cycles"] == {**cycles, "NASDAQ": nasdaq2} and second["receipt"]["carried_markets"] == ["B3"] and second["receipt"]["changed_markets"] == ["NASDAQ"]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0 and official.official_row(database, "US", "AAPL")["our_tp"] == 255.0  # type: ignore[index]
    health = official.selection_health(database, now=later(3))
    assert health["status"] in {"ok", "stale"} and health["markets"]["B3"]["carried"] is True and health["generation_id"] == second["generation_id"]
    # bootstrap still needs every market once: an empty store activates nothing
    empty = _database()
    _publish_universe(empty, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], later(1))
    assert official.current_generation(empty) is None and official.selection_health(empty, now=later(1))["status"] == "none"


def test_an_empty_answer_is_never_pinned_and_served_objects_are_copies() -> None:
    # D1: the window between a cycle's publication and its records (another process) must not poison this process
    database = _database()
    pending = {"id": "cycle-pending", "analysis_type": "valuation_universe", "entity_key": "NYSE_UNIVERSE", "methodology_version_id": "mv-1",
               "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], "universe_size": 2},
               "published_at": NOW}
    database._analysis_snapshots.append(pending)  # published, records not yet written
    assert database.valuation_predictions_for_cycle("cycle-pending") == {} and "cycle-pending" not in database._cycle_records_cache
    official.record_snapshot(database, pending, now=later(1))  # the other process finishes
    assert database.valuation_predictions_for_cycle("cycle-pending")["KO"]["tp"] == 70.0
    # F393-5: what a caller receives is a copy — mutating it changes neither the cache nor the next answer
    _three_markets(database)
    served = official.official_rows(database, "NASDAQ")["AAPL"]
    served["our_tp"] = 999.0
    served["methods"]["dcf"] = 0.0
    assert official.official_rows(database, "NASDAQ")["AAPL"]["our_tp"] == 250.0 and official.official_rows(database, "NASDAQ")["AAPL"]["methods"]["dcf"] == 252.5
    records = database.valuation_predictions_for_cycle(official.current_generation(database)["cycles"]["NASDAQ"])  # type: ignore[index]
    records["AAPL"]["tp"] = 1.0
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    generation = official.current_generation(database)
    assert generation is not None
    generation["cycles"]["NASDAQ"] = "tampered"
    assert official.current_generation(database)["cycles"]["NASDAQ"] != "tampered"  # type: ignore[index]
    # a cache MISS is a copy too (REV4-2): mutating the first answer never reaches the master snapshot
    database.drop_official_cycle_cache()
    cycle = official.current_generation(database)["cycles"]["B3"]  # type: ignore[index]
    first = database.official_cycle_snapshot(cycle)
    assert first is not None
    first["outputs"]["rows"][0]["our_tp"] = 999999.0
    assert database.analysis_snapshot_by_id(cycle)["outputs"]["rows"][0]["our_tp"] == 40.0  # type: ignore[index]
    assert database.official_cycle_snapshot(cycle)["outputs"]["rows"][0]["our_tp"] == 40.0  # type: ignore[index]
    # a single-symbol read copies ONE record (REV4-5) and agrees with the whole-cycle read
    one = database.valuation_prediction_record(cycle, "PETR4")
    assert one is not None and one["tp"] == 40.0 and database.valuation_prediction_record(cycle, "NOPE") is None
    one["tp"] = 1.0
    assert database.valuation_prediction_record(cycle, "PETR4")["tp"] == 40.0  # type: ignore[index]


def test_the_generation_chain_refuses_a_second_successor_and_orders_like_postgresql() -> None:
    # B2: two writers extending the same predecessor — the second insert conflicts (memory double = UNIQUE index in PG)
    database = _database()
    _three_markets(database)
    current = official.current_generation(database)
    assert current is not None
    from app.database import SelectionConflict
    clone = {**current, "generation_id": "another-successor", "previous_generation_id": current["previous_generation_id"]}
    if current["previous_generation_id"] is None:  # the first generation has no predecessor: chain from it instead
        clone["previous_generation_id"] = current["generation_id"]
        database.insert_valuation_official_selection({**clone, "generation_id": "first-successor", "activated_at": later(1).isoformat()})
    with pytest.raises(SelectionConflict):
        database.insert_valuation_official_selection({**clone, "activated_at": later(2).isoformat()})
    # D3: the double orders by (activated_at, insertion) exactly as PostgreSQL's ORDER BY activated_at DESC, created_at DESC
    older = {**clone, "generation_id": "older-clock", "previous_generation_id": "first-successor", "activated_at": NOW.isoformat()}
    database.insert_valuation_official_selection(older)
    assert official.current_generation(database)["generation_id"] == "first-successor"  # type: ignore[index]
    assert official.generation_at(database, NOW)["generation_id"] == "older-clock"  # type: ignore[index]
    assert official.generation_at(database, NOW - timedelta(days=1)) is None


def test_studies_replay_the_generation_in_force_at_the_decision_not_the_current_one() -> None:
    # F393-7: after a switch, a past decision still reads the generation that served it
    database = _database()
    _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    import time
    time.sleep(0.002)
    decided_at = datetime.now(timezone.utc)  # a decision taken while the first generation was in force
    time.sleep(0.002)
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=300.0, buy_in=240.0, price=250.0, internal_tp=290.0)], later(2))
    second = official.current_generation(database)
    assert second is not None and second["generation_id"] != first["generation_id"]
    assert official.generation_at(database, decided_at)["generation_id"] == first["generation_id"]  # type: ignore[index]
    replay = official.official_prediction_snapshot(database, "NASDAQ", generation=official.generation_at(database, decided_at))
    assert replay and replay["outputs"]["results"]["AAPL"]["tp"] == 250.0 and replay["outputs"]["generation_id"] == first["generation_id"]
    assert official.official_prediction_snapshot(database, "NASDAQ")["outputs"]["results"]["AAPL"]["tp"] == 300.0  # type: ignore[index]


def test_bootstrap_records_the_persisted_cycles_and_activates_the_first_generation() -> None:
    database = _database()
    for market, rows in {"B3": [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)],
                         "NASDAQ": [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)],
                         "NYSE": [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)]}.items():
        database._analysis_snapshots.append({"id": f"pre-{market}", "analysis_type": "valuation_universe", "entity_key": f"{market}_UNIVERSE",
                                             "methodology_version_id": "mv-1", "inputs": {"methodology_version": 7}, "outputs": {"rows": rows, "universe_size": 1},
                                             "published_at": NOW})  # cycles persisted BEFORE Passo 0 was deployed: no records, no generation
    assert official.current_generation(database) is None
    result = official.bootstrap_official_selection(database, now=later(1))
    assert result["recorded"] == {"B3": 1, "NASDAQ": 1, "NYSE": 1} and result["generation"]["cycles"] == {"B3": "pre-B3", "NASDAQ": "pre-NASDAQ", "NYSE": "pre-NYSE"}
    again = official.bootstrap_official_selection(database, now=later(2))  # idempotent
    assert again["recorded"] == {"B3": 0, "NASDAQ": 0, "NYSE": 0} and again["generation"]["generation_id"] == result["generation"]["generation_id"]
    assert official.provenance_sha256([_row("PETR4", tp=1.0, buy_in=1.0, price=1.0, internal_tp=1.0)]) == official.provenance_sha256(
        [{"symbol": "petr4", "as_of": "2026-09-07T22:00:00+00:00"}])  # E1: the manifest is the provenance, not the numbers
