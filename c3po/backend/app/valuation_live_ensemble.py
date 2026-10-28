"""Valuation ensemble — the nightly LIVE producer of the signed grid's PRIMARY target price (US tested population).

Once the pinned point-in-time grid (``valuation_ensemble_grid.compute_grid_section``, instrument pin ``b77f2400…``)
reports PASS, the served target price may switch to the ensemble's primary variant
(``minmax_trimmed_mean_with_consensus``). This module computes THAT number every night for NASDAQ and NYSE from LIVE
inputs at the run's clock ``T`` instead of the grid's stored snapshots — through the grid's own pinned functions, imported
and called unchanged: the rev3 admission and screen inputs (``valuation_pit_rerun.PitSourceResolver`` /
``PitComputation.screen_inputs``), the as-filed reader and payload, the pinned price publication (close of D, ≥ 90 valid
sessions, capital events, OLS beta on the equal-weight proxy), ``curve_package_at``, ``reduce_company_facts``,
``valuation_ensemble_grid._shares``, ``GridCompanyInputs``, ``derive_premises``, ``evaluate_models`` (peers = every
evaluable name of the exchange: a batch, never on demand), ``grid_consensus_at`` (latest eligible target per house in
``(T − 90 d, T]``, ≥ 3 houses, house mean) and ``aggregate_grid_variants``. Only the per-name loop of
``compute_grid_section`` (inline there, not a function) is restated in ``compute_live_section``; the parity test pins it to
the grid's floats on the grid's own fixture.

Live inputs per name (``gather_live_inputs`` / ``run_nightly``):

* catalogue row (symbol, security type, sector, valuation profile): the latest ``valuation_universe/<M>_UNIVERSE``
  (≤ 300 stocks + 25 ETFs, ``us_screener``), read once by id and checked against the resolver's classification hash;
* close of D, valid sessions, capital events, beta: ``PinnedPrices`` on the latest ``valuation_price_history``
  publication available at ``T`` (no network);
* SEC as-filed facts accepted ≤ ``T``: ``AsFiledReader`` on ``statement_vintages`` (migration 051), ``--statements
  vintages`` semantics (an uncovered name is not evaluable);
* Treasury 3Y/10Y: ``PitFetchService.fetch_macro`` (EODHD GBOND, 15 years) kept IN MEMORY, then ``curve_package_at``;
* analyst targets: ``PitFetchService.fetch_targets`` (FMP ``price-target-news``, the same pages) kept IN MEMORY, read only
  for names whose company inputs are evaluable (any other name's primary is unevaluable whatever its consensus: one value
  is below the three the aggregation needs);
* screen: ``valuation_pit_backtest_report.screen`` on the volume basis ``valuation_pit_grid.volume_check`` decides over
  the pinned publications (``None`` when undetermined: TPs unaffected, ``screened`` unknown).

Where live cannot equal the grid's PIT inputs: the catalogue is today's, not the grid's pinned one; the price publication
is tonight's (its history can be re-adjusted by the provider since the grid's 120-month vintage); the Treasury history
and the target history are fetched now (a target or close the provider revised, deleted or backfilled differs, and the
grid's own snapshot was fetched once, before its run); the resolver's outstandingShares fallback (screen market cap only)
reads the latest ``valuation_pit_source`` EODHD snapshot exactly as rev3 does, which is stale; ``T`` is the run's clock,
not the grid's 01:00 America/Sao_Paulo convention. The fetches persist NOTHING to ``valuation_pit_source``: the signed
grid's pinned sources stay untouched.

Fail closed: a market whose price pin, catalogue, statements table or Treasury curve cannot be read writes no snapshot;
a name it cannot evaluate gets ``origin = not_evaluable:<reason>`` and no number — a target fetch that fails is a refusal,
never a TP without the consensus it could not read. One ``valuation_ensemble_live/<M>_UNIVERSE`` snapshot per market and
night. Nothing here is served or selected (``valuation_official.market_of_entity`` ignores this analysis type); off by
default (``valuation_env.ensemble_live_enabled``). Logs carry counts and error classes only, never a symbol.
"""
from __future__ import annotations

