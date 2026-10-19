"""The B3 CVM field-wise overlay: its correctness end to end (precedence, point in time, the EBITDA defect, units,
restated documents), the nightly shadow (``valuation_cvm_overlay_shadow``) and the read-only before/after receipt of
``valuation-readonly-report.yml`` (``report=cvm-before-after``). Synthetic symbols and figures only."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from app import valuation_cvm_overlay_shadow as shadow
from app import valuation_env
from app.config import Settings
from app.cvm_fundamentals import CvmPackage, extract_cvm_official_statements, extract_itr_official_fundamentals, scan_cvm_package
from app.database import Database
from app.official_fundamentals import apply_official_fundamentals, apply_official_fundamentals_map, save_official_fundamentals
from app.official_statements import (
    FIELDWISE_OVERLAY_ENV,
    SOURCE_FIELDS,
    apply_official_statements,
    apply_official_statements_map,
    fieldwise_sources,
    official_overlays,
    save_official_statements,
)
from app.schemas import NormalizedQuote
from cvm_statement_fixtures import INDUSTRY, ISSUERS, Package, _flow, _ytd, build_packages, industry_income, industry_value_added

YEAR = 2026
PREVIOUS = YEAR - 1
BACKEND = Path(__file__).resolve().parents[1]
WORKFLOW = BACKEND.parents[1] / ".github" / "workflows" / "valuation-readonly-report.yml"


def _database(tmp_path: Path | None = None) -> Database:
    return Database(Settings(database_url="", auth_cookie_secure=False, **({"migrations_dir": tmp_path} if tmp_path else {})))


def _scans(packages: dict[tuple[str, int], Package] | None = None) -> list[Any]:
    packages = packages or build_packages(YEAR)
    return [scan_cvm_package(CvmPackage(kind, package_year, package.payload(), f"https://example.invalid/{kind}/{package_year}.zip"), ISSUERS)
            for (kind, package_year), package in packages.items()]


def _statements() -> dict[str, dict[str, Any]]:
    return {payload["symbol"]: payload for payload in extract_cvm_official_statements(_scans(), issuers=ISSUERS)}


def _provider_one_quarter_behind() -> dict[str, Any]:
    """EODHD-shaped fundamentals of the synthetic industrial issuer, in reais, one quarter behind the regulator."""
    return {
        "financialsAsOf": f"{YEAR}-03-31",
        "marketCap": 2_000_000.0,
        "sharesOutstanding": 1_000.0,
        "ebitda": 120_000.0,
        "totalRevenue": 520_000.0,
        "enterpriseToEbitda": 16.5,
        "quarterlyIncome": [
            {"date": f"{YEAR}-03-31", "totalRevenue": 140_000.0, "ebitda": 30_000.0, "netIncome": 14_000.0},
            {"date": f"{PREVIOUS}-12-31", "totalRevenue": 130_000.0, "ebitda": 30_000.0, "netIncome": 13_000.0},
            {"date": f"{PREVIOUS}-09-30", "totalRevenue": 120_000.0, "ebitda": 30_000.0, "netIncome": 12_000.0},
            {"date": f"{PREVIOUS}-06-30", "totalRevenue": 110_000.0, "ebitda": 30_000.0, "netIncome": 11_000.0},
        ],
        "quarterlyCashFlow": [],
        "quarterlyBalance": [{"date": f"{YEAR}-03-31", "cashAndShortTermInvestments": 80_000.0, "shortLongTermDebtTotal": 100_000.0}],
    }


# ------------------------------------------------------------------ correctness of the overlay, end to end
def test_the_ebitda_defect_is_fixed_from_the_dva_end_to_end() -> None:
    """From the CVM archives to the served figure: the legacy ITR reader carries no EBITDA, so the legacy overlay sums two
    provider quarters (the halving); the field-wise overlay over the complete statements sums four quarters of
    EBIT + |DVA D&A| and recomputes EV/EBITDA from it."""
    itr = build_packages(YEAR)[("itr", YEAR)]
    legacy = next(payload for payload in extract_itr_official_fundamentals(itr.payload(), year=YEAR, issuers=ISSUERS, source_url="https://example.invalid")
                  if payload["symbol"] == "INDS3")
    statements = _statements()["INDS3"]
    provider = _provider_one_quarter_behind()

    served_legacy = apply_official_fundamentals(provider, legacy)
    assert served_legacy["ebitda"] == 60_000.0  # Q4 and Q3 of the provider only: half a year served as TTM

    fieldwise = apply_official_statements(provider, statements)
    # EBIT + D&A per quarter (fixture, BRL thousands scaled to reais): 2Q 30+7, 1Q 28+7, 4Q 26+6, 3Q 24+6
    assert fieldwise["ebitda"] == 37_000 + 35_000 + 32_000 + 30_000
    assert fieldwise["enterpriseToEbitda"] == pytest.approx((2_000_000 + 100_000 - 82_000) / 134_000)
    assert fieldwise_sources(provider, statements)["ebitda"] == "cvm"
    assert shadow._legacy_partial_window(served_legacy) and not shadow._legacy_partial_window(fieldwise)


def test_per_field_precedence_cvm_consolidated_then_individual_then_eodhd() -> None:
    """A CVM field beats the provider's for the same period; a field the CVM row lacks stays the provider's; an issuer's
    consolidated statements win over its individual ones (the individual DRE of the fixture is doubled) and an issuer
    without consolidated statements is read from its individual ones."""
    statements = _statements()
    provider = _provider_one_quarter_behind()
    provider["quarterlyIncome"][0]["researchDevelopment"] = 1.0
    served = apply_official_statements(provider, statements["INDS3"])
    first_quarter = next(row for row in served["quarterlyIncome"] if row["date"] == f"{YEAR}-03-31")
    assert first_quarter["totalRevenue"] == 140_000  # CVM consolidated (the individual file says 280,000)
    assert first_quarter["ebitda"] == 35_000  # CVM, not the provider's 30,000
    assert first_quarter["researchDevelopment"] == 1.0  # the provider's, kept: the CVM row does not carry it
    assert statements["SERV3"]["official_metrics"]["statementScope"] == "individual"

    no_cash_flow = apply_official_statements(provider, statements["SERV3"])  # services files no DFC: the provider stays
    assert fieldwise_sources(provider, statements["SERV3"])["operatingCashflow"] == "absent"
    assert "operatingCashflow" not in no_cash_flow


def test_field_sources_mirror_what_the_overlay_serves() -> None:
    provider = _provider_one_quarter_behind()
    statements = copy.deepcopy(_statements()["INDS3"])
    sources = fieldwise_sources(provider, statements)
    assert set(sources) == set(SOURCE_FIELDS)
    assert sources["totalRevenue"] == sources["ebitda"] == sources["netIncome"] == "cvm"
    assert sources["totalCash"] == sources["totalDebt"] == sources["totalEquity"] == sources["sharesOutstanding"] == "cvm"

    # two newer CVM quarters lack EBITDA: the window mixes CVM revenue with provider quarters, EBITDA has no full window
    for row in statements["quarterlyIncome"]:
        if row["date"] in {f"{YEAR}-06-30"}:
            row.pop("ebitda")
    mixed = fieldwise_sources(provider, statements)
    assert mixed["ebitda"] == "eodhd"  # no complete window: the provider's own TTM figure stays
    assert apply_official_statements(provider, statements)["ebitda"] == provider["ebitda"]
    statements["quarterlyIncome"] = [row for row in statements["quarterlyIncome"] if row["date"] >= f"{YEAR}-01-01"]
    statements["quarterlyIncome"][0]["ebitda"] = 37_000.0
    assert fieldwise_sources(provider, statements)["ebitda"] == "mixed"  # 2Q and 1Q from CVM, 4Q and 3Q from the provider
    assert apply_official_statements(provider, statements)["ebitda"] == 37_000 + 35_000 + 30_000 + 30_000

    older = copy.deepcopy(provider)
    older["financialsAsOf"] = f"{YEAR}-09-30"  # an overlay older than the provider is ignored: every field is the provider's
    assert set(fieldwise_sources(older, statements).values()) <= {"eodhd", "absent"}
    assert fieldwise_sources({}, None) == {name: "absent" for name in SOURCE_FIELDS}


def test_a_provider_quarter_is_never_served_as_a_trailing_year() -> None:
    """Defect found (2026-10-19): EODHD's top-level ``freeCashflow``/``operatingCashflow`` are its latest QUARTER
    (``eodhd._latest_statement``), and once a name carries an overlay the screener reads them from the overlay instead of
    Brapi's TTM. Without a complete window the field-wise overlay used to leave that quarter in place, served as a year.
    Now: the provider's own complete TTM, else nothing."""
    provider = _provider_one_quarter_behind()
    provider.update({"freeCashflow": 10.0, "operatingCashflow": 12.0})
    provider["quarterlyCashFlow"] = [{"date": period, "totalCashFromOperatingActivities": 12.0, "freeCashFlow": 10.0}
                                     for period in (f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30")]
    statements = copy.deepcopy(_statements()["INDS3"])
    statements["quarterlyCashFlow"] = [row for row in statements["quarterlyCashFlow"] if row["date"] == f"{YEAR}-06-30"]
    statements["quarterlyCashFlow"][0].pop("freeCashFlow")  # capex not classifiable this quarter: no official FCF
    served = apply_official_statements(provider, statements)
    assert served["operatingCashflow"] == 20_000 + 12.0 * 3  # CVM 2Q + three provider quarters: a complete window
    assert "freeCashflow" not in served  # three provider quarters only: no TTM exists, the quarter is not served as one
    assert fieldwise_sources(provider, statements)["freeCashflow"] == "absent"
    assert fieldwise_sources(provider, statements)["operatingCashflow"] == "mixed"
    provider["quarterlyCashFlow"].append({"date": f"{PREVIOUS}-06-30", "totalCashFromOperatingActivities": 12.0, "freeCashFlow": 10.0})
    served = apply_official_statements(provider, statements)
    assert served["freeCashflow"] == 40.0  # the provider's own four quarters, one quarter behind
    assert fieldwise_sources(provider, statements)["freeCashflow"] == "eodhd"


def test_units_cvm_thousands_and_units_scale_to_the_same_reais() -> None:
    """ESCALA_MOEDA = MIL multiplies VL_CONTA by 1,000; UNIDADE leaves it: the same quarter filed both ways is the same
    number of reais, the unit the provider's figures are in."""
    def first_quarter(scale: str, factor: int) -> dict[str, Any]:
        package = Package("itr", YEAR)
        refer, start = f"{YEAR}-03-31", f"{YEAR}-01-01"
        values = tuple(value * factor for value in _ytd(0, 1))
        package.document(INDUSTRY, refer, 1, f"{YEAR}-04-10")
        package.add("DRE", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_income(values), scale=scale))
        package.add("DVA", "con", _flow(INDUSTRY, refer, 1, "ÚLTIMO", start, refer, industry_value_added(values), scale=scale))
        scans = _scans({("itr", YEAR): package})
        payload = next(item for item in extract_cvm_official_statements(scans, issuers=ISSUERS) if item["symbol"] == "INDS3")
        return payload["quarterlyIncome"][0]

    thousands, units = first_quarter("MIL", 1), first_quarter("UNIDADE", 1_000)
    assert thousands["totalRevenue"] == units["totalRevenue"] == 140_000
    assert thousands["ebitda"] == units["ebitda"] == 35_000


def test_a_restated_document_replaces_the_original_and_dates_it_by_its_own_receipt(tmp_path: Path) -> None:
    """A re-filed version of the same quarter (VERSAO 2) wins over version 1, in the extractor and in the stored
    statements the overlay reads; its receipt date is its own."""
    statements = _statements()["INDS3"]
    documents = statements["official_metrics"]["periodDocuments"]
    assert documents[f"{YEAR}-06-30"]["version"] == 2 and documents[f"{YEAR}-06-30"]["receivedOn"] == f"{YEAR}-08-02"

    database = _database(tmp_path)
    original = copy.deepcopy(statements)
    original["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"].update({"version": 1, "receivedOn": f"{YEAR}-07-10"})
    original["quarterlyIncome"][0]["ebitda"] = 99_000.0
    save_official_statements(database, [original])
    assert apply_official_statements_map(database, {"INDS3": _provider_one_quarter_behind()}, market="B3")["INDS3"]["ebitda"] == 99_000 + 35_000 + 32_000 + 30_000
    save_official_statements(database, [statements])  # the restatement arrives in a later collection
    restated = apply_official_statements_map(database, {"INDS3": _provider_one_quarter_behind()}, market="B3")["INDS3"]
    assert restated["ebitda"] == 134_000


def test_point_in_time_only_documents_received_by_the_build_instant(tmp_path: Path) -> None:
    """A snapshot stored after the cut, or holding a document received after the cut's date in Sao Paulo, is never read:
    the symbol falls back to the legacy overlay received by then (or to the provider). Live builds read snapshots the IR
    worker wrote before them, so nothing is dropped there."""
    database = _database(tmp_path)
    legacy_payload = {
        "market": "B3", "symbol": "INDS3", "as_of": f"{YEAR}-06-30", "source_name": "CVM Dados Abertos - ITR consolidado",
        "quarterlyIncome": [{"date": f"{YEAR}-06-30", "totalRevenue": 150_000.0}], "quarterlyCashFlow": [], "quarterlyBalance": [],
        "official_metrics": {},
    }
    stored_at = datetime(YEAR, 8, 3, 12, tzinfo=timezone.utc)
    database.save_analysis_snapshot("official_fundamentals", "B3:INDS3", "mv", {}, legacy_payload, stored_at)
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, _statements()["INDS3"], stored_at)

    # receivedOn of 2Q is 2026-08-02: at 2026-08-02 02:00 UTC it is still 1 August in Sao Paulo
    before_receipt = official_overlays(database, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 2, 2, tzinfo=timezone.utc))["INDS3"]
    assert before_receipt.overlay is None and before_receipt.pit_excluded  # nor the legacy one: it was stored on 3 August
    after_receipt_before_storage = official_overlays(database, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 2, 23, tzinfo=timezone.utc))["INDS3"]
    assert after_receipt_before_storage.overlay is None and after_receipt_before_storage.pit_excluded
    stored = official_overlays(database, ["INDS3"], market="B3", as_of=stored_at)["INDS3"]
    assert stored.origin == "statements" and not stored.pit_excluded

    future = copy.deepcopy(_statements()["INDS3"])
    future["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"]["receivedOn"] = f"{YEAR}-08-04"  # dated after its storage
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, future, stored_at + timedelta(minutes=1))
    excluded = official_overlays(database, ["INDS3"], market="B3", as_of=stored_at + timedelta(hours=1))["INDS3"]
    assert excluded.pit_excluded and excluded.origin == "legacy" and excluded.overlay is not None
    assert excluded.overlay["source_name"] == legacy_payload["source_name"]
    served = apply_official_statements_map(database, {"INDS3": _provider_one_quarter_behind()}, market="B3", as_of=stored_at + timedelta(hours=1))
    assert served["INDS3"]["officialFundamentals"]["sourceName"] == legacy_payload["source_name"]
    assert official_overlays(database, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 5, tzinfo=timezone.utc))["INDS3"].origin == "statements"


