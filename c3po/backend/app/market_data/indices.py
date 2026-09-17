"""One FMP quote snapshot for the six cash indices used across the application."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
from threading import Lock
from typing import Literal

import exchange_calendars as xcals

from ..config import Settings
from ..schemas import LiveMarketItem
from .http import JsonHttpClient
from .models import number


@dataclass(frozen=True)
class IndexSpec:
    symbol: str
    name: str
    currency: str
    calendar: str


INDICES = {
    '^BVSP': IndexSpec('IBOV', 'Ibovespa B3', 'BRL', 'BVMF'),
    '^IXIC': IndexSpec('NASDAQ', 'Nasdaq Composite', 'USD', 'XNYS'),
    '^NYA': IndexSpec('NYSE', 'NYSE Composite', 'USD', 'XNYS'),
    '^N225': IndexSpec('Nikkei', 'Nikkei 225', 'JPY', 'XTKS'),
    '000001.SS': IndexSpec('Shanghai', 'Shanghai Composite', 'CNY', 'XSHG'),
    '^GDAXI': IndexSpec('DAX', 'DAX Performance Index', 'EUR', 'XETR'),
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
        if not calendar.is_open_on_minute(minute):
            return 'closed', 'CLOSED'
        age = (now - as_of).total_seconds()
        return ('live' if age <= 90 else 'delayed' if age <= 25 * 60 else 'stale'), 'REGULAR'
    except Exception:
        # Unknown calendar coverage is not evidence of a closed or live market.
        return 'stale', 'UNKNOWN'


class IndexQuotesService:
    def __init__(self, settings: Settings, http: JsonHttpClient) -> None:
        self.settings = settings
        self.http = http
        self._lock = Lock()
        self._expires = datetime.min.replace(tzinfo=timezone.utc)
        self._items: dict[str, LiveMarketItem] = {}
        self._failed: set[str] = set(INDICES)

    def quote(self, symbol: str) -> LiveMarketItem:
        if symbol not in INDICES:
            raise ValueError('Unsupported cash index')
        with self._lock:
            now = datetime.now(timezone.utc)
            if now >= self._expires:
                self._refresh(now)
            item = self._items.get(symbol)
            if item is None:
                raise RuntimeError('FMP index quote unavailable')
            now = datetime.now(timezone.utc)
            status, market_state = quote_status(INDICES[symbol], item.as_of, now)
            if symbol in self._failed:
                status = 'stale'
            return item.model_copy(update={
                'status': status, 'market_state': market_state,
                'delay_minutes': max(0, int((now - item.as_of).total_seconds() // 60)),
            })

    def _refresh(self, now: datetime) -> None:
        self._expires = now + timedelta(seconds=10)
        self._failed = set(INDICES)
        if not self.settings.fmp_api_token:
            return
        try:
            payload = self.http.get_json(
                f'{self.settings.fmp_base_url.rstrip("/")}/stable/batch-quote',
                params={'symbols': ','.join(INDICES), 'apikey': self.settings.fmp_api_token},
            )
            if not isinstance(payload, list):
                return
            for row in payload:
                if not isinstance(row, dict) or row.get('symbol') not in INDICES:
                    continue
                symbol = row['symbol']
                try:
                    item = self._normalize(symbol, row, now)
                except (ValueError, TypeError, OverflowError, OSError):
                    continue
                previous = self._items.get(symbol)
                if previous and item.as_of < previous.as_of:
                    continue
                self._items[symbol] = item
                self._failed.discard(symbol)
        except Exception:
            # Transport errors may contain a URL with the key; never expose it.
            return

    @staticmethod
    def _normalize(symbol: str, row: dict, now: datetime) -> LiveMarketItem:
        spec = INDICES[symbol]
        price, stamp = number(row.get('price')), number(row.get('timestamp'))
        if price is None or not math.isfinite(price) or price <= 0 or stamp is None or not math.isfinite(stamp) or stamp <= 0:
            raise ValueError('FMP index quote invalid')
        as_of = datetime.fromtimestamp(stamp, timezone.utc)
        if as_of > now + timedelta(seconds=60):
            raise ValueError('FMP index quote is future dated')
        def finite(key: str) -> float | None:
            value = number(row.get(key))
            return value if value is not None and math.isfinite(value) else None
        previous = finite('previousClose')
        change = price - previous if previous is not None and previous > 0 else finite('change')
        percent = change / previous * 100 if change is not None and previous is not None and previous > 0 else finite('changePercentage')
        status, state = quote_status(spec, as_of, now)
        return LiveMarketItem(
            group='Index', symbol=spec.symbol, name=spec.name, provider_symbol=symbol,
            provider='Financial Modeling Prep', exchange=spec.calendar, currency=spec.currency,
            price=price, change=change, change_percent=percent, previous_close=previous,
            open=finite('open'), low=finite('dayLow'), high=finite('dayHigh'),
            market_state=state, status=status, delay_minutes=max(0, int((now-as_of).total_seconds()//60)),
            as_of=as_of, collected_at=now, quality_score=95,
        )
