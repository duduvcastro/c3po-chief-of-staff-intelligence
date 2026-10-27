"""Label-free grade computation over the real canonical readers, synthetic memory only."""
from __future__ import annotations

import copy
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app import sec_xbrl, valuation_pit_rerun as pit, valuation_pit_served as served
from app.statement_vintages import StatementVintageStore
from app.valuation_ensemble_grid import (GridInputError, compute_grid_section, paired_source_identity,
                                         validate_record_pair)
from app.valuation_ensemble_grid_inputs import derive_premises, reduce_company_facts
from app.valuation_ensemble_inputs import canonical_hash
from app.valuation_ensemble_models import MODEL_IDS
from app.valuation_official import prediction_from_row
from app.valuation_panel import _NoNetworkHttp
from app.valuation_price_history import PriceHistoryService
from tests.test_valuation_pit_rerun import (NOW, T, VINTAGE_AT, SYMBOLS, _database, _publish_prices,
                                           _publish_sources, _settings, _target)


IMPLEMENTATION = {"synthetic_instrument.py": "a" * 64}


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    import socket
    import http.client

    def forbidden(*args, **kwargs):
        raise AssertionError("real network is forbidden in ensemble grade fixtures")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)


def _canonical_facts(database, *, omit: set[str] | None = None, omit_opening: bool = False) -> None:
    store = StatementVintageStore(database)
    omitted = omit or set()
    for index, symbol in enumerate(SYMBOLS):
        issuer = f"{index + 1:010d}"
        rows = []
        periods = [(date(year, 1, 1), date(year, 12, 31), True) for year in range(2018, 2024)]
        periods += [(date(year, month, 1), date(year + (month == 10), (month + 3 - 1) % 12 + 1, 1) - timedelta(days=1), False)
                    for year in range(2022, 2025) for month in (1, 4, 7, 10) if (year, month) <= (2024, 1)]
        for start, end, annual in periods:
            accepted = datetime.combine(end + timedelta(days=45), datetime.min.time(), tzinfo=timezone.utc)
            document = f"{issuer}:{end}:{'FY' if annual else 'Q'}"
            store.register_filings([{"market": "US", "issuer_key": issuer, "source": sec_xbrl.FILING_SOURCE,
                "doc_id": document, "form": "10-K" if annual else "10-Q", "filed_date": accepted.date(),
                "period_of_report": end, "accepted_at": accepted, "accepted_source": "synthetic_sec_header",
                "symbols": [symbol]}])
            scale = (1 + (end.year - 2018) * 0.04) * (1 + index * 0.1)
            fraction = 1.0 if annual else 0.25
            flow = {"us-gaap:Revenues": 2000 * scale, "us-gaap:NetIncomeLoss": 320 * scale,
                "us-gaap:OperatingIncomeLoss": (500 + 25 * index) * scale,
                "us-gaap:DepreciationDepletionAndAmortization": 50 * scale,
                "us-gaap:NetCashProvidedByUsedInOperatingActivities": 600 * scale,
                "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment": 100 * scale,
                "us-gaap:PaymentsOfDividendsCommonStock": 80 * scale,
                "us-gaap:IncomeTaxExpenseBenefit": 80 * scale,
                "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": 400 * scale,
                "us-gaap:InterestExpense": 100 * scale,
                "us-gaap:ProceedsFromIssuanceOfLongTermDebt": 80 * scale,
                "us-gaap:RepaymentsOfLongTermDebt": 60 * scale,
                "us-gaap:ProceedsFromRepaymentsForShortTermDebt": 0.0}
            instant = {"us-gaap:StockholdersEquity": 1800 * scale, "us-gaap:CashAndCashEquivalentsAtCarryingValue": 300 * scale,
                "us-gaap:DebtCurrent": 200 * scale, "us-gaap:LongTermDebtNoncurrent": 800 * scale,
                "us-gaap:AssetsCurrent": 2500 * scale, "us-gaap:LiabilitiesCurrent": 500 * scale,
                "us-gaap:Liabilities": 1200 * scale, "us-gaap:Goodwill": 50 * scale,
                "us-gaap:IntangibleAssetsNetExcludingGoodwill": 100 * scale,
                "us-gaap:LongTermDebtCurrent": 20 * scale,
                "us-gaap:FiniteLivedIntangibleAssetsNet": 40 * scale,
                "dei:EntityCommonStockSharesOutstanding": 10.0}
            # Duplicate fiscal-year and fourth-quarter instants are equivalent
            # reports in two documents; the latest acceptance/document wins.
            for concept, value in [*flow.items(), *instant.items()]:
                if concept in omitted or (omit_opening and concept == "us-gaap:StockholdersEquity" and end == date(2023, 3, 31)):
                    continue
                rows.append({"market": "US", "issuer_key": issuer, "source": sec_xbrl.VINTAGE_SOURCE,
                    "doc_id": document, "form": "10-K" if annual else "10-Q", "filed_date": accepted.date(),
                    "accepted_at": accepted, "period_start": start if concept in flow else None, "period_end": end,
                    "concept": concept, "unit": "shares" if concept.startswith("dei:") else "USD",
                    "value": value * fraction if concept in flow else value})
        store.insert_vintages("US", issuer, rows)


