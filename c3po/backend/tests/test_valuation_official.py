"""Passo 0 of the official target price (Valuation Engine V3.2 rev 7, §7-bis): every producer cycle becomes immutable
prediction records FIRST; the official TP is a SELECTION by generation (one complete, validated, recorded cycle per
market, plus targeted admissions); what is served comes from the records; switching and rolling back are new
selections; consumers resolve ONE generation per request and never compute a TP of their own.
Rev 2 answers Codex 5577072593 (F393-1..F393-8); rev 5 closes the residuals on rev 4 (F393-4, F393-5, F393-6 a/b/c,
F393-7, F393-9) — see the tests marked "rev 5"; rev 6 closes B2 (two clocks on the record) and B3 (the explicit order
governs the direct admission) — the tests marked "rev 6" — and its residuals S1–S5, S8, S9 (the authority clock is the
prediction instant; recency on the direct admission; the CHECK mirrored; readers tie-break like the selection; unrecordable
re-runs warn once; a malformed published_at keeps the call; the idempotent column block of the migration) at the end; rev 7
closes F393-11 (the migration never backfills a legacy table; every reader honours the STORED schema — a V1 row is verified and
served as V1, never relabelled V2) — the tests marked "rev 7", last."""
from __future__ import annotations

import copy
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pytest

from app import valuation_official as official
from app.config import Settings
from app.database import Database

NOW = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)


def later(seconds: int = 0) -> datetime:
    """Explicit selections (rollback) carry an activation clock that must not precede the current generation's (D3),
    which the automatic path stamps with the wall clock — nor run ahead of the wall clock by more than 60 s (W2):
    hence seconds, never minutes."""
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


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
    # F393-5 (b): selection never precedes the records. A cycle whose records are still being written by another
    # process (SOME recorded, D1) is NOT selectable, whatever thread looks at it...
    partial = {"id": "cycle-half-recorded", "analysis_type": "valuation_universe", "entity_key": "NYSE_UNIVERSE", "methodology_version_id": "mv-1",
               "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("KO", tp=80.0, buy_in=66.0, price=67.0, internal_tp=79.0),
                                                                          _row("PEP", tp=90.0, buy_in=70.0, price=75.0, internal_tp=88.0)], "universe_size": 2},
               "published_at": NOW + timedelta(minutes=30)}
    database._analysis_snapshots.append(partial)  # bypasses the hook: snapshot exists...
    ko = official.prediction_from_row(partial["outputs"]["rows"][0], market="NYSE", scope="universe", cycle_id="cycle-half-recorded", source_version="7",
                                      prediction_instant=partial["published_at"])
    assert ko is not None and database.insert_valuation_predictions([ko]) == 1  # ...one record landed, the other is still in flight
    assert official.selectable_cycles(database)["NYSE"]["unrecorded_count"] == 1 and official.selectable_cycles(database)["NYSE"]["valid"] is False
    assert official.activate_generation_if_changed(database) is None
    assert official.current_generation(database) == generation and official.official_row(database, "NYSE", "KO")["our_tp"] == 70.0  # type: ignore[index]
    assert database.valuation_predictions_for_cycle("cycle-half-recorded").keys() == {"KO"}  # the pass wrote nothing into a half-written cycle
    # ...while a cycle with NO record at all (published while nothing was recordable, X4) is recorded BY the activation pass
    # before it is validated — the records exist before the selection that points at them, never the other way round
    unrecorded = {**partial, "id": "cycle-without-records", "outputs": {"rows": [_row("KO", tp=81.0, buy_in=67.0, price=68.0, internal_tp=80.0)], "universe_size": 2},
                  "published_at": NOW + timedelta(minutes=40)}
    database._analysis_snapshots.append(unrecorded)
    assert database.valuation_predictions_for_cycle("cycle-without-records") == {}
    recovered = official.activate_generation_if_changed(database)
    assert recovered is not None and recovered["cycles"]["NYSE"] == "cycle-without-records" and recovered["receipt"]["validation"]["NYSE"]["unrecorded_count"] == 0
    record = database.valuation_predictions_for_cycle("cycle-without-records")["KO"]
    assert record["tp"] == 81.0 and record["session_date"] == official.session_date_of("NYSE", NOW + timedelta(minutes=40))
    assert official.official_row(database, "NYSE", "KO")["official_row_sha256"] == record["row_sha256"]  # type: ignore[index]


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
    # F393-9 (rev 5): the root escapes the partial chain index, so a second partial unique index admits ONE root
    assert "CREATE UNIQUE INDEX IF NOT EXISTS valuation_official_selection_root" in sql
    assert "ON valuation_official_selection ((1)) WHERE previous_generation_id IS NULL" in sql
    # rev 6 (B2): the record's own publication clock is a NOT NULL column that can never precede the prediction's instant
    assert "prediction_instant TIMESTAMPTZ NOT NULL" in sql
    assert "published_at TIMESTAMPTZ NOT NULL CONSTRAINT valuation_predictions_published_at_check CHECK (published_at >= prediction_instant)" in sql
    # S9 / F393-11 a (rev 7): CREATE TABLE IF NOT EXISTS never alters a table created before the column, and every migration runs on
    # every start — an idempotent block at the END decides BY THE TABLE and never rewrites a legacy row: the rev 6 backfill
    # (published_at = prediction_instant under a suspended trigger) relabelled V1 rows under a hash nobody could recompute.
    statements = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))  # the comments may NAME what was removed
    assert "UPDATE valuation_predictions" not in statements and "DISABLE TRIGGER" not in statements and "ENABLE TRIGGER" not in statements  # no backfill, no trigger suspended
    assert "ADD COLUMN IF NOT EXISTS" not in statements and "SET NOT NULL" not in statements  # the column is never added blind, never hardened over rows
    assert "published_at = prediction_instant" not in statements
    tail = sql[sql.rindex("CREATE TRIGGER"):]
    block = tail[tail.index("DO $$"):]
    # the column lookup guards everything: pg_attribute (regclass, search-path aware, as the pg_constraint lookup)
    assert "FROM pg_attribute" in block and "attname = 'published_at'" in block and "NOT attisdropped" in block
    # column missing + rows → RAISE EXCEPTION naming the row count (%) and the operator path (explicit order, never automatic)
    assert "SELECT count(*) INTO legacy_rows FROM valuation_predictions;" in block and "IF legacy_rows > 0 THEN" in block
    raise_text = block[block.index("RAISE EXCEPTION"):block.index("END IF;")]
    assert "holds % legacy VALUATION_PREDICTION_V1 row(s)" in raise_text and ", legacy_rows" in raise_text and "F393-11 a" in raise_text
    assert "USING HINT" in raise_text and "by explicit order only" in raise_text and "never an in-place rewrite" in raise_text
    assert "COPY valuation_predictions TO" in raise_text and "inputs.rerun_of" in raise_text  # export + re-run keeps a verifiable identity
    assert "ALTER TABLE valuation_predictions ADD COLUMN published_at TIMESTAMPTZ)" in raise_text and "WITHOUT backfill" in raise_text  # or nullable, read as V1
    assert 'docs/VALUATION_OFFICIAL_TP_V1.md, section "Linhas legadas V1"' in raise_text
    assert raise_text.count("%") == 1  # the single placeholder is the row count: no stray % in the format string
    # column missing + empty table → the column is added NOT NULL directly, after the RAISE guard, inside the same IF
    add_column = "ALTER TABLE valuation_predictions ADD COLUMN published_at TIMESTAMPTZ NOT NULL;"
    assert add_column in block and block.index("RAISE EXCEPTION") < block.index(add_column) < block.index("FROM pg_constraint")
    assert block[block.index("RAISE EXCEPTION"):block.index(add_column)].count("END IF;") == 1  # after the RAISE guard closes...
    assert block[block.index(add_column):block.index("FROM pg_constraint")].count("END IF;") == 1  # ...and still inside the column-missing IF
    # column present → only the named CHECK is ensured (guarded by pg_constraint), one CHECK text in the block, nothing else
    assert "FROM pg_constraint" in block and "conname = 'valuation_predictions_published_at_check'" in block
    assert "ADD CONSTRAINT valuation_predictions_published_at_check" in block and block.count("CHECK (published_at >= prediction_instant)") == 1
    executed = block.replace(raise_text, "")  # the statements the block can run (the HINT only quotes the operator's ALTER)
    assert executed.count("ALTER TABLE") == 2 and executed.count("IF NOT EXISTS") == 2  # the column (guarded) and the constraint (guarded)


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
    assert set(item) == {"tp_source", "official_generation_id", "official_cycle_id", "tp_source_version", "official_session_date", "prediction_instant", "official_row_sha256",
                         "official_published_at"}  # rev 6 (B2): the record's own publication clock travels with every served item
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
    official.record_snapshot(database, pending)  # the other process finishes
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
    result = official.bootstrap_official_selection(database)
    assert result["recorded"] == {"B3": 1, "NASDAQ": 1, "NYSE": 1} and result["generation"]["cycles"] == {"B3": "pre-B3", "NASDAQ": "pre-NASDAQ", "NYSE": "pre-NYSE"}
    again = official.bootstrap_official_selection(database)  # idempotent
    assert again["recorded"] == {"B3": 0, "NASDAQ": 0, "NYSE": 0} and again["generation"]["generation_id"] == result["generation"]["generation_id"]
    assert official.provenance_sha256([_row("PETR4", tp=1.0, buy_in=1.0, price=1.0, internal_tp=1.0)]) == official.provenance_sha256(
        [{"symbol": "petr4", "as_of": "2026-09-07T22:00:00+00:00"}])  # E1: the manifest is the provenance, not the numbers


# ----------------------------------------------------------------------------------------------------- rev 5 (Codex residuals on rev 4)


def test_an_explicit_selection_validates_targeted_cycles_like_the_automatic_admission() -> None:
    # F393-4 (rev 5): select_generation used to accept a targeted cycle that had a record but failed the validator
    # (price = 0, no internal TP) — the automatic path refused it, the explicit one marked the generation complete
    database = _database()
    _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    bad = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                          {"row": {**_row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0), "price": 0, "internal_tp": None}}, later(1))
    assert "WEGE3" in database.valuation_predictions_for_cycle(bad)  # a record exists (TP and buy-in are positive)...
    assert official.current_generation(database) == base  # ...but the automatic admission refused the cycle
    with pytest.raises(ValueError, match="targeted cycle for WEGE3 is not complete/valid/recorded"):
        official.select_generation(database, cycles=base["cycles"], targeted={"WEGE3": bad}, now=later(2), activated_by="mesa", reason="bad")
    assert official.current_generation(database) == base and official.official_row(database, "B3", "WEGE3") is None
    good = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                           {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(3))
    rolled = official.select_generation(database, cycles=base["cycles"], targeted={"WEGE3": good}, now=later(4), activated_by="mesa", reason="ok")
    assert rolled["targeted"] == {"WEGE3": good} and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]


def test_the_store_is_sealed_against_the_callers_structures_on_insert_and_on_cold_reads() -> None:
    # F393-5 (rev 5): insert and cold returns shared nested structures with the caller; mutating a decomposition after
    # the insert changed what was retained under the old hash, and clearing the producer's rows list emptied the cycle
    database = _database()
    rows = [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0), _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0)]
    outputs = {"rows": rows, "universe_size": 3}
    b3 = database.save_analysis_snapshot("valuation_universe", "B3_UNIVERSE", "mv-1", {"methodology_version": 7}, outputs, NOW)
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], NOW + timedelta(minutes=1))
    _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], NOW + timedelta(minutes=2))
    rows.clear()  # the producer reuses / clears its own list after publishing
    outputs["rows"] = []
    database.drop_official_cycle_cache()  # rebuild the caches from the store
    assert set(official.official_rows(database, "B3")) == {"PETR4", "VALE3"}
    assert len(database.analysis_snapshot_by_id(b3)["outputs"]["rows"]) == 2  # type: ignore[index]
    # a record mutated by its inserter after the insert: the store keeps what was hashed
    record = official.prediction_from_row(_row("ITUB4", tp=30.0, buy_in=25.0, price=27.0, internal_tp=29.0), market="B3", scope="targeted",
                                          cycle_id="cycle-x", source_version="7", prediction_instant=NOW)
    assert record is not None
    dcf, bands = record["decomposition"]["methods"]["dcf"], dict(record["decomposition"]["bands"])
    assert database.insert_valuation_predictions([record]) == 1
    record["tp"] = 1.0
    record["decomposition"]["methods"]["dcf"] = 0.0
    stored = database.valuation_prediction_record("cycle-x", "ITUB4")
    assert stored is not None and stored["tp"] == 30.0 and stored["decomposition"]["methods"]["dcf"] == dcf
    # every cold return is a deep copy: mutating it changes neither the store nor the next answer
    database.drop_official_cycle_cache()
    cold = database.valuation_predictions_for_cycle("cycle-x")
    cold["ITUB4"]["decomposition"]["methods"]["dcf"] = -1.0
    database.drop_official_cycle_cache()
    assert database.valuation_predictions_for_cycle("cycle-x")["ITUB4"]["decomposition"]["methods"]["dcf"] == dcf
    listed = database.list_valuation_predictions("B3", "ITUB4")[0]
    listed["decomposition"]["bands"]["bear_tp"] = -1.0
    latest = database.latest_valuation_prediction("B3", "ITUB4", source=official.SOURCE_OFFICIAL)
    assert latest is not None
    latest["decomposition"]["bands"]["bull_tp"] = -1.0
    assert database.latest_valuation_prediction("B3", "ITUB4", source=official.SOURCE_OFFICIAL)["decomposition"]["bands"] == bands  # type: ignore[index]
    by_id = database.analysis_snapshot_by_id(b3)
    assert by_id is not None
    by_id["outputs"]["rows"].clear()
    latest_snapshot = database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
    assert latest_snapshot is not None
    latest_snapshot["outputs"]["rows"][0]["our_tp"] = 0.0
    assert [row["our_tp"] for row in database.analysis_snapshot_by_id(b3)["outputs"]["rows"]] == [40.0, 70.0]  # type: ignore[index]
    assert database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")["outputs"]["rows"][0]["our_tp"] == 40.0  # type: ignore[index]


def _pg_row(record: dict[str, Any], zone: ZoneInfo) -> tuple[Any, ...]:
    """The SELECT column tuple PostgreSQL hands ``Database._prediction_record`` for a stored record: NUMERIC → Decimal
    (the digits the writer bound), DATE::text, TIMESTAMPTZ in the SESSION time zone, JSONB → parsed JSON."""
    numeric = Database._numeric_param
    available = record.get("published_at")  # rev 6 (B2): the second clock, a TIMESTAMPTZ column too; NULL on a legacy V1 row (rev 7, F393-11)
    return (record["id"], record["source"], record["source_version"], record["market"], record["symbol"], record["scope"],
            record["session_date"], record["cycle_id"], datetime.fromisoformat(record["prediction_instant"]).astimezone(zone),
            datetime.fromisoformat(available).astimezone(zone) if available is not None else None,
            numeric(record["tp"]), numeric(record["buy_in"]), numeric(record["internal_tp"]), numeric(record["consensus_tp"]),
            record["consensus_source"], record["analyst_count"], numeric(record["consensus_weight_percent"]), numeric(record["price"]),
            record["currency"], json.loads(json.dumps(record["decomposition"])), record["row_sha256"])


def test_the_postgresql_row_reader_rebuilds_the_canonical_shape_and_the_stored_hash_round_trips() -> None:
    # F393-6 a (rev 5): the PG reader lacked `schema` and the top-level bands, so the stored hash never re-verified
    database = _database()
    odd = 0.1 + 0.2  # 0.30000000000000004: 17 significant digits — a float8 → NUMERIC cast would keep 15 and change it
    record = official.prediction_from_row({**_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0), "consensus_weight_percent": odd,
                                           "consensus_as_of": "2026-09-01", "calibration_factor": odd},
                                          market="B3", scope="universe", cycle_id="cycle-pg", source_version="7",
                                          prediction_instant=datetime(2026, 9, 4, 23, 30, 15, 123456, tzinfo=timezone.utc))
    assert record is not None and record["consensus_weight_percent"] == odd
    for zone in (ZoneInfo("UTC"), ZoneInfo("America/Sao_Paulo"), ZoneInfo("Asia/Tokyo")):  # whatever the session time zone
        rebuilt = database._prediction_record(_pg_row(record, zone))
        assert rebuilt == record  # the exact canonical shape: keys, types (float/int/str/None), nesting
        assert rebuilt["schema"] == official.PREDICTION_SCHEMA and rebuilt["bear_tp"] == 32.0 and rebuilt["bull_tp"] == 48.0
        core = {key: value for key, value in rebuilt.items() if key not in ("id", "row_sha256")}
        assert official.canonical_sha256(core) == record["row_sha256"]
    # the writer binds NUMERIC as the shortest round-trip decimal; a float8 cast (15 digits) would break the hash
    assert float(Database._numeric_param(odd)) == odd and Database._numeric_param(None) is None  # type: ignore[arg-type]
    assert float(Decimal(f"{odd:.15g}")) != odd
    # a JSONB delivered as text (no jsonb loader) is parsed, never hashed as a string
    as_text = list(_pg_row(record, ZoneInfo("UTC")))
    as_text[19] = json.dumps(record["decomposition"])
    assert database._prediction_record(tuple(as_text)) == record
    # the memory double serves the same shape the PG reader rebuilds
    database.insert_valuation_predictions([record])
    assert database.valuation_prediction_record("cycle-pg", "PETR4") == record


