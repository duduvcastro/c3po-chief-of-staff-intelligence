import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app import r2d2_lab_live
from app.config import Settings
from app.database import Database

TOKEN = "a" * 64
NEW_YORK = ZoneInfo("America/New_York")


def _fill(**overrides):
    fill = {"id": "TIT-1:AAPL:buy", "side": "BUY", "symbol": "AAPL", "market": "NASDAQ", "quantity": 400.0,
            "price": 250.0, "executed_at": "2026-10-26T09:35:00-04:00", "fees_usd": 1.0, "realized_pnl_usd": None,
            "realized_return_percent": None, "reason": "gap -1%, abaixo do VWAP"}
    fill.update(overrides)
    return fill


def _payload(*fills, day="2026-10-26"):
    return {"schema": r2d2_lab_live.SCHEMA, "day": day, "config": "TIT-1", "trades": list(fills)}


NOW = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def test_authorized_needs_the_configured_token_in_constant_time() -> None:
    assert r2d2_lab_live.authorized("Bearer " + TOKEN, {r2d2_lab_live.TOKEN_ENV: TOKEN})
    assert not r2d2_lab_live.authorized("Bearer " + "b" * 64, {r2d2_lab_live.TOKEN_ENV: TOKEN})
    assert not r2d2_lab_live.authorized(TOKEN, {r2d2_lab_live.TOKEN_ENV: TOKEN})
    assert not r2d2_lab_live.authorized(None, {r2d2_lab_live.TOKEN_ENV: TOKEN})
    # no token configured (or a short one): every request is refused, an empty bearer included
    assert not r2d2_lab_live.authorized("Bearer ", {})
    assert not r2d2_lab_live.authorized("Bearer short", {r2d2_lab_live.TOKEN_ENV: "short"})


def test_validate_keeps_a_session_of_buys_and_sells() -> None:
    sell = _fill(id="TIT-1:AAPL:sell", side="SELL", price=250.5, executed_at="2026-10-26T15:59:31-04:00",
                 realized_pnl_usd=198.0, realized_return_percent=0.198, reason="positiva nos últimos 30 s")
    document = r2d2_lab_live.validate(_payload(_fill(), sell), now=NOW)
    assert document["day"] == "2026-10-26" and len(document["trades"]) == 2
    assert document["trades"][0]["executed_at"] == "2026-10-26T13:35:00+00:00"
    assert document["trades"][1]["realized_pnl_usd"] == 198.0


@pytest.mark.parametrize("payload", [
    {"schema": r2d2_lab_live.SCHEMA, "day": "2026-10-26", "trades": []},
    _payload(_fill(extra=1)),
    _payload(_fill(), _fill()),
    _payload(_fill(side="SHORT")),
    _payload(_fill(market="B3")),
    _payload(_fill(symbol="aapl; drop")),
    _payload(_fill(quantity=0)),
    _payload(_fill(price=True)),
    _payload(_fill(executed_at="2026-10-27T09:35:00-04:00")),
    _payload(_fill(executed_at="2026-10-26T09:35:00")),
    _payload(_fill(realized_pnl_usd=3.0)),
    _payload(_fill(reason="")),
    _payload(day="2026-09-01"),
])
def test_validate_refuses_what_the_log_must_not_show(payload) -> None:
    with pytest.raises(r2d2_lab_live.LabLiveRefused):
        r2d2_lab_live.validate(payload, now=NOW)


def test_parse_refuses_non_json_and_nan() -> None:
    with pytest.raises(r2d2_lab_live.LabLiveRefused):
        r2d2_lab_live.parse(b"not json")
    with pytest.raises(r2d2_lab_live.LabLiveRefused):
        r2d2_lab_live.parse(b'{"x": NaN}')


def test_store_replaces_the_day_and_the_dashboard_reads_the_latest_post() -> None:
    database = Database(Settings(database_url=""))
    r2d2_lab_live.store(database, _payload(_fill()), now=NOW)
    sell = _fill(id="TIT-1:AAPL:sell", side="SELL", executed_at="2026-10-26T10:05:00-04:00",
                 realized_pnl_usd=50.0, realized_return_percent=0.05)
    result = r2d2_lab_live.store(database, _payload(_fill(), sell), now=NOW + timedelta(minutes=1))
    assert result == {"day": "2026-10-26", "config": "TIT-1", "fills": 2}
    trades = r2d2_lab_live.today_trades(database, now=NOW + timedelta(minutes=2))
    assert [trade.id for trade in trades] == ["lab:TIT-1:AAPL:sell", "lab:TIT-1:AAPL:buy"]
    assert trades[0].realized_pnl_usd == 50.0 and trades[1].gross_value_usd == 100000.0
    assert trades[0].reason.startswith("R2D2 ao vivo (TIT-1, papel)")
    # another New York day sees nothing; the lab rows never become valuation predictions
    assert r2d2_lab_live.today_trades(database, now=NOW + timedelta(days=1)) == []
    assert database.latest_analysis_snapshot("valuation_universe", "US_UNIVERSE") is None


