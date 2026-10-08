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


def _flat_value(price):
    def value_at(positions, day):
        return sum(p.quantity * price(day) for p in positions.values())
    return value_at


def test_positions_informed_on_the_first_day_measure_the_whole_month():
    from datetime import date
    from app.portfolio_accounting import period_result
    events=[event(kind='position',quantity='10',total='50',day='2026-10-01')]
    price=lambda day: Decimal(10) if day < date(2026,10,1) else Decimal(12)
    result=period_result(events,date(2026,10,1),date(2026,10,6),_flat_value(price),lambda market,day:Decimal(1))
    assert result['start']=='2026-10-01' and result['reason'] is None
    assert Decimal(result['profit_usd'])==Decimal(20) and Decimal(result['return_percent'])==Decimal(20)


def _period(events, start, end, price):
    from app.portfolio_accounting import period_result
    return period_result(events, start, end, _flat_value(price), lambda market, day: Decimal(1))


def test_year_starts_on_january_first_with_positions_informed_later():
    from datetime import date
    # caso do dono: compra em março lançada, posição informada em 01/10 com 15 ações
    events=[event(quantity='10',total='100',day='2026-03-10'),
            event(kind='position',quantity='15',total='150',day='2026-10-01',sequence=2)]
    price=lambda day: Decimal(8) if day < date(2026,3,10) else Decimal(10) if day < date(2026,10,1) else Decimal(12)
    result=_period(events,date(2026,1,1),date(2026,10,6),price)
    # 5 ações em 31/12 a 8 = 40; compra de 100 em 10/03; 15 ações a 12 = 180 hoje
    assert result['start']=='2026-01-01' and result['reason'] is None
    assert Decimal(result['profit_usd'])==Decimal(180-40-100)


def test_buy_sell_and_split_before_the_informed_position_are_undone():
    from datetime import date
    # 8 ações em 31/12 (posição anterior ao ano), compra 12, venda 5, split 2:1, posição informada 30
    events=[event(quantity='8',total='80',day='2025-11-03'),
            event(quantity='12',total='120',day='2026-04-01',sequence=2),
            event(kind='sell',quantity='5',total='60',day='2026-05-02',sequence=3),
            event(kind='split',quantity='2',total='0',day='2026-06-01',sequence=4),
            event(kind='position',quantity='30',total='150',day='2026-10-01',sequence=5)]
    price=lambda day: Decimal(10) if day < date(2026,6,1) else Decimal(5)
    result=_period(events,date(2026,1,1),date(2026,10,6),price)
    # abertura 8*10=80; fechamento 30*5=150; fluxos +120 -60
    assert result['reason'] is None
    assert Decimal(result['profit_usd'])==Decimal(150-80-120+60)


def test_dividend_in_the_year_is_returned_to_the_owner():
    from datetime import date
    events=[event(kind='position',quantity='10',total='100',day='2026-10-01'),
            event(kind='dividend',quantity='0',total='7',day='2026-10-02',sequence=2)]
    result=_period(events,date(2026,1,1),date(2026,10,6),lambda day: Decimal(10))
    assert Decimal(result['profit_usd'])==Decimal(7)


def test_movements_inconsistent_with_the_informed_position_stay_unknown():
    from datetime import date
    events=[event(quantity='10',total='100',day='2026-03-10'),
            event(kind='position',quantity='4',total='40',day='2026-10-01',sequence=2)]
    result=_period(events,date(2026,1,1),date(2026,10,6),lambda day: Decimal(10))
    assert result['profit_usd'] is None and 'incompatíveis' in result['reason']


def test_informed_position_prevails_over_incomplete_earlier_history():
    from datetime import date
    # revisão #444: 10 AAPL compradas em março; posição de 50 informada em 01/10
    events=[event(quantity='10',total='100',day='2026-03-10'),
            event(kind='position',quantity='50',total='500',day='2026-10-01',sequence=2)]
    price=lambda day: Decimal(10) if day < date(2026,10,1) else Decimal(12)
    month=_period(events,date(2026,10,1),date(2026,10,6),price)
    assert month['reason'] is None and Decimal(month['profit_usd'])==Decimal(50*12-50*10)
    year=_period(events,date(2026,1,1),date(2026,10,6),price)
    # 40 em 31/12 a 10; compra de 100; 50 a 12 hoje
    assert year['reason'] is None and Decimal(year['profit_usd'])==Decimal(600-400-100)


