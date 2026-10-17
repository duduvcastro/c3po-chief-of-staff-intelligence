from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import Settings
from app.database import Database
from app.official_fundamentals import (
    ANALYSIS_TYPE as LEGACY_ANALYSIS_TYPE,
    apply_official_fundamentals,
    save_official_fundamentals,
)
from app.official_statements import (
    ANALYSIS_TYPE,
    FIELDWISE_OVERLAY_ENV,
    apply_official_statements,
    apply_official_statements_map,
    complete_ttm,
    fieldwise_overlay_enabled,
    merge_rows_fieldwise,
    save_official_statements,
    select_official_overlay,
    statements_capture_enabled,
    statements_interval_hours,
)


def provider() -> dict:
    """EODHD-shaped fundamentals one quarter behind the regulator, EBITDA 100 in every quarter (TTM 400)."""
    return {
        "financialsAsOf": "2026-03-31",
        "updated_at": "2026-05-10",
        "marketCap": 1_000.0,
        "ebitda": 400.0,
        "enterpriseToEbitda": 2.75,
        "totalRevenue": 1_000.0,
        "quarterlyIncome": [
            {"date": "2026-03-31", "totalRevenue": 250.0, "ebitda": 100.0, "netIncome": 20.0, "researchDevelopment": 3.0},
            {"date": "2025-12-31", "totalRevenue": 250.0, "ebitda": 100.0, "netIncome": 20.0},
            {"date": "2025-09-30", "totalRevenue": 250.0, "ebitda": 100.0, "netIncome": 20.0},
            {"date": "2025-06-30", "totalRevenue": 250.0, "ebitda": 100.0, "netIncome": 20.0},
        ],
        "quarterlyCashFlow": [
            {"date": "2026-03-31", "totalCashFromOperatingActivities": 50.0, "capitalExpenditures": 10.0, "freeCashFlow": 40.0},
            {"date": "2025-12-31", "totalCashFromOperatingActivities": 50.0, "capitalExpenditures": 10.0, "freeCashFlow": 40.0},
            {"date": "2025-09-30", "totalCashFromOperatingActivities": 50.0, "capitalExpenditures": 10.0, "freeCashFlow": 40.0},
        ],
        "quarterlyBalance": [{"date": "2026-03-31", "cashAndShortTermInvestments": 100.0, "shortLongTermDebtTotal": 200.0}],
    }


def itr_overlay() -> dict:
    """The legacy CVM ITR overlay: two newer official quarters, no EBITDA (the ITR DRE has none)."""
    return {
        "market": "B3", "symbol": "SYNT3", "as_of": "2026-06-30", "published_at": "2026-08-10T00:00:00-03:00",
        "source_name": "CVM Dados Abertos - ITR consolidado", "source_url": "https://example.invalid/itr.zip",
        "quarterlyIncome": [
            {"date": "2026-06-30", "totalRevenue": 260.0, "netIncome": 22.0},
            {"date": "2026-03-31", "totalRevenue": 250.0, "netIncome": 20.0},
        ],
        "quarterlyCashFlow": [],
        "quarterlyBalance": [{"date": "2026-06-30", "cashAndShortTermInvestments": 100.0, "shortLongTermDebtTotal": 200.0}],
        "official_metrics": {"cvmTaxId": "00.000.000/0001-00"},
    }


def statements_overlay() -> dict:
    overlay = itr_overlay()
    overlay["source_name"] = "CVM Dados Abertos - ITR/DFP consolidado"
    overlay["quarterlyIncome"][0].update({"operatingIncome": 80.0, "depreciationAndAmortization": 30.0, "ebitda": 110.0})
    overlay["quarterlyIncome"][1].update({"operatingIncome": 72.0, "depreciationAndAmortization": 28.0, "ebitda": 100.0})
    overlay["quarterlyCashFlow"] = [
        {"date": "2026-06-30", "totalCashFromOperatingActivities": 60.0, "capitalExpenditures": -12.0, "freeCashFlow": 48.0},
    ]
    overlay["official_metrics"] = {"cvmTaxId": "00.000.000/0001-00", "statementScope": "consolidated"}
    return overlay


