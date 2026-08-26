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
METHODOLOGY_VERSION = 2
TOP_DISPLAY = 30
SEARCH_LIMIT = 12
ADHOC_CACHE_HOURS = 24
LISTING_CACHE_HOURS = 20
DEFAULT_DAILY_SYMBOL_BUDGET = 2_500
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


def _is_common_stock(row: dict[str, Any]) -> bool:
    security_type = str(row.get("Type") or row.get("type") or "").upper()
    if not security_type:
        return True
    excluded = ("ETF", "FUND", "INDEX", "NOTE", "BOND", "WARRANT", "RIGHT", "PREFERRED")
    return not any(value in security_type for value in excluded)


def _us_listing_market(row: dict[str, Any]) -> str | None:
    exchange = " ".join(
        str(row.get(key) or "") for key in ("Exchange", "ExchangeCode", "exchange")
    ).upper()
    if "NASDAQ" in exchange or "XNAS" in exchange:
        return "NASDAQ"
    if ("NYSE" in exchange or "XNYS" in exchange) and not any(
        value in exchange for value in ("ARCA", "AMERICAN", "MKT")
    ):
        return "NYSE"
    return None


class ChewieFundamentalsService:
    """Daily fundamentals snapshot for the FULL B3/NASDAQ/NYSE stock listings.

    The complete exchange listing (~400 B3 + thousands of US common stocks)
    is covered through a nightly refresh budget: B3 refreshes whole every
    night, the US listings rotate in cohorts until every symbol is covered
    and then keep cycling oldest-first, while the visible top 30 refresh
    daily. Requests only read the persisted snapshot; search falls back to
    a live single-symbol lookup for anything not yet covered. This never
    feeds valuation, screening or trading decisions.
    """

    def __init__(self, settings: Settings, database: Database, http: JsonHttpClient) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        self.client = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token, http)
        self.fmp = FmpClient(settings.fmp_base_url, settings.fmp_api_token, http)
        self._lock = Lock()
        self._bootstrap_cache: dict[ChewieMarket, tuple[datetime, dict[str, Any]]] = {}
        self._adhoc_cache: dict[tuple[ChewieMarket, str], tuple[datetime, dict[str, Any] | None]] = {}
        self._listing_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}

    # ------------------------------------------------------------------ daily

    def refresh_daily(self, market: ChewieMarket, *, budget: int | None = None) -> dict[str, int]:
        """Refresh up to ``budget`` symbols of the full listing and persist the
        merged snapshot. ``budget=None`` refreshes the entire listing."""
        if market == "B3":
            return self._refresh_daily_b3()
        listing = self._full_listing(market)
        listing_by_symbol = {row["symbol"]: row for row in listing}
        previous = self._snapshot_items(market)
        previous_by_symbol = {
            str(item.get("symbol")): item
            for item in previous
            if str(item.get("symbol")) in listing_by_symbol
        }

        queue: list[str] = []
        seen: set[str] = set()

        def enqueue(symbol: str) -> None:
            if symbol in listing_by_symbol and symbol not in seen:
                queue.append(symbol)
                seen.add(symbol)

        top_current = sorted(
            previous_by_symbol.values(),
            key=lambda item: _number(item.get("market_cap")) or 0.0,
            reverse=True,
        )[:TOP_DISPLAY]
        for item in top_current:
            enqueue(str(item.get("symbol")))
        for row in listing:
            if row["symbol"] not in previous_by_symbol:
                enqueue(row["symbol"])
        for item in sorted(
            previous_by_symbol.values(), key=lambda value: str(value.get("refreshed_at") or "")
        ):
            enqueue(str(item.get("symbol")))

        selected = queue if budget is None else queue[: max(0, int(budget))]
        universe_rows = {str(row.get("symbol")): row for row in self._universe_stocks(market)}
        fundamentals_by_symbol = (
            self.client.fundamentals(selected, exchange=_PROVIDER_EXCHANGE[market], workers=10)
            if selected else {}
        )
        refreshed_at = datetime.now(timezone.utc).isoformat()
        refreshed = 0
        for symbol in selected:
            fundamentals = fundamentals_by_symbol.get(symbol)
            if not fundamentals:
                continue
            row = universe_rows.get(symbol) or {
                "symbol": symbol,
                "name": listing_by_symbol[symbol].get("name"),
            }
            item = self._item(market, row, fundamentals)
            item["refreshed_at"] = refreshed_at
            previous_by_symbol[symbol] = item
            refreshed += 1

        merged = sorted(
            previous_by_symbol.values(),
            key=lambda item: _number(item.get("market_cap")) or 0.0,
            reverse=True,
        )
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {"cadence": "daily-budgeted", "scope": "full exchange listing, display-only"},
            "Daily budgeted EODHD fundamentals snapshot over the full exchange listing.",
        )
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            f"{market}_FUNDAMENTALS",
            methodology_id,
            {"market": market, "universe_size": len(listing), "refreshed": refreshed},
            {"items": merged, "universe_size": len(listing), "source": "EODHD Fundamentals"},
            datetime.now(timezone.utc),
        )
        return {"universe": len(listing), "covered": len(merged), "refreshed": refreshed}

    def _refresh_daily_b3(self) -> dict[str, int]:
        """B3 fundamentals come from the tracked B3 screener universe, which
        is already sourced from Brapi's stock catalog (real B3-listed common
        and preferred shares only -- fractional-lot tickers and Nasdaq/NYSE
        BDR wrappers are excluded upstream) with an official CVM/EODHD
        overlay. No separate listing or fundamentals fetch is needed."""
        universe_rows = self._universe_stocks("B3")
        items = [self._item_from_b3_universe_row(row) for row in universe_rows]
        methodology_id = self.database.ensure_methodology_version(
            METHODOLOGY_KEY,
            METHODOLOGY_VERSION,
            {"cadence": "daily", "scope": "B3 tracked universe (Brapi-sourced), display-only"},
            "Daily B3 fundamentals snapshot sourced from the Brapi-backed screener universe.",
        )
        self.database.save_analysis_snapshot(
            ANALYSIS_TYPE,
            "B3_FUNDAMENTALS",
            methodology_id,
            {"market": "B3", "universe_size": len(items), "refreshed": len(items)},
            {"items": items, "universe_size": len(items), "source": "Brapi Pro + EODHD overlay"},
            datetime.now(timezone.utc),
        )
        return {"universe": len(items), "covered": len(items), "refreshed": len(items)}

    def refresh_all(self, *, budget: int | None = None) -> dict[str, dict[str, int]]:
        total = DEFAULT_DAILY_SYMBOL_BUDGET if budget is None else max(0, int(budget))
        counts: dict[str, dict[str, int]] = {}
        # B3 is read straight from the already-fetched screener universe, so
        # it costs zero EODHD fundamentals calls and never eats the US budget.
        counts["B3"] = self.refresh_daily("B3")
        remaining = total
        needs = {
            market: max(1, self._pending_count(market))
            for market in ("NASDAQ", "NYSE")
        }
        need_total = sum(needs.values())
        nasdaq_budget = round(remaining * needs["NASDAQ"] / need_total) if need_total else 0
        counts["NASDAQ"] = self.refresh_daily("NASDAQ", budget=nasdaq_budget)
        counts["NYSE"] = self.refresh_daily("NYSE", budget=max(0, remaining - counts["NASDAQ"]["refreshed"]))
        return counts

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
            default_source = "Brapi Pro + EODHD overlay" if market == "B3" else "EODHD Fundamentals"
            return {
                "market": market,
                "source": f"{outputs.get('source') or default_source} · daily snapshot",
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
            for item in self._snapshot_items(market):
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
            adhoc = self._adhoc_from_query(market, clean, folded)
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

    # ------------------------------------------------------------------ internals

    def _full_listing(self, market: ChewieMarket) -> list[dict[str, Any]]:
        """Complete common-stock listing for the market, cached for the day."""
        exchange = _PROVIDER_EXCHANGE[market]
        with self._lock:
            cached = self._listing_cache.get(exchange)
        if cached is None or datetime.now(timezone.utc) - cached[0] >= timedelta(hours=LISTING_CACHE_HOURS):
            payload = self.http.get_json(
                f"{self.settings.eodhd_base_url.rstrip('/')}/api/exchange-symbol-list/{exchange}",
                params={"api_token": self.settings.eodhd_api_token, "fmt": "json"},
            )
            rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
            rows = [row for row in rows if isinstance(row, dict)]
            with self._lock:
                self._listing_cache[exchange] = (datetime.now(timezone.utc), rows)
            cached = (datetime.now(timezone.utc), rows)
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in cached[1]:
            if not _is_common_stock(row):
                continue
            if exchange == "US" and _us_listing_market(row) != market:
                continue
            symbol = str(row.get("Code") or row.get("code") or "").upper().removesuffix(".US").removesuffix(".SA")
            if not symbol or symbol in seen or not SYMBOL_PATTERN.fullmatch(symbol):
                continue
            seen.add(symbol)
            output.append({"symbol": symbol, "name": str(row.get("Name") or row.get("name") or symbol)})
        return output

    def _snapshot_items(self, market: ChewieMarket) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(ANALYSIS_TYPE, f"{market}_FUNDAMENTALS")
        outputs = snapshot.get("outputs") if snapshot else None
        items = outputs.get("items") if isinstance(outputs, dict) else None
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _pending_count(self, market: ChewieMarket) -> int:
        listing = self._full_listing(market)
        covered = {str(item.get("symbol")) for item in self._snapshot_items(market)}
        return sum(1 for row in listing if row["symbol"] not in covered)

    def _universe_stocks(self, market: ChewieMarket) -> list[dict[str, Any]]:
        snapshot = self.database.latest_analysis_snapshot(
            "valuation_universe", _UNIVERSE_SNAPSHOT_KEY[market]
        )
        outputs = snapshot.get("outputs") if snapshot else None
        rows = outputs.get("rows") if isinstance(outputs, dict) else None
        rows = rows if isinstance(rows, list) else []
        # The B3 universe is stocks-only by construction (Brapi
        # type=stock/subType=stock) and never sets "security_type"; only the
        # US universe tags "Stock" vs "ETF" rows and needs the filter.
        stocks = [
            row for row in rows
            if isinstance(row, dict)
            and row.get("symbol")
            and (market == "B3" or row.get("security_type") == "Stock")
        ]
        stocks.sort(key=lambda row: _number(row.get("market_cap")) or 0.0, reverse=True)
        return stocks

    def _bootstrap_rows(self, market: ChewieMarket) -> dict[str, Any]:
        """Before the first nightly cycle, build the display page live (top 30
        of the tracked screener universe only -- deliberately light)."""
        with self._lock:
            cached = self._bootstrap_cache.get(market)
            if cached:
                cached_at, payload = cached
                if datetime.now(timezone.utc) - cached_at < timedelta(minutes=30):
                    return payload
        stocks = self._universe_stocks(market)
        selected = stocks[:TOP_DISPLAY]
        if market == "B3":
            items = [self._item_from_b3_universe_row(row) for row in selected]
            source = "Brapi Pro + EODHD overlay"
        else:
            symbols = [str(row["symbol"]) for row in selected]
            fundamentals_by_symbol = (
                self.client.fundamentals(symbols, exchange=_PROVIDER_EXCHANGE[market], workers=10)
                if symbols else {}
            )
            items = [
                self._item(market, row, fundamentals_by_symbol.get(str(row["symbol"])) or {})
                for row in selected
            ]
            source = "EODHD Fundamentals"
        payload = {
            "market": market,
            "source": f"{source} · bootstrap (aguardando ciclo diário)",
            "universe_size": len(stocks),
            "covered_count": len(items),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
        }
        with self._lock:
            self._bootstrap_cache[market] = (datetime.now(timezone.utc), payload)
        return payload

    def _adhoc_from_query(self, market: ChewieMarket, query: str, folded: str) -> dict[str, Any] | None:
        """Live lookup for anything not yet covered by the snapshot: resolve
        the query against the full listing (name or ticker), then fetch.

        B3 deliberately skips the raw EODHD exchange listing here -- it is
        noisy with fractional-lot tickers and Nasdaq/NYSE BDR wrappers, which
        is exactly what must NOT show up under the B3 tab. A ticker-shaped
        query is fetched directly; free-text company names outside the
        tracked Brapi universe are not resolved for B3.
        """
        candidate = query.upper().replace(" ", "")
        if not SYMBOL_PATTERN.fullmatch(candidate):
            candidate = ""
        listing: list[dict[str, Any]] = []
        if market != "B3":
            try:
                listing = self._full_listing(market)
            except Exception:
                listing = []
        if listing:
            symbols = {row["symbol"] for row in listing}
            if candidate not in symbols:
                match = next(
                    (
                        row for row in listing
                        if _fold(row["symbol"]).startswith(folded) or folded in _fold(str(row["name"]))
                    ),
                    None,
                )
                candidate = match["symbol"] if match else candidate
        if not candidate:
            return None
        return self._adhoc_lookup(market, candidate)

    def _adhoc_lookup(self, market: ChewieMarket, symbol: str) -> dict[str, Any] | None:
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
    def _item_from_b3_universe_row(row: dict[str, Any]) -> dict[str, Any]:
        """Shape a B3 screener universe row (Brapi-primary, EODHD/CVM overlay
        already blended in) directly into a display item -- no extra fetch."""
        cash = _number(row.get("cash"))
        debt = _number(row.get("debt"))
        ebitda = _number(row.get("ebitda"))
        net_debt = (debt - cash) if debt is not None and cash is not None else None
        net_debt_to_ebitda = round(net_debt / ebitda, 2) if net_debt is not None and ebitda else None
        sources = ["Brapi"]
        if int(row.get("data_source_count") or 1) >= 2:
            sources.append("EODHD overlay")
        return {
            "market": "B3",
            "symbol": str(row.get("symbol")),
            "name": str(row.get("name") or row.get("symbol")),
            "sector": str(row.get("sector") or "Unclassified"),
            "logo_url": row.get("logo_url"),
            "market_cap": _number(row.get("market_cap")),
            "fundamentals_as_of": row.get("fundamentals_as_of"),
            "sources": sources,
            "multiples": {
                "pe": _number(row.get("pe")),
                "forward_pe": _number(row.get("forward_pe")),
                "ev_ebitda": _number(row.get("ev_ebitda")),
                "peg": _number(row.get("peg")),
                "price_to_book": _number(row.get("price_to_book")),
                "dividend_yield_percent": _percent(row.get("dividend_yield")),
            },
            "profitability": {
                "ebitda": ebitda,
                "roe_percent": _percent(row.get("roe")),
                "roa_percent": None,
                "profit_margin_percent": _percent(row.get("profit_margin")),
                "operating_margin_percent": None,
                "ebitda_margin_percent": _percent(row.get("ebitda_margin")),
            },
            "leverage": {
                "debt_to_equity": _number(row.get("debt_to_equity")),
                "net_debt_to_ebitda": net_debt_to_ebitda,
                "total_cash": cash,
                "total_debt": debt,
            },
            "growth": {
                "revenue_growth_percent": _percent(row.get("revenue_growth")),
                "earnings_growth_percent": _percent(row.get("earnings_growth")),
            },
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
                "ebitda": ebitda,
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
