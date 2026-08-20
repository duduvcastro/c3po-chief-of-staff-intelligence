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

    def treasury_rates(self, *, indexer: str = "prefixado", limit: int = 20) -> list[dict[str, Any]]:
        """Currently-offered Tesouro Direto bonds, sorted by maturity
        (longest first) -- a real market-observed long-term BRL yield
        curve (Brapi Pro plan), unlike the policy-rate Selic figure
        b3_screener.py's _effective_selic() already uses. "prefixado"
        bonds quote a plain nominal annualized yield in buyRate/sellRate
        (unlike Tesouro Selic, whose buyRate/sellRate are a spread over
        Selic, not a standalone rate) -- see rateInfo.rateType on each
        result if using a different indexer. Returns [] on any failure;
        callers must never let this break the caller's own risk-free
        calculation."""
        try:
            payload = self.http.get_json(
                f"{self.base_url}/api/v2/treasury/list",
                params={"indexer": indexer, "sortBy": "maturityDate", "sortOrder": "desc", "limit": limit},
                headers={"Authorization": f"Bearer {self.token}"},
            )
        except Exception:
            return []
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        output: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            buy_rate = number(row.get("buyRate"))
            sell_rate = number(row.get("sellRate"))
            if buy_rate is None and sell_rate is None:
                continue
            output.append({
                "symbol": str(row.get("symbol") or ""),
                "bond_type": str(row.get("bondType") or ""),
                "indexer": str(row.get("indexer") or ""),
                "maturity_date": str(row.get("maturityDate") or ""),
                "duration_days": int(number(row.get("durationDays")) or 0),
                "buy_rate": buy_rate,
                "sell_rate": sell_rate,
            })
        return output

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