def test_the_route_needs_the_bearer_and_feeds_the_daily_log(monkeypatch) -> None:
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    now = datetime.now(timezone.utc)
    day = now.astimezone(NEW_YORK).date().isoformat()
    payload = _payload(_fill(id="TIT-1:ZZZT:buy", symbol="ZZZT", executed_at=now.isoformat()), day=day)
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app_main.app) as client:
        refused = client.post("/api/v1/r2d2/lab-live", json=payload)
        wrong = client.post("/api/v1/r2d2/lab-live", json=payload, headers={"Authorization": "Bearer " + "b" * 64})
        bad = client.post("/api/v1/r2d2/lab-live", content=b"{", headers={"Authorization": "Bearer " + TOKEN})
        huge = client.post("/api/v1/r2d2/lab-live", content=b" " * (r2d2_lab_live.MAX_BODY_BYTES + 1),
                           headers={"Authorization": "Bearer " + TOKEN})
        before = client.get("/api/v1/r2d2").json()
        accepted = client.post("/api/v1/r2d2/lab-live", content=json.dumps(payload),
                               headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
        after = client.get("/api/v1/r2d2").json()
    app_main.r2d2_read_cache.invalidate()
    assert refused.status_code == wrong.status_code == 401
    assert bad.status_code == 422 and huge.status_code == 413
    assert accepted.status_code == 202 and accepted.json() == {"day": day, "config": "TIT-1", "fills": 1}
    assert not any(trade["id"] == "lab:TIT-1:ZZZT:buy" for trade in before["trades"])
    assert after["trades"][0]["id"] == "lab:TIT-1:ZZZT:buy" and after["trades"][0]["market"] == "NASDAQ"


@pytest.mark.parametrize("fields", [
    {"quantity": 10**400},                          # float() overflows: refused, never a 500
    {"quantity": 1e308, "price": 1e308},            # each finite, the product is not
    {"quantity": 1e9, "price": 1e6},                # each within bounds, gross above the bound
    {"price": 1e7},
    {"fees_usd": 1e300},
])
def test_out_of_bounds_numbers_are_refused_and_the_stored_day_survives(monkeypatch, fields) -> None:
    """Codex P2 (#429 6424142588): 422 for every overflow or non-finite derived value, the previous post untouched."""
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    now = datetime.now(timezone.utc)
    day = now.astimezone(NEW_YORK).date().isoformat()
    good = _payload(_fill(id="TIT-1:GOOD:buy", symbol="GOOD", executed_at=now.isoformat()), day=day)
    bad = _payload(_fill(id="TIT-1:BAD:buy", symbol="BAD", executed_at=now.isoformat(), **fields), day=day)
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app_main.app, raise_server_exceptions=False) as client:
        assert client.post("/api/v1/r2d2/lab-live", content=json.dumps(good), headers=headers).status_code == 202
        refused = client.post("/api/v1/r2d2/lab-live", content=json.dumps(bad), headers=headers)
        shown = client.get("/api/v1/r2d2").json()
    app_main.r2d2_read_cache.invalidate()
    assert refused.status_code == 422
    ids = [trade["id"] for trade in shown["trades"]]
    assert "lab:TIT-1:GOOD:buy" in ids and "lab:TIT-1:BAD:buy" not in ids
    assert all(trade["gross_value_usd"] is not None for trade in shown["trades"])


def test_a_declared_oversized_body_is_refused_before_it_is_read(monkeypatch) -> None:
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    with TestClient(app_main.app) as client:
        response = client.post("/api/v1/r2d2/lab-live", content=b"{}", headers={
            "Authorization": "Bearer " + TOKEN, "Content-Length": str(r2d2_lab_live.MAX_BODY_BYTES + 1)})
    assert response.status_code == 413


def test_the_learning_curve_counts_each_lab_session_with_closed_trades() -> None:
    database = Database(Settings(database_url=""))
    sell = _fill(id="TIT-1:AAPL:sell", side="SELL", executed_at="2026-10-26T10:05:00-04:00",
                 realized_pnl_usd=50.0, realized_return_percent=0.05)
    loss = _fill(id="TIT-1:SHEL:sell", symbol="SHEL", side="SELL", executed_at="2026-10-26T11:05:00-04:00",
                 realized_pnl_usd=-20.0, realized_return_percent=-0.02)
    r2d2_lab_live.store(database, _payload(_fill(), sell, loss), now=NOW)
    r2d2_lab_live.store(database, _payload(_fill(id="TIT-1:AAPL:buy2", executed_at="2026-10-23T09:35:00-04:00"),
                                           day="2026-10-23"), now=NOW)  # buys only: no point
    points = r2d2_lab_live.learning_curve(database, now=NOW)
    assert [(p.session_date, p.positive_trades, p.negative_trades, p.positive_percent) for p in points] == [
        ("2026-10-26", 1, 1, 50.0)]


