from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.cvm_fundamentals import (
    CvmPackage,
    _quarterly_flows,
    extract_cvm_official_statements,
    scan_cvm_package,
)
from cvm_statement_fixtures import BANK, INDUSTRY, ISSUERS, SERVICES, build_packages

YEAR = 2026
PREVIOUS = YEAR - 1


def statements(year: int = YEAR, sink=None) -> dict[str, dict]:
    packages = build_packages(year)
    scans = [
        scan_cvm_package(CvmPackage(kind, package_year, package.payload(), f"https://example.invalid/{kind}/{package_year}.zip"), ISSUERS, vintage_sink=sink)
        for (kind, package_year), package in packages.items()
    ]
    return {payload["symbol"]: payload for payload in extract_cvm_official_statements(scans, issuers=ISSUERS)}


def by_date(rows: list[dict]) -> dict[str, dict]:
    return {row["date"]: row for row in rows}


def test_complete_statements_quarterize_itr_and_derive_q4_from_dfp() -> None:
    payload = statements()["INDS3"]
    income = by_date(payload["quarterlyIncome"])

    assert payload["as_of"] == f"{YEAR}-06-30"
    assert [row["date"] for row in payload["quarterlyIncome"]] == [
        f"{YEAR}-06-30", f"{YEAR}-03-31", f"{PREVIOUS}-12-31", f"{PREVIOUS}-09-30", f"{PREVIOUS}-06-30", f"{PREVIOUS}-03-31",
    ]
    assert {period: row["totalRevenue"] for period, row in income.items()} == {
        f"{YEAR}-06-30": 150_000, f"{YEAR}-03-31": 140_000, f"{PREVIOUS}-12-31": 130_000,
        f"{PREVIOUS}-09-30": 120_000, f"{PREVIOUS}-06-30": 110_000, f"{PREVIOUS}-03-31": 100_000,
    }
    # Q4 = DFP year minus ITR nine months; EBITDA = EBIT + |DVA D&A|
    assert income[f"{PREVIOUS}-12-31"]["operatingIncome"] == 26_000
    assert income[f"{PREVIOUS}-12-31"]["depreciationAndAmortization"] == 6_000
    assert income[f"{PREVIOUS}-12-31"]["ebitda"] == 32_000
    assert income[f"{YEAR}-06-30"]["ebitda"] == 37_000
    # net income is the controllers' share; the consolidated total is not kept as a separate field
    assert income[f"{YEAR}-06-30"]["netIncome"] == 15_000
    assert "consolidatedNetIncome" not in income[f"{YEAR}-06-30"]
    assert income[f"{YEAR}-06-30"]["grossProfit"] == pytest.approx(60_000)
    assert income[f"{YEAR}-06-30"]["incomeBeforeTax"] == 30_000  # the fixture files a fixed -4 financial result per cumulative row

    cash = by_date(payload["quarterlyCashFlow"])
    assert cash[f"{YEAR}-06-30"]["totalCashFromOperatingActivities"] == 20_000
    assert cash[f"{YEAR}-06-30"]["capitalExpenditures"] == -11_000  # PP&E + intangibles; disposals and treasury excluded
    assert cash[f"{YEAR}-06-30"]["freeCashFlow"] == 9_000
    assert cash[f"{PREVIOUS}-12-31"]["capitalExpenditures"] == -9_000

    balance = by_date(payload["quarterlyBalance"])
    assert balance[f"{YEAR}-06-30"] == {
        "date": f"{YEAR}-06-30", "totalAssets": 1_000_000, "cash": 52_000, "cashAndShortTermInvestments": 82_000,
        "shortLongTermDebtTotal": 100_000, "totalEquity": 500_000, "totalStockholderEquity": 475_000,
    }
    assert f"{PREVIOUS}-12-31" in balance
    assert payload["sharesOutstanding"] == 990
    metrics = payload["official_metrics"]
    assert metrics["statementScope"] == "consolidated"
    assert metrics["companyEvBalance"] == {"asOf": f"{YEAR}-06-30", "totalCash": 82_000, "totalDebt": 100_000}
    assert metrics["shareCapitalComposition"]["asOf"] == f"{YEAR}-06-30"