def test_legacy_overlay_halves_ttm_ebitda_and_doubles_ev_ebitda_and_stays_pinned() -> None:
    """The defect this module exists for, on the unchanged legacy helper (R2D2 V2 pins its bytes)."""
    result = apply_official_fundamentals(provider(), itr_overlay())

    assert result["ebitda"] == 200.0  # two provider quarters survive the wholesale row replacement
    assert result["enterpriseToEbitda"] == pytest.approx((1_000 + 200 - 100) / 200)  # 5.5, twice the 2.75 served before
    runtime = (Path(__file__).resolve().parents[1] / "app" / "official_fundamentals.py").read_bytes()
    assert hashlib.sha256(runtime).hexdigest() == "b6edf7903931ce781735bc1c80d3c9ee865d6b4a8cd1f414589f8e6c23e27ff5"


def test_fieldwise_overlay_keeps_provider_ttm_when_a_quarter_lacks_the_field() -> None:
    result = apply_official_statements(provider(), itr_overlay())

    assert result["financialsAsOf"] == "2026-06-30"
    assert result["ebitda"] == 400.0  # the newest quarter has no EBITDA anywhere: no partial sum is served
    assert result["enterpriseToEbitda"] == 2.75
    q1 = result["quarterlyIncome"][1]
    assert q1["date"] == "2026-03-31"
    assert q1["ebitda"] == 100.0 and q1["researchDevelopment"] == 3.0  # provider fields of the same quarter survive
    assert result["totalRevenue"] == 260.0 + 250.0 * 3  # revenue is complete in all four quarters
    assert result["officialFundamentals"]["overlay"] == "fieldwise"
    assert result["officialFundamentals"]["ttmQuarters"] == ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]


def test_fieldwise_overlay_with_complete_statements_recomputes_ttm_ebitda_and_ev() -> None:
    result = apply_official_statements(provider(), statements_overlay())

    assert result["ebitda"] == 110.0 + 100.0 + 100.0 + 100.0
    assert result["enterpriseToEbitda"] == pytest.approx((1_000 + 200 - 100) / 410)
    assert result["ebitdaMargins"] == pytest.approx(410 / 1_010)
    # cash flow has only three quarters (provider Q1 + Q4 + Q3, official Q2): consecutive, so complete
    assert result["operatingCashflow"] == 60.0 + 50.0 * 3
    # capex signs differ by source (CVM negative, provider positive): sizes are summed
    assert result["officialMetrics"]["capexTtm"] == 12.0 + 10.0 * 3
    assert result["officialMetrics"]["statementScope"] == "consolidated"


def test_ttm_requires_four_consecutive_quarters() -> None:
    rows = [
        {"date": "2026-06-30", "ebitda": 1.0},
        {"date": "2026-03-31", "ebitda": 1.0},
        {"date": "2025-09-30", "ebitda": 1.0},  # Q4 missing: a gap, not a year
        {"date": "2025-06-30", "ebitda": 1.0},
    ]
    assert complete_ttm(rows, "ebitda") is None
    assert complete_ttm(rows[:3], "ebitda") is None
    rows[2]["date"] = "2025-12-31"
    rows[3]["date"] = "2025-09-30"
    assert complete_ttm(rows, "ebitda") == 4.0
    rows[3]["ebitda"] = None
    assert complete_ttm(rows, "ebitda") is None


def test_fieldwise_merge_overrides_only_carried_fields() -> None:
    merged = merge_rows_fieldwise(
        [{"date": "2026-03-31", "totalRevenue": 1.0, "ebitda": 5.0}],
        [{"date": "2026-03-31", "totalRevenue": 2.0, "ebitda": None}, {"date": "2026-06-30", "totalRevenue": 3.0}],
    )
    assert merged == [{"date": "2026-06-30", "totalRevenue": 3.0}, {"date": "2026-03-31", "totalRevenue": 2.0, "ebitda": 5.0}]


def test_an_overlay_older_than_the_provider_is_ignored() -> None:
    base = provider()
    base["financialsAsOf"] = "2026-09-30"
    assert apply_official_statements(base, statements_overlay()) == base


def test_select_overlay_serves_statements_whenever_the_symbol_has_them() -> None:
    legacy = itr_overlay()
    legacy["official_metrics"] = {"adjustedRecurringEbitda": 402.0, "cvmTaxId": "legacy"}
    statements = statements_overlay()

    selected = select_official_overlay(statements, legacy)
    assert selected["source_name"].startswith("CVM Dados Abertos - ITR/DFP")
    assert selected["official_metrics"]["adjustedRecurringEbitda"] == 402.0
    assert selected["official_metrics"]["cvmTaxId"] == "00.000.000/0001-00"

    # the legacy sync a quarter ahead of the daily statements run (every new ITR) never takes the symbol over
    legacy["as_of"] = "2026-09-30"
    assert select_official_overlay(statements, legacy)["source_name"] == statements["source_name"]
    assert select_official_overlay(None, legacy)["source_name"] == legacy["source_name"]
    assert select_official_overlay(None, None) is None
    assert select_official_overlay(statements, None)["as_of"] == "2026-06-30"


