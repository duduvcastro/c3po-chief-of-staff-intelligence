"""Valuation ensemble — the nightly LIVE producer of the signed grid's PRIMARY target price, for EVERY US common stock.

Once the pinned point-in-time grid (``valuation_ensemble_grid.compute_grid_section``, instrument pin ``b77f2400…``)
reports PASS, the served target price may switch to the ensemble's primary variant
(``minmax_trimmed_mean_with_consensus``). This module computes THAT number every night for NASDAQ and NYSE from LIVE
inputs at the run's clock ``T`` instead of the grid's stored snapshots — through the grid's own pinned functions, imported
and called unchanged: the rev3 admission and screen inputs (``valuation_pit_rerun.PitSourceResolver`` /
``PitComputation.screen_inputs``), the as-filed reader and payload, the pinned price publication (close of D, ≥ 90 valid
sessions, capital events, OLS beta on the equal-weight proxy), ``curve_package_at``, ``reduce_company_facts``,
``valuation_ensemble_grid._shares``, ``GridCompanyInputs``, ``derive_premises``, ``evaluate_models``,
``grid_consensus_at`` (latest eligible target per house in ``(T − 90 d, T]``, ≥ 3 houses, house mean) and
``aggregate_grid_variants``. Only the per-name loop of ``compute_grid_section`` (inline there, not a function) is restated
here (``_LiveSection._prepare`` / ``_finalize``); the parity tests pin it to the grid's floats on the grid's own fixture.

Population (owner, 28/10/2026: "o valuation tem que cobrir todos os papeis USA"), no cap of its own:

* the SERVED catalogue — ``valuation_universe/<M>_UNIVERSE`` (today ≤ 300 stocks + 25 ETFs, ``us_screener``) — is the
  grid's catalogue: its names are computed EXACTLY as the grid computes them (beta proxy = its symbols, peers = its
  evaluable names), and ``pit_tested`` marks the ones the grid's screen keeps (``valuation_pit_backtest_report.screen``
  on its admitted names: stock, close ≥ 3, cap ≥ 750 M, 20-session median dollar volume ≥ 20 M, the 300 most liquid);
* plus every other common stock (``security_type == "Stock"``) of the latest listed-universe publication
  (``official_listing_catalogue/<M>``, the draft listed universe), when one is published and its manifest verifies. These
  names carry no classification (the listing has no sector or profile), so the peer models refuse them; they are valued
  with the same proxy and peers as the tested names (adding them changes no tested number), admitted in chunks of
  ``EXTRA_CHUNK`` whose price series are dropped after use (bounded memory), and read at most ``EXTRA_TARGET_PAGES`` pages
  of targets (a history that fills them is refused, not truncated). ``pit_tested`` is False for them: buy permission
  stays with the tested names.

Order under the deadline and the breaker: the tested names of BOTH exchanges are read first, then every other evaluable
name by liquidity (the 20-session median dollar volume), so a deadline reaches the tested names before any other; each
section records how many names were reached and how many are pending. Every provider request is bounded as a WHOLE
response by the time left (``DeadlineJsonHttpClient``); reads stop at the deadline and finished sections may be written
until ``PUBLISH_GRACE`` after it. An open breaker after the tested reads skips the listed-only names. An exchange whose
own preparation fails, or a listed-only chunk that fails, is set aside and counted: the other exchange, and every tested
name, go on. A listed-only name that cannot be admitted says which coverage it lacks (``no_price_history``,
``no_asfiled_statements``), counted per section (``counts.listed_only_coverage``).

Where live cannot equal the grid's PIT inputs: the catalogue is today's, not the grid's pinned one; the price publication
is tonight's (its history can be re-adjusted by the provider since the grid's 120-month vintage); the Treasury and target
histories are fetched now (a revised, deleted or backfilled row differs, and the grid's snapshot was fetched once, before
its run); the resolver's outstandingShares fallback (screen market cap only) reads the latest ``valuation_pit_source``
EODHD snapshot exactly as rev3 does, which is stale; ``T`` is the run's clock, not the grid's 01:00 America/Sao_Paulo
convention; the screen's volume basis is voted tonight (``valuation_pit_grid.volume_check`` over BOTH exchanges'
publications), not read from the grid's manifest — when undetermined, ``pit_tested`` requires the name under BOTH bases.
The fetches persist NOTHING to ``valuation_pit_source``: the signed grid's pinned sources stay untouched. ``pit_tested``
says that the grid's screen RULE keeps the name tonight (on tonight's inputs); it does not prove that the name was in the
grid's tested sample on its past dates — a consumer that needs historical membership reads the grid's own records.

Fail closed: an exchange whose price pin, catalogue, statements table or Treasury curve cannot be read writes no snapshot;
a name it cannot evaluate gets ``origin = not_evaluable:<reason>`` and no number — a target read that fails is a refusal,
never a TP without the consensus it could not read; a section whose provider failed, whose tested names were not all
reached or which has no TP at all is not published (``unpublishable``). Nothing here is served or selected
(``valuation_official.market_of_entity`` ignores this analysis type); the one consumer is the R2D2 paper engine's buy
permission, on the signed grid's PASS (owner 31/10/2026: ``r2d2_live_engine.load_targets``, pit_tested names); off by default
(``valuation_env.ensemble_live_enabled``). Logs carry counts and error classes only, never a symbol.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol, cast

from . import valuation_env, valuation_pit_rerun as pit
from .config import Settings
from .database import Database
from .market_data.http import DeadlineJsonHttpClient, JsonHttpClient, MarketDataRequestError
from .valuation_ensemble_aggregation import GRID_PRIMARY_VARIANT, aggregate_grid_variants
from .valuation_ensemble_grid import _shares
from .valuation_ensemble_grid_consensus import grid_consensus_at
from .valuation_ensemble_grid_inputs import GridCompanyInputs, _date, _instant, derive_premises, reduce_company_facts
from .valuation_ensemble_inputs import Evidence, NotEvaluable, Price, canonical_hash, utc
from .valuation_ensemble_models import MODEL_IDS, ModelValue, evaluate_models
from .valuation_official import canonical_sha256
from .valuation_panel import _NoNetworkHttp
from .valuation_pit_backtest_report import VOLUME_BASES, screen
from .valuation_price_history import PriceHistoryService

logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "valuation_ensemble_live"
SCHEMA = "VALUATION-ENSEMBLE-LIVE-v2"
SOURCE = "ensemble_live"
METHODOLOGY_KEY = "valuation_ensemble_live"
METHODOLOGY_VERSION = 1
MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")
PRIMARY = GRID_PRIMARY_VARIANT  # = valuation_ensemble_pin.PROTOCOL_CONSTANTS["primary"] (pinned by test)
STATEMENTS = "vintages"  # the grid's statements mode: as-filed SEC facts only
CLASSIFICATION = "current_pinned_catalogue_rev3_convention"  # the only label GridCompanyInputs.sector_at_T admits (peer sectors)
SIGNED_INSTRUMENT_PIN = "b77f2400ef5bac57bd266f3e2edb26a9d63356b5c3fc65d47da490c8c8be6f86"
LISTED_ANALYSIS = "official_listing_catalogue"  # the listed universe (draft): entity = the exchange, outputs = the catalogue
LISTED_SCHEMA = "OFFICIAL-LISTED-UNIVERSE-v1"
EXTRA_CHUNK = 250  # listed-only names admitted per resolver pass; their series are dropped after it
EXTRA_TARGET_PAGES = 3  # target pages read for a listed-only name (100 rows each); a full read is refused, never truncated
TARGET_PAGE_LIMIT = 100  # PitFetchService.fetch_targets' rows per page
TARGETS_BREAKER_CONSECUTIVE = 10  # consecutive failed target reads = the provider is down (403/429/outage): stop reading
TARGETS_MAX_FAILED_SHARE = 0.10  # an exchange whose failed target reads exceed this share of the attempted ones is not published
REQUEST_TIMEOUT_SECONDS = 30.0  # the WHOLE response of one provider request (headers and body), never past the deadline
PUBLISH_GRACE = timedelta(minutes=5)  # reads stop at the deadline; finished sections may be written until deadline + grace
IMPLEMENTATION_FILES: tuple[str, ...] = (  # every module whose bytes can move a published number or flag, hashed into the context
    "valuation_live_ensemble.py", "valuation_ensemble_grid.py", "valuation_ensemble_grid_inputs.py", "valuation_ensemble_grid_consensus.py",
    "valuation_ensemble_aggregation.py", "valuation_ensemble_models.py", "valuation_ensemble_inputs.py", "valuation_ensemble_adapters.py",
    "valuation_pit_rerun.py", "valuation_pit_backtest_report.py", "valuation_price_history.py", "valuation_v2_engine.py",
    "valuation_v3_macro.py", "sec_xbrl.py", "statement_vintages.py", "valuation_asfiled.py",
    "valuation_official.py",  # session_date_of (which close is "close of D") and canonical_sha256
    "valuation_panel.py",  # _positive inside the screen
    "valuation_pit_grid.py",  # volume_check: the screen's volume basis
    "market_data/eodhd.py", "market_data/http.py",  # the GBOND bars' number parsing and the JSON every live read decodes
)


class TargetReader(Protocol):
    def __call__(self, market: str, symbol: str, *, pages: int | None = None) -> Sequence[Mapping[str, Any]]: ...


class LiveEnsembleError(RuntimeError):
    """A market-level refusal: no snapshot is written for that market. The text is a stable code, never a symbol."""


class LiveEnsembleDeadline(LiveEnsembleError):
    """The night's wall-clock deadline passed: nothing more is read."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _check_deadline(deadline: datetime | None, clock: Callable[[], datetime]) -> None:
    if deadline is not None and utc(clock()) >= utc(deadline):
        raise LiveEnsembleDeadline("deadline_reached")