def test_own_filing_wins_over_restated_comparative_and_latest_version_dates_publication() -> None:
    payload = statements()["INDS3"]
    income = by_date(payload["quarterlyIncome"])

    # the Q2 ITR comparative restated last year's first half (+5); the as-filed Q2 of last year stays 110
    assert income[f"{PREVIOUS}-06-30"]["totalRevenue"] == 110_000
    documents = payload["official_metrics"]["periodDocuments"]
    assert documents[f"{YEAR}-06-30"] == {
        "document": "ITR", "referenceDate": f"{YEAR}-06-30", "version": 2,
        "sourceUrl": f"https://example.invalid/itr/{YEAR}.zip", "receivedOn": f"{YEAR}-08-02",
    }
    assert documents[f"{PREVIOUS}-12-31"]["document"] == "DFP"
    assert payload["published_at"] == datetime(YEAR, 8, 2, tzinfo=payload_tz(payload)).isoformat()
    assert payload["source_name"] == "CVM Dados Abertos - ITR/DFP consolidado"


def payload_tz(payload: dict):
    return datetime.fromisoformat(payload["published_at"]).tzinfo


def test_individual_statements_only_when_the_issuer_files_no_consolidated_ones() -> None:
    payloads = statements()
    industry = by_date(payloads["INDS3"]["quarterlyIncome"])
    services = payloads["SERV3"]

    # the industrial issuer's individual DRE is doubled in the fixture: it must never leak into the consolidated read
    assert industry[f"{YEAR}-06-30"]["totalRevenue"] == 150_000
    assert services["official_metrics"]["statementScope"] == "individual"
    assert services["source_name"].endswith("individual")
    services_income = by_date(services["quarterlyIncome"])
    assert services_income[f"{YEAR}-06-30"]["netIncome"] == 15_000
    assert services_income[f"{YEAR}-06-30"]["ebitda"] == 37_000
    balance = by_date(services["quarterlyBalance"])[f"{YEAR}-06-30"]
    assert balance["totalStockholderEquity"] == balance["totalEquity"] == 500_000


def test_bank_layout_never_lands_in_industrial_fields() -> None:
    bank = statements()["BSIN3"]
    income = by_date(bank["quarterlyIncome"])[f"{YEAR}-06-30"]

    # 3.05 is pre-tax income in a bank layout; 3.01 is gross financial intermediation
    assert "operatingIncome" not in income
    assert "totalRevenue" not in income
    assert "ebitda" not in income
    assert income["incomeBeforeTax"] == 120_000
    assert income["netIncome"] == 78_000
    balance = by_date(bank["quarterlyBalance"])[f"{YEAR}-06-30"]
    # 2.02.01 is deposits and 2.03 provisions here: neither is debt nor equity
    assert "shortLongTermDebtTotal" not in balance
    assert balance["totalEquity"] == 800_000
    assert "totalStockholderEquity" not in balance  # consolidated without a minority line: left to totalEquity
    assert bank["official_metrics"]["companyEvBalance"] is None


def test_a_missing_prior_cumulative_never_becomes_a_longer_quarter() -> None:
    spans = {
        (f"{YEAR}-01-01", f"{YEAR}-06-30"): {"totalRevenue": 290.0, "netIncome": 29.0},
        (f"{YEAR}-04-01", f"{YEAR}-06-30"): {"totalRevenue": 150.0},
        (f"{YEAR}-01-01", f"{YEAR}-09-30"): {"totalRevenue": 450.0},
        (f"{YEAR}-07-01", f"{YEAR}-03-31"): {"totalRevenue": 999.0},  # another fiscal calendar: ignored
    }

    quarters = _quarterly_flows(spans)

    # no Q1 cumulative: Q2 comes only from its standalone row, and netIncome (no standalone) is absent, not 6 months
    assert quarters[f"{YEAR}-06-30"] == {"totalRevenue": 150.0}
    assert quarters[f"{YEAR}-09-30"] == {"totalRevenue": 160.0}
    assert set(quarters) == {f"{YEAR}-06-30", f"{YEAR}-09-30"}


def test_ambiguous_accounts_are_left_out() -> None:
    from app.cvm_fundamentals import INCOME_CONCEPTS, _resolve_concepts

    resolved = _resolve_concepts(
        {"operatingIncome": {"3.05": 10.0, "3.07": 12.0}, "totalRevenue": {"3.01": 100.0}},
        INCOME_CONCEPTS,
    )

    assert resolved == {"totalRevenue": 100.0}


