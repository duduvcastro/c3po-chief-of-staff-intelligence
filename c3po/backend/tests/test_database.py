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
    Since the ledger records the SERVED rows of the official selection, the market is the served market (the generation's).
    """
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    methodology_id = database.ensure_methodology_version("us-screener", 1, {}, "test")
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)

    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "JPM")):
        database.save_analysis_snapshot(
            "valuation_universe", f"{market}_UNIVERSE", methodology_id,
            {"methodology_version": 1, "market": market},
            {"rows": [{"symbol": symbol, "our_tp": 250.0, "buy_in": 200.0, "internal_tp": 240.0, "price": 220.0, "company_name": f"{symbol} Inc"}]},
            now,
        )
    database.save_analysis_snapshot(
        "valuation_universe", "B3_UNIVERSE", methodology_id,
        {"source": "brapi", "methodology_version": "V1", "cvm_first": True},
        {"rows": [{"symbol": "PETR4", "our_tp": 40.0, "buy_in": 32.0, "internal_tp": 38.0, "price": 36.0, "company_name": "Petrobras"}]},
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


def _weekly_sentiment(source: str, symbol: str, published_at: datetime, bullish: float) -> dict:
    return {
        "source_code": source, "external_id": f"{source}-sentiment-{symbol}-{published_at:%G-W%V}", "market": "US",
        "symbol": symbol, "company_name": symbol, "event_type": "News Sentiment", "title": "t", "summary": "",
        "published_at": published_at, "published_time_precision": "collected", "official_url": "https://example.com/a",
        "valuation_relevant": False,
        "raw_metadata": {"source": source, "bullish_percent": bullish, "bearish_percent": 100.0 - bullish, "articles_last_week": 9},
    }


def test_the_sentiment_readers_take_the_latest_row_of_massive_or_finnhub(tmp_path) -> None:
    """Owner 03/11/2026: Finnhub is cut and Massive writes the weekly row. Both readers take the latest published_at of
    either source (a tie goes to Massive), so the Finnhub history stays readable; the live reader ignores a row first
    published more than 8 days ago (a name with no row this week reads nothing: the One Pager's adjustment is 0), the
    causal reader reads at its cutoff whatever the age and names the row's source."""
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    now = datetime.now(timezone.utc)
    database.save_ir_events([
        _weekly_sentiment("finnhub", "AMZN", now - timedelta(days=3), 40.0),
        _weekly_sentiment("massive", "AMZN", now - timedelta(hours=1), 80.0),  # the switch: Massive's row of the week wins
        _weekly_sentiment("massive", "MSFT", now - timedelta(days=2), 30.0),
        _weekly_sentiment("finnhub", "MSFT", now - timedelta(days=1), 55.0),  # the latest wins, whatever the source
        _weekly_sentiment("finnhub", "META", now - timedelta(days=9), 90.0),  # older than 8 days: not read live
        _weekly_sentiment("finnhub", "AVGO", now - timedelta(days=4), 45.0),
        _weekly_sentiment("massive", "AVGO", now - timedelta(days=4), 65.0),  # same instant: the current source
        {**_weekly_sentiment("massive", "TTWO", now, 99.0), "event_type": "News Mention"},  # not a sentiment row
    ])

    latest = database.latest_news_sentiment(["amzn", "MSFT", "META", "AVGO", "TTWO"], "US")

    assert {symbol: row["bullish_percent"] for symbol, row in latest.items()} == {"AMZN": 80.0, "MSFT": 55.0, "AVGO": 65.0}
    assert latest["AMZN"]["source"] == "massive" and latest["MSFT"]["source"] == "finnhub"
    assert database.latest_news_sentiment(["AMZN"], "B3") == {}
    before_switch = database.news_sentiment_at(["AMZN", "META"], now - timedelta(days=2))
    assert before_switch["AMZN"]["source_code"] == "finnhub" and before_switch["AMZN"]["raw_metadata"]["bullish_percent"] == 40.0
    assert before_switch["META"]["source_code"] == "finnhub"  # the causal reader keeps the history: the decisor ages it
    after_switch = database.news_sentiment_at(["AMZN", "AVGO"], now)
    assert after_switch["AMZN"]["source_code"] == "massive" and after_switch["AMZN"]["external_id"].startswith("massive-sentiment-AMZN-")
    assert after_switch["AVGO"]["source_code"] == "massive"


def test_the_sentiment_readers_query_both_sources_with_the_latest_first() -> None:
    """The PostgreSQL shape of both readers: either source, the latest published_at first and Massive on a tie; the live
    reader with its 8-day floor, the causal one with the row's source_code (CI runs them on a real PostgreSQL too)."""
    captured: list[tuple[str, tuple]] = []

    class Rows:
        def fetchall(self):
            return []

    class Connection:
        def execute(self, query, params=()):
            captured.append((" ".join(query.split()), params))
            return Rows()

    database = Database(Settings(database_url="postgresql://configured"))

    @contextmanager
    def connection():
        yield Connection()

    database.connection = connection  # type: ignore[method-assign]
    cutoff = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)
    before = datetime.now(timezone.utc)
    assert database.latest_news_sentiment(["aapl"], "US") == {}
    assert database.news_sentiment_at(["aapl"], cutoff) == {}
    (live, live_params), (causal, causal_params) = captured
    for query in (live, causal):
        assert "source_code = ANY(%s) AND event_type = 'News Sentiment'" in query
        assert query.endswith("ORDER BY symbol, published_at DESC, (source_code = 'massive') DESC")
    assert live_params[:3] == ("US", ["massive", "finnhub"], ["AAPL"])
    assert timedelta(days=8) - timedelta(seconds=5) <= before - live_params[3] <= timedelta(days=8) + timedelta(seconds=5)
    assert "published_at >= %s" in live and "source_code" not in live.split("FROM")[0]
    assert causal_params == ("US", ["massive", "finnhub"], ["AAPL"], cutoff)
    assert "published_at <= %s" in causal and causal.split("FROM")[0].rstrip().endswith("source_code")


def test_ir_source_health_surfaces_massive_runs(tmp_path) -> None:
    """'massive' writes the weekly news sentiment since the owner cut Finnhub (03/11/2026): its runs reach the Investor
    Relations page's source health, next to the 'finnhub' runs already recorded."""
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    run_id = database.begin_ingestion_run("massive", "Massive", "market_sentiment", {})
    database.finish_ingestion_run(run_id, "succeeded", 40, 3)

    assert database.ir_source_health()["massive"]["last_status"] == "succeeded"


def test_migration_056_admits_massive_and_keeps_finnhub_without_rewriting_020() -> None:
    """The ir_events source check gains 'massive' in a NEW migration (020 is never rewritten): idempotent at every start
    (replaced only while it does not name 'massive' yet), 'finnhub' still admitted for the rows already stored, and the same
    five codes the application reads (IR_SOURCE_CODES). CI applies the whole chain twice to an empty PostgreSQL."""
    import re
    from pathlib import Path

    from app.database import IR_SOURCE_CODES

    db_dir = Path(__file__).resolve().parents[2] / "db"
    numbered = sorted(path.name for path in db_dir.glob("*.sql") if path.name[:1].isdigit())
    assert "056_ir_events_massive_source.sql" in numbered
    assert numbered.index("056_ir_events_massive_source.sql") > numbered.index("020_ir_events_finnhub_source.sql")
    sql = (db_dir / "056_ir_events_massive_source.sql").read_text(encoding="utf-8")
    checks = re.findall(r"CHECK \(source_code IN \(([^)]*)\)\)", sql)
    assert len(checks) == 1 and set(re.findall(r"'([a-z]+)'", checks[0])) == set(IR_SOURCE_CODES)
    assert "pg_get_constraintdef(oid) NOT LIKE '%massive%'" in sql and "IF NOT EXISTS" in sql
    statements = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert not re.search(r"\b(DELETE|UPDATE|TRUNCATE)\b", statements, re.I)  # the stored rows are never touched
    legacy = (db_dir / "020_ir_events_finnhub_source.sql").read_text(encoding="utf-8")
    assert "CHECK (source_code IN ('cvm', 'sec', 'ri', 'finnhub'))" in legacy and "massive" not in legacy


def test_the_finnhub_insider_rows_the_eodhd_path_checks_are_one_name_s_finnhub_rows_of_the_window(tmp_path) -> None:
    """What the EODHD Form 4 path reads to drop what Finnhub already stored (owner 03/11/2026): one name's "Insider
    Transaction" rows Finnhub wrote ('finnhub-insider-…'), whose transaction is on or after the window's first day."""
    from datetime import date

    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    today = date.today()

    def row(external_id: str, symbol: str, days_ago: int, event_type: str = "Insider Transaction") -> dict:
        day = today - timedelta(days=days_ago)
        return {"source_code": "sec", "external_id": external_id, "market": "US", "symbol": symbol, "company_name": symbol,
                "event_type": event_type, "title": "t", "published_at": datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
                "reference_date": day, "official_url": "https://www.sec.gov", "raw_metadata": {"source": external_id.split("-")[0],
                                                                                              "transaction_date": day.isoformat()}}

    database.save_ir_events([
        row("finnhub-insider-AAPL-a", "AAPL", 10), row("finnhub-insider-AAPL-b", "AAPL", 90),
        row("finnhub-insider-AAPL-old", "AAPL", 91), row("eodhd-insider-AAPL-c", "AAPL", 10),
        row("finnhub-insider-MSFT-d", "MSFT", 10), row("finnhub-insider-AAPL-e", "AAPL", 10, event_type="Material Fact"),
    ])

    read = database.finnhub_insider_transactions("aapl", since=today - timedelta(days=90))

    assert sorted(item["transaction_date"] for item in read) == sorted([(today - timedelta(days=d)).isoformat() for d in (10, 90)])
    assert {item["source"] for item in read} == {"finnhub"}
    assert database.finnhub_insider_transactions("", since=today) == []


def test_the_finnhub_insider_rows_query_is_one_name_s_finnhub_rows_of_the_window() -> None:
    from datetime import date

    captured: list[tuple[str, tuple]] = []

    class Rows:
        def fetchall(self):
            return [({"insider_name": "COOK TIMOTHY D"},), ('{"insider_name": "WILLIAMS JEFFREY E"}',)]

    class Connection:
        def execute(self, query, params=()):
            captured.append((" ".join(query.split()), params))
            return Rows()

    database = Database(Settings(database_url="postgresql://configured"))

    @contextmanager
    def connection():
        yield Connection()

    database.connection = connection  # type: ignore[method-assign]
    since = date(2026, 8, 5)
    assert database.finnhub_insider_transactions("aapl", since=since) == [{"insider_name": "COOK TIMOTHY D"}, {"insider_name": "WILLIAMS JEFFREY E"}]
    ((query, params),) = captured
    assert "source_code = 'sec' AND market = %s AND symbol = %s AND event_type = 'Insider Transaction'" in query
    assert "external_id LIKE %s AND reference_date >= %s" in query
    assert params == ("US", "AAPL", "finnhub-insider-%", since)
