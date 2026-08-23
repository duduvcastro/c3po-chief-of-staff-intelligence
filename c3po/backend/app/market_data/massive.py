from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timezone
import re
from typing import Any
from urllib.parse import quote, quote_plus, urlparse

from .http import JsonHttpClient, MarketDataRequestError
from .models import number


class MassiveResponseError(RuntimeError):
    """Raised when Massive returns a shape that cannot be audited safely."""


class MassiveClient:
    """Small, auditable Massive REST client for Day D research data.

    The production trading path does not import this client. Historical trades
    and quotes retain both participant and SIP timestamps so replay can model
    event time separately from the time the consolidated feed knew the event.
    """

    code = "massive"
    name = "Massive Stocks Advanced"

    def __init__(self, base_url: str, token: str, http: JsonHttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Massive base URL must be an absolute HTTPS URL")
        self._origin = (parsed.scheme, parsed.netloc)

    def iter_trades(self, symbol: str, *, session_date: date) -> Iterator[dict[str, Any]]:
        params = self._session_params(session_date)
        for row in self._iter_results(f"/v3/trades/{self._symbol(symbol)}", params=params):
            normalized = self._normalize_trade(symbol, row)
            if normalized is not None:
                yield normalized

    def iter_quotes(self, symbol: str, *, session_date: date) -> Iterator[dict[str, Any]]:
        params = self._session_params(session_date)
        for row in self._iter_results(f"/v3/quotes/{self._symbol(symbol)}", params=params):
            normalized = self._normalize_quote(symbol, row)
            if normalized is not None:
                yield normalized

    def splits(
        self,
        *,
        ticker: str | None = None,
        execution_date_gte: date | None = None,
        execution_date_lte: date | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 5_000, "sort": "execution_date.asc"}
        if ticker:
            params["ticker"] = self._symbol(ticker)
        if execution_date_gte:
            params["execution_date.gte"] = execution_date_gte.isoformat()
        if execution_date_lte:
            params["execution_date.lte"] = execution_date_lte.isoformat()
        return list(self._iter_results("/stocks/v1/splits", params=params))

    def dividends(
        self,
        *,
        ticker: str | None = None,
        ex_dividend_date_gte: date | None = None,
        ex_dividend_date_lte: date | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 5_000, "sort": "ex_dividend_date.asc"}
        if ticker:
            params["ticker"] = self._symbol(ticker)
        if ex_dividend_date_gte:
            params["ex_dividend_date.gte"] = ex_dividend_date_gte.isoformat()
        if ex_dividend_date_lte:
            params["ex_dividend_date.lte"] = ex_dividend_date_lte.isoformat()
        return list(self._iter_results("/stocks/v1/dividends", params=params))

    def _iter_results(
        self,
        path: str,
        *,
        params: dict[str, Any],
        max_pages: int = 100_000,
    ) -> Iterator[dict[str, Any]]:
        if not self.token:
            raise ValueError("Massive API token is not configured")
        url = f"{self.base_url}{path}"
        request_params = {**params, "apiKey": self.token}
        seen_urls: set[str] = set()
        for _page in range(max_pages):
            if url in seen_urls:
                raise MassiveResponseError("Massive pagination returned a repeated URL")
            seen_urls.add(url)
            try:
                payload = self.http.get_json(url, params=request_params)
            except MarketDataRequestError as exc:
                message = self._redact_request_error(exc)
                raise MassiveResponseError(f"Massive request failed: {message}") from None
            if not isinstance(payload, dict):
                raise MassiveResponseError("Massive response must be an object")
            results = payload.get("results") or []
            if not isinstance(results, list):
                raise MassiveResponseError("Massive results must be a list")
            for row in results:
                if isinstance(row, dict):
                    yield row
            next_url = str(payload.get("next_url") or "").strip()
            if not next_url:
                return
            self._require_same_origin(next_url)
            url = next_url
            # Massive cursor URLs omit the API key. Query filters are already
            # embedded in next_url, so only the credential is sent again.
            request_params = {"apiKey": self.token}
        raise MassiveResponseError("Massive pagination exceeded the safety limit")

    def _redact_request_error(self, exc: Exception) -> str:
        message = str(exc)
        encoded_secrets = {
            self.token,
            quote(self.token, safe=""),
            quote_plus(self.token, safe=""),
        }
        for secret in encoded_secrets:
            if secret:
                message = message.replace(secret, "[REDACTED]")
        return re.sub(
            r"(?i)(apiKey=)[^&\s\"']+",
            r"\1[REDACTED]",
            message,
        )

    def _require_same_origin(self, url: str) -> None:
        parsed = urlparse(url)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise MassiveResponseError("Massive pagination attempted to leave the configured origin")

    @staticmethod
    def _session_params(session_date: date) -> dict[str, Any]:
        return {
            "timestamp": session_date.isoformat(),
            "order": "asc",
            "sort": "timestamp",
            "limit": 50_000,
        }

    @staticmethod
    def _symbol(symbol: str) -> str:
        clean = symbol.strip().upper()
        if not clean or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for character in clean):
            raise ValueError("invalid Massive stock symbol")
        return clean

    @staticmethod
    def _timestamp(value: Any) -> datetime | None:
        try:
            nanoseconds = int(value)
        except (TypeError, ValueError):
            return None
        if nanoseconds <= 0:
            return None
        return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=timezone.utc)

    @classmethod
    def _normalize_trade(cls, symbol: str, row: dict[str, Any]) -> dict[str, Any] | None:
        event_at = cls._timestamp(row.get("participant_timestamp"))
        available_at = cls._timestamp(row.get("sip_timestamp"))
        price = number(row.get("price"))
        size = number(row.get("decimal_size")) or number(row.get("size"))
        if event_at is None or available_at is None or price is None or size is None:
            return None
        if price <= 0 or size <= 0 or available_at < event_at:
            return None
        return {
            "trade_id": str(row.get("id") or row.get("sequence_number") or ""),
            "symbol": cls._symbol(symbol),
            "event_at": event_at,
            "available_at": available_at,
            "price": price,
            "size": size,
            "exchange": row.get("exchange"),
            "conditions": tuple(row.get("conditions") or ()),
            "sequence_number": row.get("sequence_number"),
            "tape": row.get("tape"),
        }

    @classmethod
    def _normalize_quote(cls, symbol: str, row: dict[str, Any]) -> dict[str, Any] | None:
        event_at = cls._timestamp(row.get("participant_timestamp"))
        available_at = cls._timestamp(row.get("sip_timestamp"))
        bid = number(row.get("bid_price"))
        ask = number(row.get("ask_price"))
        bid_size = number(row.get("bid_size"))
        ask_size = number(row.get("ask_size"))
        values = (bid, ask, bid_size, ask_size)
        if event_at is None or available_at is None or any(value is None for value in values):
            return None
        if min(value for value in values if value is not None) <= 0 or available_at < event_at:
            return None
        return {
            "quote_id": str(row.get("id") or row.get("sequence_number") or ""),
            "symbol": cls._symbol(symbol),
            "event_at": event_at,
            "available_at": available_at,
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "bid_exchange": row.get("bid_exchange"),
            "ask_exchange": row.get("ask_exchange"),
            "conditions": tuple(row.get("conditions") or ()),
            "sequence_number": row.get("sequence_number"),
            "tape": row.get("tape"),
        }
