from __future__ import annotations

from datetime import date, datetime, timezone

from app.config import Settings
from app.push_market_alerts import PushMarketAlertsService
from app.r2d2 import _episode_summary_from_trades


SESSION = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)  # XNYS session
SESSION_DATE = date(2026, 8, 20)


class _Notifications:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def notify(self, **kwargs) -> dict:
        self.sent.append(kwargs)
        return {"status": "sent"}


def _trade(trade_id: str, side: str, quantity: float, realized, minute: int, snapshot=None):
    return {
        "id": trade_id,
        "market": "NASDAQ",
        "symbol": trade_id.split("-")[0].upper(),
        "side": side,
        "quantity": quantity,
        "realized_pnl_usd": realized,
        "decision_snapshot": snapshot or {},
        "executed_at": SESSION.replace(hour=14, minute=minute),
    }


def test_panel_walk_details_match_the_panel_counters_including_flats_and_corrections():
    trades = [
        _trade("win-buy", "BUY", 10, None, 1),
        _trade("win-sell", "SELL", 10, 241.83, 5),
        _trade("loss-buy", "BUY", 10, None, 2),
        _trade("loss-sell", "SELL", 10, -180.0, 6),
        _trade("flat-buy", "BUY", 10, None, 3),
        _trade("flat-sell", "SELL", 10, 0.0, 7),
        _trade("corr-buy", "BUY", 10, None, 4),
        _trade("corr-sell", "SELL", 10, 999.0, 8, snapshot={"correction": {"operator": "Dudu"}}),
    ]

    summary = _episode_summary_from_trades(trades, SESSION_DATE)

    assert summary["decided_episodes"] == 2  # flats fora do denominador
    assert summary["positive_episodes"] == 1
    assert summary["flat_episodes"] == 1
    details = summary["closed_episode_details"]
    assert len(details) == summary["closed_episodes"]
    winners = [item for item in details if item["net_realized_pnl_usd"] > 0]
    assert [item["symbol"] for item in winners] == ["WIN"]
    assert winners[0]["episode_id"] == "NASDAQ:WIN:win-buy"
    # Episódio corrigido é EXCLUÍDO por inteiro: nem contagem, nem detalhe,
    # nem sino — a mesma regra do painel, por construção.
    assert all(item["symbol"] != "CORR" for item in details)


def _service(summary: dict | None):
    settings = Settings(database_url="", auth_cookie_secure=False)
    notifications = _Notifications()
    service = PushMarketAlertsService(settings, None, notifications)  # type: ignore[arg-type]
    service._panel_summary = lambda now: summary  # type: ignore[method-assign]
    return service, notifications


def _summary(details: list[dict], positive: int, decided: int, rate: float) -> dict:
    return {
        "decided_episodes": decided,
        "positive_episodes": positive,
        "win_rate_percent": rate,
        "closed_episode_details": details,
    }


def _win_detail(symbol: str, net: float) -> dict:
    return {
        "episode_id": f"NASDAQ:{symbol}:{symbol.lower()}-buy",
        "market": "NASDAQ",
        "symbol": symbol,
        "net_realized_pnl_usd": net,
        "closed_at": SESSION,
    }


def test_sell_win_survives_the_closing_bell_inside_the_grace_window():
    service, notifications = _service(
        _summary([_win_detail("DINO", 241.83)], 1, 1, 100.0)
    )
    service._last_hourly_key = service._hourly_key(SESSION.replace(hour=20, minute=0))

    after_close = SESSION.replace(hour=20, minute=0, second=1)  # 20:00:01Z
    service.run_once(now=after_close)

    wins = [item for item in notifications.sent if item["category"] == "sell_win"]
    assert len(wins) == 1
    assert wins[0]["event_key"] == "sell-win:NASDAQ:DINO:dino-buy"

    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert hourly == []  # mercado fechado: taxa horária não dispara

    service2, notifications2 = _service(
        _summary([_win_detail("LATE", 10.0)], 1, 1, 100.0)
    )
    service2.run_once(now=SESSION.replace(hour=20, minute=31))  # após a graça
    assert notifications2.sent == []


def test_hourly_fires_once_per_boundary_with_panel_numbers_verbatim():
    service, notifications = _service(_summary([], 4, 15, 26.67))
    service._last_hourly_key = service._hourly_key(SESSION.replace(hour=16, minute=59))

    service.run_once(now=SESSION.replace(hour=17, minute=0, second=30))
    service.run_once(now=SESSION.replace(hour=17, minute=3))

    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert len(hourly) == 1
    assert "4W/15 episódios decididos = 26.7%" in hourly[0]["body"]
    assert hourly[0]["event_key"] == "hourly-win-rate:2026-08-20:14"


def test_process_born_mid_hour_stays_mute_until_the_next_boundary():
    service, notifications = _service(_summary([], 1, 3, 33.33))
    birth = SESSION.replace(hour=17, minute=1)  # nasce às 14:01 BRT
    service._last_hourly_key = service._hourly_key(birth)

    service.run_once(now=birth)
    service.run_once(now=SESSION.replace(hour=17, minute=30))
    assert [i for i in notifications.sent if i["category"] == "hourly_win_rate"] == []

    service.run_once(now=SESSION.replace(hour=18, minute=0, second=45))
    hourly = [i for i in notifications.sent if i["category"] == "hourly_win_rate"]
    assert len(hourly) == 1
    assert hourly[0]["event_key"] == "hourly-win-rate:2026-08-20:15"


def test_silent_on_weekends_and_with_zero_decided_episodes():
    service, notifications = _service(_summary([], 0, 0, 0.0))
    service.run_once(now=datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc))  # sábado
    assert notifications.sent == []

    service._last_hourly_key = "seed"
    service.run_once(now=SESSION.replace(hour=15, minute=0))
    assert notifications.sent == []  # zero decididos: hora consumida em silêncio
