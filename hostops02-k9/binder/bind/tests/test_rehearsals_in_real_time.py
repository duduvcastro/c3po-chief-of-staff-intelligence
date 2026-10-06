"""The rehearsal driver and the literal blocks of the runbook, with the real clock, in a temporary workspace.
The families are dated: outside their date sets (W1 2026-10-02..2026-10-10 UTC, HOSTOPS01 reads ..2026-10-05) there is
nothing these flows can bind, and the tests are skipped. The injected-clock tests of test_bind_once.py do not depend on the day."""
from datetime import datetime, timezone
import json
import os
import subprocess

import pytest

import helpers as h
import runbook_blocks


def today_or_skip(last_day):
    now = datetime.now(timezone.utc)
    if not ('2026-10-02' <= now.date().isoformat() <= last_day) or (now.replace(hour=23, minute=59, second=59) - now).total_seconds() < 600:
        pytest.skip('today is outside the date set of the family, or too close to midnight UTC')


def rehearse(kind, family, workspace):
    done = subprocess.run(['/usr/bin/python3', '-B', str(h.BIND / 'rehearse.py'), kind, '--family', str(family), '--workspace', str(workspace)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={'PATH': '/usr/bin:/bin', 'HOME': os.environ.get('HOME', '/'),'BIND_TEST_REVIEWED_REFERENCE_ROOT':os.environ['BIND_TEST_REVIEWED_REFERENCE_ROOT']}, timeout=600)
    text = done.stdout.decode('utf-8', 'replace')
    assert done.returncode == 0 and 'Traceback' not in text, text[-2000:]
    return text, json.loads((workspace / 'TRANSCRIPT.json').read_text(encoding='utf-8'))


def test_rehearsal_driver_w1_runs_to_a_verified_receipt_without_ever_starting_ssh(base, families):
    today_or_skip('2026-10-10')
    text, transcript = rehearse('w1', families['w1'], base / 'rehearsal-w1')
    steps = {step['step']: step for step in transcript if 'step' in step}
    assert steps['dispatcher prepare (family CLI)']['exit'] == 2 and steps['dispatcher prepare (family CLI)']['stdout']['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    resumed = steps['resume (family harness instead of ssh)']['stdout']
    assert resumed['status'] in ('KNOWN_COMPLETE', 'KNOWN_PARTIAL') and resumed['ssh_started'] is False and resumed['second_resume'] == 'REFUSED_FileExistsError'
    final = steps['status after resume']['stdout']
    assert final['verified'] is True and all(final['receipt_bindings'].values()) and final['mode'] == 'REHEARSAL'
    assert steps['refusal: real mode, rehearsal transport']['stdout']['code'] == 'REAL_SET_WITH_REHEARSAL_TRANSPORT'
    assert steps["refusal: the owner's word on a rehearsal set"]['stdout']['code'] == 'OWNER_ANSWER_IS_NOT_THE_SIGNATURE'
    assert steps['check after the dispatcher prepare']['exit'] == 1 and steps['check after the dispatcher prepare']['stdout']['verdict'] == 'VALID_ALREADY_PREPARED'
    assert steps['check after resume']['exit'] == 1 and steps['check after resume']['stdout']['verdict'] == 'VALID_GO_SPENT'
    assert list((base / 'rehearsal-w1' / 'pycache-prefix-must-stay-empty').iterdir()) == []
    assert 'REHEARSAL COMPLETE' in text and (base / 'rehearsal-w1' / 'REHEARSAL_MARKER.txt').is_file()
    config = json.loads((base / 'rehearsal-w1' / 'rehearsal-bound' / 'DISPATCH.BOUND.json').read_bytes())
    assert config['target'].endswith('.invalid') and config['owner'] == h.b.REHEARSAL_OWNER


def test_rehearsal_driver_precheck_stops_before_resume(base, families):
    today_or_skip('2026-10-05')
    text, transcript = rehearse('precheck', families['hostops'], base / 'rehearsal-precheck')
    steps = {step['step']: step for step in transcript if 'step' in step}
    assert steps['check']['stdout']['verdict'] == 'VALID_WINDOW_OPEN' and steps['dispatcher prepare (family CLI)']['stdout']['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    assert steps['status before resume']['stdout']['status'] == 'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN' and 'resume (family harness instead of ssh)' not in steps
    attempt = base / 'rehearsal-precheck' / 'rehearsal-bound' / '.dispatch-root' / 'precheck-rehearsal-once'
    assert sorted(path.name for path in attempt.iterdir()) == ['intent.json'] and 'STOP before resume' in text


def test_the_blocks_of_the_runbook_run_literally_in_rehearsal_mode(base, families, monkeypatch):
    today_or_skip('2026-10-10')
    monkeypatch.setenv('BIND_TEST_MANIFEST_MAY_BE_STALE', '1')          # the manifest of the binder is written after the tests
    result = runbook_blocks.run(base / 'rehearsal-runbook', families['w1'])
    assert result['blocks_run'] == ['verificar', 'prepare', 'publicar-pedido', 'pergunta', 'resposta', 'sign', 'check', 'publicar-ancora', 'dispatcher-prepare',
                                    'achar-intent', 'publicar-intent', 'id-e-hora', 'publish-proof', 'publicar-prova', 'status', 'arquivar']
    assert result['blocks_not_run'] == ['preparar-run', 'resume'] and len(result['blocks_parsed_by_zsh_n']) == 18 and result['fake_gh_calls'] == 6
    transcript = json.loads((base / 'rehearsal-runbook' / 'TRANSCRIPT.json').read_text(encoding='utf-8'))
    outputs = {(step['block'], step['repeat']): step['output'] for step in transcript if 'block' in step}
    assert 'JÁ FEITO' in outputs[('sign', True)] and 'NÃO É ASSINATURA' in ''.join(step['output'] for step in transcript if step.get('block') == 'resposta')


@pytest.mark.parametrize('kind', ['catalog', 'readback', 'release', 'activate'])
def test_rehearsal_driver_hostops02_runs_each_operation_to_a_verified_receipt(base, families, kind):
    """The four HOSTOPS02 rehearsals. Their clocks are injected (the operations are dated 2026-10-02..2026-10-05): they do not
    depend on the day they run, and only their command-line checks read the real clock."""
    import hostops02_fixtures as x
    arguments = ['/usr/bin/python3', '-B', str(h.BIND / 'rehearse.py'), 'hostops02-' + kind]
    for source in x.sources():
        arguments += ['--hostops02', str(source)]
    arguments += ['--hostops01', str(families['hostops']), '--w1', str(families['w1']), '--workspace', str(base / ('rehearsal-hostops02-' + kind))]
    done = subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={'PATH': '/usr/bin:/bin', 'HOME': os.environ.get('HOME', '/'),'BIND_TEST_REVIEWED_REFERENCE_ROOT':os.environ['BIND_TEST_REVIEWED_REFERENCE_ROOT']},
                          timeout=900)
    text = done.stdout.decode('utf-8', 'replace')
    assert done.returncode == 0 and 'Traceback' not in text and 'REHEARSAL COMPLETE: %s' % kind in text, text[-3000:]
    transcript = json.loads((base / ('rehearsal-hostops02-' + kind) / 'TRANSCRIPT.json').read_text(encoding='utf-8'))
    steps = [step for step in transcript if 'step' in step]
    resumes = [step for step in steps if step['step'].startswith('resume ')]
    assert resumes and all(step['result']['status'] == 'KNOWN_COMPLETE' for step in resumes)
    assert all(step['result'].get('verified') is True for step in steps if step['step'].startswith('status ') and 'result' in step)
    assert any(step.get('refused') == 'OWNER_ANSWER_IS_NOT_THE_SIGNATURE' for step in steps)
    assert any(step.get('refused') == 'REAL_SET_WITH_REHEARSAL_TRANSPORT' for step in steps)
