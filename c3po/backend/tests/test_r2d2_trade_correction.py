from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService, _trade_is_corrected


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
    )


def _service() -> R2D2PaperService:
    settings = _settings()
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def test_trade_is_corrected_detects_the_correction_key() -> None:
    assert _trade_is_corrected({"decision_snapshot": {"correction": {"correction_amount_usd": 100.0}}}) is True
    assert _trade_is_corrected({"decision_snapshot": {"thesis": "normal trade"}}) is False
    assert _trade_is_corrected({"decision_snapshot": None}) is False
    assert _trade_is_corrected({}) is False


def test_trade_summary_excludes_corrected_trades() -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": "REAL", "name": "Real Trade Corp", "currency": "USD",
        "stop_price": 95.0, "fundamental_score": 80.0, "technical_score": 70.0,
        "risk_score": 25.0, "composite_score": 78.0,
    }
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=10,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="real entry", decision=candidate, quote_as_of=datetime.now(timezone.utc),
    )
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="SELL", quantity=10,
        signal_price=110.0, fill_price=110.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="real winning exit", decision=candidate, quote_as_of=datetime.now(timezone.utc),
    )
    corrected_candidate = {**candidate, "symbol": "BADFEED"}
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=corrected_candidate, side="BUY", quantity=10,
        signal_price=100.0, fill_price=100.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="real entry", decision=corrected_candidate, quote_as_of=datetime.now(timezone.utc),
    )
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=corrected_candidate, side="SELL", quantity=10,
        signal_price=1.0, fill_price=1.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="phantom exit on a stale delayed quote", decision=corrected_candidate,
        quote_as_of=datetime.now(timezone.utc),
    )
    # Simulate the manual correction annotation applied to the bad SELL row only.
    for trade in service.repo.memory["trades"]:
        if trade["symbol"] == "BADFEED" and trade["side"] == "SELL":
            trade["decision_snapshot"] = {
                "correction": {"correction_amount_usd": 999.0, "phantom_realized_pnl_usd": -999.0},
            }

    summary = service.repo.trade_summary(experiment["id"])

    # 2 BUY + 1 real SELL counted; the corrected SELL is excluded entirely.
    assert summary["total_transactions"] == 3
    assert summary["positive_transactions"] == 1
    assert summary["negative_transactions"] == 0


def test_daily_learning_ignores_a_corrected_trades_phantom_loss() -> None:
    """A trade whose fill came from a stale-quote bug (2026-08-18 incident) must not
    corrupt the adaptive entry-policy loop into tightening on evidence that never
    happened. Real trades alone here comfortably clear the "widen" bar; adding one
    corrected trade with a massive phantom loss must not flip that outcome.
    """
    service = _service()
    experiment = service.ensure_initialized()
    for offset in range(5):
        session_date = date(2026, 8, 18) + timedelta(days=offset)
        service.repo.memory["snapshots"][session_date] = {
            "session_date": session_date,
            "nav_usd": 1_000_000 + (offset + 1) * 5_000,
            "cash_usd": 1_000_000,
            "daily_pnl_usd": 5_000,
            "daily_return_percent": 0.5,
            "gross_exposure_usd": 0,
            "open_positions": 0,
            "is_final": True,
        }
    # 6 real wins, 2 real losses: win_rate 75%, profit_factor 12.0 -- clears the
    # "widen" bar (>=60% win rate, >=1.35 profit factor) on its own.
    for offset in range(6):
        service.repo.memory["trades"].append({
            "realized_pnl_usd": 2_000, "decision_snapshot": {"thesis": "real winner"},
            "executed_at": datetime(2026, 8, 18, 18, offset, tzinfo=timezone.utc),
        })
    for offset in range(2):
        service.repo.memory["trades"].append({
            "realized_pnl_usd": -500, "decision_snapshot": {"thesis": "real loser"},
            "executed_at": datetime(2026, 8, 18, 19, offset, tzinfo=timezone.utc),
        })
    # One corrected trade with a huge phantom loss -- if this leaked into the
    # metrics, profit_factor would collapse well below 1.0 and the loop would
    # tighten instead of widen.
    service.repo.memory["trades"].append({
        "realized_pnl_usd": -1_000_000,
        "decision_snapshot": {"correction": {"correction_amount_usd": 1_000_000.0}},
        "executed_at": datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
    })

    state = service._ensure_daily_learning(experiment, date(2026, 8, 24))

    assert state["metrics"]["win_rate_percent"] == 75.0
    assert state["metrics"]["profit_factor"] == 12.0
    assert "widened" in state["rationale"][0]
