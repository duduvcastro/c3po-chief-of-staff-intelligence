from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.config import Settings
from app.database import Database
from app.portfolio_service import PortfolioService

NOW=datetime(2026,9,17,16,tzinfo=timezone.utc)
class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return NOW

class Provider:
    def __init__(self):self.calls=[];self.bad_fx=False
    def quotes(self,symbols):
        return [SimpleNamespace(price=6,as_of=NOW.replace(year=2025) if self.bad_fx else NOW)]
    def daily_bars(self,symbol,**kwargs):
        self.calls.append(symbol)
        return [{'date':'2026-09-16','close':5 if symbol=='USDBRL.FOREX' else 10}]

class Quote:
    symbol="TEST3"
    def model_dump(self):return {'symbol':'TEST3','price':12,'currency':'BRL','status':'live'}


def setup():
    db=Database(Settings())
    db.write_portfolio_event(dict(request_id=str(uuid4()),symbol='TEST3',market='B3',kind='position',effective_date='2026-09-15',quantity='10',total='100',fees='0'))
    realtime=SimpleNamespace(portfolio_snapshot=lambda:SimpleNamespace(items=[Quote()]))
    service=PortfolioService(Settings(),db,realtime)
    provider=Provider();service.provider=provider
    return service,provider


def test_dated_fx_includes_exchange_effect_and_history_is_cached():
    service,provider=setup()
    with patch('app.portfolio_service.datetime',Clock):
        result=service.snapshot();service.snapshot()
    assert result['summary']['positions']['TEST3']['profit']=='20'
    assert result['summary']['value_usd']=='20'
    assert result['periods'][0]['profit_usd']=='0'
    assert result['periods'][0]['return_percent']=='0'
    assert sorted(provider.calls)==['TEST3.SA','USDBRL.FOREX']
    assert result['periods'][1]['profit_usd'] is None  # No invented month-opening position.


def test_stale_fx_blocks_aggregate_but_preserves_native_profit():
    service,provider=setup();provider.bad_fx=True
    with patch('app.portfolio_service.datetime',Clock):result=service.snapshot()
    assert result['summary']['positions']['TEST3']['profit']=='20'
    assert result['summary']['profit_usd'] is None
    assert result['periods'][0]['profit_usd'] is None


def test_quote_outage_retains_saved_quantity_and_cost():
    service,_=setup()
    def unavailable():raise RuntimeError('redacted')
    service.realtime.portfolio_snapshot=unavailable
    with patch('app.portfolio_service.datetime',Clock):result=service.snapshot()
    assert result['summary']['positions']['TEST3']['quantity']=='10'
    assert result['summary']['positions']['TEST3']['total_cost']=='100'
    assert result['summary']['value_usd'] is None


def test_snapshot_cache_is_invalidated_by_ledger_change_and_not_mutable():
    service, provider = setup()
    with patch('app.portfolio_service.datetime', Clock):
        first = service.snapshot()
        first['summary']['positions'].clear()
        assert service.snapshot()['summary']['positions']
        service.database.write_portfolio_event(dict(request_id=str(uuid4()),symbol='TEST3',market='B3',kind='buy',effective_date='2026-09-17',quantity='1',total='12',fees='0'))
        assert service.snapshot()['summary']['positions']['TEST3']['quantity'] == '11'
    assert sorted(provider.calls) == ['TEST3.SA','USDBRL.FOREX']


def test_provider_io_does_not_hold_shared_cache_lock():
    from concurrent.futures import ThreadPoolExecutor
    service, provider = setup()
    original = provider.daily_bars
    def read(symbol, **kwargs):
        def acquire():
            got = service._lock.acquire(timeout=0.5)
            if got: service._lock.release()
            return got
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(acquire).result(timeout=1)
        return original(symbol, **kwargs)
    provider.daily_bars = read
    with patch('app.portfolio_service.datetime', Clock):
        assert service.snapshot()['summary']['complete']


def test_simultaneous_snapshot_has_single_valuation():
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    service, _ = setup()
    entered, release = Event(), Event()
    original = service._snapshot
    calls = []
    def blocked(*args):
        calls.append(1); entered.set()
        assert release.wait(3)
        return original(*args)
    with patch.object(service, '_snapshot', blocked), patch('app.portfolio_service.datetime', Clock):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(service.snapshot)
            assert entered.wait(1)
            second = pool.submit(service.snapshot)
            release.set()
            assert first.result() == second.result()
    assert len(calls) == 1


