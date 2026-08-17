from datetime import datetime
from typing import Any

from ..schemas import NormalizedQuote
from .http import JsonHttpClient, MarketDataRequestError
from .models import from_unix, number, quality_for, require_price, utc_now


class BrapiClient:
    code = "brapi"
    name = "Brapi"

    def __init__(self, base_url: str, token: str, http: JsonHttpClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.http = http

    def quotes(self, symbols: list[str]) -> list[NormalizedQuote]:
        clean = [symbol.upper().removesuffix(".SA") for symbol in symbols]
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            payload = self.http.get_json(
                f"{self.base_url}/api/v2/stocks/quote",
                params={"symbols": ",".join(clean)},
                headers=headers,
            )
        except MarketDataRequestError:
            payload = self.http.get_json(
                f"{self.base_url}/api/quote/{','.join(clean)}",
                headers=headers,
            )
        records = self._records(payload)
        return [self._normalize(record) for record in records]

    def intraday(self, symbol: str, *, interval: str = "5m", days: int = 5) -> list[dict[str, Any]]:
        clean = symbol.strip().upper().removesuffix(".SA")
        payload = self.http.get_json(
            f"{self.base_url}/api/v2/stocks/historical",
            params={
                "symbols": clean,
                "range": f"{max(2, min(days, 5))}d",
                "interval": interval,
                "sortOrder": "asc",
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        records = payload.get("results", []) if isinstance(payload, dict) else []
        if not records or not isinstance(records[0], dict):
            return []
        details = records[0].get("data") if isinstance(records[0].get("data"), dict) else records[0]
        rows = details.get("historicalDataPrice") or details.get("historicalData") or []
        return [self._normalize_intraday(item) for item in rows if isinstance(item, dict)]

    @staticmethod
    def _normalize_intraday(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": item.get("date", item.get("timestamp")),
            "open": number(item.get("open")),
            "high": number(item.get("high")),
            "low": number(item.get("low")),
            "close": number(item.get("close", item.get("price"))),
            "volume": number(item.get("volume")) or 0.0,
        }

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "data", "stocks", "quotes"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                for nested_key in ("results", "data", "stocks", "quotes"):
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        return [item for item in nested if isinstance(item, dict)]
        return [payload] if payload.get("symbol") or payload.get("stock") else []

    def _normalize(self, item: dict[str, Any]) -> NormalizedQuote:
        collected_at = utc_now()
        details = item.get("data") if isinstance(item.get("data"), dict) else item
        symbol = str(
            item.get("symbol")
            or item.get("requestedSymbol")
            or details.get("symbol")
            or details.get("stock")
            or details.get("ticker")
            or ""
        ).upper()
        price = require_price(details.get("regularMarketPrice", details.get("close", details.get("price"))), symbol)
        quote = NormalizedQuote(
            provider="brapi",
            symbol=symbol,
            provider_symbol=symbol,
            exchange=str(details.get("exchange") or details.get("exchangeName") or "B3"),
            currency=str(details.get("currency") or "BRL"),
            price=price,
            change=number(details.get("regularMarketChange", details.get("change"))),
            change_percent=number(details.get("regularMarketChangePercent", details.get("changePercent", details.get("change_p")))),
            open=number(details.get("regularMarketOpen", details.get("open"))),
            low=number(details.get("regularMarketDayLow", details.get("low"))),
            high=number(details.get("regularMarketDayHigh", details.get("high"))),
            previous_close=number(details.get("regularMarketPreviousClose", details.get("previousClose"))),
            volume=number(details.get("regularMarketVolume", details.get("volume"))),
            market_cap=number(details.get("marketCap", details.get("market_cap_basic"))),
            as_of=from_unix(details.get("regularMarketTime", details.get("updatedAt", details.get("timestamp"))), collected_at),
            collected_at=collected_at,
            quality_score=76,
            is_delayed=True,
        )
        quote.quality_score = quality_for(quote)
        return quote
