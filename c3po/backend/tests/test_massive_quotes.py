from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.market_data.eodhd_stream import EodhdRealtimeStream, usable_display_tick
from app.market_data import massive_quotes
from app.market_data.massive_quotes import (
    CHUNK,
    GROUP_IDLE_SECONDS,
    MassiveSnapshotStream,
    live_label,
    regular_session,
    screen_stream,
)


TOKEN = "massive-secret-token"
NOW = datetime(2026, 11, 3, 15, 0, 30, tzinfo=timezone.utc)  # Tuesday 10:00:30 ET, regular session


def ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1e9)


def snapshot(*rows: tuple[str, float, datetime]) -> dict[str, Any]:
    return {"status": "OK", "tickers": [
        {"ticker": ticker, "lastTrade": {"p": price, "s": 100, "t": ns(at), "x": 4}, "day": {"c": price}}
        for ticker, price, at in rows
    ]}


class Massive:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        self.calls.append({"url": url, "params": dict(params or {})})
        answer = self.answers.pop(0) if self.answers else {"status": "OK", "tickers": []}
        if isinstance(answer, Exception):
            raise answer
        return answer


class Idle:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def stream(massive: Massive, *, is_open: bool = True, idle: Idle | None = None, max_symbols: int = 550,
           now: datetime = NOW) -> MassiveSnapshotStream:
    return MassiveSnapshotStream("https://api.massive.example/", TOKEN, get_json=massive.get_json,
                                 max_symbols=max_symbols, clock=lambda: now, is_open=lambda _: is_open,
                                 idle_clock=idle or Idle())


def test_a_poll_keeps_the_last_trade_as_a_display_tick_in_the_screens_spelling() -> None:
    at = NOW - timedelta(seconds=2)
    massive = Massive(snapshot(("AAA", 101.25, at), ("BRK.B", 480.5, at)))
    live = stream(massive)
    live.set_group("portfolio", ["aaa.us", "BRK-B"], priority=100)

    assert live.poll_once() == 2

    assert massive.calls[0]["url"] == "https://api.massive.example/v2/snapshot/locale/us/markets/stocks/tickers"
    assert massive.calls[0]["params"] == {"tickers": "AAA,BRK.B", "apiKey": TOKEN}
    tick = live.quote("brk-b.us")
    assert tick is not None and (tick.symbol, tick.price, tick.as_of, tick.source) == ("BRK-B", 480.5, at, "trade")
    assert tick.market_state == "open"
    assert live.quote("AAA") is not None and live.status == "connected"
    # the screens' own guard accepts it (regular session, plausible against the REST price)
    assert usable_display_tick(tick, 478.0)
    assert live.bars("AAA") == []


def test_names_follow_priority_then_the_group_renewed_last_up_to_the_cap() -> None:
    idle = Idle()
    massive = Massive()
    live = stream(massive, idle=idle, max_symbols=3)
    live.set_group("market:NASDAQ", ["L1", "L2"], priority=50)
    idle.now += 1
    live.set_group("portfolio", ["P1", "L1"], priority=100)
    idle.now += 1
    live.set_group("r2d2-lab-live", ["R1"], priority=140)

    assert live.desired() == ("R1", "P1", "L1")
    live.poll_once()
    assert massive.calls[0]["params"]["tickers"] == "R1,P1,L1"


def test_a_group_no_screen_renewed_stops_being_asked() -> None:
    idle = Idle()
    massive = Massive()
    live = stream(massive, idle=idle)
    live.set_group("market:NYSE", ["N1"], priority=50)
    live.set_group("portfolio", ["P1"], priority=100)
    idle.now += GROUP_IDLE_SECONDS - 1
    live.set_group("portfolio", ["P1"], priority=100)  # the open screen renews its group
    idle.now += 2

    assert live.desired() == ("P1",)
    idle.now += GROUP_IDLE_SECONDS + 1
    assert live.desired() == ()
    assert live.poll_once() == 0 and massive.calls == [] and live.status == "idle"


def test_nothing_is_asked_outside_the_regular_session() -> None:
    massive = Massive()
    live = stream(massive, is_open=False)
    live.set_group("portfolio", ["AAA"])

    assert live.poll_once() == 0
    assert massive.calls == [] and live.status == "closed"


def test_a_failed_request_keeps_the_last_ticks_and_names_only_the_error_type() -> None:
    at = NOW - timedelta(seconds=1)
    massive = Massive(snapshot(("AAA", 10.0, at)), RuntimeError(f"403 for url ...?apiKey={TOKEN}"))
    live = stream(massive)
    live.set_group("portfolio", ["AAA"])
    live.poll_once()

    assert live.poll_once() == 0

    tick = live.quote("AAA")
    assert tick is not None and tick.price == 10.0
    assert (live.status, live.last_error) == ("error", "RuntimeError")
    line = live.beat()
    assert TOKEN not in line
    assert line == "Screen quotes (Massive): state=error symbols=1 polls=2 failures=1 ticks=1"
    assert live.beat() == "Screen quotes (Massive): state=error symbols=1 polls=0 failures=0 ticks=0"  # per interval


