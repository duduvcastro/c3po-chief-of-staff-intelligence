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
