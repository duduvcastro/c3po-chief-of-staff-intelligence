"""The grid of the US point-in-time backtest (PREREG_VALUATION_PIT_BACKTEST_US_V1 §3, §14): runs ``valuation_pit_rerun`` for
every ``T`` of the pre-registered grid, both US exchanges per ``T``, through its public API, and writes the grid manifest
the report reads (``VALUATION-PIT-GRID-MANIFEST-v1``).

``python -m app.valuation_pit_grid --market US --price-pinned-at <zoned instant> --catalogue-pinned-at <zoned instant>
--statements vintages --step-sessions 5 [--grid-start 2021-06-01] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
--manifest-out <new path> [--max-runs N] [--stop-before <zoned instant>] [--owner-order-sha256 <hex>]
[--expect-producer-sha256 <hex>] [--recompute-existing] [--dry-run]``, and
``python -m app.valuation_pit_grid --market US --host-check`` (read only).

* **The grid** is the report module's (``valuation_pit_backtest_report.eligible_bounds`` / ``prereg_grid``): every
  ``--step-sessions``-th XNYS session from the first on/after ``--grid-start`` (default and pre-registered:
  ``GRID_START`` = 2021-06-01) to the last whose exit label ``T + 1 + 21`` closed before the pinned publication (both
  exchanges' vintages), anchored at the first — ``--from/--to`` select a sub-range of THAT grid, never another grid. ONE
  price pin (the instant right after the 120-month backfill publications of both exchanges) and ONE catalogue pin for the
  whole grid: at start the grid records, per exchange, the publication, the catalogue (snapshot id and classification
  hash), the US Treasury history snapshot and the latest PIT source snapshot of every catalogue name; every run — reused or
  computed — must carry exactly those (else ``GridError``), and the latest run of its ``(exchange, T)`` must be the run
  just accounted for (an A → B → A sequence of inputs would leave the store's latest run another one: ``GridError``).
* **The volume basis of the screen** is decided once per invocation from the pinned publications (``volume_check``: the
  capital events of every catalogue name's series vote on whether the provider's volume is in traded shares or
  split-adjusted) and recorded in the manifest; an undetermined check runs nothing (``GridError``).
* **Each T runs NASDAQ then NYSE** (the re-executor loads one exchange per run; the report unions both runs of a ``T``). A
  ``(exchange, T)`` whose LATEST run already has this code (``source_version``, the producer files and reader objects), this price pin's
  publication and this statements mode, and whose cycle holds exactly its prediction identities, is REUSED without
  recomputation; ``--recompute-existing`` re-runs every ``T`` through the public API instead. Sequential; ``--max-runs N``
  caps the ``T`` COMPUTED in one invocation (reused ones are free); before EVERY exchange's run (reused ones included) the
  invocation stops at/after ``--stop-before``, and before computing an instant it stops when now + 1.5 × the slowest
  computed instant (before any is measured: 300 s per run) reaches it; a SIGTERM stops it between runs
  (``stopped.reason = terminated``). The next invocation resumes. ``--expect-producer-sha256`` refuses to run when the
  producer (files and reader objects: ``producer()["engine_sha256"]``) is not the expected one.
* **Both sources (prereg rev 2)**: right after the V3 run of every ``(exchange, T)`` the grid runs the SERVED internal TP
  (``valuation_pit_served``: ``official_internal_v1`` — the One Pager producer — re-executed on the same point-in-time
  inputs, on the V3 run's pinned vintage when it was just computed), reused under the same rules, checked against the same
  grid inputs and the same A → B → A trap; the manifest lists its runs in ``served_grid`` (each naming its V3 sibling's
  ``run_key``), ``sources`` and ``served_producer``. ``--sources v3_2_shadow`` runs the V3 source alone (the rev-1 grid: no
  served key in the manifest); ``--expect-served-producer-sha256`` refuses another served producer.
* **Output**: stdout carries JSON lines, aggregates only — one line per ``T`` (both runs: run_key, cycle, idempotent,
  reused, evaluated, records, not evaluable by reason, statements basis and coverage, the own-history model count, the
  elapsed seconds and the process's peak RSS) and a final ``manifest`` line with the whole manifest, printed BEFORE the
  manifest is written to ``--manifest-out`` (``O_EXCL | O_NOFOLLOW``, mode 0600: a NEW path in an existing directory),
  with ``manifest_sha256`` = the canonical sha256 of the manifest without that field. On an error the manifest of what
  was done is printed and written (``stopped``: the error's type, never its message) and the error is re-raised — an error
  outside a run (a reuse lookup, a check) included. ``--dry-run`` prints the grid, the pins, the as-filed coverage, how
  many runs are reusable and the volume check; ``--host-check`` prints the price publications a cut now sees, the as-filed
  coverage and the ingestion runs still running (``blocking``: the nightly valuation worker's, and any running for more
  than 30 minutes) — both write nothing, in a read-only session.
"""
from __future__ import annotations

import argparse
import json
import re
import resource
import signal
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, cast

from . import valuation_accuracy_report as accuracy
from . import valuation_pit_backtest_report as backtest
from . import valuation_pit_rerun as pit
from . import valuation_pit_served as served
from .config import Settings, get_settings
from .database import Database
from .valuation_official import canonical_sha256
from .valuation_panel import _NoNetworkHttp
from .valuation_price_history import PriceHistoryService

