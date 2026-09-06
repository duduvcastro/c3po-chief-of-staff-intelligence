"""R2D2 V2 — daily-data producer for the causal list and the 61-bar admission gate (EODHD, RAW).

Produces private JSON files for the V2 file port (contract `R2D2_V2_DATA_PORT_V1.md`,
revision 2, of the shadow generator) from the provider's end-of-day endpoints:

- `V2_CAUSAL_REGISTRY_V1`: the provider's US exchange symbol list captured after
  the official close of D-1, restricted to NYSE/NASDAQ, with the provider's
  instrument type mapped to the contract vocabulary (`COMMON_STOCK`, `ETF`, ...).
  ADR is not distinguishable in the provider's list; common stocks are reported
  as `COMMON_STOCK` and this limitation is declared in the file.
- `V2_CAUSAL_DAILY_CONTRACT_V1`: for every registry symbol, the raw OHLCV bars of
  the last 20 official sessions up to D-1 (bulk end-of-day endpoint, one call per
  session) and the splits effective inside that window (bulk splits endpoint),
  `adjustment = RAW_UNADJUSTED`, per-bar `source_at`/`available_at` = the receipt
  instant of the provider response that contained the bar.
- Per-instrument `daily` components (61 official sessions + full split history)
  for the names of a causal list, consumed by the 10:00 ET snapshot assembler.

Nothing here decides eligibility, builds the list, publishes receipts or opens a
websocket. Timestamps are receipt instants observed by this producer, never
inferred from session dates or file times. The provider token is read from the
application settings and never written to files, logs or error messages. OFF by
default: the CLI refuses to run unless `C3PO_R2D2_V2_PRODUCERS_ENABLED=true`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

PRODUCER = "fable-eodhd-daily"
PRODUCER_VERSION = "v1"
REGISTRY_SCHEMA = "V2_CAUSAL_REGISTRY_V1"
DAILY_SCHEMA = "V2_CAUSAL_DAILY_CONTRACT_V1"
COMPONENT_SCHEMA = "V2_INSTRUMENT_DAILY_COMPONENT_V1"
NEW_YORK = ZoneInfo("America/New_York")
ALLOWED_EXCHANGES = ("NYSE", "NASDAQ")
TYPE_MAP = {
    "Common Stock": "COMMON_STOCK", "ETF": "ETF", "Preferred Stock": "PREFERRED_STOCK", "Warrant": "WARRANT",
    "FUND": "FUND", "Mutual Fund": "MUTUAL_FUND", "Unit": "UNIT", "Notes": "NOTE", "ETC": "ETC", "BOND": "BOND", "INDEX": "INDEX",
}
LIQUIDITY_SESSIONS = 20
ATR_SESSIONS = 61
SYMBOL_RE_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


class ProducerError(RuntimeError):
    """Controlled message only; provider tokens and raw payloads are never included."""


# ---------------------------------------------------------------- calendar (XNYS, official sessions)

def xnys_sessions_ending(last_session: date, count: int) -> tuple[date, ...]:
    """The `count` official XNYS sessions ending at `last_session` inclusive; `last_session` must be a session."""
    import exchange_calendars
    calendar = exchange_calendars.get_calendar("XNYS")
    if not calendar.is_session(last_session.isoformat()):
        raise ProducerError("LAST_SESSION_NOT_OFFICIAL")
    window = calendar.sessions_window(last_session.isoformat(), -count)
    sessions = tuple(stamp.date() for stamp in window)
    if len(sessions) != count or sessions[-1] != last_session:
        raise ProducerError("CALENDAR_WINDOW_INVALID")
    return sessions


def previous_session(day: date) -> date:
    import exchange_calendars
    calendar = exchange_calendars.get_calendar("XNYS")
    session = calendar.date_to_session(day.isoformat(), direction="previous")
    if session.date() == day and calendar.is_session(day.isoformat()):
        session = calendar.previous_session(session)
    return session.date()


def session_open(day: date) -> datetime:
    import exchange_calendars
    calendar = exchange_calendars.get_calendar("XNYS")
    return calendar.session_open(day.isoformat()).to_pydatetime().astimezone(timezone.utc)


def session_close(day: date) -> datetime:
    import exchange_calendars
    calendar = exchange_calendars.get_calendar("XNYS")
    return calendar.session_close(day.isoformat()).to_pydatetime().astimezone(timezone.utc)


# ---------------------------------------------------------------- provider transport (raw bytes + receipt instant)

@dataclass(frozen=True)
class Response:
    payload: bytes
    received_at: datetime
    url_path: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()

    def json(self) -> Any:
        try:
            return json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProducerError(f"PROVIDER_JSON_INVALID:{self.url_path}") from exc


Fetcher = Callable[[str, Mapping[str, str]], Response]


class EodhdFetcher:
    """GET with retries; returns exact bytes and the receipt instant. The token never leaves this object."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 60.0, retries: int = 2, sleep: Callable[[float], None] = time.sleep) -> None:
        if not token.strip():
            raise ProducerError("PROVIDER_TOKEN_MISSING")
        self._base = base_url.rstrip("/")
        self._token = token.strip()
        self._timeout, self._retries, self._sleep = timeout, retries, sleep

    def __call__(self, path: str, params: Mapping[str, str]) -> Response:
        import httpx
        query = {**params, "api_token": self._token, "fmt": "json"}
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = httpx.get(self._base + path, params=query, timeout=self._timeout, follow_redirects=True)
                response.raise_for_status()
                return Response(response.content, datetime.now(timezone.utc), path)
            except httpx.HTTPError as exc:  # never include the URL (it carries the token)
                last = exc
                if attempt < self._retries:
                    self._sleep(0.5 * (2 ** attempt))
        raise ProducerError(f"PROVIDER_REQUEST_FAILED:{path}:{type(last).__name__}")


