"""Provider classification regressions on a disposable, local PostgreSQL.

C3PO_PROVIDER_HEALTH_TEST_DSN is optional; no production credentials are read.
The fixture uses connection-local temporary tables and never initializes schema.
"""
import os
from contextlib import contextmanager

import psycopg
import pytest

from app.config import Settings
from app.database import Database
from app.market_data.service import MarketDataService


@pytest.fixture(params=["memory", "postgres"])
def provider_database(request):
    settings = Settings(database_url="", eodhd_api_token="test", brapi_token="test")
    database = Database(settings)
    if request.param == "memory":
        yield database, settings
        return
    dsn = os.environ.get("C3PO_PROVIDER_HEALTH_TEST_DSN")
    if not dsn:
        pytest.skip("disposable local PostgreSQL not configured")
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    assert info.get("host", "").startswith("/tmp/"), "local test socket required"
    with psycopg.connect(dsn, client_encoding="utf8") as connection:
        connection.execute("""CREATE TEMP TABLE data_sources (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE,
            name text, source_type text, updated_at timestamptz DEFAULT now())""")
        connection.execute("""CREATE TEMP TABLE ingestion_runs (
            id uuid PRIMARY KEY, source_id uuid, status text, started_at timestamptz,
            completed_at timestamptz, metadata jsonb, records_read integer,
            records_written integer, error_summary text)""")
        connection.commit()
        database.database_url = dsn

        @contextmanager
        def local_connection():
            yield connection

        database.connection = local_connection
        yield database, settings


def test_health_survives_provider_reclassification_and_keeps_real_failures(provider_database):
    database, settings = provider_database
    service = MarketDataService(settings, database)
    quote = database.begin_ingestion_run("eodhd", "EODHD", "market_data", {})
    database.finish_ingestion_run(quote, "succeeded", 1, 1)
    success = database.market_data_provider_health()["eodhd"]["last_success_at"]

    # A different consumer changes the shared source classification, without
    # changing any quote run. This used to hide the entire PostgreSQL history.
    database.ensure_data_source("eodhd", "EODHD", "fundamental_data")
    state = next(p for p in service.health() if p.code == "eodhd")
    assert state.status == "healthy"
    assert state.last_success_at == success
    assert state.last_error is None

    failed = database.begin_ingestion_run("eodhd", "EODHD", "fundamental_data", {})
    database.finish_ingestion_run(failed, "failed", 1, 0, "provider unavailable")
    state = next(p for p in service.health() if p.code == "eodhd")
    assert state.status == "attention"
    assert state.last_error == "provider unavailable"
    assert state.last_success_at == success

    recovered = database.begin_ingestion_run("eodhd", "EODHD", "fundamental_data", {})
    database.finish_ingestion_run(recovered, "succeeded", 1, 1)
    state = next(p for p in service.health() if p.code == "eodhd")
    assert state.status == "healthy"
    assert state.last_error is None
    assert state.last_success_at >= success
    assert next(p for p in service.health() if p.code == "brapi").status == "attention"
