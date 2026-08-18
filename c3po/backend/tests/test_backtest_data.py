import json
from datetime import datetime, timedelta, timezone

from app.backtest import DEFAULT_FUNDAMENTALS
from app.backtest_data import coverage_summary, fundamentals_lookup, load_decision_rows


def _row(symbol: str, evaluated_at: datetime, **inputs) -> dict:
    return {
        "symbol": symbol,
        "evaluated_at": evaluated_at.isoformat(),
        "fundamental_score": inputs.get("fundamental_score", 70.0),
        "risk_score": inputs.get("risk_score", 30.0),
        "inputs": json.dumps({
            "confidence": inputs.get("confidence", 65.0),
            "upside": inputs.get("upside", 25.0),
            "buy_in_distance": inputs.get("buy_in_distance", 5.0),
            "thesis": inputs.get("thesis", "test thesis"),
        }),
    }


def test_load_decision_rows_parses_json_inputs_and_sorts_by_time() -> None:
    start = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    rows = [
        _row("AAPL", start + timedelta(hours=2), upside=10.0),
        _row("AAPL", start, upside=25.0),
    ]
    snapshots = load_decision_rows(rows)
    assert [s.evaluated_at for s in snapshots] == sorted(s.evaluated_at for s in snapshots)
    assert snapshots[0].fundamentals["upside"] == 25.0
    assert snapshots[0].symbol == "AAPL"


def test_fundamentals_lookup_returns_most_recent_snapshot_at_or_before() -> None:
    start = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    snapshots = load_decision_rows([
        _row("AAPL", start, fundamental_score=60.0),
        _row("AAPL", start + timedelta(days=1), fundamental_score=80.0),
    ])
    lookup = fundamentals_lookup(snapshots)

    assert lookup("AAPL", start)["fundamental_score"] == 60.0
    assert lookup("AAPL", start + timedelta(hours=1))["fundamental_score"] == 60.0
    assert lookup("AAPL", start + timedelta(days=1, hours=1))["fundamental_score"] == 80.0


def test_fundamentals_lookup_falls_back_to_defaults_for_unknown_symbol_or_before_history() -> None:
    start = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    snapshots = load_decision_rows([_row("AAPL", start)])
    lookup = fundamentals_lookup(snapshots)

    assert lookup("MSFT", start) == DEFAULT_FUNDAMENTALS
    assert lookup("AAPL", start - timedelta(days=1)) == DEFAULT_FUNDAMENTALS


def test_coverage_summary_counts_days_symbols_and_decisions() -> None:
    start = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)
    snapshots = load_decision_rows([
        _row("AAPL", start),
        _row("AAPL", start + timedelta(days=1)),
        _row("MSFT", start),
    ])
    summary = coverage_summary(snapshots)

    assert summary["decisions"] == 3
    assert summary["distinct_trading_days"] == 2
    assert summary["distinct_symbols"] == 2
    assert summary["min_decisions_per_symbol"] == 1
    assert summary["max_decisions_per_symbol"] == 2
