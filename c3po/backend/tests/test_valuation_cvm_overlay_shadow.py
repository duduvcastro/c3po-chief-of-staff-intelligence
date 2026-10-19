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
    available_at,
    fieldwise_sources,
    official_overlays,
    provider_cash_flow_ttm,
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


Q = [f"{YEAR}-06-30", f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30"]


def _cash_flow_provider(values: tuple[float, ...], dates: list[str] = Q, **extra: Any) -> dict[str, Any]:
    """Reviewer probe (rv-cvm1/probe_numbers.py): EODHD-shaped, top-level cash flow = the latest QUARTER."""
    return {"financialsAsOf": dates[0], "marketCap": 1e9, "sharesOutstanding": 1e6, "ebitda": 4e8, "freeCashflow": values[0],
            "operatingCashflow": values[0] * 2,
            "quarterlyIncome": [{"date": period, "totalRevenue": 100.0, "ebitda": 25.0, "netIncome": 10.0} for period in Q],
            "quarterlyCashFlow": [{"date": period, "freeCashFlow": value, "totalCashFromOperatingActivities": value * 2}
                                  for period, value in zip(dates, values)],
            "quarterlyBalance": [], **extra}


def test_the_provider_ttm_guard_refuses_year_to_date_rows() -> None:
    """MAJOR of the review: if EODHD .SA cash-flow rows were year-to-date (as the CVM DFC is), four of them would sum
    Q1 + H1 + 9M + FY. Probe values 20/10/40/30 (H1, Q1, FY, 9M): served 100 against a true TTM of 30 — now refused."""
    fresh = {"as_of": f"{YEAR}-06-30", "quarterlyIncome": [], "quarterlyCashFlow": [], "quarterlyBalance": []}
    cumulative = _cash_flow_provider((20.0, 10.0, 40.0, 30.0))
    assert provider_cash_flow_ttm(cumulative, "freeCashFlow") == (None, "cumulative")
    from app.official_statements import cash_flow_guard

    assert cash_flow_guard(cumulative, fresh) == {"operatingCashflow": "cumulative", "freeCashflow": "cumulative"}
    with_cvm = {**fresh, "quarterlyCashFlow": [{"date": Q[0], "freeCashFlow": 5.0, "totalCashFromOperatingActivities": 9.0}]}
    assert "freeCashflow" not in apply_official_statements(cumulative, with_cvm)  # nor mixed with year-to-date provider quarters
    served = apply_official_statements(cumulative, fresh)
    assert "freeCashflow" not in served and "operatingCashflow" not in served
    assert fieldwise_sources(cumulative, fresh)["freeCashflow"] == "absent"
    single = _cash_flow_provider((12.0, 9.0, 10.0, 11.0))  # single quarters: no year-to-date pattern (3Q > 4Q)
    assert provider_cash_flow_ttm(single, "freeCashFlow") == (42.0, "complete")
    assert apply_official_statements(single, fresh)["freeCashflow"] == 42.0


def test_a_provider_ttm_ending_at_the_fiscal_year_needs_the_annual_figure_within_five_percent() -> None:
    december = [f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30", f"{PREVIOUS}-06-30", f"{PREVIOUS}-03-31"]
    rows = (12.0, 9.0, 11.0, 10.0)
    no_annual = _cash_flow_provider(rows, december)
    assert provider_cash_flow_ttm(no_annual, "freeCashFlow") == (None, "annual_missing")  # today's normalized payload carries none
    agreeing = _cash_flow_provider(rows, december, annualCashFlow=[{"date": f"{PREVIOUS}-12-31", "freeCashFlow": 43.0}])
    assert provider_cash_flow_ttm(agreeing, "freeCashFlow") == (42.0, "complete")
    raw = _cash_flow_provider(rows, december, Financials={"Cash_Flow": {"yearly": {f"{PREVIOUS}-12-31": {"freeCashFlow": 42.0}}}})
    assert provider_cash_flow_ttm(raw, "freeCashFlow") == (42.0, "complete")
    far = _cash_flow_provider(rows, december, annualCashFlow=[{"date": f"{PREVIOUS}-12-31", "freeCashFlow": 46.0}])
    assert provider_cash_flow_ttm(far, "freeCashFlow") == (None, "annual_mismatch")
    same_year_rising = _cash_flow_provider((40.0, 30.0, 20.0, 10.0), december)  # Q1..Q4 of one year, rising: year-to-date
    assert provider_cash_flow_ttm(same_year_rising, "freeCashFlow") == (None, "cumulative")


def test_the_quarter_is_not_served_as_a_year_when_the_overlay_does_not_apply() -> None:
    """Reviewer probe (a): with no overlay, or one older than the provider, the provider's quarter used to stay."""
    stale = {"as_of": f"{YEAR}-03-31", "quarterlyIncome": [], "quarterlyCashFlow": [], "quarterlyBalance": []}
    three = _cash_flow_provider((10.0, 10.0, 10.0), Q[:3])
    for overlay in (None, stale):
        served = apply_official_statements(three, overlay)
        assert "freeCashflow" not in served and "operatingCashflow" not in served
        assert fieldwise_sources(three, overlay)["freeCashflow"] == "absent"
    four = _cash_flow_provider((12.0, 9.0, 10.0, 11.0))
    assert apply_official_statements(four, None)["freeCashflow"] == 42.0 and fieldwise_sources(four, None)["freeCashflow"] == "eodhd"


def test_capex_is_labelled_from_the_complete_window_only() -> None:
    """Reviewer probe (b): capexTtm is served only from a complete window (magnitude); otherwise it is absent."""
    fresh = {"as_of": f"{YEAR}-06-30", "quarterlyIncome": [], "quarterlyCashFlow": [], "quarterlyBalance": []}
    three = _cash_flow_provider((10.0, 10.0, 10.0), Q[:3])
    for row in three["quarterlyCashFlow"]:
        row["capitalExpenditures"] = -10.0
    assert apply_official_statements(three, fresh)["officialMetrics"]["capexTtm"] is None
    assert fieldwise_sources(three, fresh)["capexTtm"] == "absent"
    three["quarterlyCashFlow"].append({"date": Q[3], "capitalExpenditures": 10.0})
    assert apply_official_statements(three, fresh)["officialMetrics"]["capexTtm"] == 40.0
    assert fieldwise_sources(three, fresh)["capexTtm"] == "eodhd"
    assert fieldwise_sources(three, None)["capexTtm"] == "absent"  # no overlay: never set


def test_cvm_shares_off_by_a_hundredfold_are_skipped_and_counted(tmp_path: Path) -> None:
    from app.official_statements import shares_scale_skipped

    provider = _provider_one_quarter_behind()
    provider["sharesOutstanding"] = 990_000.0  # the CVM fixture files 990: a thousands/units mix-up
    statements = _statements()["INDS3"]
    served = apply_official_statements(provider, statements)
    assert served["sharesOutstanding"] == 990_000.0 and shares_scale_skipped(provider, statements)
    assert fieldwise_sources(provider, statements)["sharesOutstanding"] == "eodhd"
    provider["sharesOutstanding"] = 1_000.0
    assert apply_official_statements(provider, statements)["sharesOutstanding"] == 990 and not shares_scale_skipped(provider, statements)


def test_a_stale_overlay_is_counted_as_stale_not_as_statements(tmp_path: Path) -> None:
    """Reviewer probe (e): statements older than the provider never apply; the origin says so."""
    database = _database(tmp_path)
    old = copy.deepcopy(_statements()["INDS3"])
    old["as_of"] = f"{YEAR}-03-31"
    save_official_statements(database, [old])
    capture = shadow.ShadowCapture()
    provider = {"INDS3": _cash_flow_provider((12.0, 9.0, 10.0, 11.0))}
    capture.add(database, provider, provider, served_overlay="legacy")
    assert capture.origins == {"INDS3": "stale"} and "officialFundamentals" not in capture.shadow["INDS3"]


def test_a_tiny_negative_ratio_is_never_stored_as_negative_zero(tmp_path: Path) -> None:
    """Reviewer probe (rv-cvm2/negzero.py): ``round(-1e-12, 8)`` is ``-0.0``; PostgreSQL numeric reads it back as ``0.0``,
    the stored aggregate no longer recomputed and the receipt refused its own snapshot."""
    assert json.dumps(shadow.ratio_stats([-1e-12, -1e-12, 0.3])["median"]) == "0.0"
    database = _database(tmp_path)
    capture = shadow.ShadowCapture()
    provider = {"INDS3": _provider_one_quarter_behind()}
    save_official_statements(database, [_statements()["INDS3"]])
    capture.add(database, provider, provider, served_overlay="legacy")
    served = [{"symbol": symbol, "internal_tp": 10.0, "internal_buy_in": 8.0} for symbol in ("INDS3", "X1", "X2")]
    after = [{"symbol": "INDS3", "internal_tp": 10.0 * (1 - 1e-12), "internal_buy_in": 8.0},
             {"symbol": "X1", "internal_tp": 10.0 * (1 - 1e-12), "internal_buy_in": 8.0}, {"symbol": "X2", "internal_tp": 13.0, "internal_buy_in": 8.0}]
    outputs = shadow.build_shadow_outputs(capture, served_rows=served, before_rows=served, cash_flow_fix_rows=served, after_rows=after,
                                          universe_symbols=["INDS3"], cycle_id="00000000-0000-4000-8000-000000000002",
                                          basis_at=datetime(YEAR, 10, 19, 3, tzinfo=timezone.utc), producer_build_sha="a" * 40)
    assert "-0.0" not in json.dumps(outputs["aggregate"])
    shadow.save_shadow_snapshot(database, outputs, published_at=datetime(YEAR, 10, 19, 3, 5, tzinfo=timezone.utc))
    snapshot = database._analysis_snapshots[-1]
    snapshot["outputs"] = json.loads(json.dumps(snapshot["outputs"]).replace("-0.0", "0.0"))  # what PostgreSQL gives back
    assert shadow.before_after_receipt(database, reader_build_sha="b" * 40)["report_sha256"] == outputs["report_sha256"]


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


def _legacy(symbol: str = "INDS3", **extra: Any) -> dict[str, Any]:
    return {"market": "B3", "symbol": symbol, "as_of": f"{YEAR}-06-30", "source_name": "CVM Dados Abertos - ITR consolidado",
            "quarterlyIncome": [{"date": f"{YEAR}-06-30", "totalRevenue": 150_000.0}], "quarterlyCashFlow": [], "quarterlyBalance": [],
            "official_metrics": {}, **extra}


def test_the_receipt_guard_uses_the_end_of_the_receipt_day_in_sao_paulo(tmp_path: Path) -> None:
    """A GUARD, not a point-in-time read: the latest snapshot is refused while it was stored after the cut or while any
    contributing document is not yet available — the END of its CVM receipt day in Sao Paulo, the producer's convention."""
    database = _database(tmp_path)
    stored_at = datetime(YEAR, 8, 3, 12, tzinfo=timezone.utc)
    database.save_analysis_snapshot("official_fundamentals", "B3:INDS3", "mv", {}, _legacy(), stored_at)
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, _statements()["INDS3"], stored_at)
    # 2Q was received on 2 August: available at 2 August 23:59:59.999999 in Sao Paulo (= 3 August 02:59:59 UTC)
    stored = official_overlays(database, ["INDS3"], market="B3", as_of=stored_at)["INDS3"]
    assert stored.origin == "statements" and not stored.receipt_guard_excluded
    same_day = official_overlays(database, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 2, 23, tzinfo=timezone.utc))["INDS3"]
    assert same_day.overlay is None and same_day.receipt_guard_excluded  # 20:00 in Sao Paulo, and nothing was stored yet anyway
    assert available_at(f"{YEAR}-08-02") == datetime(YEAR, 8, 3, 2, 59, 59, 999999, tzinfo=timezone.utc)


