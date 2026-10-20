"""SEC filing-header acceptance instants survive a late submissions-JSON write (Database.save_sec_filing_events).

The API process reads that a filing has no header instant, the IR worker then stores the header-sourced event, and the
API finally saves its corrected submissions-JSON fallback: the write itself must keep the header clock and header
fields. Each scenario runs on the in-memory store and, with C3PO_SEC_FILING_EVENTS_TEST_DSN, on a disposable local
PostgreSQL (connection-local temporary tables, never the schema; no production credentials are read).
"""
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from app.config import Settings
from app.database import SEC_FILING_EVENTS_UPSERT_SQL, Database

HEADER = "filing_header"
FALLBACK = "submissions_json_ny_corrected"
ACCESSION = "0000320193-26-000077"
ACCEPTED = datetime(2026, 7, 30, 20, 30, 28, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "postgres"])
def database(request):
    settings = Settings(database_url="")
    database = Database(settings)
    if request.param == "memory":
        yield database
        return
    dsn = os.environ.get("C3PO_SEC_FILING_EVENTS_TEST_DSN")
    if not dsn:
        pytest.skip("disposable local PostgreSQL not configured")
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    assert info.get("host", "").startswith("/tmp/"), "local test socket required"
    with psycopg.connect(dsn, client_encoding="utf8") as connection:
        # the columns, keys and defaults of migrations 002/004 the upsert touches (no foreign key to ir_companies)
        connection.execute("""CREATE TEMP TABLE ir_events (
            id uuid PRIMARY KEY, source_code text NOT NULL, external_id text NOT NULL, company_id uuid,
            market text NOT NULL, symbol text, company_name text NOT NULL, regulator_id text,
            event_type text NOT NULL, form text, title text NOT NULL, summary text NOT NULL DEFAULT '',
            published_at timestamptz NOT NULL, published_time_precision text NOT NULL DEFAULT 'datetime',
            reference_date date, official_url text NOT NULL, document_url text,
            materiality text NOT NULL DEFAULT 'medium', valuation_relevant boolean NOT NULL DEFAULT false,
            valuation_status text NOT NULL DEFAULT 'informational', reviewed_at timestamptz,
            review_note text NOT NULL DEFAULT '', raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            collected_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (source_code, external_id))""")
        connection.execute("""CREATE TEMP TABLE ir_security_map (
            market text NOT NULL, symbol text NOT NULL, company_id uuid NOT NULL, PRIMARY KEY (market, symbol))""")
        connection.execute("""CREATE TEMP TABLE ir_valuation_queue (
            event_id uuid NOT NULL REFERENCES ir_events(id) ON DELETE CASCADE, market text NOT NULL,
            symbol text NOT NULL, status text NOT NULL DEFAULT 'queued', attempts integer NOT NULL DEFAULT 0,
            queued_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
            last_error text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (event_id, market, symbol))""")
        connection.commit()
        database.database_url = dsn

        @contextmanager
        def local_connection():
            yield connection

        database.connection = local_connection  # type: ignore[method-assign]
        yield database


def _filing(published_at: datetime, source: str, **metadata) -> dict:
    """An SEC filing event as sync_sec builds it, with its acceptance clock read from ``source``."""
    raw_metadata = {"accession": ACCESSION, "acceptance_time_source": source, **metadata}
    if source == HEADER:
        raw_metadata["acceptance_datetime_header"] = "20260730163028"
    return {
        "source_code": "sec", "external_id": ACCESSION, "company_id": None, "market": "US", "symbol": "AAPL",
        "company_name": "Apple Inc.", "regulator_id": "320193", "event_type": "quarterly_report", "form": "10-Q",
        "title": "10-Q filing", "summary": "SEC form 10-Q", "published_at": published_at,
        "published_time_precision": "datetime", "reference_date": None,
        "official_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000077/",
        "document_url": None, "materiality": "high", "valuation_relevant": False, "valuation_status": "informational",
        "raw_metadata": raw_metadata, "collected_at": ACCEPTED + timedelta(minutes=5),
    }


def _stored(database: Database) -> dict:
    if not database.database_url:
        event = database._ir_events[("sec", ACCESSION)]
        return {"published_at": event["published_at"], "raw_metadata": event["raw_metadata"], "title": event["title"]}
    with database.connection() as connection:
        published_at, raw_metadata, title = connection.execute(
            "SELECT published_at, raw_metadata, title FROM ir_events WHERE source_code = 'sec' AND external_id = %s",
            (ACCESSION,),
        ).fetchone()
    return {"published_at": published_at, "raw_metadata": raw_metadata, "title": title}


@pytest.mark.parametrize("fallback_offset", [timedelta(0), timedelta(seconds=-3), timedelta(hours=4)],
                         ids=["equal-clocks", "divergent-seconds", "divergent-ny-offset"])
def test_a_fallback_read_before_the_header_was_stored_never_overwrites_it(database, fallback_offset):
    # 1) the API's sync reads: no header instant stored yet, so it prepares the submissions-JSON fallback
    assert database.stored_sec_acceptances([ACCESSION], acceptance_source=HEADER) == {}
    fallback = _filing(ACCEPTED + fallback_offset, FALLBACK, acceptance_datetime_json="2026-07-31T00:30:28.000Z",
                       fulltext_keywords=["guidance"])
    fallback["title"] = "10-Q filing (API)"
    # 2) meanwhile the IR worker stores the header-sourced event
    assert database.save_sec_filing_events([_filing(ACCEPTED, HEADER)], header_source=HEADER) == 1
    # 3) the API's save lands last
    assert database.save_sec_filing_events([fallback], header_source=HEADER) == 1

    stored = _stored(database)
    assert stored["published_at"] == ACCEPTED
    assert stored["raw_metadata"]["acceptance_time_source"] == HEADER
    assert stored["raw_metadata"]["acceptance_datetime_header"] == "20260730163028"
    # everything else of the late write is still written
    assert stored["raw_metadata"]["acceptance_datetime_json"] == "2026-07-31T00:30:28.000Z"
    assert stored["raw_metadata"]["fulltext_keywords"] == ["guidance"]
    assert stored["title"] == "10-Q filing (API)"
    assert database.stored_sec_acceptances([ACCESSION], acceptance_source=HEADER) == {ACCESSION: ACCEPTED}