# ------------------------------------------------------------------ the shadow
def test_the_capture_never_raises_and_never_touches_what_is_served(tmp_path: Path) -> None:
    class Broken:
        def latest_analysis_snapshots(self, *_: Any, **__: Any) -> dict[str, Any]:
            raise RuntimeError("store down")

    capture = shadow.ShadowCapture()
    served = {"INDS3": _provider_one_quarter_behind()}
    before = copy.deepcopy(served)
    capture.add(Broken(), served, served, served_overlay="legacy")
    assert capture.failure == "RuntimeError" and served == before and capture.statements_as_of is None
    capture.add(_database(tmp_path), served, served, served_overlay="legacy")  # once failed, the cycle's shadow stays off
    assert capture.shadow == {}


def test_the_aggregate_names_no_symbol_and_counts_the_corrections(tmp_path: Path) -> None:
    database = _database(tmp_path)
    itr = build_packages(YEAR)[("itr", YEAR)]
    legacy = [payload for payload in extract_itr_official_fundamentals(itr.payload(), year=YEAR, issuers=ISSUERS, source_url="https://example.invalid")
              if payload["symbol"] == "INDS3"]
    save_official_fundamentals(database, legacy)
    save_official_statements(database, [_statements()["INDS3"]])
    provider = {"INDS3": _provider_one_quarter_behind(), "PLAIN3": {"financialsAsOf": f"{YEAR}-06-30", "ebitda": 10.0, "sharesOutstanding": 5.0}}
    served = apply_official_fundamentals_map(database, provider, market="B3")
    capture = shadow.ShadowCapture()
    capture.add(database, provider, served, served_overlay="legacy")
    assert capture.failure is None and capture.origins == {"INDS3": "statements", "PLAIN3": None}

    served_rows = [{"symbol": "INDS3", "internal_tp": 10.0, "internal_buy_in": 8.0, "internal_tp_validation_status": "validated"},
                   {"symbol": "PLAIN3", "internal_tp": 20.0, "internal_buy_in": 16.0, "internal_tp_validation_status": "validated"},
                   {"symbol": "GONE3", "internal_tp": 5.0, "internal_buy_in": 4.0}]
    shadow_rows = [{"symbol": "INDS3", "internal_tp": 12.5, "internal_buy_in": 9.0, "internal_tp_validation_status": "review_required"},
                   {"symbol": "PLAIN3", "internal_tp": 20.0, "internal_buy_in": 16.0, "internal_tp_validation_status": "validated"}]
    outputs = shadow.build_shadow_outputs(capture, served_rows=served_rows, shadow_rows=shadow_rows, universe_symbols=["INDS3", "PLAIN3"],
                                          cycle_id="00000000-0000-4000-8000-000000000001", basis_at=datetime(YEAR, 10, 19, 3, tzinfo=timezone.utc),
                                          producer_build_sha="a" * 40)
    aggregate = outputs["aggregate"]
    assert tuple(aggregate) == shadow.AGGREGATE_KEYS and outputs["report_sha256"] == shadow.canonical_sha256(aggregate)
    text = json.dumps(aggregate)
    assert not any(symbol in text for symbol in ("INDS3", "PLAIN3", "GONE3"))
    assert aggregate["names"] == {"served": 3, "shadow": 2, "pairs": 2, "only_served": 1, "only_shadow": 0}
    assert aggregate["internal_tp"]["n"] == 2 and aggregate["internal_tp"]["changed"] == 1 and aggregate["internal_tp"]["over_20_percent"] == 1
    assert aggregate["internal_tp"]["median"] == pytest.approx(0.125) and aggregate["internal_tp"]["p90"] == pytest.approx(0.225)
    assert aggregate["internal_buy_in"]["abs_p90"] == pytest.approx(0.1125)
    assert aggregate["internal_validation"] == {"served_validated": 2, "shadow_validated": 1, "changed": 1}
    assert aggregate["ebitda"] == {"changed": 1, "legacy_partial_window": 1, "corrected": 1}
    assert aggregate["field_sources"]["ebitda"] == {"cvm": 1, "eodhd": 1, "mixed": 0, "absent": 0}
    assert aggregate["overlay_origin"] == {"statements": 1, "legacy": 0, "none": 1} and aggregate["served_overlay"] == "legacy"
    assert aggregate["shares_scale_suspect"] == 0  # 990 CVM shares against 1,000 provider shares
    assert outputs["private_detail"]["INDS3"]["internal_tp_after"] == 12.5
    assert aggregate["private_detail_sha256"] == shadow.canonical_sha256(outputs["private_detail"])

    snapshot_id = shadow.save_shadow_snapshot(database, outputs, published_at=datetime(YEAR, 10, 19, 3, 5, tzinfo=timezone.utc))
    stored = database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY)
    assert stored["id"] == snapshot_id and stored["outputs"]["aggregate"] == aggregate  # JSONB round trip: the hash still recomputes
    assert database.valuation_predictions_for_cycle(snapshot_id, source="official_blend_v1") == {}  # never a prediction record


