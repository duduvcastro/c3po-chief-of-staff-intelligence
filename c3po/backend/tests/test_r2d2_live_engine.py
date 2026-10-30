import json
import math
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
    marks = {"S2": 100.27, "S3": 100.05}  # S2 back to ~+0.26%: below its step floor (+0.30%) → lock
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
    """Owner 29/10: arms at +0.10%, a new floor every 0.05 up to +0.30%, every 0.10 above, the floor ON the step."""
    floor = engine_module.lock_floor
    assert [round(floor(p), 10) for p in (0.10, 0.1499, 0.15, 0.2, 0.2999, 0.30, 0.3999, 0.40, 0.47, 0.95)] == \
           [0.10, 0.10, 0.15, 0.20, 0.25, 0.30, 0.30, 0.40, 0.40, 0.90]
    assert floor(0.15 - 1e-12) == floor(0.15)  # a hair under a step (float error) still counts it
    assert engine_module.RULE["stop_percent"] == 0.4 and engine_module.RULE["lock_min_percent"] == 0.10


@pytest.mark.parametrize(("peak", "hold", "sell", "floor"), [
    (0.12, 0.11, 0.09, 0.10), (0.17, 0.16, 0.14, 0.15), (0.33, 0.31, 0.29, 0.30), (0.47, 0.41, 0.39, 0.40)])
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
    assert _mark(engine, "S2", _at(10, 0), bid(-0.20)) == [] and not position.armed  # held at -0.20%
    assert _mark(engine, "S2", _at(10, 0, 1), bid(0.11)) == [] and position.armed  # back above +0.10%: armed, floor +0.10%
    fills = _mark(engine, "S2", _at(10, 0, 2), bid(0.09))
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: trava de lucro")]


def test_the_floor_has_no_gap_under_the_wide_band() -> None:
    floor = engine_module.lock_floor
    for peak in (0.30 - 5e-10, 0.30 - 2e-10, 0.30, 0.30 + 1e-12):
        assert round(floor(peak), 10) == 0.30
    assert round(floor(0.30 - 2e-9), 10) == 0.25


