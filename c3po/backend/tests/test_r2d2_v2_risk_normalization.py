from datetime import date

import pytest

from app.r2d2_v2_risk_normalization import (
    exact_count, finite_number, grade_candidates, institutional_candidate, quarterly_ttm,
)


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


def test_grades_future_and_duplicate_not_silently_dropped():
    row = dict(symbol="TEST", date="2026-09-17", gradingCompany="Example",
               previousGrade="Hold", newGrade="Buy", action="Upgrade")
    args = dict(symbol="TEST", since=date(2026, 6, 19), through=date(2026, 9, 17))
    assert grade_candidates([row], **args) == ("upgrade",)
    with pytest.raises(ValueError, match="DUPLICATE"):
        grade_candidates([row, row], **args)
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


def test_gap_and_missing_metric_not_treated_as_complete_ttm():
    section = statements()
    section["quarterly"]["2026-03-31"]["date"] = "2026-01-01"
    with pytest.raises(ValueError, match="NONCONTIGUOUS"):
        ttm(section)
    section = statements()
    del section["quarterly"]["2026-03-31"]["ebitda"]
    with pytest.raises(ValueError, match="NUMBER"):
        ttm(section)
