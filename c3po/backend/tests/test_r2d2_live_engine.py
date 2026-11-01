import json
import math
import threading
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable

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


def _permissive(database, now):
    """The Valuation's targets of a session test: every name has a target far above any ask (the filter has its own tests)."""
    return {symbol: 1e6 for symbol in ("AAA", "BBB", "CCC")}


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
    assert state.positions["S2"].armed  # ~+0.39% armed the lock
    t = _at(10, 1)
    marks = {"S2": 100.27, "S3": 100.05}  # S2 back to ~+0.26%: below its step floor (+0.35%) → lock
    fills = engine.step(t, lambda s: _view(marks[s], None, marks[s], marks[s] + 0.01, t) if s in marks else MarketView())
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: trava de lucro")]
    assert fills[0]["realized_pnl_usd"] > 0
    t = _at(15, 59, 31)
    fills = engine.step(t, lambda s: _view(100.05, None, 100.05, 100.06, t) if s == "S3" else MarketView())
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S3", "venda: positiva nos últimos 30 s")]
    assert not state.positions
    assert abs(state.nav_realized - 1_000_000 - sum(f["realized_pnl_usd"] for f in engine.fills if f["side"] == "SELL")) < 1e-6


def _held(engine: Engine, symbol: str) -> tuple[Position, Callable[[float], float]]:
    cost = 500.0 * 100.0 * (1 + FEE_SIDE)
    engine.state.positions[symbol] = Position(symbol, "NYSE", 500.0, 100.0, cost, _at(9, 35).isoformat())
    engine.members[symbol] = Member(symbol, "NYSE", 0.0, 0.0)
    return engine.state.positions[symbol], lambda net: cost * (1 + net / 100) / (500.0 * (1 - FEE_SIDE))  # the bid at a net


def _mark(engine: Engine, symbol: str, t: datetime, bid: float) -> list[dict]:
    return engine.step(t, lambda s: _view(bid, None, bid, bid + 0.01, t) if s == symbol else MarketView())


def test_the_step_lock_floor_is_the_last_step_the_peak_reached() -> None:
    """Owner 31/10: arms at +0.10%, floors +0.10, +0.20, then every 0.15 (+0.35, +0.50 ...), the floor ON the step."""
    floor = engine_module.lock_floor
    assert [round(floor(p), 10) for p in (0.10, 0.1999, 0.20, 0.3499, 0.35, 0.4999, 0.50, 0.66, 0.95)] == \
           [0.10, 0.10, 0.20, 0.20, 0.35, 0.35, 0.50, 0.65, 0.95]
    assert floor(0.20 - 1e-12) == floor(0.20) and floor(0.35 - 1e-12) == floor(0.35)  # a hair under a step still counts it
    assert engine_module.RULE["stop_percent"] == 0.20 and engine_module.RULE["lock_min_percent"] == 0.10


@pytest.mark.parametrize(("peak", "hold", "sell", "floor"), [
    (0.12, 0.11, 0.09, 0.10), (0.27, 0.21, 0.19, 0.20), (0.40, 0.36, 0.34, 0.35), (0.55, 0.51, 0.49, 0.50)])
def test_the_step_lock_sells_when_the_profit_falls_to_its_floor(peak: float, hold: float, sell: float, floor: float) -> None:
    engine = _engine()
    position, bid = _held(engine, "S2")
    assert _mark(engine, "S2", _at(10, 0), bid(peak)) == [] and position.armed
    assert abs(position.net_percent(engine.book(_at(10, 0))["positions"][0]["stop_price"]) - floor) < 1e-9  # the screen's stop
    assert _mark(engine, "S2", _at(10, 0, 1), bid(hold)) == []
    fills = _mark(engine, "S2", _at(10, 0, 2), bid(sell))
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: trava de lucro")]
    assert abs(fills[0]["realized_return_percent"] - sell) < 1e-6


def test_a_carried_position_is_armed_by_its_net_never_by_a_peak_of_the_earlier_rule() -> None:
    """Pre-review: a negative position carried from the +0.15% rule with a peak of +0.12% was never armed; under the new
    rule it must not be armed (and sold as a 'lock' at a loss) by that stored peak — only when its net reaches +0.10%."""
    engine = _engine()
    position, bid = _held(engine, "S2")
    position.peak_percent, position.armed = 0.12, False
    assert _mark(engine, "S2", _at(10, 0), bid(-0.15)) == [] and not position.armed  # held at -0.15% (the stop is -0.20%)
    assert _mark(engine, "S2", _at(10, 0, 1), bid(0.11)) == [] and position.armed  # back above +0.10%: armed, floor +0.10%
    fills = _mark(engine, "S2", _at(10, 0, 2), bid(0.09))
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: trava de lucro")]


def test_the_floor_has_no_gap_under_the_wide_band() -> None:
    floor = engine_module.lock_floor
    for peak in (0.20 - 5e-10, 0.20 - 2e-10, 0.20, 0.20 + 1e-12):
        assert round(floor(peak), 10) == 0.20
    assert round(floor(0.20 - 2e-9), 10) == 0.10


def test_the_stop_before_the_lock_arms_is_minus_two_tenths() -> None:
    """Owner 31/10: "colocando o stop loss em -0,20%" (-0.4% until then)."""
    engine = _engine()
    position, bid = _held(engine, "S2")
    assert _mark(engine, "S2", _at(10, 0), bid(0.09)) == [] and not position.armed  # positive, under +0.10%: not armed
    assert abs(position.net_percent(engine.book(_at(10, 0))["positions"][0]["stop_price"]) - -0.20) < 1e-9
    assert _mark(engine, "S2", _at(10, 0, 1), bid(-0.19)) == []
    fills = _mark(engine, "S2", _at(10, 0, 2), bid(-0.21))
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: stop")]


def test_no_buy_after_the_last_entry_and_negatives_carry() -> None:
    engine = _engine()
    t = _at(15, 59, 59)
    views = {"AAA": _view(97.0, 98.0, 96.99, 97.01, t)}
    engine.step(t, lambda s: views.get(s, MarketView()))
    views = {"AAA": _view(98.5, 98.0, 98.49, 98.51, _at(16, 0, 0))}
    assert engine.step(_at(16, 0, 0), lambda s: views.get(s, MarketView())) == []
    engine.state.positions["NEG"] = Position("NEG", "NYSE", 10.0, 100.0, 1000.05, _at(10, 0).isoformat(), last_mark=99.8)
    engine.close_session()
    assert engine.state.positions["NEG"].days_held == 1 and engine.state.last_session == DAY.isoformat()


@pytest.mark.parametrize("hour, minute, second", [(15, 30, 0), (15, 45, 0), (15, 59, 30), (15, 59, 59)])
def test_entries_run_until_the_close(hour: int, minute: int, second: int) -> None:
    """Owner 30/10/2026: "eu quero que seja até a hora da bolsa fechar!" — a cross after 15:29:59 ET buys, at any instant
    before 16:00, the T30 window included; the fill is stamped at the step's effective instant."""
    assert engine_module.LAST_ENTRY == time(15, 59, 59, 999999) < engine_module.SESSION_CLOSE
    engine = _engine()
    t = _at(hour, minute, second)
    below_at = t - timedelta(seconds=1)
    engine.step(below_at, lambda s: _view(97.9, 98.0, 97.89, 97.91, below_at) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    assert [(f["side"], f["symbol"]) for f in fills] == [("BUY", "AAA")]
    assert t <= datetime.fromisoformat(fills[0]["executed_at"]) < t + timedelta(seconds=1)


def test_the_last_entry_boundary_is_the_close_to_the_microsecond(monkeypatch) -> None:
    """Pre-review of c49b5bcb P2-5a: with the step's clock frozen, a cross at 15:59:59.999999 buys and one at 16:00 does not."""
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: 0.0)
    for at, bought in ((_at(15, 59, 59) + timedelta(microseconds=999999), True), (_at(16, 0, 0), False)):
        engine = _engine()
        below_at = at - timedelta(seconds=1)
        engine.step(below_at, lambda s: _view(97.9, 98.0, 97.89, 97.91, below_at) if s == "AAA" else MarketView())
        fills = engine.step(at, lambda s: _view(98.1, 98.0, 98.095, 98.105, at) if s == "AAA" else MarketView())
        assert bool(fills) is bought, at


def test_a_session_keeps_the_last_entry_of_the_label_it_started_under() -> None:
    """Pre-review of c49b5bcb P1: a deploy during Friday 30/10 (TIT-2S5-RT) never moves its window — no buy at 15:30:00 in
    a resumed TIT-2S5-RT session; a session started under the new label buys then."""
    universe = [Member("AAA", "NASDAQ", 100.0, 50e6)]
    for config, bought in (("TIT-2S5-RT", False), (None, True)):
        state = EngineState(nav_realized=1_000_000.0)
        if config:
            state.session, state.config = DAY.isoformat(), config  # resumed: the session's own label stays
        engine = Engine(state, DAY, universe)
        engine.set_candidates({"AAA": 98.0})
        assert engine.state.config == (config or engine_module.CONFIG)
        t = _at(15, 29, 59)
        engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
        t = _at(15, 30, 0)
        fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
        assert bool(fills) is bought, config


def test_the_rule_in_force_has_its_text_and_slots_on_the_screen() -> None:
    assert engine_module.CONFIG in r2d2_lab_live.LIVE_RULES and "close" in r2d2_lab_live.LIVE_RULES[engine_module.CONFIG]
    assert r2d2_lab_live.LIVE_SLOTS[engine_module.CONFIG] == engine_module.RULE["slots"]
    # the screen states the sizes, the stop and the lock of the rule a session ran under (owner 26/10: every field audited
    # against its source): the rule in force's own numbers, the days before 02/11 their -0.4% and 0.05 steps
    risk, hold, exits = r2d2_lab_live.LIVE_RISK[engine_module.CONFIG]
    rule = engine_module.RULE
    assert "stop −%.2f%% net" % rule["stop_percent"] in risk and "stop −%.2f%% net" % rule["stop_percent"] in hold
    assert "stop −%.2f%%" % rule["stop_percent"] in exits and "+%.2f%%" % rule["lock_min_percent"] in exits
    assert "5% of NAV at ≤ 2 bps, 4% at ≤ 3 bps, 2.5% at ≤ 5 bps" in risk
    assert [engine_module.size_weight(s) * 5 for s in (2.0, 3.0, 5.0)] == [5.0, 4.0, 2.5]  # the shares the text states
    assert "+0.10%, +0.20%, then every 0.15" in hold and rule["lock_step_percent"] == 0.10 and rule["lock_wide_step_percent"] == 0.15
    for older in ("TIT-2S5-RT", "TIT-2S5-RTC"):  # 30/10's rule
        assert "stop −0.4% net" in r2d2_lab_live.LIVE_RISK[older][0]
    assert "TIT-2S3-RT" not in r2d2_lab_live.LIVE_RISK  # 27-29/10 ran another stop and lock: the screen's own text


@pytest.mark.parametrize(("bid", "sold"), [(98.12, True), (98.095, False)])
def test_a_buy_in_the_last_30_seconds_sells_positive_or_carries_at_its_bid(bid: float, sold: bool) -> None:
    """A buy at 15:59:40 starts at its own quote's bid; a check that finds it positive in the T30 window sells it, else it
    carries to the next session at the bid it was last marked on."""
    engine = _engine()
    t = _at(15, 59, 39)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    t = _at(15, 59, 40)
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    assert [f["side"] for f in fills] == ["BUY"] and engine.state.positions["AAA"].last_mark == 98.095
    t = _at(15, 59, 50)
    fills = engine.step(t, lambda s: _view(98.1, 98.0, bid, bid + 0.01, t) if s == "AAA" else MarketView(),
                        pushed=lambda s: (bid, bid + 0.01, t) if s == "AAA" else None)
    assert [(f["side"], f["reason"].split(",")[0]) for f in fills] == ([("SELL", "venda: positiva nos últimos 30 s")] if sold else [])
    engine.close_session()
    assert ("AAA" in engine.state.positions) is not sold
    if not sold:
        assert engine.state.positions["AAA"].days_held == 1 and engine.state.positions["AAA"].last_mark == bid


def test_the_document_is_what_the_c3po_validator_accepts(monkeypatch) -> None:
    engine = _engine()
    t = _at(9, 40)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    t = _at(9, 41)
    engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    document = engine.document(t)
    validated = r2d2_lab_live.validate(json.loads(json.dumps(document)), now=t)
    assert validated["config"] == engine_module.CONFIG == "TIT-2S5-F20V" and len(validated["trades"]) == 1
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


def test_the_quote_feed_carries_only_the_held_names_and_the_trade_feed_the_universe() -> None:
    """Owner 29/10: a larger universe on the same WebSocket slots — trades for every grouped name, quotes only for the
    names given (the held ones); None keeps the old behaviour (both feeds the same names)."""
    assert engine_module.UNIVERSE_SIZE == 900
    stream = LiveEngineStream("", max_symbols=10)
    stream.set_group("r2d2-live", ["AAA", "BBB", "CCC"], priority=200)
    assert stream.feed_symbols("trade") == stream.feed_symbols("quote") == {"AAA", "BBB", "CCC"}
    version = stream._groups_version
    stream.set_quote_symbols({"BBB", "ZZZ"})  # a quote name outside the groups is never subscribed
    assert stream._groups_version == version + 1  # the feed loops resubscribe
    assert stream.feed_symbols("trade") == {"AAA", "BBB", "CCC"} and stream.feed_symbols("quote") == {"BBB"}
    stream.set_quote_symbols(set())
    assert stream.feed_symbols("quote") == set()
    stream.set_quote_symbols(None)
    assert stream.feed_symbols("quote") == {"AAA", "BBB", "CCC"}


def test_a_quote_that_left_the_feed_never_marks_a_later_position() -> None:
    """Pre-review of 568737c: a name sold (its quote unsubscribed) and re-bought within seconds must not be marked on the
    quote received before the gap; a refusal frame of the account's limit is recognised and never recorded."""
    stream = LiveEngineStream("", max_symbols=10)
    stream.start_session(DAY)
    stream.set_group("r2d2-live", ["AAA", "BBB"], priority=200)
    stream.set_quote_symbols({"AAA"})
    stream.record_quote("AAA", 98.18, 98.19, _at(10, 0, 3))
    assert stream.view("AAA").bid == 98.18
    stream.set_quote_symbols(set())  # sold: AAA leaves the quote feed and its last quote goes with it
    assert stream.view("AAA").bid is None
    stream.record_quote("AAA", 98.18, 98.19, _at(10, 0, 4))  # a late frame of the old subscription
    stream.set_quote_symbols({"AAA"})  # re-bought: entering the feed, no quote until a new one arrives
    assert stream.view("AAA").bid is None
    assert engine_module.refusal_code('{"status_code":422,"message":"Symbols limit reached"}') == 422
    assert engine_module.refusal_code(b'{"status_code":200,"message":"Authorized"}') is None
    assert engine_module.refusal_code('{"s":"AAA","p":98.0,"v":1,"t":1}') is None


class _QuoteFakeStream(_FakeStream):
    def __init__(self):
        super().__init__()
        self.quote_history: list[set[str] | None] = []

    def set_quote_symbols(self, symbols):
        self.quote_history.append(None if symbols is None else set(symbols))

    def start_session(self, day):
        self.opening = {"AAA": 98.0, "BBB": 50.5}  # AAA opens -2% (a candidate), BBB +1% (not one)


def test_the_session_narrows_the_trades_to_the_candidates_and_the_quotes_follow_the_held_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "load_targets", _permissive)
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe",
                        lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6), Member("BBB", "NYSE", 50.0, 20e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6))
    clock = {"t": _at(9, 30, 30)}
    stream = _QuoteFakeStream()

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        t = clock["t"]
        stream.views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t) if t < _at(9, 40) else _view(98.1, 98.0, 98.095, 98.105, t)}
        if t >= _at(9, 45):
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                    now=lambda: clock["t"], sleep=sleep)
    assert stream.subscribed_history[0] == ["AAA", "BBB"]  # the universe until the candidates are fixed
    assert stream.subscribed_history[-1] == ["AAA"]  # then the candidates and the held names only
    assert stream.quote_history[0] == set() and stream.quote_history[-1] == {"AAA"}  # quotes: none held, then the buy


def test_the_stream_evidence_counts_only_a_fresh_stream_quote_wider_than_the_limit() -> None:
    t = _at(9, 41)
    nbbo = lambda s, now: (98.095, 98.105, now)  # noqa: E731 — Massive: 1 bp
    engine = _crossing_engine()  # no stream quote for AAA (the quote feed carries only the held names)
    fills = engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(), nbbo=nbbo)
    assert [f["symbol"] for f in fills] == ["AAA"] and engine.sources["stream_would_refuse"] == 0
    engine = _crossing_engine()  # a fresh stream quote of 10 bps that alone would have refused the buy
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.05, 98.15, t) if s == "AAA" else MarketView(), nbbo=nbbo)
    assert [f["symbol"] for f in fills] == ["AAA"] and engine.sources["stream_would_refuse"] == 1


def test_a_spread_refusal_is_counted_in_its_band_and_followed_as_a_shadow_trade() -> None:
    """Owner 29/10: the refused signals per spread band and what each band would have made, with the same exits."""
    assert [engine_module.shadow_band(b) for b in (5.5, 8.0, 8.1, 10.0, 10.5)] == ["5_8", "5_8", "8_10", "8_10", "gt10"]
    engine = _crossing_engine()
    t = _at(9, 41)
    wide = lambda s, now: (97.97, 98.03, now)  # noqa: E731 — Massive: ~6.1 bps, refused by the 5 bps limit
    assert engine.step(t, lambda s: _view(98.1, 98.0, 97.97, 98.03, t) if s == "AAA" else MarketView(), nbbo=wide) == []
    assert engine.skips["spread"] == 1 and engine.state.bands["5_8"]["vetoed"] == 1
    row = engine.state.shadow["AAA"]
    # the widest of the owner's tiers (2.5% of NAV): a shadow is wider than the 5 bps limit by definition
    assert row["band"] == "5_8" and row["ask"] == 98.03 and abs(row["size_usd"] - 1_000_000.0 / 20 * 0.5) < 1e-6
    # its exits: the last trade less half the refused spread is the estimated bid; up ~+0.12% → armed, floor +0.10%
    half = row["spread_bps"] / 2 / 1e4
    price_at = lambda net: row["ask"] * (1 + FEE_SIDE) * (1 + net / 100) / ((1 - FEE_SIDE) * (1 - half))  # noqa: E731
    up, down = _at(9, 42), _at(9, 42, 1)
    engine.step(up, lambda s: MarketView(price=price_at(0.12), trade_at=up, vwap=98.0) if s == "AAA" else MarketView())
    assert engine.state.shadow["AAA"]["armed"]
    engine.step(down, lambda s: MarketView(price=price_at(0.09), trade_at=down, vwap=98.0) if s == "AAA" else MarketView())
    stats = engine.state.bands["5_8"]
    assert "AAA" not in engine.state.shadow and stats["closed"] == 1 and stats["wins"] == 1
    assert abs(stats["net_usd"] - 50_000.0 * 0.5 * 0.09 / 100) < 1e-6 and not engine.state.positions and not engine.fills  # no money


def test_the_shadows_close_with_the_session_and_the_line_and_status_carry_numbers_only() -> None:
    engine = _crossing_engine()
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.0, 98.12, t), "CCC": _view(29.1, 29.0, 29.0, 29.05, t)}  # ~12 bps and ~17 bps
    engine.step(t, lambda s: views.get(s, MarketView()), nbbo=lambda s, now: None)
    assert set(engine.state.shadow) == {"AAA", "CCC"} and engine.state.bands["gt10"]["vetoed"] == 2
    later = _at(10, 0)
    engine.step(later, lambda s: MarketView(price=98.0, trade_at=later, vwap=98.0) if s == "AAA" else MarketView())  # marked
    line = engine_module.shadow_line(engine)
    assert line == ("R2D2 live shadow: limit_bps=5.0 5_8 vetoed=0 closed=0 open=0 wins=0 net_usd=0.00 8_10 vetoed=0 closed=0 "
                    "open=0 wins=0 net_usd=0.00 gt10 vetoed=2 closed=0 open=2 wins=0 net_usd=0.00")
    import re
    import yaml

    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    pattern = run.split('grep -oE "', 1)[1].split('" | tail', 1)[0]
    assert re.search(pattern, "r2d2-live-1  | 2026-10-30 10:00:00 INFO app.r2d2_live_engine " + line)
    engine.close_session()  # AAA closes at its last mark; CCC was never marked: dropped, not counted
    stats = engine.state.bands["gt10"]
    assert not engine.state.shadow and stats["closed"] == 1 and stats["net_usd"] < 0
    assert engine.state.bands_closed == {"session": DAY.isoformat(), "bands": engine.state.bands}  # kept past the next reset
    restored = EngineState.from_json(json.loads(json.dumps(engine.state.to_json())))
    assert restored.bands == engine.state.bands and restored.shadow == {}
    database = Database(Settings(database_url=""))
    engine_module.save_state(database, engine.state, later)
    summary = engine_module.status(database, later)
    assert set(summary["spread_bands"]) == {"gt10"} and summary["spread_bands"]["gt10"]["closed"] == 1
    assert summary["spread_bands_last_session"]["session"] == DAY.isoformat()
    assert summary["spread_bands_last_session"]["bands"]["gt10"]["closed"] == 1
    assert "AAA" not in json.dumps(summary) and "CCC" not in json.dumps(summary)  # numbers only