# ---------------------------------------------------------------- helpers

def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _symbol_ok(code: Any) -> bool:
    return isinstance(code, str) and 1 <= len(code) <= 20 and code[0] in set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") and all(c in SYMBOL_RE_ALLOWED for c in code)


def parse_split_factor(text: Any) -> float | None:
    """EODHD split text 'new/old' (e.g. '4.000000/1.000000') -> new/old as float, None if invalid."""
    if not isinstance(text, str) or "/" not in text:
        return None
    left, _, right = text.partition("/")
    try:
        new, old = Decimal(left.strip()), Decimal(right.strip())
    except (InvalidOperation, ValueError):
        return None
    if new <= 0 or old <= 0:
        return None
    return float(Fraction(new) / Fraction(old))


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def write_private(path: Path, payload: bytes) -> str:
    """Atomic private publication: private temp in the same directory, fsync, rename, directory fsync."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temp = path.with_name("." + path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------- registry (V2_CAUSAL_REGISTRY_V1)

def build_registry(response: Response, *, previous_close: datetime) -> dict[str, Any]:
    """Map the provider's US symbol list to the registry contract; only NYSE/NASDAQ rows are kept."""
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise ProducerError("REGISTRY_EMPTY")
    if response.received_at <= previous_close:
        raise ProducerError("REGISTRY_CAPTURED_BEFORE_CLOSE")
    instruments = []
    seen: set[str] = set()
    counts = {"provider_rows": len(rows), "kept": 0, "skipped_exchange": 0, "skipped_symbol": 0, "duplicates": 0}
    for row in rows:
        if not isinstance(row, dict) or row.get("Exchange") not in ALLOWED_EXCHANGES:
            counts["skipped_exchange"] += 1
            continue
        code = row.get("Code")
        if not _symbol_ok(code):
            counts["skipped_symbol"] += 1
            continue
        assert isinstance(code, str)
        if code in seen:
            counts["duplicates"] += 1
            continue
        seen.add(code)
        provider_type = row.get("Type")
        security_type = TYPE_MAP.get(provider_type if isinstance(provider_type, str) else "", "OTHER")
        instruments.append({"symbol": code, "market": row["Exchange"], "security_type": security_type, "classification_verified": True})
        counts["kept"] += 1
    instruments.sort(key=lambda item: item["symbol"])
    stamp = _iso(response.received_at)
    return {"schema": REGISTRY_SCHEMA, "source_id": "eodhd-exchange-symbol-list-US", "source_at": stamp, "available_at": stamp,
            "captured_at": stamp, "coverage_verified": True, "instruments": instruments,
            "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "provider_payload_sha256": response.sha256,
                              "adr_distinction": "NOT_AVAILABLE_IN_PROVIDER_LIST: common stocks reported as COMMON_STOCK",
                              "counts": counts}}


# ---------------------------------------------------------------- daily contract (V2_CAUSAL_DAILY_CONTRACT_V1)

def _bar(item: Mapping[str, Any], session: date, received_at: datetime) -> dict[str, Any] | None:
    values = [_number(item.get(key)) for key in ("open", "high", "low", "close", "volume")]
    if any(value is None for value in values):
        return None
    open_, high, low, close, volume = values
    assert open_ is not None and high is not None and low is not None and close is not None and volume is not None
    if min(open_, high, low, close) <= 0 or volume < 0 or not low <= min(open_, close) <= max(open_, close) <= high:
        return None
    stamp = _iso(received_at)
    return {"session_date": session.isoformat(), "open": open_, "high": high, "low": low, "close": close, "volume": volume,
            "source_at": stamp, "available_at": stamp, "complete": True, "regular_session": True}