def implementation_files() -> dict[str, str]:
    app = Path(__file__).parent
    return {name: hashlib.sha256((app / name).read_bytes()).hexdigest() for name in IMPLEMENTATION_FILES}


class _DeadlineHttp(JsonHttpClient):
    """The provider client behind the night's deadline. The process's real ``JsonHttpClient`` bounds each socket
    operation only, so a slow-drip body could run past the stop: each attempt is made instead through
    ``DeadlineJsonHttpClient``, whose bound covers the WHOLE response, set to the time left before the deadline (at most
    ``REQUEST_TIMEOUT_SECONDS``), and every attempt (the client's retries) checks the deadline first. Any other client
    (a test double) is called as is, after the check."""

    def __init__(self, inner: JsonHttpClient, *, deadline: datetime | None, clock: Callable[[], datetime]) -> None:
        super().__init__(timeout=float(getattr(inner, "timeout", 0.0)), max_retries=int(getattr(inner, "max_retries", 0)))
        self.inner, self.deadline, self.clock = inner, deadline, clock
        self.bounded = type(inner) is JsonHttpClient

    def _bound(self) -> float:
        if self.deadline is None:
            return REQUEST_TIMEOUT_SECONDS
        left = (utc(self.deadline) - utc(self.clock())).total_seconds()
        return min(REQUEST_TIMEOUT_SECONDS, max(left, 0.001))

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        if not self.bounded:
            _check_deadline(self.deadline, self.clock)
            return self.inner.get_json(url, params=params, headers=headers)
        failure: Exception = MarketDataRequestError("request_failed")
        for _attempt in range(self.max_retries + 1):
            _check_deadline(self.deadline, self.clock)
            try:
                return DeadlineJsonHttpClient(timeout=self._bound()).get_json(url, params=params, headers=headers)
            except MarketDataRequestError as error:
                failure = error
        raise failure


class _DeadlineDatabase:
    """The database as the night's READERS see it: every method call (one read) checks the deadline first, so a slow store
    never starts a new read after the cut (a read already started may finish). Attributes pass through; writes (``publish``)
    use the real database. The as-filed store is NOT given this proxy (it keeps lists on the database itself):
    ``_DeadlineAsFiledReader`` guards its reads instead."""

    def __init__(self, database: Database, *, deadline: datetime, clock: Callable[[], datetime]) -> None:
        self._database, self._deadline, self._clock = database, deadline, clock

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._database, name)
        if not callable(value):
            return value

        def guarded(*args: Any, **kwargs: Any) -> Any:
            _check_deadline(self._deadline, self._clock)
            return value(*args, **kwargs)
        return guarded


def _readers_database(database: Database, deadline: datetime | None, clock: Callable[[], datetime]) -> Database:
    return database if deadline is None else cast(Database, _DeadlineDatabase(database, deadline=deadline, clock=clock))


class _DeadlineAsFiledReader(pit.AsFiledReader):
    """rev3's as-filed reader with the deadline checked before each read (presence, coverage, one issuer's facts)."""

    def __init__(self, database: Database, *, deadline: datetime | None, clock: Callable[[], datetime]) -> None:
        super().__init__(database)
        self._deadline, self._clock = deadline, clock

    def present(self) -> bool:
        _check_deadline(self._deadline, self._clock)
        return super().present()

    def coverage(self, market: str) -> dict[str, str]:
        _check_deadline(self._deadline, self._clock)
        return super().coverage(market)

    def facts(self, issuer_key: str, *, as_of: datetime, refused: Counter[str]) -> list[dict[str, Any]]:
        _check_deadline(self._deadline, self._clock)
        return super().facts(issuer_key, as_of=as_of, refused=refused)


class LiveSourceFetch(pit.PitFetchService):
    """The PIT fetcher's own provider reads (``fetch_targets``, ``fetch_macro``: endpoints, pagination, units) with the
    payload kept in memory: ``_persist`` never writes ``valuation_pit_source``, whose snapshots the signed grid pins."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient, *, deadline: datetime | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        super().__init__(settings, database, _DeadlineHttp(http, deadline=deadline, clock=clock or (lambda: datetime.now(timezone.utc))))
        self.captured: dict[str, Any] = {}
        self.calls: Counter[str] = Counter()

    def _persist(self, entity_key: str, *, provider: str, endpoint: str, market: str, symbol: str | None, payload: Any,
                 fetched_at: datetime) -> str:
        self.captured[entity_key] = payload
        self.calls[provider] += 1
        return "live:" + canonical_sha256(payload)

    def target_rows(self, market: str, symbol: str, *, pages: int | None = None) -> list[dict[str, Any]]:
        """The RAW per-house target history of one name, as the grid's snapshot holds it (a list, else a refusal);
        ``pages`` None = the grid's own fetch (20 pages)."""
        if pages is None:
            self.fetch_targets(market, symbol)
        else:
            self.fetch_targets(market, symbol, pages=pages)
        payload = self.captured.pop(pit.source_entity_key(market, pit.PROVIDER_FMP, symbol), None)
        if not isinstance(payload, list):
            raise LiveEnsembleError("targets_not_captured")
        return payload