MARKET_GROUPS: dict[str, tuple[str, ...]] = {backtest.MARKET_GROUP: backtest.MARKETS}
ENGINE_FILES: tuple[str, ...] = pit.IMPLEMENTATION_FILES  # = the run manifest's engine.implementation_file_sha256: the producer's files
ENGINE_OBJECTS: tuple[str, ...] = pit.IMPLEMENTATION_OBJECTS  # = engine.implementation_object_sha256: the Database methods its readers call
PIT_SOURCE_PROVIDERS: tuple[str, ...] = (pit.PROVIDER_EODHD, pit.PROVIDER_FMP)
PREDICTIVE_STOP_FACTOR = 1.5  # stop before an instant when now + 1.5 × the slowest computed instant reaches --stop-before
PRIOR_SECONDS_PER_RUN = 300.0  # until an instant has been measured, one run is assumed to take 300 s (an instant: one run per exchange)
INGESTION_WINDOW = timedelta(hours=12)
INGESTION_LONG_RUNNING = timedelta(minutes=30)  # a run `running` this long blocks a write whatever its source (an IR poll lasts seconds)
NIGHTLY_SOURCE_TYPE = "valuation_worker"  # the nightly valuation worker's runs block a write from their start
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCES: tuple[str, ...] = (backtest.SOURCE, backtest.SERVED_SOURCE)  # rev 2: both sources per (exchange, T): the V3 shadow, then the served internal TP


class GridError(RuntimeError):
    pass


def engine_files() -> dict[str, str]:
    """The producer's files in this code: the sha256 a run manifest names in ``engine.implementation_file_sha256`` (computed
    once per process)."""
    return pit.implementation_files()


def engine_objects() -> dict[str, str]:
    """The producer's ``Database`` reader methods in this code, as ``engine.implementation_object_sha256`` names them."""
    return pit.implementation_objects()


def producer() -> dict[str, Any]:
    """The producer of this code: its files and reader objects, and ``engine_sha256`` = the canonical sha256 of
    ``{files, objects}`` (what ``--expect-producer-sha256`` and the workflow compute from the prereg commit)."""
    files, objects = engine_files(), engine_objects()
    return {"source_version": pit.source_version(), "engine_files": files, "engine_objects": objects,
            "engine_sha256": canonical_sha256({"files": files, "objects": objects})}


def _peak_rss_kb() -> int:
    """The process's peak resident set size in KiB (``ru_maxrss`` is KiB on Linux, bytes on macOS)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak // 1024) if sys.platform == "darwin" else int(peak)


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


def volume_check(database: Database, settings: Settings, pins: Mapping[str, Mapping[str, Any]], markets: Sequence[str],
                 catalogue_pinned_at: datetime | None) -> dict[str, Any]:
    """The screen's volume basis (prereg §2), decided ONCE per invocation from the PINNED publications (read only): the
    votes of every catalogue name's series on whether the provider's volume is in traded shares or split-adjusted
    (``valuation_pit_backtest_report.volume_split_votes``), one series in memory at a time; aggregates only."""
    reader = PriceHistoryService(settings, database, _NoNetworkHttp())
    votes: Counter[str] = Counter()
    series_read = 0
    for market in markets:
        cut = pit._utc(pit._instant(pins[market]["available_at"])) + timedelta(microseconds=1)
        for symbol in pit._catalogue_symbols(database, market, before=catalogue_pinned_at):
            series = reader.series(market, symbol, available_before=cut)
            if series["status"] != "ok" or str(series.get("publication_id")) != str(pins[market]["publication_id"]):
                continue
            series_read += 1
            votes.update(backtest.volume_split_votes(series["bars"]))
    return {**backtest.volume_split_decision(votes), "series_read": series_read}


def resolve_sources(database: Database, markets: Sequence[str], catalogue_pinned_at: datetime) -> dict[str, dict[str, Any]]:
    """What every run of the grid must read, resolved ONCE at start, per exchange (read only): the catalogue the pin resolves
    (snapshot id and the classification hash the run names in its manifest), the US Treasury history snapshot, and the
    publication instant of the latest PIT source snapshot of every catalogue name and provider (``expected``, by
    ``(provider, symbol_sha256)``; summarised in the manifest by count and hash)."""
    treasury = database.latest_analysis_snapshot(pit.SOURCE_ANALYSIS_TYPE, pit.MACRO_TREASURY_KEY)
    resolved: dict[str, dict[str, Any]] = {}
    for market in markets:
        snapshot = pit.catalogue_snapshot(database, market, before=catalogue_pinned_at)
        if snapshot is None:
            raise GridError(f"no {market} catalogue published before the catalogue pin {pit._utc(catalogue_pinned_at).isoformat()}")
        catalogue = pit.admitted_catalogue(snapshot)
        expected: dict[str, str | None] = {}
        for row in catalogue:
            for provider in PIT_SOURCE_PROVIDERS:
                published = database.latest_analysis_snapshot_published_at(pit.SOURCE_ANALYSIS_TYPE, pit.source_entity_key(market, provider, str(row["symbol"])))
                expected[f"{provider}:{pit.symbol_hash(str(row['symbol']))}"] = pit._utc(published).isoformat() if published is not None else None
        resolved[market] = {"catalogue_snapshot_id": str(snapshot["id"]), "classification_sha256": canonical_sha256(catalogue), "catalogue_rows": len(catalogue),
                            "treasury_snapshot_id": str(treasury["id"]) if treasury is not None else None,
                            "pit_sources": sum(1 for value in expected.values() if value is not None), "pit_sources_sha256": canonical_sha256(sorted(expected.items())),
                            "expected": expected}
    return resolved


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
    the producer files), same pinned publication, same statements mode — and its cycle holds exactly its prediction
    identities; else ``None`` (the run is computed through the public API). Read only."""
    snapshot = database.latest_analysis_snapshot_by_inputs(pit.ANALYSIS_TYPE, {"market": market, "as_of": pit._utc(as_of).isoformat()})
    if snapshot is None:
        return None
    inputs, outputs = pit._mapping(snapshot.get("inputs")), pit._mapping(snapshot.get("outputs"))
    if str(inputs.get("source_version")) != pit.source_version():
        return None
    if backtest.producer_of(pit._mapping(inputs.get("manifest"))) != {"files": engine_files(), "objects": engine_objects()}:
        return None
    if str(pit._mapping(inputs.get("price_pin")).get("resolved_publication_id")) != publication_id:
        return None
    if pit._mapping(pit._mapping(outputs.get("summary")).get("statements")).get("mode") != statements:
        return None
    expected = {(str(symbol), str(digest)) for symbol, digest in outputs.get("prediction_identities") or []}
    stored = {(str(symbol), str(record["row_sha256"])) for symbol, record in database.valuation_predictions_for_cycle(str(snapshot["id"]), source=pit.SOURCE).items()}
    return snapshot if stored == expected else None