def test_the_consensus_of_a_record_carries_its_own_identity_with_explicit_nulls() -> None:
    # F393-6 b (rev 5): published_at, horizon, currency and a hash of its own — nulls explicit, never dropped
    keys = {"tp", "source", "analyst_count", "as_of", "published_at", "horizon", "currency", "gap_percent", "payload_sha256"}
    with_date = official.consensus_block({**_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0), "consensus_as_of": "2026-09-01",
                                          "consensus_origin_source": "brapi", "consensus_gap_percent": 2.5}, market="B3")
    assert set(with_date) == keys and with_date["published_at"] == "2026-09-01" and with_date["as_of"] == "2026-09-01"
    assert with_date["horizon"] == "12m" and with_date["currency"] == "BRL" and with_date["source"] == "brapi" and with_date["analyst_count"] == 12
    assert with_date["payload_sha256"] == official.canonical_sha256({key: value for key, value in with_date.items() if key != "payload_sha256"})
    explicit = official.consensus_block({**_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0), "consensus_published_at": "2026-09-02T12:00:00+00:00",
                                         "consensus_as_of": "2026-09-01", "consensus_horizon": "18m", "consensus_currency": "EUR"}, market="NASDAQ")
    assert explicit["published_at"] == "2026-09-02T12:00:00+00:00" and explicit["as_of"] == "2026-09-01" and explicit["horizon"] == "18m" and explicit["currency"] == "EUR"
    without = official.consensus_block({"symbol": "KO", "our_tp": 70.0, "buy_in": 60.0, "price": 65.0}, market="NYSE")
    assert set(without) == keys and {key: without[key] for key in keys - {"payload_sha256"}} == {key: None for key in keys - {"payload_sha256"}}
    assert with_date["payload_sha256"] != without["payload_sha256"] != explicit["payload_sha256"]
    database = _database()
    _three_markets(database)
    record = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert record is not None and set(record["decomposition"]["consensus"]) == keys and record["decomposition"]["consensus"]["published_at"] is None
    assert record["decomposition"]["consensus"]["currency"] == "USD" and record["decomposition"]["consensus"]["horizon"] == "12m"


def test_an_unavailable_calendar_is_an_unavailability_never_a_civil_date(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # F393-6 c (rev 5): a calendar failure used to fall back to the civil date and mint a Sunday session
    database = _database()
    cycles = _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    sunday = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)

    def broken(market: str) -> Any:
        raise RuntimeError("calendar down")

    with pytest.MonkeyPatch.context() as outage:
        outage.setattr(official, "_calendar", broken)
        caplog.set_level(logging.WARNING, logger="app.valuation_official")
        with pytest.raises(official.CalendarUnavailable):
            official.session_date_of("NASDAQ", sunday)  # not "2026-09-06"
        assert official.prediction_from_row(_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0), market="NASDAQ", scope="universe",
                                            cycle_id="c", source_version="7", prediction_instant=sunday) is None  # not recordable
        outage_cycle = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], later(1))
        assert database.valuation_predictions_for_cycle(outage_cycle) == {}  # nothing recorded under a guessed session
        assert official.current_generation(database) == base  # nothing selected either
        validation = official.selectable_cycles(database)["NYSE"]
        assert validation["calendar_unavailable"] is True and validation["valid"] is False and validation["session_date"] is None
        with pytest.raises(ValueError, match="not complete/valid/recorded"):  # the explicit path cannot select blind either
            official.select_generation(database, cycles=cycles, now=later(2), activated_by="mesa", reason="blind")
        health = official.selection_health(database, now=later(2))
        assert health["calendar_unavailable"] == ["B3", "NASDAQ", "NYSE"] and health["status"] == "stale" and health["markets"]["NYSE"]["sessions_behind"] is None
        assert any("calendar unavailable" in message for message in caplog.messages)
    # the calendar is back: the cycle published during the outage is recorded and selected by the bootstrap, with its real session
    recovered = official.bootstrap_official_selection(database)
    assert recovered["recorded"] == {"B3": 0, "NASDAQ": 0, "NYSE": 1} and recovered["generation"]["cycles"]["NYSE"] == outage_cycle
    assert database.valuation_predictions_for_cycle(outage_cycle)["KO"]["session_date"] == official.session_date_of("NYSE", later(1))


def test_the_studies_official_arm_includes_the_targeted_admissions_of_the_generation() -> None:
    # F393-7 (rev 5): official_prediction_snapshot omitted the targeted cycles of its own generation
    database = _database()
    _three_markets(database)
    base = official.current_generation(database)
    wege = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                           {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(1))
    admitted = official.current_generation(database)
    assert base is not None and admitted is not None and admitted["targeted"] == {"WEGE3": wege}
    snapshot = official.official_prediction_snapshot(database, "B3")
    assert snapshot is not None
    results = snapshot["outputs"]["results"]
    assert set(results) == {"PETR4", "VALE3", "WEGE3"} and snapshot["outputs"]["targeted_cycles"] == {"WEGE3": wege}
    assert results["WEGE3"]["tp"] == 50.0 and results["WEGE3"]["scope"] == "targeted" and results["WEGE3"]["cycle_id"] == wege
    assert results["PETR4"]["scope"] == "universe" and results["PETR4"]["cycle_id"] == admitted["cycles"]["B3"]
    assert official.official_prediction_snapshot(database, "NASDAQ")["outputs"]["targeted_cycles"] == {}  # type: ignore[index]  # B3 admissions never leak to US
    # a collision (an explicit selection naming a targeted cycle for a symbol the universe serves): the universe record wins
    petr = database.save_analysis_snapshot("security_valuation", "PETR4", "mv-1", {"methodology_version": 7},
                                           {"row": _row("PETR4", tp=90.0, buy_in=70.0, price=80.0, internal_tp=88.0)}, later(2))
    explicit = official.select_generation(database, cycles=admitted["cycles"], targeted={"WEGE3": wege, "PETR4": petr}, now=later(3), activated_by="mesa", reason="collision")
    collided = official.official_prediction_snapshot(database, "B3", generation=explicit)
    assert collided is not None and collided["outputs"]["results"]["PETR4"]["tp"] == 40.0 and collided["outputs"]["results"]["PETR4"]["scope"] == "universe"
    assert collided["outputs"]["targeted_cycles"] == {"WEGE3": wege} and official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0  # type: ignore[index]
    # a past generation still answers with ITS admissions, never the current ones (replay)
    replay = official.official_prediction_snapshot(database, "B3", generation=base)
    assert replay is not None and replay["outputs"]["targeted_cycles"] == {} and set(replay["outputs"]["results"]) == {"PETR4", "VALE3"}


def _interleave(database: Database, monkeypatch: pytest.MonkeyPatch, *, on_call: int | tuple[int, ...], action: Callable[[], None]) -> dict[str, int]:
    """Run ``action`` (another writer) right before the ``on_call``-th read(s) of the current generation return —
    i.e. between a writer's read and its chained INSERT. Nested reads made by ``action`` itself count too. Returns the
    live call counter."""
    original = database.latest_valuation_official_selection
    calls = {"n": 0}
    hooks = (on_call,) if isinstance(on_call, int) else on_call

    def interleaved() -> dict[str, Any] | None:
        calls["n"] += 1
        if calls["n"] in hooks:
            action()
        return original()

    monkeypatch.setattr(database, "latest_valuation_official_selection", interleaved)
    return calls


def test_a_writer_that_prepared_on_a_stale_generation_recomposes_instead_of_dropping_the_other_writers_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    # F393-9 (rev 5): A prepares on G0; B publishes G1 = {B}; A's write used to re-read G1 and chain G2 = {A} on it — B vanished.
    # Now A names G0 as the expected predecessor, is refused, re-reads G1 and recomposes: G2 carries B.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    new_nasdaq = {"id": "nasdaq-new", "analysis_type": "valuation_universe", "entity_key": "NASDAQ_UNIVERSE", "methodology_version_id": "mv-1",
                  "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], "universe_size": 2},
                  "published_at": later(1)}
    database._analysis_snapshots.append(new_nasdaq)  # A's cycle: recorded, not yet activated
    record = official.prediction_from_row(new_nasdaq["outputs"]["rows"][0], market="NASDAQ", scope="universe", cycle_id="nasdaq-new", source_version="7", prediction_instant=later(1))
    assert record is not None and database.insert_valuation_predictions([record]) == 1
    wege = {"id": None}

    def b_publishes() -> None:  # B: a targeted admission chained on G0
        wege["id"] = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                                     {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(2))

    _interleave(database, monkeypatch, on_call=2, action=b_publishes)  # call 1: A reads G0; call 2: inside A's write — B lands first
    g2 = official.activate_generation_if_changed(database)
    assert g2 is not None and wege["id"]
    g1 = database.valuation_official_selection(str(g2["previous_generation_id"]))
    assert g1 is not None and g1["previous_generation_id"] == g0["generation_id"] and g1["targeted"] == {"WEGE3": wege["id"]}  # B's generation
    assert g2["cycles"] == {**cycles, "NASDAQ": "nasdaq-new"} and g2["targeted"] == {"WEGE3": wege["id"]}  # A's decision, recomposed on G1
    assert official.current_generation(database) == g2
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0 and official.official_row(database, "US", "AAPL")["our_tp"] == 260.0  # type: ignore[index]
    assert [item["generation_id"] for item in database._valuation_official_selections] == [g0["generation_id"], g1["generation_id"], g2["generation_id"]]


def test_an_explicit_selection_fails_when_the_chain_moves_and_the_root_is_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    # F393-9 (rev 5), explicit path: the mesa's order was taken on G0; if G1 lands before the write, the order fails and G1 stays
    database = _database()
    _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None

    def b_publishes() -> None:
        database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                        {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(1))

    _interleave(database, monkeypatch, on_call=2, action=b_publishes)
    with pytest.raises(ValueError, match="selection conflict.*not the expected predecessor"):
        official.select_generation(database, cycles=g0["cycles"], now=later(2), activated_by="mesa", reason="rollback drill")
    current = official.current_generation(database)
    assert current is not None and current["previous_generation_id"] == g0["generation_id"] and current["targeted"]  # B's G1 is the head
    # the root is unique: a second bootstrap (previous_generation_id NULL) is refused, in the double as in the partial index
    from app.database import SelectionConflict
    fresh = _database()
    root = {**g0, "generation_id": "root-a", "previous_generation_id": None}
    fresh.insert_valuation_official_selection(root)
    with pytest.raises(SelectionConflict, match="root generation already exists"):
        fresh.insert_valuation_official_selection({**root, "generation_id": "root-b", "activated_at": later(1).isoformat()})
    assert [item["generation_id"] for item in fresh._valuation_official_selections] == ["root-a"]
    # the bootstrap path names `None` as its expected predecessor: a root that appeared meanwhile is a conflict, not a second root
    assert official._new_generation(fresh, expected_previous=None, cycles=g0["cycles"], targeted={}, source=official.SOURCE_OFFICIAL, source_version="7",
                                    session_dates=g0["session_dates"], now=later(2), activated_by="t", receipt={}) is None
    with pytest.raises(ValueError, match="selection conflict"):
        official._new_generation(fresh, expected_previous=None, cycles=g0["cycles"], targeted={}, source=official.SOURCE_OFFICIAL, source_version="7",
                                 session_dates=g0["session_dates"], now=later(2), activated_by="t", receipt={}, strict=True)


def test_the_loser_of_a_chain_conflict_recomposes_on_the_wall_clock_and_nothing_is_dropped(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # F393-9 / X1 (rev 5): on the REAL wall-clock path (save_analysis_snapshot → record_snapshot, no explicit `now`) the loser's
    # retry reused its old clock, which was earlier than the winner's activation: the D3 guard refused the recomposition and
    # the loser's decision vanished silently (the screeners kept serving the previous night). A recomposition is a NEW
    # activation, ordered by when it actually happened: the retry renews the clock.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    wege = {"id": None}

    def b_publishes() -> None:  # B: a targeted admission, wall clock, lands inside A's write
        wege["id"] = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                                     {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(2))

    _interleave(database, monkeypatch, on_call=2, action=b_publishes)  # call 1: A reads G0; call 2: inside A's write — B lands first
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(1))  # A: wall clock
    head = official.current_generation(database)
    assert head is not None and wege["id"]
    assert head["cycles"] == {**cycles, "NASDAQ": nasdaq_new} and head["targeted"] == {"WEGE3": wege["id"]}  # BOTH: A's cycle and B's admission
    g1 = database.valuation_official_selection(str(head["previous_generation_id"]))
    assert g1 is not None and g1["targeted"] == {"WEGE3": wege["id"]} and g1["cycles"] == cycles and g1["previous_generation_id"] == g0["generation_id"]
    assert official._utc(head["activated_at"]) > official._utc(g1["activated_at"])  # the recomposition is ordered after the generation it chains on
    assert not any("is not after the current generation" in message for message in caplog.messages)  # its own clock was after the head: nothing advanced (Z1)
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 260.0 and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]
    assert [item["generation_id"] for item in database._valuation_official_selections] == [g0["generation_id"], g1["generation_id"], head["generation_id"]]


def test_an_explicit_selection_normalizes_targeted_symbols_before_validating_and_writing() -> None:
    # X2 (rev 5): a rollback naming the admission as "wege3 " passed validation (case-insensitive) but was written as-is,
    # and official_row (which looks up the CLEAN symbol) never served it
    database = _database()
    _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    wege = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                           {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(1))
    rolled = official.select_generation(database, cycles=base["cycles"], targeted={" wege3 ": wege}, now=later(2), activated_by="mesa", reason="lowercase key")
    assert rolled["targeted"] == {"WEGE3": wege} and official.current_generation(database) == rolled
    served = official.official_row(database, "B3", "wege3.sa")
    assert served is not None and served["our_tp"] == 50.0 and served["official_scope"] == "targeted" and served["generation_id"] == rolled["generation_id"]
    assert official.official_prediction_snapshot(database, "B3")["outputs"]["targeted_cycles"] == {"WEGE3": wege}  # type: ignore[index]
    with pytest.raises(ValueError, match="not a targeted cycle of PETR4"):  # the normalized symbol is what the cycle is checked against
        official.select_generation(database, cycles=base["cycles"], targeted={"petr4": wege}, now=later(3), activated_by="mesa", reason="wrong symbol")
    with pytest.raises(ValueError, match="collide after normalization"):
        official.select_generation(database, cycles=base["cycles"], targeted={"wege3": wege, "WEGE3": "other-cycle"}, now=later(3), activated_by="mesa", reason="ambiguous")
    assert official._normalized_targeted({"wege3": wege, " WEGE3": wege}) == {"WEGE3": wege}  # the same order twice is not a collision
    # the automatic admission and _new_generation normalize too
    generation = official._new_generation(database, expected_previous=rolled["generation_id"], cycles=base["cycles"], targeted={"vale3 ": "cycle-v"},
                                          source=official.SOURCE_OFFICIAL, source_version="7", session_dates=base["session_dates"], now=later(4),
                                          activated_by="t", receipt={})
    assert generation is not None and generation["targeted"] == {"VALE3": "cycle-v"}


def test_the_consensus_block_keeps_instants_in_iso_form_and_treats_empty_strings_as_absent() -> None:
    # X3 (rev 5): a datetime/date the producer hands over was stringified with a space; '' became a "published" instant
    row = _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)
    stamped = datetime(2026, 9, 1, 13, 30, 15, tzinfo=timezone.utc)
    block = official.consensus_block({**row, "consensus_as_of": stamped, "consensus_published_at": date(2026, 9, 2)}, market="B3")
    assert block["as_of"] == "2026-09-01T13:30:15+00:00" and block["published_at"] == "2026-09-02"
    assert " " not in block["as_of"] and " " not in block["published_at"]
    naive = official.consensus_block({**row, "consensus_as_of": datetime(2026, 9, 1, 13, 30)}, market="B3")
    assert naive["as_of"] == "2026-09-01T13:30:00" and naive["published_at"] == "2026-09-01T13:30:00"
    empty = official.consensus_block({**row, "consensus_as_of": "", "consensus_published_at": "", "consensus_horizon": "", "consensus_currency": " ",
                                      "consensus_origin_source": ""}, market="NASDAQ")
    assert empty["as_of"] is None and empty["published_at"] is None and empty["source"] is None
    assert empty["horizon"] == "12m" and empty["currency"] == "USD"  # the defaults apply to an empty producer value as to a missing one
    fallback = official.consensus_block({**row, "consensus_as_of": " 2026-09-03 ", "consensus_published_at": ""}, market="B3")
    assert fallback["as_of"] == "2026-09-03" and fallback["published_at"] == "2026-09-03"  # '' never wins over the as_of fallback
    assert official.consensus_block({**row, "consensus_as_of": None}, market="B3")["as_of"] is None
    # the record carries the same forms (and its provenance as_of too), so the stored JSON equals what was hashed
    record = official.prediction_from_row({**row, "consensus_as_of": stamped, "consensus_origin_source": "", "as_of": date(2026, 9, 4)},
                                          market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=stamped)
    assert record is not None and record["decomposition"]["consensus"]["as_of"] == "2026-09-01T13:30:15+00:00" and record["consensus_source"] is None
    assert record["decomposition"]["provenance"]["as_of"] == "2026-09-04"
    round_trip = json.loads(json.dumps(record))
    assert official.canonical_sha256({k: v for k, v in round_trip.items() if k not in ("id", "row_sha256")}) == record["row_sha256"]