def test_a_session_runs_publishes_and_resumes_after_a_restart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "load_targets", _permissive)
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
    assert stored is not None and stored[1] == engine_module.CONFIG and len(stored[2]["positions"]) == 1
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


def test_buys_and_exits_are_checked_every_second() -> None:
    """Owner 29/10/2026: "esse cheque tem que ser por segundo e não por minuto" — a cross back above the VWAP buys at the
    second it is seen (until 29/10 it waited for the minute's close); an exit is checked at any second, as before."""
    engine = _engine()
    below = lambda t: {"AAA": _view(97.9, 98.0, 97.89, 97.91, t)}  # noqa: E731
    above = lambda t: {"AAA": _view(98.1, 98.0, 98.095, 98.105, t)}  # noqa: E731
    t = _at(9, 40, 0)
    engine.step(t, lambda s: below(t).get(s, MarketView()))
    t = _at(9, 40, 30)  # the same minute: bought at once
    fills = engine.step(t, lambda s: above(t).get(s, MarketView()))
    assert [f["symbol"] for f in fills] == ["AAA"] and 0 <= (datetime.fromisoformat(fills[0]["executed_at"]) - t).total_seconds() < 1
    t = _at(9, 40, 35)
    fills = engine.step(t, lambda s: _view(97.5, 98.0, 97.5, 97.51, t) if s == "AAA" else MarketView())
    assert [(f["side"], f["reason"].split(",")[0]) for f in fills] == [("SELL", "venda: stop")]
    t = _at(9, 40, 36)  # the stop's second was below the VWAP: back above, it is a new cross
    assert [f["symbol"] for f in engine.step(t, lambda s: above(t).get(s, MarketView()))] == ["AAA"]
    t = _at(9, 40, 37)  # still above, held: no new signal without a new dip
    assert engine.step(t, lambda s: above(t).get(s, MarketView())) == [] and engine.signals == 2


def test_a_sale_never_buys_back_in_the_same_step() -> None:
    """Pre-review of 81cf1ae P2-B: the bid stops the position while the last trade is still above the VWAP; the same
    step must not buy it back at Massive's ask. A new dip below the VWAP, then back above, is a new entry. Since 30/10 the
    stop's bid is Massive's NBBO (the exits mark on it)."""
    engine = _engine()
    engine.step(_at(10, 0), lambda s: _view(97.9, 98.0, 97.89, 97.91, _at(10, 0)) if s == "AAA" else MarketView())
    t = _at(10, 0, 1)
    assert [f["symbol"] for f in engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())] == ["AAA"]
    t = _at(10, 0, 2)  # held, one print below the VWAP (no stop): armed for a cross
    assert engine.step(t, lambda s: _view(97.95, 98.0, 97.94, 97.96, t) if s == "AAA" else MarketView()) == []
    assert engine.below["AAA"] is True
    t = _at(10, 0, 3)  # Massive's bid stops it while the last trade is back above the VWAP
    stop = lambda s, now: (97.50, 97.51, now)  # noqa: E731
    fills = engine.step(t, lambda s: _view(98.05, 98.0, 97.50, 97.51, t) if s == "AAA" else MarketView(), nbbo=stop)
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("SELL", "AAA", 97.50)] and not engine.state.positions
    nbbo = lambda s, now: (98.04, 98.06, now)  # noqa: E731
    t = _at(10, 0, 4)
    assert engine.step(t, lambda s: _view(98.05, 98.0, 98.04, 98.06, t) if s == "AAA" else MarketView(), nbbo=nbbo) == []
    t = _at(10, 0, 5)
    engine.step(t, lambda s: _view(97.95, 98.0, 97.94, 97.96, t) if s == "AAA" else MarketView(), nbbo=nbbo)
    t = _at(10, 0, 6)
    assert [f["side"] for f in engine.step(t, lambda s: _view(98.05, 98.0, 98.04, 98.06, t) if s == "AAA" else MarketView(), nbbo=nbbo)] == ["BUY"]


def _bought_aaa(engine: Engine, t: datetime) -> Position:
    """AAA bought at Massive's 98.105 ask at ``t`` (one dip, one cross)."""
    engine.step(t - timedelta(seconds=1), lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (98.095, 98.105, now))
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("BUY", "AAA", 98.105)]
    return engine.state.positions["AAA"]


def _bid_at(position: Position, net: float) -> float:
    return position.cost_usd * (1 + net / 100) / (position.shares * (1 - engine_module.FEE_SIDE))


def test_exits_mark_on_massive_and_a_feed_bid_off_the_market_never_stops() -> None:
    """30/10 10:36 BRT: the quote feed's bid sold ASX at -0.751% while the NBBO bid was ~0.5% higher (the minute's low
    was above it). The NBBO prevailing at the instant decides; the feed's bid is never the price."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    t = _at(10, 0, 2)
    feed, real = _bid_at(position, -0.75), _bid_at(position, -0.15)  # the NBBO above the -0.20% stop
    fills = engine.step(t, lambda s: _view(98.0, 98.0, feed, feed + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (real, real + 0.01, now))
    assert fills == [] and position.last_mark == real and engine.exit_sources == {"massive": 1, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 0, "fast": 0}
    t = _at(10, 0, 3)  # the NBBO crosses the stop: sold at ITS bid
    stop = _bid_at(position, -0.42)
    fills = engine.step(t, lambda s: _view(98.0, 98.0, feed, feed + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (stop, stop + 0.01, now))
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", stop)] and "stop" in fills[0]["reason"]
    assert fills[0]["realized_return_percent"] == pytest.approx(-0.42)


def test_exits_a_held_name_without_a_feed_quote_is_marked_armed_and_locked_on_massive() -> None:
    """30/10 10:43 BRT: AMD at +0.175% net on the screen, the engine's stop still at its level (no fresh feed quote,
    never armed). Massive marks it every second: the lock arms at +0.10% and sells at the step's floor."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    no_quote = MarketView(price=98.2, trade_at=t, vwap=98.0)  # trades only: the quote feed has not delivered it
    for second, net in ((2, 0.12), (3, 0.27)):
        t = _at(10, 0, second)
        bid = _bid_at(position, net)
        assert engine.step(t, lambda s: no_quote if s == "AAA" else MarketView(), nbbo=lambda s, now: (bid, bid + 0.01, now)) == []
    assert position.armed and position.peak_percent == pytest.approx(0.27) and position.exit_price() == pytest.approx(_bid_at(position, 0.20))
    t = _at(10, 0, 4)
    bid = _bid_at(position, 0.19)
    fills = engine.step(t, lambda s: no_quote if s == "AAA" else MarketView(), nbbo=lambda s, now: (bid, bid + 0.01, now))
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", bid)] and "trava" in fills[0]["reason"]
    assert engine.exit_sources == {"massive": 3, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 0, "fast": 0}


def test_exits_without_massive_the_feeds_fresh_quote_stands_in_and_nothing_is_never_a_mark(monkeypatch) -> None:
    import time as wall

    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    t = _at(10, 0, 2)
    stop = _bid_at(position, -0.45)
    # Massive silent: the feed's fresh quote stands in, but its bid alone never sells — ASX 10:36: the last trade was
    # above the stop level (the minute's low over the NBBO bid), so no sale
    fills = engine.step(t, lambda s: _view(98.0, 98.0, stop, stop + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: None)
    assert fills == [] and engine.exit_sources == {"massive": 0, "stream": 1, "none": 0, "unconfirmed": 1, "pushed": 0, "fast": 0}
    t = _at(10, 0, 3)  # the fresh last trade at the stop level confirms it: sold at the feed's quoted bid
    fills = engine.step(t, lambda s: _view(stop, 98.0, stop, stop + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: None)
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", stop)] and engine.exit_sources["stream"] == 2
    # Codex 6525240030 P2-1: a confirmed feed sale is booked at the feed's QUOTED bid, never at an estimate
    engine = _engine()
    position = _bought_aaa(engine, _at(10, 0, 1))
    t = _at(10, 0, 2)
    trade, feed = _bid_at(position, -0.45), _bid_at(position, -0.75)
    fills = engine.step(t, lambda s: _view(trade, 98.0, feed, feed + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: None)
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", feed)]
    # Codex 6525240030 P2-2: Massive's NBBO of the name is the market, whatever its distance to an earlier price: a real
    # -6% move with a 20 s old last print and a stale mark sells at its bid (a percentage filter kept the stop off)
    engine = _engine()
    position = _bought_aaa(engine, _at(10, 0, 1))
    t = _at(10, 0, 2)
    far = _bid_at(position, -6.0)
    fills = engine.step(t, lambda s: MarketView(price=98.1, trade_at=t - timedelta(seconds=20), vwap=98.0) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (far, far + 0.01, now))
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", far)] and engine.exit_sources["massive"] == 1
    engine = _engine()
    position = _bought_aaa(engine, _at(10, 0, 1))
    old = t - timedelta(seconds=engine_module.NBBO_EXIT_MAX_AGE_SECONDS + 1)  # a lagging Massive never hides a stop
    assert engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(),
                       nbbo=lambda s, now: (98.0, 98.01, old)) == []
    assert engine.exit_sources == {"massive": 0, "stream": 0, "none": 1, "unconfirmed": 0, "pushed": 0, "fast": 0}
    assert engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(),
                       nbbo=lambda s, now: (98.2, 98.1, now)) == []  # crossed: no NBBO
    assert engine.exit_sources["none"] == 2 and position.last_mark == 98.095  # never marked: still its own quote's bid
    monkeypatch.setattr(engine_module, "NBBO_EXIT_BUDGET_SECONDS", 0.3)

    def slow(symbol, now):
        wall.sleep(2.0)
        return (98.0, 98.01, now)
    began = wall.monotonic()
    engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(), nbbo=slow)
    assert wall.monotonic() - began < 0.3 + 0.5  # the exits never wait past their budget
    assert engine.exit_sources["none"] == 3 and "AAA" in engine.state.positions


def test_massive_stream_keeps_the_held_names_nbbo_in_their_own_spelling_and_drops_it_on_a_change() -> None:
    from app.r2d2_live_engine import MassiveQuoteStream

    stream = MassiveQuoteStream("key-secret")
    stream.set_symbols({"AAA", "BRK-B"})
    stream.status = "connected"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stream._record(json.dumps([
        {"ev": "Q", "sym": "AAA", "bp": 98.0, "ap": 98.02, "t": now_ms - 100},
        {"ev": "Q", "sym": "BRK.B", "bp": 500.0, "ap": 500.1, "t": now_ms - 80},  # Massive's spelling of EODHD's BRK-B
        {"ev": "Q", "sym": "ZZZ", "bp": 1.0, "ap": 1.01, "t": now_ms},  # not followed
        {"ev": "Q", "sym": "AAA", "bp": 97.0, "ap": 97.1, "t": now_ms + 60_000},  # a minute in the future: refused
        {"ev": "status", "status": "success", "message": "subscribed to: Q.AAA"},
    ]))
    stream._record("not json")
    assert stream.quote("AAA")[:2] == (98.0, 98.02) and stream.quote("BRK-B")[:2] == (500.0, 500.1)
    assert stream.quote("ZZZ") is None
    quotes, lag, worst, names = stream.take_gauges()
    assert quotes == 2 and 0 <= worst < 5_000 and names == 2 and stream.take_gauges()[0] == 0
    # pre-review of 20002f04 P2-3: an update older than the held one never replaces it; a crossed one is kept as received
    # (the last good quote never outlives the market that replaced it) and exit_bid refuses it, so Massive is asked
    stream._record(json.dumps([{"ev": "Q", "sym": "AAA", "bp": 49.0, "ap": 49.1, "t": now_ms - 5_000}]))
    assert stream.quote("AAA")[:2] == (98.0, 98.02)
    stream._record(json.dumps([{"ev": "Q", "sym": "AAA", "bp": 99.0, "ap": 98.0, "t": now_ms}]))
    crossed = stream.quote("AAA")
    assert crossed is not None and crossed[:2] == (99.0, 98.0)
    position = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, "", last_mark=98.0)
    assert engine_module.exit_bid(crossed, MarketView(), position, datetime.now(timezone.utc)) is None
    stream.set_symbols({"AAA"})  # BRK-B sold: its NBBO is dropped; a re-buy waits for a new one
    stream.set_symbols({"AAA", "BRK-B"})
    assert stream.quote("BRK-B") is None and stream.quote("AAA") is not None
    stream._last_message -= engine_module.MASSIVE_STREAM_ALIVE_SECONDS + 1  # a silent socket is never read
    assert stream.quote("AAA") is None
    stream._last_message += engine_module.MASSIVE_STREAM_ALIVE_SECONDS + 1
    stream.status = "error"
    assert stream.quote("AAA") is None


def test_massive_stream_authenticates_in_the_frame_subscribes_quotes_and_never_logs_the_key(monkeypatch, caplog) -> None:
    import asyncio

    from app.r2d2_live_engine import MassiveQuoteStream

    stream = MassiveQuoteStream("key-secret")
    stream.set_symbols({"AAA", "BRK-B"})
    sent: list[dict] = []
    urls: list[str] = []
    connections = {"n": 0}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    class Socket:
        def __init__(self) -> None:
            connections["n"] += 1
            self.first = connections["n"] == 1
            self.messages = [json.dumps([{"ev": "status", "status": "connected"}]),
                             json.dumps([{"ev": "status", "status": "auth_success"}])]
            if self.first:
                self.messages += [json.dumps([{"ev": "Q", "sym": "AAA", "bp": 98.0, "ap": 98.02, "t": now_ms}])] * 3

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, text: str) -> None:
            sent.append(json.loads(text))

        async def recv(self) -> str:
            if self.first and len(self.messages) == 2 and sent[-1]["action"] == "subscribe" and connections["n"] == 1:
                stream.set_symbols({"AAA", "CCC"})  # mid-stream, a sale and a buy
            if self.messages:
                return self.messages.pop(0)
            if self.first:
                raise ConnectionError("dropped key-secret")
            stream._stop.set()
            raise TimeoutError

    async def no_sleep(seconds: float) -> None:
        return None

    def connect(url, **kwargs):
        urls.append(url)
        return Socket()

    monkeypatch.setattr(engine_module.websockets, "connect", connect)
    monkeypatch.setattr(engine_module.asyncio, "sleep", no_sleep)
    asyncio.run(stream._run())
    assert urls == [engine_module.MASSIVE_STREAM_URL] * 2 and all("key" not in url for url in urls)  # never in the URL
    assert sent[0] == {"action": "auth", "params": "key-secret"}
    assert sent[1] == {"action": "subscribe", "params": "Q.AAA,Q.BRK.B"}
    assert {"action": "unsubscribe", "params": "Q.BRK.B"} in sent and {"action": "subscribe", "params": "Q.CCC"} in sent
    assert sent[-2:] == [{"action": "auth", "params": "key-secret"}, {"action": "subscribe", "params": "Q.AAA,Q.CCC"}]  # from scratch
    assert stream.status == "stopped" and stream.reconnects == 1
    assert stream._quotes == {} and stream.quote("AAA") is None  # pre-review of 20002f04 P1-2: no pre-drop quote survives
    assert "key-secret" not in caplog.text and "Massive stream reconnect: ConnectionError" in caplog.text

    refused = MassiveQuoteStream("key-secret")

    class Unauthorized(Socket):
        def __init__(self) -> None:
            self.first = False
            self.messages = [json.dumps([{"ev": "status", "status": "connected"}]),
                             json.dumps([{"ev": "status", "status": "auth_failed", "message": "bad key-secret"}])]

        async def recv(self) -> str:
            if not self.messages:
                refused._stop.set()
                raise TimeoutError
            return self.messages.pop(0)

    monkeypatch.setattr(engine_module.websockets, "connect", lambda url, **kwargs: Unauthorized())
    caplog.clear()
    refused._stop.clear()

    async def stop_after_one(seconds: float) -> None:
        refused._stop.set()

    monkeypatch.setattr(engine_module.asyncio, "sleep", stop_after_one)
    asyncio.run(refused._run())
    assert refused.status == "stopped" and "PermissionError" in caplog.text and "key-secret" not in caplog.text


def test_exits_read_the_pushed_nbbo_first_and_ask_massive_only_for_the_rest() -> None:
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    engine.state.positions["CCC"] = Position("CCC", "NYSE", 1000.0, 29.0, 29_001.45, t.isoformat(), last_mark=29.0)
    asked: list[str] = []
    t = _at(10, 0, 2)
    stop = _bid_at(position, -0.42)

    def nbbo(symbol, now):
        asked.append(symbol)
        return (29.01, 29.02, now)
    fills = engine.step(t, lambda s: MarketView(price=98.0, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(price=29.0, trade_at=t),
                        nbbo=nbbo, pushed=lambda s: (stop, stop + 0.01, t) if s == "AAA" else None)
    assert asked == ["CCC"]  # AAA's pushed NBBO stood; only CCC was asked
    assert [(f["symbol"], f["price"]) for f in fills] == [("AAA", stop)]
    assert engine.exit_sources == {"massive": 2, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 1, "fast": 0}
    t = _at(10, 0, 3)  # a pushed quote that is no usable mark (older than the exits' 10 s) is asked again, never used
    asked.clear()
    stale = t - timedelta(seconds=engine_module.NBBO_EXIT_MAX_AGE_SECONDS + 1)
    engine.step(t, lambda s: MarketView(price=29.0, trade_at=t), nbbo=nbbo, pushed=lambda s: (29.0, 29.01, stale))
    assert asked == ["CCC"] and engine.exit_sources["pushed"] == 1


def test_exits_a_pushed_quote_is_read_and_used_at_one_instant_and_one_that_aged_meanwhile_goes_to_massive(monkeypatch) -> None:
    """Codex 6526033042: a pushed quote accepted early aged past 10 s while a read blocked (3 s), was refused at its use,
    and Massive was never asked — no sale that second. Read and used at one instant, it goes down the chain instead."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    t = _at(10, 0, 2)
    wall = {"t": 1000.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def slow_view(symbol):  # the view's lock held 3 s, once
        if symbol == "AAA" and not slow_view.done:
            slow_view.done = True
            wall["t"] += 3.0
        return MarketView(price=98.0, trade_at=t, vwap=98.0)
    slow_view.done = False
    stop = _bid_at(position, -0.42)
    pushed_quote = (98.05, 98.06, t - timedelta(seconds=8))  # 8 s old when read, 11 s at its use
    asked = []

    def nbbo(symbol, now):
        asked.append(symbol)
        return (stop, stop + 0.01, now)
    fills = engine.step(t, slow_view, nbbo=nbbo, pushed=lambda s: pushed_quote)
    assert asked == ["AAA"] and [(f["side"], f["price"]) for f in fills] == [("SELL", stop)]
    assert engine.exit_sources == {"massive": 1, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 0, "fast": 0}


def test_exits_a_pushed_decision_is_taken_before_any_other_name_waits_on_massive() -> None:
    """Codex 6526033042: A's pushed quote was copied, B's request to Massive made the stream forget it, and A was still
    sold on the copy. Now A is judged at the instant its quote is read, before B's request: a stream that drops during B's
    wait changes nothing already decided, and the next second reads the stream (or asks Massive) afresh."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    engine.state.positions["CCC"] = Position("CCC", "NYSE", 1000.0, 29.0, 29_001.45, t.isoformat(), last_mark=29.0)
    t = _at(10, 0, 2)
    mark = _bid_at(position, 0.05)
    live = {"on": True}
    order = []

    def pushed(symbol):
        order.append(("pushed", symbol))
        return (mark, mark + 0.01, t) if symbol == "AAA" and live["on"] else None

    def nbbo(symbol, now):  # runs in Massive's worker thread: what it sees is recorded, asserted below
        order.append(("asked", symbol, position.last_mark == mark))  # AAA already marked on its pushed quote?
        live["on"] = False  # the stream forgets during CCC's request
        return (29.0, 29.01, now)
    engine.step(t, lambda s: MarketView(price=98.0 if s == "AAA" else 29.0, trade_at=t, vwap=98.0), nbbo=nbbo, pushed=pushed)
    assert order == [("pushed", "AAA"), ("pushed", "CCC"), ("asked", "CCC", True)]
    assert engine.exit_sources == {"massive": 2, "stream": 0, "none": 0, "unconfirmed": 0, "pushed": 1, "fast": 0}
    order.clear()
    t = _at(10, 0, 3)  # the next second: the stream is silent, so AAA is asked of Massive too
    engine.step(t, lambda s: MarketView(price=98.0 if s == "AAA" else 29.0, trade_at=t, vwap=98.0), nbbo=nbbo, pushed=pushed)
    assert {entry[:2] for entry in order if entry[0] == "asked"} == {("asked", "AAA"), ("asked", "CCC")}


def test_ask_nbbo_calls_between_while_an_answer_is_due_within_the_budget() -> None:
    """Load test of 31/10: while a step waited on Massive's REST, the session's passes on the pushed NBBO stood still.
    ``between`` runs during the wait, the answers are still collected, and the budget still ends the wait."""
    t = _at(10, 0, 2)
    release, calls = threading.Event(), []

    def nbbo(symbol, now):  # answers once the wait has called ``between`` three times
        assert release.wait(2.0)
        return (29.01, 29.02, now)

    def between():
        calls.append(1)
        if len(calls) == 3:
            release.set()
    answers = engine_module.ask_nbbo(nbbo, ["AAA", "CCC"], t, budget=2.0, between=between)
    assert set(answers) == {"AAA", "CCC"} and len(calls) >= 3
    late, started = threading.Event(), engine_module.clock_time.monotonic()
    calls.clear()
    try:  # a request that never answers: the budget ends the wait, ``between`` ran meanwhile, no answer
        assert engine_module.ask_nbbo(lambda s, now: (late.wait(2.0), None)[1], ["AAA"], t, budget=0.2,
                                      between=lambda: calls.append(1)) == {}
        assert engine_module.clock_time.monotonic() - started < 1.0 and len(calls) >= 3
    finally:
        late.set()


def test_exits_a_stop_pushed_while_the_step_waits_on_massive_is_sold_in_the_wait() -> None:
    """Load test of 31/10: CCC is quiet (no pushed quote), so the step asks Massive's REST for it; AAA's stop reaches the
    stream meanwhile. The session's pass (``between``) sells AAA during the wait; CCC is still marked on its answer."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    engine.state.positions["CCC"] = Position("CCC", "NYSE", 1000.0, 29.0, 29_001.45, t.isoformat(), last_mark=29.0)
    t = _at(10, 0, 2)
    mark, stop = _bid_at(position, 0.05), _bid_at(position, -0.42)
    quotes = {"AAA": (mark, mark + 0.01, t)}
    answered, sold = threading.Event(), []

    def view(symbol):
        return MarketView(price=98.0 if symbol == "AAA" else 29.0, trade_at=t, vwap=98.0)

    def nbbo(symbol, now):  # CCC's answer comes only after the pass in the wait
        assert answered.wait(2.0)
        return (29.01, 29.02, now)

    def between():
        if not answered.is_set():
            quotes["AAA"] = (stop, stop + 0.01, t + timedelta(milliseconds=50))
            sold.extend(engine.fast_exits(t + timedelta(milliseconds=60), view, quotes.get))
            answered.set()
    fills = engine.step(t, view, nbbo=nbbo, pushed=quotes.get, between=between)
    assert [(f["side"], f["symbol"], f["price"]) for f in sold] == [("SELL", "AAA", stop)] and fills == []
    assert "AAA" not in engine.state.positions and engine.state.positions["CCC"].last_mark == 29.01
    assert sum(1 for f in engine.fills if f["side"] == "SELL") == 1


def test_entries_a_stop_pushed_while_the_crosses_wait_on_massive_is_sold_in_the_wait() -> None:
    """The crosses' wait on Massive (up to NBBO_STEP_BUDGET_SECONDS) runs the session's passes too: AAA's stop pushed
    meanwhile is sold in the wait, and CCC's cross is then bought at the NAV that sale left (pre-review of c0b7c4a4)."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    mark, stop = _bid_at(position, 0.05), _bid_at(position, -0.42)

    def view_at(moment, ccc):
        def view(symbol):
            if symbol == "AAA":
                return MarketView(price=98.0, trade_at=moment, vwap=98.0)
            return MarketView(price=ccc, trade_at=moment, vwap=29.0) if symbol == "CCC" else MarketView()
        return view
    t = _at(10, 0, 2)
    quotes = {"AAA": (mark, mark + 0.01, t)}
    assert engine.step(t, view_at(t, 28.9), pushed=quotes.get) == []  # CCC under its VWAP: armed for a cross
    t = _at(10, 0, 3)
    quotes["AAA"] = (mark, mark + 0.01, t)
    view, answered, sold = view_at(t, 29.1), threading.Event(), []

    def nbbo(symbol, now):  # CCC's NBBO answers only after the pass in the wait
        assert answered.wait(2.0)
        return (29.095, 29.105, now)

    def between():
        if not answered.is_set():
            quotes["AAA"] = (stop, stop + 0.01, t + timedelta(milliseconds=50))
            sold.extend(engine.fast_exits(t + timedelta(milliseconds=60), view, quotes.get))
            answered.set()
    nav = engine.state.nav_realized
    fills = engine.step(t, view, nbbo=nbbo, pushed=quotes.get, between=between)
    assert [(f["side"], f["symbol"], f["price"]) for f in sold] == [("SELL", "AAA", stop)]
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("BUY", "CCC", 29.105)]
    assert engine.state.nav_realized < nav and set(engine.state.positions) == {"CCC"}
    spread = (29.105 - 29.095) / ((29.105 + 29.095) / 2) * 1e4  # 3.4 bps: the owner's 2.5% tier
    assert engine.state.positions["CCC"].cost_usd == pytest.approx(engine.state.nav_realized / 20 * engine_module.size_weight(spread))