def test_the_dashboard_appends_the_lab_sessions_to_the_learning_curve(monkeypatch) -> None:
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    now = datetime.now(timezone.utc)
    day = now.astimezone(NEW_YORK).date().isoformat()
    sell = _fill(id="TIT-1:ZZLC:sell", symbol="ZZLC", side="SELL", executed_at=now.isoformat(),
                 realized_pnl_usd=12.0, realized_return_percent=0.2)
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app_main.app) as client:
        posted = client.post("/api/v1/r2d2/lab-live", content=json.dumps(_payload(sell, day=day)),
                             headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
        curve = client.get("/api/v1/r2d2").json()["learning_curve"]
    app_main.r2d2_read_cache.invalidate()
    assert posted.status_code == 202
    assert curve[-1]["session_date"] == day and curve[-1]["positive_trades"] >= 1
    assert [point["session_date"] for point in curve] == sorted(point["session_date"] for point in curve)


def _book(**overrides):
    position = {"symbol": "AAPL", "market": "NASDAQ", "quantity": 186.0, "average_cost": 250.0, "last_price": 251.0,
                "cost_usd": 46527.47, "unrealized_pnl_usd": 120.5, "unrealized_return_percent": 0.259,
                "stop_price": 248.6, "opened_at": "2026-10-26T09:35:00-04:00"}
    book = {"nav_start_usd": 930549.46, "nav_usd": 930669.96, "realized_nav_usd": 930549.46, "cash_usd": 884021.99,
            "as_of": "2026-10-26T10:00:00-04:00", "positions": [position]}
    book.update(overrides)
    return book


def test_the_book_is_validated_like_the_fills() -> None:
    document = r2d2_lab_live.validate(dict(_payload(_fill()), book=_book()), now=NOW)
    assert document["book"]["positions"][0]["quantity"] == 186.0
    for bad in (_book(extra=1), _book(nav_usd=0), _book(nav_usd=1e300),
                _book(positions=[dict(_book()["positions"][0], quantity=10**400)]),
                _book(positions=[dict(_book()["positions"][0], market="B3")]),
                _book(positions=[dict(_book()["positions"][0], opened_at="2026-10-26T09:35:00")])):
        with pytest.raises(r2d2_lab_live.LabLiveRefused):
            r2d2_lab_live.validate(dict(_payload(_fill()), book=bad), now=NOW)


def test_one_book_on_every_panel(monkeypatch) -> None:
    """Owner 26/10/2026: NAV, cash, positions, daily P&L, session delta and track record come from the live book."""
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    now = datetime.now(timezone.utc)
    day = now.astimezone(NEW_YORK).date().isoformat()
    book = _book(as_of=now.isoformat(), positions=[dict(_book()["positions"][0], opened_at=now.isoformat())])
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app_main.app) as client:
        assert client.post("/api/v1/r2d2/lab-live", content=json.dumps(dict(_payload(day=day), book=book)),
                           headers=headers).status_code == 202
        dashboard = client.get("/api/v1/r2d2").json()
        live = client.get("/api/v1/r2d2/live-positions").json()
    app_main.r2d2_read_cache.invalidate()
    assert dashboard["book_source"] == "lab_live" and dashboard["status"] == "running"
    assert dashboard["nav_usd"] == dashboard["accounting_total_nav_usd"] == 930669.96
    assert dashboard["cash_usd"] == 884021.99 and dashboard["open_positions"] == 1
    assert dashboard["positions"][0]["symbol"] == "AAPL" and dashboard["positions"][0]["market_value_usd"] == 46686.0
    assert dashboard["daily_pnl_usd"] == 120.5 and dashboard["daily_pnl_date"] == day
    assert dashboard["nav_session_delta"]["total_delta_usd"] == 120.5
    assert dashboard["track_record"][-1]["session_date"] == day and dashboard["track_record"][-1]["nav_usd"] == 930669.96
    assert live["nav_usd"] == 930669.96 and live["cash_usd"] == 884021.99 and live["positions"][0]["symbol"] == "AAPL"


def test_without_a_book_the_v2_panels_stay() -> None:
    database = Database(Settings(database_url=""))
    r2d2_lab_live.store(database, _payload(_fill()), now=NOW)
    assert r2d2_lab_live.latest_book(database, now=NOW) is None


