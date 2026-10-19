"""The US point-in-time backtest of the SERVED internal TP and of the Valuation V3.2 internal TP —
PREREG_VALUATION_PIT_BACKTEST_US_V1 (``c3po/docs/PREREG_VALUATION_PIT_BACKTEST_US_V1.md``), rev 2: ONE look, read-only.

Rev 2 (owner, 19/10/2026): the receipt carries TWO verdicts, the same rule computed separately per source —
``served_internal_tp`` (PRIMARY: ``official_internal_v1``, the One Pager producer served from 20/10, re-executed
point-in-time by ``valuation_pit_served``; its records live in the ``valuation_pit_served`` run snapshots of the manifest's
``served_grid``) and ``v3_shadow`` (secondary: the rev-1 reading below, unchanged, still at the payload's top level). Each
is its own pre-registered decision at ``ALPHA`` (no multiplicity correction: different questions); a shared failure voids
both, a source's own runs or records void its verdict only; labels are read once per (symbol, session).

Question: does the internal TP of the V3 engine (no consensus inside), RE-EXECUTED point-in-time by
``valuation_pit_rerun`` from as-filed SEC statements (``--statements vintages``) on a grid of past instants ``T``, rank
the next EXECUTABLE returns of the US cross-section (NASDAQ ∪ NYSE, one cross-section per XNYS session)?

MEASUREMENT, NEVER A GATE: nothing served changes, nothing is written, nothing is fetched. The report reads:

* the GRID MANIFEST (``VALUATION-PIT-GRID-MANIFEST-v1``, written by ``valuation_pit_grid``, complete): the binding list of
  the ``valuation_pit_rerun`` runs that form the backtest — one per XNYS session ``D`` of the pre-registered grid (every
  5th session from the first on/after ``GRID_START`` = 2021-06-01 to the last whose exit label closed before the pinned
  publication: the one-off 120-month backfill of the price series) and per US exchange, ``T`` = 01:00 America/Sao_Paulo
  of the civil day after ``D``, one pinned catalogue for the whole grid — with its own ``manifest_sha256``;
* the run snapshots of the manifest: present, current (not superseded), complete, one producer, one catalogue and one
  as-filed coverage per exchange across the grid, and their aggregate coverage and screen inputs;
* the ``v3_2_shadow`` records of those runs ONLY (``run_not_in_manifest`` otherwise), under the PIT panel's rules (a
  superseded run refused, an unattested consensus horizon read as missing) and the panel's admissibility; every PIT
  record is ``retrospective`` by construction: the cohort is counted, never filtered;
* the labels of the SAME pinned price publication the grid ran on (per exchange, the cut ``available_at + 1 µs``) through
  ``PriceHistoryService.label_bar`` and the panel's observation — read ONLY when the reading is valid: a VOID reading
  reveals no statistic.

The decisory cross-section of each ``T`` is a POINT-IN-TIME SCREEN of the catalogue's stocks (the 2026 screener's rules
applied at ``T``: no ETF, close ≥ $3, market cap at ``T`` ≥ $750M, median dollar volume of the last 20 sessions ≥ $20M,
then the 300 most liquid per exchange) — the catalogue is the 2026 screener's output, selected on what happened after
``T``. On the screened union, per horizon (21 decisory; 63/126 descriptive): the accuracy report's ``horizon_report``
(``valuation_accuracy_report``: executable and total-return rank IC, decile spreads, log-MSE vs the random walk, block
standard errors on the calendar session index from the grid's first session, factor 1.5, Student t with ``B − 1`` df);
the halves of the decisory blocks; a persistence co-condition (63-session blocks, factor ``PERSISTENCE_VARIANCE_FACTOR``);
the coverage floor; and the single-look verdict VOID → UNMEASURED → NEGATIVE → PASS → FAIL. Descriptive: the unscreened
catalogue's IC, per exchange, with the upside ranked within its exchange, per calendar year, the realized per-session sd.

The receipt (``VALUATION-PIT-BACKTEST-REPORT-v1``) carries NO symbol and no wall clock in its payload: it is a function of
(manifest, store, code). The code is bound to the prereg (``code_fingerprint`` / ``PINNED_FILES`` / ``PINNED_OBJECTS``, the
accuracy report's binding machinery). The process forces a read-only PostgreSQL session and reaches five store readers.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import random
import re
import statistics
import sys
from collections import Counter
from datetime import date, datetime, time as wall_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence, cast
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from . import valuation_accuracy_report as accuracy
from . import valuation_panel as panel
from . import valuation_pit_panel as pit_panel
from . import valuation_price_history as price_history_module
from .config import Settings, get_settings
from .database import Database
from .valuation_official import SOURCE_V3_2_SHADOW, CalendarUnavailable, canonical_sha256, session_date_of
from .valuation_price_history import PriceHistoryService

SCHEMA_VERSION = "VALUATION-PIT-BACKTEST-REPORT-v1"
MANIFEST_SCHEMA = "VALUATION-PIT-GRID-MANIFEST-v1"
PREREG = "PREREG_VALUATION_PIT_BACKTEST_US_V1"
PREREG_REVISION = 2
SOURCE = SOURCE_V3_2_SHADOW
RUN_ANALYSIS_TYPE = pit_panel.PIT_RERUN_ANALYSIS_TYPE  # one snapshot per valuation_pit_rerun run
# rev 2 (owner, 19/10/2026: the Friday verdict must be about the TP SERVED from 20/10): the served internal TP (official_internal_v1) re-executed
# point-in-time by valuation_pit_served on the same PIT inputs — its records live in its run snapshots (never in valuation_predictions)
SERVED_SOURCE = "official_internal_pit"  # = valuation_pit_served.SOURCE (pinned by test)
SERVED_RUN_ANALYSIS_TYPE = "valuation_pit_served"  # = valuation_pit_served.ANALYSIS_TYPE: one snapshot per served run, its records inside
SERVED_TP_SOURCE = "official_internal_v1"  # the source the served runs re-execute
VERDICTS: dict[str, str] = {"served_internal_tp": SERVED_SOURCE, "v3_shadow": SOURCE}  # verdict → source; each its own pre-registered decision at ALPHA
PRIMARY_VERDICT = "served_internal_tp"  # the answer the owner asked for; v3_shadow is secondary — both always reported, no multiplicity correction
# --- protocol constants, pre-registered (prereg §13); every one of them travels inside the hashed payload
MARKET_GROUP = "US"
MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")  # one cross-section per XNYS session: the union of both exchanges' runs of the same T
CALENDAR_MARKET = "NASDAQ"  # the XNYS calendar (both exchanges)
STATEMENTS = "vintages"  # --statements vintages: as-filed SEC statements only; an uncovered name is not evaluable (counted)
STEP_SESSIONS = 5  # every 5th XNYS session of the grid
GRID_START = date(2021, 6, 1)  # the first T: the first XNYS session on/after it (calendar-year filers have FY2016–FY2020 statements AND year-end prices
#                                in the 120-month vintage: five fiscal years, the engine's own-history minimum); another start is a prereg revision
MIN_PRIOR_SESSIONS = 252  # and at least 252 sessions of the pinned vintage before it (beta window, admissibility): never binding on a 120-month vintage
PRICE_VINTAGE_FROM_LATEST = date(2016, 12, 1)  # a pinned vintage whose window starts later is not the 120-month backfill
T_ZONE = ZoneInfo("America/Sao_Paulo")
T_HOUR = 1  # T = 01:00 America/Sao_Paulo of the civil day after session D (the nightly cycle runs after the close): session_date = D
HORIZONS: tuple[int, ...] = (21, 63, 126)  # sessions; 63/126 descriptive
PRIMARY_HORIZON = 21
EXECUTION_LAG_SESSIONS = accuracy.EXECUTION_LAG_SESSIONS  # the executable return enters at the close of T + 1
DECISORY_STATISTIC = "ic_executable"
MIN_BLOCKS = 12
IC_MIN = 0.02
ALPHA = 0.05  # one-sided, single look: p_greater <= ALPHA
ALPHA_NEGATIVE = 0.05  # p_less <= ALPHA_NEGATIVE → NEGATIVE
ATTRITION_CAP = accuracy.ATTRITION_CAP
# the persistence co-condition of the pass: the same per-session values in blocks of 63 calendar sessions; the factor is the exact one of the triangular
# model (21-session overlap) for this grid's sampling (every 5th session, the last block partial): adjacent 63-block means correlate at ρ₁ ≈ 0.06;
# with the partial last block the exact factor is 1.14 — prereg §6.5
PERSISTENCE_BLOCK_SESSIONS = 63
PERSISTENCE_VARIANCE_FACTOR = 1.14
# the point-in-time screen of the decisory cross-section: the 2026 screener's rules (market_data.us_screener) applied at T
SCREEN_SECURITY_TYPE = "Stock"
SCREEN_MIN_CLOSE = 3.0
SCREEN_MIN_MARKET_CAP = 750_000_000.0
SCREEN_MIN_DOLLAR_VOLUME = 20_000_000.0
SCREEN_TOP_PER_EXCHANGE = 300
# the screen's dollar volume: the provider's volume may be split-adjusted while the close is as-traded; the volume check of the pinned vintages
# (volume_split_check, prereg §2) decides the basis ONCE per grid and the manifest records it: "as_traded" → close × volume, "split_adjusted" →
# close × volume ÷ S(s), S(s) the split-only factor of the later capital events (never the total-return adjusted_close: it carries every dividend
# paid after s). The rerun records both medians.
VOLUME_BASES: dict[str, str] = {"as_traded": "dollar_volume_median_20", "split_adjusted": "split_adjusted_dollar_volume_median_20"}
VOLUME_CHECK_MIN_FACTOR = 1.5  # a capital event of the check: the close/adjusted-close ratio moves by ≥ this factor between two valid sessions
VOLUME_CHECK_WINDOW = 20  # valid sessions of volume before and from the event (no other event inside)
VOLUME_CHECK_MIN_EVENTS = 3
VOLUME_CHECK_MIN_AGREEMENT = 2 / 3  # the share of the events that must agree for a decision; else "undetermined" (the grid refuses to run)
# the coverage floor: below it the reading does not measure the pre-registered cross-section (UNMEASURED)
COVERAGE_MIN_RECORDS_SHARE = 0.60  # US records / US catalogue stocks, over the grid
COVERAGE_MIN_SCREENED_NAMES = 150  # median over EVERY grid session (zero included) of screened names with an executable return at h = 21
ALLOWED_REFUSALS: tuple[str, ...] = ("duplicate_across_exchanges", "run_not_in_manifest")  # any other refused record VOIDs the reading
HISTORY_MODEL = "own_history"  # the engine's own-history model (P/E, P/B: >= 5 fiscal years) — its coverage is read, never decisory
READ_ONLY_PGOPTION = accuracy.READ_ONLY_PGOPTION
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
VERDICT_ORDER: tuple[str, ...] = ("VOID", "UNMEASURED", "NEGATIVE", "PASS", "FAIL")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# --- the code the numbers come from, bound to the prereg (§15): this module and the instrument it reuses, whole files;
#     single objects of the modules shared with the app (the store's readers, the PIT panel's two rules, the official clocks)
PINNED_FILES: tuple[str, ...] = ("valuation_pit_backtest_report.py", "valuation_accuracy_report.py", "valuation_panel.py", "valuation_price_history.py")
PINNED_OBJECTS: tuple[str, ...] = (
    *accuracy.PINNED_OBJECTS,
    "database.Database.latest_analysis_snapshot_by_inputs",
    "valuation_official.SOURCE_V3_2_SHADOW",
    "valuation_pit_panel.PIT_RERUN_ANALYSIS_TYPE", "valuation_pit_panel.UNATTESTED_HORIZONS", "valuation_pit_panel.superseded_run_keys",
    "valuation_pit_panel.refuse_superseded_runs", "valuation_pit_panel._unattested_horizon", "valuation_pit_panel._as_missing_horizon",
)
# --- the operating characteristics the prereg publishes (§8): reproducible with ``design_table()``
DESIGN_SEED = 20261023
DESIGN_REPS = 20000
DESIGN_SDS: tuple[float, ...] = (0.06, 0.08, 0.10, 0.12, 0.15, 0.20)
DESIGN_ICS: tuple[float, ...] = (-0.03, 0.0, 0.02, 0.03, 0.04, 0.05, 0.065, 0.08)
DESIGN_INSTANTS: tuple[int, ...] = (51, 101, 266)  # grids of 12, 24 and 64 blocks of 21 sessions; 266 = the 2021-06 → 2026-09 grid (last block: one instant)


class ManifestError(ValueError):
    """The grid manifest is not a ``VALUATION-PIT-GRID-MANIFEST-v1`` whose hash recomputes: nothing is read from it."""


def protocol() -> dict[str, Any]:
    """The pre-registered constants, as the receipt carries them (inside the hashed payload)."""
    return {
        "schema": SCHEMA_VERSION,
        "prereg": PREREG,
        "prereg_revision": PREREG_REVISION,
        "market_group": MARKET_GROUP,
        "markets": list(MARKETS),
        "calendar": dict(panel.CALENDARS)[CALENDAR_MARKET],
        "source": SOURCE,
        "verdicts": {"primary": PRIMARY_VERDICT, "sources": dict(VERDICTS), "served_tp_source": SERVED_TP_SOURCE,
                     "served_runs": SERVED_RUN_ANALYSIS_TYPE, "served_records": "the records inside the served run snapshots of the manifest's served_grid",
                     "rule": "the same verdict (every condition of the single look) computed separately for each source, each its own pre-registered "
                             "decision at alpha; no multiplicity correction between them (they answer different questions); both always reported",
                     "void": "a shared failure (code, manifest parameters, label vintages, grid) voids both; a source's own runs or records void its verdict only",
                     "look": "a reading spends the single look when any verdict is not VOID"},
        "statements": STATEMENTS,
        "universe": "the catalogue of each exchange pinned for the whole grid (the 2026 screener's output: selected on the outcome), screened point-in-time",
        "screen": {"security_type": SCREEN_SECURITY_TYPE, "min_close": SCREEN_MIN_CLOSE, "min_market_cap": SCREEN_MIN_MARKET_CAP,
                   "min_dollar_volume_median_20": SCREEN_MIN_DOLLAR_VOLUME, "top_per_exchange": SCREEN_TOP_PER_EXCHANGE,
                   "rank": ("median dollar volume of the last 20 sessions <= T on the grid's volume basis (traded shares: close x volume; split-adjusted "
                            "shares: close x volume / the split-only factor of the later capital events, never the total-return adjusted close), "
                            "descending; ties by symbol"),
                   "applies_to": "every verdict condition; the unscreened catalogue is descriptive",
                   "volume_basis": {"rule": "volume_split_check of the pinned vintages, decided once per grid and recorded in the manifest",
                                    "as_traded": "close x volume", "split_adjusted": "close x volume / S(s), S(s) = the product of the split-only factors "
                                    "(close/adjusted_close jumps >= 1.25) after session s", "min_factor": VOLUME_CHECK_MIN_FACTOR,
                                    "window_sessions": VOLUME_CHECK_WINDOW, "min_events": VOLUME_CHECK_MIN_EVENTS,
                                    "min_agreement": VOLUME_CHECK_MIN_AGREEMENT, "undetermined": "the grid does not run; a manifest without a decision is VOID"}},
        "step_sessions": STEP_SESSIONS,
        "grid_start": GRID_START.isoformat(),
        "min_prior_sessions": MIN_PRIOR_SESSIONS,
        "grid": ("every step_sessions-th XNYS session from the first on/after grid_start (with min_prior_sessions sessions of the pinned vintage before "
                 "it) to the last whose exit label T + 1 + primary_horizon closed before the pinned publication (both exchanges' vintages); a grid that "
                 "cannot start at grid_start is not the pre-registered grid"),
        "price_vintage": "the one-off 120-month backfill publication of each exchange, pinned for the whole grid",
        "price_vintage_from_latest": PRICE_VINTAGE_FROM_LATEST.isoformat(),
        "t_clock": f"{T_HOUR:02d}:00 {T_ZONE.key} of the civil day after session D (session_date = D)",
        "price_pin": "one --price-pinned-at for the whole grid; labels read from the same pinned publication of each exchange (cut = available_at + 1 µs)",
        "catalogue_pin": "one --catalogue-pinned-at for the whole grid: one catalogue (classification hash) per exchange across every run",
        "statements_stability": "statements.coverage.covered_in_catalogue (the pinned catalogue's as-filed coverage) equal across the runs of an exchange",
        "horizons_sessions": list(HORIZONS),
        "primary_horizon": PRIMARY_HORIZON,
        "execution_lag_sessions": EXECUTION_LAG_SESSIONS,
        "decisory_statistic": DECISORY_STATISTIC,
        "tp_horizon_sessions": accuracy.TP_HORIZON_SESSIONS,
        "min_names_per_session": accuracy.MIN_NAMES_PER_SESSION,
        "min_names_deciles": accuracy.MIN_NAMES_DECILES,
        "deciles": accuracy.DECILES,
        "block_length": "h XNYS sessions on the calendar session index from the grid's first session; complete blocks only (PREREG_VALUATION_DECISOR_V1 §5)",
        "adjacent_block_variance_factor": accuracy.ADJACENT_BLOCK_VARIANCE_FACTOR,
        "persistence": {"block_sessions": PERSISTENCE_BLOCK_SESSIONS, "variance_factor": PERSISTENCE_VARIANCE_FACTOR, "alpha": ALPHA,
                        "test": "the same per-session decisory values in blocks of 63 calendar sessions; Student t with B63 - 1 df"},
        "min_blocks": MIN_BLOCKS,
        "ic_min": IC_MIN,
        "alpha": ALPHA,
        "alpha_negative": ALPHA_NEGATIVE,
        "attrition_cap": ATTRITION_CAP,
        "attrition_decisory": "executable pair: denominator = target T + 1 + h closed before the label cut; unavailable = either label of the pair missing",
        "coverage_floor": {"min_records_share": COVERAGE_MIN_RECORDS_SHARE, "min_screened_names_median": COVERAGE_MIN_SCREENED_NAMES,
                           "records_share": "US records / US catalogue stocks over the grid",
                           "screened_names_median": "median over every grid session (zero included) of screened names with an executable return at the "
                                                    "primary horizon"},
        "allowed_refusals": list(ALLOWED_REFUSALS),
        "halves": "the first floor(B/2) and the last floor(B/2) complete blocks of the decisory statistic (the middle block out when B is odd)",
        "pass": "B >= min_blocks, IC estimate >= ic_min, p_greater <= alpha, executable decile spread estimate > 0, IC estimate > 0 in both halves, "
                "persistence p_greater <= alpha, executable attrition <= attrition_cap, coverage floor met",
        "negative": "p_less <= alpha_negative on the decisory statistic",
        "unmeasured": "no eligible executable observation, executable attrition above the cap, or the coverage floor not met",
        "void": "the reading is not valid under the prereg; no statistic is computed or published",
        "verdict_order": list(VERDICT_ORDER),
        "look": "single",
        "upside": "tp / price - 1 (the record's tp and price)",
        "return_executable": "adjusted_close(T + 1 + h) / adjusted_close(T + 1) - 1: decisory",
        "return": "adjusted_close(T + h) / adjusted_close(T) - 1: descriptive",
        "cohort": "every record is retrospective by construction (a re-execution): counted, never filtered",
        "admissibility": "valuation_panel.admissible_records; valuation_pit_panel superseded_run and unattested horizon; run_key in the manifest",
        "label_convention": panel.LABEL_CONVENTION,
        "tol_basis": panel.TOL_BASIS,
        "history_model": HISTORY_MODEL,
        "code_pins": {"files": list(PINNED_FILES), "objects": list(PINNED_OBJECTS)},
        "gate": False,
    }


# ------------------------------------------------------------------ the grid (pure: the calendar and the pinned vintages' windows)
def _calendar() -> Any:
    return price_history_module._calendar(CALENDAR_MARKET)


def t_instant(session: date) -> datetime:
    """``T`` of session ``D``: 01:00 America/Sao_Paulo of the civil day after ``D``, in UTC — checked to belong to ``D``
    (``valuation_official.session_date_of``: the last session closed at ``T``)."""
    instant = datetime.combine(session + timedelta(days=1), wall_time(T_HOUR, 0), tzinfo=T_ZONE).astimezone(timezone.utc)
    if session_date_of(CALENDAR_MARKET, instant) != session.isoformat():
        raise ValueError(f"T {instant.isoformat()} does not belong to session {session.isoformat()}")
    return instant


def _vintage_sessions(vintage: Mapping[str, Any]) -> list[date]:
    """The XNYS sessions of a vintage's window ``[from, to]`` that closed before its publication (``available_at``)."""
    available_at = panel._utc(vintage["available_at"])
    sessions = [stamp.date() for stamp in _calendar().sessions_in_range(str(vintage["from"])[:10], str(vintage["to"])[:10])]
    return [day for day in sessions if price_history_module.session_close(CALENDAR_MARKET, day) < available_at]


