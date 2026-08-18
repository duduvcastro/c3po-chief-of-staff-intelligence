"""Turns real ``r2d2_decisions`` rows into the ``fundamentals`` input
``backtest.run_backtest`` expects, so entry backtesting stops being
technical-only once enough real trading history exists.

Where the rows come from: ``r2d2_decisions`` (see
``db/016_r2d2_paper_trading.sql``) has stored ``fundamental_score``,
``technical_score``, ``risk_score``, ``composite_score`` and the full
``inputs`` JSONB (upside, confidence, buy_in_distance, thesis,
technical_indicators) for every BUY/REJECT decision since the live
90-day experiment's ``start_date``. Export the BUY rows -- e.g. with the
read-only query in ``scripts/r2d2-export-readonly.sh`` -- or query the
table directly if you have database access, and load either the CSV or
a ``psycopg`` cursor's rows with the functions below.

Minimum-sample guidance: a handful of decisions from a single session is
an anecdote, not a backtest input. ``coverage_summary`` reports distinct
trading days and decisions per symbol so you can see, at a glance,
whether there's enough history yet -- treat anything under ~15 distinct
trading days the same way ``METHODOLOGY_GOVERNANCE.md`` treats a
proposed constant change: not enough evidence to act on.
"""

from __future__ import annotations

import csv
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

FUNDAMENTAL_FIELDS = ("fundamental_score", "confidence", "risk_score", "upside", "buy_in_distance")


@dataclass(frozen=True)
class DecisionSnapshot:
    symbol: str
    evaluated_at: datetime
    fundamentals: dict[str, Any]


def _parse_timestamp(value: str) -> datetime:
    value = value.strip()
    if value.endswith("+00"):
        value = value[:-3] + "+00:00"
    return datetime.fromisoformat(value)


def load_decision_rows(rows: Iterable[dict[str, Any]]) -> list[DecisionSnapshot]:
    """Convert raw ``r2d2_decisions`` rows (dicts with string or already-parsed
    values, as produced by ``csv.DictReader`` or a DB cursor) into snapshots.

    Only successful entries carry a ``trade_id`` and are useful here --
    REJECT rows have no matching price/position to replay against, so
    callers building an export should filter to ``action = 'BUY'`` first
    (the shipped export script already does).
    """
    snapshots: list[DecisionSnapshot] = []
    for row in rows:
        inputs = row.get("inputs")
        if isinstance(inputs, str):
            inputs = json.loads(inputs) if inputs else {}
        inputs = inputs or {}
        evaluated_at = row["evaluated_at"]
        if isinstance(evaluated_at, str):
            evaluated_at = _parse_timestamp(evaluated_at)
        fundamentals = {
            "fundamental_score": float(row.get("fundamental_score") or inputs.get("fundamental_score") or 50.0),
            "confidence": float(inputs.get("confidence", 50.0)),
            "risk_score": float(row.get("risk_score") or inputs.get("risk_score") or 50.0),
            "upside": float(inputs.get("upside", 0.0)),
            "buy_in_distance": float(inputs.get("buy_in_distance", 10.0)),
            "thesis": str(inputs.get("thesis", "")),
        }
        snapshots.append(DecisionSnapshot(
            symbol=str(row["symbol"]), evaluated_at=evaluated_at, fundamentals=fundamentals,
        ))
    snapshots.sort(key=lambda s: s.evaluated_at)
    return snapshots


def load_decision_csv(path: str | Path) -> list[DecisionSnapshot]:
    """Load a ``decisions_buy.csv`` export (see ``scripts/r2d2-export-readonly.sh``)."""
    with open(path, newline="", encoding="utf-8") as handle:
        return load_decision_rows(csv.DictReader(handle))


def fundamentals_lookup(snapshots: list[DecisionSnapshot]) -> Callable[[str, datetime], dict[str, Any]]:
    """Build the ``fundamentals`` callable ``run_backtest`` accepts.

    For a given ``(symbol, at)``, returns the most recent real decision
    snapshot for that symbol at or before ``at`` -- i.e. "what did the
    live One Pager pipeline actually think about this symbol the last
    time R2D2 looked at it before this bar." Falls back to
    ``backtest.DEFAULT_FUNDAMENTALS`` for symbols/timestamps with no
    prior decision on record (e.g. a symbol the live system never
    scanned), matching today's technical-only behavior for that gap
    rather than failing the whole backtest run.
    """
    from .backtest import DEFAULT_FUNDAMENTALS  # local import: avoid a cycle at module load time

    by_symbol: dict[str, tuple[list[datetime], list[dict[str, Any]]]] = {}
    for snapshot in snapshots:
        times, values = by_symbol.setdefault(snapshot.symbol, ([], []))
        times.append(snapshot.evaluated_at)
        values.append(snapshot.fundamentals)

    def lookup(symbol: str, at: datetime) -> dict[str, Any]:
        times, values = by_symbol.get(symbol, ([], []))
        if not times:
            return dict(DEFAULT_FUNDAMENTALS)
        index = bisect_right(times, at) - 1
        if index < 0:
            return dict(DEFAULT_FUNDAMENTALS)
        return dict(values[index])

    return lookup


def coverage_summary(snapshots: list[DecisionSnapshot]) -> dict[str, Any]:
    """Distinct trading days / symbols / decisions -- print this before trusting a run."""
    days = {snapshot.evaluated_at.date() for snapshot in snapshots}
    symbols = {snapshot.symbol for snapshot in snapshots}
    per_symbol = {symbol: sum(1 for s in snapshots if s.symbol == symbol) for symbol in symbols}
    return {
        "decisions": len(snapshots),
        "distinct_trading_days": len(days),
        "distinct_symbols": len(symbols),
        "date_range": (min(days), max(days)) if days else None,
        "min_decisions_per_symbol": min(per_symbol.values()) if per_symbol else 0,
        "max_decisions_per_symbol": max(per_symbol.values()) if per_symbol else 0,
    }