def test_a_universe_cycle_published_during_a_calendar_outage_is_recovered_by_the_next_activation_pass(caplog: pytest.LogCaptureFixture) -> None:
    # X4 (rev 5): after the calendar came back, the outage cycle (no records) was recovered only by an explicit bootstrap; the
    # nightly path left the market on the stale generation. Now the activation pass records an unrecorded latest cycle before
    # validating it — records before selection — and selects it with its real session. A targeted valuation published
    # during the outage is NOT recovered: it has no record, its symbol is not admitted, and it must be re-run (documented).
    database = _database()
    cycles = _three_markets(database)
    base = official.current_generation(database)
    assert base is not None
    published_at = later(1)

    def broken(market: str) -> Any:
        raise RuntimeError("calendar down")

    with pytest.MonkeyPatch.context() as outage:
        outage.setattr(official, "_calendar", broken)
        outage_cycle = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], published_at)
        outage_targeted = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                                          {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, published_at)
        assert database.valuation_predictions_for_cycle(outage_cycle) == {} and database.valuation_predictions_for_cycle(outage_targeted) == {}
        assert official.current_generation(database) == base
    # the calendar answers again; the next producer cycle of ANOTHER market runs the ordinary activation pass (wall clock)
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(2))
    recovered = official.current_generation(database)
    assert recovered is not None and recovered["cycles"] == {**cycles, "NASDAQ": nasdaq_new, "NYSE": outage_cycle}
    assert recovered["receipt"]["changed_markets"] == ["NASDAQ", "NYSE"] and recovered["receipt"]["carried_markets"] == []
    assert recovered["session_dates"]["NYSE"] == official.session_date_of("NYSE", published_at)
    record = database.valuation_predictions_for_cycle(outage_cycle)["KO"]
    assert record["session_date"] == official.session_date_of("NYSE", published_at) and record["prediction_instant"] == published_at.isoformat()
    assert official.official_row(database, "NYSE", "KO")["our_tp"] == 75.0 and official.official_row(database, "NYSE", "KO")["official_row_sha256"] == record["row_sha256"]  # type: ignore[index]
    assert any("recorded at selection time" in message for message in caplog.messages)
    assert official.selectable_cycles(database)["NYSE"]["valid"] is True and official.selection_health(database, now=later(3))["calendar_unavailable"] == []
    # the targeted cycle of the outage stays unrecorded and unadmitted; re-running it (a new cycle) admits it
    assert database.valuation_predictions_for_cycle(outage_targeted) == {} and recovered["targeted"] == {} and official.official_row(database, "B3", "WEGE3") is None
    rerun = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                            {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, later(3))
    assert official.current_generation(database)["targeted"] == {"WEGE3": rerun} and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]


# ----------------------------------------------------------------------------------------------------- rev 5 residuals (Y1–Y4)


def _targeted(symbol: str, tp: float = 50.0) -> dict:
    return _row(symbol, tp=tp, buy_in=tp * 0.84, price=tp * 0.9, internal_tp=tp * 0.98)


def test_the_activation_clock_is_read_at_the_insert_never_before_the_records_and_never_clamped_to_the_head(monkeypatch: pytest.MonkeyPatch,
                                                                                                             caplog: pytest.LogCaptureFixture) -> None:
    # Y1: record_snapshot took its clock BEFORE writing the records and the activation reused it; when another generation
    # was activated meanwhile, the clock was clamped to that head's instant — a generation activated LATER was dated at the
    # head's instant (backdated, same host), and generation_at(decision_at) handed a decision taken on the head a generation
    # that was not in force at the decision. The clock is now read immediately before each INSERT, never clamped.
    # Z1 (b), the round-3 scenario: A publishes NASDAQ, B admits WEGE3 (G1) during A's write, a consumer decides reading G1 →
    # generation_at(decision_at) == G1 and A's head is dated after G1 — by its own clock, nothing advanced (see Z1 (a) below).
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    original = database.insert_valuation_predictions
    seen: dict[str, Any] = {"g1": None, "decision_at": None}

    def while_a_writes_records(records: list[dict[str, Any]]) -> int:
        written = original(records)
        if seen["g1"] is None and records and records[0]["market"] == "NASDAQ":  # A's records are written; before A activates:
            time.sleep(0.001)
            database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7}, {"row": _targeted("WEGE3")}, later(2))  # B admits: G1
            seen["g1"] = official.current_generation(database)
            time.sleep(0.001)
            seen["decision_at"] = datetime.now(timezone.utc)  # a consumer decides, reading G1
            assert official.generation_at(database, seen["decision_at"]) == seen["g1"]
            time.sleep(0.001)
        return written

    monkeypatch.setattr(database, "insert_valuation_predictions", while_a_writes_records)
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(1))  # A: the real path
    head = official.current_generation(database)
    g1, decision_at = seen["g1"], seen["decision_at"]
    assert head is not None and g1 is not None and decision_at is not None and g1["previous_generation_id"] == g0["generation_id"]
    assert head["previous_generation_id"] == g1["generation_id"] and head["cycles"] == {**cycles, "NASDAQ": nasdaq_new} and head["targeted"] == g1["targeted"]
    assert official._utc(g1["activated_at"]) < decision_at < official._utc(head["activated_at"])  # dated at its own INSERT: after the decision
    assert official._utc(head["activated_at"]) > official._utc(g1["activated_at"])  # Z1 (b): A's head is dated after the generation it chains on
    assert official.generation_at(database, decision_at) == g1  # the decision replays the generation it read, never the later head
    assert official.generation_at(database, official._utc(head["activated_at"])) == head
    assert not any("is not after the current generation" in message for message in caplog.messages)  # A's own clock was after G1: nothing advanced
    assert [item["generation_id"] for item in database._valuation_official_selections] == [g0["generation_id"], g1["generation_id"], head["generation_id"]]


def _third_writer_setup(database: Database) -> tuple[dict[str, str], dict[str, Any]]:
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    new_nasdaq = {"id": "nasdaq-new", "analysis_type": "valuation_universe", "entity_key": "NASDAQ_UNIVERSE", "methodology_version_id": "mv-1",
                  "inputs": {"methodology_version": 7}, "outputs": {"rows": [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], "universe_size": 2},
                  "published_at": later(1)}
    database._analysis_snapshots.append(new_nasdaq)  # A's cycle: recorded, not yet activated
    record = official.prediction_from_row(new_nasdaq["outputs"]["rows"][0], market="NASDAQ", scope="universe", cycle_id="nasdaq-new", source_version="7", prediction_instant=later(1))
    assert record is not None and database.insert_valuation_predictions([record]) == 1
    return cycles, g0


def test_a_writer_recomposes_while_the_head_keeps_moving_and_a_third_writer_does_not_drop_its_decision(monkeypatch: pytest.MonkeyPatch,
                                                                                                        caplog: pytest.LogCaptureFixture) -> None:
    # Y2: ONE recomposition was not enough when a third writer moved the head again inside the retry — the loser's decision
    # was dropped. The loser now retries while the head moves (up to RECOMPOSITION_ATTEMPTS), each attempt on its own clock.
    database = _database()
    cycles, _g0 = _third_writer_setup(database)
    symbols = iter(["WEGE3", "ITUB4"])
    admitted: list[tuple[str, str]] = []

    def another_writer() -> None:  # a different targeted admission lands inside each of A's writes
        symbol = next(symbols)
        admitted.append((symbol, database.save_analysis_snapshot("security_valuation", symbol, "mv-1", {"methodology_version": 7}, {"row": _targeted(symbol)}, later(2))))

    # A reads the head twice per attempt (the pass, then the chained write); a writer landing inside the write reads it twice more
    _interleave(database, monkeypatch, on_call=(2, 6), action=another_writer)  # B inside attempt 1, C inside attempt 2
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    head = official.activate_generation_if_changed(database)
    assert head is not None and head["cycles"] == {**cycles, "NASDAQ": "nasdaq-new"} and head["receipt"]["attempt"] == 3
    assert len(admitted) == 2 and head["targeted"] == dict(admitted)  # both other writers carried, A's decision landed
    chain = database._valuation_official_selections
    assert len(chain) == 4 and chain[-1]["generation_id"] == head["generation_id"] and chain[-2]["targeted"] == dict(admitted)
    assert all(official._utc(chain[i]["activated_at"]) < official._utc(chain[i + 1]["activated_at"]) for i in range(len(chain) - 1))  # each attempt: its own clock
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 260.0 and official.official_row(database, "B3", "ITUB4")["our_tp"] == 50.0  # type: ignore[index]
    assert not any("recomposition attempts" in message for message in caplog.messages)


def test_a_writer_gives_up_with_a_warning_when_the_head_moves_past_the_limit_and_the_next_pass_lands_it(monkeypatch: pytest.MonkeyPatch,
                                                                                                          caplog: pytest.LogCaptureFixture) -> None:
    # Y2, the limit: the head moves inside EVERY attempt → nothing activated by this pass, a WARNING says so, nothing is
    # dropped either — the next pass (the next cycle of any market, or the bootstrap) composes the decision again and lands it
    database = _database()
    cycles, _g0 = _third_writer_setup(database)
    symbols = iter(["WEGE3", "ITUB4", "BBDC4", "ABEV3", "RENT3"])
    admitted: list[tuple[str, str]] = []

    def another_writer() -> None:
        symbol = next(symbols)
        admitted.append((symbol, database.save_analysis_snapshot("security_valuation", symbol, "mv-1", {"methodology_version": 7}, {"row": _targeted(symbol)}, later(2))))

    calls = _interleave(database, monkeypatch, on_call=tuple(4 * k + 2 for k in range(official.RECOMPOSITION_ATTEMPTS)), action=another_writer)
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    assert official.activate_generation_if_changed(database) is None
    assert len(admitted) == official.RECOMPOSITION_ATTEMPTS == 5 and calls["n"] == 4 * official.RECOMPOSITION_ATTEMPTS
    assert any(f"every one of {official.RECOMPOSITION_ATTEMPTS} recomposition attempts" in message for message in caplog.messages)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == dict(admitted) and head["cycles"] == cycles  # the five writers stand; A's cycle is not in force yet
    landed = official.activate_generation_if_changed(database)  # the next pass, with a quiet head
    assert landed is not None and landed["cycles"] == {**cycles, "NASDAQ": "nasdaq-new"} and landed["targeted"] == dict(admitted) and landed["receipt"]["attempt"] == 1
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 260.0  # type: ignore[index]


def test_a_registered_targeted_cycle_that_was_not_admitted_is_admitted_by_the_next_activation_pass(caplog: pytest.LogCaptureFixture) -> None:
    # Y3: a targeted cycle recorded but not admitted (its admission lost every recomposition; a calendar outage at validation)
    # stayed unadmitted for the day. The activation pass now admits, per symbol, the most recent REGISTERED targeted cycle
    # newer than the one the generation holds — unless the universe cycle serves the symbol (A1) or the cycle fails the validator
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    from app.database import SelectionConflict

    def another_host_wins(generation: dict[str, Any]) -> None:  # every INSERT of this process loses the chain
        raise SelectionConflict(f"generation {generation['previous_generation_id']} already has a successor")

    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    with pytest.MonkeyPatch.context() as race:
        race.setattr(database, "insert_valuation_official_selection", another_host_wins)
        wege = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7}, {"row": _targeted("WEGE3")}, later(1))
    assert "WEGE3" in database.valuation_predictions_for_cycle(wege)  # registered...
    assert official.current_generation(database) == g0 and official.official_row(database, "B3", "WEGE3") is None  # ...not admitted
    assert any("recomposition attempts" in message and "WEGE3" in message for message in caplog.messages)
    petr = database.save_analysis_snapshot("security_valuation", "PETR4", "mv-1", {"methodology_version": 7}, {"row": _targeted("PETR4", 90.0)}, later(1))  # the universe serves it (A1)
    bad = database.save_analysis_snapshot("security_valuation", "ITUB4", "mv-1", {"methodology_version": 7},
                                          {"row": {**_targeted("ITUB4"), "price": 0, "internal_tp": None}}, later(1))  # registered (TP, buy-in), invalid (price)
    assert "PETR4" in database.valuation_predictions_for_cycle(petr) and "ITUB4" in database.valuation_predictions_for_cycle(bad)
    assert official.current_generation(database) == g0
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(2))  # the next pass
    recovered = official.current_generation(database)
    assert recovered is not None and recovered["cycles"] == {**cycles, "NASDAQ": nasdaq_new} and recovered["targeted"] == {"WEGE3": wege}
    assert recovered["receipt"]["targeted_recovered"] == {"WEGE3": wege} and recovered["receipt"]["changed_markets"] == ["NASDAQ"]
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0 and official.official_row(database, "B3", "WEGE3")["official_cycle_id"] == wege  # type: ignore[index]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0 and official.official_row(database, "B3", "ITUB4") is None  # type: ignore[index]
    # a recovery alone is a change: with the same cycles, a newer registered-not-admitted cycle activates a generation by itself
    with pytest.MonkeyPatch.context() as race:
        race.setattr(database, "insert_valuation_official_selection", another_host_wins)
        wege2 = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7}, {"row": _targeted("WEGE3", 90.0)}, later(3))
    assert official.current_generation(database) == recovered
    passed = official.activate_generation_if_changed(database)  # any pass, no new universe cycle
    assert passed is not None and passed["cycles"] == recovered["cycles"] and passed["targeted"] == {"WEGE3": wege2} and passed["previous_generation_id"] == recovered["generation_id"]
    assert passed["receipt"]["targeted_recovered"] == {"WEGE3": wege2} and passed["receipt"]["changed_markets"] == []
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 90.0  # type: ignore[index]
    assert official.activate_generation_if_changed(database) is None  # the generation holds the newest registered cycle: nothing to do
    latest = database.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL)
    assert {symbol: record["cycle_id"] for symbol, record in latest.items()} == {"WEGE3": wege2, "PETR4": petr, "ITUB4": bad}
    latest["WEGE3"]["tp"] = 1.0
    assert database.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL)["WEGE3"]["tp"] == 90.0  # copies


def test_targeted_keys_that_collide_after_normalization_never_stop_the_automatic_path(caplog: pytest.LogCaptureFixture) -> None:
    # Y4: a head carrying {'wege3': c1, 'WEGE3': 'other'} (a map this writer did not write) made _normalized_targeted raise
    # inside the nightly path. The automatic admission now carries the first occurrence (WARNING) and wins its own key, the
    # carry-over keeps the first occurrence, and the ambiguity is a ValueError only for an explicit order.
    database = _database()
    cycles = _three_markets(database)
    c1 = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7}, {"row": _targeted("WEGE3")}, later(1))
    g1 = official.current_generation(database)
    assert g1 is not None and g1["targeted"] == {"WEGE3": c1}
    database.insert_valuation_official_selection({**g1, "generation_id": "corrupt-head", "previous_generation_id": g1["generation_id"],
                                                  "targeted": {"wege3": c1, "WEGE3": "other"}, "activated_at": datetime.now(timezone.utc).isoformat()})
    assert official.current_generation(database)["generation_id"] == "corrupt-head"  # type: ignore[index]
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    c2 = database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7}, {"row": _targeted("WEGE3", 90.0)}, later(2))
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["previous_generation_id"] == "corrupt-head" and admitted["targeted"] == {"WEGE3": c2}  # the admission wins its own key
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 90.0  # type: ignore[index]
    assert any("collide after normalization" in message and "first occurrence" in message for message in caplog.messages)
    caplog.clear()
    database.insert_valuation_official_selection({**admitted, "generation_id": "corrupt-head-2", "previous_generation_id": admitted["generation_id"],
                                                  "targeted": {"wege3": c2, "WEGE3": "other"}, "activated_at": datetime.now(timezone.utc).isoformat()})
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(3))  # carry-over
    carried = official.current_generation(database)
    assert carried is not None and carried["previous_generation_id"] == "corrupt-head-2" and carried["cycles"] == {**cycles, "NASDAQ": nasdaq_new}
    assert carried["targeted"] == {"WEGE3": c2} and carried["receipt"]["targeted_recovered"] == {}  # the first occurrence, nothing newer registered
    assert any("collide after normalization" in message and "first occurrence" in message for message in caplog.messages)
    assert official._normalized_targeted({"wege3": c1, "WEGE3": "other"}, strict=False) == {"WEGE3": c1}
    with pytest.raises(ValueError, match="collide after normalization"):  # the explicit order is the only place the ambiguity is an error
        official.select_generation(database, cycles=carried["cycles"], targeted={"wege3": c2, "WEGE3": "other"}, now=later(4), activated_by="mesa", reason="ambiguous")
    assert official.current_generation(database) == carried


# ----------------------------------------------------------------------------------------------------- rev 5 residuals (Z1–Z5)


def _wall() -> datetime:
    """The wall clock, as the automatic path reads it — after a short sleep, so that consecutive instants differ."""
    time.sleep(0.001)
    return datetime.now(timezone.utc)


def _targeted_cycle(database: Database, symbol: str, at: datetime, tp: float = 50.0, **row: object) -> str:
    return database.save_analysis_snapshot("security_valuation", symbol, "mv-1", {"methodology_version": 7}, {"row": {**_targeted(symbol, tp), **row}}, at)


