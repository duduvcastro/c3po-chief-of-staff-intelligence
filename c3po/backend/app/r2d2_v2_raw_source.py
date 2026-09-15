"""Bounded, read-only adapter for the existing raw spool.

No new socket, capture, subscription or per-tick event file. A proposed cursor
is returned to the collector and becomes authoritative only in its database
transaction. Limits are fail-closed and are not a capacity certification.
Already journaled input is authoritative; a tail witness protects append
continuity, not arbitrary rewriting of all historical bytes in the spool.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any

from .r2d2_v2_raw_events import MAX_RAW_RECORD_BYTES, decode_record
from .r2d2_v2_sources import (
    FileShadowSource, SourceUnavailable, _require, canonical,
)

MAX_FILES = 4096
MAX_CYCLE_BYTES = 8 * 1024 * 1024
MAX_CYCLE_EVENTS = 4096
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


class SpoolShadowSource(FileShadowSource):
    def __init__(self, root: str | Path, *, raw_root: str | Path,
                 first_session: date, calendar: Any, **kwargs: Any) -> None:
        super().__init__(root, **kwargs)
        self.raw_root = Path(os.path.abspath(raw_root))
        self.first_session = first_session
        self.calendar = calendar

    def prepare_events(self, now: datetime, cursor: dict) -> dict:
        """Freeze all retained file sizes before reading any feed's new bytes.

        Every complete record in that bounded snapshot is offered together to
        the collector's existing precedence sort. An incomplete trailing append
        defers the whole batch with a diagnostic: it could contain a stop
        concurrent with a quote in another file. Bytes after the size snapshot are not
        declared observed. No BAR coverage, gap-free feed or silent-period
        watermark is inferred from this filesystem boundary.
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
                            _require(len(sessions) <= 100, "RAW_SESSION_LIMIT")
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
            # Check the combined budget before emitting anything. Never split
            # a snapshot into quote-first and trade-later economic decisions.
            budget = 0
            for name, fd, info in handles:
                saved = previous.get(name)
                offset = saved["offset"] if saved is not None else 0
                _require(type(offset) is int and 0 <= offset <= info.st_size, "RAW_TRUNCATED_OR_CURSOR_INVALID")
                if saved is not None:
                    _require(set(saved) == {"offset", "sequence", "device", "inode", "witness"}
                             and type(saved["sequence"]) is int and saved["sequence"] >= 0,
                             "RAW_CURSOR_INVALID")
                    _require((info.st_dev, info.st_ino) == (saved["device"], saved["inode"]), "RAW_FILE_REPLACED")
                    tail = os.pread(fd, min(offset, WITNESS_BYTES), max(0, offset - WITNESS_BYTES))
                    _require(hashlib.sha256(tail).hexdigest() == saved["witness"], "RAW_APPEND_BOUNDARY_CHANGED")
                budget += info.st_size - offset
                _require(budget <= MAX_CYCLE_BYTES, "RAW_READ_BUDGET_EXCEEDED")
            proposed = {}
            raw_events = []
            for name, fd, info in handles:
                saved = previous.get(name, {})
                offset, sequence = saved.get("offset", 0), saved.get("sequence", 0)
                data = os.pread(fd, info.st_size - offset, offset)
                _require(len(data) == info.st_size - offset, "RAW_CHANGED_DURING_READ")
                end = data.rfind(b"\n") + 1
                tail_bytes = len(data) - end
                _require(tail_bytes < MAX_RAW_RECORD_BYTES, "RAW_RECORD_SIZE_LIMIT")
                _require(tail_bytes == 0, "RAW_APPEND_IN_PROGRESS")
                for line in data[:end].splitlines(keepends=True):
                    envelope = decode_record(line, relative_path=name, offset=offset,
                                             sequence=sequence, now=now, calendar=self.calendar)
                    raw_events.append({**envelope["event"],
                        **{key: envelope[key] for key in ("event_id", "source_id", "source_at", "sequence",
                            "provenance", "manifest_sha", "amendment_sha", "self_sha256")},
                        "envelope_available_at": envelope["available_at"],
                        "envelope_sha256": hashlib.sha256(canonical(envelope)).hexdigest()})
                    _require(len(raw_events) + len(events) <= MAX_CYCLE_EVENTS, "RAW_EVENT_BUDGET_EXCEEDED")
                    offset += len(line)
                    sequence += 1
                after = os.fstat(fd)
                _require(after.st_size >= info.st_size, "RAW_TRUNCATED_DURING_READ")
                # Retain exact boundary bytes from the read, or the prior
                # witness for an unchanged offset. Re-read to detect a race.
                tail = os.pread(fd, min(offset, WITNESS_BYTES), max(0, offset - WITNESS_BYTES))
                if end >= WITNESS_BYTES:
                    _require(tail == data[end-WITNESS_BYTES:end], "RAW_CHANGED_DURING_READ")
                proposed[name] = {"offset": offset, "sequence": sequence,
                                  "device": info.st_dev, "inode": info.st_ino,
                                  "witness": hashlib.sha256(tail).hexdigest()}
            next_cursor = {"files": proposed}
            raw_receipts = {event["event_id"]: event["envelope_sha256"] for event in raw_events}
            _require(not (set(raw_receipts) & {event["event_id"] for event in events}), "RAW_LEGACY_ID_COLLISION")
            return {"events": events + raw_events, "diagnostics": [], "cursor": next_cursor,
                    "raw_receipts": raw_receipts}
        except SourceUnavailable as exc:
            diagnostics = [{"code": str(exc)}]
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            diagnostics = [{"code": "RAW_SOURCE_MISSING_OR_MALFORMED"}]
        finally:
            for _, fd, _ in handles:
                os.close(fd)
        return {"events": [], "diagnostics": diagnostics, "cursor": cursor}
