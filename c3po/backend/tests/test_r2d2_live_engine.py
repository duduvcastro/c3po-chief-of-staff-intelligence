import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from app import r2d2_lab_live
from app import r2d2_live_engine as engine_module
from app.config import Settings
from app.database import Database
from app.r2d2_live_engine import (FEE_SIDE, Engine, EngineState, LiveEngineStream, MarketView, Member, NEW_YORK,
                                  Position, build_universe, run_session)

DAY = date(2026, 10, 28)


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute, second), tzinfo=NEW_YORK).astimezone(timezone.utc)


def _view(price, vwap, bid, ask, at):
    return MarketView(price=price, trade_at=at, vwap=vwap, bid=bid, ask=ask, quote_at=at)


def test_the_universe_is_the_most_liquid_common_stocks_with_the_rule_floors(tmp_path: Path, monkeypatch) -> None:
    sessions = [date(2026, 10, 1) + timedelta(days=i) for i in range(20)]
    monkeypatch.setattr(engine_module, "previous_sessions", lambda day, count: sessions)
    catalog = [{"Code": "AAA", "Type": "Common Stock", "Exchange": "NASDAQ"},
               {"Code": "BBB", "Type": "Common Stock", "Exchange": "NYSE"},
               {"Code": "CCC", "Type": "Common Stock", "Exchange": "NYSE"},   # below US$ 15 M
               {"Code": "DDD", "Type": "Common Stock", "Exchange": "NASDAQ"},  # price below US$ 5
               {"Code": "EEE", "Type": "ETF", "Exchange": "NYSE ARCA"}]
    bulk = [{"code": "AAA", "close": 100.0, "volume": 1_000_000}, {"code": "BBB", "close": 50.0, "volume": 400_000},
            {"code": "CCC", "close": 20.0, "volume": 100_000}, {"code": "DDD", "close": 4.0, "volume": 10_000_000},
            {"code": "EEE", "close": 400.0, "volume": 10_000_000}]
    calls = []

    def get_json(url, params=None):
        calls.append(url)
        return catalog if url.endswith("exchange-symbol-list/US") else bulk

    members = build_universe(get_json, "https://eodhd.test", "t", DAY, tmp_path)
    assert [(m.symbol, m.market, m.prev_close) for m in members] == [("AAA", "NASDAQ", 100.0), ("BBB", "NYSE", 50.0)]
    build_universe(get_json, "https://eodhd.test", "t", DAY, tmp_path)  # the bulk files are cached per session
    assert sum(1 for url in calls if "eod-bulk" in url) == 20


def _engine(nav: float = 1_000_000.0) -> Engine:
    universe = [Member("AAA", "NASDAQ", 100.0, 50e6), Member("BBB", "NYSE", 50.0, 20e6), Member("CCC", "NYSE", 30.0, 20e6)]
    engine = Engine(EngineState(nav_realized=nav), DAY, universe)
    engine.set_candidates({"AAA": 98.0, "BBB": 50.5, "CCC": 29.0})  # AAA -2%, BBB +1% (not a candidate), CCC -3.3%
    return engine


def test_a_buy_is_a_cross_back_above_the_vwap_at_the_ask_with_a_tight_spread() -> None:
    engine = _engine()
    assert set(engine.candidates) == {"AAA", "CCC"}
    t = _at(9, 40)
    views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}
    assert engine.step(t, lambda s: views.get(s, MarketView())) == []  # both below the VWAP: armed for a cross
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.0, 29.2, t)}  # CCC spread 69 bps
    fills = engine.step(t, lambda s: views.get(s, MarketView()))
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("BUY", "AAA", 98.105)]
    position = engine.state.positions["AAA"]
    assert abs(position.cost_usd - 1_000_000 / 20) < 1e-6 and abs(position.shares * 98.105 * (1 + FEE_SIDE) - position.cost_usd) < 1e-6
    assert engine.signals == 2  # CCC signalled, refused by the spread
    assert engine.step(_at(9, 42), lambda s: views.get(s, MarketView())) == []  # no new cross: no second buy


def test_the_exits_each_second_stop_lock_and_the_last_thirty_seconds() -> None:
    engine = _engine()
    state = engine.state
    for symbol, price in (("S1", 100.0), ("S2", 100.0), ("S3", 100.0)):
        state.positions[symbol] = Position(symbol, "NYSE", 500.0, price, 500.0 * price * (1 + FEE_SIDE), _at(9, 35).isoformat())
        engine.members[symbol] = Member(symbol, "NYSE", 0.0, 0.0)
    t = _at(10, 0)
    marks = {"S1": 99.4, "S2": 100.40, "S3": 100.05}
    fills = engine.step(t, lambda s: _view(marks[s], None, marks[s], marks[s] + 0.01, t) if s in marks else MarketView())
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S1", "venda: stop")]
    assert state.positions["S2"].armed  # +0.29% armed the lock
    t = _at(10, 1)
    marks = {"S2": 100.27, "S3": 100.05}  # S2 back to +0.16%: below peak − 0.10 → lock
    fills = engine.step(t, lambda s: _view(marks[s], None, marks[s], marks[s] + 0.01, t) if s in marks else MarketView())
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: trava de lucro")]
    assert fills[0]["realized_pnl_usd"] > 0
    t = _at(15, 59, 31)
    fills = engine.step(t, lambda s: _view(100.05, None, 100.05, 100.06, t) if s == "S3" else MarketView())
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S3", "venda: positiva nos últimos 30 s")]
    assert not state.positions
    assert abs(state.nav_realized - 1_000_000 - sum(f["realized_pnl_usd"] for f in engine.fills if f["side"] == "SELL")) < 1e-6