def test_unusable_rows_are_refused_and_an_older_trade_never_replaces_a_newer_one() -> None:
    newer, older = NOW - timedelta(seconds=1), NOW - timedelta(seconds=30)
    yesterday = NOW - timedelta(days=1)
    massive = Massive(
        {"tickers": [
            {"ticker": "AAA", "lastTrade": {"p": 10.0, "t": ns(newer)}},
            {"ticker": "BBB", "lastTrade": {"p": 0, "t": ns(newer)}},
            {"ticker": "CCC", "lastTrade": {"p": 5.0}},
            {"ticker": "DDD", "lastTrade": {"p": 5.0, "t": ns(yesterday)}},
            {"ticker": "EEE", "lastTrade": {"p": 5.0, "t": ns(NOW + timedelta(minutes=1))}},
            {"ticker": "FFF", "lastTrade": {"p": "nan", "t": ns(newer)}},
            {"ticker": "ZZZ", "lastTrade": {"p": 5.0, "t": ns(newer)}},  # not asked
            {"ticker": "GGG"},
            "garbage",
        ]},
        snapshot(("AAA", 9.0, older)),
    )
    live = stream(massive)
    live.set_group("portfolio", ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"])

    assert live.poll_once() == 1
    assert live.poll_once() == 0

    tick = live.quote("AAA")
    assert tick is not None and tick.price == 10.0
    assert all(live.quote(symbol) is None for symbol in ("BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "ZZZ"))


def test_a_payload_that_is_not_a_snapshot_takes_nothing() -> None:
    for payload in (None, [], {"tickers": None}, {"tickers": "x"}, {"status": "ERROR"}):
        live = stream(Massive(payload))
        live.set_group("portfolio", ["AAA"])
        assert live.poll_once() == 0 and live.quote("AAA") is None and live.status == "connected"


def test_many_names_are_asked_in_chunks() -> None:
    names = [f"N{index:03d}" for index in range(CHUNK * 2 + 5)]
    massive = Massive()
    live = stream(massive)
    live.set_group("market:NASDAQ", names)

    live.poll_once()

    assert [len(call["params"]["tickers"].split(",")) for call in massive.calls] == [CHUNK, CHUNK, 5]


def test_the_label_names_the_source() -> None:
    assert live_label(stream(Massive())) == "Massive Real-Time"
    assert live_label(EodhdRealtimeStream("")) == "EODHD Real-Time WebSocket"
    assert live_label(SimpleNamespace()) == "EODHD Real-Time WebSocket"


def test_the_api_takes_massive_when_its_token_is_set_and_eodhd_otherwise() -> None:
    base = {"massive_base_url": "https://api.massive.example", "eodhd_api_token": "eodhd", "r2d2_ws_max_symbols": 77}
    chosen = screen_stream(SimpleNamespace(massive_api_token=TOKEN, **base))
    assert isinstance(chosen, MassiveSnapshotStream) and chosen.max_symbols == 77
    fallback = screen_stream(SimpleNamespace(massive_api_token="", **base))
    assert isinstance(fallback, EodhdRealtimeStream) and fallback.max_symbols == 77


def test_the_regular_session_is_new_york_s() -> None:
    assert regular_session(NOW)
    assert not regular_session(datetime(2026, 11, 3, 14, 29, 59, tzinfo=timezone.utc))
    assert not regular_session(datetime(2026, 11, 3, 21, 0, 1, tzinfo=timezone.utc))
    assert not regular_session(datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc))  # Saturday


def test_start_without_a_token_opens_nothing_and_stop_is_safe() -> None:
    live = MassiveSnapshotStream("https://api.massive.example", "  ", get_json=Massive().get_json)
    live.start()
    assert live._thread is None
    live.stop()
    assert live.status == "stopped"


def test_the_loop_polls_and_beats(monkeypatch: pytest.MonkeyPatch) -> None:
    at = NOW - timedelta(seconds=1)
    massive = Massive(snapshot(("AAA", 10.0, at)))
    live = stream(massive)
    live.set_group("portfolio", ["AAA"])
    lines: list[str] = []
    monkeypatch.setattr(massive_quotes.heartbeat, "info", lambda _fmt, line: lines.append(line))
    polled = []
    original = live.poll_once

    def once() -> int:
        polled.append(1)
        live._stop.set()  # one round
        return original()

    monkeypatch.setattr(live, "poll_once", once)
    live._run()

    assert polled == [1]
    assert lines == ["Screen quotes (Massive): state=connected symbols=1 polls=1 failures=0 ticks=1"]


class LabelledStream:
    label = "Massive Real-Time"
    max_symbols = 550

    def __init__(self, quotes: dict[str, Any]) -> None:
        self.quotes = quotes
        self.groups: dict[str, Any] = {}

    def set_group(self, name: str, symbols: list[str], *, priority: int = 50) -> None:
        self.groups[name] = (symbols, priority)

    def quote(self, symbol: str) -> Any:
        return self.quotes.get(symbol)

    def bars(self, symbol: str, *, limit: int = 180) -> list[dict[str, Any]]:
        return []

    def start(self) -> None: ...

    def stop(self) -> None: ...


class NoHttp:
    def get_json(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        raise AssertionError("no request expected")


def test_the_screens_name_massive_for_its_live_ticks() -> None:
    from app.config import Settings
    from app.database import Database
    from app.market_data.eodhd_stream import EodhdStreamQuote
    from app.market_data.live_markets import LiveMarketsService, MarketSpec
    from app.market_data.realtime import RealtimeMarketsService
    from app.schemas import LiveMarketItem, RealtimePortfolioIntradayPoint, RealtimePortfolioIntradayResponse

    at = datetime(2026, 8, 14, 15, tzinfo=timezone.utc)  # Friday 11:00 ET
    tick = EodhdStreamQuote(symbol="AMZN", price=231.5, as_of=at + timedelta(seconds=10), market_state="open")
    settings = Settings(eodhd_api_token="configured", auth_cookie_secure=False)
    live = LiveMarketsService(settings, NoHttp(), stream=LabelledStream({"AMZN": tick}))  # type: ignore[arg-type]
    item = live._apply_eodhd_stream(
        MarketSpec("Portfolio", "AMZN", "Amazon", "AMZN", "USD", "eodhd", "AMZN.US"),
        LiveMarketItem(group="Portfolio", symbol="AMZN", name="Amazon", provider_symbol="AMZN.US",
                       provider="EODHD All-In-One", exchange="US", currency="USD", price=230.0, previous_close=228.0,
                       market_state="REGULAR", status="delayed", delay_minutes=15, as_of=at, collected_at=at,
                       quality_score=88),
    )
    assert (item.provider, item.price, item.status) == ("Massive Real-Time", 231.5, "live")

    realtime = RealtimeMarketsService(settings, Database(settings), NoHttp(),  # type: ignore[arg-type]
                                      stream=LabelledStream({"AMZN": tick}))
    chart = realtime._apply_intraday_stream(RealtimePortfolioIntradayResponse(
        symbol="AMZN", name="Amazon", market="NASDAQ", currency="USD", session_date="2026-08-14", previous_close=228.0,
        open=229.0, high=230.5, low=228.5, current=230.0, change_percent=0.44,
        points=[RealtimePortfolioIntradayPoint(as_of=at, price=230.0, volume=100)], source="EODHD Intraday 5m",
        delay_minutes=15, status="delayed", generated_at=at,
    ))
    assert chart.source == "EODHD Intraday 5m + Massive Real-Time"
    assert chart.current == 231.5 and chart.status == "live"


def test_the_status_workflow_prints_the_heartbeat_by_its_exact_shape() -> None:
    import re
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    section = run.split('echo "== screen quotes', 1)[1]
    pattern = section.split('grep -oE "', 1)[1].split('" | tail', 1)[0]
    line = stream(Massive()).beat()

    assert re.search(pattern, "api-1  | " + line)
    assert not re.search(pattern, "api-1  | " + line + " AAA")  # anything after the numbers is never printed
    assert 'grep -cE "EODHD realtime"' in section  # the api's EODHD stream lines are only counted


def test_the_status_workflow_reads_eodhd_s_daily_counter_as_two_numbers_and_a_date() -> None:
    import re
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[3]
    run = yaml.safe_load((root / ".github" / "workflows" / "r2d2-live-status.yml").read_text())["jobs"]["status"]["steps"][1]["run"]
    section = run.split('echo "== EODHD calls today"', 1)[1]
    pattern = section.split("grep -oE '", 1)[1].split("' ||", 1)[0]
    script = section.split("<<'PY'", 1)[1].split("\nPY\n", 1)[0].split("\n", 1)[1]
    compile(script, "eodhd_usage", "exec")  # the remote snippet is valid Python as YAML hands it over

    assert re.search(pattern, "eodhd_calls_today=41999 limit=100000 date=2026-11-03")
    assert re.search(pattern, "eodhd usage read failed=MarketDataRequestError")
    assert not re.search(pattern, "eodhd_calls_today=41999 limit=100000 date=2026-11-03 someone@example.com")
    assert "print(" in script and script.count("print(") == 2 and "api_token" not in script.split("print(", 1)[1]
