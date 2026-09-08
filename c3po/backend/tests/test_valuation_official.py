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
    assert admitted["cycles"] == base["cycles"] and admitted["receipt"]["targeted_admission"] == {"symbol": "WEGE3", "cycle_id": first_targeted}
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
        official.select_generation(database, cycles={**base["cycles"], "B3": first_targeted}, now=NOW, activated_by="mesa", reason="bad")
    rolled = official.select_generation(database, cycles=base["cycles"], targeted={"WEGE3": first_targeted}, now=NOW + timedelta(minutes=30),
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
    rolled = official.select_generation(database, cycles=first["cycles"], now=NOW + timedelta(minutes=30), activated_by="mesa", reason="rollback drill")
    current = official.current_generation(database)
    assert current is not None and current == rolled and current["cycles"] == cycles and current["previous_generation_id"] == second["generation_id"]
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    with pytest.raises(ValueError):
        official.select_generation(database, cycles={**cycles, "NASDAQ": "not-a-cycle"}, now=NOW, activated_by="mesa", reason="bad")
    assert official.current_generation(database) == rolled


def test_identity_uses_the_market_session_and_records_carry_history_for_studies() -> None:
    # F393-6: the session is the market's own date, not the server's civil date; F393-7: records are the studies' history
    database = _database()
    late_night_utc = datetime(2026, 9, 8, 2, 30, tzinfo=timezone.utc)  # 23:30 in São Paulo, 22:30 in New York on 2026-09-07
    _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], late_night_utc)
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], late_night_utc)
    _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], late_night_utc)
    generation = official.current_generation(database)
    assert generation is not None and generation["session_dates"] == {"B3": "2026-09-07", "NASDAQ": "2026-09-07", "NYSE": "2026-09-07"}
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["session_date"] == "2026-09-07"  # type: ignore[index]
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], late_night_utc + timedelta(days=1))
    history = official.prediction_records(database, "US", "AAPL", source=official.SOURCE_OFFICIAL)
    assert [record["tp"] for record in history] == [260.0, 250.0] and all(record["source"] == official.SOURCE_OFFICIAL for record in history)
    from app.valuation_accuracy import load_prediction_calls
    calls = load_prediction_calls(history)
    assert [call.target_price for call in calls] == [260.0, 250.0] and calls[0].market == "US" and calls[0].price_at_call == 230.0
    assert calls[0].confidence == 70.0 and calls[0].changed_at.isoformat() == history[0]["prediction_instant"]
    snapshot = official.official_prediction_snapshot(database, "NASDAQ")
    assert snapshot and snapshot["outputs"]["results"]["AAPL"]["tp"] == 260.0 and snapshot["outputs"]["generation_id"] == official.current_generation(database)["generation_id"]  # type: ignore[index]
    from app.r2d2_entry_score_adapter import _target_price
    assert _target_price("official_prediction", snapshot["outputs"]["results"]["AAPL"]) == 260.0


def test_the_migration_defines_two_append_only_tables_with_targeted_admissions() -> None:
    sql = (Path(__file__).resolve().parents[2] / "db" / "048_valuation_official_tp.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_predictions" in sql and "CREATE TABLE IF NOT EXISTS valuation_official_selection" in sql
    assert "UNIQUE (source, source_version, market, symbol, cycle_id)" in sql and sql.count("BEFORE UPDATE OR DELETE") == 2
    assert "targeted JSONB NOT NULL DEFAULT '{}'::jsonb" in sql and "REFERENCES analysis_snapshots(id)" in sql
