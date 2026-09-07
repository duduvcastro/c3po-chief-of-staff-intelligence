"""F385-8 step 2 — the live earnings round runner: inventory of live episodes, the 18:00 NY round (provider query
through the audited producer), publication through the emitter, the quarantine procedure and the CLI.

Schedule: one run per official XNYS session, at or after 18:00 America/New_York, started by an external timer on
the producer host (cron with ``TZ=America/New_York``, e.g. ``5 18 * * 1-5``), never by the collector's worker. The
runner refuses to start before 18:00 NY or at/before the official close of the target session (both rules hold on
early-close days), and refuses a second round for the same session unless ``repeat`` is explicit (a retry after a
partial failure; the run receipt lists the earlier rounds). The intended session is the New York date of the start
instant (``auto``) or an explicit ``--session-date`` for a delayed run: "a delayed scheduled round retains its
intended session and real receipt" (port rule).

Inventory: the collector's persisted state (``r2d2_v2_shadow_epochs``, read through the same store the worker uses,
integrity-checked by it): ``state.ledger.research`` records with status ``OPEN`` — both research arms, exactly the
episodes the collector applies ``EARNINGS`` / ``EARNINGS_OBSERVATION_FAILED`` events to — or an explicit JSON
inventory file (tests, manual runs). Instrument keys ``NYSE:``/``NASDAQ:``/``US:`` are normalized to ``US:`` as the
collector does. A DIAGNOSTIC epoch has no ledger and therefore no episodes.

The round: the producer is asked for the live names only (``produce_earnings`` with ``symbols=()``, ``live_symbols``
and ``live_lookback`` = [earliest ``opened_at``, latest ``maturity_at``] as NY dates; the producer widens the calendar
query by 15 days after it); the document it wrote is read back from disk, hash-checked and handed to the emitter,
which validates every envelope before publication. A run receipt (``rounds/<session>.<round_id>.run.json``) binds
the inventory (bytes hashed), the document (sha256) and the retained round receipt.

Quarantine: envelopes refused by ``validate_envelope`` never reach the tape. ``quarantine_inventory`` lists them
(session, code, hashes; read-only, allowed while the producers are OFF) and ``purge_quarantined`` removes ONE file,
only from ``quarantine/<session>/``, only after a signed purge receipt (who, why, sha256 of the removed bytes) is
durable next to it. Nothing is ever moved into ``events/`` by hand: a defect in the emitter is fixed and a new round
is run. See ``c3po/docs/R2D2_V2_EARNINGS_ROUND_RUNBOOK.md``.

OFF by default (``C3PO_R2D2_V2_PRODUCERS_ENABLED``); the provider token never leaves the fetcher.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib
import json
import os
import re
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from .r2d2_v2_producer_daily import EodhdFetcher, Fetcher, ProducerError, canonical, write_private
from .r2d2_v2_producer_earnings import produce_earnings
from .r2d2_v2_round_emitter import (JOURNAL_SUFFIX, NEW_YORK, QUARANTINE_SCHEMA, ROUND_TARGET, Episode, RoundEmitterError, _calendar, _exists_at,
                                    _fsync_fd, _iso, _open_tree, _private_dir, _read_at, _require, _write_at, emit_round, episode_from,
                                    official_close, read_episodes, recover_rounds, sha256_hex)

INVENTORY_SCHEMA = "V2_EARNINGS_ROUND_INVENTORY_V1"
RUN_SCHEMA = "V2_EARNINGS_ROUND_RUN_V1"
PURGE_SCHEMA = "V2_EARNINGS_QUARANTINE_PURGE_V1"
SCHEDULE = "one run per official XNYS session at or after 18:00 America/New_York (external timer, e.g. cron '5 18 * * 1-5' with TZ=America/New_York)"
Clock = Callable[[], datetime]
_PREFIXES = frozenset({"US", "NYSE", "NASDAQ"})
_SESSION_NAME = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ inventory of live episodes

def normalize_instrument(key: Any) -> str:
    """``NYSE:``/``NASDAQ:``/``US:`` -> ``US:``, the collector's own normalization of instrument keys."""
    _require(isinstance(key, str), "EPISODE_INSTRUMENT_INVALID")
    assert isinstance(key, str)
    parts = key.split(":")
    _require(len(parts) == 2 and parts[0] in _PREFIXES, "EPISODE_INSTRUMENT_INVALID")
    return "US:" + parts[1]


