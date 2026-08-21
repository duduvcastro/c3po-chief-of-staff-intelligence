from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from queue import Full, Queue
from threading import Event, Lock, Thread
from typing import Protocol
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
NEW_YORK = ZoneInfo("America/New_York")


class RawStreamCapture(Protocol):
    """Non-blocking sink for provider payloads exactly as received."""

    def start(self) -> None: ...

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool: ...

    def stop(self) -> None: ...


class CompositeRawStreamCapture:
    """Fan out one exact provider payload to independent passive consumers."""

    def __init__(self, captures: list[RawStreamCapture]) -> None:
        self.captures = list(captures)

    def start(self) -> None:
        for capture in self.captures:
            capture.start()

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool:
        accepted = True
        for capture in self.captures:
            accepted = capture.record(feed, payload, received_at=received_at) and accepted
        return accepted

    def stop(self) -> None:
        for capture in reversed(self.captures):
            capture.stop()


@dataclass(frozen=True)
class CaptureStats:
    accepted: int
    written: int
    dropped: int
    write_errors: int


class AppendOnlyRawStreamCapture:
    """Spool raw EODHD events to session-partitioned append-only NDJSON.

    WebSocket ingestion never waits for disk I/O. A bounded queue absorbs
    bursts and a dedicated thread writes exact payload text to a persistent
    spool outside PostgreSQL. Files are intentionally plain NDJSON in this
    first phase so recovery and later Parquet conversion remain simple.
    """

    _STOP = object()

    def __init__(
        self,
        root: Path,
        *,
        queue_size: int = 100_000,
        rotate_bytes: int = 256 * 1024 * 1024,
        flush_every: int = 1_000,
    ) -> None:
        self.root = Path(root)
        self.rotate_bytes = max(1_024, int(rotate_bytes))
        self.flush_every = max(1, int(flush_every))
        self._queue: Queue[object] = Queue(maxsize=max(1, int(queue_size)))
        self._stop = Event()
        self._thread: Thread | None = None
        self._stats_lock = Lock()
        self._accepted = 0
        self._written = 0
        self._dropped = 0
        self._write_errors = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = Thread(target=self._run, name="eodhd-raw-spool", daemon=True)
        self._thread.start()

    def record(self, feed: str, payload: str, *, received_at: datetime) -> bool:
        if self._stop.is_set():
            return False
        observed = received_at.astimezone(timezone.utc) if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
        item = (str(feed), str(payload), observed)
        try:
            self._queue.put_nowait(item)
        except Full:
            with self._stats_lock:
                self._dropped += 1
                dropped = self._dropped
            if dropped == 1 or dropped % 10_000 == 0:
                logger.error("EODHD raw spool queue full; dropped=%d", dropped)
            return False
        with self._stats_lock:
            self._accepted += 1
        return True

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._queue.put(self._STOP)
        self._thread.join(timeout=15)
        if self._thread.is_alive():
            logger.error("EODHD raw spool did not stop within timeout")
        self._thread = None

    def stats(self) -> CaptureStats:
        with self._stats_lock:
            return CaptureStats(
                accepted=self._accepted,
                written=self._written,
                dropped=self._dropped,
                write_errors=self._write_errors,
            )

    def _run(self) -> None:
        handles: dict[tuple[str, str], tuple[int, object, int]] = {}
        writes_since_flush = 0
        try:
            while True:
                queued = self._queue.get()
                if queued is self._STOP:
                    break
                feed, payload, received_at = queued  # type: ignore[misc]
                try:
                    event_at = self._event_time(payload, received_at)
                    session = event_at.astimezone(NEW_YORK).date().isoformat()
                    record = json.dumps({
                        "schema_version": 1,
                        "provider": "EODHD",
                        "feed": feed,
                        "received_at": received_at.isoformat(),
                        "event_at": event_at.isoformat(),
                        "payload_raw": payload,
                    }, separators=(",", ":"), ensure_ascii=True) + "\n"
                    encoded_size = len(record.encode("utf-8"))
                    key = (session, feed)
                    part, handle, size = handles.get(key, (0, None, 0))
                    if handle is None or size + encoded_size > self.rotate_bytes:
                        if handle is not None:
                            handle.flush()
                            handle.close()
                        part += 1
                        directory = self.root / f"session_date={session}"
                        directory.mkdir(parents=True, exist_ok=True)
                        path = directory / f"feed={feed}-part-{part:05d}.ndjson"
                        handle = path.open("a", encoding="utf-8")
                        size = path.stat().st_size
                    handle.write(record)
                    handles[key] = (part, handle, size + encoded_size)
                    writes_since_flush += 1
                    with self._stats_lock:
                        self._written += 1
                    if writes_since_flush >= self.flush_every:
                        for _, open_handle, _ in handles.values():
                            open_handle.flush()
                        writes_since_flush = 0
                except Exception:
                    with self._stats_lock:
                        self._write_errors += 1
                    logger.exception("Failed to append EODHD raw stream payload")
        finally:
            for _, handle, _ in handles.values():
                try:
                    handle.flush()
                    handle.close()
                except Exception:
                    logger.exception("Failed to close EODHD raw spool file")

    @staticmethod
    def _event_time(payload: str, received_at: datetime) -> datetime:
        try:
            item = json.loads(payload)
            timestamp_ms = int(item.get("t") or 0) if isinstance(item, dict) else 0
            if timestamp_ms > 0:
                return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        except (TypeError, ValueError, json.JSONDecodeError, OSError):
            pass
        return received_at