def test_an_incoming_header_always_wins_over_a_stored_fallback_or_header(database):
    database.save_sec_filing_events([_filing(ACCEPTED + timedelta(hours=4), FALLBACK)], header_source=HEADER)
    assert _stored(database)["raw_metadata"]["acceptance_time_source"] == FALLBACK

    database.save_sec_filing_events([_filing(ACCEPTED, HEADER)], header_source=HEADER)
    stored = _stored(database)
    assert stored["published_at"] == ACCEPTED and stored["raw_metadata"]["acceptance_time_source"] == HEADER

    corrected = _filing(ACCEPTED + timedelta(seconds=1), HEADER)  # a later header reading replaces the earlier one
    corrected["raw_metadata"]["acceptance_datetime_header"] = "20260730163029"
    database.save_sec_filing_events([corrected], header_source=HEADER)
    stored = _stored(database)
    assert stored["published_at"] == ACCEPTED + timedelta(seconds=1)
    assert stored["raw_metadata"]["acceptance_datetime_header"] == "20260730163029"


def test_a_fallback_over_a_fallback_is_a_plain_upsert(database):
    database.save_sec_filing_events([_filing(ACCEPTED, FALLBACK)], header_source=HEADER)
    database.save_sec_filing_events([_filing(ACCEPTED + timedelta(seconds=2), FALLBACK)], header_source=HEADER)
    stored = _stored(database)
    assert stored["published_at"] == ACCEPTED + timedelta(seconds=2)
    assert stored["raw_metadata"]["acceptance_time_source"] == FALLBACK
    assert "acceptance_datetime_header" not in stored["raw_metadata"]


# ------------------------------------------------------------------ the SQL text (always runs, no PostgreSQL needed)
class _Recorder:
    """A connection and cursor that record what would be sent to PostgreSQL."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def executemany(self, sql, rows):
        self.calls.append((sql, list(rows)))

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def commit(self):
        return None


def _recording(database: Database) -> _Recorder:
    recorder = _Recorder()

    @contextmanager
    def connection():
        yield recorder

    database.database_url = "postgresql://recorded.invalid/never-connected"
    database.connection = connection  # type: ignore[method-assign]
    return recorder


def _squash(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_the_header_guard_is_decided_inside_on_conflict_do_update():
    database = Database(Settings(database_url=""))
    recorder = _recording(database)
    event = _filing(ACCEPTED, FALLBACK)
    event["valuation_relevant"] = True
    database.save_sec_filing_events([event], header_source=HEADER)

    (upsert, rows), (queue, _) = recorder.calls
    assert upsert is SEC_FILING_EVENTS_UPSERT_SQL
    assert rows[0]["header_source"] == HEADER and json.loads(rows[0]["raw_metadata"])["acceptance_time_source"] == FALLBACK
    guard = ("WHEN ir_events.raw_metadata->>'acceptance_time_source' = %(header_source)s "
             "AND (EXCLUDED.raw_metadata->>'acceptance_time_source') IS DISTINCT FROM %(header_source)s")
    on_conflict = _squash(upsert).split("ON CONFLICT (source_code, external_id) DO UPDATE", 1)[1]
    assert on_conflict.count(guard) == 2  # published_at and raw_metadata, both in the same statement as the insert
    assert f"published_at = CASE {guard} THEN ir_events.published_at" in on_conflict
    assert (f"raw_metadata = CASE {guard} THEN EXCLUDED.raw_metadata || jsonb_strip_nulls(jsonb_build_object( "
            "'acceptance_time_source', ir_events.raw_metadata->'acceptance_time_source', "
            "'acceptance_datetime_header', ir_events.raw_metadata->'acceptance_datetime_header')) "
            "ELSE EXCLUDED.raw_metadata END") in on_conflict
    assert "ir_valuation_queue" in queue


def test_without_the_header_guard_the_statement_is_save_ir_events_own():
    """save_ir_events stays byte-identical (R2D2 pins its source); the new statement differs only by the guard."""
    pinned = Database(Settings(database_url=""))
    recorder = _recording(pinned)
    pinned.save_ir_events([_filing(ACCEPTED, FALLBACK)])
    (original, _), = recorder.calls

    guarded = _squash(SEC_FILING_EVENTS_UPSERT_SQL)
    guard = ("WHEN ir_events.raw_metadata->>'acceptance_time_source' = %(header_source)s "
             "AND (EXCLUDED.raw_metadata->>'acceptance_time_source') IS DISTINCT FROM %(header_source)s")
    unguarded = guarded.replace(f"published_at = CASE {guard} THEN ir_events.published_at ", "published_at = CASE ")
    unguarded = re.sub(r"raw_metadata = CASE .*? ELSE EXCLUDED\.raw_metadata END,", "raw_metadata = EXCLUDED.raw_metadata,",
                       unguarded)
    unguarded = re.sub(r"%\(\w+\)s", "%s", unguarded)
    assert unguarded == _squash(original)
