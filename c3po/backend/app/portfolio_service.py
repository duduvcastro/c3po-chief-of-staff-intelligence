"""Personal portfolio valuations, isolated from trading and diagnostic workers."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock, Event
from bisect import bisect_right
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .config import Settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient
from .market_data.realtime import RealtimeMarketsService
from .portfolio_accounting import amount, current_values, period_result, Position
from .portfolio_split_basis import historical_price, OWNER_CONFIRMED_RESTATED


class PortfolioService:
    def __init__(self, settings: Settings, database: Database, realtime: RealtimeMarketsService):
        self.database, self.realtime = database, realtime
        declared = settings.portfolio_split_adjusted_symbols
        self.split_adjusted_symbols = (OWNER_CONFIRMED_RESTATED if declared is None else
            frozenset(s.strip().upper() for s in declared.split(",") if s.strip()))
        self.provider = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token or '', JsonHttpClient(timeout=3, max_retries=0))
        self._history: dict[tuple, tuple[datetime, list[dict]]] = {}
        self._lock = RLock()
        self._snapshot_cache = None
        self._snapshot_pending: Event | None = None
        self._fx_cache = None

    def snapshot(self) -> dict[str, Any]:
        events = self.database.list_portfolio_events()
        watchlist = self.database.list_realtime_portfolio()
        key = json.dumps([events, watchlist], sort_keys=True, default=str)
        now = datetime.now(timezone.utc)
        with self._lock:
            cached = self._snapshot_cache
            if cached and cached[0] == key and now < cached[1]:
                return deepcopy(cached[2])
            if self._snapshot_pending is None:
                self._snapshot_pending = Event()
                owner = True
            else:
                owner = False
            pending = self._snapshot_pending
        if not owner:
            if not pending.wait(timeout=5):
                raise RuntimeError('Portfolio valuation in progress; try again shortly')
            with self._lock:
                cached = self._snapshot_cache
                if cached and cached[0] == key:
                    return deepcopy(cached[2])
            raise RuntimeError('Portfolio changed during valuation; try again shortly')
        try:
            result = self._snapshot(events, watchlist, now)
            with self._lock:
                self._snapshot_cache = (key, datetime.now(timezone.utc)+timedelta(seconds=60), result)
            return deepcopy(result)
        finally:
            with self._lock:
                self._snapshot_pending = None
                pending.set()

    def _snapshot(self, events, watchlist, now):
        today = now.astimezone(ZoneInfo('America/Sao_Paulo')).date()
        if not events:
            return {'events': [], 'summary': None, 'periods': [], 'fx': None, 'generated_at': now.isoformat()}
        try:
            quotes = {q.symbol: q.model_dump() for q in self.realtime.portfolio_snapshot().items}
        except Exception:
            quotes = {}  # Holdings remain editable when a quote provider fails.
        markets = {e['symbol']: e['market'] for e in events}
        rate: Decimal | None = None
        fx = None
        if 'B3' in markets.values():
            try:
                with self._lock:
                    cached_fx = self._fx_cache
                if cached_fx and now < cached_fx[0]:
                    q = cached_fx[1]
                else:
                    try:
                        q = self.provider.quotes(['USDBRL.FOREX'])[0]
                    except Exception:
                        q = None
                    with self._lock:
                        self._fx_cache = (now+timedelta(seconds=60), q)
                if q is None:
                    raise ValueError('FX unavailable')
                ny = now.astimezone(ZoneInfo("America/New_York"))
                fx_closed = ny.weekday()==5 or (ny.weekday()==4 and ny.hour>=17) or (ny.weekday()==6 and ny.hour<17)
                max_age = timedelta(hours=72) if fx_closed else timedelta(minutes=30)
                if timedelta(0) <= now-q.as_of <= max_age and q.price > 0:
                    rate = amount(q.price)
                    fx = {'brl_per_usd': str(rate), 'as_of': q.as_of.isoformat(), 'source': 'EODHD'}
            except Exception:
                pass  # Provider error text may contain credentials.
        summary = current_values(events, quotes, rate)
        summary["unconfigured"] = sorted({e["symbol"] for e in watchlist} - set(summary["positions"]))
        first = date.fromisoformat(str(min(events, key=lambda e:str(e['effective_date']))['effective_date']))
        history_start = first - timedelta(days=10)

        def bars(symbol: str, market: str) -> list[dict]:
            key = (symbol, market, history_start, today)
            with self._lock:
                cached = self._history.get(key)
                if cached and now < cached[0]:
                    return cached[1]
            try:
                provider_symbol = symbol if market=='FX' else f"{symbol}.{'SA' if market=='B3' else 'US'}"
                rows = self.provider.daily_bars(provider_symbol, exchange='SA' if market=='B3' else 'US', start=history_start, end=today-timedelta(days=1))
            except Exception:
                rows = []
            with self._lock:
                written_at = datetime.now(timezone.utc)
                self._history = {k: v for k, v in self._history.items() if v[0] > written_at}
                # Only retain the latest requested range for each symbol/market.
                self._history = {k: v for k, v in self._history.items() if k[:2] != key[:2]}
                self._history[key] = (now+timedelta(minutes=30 if rows else 2), rows)
            return rows

        needed = list(markets.items())
        if 'B3' in markets.values():
            needed.append(('USDBRL.FOREX', 'FX'))
        def load(item):
            symbol, market = item
            rows = sorted((r for r in bars(symbol, market) if r.get('date') and r.get('close')), key=lambda r:str(r['date']))
            return (symbol, market), ([str(r['date']) for r in rows], rows)
        with ThreadPoolExecutor(max_workers=min(16, max(1, len(needed)))) as pool:
            indexed = dict(pool.map(load, needed))

        inconsistent = set()
        for event in events:
            if event['kind'] != 'split':
                continue
            factor = amount(event['quantity']) / amount(event.get('split_denominator', '1'))
            dates, raw_rows = indexed[(event['symbol'], event['market'])]
            split_day = str(event['effective_date'])
            before = bisect_right(dates, (date.fromisoformat(split_day)-timedelta(days=1)).isoformat())-1
            after = before+1
            if before < 0 or after >= len(dates):
                continue
            if (date.fromisoformat(split_day)-date.fromisoformat(dates[before])).days > 7 or (date.fromisoformat(dates[after])-date.fromisoformat(split_day)).days > 7:
                continue
            old, new = amount(raw_rows[before]['close']), amount(raw_rows[after]['close'])
            # Conservative fail-closed check, not automatic price adjustment.
            # Large split + a >2x discontinuity in position value is ambiguous.
            if old <= 0 or (factor >= 2 or factor <= Decimal('0.5')) and not Decimal('0.5') <= factor*new/old <= 2:
                inconsistent.add(event['symbol'])

        @lru_cache(maxsize=None)
        def historic(symbol: str, market: str, day: date) -> Decimal:
            if symbol in inconsistent:
                raise ValueError('Historical close inconsistent with split')
            dates, rows = indexed[(symbol, market)]
            at = bisect_right(dates, day.isoformat()) - 1
            if at < 0:
                raise ValueError('Missing history')
            row = rows[at]
            observed = date.fromisoformat(str(row['date']))
            if symbol == 'USDBRL.FOREX':
                if (day-observed).days > 4:
                    raise ValueError('Missing FX close')
            else:
                cal = xcals.get_calendar('BVMF' if market=='B3' else 'XNYS', start='2006-01-01')
                required = cal.date_to_session(day.isoformat(), direction='previous').date()
                if observed != required:
                    raise ValueError('Missing session close')
            value = amount(row['close'])
            if value <= 0:
                raise ValueError('Invalid historical price')
            return historical_price(symbol, observed, value, events, self.split_adjusted_symbols)

        @lru_cache(maxsize=None)
        def rate_at(market: str, day: date) -> Decimal:
            if market != 'B3':
                return Decimal(1)
            if day == today:
                if rate is None:
                    raise ValueError('Missing current FX')
                return rate
            return historic('USDBRL.FOREX', 'FX', day)

        values = {}

        def value_at(positions: dict[str, Position], day: date) -> Decimal:
            cache_key = (day, tuple(sorted((symbol, p.quantity) for symbol, p in positions.items())))
            if cache_key in values:
                return values[cache_key]
            value = Decimal(0)
            for symbol, position in positions.items():
                if not position.quantity:
                    continue
                if day == today:
                    quote = quotes.get(symbol)
                    if not quote or quote['status']=='stale':
                        raise ValueError('Missing current quote')
                    price = amount(quote['price'])
                    if price <= 0:
                        raise ValueError('Invalid current price')
                else:
                    price = historic(symbol, markets[symbol], day)
                value += position.quantity * price / rate_at(markets[symbol], day)
            values[cache_key] = value
            return value

        periods = []
        requested = [('Hoje', today, today), ('Mês em andamento', today.replace(day=1), today),
                     ('Ano em andamento', today.replace(month=1,day=1), today)]
        last_month_end = today.replace(day=1)-timedelta(days=1)
        while last_month_end >= first and len(requested)<330:
            requested.append((last_month_end.strftime('%m/%Y'), last_month_end.replace(day=1), last_month_end))
            last_month_end = last_month_end.replace(day=1)-timedelta(days=1)
        for year in range(today.year-1, first.year-1, -1):
            requested.append((str(year),date(year,1,1),date(year,12,31)))
        for label, start, end in requested:
            periods.append(dict(label=label, **period_result(events,start,end,value_at,rate_at)))
        return {'events': events, 'summary': summary, 'periods': periods, 'fx': fx,
                'generated_at': now.isoformat(), 'history_from': first.isoformat(),
                'methodology': 'Resultado das posições cadastradas, sem saldo em caixa. Compras são aportes; vendas e proventos são retiradas. Percentuais ajustados pelas datas dos aportes e retiradas; são estimativas quando há movimentações no período. Custos e posições devem incluir desdobramentos. Lucro em aberto convertido pelo câmbio atual; resultados dos períodos usam câmbio de cada data.'}
