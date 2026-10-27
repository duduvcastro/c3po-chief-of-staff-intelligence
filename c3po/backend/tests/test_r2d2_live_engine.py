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
        self.groups, self.opening, self.subscribed_history = {}, {}, []

    def set_group(self, name, symbols, priority=50):
        self.groups[name] = list(symbols)
        if symbols:
            self.subscribed_history.append(list(symbols))

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


def test_the_status_summary_has_no_symbols(tmp_path: Path, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    engine_module.save_state(database, EngineState(nav_realized=931176.94, last_session="2026-10-27"), _at(9, 0))
    summary = engine_module.status(database, _at(9, 1))
    assert summary["nav_realized"] == 931176.94 and summary["positions"] == 0 and summary["last_session"] == "2026-10-27"
    assert "AAA" not in json.dumps(summary)


def test_buys_are_checked_once_per_minute_close_and_exits_every_second() -> None:
    """The measured signal: a VWAP cross on a minute close, not every second (owner 27/10, the noise around the VWAP)."""
    engine = _engine()
    below = lambda t: {"AAA": _view(97.9, 98.0, 97.89, 97.91, t)}  # noqa: E731
    above = lambda t: {"AAA": _view(98.1, 98.0, 98.095, 98.105, t)}  # noqa: E731
    t = _at(9, 40, 0)
    engine.step(t, lambda s: below(t).get(s, MarketView()))
    t = _at(9, 40, 30)  # the same minute: the cross waits for the next minute close
    assert engine.step(t, lambda s: above(t).get(s, MarketView())) == []
    t = _at(9, 41, 0)
    assert [f["symbol"] for f in engine.step(t, lambda s: above(t).get(s, MarketView()))] == ["AAA"]
    t = _at(9, 41, 5)  # an exit is checked at any second
    fills = engine.step(t, lambda s: _view(97.5, 98.0, 97.5, 97.51, t) if s == "AAA" else MarketView())
    assert [(f["side"], f["reason"].split(",")[0]) for f in fills] == [("SELL", "venda: stop")]


# ------------------------------------------------------------------ Codex #500 P2 regressions
def _stream_with_session() -> LiveEngineStream:
    stream = LiveEngineStream("")
    stream.start_session(DAY)
    return stream


def test_p2_1_the_signal_reads_the_completed_minute_not_the_open_one() -> None:
    """Codex probe: 09:40 closes at 99 below a VWAP of ~99.82; a tick at 09:41:00.100 of 101 must not make the 09:41
    decision buy: the 09:40 close is still below."""
    stream = _stream_with_session()
    stream.record_trade("AAA", 100.0, 1000, _at(9, 35))
    stream.record_trade("AAA", 99.0, 100, _at(9, 40, 30))
    stream.record_quote("AAA", 100.99, 101.01, _at(9, 41))
    stream.record_trade("AAA", 101.0, 10, _at(9, 41) + timedelta(milliseconds=100))
    engine = _engine()
    engine.state.candidates = {"AAA": -2.0}
    engine.state.below = {"AAA": True}
    decision = _at(9, 41) + timedelta(milliseconds=500)
    assert stream.signal_view("AAA", 9 * 60 + 41) == (99.0, (100.0 * 1000 + 99.0 * 100) / 1100)
    assert engine.step(decision, stream.view, stream.signal_view) == []
    stream.record_trade("AAA", 101.5, 10, _at(9, 42) + timedelta(milliseconds=50))  # 09:41 closed at 101 above the VWAP
    stream.record_quote("AAA", 101.49, 101.51, _at(9, 42))
    fills = engine.step(_at(9, 42) + timedelta(milliseconds=500), stream.view, stream.signal_view)
    assert [(f["symbol"], f["price"]) for f in fills] == [("AAA", 101.51)]


def test_p2_5_late_messages_never_overwrite_newer_ones() -> None:
    stream = _stream_with_session()
    stream.record_quote("AAA", 101.0, 101.02, _at(10, 0, 5))
    stream.record_quote("AAA", 98.0, 98.02, _at(10, 0, 1))  # late: dropped
    stream.record_trade("AAA", 101.0, 10, _at(10, 0, 5))
    stream.record_trade("AAA", 98.0, 10, _at(10, 0, 1))  # late: counts in the VWAP, never moves the last price
    view = stream.view("AAA")
    assert (view.bid, view.ask, view.price) == (101.0, 101.02, 101.0)
    assert abs((view.vwap or 0) - 99.5) < 1e-9


def test_p2_2_held_names_outside_the_new_universe_stay_subscribed(tmp_path: Path, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    held = EngineState(nav_realized=1000.0, positions={"OLD": Position("OLD", "NYSE", 1.0, 50.0, 50.0, _at(9, 0).isoformat())})
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: held)
    stream = _FakeStream()
    clock = {"t": _at(15, 59, 50)}

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))

    run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                now=lambda: clock["t"], sleep=sleep)
    assert "OLD" in stream.subscribed_history[0] and "AAA" in stream.subscribed_history[0]


