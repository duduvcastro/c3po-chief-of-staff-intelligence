"""Ben Kenobi Records on a real PostgreSQL: migration 054, the served capture at the first start after the deploy, and what
every later start re-runs (db/009, 018 and 019 rewrite records at each start — never a served one).

Runs only with C3PO_MIGRATED_TEST_DSN: the CI's disposable database on a local socket where every migration was applied twice
(.github/workflows/backend-postgres.yml). Each test is ONE transaction on one connection, rolled back at the end — the
Database's own commits are absorbed — so nothing is left behind. No production credentials are read.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from app import valuation_official as official
from app.config import Settings
from app.database import LEGACY_TP_SOURCE_PRODUCER, Database
from app.valuation_official_engine import SOURCE_BLEND, SOURCE_INTERNAL

DB_DIR = Path(__file__).resolve().parents[2] / "db"
NIGHT = datetime(2026, 10, 19, 23, 0, tzinfo=timezone.utc)
EDGE_TP = 36.12500000000001  # one ulp-scale step above a cent boundary: a float8 → numeric cast (15 digits) would round it to 36.125


class _OneTransaction:
    """The test's connection as every Database call sees it: ``commit`` is absorbed, everything else is the connection's."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def commit(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


@pytest.fixture
def database() -> Iterator[Database]:
    dsn = os.environ.get("C3PO_MIGRATED_TEST_DSN")
    if not dsn:
        pytest.skip("disposable migrated PostgreSQL not configured (C3PO_MIGRATED_TEST_DSN)")
    info = conninfo_to_dict(dsn)
    assert str(info.get("host", "")).startswith("/tmp/"), "local test socket required"
    connection = psycopg.connect(dsn)
    try:
        store = Database(Settings(database_url=dsn, migrations_dir=DB_DIR))
        shared = _OneTransaction(connection)

        @contextmanager
        def one_connection() -> Iterator[Any]:
            yield shared

        store.connection = one_connection  # type: ignore[method-assign]
        yield store
    finally:
        connection.rollback()
        connection.close()


def _row(symbol: str, *, tp: float, internal_tp: float, price: float, currency: str = "BRL") -> dict[str, Any]:
    return {"symbol": symbol, "name": f"{symbol} Corp", "currency": currency, "price": price, "our_tp": tp, "buy_in": tp * 0.8,
            "internal_tp": internal_tp, "internal_buy_in": internal_tp * 0.8, "public_consensus_tp": tp * 1.2, "analyst_count": 6,
            "consensus_weight_percent": 25.0, "valuation_confidence": 75.0, "internal_score": 70.0, "internal_status": "full_match",
            "internal_expected_total_return_percent": 15.0}


def _publish(store: Database, methodology_id: str, market: str, rows: list[dict[str, Any]], at: datetime) -> str:
    return store.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", methodology_id, {"market": market, "methodology_version": 9},
                                        {"rows": rows, "universe_size": len(rows)}, at)


