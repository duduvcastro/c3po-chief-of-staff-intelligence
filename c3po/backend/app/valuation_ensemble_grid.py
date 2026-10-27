"""One label-free ensemble section at T, from the rev3 sibling runs' pinned inputs.

No service/client/store is constructed by import or default. The caller provides
the canonical database reader, pinned prices and both immutable sibling snapshots.
The executor's instrument/owner-order gates live outside this pure computation.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Callable, Mapping, Sequence, TypeVar

from . import sec_xbrl, valuation_pit_rerun as pit, valuation_pit_served as served
from .valuation_ensemble_aggregation import aggregate_grid_variants
from .valuation_ensemble_grid_consensus import grid_consensus_at
from .valuation_ensemble_grid_inputs import GridCompanyInputs, _date, _fact, _instant, derive_premises, reduce_company_facts
from .valuation_ensemble_inputs import Evidence, NotEvaluable, Price, canonical_hash, utc
from .valuation_ensemble_models import MODEL_IDS, ModelValue, evaluate_models
from .valuation_pit_backtest_report import screen
from .valuation_v3_macro import canonical_payload_sha256


SOURCE = "ensemble_pit"
SCHEMA = "VALUATION-ENSEMBLE-GRID-SECTION-v1"
DESIGN_SEED = 20261026
_T = TypeVar("_T")


class GridInputError(ValueError):
    """A sibling/pin identity defect: no section is computed from mixed inputs."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _snapshot_manifest(snapshot: Mapping[str, Any], *, analysis: str, market: str, as_of: datetime) -> dict[str, Any]:
    inputs, outputs = _mapping(snapshot.get("inputs")), _mapping(snapshot.get("outputs"))
    manifest = _mapping(inputs.get("manifest"))
    if (snapshot.get("analysis_type") != analysis or not snapshot.get("id") or inputs.get("market") != market
            or _instant(inputs.get("as_of")) != as_of or manifest.get("market") != market
            or _instant(manifest.get("as_of")) != as_of or outputs.get("market") != market
            or _instant(outputs.get("as_of")) != as_of):
        raise GridInputError("rev3_sibling_identity_or_T_mismatch")
    if not inputs.get("run_key") or outputs.get("run_key") != inputs["run_key"]:
        raise GridInputError("rev3_sibling_run_key_mismatch")
    if manifest.get("manifest_sha256") != canonical_hash({k: v for k, v in manifest.items() if k != "manifest_sha256"}):
        raise GridInputError("rev3_sibling_manifest_hash_mismatch")
    mode = _mapping(_mapping(outputs.get("summary")).get("statements")).get("mode")
    if mode != "vintages":
        raise GridInputError("ensemble_grid_requires_rev3_as_filed_vintages")
    return manifest


def _guarded(reader: Callable[[], _T], before_read: Callable[[], None] | None) -> _T:
    if before_read is not None:
        before_read()
    result = reader()
    if before_read is not None:
        before_read()
    return result


def _read_snapshot(database: Any, snapshot_id: str, *, analysis: str, entity: str | None = None,
                   before_read: Callable[[], None] | None = None) -> dict[str, Any]:
    snapshot = _guarded(lambda: database.analysis_snapshot_by_id(snapshot_id), before_read)
    if not isinstance(snapshot, Mapping) or str(snapshot.get("id")) != snapshot_id or snapshot.get("analysis_type") != analysis:
        raise GridInputError("pinned_snapshot_missing_or_identity_mismatch")
    if entity is not None and snapshot.get("entity_key") != entity:
        raise GridInputError("pinned_snapshot_entity_mismatch")
    return dict(snapshot)


def _role(manifest: Mapping[str, Any], role: str, *, symbol: str | None = None) -> dict[str, Any] | None:
    refs = [dict(x) for x in manifest.get("sources", []) if isinstance(x, Mapping) and x.get("role") == role
            and (symbol is None or x.get("symbol_sha256") == pit.symbol_hash(symbol))]
    if len(refs) > 1:
        raise GridInputError("ambiguous_rev3_source_reference")
    return refs[0] if refs else None


