"""The load test of the shared Massive path (owner, 30/10/2026: "esse fluxo de 900 papéis é bem maior, então precisa de
um teste de volume antes"; Codex 6537835879: the reader, T and Q together, the shadow tapes and the exits' service).

The REAL ``run_session`` (its once-a-second full step, its fast passes on ``wait_update``, its commits and marks writer)
runs on a database without a server, from 09:30:59 of a past session on the wall clock, with the shadow mode in force:
the REAL ``MassiveQuoteStream`` reader (its own thread) takes frames a simulated socket delivers on a schedule — trades of
900 names (the universe, into the shadow tapes) mixed with quotes of 20 carried positions — at an opening rate, then a
regular one. Three positions go quiet (no quote after the first seconds): the full step asks Massive's REST for them (a
simulated answer 0.3-0.7 s late) and the fast passes wait on it, as in production. Ten quotes cross a position's stop at
known instants. Measured (aggregates only, no symbol of any market):
  sale      from a stop-crossing quote's scheduled arrival to the engine booking the sale;
  served    every pushed quote of a held name, from its scheduled arrival to the first engine read of it or of a newer one
            of the same name (unserved ones counted; the socket stays open and silent after the last frame);
  reader    the reader's lag behind the schedule, the frames and trades the stream took against those generated;
  passes    the engine's reads of pushed quotes per second and the longest gap between two reads of a name.
Criteria (explicit, PASS/FAIL in the output): no trade or frame lost, no reconnect, no sink failure; every crossing sold,
sale p99 <= SALE_P99_MS; served p99 <= SERVED_P99_MS, unserved 0.

    python -m app.r2d2_massive_load --opening-events 40000 --opening-seconds 30 --regular-events 6000 --regular-seconds 30
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import random
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from typing import Any

from . import r2d2_live_engine as engine_module
from .config import Settings
from .database import Database
from .r2d2_live_engine import NEW_YORK, EngineState, LiveEngineStream, Member, MassiveQuoteStream, Position

DAY = date(2026, 10, 28)  # a past session: the wall clock is mapped onto it from 09:30:59
NAMES = ["N%03d" % i for i in range(900)]
CANDIDATES = 280  # NAMES[:CANDIDATES] open 2% under their last close on EODHD's tape: the candidates fixed at 09:31
HELD = ["H%02d" % i for i in range(20)]
QUIET = HELD[:3]  # no quote after QUIET_AFTER_SECONDS: the full step asks Massive's REST for them
QUIET_AFTER_SECONDS = 2.0
CROSSING = HELD[5:15]  # one stop-crossing quote each, at an instant spread over the opening phase
FRAME_EVENTS = 100  # events per frame, as Massive batches them
ENTRY_BID = 100.0
SALE_P99_MS = 1_500.0  # a full step may wait 1.7 s on Massive's REST for a quiet name; one second's pass is the floor
SERVED_P99_MS = 1_500.0


def _pct(values: list[float], q: float) -> float | None:
    return round(sorted(values)[min(len(values) - 1, int(q * len(values)))], 2) if values else None


class _Socket:
    """Frames on a schedule (perf_counter seconds) after the auth handshake; open and silent ``linger`` seconds after the
    last one, then the stream is stopped."""

    def __init__(self, stream: MassiveQuoteStream, schedule: list[tuple[float, str]], lags: list[float], linger: float) -> None:
        self.stream, self.schedule, self.lags, self.linger = stream, schedule, lags, linger
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
            if self.schedule and time.perf_counter() < self.schedule[-1][0] + self.linger:
                await asyncio.sleep(0.05)
                raise TimeoutError  # silence: the reader loops on
            self.stream._stop.set()
            raise TimeoutError
        due, frame = self.schedule[self.index]
        wait = due - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)
        self.lags.append((time.perf_counter() - due) * 1000)
        self.index += 1
        return frame


def _schedule(phases: list[tuple[float, float, list[str]]], quote_share: float, start: float, session_ms: int,
              exits_from: float) -> tuple[list[tuple[float, str]], dict[str, list[tuple[float, float]]], dict[str, float], int, int]:
    """Frames for each (events per second, seconds, traded names) phase from ``start``: trades of the phase's names;
    ``quote_share`` of the events are quotes of HELD in turn (a bid unique per name, rising a hair each time: never a
    stop or a lock); from ``exits_from`` (09:31, when the engine's exits start) one crossing quote per CROSSING name at
    -0.6% net, spread over the following phases. Returns the frames, each name's quotes (scheduled time, bid), the
    crossing instants, and the trade and quote counts."""
    rng = random.Random(30102026)
    frames: list[tuple[float, str]] = []
    quotes_by_name: dict[str, list[tuple[float, float]]] = {name: [] for name in HELD}
    crossings: dict[str, float] = {}
    trades = quotes = 0
    per_name: dict[str, int] = {}
    total = sum(seconds for _, seconds, _ in phases)
    window = max(1.0, start + total - exits_from - 2.0)  # the crossings land after 09:31, spread over what follows
    cross_at = {name: exits_from + 1.0 + window * i / max(1, len(CROSSING)) for i, name in enumerate(CROSSING)}
    quiet_from = exits_from + QUIET_AFTER_SECONDS
    clock = start
    stride = max(1, round(1 / quote_share)) if quote_share > 0 else 0
    for rate, seconds, traded in phases:
        step = FRAME_EVENTS / rate
        for _ in range(int(rate * seconds / FRAME_EVENTS)):
            events = []
            stamp = session_ms + int((clock - start) * 1000)
            for i in range(FRAME_EVENTS):
                if stride and i % stride == 0:
                    name = HELD[quotes % len(HELD)]
                    quotes += 1
                    if name in QUIET and clock > quiet_from:
                        continue  # a quiet name: nothing more pushed
                    if name in crossings or (name in cross_at and clock >= cross_at[name]):
                        if name not in crossings:
                            crossings[name] = clock
                            bid = round(ENTRY_BID * 0.994, 4)  # about -0.6% net: under the -0.4% stop
                        else:
                            continue  # sold: no more quotes of it
                    else:
                        bid = round(ENTRY_BID + 0.000001 * (len(quotes_by_name[name]) + 1), 6)
                    quotes_by_name[name].append((clock, bid))
                    events.append({"ev": "Q", "sym": name, "bp": bid, "ap": bid + 0.01, "t": stamp})
                else:
                    name = traded[trades % len(traded)]
                    events.append({"ev": "T", "sym": name, "x": 11, "p": 49.0 + rng.random(), "s": 100, "t": stamp})
                    per_name[name] = per_name.get(name, 0) + 1
                    trades += 1
            frames.append((clock, json.dumps(events)))
            clock += step
    _schedule.per_name = per_name  # type: ignore[attr-defined]
    return frames, quotes_by_name, crossings, trades, quotes


def _no_http(*args: Any, **kwargs: Any) -> Any:
    """The universe's HTTP reader: never called (``build_universe`` is replaced for the run)."""
    raise RuntimeError("the load test reads no HTTP")


def _revision() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
                              cwd=Path(__file__).resolve().parent).stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance only
        return None