def test_a_bank_never_swings_to_legacy_code_mapped_values_after_a_new_itr(tmp_path) -> None:
    """The legacy reader maps a bank's 3.05 (pre-tax) as EBIT and 2.02.01 (deposits) as debt; the statements leave
    those fields out. A legacy overlay one quarter ahead must not put them back into EV, ROE or P/B."""
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    statements = {
        "market": "B3", "symbol": "BSIN3", "as_of": "2026-06-30", "source_name": "CVM Dados Abertos - ITR/DFP consolidado",
        "quarterlyIncome": [{"date": "2026-06-30", "incomeBeforeTax": 120.0, "netIncome": 78.0}],
        "quarterlyCashFlow": [],
        "quarterlyBalance": [{"date": "2026-06-30", "totalEquity": 800.0}],
        "official_metrics": {"statementScope": "consolidated", "companyEvBalance": None},
    }
    legacy = {
        "market": "B3", "symbol": "BSIN3", "as_of": "2026-09-30", "source_name": "CVM Dados Abertos - ITR consolidado",
        "quarterlyIncome": [{"date": "2026-09-30", "operatingIncome": 130.0, "netIncome": 80.0}],
        "quarterlyCashFlow": [],
        "quarterlyBalance": [{"date": "2026-09-30", "shortLongTermDebtTotal": 5_000.0, "totalStockholderEquity": 870.0}],
        "official_metrics": {"companyEvBalance": {"asOf": "2026-09-30", "totalCash": 10.0, "totalDebt": 5_000.0}},
    }
    save_official_statements(database, [statements])
    save_official_fundamentals(database, [legacy])
    provider_bank = {"financialsAsOf": "2026-03-31", "marketCap": 2_000.0, "totalDebt": 300.0, "totalEquity": 790.0}

    served = apply_official_statements_map(database, {"BSIN3": provider_bank}, market="B3")["BSIN3"]

    assert served["officialFundamentals"]["asOf"] == "2026-06-30"
    assert served["totalDebt"] == 300.0  # the provider's, never 5,000 of deposits
    assert served["totalEquity"] == 800.0
    assert served["officialMetrics"]["companyEvBalance"] is None
    assert all(row["date"] != "2026-09-30" for row in served["quarterlyIncome"])


def test_statements_snapshots_keep_unseen_periods_and_never_move_backwards(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    assert save_official_statements(database, [statements_overlay()]) == 1
    assert save_official_statements(database, [statements_overlay()]) == 0

    newer = copy.deepcopy(statements_overlay())
    newer["as_of"] = "2026-09-30"
    newer["quarterlyIncome"] = [{"date": "2026-09-30", "totalRevenue": 270.0}]
    newer["official_metrics"] = {"periodDocuments": {"2026-09-30": {"document": "ITR", "version": 1}}}
    assert save_official_statements(database, [newer]) == 1
    outputs = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3:SYNT3")["outputs"]
    assert [row["date"] for row in outputs["quarterlyIncome"]] == ["2026-09-30", "2026-06-30", "2026-03-31"]
    assert outputs["official_metrics"]["statementScope"] == "consolidated"

    older = copy.deepcopy(statements_overlay())
    older["as_of"] = "2026-03-31"
    assert save_official_statements(database, [older]) == 0
    assert database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3:SYNT3")["outputs"]["as_of"] == "2026-09-30"
    assert database.latest_analysis_snapshot(LEGACY_ANALYSIS_TYPE, "B3:SYNT3") is None


def payload_with_document(as_of: str, version: int, received_on: str | None) -> dict:
    payload = copy.deepcopy(statements_overlay())
    payload["as_of"] = as_of
    payload["quarterlyIncome"] = [{"date": as_of, "totalRevenue": 260.0 + version}]
    payload["published_at"] = f"{received_on}T23:59:59.999999-03:00" if received_on else None
    payload["source_url"] = f"https://example.invalid/itr/{as_of[:4]}.zip" if received_on else None
    payload["official_metrics"] = {"periodDocuments": {as_of: {
        "document": "ITR", "referenceDate": as_of, "version": version, "sourceUrl": "https://example.invalid", "receivedOn": received_on,
    }}}
    return payload


def test_published_at_belongs_to_the_as_of_document_and_is_never_inherited(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))

    def saved() -> dict:
        return database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3:SYNT3")["outputs"]

    assert save_official_statements(database, [payload_with_document("2026-03-31", 1, "2026-05-10")]) == 1
    # the as_of advances to a document whose receipt is unknown: unknown, not the prior quarter's receipt
    assert save_official_statements(database, [payload_with_document("2026-06-30", 1, None)]) == 1
    assert saved()["as_of"] == "2026-06-30"
    assert saved()["published_at"] is None and saved()["source_url"] is None

    assert save_official_statements(database, [payload_with_document("2026-06-30", 1, "2026-08-12")]) == 1
    assert saved()["published_at"] == "2026-08-12T23:59:59.999999-03:00"
    # the same version seen again without its index row: the receipt seen before still holds, nothing appended
    assert save_official_statements(database, [payload_with_document("2026-06-30", 1, None)]) == 0
    assert saved()["official_metrics"]["periodDocuments"]["2026-06-30"]["receivedOn"] == "2026-08-12"

    # a re-filed version of the same quarter with an unknown receipt: never dated by the first version's receipt
    assert save_official_statements(database, [payload_with_document("2026-06-30", 2, None)]) == 1
    assert saved()["published_at"] is None
    assert saved()["official_metrics"]["periodDocuments"]["2026-06-30"]["version"] == 2