@pytest.mark.parametrize("overrides", [
    {"nav_start_usd": 1e-310, "nav_usd": 1.0},     # Codex P2: finite, within the ceiling, a tiny denominator
    {"nav_usd": 1e-310},
    {"realized_nav_usd": 0.5},
])
def test_a_book_with_a_tiny_nav_is_refused_and_the_stored_book_survives(monkeypatch, overrides) -> None:
    monkeypatch.setenv(r2d2_lab_live.TOKEN_ENV, TOKEN)
    now = datetime.now(timezone.utc)
    day = now.astimezone(NEW_YORK).date().isoformat()
    good = _book(as_of=now.isoformat(), positions=[dict(_book()["positions"][0], opened_at=now.isoformat())])
    headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
    app_main.r2d2_read_cache.invalidate()
    with TestClient(app_main.app, raise_server_exceptions=False) as client:
        assert client.post("/api/v1/r2d2/lab-live", content=json.dumps(dict(_payload(day=day), book=good)),
                           headers=headers).status_code == 202
        refused = client.post("/api/v1/r2d2/lab-live", content=json.dumps(dict(_payload(day=day), book=dict(good, **overrides))),
                              headers=headers)
        dashboard = client.get("/api/v1/r2d2").json()
        live = client.get("/api/v1/r2d2/live-positions").json()
    app_main.r2d2_read_cache.invalidate()
    assert refused.status_code == 422
    assert dashboard["nav_usd"] == 930669.96 and dashboard["daily_return_percent"] is not None
    assert dashboard["nav_session_delta"]["total_delta_percent"] is not None
    assert all(point["daily_return_percent"] is not None for point in dashboard["track_record"])
    assert all(position["allocation_percent"] is not None for position in dashboard["positions"] + live["positions"])


def test_the_opening_book_of_the_next_session_shows_the_evening_before() -> None:
    database = Database(Settings(database_url=""))
    tomorrow = "2026-10-27"
    opening = _book(nav_usd=930549.46, cash_usd=930549.46, positions=[], as_of="2026-10-27T09:30:00-04:00")
    r2d2_lab_live.store(database, dict(_payload(day=tomorrow), book=opening), now=NOW)
    day, config, book, _ = r2d2_lab_live.latest_book(database, now=NOW)
    assert (day, config, book["nav_usd"], book["positions"]) == (tomorrow, "TIT-1", 930549.46, [])


def test_the_evening_before_the_daily_pnl_is_todays_result_not_the_opening_book() -> None:
    """Owner 26/10/2026: with tomorrow's opening book posted, Daily P&L shows today's realized result (+US$ 627.49)."""
    database = Database(Settings(database_url=""))
    evening = datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc)
    shel = _fill(id="TIT-1:SHEL:sell", symbol="SHEL", side="SELL", executed_at="2026-10-26T09:53:30-04:00",
                 realized_pnl_usd=484.74, realized_return_percent=0.484)
    aapl = _fill(id="TIT-1:AAPL:sell", side="SELL", executed_at="2026-10-26T09:35:30-04:00",
                 realized_pnl_usd=142.75, realized_return_percent=0.143)
    shel_buy = _fill(id="TIT-1:SHEL:buy", symbol="SHEL", executed_at="2026-10-26T09:36:00-04:00")
    r2d2_lab_live.store(database, _payload(_fill(), aapl, shel_buy, shel), now=evening)
    opening = _book(nav_start_usd=931176.95, nav_usd=931176.95, realized_nav_usd=931176.95, cash_usd=931176.95,
                    positions=[], as_of="2026-10-27T09:30:00-04:00")
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=opening), now=evening)
    base = app_main.r2d2.dashboard()
    shown = r2d2_lab_live.apply_book(base, database, now=evening, interest=[("2026-10-23", 300.0), ("2026-10-26", 314.31)])
    assert shown.nav_usd == 931176.95 and shown.cash_usd == 931176.95  # interest up to 26/10 is in the opening NAV
    assert shown.daily_pnl_usd == 627.49 and shown.daily_pnl_date == "2026-10-26"
    delta = shown.nav_session_delta  # the session delta adds today's T-bill interest to the trading result
    assert (delta.total_delta_usd, delta.organic_delta_usd, delta.interest_delta_usd) == (941.8, 627.49, 314.31)
    assert delta.previous_total_nav_usd == 930235.15 and delta.interest_status == "posted"
    # the audit of every panel (owner 26/10): ex-interest, today's episodes, the day scoreboard, the cycle footer
    assert shown.accounting_nav_ex_interest_usd == round(931176.95 - base.interest_income_epoch_usd, 2)
    episodes = shown.today_episode_stats
    assert (episodes.session_date, episodes.closed_episodes, episodes.positive_episodes, episodes.win_rate_percent) == (
        "2026-10-26", 2, 2, 100.0)
    assert shown.stats.closed_days == base.stats.closed_days + 1 and shown.stats.positive_days == base.stats.positive_days + 1
    assert shown.stats.positive_transactions == base.stats.positive_transactions + 2
    assert shown.last_cycle is not None and shown.last_cycle.trade_count == 4 and shown.last_cycle.status == "completed"
    assert shown.methodology_version == "R2D2 LIVE · TIT-1"
    assert shown.live_rule is not None and "11:29 ET" in shown.live_rule and shown.live_slots == 1
    assert shown.track_record[-1].session_date == "2026-10-26" and shown.track_record[-1].nav_usd == 931176.95