def test_exits_a_quiet_name_judged_in_the_wait_is_never_marked_again_on_the_older_answer() -> None:
    """AAA is quiet at the step's start, so Massive's REST is asked for it; its quote reaches the stream during the wait
    and the pass arms the lock at +0.12%. The answer, asked before that quote, would mark -0.20% under the lock's floor
    and sell on a price older than the one already judged: it never marks AAA. A name the pass sold is skipped too."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    t = _at(10, 0, 2)
    quotes: dict = {}
    fresh, old = _bid_at(position, 0.12), _bid_at(position, -0.20)
    answered = threading.Event()

    def view(symbol):
        return MarketView(price=98.0, trade_at=t, vwap=98.0) if symbol == "AAA" else MarketView()

    def nbbo(symbol, now):
        assert answered.wait(2.0)
        return (old, old + 0.01, now)

    def between():
        if not answered.is_set():
            quotes["AAA"] = (fresh, fresh + 0.01, t + timedelta(milliseconds=40))
            engine.fast_exits(t + timedelta(milliseconds=50), view, quotes.get)
            answered.set()
    assert engine.step(t, view, nbbo=nbbo, pushed=quotes.get, between=between) == []
    assert position.last_mark == fresh and position.armed and "AAA" in engine.state.positions
    t = _at(10, 0, 3)  # quiet again; this time the pass in the wait sells it: the answer after it changes nothing
    stop = _bid_at(position, -0.45)
    quotes.clear()
    answered.clear()

    def selling():
        if not answered.is_set():
            quotes["AAA"] = (stop, stop + 0.01, t + timedelta(milliseconds=40))
            engine.fast_exits(t + timedelta(milliseconds=50), view, quotes.get)
            answered.set()
    assert engine.step(t, view, nbbo=nbbo, pushed=quotes.get, between=selling) == []
    assert "AAA" not in engine.state.positions
    assert [(f["side"], f["price"]) for f in engine.fills if f["symbol"] == "AAA"][-1] == ("SELL", stop)


def test_fast_exits_judge_the_held_names_on_the_pushed_nbbo_between_the_full_checks() -> None:
    """Owner 30/10/2026: "com o papel na carteira acompanhar em 0,1 s". Only the pushed NBBO, read and used at one
    instant; a name without a usable one waits for the full check; never an entry."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    engine.state.positions["CCC"] = Position("CCC", "NYSE", 1000.0, 29.0, 29_001.45, t.isoformat(), last_mark=29.0)
    t = _at(10, 0, 1, ) + timedelta(milliseconds=300)
    stop = _bid_at(position, -0.41)
    fills = engine.fast_exits(t, lambda s: MarketView(price=98.0, trade_at=t, vwap=98.0),
                              lambda s: (stop, stop + 0.01, t) if s == "AAA" else None)
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("SELL", "AAA", stop)] and "stop" in fills[0]["reason"]
    assert "CCC" in engine.state.positions and engine.state.positions["CCC"].last_mark == 29.0  # no pushed quote: untouched
    assert engine.exit_sources["fast"] == 1 and engine.exit_sources["massive"] == 0 and engine.signals == 1  # no entry
    stale = t - timedelta(seconds=engine_module.NBBO_EXIT_MAX_AGE_SECONDS + 1)
    assert engine.fast_exits(t, lambda s: MarketView(price=29.0, trade_at=t), lambda s: (27.0, 27.01, stale)) == []


def test_the_session_checks_the_held_names_every_tenth_of_a_second_between_the_full_checks(tmp_path: Path, monkeypatch) -> None:
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    carried = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, _at(9, 31).isoformat(), last_mark=98.0)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6, positions={"AAA": carried}))
    wall, clock, steps, fast = {"t": 0.0}, {"t": _at(9, 30, 59)}, [], []
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):  # a full check takes 0.05 s
        steps.append(now)
        wall["t"] += 0.05
        clock["t"] += timedelta(seconds=0.05)
        return []

    def fast_exits(self, now, view, pushed):
        fast.append(now)
        if len(fast) == 20:  # the 20th tenth-of-a-second check stops AAA
            self.state.positions.pop("AAA")
            return [{"side": "SELL", "symbol": "AAA"}]
        return []
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "fast_exits", fast_exits)

    def sleep(seconds):
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)
        if len(steps) >= 5:
            raise KeyboardInterrupt

    class Massive:
        status, reconnects = "connected", 0

        def __init__(self) -> None:
            self.calls: list[set[str]] = []

        def set_symbols(self, symbols) -> None:
            self.calls.append(set(symbols))

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, 0)
    massive = Massive()
    commits, written, stopped = [], [], []
    monkeypatch.setattr(engine_module, "save_state", lambda db, state, moment: commits.append(moment))

    class Writer:  # the marks writer's hand-overs, synchronously
        def __init__(self, write) -> None:
            pass

        def submit(self, session, as_of, marks) -> None:
            written.append(as_of)

        def stop(self) -> None:
            stopped.append(True)
    monkeypatch.setattr(engine_module, "MarksWriter", Writer)
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=_FakeStream(), database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None, massive=massive)  # type: ignore[arg-type]
    first_second = [moment for moment in fast if steps[0] <= moment < steps[1]]
    assert len(first_second) == 9  # nine tenth-of-a-second checks between two full checks
    assert len([moment for moment in written if steps[0] <= moment < steps[1]]) == 10  # the screen's marks: every tenth
    assert stopped == [True]  # whatever ends the loop (here an interrupt), the writer stops
    assert all(abs((b - a).total_seconds() - engine_module.FAST_EXIT_SECONDS) < 1e-6 for a, b in zip(first_second, first_second[1:]))
    assert massive.calls[0] == {"AAA"} and massive.calls[-1] == set()  # the sale between checks: the stream follows at once
    assert len(fast) == 20  # held nothing after the sale: no more tenth-of-a-second checks
    assert any(steps[2] <= moment <= steps[3] for moment in commits)  # the sale committed between the full checks


def test_the_session_runs_its_passes_while_a_step_waits_on_massive(tmp_path: Path, monkeypatch) -> None:
    """Load test of 31/10: while a step waits on Massive (0.6 s here, ``between`` called every 0.01 s as ``ask_nbbo``
    does), the held names keep their passes on the pushed NBBO: at least one every tenth of a second, one at once on a
    new quote. The sale of a pass is one of the step's fills (the stream follows, a commit), and the screen gets marks."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    carried = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, _at(9, 31).isoformat(), last_mark=98.0)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6, positions={"AAA": carried}))
    wall, clock, steps, fast, hooks, pushed_at = {"t": 0.0}, {"t": _at(9, 30, 59)}, [], [], [], []
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def advance(seconds):
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)

    class Massive:
        status, reconnects = "connected", 0

        def __init__(self) -> None:
            self.calls: list[set[str]] = []
            self.updated = False

        def set_symbols(self, symbols) -> None:
            self.calls.append(set(symbols))

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, 0)

        def wait_update(self, timeout):  # a quote pushed during the wait is seen at once; none between the steps
            updated, self.updated = self.updated, False
            if not updated:
                advance(timeout)
            return updated
    massive = Massive()

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):  # 0.6 s waiting on Massive
        steps.append(now)
        hooks.append(between)
        for tick in range(60):
            advance(0.01)
            if len(steps) == 1 and tick == 24:  # a new quote 0.25 s into the first wait
                massive.updated = True
                pushed_at.append(clock["t"])
            if between is not None:
                between()
        return []

    def fast_exits(self, now, view, pushed):
        fast.append(now)
        if pushed_at and now == pushed_at[0]:  # the new quote stops AAA
            self.state.positions.pop("AAA")
            return [{"side": "SELL", "symbol": "AAA"}]
        return []
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "fast_exits", fast_exits)

    def sleep(seconds):
        advance(seconds)
        if len(steps) >= 3:
            raise KeyboardInterrupt
    commits, written = [], []
    monkeypatch.setattr(engine_module, "save_state", lambda db, state, moment: commits.append((moment, sorted(state.positions))))

    class Writer:  # the marks writer's hand-overs, synchronously
        def __init__(self, write) -> None:
            pass

        def submit(self, session, as_of, marks) -> None:
            written.append(as_of)

        def stop(self) -> None:
            pass
    monkeypatch.setattr(engine_module, "MarksWriter", Writer)
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=_FakeStream(), database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None, massive=massive)  # type: ignore[arg-type]
    wait = steps[0] + timedelta(seconds=0.6)
    assert hooks[0] is not None and len(steps) == 3
    assert len(fast) == 3 and fast[-1] == pushed_at[0]  # two passes a tenth apart, then one at once on the new quote
    gaps = [(b - a).total_seconds() for a, b in zip([steps[0]] + fast, fast)]
    assert max(gaps) <= engine_module.FAST_EXIT_SECONDS + 0.011
    # the opening checkpoint holds AAA; the sale in the wait is committed once, after its step, and never again
    assert commits == [(steps[0], ["AAA"]), (steps[0], [])] and massive.calls[-1] == set()
    assert len([m for m in written if steps[0] < m < wait]) == 3  # the screen's marks on each pass of the wait


def _waiting_session(tmp_path: Path, monkeypatch, start: datetime, ticks: int, fast_exits, steps: list, commits: list,
                     sleep_ends: bool = False, buy: bool = True) -> None:
    """``run_session`` with AAA held and Massive followed (no ``wait_update``: a pass at least every tenth), each step
    waiting ``ticks`` x 0.01 s on Massive, calling ``between`` after each tick, and filling one buy (none without
    ``buy``). The steps' instants and the commits (instant, held names) go to ``steps`` and ``commits``; with
    ``sleep_ends`` the first sleep ends the session."""
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    carried = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, _at(9, 31).isoformat(), last_mark=98.0)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6, positions={"AAA": carried}))
    wall, clock = {"t": 0.0}, {"t": start}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def advance(seconds):
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)

    class Massive:
        status, reconnects = "connected", 0

        def set_symbols(self, symbols) -> None:
            pass

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, 0)

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):
        steps.append(now)
        for _ in range(ticks):
            advance(0.01)
            if between is not None:
                between()
        return [{"side": "BUY", "symbol": "BBB"}] if buy else []

    def sleep(seconds):
        if sleep_ends:
            raise KeyboardInterrupt
        assert len(steps) < 3, "the session ran past the steps this test expects"  # never a whole session
        advance(seconds)

    class Writer:
        def __init__(self, write) -> None:
            pass

        def submit(self, session, as_of, marks) -> None:
            pass

        def stop(self) -> None:
            pass
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "fast_exits", fast_exits)
    monkeypatch.setattr(engine_module, "save_state", lambda db, state, moment: commits.append((moment, sorted(state.positions))))
    monkeypatch.setattr(engine_module, "MarksWriter", Writer)
    run_session(stream=_FakeStream(), database=Database(Settings(database_url="")), get_json=None, base_url="", token="",  # type: ignore[arg-type]
                day=DAY, cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None,
                massive=Massive())  # type: ignore[arg-type]


def test_a_pass_that_fails_in_a_wait_ends_the_session_once_the_steps_fills_are_committed(tmp_path: Path, monkeypatch) -> None:
    """Pre-reviews of c0b7c4a4 and a76ed3eb: an error in a pass run during a step's wait left the step before its fills
    were committed. The step's waits run no more passes, the step's fills are committed — a sale the failing pass made
    before it raised included — and the error is raised then, ending the session as a failed pass after a step did."""
    calls = []

    def fast_exits(self, now, view, pushed):
        calls.append(now)
        raise RuntimeError("the pass failed")
    steps: list = []
    commits: list = []
    with pytest.raises(RuntimeError, match="the pass failed"):
        _waiting_session(tmp_path, monkeypatch, _at(9, 30, 59), 60, fast_exits, steps, commits)
    assert len(calls) == 1 and len(steps) == 1  # one pass in the wait, then none, and the session ends after the step
    assert commits == [(steps[0], ["AAA"]), (steps[0], ["AAA"])]  # the opening checkpoint, then the step's buy
    steps.clear()
    commits.clear()
    with pytest.raises(RuntimeError, match="the pass failed"):  # no fill at all: the checkpoint still comes first
        _waiting_session(tmp_path, monkeypatch, _at(9, 30, 59), 60, fast_exits, steps, commits, buy=False)
    assert commits == [(steps[0], ["AAA"]), (steps[0], ["AAA"])]

    def selling_then_failing(self, now, view, pushed):  # stops AAA, then fails on another name
        assert self._exit(self.state.positions["AAA"], MarketView(price=90.0, trade_at=now), now, 90.0, "fast") is not None
        raise RuntimeError("the pass failed after a sale")
    steps.clear()
    commits.clear()
    with pytest.raises(RuntimeError, match="after a sale"):
        _waiting_session(tmp_path, monkeypatch, _at(9, 30, 59), 60, selling_then_failing, steps, commits, buy=False)
    assert commits == [(steps[0], ["AAA"]), (steps[0], [])]  # no fill of the step's own: the sale alone is committed


def test_a_wait_that_crosses_the_close_runs_no_pass_at_or_past_it(tmp_path: Path, monkeypatch) -> None:
    """A step that starts just before 16:00 and waits on Massive across it: the passes in its wait stop at the close."""
    calls = []

    def fast_exits(self, now, view, pushed):
        calls.append(now)
        return []
    with pytest.raises(KeyboardInterrupt):
        _waiting_session(tmp_path, monkeypatch, _at(15, 59, 59) + timedelta(milliseconds=420), 100, fast_exits, [], [],
                         sleep_ends=True)
    close = _at(16, 0)
    assert len(calls) >= 4 and all(moment < close for moment in calls)  # a pass a tenth until 16:00, none in the last 0.42 s


def test_the_marks_writer_never_blocks_keeps_only_the_latest_and_logs_a_failure_once(monkeypatch, caplog) -> None:
    """Pre-review of 62bdbd3b P1-2: the exits' loop waited on a database commit up to ten times a second. It now only
    hands its latest marks over; one thread writes the newest it holds, never a queue, and waits after a failure."""
    import logging
    import threading
    import time as wall

    caplog.set_level(logging.INFO, logger=engine_module.logger.name)
    monkeypatch.setattr(engine_module, "MARKS_RETRY_SECONDS", 0.05)
    release, written = threading.Event(), []

    def slow(session, as_of, marks):
        release.wait(5)
        written.append(as_of)
    writer = engine_module.MarksWriter(slow)
    began = wall.monotonic()
    for second in range(5):
        writer.submit("2026-10-28", _at(10, 0, second), [])
    assert wall.monotonic() - began < 0.05  # a hand-over never waits on the database
    release.set()
    deadline = wall.monotonic() + 2
    while _at(10, 0, 4) not in written and wall.monotonic() < deadline:
        wall.sleep(0.01)
    assert written[-1] == _at(10, 0, 4) and len(written) <= 2  # the first one taken, then only the newest
    writer.stop()

    calls = []

    def failing(session, as_of, marks):
        calls.append(as_of)
        if len(calls) < 4:
            raise RuntimeError("database down")
    writer = engine_module.MarksWriter(failing)
    for second in range(4):
        writer.submit("2026-10-28", _at(10, 1, second), [])
        deadline = wall.monotonic() + 1
        while len(calls) <= second and wall.monotonic() < deadline:
            wall.sleep(0.01)
    deadline = wall.monotonic() + 1  # the recovery is logged after the successful write returns
    while not any("written again" in record.getMessage() for record in caplog.records) and wall.monotonic() < deadline:
        wall.sleep(0.01)
    writer.stop()
    messages = [record.getMessage() for record in caplog.records]
    assert sum("could not be written" in message for message in messages) == 1  # the failure once
    assert sum("written again" in message for message in messages) == 1 and writer.failures == 3  # and its recovery once


def test_a_tenth_of_a_second_check_whose_read_crosses_the_close_never_sells(monkeypatch) -> None:
    """Codex 6527492839: the pass began at 15:59:59.900, the view's read took 0.2 s and the pushed quote, stamped
    16:00:00.100, sold. The close is checked again at the effective instant, after the reads."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    engine.state.positions["CCC"] = Position("CCC", "NYSE", 1000.0, 29.0, 29_001.45, t.isoformat(), last_mark=29.0)
    wall = {"t": 500.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])
    start = _at(15, 59, 59) + timedelta(milliseconds=900)
    stop = _bid_at(position, -0.45)

    def slow_view(symbol):
        wall["t"] += 0.2  # every read takes 0.2 s: the first one already crosses 16:00
        return MarketView(price=98.0, trade_at=start, vwap=98.0)
    fills = engine.fast_exits(start, slow_view, lambda s: (stop, stop + 0.01, start + timedelta(milliseconds=200)) if s == "AAA" else None)
    assert fills == [] and "AAA" in engine.state.positions and engine.exit_sources["fast"] == 0
    wall["t"] = 500.0
    early = _at(15, 59, 58)  # the same pass a second earlier sells
    fills = engine.fast_exits(early, slow_view, lambda s: (stop, stop + 0.01, early) if s == "AAA" else None)
    assert [f["symbol"] for f in fills] == ["AAA"]


