"""F385-8 — live earnings round emitter (18:00 America/New_York, after the official close).

Turns one audited earnings round document (``produce_earnings``, schema V2_EARNINGS_COMPONENTS_V2, EMENDA 3 rev 3)
plus the inventory of LIVE episodes into ``V2_SHADOW_SOURCE_EVENT_V2`` envelopes of type ``EARNINGS`` /
``EARNINGS_OBSERVATION_FAILED`` for the collector's event tape, exactly as the port validates them
(``r2d2_v2_sources._metadata`` / ``_validate_event`` and ``r2d2_v2_earnings_events.validate_observation``):

* one **retained round receipt** per round; ``round_id`` = sha256 of the receipt core (never date-backfilled);
* ``round_received_at`` = the instant the round really started, required to be >= 18:00 NY of ``round_session`` AND
  strictly after the official XNYS close of that session (a non-session date is refused);
* one **observation window per instrument** = [earliest ``opened_at`` of its live episodes (NY date),
  latest ``maturity_at`` (NY date) + 15 days], the coverage the collector demands (``window_covers``);
* one **EARNINGS** envelope per fact the producer knows for the name inside that window — taken from
  ``evidence.known_events`` (calendar + scheduled history, whatever their admission-horizon classification), NOT
  from the admission-horizon ``events`` list: a fact dated inside a live episode's window but before the round
  session (discovered late) must still reach the collector, whose exit-by-event rule is about the live episode;
* ``earnings_event_id`` stable for the same fact (``ern:<instrument_key>:<event_date>``: the provider exposes no
  period key, so a rescheduled date is a NEW fact id and the old one remains in the tape — conservative by design);
* ``revision_sha256`` over {earnings_event_id, event_date, granularity, event_at} (same rule as the collector);
  ``event_at`` present only for INSTANT granularity (never produced by this provider today);
* ``at`` = the provider response's local reception (first local detection), never earlier than
  ``round_received_at``; ``available_at`` = the publication instant;
* **round commit the reader respects** (F385-8-A): invalid envelopes are quarantined first (durable before the tape
  is touched), a journal with the planned files, staged temp names and quarantine records is retained, a visible
  GUARD file the reader refuses is created before the first link and removed after the last, so the collector
  never consumes a half-published round (it sees no events and a diagnostic instead); ``recover_rounds``
  completes a crashed round only from staged bytes that hash exactly as planned, otherwise rolls it back behind
  the guard preserving corrupt bytes as evidence (A-R1), never rewrites a receipt already retained and never
  resets the quarantine count (A-R2); every file is read whole under a hard cap, never hashed by prefix (D-R1);
* **capacity counted as the reader counts** (F385-8-C): every directory entry (staging and guard included), with
  room reserved for the temps and the finals of the round, checked before any write; a name already present with
  identical bytes is not a new file (re-emission costs zero capacity); the receipt records the effective count;
* every envelope is validated BEFORE publication and an invalid one goes to an audited ``quarantine/``
  directory, never to the tape (a single invalid file would make the collector discard the whole tape);
* everything private (directories 0700, files 0600); no provider access here (step 2 wires ``produce_earnings``,
  the live-episode inventory and the schedule).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

from .r2d2_v2_producer_daily import canonical, write_private
from .r2d2_v2_producer_earnings import (AMENDMENT, AMENDMENT_SHA, REASON_EVIDENCE_INVALID, REASON_UNAVAILABLE, SCHEMA as ROUND_DOCUMENT_SCHEMA,
                                        _calendar, session_bounds)

# Mirrors of the port's constants (r2d2_v2_sources / r2d2_v2_earnings_events); the port integration test asserts equality.
EVENT_SCHEMA = "V2_SHADOW_SOURCE_EVENT_V2"
MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
SOURCE_AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
EARNINGS_POLICY_SHA = AMENDMENT_SHA  # 3319407a… (EMENDA 3 rev 3), the value validate_observation requires
MAX_EVENT_BYTES = 64 * 1024
MAX_EVENT_FILES = 4096
NEW_YORK = ZoneInfo("America/New_York")
ROUND_TARGET = time(18, 0)
WINDOW_TAIL_DAYS = 15
SOURCE_ID = "fable-eodhd-earnings-round"
EMITTER = "fable-earnings-round-emitter"
EMITTER_VERSION = "v1"
RECEIPT_SCHEMA = "V2_EARNINGS_ROUND_RECEIPT_V1"
QUARANTINE_SCHEMA = "V2_EARNINGS_ROUND_QUARANTINE_V1"
FAILED_REASONS = {REASON_UNAVAILABLE: "EARNINGS_SOURCE_UNAVAILABLE", REASON_EVIDENCE_INVALID: "EARNINGS_EVIDENCE_INVALID"}
GRANULARITIES = ("DAY", "BMO", "AMC", "INSTANT")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_INSTRUMENT = re.compile(r"US:[A-Z0-9][A-Z0-9.-]{0,19}\Z")
_META = {"schema", "manifest_sha", "amendment_sha", "source_id", "provenance", "source_at", "available_at", "sequence", "self_sha256"}
_ROUND_FIELDS = {"earnings_policy_sha", "round_id", "round_session", "round_received_at", "observation_window"}
_COMMON = {"type", "at", "available_at", "session", "instrument_key"}
_EARNINGS_FIELDS = _COMMON | _ROUND_FIELDS | {"earnings_event_id", "revision_sha256", "event_date", "granularity"}
_FAILED_FIELDS = _COMMON | _ROUND_FIELDS | {"reason"}


class RoundEmitterError(ValueError):
    """A round that cannot be emitted at all (refused before any write)."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise RoundEmitterError(code)


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _time(value: Any, code: str = "TIMESTAMP_INVALID") -> datetime:
    _require(isinstance(value, str), code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise RoundEmitterError(code) from None
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, code)
    return parsed.astimezone(timezone.utc)


