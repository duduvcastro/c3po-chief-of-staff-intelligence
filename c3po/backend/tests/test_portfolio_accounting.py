from decimal import Decimal

import pytest

from app.portfolio_accounting import current_values, replay


def event(symbol='ABC', kind='buy', quantity='10', total='100', fees='0', day='2026-09-01', sequence=1):
    return dict(symbol=symbol,market='NASDAQ',kind=kind,quantity=quantity,total=total,fees=fees,effective_date=day,sequence=sequence)


def test_sales_remove_average_cost_and_include_fees():
    p = replay([event(fees='2'), event(kind='sell',quantity='4',total='60',fees='1',sequence=2)])['ABC']
    assert (p.quantity,p.basis,p.realized)==(Decimal('6'),Decimal('61.2'),Decimal('18.2'))


def test_fractional_shares_and_split_preserve_basis():
    p=replay([event(quantity='0.5'),event(kind='split',quantity='4',total='0',sequence=2)])['ABC']
    assert p.quantity==2 and p.basis==100


def test_mixed_currencies_convert_only_totals_and_weight_percent():
    events=[event('BR'),event('US',quantity='2',total='50',sequence=2)]
    result=current_values(events,{'BR':{'price':15,'currency':'BRL'},'US':{'price':30,'currency':'USD'}},Decimal('5'))
    assert result['positions']['BR']['profit']=='50'
    assert Decimal(result['profit_usd'])==20
    assert Decimal(result['value_usd'])==90
    assert Decimal(result['cost_usd'])==70
    assert Decimal(result['profit_percent']) == (Decimal(90)/70-1)*100


@pytest.mark.parametrize('fx,status', [(None,'live'),(Decimal(5),'stale')])
def test_incomplete_never_becomes_complete_total(fx,status):
    result=current_values([event()],{'ABC':{'price':20,'currency':'BRL','status':status}},fx)
    assert not result['complete'] and result['profit_usd'] is None


def test_zero_basis_has_no_percentage():
    result=current_values([event(total='0')],{'ABC':{'price':20,'currency':'USD'}},None)
    assert result['profit_percent'] is None


@pytest.mark.parametrize('events',[
    [event(kind='sell')], [event(quantity='NaN')], [event(total='-1')],
    [event(kind='position',quantity='0',total='10')],
    [event(),event(kind='sell',total='1',fees='2',sequence=2)],
])
def test_invalid_ledger_refused(events):
    with pytest.raises(ValueError): replay(events)


def test_period_cash_flows_are_not_market_return():
    from datetime import date
    from app.portfolio_accounting import period_result
    events = [event(day='2026-08-31'),event(quantity='10',total='100',day='2026-09-15',sequence=2)]
    def value_at(positions, day):
        return sum(p.quantity * Decimal(10) for p in positions.values())
    result=period_result(events,date(2026,9,1),date(2026,9,30),value_at,lambda market,day:Decimal(1))
    assert Decimal(result['profit_usd'])==0 and Decimal(result['return_percent'])==0


def test_closed_period_uses_historical_holdings_and_dated_fx():
    from datetime import date
    from app.portfolio_accounting import period_result
    events=[dict(event(day='2026-08-31'),market='B3'),dict(event(kind='sell',quantity='5',total='75',day='2026-09-15',sequence=2),market='B3'),dict(event(quantity='100',total='1000',day='2026-10-01',sequence=3),market='B3')]
    dates=[]
    def rate(market,day):
        dates.append(day)
        return Decimal(5)
    def value_at(positions,day):
        return positions['ABC'].quantity * (Decimal(10) if day.month==8 else Decimal(15))/5
    result=period_result(events,date(2026,9,1),date(2026,9,30),value_at,rate)
    assert Decimal(result['profit_usd'])==10
    assert dates==[date(2026,9,15)]


def test_position_restatement_makes_period_unknown():
    from datetime import date
    from app.portfolio_accounting import period_result
    result=period_result([event(day='2026-08-31'),event(kind='position',day='2026-09-02',sequence=2)],date(2026,9,1),date(2026,9,30),None,None)
    assert result['profit_usd'] is None and 'correção' in result['reason']


def test_missing_history_does_not_return_zero_profit():
    from datetime import date
    from app.portfolio_accounting import period_result
    def fail(*args): raise ValueError('missing')
    result=period_result([event(day='2026-08-31')],date(2026,9,1),date(2026,9,30),fail,None)
    assert result['profit_usd'] is None