def test_the_marks_carry_the_level_the_rule_sells_at() -> None:
    engine = _engine()
    position = _bought_aaa(engine, _at(10, 0, 1))
    row = engine.marks()[0]
    assert row["symbol"] == "AAA" and row["armed"] is False and row["stop_percent"] == -engine_module.RULE["stop_percent"]
    assert row["stop_price"] == position.exit_price() and row["bid"] == position.last_mark
    assert (row["opened_at"], row["quantity"], row["cost_usd"]) == (position.opened_at, round(position.shares, 6),
                                                                     round(position.cost_usd, 2))


def test_the_engines_marks_dress_the_book_it_publishes_through_the_real_store(tmp_path: Path) -> None:
    """Pre-review of eb72ce47: the book rounds cost to cents and shares to 6 decimals; marks with the raw floats matched no
    position, so the screen fell back to the feed for every name. Through document, store and latest_book with an uneven
    NAV, the engine's marks are laid on its own book."""
    from app import r2d2_lab_live

    database = Database(Settings(database_url=""))
    engine = _engine(nav=931214.4417)
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    assert round(position.cost_usd, 2) != position.cost_usd  # an uneven cost, as in production
    r2d2_lab_live.store(database, engine.document(t), now=t, max_trades=engine_module.ENGINE_MAX_TRADES)
    found = r2d2_lab_live.latest_book(database, now=t)
    assert found is not None
    mark_at = t + timedelta(seconds=1)
    engine.marked_moment["AAA"] = mark_at
    row = {"session": DAY.isoformat(), "as_of": mark_at, "marks": engine.marks()}
    dressed = r2d2_lab_live.overlay_marks(found[2], row, DAY.isoformat(), mark_at + timedelta(milliseconds=100))
    assert dressed["positions"][0]["mark_as_of"] == mark_at.isoformat() and dressed["positions"][0]["stop_percent"] == -0.2
    t = _at(10, 0, 2)
    up = _bid_at(position, 0.17)
    engine.step(t, lambda s: MarketView(price=98.3, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(),
                nbbo=lambda s, now: (up, up + 0.01, now))
    row = engine.marks()[0]
    assert row["armed"] is True and row["stop_percent"] == pytest.approx(0.10) and row["net_percent"] == pytest.approx(0.17)
    assert row["marked_at"] == t.isoformat() or row["marked_at"] > t.isoformat()


def test_a_full_check_whose_reads_cross_the_close_never_sells(monkeypatch) -> None:
    """The same witness on the full check (pre-review of ab570efb): its pushed phase and its Massive/feed phase never
    mark nor sell at or past 16:00, wherever a read or Massive's wait crosses it."""
    for pushed_quote in (True, False):
        engine = _engine()
        position = _bought_aaa(engine, _at(10, 0, 1))
        wall = {"t": 900.0}
        monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])
        start = _at(15, 59, 59) + timedelta(milliseconds=900)
        stop = _bid_at(position, -0.45)

        calls = {"n": 0}

        def slow_view(symbol):  # the pushed phase's read crosses 16:00; without a pushed quote, the Massive phase's read does
            calls["n"] += 1
            wall["t"] += 0.2 if (pushed_quote or calls["n"] == 2) else 0.05
            return MarketView(price=98.0, trade_at=start, vwap=98.0)
        pushed = (lambda s: (stop, stop + 0.01, start)) if pushed_quote else (lambda s: None)
        fills = engine.step(start, slow_view, nbbo=lambda s, now: (stop, stop + 0.01, now), pushed=pushed)
        assert [f for f in fills if f["side"] == "SELL"] == [] and "AAA" in engine.state.positions, pushed_quote
        assert engine.exit_sources["massive"] == 0 and position.last_mark == 98.095  # never marked: its own quote's bid


def test_the_tenth_of_a_second_checks_never_run_past_the_close(tmp_path: Path, monkeypatch) -> None:
    """Pre-review of e1149ca5 P1: the last full check at 15:59:59.45 left half its tenth-of-a-second checks after 16:00,
    where a post-close quote could sell. Every check stops at the close."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    carried = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, _at(9, 31).isoformat(), last_mark=98.0)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6, positions={"AAA": carried}))
    wall, clock, checks = {"t": 0.0}, {"t": _at(15, 59, 58) + timedelta(milliseconds=450)}, []
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):
        wall["t"] += 0.05
        clock["t"] += timedelta(seconds=0.05)
        return []

    def fast_exits(self, now, view, pushed):
        checks.append(now)
        return []
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "fast_exits", fast_exits)

    def sleep(seconds):
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)

    class Massive:
        status, reconnects = "connected", 0

        def set_symbols(self, symbols) -> None:
            pass

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, 0)
    run_session(stream=_FakeStream(), database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None, massive=Massive())  # type: ignore[arg-type]
    close = datetime.combine(DAY, engine_module.SESSION_CLOSE, tzinfo=NEW_YORK)
    assert checks and max(checks) < close  # some checks ran in the last second, none at or after the close
    assert any(moment >= close - timedelta(seconds=1) for moment in checks)


def test_the_stream_wakes_the_exits_on_every_new_quote_of_a_followed_name() -> None:
    import threading
    import time as wall

    from app.r2d2_live_engine import MassiveQuoteStream

    stream = MassiveQuoteStream("key")
    stream.set_symbols({"AAA"})
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    began = wall.monotonic()
    assert stream.wait_update(0.05) is False and wall.monotonic() - began >= 0.04  # nothing new: the timeout
    stream._record(json.dumps([{"ev": "Q", "sym": "ZZZ", "bp": 1.0, "ap": 1.01, "t": now_ms}]))  # not followed
    assert stream.wait_update(0.02) is False
    threading.Timer(0.02, lambda: stream._record(json.dumps([{"ev": "Q", "sym": "AAA", "bp": 98.0, "ap": 98.02, "t": now_ms}]))).start()
    began = wall.monotonic()
    assert stream.wait_update(2.0) is True and wall.monotonic() - began < 1.0  # woken by the quote, not the timeout
    stream._record(json.dumps([{"ev": "Q", "sym": "AAA", "bp": 98.01, "ap": 98.02, "t": now_ms + 1}]))
    assert stream.wait_update(0.0) is True and stream.wait_update(0.0) is False  # one signal, consumed once

    class Racing(threading.Event):  # the reader's signal lands right after a wait returned False
        def wait(self, timeout=None):
            seen = super().wait(timeout)
            if not seen:
                self.set()
            return seen
    stream._updated = Racing()
    assert stream.wait_update(0.0) is False and stream.wait_update(0.0) is True  # never cleared unseen (pre-review P2)


@pytest.mark.parametrize("quotes_streaming", [True, False])
def test_the_session_reacts_to_each_new_quote_at_most_every_ten_milliseconds(tmp_path: Path, monkeypatch, quotes_streaming) -> None:
    """Owner 30/10/2026 ~14:00: "reagirmos o mais rápido possível ao valor real e atual da cotação do ticker". With quotes
    pouring in, a pass every FAST_EXIT_MIN_SECONDS; with none, a pass every FAST_EXIT_SECONDS."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    carried = Position("AAA", "NASDAQ", 100.0, 98.0, 9800.49, _at(9, 31).isoformat(), last_mark=98.0)
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6, positions={"AAA": carried}))
    wall, clock, steps, fast = {"t": 0.0}, {"t": _at(9, 30, 59)}, [], []
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):
        steps.append(now)
        wall["t"] += 0.05
        clock["t"] += timedelta(seconds=0.05)
        return []

    def fast_exits(self, now, view, pushed):
        fast.append(now)
        return []
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "fast_exits", fast_exits)

    def advance(seconds):
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)

    def sleep(seconds):
        advance(seconds)
        if len(steps) >= 3:
            raise KeyboardInterrupt

    class Massive:
        status, reconnects = "connected", 0

        def set_symbols(self, symbols) -> None:
            pass

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, 0)

        calls = 0

        def wait_update(self, timeout):
            Massive.calls += 1
            assert Massive.calls < 5_000, "the loop spins: no floor between passes"  # fail, never hang
            if quotes_streaming:
                return True  # a new quote is already there
            advance(timeout)
            return False

    handed: list[datetime] = []

    class Writer:
        def __init__(self, write) -> None:
            pass

        def submit(self, session, as_of, marks) -> None:
            handed.append(as_of)

        def stop(self) -> None:
            pass
    monkeypatch.setattr(engine_module, "MarksWriter", Writer)
    monkeypatch.setattr(engine_module, "save_state", lambda db, state, moment: None)
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=_FakeStream(), database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None, massive=Massive())  # type: ignore[arg-type]
    first_second = [moment for moment in fast if steps[0] <= moment < steps[1]]
    gaps = [(b - a).total_seconds() for a, b in zip(first_second, first_second[1:])]
    assert all(abs((b - a).total_seconds() - 1.0) < 1e-6 for a, b in zip(steps, steps[1:]))  # the full check: once a second
    assert len([moment for moment in handed if steps[0] <= moment < steps[1]]) <= 11  # the screen's marks: ~every 0.1 s
    if quotes_streaming:
        assert len(first_second) >= 90 and all(gap >= engine_module.FAST_EXIT_MIN_SECONDS - 1e-6 for gap in gaps)
    else:  # a pass every FAST_EXIT_SECONDS; the second's last wait is cut short so the full check stays once a second
        assert 9 <= len(first_second) <= 10 and all(abs(gap - engine_module.FAST_EXIT_SECONDS) < 1e-6 for gap in gaps[:-1])
        assert 0 < gaps[-1] <= engine_module.FAST_EXIT_SECONDS + 1e-6


def test_the_status_workflow_publishes_the_massive_line_and_both_feed_lines_whole() -> None:
    import re

    workflow = (Path(__file__).resolve().parents[3] / ".github" / "workflows" / "r2d2-live-status.yml").read_text(encoding="utf-8")
    pattern = re.search(r'grep -oE "(R2D2 live heartbeat:.*?)"', workflow).group(1).replace(r"\$", "$")
    accepted = re.compile(pattern)
    engine = _engine()
    stream = engine_module.MassiveQuoteStream("key")
    line = engine_module.massive_line(stream, engine)
    assert line == ("R2D2 live massive: state=idle symbols=0 quotes=0 lag_ms=0 lag_max_ms=0 pushed=0 fast=0 reconnects=0"
                    " trade_symbols=0 trades=0 trade_lag_ms=0 trade_lag_max_ms=0 off_exchange=0 extended=0 sink_failures=0")
    feed = engine_module.feed_line(object(), engine)
    old = feed[:feed.index(" exits ")]
    before_trades = line[:line.index(" trade_symbols=")]  # the line of a process deployed before the trade source
    shadow = engine_module.shadow_trades_line(LiveEngineStream(""), LiveEngineStream(""), ["AAA"])
    assert shadow == ("R2D2 live shadow trades: names=1 both=0 vwap_bps_p50=0.0 vwap_bps_p90=0.0 last_bps_p50=0.0"
                      " last_bps_p90=0.0 open_agree=0")
    for text in (line, feed, old, before_trades, shadow):
        assert accepted.search(text) and accepted.search(text).group(0) == text
    assert not accepted.fullmatch(line + " key=x") and not accepted.fullmatch(feed + " extra")


def test_a_restored_candidate_the_universe_no_longer_lists_is_never_bought() -> None:
    engine = _engine()
    engine.candidates["ZZZ"] = -3.0  # restored from the state; the rebuilt universe has no member for it
    t = _at(10, 0)
    engine.step(t, lambda s: _view(9.9, 10.0, 9.99, 10.0, t))
    t = _at(10, 0, 1)
    assert [f["symbol"] for f in engine.step(t, lambda s: _view(10.1, 10.0, 10.0995, 10.1005, t) if s == "ZZZ" else MarketView())] == []


def test_the_session_loop_runs_once_a_second_and_logs_its_lines_every_minute_whatever_the_fills(tmp_path: Path, monkeypatch, caplog) -> None:
    import logging

    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6))
    wall, clock, slept, steps = {"t": 0.0}, {"t": _at(9, 30, 59)}, [], []
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: wall["t"])

    pusheds = []

    class Massive:  # the pushed NBBO's stand-in: what the session hands it and logs of it
        status, reconnects = "connected", 0

        def __init__(self) -> None:
            self.calls: list[set[str]] = []

        def set_symbols(self, symbols) -> None:
            self.calls.append(set(symbols))

        def quote(self, symbol):
            return None

        def take_gauges(self):
            return (0, 0, 0, len(self.calls[-1]) if self.calls else 0)
    massive = Massive()

    def step(self, now, view, signal=None, nbbo=None, pushed=None, between=None):  # each step waits 0.6 s on Massive and fills
        steps.append(now)
        pusheds.append(pushed)
        wall["t"] += 0.6
        clock["t"] += timedelta(seconds=0.6)
        return [{"side": "BUY"}]
    monkeypatch.setattr(Engine, "step", step)

    def sleep(seconds):
        slept.append(seconds)
        wall["t"] += seconds
        clock["t"] += timedelta(seconds=seconds)
        if len(steps) >= 150:
            raise KeyboardInterrupt
    caplog.set_level(logging.INFO, logger=engine_module.logger.name)
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=_FakeStream(), database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None, massive=massive)  # type: ignore[arg-type]
    after_steps = slept[-100:]
    assert all(abs(s - 0.4) < 1e-6 for s in after_steps)  # one pass a second: 0.6 s of step, 0.4 s of sleep
    assert 148 <= (steps[-1] - steps[0]).total_seconds() + 1 <= 151
    feed = [r for r in caplog.records if "R2D2 live feed:" in r.getMessage()]
    assert len(feed) == 2  # every 60 s although every step filled
    # the pushed NBBO: the held names followed from the start (none carried here), its reader handed to every step, and
    # its line every minute
    assert massive.calls[0] == set() and pusheds and all(pushed == massive.quote for pushed in pusheds)
    lines = [r.getMessage() for r in caplog.records if "R2D2 live massive:" in r.getMessage()]
    assert len(lines) == 2 and lines[0].startswith("R2D2 live massive: state=connected symbols=0 ")


# ------------------------------------------------------------------ Codex #500 P2 regressions
def _stream_with_session() -> LiveEngineStream:
    stream = LiveEngineStream("")
    stream.start_session(DAY)
    return stream


def test_p2_1_the_signal_is_the_live_trade_against_the_live_vwap() -> None:
    """Every second since 29/10 (owner): 09:40 closed at 99 below a VWAP of ~99.82; a tick of 101 at 09:41:00.100 is
    back above it and buys at the 09:41:00.500 check, at the real ask (until 29/10 it waited for the 09:41 close)."""
    stream = _stream_with_session()
    stream.record_trade("AAA", 100.0, 1000, _at(9, 35))
    stream.record_trade("AAA", 99.0, 100, _at(9, 40, 30))
    engine = _engine()
    engine.state.candidates = {"AAA": -2.0}
    decision = _at(9, 40, 31)
    assert stream.live_signal("AAA") == (99.0, (100.0 * 1000 + 99.0 * 100) / 1100)
    assert engine.step(decision, stream.view, stream.live_signal) == [] and engine.below["AAA"] is True
    stream.record_quote("AAA", 100.99, 101.01, _at(9, 41))
    stream.record_trade("AAA", 101.0, 10, _at(9, 41) + timedelta(milliseconds=100))
    fills = engine.step(_at(9, 41) + timedelta(milliseconds=500), stream.view, stream.live_signal)
    assert [(f["symbol"], f["price"]) for f in fills] == [("AAA", 101.01)]


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
    fresh = LiveEngineStream("")
    fresh.start_session(DAY, restoring=True)
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
    monkeypatch.setattr(engine_module, "load_targets", _permissive)
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
    assert workflow["jobs"]["status"]["environment"] == "production"  # the current host's secrets
    run = workflow["jobs"]["status"]["steps"][1]["run"]
    assert "|| true" not in run and 'exit "$rc"' in run and "|| rc=$?" in run
    assert "--status </dev/null || exit 13" in run and "[redacted]" in run
    # a public repository: error lines are counted, never printed
    assert 'grep -cE "ERROR|Traceback|Exception"' in run and "grep -oE" in run and "error=[01]" in run


# ---- Codex #500 recheck (6446688456)
def test_r2_p2_1_every_held_name_keeps_its_place_when_the_universe_is_cut() -> None:
    universe = [Member("X%03d" % i, "NASDAQ", 50.0, 20e6) for i in range(500)]
    positions = {"X499": object(), "OUT": object()}
    chosen = engine_module.subscription(universe, positions, size=500)
    assert len(chosen) == 500 and {"X499", "OUT"} <= set(chosen) and len(set(chosen)) == 500
    assert engine_module.subscription(universe, {}, size=500) == [m.symbol for m in universe]


def _replay(stream: LiveEngineStream, trades) -> None:
    for price, size, at in trades:
        stream.record_trade("AAA", price, size, at)


def test_r2_p2_2_a_restart_holds_the_feed_until_the_saved_prefix_is_installed() -> None:
    prefix = [(100.0, 1000, _at(9, 35)), (99.5, 1100, _at(11, 59, 30))]
    after = [(98.0, 100, _at(12, 0, 1)), (99.0, 100, _at(12, 0, 59) + timedelta(milliseconds=900))]
    continuous = _stream_with_session()
    _replay(continuous, prefix + after)
    saved = _stream_with_session()
    _replay(saved, prefix)
    context = json.loads(json.dumps(saved.export({"AAA"})))
    restarted = LiveEngineStream("")
    restarted.start_session(DAY, restoring=True)
    restarted.record_trade("AAA", *after[0][:2], after[0][2])  # the feed delivers it BEFORE the restore
    assert restarted.restoring and restarted.signal_view("AAA", 12 * 60 + 1) is None
    restarted.restore(context, _at(12, 0, 2))
    restarted.record_trade("AAA", *after[1][:2], after[1][2])
    assert not restarted.restoring
    assert restarted.view("AAA").vwap == continuous.view("AAA").vwap and restarted.view("AAA").price == continuous.view("AAA").price
    # the restore's minute may miss the trades of the gap: no signal from it; the next full minute observed live signals
    assert restarted.signal_view("AAA", 12 * 60 + 1) is None
    for stream in (continuous, restarted):
        stream.record_trade("AAA", 99.2, 100, _at(12, 1, 30))
        stream.record_trade("AAA", 99.3, 100, _at(12, 2, 1))
    assert restarted.signal_view("AAA", 12 * 60 + 2) == continuous.signal_view("AAA", 12 * 60 + 2) is not None
    # the every-second signal keeps the same guard: nothing from the restore's minute, then the live trade and VWAP
    gapped = LiveEngineStream("")
    gapped.start_session(DAY, restoring=True)
    gapped.restore(context, _at(12, 0, 2))
    gapped.record_trade("AAA", 98.0, 100, _at(12, 0, 30))
    assert gapped.live_signal("AAA") is None
    gapped.record_trade("AAA", 99.3, 100, _at(12, 1, 1))
    live = gapped.live_signal("AAA")
    assert live is not None and live[0] == 99.3 and live[1] == gapped.view("AAA").vwap


def test_r2_an_in_process_retry_keeps_the_live_tapes_and_the_opening_is_the_earliest_print(tmp_path: Path, monkeypatch) -> None:
    stream = _stream_with_session()
    stream.record_trade("AAA", 101.0, 10, _at(9, 30, 5))
    stream.record_trade("AAA", 100.0, 10, _at(9, 30, 1))  # a late, earlier print is the opening
    assert stream.opening == {"AAA": 100.0}
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    resumed = EngineState(nav_realized=1000.0, session=DAY.isoformat(), candidates_fixed=True,
                          stream_context={"AAA": {"pv": 1.0, "volume": 1.0, "last_price": 1.0, "minute": 571}})
    monkeypatch.setattr(engine_module, "load_state", lambda db, seed: resumed)
    calls: list[str] = []
    monkeypatch.setattr(stream, "start_session", lambda *a, **k: calls.append("start"))
    monkeypatch.setattr(stream, "restore", lambda *a, **k: calls.append("restore"))
    monkeypatch.setattr(stream, "set_group", lambda *a, **k: None)
    clock = {"t": _at(16, 0, 1)}
    run_session(stream=stream, database=database, get_json=lambda *a, **k: None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                cache_dir=tmp_path, now=lambda: clock["t"], sleep=lambda s: None)
    assert calls == [] and stream.view("AAA").price == 101.0  # the live tape was kept, not replaced by the checkpoint


def test_r2_a_long_holiday_never_wedges_the_reconcile() -> None:
    database = Database(Settings(database_url=""))
    engine = Engine(EngineState(nav_realized=1_000_000.0), DAY, [Member("AAA", "NASDAQ", 100.0, 50e6)])
    engine.state.candidates, engine.state.below = {"AAA": -2.0}, {"AAA": False}
    engine._buy("AAA", 101.01, -2.0, 2.0, _at(10, 0))
    saved = EngineState.from_json(json.loads(json.dumps(engine.state.to_json())))
    later = DAY + timedelta(days=6)
    assert engine_module.reconcile_previous(database, saved, later, _at(9, 0) + timedelta(days=6)) is True  # refused by the screen
    assert saved.last_session == DAY.isoformat() and saved.session == ""  # closed: the next session starts
    assert engine_module.reconcile_previous(database, saved, later, _at(9, 1) + timedelta(days=6)) is True  # still pending, never raises
    flat = EngineState(nav_realized=1.0, session=DAY.isoformat())
    assert engine_module.reconcile_previous(database, flat, later, _at(9, 0) + timedelta(days=6)) is True  # unclosed, no fills: closed
    assert flat.last_session == DAY.isoformat() and flat.session == ""