def check_sources(manifest: Mapping[str, Any], resolved: Mapping[str, Any], *, market: str, catalogue_snapshot_id: str | None) -> list[str]:
    """What a run read against what the grid resolved at start: the catalogue (the pin's snapshot and its classification
    hash), the US Treasury history snapshot, and every PIT source snapshot it names (by publication instant). Returns the
    disagreements (empty: the run read the grid's inputs)."""
    problems: list[str] = []
    if catalogue_snapshot_id != resolved["catalogue_snapshot_id"]:
        problems.append("catalogue_snapshot")
    raw_sources = manifest.get("sources")
    sources: list[Any] = raw_sources if isinstance(raw_sources, list) else []
    hashes = [ref.get("classification_sha256") for ref in sources if isinstance(ref, dict) and ref.get("role") == "catalogue"]
    if hashes != [resolved["classification_sha256"]]:
        problems.append("catalogue_classification")
    curve = pit._mapping(pit._mapping(manifest.get("macro")).get("curve"))
    if str(curve.get("snapshot_id")) != str(resolved["treasury_snapshot_id"]):
        problems.append("treasury_snapshot")
    for ref in sources:
        if isinstance(ref, dict) and ref.get("role") in PIT_SOURCE_PROVIDERS and ref.get("market") == market:
            seen = pit._utc(pit._instant(ref["published_at"])).isoformat() if ref.get("published_at") else None
            if resolved["expected"].get(f"{ref['role']}:{ref.get('symbol_sha256')}") != seen:
                problems.append(f"pit_source:{ref['role']}")
                break
    return problems


def running_ingestions(database: Database, now: datetime) -> dict[str, int]:
    """The ingestion runs still ``running`` that started in the last ``INGESTION_WINDOW`` (read only): ``running`` (all of
    them) and ``blocking`` — the nightly valuation worker's (``NIGHTLY_SOURCE_TYPE``) and any running for more than
    ``INGESTION_LONG_RUNNING`` (never an investor-relations poll of a few seconds): a write of the grid never overlaps them."""
    since, long_ago = pit._utc(now) - INGESTION_WINDOW, pit._utc(now) - INGESTION_LONG_RUNNING
    if not database.database_url:
        runs = cast(dict[str, dict[str, Any]], getattr(database, "_ingestion_runs", {}))
        sources = {str(source.get("id")): str(source.get("source_type")) for source in cast(dict[str, dict[str, Any]], getattr(database, "_data_sources", {})).values()}
        active = [run for run in runs.values() if run.get("status") == "running" and pit._utc(pit._instant(run["started_at"])) >= since]
        blocking = [run for run in active if sources.get(str(run.get("source_id"))) == NIGHTLY_SOURCE_TYPE or pit._utc(pit._instant(run["started_at"])) <= long_ago]
        return {"running": len(active), "blocking": len(blocking)}
    with database.connection() as connection:
        row = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE source.source_type = %s OR run.started_at <= %s) FROM ingestion_runs run "
            "LEFT JOIN data_sources source ON source.id = run.source_id WHERE run.status = 'running' AND run.started_at >= %s",
            (NIGHTLY_SOURCE_TYPE, long_ago, since)).fetchone()
    return {"running": int(row[0]) if row else 0, "blocking": int(row[1]) if row else 0}


