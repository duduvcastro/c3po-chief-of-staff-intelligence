"""Tests of bind_once.py: the flows on scratch copies with a fake transport, determinism, the separation of REAL and
REHEARSAL sets, and every refusal code of the binder (the last test compares the codes in the source with the codes
exercised here). Clocks are injected: the fixed instant is inside the date set of every family, so the tests do not
depend on the day they are run. No host, no key, no network."""
import ast
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import types

import pytest

import helpers as h
from helpers import NOW, PRECHECK, PROVISION, W1, refused

b = h.b
ANSWER = b.REHEARSAL_ANSWER
MIN = timedelta(minutes=1)
SEC = timedelta(seconds=1)


def w1_set(base, families, name=None, **changes):
    reference = h.rehearsal_reference(base, name='rehearsal-transport' + (name or ''))
    return h.bind(base, families['w1'], W1, h.w1_parameters(base, **changes), reference, name=name)


def w1_prepared(base, families, **changes):
    reference = h.rehearsal_reference(base)
    return b.prepare(families['w1'], W1, h.w1_parameters(base, **changes), reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW), reference


def real_set(base, families, name='bound'):
    reference = h.executed_reference(base, families['w1'])
    return h.bind(base, families['w1'], W1, h.w1_parameters(base), reference, mode=b.REAL, name=name) + (reference,)


def edit_json(path, **changes):
    value = json.loads(Path(path).read_bytes())
    value.update(changes)
    return value


def modes(directory):
    return {str(path.relative_to(directory)): stat.S_IMODE(path.lstat().st_mode) for path in sorted(Path(directory).rglob('*'))}


# ---------------------------------------------------------------- small units
def test_utc_parsing_and_brt_rendering():
    assert b.parse_utc('2026-10-03T13:00:00Z') == NOW == b.parse_utc('2026-10-03T13:00:00+00:00') and b.zulu(NOW) == '2026-10-03T13:00:00Z'
    for bad in ('2026-10-03T13:00:00', '2026-10-03T10:00:00-03:00', '2026-10-03T13:00:00.5Z', '2026-13-03T13:00:00Z', '2026-10-03 13:00:00Z', None, 5):
        with refused('TIME_NOT_UTC_SECONDS'):
            b.parse_utc(bad)
    # 21:00 BRT is 00:00 UTC: a UTC day runs from 21:00 of the previous local day to 20:59:59
    assert b.brt(datetime(2026, 10, 3, 0, 0, 0, tzinfo=timezone.utc)) == 'sex 02/10/2026 21:00:00 BRT'
    assert b.brt(datetime(2026, 10, 3, 23, 59, 59, tzinfo=timezone.utc)) == 'sáb 03/10/2026 20:59:59 BRT'
    assert b.brt(datetime(2026, 10, 5, 8, 27, 0, tzinfo=timezone.utc)) == 'seg 05/10/2026 05:27:00 BRT'
    assert b.canonical({'b': 1, 'a': [2, None]}) == b'{"a":[2,null],"b":1}' and b.is_hash('a' * 64) and not b.is_hash('0' * 64) and not b.is_hash('A' * 64)


def test_put_and_directories_are_exclusive_private_and_read_back(base, monkeypatch):
    assert b.put(base, 'one', b'x') == b.sha(b'x') and stat.S_IMODE((base / 'one').stat().st_mode) == 0o600
    with refused('ALREADY_EXISTS_NEVER_OVERWRITTEN'):
        b.put(base, 'one', b'y')
    assert (base / 'one').read_bytes() == b'x'
    with refused('EMPTY_WRITE'):
        b.put(base, 'two', b'')
    b.make_directory(base / 'd')
    assert stat.S_IMODE((base / 'd').stat().st_mode) == 0o700
    with refused('ALREADY_EXISTS_NEVER_OVERWRITTEN'):
        b.make_directory(base / 'd')
    (base / 'link').symlink_to(base / 'one')
    with refused('ALREADY_EXISTS_NEVER_OVERWRITTEN'):           # a link is never followed nor replaced
        b.put(base, 'link', b'z')
    real = b.read_file
    monkeypatch.setattr(b, 'read_file', lambda *args, **kwargs: b'other')
    with refused('WRITTEN_FILE_READ_BACK'):
        b.put(base, 'three', b'x')
    monkeypatch.setattr(b, 'read_file', real)
    os.chmod(str(base / 'd'), 0o755)
    with refused('CLAIM_ROOT_NOT_PRIVATE'):
        b.claim_identity(base / 'd')


def test_binder_identity_needs_its_registry_of_seals(base, monkeypatch):
    identity, seals = b.binder_identity()
    assert identity['binder_sha256'] == b.sha(Path(b.__file__).read_bytes()) and len(seals) >= 2
    monkeypatch.setattr(b, '__file__', str(base / 'bind_once.py'))
    with refused('ACCEPTED_SEALS_MISSING'):
        b.binder_identity()
    for bad in (b'not json', b'{"schema":"X","seals":[]}', json.dumps({'schema': b.SEALS_SCHEMA, 'seals': [{'family': 'F', 'revision': '1', 'sha256sums_sha256': 'x'}]}).encode(),
                b'{"schema":"BIND_ONCE_ACCEPTED_SEALS_V1","schema":"BIND_ONCE_ACCEPTED_SEALS_V1","seals":[]}'):
        (base / 'ACCEPTED_SEALS.json').write_bytes(bad)
        with refused('ACCEPTED_SEALS_INVALID'):
            b.binder_identity()
    (base / 'ACCEPTED_SEALS.json').write_bytes(json.dumps({'schema': b.SEALS_SCHEMA, 'seals': []}).encode())
    with refused('BINDER_UNREADABLE'):
        b.binder_identity()


def test_every_command_refuses_to_run_as_root(base, families, monkeypatch):
    out, prepared, signed = w1_set(base, families)
    monkeypatch.setattr(b.os, 'geteuid', lambda: 0)
    for call in (lambda: b.prepare(families['w1'], W1, base / 'PARAMETERS.json', base / 'x', base / 'rehearsal-other', b.REHEARSAL),
                 lambda: b.sign(out, 'a' * 64, b.zulu(NOW), ANSWER), lambda: b.check(out), lambda: b.publish_proof(out, 'x', b.zulu(NOW)),
                 lambda: b.status(out), lambda: b.rehearsal_reference(base / 'rehearsal-x'), lambda: b.run_payload_locally(b'x')):
        with refused('BIND_AS_ROOT'):
            call()
    assert not (base / 'rehearsal-other').exists() and not (base / 'rehearsal-x').exists()


# ---------------------------------------------------------------- the W1 flow, end to end, on a scratch copy
def test_w1_flow_prepare_sign_check_dispatcher_proof_harness_resume_status(base, families, w1_harness):
    prepared, reference = w1_prepared(base, families, purpose_pt='Ensaio do fluxo completo em cópia de rascunho.')
    out, sheet = Path(prepared['bound']), prepared['sheet']
    # the sheet: every hash the owner signs over, the window in BRT, the question in Portuguese
    assert prepared['status'] == 'PREPARED_AWAITING_OWNER_SIGNATURE' and sheet['mode'] == 'REHEARSAL' and sheet['profile'] == 'collection'
    assert prepared['prepare_json_sha256'] == b.sha((out / 'PREPARE.json').read_bytes())
    assert sheet['family'] == {'family': 'W1PREFLIGHT01', 'revision': '3', 'sha256sums_sha256': b.sha((families['w1'] / 'SHA256SUMS').read_bytes())}
    assert sheet['request_sha256'] == b.sha((out / 'REQUEST.BOUND.json').read_bytes()) and sheet['source_sha256'] == b.sha((families['w1'] / 'w1_preflight_readonly.py').read_bytes())
    assert sheet['contract_sha256'] == b.sha((families['w1'] / 'CONTRACT.txt').read_bytes()) and sheet['writes_allowed'] is False
    assert sheet['window'] == {'date_utc': '2026-10-03', 'not_before': '2026-10-03T13:00:00Z', 'not_after': '2026-10-03T13:05:00Z',
                               'gate_not_before': '2026-10-03T13:00:00Z', 'gate_not_after': '2026-10-03T13:05:00Z', 'gate_span_seconds': 300,
                               'latest_start': '2026-10-03T13:03:40Z', 'watchdog_seconds': 80,
                               'brt': {'not_before': 'sáb 03/10/2026 10:00:00 BRT', 'not_after': 'sáb 03/10/2026 10:05:00 BRT',
                                       'gate_not_before': 'sáb 03/10/2026 10:00:00 BRT', 'gate_not_after': 'sáb 03/10/2026 10:05:00 BRT',
                                       'latest_start': 'sáb 03/10/2026 10:03:40 BRT'}}
    assert sheet['claim_root_identity'] == {'path': str(out / '.dispatch-root'), 'device': (out / '.dispatch-root').stat().st_dev,
                                            'inode': (out / '.dispatch-root').stat().st_ino}
    assert sheet['attempt_directory'] == str(out / '.dispatch-root' / 'attempt-once') and sheet['candidates'] == {'capacity_roots': 0, 'release_directories': 0}
    assert set(sheet['provisional_proofs'].values()) >= {'ACCEPTED', 'ACCEPTED_UP_TO_THE_CLAIM', 'GO_UNSIGNED', 'DISPATCH_WINDOW', 'WINDOW_WITH_WATCHDOG'}
    question = (out / 'OWNER_QUESTION.txt').read_text(encoding='utf-8')
    assert question == prepared['owner_question_pt'] and prepared['prepare_json_sha256'] in question and sheet['request_sha256'] in question
    assert 'ENSAIO' in question and 'sáb 03/10/2026 10:00:00 BRT até sáb 03/10/2026 10:05:00 BRT' in question and 'Finalidade: Ensaio do fluxo' in question
    assert 'Assino' not in question          # a rehearsal never asks for the owner's word
    # the request: the template plus exactly the bound members; the nine dates stay as sealed
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    template = json.loads((families['w1'] / 'REQUEST.UNBOUND.json').read_bytes())
    assert request['dates'] == template['dates'] and len(request['dates']) == 9 and request['status'] == request['collection']['status'] == 'BOUND'
    assert request['collection']['window'] == {'not_before': request['not_before'], 'expires_at': request['not_after']}
    assert request['host_binding_sha256'] == request['collection']['host_binding_sha256'] == sheet['host_binding_sha256']
    changed = {key for key in request if request[key] != template[key]}
    assert changed == {'status', 'host_binding_sha256', 'not_before', 'not_after', 'collection'}
    assert {key for key in request['collection'] if request['collection'][key] != template['collection'][key]} == {'status', 'host_binding_sha256', 'window'}
    # nothing signed exists before sign, and everything is private
    assert not list(out.glob('*AUTHORITY*')) and not (out / 'DISPATCH.BOUND.json').exists() and list((out / '.dispatch-root').iterdir()) == []
    assert all(mode == (0o700 if name in ('.dispatch-root', 'templates') else 0o600) for name, mode in modes(out).items())
    assert stat.S_IMODE(out.stat().st_mode) == 0o700

    signed = b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW + SEC), ANSWER, now=lambda: NOW + 2 * SEC)
    assert signed['status'] == 'BOUND_NOT_DISPATCHED' and signed['signed_at_utc'] == '2026-10-03T13:00:01Z'
    authority = json.loads((out / signed['authority_name']).read_bytes())
    go = json.loads((out / signed['go_name']).read_bytes())
    config = json.loads((out / 'DISPATCH.BOUND.json').read_bytes())
    assert signed['authority_name'].startswith('REHEARSAL_NOT_THE_OWNER_') and authority['owner'] == go['owner'] == config['owner'] == b.REHEARSAL_OWNER
    assert authority['owner_evidence'] == go['owner_evidence'] == {'channel': b.REHEARSAL_CHANNEL, 'owner_answer_verbatim': b.REHEARSAL_ANSWER,
                                                                 'signed_at_utc': '2026-10-03T13:00:01Z', 'prepare_sheet_sha256': prepared['prepare_json_sha256']}
    assert authority['status'] == go['status'] == 'SIGNED' and authority['decision'] == 'APPROVED' and go['action'] == 'GO'
    assert go['claim_root_identity'] == config['local_root_identity'] == sheet['claim_root_identity'] == json.loads((out / 'CLAIM_ROOT_IDENTITY.json').read_bytes())
    assert go['transport_binding'] == {key: config[key] for key in ('target', 'remote_command', 'command_sha256', 'runtime_sha256')}
    assert config['target'] == b.REHEARSAL_TARGET and config['authorization_ref'].startswith('REHEARSAL sha256:' + signed['go_sha256'])
    # the window in its six places, as non-null strings
    places = [request['not_before'], request['collection']['window']['not_before'], authority['not_before'], go['not_before'], config['not_before']]
    assert places == ['2026-10-03T13:00:00Z'] * 5 and config['latest_start'] == '2026-10-03T13:03:40Z'
    assert [request['not_after'], request['collection']['window']['expires_at'], authority['not_after'], go['not_after'], config['not_after']] == ['2026-10-03T13:05:00Z'] * 5
    # the scope sentence: what the W1 contract demands of it
    scope = go['scope']
    assert scope + '\n' == (out / 'GO_SCOPE.txt').read_text() and b.sha((out / 'GO_SCOPE.txt').read_bytes()) == sheet['go_scope_sha256']
    assert all('[decision %d] ' % number in scope for number in (1, 2, 3, 4, 5, 6, 11, 12, 13)) and '[decision 7]' not in scope
    assert scope.count('[side effect ') == len(w1_harness.p.SIDE_EFFECTS) >= 9 and 'identified by exit.json only' in scope
    assert all(effect in scope for effect in w1_harness.p.SIDE_EFFECTS) and sheet['scope_sha256'] in scope and sheet['family']['sha256sums_sha256'] in scope
    contract = ' '.join((families['w1'] / 'CONTRACT.txt').read_text().split())
    for number in (1, 2, 3, 4, 5, 6, 11, 12, 13):          # each decision is a quotation of the sealed contract, whitespace aside
        quoted = scope.split('[decision %d] ' % number)[1].split(' [decision ')[0].split(' Side effects declared')[0]
        assert ' '.join(quoted.split()) in contract, number
    # SHA256SUMS lists every file of the set
    listed = dict(reversed(line.split('  ')) for line in (out / 'SHA256SUMS').read_text().splitlines())
    assert set(listed) == {name for name, mode in modes(out).items() if mode == 0o600 and not name.startswith('.dispatch-root') and name != 'SHA256SUMS'}
    assert all(b.sha((out / name).read_bytes()) == digest for name, digest in listed.items())

    checked = b.check(out, families['w1'], now=lambda: NOW + 3 * SEC)
    assert checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['wrote_nothing'] and checked['family_seal_and_templates_rechecked']
    assert checked['proofs'] == {
        'source_accepts_at_not_before': 'ACCEPTED', 'source_accepts_at_latest_start': 'ACCEPTED', 'source_refuses_before_the_window': 'OUTSIDE_GO_WINDOW',
        'source_refuses_at_not_after': 'OUTSIDE_GO_WINDOW', 'source_refuses_this_user': 'REQUEST_OR_EXECUTOR_UNBOUND',
        'source_refuses_unsigned_authority': 'AUTHORITY_UNBOUND', 'source_refuses_unsigned_go': 'GO_UNBOUND',
        'dispatcher_accepts_at_not_before': 'ACCEPTED_UP_TO_THE_CLAIM', 'dispatcher_accepts_at_latest_start': 'ACCEPTED_UP_TO_THE_CLAIM',
        'dispatcher_refuses_before_the_window': 'DISPATCH_WINDOW', 'dispatcher_refuses_after_latest_start': 'WINDOW_WITH_WATCHDOG',
        'dispatcher_refuses_at_not_after': 'DISPATCH_WINDOW', 'dispatcher_refuses_unsigned_go': 'GO_UNSIGNED',
        'dispatcher_refuses_the_template_go': 'GO_UNSIGNED', 'dispatcher_refuses_unsigned_authority': 'AUTHORITY_UNSIGNED',
        'dispatcher_refuses_unbound_config': 'DISPATCH_UNBOUND', 'dispatcher_refuses_another_payload': 'FINAL_BUNDLE_BYTES'}
    assert checked['final_payload_run_locally_as_this_user']['code'] == 'REQUEST_OR_EXECUTOR_UNBOUND' and checked['attempt_phase'] == 'NOT_PREPARED'
    assert list((out / '.dispatch-root').iterdir()) == []          # the dry runs created nothing
    assert b.check(out, now=lambda: NOW - MIN)['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN'
    assert b.check(out, now=lambda: NOW + 4 * MIN)['verdict'] == 'VALID_BUT_PAST_LATEST_START_THE_DISPATCHER_WILL_REFUSE'
    assert b.status(out)['status'] == 'NOT_PREPARED'

    # the family's dispatcher, phase prepare: claim and intent, no transport
    with refused('ATTEMPT_NOT_AWAITING_PUBLICATION'):
        b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 5 * SEC), now=lambda: NOW + 6 * SEC)
    intent = h.dispatcher_prepare(out, NOW + 4 * SEC)
    assert intent == {'status': 'AWAITING_PUBLICATION_NO_SPAWN', 'intent_sha256': intent['intent_sha256'], 'go_sha256': signed['go_sha256'],
                      'config_sha256': signed['config_sha256'], 'retry': False}
    assert sorted(path.name for path in (out / '.dispatch-root').iterdir()) == ['.go-' + signed['go_sha256'] + '.claim', 'attempt-once']
    with pytest.raises(FileExistsError):
        h.dispatcher_prepare(out, NOW + 5 * SEC)          # single use: the claim is per GO
    assert b.status(out)['status'] == 'PREPARED_AWAITING_PUBLICATION' and b.check(out, now=lambda: NOW + 5 * SEC)['attempt_phase'] == 'PREPARED_AWAITING_PUBLICATION'
    proof = b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 5 * SEC), now=lambda: NOW + 6 * SEC)
    assert proof['intent_sha256'] == intent['intent_sha256'] and proof['published_at'] == '2026-10-03T13:00:05+00:00'
    raw = (out / 'PUBLICATION.PROOF.json').read_bytes()
    assert b.sha(raw) == proof['publication_proof_sha256'] and stat.S_IMODE((out / 'PUBLICATION.PROOF.json').stat().st_mode) == 0o600
    assert json.loads(raw) == {'schema': 'W1PREFLIGHT01_INTENT_PUBLICATION_V1', 'status': 'PUBLISHED', 'owner': b.REHEARSAL_OWNER,
                               'publication_ref': b.REHEARSAL_PUBLICATION, 'go_sha256': signed['go_sha256'], 'config_sha256': signed['config_sha256'],
                               'intent_sha256': intent['intent_sha256'], 'published_at': '2026-10-03T13:00:05+00:00'} and raw == b.canonical(json.loads(raw))
    assert proof['resume_command'][-4:] == ['--publication-proof', str(out / 'PUBLICATION.PROOF.json'), '--publication-proof-sha256', proof['publication_proof_sha256']]
    with refused('ALREADY_EXISTS_NEVER_OVERWRITTEN'):          # a proof is never replaced; a corrected one takes the next name
        b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 5 * SEC), now=lambda: NOW + 6 * SEC)
    second = b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 6 * SEC), 'PUBLICATION.PROOF.R2.json', now=lambda: NOW + 7 * SEC)
    assert second['publication_proof_sha256'] != proof['publication_proof_sha256']
    assert b.status(out)['status'] == 'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN'

    # resume against the family's own harness: the source on the emulated host, the line through the dispatcher
    line, receipt = h.w1_receipt_line(w1_harness, out)
    result = h.dispatcher_resume(out, proof, NOW + 8 * SEC, h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False}, line))
    assert result['status'] == 'KNOWN_COMPLETE' and result['go_sha256'] == signed['go_sha256'] and result['stdout_sha256'] == b.sha(line)
    with pytest.raises(FileExistsError):
        h.dispatcher_resume(out, proof, NOW + 9 * SEC, h.never)
    report = b.status(out)
    assert report['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and all(report['receipt_bindings'].values())
    assert report['observation_status'] == 'OBSERVED_COMPLETE' and report['problems'] == [] and report['go_spent'] is True
    assert report['metadata_sha256'] == receipt['metadata_sha256'] and report['stdout_sha256'] == b.sha(line) and report['size_reductions'] == []
    assert 'findings' not in report and report['findings_count'] == len(receipt['observation']['findings']) > 0
    assert b.status(out, show_findings=True)['findings'] == receipt['observation']['findings'] and set(report['section_status'].values()) == {'COMPLETE'}
    # status prints codes, counts and hashes: nothing of what the receipt observed
    printed = json.dumps(report)
    for value in ('/mnt/day-d-data', '6.8.0', '29.9.9', 'c3po-api-1', str(receipt['observation']['sections']['journal_filesystem'].get('bytes_available', 'no-such-value'))):
        assert value not in printed
    with refused('ATTEMPT_NOT_AWAITING_PUBLICATION'):
        b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 9 * SEC), 'PUBLICATION.PROOF.R3.json', now=lambda: NOW + 10 * SEC)
    assert b.check(out, now=lambda: NOW + 10 * SEC)['attempt_phase'] == 'FINISHED'

    # a copy elsewhere (the archive in the durable directory) still verifies with status, and can never be dispatched
    archive = base / 'archive' / 'rehearsal-bound'
    shutil.copytree(str(out), str(archive))
    os.chmod(str(archive.parent), 0o700)
    copied = b.status(archive)
    assert copied['verified'] is True and copied['bound_set_is_a_relocated_copy'] is True and copied['metadata_sha256'] == report['metadata_sha256']
    with refused('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED'):
        b.check(archive, now=lambda: NOW)
    with refused('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED'):
        b.publish_proof(archive, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 9 * SEC), 'PUBLICATION.PROOF.R4.json', now=lambda: NOW + 10 * SEC)


def test_status_of_partial_refused_uncertain_and_unverified_attempts(base, families, w1_harness):
    def attempt(name, transport):
        directory = base / name
        directory.mkdir()
        out, prepared, signed = w1_set(directory, families)
        return out, h.finish(out, transport(out))
    # a partial receipt: valid outcome, verified, problems listed as codes
    out, result = attempt('partial', lambda out: h.fixed_transport({'status': 'KNOWN_PARTIAL', 'retry_allowed': False},
                                                                    h.w1_receipt_line(w1_harness, out, world=w1_harness.broken_world())[0]))
    report = b.status(out)
    assert result['status'] == report['status'] == 'KNOWN_PARTIAL' and report['verified'] is True and report['observation_status'] == 'PARTIAL_OBSERVED'
    assert report['problems'] and all(b.re.fullmatch('[a-z_]+:[A-Z][A-Z0-9_]*', item) for item in report['problems']) and 'Parcial' in report['verdict_pt']
    # a remote refusal: no receipt, the GO is spent, the code of the refusal is shown
    out, result = attempt('refusal', lambda out: h.fixed_transport({'status': 'KNOWN_REFUSAL', 'retry_allowed': False},
                                                                    b'{"code":"OUTSIDE_GO_WINDOW","schema":"X","source_mutation":false,"status":"REFUSED"}\n'))
    report = b.status(out)
    assert report['status'] == 'KNOWN_REFUSAL' and report['verified'] is False and report['remote_code'] == 'OUTSIDE_GO_WINDOW' and report['go_spent'] is True

    # a transport that fails: UNCERTAIN, never repeated
    def failing(out):
        def run(payload, **kwargs):
            raise OSError('synthetic transport failure')
        return run
    out, result = attempt('uncertain', failing)
    report = b.status(out)
    assert result['status'] == report['status'] == 'UNCERTAIN' and report['code'] == 'TRANSPORT_OR_RECEIPT_REFUSED' and report['verified'] is False
    assert 'Nunca repetir' in report['verdict_pt']
    # a receipt the dispatcher accepts (request, GO and payload bound) whose other bindings do not hold: not verified
    for field in ('authority_sha256', 'host_binding_sha256'):
        out, result = attempt('wrong-' + field, lambda out: h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False},
                                                                             h.w1_receipt_line(w1_harness, out, changes={field: '9' * 64})[0]))
        report = b.status(out)
        assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is False and report['receipt_bindings'][field] is False
        assert report['receipt_bindings']['metadata_sha256'] is True and 'NÃO VERIFICADO' in report['verdict_pt']
    # a receipt whose seal is wrong, and one that is paired with the wrong transport status
    out, result = attempt('bad-seal', lambda out: h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False},
                                                                     h.w1_receipt_line(w1_harness, out)[0].replace(b'"ready":false', b'"ready":true')))
    assert b.status(out)['receipt_bindings']['metadata_sha256'] is False and b.status(out)['verified'] is False
    out, result = attempt('wrong-pairing', lambda out: h.fixed_transport({'status': 'KNOWN_PARTIAL', 'retry_allowed': False}, h.w1_receipt_line(w1_harness, out)[0]))
    assert b.status(out)['receipt_bindings']['status_pairs_with_transport_status'] is False and b.status(out)['verified'] is False
    # stderr not empty: not verified even when everything else holds
    out, result = attempt('stderr', lambda out: h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False},
                                                                   h.w1_receipt_line(w1_harness, out)[0], b'warning\n'))
    report = b.status(out)
    assert report['stderr_empty'] is False and report['verified'] is False