def _served_targets(snapshot: Mapping[str, Any], *, market: str, as_of: datetime) -> dict[str, float]:
    records = _mapping(snapshot.get("outputs")).get("records")
    if not isinstance(records, list):
        raise GridInputError("served_sibling_snapshot_records_missing")
    targets: dict[str, float] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise GridInputError("served_sibling_record_malformed")
        core = {k: v for k, v in record.items() if k not in ("id", "row_sha256")}
        provenance = _mapping(_mapping(record.get("decomposition")).get("provenance"))
        if (record.get("row_sha256") != canonical_hash(core) or record.get("source") != served.SOURCE
                or record.get("market") != market or str(record.get("cycle_id")) != str(snapshot["id"])
                or _instant(record.get("prediction_instant")) != as_of
                or provenance.get("run_key") != _mapping(snapshot.get("inputs")).get("run_key")):
            raise GridInputError("served_sibling_record_integrity_mismatch")
        symbol, value = str(record.get("symbol") or ""), pit._positive(record.get("tp"))
        if not symbol or value is None or symbol in targets:
            raise GridInputError("served_sibling_target_or_identity_invalid")
        targets[symbol] = value
    return targets


def paired_source_identity(v3_snapshot: Mapping[str, Any], served_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Identity read from the actual siblings, not a caller's self-hashed pin bag.

    The reporter can rebuild this before requesting any labels. Source references
    are actual snapshot IDs/hashes/clocks; the current catalogue remains labelled
    as the rev3 convention, not historical sector or original authentication.
    """
    inputs = _mapping(v3_snapshot.get("inputs"))
    market, cut = str(inputs.get("market")), _instant(inputs.get("as_of"))
    v3 = _snapshot_manifest(v3_snapshot, analysis=pit.ANALYSIS_TYPE, market=market, as_of=cut)
    other = _snapshot_manifest(served_snapshot, analysis=served.ANALYSIS_TYPE, market=market, as_of=cut)
    v3_outputs, served_outputs = (_mapping(s.get("outputs")) for s in (v3_snapshot, served_snapshot))
    for name in ("price_vintage", "price_basis", "macro", "session_date"):
        if v3.get(name) != other.get(name):
            raise GridInputError("rev3_sibling_source_mismatch:" + name)
    if v3_outputs.get("screen") != served_outputs.get("screen"):
        raise GridInputError("rev3_siblings_screen_mismatch")
    if v3_outputs.get("catalogue_counts") != served_outputs.get("catalogue_counts"):
        raise GridInputError("rev3_siblings_catalogue_counts_mismatch")
    cat = _mapping(inputs.get("catalogue_pin"))
    if not cat.get("resolved_snapshot_id") or cat != _mapping(_mapping(served_snapshot.get("inputs")).get("catalogue_pin")):
        raise GridInputError("rev3_catalogue_pin_missing_or_mismatched")
    if _role(v3, "catalogue") != _role(other, "catalogue") or _role(v3, "catalogue") is None:
        raise GridInputError("rev3_catalogue_reference_mismatch")

    def refs(manifest: Mapping[str, Any], roles: set[str]) -> list[dict[str, Any]]:
        result = [dict(x) for x in manifest.get("sources", []) if isinstance(x, Mapping) and x.get("role") in roles]
        keys = [(str(x.get("role")), str(x.get("market")), str(x.get("symbol_sha256"))) for x in result]
        if len(keys) != len(set(keys)):
            raise GridInputError("duplicate_rev3_source_reference")
        return sorted(result, key=canonical_hash)

    official = refs(v3, {pit.BASIS_VINTAGES, pit.PROVIDER_EODHD})
    if official != refs(other, {pit.BASIS_VINTAGES, pit.PROVIDER_EODHD}):
        raise GridInputError("rev3_siblings_statement_references_mismatch")
    targets = _served_targets(served_snapshot, market=market, as_of=cut)
    resident = served_outputs.get("records") or []
    identities = sorted([[str(r["symbol"]), str(r["row_sha256"])] for r in resident])
    if identities != sorted(served_outputs.get("prediction_identities") or []):
        raise GridInputError("served_sibling_prediction_set_mismatch")
    return {"v3_cycle_id": str(v3_snapshot["id"]), "v3_run_key": inputs["run_key"],
            "served_cycle_id": str(served_snapshot["id"]), "served_run_key": _mapping(served_snapshot["inputs"])["run_key"],
            "v3_manifest_sha256": v3["manifest_sha256"], "served_manifest_sha256": other["manifest_sha256"],
            "price_vintage": v3["price_vintage"], "price_basis": v3.get("price_basis"),
            "catalogue_pin": cat, "catalogue_classification": _role(v3, "catalogue"),
            "catalogue_counts": _mapping(v3_outputs.get("catalogue_counts")),
            "statement_source_references": official, "target_source_references": refs(v3, {pit.PROVIDER_FMP}),
            "macro": v3["macro"], "statements": "vintages", "screen_sha256": canonical_hash(v3_outputs["screen"]),
            "served_records_sha256": canonical_hash(identities), "served_targets_sha256": canonical_hash(targets)}


def validate_record_pair(records: Sequence[Mapping[str, Any]], v3_snapshot: Mapping[str, Any],
                         served_snapshot: Mapping[str, Any], *, volume_basis: str = "as_traded") -> list[str]:
    """Cross-check pre-label rows against independently re-read sibling records.

    ``volume_basis`` is supplied by the pinned rev3 manifest's volume_basis.decision,
    never trusted merely because an ensemble row asserts it.
    """
    problems: list[str] = []
    try:
        identity = paired_source_identity(v3_snapshot, served_snapshot)
        inputs = _mapping(v3_snapshot["inputs"])
        market, cut = str(inputs["market"]), _instant(inputs["as_of"])
        screen_inputs = _mapping(_mapping(v3_snapshot["outputs"]).get("screen"))
        chosen, _ = screen(screen_inputs, basis=volume_basis)
        targets = _served_targets(served_snapshot, market=market, as_of=cut)
        classes = [_mapping(row.get("catalogue_classification")) for row in records]
        if (len(records) != _mapping(identity.get("catalogue_counts")).get("rows")
                or canonical_hash(sorted(classes, key=lambda x: str(x.get("symbol"))))
                != _mapping(identity.get("catalogue_classification")).get("classification_sha256")):
            problems.append("ensemble_catalogue_names_or_classification_mismatch")
        symbols: set[str] = set()
        for row in records:
            symbol = str(row.get("symbol") or "")
            if not symbol or symbol in symbols:
                problems.append("ensemble_duplicate_or_missing_symbol")
            if _mapping(row.get("catalogue_classification")).get("symbol") != symbol:
                problems.append("ensemble_catalogue_row_symbol_mismatch")
            symbols.add(symbol)
            expected_price = pit._positive(_mapping(screen_inputs.get(symbol)).get("close"))
            if row.get("price") != expected_price:
                problems.append("ensemble_price_differs_from_rev3:" + symbol)
            if row.get("served_tp") != targets.get(symbol):
                problems.append("ensemble_served_tp_differs_from_sibling:" + symbol)
            if row.get("screened") is not (symbol in chosen) or row.get("screen_volume_basis") != volume_basis:
                problems.append("ensemble_screen_differs_from_rev3:" + symbol)
            if (row.get("market") != market or _instant(row.get("as_of")) != cut
                    or row.get("session_date") != _mapping(inputs["manifest"])["session_date"]):
                problems.append("ensemble_row_slot_mismatch:" + symbol)
            if row.get("paired_source_sha256") != canonical_hash(identity):
                problems.append("ensemble_row_source_reference_mismatch:" + symbol)
    except (ValueError, TypeError, KeyError) as error:
        problems.append("ensemble_paired_source_invalid:" + type(error).__name__)
    return sorted(set(problems))


def _shares(raw: list[dict[str, Any]], *, front: Any, end: date) -> tuple[Any, dict[str, Any]] | None:
    """Exactly rev3's cover-document selection; no current outstandingShares fallback."""
    concepts = {concept for field in pit.AS_FILED_BALANCE for concept in front.CONCEPT_LADDER[field]}
    newest: dict[str, date] = {}
    accepted: dict[str, datetime] = {}
    for row in raw:
        doc = str(row["doc_id"])
        accepted[doc] = max(_instant(row["accepted_at"]), accepted.get(doc, _instant(row["accepted_at"])))
        if row.get("period_start") is None and row["concept"] in concepts:
            newest[doc] = max(_date(row["period_end"]), newest.get(doc, _date(row["period_end"])))
    counts = front._cover_shares(raw)
    candidates = [doc for doc in counts if newest.get(doc) == end]
    if not candidates:
        return None
    doc = max(candidates, key=lambda key: (accepted[key], key))
    rows = [row for row in raw if str(row["doc_id"]) == doc and row["concept"] == "dei:EntityCommonStockSharesOutstanding"]
    if not rows:
        return None
    newest_cover = max(_date(row["period_end"]) for row in rows)
    rows = [row for row in rows if _date(row["period_end"]) == newest_cover]
    return _fact(float(counts[doc]), end, rows, "rev3_latest_own_balance_cover_document:class_sum_protocol_convention", unit="shares")


def compute_grid_section(database: Any, *, market: str, as_of: datetime, prices: pit.PinnedPrices,
                         v3_snapshot: Mapping[str, Any], served_snapshot: Mapping[str, Any],
                         implementation: Mapping[str, str], seed: int = DESIGN_SEED,
                         vintages: pit.AsFiledReader | None = None, volume_basis: str,
                         before_read: Callable[[], None] | None = None) -> dict[str, Any]:
    """Compute all16 kernels/all8 variants for ONE immutable rev3 (exchange,T).

    Labels, prediction TP inputs and financial-current-provider blocks are absent
    from the API. The served sibling's TP is copied only as the paired comparator.
    Identity/pin defects refuse the section; company missingness keeps all16 rows.
    Nothing is persisted or promoted. Caller's instrument binding precedes this.
    """
    cut = utc(as_of)
    if market not in {"NASDAQ", "NYSE"} or type(seed) is not int or seed != DESIGN_SEED:
        raise GridInputError("unsupported_market_or_design_seed")
    if volume_basis not in pit.DOLLAR_VOLUME_BASES:
        raise GridInputError("explicit_rev3_volume_basis_required")
    if not isinstance(implementation, Mapping) or not implementation or any(not isinstance(k, str) or not k or not isinstance(v, str) or re.fullmatch(r"[0-9a-f]{64}", v) is None
                                 for k, v in implementation.items()):
        raise GridInputError("explicit_implementation_fingerprints_required")
    v3 = _snapshot_manifest(v3_snapshot, analysis=pit.ANALYSIS_TYPE, market=market, as_of=cut)
    sibling = _snapshot_manifest(served_snapshot, analysis=served.ANALYSIS_TYPE, market=market, as_of=cut)
    input_pins = paired_source_identity(v3_snapshot, served_snapshot)
    if prices.market != market or utc(prices.as_of) != cut or prices.manifest() != v3.get("price_vintage"):
        raise GridInputError("rev3_price_pin_mismatch")
    if sibling.get("price_vintage") != v3.get("price_vintage") or sibling.get("session_date") != v3.get("session_date"):
        raise GridInputError("rev3_siblings_price_or_session_mismatch")
    screen_inputs = _mapping(_mapping(v3_snapshot.get("outputs")).get("screen"))
    if screen_inputs != _mapping(_mapping(served_snapshot.get("outputs")).get("screen")):
        raise GridInputError("rev3_siblings_screen_mismatch")
    selected, screen_refused = screen(screen_inputs, basis=volume_basis)
    cat_pin = _mapping(_mapping(v3_snapshot.get("inputs")).get("catalogue_pin"))
    served_cat_pin = _mapping(_mapping(served_snapshot.get("inputs")).get("catalogue_pin"))
    if not cat_pin.get("resolved_snapshot_id") or cat_pin != served_cat_pin:
        raise GridInputError("rev3_catalogue_pin_missing_or_mismatched")
    catalogue_snapshot = _read_snapshot(database, str(cat_pin["resolved_snapshot_id"]), analysis=pit.CATALOGUE_ANALYSIS_TYPE,
                                        entity=f"{market}_UNIVERSE", before_read=before_read)
    catalogue = pit.admitted_catalogue(catalogue_snapshot)
    cat_ref = _role(v3, "catalogue")
    if cat_ref is None or cat_ref != _role(sibling, "catalogue") or cat_ref.get("classification_sha256") != canonical_hash(catalogue):
        raise GridInputError("rev3_catalogue_content_mismatch")
    symbols = [str(row["symbol"]) for row in catalogue]
    if len(symbols) != len(set(symbols)):
        raise GridInputError("duplicate_catalogue_symbol")
    _guarded(lambda: prices.build_proxy(symbols), before_read)
    curve_ref = _mapping(_mapping(v3.get("macro")).get("curve"))
    if not curve_ref.get("snapshot_id") or _mapping(_mapping(sibling.get("macro")).get("curve")) != curve_ref:
        raise GridInputError("rev3_treasury_pin_missing_or_mismatched")
    macro_snapshot = _read_snapshot(database, str(curve_ref["snapshot_id"]), analysis=pit.SOURCE_ANALYSIS_TYPE,
                                    entity=pit.MACRO_TREASURY_KEY, before_read=before_read)
    history = _mapping(_mapping(macro_snapshot.get("outputs")).get("payload"))
    if history.get("payload_sha256") != canonical_payload_sha256(history) or history.get("payload_sha256") != curve_ref.get("source_payload_sha256"):
        raise GridInputError("rev3_treasury_source_hash_mismatch")
    curve = pit.curve_package_at(history, as_of=cut, economic_date=pit.economic_date_of(market, cut))
    if curve is None or curve.get("payload_sha256") != curve_ref.get("derived_payload_sha256"):
        raise GridInputError("rev3_treasury_at_T_mismatch")
    served_targets = _served_targets(served_snapshot, market=market, as_of=cut)
    reader = vintages if vintages is not None else pit.AsFiledReader(database)
    if not _guarded(reader.present, before_read):
        raise GridInputError("statement_vintages_unavailable")
    coverage = _guarded(lambda: reader.coverage(market), before_read)
    raw_by_issuer: dict[str, list[dict[str, Any]]] = {}
    companies: dict[str, GridCompanyInputs] = {}
    premises_by_symbol: dict[str, Any] = {}
    ledger: dict[str, Any] = {}
    consensus: dict[str, tuple[float | None, dict[str, Any]]] = {}
    company_refusals: dict[str, str] = {}
    for row in catalogue:
        symbol = str(row["symbol"])
        item: dict[str, Any] = {"status": "not_evaluable", "reason": None, "models": 16,
                                "classification_basis": "current_pinned_catalogue_rev3_convention",
                                "original_scope_class_share_basis_authentication": False}
        ledger[symbol] = item
        try:
            if row.get("security_type") != "Stock":
                raise NotEvaluable("not_a_stock")
            if symbol not in screen_inputs:
                raise NotEvaluable("rev3_symbol_inputs_not_admitted_at_T")
            issuer = coverage.get(symbol)
            if not issuer:
                raise NotEvaluable("statement_vintages_missing")
            if issuer not in raw_by_issuer:
                refused: Counter[str] = Counter()
                raw_by_issuer[issuer] = _guarded(lambda key=issuer: reader.facts(key, as_of=cut, refused=refused), before_read)
                if refused:
                    item["reader_refused"] = dict(sorted(refused.items()))
            raw = raw_by_issuer[issuer]
            payload, reference = pit.as_filed_payload(raw, market=market, front=reader.front)
            expected = _role(v3, pit.BASIS_VINTAGES, symbol=symbol)
            other_expected = _role(sibling, pit.BASIS_VINTAGES, symbol=symbol)
            if expected is None or other_expected is None or expected != other_expected:
                raise GridInputError("rev3_statement_source_reference_missing_or_mismatched")
            if any(expected.get(key) != reference.get(key) for key in reference):
                raise GridInputError("statements_table_not_stable")
            facts, facts_audit = reduce_company_facts(raw, issuer=issuer, as_of=cut, front=reader.front)
            item["facts"] = facts_audit
            fundamentals = pit.pit_fundamentals(payload, market=market, economic_date=pit.economic_date_of(market, cut))
            balance_end = _mapping(fundamentals.get("balance")).get("period_end")
            if balance_end is not None and facts:
                share_fact = _shares(raw, front=reader.front, end=_date(balance_end))
                if share_fact is not None:
                    facts["shares"], facts_audit["derivations"]["shares"] = share_fact
            if _guarded(lambda: prices.valid_sessions(symbol), before_read) < pit.MIN_VALID_SESSIONS:
                raise NotEvaluable(f"fewer_than_{pit.MIN_VALID_SESSIONS}_valid_sessions_at_T")
            price, price_session = _guarded(lambda: prices.price_at(symbol), before_read)
            if price is None or price_session != prices.session_date:
                raise NotEvaluable("close_D_unavailable")
            if price != pit._positive(_mapping(screen_inputs[symbol]).get("close")):
                raise GridInputError("rev3_pinned_close_differs_from_sibling")
            shares = facts.get("shares")
            if shares is None:
                raise NotEvaluable("official_cover_shares_unavailable")
            events = _guarded(lambda: prices.capital_events(symbol), before_read)
            if any(day > shares.period_end.isoformat() for day in events):
                raise NotEvaluable("capital_event_between_shares_and_T")
            basis = "rev3-as-traded:" + prices.publication_id + ":" + issuer
            price_evidence = Evidence("PRICE", prices.publication_id, prices.available_at, prices.bars_sha256)
            profile = row.get("valuation_profile")
            financial = profile == "financial" if isinstance(profile, str) and profile in {"financial", "general", "cyclical"} else None
            sector = row.get("sector")
            company = GridCompanyInputs(symbol, market, "USD", cut, basis,
                Price(price, "USD", _date(price_session), basis, price_evidence), facts,
                sector=sector.strip() if isinstance(sector, str) else "", sector_evidence=None, financial_company=financial, issuer_id=issuer,
                protocol={"basis_id": basis, "session_date": prices.session_date,
                          "catalogue_classification": "current_pinned_catalogue_rev3_convention"})
            company.validate()
            beta, beta_audit = _guarded(lambda: prices.beta(symbol), before_read)
            premises, premises_audit = derive_premises(company, curve=curve, beta=beta, beta_audit=beta_audit, facts_audit=facts_audit)
            companies[symbol] = company
            premises_by_symbol[symbol] = premises
            item.update(status="available", reason=None, premises=premises_audit, issuer_key=issuer,
                        price={"value": price, "session_date": price_session, "publication_available_at": prices.available_at.isoformat(),
                               "rule": "rev3_retrospective_pinned_publication_close_D_not_historical_capture_proof"})
        except NotEvaluable as error:
            company_refusals[symbol] = str(error)
            item["reason"] = str(error)
        # Raw analyst targets are read only through the snapshot that the sibling
        # explicitly referenced. Missing observation is not a fabricated median.
        target_ref = _role(v3, pit.PROVIDER_FMP, symbol=symbol)
        if target_ref is None:
            consensus[symbol] = (None, {"reason": "targets_snapshot_missing", "snapshot_id": None, "analyst_count": 0})
        else:
            target_snapshot = _read_snapshot(database, str(target_ref["snapshot_id"]), analysis=pit.SOURCE_ANALYSIS_TYPE,
                entity=pit.source_entity_key(market, pit.PROVIDER_FMP, symbol), before_read=before_read)
            target_rows = _mapping(target_snapshot.get("outputs")).get("payload")
            if not isinstance(target_rows, list) or canonical_hash(target_rows) != target_ref.get("payload_sha256"):
                raise GridInputError("rev3_consensus_snapshot_hash_mismatch")
            consensus[symbol] = grid_consensus_at(target_rows, as_of=cut, currency="USD", snapshot_id=str(target_snapshot["id"]), market=market)
        item["consensus"] = consensus[symbol][1]
    # The context key is known before evaluation. It contains canonical inputs,
    # never model outputs/record hashes and never the persistence clock.
    identity = {"source": SOURCE, "market": market, "as_of": cut.isoformat(), "seed": seed,
                "input_pins": input_pins, "implementation": dict(sorted(implementation.items())),
                "policy_id": "ensemble-grid-explicit-cashflow-v1", "volume_basis": volume_basis,
                "canonical_fact_rows_sha256": canonical_hash({issuer: sorted(str(r["row_hash"]) for r in rows)
                                                               for issuer, rows in sorted(raw_by_issuer.items())})}
    run_key = canonical_hash(identity)
    peers = tuple(companies[s] for s in sorted(companies))
    records: list[dict[str, Any]] = []
    totals: dict[str, Counter[str]] = {model: Counter() for model in MODEL_IDS}
    for row in catalogue:
        symbol = str(row["symbol"])
        company = companies.get(symbol)
        models = (evaluate_models(company, premises_by_symbol[symbol], peers=peers) if company is not None else
                  tuple(ModelValue(model, None, "not_evaluable", company_refusals.get(symbol, "company_inputs_unavailable")) for model in MODEL_IDS))
        value, consensus_receipt = consensus[symbol]
        aggregate = aggregate_grid_variants(models, value, consensus_reason=consensus_receipt.get("reason"))
        for model in models:
            totals[model.model]["evaluated" if model.status == "evaluated" else "not_evaluable:" + str(model.reason)] += 1
        records.append({"source": SOURCE, "market": market, "symbol": symbol, "session_date": prices.session_date,
            "as_of": cut.isoformat(), "run_key": run_key, "price": pit._positive(_mapping(screen_inputs.get(symbol)).get("close")),
            "catalogue_classification": dict(row),
            "served_tp": served_targets.get(symbol), "paired_source_sha256": canonical_hash(input_pins),
            "screened": symbol in selected, "screen_volume_basis": volume_basis,
            "models": [asdict(x) for x in models], "variants": aggregate["variants"],
            "primary": aggregate["primary"], "consensus": consensus_receipt, "input_ledger": ledger[symbol]})
    pair_problems = validate_record_pair(records, v3_snapshot, served_snapshot, volume_basis=volume_basis)
    if pair_problems:
        raise GridInputError("computed_records_do_not_match_rev3_siblings:" + ",".join(pair_problems))
    result = {"schema": SCHEMA, "source": SOURCE, "market": market, "session_date": prices.session_date, "as_of": cut.isoformat(),
              "seed": seed, "run_key": run_key, "input_pins": input_pins, "implementation": dict(sorted(implementation.items())),
              "context_identity": identity, "volume_basis": volume_basis,
              "records": records, "records_sha256": canonical_hash(records), "catalogue_stocks": sum(row.get("security_type") == "Stock" for row in catalogue),
              "ledger": {"catalogue_names": len(catalogue), "model_denominator_each": len(catalogue),
                         "model_results": {key: dict(sorted(value.items())) for key, value in totals.items()},
                         "screen_refused": dict(sorted(screen_refused.items())), "company_refusals": dict(sorted(Counter(company_refusals.values()).items()))},
              "external_api_calls": 0, "labels_read": 0, "historical_original_admissibility": False,
              "instrument_binding_enforced_here": False, "promotion_authorized": False}
    result["payload_sha256"] = canonical_hash(result)
    return result