def _records(store: Database, where: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with store.connection() as connection:
        return connection.execute(f"SELECT * FROM valuation_change_records WHERE {where} ORDER BY id", params).fetchall()


def test_migration_054_adds_the_two_columns_the_foreign_key_and_the_partial_unique_index(database: Database) -> None:
    with database.connection() as connection:
        columns = dict(connection.execute(
            """
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'valuation_change_records' AND column_name IN ('tp_source', 'generation_id')
            """
        ).fetchall())
        nullable = connection.execute(
            """
            SELECT bool_and(is_nullable = 'YES') AND bool_and(column_default IS NULL) FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = 'valuation_change_records' AND column_name IN ('tp_source', 'generation_id')
            """
        ).fetchone()
        index = connection.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'valuation_change_generation_symbol'").fetchone()
        target = connection.execute(
            """
            SELECT constraint_row.confrelid::regclass::text
            FROM pg_constraint AS constraint_row
            JOIN pg_attribute AS attribute ON attribute.attrelid = constraint_row.conrelid AND attribute.attnum = ANY (constraint_row.conkey)
            WHERE constraint_row.conrelid = 'valuation_change_records'::regclass AND constraint_row.contype = 'f' AND attribute.attname = 'generation_id'
            """
        ).fetchone()

    assert columns == {"tp_source": "text", "generation_id": "uuid"}
    assert nullable == (True,)  # no NOT NULL, no DEFAULT: the legacy rows stay NULL
    assert index is not None and "CREATE UNIQUE INDEX" in index[0] and "(generation_id, market, symbol)" in index[0]
    assert "WHERE (generation_id IS NOT NULL)" in index[0]
    assert target == ("valuation_official_selection",)


def test_the_first_start_records_the_served_tp_and_no_start_ever_rewrites_a_record(database: Database, monkeypatch) -> None:
    store = database
    methodology_id = store.ensure_methodology_version("c3po_equity_valuation", 9, {}, "test")
    legacy_id = str(uuid4())
    with store.connection() as connection:  # a record of the producer-row capture, as the table holds them before the deploy
        connection.execute(
            """
            INSERT INTO valuation_change_records
                (id, snapshot_id, market, symbol, company_name, changed_at, trigger_type, trigger_title, trigger_summary, source_name,
                 currency, old_tp, new_tp, new_buy_in, new_consensus_tp, price, new_confidence, methodology_name, methodology_version, metadata)
            VALUES (%s, NULL, 'B3', 'PETR4', 'Petrobras', %s, 'market_data', 'legacy', 'C3PO TP passou de R$ 39,00 para R$ 40,00.',
                    'Brapi + EODHD', 'BRL', 39, 40, 32, 48, 33, 75, 'C3PO Valuation Model', 9, %s::jsonb)
            """,
            (legacy_id, NIGHT - timedelta(days=5), json.dumps({"analysis_type": "valuation_universe", "changed_fields": ["c3po_tp"]})),
        )
    legacy_before = _records(store, "id = %s", (legacy_id,))

    # before the deploy: the generations are written by the code that did not capture them (the switch of 20/10 included)
    store._capture_served_after_selection = lambda: None  # type: ignore[method-assign]
    cycles = {
        "NASDAQ": _publish(store, methodology_id, "NASDAQ", [_row("AAPL", tp=250.0, internal_tp=230.0, price=220.0, currency="USD")], NIGHT),
        "NYSE": _publish(store, methodology_id, "NYSE", [_row("KO", tp=70.0, internal_tp=66.0, price=64.0, currency="USD")], NIGHT),
        "B3": _publish(store, methodology_id, "B3", [_row("PETR4", tp=40.0, internal_tp=EDGE_TP, price=33.0)], NIGHT),
    }
    report = official.before_after_report(store, cycles=cycles, targeted={})
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_AUTHORIZED", True)
    monkeypatch.setattr(official, "OFFICIAL_TP_REPLACEMENT_RECEIPT_SHA256", report["report_sha256"])
    switched = official.select_generation(store, cycles=cycles, now=datetime.now(timezone.utc), activated_by="mesa", reason="P1 switch",
                                          source=SOURCE_INTERNAL, source_version="9", before_after_sha256=report["report_sha256"])
    del store._capture_served_after_selection  # the deployed code
    assert store.list_valuation_changes(limit=50)[0] == 1

    store.initialize()  # the first start after the deploy: migrations (054 included) re-run, then the served boundary is captured

    total, records = store.list_valuation_changes(limit=50)
    served = {(record["market"], record["symbol"]): record for record in records if not record["legacy"]}
    assert total == 4 and set(served) == {("B3", "PETR4"), ("NASDAQ", "AAPL"), ("NYSE", "KO")}
    for (market, symbol), record in served.items():
        row = official.official_row(store, market, symbol)
        assert row is not None and float(record["new_tp"]) == row["our_tp"] and float(record["new_buy_in"]) == row["buy_in"]
        assert (record["tp_source"], record["generation_id"], record["tp_source_label"]) == (SOURCE_INTERNAL, switched["generation_id"], SOURCE_INTERNAL)
    petr = served[("B3", "PETR4")]
    assert float(petr["new_tp"]) == EDGE_TP and float(petr["old_tp"]) == 40.0 and petr["trigger_type"] == "methodology"
    assert petr["metadata"]["previous_record_id"] == legacy_id and petr["metadata"]["previous_tp_source_label"] == LEGACY_TP_SOURCE_PRODUCER
    legacy = next(record for record in records if record["legacy"])
    assert (legacy["id"], legacy["tp_source"], legacy["generation_id"], legacy["tp_source_label"]) == (legacy_id, None, None, LEGACY_TP_SOURCE_PRODUCER)
    assert _records(store, "id = %s", (legacy_id,)) == legacy_before  # never rewritten
    assert store.capture_served_valuation_changes() == 0  # the stored NUMERIC reads back exactly what is compared: no re-record

    # the next night: only what the served TP changed is appended; a second record of the same (generation, symbol) never lands
    _publish(store, methodology_id, "B3", [_row("PETR4", tp=41.0, internal_tp=37.0, price=33.5)], datetime.now(timezone.utc))
    head = official.current_generation(store)
    assert head is not None and head["source"] == SOURCE_INTERNAL
    night = [record for record in store.list_valuation_changes(limit=50)[1] if record["generation_id"] == head["generation_id"]]
    assert [(record["symbol"], float(record["old_tp"]), float(record["new_tp"]), record["trigger_type"]) for record in night] == [
        ("PETR4", EDGE_TP, 37.0, "market_data")]
    store._store_valuation_changes([{**night[0], "id": str(uuid4()), "new_tp": 1.0}])  # ON CONFLICT (generation_id, market, symbol)
    assert store.list_valuation_changes(limit=50)[0] == 5

    # every later start re-runs every migration — 009, 018 and 019 rewrite records — and captures nothing new
    served_before = _records(store, "generation_id IS NOT NULL")
    store.initialize()
    assert _records(store, "generation_id IS NOT NULL") == served_before
    assert _records(store, "id = %s", (legacy_id,)) == legacy_before
    assert store.list_valuation_changes(limit=50)[0] == 5

    # and a rollback to the blend is one record per served symbol, back on the blend
    rolled = official.select_generation(store, cycles={**cycles, "B3": head["cycles"]["B3"]}, now=datetime.now(timezone.utc),
                                        activated_by="mesa", reason="rollback", source=SOURCE_BLEND)
    back = [record for record in store.list_valuation_changes(limit=50)[1] if record["generation_id"] == rolled["generation_id"]]
    assert sorted(record["symbol"] for record in back) == ["AAPL", "KO", "PETR4"]
    assert all(record["tp_source"] == SOURCE_BLEND and record["trigger_type"] == "methodology" for record in back)
