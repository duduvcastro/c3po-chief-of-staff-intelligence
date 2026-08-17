from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from threading import RLock
from typing import Any
import unicodedata
from urllib.parse import quote
from zoneinfo import ZoneInfo

from ..config import Settings
from ..database import Database
from ..schemas import (
    InstrumentIntradayResponse,
    NormalizedQuote,
    RealtimeMarketIndex,
    RealtimeMarketLeader,
    RealtimeMarketResponse,
    RealtimePortfolioIntradayPoint,
    RealtimePortfolioIntradayResponse,
    RealtimePortfolioItem,
    RealtimePortfolioResponse,
    RealtimePortfolioSymbolSearchResponse,
    RealtimePortfolioSymbolSuggestion,
)
from .brapi import BrapiClient
from .eodhd import EodhdClient
from .http import JsonHttpClient
from .eodhd_stream import EodhdRealtimeStream
from .models import canonical_us_security_name, canonical_us_security_type, from_unix, number
from .live_markets import MARKET_SPECS as LIVE_MARKET_SPECS


REFRESH_SECONDS = 60
STREAM_REFRESH_SECONDS = 3
CACHE_SECONDS = 55
SYMBOL_CATALOG_SECONDS = 24 * 60 * 60
MAX_STREAM_PRICE_DEVIATION = 0.35


@dataclass(frozen=True)
class RealtimeMarketSpec:
    market: str
    index_symbol: str
    index_name: str
    index_currency: str


MARKET_SPECS = {
    "B3": RealtimeMarketSpec("B3", "^BVSP", "Ibovespa", "BRL"),
    "NASDAQ": RealtimeMarketSpec("NASDAQ", "^IXIC", "Nasdaq Composite", "USD"),
    "NYSE": RealtimeMarketSpec("NYSE", "^NYA", "NYSE Composite", "USD"),
}