def live_episodes_from_state(state: Mapping[str, Any]) -> list[Episode]:
    """The OPEN research records of the collector's ledger (both arms): exactly the episodes the collector applies
    earnings observations to. A DIAGNOSTIC epoch has no ledger and therefore no episodes."""
    _require(isinstance(state, Mapping), "STATE_NOT_OBJECT")
    ledger = state.get("ledger")
    if ledger is None:
        return []
    _require(isinstance(ledger, Mapping) and isinstance(ledger.get("research"), Mapping), "LEDGER_INVALID")
    assert isinstance(ledger, Mapping)
    research = ledger["research"]
    assert isinstance(research, Mapping)
    episodes: list[Episode] = []
    for key in sorted(research):
        record = research[key]
        _require(isinstance(record, Mapping), "EPISODE_NOT_OBJECT")
        assert isinstance(record, Mapping)
        if record.get("status") != "OPEN":
            continue
        episodes.append(episode_from({"instrument_key": normalize_instrument(record.get("instrument_key")),
                                      "opened_at": record.get("opened_at"), "maturity_at": record.get("maturity_at")}))
    return episodes


def inventory_from_store(reader: Any, epoch: str) -> tuple[list[Episode], dict[str, Any]]:
    """Read the persisted state through the same store the worker uses (its ``read`` verifies the state hash)."""
    saved = reader.read(epoch)
    _require(isinstance(saved, Mapping) and isinstance(saved.get("state"), Mapping), "EPOCH_NOT_FOUND")
    assert isinstance(saved, Mapping)
    source = {"kind": "store", "epoch": epoch, "state_sha": saved.get("state_sha"), "version": saved.get("version")}
    return live_episodes_from_state(saved["state"]), source


def inventory_document(episodes: Sequence[Episode], source: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema": INVENTORY_SCHEMA, "source": dict(source),
            "episodes": [{"instrument_key": e.instrument_key, "opened_at": _iso(e.opened_at), "maturity_at": _iso(e.maturity_at)} for e in episodes]}


def lookback(episodes: Sequence[Episode]) -> tuple[date, date] | None:
    """[earliest ``opened_at``, latest ``maturity_at``] as New York dates; the producer adds the 15-day tail itself."""
    if not episodes:
        return None
    return (min(e.opened_at.astimezone(NEW_YORK).date() for e in episodes), max(e.maturity_at.astimezone(NEW_YORK).date() for e in episodes))


# ------------------------------------------------------------------ the round

def target_session(now: datetime, explicit: date | None = None) -> date:
    """The intended session: explicit (a delayed run keeps its intended session) or the NY date of the start instant."""
    session = explicit or now.astimezone(NEW_YORK).date()
    _require(_calendar().is_session(session.isoformat()), "ROUND_SESSION_NOT_A_SESSION")
    return session


def round_open(session: date, now: datetime) -> None:
    """The schedule guard, applied BEFORE any provider call: at or after 18:00 NY of the session and after its official close."""
    target = datetime.combine(session, ROUND_TARGET, NEW_YORK).astimezone(timezone.utc)
    _require(now >= target, "ROUND_BEFORE_18_00_NY")
    _require(now > official_close(session), "ROUND_NOT_AFTER_OFFICIAL_CLOSE")


def previous_rounds(root: Path, session: date) -> list[str]:
    """Retained round receipts already emitted for the session (run receipts and journals of crashed rounds excluded)."""
    rounds_dir = root / "rounds"
    if not rounds_dir.is_dir():
        return []
    prefix = session.isoformat() + "."
    return sorted(name for name in os.listdir(rounds_dir)
                  if name.startswith(prefix) and name.endswith(".json") and not name.endswith(".run.json") and not name.endswith(JOURNAL_SUFFIX))


