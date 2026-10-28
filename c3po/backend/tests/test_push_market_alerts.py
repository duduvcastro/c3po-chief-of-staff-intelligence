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


def test_each_hour_reports_the_full_day_accumulated_rate_not_the_hourly_increment():
    service, notifications = _service(None)
    service._last_hourly_key = service._hourly_key(SESSION.replace(hour=16, minute=59))
    summaries = {
        17: _summary([], 1, 2, 50.0),
        18: _summary([], 3, 5, 60.0),
    }
    service._panel_summary = lambda now: summaries[now.hour]  # type: ignore[method-assign]

    service.run_once(now=SESSION.replace(hour=17, minute=0, second=5))
    service.run_once(now=SESSION.replace(hour=18, minute=0, second=5))

    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert len(hourly) == 2
    assert "Acumulado do pregão: 1W/2 episódios decididos = 50.0%" in hourly[0]["body"]
    assert "Acumulado do pregão: 3W/5 episódios decididos = 60.0%" in hourly[1]["body"]
    assert "2W/3" not in hourly[1]["body"]  # incremento isolado da segunda hora


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


def test_observer_only_reads_the_experiment_and_is_silent_when_absent(monkeypatch):
    import app.push_market_alerts as module

    calls = {"experiment": 0}

    class _ReadOnlyRepo:
        def __init__(self, database):
            pass

        def experiment(self, code):
            calls["experiment"] += 1
            return None  # experimento ausente

        def ensure_experiment(self, settings):
            raise AssertionError("observer must NEVER run the initialization upsert")

    monkeypatch.setattr(module, "R2D2Repository", _ReadOnlyRepo)
    settings = Settings(database_url="", auth_cookie_secure=False)
    notifications = _Notifications()
    service = PushMarketAlertsService(settings, None, notifications)  # type: ignore[arg-type]

    service.run_once(now=SESSION.replace(hour=15, minute=0))

    assert calls["experiment"] == 1
    assert notifications.sent == []  # ausente = silêncio, jamais criação


def test_the_live_book_feeds_the_sell_win_and_hourly_pushes():
    """Since 26/10/2026 the R2D2 book is the live lab book: the pushes read the panels' own walk over its documents
    (the paused V2 experiment has no trades any more, so the pushes had gone silent)."""
    from datetime import timedelta

    from app import r2d2_lab_live
    from app.database import Database
    from tests.test_r2d2_lab_live import _fill, _payload

    database = Database(Settings(database_url=""))
    now = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)  # 14:00 ET, a session
    win = _fill(id="TIT-1:AAPL:sell", side="SELL", price=250.5, executed_at="2026-10-26T13:59:31-04:00",
                realized_pnl_usd=198.0, realized_return_percent=0.198, reason="trava de lucro")
    loss_buy = _fill(id="TIT-1:MSFT:buy", symbol="MSFT", executed_at="2026-10-26T10:00:00-04:00")
    loss = _fill(id="TIT-1:MSFT:sell", symbol="MSFT", side="SELL", price=240.0, executed_at="2026-10-26T11:00:00-04:00",
                 realized_pnl_usd=-120.0, realized_return_percent=-0.5, reason="stop")
    r2d2_lab_live.store(database, _payload(_fill(), win, loss_buy, loss), now=now)
    summary = r2d2_lab_live.episode_summary(database, now=now)
    assert summary is not None and summary["decided_episodes"] == 2 and summary["positive_episodes"] == 1
    assert summary["win_rate_percent"] == 50.0
    notifications = _Notifications()
    service = PushMarketAlertsService(Settings(database_url=""), database, notifications)  # type: ignore[arg-type]
    service._last_hourly_key = "2026-10-26:14"  # the previous hour already reported
    service.run_once(now)
    sells = [item for item in notifications.sent if item["category"] == "sell_win"]
    hourly = [item for item in notifications.sent if item["category"] == "hourly_win_rate"]
    assert [item["body"].split(":")[0] for item in sells] == ["AAPL"] and sells[0]["event_key"] == "sell-win:lab:2026-10-26:TIT-1:AAPL:sell"
    assert len(hourly) == 1 and "1W/2" in hourly[0]["body"] and "50.0%" in hourly[0]["body"]
    assert r2d2_lab_live.episode_summary(database, now=now + timedelta(days=1)) is None  # no document today: V2 answers



def test_a_fill_id_reused_on_another_session_still_pushes_its_own_winner_once():
    """Codex #503: fill ids are unique within a day's document only. Two sessions reusing 'TIT-1:AAPL:sell' are two
    winners (two pushes); repeated ticks and an observer restart of the same session add none."""
    from datetime import timedelta

    from app import r2d2_lab_live
    from app.database import Database
    from app.push_notifications import PushNotificationService
    from tests.test_r2d2_lab_live import _fill, _payload

    database = Database(Settings(database_url=""))
    delivered: list[str] = []

    class _Recording(PushNotificationService):
        def notify(self, **kwargs):  # the real claim of the event key, a recording transport
            if self.database.claim_push_notification_event(event_key=kwargs["event_key"], category=kwargs["category"],
                                                           title=kwargs["title"], body=kwargs["body"],
                                                           deep_link=kwargs.get("deep_link") or "", at=datetime.now(timezone.utc)):
                delivered.append(kwargs["event_key"])
            return {"status": "sent"}
    settings = Settings(database_url="")
    for day, net in (("2026-10-26", 20.0), ("2026-10-27", 30.0)):
        now = datetime.fromisoformat(day + "T18:00:00+00:00")
        buy = _fill(executed_at=day + "T09:35:00-04:00")
        sell = _fill(id="TIT-1:AAPL:sell", side="SELL", price=250.5, executed_at=day + "T13:00:00-04:00",
                     realized_pnl_usd=net, realized_return_percent=0.1, reason="trava de lucro")
        r2d2_lab_live.store(database, _payload(buy, sell, day=day), now=now)
        for restart in range(2):  # a restarted observer re-reads the same episode
            service = PushMarketAlertsService(settings, database, _Recording(settings, database))
            for tick in range(3):
                service.run_once(now + timedelta(seconds=60 * tick))
    winners = [key for key in delivered if key.startswith("sell-win:")]
    assert winners == ["sell-win:lab:2026-10-26:TIT-1:AAPL:sell", "sell-win:lab:2026-10-27:TIT-1:AAPL:sell"]
