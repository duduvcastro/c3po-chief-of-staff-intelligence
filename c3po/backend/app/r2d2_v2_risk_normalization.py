"""Strict candidate normalization; no default scores or coverage attestation.

Candidates require a separate audited freshness/population assessment before
they may enter adapt_canonical_risk. A parsed empty list is NOT verified zero.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import math
import json
import re
from typing import Any

from app.r2d2_v2_risk_source import InsiderActivity, InstitutionalPositions


def canonical_symbol(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,14}", value):
        raise ValueError("SYMBOL_INVALID")
    return value.upper()


def strict_day(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def canonical_growth_ratio(value: Any) -> tuple[float, dict[str, Any]]:
    """RC-2: preserve the explicit historical heuristic, including its boundary."""
    number = finite_number(value)
    converted = abs(number) > 2
    return (number / 100 if converted else number), {
        "normalization": "ORIGIN_RATIO_ABS_GT_2_DIVIDE_100",
        "origin_revision": "6083d7420746434426a11134b8edf0ba4b60b6b0",
        "input_value": number, "divided_by_100": converted,
    }


def insider_event_candidates(rows: list[dict[str, Any]], *, symbol: str,
                             decision_at: datetime) -> InsiderActivity:
    """Canonical population is persisted ir_events, not raw provider filings.

    The executor supplies a consistent DB snapshot and independently checks the
    sync_sec coverage receipt. These counts alone do not attest 180d coverage.
    No ingestion, fallback provider call or insertion occurs here.
    """
    if decision_at.tzinfo is None or decision_at.utcoffset() is None:
        raise ValueError("INSIDER_DECISION_CLOCK_INVALID")
    symbol = canonical_symbol(symbol)
    since = decision_at - timedelta(days=180)
    buys = sells = 0
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if (row.get("symbol") != symbol or row.get("market") != "US"
                or row.get("source_code") != "sec"
                or row.get("event_type") != "Insider Transaction"):
            continue
        published = row.get("published_at")
        if (not isinstance(published, datetime) or published.tzinfo is None
                or published.utcoffset() is None):
            raise ValueError("INSIDER_PUBLICATION_CLOCK_INVALID")
        if published > decision_at:
            raise ValueError("INSIDER_FUTURE_EVENT")
        if published < since:
            continue
        external_id = row.get("external_id")
        if not isinstance(external_id, str) or not external_id:
            raise ValueError("INSIDER_EVENT_ID_MISSING")
        identity = (row["source_code"], external_id)
        if identity in seen:
            raise ValueError("INSIDER_DUPLICATE_EVENT")
        seen.add(identity)
        metadata = row.get("raw_metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except ValueError:
                raise ValueError("INSIDER_METADATA_INVALID") from None
        if not isinstance(metadata, dict):
            raise ValueError("INSIDER_METADATA_INVALID")
        # Exact precedence of Database._insider_transaction_direction at the
        # pinned origin. Do not count grants/unknown events in total_count.
        if metadata.get("source") == "cvm_vlmo":
            movement = str(metadata.get("movement") or "")
            direction = 1 if movement.startswith("Compra") else -1 if movement.startswith("Venda") else 0
        elif metadata.get("is_purchase"):
            direction = 1
        elif metadata.get("is_sale"):
            direction = -1
        else:
            direction = 0
        buys += int(direction > 0)
        sells += int(direction < 0)
    return InsiderActivity(buys + sells, buys, sells)


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
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("INSTITUTIONAL_ROW_MISSING")
    row = payload[0]
    # Declared identity coercion: case-insensitive ticker, integral numeric
    # year/quarter (including provider strings). Never truncate fractions.
    if (canonical_symbol(row.get("symbol")) != canonical_symbol(symbol)
            or exact_count(row.get("year")) != year or exact_count(row.get("quarter")) != quarter):
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
        event_day = strict_day(row.get("date"))
        if event_day is None:
            continue  # The original skips malformed dates, not the whole issuer.
        if event_day > through:
            raise ValueError("GRADES_FUTURE_RECORD")
        if event_day < since:
            continue
        keys = ("date", "gradingCompany", "action")
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in keys):
            raise ValueError("GRADES_FIELDS_MISSING")
        # RC-4 explicitly chooses this deduplication identity. Grade labels do
        # not participate in the directional score. Keep raw receipts intact.
        identity = (row["date"], row["gradingCompany"], row["action"].lower())
        if identity in seen:
            continue
        seen.add(identity)
        actions.append(row["action"].lower())
    return tuple(actions)


def quarterly_ttm(section: Any, *, field: str, through: date,
                  currency: str) -> tuple[float, tuple[date, ...]]:
    if not isinstance(section, dict) or not isinstance(section.get("quarterly"), dict):
        raise ValueError("QUARTERLY_STATEMENTS_MISSING")
    # EODHD._dated_rows selects the first eight KEYS descending, then OnePager
    # takes the first four rows. The embedded date must not change that order.
    periods = section["quarterly"]
    parsed: list[tuple[date, dict[str, Any]]] = []
    for key in sorted(periods, reverse=True)[:8]:
        row = periods[key]
        if not isinstance(row, dict):
            continue
        period = strict_day(row.get("date") or key)
        if period is None:
            raise ValueError("STATEMENT_DATE_INVALID")
        if period > through:
            raise ValueError("STATEMENT_FUTURE_PERIOD")
        parsed.append((period, row))
    if len(parsed) < 4:
        raise ValueError("TTM_FOUR_QUARTERS_REQUIRED")
    selected = parsed[:4]
    dates = tuple(item[0] for item in selected)
    if len(set(dates)) != len(dates):
        raise ValueError("STATEMENT_DUPLICATE_PERIOD")
    # RC-4: four complete quarterly rows, selected descending as in origin.
    # Do not invent a fiscal-quarter day-length threshold or a new TTL.
    if any(row.get("currency_symbol") != currency for _, row in selected):
        raise ValueError("STATEMENT_CURRENCY_MISMATCH")
    value = sum(finite_number(row.get(field)) for _, row in selected)
    if not math.isfinite(value):
        raise ValueError("TTM_NOT_FINITE")
    return value, dates
