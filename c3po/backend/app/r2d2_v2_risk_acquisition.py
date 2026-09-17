"""Bounded, injectable acquisition for the V2 risk producer.

This layer preserves response bytes and factual receipt clocks. HTTP success
does not attest coverage, freshness, or READY. It has no database, policy,
worker or trading side effects; private persistence belongs to the executor.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit


@dataclass(frozen=True)
class SourceRequest:
    provider: str
    path: str
    parameters: Mapping[str, str | int]


@dataclass(frozen=True)
class HttpReply:
    status: int
    body: bytes


@dataclass(frozen=True)
class SourceReceipt:
    request: SourceRequest
    started_at: datetime
    received_at: datetime
    status: int | None
    body: bytes
    payload_sha256: str
    diagnostic: str | None

    def payload(self) -> Any:
        if self.diagnostic is not None:
            raise ValueError(self.diagnostic)
        return json.loads(self.body)


@dataclass(frozen=True)
class Acquisition:
    receipts: tuple[SourceReceipt, ...]
    traversal_complete: bool
    diagnostic: str | None
    # Traversal only proves the returned pagination was exhausted. Neither an
    # empty response nor exhaustion proves issuer/population/window coverage.
    coverage_verified: bool = False


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _reject_constant(_: str) -> Any:
    raise ValueError("NON_FINITE_JSON")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


class RiskAcquirer:
    """Transport must enforce timeout/response-size limits before buffering.

    Credentials are resolved within the transport, never in SourceRequest.
    Raised transport messages/URLs are intentionally not included in receipts.
    """

    def __init__(self, transport: Callable[[SourceRequest], HttpReply],
                 clock: Callable[[], datetime], *, max_pages: int = 100,
                 max_body_bytes: int = 16 * 1024 * 1024) -> None:
        if type(max_pages) is not int or not 1 <= max_pages <= 100:
            raise ValueError("PAGE_BUDGET_INVALID")
        if type(max_body_bytes) is not int or not 1 <= max_body_bytes <= 16 * 1024 * 1024:
            raise ValueError("BODY_BUDGET_INVALID")
        self.transport = transport
        self.clock = clock
        self.max_pages = max_pages
        self.max_body_bytes = max_body_bytes

    @staticmethod
    def _symbol(symbol: str, market: str = "US") -> str:
        if market != "US":
            raise ValueError("MARKET_UNSUPPORTED_COMPLETED_NULL")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,14}", symbol):
            raise ValueError("SYMBOL_INVALID")
        symbol = symbol.upper()
        if symbol.endswith(".SA"):
            raise ValueError("MARKET_UNSUPPORTED_COMPLETED_NULL")
        return symbol

    def _read(self, request: SourceRequest) -> SourceReceipt:
        started = self.clock()
        if not _aware(started):
            raise ValueError("CLOCK_INVALID")
        status: int | None = None
        body = b""
        diagnostic: str | None = None
        try:
            reply = self.transport(request)
            status = reply.status
            body = reply.body
        except Exception:
            diagnostic = "TRANSPORT_FAILED"
        received = self.clock()
        if not _aware(received) or received < started:
            raise ValueError("CLOCK_INVALID")
        if diagnostic is None:
            if type(body) is not bytes or len(body) > self.max_body_bytes:
                body = b""
                diagnostic = "BODY_REJECTED"
            elif type(status) is not int or status != 200:
                diagnostic = "HTTP_FAILED"
            else:
                try:
                    json.loads(body, parse_constant=_reject_constant,
                               object_pairs_hook=_unique_object)
                except (ValueError, UnicodeError, RecursionError):
                    diagnostic = "JSON_INVALID"
        return SourceReceipt(request, started, received, status, body,
                             hashlib.sha256(body).hexdigest(), diagnostic)

    def fundamentals(self, symbol: str, *, market: str = "US") -> Acquisition:
        symbol = self._symbol(symbol, market)
        provider_symbol = symbol if "." in symbol else f"{symbol}.US"
        request = SourceRequest("eodhd", f"/api/v1.1/fundamentals/{provider_symbol}", {})
        receipt = self._read(request)
        return Acquisition((receipt,), receipt.diagnostic is None, receipt.diagnostic)

    def grades(self, symbol: str, *, market: str = "US") -> Acquisition:
        receipt = self._read(SourceRequest("fmp", "/stable/grades",
                                           {"symbol": self._symbol(symbol, market)}))
        # The endpoint's population/window completeness needs separate proof.
        return Acquisition((receipt,), receipt.diagnostic is None, receipt.diagnostic)

    def institutional(self, symbol: str, *, year: int, quarter: int, market: str = "US") -> Acquisition:
        if type(year) is not int or not 2000 <= year <= 2100 or type(quarter) is not int or quarter not in (1, 2, 3, 4):
            raise ValueError("QUARTER_INVALID")
        receipt = self._read(SourceRequest(
            "fmp", "/stable/institutional-ownership/symbol-positions-summary",
            {"symbol": self._symbol(symbol, market), "year": year, "quarter": quarter}))
        return Acquisition((receipt,), receipt.diagnostic is None, receipt.diagnostic)

    def form4_fallback_diagnostic(self, symbol: str) -> Acquisition:
        symbol = self._symbol(symbol)
        offset = 0
        receipts: list[SourceReceipt] = []
        for _ in range(self.max_pages):
            receipt = self._read(SourceRequest("eodhd", f"/api/sec-filings/{symbol}/form4",
                                               {"page[offset]": offset, "page[limit]": 100}))
            receipts.append(receipt)
            if receipt.diagnostic:
                return Acquisition(tuple(receipts), False, receipt.diagnostic)
            payload = receipt.payload()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                return Acquisition(tuple(receipts), False, "FORM4_ENVELOPE_INVALID")
            links = payload.get("links")
            if not isinstance(links, dict) or "next" not in links:
                return Acquisition(tuple(receipts), False, "FORM4_NEXT_MISSING")
            rows = payload["data"]
            if len(rows) > 100 or any(not isinstance(row, dict) for row in rows):
                return Acquisition(tuple(receipts), False, "FORM4_ROWS_INVALID")
            next_path = links["next"]
            if next_path is None:
                return Acquisition(tuple(receipts), True, None)
            if not isinstance(next_path, str) or not rows:
                return Acquisition(tuple(receipts), False, "FORM4_NEXT_INVALID")
            # Never follow arbitrary provider URLs or echo their queries. Only
            # validate the expected offset and reconstruct an allowlisted call.
            parsed = urlsplit(next_path)
            query = parse_qs(parsed.query)
            if (parsed.scheme or parsed.netloc or parsed.fragment
                    or parsed.path not in (f"/api/sec-filings/{symbol}/form4",
                                           f"/api/sec-filings/{symbol}.US/form4")
                    or set(query) != {"page[offset]", "page[limit]"}
                    or query["page[offset]"] != [str(offset + len(rows))]
                    or query["page[limit]"] != ["100"]):
                return Acquisition(tuple(receipts), False, "FORM4_NEXT_INVALID")
            offset += len(rows)
        return Acquisition(tuple(receipts), False, "PAGE_BUDGET_EXHAUSTED")
