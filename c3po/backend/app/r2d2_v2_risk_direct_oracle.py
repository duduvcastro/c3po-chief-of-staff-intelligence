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


class OracleProvenanceError(ValueError):
    """Corrupted/misbound evidence cannot enable provider fallback."""


class OracleProviderFailure(ValueError):
    """A recorded provider failure can enable the expressly opted-in contract."""


# Independent pin of the owner-approved normative contract; never accept an
# arbitrary nonempty flag or import a candidate selection helper.
FALLBACK_CONTRACT_SHA256 = hashlib.sha256(
    b"RC4BIS_REV3:Finnhub_attempt_verified;EODHD_on_HTTP_transport_invalid_future_empty_or_truncated;no_union;full_EODHD_coverage;integrity_failure_never_fallback"
).hexdigest()
FABLE_DISPOSITION_SHA256 = "b7a80c08cc600bc1314b49966816575e650e86f8daf6fe801705c31c8ae627be"


def _integrity(receipt: dict[str, Any], *, cutoff: datetime | None) -> bytes:
    try:
        body = base64.b64decode(receipt['body_b64'], validate=True)
        start, end = (datetime.fromisoformat(receipt[key]) for key in ('started_at', 'received_at'))
        if (any(clock.tzinfo is None or clock.utcoffset() is None for clock in (start, end))
                or start > end or (cutoff is not None and start < cutoff)
                or hashlib.sha256(body).hexdigest() != receipt['payload_sha256']):
            raise ValueError('invalid')
        return body
    except (ValueError, TypeError, KeyError):
        raise OracleProvenanceError('ORACLE_DIRECT_PROVENANCE_INVALID') from None


