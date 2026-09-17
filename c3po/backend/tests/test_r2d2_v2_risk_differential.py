from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from app.r2d2_v2_risk_acquisition import SourceReceipt, SourceRequest
from app.r2d2_v2_risk_differential import (
    ORIGIN_PINS, ORIGIN_REVISION, PREREGISTERED_LIST, PREREGISTERED_RECEIPT,
    compare_contemporary_sample, independent_oracle, verify_oracle_sources,
)
from test_r2d2_v2_risk_bundle import NOW, arguments


@pytest.fixture(scope='module')
def sources():
    # Exact committed bytes; independent of shallow CI checkout history.
    root = Path(__file__).resolve().parents[2] / 'docs/r2d2-risk-source/origin'
    declared = {name: digest for digest, name in
                (line.split('  ', 1) for line in (root / 'ORIGIN_FILES.sha256').read_text().splitlines())}
    assert declared == ORIGIN_PINS
    sources = {path: (root / path).read_bytes() for path in ORIGIN_PINS}
    assert all(hashlib.sha256(body).hexdigest() == ORIGIN_PINS[path] for path, body in sources.items())
    return sources



def case(count=10, *, null=False):
    bundles = {}
    for index in range(count):
        symbol = f'SYNTH{index}'
        args = arguments()
        args['symbol'] = symbol
        for key in ('fundamentals', 'grades', 'institutional'):
            old = args[key]
            body = old.body.replace(b'SYNTH', symbol.encode())
            if null and key == 'fundamentals':
                data = json.loads(body)
                data['Technicals']['Beta'] = 0
                body = json.dumps(data).encode()
            params = dict(old.request.parameters)
            if 'symbol' in params:
                params['symbol'] = symbol
            args[key] = SourceReceipt(SourceRequest(old.request.provider, old.request.path.replace('SYNTH', symbol), params),
                                      old.started_at, old.received_at, old.status, body,
                                      hashlib.sha256(body).hexdigest(), None)
        for key in ('insider_snapshot', 'official_snapshot'):
            old = args[key]
            args[key] = replace(old, body=old.body.replace(b'SYNTH', symbol.encode()))
        bundles[symbol] = args
    sample = {'schema': 'RISK_DIFFERENTIAL_SAMPLE_V1', 'namespace': 'R2D2-V2-DIAG-ENSAIO-2026-09-14',
              'session_date': '2026-09-14', 'list_sha256': PREREGISTERED_LIST,
              'receipt_sha256': PREREGISTERED_RECEIPT, 'symbols': list(bundles),
              'selected_at': (NOW-timedelta(seconds=10)).isoformat(), 'source_envelope_sha256': '0' * 64,
              'fixture_only': True}
    raw = json.dumps(sample).encode()
    return dict(sample_bytes=raw, sample_sha256=hashlib.sha256(raw).hexdigest(), bundles=bundles)


def test_origin_and_oracle_pins_separate_and_methods_identical(sources):
    result = verify_oracle_sources(sources)
    assert result['origin_sha256']['app/one_pager.py'] != result['runtime_sha256']['app/one_pager.py']
    assert 'save_ir_events' in result['origin_methods_ast_identical']['app/database.py']


def test_synthetic_ten_exact_ready_is_nonvacuous_math_pass_not_real_capture(sources):
    result = compare_contemporary_sample(**case(), origin_sources=sources)
    assert result['aggregate']['status'] == 'PASS'
    assert result['aggregate']['counts']['READY_EXACT'] == 10
    assert result['aggregate']['capture_provenance_independently_verified'] is False
    assert result['aggregate']['historical_proof'] is False
    assert result['aggregate']['production_authorized'] is False
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('count,null', [(0, False), (9, False), (20, True)])
def test_no_vacuous_success(sources, count, null):
    data = case(count, null=null)
    if not count:
        with pytest.raises(ValueError):
            compare_contemporary_sample(**data, origin_sources=sources)
    else:
        result = compare_contemporary_sample(**data, origin_sources=sources)
        assert result['aggregate']['status'] == 'INCONCLUSIVE'
        if null:
            assert result['aggregate']['counts']['COMPLETED_NULL'] == 20
            assert result['aggregate']['arithmetic_gate_rev2']['status'] == 'PASS'
            assert result['aggregate']['arithmetic_gate_rev2']['exact'] == 20
            assert result['aggregate']['arithmetic_gate_rev2']['coverage_authorization'] is False
            assert all(v['legacy_oracle']['risk_score'] is not None for v in result['comparisons'].values())


