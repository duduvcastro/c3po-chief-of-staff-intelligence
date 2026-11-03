"""One EODHD real-time snapshot for the six cash indices used across the application (owner 03/11/2026: FMP is cut and
the indices move to EODHD, whose plan is already paid). EODHD's index quotes are delayed (~15 min for IBOV, Nasdaq, NYSE
and DAX in the probe of 03/11/2026), so a card usually reads "delayed": quote_status says so from the quote's own time."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import logging
import httpx
from time import monotonic
from threading import Event, Lock, Thread
from typing import Literal
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from ..config import Settings
from ..schemas import LiveMarketItem, NormalizedQuote
from .eodhd import EodhdClient
from .http import JsonHttpClient, DeadlineJsonHttpClient


PROVIDER = 'EODHD'
# One refresh is one batch request that EODHD bills as six calls (one per symbol): at most one a minute (FMP's was 10 s)
CACHE_SECONDS = 60
# EODHD answers the Shanghai Composite as 000001.SHG: SSEC.INDX returned "NA" fields on 19/08/2026 and nothing in the
# probe of 03/11/2026. Kept apart so a provider-side change is a one-line edit.
SHANGHAI_EODHD_CODE = '000001.SHG'


@dataclass(frozen=True)
class IndexSpec:
    symbol: str
    name: str
    currency: str
    calendar: str
    eodhd_code: str  # the provider's code; the key of INDICES stays the symbol the application exposes


INDICES = {
    '^BVSP': IndexSpec('IBOV', 'Ibovespa B3', 'BRL', 'BVMF', 'BVSP.INDX'),
    '^IXIC': IndexSpec('NASDAQ', 'Nasdaq Composite', 'USD', 'XNYS', 'IXIC.INDX'),
    '^NYA': IndexSpec('NYSE', 'NYSE Composite', 'USD', 'XNYS', 'NYA.INDX'),
    '^N225': IndexSpec('Nikkei', 'Nikkei 225', 'JPY', 'XTKS', 'N225.INDX'),
    '000001.SS': IndexSpec('Shanghai', 'Shanghai Composite', 'CNY', 'XSHG', SHANGHAI_EODHD_CODE),
    '^GDAXI': IndexSpec('DAX', 'DAX Performance Index', 'EUR', 'XETR', 'GDAXI.INDX'),
}


@lru_cache(maxsize=6)
def _calendar(name: str):
    return xcals.get_calendar(name)


def quote_status(spec: IndexSpec, as_of: datetime, now: datetime) -> tuple[Literal['live', 'delayed', 'closed', 'stale'], str]:
    try:
        calendar = _calendar(spec.calendar)
        minute = now.replace(second=0, microsecond=0)
        session = calendar.minute_to_session(minute, direction='previous')
        if as_of < calendar.session_open(session).to_pydatetime():
            return 'stale', 'STALE'
        close = calendar.session_close(session).to_pydatetime()
        if spec.calendar == 'BVMF':
            # BVMF fixes 18:00 Sao Paulo even during US daylight saving time.
            # B3 cash closes at 16:00 New York (17:00/18:00 Sao Paulo).
            # Keep B3 holidays/special sessions; never inherit US early closes.
            regular_close = datetime.combine(
                session.date(), datetime.min.time().replace(hour=16),
                tzinfo=ZoneInfo('America/New_York'),
            )
            close = min(calendar.session_close(session).to_pydatetime(), regular_close)
        if now >= close:
            # A quote frozen before the close is not a closing observation.
            return ('closed', 'CLOSED') if as_of >= close - timedelta(minutes=5) else ('stale', 'STALE')
        if calendar.is_open_on_minute(minute, ignore_breaks=True) and not calendar.is_open_on_minute(minute):
            age = (now - as_of).total_seconds()
            return ('delayed' if age <= 25 * 60 else 'stale'), 'BREAK'
        if not calendar.is_open_on_minute(minute, ignore_breaks=True):
            return 'stale', 'STALE'
        age = (now - as_of).total_seconds()
        return ('live' if age <= 90 else 'delayed' if age <= 25 * 60 else 'stale'), 'REGULAR'
    except Exception:
        # Unknown calendar coverage is not evidence of a closed or live market.
        return 'stale', 'UNKNOWN'


class IndexQuotesService:
    def __init__(self, settings: Settings, http: JsonHttpClient) -> None:
        self.settings = settings
        if isinstance(http, JsonHttpClient):
            transport = getattr(http.client, '_transport', None) if http.client else None
            if transport is not None and not isinstance(transport, httpx.AsyncBaseTransport):
                raise ValueError('Index deadline client requires an asynchronous transport')
            self.http = DeadlineJsonHttpClient(timeout=3.0, transport=transport)
        else:
            self.http = http  # Explicit test double, no production transport.
        self._lock = Lock()
        self._refreshing: Event | None = None
        self._refresh_deadline = 0.0
        self._expires = datetime.min.replace(tzinfo=timezone.utc)
        self._items: dict[str, LiveMarketItem] = {}
        self._failed: set[str] = set(INDICES)

    def quote(self, symbol: str) -> LiveMarketItem:
        if symbol not in INDICES:
            raise ValueError('Unsupported cash index')
        now = datetime.now(timezone.utc)
        with self._lock:
            owner = self._refreshing is None and now >= self._expires
            if owner:
                self._refreshing = Event()
                self._refresh_deadline = monotonic() + 3.0
            pending = self._refreshing
            cold = symbol not in self._items
            deadline = self._refresh_deadline
        if owner:
            assert pending is not None
            def refresh():
                try:
                    fresh = self._fetch(now)
                    with self._lock:
                        self._failed = set(INDICES)
                        for key, item in fresh.items():
                            previous = self._items.get(key)
                            if previous is None or item.as_of >= previous.as_of:
                                self._items[key] = item
                                self._failed.discard(key)
                        self._expires = datetime.now(timezone.utc) + timedelta(seconds=CACHE_SECONDS)
                finally:
                    with self._lock:
                        self._refreshing = None
                        pending.set()
            Thread(target=refresh, daemon=True, name='index-quotes-refresh').start()
        if cold and pending is not None:
            # Shared batch deadline prevents six sequential cold waits.
            pending.wait(timeout=max(0.0, deadline-monotonic()))
        with self._lock:
            item = self._items.get(symbol)
            stale = symbol in self._failed
        if item is None:
            raise RuntimeError('EODHD index quote unavailable')
        now = datetime.now(timezone.utc)
        status, market_state = quote_status(INDICES[symbol], item.as_of, now)
        if stale:
            status = 'stale'
        return item.model_copy(update={
            'status': status, 'market_state': market_state,
            'delay_minutes': max(0, int((now - item.as_of).total_seconds() // 60)),
        })

    def _fetch(self, now: datetime) -> dict[str, LiveMarketItem]:
        """The six indices in ONE batch through the frozen EodhdClient.quotes (as live_markets reads .INDX codes). Without
        an EODHD token nothing is fetched and every quote() reports the index unavailable."""
        items: dict[str, LiveMarketItem] = {}
        if not self.settings.eodhd_api_token:
            return items
        by_code = {spec.eodhd_code.upper(): symbol for symbol, spec in INDICES.items()}
        try:
            client = EodhdClient(self.settings.eodhd_base_url, self.settings.eodhd_api_token, self.http)
            quotes = client.quotes([spec.eodhd_code for spec in INDICES.values()])
        except Exception as exc:
            # The class name only: a provider error may carry the URL and its token.
            logging.getLogger(__name__).warning("Index quote fetch failed (%s)", type(exc).__name__)
            return {}
        for quote in quotes:
            symbol = by_code.get(quote.provider_symbol.upper())
            if symbol is None:
                continue
            try:
                items[symbol] = self._normalize(symbol, quote, now)
            except (ValueError, TypeError, OverflowError, OSError):
                continue
        return items

    @staticmethod
    def _normalize(symbol: str, quote: NormalizedQuote, now: datetime) -> LiveMarketItem:
        spec = INDICES[symbol]
        price = quote.price
        if not math.isfinite(price) or price <= 0:
            raise ValueError('EODHD index quote has no valid price')
        # The helper stamps a record without a usable provider timestamp ("NA", missing) with its own collection instant:
        # that is no observation time, and a quote without one never becomes fresh.
        as_of = quote.as_of
        if as_of == quote.collected_at or as_of.timestamp() <= 0:
            raise ValueError('EODHD index quote has no provider timestamp')
        if as_of > now + timedelta(seconds=60):
            raise ValueError('EODHD index quote is future dated')

        def finite(value: float | None) -> float | None:
            return value if value is not None and math.isfinite(value) else None

        previous = finite(quote.previous_close)
        change = price - previous if previous is not None and previous > 0 else finite(quote.change)
        percent = change / previous * 100 if change is not None and previous is not None and previous > 0 else finite(quote.change_percent)
        status, state = quote_status(spec, as_of, now)
        return LiveMarketItem(
            # The currency is the index's own: the helper defaults a quote without one to USD.
            group='Index', symbol=spec.symbol, name=spec.name, provider_symbol=symbol,
            provider=PROVIDER, exchange=spec.calendar, currency=spec.currency,
            price=price, change=change, change_percent=percent, previous_close=previous,
            open=finite(quote.open), low=finite(quote.low), high=finite(quote.high),
            market_state=state, status=status, delay_minutes=max(0, int((now-as_of).total_seconds()//60)),
            as_of=as_of, collected_at=now, quality_score=quote.quality_score,
        )