def test_r2_p2_4_a_late_trade_of_the_completed_minute_moves_its_close_and_vwap() -> None:
    trades = [(100.0, 1000, _at(9, 35)), (99.0, 100, _at(9, 40, 30)), (101.5, 1200, _at(9, 40, 59) + timedelta(milliseconds=950)),
              (101.0, 10, _at(9, 41) + timedelta(milliseconds=100))]
    in_order, late = _stream_with_session(), _stream_with_session()
    _replay(in_order, trades)
    _replay(late, [trades[0], trades[1], trades[3], trades[2]])  # 09:40:59.950 arrives after the 09:41:00.100 tick
    minute = 9 * 60 + 41
    assert late.signal_view("AAA", minute) == in_order.signal_view("AAA", minute)
    close, vwap = late.signal_view("AAA", minute) or (0.0, 0.0)
    assert close == 101.5 and abs(vwap - (100.0 * 1000 + 99.0 * 100 + 101.5 * 1200) / 2300) < 1e-9
    assert late.view("AAA").price == 101.0  # the current price is still the newest trade
    for engine_stream in (in_order, late):
        engine_stream.record_quote("AAA", 101.0, 101.02, _at(9, 41))
    engines = [_engine(), _engine()]
    for engine in engines:
        engine.state.candidates, engine.state.below = {"AAA": -2.0}, {"AAA": True}
    decision = _at(9, 41) + timedelta(milliseconds=500)
    assert late.live_signal("AAA") == in_order.live_signal("AAA") == (101.0, (100.0 * 1000 + 99.0 * 100 + 101.5 * 1200 + 101.0 * 10) / 2310)
    assert [f["symbol"] for f in engines[0].step(decision, in_order.view, in_order.live_signal)] == \
           [f["symbol"] for f in engines[1].step(decision, late.view, late.live_signal)] == ["AAA"]


def test_r2_p2_3_the_previous_sessions_pending_sell_is_published_before_its_fills_are_cleared() -> None:
    database = Database(Settings(database_url=""))
    previous = DAY
    state = EngineState(nav_realized=1_000_000.0)
    engine = Engine(state, previous, [Member("AAA", "NASDAQ", 100.0, 50e6)])
    engine.state.candidates = {"AAA": -2.0}
    engine.state.below = {"AAA": False}
    engine._buy("AAA", 101.01, -2.0, 2.0, _at(10, 0))  # the BUY, published
    engine_module.publish(database, engine, _at(10, 0))
    position = engine.state.positions["AAA"]
    engine._sell(position, 100.4, position.net_percent(100.4), "hard_stop", _at(15, 59, 59))  # checkpoint saved, the screen write failed
    saved = EngineState.from_json(json.loads(json.dumps(engine.state.to_json())))
    stale = (database.latest_analysis_snapshot(engine_module.r2d2_lab_live.ANALYSIS_TYPE, previous.isoformat()) or {})["outputs"]
    assert [t["side"] for t in stale["trades"]] == ["BUY"]
    next_day = DAY + timedelta(days=1)
    assert engine_module.reconcile_previous(database, saved, next_day, _at(9, 0) + timedelta(days=1)) is True
    fixed = (database.latest_analysis_snapshot(engine_module.r2d2_lab_live.ANALYSIS_TYPE, previous.isoformat()) or {})["outputs"]
    assert [t["side"] for t in fixed["trades"]] == ["BUY", "SELL"] and saved.last_session == previous.isoformat()
    assert engine_module.reconcile_previous(database, saved, next_day, _at(9, 1) + timedelta(days=1)) is False  # already in place
    fresh = Engine(saved, next_day, [])
    assert not fresh.fills  # cleared only now, after the previous document carries them


def test_r2_p2_5_the_heartbeat_carries_numbers_and_a_closed_state_never_an_error_text() -> None:
    import re
    import yaml

    class Noisy:
        status = "auth refused for AAPL"
        last_error = "401 AAPL token=secret"
        last_trade: dict = {}
        nbbo: dict = {}
    line = engine_module.heartbeat(Noisy(), _engine(), _at(10, 0))
    assert "AAPL" not in line and "secret" not in line and "stream=other error=1" in line
    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    pattern = run.split('grep -oE "', 1)[1].split('" | tail', 1)[0]
    assert re.search(pattern, "r2d2-live-1  | 2026-10-28 10:00:00 INFO app.r2d2_live_engine " + line)
    assert not re.search(pattern, "R2D2 live heartbeat: stream connected (auth refused for AAPL), trades 1")



def test_r2b_a_retry_after_the_first_checkpoint_failed_keeps_the_opening_and_the_vwap(tmp_path: Path, monkeypatch) -> None:
    """Codex 501/6452206633: the first save of the day fails before anything is durable; main retries with the SAME stream.
    The retry is not 'resumed' (no checkpoint of today), yet the stream's tapes of today must survive."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1_000_000.0))
    real_save = engine_module.save_state
    failures = {"left": 1}

    def flaky_save(db, state, moment):
        if failures["left"]:
            failures["left"] -= 1
            raise RuntimeError("the first checkpoint failed")
        return real_save(db, state, moment)
    monkeypatch.setattr(engine_module, "save_state", flaky_save)
    stream = LiveEngineStream("")
    monkeypatch.setattr(stream, "set_group", lambda *a, **k: None)
    clock = {"t": _at(9, 30, 30)}

    def sleep(seconds):
        if clock["t"] < _at(9, 30, 40) <= clock["t"] + timedelta(seconds=max(seconds, 0.05)):
            stream.record_trade("AAA", 98.0, 1000, _at(9, 30, 40))  # the opening print, 2% below the previous close
        clock["t"] += timedelta(seconds=max(seconds, 0.05))
    with pytest.raises(RuntimeError, match="first checkpoint"):
        run_session(stream=stream, database=database, get_json=lambda *a, **k: None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep)
    assert stream.opening == {"AAA": 98.0}
    stream.record_trade("AAA", 100.5, 100, _at(9, 32))  # the feed goes on between the failure and the retry
    clock["t"] = _at(16, 0, 1)
    state = run_session(stream=stream, database=database, get_json=lambda *a, **k: None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                        cache_dir=tmp_path, now=lambda: clock["t"], sleep=lambda s: None)
    assert stream.opening == {"AAA": 98.0}
    assert abs((stream.view("AAA").vwap or 0) - (98.0 * 1000 + 100.5 * 100) / 1100) < 1e-9
    assert state.candidates == {"AAA": pytest.approx(-2.0)}


# ---- 28/10: 164 signals and no buy — the feed reader fell behind (every quote stale) or the spread refused them
def test_feed_the_reader_subscribes_once_and_again_only_when_a_group_changes(monkeypatch) -> None:
    import asyncio

    stream = LiveEngineStream("tok", max_symbols=550)
    stream.set_group(engine_module.STREAM_GROUP, ["AAA", "BBB"], priority=200)
    stream.start_session(DAY)
    sent: list[dict] = []
    stamp = int(_at(10, 0).timestamp() * 1000)
    trades = [json.dumps({"s": "AAA", "p": 98.0 + i / 100, "v": 100, "t": stamp + i, "ms": "open"}) for i in range(50)]

    class Socket:
        def __init__(self) -> None:
            self.messages = [json.dumps({"status_code": 200})] + trades

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, text: str) -> None:
            sent.append(json.loads(text))

        async def recv(self) -> str:
            if len(self.messages) == 25:  # mid-stream, the held names change once
                stream.set_group(engine_module.STREAM_GROUP, ["AAA", "CCC"], priority=200)
            if not self.messages:
                stream._stop.set()
                raise TimeoutError
            return self.messages.pop(0)

    monkeypatch.setattr(engine_module.websockets, "connect", lambda url, **kwargs: Socket())
    asyncio.run(stream._run_feed("trade", "us", stream._record))
    assert sent == [{"action": "subscribe", "symbols": "AAA,BBB"},
                    {"action": "unsubscribe", "symbols": "BBB"}, {"action": "subscribe", "symbols": "CCC"}]
    assert stream.view("AAA").price == pytest.approx(98.49)  # every message reached the tape, in order
    assert stream.status == "stopped"


def test_feed_a_reconnect_subscribes_from_scratch_and_never_prints_the_token(monkeypatch, caplog) -> None:
    import asyncio

    stream = LiveEngineStream("tok-secret", max_symbols=550)
    stream.set_group(engine_module.STREAM_GROUP, ["AAA"], priority=200)
    sent: list[dict] = []
    connections = {"n": 0}

    class Socket:
        def __init__(self) -> None:
            connections["n"] += 1
            self.first = connections["n"] == 1
            self.messages = [json.dumps({"status_code": 200})]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, text: str) -> None:
            sent.append(json.loads(text))

        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            if self.first:
                raise RuntimeError("dropped tok-secret")
            stream._stop.set()
            raise TimeoutError

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(engine_module.websockets, "connect", lambda url, **kwargs: Socket())
    monkeypatch.setattr(engine_module.asyncio, "sleep", no_sleep)
    asyncio.run(stream._run_feed("quote", "us-quote", stream._record_quote))
    assert sent == [{"action": "subscribe", "symbols": "AAA"}, {"action": "subscribe", "symbols": "AAA"}]
    assert "tok-secret" not in caplog.text and "[redacted]" in caplog.text


def test_feed_the_lag_and_the_reasons_a_signal_did_not_buy_are_counted() -> None:
    import re
    import yaml

    stream = LiveEngineStream("x", max_symbols=550)
    stream.start_session(DAY)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    stream._record_quote(json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": now_ms - 7000}))
    stream._record_quote(json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": now_ms - 2000}))
    stream._record_quote(json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": 0}))  # malformed: never a gauge reading
    assert 1500 < stream.lag_ms["quote"] < 3000 and 6500 < stream.lag_max_ms["quote"] < 8000
    assert stream.messages == {"trade": 0, "quote": 2}

    engine = _engine()
    t = _at(9, 40)
    views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}
    engine.step(t, lambda s: views.get(s, MarketView()))
    t = _at(9, 41)
    stale = MarketView(price=98.1, trade_at=t, vwap=98.0, bid=98.095, ask=98.105, quote_at=t - timedelta(seconds=6))
    views = {"AAA": stale, "CCC": _view(29.1, 29.0, 29.0, 29.2, t)}  # AAA stream quote 6 s old (its bound: 5 s), CCC 69 bps
    assert engine.step(t, lambda s: views.get(s, MarketView())) == []
    assert engine.skips == {"held": 0, "slots": 0, "noquote": 0, "stale": 1, "spread": 1, "late": 0, "implausible": 0} and engine.signals == 2
    views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": MarketView(price=28.9, trade_at=t, vwap=29.0)}
    engine.step(_at(9, 42), lambda s: views.get(s, MarketView()))
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, _at(9, 43)), "CCC": MarketView(price=29.1, trade_at=t, vwap=29.0)}
    fills = engine.step(_at(9, 43), lambda s: views.get(s, MarketView()))  # AAA buys; CCC never had a quote
    assert [f["symbol"] for f in fills] == ["AAA"] and engine.skips["noquote"] == 1 and engine.signals == 4

    line = engine_module.feed_line(stream, engine)
    assert line.startswith("R2D2 live feed: trade_messages=0 quote_messages=2 trade_lag_ms=0 quote_lag_ms=")
    assert line.endswith("skips held=0 slots=0 noquote=1 stale=1 spread=1 late=0 implausible=0 nbbo massive=0 stream=3 unanswered=0 mismatch=0 stream_would_refuse=0 exits massive=0 stream=0 none=0 unconfirmed=0")
    assert stream.lag_max_ms == {"trade": 0, "quote": 0} and stream.messages == {"trade": 0, "quote": 0}  # per interval
    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    pattern = run.split('grep -oE "', 1)[1].split('" | tail', 1)[0]
    assert re.search(pattern, "r2d2-live-1  | 2026-10-28 10:00:00 INFO app.r2d2_live_engine " + line)


def test_feed_every_message_counts_in_exactly_one_interval_under_a_concurrent_heartbeat() -> None:
    """Codex 6473172399: the feed thread and the heartbeat race; no message may vanish from both intervals."""
    import random
    import threading

    stream = LiveEngineStream("x", max_symbols=550)
    stream.start_session(DAY)
    engine = _engine()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    lags = {"trade": [], "quote": []}
    rng = random.Random(7)
    payloads = []
    for i in range(6000):
        kind, lag = ("trade" if i % 2 else "quote"), rng.randint(1_000, 90_000)
        lags[kind].append(lag)
        if kind == "trade":
            payloads.append((kind, json.dumps({"s": "AAA", "p": 98.0, "v": 10, "t": now_ms - lag, "ms": "open"})))
        else:
            payloads.append((kind, json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": now_ms - lag})))
    done = threading.Event()

    def feed() -> None:
        for kind, payload in payloads:
            (stream._record if kind == "trade" else stream._record_quote)(payload)
        done.set()

    lines = []
    worker = threading.Thread(target=feed)
    worker.start()
    while not done.is_set():
        lines.append(engine_module.feed_line(stream, engine))
    worker.join()
    lines.append(engine_module.feed_line(stream, engine))
    for kind in ("trade", "quote"):
        counts = [int(line.split(kind + "_messages=")[1].split()[0]) for line in lines]
        worst = [int(line.split(kind + "_lag_max_ms=")[1].split()[0]) for line in lines]
        assert sum(counts) == len(lags[kind])  # every message in exactly one interval
        assert max(worst) >= max(lags[kind]) - 50 and all(w == 0 for c, w in zip(counts, worst) if c == 0)


@pytest.mark.parametrize("kind", ["trade", "quote"])
def test_feed_a_message_arriving_while_the_heartbeat_takes_the_interval_counts_once_with_its_lag(kind: str) -> None:
    """Codex 6473172399, the directed interleaving: the heartbeat is INSIDE the take (holding the gauges' lock) when the
    feed applies a 7 s late message. The feed must wait for the take, and the message must count in exactly one interval
    — the next — with its lag as THAT interval's worst; the tape or the NBBO gets it either way."""
    import threading
    import time as wall

    stream = LiveEngineStream("x", max_symbols=550)
    stream.start_session(DAY)
    engine = _engine()
    heartbeat = threading.current_thread()
    inside, moments = threading.Event(), {}

    class HeldLock:
        def __init__(self) -> None:
            self.inner = threading.Lock()

        def __enter__(self):
            self.inner.acquire()
            if threading.current_thread() is heartbeat and not inside.is_set():
                inside.set()
                wall.sleep(0.3)  # the feed thread reaches the gauges now
                moments["released"] = wall.monotonic()
            return self

        def __exit__(self, *exc):
            self.inner.release()
            return False

    stream._gauge_lock = HeldLock()  # type: ignore[assignment]
    stamp = int(_at(10, 0).timestamp() * 1000)
    payload = (json.dumps({"s": "AAA", "p": 98.0, "v": 10, "t": stamp, "ms": "open"}) if kind == "trade"
               else json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": stamp}))
    lag_at_send = {}

    def feed() -> None:
        inside.wait(5)
        lag_at_send["ms"] = int(wall.time() * 1000) - stamp
        (stream._record if kind == "trade" else stream._record_quote)(payload)
        moments["fed"] = wall.monotonic()

    worker = threading.Thread(target=feed)
    worker.start()
    first = engine_module.feed_line(stream, engine)
    worker.join(5)
    second = engine_module.feed_line(stream, engine)
    assert inside.is_set(), "the heartbeat must take the gauges under the lock the feed updates them with"
    assert moments["fed"] >= moments["released"]  # the feed waited for the take: it never wrote into a half-taken interval
    lines = [first, second]
    counts = [int(line.split(kind + "_messages=")[1].split()[0]) for line in lines]
    worst = [int(line.split(kind + "_lag_max_ms=")[1].split()[0]) for line in lines]
    assert counts == [0, 1]  # exactly one interval: the next
    assert worst[0] == 0 and lag_at_send["ms"] <= worst[1] < lag_at_send["ms"] + 5_000  # its lag in that same interval
    if kind == "trade":
        assert stream.view("AAA").price == 98.0
    else:
        assert stream.nbbo["AAA"][:2] == (98.0, 98.01)


# ---- 28/10 afternoon: the entries read the NBBO the lab measured (Massive, at most 60 s old), the stream only as fallback
def _crossing_engine():
    engine = _engine()
    t = _at(9, 40)
    below = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}
    engine.step(t, lambda s: below.get(s, MarketView()))
    return engine


def test_nbbo_a_buy_takes_the_massive_nbbo_where_the_streams_quote_was_wider() -> None:
    engine = _crossing_engine()
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.05, 98.15, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}  # stream: AAA 10 bps
    asked = []

    def nbbo(symbol, now):
        asked.append((symbol, now))
        return (98.095, 98.105, now - timedelta(seconds=20))  # Massive: 1 bp, quiet for 20 s (the lab takes it)
    fills = engine.step(t, lambda s: views.get(s, MarketView()), nbbo=nbbo)
    assert [(f["side"], f["symbol"], f["price"]) for f in fills] == [("BUY", "AAA", 98.105)]
    assert "NBBO Massive" in fills[0]["reason"] and [s for s, _ in asked] == ["AAA"]
    assert 0 <= (asked[0][1] - t).total_seconds() < 1  # asked at the effective instant
    assert engine.sources == {"massive": 1, "stream": 0, "unanswered": 0, "mismatch": 0, "stream_would_refuse": 1}


def test_a_day_whose_publish_failed_is_republished_under_its_own_rule_after_a_rule_change(monkeypatch) -> None:
    """Codex 6508087909: 29/10 checkpointed under TIT-2S3-RT (a state of the earlier code: no config field, the rule in
    its checkpoint's inputs), its public write failed; the 30/10 process (TIT-2S5-RT) republishes it under TIT-2S3-RT."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "CONFIG", "TIT-2S3-RT")
    engine = _engine()
    t = _at(9, 40)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    t = _at(9, 41)
    engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    engine.close_session()
    saved = engine.state.to_json()
    saved.pop("config")  # written by the earlier code: the rule is only in the checkpoint's inputs
    methodology = database.ensure_methodology_version("r2d2_live_engine", 2, {}, "earlier")
    database.save_analysis_snapshot(engine_module.STATE_TYPE, engine_module.STATE_KEY, methodology, {"config": "TIT-2S3-RT"},
                                    saved, t)
    assert database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, DAY.isoformat()) is None  # the publish failed
    monkeypatch.setattr(engine_module, "CONFIG", "TIT-2S5-RT")  # the rule changes overnight; the process restarts
    state = engine_module.load_state(database, lambda: None)
    assert state.config == "TIT-2S3-RT"
    next_day = DAY + timedelta(days=1)
    close_at = datetime.combine(DAY, engine_module.SESSION_CLOSE, tzinfo=NEW_YORK).astimezone(timezone.utc)
    assert engine_module.reconcile_previous(database, state, next_day, close_at + timedelta(hours=17)) is True
    stored = database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, DAY.isoformat())["outputs"]
    assert stored["config"] == "TIT-2S3-RT" and all(trade["id"].startswith("TIT-2S3-RT:") for trade in stored["trades"])
    assert Engine(state, next_day, []).state.config == "TIT-2S5-RT"  # the new session runs under the rule in force


def test_a_rule_change_never_rewrites_a_day_already_published(monkeypatch) -> None:
    """Pre-review of b84a436: 29/10 ran under TIT-2S3-RT; the next session (TIT-2S5-RT) reconciles it and must keep its
    config and trade ids — nothing is republished when the stored document already holds the day's fills."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "CONFIG", "TIT-2S3-RT")
    engine = _engine()
    t = _at(9, 40)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    t = _at(9, 41)
    engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    close_at = datetime.combine(DAY, engine_module.SESSION_CLOSE, tzinfo=NEW_YORK).astimezone(timezone.utc)
    engine_module.publish(database, engine, close_at, as_of=close_at)
    engine.close_session()
    monkeypatch.setattr(engine_module, "CONFIG", "TIT-2S5-RT")  # the rule changes overnight
    next_day = DAY + timedelta(days=1)
    assert engine_module.reconcile_previous(database, engine.state, next_day, close_at + timedelta(hours=17)) is False
    stored = database.latest_analysis_snapshot(r2d2_lab_live.ANALYSIS_TYPE, DAY.isoformat())["outputs"]
    assert stored["config"] == "TIT-2S3-RT" and all(trade["id"].startswith("TIT-2S3-RT:") for trade in stored["trades"])


@pytest.mark.parametrize(("ask", "bought"), [(29.01, True), (29.0145, True), (29.016, False)])
def test_the_spread_limit_is_five_basis_points(ask: float, bought: bool) -> None:
    """Owner 29/10: "vamos mudar para até 5 bps" — 3.4 and 4.999 bps buy, 5.5 bps is refused (it was 3 bps)."""
    assert engine_module.RULE["spread_max_bps"] == 5.0 and engine_module.CONFIG == "TIT-2S5-F20V"
    engine = _crossing_engine()
    t = _at(9, 41)
    views = {"CCC": _view(29.1, 29.0, 29.0, ask, t)}
    fills = engine.step(t, lambda s: views.get(s, MarketView()), nbbo=lambda s, now: (29.0, ask, now))
    assert ([f["symbol"] for f in fills] == ["CCC"]) is bought and engine.skips["spread"] == (0 if bought else 1)


