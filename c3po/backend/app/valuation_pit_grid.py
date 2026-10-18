"""The grid of the US point-in-time backtest (PREREG_VALUATION_PIT_BACKTEST_US_V1 §3, §14): runs ``valuation_pit_rerun`` for
every ``T`` of the pre-registered grid, both US exchanges per ``T``, through its public API, and writes the grid manifest
the report reads (``VALUATION-PIT-GRID-MANIFEST-v1``).

``python -m app.valuation_pit_grid --market US --price-pinned-at <zoned instant> --statements vintages --step-sessions 5
[--grid-start 2021-06-01] [--from YYYY-MM-DD] [--to YYYY-MM-DD] --manifest-out <new path> [--max-runs N]
[--stop-before <zoned instant>] [--owner-order-sha256 <hex>] [--recompute-existing] [--dry-run]``, and
``python -m app.valuation_pit_grid --market US --host-check`` (read only).

* **The grid** is the report module's (``valuation_pit_backtest_report.eligible_bounds`` / ``prereg_grid``): every
  ``--step-sessions``-th XNYS session from the first on/after ``--grid-start`` (default and pre-registered:
  ``GRID_START`` = 2021-06-01) to the last whose exit label ``T + 1 + 21`` closed before the pinned publication (both
  exchanges' vintages), anchored at the first — ``--from/--to`` (default: those bounds; outside them a refusal) select a
  sub-range of THAT grid, never another grid. The pin is ONE instant for the whole grid: the instant right after the
  one-off 120-month backfill publications of both exchanges (``valuation_price_history --backfill --months 120``), so that
  every ``T`` resolves them and never a later 36-month nightly republication; a pinned vintage that cannot start the grid
  at ``--grid-start`` is refused, the publication it resolves per exchange is recorded in the manifest, and every run's
  receipt must report that same publication (else the invocation stops). ``T`` = 01:00 America/Sao_Paulo of the civil day
  after the session (``t_instant``).
* **Each T runs NASDAQ then NYSE** (the re-executor loads one exchange per run and never the sibling as peers; the report
  unions both runs of a ``T``). A ``(exchange, T)`` whose LATEST run in the store already has this code (``source_version``
  and the engine files), this pin's publication and this statements mode, and whose cycle holds exactly its prediction
  identities, is REUSED without recomputation (``reused: true``, ``idempotent: true``) — a resumed grid never pays again
  for the ``T`` it already ran; ``--recompute-existing`` re-runs every ``T`` through the public API instead (an unchanged
  input set comes back idempotent, a changed one supersedes). Sequential; ``--max-runs N`` caps the ``T`` COMPUTED in one
  invocation (reused ones are free), ``--stop-before`` stops before starting a ``T`` at/after that instant (the operator's
  window: never into a session or a nightly phase); the next invocation resumes.
* **Output**: stdout carries JSON lines, aggregates only — one line per ``T`` (both runs: run_key, cycle, idempotent,
  reused, evaluated, records, not evaluable by reason, statements basis and coverage, the own-history model count and the
  elapsed seconds) and a final ``manifest`` line with the whole manifest; the manifest is also written to
  ``--manifest-out`` (``O_EXCL | O_NOFOLLOW``, mode 0600: a NEW path), with ``manifest_sha256`` = the canonical sha256
  of the manifest without that field. On an error the manifest of what was done is written (``stopped``: the error's
  type, never its message) and the error is re-raised. ``--dry-run`` prints the grid, the pin, the as-filed coverage and
  how many runs are reusable; ``--host-check`` prints the price publications a cut now sees and the as-filed coverage —
  both write nothing, in a read-only session.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from . import valuation_accuracy_report as accuracy
from . import valuation_pit_backtest_report as backtest
from . import valuation_pit_rerun as pit
from .config import Settings, get_settings
from .database import Database
from .valuation_panel import _NoNetworkHttp
from .valuation_price_history import PriceHistoryService

MARKET_GROUPS: dict[str, tuple[str, ...]] = {backtest.MARKET_GROUP: backtest.MARKETS}
ENGINE_FILES: tuple[str, ...] = ("valuation_v3_engine.py", "valuation_v3_inputs.py", "valuation_v3_macro.py", "valuation_v3_shadow.py", "valuation_pit_rerun.py")  # = the run manifest's engine.implementation_file_sha256 (pinned by test)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GridError(RuntimeError):
    pass


def engine_files() -> dict[str, str]:
    """The producer of this code: the sha256 of the files a run manifest names in ``engine.implementation_file_sha256``."""
    return {name: pit._file_sha256(name) for name in ENGINE_FILES}


def producer() -> dict[str, Any]:
    return {"source_version": pit.source_version(), "engine_files": engine_files()}


def resolve_pins(database: Database, settings: Settings, markets: Sequence[str], pinned_at: datetime) -> dict[str, dict[str, Any]]:
    """The publication ``--price-pinned-at`` resolves per exchange (the cut ``PinnedPrices`` uses), read only."""
    reader = PriceHistoryService(settings, database, _NoNetworkHttp())
    pins: dict[str, dict[str, Any]] = {}
    for market in markets:
        vintage = reader.vintage(market, available_before=pinned_at)
        if vintage is None or vintage["status"] != "ok":
            raise GridError(f"no verifiable {market} price vintage before the pin {pinned_at.isoformat()} ({'none' if vintage is None else vintage['status']})")
        pins[market] = {"status": "ok", "publication_id": str(vintage["publication_id"]), "price_snapshot_id": vintage["price_snapshot_id"],
                        "available_at": vintage["available_at"], "bars_sha256": vintage["bars_sha256"], "from": vintage["from"], "to": vintage["to"]}
    return pins


def plan(pins: Mapping[str, Mapping[str, Any]], *, step: int, start: date | None, end: date | None, grid_start: date | None = None
         ) -> tuple[dict[str, Any], list[date], list[date]]:
    """The bounds of the grid for these pins from ``grid_start`` (default: the pre-registered ``GRID_START``), the whole
    grid at ``step``, and the sub-range ``[start, end]`` of it (default: the bounds). A pinned vintage that cannot start the
    grid at ``grid_start`` (fewer than 252 sessions before it: a 36-month nightly republication instead of the 120-month
    backfill) and a range outside the bounds are ``GridError``: neither would be the pre-registered grid."""
    bounds = backtest.eligible_bounds(pins, grid_start=grid_start)
    full = backtest.prereg_grid(bounds, step=step)
    if not full:
        raise GridError(f"the pinned vintages give no grid (bounds {bounds['first_eligible']} … {bounds['last_eligible']})")
    if not bounds["starts_at_grid_start"]:
        raise GridError(f"the pinned vintages cannot start the grid at {bounds['grid_start']} (first eligible {bounds['first_eligible']}): pin the "
                        "120-month backfill publication of both exchanges")
    first, last = date.fromisoformat(bounds["first_eligible"]), date.fromisoformat(bounds["last_eligible"])
    start = start or first
    end = end or last
    if start < first or end > last or start > end:
        raise GridError(f"--from/--to {start.isoformat()} … {end.isoformat()} must lie within the pre-registered bounds {first.isoformat()} … {last.isoformat()}")
    return bounds, full, [session for session in full if start <= session <= end]


def _history_active(rows: Any) -> int:
    rows = rows if isinstance(rows, Mapping) else {}
    return sum(1 for row in rows.values() if isinstance(row, Mapping) and backtest.HISTORY_MODEL in (row.get("models") or {}))


def reusable_run(database: Database, market: str, as_of: datetime, *, publication_id: str, statements: str) -> dict[str, Any] | None:
    """The LATEST run of ``(market, T)`` when it is the run this invocation would compute — same code (``source_version`` and
    the engine files), same pinned publication, same statements mode — and its cycle holds exactly its prediction
    identities; else ``None`` (the run is computed through the public API). Read only."""
    snapshot = database.latest_analysis_snapshot_by_inputs(pit.ANALYSIS_TYPE, {"market": market, "as_of": pit._utc(as_of).isoformat()})
    if snapshot is None:
        return None
    inputs, outputs = pit._mapping(snapshot.get("inputs")), pit._mapping(snapshot.get("outputs"))
    if str(inputs.get("source_version")) != pit.source_version():
        return None
    if pit._mapping(pit._mapping(inputs.get("manifest")).get("engine")).get("implementation_file_sha256") != engine_files():
        return None
    if str(pit._mapping(inputs.get("price_pin")).get("resolved_publication_id")) != publication_id:
        return None
    if pit._mapping(pit._mapping(outputs.get("summary")).get("statements")).get("mode") != statements:
        return None
    expected = {(str(symbol), str(digest)) for symbol, digest in outputs.get("prediction_identities") or []}
    stored = {(str(symbol), str(record["row_sha256"])) for symbol, record in database.valuation_predictions_for_cycle(str(snapshot["id"]), source=pit.SOURCE).items()}
    return snapshot if stored == expected else None


def asfiled_coverage(database: Database, markets: Sequence[str], statements: str) -> dict[str, Any]:
    """How deep the as-filed table covers each exchange's catalogue NOW (aggregate): the names ``--statements vintages`` can
    evaluate (a run's own count is ``statements.coverage`` in its receipt). Read only."""
    if statements == "provider":
        return {"mode": statements}
    reader = pit.AsFiledReader(database)
    present = reader.present()
    result: dict[str, Any] = {"mode": statements, "table_present": present}
    for market in markets:
        catalogue = set(pit._catalogue_symbols(database, market))
        covered = set(reader.coverage(market)) if present else set()
        result[market] = {"catalogue": len(catalogue), "covered_in_catalogue": len(catalogue & covered)}
    return result


def host_check(database: Database, settings: Settings, *, markets: Sequence[str], now: datetime) -> dict[str, Any]:
    """The read-only check before the host steps (prereg §14 a): per exchange, the price publication a cut at ``now`` sees
    (id, availability, window, symbols and bars it holds) and the as-filed coverage of the catalogue. Aggregates only."""
    reader = PriceHistoryService(settings, database, _NoNetworkHttp())
    publications: dict[str, Any] = {}
    for market in markets:
        vintage = reader.vintage(market, available_before=now)
        publications[market] = None if vintage is None else {
            "status": vintage["status"], "publication_id": vintage["publication_id"], "available_at": vintage["available_at"], "from": vintage["from"],
            "to": vintage["to"], "symbols": len(vintage["series_sha256"]), "bars": sum(int(count) for count in vintage["series_bars"].values())}
    return {"kind": "host_check", "now": pit._utc(now).isoformat(), "publications": publications, "coverage": asfiled_coverage(database, markets, backtest.STATEMENTS),
            "producer": producer()}


def _entry(*, as_of: datetime, session: date, market: str, run_key: str, cycle_id: str, idempotent: bool, reused: bool, supersedes: str | None,
           summary: Mapping[str, Any], records: int, history_active: int) -> dict[str, Any]:
    return {"as_of": pit._utc(as_of).isoformat(), "session_date": session.isoformat(), "market": market, "run_key": run_key, "cycle_id": cycle_id,
            "idempotent": idempotent, "reused": reused, "supersedes": supersedes, "evaluated": int(summary.get("evaluated") or 0), "records": records,
            "not_evaluable": {str(key): int(value) for key, value in sorted(pit._mapping(summary.get("not_evaluable")).items())},
            "history_model_active": history_active}


def _line(entry: Mapping[str, Any], summary: Mapping[str, Any], elapsed: float) -> dict[str, Any]:
    """The aggregate per-run receipt of the stdout line (no symbol)."""
    statements = pit._mapping(summary.get("statements"))
    return {**{key: entry[key] for key in ("run_key", "cycle_id", "idempotent", "reused", "supersedes", "evaluated", "records", "not_evaluable", "history_model_active")},
            "statements_basis": statements.get("basis"), "statements_coverage": statements.get("coverage"), "price_vintage": summary.get("price_vintage"),
            "elapsed_seconds": round(elapsed, 3)}


class GridRun:
    """One invocation: the plan, the runs, the manifest."""

    def __init__(self, database: Database, settings: Settings, *, market_group: str, price_pinned_at: datetime, statements: str, step: int,
                 clock: Callable[[], datetime] | None = None, monotonic: Callable[[], float] = time.monotonic,
                 emit: Callable[[dict[str, Any]], None] | None = None, grid_start: date | None = None) -> None:
        if market_group not in MARKET_GROUPS:
            raise GridError(f"unknown market group {market_group!r}")
        if price_pinned_at.tzinfo is None or price_pinned_at.utcoffset() is None:
            raise GridError("the price pin must carry a time zone")
        if statements not in pit.STATEMENTS_MODES:
            raise GridError(f"unknown statements mode {statements!r}")
        self.database = database
        self.settings = settings
        self.market_group = market_group
        self.markets = MARKET_GROUPS[market_group]
        self.price_pinned_at = pit._utc(price_pinned_at)
        self.statements = statements
        self.step = step
        self.grid_start = grid_start or backtest.GRID_START
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.emit: Callable[[dict[str, Any]], None] = emit or (lambda line: print(json.dumps(line, sort_keys=True, allow_nan=False), flush=True))
        if self.price_pinned_at > pit._utc(self.clock()):
            raise GridError(f"the price pin {self.price_pinned_at.isoformat()} is in the future: it would resolve another vintage when repeated")
        self.pins = resolve_pins(database, settings, self.markets, self.price_pinned_at)
        self.failure: BaseException | None = None  # the error that stopped run(), re-raised by the caller once the manifest is written

    def dry_run(self, *, start: date | None, end: date | None) -> dict[str, Any]:
        bounds, full, sessions = plan(self.pins, step=self.step, start=start, end=end, grid_start=self.grid_start)
        reusable_runs = 0
        reusable_t = 0
        for session in sessions:
            found = [reusable_run(self.database, market, backtest.t_instant(session), publication_id=self.pins[market]["publication_id"], statements=self.statements)
                     for market in self.markets]
            reusable_runs += sum(1 for item in found if item is not None)
            reusable_t += all(item is not None for item in found)
        return {"kind": "dry_run", "market": self.market_group, "markets": list(self.markets), "price_pin": self._pin_block(), "statements": self.statements,
                "step_sessions": self.step, "grid_start": self.grid_start.isoformat(), "bounds": bounds, "prereg_grid_sessions": len(full),
                "grid": {"count": len(sessions), "first": sessions[0].isoformat() if sessions else None, "last": sessions[-1].isoformat() if sessions else None,
                         "sessions": [session.isoformat() for session in sessions]},
                "reusable": {"runs": reusable_runs, "t_complete": reusable_t}, "coverage": asfiled_coverage(self.database, self.markets, self.statements),
                "producer": producer()}

    def _pin_block(self) -> dict[str, Any]:
        return {"requested_at": self.price_pinned_at.isoformat(), **{market: dict(pin) for market, pin in self.pins.items()}}


    def run(self, *, start: date | None, end: date | None, max_runs: int | None, stop_before: datetime | None, recompute_existing: bool,
            owner_order_sha256: str | None) -> dict[str, Any]:
        """The runs of the sub-range, in grid order, then the manifest (returned; written by the caller). A run that raises
        stops the invocation: ``stopped`` names the ``T``, the exchange and the error's TYPE; the error is re-raised by the
        caller after the manifest is written (``self.failure``)."""
        bounds, full, sessions = plan(self.pins, step=self.step, start=start, end=end, grid_start=self.grid_start)
        self.failure = None
        entries: list[dict[str, Any]] = []
        computed = 0
        stopped: dict[str, Any] | None = None
        for session in sessions:
            as_of = backtest.t_instant(session)
            found = {market: (None if recompute_existing else reusable_run(self.database, market, as_of, publication_id=self.pins[market]["publication_id"],
                                                                           statements=self.statements)) for market in self.markets}
            needs_run = any(snapshot is None for snapshot in found.values())
            if needs_run and max_runs is not None and computed >= max_runs:
                stopped = {"reason": "max_runs", "at": as_of.isoformat()}
                break
            if needs_run and stop_before is not None and pit._utc(self.clock()) >= stop_before:
                stopped = {"reason": "stop_before", "at": as_of.isoformat()}
                break
            line: dict[str, Any] = {"kind": "t", "as_of": as_of.isoformat(), "session_date": session.isoformat(), "runs": {}}
            started = self.monotonic()
            pending: list[dict[str, Any]] = []
            market = self.markets[0]
            try:
                for market in self.markets:
                    tick = self.monotonic()
                    snapshot = found[market]
                    if snapshot is not None:
                        outputs = pit._mapping(snapshot.get("outputs"))
                        summary = pit._mapping(outputs.get("summary"))
                        entry = _entry(as_of=as_of, session=session, market=market, run_key=str(snapshot["inputs"]["run_key"]), cycle_id=str(snapshot["id"]),
                                       idempotent=True, reused=True, supersedes=pit._mapping(snapshot.get("inputs")).get("supersedes"), summary=summary,
                                       records=len(outputs.get("prediction_identities") or []), history_active=_history_active(outputs.get("rows")))
                    else:
                        service = pit.PitRerunService(self.database, settings=self.settings)
                        receipt, computation = service.rerun(market, as_of=as_of, price_pinned_at=self.price_pinned_at, statements=self.statements)
                        if service.http is not None and service.http.calls != 0:
                            raise pit.PitRerunIntegrityError(f"a grid run made {service.http.calls} network call(s)")
                        if receipt["price_vintage"] != self.pins[market]["publication_id"]:
                            raise GridError(f"the {market} run resolved another publication than the grid's pin")
                        summary = receipt
                        entry = _entry(as_of=as_of, session=session, market=market, run_key=receipt["run_key"], cycle_id=receipt["cycle_id"],
                                       idempotent=bool(receipt["idempotent"]), reused=False, supersedes=receipt["supersedes"], summary=summary,
                                       records=int(receipt["records"]["expected"]), history_active=_history_active(computation.results))
                    pending.append(entry)
                    line["runs"][market] = _line(entry, summary, self.monotonic() - tick)
            except Exception as error:  # the type only: a message may name a symbol
                self.failure = error
                stopped = {"reason": "error", "at": as_of.isoformat(), "market": market, "error": type(error).__name__}
                break
            entries.extend(pending)
            computed += any(snapshot is None for snapshot in found.values())
            line["elapsed_seconds"] = round(self.monotonic() - started, 3)
            self.emit(line)
        done = {entry["session_date"] for entry in entries}
        manifest: dict[str, Any] = {
            "schema": backtest.MANIFEST_SCHEMA, "market": self.market_group, "markets": list(self.markets), "price_pin": self._pin_block(),
            "statements": self.statements, "step_sessions": self.step, "grid_start": self.grid_start.isoformat(), "t_clock": backtest.protocol()["t_clock"],
            "bounds": {"first_eligible": bounds["first_eligible"], "last_eligible": bounds["last_eligible"]},
            "range": {"from": sessions[0].isoformat() if sessions else None, "to": sessions[-1].isoformat() if sessions else None},
            "prereg_grid_sessions": len(full), "grid": entries,
            "complete": all(session.isoformat() in done for session in full), "remaining": sum(1 for session in full if session.isoformat() not in done),
            "stopped": stopped, "producer": producer(), "owner_order_sha256": owner_order_sha256,
        }
        manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)
        return manifest