def test_every_contributing_document_is_checked_dva_included(tmp_path: Path) -> None:
    database = _database(tmp_path)
    stored_at = datetime(YEAR, 8, 20, 12, tzinfo=timezone.utc)
    database.save_analysis_snapshot("official_fundamentals", "B3:INDS3", "mv", {}, _legacy(), stored_at)
    statements = copy.deepcopy(_statements()["INDS3"])
    period = statements["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"]
    period["contributing"].append({"document": "ITR", "referenceDate": f"{YEAR}-06-30", "version": 3, "receivedOn": f"{YEAR}-08-25"})  # e.g. a DVA re-filed later
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, statements, stored_at)
    excluded = official_overlays(database, ["INDS3"], market="B3", as_of=stored_at + timedelta(hours=1))["INDS3"]
    assert excluded.receipt_guard_excluded and excluded.origin == "legacy"
    assert official_overlays(database, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 26, 3, tzinfo=timezone.utc))["INDS3"].origin == "statements"


def test_a_refused_latest_snapshot_gives_way_to_the_earlier_one_never_to_a_legacy_swing(tmp_path: Path) -> None:
    database = _database(tmp_path)
    first = datetime(YEAR, 8, 5, 12, tzinfo=timezone.utc)
    database.save_analysis_snapshot("official_fundamentals", "B3:INDS3", "mv", {}, _legacy(), first)
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, _statements()["INDS3"], first)
    newer = copy.deepcopy(_statements()["INDS3"])
    newer["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"]["receivedOn"] = f"{YEAR}-09-10"  # received today, stored today
    newer["quarterlyIncome"][0]["ebitda"] = 1.0
    today = datetime(YEAR, 9, 10, 15, tzinfo=timezone.utc)
    database.save_analysis_snapshot("official_statements", "B3:INDS3", "mv", {}, newer, today)
    chosen = official_overlays(database, ["INDS3"], market="B3", as_of=today + timedelta(hours=1))["INDS3"]
    assert chosen.receipt_guard_excluded and chosen.origin == "statements" and chosen.overlay is not None
    assert chosen.overlay["quarterlyIncome"][0]["ebitda"] == 37_000  # the earlier statements, not the new ones, not the legacy rows