def test_a_generation_is_never_dated_before_the_head_it_chains_on(caplog: pytest.LogCaptureFixture) -> None:
    # Z1 (a): with the clamp gone, a host whose wall clock runs BEHIND the host that wrote the head dated its generation behind
    # the head; readers take the head by max(activated_at) (memory and SQL alike), so it never became the head, every later
    # writer chained on the stale head, conflicted x5 and gave up — the chain was locked (bootstrap and select_generation too).
    # The non-strict path now ADVANCES the instant to the head's + 1 µs (WARNING); it only advances, never recedes. The
    # explicit path keeps refusing a clock behind the head (D3).
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    ahead = datetime.now(timezone.utc) + timedelta(seconds=2)  # host B, 2 s ahead of this host, just admitted a targeted cycle
    database.insert_valuation_official_selection({**g0, "generation_id": "host-b-ahead", "previous_generation_id": g0["generation_id"],
                                                  "targeted": {"WEGE3": "wege-cycle"}, "activated_at": ahead.isoformat()})
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], later(1))  # this host, behind
    head = official.current_generation(database)
    assert head is not None and head["previous_generation_id"] == "host-b-ahead" and head["cycles"] == {**cycles, "NASDAQ": nasdaq_new}
    assert official._utc(head["activated_at"]) == ahead + timedelta(microseconds=1)  # advanced by the least amount — never behind the head
    assert head["targeted"] == {"WEGE3": "wege-cycle"} and head["receipt"]["attempt"] == 1
    advanced = [message for message in caplog.messages if "is not after the current generation" in message and "advanced to" in message]
    assert len(advanced) == 1 and (ahead + timedelta(microseconds=1)).isoformat() in advanced[0]
    # later writers succeed: an admission chains on the new head (advanced again — this host's clock is still behind)
    itub = _targeted_cycle(database, "ITUB4", later(2))
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["previous_generation_id"] == head["generation_id"] and admitted["receipt"]["attempt"] == 1
    assert admitted["targeted"] == {"ITUB4": itub, "WEGE3": "wege-cycle"}
    assert official._utc(admitted["activated_at"]) == official._utc(head["activated_at"]) + timedelta(microseconds=1)
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 260.0 and official.official_row(database, "B3", "ITUB4")["our_tp"] == 50.0  # type: ignore[index]
    assert official.bootstrap_official_selection(database)["generation"] == admitted  # a pass with nothing to change is not locked either
    assert official.generation_at(database, ahead)["generation_id"] == "host-b-ahead"  # type: ignore[index]
    assert official.generation_at(database, ahead + timedelta(microseconds=1)) == head and official.generation_at(database, ahead + timedelta(microseconds=2)) == admitted
    chain = database._valuation_official_selections
    assert [item["generation_id"] for item in chain] == [g0["generation_id"], "host-b-ahead", head["generation_id"], admitted["generation_id"]]
    assert all(official._utc(chain[i]["activated_at"]) < official._utc(chain[i + 1]["activated_at"]) for i in range(len(chain) - 1))  # chain order == clock order
    # the explicit path keeps refusing a clock behind the head (D3): the mesa re-reads; it is never advanced
    with pytest.raises(ValueError, match="earlier than the current generation"):
        official.select_generation(database, cycles=head["cycles"], now=datetime.now(timezone.utc), activated_by="mesa", reason="stale clock")
    rolled = official.select_generation(database, cycles=head["cycles"], now=ahead + timedelta(seconds=1), activated_by="mesa", reason="rollback drill")
    assert official.current_generation(database) == rolled
    # a tie with the head is advanced too (strictly after); a clock ahead of the head is written as read — it never recedes
    tied = official._new_generation(database, expected_previous=rolled["generation_id"], cycles=rolled["cycles"], targeted={}, source=official.SOURCE_OFFICIAL,
                                    source_version="7", session_dates=rolled["session_dates"], now=official._utc(rolled["activated_at"]), activated_by="t", receipt={})
    assert tied is not None and official._utc(tied["activated_at"]) == official._utc(rolled["activated_at"]) + timedelta(microseconds=1)
    kept = official._new_generation(database, expected_previous=tied["generation_id"], cycles=rolled["cycles"], targeted={}, source=official.SOURCE_OFFICIAL,
                                    source_version="7", session_dates=rolled["session_dates"], now=official._utc(tied["activated_at"]) + timedelta(minutes=5),
                                    activated_by="t", receipt={})
    assert kept is not None and official._utc(kept["activated_at"]) == official._utc(tied["activated_at"]) + timedelta(minutes=5)


def test_an_explicit_order_stands_over_the_targeted_cycles_registered_before_it(caplog: pytest.LogCaptureFixture) -> None:
    # Z2 (Y3 residual): the recovery re-admitted, on the next automatic pass or bootstrap, what a mesa order had purged
    # (select_generation(targeted={})) or rolled back (to an older cycle while a newer one was registered) — the comment "an
    # explicit selection of an older one stands" was false. The mesa's LAST explicit order is authoritative over every targeted
    # cycle PREDICTED at or before its instant (a re-run keeps the original instant, S1) — whether it is the head or automatic
    # generations have chained on it since; only cycles predicted AFTER the order are recovered.
    database = _database()
    cycles = _three_markets(database)
    c1 = _targeted_cycle(database, "WEGE3", _wall())
    c2 = _targeted_cycle(database, "WEGE3", _wall(), 90.0)
    assert official.current_generation(database)["targeted"] == {"WEGE3": c2}  # type: ignore[index]
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    # a purge stays purged: across an automatic pass, a bootstrap, an automatic generation chained on the order and passes after it
    purged = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="purge")
    assert official.activate_generation_if_changed(database) is None and official.current_generation(database) == purged
    assert official.bootstrap_official_selection(database)["generation"] == purged
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())
    auto = official.current_generation(database)
    assert auto is not None and auto["previous_generation_id"] == purged["generation_id"] and auto["cycles"] == {**cycles, "NASDAQ": nasdaq_new}
    assert auto["targeted"] == {} and auto["receipt"]["targeted_recovered"] == {} and auto["receipt"]["targeted_refused"] == {}
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == auto
    assert official.official_row(database, "B3", "WEGE3") is None
    # a rollback to c1 with c2 registered stays on c1
    rolled = official.select_generation(database, cycles=auto["cycles"], targeted={"WEGE3": c1}, now=_wall(), activated_by="mesa", reason="rollback to c1")
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == rolled
    nyse_new = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], _wall())
    after = official.current_generation(database)
    assert after is not None and after["cycles"]["NYSE"] == nyse_new and after["targeted"] == {"WEGE3": c1} and after["receipt"]["targeted_recovered"] == {}
    assert official.activate_generation_if_changed(database) is None
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0 and official.official_row(database, "B3", "WEGE3")["official_cycle_id"] == c1  # type: ignore[index]
    # a targeted cycle registered AFTER the order is recovered (its admission lost every recomposition), for a held symbol and a new one
    from app.database import SelectionConflict

    def another_host_wins(generation: dict[str, Any]) -> None:
        raise SelectionConflict(f"generation {generation['previous_generation_id']} already has a successor")

    with pytest.MonkeyPatch.context() as race:
        race.setattr(database, "insert_valuation_official_selection", another_host_wins)
        c3 = _targeted_cycle(database, "WEGE3", _wall(), 120.0)
        itub = _targeted_cycle(database, "ITUB4", _wall())
    assert official.current_generation(database) == after
    passed = official.activate_generation_if_changed(database)
    assert passed is not None and passed["targeted"] == {"ITUB4": itub, "WEGE3": c3} and passed["receipt"]["targeted_recovered"] == {"ITUB4": itub, "WEGE3": c3}
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 120.0 and official.official_row(database, "B3", "ITUB4")["our_tp"] == 50.0  # type: ignore[index]
    # the order is found through the storage API: the latest generation carrying the marker select_generation writes (the double as the SQL, W3)
    order = database.latest_explicit_valuation_official_selection()
    assert order is not None and order["generation_id"] == rolled["generation_id"] and order["receipt"]["explicit"] is True
    fresh = _database()
    _three_markets(fresh)
    assert fresh.latest_explicit_valuation_official_selection() is None
    assert not any("is not after the current generation" in message for message in caplog.messages)  # wall clocks throughout: nothing advanced


def test_a_refused_registered_targeted_cycle_is_a_warning_once_and_is_named_in_the_receipt(monkeypatch: pytest.MonkeyPatch,
                                                                                            caplog: pytest.LogCaptureFixture) -> None:
    # Z3: a registered-but-invalid targeted cycle was refused with a WARNING on EVERY activation pass. A refusal already known —
    # by this process, or by the head's receipt (targeted_refused, written by the passes and carried by the admissions) — is
    # INFO; the WARNING comes back only when the refused cycle id changes.
    monkeypatch.setattr(official, "_refusals_logged", {})
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    caplog.set_level(logging.INFO, logger="app.valuation_official")

    def refusals() -> list[int]:
        return [record.levelno for record in caplog.records if "refused" in record.getMessage() and "ITUB4" in record.getMessage()]

    bad = _targeted_cycle(database, "ITUB4", _wall(), price=0, internal_tp=None)  # registered (TP, buy-in), invalid (price, internal TP)
    assert "ITUB4" in database.valuation_predictions_for_cycle(bad) and refusals() == [logging.WARNING]  # the admission warns once
    caplog.clear()
    assert official.activate_generation_if_changed(database) is None and official.activate_generation_if_changed(database) is None
    assert official.bootstrap_official_selection(database)["generation"] == g0
    assert refusals() == [logging.INFO] * 3  # every later pass of this process: INFO
    caplog.clear()
    monkeypatch.setattr(official, "_refusals_logged", {})  # another process; the head's receipt does not name the refusal yet: one WARNING, then INFO
    assert official.activate_generation_if_changed(database) is None and official.activate_generation_if_changed(database) is None
    assert refusals() == [logging.WARNING, logging.INFO]
    caplog.clear()
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())  # a written generation
    written = official.current_generation(database)
    assert written is not None and written["cycles"]["NASDAQ"] == nasdaq_new and written["targeted"] == {}
    assert written["receipt"]["targeted_refused"] == {"ITUB4": bad} and written["receipt"]["targeted_recovered"] == {}
    monkeypatch.setattr(official, "_refusals_logged", {})  # another process again: the receipt names it → INFO only
    assert official.activate_generation_if_changed(database) is None and refusals() == [logging.INFO, logging.INFO]
    caplog.clear()
    wege = _targeted_cycle(database, "WEGE3", _wall())  # an admission carries the known refusals, so a later pass stays quiet
    admission = official.current_generation(database)
    assert admission is not None and admission["targeted"] == {"WEGE3": wege} and admission["receipt"]["targeted_refused"] == {"ITUB4": bad}
    monkeypatch.setattr(official, "_refusals_logged", {})
    assert official.activate_generation_if_changed(database) is None and refusals() == [logging.INFO]
    caplog.clear()
    bad2 = _targeted_cycle(database, "ITUB4", _wall(), 60.0, price=0)  # the refused cycle id changes: WARNING once, INFO after
    assert refusals() == [logging.WARNING]
    assert official.activate_generation_if_changed(database) is None and refusals() == [logging.WARNING, logging.INFO]
    caplog.clear()
    monkeypatch.setattr(official, "_refusals_logged", {})  # another process: the receipt names bad, not bad2 → WARNING once more, then INFO
    assert official.activate_generation_if_changed(database) is None and official.activate_generation_if_changed(database) is None
    assert refusals() == [logging.WARNING, logging.INFO]
    nyse_new = _publish_universe(database, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], _wall())
    written = official.current_generation(database)
    assert written is not None and written["cycles"]["NYSE"] == nyse_new and written["receipt"]["targeted_refused"] == {"ITUB4": bad2}
    good = _targeted_cycle(database, "ITUB4", _wall(), 70.0)  # a valid cycle admitted: the refusal leaves the carried receipt
    admission = official.current_generation(database)
    assert admission is not None and admission["targeted"] == {"ITUB4": good, "WEGE3": wege} and admission["receipt"]["targeted_refused"] == {}
    caplog.clear()
    assert official.activate_generation_if_changed(database) is None and refusals() == []
    assert official.official_row(database, "B3", "ITUB4")["our_tp"] == 70.0 and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]
    assert official.current_generation(database)["cycles"] == {**cycles, "NASDAQ": nasdaq_new, "NYSE": nyse_new}  # type: ignore[index]


def test_a_targeted_admission_numbers_its_attempts_in_the_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    # Z4: the admission's docstring claimed each attempt was numbered, but only the activation pass wrote `attempt`
    database = _database()
    _three_markets(database)
    first = _targeted_cycle(database, "WEGE3", later(1))
    g1 = official.current_generation(database)
    assert g1 is not None and g1["receipt"]["attempt"] == 1 and g1["receipt"]["targeted_admission"]["cycle_id"] == first and g1["receipt"]["targeted_refused"] == {}
    landed: dict[str, str] = {}

    def another_writer() -> None:  # a different admission lands inside this admission's write
        landed["ITUB4"] = _targeted_cycle(database, "ITUB4", later(2))

    calls = _interleave(database, monkeypatch, on_call=2, action=another_writer)  # call 1: the admission reads G1; call 2: inside its write
    second = _targeted_cycle(database, "BBDC4", later(3))
    reads = calls["n"]
    head = official.current_generation(database)
    assert head is not None and head["receipt"]["attempt"] == 2 and head["receipt"]["targeted_admission"]["cycle_id"] == second
    assert head["targeted"] == {"BBDC4": second, "ITUB4": landed["ITUB4"], "WEGE3": first} and reads == 6  # 2 reads per attempt (x2), 2 by the other writer
    assert database.valuation_official_selection(str(head["previous_generation_id"]))["receipt"]["attempt"] == 1  # type: ignore[index]


def test_a_rollback_of_a_universe_cycle_survives_the_automatic_pass_and_the_bootstrap(caplog: pytest.LogCaptureFixture) -> None:
    # W1: the candidates of a pass were the LATEST snapshot per market, so a mesa rollback to an older universe cycle
    # (select_generation) was undone by the next automatic pass and by the bootstrap. The authority rule of Z2 now holds
    # for universe cycles: a candidate PREDICTED at or before the mesa's last explicit order (a re-run keeps the original
    # instant, S1) is not new — the cycle in force is carried (receipt.held_by_explicit_order); only a cycle predicted AFTER
    # the order is activated.
    database = _database()
    cycles = _three_markets(database)  # G0: published at NOW (a fixed past instant)
    g0 = official.current_generation(database)
    assert g0 is not None and g0["receipt"]["held_by_explicit_order"] == [] and g0["receipt"]["explicit_order"] is None
    b3_new = _publish_universe(database, "B3", [_row("PETR4", tp=44.0, buy_in=35.0, price=37.0, internal_tp=43.0),
                                                _row("VALE3", tp=72.0, buy_in=61.0, price=63.0, internal_tp=71.0)], _wall())  # G1
    g1 = official.current_generation(database)
    assert g1 is not None and g1["cycles"] == {**cycles, "B3": b3_new} and g1["previous_generation_id"] == g0["generation_id"]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 44.0  # type: ignore[index]
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    rolled = official.select_generation(database, cycles=g0["cycles"], now=_wall(), activated_by="mesa", reason="rollback B3 to G0")
    assert rolled["cycles"] == cycles and official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0  # type: ignore[index]
    # the automatic pass and the bootstrap keep the rollback (they re-activated b3_new before: the latest snapshot per market)
    assert official.activate_generation_if_changed(database) is None
    assert official.bootstrap_official_selection(database)["generation"] == rolled
    assert official.current_generation(database) == rolled and official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0  # type: ignore[index]
    # another market's cycle published AFTER the order is activated; B3 stays on the order's cycle, named as held
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())
    auto = official.current_generation(database)
    assert auto is not None and auto["previous_generation_id"] == rolled["generation_id"] and auto["cycles"] == {**cycles, "NASDAQ": nasdaq_new}
    assert auto["receipt"]["held_by_explicit_order"] == ["B3"] and auto["receipt"]["carried_markets"] == ["B3"] and auto["receipt"]["changed_markets"] == ["NASDAQ"]
    assert auto["receipt"]["explicit_order"] == rolled["generation_id"] and auto["receipt"]["validation"]["B3"]["cycle_id"] == b3_new  # the held candidate is still documented
    assert auto["session_dates"]["B3"] == rolled["session_dates"]["B3"] and auto["activated_by"] == official.ACTIVATED_BY
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == auto
    health = official.selection_health(database, now=_wall())
    assert health["markets"]["B3"]["carried"] is True and health["markets"]["B3"]["cycle_id"] == cycles["B3"] and health["generation_id"] == auto["generation_id"]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0 and official.official_row(database, "US", "AAPL")["our_tp"] == 260.0  # type: ignore[index]
    # a B3 cycle published AFTER the rollback activates — the order decided over b3_new, not over the future
    b3_after = _publish_universe(database, "B3", [_row("PETR4", tp=46.0, buy_in=36.0, price=38.0, internal_tp=45.0),
                                                  _row("VALE3", tp=74.0, buy_in=62.0, price=64.0, internal_tp=73.0)], _wall())
    after = official.current_generation(database)
    assert after is not None and after["cycles"] == {**cycles, "NASDAQ": nasdaq_new, "B3": b3_after} and after["previous_generation_id"] == auto["generation_id"]
    assert after["receipt"]["held_by_explicit_order"] == [] and after["receipt"]["carried_markets"] == [] and after["receipt"]["changed_markets"] == ["B3"]
    assert official.official_row(database, "B3", "PETR4")["our_tp"] == 46.0 and official.activate_generation_if_changed(database) is None  # type: ignore[index]
    # a rollback to an older cycle while an even newer one is published before the order: held too; the bootstrap of a fresh process agrees
    rolled_again = official.select_generation(database, cycles={**after["cycles"], "B3": b3_new}, now=_wall(), activated_by="mesa", reason="rollback B3 to G1")
    assert official.bootstrap_official_selection(database)["generation"] == rolled_again and official.official_row(database, "B3", "PETR4")["our_tp"] == 44.0  # type: ignore[index]
    assert not any("is not after the current generation" in message for message in caplog.messages)  # wall clocks throughout: nothing advanced
    # without an order nothing is held: a cycle published in the past (before the generation in force) still activates
    fresh = _database()
    fresh_cycles = _three_markets(fresh)
    nyse_past = _publish_universe(fresh, "NYSE", [_row("KO", tp=75.0, buy_in=63.0, price=66.0, internal_tp=74.0)], NOW + timedelta(minutes=5))
    fresh_head = official.current_generation(fresh)
    assert fresh_head is not None and fresh_head["cycles"] == {**fresh_cycles, "NYSE": nyse_past} and fresh_head["receipt"]["held_by_explicit_order"] == []