def live_treasury_curve(fetch: LiveSourceFetch, *, as_of: datetime, market: str = "NASDAQ") -> tuple[dict[str, Any], dict[str, Any]]:
    """The 3Y/10Y package at ``T`` from a fresh EODHD GBOND history, through ``curve_package_at`` (series unit, next-UTC-
    midnight availability, latest common date ≤ the economic date). ``None`` at ``T`` is a refusal, never a stale rate."""
    cut = utc(as_of)
    fetch.fetch_macro(market)
    history = fetch.captured.pop(pit.MACRO_TREASURY_KEY, None)
    if not isinstance(history, dict):
        raise LiveEnsembleError("treasury_history_not_captured")
    curve = pit.curve_package_at(history, as_of=cut, economic_date=pit.economic_date_of(market, cut))
    if curve is None:
        raise LiveEnsembleError("treasury_curve_unavailable_at_T")
    return curve, {"origin": "live_fetch:" + pit.MACRO_TREASURY_KEY, "source_payload_sha256": history.get("payload_sha256"),
                   "derived_payload_sha256": curve.get("payload_sha256"), "as_of": curve.get("as_of"), "fetched_at": history.get("fetched_at")}


def decide_volume_basis(database: Database, settings: Settings, prices: Mapping[str, pit.PinnedPrices]) -> tuple[str | None, dict[str, Any]]:
    """The screen's volume basis, decided as the grid decides it (``valuation_pit_grid.volume_check``: the votes of every
    catalogue series of the pinned publications, read only); ``None`` when undetermined."""
    from . import valuation_pit_grid as pit_grid  # the grid's CLI module, loaded only when a night actually runs

    pins = {market: {"available_at": pinned.available_at.isoformat(), "publication_id": pinned.publication_id} for market, pinned in prices.items()}
    result = pit_grid.volume_check(database, settings, pins, sorted(pins), None)
    decision = result.get("decision")
    receipt = {key: result.get(key) for key in ("events", "as_traded_like", "split_adjusted_like", "decision", "series_read")}
    return (str(decision) if decision in VOLUME_BASES else None), receipt


def listing_symbol(value: Any) -> str:
    """One spelling per share class: the provider's (``BRK-B``), whatever the listing wrote (``BRK.B``, ``BRK/B``)."""
    return re.sub(r"[./ ]+", "-", str(value or "").strip().upper())