def test_a_legacy_snapshot_is_guarded_on_its_own_receipt(tmp_path: Path) -> None:
    """Reviewer probe (d): statements with a future receipt fell back to a legacy snapshot whose receipt was never checked."""
    database = _database(tmp_path)
    future = copy.deepcopy(_statements()["INDS3"])
    future["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"]["receivedOn"] = "2099-01-01"
    save_official_statements(database, [future])
    save_official_fundamentals(database, [_legacy(published_at="2099-01-01T12:00:00+00:00")])
    chosen = official_overlays(database, ["INDS3"], market="B3")["INDS3"]
    assert chosen.receipt_guard_excluded and chosen.overlay is None and chosen.origin is None
    date_only = _database(tmp_path)
    date_only.save_analysis_snapshot("official_fundamentals", "B3:INDS3", "mv", {}, _legacy(published_at=f"{YEAR}-08-02"),
                                     datetime(YEAR, 8, 1, tzinfo=timezone.utc))
    assert official_overlays(date_only, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 2, 20, tzinfo=timezone.utc))["INDS3"].overlay is None
    assert official_overlays(date_only, ["INDS3"], market="B3", as_of=datetime(YEAR, 8, 3, 3, tzinfo=timezone.utc))["INDS3"].origin == "legacy"


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
    before_rows = [*served_rows[:2], {"symbol": "GONE3", "internal_tp": 5.5, "internal_buy_in": 4.0}]  # GONE3 moved since the cycle
    fix_rows = [{"symbol": "INDS3", "internal_tp": 11.0, "internal_buy_in": 8.5}, served_rows[1]]
    after_rows = [{"symbol": "INDS3", "internal_tp": 12.5, "internal_buy_in": 9.0, "internal_tp_validation_status": "review_required"},
                  {"symbol": "PLAIN3", "internal_tp": 20.0, "internal_buy_in": 16.0, "internal_tp_validation_status": "validated"}]
    outputs = shadow.build_shadow_outputs(capture, served_rows=served_rows, before_rows=before_rows, cash_flow_fix_rows=fix_rows,
                                          after_rows=after_rows, universe_symbols=["INDS3", "PLAIN3"],
                                          cycle_id="00000000-0000-4000-8000-000000000001", basis_at=datetime(YEAR, 10, 19, 3, tzinfo=timezone.utc),
                                          producer_build_sha="a" * 40)
    aggregate = outputs["aggregate"]
    assert tuple(aggregate) == shadow.AGGREGATE_KEYS and outputs["report_sha256"] == shadow.canonical_sha256(aggregate)
    text = json.dumps(aggregate)
    assert not any(symbol in text for symbol in ("INDS3", "PLAIN3", "GONE3"))
    assert aggregate["names"] == {"served_rows": 3, "before": 3, "before_matches_served": 2, "after": 2, "pairs": 2, "only_before": 1, "only_after": 0}
    assert aggregate["internal_tp"]["n"] == 2 and aggregate["internal_tp"]["changed"] == 1 and aggregate["internal_tp"]["over_20_percent"] == 1
    assert aggregate["internal_tp"]["median"] == pytest.approx(0.125) and aggregate["internal_tp"]["p90"] == pytest.approx(0.225)
    assert aggregate["internal_buy_in"]["abs_p90"] == pytest.approx(0.1125)
    assert aggregate["internal_validation"] == {"before_validated": 2, "after_validated": 1, "changed": 1}
    # the decomposition: INDS3 10 -> 11 by the cash-flow fix alone, 11 -> 12.5 by the CVM rows
    assert aggregate["cash_flow_fix_internal_tp"]["median"] == pytest.approx(0.05) and aggregate["cash_flow_fix_internal_tp"]["n"] == 2
    assert aggregate["cvm_rows_internal_tp"]["p90"] == pytest.approx((12.5 / 11 - 1) * 0.9)
    assert aggregate["ebitda"] == {"changed": 1, "legacy_partial_window": 1, "corrected": 1}
    assert aggregate["field_sources"]["ebitda"] == {"cvm": 1, "eodhd": 1, "mixed": 0, "absent": 0}
    assert aggregate["overlay_origin"] == {"statements": 1, "legacy": 0, "stale": 0, "none": 1} and aggregate["served_overlay"] == "legacy"
    assert aggregate["shares_scale_skipped"] == 0  # 990 CVM shares against 1,000 provider shares
    assert aggregate["cash_flow_guard"] == {"cumulative": 0, "annual_missing": 0, "annual_mismatch": 0}
    assert outputs["private_detail"]["INDS3"]["internal_tp_after"] == 12.5
    assert aggregate["private_detail_sha256"] == shadow.canonical_sha256(outputs["private_detail"])

    snapshot_id = shadow.save_shadow_snapshot(database, outputs, published_at=datetime(YEAR, 10, 19, 3, 5, tzinfo=timezone.utc))
    stored = database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY)
    assert stored["id"] == snapshot_id and stored["outputs"]["aggregate"] == aggregate  # JSONB round trip: the hash still recomputes
    assert outputs["private_detail"]["INDS3"]["internal_tp_fix"] == 11.0 and outputs["private_detail"]["INDS3"]["internal_tp_served"] == 10.0
    assert outputs["attestation_sha256"] == shadow.canonical_sha256({"aggregate": aggregate, "producer_build_sha": "a" * 40})
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


