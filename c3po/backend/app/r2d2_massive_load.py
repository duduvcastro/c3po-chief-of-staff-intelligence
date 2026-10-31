"""The load test of the shared Massive path (owner, 30/10/2026: "esse fluxo de 900 papéis é bem maior, então precisa de
um teste de volume antes"; Codex 6537835879: the reader, T and Q together, the shadow tapes and the exits' service).

A simulated socket delivers frames on a schedule to the REAL ``MassiveQuoteStream`` reader (its ``_run`` loop in its own
thread, as in production): trades of 900 names mixed with quotes of the 20 held names, at an opening rate, then a
regular one. The trades go to a shadow ``LiveEngineStream`` (the Monday mode); meanwhile the main thread runs the
engine's REAL ``Engine.fast_exits`` on the pushed quotes at the engine's cadence, and watches every quote of a held name
become readable. Measured (aggregates only, no symbol of any market): every trade and quote generated against those the
stream took (losses), the reader's lag behind the schedule, the time from a quote's scheduled arrival to the exits
reading it, the exit passes per second and their duration, reconnects.

    python -m app.r2d2_massive_load --opening-rate 40000 --opening-seconds 30 --regular-rate 6000 --regular-seconds 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from datetime import date, datetime, time as day_time, timedelta, timezone
from typing import Any

from . import r2d2_live_engine as engine_module
from .r2d2_live_engine import NEW_YORK, Engine, EngineState, LiveEngineStream, MarketView, Member, MassiveQuoteStream, Position

DAY = date(2026, 10, 28)  # any past session: the stamps sit inside it, the stream's clock checks pass
NAMES = ["N%03d" % i for i in range(900)]
HELD = ["H%02d" % i for i in range(20)]
FRAME_EVENTS = 100  # events per frame, as Massive batches them
QUOTE_SHARE = 0.05  # one event in twenty is a held name's quote


def _percentile(values: list[float], q: float) -> float | None:
    return round(sorted(values)[min(len(values) - 1, int(q * len(values)))], 3) if values else None


class _Socket:
    """Frames on a schedule (perf_counter seconds), after the auth handshake; ends the stream when the schedule ends."""

    def __init__(self, stream: MassiveQuoteStream, schedule: list[tuple[float, str]], sent_quotes: dict[float, float],
                 lags: list[float]) -> None:
        self.stream, self.schedule, self.sent_quotes, self.lags = stream, schedule, sent_quotes, lags
        self.handshake = [json.dumps([{"ev": "status", "status": "connected"}]),
                          json.dumps([{"ev": "status", "status": "auth_success"}])]
        self.index = 0
        self.subscribed = 0

    async def __aenter__(self) -> "_Socket":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def send(self, text: str) -> None:
        frame = json.loads(text)
        if frame.get("action") == "subscribe":
            self.subscribed += len(str(frame.get("params", "")).split(","))

    async def recv(self) -> str:
        if self.handshake:
            return self.handshake.pop(0)
        if self.index >= len(self.schedule):
            self.stream._stop.set()
            raise TimeoutError
        due, frame = self.schedule[self.index]
        wait = due - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)
        self.lags.append((time.perf_counter() - due) * 1000)  # how late the reader comes back for this frame (ms)
        self.index += 1
        return frame


def _schedule(phases: list[tuple[float, float]], base_ms: int, start: float) -> tuple[list[tuple[float, str]], dict[float, float], int, int]:
    """Frames of FRAME_EVENTS events for each (rate per second, seconds) phase: trades of NAMES and, QUOTE_SHARE of the
    events, quotes of HELD whose bid is unique (it identifies the quote when the exits read it)."""
    schedule: list[tuple[float, str]] = []
    sent_quotes: dict[float, float] = {}
    trades = quotes = 0
    clock = start
    sequence = 0
    for rate, seconds in phases:
        frames = int(rate * seconds / FRAME_EVENTS)
        step = FRAME_EVENTS / rate
        for _ in range(frames):
            events = []
            for i in range(FRAME_EVENTS):
                sequence += 1
                stamp = base_ms + int((clock - start) * 1000)
                if i % int(1 / QUOTE_SHARE) == 0:
                    bid = round(100.0 + sequence * 1e-6, 6)
                    sent_quotes[bid] = clock
                    events.append({"ev": "Q", "sym": HELD[sequence % len(HELD)], "bp": bid, "ap": bid + 0.01, "t": stamp})
                    quotes += 1
                else:
                    events.append({"ev": "T", "sym": NAMES[trades % len(NAMES)], "x": 11, "p": 50.0 + (sequence % 7) * 0.01,
                                   "s": 100, "t": stamp})
                    trades += 1  # the trade counter picks the name: every name trades
            schedule.append((clock, json.dumps(events)))
            clock += step
    return schedule, sent_quotes, trades, quotes


def run(opening_rate: float, opening_seconds: float, regular_rate: float, regular_seconds: float) -> dict[str, Any]:
    shadow = LiveEngineStream("", max_symbols=1000)
    shadow.start_session(DAY)
    massive = MassiveQuoteStream("load-test", trade_sink=shadow.record_trade)
    massive.set_symbols(set(HELD))
    massive.set_trade_symbols(NAMES)
    base_ms = int(datetime.combine(DAY, day_time(10, 0), tzinfo=NEW_YORK).timestamp() * 1000)
    start = time.perf_counter() + 1.0  # the schedule begins a second after the reader is up
    schedule, sent_quotes, trades, quotes = _schedule([(opening_rate, opening_seconds), (regular_rate, regular_seconds)],
                                                       base_ms, start)
    lags: list[float] = []
    socket = _Socket(massive, schedule, sent_quotes, lags)
    original = engine_module.websockets.connect
    engine_module.websockets.connect = lambda url, **kwargs: socket  # type: ignore[assignment]
    try:
        reader = threading.Thread(target=lambda: asyncio.run(massive._run()), name="massive-load", daemon=True)
        reader.start()
        # the exits: 20 held positions marked on the pushed quotes at the engine's own cadence
        universe = [Member(name, "NASDAQ", 100.0, 50e6) for name in HELD]
        state = EngineState(nav_realized=1_000_000.0)
        opened = datetime.combine(DAY, day_time(9, 45), tzinfo=NEW_YORK).isoformat()
        for name in HELD:
            state.positions[name] = Position(name, "NASDAQ", 100.0, 100.0, 100.0 * 100.0 * (1 + engine_module.FEE_SIDE), opened,
                                             last_mark=100.0)
        engine = Engine(state, DAY, universe)
        engine.state.session = DAY.isoformat()
        seen: dict[str, float] = {}
        quote_delays: list[float] = []
        passes: list[float] = []
        end = schedule[-1][0] + 1.0 if schedule else start
        mid = datetime.combine(DAY, day_time(10, 0), tzinfo=NEW_YORK).astimezone(timezone.utc)
        while time.perf_counter() < end and reader.is_alive():
            massive.wait_update(engine_module.FAST_EXIT_SECONDS)
            began = time.perf_counter()
            for name in HELD:
                pushed = massive.quote(name)
                if pushed is not None and seen.get(name) != pushed[0]:
                    seen[name] = pushed[0]
                    sent = sent_quotes.get(pushed[0])
                    if sent is not None:
                        quote_delays.append((began - sent) * 1000)
            # the engine's pass on those quotes (a quote's own SIP time is the session instant: fresh to the engine)
            moment = mid + timedelta(seconds=time.perf_counter() - start)
            engine.fast_exits(moment, lambda symbol: MarketView(),
                              lambda symbol: (lambda q: (q[0], q[1], moment) if q else None)(massive.quote(symbol)))
            passes.append((time.perf_counter() - began) * 1000)
            gap = engine_module.FAST_EXIT_MIN_SECONDS - (time.perf_counter() - began)
            if gap > 0:
                time.sleep(gap)
        reader.join(timeout=10)
    finally:
        engine_module.websockets.connect = original  # type: ignore[assignment]
    taken = massive.take_trade_gauges()
    duration = (schedule[-1][0] - schedule[0][0]) if schedule else 0.0
    return {
        "profile": {"opening_trades_per_second": opening_rate, "opening_seconds": opening_seconds,
                    "regular_trades_per_second": regular_rate, "regular_seconds": regular_seconds,
                    "frame_events": FRAME_EVENTS, "quote_share": QUOTE_SHARE, "names": len(NAMES), "held": len(HELD)},
        "generated": {"events": trades + quotes, "trades": trades, "quotes": quotes, "frames": len(schedule)},
        "taken": {"trades": taken[1], "quote_messages": massive.messages, "off_exchange": taken[4], "extended": taken[5],
                  "sink_failures": taken[6], "frames_read": socket.index, "subscribed_channels": socket.subscribed},
        "losses": {"trades": trades - taken[1], "frames": len(schedule) - socket.index},
        "reader_lag_ms": {"p50": _percentile(lags, 0.5), "p99": _percentile(lags, 0.99), "max": max(lags) if lags else None},
        "quote_to_exits_ms": {"n": len(quote_delays), "p50": _percentile(quote_delays, 0.5), "p99": _percentile(quote_delays, 0.99),
                              "max": round(max(quote_delays), 3) if quote_delays else None},
        "exit_passes": {"n": len(passes), "per_second": round(len(passes) / duration, 1) if duration else None,
                        "duration_ms_p50": _percentile(passes, 0.5), "duration_ms_p99": _percentile(passes, 0.99)},
        "reconnects": massive.reconnects, "status": massive.status,
        "tapes_with_trades": sum(1 for name in NAMES if name in shadow.tapes),
        "held_positions_left": len(engine.state.positions),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.r2d2_massive_load")
    parser.add_argument("--opening-rate", type=float, default=40_000)
    parser.add_argument("--opening-seconds", type=float, default=30)
    parser.add_argument("--regular-rate", type=float, default=6_000)
    parser.add_argument("--regular-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.opening_rate, args.opening_seconds, args.regular_rate, args.regular_seconds), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
