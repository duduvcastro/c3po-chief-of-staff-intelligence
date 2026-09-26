from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.config import Settings
from app.database import Database
from app.portfolio_service import PortfolioService
from app.portfolio_split_basis import historical_price


def event(kind='buy', quantity='20', day='2022-05-02', total='2000'):
    return dict(request_id=str(uuid4()),symbol='AMZN',market='NASDAQ',kind=kind,
                effective_date=day,quantity=quantity,total=total,fees='0',split_denominator='1')


def snapshot(adjusted, original=False):
    db=Database(Settings())
    db.write_portfolio_event(event(quantity='1' if original else '20'))
    if original:db.write_portfolio_event(event('split','20','2022-06-06','0'))
    class Quote:
        symbol='AMZN'
        def model_dump(self):return dict(symbol='AMZN',price=100,currency='USD',status='live')
    svc=PortfolioService(Settings(portfolio_split_adjusted_symbols=None if adjusted is None else 'AMZN' if adjusted else ''),db,
        SimpleNamespace(portfolio_snapshot=lambda:SimpleNamespace(items=[Quote()])))
    svc.provider=SimpleNamespace(daily_bars=lambda *a,**kw:[
        dict(date='2022-05-31',close=2200,adjusted_close=999),
        dict(date='2022-06-06',close=110,adjusted_close=888),
        dict(date='2022-06-30',close=100,adjusted_close=777)])
    before=db.list_portfolio_events()
    out=svc._snapshot(before,[],datetime(2022,7,1,16,tzinfo=timezone.utc))
    assert db.list_portfolio_events()==before
    return out


def test_restated_and_original_ledgers_produce_same_june_profit_without_changing_cost():
    for adjusted, original in [(True,False),(False,True),(None,False)]:
        out=snapshot(adjusted,original)
        june=next(p for p in out['periods'] if p['label']=='06/2022')
        assert Decimal(june['profit_usd'])==Decimal('-200')
        assert out['summary']['positions']['AMZN']['quantity']=='20'
        assert out['summary']['positions']['AMZN']['total_cost']=='2000'


def test_unknown_basis_is_not_reported_as_a_loss():
    out=snapshot(False)
    assert next(p for p in out['periods'] if p['label']=='06/2022')['profit_usd'] is None


def test_double_adjustment_is_refused():
    out=snapshot(True,True)
    assert next(p for p in out['periods'] if p['label']=='06/2022')['profit_usd'] is None


@pytest.mark.parametrize('day,expected',[('2022-06-03','100'),('2022-06-06','2000')])
def test_exact_trading_boundary(day,expected):
    assert historical_price('AMZN',date.fromisoformat(day),Decimal(2000),[],{'AMZN'})==Decimal(expected)


def test_other_symbols_unchanged():
    assert historical_price('OTHER',date(2020,1,1),Decimal(2000),[],{'AMZN'})==2000


def test_owner_confirmed_default_is_only_amzn_and_empty_override_disables_it():
    for setting, expected in [(None, frozenset({"AMZN"})), ("", frozenset())]:
        svc=PortfolioService(Settings(portfolio_split_adjusted_symbols=setting),
            Database(Settings()),SimpleNamespace())
        assert svc.split_adjusted_symbols == expected
