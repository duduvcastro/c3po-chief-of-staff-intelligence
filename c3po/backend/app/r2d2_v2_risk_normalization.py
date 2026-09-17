"""Strict candidate normalization; no default scores or coverage attestation.

Candidates require a separate audited freshness/population assessment before
they may enter adapt_canonical_risk. A parsed empty list is NOT verified zero.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import math
from typing import Any

from app.r2d2_v2_risk_source import InstitutionalPositions


def finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("NUMBER_MISSING_OR_INVALID")
    try:
        numeric = Decimal(str(value))
        result = float(numeric)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError("NUMBER_MISSING_OR_INVALID") from None
    if not numeric.is_finite() or not math.isfinite(result):
        raise ValueError("NUMBER_MISSING_OR_INVALID")
    return result


def exact_count(value: Any) -> int:
    finite_number(value)
    numeric = Decimal(str(value))
    if numeric < 0 or numeric != numeric.to_integral_value():
        raise ValueError("COUNT_INVALID")
    return int(numeric)


def institutional_candidate(payload: Any, *, symbol: str, year: int,
                            quarter: int) -> InstitutionalPositions:
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise ValueError("INSTITUTIONAL_ROW_MISSING_OR_AMBIGUOUS")
    row = payload[0]
    if row.get("symbol") != symbol or row.get("year") != year or row.get("quarter") != quarter:
        raise ValueError("INSTITUTIONAL_IDENTITY_MISMATCH")
    return InstitutionalPositions(*(exact_count(row.get(key)) for key in
                                    ("newPositions", "increasedPositions", "reducedPositions", "closedPositions")))


def grade_candidates(payload: Any, *, symbol: str, since: date,
                     through: date) -> tuple[str, ...]:
    if since > through or not isinstance(payload, list):
        raise ValueError("GRADES_WINDOW_OR_PAYLOAD_INVALID")
    actions: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for row in payload:
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            raise ValueError("GRADES_IDENTITY_MISMATCH")
        try:
            event_day = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("GRADES_DATE_INVALID") from None
        if event_day > through:
            raise ValueError("GRADES_FUTURE_RECORD")
        if event_day < since:
            continue
        keys = ("date", "gradingCompany", "previousGrade", "newGrade", "action")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in keys):
            raise ValueError("GRADES_FIELDS_MISSING")
        identity = tuple(row[key] for key in keys)
        if identity in seen:
            raise ValueError("GRADES_DUPLICATE_RECORD")
        seen.add(identity)
        actions.append(row["action"].strip().lower())
    return tuple(actions)


def quarterly_ttm(section: Any, *, field: str, through: date,
                  currency: str) -> tuple[float, tuple[date, ...]]:
    if not isinstance(section, dict) or not isinstance(section.get("quarterly"), dict):
        raise ValueError("QUARTERLY_STATEMENTS_MISSING")
    rows = list(section["quarterly"].values())
    parsed: list[tuple[date, dict[str, Any]]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("STATEMENT_INVALID")
        try:
            period = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("STATEMENT_DATE_INVALID") from None
        if period > through:
            raise ValueError("STATEMENT_FUTURE_PERIOD")
        parsed.append((period, row))
    parsed.sort(key=lambda item: item[0], reverse=True)
    if len(parsed) < 4:
        raise ValueError("TTM_FOUR_QUARTERS_REQUIRED")
    selected = parsed[:4]
    dates = tuple(item[0] for item in selected)
    if len({item[0] for item in parsed}) != len(parsed):
        raise ValueError("STATEMENT_DUPLICATE_PERIOD")
    # Reject gaps/annual substitutes. Fiscal 52/53-week quarters are allowed;
    # unusual fiscal transitions require an explicit reviewed normalization.
    if any(not 65 <= (dates[i] - dates[i + 1]).days <= 115 for i in range(3)):
        raise ValueError("TTM_NONCONTIGUOUS_QUARTERS")
    if any(row.get("currency_symbol") != currency for _, row in selected):
        raise ValueError("STATEMENT_CURRENCY_MISMATCH")
    value = sum(finite_number(row.get(field)) for _, row in selected)
    if not math.isfinite(value):
        raise ValueError("TTM_NOT_FINITE")
    return value, dates