def listed_population(database: Database, market: str, *, before: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every common stock of the latest listed-universe publication of ``market``, as admitted catalogue rows WITHOUT
    classification (the listing carries none), one row per share class; ``[]`` when none is published or it does not
    verify (manifest, or a malformed ``listings``) — the exchange's served catalogue still runs."""
    snapshot = (database.latest_analysis_snapshot(LISTED_ANALYSIS, market) if before is None
                else database.latest_analysis_snapshot_before(LISTED_ANALYSIS, market, utc(before)))
    if snapshot is None:
        return [], {"status": "absent"}
    outputs = _mapping(snapshot.get("outputs"))
    reference: dict[str, Any] = {"snapshot_id": str(snapshot.get("id")), "manifest_sha256": outputs.get("manifest_sha256")}
    try:
        if not (outputs.get("schema") == LISTED_SCHEMA and outputs.get("market") == market
                and outputs.get("manifest_sha256") == canonical_hash({k: v for k, v in outputs.items() if k != "manifest_sha256"})):
            return [], {**reference, "status": "refused_manifest"}
        listings = outputs.get("listings")
        if not isinstance(listings, list):
            raise TypeError("listings_not_a_list")
        symbols = {listing_symbol(item.get("symbol")) for item in listings
                   if isinstance(item, Mapping) and item.get("market") == market and item.get("security_type") == "Stock"}
    except (TypeError, ValueError, AttributeError):
        return [], {**reference, "status": "refused_listings"}
    rows = [{"symbol": symbol, **{name: None for name in pit.CURRENT_FIELDS_ADMITTED}, "security_type": "Stock"}
            for symbol in sorted(symbols) if symbol]
    return rows, {**reference, "status": "read", "stocks": len(rows)}


@dataclass(frozen=True)
class LiveInputs:
    """Everything one (exchange, T) section reads, resolved before any model runs. ``targets(market, symbol, pages=)``
    returns the RAW target rows or raises (a provider failure); the parity test passes the grid's pinned rows instead.
    ``catalogue`` and its admission are the served catalogue's (the grid's); ``extra_rows`` are the listed-only stocks."""
    market: str
    as_of: datetime
    prices: pit.PinnedPrices
    reader: pit.AsFiledReader
    catalogue: list[dict[str, Any]]
    catalogue_reference: dict[str, Any]
    screen_inputs: dict[str, dict[str, Any]]
    not_admitted: dict[str, str]
    statement_references: list[dict[str, Any]]
    curve: dict[str, Any]
    curve_reference: dict[str, Any]
    targets: TargetReader
    volume_basis: str | None
    volume_check: dict[str, Any] | None = None
    extra_rows: list[dict[str, Any]] = field(default_factory=list)
    listed_reference: dict[str, Any] = field(default_factory=dict)
    database: Any = None


class _PopulationResolver(pit.PitSourceResolver):
    """rev3's resolver over a given set of rows (one chunk of listed-only names) instead of the latest catalogue: every
    other step of ``resolve`` — statements, sessions, close, shares, capital events, screen inputs — is the pinned one."""

    def __init__(self, database: Database, *, rows: Sequence[Mapping[str, Any]], **kwargs: Any) -> None:
        super().__init__(database, **kwargs)
        self._rows = [dict(row) for row in rows]

    def catalogue(self, market: str) -> list[dict[str, Any]]:
        self.catalogue_rows = len(self._rows)
        self.catalogue_stocks = sum(row.get("security_type") == "Stock" for row in self._rows)
        self.catalogue_snapshot_id = "listed_population_chunk"
        self.references.append({"role": "catalogue", "market": market, "classification_sha256": canonical_sha256(self._rows),
                                "rows": len(self._rows), "fields_admitted": list(pit.CURRENT_FIELDS_ADMITTED)})
        return [dict(row) for row in self._rows]


def _admitted(resolver: pit.PitSourceResolver) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    screen_inputs = pit.PitComputation.screen_inputs(cast(pit.PitComputation, SimpleNamespace(resolver=resolver)))
    return (screen_inputs, dict(resolver.not_evaluable),
            [dict(item) for item in resolver.references if item.get("role") == pit.BASIS_VINTAGES])


def gather_live_inputs(database: Database, *, market: str, as_of: datetime, prices: pit.PinnedPrices, curve: Mapping[str, Any],
                       curve_reference: Mapping[str, Any], targets: TargetReader, volume_basis: str | None,
                       volume_check: Mapping[str, Any] | None = None, reader: pit.AsFiledReader | None = None,
                       listed: bool = True, deadline: datetime | None = None, clock: Callable[[], datetime] | None = None,
                       catalogue_cut: datetime | None = None) -> LiveInputs:
    """rev3's admission at ``T``, unchanged, over the served catalogue: ``PitSourceResolver`` (``vintages``, the latest
    catalogue) decides which names have statements, ≥ 90 valid sessions, a close and shares at ``T``, and
    ``PitComputation.screen_inputs`` (which reads only ``self.resolver``) gives the screen inputs the grid's sibling run
    stored. ``listed``: add the listed-only stocks (admitted later, in chunks). ``deadline``: every read of the resolver
    (each issuer's facts, each series, each snapshot) checks it before it starts. ``catalogue_cut`` (the nightly run: its
    ``T``): the served catalogue and the listing are the latest published BEFORE it, never one published during the run;
    ``None`` (the parity tests, at a past ``T``): the grid's convention, the current catalogue. Market-level defects raise."""
    cut = utc(as_of)
    tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
    reads = _readers_database(database, deadline, tick)
    if market not in MARKETS:
        raise LiveEnsembleError("unsupported_market")
    if prices.market != market or utc(prices.as_of) != cut:
        raise LiveEnsembleError("price_pin_not_of_this_section")
    if not isinstance(curve, Mapping) or pit._number(curve.get("interpolated_5y_rate")) is None:
        raise LiveEnsembleError("treasury_curve_unavailable")
    if volume_basis is not None and volume_basis not in VOLUME_BASES:
        raise LiveEnsembleError("unknown_volume_basis")
    reader = reader if reader is not None else _DeadlineAsFiledReader(database, deadline=deadline, clock=tick)
    resolver = pit.PitSourceResolver(reads, market=market, as_of=cut, prices=prices, statements=STATEMENTS, vintages=reader,
                                     catalogue_pinned_at=utc(catalogue_cut) if catalogue_cut is not None else None)
    resolver.resolve()
    if resolver.catalogue_snapshot_id is None:
        raise LiveEnsembleError("catalogue_missing")
    catalogue = pit.admitted_catalogue(reads.analysis_snapshot_by_id(resolver.catalogue_snapshot_id))
    roles = [item for item in resolver.references if item.get("role") == "catalogue"]
    if not catalogue or len(roles) != 1 or roles[0].get("classification_sha256") != canonical_hash(catalogue):
        raise LiveEnsembleError("catalogue_changed_during_run")
    screen_inputs, not_admitted, references = _admitted(resolver)
    catalogue_reference = {"snapshot_id": resolver.catalogue_snapshot_id, "classification_sha256": roles[0]["classification_sha256"],
                           "rows": len(catalogue), "stocks": sum(row.get("security_type") == "Stock" for row in catalogue)}
    extra_rows: list[dict[str, Any]] = []
    listed_reference: dict[str, Any] = {"status": "not_requested"}
    if listed:
        listed_rows, listed_reference = listed_population(reads, market, before=catalogue_cut)
        served = {listing_symbol(row["symbol"]) for row in catalogue}
        extra_rows = [row for row in listed_rows if row["symbol"] not in served]
    return LiveInputs(market, cut, prices, reader, catalogue, catalogue_reference, screen_inputs, not_admitted, references, dict(curve),
                      dict(curve_reference), targets, volume_basis, dict(volume_check) if volume_check is not None else None,
                      extra_rows, listed_reference, reads)


def _statement_reference(references: Sequence[Mapping[str, Any]], symbol: str) -> Mapping[str, Any] | None:
    key = pit.symbol_hash(symbol)
    found = [item for item in references if item.get("symbol_sha256") == key]
    return found[0] if len(found) == 1 else None


def _evict(prices: pit.PinnedPrices, symbols: Iterable[str]) -> None:
    """Drop one chunk's series from the pin's per-symbol caches (the served catalogue's stay: they are the proxy). Holding
    every series of a listed universe at once (~1 MB per 120-month series) would not fit the host."""
    keys = {key for symbol in symbols for key in (symbol, symbol.strip().upper())}
    for cache in ("_bars", "_returns", "_capital_events", "_splits"):
        store = getattr(prices, cache, None)
        if isinstance(store, dict):
            for key in keys:
                store.pop(key, None)


@dataclass
class _Name:
    row: dict[str, Any]
    served: bool  # in the served catalogue (the grid's)
    pit_tested: bool = False
    screened: bool | None = None
    screen: dict[str, Any] | None = None
    issuer: str | None = None
    facts_rows_sha256: str | None = None
    company: GridCompanyInputs | None = None
    premises: Any = None
    refusal: str | None = None
    models: tuple[ModelValue, ...] = ()
    targets: list[Mapping[str, Any]] | None = None
    target_error: str | None = None
    pending: str | None = None  # pending_preparation / pending_targets: the deadline came first

    @property
    def symbol(self) -> str:
        return str(self.row["symbol"])

    def liquidity(self, basis: str | None) -> float:
        value = pit._positive(_mapping(self.screen).get(VOLUME_BASES.get(basis or "", "dollar_volume_median_20")))
        return value if value is not None else -math.inf


@dataclass
class _TargetReads:
    """The provider's state across both exchanges of one night (one provider, one breaker)."""
    attempted: int = 0
    failed: int = 0
    consecutive: int = 0

    @property
    def open(self) -> bool:
        return self.consecutive >= TARGETS_BREAKER_CONSECUTIVE


class _LiveSection:
    """One exchange at ``T``: the served catalogue first (the grid's computation), then the listed-only names."""

    def __init__(self, inputs: LiveInputs) -> None:
        self.inputs = inputs
        self.market, self.cut, self.prices, self.reader = inputs.market, utc(inputs.as_of), inputs.prices, inputs.reader
        symbols = [str(row["symbol"]) for row in inputs.catalogue]
        extra = [str(row["symbol"]) for row in inputs.extra_rows]
        if len(symbols) != len(set(symbols)) or len(extra) != len(set(extra)) or set(symbols) & set(extra):
            raise LiveEnsembleError("duplicate_population_symbol")
        self.catalogue_symbols = symbols
        self.names: dict[str, _Name] = {str(row["symbol"]): _Name(dict(row), True) for row in inputs.catalogue}
        self.names.update({str(row["symbol"]): _Name(dict(row), False) for row in inputs.extra_rows})
        self.issuer_digests: dict[str, str] = {}
        self.coverage: dict[str, str] = {}
        self.peers: tuple[GridCompanyInputs, ...] = ()
        self.screen_refused: Counter[str] = Counter()
        self.pit_tested_rule = ""
        self.reads = Counter[str]()
        self.failure: str | None = None  # the exchange's own preparation failed: it is not published, the other one is
        self.chunks_failed = 0
        self.deadline: datetime | None = None  # set by _run_sections: checked before every preparation step
        self.clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    # ---- inputs (compute_grid_section's per-name loop, the same calls in the same order)
    def _prepare(self, name: _Name, screen_inputs: Mapping[str, Mapping[str, Any]], not_admitted: Mapping[str, str],
                 references: Sequence[Mapping[str, Any]], raw_by_issuer: dict[str, list[dict[str, Any]]]) -> None:
        _check_deadline(self.deadline, self.clock)  # one name is one preparation step: none starts after the cut
        market, cut, prices, reader = self.market, self.cut, self.prices, self.reader
        row, symbol = name.row, name.symbol
        name.screen = dict(screen_inputs[symbol]) if symbol in screen_inputs else None
        try:
            if row.get("security_type") != "Stock":
                raise NotEvaluable("not_a_stock")
            if symbol not in screen_inputs:
                raise NotEvaluable(self._not_admitted(name, not_admitted))
            issuer = self.coverage.get(symbol)
            if not issuer:
                raise NotEvaluable("statement_vintages_missing")
            if issuer not in raw_by_issuer:
                refused: Counter[str] = Counter()
                raw_by_issuer[issuer] = reader.facts(issuer, as_of=cut, refused=refused)
                self.issuer_digests[issuer] = canonical_sha256(sorted(str(r["row_hash"]) for r in raw_by_issuer[issuer]))
            raw = raw_by_issuer[issuer]
            name.issuer = issuer
            payload, reference = pit.as_filed_payload(raw, market=market, front=reader.front)
            expected = _statement_reference(references, symbol)
            if expected is None or any(expected.get(key) != reference.get(key) for key in reference):
                raise NotEvaluable("statements_changed_during_run")  # a fact accepted by T landed between the two reads
            facts, facts_audit = reduce_company_facts(raw, issuer=issuer, as_of=cut, front=reader.front)
            name.facts_rows_sha256 = facts_audit.get("accepted_rows_sha256")
            fundamentals = pit.pit_fundamentals(payload, market=market, economic_date=pit.economic_date_of(market, cut))
            balance_end = _mapping(fundamentals.get("balance")).get("period_end")
            if balance_end is not None and facts:
                share_fact = _shares(raw, front=reader.front, end=_date(balance_end))
                if share_fact is not None:
                    facts["shares"], facts_audit["derivations"]["shares"] = share_fact
            if prices.valid_sessions(symbol) < pit.MIN_VALID_SESSIONS:
                raise NotEvaluable(f"fewer_than_{pit.MIN_VALID_SESSIONS}_valid_sessions_at_T")
            price, price_session = prices.price_at(symbol)
            if price is None or price_session != prices.session_date:
                raise NotEvaluable("close_D_unavailable")
            if price != pit._positive(_mapping(screen_inputs[symbol]).get("close")):
                raise NotEvaluable("close_changed_during_run")
            shares = facts.get("shares")
            if shares is None:
                raise NotEvaluable("official_cover_shares_unavailable")
            if any(day > shares.period_end.isoformat() for day in prices.capital_events(symbol)):
                raise NotEvaluable("capital_event_between_shares_and_T")
            basis = "rev3-as-traded:" + prices.publication_id + ":" + issuer  # the grid's basis label (an identity, no number)
            price_evidence = Evidence("PRICE", prices.publication_id, prices.available_at, prices.bars_sha256)
            profile = row.get("valuation_profile")
            financial = profile == "financial" if isinstance(profile, str) and profile in {"financial", "general", "cyclical"} else None
            sector = row.get("sector")
            company = GridCompanyInputs(symbol, market, "USD", cut, basis,
                Price(price, "USD", _date(price_session), basis, price_evidence), facts,
                sector=sector.strip() if isinstance(sector, str) else "", sector_evidence=None, financial_company=financial, issuer_id=issuer,
                protocol={"basis_id": basis, "session_date": prices.session_date, "catalogue_classification": CLASSIFICATION})
            company.validate()
            beta, beta_audit = prices.beta(symbol)
            name.premises, _ = derive_premises(company, curve=self.inputs.curve, beta=beta, beta_audit=beta_audit, facts_audit=facts_audit)
            name.company = company
        except NotEvaluable as error:
            name.refusal = str(error)
        except (ValueError, TypeError, KeyError, ArithmeticError) as error:  # one malformed name never takes the exchange down
            name.refusal = "input_error:" + type(error).__name__

    def _not_admitted(self, name: _Name, not_admitted: Mapping[str, str]) -> str:
        """A served name keeps rev3's reason; a listed-only name says which coverage it lacks (the owner reads coverage)."""
        if not name.served:
            if not self.prices.bars(name.symbol):
                return "no_price_history"
            if name.symbol not in self.coverage:
                return "no_asfiled_statements"
        return "not_admitted_at_T:" + not_admitted.get(name.symbol, "unknown")

    @staticmethod
    def _models_of(name: _Name) -> tuple[ModelValue, ...]:
        if name.models:
            return name.models
        reason = name.pending or name.refusal or "company_inputs_unavailable"
        return tuple(ModelValue(model, None, "not_evaluable", reason) for model in MODEL_IDS)

    def _evaluate(self, names: Iterable[_Name]) -> None:
        for name in names:
            name.models = (evaluate_models(name.company, name.premises, peers=self.peers) if name.company is not None else
                           tuple(ModelValue(model, None, "not_evaluable", name.refusal or "company_inputs_unavailable") for model in MODEL_IDS))

    def prepare_served(self) -> None:
        """The served catalogue, exactly as the grid: proxy over its symbols, peers = its evaluable names, its screen."""
        self.prices.build_proxy(self.catalogue_symbols)
        if not self.reader.present():
            raise LiveEnsembleError("statement_vintages_unavailable")
        self.coverage = self.reader.coverage(self.market)
        raw_by_issuer: dict[str, list[dict[str, Any]]] = {}
        served = [self.names[symbol] for symbol in self.catalogue_symbols]
        for name in served:
            self._prepare(name, self.inputs.screen_inputs, self.inputs.not_admitted, self.inputs.statement_references, raw_by_issuer)
        self.peers = tuple(name.company for name in sorted(served, key=lambda item: item.symbol) if name.company is not None)
        basis = self.inputs.volume_basis
        if basis is not None:
            selected, self.screen_refused = screen(self.inputs.screen_inputs, basis=basis)
            self.pit_tested_rule = "screen:" + basis
        else:  # undetermined tonight: tested only if the grid's screen keeps the name under EITHER basis it may have decided
            as_traded, self.screen_refused = screen(self.inputs.screen_inputs, basis="as_traded")
            selected = as_traded & screen(self.inputs.screen_inputs, basis="split_adjusted")[0]
            self.pit_tested_rule = "screen:both_bases"
        for name in served:
            name.pit_tested = name.symbol in selected
            name.screened = (name.symbol in selected) if basis is not None else None
        self._evaluate(served)

    def prepare_extras(self, *, deadline: datetime | None, clock: Callable[[], datetime]) -> bool:
        """The listed-only names, in chunks, valued with the served catalogue's proxy and peers. Returns False when the
        deadline stopped it (the names not reached are ``pending_preparation``)."""
        extras = [self.names[str(row["symbol"])] for row in self.inputs.extra_rows]
        for start in range(0, len(extras), EXTRA_CHUNK):
            chunk = extras[start:start + EXTRA_CHUNK]
            try:
                _check_deadline(deadline, clock)
            except LiveEnsembleDeadline:
                for name in extras[start:]:
                    name.pending = "pending_preparation"
                return False
            try:
                resolver = _PopulationResolver(self.inputs.database, rows=[name.row for name in chunk], market=self.market, as_of=self.cut,
                                               prices=self.prices, statements=STATEMENTS, vintages=self.reader)
                resolver.resolve()
                screen_inputs, not_admitted, references = _admitted(resolver)
                self.prices.build_proxy(self.catalogue_symbols)  # resolve() rebuilt it over the chunk: back to the grid's proxy
                raw_by_issuer: dict[str, list[dict[str, Any]]] = {}
                for name in chunk:
                    self._prepare(name, screen_inputs, not_admitted, references, raw_by_issuer)
                self._evaluate(chunk)
            except LiveEnsembleDeadline:  # the cut came inside the chunk: it and every later one are pending, nothing half-done
                for name in extras[start:]:
                    name.company, name.models, name.refusal, name.pending = None, (), None, "pending_preparation"
                return False
            except Exception as error:  # one chunk's failure refuses that chunk only: never a tested name, never the exchange
                self.chunks_failed += 1
                for name in chunk:
                    name.company, name.models, name.refusal = None, (), "listed_chunk_failed:" + _failure_code(error)
            finally:
                self.prices.build_proxy(self.catalogue_symbols)
                _evict(self.prices, [name.symbol for name in chunk])
        return True

    def skip_extras(self, reason: str) -> None:
        for row in self.inputs.extra_rows:
            name = self.names[str(row["symbol"])]
            if name.company is None and name.refusal is None:
                name.refusal = reason

    # ---- targets
    def awaiting(self, *, pit_tested: bool) -> list[_Name]:
        return [name for name in self.names.values() if name.company is not None and name.pending is None
                and name.targets is None and name.target_error is None and name.pit_tested is pit_tested]

    def read(self, name: _Name, reads: _TargetReads, *, deadline: datetime | None, clock: Callable[[], datetime]) -> None:
        """One name's targets; ``LiveEnsembleDeadline`` propagates (nothing more is read tonight)."""
        if reads.open:
            name.target_error = "targets_circuit_open"
            return
        _check_deadline(deadline, clock)
        reads.attempted += 1
        self.reads["attempted"] += 1
        try:
            rows = list(self.inputs.targets(self.market, name.symbol, pages=None if name.served else EXTRA_TARGET_PAGES))
        except LiveEnsembleDeadline:
            reads.attempted -= 1
            self.reads["attempted"] -= 1
            raise
        except Exception as error:  # the provider's failure: refused, never a TP without the consensus it could not read
            reads.failed += 1
            reads.consecutive += 1
            self.reads["failed"] += 1
            name.target_error = "targets_fetch_failed:" + type(error).__name__
            return
        reads.consecutive = 0
        if not name.served and len(rows) >= EXTRA_TARGET_PAGES * TARGET_PAGE_LIMIT:
            name.target_error = "targets_history_beyond_page_cap"  # never a consensus from a truncated history
            return
        name.targets = rows

    # ---- outcome
    def _finalize(self, name: _Name, context_sha256: str) -> dict[str, Any]:
        primary_value: float | None = None
        sample_size = 0
        targets_sha256: str | None = None
        consensus: dict[str, Any] = {"used": False, "value": None, "analyst_count": 0, "reason": "not_fetched:company_not_evaluable"}
        if name.company is None:
            reason = name.pending or name.refusal or "company_inputs_unavailable"
        elif name.pending is not None or (name.targets is None and name.target_error is None):
            reason = name.pending or "pending_targets"
            consensus["reason"] = "not_fetched:" + reason
        elif name.target_error is not None:
            reason = name.target_error
            consensus["reason"] = reason
        else:
            rows = name.targets or []
            targets_sha256 = canonical_sha256(rows)
            reason = "consensus_not_read"
            try:
                value, receipt = grid_consensus_at(rows, as_of=self.cut, currency="USD", snapshot_id="live:" + targets_sha256, market=self.market)
                consensus = {"used": False, "value": value, "analyst_count": receipt.get("analyst_count"), "reason": receipt.get("reason"),
                             "public_consensus_tp": receipt.get("public_consensus_tp"), "published_at": receipt.get("consensus_published_at")}
                aggregate = aggregate_grid_variants(name.models, value, consensus_reason=receipt.get("reason"))
                variant = _mapping(_mapping(aggregate.get("variants")).get(PRIMARY))
                if aggregate.get("primary") != PRIMARY or not variant:
                    raise NotEvaluable("primary_variant_mismatch")
                primary_value = variant.get("value")
                sample_size = int(variant.get("sample_size") or 0)
                consensus["used"] = bool(variant.get("consensus_included"))
                reason = str(variant.get("reason") or "primary_not_evaluated")
            except NotEvaluable as error:
                reason = "consensus_or_aggregation:" + str(error)
            except (ValueError, TypeError, OverflowError) as error:
                reason = "consensus_or_aggregation:" + type(error).__name__
            if consensus.get("reason") == "not_fetched:company_not_evaluable":  # the consensus reader itself refused the rows
                consensus["reason"] = reason
            elif primary_value is None and consensus.get("reason") is None:  # the consensus was read; the aggregation refused
                consensus["reason"] = "aggregation_refused"
        origin = "ensemble" if primary_value is not None else "not_evaluable:" + reason
        return {
            "symbol": name.symbol, "security_type": name.row.get("security_type"), "in_served_catalogue": name.served,
            "pit_tested": name.pit_tested, "screened": name.screened,
            "primary_tp": primary_value, "origin": origin, "models_evaluated": sum(model.status == "evaluated" for model in self._models_of(name)),
            "sample_size": sample_size, "model_values": {model.model: model.value for model in self._models_of(name)}, "consensus": consensus,
            "price": pit._positive(_mapping(name.screen).get("close")), "session_date": self.prices.session_date, "as_of": self.cut.isoformat(),
            "inputs_sha256": canonical_sha256({"context_sha256": context_sha256, "symbol": name.symbol, "catalogue_row": name.row,
                                               "screen": name.screen, "issuer": name.issuer, "facts_rows_sha256": name.facts_rows_sha256,
                                               "targets_rows_sha256": targets_sha256}),
        }

    def _listed_coverage(self) -> dict[str, int]:
        extras = [self.names[str(row["symbol"])] for row in self.inputs.extra_rows]
        return {"names": len(extras), "no_price_history": sum(name.refusal == "no_price_history" for name in extras),
                "no_asfiled_statements": sum(name.refusal == "no_asfiled_statements" for name in extras),
                "admitted": sum(name.screen is not None for name in extras), "evaluable": sum(name.company is not None for name in extras),
                "chunks_failed": self.chunks_failed}

    def result(self, reads: _TargetReads) -> dict[str, Any]:
        inputs = self.inputs
        context = {"schema": SCHEMA, "source": SOURCE, "market": self.market, "as_of": self.cut.isoformat(), "primary": PRIMARY,
                   "price_vintage": self.prices.manifest(), "session_date": self.prices.session_date, "curve": dict(inputs.curve_reference),
                   "catalogue": dict(inputs.catalogue_reference), "listed": dict(inputs.listed_reference), "statements": STATEMENTS,
                   "volume_basis": inputs.volume_basis, "pit_tested_rule": self.pit_tested_rule,
                   "canonical_fact_rows_sha256": canonical_sha256(dict(sorted(self.issuer_digests.items()))),
                   "peers_sha256": canonical_sha256(sorted(company.symbol for company in self.peers)),
                   "implementation": implementation_files(), "signed_instrument_pin": SIGNED_INSTRUMENT_PIN}
        context_sha256 = canonical_sha256(context)
        records = [self._finalize(self.names[symbol], context_sha256) for symbol in sorted(self.names)]
        totals: dict[str, Counter[str]] = {model: Counter() for model in MODEL_IDS}
        for name in self.names.values():  # every population row in every model's denominator, a refused chunk included
            for model in self._models_of(name):
                totals[model.model]["evaluated" if model.status == "evaluated" else "not_evaluable:" + str(model.reason)] += 1
        origins = Counter(record["origin"] for record in records)
        consensus_counts = Counter("used" if record["consensus"].get("used") else "not_used:" + str(record["consensus"].get("reason") or "unavailable")
                                   for record in records)
        with_tp = [record for record in records if record["primary_tp"] is not None]
        tested = [record for record in records if record["pit_tested"]]
        pending = [name for name in self.names.values() if name.pending is not None
                   or (name.company is not None and name.targets is None and name.target_error is None)]
        counts = {"population_rows": len(records), "catalogue_rows": len(inputs.catalogue),
                  "catalogue_stocks": sum(row.get("security_type") == "Stock" for row in inputs.catalogue),
                  "listed_only_stocks": len(inputs.extra_rows), "admitted_at_T": sum(name.screen is not None for name in self.names.values()),
                  "evaluable_inputs": sum(name.company is not None for name in self.names.values()), "with_primary_tp": len(with_tp),
                  "pit_tested": len(tested), "pit_tested_with_primary_tp": sum(record["primary_tp"] is not None for record in tested),
                  "pit_tested_pending": sum(1 for name in pending if name.pit_tested),
                  "screened": (sum(1 for record in records if record["screened"]) if inputs.volume_basis is not None else None),
                  "screened_with_primary_tp": (sum(1 for record in with_tp if record["screened"]) if inputs.volume_basis is not None else None),
                  "reach": {"reached": len(records) - len(pending), "pending": len(pending)},
                  "origins": dict(sorted(origins.items())), "consensus": dict(sorted(consensus_counts.items())),
                  "model_results": {model: dict(sorted(counter.items())) for model, counter in totals.items()},
                  "screen_refused": dict(sorted(self.screen_refused.items())),
                  "listed_only_coverage": self._listed_coverage(),
                  "targets": {"attempted": int(self.reads["attempted"]), "failed": int(self.reads["failed"]), "circuit_open": reads.open}}
        return {"schema": SCHEMA, "source": SOURCE, "market": self.market, "as_of": self.cut.isoformat(), "session_date": self.prices.session_date,
                "primary": PRIMARY, "volume_basis": inputs.volume_basis, "volume_check": inputs.volume_check, "complete": not pending,
                "context": context, "context_sha256": context_sha256, "records": records, "counts": counts}


def _read_all(sections: Sequence[_LiveSection], reads: _TargetReads, *, pit_tested: bool, deadline: datetime | None,
              clock: Callable[[], datetime]) -> bool:
    """The targets of every awaiting name of ``sections`` (one class: tested or not), most liquid first across the
    exchanges. Returns False when the deadline stopped the reads (the rest stays pending)."""
    queue = sorted(((section, name) for section in sections for name in section.awaiting(pit_tested=pit_tested)),
                   key=lambda item: (-item[1].liquidity(item[0].inputs.volume_basis), item[0].market, item[1].symbol))
    for section, name in queue:
        try:
            section.read(name, reads, deadline=deadline, clock=clock)
        except LiveEnsembleDeadline:
            return False
    return True


def _failure_code(error: Exception) -> str:
    return str(error) if isinstance(error, LiveEnsembleError) else type(error).__name__


def _run_sections(sections: Sequence[_LiveSection], *, deadline: datetime | None, clock: Callable[[], datetime]) -> tuple[_TargetReads, bool]:
    """Tested names of every exchange first, then the listed-only names' inputs, then every other name by liquidity. An
    exchange whose own preparation fails is set aside (``failure``) and the other goes on; an open breaker after the
    tested reads skips the listed-only names (nothing more would be read tonight)."""
    reads = _TargetReads()
    for section in sections:
        section.deadline, section.clock = deadline, clock
    for section in sections:
        _check_deadline(deadline, clock)
        try:
            section.prepare_served()
        except LiveEnsembleDeadline:
            raise
        except Exception as error:  # one exchange's failure never costs the other its night
            section.failure = _failure_code(error)
    healthy = [section for section in sections if section.failure is None]
    complete = _read_all(healthy, reads, pit_tested=True, deadline=deadline, clock=clock)
    if complete and reads.open:
        for section in healthy:
            section.skip_extras("skipped:targets_circuit_open")
    elif complete:
        complete = all([section.prepare_extras(deadline=deadline, clock=clock) for section in healthy])
        if complete:
            complete = _read_all(healthy, reads, pit_tested=False, deadline=deadline, clock=clock)
    if not complete:
        for section in healthy:
            for name in section.names.values():
                if name.company is None and name.refusal is None and name.pending is None and not name.served:
                    name.pending = "pending_preparation"
    return reads, complete


def compute_live_section(inputs: LiveInputs, *, deadline: datetime | None = None, clock: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """One exchange at ``T``: the served catalogue as the grid computes it, then the listed-only names; per name the
    primary TP or ``not_evaluable:<reason>`` (``pending_*`` when the deadline came first), never a guessed number."""
    tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
    section = _LiveSection(inputs)
    reads, _ = _run_sections([section], deadline=deadline, clock=tick)
    if section.failure is not None:
        raise LiveEnsembleError(section.failure)
    return section.result(reads)


def unpublishable(section: Mapping[str, Any]) -> str | None:
    """Why a computed section must NOT be published as tonight's: the provider failed (breaker open, or more than
    ``TARGETS_MAX_FAILED_SHARE`` of the target reads), a tested name was left pending, or not one name has a primary TP.
    A refused section leaves the exchange unpublished, so the phase records a failure and the health card is never green."""
    counts = _mapping(section.get("counts"))
    targets = _mapping(counts.get("targets"))
    attempted, failed = int(targets.get("attempted") or 0), int(targets.get("failed") or 0)
    if targets.get("circuit_open"):
        return "targets_circuit_open"
    if attempted and failed > TARGETS_MAX_FAILED_SHARE * attempted:
        return "targets_failed_share"
    if counts.get("pit_tested_pending"):
        return "tested_names_pending"
    if not counts.get("with_primary_tp"):
        return "no_primary_tp"
    return None


def publish(database: Database, section: Mapping[str, Any], *, published_at: datetime) -> str:
    """ONE ``valuation_ensemble_live/<M>_UNIVERSE`` snapshot; ``published_at`` is the real clock, never before ``T``."""
    at = utc(published_at)
    market = str(section["market"])
    if market not in MARKETS or at < _instant(section["as_of"]):
        raise LiveEnsembleError("publication_not_after_T")
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY, METHODOLOGY_VERSION,
        {"schema": SCHEMA, "primary": PRIMARY, "statements": STATEMENTS, "served": False, "signed_instrument_pin": SIGNED_INSTRUMENT_PIN},
        "Nightly live producer of the valuation ensemble's primary target price: the signed grid's computation on live inputs, every "
        "US common stock; not served until the grid passes and the owner switches; buy permission only for pit_tested names.")
    inputs = {"schema": SCHEMA, "source": SOURCE, "market": market, "as_of": section["as_of"], "context": section["context"],
              "context_sha256": section["context_sha256"]}
    outputs = {**section, "published_at": at.isoformat(),
               "governance": {"served": False, "decision_consumer": "r2d2_live_engine", "official_tp_replacement_authorized": False,
                              "switch_requires": "signed grid PASS and an owner order", "buy_permission_scope": "pit_tested only"}}
    return database.save_analysis_snapshot(ANALYSIS_TYPE, f"{market}_UNIVERSE", methodology_id, inputs, outputs, at)


def last_run_at(database: Database) -> datetime | None:
    """The night is done when BOTH exchanges have a snapshot: the older of the two, ``None`` while one is missing."""
    stamps: list[datetime] = []
    for market in MARKETS:
        stamp = database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, f"{market}_UNIVERSE")
        if stamp is None:
            return None
        stamps.append(stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc))
    return min(stamps)


