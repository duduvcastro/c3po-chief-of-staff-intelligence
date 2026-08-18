from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService


def _settings() -> Settings:
    return Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
        r2d2_delayed_quote_protection_grace_minutes=3.0,
    )


def _service() -> R2D2PaperService:
    settings = _settings()
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def _open_position(service: R2D2PaperService, symbol: str, opened_at: datetime) -> tuple[dict, str]:
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    candidate = {
        "market": "NASDAQ", "symbol": symbol, "name": "Delayed Feed Corp", "currency": "USD",
        "stop_price": 145.0, "fundamental_score": 80.0, "technical_score": 70.0,
        "risk_score": 25.0, "composite_score": 78.0,
    }
    service.repo.execute_trade(
        experiment, cycle_id=cycle_id, candidate=candidate, side="BUY", quantity=100,
        signal_price=150.0, fill_price=150.0, fx=1.0, fees=0.0, slippage=0.0,
        reason="test entry", decision=candidate, quote_as_of=opened_at,
    )
    service.repo.memory["positions"][("NASDAQ", symbol)]["opened_at"] = opened_at
    return experiment, cycle_id


def test_delayed_quote_within_grace_period_leaves_position_open() -> None:
    service = _service()
    opened = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    experiment, cycle_id = _open_position(service, "GRACE", opened)
    # First tick starts the "awaiting live quote" clock at t+1min.
    first_now = opened + timedelta(minutes=1)
    first_quote = SimpleNamespace(price=140.0, change_percent=-6.67, status="delayed", as_of=opened)
    service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "GRACE"): first_quote}, first_now,
    )

    # Second tick one minute later -- still well inside the 3-minute grace window.
    second_now = first_now + timedelta(minutes=1)
    second_quote = SimpleNamespace(price=140.0, change_percent=-6.67, status="delayed", as_of=opened)
    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "GRACE"): second_quote}, second_now,
    )

    assert exits == 0
    positions = service.repo.positions(experiment["id"])
    assert len(positions) == 1
    snapshot = positions[0]["strategy_snapshot"]
    assert snapshot["decision_state"] == "awaiting live quote"
    assert snapshot["awaiting_live_quote_minutes"] == 1.0
    # Price shown to the operator does NOT silently jump to the delayed tick.
    assert float(positions[0]["last_price_local"]) == 150.0


def test_delayed_quote_past_grace_period_flags_for_manual_review_without_auto_selling() -> None:
    """Auto-sell on this path is emergency-disabled (2026-08-18): it acted on an
    unvalidated delayed-quote price and produced implausible fills in production
    (SPCX, DINO exited around -85%/-61% off a feed that hadn't moved meaningfully
    moments earlier). Until a sanity check against average_cost/high_water lands,
    this path only flags the position loudly -- it must NOT execute a sale.
    """
    service = _service()
    opened = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    experiment, cycle_id = _open_position(service, "BACKSTOP", opened)
    first_now = opened + timedelta(minutes=1)
    first_quote = SimpleNamespace(price=149.0, change_percent=-0.67, status="delayed", as_of=opened)
    service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "BACKSTOP"): first_quote}, first_now,
    )

    # Second tick: still delayed, now past the 3-minute grace period, price well
    # below the hard stop (0.65% default -> hard stop ~= 149.03) -- must NOT sell.
    second_now = opened + timedelta(minutes=4)
    second_quote = SimpleNamespace(price=140.0, change_percent=-6.67, status="delayed", as_of=opened)
    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "BACKSTOP"): second_quote}, second_now,
    )

    assert exits == 0
    positions = service.repo.positions(experiment["id"])
    assert len(positions) == 1
    assert positions[0]["strategy_snapshot"]["decision_state"] == (
        "delayed quote past grace period -- needs manual review"
    )
    sells = [t for t in service.repo.trades(experiment["id"]) if t["side"] == "SELL"]
    assert sells == []


def test_delayed_quote_past_grace_period_above_hard_stop_stays_open() -> None:
    service = _service()
    opened = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    experiment, cycle_id = _open_position(service, "SAFE", opened)
    first_now = opened + timedelta(minutes=1)
    first_quote = SimpleNamespace(price=149.9, change_percent=-0.07, status="delayed", as_of=opened)
    service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "SAFE"): first_quote}, first_now,
    )

    second_now = opened + timedelta(minutes=4)
    second_quote = SimpleNamespace(price=149.8, change_percent=-0.13, status="delayed", as_of=opened)
    exits = service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "SAFE"): second_quote}, second_now,
    )

    assert exits == 0
    assert len(service.repo.positions(experiment["id"])) == 1


def test_awaiting_live_quote_marker_clears_once_feed_recovers() -> None:
    service = _service()
    opened = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    experiment, cycle_id = _open_position(service, "RECOVER", opened)
    delayed_now = opened + timedelta(minutes=1)
    delayed_quote = SimpleNamespace(price=149.9, change_percent=-0.07, status="delayed", as_of=opened)
    service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "RECOVER"): delayed_quote}, delayed_now,
    )
    assert "awaiting_live_quote_since" in service.repo.positions(experiment["id"])[0]["strategy_snapshot"]

    service._technical_snapshot = lambda item: {  # type: ignore[method-assign]
        "score": 55.0, "atr": 1.0, "atr_percent": 1.0, "vwap": 149.5,
        "ema8": 149.6, "ema20": 149.4, "macd_histogram": 0.1,
        "macd_acceleration": 0.05, "momentum30": 0.2, "price_structure": "range",
        "trend_state": "neutral", "volume_state": "neutral", "data_status": "live",
        "as_of": (opened + timedelta(minutes=2)).isoformat(),
    }
    live_now = opened + timedelta(minutes=2)
    live_quote = SimpleNamespace(price=149.9, change_percent=-0.07, status="live", as_of=live_now)
    service._mark_and_exit(
        experiment, cycle_id, service.repo.positions(experiment["id"]),
        {("NASDAQ", "RECOVER"): live_quote}, live_now,
    )

    snapshot = service.repo.positions(experiment["id"])[0]["strategy_snapshot"]
    assert "awaiting_live_quote_since" not in snapshot
    assert "awaiting_live_quote_minutes" not in snapshot
