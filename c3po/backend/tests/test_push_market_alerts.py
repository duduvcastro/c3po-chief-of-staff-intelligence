from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.push_market_alerts import PushMarketAlertsService
from app.r2d2_exit_policy_engine import Episode, LedgerFill


SESSION_OPEN = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)  # XNYS session


class _Notifications:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def notify(self, **kwargs) -> dict:
        self.sent.append(kwargs)
        return {"status": "sent"}


def _fill(fill_id: str, side: str, realized: float | None, minute: int) -> LedgerFill:
    price = 100.0
    quantity = 10.0
    gross = quantity * price
    return LedgerFill(
        id=fill_id,
        market="NASDAQ",
        symbol="TEST",
        name="TEST",
        side=side,
        quantity=quantity,
        signal_price_local=price,
        fill_price_local=price,
        fx_to_usd=1.0,
        gross_value_usd=gross,
        fees_usd=gross * 0.0004,
        slippage_usd=0.0,
        realized_pnl_usd=realized,
        reason="test",
        decision_snapshot={},
        executed_at=SESSION_OPEN.replace(minute=30 + minute % 30, hour=13 + minute // 30),
        quote_as_of=SESSION_OPEN,
    )


def _episode(episode_id: str, net: float, closed_minute: int) -> Episode:
    buy = _fill(f"{episode_id}-buy", "BUY", None, closed_minute - 2)
    sell = _fill(f"{episode_id}-sell", "SELL", net, closed_minute)
    return Episode(
        id=f"NASDAQ:TEST:{episode_id}",
        market="NASDAQ",
        symbol="TEST",
        name="TEST",
        fills=(buy, sell),
        opened_at=buy.executed_at,
        closed_at=sell.executed_at,
    )


def _service(episodes: list[Episode]) -> tuple[PushMarketAlertsService, _Notifications]:
    settings = Settings(database_url="", auth_cookie_secure=False)
    notifications = _Notifications()
    service = PushMarketAlertsService(settings, None, notifications)  # type: ignore[arg-type]
    service._closed_episodes_today = lambda now: episodes  # type: ignore[method-assign]
    return service, notifications


def test_sell_win_fires_only_for_net_positive_episodes_with_stable_keys() -> None:
    service, notifications = _service([
        _episode("win", 241.83, 10),
        _episode("loss", -180.0, 12),
    ])

    service.run_once(now=SESSION_OPEN.replace(hour=15, minute=12))

    wins = [item for item in notifications.sent if item["category"] == "sell_win"]
    assert len(wins) == 1
    assert wins[0]["event_key"] == "sell-win:NASDAQ:TEST:win"
    assert "241.83" in wins[0]["body"].replace(",", "")


def test_hourly_rate_fires_once_at_the_hour_with_panel_format() -> None:
    service, notifications = _service([
        _episode("win", 100.0, 10),
        _episode("loss", -50.0, 12),
        _episode("loss2", -30.0, 14),
    ])

    on_the_hour = SESSION_OPEN.replace(hour=17, minute=1)  # 14:01 BRT
    service.run_once(now=on_the_hour)
    service.run_once(now=on_the_hour.replace(minute=3))  # mesmo slot: silêncio

    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert len(hourly) == 1
    assert "1W/3" in hourly[0]["body"]
    assert "33.3%" in hourly[0]["body"]
    assert hourly[0]["event_key"] == "hourly-win-rate:2026-08-20:14"


def test_everything_is_silent_when_market_is_closed_or_no_episodes() -> None:
    service, notifications = _service([_episode("win", 100.0, 10)])
    saturday = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)
    service.run_once(now=saturday)
    assert notifications.sent == []

    service_empty, notifications_empty = _service([])
    service_empty.run_once(now=SESSION_OPEN.replace(hour=15, minute=0))
    assert notifications_empty.sent == []


def test_worker_restart_mid_hour_stays_silent_until_next_boundary() -> None:
    service, notifications = _service([_episode("win", 100.0, 10)])

    service.run_once(now=SESSION_OPEN.replace(hour=17, minute=37))  # 14:37 BRT
    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert hourly == []

    service.run_once(now=SESSION_OPEN.replace(hour=18, minute=1))  # 15:01 BRT
    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert len(hourly) == 1