def _published_since(database: Database, market: str, since: datetime | None) -> bool:
    if since is None:
        return False
    stamp = database.latest_analysis_snapshot_published_at(ANALYSIS_TYPE, f"{market}_UNIVERSE")
    return stamp is not None and utc(stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)) >= utc(since)


def run_nightly(database: Database, settings: Settings, http: JsonHttpClient, *, clock: Callable[[], datetime] | None = None,
                since: datetime | None = None, deadline: datetime | None = None, markets: Sequence[str] = MARKETS) -> dict[str, Any]:
    """The valuation worker's ``ensemble_live`` phase. Off (the default) → nothing is read, fetched or written.

    ``T`` is read once; an exchange already published since ``since`` (the night's due time) is skipped, so a retry only
    completes what is missing. ``deadline`` (wall clock) is checked before every step and every provider request; past it
    nothing more is read — the tested names were read first, so a section whose tested names are complete is still
    published, with the rest ``pending``. A section ``unpublishable`` refuses is not published. Raises ``LiveEnsembleError``
    (counts only) when an exchange is left unpublished or a published one is partial, so the phase is recorded failed —
    never a plain success — and the worker's retry cap applies; the summary and every log line hold counts only."""
    if not valuation_env.ensemble_live_enabled():
        return {"enabled": False}
    tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
    as_of = utc(tick())
    requested = [market for market in MARKETS if market in markets]
    pending: list[str] = []
    for index, market in enumerate(requested):
        try:
            _check_deadline(deadline, tick)  # past the stop nothing is read, not even whether tonight already published it
        except LiveEnsembleDeadline:
            pending.extend(requested[index:])  # unknown, so unpublished: the run is recorded failed, never a plain success
            break
        if not _published_since(database, market, since):
            pending.append(market)
    failures: Counter[str] = Counter()
    summary: dict[str, Any] = {"enabled": True, "as_of": as_of.isoformat(), "markets_pending": len(pending), "published": 0, "partial": 0,
                               "names": 0, "with_primary_tp": 0, "pit_tested_with_primary_tp": 0, "names_pending": 0}
    if pending:
        fetch = LiveSourceFetch(settings, database, http, deadline=deadline, clock=tick)
        try:
            _check_deadline(deadline, tick)
            _run_markets(database, settings, fetch, pending, as_of=as_of, tick=tick, deadline=deadline, failures=failures, summary=summary)
        except LiveEnsembleDeadline:
            failures["deadline_reached"] += 1
        finally:
            summary["provider_reads"] = dict(sorted(fetch.calls.items()))
    summary["failures"] = dict(sorted(failures.items()))
    logger.info("Valuation ensemble live: pending=%d published=%d partial=%d names=%d with_primary_tp=%d names_pending=%d failures=%s",
                len(pending), summary["published"], summary["partial"], summary["names"], summary["with_primary_tp"], summary["names_pending"],
                summary["failures"])
    if summary["published"] != len(pending):
        raise LiveEnsembleError(f"markets_not_published:{len(pending) - summary['published']}")
    if summary["partial"]:
        raise LiveEnsembleError(f"markets_partial:{summary['partial']}:names_pending:{summary['names_pending']}")
    return summary