def test_quantiles_interpolate_linearly() -> None:
    assert shadow.quantile([], 0.5) is None
    assert shadow.quantile([3.0], 0.9) == 3.0
    assert shadow.quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert shadow.quantile([0.0, 10.0], 0.9) == pytest.approx(9.0)


# ------------------------------------------------------------------ the nightly build, end to end
SYMBOLS = [f"{chr(65 + index)}SYN3" for index in range(8)]


class _Http:
    def get_json(self, url: str, *, params: Any = None, headers: Any = None) -> Any:
        return {"results": [{"symbol": symbol, "name": f"Sintetica {index}", "longName": f"Sintetica Teste {index}",
                             "sector": "Utilities" if index % 2 else "Technology Services", "subsector": "Teste"}
                            for index, symbol in enumerate(SYMBOLS)]}


def _service(database: Database) -> Any:
    from app.market_data.b3_screener import B3ScreenerService

    now = datetime.now(timezone.utc)
    settings = Settings(brapi_token="configured", eodhd_api_token="configured", auth_cookie_secure=False)
    service = B3ScreenerService(settings, database, _Http())  # type: ignore[arg-type]
    quotes = {symbol: NormalizedQuote(provider="brapi", symbol=symbol, provider_symbol=symbol, exchange="B3", currency="BRL", price=20 + index,
                                      change_percent=0.1, volume=2_000_000, market_cap=2_000_000_000 + index * 50_000_000, as_of=now,
                                      collected_at=now, quality_score=94)
              for index, symbol in enumerate(SYMBOLS)}
    statistics_payload = {symbol: {"trailingPE": 6.0 + index, "forwardPE": 5.5 + index, "enterpriseToEbitda": 5.0 + index / 2, "priceToBook": 1.0 + index / 10,
                                   "beta": 0.9, "sharesOutstanding": 100_000_000, "marketCap": 2_000_000_000 + index * 50_000_000}
                          for index, symbol in enumerate(SYMBOLS)}
    financial_payload = {symbol: {"returnOnEquity": 0.15, "profitMargins": 0.12, "ebitdaMargins": 0.2, "revenueGrowthAnnual": 0.06,
                                  "earningsGrowthAnnual": 0.07, "freeCashflow": 170_000_000, "operatingCashflow": 210_000_000, "ebitda": 400_000_000,
                                  "totalCash": 250_000_000, "totalDebt": 300_000_000, "debtToEquity": 0.8, "targetMeanPrice": 26.0 + index,
                                  "numberOfAnalystOpinions": 8}
                         for index, symbol in enumerate(SYMBOLS)}
    eodhd = {symbol: {"marketCap": 2_000_000_000 + index * 50_000_000, "trailingPE": 6.0 + index, "enterpriseToEbitda": 5.0 + index / 2,
                      "priceToBook": 1.0 + index / 10, "returnOnEquity": 0.15, "profitMargins": 0.12, "revenueGrowthAnnual": 0.06,
                      "earningsGrowthAnnual": 0.07, "ebitda": 400_000_000.0, "totalRevenue": 2_000_000_000.0, "sharesOutstanding": 100_000_000,
                      "targetMeanPrice": 26.0 + index, "numberOfAnalystOpinions": 8, "financialsAsOf": f"{YEAR}-06-30",
                      "updated_at": date.today().isoformat(),
                      "freeCashflow": 42_500_000.0, "operatingCashflow": 52_500_000.0,  # EODHD's top level: the latest QUARTER
                      "quarterlyIncome": [{"date": period, "totalRevenue": 500_000_000.0, "ebitda": 100_000_000.0, "netIncome": 60_000_000.0}
                                          for period in (f"{YEAR}-06-30", f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30")],
                      "quarterlyCashFlow": [{"date": period, "totalCashFromOperatingActivities": 52_500_000.0, "freeCashFlow": 42_500_000.0}
                                            for period in (f"{YEAR}-06-30", f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30")]}
             for index, symbol in enumerate(SYMBOLS)}
    service._quotes = lambda _: quotes  # type: ignore[method-assign]
    service._fundamental_map = lambda endpoint, _: statistics_payload if endpoint == "statistics" else financial_payload  # type: ignore[method-assign]
    service._historical_map = lambda _: {symbol: {"adtv_90d": 30_000_000, "history_days": 63.0, "volatility_90d": 0.3, "support_60d": 18.0 + index,
                                                  "median_20d": 19.5 + index, "low_20d": 18.5 + index, "last_close": 20.0 + index}
                                         for index, symbol in enumerate(SYMBOLS)}  # type: ignore[method-assign]
    service._macro_context = lambda: {"selic": 0.12, "ipca12m": 0.045}  # type: ignore[method-assign]
    service._eodhd_cache = {symbol: (payload, now) for symbol, payload in eodhd.items()}  # received: no HTTP call is made
    service._eodhd_cache_expires_at = now + timedelta(hours=1)
    for market, symbol in (("NASDAQ", "AAPL"), ("NYSE", "KO")):  # the official selection needs every market recorded once
        database.save_analysis_snapshot("valuation_universe", f"{market}_UNIVERSE", "mv-1", {"methodology_version": 1},
                                        {"rows": [{"symbol": symbol, "our_tp": 250.0, "buy_in": 200.0, "price": 220.0, "internal_tp": 245.0}],
                                         "universe_size": 1}, now - timedelta(minutes=5))
    # the CVM says the first name's EBITDA is twice the provider's (4 complete quarters, stored before the build)
    statements = {
        "market": "B3", "symbol": SYMBOLS[0], "as_of": f"{YEAR}-06-30", "source_name": "CVM Dados Abertos - ITR/DFP consolidado",
        "quarterlyIncome": [{"date": period, "ebitda": 200_000_000.0}
                            for period in (f"{YEAR}-06-30", f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30")],
        "quarterlyCashFlow": [], "quarterlyBalance": [],
        "official_metrics": {"statementScope": "consolidated", "periodDocuments": {f"{YEAR}-06-30": {"document": "ITR", "referenceDate": f"{YEAR}-06-30",
                                                                                                    "version": 1, "receivedOn": f"{YEAR}-08-10"}}},
    }
    save_official_statements(database, [statements])
    return service


def _served(service: Any) -> dict[str, tuple[Any, ...]]:
    return {row["symbol"]: (row.get("our_tp"), row.get("internal_tp"), row.get("buy_in"), row.get("internal_buy_in"), row.get("ebitda"))
            for row in service._matrix_rows}


def test_the_nightly_build_records_one_shadow_snapshot_and_serves_exactly_what_it_served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FIELDWISE_OVERLAY_ENV, raising=False)
    monkeypatch.setenv("C3PO_BUILD_SHA", "e" * 40)
    monkeypatch.delenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, raising=False)
    off_database = _database()
    off = _service(off_database)
    off.screen(refresh=True)
    assert off_database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is None

    monkeypatch.setenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, "true")
    on_database = _database()
    on = _service(on_database)
    on.screen(refresh=True)
    assert _served(on) == _served(off)  # the shadow changes nothing served
    assert all(served[4] == 400_000_000.0 for served in _served(on).values())
    snapshots = [item for item in on_database._analysis_snapshots if item["analysis_type"] == shadow.ANALYSIS_TYPE]
    assert len(snapshots) == 1
    outputs = snapshots[0]["outputs"]
    aggregate = outputs["aggregate"]
    cycle = on_database.latest_analysis_snapshot("valuation_universe", "B3_UNIVERSE")
    assert aggregate["cycle_id"] == cycle["id"] and outputs["producer_build_sha"] == "e" * 40
    assert aggregate["universe"] == len(SYMBOLS) and aggregate["overlay_origin"]["statements"] == 1
    assert aggregate["field_sources"]["ebitda"]["cvm"] == 1 and aggregate["field_sources"]["ebitda"]["eodhd"] == len(SYMBOLS) - 1
    assert aggregate["ebitda"]["changed"] == 1 and aggregate["ebitda"]["corrected"] == 0  # the provider's figure was not a halved legacy sum
    assert aggregate["names"]["pairs"] == len(on._matrix_rows) and aggregate["internal_tp"]["n"] == len(on._matrix_rows)
    assert aggregate["internal_tp"]["changed"] >= 1  # the corrected EBITDA moves that name's internal TP
    assert not any(symbol in json.dumps(aggregate) for symbol in SYMBOLS)
    assert outputs["private_detail"][SYMBOLS[0]]["ebitda_after"] == 800_000_000.0

    # serving switched on: before and after are the same overlay, the shadow is then an identity check
    monkeypatch.setenv(FIELDWISE_OVERLAY_ENV, "true")
    on.screen(refresh=True)
    identity = on_database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY)["outputs"]["aggregate"]
    assert identity["served_overlay"] == "fieldwise" and identity["internal_tp"]["changed"] == 0 and identity["ebitda"]["changed"] == 0


def test_a_failing_shadow_never_breaks_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FIELDWISE_OVERLAY_ENV, raising=False)
    monkeypatch.setenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, "true")

    def broken(*_: Any, **__: Any) -> Any:
        raise RuntimeError("shadow bug")

    database = _database()
    service = _service(database)
    monkeypatch.setattr(shadow, "build_shadow_outputs", broken)
    response = service.screen(refresh=True)
    assert response.universe_size == len(SYMBOLS) and database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is None
    monkeypatch.setattr(shadow, "official_overlays", broken)  # the capture fails inside the served fetch: still served
    second = _service(_database())
    assert second.screen(refresh=True).universe_size == len(SYMBOLS)
    assert second.database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is None


def test_the_shadow_switch_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, raising=False)
    assert valuation_env.cvm_overlay_shadow_enabled() is False
    for raw, expected in (("true", True), ("TRUE", True), ("false", False), ("", False), ("enabled", False)):
        monkeypatch.setenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, raw)
        assert valuation_env.cvm_overlay_shadow_enabled() is expected