def test_an_explicit_order_refuses_a_clock_in_the_future_beyond_the_tolerance() -> None:
    # W2: an order dated in the future would stand over cycles not yet published (W1/Z2) and hold every automatic
    # activation behind it (Z1). The order carries the mesa's wall clock: further ahead of this host's than 60 s is a
    # wrong clock — refused before any validation, symmetric to the D3 refusal of a clock behind the head.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None and official.EXPLICIT_CLOCK_TOLERANCE == timedelta(seconds=60)
    with pytest.raises(ValueError, match="in the future by more than 60 s"):
        official.select_generation(database, cycles=cycles, now=datetime.now(timezone.utc) + timedelta(seconds=61), activated_by="mesa", reason="future")
    with pytest.raises(ValueError, match="in the future"):  # the guard runs first: a future clock with an incomplete map is refused for the clock
        official.select_generation(database, cycles={"B3": cycles["B3"]}, now=datetime.now(timezone.utc) + timedelta(hours=1), activated_by="mesa", reason="future")
    with pytest.raises(ValueError, match="in the future"):  # a naive datetime is UTC
        official.select_generation(database, cycles=cycles, now=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5), activated_by="mesa", reason="naive")
    assert official.current_generation(database) == g0
    rolled = official.select_generation(database, cycles=cycles, now=datetime.now(timezone.utc) + timedelta(seconds=30), activated_by="mesa", reason="drill")  # within the tolerance
    assert official.current_generation(database) == rolled and rolled["receipt"] == {"reason": "drill", "explicit": True}
    with pytest.raises(ValueError, match="earlier than the current generation"):  # D3, the other side
        official.select_generation(database, cycles=cycles, now=datetime.now(timezone.utc), activated_by="mesa", reason="behind")


def test_an_order_is_recognized_by_its_marker_never_by_activated_by(caplog: pytest.LogCaptureFixture) -> None:
    # W3: the authority of Z2 was keyed by `activated_by != ACTIVATED_BY`, so an automatic pass run with a custom
    # activated_by (an ops CLI) became an "order" and blocked the recovery of every targeted cycle registered before it.
    # The automatic functions have no activated_by parameter; an order is the marker select_generation alone writes
    # (receipt.explicit = True) and the automatic path strips that key from any receipt it is handed.
    import inspect
    from app.database import SelectionConflict
    assert "activated_by" not in inspect.signature(official.activate_generation_if_changed).parameters
    assert "activated_by" not in inspect.signature(official.admit_targeted_cycle).parameters
    database = _database()
    _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None

    def another_host_wins(generation: dict[str, Any]) -> None:
        raise SelectionConflict(f"generation {generation['previous_generation_id']} already has a successor")

    with pytest.MonkeyPatch.context() as race:  # a registered targeted cycle whose admission lost: the next pass recovers it (Y3)
        race.setattr(database, "insert_valuation_official_selection", another_host_wins)
        wege = _targeted_cycle(database, "WEGE3", _wall())
    assert official.current_generation(database) == g0
    # an automatic generation written by a custom writer name — even handed a forged marker — is not an order
    forged = official._new_generation(database, expected_previous=g0["generation_id"], cycles=g0["cycles"], targeted={}, source=official.SOURCE_OFFICIAL,
                                      source_version="7", session_dates=g0["session_dates"], activated_by="ops-cli", receipt={"explicit": True, "reason": "forged"})
    assert forged is not None and forged["activated_by"] == "ops-cli" and forged["receipt"] == {"reason": "forged"}
    assert database.latest_explicit_valuation_official_selection() is None
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    passed = official.activate_generation_if_changed(database)  # not blocked by the ops-cli row
    assert passed is not None and passed["previous_generation_id"] == forged["generation_id"] and passed["activated_by"] == official.ACTIVATED_BY
    assert passed["targeted"] == {"WEGE3": wege} and passed["receipt"]["targeted_recovered"] == {"WEGE3": wege}
    assert passed["receipt"]["explicit_order"] is None and passed["receipt"]["held_by_explicit_order"] == [] and "explicit" not in passed["receipt"]
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]
    # a real order carries the marker and is the authority — whatever its activated_by, even the automatic writer's own name
    purged = official.select_generation(database, cycles=g0["cycles"], targeted={}, now=_wall(), activated_by=official.ACTIVATED_BY, reason="purge")
    assert purged["receipt"] == {"reason": "purge", "explicit": True}
    order = database.latest_explicit_valuation_official_selection()
    assert order is not None and order["generation_id"] == purged["generation_id"]
    assert official.activate_generation_if_changed(database) is None and official.official_row(database, "B3", "WEGE3") is None  # the purge stands
    # rows that merely LOOK like orders are not: "mesa" as activated_by without the marker; the marker as a string; the marker false
    for generation_id, activated_by, receipt in (("mesa-named", "mesa", {"reason": "seeded"}), ("string-marker", "mesa", {"explicit": "true"}),
                                                 ("false-marker", "mesa", {"explicit": False})):
        head = official.current_generation(database)
        assert head is not None
        database.insert_valuation_official_selection({**head, "generation_id": generation_id, "previous_generation_id": head["generation_id"],
                                                      "activated_at": _wall().isoformat(), "activated_by": activated_by, "receipt": receipt})
    assert database.latest_explicit_valuation_official_selection()["generation_id"] == purged["generation_id"]  # type: ignore[index]
    assert official.current_generation(database)["generation_id"] == "false-marker"  # type: ignore[index]
    # the admission path writes ACTIVATED_BY too
    itub = _targeted_cycle(database, "ITUB4", _wall())
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"ITUB4": itub} and admitted["activated_by"] == official.ACTIVATED_BY and "explicit" not in admitted["receipt"]


def test_a_legacy_row_chained_behind_its_predecessor_is_repaired_and_reported(caplog: pytest.LogCaptureFixture) -> None:
    # W4: a row written before Z1 by a host whose clock ran behind is chained on its predecessor but dated BEFORE it: the
    # readers' head (max(activated_at)) stays the predecessor, whose UNIQUE successor slot is taken — every writer chained
    # on the head, conflicted and gave up: the chain was locked for good. A conflict that finds the head unmoved now walks
    # to the chain tip and chains on it; the health names the successor while the head is not the tip.
    database = _database()
    cycles = _three_markets(database)
    g0 = official.current_generation(database)
    assert g0 is not None
    behind_at = official._utc(g0["activated_at"]) - timedelta(seconds=1)
    database.insert_valuation_official_selection({**g0, "generation_id": "behind-row", "previous_generation_id": g0["generation_id"],
                                                  "targeted": {"WEGE3": "wege-legacy"}, "activated_at": behind_at.isoformat()})
    assert official.current_generation(database) == g0  # never the head for the readers
    assert database.valuation_official_selection_successor(g0["generation_id"])["generation_id"] == "behind-row"  # type: ignore[index]
    assert database.valuation_official_selection_successor("behind-row") is None and database.valuation_official_selection_successor("nope") is None
    health = official.selection_health(database, now=_wall())
    assert health["head_has_successor"] == "behind-row" and "successor dated behind it (behind-row)" in health["detail"] and health["generation_id"] == g0["generation_id"]
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())
    head = official.current_generation(database)
    assert head is not None and head["cycles"] == {**cycles, "NASDAQ": nasdaq_new} and head["previous_generation_id"] == "behind-row"
    assert head["receipt"]["repaired_chain"] == {"head": g0["generation_id"], "chained_on": "behind-row"} and head["receipt"]["attempt"] == 1
    assert head["targeted"] == {} and official._utc(head["activated_at"]) > official._utc(g0["activated_at"])  # the head's content, dated after the head
    assert sum("chained on the tip instead" in message for message in caplog.messages) == 1
    assert official.selection_health(database, now=_wall())["head_has_successor"] is None
    assert [item["generation_id"] for item in database._valuation_official_selections] == [g0["generation_id"], "behind-row", head["generation_id"]]
    itub = _targeted_cycle(database, "ITUB4", _wall())  # later writers chain normally
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["previous_generation_id"] == head["generation_id"] and "repaired_chain" not in admitted["receipt"]
    assert admitted["targeted"] == {"ITUB4": itub} and official.official_row(database, "US", "AAPL")["our_tp"] == 260.0  # type: ignore[index]
    # the explicit path repairs too: the mesa can act on a locked chain (D3 still holds its clock at or after the head)
    database.insert_valuation_official_selection({**admitted, "generation_id": "behind-2", "previous_generation_id": admitted["generation_id"],
                                                  "activated_at": (official._utc(admitted["activated_at"]) - timedelta(seconds=1)).isoformat()})
    assert official.current_generation(database) == admitted
    rolled = official.select_generation(database, cycles=g0["cycles"], now=_wall(), activated_by="mesa", reason="rollback on a locked chain")
    assert rolled["previous_generation_id"] == "behind-2" and rolled["receipt"] == {"reason": "rollback on a locked chain", "explicit": True,
                                                                                    "repaired_chain": {"head": admitted["generation_id"], "chained_on": "behind-2"}}
    assert official.current_generation(database) == rolled and official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    # two legacy rows in a row: the walk reaches the tip; the clock is advanced past the later of the tip and the head when needed
    rolled_at = official._utc(rolled["activated_at"])
    database.insert_valuation_official_selection({**rolled, "generation_id": "behind-3", "previous_generation_id": rolled["generation_id"],
                                                  "activated_at": (rolled_at - timedelta(seconds=2)).isoformat(), "receipt": {}})
    database.insert_valuation_official_selection({**rolled, "generation_id": "behind-4", "previous_generation_id": "behind-3",
                                                  "activated_at": (rolled_at - timedelta(seconds=1)).isoformat(), "receipt": {}})
    assert official.selection_health(database, now=_wall())["head_has_successor"] == "behind-3"
    stale = {**rolled, "generation_id": "stale-clock", "previous_generation_id": rolled["generation_id"], "activated_at": (rolled_at - timedelta(seconds=1)).isoformat(),
             "receipt": {"attempt": 1}}
    repaired = official._repaired(database, stale, expected_previous=rolled["generation_id"], error=RuntimeError("already has a successor"), strict=False)
    assert repaired is not None and repaired["previous_generation_id"] == "behind-4" and official._utc(repaired["activated_at"]) == rolled_at + timedelta(microseconds=1)
    assert official.current_generation(database) == repaired and repaired["receipt"] == {"attempt": 1, "repaired_chain": {"head": rolled["generation_id"], "chained_on": "behind-4"}}
    assert official.selection_health(database, now=_wall())["head_has_successor"] is None
    # a conflict whose head MOVED is the ordinary race, not a repair: None on the automatic path, ValueError on the explicit one
    assert official._repaired(database, stale, expected_previous=rolled["generation_id"], error=RuntimeError("x"), strict=False) is None
    with pytest.raises(ValueError, match="selection conflict: x"):
        official._repaired(database, stale, expected_previous=rolled["generation_id"], error=RuntimeError("x"), strict=True)
    # a conflict with the head unmoved and NO successor visible (the storage refused for another reason) is given up, never repaired
    assert official._repaired(database, {**stale, "previous_generation_id": repaired["generation_id"]}, expected_previous=repaired["generation_id"],
                              error=RuntimeError("y"), strict=False) is None
    assert official.current_generation(database) == repaired
    # the health of an empty store carries the key too
    assert official.selection_health(_database(), now=_wall())["head_has_successor"] is None


def test_a_re_run_of_the_same_refused_targeted_cycle_is_info_once_the_receipt_names_it(monkeypatch: pytest.MonkeyPatch,
                                                                                         caplog: pytest.LogCaptureFixture) -> None:
    # W5: the admission validated before reading the head and never passed the head's known refusals (receipt.targeted_refused)
    # to the validator, so a re-run of the same refused targeted cycle (record_snapshot is idempotent per cycle) in another
    # process was a WARNING every time, while the recovery pass (Z3) already said INFO.
    monkeypatch.setattr(official, "_refusals_logged", {})
    database = _database()
    _three_markets(database)
    caplog.set_level(logging.INFO, logger="app.valuation_official")

    def refusals() -> list[int]:
        return [record.levelno for record in caplog.records if "refused" in record.getMessage() and "ITUB4" in record.getMessage()]

    def another_process() -> None:
        caplog.clear()
        monkeypatch.setattr(official, "_refusals_logged", {})

    bad = _targeted_cycle(database, "ITUB4", _wall(), price=0, internal_tp=None)  # registered (TP, buy-in), invalid (price, internal TP)
    assert refusals() == [logging.WARNING]  # unknown to this process and to the head's receipt
    another_process()
    assert official.admit_targeted_cycle(database, symbol="ITUB4", cycle_id=bad) is None and refusals() == [logging.WARNING]  # no receipt names it yet
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())
    written = official.current_generation(database)
    assert written is not None and written["cycles"]["NASDAQ"] == nasdaq_new and written["receipt"]["targeted_refused"] == {"ITUB4": bad}
    another_process()
    assert official.admit_targeted_cycle(database, symbol=" itub4 ", cycle_id=bad) is None and refusals() == [logging.INFO]  # the head names it: INFO
    another_process()
    snapshot = database.analysis_snapshot_by_id(bad)  # the real re-run path: the persistence hook on the same cycle
    assert snapshot is not None and official.record_snapshot(database, snapshot) == {"recorded": 0, "generation": None} and refusals() == [logging.INFO]
    assert official.current_generation(database) == written
    another_process()
    bad2 = _targeted_cycle(database, "ITUB4", _wall(), 60.0, price=0)  # a different refused cycle id: WARNING once
    assert refusals() == [logging.WARNING]
    another_process()
    assert official.admit_targeted_cycle(database, symbol="ITUB4", cycle_id=bad2) is None and refusals() == [logging.WARNING]  # the receipt names bad, not bad2
    good = _targeted_cycle(database, "ITUB4", _wall(), 70.0)
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"ITUB4": good} and admitted["receipt"]["targeted_refused"] == {}
    another_process()
    assert official.admit_targeted_cycle(database, symbol="ITUB4", cycle_id=good) is None and refusals() == []  # already admitted: nothing validated, nothing logged
    # without a generation there is nothing to admit into and nothing is validated; the bootstrap's recovery pass validates it (Y3)
    fresh = _database()
    another_process()
    fresh_bad = _targeted_cycle(fresh, "ITUB4", _wall(), price=0, internal_tp=None)
    assert "ITUB4" in fresh.valuation_predictions_for_cycle(fresh_bad) and official.current_generation(fresh) is None and refusals() == []
    _three_markets(fresh)
    assert refusals() == [logging.WARNING] and official.current_generation(fresh)["receipt"]["targeted_refused"] == {"ITUB4": fresh_bad}  # type: ignore[index]


# --- rev 6: Codex residuals B2 (two clocks on the record) and B3 (the explicit order governs the direct admission) -----------


def _rerun_universe(database: Database, market: str, rows: list[dict], *, rerun_of: str, prediction_instant: str | None, at: datetime) -> str:
    inputs: dict[str, Any] = {"methodology_version": 7, "market": market, "source_manifest_sha256": "a" * 64, "rerun_of": rerun_of}
    if prediction_instant is not None:
        inputs["prediction_instant"] = prediction_instant
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", inputs, {"rows": rows, "universe_size": len(rows) + 1}, at)


