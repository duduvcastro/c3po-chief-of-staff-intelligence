from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from math import ceil
from threading import Lock
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import Settings
from .database import Database

logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _safe_build_sha(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"development", "unknown"}:
        return normalized
    if 7 <= len(normalized) <= 64 and all(character in "0123456789abcdef" for character in normalized):
        return normalized
    return "unknown"


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, ceil(len(ordered) * percentile) - 1)
    return ordered[index]


@dataclass(frozen=True)
class ApiTimingSample:
    recorded_at: datetime
    method: str
    route: str
    duration_ms: float
    status_code: int


@dataclass
class _ApiTimingBucket:
    bucket_start: datetime
    method: str
    route: str
    durations_ms: list[float] = field(default_factory=list)
    error_count: int = 0


class ApiPerformanceRegistry:
    def __init__(
        self,
        *,
        retention_minutes: int = 15,
        max_samples: int = 10_000,
        flush_seconds: int = 60,
        build_sha: str = "development",
        process_id: str | None = None,
    ) -> None:
        self.retention_minutes = retention_minutes
        self.flush_seconds = max(1, flush_seconds)
        self.build_sha = _safe_build_sha(build_sha)
        self.process_id = process_id or str(uuid4())
        self.samples: deque[ApiTimingSample] = deque(maxlen=max_samples)
        self.lock = Lock()
        self._api_buckets: dict[tuple[datetime, str, str], _ApiTimingBucket] = {}
        self._page_load_samples: dict[str, dict[str, Any]] = {}

    def configure(self, *, flush_seconds: int, build_sha: str) -> None:
        with self.lock:
            self.flush_seconds = max(1, flush_seconds)
            self.build_sha = _safe_build_sha(build_sha)

    def record(
        self,
        method: str,
        route: str,
        duration_ms: float,
        status_code: int,
        *,
        recorded_at: datetime | None = None,
    ) -> None:
        at = recorded_at or datetime.now(timezone.utc)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        else:
            at = at.astimezone(timezone.utc)
        sample = ApiTimingSample(
            recorded_at=at,
            method=method.upper(),
            route=route,
            duration_ms=round(max(0.0, duration_ms), 3),
            status_code=status_code,
        )
        bucket_start = self._bucket_start(at)
        key = (bucket_start, sample.method, sample.route)
        with self.lock:
            self.samples.append(sample)
            bucket = self._api_buckets.setdefault(
                key,
                _ApiTimingBucket(
                    bucket_start=bucket_start,
                    method=sample.method,
                    route=sample.route,
                ),
            )
            bucket.durations_ms.append(sample.duration_ms)
            if sample.status_code >= 400:
                bucket.error_count += 1
            self._prune(sample.recorded_at)

    def queue_page_load(self, payload: dict[str, Any], *, received_at: datetime | None = None) -> bool:
        sample_id = str(payload["sample_id"])
        at = received_at or datetime.now(timezone.utc)
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        else:
            at = at.astimezone(timezone.utc)
        row = {
            **payload,
            "sample_id": sample_id,
            "received_at": at,
            "backend_build_sha": self.build_sha,
        }
        with self.lock:
            if sample_id in self._page_load_samples:
                return False
            self._page_load_samples[sample_id] = row
        return True

    def snapshot(self) -> list[dict[str, object]]:
        now = datetime.now(timezone.utc)
        with self.lock:
            self._prune(now)
            current = list(self.samples)

        grouped: dict[tuple[str, str], list[ApiTimingSample]] = {}
        for sample in current:
            grouped.setdefault((sample.method, sample.route), []).append(sample)

        output: list[dict[str, object]] = []
        for (method, route), samples in grouped.items():
            durations = [sample.duration_ms for sample in samples]
            output.append({
                "method": method,
                "route": route,
                "request_count": len(samples),
                "average_ms": round(sum(durations) / len(durations), 2),
                "p95_ms": round(_percentile(durations, 0.95), 2),
                "max_ms": round(max(durations), 2),
                "error_percent": round(
                    sum(1 for sample in samples if sample.status_code >= 400) / len(samples) * 100,
                    2,
                ),
            })
        return sorted(output, key=lambda item: (-float(item["p95_ms"]), -int(item["request_count"])))

    def drain(
        self,
        *,
        now: datetime | None = None,
        include_current: bool = False,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.lock:
            ready_keys = [
                key for key, bucket in self._api_buckets.items()
                if include_current or bucket.bucket_start + timedelta(seconds=self.flush_seconds) <= at
            ]
            buckets = [self._api_buckets.pop(key) for key in ready_keys]
            page_loads = list(self._page_load_samples.values())
            self._page_load_samples.clear()

        api_rows: list[dict[str, Any]] = []
        for bucket in buckets:
            identity = "|".join((
                self.process_id,
                bucket.bucket_start.isoformat(),
                bucket.method,
                bucket.route,
                self.build_sha,
            ))
            api_rows.append({
                "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "process_id": self.process_id,
                "bucket_start": bucket.bucket_start,
                "bucket_seconds": self.flush_seconds,
                "backend_build_sha": self.build_sha,
                "method": bucket.method,
                "route_template": bucket.route,
                "request_count": len(bucket.durations_ms),
                "error_count": bucket.error_count,
                "duration_sum_ms": round(sum(bucket.durations_ms), 3),
                "duration_max_ms": round(max(bucket.durations_ms), 3),
                "durations_ms": bucket.durations_ms,
            })
        return api_rows, page_loads

    def restore(self, api_rows: list[dict[str, Any]], page_loads: list[dict[str, Any]]) -> None:
        with self.lock:
            for row in api_rows:
                key = (row["bucket_start"], row["method"], row["route_template"])
                bucket = self._api_buckets.setdefault(
                    key,
                    _ApiTimingBucket(
                        bucket_start=row["bucket_start"],
                        method=row["method"],
                        route=row["route_template"],
                    ),
                )
                bucket.durations_ms = list(row["durations_ms"]) + bucket.durations_ms
                bucket.error_count += int(row["error_count"])
            for row in page_loads:
                self._page_load_samples.setdefault(str(row["sample_id"]), row)

    def _bucket_start(self, at: datetime) -> datetime:
        epoch_seconds = int(at.timestamp())
        start_seconds = epoch_seconds - (epoch_seconds % self.flush_seconds)
        return datetime.fromtimestamp(start_seconds, tz=timezone.utc)

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(minutes=self.retention_minutes)
        while self.samples and self.samples[0].recorded_at < cutoff:
            self.samples.popleft()


class PerformanceObservabilityService:
    def __init__(self, settings: Settings, database: Database, registry: ApiPerformanceRegistry) -> None:
        self.settings = settings
        self.database = database
        self.registry = registry
        self.registry.configure(
            flush_seconds=settings.performance_flush_seconds,
            build_sha=settings.build_sha,
        )
        self._last_purge_at: datetime | None = None

    def capture_page_load(self, payload: dict[str, Any]) -> bool:
        return self.registry.queue_page_load(payload)

    def flush(self, *, include_current: bool = False, now: datetime | None = None) -> dict[str, int]:
        at = now or datetime.now(timezone.utc)
        api_rows, page_loads = self.registry.drain(now=at, include_current=include_current)
        try:
            api_written = self.database.save_api_performance_buckets(api_rows)
            page_written = self.database.save_page_load_performance_samples(page_loads)
        except Exception:
            self.registry.restore(api_rows, page_loads)
            raise

        purged = 0
        if self._last_purge_at is None or at - self._last_purge_at >= timedelta(hours=24):
            before = at - timedelta(days=self.settings.performance_retention_days)
            purged = self.database.purge_performance_observations(before)
            self._last_purge_at = at
        return {"api_buckets": api_written, "page_loads": page_written, "purged": purged}

    def history(self, *, hours: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=hours)
        api_rows = self.database.list_api_performance_buckets(since)
        page_rows = self.database.list_page_load_performance_samples(since)
        capacity_rows = self.database.list_server_usage_samples(since)

        api_grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in api_rows:
            key = (str(row["backend_build_sha"]), str(row["method"]), str(row["route_template"]))
            api_grouped.setdefault(key, []).append(row)
        api_summaries: list[dict[str, Any]] = []
        for (build_sha, method, route), rows in api_grouped.items():
            durations = [float(value) for row in rows for value in row["durations_ms"]]
            request_count = sum(int(row["request_count"]) for row in rows)
            error_count = sum(int(row["error_count"]) for row in rows)
            if not durations or not request_count:
                continue
            api_summaries.append({
                "backend_build_sha": build_sha,
                "method": method,
                "route": route,
                "bucket_count": len(rows),
                "request_count": request_count,
                "average_ms": round(sum(durations) / len(durations), 2),
                "p95_ms": round(_percentile(durations, 0.95), 2),
                "max_ms": round(max(durations), 2),
                "error_percent": round(error_count / request_count * 100, 2),
                "total_duration_ms": round(sum(durations), 2),
            })
        api_summaries.sort(key=lambda item: (-float(item["total_duration_ms"]), -float(item["p95_ms"])))

        page_grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in page_rows:
            key = (
                str(row["frontend_build_sha"]),
                str(row["backend_build_sha"]),
                str(row["view_key"]),
                str(row["device_class"]),
            )
            page_grouped.setdefault(key, []).append(row)
        page_summaries: list[dict[str, Any]] = []
        for (frontend_build, backend_build, view_key, device_class), rows in page_grouped.items():
            totals = [float(row["total_ms"]) for row in rows]
            sample_count = len(rows)
            page_summaries.append({
                "frontend_build_sha": frontend_build,
                "backend_build_sha": backend_build,
                "view": view_key,
                "device_class": device_class,
                "sample_count": sample_count,
                "average_total_ms": round(sum(totals) / sample_count, 2),
                "p95_total_ms": round(_percentile(totals, 0.95), 2),
                "average_api_wait_ms": round(sum(float(row["api_wait_ms"]) for row in rows) / sample_count, 2),
                "average_backend_ms": round(sum(float(row["backend_total_ms"]) for row in rows) / sample_count, 2),
                "average_render_ms": round(sum(float(row["render_ms"]) for row in rows) / sample_count, 2),
                "average_request_count": round(sum(int(row["request_count"]) for row in rows) / sample_count, 2),
            })
        page_summaries.sort(key=lambda item: (-float(item["p95_total_ms"]), -int(item["sample_count"])))

        observed_at = [row["bucket_start"] for row in api_rows] + [row["received_at"] for row in page_rows]
        session_dates = sorted({
            local.date().isoformat()
            for value in observed_at
            for local in [value.astimezone(NEW_YORK)]
            if local.weekday() < 5 and time(9, 30) <= local.time().replace(tzinfo=None) <= time(16, 0)
        })
        minimum_sessions = self.settings.performance_minimum_sample_sessions
        return {
            "generated_at": now,
            "window_hours": hours,
            "retention_days": self.settings.performance_retention_days,
            "flush_seconds": self.settings.performance_flush_seconds,
            "minimum_sample_sessions": minimum_sessions,
            "observed_regular_session_dates": session_dates,
            "sample_status": "stable" if len(session_dates) >= minimum_sessions else "collecting",
            "api_routes": api_summaries,
            "page_loads": page_summaries,
            "capacity_windows": self._capacity_windows(capacity_rows),
            "capacity_methodology": {
                "us_regular_session": "Weekdays from 09:30 through 16:00 America/New_York",
                "valuation_off_hours": "Every day from 01:00 through 08:00 America/Sao_Paulo",
                "load_normalization": f"One-minute load p95 divided by {self.settings.server_usage_cpu_count} vCPU",
                "decision_gate": f"Collect at least {minimum_sessions} US regular sessions before sizing infrastructure",
            },
            "privacy": {
                "route_identity": "FastAPI route template only",
                "page_identity": "view key, build hashes and viewport class only",
                "excluded": "resolved paths, query strings, symbols, tickers, user and session identifiers",
            },
        }

    def _capacity_windows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[tuple[dict[str, Any], str]]] = {
            "us_regular_session": [],
            "valuation_off_hours": [],
        }
        for row in rows:
            collected_at = row["collected_at"]
            new_york = collected_at.astimezone(NEW_YORK)
            sao_paulo = collected_at.astimezone(SAO_PAULO)
            new_york_time = new_york.time().replace(tzinfo=None)
            sao_paulo_time = sao_paulo.time().replace(tzinfo=None)
            if new_york.weekday() < 5 and time(9, 30) <= new_york_time <= time(16, 0):
                grouped["us_regular_session"].append((row, new_york.date().isoformat()))
            if time(1, 0) <= sao_paulo_time <= time(8, 0):
                grouped["valuation_off_hours"].append((row, sao_paulo.date().isoformat()))

        summaries: list[dict[str, Any]] = []
        for window, dated_rows in grouped.items():
            if not dated_rows:
                continue
            window_rows = [row for row, _ in dated_rows]
            cpu = self._numeric_values(window_rows, "cpu_percent")
            steal = self._numeric_values(window_rows, "cpu_steal_percent")
            load = self._numeric_values(window_rows, "load_average_1m")
            load_p95 = _percentile(load, 0.95) if load else None
            summaries.append({
                "window": window,
                "sample_count": len(window_rows),
                "observed_dates": sorted({date for _, date in dated_rows}),
                "cpu_average_percent": self._average(cpu),
                "cpu_p95_percent": round(_percentile(cpu, 0.95), 3) if cpu else None,
                "cpu_max_percent": round(max(cpu), 3) if cpu else None,
                "cpu_steal_average_percent": self._average(steal),
                "cpu_steal_p95_percent": round(_percentile(steal, 0.95), 3) if steal else None,
                "cpu_steal_max_percent": round(max(steal), 3) if steal else None,
                "load_1m_average": self._average(load, digits=4),
                "load_1m_p95": round(load_p95, 4) if load_p95 is not None else None,
                "load_1m_max": round(max(load), 4) if load else None,
                "load_1m_p95_per_vcpu": (
                    round(load_p95 / self.settings.server_usage_cpu_count, 4)
                    if load_p95 is not None else None
                ),
            })
        return summaries

    @staticmethod
    def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
        return [float(row[key]) for row in rows if row.get(key) is not None]

    @staticmethod
    def _average(values: list[float], *, digits: int = 3) -> float | None:
        return round(sum(values) / len(values), digits) if values else None


async def run_performance_flush_loop(
    service: PerformanceObservabilityService,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=service.settings.performance_flush_seconds)
        except TimeoutError:
            try:
                await asyncio.to_thread(service.flush)
            except Exception:
                logger.exception("Persistent performance telemetry flush failed")
    try:
        await asyncio.to_thread(service.flush, include_current=True)
    except Exception:
        logger.exception("Final persistent performance telemetry flush failed")


api_performance = ApiPerformanceRegistry()
