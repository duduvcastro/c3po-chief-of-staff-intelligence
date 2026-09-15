"""Bounded, read-only adapter for the existing raw spool.

No new socket, capture, subscription or per-tick event file. A proposed cursor
is returned to the collector and becomes authoritative only in its database
transaction. Page targets are not a capacity certification.
Already journaled input is authoritative; a tail witness protects append
continuity, not arbitrary rewriting of all historical bytes in the spool.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from collections import Counter
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any

from .r2d2_v2_raw_events import MAX_RAW_RECORD_BYTES, inspect_record
from .r2d2_v2_sources import (
    FileShadowSource, SourceUnavailable, _require, _load_json, _time, canonical,
)

MAX_FILES = 4096
MAX_CYCLE_EVENTS = 16384
MAX_PAGES_PER_CYCLE = 16
MAX_DRAIN_SECONDS = 0.5
WITNESS_BYTES = 128
_SESSION = re.compile(r"session_date=(\d{4}-\d{2}-\d{2})\Z")
_PART = re.compile(r"feed=(quote|trade)-part-\d{5,}\.ndjson\Z")


def _open_dir(path: Path) -> int:
    """Anchor every component without following symlinks, including ancestors."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        # The existing capture inherits umask; reading does not change it.
        _require(not (os.fstat(fd).st_mode & 0o022), "RAW_DIRECTORY_WRITABLE_BY_OTHERS")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _received(data: bytes | None, now: datetime) -> datetime | None:
    if data is None:
        return None
    try:
        received = _time(_load_json(data)["received_at"])
        return received if received <= now else None
    except (SourceUnavailable, ValueError, TypeError, KeyError, OverflowError):
        return None


def _frames(fd: int, start: int, limit: int):
    """Snapshot-bounded streaming; oversized frames retain only hash and tail."""
    offset = start
    position = start
    data = bytearray()
    size = 0
    tail = b""
    sha = hashlib.sha256()
    while position < limit:
        chunk = os.pread(fd, min(64 * 1024, limit - position), position)
        _require(bool(chunk), "RAW_CHANGED_DURING_READ")
        position += len(chunk)
        for part in chunk.splitlines(keepends=True):
            size += len(part)
            sha.update(part)
            tail = (tail + part)[-WITNESS_BYTES:]
            if size <= MAX_RAW_RECORD_BYTES:
                data.extend(part)
            else:
                data.clear()
            if part.endswith(b"\n"):
                yield {"offset": offset, "bytes": size, "sha256": sha.hexdigest(),
                       "tail": tail, "data": bytes(data) if size <= MAX_RAW_RECORD_BYTES else None}
                offset += size
                data.clear()
                size = 0
                tail = b""
                sha = hashlib.sha256()
    _require(size == 0, "RAW_APPEND_IN_PROGRESS")