def test_long_history_is_indexed_once_and_warm_snapshot_skips_valuation():
    from datetime import date, timedelta
    from time import perf_counter
    from app.schemas import RealtimePortfolioItem
    db = Database(Settings())
    symbols = [f'T{i}' for i in range(15)]
    for symbol in symbols:
        db.write_portfolio_event(dict(request_id=str(uuid4()),symbol=symbol,market='NASDAQ',kind='buy',effective_date='2006-09-25',quantity='10',total='100',fees='0'))
    quotes = [SimpleNamespace(symbol=s, model_dump=lambda s=s: {'symbol':s,'price':12,'currency':'USD','status':'live'}) for s in symbols]
    service = PortfolioService(Settings(), db, SimpleNamespace(portfolio_snapshot=lambda: SimpleNamespace(items=quotes)))
    rows=[];day=date(2006,9,15)
    while day < NOW.date():
        rows.append({'date':day.isoformat(),'close':10});day+=timedelta(days=1)
    calls=[]
    service.provider=SimpleNamespace(daily_bars=lambda symbol,**kw: calls.append(symbol) or rows)
    with patch('app.portfolio_service.datetime',Clock):
        started=perf_counter();result=service.snapshot();cold=perf_counter()-started
        with patch.object(service,'_snapshot',side_effect=AssertionError('warm cache must not revalue')):
            started=perf_counter();again=service.snapshot();warm=perf_counter()-started
    assert result==again and len(calls)==15
    assert len(result['periods'])>200
    print(f'portfolio15_20years cold={cold:.4f}s warm={warm:.4f}s')


def test_nvda_public_reference_not_provider_capture_uses_raw_close_and_rejects_adjusted_input():
    # PUBLIC_REFERENCE_NOT_PROVIDER_CAPTURE. NVIDIA 10:1 ex-date2024-06-10.
    # Reference values per Fable5823256202; no EODHD payload claimed.
    from decimal import Decimal
    now=datetime(2024,6,11,16,tzinfo=timezone.utc)
    class SplitClock(datetime):
        @classmethod
        def now(cls,tz=None):return now
    def run(preclose):
        db=Database(Settings())
        db.write_portfolio_event(dict(request_id=str(uuid4()),symbol='NVDA',market='NASDAQ',kind='buy',effective_date='2024-06-06',quantity='1',total='1200',fees='0'))
        db.write_portfolio_event(dict(request_id=str(uuid4()),symbol='NVDA',market='NASDAQ',kind='split',effective_date='2024-06-10',quantity='10',total='0',fees='0'))
        q=SimpleNamespace(symbol='NVDA', model_dump=lambda:{'price':121.79,'currency':'USD','status':'live'})
        service=PortfolioService(Settings(),db,SimpleNamespace(portfolio_snapshot=lambda:SimpleNamespace(items=[q])))
        service.provider=SimpleNamespace(daily_bars=lambda *a,**k:[
            {'date':'2024-06-06','close':1200,'adjusted_close':120},
            {'date':'2024-06-07','close':preclose,'adjusted_close':120.888},
            {'date':'2024-06-10','close':121.79,'adjusted_close':12.179}])
        with patch('app.portfolio_service.datetime',SplitClock): result=service.snapshot()
        return result
    good=run(1208.88)
    assert Decimal(good['summary']['positions']['NVDA']['quantity'])==10
    assert Decimal(good['summary']['value_usd'])==Decimal('1217.90')
    assert Decimal(good['periods'][0]['profit_usd'])==0  # June11 unchanged from raw June10.
    bad=run(120.888)
    assert bad['periods'][0]['profit_usd'] is None
    assert bad['periods'][0]['reason']
    # June7→June10 true return is +0.746%, not a fictitious +900%.
    assert Decimal('0.007') < Decimal('1217.9')/Decimal('1208.88')-1 < Decimal('0.008')


def test_history_cache_evicts_expired_and_replaced_ranges():
    from datetime import timedelta
    service, provider = setup()
    for i in range(100):
        service._history[(str(i), 'B3', '2006-01-01', '2026-09-16')] = (NOW-timedelta(seconds=1), [{}])
    service._history[('TEST3','B3','2006-01-01','2026-09-16')] = (NOW+timedelta(days=1), [{}])
    with patch('app.portfolio_service.datetime', Clock):
        service.snapshot()
    assert len(service._history) == 2
    assert all(k[2] != '2006-01-01' for k in service._history)


def test_historical_calendar_start_is_fixed_before_accepted_events():
    import app.portfolio_service as module
    service, provider = setup()
    actual = module.xcals.get_calendar
    calls = []
    def checked(name, **kwargs):
        calls.append(kwargs)
        assert kwargs['start'] == '2006-01-01'
        cal = actual(name, **kwargs)
        assert cal.is_session('2006-09-25')
        return cal
    with patch('app.portfolio_service.datetime', Clock), patch.object(module.xcals, 'get_calendar', checked):
        result = service.snapshot()
    assert calls
    assert result['periods'][0]['profit_usd'] == '0'