def _fixture(*, omit: set[str] | None = None, omit_opening: bool = False, etf: str | None = None):
    database = _database()
    _publish_prices(database)
    targets = {symbol: [_target(house, T - timedelta(days=10), value) for house, value in (("A", 100), ("B", 200), ("C", 1000))]
               for symbol in SYMBOLS}
    _publish_sources(database, targets=targets, poison=True)
    if etf is not None:
        catalogue = next(s for s in database._analysis_snapshots if s["analysis_type"] == pit.CATALOGUE_ANALYSIS_TYPE)
        next(row for row in catalogue["outputs"]["rows"] if row["symbol"] == etf)["security_type"] = "ETF"
    _canonical_facts(database, omit=omit, omit_opening=omit_opening)
    reader = pit.AsFiledReader(database)
    prices = pit.PinnedPrices(PriceHistoryService(_settings(), database, _NoNetworkHttp()), "NASDAQ", as_of=T,
                              pinned_at=VINTAGE_AT + timedelta(seconds=1), pin_mode="explicit")
    resolver = pit.PitSourceResolver(database, market="NASDAQ", as_of=T, prices=prices, statements="vintages",
                                      vintages=reader, catalogue_pinned_at=VINTAGE_AT)
    resolver.resolve()
    macro = resolver.macro()
    manifest = {"market": "NASDAQ", "as_of": T.isoformat(), "session_date": prices.session_date,
        "sources": sorted(resolver.references, key=canonical_hash), "price_vintage": prices.manifest(),
        "price_basis": dict(pit.PRICE_BASIS), "macro": macro.references}
    manifest["manifest_sha256"] = canonical_hash(manifest)
    screen_inputs = pit.PitComputation.screen_inputs(cast(pit.PitComputation, SimpleNamespace(resolver=resolver)))
    common = {"market": "NASDAQ", "as_of": T.isoformat(), "summary": {"statements": {"mode": "vintages"}},
              "screen": screen_inputs, "catalogue_counts": {"rows": len(SYMBOLS), "stocks": len(SYMBOLS) - int(etf is not None)}}
    v3_key = canonical_hash(["fixture_v3", manifest])
    v3_id = database.save_analysis_snapshot(pit.ANALYSIS_TYPE, "fixture-v3", "fixture", {"market": "NASDAQ", "as_of": T.isoformat(),
        "run_key": v3_key, "manifest": manifest, "catalogue_pin": resolver.catalogue_pin}, {**common, "run_key": v3_key}, NOW)
    served_manifest = copy.deepcopy(manifest)
    served_manifest["sources"] = [r for r in served_manifest["sources"] if r["role"] != pit.PROVIDER_FMP]
    served_manifest.pop("manifest_sha256")
    served_manifest["manifest_sha256"] = canonical_hash(served_manifest)
    served_key = canonical_hash(["fixture_served", served_manifest])
    served_id = "00000000-0000-0000-0000-000000000123"
    records = []
    for symbol, item in sorted(screen_inputs.items()):
        if item["security_type"] != "Stock":
            continue
        record = prediction_from_row({"symbol": symbol, "price": item["close"], "internal_tp": 777.0,
            "internal_buy_in": 70.0, "methods": {"fixture": 777.0}, "tp_validation_status": "diagnostic_only"},
            market="NASDAQ", scope="universe", cycle_id=served_id, source_version="fixture", prediction_instant=T,
            source_manifest_sha256=served_manifest["manifest_sha256"], published_at=NOW, source=served.SERVED_SOURCE,
            extra_provenance={"run_key": served_key})
        assert record is not None
        records.append(served.relabelled(record))
    database.save_analysis_snapshot(served.ANALYSIS_TYPE, "fixture-served", "fixture", {"market": "NASDAQ", "as_of": T.isoformat(),
        "run_key": served_key, "manifest": served_manifest, "catalogue_pin": resolver.catalogue_pin},
        {**common, "run_key": served_key, "records": records, "prediction_identities": [[r["symbol"], r["row_sha256"]] for r in records]},
        NOW, snapshot_id=served_id)
    v3_snapshot, served_snapshot = database.analysis_snapshot_by_id(v3_id), database.analysis_snapshot_by_id(served_id)
    assert v3_snapshot is not None and served_snapshot is not None
    return database, prices, v3_snapshot, served_snapshot