# ------------------------------------------------------------------ the read-only receipt and the workflow
def _workflow_steps() -> dict[str, dict[str, Any]]:
    import yaml

    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    return {step["name"]: step for job in jobs.values() for step in job.get("steps", []) if step.get("name")}


def _runner_script(step: dict[str, Any]) -> str:
    return str(step["run"]).split("<<'PY' || exit 1\n", 1)[1].split("\nPY\n", 1)[0]


def _shadow_database(producer: str = "a" * 40) -> Database:
    database = _database()
    capture = shadow.ShadowCapture()
    provider = {"INDS3": _provider_one_quarter_behind()}
    save_official_statements(database, [_statements()["INDS3"]])
    capture.add(database, provider, provider, served_overlay="legacy")
    outputs = shadow.build_shadow_outputs(
        capture, served_rows=[{"symbol": "INDS3", "internal_tp": 10.0, "internal_buy_in": 8.0}],
        shadow_rows=[{"symbol": "INDS3", "internal_tp": 11.0, "internal_buy_in": 8.5}], universe_symbols=["INDS3"],
        cycle_id="00000000-0000-4000-8000-000000000002", basis_at=datetime(YEAR, 10, 19, 3, tzinfo=timezone.utc), producer_build_sha=producer)
    shadow.save_shadow_snapshot(database, outputs, published_at=datetime(YEAR, 10, 19, 3, 5, tzinfo=timezone.utc))
    return database