def test_p2_3_a_restart_restores_the_tapes_and_never_selects_again() -> None:
    stream = _stream_with_session()
    stream.record_trade("AAA", 100.0, 1000, _at(9, 35))
    stream.record_trade("AAA", 99.0, 1000, _at(11, 0))
    engine = _engine()
    engine.state.candidates_fixed = True
    engine.state.stream_context = stream.export({"AAA"})
    saved = EngineState.from_json(json.loads(json.dumps(engine.state.to_json())))
    fresh = _stream_with_session()
    fresh.restore(saved.stream_context)
    assert fresh.view("AAA").vwap == stream.view("AAA").vwap == 99.5
    resumed = Engine(saved, DAY, [Member("AAA", "NASDAQ", 100.0, 50e6), Member("ZZZ", "NYSE", 50.0, 20e6)])
    resumed.set_candidates({"ZZZ": 40.0})  # a restart never selects again, even when the first selection was empty
    assert "ZZZ" not in resumed.candidates
    empty = Engine(EngineState(nav_realized=1.0), DAY, [Member("ZZZ", "NYSE", 50.0, 20e6)])
    empty.set_candidates({})
    assert empty.state.candidates_fixed and not empty.candidates
    empty.set_candidates({"ZZZ": 40.0})
    assert not empty.candidates


def test_p2_4_a_failure_between_the_checkpoint_and_the_screen_loses_nothing(tmp_path: Path, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1_000_000.0))
    clock = {"t": _at(9, 30, 30)}
    stream = _FakeStream()
    real_publish = engine_module.publish
    failures = {"left": 0}

    def flaky_publish(db, engine, moment):
        if engine.fills and failures["left"] > 0:
            failures["left"] -= 1
            raise RuntimeError("the screen write failed")
        return real_publish(db, engine, moment)

    monkeypatch.setattr(engine_module, "publish", flaky_publish)

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        t = clock["t"]
        price = 97.9 if t < _at(9, 40) else 98.1
        stream.views = {"AAA": _view(price, 98.0, price - 0.005, price + 0.005, t)}

    failures["left"] = 1
    with pytest.raises(RuntimeError):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                    now=lambda: clock["t"], sleep=sleep)
    clock["t"] = _at(15, 59, 55)
    run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                now=lambda: clock["t"], sleep=sleep)
    doc = database.latest_analysis_snapshot("r2d2_lab_live", DAY.isoformat())["outputs"]
    assert [t["side"] for t in doc["trades"]][:1] == ["BUY"]  # the buy the failed publish did not show is on the screen


def test_p2_6_a_long_session_publishes_beyond_the_public_route_cap() -> None:
    database = Database(Settings(database_url=""))
    engine = _engine()
    t = _at(12, 0)
    for index in range(401):
        engine.state.fills.append({"side": "BUY", "symbol": "AAA", "market": "NASDAQ", "quantity": 1.0, "price": 100.0,
                                   "executed_at": (t + timedelta(seconds=index)).isoformat(), "fees_usd": 0.01,
                                   "realized_pnl_usd": None, "realized_return_percent": None, "reason": "compra"})
    assert engine_module.publish(database, engine, t + timedelta(minutes=10))["fills"] == 401
    with pytest.raises(r2d2_lab_live.LabLiveRefused):  # the public route keeps its 400 cap
        r2d2_lab_live.validate(json.loads(json.dumps(engine.document(t + timedelta(minutes=10)))), now=t)


def test_p2_7_the_status_workflow_fails_on_access_or_mandatory_reads() -> None:
    import yaml
    root = Path(__file__).resolve().parents[3]
    workflow = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())
    run = workflow["jobs"]["status"]["steps"][1]["run"]
    assert "|| true" not in run and 'exit "$rc"' in run and "|| rc=$?" in run
    assert "--status </dev/null || exit 13" in run and "[redacted]" in run