def _compute(fixture, **changes):
    database, prices, v3, sibling = fixture
    return compute_grid_section(database, market="NASDAQ", as_of=T, prices=prices, v3_snapshot=v3,
                                served_snapshot=sibling, implementation=IMPLEMENTATION, volume_basis="as_traded", **changes)


@pytest.fixture(scope="module")
def ready():
    return _fixture()


def test_real_canonical_readers_all_models_variants_denominators_and_no_original_requirement(ready):
    result = _compute(ready)
    assert result["source"] == "ensemble_pit" and result["labels_read"] == result["external_api_calls"] == 0
    assert result["catalogue_stocks"] == result["ledger"]["model_denominator_each"] == 6
    assert [r["symbol"] for r in result["records"]] == sorted(SYMBOLS)
    assert all(tuple(m["model"] for m in r["models"]) == MODEL_IDS and len(r["variants"]) == 8 for r in result["records"])
    assert all(sum(counts.values()) == 6 for counts in result["ledger"]["model_results"].values())
    assert any(sum(m["status"] == "evaluated" for m in r["models"]) >= 14 for r in result["records"])
    assert not result["historical_original_admissibility"] and not result["instrument_binding_enforced_here"]
    assert result["input_pins"] == paired_source_identity(ready[2], ready[3])
    assert validate_record_pair(result["records"], ready[2], ready[3]) == []
    assert canonical_hash(result["context_identity"]) == result["run_key"]
    assert all(r["run_key"] == result["run_key"] for r in result["records"])


def test_house_mean_is_from_raw_snapshot_not_median_or_served_tp(ready):
    result = _compute(ready)
    row = result["records"][0]
    assert row["consensus"]["value"] == pytest.approx(1300 / 3)
    assert row["consensus"]["public_consensus_tp"] == 200
    assert row["consensus"]["analyst_count"] == 3 and row["consensus"]["snapshot_id"]
    assert row["served_tp"] == 777
    assert all(m["value"] != 777 for m in row["models"] if m["value"] is not None)


