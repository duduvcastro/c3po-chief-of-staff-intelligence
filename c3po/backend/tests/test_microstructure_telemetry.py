from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import time

from app.microstructure_capture import CaptureStats
from app.microstructure_processor import ProcessorStats
from app.microstructure_telemetry import MicrostructureResourceTelemetry


class _StatsSource:
    def __init__(self, value) -> None:  # noqa: ANN001
        self.value = value

    def stats(self):  # noqa: ANN201
        return self.value


def _raw_stats(now: datetime) -> CaptureStats:
    return CaptureStats(
        accepted=100,
        written=98,
        dropped=1,
        disk_guard_dropped=1,
        write_errors=0,
        queue_depth=4,
        queue_capacity=100,
        queue_high_water=12,
        last_trade_received_at=now - timedelta(seconds=2),
        last_quote_received_at=now - timedelta(seconds=1),
        last_write_at=now - timedelta(milliseconds=250),
    )


def _processor_stats(now: datetime) -> ProcessorStats:
    return ProcessorStats(
        accepted=100,
        processed=95,
        malformed=1,
        ignored=1,
        late=1,
        dropped=1,
        disk_guard_dropped=1,
        aggregates_written=50,
        write_errors=0,
        queue_depth=3,
        queue_capacity=100,
        queue_high_water=9,
        last_event_at=now - timedelta(milliseconds=500),
    )


def test_telemetry_exposes_container_queue_drop_and_feed_gap_metrics(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir()
    (cgroup / "cpu.stat").write_text("usage_usec 1000000\n", encoding="utf-8")
    (cgroup / "memory.current").write_text("123456\n", encoding="utf-8")
    monotonic_values = iter((10.0, 11.0))
    now_values = iter((now, now + timedelta(seconds=1)))
    telemetry = MicrostructureResourceTelemetry(
        tmp_path / "telemetry",
        raw_capture=_StatsSource(_raw_stats(now)),
        processor=_StatsSource(_processor_stats(now)),
        minimum_free_bytes=0,
        disk_usage=lambda path: SimpleNamespace(free=1_000_000),
        monotonic=lambda: next(monotonic_values),
        now=lambda: next(now_values),
        cgroup_root=cgroup,
    )

    first = telemetry.snapshot()
    (cgroup / "cpu.stat").write_text("usage_usec 1250000\n", encoding="utf-8")
    second = telemetry.snapshot()

    assert first["container_cpu_percent"] is None
    assert second["container_cpu_percent"] == 25.0
    assert second["container_rss_bytes"] == 123456
    assert second["sample_gap_seconds"] == 1.0
    assert second["raw"]["queue_depth"] == 4
    assert second["raw"]["queue_high_water"] == 12
    assert second["raw"]["dropped"] == 1
    assert second["raw"]["trade_feed_gap_seconds"] == 3.0
    assert second["raw"]["quote_feed_gap_seconds"] == 2.0
    assert second["processor"]["event_gap_seconds"] == 1.5


def test_telemetry_writes_append_only_one_second_rows(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    telemetry = MicrostructureResourceTelemetry(
        tmp_path,
        raw_capture=_StatsSource(_raw_stats(now)),
        processor=None,
        interval_seconds=0.5,
        minimum_free_bytes=0,
        disk_usage=lambda path: SimpleNamespace(free=1_000_000),
    )

    telemetry.start()
    time.sleep(0.05)
    telemetry.stop()

    paths = list(tmp_path.glob("session_date=*/run-*.ndjson"))
    assert len(paths) == 1
    rows = [json.loads(line) for line in paths[0].read_text().splitlines()]
    assert rows
    assert rows[0]["schema_version"] == "DAY-D-MICROSTRUCTURE-T0-v1"
    assert rows[0]["service"] == "r2d2-worker"
    assert rows[0]["processor"] is None