def _day(value: Any, code: str = "DATE_INVALID") -> date:
    _require(isinstance(value, str), code)
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise RoundEmitterError(code) from None
    _require(parsed.isoformat() == value, code)
    return parsed


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ live episodes

@dataclass(frozen=True)
class Episode:
    instrument_key: str
    opened_at: datetime
    maturity_at: datetime

    @property
    def symbol(self) -> str:
        return self.instrument_key.split(":", 1)[1]


def episode_from(row: Mapping[str, Any]) -> Episode:
    _require(isinstance(row, Mapping), "EPISODE_NOT_OBJECT")
    key = row.get("instrument_key")
    _require(isinstance(key, str) and _INSTRUMENT.fullmatch(key) is not None, "EPISODE_INSTRUMENT_INVALID")
    assert isinstance(key, str)
    opened, maturity = _time(row.get("opened_at"), "EPISODE_CLOCK_INVALID"), _time(row.get("maturity_at"), "EPISODE_CLOCK_INVALID")
    _require(opened < maturity, "EPISODE_MATURITY_NOT_AFTER_OPEN")
    return Episode(key, opened, maturity)


def read_episodes(path: Path) -> list[Episode]:
    """The live-episode inventory handed to the round: a JSON list of {instrument_key, opened_at, maturity_at}."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RoundEmitterError("EPISODES_UNREADABLE") from error
    _require(isinstance(rows, list), "EPISODES_NOT_A_LIST")
    return [episode_from(row) for row in rows]


def observation_windows(episodes: Sequence[Episode]) -> dict[str, list[str]]:
    """Per instrument: [earliest opened_at (NY date), latest maturity_at (NY date) + 15 days] — what window_covers needs."""
    windows: dict[str, tuple[date, date]] = {}
    for episode in episodes:
        start = episode.opened_at.astimezone(NEW_YORK).date()
        end = episode.maturity_at.astimezone(NEW_YORK).date() + timedelta(days=WINDOW_TAIL_DAYS)
        current = windows.get(episode.instrument_key)
        windows[episode.instrument_key] = (min(start, current[0]) if current else start, max(end, current[1]) if current else end)
    return {key: [value[0].isoformat(), value[1].isoformat()] for key, value in sorted(windows.items())}


# ------------------------------------------------------------------ round receipt

def _calendar_block(document: Mapping[str, Any]) -> Mapping[str, Any]:
    block = document.get("calendar")
    return block if isinstance(block, Mapping) else {}


def _round_producer(document: Mapping[str, Any]) -> str | None:
    symbols = document.get("symbols")
    if not isinstance(symbols, Mapping) or not symbols:
        return None
    first = next(iter(symbols.values()))
    policy = first.get("policy") if isinstance(first, Mapping) else None
    producer = policy.get("producer") if isinstance(policy, Mapping) else None
    return producer if isinstance(producer, str) else None


def official_close(session: date) -> datetime:
    calendar = _calendar()
    _require(calendar.is_session(session.isoformat()), "ROUND_SESSION_NOT_A_SESSION")
    return session_bounds(session)[1].astimezone(timezone.utc)


def build_receipt(document: Mapping[str, Any], episodes: Sequence[Episode], *, published_at: datetime) -> dict[str, Any]:
    """The retained receipt of one round; ``round_id`` = sha256 of its core (everything known before publication)."""
    _require(isinstance(document, Mapping) and document.get("schema") == ROUND_DOCUMENT_SCHEMA, "ROUND_DOCUMENT_SCHEMA")
    _require(document.get("amendment") == AMENDMENT and document.get("amendment_sha") == EARNINGS_POLICY_SHA, "ROUND_DOCUMENT_POLICY")
    _require(isinstance(document.get("symbols"), Mapping), "ROUND_DOCUMENT_SYMBOLS")
    round_session = _day(document.get("session_date"), "ROUND_SESSION_INVALID")
    round_block = document.get("round")
    _require(isinstance(round_block, Mapping), "ROUND_BLOCK_MISSING")
    assert isinstance(round_block, Mapping)
    received = _time(round_block.get("executed_at"), "ROUND_RECEIVED_AT_INVALID")
    target = datetime.combine(round_session, ROUND_TARGET, NEW_YORK).astimezone(timezone.utc)
    close = official_close(round_session)
    _require(received >= target, "ROUND_BEFORE_18_00_NY")
    _require(received > close, "ROUND_NOT_AFTER_OFFICIAL_CLOSE")
    published = published_at.astimezone(timezone.utc)
    _require(published >= received, "PUBLISHED_BEFORE_ROUND")
    calendar_block = _calendar_block(document)
    calendar_sha = calendar_block.get("payload_sha256")
    _require(isinstance(calendar_sha, str) and _HASH.fullmatch(calendar_sha) is not None, "ROUND_CALENDAR_SHA_INVALID")
    windows = observation_windows(episodes)
    core = {
        "schema": RECEIPT_SCHEMA, "emitter": EMITTER, "emitter_version": EMITTER_VERSION,
        "round_session": round_session.isoformat(), "round_target": "18:00 America/New_York after the official close",
        "round_received_at": _iso(received), "official_close": _iso(close), "published_at": _iso(published),
        "earnings_policy_sha": EARNINGS_POLICY_SHA, "amendment": AMENDMENT,
        "document_sha256": sha256_hex(canonical(document)), "calendar_payload_sha256": calendar_sha,
        "producer": _round_producer(document),
        "symbols_in_round": sorted(document["symbols"]), "live_episodes": len(episodes),
        "instruments": sorted(windows), "observation_windows": windows,
    }
    return {**core, "round_id": sha256_hex(canonical(core))}


# ------------------------------------------------------------------ events

def revision_sha256(event: Mapping[str, Any]) -> str:
    facts = {key: event.get(key) for key in ("earnings_event_id", "event_date", "granularity", "event_at")}
    if facts["event_at"] is not None:
        facts["event_at"] = _iso(_time(facts["event_at"]))
    return sha256_hex(canonical(facts))


def earnings_event_id(instrument_key: str, event_date: str) -> str:
    return f"ern:{instrument_key}:{event_date}"


def _component_failure(component: Mapping[str, Any] | None) -> str | None:
    if component is None:
        return "EARNINGS_SOURCE_UNAVAILABLE"  # the round never consulted this name: nothing observed for its episodes
    reasons = component.get("exclusion", {}).get("reasons", []) if isinstance(component.get("exclusion"), Mapping) else []
    for producer_reason, failure in FAILED_REASONS.items():
        if producer_reason in reasons:
            return failure
    return None


def _known_facts(component: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Every fact the producer knows for the name (``evidence.known_events``: calendar + scheduled history, with
    their classification), not only the ones inside the admission horizon: an event dated inside a live episode's
    window but before the round session must still reach the collector. A component without the list is a
    producer defect and refuses the whole round before any write."""
    evidence = component.get("evidence")
    known = evidence.get("known_events") if isinstance(evidence, Mapping) else None
    _require(isinstance(known, list) and all(isinstance(item, Mapping) for item in known), "COMPONENT_KNOWN_EVENTS_MISSING")
    assert isinstance(known, list)
    return known


