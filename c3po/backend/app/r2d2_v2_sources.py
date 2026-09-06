"""Read-only file port for separately audited V2 producers, not a live adapter.

Producer contract: publish root/snapshot.json by atomic rename; append immutable
root/events/<event_id>.<self_sha256>.json files. Directories must be private
(0700), files private (0600). self_sha256 hashes canonical JSON without that
field (ASCII, sorted keys, compact separators, no NaN). The port never writes,
fetches providers, imports the application or claims the legacy feeds are ready.

Snapshot instrument payloads are preserved in full even when invalid.
data_available is a diagnostic, never the mapper's input-completeness decision.
A completed response with invalid risk must not become a later retry. Calendar completeness,
ADV20, eligibility policy and earnings through maturity belong to the mapper.
daily.adjustment is RAW_UNADJUSTED; every bar explicitly carries complete,
regular_session, source_at and available_at; every split carries its own
source_at/available_at. No timestamp or negative earnings coverage is inferred.
Events use the portfolio type/at/available_at/session/instrument_key shape;
BAR coverage and dividend entitlement/payment are explicit, never synthesized.
Events are returned repeatedly with immutable receipts: the durable consumer
must deduplicate by event_id and reject any changed receipt across restarts.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from threading import RLock
from typing import Any, TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from .database import Database

MANIFEST_SHA = "01d258903c060660a51ad48e7506903d038b0fa6901142456e06c7858350c359"
SNAPSHOT_SCHEMA = "V2_SHADOW_SOURCE_SNAPSHOT_V1"
EVENT_SCHEMA = "V2_SHADOW_SOURCE_EVENT_V1"
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 64 * 1024
MAX_EVENT_FILES = 4096
MAX_INSTRUMENTS = 10000
NY = ZoneInfo("America/New_York")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_META = {"schema", "manifest_sha", "source_id", "provenance", "source_at", "available_at", "sequence", "self_sha256"}


class SourceUnavailable(ValueError):
    """Controlled diagnostic code only; never include input or error strings."""


def _require(value: bool, code: str) -> None:
    if not value:
        raise SourceUnavailable(code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _time(value: Any) -> datetime:
    _require(isinstance(value, str), "TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise SourceUnavailable("TIMESTAMP_INVALID") from None
    _require(parsed.tzinfo is not None, "TIMESTAMP_NAIVE")
    return parsed.astimezone(timezone.utc)


def _now(now: datetime) -> datetime:
    _require(isinstance(now, datetime) and now.tzinfo is not None, "NOW_NOT_AWARE")
    return now.astimezone(timezone.utc)


def _number(value: Any, *, positive: bool = False) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def _token(value: Any) -> bool:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _causal(value: dict[str, Any], through: datetime) -> tuple[datetime, datetime]:
    source, available = _time(value.get("source_at")), _time(value.get("available_at"))
    _require(source <= available <= through, "SOURCE_FUTURE_OR_REVERSED")
    return source, available


def capabilities() -> dict[str, Any]:
    return {"file_envelope_port": True, "production_ready": False,
            "legacy_inventory_diagnostic_only": True,
            "missing_producer_contracts": ["causal_bid_ask_universe_10et", "daily_61_ohlc_splits_known_adv20", "earnings_verified_coverage"],
            "activation_blocked_until_audited_producer": True}


def _load_json(data: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        result = json.loads(data, object_pairs_hook=pairs,
                            parse_constant=lambda _value: (_ for _ in ()).throw(SourceUnavailable("JSON_NONFINITE")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, SourceUnavailable):
            raise
        raise SourceUnavailable("JSON_MALFORMED") from None
    _require(isinstance(result, dict), "ENVELOPE_NOT_OBJECT")
    return result


def _metadata(envelope: dict[str, Any], schema: str, now: datetime) -> None:
    extra = {"universe"} if schema == SNAPSHOT_SCHEMA else {"event_id", "event"}
    _require(set(envelope) == _META | extra, "ENVELOPE_FIELDS")
    _require(envelope.get("schema") == schema, "SCHEMA_MISMATCH")
    _require(envelope.get("manifest_sha") == MANIFEST_SHA, "MANIFEST_MISMATCH")
    _require(_token(envelope.get("source_id")), "SOURCE_ID_INVALID")
    _require(type(envelope.get("sequence")) is int and envelope["sequence"] >= 0, "SEQUENCE_INVALID")
    provenance = envelope.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != {"producer", "version", "payload_sha256"}:
        raise SourceUnavailable("PROVENANCE_MISSING")
    _require(_token(provenance["producer"]) and _token(provenance["version"]) and _hash(provenance["payload_sha256"]), "PROVENANCE_INVALID")
    _require(_hash(envelope.get("self_sha256")), "ENVELOPE_HASH_MISSING")
    try:
        digest = hashlib.sha256(canonical({k: v for k, v in envelope.items() if k != "self_sha256"})).hexdigest()
    except (ValueError, TypeError, RecursionError):
        raise SourceUnavailable("JSON_MALFORMED") from None
    _require(digest == envelope["self_sha256"], "ENVELOPE_HASH_MISMATCH")
    _causal(envelope, now)


def _private_directory(fd: int) -> None:
    info = os.fstat(fd)
    _require(stat.S_ISDIR(info.st_mode), "SOURCE_NOT_DIRECTORY")
    _require(stat.S_IMODE(info.st_mode) & 0o077 == 0, "SOURCE_DIRECTORY_NOT_PRIVATE")


def _open_directory(root: Path) -> int:
    """Walk anchored descriptors; no symlink traversal, even in ancestors."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        _private_directory(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_file(directory: int, name: str, budget: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode), "SOURCE_NOT_REGULAR")
        _require(stat.S_IMODE(before.st_mode) & 0o077 == 0, "SOURCE_FILE_NOT_PRIVATE")
        _require(0 < before.st_size <= budget, "SOURCE_SIZE_LIMIT")
        data = stream.read(budget + 1)
        after = os.fstat(stream.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    _require(identity(before) == identity(after) and len(data) == before.st_size, "SOURCE_CHANGED_DURING_READ")
    return data


def _instrument(row: dict[str, Any], now: datetime, envelope_available: datetime) -> dict[str, Any]:
    required = {"symbol", "market", "security_type", "classification_verified", "sequence", "source_at", "available_at", "quote", "daily", "risk", "earnings"}
    _require(set(row) == required, "INSTRUMENT_FIELDS")
    _require(row["market"] in {"NYSE", "NASDAQ"}, "MARKET_INVALID")
    _require(row["classification_verified"] is True and _token(row["security_type"]), "CLASSIFICATION_UNVERIFIED")
    _require(type(row["sequence"]) is int and row["sequence"] >= 0, "INSTRUMENT_SEQUENCE_INVALID")
    _, available = _causal(row, envelope_available)
    quote = row["quote"]
    _require(isinstance(quote, dict) and set(quote) == {"bid", "ask", "bid_source_at", "ask_source_at", "available_at"}, "QUOTE_MISSING")
    _require(_number(quote["bid"], positive=True) and _number(quote["ask"], positive=True) and quote["ask"] >= quote["bid"], "QUOTE_INVALID")
    quote_available = _time(quote["available_at"])
    _require(quote_available <= available, "QUOTE_AVAILABLE_FUTURE")
    for key in ("bid_source_at", "ask_source_at"):
        source = _time(quote[key])
        _require(source <= quote_available and 0 <= (now - source).total_seconds() <= 10, "QUOTE_STALE_OR_FUTURE")
    daily = row["daily"]
    _require(isinstance(daily, dict) and set(daily) == {"bars", "splits", "adjustment", "coverage_verified", "split_coverage_verified", "source_at", "available_at"}, "DAILY_MISSING")
    _causal(daily, available)
    _require(daily["coverage_verified"] is True and daily["adjustment"] == "RAW_UNADJUSTED", "DAILY_COVERAGE_OR_ADJUSTMENT_UNVERIFIED")
    _require(isinstance(daily["bars"], list) and len(daily["bars"]) == 61, "DAILY_61_REQUIRED")
    days = []
    for bar in daily["bars"]:
        _require(isinstance(bar, dict) and set(bar) == {"session_date", "open", "high", "low", "close", "volume", "complete", "regular_session", "source_at", "available_at"}, "DAILY_BAR_FIELDS")
        try:
            day = date.fromisoformat(bar["session_date"])
        except (ValueError, TypeError):
            raise SourceUnavailable("DAILY_DATE_INVALID") from None
        _require(day < now.astimezone(NY).date() and bar["complete"] is True and bar["regular_session"] is True, "DAILY_NOT_COMPLETED_REGULAR")
        _causal(bar, available)
        _require(all(_number(bar[k], positive=True) for k in ("open", "high", "low", "close")) and _number(bar["volume"]), "DAILY_NUMBER_INVALID")
        _require(bar["high"] >= max(bar["open"], bar["close"]) and bar["low"] <= min(bar["open"], bar["close"]), "DAILY_OHLC_INVALID")
        days.append(day)
    _require(days == sorted(set(days)), "DAILY_DUPLICATE_OR_ORDER")
    _require(isinstance(daily["splits"], list) and daily["split_coverage_verified"] is True, "SPLIT_EVIDENCE_MISSING")
    for split in daily["splits"]:
        _require(isinstance(split, dict) and set(split) == {"factor", "effective_at", "source_at", "available_at"} and _number(split["factor"], positive=True), "SPLIT_INVALID")
        _time(split["effective_at"])  # future effective splits remain known evidence; mapper decides application
        _causal(split, available)
    risk = row["risk"]
    _require(isinstance(risk, dict) and set(risk) == {"value", "producer", "source_at", "available_at"}, "RISK_MISSING")
    _causal(risk, available)
    _require(_number(risk["value"]) and risk["value"] <= 100 and _token(risk["producer"]), "RISK_INVALID")
    earnings = row["earnings"]
    _require(isinstance(earnings, dict) and set(earnings) == {"coverage_verified", "window_start", "window_end", "events", "source_at", "available_at"}, "EARNINGS_MISSING")
    _causal(earnings, available)
    _require(earnings["coverage_verified"] is True, "EARNINGS_COVERAGE_UNVERIFIED")
    beginning, end = _time(earnings["window_start"]), _time(earnings["window_end"])
    _require(beginning <= available <= end and isinstance(earnings["events"], list), "EARNINGS_COVERAGE_WINDOW")
    for event in earnings["events"]:
        _require(isinstance(event, dict) and set(event) == {"event_at", "available_at"}, "EARNINGS_EVENT_INVALID")
        _require(beginning <= _time(event["event_at"]) <= end and _time(event["available_at"]) <= available, "EARNINGS_EVENT_NOT_CAUSAL")
    return {**row, "data_available": True, "diagnostics": []}


class FileShadowSource:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(os.path.abspath(root))
        self._event_hashes: dict[str, str] = {}
        self._lock = RLock()
        self.last_event_diagnostics: list[dict[str, str]] = []

    capabilities = staticmethod(capabilities)

    def snapshot(self, now: datetime) -> dict[str, Any]:
        now = _now(now)
        missing = {"schema": "V2_SHADOW_SOURCE_BATCH_V1", "status": "MISSING", "manifest_sha": MANIFEST_SHA,
                   "universe": {"coverage_verified": False, "instruments": []}, "diagnostics": []}
        try:
            fd = _open_directory(self.root)
            try:
                data = _read_file(fd, "snapshot.json", MAX_SNAPSHOT_BYTES)
            finally:
                os.close(fd)
            envelope = _load_json(data)
            _metadata(envelope, SNAPSHOT_SCHEMA, now)
            universe = envelope["universe"]
            _require(isinstance(universe, dict) and set(universe) == {"coverage_verified", "instruments"}, "UNIVERSE_MISSING")
            _require(universe["coverage_verified"] is True, "UNIVERSE_COVERAGE_UNVERIFIED")
            rows = universe["instruments"]
            _require(isinstance(rows, list) and len(rows) <= MAX_INSTRUMENTS, "UNIVERSE_SIZE_LIMIT")
            seen, instruments = set(), []
            for row in rows:
                _require(isinstance(row, dict) and isinstance(row.get("symbol"), str) and _SYMBOL.fullmatch(row["symbol"]) is not None, "INSTRUMENT_ID_INVALID")
                _require(row["symbol"] not in seen, "UNIVERSE_DUPLICATE_SYMBOL")
                seen.add(row["symbol"])
                try:
                    instruments.append(_instrument(row, now, _time(envelope["available_at"])))
                except SourceUnavailable as exc:
                    instruments.append({**row, "data_available": False, "diagnostics": [{"code": str(exc)}]})
                except (ValueError, TypeError, KeyError, OverflowError):
                    instruments.append({**row, "data_available": False, "diagnostics": [{"code": "INSTRUMENT_MALFORMED"}]})
            return {"schema": "V2_SHADOW_SOURCE_BATCH_V1", "status": "AVAILABLE", "manifest_sha": MANIFEST_SHA,
                    **{k: envelope[k] for k in ("source_id", "provenance", "source_at", "available_at", "sequence", "self_sha256")},
                    "envelope_sha256": hashlib.sha256(data).hexdigest(),
                    "universe": {"coverage_verified": True, "instruments": instruments}, "diagnostics": []}
        except SourceUnavailable as exc:
            missing["diagnostics"] = [{"code": str(exc)}]
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            missing["diagnostics"] = [{"code": "SOURCE_MISSING_OR_MALFORMED"}]
        return missing

    def events(self, now: datetime) -> list[dict[str, Any]]:
        now = _now(now)
        with self._lock:
            self.last_event_diagnostics = []
            try:
                root_fd = _open_directory(self.root)
                try:
                    directory = os.open("events", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
                finally:
                    os.close(root_fd)
                try:
                    _private_directory(directory)
                    names = []
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            names.append(entry.name)
                            _require(len(names) <= MAX_EVENT_FILES, "EVENT_FILE_LIMIT")
                    found: dict[str, dict[str, Any]] = {}
                    duplicates = set()
                    for name in sorted(names):
                        if name.startswith(".") or not name.endswith(".json"):
                            continue  # atomic producer staging, never a completed event
                        try:
                            data = _read_file(directory, name, MAX_EVENT_BYTES)
                            envelope = _load_json(data)
                            _metadata(envelope, EVENT_SCHEMA, now)
                            identity = envelope["event_id"]
                            _require(_token(identity) and name == identity + "." + envelope["self_sha256"] + ".json", "EVENT_RECEIPT_FILENAME")
                            _validate_event(envelope["event"], _time(envelope["available_at"]))
                            digest = hashlib.sha256(data).hexdigest()
                            old = self._event_hashes.get(identity)
                            _require(old is None or old == digest, "EVENT_ID_MUTATED")
                            if identity in found:
                                duplicates.add(identity)
                            found[identity] = {**envelope["event"], "event_id": identity, "source_id": envelope["source_id"],
                                               "source_at": envelope["source_at"], "envelope_available_at": envelope["available_at"],
                                               "sequence": envelope["sequence"], "provenance": envelope["provenance"],
                                               "manifest_sha": MANIFEST_SHA, "self_sha256": envelope["self_sha256"],
                                               "envelope_sha256": digest}
                        except SourceUnavailable as exc:
                            self.last_event_diagnostics.append({"code": str(exc)})
                        except (OSError, ValueError, TypeError, KeyError, OverflowError):
                            self.last_event_diagnostics.append({"code": "EVENT_MISSING_OR_MALFORMED"})
                    for identity in duplicates:
                        found.pop(identity, None)
                        self.last_event_diagnostics.append({"code": "EVENT_ID_DUPLICATED"})
                    if self.last_event_diagnostics:
                        return []  # don't process a partial event tape as complete
                    for identity, event in found.items():
                        self._event_hashes[identity] = event["envelope_sha256"]
                    return sorted(found.values(), key=lambda e: (_time(e["available_at"]), e["sequence"], e["event_id"]))
                finally:
                    os.close(directory)
            except SourceUnavailable as exc:
                self.last_event_diagnostics = [{"code": str(exc)}]
            except (OSError, ValueError, TypeError):
                self.last_event_diagnostics = [{"code": "EVENT_SOURCE_MISSING"}]
            return []


def _validate_event(event: Any, through: datetime) -> None:
    """Validate evidence shape, preserving explicit gap/unknown-value events.

    No generic PRICE or dividend announcement is promoted into a trade/entitlement.
    A BAR with coverage_complete=false and an entitlement with net_per_share=null
    are valid evidence of missing observation, handled explicitly by the ledger.
    """
    _require(isinstance(event, dict), "EVENT_MISSING")
    common = {"type", "at", "available_at", "session", "instrument_key"}
    shapes = {
        "BAR": {"end_at", "open", "high", "low", "close", "regular", "coverage_complete"},
        "TRADE": {"price", "regular"}, "MARK": {"price", "regular"},
        "QUOTE": {"bid", "ask", "bid_at", "ask_at", "regular"},
        "SPLIT": {"factor"}, "DIVIDEND_ENTITLEMENT": {"entitlement_id", "net_per_share"},
        "DIVIDEND_PAYMENT": {"entitlement_id"}, "EARNINGS": {"earnings_at"},
        "MATURITY": set(), "DATA_GAP": {"reason"}, "SESSION_OPEN": set(), "SESSION_CLOSE": set(),
    }
    kind = event.get("type")
    _require(isinstance(kind, str) and kind in shapes, "EVENT_KIND_OR_FIELDS")
    if kind.startswith("SESSION_"):
        common = common - {"instrument_key"}
    optional = {"trades"} if kind == "BAR" else set()
    required = common | shapes[kind]
    _require(required <= set(event) <= (required | optional), "EVENT_KIND_OR_FIELDS")
    if not kind.startswith("SESSION_"):
        _require(_token(event["instrument_key"]), "EVENT_INSTRUMENT_INVALID")
    at, available = _time(event["at"]), _time(event["available_at"])
    _require(at <= available <= through, "EVENT_FUTURE_OR_REVERSED")
    try:
        _require(isinstance(event["session"], str) and date.fromisoformat(event["session"]).isoformat() == event["session"], "EVENT_SESSION_INVALID")
    except (ValueError, TypeError):
        raise SourceUnavailable("EVENT_SESSION_INVALID") from None
    if kind in {"BAR", "TRADE", "MARK", "QUOTE"}:
        _require(type(event["regular"]) is bool, "EVENT_REGULAR_FLAG_MISSING")
    if kind in {"TRADE", "MARK"}:
        _require(_number(event["price"], positive=True), "EVENT_PRICE_INVALID")
    elif kind == "BAR":
        end = _time(event["end_at"])
        _require(at < end <= available and type(event["coverage_complete"]) is bool, "EVENT_BAR_COVERAGE_OR_INTERVAL")
        _require(all(_number(event[k], positive=True) for k in ("open", "high", "low", "close")), "EVENT_BAR_NUMBER_INVALID")
        _require(event["low"] <= min(event["open"], event["close"]) <= max(event["open"], event["close"]) <= event["high"], "EVENT_BAR_OHLC_INVALID")
        if "trades" in event:
            _require(isinstance(event["trades"], list), "EVENT_BAR_TRADES_INVALID")
            previous = at
            for trade in event["trades"]:
                _require(isinstance(trade, dict) and set(trade) == {"at", "price"} and _number(trade["price"], positive=True), "EVENT_BAR_TRADE_INVALID")
                instant = _time(trade["at"])
                _require(previous <= instant < end, "EVENT_BAR_TRADE_ORDER_INVALID")
                previous = instant
    elif kind == "QUOTE":
        _require(_number(event["bid"], positive=True) and _number(event["ask"], positive=True) and event["ask"] >= event["bid"], "EVENT_QUOTE_INVALID")
        for key in ("bid_at", "ask_at"):
            _require(_time(event[key]) <= at, "EVENT_QUOTE_FUTURE")
    elif kind == "SPLIT":
        _require(_number(event["factor"], positive=True), "EVENT_SPLIT_INVALID")
    elif kind in {"DIVIDEND_ENTITLEMENT", "DIVIDEND_PAYMENT"}:
        _require(_token(event["entitlement_id"]), "EVENT_ENTITLEMENT_INVALID")
        if kind == "DIVIDEND_ENTITLEMENT":
            _require(event["net_per_share"] is None or _number(event["net_per_share"]), "EVENT_DIVIDEND_INVALID")
    elif kind == "EARNINGS":
        _time(event["earnings_at"])  # receipt time is not the scheduled announcement time
    elif kind == "DATA_GAP":
        _require(_token(event["reason"]), "EVENT_GAP_REASON_INVALID")


class ExistingAppInventory:
    """Diagnostic sample only: two already-persisted snapshots, no services."""
    def __init__(self, database: Database) -> None:
        self.database = database

    def read(self, now: datetime) -> dict[str, Any]:
        now = _now(now)
        instruments, diagnostics = [], []
        for market in ("NASDAQ", "NYSE"):
            try:
                snapshot = self.database.latest_analysis_snapshot("valuation_universe", market + "_UNIVERSE")
                if not isinstance(snapshot, dict):
                    raise SourceUnavailable("LEGACY_SNAPSHOT_MISSING")
                value = snapshot.get("published_at")
                published = _now(value) if isinstance(value, datetime) else _time(value)
                _require(published <= now, "LEGACY_SNAPSHOT_FUTURE")
                rows = snapshot.get("outputs", {}).get("rows")
                _require(isinstance(rows, list) and len(rows) <= MAX_INSTRUMENTS, "LEGACY_ROWS_MISSING")
                for row in rows:
                    if isinstance(row, dict) and isinstance(row.get("symbol"), str) and _SYMBOL.fullmatch(row["symbol"]):
                        instruments.append({"symbol": row["symbol"], "market": market,
                                            "published_at": published.isoformat(), "diagnostic_only": True})
            except SourceUnavailable as exc:
                diagnostics.append({"market": market, "code": str(exc)})
            except Exception:
                diagnostics.append({"market": market, "code": "LEGACY_READ_FAILED"})
        return {"schema": "V2_EXISTING_APP_INVENTORY_DIAGNOSTIC_V1", "status": "DIAGNOSTIC_ONLY",
                "universe": {"coverage_verified": False, "instruments": instruments},
                "production_ready": False, "diagnostics": diagnostics, "capabilities": capabilities()}