def test_no_current_provider_block_or_precomputed_v3_target_and_idempotent(ready):
    a = _compute(ready)
    changed = (ready[0], ready[1], copy.deepcopy(ready[2]), copy.deepcopy(ready[3]))
    changed[2]["outputs"]["rows"] = {symbol: {"v3_internal_tp": 1e100, "models": {"poison": 1e100}} for symbol in SYMBOLS}
    assert _compute(changed) == a == _compute(ready)


@pytest.mark.parametrize("field", ["price", "served_tp", "screened", "paired_source_sha256"])
def test_pair_validator_refuses_tampered_source_correspondence(ready, field):
    rows = copy.deepcopy(_compute(ready)["records"])
    rows[0][field] = (not rows[0][field]) if field == "screened" else 123456
    assert validate_record_pair(rows, ready[2], ready[3])


def test_pair_validator_refuses_dropped_or_substituted_catalogue_name(ready):
    rows = copy.deepcopy(_compute(ready)["records"])
    assert "ensemble_catalogue_names_or_classification_mismatch" in validate_record_pair(rows[1:], ready[2], ready[3])
    rows[0]["symbol"] = "ZZZ"
    assert validate_record_pair(rows, ready[2], ready[3])


@pytest.mark.parametrize("kind", ["mode", "T", "price", "records"])
def test_mixed_or_corrupt_siblings_refuse_before_compute(ready, kind):
    db, prices, v3, sibling = ready
    v3, sibling = copy.deepcopy(v3), copy.deepcopy(sibling)
    if kind == "mode":
        v3["outputs"]["summary"]["statements"]["mode"] = "provider"
    elif kind == "T":
        sibling["inputs"]["as_of"] = (T - timedelta(days=1)).isoformat()
    elif kind == "price":
        sibling["inputs"]["manifest"]["price_vintage"]["publication_id"] = "another"
    else:
        sibling["outputs"]["records"][0]["tp"] = 1e10
    with pytest.raises((GridInputError, ValueError)):
        _compute((db, prices, v3, sibling))


def test_partial_debt_and_partial_intangibles_do_not_become_aggregates():
    fixture = _fixture(omit={"us-gaap:DebtCurrent", "us-gaap:IntangibleAssetsNetExcludingGoodwill"})
    result = _compute(fixture)
    for row in result["records"]:
        models = {m["model"]: m for m in row["models"]}
        assert models["ev_sales"]["reason"] == "missing_fact:debt"
        assert models["tangible_book"]["reason"] == "missing_fact:intangible_assets_excluding_goodwill"
        assert models["price_book"]["status"] == "evaluated"


def test_residual_income_requires_exact_opening_date_not_nearest():
    result = _compute(_fixture(omit_opening=True))
    for row in result["records"]:
        residual = next(m for m in row["models"] if m["model"] == "residual_income")
        assert residual["reason"] == "missing_fact:book_equity_beginning"


def test_recomputed_tax_missing_is_not_an_exception_or_zero_fill():
    result = _compute(_fixture(omit={"us-gaap:IncomeTaxExpenseBenefit"}))
    assert all(next(m for m in row["models"] if m["model"] == "dcf_fcff")["reason"] == "missing_premise:tax_rate"
               for row in result["records"])
    assert all("tax_rate" not in row["input_ledger"]["premises"]["receipt"]["scalars"] for row in result["records"])


def test_seed_and_implementation_are_explicit(ready):
    with pytest.raises(GridInputError, match="seed"):
        _compute(ready, seed=3)
    with pytest.raises(TypeError):
        _compute(ready, labels={"AAA": 1})


def test_stock_denominator_and_full_catalogue_ledger_include_one_etf():
    fixture = _fixture(etf="FFF")
    result = _compute(fixture)
    assert result["catalogue_stocks"] == 5
    assert len(result["records"]) == result["ledger"]["model_denominator_each"] == 6
    etf = next(row for row in result["records"] if row["symbol"] == "FFF")
    assert not etf["screened"] and etf["served_tp"] is None
    assert all(model["reason"] == "not_a_stock" for model in etf["models"])
    assert validate_record_pair(result["records"], fixture[2], fixture[3]) == []


