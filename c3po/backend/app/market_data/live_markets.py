from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from urllib.parse import quote

from ..config import Settings
from ..schemas import LiveMarketIndexResponse, LiveMarketItem, LiveMarketsResponse
from .brapi import BrapiClient
from .eodhd import EodhdClient
from .eodhd_stream import EodhdRealtimeStream
from .http import JsonHttpClient
from .models import from_unix, number


REFRESH_SECONDS = 30
CACHE_SECONDS = 25
INDEX_REFRESH_SECONDS = 3
INDEX_CACHE_SECONDS = 2
DEFAULT_DELAY_MINUTES = 5
BOND_CACHE_SECONDS = 900


@dataclass(frozen=True)
class MarketSpec:
    group: str
    symbol: str
    name: str
    provider_symbol: str
    currency: str
    provider: str = "yahoo"
    eodhd_symbol: str | None = None


MARKET_SPECS = (
    MarketSpec("Future Index", "S&P 500 Fut.", "S&P 500 E-mini Futures", "ES=F", "USD"),
    MarketSpec("Future Index", "Nasdaq Fut.", "Nasdaq 100 E-mini Futures", "NQ=F", "USD"),
    MarketSpec("Future Index", "Nikkei", "Nikkei 225", "^N225", "JPY", "eodhd", "N225.INDX"),
    MarketSpec("Future Index", "DAX", "DAX Performance Index", "^GDAXI", "EUR", "eodhd", "GDAXI.INDX"),
    MarketSpec("Future Index", "Shanghai", "Shanghai Composite", "000001.SS", "CNY", "eodhd", "SSEC.INDX"),
    MarketSpec("Future Index", "US3Y", "US 3-Year Treasury Yield", "US3Y.GBOND", "%", "eodhd_bond", "US3Y.GBOND"),
    MarketSpec("Future Index", "US10Y", "US 10-Year Treasury Yield", "US10Y.GBOND", "%", "eodhd_bond", "US10Y.GBOND"),
    MarketSpec("Index", "IBOV", "Ibovespa B3", "^BVSP", "BRL"),
    MarketSpec("Index", "NASDAQ", "Nasdaq Composite", "^IXIC", "USD"),
    MarketSpec("Index", "NYSE", "NYSE Composite", "^NYA", "USD"),
    MarketSpec("Currencies", "USD/BRL", "US Dollar / Brazilian Real", "BRL=X", "BRL", "eodhd", "USDBRL.FOREX"),
    MarketSpec("Currencies", "EUR/BRL", "Euro / Brazilian Real", "EURBRL=X", "BRL", "eodhd", "EURBRL.FOREX"),
    MarketSpec("Currencies", "GBP/BRL", "British Pound / Brazilian Real", "GBPBRL=X", "BRL", "eodhd", "GBPBRL.FOREX"),
    MarketSpec("Crypto", "BTC", "Bitcoin", "BTC-USD", "USD", "eodhd", "BTC-USD.CC"),
    MarketSpec("Crypto", "ETH", "Ethereum", "ETH-USD", "USD", "eodhd", "ETH-USD.CC"),
    MarketSpec("Crypto", "SOL", "Solana", "SOL-USD", "USD", "eodhd", "SOL-USD.CC"),
    MarketSpec("Crypto", "BONK", "Bonk", "BONK-USD", "USD", "eodhd", "BONK-USD.CC"),
    MarketSpec("Crypto", "DOGE", "Dogecoin", "DOGE-USD", "USD", "eodhd", "DOGE-USD.CC"),
    MarketSpec("Portfolio", "AMZN", "Amazon", "AMZN", "USD", "eodhd", "AMZN.US"),
    MarketSpec("Portfolio", "AVGO", "Broadcom", "AVGO", "USD", "eodhd", "AVGO.US"),
    MarketSpec("Portfolio", "VOO", "Vanguard S&P 500 ETF", "VOO", "USD", "eodhd", "VOO.US"),
    MarketSpec("Portfolio", "TTWO", "Take-Two Interactive", "TTWO", "USD", "eodhd", "TTWO.US"),
    MarketSpec(
        "Portfolio",
        "SPCX",
        "Space Exploration Technologies Corp. Class A Common Stock",
        "SPCX",
        "USD",
        "eodhd",
        "SPCX.US",
    ),
    MarketSpec("Portfolio", "KWEB", "KraneShares CSI China Internet ETF", "KWEB", "USD", "eodhd", "KWEB.US"),
    MarketSpec("Portfolio", "MHVYF", "Mitsubishi Heavy Industries", "MHVYF", "USD", "eodhd", "MHVYF.US"),
    MarketSpec("Portfolio", "UNIP6", "Unipar", "UNIP6", "BRL", "brapi"),
    MarketSpec("Portfolio", "PRNR3", "Priner", "PRNR3", "BRL", "brapi"),
)