def test_switches_default_to_legacy_overlay_and_capture_on(monkeypatch) -> None:
    for name in (FIELDWISE_OVERLAY_ENV, "C3PO_CVM_STATEMENTS_CAPTURE_ENABLED", "C3PO_CVM_STATEMENTS_INTERVAL_HOURS"):
        monkeypatch.delenv(name, raising=False)
    assert fieldwise_overlay_enabled() is False
    assert statements_capture_enabled() is True
    assert statements_interval_hours() == 24.0
    monkeypatch.setenv(FIELDWISE_OVERLAY_ENV, "TRUE")
    monkeypatch.setenv("C3PO_CVM_STATEMENTS_CAPTURE_ENABLED", "false")
    monkeypatch.setenv("C3PO_CVM_STATEMENTS_INTERVAL_HOURS", "1")
    assert fieldwise_overlay_enabled() is True
    assert statements_capture_enabled() is False
    assert statements_interval_hours() == 6.0
    monkeypatch.setenv("C3PO_CVM_STATEMENTS_INTERVAL_HOURS", "nan")
    assert statements_interval_hours() == 24.0


def test_b3_screener_serves_the_fieldwise_overlay_only_when_switched_on(tmp_path, monkeypatch) -> None:
    from app.market_data.b3_screener import B3ScreenerService

    settings = Settings(database_url="", migrations_dir=tmp_path)
    database = Database(settings)
    save_official_fundamentals(database, [itr_overlay()])
    save_official_statements(database, [statements_overlay()])
    screener = B3ScreenerService(settings, database, http=None)  # type: ignore[arg-type]
    received = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    screener._eodhd_cache = {"SYNT3": (provider(), received)}
    screener._eodhd_cache_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    monkeypatch.delenv(FIELDWISE_OVERLAY_ENV, raising=False)
    legacy, receipts = screener._eodhd_fundamentals_with_receipts(["SYNT3"])
    assert legacy["SYNT3"]["ebitda"] == 200.0  # today's served behaviour, unchanged while the switch is off
    assert receipts == {"SYNT3": received}

    monkeypatch.setenv(FIELDWISE_OVERLAY_ENV, "true")
    fieldwise, _ = screener._eodhd_fundamentals_with_receipts(["SYNT3"])
    assert fieldwise["SYNT3"]["ebitda"] == 410.0
    assert fieldwise["SYNT3"]["officialFundamentals"]["overlay"] == "fieldwise"


def test_apply_map_falls_back_to_the_legacy_overlay_fieldwise(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    save_official_fundamentals(database, [itr_overlay()])

    result = apply_official_statements_map(database, {"SYNT3": provider(), "NONE3": {"financialsAsOf": "2026-03-31"}}, market="B3")

    assert result["SYNT3"]["ebitda"] == 400.0
    assert result["SYNT3"]["financialsAsOf"] == "2026-06-30"
    assert result["NONE3"] == {"financialsAsOf": "2026-03-31"}
