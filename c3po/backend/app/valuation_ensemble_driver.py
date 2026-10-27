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
import fcntl
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
READING_SCHEMA = "VALUATION-ENSEMBLE-READING-v1"
MAX_MANIFEST_BYTES = 256 * 1024 * 1024
PUBLIC_UPPER = frozenset({"PASS", "FAIL", "VOID", "UNMEASURED", "NEGATIVE", "SINGLE", "US", "NASDAQ", "NYSE"})
MAX_REV3_BYTES = 64 * 1024 * 1024
MAX_CHECKOUT_BYTES = 1024 * 1024
ASFILED_SOURCE_CODE = "sec_asfiled"  # the Investor Relations worker's as-filed poll (investor_relations.py)
ASFILED_WAIT_SECONDS = 180  # a poll in flight is waited for (it lasts seconds); one still running after this refuses
INGESTION_WINDOW = timedelta(hours=12)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_CODE = re.compile(r"[a-z0-9_:./=-]{1,200}")  # a code or a repository path: lower case, so never a ticker
NIGHTLY_SOURCE_TYPE = "valuation_worker"  # the nightly valuation worker (the rev3 rule of valuation_pit_grid.running_ingestions)
INGESTION_LONG_RUNNING = timedelta(minutes=30)


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
    two hold the same ensemble modules (the image is the checkout's revision: nothing else may run under its pin; the guard's queries are this pinned module's own)."""
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


def write_all(fd: int, data: bytes) -> None:
    """``os.write`` until every byte is written (a short write on a nearly full disk is a refusal, never half a line)."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("ensemble_driver_short_write")
        view = view[written:]


def fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def append_journal(journal: Path, entry: Mapping[str, Any]) -> None:
    line = (json.dumps({"schema": JOURNAL_SCHEMA, "entry": entry}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()
    created = not journal.exists()
    fd = os.open(journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("ensemble_driver_journal_not_private_regular_owned_file")
        write_all(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    if created:
        fsync_directory(journal.parent)


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


def write_manifest(directory: Path, manifest: Mapping[str, Any], *, key: str = "manifest_sha256") -> Path:
    """A private, immutable JSON document named by its own digest (``key``; the canonical sha256 of the rest)."""
    digest = str(manifest[key])
    if not _SHA256.fullmatch(digest) or canonical_hash({k: v for k, v in manifest.items() if k != key}) != digest:
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
        write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(directory)
    return path


# ------------------------------------------------------------------ the operational guard (before and after each section)
def asfiled_running(database: Any, now: datetime) -> int:
    """The as-filed polls (``sec_asfiled``) still ``running`` that started in the last 12 h: a poll writes statement
    vintages, so no section starts or ends while one is in flight. Read only."""
    since = utc(now) - INGESTION_WINDOW
    if not database.database_url:
        runs = getattr(database, "_ingestion_runs", {})
        return sum(1 for run in runs.values() if run.get("status") == "running" and run.get("source_code") == ASFILED_SOURCE_CODE
                   and _started(run) >= since)
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


def blocking_ingestions(database: Any, now: datetime) -> int:
    """The rev3 rule (``valuation_pit_grid.running_ingestions``), kept here so the guard runs pinned code only: the runs
    still ``running`` that started in the last 12 h and are the nightly valuation worker's or have run for 30 min. Read only."""
    since, long_ago = utc(now) - INGESTION_WINDOW, utc(now) - INGESTION_LONG_RUNNING
    if not database.database_url:
        runs = getattr(database, "_ingestion_runs", {})
        sources = {str(source.get("id")): str(source.get("source_type")) for source in getattr(database, "_data_sources", {}).values()}
        active = [run for run in runs.values() if run.get("status") == "running" and _started(run) >= since]
        return sum(1 for run in active if sources.get(str(run.get("source_id"))) == NIGHTLY_SOURCE_TYPE or _started(run) <= long_ago)
    with database.connection() as connection:
        row = connection.execute(
            "SELECT count(*) FILTER (WHERE source.source_type = %s OR run.started_at <= %s) FROM ingestion_runs run "
            "LEFT JOIN data_sources source ON source.id = run.source_id WHERE run.status = 'running' AND run.started_at >= %s",
            (NIGHTLY_SOURCE_TYPE, long_ago, since)).fetchone()
    return int(row[0]) if row else 0


def _started(run: Mapping[str, Any]) -> datetime:
    value = run["started_at"]
    return utc(value if isinstance(value, datetime) else datetime.fromisoformat(str(value)))


class ChunkLock:
    """One driver at a time on the store: an exclusive ``flock`` on ``<store>/driver.lock`` for the whole chunk (a driver a
    failed cleanup left running keeps it; a second one refuses instead of sharing the journal)."""

    def __init__(self, root: Path) -> None:
        self.path = root / "driver.lock"
        self.fd: int | None = None

    def __enter__(self) -> "ChunkLock":
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise ValueError("ensemble_driver_another_chunk_is_running") from None
        self.fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


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
    with ChunkLock(root):
        manifests = private_directory(root / "manifests")
        journal = root / f"journal-{order_sha256}-{pin_sha256}.jsonl"
        store = JournaledStore(private_directory(root / "receipts"), journal=journal, pairs=pairs, owner_order_sha256=order_sha256)
        prior = tuple(read_journal(journal))
        started = time.monotonic()
        first_section: list[float] = []  # the executor verifies every prior entry BEFORE its first section's prices

        def timed_prices(v3_ref: Mapping[str, Any]) -> Any:
            if not first_section:
                first_section.append(time.monotonic())
            return prices_for(v3_ref)
        manifest = execute_grade_chunk(
            database, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files, owner_order_bytes=order_bytes,
            owner_order_sha256=order_sha256, store=store, prices_for=timed_prices,
            operational_guard=guard or operational_guard(database, clock=now, blocking=blocking_ingestions),
            report_calendar=report_calendar_for(rev3), max_runs=max_runs, stop_before=stop_before, clock=now, prior_entries=prior)
        ended = time.monotonic()
        write_manifest(manifests, manifest)
    computed = int(manifest["computed_this_chunk"])
    verified_until = first_section[0] if first_section else ended
    compute_seconds = ended - verified_until
    return {"schema": CHUNK_SCHEMA, "kind": "chunk", "manifest_sha256": manifest["manifest_sha256"], "complete": manifest["complete"],
            "remaining": manifest["remaining"], "entries": len(manifest["entries"]), "computed_this_chunk": computed,
            "prior_entries": len(prior), "journaled_this_chunk": store.journaled, "stopped": manifest["stopped"],
            "elapsed_seconds": round(ended - started, 1), "prior_verify_seconds": round(verified_until - started, 1),
            "compute_seconds": round(compute_seconds, 1), "seconds_per_section": round(compute_seconds / computed, 1) if computed else None,
            "receipt_bytes_written": store.bytes_written, "peak_rss_kb": peak_rss_kb(),
            "owner_order_sha256": order_sha256, "instrument_pin_sha256": pin_sha256}


# ------------------------------------------------------------------ the single-look reading
class LabelReader:
    """``label_reader(row, h)`` for ``build_report``: the labels of the rev3 PINNED price publication of the row's exchange
    (cut = its ``available_at`` + 1 µs, checked to resolve exactly that publication before any label), the rev3 rules —
    the basis check of the row's close(D) against the publication's close at D (``TOL_BASIS``), ``return`` =
    adjusted_close(D+h) / adjusted_close(D) − 1, ``return_executable`` = adjusted_close(D+1+h) / adjusted_close(D+1) − 1,
    a missing label's ``reason`` = the label's status. The reader keeps one series at a time; the report reads symbol
    after symbol."""

    def __init__(self, reader: Any, rev3: Mapping[str, Any]) -> None:
        from . import valuation_panel as panel

        self.reader, self.panel = reader, panel
        self.cuts: dict[str, datetime] = {}
        self.calendar_close: dict[str, datetime | None] = {}
        pins = rev3.get("price_pin") if isinstance(rev3.get("price_pin"), Mapping) else {}
        for market in ("NASDAQ", "NYSE"):
            pin = pins.get(market) if isinstance(pins, Mapping) else None
            if not isinstance(pin, Mapping) or pin.get("status") != "ok":
                raise ValueError("ensemble_driver_rev3_price_pin_missing")
            cut = utc(datetime.fromisoformat(str(pin["available_at"]).replace("Z", "+00:00"))) + timedelta(microseconds=1)
            vintage = reader.vintage(market, available_before=cut)
            if (vintage is None or vintage.get("status") != "ok" or str(vintage.get("publication_id")) != str(pin.get("publication_id"))
                    or vintage.get("bars_sha256") != pin.get("bars_sha256")):
                raise ValueError("ensemble_driver_label_vintage_not_the_pinned_one")
            self.cuts[market], self.calendar_close[market] = cut, panel.calendar_horizon(market)

    def _label(self, market: str, symbol: str, session: Any, horizon: int) -> dict[str, Any]:
        cut = self.cuts[market]
        return self.panel.resolve_label(self.reader.label_bar(market, symbol, session, horizon, available_before=cut), cut=cut,
                                        calendar_close=self.calendar_close[market])

    def __call__(self, row: Mapping[str, Any], horizon: int) -> dict[str, Any]:
        from datetime import date

        market, symbol, day = str(row["market"]), str(row["symbol"]), str(row["session_date"])[:10]
        positive = self.panel._positive
        bar = self.reader.bars(market, symbol, available_before=self.cuts[market]).get(day)
        close, adjusted = (positive(bar.get("close")), positive(bar.get("adjusted_close"))) if bar else (None, None)
        price = positive(row.get("price"))
        if close is None or adjusted is None:
            return {"return": None, "return_executable": None, "reason": "label_unavailable:adjustment_unknown"}
        if price is None or abs(price - close) / close > self.panel.TOL_BASIS:
            return {"return": None, "return_executable": None, "reason": "label_unavailable:basis_mismatch"}
        session = date.fromisoformat(day)
        at_h, at_1, at_exit = (self._label(market, symbol, session, k) for k in (horizon, 1, horizon + 1))

        def realized(label: Mapping[str, Any]) -> float | None:
            return positive(label.get("adjusted_close")) if label.get("status") == "labelled" else None
        exit_h, entry, exit_x = realized(at_h), realized(at_1), realized(at_exit)
        # the reason of a missing label: the executable pair's first (the report's attrition counts it), else the h label's
        missing = next((label for value, label in ((entry, at_1), (exit_x, at_exit), (exit_h, at_h)) if value is None), None)
        reason = None if missing is None else str(missing.get("status"))
        return {"return": exit_h / adjusted - 1.0 if exit_h is not None else None,
                "return_executable": exit_x / entry - 1.0 if exit_x is not None and entry is not None else None, "reason": reason}


_SCHEMA_NAME = re.compile(r"[A-Z0-9]+(-[A-Z0-9]+)*-v[0-9]+")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9:.]+([+-][0-9]{2}:[0-9]{2}|Z)?)?")