def _service(database: Database, *, nightly: bool = True) -> Any:
    from app.market_data.b3_screener import B3ScreenerService

    now = datetime.now(timezone.utc)
    settings = Settings(brapi_token="configured", eodhd_api_token="configured", auth_cookie_secure=False)
    service = B3ScreenerService(settings, database, _Http(), nightly_cvm_shadow=nightly)  # type: ignore[arg-type]
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
    assert aggregate["names"]["before_matches_served"] == aggregate["names"]["served_rows"] == len(on._matrix_rows)  # same moment, same rows
    assert aggregate["cash_flow_fix_internal_tp"]["n"] == len(on._matrix_rows)
    assert aggregate["internal_tp"]["changed"] >= 1  # the corrected EBITDA moves that name's internal TP
    assert not any(symbol in json.dumps(aggregate) for symbol in SYMBOLS)
    assert outputs["private_detail"][SYMBOLS[0]]["ebitda_after"] == 800_000_000.0

    # serving switched on: before and after are the same overlay, the shadow is then an identity check
    monkeypatch.setenv(FIELDWISE_OVERLAY_ENV, "true")
    on.screen(refresh=True)
    identity = on_database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY)["outputs"]["aggregate"]
    assert identity["served_overlay"] == "fieldwise" and identity["internal_tp"]["changed"] == 0 and identity["ebitda"]["changed"] == 0
    assert identity["names"]["before_matches_served"] == identity["names"]["served_rows"]


