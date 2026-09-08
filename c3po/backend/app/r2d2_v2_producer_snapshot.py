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
  the assembly instant of the snapshot that carries it. A tick is accepted only
  with a finite, positive clock not later than its receipt; anything else is
  rejected with a counted reason and never replaces the last causal quote;
- `daily` from `components/<D>/daily_61/<symbol>.json` (producer 1/3), `risk`
  from `components/<D>/risk.json` (`V2_RISK_COMPONENTS_V1`: `{schema,
  session_date, symbols:{SYMBOL:{value, producer, source_at, available_at}}}`)
  and `earnings` from `components/<D>/earnings.json` (producer 3/3,
  `V2_EARNINGS_COMPONENTS_V2`). Component files are re-read at every publication
  (unchanged files are not re-parsed), so a response that lands during the
  window is carried by the next snapshot. A component that has NOT arrived is
  published as PENDING: exact port fields, `source_at = available_at = null`,
  so the collector's `input_complete` stays false and the name stays pending;
  the assembly clock is never used as a component receipt. A component that
  arrived and concluded invalid (e.g. `coverage_verified = false` with its own
  clocks) is passed through unchanged;
- publication by private atomic rename roughly once per second inside
  [10:00:00, 10:01:00) New York, envelope `sequence` increasing, raw tick tape
  kept in a private NDJSON file whose SHA-256 is the `provenance.payload_sha256`;
- the tick consumer is supervised: a failure is reported in the result and the
  run is not declared `CAPTURED`.

No eligibility decision, no order, no access to the V1 engine or its stream.
OFF by default (`C3PO_R2D2_V2_PRODUCERS_ENABLED=true` required). The provider
token is used only to open the websocket and never written anywhere.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .r2d2_v2_producer_daily import COMPONENT_SCHEMA as DAILY_COMPONENT_SCHEMA, REGISTRY_SCHEMA, ProducerError, canonical, write_private
from .r2d2_v2_producer_earnings import COMPONENT_KEYS as EARNINGS_KEYS, SCHEMA as EARNINGS_SCHEMA

PRODUCER = "fable-eodhd-snapshot"
PRODUCER_VERSION = "v3"
SNAPSHOT_SCHEMA = "V2_SHADOW_SOURCE_SNAPSHOT_V2"
RISK_SCHEMA = "V2_RISK_COMPONENTS_V1"
MANIFEST_SHA = "eabbe18057b7e5823535dd61e93c5190b33f8c7ac80b9118229b7908f974f4d0"
AMENDMENT_SHA = "3a25b9929d0c65aa97fe90b9c9cfc7dd904fedde23df884e8e42f199ae2e5ff4"
NEW_YORK = ZoneInfo("America/New_York")
CAPTURE_OPEN = time(10, 0)
CAPTURE_CLOSE = time(10, 1)
WARMUP_SECONDS = 30
PUBLISH_INTERVAL_SECONDS = 1.0
MAX_SYMBOLS = 550
DAILY_KEYS = frozenset({"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"})
RISK_KEYS = frozenset({"value", "producer", "source_at", "available_at"})
STATUS_CAPTURED = "CAPTURED"
STATUS_EMPTY = "CAPTURE_EMPTY"
STATUS_DEGRADED = "CAPTURE_DEGRADED_CONSUMER_FAILED"


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


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


Reader = Callable[[Path], Any]


@dataclass(frozen=True)
class Components:
    """Per-symbol component responses. A key present with an invalid shape is a CONCLUDED invalid response
    (passed through unchanged, with a diagnostic); a key absent is a response that has not arrived (PENDING)."""
    daily: Mapping[str, Any]
    risk: Mapping[str, Any]
    earnings: Mapping[str, Any]
    registry: Mapping[str, Mapping[str, Any]]
    diagnostics: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def diagnostic_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for codes in self.diagnostics.values():
            for code in codes:
                counts[code] = counts.get(code, 0) + 1
        return counts