def first_session_on_or_after(day: date) -> date:
    """The first XNYS session on or after ``day``."""
    return _calendar().date_to_session(day.isoformat(), direction="next").date()


def eligible_bounds(vintages: Mapping[str, Mapping[str, Any] | None], *, grid_start: date | None = None) -> dict[str, Any]:
    """The first and last session of the grid given each exchange's pinned vintage (``status = ok``, ``from``, ``to``,
    ``available_at``): first = the later of the first session on/after ``grid_start`` (default ``GRID_START``) and the
    session with ``MIN_PRIOR_SESSIONS`` sessions of the window before it; last = the session whose exit label ``T + 1 +
    PRIMARY_HORIZON`` is the last session of the window that closed before the publication. Intersected over the
    exchanges; ``None`` when a vintage is not usable or too short. ``starts_at_grid_start`` says whether the vintages let
    the grid begin where it was asked to (a 36-month vintage cannot start a 2021 grid)."""
    start = first_session_on_or_after(grid_start or GRID_START)
    exit_lag = PRIMARY_HORIZON + EXECUTION_LAG_SESSIONS
    per_market: dict[str, Any] = {}
    firsts: list[date] = []
    lasts: list[date] = []
    usable = True
    for market in MARKETS:
        vintage = vintages.get(market)
        if not vintage or vintage.get("status") != "ok":
            per_market[market] = None
            usable = False
            continue
        sessions = _vintage_sessions(vintage)
        if len(sessions) <= MIN_PRIOR_SESSIONS + exit_lag:
            per_market[market] = {"sessions": len(sessions), "first_eligible": None, "last_eligible": None}
            usable = False
            continue
        first, last = max(sessions[MIN_PRIOR_SESSIONS], start), sessions[-1 - exit_lag]
        per_market[market] = {"sessions": len(sessions), "first_session": sessions[0].isoformat(), "first_eligible": first.isoformat(),
                              "last_eligible": last.isoformat(), "last_label_session": sessions[-1].isoformat()}
        firsts.append(first)
        lasts.append(last)
    if not usable or max(firsts) > min(lasts):
        return {"grid_start": start.isoformat(), "first_eligible": None, "last_eligible": None, "starts_at_grid_start": False, "per_market": per_market}
    return {"grid_start": start.isoformat(), "first_eligible": max(firsts).isoformat(), "last_eligible": min(lasts).isoformat(),
            "starts_at_grid_start": max(firsts) == start, "per_market": per_market}


def prereg_grid(bounds: Mapping[str, Any], *, step: int | None = None) -> list[date]:
    """Every ``step``-th XNYS session from ``first_eligible`` to ``last_eligible`` (anchored at the first: a sub-range of the
    grid is always a subset of it)."""
    step = STEP_SESSIONS if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")
    if not bounds.get("first_eligible") or not bounds.get("last_eligible"):
        return []
    sessions = [stamp.date() for stamp in _calendar().sessions_in_range(bounds["first_eligible"], bounds["last_eligible"])]
    return sessions[::step]