# ------------------------------------------------------------------ CLI
def _day(parser: argparse.ArgumentParser, option: str, value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        parser.error(f"{option} must be YYYY-MM-DD, got {value!r}")


def main(argv: list[str] | None = None, *, database: Database | None = None, settings: Settings | None = None,
         clock: Callable[[], datetime] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PREREG_VALUATION_PIT_BACKTEST_US_V1: run valuation_pit_rerun over the pre-registered grid (both US exchanges "
                                                 "per T, resumable) and write the grid manifest. Prints aggregates only (JSON lines), never a symbol.")
    parser.add_argument("--market", choices=sorted(MARKET_GROUPS), required=True)
    parser.add_argument("--from", dest="start", default=None, help="first session of the sub-range (YYYY-MM-DD; default: the pre-registered first)")
    parser.add_argument("--to", dest="end", default=None, help="last session of the sub-range (YYYY-MM-DD; default: the pre-registered last)")
    parser.add_argument("--step-sessions", type=int, default=backtest.STEP_SESSIONS, help="every Nth XNYS session (the prereg fixes 5)")
    parser.add_argument("--price-pinned-at", default=None, help="the ONE price pin of the whole grid, ISO-8601 WITH zone, at or before now: the instant right "
                                                                "after the 120-month backfill publications (required but with --host-check)")
    parser.add_argument("--grid-start", default=None, help=f"the first session of the grid (YYYY-MM-DD; default and pre-registered: {backtest.GRID_START.isoformat()})")
    parser.add_argument("--statements", choices=pit.STATEMENTS_MODES, default=backtest.STATEMENTS, help="the re-executor's statements mode (the prereg fixes vintages)")
    parser.add_argument("--manifest-out", type=Path, default=None, help="write the grid manifest to this NEW path (O_EXCL|O_NOFOLLOW, 0600)")
    parser.add_argument("--max-runs", type=int, default=None, help="compute at most N grid instants in this invocation (reused ones are free); resume later")
    parser.add_argument("--stop-before", default=None, help="do not start a grid instant at/after this ISO-8601 instant WITH zone (the operator's window)")
    parser.add_argument("--owner-order-sha256", default=None, help="the sha256 of the owner's order authorising the writes, recorded in the manifest")
    parser.add_argument("--recompute-existing", action="store_true", help="re-run every T through the public API instead of reusing a complete run")
    parser.add_argument("--dry-run", action="store_true", help="print the grid, the pin, the coverage and what is reusable; nothing written")
    parser.add_argument("--host-check", action="store_true", help="print the price publications a cut now sees and the as-filed coverage; nothing written")
    args = parser.parse_args(argv)
    if args.host_check:
        if any(value is not None for value in (args.price_pinned_at, args.manifest_out, args.max_runs, args.start, args.end, args.grid_start)) or args.dry_run:
            parser.error("--host-check takes --market only")
        accuracy.force_read_only_session()
        settings = settings if settings is not None else get_settings()
        database = database if database is not None else Database(settings)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        print(json.dumps(host_check(database, settings, markets=MARKET_GROUPS[args.market], now=now), sort_keys=True, allow_nan=False, default=str))
        return 0
    if args.price_pinned_at is None:
        parser.error("--price-pinned-at is required")
    pinned_at = pit._cli_instant(parser, "--price-pinned-at", args.price_pinned_at)
    grid_start = _day(parser, "--grid-start", args.grid_start)
    stop_before = pit._cli_instant(parser, "--stop-before", args.stop_before) if args.stop_before is not None else None
    start, end = _day(parser, "--from", args.start), _day(parser, "--to", args.end)
    if args.step_sessions <= 0:
        parser.error("--step-sessions must be positive")
    if args.max_runs is not None and args.max_runs < 0:
        parser.error("--max-runs must be >= 0")
    if args.owner_order_sha256 is not None and not _SHA256.match(args.owner_order_sha256):
        parser.error("--owner-order-sha256 must be 64 lowercase hex characters")
    if not args.dry_run:
        if args.manifest_out is None:
            parser.error("--manifest-out is required (except with --dry-run)")
        if args.manifest_out.is_symlink() or args.manifest_out.exists():
            parser.error(f"--manifest-out {args.manifest_out} exists (or is a symlink): the manifest is written to a NEW path only, nothing run")
    elif args.manifest_out is not None or args.max_runs is not None or args.recompute_existing:
        parser.error("--dry-run writes nothing: --manifest-out/--max-runs/--recompute-existing do not apply")
    if args.dry_run:
        accuracy.force_read_only_session()  # libpq reads it at connect time: every transaction of this process is read-only
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings)
    try:
        grid = GridRun(database, settings, market_group=args.market, price_pinned_at=pinned_at, statements=args.statements, step=args.step_sessions, clock=clock,
                       grid_start=grid_start)
        if args.dry_run:
            print(json.dumps(grid.dry_run(start=start, end=end), sort_keys=True, allow_nan=False))
            return 0
        manifest = grid.run(start=start, end=end, max_runs=args.max_runs, stop_before=stop_before, recompute_existing=args.recompute_existing,
                            owner_order_sha256=args.owner_order_sha256)
    except GridError as error:
        parser.error(str(error))
    manifest_out = cast(Path, args.manifest_out)  # required (checked above) whenever this is reached
    pit.write_private_detail(manifest_out, manifest)
    print(json.dumps({"kind": "manifest", "path": str(manifest_out), "manifest_sha256": manifest["manifest_sha256"], "complete": manifest["complete"],
                      "entries": len(manifest["grid"]), "remaining": manifest["remaining"], "stopped": manifest["stopped"], "manifest": manifest},
                     sort_keys=True, allow_nan=False), flush=True)
    if grid.failure is not None:
        raise grid.failure
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