def public_text(value: str) -> str:
    """A string as published: a lower-case code, a status word, a schema name or an instant as it is; anything else (a
    sibling check's ``…:SYMBOL``, an exception's text kept as a model reason) reduced to its code prefix + ``:redacted``."""
    if _CODE.fullmatch(value) or value in PUBLIC_UPPER or _SCHEMA_NAME.fullmatch(value) or _INSTANT.fullmatch(value):
        return value
    prefix = value.split(":", 1)[0]
    return prefix + ":redacted" if prefix != value and _CODE.fullmatch(prefix) else "redacted"


def public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The reading as published: every string and key through ``public_text`` (counts under keys that collapse to one are
    summed); the protocol block — constant prose of the pinned report module — as it is. The full reading stays private."""
    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                name = public_text(str(key))
                item = item if key == "protocol" else walk(item)
                if name in out and isinstance(out[name], (int, float)) and isinstance(item, (int, float)) and not isinstance(item, bool):
                    out[name] = out[name] + item
                else:
                    out[name] = item
            return out
        if isinstance(value, list):
            items = [walk(item) for item in value]
            return sorted(set(items)) if items and all(isinstance(item, str) for item in items) else items
        return public_text(value) if isinstance(value, str) else value
    return walk(json.loads(json.dumps(payload, allow_nan=False)))


def run_report(database: Any, settings: Any, *, rev3: Mapping[str, Any], pin_sha256: str, binding: InstrumentBinding, manifest_sha256: str,
               legacy_root: Path = LEGACY_ROOT, store_root: Path = STORE_ROOT, app_dir: Path | None = None,
               label_reader: Callable[[Mapping[str, Any], int], Mapping[str, Any]] | None = None,
               paired_sources_reader: Callable[[Mapping[str, Any]], tuple[Any, Any]] | None = None) -> dict[str, Any]:
    """The single-look reading of the COMPLETE grade manifest ``manifest_sha256`` (the digest the last chunk published),
    streamed entry by entry from the private store (``build_report(records_for=...)``): every instrument, manifest, row and
    sibling check runs before the first label. The full reading stays private (``reports/<reading_sha256>.json``) and is
    the host's own record of the single look (``earlier_reading``)."""
    from .valuation_ensemble_calendar import report_calendar_for
    from .valuation_ensemble_executor import load_grade_artifact
    from .valuation_ensemble_report import build_report

    if not _SHA256.fullmatch(manifest_sha256):
        raise ValueError("ensemble_driver_manifest_digest_invalid")
    pin = json.loads(checkout_file(legacy_root, PINS / f"{pin_sha256}.json"))
    if not isinstance(pin, dict):
        raise ValueError("ensemble_driver_pin_invalid")
    files = instrument_file_hashes(legacy_root)
    running_files(files, app_dir or Path(__file__).resolve().parent)
    root = private_directory(store_root)
    with ChunkLock(root):
        reports = private_directory(root / "reports")
        spent = earlier_reading(reports, manifest_sha256)
        if spent is not None:  # the same manifest: the stored reading, no label read again
            return reading_line(spent, pin_sha256=pin_sha256, elapsed=0.0, repeated=True)
        manifest = json.loads(checkout_file(root / "manifests", Path(f"{manifest_sha256}.json"), limit=MAX_MANIFEST_BYTES))
        store = FileReceiptStore(private_directory(root / "receipts"))
        calendar = report_calendar_for(rev3)
        if label_reader is None:
            from .valuation_accuracy_report import _SymbolReader
            from .valuation_panel import _CutReads, _NoNetworkHttp

            label_reader = LabelReader(_SymbolReader(settings, _CutReads(database), _NoNetworkHttp()), rev3)
        if paired_sources_reader is None:
            def siblings(entry: Mapping[str, Any]) -> tuple[Any, Any]:
                return (database.analysis_snapshot_by_id(str(entry["v3_cycle_id"])), database.analysis_snapshot_by_id(str(entry["served_cycle_id"])))
            paired_sources_reader = siblings

        def records_for(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
            return load_grade_artifact(store, str(entry["receipt_run_key"]))["section"]["records"]
        started = time.monotonic()
        reading = build_report(manifest, None, rev3_manifest=rev3, pin=pin, binding=binding, file_hashes=files, label_reader=label_reader,
                               index_of=calendar["index_of"], mature_through={int(h): v for h, v in calendar["mature_through"].items()},
                               partition_last=calendar["partition_last"], expected_manifest_sha256=manifest_sha256,
                               paired_sources_reader=paired_sources_reader, records_for=records_for)
        elapsed = time.monotonic() - started
        document = {**reading, "manifest_sha256": manifest_sha256}
        write_manifest(reports, {**document, "reading_sha256": canonical_hash(document)}, key="reading_sha256")
    return reading_line(document, pin_sha256=pin_sha256, elapsed=elapsed, repeated=False)


def earlier_reading(reports: Path, manifest_sha256: str) -> dict[str, Any] | None:
    """The single look, on the host: a stored reading that is not VOID over ANOTHER manifest refuses a new one; one over
    THIS manifest is returned as it is (no label read again). VOID readings read no label and spend nothing."""
    found = None
    for path in sorted(reports.glob("*.json")):
        document = json.loads(checkout_file(reports, Path(path.name), limit=MAX_MANIFEST_BYTES))
        status = (((document.get("payload") or {}).get("verdict")) or {}).get("status")
        if status == "VOID":
            continue
        if document.get("manifest_sha256") != manifest_sha256:
            raise ValueError("ensemble_driver_single_look_spent_on_another_manifest")
        found = document
    return found


def reading_line(document: Mapping[str, Any], *, pin_sha256: str, elapsed: float, repeated: bool) -> dict[str, Any]:
    """The printed line: the public payload, its own digest, and the private payload's digest only when nothing was redacted
    (a redacted VOID reason must not be recoverable by hashing candidate symbols into the public payload)."""
    public = public_payload(document["payload"])
    exact = public == json.loads(json.dumps(document["payload"], allow_nan=False))
    return {"schema": READING_SCHEMA, "kind": "reading", "payload_sha256": document["payload_sha256"] if exact else None,
            "public_payload_sha256": canonical_hash(public), "redacted": not exact, "repeated": repeated,
            "manifest_sha256": document["manifest_sha256"], "instrument_pin_sha256": pin_sha256,
            "elapsed_seconds": round(elapsed, 1), "peak_rss_kb": peak_rss_kb(), "payload": public}


def peak_rss_kb() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak // 1024) if sys.platform == "darwin" else int(peak)


def refusal_code(error: BaseException) -> str:
    """A refusal's printable reason: the executor's own codes (``;``-joined, a file path allowed), never free text — a
    token that is not a lower-case code (a ticker is upper case) reduces the whole reason to the exception's class."""
    tokens = [token.strip().replace("technical_GO", "technical_go") for token in str(error).split(";")]
    if tokens and all(_CODE.fullmatch(token) for token in tokens):
        return ";".join(tokens)
    return f"exception:{type(error).__name__}"


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
    parser.add_argument("--report", action="store_true", help="the single-look reading of the complete manifest --manifest-sha256 (no owner order)")
    parser.add_argument("--manifest-sha256", default=None)
    parser.add_argument("--owner-order-sha256", default=None)
    parser.add_argument("--pin-sha256", required=True)
    parser.add_argument("--instrument-commit", required=True)
    parser.add_argument("--owner-signature-comment-id", type=int, required=True)
    parser.add_argument("--technical-go-comment-id", type=int, required=True)
    parser.add_argument("--max-runs", type=int, default=None)
    parser.add_argument("--stop-before", default=None)
    args = parser.parse_args(argv)
    checks = [("--pin-sha256", args.pin_sha256, _SHA256), ("--instrument-commit", args.instrument_commit, _COMMIT)]
    checks.append(("--manifest-sha256", args.manifest_sha256, _SHA256) if args.report else ("--owner-order-sha256", args.owner_order_sha256, _SHA256))
    for option, value, pattern in checks:
        if not isinstance(value, str) or not pattern.fullmatch(value):
            parser.error(f"{option} is not lowercase hex of the right length")
    if args.owner_signature_comment_id <= 0 or args.technical_go_comment_id <= 0:
        parser.error("the comment ids must be positive")
    if args.report and any(value is not None for value in (args.owner_order_sha256, args.max_runs, args.stop_before)):
        parser.error("--report takes no owner order, --max-runs or --stop-before")
    if not args.report and (args.max_runs is None or not 1 <= args.max_runs <= 200 or args.stop_before is None or args.manifest_sha256 is not None):
        parser.error("a chunk needs --max-runs 1-200 and --stop-before (and no --manifest-sha256)")
    stop_before = None if args.report else _instant(parser, args.stop_before)
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
        if args.report:
            print(json.dumps({"kind": "start", "max_runs": None, "stop_before": None}, sort_keys=True), flush=True)
            result = run_report(database, settings, rev3=rev3, pin_sha256=args.pin_sha256, binding=binding, manifest_sha256=str(args.manifest_sha256))
        else:
            assert stop_before is not None
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
