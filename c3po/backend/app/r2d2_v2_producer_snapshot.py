"""R2D2 V2 — 10:00 ET snapshot producer: live quotes for the causal list + prepared components.

Publishes `snapshot.json` (schema `V2_SHADOW_SOURCE_SNAPSHOT_V2`, contract
`R2D2_V2_DATA_PORT_V1.md` rev 2) for one session D of one epoch:

- symbols = the causal list committed on D-1 (`causal_list/<epoch>/<D>.json`,
  field `commitment.list`); the universe always carries every listed symbol,
  with `bid`/`ask` null while no quote tick has been received (the collector
  keeps such names pending until the capture window closes);
- quotes from the provider's `us-quote` websocket feed, subscribed only for the
  list; each tick keeps its own clocks: `bid_source_at = ask_source_at` = the
  tick timestamp `t`, `received_at` = local receipt instant, `available_at` =
  the assembly instant of the snapshot that carries it;
- `daily` from `components/<D>/daily_61/<symbol>.json` (producer 1/2), `risk`
  from `components/<D>/risk.json` and `earnings` from
  `components/<D>/earnings.json` (other producers); a missing component is
  represented explicitly as an invalid response (`risk.value = null`,
  `earnings.coverage_verified = false`), never invented;
- publication by private atomic rename roughly once per second inside
  [10:00:00, 10:01:00) New York, envelope `sequence` increasing, raw tick tape
  kept in a private NDJSON file whose SHA-256 is the `provenance.payload_sha256`.

No eligibility decision, no order, no access to the V1 engine or its stream.
OFF by default (`C3PO_R2D2_V2_PRODUCERS_ENABLED=true` required). The provider
token is used only to open the websocket and never written anywhere.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping
from zoneinfo import ZoneInfo

from .r2d2_v2_producer_daily import ProducerError, canonical, write_private

PRODUCER = "fable-eodhd-snapshot"
PRODUCER_VERSION = "v1"
SNAPSHOT_SCHEMA = "V2_SHADOW_SOURCE_SNAPSHOT_V2"
MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
NEW_YORK = ZoneInfo("America/New_York")
CAPTURE_OPEN = time(10, 0)
CAPTURE_CLOSE = time(10, 1)
WARMUP_SECONDS = 30
PUBLISH_INTERVAL_SECONDS = 1.0
MAX_SYMBOLS = 550


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def capture_window(session_date: date) -> tuple[datetime, datetime]:
    open_at = datetime.combine(session_date, CAPTURE_OPEN, NEW_YORK).astimezone(timezone.utc)
    close_at = datetime.combine(session_date, CAPTURE_CLOSE, NEW_YORK).astimezone(timezone.utc)
    return open_at, close_at


# ---------------------------------------------------------------- inputs

def read_causal_symbols(root: Path, epoch: str, session_date: date) -> list[str]:
    path = root / "causal_list" / epoch / f"{session_date.isoformat()}.json"
    try:
        envelope = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ProducerError("CAUSAL_LIST_UNREADABLE") from exc
    commitment = envelope.get("commitment") if isinstance(envelope, dict) else None
    if not isinstance(commitment, dict):
        raise ProducerError("CAUSAL_LIST_INVALID")
    symbols = commitment.get("list")
    if (not isinstance(symbols, list) or not symbols or len(symbols) > MAX_SYMBOLS
            or any(not isinstance(s, str) or not s for s in symbols) or len(set(symbols)) != len(symbols)
            or commitment.get("session") != session_date.isoformat() or commitment.get("epoch") != epoch):
        raise ProducerError("CAUSAL_LIST_INVALID")
    return [str(s) for s in symbols]


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class Components:
    daily: Mapping[str, Mapping[str, Any]]
    risk: Mapping[str, Mapping[str, Any]]
    earnings: Mapping[str, Mapping[str, Any]]
    registry: Mapping[str, Mapping[str, Any]]


def load_components(root: Path, session_date: date, symbols: list[str]) -> Components:
    base = root / "components" / session_date.isoformat()
    daily: dict[str, Mapping[str, Any]] = {}
    for symbol in symbols:
        item = _read_json(base / "daily_61" / f"{symbol}.json")
        if isinstance(item, dict) and item.get("symbol") == symbol and isinstance(item.get("daily"), dict):
            daily[symbol] = item["daily"]
    risk = _read_json(base / "risk.json")
    earnings = _read_json(base / "earnings.json")
    registry_file = _read_json(base / "registry.json")
    registry: dict[str, Mapping[str, Any]] = {}
    if isinstance(registry_file, dict):
        for row in registry_file.get("instruments", []):
            if isinstance(row, dict) and isinstance(row.get("symbol"), str):
                registry[row["symbol"]] = row
    return Components(daily=daily, risk=risk if isinstance(risk, dict) else {}, earnings=earnings if isinstance(earnings, dict) else {}, registry=registry)


# ---------------------------------------------------------------- quote state

@dataclass
class Quote:
    bid: float | None
    ask: float | None
    tick_at: datetime
    received_at: datetime
    raw: str


@dataclass
class QuoteBook:
    """Latest quote per symbol from the raw tick tape; later ticks never regress the clock."""
    quotes: dict[str, Quote] = field(default_factory=dict)
    tape: list[str] = field(default_factory=list)
    updates: dict[str, int] = field(default_factory=dict)

    def record(self, payload: str, received_at: datetime, allowed: set[str]) -> str | None:
        self.tape.append(payload)
        try:
            item = json.loads(payload)
        except ValueError:
            return None
        if not isinstance(item, dict):
            return None
        symbol = str(item.get("s") or "").strip().upper()
        if symbol not in allowed:
            return None
        stamp = item.get("t")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            return None
        tick_ms = int(stamp)
        if tick_ms <= 0:
            return None
        bid = item.get("bp") if isinstance(item.get("bp"), (int, float)) and not isinstance(item.get("bp"), bool) else None
        ask = item.get("ap") if isinstance(item.get("ap"), (int, float)) and not isinstance(item.get("ap"), bool) else None
        tick_at = datetime.fromtimestamp(tick_ms / 1000, tz=timezone.utc)
        current = self.quotes.get(symbol)
        if current is not None and tick_at < current.tick_at:
            return None
        self.quotes[symbol] = Quote(float(bid) if bid is not None and bid > 0 else None,
                                    float(ask) if ask is not None and ask > 0 else None, tick_at, received_at, payload)
        self.updates[symbol] = self.updates.get(symbol, 0) + 1
        return symbol

    def tape_sha256(self) -> str:
        return hashlib.sha256("\n".join(self.tape).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- snapshot assembly (pure)

def _invalid_risk(now_iso: str) -> dict[str, Any]:
    return {"value": None, "producer": "component-missing", "source_at": now_iso, "available_at": now_iso}


def _invalid_earnings(now_iso: str) -> dict[str, Any]:
    return {"coverage_verified": False, "window_start": now_iso, "window_end": now_iso, "events": [], "source_at": now_iso, "available_at": now_iso}


def _invalid_daily(now_iso: str) -> dict[str, Any]:
    return {"bars": [], "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": False, "split_coverage_verified": False,
            "source_at": now_iso, "available_at": now_iso}


def assemble_snapshot(symbols: list[str], book: QuoteBook, components: Components, *, now: datetime, sequence: int) -> dict[str, Any]:
    """One complete universe row per listed symbol; nulls where no quote yet; components as prepared."""
    now_iso = _iso(now)
    instruments = []
    for symbol in symbols:
        quote = book.quotes.get(symbol)
        registry = components.registry.get(symbol, {})
        market = registry.get("market") if isinstance(registry.get("market"), str) else None
        security_type = registry.get("security_type") if isinstance(registry.get("security_type"), str) else None
        row: dict[str, Any] = {
            "symbol": symbol,
            "market": market,
            "security_type": security_type,
            "classification_verified": registry.get("classification_verified") is True,
            "sequence": book.updates.get(symbol, 0),
            "source_at": _iso(quote.tick_at) if quote else now_iso,
            "available_at": now_iso,
            "quote": ({"bid": quote.bid, "ask": quote.ask, "bid_source_at": _iso(quote.tick_at), "ask_source_at": _iso(quote.tick_at),
                       "received_at": _iso(quote.received_at), "available_at": now_iso} if quote else
                      {"bid": None, "ask": None, "bid_source_at": None, "ask_source_at": None, "received_at": None, "available_at": now_iso}),
            "daily": dict(components.daily.get(symbol) or _invalid_daily(now_iso)),
            "risk": dict(components.risk.get(symbol) or _invalid_risk(now_iso)),
            "earnings": dict(components.earnings.get(symbol) or _invalid_earnings(now_iso)),
        }
        instruments.append(row)
    body = {
        "schema": SNAPSHOT_SCHEMA, "manifest_sha": MANIFEST_SHA, "amendment_sha": AMENDMENT_SHA,
        "source_id": "fable-eodhd-us-quote-snapshot",
        "provenance": {"producer": PRODUCER, "version": PRODUCER_VERSION, "payload_sha256": book.tape_sha256()},
        "source_at": _iso(min((q.tick_at for q in book.quotes.values()), default=now)),
        "available_at": now_iso, "sequence": sequence,
        "universe": {"coverage_verified": True, "instruments": instruments},
    }
    body["self_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


# ---------------------------------------------------------------- feed and loop

TickSource = Callable[[list[str]], AsyncIterator[tuple[str, datetime]]]


async def eodhd_quote_ticks(symbols: list[str], *, token: str, stop_at: datetime) -> AsyncIterator[tuple[str, datetime]]:
    """Raw `us-quote` payloads with local receipt instants; reconnects until stop_at."""
    import websockets
    url = f"wss://ws.eodhistoricaldata.com/ws/us-quote?api_token={token}"
    while datetime.now(timezone.utc) < stop_at:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=2, max_size=1_000_000) as socket:
                authorization = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
                if authorization.get("status_code", authorization.get("status")) != 200:
                    raise ProducerError("QUOTE_FEED_AUTHORIZATION_FAILED")
                await socket.send(json.dumps({"action": "subscribe", "symbols": ",".join(symbols)}))
                while datetime.now(timezone.utc) < stop_at:
                    try:
                        payload = await asyncio.wait_for(socket.recv(), timeout=1)
                    except TimeoutError:
                        continue
                    received = datetime.now(timezone.utc)
                    yield (payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)), received
        except ProducerError:
            raise
        except Exception:  # network errors: reconnect without exposing the URL
            await asyncio.sleep(1)


async def run_capture(*, root: Path, epoch: str, session_date: date, symbols: list[str], components: Components,
                      ticks: TickSource, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, publish_interval: float = PUBLISH_INTERVAL_SECONDS) -> dict[str, Any]:
    """Consume ticks from warm-up to the window close; publish snapshot.json inside the window."""
    open_at, close_at = capture_window(session_date)
    book = QuoteBook()
    allowed = set(symbols)
    sequence = 0
    published: list[dict[str, Any]] = []
    tape_path = root / "tape" / f"{session_date.isoformat()}.us-quote.ndjson"
    tape_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(tape_path.parent, 0o700)
    tape_fd = os.open(tape_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    tape = os.fdopen(tape_fd, "a", encoding="utf-8")
    next_publish = open_at
    stopped = False

    async def consume() -> None:
        nonlocal stopped
        async for payload, received in ticks(symbols):
            tape.write(json.dumps({"received_at": _iso(received), "payload": payload}) + "\n")
            book.record(payload, received, allowed)
            if clock() >= close_at:
                break
        stopped = True

    consumer = asyncio.ensure_future(consume())
    try:
        while True:
            now = clock()
            if now >= close_at or stopped:
                break
            if now >= next_publish and now < close_at:
                sequence += 1
                body = assemble_snapshot(symbols, book, components, now=now, sequence=sequence)
                digest = write_private(root / "snapshot.json", canonical(body))
                published.append({"sequence": sequence, "available_at": body["available_at"], "sha256": digest,
                                  "quoted": sum(1 for s in symbols if s in book.quotes), "self_sha256": body["self_sha256"]})
                next_publish = now + timedelta(seconds=publish_interval)
            await sleep(0.05)
    finally:
        consumer.cancel()
        try:
            await consumer
        except (asyncio.CancelledError, Exception):
            pass
        tape.flush()
        os.fsync(tape.fileno())
        tape.close()
    return {"epoch": epoch, "session_date": session_date.isoformat(), "symbols": len(symbols), "published": published,
            "tape_sha256": book.tape_sha256(), "tape_file": str(tape_path), "quoted_symbols": sum(1 for s in symbols if s in book.quotes),
            "window": [_iso(open_at), _iso(close_at)]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--root", required=True, help="private epoch root of the file port")
    args = parser.parse_args(argv)
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    from .config import get_settings
    settings = get_settings()
    if not settings.eodhd_api_token.strip():
        raise ProducerError("PROVIDER_TOKEN_MISSING")
    root, epoch, session_date = Path(args.root), args.epoch, date.fromisoformat(args.session_date)
    symbols = read_causal_symbols(root, epoch, session_date)
    components = load_components(root, session_date, symbols)
    open_at, close_at = capture_window(session_date)
    start_at = open_at - timedelta(seconds=WARMUP_SECONDS)
    now = datetime.now(timezone.utc)
    if now >= close_at:
        raise ProducerError("CAPTURE_WINDOW_ALREADY_CLOSED")
    if now < start_at:
        import time as _time
        _time.sleep((start_at - now).total_seconds())
    token = settings.eodhd_api_token

    def ticks(names: list[str]) -> AsyncIterator[tuple[str, datetime]]:
        return eodhd_quote_ticks(names, token=token, stop_at=close_at)

    result = asyncio.run(run_capture(root=root, epoch=epoch, session_date=session_date, symbols=symbols, components=components, ticks=ticks))
    result["status"] = "CAPTURED"
    print(json.dumps({k: v for k, v in result.items() if k != "published"} | {"publications": len(result["published"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
