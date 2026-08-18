from datetime import datetime, timedelta, timezone

from app.valuation_accuracy import (
    ValuationCall,
    coverage_summary,
    evaluate_calls,
    load_valuation_calls,
)


def _call(symbol: str, changed_at: datetime, price: float, tp: float, confidence: float = 70.0) -> dict:
    return {
        "market": "US", "symbol": symbol, "changed_at": changed_at.isoformat(),
        "price": price, "new_tp": tp, "new_confidence": confidence,
    }


def test_load_valuation_calls_skips_rows_without_price_or_target() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _call("AAPL", now, 100.0, 120.0),
        {"market": "US", "symbol": "MSFT", "changed_at": now.isoformat(), "price": 0, "new_tp": 400.0},
        {"market": "US", "symbol": "NVDA", "changed_at": now.isoformat(), "price": 100.0, "new_tp": 0},
    ]
    calls = load_valuation_calls(rows)
    assert len(calls) == 1
    assert calls[0].symbol == "AAPL"
    assert round(calls[0].predicted_return_percent, 6) == 20.0


def test_evaluate_calls_only_grades_horizons_that_have_elapsed() -> None:
    old_call = ValuationCall(
        market="US", symbol="AAPL", changed_at=datetime.now(timezone.utc) - timedelta(days=100),
        price_at_call=100.0, target_price=120.0, confidence=80.0,
    )
    recent_call = ValuationCall(
        market="US", symbol="MSFT", changed_at=datetime.now(timezone.utc) - timedelta(days=10),
        price_at_call=200.0, target_price=240.0, confidence=80.0,
    )

    def price_lookup(symbol: str, at: datetime) -> float | None:
        return {"AAPL": 118.0, "MSFT": 210.0}.get(symbol)

    outcomes = evaluate_calls([old_call, recent_call], price_lookup, horizons_days=(30, 60, 90))
    graded_symbols = {o.call.symbol for o in outcomes}
    assert graded_symbols == {"AAPL"}
    assert len(outcomes) == 3  # AAPL graded at 30, 60 and 90 days; MSFT skipped entirely


def test_evaluate_calls_skips_when_price_lookup_returns_none() -> None:
    call = ValuationCall(
        market="US", symbol="ZZZZ", changed_at=datetime.now(timezone.utc) - timedelta(days=100),
        price_at_call=50.0, target_price=60.0, confidence=70.0,
    )
    outcomes = evaluate_calls([call], lambda symbol, at: None, horizons_days=(30,))
    assert outcomes == []


def test_call_outcome_hit_target_and_direction_and_error() -> None:
    call = ValuationCall(
        market="US", symbol="AAPL", changed_at=datetime.now(timezone.utc) - timedelta(days=100),
        price_at_call=100.0, target_price=120.0, confidence=80.0,
    )

    def price_lookup(symbol: str, at: datetime) -> float | None:
        return 125.0

    outcomes = evaluate_calls([call], price_lookup, horizons_days=(90,))
    outcome = outcomes[0]
    assert outcome.hit_target is True
    assert outcome.direction_correct is True
    assert outcome.actual_return_percent == 25.0
    assert round(outcome.error_percent, 2) == 5.0  # beat the 20% call by 5pp


def test_call_outcome_bearish_tp_below_call_price() -> None:
    call = ValuationCall(
        market="US", symbol="AAPL", changed_at=datetime.now(timezone.utc) - timedelta(days=100),
        price_at_call=100.0, target_price=80.0, confidence=60.0,
    )
    outcomes = evaluate_calls([call], lambda s, a: 75.0, horizons_days=(90,))
    assert outcomes[0].hit_target is True

    outcomes_missed = evaluate_calls([call], lambda s, a: 95.0, horizons_days=(90,))
    assert outcomes_missed[0].hit_target is False
    assert outcomes_missed[0].direction_correct is True  # still moved down, just not far enough


def test_summary_by_horizon_and_calibration_by_confidence() -> None:
    base = datetime.now(timezone.utc) - timedelta(days=100)
    calls = [
        ValuationCall("US", "AAPL", base, 100.0, 120.0, confidence=95.0),
        ValuationCall("US", "MSFT", base, 100.0, 120.0, confidence=95.0),
        ValuationCall("US", "NVDA", base, 100.0, 120.0, confidence=50.0),
    ]
    prices = {"AAPL": 125.0, "MSFT": 130.0, "NVDA": 90.0}
    outcomes = evaluate_calls(calls, lambda symbol, at: prices[symbol], horizons_days=(90,))
    from app.valuation_accuracy import AccuracyReport
    report = AccuracyReport(outcomes)

    summary = report.summary_by_horizon()
    assert summary[90]["graded_calls"] == 3
    assert summary[90]["hit_rate_percent"] == round(2 / 3 * 100, 2)

    calibration = report.calibration_by_confidence(90)
    assert calibration["90+"]["graded_calls"] == 2
    assert calibration["90+"]["hit_rate_percent"] == 100.0
    assert calibration["<60"]["graded_calls"] == 1
    assert calibration["<60"]["hit_rate_percent"] == 0.0


def test_coverage_summary_reports_calls_symbols_and_date_range() -> None:
    calls = load_valuation_calls([
        _call("AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc), 100.0, 120.0),
        _call("AAPL", datetime(2026, 2, 1, tzinfo=timezone.utc), 105.0, 125.0),
        _call("MSFT", datetime(2026, 1, 15, tzinfo=timezone.utc), 200.0, 240.0),
    ])
    summary = coverage_summary(calls)
    assert summary["calls"] == 3
    assert summary["distinct_symbols"] == 2
    assert summary["date_range"] == (datetime(2026, 1, 1).date(), datetime(2026, 2, 1).date())


def test_coverage_summary_empty() -> None:
    assert coverage_summary([]) == {"calls": 0, "distinct_symbols": 0, "date_range": None}