def test_no_buy_after_the_last_entry_and_negatives_carry() -> None:
    engine = _engine()
    t = _at(15, 30, 0)
    views = {"AAA": _view(97.0, 98.0, 96.99, 97.01, t)}
    engine.step(t, lambda s: views.get(s, MarketView()))
    views = {"AAA": _view(98.5, 98.0, 98.49, 98.51, _at(15, 30, 1))}
    assert engine.step(_at(15, 30, 1), lambda s: views.get(s, MarketView())) == []
    engine.state.positions["NEG"] = Position("NEG", "NYSE", 10.0, 100.0, 1000.05, _at(10, 0).isoformat(), last_mark=99.8)
    engine.close_session()
    assert engine.state.positions["NEG"].days_held == 1 and engine.state.last_session == DAY.isoformat()


def test_the_document_is_what_the_c3po_validator_accepts(monkeypatch) -> None:
    engine = _engine()
    t = _at(9, 40)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    t = _at(9, 41)
    engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    document = engine.document(t)
    validated = r2d2_lab_live.validate(json.loads(json.dumps(document)), now=t)
    assert validated["config"] == "TIT-2S3-RT" and len(validated["trades"]) == 1
    assert validated["book"]["positions"][0]["symbol"] == "AAA" and validated["cycle"]["entries"] == 1


def test_the_stream_keeps_the_open_the_vwap_and_the_nbbo_of_the_session() -> None:
    stream = LiveEngineStream("")
    stream.start_session(DAY)
    ms = lambda moment: int(moment.timestamp() * 1000)  # noqa: E731
    stream._record(json.dumps({"s": "AAA", "p": 99.0, "v": 100, "t": ms(_at(9, 29, 50)), "ms": "extended-hours"}))
    stream._record(json.dumps({"s": "AAA", "p": 98.0, "v": 100, "t": ms(_at(9, 30, 1)), "ms": "open"}))
    stream._record(json.dumps({"s": "AAA", "p": 100.0, "v": 300, "t": ms(_at(9, 31)), "ms": "open"}))
    stream._record(json.dumps({"s": "AAA", "p": 500.0, "v": 1000, "t": ms(_at(9, 32)), "ms": "open", "dp": True}))
    stream._record_quote(json.dumps({"s": "AAA", "bp": 99.99, "ap": 100.01, "t": ms(_at(9, 31, 2))}))
    view = stream.view("AAA")
    assert stream.opening["AAA"] == 98.0 and view.price == 100.0
    assert abs((view.vwap or 0) - (98 * 100 + 100 * 300) / 400) < 1e-9
    assert (view.bid, view.ask) == (99.99, 100.01)


class _FakeStream:
    def __init__(self):
        self.groups, self.opening = {}, {}

    def set_group(self, name, symbols, priority=50):
        self.groups[name] = list(symbols)

    def start_session(self, day):
        self.opening = {"AAA": 98.0}

    def view(self, symbol):
        return self.views.get(symbol, MarketView()) if hasattr(self, "views") else MarketView()


def test_a_session_runs_publishes_and_resumes_after_a_restart(tmp_path: Path, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    seed = EngineState(nav_realized=931176.94)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: seed)
    clock = {"t": _at(9, 30, 30)}
    stream = _FakeStream()

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        t = clock["t"]
        if t < _at(9, 40):
            stream.views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t)}
        elif t < _at(15, 59, 30):
            stream.views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t)}
        else:
            stream.views = {"AAA": _view(98.3, 98.0, 98.30, 98.31, t)}

    def stop_at_noon(seconds):
        sleep(seconds)
        if clock["t"] >= _at(12, 0):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                    now=lambda: clock["t"], sleep=stop_at_noon)
    stored = r2d2_lab_live.latest_book(database, now=_at(12, 0))
    assert stored is not None and stored[1] == "TIT-2S3-RT" and len(stored[2]["positions"]) == 1
    # the service restarts at noon: the session resumes with its fill, its candidates and its opening NAV
    state = run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                        now=lambda: clock["t"], sleep=sleep)
    assert not state.positions and state.last_session == DAY.isoformat() and state.session == ""
    doc = database.latest_analysis_snapshot("r2d2_lab_live", DAY.isoformat())["outputs"]
    assert [t["side"] for t in doc["trades"]] == ["BUY", "SELL"]
    assert doc["book"]["nav_start_usd"] == 931176.94 and doc["book"]["nav_usd"] > 931176.94
    assert stream.groups["r2d2-live"] == []