class LiveMarketsService:
    def __init__(
        self,
        settings: Settings,
        http: JsonHttpClient,
        stream: EodhdRealtimeStream | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.stream = stream
        self._lock = Lock()
        self._index_lock = Lock()
        self._cached: LiveMarketsResponse | None = None
        self._cache_expires_at: datetime | None = None
        self._cached_index: LiveMarketIndexResponse | None = None
        self._index_cache_expires_at: datetime | None = None
        self._bond_items: list[LiveMarketItem] = []
        self._bond_cache_expires_at: datetime | None = None
        self._last_items: dict[str, LiveMarketItem] = {}

    def snapshot(self) -> LiveMarketsResponse:
        now = datetime.now(timezone.utc)
        if self._cached and self._cache_expires_at and now < self._cache_expires_at:
            return self._cached
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._cached and self._cache_expires_at and now < self._cache_expires_at:
                return self._cached
            response = self._build(now)
            self._cached = response
            self._cache_expires_at = now + timedelta(seconds=CACHE_SECONDS)
            return response

    def index_snapshot(self) -> LiveMarketIndexResponse:
        now = datetime.now(timezone.utc)
        if self._cached_index and self._index_cache_expires_at and now < self._index_cache_expires_at:
            return self._cached_index
        with self._index_lock:
            now = datetime.now(timezone.utc)
            if self._cached_index and self._index_cache_expires_at and now < self._index_cache_expires_at:
                return self._cached_index
            specs = [spec for spec in MARKET_SPECS if spec.group == "Index"]
            items: dict[str, LiveMarketItem] = {}
            errors: list[str] = []
            with ThreadPoolExecutor(max_workers=len(specs)) as executor:
                futures = {executor.submit(self._fetch_yahoo, spec): spec for spec in specs}
                for future in as_completed(futures):
                    spec = futures[future]
                    try:
                        item = future.result()
                        items[item.symbol] = item
                    except Exception as exc:
                        errors.append(f"{spec.symbol}: {type(exc).__name__}")

            ordered: list[LiveMarketItem] = []
            for spec in specs:
                item = items.get(spec.symbol)
                if item:
                    self._last_items[spec.symbol] = item
                    ordered.append(item)
                    continue
                fallback = self._last_items.get(spec.symbol)
                if fallback:
                    ordered.append(fallback.model_copy(update={"status": "stale", "collected_at": now}))

            response = LiveMarketIndexResponse(
                generated_at=now,
                refresh_seconds=INDEX_REFRESH_SECONDS,
                items=ordered,
                errors=errors,
            )
            self._cached_index = response
            self._index_cache_expires_at = now + timedelta(seconds=INDEX_CACHE_SECONDS)
            return response

    def _build(self, generated_at: datetime) -> LiveMarketsResponse:
        items: dict[str, LiveMarketItem] = {}
        errors: list[str] = []

        eodhd_specs = [spec for spec in MARKET_SPECS if spec.provider == "eodhd"]
        bond_specs = [spec for spec in MARKET_SPECS if spec.provider == "eodhd_bond"]
        if self.stream:
            self.stream.set_group(
                "markets:portfolio",
                [spec.symbol for spec in eodhd_specs if spec.group == "Portfolio"],
                priority=80,
            )
        if self.settings.eodhd_api_token:
            try:
                for item in self._fetch_eodhd(eodhd_specs):
                    items[item.symbol] = item
            except Exception as exc:
                errors.append(f"EODHD: {type(exc).__name__}; Yahoo fallback active")
            try:
                for item in self._bond_snapshot(bond_specs, generated_at):
                    items[item.symbol] = item
            except Exception as exc:
                errors.append(f"EODHD Government Bonds: {type(exc).__name__}")
        else:
            errors.append("EODHD credential unavailable; Yahoo fallback active")

        # E-mini futures have no EODHD .INDX equivalent, so they stay on the
        # public chart feed. Nikkei/DAX/Shanghai moved to EODHD's .INDX
        # symbols (2026-08-19) -- Yahoo showed multi-hour-stale prints for
        # these three specifically; falls back to Yahoo automatically below
        # if a given .INDX symbol doesn't resolve (same as any other EODHD
        # spec: see "eodhd_specs if spec.symbol not in items" a few lines down).
        yahoo_specs = [spec for spec in MARKET_SPECS if spec.provider == "yahoo"]
        yahoo_specs.extend(spec for spec in eodhd_specs if spec.symbol not in items)
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(self._fetch_yahoo, spec): spec for spec in yahoo_specs}
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    item = future.result()
                    items[item.symbol] = item
                except Exception as exc:
                    errors.append(f"{spec.symbol}: {type(exc).__name__}")

        brapi_specs = [spec for spec in MARKET_SPECS if spec.provider == "brapi"]
        if brapi_specs:
            try:
                for item in self._fetch_brapi(brapi_specs):
                    items[item.symbol] = item
            except Exception as exc:
                errors.append(f"B3 portfolio: {type(exc).__name__}")

        ordered: list[LiveMarketItem] = []
        for spec in MARKET_SPECS:
            item = items.get(spec.symbol)
            if item:
                self._last_items[spec.symbol] = item
                ordered.append(item)
                continue
            fallback = self._last_items.get(spec.symbol)
            if fallback:
                ordered.append(fallback.model_copy(update={"status": "stale", "collected_at": generated_at}))

        groups = {name: [] for name in ("Future Index", "Index", "Currencies", "Crypto", "Portfolio")}
        for item in ordered:
            groups[item.group].append(item)
        eodhd_plan = self.settings.eodhd_plan.replace("-", " ").title()
        global_methodology = (
            f"EODHD {eodhd_plan} is active for US portfolio securities, FX and crypto; "
            "its real-time WebSocket supersedes delayed US equity quotes when trades arrive. "
            "EODHD Government Bonds supplies the US yield curve, while Yahoo Finance remains "
            "the near-real-time source for futures, spot equity indices and the identified fallback."
            if self.settings.eodhd_api_token else
            "Yahoo Finance public chart feed is active because EODHD is not configured."
        )
        return LiveMarketsResponse(
            generated_at=generated_at,
            refresh_seconds=REFRESH_SECONDS,
            cache_seconds=CACHE_SECONDS,
            item_count=len(ordered),
            groups=groups,
            errors=errors,
            methodology={
                "global": global_methodology,
                "b3": "Brapi Pro quote feed for Brazilian portfolio securities.",
                "refresh": "The browser refreshes every 30 seconds while visible and immediately after returning to the tab.",
                "fallback": "If a provider fails, the last valid quote remains visible and is marked stale.",
            },
        )

    def _fetch_eodhd(self, specs: list[MarketSpec]) -> list[LiveMarketItem]:
        if not self.settings.eodhd_api_token:
            raise RuntimeError("EODHD credential is not configured")
        client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
        normalized = []
        for suffix in (".US", ".FOREX", ".CC", ".INDX"):
            symbols = [spec.eodhd_symbol for spec in specs if spec.eodhd_symbol and spec.eodhd_symbol.endswith(suffix)]
            if not symbols:
                continue
            try:
                normalized.extend(client.quotes(symbols))
            except Exception:
                # One bad/unsupported symbol in a batch (e.g. an .INDX code
                # EODHD doesn't actually carry) must not lose every other
                # suffix's already-fetched quotes -- each group degrades on
                # its own via the Yahoo fallback below, independently.
                continue
        quotes = {item.provider_symbol: item for item in normalized}
        output: list[LiveMarketItem] = []
        for spec in specs:
            quote_item = quotes.get(spec.eodhd_symbol or "")
            if not quote_item:
                continue
            previous_close = quote_item.previous_close
            if previous_close is None and quote_item.change is not None:
                previous_close = quote_item.price - quote_item.change
            if previous_close is None and quote_item.change_percent is not None and quote_item.change_percent > -99.99:
                previous_close = quote_item.price / (1 + quote_item.change_percent / 100)
            delay_minutes = 15 if (spec.eodhd_symbol or "").endswith(".US") else 1
            item = LiveMarketItem(
                group=spec.group,
                symbol=spec.symbol,
                name=spec.name,
                provider_symbol=spec.eodhd_symbol or spec.provider_symbol,
                provider="EODHD All-In-One",
                exchange=quote_item.exchange,
                currency=quote_item.currency or spec.currency,
                price=quote_item.price,
                change=quote_item.change,
                change_percent=quote_item.change_percent,
                open=quote_item.open,
                low=quote_item.low,
                high=quote_item.high,
                previous_close=previous_close,
                market_state="REGULAR",
                status="delayed" if quote_item.is_delayed else "live",
                delay_minutes=delay_minutes if quote_item.is_delayed else 0,
                as_of=quote_item.as_of,
                collected_at=quote_item.collected_at,
                quality_score=quote_item.quality_score,
            )
            output.append(self._apply_eodhd_stream(spec, item))
        return output

    def _fetch_eodhd_bonds(self, specs: list[MarketSpec]) -> list[LiveMarketItem]:
        if not self.settings.eodhd_api_token:
            raise RuntimeError("EODHD credential is not configured")
        client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
        collected_at = datetime.now(timezone.utc)
        output: list[LiveMarketItem] = []
        for spec in specs:
            history = sorted(
                client.history(spec.eodhd_symbol or spec.provider_symbol, exchange="GBOND", days=30),
                key=lambda row: str(row.get("date") or ""),
            )
            if not history:
                continue
            latest = history[-1]
            price = number(latest.get("close"))
            if price is None:
                continue
            previous_close = number(history[-2].get("close")) if len(history) > 1 else None
            change = price - previous_close if previous_close is not None else None
            change_percent = change / previous_close * 100 if change is not None and previous_close else None
            try:
                as_of = datetime.fromisoformat(str(latest.get("date"))).replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                as_of = collected_at
            output.append(LiveMarketItem(
                group=spec.group,
                symbol=spec.symbol,
                name=spec.name,
                provider_symbol=spec.eodhd_symbol or spec.provider_symbol,
                provider="EODHD Government Bonds",
                exchange="GBOND",
                currency=spec.currency,
                price=price,
                change=change,
                change_percent=change_percent,
                open=None,
                low=None,
                high=None,
                previous_close=previous_close,
                market_state="EOD",
                status="closed",
                delay_minutes=0,
                as_of=as_of,
                collected_at=collected_at,
                quality_score=90 if previous_close is not None else 84,
            ))
        return output

    def _bond_snapshot(self, specs: list[MarketSpec], now: datetime) -> list[LiveMarketItem]:
        if self._bond_items and self._bond_cache_expires_at and now < self._bond_cache_expires_at:
            return self._bond_items
        items = self._fetch_eodhd_bonds(specs)
        if items:
            self._bond_items = items
            self._bond_cache_expires_at = now + timedelta(seconds=BOND_CACHE_SECONDS)
        return items

    def _apply_eodhd_stream(self, spec: MarketSpec, item: LiveMarketItem) -> LiveMarketItem:
        if not self.stream or spec.group != "Portfolio" or not (spec.eodhd_symbol or "").endswith(".US"):
            return item
        tick = self.stream.quote(spec.symbol)
        if not tick or tick.as_of < item.as_of:
            return item
        previous_close = item.previous_close
        change = tick.price - previous_close if previous_close else item.change
        change_percent = change / previous_close * 100 if change is not None and previous_close else item.change_percent
        is_open = tick.market_state.lower() in {"open", "extended-hours"}
        return item.model_copy(update={
            "provider": "EODHD Real-Time WebSocket",
            "price": tick.price,
            "change": change,
            "change_percent": change_percent,
            "market_state": tick.market_state.upper(),
            "status": "live" if is_open else "closed",
            "delay_minutes": 0,
            "as_of": tick.as_of,
            "collected_at": datetime.now(timezone.utc),
            "quality_score": max(item.quality_score, 92),
        })

    def _fetch_yahoo(self, spec: MarketSpec) -> LiveMarketItem:
        payload = self.http.get_json(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(spec.provider_symbol, safe='')}",
            params={"range": "1d", "interval": "5m"},
            headers={"User-Agent": "Mozilla/5.0 C3PO-Market-Console/1.0"},
        )
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        collected_at = datetime.now(timezone.utc)
        price = number(meta.get("regularMarketPrice"))
        if price is None:
            raise ValueError(f"{spec.symbol}: no market price")
        previous_close = number(meta.get("previousClose")) or number(meta.get("chartPreviousClose"))
        change = price - previous_close if previous_close else None
        change_percent = change / previous_close * 100 if change is not None and previous_close else None
        market_state = str(meta.get("marketState") or "UNKNOWN").upper()
        status = "closed" if market_state in {"CLOSED", "POST", "PRE"} else "delayed"
        optional = (
            previous_close,
            number(meta.get("regularMarketOpen")),
            number(meta.get("regularMarketDayLow")),
            number(meta.get("regularMarketDayHigh")),
        )
        quality = min(96, 80 + sum(value is not None for value in optional) * 4)
        return LiveMarketItem(
            group=spec.group,
            symbol=spec.symbol,
            name=spec.name,
            provider_symbol=spec.provider_symbol,
            provider="Yahoo Finance",
            exchange=str(meta.get("exchangeName") or meta.get("fullExchangeName") or "Global"),
            currency=str(meta.get("currency") or spec.currency),
            price=price,
            change=change,
            change_percent=change_percent,
            open=number(meta.get("regularMarketOpen")),
            low=number(meta.get("regularMarketDayLow")),
            high=number(meta.get("regularMarketDayHigh")),
            previous_close=previous_close,
            market_state=market_state,
            status=status,
            delay_minutes=DEFAULT_DELAY_MINUTES,
            as_of=from_unix(meta.get("regularMarketTime"), collected_at),
            collected_at=collected_at,
            quality_score=quality,
        )

    def _fetch_brapi(self, specs: list[MarketSpec]) -> list[LiveMarketItem]:
        if not self.settings.brapi_token:
            raise RuntimeError("Brapi credential is not configured")
        client = BrapiClient(self.settings.brapi_base_url, self.settings.brapi_token, self.http)
        quotes = {item.symbol: item for item in client.quotes([spec.provider_symbol for spec in specs])}
        output: list[LiveMarketItem] = []
        for spec in specs:
            item = quotes.get(spec.provider_symbol)
            if not item:
                continue
            output.append(LiveMarketItem(
                group=spec.group,
                symbol=spec.symbol,
                name=spec.name,
                provider_symbol=spec.provider_symbol,
                provider="Brapi Pro",
                exchange=item.exchange or "B3",
                currency=item.currency or spec.currency,
                price=item.price,
                change=item.change,
                change_percent=item.change_percent,
                open=item.open,
                low=item.low,
                high=item.high,
                previous_close=item.previous_close,
                market_state="REGULAR",
                status="delayed" if item.is_delayed else "live",
                delay_minutes=DEFAULT_DELAY_MINUTES if item.is_delayed else 0,
                as_of=item.as_of,
                collected_at=item.collected_at,
                quality_score=item.quality_score,
            ))
        return output
