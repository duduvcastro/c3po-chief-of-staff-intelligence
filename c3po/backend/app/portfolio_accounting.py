"""Native-currency position accounting. No provider calls or implied historical holdings."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal('0')


def amount(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Valor numérico inválido") from exc
    if not number.is_finite() or number < 0:
        raise ValueError('Valor deve ser finito e não negativo')
    return number


@dataclass
class Position:
    quantity: Decimal = ZERO
    basis: Decimal = ZERO
    realized: Decimal = ZERO
    dividends: Decimal = ZERO


def replay(events: list[dict], through: date | None = None) -> dict[str, Position]:
    positions: dict[str, Position] = {}
    for event in sorted(events, key=lambda e: (str(e['effective_date']), e['sequence'])):
        if through and date.fromisoformat(str(event['effective_date'])) > through:
            continue
        position = positions.setdefault(event['symbol'], Position())
        quantity, total, fees = (amount(event[key]) for key in ('quantity', 'total', 'fees'))
        kind = event['kind']
        denominator = amount(event.get('split_denominator', '1'))
        if denominator <= 0 or (kind != 'split' and denominator != 1):
            raise ValueError('Denominador permitido apenas em desdobramento')
        if kind == 'position':
            if fees != 0:
                raise ValueError('Inclua as taxas no custo total da posição')
            if quantity == 0 and total != 0:
                raise ValueError('Posição sem ações deve ter custo zero')
            position.quantity, position.basis = quantity, total
        elif kind == 'buy':
            if quantity <= 0:
                raise ValueError('Quantidade da compra deve ser positiva')
            position.quantity += quantity
            position.basis += total + fees
        elif kind == 'sell':
            if quantity <= 0 or quantity > position.quantity:
                raise ValueError('Venda excede a quantidade disponível na data')
            if fees > total:
                raise ValueError('Taxas da venda excedem o valor total')
            basis_sold = position.basis * quantity / position.quantity
            position.quantity -= quantity
            position.basis -= basis_sold
            position.realized += total - fees - basis_sold
        elif kind == 'dividend':
            if quantity != 0 or fees > total:
                raise ValueError('Provento deve ter quantidade zero e taxas até o total')
            position.dividends += total - fees
        elif kind == 'split':
            if quantity <= 0 or position.quantity <= 0 or total != 0 or fees != 0:
                raise ValueError('Desdobramento exige fator positivo e posição existente, sem valor ou taxas')
            position.quantity = position.quantity * quantity / denominator
        else:
            raise ValueError('Movimentação inválida')
    return positions


def current_values(events: list[dict], quotes: dict[str, dict], brl_per_usd: Decimal | None) -> dict:
    positions = replay(events)
    rows: dict[str, dict] = {}
    total_basis = total_value = ZERO
    missing: list[str] = []
    for symbol, p in positions.items():
        quote = quotes.get(symbol)
        native = {'quantity': str(p.quantity), 'total_cost': str(p.basis),
                  'realized': str(p.realized), 'dividends': str(p.dividends),
                  'value': None, 'profit': None, 'profit_percent': None}
        rows[symbol] = native
        if p.quantity == 0:
            native.update(value='0', profit='0')
            continue
        if not quote or quote.get('status') == 'stale' or quote.get('price') is None:
            missing.append(symbol)
            continue
        try:
            price = amount(quote['price'])
        except ValueError:
            missing.append(symbol)
            continue
        if price <= 0:
            missing.append(symbol)
            continue
        value = p.quantity * price
        profit = value - p.basis
        native.update(value=str(value), profit=str(profit),
                      profit_percent=str(profit / p.basis * 100) if p.basis else None)
        currency = quote['currency']
        rate = Decimal(1) if currency == 'USD' else brl_per_usd if currency == 'BRL' else None
        if rate is None or rate <= 0:
            missing.append(symbol)
            continue
        total_value += value / rate
        total_basis += p.basis / rate
    complete = not missing
    return {'positions': rows, 'complete': complete, 'missing': missing,
            'value_usd': str(total_value) if complete else None,
            'cost_usd': str(total_basis) if complete else None,
            'profit_usd': str(total_value-total_basis) if complete else None,
            'profit_percent': str((total_value/total_basis-1)*100) if complete and total_basis else None}


def holdings_at_period_start(events: list[dict], start: date, end: date) -> dict[str, Position]:
    """Holdings at the close before `start`.

    A symbol without an informed position inside [start, end] is replayed forward.
    A symbol with one is reconstructed backwards from its latest informed position in
    the period, undoing that symbol's buys, sells and splits dated inside the period and
    ordered before it: the informed position already reflects them. Earlier informed
    positions inside the period are superseded by the latest one.
    """
    from datetime import timedelta
    before = start - timedelta(days=1)
    key = lambda e: (str(e['effective_date']), e['sequence'])
    ordered = sorted(events, key=key)
    inside = [e for e in ordered if start.isoformat() <= str(e['effective_date']) <= end.isoformat()]
    last_snapshot: dict[str, dict] = {}
    for e in inside:
        if e['kind'] == 'position':
            last_snapshot[e['symbol']] = e
    positions = replay(events, before)
    for symbol, snap in last_snapshot.items():
        quantity = amount(snap['quantity'])
        for e in reversed([e for e in inside if e['symbol'] == symbol and key(e) < key(snap)]):
            kind = e['kind']
            if kind == 'buy':
                quantity -= amount(e['quantity'])
            elif kind == 'sell':
                quantity += amount(e['quantity'])
            elif kind == 'split':
                quantity = quantity * amount(e.get('split_denominator', '1')) / amount(e['quantity'])
            if quantity < 0:
                raise ValueError('Movimentações do período incompatíveis com a posição informada')
        prior = positions.get(symbol)
        if prior is not None and prior.quantity and prior.quantity != quantity:
            # History before the period disagrees with the informed position: ambiguous restatement.
            raise ValueError('Movimentações do período incompatíveis com a posição informada')
        positions.setdefault(symbol, Position()).quantity = quantity
    return positions


def period_result(events: list[dict], start: date, end: date, value_at: Any, rate_at: Any) -> dict:
    """Modified Dietz on the securities sleeve; dated flows assumed at day end.

    Proceeds/dividends leave this sleeve. Purchases enter it. No cash balance is
    implicitly retained. A position correction cannot supply a historical flow.
    """
    from datetime import timedelta
    before = start - timedelta(days=1)
    result = {'start': start.isoformat(), 'end': end.isoformat(),
              'profit_usd': None, 'return_percent': None, 'reason': None}
    selected = [e for e in events if start.isoformat() <= str(e['effective_date']) <= end.isoformat()]
    snapshots = [e for e in selected if e['kind'] == 'position']
    if snapshots:
        # Informed positions are holdings as of their date. The period still starts on
        # `start`: holdings at the previous close are reconstructed from the latest
        # informed position by undoing the movements of the period recorded before it.
        try:
            opening_positions = holdings_at_period_start(events, start, end)
        except ValueError:
            result['reason'] = 'Movimentações do período incompatíveis com a posição informada'
            return result
    else:
        first = min(events, key=lambda e:(str(e['effective_date']),e['sequence'])) if events else None
        if first is None or (str(first['effective_date']) > before.isoformat() and first['kind'] != 'buy'):
            result['reason'] = 'Sem posição comprovada no início do período'
            return result
        opening_positions = replay(events, before)
    try:
        opening = value_at(opening_positions, before)
        closing = value_at(replay(events, end), end)
        flows = weighted = ZERO
        days = Decimal((end - before).days)
        for e in selected:
            total, fees = amount(e['total']), amount(e['fees'])
            flow = total+fees if e['kind']=='buy' else -(total-fees) if e['kind'] in ('sell','dividend') else ZERO
            if flow:
                day = date.fromisoformat(str(e['effective_date']))
                fx = rate_at(e['market'], day)
                flow /= fx
                flows += flow
                weighted += flow * Decimal((end-day).days) / days
        profit = closing-opening-flows
        capital = opening+weighted
        result.update(profit_usd=str(profit), return_percent=str(profit/capital*100) if capital>0 else None)
        if capital <= 0:
            result['reason'] = 'Base de capital insuficiente para percentual'
    except (ValueError, KeyError):
        result['reason'] = 'Cotação ou câmbio histórico indisponível para uma das posições'
    return result