# ------------------------------------------------------------------ the manifest (shared with valuation_pit_grid)
def producer_of(run_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """A run's producer as its manifest names it: the files (``engine.implementation_file_sha256``) and the ``Database``
    methods its readers call (``engine.implementation_object_sha256``)."""
    engine = panel._mapping(run_manifest.get("engine"))
    return {"files": engine.get("implementation_file_sha256"), "objects": engine.get("implementation_object_sha256")}


def volume_basis(manifest: Mapping[str, Any]) -> str | None:
    """The screen's dollar-volume basis the grid decided (``volume_split_check`` of the pinned vintages, recorded in the
    manifest): ``as_traded`` or ``split_adjusted``; ``None`` when the manifest records no decision (the reading is VOID)."""
    decision = panel._mapping(manifest.get("volume_basis")).get("decision")
    return str(decision) if decision in VOLUME_BASES else None


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    """The canonical sha256 of a manifest without its own ``manifest_sha256`` field."""
    return canonical_sha256({key: value for key, value in manifest.items() if key != "manifest_sha256"})


MANIFEST_ENTRY_KEYS: tuple[str, ...] = ("as_of", "session_date", "market", "run_key", "cycle_id", "idempotent", "evaluated", "not_evaluable")


def load_manifest(text: str) -> dict[str, Any]:
    """A grid manifest, validated: the schema, the hash, one entry per ``(T, exchange)`` with the fields the report reads,
    a 64-hex ``run_key`` used once, a zoned ``as_of``, and the price pin of each exchange. Anything else is a
    ``ManifestError`` (nothing read)."""
    if len(text.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"the grid manifest is larger than {MAX_MANIFEST_BYTES} bytes")
    try:
        manifest = json.loads(text)
    except ValueError as error:
        raise ManifestError("the grid manifest is not a JSON document") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"the grid manifest is not a {MANIFEST_SCHEMA}")
    if manifest.get("manifest_sha256") != manifest_sha256(manifest):
        raise ManifestError("the grid manifest's manifest_sha256 does not recompute")
    grid = manifest.get("grid")
    pins = manifest.get("price_pin")
    if not isinstance(grid, list) or not isinstance(pins, dict):
        raise ManifestError("the grid manifest lacks its grid or its price pin")
    for market in MARKETS:
        pin = pins.get(market)
        if not isinstance(pin, dict) or not pin.get("publication_id") or panel._parse_instant(pin.get("available_at")) is None:
            raise ManifestError(f"the grid manifest has no usable price pin for {market}")
    served_grid = manifest.get("served_grid")
    if served_grid is not None and not isinstance(served_grid, list):
        raise ManifestError("the grid manifest's served_grid is not a list")
    for entries in (grid, served_grid or []):  # rev 2: the served runs' entries hold the same shape, each (T, exchange) and run_key once
        _check_entries(entries)
    return manifest


