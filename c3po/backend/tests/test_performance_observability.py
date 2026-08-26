from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.access_control import required_capability
from app.api_performance import ApiPerformanceRegistry, PerformanceObservabilityService
from app.config import Settings
from app.database import Database
from app.main import _api_route_template
from app.schemas import PageLoadPerformanceRequest


def _settings(**overrides) -> Settings:
    return Settings(
        database_url="",
        build_sha="abc1234",
        performance_flush_seconds=60,
        performance_retention_days=90,
        performance_minimum_sample_sessions=5,
        **overrides,
    )


def test_api_requests_are_buffered_then_persisted_in_fixed_buckets() -> None:
    settings = _settings()
    database = Database(settings)
    registry = ApiPerformanceRegistry(
        flush_seconds=60,
        build_sha=settings.build_sha,
        process_id="c42b784f-7c3f-4b09-a65f-3242a0405591",
    )
    service = PerformanceObservabilityService(settings, database, registry)
    at = datetime.now(timezone.utc).replace(second=10, microsecond=0)

    registry.record("GET", "/api/v1/market-data/quotes/{market}/{symbol}", 10, 200, recorded_at=at)
    registry.record("GET", "/api/v1/market-data/quotes/{market}/{symbol}", 30, 500, recorded_at=at)

    assert database._api_performance_buckets == []
    outcome = service.flush(now=at + timedelta(minutes=1))

    assert outcome["api_buckets"] == 1
    row = database._api_performance_buckets[0]
    assert row["route_template"] == "/api/v1/market-data/quotes/{market}/{symbol}"
    assert row["request_count"] == 2
    assert row["error_count"] == 1
    assert row["durations_ms"] == [10, 30]
    assert row["backend_build_sha"] == "abc1234"


def test_bucket_insert_and_page_sample_are_restart_idempotent() -> None:
    settings = _settings()
    database = Database(settings)
    at = datetime.now(timezone.utc)
    bucket = {
        "id": "a" * 64,
        "process_id": str(uuid4()),
        "bucket_start": at,
        "bucket_seconds": 60,
        "backend_build_sha": "abc1234",
        "method": "GET",
        "route_template": "/api/v1/command-center",
        "request_count": 1,
        "error_count": 0,
        "duration_sum_ms": 12.0,
        "duration_max_ms": 12.0,
        "durations_ms": [12.0],
    }
    page = {
        "sample_id": str(uuid4()),
        "received_at": at,
        "view": "command",
        "frontend_build_sha": "def4567",
        "backend_build_sha": "abc1234",
        "device_class": "desktop",
        "total_ms": 100.0,
        "api_wait_ms": 80.0,
        "backend_total_ms": 40.0,
        "render_ms": 20.0,
        "request_count": 2,
    }

    assert database.save_api_performance_buckets([bucket]) == 1
    assert database.save_api_performance_buckets([bucket]) == 0
    assert database.save_page_load_performance_samples([page]) == 1
    assert database.save_page_load_performance_samples([page]) == 0


def test_history_groups_by_view_and_build_and_waits_for_five_sessions() -> None:
    settings = _settings()
    database = Database(settings)
    service = PerformanceObservabilityService(settings, database, ApiPerformanceRegistry())
    new_york = ZoneInfo("America/New_York")
    today = datetime.now(new_york).date()
    session_dates = []
    candidate = today
    while len(session_dates) < 5:
        if candidate.weekday() < 5:
            session_dates.append(candidate)
        candidate -= timedelta(days=1)

    for index, session_date in enumerate(session_dates):
        observed_at = datetime.combine(session_date, datetime.min.time(), tzinfo=new_york).replace(
            hour=10,
            minute=30,
        ).astimezone(timezone.utc)
        database.save_page_load_performance_samples([{
            "sample_id": str(uuid4()),
            "received_at": observed_at,
            "view": "r2d2",
            "frontend_build_sha": "def4567",
            "backend_build_sha": "abc1234",
            "device_class": "desktop",
            "total_ms": 100.0 + index * 10,
            "api_wait_ms": 70.0,
            "backend_total_ms": 40.0,
            "render_ms": 30.0 + index * 10,
            "request_count": 2,
        }])

    result = service.history(hours=24 * 10)

    assert result["sample_status"] == "stable"
    assert len(result["observed_regular_session_dates"]) == 5
    assert result["page_loads"][0]["view"] == "r2d2"
    assert result["page_loads"][0]["frontend_build_sha"] == "def4567"
    assert result["page_loads"][0]["sample_count"] == 5


