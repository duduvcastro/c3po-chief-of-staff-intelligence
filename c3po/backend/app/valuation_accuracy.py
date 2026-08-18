"""Checks whether C3PO's canonical valuation calls (Dark Side / Last Jedi /
Ben Kenobi Records -- see ``c3po/docs/VALUATION_ACCURACY.md``) are actually
tracking reality, using ``valuation_change_records`` (the "Ben Kenobi
Records" audit trail: every time a target price changed for a symbol, with
the price at that moment) plus real subsequent price history.

Mirrors the shape of ``backtest.py``/``backtest_data.py`` on purpose: pure
computation here, zero bundled market data, a ``work/`` script wires in a
real price source, and nothing is trustworthy below a minimum sample --
see ``coverage_summary`` and ``c3po/docs/VALUATION_ACCURACY.md``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

CONFIDENCE_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 60.0, "<60"),
    (60.0, 75.0, "60-75"),
    (75.0, 90.0, "75-90"),
    (90.0, 100.0001, "90+"),
)


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    if value.endswith("+00"):
        value = value[:-3] + "+00:00"
    return datetime.fromisoformat(value)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ValuationCall:
    """One row of valuation_change_records: a TP set for a symbol at a point in time."""
    market: str  # 'B3' or 'US'
    symbol: str
    changed_at: datetime
    price_at_call: float
    target_price: float
    confidence: float

    @property
    def predicted_return_percent(self) -> float:
        if self.price_at_call <= 0:
            return 0.0
        return (self.target_price / self.price_at_call - 1) * 100


def load_valuation_calls(rows: Iterable[dict[str, Any]]) -> list[ValuationCall]:
    """Convert raw valuation_change_records rows (CSV dicts or DB cursor rows) into calls.

    Skips rows with no usable target price or price-at-call -- an "initial"
    record with a missing ``price`` (data was incomplete that day) can't be
    graded, so it's dropped rather than guessed at.
    """
    calls: list[ValuationCall] = []
    for row in rows:
        target_price = _float(row.get("new_tp"))
        price_at_call = _float(row.get("price"))
        if target_price <= 0 or price_at_call <= 0:
            continue
        changed_at = row["changed_at"]
        if isinstance(changed_at, str):
            changed_at = _parse_timestamp(changed_at)
        calls.append(ValuationCall(
            market=str(row.get("market") or "").upper(),
            symbol=str(row.get("symbol") or "").upper(),
            changed_at=changed_at,
            price_at_call=price_at_call,
            target_price=target_price,
            confidence=_float(row.get("new_confidence"), 50.0),
        ))
    calls.sort(key=lambda call: call.changed_at)
    return calls


def load_valuation_calls_csv(path: str | Path) -> list[ValuationCall]:
    with open(path, newline="", encoding="utf-8") as handle:
        return load_valuation_calls(csv.DictReader(handle))


@dataclass(frozen=True)
class CallOutcome:
    call: ValuationCall
    horizon_days: int
    price_at_horizon: float
    actual_return_percent: float

    @property
    def error_percent(self) -> float:
        """Actual return minus predicted return. Negative = fell short of the call."""
        return self.actual_return_percent - self.call.predicted_return_percent

    @property
    def direction_correct(self) -> bool:
        predicted = self.call.predicted_return_percent
        if predicted == 0:
            return True
        return (predicted > 0) == (self.actual_return_percent > 0)

    @property
    def hit_target(self) -> bool:
        """Did the price actually reach the called target by this horizon."""
        if self.call.target_price >= self.call.price_at_call:
            return self.price_at_horizon >= self.call.target_price
        return self.price_at_horizon <= self.call.target_price


PriceLookup = Callable[[str, datetime], float | None]


def evaluate_calls(
    calls: list[ValuationCall], price_lookup: PriceLookup, *,
    horizons_days: tuple[int, ...] = (30, 60, 90),
) -> list[CallOutcome]:
    """For each call, look up the real price ``horizon_days`` later and grade it.

    A call is only graded at a horizon if that much time has actually
    elapsed since ``changed_at`` (as of ``datetime.now()``) AND
    ``price_lookup`` has data for that date -- there is no forward-filling
    or extrapolation. Calls too recent to have reached a horizon yet are
    silently skipped for that horizon, which is why ``coverage_summary``
    matters: a report with few graded outcomes is not evidence of anything.
    """
    now = datetime.now(calls[0].changed_at.tzinfo) if calls else datetime.now()
    outcomes: list[CallOutcome] = []
    for call in calls:
        for horizon in horizons_days:
            target_date = call.changed_at + timedelta(days=horizon)
            if target_date > now:
                continue
            price = price_lookup(call.symbol, target_date)
            if price is None or price <= 0:
                continue
            actual_return = (price / call.price_at_call - 1) * 100
            outcomes.append(CallOutcome(
                call=call, horizon_days=horizon,
                price_at_horizon=price, actual_return_percent=actual_return,
            ))
    return outcomes


@dataclass
class AccuracyReport:
    outcomes: list[CallOutcome]

    def for_horizon(self, horizon_days: int) -> list[CallOutcome]:
        return [outcome for outcome in self.outcomes if outcome.horizon_days == horizon_days]

    def summary_by_horizon(self) -> dict[int, dict[str, Any]]:
        horizons = sorted({outcome.horizon_days for outcome in self.outcomes})
        summary: dict[int, dict[str, Any]] = {}
        for horizon in horizons:
            subset = self.for_horizon(horizon)
            if not subset:
                continue
            errors = [outcome.error_percent for outcome in subset]
            summary[horizon] = {
                "graded_calls": len(subset),
                "hit_rate_percent": round(sum(o.hit_target for o in subset) / len(subset) * 100, 2),
                "direction_correct_percent": round(
                    sum(o.direction_correct for o in subset) / len(subset) * 100, 2,
                ),
                "mean_absolute_error_percent": round(sum(abs(e) for e in errors) / len(errors), 2),
                "mean_error_percent": round(sum(errors) / len(errors), 2),
            }
        return summary

    def calibration_by_confidence(self, horizon_days: int) -> dict[str, dict[str, Any]]:
        """Does a higher-confidence call actually hit more often? If not, confidence isn't calibrated."""
        subset = self.for_horizon(horizon_days)
        buckets: dict[str, list[CallOutcome]] = {}
        for outcome in subset:
            for low, high, label in CONFIDENCE_BUCKETS:
                if low <= outcome.call.confidence < high:
                    buckets.setdefault(label, []).append(outcome)
                    break
        return {
            label: {
                "graded_calls": len(items),
                "hit_rate_percent": round(sum(o.hit_target for o in items) / len(items) * 100, 2),
            }
            for label, items in buckets.items() if items
        }


def coverage_summary(calls: list[ValuationCall]) -> dict[str, Any]:
    """Distinct symbols / calls / date range -- check before trusting an accuracy report.

    Mirrors backtest_data.coverage_summary(): a handful of calls is an
    anecdote, not a track record. See VALUATION_ACCURACY.md for the
    minimum-sample bar before drawing any conclusion from this report.
    """
    if not calls:
        return {"calls": 0, "distinct_symbols": 0, "date_range": None}
    dates = [call.changed_at.date() for call in calls]
    symbols = {call.symbol for call in calls}
    return {
        "calls": len(calls),
        "distinct_symbols": len(symbols),
        "date_range": (min(dates), max(dates)),
    }
