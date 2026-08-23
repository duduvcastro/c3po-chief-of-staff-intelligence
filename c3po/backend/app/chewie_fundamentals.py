from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from threading import Lock
from typing import Any, Literal
import unicodedata

from .config import Settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.fmp import FmpClient
from .market_data.http import JsonHttpClient


ChewieMarket = Literal["B3", "NASDAQ", "NYSE"]

ANALYSIS_TYPE = "chewie_fundamentals"
METHODOLOGY_KEY = "chewie_fundamentals_daily"
METHODOLOGY_VERSION = 1
TOP_DISPLAY = 30
SEARCH_LIMIT = 12
ADHOC_CACHE_HOURS = 24
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")

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


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


class ChewieFundamentalsService:
    """Daily fundamentals snapshot for the tracked B3/NASDAQ/NYSE stock universe.

    The snapshot is refreshed once per day by the valuation worker; requests
    only read persisted data. Search falls back to a live single-symbol lookup
    for stocks outside the tracked universe. This never feeds valuation,
    screening or trading decisions.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.client = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self.fmp = FmpClient(settings.fmp_base_url, settings.fmp_api_token, http)
        self._lock = Lock()
        self._bootstrap_cache: dict[ChewieMarket, tuple[datetime, dict[str, Any]]] = {}
        self._adhoc_cache: dict[tuple[ChewieMarket, str], tuple[datetime, dict[str, Any] | None]] = {}

    # ------------------------------------------------------------------ daily

    def refresh_daily(self, market: ChewieMarket) -> int:
        """Fetch fundamentals for the FULL stock universe and persist a snapshot."""
        stocks = self._universe_stocks(market)
        symbols = [str(row["symbol"]) for row in stocks]
        fundamentals_by_symbol = (
            self.client.fundamentals(symbols, exchange=_PROVIDER_EXCHANGE[market], workers=10)
            if symbols else {}
        )
        items = []
        for row in stocks:
            fundamentals = fundamentals_by_symbol.get(str(row["symbol"])) or {}
            items.append(self._item(market, row, fundamentals))
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {"cadence": "daily", "scope": "display-only fundamentals"},
            "Daily EODHD fundamentals snapshot for the Chewie Fundamentals tab.",
        )
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            f"{market}_FUNDAMENTALS",
            methodology_id,
            {"market": market, "universe_size": len(stocks)},
            {"items": items, "universe_size": len(stocks)},
            datetime.now(timezone.utc),
        )
        return len(items)

    def refresh_all(self) -> dict[str, int]:
        return {market: self.refresh_daily(market) for market in ("B3", "NASDAQ", "NYSE")}

    def has_snapshot(self, market: ChewieMarket) -> bool:
        return self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_FUNDAMENTALS") is not None

    def last_refreshed_at(self) -> datetime | None:
        """Oldest published_at across the three market snapshots, or None."""
        stamps: list[datetime] = []
        for market in ("B3", "NASDAQ", "NYSE"):
            snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_FUNDAMENTALS")
            published = snapshot.get("published_at") if snapshot else None
            if not isinstance(published, datetime):
                return None
            stamps.append(published if published.tzinfo else published.replace(tzinfo=timezone.utc))
        return min(stamps)

    # ------------------------------------------------------------------ reads

    def rows(self, market: ChewieMarket) -> dict[str, Any]:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_FUNDAMENTALS")
        if snapshot:
            outputs = snapshot.get("outputs") or {}
            items = outputs.get("items") if isinstance(outputs, dict) else None
            items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
            published_at = snapshot.get("published_at")
            generated_at = (
                published_at.isoformat()
                if isinstance(published_at, datetime)
                else str(published_at or datetime.now(timezone.utc).isoformat())
            )
            return {
                "market": market,
                "source": "EODHD Fundamentals · daily snapshot",
                "universe_size": int(outputs.get("universe_size") or len(items)),
                "covered_count": len(items),
                "generated_at": generated_at,
                "items": items[:TOP_DISPLAY],
            }
        return self._bootstrap_rows(market)

    def search(self, market: ChewieMarket, query: str) -> dict[str, Any]:
        clean = query.strip()
        folded = _fold(clean)
        matches: list[dict[str, Any]] = []
        if folded:
            snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_FUNDAMENTALS")
            outputs = snapshot.get("outputs") if snapshot else None
            items = outputs.get("items") if isinstance(outputs, dict) else None
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                symbol = _fold(str(item.get("symbol") or ""))
                name = _fold(str(item.get("name") or ""))
                if symbol.startswith(folded) or folded in name:
                    matches.append({**item, "from_universe": True})
                if len(matches) >= SEARCH_LIMIT:
                    break
            matches.sort(key=lambda item: (not _fold(str(item.get("symbol"))).startswith(folded), -(item.get("market_cap") or 0.0)))
        if not matches:
            adhoc = self._adhoc_lookup(market, clean)
            if adhoc:
                matches = [{**adhoc, "from_universe": False}]
        return {"market": market, "query": clean, "items": matches[:SEARCH_LIMIT]}

    # ------------------------------------------------------------------ pdf

    def report_payload(self, market: ChewieMarket, symbol: str) -> dict[str, Any] | None:
        """Fresh full fundamentals for one symbol, shaped for the PDF renderer."""
        clean = symbol.strip().upper()
        if not SYMBOL_PATTERN.fullmatch(clean):
            return None
        fundamentals = self.client.fundamentals(
            [clean], exchange=_PROVIDER_EXCHANGE[market], workers=1
        ).get(clean)
        if not fundamentals:
            return None
        price = self._latest_price(market, clean)
        universe_row = next(
            (row for row in self._universe_stocks(market) if str(row.get("symbol")) == clean),
            {},
        )
        return {
            "market": market,
            "symbol": clean,
            "fundamentals": fundamentals,
            "item": self._item(market, universe_row or {"symbol": clean}, fundamentals),
            "price": price,
            "currency": "BRL" if market == "B3" else "USD",
            "fmp_consensus": self._fmp_consensus(market, clean),
            "news_sentiment": self._news_sentiment(market, clean),
        }

    def _fmp_consensus(self, market: ChewieMarket, symbol: str) -> dict[str, float] | None:
        if not self.settings.fmp_api_token:
            return None
        provider_symbol = f"{symbol}.SA" if market == "B3" else symbol
        return self.fmp.price_target_consensus(provider_symbol)

    def _news_sentiment(self, market: ChewieMarket, symbol: str) -> dict[str, Any] | None:
        if market == "B3" or not self.settings.finnhub_api_token:
            return None
        try:
            import httpx

            from .market_data.finnhub import FinnhubClient

            with httpx.Client(timeout=10) as client:
                finnhub = FinnhubClient(
                    self.settings.finnhub_base_url, self.settings.finnhub_api_token, client
                )
                return finnhub.news_sentiment(symbol)
        except Exception:
            return None

    def render_report(self, market: ChewieMarket, symbol: str) -> Path | None:
        payload = self.report_payload(market, symbol)
        if payload is None:
            return None
        from .chewie_pdf import ChewieFundamentalsPdfRenderer

        output_dir = self.settings.one_pager_output_dir.parent / "chewie-reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{payload['symbol']}-{market}-fundamentals.pdf"
        ChewieFundamentalsPdfRenderer().render(path, payload, datetime.now(timezone.utc))
        return path

    # ------------------------------------------------------------------ internals

    def _universe_stocks(self, market: ChewieMarket) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            "valuation_universe", _UNIVERSE_SNAPSHOT_KEY[market]
        )
        outputs = snapshot.get("outputs") if snapshot else None
        rows = outputs.get("rows") if isinstance(outputs, dict) else None
        rows = rows if isinstance(rows, list) else []
        stocks = [
            row for row in rows
            if isinstance(row, dict) and row.get("security_type") == "Stock" and row.get("symbol")
        ]
        stocks.sort(key=lambda row: _number(row.get("market_cap")) or 0.0, reverse=True)
        return stocks

    def _bootstrap_rows(self, market: ChewieMarket) -> dict[str, Any]:
        """Before the first nightly cycle, build the display page live (top 30 only)."""
        with self._lock:
            cached = self._bootstrap_cache.get(market)
            if cached:
                cached_at, payload = cached
                if datetime.now(timezone.utc) - cached_at < timedelta(minutes=30):
                    return payload
            stocks = self._universe_stocks(market)
            selected = stocks[:TOP_DISPLAY]
            symbols = [str(row["symbol"]) for row in selected]
            fundamentals_by_symbol = (
                self.client.fundamentals(symbols, exchange=_PROVIDER_EXCHANGE[market], workers=10)
                if symbols else {}
            )
            items = [
                self._item(market, row, fundamentals_by_symbol.get(str(row["symbol"])) or {})
                for row in selected
            ]
            payload = {
                "market": market,
                "source": "EODHD Fundamentals · bootstrap (aguardando ciclo diário)",
                "universe_size": len(stocks),
                "covered_count": len(items),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "items": items,
            }
            self._bootstrap_cache[market] = (datetime.now(timezone.utc), payload)
            return payload

    def _adhoc_lookup(self, market: ChewieMarket, query: str) -> dict[str, Any] | None:
        symbol = query.upper().replace(" ", "")
        if not SYMBOL_PATTERN.fullmatch(symbol):
            return None
        key = (market, symbol)
        with self._lock:
            cached = self._adhoc_cache.get(key)
            if cached:
                cached_at, item = cached
                if datetime.now(timezone.utc) - cached_at < timedelta(hours=ADHOC_CACHE_HOURS):
                    return item
        fundamentals = self.client.fundamentals(
            [symbol], exchange=_PROVIDER_EXCHANGE[market], workers=1
        ).get(symbol)
        item = None
        if fundamentals and fundamentals.get("companyName"):
            item = self._item(market, {"symbol": symbol}, fundamentals)
        with self._lock:
            self._adhoc_cache[key] = (datetime.now(timezone.utc), item)
        return item

    def _latest_price(self, market: ChewieMarket, symbol: str) -> dict[str, Any] | None:
        try:
            quotes = self.client.quotes([f"{symbol}.{_PROVIDER_EXCHANGE[market]}"])
        except Exception:
            return None
        if not quotes:
            return None
        quote = quotes[0]
        return {
            "price": _number(getattr(quote, "price", None)),
            "change_percent": _number(getattr(quote, "change_percent", None)),
            "as_of": getattr(quote, "as_of", None),
        }

    @staticmethod
    def _item(market: ChewieMarket, row: dict[str, Any], fundamentals: dict[str, Any]) -> dict[str, Any]:
        total_debt = _number(fundamentals.get("totalDebt"))
        total_cash = _number(fundamentals.get("totalCash"))
        ebitda = _number(fundamentals.get("ebitda"))
        net_debt = (total_debt - total_cash) if total_debt is not None and total_cash is not None else None
        net_debt_to_ebitda = round(net_debt / ebitda, 2) if net_debt is not None and ebitda else None

        # The nightly screeners already blend and cross-validate multiples
        # (Brapi + EODHD + official CVM overlay on B3; validated EODHD on US),
        # so universe-row values take precedence over the raw provider payload.
        blend_used = any(
            _number(row.get(key)) is not None
            for key in ("pe", "forward_pe", "ev_ebitda", "price_to_book")
        )
        sources = []
        if blend_used:
            sources.append("Screener blend (Brapi + EODHD + CVM)" if market == "B3" else "Screener validated")
        if fundamentals:
            sources.append("EODHD")

        return {
            "market": market,
            "symbol": str(row.get("symbol")),
            "name": str(fundamentals.get("companyName") or row.get("name") or row.get("symbol")),
            "sector": str(row.get("sector") or fundamentals.get("sector") or "Unclassified"),
            "logo_url": EodhdClient.normalize_logo_url(fundamentals.get("logoUrl")) or row.get("logo_url"),
            "market_cap": _number(row.get("market_cap")) or _number(fundamentals.get("marketCap")),
            "fundamentals_as_of": fundamentals.get("financialsAsOf") or fundamentals.get("updated_at"),
            "sources": sources,
            "multiples": {
                "pe": _number(row.get("pe")) or _number(fundamentals.get("trailingPE")),
                "forward_pe": _number(row.get("forward_pe")) or _number(fundamentals.get("forwardPE")),
                "ev_ebitda": _number(row.get("ev_ebitda")) or _number(fundamentals.get("enterpriseToEbitda")),
                "peg": _number(row.get("peg")) or _number(fundamentals.get("pegRatio")),
                "price_to_book": _number(row.get("price_to_book")) or _number(fundamentals.get("priceToBook")),
                "dividend_yield_percent": (
                    _percent(row.get("dividend_yield"))
                    or _percent(fundamentals.get("dividendYield"))
                ),
            },
            "profitability": {
                "roe_percent": _number(row.get("roe_percent")) or _percent(fundamentals.get("returnOnEquity")),
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