def _component_map(document: Any, *, schema: str, session: str, keys: frozenset[str], symbols: Sequence[str], label: str,
                   note: Callable[[str, str], None]) -> dict[str, Any]:
    """A document that is not attributable to this session (absent, other schema/session) means no response yet.
    A response present for the symbol is concluded, valid or not: it is passed through unchanged, never replaced by PENDING."""
    if document is None:
        for symbol in symbols:
            note(symbol, f"{label}_COMPONENT_ABSENT")
        return {}
    if not (isinstance(document, dict) and document.get("schema") == schema and document.get("session_date") == session
            and isinstance(document.get("symbols"), dict)):
        for symbol in symbols:
            note(symbol, f"{label}_DOCUMENT_INVALID")
        return {}
    result: dict[str, Any] = {}
    for symbol in symbols:
        if symbol not in document["symbols"]:
            note(symbol, f"{label}_COMPONENT_ABSENT")
            continue
        component = document["symbols"][symbol]
        if not isinstance(component, dict) or set(component) != keys:
            note(symbol, f"{label}_COMPONENT_INVALID")
        result[symbol] = component
    return result


def load_components(root: Path, session_date: date, symbols: Sequence[str], *, read: Reader = _read_json) -> Components:
    """Component responses for the listed symbols; every absence or invalid response is a per-symbol diagnostic."""
    base = root / "components" / session_date.isoformat()
    session = session_date.isoformat()
    diagnostics: dict[str, list[str]] = {}

    def note(symbol: str, code: str) -> None:
        diagnostics.setdefault(symbol, []).append(code)

    daily: dict[str, Any] = {}
    for symbol in symbols:
        item = read(base / "daily_61" / f"{symbol}.json")
        if item is None:
            note(symbol, "DAILY_COMPONENT_ABSENT")
            continue
        if not (isinstance(item, dict) and item.get("schema") == DAILY_COMPONENT_SCHEMA and item.get("symbol") == symbol and "daily" in item):
            note(symbol, "DAILY_DOCUMENT_INVALID")  # not attributable to this symbol: no response
            continue
        component = item["daily"]
        if not isinstance(component, dict) or set(component) != DAILY_KEYS:
            note(symbol, "DAILY_COMPONENT_INVALID")
        daily[symbol] = component
    risk = _component_map(read(base / "risk.json"), schema=RISK_SCHEMA, session=session, keys=RISK_KEYS, symbols=symbols, label="RISK", note=note)
    earnings = _component_map(read(base / "earnings.json"), schema=EARNINGS_SCHEMA, session=session, keys=EARNINGS_KEYS, symbols=symbols,
                              label="EARNINGS", note=note)
    registry_file = read(base / "registry.json")
    registry: dict[str, Mapping[str, Any]] = {}
    if isinstance(registry_file, dict) and registry_file.get("schema") == REGISTRY_SCHEMA and isinstance(registry_file.get("instruments"), list):
        for row in registry_file["instruments"]:
            if isinstance(row, dict) and isinstance(row.get("symbol"), str):
                registry[row["symbol"]] = row
    for symbol in symbols:
        if symbol not in registry:
            note(symbol, "REGISTRY_ROW_ABSENT")
    return Components(daily=daily, risk=risk, earnings=earnings, registry=registry,
                      diagnostics={symbol: tuple(codes) for symbol, codes in diagnostics.items()})


class ComponentLoader:
    """Re-reads the component files on every call; a file with the same inode, size and mtime is not re-parsed."""

    def __init__(self, root: Path, session_date: date, symbols: Sequence[str]) -> None:
        self.root, self.session_date, self.symbols = root, session_date, list(symbols)
        self._cache: dict[Path, tuple[tuple[int, int, int], Any]] = {}

    def read(self, path: Path) -> Any | None:
        try:
            stat = os.stat(path)
        except OSError:
            self._cache.pop(path, None)
            return None
        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        value = _read_json(path)
        self._cache[path] = (signature, value)
        return value

    def __call__(self) -> Components:
        return load_components(self.root, self.session_date, self.symbols, read=self.read)