def _check_entries(grid: list[Any]) -> None:
    """Every entry of a grid list (``grid`` or ``served_grid``): the fields the report reads, a zoned ``as_of``, a known
    exchange, a 64-hex ``run_key``, each ``(T, exchange)`` and ``run_key`` once."""
    seen: set[tuple[str, str]] = set()
    run_keys: set[str] = set()
    for entry in grid:
        if not isinstance(entry, dict) or any(key not in entry for key in MANIFEST_ENTRY_KEYS):
            raise ManifestError(f"a grid entry lacks one of {list(MANIFEST_ENTRY_KEYS)}")
        try:
            parsed = datetime.fromisoformat(str(entry["as_of"]).replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ManifestError("a grid entry's as_of is not a zoned instant")
        instant = parsed.astimezone(timezone.utc)
        if entry["market"] not in MARKETS or not isinstance(entry["run_key"], str) or not _SHA256.match(entry["run_key"]):
            raise ManifestError("a grid entry names an unknown exchange or a run_key that is not a sha256")
        key = (instant.isoformat(), str(entry["market"]))
        if key in seen or entry["run_key"] in run_keys:
            raise ManifestError("a (T, exchange) or a run_key appears twice in the grid manifest")
        seen.add(key)
        run_keys.add(entry["run_key"])


# ------------------------------------------------------------------ the point-in-time screen (pure)
def volume_split_votes(bars: Mapping[str, Mapping[str, Any]]) -> Counter[str]:
    """The votes of ONE series (``{session: bar}`` of the pinned vintage) on the provider's volume: whether its ``volume``
    is in traded shares or split-adjusted, read on its capital events (no symbol is named: prereg §2). An event is a
    session where the ratio ``close / adjusted_close`` moves by at least ``VOLUME_CHECK_MIN_FACTOR`` from the previous valid
    session (a split of factor ``f`` = the ratio before ÷ the ratio after); with ``VOLUME_CHECK_WINDOW`` valid volumes
    before it and from it (no other event inside), the log change ``v`` of the median volume is compared with ``ln f``:
    traded shares move by the split factor (``v`` closer to ``ln f`` than to 0: ``as_traded``), split-adjusted volumes do
    not (``split_adjusted``)."""
    window = VOLUME_CHECK_WINDOW
    votes: Counter[str] = Counter()
    valid = [(close / adjusted, panel._positive(bars[session].get("volume"))) for session in sorted(bars)
             if (close := panel._positive(bars[session].get("close"))) is not None and (adjusted := panel._positive(bars[session].get("adjusted_close"))) is not None]
    events = [index for index in range(1, len(valid)) if max(valid[index - 1][0] / valid[index][0], valid[index][0] / valid[index - 1][0]) >= VOLUME_CHECK_MIN_FACTOR]
    for position, index in enumerate(events):
        if (position and index - events[position - 1] <= window) or (position + 1 < len(events) and events[position + 1] - index <= window):
            continue  # another event inside a window: not a clean reading
        before = [volume for _ratio, volume in valid[max(0, index - window):index] if volume is not None]
        after = [volume for _ratio, volume in valid[index:index + window] if volume is not None]
        if index < window or len(before) < window or len(after) < window:
            continue
        change, split = math.log(statistics.median(after) / statistics.median(before)), math.log(valid[index - 1][0] / valid[index][0])
        votes["as_traded" if abs(change - split) < abs(change) else "split_adjusted"] += 1
    return votes


def volume_split_decision(votes: Mapping[str, int]) -> dict[str, Any]:
    """The screen's volume basis from the votes of every series of the pinned vintages: the leading reading when at least
    ``VOLUME_CHECK_MIN_EVENTS`` clean events voted and at least ``VOLUME_CHECK_MIN_AGREEMENT`` of them agree, else
    ``undetermined`` (the grid does not run). Both branches are pre-registered: ``as_traded`` → close × volume,
    ``split_adjusted`` → close × volume ÷ the split-only factor of the later capital events (``VOLUME_BASES``)."""
    events = int(sum(votes.values()))
    as_traded, split_adjusted = int(votes.get("as_traded", 0)), int(votes.get("split_adjusted", 0))
    decision = "undetermined"
    if events >= VOLUME_CHECK_MIN_EVENTS:
        leader, count = ("as_traded", as_traded) if as_traded >= split_adjusted else ("split_adjusted", split_adjusted)
        if count / events >= VOLUME_CHECK_MIN_AGREEMENT:
            decision = leader
    return {"events": events, "as_traded_like": as_traded, "split_adjusted_like": split_adjusted, "decision": decision, "field": VOLUME_BASES.get(decision)}


def volume_split_check(series: Iterable[Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """``volume_split_decision`` of the votes of every series."""
    votes: Counter[str] = Counter()
    for bars in series:
        votes.update(volume_split_votes(bars))
    return volume_split_decision(votes)


def screen(inputs: Mapping[str, Mapping[str, Any]], *, basis: str = "as_traded") -> tuple[set[str], Counter[str]]:
    """The decisory names of ONE exchange at ONE ``T`` from the run's screen inputs (``valuation_pit_rerun`` outputs.screen,
    every evaluated name): a stock, close ≥ ``SCREEN_MIN_CLOSE``, market cap at ``T`` ≥ ``SCREEN_MIN_MARKET_CAP``, median
    dollar volume of the last 20 sessions ≥ ``SCREEN_MIN_DOLLAR_VOLUME`` (on the grid's volume basis: ``VOLUME_BASES``),
    then the ``SCREEN_TOP_PER_EXCHANGE`` most liquid (ties by symbol). Returns the names kept and the names removed by
    their FIRST failed rule."""
    field = VOLUME_BASES[basis]
    removed: Counter[str] = Counter()
    eligible: list[tuple[float, str]] = []
    for symbol in sorted(inputs):
        item = inputs[symbol]
        close, cap, volume = panel._positive(item.get("close")), panel._positive(item.get("market_cap")), panel._positive(item.get(field))
        if item.get("security_type") != SCREEN_SECURITY_TYPE:
            removed["not_a_stock"] += 1
        elif close is None or close < SCREEN_MIN_CLOSE:
            removed["close_below_min"] += 1
        elif cap is None or cap < SCREEN_MIN_MARKET_CAP:
            removed["market_cap_below_min"] += 1
        elif volume is None or volume < SCREEN_MIN_DOLLAR_VOLUME:
            removed["dollar_volume_below_min"] += 1
        else:
            eligible.append((volume, symbol))
    ranked = sorted(eligible, key=lambda item: (-item[0], item[1]))
    if len(ranked) > SCREEN_TOP_PER_EXCHANGE:
        removed["beyond_top_per_exchange"] += len(ranked) - SCREEN_TOP_PER_EXCHANGE
    return {symbol for _volume, symbol in ranked[:SCREEN_TOP_PER_EXCHANGE]}, removed


# ------------------------------------------------------------------ the decisory blocks, their halves, the persistence test and the verdict (pure)
def complete_block_means(points: Iterable[tuple[int, float]], *, block_length: int, mature_through: int | None,
                         partition_last: int | None) -> list[tuple[int, float]]:
    """``(block, mean)`` of the COMPLETE blocks that hold a value — exactly ``valuation_accuracy_report.block_statistics``'s
    rule (checked against it on every report)."""
    last_complete = -1
    if mature_through is not None and mature_through >= 0:
        if partition_last is not None and partition_last <= mature_through:
            last_complete = partition_last // block_length
        else:
            last_complete = (mature_through + 1) // block_length - 1
    by_block: dict[int, list[float]] = {}
    for index, value in sorted(points):
        by_block.setdefault(index // block_length, []).append(float(value))
    return [(block, math.fsum(values) / len(values)) for block, values in sorted(by_block.items()) if block <= last_complete]


def halves(means: Sequence[tuple[int, float]]) -> dict[str, Any]:
    """The decisory test on each half of the complete blocks: the first ``⌊B/2⌋`` and the last ``⌊B/2⌋`` (the middle
    block left out when ``B`` is odd), each by ``batch_means_test`` (estimate = the mean of its block means)."""
    count = len(means) // 2

    def half(part: Sequence[tuple[int, float]]) -> dict[str, Any]:
        return {"blocks": len(part), "first_block": part[0][0] if part else None, "last_block": part[-1][0] if part else None,
                **accuracy.batch_means_test([value for _block, value in part])}

    return {"blocks": len(means), "per_half": count, "first": half(means[:count]), "second": half(means[len(means) - count:] if count else [])}


def persistence_test(means: Sequence[float]) -> dict[str, Any]:
    """The persistence co-condition (prereg §6.5): the batch-means test of the 63-session block means with
    ``PERSISTENCE_VARIANCE_FACTOR`` — ``se = √factor · sd / √B63``, Student t with ``B63 − 1`` df. Below two blocks there is
    no se; with ``se = 0`` there is no test."""
    blocks = len(means)
    result: dict[str, Any] = {"block_sessions": PERSISTENCE_BLOCK_SESSIONS, "variance_factor": PERSISTENCE_VARIANCE_FACTOR, "blocks": blocks,
                              "estimate": panel._finite(math.fsum(means) / blocks) if blocks else None, "se": None, "t": None, "df": max(0, blocks - 1),
                              "p_greater": None, "p_less": None}
    if blocks >= 2:
        center = math.fsum(means) / blocks
        sd = math.sqrt(math.fsum((mean - center) ** 2 for mean in means) / (blocks - 1))
        se = math.sqrt(PERSISTENCE_VARIANCE_FACTOR) * sd / math.sqrt(blocks)
        if se > 0.0:
            t = center / se
            result.update({"se": panel._finite(se), "t": panel._finite(t), "p_greater": accuracy.student_t_sf(t, blocks - 1),
                           "p_less": accuracy.student_t_sf(-t, blocks - 1)})
        else:
            result["se"] = 0.0
    return result


def verdict(primary: Mapping[str, Any] | None, split: Mapping[str, Any] | None, *, persistence: Mapping[str, Any] | None = None,
            coverage: Mapping[str, Any] | None = None, void: Sequence[str] = ()) -> dict[str, Any]:
    """The pre-registered single look (prereg §7), in order, on the screened EXECUTABLE IC at the primary horizon:
    ``VOID`` (the reading is not valid under the prereg — no statistic is computed or published) → ``UNMEASURED`` (no
    eligible executable observation, the executable attrition above the cap, or the coverage floor not met) → ``NEGATIVE``
    (``p_less ≤ ALPHA_NEGATIVE``) → ``PASS`` (all of: ``B ≥ MIN_BLOCKS``, estimate ≥ ``IC_MIN``, ``p_greater ≤ ALPHA``,
    executable decile spread > 0, the estimate > 0 in both halves, the 63-session persistence test's ``p_greater ≤ ALPHA``)
    → ``FAIL`` (not demonstrated), with the failed conditions listed. Never a gate."""
    coverage = coverage or {}
    result: dict[str, Any] = {"status": "FAIL", "statistic": DECISORY_STATISTIC, "horizon_sessions": PRIMARY_HORIZON, "look": "SINGLE", "reasons": [],
                              "blocks": None, "blocks_pending": None, "ic_estimate": None, "ic_se": None, "ic_t": None, "ic_df": None, "ic_p_greater": None,
                              "ic_p_less": None, "decile_spread_executable_estimate": None, "halves": {"first": None, "second": None},
                              "persistence_blocks": None, "persistence_estimate": None, "persistence_p_greater": None, "attrition_executable": None,
                              "coverage_records_share": coverage.get("records_share"), "coverage_screened_names_median": coverage.get("screened_names_median"),
                              "gate": False}
    if void or primary is None or split is None:
        result.update({"status": "VOID", "reasons": list(void) or ["no_reading"]})
        return result
    blocks = primary[DECISORY_STATISTIC]["blocks"]
    spread = primary["decile_spread_executable"]["blocks"]["estimate"]
    attrition = primary["attrition_executable"]
    first, second = split["first"]["estimate"], split["second"]["estimate"]
    persistence = persistence or {}
    result.update({"blocks": blocks["blocks"], "blocks_pending": blocks["blocks_pending"], "ic_estimate": blocks["estimate"], "ic_se": blocks["se"],
                   "ic_t": blocks["t"], "ic_df": blocks["df"], "ic_p_greater": blocks["p_greater"], "ic_p_less": blocks["p_less"],
                   "decile_spread_executable_estimate": spread, "halves": {"first": first, "second": second}, "persistence_blocks": persistence.get("blocks"),
                   "persistence_estimate": persistence.get("estimate"), "persistence_p_greater": persistence.get("p_greater"),
                   "attrition_executable": attrition["rate"]})
    if not attrition["eligible"]:
        result.update({"status": "UNMEASURED", "reasons": ["no_eligible_observations"]})
        return result
    if attrition["rate"] > ATTRITION_CAP:
        result.update({"status": "UNMEASURED", "reasons": [f"attrition_above_cap:{attrition['rate']:.4f}>{ATTRITION_CAP}"]})
        return result
    floor: list[str] = []
    share, names = coverage.get("records_share"), coverage.get("screened_names_median")
    if share is None or share < COVERAGE_MIN_RECORDS_SHARE:
        floor.append(f"coverage_records_share_below_floor:{share}<{COVERAGE_MIN_RECORDS_SHARE}")
    if names is None or names < COVERAGE_MIN_SCREENED_NAMES:
        floor.append(f"coverage_screened_names_below_floor:{names}<{COVERAGE_MIN_SCREENED_NAMES}")
    if floor:
        result.update({"status": "UNMEASURED", "reasons": floor})
        return result
    if blocks["p_less"] is not None and blocks["p_less"] <= ALPHA_NEGATIVE:
        result.update({"status": "NEGATIVE", "reasons": [f"ic_executable_negative:p_less={blocks['p_less']:.6f}<={ALPHA_NEGATIVE}"]})
        return result
    failures: list[str] = []
    if blocks["blocks"] < MIN_BLOCKS:
        failures.append(f"blocks_below_min:{blocks['blocks']}<{MIN_BLOCKS}")
    if blocks["estimate"] is None or blocks["estimate"] < IC_MIN:
        failures.append(f"ic_executable_below_min:{blocks['estimate']}<{IC_MIN}")
    if blocks["p_greater"] is None or blocks["p_greater"] > ALPHA:
        failures.append(f"ic_executable_not_significant:p_greater={blocks['p_greater']}>{ALPHA}")
    if spread is None or spread <= 0.0:
        failures.append("decile_spread_executable_unmeasured" if spread is None else "decile_spread_executable_not_positive")
    for name, value in (("first", first), ("second", second)):
        if value is None or value <= 0.0:
            failures.append(f"ic_executable_{name}_half_not_positive:{value}")
    persistent = persistence.get("p_greater")
    if persistent is None or persistent > ALPHA:
        failures.append(f"ic_executable_not_persistent:p_greater_63={persistent}>{ALPHA}")
    result.update({"status": "PASS" if not failures else "FAIL", "reasons": failures})
    return result


# ------------------------------------------------------------------ the design: operating characteristics of the single look (prereg §8)
def design_table(*, reps: int = DESIGN_REPS, seed: int = DESIGN_SEED, sds: Sequence[float] = DESIGN_SDS, ics: Sequence[float] = DESIGN_ICS,
                 instants: Sequence[int] = DESIGN_INSTANTS) -> dict[str, Any]:
    """P(PASS) and P(NEGATIVE) of the pre-registered look under the overlap model of PREREG_VALUATION_DECISOR_V1 §5: the
    daily executable IC is ``ic + sd · N_t``, ``N_t`` the normalised moving sum of ``h`` independent standard normals
    (autocorrelation ``1 − k/h``), SAMPLED every ``STEP_SESSIONS`` sessions from the anchor on a grid of ``instants``
    instants (``266`` = the pre-registered grid: 64 blocks of 21 calendar sessions, the last holding ONE instant, 22
    blocks of 63); blocks of ``h`` calendar sessions and, for the persistence co-condition, of
    ``PERSISTENCE_BLOCK_SESSIONS``; the verdict's own rule on the ``B`` blocks (estimate ≥ ``IC_MIN``, ``t ≥`` the
    critical value of ``ALPHA``, both halves > 0, the 63-session ``t ≥`` its critical value; NEGATIVE when ``t ≤ −`` the
    critical value of ``ALPHA_NEGATIVE``). Neither attrition, the coverage floor nor the decile-spread condition is
    modelled (PASS probabilities are upper bounds). Common random numbers across cells; deterministic for a seed."""
    if reps <= 0 or not instants or min(sds) <= 0.0:
        raise ValueError("reps, instants and sds must be positive")
    h, step, long = PRIMARY_HORIZON, STEP_SESSIONS, PERSISTENCE_BLOCK_SESSIONS
    grids = {n: [k * step for k in range(n)] for n in instants}
    blocks = {n: len({t // h for t in grids[n]}) for n in instants}
    long_blocks = {n: len({t // long for t in grids[n]}) for n in instants}
    if min(blocks.values()) < 2:
        raise ValueError("every design grid needs at least two blocks")
    critical = {n: accuracy.student_t_isf(ALPHA, blocks[n] - 1) for n in instants}
    critical_negative = {n: accuracy.student_t_isf(ALPHA_NEGATIVE, blocks[n] - 1) for n in instants}
    critical_long = {n: accuracy.student_t_isf(ALPHA, long_blocks[n] - 1) if long_blocks[n] >= 2 else math.inf for n in instants}
    factor, factor_long, root = math.sqrt(accuracy.ADJACENT_BLOCK_VARIANCE_FACTOR), math.sqrt(PERSISTENCE_VARIANCE_FACTOR), math.sqrt(h)
    sessions = max(grids[n][-1] for n in instants) + 1
    passed: Counter[tuple[int, float, float]] = Counter()
    negative: Counter[tuple[int, float, float]] = Counter()
    rng = random.Random(seed)
    for _ in range(reps):
        walk, total = [0.0], 0.0
        for _step in range(sessions + h - 1):
            total += rng.gauss(0.0, 1.0)
            walk.append(total)
        for n in instants:
            by_block: dict[int, list[float]] = {}
            by_long: dict[int, list[float]] = {}
            for t in grids[n]:
                value = (walk[t + h] - walk[t]) / root
                by_block.setdefault(t // h, []).append(value)
                by_long.setdefault(t // long, []).append(value)
            window = [math.fsum(items) / len(items) for _block, items in sorted(by_block.items())]
            long_means = [math.fsum(items) / len(items) for _block, items in sorted(by_long.items())]
            b = len(window)
            count = b // 2
            center = math.fsum(window) / b
            spread = math.sqrt(math.fsum((m - center) ** 2 for m in window) / (b - 1))
            first, second = math.fsum(window[:count]) / count, math.fsum(window[b - count:]) / count
            long_center = math.fsum(long_means) / len(long_means)
            long_spread = math.sqrt(math.fsum((m - long_center) ** 2 for m in long_means) / (len(long_means) - 1)) if len(long_means) >= 2 else 0.0
            for sd in sds:
                se = factor * sd * spread / math.sqrt(b)
                se_long = factor_long * sd * long_spread / math.sqrt(len(long_means))
                if se <= 0.0:
                    continue
                for ic in ics:
                    estimate = ic + sd * center
                    t_value = estimate / se
                    if t_value <= -critical_negative[n]:
                        negative[(n, sd, ic)] += 1
                    elif (estimate >= IC_MIN and t_value >= critical[n] and ic + sd * first > 0.0 and ic + sd * second > 0.0
                          and se_long > 0.0 and (ic + sd * long_center) / se_long >= critical_long[n]):
                        passed[(n, sd, ic)] += 1
    cells = [{"instants": n, "blocks": blocks[n], "persistence_blocks": long_blocks[n], "sd": sd, "ic": ic, "pass": passed[(n, sd, ic)] / reps,
              "negative": negative[(n, sd, ic)] / reps} for n in instants for sd in sds for ic in ics]
    return {"model": "daily IC = ic + sd * normalised moving sum of h normals, sampled every step sessions", "reps": reps, "seed": seed, "horizon": h,
            "step_sessions": step, "persistence_block_sessions": long, "alpha": ALPHA, "alpha_negative": ALPHA_NEGATIVE, "ic_min": IC_MIN,
            "blocks": {blocks[n]: n for n in instants}, "persistence_blocks": {blocks[n]: long_blocks[n] for n in instants}, "cells": cells}


# ------------------------------------------------------------------ the code binding (prereg §15): the accuracy report's machinery, this module's pins
def code_fingerprint(*, build_sha: str | None = None) -> dict[str, Any]:
    """The sha256 of every ``PINNED_FILES`` module (its bytes) and ``PINNED_OBJECTS`` object (source text / constant
    ``repr``), plus — recorded, never pinned — the calendar library's and Python's versions and the deployed revision."""
    package = __package__ or "app"
    here = Path(__file__).resolve().parent
    objects: dict[str, str] = {}
    for qualified in PINNED_OBJECTS:
        module_name, _dot, path = qualified.partition(".")
        value: Any = importlib.import_module(f"{package}.{module_name}")
        for attribute in path.split("."):
            value = getattr(value, attribute)
        objects[f"{package}.{qualified}"] = accuracy._object_sha256(value)
    return {"files": {f"{package}/{name}": accuracy._file_sha256(here / name) for name in PINNED_FILES}, "objects": objects,
            "exchange_calendars": getattr(xcals, "__version__", "unknown"), "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "build_sha": build_sha}


def render_pins(code: Mapping[str, Any] | None = None) -> str:
    """The pin lines the prereg carries (§15), sorted."""
    return accuracy.render_pins(code if code is not None else code_fingerprint())


# ------------------------------------------------------------------ read-only plumbing
class ReadOnlyStore:
    """The store as the report sees it: the accuracy report's four readers plus ``latest_analysis_snapshot_by_inputs`` (the
    run snapshots and the superseded chain) — any other attribute is an ``AttributeError`` (no writer is reachable)."""

    READERS: tuple[str, ...] = (*accuracy.ReadOnlyStore.READERS, "latest_analysis_snapshot_by_inputs")

    def __init__(self, database: Any) -> None:
        self._database = database

    def __getattr__(self, name: str) -> Any:
        if name in ReadOnlyStore.READERS:
            return getattr(self._database, name)
        raise AttributeError(f"valuation_pit_backtest_report is read-only: {name!r} is not one of its readers {ReadOnlyStore.READERS}")


def _trim_run(snapshot: Mapping[str, Any] | None, *, served: bool = False) -> dict[str, Any] | None:
    """A run snapshot reduced to what the report and the PIT panel's superseded chain read (the engine's per-symbol rows are
    counted, never kept): identity, clocks, pins, producer, catalogue reference, summary, prediction identities, screen
    inputs, catalogue counts, the own-history model count."""
    if snapshot is None:
        return None
    inputs, outputs = panel._mapping(snapshot.get("inputs")), panel._mapping(snapshot.get("outputs"))
    manifest = panel._mapping(inputs.get("manifest"))
    rows = panel._mapping(outputs.get("rows"))
    kept_inputs = {key: inputs[key] for key in ("run_key", "market", "as_of", "source", "source_version", "supersedes", "price_pin", "catalogue_pin") if key in inputs}
    raw_sources = manifest.get("sources")
    sources: list[Any] = raw_sources if isinstance(raw_sources, list) else []
    kept_inputs["manifest"] = {"engine": manifest.get("engine"), "price_vintage": manifest.get("price_vintage"), "session_date": manifest.get("session_date"),
                               "catalogue": [ref for ref in sources if isinstance(ref, dict) and ref.get("role") == "catalogue"]}
    trimmed = {"id": str(snapshot.get("id")), "published_at": panel._utc(snapshot["published_at"]), "inputs": copy.deepcopy(kept_inputs),
               "outputs": {"summary": copy.deepcopy(panel._mapping(outputs.get("summary"))), "prediction_identities": copy.deepcopy(outputs.get("prediction_identities") or []),
                           "screen": copy.deepcopy(panel._mapping(outputs.get("screen"))), "catalogue_counts": copy.deepcopy(panel._mapping(outputs.get("catalogue_counts"))),
                           "history_model": {"evaluated": len(rows), "active": sum(1 for row in rows.values() if HISTORY_MODEL in panel._mapping(panel._mapping(row).get("models")))}}}
    if served:  # the served run's records live in its snapshot: each reduced (``_stub``), with whether its identity recomputes
        raw = outputs.get("records")
        trimmed["outputs"]["records"] = [{**_stub(record), "verified": _record_verifies(record)} for record in (raw if isinstance(raw, list) else []) if isinstance(record, dict)]
    return trimmed


def _record_verifies(record: Mapping[str, Any]) -> bool:
    """Whether a snapshot-resident record's ``row_sha256`` recomputes from its own fields (``valuation_pit_served.record_verifies``)."""
    core = {key: value for key, value in record.items() if key not in ("id", "row_sha256")}
    return bool(record.get("row_sha256")) and canonical_sha256(core) == record.get("row_sha256")


class _RunSnapshots:
    """``latest_analysis_snapshot_by_inputs`` for the run analysis types (the V3 runs and the served runs), memoised for ONE
    report (the store is append-only: every caller — this report and ``valuation_pit_panel.superseded_run_keys`` — sees one
    answer per key) and trimmed (``_trim_run``). Everything else is delegated untouched."""

    def __init__(self, database: Any) -> None:
        self._database = database
        self._memo: dict[str, dict[str, Any] | None] = {}
        self.reads = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._database, name)

    def latest_analysis_snapshot_by_inputs(self, analysis_type: str, inputs_match: dict[str, str]) -> dict[str, Any] | None:
        if analysis_type not in (RUN_ANALYSIS_TYPE, SERVED_RUN_ANALYSIS_TYPE):
            return self._database.latest_analysis_snapshot_by_inputs(analysis_type, inputs_match)
        key = json.dumps([analysis_type, sorted(inputs_match.items())])
        if key not in self._memo:
            self.reads += 1
            self._memo[key] = _trim_run(self._database.latest_analysis_snapshot_by_inputs(analysis_type, inputs_match),
                                        served=analysis_type == SERVED_RUN_ANALYSIS_TYPE)
        return copy.deepcopy(self._memo[key])


_STUB_KEYS: tuple[str, ...] = ("source", "source_version", "market", "symbol", "scope", "session_date", "cycle_id", "prediction_instant", "published_at",
                               "tp", "price", "currency", "consensus_tp", "bear_tp", "bull_tp", "row_sha256")


def _stub(record: Mapping[str, Any]) -> dict[str, Any]:
    """A record reduced to what admissibility, the PIT rules and the observation read (the run's heavy provenance is dropped
    once its ``run_key`` was read): ~150k records of a grid never sit in memory whole."""
    decomposition = panel._mapping(record.get("decomposition"))
    provenance = panel._mapping(decomposition.get("provenance"))
    return {**{key: record.get(key) for key in _STUB_KEYS},
            "decomposition": {"consensus": copy.deepcopy(decomposition.get("consensus")), "bands": copy.deepcopy(decomposition.get("bands")),
                              "status": decomposition.get("status"), "provenance": {"run_key": provenance.get("run_key"), "rerun_of": provenance.get("rerun_of")}}}


_ROW_KEYS: tuple[str, ...] = ("market", "screened", "tp", "price", "adjustment", "close_at_session", "consensus_status", "producer_status", "scope", "cohort")
_LABEL_KEYS: tuple[str, ...] = ("status", "eligible", "realized", "e_source", "e_consensus", "within_bands")


def _compact(row: Mapping[str, Any]) -> dict[str, Any]:
    """An observation reduced to what ``horizon_report`` reads (``point``, ``horizon_metrics``, ``executable_attrition``,
    the mask statistics) and the screen flag: a grid's ~150k observations never sit in memory with their bar hashes,
    clocks and identities (lossless for the receipt: pinned by test)."""
    consensus = panel._mapping(row.get("consensus"))
    return {**{key: row.get(key) for key in _ROW_KEYS}, "symbol": sys.intern(str(row["symbol"])), "session": sys.intern(str(row["session"])),
            "consensus": {"tp": consensus.get("tp"), "horizon": consensus.get("horizon")},
            "horizons": {key: {name: label.get(name) for name in _LABEL_KEYS} for key, label in row["horizons"].items()}}


def label_horizons() -> tuple[int, ...]:
    """Every label a record needs: ``h`` and the executable pair ``(1, h + 1)`` for each horizon."""
    return tuple(sorted({EXECUTION_LAG_SESSIONS, *HORIZONS, *(h + EXECUTION_LAG_SESSIONS for h in HORIZONS)}))


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {"n": len(values), "min": panel._finite(min(values)), "median": panel._finite(statistics.median(values)), "max": panel._finite(max(values))}


def _points_by_session(rows: Sequence[Mapping[str, Any]], horizon: int) -> dict[str, list[dict[str, Any]]]:
    """``accuracy.point`` of every row at ``horizon``, with the row's exchange, by session, in the accuracy report's order."""
    points = []
    for row in rows:
        item = accuracy.point(row, horizon)
        if item is not None:
            points.append({**item, "market": row.get("market")})
    by_session: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(points, key=lambda p: (p["session"], p["symbol"])):
        by_session.setdefault(item["session"], []).append(item)
    return by_session


def _session_values(by_session: Mapping[str, Sequence[Mapping[str, Any]]], statistic: str, index_of: Mapping[str, int]) -> list[tuple[int, float]]:
    """``(session index, value)`` of a statistic per session — the per-session values the accuracy report blocks."""
    return [(index_of[session], value) for session in sorted(by_session) if (value := accuracy._session_statistic(by_session[session], statistic)[0]) is not None]


class PitBacktestReportService:
    """Reads the store for a grid manifest (its run snapshots, the records of its runs, the labels of its pinned
    publications) and produces the aggregate receipt. Never writes, never fetches."""

    def __init__(self, database: Database, *, settings: Settings | None = None, price_history: PriceHistoryService | None = None) -> None:
        self.database = database
        self._caller_price_history = price_history
        self._settings = settings if settings is not None else (None if price_history is not None else get_settings())
        self.http: panel._NoNetworkHttp | None = None if price_history is not None else panel._NoNetworkHttp()  # pinned at 0 calls
        self.labels_read = 0  # label_bar calls of the last report (0 when the reading is VOID: nothing outcome-related is read)

    def _reader(self) -> PriceHistoryService:
        if self._caller_price_history is not None:
            return self._caller_price_history
        assert self.http is not None and self._settings is not None
        return accuracy._SymbolReader(self._settings, cast(Database, panel._CutReads(self.database)), self.http)

    # ---- the manifest's parameters and the pinned publications
    @staticmethod
    def _parameters(manifest: Mapping[str, Any]) -> list[str]:
        void: list[str] = []
        if manifest.get("complete") is not True:
            void.append("manifest_not_complete")
        if manifest.get("market") != MARKET_GROUP:
            void.append(f"manifest_market_not_{MARKET_GROUP}")
        if manifest.get("grid_start") != GRID_START.isoformat():
            void.append(f"manifest_grid_start_not_prereg:{manifest.get('grid_start')}")
        if list(manifest.get("markets") or []) != list(MARKETS):
            void.append("manifest_markets_not_" + "_".join(MARKETS))
        if manifest.get("statements") != STATEMENTS:
            void.append(f"manifest_statements_not_{STATEMENTS}")
        if manifest.get("step_sessions") != STEP_SESSIONS:
            void.append(f"manifest_step_not_{STEP_SESSIONS}")
        if volume_basis(manifest) is None:
            void.append("manifest_volume_basis_not_decided")
        return void

    @staticmethod
    def _label_vintages(reader: PriceHistoryService, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, datetime], list[str]]:
        """Per exchange, the pinned publication (the manifest's) read back through the cut that resolves exactly it
        (``available_at + 1 µs``), checked: publication id, bars hash, a 120-month window."""
        headers: dict[str, Any] = {}
        cuts: dict[str, datetime] = {}
        void: list[str] = []
        for market in MARKETS:
            pin = manifest["price_pin"][market]
            cut = panel._utc(pin["available_at"]) + timedelta(microseconds=1)
            vintage = reader.vintage(market, available_before=cut)
            cuts[market] = cut
            headers[market] = None if vintage is None else {key: vintage.get(key) for key in ("status", "publication_id", "price_snapshot_id", "available_at",
                                                                                                "fetched_at", "from", "to", "bars_sha256")}
            if (vintage is None or vintage["status"] != "ok" or str(vintage["publication_id"]) != str(pin["publication_id"])
                    or (pin.get("bars_sha256") is not None and vintage.get("bars_sha256") != pin.get("bars_sha256"))):
                void.append(f"label_vintage_not_the_pinned_one:{market}")
            elif str(vintage["from"])[:10] > PRICE_VINTAGE_FROM_LATEST.isoformat():
                void.append(f"price_vintage_not_120_months:{market}")
        return headers, cuts, void

    # ---- the grid and the runs
    @staticmethod
    def _grid(manifest: Mapping[str, Any], expected: Sequence[date], bounds: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        markets_by_session: dict[str, set[str]] = {}
        clock_mismatches = 0
        for entry in manifest["grid"]:
            session = str(entry["session_date"])[:10]
            markets_by_session.setdefault(session, set()).add(str(entry["market"]))
            try:
                expected_instant: str | None = t_instant(date.fromisoformat(session)).isoformat()
            except (ValueError, CalendarUnavailable):
                expected_instant = None
            if panel._utc(entry["as_of"]).isoformat() != expected_instant:
                clock_mismatches += 1
        manifest_sessions = sorted(markets_by_session)
        wanted = [day.isoformat() for day in expected]
        missing = sorted(set(wanted) - set(manifest_sessions))
        extra = sorted(set(manifest_sessions) - set(wanted))
        half_done = sum(1 for markets in markets_by_session.values() if markets != set(MARKETS))
        status = "PREREG" if not missing and not extra and not half_done and not clock_mismatches and wanted else "MISMATCH"
        void: list[str] = []
        if not wanted:
            void.append("no_prereg_grid:pinned_vintage_too_short_or_unusable")
        elif not bounds.get("starts_at_grid_start"):
            void.append(f"grid_start_not_prereg:{bounds.get('first_eligible')}")  # the pinned vintages cannot start the grid at GRID_START (not the 120-month backfill)
        if missing:
            void.append(f"grid_sessions_missing:{len(missing)}")
        if extra:
            void.append(f"grid_sessions_not_prereg:{len(extra)}")
        if half_done:
            void.append(f"grid_sessions_without_both_exchanges:{half_done}")
        if clock_mismatches:
            void.append(f"grid_t_clock_mismatch:{clock_mismatches}")
        return {"status": status, "expected_sessions": len(wanted), "manifest_sessions": len(manifest_sessions), "missing": len(missing), "extra": len(extra),
                "without_both_exchanges": half_done, "t_clock_mismatches": clock_mismatches, "first_session": wanted[0] if wanted else None,
                "last_session": wanted[-1] if wanted else None}, void

    @staticmethod
    def _runs(store: _RunSnapshots, manifest: Mapping[str, Any], *, entries_key: str = "grid", analysis_type: str = RUN_ANALYSIS_TYPE
              ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
        """Every manifest entry against the store: ``current`` (the latest run of its (exchange, T) IS it), ``superseded`` (it
        exists, a later run of the same (exchange, T) superseded it), ``missing``; a current run whose cycle, pin, statements
        mode or session disagrees with the manifest is ``mismatched``. Across the current runs of an exchange: one producer,
        one catalogue (classification hash), one as-filed coverage. Returns the aggregate, the current runs by run_key and the
        VOID reasons."""
        status: Counter[str] = Counter()
        mismatch: Counter[str] = Counter()
        current: dict[str, dict[str, Any]] = {}
        for entry in manifest.get(entries_key) or []:
            market, run_key = str(entry["market"]), str(entry["run_key"])
            as_of = panel._utc(entry["as_of"]).isoformat()
            latest = store.latest_analysis_snapshot_by_inputs(analysis_type, {"market": market, "as_of": as_of})
            if latest is None or str(latest["inputs"].get("run_key")) != run_key:
                status["superseded" if store.latest_analysis_snapshot_by_inputs(analysis_type, {"run_key": run_key}) is not None else "missing"] += 1
                continue
            reasons = []
            if latest["id"] != str(entry["cycle_id"]):
                reasons.append("cycle_id")
            if str(panel._mapping(latest["inputs"].get("price_pin")).get("resolved_publication_id")) != str(manifest["price_pin"][market]["publication_id"]):
                reasons.append("price_pin")
            if panel._mapping(latest["outputs"]["summary"].get("statements")).get("mode") != manifest.get("statements"):
                reasons.append("statements_mode")
            if str(latest["inputs"]["manifest"].get("session_date")) != str(entry["session_date"])[:10]:
                reasons.append("session_date")
            if reasons:
                status["mismatched"] += 1
                mismatch.update(reasons)
                continue
            status["current"] += 1
            current[run_key] = {**latest, "market": market}
        engines = {json.dumps(producer_of(run["inputs"]["manifest"]), sort_keys=True) for run in current.values()}
        versions = Counter(str(run["inputs"].get("source_version")) for run in current.values())
        uniform = len(engines) == 1 and len(versions) == 1
        void = [f"runs_{name}:{count}" for name, count in sorted(status.items()) if name != "current" and count]
        if not current:
            void.append("no_current_run")
        elif not uniform:
            void.append("producer_not_uniform")
        catalogues: dict[str, Any] = {}
        for market in MARKETS:
            runs = [run for run in current.values() if run["market"] == market]
            hashes = {json.dumps(sorted(str(ref.get("classification_sha256")) for ref in run["inputs"]["manifest"].get("catalogue") or []), sort_keys=True) for run in runs}
            # the as-filed coverage OF THE PINNED CATALOGUE (never ``covered``: the whole store, which the live poll keeps growing with the live
            # universe's new names — invisible to the grid, whose facts are accepted after every T); a catalogue issuer backfilled mid-grid changes it
            covered = {json.dumps(panel._mapping(panel._mapping(run["outputs"]["summary"].get("statements")).get("coverage")).get("covered_in_catalogue"))
                       for run in runs}
            if len(hashes) > 1:
                void.append(f"catalogue_not_uniform:{market}")
            if len(covered) > 1:
                void.append(f"statements_table_not_stable:{market}")
            catalogues[market] = {"classification_hashes": len(hashes), "covered_in_catalogue_values": len(covered)}
        aggregate = {"entries": len(manifest.get(entries_key) or []), "status": panel._counts(status), "mismatch_reasons": panel._counts(mismatch), "catalogues": catalogues,
                     "producer": {"uniform": uniform, "source_versions": panel._counts(versions),
                                  "engine_files": json.loads(next(iter(engines)))["files"] if uniform else None,
                                  "engine_objects": json.loads(next(iter(engines)))["objects"] if uniform else None, "engine_identities": len(engines)}}
        return aggregate, current, void

    @staticmethod
    def _coverage(current: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """Aggregates of the current runs' own summaries (no symbol): per exchange and for the union, the catalogue read (rows
        and stocks), the names evaluated, with an internal TP and recorded, the not-evaluable names by reason, the
        statements basis and the as-filed coverage counts; and the share of evaluated names whose engine ran the
        own-history model, per session."""
        def empty() -> dict[str, Any]:
            return {"runs": 0, "catalogue_names": 0, "catalogue_stocks": 0, "evaluated": 0, "with_internal_tp": 0, "records": 0, "history_model_active": 0,
                    "not_evaluable": Counter(), "statements_basis": Counter(), "statements_coverage": Counter()}

        cells: dict[str, dict[str, Any]] = {market: empty() for market in (*MARKETS, MARKET_GROUP)}
        by_session: dict[str, list[int]] = {}
        per_run_catalogue: list[float] = []
        per_run_evaluated: list[float] = []
        for run in current.values():
            summary = run["outputs"]["summary"]
            history = run["outputs"]["history_model"]
            statements = panel._mapping(summary.get("statements"))
            counts = panel._mapping(run["outputs"].get("catalogue_counts"))
            catalogue = int(counts.get("rows") or panel._mapping(summary.get("price_basis_evidence")).get("symbols_read") or 0)
            per_run_catalogue.append(float(catalogue))
            per_run_evaluated.append(float(summary.get("evaluated") or 0))
            for name in (run["market"], MARKET_GROUP):
                cell = cells[name]
                cell["runs"] += 1
                cell["catalogue_names"] += catalogue
                cell["catalogue_stocks"] += int(counts.get("stocks") or 0)
                cell["evaluated"] += int(summary.get("evaluated") or 0)
                cell["with_internal_tp"] += int(summary.get("with_internal_tp") or 0)
                cell["records"] += len(run["outputs"]["prediction_identities"])
                cell["history_model_active"] += int(history["active"])
                cell["not_evaluable"].update({str(key): int(value) for key, value in panel._mapping(summary.get("not_evaluable")).items()})
                cell["statements_basis"].update({str(key): int(value) for key, value in panel._mapping(statements.get("basis")).items()})
                cell["statements_coverage"].update({str(key): int(value) for key, value in panel._mapping(statements.get("coverage")).items()})
            pair = by_session.setdefault(str(run["inputs"]["manifest"].get("session_date")), [0, 0])
            pair[0] += int(history["active"])
            pair[1] += int(history["evaluated"])
        result: dict[str, Any] = {}
        for name, cell in cells.items():
            result[name] = {**{key: value for key, value in cell.items() if not isinstance(value, Counter)},
                            **{key: panel._counts(value) for key, value in cell.items() if isinstance(value, Counter)},
                            "history_model_share": panel._finite(cell["history_model_active"] / cell["evaluated"]) if cell["evaluated"] else None,
                            "records_share": panel._finite(cell["records"] / cell["catalogue_stocks"]) if cell["catalogue_stocks"] else None}
        result[MARKET_GROUP]["history_model_share_per_session"] = _distribution([active / evaluated for active, evaluated in by_session.values() if evaluated])
        result[MARKET_GROUP]["per_run"] = {"catalogue_names": _distribution(per_run_catalogue), "evaluated": _distribution(per_run_evaluated)}
        return result

    # ---- phase A: the records of the manifest's runs, WITHOUT labels
    @staticmethod
    def _records(store: _RunSnapshots, manifest: Mapping[str, Any], current: Mapping[str, Mapping[str, Any]], records_cut: datetime | None
                 ) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
        """Per exchange and per T of the manifest: the ``v3_2_shadow`` records of that instant, those of the manifest's runs
        only (``run_not_in_manifest``), reduced (``_stub``); then the PIT rules (superseded runs refused, unattested horizon
        read as missing), the panel's admissibility, the universe scope and one record per (symbol, session) across the
        exchanges. No label is read here. Returns the admissible records (with symbols: never printed), the record counts
        and the number of current runs whose records are not exactly their identities."""
        run_keys = {str(entry["run_key"]) for entry in manifest["grid"]}
        instants_by_market: dict[str, set[str]] = {market: set() for market in MARKETS}
        for entry in manifest["grid"]:
            instants_by_market[str(entry["market"])].add(panel._utc(entry["as_of"]).isoformat())
        read = 0
        refused: Counter[str] = Counter()
        identities: dict[str, set[tuple[str, str]]] = {}
        kept_records: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for market in MARKETS:
            stubs: list[dict[str, Any]] = []
            for as_of in sorted(instants_by_market[market]):
                instant = panel._utc(as_of)
                for record in store.list_valuation_predictions_in_window(market, source=SOURCE, since=instant, until=instant + timedelta(microseconds=1)):
                    read += 1
                    run_key = str(panel._mapping(panel._mapping(record.get("decomposition")).get("provenance")).get("run_key") or "")
                    if run_key not in run_keys:
                        refused["run_not_in_manifest"] += 1
                        continue
                    identities.setdefault(run_key, set()).add((str(record.get("symbol")), str(record.get("row_sha256"))))
                    stubs.append(_stub(record))
            kept, superseded = pit_panel.refuse_superseded_runs(stubs, database=cast(Database, store), market=market)
            if superseded:
                refused[pit_panel.SUPERSEDED_RUN] += superseded
            unattested = [pit_panel._as_missing_horizon(stub) if pit_panel._unattested_horizon(stub) is not None else stub for stub in kept]
            if records_cut is None:
                refused["no_current_run"] += len(unattested)
                continue
            admissible, refusals = panel.admissible_records(unattested, cut=records_cut)
            refused.update(refusals)
            for record in admissible:
                key = (str(record["symbol"]), str(record["session_date"])[:10])
                if str(record.get("scope") or "") != accuracy.SCOPE:
                    refused["scope_not_universe"] += 1
                elif key in seen:
                    refused["duplicate_across_exchanges"] += 1
                else:
                    seen.add(key)
                    kept_records.append(record)
        incomplete = sum(1 for run_key, run in current.items()
                         if identities.get(run_key, set()) != {(str(symbol), str(digest)) for symbol, digest in run["outputs"]["prediction_identities"]})
        return kept_records, {"read": read, "refused": panel._counts(refused), "admissible": len(kept_records)}, incomplete

    @staticmethod
    def _served_records(current: Mapping[str, Mapping[str, Any]], records_cut: datetime | None) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
        """The served internal TP's records: those INSIDE the current served runs of the manifest (no other record exists —
        they are never in ``valuation_predictions``), each refused unless its identity recomputes (``identity_not_verified``)
        and it is of its run (source, ``run_key``, cycle, exchange, ``T``: ``record_not_of_its_run``); then the PIT
        unattested-horizon rule, the panel's admissibility, the universe scope and one record per (symbol, session) across
        the exchanges — exactly the V3 records' path. No label is read here."""
        read = 0
        refused: Counter[str] = Counter()
        identities: dict[str, set[tuple[str, str]]] = {}
        by_market: dict[str, list[dict[str, Any]]] = {market: [] for market in MARKETS}
        for run_key, run in current.items():
            as_of = panel._utc(run["inputs"]["as_of"]).isoformat() if run["inputs"].get("as_of") else None
            for stub in run["outputs"].get("records") or []:
                read += 1
                if not stub.get("verified"):
                    refused["identity_not_verified"] += 1
                    continue
                provenance = panel._mapping(panel._mapping(stub.get("decomposition")).get("provenance"))
                instant = panel._parse_instant(stub.get("prediction_instant"))
                if (stub.get("source") != SERVED_SOURCE or str(provenance.get("run_key") or "") != run_key or str(stub.get("cycle_id")) != run["id"]
                        or stub.get("market") != run["market"] or instant is None or instant.isoformat() != as_of):
                    refused["record_not_of_its_run"] += 1
                    continue
                identities.setdefault(run_key, set()).add((str(stub.get("symbol")), str(stub.get("row_sha256"))))
                by_market[str(run["market"])].append({key: value for key, value in stub.items() if key != "verified"})
        kept_records: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for market in MARKETS:
            unattested = [pit_panel._as_missing_horizon(stub) if pit_panel._unattested_horizon(stub) is not None else stub for stub in by_market[market]]
            if records_cut is None:
                refused["no_current_run"] += len(unattested)
                continue
            admissible, refusals = panel.admissible_records(unattested, cut=records_cut)
            refused.update(refusals)
            for record in admissible:
                key = (str(record["symbol"]), str(record["session_date"])[:10])
                if str(record.get("scope") or "") != accuracy.SCOPE:
                    refused["scope_not_universe"] += 1
                elif key in seen:
                    refused["duplicate_across_exchanges"] += 1
                else:
                    seen.add(key)
                    kept_records.append(record)
        incomplete = sum(1 for run_key, run in current.items()
                         if identities.get(run_key, set()) != {(str(symbol), str(digest)) for symbol, digest in run["outputs"]["prediction_identities"]})
        return kept_records, {"read": read, "refused": panel._counts(refused), "admissible": len(kept_records)}, incomplete

    @staticmethod
    def _screen(records: Sequence[Mapping[str, Any]], current: Mapping[str, Mapping[str, Any]], *, basis: str) -> tuple[set[tuple[str, str, str]], dict[str, Any]]:
        """The point-in-time screen of every current run (``screen``), the records it keeps (``(market, session, symbol)``)
        and its aggregate: names removed by rule over the grid, and per session the records, the screened ones and the
        share removed. No label is read here."""
        kept: set[tuple[str, str, str]] = set()
        removed: Counter[str] = Counter()
        for run in current.values():
            session = str(run["inputs"]["manifest"].get("session_date"))
            names, reasons = screen(run["outputs"]["screen"], basis=basis)
            removed.update(reasons)
            kept.update((str(run["market"]), session, symbol) for symbol in names)
        per_session: dict[str, list[int]] = {}
        for record in records:
            session = str(record["session_date"])[:10]
            pair = per_session.setdefault(session, [0, 0])
            pair[0] += 1
            pair[1] += (str(record["market"]), session, str(record["symbol"])) in kept
        rows = [{"session": session, "records": total, "screened": screened, "removed_share": panel._finite(1.0 - screened / total) if total else None}
                for session, (total, screened) in sorted(per_session.items())]
        return kept, {"volume_basis": basis, "removed_by_rule": panel._counts(removed), "per_session": rows,
                      "removed_share": _distribution([row["removed_share"] for row in rows if row["removed_share"] is not None]),
                      "records": len(records), "screened": sum(row["screened"] for row in rows)}

    # ---- phase B: the labels (only for a valid reading)
    def _label(self, reader: PriceHistoryService, records: Sequence[Mapping[str, Any]], kept: set[tuple[str, str, str]], cuts: Mapping[str, datetime]
               ) -> tuple[list[dict[str, Any]], Counter[str]]:
        """One observation per record with the labels of its exchange's pinned publication (``_label_many`` of one source)."""
        return self._label_many(reader, {SOURCE: (records, kept)}, cuts)[SOURCE]

    def _label_many(self, reader: PriceHistoryService, sources: Mapping[str, tuple[Sequence[Mapping[str, Any]], set[tuple[str, str, str]]]],
                    cuts: Mapping[str, datetime]) -> dict[str, tuple[list[dict[str, Any]], Counter[str]]]:
        """Per source, one observation per record with the labels of its exchange's pinned publication — symbol after symbol,
        one series read per symbol, the labels of a (symbol, session) read ONCE whatever the number of sources holding a
        record of it — compacted, with its exchange and its screen flag (the source's own screen)."""
        result: dict[str, tuple[list[dict[str, Any]], Counter[str]]] = {name: ([], Counter()) for name in sources}
        horizons = label_horizons()
        for market in MARKETS:
            calendar_close = panel.calendar_horizon(market)
            cut = cuts[market]
            by_pair: dict[tuple[str, str], list[tuple[str, Mapping[str, Any]]]] = {}
            for name, (records, _kept) in sources.items():
                for record in records:
                    if record["market"] == market:
                        by_pair.setdefault((str(record["symbol"]), str(record["session_date"])[:10]), []).append((name, record))
            current_symbol: str | None = None
            bars: dict[str, dict[str, Any]] = {}
            for (symbol, day), held in sorted(by_pair.items()):
                session = date.fromisoformat(day)
                if symbol != current_symbol:
                    bars, current_symbol = reader.bars(market, symbol, available_before=cut), symbol
                labels = {horizon: panel.resolve_label(reader.label_bar(market, symbol, session, horizon, available_before=cut), cut=cut, calendar_close=calendar_close)
                          for horizon in horizons}
                self.labels_read += len(horizons)
                for name, record in held:
                    row = panel.observation(record, bars.get(session.isoformat()), labels, deadline=panel.live_deadline(market, panel._utc(record["prediction_instant"])))
                    row.update({"scope": str(record.get("scope") or ""), "producer_status": panel._mapping(record.get("decomposition")).get("status"),
                                "market": market, "screened": (market, session.isoformat(), symbol) in sources[name][1]})
                    rows, cohort = result[name]
                    cohort[str(row["cohort"])] += 1
                    rows.append(_compact(row))
        return result

    # ---- the receipt
    def report(self, manifest: Mapping[str, Any], *, prereg_sha256: str | None = None, code_pins: Mapping[str, str] | None = None,
               build_sha: str | None = None) -> dict[str, Any]:
        """The receipt for ``manifest`` (validated by ``load_manifest``): ``{schema, payload, payload_sha256}`` — no symbol
        anywhere, no wall clock in the payload. Labels are read and statistics computed ONLY when the reading is valid
        (else ``VOID`` with nulls)."""
        if prereg_sha256 is not None and not _SHA256.match(prereg_sha256):
            raise ValueError("prereg_sha256 must be a lowercase hex sha256")
        load_manifest(json.dumps(manifest))  # the same checks whatever the caller passed
        self.labels_read = 0
        code = code_fingerprint(build_sha=build_sha)
        binding = accuracy.bind_code(code, code_pins, prereg_sha256=prereg_sha256)
        void: list[str] = [] if binding["status"] == "BOUND" else [f"code_{binding['status'].lower()}", *binding["reasons"]]
        void += self._parameters(manifest)
        store = _RunSnapshots(self.database)
        reader = self._reader()
        vintages, cuts, vintage_void = self._label_vintages(reader, manifest)
        void += vintage_void
        bounds = eligible_bounds(vintages)
        expected = prereg_grid(bounds)
        grid, grid_void = self._grid(manifest, expected, bounds)
        void += grid_void
        shared = list(void)  # code, manifest parameters, label vintages, grid: a shared failure voids BOTH verdicts
        runs, current, runs_void = self._runs(store, manifest)
        void += runs_void
        published = [panel._utc(run["published_at"]) for run in current.values()]
        records_cut = max(published) + timedelta(microseconds=1) if published else None
        records, counts, incomplete = self._records(store, manifest, current, records_cut)
        runs["incomplete"] = incomplete
        if incomplete:
            void.append(f"runs_incomplete:{incomplete}")
        # the served internal TP (rev 2): its own runs (served_grid), records (inside its snapshots), grid and integrity — its own VOID reasons
        served_void: list[str] = []
        if "served_grid" not in manifest or SERVED_SOURCE not in list(manifest.get("sources") or []):
            served_void.append("served:source_not_in_manifest")
        served_grid, served_grid_void = self._grid({"grid": manifest.get("served_grid") or []}, expected, bounds)
        served_void += [f"served:{reason}" for reason in served_grid_void if reason not in grid_void]
        served_runs, served_current, served_runs_void = self._runs(store, manifest, entries_key="served_grid", analysis_type=SERVED_RUN_ANALYSIS_TYPE)
        served_void += [f"served:{reason}" for reason in served_runs_void]
        served_published = [panel._utc(run["published_at"]) for run in served_current.values()]
        served_cut = max(served_published) + timedelta(microseconds=1) if served_published else None
        served_records, served_counts, served_incomplete = self._served_records(served_current, served_cut)
        served_runs["incomplete"] = served_incomplete
        if served_incomplete:
            served_void.append(f"served:runs_incomplete:{served_incomplete}")
        # the calendar index from the grid's first session (expected grid; the manifest's own first session without one) — no label read
        manifest_sessions = sorted({str(entry["session_date"])[:10] for entry in manifest["grid"]})
        anchor = expected[0] if expected else (date.fromisoformat(manifest_sessions[0]) if manifest_sessions else None)
        label_cut = min(cuts.values())
        index_of: dict[str, int] = {}
        mature_through: dict[int, int | None] = {}
        partition_last: int | None = None
        if anchor is not None:
            last_closed = panel.last_closed_session(CALENDAR_MARKET, label_cut)
            end = max([date.fromisoformat(day) for day in (last_closed, *manifest_sessions) if day] + [anchor])
            calendar = accuracy._calendar_dates(CALENDAR_MARKET, anchor, end)
            index_of = {session: index for index, session in enumerate(calendar)}
            if expected:
                partition_last = index_of.get(expected[-1].isoformat())
            for horizon in label_horizons():
                through = accuracy._mature_through(CALENDAR_MARKET, label_cut, horizon)
                mature_through[horizon] = None if through is None or through < anchor else sum(1 for session in calendar if session <= through.isoformat()) - 1

        def inside(found: list[dict[str, Any]], tally: dict[str, Any]) -> list[dict[str, Any]]:
            outside = [record for record in found if str(record["session_date"])[:10] not in index_of]
            if outside:
                tally["refused"] = panel._counts(Counter({**tally["refused"], "outside_grid_calendar": len(outside)}))
            return [record for record in found if str(record["session_date"])[:10] in index_of]

        records = inside(records, counts)
        served_records = inside(served_records, served_counts)
        void += [f"records_refused:{cause}:{count}" for cause, count in sorted(counts["refused"].items()) if cause not in ALLOWED_REFUSALS and count]
        served_void += [f"served:records_refused:{cause}:{count}" for cause, count in sorted(served_counts["refused"].items())
                        if cause not in ALLOWED_REFUSALS and count]
        served_void = shared + served_void
        basis = volume_basis(manifest)
        kept, screened = self._screen(records, current, basis=basis or "as_traded") if basis is not None else (set(), {"volume_basis": None})
        served_kept, served_screened = (self._screen(served_records, served_current, basis=basis) if basis is not None else (set(), {"volume_basis": None}))
        coverage = self._coverage(current)
        served_coverage = self._coverage(served_current)
        records_share = coverage[MARKET_GROUP]["records_share"]
        served_share = served_coverage[MARKET_GROUP]["records_share"]
        payload: dict[str, Any] = {
            "schema": SCHEMA_VERSION, "protocol": protocol(), "prereg_sha256": prereg_sha256, "code": code, "code_binding": binding,
            "manifest": {"manifest_sha256": manifest["manifest_sha256"], "schema": manifest["schema"], "market": manifest.get("market"),
                         "markets": manifest.get("markets"), "statements": manifest.get("statements"), "step_sessions": manifest.get("step_sessions"),
                         "grid_start": manifest.get("grid_start"), "price_pin": copy.deepcopy(manifest["price_pin"]),
                         "catalogue_pin": copy.deepcopy(manifest.get("catalogue_pin")), "entries": len(manifest["grid"]), "complete": manifest.get("complete")},
            "label_vintages": vintages, "label_cut": label_cut.isoformat(), "records_cut": records_cut.isoformat() if records_cut else None,
            "bounds": bounds, "grid": grid, "runs": runs, "coverage": coverage, "records": counts, "screen": screened,
            "anchor": anchor.isoformat() if anchor else None, "partition_last_index": partition_last,
            "horizons": None, "halves": None, "persistence": None, "names_per_session": None, "realized_sd_per_session": None, "descriptive": None,
        }
        served_block: dict[str, Any] = {
            "source": SERVED_SOURCE, "re_executes": SERVED_TP_SOURCE, "entries": len(manifest.get("served_grid") or []), "sources": manifest.get("sources"),
            "records_cut": served_cut.isoformat() if served_cut else None, "grid": served_grid, "runs": served_runs, "coverage": served_coverage,
            "records": served_counts, "screen": served_screened,
            "horizons": None, "halves": None, "persistence": None, "names_per_session": None, "realized_sd_per_session": None, "descriptive": None,
        }
        readings = {name: reading for name, reading, valid in ((SOURCE, (records, kept), not void), (SERVED_SOURCE, (served_records, served_kept), not served_void))
                    if valid}
        labelled = self._label_many(reader, readings, cuts) if readings else {}
        # S3 of the review: a reading that is not valid reads no label and publishes no statistic — per verdict
        if SOURCE in labelled:
            statistics_block, decided = self._statistics(*labelled[SOURCE], expected=expected, index_of=index_of, mature_through=mature_through,
                                                         partition_last=partition_last, records_share=records_share)
            counts.update(statistics_block.pop("counts"))
            payload.update(statistics_block)
        else:
            decided = verdict(None, None, coverage={"records_share": records_share, "screened_names_median": None}, void=void)
        if SERVED_SOURCE in labelled:
            statistics_block, served_decided = self._statistics(*labelled[SERVED_SOURCE], expected=expected, index_of=index_of, mature_through=mature_through,
                                                                partition_last=partition_last, records_share=served_share)
            served_counts.update(statistics_block.pop("counts"))
            served_block.update(statistics_block)
        else:
            served_decided = verdict(None, None, coverage={"records_share": served_share, "screened_names_median": None}, void=served_void)
        served_block["verdict"] = served_decided
        payload["verdict"] = decided
        payload["served_internal_tp"] = served_block
        payload["verdicts"] = {"primary": PRIMARY_VERDICT, "served_internal_tp": copy.deepcopy(served_decided), "v3_shadow": copy.deepcopy(decided)}
        return {"schema": SCHEMA_VERSION, "payload": payload, "payload_sha256": canonical_sha256(payload)}

    def _statistics(self, rows: list[dict[str, Any]], cohort: Counter[str], *, expected: Sequence[date], index_of: Mapping[str, int],
                    mature_through: Mapping[int, int | None], partition_last: int | None, records_share: float | None) -> tuple[dict[str, Any], dict[str, Any]]:
        """The statistics of ONE source's labelled observations and its verdict: the horizons on the screened set, the halves,
        the persistence co-condition, the names per session, the realized sd and the descriptive block (prereg §5–§7)."""
        decisory = [row for row in rows if row["screened"]]
        horizons = {str(horizon): accuracy.horizon_report(decisory, horizon, index_of=index_of, mature_through=mature_through, partition_last=partition_last)
                    for horizon in HORIZONS}
        primary = horizons[str(PRIMARY_HORIZON)]
        by_session = _points_by_session(decisory, PRIMARY_HORIZON)
        values = _session_values(by_session, DECISORY_STATISTIC, index_of)
        split = self._halves(by_session, primary, index_of=index_of, partition_last=partition_last)
        long_means = complete_block_means(values, block_length=PERSISTENCE_BLOCK_SESSIONS, mature_through=primary[DECISORY_STATISTIC]["mature_through_index"],
                                          partition_last=partition_last)
        persistence = {**persistence_test([mean for _block, mean in long_means]), "first_block": long_means[0][0] if long_means else None,
                       "last_block": long_means[-1][0] if long_means else None}
        names = self._names_per_session(by_session, [session.isoformat() for session in expected])
        realized_sd = panel._finite(statistics.stdev([value for _index, value in values])) if len(values) >= 2 else None
        block = {"counts": {"cohort": panel._counts(cohort), "observations": len(rows)}, "horizons": horizons, "halves": split, "persistence": persistence,
                 "names_per_session": names, "realized_sd_per_session": realized_sd,
                 "descriptive": self._descriptive(rows, decisory, by_session, values, index_of=index_of, mature_through=dict(mature_through),
                                                  partition_last=partition_last)}
        decided = verdict(primary, split[DECISORY_STATISTIC], persistence=persistence,
                          coverage={"records_share": records_share, "screened_names_median": names["executable_h_primary"]["median"]})
        return block, decided

    @staticmethod
    def _halves(by_session: Mapping[str, Sequence[Mapping[str, Any]]], primary: Mapping[str, Any], *, index_of: Mapping[str, int],
                partition_last: int | None) -> dict[str, Any]:
        """The halves of the decisory blocks (and, descriptive, of the total-return IC), from the same per-session values
        the accuracy report blocks — the complete blocks recomputed here must be exactly its ``blocks``/``estimate``."""
        result: dict[str, Any] = {}
        for statistic in (DECISORY_STATISTIC, "ic"):
            values = _session_values(by_session, statistic, index_of)
            means = complete_block_means(values, block_length=PRIMARY_HORIZON, mature_through=primary[statistic]["mature_through_index"], partition_last=partition_last)
            blocks = primary[statistic]["blocks"]
            if len(means) != blocks["blocks"] or accuracy.batch_means_test([mean for _block, mean in means])["estimate"] != blocks["estimate"]:
                raise RuntimeError(f"the halves' blocks of {statistic} are not the accuracy report's blocks: the block rule drifted")
            result[statistic] = halves(means)
        return result

    @staticmethod
    def _names_per_session(by_session: Mapping[str, Sequence[Mapping[str, Any]]], sessions: Sequence[str]) -> dict[str, Any]:
        """The screened names with an executable return at the primary horizon on EVERY session of the grid — a session
        without any counts zero (the coverage floor's median)."""
        counts = [float(sum(1 for item in by_session.get(session, []) if item["return_executable"] is not None)) for session in sessions]
        return {"executable_h_primary": _distribution(counts)}

    @staticmethod
    def _descriptive(rows: Sequence[Mapping[str, Any]], decisory: Sequence[Mapping[str, Any]], by_session: Mapping[str, Sequence[Mapping[str, Any]]],
                     values: Sequence[tuple[int, float]], *, index_of: Mapping[str, int], mature_through: Mapping[int, int | None],
                     partition_last: int | None) -> dict[str, Any]:
        """Never decisory: the unscreened catalogue at the primary horizon; the executable IC per exchange; the IC with the
        upside ranked WITHIN its exchange; the executable IC per calendar year."""
        h = PRIMARY_HORIZON
        exec_through = mature_through.get(h + EXECUTION_LAG_SESSIONS)
        unscreened = accuracy.horizon_report(rows, h, index_of=index_of, mature_through=mature_through, partition_last=partition_last)
        per_exchange: dict[str, Any] = {}
        for market in MARKETS:
            subset = {session: [item for item in items if item["market"] == market] for session, items in by_session.items()}
            points = _session_values(subset, DECISORY_STATISTIC, index_of)
            per_exchange[market] = {"sessions_measured": len(points),
                                    "blocks": accuracy.block_statistics(points, block_length=h, mature_through=exec_through, partition_last=partition_last)}
        within: list[tuple[int, float]] = []
        for session, items in sorted(by_session.items()):
            usable = [item for item in items if item["return_executable"] is not None]
            if len(usable) < accuracy.MIN_NAMES_PER_SESSION:
                continue
            percentile: dict[int, float] = {}
            for market in MARKETS:
                members = [index for index, item in enumerate(usable) if item["market"] == market]
                ranks = accuracy.average_ranks([usable[index]["upside"] for index in members])
                percentile.update({index: rank / len(members) for index, rank in zip(members, ranks)})
            value = accuracy.spearman([percentile[index] for index in range(len(usable))], [item["return_executable"] for item in usable])
            if value is not None:
                within.append((index_of[session], value))
        sessions_by_index = {index: session for session, index in index_of.items()}
        by_year: dict[str, list[float]] = {}
        for index, value in values:
            by_year.setdefault(sessions_by_index[index][:4], []).append(value)
        return {"unscreened": {str(h): unscreened}, "per_exchange": per_exchange,
                "within_exchange_rank_ic": {"sessions_measured": len(within),
                                            "blocks": accuracy.block_statistics(within, block_length=h, mature_through=exec_through, partition_last=partition_last)},
                "ic_by_year": {year: {"sessions": len(items), "mean": panel._finite(math.fsum(items) / len(items))} for year, items in sorted(by_year.items())},
                "decisory_observations": len(decisory)}


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PREREG_VALUATION_PIT_BACKTEST_US_V1: the single look of the US point-in-time backtest of the V3.2 internal "
                                                 "TP over a grid manifest — read-only, no network; prints the aggregate receipt (no symbols).")
    parser.add_argument("--manifest", required=True, help="the grid manifest (VALUATION-PIT-GRID-MANIFEST-v1) path, or - for stdin")
    parser.add_argument("--prereg", type=Path, default=None, help="path of the pre-registration document: its sha256 and its code pins travel inside the payload")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read(MAX_MANIFEST_BYTES + 1) if args.manifest == "-" else Path(args.manifest).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        parser.error(f"--manifest cannot be read ({type(error).__name__})")
    try:
        manifest = load_manifest(text)
    except ManifestError as error:
        parser.error(f"--manifest: {error}")
    prereg_sha256: str | None = None
    code_pins: dict[str, str] | None = None
    if args.prereg is not None:
        if not args.prereg.is_file():
            parser.error(f"--prereg {args.prereg} is not a file")
        content = args.prereg.read_bytes()
        prereg_sha256 = hashlib.sha256(content).hexdigest()
        try:
            code_pins = accuracy.pins_from_prereg(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            parser.error(f"--prereg {args.prereg}: {error}")
    accuracy.force_read_only_session()
    settings = get_settings()
    service = PitBacktestReportService(cast(Database, ReadOnlyStore(Database(settings))), settings=settings)
    result = service.report(manifest, prereg_sha256=prereg_sha256, code_pins=code_pins, build_sha=os.environ.get("C3PO_BUILD_SHA"))
    if service.http is not None and service.http.calls != 0:  # the network-free guarantee is checked, not asserted
        raise RuntimeError(f"the report made {service.http.calls} network call(s)")
    result["provenance"] = {"generated_at": datetime.now(timezone.utc).isoformat()}  # outside the payload
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