import hashlib
import logging
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from . import valuation_env, valuation_pit_rerun as pit
from .config import Settings
from .database import Database
from .market_data.http import JsonHttpClient
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
SCHEMA = "VALUATION-ENSEMBLE-LIVE-v1"
SOURCE = "ensemble_live"
METHODOLOGY_KEY = "valuation_ensemble_live"
METHODOLOGY_VERSION = 1
MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")
PRIMARY = GRID_PRIMARY_VARIANT  # = valuation_ensemble_pin.PROTOCOL_CONSTANTS["primary"] (pinned by test)
STATEMENTS = "vintages"  # the grid's statements mode: as-filed SEC facts only
CLASSIFICATION = "current_pinned_catalogue_rev3_convention"  # the only label GridCompanyInputs.sector_at_T admits (peer sectors)
SIGNED_INSTRUMENT_PIN = "b77f2400ef5bac57bd266f3e2edb26a9d63356b5c3fc65d47da490c8c8be6f86"
IMPLEMENTATION_FILES: tuple[str, ...] = (  # every module whose bytes can move a published number, hashed into the context
    "valuation_live_ensemble.py", "valuation_ensemble_grid.py", "valuation_ensemble_grid_inputs.py", "valuation_ensemble_grid_consensus.py",
    "valuation_ensemble_aggregation.py", "valuation_ensemble_models.py", "valuation_ensemble_inputs.py", "valuation_ensemble_adapters.py",
    "valuation_pit_rerun.py", "valuation_pit_backtest_report.py", "valuation_price_history.py", "valuation_v2_engine.py",
    "valuation_v3_macro.py", "sec_xbrl.py", "statement_vintages.py", "valuation_asfiled.py",
)

TargetReader = Callable[[str, str], Sequence[Mapping[str, Any]]]


class LiveEnsembleError(RuntimeError):
    """A market-level refusal: no snapshot is written for that market. The text is a stable code, never a symbol."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def implementation_files() -> dict[str, str]:
    app = Path(__file__).parent
    return {name: hashlib.sha256((app / name).read_bytes()).hexdigest() for name in IMPLEMENTATION_FILES}


class LiveSourceFetch(pit.PitFetchService):
    """The PIT fetcher's own provider reads (``fetch_targets``, ``fetch_macro``: endpoints, pagination, units) with the
    payload kept in memory: ``_persist`` never writes ``valuation_pit_source``, whose snapshots the signed grid pins."""

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        super().__init__(settings, database, http)
        self.captured: dict[str, Any] = {}
        self.calls: Counter[str] = Counter()

    def _persist(self, entity_key: str, *, provider: str, endpoint: str, market: str, symbol: str | None, payload: Any,
                 fetched_at: datetime) -> str:
        self.captured[entity_key] = payload
        self.calls[provider] += 1
        return "live:" + canonical_sha256(payload)

    def target_rows(self, market: str, symbol: str) -> list[dict[str, Any]]:
        """The RAW per-house target history of one name, as the grid's snapshot holds it (a list, else a refusal)."""
        self.fetch_targets(market, symbol)
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


@dataclass(frozen=True)
class LiveInputs:
    """Everything one (exchange, T) section reads, resolved before any model runs. ``targets(market, symbol)`` returns the
    RAW target rows or raises (a provider failure); the parity test passes the grid's pinned rows instead."""
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