def test_a_record_carries_its_own_publication_clock_distinct_from_the_prediction_instant(caplog: pytest.LogCaptureFixture) -> None:
    # B2 (rev 6, spec rev 7 line 223): prediction_instant = the published_at of the ORIGINAL live evaluation; published_at = the
    # factual availability of the snapshot that contains the record — for a re-run, the re-run date, never retro-dated. The
    # record had ONE clock; now it has two, both hashed (VALUATION_PREDICTION_V2), persisted, round-tripped, served and graded.
    database = _database()
    cycles = _three_markets(database)
    live = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert live is not None and live["schema"] == official.PREDICTION_SCHEMA == "VALUATION_PREDICTION_V2"
    assert live["published_at"] == live["prediction_instant"] == (NOW + timedelta(minutes=1)).isoformat()  # a live cycle: both clocks equal
    assert live["decomposition"]["provenance"]["rerun_of"] is None
    core = {key: value for key, value in live.items() if key not in ("id", "row_sha256")}
    assert "published_at" in core and official.canonical_sha256(core) == live["row_sha256"]
    row = _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)
    shifted = official.prediction_from_row(row, market="NASDAQ", scope="universe", cycle_id=cycles["NASDAQ"], source_version="7",
                                           prediction_instant=NOW + timedelta(minutes=1), published_at=NOW + timedelta(days=1), source_manifest_sha256="a" * 64)
    assert shifted is not None and shifted["prediction_instant"] == live["prediction_instant"] and shifted["published_at"] == (NOW + timedelta(days=1)).isoformat()
    assert shifted["row_sha256"] != live["row_sha256"]  # the publication clock is part of the identity
    assert {key: value for key, value in shifted.items() if key not in ("id", "row_sha256", "published_at")} == {key: value for key, value in live.items() if key not in ("id", "row_sha256", "published_at")}
    # served: the stamp carries the record's own publication clock, and every item model declares it
    served = official.official_row(database, "US", "AAPL")
    assert served is not None and served["official_published_at"] == live["published_at"] and served["prediction_instant"] == live["prediction_instant"]
    assert official.item_stamp(served)["official_published_at"] == live["published_at"] and official.item_stamp(None)["official_published_at"] is None
    assert official.official_rows(database, "NASDAQ")["AAPL"]["official_published_at"] == live["published_at"]
    from app.schemas import B3Candidate, MatrixPowerItem
    assert "official_published_at" in B3Candidate.model_fields and "official_published_at" in MatrixPowerItem.model_fields
    # a synthetic re-run cycle: a NEW cycle, published now, reproducing the original's prediction — prediction_instant = the
    # original's, published_at = the re-run's, the session the original's, the original named in the provenance
    rerun_at = _wall()
    rerun = _rerun_universe(database, "NASDAQ", [row], rerun_of=cycles["NASDAQ"], prediction_instant=live["prediction_instant"], at=rerun_at)
    record = database.valuation_prediction_record(rerun, "AAPL")
    assert record is not None and record["cycle_id"] == rerun and record["prediction_instant"] == live["prediction_instant"]
    assert record["published_at"] == rerun_at.isoformat() and record["published_at"] != record["prediction_instant"]
    assert record["session_date"] == live["session_date"] == "2026-09-04" and record["decomposition"]["provenance"]["rerun_of"] == cycles["NASDAQ"]
    assert official.cycle_clocks(database.analysis_snapshot_by_id(rerun) or {}) == (_utc_(live["prediction_instant"]), rerun_at, cycles["NASDAQ"])
    head = official.current_generation(database)  # the re-run is a new cycle published after the generation: activated, with the ORIGINAL's session
    assert head is not None and head["cycles"]["NASDAQ"] == rerun and head["session_dates"]["NASDAQ"] == live["session_date"]
    assert head["receipt"]["validation"]["NASDAQ"]["published_at"] == rerun_at.isoformat() and head["receipt"]["validation"]["NASDAQ"]["session_date"] == "2026-09-04"
    stamped = official.official_row(database, "US", "AAPL")
    assert stamped is not None and stamped["prediction_instant"] == live["prediction_instant"] and stamped["official_published_at"] == rerun_at.isoformat()
    assert stamped["official_row_sha256"] == record["row_sha256"] != live["row_sha256"]
    # the PostgreSQL-shaped reader rebuilds BOTH clocks in UTC whatever the session zone, and the stored hash re-verifies
    for zone in (ZoneInfo("UTC"), ZoneInfo("America/Sao_Paulo"), ZoneInfo("Asia/Tokyo")):
        rebuilt = database._prediction_record(_pg_row(record, zone))
        assert rebuilt == record and rebuilt["published_at"] == rerun_at.isoformat() and rebuilt["prediction_instant"] == live["prediction_instant"]
        assert official.canonical_sha256({key: value for key, value in rebuilt.items() if key not in ("id", "row_sha256")}) == record["row_sha256"]
    # studies and grading: the call keeps the prediction's instant as changed_at and the record's publication apart
    from app.valuation_accuracy import load_prediction_calls
    calls = load_prediction_calls([record, live])
    assert calls[0].changed_at.isoformat() == live["prediction_instant"] and calls[0].published_at == rerun_at and calls[0].cycle_id == rerun
    assert calls[1].published_at == datetime.fromisoformat(live["published_at"]) == calls[1].changed_at
    assert load_prediction_calls([{key: value for key, value in live.items() if key != "published_at"}])[0].published_at is None  # a legacy record
    # a re-run that names no original instant, or names one AFTER its own publication, is NOT recordable (never mis-dated) and not selectable
    caplog.set_level(logging.WARNING, logger="app.valuation_official")
    ko = [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)]
    nameless = _rerun_universe(database, "NYSE", ko, rerun_of=cycles["NYSE"], prediction_instant=None, at=_wall())
    assert database.valuation_predictions_for_cycle(nameless) == {} and official.current_generation(database) == head
    assert any("names no original prediction_instant — not recordable (B2)" in message for message in caplog.messages)
    forward = _rerun_universe(database, "NYSE", ko, rerun_of=cycles["NYSE"], prediction_instant=(_wall() + timedelta(days=1)).isoformat(), at=_wall())
    assert database.valuation_predictions_for_cycle(forward) == {} and official.current_generation(database) == head
    assert any("AFTER its own publication" in message and "not recordable (B2)" in message for message in caplog.messages)
    for cycle_id in (nameless, forward):
        snapshot = database.analysis_snapshot_by_id(cycle_id)
        assert snapshot is not None and official.cycle_clocks(snapshot) is None
        validation = official.cycle_validation({**snapshot, "analysis_type": "valuation_universe", "entity_key": "NYSE_UNIVERSE"})
        assert validation["valid"] is False and validation["session_date"] is None
    assert official.official_row(database, "NYSE", "KO")["official_cycle_id"] == cycles["NYSE"]  # type: ignore[index]  # NYSE stays on its live cycle


def _utc_(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def test_the_explicit_order_governs_the_direct_admission_and_a_replay_of_an_old_cycle(monkeypatch: pytest.MonkeyPatch,
                                                                                       caplog: pytest.LogCaptureFixture) -> None:
    # B3 (rev 6, F393-10): the authority of the mesa's last explicit order held on the recovery pass (Z2) and on universe
    # cycles (W1), but NOT on the direct admission: the persistence hook replaying the SAME old targeted cycle
    # (record_snapshot on a snapshot already recorded, recorded = 0) called admit_targeted_cycle, which validated the cycle,
    # found it absent from the head's targeted map and admitted it again — a purge was undone, a rollback restored to the
    # newer cycle. The order now governs the direct path too, re-read on every attempt; only a cycle published after it is admitted.
    from app.database import SelectionConflict
    database = _database()
    cycles = _three_markets(database)
    c1 = _targeted_cycle(database, "WEGE3", _wall())  # TGT/TP50
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["targeted"] == {"WEGE3": c1} and official.official_row(database, "B3", "WEGE3")["our_tp"] == 50.0  # type: ignore[index]
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()  # the bootstrap warnings of the two-market window above are not this test's
    purged = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="purge")
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == purged  # the normal pass keeps the purge
    chain = [item["generation_id"] for item in database._valuation_official_selections]
    # the replay of the SAME snapshot through the persistence hook: zero records inserted, NO generation created, nothing restored
    snapshot = database.analysis_snapshot_by_id(c1)
    assert snapshot is not None and official.record_snapshot(database, snapshot) == {"recorded": 0, "generation": None}
    assert official.admit_targeted_cycle(database, symbol=" wege3 ", cycle_id=c1) is None  # the direct call too
    assert [item["generation_id"] for item in database._valuation_official_selections] == chain and official.current_generation(database) == purged
    assert official.official_row(database, "B3", "WEGE3") is None and len(database.valuation_predictions_for_cycle(c1)) == 1
    held = [record for record in caplog.records if "held, not admitted" in record.getMessage()]
    assert len(held) == 2 and {record.levelno for record in held} == {logging.INFO} and c1 in held[0].getMessage() and purged["generation_id"] in held[0].getMessage()
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)  # nothing validated, nothing warned for a held cycle
    assert official._predicted_at_or_before(database, "no-such-cycle", purged) is True  # an unreadable cycle is held too, never admitted over an order
    # control: a cycle genuinely published AFTER the order is admitted (TP80)
    c2 = _targeted_cycle(database, "WEGE3", _wall(), 80.0)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": c2} and head["previous_generation_id"] == purged["generation_id"]
    assert head["receipt"]["targeted_admission"]["cycle_id"] == c2 and official.official_row(database, "B3", "WEGE3")["our_tp"] == 80.0  # type: ignore[index]
    # a rollback to c1 while c2 is registered: the replay of c2 (and of c1 itself) restores nothing — the rollback stays on c1
    rolled = official.select_generation(database, cycles=cycles, targeted={"WEGE3": c1}, now=_wall(), activated_by="mesa", reason="rollback to c1")
    for cycle_id in (c2, c1):
        replayed = database.analysis_snapshot_by_id(cycle_id)
        assert replayed is not None and official.record_snapshot(database, replayed) == {"recorded": 0, "generation": None}
    assert official.current_generation(database) == rolled and official.official_row(database, "B3", "WEGE3")["official_cycle_id"] == c1  # type: ignore[index]
    assert official.activate_generation_if_changed(database) is None
    # the order is re-read on EVERY attempt: a purge landing between the first and the second attempt of an admission is honoured
    # by the second — the cycle (published before that purge) is held, and the pass after it keeps the purge (Z2, same clock)
    original_insert = database.insert_valuation_official_selection
    landed: list[dict[str, Any]] = []

    def purge_lands_inside_the_first_attempt(generation: dict[str, Any]) -> None:
        if landed:
            return original_insert(generation)
        landed.append({})  # the guard first: select_generation below inserts through this very function
        landed[0] = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="purge during admission")
        raise SelectionConflict(f"generation {generation['previous_generation_id']} already has a successor")

    monkeypatch.setattr(database, "insert_valuation_official_selection", purge_lands_inside_the_first_attempt)
    caplog.clear()
    c3 = _targeted_cycle(database, "WEGE3", _wall(), 120.0)
    assert landed and official.current_generation(database) == landed[0] and landed[0]["previous_generation_id"] == rolled["generation_id"]
    assert official.official_row(database, "B3", "WEGE3") is None and official.activate_generation_if_changed(database) is None
    held_c3 = [record for record in caplog.records if "held, not admitted" in record.getMessage() and c3 in record.getMessage()]
    assert len(held_c3) == 1 and landed[0]["generation_id"] in held_c3[0].getMessage()
    assert not any("recomposition attempts" in message for message in caplog.messages)  # the second attempt held, it did not keep retrying
    # control again: a cycle published after that purge is admitted on its first attempt
    c4 = _targeted_cycle(database, "WEGE3", _wall(), 90.0)
    final = official.current_generation(database)
    assert final is not None and final["targeted"] == {"WEGE3": c4} and final["previous_generation_id"] == landed[0]["generation_id"] and final["receipt"]["attempt"] == 1
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 90.0  # type: ignore[index]


# --- rev 6 residuals (S1–S5, S8): the authority clock is the prediction instant; recency on the direct admission; the CHECK
# --- mirrored; readers tie-break like the selection; unrecordable re-runs warn once; malformed published_at keeps the call


def _rerun_targeted(database: Database, symbol: str, *, rerun_of: str, prediction_instant: str | None, at: datetime, tp: float = 50.0) -> str:
    inputs: dict[str, Any] = {"methodology_version": 7, "rerun_of": rerun_of}
    if prediction_instant is not None:
        inputs["prediction_instant"] = prediction_instant
    return database.save_analysis_snapshot("security_valuation", symbol, "mv-1", inputs, {"row": _targeted(symbol, tp)}, at)


def test_a_re_run_published_after_an_explicit_order_never_re_opens_what_the_order_decided(caplog: pytest.LogCaptureFixture) -> None:
    # S1: the authority clock of an order was the cycle's PUBLICATION, so a RE-RUN of a purged (or rolled-back) cycle — a new
    # cycle published after the order, reproducing the SAME prediction (inputs.rerun_of + inputs.prediction_instant) — was admitted
    # by the direct path, recovered by the pass and re-activated on the universe path (W1), undoing the order with the very
    # prediction it had decided over. The clock is now the PREDICTION instant (a re-run keeps the original's) on all three paths.
    database = _database()
    cycles = _three_markets(database)
    c1 = _targeted_cycle(database, "WEGE3", _wall())
    c1_record = database.valuation_prediction_record(c1, "WEGE3")
    assert c1_record is not None and official.current_generation(database)["targeted"] == {"WEGE3": c1}  # type: ignore[index]
    purged = official.select_generation(database, cycles=cycles, targeted={}, now=_wall(), activated_by="mesa", reason="purge")
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    # the direct admission (the persistence hook on the re-run: a NEW cycle, so its record IS inserted) holds the re-run
    rerun = _rerun_targeted(database, "WEGE3", rerun_of=c1, prediction_instant=c1_record["prediction_instant"], at=_wall())
    rerun_record = database.valuation_prediction_record(rerun, "WEGE3")
    assert rerun_record is not None and rerun_record["prediction_instant"] == c1_record["prediction_instant"] and rerun_record["published_at"] > official._utc(purged["activated_at"]).isoformat()
    assert official.current_generation(database) == purged and official.official_row(database, "B3", "WEGE3") is None
    held = [record for record in caplog.records if "held, not admitted" in record.getMessage() and rerun in record.getMessage()]
    assert len(held) == 1 and held[0].levelno == logging.INFO and "predicted at or before" in held[0].getMessage()
    assert official._predicted_at_or_before(database, rerun, purged) is True and official._predicted_at_or_before(database, c1, purged) is True
    # the recovery pass and the bootstrap hold it too — the re-run is the LATEST targeted record of the symbol (S4) and is skipped by its prediction instant
    assert database.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL)["WEGE3"]["cycle_id"] == rerun
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == purged
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
    # a genuinely NEW prediction after the order is admitted
    c2 = _targeted_cycle(database, "WEGE3", _wall(), 80.0)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": c2} and head["previous_generation_id"] == purged["generation_id"]
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 80.0  # type: ignore[index]
    # a rollback to c1 while c2 is registered: a re-run of c2 (published after the rollback) restores nothing; a re-run of c1 changes nothing
    rolled = official.select_generation(database, cycles=cycles, targeted={"WEGE3": c1}, now=_wall(), activated_by="mesa", reason="rollback to c1")
    c2_record = database.valuation_prediction_record(c2, "WEGE3")
    assert c2_record is not None
    rerun_c2 = _rerun_targeted(database, "WEGE3", rerun_of=c2, prediction_instant=c2_record["prediction_instant"], at=_wall(), tp=80.0)
    rerun_c1 = _rerun_targeted(database, "WEGE3", rerun_of=c1, prediction_instant=c1_record["prediction_instant"], at=_wall())
    assert database.valuation_prediction_record(rerun_c2, "WEGE3") is not None and database.valuation_prediction_record(rerun_c1, "WEGE3") is not None
    assert official.current_generation(database) == rolled and official.official_row(database, "B3", "WEGE3")["official_cycle_id"] == c1  # type: ignore[index]
    assert official.activate_generation_if_changed(database) is None and official.bootstrap_official_selection(database)["generation"] == rolled
    # the universe path (W1): a re-run of the rolled-back universe cycle, published after the rollback, is held — the market stays on the order's cycle
    b3_new = _publish_universe(database, "B3", [_row("PETR4", tp=44.0, buy_in=35.0, price=37.0, internal_tp=43.0),
                                                _row("VALE3", tp=72.0, buy_in=61.0, price=63.0, internal_tp=71.0)], _wall())
    assert official.current_generation(database)["cycles"]["B3"] == b3_new  # type: ignore[index]
    rolled_b3 = official.select_generation(database, cycles={**cycles}, targeted={"WEGE3": c1}, now=_wall(), activated_by="mesa", reason="rollback B3")
    b3_snapshot = database.analysis_snapshot_by_id(b3_new)
    assert b3_snapshot is not None
    b3_rerun = _rerun_universe(database, "B3", b3_snapshot["outputs"]["rows"], rerun_of=b3_new, prediction_instant=official._utc(b3_snapshot["published_at"]).isoformat(), at=_wall())
    assert database.valuation_prediction_record(b3_rerun, "PETR4") is not None  # recorded (a new cycle)...
    assert official.current_generation(database) == rolled_b3 and official.official_row(database, "B3", "PETR4")["our_tp"] == 40.0  # type: ignore[index]  # ...not activated
    assert official.selectable_cycles(database)["B3"]["cycle_id"] == b3_rerun and official.selectable_cycles(database)["B3"]["prediction_instant"] == official._utc(b3_snapshot["published_at"]).isoformat()
    nasdaq_new = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], _wall())  # a live cycle after the order
    after = official.current_generation(database)
    assert after is not None and after["cycles"] == {**cycles, "NASDAQ": nasdaq_new} and after["receipt"]["held_by_explicit_order"] == ["B3"]
    assert after["receipt"]["validation"]["B3"]["cycle_id"] == b3_rerun and after["targeted"] == {"WEGE3": c1}
    assert official.bootstrap_official_selection(database)["generation"] == after
    # a re-run whose clocks cannot be read is held too (nothing unknown is admitted over an order)
    nameless = _rerun_targeted(database, "WEGE3", rerun_of=c1, prediction_instant=None, at=_wall())
    assert database.valuation_predictions_for_cycle(nameless) == {} and official._predicted_at_or_before(database, nameless, rolled_b3) is True
    assert official.admit_targeted_cycle(database, symbol="WEGE3", cycle_id=nameless) is None and official.current_generation(database) == after