def _strict_json(body: bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError('duplicate')
            output[key] = value
        return output
    def nonfinite(_: str) -> Any:
        raise ValueError('nonfinite')
    return json.loads(body, object_pairs_hook=unique, parse_constant=nonfinite)


def _read(receipt: dict[str, Any], *, cutoff: datetime) -> Any:
    body = _integrity(receipt, cutoff=cutoff)
    status, diagnostic = receipt['status'], receipt['diagnostic']
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        raise OracleProvenanceError('ORACLE_STATUS_EVIDENCE_INVALID')
    if status is None:
        if diagnostic != 'TRANSPORT_FAILED' or body:
            raise OracleProvenanceError('ORACLE_TRANSPORT_EVIDENCE_INVALID')
        raise OracleProviderFailure('FINNHUB_TRANSPORT_FAILED')
    if status != 200:
        if diagnostic not in (None, 'HTTP_FAILED'):
            raise OracleProvenanceError('ORACLE_HTTP_EVIDENCE_INVALID')
        raise OracleProviderFailure('FINNHUB_HTTP_' + str(status))
    if diagnostic not in (None, 'JSON_INVALID', 'BODY_REJECTED'):
        raise OracleProvenanceError('ORACLE_DIAGNOSTIC_EVIDENCE_INVALID')
    if diagnostic == 'BODY_REJECTED':
        if body:
            raise OracleProvenanceError('ORACLE_BODY_REJECTION_UNPROVEN')
        raise OracleProviderFailure('FINNHUB_BODY_REJECTED')
    try:
        payload = _strict_json(body)
    except (ValueError, UnicodeError, RecursionError):
        raise OracleProviderFailure('FINNHUB_JSON_INVALID') from None
    if diagnostic == 'JSON_INVALID':
        raise OracleProvenanceError('ORACLE_JSON_FAILURE_UNPROVEN')
    return payload


def _day(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('ORACLE_DIRECT_DATE_UNKNOWN')
    return date.fromisoformat(value)


def _finnhub_transactions(snapshot: dict[str, Any], cutoff: datetime) -> tuple[list[dict[str, Any]], bool]:
    symbol = snapshot['symbol']
    receipts = snapshot['finnhub_receipts']
    stack = [((cutoff-timedelta(days=180)).date(), cutoff.date())]
    rows = []
    # Independent iterative traversal excludes capped/truncated parent rows.
    for receipt_index, receipt in enumerate(receipts):
        try:
            if not stack:
                raise OracleProvenanceError('ORACLE_FINNHUB_TREE_UNKNOWN')
            start, end = stack.pop()
            if (receipt['provider'] != 'finnhub' or receipt['path'] != '/api/v1/stock/insider-transactions'
                    or receipt['parameters'] != {'symbol': symbol, 'from': start.isoformat(), 'to': end.isoformat()}):
                raise OracleProvenanceError('ORACLE_FINNHUB_TREE_UNKNOWN')
            payload = _read(receipt, cutoff=cutoff)
            if not isinstance(payload, dict) or payload.get('symbol') != symbol or not isinstance(payload.get('data'), list):
                raise OracleProviderFailure('FINNHUB_ENVELOPE_IDENTITY_UNKNOWN')
            data = payload['data']
            for row in data:
                if not isinstance(row, dict):
                    raise OracleProviderFailure('FINNHUB_ROWS_INVALID')
                try:
                    in_window = start <= _day(row.get('transactionDate')) <= end
                except ValueError:
                    in_window = False
                if not in_window:
                    raise OracleProviderFailure('FINNHUB_REQUEST_WINDOW_NOT_OBSERVED')
            split = len(data) >= 100
            for key in ('next', 'nextPage', 'next_page', 'nextCursor', 'next_cursor', 'hasMore', 'has_more', 'pagination', 'links'):
                split = split or payload.get(key) not in (None, False, '', [], {})
            for key in ('total', 'totalCount', 'total_count'):
                if key in payload:
                    total = payload[key]
                    if type(total) is not int or total < len(data):
                        raise OracleProviderFailure('FINNHUB_TOTAL_METADATA_INVALID')
                    split = split or total > len(data)
            if split:
                if start == end:
                    raise OracleProviderFailure('FINNHUB_SINGLE_DAY_SATURATED')
                middle = start + timedelta(days=(end-start).days//2)
                stack.extend(((middle+timedelta(days=1), end), (start, middle)))
                continue
            rows.extend(data)
        except OracleProviderFailure:
            if receipt_index + 1 != len(receipts):
                raise OracleProvenanceError('ORACLE_RECEIPTS_AFTER_FAILURE') from None
            raise
    if stack:
        if receipts and len(receipts) == snapshot['request_limits']['finnhub']:
            raise OracleProviderFailure('FINNHUB_REQUEST_BUDGET_EXHAUSTED')
        raise OracleProvenanceError('ORACLE_FINNHUB_MISSING_RECEIPTS')
    transactions = []
    for row in rows:
        if 'symbol' in row and row['symbol'] != symbol:
            raise OracleProviderFailure('FINNHUB_ROW_IDENTITY_MISMATCH')
        transaction = FinnhubClient._normalize_transaction(row)
        if transaction is None:
            raise OracleProviderFailure('DIRECT_INSIDER_NORMALIZATION_LOSS')
        transactions.append(transaction)
    return transactions, bool(rows)


def _eodhd_transactions(snapshot: dict[str, Any], cutoff: datetime, *, require_metadata: bool = False) -> list[dict[str, Any]]:
    symbol = snapshot['symbol']
    receipts = snapshot.get('eodhd_receipts', [])
    identity = snapshot.get('eodhd_identity_receipt')
    recognized = False
    if identity:
        body = _integrity(identity, cutoff=None)
        path_symbol = symbol if '.' in symbol else symbol + '.US'
        if (identity['provider'] != 'eodhd' or identity['path'] != '/api/v1.1/fundamentals/' + path_symbol
                or identity['parameters'] != {} or identity['status'] != 200 or identity['diagnostic'] is not None):
            raise OracleProvenanceError('ORACLE_EODHD_IDENTITY_PROVENANCE_INVALID')
        recognized = _strict_json(body).get('General', {}).get('Code') == symbol
    offset = 0
    ended = False
    transactions = []
    declared_total: int | None = None
    filing_ids: set[str] = set()
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
        if require_metadata:
            meta = payload.get('meta')
            if not isinstance(meta, dict) or not isinstance(meta.get('page'), dict):
                raise ValueError('ORACLE_EODHD_TOTAL_METADATA_UNKNOWN')
            page = meta['page']
            if (type(page.get('offset')) is not int or page['offset'] != offset
                    or type(page.get('limit')) is not int or page['limit'] != 100):
                raise ValueError('ORACLE_EODHD_PAGE_METADATA_INCONSISTENT')
            count = meta.get('total')
            if type(count) is not int or count < 0 or (declared_total is not None and count != declared_total):
                raise ValueError('ORACLE_EODHD_TOTAL_METADATA_INCONSISTENT')
            declared_total = count
        for filing in filings:
            if not isinstance(filing, dict):
                raise ValueError('ORACLE_EODHD_FILING_UNKNOWN')
            if require_metadata:
                identifier = filing.get('accession_number')
                if not isinstance(identifier, str) or not identifier.strip():
                    raise ValueError('ORACLE_EODHD_FILING_ID_UNKNOWN')
                if identifier in filing_ids:
                    raise ValueError('ORACLE_EODHD_DUPLICATE_FILING')
                filing_ids.add(identifier)
            if 'symbol' in filing:
                if filing['symbol'] != symbol:
                    raise ValueError('ORACLE_EODHD_IDENTITY_UNKNOWN')
                recognized = True
            filed_at = _day(filing['filed_at']).isoformat()
            if not isinstance(filing.get('non_derivative'), list):
                raise ValueError('ORACLE_EODHD_ROWS_UNKNOWN')
            for row in filing['non_derivative']:
                if not isinstance(row, dict):
                    raise ValueError('ORACLE_EODHD_ROW_UNKNOWN')
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
    if declared_total is not None and offset != declared_total:
        raise ValueError('ORACLE_EODHD_TOTAL_COVERAGE_UNKNOWN')
    if not ended or not recognized:
        raise ValueError('ORACLE_EODHD_COVERAGE_UNKNOWN')
    return transactions


def independent_direct_events(snapshot: dict[str, Any], *, received_at: datetime | None = None,
                              computed_at: datetime | None = None) -> dict[str, Any]:
    """Return original IR events or an explicit unknown-coverage diagnostic.

    This helper is an arithmetic oracle, not a second authorizing coverage gate.
    Even zero events remain separate from unknown/incomplete provider evidence.
    """
    cutoff = datetime.fromisoformat(snapshot['query_cutoff_at'])
    if (snapshot.get('schema') != 'DIRECT_INSIDER_RC4BIS_V1' or snapshot.get('market') != 'US'
            or cutoff.tzinfo is None or cutoff.utcoffset() is None):
        raise ValueError('ORACLE_DIRECT_SNAPSHOT_INVALID')
    opted_in = (re.fullmatch(r'[0-9a-f]{64}', FALLBACK_CONTRACT_SHA256) is not None
                and snapshot.get('fallback_contract_sha256') == FALLBACK_CONTRACT_SHA256)
    try:
        if opted_in and cutoff.utcoffset() != timedelta(0):
            raise OracleProvenanceError('ORACLE_CUTOFF_MUST_BE_UTC')
        if opted_in and (received_at is None or computed_at is None):
            raise OracleProvenanceError('ORACLE_FALLBACK_AVAILABILITY_UNKNOWN')
        if opted_in and snapshot.get('fable_disposition_sha256') != FABLE_DISPOSITION_SHA256:
            raise OracleProvenanceError('ORACLE_FALLBACK_DISPOSITION_UNKNOWN')
        if 'fallback_contract_sha256' in snapshot and not opted_in:
            raise OracleProvenanceError('ORACLE_FALLBACK_CONTRACT_UNKNOWN')
        limits = snapshot.get('request_limits', {})
        finn_limit, eod_limit = limits.get('finnhub'), limits.get('eodhd')
        if (type(finn_limit) is not int or not 1 <= finn_limit <= 512
                or type(eod_limit) is not int or not 1 <= eod_limit <= 100
                or limits.get('total') != finn_limit + eod_limit
                or not isinstance(snapshot.get('finnhub_receipts'), list)
                or not isinstance(snapshot.get('eodhd_receipts'), list)
                or not 1 <= len(snapshot['finnhub_receipts']) <= finn_limit
                or len(snapshot['eodhd_receipts']) > eod_limit):
            raise OracleProvenanceError('ORACLE_DIRECT_BUDGET_INVALID')
        all_receipts = snapshot['finnhub_receipts'] + snapshot['eodhd_receipts']
        if snapshot.get('eodhd_identity_receipt'):
            all_receipts.append(snapshot['eodhd_identity_receipt'])
        for receipt in all_receipts:
            # Check every supplied receipt's integrity before considering a
            # failure fallback; a corrupted later receipt cannot be hidden by
            # an earlier provider failure.
            _integrity(receipt, cutoff=None)
            if received_at is not None and datetime.fromisoformat(receipt['received_at']) > received_at:
                raise OracleProvenanceError('ORACLE_DIRECT_CLOCK_INVALID')
        if (received_at is not None and computed_at is not None
                and not cutoff <= received_at <= computed_at):
            raise OracleProvenanceError('ORACLE_DIRECT_CLOCK_INVALID')
        failure = None
        try:
            transactions, has_rows = _finnhub_transactions(snapshot, cutoff)
        except OracleProviderFailure as error:
            if not opted_in:
                raise
            failure = str(error)
            transactions, has_rows = [], False
        if has_rows:
            if snapshot.get('eodhd_receipts'):
                raise OracleProvenanceError('ORACLE_PROVIDERS_MUST_NOT_UNION')
            provider = 'finnhub'
            original = InvestorRelationsService._finnhub_insider_events
        else:
            transactions = _eodhd_transactions(snapshot, cutoff, require_metadata=opted_in)
            provider = 'eodhd'
            original = InvestorRelationsService._eodhd_insider_events
        if opted_in:
            selection = snapshot.get('provider_selection')
            if (not isinstance(selection, dict) or selection.get('selected') != provider
                    or not isinstance(selection.get('reason'), str)
                    or not re.fullmatch(r'[A-Z][A-Z0-9_]*', selection['reason'])
                    or (failure is None and selection['reason'] != ('FINNHUB_NONEMPTY' if has_rows else 'FINNHUB_EMPTY'))
                    or (failure is not None and selection['reason'] != failure)):
                raise OracleProvenanceError('ORACLE_PROVIDER_SELECTION_INVALID')
    except (ValueError, KeyError, TypeError, IndexError, RecursionError):
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
    if any(event['published_at'] > cutoff for event in events):
        return {'events': [], 'complete': False, 'provider': None, 'diagnostic': 'ORACLE_DIRECT_FUTURE_RECORD'}
    # The source IR helper floors the lookback to a date; the origin DB query
    # then applies its factual datetime cutoff. Preserve that second boundary.
    events = [event for event in events if cutoff-timedelta(days=180) <= event['published_at'] <= cutoff]
    result = {'events': events, 'complete': True, 'provider': provider, 'diagnostic': None}
    if opted_in:
        result['fallback_contract_sha256'] = FALLBACK_CONTRACT_SHA256
        result['fallback_cause'] = failure
    return result
