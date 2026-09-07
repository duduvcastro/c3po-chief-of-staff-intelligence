"""Passo 0 of the official target price (Valuation Engine V3.2 rev 7, §7-bis): every producer cycle becomes immutable
prediction records; the official TP is a SELECTION by generation (one complete, validated cycle per market); switching
and rolling back are new selections; consumers resolve through the generation and never compute a TP of their own."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import valuation_official as official
from app.config import Settings
from app.database import Database

NOW = datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc)


def _database() -> Database:
    return Database(Settings(brapi_token="brapi-test", eodhd_api_token="eodhd-test", auth_cookie_secure=False))


def _row(symbol: str, *, tp: float, buy_in: float, price: float, internal_tp: float, **extra: object) -> dict:
    return {"symbol": symbol, "our_tp": tp, "buy_in": buy_in, "price": price, "internal_tp": internal_tp, "public_consensus_tp": tp * 1.1,
            "analyst_count": 12, "consensus_weight_percent": 25.0, "methods": {"dcf": tp * 1.01, "multiples": tp * 0.99},
            "calibration_factor": 1.02, "risk_score": 40.0, "valuation_confidence": 70.0, "method_dispersion_percent": 3.0,
            "signal_quality": "validated", **extra}


def _publish_universe(database: Database, market: str, rows: list[dict], at: datetime, version: int = 7) -> str:
    return database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1",
                                           {"methodology_version": version, "market": market},
                                           {"rows": rows, "universe_size": len(rows) + 1}, at)


def _three_markets(database: Database) -> dict[str, str]:
    return {
        "B3": _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0),
                                                 _row("VALE3", tp=70.0, buy_in=60.0, price=62.0, internal_tp=69.0)], NOW),
        "NASDAQ": _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], NOW + timedelta(minutes=1)),
        "NYSE": _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], NOW + timedelta(minutes=2)),
    }


def test_a_universe_cycle_becomes_prediction_records_and_three_markets_activate_one_generation() -> None:
    database = _database()
    b3 = _publish_universe(database, "B3", [_row("PETR4", tp=40.0, buy_in=32.0, price=36.0, internal_tp=39.0)], NOW)
    assert official.current_generation(database) is None  # two markets missing: an incomplete generation is never selectable
    record = database.latest_valuation_prediction("B3", "PETR4", source=official.SOURCE_OFFICIAL)
    assert record and record["tp"] == 40.0 and record["cycle_id"] == b3 and record["scope"] == "universe" and record["currency"] == "BRL"
    assert official.official_row(database, "B3", "PETR4") is None  # no generation yet: no official TP, even though a record exists
    nasdaq = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=250.0, buy_in=200.0, price=220.0, internal_tp=245.0)], NOW + timedelta(minutes=1))
    assert official.current_generation(database) is None
    nyse = _publish_universe(database, "NYSE", [_row("KO", tp=70.0, buy_in=60.0, price=65.0, internal_tp=68.0)], NOW + timedelta(minutes=2))
    generation = official.current_generation(database)
    assert generation and generation["validated_complete"] and generation["cycles"] == {"B3": b3, "NASDAQ": nasdaq, "NYSE": nyse}
    assert generation["previous_generation_id"] is None and generation["source"] == official.SOURCE_OFFICIAL and generation["source_version"] == "7"
    assert generation["session_dates"] == {"B3": "2026-09-07", "NASDAQ": "2026-09-07", "NYSE": "2026-09-07"}
    row = official.official_row(database, "US", "AAPL")
    assert row and row["our_tp"] == 250.0 and row["buy_in"] == 200.0 and row["tp_source"] == official.SOURCE_OFFICIAL
    assert row["generation_id"] == generation["generation_id"] and row["official_cycle_id"] == nasdaq and row["official_market"] == "NASDAQ"
    assert official.official_row(database, "US", "MSFT") is None  # outside the universe: no TP — never computed by a consumer
    assert set(official.official_rows(database, "US")) == {"AAPL", "KO"} and set(official.official_rows(database, "B3")) == {"PETR4"}
    # records are hashed over their content and unique per (source, version, market, symbol, cycle): re-inserting is a no-op
    record = database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)
    assert record is not None
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    assert record["row_sha256"] == official.canonical_sha256(core)
    assert database.insert_valuation_predictions([record]) == 0


def test_a_new_cycle_of_one_market_is_a_new_generation_and_the_previous_one_stays_readable() -> None:
    database = _database()
    cycles = _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    later = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], NOW + timedelta(minutes=10))
    second = official.current_generation(database)
    assert second is not None and second["generation_id"] != first["generation_id"]
    assert second["cycles"] == {**cycles, "NASDAQ": later} and second["previous_generation_id"] == first["generation_id"]
    assert second["receipt"]["changed_markets"] == ["NASDAQ"]
    assert official.official_row(database, "NASDAQ", "AAPL")["our_tp"] == 260.0  # type: ignore[index]
    assert official.official_row(database, "NASDAQ", "AAPL", generation=first)["our_tp"] == 250.0  # type: ignore[index]  # history is readable
    assert database.valuation_official_selection(first["generation_id"]) == first
    # a targeted (on-demand) valuation is recorded but never activates a generation
    database.save_analysis_snapshot("security_valuation", "WEGE3", "mv-1", {"methodology_version": 7},
                                    {"row": _row("WEGE3", tp=50.0, buy_in=42.0, price=45.0, internal_tp=49.0)}, NOW + timedelta(minutes=11))
    assert official.current_generation(database) == second
    targeted = official.official_row(database, "B3", "WEGE3")
    assert targeted and targeted["official_scope"] == "targeted" and targeted["our_tp"] == 50.0 and targeted["generation_id"] == second["generation_id"]
    assert official.official_row(database, "B3", "wege3.sa") == targeted


def test_a_cycle_with_an_unusable_row_never_becomes_the_official_selection() -> None:
    database = _database()
    _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    broken = _publish_universe(database, "NASDAQ", [_row("AAPL", tp=270.0, buy_in=215.0, price=230.0, internal_tp=265.0),
                                                     {**_row("NVDA", tp=900.0, buy_in=700.0, price=800.0, internal_tp=880.0), "buy_in": None}],
                               NOW + timedelta(minutes=20))
    assert official.current_generation(database) == first  # consistency wins: the whole cycle is not selectable, the previous generation holds
    assert database.latest_valuation_prediction("NASDAQ", "NVDA", source=official.SOURCE_OFFICIAL) is None  # an unusable row is not a prediction
    assert database.latest_valuation_prediction("NASDAQ", "AAPL", source=official.SOURCE_OFFICIAL)["cycle_id"] == broken  # type: ignore[index]
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]  # still the selected generation
    validation = official.selectable_cycles(database)["NASDAQ"]
    assert validation["valid"] is False and validation["invalid_count"] == 1 and validation["invalid_rows"] == ["NVDA"]


def test_rollback_and_switches_are_new_selections_over_existing_complete_cycles() -> None:
    database = _database()
    cycles = _three_markets(database)
    first = official.current_generation(database)
    assert first is not None
    _publish_universe(database, "NASDAQ", [_row("AAPL", tp=260.0, buy_in=210.0, price=230.0, internal_tp=255.0)], NOW + timedelta(minutes=10))
    second = official.current_generation(database)
    assert second is not None
    rolled = official.select_generation(database, cycles=first["cycles"], now=NOW + timedelta(minutes=30), activated_by="mesa", reason="rollback drill")
    current = official.current_generation(database)
    assert current is not None
    assert current == rolled and current["cycles"] == cycles and current["previous_generation_id"] == second["generation_id"]
    assert official.official_row(database, "US", "AAPL")["our_tp"] == 250.0  # type: ignore[index]
    with pytest.raises(ValueError):
        official.select_generation(database, cycles={**cycles, "NASDAQ": "not-a-cycle"}, now=NOW, activated_by="mesa", reason="bad")
    assert official.current_generation(database) == rolled  # a refused selection changes nothing


def test_the_migration_defines_two_append_only_tables() -> None:
    sql = (Path(__file__).resolve().parents[2] / "db" / "048_valuation_official_tp.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS valuation_predictions" in sql and "CREATE TABLE IF NOT EXISTS valuation_official_selection" in sql
    assert "UNIQUE (source, source_version, market, symbol, cycle_id)" in sql and sql.count("BEFORE UPDATE OR DELETE") == 2
    assert "REFERENCES analysis_snapshots(id)" in sql and "previous_generation_id UUID REFERENCES valuation_official_selection(generation_id)" in sql