def test_status_refuses_an_attempt_directory_that_is_not_what_the_dispatcher_wrote(base, families, w1_harness):
    def finished(name):
        directory = base / name
        directory.mkdir()
        out, prepared, signed = w1_set(directory, families)
        h.finish(out, h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False}, h.w1_receipt_line(w1_harness, out)[0]))
        return out, out / '.dispatch-root' / 'attempt-once'
    out, attempt = finished('extra')
    (attempt / 'stray').write_bytes(b'x')
    with refused('ATTEMPT_FILE_SET'):
        b.status(out)
    for name, code in (('exit.json', 'EXIT_JSON_UNREADABLE'), ('stdout.private.json', 'STDOUT_UNREADABLE'), ('stderr.private', 'STDERR_UNREADABLE')):
        out, attempt = finished('mode-' + name)
        (attempt / name).chmod(0o644)
        with refused(code):
            b.status(out)
    out, attempt = finished('not-canonical')
    (attempt / 'exit.json').write_bytes(b.pretty(json.loads((attempt / 'exit.json').read_bytes())))
    with refused('EXIT_JSON_INVALID'):
        b.status(out)
    out, attempt = finished('not-json')
    (attempt / 'exit.json').write_bytes(b'[1]')
    with refused('EXIT_JSON_INVALID'):
        b.status(out)
    out, attempt = finished('other-go')
    (attempt / 'exit.json').write_bytes(b.canonical(edit_json(attempt / 'exit.json', go_sha256='9' * 64)))
    with refused('EXIT_JSON_DOES_NOT_BIND_THIS_SET'):
        b.status(out)
    out, attempt = finished('stdout-changed')
    (attempt / 'stdout.private.json').write_bytes((attempt / 'stdout.private.json').read_bytes() + b' ')
    with refused('EXIT_JSON_DOES_NOT_MATCH_THE_STORED_OUTPUT'):
        b.status(out)
    out, attempt = finished('not-a-receipt')
    (attempt / 'stdout.private.json').write_bytes(b'[]\n')
    (attempt / 'exit.json').write_bytes(b.canonical(edit_json(attempt / 'exit.json', stdout_sha256=b.sha(b'[]\n'))))
    with refused('RECEIPT_INVALID'):
        b.status(out)
    # a spawn marker without a result: the attempt was consumed and nothing is known
    out, attempt = finished('no-result')
    for name in ('exit.json', 'stdout.private.json', 'stderr.private'):
        (attempt / name).unlink()
    report = b.status(out)
    assert report['status'] == 'SPAWN_CLAIMED_NO_RESULT' and report['go_spent'] is True and report['verified'] is False
    (attempt / 'intent.json').unlink()
    (attempt / 'spawn.claim').unlink()
    assert b.status(out)['status'] == 'UNEXPECTED_ATTEMPT_CONTENT'
    attempt.rmdir()
    assert b.status(out)['status'] == 'CLAIMED_WITHOUT_ATTEMPT_DIRECTORY'


# ---------------------------------------------------------------- HOSTOPS core profile
def test_precheck_flow_up_to_the_dispatcher_prepare(base, families):
    reference = h.rehearsal_reference(base)
    out, prepared, signed = h.bind(base, families['hostops'], PRECHECK, h.precheck_parameters(base), reference)
    sheet = prepared['sheet']
    assert sheet['profile'] == 'core' and sheet['family']['family'] == 'HOSTOPS01' and sheet['success_criterion'] == 'PRECHECK_ALL_OBSERVED'
    assert sheet['source_name'] == 'precheck_readonly.py' and sheet['writes_allowed'] is False and sheet['window']['gate_span_seconds'] == 3000
    effects = json.loads((out / 'EFFECTS.json').read_bytes())
    assert b.sha((out / 'EFFECTS.json').read_bytes()) == sheet['effects_sha256'] and effects['writes'] == 0 and effects['operation'] == PRECHECK
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    authority = json.loads((out / signed['authority_name']).read_bytes())
    go = json.loads((out / signed['go_name']).read_bytes())
    assert request['date'] == '2026-10-03' and request['evidence'] == [] and request['plan']['status'] == 'BOUND'
    assert {key: request['plan'][key] for key in h.PRECHECK_PLAN} == h.PRECHECK_PLAN
    assert authority['effects'] == go['effects'] == effects and go['success_criterion'] == 'PRECHECK_ALL_OBSERVED'
    assert go['scope_statement'] + '\n' == (out / 'GO_SCOPE.txt').read_text() and 'scope' not in go and 'owner_evidence' not in go
    assert authority['owner_evidence'] == ('REHEARSAL_NOT_THE_OWNER answered "REHEARSAL_NO_OWNER_ANSWER" (REHEARSAL_NO_OWNER_WAS_ASKED) at '
                                           '2026-10-03T13:00:00Z over sheet PREPARE.json sha256:' + prepared['prepare_json_sha256'])
    assert len(request) == 16 and len(authority) == 16 and len(go) == 20          # exactly the key sets of the family
    question = (out / 'OWNER_QUESTION.txt').read_text(encoding='utf-8')
    assert 'pré-checagem' in question and sheet['effects_sha256'] in question and 'critério de sucesso: PRECHECK_ALL_OBSERVED' in question
    checked = b.check(out, families['hostops'], now=lambda: NOW)
    assert checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['proofs']['dispatcher_accepts_at_not_before'] == 'ACCEPTED_UP_TO_THE_CLAIM'
    assert checked['proofs']['dispatcher_refuses_unsigned_go'] == 'GO_UNSIGNED' and checked['proofs']['source_refuses_at_not_after'] == 'OUTSIDE_GO_WINDOW'
    intent = h.dispatcher_prepare(out, NOW + SEC)
    assert intent['status'] == 'AWAITING_PUBLICATION_NO_SPAWN' and b.status(out)['status'] == 'PREPARED_AWAITING_PUBLICATION'
    assert json.loads((out / '.dispatch-root' / 'precheck-once' / 'intent.json').read_bytes())['schema'] == 'HOSTOPS_PRECHECK_DISPATCH_INTENT_V1'


def test_core_gate_window_inside_a_longer_owner_window(base, families):
    """The owner's window is the request and authority window; the GO and the dispatch carry the shorter gate."""
    reference = h.rehearsal_reference(base)
    parameters = h.precheck_parameters(base, not_before='2026-10-03T03:00:00Z', not_after='2026-10-03T23:59:59Z',
                                       gate_not_before='2026-10-03T13:00:00Z', gate_not_after='2026-10-03T14:00:00Z')
    out, prepared, signed = h.bind(base, families['hostops'], PRECHECK, parameters, reference)
    request, authority, go, config = (json.loads((out / name).read_bytes()) for name in ('REQUEST.BOUND.json', signed['authority_name'], signed['go_name'], 'DISPATCH.BOUND.json'))
    assert (request['not_before'], request['not_after']) == (authority['not_before'], authority['not_after']) == ('2026-10-03T03:00:00Z', '2026-10-03T23:59:59Z')
    assert (go['not_before'], go['not_after']) == (config['not_before'], config['not_after']) == ('2026-10-03T13:00:00Z', '2026-10-03T14:00:00Z')
    assert config['latest_start'] == '2026-10-03T13:58:40Z' and prepared['sheet']['window']['gate_span_seconds'] == 3600
    question = (out / 'OWNER_QUESTION.txt').read_text(encoding='utf-8')
    assert 'de sáb 03/10/2026 00:00:00 BRT até sáb 03/10/2026 20:59:59 BRT' in question and 'só pode acontecer de sáb 03/10/2026 10:00:00 BRT até sáb 03/10/2026 11:00:00 BRT' in question
    assert b.check(out, now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    for changes in ({'not_after': '2026-10-03T15:00:01Z'}, {'gate_not_before': '2026-10-03T13:00:00Z', 'gate_not_after': '2026-10-03T14:00:01Z', 'not_after': '2026-10-03T15:00:00Z'}):
        with refused('GATE_SPAN_OVER_FAMILY_CAP'):
            b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, name='P2.json', **changes), reference, base / 'rehearsal-two', b.REHEARSAL, now=lambda: NOW)
    with refused('WINDOW_ORDER'):
        b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, name='P3.json', gate_not_before='2026-10-03T12:59:59Z', gate_not_after='2026-10-03T13:30:00Z'),
                  reference, base / 'rehearsal-two', b.REHEARSAL, now=lambda: NOW)
    with refused('PARAMETERS_INVALID'):
        b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, name='P4.json', gate_not_before='2026-10-03T13:00:00Z'),
                  reference, base / 'rehearsal-two', b.REHEARSAL, now=lambda: NOW)
    assert not (base / 'rehearsal-two').exists()


def precheck_receipt(base, hostops_harness, name='precheck.stdout.private.json', change=None, host=h.REHEARSAL_HOST):
    """An OP_PRECHECK receipt of the family, taken on its emulated host with the family's own fixture documents, then bound
    to the host binding of the rehearsal sets (the fixtures bind it to their synthetic host 1111...) and sealed again: the
    evidence a rehearsal write request cites as a loose file. `change` edits the body before the seal."""
    f, hostemu = hostops_harness
    k = f.load('precheck')
    world = f.world(k)
    receipt = f.Docs(k, f.precheck_fields(k, world, placement='A')).run(world)
    assert receipt['outcome'] == 'PRECHECK_ALL_OBSERVED' and receipt['host_binding_sha256'] == f.HOST
    receipt = h.resealed(receipt, change, host)
    return h.receipt_file(base / name, receipt), receipt