class RealtimeMarketsService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        http: JsonHttpClient,
        stream: EodhdRealtimeStream | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.http = http
        self.stream = stream
        self._lock = RLock()
        self._responses: dict[str, tuple[datetime, RealtimeMarketResponse]] = {}
        self._us_quotes: tuple[datetime, list[dict[str, Any]]] | None = None
        self._us_catalog: tuple[datetime, dict[str, dict[str, Any]]] | None = None
        self._b3_quotes: tuple[datetime, list[RealtimeMarketLeader]] | None = None
        self._us_previous_close: dict[str, float] = {}
        self._portfolio_quotes: dict[str, tuple[datetime, RealtimeMarketLeader]] = {}
        self._intraday_series: dict[str, tuple[datetime, RealtimePortfolioIntradayResponse]] = {}
        self._instrument_intraday_series: dict[str, tuple[datetime, InstrumentIntradayResponse]] = {}

    def snapshot(self, market: str) -> RealtimeMarketResponse:
        normalized = market.strip().upper()
        if normalized not in MARKET_SPECS:
            raise ValueError("Market must be B3, NASDAQ or NYSE")
        now = datetime.now(timezone.utc)
        cached = self._responses.get(normalized)
        if cached and now < cached[0]:
            return self._apply_stream(normalized, cached[1], now)
        with self._lock:
            now = datetime.now(timezone.utc)
            cached = self._responses.get(normalized)
            if cached and now < cached[0]:
                return self._apply_stream(normalized, cached[1], now)
            response = self._build(normalized, now)
            self._responses[normalized] = (now + timedelta(seconds=CACHE_SECONDS), response)
            return self._apply_stream(normalized, response, now)

    def _build(self, market: str, now: datetime) -> RealtimeMarketResponse:
        spec = MARKET_SPECS[market]
        index = self._index_quote(spec)
        if market == "B3":
            rows = self._b3_rows(now)
            source = "Brapi Pro market-wide quote list"
            delay_minutes = 5
        else:
            rows = self._us_rows(market, now)
            source = "EODHD Bulk Live US"
            delay_minutes = 15
        if not rows:
            raise RuntimeError(f"No valid {market} securities returned by the market data provider")

        return RealtimeMarketResponse(
            market=market,
            index=index,
            universe_size=len(rows),
            gainers=self._leaders(rows, "change_percent", reverse=True),
            losers=self._leaders(rows, "change_percent", reverse=False),
            volume_leaders=self._leaders(rows, "volume", reverse=True),
            cash_leaders=self._leaders(rows, "cash_volume", reverse=True),
            source=source,
            delay_minutes=delay_minutes,
            refresh_seconds=REFRESH_SECONDS,
            generated_at=now,
        )

    def portfolio_snapshot(self) -> RealtimePortfolioResponse:
        now = datetime.now(timezone.utc)
        entries = self.database.list_realtime_portfolio()
        if not entries:
            return RealtimePortfolioResponse(
                item_count=0,
                items=[],
                refresh_seconds=REFRESH_SECONDS,
                generated_at=now,
                sources=[],
            )

        us_symbols = [entry["symbol"] for entry in entries if entry["market"] != "B3"]
        if self.stream:
            self.stream.set_group("portfolio", us_symbols, priority=100)

        rows_by_market: dict[str, dict[str, RealtimeMarketLeader]] = {}
        errors: list[str] = []
        for market in sorted({entry["market"] for entry in entries}):
            try:
                symbols = [entry["symbol"] for entry in entries if entry["market"] == market]
                rows = (
                    self._b3_portfolio_rows(now, symbols)
                    if market == "B3"
                    else self._us_portfolio_rows(market, now, symbols)
                )
                rows_by_market[market] = {row.symbol: row for row in rows}
            except Exception as exc:
                errors.append(f"{market}: {type(exc).__name__}")

        items: list[RealtimePortfolioItem] = []
        for entry in entries:
            market = entry["market"]
            quote_row = rows_by_market.get(market, {}).get(entry["symbol"])
            if not quote_row:
                errors.append(f"{entry['symbol']}: quote unavailable")
                continue
            quote_row = self._apply_stream_row(quote_row) if market != "B3" else quote_row
            age_minutes = max(0, int((now - quote_row.as_of).total_seconds() / 60))
            if age_minutes > 24 * 60:
                quote_row = quote_row.model_copy(update={"status": "stale"})
            source = "Brapi Pro" if market == "B3" else (
                "EODHD Real-Time WebSocket" if quote_row.status == "live" else "EODHD Bulk Live US"
            )
            items.append(RealtimePortfolioItem(
                **quote_row.model_dump(),
                market=market,
                source=source,
            ))
        sources = sorted({item.source for item in items})
        return RealtimePortfolioResponse(
            item_count=len(items),
            items=items,
            refresh_seconds=STREAM_REFRESH_SECONDS if us_symbols and self.stream else REFRESH_SECONDS,
            generated_at=now,
            sources=sources,
            errors=errors,
        )

    def portfolio_intraday(self, symbol: str) -> RealtimePortfolioIntradayResponse:
        normalized = self._normalize_portfolio_symbol(symbol)
        entry = next(
            (item for item in self.database.list_realtime_portfolio() if item["symbol"] == normalized),
            None,
        )
        if not entry:
            raise ValueError(f"{normalized} is not in My Portfolio")
        now = datetime.now(timezone.utc)
        cached = self._intraday_series.get(normalized)
        if cached and now < cached[0]:
            return self._apply_intraday_stream(cached[1])
        with self._lock:
            now = datetime.now(timezone.utc)
            cached = self._intraday_series.get(normalized)
            if cached and now < cached[0]:
                return self._apply_intraday_stream(cached[1])
            response = self._build_portfolio_intraday(entry, now)
            self._intraday_series[normalized] = (now + timedelta(seconds=CACHE_SECONDS), response)
            return self._apply_intraday_stream(response)

    def instrument_intraday(
        self,
        symbol: str,
        *,
        market: str | None = None,
        name: str | None = None,
    ) -> InstrumentIntradayResponse:
        raw_symbol = symbol.strip()
        if not raw_symbol or len(raw_symbol) > 40:
            raise ValueError("Invalid instrument symbol")
        market_hint = (market or "").strip().upper()
        cache_key = f"{market_hint}:{raw_symbol.upper()}"
        now = datetime.now(timezone.utc)
        cached = self._instrument_intraday_series.get(cache_key)
        if cached and now < cached[0]:
            return cached[1]

        with self._lock:
            now = datetime.now(timezone.utc)
            cached = self._instrument_intraday_series.get(cache_key)
            if cached and now < cached[0]:
                return cached[1]

            live_spec = next(
                (
                    spec for spec in LIVE_MARKET_SPECS
                    if raw_symbol.casefold() in {
                        spec.symbol.casefold(),
                        spec.provider_symbol.casefold(),
                        (spec.eodhd_symbol or "").casefold(),
                    }
                ),
                None,
            )
            if live_spec:
                response = self._live_instrument_intraday(live_spec, now)
            elif raw_symbol.startswith("^"):
                response = self._yahoo_instrument_intraday(
                    raw_symbol,
                    symbol=raw_symbol.upper(),
                    name=name or raw_symbol.upper(),
                    market="Indices",
                    currency="USD",
                    now=now,
                )
            else:
                normalized = self._normalize_portfolio_symbol(raw_symbol)
                if market_hint == "B3" or re.fullmatch(r"[A-Z]{4}(?:3|4|5|6|11)", normalized):
                    entry = {"symbol": normalized, "name": name or normalized, "market": "B3"}
                else:
                    catalog_row = self._us_symbol_catalog(now).get(normalized)
                    resolved_market = self._portfolio_catalog_market(catalog_row) if catalog_row else None
                    resolved_market = resolved_market or (market_hint if market_hint in {"NASDAQ", "NYSE", "OTC"} else None)
                    if not resolved_market:
                        raise ValueError(f"{normalized} was not found as a supported market instrument")
                    entry = {
                        "symbol": normalized,
                        "name": name or str((catalog_row or {}).get("Name") or normalized),
                        "market": resolved_market,
                    }
                portfolio_response = self._build_portfolio_intraday(entry, now)
                response = InstrumentIntradayResponse(**portfolio_response.model_dump())

            self._instrument_intraday_series[cache_key] = (now + timedelta(seconds=CACHE_SECONDS), response)
            return response

    def _live_instrument_intraday(self, spec: Any, now: datetime) -> InstrumentIntradayResponse:
        if spec.provider == "brapi" and self.settings.brapi_token:
            rows = BrapiClient(
                self.settings.brapi_base_url,
                self.settings.brapi_token,
                self.http,
            ).intraday(spec.provider_symbol or spec.symbol, interval="5m", days=5)
            return self._normalize_instrument_intraday(
                rows,
                symbol=spec.symbol,
                name=spec.name,
                market="B3",
                currency=spec.currency,
                source="Brapi Pro Intraday",
                delay_minutes=5,
                market_timezone=ZoneInfo("America/Sao_Paulo"),
                now=now,
            )
        if spec.provider == "eodhd" and self.settings.eodhd_api_token and spec.eodhd_symbol:
            rows = EodhdClient(
                self.settings.eodhd_base_url,
                self.settings.eodhd_api_token,
                self.http,
            ).intraday(spec.eodhd_symbol, interval="5m", days=7)
            timezone_name = "UTC" if spec.group in {"Currencies", "Crypto"} else "America/New_York"
            return self._normalize_instrument_intraday(
                rows,
                symbol=spec.symbol,
                name=spec.name,
                market=spec.group,
                currency=spec.currency,
                source="EODHD Intraday 5m",
                delay_minutes=1 if spec.group in {"Currencies", "Crypto"} else 15,
                market_timezone=ZoneInfo(timezone_name),
                now=now,
                always_open=spec.group == "Crypto",
                full_day=spec.group == "Currencies",
            )
        if spec.provider == "eodhd_bond" and self.settings.eodhd_api_token and spec.eodhd_symbol:
            rows = EodhdClient(
                self.settings.eodhd_base_url,
                self.settings.eodhd_api_token,
                self.http,
            ).history(spec.eodhd_symbol, exchange="GBOND", days=45)
            return self._normalize_daily_instrument_history(
                rows,
                symbol=spec.symbol,
                name=spec.name,
                market=spec.group,
                currency=spec.currency,
                now=now,
            )
        return self._yahoo_instrument_intraday(
            spec.provider_symbol,
            symbol=spec.symbol,
            name=spec.name,
            market=spec.group,
            currency=spec.currency,
            now=now,
        )

    def _yahoo_instrument_intraday(
        self,
        provider_symbol: str,
        *,
        symbol: str,
        name: str,
        market: str,
        currency: str,
        now: datetime,
    ) -> InstrumentIntradayResponse:
        payload = self.http.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(provider_symbol, safe='')}",
            params={"range": "5d", "interval": "5m"},
            headers={"User-Agent": "Mozilla/5.0 C3PO-Instrument-Preview/1.0"},
        )
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote_rows = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        rows = []
        for index, timestamp in enumerate(timestamps):
            rows.append({
                "timestamp": timestamp,
                "open": self._series_value(quote_rows, "open", index),
                "high": self._series_value(quote_rows, "high", index),
                "low": self._series_value(quote_rows, "low", index),
                "close": self._series_value(quote_rows, "close", index),
                "volume": self._series_value(quote_rows, "volume", index),
            })
        meta = result.get("meta") or {}
        timezone_name = str(meta.get("exchangeTimezoneName") or "UTC")
        try:
            market_timezone = ZoneInfo(timezone_name)
        except Exception:
            market_timezone = ZoneInfo("UTC")
        return self._normalize_instrument_intraday(
            rows,
            symbol=symbol,
            name=name,
            market=market,
            currency=str(meta.get("currency") or currency),
            source="Yahoo Finance Intraday 5m",
            delay_minutes=5,
            market_timezone=market_timezone,
            now=now,
        )

    @staticmethod
    def _series_value(series: dict[str, Any], key: str, index: int) -> Any:
        values = series.get(key) or []
        return values[index] if index < len(values) else None

    def _normalize_instrument_intraday(
        self,
        rows: list[dict[str, Any]],
        *,
        symbol: str,
        name: str,
        market: str,
        currency: str,
        source: str,
        delay_minutes: int,
        market_timezone: ZoneInfo,
        now: datetime,
        always_open: bool = False,
        full_day: bool = False,
    ) -> InstrumentIntradayResponse:
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            price = number(row.get("close"))
            as_of = self._intraday_datetime(row.get("timestamp"), market_timezone)
            if price is None or price <= 0 or as_of is None:
                continue
            normalized_rows.append({
                "as_of": as_of,
                "price": price,
                "open": number(row.get("open")),
                "high": number(row.get("high")),
                "low": number(row.get("low")),
                "volume": max(0.0, number(row.get("volume")) or 0.0),
            })
        if not normalized_rows:
            raise RuntimeError(f"No intraday data returned for {symbol}")
        normalized_rows.sort(key=lambda item: item["as_of"])
        session_date = max(item["as_of"].astimezone(market_timezone).date() for item in normalized_rows)
        session_rows = [
            item for item in normalized_rows
            if item["as_of"].astimezone(market_timezone).date() == session_date
        ]
        deduplicated = {item["as_of"]: item for item in session_rows}
        session_rows = [deduplicated[key] for key in sorted(deduplicated)]
        opening_price = session_rows[0]["open"] or session_rows[0]["price"]
        current = session_rows[-1]["price"]
        local_now = now.astimezone(market_timezone)
        current_minutes = local_now.hour * 60 + local_now.minute
        if always_open:
            session_open = session_date == local_now.date()
        elif full_day:
            session_open = session_date == local_now.date() and local_now.weekday() < 5
        else:
            session_open = session_date == local_now.date() and local_now.weekday() < 5 and 9 * 60 <= current_minutes <= 18 * 60
        age_days = (local_now.date() - session_date).days
        status = "delayed" if session_open else "closed" if age_days <= 7 else "stale"
        return InstrumentIntradayResponse(
            symbol=symbol,
            name=name,
            market=market,
            currency=currency,
            session_date=session_date.isoformat(),
            interval_minutes=5,
            open=opening_price,
            high=max(item["high"] or item["price"] for item in session_rows),
            low=min(item["low"] or item["price"] for item in session_rows),
            current=current,
            change_percent=(current / opening_price - 1) * 100,
            points=[
                RealtimePortfolioIntradayPoint(as_of=item["as_of"], price=item["price"], volume=item["volume"])
                for item in session_rows
            ],
            source=source,
            delay_minutes=delay_minutes,
            status=status,
            generated_at=now,
        )

    @staticmethod
    def _normalize_daily_instrument_history(
        rows: list[dict[str, Any]],
        *,
        symbol: str,
        name: str,
        market: str,
        currency: str,
        now: datetime,
    ) -> InstrumentIntradayResponse:
        normalized: dict[str, tuple[datetime, float, float]] = {}
        for row in rows:
            price = number(row.get("close"))
            date_value = str(row.get("date") or "")
            if price is None or price <= 0 or not date_value:
                continue
            try:
                as_of = datetime.fromisoformat(date_value).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            normalized[date_value] = (as_of, price, max(0.0, number(row.get("volume")) or 0.0))
        history = [normalized[key] for key in sorted(normalized)][-30:]
        if not history:
            raise RuntimeError(f"No official daily history returned for {symbol}")

        current = history[-1][1]
        previous_close = history[-2][1] if len(history) > 1 else current
        latest_date = history[-1][0].date()
        age_days = (now.date() - latest_date).days
        return InstrumentIntradayResponse(
            symbol=symbol,
            name=name,
            market=market,
            currency=currency,
            session_date=latest_date.isoformat(),
            series_kind="daily",
            interval_minutes=1440,
            open=previous_close,
            high=max(item[1] for item in history),
            low=min(item[1] for item in history),
            current=current,
            change_percent=(current / previous_close - 1) * 100 if previous_close else 0,
            points=[
                RealtimePortfolioIntradayPoint(as_of=as_of, price=price, volume=volume)
                for as_of, price, volume in history
            ],
            source="EODHD Government Bonds · Official daily closes",
            delay_minutes=0,
            status="closed" if age_days <= 7 else "stale",
            generated_at=now,
        )

    def _build_portfolio_intraday(
        self,
        entry: dict[str, Any],
        now: datetime,
    ) -> RealtimePortfolioIntradayResponse:
        symbol = str(entry["symbol"])
        market = str(entry["market"])
        if market == "B3":
            if not self.settings.brapi_token:
                raise RuntimeError("Brapi credential is not configured")
            rows = BrapiClient(
                self.settings.brapi_base_url,
                self.settings.brapi_token,
                self.http,
            ).intraday(symbol, interval="5m", days=5)
            market_timezone = ZoneInfo("America/Sao_Paulo")
            source = "Brapi Pro Intraday"
            currency = "BRL"
            delay_minutes = 5
        else:
            if not self.settings.eodhd_api_token:
                raise RuntimeError("EODHD credential is not configured")
            rows = EodhdClient(
                self.settings.eodhd_base_url,
                self.settings.eodhd_api_token,
                self.http,
            ).intraday(symbol, exchange="US", interval="5m", days=7)
            market_timezone = ZoneInfo("America/New_York")
            source = "EODHD Intraday 5m"
            currency = "USD"
            delay_minutes = 15

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            price = number(row.get("close"))
            as_of = self._intraday_datetime(row.get("timestamp"), market_timezone)
            if price is None or price <= 0 or as_of is None:
                continue
            normalized_rows.append({
                "as_of": as_of,
                "price": price,
                "open": number(row.get("open")),
                "high": number(row.get("high")),
                "low": number(row.get("low")),
                "volume": max(0.0, number(row.get("volume")) or 0.0),
            })
        if not normalized_rows:
            raise RuntimeError(f"No intraday data returned for {symbol}")

        normalized_rows.sort(key=lambda item: item["as_of"])
        session_date = max(item["as_of"].astimezone(market_timezone).date() for item in normalized_rows)
        session_rows = [
            item for item in normalized_rows
            if item["as_of"].astimezone(market_timezone).date() == session_date
        ]
        deduplicated = {item["as_of"]: item for item in session_rows}
        session_rows = [deduplicated[key] for key in sorted(deduplicated)]
        opening_price = session_rows[0]["open"] or session_rows[0]["price"]
        current = session_rows[-1]["price"]
        points = [
            RealtimePortfolioIntradayPoint(
                as_of=item["as_of"],
                price=item["price"],
                volume=item["volume"],
            )
            for item in session_rows
        ]
        high = max(item["high"] or item["price"] for item in session_rows)
        low = min(item["low"] or item["price"] for item in session_rows)
        local_now = now.astimezone(market_timezone)
        open_minutes, close_minutes = ((10 * 60, 18 * 60) if market == "B3" else (9 * 60 + 30, 16 * 60))
        current_minutes = local_now.hour * 60 + local_now.minute
        session_open = (
            session_date == local_now.date()
            and local_now.weekday() < 5
            and open_minutes <= current_minutes <= close_minutes
        )
        age_days = (local_now.date() - session_date).days
        status = "delayed" if session_open else "closed" if age_days <= 7 else "stale"
        return RealtimePortfolioIntradayResponse(
            symbol=symbol,
            name=str(entry.get("name") or symbol),
            market=market,
            currency=currency,
            session_date=session_date.isoformat(),
            interval_minutes=5,
            open=opening_price,
            high=high,
            low=low,
            current=current,
            change_percent=(current / opening_price - 1) * 100,
            points=points,
            source=source,
            delay_minutes=delay_minutes,
            status=status,
            generated_at=now,
        )

    def _apply_intraday_stream(
        self,
        response: RealtimePortfolioIntradayResponse,
    ) -> RealtimePortfolioIntradayResponse:
        if response.market == "B3" or not self.stream or not response.points:
            return response
        tick = self.stream.quote(response.symbol)
        market_timezone = ZoneInfo("America/New_York")
        if (
            not tick
            or tick.as_of.astimezone(market_timezone).date().isoformat() != response.session_date
            or tick.as_of < response.points[-1].as_of
            or abs(tick.price / response.current - 1) > MAX_STREAM_PRICE_DEVIATION
        ):
            return response
        points = list(response.points)
        live_point = RealtimePortfolioIntradayPoint(as_of=tick.as_of, price=tick.price, volume=0)
        if tick.as_of == points[-1].as_of:
            points[-1] = live_point
        else:
            points.append(live_point)
        return response.model_copy(update={
            "current": tick.price,
            "high": max(response.high, tick.price),
            "low": min(response.low, tick.price),
            "change_percent": (tick.price / response.open - 1) * 100,
            "points": points,
            "source": f"{response.source} + EODHD Real-Time WebSocket",
            "delay_minutes": 0,
            "status": "live",
            "generated_at": datetime.now(timezone.utc),
        })

    @staticmethod
    def _intraday_datetime(value: Any, market_timezone: ZoneInfo) -> datetime | None:
        if value is None:
            return None
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = None
        if numeric_value is not None:
            if numeric_value > 10_000_000_000:
                numeric_value /= 1000
            try:
                return datetime.fromtimestamp(numeric_value, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=market_timezone)
        return parsed.astimezone(timezone.utc)

    def add_portfolio_symbol(self, symbol: str) -> RealtimePortfolioResponse:
        normalized = self._normalize_portfolio_symbol(symbol)
        now = datetime.now(timezone.utc)
        match: RealtimeMarketLeader | None = None
        market: str | None = None
        if re.fullmatch(r"[A-Z]{4}(?:3|4|5|6|11)", normalized):
            match = next((row for row in self._b3_portfolio_rows(now, [normalized]) if row.symbol == normalized), None)
            market = "B3" if match else None
        else:
            catalog_row = self._us_symbol_catalog(now).get(normalized)
            market = (
                self._portfolio_catalog_market(catalog_row)
                if catalog_row and self._is_portfolio_security(catalog_row)
                else None
            )
            if market:
                match = next(
                    (row for row in self._us_portfolio_rows(market, now, [normalized]) if row.symbol == normalized),
                    None,
                )
        if not match or not market:
            raise ValueError(f"{normalized} was not found as an active B3, NASDAQ, NYSE or OTC stock or ETF")
        self.database.add_realtime_portfolio(match.symbol, match.name, market)
        return self.portfolio_snapshot()

    def search_portfolio_symbols(
        self,
        query: str,
        *,
        limit: int = 8,
    ) -> RealtimePortfolioSymbolSearchResponse:
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Search query is required")
        normalized_query = self._search_key(clean_query)
        ticker_query = re.sub(r"[^A-Z0-9\-]", "", clean_query.upper())
        now = datetime.now(timezone.utc)
        tracked = {item["symbol"] for item in self.database.list_realtime_portfolio()}
        ranked: list[tuple[int, str, str, RealtimePortfolioSymbolSuggestion]] = []
        errors: list[str] = []
        sources: list[str] = []

        registry_matches = 0
        for company in self.database.list_ir_companies():
            raw_market = str(company.get("market") or "").upper()
            exchange = str(company.get("exchange") or raw_market or "C3PO")
            market = self._portfolio_registry_market(raw_market, exchange)
            if not market:
                continue
            name = str(company.get("company_name") or "")
            for symbol_value in company.get("symbols") or []:
                symbol = str(symbol_value).upper()
                rank = self._portfolio_search_rank(symbol, name, ticker_query, normalized_query)
                if rank is None:
                    continue
                ranked.append((rank, symbol, market, RealtimePortfolioSymbolSuggestion(
                    symbol=symbol,
                    name=name or symbol,
                    market=market,
                    exchange=exchange,
                    security_type="Stock / ETF",
                    currency="BRL" if market == "B3" else "USD",
                    already_tracked=symbol in tracked,
                )))
                registry_matches += 1
        if registry_matches:
            sources.append("C3PO issuer registry")

        try:
            for row in self._b3_rows(now):
                rank = self._portfolio_search_rank(row.symbol, row.name, ticker_query, normalized_query)
                if rank is None:
                    continue
                ranked.append((rank, row.symbol, "B3", RealtimePortfolioSymbolSuggestion(
                    symbol=row.symbol,
                    name=row.name,
                    market="B3",
                    exchange="B3",
                    security_type="Stock / ETF",
                    currency="BRL",
                    already_tracked=row.symbol in tracked,
                )))
            sources.append("Brapi Pro")
        except Exception as exc:
            errors.append(f"B3: {type(exc).__name__}")

        try:
            for symbol, metadata in self._us_symbol_catalog(now).items():
                market = self._portfolio_catalog_market(metadata)
                if not market or not self._is_portfolio_security(metadata):
                    continue
                name = canonical_us_security_name(
                    symbol,
                    metadata.get("Name") or metadata.get("name") or symbol,
                )
                rank = self._portfolio_search_rank(symbol, name, ticker_query, normalized_query)
                if rank is None:
                    continue
                security_type = canonical_us_security_type(
                    symbol,
                    metadata.get("Type") or metadata.get("type"),
                )
                ranked.append((rank, symbol, market, RealtimePortfolioSymbolSuggestion(
                    symbol=symbol,
                    name=name,
                    market=market,
                    exchange=str(metadata.get("Exchange") or metadata.get("ExchangeCode") or market),
                    security_type=security_type,
                    currency=str(metadata.get("Currency") or metadata.get("currency") or "USD"),
                    already_tracked=symbol in tracked,
                )))
            sources.append("EODHD")
        except Exception as exc:
            errors.append(f"US: {type(exc).__name__}")

        deduplicated: list[RealtimePortfolioSymbolSuggestion] = []
        seen: set[tuple[str, str]] = set()
        for _, _, _, item in sorted(ranked, key=lambda entry: (entry[0], entry[1], entry[2])):
            key = (item.market, item.symbol)
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
            if len(deduplicated) >= max(1, min(limit, 12)):
                break
        return RealtimePortfolioSymbolSearchResponse(
            query=clean_query,
            item_count=len(deduplicated),
            items=deduplicated,
            sources=sources,
            errors=errors,
        )

    def delete_portfolio_symbol(self, symbol: str) -> RealtimePortfolioResponse:
        normalized = self._normalize_portfolio_symbol(symbol)
        if not self.database.delete_realtime_portfolio(normalized):
            raise ValueError(f"{normalized} is not in My Portfolio")
        return self.portfolio_snapshot()

    @staticmethod
    def _normalize_portfolio_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.endswith(".SA") or normalized.endswith(".US"):
            normalized = normalized[:-3]
        if "." in normalized:
            normalized = normalized.replace(".", "-")
        if not normalized or len(normalized) > 18 or not re.fullmatch(r"[A-Z0-9\-]+", normalized):
            raise ValueError("Invalid ticker")
        return normalized

    @staticmethod
    def _search_key(value: str) -> str:
        decomposed = unicodedata.normalize("NFD", value)
        return "".join(character for character in decomposed if unicodedata.category(character) != "Mn").casefold()

    @classmethod
    def _portfolio_search_rank(
        cls,
        symbol: str,
        name: str,
        ticker_query: str,
        normalized_query: str,
    ) -> int | None:
        clean_symbol = symbol.upper()
        clean_name = cls._search_key(name)
        if ticker_query and clean_symbol == ticker_query:
            return 0
        if ticker_query and clean_symbol.startswith(ticker_query):
            return 1
        if clean_name.startswith(normalized_query):
            return 2
        if ticker_query and ticker_query in clean_symbol:
            return 3
        if normalized_query in clean_name:
            return 4
        return None

    @staticmethod
    def _portfolio_registry_market(market: str, exchange: str) -> str | None:
        if market == "B3":
            return "B3"
        normalized_exchange = exchange.upper()
        if "NASDAQ" in normalized_exchange or normalized_exchange in {"XNAS", "NMS", "NGM", "NCM"}:
            return "NASDAQ"
        if any(value in normalized_exchange for value in ("NYSE", "ARCA", "AMEX")):
            return "NYSE"
        if normalized_exchange in {"XNYS", "ARCX", "XASE"}:
            return "NYSE"
        if any(value in normalized_exchange for value in ("OTC", "PINK")):
            return "OTC"
        return None

    @staticmethod
    def _leaders(rows: list[RealtimeMarketLeader], field: str, *, reverse: bool) -> list[RealtimeMarketLeader]:
        eligible = rows
        if field == "change_percent":
            eligible = [
                item for item in rows
                if item.volume > 0 and item.cash_volume >= 100_000 and abs(item.change_percent) <= 500
            ]
        return sorted(eligible, key=lambda item: getattr(item, field), reverse=reverse)[:5]

    def _apply_stream(self, market: str, response: RealtimeMarketResponse, now: datetime) -> RealtimeMarketResponse:
        if market == "B3" or not self.stream:
            return response
        groups = ("gainers", "losers", "volume_leaders", "cash_leaders")
        symbols = list(dict.fromkeys(
            item.symbol
            for group in groups
            for item in getattr(response, group)
        ))
        self.stream.set_group(f"market:{market}", symbols, priority=50)
        updated = {
            group: [self._apply_stream_row(item) for item in getattr(response, group)]
            for group in groups
        }
        live_count = sum(item.status == "live" for group in groups for item in updated[group])
        source = "EODHD T-15 market scan"
        if live_count:
            source += " + real-time WebSocket quotes"
        return response.model_copy(update={
            **updated,
            "source": source,
            "refresh_seconds": STREAM_REFRESH_SECONDS,
            "generated_at": now,
        })

    def _apply_stream_row(self, row: RealtimeMarketLeader) -> RealtimeMarketLeader:
        if not self.stream:
            return row
        tick = self.stream.quote(row.symbol)
        if not tick or tick.as_of < row.as_of:
            return row
        if abs(tick.price / row.price - 1) > MAX_STREAM_PRICE_DEVIATION:
            return row
        previous_close = self._us_previous_close.get(row.symbol)
        if previous_close is None and row.change_percent > -99.99:
            previous_close = row.price / (1 + row.change_percent / 100)
        change_percent = (tick.price / previous_close - 1) * 100 if previous_close else row.change_percent
        return row.model_copy(update={
            "price": tick.price,
            "change_percent": change_percent,
            "cash_volume": tick.price * row.volume,
            "as_of": tick.as_of,
            "status": "live",
            "delay_minutes": 0,
        })

    def _index_quote(self, spec: RealtimeMarketSpec) -> RealtimeMarketIndex:
        payload = self.http.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(spec.index_symbol, safe='')}",
            params={"range": "1d", "interval": "5m"},
            headers={"User-Agent": "Mozilla/5.0 C3PO-Realtime/1.0"},
        )
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        collected_at = datetime.now(timezone.utc)
        value = number(meta.get("regularMarketPrice"))
        if value is None:
            raise ValueError(f"{spec.index_name}: no index value")
        previous_close = number(meta.get("previousClose")) or number(meta.get("chartPreviousClose"))
        change_percent = (value / previous_close - 1) * 100 if previous_close else None
        market_state = str(meta.get("marketState") or "UNKNOWN").upper()
        if market_state == "REGULAR":
            status = "delayed"
        elif market_state in {"CLOSED", "PRE", "POST", "PREPRE", "POSTPOST"}:
            status = "closed"
        else:
            status = "stale"
        return RealtimeMarketIndex(
            symbol=spec.index_symbol,
            name=spec.index_name,
            value=value,
            change_percent=change_percent,
            currency=str(meta.get("currency") or spec.index_currency),
            market_state=market_state,
            status=status,
            as_of=from_unix(meta.get("regularMarketTime"), collected_at),
        )

    def _b3_rows(self, now: datetime) -> list[RealtimeMarketLeader]:
        if self._b3_quotes and now < self._b3_quotes[0]:
            return self._b3_quotes[1]
        if not self.settings.brapi_token:
            raise RuntimeError("Brapi credential is not configured")
        payload = self.http.get_json(
            f"{self.settings.brapi_base_url.rstrip('/')}/api/quote/list",
            params={
                "sortBy": "volume",
                "sortOrder": "desc",
                "limit": 2000,
                "page": 1,
                "type": "stock",
            },
            headers={"Authorization": f"Bearer {self.settings.brapi_token}"},
        )
        raw_rows = payload.get("stocks") or payload.get("results") or payload.get("data") or []
        rows: list[RealtimeMarketLeader] = []
        for raw in raw_rows:
            symbol = str(raw.get("stock") or raw.get("symbol") or raw.get("ticker") or "").upper().replace(".SA", "")
            price = number(raw.get("close")) or number(raw.get("regularMarketPrice"))
            change = number(raw.get("change"))
            if change is None:
                change = number(raw.get("change_percent")) or number(raw.get("regularMarketChangePercent"))
            volume = number(raw.get("volume")) or number(raw.get("regularMarketVolume"))
            if not re.fullmatch(r"[A-Z]{4}(?:3|4|5|6|11)", symbol):
                continue
            if price is None or price <= 0 or change is None or volume is None or volume < 0:
                continue
            rows.append(RealtimeMarketLeader(
                symbol=symbol,
                name=str(raw.get("name") or raw.get("longName") or symbol),
                price=price,
                change_percent=change,
                volume=volume,
                cash_volume=price * volume,
                currency="BRL",
                exchange="B3",
                as_of=now,
                logo_url=raw.get("logo") or raw.get("logoUrl"),
                status="delayed",
                delay_minutes=5,
            ))
        self._b3_quotes = (now + timedelta(seconds=CACHE_SECONDS), rows)
        return rows

    def _b3_portfolio_rows(self, now: datetime, symbols: list[str]) -> list[RealtimeMarketLeader]:
        rows = {row.symbol: row for row in self._b3_rows(now)}
        missing = [symbol for symbol in symbols if symbol not in rows]
        for symbol in list(missing):
            cached = self._portfolio_quote(symbol, now)
            if cached:
                rows[symbol] = cached
                missing.remove(symbol)
        if missing:
            client = BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http)
            try:
                quotes = client.quotes(missing)
            except Exception:
                quotes = []
            for quote_row in quotes:
                symbol = quote_row.symbol.removesuffix(".SA")
                if symbol not in missing:
                    continue
                row = self._portfolio_row_from_quote(
                    quote_row,
                    name=symbol,
                    market="B3",
                    delay_minutes=5,
                )
                rows[symbol] = row
                self._portfolio_quotes[symbol] = (now + timedelta(seconds=CACHE_SECONDS), row)
        return list(rows.values())

    def _us_rows(self, market: str, now: datetime) -> list[RealtimeMarketLeader]:
        catalog = self._us_symbol_catalog(now)
        quotes = self._us_bulk_quotes(now)
        rows: list[RealtimeMarketLeader] = []
        for raw in quotes:
            symbol = self._us_symbol(raw.get("code") or raw.get("Code"))
            metadata = catalog.get(symbol)
            if not symbol or not metadata or self._catalog_market(metadata) != market or not self._is_common_stock(metadata):
                continue
            row = self._us_row(raw, metadata, market, now)
            if row:
                rows.append(row)
        return rows

    def _us_investable_rows(self, market: str, now: datetime) -> list[RealtimeMarketLeader]:
        """Return every quoted US stock or ETF assigned to the requested venue.

        The public market-leader tables intentionally contain common stocks only.
        Trading and portfolio workflows need the broader investable catalog,
        including NASDAQ ETFs and NYSE Arca / NYSE American securities.
        """
        catalog = self._us_symbol_catalog(now)
        quotes = self._us_bulk_quotes(now)
        rows: list[RealtimeMarketLeader] = []
        for raw in quotes:
            symbol = self._us_symbol(raw.get("code") or raw.get("Code"))
            metadata = catalog.get(symbol)
            if (
                not symbol
                or not metadata
                or self._portfolio_catalog_market(metadata) != market
                or not self._is_portfolio_security(metadata)
            ):
                continue
            row = self._us_row(raw, metadata, market, now)
            if row:
                rows.append(row)
        return rows

    def _us_portfolio_rows(
        self,
        market: str,
        now: datetime,
        symbols: list[str],
    ) -> list[RealtimeMarketLeader]:
        rows = {row.symbol: row for row in self._us_rows(market, now)}
        missing = [symbol for symbol in symbols if symbol not in rows]
        catalog = self._us_symbol_catalog(now)
        quotes = {
            self._us_symbol(raw.get("code") or raw.get("Code")): raw
            for raw in self._us_bulk_quotes(now)
        }
        for symbol in list(missing):
            metadata = catalog.get(symbol)
            if (
                not metadata
                or not self._is_portfolio_security(metadata)
                or self._portfolio_catalog_market(metadata) != market
            ):
                continue
            raw = quotes.get(symbol)
            row = self._us_row(raw, metadata, market, now) if raw else self._portfolio_quote(symbol, now)
            if row:
                rows[symbol] = row
                missing.remove(symbol)
        if missing:
            client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
            for symbol in missing:
                metadata = catalog.get(symbol)
                if (
                    not metadata
                    or not self._is_portfolio_security(metadata)
                    or self._portfolio_catalog_market(metadata) != market
                ):
                    continue
                try:
                    quote_rows = client.quotes([symbol])
                except Exception:
                    continue
                if not quote_rows:
                    continue
                row = self._portfolio_row_from_quote(
                    quote_rows[0],
                    name=str(metadata.get("Name") or metadata.get("name") or symbol),
                    market=market,
                    delay_minutes=15,
                )
                rows[symbol] = row
                self._portfolio_quotes[symbol] = (now + timedelta(seconds=CACHE_SECONDS), row)
        return list(rows.values())

    def _us_row(
        self,
        raw: dict[str, Any],
        metadata: dict[str, Any],
        market: str,
        now: datetime,
    ) -> RealtimeMarketLeader | None:
        symbol = self._us_symbol(raw.get("code") or raw.get("Code"))
        if not symbol:
            return None
        price = number(raw.get("close"))
        change = number(raw.get("change_p"))
        volume = number(raw.get("volume"))
        if price is None or price <= 0 or change is None or volume is None or volume < 0:
            return None
        reported_previous_close = number(raw.get("previousClose"))
        derived_previous_close = price / (1 + change / 100) if change > -99.99 else None
        previous_close = reported_previous_close
        if reported_previous_close and derived_previous_close:
            implied_change = (price / reported_previous_close - 1) * 100
            if abs(implied_change - change) > 2:
                previous_close = derived_previous_close
        elif derived_previous_close:
            previous_close = derived_previous_close
        if previous_close and previous_close > 0:
            self._us_previous_close[symbol] = previous_close
        return RealtimeMarketLeader(
            symbol=symbol,
            name=str(metadata.get("Name") or metadata.get("name") or symbol),
            price=price,
            change_percent=change,
            volume=volume,
            cash_volume=price * volume,
            currency=str(metadata.get("Currency") or metadata.get("currency") or "USD"),
            exchange=market,
            as_of=from_unix(raw.get("timestamp"), now),
            status="delayed",
            delay_minutes=15,
        )

    def _portfolio_quote(self, symbol: str, now: datetime) -> RealtimeMarketLeader | None:
        cached = self._portfolio_quotes.get(symbol)
        return cached[1] if cached and now < cached[0] else None

    def _portfolio_row_from_quote(
        self,
        quote_row: NormalizedQuote,
        *,
        name: str,
        market: str,
        delay_minutes: int,
    ) -> RealtimeMarketLeader:
        previous_close = quote_row.previous_close
        change = quote_row.change_percent
        if change is None and previous_close and previous_close > 0:
            change = (quote_row.price / previous_close - 1) * 100
        if market != "B3" and previous_close and previous_close > 0:
            self._us_previous_close[quote_row.symbol] = previous_close
        volume = quote_row.volume or 0.0
        return RealtimeMarketLeader(
            symbol=quote_row.symbol.removesuffix(".SA").removesuffix(".US"),
            name=name,
            price=quote_row.price,
            change_percent=change or 0.0,
            volume=volume,
            cash_volume=quote_row.price * volume,
            currency=quote_row.currency or ("BRL" if market == "B3" else "USD"),
            exchange=market,
            as_of=quote_row.as_of,
            status="delayed",
            delay_minutes=delay_minutes,
        )

    def _us_bulk_quotes(self, now: datetime) -> list[dict[str, Any]]:
        if self._us_quotes and now < self._us_quotes[0]:
            return self._us_quotes[1]
        if not self.settings.eodhd_api_token:
            raise RuntimeError("EODHD credential is not configured")
        payload = self.http.get_json(
            f"{self.settings.eodhd_base_url.rstrip('/')}/api/real-time/AAPL.US",
            params={"ex": "US", "api_token": self.settings.eodhd_api_token, "fmt": "json"},
        )
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        self._us_quotes = (now + timedelta(seconds=CACHE_SECONDS), rows)
        return rows

    def _us_symbol_catalog(self, now: datetime) -> dict[str, dict[str, Any]]:
        if self._us_catalog and now < self._us_catalog[0]:
            return self._us_catalog[1]
        if not self.settings.eodhd_api_token:
            raise RuntimeError("EODHD credential is not configured")
        payload = self.http.get_json(
            f"{self.settings.eodhd_base_url.rstrip('/')}/api/exchange-symbol-list/US",
            params={"api_token": self.settings.eodhd_api_token, "fmt": "json"},
        )
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        catalog = {self._us_symbol(row.get("Code") or row.get("code")): row for row in rows}
        catalog.pop("", None)
        self._us_catalog = (now + timedelta(seconds=SYMBOL_CATALOG_SECONDS), catalog)
        return catalog

    @staticmethod
    def _us_symbol(value: Any) -> str:
        return str(value or "").upper().removesuffix(".US")

    @staticmethod
    def _catalog_market(row: dict[str, Any]) -> str | None:
        exchange = " ".join(str(row.get(key) or "") for key in ("Exchange", "ExchangeCode", "exchange")).upper()
        if "NASDAQ" in exchange or "XNAS" in exchange:
            return "NASDAQ"
        if ("NYSE" in exchange or "XNYS" in exchange) and not any(value in exchange for value in ("ARCA", "AMERICAN", "MKT")):
            return "NYSE"
        return None

    @classmethod
    def _portfolio_catalog_market(cls, row: dict[str, Any]) -> str | None:
        market = cls._catalog_market(row)
        if market:
            return market
        exchange = " ".join(str(row.get(key) or "") for key in ("Exchange", "ExchangeCode", "exchange")).upper()
        if any(value in exchange for value in ("NYSE ARCA", "ARCA", "NYSE AMERICAN", "NYSE MKT", "AMERICAN")):
            return "NYSE"
        if any(value in exchange for value in ("OTC", "PINK")):
            return "OTC"
        return None

    @staticmethod
    def _is_common_stock(row: dict[str, Any]) -> bool:
        security_type = str(row.get("Type") or row.get("type") or "").upper()
        if not security_type:
            return True
        excluded = ("ETF", "FUND", "INDEX", "NOTE", "BOND", "WARRANT", "RIGHT", "PREFERRED")
        return not any(value in security_type for value in excluded)

    @classmethod
    def _is_portfolio_security(cls, row: dict[str, Any]) -> bool:
        security_type = str(row.get("Type") or row.get("type") or "").upper()
        return cls._is_common_stock(row) or "ETF" in security_type or "EXCHANGE TRADED" in security_type