def test_a_replay_of_an_old_targeted_cycle_with_no_order_after_it_is_not_admitted(caplog: pytest.LogCaptureFixture) -> None:
    # S2: c1 (TP50) then c2 (TP80) admitted; replaying the SNAPSHOT of c1 (the persistence hook, recorded = 0; or the direct call)
    # found c1 absent from the head's targeted map, validated it and admitted it: a generation serving TP50, and the next
    # activation pass recovered c2 — flip-flop generations and a downgraded served number. The direct admission now applies the
    # recovery's recency rule: a candidate not newer than the held record's prediction is not admitted (INFO, no generation).
    database = _database()
    cycles = _three_markets(database)
    c1 = _targeted_cycle(database, "WEGE3", _wall())
    c2 = _targeted_cycle(database, "WEGE3", _wall(), 80.0)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": c2} and official.official_row(database, "B3", "WEGE3")["our_tp"] == 80.0  # type: ignore[index]
    chain = [item["generation_id"] for item in database._valuation_official_selections]
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    snapshot = database.analysis_snapshot_by_id(c1)
    assert snapshot is not None and official.record_snapshot(database, snapshot) == {"recorded": 0, "generation": None}
    assert official.admit_targeted_cycle(database, symbol="wege3", cycle_id=c1) is None
    assert [item["generation_id"] for item in database._valuation_official_selections] == chain and official.current_generation(database) == head
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 80.0 and official.activate_generation_if_changed(database) is None  # type: ignore[index]
    not_newer = [record for record in caplog.records if "is not newer than the cycle the generation holds" in record.getMessage()]
    assert len(not_newer) == 2 and {record.levelno for record in not_newer} == {logging.INFO} and c1 in not_newer[0].getMessage() and c2 in not_newer[0].getMessage()
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)  # nothing validated, nothing warned
    # the same with an explicit order OLDER than both cycles: the order does not hold c1 (predicted after it) — the recency rule does
    fresh = _database()
    fresh_cycles = _three_markets(fresh)
    order = official.select_generation(fresh, cycles=fresh_cycles, now=_wall(), activated_by="mesa", reason="an old order")
    f1 = _targeted_cycle(fresh, "WEGE3", _wall())
    f2 = _targeted_cycle(fresh, "WEGE3", _wall(), 80.0)
    fresh_head = official.current_generation(fresh)
    assert fresh_head is not None and fresh_head["targeted"] == {"WEGE3": f2} and fresh.latest_explicit_valuation_official_selection() == order
    assert official._predicted_at_or_before(fresh, f1, order) is False
    fresh_snapshot = fresh.analysis_snapshot_by_id(f1)
    assert fresh_snapshot is not None and official.record_snapshot(fresh, fresh_snapshot) == {"recorded": 0, "generation": None}
    assert official.current_generation(fresh) == fresh_head and official.official_row(fresh, "B3", "WEGE3")["our_tp"] == 80.0  # type: ignore[index]
    assert official.activate_generation_if_changed(fresh) is None
    # a genuinely newer cycle is admitted; a re-run of the held cycle (tied on prediction_instant) is not
    f3 = _targeted_cycle(fresh, "WEGE3", _wall(), 90.0)
    assert official.current_generation(fresh)["targeted"] == {"WEGE3": f3}  # type: ignore[index]
    f3_record = fresh.valuation_prediction_record(f3, "WEGE3")
    assert f3_record is not None
    f3_rerun = _rerun_targeted(fresh, "WEGE3", rerun_of=f3, prediction_instant=f3_record["prediction_instant"], at=_wall(), tp=90.0)
    assert fresh.valuation_prediction_record(f3_rerun, "WEGE3") is not None and official.current_generation(fresh)["targeted"] == {"WEGE3": f3}  # type: ignore[index]
    assert official.activate_generation_if_changed(fresh) is None


def test_a_publication_before_the_prediction_is_refused_by_the_record_builder_and_the_memory_double() -> None:
    # S3: prediction_from_row accepted published_at < prediction_instant (the memory double stored it; PostgreSQL's CHECK refuses it)
    database = _database()
    row = _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)
    with pytest.raises(ValueError, match="precedes prediction_instant"):
        official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, published_at=NOW - timedelta(seconds=1))
    record = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, published_at=NOW)
    assert record is not None and record["published_at"] == record["prediction_instant"]  # equal clocks: a live cycle
    later_record = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c2", source_version="7", prediction_instant=NOW, published_at=NOW + timedelta(days=1))
    assert later_record is not None
    bad = {**record, "id": "bad", "cycle_id": "c3", "published_at": (NOW - timedelta(seconds=1)).isoformat()}
    with pytest.raises(ValueError, match="CHECK \\(published_at >= prediction_instant\\)"):
        database.insert_valuation_predictions([record, bad])  # the whole statement is refused, as in PostgreSQL: nothing stored
    assert database._valuation_predictions == [] and database.latest_valuation_prediction("B3", "PETR4", source=official.SOURCE_OFFICIAL) is None
    assert database.insert_valuation_predictions([record, later_record]) == 2
    naive = {**record, "id": "naive", "cycle_id": "c4", "published_at": (NOW - timedelta(seconds=1)).replace(tzinfo=None).isoformat()}
    with pytest.raises(ValueError):  # a naive instant is UTC, as everywhere in the double
        database.insert_valuation_predictions([naive])
    assert len(database._valuation_predictions) == 2


def test_readers_tie_break_on_published_at_so_a_re_run_is_the_latest_record_for_every_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    # S4: after a re-run (same prediction_instant, later published_at) the memory readers kept the ORIGINAL (max / strict >) while
    # the selection served the RE-RUN, and the SQL ORDER BY prediction_instant DESC had no tie-break. Every reader now orders by
    # (prediction_instant, published_at, insertion/created_at); the SQL text embeds the tie-break.
    from contextlib import contextmanager
    database = _database()
    cycles = _three_markets(database)
    live = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert live is not None
    row = _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)
    rerun = _rerun_universe(database, "NASDAQ", [row], rerun_of=cycles["NASDAQ"], prediction_instant=live["prediction_instant"], at=_wall())
    assert official.current_generation(database)["cycles"]["NASDAQ"] == rerun  # type: ignore[index]  # the selection serves the re-run...
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["cycle_id"] == rerun  # type: ignore[index]  # ...and so does every reader
    assert [record["cycle_id"] for record in database.list_valuation_predictions("NASDAQ", "AAPL")] == [rerun, cycles["NASDAQ"]]
    assert [record["cycle_id"] for record in official.prediction_records(database, "US", "AAPL")] == [rerun, cycles["NASDAQ"]]
    wege = _targeted_cycle(database, "WEGE3", _wall())
    wege_record = database.valuation_prediction_record(wege, "WEGE3")
    assert wege_record is not None
    wege_rerun = _rerun_targeted(database, "WEGE3", rerun_of=wege, prediction_instant=wege_record["prediction_instant"], at=_wall())
    assert database.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL)["WEGE3"]["cycle_id"] == wege_rerun
    # a re-run inserted BEFORE its original in the store (another host wrote it first) still wins: the key is the clocks, insertion last
    early = official.prediction_from_row(row, market="NYSE", scope="universe", cycle_id="rerun-first", source_version="7", prediction_instant=NOW, published_at=NOW + timedelta(days=1))
    original = official.prediction_from_row(row, market="NYSE", scope="universe", cycle_id="original-second", source_version="7", prediction_instant=NOW)
    assert early is not None and original is not None and database.insert_valuation_predictions([early, original]) == 2
    assert database.latest_valuation_prediction("NYSE", "AAPL", source=official.SOURCE_OFFICIAL)["cycle_id"] == "rerun-first"  # type: ignore[index]
    assert [record["cycle_id"] for record in database.list_valuation_predictions("NYSE", "AAPL")] == ["rerun-first", "original-second"]
    # the double's order on a full tie (both clocks equal) is the insertion order, as created_at orders it in PostgreSQL
    twin = {**original, "id": "twin", "cycle_id": "twin-cycle"}
    assert database.insert_valuation_predictions([twin]) == 1
    assert [record["cycle_id"] for record in database.list_valuation_predictions("NYSE", "AAPL")] == ["rerun-first", "twin-cycle", "original-second"]
    # the SQL readers embed the same tie-break (a recording connection: no database is reached)
    pg = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False, database_url="postgresql://configured"))
    queries: list[str] = []

    class Recording:
        def execute(self, query: str, params: Any = None) -> "Recording":
            queries.append(" ".join(query.split()))
            return self

        def fetchall(self) -> list[Any]:
            return []

        def fetchone(self) -> Any:
            return None

    @contextmanager
    def fake_connection() -> Any:
        yield Recording()

    monkeypatch.setattr(pg, "connection", fake_connection)
    assert pg.list_valuation_predictions("NASDAQ", "AAPL") == [] and pg.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL) == {}
    assert pg.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL) is None
    # NULLS LAST (rev 7): a legacy V1 row (NULL published_at) never sorts ahead of a V2 re-run tied on prediction_instant.
    assert len(queries) == 3 and Database._PREDICTION_ORDER == "prediction_instant DESC, published_at DESC NULLS LAST, created_at DESC"
    assert "ORDER BY prediction_instant DESC, published_at DESC NULLS LAST, created_at DESC LIMIT %s" in queries[0]
    assert "SELECT DISTINCT ON (symbol)" in queries[1] and "ORDER BY symbol, prediction_instant DESC, published_at DESC NULLS LAST, created_at DESC" in queries[1]
    assert "ORDER BY prediction_instant DESC, published_at DESC NULLS LAST, created_at DESC LIMIT 1" in queries[2]
    assert not any("ORDER BY prediction_instant DESC LIMIT" in query or "prediction_instant DESC\n" in query for query in queries)


def test_an_unrecordable_re_run_is_a_warning_once_per_cycle_and_info_after(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # S5: a re-run without inputs.prediction_instant (or dated after its own publication) is never recordable, and every activation
    # pass met it twice (recording at selection time, then validating): 2 WARNINGs per pass, forever. Once per cycle id, INFO after.
    monkeypatch.setattr(official, "_unrecordable_logged", set())
    database = _database()
    cycles = _three_markets(database)
    head = official.current_generation(database)
    caplog.set_level(logging.INFO, logger="app.valuation_official")

    def unrecordable(cycle_id: str) -> list[int]:
        return [record.levelno for record in caplog.records if "not recordable (B2)" in record.getMessage() and cycle_id in record.getMessage()]

    ko = [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)]
    nameless = _rerun_universe(database, "NYSE", ko, rerun_of=cycles["NYSE"], prediction_instant=None, at=_wall())
    # the hook's pass meets the cycle three times: record_snapshot records it (1), then the activation pass records it at selection time (2) and validates it (3)
    assert unrecordable(nameless) == [logging.WARNING, logging.INFO, logging.INFO]
    assert official.current_generation(database) == head and database.valuation_predictions_for_cycle(nameless) == {}
    caplog.clear()
    for _ in range(3):
        assert official.activate_generation_if_changed(database) is None
    assert official.bootstrap_official_selection(database)["generation"] == head
    assert unrecordable(nameless) == [logging.INFO] * 9 and not any(record.levelno >= logging.WARNING for record in caplog.records)  # 3 passes x 2 + the bootstrap's 3
    assert nameless in official._unrecordable_logged
    caplog.clear()
    forward = _rerun_universe(database, "NYSE", ko, rerun_of=cycles["NYSE"], prediction_instant=(_wall() + timedelta(days=1)).isoformat(), at=_wall())
    assert unrecordable(forward) == [logging.WARNING, logging.INFO, logging.INFO] and unrecordable(nameless) == []  # a different cycle id warns once; the old one is not met (not the latest)
    caplog.clear()
    assert official.activate_generation_if_changed(database) is None and unrecordable(forward) == [logging.INFO, logging.INFO]
    monkeypatch.setattr(official, "_unrecordable_logged", set())  # another process warns once more, then INFO
    caplog.clear()
    assert official.activate_generation_if_changed(database) is None and unrecordable(forward) == [logging.WARNING, logging.INFO]
    assert official.official_row(database, "NYSE", "KO")["official_cycle_id"] == cycles["NYSE"]  # type: ignore[index]  # NYSE stays on its live cycle throughout


def test_the_studies_loader_keeps_a_call_whose_published_at_is_malformed(caplog: pytest.LogCaptureFixture) -> None:
    # S8: load_prediction_calls parsed published_at inside the main try and dropped the WHOLE call on a malformed value — the
    # call's identity is the prediction, not its second clock: kept, published_at = None, one WARNING.
    from app.valuation_accuracy import load_prediction_calls
    database = _database()
    _three_markets(database)
    record = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert record is not None
    caplog.set_level(logging.WARNING, logger="app.valuation_accuracy")
    calls = load_prediction_calls([{**record, "published_at": "not-a-clock"}, {**record, "published_at": ""}, {**record, "published_at": None}, record,
                                   {**record, "prediction_instant": "not-a-clock"}])
    assert [call.published_at for call in calls] == [None, None, None, datetime.fromisoformat(record["published_at"])]  # the malformed PREDICTION instant is still dropped
    assert all(call.changed_at.isoformat() == record["prediction_instant"] and call.target_price == 250.0 and call.cycle_id == record["cycle_id"] for call in calls)
    warned = [message for message in caplog.messages if "malformed published_at" in message]
    assert len(warned) == 1 and "'not-a-clock'" in warned[0] and record["cycle_id"] in warned[0]


# --- rev 6 residuals (U1, U2): the held targeted cycle is read normalized; the double mirrors NOT NULL on published_at ----------


def test_a_held_targeted_cycle_under_a_legacy_key_still_governs_the_direct_admission(caplog: pytest.LogCaptureFixture) -> None:
    # U1: admit_targeted_cycle read the held cycle with current["targeted"].get(clean) — a head whose map carries a legacy key not
    # written clean ({'wege3': c2}, which Y4 tolerates on the automatic path) looked as if nothing were held: the recency rule (S2)
    # and the early return were bypassed, the replay of the older c1 was validated and admitted (TP80 → TP50) and re-admitting the
    # held cycle itself chained a redundant generation. The held cycle is now read from the map NORMALIZED, as it is served.
    database = _database()
    cycles = _three_markets(database)
    c1 = _targeted_cycle(database, "WEGE3", _wall())
    c2 = _targeted_cycle(database, "WEGE3", _wall(), 80.0)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": c2}
    database.insert_valuation_official_selection({**head, "generation_id": "legacy-head", "previous_generation_id": head["generation_id"],
                                                  "targeted": {"wege3": c2}, "activated_at": _wall().isoformat()})
    legacy = official.current_generation(database)
    assert legacy is not None and legacy["generation_id"] == "legacy-head"
    assert official.official_row(database, "B3", "WEGE3") is None  # X2: a legacy key is not served until a generation writes it clean (the pass, below)
    chain = [item["generation_id"] for item in database._valuation_official_selections]
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    snapshot = database.analysis_snapshot_by_id(c1)
    assert snapshot is not None and official.record_snapshot(database, snapshot) == {"recorded": 0, "generation": None}  # the hook's replay of c1...
    assert official.admit_targeted_cycle(database, symbol="wege3", cycle_id=c1) is None  # ...and the direct call: not newer than the held c2 (S2)
    assert official.admit_targeted_cycle(database, symbol="WEGE3", cycle_id=c2) is None  # the held cycle itself: the early return, no redundant generation
    assert [item["generation_id"] for item in database._valuation_official_selections] == chain and official.current_generation(database) == legacy
    not_newer = [record for record in caplog.records if "is not newer than the cycle the generation holds" in record.getMessage()]
    assert len(not_newer) == 2 and {record.levelno for record in not_newer} == {logging.INFO} and c1 in not_newer[0].getMessage() and c2 in not_newer[0].getMessage()
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)  # nothing validated, nothing warned
    # the direct path now agrees with the activation pass: the pass carries c2 under its clean key (Y4) and recovers nothing — never c1
    repaired = official.activate_generation_if_changed(database)
    assert repaired is not None and repaired["previous_generation_id"] == "legacy-head" and repaired["cycles"] == cycles
    assert repaired["targeted"] == {"WEGE3": c2} and repaired["receipt"]["targeted_recovered"] == {} and repaired["receipt"]["changed_markets"] == []
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 80.0 and official.activate_generation_if_changed(database) is None  # type: ignore[index]
    # a genuinely newer cycle is still admitted
    c3 = _targeted_cycle(database, "WEGE3", _wall(), 90.0)
    admitted = official.current_generation(database)
    assert admitted is not None and admitted["previous_generation_id"] == repaired["generation_id"] and admitted["targeted"] == {"WEGE3": c3}
    assert official.official_row(database, "B3", "WEGE3")["our_tp"] == 90.0  # type: ignore[index]


def test_a_record_without_its_publication_clock_is_refused_by_the_memory_double_as_by_not_null() -> None:
    # U2: the double stored a record without published_at, while the SQL writer raises KeyError on the missing key and PostgreSQL
    # refuses NULL (the column is NOT NULL, S9) — a test could pass on a record the table would never hold. ValueError, nothing stored.
    database = _database()
    row = _row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)
    record = official.prediction_from_row(row, market="B3", scope="universe", cycle_id="c", source_version="7", prediction_instant=NOW, published_at=NOW)
    assert record is not None
    null = {**record, "id": "null", "cycle_id": "c2", "published_at": None}
    absent = {key: value for key, value in {**record, "id": "absent", "cycle_id": "c3"}.items() if key != "published_at"}
    for nameless in (null, absent):
        with pytest.raises(ValueError, match="published_at NOT NULL"):
            database.insert_valuation_predictions([record, nameless])  # the whole statement is refused, as in PostgreSQL: nothing stored
        assert database._valuation_predictions == [] and database.latest_valuation_prediction("B3", "PETR4", source=official.SOURCE_OFFICIAL) is None
    assert database.insert_valuation_predictions([record]) == 1


# --- rev 7 (F393-11): the migration never backfills a legacy table; every reader honours the STORED schema — a V1 row stays V1 ---


def _legacy_v1_record(row: dict, *, market: str, scope: str, cycle_id: str, prediction_instant: datetime, source_version: str = "7",
                      source_manifest_sha256: str | None = "a" * 64) -> dict[str, Any]:
    """The rev-5 emitter (``VALUATION_PREDICTION_V1``) — the rows a legacy table holds: ONE clock (no ``published_at`` in the
    hashed core) and no ``rerun_of`` in the provenance; both joined the core in rev 6. Derived from today's emitter by removing
    exactly what rev 6 added and re-hashing as V1: the hash the rev-5 code (git f3ff907) computes for the same row."""
    record = official.prediction_from_row(row, market=market, scope=scope, cycle_id=cycle_id, source_version=source_version,
                                          prediction_instant=prediction_instant, source_manifest_sha256=source_manifest_sha256)
    assert record is not None
    core = copy.deepcopy({key: value for key, value in record.items() if key not in ("id", "schema", "row_sha256", "published_at")})
    core["decomposition"]["provenance"].pop("rerun_of")
    core = {"schema": official.LEGACY_PREDICTION_SCHEMA, **core}
    return {**core, "id": record["id"], "row_sha256": official.canonical_sha256(core)}