class SpoolShadowSource(FileShadowSource):
    def __init__(self, root: str | Path, *, raw_root: str | Path,
                 first_session: date, calendar: Any, **kwargs: Any) -> None:
        super().__init__(root, **kwargs)
        self.raw_root = Path(os.path.abspath(raw_root))
        self.first_session = first_session
        self.calendar = calendar

    def prepare_events(self, now: datetime, cursor: dict, *, snapshot: dict | None = None) -> dict:
        """Offer a contiguous prefix at a common reception horizon.

        The record budget is a page target. Equal-reception groups are atomic:
        extend through ties rather than permanently refusing an oversized group.
        This preserves per-page precedence, not global event-time ordering for
        late arrivals across pages. snapshot is ephemeral, never another cursor.
        """
        events = super().events(now)
        diagnostics = list(self.last_event_diagnostics)
        handles: list[tuple[str, int, os.stat_result]] = []
        try:
            if diagnostics:
                return {"events": [], "diagnostics": diagnostics, "cursor": cursor}
            _require(isinstance(cursor, dict) and set(cursor) <= {"files"}, "RAW_CURSOR_INVALID")
            previous = cursor.get("files", {})
            _require(isinstance(previous, dict) and len(previous) <= MAX_FILES, "RAW_CURSOR_INVALID")
            root_fd = _open_dir(self.raw_root)
            try:
                with os.scandir(root_fd) as listing:
                    sessions = []
                    for count, entry in enumerate(listing, 1):
                        _require(count <= MAX_FILES, "RAW_DIRECTORY_ENTRY_LIMIT")
                        match = _SESSION.fullmatch(entry.name)
                        if match and self.first_session <= date.fromisoformat(match[1]) <= now.date():
                            sessions.append(entry.name)
                            _require(len(sessions) <= 250, "RAW_SESSION_LIMIT")
                for session in sorted(sessions):
                    directory = os.open(session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
                    try:
                        _require(not (os.fstat(directory).st_mode & 0o022), "RAW_DIRECTORY_WRITABLE_BY_OTHERS")
                        with os.scandir(directory) as listing:
                            names = []
                            for count, entry in enumerate(listing, 1):
                                _require(count <= MAX_FILES, "RAW_DIRECTORY_ENTRY_LIMIT")
                                if _PART.fullmatch(entry.name):
                                    names.append(entry.name)
                                    _require(len(handles) + len(names) <= MAX_FILES, "RAW_FILE_LIMIT")
                        for name in sorted(names):
                            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
                            info = os.fstat(fd)
                            handles.append((session + "/" + name, fd, info))
                            _require(stat.S_ISREG(info.st_mode) and not (info.st_mode & 0o022), "RAW_FILE_INVALID")
                    finally:
                        os.close(directory)
            finally:
                os.close(root_fd)
            _require(bool(handles), "RAW_CAPTURE_NOT_OBSERVED")
            names = {name for name, _, _ in handles}
            _require(set(previous) <= names, "RAW_RETAINED_FILE_MISSING")
            if snapshot is None:
                snapshot = {name: {"size": info.st_size, "device": info.st_dev, "inode": info.st_ino}
                            for name, _, info in handles}
            _require(set(snapshot) <= names, "RAW_RETAINED_FILE_MISSING")
            handles_for_page = [(name, fd, info) for name, fd, info in handles if name in snapshot]
            previous_tails: dict[str, bytes] = {}
            pending = []
            for name, fd, info in handles_for_page:
                frozen = snapshot[name]
                _require((info.st_dev, info.st_ino) == (frozen["device"], frozen["inode"]), "RAW_FILE_REPLACED")
                _require(info.st_size >= frozen["size"], "RAW_TRUNCATED_DURING_READ")
                saved = previous.get(name)
                offset = saved["offset"] if saved is not None else 0
                _require(type(offset) is int and 0 <= offset <= frozen["size"], "RAW_TRUNCATED_OR_CURSOR_INVALID")
                previous_tails[name] = b""
                if saved is not None:
                    _require(set(saved) in ({"offset", "sequence", "device", "inode", "witness"},
                                            {"offset", "sequence", "device", "inode", "witness", "received_max"})
                             and type(saved["sequence"]) is int and saved["sequence"] >= 0,
                             "RAW_CURSOR_INVALID")
                    if saved.get("received_max") is not None:
                        _time(saved["received_max"])
                    _require((info.st_dev, info.st_ino) == (saved["device"], saved["inode"]), "RAW_FILE_REPLACED")
                    tail = os.pread(fd, min(offset, WITNESS_BYTES), max(0, offset - WITNESS_BYTES))
                    _require(hashlib.sha256(tail).hexdigest() == saved["witness"], "RAW_APPEND_BOUNDARY_CHANGED")
                    previous_tails[name] = tail
                if offset < frozen["size"]:
                    pending.append(name)
            per_file = max(1, MAX_CYCLE_EVENTS // max(1, len(pending)))
            horizons = []
            prefixes: dict[str, list[dict]] = {}
            minimum = datetime.min.replace(tzinfo=timezone.utc)
            # Capture per-file prefixes before choosing one common W. Retain
            # only metadata/hashes here; frame bytes are re-read for delivery.
            for name, fd, _ in handles_for_page:
                if name not in pending:
                    continue
                saved = previous.get(name, {})
                high = _time(saved["received_max"]) if saved.get("received_max") else minimum
                rows = []
                end = saved.get("offset", 0)
                for frame in _frames(fd, saved.get("offset", 0), snapshot[name]["size"]):
                    received = _received(frame["data"], now)
                    if received is not None:
                        high = max(high, received)
                    rows.append({"offset": frame["offset"], "sha256": frame["sha256"]})
                    end = frame["offset"] + frame["bytes"]
                    if len(rows) >= per_file:
                        break
                prefixes[name] = rows
                if end < snapshot[name]["size"]:
                    horizons.append(high)
            cutoff = min(horizons) if horizons else None  # None is +infinity.
            proposed = {}
            raw_events = []
            skipped_receipts = []
            notices = []
            delivered_count = 0
            for name, fd, info in handles_for_page:
                saved = previous.get(name, {})
                offset, sequence = saved.get("offset", 0), saved.get("sequence", 0)
                high = _time(saved["received_max"]) if saved.get("received_max") else None
                expected_tail = previous_tails[name]
                prefix = {row["offset"]: row["sha256"] for row in prefixes.get(name, [])}
                for frame in _frames(fd, offset, snapshot[name]["size"]):
                    if frame["offset"] in prefix:
                        _require(frame["sha256"] == prefix[frame["offset"]], "RAW_CHANGED_DURING_READ")
                    received = _received(frame["data"], now)
                    if cutoff is not None and received is not None and received > cutoff:
                        break
                    # Extend past the initial prefix through the cutoff, so a
                    # STOP with the same reception timestamp cannot be hidden.
                    if high is not None and received is not None and received < high:
                        notices.append({"code": "RAW_RECEIVED_AT_DECREASED", "path": name,
                                        "offset": offset, "raw_sha256": frame["sha256"]})
                    if received is not None:
                        high = max(high, received) if high is not None else received
                    if frame["data"] is None:
                        inspected = {"envelope": None, "receipt": {"path": name, "offset": offset,
                            "bytes": frame["bytes"], "raw_sha256": frame["sha256"],
                            "code": "RAW_RECORD_FRAME_INVALID", "disposition": "QUARANTINED"}}
                    else:
                        inspected = inspect_record(frame["data"], relative_path=name, offset=offset,
                                                   sequence=sequence, now=now, calendar=self.calendar)
                    envelope = inspected["envelope"]
                    if envelope is None:
                        skipped_receipts.append(inspected["receipt"])
                    else:
                        raw_events.append({**envelope["event"],
                            **{key: envelope[key] for key in ("event_id", "source_id", "source_at", "sequence",
                                "provenance", "manifest_sha", "amendment_sha", "self_sha256")},
                            "envelope_available_at": envelope["available_at"],
                            "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest()})
                        sequence += 1
                    offset += frame["bytes"]
                    delivered_count += 1
                    expected_tail = (expected_tail + frame["tail"])[-WITNESS_BYTES:]
                after = os.fstat(fd)
                _require(after.st_size >= snapshot[name]["size"], "RAW_TRUNCATED_DURING_READ")
                tail = os.pread(fd, min(offset, WITNESS_BYTES), max(0, offset - WITNESS_BYTES))
                _require(tail == expected_tail, "RAW_CHANGED_DURING_READ")
                proposed[name] = {"offset": offset, "sequence": sequence,
                                  "device": info.st_dev, "inode": info.st_ino,
                                  "witness": hashlib.sha256(tail).hexdigest(),
                                  "received_max": high.isoformat() if high is not None else None}
            next_cursor = {"files": proposed}
            raw_receipts = {event["event_id"]: event["envelope_sha256"] for event in raw_events}
            _require(not (set(raw_receipts) & {event["event_id"] for event in events}), "RAW_LEGACY_ID_COLLISION")
            page = {"cutoff_received_at": cutoff.isoformat() if cutoff is not None else None,
                    "record_count": delivered_count, "target_records": MAX_CYCLE_EVENTS,
                    "target_exceeded": delivered_count > MAX_CYCLE_EVENTS,
                    "diagnostic_counts": dict(Counter(row["code"] for row in notices)),
                    "skipped_counts": dict(Counter(row["code"] for row in skipped_receipts)),
                    "notices": notices}
            return {"events": events + raw_events, "diagnostics": [], "cursor": next_cursor,
                    "raw_receipts": raw_receipts, "skipped_receipts": skipped_receipts, "page": page,
                    "snapshot": snapshot,
                    "has_more": any(proposed[name]["offset"] < snapshot[name]["size"] for name in proposed)}
        except SourceUnavailable as exc:
            diagnostics = [{"code": str(exc)}]
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            diagnostics = [{"code": "RAW_SOURCE_MISSING_OR_MALFORMED"}]
        finally:
            for _, fd, _ in handles:
                os.close(fd)
        return {"events": [], "diagnostics": diagnostics, "cursor": cursor}