def test_past_month_is_reconstructed_from_a_later_informed_position():
    from datetime import date
    events=[event(quantity='10',total='100',day='2026-03-10'),
            event(kind='position',quantity='50',total='500',day='2026-10-01',sequence=2)]
    price=lambda day: Decimal(10) if day <= date(2026,8,31) else Decimal(11)
    september=_period(events,date(2026,9,1),date(2026,9,30),price)
    # 50 ações em 31/08 e em 30/09 (reconstruídas da posição de 01/10): 50*(11-10)
    assert september['reason'] is None and Decimal(september['profit_usd'])==Decimal(50)


def test_movement_on_the_day_of_the_informed_position_is_ambiguous():
    from datetime import date
    events=[event(kind='position',quantity='10',total='100',day='2026-10-01'),
            event(quantity='5',total='60',day='2026-10-01',sequence=2)]
    result=_period(events,date(2026,9,1),date(2026,9,30),lambda day: Decimal(10))
    assert result['profit_usd'] is None and 'mesmo dia' in result['reason']


def test_same_day_typo_fix_of_an_informed_position_is_not_profit():
    from datetime import date
    events=[event(kind='position',quantity='5',total='50',day='2026-10-01'),
            event(kind='position',quantity='50',total='500',day='2026-10-01',sequence=2)]
    price=lambda day: Decimal(10) if day < date(2026,10,1) else Decimal(12)
    result=_period(events,date(2026,1,1),date(2026,10,6),price)
    # vale a última posição do dia (50): 50*(12-10), sem lucro fictício da correção
    assert result['reason'] is None and Decimal(result['profit_usd'])==Decimal(100)


def test_correction_on_a_later_date_is_not_profit():
    from datetime import date
    events=[event(kind='position',quantity='10',total='100',day='2026-03-01'),
            event(kind='position',quantity='50',total='500',day='2026-10-01',sequence=2)]
    price=lambda day: Decimal(10) if day <= date(2026,3,31) else Decimal(12)
    assert 'corrigida' in _period(events,date(2026,1,1),date(2026,10,6),price)['reason']
    # períodos que não atravessam a correção usam a posição vigente (10 ações em abril)
    april=_period(events,date(2026,4,1),date(2026,4,30),price)
    assert april['reason'] is None and Decimal(april['profit_usd'])==Decimal(10*2)


def test_dividend_on_the_day_of_the_informed_position_is_not_ambiguous():
    from datetime import date
    events=[event(kind='position',quantity='10',total='100',day='2026-10-01'),
            event(kind='dividend',quantity='0',total='7',day='2026-10-01',sequence=2)]
    result=_period(events,date(2026,1,1),date(2026,10,6),lambda day: Decimal(10))
    assert result['reason'] is None and Decimal(result['profit_usd'])==Decimal(7)


def test_missing_history_does_not_return_zero_profit():
    from datetime import date
    from app.portfolio_accounting import period_result
    def fail(*args): raise ValueError('missing')
    result=period_result([event(day='2026-08-31')],date(2026,9,1),date(2026,9,30),fail,None)
    assert result['profit_usd'] is None


def test_amzn_position_subtracts_entire_acquisition_cost():
    result = current_values([event('AMZN', kind='position', quantity='2250', total='243175.500')], {'AMZN': {'price': Decimal('249.74'), 'currency': 'USD'}}, None)
    position = result['positions']['AMZN']
    assert Decimal(position['value']) == Decimal('561915.00')
    assert Decimal(position['total_cost']) == Decimal('243175.50')
    assert Decimal(position['profit']) == Decimal('318739.50')
    assert Decimal(result['profit_usd']) == Decimal('318739.50')
