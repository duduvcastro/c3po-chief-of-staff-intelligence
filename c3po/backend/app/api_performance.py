from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import ceil
from threading import Lock


@dataclass(frozen=True)
class ApiTimingSample:
    recorded_at: datetime
    method: str
    route: str
    duration_ms: float
    status_code: int


class ApiPerformanceRegistry:
    def __init__(self, *, retention_minutes: int = 15, max_samples: int = 10_000) -> None:
        self.retention_minutes = retention_minutes
        self.samples: deque[ApiTimingSample] = deque(maxlen=max_samples)
        self.lock = Lock()

    def record(self, method: str, route: str, duration_ms: float, status_code: int) -> None:
        sample = ApiTimingSample(
            recorded_at=datetime.now(timezone.utc),
            method=method.upper(),
            route=route,
            duration_ms=max(0.0, duration_ms),
            status_code=status_code,
        )
        with self.lock:
            self.samples.append(sample)
            self._prune(sample.recorded_at)

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
            durations = sorted(sample.duration_ms for sample in samples)
            p95_index = max(0, ceil(len(durations) * 0.95) - 1)
            output.append({
                "method": method,
                "route": route,
                "request_count": len(samples),
                "average_ms": round(sum(durations) / len(durations), 2),
                "p95_ms": round(durations[p95_index], 2),
                "max_ms": round(durations[-1], 2),
                "error_percent": round(
                    sum(1 for sample in samples if sample.status_code >= 400) / len(samples) * 100,
                    2,
                ),
            })
        return sorted(output, key=lambda item: (-float(item["p95_ms"]), -int(item["request_count"])))

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(minutes=self.retention_minutes)
        while self.samples and self.samples[0].recorded_at < cutoff:
            self.samples.popleft()


api_performance = ApiPerformanceRegistry()
