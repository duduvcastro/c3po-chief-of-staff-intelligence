"""F1 provider diagnostic family: standalone, two GETs, private ciphertext, no operational readiness.
Pinned producer normalizer extracted without importing its application. No action on import.
"""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence
PRODUCER = "fable-eodhd-daily"


PRODUCER_VERSION = "v2"


REGISTRY_SCHEMA = "V2_CAUSAL_REGISTRY_V1"


RECEIPT_SCHEMA = "V2_PRODUCER_RECEIPT_V1"


REGISTRY_FIELDS = frozenset({"schema", "source_id", "source_at", "available_at", "captured_at", "coverage_verified", "instruments"})


ALLOWED_EXCHANGES = ("NYSE", "NASDAQ")


TYPE_MAP = {
    "Common Stock": "COMMON_STOCK", "ETF": "ETF", "Preferred Stock": "PREFERRED_STOCK", "Warrant": "WARRANT",
    "FUND": "FUND", "Mutual Fund": "MUTUAL_FUND", "Unit": "UNIT", "Notes": "NOTE", "ETC": "ETC", "BOND": "BOND", "INDEX": "INDEX",
}


DAILY_ELIGIBLE_TYPES = ("COMMON_STOCK", "COMMON_STOCK_ADR")  # the only classes the signed list builder selects


SYMBOL_RE_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")


class ProducerError(RuntimeError):
    """Controlled message only; provider tokens and raw payloads are never included."""


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


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _symbol_ok(code: Any) -> bool:
    return isinstance(code, str) and 1 <= len(code) <= 20 and code[0] in set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") and all(c in SYMBOL_RE_ALLOWED for c in code)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _receipt(document: str, **fields: Any) -> dict[str, Any]:
    return {"schema": RECEIPT_SCHEMA, "producer": PRODUCER, "version": PRODUCER_VERSION, "document": document, **fields}


def build_registry(response: Response, *, previous_close: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map the provider's US symbol list to the registry contract (port document, receipt); only NYSE/NASDAQ rows are kept."""
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
    document = {"schema": REGISTRY_SCHEMA, "source_id": "eodhd-exchange-symbol-list-US", "source_at": stamp, "available_at": stamp,
                "captured_at": stamp, "coverage_verified": True, "instruments": instruments}
    assert set(document) == REGISTRY_FIELDS
    receipt = _receipt("registry", provider_payload_sha256=response.sha256, received_at=stamp, counts=counts,
                       adr_distinction="NOT_AVAILABLE_IN_PROVIDER_LIST: common stocks reported as COMMON_STOCK")
    return document, receipt


def _bar(item: Mapping[str, Any], session: date, received_at: datetime) -> dict[str, Any] | None:
    """A complete regular-session bar; the caller guarantees `received_at` is after the session close."""
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


def _distinct(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Identical duplicate rows count once; rows that differ are a conflict for the caller to record."""
    unique: dict[bytes, Mapping[str, Any]] = {}
    for row in rows:
        try:
            unique.setdefault(canonical(row), row)
        except (TypeError, ValueError):
            unique[repr(row).encode()] = row
    return list(unique.values())