# ---------------------------------------------------------------- quote state

@dataclass
class Quote:
    bid: float | None
    ask: float | None
    tick_at: datetime
    received_at: datetime
    raw: str


def _price(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


@dataclass
class QuoteBook:
    """Latest causal quote per symbol from the raw tick tape; invalid or future ticks never replace it."""
    quotes: dict[str, Quote] = field(default_factory=dict)
    tape: list[str] = field(default_factory=list)
    updates: dict[str, int] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=dict)

    def _reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def record(self, payload: str, received_at: datetime, allowed: set[str]) -> str | None:
        self.tape.append(payload)
        try:
            return self._record(payload, received_at, allowed)
        except Exception:  # one payload can never stop the consumer; the reason is counted
            self._reject("PAYLOAD_ERROR")
            return None

    def _record(self, payload: str, received_at: datetime, allowed: set[str]) -> str | None:
        try:
            item = json.loads(payload)
        except ValueError:
            self._reject("NOT_JSON")
            return None
        if not isinstance(item, dict):
            self._reject("NOT_OBJECT")
            return None
        symbol = str(item.get("s") or "").strip().upper()
        if symbol not in allowed:
            self._reject("SYMBOL_NOT_LISTED")
            return None
        stamp = item.get("t")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= 0:
            self._reject("TICK_CLOCK_INVALID")
            return None
        tick_at = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
        if tick_at > received_at:
            self._reject("TICK_IN_FUTURE")
            return None
        current = self.quotes.get(symbol)
        if current is not None and tick_at < current.tick_at:
            self._reject("TICK_REGRESSES")
            return None
        self.quotes[symbol] = Quote(_price(item.get("bp")), _price(item.get("ap")), tick_at, received_at, payload)
        self.updates[symbol] = self.updates.get(symbol, 0) + 1
        return symbol

    def tape_sha256(self) -> str:
        return hashlib.sha256("\n".join(self.tape).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- snapshot assembly (pure)

def pending_daily() -> dict[str, Any]:
    return {"bars": [], "splits": [], "adjustment": "RAW_UNADJUSTED", "coverage_verified": False, "split_coverage_verified": False,
            "source_at": None, "available_at": None}


def pending_risk() -> dict[str, Any]:
    return {"value": None, "producer": "component-pending", "source_at": None, "available_at": None}


def pending_earnings() -> dict[str, Any]:
    return {"coverage_verified": False, "window_start": None, "window_end": None, "events": [], "source_at": None, "available_at": None,
            "policy": None, "evidence": None, "exclusion": None}


def _present(value: Any, pending: Callable[[], dict[str, Any]]) -> Any:
    """A concluded response is carried as it came (valid or not); only a response that has not arrived is PENDING."""
    if value is None:
        return pending()
    return dict(value) if isinstance(value, dict) else value


def assemble_snapshot(symbols: Sequence[str], book: QuoteBook, components: Components, *, now: datetime, sequence: int) -> dict[str, Any]:
    """One complete universe row per listed symbol; nulls where no quote yet; components as they arrived or PENDING."""
    now_iso = _iso(now)
    instruments = []
    for symbol in symbols:
        quote = book.quotes.get(symbol)
        registry = components.registry.get(symbol, {})
        market = registry.get("market") if isinstance(registry.get("market"), str) else None
        security_type = registry.get("security_type") if isinstance(registry.get("security_type"), str) else None
        daily = components.daily.get(symbol)
        risk = components.risk.get(symbol)
        earnings = components.earnings.get(symbol)
        # Row clocks describe this row: earliest source clock among its present pieces, else the assembly instant.
        clocks = [quote.tick_at] if quote else []
        clocks.extend(at for at in (_parse(component.get("source_at")) for component in (daily, risk, earnings) if isinstance(component, dict))
                      if at is not None)
        row: dict[str, Any] = {
            "symbol": symbol,
            "market": market,
            "security_type": security_type,
            "classification_verified": registry.get("classification_verified") is True,
            "sequence": book.updates.get(symbol, 0),
            "source_at": _iso(min(clocks)) if clocks else now_iso,
            "available_at": now_iso,
            "quote": ({"bid": quote.bid, "ask": quote.ask, "bid_source_at": _iso(quote.tick_at), "ask_source_at": _iso(quote.tick_at),
                       "received_at": _iso(quote.received_at), "available_at": now_iso} if quote else
                      {"bid": None, "ask": None, "bid_source_at": None, "ask_source_at": None, "received_at": None, "available_at": now_iso}),
            "daily": _present(daily, pending_daily),
            "risk": _present(risk, pending_risk),
            "earnings": _present(earnings, pending_earnings),
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
ComponentSource = Components | Callable[[], Components]


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


async def run_capture(*, root: Path, epoch: str, session_date: date, symbols: list[str], components: ComponentSource,
                      ticks: TickSource, clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, publish_interval: float = PUBLISH_INTERVAL_SECONDS) -> dict[str, Any]:
    """Consume ticks from warm-up to the window close; publish snapshot.json inside the window with freshly loaded components."""
    open_at, close_at = capture_window(session_date)
    load: Callable[[], Components] = components if callable(components) else (lambda: components)  # type: ignore[assignment]
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
    consumer_error: str | None = None
    last_components: Components | None = None

    async def consume() -> None:
        async for payload, received in ticks(symbols):
            tape.write(json.dumps({"received_at": _iso(received), "payload": payload}) + "\n")
            book.record(payload, received, allowed)
            if clock() >= close_at:
                break

    consumer = asyncio.ensure_future(consume())
    try:
        while True:
            now = clock()
            if now >= close_at:
                break
            if consumer_error is None and consumer.done() and not consumer.cancelled() and consumer.exception() is not None:
                consumer_error = type(consumer.exception()).__name__
            if now >= next_publish:
                sequence += 1
                last_components = load()
                body = assemble_snapshot(symbols, book, last_components, now=now, sequence=sequence)
                digest = write_private(root / "snapshot.json", canonical(body))
                published.append({"sequence": sequence, "available_at": body["available_at"], "sha256": digest,
                                  "quoted": sum(1 for s in symbols if s in book.quotes), "self_sha256": body["self_sha256"],
                                  "component_diagnostics": last_components.diagnostic_counts()})
                next_publish = now + timedelta(seconds=publish_interval)
            await sleep(0.05)
    finally:
        # The consumer's fate is read AFTER it has finished: a failure between the last inspection and the
        # cutoff is a failure, an intentional cancellation is not.
        if not consumer.done():
            consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            consumer_error = consumer_error or type(exc).__name__
        tape.flush()
        os.fsync(tape.fileno())
        tape.close()
    status = STATUS_DEGRADED if consumer_error else (STATUS_CAPTURED if published else STATUS_EMPTY)
    return {"epoch": epoch, "session_date": session_date.isoformat(), "symbols": len(symbols), "published": published,
            "status": status, "consumer_error": consumer_error, "rejected_ticks": dict(book.rejected),
            "tape_sha256": book.tape_sha256(), "tape_file": str(tape_path), "quoted_symbols": sum(1 for s in symbols if s in book.quotes),
            "component_diagnostics": {symbol: list(codes) for symbol, codes in (last_components.diagnostics.items() if last_components else [])},
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
    loader = ComponentLoader(root, session_date, symbols)
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

    result = asyncio.run(run_capture(root=root, epoch=epoch, session_date=session_date, symbols=symbols, components=loader, ticks=ticks))
    summary = {k: v for k, v in result.items() if k not in ("published", "component_diagnostics")}
    summary["publications"] = len(result["published"])
    summary["component_diagnostics"] = result["published"][-1]["component_diagnostics"] if result["published"] else {}
    print(json.dumps(summary, sort_keys=True))
    return 0 if result["status"] == STATUS_CAPTURED else 1


if __name__ == "__main__":
    raise SystemExit(main())