def test_a_spread_of_exactly_five_basis_points_is_bought_whatever_its_float() -> None:
    """Pre-review of 43f7a89e: 119.97 x 120.03 is 5.00000000000019 bps in float — bought, as 39.99 x 40.01 (4.999999999999)."""
    for bid, ask, close, vwap in ((119.97, 120.03, 120.0, 119.9), (39.99, 40.01, 40.0, 39.9)):
        engine = _engine()
        engine.members["CCC"] = Member("CCC", "NYSE", close * 1.05, 20e6)
        engine.candidates["CCC"] = -4.8
        t = _at(9, 41)
        engine.step(t - timedelta(seconds=1), lambda s: _view(vwap - 0.1, vwap, bid - 0.1, ask - 0.1, t) if s == "CCC" else MarketView())
        fills = engine.step(t, lambda s: _view(close, vwap, bid, ask, t) if s == "CCC" else MarketView(),
                            nbbo=lambda s, now: (bid, ask, now))
        assert [f["symbol"] for f in fills] == ["CCC"] and engine.skips["spread"] == 0, (bid, ask)
        assert engine.state.positions["CCC"].cost_usd == pytest.approx(1_000_000.0 / 20 * 0.5)  # the 2.5% tier


def test_nbbo_massive_silent_falls_back_to_the_stream_and_an_old_or_wide_nbbo_is_refused() -> None:
    engine = _crossing_engine()
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.0, 29.02, t)}
    fills = engine.step(t, lambda s: views.get(s, MarketView()), nbbo=lambda s, now: None)
    assert [f["symbol"] for f in fills] == ["AAA"] and "cotação do stream" in fills[0]["reason"]
    assert engine.sources["unanswered"] == 2 and engine.sources["stream"] == 2 and engine.skips["spread"] == 1  # CCC 6.9 bps

    engine = _crossing_engine()
    old = lambda s, now: (98.095, 98.105, now - timedelta(seconds=61)) if s == "AAA" else (29.0, 29.2, now)
    assert engine.step(t, lambda s: views.get(s, MarketView()), nbbo=old) == []
    assert engine.skips["stale"] == 1 and engine.skips["spread"] == 1 and engine.sources["massive"] == 2


def test_nbbo_the_massive_reader_asks_for_the_quote_prevailing_at_the_instant_and_never_raises() -> None:
    calls = []
    now = _at(10, 15, 7)

    def get_json(url, params=None):
        calls.append((url, dict(params or {})))
        return {"results": [{"bid_price": 50.0, "ask_price": 50.01, "sip_timestamp": int(now.timestamp() * 1e9) - 3_000_000_000}]}
    nbbo = engine_module.massive_nbbo(get_json, "https://api.massive.com/", "tok")
    quote = nbbo("BRK.B", now)
    assert quote is not None
    bid, ask, at = quote
    assert (bid, ask) == (50.0, 50.01) and (now - at).total_seconds() == pytest.approx(3.0)
    url, params = calls[0]
    assert url == "https://api.massive.com/v3/quotes/BRK.B" and params["timestamp.lte"] == int(now.timestamp() * 1e9)
    nbbo("BRK-B", now)  # the universe carries EODHD's spelling: Massive's is asked
    assert calls[1][0] == "https://api.massive.com/v3/quotes/BRK.B"
    assert params["order"] == "desc" and params["sort"] == "timestamp" and params["limit"] == 1 and params["apiKey"] == "tok"

    clock, tries = {"t": 100.0}, []

    def broken(url, params=None):
        tries.append(clock["t"])
        raise RuntimeError("timeout for apiKey=tok")
    failing = engine_module.massive_nbbo(broken, "https://api.massive.com", "tok", monotonic=lambda: clock["t"])
    # the owner's instruction (30/10, Codex 6524471382): 3 failures in a row pause Massive for 5 s (until 30/10 one failure
    # paused it 30 s)
    assert failing("AAA", now) is None and failing("AAA", now) is None and tries == [100.0, 100.0]
    assert failing("AAA", now) is None and tries == [100.0] * 3
    clock["t"] = 104.9
    assert failing("AAA", now) is None and tries == [100.0] * 3  # paused: the stream stands in
    clock["t"] = 105.1
    assert failing("AAA", now) is None and tries == [100.0] * 3 + [105.1]
    script, seen = [RuntimeError("a"), RuntimeError("b"), {"results": []}, RuntimeError("c"), RuntimeError("d")], []

    def flaky(url, params=None):
        item = script[len(seen)]
        seen.append(clock["t"])
        if isinstance(item, Exception):
            raise item
        return item
    reader = engine_module.massive_nbbo(flaky, "https://x", "t", monotonic=lambda: clock["t"])
    clock["t"] = 200.0
    assert all(reader("AAA", now) is None for _ in range(5)) and len(seen) == 5  # an answer resets the count: never paused
    for payload in ({}, {"results": []}, {"results": [{"bid_price": 0, "ask_price": 1, "sip_timestamp": 1}]},
                    {"results": [{"bid_price": 2, "ask_price": 1, "sip_timestamp": 1}]}, ["not", "a", "dict"]):
        assert engine_module.massive_nbbo(lambda url, params=None, p=payload: p, "https://x", "t")("AAA", now) is None


def test_nbbo_massive_time_per_minute_is_bounded_and_the_stream_stands_in_past_it(monkeypatch) -> None:
    import threading
    import time as wall

    monkeypatch.setattr(engine_module, "NBBO_STEP_BUDGET_SECONDS", 0.5)
    engine = _engine()
    engine.candidates.update({"DDD": -2.0, "EEE": -2.0})
    engine.members.update({s: Member(s, "NYSE", 50.0, 20e6) for s in ("DDD", "EEE")})
    t = _at(9, 40)
    below = {s: _view(97.9, 98.0, 97.89, 97.91, t) for s in ("AAA", "CCC", "DDD", "EEE")}
    engine.step(t, lambda s: below.get(s, MarketView()))
    t = _at(9, 41)
    above = {s: _view(98.1, 98.0, 98.095, 98.105, t) for s in ("AAA", "CCC", "DDD", "EEE")}
    release = threading.Event()

    def nbbo(symbol, now):  # DDD's answer never comes within the minute's budget; the others answer at once
        if symbol == "DDD":
            release.wait(10)
        return (98.095, 98.105, now)
    began = wall.monotonic()
    fills = engine.step(t, lambda s: above.get(s, MarketView()), nbbo=nbbo)
    waited = wall.monotonic() - began
    release.set()
    # the step waits for Massive at most the budget (Codex 6478311166 P2-1): the straggler is never waited for and the
    # stream's quote stands in for it; the others were asked at the same time and answered
    assert 0.5 <= waited < 1.5 and len(fills) == 4
    assert engine.sources == {"massive": 3, "stream": 1, "unanswered": 1, "mismatch": 0, "stream_would_refuse": 0}
    assert all(0.5 <= (datetime.fromisoformat(f["executed_at"]) - t).total_seconds() < 1.5 for f in fills)  # the effective instant


def test_nbbo_every_cross_of_the_minute_is_asked_at_once() -> None:
    """29/10 open: asked one after the other (~0.7 s each), a 3 s budget answered ~3 of ~13 crosses a minute (36 of 156
    by 10:43 BRT) and the rest fell back to the stream's late quote. Asked at once, all of them answer inside the budget."""
    import threading
    import time as wall

    symbols = ["S%02d" % i for i in range(13)]
    engine = Engine(EngineState(nav_realized=1_000_000.0), DAY, [Member(s, "NYSE", 100.0, 50e6) for s in symbols])
    engine.set_candidates({s: 98.0 for s in symbols})
    t = _at(9, 40)
    engine.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t))
    t = _at(9, 41)
    lock, active, peak, asked = threading.Lock(), [0], [0], []

    def nbbo(symbol, now):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            asked.append((symbol, now))
        wall.sleep(0.7)
        with lock:
            active[0] -= 1
        return (98.095, 98.105, now - timedelta(seconds=1))
    began = wall.monotonic()
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.0, 98.2, t), nbbo=nbbo)  # the stream's own quote: 20 bps
    waited = wall.monotonic() - began
    assert sorted(s for s, _ in asked) == symbols and peak[0] == 13 and waited < 2.0  # one after the other: 9.1 s
    assert len(fills) == 13 and all("NBBO Massive" in f["reason"] for f in fills)
    assert engine.sources == {"massive": 13, "stream": 0, "unanswered": 0, "mismatch": 0, "stream_would_refuse": 13}
    assert all(0 <= (at - t).total_seconds() < 1 for _, at in asked)  # each asked at the effective instant of the asking


def test_nbbo_a_reader_that_raises_is_no_answer_and_the_budget_counts_from_the_first_asking(monkeypatch) -> None:
    import time as wall

    monkeypatch.setattr(engine_module, "NBBO_STEP_BUDGET_SECONDS", 0.4)
    starts: list[float] = []

    def nbbo(symbol, now):
        starts.append(wall.monotonic())
        if symbol == "B":
            raise RuntimeError("no answer")
        if symbol == "C":
            wall.sleep(2.0)  # never waited for
        return (10.0, 10.01, now)
    began = wall.monotonic()
    answers = engine_module.ask_nbbo(nbbo, ["A", "B", "C"], _at(9, 41))
    waited = wall.monotonic() - began
    assert set(answers) == {"A"} and waited < 0.4 + 0.15  # the budget runs from the first asking, not after every start


@pytest.mark.parametrize("case", ["last_entry", "massive_age", "stream_age"])
def test_nbbo_the_effective_instant_is_sampled_after_the_buys_quote_read(monkeypatch, case: str) -> None:
    """Codex 6499564395 P2: the buy's own quote read (the stream's lock) waits 2 s; the last entry and the quote's age
    are judged, and the fill stamped, on the instant AFTER that wait. Each control without the wait buys."""
    clock = {"t": 0.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: clock["t"])
    start = {"last_entry": _at(15, 59, 58), "massive_age": _at(10, 0, 0), "stream_age": _at(10, 0, 0)}[case]

    def attempt(wait: float) -> tuple[list[dict], Engine]:
        clock["t"] = 0.0
        engine = _engine()
        below_at = start - timedelta(seconds=60)
        engine.step(below_at, lambda s: _view(97.9, 98.0, 97.89, 97.91, below_at) if s == "AAA" else MarketView())
        stream_at = start - timedelta(seconds=4) if case == "stream_age" else start
        reads = {"AAA": 0}

        def view(symbol):
            if symbol != "AAA":
                return MarketView()
            reads["AAA"] += 1
            if reads["AAA"] == 2:  # the buy's own read of the quote
                clock["t"] += wait
            return _view(98.1, 98.0, 98.095, 98.105, stream_at)
        if case == "stream_age":
            nbbo = lambda s, now: None  # noqa: E731 — Massive silent: the stream's quote (5 s bound) stands in
        else:
            age = 59 if case == "massive_age" else 0
            nbbo = lambda s, now: (98.095, 98.105, start - timedelta(seconds=age))  # noqa: E731
        return engine.step(start, view, nbbo=nbbo), engine

    fills, engine = attempt(2.0)
    assert fills == [] and not engine.state.positions
    assert (engine.skips["late"], engine.skips["stale"]) == ((1, 0) if case == "last_entry" else (0, 1))
    fills, engine = attempt(0.0)
    assert [f["symbol"] for f in fills] == ["AAA"] and fills[0]["executed_at"] == start.isoformat()


@pytest.mark.parametrize("case", ["stale_quote", "t30_positive"])
def test_the_exits_instant_is_sampled_after_their_quote_read(monkeypatch, case: str) -> None:
    """As the entries (Codex 6499564395): the exit's own quote read waits 2 s; freshness and the T30 rule are judged,
    and the sell stamped, on the instant after that wait."""
    clock = {"t": 0.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: clock["t"])
    t = _at(10, 5) if case == "stale_quote" else _at(15, 59, 29)

    def attempt(wait: float) -> list[dict]:
        clock["t"] = 0.0
        engine = _engine()
        engine.step(_at(9, 59), lambda s: _view(97.9, 98.0, 97.89, 97.91, _at(9, 59)) if s == "AAA" else MarketView())
        bought = engine.step(_at(10, 0), lambda s: _view(98.1, 98.0, 98.095, 98.105, _at(10, 0)) if s == "AAA" else MarketView())
        assert [f["symbol"] for f in bought] == ["AAA"]

        def view(symbol):
            if symbol != "AAA":
                return MarketView()
            clock["t"] += wait
            if case == "stale_quote":  # 4 s old at t, below the stop
                return _view(97.5, 98.0, 97.5, 97.51, t - timedelta(seconds=4))
            return _view(98.2, 98.0, 98.2, 98.21, t)  # fresh, ~+0.09% net: positive, never armed
        return engine.step(t, view)

    waited, control = attempt(2.0), attempt(0.0)
    if case == "stale_quote":  # 6 s old at the decision: neither marked nor sold; the control sells at t
        assert waited == [] and [(f["side"], f["executed_at"]) for f in control] == [("SELL", t.isoformat())]
    else:  # 15:59:31 at the decision is past 15:59:30: sold, stamped at the decision; the control at 15:59:29 is not
        assert [(f["side"], f["executed_at"]) for f in waited] == [("SELL", (t + timedelta(seconds=2)).isoformat())]
        assert control == []


def test_nbbo_with_every_slot_taken_massive_is_not_asked() -> None:
    engine = _crossing_engine()
    engine.state.positions.update({"P%02d" % i: object() for i in range(engine_module.RULE["slots"])})  # type: ignore[misc]
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.0, 29.005, t)}
    asked = []
    assert engine.step(t, lambda s: views.get(s, MarketView()), nbbo=lambda s, now: asked.append(s)) == []
    # the held names are marked on Massive (the exits); no candidate is asked with every slot taken
    assert sorted(asked) == sorted(engine.state.positions) and engine.skips["slots"] == 2


def test_nbbo_the_session_hands_the_reader_to_every_step_and_the_request_lines_stay_out_of_the_logs(tmp_path: Path, monkeypatch) -> None:
    import logging

    engine_module.quiet_request_logs()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6))
    clock = {"t": _at(9, 30, 30)}
    stream = _FakeStream()
    received = []
    original = Engine.step

    def spy(self, now, view, signal=None, nbbo=None, pushed=None, between=None):
        received.append(nbbo)
        return original(self, now, view, signal, nbbo)
    monkeypatch.setattr(Engine, "step", spy)

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        stream.views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, clock["t"])}  # type: ignore[attr-defined]
        if clock["t"] >= _at(9, 33):
            raise KeyboardInterrupt
    reader = lambda symbol, now: None
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY,  # type: ignore[arg-type]
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=reader)
    assert received and all(r is reader for r in received)


def test_nbbo_an_answer_after_the_last_entry_buys_nothing_and_the_execution_time_is_the_effective_one(monkeypatch) -> None:
    """Codex 6478311166 P2-2: asked at 15:59:59, answered 1.49 s later (16:00:00.49): past the last entry, no buy."""
    clock = {"t": 0.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: clock["t"])
    engine = _engine()
    t = _at(15, 58, 59)
    below = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}
    engine.step(t, lambda s: below.get(s, MarketView()))
    t = _at(15, 59, 59)
    above = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.0, 29.005, t)}
    quotes = {"AAA": (98.095, 98.105), "CCC": (29.0, 29.005)}

    def slow(symbol, now):  # asked at once, both answered 1.49 s after the asking
        clock["t"] = max(clock["t"], 1.49)
        return (*quotes[symbol], now)
    assert engine.step(t, lambda s: above.get(s, MarketView()), nbbo=slow) == []
    assert not engine.state.positions and engine.skips["late"] == 1 and engine.fills == []
    clock["t"] = 0.0  # the control: asked at 15:59:57, answered inside the window, executed at the effective instant
    engine = _engine()
    engine.step(_at(15, 58, 57), lambda s: below.get(s, MarketView()))
    fills = engine.step(_at(15, 59, 57), lambda s: above.get(s, MarketView()), nbbo=slow)
    assert [f["symbol"] for f in fills] == ["AAA", "CCC"] and engine.skips["late"] == 0
    assert all(f["executed_at"] == (_at(15, 59, 57) + timedelta(seconds=1.49)).isoformat() for f in fills)


@pytest.mark.parametrize("row", [
    {"bid_price": 1e309, "ask_price": 1e309, "sip_timestamp": 1},  # inf
    {"bid_price": 98.0, "ask_price": float("nan"), "sip_timestamp": 1},
    {"bid_price": 98.0, "ask_price": 98.01, "sip_timestamp": 253402300800000000000},  # year 10000
    {"bid_price": 98.0, "ask_price": 98.01, "sip_timestamp": 10 ** 40},  # overflow
    {"bid_price": 98.0, "ask_price": 98.01, "sip_timestamp": "x"},
    {"bid_price": 98.0, "ask_price": 98.01, "sip_timestamp": 1},  # 1970: not the instant's NBBO
])
def test_nbbo_an_answer_that_is_no_usable_nbbo_is_refused_whole_and_the_stream_stands_in(row) -> None:
    """Codex 6478311166 P2-3: refused inside the reader's boundary, before any state; the healthy stream buys."""
    now = _at(9, 41)
    reader = engine_module.massive_nbbo(lambda url, params=None: {"results": [dict(row)]}, "https://x", "t")
    assert reader("AAA", now) is None
    engine = _crossing_engine()
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, now), "CCC": _view(28.9, 29.0, 28.80, 29.00, now)}
    fills = engine.step(now, lambda s: views.get(s, MarketView()), nbbo=reader)
    assert [(f["symbol"], f["price"]) for f in fills] == [("AAA", 98.105)] and "cotação do stream" in fills[0]["reason"]
    assert all(math.isfinite(v) for v in (fills[0]["quantity"], fills[0]["fees_usd"]))


def test_nbbo_the_streams_own_records_reject_non_finite_numbers() -> None:
    stream = LiveEngineStream("x", max_symbols=550)
    stream.start_session(DAY)
    stamp = int(_at(10, 0).timestamp() * 1000)
    stream._record_quote('{"s": "AAA", "bp": 98.0, "ap": Infinity, "t": %d}' % stamp)
    stream._record_quote('{"s": "AAA", "bp": NaN, "ap": 98.01, "t": %d}' % stamp)
    stream._record('{"s": "AAA", "p": Infinity, "v": 10, "t": %d, "ms": "open"}' % stamp)
    assert "AAA" not in stream.nbbo and stream.view("AAA").price is None


def test_nbbo_a_finite_but_absurd_or_foreign_quote_is_never_bought_on() -> None:
    """Pre-review of e8ce1f3: bid = ask = 2e6 (or another instrument's NBBO) passes finiteness and spread; its mid is far
    from the signal's own close, so Massive's answer is refused and the healthy stream stands in; an absurd stream quote
    is skipped, state untouched."""
    now = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, now), "CCC": _view(28.9, 29.0, 28.80, 29.00, now)}
    for answer in ((2e6, 2e6, now), (196.0, 196.01, now)):  # absurd; another class of the name at twice the price
        engine = _crossing_engine()
        fills = engine.step(now, lambda s: views.get(s, MarketView()), nbbo=lambda s, t, a=answer: a)
        assert [(f["symbol"], f["price"]) for f in fills] == [("AAA", 98.105)] and "cotação do stream" in fills[0]["reason"]
        assert engine.sources["mismatch"] == 1 and engine.sources["massive"] == 0
    engine = _crossing_engine()
    absurd = {"AAA": _view(98.1, 98.0, 2e6, 2e6, now)}
    assert engine.step(now, lambda s: absurd.get(s, MarketView())) == []
    assert engine.skips["implausible"] == 1 and not engine.state.positions and engine.fills == []


def test_nbbo_a_stream_message_stamped_in_the_future_never_pins_the_book() -> None:
    stream = LiveEngineStream("x", max_symbols=550)
    stream.start_session(datetime.now(NEW_YORK).date())
    ahead = int((datetime.now(timezone.utc) + timedelta(hours=3)).timestamp() * 1000)
    stream._record_quote(json.dumps({"s": "AAA", "bp": 98.0, "ap": 98.01, "t": ahead}))
    assert "AAA" not in stream.nbbo
    stream._record(json.dumps({"s": "AAA", "p": 98.0, "v": 10, "t": ahead, "ms": "open"}))
    assert stream.view("AAA").price is None