def test_vintage_batches_carry_raw_level_two_rows_of_the_chosen_scope() -> None:
    batches: list = []
    statements(sink=batches.append)

    rows: dict = {}
    for batch in batches:
        for document, document_rows in batch.rows.items():
            rows.setdefault((batch.statement, *document), []).extend(document_rows)
    q2 = (INDUSTRY["tax_id"], f"{YEAR}-06-30", 2)
    assert {key[0] for key in rows if key[1:] == q2} == {"DRE_con", "DVA_con", "DFC_MI_con", "BPA_con", "BPP_con", "composicao_capital"}
    dre = rows[("DRE_con", *q2)]
    assert ["ÚLTIMO", f"{YEAR}-01-01", f"{YEAR}-06-30", "3.01", "Receita de Venda de Bens e/ou Serviços", "290", "MIL", "REAL", "S"] in dre
    assert any(row[0] == "PENÚLTIMO" for row in dre)  # comparatives are part of the filing as delivered
    assert not any(row[3] == "3.99.01.01" for row in dre)  # deeper than level 2: not kept
    assert not any(row[3] == "6.01.01.02" for row in rows[("DFC_MI_con", *q2)])
    # the consolidated filer's individual DRE is never read; the individual-only issuer's is
    assert not any(key[0] == "DRE_ind" and key[1] == INDUSTRY["tax_id"] for key in rows)
    assert any(key[0] == "DRE_ind" and key[1] == SERVICES["tax_id"] for key in rows)
    assert any(key[1] == BANK["tax_id"] for key in rows)


def test_vintage_batches_are_bounded_and_lose_nothing(monkeypatch) -> None:
    def collect() -> tuple[int, dict]:
        batches: list = []
        statements(sink=batches.append)
        merged: dict = {}
        for batch in batches:
            for document, document_rows in batch.rows.items():
                merged.setdefault((batch.statement, *document), []).extend(document_rows)
        return len(batches), merged

    whole_count, whole = collect()
    monkeypatch.setattr("app.cvm_fundamentals.VINTAGE_FLUSH_ROWS", 5)
    split_count, split = collect()

    assert split_count > whole_count
    assert {key: sorted(value) for key, value in split.items()} == {key: sorted(value) for key, value in whole.items()}


def test_unmapped_issuers_are_neither_read_nor_captured() -> None:
    batches: list = []
    packages = build_packages(YEAR)
    only_services = {SERVICES["tax_id"]: ISSUERS[SERVICES["tax_id"]]}
    scans = [
        scan_cvm_package(CvmPackage(kind, year, package.payload(), "https://example.invalid"), only_services, vintage_sink=batches.append)
        for (kind, year), package in packages.items()
    ]

    payloads = extract_cvm_official_statements(scans, issuers=only_services)

    assert [payload["symbol"] for payload in payloads] == ["SERV3"]
    assert {document[0] for batch in batches for document in batch.rows} == {SERVICES["tax_id"]}


