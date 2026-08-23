from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import resource
import shutil
import socket
from threading import Event, Thread
import time
from typing import Any, Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")


class StatsSource(Protocol):
    def stats(self) -> Any: ...


class MicrostructureResourceTelemetry:
    """Append one-second, container-local capture health observations."""

    schema_version = "DAY-D-MICROSTRUCTURE-T0-v1"

    def __init__(
        self,
        root: Path,
        *,
        raw_capture: StatsSource,
        processor: StatsSource | None = None,
        interval_seconds: float = 1.0,
        minimum_free_bytes: int = 20 * 1024**3,
        service_name: str = "r2d2-worker",
        disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
        monotonic: Callable[[], float] = time.monotonic,
        process_time: Callable[[], float] = time.process_time,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
    ) -> None:
        self.root = Path(root)
        self.raw_capture = raw_capture
        self.processor = processor
        self.interval_seconds = max(0.5, float(interval_seconds))
        self.minimum_free_bytes = max(0, int(minimum_free_bytes))
        self.service_name = service_name
        self._disk_usage = disk_usage
        self._monotonic = monotonic
        self._process_time = process_time
        self._now = now
        self._cgroup_root = Path(cgroup_root)
        self._stop = Event()
        self._thread: Thread | None = None
        self._run_id = str(uuid4())
        self._last_monotonic: float | None = None
        self._last_cpu_seconds: float | None = None
        self._samples_written = 0
        self._write_errors = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        if not self._disk_available():
            raise RuntimeError(
                "microstructure telemetry disk reserve is unavailable at startup"
            )
        self._stop.clear()
        self._thread = Thread(
            target=self._run,
            name="microstructure-t0-telemetry",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            logger.error("Microstructure telemetry did not stop within timeout")
        self._thread = None

    def counters(self) -> dict[str, int]:
        return {
            "samples_written": self._samples_written,
            "write_errors": self._write_errors,
        }

    def snapshot(self) -> dict[str, Any]:
        measured_at = self._now().astimezone(timezone.utc)
        monotonic_now = self._monotonic()
        cpu_seconds = self._container_cpu_seconds()
        elapsed = (
            monotonic_now - self._last_monotonic
            if self._last_monotonic is not None
            else None
        )
        cpu_percent = (
            (cpu_seconds - self._last_cpu_seconds) / elapsed * 100.0
            if elapsed and elapsed > 0 and self._last_cpu_seconds is not None
            else None
        )
        self._last_monotonic = monotonic_now
        self._last_cpu_seconds = cpu_seconds

        raw = self.raw_capture.stats()
        processor = self.processor.stats() if self.processor else None
        free_bytes = int(self._disk_usage(self.root).free)
        return {
            "schema_version": self.schema_version,
            "measured_at": measured_at.isoformat(),
            "session_date": measured_at.astimezone(NEW_YORK).date().isoformat(),
            "service": self.service_name,
            "container_id": socket.gethostname(),
            "telemetry_run_id": self._run_id,
            "sample_gap_seconds": elapsed,
            "container_cpu_percent": cpu_percent,
            "container_rss_bytes": self._container_rss_bytes(),
            "disk_free_bytes": free_bytes,
            "disk_reserve_bytes": self.minimum_free_bytes,
            "raw": self._stats_payload(raw, measured_at),
            "processor": self._stats_payload(processor, measured_at),
        }

    def _run(self) -> None:
        handle = None
        current_session = None
        try:
            while not self._stop.is_set():
                started = self._monotonic()
                try:
                    payload = self.snapshot()
                    session = payload["session_date"]
                    if current_session != session:
                        if handle is not None:
                            handle.flush()
                            handle.close()
                        directory = self.root / f"session_date={session}"
                        directory.mkdir(parents=True, exist_ok=True)
                        path = directory / f"run-{self._run_id}.ndjson"
                        handle = path.open("x", encoding="utf-8")
                        current_session = session
                    record = json.dumps(
                        payload,
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ) + "\n"
                    if not self._disk_available(len(record.encode("utf-8"))):
                        raise OSError("microstructure telemetry disk reserve reached")
                    handle.write(record)
                    handle.flush()
                    self._samples_written += 1
                except Exception:
                    self._write_errors += 1
                    logger.exception("Failed to write microstructure T0 telemetry")
                elapsed = self._monotonic() - started
                self._stop.wait(max(0.0, self.interval_seconds - elapsed))
        finally:
            if handle is not None:
                try:
                    handle.flush()
                    handle.close()
                except Exception:
                    logger.exception("Failed to close microstructure telemetry file")

    @staticmethod
    def _stats_payload(stats: Any | None, measured_at: datetime) -> dict[str, Any] | None:
        if stats is None:
            return None
        payload = asdict(stats)
        for key, value in tuple(payload.items()):
            if isinstance(value, datetime):
                payload[key] = value.astimezone(timezone.utc).isoformat()
                gap_name = key.removeprefix("last_").removesuffix("_at")
                gap_name = gap_name.replace("_received", "_feed")
                payload[f"{gap_name}_gap_seconds"] = max(
                    0.0,
                    (measured_at - value.astimezone(timezone.utc)).total_seconds(),
                )
        return payload

    def _container_cpu_seconds(self) -> float:
        cpu_stat = self._cgroup_root / "cpu.stat"
        try:
            for line in cpu_stat.read_text(encoding="utf-8").splitlines():
                key, value = line.split(maxsplit=1)
                if key == "usage_usec":
                    return int(value) / 1_000_000
        except (OSError, ValueError):
            pass
        return self._process_time()

    def _container_rss_bytes(self) -> int:
        memory_current = self._cgroup_root / "memory.current"
        try:
            return int(memory_current.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            scale = 1 if os.uname().sysname == "Darwin" else 1024
            return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale)

    def _disk_available(self, required_bytes: int = 0) -> bool:
        try:
            free_bytes = int(self._disk_usage(self.root).free)
        except OSError:
            return False
        return free_bytes - max(0, int(required_bytes)) >= self.minimum_free_bytes
