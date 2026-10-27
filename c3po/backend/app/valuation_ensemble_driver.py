"""Host driver of the signed ensemble grade (PREREG_VALUATION_ENSEMBLE_PIT_US_V1): ONE bounded chunk, aggregates out.

``.github/workflows/valuation-ensemble-grid.yml`` runs it inside the running api container, after its own host preflight
(reboot flags, R2D2/massive services and timers, blocking ingestions, the as-filed backfill paused, disk and memory) and
under the deployment lock the remote shell holds SHARED for the whole leg. Everything it reads is pinned:

* the owner's order, ``/legacy/c3po/ops/owner-orders/<sha>.json`` (its bytes; ``execute_grade_chunk`` checks its scope);
* the instrument pin, ``/legacy/c3po/ops/valuation-ensemble/<pin sha>.json``, bound to the trust anchor the workflow
  verified on the channel (instrument commit, owner-signature and technical-GO comment ids);
* the instrument files hashed at the checkout (``/legacy``) AND as imported here: a running module whose bytes differ
  from the checkout's refuses the chunk (the image and the checkout are one revision, or nothing runs);
* the signed rev3 grid manifest, on stdin (the executor checks its digest against the prereg's constant);
* prices through ``PinnedPrices`` at the rev3 price pin (``pin_mode="explicit"``): the grid section refuses any other
  publication than its V3 sibling's.

The database session is read only (``PGOPTIONS``). The only writes are private files under
``/app/day-d-data/valuation-ensemble`` (directories 0700, files 0600, owned by this process): the executor's receipts,
a journal of the committed sections and each chunk's manifest. The journal makes an interrupted chunk lose nothing:
every section header the executor commits is journaled at once (fsync) as its manifest entry, rebuilt from the header
and the rev3 pair; the next chunk hands the journal to the executor as ``prior_entries``, and the executor verifies
every one of them against the stored artifact and the reference siblings (an entry is a reference, never a boolean).

stdout carries JSON lines with aggregates only (counts, digests, timings): never a symbol. A refusal prints a reason
code (lowercase, so never a ticker; anything else is reduced to the exception's class) and exits 2; the traceback goes
to stderr, which the workflow keeps private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import stat
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .valuation_ensemble_inputs import canonical_hash, utc
from .valuation_ensemble_persistence import FileReceiptStore
from .valuation_ensemble_pin import PREREG_COMMIT, InstrumentBinding, instrument_file_hashes


LEGACY_ROOT = Path("/legacy")
STORE_ROOT = Path("/app/day-d-data/valuation-ensemble")
ORDERS = Path("c3po/ops/owner-orders")
PINS = Path("c3po/ops/valuation-ensemble")
APP_PREFIX = "c3po/backend/app/"
SECTION_SCHEMA = "VALUATION-ENSEMBLE-GRADE-ARTIFACT-v1"
JOURNAL_SCHEMA = "VALUATION-ENSEMBLE-GRID-JOURNAL-v1"
CHUNK_SCHEMA = "VALUATION-ENSEMBLE-GRID-CHUNK-v1"
MAX_REV3_BYTES = 64 * 1024 * 1024
MAX_CHECKOUT_BYTES = 1024 * 1024
ASFILED_SOURCE_CODE = "sec_asfiled"  # the Investor Relations worker's as-filed poll (investor_relations.py)
ASFILED_WAIT_SECONDS = 180  # a poll in flight is waited for (it lasts seconds); one still running after this refuses
INGESTION_WINDOW = timedelta(hours=12)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_CODE = re.compile(r"[a-z0-9_:;.=-]{1,300}")


# ------------------------------------------------------------------ pinned inputs
def checkout_file(root: Path, relative: Path, *, limit: int = MAX_CHECKOUT_BYTES) -> bytes:
    """The bytes of ``root/relative`` with no symbolic link anywhere on its path, a regular file within ``limit``."""
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("ensemble_driver_checkout_path_holds_a_symlink")
    fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("ensemble_driver_checkout_file_invalid")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(limit + 1)
    finally:
        os.close(fd)
    if len(raw) > limit:
        raise ValueError("ensemble_driver_checkout_file_invalid")
    return raw


def running_files(checkout: Mapping[str, str], app_dir: Path) -> None:
    """Refuse unless every instrument module of the checkout is byte-identical to the one this process imports, and the
    two hold the same ensemble modules (the image is the checkout's revision: nothing else may run under its pin)."""
    names = {name.removeprefix(APP_PREFIX) for name in checkout if name.startswith(APP_PREFIX)}
    running = {path.name for path in app_dir.glob("valuation_ensemble_*.py")}
    if running != {name for name in names if name.startswith("valuation_ensemble_")}:
        raise ValueError("ensemble_driver_running_modules_differ_from_checkout")
    for name in sorted(names):
        if hashlib.sha256((app_dir / name).read_bytes()).hexdigest() != checkout[APP_PREFIX + name]:
            raise ValueError("ensemble_driver_running_code_differs_from_checkout")


def read_rev3(stream: Any) -> dict[str, Any]:
    raw = stream.read(MAX_REV3_BYTES + 1)
    if len(raw) > MAX_REV3_BYTES:
        raise ValueError("ensemble_driver_rev3_manifest_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("ensemble_driver_rev3_manifest_invalid")
    return value


def price_pin_of(rev3: Mapping[str, Any]) -> datetime:
    """The ONE price pin of the rev3 grid (``price_pin.requested_at``): every section re-reads that publication."""
    pins = rev3.get("price_pin")
    requested = pins.get("requested_at") if isinstance(pins, Mapping) else None
    if not isinstance(requested, str):
        raise ValueError("ensemble_driver_rev3_price_pin_missing")
    return utc(datetime.fromisoformat(requested.replace("Z", "+00:00")))


# ------------------------------------------------------------------ the private store and its journal
def private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("ensemble_driver_directory_must_be_private_owned_directory")
    return path


def _slot(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(row["market"]), str(row["session_date"]), str(row["as_of"])


def entry_of(receipt: Mapping[str, Any], pairs: Mapping[tuple[str, str, str], tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
    """The manifest entry ``execute_grade_chunk`` builds for a committed section, rebuilt from the section header it
    stored and the rev3 pair of its slot (the same fields, the same sources)."""
    section = receipt["section"]
    pair = pairs.get(_slot(section))
    if pair is None:
        raise ValueError("ensemble_driver_section_outside_reference_pairs")
    v3_ref, served_ref = pair
    entry = {key: section[key] for key in ("market", "session_date", "as_of", "run_key", "records_sha256", "catalogue_stocks", "input_pins")}
    entry.update({"receipt_run_key": receipt["run_key"], "v3_cycle_id": str(v3_ref["cycle_id"]), "served_cycle_id": str(served_ref["cycle_id"]),
                  "v3_run_key": v3_ref["run_key"], "served_run_key": served_ref["run_key"], "instrument_commit": receipt["instrument_commit"],
                  "instrument_pin_sha256": receipt["instrument_pin_sha256"], "implementation_files": dict(receipt["implementation_files"]),
                  "started_at": receipt["started_at"]})
    return entry


class JournaledStore(FileReceiptStore):
    """The executor's private sink; each section header it commits is journaled at once as its manifest entry."""

    def __init__(self, directory: Path, *, journal: Path, pairs: Mapping[tuple[str, str, str], tuple[Mapping[str, Any], Mapping[str, Any]]],
                 owner_order_sha256: str) -> None:
        super().__init__(directory)
        self.journal = journal
        self.pairs = pairs
        self.owner_order_sha256 = owner_order_sha256
        self.journaled = 0
        self.bytes_written = 0

    def put(self, receipt: Mapping[str, Any]) -> tuple[Path, bool]:
        path, created = super().put(receipt)
        if created:
            self.bytes_written += path.stat().st_size
        if receipt.get("schema") == SECTION_SCHEMA:
            if receipt.get("owner_order_sha256") != self.owner_order_sha256:
                raise ValueError("ensemble_driver_section_of_another_order")
            append_journal(self.journal, entry_of(receipt, self.pairs))
            self.journaled += 1
        return path, created


def append_journal(journal: Path, entry: Mapping[str, Any]) -> None:
    line = (json.dumps({"schema": JOURNAL_SCHEMA, "entry": entry}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("ensemble_driver_journal_not_private_regular_owned_file")
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def read_journal(journal: Path) -> list[dict[str, Any]]:
    """The journaled entries, one per slot (a slot computed again after an interruption keeps its LATEST commit; both
    are complete artifacts). A torn LAST line — a crash inside the append, never a committed entry — is cut off so the
    next append starts on a line of its own; any other bad line refuses."""
    try:
        fd = os.open(journal, os.O_RDWR | os.O_NOFOLLOW)
    except FileNotFoundError:
        return []
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("ensemble_driver_journal_not_private_regular_owned_file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read()
        lines = raw.split(b"\n")
        if lines.pop():  # the bytes after the last newline: a torn append
            os.ftruncate(fd, len(raw) - len(raw.rsplit(b"\n", 1)[-1]))
            os.fsync(fd)
    finally:
        os.close(fd)
    by_slot: dict[tuple[str, str, str], dict[str, Any]] = {}
    for line in lines:
        value = json.loads(line)
        if not isinstance(value, dict) or value.get("schema") != JOURNAL_SCHEMA or not isinstance(value.get("entry"), dict):
            raise ValueError("ensemble_driver_journal_line_invalid")
        by_slot[_slot(value["entry"])] = value["entry"]
    return [by_slot[slot] for slot in sorted(by_slot, key=lambda x: (x[1], x[0], x[2]))]


def write_manifest(directory: Path, manifest: Mapping[str, Any]) -> Path:
    digest = str(manifest["manifest_sha256"])
    if not _SHA256.fullmatch(digest) or canonical_hash({k: v for k, v in manifest.items() if k != "manifest_sha256"}) != digest:
        raise ValueError("ensemble_driver_manifest_digest_invalid")
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    path = directory / f"{digest}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        if checkout_file(directory, Path(path.name), limit=len(raw)) != raw:
            raise ValueError("ensemble_driver_manifest_collision") from None
        return path
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


# ------------------------------------------------------------------ the operational guard (before and after each section)
def asfiled_running(database: Any, now: datetime) -> int:
    """The as-filed polls (``sec_asfiled``) still ``running`` that started in the last 12 h: a poll writes statement
    vintages, so no section starts or ends while one is in flight. Read only."""
    since = utc(now) - INGESTION_WINDOW
    if not database.database_url:
        runs = getattr(database, "_ingestion_runs", {})
        return sum(1 for run in runs.values() if run.get("status") == "running" and run.get("source_code") == ASFILED_SOURCE_CODE
                   and utc(run["started_at"] if isinstance(run["started_at"], datetime) else datetime.fromisoformat(str(run["started_at"]))) >= since)
    with database.connection() as connection:
        row = connection.execute(
            "SELECT count(*) FROM ingestion_runs run JOIN data_sources source ON source.id = run.source_id "
            "WHERE run.status = 'running' AND run.started_at >= %s AND source.code = %s", (since, ASFILED_SOURCE_CODE)).fetchone()
    return int(row[0]) if row else 0


def operational_guard(database: Any, *, clock: Callable[[], datetime], blocking: Callable[[Any, datetime], int],
                      sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                      wait_seconds: float = ASFILED_WAIT_SECONDS) -> Callable[[], None]:
    """Raises on a blocked or unknown state, returns ``None`` otherwise (the executor's contract): no nightly valuation
    worker or long ingestion running (the rev3 rule), and no as-filed poll in flight — waited for up to
    ``wait_seconds`` (a poll lasts seconds), then a refusal. A query that cannot answer propagates: fail closed."""
    def guard() -> None:
        if blocking(database, clock()):
            raise ValueError("ensemble_guard_blocking_ingestion")
        deadline = monotonic() + wait_seconds
        while asfiled_running(database, clock()):
            if monotonic() >= deadline:
                raise ValueError("ensemble_guard_asfiled_poll_running")
            sleep(5.0)
        return None
    return guard


def _blocking(database: Any, now: datetime) -> int:
    from .valuation_pit_grid import running_ingestions
    return int(running_ingestions(database, now)["blocking"])


# ------------------------------------------------------------------ one chunk
def run_chunk(database: Any, settings: Any, *, rev3: Mapping[str, Any], order_sha256: str, pin_sha256: str, binding: InstrumentBinding,
              max_runs: int, stop_before: datetime, legacy_root: Path = LEGACY_ROOT, store_root: Path = STORE_ROOT,
              app_dir: Path | None = None, clock: Callable[[], datetime] | None = None,
              prices_for: Callable[[Mapping[str, Any]], Any] | None = None,
              guard: Callable[[], None] | None = None) -> dict[str, Any]:
    from .valuation_ensemble_calendar import report_calendar_for
    from .valuation_ensemble_executor import _reference_pairs, execute_grade_chunk

    now = clock or (lambda: datetime.now(timezone.utc))
    order_bytes = checkout_file(legacy_root, ORDERS / f"{order_sha256}.json")
    pin = json.loads(checkout_file(legacy_root, PINS / f"{pin_sha256}.json"))
    if not isinstance(pin, dict):
        raise ValueError("ensemble_driver_pin_invalid")
    files = instrument_file_hashes(legacy_root)
    running_files(files, app_dir or Path(__file__).resolve().parent)
    pairs = {_slot(v3): (v3, served) for v3, served in _reference_pairs(rev3)}
    if prices_for is None:
        from .valuation_panel import _NoNetworkHttp
        from .valuation_pit_rerun import PinnedPrices
        from .valuation_price_history import PriceHistoryService

        pinned_at, reader = price_pin_of(rev3), PriceHistoryService(settings, database, _NoNetworkHttp())

        def pinned(v3_ref: Mapping[str, Any]) -> Any:
            as_of = utc(datetime.fromisoformat(str(v3_ref["as_of"]).replace("Z", "+00:00")))
            return PinnedPrices(reader, str(v3_ref["market"]), as_of=as_of, pinned_at=pinned_at, pin_mode="explicit")
        prices_for = pinned
    root = private_directory(store_root)
    manifests = private_directory(root / "manifests")
    journal = root / f"journal-{order_sha256}-{pin_sha256}.jsonl"
    store = JournaledStore(private_directory(root / "receipts"), journal=journal, pairs=pairs, owner_order_sha256=order_sha256)
    prior = tuple(read_journal(journal))
    started = time.monotonic()
    manifest = execute_grade_chunk(
        database, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files, owner_order_bytes=order_bytes,
        owner_order_sha256=order_sha256, store=store, prices_for=prices_for,
        operational_guard=guard or operational_guard(database, clock=now, blocking=_blocking),
        report_calendar=report_calendar_for(rev3), max_runs=max_runs, stop_before=stop_before, clock=now, prior_entries=prior)
    elapsed = time.monotonic() - started
    write_manifest(manifests, manifest)
    computed = int(manifest["computed_this_chunk"])
    return {"schema": CHUNK_SCHEMA, "kind": "chunk", "manifest_sha256": manifest["manifest_sha256"], "complete": manifest["complete"],
            "remaining": manifest["remaining"], "entries": len(manifest["entries"]), "computed_this_chunk": computed,
            "prior_entries": len(prior), "journaled_this_chunk": store.journaled, "stopped": manifest["stopped"],
            "elapsed_seconds": round(elapsed, 1), "seconds_per_section": round(elapsed / computed, 1) if computed else None,
            "receipt_bytes_written": store.bytes_written, "peak_rss_kb": peak_rss_kb(),
            "owner_order_sha256": order_sha256, "instrument_pin_sha256": pin_sha256}


def peak_rss_kb() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak // 1024) if sys.platform == "darwin" else int(peak)


def refusal_code(error: BaseException) -> str:
    """A refusal's printable reason: the executor's own lowercase code, never free text (a ticker is upper case)."""
    text = str(error).strip()
    return text if _CODE.fullmatch(text) else f"exception:{type(error).__name__}"


def _instant(parser: argparse.ArgumentParser, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parser.error("--stop-before must be ISO-8601 with a zone")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parser.error("--stop-before must be ISO-8601 with a zone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None, *, database: Any = None, settings: Any = None) -> int:
    parser = argparse.ArgumentParser(description="PREREG_VALUATION_ENSEMBLE_PIT_US_V1: one bounded grade chunk on the host (rev3 manifest on stdin). "
                                                 "Prints aggregates only (JSON lines), never a symbol.")
    parser.add_argument("--owner-order-sha256", required=True)
    parser.add_argument("--pin-sha256", required=True)
    parser.add_argument("--instrument-commit", required=True)
    parser.add_argument("--owner-signature-comment-id", type=int, required=True)
    parser.add_argument("--technical-go-comment-id", type=int, required=True)
    parser.add_argument("--max-runs", type=int, required=True)
    parser.add_argument("--stop-before", required=True)
    args = parser.parse_args(argv)
    for option, value, pattern in (("--owner-order-sha256", args.owner_order_sha256, _SHA256), ("--pin-sha256", args.pin_sha256, _SHA256),
                                   ("--instrument-commit", args.instrument_commit, _COMMIT)):
        if not pattern.fullmatch(value):
            parser.error(f"{option} is not lowercase hex of the right length")
    if not 1 <= args.max_runs <= 200 or args.owner_signature_comment_id <= 0 or args.technical_go_comment_id <= 0:
        parser.error("--max-runs must be 1-200 and the comment ids positive")
    stop_before = _instant(parser, args.stop_before)
    binding = InstrumentBinding(expected_pin_sha256=args.pin_sha256, prereg_commit=PREREG_COMMIT, instrument_commit=args.instrument_commit,
                                owner_signature_comment_id=args.owner_signature_comment_id, technical_GO_comment_id=args.technical_go_comment_id)
    try:
        from .valuation_accuracy_report import force_read_only_session

        force_read_only_session()  # libpq reads it at connect time: every transaction of this process is read only
        if settings is None:
            from .config import get_settings
            settings = get_settings()
        if database is None:
            from .database import Database
            database = Database(settings)
        rev3 = read_rev3(sys.stdin.buffer)
        print(json.dumps({"kind": "start", "max_runs": args.max_runs, "stop_before": stop_before.isoformat()}, sort_keys=True), flush=True)
        result = run_chunk(database, settings, rev3=rev3, order_sha256=args.owner_order_sha256, pin_sha256=args.pin_sha256, binding=binding,
                           max_runs=args.max_runs, stop_before=stop_before)
    except Exception as error:  # noqa: BLE001 - every refusal is one printed code; the traceback stays on stderr (private)
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"kind": "refused", "reason": refusal_code(error), "peak_rss_kb": peak_rss_kb()}, sort_keys=True), flush=True)
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
