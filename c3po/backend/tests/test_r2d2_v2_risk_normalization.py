from datetime import date, datetime, timedelta, timezone

import pytest

from app.r2d2_v2_risk_normalization import (
    exact_count, finite_number, grade_candidates, institutional_candidate, quarterly_ttm,
    canonical_growth_ratio, insider_event_candidates,
)


@pytest.mark.parametrize("value", [-250, -2.001, -2, 0, 2, 2.001, 250, "-12.5"])
def test_ratio_matches_original_and_records_conversion(value):
    from app.one_pager import OnePagerService
    normalized, receipt = canonical_growth_ratio(value)
    assert normalized == OnePagerService._ratio(value)
    assert receipt["divided_by_100"] == (abs(float(value)) > 2)


def test_insider_matches_database_direction_window_and_filters():
    from app.database import Database
    from dataclasses import asdict
    now = datetime(2026, 9, 17, 18, tzinfo=timezone.utc)
    base = dict(symbol="TEST", market="US", source_code="sec", event_type="Insider Transaction",
                published_at=now-timedelta(days=1))
    rows = [
        {**base, "raw_metadata": {"source": "finnhub", "is_purchase": True}},
        {**base, "raw_metadata": {"source": "eodhd", "is_sale": True}},
        {**base, "raw_metadata": {"is_purchase": True, "is_sale": True}},
        {**base, "raw_metadata": {"transaction_code": "A"}},
        {**base, "source_code": "finnhub", "raw_metadata": {"is_purchase": True}},
        {**base, "symbol": "OTHER", "raw_metadata": {"is_sale": True}},
        {**base, "published_at": now-timedelta(days=180), "raw_metadata": {"is_sale": True}},
        {**base, "published_at": now-timedelta(days=180, seconds=1), "raw_metadata": {"is_sale": True}},
    ]
    database = object.__new__(Database)
    database.database_url = ""
    database._ir_events = {str(i): row for i, row in enumerate(rows)}
    original = database.insider_transaction_activity(["TEST"], "US", now-timedelta(days=180))["TEST"]
    result = insider_event_candidates(rows, symbol="TEST", decision_at=now)
    assert asdict(result) == original == {"total_count": 4, "buy_count": 2, "sell_count": 2}


def test_insider_future_event_refused_instead_of_counted():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    row = dict(symbol="TEST", market="US", source_code="sec", event_type="Insider Transaction",
               published_at=now+timedelta(seconds=1), raw_metadata={"is_purchase": True})
    with pytest.raises(ValueError, match="FUTURE"):
        insider_event_candidates([row], symbol="TEST", decision_at=now)


@pytest.mark.parametrize("value", [None, True, "", "NaN", "Infinity", [], {}, "1,2"])
def test_missing_or_malformed_never_defaults_to_zero(value):
    with pytest.raises(ValueError):
        finite_number(value)


@pytest.mark.parametrize("value", [-1, 1.5, "2.1", False])
def test_counts_cannot_truncate(value):
    with pytest.raises(ValueError):
        exact_count(value)


def test_zero_is_a_value_but_missing_field_is_not():
    row = dict(symbol="TEST", year=2026, quarter=2, newPositions=0,
               increasedPositions="0", reducedPositions=0, closedPositions=0)
    assert institutional_candidate([row], symbol="TEST", year=2026, quarter=2).new_positions == 0
    del row["closedPositions"]
    with pytest.raises(ValueError):
        institutional_candidate([row], symbol="TEST", year=2026, quarter=2)


@pytest.mark.parametrize("field,value", [("symbol", "OTHER"), ("year", 2025), ("quarter", 1)])
def test_wrong_institutional_identity_refused(field, value):
    row = dict(symbol="TEST", year=2026, quarter=2)
    row[field] = value
    with pytest.raises(ValueError, match="IDENTITY"):
        institutional_candidate([row], symbol="TEST", year=2026, quarter=2)


def test_grades_future_refused_and_rc4_deduplication_applied():
    row = dict(symbol="TEST", date="2026-09-17", gradingCompany="Example",
               previousGrade="Hold", newGrade="Buy", action="Upgrade")
    args = dict(symbol="TEST", since=date(2026, 6, 19), through=date(2026, 9, 17))
    assert grade_candidates([row], **args) == ("upgrade",)
    assert grade_candidates([row, {**row, "newGrade": "Strong Buy"}], **args) == ("upgrade",)
    with pytest.raises(ValueError, match="FUTURE"):
        grade_candidates([{**row, "date": "2026-09-18"}], **args)


def statements():
    return {"quarterly": {day: {"date": day, "currency_symbol": "USD", "ebitda": "-10"}
                          for day in ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30")}}


def ttm(section):
    return quarterly_ttm(section, field="ebitda", through=date(2026, 9, 17), currency="USD")


def test_negative_ebitda_preserved_four_quarters_required():
    section = statements()
    assert ttm(section)[0] == -40
    del section["quarterly"]["2025-09-30"]
    with pytest.raises(ValueError, match="FOUR_QUARTERS"):
        ttm(section)


def test_currency_mismatch_cannot_be_added():
    section = statements()
    section["quarterly"]["2026-03-31"]["currency_symbol"] = "BRL"
    with pytest.raises(ValueError, match="CURRENCY"):
        ttm(section)


def test_no_new_quarter_length_policy_and_missing_metric_refused():
    section = statements()
    section["quarterly"]["2026-03-31"]["date"] = "2026-01-01"
    assert ttm(section)[0] == -40
    section = statements()
    del section["quarterly"]["2026-03-31"]["ebitda"]
    with pytest.raises(ValueError, match="NUMBER"):
        ttm(section)
