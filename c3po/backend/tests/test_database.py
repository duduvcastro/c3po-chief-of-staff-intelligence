from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

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


def test_latest_analysis_snapshot_outputs_projects_only_requested_field(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("peer-quality", 1, {}, "test")
    now = datetime(2026, 8, 24, 4, 0, tzinfo=timezone.utc)
    report = {"pre_ab_ready": True, "gates": {"target_roe_non_null": True}}
    database.save_analysis_snapshot(
        "valuation_v2_peer_quality",
        "B3_V2_PEER_QUALITY",
        methodology_id,
        {},
        {"packets": {"large": [1, 2, 3]}, "pre_ab_report": report},
        now,
    )

    projected = database.latest_analysis_snapshot_outputs(
        "valuation_v2_peer_quality",
        ["B3_V2_PEER_QUALITY", "US_V2_PEER_QUALITY"],
        "pre_ab_report",
    )

    assert projected == {
        "B3_V2_PEER_QUALITY": {"published_at": now, "output": report}
    }


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


def test_ingestion_run_health_preserves_success_but_surfaces_latest_failure(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    code = "valuation-worker-v2-data"
    succeeded = database.begin_ingestion_run(code, "V2 data", "valuation_worker", {})
    database.finish_ingestion_run(succeeded, "succeeded", 0, 3)
    failed = database.begin_ingestion_run(code, "V2 data", "valuation_worker", {})
    database.finish_ingestion_run(failed, "failed", 0, 0, "provider unavailable")

    health = database.ingestion_run_health([code])[code]

    assert health["last_status"] == "failed"
    assert health["last_success_at"] is not None
    assert health["last_error"] == "provider unavailable"


def test_insider_transaction_activity_counts_buys_and_sells_from_both_shapes(tmp_path) -> None:
    """Root-caused 2026-08-20: CVM VLMO insider data was fully ingested and
    stored but never read back by anything -- governance_risk was a hardcoded
    neutral constant. This covers the two raw_metadata shapes insider events
    are stored with: CVM VLMO (movement string) and Finnhub/SEC Form 4
    (is_purchase/is_sale booleans).
    """
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    now = datetime.now(timezone.utc)
    database.save_ir_events([
        {
            "source_code": "cvm", "external_id": "cvm-1", "market": "B3", "symbol": "PRNR3",
            "company_name": "Priner", "event_type": "Insider Transaction", "title": "t", "summary": "",
            "published_at": now, "official_url": "https://dados.cvm.gov.br/", "valuation_relevant": False,
            "raw_metadata": {"source": "cvm_vlmo", "movement": "Compra à vista", "quantity": 1000, "price": 5.0},
        },
        {
            "source_code": "cvm", "external_id": "cvm-2", "market": "B3", "symbol": "PRNR3",
            "company_name": "Priner", "event_type": "Insider Transaction", "title": "t", "summary": "",
            "published_at": now, "official_url": "https://dados.cvm.gov.br/", "valuation_relevant": False,
            "raw_metadata": {"source": "cvm_vlmo", "movement": "Venda à vista", "quantity": 200, "price": 5.5},
        },
        {
            "source_code": "sec", "external_id": "finnhub-1", "market": "US", "symbol": "AMZN",
            "company_name": "Amazon", "event_type": "Insider Transaction", "title": "t", "summary": "",
            "published_at": now, "official_url": "https://sec.gov/", "valuation_relevant": False,
            "raw_metadata": {"source": "finnhub", "is_purchase": True, "is_sale": False, "share_change": 500},
        },
    ])

    b3_activity = database.insider_transaction_activity(["PRNR3"], "B3", now - timedelta(days=30))
    us_activity = database.insider_transaction_activity(["AMZN"], "US", now - timedelta(days=30))

    assert b3_activity["PRNR3"] == {"buy_count": 1, "sell_count": 1, "total_count": 2}
    assert us_activity["AMZN"] == {"buy_count": 1, "sell_count": 0, "total_count": 1}


def test_insider_transaction_activity_ignores_events_outside_lookback_window(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    old_event_at = datetime.now(timezone.utc) - timedelta(days=400)
    database.save_ir_events([{
        "source_code": "cvm", "external_id": "cvm-old", "market": "B3", "symbol": "PRNR3",
        "company_name": "Priner", "event_type": "Insider Transaction", "title": "t", "summary": "",
        "published_at": old_event_at, "official_url": "https://dados.cvm.gov.br/", "valuation_relevant": False,
        "raw_metadata": {"source": "cvm_vlmo", "movement": "Compra à vista", "quantity": 1000, "price": 5.0},
    }])

    activity = database.insider_transaction_activity(["PRNR3"], "B3", datetime.now(timezone.utc) - timedelta(days=180))

    assert activity == {}


def test_latest_news_sentiment_returns_the_most_recent_snapshot(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    stale_at = datetime.now(timezone.utc) - timedelta(days=7)
    fresh_at = datetime.now(timezone.utc)
    database.save_ir_events([
        {
            "source_code": "finnhub", "external_id": "finnhub-sentiment-AMZN-2026-W32", "market": "US", "symbol": "AMZN",
            "company_name": "Amazon", "event_type": "News Sentiment", "title": "t", "summary": "",
            "published_at": stale_at, "official_url": "https://finnhub.io/quote/AMZN", "valuation_relevant": False,
            "raw_metadata": {"source": "finnhub", "bullish_percent": 40.0, "bearish_percent": 60.0, "articles_last_week": 3},
        },
        {
            "source_code": "finnhub", "external_id": "finnhub-sentiment-AMZN-2026-W33", "market": "US", "symbol": "AMZN",
            "company_name": "Amazon", "event_type": "News Sentiment", "title": "t", "summary": "",
            "published_at": fresh_at, "official_url": "https://finnhub.io/quote/AMZN", "valuation_relevant": False,
            "raw_metadata": {"source": "finnhub", "bullish_percent": 72.0, "bearish_percent": 28.0, "articles_last_week": 9},
        },
    ])

    sentiment = database.latest_news_sentiment(["AMZN"], "US")

    assert sentiment["AMZN"]["bullish_percent"] == 72.0
    assert sentiment["AMZN"]["articles_last_week"] == 9