def _run_markets(database: Database, settings: Settings, fetch: LiveSourceFetch, pending: Sequence[str], *, as_of: datetime,
                 tick: Callable[[], datetime], deadline: datetime | None, failures: Counter[str], summary: dict[str, Any]) -> None:
    """The pending exchanges of one night, counted into ``summary``; a ``LiveEnsembleDeadline`` before the sections exist
    propagates (nothing to publish)."""
    try:
        curve, curve_reference = live_treasury_curve(fetch, as_of=as_of)
    except LiveEnsembleDeadline:
        raise
    except Exception as error:  # no rate is guessed: no exchange tonight
        failures["treasury_curve:" + type(error).__name__] += len(pending)
        return
    # the volume basis is voted over BOTH exchanges' publications, as the grid votes — also on a retry of one exchange
    reads = _readers_database(database, deadline, tick)  # every series/snapshot read below checks the deadline before it starts
    series = PriceHistoryService(settings, reads, _NoNetworkHttp())
    prices: dict[str, pit.PinnedPrices] = {}
    for market in MARKETS:
        try:
            prices[market] = pit.PinnedPrices(series, market, as_of=as_of, pinned_at=as_of, pin_mode="run_start")
        except LiveEnsembleDeadline:
            raise
        except Exception as error:
            if market in pending:
                failures["price_vintage:" + type(error).__name__] += 1
    volume_basis: str | None = None
    volume_check: dict[str, Any] = {"decision": "not_every_exchange_pinned"}
    if set(prices) == set(MARKETS):
        _check_deadline(deadline, tick)
        try:
            volume_basis, volume_check = decide_volume_basis(reads, settings, prices)
        except LiveEnsembleDeadline:
            raise
        except Exception as error:  # the screen flag only: TPs never depend on it
            failures["volume_check:" + type(error).__name__] += 1
            volume_check = {"decision": "volume_check_failed"}
    sections: list[_LiveSection] = []
    for market in pending:
        pinned = prices.get(market)
        if pinned is None:
            continue
        _check_deadline(deadline, tick)
        try:
            sections.append(_LiveSection(gather_live_inputs(database, market=market, as_of=as_of, prices=pinned, curve=curve,
                                                            curve_reference=curve_reference, targets=fetch.target_rows,
                                                            volume_basis=volume_basis, volume_check=volume_check,
                                                            deadline=deadline, clock=tick, catalogue_cut=as_of)))
        except LiveEnsembleDeadline:
            raise
        except LiveEnsembleError as error:
            failures["section:" + str(error)] += 1
        except Exception as error:
            failures["section:" + type(error).__name__] += 1
    if not sections:
        return
    try:
        reads, complete = _run_sections(sections, deadline=deadline, clock=tick)
    except LiveEnsembleDeadline:  # the deadline came while the served catalogues were being prepared: no section is ready
        raise
    if not complete:
        failures["deadline_reached"] += 1
    for section in sections:
        if section.failure is not None:
            failures["section:" + section.failure] += 1
            continue
        try:
            _check_deadline(deadline + PUBLISH_GRACE if deadline is not None else None, tick)
        except LiveEnsembleDeadline:
            failures["deadline_reached_before_publish"] += 1
            continue
        try:
            result = section.result(reads)
            refusal = unpublishable(result)
            if refusal is not None:
                raise LiveEnsembleError(refusal)
            publish(database, result, published_at=tick())
        except LiveEnsembleError as error:
            failures["section:" + str(error)] += 1
            continue
        except Exception as error:
            failures["section:" + type(error).__name__] += 1
            continue
        counts = result["counts"]
        summary["published"] += 1
        summary["partial"] += int(not result["complete"])
        summary["names"] += int(counts["population_rows"])
        summary["with_primary_tp"] += int(counts["with_primary_tp"])
        summary["pit_tested_with_primary_tp"] += int(counts["pit_tested_with_primary_tp"])
        summary["names_pending"] += int(counts["reach"]["pending"])
