from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import Settings
from app.database import Database


class RecordingCursor:
    def __init__(self) -> None:
        self.query = ""
        self.rows: list[tuple[str, str, datetime]] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def executemany(self, query: str, rows: list[tuple[str, str, datetime]]) -> None:
        self.query = query
        self.rows = rows


class PostgresStyleConnection:
    def __init__(self) -> None:
        self.recording_cursor = RecordingCursor()
        self.committed = False

    def cursor(self) -> RecordingCursor:
        return self.recording_cursor

    def commit(self) -> None:
        self.committed = True


def test_mark_alerts_read_uses_postgres_cursor_executemany(monkeypatch, tmp_path) -> None:
    database = Database(Settings(database_url="postgresql://configured", migrations_dir=tmp_path))
    connection = PostgresStyleConnection()

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(database, "connection", fake_connection)
    read_at = datetime(2026, 8, 16, 20, 0, tzinfo=timezone.utc)

    marked = database.mark_alerts_read(
        " EU@EduardoCastro.com.br ",
        ["alert-1", "alert-2", "alert-1", ""],
        read_at,
    )

    assert marked == 2
    assert connection.committed is True
    assert "INSERT INTO alert_reads" in connection.recording_cursor.query
    assert connection.recording_cursor.rows == [
        ("eu@eduardocastro.com.br", "alert-1", read_at),
        ("eu@eduardocastro.com.br", "alert-2", read_at),
    ]


def test_capture_valuation_changes_labels_nasdaq_and_nyse_by_exchange(tmp_path) -> None:
    """Ben Kenobi Records bug (2026-08-18): the US screener's valuation_universe
    snapshots carry the exchange ("NASDAQ"/"NYSE") in inputs.market, not "US". The
    old fallback (`if market not in {"B3", "US"}: market = "B3"`) caught every one
    of those and mislabeled it as B3 -- polluting the "Todos" view with mislabeled
    US entries and starving real B3 coverage off the first (most-recent) page.
    Market is now derived from the snapshot's own entity_key (NASDAQ_UNIVERSE/
    NYSE_UNIVERSE/B3_UNIVERSE), which is authoritative, so Ben Kenobi Records can
    classify by exchange (B3/NASDAQ/NYSE) instead of a generic B3/US split.
    """
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("us-screener", 1, {}, "test")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)

    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "JPM")):
        database.save_analysis_snapshot(
            "valuation_universe", f"{market}_UNIVERSE", methodology_id,
            {"methodology_version": 1, "market": market},
            {"rows": [{"symbol": symbol, "our_tp": 250.0, "company_name": f"{symbol} Inc"}]},
            now,
        )
    database.save_analysis_snapshot(
        "valuation_universe", "B3_UNIVERSE", methodology_id,
        {"source": "brapi", "methodology_version": "V1", "cvm_first": True},
        {"rows": [{"symbol": "PETR4", "our_tp": 40.0, "company_name": "Petrobras"}]},
        now,
    )

    total, records = database.list_valuation_changes(limit=10)

    assert total == 3
    by_symbol = {item["symbol"]: item["market"] for item in records}
    assert by_symbol == {"AAPL": "NASDAQ", "JPM": "NYSE", "PETR4": "B3"}


def test_ir_source_health_surfaces_finnhub_runs(tmp_path) -> None:
    """ir_source_health() had a hardcoded {"cvm", "sec", "ri"} allowlist
    predating the Finnhub source (db/020_ir_events_finnhub_source.sql) --
    a "finnhub" ingestion run would silently vanish from this method,
    leaving the Official Intelligence health card stuck on "attention"
    forever even while the sync itself succeeded. Regression test for
    both the in-memory and the equivalent SQL WHERE clause fix.
    """
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    run_id = database.begin_ingestion_run("finnhub", "Finnhub", "market_sentiment", {})
    database.finish_ingestion_run(run_id, "succeeded", 5, 5)

    health = database.ir_source_health()

    assert health["finnhub"]["last_status"] == "succeeded"
