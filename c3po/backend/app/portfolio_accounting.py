"""Native-currency position accounting. No provider calls or implied historical holdings."""
from dataclasses import dataclass
from datetime import date, timedelta
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


class AmbiguousDay(ValueError):
    pass


class Restatement(ValueError):
    pass


def restatements(events: list[dict]) -> list[tuple[str, str]]:
    """(symbol, date) of informed positions that disagree with the previous informed
    position of the same symbol plus the movements between them: a correction, not a trade."""
    key = lambda e: (str(e['effective_date']), e['sequence'])
    found = []
    for symbol in {e['symbol'] for e in events}:
        quantity, informed_day, moved = None, None, False
        for e in sorted((e for e in events if e['symbol'] == symbol), key=key):
            kind = e['kind']
            if kind == 'position':
                informed = amount(e['quantity'])
                # a second informed position on the same day, with no movement between them,
                # fixes a typing error: the last one is the informed position of that day
                same_day_fix = informed_day == str(e['effective_date']) and not moved
                if quantity is not None and informed != quantity and not same_day_fix:
                    found.append((symbol, str(e['effective_date'])))
                quantity, informed_day, moved = informed, str(e['effective_date']), False
                continue
            if kind != 'dividend':
                moved = True
            if quantity is None:
                continue
            if kind == 'buy':
                quantity += amount(e['quantity'])
            elif kind == 'sell':
                quantity -= amount(e['quantity'])
            elif kind == 'split':
                quantity = quantity * amount(e['quantity']) / amount(e.get('split_denominator', '1'))
    return found


def holdings_at(events: list[dict], day: date) -> dict[str, Position]:
    """Holdings at the close of `day`.

    For a symbol with no informed position up to `day` but one dated after it, the earliest
    such position (the last one on that date) is the reference: the holdings are reconstructed backwards from it, undoing that
    symbol's buys, sells and splits dated after `day` and before it. Otherwise the ledger
    is replayed forward. An informed position prevails over an incomplete earlier history.
    A movement on the same day as the reference position is ambiguous (before or after it?).
    """
    key = lambda e: (str(e['effective_date']), e['sequence'])
    ordered = sorted(events, key=key)
    positions = replay(events, day)
    later_snapshot: dict[str, dict] = {}
    for e in ordered:
        if e['kind'] == 'position' and str(e['effective_date']) > day.isoformat():
            first = later_snapshot.get(e['symbol'])
            # earliest date after `day`; on that date, the last informed position wins
            if first is None or str(e['effective_date']) == str(first['effective_date']):
                later_snapshot[e['symbol']] = e
    anchored = {e['symbol'] for e in ordered if e['kind'] == 'position' and str(e['effective_date']) <= day.isoformat()}
    for symbol, snap in later_snapshot.items():
        if symbol in anchored:
            # an informed position at or before `day` already anchors the forward replay
            continue
        if day < date(date.fromisoformat(str(snap['effective_date'])).year, 1, 1) - timedelta(days=1):
            # an informed position is projected back at most to the close before its own
            # year (31/12): earlier holdings of that symbol come only from recorded movements
            continue
        moves = [e for e in ordered if e['symbol'] == symbol and e['kind'] not in ('position', 'dividend')
                 and day.isoformat() < str(e['effective_date']) <= str(snap['effective_date'])]
        if any(str(e['effective_date']) == str(snap['effective_date']) for e in moves):
            raise AmbiguousDay(symbol)
        quantity = amount(snap['quantity'])
        for e in reversed(moves):
            if e['kind'] == 'buy':
                quantity -= amount(e['quantity'])
            elif e['kind'] == 'sell':
                quantity += amount(e['quantity'])
            elif e['kind'] == 'split':
                quantity = quantity * amount(e.get('split_denominator', '1')) / amount(e['quantity'])
            if quantity < 0:
                raise ValueError('Movimentações incompatíveis com a posição informada')
        positions.setdefault(symbol, Position()).quantity = quantity
    return positions


def period_result(events: list[dict], start: date, end: date, value_at: Any, rate_at: Any) -> dict:
    """Modified Dietz on the securities sleeve; dated flows assumed at day end.

    The period always starts on `start`. Holdings at the previous close and at `end` come
    from holdings_at (informed positions prevail and are reconstructed backwards). Buys,
    sells and dividends inside the period are the flows. No cash balance is retained.
    """
    from datetime import timedelta
    before = start - timedelta(days=1)
    result = {'start': start.isoformat(), 'end': end.isoformat(),
              'profit_usd': None, 'return_percent': None, 'reason': None}
    selected = [e for e in events if start.isoformat() <= str(e['effective_date']) <= end.isoformat()]
    if not any(e['kind'] == 'position' for e in events):
        first = min(events, key=lambda e:(str(e['effective_date']),e['sequence'])) if events else None
        if first is None or (str(first['effective_date']) > before.isoformat() and first['kind'] != 'buy'):
            result['reason'] = 'Sem posição comprovada no início do período'
            return result
    crossed = [(symbol, day) for symbol, day in restatements(events) if before.isoformat() < day <= end.isoformat()]
    if crossed:
        symbol, day = sorted(crossed, key=lambda x: x[1])[0]
        result['reason'] = f"Posição de {symbol} corrigida em {date.fromisoformat(day).strftime('%d/%m/%Y')}; a correção não é resultado"
        return result
    try:
        opening_positions, closing_positions = holdings_at(events, before), holdings_at(events, end)
    except AmbiguousDay as exc:
        result['reason'] = f'Movimentação de {exc.args[0]} no mesmo dia da posição informada; não se sabe se veio antes ou depois'
        return result
    except ValueError:
        result['reason'] = 'Movimentações incompatíveis com a posição informada'
        return result
    try:
        opening = value_at(opening_positions, before)
        closing = value_at(closing_positions, end)
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