def provision_parameters(base, hostops_harness, receipt_file, name='PARAMETERS.json', **changes):
    f, hostemu = hostops_harness
    k = f.load('provision')
    plan = f.provision_fields(k, f.world(k), placement='A')
    expected = json.loads(json.dumps(plan))

    def copy(pointer):
        return {'$from': {'evidence': 'PRECHECK', 'pointer': pointer}}
    plan['chains'] = {key: copy('/items/chains/%s/rows' % key) for key in plan['chains']}
    plan['evidence_boot_id_sha256'] = copy('/items/boot/boot_id_sha256')
    plan['retention_tag']['image_id'] = copy('/items/image/id')
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': PROVISION, 'label': 'provision', 'signature_model': 'IND', 'not_before': b.zulu(h.HOSTOPS_NOW),
             'not_after': b.zulu(h.HOSTOPS_NOW + 10 * MIN), 'plan': plan, 'review': h.review_record(base),
             'evidence': [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_file': str(receipt_file)}]}
    return h.write_json(base / name, h.apply(value, changes)), expected


def test_provision_flow_with_rows_copied_from_the_precheck_receipt_and_resume_on_the_emulated_host(base, families, hostops_harness):
    f, hostemu = hostops_harness
    receipt_file, receipt = precheck_receipt(base, hostops_harness)
    parameters, expected_plan = provision_parameters(base, hostops_harness, receipt_file)
    reference = h.rehearsal_reference(base)
    out, prepared, signed = h.bind(base, families['hostops'], PROVISION, parameters, reference, now=h.HOSTOPS_NOW)
    sheet = prepared['sheet']
    assert sheet['writes_allowed'] is True and sheet['success_criterion'] == 'PROVISIONED_ALL_VERIFIED_DURABLE' and sheet['window']['gate_span_seconds'] == 600
    assert sheet['evidence'] == [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_sha256': receipt['metadata_sha256'],
                                  'receipt_file_sha256': b.sha(receipt_file.read_bytes()), 'receipt_status': 'METADATA_ONLY_REQUIRES_REVIEW',
                                  'receipt_schema': 'READONLY_HOSTOPS_PRECHECK_RECEIPT_V1', 'outcome': 'PRECHECK_ALL_OBSERVED', 'complete': True,
                                  'not_complete_accepted_by_parameter': False, 'receipt_host_binding_is_the_one_of_this_set': True,
                                  'receipt_payload_is_the_sealed_source_of_that_operation': True,
                                  'source': 'RECEIPT_FILE', 'bound_set': None, 'exit_json_binds_these_bytes': None}]
    assert {(item['plan_pointer'], item['operation'], item['receipt_pointer']) for item in sheet['plan_values_equal_to_the_cited_receipts']} == {
        ('/chains/ETC', PRECHECK, '/items/chains/ETC/rows'), ('/chains/VAR_LIB', PRECHECK, '/items/chains/VAR_LIB/rows'),
        ('/chains/DATA_VOLUME', PRECHECK, '/items/chains/DATA_VOLUME/rows'), ('/evidence_boot_id_sha256', PRECHECK, '/items/boot/boot_id_sha256'),
        ('/retention_tag/image_id', PRECHECK, '/items/image/id')}
    assert sheet['review'] == {'kind': 'CODEX_REVIEWED', 'document_sha256': b.sha((base / 'REVIEW_RECORD.synthetic.txt').read_bytes()),
                               'document_bytes': len((base / 'REVIEW_RECORD.synthetic.txt').read_bytes())} and sheet['signature_model'] == 'IND'
    assert {item['plan_pointer'] for item in sheet['plan_values_copied_from_receipts']} == {'/chains/ETC', '/chains/VAR_LIB', '/chains/DATA_VOLUME',
                                                                                          '/evidence_boot_id_sha256', '/retention_tag/image_id'}
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    # the rows that entered the request by pointer are exactly the rows the family's own fixture builds for the same host
    assert {key: request['plan'][key] for key in expected_plan} == expected_plan
    assert request['evidence'] == [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_sha256': receipt['metadata_sha256']}] and request['writes_allowed'] is True
    question = (out / 'OWNER_QUESTION.txt').read_text(encoding='utf-8')
    assert 'ESTA OPERAÇÃO GRAVA NO SERVIDOR' in question and 'uma operação que GRAVA' in question and 'parcial' not in question
    # the owner is shown what is created, path by path, the review status bound by hash, and the receipt the request rests on
    effects = json.loads((out / 'EFFECTS.json').read_bytes())
    assert len(effects['creates']) == 15 and all('- diretório %s, modo 0700 (será criado)' % row['path'] in question for row in effects['creates'])
    assert '- etiqueta de imagem c3po/backend:massive-supervisor-epoch03 sobre o ID de imagem assinado (será criado)' in question
    assert effects['retention_tag']['image_id'] not in question          # the image ID stays in EFFECTS.json
    assert 'Revisão prévia do Codex sobre estes bytes: FEITA, segundo o registro de sha256 ' + sheet['review']['document_sha256'] in question
    assert '- PRECHECK: %s, recibo sha256 %s, resultado PRECHECK_ALL_OBSERVED (completo)' % (PRECHECK, receipt['metadata_sha256']) in question
    assert 'Modelo de assinatura: individual (IND)' in question
    assert b.check(out, families['hostops'], now=lambda: h.HOSTOPS_NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    # resume on the family's emulated host, as uid 0, through the family's dispatcher
    k = f.load('provision')
    host = f.world(k)
    state = b.signed_state(out)

    def transport(payload, **kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'], kwargs['command_sha256']) is True
        raws = state['raws']
        pins = k.m.Pins(payload=f.sha(k.source), request=f.sha(raws[0]), authority=f.sha(raws[1]), go=f.sha(raws[2]))
        done = k.m.run(raws[0], raws[1], raws[2], pins=pins, payload_bytes=k.source, host=host, clock=lambda: h.HOSTOPS_NOW + 4 * SEC,
                       monotonic=lambda: 0, executor_uid=lambda: 0)
        return {'status': 'KNOWN_COMPLETE' if done['status'] == 'METADATA_ONLY_REQUIRES_REVIEW' else 'KNOWN_PARTIAL', 'retry_allowed': False}, f.line(done), b''
    result = h.finish(out, transport, at=h.HOSTOPS_NOW)
    report = b.status(out)
    assert result['status'] == report['status'] == 'KNOWN_COMPLETE' and report['verified'] is True
    assert report['outcome'] == report['success_criterion'] == 'PROVISIONED_ALL_VERIFIED_DURABLE' and report['success_criterion_met'] is True
    assert report['mutating_calls']['uncertain'] == 0 and report['mutating_calls']['succeeded'] > 0 and all(report['receipt_bindings'].values())
    assert '/etc/c3po-bar' not in json.dumps(report) and '801' not in json.dumps(report['mutating_calls'])


def test_evidence_and_plan_references_are_computed_never_typed(base, families, hostops_harness):
    receipt_file, receipt = precheck_receipt(base, hostops_harness)
    reference = h.rehearsal_reference(base)

    def attempt(code, **changes):
        parameters, _ = provision_parameters(base, hostops_harness, receipt_file, name='P-%s.json' % len(os.listdir(str(base))), **changes)
        with refused(code):
            b.prepare(families['hostops'], PROVISION, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
        assert not (base / 'rehearsal-bound').exists()

    def evidence(path, role='PRECHECK', operation=PRECHECK, **extra):
        return [dict({'role': role, 'operation': operation, 'receipt_file': str(path)}, **extra)]
    attempt('EVIDENCE_RECEIPT_UNREADABLE', evidence=evidence(base / 'missing.json'))
    for index, bad in enumerate((b'not json', b'[1]', b'{"status":"METADATA_ONLY_REQUIRES_REVIEW"}', b'{"a":1,"a":2}')):
        (base / ('bad%d.json' % index)).write_bytes(bad)
        attempt('EVIDENCE_RECEIPT_INVALID', evidence=evidence(base / ('bad%d.json' % index)))
    changed = dict(receipt, ready=True)
    h.write_json(base / 'changed.json', changed)
    attempt('EVIDENCE_RECEIPT_SEAL', evidence=evidence(base / 'changed.json'))          # a typed or edited receipt hash cannot enter a request
    refusal = {'status': 'REFUSED', 'operation': PRECHECK, 'code': 'OUTSIDE_GO_WINDOW'}
    refusal['metadata_sha256'] = b.sha(b.canonical(refusal))
    h.write_json(base / 'refusal.json', refusal)
    attempt('EVIDENCE_RECEIPT_NOT_A_RESULT', evidence=evidence(base / 'refusal.json'))
    attempt('EVIDENCE_RECEIPT_OPERATION', evidence=evidence(receipt_file, operation='GO_READONLY_SUPERVISOR_READBACK_01'))
    for bad in ([{'role': 'PRECHECK', 'operation': PRECHECK}], [{'role': 'precheck', 'operation': PRECHECK, 'receipt_file': str(receipt_file)}],
                evidence(receipt_file) * 2, evidence(receipt_file, receipt_sha256='a' * 64), 'x', evidence(receipt_file) * 17):
        attempt('PARAMETERS_INVALID', evidence=bad)
    # an exit.json beside the receipt must bind those very bytes
    beside = base / 'attempt'
    beside.mkdir()
    shutil.copy(str(receipt_file), str(beside / 'stdout.private.json'))
    h.write_json(beside / 'exit.json', {'status': 'KNOWN_COMPLETE', 'stdout_sha256': '9' * 64})
    attempt('EVIDENCE_RECEIPT_EXIT_MISMATCH', evidence=evidence(beside / 'stdout.private.json'))
    h.write_json(beside / 'exit.json', {'status': 'KNOWN_PARTIAL', 'stdout_sha256': b.sha(receipt_file.read_bytes())})
    attempt('EVIDENCE_RECEIPT_EXIT_MISMATCH', evidence=evidence(beside / 'stdout.private.json'))
    (beside / 'exit.json').write_bytes(b'not json')
    attempt('EVIDENCE_RECEIPT_EXIT_MISMATCH', evidence=evidence(beside / 'stdout.private.json'))
    # plan references
    parameters, expected = provision_parameters(base, hostops_harness, receipt_file)
    plan = json.loads(parameters.read_text())['plan']
    attempt('PLAN_REFERENCE_NOT_FOUND', plan=dict(plan, evidence_boot_id_sha256={'$from': {'evidence': 'PRECHECK', 'pointer': '/items/boot/absent'}}))
    attempt('PLAN_REFERENCE_NOT_FOUND', plan=dict(plan, evidence_boot_id_sha256={'$from': {'evidence': 'PRECHECK', 'pointer': '/items/chains/ETC/rows/7'}}))
    attempt('PLAN_REFERENCE_INVALID', plan=dict(plan, evidence_boot_id_sha256={'$from': {'evidence': 'OTHER', 'pointer': '/items/boot/boot_id_sha256'}}))
    attempt('PLAN_REFERENCE_INVALID', plan=dict(plan, evidence_boot_id_sha256={'$from': {'evidence': 'PRECHECK', 'pointer': 'items'}}))
    attempt('PLAN_REFERENCE_INVALID', plan=dict(plan, evidence_boot_id_sha256={'$from': {'evidence': 'PRECHECK', 'pointer': '/items/boot/boot_id_sha256'}, 'other': 1}))
    attempt('PLAN_KEYS_MISMATCH', plan={key: value for key, value in plan.items() if key != 'creates'})
    attempt('PLAN_KEYS_MISMATCH', plan=dict(plan, extra=1))
    attempt('PARAMETERS_INVALID', plan=[1])
    attempt('FAMILY_REFUSES_THE_PLAN', plan=dict(plan, creates=None))
    # a boot identifier that is not the cited receipt's, typed: refused by the binder before the family is even asked
    attempt('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', plan=dict(plan, evidence_boot_id_sha256='not-a-hash'))
    # a write request without the precheck evidence: its typed rows have no receipt to be compared with
    attempt('PLAN_VALUE_WITHOUT_ITS_SINGLE_CITED_RECEIPT', plan=expected, evidence=[])
    # what the family's own authenticate() refuses in a core request is surfaced with the family's code, before anything is created
    with pytest.raises(b.Refused) as caught:
        parameters, _ = provision_parameters(base, hostops_harness, receipt_file, name='P-family.json', plan=dict(plan, journal_leaf='Not A Leaf'))
        b.prepare(families['hostops'], PROVISION, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
    assert str(caught.value).startswith('FAMILY_REFUSES_THE_') and not (base / 'rehearsal-bound').exists()
    # a write gate longer than the family's 900 s
    attempt('GATE_SPAN_OVER_FAMILY_CAP', not_after=b.zulu(h.HOSTOPS_NOW + 16 * MIN))
    # 2026-10-05 UTC is not a write date of this family
    with refused('DATE_NOT_IN_FAMILY_SCOPE'):
        parameters, _ = provision_parameters(base, hostops_harness, receipt_file, name='P-date.json', not_before='2026-10-05T08:00:00Z', not_after='2026-10-05T08:10:00Z')
        b.prepare(families['hostops'], PROVISION, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)


INSTALL = 'GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
READBACK = 'GO_READONLY_SUPERVISOR_READBACK_01'


def core_parameters(base, operation, label, plan, evidence, name='PARAMETERS.json', minutes=10, **changes):
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': operation, 'label': label, 'signature_model': 'IND', 'not_before': b.zulu(h.HOSTOPS_NOW),
             'not_after': b.zulu(h.HOSTOPS_NOW + minutes * MIN), 'plan': plan, 'evidence': evidence}
    if operation in (PROVISION, INSTALL):
        value['review'] = h.review_record(base)
    return h.write_json(base / name, h.apply(value, changes))


def emulated_transport(f, k, host, state):
    """The family's own source on the family's emulated host, target uid injected: what the remote side would answer."""
    def transport(payload, **kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'], kwargs['command_sha256']) is True
        raws = state['raws']
        pins = k.m.Pins(payload=f.sha(k.source), request=f.sha(raws[0]), authority=f.sha(raws[1]), go=f.sha(raws[2]))
        done = k.m.run(raws[0], raws[1], raws[2], pins=pins, payload_bytes=k.source, host=host, clock=lambda: h.HOSTOPS_NOW + 4 * SEC,
                       monotonic=lambda: 0, executor_uid=lambda: 0)
        return {'status': 'KNOWN_COMPLETE' if done['status'] == 'METADATA_ONLY_REQUIRES_REVIEW' else 'KNOWN_PARTIAL', 'retry_allowed': False}, f.line(done), b''
    return transport


def from_receipt(role, pointer):
    return {'$from': {'evidence': role, 'pointer': pointer}}


def test_install_units_flow_with_units_rendered_again_by_the_reference_loop(base, families, hostops_harness):
    f, hostemu = hostops_harness
    receipt_file, receipt = precheck_receipt(base, hostops_harness)
    k = f.load('install_units')
    host = f.world(k)
    plan = f.install_fields(k, host, placement='A')
    expected = json.loads(json.dumps(plan))
    plan['unit_directory'] = from_receipt('PRECHECK', '/items/chains/UNIT_DIRECTORY/rows')
    plan['evidence_boot_id_sha256'] = from_receipt('PRECHECK', '/items/boot/boot_id_sha256')
    evidence = [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_file': str(receipt_file)}]
    reference = h.rehearsal_reference(base)
    out, prepared, signed = h.bind(base, families['hostops'], INSTALL, core_parameters(base, INSTALL, 'install', plan, evidence), reference, now=h.HOSTOPS_NOW)
    sheet = prepared['sheet']
    assert sheet['contract_section_12_checks'] == {'units_rendered_again_by_the_reference_loop': 2} and sheet['writes_allowed'] is True
    assert [item['plan_pointer'] for item in sheet['plan_values_equal_to_the_cited_receipts']] == ['/unit_directory', '/evidence_boot_id_sha256']
    for name in ('c3po-massive.service', 'c3po-massive.timer'):
        assert '- arquivo /etc/systemd/system/%s, modo 0644 (será criado)' % name in prepared['owner_question_pt']
    assert sheet['success_criterion'] == 'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    assert {key: request['plan'][key] for key in expected} == expected
    assert 'instalação dos arquivos de unidade' in prepared['owner_question_pt'] and 'ESTA OPERAÇÃO GRAVA NO SERVIDOR' in prepared['owner_question_pt']
    assert b.check(out, families['hostops'], now=lambda: h.HOSTOPS_NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    result = h.finish(out, emulated_transport(f, k, host, b.signed_state(out)), at=h.HOSTOPS_NOW)
    report = b.status(out)
    assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and report['success_criterion_met'] is True
    assert report['outcome'] == 'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    # a unit whose signed hash or size is not the reference render of its template and values: refused before the owner is asked
    counter = [0]

    def attempt(change):
        counter[0] += 1
        changed = json.loads(json.dumps(plan))
        change(changed['units'])
        parameters = core_parameters(base, INSTALL, 'install', changed, evidence, name='P%d.json' % counter[0])
        with refused('UNIT_RENDER_NOT_THE_REFERENCE_LOOP'):
            b.prepare(families['hostops'], INSTALL, parameters, reference, base / 'rehearsal-two', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
        assert not (base / 'rehearsal-two').exists()
    attempt(lambda units: units[0].update(rendered_bytes=units[0]['rendered_bytes'] + 1))
    attempt(lambda units: units[0].update(rendered_sha256='9' * 64))
    attempt(lambda units: units[0]['placeholders'].update(NETWORK='host'))
    attempt(lambda units: units[0]['placeholders'].pop('NETWORK'))          # a placeholder left in the text
    attempt(lambda units: units[0]['placeholders'].update(NETWORK=5))
    attempt(lambda units: units[0].update(template_b64='not base64 at all!'))
    attempt(lambda units: units[0].update(template_sha256='9' * 64))
    attempt(lambda units: units[1].update(template_b64=5))
    attempt(lambda units: units.append('not a unit'))
    attempt(lambda units: units[0].update(placeholders=None))
    assert b.reference_render(b'A=@X@ B=@Y@ A=@X@\n', {'X': '1', 'Y': '2'}) == b'A=1 B=2 A=1\n'
    with refused('UNIT_RENDER_NOT_THE_REFERENCE_LOOP'):
        b.reference_render('é@X@'.encode('utf-8'), {'X': '1'})
    with refused('UNIT_RENDER_NOT_THE_REFERENCE_LOOP'):
        b.reference_render(b'@X@', {'X': 'é'})


def test_readback_flow_and_the_floor_compared_with_the_precheck_figure_before_the_signature(base, families, hostops_harness):
    f, hostemu = hostops_harness
    k = f.load('readback')
    host, provision, install = f.ready_host(k, placement='A')
    provision, install = h.resealed(provision), h.resealed(install)          # the fixtures' receipts, bound to the host of the rehearsal sets
    precheck_file, precheck = precheck_receipt(base, hostops_harness)
    files = {'PRECHECK': precheck_file}
    for role, receipt in (('PROVISION', provision), ('INSTALL', install)):
        files[role] = h.receipt_file(base / (role.lower() + '.stdout.private.json'), receipt)
    operations = {'PRECHECK': PRECHECK, 'PROVISION': PROVISION, 'INSTALL': INSTALL}

    def evidence(*roles, **replaced):
        return [{'role': role, 'operation': operations[role.rstrip('2')], 'receipt_file': str(replaced.get(role, files[role.rstrip('2')]))} for role in roles]
    plan = f.readback_fields(k, host, provision, install)
    expected = json.loads(json.dumps(plan))
    plan['provision'] = {'receipt_sha256': from_receipt('PROVISION', '/metadata_sha256')}
    plan['install'] = {'receipt_sha256': from_receipt('INSTALL', '/metadata_sha256'), 'outcome': from_receipt('INSTALL', '/outcome')}
    plan['journal_mount_point'] = from_receipt('PROVISION', '/effects/journal/mount_point_by_device_change')
    reference = h.rehearsal_reference(base)
    parameters = core_parameters(base, READBACK, 'readback', plan, evidence('PRECHECK', 'PROVISION', 'INSTALL'), minutes=50)
    out, prepared, signed = h.bind(base, families['hostops'], READBACK, parameters, reference, now=h.HOSTOPS_NOW)
    sheet = prepared['sheet']
    assert sheet['contract_section_12_checks'] == {'units_rendered_again_by_the_reference_loop': 2, 'floor_compared_on_chain': 'VAR_LIB',
                                                   'floor_met_by_the_precheck_figure': True, 'journal_mount_point_is_the_one_in_the_provision_effects': True}
    assert '595212316672' not in json.dumps(sheet) and '56706990080' not in json.dumps(sheet)          # the figures stay in the request and the receipts
    assert [item['plan_pointer'] for item in sheet['plan_values_equal_to_the_cited_receipts']] == [
        '/provision/receipt_sha256', '/install/receipt_sha256', '/install/outcome', '/evidence_boot_id_sha256', '/unit_directory']
    assert sheet['review'] is None and 'Recibos em que este pedido se apoia:' in prepared['owner_question_pt'] and 'O que esta execução cria' not in prepared['owner_question_pt']
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    assert {key: request['plan'][key] for key in expected} == expected and len(request['evidence']) == 3
    assert sheet['success_criterion'] == 'READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET' and sheet['writes_allowed'] is False
    assert b.check(out, families['hostops'], now=lambda: h.HOSTOPS_NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    result = h.finish(out, emulated_transport(f, k, host, b.signed_state(out)), at=h.HOSTOPS_NOW)
    report = b.status(out)
    assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and report['success_criterion_met'] is True
    assert report['outcome'] == 'READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'

    counter = [0]

    def attempt(code, changed_plan=None, cited=None):
        counter[0] += 1
        parameters = core_parameters(base, READBACK, 'readback', changed_plan or plan, cited or evidence('PRECHECK', 'PROVISION', 'INSTALL'),
                                     name='P%d.json' % counter[0], minutes=50)
        with refused(code):
            b.prepare(families['hostops'], READBACK, parameters, reference, base / 'rehearsal-two', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
        assert not (base / 'rehearsal-two').exists()

    def resealed(receipt, name, change):
        value = json.loads(json.dumps(receipt))
        value.pop('metadata_sha256')
        change(value)
        value['metadata_sha256'] = b.sha(b.canonical(value))
        path = base / name
        path.write_bytes(f.line(value))
        return path
    floor = expected['free_space_floor_bytes']
    # the precheck read less than the floor on the chain the provision names: the GATE readback would exit 2 and spend its GO
    short = resealed(precheck, 'short.json', lambda value: value['items']['chains']['VAR_LIB'].update(bytes_available_to_non_root_f_bavail=floor - 1))
    attempt('FREE_SPACE_BELOW_FLOOR_DO_NOT_ASK_FOR_THE_SIGNATURE', cited=evidence('PRECHECK', 'PROVISION', 'INSTALL', PRECHECK=short))
    # the family accepts any mount point above the journal root; the binder demands the one the provision receipt shows
    attempt('READBACK_MOUNT_POINT_NOT_THE_PROVISION_ONE', dict(plan, journal_mount_point='/var'))
    attempt('READBACK_FLOOR_EVIDENCE_MISSING', cited=evidence('PROVISION', 'INSTALL'))
    attempt('READBACK_FLOOR_EVIDENCE_MISSING', cited=evidence('PRECHECK', 'INSTALL'), changed_plan=dict(
        plan, provision={'receipt_sha256': provision['metadata_sha256']}, journal_mount_point='/'))
    attempt('READBACK_FLOOR_EVIDENCE_MISSING', cited=evidence('PRECHECK', 'PRECHECK2', 'PROVISION', 'INSTALL'))          # two candidates: not decided by guess
    no_journal = resealed(provision, 'no-journal.json', lambda value: value['effects'].pop('journal'))
    attempt('READBACK_FLOOR_EVIDENCE_MISSING', cited=evidence('PRECHECK', 'PROVISION', 'INSTALL', PROVISION=no_journal),
            changed_plan=dict(plan, journal_mount_point='/'))
    no_chain = resealed(precheck, 'no-chain.json', lambda value: value['items']['chains'].pop('VAR_LIB'))
    attempt('READBACK_FLOOR_EVIDENCE_MISSING', cited=evidence('PRECHECK', 'PROVISION', 'INSTALL', PRECHECK=no_chain))
    attempt('UNIT_RENDER_NOT_THE_REFERENCE_LOOP', dict(plan, substitutions=dict(expected['substitutions'], NETWORK='host')))
    # the rule itself, at its boundary, and outside GATE mode
    entries = [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_sha256': 'a' * 64}, {'role': 'PROVISION', 'operation': PROVISION, 'receipt_sha256': 'b' * 64}]
    exact = json.loads(json.dumps(precheck))
    exact['items']['chains']['VAR_LIB']['bytes_available_to_non_root_f_bavail'] = floor
    assert b.presign_rules(expected, entries, {'PRECHECK': exact, 'PROVISION': provision})['floor_met_by_the_precheck_figure'] is True
    assert 'floor_compared_on_chain' not in b.presign_rules(dict(expected, mode='RECONCILIATION'), [], {})


# ---------------------------------------------------------------- REAL mode, with a synthetic executed reference
def test_real_mode_binds_from_an_executed_reference_and_prints_no_transport_value(base, families, capsys, monkeypatch):
    out, prepared, signed, reference = real_set(base, families)
    sheet = prepared['sheet']
    config = json.loads((out / 'DISPATCH.BOUND.json').read_bytes())
    executed = json.loads(reference.read_bytes())
    assert sheet['mode'] == 'REAL' and sheet['owner'] == 'DUDU' and signed['authority_name'] == 'DUDU_ATTEMPT_AUTHORITY.json' and signed['go_name'] == 'DUDU_ATTEMPT_GO.json'
    assert {key: config[key] for key in ('target', 'remote_command', 'ssh_key', 'known_hosts', 'command_sha256', 'host_binding_sha256')} == \
        {key: executed[key] for key in ('target', 'remote_command', 'ssh_key', 'known_hosts', 'command_sha256', 'host_binding_sha256')}
    assert sheet['transport_reference']['sha256'] == b.sha(reference.read_bytes()) and sheet['transport_reference']['last_use']['status'] == 'KNOWN_COMPLETE'
    assert sheet['transport_reference']['connection_files'] == {'lstat_only_never_opened': True, 'mtime_and_ctime_older_than_last_use_exit_json': True}
    authority = json.loads((out / signed['authority_name']).read_bytes())
    assert authority['owner'] == 'DUDU' and authority['owner_evidence'] == {'channel': 'AskUserQuestion via Fable', 'owner_answer_verbatim': 'Assino',
                                                                            'signed_at_utc': '2026-10-03T13:00:00Z', 'prepare_sheet_sha256': prepared['prepare_json_sha256']}
    assert config['authorization_ref'] == 'sha256:%s (DUDU_ATTEMPT_GO.json, owner answer recorded at 2026-10-03T13:00:00Z, over sheet PREPARE.json sha256:%s)' % (
        signed['go_sha256'], prepared['prepare_json_sha256'])
    question = (out / 'OWNER_QUESTION.txt').read_text(encoding='utf-8')
    assert question.rstrip().endswith('Se estiver de acordo, responda exatamente: Assino') and 'ENSAIO' not in question
    assert b.check(out, families['w1'], now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    # the key and known-hosts files were never opened: only lstat reaches them
    opened = []
    real_open = os.open

    def spy(path, flags, *args, **kwargs):
        opened.append(str(path))
        return real_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(b.os, 'open', spy)
    b.check(out, families['w1'], now=lambda: NOW)
    monkeypatch.undo()
    assert opened and not any(Path(item).name in ('ssh_key', 'known_hosts') for item in opened)
    # a real set takes a numeric comment id, never the rehearsal marker
    h.dispatcher_prepare(out, NOW + SEC)
    for bad in (b.REHEARSAL_PUBLICATION, '12', 'https://example.org/1', '1234567x', None):
        with refused('COMMENT_ID_INVALID'):
            b.publish_proof(out, bad, b.zulu(NOW + 2 * SEC), now=lambda: NOW + 3 * SEC)
    proof = b.publish_proof(out, '5955151654', b.zulu(NOW + 2 * SEC), now=lambda: NOW + 3 * SEC)
    assert json.loads((out / 'PUBLICATION.PROOF.json').read_bytes())['publication_ref'] == '5955151654' and proof['mode'] == 'REAL'
    # no output of the binder, and no file meant to be read or published, carries the target or a key path
    printed = json.dumps([prepared, signed, proof, b.check(out, now=lambda: NOW), b.status(out)])
    secrets = [executed['target'], executed['target'].split('@')[1], executed['ssh_key']['path'], executed['known_hosts']['path']]
    for name in ('PREPARE.json', 'OWNER_QUESTION.txt', 'SHA256SUMS', 'CLAIM_ROOT_IDENTITY.json', 'GO_SCOPE.txt', 'PARAMETERS.json', 'REQUEST.BOUND.json', 'PUBLICATION.PROOF.json'):
        printed += (out / name).read_text(encoding='utf-8')
    assert all(secret not in printed for secret in secrets)
    assert executed['target'] in (out / 'DISPATCH.BOUND.json').read_text() and executed['target'] in (out / signed['go_name']).read_text()


def test_the_binder_and_its_documents_hold_no_value_of_the_executed_bound_sets():
    """The files of this binder against the transport values recorded in the bound sets that really ran (when they are on
    this machine). Only booleans are asserted, so that a failure prints no value."""
    candidates = [Path('/offline/optional-work/hostfacts01-fable-20261002/bound/DISPATCH.BOUND.json'),
                  h.SCRATCH / 'postdeploy-rev5' / 'bound-F2' / 'DISPATCH.BOUND.json']
    texts = [path.read_text(encoding='utf-8', errors='replace') for path in sorted(h.BIND.glob('*')) + sorted(h.HERE.glob('*.py')) if path.is_file()]
    checked = 0
    for path in candidates:
        if not path.is_file():
            continue
        config = json.loads(path.read_bytes())
        values = [config['target'], config['target'].split('@')[-1], config['ssh_key']['path'], config['known_hosts']['path']]
        found = any(value in text for value in values for text in texts)
        assert not found, 'a transport value of an executed bound set appears in a file of the binder'
        checked += 1
    if not checked:
        pytest.skip('no executed bound set on this machine')


# ---------------------------------------------------------------- REAL and REHEARSAL never mix
def test_rehearsal_and_real_cannot_be_mixed_at_prepare(base, families):
    fake = h.rehearsal_reference(base)
    executed = h.executed_reference(base, families['w1'])
    parameters = h.w1_parameters(base)

    def attempt(code, reference, out, mode):
        with refused(code):
            b.prepare(families['w1'], W1, parameters, reference, base / out, mode, now=lambda: NOW)
        assert not (base / out).exists()
    attempt('REAL_SET_WITH_REHEARSAL_TRANSPORT', fake, 'bound', b.REAL)
    attempt('REHEARSAL_SET_WITH_REAL_TRANSPORT', executed, 'rehearsal-bound', b.REHEARSAL)
    attempt('REHEARSAL_DIRECTORY_NAME', fake, 'bound', b.REHEARSAL)
    attempt('REAL_SET_IN_REHEARSAL_DIRECTORY', executed, 'rehearsal-bound', b.REAL)
    attempt('REAL_SET_IN_REHEARSAL_DIRECTORY', executed, 'Rehearsal_bound', b.REAL)
    attempt('MODE_INVALID', fake, 'rehearsal-bound', 'DRY')
    # an executed-looking reference whose target is in a reserved domain, or whose files are the rehearsal markers, is not REAL
    for index, target in enumerate(('operator@host.invalid', 'operator@host.test', 'operator@host.example', 'operator@localhost', b.REHEARSAL_TARGET)):
        attempt('REAL_SET_WITH_REHEARSAL_TRANSPORT', h.executed_reference(base, families['w1'], name='executed-%d' % index, target=target), 'bound', b.REAL)
    marker = json.loads(fake.read_bytes())
    attempt('REAL_SET_WITH_REHEARSAL_TRANSPORT', h.executed_reference(base, families['w1'], name='executed-marker', ssh_key=marker['ssh_key']), 'bound', b.REAL)
    # a rehearsal reference that names anything but the fake target and the marker files is not a rehearsal reference
    for index, changes in enumerate(({'target': h.SYNTHETIC_TARGET}, {'target': 'rehearsal@other.invalid'},
                                     {'ssh_key': json.loads(executed.read_bytes())['ssh_key']}, {'known_hosts': json.loads(executed.read_bytes())['known_hosts']})):
        path = h.write_json(base / ('reference-%d.json' % index), edit_json(fake, **changes))
        attempt('REHEARSAL_SET_WITH_REAL_TRANSPORT', path, 'rehearsal-bound', b.REHEARSAL)
    with refused('REHEARSAL_DIRECTORY_NAME'):
        b.rehearsal_reference(base / 'transport')
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.rehearsal_reference(fake.parent)
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.rehearsal_reference(base / 'missing' / 'rehearsal-x')


def test_a_rehearsal_set_cannot_become_real_and_a_real_set_cannot_become_a_rehearsal(base, families):
    (base / 'r').mkdir()
    (base / 'x').mkdir()
    rehearsal, prepared, signed = w1_set(base / 'r', families)
    real, real_prepared, real_signed, executed = real_set(base / 'x', families)
    executed_fields = {key: json.loads(executed.read_bytes())[key] for key in ('target', 'ssh_key', 'known_hosts', 'command_sha256', 'host_binding_sha256')}
    # 1. the directory name
    moved = rehearsal.parent / 'bound'
    rehearsal.rename(moved)
    for call in (lambda: b.check(moved, now=lambda: NOW), lambda: b.status(moved), lambda: b.publish_proof(moved, '5955151654', b.zulu(NOW), now=lambda: NOW)):
        with refused('REHEARSAL_DIRECTORY_NAME'):
            call()
    moved.rename(rehearsal)
    moved = real.parent / 'rehearsal-bound'
    real.rename(moved)
    with refused('REAL_SET_IN_REHEARSAL_DIRECTORY'):
        b.check(moved, now=lambda: NOW)
    moved.rename(real)
    # 2. the transport of a rehearsal set replaced by the executed one (and the hashes of the set made consistent again)
    config = edit_json(rehearsal / 'DISPATCH.BOUND.json', **executed_fields)
    original = (rehearsal / 'DISPATCH.BOUND.json').read_bytes()
    (rehearsal / 'DISPATCH.BOUND.json').write_bytes(b.pretty(config))
    with refused('BOUND_SUMS_INVALID'):
        b.check(rehearsal, now=lambda: NOW)
    h.rewrite_sums(rehearsal)
    for call in (lambda: b.check(rehearsal, now=lambda: NOW), lambda: b.status(rehearsal)):
        with refused('REHEARSAL_SET_WITH_REAL_TRANSPORT'):
            call()
    # ... and the family's own dispatcher refuses that configuration as well: the signed GO binds the fake target
    d = h.runtime_of(families['w1'], W1)['dispatch']
    d.__file__ = str(rehearsal / 'dispatch_once.py')
    with pytest.raises(ValueError, match='GO_TRANSPORT_BINDING|HOST_BINDING'):
        d.execute(str(rehearsal / 'DISPATCH.BOUND.json'), b.sha(b.pretty(config)), phase='prepare', clock=lambda: NOW, monotonic=lambda: 0.0, transport=h.never)
    assert list((rehearsal / '.dispatch-root').iterdir()) == []
    (rehearsal / 'DISPATCH.BOUND.json').write_bytes(original)
    h.rewrite_sums(rehearsal)
    assert b.check(rehearsal, now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    # 3. the transport of a real set replaced by the fake one
    fake = json.loads((rehearsal / 'DISPATCH.BOUND.json').read_bytes())
    (real / 'DISPATCH.BOUND.json').write_bytes(b.pretty(edit_json(real / 'DISPATCH.BOUND.json', target=fake['target'], ssh_key=fake['ssh_key'], known_hosts=fake['known_hosts'])))
    h.rewrite_sums(real)
    with refused('REAL_SET_WITH_REHEARSAL_TRANSPORT'):
        b.check(real, now=lambda: NOW)
    # 4. the sheet: mode or owner edited
    for name, changes, code in (('m1', {'mode': 'REAL'}, 'REAL_SET_IN_REHEARSAL_DIRECTORY'), ('m2', {'owner': 'DUDU'}, 'OWNER_MODE_MISMATCH'), ('m3', {'mode': 'OTHER'}, 'MODE_INVALID')):
        (base / name).mkdir()
        prepared, reference = w1_prepared(base / name, families)
        out = Path(prepared['bound'])
        (out / 'PREPARE.json').write_bytes(b.pretty(edit_json(out / 'PREPARE.json', **changes)))
        with refused(code):
            b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    (base / 'm4').mkdir()
    out, prepared, signed, executed = real_set(base / 'm4', families)
    (out / 'PREPARE.json').write_bytes(b.pretty(edit_json(out / 'PREPARE.json', owner=b.REHEARSAL_OWNER)))
    with refused('OWNER_MODE_MISMATCH'):
        b.status(out)
    # 5. a real answer on a rehearsal sheet is impossible: the evidence of a rehearsal set never says "Assino"
    (base / 'm5').mkdir()
    out, prepared, signed = w1_set(base / 'm5', families)
    authority = json.loads((out / signed['authority_name']).read_bytes())
    authority['owner_evidence'].update(channel=b.REAL_CHANNEL, owner_answer_verbatim=b.REAL_ANSWER)
    (out / signed['authority_name']).write_bytes(b.canonical(authority))
    h.rewrite_sums(out)
    with refused('OWNER_EVIDENCE_INVALID'):
        b.check(out, now=lambda: NOW)


# ---------------------------------------------------------------- determinism
def test_the_same_inputs_give_the_same_bytes(base, families):
    sets = []
    reference = h.rehearsal_reference(base)
    for name in ('a', 'b'):
        (base / name).mkdir()
        parameters = h.w1_parameters(base / name)
        out = base / name / 'rehearsal-bound'
        prepared = b.prepare(families['w1'], W1, parameters, reference, out, b.REHEARSAL, now=lambda: NOW)
        sets.append((out, prepared))
    (a, first), (c, second) = sets
    for name in ('REQUEST.BOUND.json', 'GO_SCOPE.txt', 'PARAMETERS.json', 'dispatch_once.py', 'w1_preflight_readonly.py', 'templates/GO.UNBOUND.json'):
        assert (a / name).read_bytes() == (c / name).read_bytes(), name

    def without_location(sheet):
        sheet = json.loads(json.dumps(sheet))
        for key in ('claim_root_identity', 'attempt_directory'):
            sheet.pop(key)
        return sheet
    assert without_location(first['sheet']) == without_location(second['sheet']) and first['prepare_json_sha256'] != second['prepare_json_sha256']
    # sign is a pure construction: check rebuilds every signed document from the sheet and the evidence and demands the same bytes
    signed = b.sign(a, first['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    state = b.signed_state(a)
    again = b.rebuild(state, state['fields'], json.loads(state['raws'][1])['owner_evidence'], first['prepare_json_sha256'])
    assert again['authority'] == (a / signed['authority_name']).read_bytes() and again['go'] == (a / signed['go_name']).read_bytes()
    assert again['payload'] == (a / 'FINAL_PAYLOAD.BOUND.py').read_bytes() and again['config_raw'] == (a / 'DISPATCH.BOUND.json').read_bytes()
    assert b.rebuild(state, state['fields'], json.loads(state['raws'][1])['owner_evidence'], first['prepare_json_sha256']) == again
    # the other set, signed at the same second, differs only where the claim root and the sheet enter
    other = b.sign(c, second['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    go_a, go_c = json.loads((a / signed['go_name']).read_bytes()), json.loads((c / other['go_name']).read_bytes())
    differing = {key for key in go_a if go_a[key] != go_c[key]}
    assert differing == {'authority_sha256', 'claim_root_identity', 'owner_evidence'} and signed['request_sha256'] == other['request_sha256']
    # documents are canonical JSON: one byte string per content
    for name in ('REQUEST.BOUND.json', signed['authority_name'], signed['go_name']):
        raw = (a / name).read_bytes()
        assert raw == b.canonical(json.loads(raw))
    # the launcher of the family reproduces the final payload from the four bound blobs
    rt = h.runtime_of(families['w1'], W1)
    source = (a / 'w1_preflight_readonly.py').read_bytes()
    raws = [(a / name).read_bytes() for name in ('REQUEST.BOUND.json', signed['authority_name'], signed['go_name'])]
    assert rt['launcher'].build(source, *raws, expected_payload_sha256=b.sha(source), expected_request_sha256=b.sha(raws[0]),
                                expected_authority_sha256=b.sha(raws[1]), expected_go_sha256=b.sha(raws[2])) == (a / 'FINAL_PAYLOAD.BOUND.py').read_bytes()


# ---------------------------------------------------------------- the sealed family
def test_family_seal_refusals(base, families):
    reference = h.rehearsal_reference(base)
    parameters = h.w1_parameters(base)
    counter = [0]

    def attempt(code, change, operation=W1):
        counter[0] += 1
        family = h.copy_family(families['w1'], base / ('family-%d' % counter[0]))
        change(family)
        with refused(code):
            b.prepare(family, operation, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
        assert not (base / 'rehearsal-bound').exists()

    def reseal(family):
        names = sorted(str(path.relative_to(family)) for path in family.rglob('*') if path.is_file() and path.name != 'SHA256SUMS')
        (family / 'SHA256SUMS').write_text(''.join('%s  %s\n' % (b.sha((family / name).read_bytes()), name) for name in names))
    attempt('FAMILY_NOT_FOUND', lambda family: (family / 'SHA256SUMS').unlink())
    with refused('FAMILY_NOT_FOUND'):
        b.prepare(base / 'no-such-family', W1, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    (base / 'link').symlink_to(families['w1'])
    with refused('FAMILY_NOT_FOUND'):
        b.verify_family(base / 'link')
    attempt('FAMILY_SUMS_INVALID', lambda family: (family / 'SHA256SUMS').write_bytes((family / 'SHA256SUMS').read_bytes() + b'garbage\n'))
    attempt('FAMILY_SUMS_INVALID', lambda family: (family / 'SHA256SUMS').write_bytes((family / 'SHA256SUMS').read_bytes() * 2))
    attempt('FAMILY_SUMS_INVALID', lambda family: (family / 'SHA256SUMS').write_bytes(b'\n'))
    attempt('FAMILY_SUMS_INVALID', lambda family: (family / 'SHA256SUMS').write_bytes('é\n'.encode()))
    attempt('FAMILY_SUMS_INVALID', lambda family: (family / 'SHA256SUMS').write_bytes(('a' * 64 + '  ../x\n').encode()))
    attempt('FAMILY_FILE_SET', lambda family: (family / 'extra.py').write_bytes(b'x'))
    attempt('FAMILY_FILE_SET', lambda family: (family / 'CONTRACT.txt').unlink())

    def link(family):
        (family / 'transport_once.py').unlink()
        (family / 'transport_once.py').symlink_to(families['w1'] / 'transport_once.py')
    attempt('FAMILY_FILE_SET', link)
    attempt('FAMILY_HASH', lambda family: (family / 'dispatch_once.py').write_bytes((family / 'dispatch_once.py').read_bytes() + b'\n'))
    attempt('FAMILY_HASH', lambda family: (family / 'CONTRACT.txt').write_bytes((family / 'CONTRACT.txt').read_bytes().replace(b'Nine', b'Ten')))

    def changed_and_resealed(family):
        (family / 'w1_preflight_readonly.py').write_bytes((family / 'w1_preflight_readonly.py').read_bytes() + b'\n')
        reseal(family)
    attempt('FAMILY_SEAL_NOT_ACCEPTED', changed_and_resealed)          # a consistent manifest is not enough: the seal must be a known one
    attempt('OPERATION_NOT_IN_FAMILY', lambda family: None, operation=PRECHECK)
    for bad in ('precheck', 'GO_', 'go_readonly_w1preflight_01', None, 'GO_X; rm'):
        attempt('OPERATION_NAME_INVALID', lambda family: None, operation=bad)
    # a cache directory left by a test run does not change the seal
    family = h.copy_family(families['w1'], base / 'family-with-cache')
    (family / '__pycache__').mkdir()
    (family / '__pycache__' / 'x.pyc').write_bytes(b'x')
    assert b.verify_family(family)['sums_sha256'] == b.sha((families['w1'] / 'SHA256SUMS').read_bytes())


def test_template_and_dispatcher_consistency_refusals(families):
    family = b.verify_family(families['w1'])
    op = b.select_operation(family, W1)
    rt = b.load_runtime(op['files'], op['source_name'], op['directory'])
    facts = b.dispatcher_facts(rt, op['files'])
    assert facts == {'intent_schema': 'W1PREFLIGHT01_DISPATCH_INTENT_V1', 'claim_schema': 'W1PREFLIGHT01_GO_CLAIM_V1',
                     'publication_schema': 'W1PREFLIGHT01_INTENT_PUBLICATION_V1', 'config_schema': 'W1PREFLIGHT01_DISPATCH_AUTHORIZATION_V1',
                     'dates': ['2026-10-0%d' % day for day in range(2, 10)] + ['2026-10-10']}
    assert b.profile_of(rt['source']) == 'collection' and b.template_chain(op, rt, facts)['source_sha256'] == b.sha(op['files']['w1_preflight_readonly.py'])

    def doctored(name, change):
        files = dict(op['files'])
        files[name] = change(files[name])
        return dict(op, files=files)

    def json_change(**changes):
        return lambda raw: b.canonical(dict(json.loads(raw), **changes))
    for name, change in (('GO.UNBOUND.json', json_change(status='SIGNED')), ('GO.UNBOUND.json', json_change(owner='X')),
                         ('AUTHORITY.UNBOUND.json', json_change(execution_authorized=True)), ('REQUEST.UNBOUND.json', json_change(not_before='2026-10-03T13:00:00Z')),
                         ('DISPATCH.UNBOUND.json', json_change(target='a@b')), ('DISPATCH.UNBOUND.json', json_change(watchdog_seconds=250)),
                         ('DISPATCH.UNBOUND.json', json_change(retry=True)), ('PUBLICATION_PROOF.UNBOUND.json', json_change(schema='OTHER_INTENT_PUBLICATION_V1')),
                         ('PUBLICATION_PROOF.UNBOUND.json', json_change(extra=1)), (b.UNBOUND_PAYLOAD, lambda raw: raw + b'\n'),
                         ('REQUEST.UNBOUND.json', lambda raw: raw + b' ')):
        with refused('TEMPLATE_CHAIN'):
            b.template_chain(doctored(name, change), rt, facts)
    with refused('TEMPLATE_CHAIN'):
        b.template_chain(op, dict(rt, launcher=types.SimpleNamespace(build=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('BUILD_PIN')))), facts)
    for name, change in (('GO.UNBOUND.json', lambda raw: b'[]'), ('REQUEST.UNBOUND.json', lambda raw: b'{"a":1,"a":2}'), ('DISPATCH.UNBOUND.json', lambda raw: b'{')):
        with refused('TEMPLATE_INVALID'):
            b.template_chain(doctored(name, change), rt, facts)
    # select_operation: the runtime pins of the template are the hashes of the files beside it
    files = dict(family['files'])
    files['transport_once.py'] = files['transport_once.py'] + b'\n'
    with refused('TEMPLATE_CHAIN'):
        b.select_operation(dict(family, files=files), W1)
    for change in (lambda config: config['runtime_sha256'].pop('launcher_stdin.py'), lambda config: config['runtime_sha256'].update({'x.py': 'a' * 64}),
                   lambda config: config.update(runtime_sha256=None), lambda config: config['runtime_sha256'].update({'Other-Name.py': config['runtime_sha256'].pop('w1_preflight_readonly.py')})):
        config = json.loads(family['files']['DISPATCH.UNBOUND.json'])
        change(config)
        with refused('TEMPLATE_INVALID'):
            b.select_operation(dict(family, files=dict(family['files'], **{'DISPATCH.UNBOUND.json': b.canonical(config)})), W1)
    with refused('TEMPLATE_INVALID'):
        b.select_operation(dict(family, files=dict(family['files'], **{'DISPATCH.UNBOUND.json': b'{'})), W1)
    with refused('FAMILY_FILE_SET'):
        b.select_operation(dict(family, files={name: raw for name, raw in family['files'].items() if name != 'GO.UNBOUND.json'}), W1)
    # the dispatcher's own text: one name of each kind, and exactly the date set of its source
    text = op['files']['dispatch_once.py']
    for change in (lambda raw: raw.replace(b"start.date().isoformat() in (", b"start.date().isoformat() not in ("),
                   lambda raw: raw.replace(b"'W1PREFLIGHT01_DISPATCH_INTENT_V1'", b"'OTHER_DISPATCH_INTENT_V1'", 1),
                   lambda raw: raw.replace(b"'W1PREFLIGHT01_GO_CLAIM_V1'", b"'CLAIM'"),
                   lambda raw: raw.replace(b"'READONLY_W1PREFLIGHT01_RECEIPT_V1'", b"'READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1'")):
        with refused('DISPATCHER_LITERALS'):
            b.dispatcher_facts(rt, dict(op['files'], **{'dispatch_once.py': change(text)}))
    for change in (lambda raw: raw.replace(b",'2026-10-10')", b")"), lambda raw: raw.replace(b"('2026-10-02',", b"('2026-10-01','2026-10-02',"),
                   lambda raw: raw.replace(b"'2026-10-02','2026-10-03'", b"'2026-10-03','2026-10-02'")):
        with refused('DISPATCH_DATE_LITERAL'):
            b.dispatcher_facts(rt, dict(op['files'], **{'dispatch_once.py': change(text)}))
    with refused('FAMILY_PROFILE_UNKNOWN'):
        b.profile_of(types.SimpleNamespace(authenticate=1, DATES=[]))
    with refused('RUNTIME_DOES_NOT_LOAD'):
        b.load_runtime(dict(op['files'], **{'w1_preflight_readonly.py': b'raise RuntimeError("x")\n'}), op['source_name'], op['directory'])
    with refused('RUNTIME_DOES_NOT_LOAD'):
        b.load_runtime(dict(op['files'], **{'dispatch_once.py': b'def broken(:\n'}), op['source_name'], op['directory'])
    assert 'w1_preflight_readonly' not in sys.modules or sys.modules['w1_preflight_readonly'] is not rt['source']          # sys.modules is restored
    # the four HOSTOPS01 operations are the core profile, each with its own names
    hostops = b.verify_family(families['hostops'])
    for operation, source in ((PRECHECK, 'precheck_readonly.py'), (PROVISION, 'provision_dirs.py'), ('GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01', 'install_units.py'),
                              ('GO_READONLY_SUPERVISOR_READBACK_01', 'readback_readonly.py')):
        selected = b.select_operation(hostops, operation)
        runtime = b.load_runtime(selected['files'], selected['source_name'], selected['directory'])
        assert selected['source_name'] == source and b.profile_of(runtime['source']) == 'core'
        b.template_chain(selected, runtime, b.dispatcher_facts(runtime, selected['files']))


def test_scope_sentence_units(families):
    family = b.verify_family(families['w1'])
    op = b.select_operation(family, W1)
    m = b.load_runtime(op['files'], op['source_name'], op['directory'])['source']
    rule = b.COLLECTION_SCOPE_RULES[W1]
    contract = family['files']['CONTRACT.txt'].decode('ascii')
    decisions = b.contract_decisions(contract, rule['decisions_header'])
    assert sorted(decisions) == list(range(1, 14)) and decisions[13].startswith('Two shared budgets.') and decisions[1].startswith('Nine UTC dates')
    arguments = (m, rule, contract, 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')
    assert b.collection_scope(*arguments) == b.collection_scope(*arguments) and '..' not in b.collection_scope(*arguments).replace('...', '')
    for bad in (contract.replace(rule['decisions_header'], 'OTHER HEADER'), contract + '\n' + rule['decisions_header'] + '\n1. again\n',
                contract.replace('\n13. Two shared budgets.', '\n14. Two shared budgets.'), contract.replace('\n2. Candidates in the signed request.', '\n   Candidates in the signed request.')):
        with refused('CONTRACT_DECISIONS_NOT_FOUND'):
            b.collection_scope(m, rule, bad, 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')
    with refused('CONTRACT_DECISIONS_NOT_FOUND'):
        b.collection_scope(m, dict(rule, decisions=(1, 14)), contract, 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')
    for effects in ([], ['one'] * 8, m.SIDE_EFFECTS + [5], list(reversed(m.SIDE_EFFECTS))):
        fake = types.SimpleNamespace(SIDE_EFFECTS=effects, SCOPE=m.SCOPE, OPERATION=m.OPERATION, SCOPE_SHA256=m.SCOPE_SHA256)
        with refused('SIDE_EFFECTS_NOT_FOUND'):
            b.collection_scope(fake, rule, contract, 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')
    with refused('SCOPE_SENTENCE_INVALID'):
        b.collection_scope(m, rule, contract.replace('1. Nine UTC dates', '1. Nine\tUTC dates'), 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')
    with refused('SCOPE_SENTENCE_INVALID'):
        b.collection_scope(m, rule, contract.replace('1. Nine UTC dates', '1. Nine UTC dates ' + 'x' * 24000), 'c' * 64, 's' * 64, 'p' * 64, '2026-10-03')


def test_an_operation_without_scope_rules_or_owner_text_is_refused_until_it_brings_them(base, families, monkeypatch):
    reference = h.rehearsal_reference(base)
    monkeypatch.setattr(b, 'COLLECTION_SCOPE_RULES', {})
    with refused('SCOPE_RULES_UNKNOWN_FOR_OPERATION'):
        b.prepare(families['w1'], W1, h.w1_parameters(base), reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    monkeypatch.undo()
    with refused('OWNER_SUMMARY_IS_FIXED_FOR_THIS_OPERATION'):
        b.prepare(families['w1'], W1, h.w1_parameters(base, owner_summary_pt='Resumo em português, com mais de vinte caracteres.'), reference,
                  base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    # a future operation (hostops02) is not in the table: it must bring its own Portuguese summary, which then enters the question
    monkeypatch.setattr(b, 'OWNER_TEXT_PT', {})
    with refused('OWNER_SUMMARY_MISSING'):
        b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base), reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    assert not (base / 'rehearsal-bound').exists()
    summary = 'Resumo próprio desta operação futura, escrito para o dono, em português.'
    prepared = b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, owner_summary_pt=summary), reference, base / 'rehearsal-bound',
                         b.REHEARSAL, now=lambda: NOW)
    assert summary in prepared['owner_question_pt'] and 'PEDIDO DE ASSINATURA - operação ' + PRECHECK in prepared['owner_question_pt']
    b.sign(base / 'rehearsal-bound', prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    assert b.check(base / 'rehearsal-bound', now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'


# ---------------------------------------------------------------- parameters and windows
def test_parameter_refusals_create_nothing(base, families):
    reference = h.rehearsal_reference(base)
    counter = [0]

    def attempt(code, now=NOW, family='w1', **changes):
        counter[0] += 1
        make = h.w1_parameters if family == 'w1' else h.precheck_parameters
        parameters = make(base, name='P%d.json' % counter[0], **changes)
        with refused(code):
            b.prepare(families[family], W1 if family == 'w1' else PRECHECK, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: now)
        assert not (base / 'rehearsal-bound').exists()
    with refused('PARAMETERS_UNREADABLE'):
        b.prepare(families['w1'], W1, base / 'missing.json', reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    for index, bad in enumerate((b'not json', b'[]', b'{"schema":"BIND_ONCE_PARAMETERS_V1","schema":"BIND_ONCE_PARAMETERS_V1"}')):
        (base / ('bad%d.json' % index)).write_bytes(bad)
        with refused('PARAMETERS_INVALID'):
            b.prepare(families['w1'], W1, base / ('bad%d.json' % index), reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    attempt('PARAMETERS_INVALID', schema='OTHER')
    attempt('PARAMETERS_INVALID', candidates=h.DROP)
    attempt('PARAMETERS_INVALID', label=h.DROP)
    attempt('PARAMETERS_INVALID', extra=1)
    attempt('PARAMETERS_INVALID', plan={})                         # a plan belongs to the core profile only
    attempt('PARAMETERS_INVALID', signature_model=h.DROP)
    attempt('PARAMETERS_INVALID', signature_model='OTHER')
    attempt('PARAMETERS_INVALID', signature_model=['IND'])
    attempt('PARAMETERS_INVALID', review=h.review_record(base))          # a review record belongs to a write request only
    attempt('PARAMETERS_INVALID', family='hostops', review=h.review_record(base))
    attempt('PARAMETERS_INVALID', family='hostops', candidates={})
    attempt('PARAMETERS_INVALID', family='hostops', evidence=h.DROP)
    attempt('PARAMETERS_OPERATION_MISMATCH', operation=PRECHECK)
    for label in ('Bad Label', '', 'x' * 41, '-x', 'a/b', None):
        attempt('PARAMETERS_LABEL', label=label)
    for key in ('not_before', 'not_after'):
        for value in ('2026-10-03T10:00:00-03:00', '2026-10-03T13:00:00', '2026-10-03T13:00:00.000Z', 1790000000, None):
            attempt('WINDOW_NOT_UTC_SECONDS', **{key: value})
    attempt('WINDOW_ORDER', not_after=b.zulu(NOW))
    attempt('WINDOW_ORDER', not_after=b.zulu(NOW - MIN))
    attempt('WINDOW_CROSSES_UTC_MIDNIGHT', not_before='2026-10-03T23:50:00Z', not_after='2026-10-04T00:10:00Z')          # 21:00 BRT
    attempt('WINDOW_SHORTER_THAN_WATCHDOG', not_after=b.zulu(NOW + 79 * SEC))
    attempt('WINDOW_ALREADY_UNUSABLE', now=NOW + 3 * MIN + 41 * SEC)
    attempt('DATE_NOT_IN_FAMILY_SCOPE', now=NOW, not_before='2026-10-11T13:00:00Z', not_after='2026-10-11T14:00:00Z')
    attempt('DATE_NOT_IN_FAMILY_SCOPE', now=datetime(2026, 9, 30, tzinfo=timezone.utc), not_before='2026-10-01T13:00:00Z', not_after='2026-10-01T14:00:00Z')
    attempt('DATE_NOT_IN_FAMILY_SCOPE', family='hostops', not_before='2026-10-06T13:00:00Z', not_after='2026-10-06T13:30:00Z')
    attempt('GATE_NOT_SUPPORTED_BY_THIS_PROFILE', gate_not_before=b.zulu(NOW), gate_not_after=b.zulu(NOW + 5 * MIN))
    attempt('GATE_SPAN_OVER_FAMILY_CAP', family='hostops', not_after=b.zulu(NOW + 61 * MIN))
    attempt('PLAN_KEYS_MISMATCH', family='hostops', plan={})
    attempt('FAMILY_REFUSES_THE_PLAN', family='hostops', plan=dict(h.PRECHECK_PLAN, capacity=None))
    # what the family itself refuses in a request is surfaced with the family's code, before anything is created
    for candidates, code in (({'release_directories': ['a', 'b', 'c', 'd', 'e'], 'capacity_roots': []}, 'CANDIDATES_INVALID'),
                             ({'release_directories': ['../x'], 'capacity_roots': []}, 'CANDIDATES_INVALID'), ({'release_directories': []}, 'CANDIDATES_INVALID')):
        counter[0] += 1
        with pytest.raises(b.Refused) as caught:
            b.prepare(families['w1'], W1, h.w1_parameters(base, name='P%d.json' % counter[0], candidates=candidates), reference, base / 'rehearsal-bound',
                      b.REHEARSAL, now=lambda: NOW)
        assert str(caught.value) == 'FAMILY_REFUSES_THE_REQUEST_' + code and not (base / 'rehearsal-bound').exists()
    with pytest.raises(b.Refused) as caught:
        b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, name='PX.json', plan=dict(h.PRECHECK_PLAN, image_reference='c3po/backend:rollback')),
                  reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    assert str(caught.value) == 'FAMILY_REFUSES_THE_REQUEST_IMAGE_REFERENCE_INVALID'
    h.COVERED.add('FAMILY_REFUSES_THE_REQUEST_')
    # the first and the last hour of the last UTC day of the set; signed candidates enter the request, and only their counts the sheet and the question
    prepared = b.prepare(families['w1'], W1, h.w1_parameters(base, name='day.json', not_before='2026-10-10T00:00:00Z', not_after='2026-10-10T01:00:00Z',
                                                             candidates={'release_directories': ['release-20261005'], 'capacity_roots': ['/var/lib/c3po-capacity']}),
                         reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    assert prepared['sheet']['window']['brt']['not_before'] == 'sex 09/10/2026 21:00:00 BRT' and prepared['sheet']['window']['latest_start'] == '2026-10-10T00:58:40Z'
    assert prepared['sheet']['window']['gate_span_seconds'] == 3600
    assert prepared['sheet']['candidates'] == {'capacity_roots': 1, 'release_directories': 1} and 'release-20261005' not in json.dumps(prepared['sheet'])
    assert json.loads((base / 'rehearsal-bound' / 'REQUEST.BOUND.json').read_bytes())['collection']['candidates']['release_directories'] == ['release-20261005']
    assert 'Candidatos assinados no pedido (só as contagens; os nomes estão em REQUEST.BOUND.json): capacity_roots: 1; release_directories: 1.' in prepared['owner_question_pt']
    assert 'release-20261005' not in prepared['owner_question_pt']
    last = b.prepare(families['w1'], W1, h.w1_parameters(base, name='last.json', not_before='2026-10-10T22:59:59Z', not_after='2026-10-10T23:59:59Z'),
                     reference, base / 'rehearsal-last-hour', b.REHEARSAL, now=lambda: NOW)
    assert last['sheet']['window']['latest_start'] == '2026-10-10T23:58:39Z' and last['sheet']['window']['brt']['not_after'] == 'sáb 10/10/2026 20:59:59 BRT'
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.prepare(families['w1'], W1, h.w1_parameters(base), reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.prepare(families['w1'], W1, h.w1_parameters(base), reference, base / 'missing' / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.prepare(families['w1'], W1, h.w1_parameters(base), reference, Path('rehearsal-relative'), b.REHEARSAL, now=lambda: NOW)


# ---------------------------------------------------------------- the transport reference
def test_transport_reference_refusals(base, families):
    parameters = h.w1_parameters(base)
    counter = [0]

    def attempt(code, reference, mode=b.REAL):
        with refused(code):
            b.prepare(families['w1'], W1, parameters, reference, base / ('bound' if mode == b.REAL else 'rehearsal-bound'), mode, now=lambda: NOW)
        assert not (base / 'bound').exists() and not (base / 'rehearsal-bound').exists()

    def executed(**changes):
        counter[0] += 1
        return h.executed_reference(base, families['w1'], name='executed-%d' % counter[0], **changes)
    attempt('TRANSPORT_REFERENCE_PATH', Path('relative/DISPATCH.BOUND.json'))
    attempt('TRANSPORT_REFERENCE_PATH', Path(str(base) + '/x/../DISPATCH.BOUND.json'))
    attempt('TRANSPORT_REFERENCE_UNREADABLE', base / 'missing.json')
    (base / 'big.json').write_bytes(b' ' * 65537)
    attempt('TRANSPORT_REFERENCE_UNREADABLE', base / 'big.json')
    for index, bad in enumerate((b'not json', b'[]', b'{"target":"a@b","target":"a@b"}')):
        (base / ('ref%d.json' % index)).write_bytes(bad)
        attempt('TRANSPORT_REFERENCE_SHAPE', base / ('ref%d.json' % index))
    for changes in ({'target': 'no-at-sign'}, {'target': 'Upper@host.example.net'}, {'target': 5}, {'remote_command': 'sudo -n /usr/bin/python3 -'},
                    {'ssh_key': 'path'}, {'ssh_key': {'path': 'relative', 'sha256': 'a' * 64}}, {'known_hosts': {'path': '/x', 'sha256': 'zz'}},
                    {'known_hosts': {'path': '/x', 'sha256': 'a' * 64, 'extra': 1}}, {'known_hosts': h.DROP}):
        attempt('TRANSPORT_REFERENCE_SHAPE', executed(**changes))
    for changes in ({'status': 'UNBOUND'}, {'decision': 'UNBOUND'}, {'schema': 'SOMETHING_ELSE_V1'}, {'schema': h.DROP}, {'command_sha256': None},
                    {'attempt_directory': 'relative'}, {'skip_exit': True}, {'exit': {'status': 'UNCERTAIN'}}, {'exit': {'status': 'KNOWN_REFUSAL'}},
                    {'exit': {'config_sha256': '9' * 64}}, {'exit': {'attempts': 2}}, {'exit': {'stderr_sha256': '9' * 64}}, {'exit': {'command_sha256': '9' * 64}}):
        attempt('TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG', executed(**changes))
    reference = executed()
    (reference.parent / '.dispatch-root' / 'executed-once' / 'spawn.claim').unlink()
    attempt('TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG', reference)
    reference = executed()
    (reference.parent / '.dispatch-root' / 'executed-once' / 'exit.json').write_bytes(b'not json')
    attempt('TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG', reference)
    reference = executed()
    reference.write_bytes(reference.read_bytes() + b'\n')          # the configuration edited after it ran: its exit.json names other bytes
    attempt('TRANSPORT_REFERENCE_NOT_AN_EXECUTED_CONFIG', reference)
    attempt('HOST_BINDING_NOT_REPRODUCED', executed(host_binding_sha256='9' * 64))
    attempt('COMMAND_PIN_NOT_THE_EXECUTED_ONE', executed(command_sha256='9' * 64, exit={'command_sha256': '9' * 64}))
    # the key and known-hosts files: metadata only, and nothing later than the last use
    for change, code in ((lambda path: path.unlink(), 'SSH_REFERENCE_FILE'), (lambda path: path.chmod(0o644), 'SSH_REFERENCE_FILE'),
                         (lambda path: path.write_bytes(b''), 'SSH_REFERENCE_FILE'), (lambda path: os.link(str(path), str(path) + '.second'), 'SSH_REFERENCE_FILE'),
                         (lambda path: path.write_bytes(b'x' * 65537), 'SSH_REFERENCE_FILE'),
                         (lambda path: os.utime(str(path)), 'SSH_REFERENCE_CHANGED_SINCE_LAST_USE'), (lambda path: path.chmod(0o600), 'SSH_REFERENCE_CHANGED_SINCE_LAST_USE')):
        for key in ('ssh_key', 'known_hosts'):
            reference = executed()
            change(reference.parent / key)
            attempt(code, reference)
    reference = executed()
    target = reference.parent / 'elsewhere'
    (reference.parent / 'ssh_key').rename(target)
    (reference.parent / 'ssh_key').symlink_to(target)
    attempt('SSH_REFERENCE_FILE', reference)
    real_directory = base / 'real-directory'
    real_directory.mkdir()
    (base / 'linked').symlink_to(real_directory)          # a link in the middle of the path of the key: never followed
    (real_directory / 'ssh_key').write_bytes(b'SYNTHETIC_TEST_FILE_NOT_A_KEY\n')
    (real_directory / 'ssh_key').chmod(0o600)
    attempt('SSH_REFERENCE_FILE', executed(ssh_key={'path': str(base / 'linked' / 'ssh_key'), 'sha256': b.sha(b'SYNTHETIC_TEST_FILE_NOT_A_KEY\n')}))
    # the fake reference: its marker files are checked the same way
    fake = h.rehearsal_reference(base)
    (fake.parent / 'NOT_A_KEY').chmod(0o644)
    attempt('SSH_REFERENCE_FILE', fake, b.REHEARSAL)


# ---------------------------------------------------------------- sign
def test_sign_refusals_write_nothing(base, families, monkeypatch):
    counter = [0]

    def fresh():
        counter[0] += 1
        directory = base / ('s%d' % counter[0])
        directory.mkdir()
        prepared, reference = w1_prepared(directory, families)
        return Path(prepared['bound']), prepared, reference

    def attempt(code, out, prepared, sheet=h.DROP, signed_at=h.DROP, now=NOW):
        before = modes(out)
        with refused(code):
            b.sign(out, prepared['prepare_json_sha256'] if sheet is h.DROP else sheet, b.zulu(now) if signed_at is h.DROP else signed_at, ANSWER, now=lambda: now)
        assert modes(out) == before          # nothing was created or changed by the refused call
    out, prepared, reference = fresh()
    for bad in ('xyz', 'A' * 64, '0' * 64, prepared['prepare_json_sha256'][:63], None):
        attempt('SHEET_SHA256_INVALID', out, prepared, sheet=bad)
    for bad in ('2026-10-03T10:00:00-03:00', 'now', '2026-10-03T13:00:00.1Z', None):
        attempt('SIGNED_AT_NOT_UTC_SECONDS', out, prepared, signed_at=bad)
    attempt('SHEET_IS_NOT_THE_ONE_THE_OWNER_SAW', out, prepared, sheet='f' * 64)
    attempt('SIGNATURE_BEFORE_THE_SHEET_EXISTED', out, prepared, signed_at=b.zulu(NOW - SEC))
    attempt('SIGNATURE_IN_THE_FUTURE', out, prepared, signed_at=b.zulu(NOW + 2 * SEC), now=NOW + SEC)
    attempt('WINDOW_ALREADY_UNUSABLE', out, prepared, signed_at=b.zulu(NOW + SEC), now=NOW + 3 * MIN + 41 * SEC)
    attempt('WINDOW_ALREADY_UNUSABLE', out, prepared, signed_at=b.zulu(NOW + 3 * MIN + 41 * SEC), now=NOW + 3 * MIN + 41 * SEC)
    for call in (lambda: b.sign(base / 'missing', 'a' * 64, b.zulu(NOW), ANSWER), lambda: b.sign(Path('relative'), 'a' * 64, b.zulu(NOW), ANSWER), lambda: b.check(base / 'missing'),
                 lambda: b.status(base / 'missing'), lambda: b.publish_proof(base / 'missing', '5955151654', b.zulu(NOW))):
        with refused('BOUND_NOT_FOUND'):
            call()
    (base / 'rehearsal-link').symlink_to(out)
    with refused('BOUND_NOT_FOUND'):
        b.sign(base / 'rehearsal-link', prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    (base / 'rehearsal-empty').mkdir(mode=0o700)
    with refused('BOUND_NOT_PREPARED'):
        b.sign(base / 'rehearsal-empty', 'a' * 64, b.zulu(NOW), ANSWER, now=lambda: NOW)
    # the sheet itself
    for bad in (b'not json', b'[]', b.pretty({'schema': 'OTHER'}), b.pretty(dict(prepared['sheet'], label='Bad Label')), b.pretty(dict(prepared['sheet'], files_sha256=None))):
        out, prepared, reference = fresh()
        (out / 'PREPARE.json').write_bytes(bad)
        attempt('BOUND_NOT_PREPARED', out, prepared)
    out, prepared, reference = fresh()
    (out / 'PREPARE.json').write_bytes(b.pretty(edit_json(out / 'PREPARE.json', request_sha256='9' * 64)))
    attempt('OWNER_QUESTION_CHANGED', out, prepared)          # a sheet that is not the one the question was written from
    out, prepared, reference = fresh()
    (out / 'OWNER_QUESTION.txt').write_bytes((out / 'OWNER_QUESTION.txt').read_bytes().replace('só de leitura'.encode(), 'de leitura'.encode()))
    attempt('OWNER_QUESTION_CHANGED', out, prepared)
    # privacy of the directory
    out, prepared, reference = fresh()
    out.chmod(0o755)
    attempt('BOUND_NOT_PRIVATE', out, prepared)
    out, prepared, reference = fresh()
    (out / 'templates').chmod(0o750)
    attempt('BOUND_NOT_PRIVATE', out, prepared)
    out, prepared, reference = fresh()
    (out / 'REQUEST.BOUND.json').chmod(0o644)
    attempt('BOUND_CHANGED', out, prepared)
    # the file set and its bytes
    out, prepared, reference = fresh()
    (out / 'stray.txt').write_bytes(b'x')
    attempt('BOUND_FILE_SET_OR_ALREADY_SIGNED', out, prepared)
    out, prepared, reference = fresh()
    (out / 'transport_once.py').unlink()
    attempt('BOUND_FILE_SET_OR_ALREADY_SIGNED', out, prepared)
    out, prepared, reference = fresh()
    (out / 'PUBLICATION.PROOF.json').write_bytes(b'{}')
    attempt('BOUND_FILE_SET_OR_ALREADY_SIGNED', out, prepared)
    for name in ('REQUEST.BOUND.json', 'w1_preflight_readonly.py', 'dispatch_once.py', 'launcher_stdin.py', 'transport_once.py', 'GO_SCOPE.txt', 'PARAMETERS.json',
                 'templates/GO.UNBOUND.json', 'templates/DISPATCH.UNBOUND.json'):
        out, prepared, reference = fresh()
        (out / name).write_bytes((out / name).read_bytes() + b' ')
        attempt('BOUND_CHANGED', out, prepared)
    # the claim root
    out, prepared, reference = fresh()
    (out / '.dispatch-root' / 'something').write_bytes(b'x')
    attempt('CLAIM_ROOT_CHANGED_OR_USED', out, prepared)
    out, prepared, reference = fresh()
    (out / '.dispatch-root').chmod(0o755)
    attempt('CLAIM_ROOT_NOT_PRIVATE', out, prepared)
    out, prepared, reference = fresh()
    (out / '.dispatch-root').rmdir()
    (out / '.dispatch-root').mkdir(mode=0o700)          # same path, another directory: not the root the owner signed over
    if b.claim_identity(out / '.dispatch-root') != prepared['sheet']['claim_root_identity']:
        attempt('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED', out, prepared)
    out, prepared, reference = fresh()
    moved = base / 'moved'
    moved.mkdir()
    out.rename(moved / out.name)          # the whole prepared set moved: the claim root path is no longer the signed one
    attempt('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED', moved / out.name, prepared)
    # the binder and the reference must be the ones of the prepare
    out, prepared, reference = fresh()
    original = b.binder_identity
    monkeypatch.setattr(b, 'binder_identity', lambda: ({'binder_sha256': '9' * 64, 'accepted_seals_sha256': original()[0]['accepted_seals_sha256']}, original()[1]))
    attempt('BINDER_CHANGED_SINCE_PREPARE', out, prepared)
    monkeypatch.undo()
    out, prepared, reference = fresh()
    reference.write_bytes(reference.read_bytes() + b'\n')
    attempt('TRANSPORT_REFERENCE_PIN', out, prepared)
    out, prepared, reference = fresh()
    reference.unlink()
    attempt('TRANSPORT_REFERENCE_UNREADABLE', out, prepared)
    out, prepared, reference = fresh()
    (reference.parent / 'NOT_KNOWN_HOSTS').chmod(0o644)
    attempt('SSH_REFERENCE_FILE', out, prepared)
    out, prepared, reference = fresh()
    (out / 'PREPARE.json').write_bytes(b.pretty(edit_json(out / 'PREPARE.json', transport_reference=None)))
    (out / 'OWNER_QUESTION.txt').write_bytes(b.question_text(json.loads((out / 'PREPARE.json').read_bytes()), b.sha((out / 'PREPARE.json').read_bytes())))
    attempt('BOUND_CHANGED', out, prepared, sheet=b.sha((out / 'PREPARE.json').read_bytes()))
    out, prepared, reference = fresh()
    sheet = edit_json(out / 'PREPARE.json', host_binding_sha256='9' * 64)
    (out / 'PREPARE.json').write_bytes(b.pretty(sheet))
    (out / 'OWNER_QUESTION.txt').write_bytes(b.question_text(sheet, b.sha(b.pretty(sheet))))
    attempt('HOST_BINDING_NOT_REPRODUCED', out, prepared, sheet=b.sha(b.pretty(sheet)))
    # a proof of the family that fails, and a written set the dispatcher would not read: both stop the signature
    out, prepared, reference = fresh()
    monkeypatch.setattr(b, 'dry_dispatch', lambda *args: 'LOCAL_PIN')
    with pytest.raises(b.Refused) as caught:
        b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    assert str(caught.value) == 'PROOF_FAILED_DISPATCHER_ACCEPTS_AT_NOT_BEFORE' and not (out / 'DISPATCH.BOUND.json').exists()
    h.COVERED.add('PROOF_FAILED_')
    monkeypatch.undo()
    real_dry = b.dry_dispatch
    monkeypatch.setattr(b, 'dry_dispatch', lambda rt, path, digest, clock, memory, ssh: real_dry(rt, path, digest, clock, memory, ssh) if memory else 'LOCAL_PERMISSIONS')
    with refused('WRITTEN_SET_CHECK'):
        b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    monkeypatch.undo()
    assert (out / 'SHA256SUMS').exists()          # that refusal comes after the writes; the set is complete and check decides
    # sign runs once
    out, prepared, reference = fresh()
    b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
    attempt('BOUND_FILE_SET_OR_ALREADY_SIGNED', out, prepared)
    assert b.check(out, now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'


def test_a_signature_given_before_the_window_opens_is_bound_and_checked(base, families):
    """A request signed on the eve: nothing depends on the real clock being inside the window."""
    reference = h.rehearsal_reference(base)
    eve = datetime(2026, 10, 4, 15, tzinfo=timezone.utc)          # Sunday 12:00 BRT
    parameters = h.w1_parameters(base, not_before='2026-10-05T08:00:00Z', not_after='2026-10-05T08:20:00Z')
    out, prepared, signed = h.bind(base, families['w1'], W1, parameters, reference, now=eve)
    assert prepared['sheet']['window']['brt']['not_before'] == 'seg 05/10/2026 05:00:00 BRT' and signed['signed_at_utc'] == '2026-10-04T15:00:00Z'
    assert b.check(out, families['w1'], now=lambda: eve)['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN'
    with pytest.raises(ValueError, match='DISPATCH_WINDOW'):
        h.dispatcher_prepare(out, eve)
    assert list((out / '.dispatch-root').iterdir()) == []
    assert h.dispatcher_prepare(out, datetime(2026, 10, 5, 8, 0, 1, tzinfo=timezone.utc))['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'


# ---------------------------------------------------------------- check, on a signed set
def test_check_refusals(base, families, monkeypatch):
    counter = [0]

    def fresh(real=False):
        counter[0] += 1
        directory = base / ('c%d' % counter[0])
        directory.mkdir()
        return real_set(directory, families)[:3] if real else w1_set(directory, families)
    prepared, reference = w1_prepared(base, families)
    with refused('BOUND_FILE_SET_NOT_SIGNED'):
        b.check(Path(prepared['bound']), now=lambda: NOW)
    with refused('BOUND_FILE_SET_NOT_SIGNED'):
        b.status(Path(prepared['bound']))
    out, prepared, signed = fresh()
    (out / 'stray').write_bytes(b'x')
    with refused('BOUND_FILE_SET_NOT_SIGNED'):
        b.check(out, now=lambda: NOW)
    for change in (lambda raw: raw + b'garbage\n', lambda raw: raw.replace(raw[:64], b'9' * 64), lambda raw: raw + raw.splitlines(True)[0], lambda raw: b''.join(raw.splitlines(True)[1:])):
        out, prepared, signed = fresh()
        (out / 'SHA256SUMS').write_bytes(change((out / 'SHA256SUMS').read_bytes()))
        with refused('BOUND_SUMS_INVALID'):
            b.check(out, now=lambda: NOW)
    for name in ('dispatch_once.py', 'REQUEST.BOUND.json', 'templates/REQUEST.UNBOUND.json'):
        out, prepared, signed = fresh()
        (out / name).write_bytes((out / name).read_bytes() + b' ')
        h.rewrite_sums(out)
        with refused('BOUND_CHANGED'):
            b.check(out, now=lambda: NOW)
    out, prepared, signed = fresh()
    (out / 'CLAIM_ROOT_IDENTITY.json').write_bytes(b.pretty({'path': '/x', 'device': 1, 'inode': 1}))
    h.rewrite_sums(out)
    with refused('BOUND_CHANGED'):
        b.check(out, now=lambda: NOW)
    for raw in (b'[]', b.pretty({'schema': 'X'})):
        out, prepared, signed = fresh()
        (out / 'DISPATCH.BOUND.json').write_bytes(raw)
        h.rewrite_sums(out)
        with refused('BOUND_CHANGED'):
            b.check(out, now=lambda: NOW)
    out, prepared, signed = fresh()
    (out / signed['authority_name']).write_bytes(b'not json')
    h.rewrite_sums(out)
    with refused('BOUND_CHANGED'):
        b.check(out, now=lambda: NOW)
    # the owner evidence carried by the signed documents
    for change in (lambda evidence: evidence.update(signed_at_utc='2026-10-03T12:59:59Z'), lambda evidence: evidence.update(signed_at_utc='yesterday'),
                   lambda evidence: evidence.update(prepare_sheet_sha256='9' * 64), lambda evidence: evidence.pop('channel'),
                   lambda evidence: evidence.update(owner_answer_verbatim='sim')):
        out, prepared, signed = fresh()
        authority = json.loads((out / signed['authority_name']).read_bytes())
        change(authority['owner_evidence'])
        (out / signed['authority_name']).write_bytes(b.canonical(authority))
        h.rewrite_sums(out)
        with refused('OWNER_EVIDENCE_INVALID'):
            b.check(out, now=lambda: NOW)
    out, prepared, signed = fresh()
    (out / signed['authority_name']).write_bytes(b.canonical(edit_json(out / signed['authority_name'], owner_evidence='free text')))
    h.rewrite_sums(out)
    with refused('OWNER_EVIDENCE_INVALID'):
        b.check(out, now=lambda: NOW)
    # documents that are consistent with each other but are not what sign builds
    for name, change in (('go', lambda go: go.update(scope=go['scope'] + ' and anything else')), ('go', lambda go: go.update(not_after='2026-10-03T13:30:00Z')),
                         ('authority', lambda authority: authority.update(decision='REJECTED')), ('config', lambda config: config.update(watchdog_seconds=90)),
                         ('config', lambda config: config.update(attempt_directory=config['attempt_directory'] + '-two')),
                         ('config', lambda config: config.update(command_sha256='9' * 64)), ('payload', None)):
        out, prepared, signed = fresh()
        path = out / {'go': signed['go_name'], 'authority': signed['authority_name'], 'config': 'DISPATCH.BOUND.json', 'payload': 'FINAL_PAYLOAD.BOUND.py'}[name]
        if change is None:
            path.write_bytes(path.read_bytes() + b'\n')
        else:
            value = json.loads(path.read_bytes())
            change(value)
            path.write_bytes(b.pretty(value) if name == 'config' else b.canonical(value))
        h.rewrite_sums(out)
        with refused('NOT_THE_DETERMINISTIC_CONSTRUCTION'):
            b.check(out, now=lambda: NOW)
    out, prepared, signed = fresh(real=True)
    config = json.loads((out / 'DISPATCH.BOUND.json').read_bytes())
    config['known_hosts'] = dict(config['known_hosts'], sha256='9' * 64)
    (out / 'DISPATCH.BOUND.json').write_bytes(b.pretty(config))
    h.rewrite_sums(out)
    with refused('HOST_BINDING_NOT_REPRODUCED'):
        b.check(out, now=lambda: NOW)
    # the family given to check must be the one the set was bound from
    out, prepared, signed = fresh()
    with refused('FAMILY_IS_NOT_THE_ONE_BOUND'):
        b.check(out, families['hostops'], now=lambda: NOW)
    monkeypatch.setattr(b, 'COLLECTION_SCOPE_RULES', {W1: dict(b.COLLECTION_SCOPE_RULES[W1], title='another title')})
    with refused('FAMILY_IS_NOT_THE_ONE_BOUND'):          # a scope sentence that is not the one this binder derives from that family
        b.check(out, families['w1'], now=lambda: NOW)
    monkeypatch.undo()
    with refused('FAMILY_NOT_FOUND'):
        b.check(out, base / 'no-family', now=lambda: NOW)
    # a key or known-hosts file that is gone or no longer private: the dispatcher would refuse, and check says so
    out, prepared, signed = fresh()
    config = json.loads((out / 'DISPATCH.BOUND.json').read_bytes())
    Path(config['ssh_key']['path']).chmod(0o644)
    with pytest.raises(b.Refused) as caught:
        b.check(out, now=lambda: NOW)
    assert str(caught.value) == 'PROOF_FAILED_DISPATCHER_ACCEPTS_AT_NOT_BEFORE'
    # the local run of the final payload
    out, prepared, signed = fresh()
    monkeypatch.setattr(b.subprocess, 'run', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('no interpreter')))
    with refused('PAYLOAD_LOCAL_RUN_FAILED'):
        b.check(out, now=lambda: NOW)
    for done in (types.SimpleNamespace(returncode=0, stdout=b'{"status":"REFUSED","code":"REQUEST_OR_EXECUTOR_UNBOUND"}', stderr=b''),
                 types.SimpleNamespace(returncode=1, stdout=b'{"status":"REFUSED","code":"REQUEST_OR_EXECUTOR_UNBOUND"}', stderr=b'warning'),
                 types.SimpleNamespace(returncode=1, stdout=b'{"status":"REFUSED","code":"PIN_MISMATCH"}', stderr=b''),
                 types.SimpleNamespace(returncode=1, stdout=b'not json', stderr=b''), types.SimpleNamespace(returncode=1, stdout=b'[]', stderr=b'')):
        monkeypatch.setattr(b.subprocess, 'run', lambda *args, done=done, **kwargs: done)
        with refused('PAYLOAD_LOCAL_RUN_UNEXPECTED'):
            b.check(out, now=lambda: NOW)
    monkeypatch.undo()
    assert list((out / '.dispatch-root').iterdir()) == [] and b.check(out, now=lambda: NOW)['wrote_nothing'] is True


def test_dry_dispatch_stops_at_the_claim_and_never_opens_the_connection_files(base, families):
    out, prepared, signed = w1_set(base, families)
    state = b.signed_state(out)
    config = state['config']
    ssh_paths = (config['ssh_key']['path'], config['known_hosts']['path'])
    path = str(out / 'DISPATCH.BOUND.json')
    assert b.dry_dispatch(state['rt'], path, signed['config_sha256'], NOW, {}, ssh_paths) == 'ACCEPTED_UP_TO_THE_CLAIM'
    assert list((out / '.dispatch-root').iterdir()) == []
    assert b.dry_dispatch(state['rt'], path, '9' * 64, NOW, {}, ssh_paths) == 'LOCAL_PIN'          # the config hash is the trust anchor
    assert b.dry_dispatch(state['rt'], path, signed['config_sha256'], NOW, {path: b'x'}, ssh_paths) == 'LOCAL_PIN'
    assert b.dry_dispatch(state['rt'], path, 'zz', NOW, {path: state['config_raw']}, ssh_paths) == 'LOCAL_PIN_UNBOUND'
    # the module is left as it was: its own read and os are back
    d = state['rt']['dispatch']
    assert d.os is os and d.read.__module__ == 'dispatch_once'
    # the real dispatcher, undisturbed, does create the claim: the dry run stopped exactly before it
    assert h.dispatcher_prepare(out, NOW + SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    assert b.dry_dispatch(b.signed_state(out)['rt'], path, signed['config_sha256'], NOW + 2 * SEC, {}, ssh_paths) == 'ACCEPTED_UP_TO_THE_CLAIM'
    proxy = b.OsProxy(os)
    for call in (lambda: proxy.open(str(out / 'x'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), lambda: proxy.open(str(out / 'SHA256SUMS'), os.O_RDWR),
                 lambda: proxy.mkdir(str(out / 'd')), lambda: proxy.write(1, b'x')):
        with pytest.raises(b.DryStop):
            call()
    descriptor = proxy.open(str(out / 'SHA256SUMS'), os.O_RDONLY)
    os.close(descriptor)
    assert not (out / 'x').exists() and not (out / 'd').exists()


# ---------------------------------------------------------------- publication proof
def test_publish_proof_refusals(base, families):
    counter = [0]

    def prepared_set():
        counter[0] += 1
        directory = base / ('p%d' % counter[0])
        directory.mkdir()
        out, prepared, signed = w1_set(directory, families)
        intent = h.dispatcher_prepare(out, NOW + 10 * SEC)
        return out, signed, intent, out / '.dispatch-root' / 'attempt-once'

    def attempt(code, out, comment=b.REHEARSAL_PUBLICATION, created=NOW + 11 * SEC, now=NOW + 12 * SEC, name='PUBLICATION.PROOF.json'):
        with refused(code):
            b.publish_proof(out, comment, created if type(created) is str else b.zulu(created), name, now=lambda: now)
        assert not list(out.glob('PUBLICATION.PROOF*'))
    out, signed, intent, attempt_directory = prepared_set()
    for name in ('proof.json', 'PUBLICATION.PROOF.R1.json', 'PUBLICATION.PROOF.R10.json', '../PUBLICATION.PROOF.json', 'PUBLICATION.PROOF.json.bak', None):
        attempt('PROOF_NAME_INVALID', out, name=name)
    for created in ('2026-10-03T10:00:11-03:00', '2026-10-03T13:00:11', '13:00:11'):
        attempt('CREATED_AT_NOT_UTC_SECONDS', out, created=created)
    attempt('REHEARSAL_SET_WITH_A_REAL_PUBLICATION', out, comment='5955151654')
    attempt('PUBLISHED_BEFORE_THE_INTENT', out, created=NOW + 9 * SEC)          # use the creation time of the comment, which follows the intent
    attempt('PUBLISHED_IN_THE_FUTURE', out, created=NOW + 13 * SEC)
    attempt('WINDOW_ALREADY_UNUSABLE', out, now=NOW + 3 * MIN + 41 * SEC)
    out, signed, intent, attempt_directory = prepared_set()
    claim = out / '.dispatch-root' / ('.go-%s.claim' % signed['go_sha256'])
    claim.write_bytes(claim.read_bytes().replace(signed['config_sha256'].encode(), b'9' * 64))
    attempt('CLAIM_IS_NOT_OF_THIS_CONFIG', out)
    out, signed, intent, attempt_directory = prepared_set()
    (attempt_directory / 'intent.json').chmod(0o644)
    attempt('INTENT_UNREADABLE', out)
    for change in (lambda value: value.update(go_sha256='9' * 64), lambda value: value.update(schema='SUPERVISOR_HOSTFACTS_DISPATCH_INTENT_V1'),
                   lambda value: value.update(attempts=2), lambda value: value.update(started_at=None), lambda value: value.update(started_at='2026-10-03T12:59:59+00:00'),
                   lambda value: value.update(started_at='not a time'), lambda value: value.update(extra=1)):
        out, signed, intent, attempt_directory = prepared_set()
        value = json.loads((attempt_directory / 'intent.json').read_bytes())
        change(value)
        (attempt_directory / 'intent.json').write_bytes(b.canonical(value))
        attempt('INTENT_DOES_NOT_BIND_THIS_SET', out)
    out, signed, intent, attempt_directory = prepared_set()
    (attempt_directory / 'intent.json').write_bytes(b'[]')
    attempt('INTENT_DOES_NOT_BIND_THIS_SET', out)
    out, signed, intent, attempt_directory = prepared_set()
    (attempt_directory / 'stray').write_bytes(b'x')
    attempt('ATTEMPT_NOT_AWAITING_PUBLICATION', out)
    # the proof the binder writes is the one the family's dispatcher accepts, and no other intent hash passes
    out, signed, intent, attempt_directory = prepared_set()
    proof = b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW + 11 * SEC), now=lambda: NOW + 12 * SEC)
    result = h.dispatcher_resume(out, proof, NOW + 13 * SEC, h.fixed_transport({'status': 'KNOWN_REFUSAL', 'retry_allowed': False}, b'{"status":"REFUSED"}\n'))
    assert result['status'] == 'KNOWN_REFUSAL' and (attempt_directory / 'spawn.claim').exists()


# ---------------------------------------------------------------- defensive limits, reached through substitution
def test_limits_that_the_sealed_families_cannot_reach_are_still_refusals(base, families, monkeypatch):
    reference = h.rehearsal_reference(base)
    parameters = h.w1_parameters(base)
    real_load = b.load_runtime

    def with_launcher(build):
        def load(sources, source_name, directory):
            rt = real_load(sources, source_name, directory)
            original = rt['launcher'].build

            def patched(source, request, *rest, **pins):
                return build(original, source, request, *rest, **pins) if b'"status":"BOUND"' in request else original(source, request, *rest, **pins)
            rt['launcher'] = types.SimpleNamespace(build=patched)
            return rt
        return load
    monkeypatch.setattr(b, 'load_runtime', with_launcher(lambda original, *args, **pins: (_ for _ in ()).throw(ValueError('BUILD_SIZE'))))
    with refused('LAUNCHER_REFUSES_TO_BUILD'):
        b.prepare(families['w1'], W1, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    monkeypatch.setattr(b, 'load_runtime', with_launcher(lambda original, *args, **pins: b'x' * (2 * 1024 * 1024 + 1)))
    with refused('FINAL_PAYLOAD_TOO_LARGE'):
        b.prepare(families['w1'], W1, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    monkeypatch.undo()
    real_pretty = b.pretty
    monkeypatch.setattr(b, 'pretty', lambda value: real_pretty(value) + b' ' * 65536 if type(value) is dict and 'attempt_directory' in value else real_pretty(value))
    with refused('CONFIG_TOO_LARGE'):
        b.prepare(families['w1'], W1, parameters, reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    monkeypatch.undo()
    assert not (base / 'rehearsal-bound').exists()
    # a request beyond the 65536 bytes every family decodes
    family = b.verify_family(families['w1'])
    op = b.select_operation(family, W1)
    rt = b.load_runtime(op['files'], op['source_name'], op['directory'])
    template = b.template_chain(op, rt, b.dispatcher_facts(rt, op['files']))
    window = {'start': NOW, 'end': NOW + 5 * MIN, 'gate_start': NOW, 'gate_end': NOW + 5 * MIN}
    request, raw = b.bind_request('collection', template, rt['source'], {'candidates': {'release_directories': [], 'capacity_roots': []}}, window, 'a' * 64, None, None)
    assert len(raw) < 65536
    with refused('REQUEST_NOT_CANONICAL_OR_TOO_LARGE'):
        b.bind_request('collection', template, rt['source'], {'candidates': {'release_directories': ['x' * 70000], 'capacity_roots': []}}, window, 'a' * 64, None, None)
    for change in ({'dates': ['2026-10-02']}, {'collection': None}, {'collection': dict(template['request']['collection'], status='BOUND')},
                   {'collection': dict(template['request']['collection'], window={'not_before': 'x', 'expires_at': None})}):
        with refused('TEMPLATE_INVALID'):
            b.bind_request('collection', dict(template, request=dict(template['request'], **change)), rt['source'], {'candidates': {}}, window, 'a' * 64, None, None)
    # a target the family's dispatcher would not accept in its command
    fields = {'target': 'not a target', 'remote_command': b.REMOTE_COMMAND, 'ssh_key': {'path': '/k', 'sha256': 'a' * 64}, 'known_hosts': {'path': '/h', 'sha256': 'b' * 64}}
    with refused('DISPATCHER_REFUSES_THE_COMMAND'):
        b.bind_config(template, rt, b.REHEARSAL, b.REHEARSAL_OWNER, 'a' * 64, window, fields, {'path': '/r', 'device': 1, 'inode': 1}, '/r/x-once', '/b',
                      {key: key for key in b.BLOBS}, {key: 'a' * 64 for key in b.BLOBS}, 'ref')
    # templates whose key sets are not the family's: a member the binder sets must already be a member of the template
    evidence = b.owner_evidence('collection', b.REHEARSAL, b.zulu(NOW), 'a' * 64)
    missing = {key: value for key, value in template['authority'].items() if key != 'decision'}
    with refused('TEMPLATE_INVALID'):
        b.bind_authority('collection', dict(template, authority=missing), rt['source'], b.REHEARSAL_OWNER, 'a' * 64, window, 'b' * 64, evidence, None)
    missing = {key: value for key, value in template['go'].items() if key != 'action'}
    with refused('TEMPLATE_INVALID'):
        b.bind_go('collection', dict(template, go=missing), rt['source'], b.REHEARSAL_OWNER, 'a' * 64, window, 'b' * 64, 'c' * 64,
                  {'path': '/r', 'device': 1, 'inode': 1}, evidence, {}, None, 'scope', None)
    with refused('TEMPLATE_INVALID'):
        b.bind_config(dict(template, config={key: value for key, value in template['config'].items() if key != 'latest_start'}), rt, b.REHEARSAL,
                      b.REHEARSAL_OWNER, 'a' * 64, window, dict(fields, target=b.REHEARSAL_TARGET), {'path': '/r', 'device': 1, 'inode': 1}, '/r/x-once', '/b',
                      {key: key for key in b.BLOBS}, {key: 'a' * 64 for key in b.BLOBS}, 'ref')
    # the core profile: the three documents have exactly the key sets of the family
    hostops = b.verify_family(families['hostops'])
    selected = b.select_operation(hostops, PRECHECK)
    core = b.load_runtime(selected['files'], selected['source_name'], selected['directory'])
    core_template = b.template_chain(selected, core, b.dispatcher_facts(core, selected['files']))
    m = core['source']
    for kind in ('request', 'authority', 'go'):
        extended = dict(core_template, **{kind: dict(core_template[kind], extra=None)})
        with refused('TEMPLATE_INVALID'):
            if kind == 'request':
                b.bind_request('core', extended, m, {}, window, 'a' * 64, [], dict(h.PRECHECK_PLAN))
            elif kind == 'authority':
                b.bind_authority('core', extended, m, b.REHEARSAL_OWNER, 'a' * 64, window, 'b' * 64, 'evidence', {})
            else:
                b.bind_go('core', extended, m, b.REHEARSAL_OWNER, 'a' * 64, window, 'b' * 64, 'c' * 64, {'path': '/r', 'device': 1, 'inode': 1}, 'evidence', {},
                          {}, m.SCOPE_STATEMENT, 'PRECHECK_ALL_OBSERVED')
    with refused('TEMPLATE_INVALID'):          # the scope statement of a core GO is the constant of its source, never free text
        b.bind_go('core', core_template, m, b.REHEARSAL_OWNER, 'a' * 64, window, 'b' * 64, 'c' * 64, {'path': '/r', 'device': 1, 'inode': 1}, 'evidence', {},
                  {}, m.SCOPE_STATEMENT + ' and more', 'PRECHECK_ALL_OBSERVED')


# ---------------------------------------------------------------- command line
def run_cli(*arguments):
    done = subprocess.run([sys.executable, '-B', str(h.BIND / 'bind_once.py')] + [str(item) for item in arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=120)
    return done.returncode, json.loads(done.stdout), done.stderr


def test_command_line_refusals_are_one_json_object_exit_2_and_never_a_traceback(base, families, capsys, monkeypatch):
    reference = h.rehearsal_reference(base)
    code, answer, err = run_cli('sign', '--bound', base / 'missing', '--sheet-sha256', 'a' * 64, '--signed-at', '2026-10-03T13:00:00Z', '--owner-answer', ANSWER)
    assert (code, answer, err) == (2, {'status': 'REFUSED', 'code': 'BOUND_NOT_FOUND', 'created_by_this_run': [], 'note': 'Nothing was written by this run.'}, b'')
    for arguments in (('check', '--bound', base / 'missing'), ('status', '--bound', base / 'missing'),
                      ('publish-proof', '--bound', base / 'missing', '--comment-id', '5955151654', '--created-at', '2026-10-03T13:00:00Z'),
                      ('prepare', '--family', base / 'missing', '--operation', W1, '--params', base / 'p.json', '--reference', reference, '--out', base / 'rehearsal-x', '--mode', 'rehearsal'),
                      ('rehearsal-reference', '--out', base / 'not-so-named')):
        code, answer, err = run_cli(*arguments)
        assert code == 2 and answer['status'] == 'REFUSED' and b.re.fullmatch(b.CODE, answer['code']) and err == b'' and answer['created_by_this_run'] == []
    # a refusal after the directory was created says what exists
    parameters = h.w1_parameters(base, not_before='2026-10-03T13:00:00Z', not_after='2026-10-03T13:05:00Z')
    done = subprocess.run([sys.executable, '-B', str(h.BIND / 'bind_once.py'), 'prepare', '--family', str(families['w1'])], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert done.returncode == 2 and b'Traceback' not in done.stderr          # argparse usage error, not a traceback
    # an unforeseen error is reported by type only
    monkeypatch.setattr(b, 'verify_family', lambda directory: (_ for _ in ()).throw(RuntimeError('/secret/path must not be printed')))
    capsys.readouterr()
    code = b.main(['prepare', '--family', str(families['w1']), '--operation', W1, '--params', str(parameters), '--reference', str(reference),
                   '--out', str(base / 'rehearsal-y'), '--mode', 'rehearsal'])
    printed = capsys.readouterr()
    answer = json.loads(printed.out)
    assert code == 2 and answer['code'] == 'UNEXPECTED_RuntimeError' and '/secret/path' not in printed.out + printed.err
    # a refusal after the first creation says what this run had created
    monkeypatch.undo()
    monkeypatch.setattr(b, 'proofs', lambda *args, **kwargs: (_ for _ in ()).throw(b.Refused('PROOF_FAILED_SYNTHETIC')))
    parameters = h.w1_parameters(base, name='future.json', not_before='2026-10-10T23:00:00Z', not_after='2026-10-10T23:59:59Z')
    code = b.main(['prepare', '--family', str(families['w1']), '--operation', W1, '--params', str(parameters), '--reference', str(reference),
                   '--out', str(base / 'rehearsal-z'), '--mode', 'rehearsal'])
    answer = json.loads(capsys.readouterr().out)
    if answer['code'] == 'PROOF_FAILED_SYNTHETIC':          # (after 2026-10-10 the window itself is refused first, and nothing is created)
        assert code == 2 and 'rehearsal-z' in answer['created_by_this_run'] and 'REQUEST.BOUND.json' in answer['created_by_this_run']
        assert 'had already created' in answer['note'] and not (base / 'rehearsal-z' / 'PREPARE.json').exists()
        with refused('BOUND_NOT_PREPARED'):          # a directory without its sheet can never be signed
            b.sign(base / 'rehearsal-z', 'a' * 64, '2026-10-10T23:00:00Z', ANSWER)


def test_command_line_flow_in_real_time_when_today_is_inside_the_date_set(base, families):
    """prepare, sign, check, status through the command line with the real clock. The families are dated: outside
    2026-10-02..2026-10-10 UTC this test has nothing it can bind and is skipped."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    end = min(now + timedelta(minutes=30), now.replace(hour=23, minute=59, second=59))
    if now.date().isoformat() not in ['2026-10-0%d' % day for day in range(2, 10)] + ['2026-10-10'] or (end - now).total_seconds() < 200:
        pytest.skip('today is outside the date set of the W1 family, or too close to midnight UTC')
    reference = h.rehearsal_reference(base)
    parameters = h.w1_parameters(base, not_before=b.zulu(now), not_after=b.zulu(end))
    out = base / 'rehearsal-bound'
    code, prepared, err = run_cli('prepare', '--family', families['w1'], '--operation', W1, '--params', parameters, '--reference', reference, '--out', out, '--mode', 'rehearsal')
    assert code == 0 and err == b'' and prepared['status'] == 'PREPARED_AWAITING_OWNER_SIGNATURE'
    code, refusal, err = run_cli('sign', '--bound', out, '--sheet-sha256', '9' * 64, '--signed-at', prepared['sheet']['prepared_at_utc'], '--owner-answer', ANSWER)
    assert code == 2 and refusal['code'] == 'SHEET_IS_NOT_THE_ONE_THE_OWNER_SAW'
    for answer in ('Assino', 'sim', ''):          # a rehearsal set never takes the owner's word, nor any other answer
        code, refusal, err = run_cli('sign', '--bound', out, '--sheet-sha256', prepared['prepare_json_sha256'], '--signed-at', prepared['sheet']['prepared_at_utc'],
                                     '--owner-answer', answer)
        assert code == 2 and refusal['code'] == 'OWNER_ANSWER_IS_NOT_THE_SIGNATURE' and refusal['created_by_this_run'] == []
    done = subprocess.run([sys.executable, '-B', str(h.BIND / 'bind_once.py'), 'sign', '--bound', str(out), '--sheet-sha256', prepared['prepare_json_sha256'],
                           '--signed-at', prepared['sheet']['prepared_at_utc']], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert done.returncode == 2 and b'--owner-answer' in done.stderr and not (out / 'DISPATCH.BOUND.json').exists()          # the answer is not optional
    code, signed, err = run_cli('sign', '--bound', out, '--sheet-sha256', prepared['prepare_json_sha256'], '--signed-at', prepared['sheet']['prepared_at_utc'],
                                '--owner-answer', ANSWER)
    assert code == 0 and signed['status'] == 'BOUND_NOT_DISPATCHED' and signed['owner_answer_verbatim'] == ANSWER
    code, checked, err = run_cli('check', '--bound', out, '--family', families['w1'])
    assert code == 0 and checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['a_new_dispatcher_prepare_would_reach_the_claim_and'] == 'CREATE_IT'
    # the printed command carries a placeholder for the pycache prefix: it is run as block 6 of the runbook runs it, with a fresh empty directory
    assert signed['prepare_command'][:4] == ['/usr/bin/python3', '-B', '-X', 'pycache_prefix=' + b.PYCACHE_PLACEHOLDER]
    fresh = base / 'pycache-prefix'
    fresh.mkdir(mode=0o700)
    command = [item.replace(b.PYCACHE_PLACEHOLDER, str(fresh)) for item in signed['prepare_command']]
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin'}, timeout=120)
    assert done.returncode == 2 and json.loads(done.stdout)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN' and list(fresh.iterdir()) == []
    code, report, err = run_cli('status', '--bound', out)
    assert code == 1 and report['status'] == 'PREPARED_AWAITING_PUBLICATION' and report['claim_root_read'] == 'OF_THIS_DIRECTORY'
    # check after the dispatcher prepare: valid, but the claim exists, and the exit code says the prepare cannot be run again
    code, checked, err = run_cli('check', '--bound', out, '--family', families['w1'])
    assert code == 1 and checked['verdict'] == 'VALID_ALREADY_PREPARED' and checked['window_verdict'] == 'VALID_WINDOW_OPEN'
    assert checked['a_new_dispatcher_prepare_would_reach_the_claim_and'] == 'BE_REFUSED' and checked['attempt_phase'] == 'PREPARED_AWAITING_PUBLICATION'


# ---------------------------------------------------------------- every refusal code of the binder was exercised
def refusal_codes_of_the_source():
    tree = ast.parse(Path(b.__file__).read_text(encoding='utf-8'))
    positions = {'need': 1, 'Refused': 0, 'read_file': 2, 'strict_json': 1, 'parse_utc': 1, 'private_directory': 1, 'literal': 2}
    codes, dynamic = set(), set()

    def take(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            codes.add(node.value)
        elif isinstance(node, ast.IfExp):
            take(node.body)
            take(node.orelse)
        elif isinstance(node, ast.BinOp) and isinstance(node.left, ast.Constant):
            dynamic.add(node.left.value)
        elif not isinstance(node, ast.Name):
            raise AssertionError('a refusal code that this test cannot read at line %d' % node.lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in positions and len(node.args) > positions[node.func.id]:
            take(node.args[positions[node.func.id]])
        if isinstance(node, ast.FunctionDef):
            for default, argument in zip(node.args.defaults[::-1], node.args.args[::-1]):
                if argument.arg == 'code':
                    take(default)
    return codes, dynamic


def test_zz_every_refusal_code_of_the_binder_is_exercised_by_these_tests(request):
    if request.config.getoption('keyword') or request.config.getoption('markexpr') or any('::' in str(argument) for argument in request.config.args):
        pytest.skip('only meaningful when the whole file is run')
    codes, dynamic = refusal_codes_of_the_source()
    assert len(codes) > 120 and dynamic == {'FAMILY_REFUSES_THE_REQUEST_', 'PROOF_FAILED_', 'EVIDENCE_SET_', 'RELEASE_FIELDS_'}          # the last: HOSTOPS02 K10
    missing = sorted((codes | dynamic) - h.COVERED)
    assert missing == [], 'refusal codes of bind_once.py that no test exercised: %s' % missing


# ================================================================ repair round of 2026-10-02 (review of the binder)
OPERATIONS = {'PRECHECK': PRECHECK, 'PROVISION': PROVISION, 'INSTALL': INSTALL, 'READBACK': READBACK}
REAL_COMMENT = '5955151654'


def core_set(base, families, operation, parameters, reference, mode=b.REHEARSAL, name=None):
    return h.bind(base, families['hostops'], operation, parameters, reference, mode=mode, name=name, now=h.HOSTOPS_NOW)


def run_on_emulated_host(hostops_harness, key, host, out, mode=b.REHEARSAL):
    """The bound set `out` resumed through the family's dispatcher against the family's emulated host, as uid 0."""
    f, hostemu = hostops_harness
    k = f.load(key)
    host.refused = k.m.Refused
    return h.finish(out, emulated_transport(f, k, host, b.signed_state(out)), comment_id=b.REHEARSAL_PUBLICATION if mode == b.REHEARSAL else REAL_COMMENT,
                    at=h.HOSTOPS_NOW)


def executed_precheck(base, families, hostops_harness, reference, mode=b.REHEARSAL, name=None, host=None):
    f, hostemu = hostops_harness
    host = hostemu.world() if host is None else host
    name = name or ('rehearsal-precheck' if mode == b.REHEARSAL else 'bound-precheck')
    parameters = core_parameters(base, PRECHECK, 'precheck', dict(h.PRECHECK_PLAN), [], name='P-%s.json' % name, minutes=50)
    out, prepared, signed = core_set(base, families, PRECHECK, parameters, reference, mode, name)
    assert run_on_emulated_host(hostops_harness, 'precheck', host, out, mode)['status'] == 'KNOWN_COMPLETE'
    return out, host


def cite(**roles):
    """evidence entries; a directory is cited as a bound set, a file as a loose receipt."""
    entries = []
    for role, path in roles.items():
        entry = {'role': role, 'operation': OPERATIONS[role.rstrip('2')], ('bound' if Path(path).is_dir() else 'receipt_file'): str(path)}
        entries.append(entry)
    return entries


def provision_plan(hostops_harness, role='PRECHECK'):
    f, hostemu = hostops_harness
    k = f.load('provision')
    typed = f.provision_fields(k, f.world(k), placement='A')
    plan = json.loads(json.dumps(typed))
    plan['chains'] = {key: from_receipt(role, '/items/chains/%s/rows' % key) for key in plan['chains']}
    plan['evidence_boot_id_sha256'] = from_receipt(role, '/items/boot/boot_id_sha256')
    plan['retention_tag']['image_id'] = from_receipt(role, '/items/image/id')
    return plan, typed


def test_real_chain_precheck_provision_install_readback_each_citing_the_bound_set_before_it(base, families, hostops_harness):
    """REAL mode, synthetic executed reference, the family's emulated host: every later request cites the BOUND SET of the
    earlier operation (never a loose file), the binder verifies it as `status` does and takes every value by pointer."""
    f, hostemu = hostops_harness
    reference = h.executed_reference(base, families['w1'])
    host = hostemu.world()
    real_host = json.loads(reference.read_bytes())['host_binding_sha256']
    precheck_set, host = executed_precheck(base, families, hostops_harness, reference, b.REAL, host=host)
    # provision (A3): rows, boot and image by pointer from the precheck SET
    plan, typed = provision_plan(hostops_harness)
    out, prepared, signed = core_set(base, families, PROVISION, core_parameters(base, PROVISION, 'provision', plan, cite(PRECHECK=precheck_set), name='P-provision.json'),
                                     reference, b.REAL, 'bound-provision')
    fact = prepared['sheet']['evidence'][0]
    precheck_report = b.status(precheck_set)
    assert fact['source'] == 'BOUND_SET' and fact['complete'] is True and fact['exit_json_binds_these_bytes'] is True and fact['outcome'] == 'PRECHECK_ALL_OBSERVED'
    assert fact['bound_set'] == {'mode': 'REAL', 'config_sha256': precheck_report['config_sha256'], 'request_sha256': precheck_report['request_sha256'],
                                 'go_sha256': precheck_report['go_sha256'], 'exit_json_sha256': precheck_report['exit_json_sha256'],
                                 'transport_status': 'KNOWN_COMPLETE', 'exit_json_binds_config_request_go_and_output': True, 'stderr_empty': True,
                                 'relocated_copy': False}
    assert fact['receipt_sha256'] == precheck_report['metadata_sha256'] and prepared['sheet']['host_binding_sha256'] == real_host
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    assert {key: request['plan'][key] for key in typed} == typed and request['evidence'][0]['receipt_sha256'] == precheck_report['metadata_sha256']
    question = prepared['owner_question_pt']
    assert question.rstrip().endswith('Se estiver de acordo, responda exatamente: Assino') and 'Revisão prévia do Codex sobre estes bytes: FEITA' in question
    authority = json.loads((out / signed['authority_name']).read_bytes())
    assert authority['owner_evidence'].startswith('DUDU answered "Assino" (AskUserQuestion via Fable) at ')
    assert run_on_emulated_host(hostops_harness, 'provision', host, out, b.REAL)['status'] == 'KNOWN_COMPLETE'
    provision_set = out
    # install (B1): unit directory rows and boot from the same precheck set
    k = f.load('install_units')
    plan = f.install_fields(k, host, placement='A')
    plan['unit_directory'] = from_receipt('PRECHECK', '/items/chains/UNIT_DIRECTORY/rows')
    plan['evidence_boot_id_sha256'] = from_receipt('PRECHECK', '/items/boot/boot_id_sha256')
    install_set, prepared, signed = core_set(base, families, INSTALL, core_parameters(base, INSTALL, 'install', plan, cite(PRECHECK=precheck_set), name='P-install.json'),
                                             reference, b.REAL, 'bound-install')
    assert run_on_emulated_host(hostops_harness, 'install_units', host, install_set, b.REAL)['status'] == 'KNOWN_COMPLETE'
    # what other authorities do between the install and the readback (token, reload), as the family's ready_host() does. The
    # catalog (operation 4b) is K2a's: a REAL readback that expects it INITIALISED must cite the A9 set (test_hostops02 binds
    # that chain); here the readback expects the root still empty (NOT_YET), which binds as before.
    host.tree.add('/etc/c3po-bar/token', kind='file', mode=0o600, content=b'never-emit-token-canary-0123456789\n')
    host.is_enabled['c3po-massive.timer'] = 'disabled'
    loaded = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead'}
    host.units['c3po-massive.service'] = dict(loaded, Id='c3po-massive.service', UnitFileState='static', FragmentPath='/etc/systemd/system/c3po-massive.service',
                                              TriggeredBy='c3po-massive.timer')
    host.units['c3po-massive.timer'] = dict(loaded, Id='c3po-massive.timer', UnitFileState='disabled', FragmentPath='/etc/systemd/system/c3po-massive.timer')
    # readback (B3), mode GATE: three bound sets cited, the receipt hashes and the outcome by pointer
    k = f.load('readback')
    host.refused = k.m.Refused
    receipts = {role: json.loads((path / '.dispatch-root' / (label + '-once') / 'stdout.private.json').read_bytes())
                for role, path, label in (('PROVISION', provision_set, 'provision'), ('INSTALL', install_set, 'install'))}
    plan = f.readback_fields(k, host, receipts['PROVISION'], receipts['INSTALL'], catalog='NOT_YET')
    expected = json.loads(json.dumps(plan))
    plan['provision'] = {'receipt_sha256': from_receipt('PROVISION', '/metadata_sha256')}
    plan['install'] = {'receipt_sha256': from_receipt('INSTALL', '/metadata_sha256'), 'outcome': from_receipt('INSTALL', '/outcome')}
    plan['journal_mount_point'] = from_receipt('PROVISION', '/effects/journal/mount_point_by_device_change')
    plan['evidence_boot_id_sha256'] = from_receipt('PRECHECK', '/items/boot/boot_id_sha256')
    plan['unit_directory'] = from_receipt('PRECHECK', '/items/chains/UNIT_DIRECTORY/rows')
    cited = cite(PRECHECK=precheck_set, PROVISION=provision_set, INSTALL=install_set)
    typed = f.readback_fields(k, host, receipts['PROVISION'], receipts['INSTALL'])['catalog']          # INITIALISED, typed, no 4b receipt cited
    with refused('CATALOG_WITHOUT_THE_CITED_4B_RECEIPT'):
        b.prepare(families['hostops'], READBACK, core_parameters(base, READBACK, 'readback', dict(plan, catalog=typed), cited, name='P-readback-typed.json', minutes=50),
                  reference, base / 'bound-readback-typed', b.REAL, now=lambda: h.HOSTOPS_NOW)
    assert not (base / 'bound-readback-typed').exists()
    out, prepared, signed = core_set(base, families, READBACK, core_parameters(base, READBACK, 'readback', plan, cited, name='P-readback.json', minutes=50),
                                     reference, b.REAL, 'bound-readback')
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    assert {key: request['plan'][key] for key in expected} == expected
    assert [item['source'] for item in prepared['sheet']['evidence']] == ['BOUND_SET'] * 3 and all(item['complete'] for item in prepared['sheet']['evidence'])
    assert run_on_emulated_host(hostops_harness, 'readback', host, out, b.REAL)['status'] == 'KNOWN_COMPLETE'
    report = b.status(out)
    assert report['verified'] is True and report['success_criterion_met'] is True and report['outcome'] == 'READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
    # an archived copy of an executed set (block 11 of the runbook) is as good a citation as the set in its place
    archive = base / 'archive'
    archive.mkdir(mode=0o700)
    shutil.copytree(str(precheck_set), str(archive / 'bound-precheck'))
    again = b.prepare(families['hostops'], PROVISION, core_parameters(base, PROVISION, 'provision', provision_plan(hostops_harness)[0],
                                                                      cite(PRECHECK=archive / 'bound-precheck'), name='P-archive.json'),
                      reference, base / 'bound-from-archive', b.REAL, now=lambda: h.HOSTOPS_NOW)
    assert again['sheet']['evidence'][0]['bound_set']['relocated_copy'] is True and again['sheet']['request_sha256'] != ''


def test_a_cited_receipt_must_be_of_this_operation_this_family_this_host_this_mode_and_complete(base, families, hostops_harness):
    """MAJOR (provenance of a cited receipt). Each crossing the review showed as accepted is refused before anything is
    created: another host binding (the fixture's, the rehearsal's in a REAL request), another schema, no operation member,
    a partial outcome, a loose file in REAL mode, a set of the other mode, of another seal, of another operation, a set
    that has no verified receipt, and a stored receipt edited and sealed again."""
    f, hostemu = hostops_harness
    fake = h.rehearsal_reference(base)
    executed = h.executed_reference(base, families['w1'])
    real_host = json.loads(executed.read_bytes())['host_binding_sha256']
    counter = [0]

    def attempt(code, evidence, mode=b.REHEARSAL, reference=None, plan=None):
        counter[0] += 1
        parameters = core_parameters(base, PROVISION, 'provision', plan or provision_plan(hostops_harness)[0], evidence, name='X%d.json' % counter[0])
        out = base / ('rehearsal-x' if mode == b.REHEARSAL else 'bound-x')
        with refused(code):
            b.prepare(families['hostops'], PROVISION, parameters, reference or (fake if mode == b.REHEARSAL else executed), out, mode, now=lambda: h.HOSTOPS_NOW)
        assert not out.exists()
    good, receipt = precheck_receipt(base, hostops_harness)
    # (g) another host binding: any 64-hex, and the binding the family's own fixtures carry
    other, _ = precheck_receipt(base, hostops_harness, 'other-host.json', host='9' * 64)
    attempt('EVIDENCE_RECEIPT_OF_ANOTHER_HOST', cite(PRECHECK=other))
    fixture, raw = precheck_receipt(base, hostops_harness, 'fixture-host.json', host=None)
    assert raw['host_binding_sha256'] == f.HOST != h.REHEARSAL_HOST
    attempt('EVIDENCE_RECEIPT_OF_ANOTHER_HOST', cite(PRECHECK=fixture))
    # (f) another schema; and no operation member at all (what the real HOSTFACTS01 receipt looks like)
    w1_schema, _ = precheck_receipt(base, hostops_harness, 'w1-schema.json', change=lambda value: value.update(schema='READONLY_W1PREFLIGHT01_RECEIPT_V1'))
    attempt('EVIDENCE_RECEIPT_SCHEMA', cite(PRECHECK=w1_schema))
    unnamed, _ = precheck_receipt(base, hostops_harness, 'unnamed.json', change=lambda value: (value.pop('operation'), value.update(schema='READONLY_W1PREFLIGHT01_RECEIPT_V1')))
    attempt('EVIDENCE_RECEIPT_OPERATION', cite(PRECHECK=unnamed))
    # a receipt that names another payload: not produced by the sealed source of that operation in this family
    other_bytes, _ = precheck_receipt(base, hostops_harness, 'other-bytes.json', change=lambda value: value.update(payload_sha256='7' * 64))
    attempt('EVIDENCE_RECEIPT_OF_OTHER_BYTES', cite(PRECHECK=other_bytes))
    assert receipt['payload_sha256'] == b.sha((families['hostops'] / 'precheck' / 'precheck_readonly.py').read_bytes())
    # an operation this sealed family does not hold cannot be cited at all
    for operation in (W1, 'NOT_AN_OPERATION_NAME', 'GO_READONLY_SUPERVISOR_HOSTFACTS_01'):
        attempt('EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY', [{'role': 'PRECHECK', 'operation': PRECHECK, 'receipt_file': str(good)},
                                                         {'role': 'FACTS', 'operation': operation, 'receipt_file': str(good)}])
    # (h) a precheck that is not PRECHECK_ALL_OBSERVED: refused, unless the parameter accepts it by name, and then the sheet and the question say so
    partial, _ = precheck_receipt(base, hostops_harness, 'partial.json',
                                  change=lambda value: value.update(status='PARTIAL_METADATA_REQUIRES_REVIEW', outcome='PARTIAL_OBSERVED'))
    attempt('EVIDENCE_RECEIPT_NOT_COMPLETE', cite(PRECHECK=partial))
    odd, _ = precheck_receipt(base, hostops_harness, 'odd.json', change=lambda value: value.update(outcome='PARTIAL_OR_WINDOW_EXPIRED'))
    attempt('EVIDENCE_RECEIPT_NOT_COMPLETE', cite(PRECHECK=odd))          # a complete status with another outcome is not the success outcome either
    for bad in (False, 'yes', 1):
        attempt('PARAMETERS_INVALID', [dict(cite(PRECHECK=partial)[0], accept_not_complete=bad)])
    accepted = b.prepare(families['hostops'], PROVISION, core_parameters(base, PROVISION, 'provision', provision_plan(hostops_harness)[0],
                                                                         [dict(cite(PRECHECK=partial)[0], accept_not_complete=True)], name='accepted.json'),
                         fake, base / 'rehearsal-accepted', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
    fact = accepted['sheet']['evidence'][0]
    assert (fact['complete'], fact['not_complete_accepted_by_parameter'], fact['outcome'], fact['receipt_status']) == (False, True, 'PARTIAL_OBSERVED', 'PARTIAL_METADATA_REQUIRES_REVIEW')
    assert 'resultado PARTIAL_OBSERVED (NÃO COMPLETO, aceito por parâmetro: confira antes de assinar)' in accepted['owner_question_pt']
    # (i) REAL mode: a loose file is never evidence, whatever host binding it carries
    for host in (h.REHEARSAL_HOST, real_host):
        loose, _ = precheck_receipt(base, hostops_harness, 'loose-%s.json' % host[:8], host=host)
        attempt('EVIDENCE_OF_A_REAL_REQUEST_MUST_BE_A_BOUND_SET', cite(PRECHECK=loose), mode=b.REAL)
    # bound sets: one REHEARSAL and one REAL precheck, each resumed on the emulated host
    (base / 'r').mkdir()
    (base / 'x').mkdir()
    rehearsal_set, _ = executed_precheck(base / 'r', families, hostops_harness, fake, b.REHEARSAL)
    real_set_, _ = executed_precheck(base / 'x', families, hostops_harness, executed, b.REAL)
    attempt('EVIDENCE_SET_OF_THE_OTHER_MODE', cite(PRECHECK=rehearsal_set), mode=b.REAL)          # the review's case i, in the form REAL mode demands
    attempt('EVIDENCE_SET_OF_THE_OTHER_MODE', cite(PRECHECK=real_set_), mode=b.REHEARSAL)
    # a REAL set of another host: the same family and operation, bound to another target
    elsewhere = h.executed_reference(base, families['w1'], name='executed-elsewhere', another_target='operator@another-host.example.net')
    assert json.loads(elsewhere.read_bytes())['host_binding_sha256'] != real_host
    attempt('EVIDENCE_RECEIPT_OF_ANOTHER_HOST', cite(PRECHECK=real_set_), mode=b.REAL, reference=elsewhere)
    # a set of another seal (a W1 set), and a set of another operation of this family
    (base / 'w').mkdir()
    w1_out, _, _ = w1_set(base / 'w', families)
    attempt('EVIDENCE_SET_OF_ANOTHER_SEAL', cite(PRECHECK=w1_out))
    attempt('EVIDENCE_SET_OF_ANOTHER_OPERATION', [{'role': 'PRECHECK', 'operation': PRECHECK, 'bound': str(rehearsal_set)},
                                                  {'role': 'EARLIER', 'operation': READBACK, 'bound': str(rehearsal_set)}])
    # a finished set whose result is not verified (here: something on stderr) is no evidence either, although its receipt is stored
    (base / 's').mkdir()
    noisy_set, _, _ = core_set(base / 's', families, PRECHECK, core_parameters(base / 's', PRECHECK, 'precheck', dict(h.PRECHECK_PLAN), [], minutes=50), fake)
    k = f.load('precheck')
    noisy_host = hostemu.world()
    noisy_host.refused = k.m.Refused
    quiet = emulated_transport(f, k, noisy_host, b.signed_state(noisy_set))

    def noisy(payload, **kwargs):
        result, line, _ = quiet(payload, **kwargs)
        return result, line, b'warning\n'
    assert h.finish(noisy_set, noisy, at=h.HOSTOPS_NOW)['status'] == 'KNOWN_COMPLETE'
    report = b.status(noisy_set)
    assert report['verified'] is False and report['stderr_empty'] is False and all(report['receipt_bindings'].values())
    attempt('EVIDENCE_SET_WITHOUT_A_VERIFIED_RECEIPT', cite(PRECHECK=noisy_set))
    # a signed set that was never run has no receipt; a prepared one is not signed; a path that is no set at all
    (base / 'n').mkdir()
    never_run, _, _ = core_set(base / 'n', families, PRECHECK, core_parameters(base / 'n', PRECHECK, 'precheck', dict(h.PRECHECK_PLAN), [], minutes=50), fake)
    attempt('EVIDENCE_SET_WITHOUT_A_VERIFIED_RECEIPT', cite(PRECHECK=never_run))
    (base / 'u').mkdir()
    unsigned = b.prepare(families['hostops'], PRECHECK, core_parameters(base / 'u', PRECHECK, 'precheck', dict(h.PRECHECK_PLAN), [], minutes=50), fake,
                         base / 'u' / 'rehearsal-bound', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
    attempt('EVIDENCE_SET_BOUND_FILE_SET_NOT_SIGNED', cite(PRECHECK=Path(unsigned['bound'])))
    attempt('EVIDENCE_SET_BOUND_NOT_FOUND', [{'role': 'PRECHECK', 'operation': PRECHECK, 'bound': str(base / 'no-such-set')}])
    h.COVERED.add('EVIDENCE_SET_')
    # the stored receipt of a finished set edited and sealed again: its exit.json no longer names those bytes
    (base / 'e').mkdir()
    edited, _ = executed_precheck(base / 'e', families, hostops_harness, fake, b.REHEARSAL)
    stored = edited / '.dispatch-root' / 'precheck-once' / 'stdout.private.json'
    changed = h.resealed(json.loads(stored.read_bytes()), lambda value: value['items']['boot'].update(boot_id_sha256='e' * 64), host=None)
    stored.write_bytes(b.canonical(changed) + b'\n')
    attempt('EVIDENCE_SET_EXIT_JSON_DOES_NOT_MATCH_THE_STORED_OUTPUT', cite(PRECHECK=edited))
    # the good receipt, as a loose file in a rehearsal and as a bound set in both modes, is accepted
    for mode, evidence, reference in ((b.REHEARSAL, cite(PRECHECK=good), fake), (b.REHEARSAL, cite(PRECHECK=rehearsal_set), fake), (b.REAL, cite(PRECHECK=real_set_), executed)):
        counter[0] += 1
        out = base / ('%s-ok-%d' % ('rehearsal' if mode == b.REHEARSAL else 'bound', counter[0]))
        prepared = b.prepare(families['hostops'], PROVISION, core_parameters(base, PROVISION, 'provision', provision_plan(hostops_harness)[0], evidence,
                                                                           name='ok%d.json' % counter[0]), reference, out, mode, now=lambda: h.HOSTOPS_NOW)
        assert prepared['sheet']['evidence'][0]['complete'] is True and prepared['sheet']['evidence'][0]['source'] == ('RECEIPT_FILE' if evidence[0].get('receipt_file') else 'BOUND_SET')


def test_plan_values_must_be_the_values_of_the_single_cited_receipt_typed_or_copied(base, families, hostops_harness):
    """MAJOR (typed plan values). A request never binds with a boot identifier, chain rows, an image ID, a receipt hash or
    an outcome that is not the one of the receipt it cites, whether the value was typed or copied by pointer from another
    receipt; valid 64-hex values of another boot are used, not malformed ones."""
    f, hostemu = hostops_harness
    reference = h.rehearsal_reference(base)
    good, receipt = precheck_receipt(base, hostops_harness)
    old_boot, old = precheck_receipt(base, hostops_harness, 'old-boot.json', change=lambda value: value['items']['boot'].update(boot_id_sha256='e' * 64))
    counter = [0]

    def attempt(code, operation, label, plan, evidence, minutes=10):
        counter[0] += 1
        parameters = core_parameters(base, operation, label, plan, evidence, name='V%d.json' % counter[0], minutes=minutes)
        with refused(code):
            b.prepare(families['hostops'], operation, parameters, reference, base / 'rehearsal-refused', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
        assert not (base / 'rehearsal-refused').exists()

    def accepted(operation, label, plan, evidence, minutes=10):
        counter[0] += 1
        return b.prepare(families['hostops'], operation, core_parameters(base, operation, label, plan, evidence, name='V%d.json' % counter[0], minutes=minutes),
                         reference, base / ('rehearsal-accepted-%d' % counter[0]), b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
    NOT_THE_RECEIPT, NOT_SINGLE = 'PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', 'PLAN_VALUE_WITHOUT_ITS_SINGLE_CITED_RECEIPT'
    # ---- provision
    by_pointer, typed = provision_plan(hostops_harness)
    assert typed['evidence_boot_id_sha256'] == receipt['items']['boot']['boot_id_sha256'] != 'e' * 64
    assert accepted(PROVISION, 'provision', json.loads(json.dumps(typed)), cite(PRECHECK=good))['sheet']['plan_values_copied_from_receipts'] == []          # typed and equal: bound
    attempt(NOT_THE_RECEIPT, PROVISION, 'provision', dict(typed, evidence_boot_id_sha256='c' * 64), cite(PRECHECK=good))                                   # (a) another boot, typed
    moved = json.loads(json.dumps(typed))
    moved['chains']['DATA_VOLUME'][-1]['inode'] += 12345
    attempt(NOT_THE_RECEIPT, PROVISION, 'provision', moved, cite(PRECHECK=good))                                                                          # (b) a row that is not the receipt's
    for name in typed['chains']:
        for change in (lambda rows: rows.pop(), lambda rows: rows[0].update(mode=rows[0]['mode'] ^ 0o002), lambda rows: rows.reverse()):
            other = json.loads(json.dumps(typed))
            change(other['chains'][name])
            attempt(NOT_THE_RECEIPT, PROVISION, 'provision', other, cite(PRECHECK=good))
    attempt(NOT_THE_RECEIPT, PROVISION, 'provision', dict(typed, retention_tag=dict(typed['retention_tag'], image_id='sha256:' + 'd' * 64)), cite(PRECHECK=good))   # (c)
    # (d) rows copied from a receipt of an earlier boot and the boot identifier from another: two prechecks of two boots
    mixed = json.loads(json.dumps(by_pointer))
    mixed['chains'] = {key: from_receipt('PRECHECK2', '/items/chains/%s/rows' % key) for key in typed['chains']}
    attempt('CITED_PRECHECKS_OF_DIFFERENT_BOOTS', PROVISION, 'provision', mixed, cite(PRECHECK=good, PRECHECK2=old_boot))
    # two prechecks of ONE boot: which one the rows come from is not decided by guess
    twin, _ = precheck_receipt(base, hostops_harness, 'twin.json', change=lambda value: value.update(observed_at='2026-10-03T16:00:00+00:00'))
    attempt(NOT_SINGLE, PROVISION, 'provision', by_pointer, cite(PRECHECK=good, PRECHECK2=twin))
    # (e) the only cited precheck is of another boot than the boot identifier the plan types
    attempt(NOT_THE_RECEIPT, PROVISION, 'provision', json.loads(json.dumps(typed)), cite(PRECHECK=old_boot))
    # a chain the cited precheck never read
    extra = json.loads(json.dumps(typed))
    extra['chains']['CAPACITY_PARENT'] = extra['chains']['ETC']
    attempt(NOT_THE_RECEIPT, PROVISION, 'provision', extra, cite(PRECHECK=good))
    # ---- install
    k = f.load('install_units')
    install_typed = f.install_fields(k, f.world(k), placement='A')
    assert accepted(INSTALL, 'install', json.loads(json.dumps(install_typed)), cite(PRECHECK=good))['status'] == 'PREPARED_AWAITING_OWNER_SIGNATURE'
    attempt(NOT_THE_RECEIPT, INSTALL, 'install', dict(install_typed, evidence_boot_id_sha256='c' * 64), cite(PRECHECK=good))
    attempt(NOT_THE_RECEIPT, INSTALL, 'install', json.loads(json.dumps(install_typed)), cite(PRECHECK=old_boot))
    rows = json.loads(json.dumps(install_typed['unit_directory']))
    rows[-1]['inode'] += 1
    attempt(NOT_THE_RECEIPT, INSTALL, 'install', dict(install_typed, unit_directory=rows), cite(PRECHECK=good))
    # ---- readback
    k = f.load('readback')
    host, provision, install = f.ready_host(k, placement='A')
    provision, install = h.resealed(provision), h.resealed(install)
    files = {'PRECHECK': good, 'PROVISION': h.receipt_file(base / 'provision.json', provision), 'INSTALL': h.receipt_file(base / 'install.json', install)}
    readback = f.readback_fields(k, host, provision, install)
    assert accepted(READBACK, 'readback', json.loads(json.dumps(readback)), cite(**files), minutes=50)['sheet']['contract_section_12_checks']['floor_met_by_the_precheck_figure'] is True
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', dict(readback, provision={'receipt_sha256': 'a' * 64}), cite(**files), minutes=50)                     # (1)
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', dict(readback, install=dict(readback['install'], receipt_sha256='b' * 64)), cite(**files), minutes=50)  # (2)
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', json.loads(json.dumps(readback)), cite(**dict(files, PRECHECK=old_boot)), minutes=50)                   # (3) floor from another boot
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', dict(readback, evidence_boot_id_sha256='c' * 64), cite(**files), minutes=50)
    other_rows = json.loads(json.dumps(readback['unit_directory']))
    other_rows[-1]['device'] += 1
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', dict(readback, unit_directory=other_rows), cite(**files), minutes=50)
    # (7) the cited install receipt is partial and the plan types the success outcome over its hash
    partial = h.resealed(install, lambda value: value.update(outcome='PARTIAL_REQUIRES_RECONCILIATION', status='PARTIAL_METADATA_REQUIRES_REVIEW'))
    partial_file = h.receipt_file(base / 'install-partial.json', partial)
    lying = dict(readback, install={'receipt_sha256': partial['metadata_sha256'], 'outcome': 'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'})
    attempt('EVIDENCE_RECEIPT_NOT_COMPLETE', READBACK, 'readback', lying, cite(**dict(files, INSTALL=partial_file)), minutes=50)
    cited = cite(**dict(files, INSTALL=partial_file))
    cited[-1]['accept_not_complete'] = True
    attempt(NOT_THE_RECEIPT, READBACK, 'readback', lying, cited, minutes=50)
    # a RECONCILIATION readback after that partial install: the outcome and the hash of the receipt it cites, no gate, bound
    reconciliation = dict(readback, mode='RECONCILIATION', install={'receipt_sha256': partial['metadata_sha256'], 'outcome': 'PARTIAL_REQUIRES_RECONCILIATION'})
    prepared = accepted(READBACK, 'readback', reconciliation, cited, minutes=50)
    assert prepared['sheet']['success_criterion'] == 'RECONCILIATION_OBSERVED_NOTHING_GATED' and 'NÃO COMPLETO, aceito por parâmetro' in prepared['owner_question_pt']
    # members that are null are the family's to judge: nothing is compared, and nothing needs to be cited for them
    assert b.plan_sources(READBACK, {'provision': {'receipt_sha256': None}, 'install': {'receipt_sha256': None, 'outcome': None},
                                     'evidence_boot_id_sha256': None, 'unit_directory': None}, [], {}) == []
    assert b.plan_sources(PROVISION, {'chains': None, 'evidence_boot_id_sha256': None, 'retention_tag': None}, [], {}) == []
    assert b.plan_sources(PRECHECK, dict(h.PRECHECK_PLAN), [], {}) == [] and b.plan_sources('GO_SOME_FUTURE_OPERATION_01', {'chains': {'ETC': []}}, [], {}) == []
    assert b.pointer_value({'a': [{'b/c': 1, 'd~e': 2}]}, '/a/0/b~1c') == 1 and b.pointer_value({'a': [{'d~e': 2}]}, '/a/0/d~0e') == 2
    assert b.pointer_value({'a': [1]}, '/a/1') is b.MISSING and b.pointer_value({'a': [1]}, '/a/01') is b.MISSING and b.pointer_value({'a': 1}, '/a/b') is b.MISSING


def test_w1_window_is_refused_beyond_the_read_cap_at_prepare_and_whenever_the_set_is_opened(base, families, monkeypatch):
    """The sealed W1 dispatcher and source accept a whole UTC day; the plan's 3600 s read gate is enforced by the binder."""
    reference = h.rehearsal_reference(base)
    for index, (start, end) in enumerate((('2026-10-03T13:00:00Z', '2026-10-03T14:00:01Z'), ('2026-10-03T00:00:00Z', '2026-10-03T23:59:59Z'),
                                          ('2026-10-10T00:00:00Z', '2026-10-10T23:59:59Z'))):
        with refused('WINDOW_OVER_THE_READ_CAP'):
            b.prepare(families['w1'], W1, h.w1_parameters(base, name='long%d.json' % index, not_before=start, not_after=end), reference,
                      base / 'rehearsal-long', b.REHEARSAL, now=lambda: NOW)
        assert not (base / 'rehearsal-long').exists()
    out, prepared, signed = h.bind(base, families['w1'], W1, h.w1_parameters(base, name='hour.json', not_before='2026-10-03T13:00:00Z', not_after='2026-10-03T14:00:00Z'), reference)
    assert prepared['sheet']['window']['gate_span_seconds'] == 3600 == b.COLLECTION_SCOPE_RULES[W1]['max_window_seconds']
    assert 'de sáb 03/10/2026 10:00:00 BRT até sáb 03/10/2026 11:00:00 BRT' in prepared['owner_question_pt']          # the owner reads both ends in BRT
    assert b.check(out, families['w1'], now=lambda: NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    # the family itself would take that set and a far longer one: the cap is the binder's, so it is applied again by check, status and sign
    monkeypatch.setattr(b, 'COLLECTION_SCOPE_RULES', {W1: dict(b.COLLECTION_SCOPE_RULES[W1], max_window_seconds=3599)})
    for call in (lambda: b.check(out, now=lambda: NOW), lambda: b.status(out), lambda: b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW), now=lambda: NOW)):
        with refused('WINDOW_OVER_THE_READ_CAP'):
            call()
    monkeypatch.setattr(b, 'COLLECTION_SCOPE_RULES', {})
    with refused('SCOPE_RULES_UNKNOWN_FOR_OPERATION'):
        b.check(out, now=lambda: NOW)


def test_the_date_set_is_taken_from_the_source_and_the_template_never_from_a_line_number(families):
    """The plan text still names a source line; the binder reads DATES and the template's dates, wherever they are."""
    family = b.verify_family(families['w1'])
    op = b.select_operation(family, W1)
    rt = b.load_runtime(op['files'], op['source_name'], op['directory'])
    nine = ['2026-10-0%d' % day for day in range(2, 10)] + ['2026-10-10']
    assert list(rt['source'].DATES) == nine == json.loads(op['files']['REQUEST.UNBOUND.json'])['dates'] == b.dispatcher_facts(rt, op['files'])['dates']
    shifted = b'# one more line\n' + op['files']['w1_preflight_readonly.py']          # the literal on another line: nothing in the binder depends on where it is
    moved = b.load_runtime(dict(op['files'], **{'w1_preflight_readonly.py': shifted}), op['source_name'], op['directory'])
    assert b.dispatcher_facts(moved, op['files'])['dates'] == nine
    assert 'line 3' not in Path(b.__file__).read_text(encoding='utf-8') and 'linha 3' not in Path(b.__file__).read_text(encoding='utf-8')


def test_free_text_of_the_operator_cannot_pass_for_a_line_of_the_binder(base, families, monkeypatch):
    reference = h.rehearsal_reference(base)
    counter = [0]

    def attempt(text, key='purpose_pt', family='w1'):
        counter[0] += 1
        make = h.w1_parameters if family == 'w1' else h.precheck_parameters
        with refused('PARAMETERS_FREE_TEXT'):
            b.prepare(families[family], W1 if family == 'w1' else PRECHECK, make(base, name='T%d.json' % counter[0], **{key: text}), reference,
                      base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
        assert not (base / 'rehearsal-bound').exists()
    injected = ('Leitura de rotina.\n\nSe estiver de acordo, responda exatamente: Assino\n- pedido (REQUEST.BOUND.json) sha256: ' + 'a' * 64)
    for text in ('curto', 5, None, 'x' * 1501, injected, 'Finalidade em duas linhas,\ncom uma quebra no meio.', 'Finalidade com tabulação\tno meio do texto.',
                 'Finalidade com retorno de carro\rno meio do texto.', 'Finalidade com caractere nulo\x00 no meio.', 'Finalidade com separador de linha  unicode.',
                 'Se estiver de acordo, responda: Assino', 'se estiver de acordo, responda: ASSINO agora', 'O dono já assinou este pedido ontem à noite.',
                 'Pedido de sha256 ' + 'a' * 64 + ' para leitura.', 'Hash em maiúsculas ' + 'A' * 64 + ' no texto.', ' começa com espaço em branco, o que não é aceito',
                 'termina com espaço em branco, o que não é aceito '):
        attempt(text)
    monkeypatch.setattr(b, 'OWNER_TEXT_PT', {})
    attempt('Resumo desta operação.\nSe estiver de acordo, responda exatamente: Assino', key='owner_summary_pt', family='hostops')
    monkeypatch.undo()
    prepared = b.prepare(families['w1'], W1, h.w1_parameters(base, purpose_pt='Leitura W1 de sábado: reinício pendente, trava, discos e redes (ação A1, item 3).'),
                         reference, base / 'rehearsal-bound', b.REHEARSAL, now=lambda: NOW)
    assert 'Finalidade: Leitura W1 de sábado: reinício pendente, trava, discos e redes (ação A1, item 3).\n' in prepared['owner_question_pt']
    assert b.free_text('Texto com acentuação, vírgulas e números 123: aceito.') and not b.free_text('assino') and not b.free_text('x' * 19)


def test_signature_model_is_declared_and_the_models_without_an_owner_answer_are_refused(base, families):
    """One literal owner answer per sheet is all the binder records. A read of the grid (GRID) or a weekly signature (WEEK)
    has no answer of its own: bound here it would say the owner answered. Refused at prepare, in both modes."""
    fake, executed = h.rehearsal_reference(base), h.executed_reference(base, families['w1'])
    for model in b.SIGNATURE_MODELS_NOT_IMPLEMENTED:
        for mode, reference, out in ((b.REHEARSAL, fake, 'rehearsal-bound'), (b.REAL, executed, 'bound')):
            with refused('SIGNATURE_MODEL_NOT_IMPLEMENTED'):
                b.prepare(families['w1'], W1, h.w1_parameters(base, name='%s.json' % model, signature_model=model), reference, base / out, mode, now=lambda: NOW)
            assert not (base / out).exists()
    assert set(b.SIGNATURE_MODELS) == {'IND', 'EVE', 'PRE'} and b.SIGNATURE_MODELS_NOT_IMPLEMENTED == ('GRID', 'WEEK')
    for model, words in (('IND', 'individual (IND)'), ('EVE', 'de véspera (EVE)'), ('PRE', 'antecipada (PRE)')):
        (base / model).mkdir()
        out, prepared, signed = h.bind(base / model, families['w1'], W1, h.w1_parameters(base / model, signature_model=model), h.rehearsal_reference(base / model))
        assert prepared['sheet']['signature_model'] == model and 'Modelo de assinatura: ' + words in prepared['owner_question_pt']
        assert 'vale para este pedido e para nenhum outro' in prepared['owner_question_pt']


def test_only_the_literal_word_is_a_signature_and_a_rehearsal_never_records_it(base, families):
    (base / 'x').mkdir()
    executed = h.executed_reference(base / 'x', families['w1'])
    prepared = b.prepare(families['w1'], W1, h.w1_parameters(base / 'x'), executed, base / 'x' / 'bound', b.REAL, now=lambda: NOW)
    out = Path(prepared['bound'])
    before = modes(out)
    for answer in ('assino', 'ASSINO', 'Assino.', ' Assino', 'Assino ', 'Assino\n', 'Sim', 'sim, assino', 'Assino o ato B', 'ok', '', None, True, b.REHEARSAL_ANSWER, ['Assino']):
        with refused('OWNER_ANSWER_IS_NOT_THE_SIGNATURE'):
            b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), answer, now=lambda: NOW)
        assert modes(out) == before          # nothing written by a refused answer; the set can still be signed by the real one
    signed = b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), 'Assino', now=lambda: NOW)
    assert signed['owner_answer_verbatim'] == 'Assino' == json.loads((out / signed['authority_name']).read_bytes())['owner_evidence']['owner_answer_verbatim']
    prepared, reference = w1_prepared(base, families)
    for answer in ('Assino', 'assino', '', None):
        with refused('OWNER_ANSWER_IS_NOT_THE_SIGNATURE'):
            b.sign(Path(prepared['bound']), prepared['prepare_json_sha256'], b.zulu(NOW), answer, now=lambda: NOW)
    assert not list(Path(prepared['bound']).glob('*AUTHORITY*'))


def test_a_write_request_states_review_or_waiver_bound_by_hash(base, families, hostops_harness):
    """The owner's decision on writes makes the review of the bytes a precondition of each write unless he waives it for
    that operation: the question says which, with the hash of the document, computed here."""
    reference = h.rehearsal_reference(base)
    good, receipt = precheck_receipt(base, hostops_harness)
    plan, typed = provision_plan(hostops_harness)
    counter = [0]

    def attempt(code, **changes):
        counter[0] += 1
        with refused(code):
            b.prepare(families['hostops'], PROVISION, core_parameters(base, PROVISION, 'provision', plan, cite(PRECHECK=good), name='R%d.json' % counter[0], **changes),
                      reference, base / 'rehearsal-refused', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
        assert not (base / 'rehearsal-refused').exists()
    attempt('REVIEW_OR_WAIVER_MISSING_FOR_A_WRITE', review=h.DROP)
    document = h.review_record(base)['document_file']
    for bad in ('reviewed', None, {'kind': 'CODEX_REVIEWED'}, {'kind': 'REVIEWED', 'document_file': document}, {'kind': 5, 'document_file': document},
                {'kind': 'OWNER_WAIVED', 'document_file': 5}, {'kind': 'OWNER_WAIVED', 'document_file': document, 'sha256': 'a' * 64}):
        attempt('REVIEW_OR_WAIVER_INVALID', review=bad)          # the hash is never typed
    (base / 'empty.txt').write_bytes(b'')
    (base / 'link.txt').symlink_to(document)
    for name in ('missing.txt', 'empty.txt', 'link.txt'):
        attempt('REVIEW_OR_WAIVER_DOCUMENT_UNREADABLE', review={'kind': 'CODEX_REVIEWED', 'document_file': str(base / name)})
    waiver = base / 'WAIVER.synthetic.json'
    waiver.write_text('{"synthetic": "stands for the owner decision that waives the review for this operation; no owner decided anything here"}\n')
    out, prepared, signed = core_set(base, families, PROVISION, core_parameters(base, PROVISION, 'provision', plan, cite(PRECHECK=good), name='waived.json',
                                                                                review={'kind': 'OWNER_WAIVED', 'document_file': 'WAIVER.synthetic.json'}), reference)
    digest = b.sha(waiver.read_bytes())
    assert prepared['sheet']['review'] == {'kind': 'OWNER_WAIVED', 'document_sha256': digest, 'document_bytes': len(waiver.read_bytes())}
    assert ('Revisão prévia do Codex sobre estes bytes: DISPENSADA por decisão sua para esta operação, segundo o documento de sha256 %s. '
            'Ao assinar você confirma essa dispensa.' % digest) in prepared['owner_question_pt'] and 'FEITA' not in prepared['owner_question_pt']
    assert b.check(out, families['hostops'], now=lambda: h.HOSTOPS_NOW)['verdict'] == 'VALID_WINDOW_OPEN'
    # the kind shown to the owner is the kind of the bound parameters: a sheet (and question) edited to say "reviewed" is refused
    prepared = b.prepare(families['hostops'], PROVISION, core_parameters(base, PROVISION, 'provision', plan, cite(PRECHECK=good), name='waived2.json',
                                                                         review={'kind': 'OWNER_WAIVED', 'document_file': 'WAIVER.synthetic.json'}),
                         reference, base / 'rehearsal-kind', b.REHEARSAL, now=lambda: h.HOSTOPS_NOW)
    kind = Path(prepared['bound'])
    sheet = json.loads((kind / 'PREPARE.json').read_bytes())
    sheet['review']['kind'] = 'CODEX_REVIEWED'
    (kind / 'PREPARE.json').write_bytes(b.pretty(sheet))
    (kind / 'OWNER_QUESTION.txt').write_bytes(b.question_text(sheet, b.sha(b.pretty(sheet)), json.loads((kind / 'EFFECTS.json').read_bytes())))
    with refused('SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES'):
        b.sign(kind, b.sha(b.pretty(sheet)), b.zulu(h.HOSTOPS_NOW), ANSWER, now=lambda: h.HOSTOPS_NOW)
    # a read has no such line, and the effects of a write that cannot be listed are never put to the owner
    read = b.prepare(families['hostops'], PRECHECK, h.precheck_parameters(base, name='read.json'), reference, base / 'rehearsal-read', b.REHEARSAL, now=lambda: NOW)
    assert 'Revisão prévia' not in read['owner_question_pt'] and read['sheet']['review'] is None
    effects = json.loads((out / 'EFFECTS.json').read_bytes())
    assert len(b.effects_lines(effects)) == 16 and b.effects_lines(dict(effects, retention_tag=None))[-1].startswith('- diretório ')
    present = json.loads(json.dumps(effects))
    present['creates'][0]['expect'] = 'PRESENT'
    assert b.effects_lines(present)[0] == '- diretório /etc/c3po-bar, modo 0700 (o pedido o assina como já existente: só é conferido)'
    for broken in ({}, {'creates': []}, {'creates': [{'path': '/etc/x', 'expect': 'ABSENT'}]}, {'creates': [{'path': '/etc/x\n- outro', 'mode_octal': '0700', 'expect': 'ABSENT'}]},
                   {'creates': [{'path': '/etc/x', 'mode_octal': '700', 'expect': 'ABSENT'}]}, {'creates': ['x']}, {'creates': [{'path': '/etc/x', 'mode_octal': '0700'}]},
                   {'units': [{'destination_name': 'a.service', 'mode_octal': '0644', 'expect': 'ABSENT'}]}, {'units': [{'mode_octal': '0644', 'expect': 'ABSENT'}], 'directory': '/etc/systemd/system'},
                   {'retention_tag': {'reference': 'a\nb', 'expect': 'ABSENT'}}, {'retention_tag': {'reference': 'c3po/backend:x'}},
                   {'creates': [{'path': '/etc/x', 'mode_octal': '0700', 'expect': 'MAYBE'}]}, {'retention_tag': {'reference': 'c3po/backend:x', 'expect': None}}):
        with refused('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER'):
            b.effects_lines(broken)


def test_what_the_owner_is_shown_is_derived_again_from_what_is_bound(base, families):
    """The review's case: a sheet edited consistently (question regenerated, new hash passed) used to sign a GO whose
    window was not the one shown. Every displayed member is now recomputed from the UTC fields and the files of the set."""
    counter = [0]

    def tampered(change, signed=False):
        counter[0] += 1
        directory = base / ('d%d' % counter[0])
        directory.mkdir()
        if signed:
            out, prepared, _ = w1_set(directory, families, candidates={'release_directories': ['release-20261005'], 'capacity_roots': []},
                                      purpose_pt='Finalidade original desta leitura de ensaio.')
        else:
            prepared, _ = w1_prepared(directory, families, candidates={'release_directories': ['release-20261005'], 'capacity_roots': []},
                                      purpose_pt='Finalidade original desta leitura de ensaio.')
            out = Path(prepared['bound'])
        sheet = json.loads((out / 'PREPARE.json').read_bytes())
        change(sheet)
        (out / 'PREPARE.json').write_bytes(b.pretty(sheet))
        (out / 'OWNER_QUESTION.txt').write_bytes(b.question_text(sheet, b.sha(b.pretty(sheet))))
        if signed:
            h.rewrite_sums(out)
        return out, b.sha(b.pretty(sheet))
    window_edits = (lambda sheet: sheet['window']['brt'].update(not_after='sáb 03/10/2026 23:00:00 BRT'),          # the review's case 2c
                    lambda sheet: sheet['window']['brt'].update(not_before='sex 02/10/2026 10:00:00 BRT'),
                    lambda sheet: sheet['window']['brt'].update(latest_start='sáb 03/10/2026 10:04:59 BRT'),
                    lambda sheet: sheet['window'].update(gate_span_seconds=3600), lambda sheet: sheet['window'].update(date_utc='2026-10-04'),
                    lambda sheet: sheet['window'].update(latest_start='2026-10-03T13:04:59Z'), lambda sheet: sheet['window'].update(watchdog_seconds=1),
                    lambda sheet: sheet['window'].update(extra=1), lambda sheet: sheet['window']['brt'].pop('gate_not_before'))
    for change in window_edits:
        out, digest = tampered(change)
        before = modes(out)
        with refused('SHEET_WINDOW_NOT_DERIVED_FROM_ITS_UTC_FIELDS'):
            b.sign(out, digest, b.zulu(NOW), ANSWER, now=lambda: NOW)
        assert modes(out) == before
    out, digest = tampered(window_edits[0], signed=True)
    for call in (lambda: b.check(out, now=lambda: NOW), lambda: b.status(out)):
        with refused('SHEET_WINDOW_NOT_DERIVED_FROM_ITS_UTC_FIELDS'):
            call()
    for change in (lambda sheet: sheet.update(purpose_pt='Outra finalidade, que os parâmetros não trazem.'), lambda sheet: sheet.pop('purpose_pt'),
                   lambda sheet: sheet.update(signature_model='EVE'), lambda sheet: sheet['candidates'].update(release_directories=0),
                   lambda sheet: sheet.pop('candidates'), lambda sheet: sheet.update(scope_sha256='9' * 64), lambda sheet: sheet.update(parameters_sha256='9' * 64),
                   lambda sheet: sheet.update(source_sha256='9' * 64), lambda sheet: sheet.update(go_scope_sha256='9' * 64),
                   lambda sheet: sheet.update(effects_sha256='9' * 64), lambda sheet: sheet.update(review={'kind': 'CODEX_REVIEWED', 'document_sha256': '9' * 64, 'document_bytes': 1}),
                   lambda sheet: sheet.update(label='another')):
        out, digest = tampered(change)
        with refused('SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES'):
            b.sign(out, digest, b.zulu(NOW), ANSWER, now=lambda: NOW)
    # a read carries no review member, even when the bound parameters are edited to declare one and every hash of the sheet follows
    def with_declared_review(sheet):
        out = Path(sheet['claim_root_identity']['path']).parent
        params = json.loads((out / 'PARAMETERS.json').read_bytes())
        params['review'] = {'kind': 'CODEX_REVIEWED', 'document_file': 'REVIEW.txt'}
        (out / 'PARAMETERS.json').write_bytes(json.dumps(params, sort_keys=True).encode('utf-8'))
        digest = b.sha((out / 'PARAMETERS.json').read_bytes())
        sheet['files_sha256']['PARAMETERS.json'] = sheet['parameters_sha256'] = digest
        sheet['review'] = {'kind': 'CODEX_REVIEWED', 'document_sha256': '9' * 64, 'document_bytes': 1}
    out, digest = tampered(with_declared_review)
    assert json.loads((out / 'PARAMETERS.json').read_bytes())['review']['kind'] == json.loads((out / 'PREPARE.json').read_bytes())['review']['kind']
    with refused('SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES'):
        b.sign(out, digest, b.zulu(NOW), ANSWER, now=lambda: NOW)
    assert not (out / 'DISPATCH.BOUND.json').exists()
    # a read turned into a write on the sheet, or a member the question needs removed: no question can be written from it
    for change in (lambda sheet: sheet.update(writes_allowed=True), lambda sheet: sheet.pop('signature_model'), lambda sheet: sheet.update(signature_model=['IND'])):
        counter[0] += 1
        directory = base / ('q%d' % counter[0])
        directory.mkdir()
        prepared, _ = w1_prepared(directory, families)
        out = Path(prepared['bound'])
        sheet = json.loads((out / 'PREPARE.json').read_bytes())
        change(sheet)
        (out / 'PREPARE.json').write_bytes(b.pretty(sheet))
        with refused('OWNER_QUESTION_CHANGED'):
            b.sign(out, b.sha(b.pretty(sheet)), b.zulu(NOW), ANSWER, now=lambda: NOW)
    assert b.window_of_sheet({'start': NOW, 'end': NOW + 5 * MIN, 'gate_start': NOW + MIN, 'gate_end': NOW + 4 * MIN}, 80) == {
        'date_utc': '2026-10-03', 'not_before': '2026-10-03T13:00:00Z', 'not_after': '2026-10-03T13:05:00Z', 'gate_not_before': '2026-10-03T13:01:00Z',
        'gate_not_after': '2026-10-03T13:04:00Z', 'gate_span_seconds': 180, 'latest_start': '2026-10-03T13:02:40Z', 'watchdog_seconds': 80,
        'brt': {'not_before': 'sáb 03/10/2026 10:00:00 BRT', 'not_after': 'sáb 03/10/2026 10:05:00 BRT', 'gate_not_before': 'sáb 03/10/2026 10:01:00 BRT',
                'gate_not_after': 'sáb 03/10/2026 10:04:00 BRT', 'latest_start': 'sáb 03/10/2026 10:02:40 BRT'}}


def test_a_bound_set_holds_no_directory_but_its_own(base, families):
    """A bytecode cache beside the runtime files could be executed in their place by the interpreter that runs the dispatcher."""
    counter = [0]

    def fresh(signed):
        counter[0] += 1
        directory = base / ('k%d' % counter[0])
        directory.mkdir()
        if signed:
            return w1_set(directory, families)[:2]
        prepared, _ = w1_prepared(directory, families)
        return Path(prepared['bound']), prepared
    for relative in ('__pycache__', '.pytest_cache', 'templates/__pycache__', 'extra', 'templates/extra/deeper'):
        out, prepared = fresh(signed=False)
        (out / relative).mkdir(parents=True, mode=0o700)
        if relative == '__pycache__':
            (out / relative / 'transport_once.cpython-39.pyc').write_bytes(b'planted')
        with refused('BOUND_SET_HOLDS_A_DIRECTORY_THAT_IS_NOT_ITS_OWN'):
            b.sign(out, prepared['prepare_json_sha256'], b.zulu(NOW), ANSWER, now=lambda: NOW)
        assert not (out / 'DISPATCH.BOUND.json').exists()
        out, prepared = fresh(signed=True)
        (out / relative).mkdir(parents=True, mode=0o700)
        for call in (lambda: b.check(out, now=lambda: NOW), lambda: b.status(out), lambda: b.publish_proof(out, b.REHEARSAL_PUBLICATION, b.zulu(NOW), now=lambda: NOW)):
            with refused('BOUND_SET_HOLDS_A_DIRECTORY_THAT_IS_NOT_ITS_OWN'):
                call()
    # the claim root is the dispatcher's: what it creates there is not the set's concern
    out, prepared = fresh(signed=True)
    h.dispatcher_prepare(out, NOW + SEC)
    assert b.status(out)['status'] == 'PREPARED_AWAITING_PUBLICATION'
    # the printed dispatcher commands leave the interpreter no cache to read
    command = b.dispatch_command(out, 'a' * 64, 'resume', ('/p', 'b' * 64))
    assert command[:5] == ['/usr/bin/python3', '-B', '-X', 'pycache_prefix=<fresh-empty-0700-directory>', str(out / 'dispatch_once.py')] and command[-4:] == [
        '--publication-proof', '/p', '--publication-proof-sha256', 'b' * 64]


def test_check_says_when_the_claim_exists_or_the_go_is_spent(base, families, w1_harness, capsys):
    out, prepared, signed = w1_set(base, families)
    checked = b.check(out, now=lambda: NOW)
    assert (checked['verdict'], checked['window_verdict'], checked['a_new_dispatcher_prepare_would_reach_the_claim_and']) == ('VALID_WINDOW_OPEN', 'VALID_WINDOW_OPEN', 'CREATE_IT')
    assert b.check(out, now=lambda: NOW - MIN)['a_new_dispatcher_prepare_would_reach_the_claim_and'] == 'BE_REFUSED'
    intent, proof = h.prepared_and_published(out)
    checked = b.check(out, now=lambda: NOW + 5 * SEC)
    assert (checked['verdict'], checked['window_verdict'], checked['attempt_phase']) == ('VALID_ALREADY_PREPARED', 'VALID_WINDOW_OPEN', 'PREPARED_AWAITING_PUBLICATION')
    assert checked['proofs']['dispatcher_accepts_at_not_before'] == 'ACCEPTED_UP_TO_THE_CLAIM' and checked['a_new_dispatcher_prepare_would_reach_the_claim_and'] == 'BE_REFUSED'
    with pytest.raises(FileExistsError):          # what the verdict announces: the real prepare fails at the exclusive creation
        h.dispatcher_prepare(out, NOW + 6 * SEC)
    assert b.main(['check', '--bound', str(out)]) == 1 and json.loads(capsys.readouterr().out)['verdict'] == 'VALID_ALREADY_PREPARED'
    h.dispatcher_resume(out, proof, NOW + 8 * SEC, h.fixed_transport({'status': 'KNOWN_COMPLETE', 'retry_allowed': False}, h.w1_receipt_line(w1_harness, out)[0]))
    checked = b.check(out, now=lambda: NOW + 9 * SEC)
    assert (checked['verdict'], checked['attempt_phase']) == ('VALID_GO_SPENT', 'FINISHED')
    assert b.main(['check', '--bound', str(out)]) == 1 and json.loads(capsys.readouterr().out)['verdict'] == 'VALID_GO_SPENT'
    attempt = out / '.dispatch-root' / 'attempt-once'
    for name in ('exit.json', 'stdout.private.json', 'stderr.private'):
        (attempt / name).unlink()
    assert b.check(out, now=lambda: NOW + 9 * SEC)['verdict'] == 'VALID_GO_SPENT'          # spawn.claim without a result: spent, outcome unknown
    (attempt / 'spawn.claim').unlink()
    (attempt / 'stray').write_bytes(b'x')
    assert b.check(out, now=lambda: NOW + 9 * SEC)['verdict'] == 'VALID_BUT_THE_CLAIM_ROOT_IS_NOT_AS_THE_DISPATCHER_LEAVES_IT'


def test_status_of_a_relocated_copy_reads_the_original_claim_root_and_never_says_nothing_was_consumed(base, families):
    """The family's dispatcher run from a copy reads the blobs and claims at the ORIGINAL paths. status of that copy used to
    read the copy's own empty claim root and answer NOT_PREPARED, "nothing was consumed", while the GO was claimed."""
    out, prepared, signed = w1_set(base, families)
    copy = base / 'elsewhere' / 'rehearsal-bound'
    copy.parent.mkdir(mode=0o700)
    shutil.copytree(str(out), str(copy))
    with refused('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED'):
        b.check(copy, now=lambda: NOW)
    report = b.status(copy)
    assert (report['status'], report['claim_root_read'], report['bound_set_is_a_relocated_copy']) == ('NOT_PREPARED', 'ORIGINAL_NAMED_ON_THE_SHEET', True)
    assert 'ORIGINAL' in report['verdict_pt']
    # the dispatcher of the COPY, phase prepare: it claims in the original root (single use is kept), and the copy's own root stays empty
    intent = h.dispatcher_prepare(copy, NOW + SEC)
    assert intent['status'] == 'AWAITING_PUBLICATION_NO_SPAWN' and list((copy / '.dispatch-root').iterdir()) == []
    assert sorted(path.name for path in (out / '.dispatch-root').iterdir()) == ['.go-' + signed['go_sha256'] + '.claim', 'attempt-once']
    report = b.status(copy)
    assert (report['status'], report['claim_exists'], report['claim_root_read']) == ('PREPARED_AWAITING_PUBLICATION', True, 'ORIGINAL_NAMED_ON_THE_SHEET')
    assert 'nada foi consumido' not in report['verdict_pt'] and b.status(out)['status'] == 'PREPARED_AWAITING_PUBLICATION'
    with pytest.raises(FileExistsError):
        h.dispatcher_prepare(out, NOW + 2 * SEC)          # the original cannot be prepared again
    # the original gone (the scratchpad is cleaned): the copy's own empty root says nothing about what was consumed
    out.rename(base / 'rehearsal-moved-away')
    report = b.status(copy)
    assert (report['status'], report['claim_root_read'], report['attempt_phase_in_this_copy']) == ('RELOCATED_COPY_STATE_NOT_KNOWN', 'OF_THIS_COPY_THE_ORIGINAL_WAS_NOT_FOUND', 'NOT_PREPARED')
    assert report['verified'] is False and report['claim_exists'] is None and report['go_spent'] is None and 'nada foi consumido' not in report['verdict_pt']
    # another directory at the original path is not the signed root either
    (base / 'rehearsal-bound').mkdir(mode=0o700)
    (base / 'rehearsal-bound' / '.dispatch-root').mkdir(mode=0o700)
    if b.claim_identity(base / 'rehearsal-bound' / '.dispatch-root') != prepared['sheet']['claim_root_identity']:
        assert b.status(copy)['status'] == 'RELOCATED_COPY_STATE_NOT_KNOWN'
    # a set in its own place still says it plainly
    (base / 'own').mkdir()
    own, _, _ = w1_set(base / 'own', families)
    report = b.status(own)
    assert (report['status'], report['claim_root_read']) == ('NOT_PREPARED', 'OF_THIS_DIRECTORY') and 'nada foi consumido' in report['verdict_pt']
