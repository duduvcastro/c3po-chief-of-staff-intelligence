from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import r2d2 as r2d2_module
from app import r2d2_strategy
from app.config import Settings
from app.database import Database
from app.r2d2 import R2D2PaperService


def _service() -> R2D2PaperService:
    settings = Settings(
        database_url="",
        r2d2_start_date="2026-08-17",
        r2d2_checkpoint_days=90,
        r2d2_starting_capital_usd=1_000_000,
    )
    return R2D2PaperService(settings, Database(settings), None, None, None)  # type: ignore[arg-type]


def test_mandate_describes_loss_only_same_session_reentry_guard() -> None:
    experiment = _service().ensure_initialized()

    assert experiment["mandate"]["turnover_policy"]["full_exit_reentry_policy"] == (
        "loss exits block same-symbol re-entry for the rest of the Sao Paulo "
        "session; profit exits remain subject only to the regular cooldown"
    )


def test_buy_rebases_low_entry_stop_to_the_fresh_fill_quote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    experiment = service.ensure_initialized()
    cycle_id = service.repo.start_cycle(experiment["id"], ["NASDAQ"])
    fill_now = datetime(2026, 8, 24, 13, 56, 3, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return fill_now

    monkeypatch.setattr(r2d2_module, "datetime", FrozenDateTime)
    fresh_as_of = FrozenDateTime(
        2026, 8, 24, 13, 56, 0, 142000, tzinfo=timezone.utc,
    )
    monkeypatch.setattr(
        service,
        "dashboard",
        lambda: SimpleNamespace(
            daily_return_percent=0.0,
            nav_usd=1_000_000.0,
            cash_usd=1_000_000.0,
            positions=[],
            gross_exposure_usd=0.0,
        ),
    )
    service.realtime = SimpleNamespace(
        stream=SimpleNamespace(
            quote=lambda symbol: SimpleNamespace(
                price=218.39,
                as_of=fresh_as_of,
            ),
        ),
    )
    candidate = {
        "market": "NASDAQ",
        "symbol": "LOW",
        "name": "Lowe's Companies Inc",
        "currency": "USD",
        "price": 219.14,
        "stop_price": 218.26344,
        "quote_status": "live",
        "quote_as_of": datetime(2026, 8, 24, 13, 54, tzinfo=timezone.utc),
        "technical_indicators": {"atr": 0.643205, "atr_percent": 0.294},
        "composite_score": 75.0,
        "confidence": 75.0,
        "technical_score": 70.0,
        "risk_score": 30.0,
        "fundamental_score": 80.0,
        "thesis": "Named LOW regression",
    }

    trade = service._buy(experiment, cycle_id, candidate, [])

    assert trade is not None
    assert trade["signal_price_local"] == pytest.approx(218.39)
    assert trade["fill_price_local"] == pytest.approx(218.60839)
    average_cost = trade["gross_value_usd"] / trade["quantity"]
    average_cost += trade["fees_usd"] / trade["quantity"]
    expected_stop = max(
        r2d2_strategy.entry_stop_quote_price(218.39, 0.643205),
        r2d2_strategy.hard_stop_quote_price(average_cost, 0.65),
    )
    assert trade["decision_snapshot"]["stop_price"] == pytest.approx(expected_stop)
    assert trade["decision_snapshot"]["stop_price"] < 218.26344
    position = service.repo.positions(experiment["id"])[0]
    assert position["hard_stop_price_local"] == pytest.approx(expected_stop)