def test_the_receipt_rehashes_the_stored_aggregate_and_binds_both_builds() -> None:
    database = _shadow_database()
    receipt = shadow.before_after_receipt(database, reader_build_sha="b" * 40)
    assert set(receipt) == set(shadow.AGGREGATE_KEYS) | set(shadow.ATTESTATION_KEYS)
    assert receipt["producer_build_sha"] == "a" * 40 and receipt["reader_build_sha"] == "b" * 40
    assert receipt["receipt_sha256"] == shadow.canonical_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    assert receipt["report_sha256"] == shadow.canonical_sha256({key: receipt[key] for key in shadow.AGGREGATE_KEYS})
    assert "INDS3" not in json.dumps(receipt)
    markdown = shadow.before_after_markdown(receipt)
    assert receipt["report_sha256"] in markdown and receipt["receipt_sha256"] in markdown and "a" * 40 in markdown and "INDS3" not in markdown

    database._analysis_snapshots[-1]["outputs"]["aggregate"]["universe"] = 99  # altered after the producer hashed it
    with pytest.raises(ValueError, match="does not recompute"):
        shadow.before_after_receipt(database, reader_build_sha="b" * 40)
    with pytest.raises(LookupError):
        shadow.before_after_receipt(_database(), reader_build_sha="b" * 40)