def build_events(document: Mapping[str, Any], episodes: Sequence[Episode], receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One envelope per live-episode fact: EARNINGS per known event (``_known_facts``) inside the instrument's window,
    or ONE EARNINGS_OBSERVATION_FAILED per instrument whose observation failed. Clean instruments emit nothing (the
    receipt records them). Envelopes are complete but NOT yet validated: ``validate_envelope`` decides tape or quarantine."""
    windows = receipt["observation_windows"]
    round_session, round_received_at, round_id = receipt["round_session"], receipt["round_received_at"], receipt["round_id"]
    published_at = receipt["published_at"]
    provenance = {"producer": EMITTER, "version": EMITTER_VERSION, "payload_sha256": receipt["document_sha256"]}
    calendar_block = _calendar_block(document)
    envelopes: list[dict[str, Any]] = []
    sequence = 0

    def envelope(event: dict[str, Any], source_at: str) -> dict[str, Any]:
        nonlocal sequence
        body = {"schema": EVENT_SCHEMA, "manifest_sha": MANIFEST_SHA, "amendment_sha": SOURCE_AMENDMENT_SHA, "source_id": SOURCE_ID,
                "provenance": provenance, "source_at": source_at, "available_at": published_at, "sequence": sequence,
                "event_id": f"earn-{round_session}-{round_id[:12]}-{sequence:04d}", "event": event}
        sequence += 1
        return {**body, "self_sha256": sha256_hex(canonical(body))}

    for instrument in receipt["instruments"]:
        symbol = instrument.split(":", 1)[1]
        component = document["symbols"].get(symbol)
        window = windows[instrument]
        base = {"at": None, "available_at": published_at, "session": round_session, "instrument_key": instrument,
                "earnings_policy_sha": EARNINGS_POLICY_SHA, "round_id": round_id, "round_session": round_session,
                "round_received_at": round_received_at, "observation_window": window}
        failure = _component_failure(component)
        if failure is not None:
            at = (component or {}).get("available_at") or calendar_block.get("received_at") or round_received_at
            envelopes.append(envelope({**base, "type": "EARNINGS_OBSERVATION_FAILED", "at": at, "reason": failure},
                                      source_at=(component or {}).get("source_at") or at))
            continue
        assert component is not None
        for item in _known_facts(component):
            event_date = str(item.get("event_date"))
            if not (window[0] <= event_date <= window[1]):
                continue  # outside every live episode of this instrument: not an observation for the tape
            fact = {**base, "type": "EARNINGS", "at": item.get("available_at"), "earnings_event_id": earnings_event_id(instrument, event_date),
                    "event_date": event_date, "granularity": item.get("granularity")}
            if item.get("granularity") == "INSTANT":
                fact["event_at"] = item.get("event_at")
            fact["revision_sha256"] = revision_sha256(fact)
            envelopes.append(envelope(fact, source_at=component.get("source_at") or str(fact["at"])))
    return envelopes


# ------------------------------------------------------------------ validation (mirror of the port, run BEFORE publishing)

def validate_envelope(envelope: Mapping[str, Any], *, now: datetime) -> None:
    """The port's envelope + EARNINGS/FAILED observation rules, applied by the producer before anything reaches the tape."""
    through = now.astimezone(timezone.utc)
    _require(isinstance(envelope, Mapping) and set(envelope) == _META | {"event_id", "event"}, "ENVELOPE_FIELDS")
    _require(envelope.get("schema") == EVENT_SCHEMA, "SCHEMA_MISMATCH")
    _require(envelope.get("manifest_sha") == MANIFEST_SHA and envelope.get("amendment_sha") == SOURCE_AMENDMENT_SHA, "MANIFEST_OR_AMENDMENT_MISMATCH")
    _require(isinstance(envelope.get("source_id"), str) and _TOKEN.fullmatch(envelope["source_id"]) is not None, "SOURCE_ID_INVALID")
    _require(type(envelope.get("sequence")) is int and envelope["sequence"] >= 0, "SEQUENCE_INVALID")
    provenance = envelope.get("provenance")
    _require(isinstance(provenance, Mapping) and set(provenance) == {"producer", "version", "payload_sha256"}, "PROVENANCE_MISSING")
    assert isinstance(provenance, Mapping)
    _require(all(isinstance(provenance[k], str) and _TOKEN.fullmatch(provenance[k]) for k in ("producer", "version"))
             and isinstance(provenance["payload_sha256"], str) and _HASH.fullmatch(provenance["payload_sha256"]) is not None, "PROVENANCE_INVALID")
    identity = envelope.get("event_id")
    _require(isinstance(identity, str) and _TOKEN.fullmatch(identity) is not None, "EVENT_ID_INVALID")
    digest = sha256_hex(canonical({k: v for k, v in envelope.items() if k != "self_sha256"}))
    _require(envelope.get("self_sha256") == digest, "ENVELOPE_HASH_MISMATCH")
    source_at, available_at = _time(envelope.get("source_at")), _time(envelope.get("available_at"))
    _require(source_at <= available_at <= through, "SOURCE_FUTURE_OR_REVERSED")
    _require(len(canonical(envelope)) <= MAX_EVENT_BYTES, "EVENT_SIZE_LIMIT")
    event = envelope["event"]
    _require(isinstance(event, Mapping), "EVENT_MISSING")
    kind = event.get("type")
    _require(kind in ("EARNINGS", "EARNINGS_OBSERVATION_FAILED"), "EVENT_KIND")
    required = _EARNINGS_FIELDS if kind == "EARNINGS" else _FAILED_FIELDS
    optional = {"event_at"} if kind == "EARNINGS" else set()
    _require(required <= set(event) <= required | optional, "EVENT_KIND_OR_FIELDS")
    _require(isinstance(event["instrument_key"], str) and _INSTRUMENT.fullmatch(event["instrument_key"]) is not None, "EVENT_INSTRUMENT_INVALID")
    at, available = _time(event["at"]), _time(event["available_at"])
    _require(at <= available <= available_at, "EVENT_FUTURE_OR_REVERSED")
    _require(_day(event["session"], "EVENT_SESSION_INVALID") == _day(event["round_session"], "EVENT_SESSION_INVALID"), "EVENT_SESSION_INVALID")
    _require(event.get("earnings_policy_sha") == EARNINGS_POLICY_SHA, "EARNINGS_POLICY_SHA")
    _require(isinstance(event.get("round_id"), str) and _HASH.fullmatch(event["round_id"]) is not None, "ROUND_ID_INVALID")
    received = _time(event["round_received_at"])
    _require(received <= at, "AT_BEFORE_ROUND")
    target = datetime.combine(_day(event["round_session"]), ROUND_TARGET, NEW_YORK).astimezone(timezone.utc)
    _require(received >= target, "ROUND_BEFORE_18_00_NY")
    window = event.get("observation_window")
    _require(isinstance(window, list) and len(window) == 2, "OBSERVATION_WINDOW_INVALID")
    assert isinstance(window, list)
    _require(_day(window[0]) <= _day(window[1]), "OBSERVATION_WINDOW_INVALID")
    if kind == "EARNINGS_OBSERVATION_FAILED":
        _require(event.get("reason") in set(FAILED_REASONS.values()), "FAILURE_REASON_INVALID")
        return
    _require(isinstance(event.get("earnings_event_id"), str) and _TOKEN.fullmatch(event["earnings_event_id"]) is not None, "EARNINGS_EVENT_ID_INVALID")
    granularity = event.get("granularity")
    _require(granularity in GRANULARITIES, "GRANULARITY_INVALID")
    _require(("event_at" in event) == (granularity == "INSTANT"), "EVENT_AT_ONLY_FOR_INSTANT")
    if granularity == "INSTANT":
        _time(event["event_at"], "EVENT_AT_INVALID")
    event_date = _day(event.get("event_date"), "EVENT_DATE_INVALID")
    _require(_day(window[0]) <= event_date <= _day(window[1]), "EVENT_OUTSIDE_WINDOW")
    _require(event.get("revision_sha256") == revision_sha256(event), "REVISION_SHA_MISMATCH")


# ------------------------------------------------------------------ descriptor-anchored directories (no symlink traversal)

READ_LIMIT_BYTES = 64 * 1024 * 1024  # hard cap for any file this module reads whole (quarantine records wrap oversized envelopes)


def _open_tree(path: Path) -> int:
    """Walk anchored descriptors from ``/``: every component is opened with O_NOFOLLOW, so a symlink anywhere in the
    path (ancestors included) is refused instead of followed — the same discipline as the collector's reader."""
    resolved = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in resolved.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    info = os.stat(path, follow_symlinks=False)
    _require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o077 == 0, "DIRECTORY_NOT_PRIVATE")