def test_massive_stream_hands_the_followed_names_trades_to_the_sink_and_drops_off_exchange_prints() -> None:
    """Owner 30/10 ("passar também os negócios para o stream da Massive"): a trade of a followed name reaches the
    engine's tapes in the engine's spelling, at its SIP time; a print reported to a FINRA facility (TRF id or exchange
    4: off-exchange, as EODHD's dark-pool flag) never does, nor a name not followed, a bad price or a stamp ahead."""
    received: list[tuple] = []
    stream = engine_module.MassiveQuoteStream("key", trade_sink=lambda *trade: received.append(trade))
    stream.set_trade_symbols({"AAA", "BRK-B"})
    now_ms = int(_at(10, 0).timestamp() * 1000)  # a session instant (in the past: never ahead of the clock)
    ahead_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + 60_000
    frame = [{"ev": "T", "sym": "AAA", "x": 11, "p": 98.1, "s": 100, "t": now_ms},
             {"ev": "T", "sym": "BRK.B", "x": 4, "trfi": 202, "p": 400.0, "s": 50, "t": now_ms},
             {"ev": "T", "sym": "AAA", "x": 4, "p": 98.2, "s": 10, "t": now_ms},
             {"ev": "T", "sym": "BRK.B", "x": 12, "p": 400.5, "s": 5, "t": now_ms},
             {"ev": "T", "sym": "CCC", "x": 11, "p": 10.0, "s": 1, "t": now_ms},
             {"ev": "T", "sym": "AAA", "x": 11, "p": 98.3, "s": 1, "t": ahead_ms},
             {"ev": "T", "sym": "AAA", "x": 11, "p": -1, "s": 1, "t": now_ms},
             {"ev": "T", "sym": "AAA", "x": 11, "p": 98.4, "s": 1, "t": now_ms, "c": [12]},  # a Form T print
             {"ev": "Q", "sym": "AAA", "bp": 98.0, "ap": 98.02, "t": now_ms}]
    after_close = int(datetime.combine(date(2026, 10, 28), time(16, 0, 1), tzinfo=NEW_YORK).timestamp() * 1000)
    frame.append({"ev": "T", "sym": "AAA", "x": 11, "p": 98.5, "s": 1, "t": after_close})  # at or after the close
    stream._record(json.dumps(frame))
    assert [(symbol, price, size) for symbol, price, size, _ in received] == [("AAA", 98.1, 100.0), ("BRK-B", 400.5, 5.0)]
    assert all(at.tzinfo is not None and abs(at.timestamp() * 1000 - now_ms) < 1 for *_, at in received)
    names, trades, _, _, off_exchange, extended, failures = stream.take_trade_gauges()
    assert (names, trades, off_exchange, extended, failures) == (2, 2, 2, 2, 0) and stream.take_trade_gauges()[1] == 0
    quiet = engine_module.MassiveQuoteStream("key")  # without a sink: nothing subscribed
    quiet.set_trade_symbols({"AAA"})
    assert quiet._trade_symbols == frozenset() and not quiet.feeds_trades

    def broken(*trade):
        raise RuntimeError("a bad trade")
    fragile = engine_module.MassiveQuoteStream("key", trade_sink=broken)
    fragile.set_symbols({"AAA"})
    fragile.set_trade_symbols({"AAA"})
    fragile._record(json.dumps([{"ev": "T", "sym": "AAA", "x": 11, "p": 98.1, "s": 1, "t": now_ms},
                                {"ev": "Q", "sym": "AAA", "bp": 98.0, "ap": 98.02, "t": now_ms}]))
    assert fragile._quotes["AAA"][0] == 98.0 and fragile.take_trade_gauges()[6] == 1  # counted; the quote is kept
    fragile.set_trade_sink(None)
    assert fragile._trade_symbols == frozenset() and not fragile.feeds_trades


def test_massive_stream_subscribes_the_quotes_and_the_trades_in_batches(monkeypatch) -> None:
    import asyncio

    stream = engine_module.MassiveQuoteStream("key", trade_sink=lambda *trade: None)
    stream.set_symbols({"AAA"})
    names = {"N%03d" % i for i in range(450)}
    stream.set_trade_symbols(names | {"BRK-B"})
    sent: list[dict] = []

    class Socket:
        def __init__(self) -> None:
            self.messages = [json.dumps([{"ev": "status", "status": "connected"}]),
                             json.dumps([{"ev": "status", "status": "auth_success"}])]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, text: str) -> None:
            sent.append(json.loads(text))

        async def recv(self) -> str:
            if self.messages:
                return self.messages.pop(0)
            stream._stop.set()
            raise TimeoutError

    monkeypatch.setattr(engine_module.websockets, "connect", lambda url, **kwargs: Socket())
    asyncio.run(stream._run())
    frames = [frame for frame in sent if frame["action"] == "subscribe"]
    channels = [channel for frame in frames for channel in frame["params"].split(",")]
    assert all(len(frame["params"].split(",")) <= engine_module.MASSIVE_SUBSCRIBE_BATCH for frame in frames)
    assert sorted(channels) == sorted({"Q.AAA", "T.BRK.B"} | {"T." + name for name in names})


class _MassiveFake:
    status, reconnects = "connected", 0

    def __init__(self, feeds: bool = False) -> None:
        self.trade_history: list[list[str]] = []
        self.sinks: list[object] = []
        self.feeds_trades = feeds

    def set_trade_sink(self, sink) -> None:
        self.sinks.append(sink)

    def set_symbols(self, symbols) -> None:
        return None

    def set_trade_symbols(self, symbols) -> None:
        self.trade_history.append(list(symbols))

    def quote(self, symbol):
        return None

    def wait_update(self, timeout: float) -> bool:
        return False

    def take_gauges(self):
        return 0, 0, 0, 0

    def take_trade_gauges(self):
        return 0, 0, 0, 0, 0, 0, 0


@pytest.mark.parametrize("source, shadow", [("massive", False), ("eodhd", True), ("eodhd", False)])
def test_the_trade_source_feeds_the_signal_from_one_feed_only(tmp_path: Path, monkeypatch, source: str, shadow: bool) -> None:
    """EODHD's group is the same in every mode (its quote feed is the exits' last resort, pre-review of 4e193651 P0).
    With the Massive source Massive follows the universe and then the candidates and EODHD's trades are not recorded; in
    the shadow (EODHD in force) Massive's trades of the same names go to a separate set of tapes; else nothing changes."""
    monkeypatch.setattr(engine_module, "TRADE_SOURCE", source)
    monkeypatch.setattr(engine_module, "TRADE_SHADOW", shadow)
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe",
                        lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6), Member("BBB", "NYSE", 50.0, 20e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1e6))
    clock = {"t": _at(9, 30, 30)}
    stream = _QuoteFakeStream()
    stream.feed_trades = True
    massive = _MassiveFake(feeds=source == "massive")

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        stream.views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, clock["t"])}  # below the VWAP: no buy, nothing held
        if clock["t"] >= _at(9, 32):
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                    now=lambda: clock["t"], sleep=sleep, massive=massive)  # type: ignore[arg-type]
    assert stream.subscribed_history[0] == ["AAA", "BBB"] and stream.subscribed_history[-1] == ["AAA"]  # every mode
    assert stream.feed_trades is (source != "massive")
    if source == "massive" or shadow:
        assert massive.trade_history[0] == ["AAA", "BBB"] and massive.trade_history[-1] == ["AAA"]
    else:
        assert massive.trade_history == []
    assert (len(massive.sinks) == 1 and isinstance(getattr(massive.sinks[0], "__self__", None), LiveEngineStream)) is shadow


def test_the_quote_feed_keeps_the_held_names_whatever_the_trade_source() -> None:
    """Pre-review of 4e193651 P0, with the real stream: EODHD's quote feed is the grouped names among the held ones, and
    stays so when its trades are not recorded (TRADE_SOURCE "massive")."""
    stream = LiveEngineStream("", max_symbols=10)
    stream.start_session(DAY)
    stream.set_group(engine_module.STREAM_GROUP, ["AAA", "HLD"], priority=200)
    stream.set_quote_symbols({"HLD"})
    stream.feed_trades = False
    assert stream.feed_symbols("quote") == {"HLD"} and stream.feed_symbols("trade") == {"AAA", "HLD"}
    stamp = int(_at(10, 0).timestamp() * 1000)
    stream._record(json.dumps({"s": "AAA", "p": 98.0, "v": 10, "t": stamp}))
    assert "AAA" not in stream.tapes  # the trade is not recorded twice: Massive feeds the tapes
    stream.feed_trades = True
    stream._record(json.dumps({"s": "AAA", "p": 98.0, "v": 10, "t": stamp}))
    assert stream.tapes["AAA"].last_price == 98.0


def test_the_shadow_line_compares_massives_tape_with_eodhds() -> None:
    mine, theirs = LiveEngineStream(""), LiveEngineStream("")
    for tapes in (mine, theirs):
        tapes.start_session(DAY)
    mine.record_trade("AAA", 100.0, 100, _at(9, 30, 1))
    mine.record_trade("AAA", 101.0, 100, _at(9, 40))
    theirs.record_trade("AAA", 100.0, 100, _at(9, 30, 1))
    theirs.record_trade("AAA", 101.1, 100, _at(9, 40))
    mine.record_trade("BBB", 50.0, 10, _at(9, 30, 2))  # only in EODHD's: not compared
    line = engine_module.shadow_trades_line(mine, theirs, ["AAA", "BBB"])
    assert line.startswith("R2D2 live shadow trades: names=2 both=1 ") and line.endswith(" open_agree=1")
    assert "last_bps_p50=9.9" in line  # 101.1 against 101.0


def test_the_massive_trade_path_keeps_up_with_an_opening_burst() -> None:
    """Owner 30/10: "esse fluxo de 900 papéis é bem maior, então precisa de um teste de volume antes" — 200,000 trades of
    900 names, in frames of 100 as the socket delivers them, through the stream's handler into the engine's tapes. The
    lab measured 3,096 trades/s for 900 names on 30/10, 5,984 in the busiest second: the path must take five times that."""
    from time import perf_counter

    tapes = LiveEngineStream("", max_symbols=1000)
    tapes.start_session(DAY)
    names = ["N%03d" % i for i in range(900)]
    stream = engine_module.MassiveQuoteStream("key", trade_sink=tapes.record_trade)
    stream.set_trade_symbols(names)
    base = int(_at(10, 0).timestamp() * 1000)
    frames = [json.dumps([{"ev": "T", "sym": names[(f * 100 + i) % 900], "x": 11, "p": 50.0 + (i % 7) * 0.01, "s": 100,
                           "t": base + f} for i in range(100)]) for f in range(2000)]
    started = perf_counter()
    for frame in frames:
        stream._record(frame)
    rate = 200_000 / (perf_counter() - started)
    print("massive trade path: %.0f trades/s" % rate)
    assert stream.take_trade_gauges()[1] == 200_000
    assert all(tapes.tapes[name].volume > 0 for name in names)
    assert rate > 5 * 5_984


def test_the_shared_massive_path_keeps_the_exits_served_under_an_opening_load() -> None:
    """Codex 6537835879: the REAL run_session (full step, fast passes, commits) with the shadow on the REAL reader loop —
    trades and quotes mixed in a short opening burst then a regular rate, ten quotes crossing a stop: no trade or frame
    lost, no reconnect, every crossing sold and every pushed quote read, within the harness's own criteria (the full
    profile is ``python -m app.r2d2_massive_load``)."""
    from app import r2d2_massive_load

    result = r2d2_massive_load.run(0, 0, 40_000, 3, 6_000, 1, from_open=False)  # from 09:30:59: the exits at once
    assert result["criteria"]["verdict"] == "PASS", result["criteria"]
    assert result["taken"]["subscribed_channels"] >= r2d2_massive_load.CANDIDATES + 2 * len(r2d2_massive_load.HELD)  # T. and Q.


def test_the_owners_sizes_of_31_10_are_the_tiers_and_the_flat_close_stays_off() -> None:
    """Owner 31/10: "2 bps para 5% da posição de cada ação, 3 bps para 4%, 5 bps para 2,5%" (NAV/20 x 1, 0.8, 0.5); "Zerar
    é idiotice" — no flat close. The other size rules stay available."""
    assert engine_module.RULE["close_flat"] is False and engine_module.RULE["size_rule"] == "tiers"
    weight = engine_module.size_weight
    assert [weight(s) for s in (0.5, 2.0, 2.0000001, 2.01, 3.0, 3.01, 4.9, 5.0)] == [1.0, 1.0, 1.0, 0.8, 0.8, 0.5, 0.5, 0.5]
    exact = (100.01 - 99.99) / ((100.01 + 99.99) / 2) * 1e4  # exactly 2 bps, a hair over it in float
    assert exact > 2.0 and weight(exact) == 1.0
    assert weight(4.0, "equal") == 1.0 and weight(0.5, "equal") == 1.0
    assert engine_module.size_weight(5.0, "taper") == pytest.approx(0.4) and engine_module.size_weight(1.0, "taper") == 1.0
    assert engine_module.size_weight(4.0, "inverse") == pytest.approx(0.5) and engine_module.size_weight(1.5, "inverse") == 1.0


def _held_negative(engine: Engine) -> Position:
    t = _at(15, 50, 0)
    engine.step(t - timedelta(seconds=1), lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    assert [f["side"] for f in fills] == ["BUY"]
    return engine.state.positions["AAA"]


@pytest.mark.parametrize("flat", [False, True])
def test_a_flat_close_sells_a_negative_position_from_t30(monkeypatch, flat: bool) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", flat)
    engine = _engine()
    _held_negative(engine)
    t = _at(15, 59, 31)
    bid = 98.0  # about -0.12% net: neither the stop nor the lock
    fills = engine.step(t, lambda s: _view(98.0, 98.0, bid, bid + 0.01, t) if s == "AAA" else MarketView(),
                        pushed=lambda s: (bid, bid + 0.01, t) if s == "AAA" else None)
    sold = [(f["side"], f["reason"].split(",")[0]) for f in fills if f["side"] == "SELL"]
    assert sold == ([("SELL", "venda: zerada no fechamento")] if flat else [])
    assert ("AAA" in engine.state.positions) is not flat


def test_a_flat_close_confirms_the_feeds_bid_with_any_fresh_trade(monkeypatch) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", True)
    engine = _engine()
    _held_negative(engine)
    t = _at(15, 59, 35)
    # the feed only: its bid at -0.11% net, the fresh last trade elsewhere (-0.05%): any fresh trade confirms the flat sale
    fills = engine.step(t, lambda s: _view(98.06, 98.0, 98.0, 98.01, t) if s == "AAA" else MarketView())
    assert [f["reason"].split(",")[0] for f in fills if f["side"] == "SELL"] == ["venda: zerada no fechamento"]


def test_a_flat_close_never_carries_an_unconfirmed_stop_on_the_feed(monkeypatch) -> None:
    """Pre-review of f3db006c P1: the feed's bid at the stop (-0.5%), the fresh trade at -0.1% — the stop is unconfirmed,
    the window's flat sale still stands on that trade; without the flat close it stays unconfirmed."""
    for flat in (True, False):
        monkeypatch.setitem(engine_module.RULE, "close_flat", flat)
        engine = _engine()
        position = _held_negative(engine)
        bid = position.cost_usd * (1 - 0.5 / 100) / (position.shares * (1 - FEE_SIDE))
        trade = position.cost_usd * (1 - 0.1 / 100) / (position.shares * (1 - FEE_SIDE))  # above the -0.20% stop
        t = _at(15, 59, 35)
        fills = engine.step(t, lambda s: _view(trade, 98.0, bid, bid + 0.01, t) if s == "AAA" else MarketView())
        sold = [f["reason"].split(",")[0] for f in fills if f["side"] == "SELL"]
        assert sold == (["venda: zerada no fechamento"] if flat else []), flat


def test_a_flat_close_cutoff_is_the_instant_before_t30(monkeypatch) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", True)
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: 0.0)
    assert engine_module.FLAT_LAST_ENTRY == time(15, 59, 29, 999999)
    for at, bought in ((_at(15, 59, 29) + timedelta(microseconds=999999), True), (_at(15, 59, 30), False)):
        engine = _engine()
        below_at = at - timedelta(seconds=1)
        engine.step(below_at, lambda s: _view(97.9, 98.0, 97.89, 97.91, below_at) if s == "AAA" else MarketView())
        fills = engine.step(at, lambda s: _view(98.1, 98.0, 98.095, 98.105, at) if s == "AAA" else MarketView())
        assert bool([f for f in fills if f["side"] == "BUY"]) is bought, at


def test_a_flat_close_sells_a_carried_position_and_on_the_fast_pass(monkeypatch) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", True)
    engine = _engine()
    position = _held_negative(engine)
    position.days_held = 1  # a negative carried from an earlier session
    t = _at(15, 59, 31)
    fills = engine.fast_exits(t, lambda s: MarketView(), lambda s: (98.0, 98.01, t) if s == "AAA" else None)
    assert [f["reason"].split(",")[0] for f in fills] == ["venda: zerada no fechamento"]
    assert "pregão(ões) atrás" in fills[0]["reason"] and not engine.state.positions


def test_a_flat_close_carries_nothing_past_the_close(monkeypatch) -> None:
    for flat in (True, False):
        monkeypatch.setitem(engine_module.RULE, "close_flat", flat)
        engine = _engine()
        position = _held_negative(engine)  # no check after 15:59:30 reached it (no usable quote)
        engine.close_session()
        if flat:
            assert not engine.state.positions and engine.fills[-1]["side"] == "SELL"
            assert engine.fills[-1]["price"] == position.last_mark and engine.fills[-1]["executed_at"] == _at(16, 0).isoformat()
        else:
            assert engine.state.positions["AAA"].days_held == 1


def test_the_shadows_follow_the_close_mode_and_the_size(monkeypatch) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", True)
    monkeypatch.setitem(engine_module.RULE, "size_rule", "taper")
    engine = _engine()
    t = _at(15, 59, 0)
    engine._shadow_open("AAA", 98.105, 6.0, t)
    assert engine.state.shadow["AAA"]["size_usd"] == pytest.approx(1_000_000.0 / 20 * engine_module.size_weight(6.0, "taper"))
    late = _at(15, 59, 31)
    engine._shadow_exits(late, lambda s: _view(98.05, 98.0, 98.04, 98.06, late) if s == "AAA" else MarketView())
    assert "AAA" not in engine.state.shadow  # a negative shadow closes in the window under a flat close


def test_an_unknown_size_rule_is_refused() -> None:
    assert engine_module.RULE["size_rule"] in engine_module.SIZE_RULES
    with pytest.raises(ValueError):
        engine_module.size_weight(4.0, "Taper")


@pytest.mark.parametrize(("hour", "minute", "second", "bought"), [(15, 59, 20, True), (15, 59, 40, False)])
def test_a_flat_close_takes_no_entry_in_the_last_30_seconds(monkeypatch, hour, minute, second, bought) -> None:
    monkeypatch.setitem(engine_module.RULE, "close_flat", True)
    engine = _engine()
    t = _at(hour, minute, second)
    engine.step(t - timedelta(seconds=1), lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    assert bool([f for f in fills if f["side"] == "BUY"]) is bought


@pytest.mark.parametrize(("bid", "ask", "cost"), [(98.0855, 98.105, 50_000.0), (98.0775, 98.105, 40_000.0),
                                                 (98.065, 98.105, 25_000.0)])
def test_the_owners_tiers_size_a_buy_by_its_spread(bid: float, ask: float, cost: float) -> None:
    """Owner 31/10: 1.99 bps → 5% of NAV, 2.80 bps → 4%, 4.08 bps → 2.5% (NAV 1 M), each through a real buy."""
    engine = _engine()
    t = _at(10, 0, 0)
    engine.step(t - timedelta(seconds=1), lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, bid, ask, t) if s == "AAA" else MarketView())
    assert [f["side"] for f in fills] == ["BUY"] and engine.state.positions["AAA"].cost_usd == pytest.approx(cost)


@pytest.mark.parametrize("rule", ["taper", "inverse"])
def test_the_size_follows_the_spread_paid(monkeypatch, rule: str) -> None:
    monkeypatch.setitem(engine_module.RULE, "size_rule", rule)
    engine = _engine()
    t = _at(10, 0, 0)
    bid, ask = 98.065, 98.105  # about 4.1 bps
    engine.step(t - timedelta(seconds=1), lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())
    fills = engine.step(t, lambda s: _view(98.1, 98.0, bid, ask, t) if s == "AAA" else MarketView())
    spread = (ask - bid) / ((ask + bid) / 2) * 1e4
    position = engine.state.positions["AAA"]
    assert [f["side"] for f in fills] == ["BUY"]
    assert position.cost_usd == pytest.approx(1_000_000.0 / 20 * engine_module.size_weight(spread, rule))
    assert position.cost_usd < 1_000_000.0 / 20


def test_the_status_shows_the_valuation_snapshots_in_counts_only() -> None:
    database = Database(Settings(database_url=""))
    now = _at(8, 0)
    assert engine_module.status(database, now)["valuation_live"] == {"NASDAQ_UNIVERSE": None, "NYSE_UNIVERSE": None}
    methodology = database.ensure_methodology_version("valuation_ensemble_live", 1, {}, "test")
    outputs = {"complete": True, "records": [{"symbol": "AAPL", "primary_tp": 200.0}],
               "counts": {"population_rows": 900, "with_primary_tp": 400, "pit_tested": 600, "pit_tested_with_primary_tp": 350,
                          "screened_with_primary_tp": 300, "reach": {"reached": 900, "pending": 0}}}
    database.save_analysis_snapshot("valuation_ensemble_live", "NASDAQ_UNIVERSE", methodology, {}, outputs, now - timedelta(hours=3))
    seen = engine_module.status(database, now)["valuation_live"]
    assert seen["NYSE_UNIVERSE"] is None and seen["NASDAQ_UNIVERSE"] == {
        "published_at": (now - timedelta(hours=3)).isoformat(), "age_hours": 3.0, "complete": True, "names_pending": 0,
        "population_rows": 900, "with_primary_tp": 400, "pit_tested": 600, "pit_tested_with_primary_tp": 350,
        "screened_with_primary_tp": 300}
    assert "AAPL" not in json.dumps(seen)