def test_interest_posted_from_the_books_first_session_is_cash_of_the_book() -> None:
    database = Database(Settings(database_url=""))
    session = datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    book = _book(nav_start_usd=931176.94, nav_usd=931500.0, realized_nav_usd=931176.94, cash_usd=884000.0,
                 as_of="2026-10-27T15:00:00-04:00",
                 positions=[dict(_book()["positions"][0], opened_at="2026-10-27T10:00:00-04:00")])
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=book), now=session)
    interest = [("2026-10-26", 314.31), ("2026-10-27", 300.5)]
    shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=session, interest=interest)
    assert shown.nav_usd == 931800.5 and shown.cash_usd == 884300.5
    assert shown.daily_pnl_usd == 323.06  # trading only
    delta = shown.nav_session_delta
    assert (delta.previous_total_nav_usd, delta.current_total_nav_usd, delta.total_delta_usd) == (931176.94, 931800.5, 623.56)
    live = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=session, interest=interest)
    assert live.nav_usd == 931800.5 and live.cash_usd == 884300.5


def test_the_cycle_counts_are_validated_and_shown() -> None:
    database = Database(Settings(database_url=""))
    doc = dict(_payload(_fill()), cycle={"candidates": 183, "signals": 172, "entries": 2, "closed": 2})
    r2d2_lab_live.store(database, doc, now=NOW)
    shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=NOW) if r2d2_lab_live.latest_book(database, now=NOW) else None
    assert shown is None  # no book: the V2 panels stay
    later = NOW + timedelta(minutes=1)  # a later post of the day (the store keeps the latest by publication time)
    r2d2_lab_live.store(database, dict(doc, book=_book()), now=later)
    shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=later)
    assert shown.last_cycle is not None and (shown.last_cycle.scanned_count, shown.last_cycle.signal_count) == (183, 172)
    for bad in ({"candidates": 1}, {"candidates": -1, "signals": 0, "entries": 0, "closed": 0},
                {"candidates": True, "signals": 0, "entries": 0, "closed": 0}):
        with pytest.raises(r2d2_lab_live.LabLiveRefused):
            r2d2_lab_live.validate(dict(_payload(_fill()), cycle=bad), now=NOW)


def _session_26(database) -> None:
    fills = [_fill(id="T1:AAPL:buy", executed_at="2026-10-26T09:35:00-04:00", quantity=290.617, price=344.1),
             _fill(id="T1:AAPL:sell", side="SELL", executed_at="2026-10-26T09:35:30-04:00", quantity=290.617, price=344.5,
                   realized_pnl_usd=142.74, realized_return_percent=0.14),
             _fill(id="T1:SHEL:buy", symbol="SHEL", market="NYSE", executed_at="2026-10-26T09:36:00-04:00", quantity=937.096,
                   price=106.9),
             _fill(id="T1:SHEL:sell", symbol="SHEL", market="NYSE", side="SELL", executed_at="2026-10-26T09:53:30-04:00",
                   quantity=937.096, price=107.4, realized_pnl_usd=484.74, realized_return_percent=0.48)]
    r2d2_lab_live.store(database, _payload(*fills), now=datetime(2026, 10, 26, 21, 12, tzinfo=timezone.utc))
    opening = _book(nav_start_usd=931176.94, nav_usd=931176.94, realized_nav_usd=931176.94, cash_usd=931176.94,
                    positions=[], as_of="2026-10-27T09:30:00-04:00")
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=opening),
                        now=datetime(2026, 10, 26, 23, 47, tzinfo=timezone.utc))