def gather_live_inputs(database: Database, *, market: str, as_of: datetime, prices: pit.PinnedPrices, curve: Mapping[str, Any],
                       curve_reference: Mapping[str, Any], targets: TargetReader, volume_basis: str | None,
                       volume_check: Mapping[str, Any] | None = None, reader: pit.AsFiledReader | None = None) -> LiveInputs:
    """rev3's admission at ``T``, unchanged: ``PitSourceResolver`` (``vintages``, the latest catalogue) decides which names
    have statements, ≥ 90 valid sessions, a close and shares at ``T``, and ``PitComputation.screen_inputs`` (which reads
    only ``self.resolver``) gives the screen inputs the grid's sibling run stored. Market-level defects raise."""
    cut = utc(as_of)
    if market not in MARKETS:
        raise LiveEnsembleError("unsupported_market")
    if prices.market != market or utc(prices.as_of) != cut:
        raise LiveEnsembleError("price_pin_not_of_this_section")
    if not isinstance(curve, Mapping) or pit._number(curve.get("interpolated_5y_rate")) is None:
        raise LiveEnsembleError("treasury_curve_unavailable")
    if volume_basis is not None and volume_basis not in VOLUME_BASES:
        raise LiveEnsembleError("unknown_volume_basis")
    reader = reader if reader is not None else pit.AsFiledReader(database)
    resolver = pit.PitSourceResolver(database, market=market, as_of=cut, prices=prices, statements=STATEMENTS, vintages=reader)
    resolver.resolve()
    if resolver.catalogue_snapshot_id is None:
        raise LiveEnsembleError("catalogue_missing")
    catalogue = pit.admitted_catalogue(database.analysis_snapshot_by_id(resolver.catalogue_snapshot_id))
    references = [dict(item) for item in resolver.references]
    roles = [item for item in references if item.get("role") == "catalogue"]
    if not catalogue or len(roles) != 1 or roles[0].get("classification_sha256") != canonical_hash(catalogue):
        raise LiveEnsembleError("catalogue_changed_during_run")
    screen_inputs = pit.PitComputation.screen_inputs(cast(pit.PitComputation, SimpleNamespace(resolver=resolver)))
    catalogue_reference = {"snapshot_id": resolver.catalogue_snapshot_id, "classification_sha256": roles[0]["classification_sha256"],
                           "rows": len(catalogue), "stocks": sum(row.get("security_type") == "Stock" for row in catalogue)}
    return LiveInputs(market, cut, prices, reader, catalogue, catalogue_reference, screen_inputs, dict(resolver.not_evaluable),
                      [item for item in references if item.get("role") == pit.BASIS_VINTAGES], dict(curve), dict(curve_reference),
                      targets, volume_basis, dict(volume_check) if volume_check is not None else None)


def _statement_reference(references: Sequence[Mapping[str, Any]], symbol: str) -> Mapping[str, Any] | None:
    key = pit.symbol_hash(symbol)
    found = [item for item in references if item.get("symbol_sha256") == key]
    return found[0] if len(found) == 1 else None