@pytest.mark.parametrize("expires_on_call", [1, 2])
def test_gate_expiry_before_or_immediately_after_database_read_stops_consumption(ready, monkeypatch, expires_on_call):
    database = ready[0]
    original = database.analysis_snapshot_by_id
    read_ids = []
    calls = 0

    def read(snapshot_id):
        read_ids.append(snapshot_id)
        return original(snapshot_id)

    def active():
        nonlocal calls
        calls += 1
        if calls >= expires_on_call:
            raise RuntimeError("synthetic_owner_order_expired")

    monkeypatch.setattr(database, "analysis_snapshot_by_id", read)
    with pytest.raises(RuntimeError, match="expired"):
        _compute(ready, before_read=active)
    assert len(read_ids) == expires_on_call - 1
    assert calls == expires_on_call


def test_gate_expiry_immediately_after_real_fact_reader_stops_followup(ready, monkeypatch):
    reader = pit.AsFiledReader(ready[0])
    assert reader.present()
    original = reader.facts
    consumed = False

    def facts(*args, **kwargs):
        nonlocal consumed
        rows = original(*args, **kwargs)
        consumed = True
        return rows

    def active():
        if consumed:
            raise RuntimeError("synthetic_owner_order_expired_after_fact_read")

    monkeypatch.setattr(reader, "facts", facts)
    with pytest.raises(RuntimeError, match="after_fact_read"):
        _compute(ready, vintages=reader, before_read=active)
    assert consumed


@pytest.mark.parametrize("future", [True, False])
def test_appended_fact_after_T_is_inert_but_new_fact_by_T_refuses_old_sibling(future):
    fixture = _fixture()
    before = _compute(fixture)
    store = StatementVintageStore(fixture[0])
    original = next(row for row in getattr(fixture[0], "_statement_vintages") if row["concept"] == "us-gaap:Revenues")
    added = dict(original, doc_id="synthetic-later-comparative", value=1e9,
                 accepted_at=T + timedelta(days=1) if future else T - timedelta(days=1))
    store.insert_vintages("US", original["issuer_key"], [added])
    if future:
        assert _compute(fixture) == before
    else:
        with pytest.raises(GridInputError, match="statements_table_not_stable"):
            _compute(fixture)


@pytest.mark.parametrize("kind", ["targets", "treasury"])
def test_pinned_snapshot_content_change_is_refused_instead_of_current_fallback(kind):
    fixture = _fixture()
    if kind == "targets":
        snapshot = next(s for s in fixture[0]._analysis_snapshots if s["entity_key"] == pit.source_entity_key("NASDAQ", pit.PROVIDER_FMP, "AAA"))
        snapshot["outputs"]["payload"][0]["priceTarget"] = 1e9
    else:
        snapshot = next(s for s in fixture[0]._analysis_snapshots if s["entity_key"] == pit.MACRO_TREASURY_KEY)
        snapshot["outputs"]["payload"]["series"]["US3Y.GBOND"][0]["close"] = 19.0
    with pytest.raises(GridInputError, match="hash_mismatch"):
        _compute(fixture)


def test_corrupt_eligible_fact_cannot_promote_an_older_value(ready):
    reader = pit.AsFiledReader(ready[0])
    assert reader.present()
    issuer = reader.coverage("NASDAQ")["AAA"]
    rows = reader.facts(issuer, as_of=T, refused=Counter())
    rows[0] = {**rows[0], "row_hash": "0" * 64}
    facts, audit = reduce_company_facts(rows, issuer=issuer, as_of=T, front=reader.front)
    assert facts == {} and audit["refused"]["canonical_fact_hash_mismatch"] == 1