def test_the_status_prints_only_integers_whatever_a_snapshot_holds() -> None:
    database = Database(Settings(database_url=""))
    now = _at(8, 0)
    methodology = database.ensure_methodology_version("valuation_ensemble_live", 1, {}, "test")
    outputs = {"complete": "AAPL", "counts": {"population_rows": "AAPL", "with_primary_tp": ["AAPL"], "pit_tested": True, "reach": {"pending": "AAPL"}}}
    database.save_analysis_snapshot("valuation_ensemble_live", "NYSE_UNIVERSE", methodology, {}, outputs, now - timedelta(hours=1))
    seen = engine_module.valuation_snapshots(database, now)["NYSE_UNIVERSE"]
    assert seen["complete"] is False and seen["names_pending"] is None and seen["population_rows"] is None
    assert seen["with_primary_tp"] is None and seen["pit_tested"] is None and "AAPL" not in json.dumps(seen)


def test_a_failed_valuation_read_never_fails_the_status_and_prints_no_message() -> None:
    class Broken:
        def latest_analysis_snapshot(self, analysis_type, entity):
            raise RuntimeError("AAPL went wrong")

    assert engine_module.valuation_snapshots(Broken(), _at(8, 0)) == {"NASDAQ_UNIVERSE": {"error": "RuntimeError"}, "NYSE_UNIVERSE": {"error": "RuntimeError"}}


def test_the_status_shows_the_producers_last_run_in_a_closed_shape() -> None:
    at = _at(5, 0)

    class Runs:
        def __init__(self, error, status="failed"):
            self.run = {"last_status": status, "started_at": at, "completed_at": at + timedelta(minutes=30), "last_success_at": None,
                        "last_error": error, "metadata": {"secret": "AAPL"}}

        def ingestion_run_health(self, codes):
            assert codes == ["valuation-worker-ensemble-live"]
            return {codes[0]: self.run}

    seen = engine_module.valuation_phase(Runs("LiveEnsembleError: markets_not_published:2"))
    assert seen == {"last_status": "failed", "started_at": at.isoformat(), "completed_at": (at + timedelta(minutes=30)).isoformat(),
                    "last_success_at": None, "last_error": "LiveEnsembleError: markets_not_published:2"}
    assert engine_module.valuation_phase(Runs("LiveEnsembleError: markets_partial:1:names_pending:300"))["last_error"].endswith("names_pending:300")
    assert engine_module.valuation_phase(Runs("ValueError: AAPL has no price"))["last_error"] == "ValueError"  # never the message
    assert engine_module.valuation_phase(Runs("AAPL broke: at 3"))["last_error"] == "other"
    assert engine_module.valuation_phase(Runs("AAPL: broke"))["last_error"] == "other"  # a ticker never passes for a class
    assert engine_module.valuation_phase(Runs("AAPL"))["last_error"] == "other"
    assert engine_module.valuation_phase(Runs("orphaned: the worker restarted"))["last_error"] == "orphaned"
    assert engine_module.valuation_phase(Runs("QueryCanceled: canceling statement"))["last_error"] == "QueryCanceled"
    assert engine_module.valuation_phase(Runs("no colon AAPL here"))["last_error"] == "other"
    assert engine_module.valuation_phase(Runs(None, "succeeded")) == {"last_status": "succeeded", "started_at": at.isoformat(),
                                                                      "completed_at": (at + timedelta(minutes=30)).isoformat(),
                                                                      "last_success_at": None, "last_error": None}
    assert "AAPL" not in json.dumps([engine_module.valuation_phase(Runs(text)) for text in ("ValueError: AAPL", "no colon AAPL here")])


def test_a_failed_phase_read_never_fails_the_status() -> None:
    class Broken:
        def ingestion_run_health(self, codes):
            raise RuntimeError("AAPL went wrong")

    assert engine_module.valuation_phase(Broken()) == {"error": "RuntimeError"}
    empty = engine_module.valuation_phase(Database(Settings(database_url="")))
    assert empty == {"last_status": None, "started_at": None, "completed_at": None, "last_success_at": None, "last_error": None}


def test_the_status_workflow_prints_the_workers_count_only_line_and_no_other() -> None:
    import re
    import yaml

    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    assert 'logs --no-color --since 30h --tail 20000 valuation-worker' in run
    pattern = run.split('printf \'%s\\n\' "$worker" | grep -oE "', 1)[1].split('" | tail', 1)[0]
    line = "Valuation ensemble live: pending=2 published=0 partial=0 names=0 with_primary_tp=0 names_pending=0 failures={'deadline_reached': 1, 'market_setup:ValueError': 2}"
    assert re.search(pattern, "c3po-valuation-worker-1  | INFO " + line).group(0) == line
    assert re.search(pattern, line.replace("deadline_reached", "AAPL")) is None
    assert re.search(pattern, line.replace("deadline_reached", "section:AAPL")) is None
    for key in ("section:publication_not_after_T", "price_vintage:NotEvaluable", "section:QueryCanceled"):  # a key of the code stays
        assert re.search(pattern, line.replace("deadline_reached", key))
    assert re.search(pattern, line + " AAPL") is None


# ------------------------------------------------------------------ the Valuation's buy permission (owner 31/10, on the PASS)
def _targeted(targets) -> Engine:
    universe = [Member("AAA", "NASDAQ", 100.0, 50e6), Member("CCC", "NYSE", 30.0, 20e6)]
    engine = Engine(EngineState(nav_realized=1_000_000.0), DAY, universe, targets=targets)
    engine.set_candidates({"AAA": 98.0, "CCC": 29.0})
    t = _at(9, 40)
    views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.89, 28.91, t)}
    engine.step(t, lambda s: views.get(s, MarketView()))  # both below the VWAP: armed for a cross
    return engine


def _cross(engine: Engine) -> list[dict]:
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.095, 29.105, t)}  # ~1 and ~3.4 bps
    return engine.step(t, lambda s: views.get(s, MarketView()))


def test_the_valuation_buys_only_with_the_target_at_least_ten_percent_above_the_ask() -> None:
    """Owner 31/10, on the grid's PASS: "ele so entra com upside minimo de 10%". The minimum includes 10%, measured on the ask
    actually paid; under it the signal is refused and followed in paper (the rule without the filter, beside it)."""
    ask = 98.105
    engine = _targeted({"AAA": ask * 1.10, "CCC": 29.105 * 1.0999})
    fills = _cross(engine)
    assert [(f["side"], f["symbol"]) for f in fills] == [("BUY", "AAA")] and set(engine.state.shadow) == {"V:CCC"}
    assert engine.state.shadow["V:CCC"]["band"] == "val_lt10" and engine.state.bands["val_lt10"]["vetoed"] == 1
    assert engine.signals == 2 and "val_none" not in engine.state.bands


def test_a_name_without_a_target_is_not_bought_and_no_targets_buy_nothing() -> None:
    engine = _targeted({"AAA": 500.0})
    assert [f["symbol"] for f in _cross(engine)] == ["AAA"] and engine.state.shadow["V:CCC"]["band"] == "val_none"
    empty = _targeted({})  # fail closed: no snapshot in force, no buy
    assert _cross(empty) == [] and not empty.state.positions and empty.state.bands["val_none"]["vetoed"] == 2


def test_the_spread_limit_is_judged_before_the_valuation() -> None:
    engine = _targeted({"AAA": 500.0, "CCC": 500.0})
    t = _at(9, 41)
    views = {"AAA": _view(98.1, 98.0, 97.97, 98.03, t), "CCC": _view(29.1, 29.0, 29.095, 29.105, t)}  # AAA ~6 bps
    fills = engine.step(t, lambda s: views.get(s, MarketView()))
    assert [f["symbol"] for f in fills] == ["CCC"] and engine.state.shadow["AAA"]["band"] == "5_8"
    assert "val_lt10" not in engine.state.bands and "val_none" not in engine.state.bands


def test_a_session_started_under_another_rule_keeps_it_on_a_restart() -> None:
    state = EngineState(nav_realized=1_000_000.0, session=DAY.isoformat(), config="TIT-2S5-F20")
    engine = Engine(state, DAY, [Member("AAA", "NASDAQ", 100.0, 50e6)], targets={})
    assert engine.resumed and engine.targets is None  # the old label: no filter for the rest of that session
    fresh = Engine(EngineState(nav_realized=1_000_000.0), DAY, [], targets={})
    assert fresh.state.config == engine_module.CONFIG and fresh.targets == {}


def test_a_later_label_never_drops_the_filter_of_a_session_in_progress(monkeypatch) -> None:
    assert engine_module.CONFIG in engine_module.VALUATION_CONFIGS
    state = EngineState(nav_realized=1_000_000.0, session=DAY.isoformat(), config="TIT-2S5-F20V", targets={"AAA": 200.0})
    monkeypatch.setattr(engine_module, "CONFIG", "TIT-2S5-F21")  # a rule changed during the session
    engine = Engine(state, DAY, [Member("AAA", "NASDAQ", 100.0, 50e6)], targets={"AAA": 1.0})
    assert engine.resumed and engine.targets == {"AAA": 200.0}  # the session's own, the one it started on


def test_the_session_keeps_the_targets_it_started_on_through_a_restart() -> None:
    engine = _targeted({"AAA": 500.0})
    restored = EngineState.from_json(json.loads(json.dumps(engine.state.to_json())))
    assert restored.targets == {"AAA": 500.0}
    resumed = Engine(restored, DAY, [Member("AAA", "NASDAQ", 100.0, 50e6)], targets={"AAA": 1.0, "CCC": 1.0})
    assert resumed.resumed and resumed.targets == {"AAA": 500.0}
    next_day = Engine(restored, DAY + timedelta(days=1), [], targets={"BBB": 7.0})
    assert not next_day.resumed and next_day.targets == {"BBB": 7.0}  # a new session reads its own


def test_the_two_shadow_families_never_suppress_each_other() -> None:
    """A name refused by the spread and, later, by the Valuation (or the reverse) is followed in both: each family measures
    its own rule, and the spread bands stay comparable with the days before the filter."""
    wide = _targeted({})  # the spread first: a 5_8 shadow, then the Valuation's refusal on a tight quote
    t = _at(9, 41)
    wide.step(t, lambda s: _view(98.1, 98.0, 97.97, 98.03, t) if s == "AAA" else MarketView())
    assert wide.state.bands["5_8"]["vetoed"] == 1 and wide.state.shadow["AAA"]["band"] == "5_8"
    t = _at(9, 42)
    wide.step(t, lambda s: _view(97.9, 98.0, 97.89, 97.91, t) if s == "AAA" else MarketView())  # back under the VWAP
    t = _at(9, 43)
    wide.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    key = engine_module.VALUATION_SHADOW_PREFIX + "AAA"
    assert wide.state.shadow[key]["band"] == "val_none" and wide.state.shadow[key]["symbol"] == "AAA" and "AAA" in wide.state.shadow
    tight = _targeted({})  # the reverse order
    t = _at(9, 41)
    tight.step(t, lambda s: _view(98.1, 98.0, 98.095, 98.105, t) if s == "AAA" else MarketView())
    t = _at(9, 42)  # under the VWAP again, but above the first shadow's stop
    tight.step(t, lambda s: _view(98.05, 98.1, 98.04, 98.06, t) if s == "AAA" else MarketView())
    t = _at(9, 43)
    tight.step(t, lambda s: _view(98.2, 98.1, 98.17, 98.23, t) if s == "AAA" else MarketView())  # ~6 bps
    assert set(tight.state.shadow) == {key, "AAA"} and tight.state.shadow["AAA"]["band"] == "5_8"
    # both follow the same name's trades and close by themselves
    down = _at(9, 44)
    tight.step(down, lambda s: MarketView(price=97.5, trade_at=down, vwap=98.0) if s == "AAA" else MarketView())
    assert not tight.state.shadow and tight.state.bands["5_8"]["closed"] == 1 and tight.state.bands["val_none"]["closed"] == 1


def test_a_buy_records_the_upside_it_was_allowed_on() -> None:
    engine = _targeted({"AAA": 98.105 * 1.2})
    assert _cross(engine)[0]["reason"].endswith(", upside Valuation +20.0%")
    assert ", upside" not in _crossed_without_filter()["reason"]


def _crossed_without_filter() -> dict:
    engine = _targeted(None)
    return _cross(engine)[0]


def test_a_session_buys_through_a_real_snapshot_and_a_restart_reads_it_no_more(tmp_path: Path, monkeypatch) -> None:
    """The whole path, ``load_targets`` unpatched: the snapshot in the database, the session's buy, a restart at noon that
    keeps the session's targets though the snapshot went away, the day closed."""
    database = Database(Settings(database_url=""))
    monkeypatch.setattr(engine_module, "build_universe", lambda *a, **k: [Member("AAA", "NASDAQ", 100.0, 50e6),
                                                                         Member("CCC", "NYSE", 30.0, 20e6)])
    monkeypatch.setattr(engine_module, "seed_from_lab_book", lambda db, now: EngineState(nav_realized=1_000_000.0))
    _snapshot(database, "NASDAQ_UNIVERSE", [_row("AAA", 200.0)], _at(6, 0))
    _snapshot(database, "NYSE_UNIVERSE", [_row("BBB", 200.0)], _at(6, 0))
    clock = {"t": _at(9, 30, 30)}

    class Stream(_FakeStream):
        def start_session(self, day):
            self.opening = {"AAA": 98.0, "CCC": 29.0}
    stream = Stream()

    def sleep(seconds):
        clock["t"] += timedelta(seconds=max(seconds, 1.0))
        t = clock["t"]
        if t < _at(9, 40):
            stream.views = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.89, 28.91, t)}
        elif t < _at(15, 59, 30):
            stream.views = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.095, 29.105, t)}
        else:
            stream.views = {"AAA": _view(98.3, 98.0, 98.30, 98.31, t), "CCC": _view(29.1, 29.0, 29.095, 29.105, t)}

    def stop_at_noon(seconds):
        sleep(seconds)
        if clock["t"] >= _at(12, 0):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                    now=lambda: clock["t"], sleep=stop_at_noon)
    stored = engine_module.load_state(database, lambda: None)
    assert list(stored.positions) == ["AAA"] and stored.targets == {"AAA": 200.0, "BBB": 200.0}
    assert stored.bands["val_none"]["vetoed"] == 1 and "V:CCC" in stored.shadow  # CCC crossed, had no target: refused, followed
    database._analysis_snapshots[:] = [row for row in database._analysis_snapshots if row["analysis_type"] != engine_module.VALUATION_TYPE]
    state = run_session(stream=stream, database=database, get_json=None, base_url="", token="", day=DAY, cache_dir=tmp_path,
                        now=lambda: clock["t"], sleep=sleep)
    doc = database.latest_analysis_snapshot("r2d2_lab_live", DAY.isoformat())["outputs"]
    assert doc["config"] == engine_module.CONFIG and [(t["side"], t["symbol"]) for t in doc["trades"]] == [("BUY", "AAA"), ("SELL", "AAA")]
    assert not state.positions and state.last_session == DAY.isoformat()


@pytest.mark.parametrize("snapshot", [
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": None, "outputs": {"records": []}},
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": "2026-10-28T10:00:00+00:00", "outputs": {"records": []}},
    {"inputs": [], "published_at": _at(7, 0), "outputs": {"records": []}},
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": _at(7, 0), "outputs": []},
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": _at(7, 0), "outputs": {"records": 5}},
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": _at(7, 0), "outputs": {"records": ["a row"]}},
    {"inputs": {"schema": engine_module.VALUATION_SCHEMA}, "published_at": _at(7, 0),
     "outputs": {"records": [{"symbol": "AAA", "primary_tp": 10**400, "pit_tested": True, "origin": "ensemble"}]}},
], ids=["no_instant", "a_string_instant", "inputs_a_list", "outputs_a_list", "records_a_number", "a_row_not_a_mapping", "an_overflowing_target"])
def test_a_malformed_snapshot_gives_no_target_and_never_ends_the_session(snapshot, caplog) -> None:
    class Stored:
        def latest_analysis_snapshot(self, analysis_type, entity):
            return snapshot

    assert engine_module.load_targets(Stored(), _at(8, 0)) == {}
    assert "no target" in caplog.text and "nothing is bought this session" in caplog.text


def test_a_fresh_snapshot_without_one_tested_name_is_never_a_silent_day(caplog) -> None:
    database = Database(Settings(database_url=""))
    now = _at(8, 0)
    for entity in engine_module.VALUATION_ENTITIES:
        _snapshot(database, entity, [_row("AAA", 120.0, tested=False)], now - timedelta(hours=1))
    assert engine_module.load_targets(database, now) == {} and "nothing is bought this session" in caplog.text


def test_a_failed_database_read_ends_the_attempt_as_load_state_does() -> None:
    class Broken:
        def latest_analysis_snapshot(self, analysis_type, entity):
            raise RuntimeError("connection lost")

    with pytest.raises(RuntimeError):
        engine_module.load_targets(Broken(), _at(8, 0))


def _snapshot(database, entity, records, published, schema=engine_module.VALUATION_SCHEMA):
    methodology = database.ensure_methodology_version("valuation_ensemble_live", 1, {}, "test")
    database.save_analysis_snapshot(engine_module.VALUATION_TYPE, entity, methodology, {"schema": schema}, {"records": records}, published)


def _row(symbol, tp, *, tested=True, origin="ensemble"):
    return {"symbol": symbol, "primary_tp": tp, "pit_tested": tested, "origin": origin}


def test_the_targets_are_the_tested_names_of_each_exchanges_newest_snapshot() -> None:
    database = Database(Settings(database_url=""))
    now = _at(8, 0)
    _snapshot(database, "NASDAQ_UNIVERSE", [_row("AAA", 1.0)], now - timedelta(days=2))
    _snapshot(database, "NASDAQ_UNIVERSE", [_row("AAA", 120.0), _row("NOTTESTED", 50.0, tested=False), _row("NOTP", None, origin="not_evaluable:x"),
                                            _row("ZERO", 0.0), _row("NAN", float("nan")), _row("BOOL", True), _row(None, 10.0), _row(" ", 10.0)],
              now - timedelta(hours=3))
    _snapshot(database, "NYSE_UNIVERSE", [_row("BRK.B", 500.0), _row("REFUSED", 40.0, origin="not_evaluable:y")], now - timedelta(hours=3))
    assert engine_module.load_targets(database, now) == {"AAA": 120.0, "BRK-B": 500.0}
    assert engine_module.target_key("brk.b ") == "BRK-B" == engine_module.target_key("BRK-B")


@pytest.mark.parametrize("published,schema", [(timedelta(hours=73), engine_module.VALUATION_SCHEMA), (timedelta(hours=1), "ANOTHER")])
def test_an_old_or_foreign_snapshot_gives_its_exchange_no_target(published, schema, caplog) -> None:
    database = Database(Settings(database_url=""))
    now = _at(8, 0)
    _snapshot(database, "NASDAQ_UNIVERSE", [_row("AAA", 120.0)], now - published, schema=schema)
    _snapshot(database, "NYSE_UNIVERSE", [_row("BBB", 120.0)], now - timedelta(hours=1))
    assert engine_module.load_targets(database, now) == {"BBB": 120.0}
    assert "no target there" in caplog.text and "AAA" not in caplog.text
    assert engine_module.load_targets(Database(Settings(database_url="")), now) == {}  # no snapshot at all


def test_the_valuation_constants_are_the_live_producers() -> None:
    from app import valuation_live_ensemble as live

    assert engine_module.VALUATION_TYPE == live.ANALYSIS_TYPE and engine_module.VALUATION_SCHEMA == live.SCHEMA
    assert engine_module.VALUATION_ENTITIES == tuple(f"{market}_UNIVERSE" for market in sorted(live.MARKETS))


def test_the_valuation_line_carries_numbers_only_and_the_status_workflow_prints_it() -> None:
    engine = _targeted({"AAA": 500.0})
    _cross(engine)
    line = engine_module.valuation_line(engine)
    assert line == ("R2D2 live valuation: min_upside_pct=10.0 targets=1 candidates_covered=1 of=2 val_lt10 vetoed=0 closed=0 open=0 "
                    "wins=0 net_usd=0.00 val_none vetoed=1 closed=0 open=1 wins=0 net_usd=0.00")
    import re
    import yaml

    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    pattern = run.split('grep -oE "', 1)[1].split('" | tail', 1)[0]
    assert re.search(pattern, "r2d2-live-1  | 2026-11-03 10:00:00 INFO app.r2d2_live_engine " + line)


def test_the_shadows_of_the_filter_follow_the_exits_and_keep_their_band() -> None:
    engine = _targeted({"AAA": 99.0, "CCC": 500.0})  # AAA's target 0.9% above the ask: refused
    _cross(engine)
    row = engine.state.shadow["V:AAA"]
    assert row["band"] == "val_lt10" and row["symbol"] == "AAA" and abs(row["size_usd"] - 50_000.0) < 1e-6  # the tier its spread paid
    half = row["spread_bps"] / 2 / 1e4
    price_at = lambda net: row["ask"] * (1 + FEE_SIDE) * (1 + net / 100) / ((1 - FEE_SIDE) * (1 - half))  # noqa: E731
    down = _at(9, 42)
    engine.step(down, lambda s: MarketView(price=price_at(-0.25), trade_at=down, vwap=98.0) if s == "AAA" else MarketView())
    stats = engine.state.bands["val_lt10"]
    assert "V:AAA" not in engine.state.shadow and stats["closed"] == 1 and stats["wins"] == 0 and stats["net_usd"] < 0


def test_the_screen_states_the_valuation_rule() -> None:
    config = engine_module.CONFIG
    assert "Valuation target ≥ 10% above the ask" in r2d2_lab_live.LIVE_RULES[config]
    assert r2d2_lab_live.LIVE_SLOTS[config] == 20 and r2d2_lab_live.LIVE_RISK[config] == r2d2_lab_live.LIVE_RISK["TIT-2S5-F20"]