def test_the_history_survives_the_new_york_date_change_without_a_new_write() -> None:
    """Codex #494 finding 1: the 26/10 point and the scoreboard are the same before and after midnight in New York."""
    database = Database(Settings(database_url=""))
    _session_26(database)
    base = app_main.r2d2.dashboard()
    interest = [("2026-10-26", 314.31)]
    evening = r2d2_lab_live.apply_book(base, database, now=datetime(2026, 10, 26, 23, 50, tzinfo=timezone.utc), interest=interest)
    night = r2d2_lab_live.apply_book(base, database, now=datetime(2026, 10, 27, 5, 0, tzinfo=timezone.utc), interest=interest)
    for shown in (evening, night):
        point = [p for p in shown.track_record if p.session_date == "2026-10-26"]
        assert len(point) == 1 and point[0].nav_usd == 931176.94 and point[0].daily_pnl_usd == 627.48 and point[0].is_final
        assert shown.stats.closed_days == base.stats.closed_days + 1
        assert shown.stats.positive_transactions == base.stats.positive_transactions + 2
        assert shown.nav_usd == 931176.94 and shown.cash_usd == 931176.94
    assert evening.daily_pnl_usd == 627.48 and evening.daily_pnl_date == "2026-10-26"
    assert night.daily_pnl_usd == 0.0 and night.daily_pnl_date == "2026-10-27"  # the new session has not traded yet
    assert night.today_episode_stats.closed_episodes == 0


def test_episodes_are_positions_closed_not_sell_legs() -> None:
    """Codex #494 finding 2: a partial exit and a full exit in two legs are one episode; a re-entry is another."""
    legs = [
        {"symbol": "AAA", "side": "BUY", "quantity": 100.0, "executed_at": "2026-10-26T13:35:00+00:00", "realized_pnl_usd": None},
        {"symbol": "AAA", "side": "SELL", "quantity": 40.0, "executed_at": "2026-10-26T13:40:00+00:00", "realized_pnl_usd": 10.0},
        {"symbol": "AAA", "side": "SELL", "quantity": 60.0, "executed_at": "2026-10-26T13:45:00+00:00", "realized_pnl_usd": -4.0},
        {"symbol": "AAA", "side": "BUY", "quantity": 50.0, "executed_at": "2026-10-26T14:00:00+00:00", "realized_pnl_usd": None},
        {"symbol": "AAA", "side": "SELL", "quantity": 50.0, "executed_at": "2026-10-26T14:30:00+00:00", "realized_pnl_usd": -3.0},
        {"symbol": "BBB", "side": "SELL", "quantity": 10.0, "executed_at": "2026-10-26T13:31:00+00:00", "realized_pnl_usd": 2.0},
        {"symbol": "CCC", "side": "BUY", "quantity": 10.0, "executed_at": "2026-10-26T15:00:00+00:00", "realized_pnl_usd": None},
        {"symbol": "CCC", "side": "SELL", "quantity": 4.0, "executed_at": "2026-10-26T15:10:00+00:00", "realized_pnl_usd": 1.0},
    ]
    closed = r2d2_lab_live._closed_episodes({"2026-10-26": {"trades": legs}}, "2026-10-26")
    # AAA twice (+6 in two legs, then -3); BBB's sell has no proven opening: not counted; CCC still open
    assert sorted(closed) == [-3.0, 6.0]


def test_a_position_carried_across_sessions_closes_once_with_its_whole_result() -> None:
    """Codex #496 finding 1: BUY 10 yesterday, SELL 5 today (+1) leaves 5 open: no episode closed; the last SELL 5
    (-0.5) closes ONE episode of +0.5, the same as the canonical consumer."""
    yesterday = {"trades": [{"symbol": "AAA", "side": "BUY", "quantity": 10.0, "executed_at": "2026-10-26T14:00:00+00:00",
                             "realized_pnl_usd": None}]}
    first = {"symbol": "AAA", "side": "SELL", "quantity": 5.0, "executed_at": "2026-10-27T14:00:00+00:00", "realized_pnl_usd": 1.0}
    last = {"symbol": "AAA", "side": "SELL", "quantity": 5.0, "executed_at": "2026-10-27T15:00:00+00:00", "realized_pnl_usd": -0.5}
    assert r2d2_lab_live._closed_episodes({"2026-10-26": yesterday, "2026-10-27": {"trades": [first]}}, "2026-10-27") == []
    assert r2d2_lab_live._closed_episodes({"2026-10-26": yesterday, "2026-10-27": {"trades": [first, last]}}, "2026-10-27") == [0.5]
    # the episode belongs to the day it closed: yesterday's view counts nothing
    assert r2d2_lab_live._closed_episodes({"2026-10-26": yesterday}, "2026-10-26") == []