def build_daily_contract(registry: Mapping[str, Any], bulk_by_session: Mapping[date, Response],
                         splits_by_session: Mapping[date, Response], *, sessions: Sequence[date], previous_close: datetime) -> dict[str, Any]:
    """Assemble the 20-session raw bars and window splits for every registry symbol."""
    if tuple(sessions) != tuple(sorted(set(sessions))) or len(sessions) != LIQUIDITY_SESSIONS:
        raise ProducerError("LIQUIDITY_WINDOW_INVALID")
    if set(bulk_by_session) != set(sessions) or set(splits_by_session) != set(sessions):
        raise ProducerError("BULK_RESPONSES_INCOMPLETE")
    symbols = [item["symbol"] for item in registry["instruments"]]
    bars: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    splits: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    latest_receipt = previous_close
    for session in sessions:
        response = bulk_by_session[session]
        if response.received_at <= session_close(session):
            raise ProducerError("BULK_RECEIVED_BEFORE_SESSION_CLOSE")
        latest_receipt = max(latest_receipt, response.received_at)
        rows = response.json()
        if not isinstance(rows, list):
            raise ProducerError("BULK_PAYLOAD_INVALID")
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = row.get("code")
            if not isinstance(code, str) or code not in bars or row.get("date") != session.isoformat():
                continue
            bar = _bar(row, session, response.received_at)
            if bar is not None:
                bars[code].append(bar)
        split_response = splits_by_session[session]
        latest_receipt = max(latest_receipt, split_response.received_at)
        split_rows = split_response.json()
        if not isinstance(split_rows, list):
            raise ProducerError("BULK_SPLITS_PAYLOAD_INVALID")
        for row in split_rows:
            if not isinstance(row, dict):
                continue
            code = row.get("code")
            factor = parse_split_factor(row.get("split"))
            if not isinstance(code, str) or code not in splits or factor is None or row.get("date") != session.isoformat():
                continue
            stamp = _iso(split_response.received_at)
            splits[code].append({"factor": factor, "effective_at": _iso(session_open(session)), "source_at": stamp, "available_at": stamp})
    stamp = _iso(latest_receipt)
    instruments = []
    for symbol in symbols:
        instruments.append({"symbol": symbol, "daily": {
            "bars": bars[symbol], "splits": splits[symbol], "adjustment": "RAW_UNADJUSTED",
            "coverage_verified": True, "split_coverage_verified": True, "source_at": stamp, "available_at": stamp}})
    return {"schema": DAILY_SCHEMA, "source_id": "eodhd-eod-bulk-last-day-US", "source_at": stamp, "available_at": stamp,
            "instruments": instruments,
            "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "sessions": [s.isoformat() for s in sessions],
                              "bulk_payload_sha256": {s.isoformat(): bulk_by_session[s].sha256 for s in sessions},
                              "splits_payload_sha256": {s.isoformat(): splits_by_session[s].sha256 for s in sessions},
                              "split_effective_convention": "official session open of the provider's split date",
                              "complete_bars": sum(len(bars[s]) == LIQUIDITY_SESSIONS for s in symbols), "symbols": len(symbols)}}


# ---------------------------------------------------------------- per-instrument 61-bar component (snapshot input)

def build_instrument_component(symbol: str, eod: Response, splits: Response, *, sessions: Sequence[date]) -> dict[str, Any]:
    """The `daily` component of one snapshot instrument: exactly the 61 official sessions, full split history."""
    if len(sessions) != ATR_SESSIONS:
        raise ProducerError("ATR_WINDOW_INVALID")
    rows = eod.json()
    if not isinstance(rows, list):
        raise ProducerError("EOD_PAYLOAD_INVALID")
    by_date = {row.get("date"): row for row in rows if isinstance(row, dict) and isinstance(row.get("date"), str)}
    bars = []
    missing = []
    for session in sessions:
        row = by_date.get(session.isoformat())
        bar = _bar(row, session, eod.received_at) if row is not None else None
        if bar is None:
            missing.append(session.isoformat())
        else:
            bars.append(bar)
    split_rows = splits.json()
    if not isinstance(split_rows, list):
        raise ProducerError("SPLITS_PAYLOAD_INVALID")
    split_items = []
    for row in split_rows:
        if not isinstance(row, dict):
            continue
        factor = parse_split_factor(row.get("split"))
        try:
            effective = date.fromisoformat(str(row.get("date")))
        except ValueError:
            continue
        if factor is None:
            continue
        stamp = _iso(splits.received_at)
        try:
            effective_at = _iso(session_open(effective))
        except Exception:  # a split dated on a non-session day: keep the calendar day at 09:30 New York
            effective_at = _iso(datetime.combine(effective, datetime.min.time(), NEW_YORK).replace(hour=9, minute=30))
        split_items.append({"factor": factor, "effective_at": effective_at, "source_at": stamp, "available_at": stamp})
    stamp = _iso(max(eod.received_at, splits.received_at))
    component = {"bars": bars, "splits": split_items, "adjustment": "RAW_UNADJUSTED",
                 "coverage_verified": not missing, "split_coverage_verified": True,
                 "source_at": _iso(eod.received_at), "available_at": stamp}
    return {"schema": COMPONENT_SCHEMA, "symbol": symbol, "daily": component,
            "producer_note": {"producer": PRODUCER, "version": PRODUCER_VERSION, "missing_sessions": missing,
                              "eod_payload_sha256": eod.sha256, "splits_payload_sha256": splits.sha256,
                              "sessions": [sessions[0].isoformat(), sessions[-1].isoformat()]}}