def test_price_control_does_not_change_non_fx_risk():
    args = arguments()
    assert independent_oracle(args, control_price=.01)['risk_score'] == independent_oracle(args, control_price=10000)['risk_score']


def test_duplicate_events_seeded_through_actual_save_ir_events():
    args = arguments()
    snapshot = args['insider_snapshot'].payload()
    event = {'source_code': 'sec', 'external_id': 'same-record', 'symbol': 'SYNTH', 'market': 'US',
             'event_type': 'Insider Transaction', 'published_at': NOW.isoformat(),
             'raw_metadata': {'is_purchase': True}, 'valuation_relevant': False}
    snapshot['events'] = [event, event]
    args['insider_snapshot'] = replace(args['insider_snapshot'], body=json.dumps(snapshot).encode())
    result = independent_oracle(args)
    assert result['insider_activity'] == {'buy_count': 1, 'sell_count': 0, 'total_count': 1}


def test_order_and_source_bytes_are_pinned(sources):
    data = case()
    data['bundles'] = dict(reversed(list(data['bundles'].items())))
    with pytest.raises(ValueError, match='SAMPLE_BINDING'):
        compare_contemporary_sample(**data, origin_sources=sources)
    changed = {**sources, 'app/one_pager.py': b'changed'}
    with pytest.raises(ValueError, match='ORIGIN_SOURCE_HASH'):
        compare_contemporary_sample(**case(), origin_sources=changed)


def test_ready_mismatch_fails_gate(sources, monkeypatch):
    import app.r2d2_v2_risk_differential as harness
    original = harness.independent_oracle
    def wrong(args):
        result = original(args)
        result['risk_score'] += 1
        return result
    monkeypatch.setattr(harness, 'independent_oracle', wrong)
    report = compare_contemporary_sample(**case(), origin_sources=sources)
    assert report['aggregate']['status'] == 'NO_GO'
    assert report['aggregate']['counts']['READY_MISMATCH'] == 10


def test_unclassified_exception_never_echoes_sensitive_message(sources, monkeypatch):
    import app.r2d2_v2_risk_differential as harness
    def broken(_):
        raise RuntimeError('apikey=secret')
    monkeypatch.setattr(harness, 'independent_oracle', broken)
    report = compare_contemporary_sample(**case(), origin_sources=sources)
    assert report['aggregate']['status'] == 'NO_GO'
    assert report['aggregate']['counts']['UNCLASSIFIED_EXCEPTION'] == 10
    assert 'secret' not in json.dumps(report)


def test_null_mismatch_fails_arithmetic_gate_without_claiming_readiness(sources, monkeypatch):
    import app.r2d2_v2_risk_differential as harness
    original = harness.independent_oracle
    def wrong(args):
        value = original(args)
        value['risk_score'] += 1
        return value
    monkeypatch.setattr(harness, 'independent_oracle', wrong)
    report = compare_contemporary_sample(**case(20, null=True), origin_sources=sources)
    assert report['aggregate']['arithmetic_gate_rev2']['status'] == 'NO_GO'
    assert report['aggregate']['arithmetic_gate_rev2']['mismatches'] == 20
    assert report['aggregate']['counts']['READY'] == 0


