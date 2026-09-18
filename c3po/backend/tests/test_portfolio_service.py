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