def test_sync_cvm_statements_saves_its_own_analysis_type_and_reports_skipped_vintages(tmp_path, monkeypatch) -> None:
    from app.database import Database
    from app.investor_relations import SAO_PAULO, InvestorRelationsService, normalize_company_name
    from app.official_fundamentals import ANALYSIS_TYPE as LEGACY_ANALYSIS_TYPE
    from app.official_statements import ANALYSIS_TYPE

    settings = Settings(database_url="", migrations_dir=tmp_path, investor_relations_output_dir=tmp_path / "ir-pdf")
    database = Database(settings)
    ir = InvestorRelationsService(settings, database)
    for company, symbols in ((INDUSTRY, ["INDS3", "INDS4"]), (SERVICES, ["SERV3"])):
        for symbol in symbols:
            database.register_ir_securities([{
                "market": "B3", "symbol": symbol, "company_name": company["name"],
                "name_key": normalize_company_name(company["name"]), "regulator_id": company["code"],
                "tax_id": company["tax_id"], "exchange": "B3",
            }])
    year = datetime.now(SAO_PAULO).year
    packages = build_packages(year)
    requested: list[tuple[str, int]] = []

    def package(kind, package_year, cutoff):
        requested.append((kind, package_year))
        fixture = packages.get((kind, package_year))
        if fixture is None:
            return [], b"", f"https://example.invalid/{kind}/{package_year}.zip"
        return fixture.index, fixture.payload(), f"https://example.invalid/{kind}/{package_year}.zip"

    monkeypatch.setattr(ir, "_cvm_structured_package", package)

    records_read, written = ir.sync_cvm_statements()

    assert requested == [("dfp", year - 2), ("itr", year - 1), ("dfp", year - 1), ("itr", year)]  # oldest filings first
    assert written == 3  # INDS3, INDS4, SERV3: the bank is not mapped to a symbol here
    assert records_read == sum(len(fixture.index) for fixture in packages.values())
    snapshot = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3:INDS3")
    assert snapshot["outputs"]["quarterlyIncome"][0]["ebitda"] == 37_000
    assert database.latest_analysis_snapshot(LEGACY_ANALYSIS_TYPE, "B3:INDS3") is None  # the legacy overlay is untouched
    run = next(run for run in database._ingestion_runs.values() if run["source_code"] == "cvm_statements")
    assert run["status"] == "succeeded"
    if importlib.util.find_spec("app.statement_vintages") is None:  # before the 051 front merges: said, not hidden
        assert "store absent" in run["error_summary"]
    else:
        assert run["error_summary"] is None

    assert ir.sync_cvm_statements()[1] == 0  # unchanged statements append nothing


def test_sync_cvm_statements_matches_by_cnpj_and_refuses_a_name_match_with_another_cnpj(tmp_path) -> None:
    from app.database import Database
    from app.investor_relations import InvestorRelationsService, normalize_company_name

    settings = Settings(database_url="", migrations_dir=tmp_path, investor_relations_output_dir=tmp_path / "ir-pdf")
    database = Database(settings)
    ir = InvestorRelationsService(settings, database)
    database.register_ir_securities([{
        "market": "B3", "symbol": "HOLD3", "company_name": INDUSTRY["name"],
        "name_key": normalize_company_name(INDUSTRY["name"]), "tax_id": "99.999.999/0001-99", "exchange": "B3",
    }])
    companies = database.list_ir_companies("B3")
    index = {item["name_key"]: item for item in companies}

    issuers = ir._cvm_statement_issuers(
        [{"CNPJ_CIA": INDUSTRY["tax_id"], "DENOM_CIA": INDUSTRY["name"], "CD_CVM": INDUSTRY["code"]}],
        index,
        {item["tax_id"]: item for item in companies if item.get("tax_id")},
    )

    assert issuers == {}


def test_ir_worker_spaces_statement_runs_from_the_last_success(tmp_path, monkeypatch) -> None:
    from app.database import Database
    from app.ir_worker import next_cvm_statements_run

    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    assert next_cvm_statements_run(database) == datetime.min.replace(tzinfo=timezone.utc)
    run_id = database.begin_ingestion_run("cvm_statements", "CVM", "regulatory_disclosure", {})
    database.finish_ingestion_run(run_id, "succeeded", 1, 1)
    finished = database._ingestion_runs[run_id]["completed_at"]
    monkeypatch.setenv("C3PO_CVM_STATEMENTS_INTERVAL_HOURS", "48")

    assert next_cvm_statements_run(database) == finished.astimezone(timezone.utc) + timedelta(hours=48)


def test_an_unknown_receipt_date_is_never_the_wall_clock(tmp_path) -> None:
    from app.database import Database
    from app.official_statements import save_official_statements

    packages = build_packages(YEAR)
    packages[("itr", YEAR)].index = []  # statements present, index row missing: the receipt date is unknown
    scans = [
        scan_cvm_package(CvmPackage(kind, year, package.payload(), "https://example.invalid"), ISSUERS)
        for (kind, year), package in packages.items()
    ]
    payloads = extract_cvm_official_statements(scans, issuers=ISSUERS)
    industry = next(payload for payload in payloads if payload["symbol"] == "INDS3")

    assert industry["published_at"] is None
    assert industry["official_metrics"]["periodDocuments"][f"{YEAR}-06-30"]["receivedOn"] is None
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    assert save_official_statements(database, payloads) == len(payloads)
    assert save_official_statements(database, extract_cvm_official_statements(scans, issuers=ISSUERS)) == 0