def direct_snapshot(finnhub_rows, *, eodhd_rows=None, tree=False):
    import base64
    from datetime import timedelta
    cutoff = NOW
    start = (cutoff-timedelta(days=180)).date()
    end = cutoff.date()
    def recorded(provider, path, params, body):
        raw = json.dumps(body).encode()
        return {'provider': provider, 'path': path, 'parameters': params,
                'started_at': cutoff.isoformat(), 'received_at': (cutoff+timedelta(seconds=1)).isoformat(),
                'status': 200, 'diagnostic': None, 'body_b64': base64.b64encode(raw).decode(),
                'payload_sha256': hashlib.sha256(raw).hexdigest()}
    def finnhub(a, b, rows):
        return recorded('finnhub', '/api/v1/stock/insider-transactions',
                        {'symbol': 'SYNTH', 'from': a.isoformat(), 'to': b.isoformat()}, {'symbol': 'SYNTH', 'data': rows})
    if tree:
        middle = start+timedelta(days=(end-start).days//2)
        parent = [{'name': 'Parent not counted', 'transactionCode': 'P', 'transactionDate': '2026-09-01'}] * 100
        receipts = [finnhub(start, end, parent), finnhub(start, middle, finnhub_rows[:1]),
                    finnhub(middle+timedelta(days=1), end, finnhub_rows[1:])]
    else:
        receipts = [finnhub(start, end, finnhub_rows)]
    fallback = []
    if eodhd_rows is not None:
        data = [] if not eodhd_rows else [{'symbol': 'SYNTH', 'filed_at': '2026-09-01', 'non_derivative': eodhd_rows}]
        fallback = [recorded('eodhd', '/api/sec-filings/SYNTH/form4', {'page[offset]': 0, 'page[limit]': 100},
                             {'data': data, 'links': {'next': None}})]
    identity = recorded('eodhd', '/api/v1.1/fundamentals/SYNTH.US', {}, {'General': {'Code': 'SYNTH'}})
    return {'schema': 'DIRECT_INSIDER_RC4BIS_V1', 'symbol': 'SYNTH', 'market': 'US',
            'query_cutoff_at': cutoff.isoformat(), 'finnhub_receipts': receipts,
            'eodhd_receipts': fallback, 'eodhd_identity_receipt': identity}


def direct_oracle(snapshot):
    from datetime import timedelta
    from app.r2d2_v2_risk_bundle import PrivateSnapshot
    args = arguments()
    args['insider_snapshot'] = PrivateSnapshot(json.dumps(snapshot).encode(), NOW+timedelta(seconds=1), 'DIRECT')
    args.update(computed_at=NOW+timedelta(seconds=2), available_at=NOW+timedelta(seconds=2), decision_at=NOW+timedelta(seconds=2))
    return independent_oracle(args)


def test_direct_finnhub_manual_counts_duplicate_identity_and_window():
    rows = [
        {'name': 'Same Person', 'transactionCode': 'P', 'transactionDate': '2026-09-01'},
        {'name': 'Same Person', 'transactionCode': 'P', 'transactionDate': '2026-09-01'},
        {'name': 'Seller', 'transactionCode': 'S', 'transactionDate': '2026-09-02'},
        {'name': 'Award', 'transactionCode': 'A', 'transactionDate': '2026-09-02'},
        {'name': 'Too old', 'transactionCode': 'P', 'transactionDate': '2026-01-01'},
    ]
    result = direct_oracle(direct_snapshot(rows))
    assert result['insider_activity'] == {'buy_count': 1, 'sell_count': 1, 'total_count': 2}
    assert result['direct_insider'] == {'complete': True, 'provider': 'finnhub', 'diagnostic': None}


def test_direct_parent_at_cap_excluded_and_children_counted():
    rows = [{'name': 'Buyer', 'transactionCode': 'P', 'transactionDate': '2026-04-01'},
            {'name': 'Seller', 'transactionCode': 'S', 'transactionDate': '2026-09-01'}]
    result = direct_oracle(direct_snapshot(rows, tree=True))
    assert result['insider_activity'] == {'buy_count': 1, 'sell_count': 1, 'total_count': 2}


def test_direct_empty_finnhub_uses_original_eodhd_normalizer_only():
    rows = [{'reporting_owner_name': 'Buyer', 'transaction_code': 'P', 'transaction_date': '2026-09-01', 'shares_amount': 10},
            {'reporting_owner_name': 'Seller', 'transaction_code': 'S', 'transaction_date': '2026-09-01', 'shares_amount': 20}]
    result = direct_oracle(direct_snapshot([], eodhd_rows=rows))
    assert result['insider_activity'] == {'buy_count': 1, 'sell_count': 1, 'total_count': 2}
    assert result['direct_insider']['provider'] == 'eodhd'


def test_direct_providers_never_sum():
    result = direct_oracle(direct_snapshot(
        [{'name': 'Buyer', 'transactionCode': 'P', 'transactionDate': '2026-09-01'}],
        eodhd_rows=[{'reporting_owner_name': 'Seller', 'transaction_code': 'S', 'transaction_date': '2026-09-01'}]))
    assert result['insider_activity'] is None
    assert result['direct_insider']['complete'] is False


def test_direct_empty_verified_both_distinct_from_missing_fallback():
    verified = direct_oracle(direct_snapshot([], eodhd_rows=[]))
    unknown = direct_oracle(direct_snapshot([]))
    assert verified['insider_activity'] is None  # original DB returns no bucket for verified zero
    assert verified['direct_insider']['complete'] is True
    assert unknown['insider_activity'] is None
    assert unknown['direct_insider']['complete'] is False


def test_direct_clock_injection_does_not_mutate_original_module_globals():
    import app.investor_relations as ir
    original_datetime, original_days = ir.datetime, ir.FINNHUB_INSIDER_LOOKBACK_DAYS
    direct_oracle(direct_snapshot([], eodhd_rows=[]))
    assert ir.datetime is original_datetime
    assert ir.FINNHUB_INSIDER_LOOKBACK_DAYS == original_days == 90
