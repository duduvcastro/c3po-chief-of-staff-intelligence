"""The weekly news sentiment on a real PostgreSQL after the owner cut Finnhub (03/11/2026): migration 056 admits the
'massive' source next to 'finnhub' (whose rows stay), and the readers take the latest row of either.

Runs only with C3PO_MIGRATED_TEST_DSN: the CI's disposable database on a local socket where every migration was applied
twice (.github/workflows/backend-postgres.yml). Each test is ONE transaction on one connection, rolled back at the end —
the Database's own commits are absorbed — so nothing is left behind. No production credentials are read.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config import Settings
from app.database import IR_SOURCE_CODES, Database

DB_DIR = Path(__file__).resolve().parents[2] / "db"


class _OneTransaction:
    """The test's connection as every Database call sees it: ``commit`` is absorbed, everything else is the connection's."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def commit(self) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


@pytest.fixture
def migrated() -> Iterator[tuple[Database, psycopg.Connection]]:
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
        yield store, connection
    finally:
        connection.rollback()
        connection.close()


def _sentiment(source: str, symbol: str, published_at: datetime, bullish: float) -> dict[str, Any]:
    return {
        "source_code": source, "external_id": f"{source}-sentiment-{symbol}-{published_at:%G-W%V}-{uuid4().hex[:8]}",
        "company_id": None, "market": "US", "symbol": symbol, "company_name": symbol, "regulator_id": None,
        "event_type": "News Sentiment", "form": None, "title": "t", "summary": "", "published_at": published_at,
        "published_time_precision": "collected", "reference_date": published_at.date(), "official_url": "https://example.com/a",
        "document_url": None, "materiality": "low", "valuation_relevant": False, "valuation_status": "informational",
        "raw_metadata": {"source": source, "bullish_percent": bullish, "bearish_percent": 100.0 - bullish, "articles_last_week": 9},
        "collected_at": published_at,
    }


def test_the_source_check_admits_massive_and_finnhub_and_nothing_else(migrated: tuple[Database, psycopg.Connection]) -> None:
    _store, connection = migrated
    definition = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'ir_events'::regclass AND conname = 'ir_events_source_code_check'"
    ).fetchone()
    assert definition is not None and all(f"'{code}'" in definition[0] for code in IR_SOURCE_CODES)
    connection.execute("SAVEPOINT refused_source")
    with pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(
            "INSERT INTO ir_events (id, source_code, external_id, market, company_name, event_type, title, published_at, official_url) "
            "VALUES (%s, 'fmp', 'fmp-x', 'US', 'X', 'News Sentiment', 't', now(), 'https://example.com')",
            (str(uuid4()),),
        )
    connection.execute("ROLLBACK TO SAVEPOINT refused_source")


def test_the_readers_take_the_latest_weekly_row_of_either_source(migrated: tuple[Database, psycopg.Connection]) -> None:
    store, _connection = migrated
    now = datetime.now(timezone.utc)
    symbol_a, symbol_b, symbol_c = (f"ZZ{uuid4().hex[:6].upper()}" for _ in range(3))  # names no real row carries
    assert store.save_ir_events([
        _sentiment("finnhub", symbol_a, now - timedelta(days=3), 40.0),
        _sentiment("massive", symbol_a, now - timedelta(hours=1), 80.0),
        _sentiment("massive", symbol_b, now - timedelta(days=2), 30.0),
        _sentiment("finnhub", symbol_b, now - timedelta(days=1), 55.0),
        _sentiment("finnhub", symbol_c, now - timedelta(days=9), 90.0),
    ]) == 5

    latest = store.latest_news_sentiment([symbol_a, symbol_b, symbol_c], "US")
    assert {symbol: row["bullish_percent"] for symbol, row in latest.items()} == {symbol_a: 80.0, symbol_b: 55.0}
    causal = store.news_sentiment_at([symbol_a, symbol_c], now - timedelta(days=2))
    assert causal[symbol_a]["source_code"] == "finnhub" and causal[symbol_a]["raw_metadata"]["bullish_percent"] == 40.0
    assert causal[symbol_c]["source_code"] == "finnhub"
    assert store.news_sentiment_at([symbol_a], now)[symbol_a]["source_code"] == "massive"


def test_a_massive_run_reaches_the_source_health(migrated: tuple[Database, psycopg.Connection]) -> None:
    store, _connection = migrated
    run_id = store.begin_ingestion_run("massive", "Massive", "market_sentiment", {"operation": "news_sentiment"})
    store.finish_ingestion_run(run_id, "succeeded", 40, 3)
    assert store.ir_source_health()["massive"]["last_status"] == "succeeded"
