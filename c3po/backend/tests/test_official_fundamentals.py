import pytest

from app.config import Settings
from app.database import Database
from app.official_fundamentals import (
    ANALYSIS_TYPE,
    apply_official_fundamentals,
    apply_official_fundamentals_map,
    ensure_builtin_official_fundamentals,
)


def stale_unip6_fundamentals() -> dict:
    return {
        "companyName": "Unipar Carbocloro S.A.",
        "financialsAsOf": "2026-03-31",
        "updated_at": "2026-08-06",
        "marketCap": 7_088_006_656,
        "sharesOutstanding": 111_638_000,
        "targetMeanPrice": 64.0,
        "quarterlyIncome": [
            {"date": "2026-03-31", "totalRevenue": 1_200_000_000, "ebitda": 150_000_000, "netIncome": 35_000_000},
            {"date": "2025-12-31", "totalRevenue": 1_238_971_000, "ebitda": 149_078_000, "netIncome": -5_135_000},
            {"date": "2025-09-30", "totalRevenue": 1_260_883_000, "ebitda": 259_567_000, "netIncome": 109_148_000},
        ],
        "quarterlyCashFlow": [
            {"date": "2026-03-31", "totalCashFromOperatingActivities": 180_000_000, "capitalExpenditures": -160_000_000, "freeCashFlow": 20_000_000},
            {"date": "2025-12-31", "totalCashFromOperatingActivities": 124_065_000, "capitalExpenditures": -255_221_000, "freeCashFlow": -131_156_000},
            {"date": "2025-09-30", "totalCashFromOperatingActivities": 241_668_000, "capitalExpenditures": -280_873_000, "freeCashFlow": -39_205_000},
        ],
        "quarterlyBalance": [{"date": "2026-03-31", "cashAndShortTermInvestments": 1_078_000_000}],
    }


def test_official_release_overrides_stale_period_and_recomputes_ttm(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    assert ensure_builtin_official_fundamentals(database) == 1
    overlay = database.latest_analysis_snapshot(ANALYSIS_TYPE, "B3:UNIP6")["outputs"]

    result = apply_official_fundamentals(stale_unip6_fundamentals(), overlay)

    assert result["financialsAsOf"] == "2026-06-30"
    assert result["quarterlyIncome"][0]["netIncome"] == 123_321_000
    assert result["quarterlyIncome"][1]["totalRevenue"] == 1_238_235_000
    assert result["totalRevenue"] == 5_233_765_000
    assert result["ebitda"] == 948_645_000
    assert result["operatingCashflow"] == 983_570_000
    assert result["totalCash"] == 1_375_373_000
    assert result["totalDebt"] == 3_691_000_000
    assert result["sharesOutstanding"] == 113_173_265
    assert result["revenueGrowthAnnual"] == pytest.approx(1_495_676 / 1_273_920 - 1)
    assert result["earningsGrowthAnnual"] == pytest.approx(123_321 / 231_502 - 1)
    assert result["targetMeanPrice"] == 64.0
    assert result["officialFundamentals"]["sourceName"].endswith("2T26")


def test_builtin_overlay_is_idempotent_and_batch_loadable(tmp_path) -> None:
    database = Database(Settings(database_url="", migrations_dir=tmp_path))
    assert ensure_builtin_official_fundamentals(database) == 1
    assert ensure_builtin_official_fundamentals(database) == 0

    result = apply_official_fundamentals_map(
        database,
        {"UNIP6": stale_unip6_fundamentals(), "PRNR3": {"financialsAsOf": "2026-03-31"}},
        market="B3",
    )

    assert result["UNIP6"]["financialsAsOf"] == "2026-06-30"
    assert result["PRNR3"] == {"financialsAsOf": "2026-03-31"}