def test_the_readonly_workflow_publishes_the_cvm_receipt_aggregate_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    """``report=cvm-before-after``: the CLI's receipt passes the workflow's own verifier, the second read-only exec renders
    the summary from it alone, and the summary verifier binds it to the verified hashes and to the SAME deployed build that
    read the receipt; a deploy between the two execs, a tampered or re-attributed receipt, or a symbol-keyed block are
    refused before anything is uploaded. Each script runs here as the workflow file carries it."""
    steps = _workflow_steps()
    database = _shadow_database(producer="a" * 40)
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(database_url="", auth_cookie_secure=False))
    monkeypatch.setattr("app.database.Database", lambda settings: database)
    reader = "b" * 40
    monkeypatch.setenv("C3PO_BUILD_SHA", reader)
    assert shadow.main(["--before-after"]) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n") == 1 and "INDS3" not in printed

    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    out.mkdir()
    verify = _runner_script(steps["Verify the CVM before/after receipt and keep the aggregate only"])

    def verified(text: str) -> subprocess.CompletedProcess[str]:
        (raw / "cvm_before_after.json").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, "-", str(raw / "cvm_before_after.json"), str(out)], input=verify, text=True, capture_output=True)

    accepted = verified(printed)
    assert accepted.returncode == 0, accepted.stderr
    receipt = json.loads(printed)
    assert json.loads((out / "report.json").read_text(encoding="utf-8")) == receipt

    remote = str(steps["Render the CVM Portuguese summary in the running api container, read-only"]["run"])
    render = remote.split("render='", 1)[1].split("'\n", 1)[0]

    def rendered_under(build: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-c", render], input=(out / "report.json").read_text(encoding="utf-8"), text=True, capture_output=True,
                              cwd=BACKEND, env={**os.environ, "PYTHONPATH": str(BACKEND), "C3PO_BUILD_SHA": build})

    rendered = rendered_under(reader)
    assert rendered.returncode == 0, rendered.stderr
    assert json.loads(rendered.stdout) == {"markdown": shadow.before_after_markdown(receipt), "renderer_build_sha": reader}
    summarize = _runner_script(steps["Verify the CVM summary and keep aggregates only"])
    env = {**os.environ, "RUN_ID": "7", "REVISION": "c" * 40, "GITHUB_STEP_SUMMARY": str(tmp_path / "step_summary.md")}

    def summarized(text: str) -> subprocess.CompletedProcess[str]:
        (raw / "cvm_summary.json").write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, "-", str(raw / "cvm_summary.json"), str(out)], input=summarize, text=True, capture_output=True, env=env)

    done = summarized(rendered.stdout)
    assert done.returncode == 0, done.stderr
    metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["producer_build_sha"] == "a" * 40 and metadata["reader_build_sha"] == reader and metadata["report"] == "cvm-before-after"
    assert metadata["report_sha256"] == receipt["report_sha256"] and metadata["receipt_sha256"] == receipt["receipt_sha256"]
    published = [path.read_text(encoding="utf-8") for path in out.iterdir()] + [(tmp_path / "step_summary.md").read_text(encoding="utf-8"), done.stdout]
    assert not any("INDS3" in text for text in published)

    def reattested(changes: dict[str, Any]) -> str:
        body = {key: value for key, value in {**receipt, **changes}.items() if key != "receipt_sha256"}
        return json.dumps({**body, "receipt_sha256": shadow.canonical_sha256(body)})

    keyed = {**receipt, "names": {**receipt["names"], "INDS3": 1}}
    for text, message in (
        (json.dumps({**receipt, "detail": {"INDS3": {}}}), "keys are not exactly the aggregate's"),
        (json.dumps(keyed), "unexpected names block"),
        (json.dumps({**receipt, "field_sources": {**receipt["field_sources"], "INDS3": {"cvm": 1, "eodhd": 0, "mixed": 0, "absent": 0}}}),
         "unexpected field_sources block"),
        (json.dumps({**receipt, "universe": receipt["universe"] + 1}), "report_sha256 does not recompute"),
        (reattested({"universe": receipt["universe"] + 1}), "report_sha256 does not recompute"),
        (json.dumps({**receipt, "producer_build_sha": "d" * 40}), "receipt_sha256 does not recompute"),
        (reattested({"producer_build_sha": "development"}), "not a commit sha"),
        (reattested({"reader_build_sha": None}), "not a commit sha"),
        (json.dumps({**receipt, "schema": "VALUATION_P1_BEFORE_AFTER_V3"}), "not the CVM overlay receipt V1"),
        ("not json", "not a single JSON document"),
        (" " * 70000, "larger than an aggregate"),
    ):
        refused = verified(text)
        assert refused.returncode != 0 and message in refused.stderr, (message, refused.stderr)
        assert "INDS3" not in refused.stdout + refused.stderr
    assert verified(printed).returncode == 0

    (tmp_path / "step_summary.md").unlink()
    (out / "metadata.json").unlink()
    (out / "summary.md").unlink()
    race = summarized(rendered_under("d" * 40).stdout)  # a deploy between the receipt and its summary
    assert race.returncode != 0 and "the deployed build changed between the receipt and its summary" in race.stderr
    assert not (out / "metadata.json").exists() and not (tmp_path / "step_summary.md").exists()
    other = summarized(json.dumps({"markdown": shadow.before_after_markdown({**receipt, "report_sha256": "f" * 64}), "renderer_build_sha": reader}))
    assert other.returncode != 0 and "not rendered from this receipt" in other.stderr