def asfiled_coverage(database: Database, markets: Sequence[str], statements: str, *, before: datetime | None = None) -> dict[str, Any]:
    """How deep the as-filed table covers each exchange's catalogue NOW (aggregate): the names ``--statements vintages`` can
    evaluate (a run's own count is ``statements.coverage`` in its receipt). Read only."""
    if statements == "provider":
        return {"mode": statements}
    reader = pit.AsFiledReader(database)
    present = reader.present()
    result: dict[str, Any] = {"mode": statements, "table_present": present}
    for market in markets:
        catalogue = set(pit._catalogue_symbols(database, market, before=before))
        covered = set(reader.coverage(market)) if present else set()
        result[market] = {"catalogue": len(catalogue), "covered_in_catalogue": len(catalogue & covered)}
    return result


def host_check(database: Database, settings: Settings, *, markets: Sequence[str], now: datetime) -> dict[str, Any]:
    """The read-only check before the host steps (prereg §14 a): per exchange, the price publication a cut at ``now`` sees
    (id, availability, window, symbols and bars it holds), the as-filed coverage of the catalogue and the ingestion runs
    still running. Aggregates only."""
    reader = PriceHistoryService(settings, database, _NoNetworkHttp())
    publications: dict[str, Any] = {}
    for market in markets:
        vintage = reader.vintage(market, available_before=now)
        publications[market] = None if vintage is None else {
            "status": vintage["status"], "publication_id": vintage["publication_id"], "available_at": vintage["available_at"], "from": vintage["from"],
            "to": vintage["to"], "symbols": len(vintage["series_sha256"]), "bars": sum(int(count) for count in vintage["series_bars"].values())}
    return {"kind": "host_check", "now": pit._utc(now).isoformat(), "publications": publications, "coverage": asfiled_coverage(database, markets, backtest.STATEMENTS),
            "ingestion_runs": running_ingestions(database, now), "producer": producer(), "served_producer": served.producer()}


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
    """One invocation: the pins, the plan, the runs, the manifest."""

    def __init__(self, database: Database, settings: Settings, *, market_group: str, price_pinned_at: datetime, statements: str, step: int,
                 catalogue_pinned_at: datetime | None = None, clock: Callable[[], datetime] | None = None, monotonic: Callable[[], float] = time.monotonic,
                 emit: Callable[[dict[str, Any]], None] | None = None, grid_start: date | None = None, expect_producer_sha256: str | None = None,
                 sources: Sequence[str] = SOURCES, expect_served_producer_sha256: str | None = None) -> None:
        if market_group not in MARKET_GROUPS:
            raise GridError(f"unknown market group {market_group!r}")
        if not sources or len(set(sources)) != len(sources) or any(source not in SOURCES for source in sources) or sources[0] != backtest.SOURCE:
            raise GridError(f"--sources must start with {backtest.SOURCE} and name sources of {', '.join(SOURCES)} once each")
        if expect_served_producer_sha256 is not None and served.producer()["engine_sha256"] != expect_served_producer_sha256:
            raise GridError("the served producer files of this code are not the expected ones (--expect-served-producer-sha256): nothing runs")
        for name, pin in (("price", price_pinned_at), ("catalogue", catalogue_pinned_at)):
            if pin is not None and (pin.tzinfo is None or pin.utcoffset() is None):
                raise GridError(f"the {name} pin must carry a time zone")
        if statements not in pit.STATEMENTS_MODES:
            raise GridError(f"unknown statements mode {statements!r}")
        if expect_producer_sha256 is not None and producer()["engine_sha256"] != expect_producer_sha256:
            raise GridError("the producer files of this code are not the expected ones (--expect-producer-sha256): nothing runs")
        self.database = database
        self.settings = settings
        self.market_group = market_group
        self.markets = MARKET_GROUPS[market_group]
        self.price_pinned_at = pit._utc(price_pinned_at)
        self.catalogue_pinned_at = pit._utc(catalogue_pinned_at) if catalogue_pinned_at is not None else None
        self.statements = statements
        self.served = backtest.SERVED_SOURCE in sources  # the served internal TP runs right after the V3 run of every (exchange, T)
        self.step = step
        self.grid_start = grid_start or backtest.GRID_START
        self.clock: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.emit: Callable[[dict[str, Any]], None] = emit or (lambda line: print(json.dumps(line, sort_keys=True, allow_nan=False), flush=True))
        now = pit._utc(self.clock())
        for name, pin in (("price", self.price_pinned_at), ("catalogue", self.catalogue_pinned_at)):
            if pin is not None and pin > now:
                raise GridError(f"the {name} pin {pin.isoformat()} is in the future: it would resolve something else when repeated")
        self.pins = resolve_pins(database, settings, self.markets, self.price_pinned_at)
        self.sources = resolve_sources(database, self.markets, self.catalogue_pinned_at) if self.catalogue_pinned_at is not None else None
        self.volume_basis = volume_check(database, settings, self.pins, self.markets, self.catalogue_pinned_at)
        self.failure: BaseException | None = None  # the error that stopped run(), re-raised by the caller once the manifest is written
        self.terminated = False

    def _pin_block(self) -> dict[str, Any]:
        return {"requested_at": self.price_pinned_at.isoformat(), **{market: dict(pin) for market, pin in self.pins.items()}}

    def _catalogue_block(self) -> dict[str, Any] | None:
        if self.sources is None or self.catalogue_pinned_at is None:
            return None
        return {"requested_at": self.catalogue_pinned_at.isoformat(),
                **{market: {key: value for key, value in resolved.items() if key != "expected"} for market, resolved in self.sources.items()}}

    def dry_run(self, *, start: date | None, end: date | None) -> dict[str, Any]:
        bounds, full, sessions = plan(self.pins, step=self.step, start=start, end=end, grid_start=self.grid_start)
        reusable_runs = reusable_t = served_runs = served_t = 0
        for session in sessions:
            found = [reusable_run(self.database, market, backtest.t_instant(session), publication_id=self.pins[market]["publication_id"], statements=self.statements)
                     for market in self.markets]
            reusable_runs += sum(1 for item in found if item is not None)
            reusable_t += all(item is not None for item in found)
            if self.served:
                served_found = [served.reusable_run(self.database, market, backtest.t_instant(session), publication_id=self.pins[market]["publication_id"],
                                                    statements=self.statements) for market in self.markets]
                served_runs += sum(1 for item in served_found if item is not None)
                served_t += all(item is not None for item in served_found)
        result = {"kind": "dry_run", "market": self.market_group, "markets": list(self.markets), "price_pin": self._pin_block(), "catalogue_pin": self._catalogue_block(),
                  "statements": self.statements, "step_sessions": self.step, "grid_start": self.grid_start.isoformat(), "bounds": bounds,
                  "prereg_grid_sessions": len(full),
                  "grid": {"count": len(sessions), "first": sessions[0].isoformat() if sessions else None, "last": sessions[-1].isoformat() if sessions else None,
                           "sessions": [session.isoformat() for session in sessions]},
                  "reusable": {"runs": reusable_runs, "t_complete": reusable_t}, "volume_basis": dict(self.volume_basis),
                  "coverage": asfiled_coverage(self.database, self.markets, self.statements, before=self.catalogue_pinned_at), "producer": producer()}
        if self.served:
            result.update({"sources": list(SOURCES), "served_reusable": {"runs": served_runs, "t_complete": served_t}, "served_producer": served.producer()})
        return result

    def _terminate(self, _signum: int, _frame: Any) -> None:
        self.terminated = True  # checked between runs: the run in flight completes, the manifest is written

    def _stop_reason(self, stop_before: datetime | None, *, predict: float | None) -> str | None:
        if self.terminated:
            return "terminated"
        if stop_before is None:
            return None
        now = pit._utc(self.clock())
        if now >= stop_before:
            return "stop_before"
        if predict is not None and now + timedelta(seconds=PREDICTIVE_STOP_FACTOR * predict) >= stop_before:
            return "stop_before_predicted"
        return None

    def _check(self, market: str, as_of: datetime, manifest: Mapping[str, Any], catalogue_snapshot_id: str | None, run_key: str, *, computed: bool,
               analysis_type: str = pit.ANALYSIS_TYPE) -> None:
        """A run — reused or just computed, of either source (``analysis_type``) — read the grid's inputs and is the latest
        run of its ``(exchange, T)``."""
        if self.sources is not None:
            problems = check_sources(manifest, self.sources[market], market=market, catalogue_snapshot_id=catalogue_snapshot_id)
            if problems:
                raise GridError(f"the {market} run of {as_of.isoformat()} read other inputs than the grid resolved at start ({', '.join(problems)})")
        if computed:  # A → B → A: an idempotent A is not the store's latest run when a B superseded it in between
            latest = self.database.latest_analysis_snapshot_by_inputs(analysis_type, {"market": market, "as_of": as_of.isoformat()})
            if latest is None or str(pit._mapping(latest.get("inputs")).get("run_key")) != run_key:
                raise GridError(f"the latest {market} run of {as_of.isoformat()} is not the run just computed: another run of that instant superseded it")

    def run(self, *, start: date | None, end: date | None, max_runs: int | None, stop_before: datetime | None, recompute_existing: bool,
            owner_order_sha256: str | None) -> dict[str, Any]:
        """The runs of the sub-range, in grid order, then the manifest (returned; printed and written by the caller). Any
        error once the grid has started — a run, a reuse lookup, a check — stops the invocation: ``stopped`` names the
        ``T``, the exchange and the error's TYPE; the error is re-raised by the caller after the manifest is written
        (``self.failure``). A SIGTERM stops it between runs. An undetermined volume basis runs nothing (``GridError``)."""
        bounds, full, sessions = plan(self.pins, step=self.step, start=start, end=end, grid_start=self.grid_start)
        if self.volume_basis["decision"] not in backtest.VOLUME_BASES:
            raise GridError(f"the volume check of the pinned vintages is undetermined ({self.volume_basis['events']} clean capital events, "
                            f"{self.volume_basis['as_traded_like']} as traded, {self.volume_basis['split_adjusted_like']} split-adjusted): nothing runs")
        self.failure = None
        self.terminated = False
        entries: list[dict[str, Any]] = []
        served_entries: list[dict[str, Any]] = []
        computed = 0
        slowest: float | None = None  # the slowest computed instant so far; before the first, PRIOR_SECONDS_PER_RUN per run
        stopped: dict[str, Any] | None = None
        previous = signal.signal(signal.SIGTERM, self._terminate)
        try:
            for session in sessions:
                as_of = backtest.t_instant(session)
                market = self.markets[0]
                try:
                    found = {market: (None if recompute_existing else reusable_run(self.database, market, as_of, publication_id=self.pins[market]["publication_id"],
                                                                                   statements=self.statements)) for market in self.markets}
                    served_found = {market: (None if recompute_existing or not self.served else served.reusable_run(
                        self.database, market, as_of, publication_id=self.pins[market]["publication_id"], statements=self.statements)) for market in self.markets}
                    needs_run = any(snapshot is None for snapshot in found.values()) or (self.served and any(snapshot is None for snapshot in served_found.values()))
                    if needs_run and max_runs is not None and computed >= max_runs:
                        stopped = {"reason": "max_runs", "at": as_of.isoformat()}
                        break
                    expected = slowest if slowest is not None else PRIOR_SECONDS_PER_RUN * len(self.markets) * (2 if self.served else 1)  # a served run per V3 run
                    reason = self._stop_reason(stop_before, predict=expected if needs_run else None)
                    if reason is not None:
                        stopped = {"reason": reason, "at": as_of.isoformat()}
                        break
                    line: dict[str, Any] = {"kind": "t", "as_of": as_of.isoformat(), "session_date": session.isoformat(), "runs": {}}
                    started = self.monotonic()
                    pending: list[dict[str, Any]] = []
                    served_pending: list[dict[str, Any]] = []
                    if self.served:
                        line["served"] = {}
                    for market in self.markets:
                        reason = self._stop_reason(stop_before, predict=None)
                        if reason is not None:  # before EVERY exchange's run: a half-done instant is never listed (its runs are reused next time)
                            stopped = {"reason": reason, "at": as_of.isoformat(), "market": market}
                            break
                        tick = self.monotonic()
                        snapshot = found[market]
                        computation: pit.PitComputation | None = None
                        if snapshot is not None:
                            inputs, outputs = pit._mapping(snapshot.get("inputs")), pit._mapping(snapshot.get("outputs"))
                            summary = pit._mapping(outputs.get("summary"))
                            self._check(market, as_of, pit._mapping(inputs.get("manifest")), pit._mapping(inputs.get("catalogue_pin")).get("resolved_snapshot_id"),
                                        str(inputs["run_key"]), computed=False)
                            entry = _entry(as_of=as_of, session=session, market=market, run_key=str(inputs["run_key"]), cycle_id=str(snapshot["id"]),
                                           idempotent=True, reused=True, supersedes=inputs.get("supersedes"), summary=summary,
                                           records=len(outputs.get("prediction_identities") or []), history_active=_history_active(outputs.get("rows")))
                        else:
                            service = pit.PitRerunService(self.database, settings=self.settings)
                            receipt, computation = service.rerun(market, as_of=as_of, price_pinned_at=self.price_pinned_at, statements=self.statements,
                                                                 catalogue_pinned_at=self.catalogue_pinned_at)
                            if service.http is not None and service.http.calls != 0:
                                raise pit.PitRerunIntegrityError(f"a grid run made {service.http.calls} network call(s)")
                            if receipt["price_vintage"] != self.pins[market]["publication_id"]:
                                raise GridError(f"the {market} run resolved another publication than the grid's pin")
                            self._check(market, as_of, computation.manifest, pit._mapping(receipt.get("catalogue_pin")).get("resolved_snapshot_id"),
                                        str(receipt["run_key"]), computed=True)
                            summary = receipt
                            entry = _entry(as_of=as_of, session=session, market=market, run_key=receipt["run_key"], cycle_id=receipt["cycle_id"],
                                           idempotent=bool(receipt["idempotent"]), reused=False, supersedes=receipt["supersedes"], summary=summary,
                                           records=int(receipt["records"]["expected"]), history_active=_history_active(computation.results))
                        pending.append(entry)
                        line["runs"][market] = _line(entry, summary, self.monotonic() - tick)
                        if self.served:
                            reason = self._stop_reason(stop_before, predict=None)
                            if reason is not None:  # between the V3 run and its served run too: the half-done instant is never listed
                                stopped = {"reason": reason, "at": as_of.isoformat(), "market": market, "source": backtest.SERVED_SOURCE}
                                break
                            tick = self.monotonic()
                            served_entry, served_summary = self._served_run(market, as_of, session, served_found[market], computation, v3_run_key=entry["run_key"])
                            served_pending.append(served_entry)
                            line["served"][market] = _line(served_entry, served_summary, self.monotonic() - tick)
                    if stopped is not None:
                        break
                    entries.extend(pending)
                    served_entries.extend(served_pending)
                    elapsed = self.monotonic() - started
                    if needs_run:
                        computed += 1
                        slowest = elapsed if slowest is None else max(slowest, elapsed)
                    line.update({"elapsed_seconds": round(elapsed, 3), "peak_rss_kb": _peak_rss_kb()})
                    self.emit(line)
                except Exception as error:  # the type only: a message may name a symbol
                    self.failure = error
                    stopped = {"reason": "error", "at": as_of.isoformat(), "market": market, "error": type(error).__name__}
                    break
        finally:
            signal.signal(signal.SIGTERM, previous)
        done = {entry["session_date"] for entry in entries}
        manifest: dict[str, Any] = {
            "schema": backtest.MANIFEST_SCHEMA, "market": self.market_group, "markets": list(self.markets), "price_pin": self._pin_block(),
            "catalogue_pin": self._catalogue_block(), "statements": self.statements, "step_sessions": self.step, "grid_start": self.grid_start.isoformat(),
            "t_clock": backtest.protocol()["t_clock"], "bounds": {"first_eligible": bounds["first_eligible"], "last_eligible": bounds["last_eligible"]},
            "range": {"from": sessions[0].isoformat() if sessions else None, "to": sessions[-1].isoformat() if sessions else None},
            "prereg_grid_sessions": len(full), "grid": entries,
            "complete": all(session.isoformat() in done for session in full), "remaining": sum(1 for session in full if session.isoformat() not in done),
            "stopped": stopped, "producer": producer(), "volume_basis": dict(self.volume_basis), "owner_order_sha256": owner_order_sha256,
        }
        if self.served:  # rev 2: the served internal TP's runs, one per (exchange, T) beside the V3 run (its run_key named), and their producer
            manifest.update({"sources": list(SOURCES), "served_grid": served_entries, "served_producer": served.producer()})
        manifest["manifest_sha256"] = backtest.manifest_sha256(manifest)
        return manifest

    def _served_run(self, market: str, as_of: datetime, session: date, snapshot: Mapping[str, Any] | None, computation: pit.PitComputation | None, *,
                    v3_run_key: str) -> tuple[dict[str, Any], Mapping[str, Any]]:
        """The served internal TP's run of ``(exchange, T)``, right after its V3 run: reused when complete, else computed through
        the served module's public API — on the V3 run's pinned vintage and as-filed reader when it was just computed (their
        caches; the same pins) — and checked as a V3 run is (the grid's inputs, the latest run of its (exchange, T))."""
        if snapshot is not None:
            inputs, outputs = pit._mapping(snapshot.get("inputs")), pit._mapping(snapshot.get("outputs"))
            summary = pit._mapping(outputs.get("summary"))
            self._check(market, as_of, pit._mapping(inputs.get("manifest")), pit._mapping(inputs.get("catalogue_pin")).get("resolved_snapshot_id"),
                        str(inputs["run_key"]), computed=False, analysis_type=served.ANALYSIS_TYPE)
            entry = _entry(as_of=as_of, session=session, market=market, run_key=str(inputs["run_key"]), cycle_id=str(snapshot["id"]), idempotent=True, reused=True,
                           supersedes=inputs.get("supersedes"), summary=summary, records=len(outputs.get("prediction_identities") or []), history_active=0)
            return {**entry, "v3_run_key": v3_run_key}, summary
        service = served.PitServedService(self.database, settings=self.settings)
        receipt, run = service.rerun(market, as_of=as_of, price_pinned_at=self.price_pinned_at, statements=self.statements, catalogue_pinned_at=self.catalogue_pinned_at,
                                     prices=computation.resolver.prices if computation is not None else None,
                                     vintages=computation.resolver.vintages if computation is not None else None)
        if service.http is not None and service.http.calls != 0:
            raise pit.PitRerunIntegrityError(f"a served grid run made {service.http.calls} network call(s)")
        if receipt["price_vintage"] != self.pins[market]["publication_id"]:
            raise GridError(f"the served {market} run resolved another publication than the grid's pin")
        self._check(market, as_of, run.manifest, pit._mapping(receipt.get("catalogue_pin")).get("resolved_snapshot_id"), str(receipt["run_key"]), computed=True,
                    analysis_type=served.ANALYSIS_TYPE)
        entry = _entry(as_of=as_of, session=session, market=market, run_key=receipt["run_key"], cycle_id=receipt["cycle_id"], idempotent=bool(receipt["idempotent"]),
                       reused=False, supersedes=receipt["supersedes"], summary=receipt, records=int(receipt["records"]["expected"]), history_active=0)
        return {**entry, "v3_run_key": v3_run_key}, receipt


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
    parser.add_argument("--catalogue-pinned-at", default=None, help="the ONE catalogue pin of the whole grid, ISO-8601 WITH zone, at or before now (required "
                                                                    "but with --host-check)")
    parser.add_argument("--grid-start", default=None, help=f"the first session of the grid (YYYY-MM-DD; default and pre-registered: {backtest.GRID_START.isoformat()})")
    parser.add_argument("--statements", choices=pit.STATEMENTS_MODES, default=backtest.STATEMENTS, help="the re-executor's statements mode (the prereg fixes vintages)")
    parser.add_argument("--manifest-out", type=Path, default=None, help="write the grid manifest to this NEW path (O_EXCL|O_NOFOLLOW, 0600) in an existing directory")
    parser.add_argument("--max-runs", type=int, default=None, help="compute at most N grid instants in this invocation (reused ones are free); resume later")
    parser.add_argument("--stop-before", default=None, help="do not start a run at/after this ISO-8601 instant WITH zone (the operator's window)")
    parser.add_argument("--owner-order-sha256", default=None, help="the sha256 of the owner's order authorising the writes, recorded in the manifest")
    parser.add_argument("--expect-producer-sha256", default=None, help="refuse to run unless the canonical sha256 of the producer files is this one")
    parser.add_argument("--expect-served-producer-sha256", default=None, help="refuse to run unless the canonical sha256 of the served producer is this one")
    parser.add_argument("--sources", default=",".join(SOURCES), help=f"comma-separated sources per (exchange, T) (the prereg rev 2 fixes {','.join(SOURCES)}; "
                                                                      f"{SOURCES[0]} alone is the rev-1 grid)")
    parser.add_argument("--recompute-existing", action="store_true", help="re-run every T through the public API instead of reusing a complete run")
    parser.add_argument("--dry-run", action="store_true", help="print the grid, the pins, the coverage and what is reusable; nothing written")
    parser.add_argument("--host-check", action="store_true", help="print the price publications a cut now sees, the as-filed coverage and the running ingestions")
    args = parser.parse_args(argv)
    if args.host_check:
        if any(value is not None for value in (args.price_pinned_at, args.catalogue_pinned_at, args.manifest_out, args.max_runs, args.start, args.end,
                                               args.grid_start)) or args.dry_run:
            parser.error("--host-check takes --market only")
        accuracy.force_read_only_session()
        settings = settings if settings is not None else get_settings()
        database = database if database is not None else Database(settings)
        now = (clock or (lambda: datetime.now(timezone.utc)))()
        print(json.dumps(host_check(database, settings, markets=MARKET_GROUPS[args.market], now=now), sort_keys=True, allow_nan=False, default=str))
        return 0
    if args.price_pinned_at is None or args.catalogue_pinned_at is None:
        parser.error("--price-pinned-at and --catalogue-pinned-at are required")
    pinned_at = pit._cli_instant(parser, "--price-pinned-at", args.price_pinned_at)
    catalogue_pinned_at = pit._cli_instant(parser, "--catalogue-pinned-at", args.catalogue_pinned_at)
    grid_start = _day(parser, "--grid-start", args.grid_start)
    stop_before = pit._cli_instant(parser, "--stop-before", args.stop_before) if args.stop_before is not None else None
    start, end = _day(parser, "--from", args.start), _day(parser, "--to", args.end)
    if args.step_sessions <= 0:
        parser.error("--step-sessions must be positive")
    if args.max_runs is not None and args.max_runs < 0:
        parser.error("--max-runs must be >= 0")
    sources = tuple(source.strip() for source in str(args.sources).split(",") if source.strip())
    for option, value in (("--owner-order-sha256", args.owner_order_sha256), ("--expect-producer-sha256", args.expect_producer_sha256),
                          ("--expect-served-producer-sha256", args.expect_served_producer_sha256)):
        if value is not None and not _SHA256.match(value):
            parser.error(f"{option} must be 64 lowercase hex characters")
    if not args.dry_run:
        if args.manifest_out is None:
            parser.error("--manifest-out is required (except with --dry-run)")
        if args.manifest_out.is_symlink() or args.manifest_out.exists():
            parser.error(f"--manifest-out {args.manifest_out} exists (or is a symlink): the manifest is written to a NEW path only, nothing run")
        parent = args.manifest_out.parent
        if parent.is_symlink() or not parent.is_dir():
            parser.error(f"--manifest-out's directory {parent} does not exist (or is a symlink): nothing run")
    elif args.manifest_out is not None or args.max_runs is not None or args.recompute_existing:
        parser.error("--dry-run writes nothing: --manifest-out/--max-runs/--recompute-existing do not apply")
    if args.dry_run:
        accuracy.force_read_only_session()  # libpq reads it at connect time: every transaction of this process is read-only
    settings = settings if settings is not None else get_settings()
    database = database if database is not None else Database(settings)
    try:
        grid = GridRun(database, settings, market_group=args.market, price_pinned_at=pinned_at, catalogue_pinned_at=catalogue_pinned_at, statements=args.statements,
                       step=args.step_sessions, clock=clock, grid_start=grid_start, expect_producer_sha256=args.expect_producer_sha256, sources=sources,
                       expect_served_producer_sha256=args.expect_served_producer_sha256)
        if args.dry_run:
            print(json.dumps(grid.dry_run(start=start, end=end), sort_keys=True, allow_nan=False))
            return 0
        manifest = grid.run(start=start, end=end, max_runs=args.max_runs, stop_before=stop_before, recompute_existing=args.recompute_existing,
                            owner_order_sha256=args.owner_order_sha256)
    except GridError as error:
        parser.error(str(error))
    manifest_out = cast(Path, args.manifest_out)  # required (checked above) whenever this is reached
    print(json.dumps({"kind": "manifest", "path": str(manifest_out), "manifest_sha256": manifest["manifest_sha256"], "complete": manifest["complete"],
                      "entries": len(manifest["grid"]), "remaining": manifest["remaining"], "stopped": manifest["stopped"], "manifest": manifest},
                     sort_keys=True, allow_nan=False), flush=True)  # printed BEFORE the file is written: a failing write never loses the manifest
    pit.write_private_detail(manifest_out, manifest)
    if grid.failure is not None:
        raise grid.failure
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