@contextmanager
def exclusive_round(root: Path) -> Iterator[None]:
    """One round process at a time per source root (F385-8-B): recovery, the repeat guard, the provider round and the
    commit all happen under an exclusive advisory lock (``rounds/.lock``, flock); a second process is refused with
    ``ROUND_LOCKED`` before any provider call. The lock lives in the open file description, so it also excludes
    threads of the same process that open the file separately."""
    _private_dir(root)
    _private_dir(root / "rounds")
    fd = os.open(root / "rounds" / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RoundEmitterError("ROUND_LOCKED") from error
        yield
    finally:
        os.close(fd)


def run_round(fetch: Fetcher, episodes: Sequence[Episode], root: Path, *, session: date | None = None, clock: Clock | None = None,
              repeat: bool = False, inventory_source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Lock -> recovery of crashed rounds -> guards -> one producer round for the live names only -> the emitter ->
    a run receipt binding inventory, document and round."""
    tick = clock or _utc
    started = tick().astimezone(timezone.utc)
    with exclusive_round(root):
        recovered = recover_rounds(root, now=started)
        day = target_session(started, session)
        round_open(day, started)
        earlier = previous_rounds(root, day)
        _require(repeat or not earlier, "ROUND_ALREADY_EMITTED_FOR_SESSION")
        symbols = sorted({episode.symbol for episode in episodes})
        window = lookback(episodes)
        document_dir = root / "documents" / day.isoformat() / ("round-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
        for directory in (root / "documents", root / "documents" / day.isoformat(), document_dir):
            _private_dir(directory)
        produced = produce_earnings(fetch, (), session_date=day, output_dir=document_dir, now=started, live_symbols=symbols, live_lookback=window)
        document_path = Path(produced["output"])
        data = document_path.read_bytes()
        _require(sha256_hex(data) == produced["sha256"], "DOCUMENT_HASH_MISMATCH")
        document = json.loads(data)
        published = tick().astimezone(timezone.utc)
        summary = emit_round(document, episodes, root, now=published)
        inventory = inventory_document(episodes, inventory_source or {"kind": "explicit"})
        run = {"schema": RUN_SCHEMA, "schedule": SCHEDULE, "round_session": day.isoformat(), "round_id": summary["round_id"],
               "started_at": _iso(started), "published_at": _iso(published), "repeat": bool(earlier), "previous_rounds": earlier,
               "recovered_before": recovered, "live_symbols": symbols,
               "live_lookback": [window[0].isoformat(), window[1].isoformat()] if window else None,
               "document": {"path": str(document_path), "sha256": produced["sha256"], "counts": produced["counts"]},
               "inventory": inventory, "inventory_sha256": sha256_hex(canonical(inventory)),
               "receipt": summary["receipt"], "commit": summary["commit"], "published": summary["published"], "new_files": summary["new_files"],
               "quarantined": summary["quarantined"]}
        run_path = root / "rounds" / (day.isoformat() + "." + summary["round_id"] + ".run.json")
        write_private(run_path, canonical(run))
    return {**summary, "run": str(run_path), "document": str(document_path), "document_sha256": produced["sha256"],
            "live_symbols": len(symbols), "started_at": _iso(started), "published_at": _iso(published), "repeat": bool(earlier),
            "recovered_before": recovered}


# ------------------------------------------------------------------ quarantine procedure

def _open_session_dir(base_fd: int, session: str) -> int:
    """The session directory opened relative to the quarantine descriptor, never through a symlink (F385-8-D)."""
    return os.open(session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=base_fd)


def quarantine_inventory(root: Path) -> list[dict[str, Any]]:
    """Read-only audit of everything the emitter refused: one line per file, with the code and the bytes' hash.
    Directories and files are reached only through descriptors opened with O_NOFOLLOW (ancestors included): a symlink
    anywhere is reported as refused, never followed."""
    items: list[dict[str, Any]] = []
    if not (root / "quarantine").is_dir():
        return items
    try:
        base_fd = _open_tree(root / "quarantine")
    except OSError as error:
        return [{"session": None, "kind": "QUARANTINE_DIRECTORY_REFUSED", "error": type(error).__name__}]
    try:
        for session in sorted(os.listdir(base_fd)):
            if session.startswith("."):
                continue
            try:
                fd = _open_session_dir(base_fd, session)
            except OSError as error:
                items.append({"session": session, "kind": "SESSION_DIRECTORY_REFUSED", "error": type(error).__name__})
                continue
            try:
                for name in sorted(os.listdir(fd)):
                    if name.startswith("."):
                        continue
                    try:
                        data = _read_at(fd, name)
                    except (OSError, RoundEmitterError) as error:
                        items.append({"session": session, "file": name, "kind": "FILE_REFUSED", "error": type(error).__name__})
                        continue
                    item: dict[str, Any] = {"session": session, "file": name, "sha256": sha256_hex(data)}
                    if name.endswith(".purge.json"):
                        items.append({**item, "kind": "PURGE_RECEIPT"})
                        continue
                    try:
                        body = json.loads(data)
                    except ValueError:
                        body = None
                    if not isinstance(body, dict) or body.get("schema") != QUARANTINE_SCHEMA or not isinstance(body.get("envelope"), dict):
                        items.append({**item, "kind": "UNREADABLE"})
                        continue
                    envelope = body["envelope"]
                    event = envelope.get("event") if isinstance(envelope.get("event"), dict) else {}
                    items.append({**item, "kind": "QUARANTINED", "code": body.get("code"), "round_id": body.get("round_id"),
                                  "quarantined_at": body.get("quarantined_at"), "event_id": envelope.get("event_id"),
                                  "instrument_key": event.get("instrument_key"), "type": event.get("type")})
            finally:
                os.close(fd)
    finally:
        os.close(base_fd)
    return items


def purge_quarantined(root: Path, session: str, name: str, *, signed_by: str, reason: str, now: datetime) -> dict[str, Any]:
    """Remove ONE quarantined file, only from ``quarantine/<session>/``, only after a signed purge receipt is durable
    next to it. Every step (read, receipt, unlink, fsync) is anchored in a descriptor of the session directory reached
    without following symlinks, so a symlinked session directory or file cannot make the purge act outside (F385-8-D)."""
    _require(bool(signed_by.strip()) and bool(reason.strip()), "PURGE_REQUIRES_SIGNER_AND_REASON")
    _require(_SESSION_NAME.fullmatch(session) is not None and "/" not in name and not name.startswith(".") and name.endswith(".json")
             and not name.endswith(".purge.json"), "PURGE_TARGET_INVALID")
    try:
        base_fd = _open_tree(root / "quarantine")
    except OSError as error:
        raise RoundEmitterError("PURGE_TARGET_NOT_IN_QUARANTINE") from error
    try:
        try:
            fd = _open_session_dir(base_fd, session)
        except OSError as error:
            raise RoundEmitterError("PURGE_TARGET_NOT_IN_QUARANTINE") from error
    finally:
        os.close(base_fd)
    try:
        try:
            data = _read_at(fd, name)
        except (OSError, RoundEmitterError) as error:
            raise RoundEmitterError("PURGE_TARGET_NOT_IN_QUARANTINE") from error
        try:
            body = json.loads(data)
        except ValueError:
            body = None
        record = body if isinstance(body, dict) else {}
        receipt = {"schema": PURGE_SCHEMA, "session": session, "file": name, "sha256": sha256_hex(data), "code": record.get("code"),
                   "round_id": record.get("round_id"), "signed_by": signed_by.strip(), "reason": reason.strip(), "purged_at": _iso(now)}
        receipt_name = name[:-len(".json")] + ".purge.json"
        _require(not _exists_at(fd, receipt_name), "PURGE_RECEIPT_EXISTS")
        _write_at(fd, receipt_name, canonical(receipt))  # durable before the removal: a crash in between leaves both, never neither
        _fsync_fd(fd)
        os.unlink(name, dir_fd=fd)
        _fsync_fd(fd)
    finally:
        os.close(fd)
    return receipt


# ------------------------------------------------------------------ CLI (OFF by default)

def _settings() -> Any:
    from .config import get_settings
    return get_settings()


def _store_reader(settings: Any) -> Any:
    """The port's ``PostgresShadowStore`` over the app's connection factory (construction opens no connection; never
    ``Database.initialize()``). The store module arrives with the port (#383/#386, merged before #385): resolved at runtime."""
    from .database import Database
    try:
        store_module = importlib.import_module(str(__package__) + ".r2d2_v2_store")
    except ImportError as error:
        raise RoundEmitterError("SHADOW_STORE_UNAVAILABLE") from error
    return store_module.PostgresShadowStore(Database(settings).connection)


def _fetcher(settings: Any) -> Fetcher:
    return EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=settings.market_data_timeout_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="private source root the collector reads (default: settings r2d2_v2_shadow_source_dir)")
    parser.add_argument("--session-date", default="auto", help="intended XNYS session (ISO) or 'auto' = New York date of the start instant")
    inventory = parser.add_mutually_exclusive_group()
    inventory.add_argument("--episodes-file", help="explicit live-episode inventory: JSON list of {instrument_key, opened_at, maturity_at}")
    inventory.add_argument("--epoch", help="read the live episodes from the collector's persisted state of this epoch")
    parser.add_argument("--repeat", action="store_true", help="allow a second round for the same session (retry after a partial failure)")
    parser.add_argument("--audit-quarantine", action="store_true", help="list the quarantine (read-only, no provider, allowed while OFF)")
    parser.add_argument("--recover", action="store_true", help="complete or roll back rounds that crashed between guard and receipt (no provider)")
    parser.add_argument("--purge-quarantine", nargs=2, metavar=("SESSION", "FILE"), help="remove ONE quarantined file after a signed purge receipt")
    parser.add_argument("--signed-by", help="who signs the purge")
    parser.add_argument("--reason", help="why the quarantined file is removed")
    args = parser.parse_args(argv)
    if args.audit_quarantine:
        root = Path(args.root) if args.root else Path(_settings().r2d2_v2_shadow_source_dir)
        print(json.dumps({"status": "AUDIT", "root": str(root), "quarantine": quarantine_inventory(root)}, sort_keys=True))
        return 0
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    settings = _settings()
    root = Path(args.root) if args.root else Path(settings.r2d2_v2_shadow_source_dir)
    try:
        if args.recover:
            with exclusive_round(root):
                outcomes = recover_rounds(root, now=_utc())
            print(json.dumps({"status": "RECOVERED", "rounds": outcomes}, sort_keys=True))
            return 0
        if args.purge_quarantine:
            session, name = args.purge_quarantine
            receipt = purge_quarantined(root, session, name, signed_by=args.signed_by or "", reason=args.reason or "", now=_utc())
            print(json.dumps({"status": "PURGED", "receipt": receipt}, sort_keys=True))
            return 0
        if args.episodes_file:
            episodes, source = read_episodes(Path(args.episodes_file)), {"kind": "file", "path": args.episodes_file}
        elif args.epoch:
            episodes, source = inventory_from_store(_store_reader(settings), args.epoch)
        else:
            parser.error("--episodes-file or --epoch is required for a round")
        intended = None if args.session_date == "auto" else date.fromisoformat(args.session_date)
        result = run_round(_fetcher(settings), episodes, root, session=intended, clock=_utc, repeat=args.repeat, inventory_source=source)
    except (RoundEmitterError, ProducerError, ValueError) as error:
        print(json.dumps({"status": "REFUSED", "code": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"status": "EMITTED", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