def _hash_of(record: dict[str, Any]) -> str:
    return official.canonical_sha256({key: value for key, value in record.items() if key not in ("id", "row_sha256")})


def test_a_legacy_v1_row_is_read_verified_and_served_as_v1_never_relabelled_v2(caplog: pytest.LogCaptureFixture) -> None:
    # F393-11 b (rev 7): the reader stamped schema = V2 on EVERY PostgreSQL row — a legacy rev-5 row (hashed without published_at)
    # came back as VALUATION_PREDICTION_V2 under its V1 hash, an identity nobody could recompute. The STORED schema decides now:
    # a V1 row is rebuilt as V1, its hash verified as V1, served without official_published_at (never derived) — never relabelled.
    database = _database()
    cycles = _three_markets(database)
    v2 = database.valuation_prediction_record(cycles["NASDAQ"], "AAPL")
    assert v2 is not None and v2["schema"] == official.PREDICTION_SCHEMA == "VALUATION_PREDICTION_V2"
    row = _row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)
    v1 = _legacy_v1_record(row, market="NASDAQ", scope="universe", cycle_id=cycles["NASDAQ"], prediction_instant=NOW + timedelta(minutes=1))
    assert v1["schema"] == official.LEGACY_PREDICTION_SCHEMA == "VALUATION_PREDICTION_V1" and "published_at" not in v1
    assert "rerun_of" not in v1["decomposition"]["provenance"] and v1["row_sha256"] != v2["row_sha256"] and _hash_of(v1) == v1["row_sha256"]
    # the PostgreSQL-shaped row — published_at NULL: the column added by explicit order, never backfilled — is rebuilt as V1 in every
    # session zone, its hash recomputed and verified as V1, no published_at key, the decomposition as stored
    for zone in (ZoneInfo("UTC"), ZoneInfo("America/Sao_Paulo"), ZoneInfo("Asia/Tokyo")):
        rebuilt = database._prediction_record(_pg_row(v1, zone))
        assert rebuilt == v1 and rebuilt["schema"] == official.LEGACY_PREDICTION_SCHEMA and "published_at" not in rebuilt and _hash_of(rebuilt) == v1["row_sha256"]
    # the memory double behaves the same: the legacy row REPLACES the cycle's V2 record (a table recorded by rev 5) and every reader keeps it V1
    database._valuation_predictions[:] = [record for record in database._valuation_predictions if record["cycle_id"] != cycles["NASDAQ"]] + [v1]
    database.drop_official_cycle_cache()
    for served in (database.valuation_prediction_record(cycles["NASDAQ"], "AAPL"), database.valuation_predictions_for_cycle(cycles["NASDAQ"])["AAPL"],
                   database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL), database.list_valuation_predictions("NASDAQ", "AAPL")[0],
                   official.prediction_records(database, "US", "AAPL")[0]):
        assert served == v1 and served["schema"] == official.LEGACY_PREDICTION_SCHEMA and "published_at" not in served
    assert database.valuation_prediction_record(cycles["NASDAQ"], "AAPL") == v1  # the cache hit, too
    # served: the stamp carries official_published_at = None (never derived from the prediction's instant) and the V1 hash
    stamped = official.official_row(database, "US", "AAPL")
    assert stamped is not None and stamped["our_tp"] == 250.0 and stamped["official_published_at"] is None and stamped["official_row_sha256"] == v1["row_sha256"]
    assert stamped["prediction_instant"] == v1["prediction_instant"] and official.item_stamp(stamped)["official_published_at"] is None
    assert official.official_rows(database, "NASDAQ")["AAPL"]["official_published_at"] is None
    # the cycle stays selectable — its identity is verifiable: the validator, the activation pass and an explicit order accept it
    snapshot = database.analysis_snapshot_by_id(cycles["NASDAQ"])
    assert snapshot is not None
    validation = official.cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(cycles["NASDAQ"]))
    assert validation["valid"] is True and validation["unrecorded_count"] == 0
    assert official.selectable_cycles(database)["NASDAQ"]["valid"] is True and official.activate_generation_if_changed(database) is None
    head = official.current_generation(database)
    assert head is not None and head["cycles"]["NASDAQ"] == cycles["NASDAQ"]
    rolled = official.select_generation(database, cycles=head["cycles"], now=later(1), activated_by="mesa", reason="a legacy cycle is selectable")
    assert rolled["cycles"]["NASDAQ"] == cycles["NASDAQ"] and official.official_row(database, "US", "AAPL")["official_row_sha256"] == v1["row_sha256"]  # type: ignore[index]
    # the studies' arm hands the V1 record as it is; the loader's call has no second clock
    from app.valuation_accuracy import load_prediction_calls
    arm = official.official_prediction_snapshot(database, "NASDAQ")
    assert arm is not None and arm["outputs"]["results"]["AAPL"] == v1
    call = load_prediction_calls([v1])[0]
    assert call.published_at is None and call.changed_at.isoformat() == v1["prediction_instant"] and call.row_sha256 == v1["row_sha256"]
    # the auditor's counterproof, at the reader: the V1 row with published_at FILLED IN PLACE (what the rev 6 migration did) is NOT
    # served as V2 under the V1 hash — a PostgreSQL row has no schema column, and the provenance without rerun_of tells the rev-5
    # emitter: rebuilt as V1, verified as V1, the filled clock IGNORED (official_published_at None), a WARNING once, INFO after
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    filled = {key: value for key, value in v1.items() if key != "schema"}
    filled["published_at"] = v1["prediction_instant"]
    for zone in (ZoneInfo("UTC"), ZoneInfo("Asia/Tokyo")):
        rebuilt = database._prediction_record(_pg_row(filled, zone))
        assert rebuilt == v1 and rebuilt["schema"] == official.LEGACY_PREDICTION_SCHEMA and "published_at" not in rebuilt
    filled_logs = [record for record in caplog.records if "filled in place" in record.getMessage()]
    assert [record.levelno for record in filled_logs] == [logging.WARNING, logging.INFO] and v1["id"] in filled_logs[0].getMessage()
    assert not any("is not served" in record.getMessage() for record in caplog.records)
    database._valuation_predictions[:] = [record for record in database._valuation_predictions if record["cycle_id"] != cycles["NASDAQ"]] + [{**filled, "schema": official.LEGACY_PREDICTION_SCHEMA}]
    database.drop_official_cycle_cache()
    assert database.valuation_prediction_record(cycles["NASDAQ"], "AAPL") == v1 and official.official_row(database, "US", "AAPL")["official_published_at"] is None  # type: ignore[index]


def test_a_row_that_claims_v2_without_its_clock_is_an_integrity_failure_not_served(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    # F393-11 b (rev 7): a row whose hash covers published_at (V2) but whose stored clock is NULL/absent cannot be verified under
    # any schema: not served (every reader), WARNING once per record per process, and its cycle is not selectable — the generation
    # in force carries the market, nothing is served in the row's place.
    database = _database()
    cycles = _three_markets(database)
    v2 = database.valuation_prediction_record(cycles["NYSE"], "KO")
    assert v2 is not None
    snapshot = database.analysis_snapshot_by_id(cycles["NYSE"])
    assert snapshot is not None
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    nulled = {**v2, "published_at": None}
    absent = {key: value for key, value in v2.items() if key != "published_at"}
    for broken in (nulled, absent):  # the memory double: the stored dict claims V2 without its clock
        database._valuation_predictions[:] = [record for record in database._valuation_predictions if record["cycle_id"] != cycles["NYSE"]] + [broken]
        database.drop_official_cycle_cache()
        assert database.valuation_prediction_record(cycles["NYSE"], "KO") is None and database.valuation_predictions_for_cycle(cycles["NYSE"]) == {}
        assert cycles["NYSE"] not in database._cycle_records_cache  # an empty answer is never pinned (D1)
        assert database.latest_valuation_prediction("NYSE", "KO", source=official.SOURCE_OFFICIAL) is None and database.list_valuation_predictions("NYSE", "KO") == []
        assert database.latest_targeted_predictions("NYSE", source=official.SOURCE_OFFICIAL) == {}
        assert official.official_row(database, "NYSE", "KO") is None and official.official_rows(database, "NYSE") == {}
        validation = official.cycle_validation(snapshot, recorded=database.valuation_predictions_for_cycle(cycles["NYSE"]))
        assert validation["valid"] is False and validation["unrecorded_count"] == 1
        assert official.selectable_cycles(database)["NYSE"]["valid"] is False  # the re-record is idempotent on the unique key: nothing replaces the row
        assert official.activate_generation_if_changed(database) is None and official.current_generation(database)["cycles"]["NYSE"] == cycles["NYSE"]  # type: ignore[index]
    refused = [record for record in caplog.records if "is not served" in record.getMessage()]
    assert refused and refused[0].levelno == logging.WARNING and {record.levelno for record in refused[1:]} == {logging.INFO}  # once per record per process
    assert "claims schema VALUATION_PREDICTION_V2 but carries no published_at" in refused[0].getMessage() and v2["id"] in refused[0].getMessage()
    # the PostgreSQL-shaped row (no schema column): published_at NULL under a hash computed WITH the clock does not verify as V1
    caplog.clear()
    assert database._prediction_record(_pg_row(nulled, ZoneInfo("UTC"))) is None
    assert any("does not verify as VALUATION_PREDICTION_V1" in record.getMessage() for record in caplog.records)
    # a legacy row whose content was altered does not verify either — a tampered number is never served under a hash it does not match
    row = _row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)
    v1 = _legacy_v1_record(row, market="NYSE", scope="universe", cycle_id=cycles["NYSE"], prediction_instant=NOW + timedelta(minutes=2))
    tampered = {**v1, "tp": 700.0}
    assert database._prediction_record(_pg_row(tampered, ZoneInfo("UTC"))) is None and database._prediction_record(_pg_row(v1, ZoneInfo("UTC"))) == v1
    database._valuation_predictions[:] = [record for record in database._valuation_predictions if record["cycle_id"] != cycles["NYSE"]] + [tampered]
    database.drop_official_cycle_cache()
    assert database.valuation_prediction_record(cycles["NYSE"], "KO") is None and official.official_row(database, "NYSE", "KO") is None
    # an unknown schema is refused too; a V2 row is served exactly as before (no hash is recomputed for it)
    assert official.stored_prediction({**v2, "schema": "VALUATION_PREDICTION_V9"}) is None
    assert official.stored_prediction(v2) == v2 and official.stored_prediction({key: value for key, value in v2.items() if key != "schema"}) == v2
    assert official.stored_prediction({**v2, "tp": 1.0}) == {**v2, "tp": 1.0}
    # the SQL readers drop the refused row AFTER the query (a fake connection hands the rows PostgreSQL would): the cycle read keeps
    # the verifiable rows only, the history is shorter, the single-row readers answer None — nothing is served in the row's place
    from contextlib import contextmanager
    pg = Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False, database_url="postgresql://configured"))
    rows = [_pg_row(nulled, ZoneInfo("UTC")), _pg_row(v1, ZoneInfo("Asia/Tokyo"))]

    class Handing:
        def execute(self, query: str, params: Any = None) -> "Handing":
            return self

        def fetchall(self) -> list[Any]:
            return rows

        def fetchone(self) -> Any:
            return rows[0]

    @contextmanager
    def fake_connection() -> Any:
        yield Handing()

    monkeypatch.setattr(pg, "connection", fake_connection)
    assert pg.latest_valuation_prediction("NYSE", "KO", source=official.SOURCE_OFFICIAL) is None and pg.valuation_prediction_record(cycles["NYSE"], "KO") is None
    assert pg.valuation_predictions_for_cycle(cycles["NYSE"]) == {"KO": v1} and pg.list_valuation_predictions("NYSE", "KO") == [v1]
    assert pg.latest_targeted_predictions("NYSE", source=official.SOURCE_OFFICIAL) == {"KO": v1}
    assert pg.valuation_prediction_record(cycles["NYSE"], "KO") == v1  # the cycle read pinned the verifiable rows only: a cache hit serves the V1 row


def test_a_mixed_table_keeps_each_schema_and_hash_per_row(caplog: pytest.LogCaptureFixture) -> None:
    # F393-11 b (rev 7): V1 (rev 5) and V2 (rev 6) rows for the same market and symbol coexist in one table (the column added by
    # explicit order, never backfilled): every reader hands each row under ITS schema and ITS hash, memory and PostgreSQL alike.
    database = _database()
    old_at = NOW - timedelta(days=1)
    row = _row("KO", tp=68.0, buy_in=58.0, price=64.0, internal_tp=67.0)
    legacy_cycle = _publish_universe(database, "NYSE", [row], old_at)
    v1 = _legacy_v1_record(row, market="NYSE", scope="universe", cycle_id=legacy_cycle, prediction_instant=old_at)
    database._valuation_predictions[:] = [v1]  # the cycle was recorded by rev 5
    cycles = _three_markets(database)  # rev 6 records for the same market and symbol, in the same table
    v2 = database.valuation_prediction_record(cycles["NYSE"], "KO")
    assert v2 is not None and v2["schema"] == official.PREDICTION_SCHEMA and v2["published_at"] == v2["prediction_instant"]
    caplog.set_level(logging.INFO, logger="app.valuation_official")
    caplog.clear()
    history = database.list_valuation_predictions("NYSE", "KO")
    assert [(record["cycle_id"], record["schema"]) for record in history] == [(cycles["NYSE"], official.PREDICTION_SCHEMA), (legacy_cycle, official.LEGACY_PREDICTION_SCHEMA)]
    assert history == [v2, v1] and "published_at" not in history[1] and all(_hash_of(record) == record["row_sha256"] for record in history)
    assert official.prediction_records(database, "NYSE", "KO") == history and official.prediction_records(database, "US", "KO", source=official.SOURCE_OFFICIAL) == history
    assert database.latest_valuation_prediction("NYSE", "KO", source=official.SOURCE_OFFICIAL) == v2  # the newest by the clocks is the V2
    for record in (v1, v2):  # the PostgreSQL-shaped rows of the same table, in any session zone
        for zone in (ZoneInfo("UTC"), ZoneInfo("America/Sao_Paulo")):
            rebuilt = database._prediction_record(_pg_row(record, zone))
            assert rebuilt == record and rebuilt["schema"] == record["schema"] and _hash_of(rebuilt) == record["row_sha256"]
    # the generation serves the V2 cycle with its clock; a rollback onto the legacy cycle serves the V1 row without one, under the V1 hash
    head = official.current_generation(database)
    assert head is not None and head["cycles"]["NYSE"] == cycles["NYSE"]
    served = official.official_row(database, "NYSE", "KO")
    assert served is not None and served["official_published_at"] == v2["published_at"] and served["official_row_sha256"] == v2["row_sha256"] and served["our_tp"] == 70.0
    # a legacy TARGETED row (admitted before any order): the targeted reader and the targeted served path keep it V1 too
    wege = _targeted_cycle(database, "WEGE3", _wall())
    wege_v1 = _legacy_v1_record(_row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0), market="B3", scope="targeted", cycle_id=wege,
                                prediction_instant=official._utc(database.analysis_snapshot_by_id(wege)["published_at"]), source_manifest_sha256=None)  # type: ignore[index]
    database._valuation_predictions[:] = [record for record in database._valuation_predictions if record["cycle_id"] != wege] + [wege_v1]
    database.drop_official_cycle_cache()
    assert database.latest_targeted_predictions("B3", source=official.SOURCE_OFFICIAL) == {"WEGE3": wege_v1} and wege_v1["schema"] == official.LEGACY_PREDICTION_SCHEMA
    targeted = official.official_row(database, "B3", "WEGE3")
    assert targeted is not None and targeted["official_scope"] == "targeted" and targeted["official_published_at"] is None and targeted["official_row_sha256"] == wege_v1["row_sha256"]
    assert official.official_prediction_snapshot(database, "B3")["outputs"]["results"]["WEGE3"] == wege_v1  # type: ignore[index]
    # a rollback onto the legacy universe cycle, keeping the legacy targeted one (both validated by the same validator: verifiable identities)
    head = official.current_generation(database)
    assert head is not None and head["targeted"] == {"WEGE3": wege}
    rolled = official.select_generation(database, cycles={**head["cycles"], "NYSE": legacy_cycle}, targeted={"WEGE3": wege}, now=later(1), activated_by="mesa",
                                        reason="rollback onto a legacy cycle")
    assert rolled["cycles"]["NYSE"] == legacy_cycle and rolled["session_dates"]["NYSE"] == v1["session_date"] and rolled["targeted"] == {"WEGE3": wege}
    served = official.official_row(database, "NYSE", "KO")
    assert served is not None and served["official_published_at"] is None and served["official_row_sha256"] == v1["row_sha256"] and served["our_tp"] == 68.0
    assert served["prediction_instant"] == v1["prediction_instant"] and official.official_stamp(database, "NYSE")["official_cycle_id"] == legacy_cycle
    assert official.official_row(database, "B3", "WEGE3")["official_published_at"] is None  # type: ignore[index]
    # the studies read each row with its own clock
    from app.valuation_accuracy import load_prediction_calls
    calls = load_prediction_calls(history)
    assert calls[0].published_at == datetime.fromisoformat(v2["published_at"]) and calls[0].row_sha256 == v2["row_sha256"]
    assert calls[1].published_at is None and calls[1].row_sha256 == v1["row_sha256"] and calls[1].changed_at == old_at
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)  # nothing refused, nothing warned