# ---------------------------------------------------------------- orchestration

def produce_causal_inputs(fetch: Fetcher, *, session_date: date, output_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    """Registry + 20-session daily contract for the causal list of `session_date` (built on D-1 after the close)."""
    previous = previous_session(session_date)
    close = session_close(previous)
    clock = now or datetime.now(timezone.utc)
    if clock <= close:
        raise ProducerError("PREVIOUS_SESSION_NOT_CLOSED")
    sessions = xnys_sessions_ending(previous, LIQUIDITY_SESSIONS)
    registry = build_registry(fetch("/api/exchange-symbol-list/US", {}), previous_close=close)
    bulk = {session: fetch("/api/eod-bulk-last-day/US", {"date": session.isoformat()}) for session in sessions}
    splits = {session: fetch("/api/eod-bulk-last-day/US", {"date": session.isoformat(), "type": "splits"}) for session in sessions}
    daily = build_daily_contract(registry, bulk, splits, sessions=sessions, previous_close=close)
    registry_sha = write_private(output_dir / "registry.json", canonical(registry))
    daily_sha = write_private(output_dir / "daily_contract.json", canonical(daily))
    return {"session_date": session_date.isoformat(), "previous_session": previous.isoformat(), "registry_sha256": registry_sha,
            "daily_contract_sha256": daily_sha, "registry_symbols": len(registry["instruments"]),
            "complete_bars": daily["producer_note"]["complete_bars"], "output_dir": str(output_dir)}


def produce_instrument_components(fetch: Fetcher, symbols: Sequence[str], *, session_date: date, output_dir: Path) -> dict[str, Any]:
    """61-session components for the names of a causal list (D-1 after the close, before the snapshot)."""
    previous = previous_session(session_date)
    sessions = xnys_sessions_ending(previous, ATR_SESSIONS)
    written: dict[str, str] = {}
    incomplete: list[str] = []
    for symbol in symbols:
        if not _symbol_ok(symbol):
            raise ProducerError("SYMBOL_INVALID")
        eod = fetch(f"/api/eod/{symbol}.US", {"period": "d", "from": sessions[0].isoformat(), "to": sessions[-1].isoformat()})
        splits = fetch(f"/api/splits/{symbol}.US", {"from": "1990-01-01"})
        component = build_instrument_component(symbol, eod, splits, sessions=sessions)
        if not component["daily"]["coverage_verified"]:
            incomplete.append(symbol)
        written[symbol] = write_private(output_dir / "daily_61" / f"{symbol}.json", canonical(component))
    return {"session_date": session_date.isoformat(), "symbols": len(symbols), "incomplete": incomplete, "component_sha256": written}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", required=True, help="D (ISO); inputs are built for D-1 after the close")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--list-file", help="optional causal-list symbols (one per line) to produce 61-session components")
    args = parser.parse_args(argv)
    if os.environ.get("C3PO_R2D2_V2_PRODUCERS_ENABLED", "").lower() != "true":
        print('{"status":"OFF","reason":"C3PO_R2D2_V2_PRODUCERS_ENABLED is not true"}')
        return 0
    from .config import get_settings
    settings = get_settings()
    fetch = EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=settings.market_data_timeout_seconds)
    session_date = date.fromisoformat(args.session_date)
    output_dir = Path(args.output_dir)
    result = produce_causal_inputs(fetch, session_date=session_date, output_dir=output_dir)
    if args.list_file:
        symbols = [line.strip() for line in Path(args.list_file).read_text(encoding="utf-8").splitlines() if line.strip()]
        result["components"] = produce_instrument_components(fetch, symbols, session_date=session_date, output_dir=output_dir)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
