from __future__ import annotations

import hashlib
import json
import subprocess
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
    # Trusted local pinned git objects only; no fetch, credentials or provider.
    repo = Path(__file__).resolve().parents[3]
    return {path: subprocess.check_output(['git', 'show', ORIGIN_REVISION + ':c3po/backend/' + path], cwd=repo)
            for path in ORIGIN_PINS}


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