def _open_private_dir(path: Path) -> int:
    fd = _open_tree(path)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) & 0o077 == 0, "DIRECTORY_NOT_PRIVATE")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _fsync_fd(fd: int) -> None:
    os.fsync(fd)


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_at(dir_fd: int, name: str, data: bytes) -> None:
    """Create a private regular file under the descriptor (never over an existing one, never through a symlink)."""
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _read_at(dir_fd: int, name: str, limit: int | None = None) -> bytes:
    """Read a regular file COMPLETELY through the descriptor: the size is checked against the limit before reading,
    the bytes read must equal that size and the file identity must not change during the read. Never a prefix, never
    a silently truncated read (F385-8 D-R1): an oversized file is refused, not hashed partially."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        _require(stat.S_ISREG(before.st_mode), "NOT_A_REGULAR_FILE")
        cap = READ_LIMIT_BYTES if limit is None else limit  # module constant read at call time (patchable in tests)
        _require(before.st_size <= cap, "FILE_TOO_LARGE")
        data = handle.read(before.st_size + 1)
        after = os.fstat(handle.fileno())
        _require(len(data) == before.st_size and _identity(before) == _identity(after), "FILE_CHANGED_DURING_READ")
        return data


def _exists_at(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _unlink_at(dir_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass


def _tape_entries(dir_fd: int) -> list[str]:
    """Every directory entry, exactly what the collector counts against MAX_EVENT_FILES (staging and guards included)."""
    return sorted(os.listdir(dir_fd))


def _visible_events(entries: Sequence[str]) -> list[str]:
    return [name for name in entries if not name.startswith(".") and name.endswith(".json") and not name.startswith(GUARD_PREFIX)]


# ------------------------------------------------------------------ round commit: guard + journal, atomic publication, recovery

GUARD_PREFIX = "ROUND-COMMIT-"
GUARD_SCHEMA = "V2_EARNINGS_ROUND_COMMIT_GUARD_V1"
JOURNAL_SCHEMA = "V2_EARNINGS_ROUND_JOURNAL_V1"
JOURNAL_SUFFIX = ".journal.json"
RECOVERY_DIR = "recovery"


def _guard_name(round_id: str) -> str:
    return f"{GUARD_PREFIX}{round_id[:16]}.json"


def pending_rounds(root: Path) -> list[str]:
    """Journals of rounds that did not reach the end of their commit (crash between quarantine/guard and journal removal)."""
    rounds_dir = root / "rounds"
    if not rounds_dir.is_dir():
        return []
    return sorted(name for name in os.listdir(rounds_dir) if name.endswith(JOURNAL_SUFFIX) and not name.startswith("."))


def _retained_path(rounds_dir: Path, receipt: Mapping[str, Any]) -> Path:
    return rounds_dir / f"{receipt['round_session']}.{receipt['round_id']}.json"


def _retain(rounds_dir: Path, receipt: Mapping[str, Any], *, commit: str, files: Sequence[Mapping[str, Any]], quarantined: Sequence[Mapping[str, Any]],
            events_after: int, now: datetime, note: str | None = None, recovery: Mapping[str, Any] | None = None) -> Path:
    retained = {**receipt, "commit": commit, "published": [dict(item) for item in files], "published_count": len(files),
                "new_files": sum(1 for item in files if item.get("state") == "new"),
                "quarantined": [dict(item) for item in quarantined], "quarantined_count": len(quarantined),
                "events_in_tape_after": events_after, "retained_at": _iso(now)}
    if note:
        retained["note"] = note
    if recovery:
        retained["recovery"] = dict(recovery)
    path = _retained_path(rounds_dir, receipt)
    write_private(path, canonical(retained))
    return path


def _write_quarantine(quarantine_dir: Path, receipt: Mapping[str, Any], quarantined: Sequence[Mapping[str, Any]], *, now: datetime) -> list[dict[str, Any]]:
    """Quarantine records are durable BEFORE the tape is touched (A-R2): a crash anywhere later never loses a rejection.
    Re-writing the same record is idempotent (same name, same bytes)."""
    files: list[dict[str, Any]] = []
    if not quarantined:
        return files
    _private_dir(quarantine_dir)
    for item in quarantined:
        name = f"{item['event_id']}.{item['sha256']}.json"
        record = canonical({"schema": QUARANTINE_SCHEMA, "round_id": receipt["round_id"], "quarantined_at": item.get("quarantined_at") or _iso(now),
                            "code": item["code"], "envelope": item["envelope"]})
        target = quarantine_dir / name
        if target.exists():
            _require(target.read_bytes() == record, "QUARANTINE_RECORD_COLLISION")
        else:
            write_private(target, record)
        files.append({"file": name, "code": item["code"], "sha256": sha256_hex(record)})
    return files


def publish_round(root: Path, receipt: Mapping[str, Any], envelopes: Sequence[Mapping[str, Any]], *, now: datetime) -> dict[str, Any]:
    """Validate every envelope, then commit the round to ``events/`` as a unit the collector cannot read half-way:

    1. invalid envelopes go to the audited quarantine FIRST (durable before anything touches the tape);
    2. capacity is checked the way the reader counts (every directory entry, staging and guard included, with room for
       the temps AND the finals of this round) before any write; names already present with identical bytes are not
       new files, so re-emitting a round costs zero capacity;
    3. a journal (round receipt core + planned files + staged temp names + quarantine records) is retained in ``rounds/``;
    4. a GUARD file — a visible ``.json`` the reader refuses — is created BEFORE the first link, so while the round is
       between links (or after a crash) the reader returns no events and a diagnostic, never a partial round;
    5. the envelopes are staged hidden, linked one by one, the directory is fsynced, temps and the guard are removed;
    6. the retained receipt is written and the journal removed. A crash anywhere leaves the journal (and possibly the
       guard) behind: ``recover_rounds`` completes the round from intact staged bytes, or rolls it back preserving any
       corrupt bytes as evidence, and never rewrites a receipt that is already retained."""
    events_dir, rounds_dir, quarantine_dir = root / "events", root / "rounds", root / "quarantine" / str(receipt["round_session"])
    for directory in (root, events_dir, rounds_dir):
        _private_dir(directory)
    _require(not pending_rounds(root), "PENDING_ROUND_REQUIRES_RECOVERY")
    valid: list[tuple[str, bytes, str]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for envelope in envelopes:
        data = canonical(envelope)
        try:
            validate_envelope(envelope, now=now)
        except RoundEmitterError as error:
            quarantined.append({"event_id": envelope.get("event_id"), "sha256": sha256_hex(data), "code": str(error), "envelope": envelope, "quarantined_at": _iso(now)})
            continue
        name = f"{envelope['event_id']}.{envelope['self_sha256']}.json"
        if name not in seen:  # the same envelope twice in one round is one file (its name carries its hash)
            seen.add(name)
            valid.append((name, data, sha256_hex(data)))
    quarantine_files = _write_quarantine(quarantine_dir, receipt, quarantined, now=now)
    events_fd = _open_private_dir(events_dir)
    try:
        entries = _tape_entries(events_fd)
        _require(not any(name.startswith(GUARD_PREFIX) for name in entries), "PENDING_ROUND_REQUIRES_RECOVERY")
        present = set(_visible_events(entries))
        files: list[dict[str, Any]] = []
        new: list[tuple[str, bytes, str]] = []
        for name, data, digest in valid:
            if name in present:
                _require(_read_at(events_fd, name, MAX_EVENT_BYTES) == data, "EVENT_RECEIPT_COLLISION")  # same name ⇒ same bytes (hash in the name)
                files.append({"file": name, "sha256": digest, "state": "already_present"})
            else:
                new.append((name, data, digest))
                files.append({"file": name, "sha256": digest, "state": "new"})
        # the reader counts every entry: existing + temps + finals + guard must never exceed the limit at any instant
        _require(len(entries) + 2 * len(new) + (1 if new else 0) <= MAX_EVENT_FILES, "EVENT_FILE_LIMIT")
        journal_path = None
        if new:
            guard = _guard_name(receipt["round_id"])
            planned = [{"name": name, "sha256": digest, "temp": ".stage-" + uuid4().hex + ".tmp"} for name, _, digest in new]
            journal = {"schema": JOURNAL_SCHEMA, "round_id": receipt["round_id"], "round_session": receipt["round_session"], "guard": guard,
                       "files": planned, "receipt": dict(receipt), "published": files, "quarantined": quarantine_files, "started_at": _iso(now)}
            journal_path = rounds_dir / f"{receipt['round_session']}.{receipt['round_id']}{JOURNAL_SUFFIX}"
            write_private(journal_path, canonical(journal))
            _write_at(events_fd, guard, canonical({"schema": GUARD_SCHEMA, "round_id": receipt["round_id"], "round_session": receipt["round_session"],
                                                     "files": [item["name"] for item in planned], "started_at": _iso(now)}))
            _fsync_fd(events_fd)
            staged: list[str] = []
            for item, (_, data, _) in zip(planned, new):
                _write_at(events_fd, item["temp"], data)
                staged.append(item["temp"])
            for item in planned:
                try:
                    os.link(item["temp"], item["name"], src_dir_fd=events_fd, dst_dir_fd=events_fd)
                except FileExistsError:
                    _require(sha256_hex(_read_at(events_fd, item["name"], MAX_EVENT_BYTES)) == item["sha256"], "EVENT_RECEIPT_COLLISION")
            _fsync_fd(events_fd)
            for temp in staged:
                _unlink_at(events_fd, temp)
            _unlink_at(events_fd, guard)
            _fsync_fd(events_fd)
            commit = "complete"
        else:
            commit = "already_present"
        events_after = len(_visible_events(_tape_entries(events_fd)))
        receipt_path = _retain(rounds_dir, receipt, commit=commit, files=files, quarantined=quarantine_files, events_after=events_after, now=now)
        if journal_path is not None:
            journal_path.unlink()
            _fsync_dir(rounds_dir)
    finally:
        os.close(events_fd)
    return {"round_id": receipt["round_id"], "round_session": receipt["round_session"], "published": len(files), "new_files": len(new),
            "quarantined": len(quarantined), "receipt": str(receipt_path), "events_dir": str(events_dir),
            "quarantine_dir": str(quarantine_dir) if quarantined else None, "commit": commit}


def _load_journal(path: Path) -> dict[str, Any]:
    try:
        journal = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise RoundEmitterError("JOURNAL_UNREADABLE") from error
    _require(isinstance(journal, dict) and journal.get("schema") == JOURNAL_SCHEMA and isinstance(journal.get("files"), list)
             and isinstance(journal.get("receipt"), dict), "JOURNAL_INVALID")
    return journal


def _quarantine_present(root: Path, receipt: Mapping[str, Any], planned: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """The quarantine records the journal planned: those durable on disk (with their bytes re-hashed) and those missing."""
    folder = root / "quarantine" / str(receipt["round_session"])
    present: list[dict[str, Any]] = []
    missing: list[str] = []
    for item in planned:
        path = folder / str(item.get("file"))
        if path.is_file() and not path.is_symlink():
            present.append({"file": item["file"], "code": item.get("code"), "sha256": sha256_hex(path.read_bytes())})
        else:
            missing.append(str(item.get("file")))
    return present, missing


def recover_rounds(root: Path, *, now: datetime) -> list[dict[str, Any]]:
    """Finish or undo every round whose journal survived a crash (F385-8 A, A-R1, A-R2):

    * a receipt already retained for the round is never rewritten: only leftovers (temps, guard) are removed;
    * completion links the staged bytes that are still missing, only if every staged file hashes exactly as planned;
    * a staged (or linked) file whose bytes do not match — truncated, corrupt — is never accepted: it is MOVED to
      ``rounds/recovery/<round_id>/`` as evidence (hash observed vs expected recorded), the round is rolled back
      behind the guard, and the tape is released;
    * quarantine records planned by the journal are checked on disk and listed in the receipt (never reset to zero).
    The guard is removed only at the end, so the reader never sees a partial round. Each outcome leaves a receipt."""
    outcomes: list[dict[str, Any]] = []
    rounds_dir, events_dir = root / "rounds", root / "events"
    for journal_name in pending_rounds(root):
        journal_path = rounds_dir / journal_name
        journal = _load_journal(journal_path)
        receipt = journal["receipt"]
        round_id = str(receipt["round_id"])
        retained_path = _retained_path(rounds_dir, receipt)
        quarantine_present, quarantine_missing = _quarantine_present(root, receipt, journal.get("quarantined") or [])
        events_fd = _open_private_dir(events_dir)
        try:
            if retained_path.is_file():
                # crash after the receipt was retained: the round is complete; never rewrite the receipt (A-R2)
                for item in journal["files"]:
                    _unlink_at(events_fd, item["temp"])
                _unlink_at(events_fd, str(journal.get("guard") or _guard_name(round_id)))
                _fsync_fd(events_fd)
                commit, note, missing, corrupt = "already_retained", None, [], []
            else:
                missing, corrupt = [], []
                linkable: list[Mapping[str, Any]] = []
                for item in journal["files"]:
                    for kind, entry in (("final", item["name"]), ("temp", item["temp"])):
                        if not _exists_at(events_fd, entry):
                            continue
                        try:
                            observed = sha256_hex(_read_at(events_fd, entry, MAX_EVENT_BYTES))
                        except RoundEmitterError as error:
                            observed = f"unreadable:{error}"
                        if observed != item["sha256"]:
                            corrupt.append({"kind": kind, "entry": entry, "name": item["name"], "expected_sha256": item["sha256"], "observed": observed})
                    if not _exists_at(events_fd, item["name"]) and not _exists_at(events_fd, item["temp"]):
                        missing.append(item["name"])
                    elif not _exists_at(events_fd, item["name"]):
                        linkable.append(item)
                if corrupt or missing:
                    # controlled, audited rollback: corrupt bytes are preserved as evidence, never accepted into the tape
                    evidence_dir = rounds_dir / RECOVERY_DIR / round_id
                    if corrupt:
                        _private_dir(rounds_dir / RECOVERY_DIR)
                        _private_dir(evidence_dir)
                        evidence_fd = _open_private_dir(evidence_dir)
                        try:
                            for item in corrupt:
                                target = f"{item['kind']}-{item['entry'].lstrip('.')}"
                                os.rename(item["entry"], target, src_dir_fd=events_fd, dst_dir_fd=evidence_fd)
                                item["evidence"] = str(evidence_dir / target)
                            _fsync_fd(evidence_fd)
                        finally:
                            os.close(evidence_fd)
                    for item in journal["files"]:
                        _unlink_at(events_fd, item["name"])
                    commit = "rolled_back"
                    note = "; ".join(filter(None, ["staged bytes missing for: " + ", ".join(missing) if missing else "",
                                                   "corrupt bytes preserved as evidence for: " + ", ".join(sorted({c["name"] for c in corrupt})) if corrupt else ""]))
                else:
                    for item in linkable:
                        os.link(item["temp"], item["name"], src_dir_fd=events_fd, dst_dir_fd=events_fd)
                    commit, note = "recovered", None
                _fsync_fd(events_fd)
                for item in journal["files"]:
                    _unlink_at(events_fd, item["temp"])
                _unlink_at(events_fd, str(journal.get("guard") or _guard_name(round_id)))
                _fsync_fd(events_fd)
            events_after = len(_visible_events(_tape_entries(events_fd)))
        finally:
            os.close(events_fd)
        recovery = {"missing": missing, "corrupt": corrupt, "quarantine_missing": quarantine_missing, "recovered_at": _iso(now)}
        if commit == "already_retained":
            receipt_path = retained_path
        else:
            published = [dict(item) for item in journal.get("published", [])] if commit == "recovered" else []
            if quarantine_missing:
                note = "; ".join(filter(None, [note, "quarantine records missing on disk: " + ", ".join(quarantine_missing)]))
            receipt_path = _retain(rounds_dir, receipt, commit=commit, files=published, quarantined=quarantine_present, events_after=events_after,
                                   now=now, note=note, recovery=recovery)
        journal_path.unlink()
        _fsync_dir(rounds_dir)
        outcomes.append({"round_id": round_id, "round_session": receipt["round_session"], "commit": commit, "receipt": str(receipt_path),
                         "missing": missing, "corrupt": [c["name"] for c in corrupt], "quarantine_missing": quarantine_missing})
    return outcomes


def emit_round(document: Mapping[str, Any], episodes: Sequence[Episode], root: Path, *, now: datetime) -> dict[str, Any]:
    """Receipt → envelopes → validation → guarded atomic publication → retained receipt. No provider access."""
    receipt = build_receipt(document, episodes, published_at=now)
    envelopes = build_events(document, episodes, receipt)
    return publish_round(root, receipt, envelopes, now=now)
