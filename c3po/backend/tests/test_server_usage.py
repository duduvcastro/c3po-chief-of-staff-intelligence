from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.database import Database
from app.api_performance import ApiPerformanceRegistry, api_performance
from app.server_usage import ServerUsageCollector, ServerUsageService


def test_collector_reads_host_cpu_and_calculates_delta(tmp_path) -> None:
    proc_stat = tmp_path / "stat"
    proc_stat.write_text("cpu  100 0 50 850 0 0 0 0 0 0\n", encoding="utf-8")
    settings = Settings(
        database_url="",
        server_usage_proc_stat_path=proc_stat,
        server_usage_disk_path=tmp_path,
    )
    collector = ServerUsageCollector(settings, Database(settings))

    assert collector.cpu_ticks() == (1000, 850)
    sample = collector.sample((1000, 850), (1100, 920))

    assert sample["cpu_percent"] == pytest.approx(30.0)
    assert sample["disk_total_bytes"] > 0
    assert sample["disk_used_bytes"] >= 0


def test_sysstat_backfill_is_imported_as_cpu_history() -> None:
    settings = Settings(database_url="")
    database = Database(settings)
    collector = ServerUsageCollector(settings, database)
    payload = """# hostname;interval;timestamp;CPU;%user;%nice;%system;%iowait;%steal;%idle
host;585;2026-08-06 20:00:00 UTC;-1;4.00;0.00;1.00;0.00;0.00;95.00
host;585;2026-08-06 20:10:00 UTC;-1;7.00;0.00;2.00;0.00;0.00;91.00
"""

    assert collector.import_sadf(payload) == 2
    rows = database.list_server_usage_samples(datetime(2026, 8, 6, tzinfo=timezone.utc))

    assert [float(row["cpu_percent"]) for row in rows] == [5.0, 9.0]
    assert all(row["source"] == "sysstat-backfill" for row in rows)


def test_snapshot_uses_a_time_based_five_minute_moving_average() -> None:
    settings = Settings(database_url="")
    database = Database(settings)
    now = datetime.now(timezone.utc)
    base = {
        "server_id": settings.server_usage_server_id,
        "server_name": settings.server_usage_server_name,
        "region": settings.server_usage_region,
        "disk_total_bytes": 1000,
        "disk_used_bytes": 440,
        "disk_free_bytes": 560,
        "source": "test",
    }
    database.save_server_usage_samples([
        {**base, "collected_at": now - timedelta(minutes=7), "cpu_percent": 90.0},
        {**base, "collected_at": now - timedelta(minutes=4), "cpu_percent": 20.0},
        {**base, "collected_at": now - timedelta(minutes=1), "cpu_percent": 40.0},
    ])

    response = ServerUsageService(settings, database).snapshot(hours=1)

    assert len(response.servers) == 1
    server = response.servers[0]
    assert server.current.cpu_moving_average_5m == pytest.approx(30.0)
    assert server.current.disk_percent == pytest.approx(44.0)
    assert server.status == "healthy"


def test_api_performance_registry_reports_slowest_routes_by_p95() -> None:
    registry = ApiPerformanceRegistry()
    registry.record("GET", "/api/v1/fast", 10, 200)
    registry.record("GET", "/api/v1/slow", 80, 200)
    registry.record("GET", "/api/v1/slow", 120, 500)

    rows = registry.snapshot()

    assert rows[0] == {
        "method": "GET",
        "route": "/api/v1/slow",
        "request_count": 2,
        "average_ms": 100.0,
        "p95_ms": 120,
        "max_ms": 120,
        "error_percent": 50.0,
    }


def test_server_usage_snapshot_includes_api_performance() -> None:
    settings = Settings(database_url="")
    database = Database(settings)
    api_performance.record("GET", "/api/v1/test-performance", 42, 200)

    response = ServerUsageService(settings, database).snapshot(hours=1)

    matching = [item for item in response.api_endpoints if item.route == "/api/v1/test-performance"]
    assert matching[0].average_ms == 42