def compute_live_section(inputs: LiveInputs) -> dict[str, Any]:
    """The grid's per-name computation for ONE exchange at ``T`` (``compute_grid_section``'s loop, the same calls in the
    same order), on live inputs. Per name: the primary TP or ``not_evaluable:<reason>``; never a guessed number."""
    market, cut, prices, reader = inputs.market, utc(inputs.as_of), inputs.prices, inputs.reader
    catalogue, screen_inputs, curve = inputs.catalogue, inputs.screen_inputs, inputs.curve
    symbols = [str(row["symbol"]) for row in catalogue]
    if len(symbols) != len(set(symbols)):
        raise LiveEnsembleError("duplicate_catalogue_symbol")
    prices.build_proxy(symbols)
    selected: set[str] | None = None
    screen_refused: Counter[str] = Counter()
    if inputs.volume_basis is not None:
        selected, screen_refused = screen(screen_inputs, basis=inputs.volume_basis)
    if not reader.present():
        raise LiveEnsembleError("statement_vintages_unavailable")
    coverage = reader.coverage(market)
    economic = pit.economic_date_of(market, cut)
    raw_by_issuer: dict[str, list[dict[str, Any]]] = {}
    companies: dict[str, GridCompanyInputs] = {}
    premises_by_symbol: dict[str, Any] = {}
    refusals: dict[str, str] = {}
    ledger: dict[str, dict[str, Any]] = {}
    for row in catalogue:
        symbol = str(row["symbol"])
        item: dict[str, Any] = {"issuer": None, "facts_rows_sha256": None}
        ledger[symbol] = item
        try:
            if row.get("security_type") != "Stock":
                raise NotEvaluable("not_a_stock")
            if symbol not in screen_inputs:
                raise NotEvaluable("not_admitted_at_T:" + inputs.not_admitted.get(symbol, "unknown"))
            issuer = coverage.get(symbol)
            if not issuer:
                raise NotEvaluable("statement_vintages_missing")
            if issuer not in raw_by_issuer:
                refused: Counter[str] = Counter()
                raw_by_issuer[issuer] = reader.facts(issuer, as_of=cut, refused=refused)
            raw = raw_by_issuer[issuer]
            item["issuer"] = issuer
            payload, reference = pit.as_filed_payload(raw, market=market, front=reader.front)
            expected = _statement_reference(inputs.statement_references, symbol)
            if expected is None or any(expected.get(key) != reference.get(key) for key in reference):
                raise NotEvaluable("statements_changed_during_run")  # a fact accepted by T landed between the two reads
            facts, facts_audit = reduce_company_facts(raw, issuer=issuer, as_of=cut, front=reader.front)
            item["facts_rows_sha256"] = facts_audit.get("accepted_rows_sha256")
            fundamentals = pit.pit_fundamentals(payload, market=market, economic_date=economic)
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
            premises, _ = derive_premises(company, curve=curve, beta=beta, beta_audit=beta_audit, facts_audit=facts_audit)
            companies[symbol] = company
            premises_by_symbol[symbol] = premises
        except NotEvaluable as error:
            refusals[symbol] = str(error)
        except (ValueError, TypeError, KeyError, ArithmeticError) as error:  # one malformed name never takes the exchange down
            refusals[symbol] = "input_error:" + type(error).__name__
    peers = tuple(companies[key] for key in sorted(companies))
    context = {"schema": SCHEMA, "source": SOURCE, "market": market, "as_of": cut.isoformat(), "primary": PRIMARY,
               "price_vintage": prices.manifest(), "session_date": prices.session_date, "curve": dict(inputs.curve_reference),
               "catalogue": dict(inputs.catalogue_reference), "statements": STATEMENTS, "volume_basis": inputs.volume_basis,
               "canonical_fact_rows_sha256": canonical_sha256({issuer: sorted(str(r["row_hash"]) for r in rows)
                                                              for issuer, rows in sorted(raw_by_issuer.items())}),
               "evaluable_names_sha256": canonical_sha256(sorted(companies)), "implementation": implementation_files(),
               "signed_instrument_pin": SIGNED_INSTRUMENT_PIN}
    context_sha256 = canonical_sha256(context)
    records: list[dict[str, Any]] = []
    totals: dict[str, Counter[str]] = {model: Counter() for model in MODEL_IDS}
    origins: Counter[str] = Counter()
    consensus_counts: Counter[str] = Counter()
    for row in catalogue:
        symbol = str(row["symbol"])
        company = companies.get(symbol)
        models = (evaluate_models(company, premises_by_symbol[symbol], peers=peers) if company is not None else
                  tuple(ModelValue(model, None, "not_evaluable", refusals.get(symbol, "company_inputs_unavailable")) for model in MODEL_IDS))
        for model in models:
            totals[model.model]["evaluated" if model.status == "evaluated" else "not_evaluable:" + str(model.reason)] += 1
        reason: str | None = refusals.get(symbol, "company_inputs_unavailable") if company is None else None
        primary_value: float | None = None
        sample_size = 0
        consensus: dict[str, Any] = {"used": False, "value": None, "analyst_count": 0, "reason": "not_fetched:company_not_evaluable"}
        targets_sha256: str | None = None
        if company is not None:
            try:
                rows = list(inputs.targets(market, symbol))
            except Exception as error:  # the provider's failure: refused, never a TP without the consensus it could not read
                reason = "targets_fetch_failed:" + type(error).__name__
                consensus = {**consensus, "reason": reason}
            else:
                targets_sha256 = canonical_sha256(rows)
                try:
                    value, receipt = grid_consensus_at(rows, as_of=cut, currency="USD", snapshot_id="live:" + targets_sha256, market=market)
                    aggregate = aggregate_grid_variants(models, value, consensus_reason=receipt.get("reason"))
                    variant = _mapping(_mapping(aggregate.get("variants")).get(PRIMARY))
                    if aggregate.get("primary") != PRIMARY or not variant:
                        raise NotEvaluable("primary_variant_mismatch")
                    primary_value = variant.get("value")
                    sample_size = int(variant.get("sample_size") or 0)
                    consensus = {"used": bool(variant.get("consensus_included")), "value": value, "analyst_count": receipt.get("analyst_count"),
                                 "reason": receipt.get("reason"), "public_consensus_tp": receipt.get("public_consensus_tp"),
                                 "published_at": receipt.get("consensus_published_at")}
                    if primary_value is None:
                        reason = str(variant.get("reason") or "primary_not_evaluated")
                except NotEvaluable as error:
                    reason = "consensus_or_aggregation:" + str(error)
                except (ValueError, TypeError, OverflowError) as error:
                    reason = "consensus_or_aggregation:" + type(error).__name__
        if primary_value is not None:
            reason = None
        origin = "ensemble" if primary_value is not None else "not_evaluable:" + str(reason or "unknown")
        origins[origin] += 1
        consensus_counts["used" if consensus.get("used") else "not_used:" + str(consensus.get("reason") or "unavailable")] += 1
        audit = ledger[symbol]
        records.append({
            "symbol": symbol, "security_type": row.get("security_type"),
            "screened": (symbol in selected) if selected is not None else None,
            "primary_tp": primary_value, "origin": origin, "models_evaluated": sum(model.status == "evaluated" for model in models),
            "sample_size": sample_size, "model_values": {model.model: model.value for model in models}, "consensus": consensus,
            "price": pit._positive(_mapping(screen_inputs.get(symbol)).get("close")), "session_date": prices.session_date, "as_of": cut.isoformat(),
            "inputs_sha256": canonical_sha256({"context_sha256": context_sha256, "symbol": symbol, "catalogue_row": dict(row),
                                               "screen": screen_inputs.get(symbol), "issuer": audit["issuer"],
                                               "facts_rows_sha256": audit["facts_rows_sha256"], "targets_rows_sha256": targets_sha256}),
        })
    with_tp = [record for record in records if record["primary_tp"] is not None]
    counts = {"catalogue_rows": len(catalogue), "catalogue_stocks": sum(row.get("security_type") == "Stock" for row in catalogue),
              "admitted_at_T": len(screen_inputs), "evaluable_inputs": len(companies), "with_primary_tp": len(with_tp),
              "screened": len(selected) if selected is not None else None,
              "screened_with_primary_tp": sum(1 for record in with_tp if record["screened"]) if selected is not None else None,
              "origins": dict(sorted(origins.items())), "consensus": dict(sorted(consensus_counts.items())),
              "model_results": {model: dict(sorted(counter.items())) for model, counter in totals.items()},
              "screen_refused": dict(sorted(screen_refused.items()))}
    return {"schema": SCHEMA, "source": SOURCE, "market": market, "as_of": cut.isoformat(), "session_date": prices.session_date,
            "primary": PRIMARY, "volume_basis": inputs.volume_basis, "volume_check": inputs.volume_check,
            "context": context, "context_sha256": context_sha256, "records": records, "counts": counts}


