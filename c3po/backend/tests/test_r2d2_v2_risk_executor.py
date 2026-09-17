from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.r2d2_v2_risk_executor import execute_private_risk
from test_r2d2_v2_risk_bundle import NOW, arguments


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def fixture(tmp_path: Path, *, null=False):
    root = tmp_path / 'input'
    root.mkdir(mode=0o700)
    def put(name, body):
        path = root / name
        path.write_bytes(body)
        path.chmod(0o600)
        return {'path': name, 'sha256': hashlib.sha256(body).hexdigest()}
    args = arguments()
    sources = {}
    for key in ('fundamentals', 'grades', 'institutional'):
        source = args[key]
        body = source.body
        if null and key == 'fundamentals':
            data = json.loads(body)
            data['Technicals']['Beta'] = 0
            body = encode(data)
        body_ref = put(key + '.body', body)
        doc = {'request': {'provider': source.request.provider, 'path': source.request.path,
                           'parameters': dict(source.request.parameters)},
               'started_at': source.started_at.isoformat(), 'received_at': source.received_at.isoformat(),
               'status': source.status, 'diagnostic': source.diagnostic, 'payload_sha256': body_ref['sha256']}
        sources[key] = {'body': body_ref, 'receipt': put(key + '.receipt', encode(doc))}
    for key in ('insider', 'official'):
        snapshot = args[key + '_snapshot']
        sources[key] = {'body': put(key + '.snapshot', snapshot.body),
                        'source_id': snapshot.source_id, 'received_at': snapshot.received_at.isoformat()}
    clocks = put('assessment.json', encode({'symbol': 'SYNTH', 'computed_at': NOW.isoformat(),
                                          'available_at': NOW.isoformat(), 'factual_assessment': True}))
    manifest = {'schema': 'V2_RISK_REPLAY_MANIFEST_V1', 'namespace': 'R2D2-V2-SHADOW-2026-09-18',
                'session_date': '2026-09-18', 'mode': 'OFFLINE_REPLAY', 'phase_pending': 0,
                'decision_at': NOW.isoformat(), 'admission': put('admission.json', encode({'fixture': True})),
                'symbols': [{'symbol': 'SYNTH', 'market': 'US', 'sources': sources, 'assessment_clock': clocks}]}
    def save():
        ref = put('manifest.json', encode(manifest))
        return dict(manifest_path=root / 'manifest.json', manifest_sha256=ref['sha256'],
                    expected_namespace='R2D2-V2-SHADOW-2026-09-18', expected_session_date=date(2026, 9, 18),
                    output_path=tmp_path / 'output', execution_at=NOW + timedelta(hours=1))
    return manifest, root, save


def test_offline_replay_outputs_port_contract_preserving_clocks_and_hashes(tmp_path):
    _, _, save = fixture(tmp_path)
    result = execute_private_risk(**save())
    path = tmp_path / 'output'
    assert result['counts'] == {'READY': 1, 'COMPLETED_NULL': 0}
    assert result['historical_provenance_independently_verified'] is False
    assert result['authorization_granted'] is False
    risk = json.loads((path / 'risk.json').read_bytes())
    assert risk['schema'] == 'V2_RISK_COMPONENTS_V1'
    assert risk['symbols']['SYNTH']['source_at'] == NOW.isoformat()
    assert result['execution_at'] != risk['symbols']['SYNTH']['source_at']
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    manifest = json.loads((path / 'MANIFEST.json').read_bytes())
    for name, sha in manifest['files'].items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == sha
        assert stat.S_IMODE((path / name).stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        execute_private_risk(**save())


def test_completed_null_preserved_never_claims_ready(tmp_path):
    _, _, save = fixture(tmp_path, null=True)
    result = execute_private_risk(**save())
    assert result['counts'] == {'READY': 0, 'COMPLETED_NULL': 1}
    assert json.loads((tmp_path / 'output' / 'risk.json').read_bytes())['symbols']['SYNTH']['value'] is None


@pytest.mark.parametrize('mutation', ['pending', 'duplicate', 'too_many', 'date', 'namespace', 'mode', 'future'])
def test_binding_and_inventory_refusals_write_no_output(tmp_path, mutation):
    manifest, _, save = fixture(tmp_path)
    if mutation == 'pending': manifest['phase_pending'] = 1
    if mutation == 'duplicate': manifest['symbols'] *= 2
    if mutation == 'too_many': manifest['symbols'] *= 551
    if mutation == 'date': manifest['session_date'] = '2026-09-19'
    if mutation == 'namespace': manifest['namespace'] = 'R2D2-V2-SHADOW-other'
    if mutation == 'mode': manifest['mode'] = 'LIVE'
    if mutation == 'future': manifest['decision_at'] = (NOW + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        execute_private_risk(**save())
    assert not (tmp_path / 'output').exists()


@pytest.mark.parametrize('mutation', ['missing', 'hash', 'permission', 'symlink', 'missing_source', 'traversal'])
def test_missing_or_changed_private_evidence_never_completes(tmp_path, mutation):
    manifest, root, save = fixture(tmp_path)
    args = save()
    file = root / 'fundamentals.body'
    if mutation == 'missing': file.unlink()
    if mutation == 'hash': file.write_bytes(b'{}')
    if mutation == 'permission': file.chmod(0o644)
    if mutation == 'symlink':
        other = root / 'other'
        file.rename(other)
        file.symlink_to(other)
    if mutation == 'missing_source':
        del manifest['symbols'][0]['sources']['insider']
        args = save()
    if mutation == 'traversal':
        manifest['symbols'][0]['sources']['fundamentals']['body']['path'] = '../fundamentals.body'
        args = save()
    with pytest.raises((ValueError, OSError, KeyError)):
        execute_private_risk(**args)
    assert not (tmp_path / 'output').exists()


def test_clock_manifest_claim_missing_is_not_fabricated(tmp_path):
    manifest, root, save = fixture(tmp_path)
    body = encode({'symbol': 'SYNTH', 'computed_at': NOW.isoformat(), 'available_at': NOW.isoformat()})
    (root / 'assessment.json').write_bytes(body)
    manifest['symbols'][0]['assessment_clock']['sha256'] = hashlib.sha256(body).hexdigest()
    with pytest.raises(ValueError, match='ASSESSMENT_CLOCK_BINDING_INVALID'):
        execute_private_risk(**save())


def test_input_root_must_be_private(tmp_path):
    _, root, save = fixture(tmp_path)
    args = save()
    root.chmod(0o755)
    with pytest.raises(ValueError, match='INPUT_DIRECTORY_PERMISSIONS'):
        execute_private_risk(**args)


def test_interrupted_publication_has_no_success_manifest(tmp_path, monkeypatch):
    _, _, save = fixture(tmp_path)
    def interrupt(_):
        raise KeyboardInterrupt()
    monkeypatch.setattr(os, 'fsync', interrupt)
    with pytest.raises(KeyboardInterrupt):
        execute_private_risk(**save())
    assert not (tmp_path / 'output' / 'MANIFEST.json').exists()


def test_b3_supported_as_explicit_completed_null_without_http_sources(tmp_path):
    manifest, _, save = fixture(tmp_path)
    manifest['symbols'][0]['market'] = 'B3'
    del manifest['symbols'][0]['sources']
    result = execute_private_risk(**save())
    assert result['counts'] == {'READY': 0, 'COMPLETED_NULL': 1}
    assert result['readiness'] == 'NO_READY_SYMBOLS'
    assert result['predecessor_chain_independently_verified'] is False
    assert result['certification_granted'] is False