def test_an_opening_book_has_one_nav_and_both_routes_show_the_same_nav_and_allocation() -> None:
    """Codex #496 finding 2: a book for a session not yet open with NAVs that differ is refused; a coherent one gives the
    same NAV and allocation on the dashboard and on live positions, before and after the New York date change."""
    database = Database(Settings(database_url=""))
    evening = datetime(2026, 10, 27, 23, 50, tzinfo=timezone.utc)
    position = dict(_book()["positions"][0], quantity=1.0, last_price=100.0, average_cost=100.0, cost_usd=100.0,
                    unrealized_pnl_usd=0.0, unrealized_return_percent=0.0, opened_at="2026-10-27T15:00:00-04:00")
    incoherent = _book(nav_start_usd=100.0, nav_usd=110.0, realized_nav_usd=100.0, cash_usd=10.0, positions=[position],
                       as_of="2026-10-28T09:30:00-04:00")
    with pytest.raises(r2d2_lab_live.LabLiveRefused):
        r2d2_lab_live.validate(dict(_payload(day="2026-10-28"), book=incoherent), now=evening)
    opening = dict(incoherent, nav_usd=100.0, cash_usd=0.0)
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-28"), book=opening), now=evening)
    interest = [("2026-10-27", 10.0)]
    for clock in (evening, datetime(2026, 10, 28, 5, 0, tzinfo=timezone.utc)):
        shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=clock, interest=interest)
        live = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=clock, interest=interest)
        assert shown.nav_usd == live.nav_usd == 110.0
        assert shown.positions[0].allocation_percent == live.positions[0].allocation_percent == round(100 / 110 * 100, 4)


def test_allocation_uses_the_effective_nav_with_interest() -> None:
    """Codex #494 finding 3: the allocation's denominator is the NAV both routes return after interest."""
    database = Database(Settings(database_url=""))
    session = datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    book = _book(nav_start_usd=931176.94, nav_usd=931500.0, realized_nav_usd=931176.94, cash_usd=884000.0,
                 as_of="2026-10-27T15:00:00-04:00", positions=[dict(_book()["positions"][0], opened_at="2026-10-27T10:00:00-04:00")])
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=book), now=session)
    interest = [("2026-10-27", 300.5)]
    shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=session, interest=interest)
    live = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=session, interest=interest)
    expected = round(186.0 * 251.0 / 931800.5 * 100, 4)
    assert shown.nav_usd == live.nav_usd == 931800.5
    assert shown.positions[0].allocation_percent == live.positions[0].allocation_percent == expected


def test_the_screen_shows_the_engines_own_marks_sorted_by_ticker_with_the_stop_level() -> None:
    """Owner 30/10/2026: ASST and FTI showed +0.10% on the screen, re-marked on the feed's last trade, while the engine
    (the bid of Massive's NBBO net of the sale's fee) never armed the lock — "temos q acertar isso". The engine's own marks
    (migration 055) are what the screen shows, the table runs by ticker, the STOP column carries the level the rule sells
    at, and the screen asks every tenth of a second during the session."""
    database = Database(Settings(database_url=""))
    session = datetime(2026, 10, 27, 14, 43, tzinfo=timezone.utc)  # 10:43 ET
    zzz = dict(_book()["positions"][0], symbol="ZZZ", market="NYSE", quantity=1000.0, average_cost=50.0, last_price=50.05,
               cost_usd=50002.5, unrealized_pnl_usd=47.5, unrealized_return_percent=0.095, stop_price=49.80,
               opened_at="2026-10-27T10:00:00-04:00")
    aaa = dict(zzz, symbol="AAA", unrealized_pnl_usd=-10.0, unrealized_return_percent=-0.02)
    book = _book(nav_start_usd=931176.94, nav_usd=931214.44, realized_nav_usd=931176.94, cash_usd=831171.94,
                 as_of="2026-10-27T10:43:00-04:00", positions=[zzz, aaa])
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=book), now=session)
    tick_at = session + timedelta(seconds=40)

    def quotes(references):
        return {"ZZZ": (50.07, tick_at), "AAA": (50.06, tick_at)}  # the feed's last trades
    mark = {"symbol": "ZZZ", "bid": 50.06, "net_percent": 0.112, "armed": True, "stop_price": 50.0525, "stop_percent": 0.10,
            "marked_at": tick_at.isoformat(), "opened_at": "2026-10-27T10:00:00-04:00", "quantity": 1000.0, "cost_usd": 50002.5}
    database.save_r2d2_live_marks("2026-10-27", tick_at, [mark])
    live = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert [position.symbol for position in live.positions] == ["AAA", "ZZZ"]  # by ticker
    assert live.refresh_seconds == r2d2_lab_live.LIVE_REFRESH_SECONDS == 0.1
    marked, ticked = live.positions[1], live.positions[0]
    assert marked.last_price_local == 50.06 and marked.unrealized_return_percent == 0.112  # the engine's bid and net
    assert marked.stop_price_local == 50.0525 and marked.stop_lock_percent == 0.10 and marked.decision_state == "trava armada"
    assert abs(marked.unrealized_pnl_usd - 50002.5 * 0.112 / 100) < 1e-6
    assert ticked.last_price_local == 50.06 and ticked.decision_state == "hold"  # no engine mark: the feed's tick stays
    expected = (1000.0 * 49.80 * (1 - r2d2_lab_live.SELL_FEE) / 50002.5 - 1) * 100  # the level of the book's stop price
    assert ticked.stop_lock_percent == round(expected, 4) and ticked.stop_lock_percent < 0
    stale = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database,
                                          now=tick_at + timedelta(seconds=r2d2_lab_live.MARKS_FRESH_SECONDS + 1), quotes=quotes)
    assert {position.symbol: position.last_price_local for position in stale.positions} == {"AAA": 50.06, "ZZZ": 50.07}
    database.save_r2d2_live_marks("2026-10-26", tick_at, [{"symbol": "ZZZ", "bid": 1.0, "net_percent": 5.0, "armed": True,
                                                            "stop_price": 1.0, "stop_percent": 0.1, "marked_at": None}])
    other = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert {position.symbol: position.last_price_local for position in other.positions} == {"AAA": 50.06, "ZZZ": 50.07}
    # a name the engine has not marked yet (restored after a restart: no instant) keeps the live tick, never shown as fresh
    database.save_r2d2_live_marks("2026-10-27", tick_at, [dict(mark, marked_at=None)])
    unmarked = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert {position.symbol: position.last_price_local for position in unmarked.positions} == {"AAA": 50.06, "ZZZ": 50.07}
    # Codex 6528658844: a mark of ANOTHER position of the same ticker (a sale and a re-buy inside the window, in either
    # direction) is never laid on this one: another opening, other shares or another cost keep the live tick
    for other in (dict(mark, opened_at="2026-10-27T10:30:00-04:00"), dict(mark, quantity=900.0), dict(mark, cost_usd=45000.0),
                  {key: value for key, value in mark.items() if key != "opened_at"}):
        database.save_r2d2_live_marks("2026-10-27", tick_at, [other])
        shown = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
        zzz_shown = next(position for position in shown.positions if position.symbol == "ZZZ")
        assert zzz_shown.last_price_local == 50.07 and zzz_shown.decision_state == "hold", other
    database.save_r2d2_live_marks("2026-10-27", tick_at, [dict(mark, opened_at="2026-10-27T14:00:00+00:00")])  # same instant
    same = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert next(position for position in same.positions if position.symbol == "ZZZ").last_price_local == 50.06
    after_close = datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    assert r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=after_close, quotes=quotes).refresh_seconds == 1