def publish(database: Database, section: Mapping[str, Any], *, published_at: datetime) -> str:
    """ONE ``valuation_ensemble_live/<M>_UNIVERSE`` snapshot; ``published_at`` is the real clock, never before ``T``."""
    at = utc(published_at)
    market = str(section["market"])
    if market not in MARKETS or at < _instant(section["as_of"]):
        raise LiveEnsembleError("publication_not_after_T")
    methodology_id = database.ensure_methodology_version(
        METHODOLOGY_KEY, METHODOLOGY_VERSION,
        {"schema": SCHEMA, "primary": PRIMARY, "statements": STATEMENTS, "served": False, "signed_instrument_pin": SIGNED_INSTRUMENT_PIN},
        "Nightly live producer of the valuation ensemble's primary target price: the signed grid's computation on live inputs; "
        "not served until the grid passes and the owner switches.")
    inputs = {"schema": SCHEMA, "source": SOURCE, "market": market, "as_of": section["as_of"], "context": section["context"],
              "context_sha256": section["context_sha256"]}
    outputs = {**section, "published_at": at.isoformat(),
               "governance": {"served": False, "decision_consumer": False, "official_tp_replacement_authorized": False,
                              "switch_requires": "signed grid PASS and an owner order"}}
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
                since: datetime | None = None, markets: Sequence[str] = MARKETS) -> dict[str, Any]:
    """The valuation worker's ``ensemble_live`` phase. Off (the default) → nothing is read, fetched or written.

    ``T`` is read once; each exchange is isolated (its failure is counted by error class and the other still publishes);
    an exchange already published since ``since`` (the night's due time) is skipped, so a retry inside the window only
    completes what is missing. Raises ``LiveEnsembleError`` (a count) when an exchange is left unpublished, so the phase
    is recorded failed and retried; the returned summary and every log line hold counts only."""
    if not valuation_env.ensemble_live_enabled():
        return {"enabled": False}
    tick: Callable[[], datetime] = clock or (lambda: datetime.now(timezone.utc))
    as_of = utc(tick())
    pending = [market for market in MARKETS if market in markets and not _published_since(database, market, since)]
    failures: Counter[str] = Counter()
    summary: dict[str, Any] = {"enabled": True, "as_of": as_of.isoformat(), "markets_pending": len(pending), "published": 0,
                               "names": 0, "with_primary_tp": 0, "screened_with_primary_tp": 0}
    if pending:
        fetch = LiveSourceFetch(settings, database, http)
        curve: dict[str, Any] | None = None
        curve_reference: dict[str, Any] = {}
        try:
            curve, curve_reference = live_treasury_curve(fetch, as_of=as_of)
        except Exception as error:
            failures["treasury_curve:" + type(error).__name__] += 1
        prices: dict[str, pit.PinnedPrices] = {}
        if curve is not None:
            series = PriceHistoryService(settings, database, _NoNetworkHttp())
            for market in pending:
                try:
                    prices[market] = pit.PinnedPrices(series, market, as_of=as_of, pinned_at=as_of, pin_mode="run_start")
                except Exception as error:
                    failures["price_vintage:" + type(error).__name__] += 1
        volume_basis: str | None = None
        volume_check: dict[str, Any] | None = None
        if prices:
            try:
                volume_basis, volume_check = decide_volume_basis(database, settings, prices)
            except Exception as error:  # the screen flag only: TPs never depend on it
                failures["volume_check:" + type(error).__name__] += 1
        for market, pinned in prices.items():
            try:
                inputs = gather_live_inputs(database, market=market, as_of=as_of, prices=pinned, curve=cast(dict[str, Any], curve),
                                            curve_reference=curve_reference, targets=fetch.target_rows, volume_basis=volume_basis,
                                            volume_check=volume_check)
                section = compute_live_section(inputs)
                publish(database, section, published_at=tick())
            except Exception as error:
                failures["section:" + type(error).__name__] += 1
                continue
            counts = section["counts"]
            summary["published"] += 1
            summary["names"] += int(counts["catalogue_rows"])
            summary["with_primary_tp"] += int(counts["with_primary_tp"])
            summary["screened_with_primary_tp"] += int(counts["screened_with_primary_tp"] or 0)
        summary["provider_reads"] = dict(sorted(fetch.calls.items()))
    summary["failures"] = dict(sorted(failures.items()))
    logger.info("Valuation ensemble live: pending=%d published=%d names=%d with_primary_tp=%d failures=%s", len(pending), summary["published"],
                summary["names"], summary["with_primary_tp"], summary["failures"])
    if summary["published"] != len(pending):
        raise LiveEnsembleError(f"markets_not_published:{len(pending) - summary['published']}")
    return summary
