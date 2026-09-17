"""Independent RC4bis replay using original normalizers and IR event methods.

Does not import candidate acquisition/assessment/event builders. Clock injection
copies a function's globals locally; it never patches the live module globals.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from types import FunctionType, SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.investor_relations import InvestorRelationsService
from app.market_data.eodhd import EodhdClient
from app.market_data.finnhub import FinnhubClient


def _read(receipt: dict[str, Any], *, cutoff: datetime) -> Any:
    body = base64.b64decode(receipt['body_b64'], validate=True)
    start, end = (datetime.fromisoformat(receipt[key]) for key in ('started_at', 'received_at'))
    if (receipt['status'] != 200 or receipt['diagnostic'] is not None
            or any(clock.tzinfo is None or clock.utcoffset() is None for clock in (start, end))
            or not cutoff <= start <= end or hashlib.sha256(body).hexdigest() != receipt['payload_sha256']):
        raise ValueError('ORACLE_DIRECT_RECEIPT_UNKNOWN')
    return json.loads(body)


def _day(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('ORACLE_DIRECT_DATE_UNKNOWN')
    return date.fromisoformat(value)


def _finnhub_transactions(snapshot: dict[str, Any], cutoff: datetime) -> tuple[list[dict[str, Any]], bool]:
    symbol = snapshot['symbol']
    receipts = snapshot['finnhub_receipts']
    stack = [((cutoff-timedelta(days=180)).date(), cutoff.date())]
    rows = []
    # Independent iterative traversal: saturated parent bodies are excluded;
    # their two children must cover the entire inclusive parent interval.
    for receipt in receipts:
        if not stack:
            raise ValueError('ORACLE_FINNHUB_TREE_UNKNOWN')
        start, end = stack.pop()
        if (receipt['provider'] != 'finnhub' or receipt['path'] != '/api/v1/stock/insider-transactions'
                or receipt['parameters'] != {'symbol': symbol, 'from': start.isoformat(), 'to': end.isoformat()}):
            raise ValueError('ORACLE_FINNHUB_TREE_UNKNOWN')
        payload = _read(receipt, cutoff=cutoff)
        if not isinstance(payload, dict) or payload.get('symbol') != symbol or not isinstance(payload.get('data'), list):
            raise ValueError('ORACLE_FINNHUB_IDENTITY_UNKNOWN')
        data = payload['data']
        if len(data) >= 100:
            if start == end:
                raise ValueError('ORACLE_FINNHUB_COVERAGE_UNKNOWN')
            middle = start + timedelta(days=(end-start).days//2)
            stack.extend(((middle+timedelta(days=1), end), (start, middle)))
            continue
        rows.extend(data)
    if stack:
        raise ValueError('ORACLE_FINNHUB_COVERAGE_UNKNOWN')
    transactions = []
    for row in rows:
        if not isinstance(row, dict) or ('symbol' in row and row['symbol'] != symbol):
            raise ValueError('ORACLE_FINNHUB_ROW_UNKNOWN')
        transaction = FinnhubClient._normalize_transaction(row)
        if transaction is None:
            raise ValueError('ORACLE_DIRECT_NORMALIZATION_LOSS')
        if _day(transaction['transaction_date']) > cutoff.date():
            raise ValueError('ORACLE_DIRECT_FUTURE_RECORD')
        transactions.append(transaction)
    return transactions, bool(rows)


def _eodhd_transactions(snapshot: dict[str, Any], cutoff: datetime) -> list[dict[str, Any]]:
    symbol = snapshot['symbol']
    receipts = snapshot.get('eodhd_receipts', [])
    identity = snapshot.get('eodhd_identity_receipt')
    recognized = False
    if identity:
        body = base64.b64decode(identity['body_b64'], validate=True)
        path_symbol = symbol if '.' in symbol else symbol + '.US'
        if (identity['provider'] == 'eodhd' and identity['path'] == '/api/v1.1/fundamentals/' + path_symbol
                and identity['status'] == 200 and identity['diagnostic'] is None
                and hashlib.sha256(body).hexdigest() == identity['payload_sha256']):
            recognized = json.loads(body).get('General', {}).get('Code') == symbol
    offset = 0
    ended = False
    transactions = []
    for receipt in receipts:
        if (ended or receipt['provider'] != 'eodhd' or receipt['path'] != '/api/sec-filings/' + symbol + '/form4'
                or receipt['parameters'] != {'page[offset]': offset, 'page[limit]': 100}):
            raise ValueError('ORACLE_EODHD_PAGINATION_UNKNOWN')
        payload = _read(receipt, cutoff=cutoff)
        if (not isinstance(payload, dict) or not isinstance(payload.get('data'), list)
                or not isinstance(payload.get('links'), dict) or 'next' not in payload['links']
                or len(payload['data']) > 100):
            raise ValueError('ORACLE_EODHD_ENVELOPE_UNKNOWN')
        filings = payload['data']
        for filing in filings:
            if 'symbol' in filing:
                if filing['symbol'] != symbol:
                    raise ValueError('ORACLE_EODHD_IDENTITY_UNKNOWN')
                recognized = True
            filed_at = _day(filing['filed_at']).isoformat()
            if not isinstance(filing.get('non_derivative'), list):
                raise ValueError('ORACLE_EODHD_ROWS_UNKNOWN')
            for row in filing['non_derivative']:
                transaction = EodhdClient._normalize_form4_row(row, filed_at)
                if transaction is None:
                    raise ValueError('ORACLE_DIRECT_NORMALIZATION_LOSS')
                if _day(transaction['transaction_date']) > cutoff.date():
                    raise ValueError('ORACLE_DIRECT_FUTURE_RECORD')
                transactions.append(transaction)
        next_link = payload['links']['next']
        ended = next_link is None
        if not ended:
            parsed = urlsplit(next_link)
            if (not filings or parsed.scheme or parsed.netloc or parsed.fragment
                    or parsed.path not in (f'/api/sec-filings/{symbol}/form4', f'/api/sec-filings/{symbol}.US/form4')
                    or parse_qs(parsed.query) != {'page[offset]': [str(offset+len(filings))], 'page[limit]': ['100']}):
                raise ValueError('ORACLE_EODHD_PAGINATION_UNKNOWN')
        offset += len(filings)
    if not ended or not recognized:
        raise ValueError('ORACLE_EODHD_COVERAGE_UNKNOWN')
    return transactions


def independent_direct_events(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return original IR events or an explicit unknown-coverage diagnostic.

    This helper is an arithmetic oracle, not a second authorizing coverage gate.
    Even zero events remain separate from unknown/incomplete provider evidence.
    """
    cutoff = datetime.fromisoformat(snapshot['query_cutoff_at'])
    if (snapshot.get('schema') != 'DIRECT_INSIDER_RC4BIS_V1' or snapshot.get('market') != 'US'
            or cutoff.tzinfo is None or cutoff.utcoffset() is None):
        raise ValueError('ORACLE_DIRECT_SNAPSHOT_INVALID')
    try:
        transactions, has_rows = _finnhub_transactions(snapshot, cutoff)
        if has_rows:
            if snapshot.get('eodhd_receipts'):
                raise ValueError('ORACLE_PROVIDERS_MUST_NOT_UNION')
            provider = 'finnhub'
            original = InvestorRelationsService._finnhub_insider_events
        else:
            transactions = _eodhd_transactions(snapshot, cutoff)
            provider = 'eodhd'
            original = InvestorRelationsService._eodhd_insider_events
    except (ValueError, KeyError, TypeError, IndexError):
        return {'events': [], 'complete': False, 'provider': None, 'diagnostic': 'ORACLE_DIRECT_COVERAGE_UNKNOWN'}

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cutoff.astimezone(tz) if tz is not None else cutoff.replace(tzinfo=None)

    class RecordedTransactions:
        def insider_transactions(self, symbol: str, *, since: date) -> list[dict[str, Any]]:
            if symbol != snapshot['symbol'] or since != (cutoff-timedelta(days=180)).date():
                raise ValueError('ORACLE_DIRECT_WINDOW_MISMATCH')
            return copy.deepcopy(transactions)

    # Copy globals, not patch: concurrent application calls see the original
    # datetime and lookback. Only this replay's bound function uses the order's
    # explicitly authorized 180-day window and factual cutoff clock.
    replay = FunctionType(original.__code__, {**original.__globals__, 'datetime': Clock,
                          'FINNHUB_INSIDER_LOOKBACK_DAYS': 180}, original.__name__, original.__defaults__, original.__closure__)
    service = SimpleNamespace(settings=SimpleNamespace(finnhub_api_token='OFFLINE', eodhd_api_token='OFFLINE'),
                              finnhub=RecordedTransactions(), eodhd=RecordedTransactions())
    events = replay(service, snapshot['symbol'], '', None, snapshot['symbol'])
    # The source IR helper floors the lookback to a date; the origin DB query
    # then applies its factual datetime cutoff. Preserve that second boundary.
    events = [event for event in events if cutoff-timedelta(days=180) <= event['published_at'] <= cutoff]
    return {'events': events, 'complete': True, 'provider': provider, 'diagnostic': None}