def test_the_stop_before_the_lock_arms_is_minus_four_tenths() -> None:
    engine = _engine()
    position, bid = _held(engine, "S2")
    assert _mark(engine, "S2", _at(10, 0), bid(0.09)) == [] and not position.armed  # positive, under +0.10%: not armed
    assert abs(position.net_percent(engine.book(_at(10, 0))["positions"][0]["stop_price"]) - -0.4) < 1e-9
    assert _mark(engine, "S2", _at(10, 0, 1), bid(-0.39)) == []
    fills = _mark(engine, "S2", _at(10, 0, 2), bid(-0.41))
    assert [(f["symbol"], f["reason"].split(",")[0]) for f in fills] == [("S2", "venda: stop")]


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
    assert validated["config"] == "TIT-2S5-RT" and len(validated["trades"]) == 1
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
    assert row["band"] == "5_8" and row["ask"] == 98.03 and abs(row["size_usd"] - 1_000_000.0 / 20) < 1e-6
    # its exits: the last trade less half the refused spread is the estimated bid; up ~+0.12% → armed, floor +0.10%
    half = row["spread_bps"] / 2 / 1e4
    price_at = lambda net: row["ask"] * (1 + FEE_SIDE) * (1 + net / 100) / ((1 - FEE_SIDE) * (1 - half))  # noqa: E731
    up, down = _at(9, 42), _at(9, 42, 1)
    engine.step(up, lambda s: MarketView(price=price_at(0.12), trade_at=up, vwap=98.0) if s == "AAA" else MarketView())
    assert engine.state.shadow["AAA"]["armed"]
    engine.step(down, lambda s: MarketView(price=price_at(0.09), trade_at=down, vwap=98.0) if s == "AAA" else MarketView())
    stats = engine.state.bands["5_8"]
    assert "AAA" not in engine.state.shadow and stats["closed"] == 1 and stats["wins"] == 1
    assert abs(stats["net_usd"] - 50_000.0 * 0.09 / 100) < 1e-6 and not engine.state.positions and not engine.fills  # no money


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
    assert stored is not None and stored[1] == "TIT-2S5-RT" and len(stored[2]["positions"]) == 1
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
    feed, real = _bid_at(position, -0.75), _bid_at(position, -0.25)
    fills = engine.step(t, lambda s: _view(98.0, 98.0, feed, feed + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (real, real + 0.01, now))
    assert fills == [] and position.last_mark == real and engine.exit_sources == {"massive": 1, "stream": 0, "none": 0, "unconfirmed": 0}
    t = _at(10, 0, 3)  # the NBBO crosses the stop: sold at ITS bid
    stop = _bid_at(position, -0.42)
    fills = engine.step(t, lambda s: _view(98.0, 98.0, feed, feed + 0.01, t) if s == "AAA" else MarketView(),
                        nbbo=lambda s, now: (stop, stop + 0.01, now))
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", stop)] and "stop" in fills[0]["reason"]
    assert fills[0]["realized_return_percent"] == pytest.approx(-0.42)


def test_exits_a_held_name_without_a_feed_quote_is_marked_armed_and_locked_on_massive() -> None:
    """30/10 10:43 BRT: AMD at +0.175% net on the screen, the engine's stop still -0.4% (no fresh feed quote, never
    armed). Massive marks it every second: the lock arms at +0.10% and sells at the step's floor."""
    engine = _engine()
    t = _at(10, 0, 1)
    position = _bought_aaa(engine, t)
    no_quote = MarketView(price=98.2, trade_at=t, vwap=98.0)  # trades only: the quote feed has not delivered it
    for second, net in ((2, 0.12), (3, 0.17)):
        t = _at(10, 0, second)
        bid = _bid_at(position, net)
        assert engine.step(t, lambda s: no_quote if s == "AAA" else MarketView(), nbbo=lambda s, now: (bid, bid + 0.01, now)) == []
    assert position.armed and position.peak_percent == pytest.approx(0.17) and position.exit_price() == pytest.approx(_bid_at(position, 0.15))
    t = _at(10, 0, 4)
    bid = _bid_at(position, 0.14)
    fills = engine.step(t, lambda s: no_quote if s == "AAA" else MarketView(), nbbo=lambda s, now: (bid, bid + 0.01, now))
    assert [(f["side"], f["price"]) for f in fills] == [("SELL", bid)] and "trava" in fills[0]["reason"]
    assert engine.exit_sources == {"massive": 3, "stream": 0, "none": 0, "unconfirmed": 0}


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
    assert fills == [] and engine.exit_sources == {"massive": 0, "stream": 1, "none": 0, "unconfirmed": 1}
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
    assert engine.exit_sources == {"massive": 0, "stream": 0, "none": 1, "unconfirmed": 0}
    assert engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(),
                       nbbo=lambda s, now: (98.2, 98.1, now)) == []  # crossed: no NBBO
    assert engine.exit_sources["none"] == 2 and position.last_mark == 98.105
    monkeypatch.setattr(engine_module, "NBBO_EXIT_BUDGET_SECONDS", 0.3)

    def slow(symbol, now):
        wall.sleep(2.0)
        return (98.0, 98.01, now)
    began = wall.monotonic()
    engine.step(t, lambda s: MarketView(price=98.1, trade_at=t, vwap=98.0) if s == "AAA" else MarketView(), nbbo=slow)
    assert wall.monotonic() - began < 0.3 + 0.5  # the exits never wait past their budget
    assert engine.exit_sources["none"] == 3 and "AAA" in engine.state.positions


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

    def step(self, now, view, signal=None, nbbo=None):  # each step waits 0.6 s on Massive and fills
        steps.append(now)
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
                    cache_dir=tmp_path, now=lambda: clock["t"], sleep=sleep, nbbo=lambda s, now: None)
    after_steps = slept[-100:]
    assert all(abs(s - 0.4) < 1e-6 for s in after_steps)  # one pass a second: 0.6 s of step, 0.4 s of sleep
    assert 148 <= (steps[-1] - steps[0]).total_seconds() + 1 <= 151
    feed = [r for r in caplog.records if "R2D2 live feed:" in r.getMessage()]
    assert len(feed) == 2  # every 60 s although every step filled


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
    """Owner 29/10: "vamos mudar para até 5 bps" — 3.4 and 5.0 bps buy, 5.5 bps is refused (it was 3 bps)."""
    assert engine_module.RULE["spread_max_bps"] == 5.0 and engine_module.CONFIG == "TIT-2S5-RT"
    engine = _crossing_engine()
    t = _at(9, 41)
    views = {"CCC": _view(29.1, 29.0, 29.0, ask, t)}
    fills = engine.step(t, lambda s: views.get(s, MarketView()), nbbo=lambda s, now: (29.0, ask, now))
    assert ([f["symbol"] for f in fills] == ["CCC"]) is bought and engine.skips["spread"] == (0 if bought else 1)


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
    start = {"last_entry": _at(15, 29, 58), "massive_age": _at(10, 0, 0), "stream_age": _at(10, 0, 0)}[case]

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

    def spy(self, now, view, signal=None, nbbo=None):
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
    """Codex 6478311166 P2-2: asked at 15:29:59, answered 1.49 s later (15:30:00.49): past the last entry, no buy."""
    clock = {"t": 0.0}
    monkeypatch.setattr(engine_module.clock_time, "monotonic", lambda: clock["t"])
    engine = _engine()
    t = _at(15, 28, 59)
    below = {"AAA": _view(97.9, 98.0, 97.89, 97.91, t), "CCC": _view(28.9, 29.0, 28.80, 29.00, t)}
    engine.step(t, lambda s: below.get(s, MarketView()))
    t = _at(15, 29, 59)
    above = {"AAA": _view(98.1, 98.0, 98.095, 98.105, t), "CCC": _view(29.1, 29.0, 29.0, 29.005, t)}
    quotes = {"AAA": (98.095, 98.105), "CCC": (29.0, 29.005)}

    def slow(symbol, now):  # asked at once, both answered 1.49 s after the asking
        clock["t"] = max(clock["t"], 1.49)
        return (*quotes[symbol], now)
    assert engine.step(t, lambda s: above.get(s, MarketView()), nbbo=slow) == []
    assert not engine.state.positions and engine.skips["late"] == 1 and engine.fills == []
    clock["t"] = 0.0  # the control: asked at 15:29:57, answered inside the window, executed at the effective instant
    engine = _engine()
    engine.step(_at(15, 28, 57), lambda s: below.get(s, MarketView()))
    fills = engine.step(_at(15, 29, 57), lambda s: above.get(s, MarketView()), nbbo=slow)
    assert [f["symbol"] for f in fills] == ["AAA", "CCC"] and engine.skips["late"] == 0
    assert all(f["executed_at"] == (_at(15, 29, 57) + timedelta(seconds=1.49)).isoformat() for f in fills)


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
