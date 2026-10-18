"""Decisor V1 readers on a disposable, LOCAL PostgreSQL: the queries the memory double cannot prove (the JSONB extraction of
the consensus term structure, the decoding of the sentiment rows, the causal poll read, the 051 filings and the 053 marks
with their insert-clock margin).

C3PO_VALUATION_DECISOR_TEST_DSN (or C3PO_PROVIDER_HEALTH_TEST_DSN) is optional — skipped without it; it must be a local
socket under /tmp. No production credential is read and no schema is initialized: connection-local TEMP tables with the
columns the readers use (their names resolve first through pg_temp, as ``to_regclass`` does)."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import uuid4

import pytest

from app import valuation_asfiled as asfiled
from app import valuation_earnings_calendar as calendar_module
from app.config import Settings
from app.database import Database

UTC = timezone.utc
D = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)

_TABLES = (
    """CREATE TEMP TABLE data_sources (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE, name text, source_type text,
       updated_at timestamptz DEFAULT now())""",
    """CREATE TEMP TABLE ingestion_runs (id uuid PRIMARY KEY, source_id uuid, status text, started_at timestamptz, completed_at timestamptz,
       metadata jsonb, records_read integer, records_written integer, error_summary text)""",
    """CREATE TEMP TABLE analysis_snapshots (id uuid PRIMARY KEY, analysis_type text, entity_key text, methodology_version_id uuid, inputs jsonb,
       outputs jsonb, published_at timestamptz, supersedes_id uuid)""",
    """CREATE TEMP TABLE ir_events (id uuid PRIMARY KEY, source_code text, external_id text, market text, symbol text, event_type text,
       published_at timestamptz, raw_metadata jsonb)""",
    """CREATE TEMP TABLE statement_filings (id uuid PRIMARY KEY, market text, issuer_key text, source text, doc_id text, document_version integer,
       form text, items text, symbols text[], period_of_report date, filed_date date, accepted_at timestamptz, accepted_source text,
       json_accepted_raw text, header_sha256 text, first_seen_at timestamptz)""",
    """CREATE TEMP TABLE valuation_tp_staleness (id uuid PRIMARY KEY, market text, symbol text, issuer_key text, doc_id text, form text,
       items text, accepted_at timestamptz, period_of_report date, state text, reason text, official_cycle_id text,
       prediction_instant timestamptz, fundamentals_as_of date, expected_period_end date, covers_period boolean, queued_for_cut_at timestamptz,
       recorded_at timestamptz, created_at timestamptz)""",
)


@pytest.fixture
def pg() -> Iterator[tuple[Database, Any]]:
    dsn = os.environ.get("C3PO_VALUATION_DECISOR_TEST_DSN") or os.environ.get("C3PO_PROVIDER_HEALTH_TEST_DSN")
    if not dsn:
        pytest.skip("disposable local PostgreSQL not configured")
    import psycopg

    info = psycopg.conninfo.conninfo_to_dict(dsn)
    assert str(info.get("host", "")).startswith("/tmp/"), "local test socket required"
    database = Database(Settings(database_url="", eodhd_api_token="test", brapi_token="test", auth_cookie_secure=False))
    with psycopg.connect(dsn, client_encoding="utf8") as connection:
        for statement in _TABLES:
            connection.execute(statement)
        connection.commit()
        database.database_url = dsn

        @contextmanager
        def local_connection() -> Iterator[Any]:
            yield connection

        database.connection = local_connection  # type: ignore[method-assign]
        yield database, connection


def test_the_poll_reader_is_causal_by_completion_and_counts_only_progress(pg: tuple[Database, Any]) -> None:
    database, connection = pg
    runs = []
    for status, records, started, completed in (("succeeded", 30, D - timedelta(hours=2), D - timedelta(hours=1)),
                                                ("succeeded", 0, D - timedelta(minutes=40), D - timedelta(minutes=30)),
                                                ("partial", 30, D - timedelta(minutes=20), D - timedelta(minutes=10)),
                                                ("succeeded", 30, D - timedelta(minutes=5), D + timedelta(minutes=1))):
        run_id = database.begin_ingestion_run("sec_asfiled", "SEC EDGAR as-filed statements", "regulatory_disclosure", {"scheduled_for": "night-1"})
        database.finish_ingestion_run(run_id, status, records, 0)
        connection.execute("UPDATE ingestion_runs SET started_at = %s, completed_at = %s WHERE id = %s", (started, completed, run_id))
        runs.append(run_id)
    connection.commit()
    found = database.ingestion_run_completed_at_or_before("sec_asfiled", D - timedelta(seconds=60), min_records_read=1)
    assert found is not None and found["id"] == runs[0] and found["records_read"] == 30 and found["completed_at"] == D - timedelta(hours=1)
    assert database.ingestion_run_completed_at_or_before("sec_asfiled", D - timedelta(seconds=60))["id"] == runs[1]  # type: ignore[index]
    assert database.ingestion_run_completed_at_or_before("sec_asfiled", D - timedelta(hours=3)) is None
    assert database.count_ingestion_runs("sec_asfiled", "succeeded", scheduled_for="night-1") == 3
    assert database.count_ingestion_runs("sec_asfiled", "partial", scheduled_for="night-2") == 0


def _snapshot(connection: Any, analysis_type: str, entity_key: str, outputs: Any, published: datetime) -> str:
    snapshot_id = str(uuid4())
    connection.execute("INSERT INTO analysis_snapshots (id, analysis_type, entity_key, inputs, outputs, published_at) VALUES (%s, %s, %s, '{}'::jsonb, "
                       "%s::jsonb, %s)", (snapshot_id, analysis_type, entity_key, json.dumps(outputs), published))
    return snapshot_id


def test_the_consensus_reader_extracts_only_the_term_structure_of_the_names_asked(pg: tuple[Database, Any]) -> None:
    database, connection = pg
    packet = {"fy1_estimate": {"fiscal_year_end": "2027-09-30", "eps_avg": 6.0}, "forward_estimates": [{"fiscal_year_end": "2027-09-30", "eps_avg": 6.0}],
              "ratios_annual": [{"pe": 30}] * 10}
    old = _snapshot(connection, "valuation_v2_data", "NASDAQ_V2_DATA", {"packets": {"AAPL": packet, "MSFT": packet, "BAD": "not an object"}},
                    D - timedelta(days=31))
    _snapshot(connection, "valuation_v2_data", "NASDAQ_V2_DATA", {"packets": {"AAPL": {**packet, "fy1_estimate": {"eps_avg": 1.0}}}}, D + timedelta(minutes=1))
    malformed = _snapshot(connection, "valuation_v2_data", "NYSE_V2_DATA", {"packets": []}, D - timedelta(days=1))  # packets not an object
    connection.commit()
    read = database.v2_forward_eps_at_or_before("NASDAQ", ["aapl", "BAD", "NONE"], D)
    assert read is not None and read["snapshot_id"] == old and read["published_at"] == D - timedelta(days=31)
    assert read["packets"] == {"AAPL": {"fy1_estimate": packet["fy1_estimate"], "forward_estimates": packet["forward_estimates"]}}
    assert database.v2_forward_eps_at_or_before("NYSE", ["KO"], D) == {"snapshot_id": malformed, "published_at": D - timedelta(days=1), "packets": {}}
    assert database.v2_forward_eps_at_or_before("NASDAQ", ["AAPL"], D - timedelta(days=40)) is None


def test_the_calendar_readers_read_published_clocks_only(pg: tuple[Database, Any]) -> None:
    database, connection = pg
    outputs = {"schema": calendar_module.SCHEMA, "request": {"from": "2026-10-07", "to": "2026-11-13"}, "events": [], "rows": 0}
    first = _snapshot(connection, calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY, outputs, D - timedelta(hours=40))
    second = _snapshot(connection, calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY, outputs, D - timedelta(hours=10))
    _snapshot(connection, calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY, outputs, D - timedelta(seconds=30))
    connection.commit()
    read = calendar_module.calendars_at(database, D, recent_hours=36, margin_seconds=60)
    assert [item["snapshot_id"] for item in read["recent"]] == [second] and read["latest"]["snapshot_id"] == second
    assert calendar_module.calendars_at(database, D - timedelta(hours=11), recent_hours=36, margin_seconds=60)["latest"]["snapshot_id"] == first
    assert database.latest_analysis_snapshot_published_at(calendar_module.ANALYSIS_TYPE, calendar_module.ENTITY_KEY) == D - timedelta(seconds=30)


def test_the_sentiment_reader_decodes_the_row_read_at_the_clock(pg: tuple[Database, Any]) -> None:
    database, connection = pg
    for symbol, published, bearish in (("AAPL", D - timedelta(days=9), 20.0), ("AAPL", D - timedelta(days=2), 70.0), ("AAPL", D + timedelta(hours=1), 5.0),
                                       ("KO", D + timedelta(hours=1), 90.0)):
        connection.execute("INSERT INTO ir_events (id, source_code, external_id, market, symbol, event_type, published_at, raw_metadata) VALUES "
                           "(%s, 'finnhub', %s, 'US', %s, 'News Sentiment', %s, %s::jsonb)",
                           (str(uuid4()), f"finnhub-sentiment-{symbol}-{published:%G-W%V}", symbol, published,
                            json.dumps({"bearish_percent": bearish, "bullish_percent": 100 - bearish, "articles_last_week": 9})))
    connection.commit()
    read = database.news_sentiment_at(["aapl", "ko"], D)
    assert set(read) == {"AAPL"} and read["AAPL"]["raw_metadata"]["bearish_percent"] == 70.0 and read["AAPL"]["published_at"] == D - timedelta(days=2)
    assert read["AAPL"]["external_id"].startswith("finnhub-sentiment-AAPL-")


def test_the_051_and_053_readers_apply_the_insert_margin(pg: tuple[Database, Any]) -> None:
    database, connection = pg
    for doc_id, form, items, accepted, seen in (("f-1", "8-K", "2.02,9.01", datetime(2026, 7, 15, 20, 30, tzinfo=UTC), datetime(2026, 7, 15, 21, tzinfo=UTC)),
                                                ("f-2", "10-Q/A", "", datetime(2026, 7, 20, 20, 30, tzinfo=UTC), datetime(2026, 7, 20, 21, tzinfo=UTC)),
                                                ("f-3", "10-Q", "", datetime(2026, 8, 1, 20, 30, tzinfo=UTC), D - timedelta(seconds=30))):
        connection.execute("INSERT INTO statement_filings (id, market, issuer_key, source, doc_id, document_version, form, items, symbols, period_of_report, "
                           "filed_date, accepted_at, accepted_source, first_seen_at) VALUES (%s, 'US', '0000999201', 'sec_edgar', %s, 1, %s, %s, %s, %s, "
                           "%s, %s, 'sec_header', %s)",
                           (str(uuid4()), doc_id, form, items, ["AAPL"], date(2026, 6, 30), accepted.date(), accepted, seen))
    mark = {"market": "NASDAQ", "symbol": "AAPL", "issuer_key": "0000999201", "doc_id": "f-1", "form": "8-K", "items": "2.02", "accepted_at": D - timedelta(hours=9),
            "state": "stale", "reason": "tp_predates_acceptance", "recorded_at": D - timedelta(hours=8)}
    for created in (D - timedelta(hours=8), D - timedelta(seconds=30)):
        connection.execute("INSERT INTO valuation_tp_staleness (id, market, symbol, issuer_key, doc_id, form, items, accepted_at, state, reason, recorded_at, "
                           "created_at) VALUES (%(id)s, %(market)s, %(symbol)s, %(issuer_key)s, %(doc_id)s, %(form)s, %(items)s, %(accepted_at)s, %(state)s, "
                           "%(reason)s, %(recorded_at)s, %(created_at)s)", {**mark, "id": str(uuid4()), "doc_id": f"{mark['doc_id']}-{created:%H%M%S}",
                                                                           "created_at": created})
    connection.commit()
    filings = calendar_module.filings_known_at(database, D, lookback_days=400, margin_seconds=60)
    assert filings["status"] == "ok" and [item["doc_id"] for item in filings["by_symbol"]["AAPL"]] == ["f-1"]
    assert filings["by_symbol"]["AAPL"][0]["period_of_report"] == "2026-06-30"
    staleness = asfiled.us_staleness_at(database, D, margin_seconds=60)
    assert staleness["status"] == "ok" and staleness["marks_known"] == 1 and len(staleness["pending"]["AAPL"]) == 1
    assert asfiled.us_staleness_at(database, D, margin_seconds=0)["marks_known"] == 2