def test_history_compares_regular_session_and_off_hours_capacity() -> None:
    settings = _settings(server_usage_cpu_count=2)
    database = Database(settings)
    service = PerformanceObservabilityService(settings, database, ApiPerformanceRegistry())
    new_york = ZoneInfo("America/New_York")
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    today = datetime.now(new_york).date()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    regular_at = datetime.combine(today, datetime.min.time(), tzinfo=new_york).replace(
        hour=10,
        minute=30,
    ).astimezone(timezone.utc)
    off_hours_at = datetime.combine(
        datetime.now(sao_paulo).date(),
        datetime.min.time(),
        tzinfo=sao_paulo,
    ).replace(hour=2).astimezone(timezone.utc)
    base = {
        "server_id": settings.server_usage_server_id,
        "server_name": settings.server_usage_server_name,
        "region": settings.server_usage_region,
        "disk_total_bytes": 1000,
        "disk_used_bytes": 400,
        "disk_free_bytes": 600,
        "source": "test",
    }
    database.save_server_usage_samples([
        {
            **base,
            "collected_at": regular_at,
            "cpu_percent": 40.0,
            "cpu_steal_percent": 2.0,
            "load_average_1m": 1.5,
            "load_average_5m": 1.0,
            "load_average_15m": 0.8,
        },
        {
            **base,
            "collected_at": off_hours_at,
            "cpu_percent": 80.0,
            "cpu_steal_percent": 5.0,
            "load_average_1m": 2.4,
            "load_average_5m": 2.0,
            "load_average_15m": 1.6,
        },
    ])

    result = service.history(hours=24 * 10)
    windows = {item["window"]: item for item in result["capacity_windows"]}

    regular = windows["us_regular_session"]
    assert regular["cpu_p95_percent"] == pytest.approx(40.0)
    assert regular["cpu_steal_max_percent"] == pytest.approx(2.0)
    assert regular["load_1m_p95_per_vcpu"] == pytest.approx(0.75)
    off_hours = windows["valuation_off_hours"]
    assert off_hours["cpu_p95_percent"] == pytest.approx(80.0)
    assert off_hours["load_1m_p95_per_vcpu"] == pytest.approx(1.2)


def test_route_identity_never_falls_back_to_resolved_path_or_query() -> None:
    matched = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/market-data/quotes/us/AAPL",
        "query_string": b"symbol=AAPL",
        "headers": [],
        "route": SimpleNamespace(path="/api/v1/market-data/quotes/{market}/{symbol}"),
    })
    unmatched = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/private/AAPL",
        "query_string": b"symbol=AAPL",
        "headers": [],
    })

    assert _api_route_template(matched) == "/api/v1/market-data/quotes/{market}/{symbol}"
    assert _api_route_template(unmatched) == "/api/{unmatched}"
    assert "AAPL" not in _api_route_template(unmatched)


def test_middleware_records_the_fastapi_template_not_the_requested_filename() -> None:
    from app import main as app_main

    with app_main.api_performance.lock:
        app_main.api_performance.samples.clear()
        app_main.api_performance._api_buckets.clear()
    with TestClient(app_main.app) as client:
        response = client.get("/api/v1/one-pagers/PRIVATE-AAPL.pdf")

    assert response.status_code == 404
    routes = {item["route"] for item in app_main.api_performance.snapshot()}
    assert "/api/v1/one-pagers/{filename}" in routes
    assert all("PRIVATE-AAPL" not in route for route in routes)


def test_page_load_contract_forbids_identity_and_query_fields() -> None:
    payload = {
        "sample_id": str(uuid4()),
        "view": "r2d2",
        "frontend_build_sha": "def4567",
        "device_class": "desktop",
        "total_ms": 100,
        "api_wait_ms": 70,
        "backend_total_ms": 40,
        "render_ms": 30,
        "request_count": 2,
        "symbol": "AAPL",
    }

    with pytest.raises(ValidationError):
        PageLoadPerformanceRequest.model_validate(payload)


def test_page_load_endpoint_accepts_anonymous_view_metrics_and_flushes_them() -> None:
    from app import main as app_main

    sample_id = str(uuid4())
    with TestClient(app_main.app) as client:
        response = client.post("/api/v1/telemetry/page-load", json={
            "sample_id": sample_id,
            "view": "r2d2",
            "frontend_build_sha": "def4567",
            "device_class": "desktop",
            "total_ms": 100,
            "api_wait_ms": 70,
            "backend_total_ms": 40,
            "render_ms": 30,
            "request_count": 2,
        })

    assert response.status_code == 202
    assert response.json()["sample_id"] == sample_id
    assert any(
        str(item["sample_id"]) == sample_id
        for item in app_main.database._page_load_performance_samples
    )


def test_page_load_ingestion_requires_read_not_owner_capability() -> None:
    assert required_capability("/api/v1/telemetry/page-load", "POST") == "read"
