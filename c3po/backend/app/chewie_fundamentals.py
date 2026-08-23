from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Literal

from .config import Settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient


ChewieMarket = Literal["B3", "NASDAQ", "NYSE"]

CACHE_MINUTES = 30
MAX_SYMBOLS_PER_MARKET = 150

_UNIVERSE_SNAPSHOT_KEY: dict[ChewieMarket, str] = {
    "B3": "B3_UNIVERSE",
    "NASDAQ": "NASDAQ_UNIVERSE",
    "NYSE": "NYSE_UNIVERSE",
}
_PROVIDER_EXCHANGE: dict[ChewieMarket, str] = {
    "B3": "SA",
    "NASDAQ": "US",
    "NYSE": "US",
}


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _percent(value: Any) -> float | None:
    parsed = _number(value)
    return round(parsed * 100, 2) if parsed is not None else None


class ChewieFundamentalsService:
    """Read-only fundamentals table blending FMP/Brapi/EODHD-sourced ratios
    already computed for the tracked B3/NASDAQ/NYSE universe.

    This never feeds valuation, screening or trading decisions -- it only
    re-reads the persisted universe snapshot for the symbol/name/sector list
    and fetches EODHD fundamentals for display.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.client = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self._lock = Lock()
        self._cache: dict[ChewieMarket, tuple[datetime, dict[str, Any]]] = {}

    def rows(self, market: ChewieMarket, *, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            cached = self._cache.get(market)
            if cached and not refresh:
                cached_at, payload = cached
                age_minutes = (datetime.now(timezone.utc) - cached_at).total_seconds() / 60
                if age_minutes < CACHE_MINUTES:
                    return payload
            payload = self._build(market)
            self._cache[market] = (datetime.now(timezone.utc), payload)
            return payload

    def _build(self, market: ChewieMarket) -> dict[str, Any]:
        snapshot = self.database.latest_analysis_snapshot(
            "valuation_universe", _UNIVERSE_SNAPSHOT_KEY[market]
        )
        outputs = snapshot.get("outputs") if snapshot else None
        universe_rows = outputs.get("rows") if isinstance(outputs, dict) else None
        universe_rows = universe_rows if isinstance(universe_rows, list) else []

        stocks = [
            row for row in universe_rows
            if isinstance(row, dict) and row.get("security_type") == "Stock" and row.get("symbol")
        ]
        stocks.sort(key=lambda row: _number(row.get("market_cap")) or 0.0, reverse=True)
        selected = stocks[:MAX_SYMBOLS_PER_MARKET]
        symbols = [str(row["symbol"]) for row in selected]

        fundamentals_by_symbol = (
            self.client.fundamentals(symbols, exchange=_PROVIDER_EXCHANGE[market], workers=10)
            if symbols else {}
        )

        items = []
        for row in selected:
            symbol = str(row["symbol"])
            fundamentals = fundamentals_by_symbol.get(symbol) or {}
            items.append(self._item(market, row, fundamentals))

        return {
            "market": market,
            "source": "EODHD Fundamentals",
            "universe_size": len(stocks),
            "covered_count": len(items),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }

    @staticmethod
    def _item(market: ChewieMarket, row: dict[str, Any], fundamentals: dict[str, Any]) -> dict[str, Any]:
        total_debt = _number(fundamentals.get("totalDebt"))
        total_cash = _number(fundamentals.get("totalCash"))
        ebitda = _number(fundamentals.get("ebitda"))
        net_debt = (total_debt - total_cash) if total_debt is not None and total_cash is not None else None
        net_debt_to_ebitda = round(net_debt / ebitda, 2) if net_debt is not None and ebitda else None
        return {
            "market": market,
            "symbol": str(row.get("symbol")),
            "name": str(fundamentals.get("companyName") or row.get("name") or row.get("symbol")),
            "sector": str(row.get("sector") or fundamentals.get("sector") or "Unclassified"),
            "logo_url": EodhdClient.normalize_logo_url(fundamentals.get("logoUrl")) or row.get("logo_url"),
            "market_cap": _number(row.get("market_cap")) or _number(fundamentals.get("marketCap")),
            "fundamentals_as_of": fundamentals.get("financialsAsOf") or fundamentals.get("updated_at"),
            "multiples": {
                "pe": _number(fundamentals.get("trailingPE")),
                "forward_pe": _number(fundamentals.get("forwardPE")),
                "ev_ebitda": _number(fundamentals.get("enterpriseToEbitda")),
                "peg": _number(fundamentals.get("pegRatio")),
                "price_to_book": _number(fundamentals.get("priceToBook")),
            },
            "profitability": {
                "roe_percent": _percent(fundamentals.get("returnOnEquity")),
                "roa_percent": _percent(fundamentals.get("returnOnAssets")),
                "profit_margin_percent": _percent(fundamentals.get("profitMargins")),
                "operating_margin_percent": _percent(fundamentals.get("operatingMargins")),
                "ebitda_margin_percent": _percent(fundamentals.get("ebitdaMargins")),
            },
            "leverage": {
                "debt_to_equity": _number(fundamentals.get("debtToEquity")),
                "net_debt_to_ebitda": net_debt_to_ebitda,
                "total_cash": total_cash,
                "total_debt": total_debt,
            },
            "growth": {
                "revenue_growth_percent": _percent(fundamentals.get("revenueGrowthAnnual")),
                "earnings_growth_percent": _percent(fundamentals.get("earningsGrowthAnnual")),
            },
        }