def test_the_cvm_mode_is_gated_read_only_and_needs_no_new_secret() -> None:
    import re

    import yaml

    text = WORKFLOW.read_text(encoding="utf-8")
    report_input = yaml.safe_load(text)[True]["workflow_dispatch"]["inputs"]["report"]
    assert report_input["default"] == "accuracy" and "cvm-before-after" in report_input["options"]
    steps = _workflow_steps()
    names = ("Run the CVM before/after receipt in the running api container, read-only", "Verify the CVM before/after receipt and keep the aggregate only",
             "Render the CVM Portuguese summary in the running api container, read-only", "Verify the CVM summary and keep aggregates only",
             "Publish the CVM before/after receipt")
    for name in names:
        assert steps[name]["if"] == "steps.inputs.outputs.report == 'cvm-before-after'"
    for name in (names[0], names[2]):
        run = str(steps[name]["run"])
        assert "exec -T \\\n  -e 'PGOPTIONS=-c default_transaction_read_only=on' \\\n  api python" in run
        assert "/run/c3po-security/reboot.pending" in run and "remote stderr lines (kept private, not printed)" in run
    assert "api python -m app.valuation_cvm_overlay_shadow --before-after </dev/null" in str(steps[names[0]]["run"])
    assert steps[names[4]]["with"]["path"] == "${{ runner.temp }}/valuation-cvm-before-after"
    assert sorted(set(re.findall(r"secrets\.([A-Z0-9_]+)", text))) == ["C3PO_AWS_HOST", "C3PO_AWS_KNOWN_HOSTS", "C3PO_AWS_SSH_KEY", "C3PO_AWS_USER"]
    verifier = _runner_script(steps[names[1]])
    assert all(f'"{key}"' in verifier for key in (*shadow.AGGREGATE_KEYS, *shadow.ATTESTATION_KEYS, *SOURCE_FIELDS))