def test_the_shadow_runs_only_in_the_nightly_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not in another process's full build (the IR worker's screener is not the nightly producer), and not in
    refresh_symbols' cold build even in the valuation worker."""
    monkeypatch.delenv(FIELDWISE_OVERLAY_ENV, raising=False)
    monkeypatch.setenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, "true")
    other = _service(_database(), nightly=False)
    other.screen(refresh=True)
    assert other.database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is None
    nightly = _service(_database())
    nightly._build_targeted_valuation = lambda symbol: None  # type: ignore[method-assign]
    nightly.refresh_symbols([SYMBOLS[0]])  # no matrix yet: a cold full build on behalf of one symbol
    assert nightly._matrix_rows and nightly.database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is None
    nightly.screen(refresh=True)
    assert nightly.database.latest_analysis_snapshot(shadow.ANALYSIS_TYPE, shadow.ENTITY_KEY) is not None


def test_with_the_shadow_on_everything_served_and_stored_is_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reviewer probe (identity): the response, the matrix rows, every other snapshot and the prediction records are the
    same with the shadow on and off, field for field (instants and ids aside); the shadow adds exactly one snapshot."""
    volatile = {"generated_at", "appliedAt", "published_at", "prediction_instant", "id", "cycle_id", "basis_at", "row_sha256",
                "consensus_published_at", "as_of", "payload_sha256", "source_manifest_sha256", "official_cycle_id", "official_generation_id",
                "activated_at", "generation_id", "snapshot_id", "applied_at", "updated_at"}

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in sorted(value.items()) if key not in volatile}
        if isinstance(value, (list, tuple)):
            return [scrub(item) for item in value]
        return value

    def run(on: bool) -> tuple[str, int]:
        monkeypatch.setenv(valuation_env.CVM_OVERLAY_SHADOW_ENV, "true" if on else "")
        database = _database()
        service = _service(database)
        response = service.screen(refresh=True)
        snapshots = [(item["analysis_type"], item["entity_key"], item["outputs"]) for item in database._analysis_snapshots
                     if item["analysis_type"] != shadow.ANALYSIS_TYPE]
        predictions = getattr(database, "_valuation_predictions", None)
        state = scrub([json.loads(response.model_dump_json()), service._matrix_rows, snapshots, list(predictions) if predictions is not None else None])
        return json.dumps(state, sort_keys=True, default=str), len(database._analysis_snapshots)

    monkeypatch.delenv(FIELDWISE_OVERLAY_ENV, raising=False)
    (off, off_count), (on, on_count) = run(False), run(True)
    assert on == off and on_count == off_count + 1


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
    served = [{"symbol": "INDS3", "internal_tp": 10.0, "internal_buy_in": 8.0}]
    outputs = shadow.build_shadow_outputs(
        capture, served_rows=served, before_rows=served, cash_flow_fix_rows=served,
        after_rows=[{"symbol": "INDS3", "internal_tp": 11.0, "internal_buy_in": 8.5}], universe_symbols=["INDS3"],
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

    database._analysis_snapshots[-1]["outputs"]["producer_build_sha"] = "d" * 40  # re-attributed after it was stored
    with pytest.raises(ValueError, match="attestation_sha256"):
        shadow.before_after_receipt(database, reader_build_sha="b" * 40)
    database._analysis_snapshots[-1]["outputs"]["producer_build_sha"] = "a" * 40
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
    smuggled_bool = {**receipt, "field_sources": {**receipt["field_sources"], "ebitda": {**receipt["field_sources"]["ebitda"], "cvm": True}}}
    for text, message in (
        (json.dumps({**receipt, "detail": {"INDS3": {}}}), "keys are not exactly the aggregate's"),
        (json.dumps(keyed), "unexpected names block"),
        (reattested({"field_sources": smuggled_bool["field_sources"]}), "unexpected field_sources block"),
        (reattested({"ebitda": {**receipt["ebitda"], "changed": True}}), "unexpected ebitda block"),
        (reattested({"served_overlay": "PETR4"}), "unexpected overlay names"),
        (reattested({"cycle_id": "PETR4"}), "not a snapshot id"),
        (reattested({"basis_at": receipt["basis_at"] + " PETR4"}), "not an ISO-8601 instant"),
        (reattested({"statements_as_of": receipt["statements_as_of"] + "\nPETR4"}), "not an ISO-8601 instant"),
        (reattested({"universe": "PETR4"}), "not a count"),
        (reattested({"internal_tp": {**receipt["internal_tp"], "median": ["PETR4"]}}), "unexpected internal_tp block"),
        (json.dumps({**receipt, "field_sources": {**receipt["field_sources"], "INDS3": {"cvm": 1, "eodhd": 0, "mixed": 0, "absent": 0}}}),
         "unexpected field_sources block"),
        (json.dumps({**receipt, "universe": receipt["universe"] + 1}), "report_sha256 does not recompute"),
        (reattested({"universe": receipt["universe"] + 1}), "report_sha256 does not recompute"),
        (json.dumps({**receipt, "producer_build_sha": "d" * 40}), "receipt_sha256 does not recompute"),
        (reattested({"producer_build_sha": "development"}), "not a commit sha"),
        (reattested({"reader_build_sha": None}), "not a commit sha"),
        (json.dumps({**receipt, "schema": "VALUATION_P1_BEFORE_AFTER_V3"}), "not the CVM overlay receipt V2"),
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
