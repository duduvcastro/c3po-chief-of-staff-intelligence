"""Personal portfolio valuations, isolated from trading and diagnostic workers."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from .config import Settings
from .database import Database
from .market_data.eodhd import EodhdClient
from .market_data.http import JsonHttpClient
from .market_data.realtime import RealtimeMarketsService
from .portfolio_accounting import amount, current_values, period_result, Position


class PortfolioService:
    def __init__(self, settings: Settings, database: Database, realtime: RealtimeMarketsService):
        self.database, self.realtime = database, realtime
        self.provider = EodhdClient(settings.eodhd_base_url, settings.eodhd_api_token or '', JsonHttpClient(timeout=8, max_retries=0))
        self._history: dict[tuple, tuple[datetime, list[dict]]] = {}
        self._lock = RLock()

    def snapshot(self) -> dict[str, Any]:
        events = self.database.list_portfolio_events()
        now = datetime.now(timezone.utc)
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
                q = self.provider.quotes(['USDBRL.FOREX'])[0]
                ny = now.astimezone(ZoneInfo("America/New_York"))
                fx_closed = ny.weekday()==5 or (ny.weekday()==4 and ny.hour>=17) or (ny.weekday()==6 and ny.hour<17)
                max_age = timedelta(hours=72) if fx_closed else timedelta(minutes=30)
                if timedelta(0) <= now-q.as_of <= max_age and q.price > 0:
                    rate = amount(q.price)
                    fx = {'brl_per_usd': str(rate), 'as_of': q.as_of.isoformat(), 'source': 'EODHD'}
            except Exception:
                pass  # Provider error text may contain credentials.
        summary = current_values(events, quotes, rate)
        summary["unconfigured"] = sorted({e["symbol"] for e in self.database.list_realtime_portfolio()} - set(summary["positions"]))
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
                if len(self._history) > 1000:
                    self._history.clear()
                self._history[key] = (now+timedelta(minutes=30 if rows else 2), rows)
                return rows

        def historic(symbol: str, market: str, day: date) -> Decimal:
            rows = [r for r in bars(symbol, market) if r.get('date') and str(r['date']) <= day.isoformat() and r.get('close')]
            if not rows:
                raise ValueError('Missing history')
            row = max(rows, key=lambda r:str(r['date']))
            observed = date.fromisoformat(str(row['date']))
            if symbol == 'USDBRL.FOREX':
                if (day-observed).days > 4:
                    raise ValueError('Missing FX close')
            else:
                cal = xcals.get_calendar('BVMF' if market=='B3' else 'XNYS')
                required = cal.date_to_session(day.isoformat(), direction='previous').date()
                if observed != required:
                    raise ValueError('Missing session close')
            value = amount(row['close'])
            if value <= 0:
                raise ValueError('Invalid historical price')
            return value

        def rate_at(market: str, day: date) -> Decimal:
            if market != 'B3':
                return Decimal(1)
            if day == today:
                if rate is None:
                    raise ValueError('Missing current FX')
                return rate
            return historic('USDBRL.FOREX', 'FX', day)

        def value_at(positions: dict[str, Position], day: date) -> Decimal:
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