def test_the_screen_and_the_engine_charge_the_same_sale_fee() -> None:
    from app import r2d2_live_engine

    assert r2d2_lab_live.SELL_FEE == r2d2_live_engine.FEE_SIDE


def test_open_positions_move_with_the_live_tick_during_the_session() -> None:
    """Owner 27/10/2026: the price on the screen in real time. A live tick re-marks value, result and NAV on both
    routes; cash never moves; after the close (or without a tick) the lab's own mark stays."""
    database = Database(Settings(database_url=""))
    session = datetime(2026, 10, 27, 14, 43, tzinfo=timezone.utc)  # 10:43 ET
    position = dict(_book()["positions"][0], symbol="BTI", market="NYSE", quantity=782.042, average_cost=59.55, last_price=59.57,
                    cost_usd=46558.84, unrealized_pnl_usd=16.45, unrealized_return_percent=0.035, opened_at="2026-10-27T10:00:00-04:00")
    book = _book(nav_start_usd=931176.94, nav_usd=931193.39, realized_nav_usd=931176.94, cash_usd=884618.10,
                 as_of="2026-10-27T10:43:00-04:00", positions=[position])
    r2d2_lab_live.store(database, dict(_payload(day="2026-10-27"), book=book), now=session)
    tick_at = session + timedelta(seconds=40)

    def quotes(references):
        assert references == {"BTI": 59.57}
        return {"BTI": (59.70, tick_at)}

    move = 782.042 * (59.70 - 59.57)
    live = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert live.positions[0].last_price_local == 59.70 and live.positions[0].quote_status == "live"
    assert live.positions[0].quote_freshness == "fresh" and live.positions[0].quote_age_seconds == 1.0
    assert live.nav_usd == round(931193.39 + move, 2) and live.cash_usd == 884618.10
    assert abs(live.positions[0].unrealized_pnl_usd - (16.45 + move)) < 1e-6
    shown = r2d2_lab_live.apply_book(app_main.r2d2.dashboard(), database, now=tick_at + timedelta(seconds=1), quotes=quotes)
    assert shown.nav_usd == live.nav_usd and shown.daily_pnl_usd == round(931193.39 + move - 931176.94, 2)
    after_close = datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    closed = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=after_close, quotes=quotes)
    assert closed.positions[0].last_price_local == 59.57 and closed.nav_usd == 931193.39
    no_tick = r2d2_lab_live.apply_book_live(app_main.r2d2.live_positions(), database, now=tick_at, quotes=lambda refs: {})
    assert no_tick.positions[0].last_price_local == 59.57 and no_tick.positions[0].quote_status == "lab"