def run(opening_events: float, opening_seconds: float, session_events: float, session_seconds: float,
        regular_events: float, regular_seconds: float, quote_share: float = 0.05, from_open: bool = True) -> dict[str, Any]:
    """``from_open``: the wall clock maps onto 09:29:59, the opening phase (``opening_seconds`` <= 60) is the 900 names'
    minute before the candidates are fixed (no exit runs yet, as in production); else it maps onto 09:30:59 and the
    opening phase is skipped. The session phase (the candidates and the held names, exits running) and the regular one
    follow from 09:31."""
    first = day_time(9, 29, 59) if from_open else day_time(9, 30, 59)
    session_start = datetime.combine(DAY, first, tzinfo=NEW_YORK).astimezone(timezone.utc)
    universe = [Member(name, "NASDAQ", 50.0, 50e6) for name in NAMES] + [Member(name, "NASDAQ", 100.0, 50e6) for name in HELD]
    state = EngineState(nav_realized=1_000_000.0)
    opened = datetime.combine(DAY, day_time(9, 45), tzinfo=NEW_YORK).isoformat()
    for name in HELD:  # carried positions: the exits run from 09:31, the entries find no candidate (no opening print)
        state.positions[name] = Position(name, "NASDAQ", 100.0, ENTRY_BID, 100.0 * ENTRY_BID * (1 + engine_module.FEE_SIDE),
                                         opened, last_mark=ENTRY_BID, days_held=1)
    massive = MassiveQuoteStream("load-test", url="ws://127.0.0.1:9/")
    lags: list[float] = []
    served: dict[str, list[tuple[float, float, float | None]]] = {}
    reads: dict[str, list[float]] = {name: [] for name in HELD}
    sales: dict[str, float] = {}
    t0 = time.perf_counter()
    now = lambda: session_start + timedelta(seconds=time.perf_counter() - t0)  # noqa: E731
    session_ms = int((session_start + timedelta(seconds=1)).timestamp() * 1000)  # the schedule starts a second in
    start_at = t0 + 1.0
    exits_from = t0 + (61.0 if from_open else 1.0)  # 09:31:00 on the wall clock
    phases: list[tuple[float, float, list[str]]] = []
    if from_open:
        phases.append((opening_events, min(60.0, opening_seconds), NAMES))
        if opening_seconds < 60.0:
            phases.append((regular_events, 60.0 - opening_seconds, NAMES))  # the rest of the opening minute
    phases += [(session_events, session_seconds, NAMES[:CANDIDATES]), (regular_events, regular_seconds, NAMES[:CANDIDATES])]
    frames, quotes_by_name, crossings, trades, quotes = _schedule(phases, quote_share, start_at, session_ms, exits_from)
    # building the frames took time: the wall clock (and the session's) starts now, the schedule a second later
    shift = time.perf_counter() - t0
    t0 += shift
    exits_from += shift  # 09:31 on the wall clock moves with it
    frames = [(due + shift, frame) for due, frame in frames]
    quotes_by_name = {name: [(due + shift, bid) for due, bid in items] for name, items in quotes_by_name.items()}
    crossings = {name: due + shift for name, due in crossings.items()}
    end = (frames[-1][0] if frames else start_at) + 1.5
    for name, items in quotes_by_name.items():
        served[name] = [(due, bid, None) for due, bid in items]
    index_of = {name: {bid: i for i, (_, bid) in enumerate(items)} for name, items in quotes_by_name.items()}
    # the quotes pushed before 09:31 (the exits start then) stay out of the bookkeeping: marking them inside the engine's
    # first read would be the harness's own cost, not the engine's
    first_unserved = {name: next((i for i, (due, _) in enumerate(items) if due >= exits_from), len(items))
                      for name, items in quotes_by_name.items()}
    socket = _Socket(massive, frames, lags, linger=1.0)
    quote = massive.quote
    totals = {"trades": 0, "off_exchange": 0, "extended": 0, "sink_failures": 0}
    take = massive.take_trade_gauges
    shadows: list[Any] = []

    def cumulative_take() -> tuple[int, int, int, int, int, int, int]:
        taken = take()  # the session's minute line resets the counts: the harness keeps the totals
        for key, value in zip(("trades", "off_exchange", "extended", "sink_failures"), (taken[1], taken[4], taken[5], taken[6])):
            totals[key] += value
        return taken
    set_sink = massive.set_trade_sink

    def captured_sink(sink: Any) -> None:
        if sink is not None:
            shadows.append(getattr(sink, "__self__", None))
        set_sink(sink)
    massive.take_trade_gauges = cumulative_take  # type: ignore[method-assign]
    massive.set_trade_sink = captured_sink  # type: ignore[method-assign]

    def recorded_quote(symbol: str) -> Any:
        found = quote(symbol)
        instant = time.perf_counter()
        if symbol in reads:
            reads[symbol].append(instant)
        if found is not None and symbol in index_of:
            upto = index_of[symbol].get(found[0])
            if upto is not None:
                items = served[symbol]
                for i in range(first_unserved[symbol], upto + 1):
                    due, bid, _ = items[i]
                    items[i] = (due, bid, instant)
                first_unserved[symbol] = max(first_unserved[symbol], upto + 1)
        return found

    def rest(symbol: str, at: datetime) -> tuple[float, float, datetime] | None:
        time.sleep(random.uniform(0.3, 0.7))  # Massive's REST from the host, ~0.3-0.7 s (30/10)
        return ENTRY_BID, ENTRY_BID + 0.01, at

    sell = engine_module.Engine._sell

    def recorded_sell(self: Any, position: Any, bid: float, net: float, reason: str, moment: datetime) -> Any:
        sales.setdefault(position.symbol, time.perf_counter())
        return sell(self, position, bid, net, reason, moment)

    def sleep(seconds: float) -> None:
        if time.perf_counter() >= end:
            raise KeyboardInterrupt
        time.sleep(seconds)

    patched = {"build_universe": engine_module.build_universe, "seed_from_lab_book": engine_module.seed_from_lab_book,
               "connect": engine_module.websockets.connect, "_sell": engine_module.Engine._sell,
               "TRADE_SHADOW": engine_module.TRADE_SHADOW}
    engine_module.build_universe = lambda *a, **k: universe  # type: ignore[assignment]
    engine_module.seed_from_lab_book = lambda db, now: state  # type: ignore[assignment]
    engine_module.websockets.connect = lambda url, **kwargs: socket  # type: ignore[assignment]
    engine_module.Engine._sell = recorded_sell  # type: ignore[method-assign]
    engine_module.TRADE_SHADOW = True
    massive.quote = recorded_quote  # type: ignore[method-assign]
    stream = LiveEngineStream("", max_symbols=1000)  # EODHD's, never connected: no fallback quote

    def opening_prints() -> None:
        """EODHD's opening print of the candidates (2% under their last close), once the session has started."""
        while stream.session != DAY:
            time.sleep(0.01)
        at = now()
        for name in NAMES[:CANDIDATES]:
            stream.record_trade(name, 49.0, 100, max(at, datetime.combine(DAY, day_time(9, 30, 0, 500000), tzinfo=NEW_YORK)))
    threading.Thread(target=opening_prints, name="opening-prints", daemon=True).start()
    massive.start()
    try:
        with tempfile.TemporaryDirectory() as cache:
            try:
                engine_module.run_session(stream=stream, database=Database(Settings(database_url="")), get_json=_no_http,
                                          base_url="", token="", day=DAY, cache_dir=Path(cache), now=now, sleep=sleep,
                                          nbbo=rest, massive=massive)
            except KeyboardInterrupt:
                pass
    finally:
        massive.stop()
        engine_module.build_universe = patched["build_universe"]  # type: ignore[assignment]
        engine_module.seed_from_lab_book = patched["seed_from_lab_book"]  # type: ignore[assignment]
        engine_module.Engine._sell = patched["_sell"]  # type: ignore[method-assign]
        engine_module.TRADE_SHADOW = patched["TRADE_SHADOW"]
        reader = massive._thread
        if reader is not None:
            reader.join(timeout=10)
        engine_module.websockets.connect = patched["connect"]  # type: ignore[assignment]
    massive.take_trade_gauges()  # the counts since the session's last minute line, into the totals
    per_name = getattr(_schedule, "per_name", {})
    shadow = shadows[-1] if shadows else None
    tape_trades = {name: int(round(shadow.tapes[name].volume / 100)) if shadow is not None and name in shadow.tapes else 0
                   for name in per_name}
    candidates = set(NAMES[:CANDIDATES])
    candidate_generated = sum(count for name, count in per_name.items() if name in candidates)
    candidate_taken = sum(count for name, count in tape_trades.items() if name in candidates)
    other_generated = sum(count for name, count in per_name.items() if name not in candidates)
    other_taken = sum(count for name, count in tape_trades.items() if name not in candidates)
    sale_ms = [(sales[name] - crossings[name]) * 1000 for name in crossings if name in sales]
    # the exits run from 09:31: a quote pushed before is the stream's, read once they start (counted apart)
    served_ms = [(at - due) * 1000 for name in HELD for due, _, at in served[name] if at is not None and due >= exits_from]
    unserved = sum(1 for name in HELD for due, _, at in served[name] if at is None and due >= exits_from)
    slowest = sorted(((at - due) * 1000, due - exits_from) for name in HELD for due, _, at in served[name]
                     if at is not None and due >= exits_from)[-12:]
    before_exits = sum(1 for name in HELD for due, _, _ in served[name] if due < exits_from)
    gaps = [max((b - a) * 1000 for a, b in zip(times, times[1:])) for name, times in reads.items()
            if name not in QUIET and name not in CROSSING and len(times) > 1]
    duration = (frames[-1][0] - frames[0][0]) if frames else 0.0
    reads_in_run = sum(1 for times in reads.values() for t in times if frames and frames[0][0] <= t <= frames[-1][0])
    result = {
        "revision": _revision(), "python": platform.python_version(), "platform": platform.platform(),
        "websockets": getattr(engine_module.websockets, "__version__", None),
        "profile": {"from_open": from_open, "opening_events_per_second": opening_events, "opening_seconds": opening_seconds,
                    "session_events_per_second": session_events, "session_seconds": session_seconds,
                    "regular_events_per_second": regular_events, "regular_seconds": regular_seconds,
                    "candidates": CANDIDATES,
                    "quote_share": quote_share, "frame_events": FRAME_EVENTS, "names": len(NAMES), "held": len(HELD),
                    "quiet": len(QUIET), "crossing": len(CROSSING), "rest_latency_s": [0.3, 0.7]},
        "generated": {"trades": trades, "quotes_pushed": sum(len(items) for items in quotes_by_name.values()),
                      "frames": len(frames)},
        "taken": {"trades": totals["trades"], "frames_read": socket.index, "subscribed_channels": socket.subscribed,
                  "off_exchange": totals["off_exchange"], "extended": totals["extended"], "sink_failures": totals["sink_failures"],
                  "candidate_trades_generated": candidate_generated, "candidate_trades_in_shadow_tapes": candidate_taken,
                  "other_trades_generated": other_generated, "other_trades_in_shadow_tapes": other_taken,
                  "quotes_before_0931": before_exits},
        # a candidate is followed all session: each of its trades must reach the shadow tapes. The other names are
        # informative only: the subscription's cap (UNIVERSE_SIZE with the held names) leaves the last 20 never followed
        # (Codex 6538461047: the whole difference of the full profile), and none is followed after 09:31
        "losses": {"candidate_trades": candidate_generated - candidate_taken, "frames": len(frames) - socket.index},
        "reader_lag_ms": {"p50": _pct(lags, 0.5), "p99": _pct(lags, 0.99), "max": round(max(lags), 2) if lags else None},
        "sale_after_crossing_ms": {"n": len(sale_ms), "of": len(crossings), "p50": _pct(sale_ms, 0.5),
                                   "p99": _pct(sale_ms, 0.99), "max": round(max(sale_ms), 2) if sale_ms else None},
        "served_ms": {"n": len(served_ms), "unserved": unserved, "p50": _pct(served_ms, 0.5), "p99": _pct(served_ms, 0.99),
                      "max": round(max(served_ms), 2) if served_ms else None},
        "served_slowest": [[round(offset, 2), round(ms, 1)] for ms, offset in slowest],  # [s after 09:31, ms]
        "reads": {"per_second": round(reads_in_run / duration, 1) if duration else None,
                  "longest_gap_ms_max": round(max(gaps), 2) if gaps else None},
        "reconnects": massive.reconnects,
    }
    checks = {
        "no_loss": result["losses"] == {"candidate_trades": 0, "frames": 0} and shadow is not None,
        "no_reconnect": massive.reconnects == 0,
        "no_sink_failure": totals["sink_failures"] == 0,
        "every_crossing_sold": len(sale_ms) == len(crossings) > 0,
        "sale_p99": bool(sale_ms) and (result["sale_after_crossing_ms"]["p99"] or 0) <= SALE_P99_MS,
        "served_p99": bool(served_ms) and (result["served_ms"]["p99"] or 0) <= SERVED_P99_MS,
        "none_unserved": unserved == 0,
    }
    result["criteria"] = {"sale_p99_ms_max": SALE_P99_MS, "served_p99_ms_max": SERVED_P99_MS, "checks": checks,
                          "verdict": "PASS" if all(checks.values()) else "FAIL"}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.r2d2_massive_load")
    parser.add_argument("--opening-events", type=float, default=40_000)
    parser.add_argument("--opening-seconds", type=float, default=60)
    parser.add_argument("--session-events", type=float, default=20_000)
    parser.add_argument("--session-seconds", type=float, default=30)
    parser.add_argument("--regular-events", type=float, default=6_000)
    parser.add_argument("--regular-seconds", type=float, default=30)
    parser.add_argument("--quote-share", type=float, default=0.05)
    parser.add_argument("--from-0931", action="store_true", help="skip the opening minute (the session starts at 09:31)")
    args = parser.parse_args(argv)
    result = run(args.opening_events, args.opening_seconds, args.session_events, args.session_seconds, args.regular_events,
                 args.regular_seconds, args.quote_share, from_open=not args.from_0931)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["criteria"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
