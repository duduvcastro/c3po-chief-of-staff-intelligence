"""HOSTOPS02 bound by bind_once.py: K2a catalog_init (A6, A9), K11 epoch_readback (M2p, M2), K10 install_release (M1, M1'),
K6a activate (M3, M3'). Synthetic only: the receipts the requests cite are produced by the cited operations' own sealed
sources on their families' emulated hosts and bound to the rehearsal host; the resumes run each operation's sealed source
on its own emulated host, through the family's dispatcher and the reviewed transport bytes; clocks are injected (these
operations are dated 2026-10-02..2026-10-05). The last test binds the whole weekend in REAL mode against a synthetic
executed reference, every citation a bound set."""
import json
import re
import os
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
import types

import pytest

import helpers as h
from helpers import refused
import hostops02_fixtures as x

b = h.b
MIN = timedelta(minutes=1)
SEC = timedelta(seconds=1)


@pytest.fixture(scope='session')
def env(tmp_path_factory, families, w1_harness):
    root = h.resolved(tmp_path_factory.mktemp('hostops02'))
    copy = x.sealed_copy(root / 'hostops02')
    h2 = x.hostops02(copy)
    h1 = x.hostops01(families['hostops'])
    precheck, provision, install, host1 = x.hostops01_receipts(h1, h2.hostemu.REVISION, with_host=True)
    work = root / 'work'
    work.mkdir(mode=0o700)
    release = x.release_bytes(h2)
    policy = x.policy_bytes(h2, release)
    override = x.override_bytes(h2, release, policy)
    files = {name: x.write_receipt(work / ('%s.receipt.json' % name), x.resealed(receipt))
             for name, receipt in (('precheck', precheck), ('provision', provision), ('install', install))}
    files['k11pre'] = x.write_receipt(work / 'k11pre.receipt.json', x.resealed(x.k11_receipt(h2, 'PRE', x.K11_PRE + 12 * MIN, release, policy)))
    files['k11post'] = x.write_receipt(work / 'k11post.receipt.json', x.resealed(x.k11_receipt(h2, 'POST', x.K11_POST + MIN, release, policy)))
    files['k10'] = x.write_receipt(work / 'k10.receipt.json', x.resealed(x.k10_receipt(h2, x.M1 + 3 * MIN, release)))
    inputs = {'release': str(x.write(work / 'release.json', release)), 'policy': str(x.write(work / 'policy.json', policy)),
              'override': str(x.write(work / 'override.json', override))}
    reference = h.rehearsal_reference(work)
    rows = precheck['items']['chains']['DATA_VOLUME']['rows']
    w1 = {name: x.w1_set(work, families['w1'], w1_harness, reference, 'rehearsal-w1-' + name, name, at, rows)
          for name, at in (('grid', x.GRID), ('sunday', x.SUNDAY), ('m0', x.M0))}
    dirs = {x.CATALOG: copy / 'catalog_init', x.RELEASE: copy / 'install_release', x.READBACK: copy / 'epoch_readback', x.ACTIVATE: copy / 'activate'}
    review = x.review_record(work, copy)
    ENV_REVIEW[0] = review['document_file']
    return types.SimpleNamespace(root=root, copy=copy, h1=h1, h2=h2, work=work, precheck=precheck, provision=provision, install=install,
                                 release=release, policy=policy, override=override, files=files, inputs=inputs, reference=reference, w1=w1,
                                 dirs=dirs, H1=str(families['hostops']), W1=str(families['w1']), review=review, families=families,
                                 w1_harness=w1_harness, host1=host1)


COUNT = [0]
ENV_REVIEW = [None]


def params_file(base, value):
    COUNT[0] += 1
    return h.write_json(Path(base) / ('P-%d.json' % COUNT[0]), value)


def bind(env, base, operation, value, name, now, mode=b.REHEARSAL, reference=None, sign_at=None):
    out = Path(base) / name
    prepared = b.prepare(env.dirs[operation], operation, params_file(base, value), reference or env.reference, out, mode, now=lambda: now)
    b.sign(out, prepared['prepare_json_sha256'], b.zulu(sign_at or now), h.answer_of(mode), now=lambda: sign_at or now)
    return out, prepared


def attempt(env, base, code, operation, value, now, mode=b.REHEARSAL, reference=None):
    out = Path(base) / ('rehearsal-attempt' if mode == b.REHEARSAL else 'attempt')
    with refused(code):
        b.prepare(env.dirs[operation], operation, params_file(base, value), reference or env.reference, out, mode, now=lambda: now)
    assert not out.exists()


def catalog_params(env, mode, label='a6', start=x.A6, **changes):
    k, host = x.catalog_host(env.h2, env.provision)
    value = x.parameters(x.CATALOG, label, start, 15, x.catalog_plan(env.h2, host, mode),
                         [x.cite('PRECHECK', x.PRECHECK, env.files['precheck'], env.H1), x.cite('PROVISION', x.PROVISION, env.files['provision'], env.H1)],
                         review=env.review)
    value.update(changes)
    return value


def readback_params(env, mode, label='m2p', start=x.K11_PRE, pre=None, **changes):
    k, host = x.readback_host(env.h2, mode, env.release)
    evidence = [x.cite('PRECHECK', x.PRECHECK, env.files['precheck'], env.H1)] + ([x.cite('M2P', x.READBACK, pre)] if pre else [])
    inputs = dict(env.inputs) if mode == 'PRE' else {'release': env.inputs['release'], 'policy': env.inputs['policy']}
    value = x.parameters(x.READBACK, label, start, 60 if mode == 'PRE' else 22, x.readback_plan(env.h2, host, mode, env.release, env.policy, env.override,
                                                                                               'M2P' if pre else None), evidence, inputs=inputs, review=env.review)
    value.update(changes)
    return value


def release_evidence(env, k11=None, sunday=None):
    return [x.cite('S1_PRECHECK', x.PRECHECK, env.files['precheck'], env.H1), x.cite('A3_PROVISION', x.PROVISION, env.files['provision'], env.H1),
            x.cite('B1_INSTALL', x.INSTALL, env.files['install'], env.H1), x.cite('SUNDAY_W1', x.W1, sunday or env.w1['sunday'], env.W1),
            x.cite('M2P', x.READBACK, k11 or env.files['k11pre'], env.dirs[x.READBACK]), x.cite('A4_PROVISION', x.PROVISION, env.files['provision'], env.H1)]


def release_params(env, label='m1', start=x.M1, **changes):
    k, host = x.release_host(env.h2)
    value = x.parameters(x.RELEASE, label, start, 15, x.release_plan(env.h2, host, env.release, 'S1_PRECHECK'), release_evidence(env),
                         signature_model='PRE', inputs={'release': env.inputs['release']}, review=env.review)
    value.update(changes)
    return value


def activate_params(env, label='m3', start=x.M3, **changes):
    k, host = x.activate_host(env.h2, env.release)
    value = x.parameters(x.ACTIVATE, label, start, 15, x.activate_plan(env.h2, host),
                         [x.cite('M2P', x.READBACK, env.files['k11pre'], env.dirs[x.READBACK])], signature_model='PRE',
                         inputs={'policy': env.inputs['policy'], 'release': env.inputs['release'], 'override': env.inputs['override']}, review=env.review)
    value.update(changes)
    return value


def gates_file(base, review=True, **items):
    """review: the co-auditor's statement that the review of the candidate suffices (the synthetic review names every
    operation, seal and payload of the tier); a dict replaces it; False leaves it out."""
    value = {'schema': b.GATES_SCHEMA}
    if review:
        value['codex_review'] = review if type(review) is dict else {'document_file': ENV_REVIEW[0], 'form': 'CANDIDATE_REVIEW_SUFFICES'}
    value.update(items)
    return h.write_json(Path(base) / ('GATES-%d.json' % len(list(Path(base).glob('GATES-*')))), value)


# ================================================================ the four operations, rehearsal mode, each to a verified receipt
def test_catalog_a6_then_a9_with_its_dispatch_gates_and_resumes_on_k2a_emulated_host(env, base):
    a6, prepared = bind(env, base, x.CATALOG, catalog_params(env, 'REHEARSAL'), 'rehearsal-a6', x.A6)
    sheet = prepared['sheet']
    assert sheet['family']['family'] == 'HOSTOPS02_CATALOG_INIT' and sheet['family']['core']['generation_sha256'] == '4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
    core = sheet['hostops02']['core']
    assert core['assembly_check']['answer'] == 'BUILD_EQUAL' and core['assembly']['source_sha256'] == sheet['source_sha256'] and core['unsealed_directories_skipped'] == []
    assert sheet['success_criterion'] == 'REHEARSAL_CATALOG_READY_VERIFIED' and sheet['hostops02']['dispatch_gates'] == ['CODEX_REVIEW_OF_THE_BOUND_SET']
    pointers = {item['plan_pointer'] for item in sheet['plan_values_equal_to_the_cited_receipts']}
    assert pointers == {'/evidence_boot_id_sha256', '/image_id', '/image_revision'}          # the revision is compared with the precheck's reading
    assert sheet['hostops02']['rules']['rows_from_the_provision_ledger'] == 4 and sheet['evidence'][0]['family']['family'] == 'HOSTOPS01'
    question = prepared['owner_question_pt']
    assert 'REHEARSAL (ensaio no servidor' in question and '<ID da imagem assinado>' in question and env.h2.hostemu.BACKEND not in question
    assert '- pasta /var/lib/c3po-bar-rehearsal-20261003a.docker-cli, root:root, modo 0700 (tem de estar ausente; será criada por esta execução e fica depois dela)' in question
    assert 'identidades assinadas (5 linhas)' in question and re.search(r'(?<![0-9a-f])801(?![0-9a-f])', question) is None and '(identidade assinada, em PREPARE.json)' in question
    assert 'a pasta real do journal não é usada; duas pastas descartáveis são criadas em /var/lib e ficam' in question and 'a produção não é tocada' not in question
    assert 'Revisão prévia do Codex sobre estes bytes: FEITA (documento sha256 %s).' % b.sha(Path(env.review['document_file']).read_bytes()) in question
    k, host = x.catalog_host(env.h2, env.provision)
    intent, proof, result, report = x.finish(a6, host, x.A6 + 30 * SEC)
    assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and report['outcome'] == 'REHEARSAL_CATALOG_READY_VERIFIED'
    # A9: the same bytes, mode REAL; the dispatch is gated on A6's receipt and on a grid read of this boot
    a9, prepared = bind(env, base, x.CATALOG, catalog_params(env, 'REAL', 'a9', x.A9), 'rehearsal-a9', x.A9)
    assert prepared['sheet']['hostops02']['dispatch_gates'] == ['K2A_REHEARSAL_RECEIPT_OF_THESE_BYTES', 'K2A_GRID_READ_PIN_NO_REBOOT', 'CODEX_REVIEW_OF_THE_BOUND_SET']
    assert 'o recibo do ensaio destes mesmos bytes' in prepared['owner_question_pt'] and 'Job Linux destes bytes: não registrado' in prepared['owner_question_pt']
    assert 'Ensaio destes mesmos bytes (A6): ainda sem recibo neste preparo' in prepared['owner_question_pt']
    checked = b.check(a9, env.dirs[x.CATALOG], now=lambda: x.A9 + MIN)
    assert checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET' and checked['dispatch_gates']['failed'] == ['GATES_FILE_NOT_GIVEN']
    gates = gates_file(base, review=x.codex_review_of(a9), rehearsal={'bound': str(a6), 'family': str(env.dirs[x.CATALOG])},
                       grid_read={'bound': str(env.w1['grid']), 'family': env.W1})
    checked = b.check(a9, env.dirs[x.CATALOG], gates, now=lambda: x.A9 + MIN)
    assert checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['dispatch_allowed_by_the_gates'] is True and checked['now_is_a_minute_to_avoid'] is False
    # a grid read taken too long before, or without its family, or a rehearsal receipt that is not complete: the gate says so
    late = b.check(a9, env.dirs[x.CATALOG], gates, now=lambda: x.GRID + 61 * MIN)
    assert 'K2A_GRID_READ:TAKEN_MINUTES_BEFORE_THE_DISPATCH' in late['dispatch_gates']['failed']
    half = b.check(a9, env.dirs[x.CATALOG], gates_file(base, rehearsal={'bound': str(a6)}, grid_read={'bound': str(env.w1['grid']), 'family': env.W1}),
                   now=lambda: x.A9 + MIN)
    assert half['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET' and half['dispatch_gates']['failed'] == ['K2A_REHEARSAL_RECEIPT:FAMILY_NOT_GIVEN']
    other = b.check(a9, env.dirs[x.CATALOG], gates_file(base, rehearsal={'bound': str(a9), 'family': str(env.dirs[x.CATALOG])},
                                                         grid_read={'bound': str(env.w1['grid']), 'family': env.W1}), now=lambda: x.A9 + MIN)
    assert other['dispatch_gates']['failed'] == ['K2A_REHEARSAL_RECEIPT:EVIDENCE_SET_WITHOUT_A_VERIFIED_RECEIPT']
    # A9's reserve on Sunday (A1 4.2): a spare of the same bytes and effects, its own day, usable only if A9 was never prepared
    sunday = x.A9.replace(day=4, hour=11, minute=30)
    a9s, prepared = bind(env, base, x.CATALOG, catalog_params(env, 'REAL', 'a9-spare', sunday, spare_of={'bound': str(a9)}), 'rehearsal-a9-spare', x.A9)
    assert prepared['sheet']['hostops02']['dispatch_gates'][-1] == 'SPARE_PRIMARY_NEVER_PREPARED'
    k, host = x.catalog_host(env.h2, env.provision)
    intent, proof, result, report = x.finish(a9, host, x.A9 + MIN)
    assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and report['outcome'] == report['success_criterion'] == 'CATALOG_READY_VERIFIED'
    assert b.check(a9, env.dirs[x.CATALOG], gates, now=lambda: x.A9 + 2 * MIN)['verdict'] == 'VALID_GO_SPENT'
    spent = b.check(a9s, env.dirs[x.CATALOG], gates, now=lambda: sunday + MIN)
    assert spent['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET' and 'SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS' in spent['dispatch_gates']['failed']


def test_readback_pre_then_post_gated_on_the_install(env, base):
    pre, prepared = bind(env, base, x.READBACK, readback_params(env, 'PRE'), 'rehearsal-m2p', x.K11_PRE)
    sheet = prepared['sheet']
    assert sheet['writes_allowed'] is False and sheet['review']['kind'] == 'CODEX_REVIEWED' and sheet['success_criterion'] == x.b.PRE_FULL_OUTCOME
    rules = sheet['hostops02']['rules']
    assert rules['rows_signed_from_cited_receipts'] == {'release': 3} and rules['image_and_revision_from'] == 'PRECHECK'
    assert set(rules['siblings']) == {'activate', 'catalog_init', 'install_release'} and rules['release_place_and_floors_are_the_siblings'] is True
    assert sheet['hostops02']['bind_inputs'] == {name: {'sha256': b.sha(raw), 'bytes': len(raw)} for name, raw in
                                                (('release', env.release), ('policy', env.policy), ('override', env.override))}
    question = prepared['owner_question_pt']
    assert 'que não grava nada mas inicia um contêiner' in question and '--name hostops02-k11-<16 primeiros hex do GO>' in question
    assert 'Revisão prévia do Codex sobre estes bytes: FEITA' in question and '- override do compose: sha256 %s (%d bytes); os bytes vão no pedido' % (
        b.sha(env.override), len(env.override)) in question
    assert 'conferida nos instantes (horário de Brasília) seg 05/10/2026 06:00:00 BRT' in question and '+00:00' not in question
    assert rules['siblings_tests'] == {'stale_recorded_seals': ['activate', 'catalog_init'], 'record': None} and 'Atenção: o registro selado das operações irmãs' in question
    k, host = x.readback_host(env.h2, 'PRE', env.release)
    intent, proof, result, report = x.finish(pre, host, x.K11_PRE + 12 * MIN)
    assert result['status'] == 'KNOWN_COMPLETE' and report['verified'] is True and report['outcome'] == x.b.PRE_FULL_OUTCOME
    # POST cites the PRE set (its observed rows) and is gated on M1's complete receipt
    post, prepared = bind(env, base, x.READBACK, readback_params(env, 'POST', 'm2', x.K11_POST, pre), 'rehearsal-m2', x.SITTING)
    assert prepared['sheet']['hostops02']['rules']['rows_signed_from_cited_receipts'] == {'release': 3, 'live': 4, 'deploy_tree': 3, 'lock_directory': 5}
    assert prepared['sheet']['hostops02']['dispatch_gates'] == ['K11_POST_AFTER_THE_COMPLETE_INSTALL']
    install = {'receipt_file': str(env.files['k10']), 'family': str(env.dirs[x.RELEASE])}
    checked = b.check(post, env.dirs[x.READBACK], gates_file(base, install=install), now=lambda: x.K11_POST + MIN)
    assert checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['dispatch_gates']['failed'] == []
    checked = b.check(post, env.dirs[x.READBACK], gates_file(base, install=dict(install, receipt_file=str(base / 'absent.json'))), now=lambda: x.K11_POST + MIN)
    assert checked['dispatch_gates']['failed'] == ['K11_INSTALL:EVIDENCE_RECEIPT_UNREADABLE']
    k, host = x.readback_host(env.h2, 'POST', env.release)
    intent, proof, result, report = x.finish(post, host, x.K11_POST + MIN)
    assert result['status'] == 'KNOWN_COMPLETE' and report['outcome'] == x.b.POST_OUTCOME and report['verified'] is True


def test_release_primary_and_spare_with_the_sunday_and_monday_gates(env, base):
    m1, prepared = bind(env, base, x.RELEASE, release_params(env), 'rehearsal-m1', x.SITTING)
    rules = prepared['sheet']['hostops02']['rules']
    assert rules['sunday_gate']['failed'] == [x.b.SUNDAY_ONLY_FAILURE] and rules['sunday_gate']['checks'] == 19
    assert rules['release_fields']['expected_from_the_full_pre']['sha256'] == b.sha(env.release) and rules['host_evidence_complete'] is True
    assert rules['linux_proof'] is None and rules['linux_proof_required'] is False
    question = prepared['owner_question_pt']
    assert 'Prova do job Linux (binding/linux_proof.py): não exigida neste ensaio.' in question and 'falhou só a que falha por construção' in question
    assert '- pasta /mnt/day-d-data/r2d2-v2-release-20261005, root:root, modo 0700 (será criada; tem de estar ausente)' in question
    assert 'Modelo de assinatura: antecipada (PRE)' in question
    assert rules['provisions_cited'] == 2 and rules['host_evidence_reason_pt'] is None and 'Motivo dado pelo operador' not in question
    assert prepared['sheet']['hostops02']['dispatch_gates'] == ['K10_M0_PREDISPATCH_DISPATCH_ALLOWED', 'CODEX_REVIEW_OF_THE_BOUND_SET']
    assert '- release: sha256 %s (%d bytes); os bytes vão no pedido' % (b.sha(env.release), len(env.release)) in question
    spare, prepared = bind(env, base, x.RELEASE, release_params(env, 'm1-spare', x.M1_SPARE, spare_of={'bound': str(m1)}), 'rehearsal-m1-spare', x.SITTING)
    assert prepared['sheet']['hostops02']['spare_of']['label'] == 'm1' and 'Limite conhecido, da regra do contrato desta operação' in prepared['owner_question_pt']
    assert json.loads(b.spare_registry(m1).read_bytes())['spare_bound'] == str(spare)
    gates = gates_file(base, m0={'bound': str(env.w1['m0']), 'family': env.W1})
    for bound_set in (m1, spare):
        checked = b.check(bound_set, env.dirs[x.RELEASE], gates, now=lambda: x.M1 - 5 * MIN)
        assert checked['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN' and checked['dispatch_gates']['failed'] == [], checked['dispatch_gates']
    with refused('GATES_NEED_THE_FAMILY'):
        b.check(m1, None, gates, now=lambda: x.M1 - 5 * MIN)
    late = b.check(m1, env.dirs[x.RELEASE], gates, now=lambda: x.M0 + 70 * MIN)
    assert 'K10_M0:M0_IS_OF_THE_SAME_DAY_AND_NOT_OLDER_THAN_AN_HOUR' in late['dispatch_gates']['failed']
    assert x.dispatcher_prepare(m1, x.M1 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    checked = b.check(spare, env.dirs[x.RELEASE], gates, now=lambda: x.M1 + 40 * SEC)
    assert checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET'
    assert checked['dispatch_gates']['failed'] == ['K10_M0:PRIMARY_WAS_NEVER_DISPATCHED', 'SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS']
    proof = b.publish_proof(m1, b.REHEARSAL_PUBLICATION, b.zulu(x.M1 + 31 * SEC), now=lambda: x.M1 + 32 * SEC)
    early = b.check(m1, env.dirs[x.RELEASE], gates, 'resume', now=lambda: x.M1 + 60 * SEC)
    assert early['verdict'] == 'VALID_BUT_RESUME_GATES_NOT_MET' and early['dispatch_gates']['failed'] == ['K10_M0:RESUME_NOT_BEFORE_NOT_BEFORE_PLUS_120_SECONDS']
    at = x.M1 + 150 * SEC
    assert b.check(m1, env.dirs[x.RELEASE], gates, 'resume', now=lambda: at)['verdict'] == 'VALID_RESUME_ALLOWED_BY_THE_GATES'
    with refused('STEP_RESUME_NOT_FOR_THIS_OPERATION'):
        b.check(env.w1['m0'], None, None, 'resume', now=lambda: at)
    state = b.signed_state(m1)
    k, host = x.release_host(env.h2)
    result = state['rt']['dispatch'].execute(str(m1 / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume', publication_path=proof['publication_proof_path'],
                                             publication_sha256=proof['publication_proof_sha256'], clock=lambda: at, monotonic=lambda: 0.0,
                                             transport=x.emulated_transport(m1, host, at))
    report = b.status(m1)
    assert result['status'] == report['status'] == 'KNOWN_COMPLETE' and report['outcome'] == x.b.RELEASE_INSTALLED_OUTCOME and report['verified'] is True


def test_activate_primary_and_spare_gated_on_the_post_readback(env, base):
    m3, prepared = bind(env, base, x.ACTIVATE, activate_params(env), 'rehearsal-m3', x.SITTING)
    rules = prepared['sheet']['hostops02']['rules']
    assert rules['override_is_the_one_the_pre_rendered'] and rules['four_values_override_and_policy_digest_reproduced'] and rules['full_pre'] == 'M2P'
    pointers = {item['plan_pointer'] for item in prepared['sheet']['plan_values_equal_to_the_cited_receipts']}
    assert {'/live_parent', '/release/parent', '/deploy_directory', '/lock/directory', '/evidence_boot_id_sha256', '/worker/image_id', '/data_root',
            '/worker/mount_target', '/policy/sha256', '/release/sha256'} <= pointers
    question = prepared['owner_question_pt']
    assert '--force-recreate r2d2-worker' in question and 'recria UM serviço' in question and 'Consequência que fica depois da execução' in question
    assert 'C3PO_R2D2_V2_LIVE_POLICY_SHA=%s' % b.sha(env.policy) in question and env.h2.hostemu.BACKEND not in question
    assert 'o contêiner antigo do trabalhador, que o docker compose remove ao recriar' in question and 'a época não começa' in question
    assert 'nenhum trabalhador roda' in question and 'decisão em aberto D2' in question and 'regra da seção 6 do DESIGN' not in question
    assert '- override do compose: sha256 %s (%d bytes); não vai no pedido' % (b.sha(env.override), len(env.override)) in question
    assert '- release: sha256 %s (%d bytes); no pedido vão só o hash e o tamanho' % (b.sha(env.release), len(env.release)) in question
    spare, prepared = bind(env, base, x.ACTIVATE, activate_params(env, 'm3-spare', x.M3_SPARE, spare_of={'bound': str(m3)}), 'rehearsal-m3-spare', x.SITTING)
    gates = gates_file(base, readback_post={'receipt_file': str(env.files['k11post']), 'family': str(env.dirs[x.READBACK])})
    checked = b.check(m3, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3 + 30 * SEC)
    assert checked['verdict'] == 'VALID_WINDOW_OPEN' and checked['dispatch_gates']['failed'] == []
    pre_as_post = b.check(m3, env.dirs[x.ACTIVATE], gates_file(base, readback_post={'receipt_file': str(env.files['k11pre']), 'family': str(env.dirs[x.READBACK])}),
                          now=lambda: x.M3 + 30 * SEC)
    assert 'K6A_READBACK_POST:COMPLETE_POST' in pre_as_post['dispatch_gates']['failed']
    k, host = x.activate_host(env.h2, env.release)
    intent, proof, result, report = x.finish(m3, host, x.M3 + 40 * SEC)
    assert result['status'] == 'KNOWN_COMPLETE' and report['outcome'] == 'ACTIVATE_WORKER_RECREATED_AND_VERIFIED' and report['verified'] is True
    checked = b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)
    assert checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET' and checked['dispatch_gates']['failed'] == ['SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS']


# ================================================================ refusals: the family, the core and the evidence
def patched_seals(monkeypatch, change):
    original = b.binder_identity

    def identity():
        found, seals = original()
        seals = json.loads(json.dumps(seals))
        change(seals)
        return found, seals
    monkeypatch.setattr(b, 'binder_identity', identity)


def resealed_directory(directory):
    """SHA256SUMS of an operation directory written again after a deliberate edit; returns its new hash."""
    directory = Path(directory)
    listed = [line[66:] for line in (directory / 'SHA256SUMS').read_text().splitlines()]
    names = sorted(set(listed) | {str(path.relative_to(directory)) for path in directory.rglob('*') if path.is_file() and path.name != 'SHA256SUMS'})
    names = [name for name in names if (directory / name).is_file()]
    raw = ''.join('%s  %s\n' % (b.sha((directory / name).read_bytes()), name) for name in names).encode()
    (directory / 'SHA256SUMS').write_bytes(raw)
    return b.sha(raw)


def test_family_core_and_assembly_refusals(env, base, monkeypatch):
    value = catalog_params(env, 'REHEARSAL')
    # an operation directory without its core beside it
    alone = base / 'alone'
    alone.mkdir()
    shutil.copytree(str(env.dirs[x.CATALOG]), str(alone / 'catalog_init'))
    with refused('CORE_NOT_FOUND'):
        b.prepare(alone / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-x', b.REHEARSAL, now=lambda: x.A6)
    # work/ and review-*/ are outside the seal and reported; any other unlisted file breaks it
    tier = base / 'tier'
    shutil.copytree(str(env.copy), str(tier))
    (tier / 'catalog_init' / 'work').mkdir()
    (tier / 'catalog_init' / 'work' / 'notes.txt').write_text('not sealed')
    (tier / 'catalog_init' / 'review-host').mkdir()
    out, prepared = None, b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-tier', b.REHEARSAL, now=lambda: x.A6)
    assert prepared['sheet']['hostops02']['core']['unsealed_directories_skipped'] == ['review-host', 'work']
    (tier / 'catalog_init' / 'stray.txt').write_text('x')
    with refused('FAMILY_FILE_SET'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    (tier / 'catalog_init' / 'stray.txt').unlink()
    (tier / 'catalog_init' / 'work.txt').write_text('a file named like the directory is not the directory')
    with refused('FAMILY_FILE_SET'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    (tier / 'catalog_init' / 'work.txt').unlink()
    # the core: an extra file, a changed file, another list, an invalid list, another generation
    (tier / 'core' / 'extra.py').write_text('x = 1\n')
    with refused('CORE_FILE_SET'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    (tier / 'core' / 'extra.py').unlink()
    (tier / 'core' / 'linux_root' / 'SHAPES.linux-root.json').write_text('{}')          # what the core's Linux job writes is not listed
    (tier / 'core' / 'tests' / 'family.py').write_text((tier / 'core' / 'tests' / 'family.py').read_text() + '\n# edited\n')
    with refused('CORE_HASH'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    shutil.copy2(str(env.copy / 'core' / 'tests' / 'family.py'), str(tier / 'core' / 'tests' / 'family.py'))
    sums = tier / 'core' / 'CORE_SHA256SUMS'
    original = sums.read_bytes()
    sums.write_bytes(original + b'\n')
    with refused('CORE_SEAL_NOT_ACCEPTED'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    sums.write_bytes(b'not a list\n')
    patched_seals(monkeypatch, lambda seals: [item['core'].update(sha256sums_sha256=b.sha(b'not a list\n')) for item in seals if 'core' in item])
    with refused('CORE_SUMS_INVALID'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    sums.write_bytes(original)
    monkeypatch.undo()
    patched_seals(monkeypatch, lambda seals: [item['core'].update(generation_sha256='e' * 64) for item in seals if 'core' in item])
    with refused('CORE_GENERATION_NOT_THE_SOURCES'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    monkeypatch.undo()
    # the operation directory: an assembly record that is not the build, a build that is not the assembly of the core
    shutil.rmtree(str(tier / 'catalog_init' / 'work'))
    shutil.rmtree(str(tier / 'catalog_init' / 'review-host'))
    record = tier / 'catalog_init' / 'build' / 'ASSEMBLY.json'
    saved = record.read_bytes()
    record.write_bytes(saved.replace(b'"source_bytes": 119374', b'"source_bytes": 1'))
    record_seal = resealed_directory(tier / 'catalog_init')
    patched_seals(monkeypatch, lambda seals: [item.update(sha256sums_sha256=record_seal) for item in seals if item['family'] == 'HOSTOPS02_CATALOG_INIT'])
    with refused('CORE_ASSEMBLY_CHECK_FAILED'):          # the record agrees on every pinned hash; only the core's own check sees the difference
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    record.write_bytes(saved.replace(b'"operation": "GO_WRITE_HOSTOPS02_CATALOG_INIT_01"', b'"operation": "GO_WRITE_HOSTOPS02_OTHER_01"'))
    record_seal = resealed_directory(tier / 'catalog_init')
    monkeypatch.undo()
    patched_seals(monkeypatch, lambda seals: [item.update(sha256sums_sha256=record_seal) for item in seals if item['family'] == 'HOSTOPS02_CATALOG_INIT'])
    with refused('ASSEMBLY_RECORD_NOT_THE_BUILD'):
        b.prepare(tier / 'catalog_init', x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    monkeypatch.undo()
    # an operation of a HOSTOPS02 seal that this binder has no rules for
    monkeypatch.setattr(b, 'HOSTOPS02', {key: item for key, item in b.HOSTOPS02.items() if key != x.CATALOG})
    with refused('HOSTOPS02_OPERATION_WITHOUT_BINDING_RULES'):
        b.prepare(env.dirs[x.CATALOG], x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    monkeypatch.undo()
    # a rule that meets a receipt it cannot read
    monkeypatch.setitem(b.RULES_OF, x.CATALOG, lambda ctx: {}['absent'])
    with refused('HOSTOPS02_RULE_INPUT_MALFORMED'):
        b.prepare(env.dirs[x.CATALOG], x.CATALOG, params_file(base, value), env.reference, base / 'rehearsal-y', b.REHEARSAL, now=lambda: x.A6)
    assert not (base / 'rehearsal-y').exists()


def test_evidence_of_other_families_and_inputs(env, base):
    value = catalog_params(env, 'REHEARSAL')
    attempt(env, base, 'EVIDENCE_FAMILY_NOT_AN_ACCEPTED_SEAL', x.CATALOG, dict(value, evidence=[dict(value['evidence'][0], family=str(base)), value['evidence'][1]]), x.A6)
    attempt(env, base, 'EVIDENCE_OPERATION_NOT_IN_THIS_FAMILY', x.CATALOG,
            dict(value, evidence=[{k: v for k, v in value['evidence'][0].items() if k != 'family'}, value['evidence'][1]]), x.A6)
    attempt(env, base, 'PARAMETERS_INVALID', x.CATALOG, dict(value, inputs={}), x.A6)                    # K2a takes no input file
    attempt(env, base, 'PARAMETERS_INVALID', x.CATALOG, dict(value, linux_proof={}), x.A6)          # the junit proof is K10's
    attempt(env, base, 'OWNER_SUMMARY_IS_FIXED_FOR_THIS_OPERATION', x.CATALOG, dict(value, owner_summary_pt='a summary the operator would type here'), x.A6)
    pre = readback_params(env, 'PRE')
    attempt(env, base, 'BIND_INPUTS_INVALID', x.READBACK, dict(pre, inputs=dict(pre['inputs'], secret=env.inputs['release'])), x.K11_PRE)
    attempt(env, base, 'BIND_INPUT_UNREADABLE', x.READBACK, dict(pre, inputs=dict(pre['inputs'], policy=str(base / 'absent.json'))), x.K11_PRE)
    plan = json.loads(json.dumps(pre['plan']))
    for marker in ({'$input': 'policy', 'as': 'md5'}, {'$input': 'policy', 'as': 'member', 'member': 'absent'}, {'$input': 'policy', 'as': 'b64', 'member': 'x'},
                   {'$input': 'override', 'as': 'member', 'member': 'services'}):
        plan['policy']['sha256'] = marker
        attempt(env, base, 'PLAN_INPUT_INVALID', x.READBACK, dict(pre, plan=plan), x.K11_PRE)
    plan['policy']['sha256'] = b.sha(env.policy)          # typed, not taken from the input file
    attempt(env, base, 'PLAN_MEMBER_NOT_FROM_ITS_INPUT_FILE', x.READBACK, dict(pre, plan=plan), x.K11_PRE)
    attempt(env, base, 'BIND_INPUT_NOT_USED', x.READBACK, dict(readback_params(env, 'POST', 'm2', x.K11_POST), inputs=dict(env.inputs)), x.SITTING)
    # a window whose dispatch minutes are all minutes to avoid
    attempt(env, base, 'GATE_WINDOW_ONLY_IN_MINUTES_TO_AVOID', x.READBACK,
            dict(pre, not_before=b.zulu(x.K11_PRE.replace(minute=10)), not_after=b.zulu(x.K11_PRE.replace(minute=25, second=50))), x.K11_PRE.replace(minute=0))


def test_catalog_rule_refusals(env, base):
    def provision_changed(change):
        return x.write_receipt(base / ('provision-%d.json' % COUNT[0]), x.resealed(env.provision, change=change))

    value = catalog_params(env, 'REHEARSAL')
    partial = provision_changed(lambda r: r.update(status='PARTIAL_METADATA_REQUIRES_REVIEW'))
    attempt(env, base, 'CATALOG_EVIDENCE_INCOMPLETE', x.CATALOG,
            dict(value, evidence=[value['evidence'][0], dict(x.cite('PROVISION', x.PROVISION, partial, env.H1), accept_not_complete=True)]), x.A6)
    for code, change in (('EVIDENCE_NOT_OF_THE_SAME_BOOT', lambda r: r['effects'].update(evidence_boot_id_sha256='e' * 64)),
                         ('RETENTION_TAG_NOT_THE_SIGNED_IMAGE', lambda r: r['retention_tag'].update(image_id='sha256:' + 'e' * 64)),
                         ('PROVISION_LEDGER_ROW_NOT_FOUND', lambda r: r.update(ledger=[row for row in r['ledger'] if row['key'] != 'SUP_JOURNAL']))):
        attempt(env, base, code, x.CATALOG, dict(value, evidence=[value['evidence'][0], x.cite('PROVISION', x.PROVISION, provision_changed(change), env.H1)]), x.A6)
    plan = json.loads(json.dumps(value['plan']))
    rows = {row['key']: row for row in env.provision['ledger']}
    typed = env.precheck['items']['chains']['ETC']['rows'] + [
        {'path': rows[key]['path'], 'device': rows[key]['observed']['device'], 'inode': rows[key]['observed']['inode'] + (1 if key == 'SUP_DOCKER_CLI' else 0),
         'uid': 0, 'gid': 0, 'mode': 0o700} for key in ('SUP_CONFIG', 'SUP_DOCKER_CLI')]
    plan['docker_config_chain'] = typed          # typed, with one inode that is not the ledger's
    attempt(env, base, 'CATALOG_CHAIN_NOT_THE_RECEIPTS_ROWS', x.CATALOG, dict(value, plan=plan), x.A6)
    for marker in ({'$ledger_row': {'evidence': 'PRECHECK', 'path': '/etc/c3po-bar', 'key': 'SUP_CONFIG'}}, {'$concat': []}, {'$concat': ['x']},
                   {'$source': 'NOT_A_CONSTANT'}, {'$source': 'Pins'}):
        attempt(env, base, 'PLAN_REFERENCE_INVALID', x.CATALOG, dict(value, plan=dict(value['plan'], docker_config_chain=marker)), x.A6)
    attempt(env, base, 'PROVISION_LEDGER_ROW_NOT_FOUND', x.CATALOG, dict(value, plan=dict(value['plan'], docker_config_chain={'$concat': [
        [x.ledger('/etc/c3po-bar/absent', 'SUP_CONFIG')]]})), x.A6)
    real = catalog_params(env, 'REAL', 'a9', x.A9)
    attempt(env, base, 'RELEASE_TREE_UNREADABLE', x.CATALOG, dict(real, release_tree=str(base / 'no-tree')), x.A9)
    tree = x.release_tree(base / 'tree', env.h2)
    readme = tree / 'c3po' / 'deployment' / 'massive-supervisor' / 'README.md'
    saved = readme.read_text()
    readme.write_text(saved.replace('import json', 'import  json'))
    attempt(env, base, 'SCRIPT_NOT_THE_READMES', x.CATALOG, dict(real, release_tree=str(tree)), x.A9)
    readme.write_text(saved)
    assembler = tree / 'c3po' / 'backend' / 'app' / 'r2d2_v2_epoch_assembler.py'
    assembler.write_text(assembler.read_text().replace('SHADOW', 'DIAG'))
    attempt(env, base, 'EPOCH_NOT_THE_RELEASES', x.CATALOG, dict(real, release_tree=str(tree)), x.A9)
    assembler.write_text("EPOCH = 'R2D2-V2-SHADOW-2026-10-05'\n")
    attempt(env, base, 'LINUX_JOB_RECORD_UNREADABLE', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'LINUX_JOB_PASSED', 'document_file': str(base / 'none')}), x.A9)
    attempt(env, base, 'PARAMETERS_INVALID', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'TRUST_ME', 'document_file': str(env.review['document_file'])}), x.A9)
    # the Linux job: no owner waiver (neither contract allows one), and the record must be of THESE bytes and of the core
    attempt(env, base, 'PARAMETERS_INVALID', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'OWNER_WAIVED', 'document_file': env.review['document_file']}), x.A9)
    junk = x.write(base / 'junk-job.txt', b'this file names no hash and no operation\n')
    attempt(env, base, 'LINUX_JOB_RECORD_NOT_OF_THESE_BYTES', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'LINUX_JOB_PASSED', 'document_file': str(junk)}), x.A9)
    hashes, core = x.tier_hashes(env.copy)
    no_core = x.write(base / 'job-without-core.txt', ('seal %s source %s\n' % hashes['catalog_init'][1:3]).encode())
    attempt(env, base, 'LINUX_JOB_RECORD_NOT_OF_THESE_BYTES', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'LINUX_JOB_PASSED', 'document_file': str(no_core)}), x.A9)
    other = x.write(base / 'job-of-the-superseded-seal.txt', ('core %s seal %s source %s\n' % (core, '8b2bced33c01be75605838bf3a31e7f5dd3a65cd9cc34e245bbcd55fea3f38a9',
                                                                                                     hashes['catalog_init'][2])).encode())
    attempt(env, base, 'LINUX_JOB_RECORD_NOT_OF_THESE_BYTES', x.CATALOG, dict(real, release_tree=str(tree), linux_job={'kind': 'LINUX_JOB_PASSED', 'document_file': str(other)}), x.A9)
    # the README's command (K2a CONTRACT 5 step 4), compared word by word with the effects
    for name, command, code in (('no-command', '', 'README_COMMAND_NOT_FOUND'),
                                ('two-commands', x.README_COMMAND + x.README_COMMAND, 'README_COMMAND_NOT_FOUND'),
                                ('unbalanced', x.README_COMMAND.replace('"$epoch"', '"$epoch'), 'README_COMMAND_NOT_FOUND'),
                                ('no-redirect', x.README_COMMAND.replace(' < catalog-init.py', ''), 'README_COMMAND_NOT_FOUND'),
                                ('network-host', x.README_COMMAND.replace('--network none', '--network host'), 'DOCKER_ARGUMENTS_NOT_THE_READMES'),
                                ('other-config', x.README_COMMAND.replace('DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli', 'DOCKER_CONFIG=/root/.docker'), 'DOCKER_ARGUMENTS_NOT_THE_READMES'),
                                ('other-stdin', x.README_COMMAND.replace('< catalog-init.py', '< other.py'), 'DOCKER_ARGUMENTS_NOT_THE_READMES')):
        variant = x.release_tree(base / ('tree-' + name), env.h2, command=command)
        (variant / 'c3po' / 'backend' / 'app' / 'r2d2_v2_epoch_assembler.py').write_text("EPOCH = 'R2D2-V2-SHADOW-2026-10-05'\n")
        attempt(env, base, code, x.CATALOG, dict(real, release_tree=str(variant)), x.A9)
    # with both, in rehearsal mode, the question says so
    job = {'kind': 'LINUX_JOB_PASSED', 'document_file': env.review['document_file']}
    out, prepared = bind(env, base, x.CATALOG, dict(real, release_tree=str(tree), linux_job=job), 'rehearsal-a9-tree', x.A9)
    rules = prepared['sheet']['hostops02']['rules']
    assert rules['release_tree']['epoch_is_the_releases'] is True and rules['release_tree']['docker_arguments_are_the_readmes']['words'] == 24
    assert rules['linux_job']['names_these_bytes'] == ['core', 'final_payload_unbound', 'seal', 'source']
    assert 'Job Linux destes bytes: APROVADO segundo o registro de sha256' in prepared['owner_question_pt'] and 'o comando docker é o do README' in prepared['owner_question_pt']
    # the A6 rehearsal stand-in for the comparison: the rehearsal's own effects agree with the README too
    a6 = catalog_params(env, 'REHEARSAL', 'a6-tree', release_tree=str(tree))
    out, prepared = bind(env, base, x.CATALOG, a6, 'rehearsal-a6-tree', x.A6)
    assert prepared['sheet']['hostops02']['rules']['release_tree']['docker_arguments_are_the_readmes']['words'] == 24


def test_readback_rule_refusals(env, base, monkeypatch):
    pre = readback_params(env, 'PRE')
    other_boot = x.write_receipt(base / 'provision-other-boot.json', x.resealed(env.provision, change=lambda r: r['effects'].update(evidence_boot_id_sha256='e' * 64)))
    attempt(env, base, 'EVIDENCE_NOT_OF_THE_SAME_BOOT', x.READBACK, dict(pre, evidence=pre['evidence'] + [x.cite('PROVISION', x.PROVISION, other_boot, env.H1)]), x.K11_PRE)
    plan = json.loads(json.dumps(pre['plan']))
    plan['release']['parent']['rows'] = env.precheck['items']['chains']['DATA_VOLUME']['rows']
    for key, pointer in (('evidence_boot_id_sha256', '/items/boot/boot_id_sha256'),):
        plan[key] = env.precheck['items']['boot']['boot_id_sha256']
    plan['image']['image_id'] = env.precheck['items']['image']['id']
    plan['revision'] = env.precheck['items']['image']['revision_label']
    attempt(env, base, 'IMAGE_WITHOUT_A_CITED_READ', x.READBACK, dict(pre, plan=plan, evidence=[x.cite('PROVISION', x.PROVISION, env.files['provision'], env.H1)]),
            x.K11_PRE)
    attempt(env, base, 'READBACK_EVIDENCE_WITHOUT_A_BOOT', x.READBACK, dict(pre, plan=plan, evidence=[x.cite('W1', x.W1, env.w1['sunday'], env.W1)]), x.K11_PRE)
    changed = json.loads(json.dumps(pre['plan']))
    changed['image']['image_id'] = 'sha256:' + 'e' * 64
    attempt(env, base, 'IMAGE_NOT_THE_ONE_OF_THE_CITED_READ', x.READBACK, dict(pre, plan=changed), x.K11_PRE)
    changed = json.loads(json.dumps(pre['plan']))
    k, host = x.readback_host(env.h2, 'PRE', env.release)
    changed['live']['parent']['rows'] = env.h2.hostemu.rows(host, env.h2.k11.LIVE_PARENT)          # typed rows that no cited receipt holds
    attempt(env, base, 'PLAN_ROWS_NOT_THE_ROWS_OF_A_CITED_RECEIPT', x.READBACK, dict(pre, plan=changed), x.K11_PRE)
    changed = json.loads(json.dumps(pre['plan']))
    changed['limits']['data_volume_free_bytes'] = 2 * 1048576
    attempt(env, base, 'LIMITS_NOT_THE_SIBLINGS_FLOORS', x.READBACK, dict(pre, plan=changed), x.K11_PRE)
    post = readback_params(env, 'POST', 'm2', x.K11_POST)
    post['evidence'] = [post['evidence'][0]]
    other = x.write(base / 'release-other-revision.json', env.h2.k11.release_bytes(code_revision='e' * 40))
    typed = json.loads(json.dumps(post['plan']))
    k, host = x.readback_host(env.h2, 'POST', env.release)
    typed['live']['parent']['rows'] = env.h2.hostemu.rows(host, env.h2.k11.LIVE_PARENT)
    attempt(env, base, 'PLAN_ROWS_NOT_THE_ROWS_OF_A_CITED_RECEIPT', x.READBACK, dict(post, plan=typed), x.SITTING)          # rows only a PRE holds
    plan = json.loads(json.dumps(post['plan']))
    for chain in (plan['live']['parent'], plan['deploy']['tree'], plan['deploy']['lock_directory']):
        chain['rows'] = None
    plan.update(revision=env.precheck['items']['image']['revision_label'], package_sha256=json.loads(env.release)['implementation_package_sha'])          # typed
    other_policy = x.write(base / 'policy-other-release.json', env.h2.k11.policy_bytes(other.read_bytes()))
    attempt(env, base, 'REVISION_NOT_THE_RELEASES', x.READBACK, dict(post, plan=plan, inputs=dict(post['inputs'], release=str(other), policy=str(other_policy))),
            x.SITTING)
    # a K11 whose siblings are not the sealed ones beside it
    lone = base / 'lone'
    lone.mkdir()
    for name in ('core', 'epoch_readback'):
        shutil.copytree(str(env.copy / name), str(lone / name))
    with refused('SIBLINGS_NOT_THE_SEALED_SIBLINGS'):
        b.prepare(lone / 'epoch_readback', x.READBACK, params_file(base, pre), env.reference, base / 'rehearsal-x', b.REHEARSAL, now=lambda: x.K11_PRE)
    monkeypatch.setattr(b, 'siblings_of', lambda ctx: ({}, {'install_release': types.SimpleNamespace(DATA_VOLUME='/mnt/other', RELEASE_DIRECTORY_NAME='x',
                                                                                                      RELEASE_FILE_NAME='y', FREE_BYTES_FLOOR=1),
                                                            'activate': types.SimpleNamespace(FREE_BYTES_FLOOR=1, FREE_INODES_FLOOR=8)}))
    attempt(env, base, 'RELEASE_PLACE_NOT_THE_SIBLINGS', x.READBACK, pre, x.K11_PRE)


def test_release_rule_refusals(env, base, monkeypatch):
    value = release_params(env)
    attempt(env, base, 'RELEASE_EVIDENCE_INCOMPLETE', x.RELEASE, dict(value, evidence=value['evidence'][:2] + value['evidence'][3:]), x.SITTING)
    post_file = x.cite('M2P', x.READBACK, env.files['k11post'], env.dirs[x.READBACK])
    attempt(env, base, 'RELEASE_NOT_VERIFIED_BY_A_FULL_PRE', x.RELEASE, dict(value, evidence=value['evidence'][:4] + [post_file]), x.SITTING)
    moved = x.write_receipt(base / 'k11pre-other-parent.json', x.resealed(json.loads(env.files['k11pre'].read_bytes()),
                                                                           change=lambda r: r['effects']['release']['parent'].update(chain_sha256='e' * 64)))
    attempt(env, base, 'RELEASE_PARENT_NOT_THE_ONE_THE_PRE_READ', x.RELEASE,
            dict(value, evidence=value['evidence'][:4] + [x.cite('M2P', x.READBACK, moved, env.dirs[x.READBACK])]), x.SITTING)
    other = x.write(base / 'release-other.json', env.h2.k11.release_bytes(authorization_ref='ANOTHER_SYNTHETIC_RELEASE'))
    attempt(env, base, 'RELEASE_FIELDS_RELEASE_SHA256_NOT_THE_EXPECTED_HASH', x.RELEASE, dict(value, inputs={'release': str(other)}), x.SITTING)
    h.COVERED.add('RELEASE_FIELDS_')
    attempt(env, base, 'RELEASE_SUNDAY_READ_NOT_A_BOUND_SET', x.RELEASE,
            dict(value, evidence=value['evidence'][:3] + [x.cite('SUNDAY_W1', x.W1, env.w1['sunday'] / '.dispatch-root' / 'sunday-once' / 'stdout.private.json', env.W1)]
                 + value['evidence'][4:]), x.SITTING)
    rows = env.precheck['items']['chains']['DATA_VOLUME']['rows']
    other_rows = x.w1_set(base, env.families['w1'], env.w1_harness, env.reference, 'rehearsal-w1-other-rows', 'other-rows', x.SUNDAY,
                          [dict(row, inode=row['inode'] + 1) if row['path'] == '/mnt/day-d-data' else row for row in rows])
    attempt(env, base, 'RELEASE_SUNDAY_GATE_FAILED', x.RELEASE, dict(value, evidence=release_evidence(env, sunday=other_rows)), x.SITTING)
    junit = x.linux_junit_pair(base, env.h2)
    (base / 'bad.xml').write_text('<testsuites/>')
    attempt(env, base, 'LINUX_PROOF_NOT_ACCEPTED', x.RELEASE, dict(value, linux_proof=dict(junit, user_junit=str(base / 'bad.xml'))), x.SITTING)
    attempt(env, base, 'LINUX_PROOF_NOT_ACCEPTED', x.RELEASE, dict(value, linux_proof=dict(junit, user_junit=junit['root_junit'])), x.SITTING)
    out, prepared = bind(env, base, x.RELEASE, dict(value, linux_proof=junit), 'rehearsal-m1-proof', x.SITTING)
    proof = prepared['sheet']['hostops02']['rules']['linux_proof']
    assert proof['decision'] == 'LINUX_PROOF_ACCEPTED' and 'Prova do job Linux (binding/linux_proof.py): ACEITA' in prepared['owner_question_pt']
    # the tool's member differs from the plan's (a tool other than the sealed one would say so)
    original = b.binding_tool

    def tool(family, name):
        module, digest = original(family, name)
        if name == 'release_fields.py':
            judged = module.judged
            module.judged = lambda *args: (dict(judged(*args)[0], path='/elsewhere'), judged(*args)[1])
        return module, digest
    monkeypatch.setattr(b, 'binding_tool', tool)
    attempt(env, base, 'RELEASE_MEMBER_NOT_THE_TOOLS', x.RELEASE, value, x.SITTING)
    monkeypatch.undo()
    # a sealed directory without one of its tools
    tier = base / 'tier'
    shutil.copytree(str(env.copy), str(tier))
    (tier / 'install_release' / 'binding' / 'predispatch.py').unlink()
    seal = resealed_directory(tier / 'install_release')
    patched_seals(monkeypatch, lambda seals: [item.update(sha256sums_sha256=seal) for item in seals if item['family'] == 'HOSTOPS02_INSTALL_RELEASE'])
    with refused('REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES'):          # the review names the accepted seal, not this one
        b.prepare(tier / 'install_release', x.RELEASE, params_file(base, value), env.reference, base / 'rehearsal-x', b.REHEARSAL, now=lambda: x.SITTING)
    review = x.write(base / 'review-of-the-resealed.txt', ('seal %s final %s\n' % (seal, x.tier_hashes(env.copy)[0]['install_release'][3])).encode())
    with refused('BINDING_TOOL_MISSING'):
        b.prepare(tier / 'install_release', x.RELEASE, params_file(base, dict(value, review={'kind': 'CODEX_REVIEWED', 'document_file': str(review)})),
                  env.reference, base / 'rehearsal-x', b.REHEARSAL, now=lambda: x.SITTING)


def test_activate_rule_refusals(env, base):
    value = activate_params(env)
    k11pre = json.loads(env.files['k11pre'].read_bytes())
    for code, change in (('LIVE_PARENT_NOT_ACCEPTABLE_TO_A_WRITE', lambda r: r['items']['directory:LIVE_PARENT'].update(setgid=True)),
                         ('ACTIVATE_NOT_WHAT_THE_PRE_RENDERED', lambda r: r['effects']['render'].update(override_sha256='e' * 64)),
                         ('POLICY_NOT_VERIFIED_AT_THIS_GATE', lambda r: r['effects']['policy'].update(valid_at=['2026-10-05T13:30:00+00:00'])),
                         ('ACTIVATE_EVIDENCE_NOT_ONE_FULL_PRE', lambda r: r['effects'].update(rows_in_receipt=False))):
        path = x.write_receipt(base / ('k11pre-%s.json' % code.lower()), x.resealed(k11pre, change=change))
        attempt(env, base, code, x.ACTIVATE, dict(value, evidence=[x.cite('M2P', x.READBACK, path, env.dirs[x.READBACK])]), x.SITTING)
    attempt(env, base, 'OVERRIDE_FILE_NOT_THE_ONE_ACTIVATE_WRITES', x.ACTIVATE, dict(value, inputs=dict(value['inputs'], override=env.inputs['policy'])), x.SITTING)
    attempt(env, base, 'OVERRIDE_FILE_NOT_THE_ONE_ACTIVATE_WRITES', x.ACTIVATE,
            dict(value, inputs={key: item for key, item in value['inputs'].items() if key != 'override'}), x.SITTING)
    # the independent computation: a request whose effects say other values than the ones computed here
    out, prepared = bind(env, base, x.ACTIVATE, value, 'rehearsal-m3-rule', x.SITTING)
    state = b.signed_state(out)
    request = json.loads(state['files']['REQUEST.BOUND.json'])
    effects = json.loads(state['files']['EFFECTS.json'])
    effects['recreate']['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA'] = 'e' * 64
    pre = json.loads(env.files['k11pre'].read_bytes())
    pre['effects']['render']['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA'] = 'e' * 64
    ctx = {'plan': request['plan'], 'effects': effects, 'entries': request['evidence'], 'receipts': {'M2P': pre},
           'evidence_facts': [{'role': 'M2P', 'complete': True}], 'inputs': {'policy': env.policy, 'release': env.release, 'override': env.override},
           'window': state['window']}
    with refused('ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED'):
        b.activate_rules(ctx)
    ctx['plan'] = dict(request['plan'], data_root='/elsewhere')
    with refused('ACTIVATE_DERIVED_VALUES_NOT_REPRODUCED'):
        b.activate_rules(dict(ctx, effects=json.loads(state['files']['EFFECTS.json']), receipts={'M2P': json.loads(env.files['k11pre'].read_bytes())}))


def test_spare_refusals(env, base):
    m3, prepared = bind(env, base, x.ACTIVATE, activate_params(env), 'rehearsal-m3', x.SITTING)
    value = activate_params(env, 'm3-spare', x.M3_SPARE, spare_of={'bound': str(m3)})
    attempt(env, base, 'SPARE_PRIMARY_NOT_A_SIGNED_SET', x.ACTIVATE, dict(value, spare_of={'bound': str(base)}), x.SITTING)
    attempt(env, base, 'PARAMETERS_INVALID', x.ACTIVATE, dict(value, spare_of={'bound': str(m3), 'label': 'x'}), x.SITTING)
    attempt(env, base, 'SPARE_PRIMARY_NOT_OF_THIS_OPERATION', x.ACTIVATE, dict(value, label='m3'), x.SITTING)
    attempt(env, base, 'SPARE_PRIMARY_NOT_OF_THIS_OPERATION', x.ACTIVATE, dict(value, spare_of={'bound': str(env.w1['m0'])}), x.SITTING)
    attempt(env, base, 'SPARE_WINDOW_NOT_AFTER_THE_PRIMARY', x.ACTIVATE, activate_params(env, 'm3-spare', x.M3, spare_of={'bound': str(m3)}), x.SITTING)
    plan = json.loads(json.dumps(value['plan']))
    plan['override_name'] = 'compose.override.spare.json'          # another name: other effects, though the PRE rendered the same bytes
    attempt(env, base, 'SPARE_EFFECTS_NOT_THE_PRIMARYS', x.ACTIVATE, dict(value, plan=plan), x.SITTING)
    spare, prepared = bind(env, base, x.ACTIVATE, value, 'rehearsal-m3-spare', x.SITTING)
    attempt(env, base, 'SPARE_PRIMARY_NOT_OF_THIS_OPERATION', x.ACTIVATE,
            activate_params(env, 'm3-spare2', x.M3.replace(hour=13, minute=30), spare_of={'bound': str(spare)}), x.SITTING)          # no spare of a spare
    # one spare per primary: a second one is refused, before or after the primary was prepared
    attempt(env, base, 'SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY', x.ACTIVATE,
            activate_params(env, 'm3-spare3', x.M3.replace(hour=13, minute=30), spare_of={'bound': str(m3)}), x.SITTING)
    assert x.dispatcher_prepare(m3, x.M3 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    attempt(env, base, 'SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY', x.ACTIVATE, activate_params(env, 'm3-spare3', x.M3_SPARE, spare_of={'bound': str(m3)}), x.M3 + MIN)
    # a primary prepared by the dispatcher cannot have a spare bound while it can still be sent (here a second primary, m3b)
    m3b, prepared = bind(env, base, x.ACTIVATE, activate_params(env, 'm3b'), 'rehearsal-m3b', x.SITTING)
    assert x.dispatcher_prepare(m3b, x.M3 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    attempt(env, base, 'SPARE_PRIMARY_ALREADY_PREPARED', x.ACTIVATE, activate_params(env, 'm3b-spare', x.M3_SPARE, spare_of={'bound': str(m3b)}), x.M3 + MIN)
    moved = base / 'moved'
    moved.mkdir()
    shutil.copytree(str(m3), str(moved / 'rehearsal-m3'))
    shutil.rmtree(str(m3))
    attempt(env, base, 'SPARE_PRIMARY_CLAIM_ROOT_NOT_FOUND', x.ACTIVATE,
            activate_params(env, 'm3-spare4', x.M3_SPARE, spare_of={'bound': str(moved / 'rehearsal-m3')}), x.M3 + MIN)
    gates = gates_file(base, readback_post={'receipt_file': str(env.files['k11post']), 'family': str(env.dirs[x.READBACK])})
    checked = b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)          # the primary is no longer where the spare names it
    assert checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET' and checked['dispatch_gates']['failed'] == ['SPARE:PRIMARY_SET_UNREADABLE:BOUND_NOT_FOUND']


def test_check_gates_refusals(env, base, monkeypatch):
    pre, prepared = bind(env, base, x.READBACK, readback_params(env, 'PRE'), 'rehearsal-m2p', x.K11_PRE)
    with refused('GATES_NOT_DEFINED_FOR_THIS_SET'):
        b.check(pre, None, gates_file(base, install={}), now=lambda: x.K11_PRE + MIN)
    with refused('GATES_NOT_DEFINED_FOR_THIS_SET'):          # a set of the earlier families has no gates
        b.check(env.w1['m0'], None, gates_file(base, m0={}), now=lambda: x.M0)
    m1, prepared = bind(env, base, x.RELEASE, release_params(env), 'rehearsal-m1', x.SITTING)
    for raw in (b'not json', b'{"schema":"OTHER"}', json.dumps({'schema': b.GATES_SCHEMA, 'unknown': {}}).encode(), json.dumps({'schema': b.GATES_SCHEMA, 'm0': []}).encode()):
        (base / 'bad-gates.json').write_bytes(raw)
        with refused('GATES_FILE_INVALID'):
            b.check(m1, env.dirs[x.RELEASE], base / 'bad-gates.json', now=lambda: x.M1 - 5 * MIN)
    gates = gates_file(base, m0={'bound': str(env.w1['m0']), 'family': env.W1})
    original = b.binding_tool
    monkeypatch.setattr(b, 'binding_tool', lambda family, name: (original(family, name)[0], 'e' * 64))
    with refused('BINDING_TOOL_NOT_THE_ONE_OF_THE_PREPARE'):
        b.check(m1, env.dirs[x.RELEASE], gates, now=lambda: x.M1 - 5 * MIN)
    monkeypatch.undo()
    not_bound = b.check(m1, env.dirs[x.RELEASE], gates_file(base, m0={'receipt_file': str(env.w1['m0'] / '.dispatch-root' / 'm0-once' / 'stdout.private.json'),
                                                                       'family': env.W1}), now=lambda: x.M1 - 5 * MIN)
    assert not_bound['dispatch_gates']['failed'] == ['K10_M0:NOT_A_BOUND_SET']
    # the receipts the request cites are read again at check: gone, the gate cannot be evaluated
    params = json.loads((m1 / 'PARAMETERS.json').read_bytes())
    receipt = Path(params['evidence'][0]['receipt_file'])
    saved = receipt.read_bytes()
    receipt.unlink()
    try:
        with refused('CITED_RECEIPTS_NOT_FOUND_AGAIN'):
            b.check(m1, env.dirs[x.RELEASE], gates, now=lambda: x.M1 - 5 * MIN)
    finally:
        receipt.write_bytes(saved)
        receipt.chmod(0o600)


def test_sealed_copy_and_what_is_derived_again(env, base, monkeypatch):
    result = b.sealed_copy(base / 'copy', [str(env.copy)])
    assert result['status'] == 'SEALED_COPY_WRITTEN' and set(result['directories']) == {'core', 'catalog_init', 'install_release', 'epoch_readback', 'activate'}
    assert all(item['files_taken_from_a_later_source'] == [] for item in result['directories'].values())
    with refused('OUT_EXISTS_OR_PARENT_MISSING'):
        b.sealed_copy(base / 'copy', [str(env.copy)])
    with refused('SEALED_COPY_SOURCE_NOT_FOUND'):
        b.sealed_copy(base / 'copy2', [str(base / 'empty-source')])
    (base / 'empty-source').mkdir()
    with refused('SEALED_COPY_SOURCE_NOT_FOUND'):
        b.sealed_copy(base / 'copy2', [str(base / 'empty-source')])
    broken = base / 'broken'
    shutil.copytree(str(env.copy), str(broken))
    (broken / 'core' / 'tests' / 'family.py').write_text('edited after the seal\n')
    with refused('SEALED_COPY_FILE_NOT_FOUND'):
        b.sealed_copy(base / 'copy3', [str(broken)])
    repaired = b.sealed_copy(base / 'copy4', [str(broken), str(env.copy)])          # the sealed bytes, from where they still are
    assert repaired['directories']['core']['files_taken_from_a_later_source'] == ['tests/family.py']
    # a HOSTOPS02 sheet shows input files that the bound request carries; edited, it is refused even with a consistent question
    out, prepared = bind(env, base, x.ACTIVATE, activate_params(env), 'rehearsal-m3', x.SITTING)
    sheet = json.loads((out / 'PREPARE.json').read_bytes())
    sheet['hostops02']['bind_inputs']['policy']['bytes'] += 1
    raw = b.pretty(sheet)
    os.chmod(str(out / 'PREPARE.json'), 0o600)
    (out / 'PREPARE.json').write_bytes(raw)
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    (out / 'OWNER_QUESTION.txt').write_bytes(b.question_text(sheet, b.sha(raw), json.loads((out / 'EFFECTS.json').read_bytes()), request['plan']))
    h.rewrite_sums(out)
    with refused('SHEET_FIELD_NOT_DERIVED_FROM_THE_BOUND_FILES'):
        b.signed_state(out)
    # what the owner's list cannot show is refused before anything is created
    with refused('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER'):
        b.hostops02_effects_lines({'operation': x.RELEASE}, {'directory': {'path': '/x', 'mode_octal': '0700', 'expect': 'PRESENT'}}, {})
    with refused('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER'):
        b.hostops02_effects_lines({'operation': x.ACTIVATE}, {}, {})


# ================================================================ the weekend in REAL mode: every citation a bound set
def test_real_weekend_chain_every_citation_a_bound_set_and_every_resume_on_an_emulated_host(env, base):
    """S1, A3, B1 (HOSTOPS01) -> A6 -> A9 (gated) -> M2p -> M1, M1' (gated) -> M2 (gated) -> M3, M3' (gated), REAL mode against a
    synthetic executed reference. Each later request cites the BOUND SETS of the earlier ones; nothing is a loose file."""
    f1 = env.h1.family
    reference = h.executed_reference(base, env.families['w1'])
    real_host = json.loads(reference.read_bytes())['host_binding_sha256']
    hostops01 = env.families['hostops']
    # the three HOSTOPS01 sets on one emulated host whose image carries the release revision
    k = f1.load('precheck')
    host1 = f1.world(k)
    for image in host1.docker.images:
        image['Config']['Labels']['org.opencontainers.image.revision'] = env.h2.hostemu.REVISION
    sets = {}
    for operation, name, key, start, fields, minutes, extra in (
            (x.PRECHECK, 'precheck', 'precheck', x.S1, lambda kk: f1.precheck_fields(kk, host1, placement='A'), 50, {}),
            (x.PROVISION, 'provision', 'provision', x.A3, lambda kk: f1.provision_fields(kk, host1, placement='A'), 10, {'review': env.review}),
            (x.INSTALL, 'install', 'install_units', x.B1, lambda kk: f1.install_fields(kk, host1, placement='A'), 10, {'review': env.review})):
        kk = f1.load(key)
        host1.refused = kk.m.Refused
        plan = fields(kk)
        evidence = []
        if operation != x.PRECHECK:
            evidence = [x.cite('PRECHECK', x.PRECHECK, sets['precheck'])]
            plan = json.loads(json.dumps(plan))
            plan['evidence_boot_id_sha256'] = x.frm('PRECHECK', '/items/boot/boot_id_sha256')
        value = x.parameters(operation, name, start, minutes, plan, evidence, **extra)
        out = base / ('bound-' + name)
        prepared = b.prepare(hostops01, operation, params_file(base, value), reference, out, b.REAL, now=lambda: start)
        b.sign(out, prepared['prepare_json_sha256'], b.zulu(start), b.REAL_ANSWER, now=lambda: start)
        intent, proof, result, report = x.finish(out, host1, start + 30 * SEC, comment='5955151654')
        assert report['verified'] is True and report['status'] == 'KNOWN_COMPLETE', (name, report)
        sets[name] = out
    provision = x.stdout_of(sets['provision'], 'provision')
    rows = x.stdout_of(sets['precheck'], 'precheck')['items']['chains']['DATA_VOLUME']['rows']
    w1 = {name: x.w1_set(base, env.families['w1'], env.w1_harness, reference, 'bound-w1-' + name, name, at, rows, mode=b.REAL)
          for name, at in (('grid', x.GRID), ('sunday', x.SUNDAY), ('m0', x.M0))}
    tree = x.release_tree(base / 'tree', env.h2)
    job = {'kind': 'LINUX_JOB_PASSED', 'document_file': env.review['document_file']}
    catalog_evidence = [x.cite('PRECHECK', x.PRECHECK, sets['precheck'], env.H1), x.cite('PROVISION', x.PROVISION, sets['provision'], env.H1)]
    k, host = x.catalog_host(env.h2, provision)
    a9 = x.parameters(x.CATALOG, 'a9', x.A9, 15, x.catalog_plan(env.h2, host, 'REAL'), catalog_evidence, review=env.review)
    attempt(env, base, 'RELEASE_TREE_REQUIRED', x.CATALOG, a9, x.A9, mode=b.REAL, reference=reference)
    attempt(env, base, 'LINUX_JOB_RECORD_REQUIRED', x.CATALOG, dict(a9, release_tree=str(tree)), x.A9, mode=b.REAL, reference=reference)
    done = {}
    for mode, label, start in (('REHEARSAL', 'a6', x.A6), ('REAL', 'a9', x.A9)):
        k, host = x.catalog_host(env.h2, provision)
        value = x.parameters(x.CATALOG, label, start, 15, x.catalog_plan(env.h2, host, mode), catalog_evidence, review=env.review, release_tree=str(tree),
                             linux_job=job, **({'rehearsal': {'bound': str(done['a6'])}} if label == 'a9' else {}))
        out, prepared = bind(env, base, x.CATALOG, value, 'bound-' + label, start, mode=b.REAL, reference=reference)
        assert prepared['sheet']['host_binding_sha256'] == real_host and all(item['source'] == 'BOUND_SET' for item in prepared['sheet']['evidence'])
        assert prepared['owner_question_pt'].rstrip().endswith('Se estiver de acordo, responda exatamente: Assino')
        if label == 'a9':
            assert prepared['sheet']['hostops02']['rules']['rehearsal_receipt']['outcome'] == 'REHEARSAL_CATALOG_READY_VERIFIED'
            assert 'Ensaio destes mesmos bytes (A6): recibo sha256' in prepared['owner_question_pt']
            gates = gates_file(base, review=x.codex_review_of(out), rehearsal={'bound': str(done['a6']), 'family': str(env.dirs[x.CATALOG])},
                               grid_read={'bound': str(w1['grid']), 'family': env.W1})
            assert b.check(out, env.dirs[x.CATALOG], gates, now=lambda: start + MIN)['verdict'] == 'VALID_WINDOW_OPEN'
            assert b.check(out, env.dirs[x.CATALOG], gates_file(base, review=False, rehearsal={'bound': str(done['a6']), 'family': str(env.dirs[x.CATALOG])},
                                                                grid_read={'bound': str(w1['grid']), 'family': env.W1}),
                           now=lambda: start + MIN)['dispatch_gates']['failed'] == ['CODEX_REVIEW:NOT_GIVEN']
            rehearsal_file = gates_file(base, rehearsal={'receipt_file': str(done['a6'] / '.dispatch-root' / 'a6-once' / 'stdout.private.json'),
                                                         'family': str(env.dirs[x.CATALOG])}, grid_read={'bound': str(w1['grid']), 'family': env.W1})
            loose = b.check(out, env.dirs[x.CATALOG], rehearsal_file, now=lambda: start + MIN)
            assert loose['dispatch_gates']['failed'] == ['K2A_REHEARSAL_RECEIPT:EVIDENCE_OF_A_REAL_REQUEST_MUST_BE_A_BOUND_SET']
        k, host = x.catalog_host(env.h2, provision)
        intent, proof, result, report = x.finish(out, host, start + MIN, comment='5955151654')
        assert report['verified'] is True and report['status'] == 'KNOWN_COMPLETE', report
        done[label] = out
    hostops01_cites_the_a9_set(env, base, sets, done, host1, reference)
    # M2p
    k, host = x.readback_host(env.h2, 'PRE', env.release)
    value = x.parameters(x.READBACK, 'm2p', x.K11_PRE, 60, x.readback_plan(env.h2, host, 'PRE', env.release, env.policy, env.override),
                         [x.cite('PRECHECK', x.PRECHECK, sets['precheck'], env.H1)], inputs=dict(env.inputs), linux_job=job, review=env.review)
    # REAL: SIBLINGS.txt names earlier seals of two siblings, so the record of a run beside the accepted ones is required
    attempt(env, base, 'SIBLINGS_TESTS_NOT_RERUN_FOR_THE_ACCEPTED_SEALS', x.READBACK, value, x.K11_PRE, mode=b.REAL, reference=reference)
    value['siblings_tests'] = {'document_file': env.review['document_file']}
    m2p, prepared = bind(env, base, x.READBACK, value, 'bound-m2p', x.K11_PRE, mode=b.REAL, reference=reference)
    assert prepared['sheet']['hostops02']['rules']['siblings_tests']['record']['names_the_seals'] == ['epoch_readback', 'activate', 'catalog_init', 'install_release']
    assert 'Testes das operações irmãs (contrato, seção 8, passo 3): registro sha256' in prepared['owner_question_pt']
    intent, proof, result, report = x.finish(m2p, host, x.K11_PRE + 12 * MIN, comment='5955151654')
    assert report['verified'] and report['outcome'] == x.b.PRE_FULL_OUTCOME
    # M1 and M1' (Sunday sitting), with the Linux proof
    junit = x.linux_junit_pair(base, env.h2)
    k, host = x.release_host(env.h2)
    evidence = [x.cite('S1_PRECHECK', x.PRECHECK, sets['precheck'], env.H1), x.cite('A3_PROVISION', x.PROVISION, sets['provision'], env.H1),
                x.cite('B1_INSTALL', x.INSTALL, sets['install'], env.H1), x.cite('SUNDAY_W1', x.W1, w1['sunday'], env.W1),
                x.cite('M2P', x.READBACK, m2p, env.dirs[x.READBACK]), x.cite('A4_PROVISION', x.PROVISION, sets['provision'], env.H1)]
    plan = x.release_plan(env.h2, host, env.release, 'S1_PRECHECK')
    value = x.parameters(x.RELEASE, 'm1', x.M1, 15, plan, evidence, signature_model='PRE', inputs={'release': env.inputs['release']}, review=env.review,
                         linux_proof=junit)
    attempt(env, base, 'LINUX_PROOF_REQUIRED', x.RELEASE, {key: item for key, item in value.items() if key != 'linux_proof'}, x.SITTING, mode=b.REAL,
            reference=reference)
    m1, prepared = bind(env, base, x.RELEASE, value, 'bound-m1', x.SITTING, mode=b.REAL, reference=reference)
    assert prepared['sheet']['hostops02']['rules']['linux_proof']['decision'] == 'LINUX_PROOF_ACCEPTED'
    m1s, prepared = bind(env, base, x.RELEASE, dict(value, label='m1-spare', not_before=b.zulu(x.M1_SPARE), not_after=b.zulu(x.M1_SPARE + 15 * MIN),
                                                    spare_of={'bound': str(m1)}), 'bound-m1-spare', x.SITTING, mode=b.REAL, reference=reference)
    gates = gates_file(base, review=x.codex_review_of(m1), m0={'bound': str(w1['m0']), 'family': env.W1})
    assert b.check(m1, env.dirs[x.RELEASE], gates, now=lambda: x.M1 - 5 * MIN)['dispatch_gates']['failed'] == []
    k, host = x.release_host(env.h2)
    intent, proof, result, report = x.finish(m1, host, x.M1 + 3 * MIN, comment='5955151654')
    assert report['verified'] and report['outcome'] == x.b.RELEASE_INSTALLED_OUTCOME
    assert b.check(m1s, env.dirs[x.RELEASE], gates, now=lambda: x.M1_SPARE)['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET'
    # M2, gated on M1's complete receipt
    k, host = x.readback_host(env.h2, 'POST', env.release)
    value = x.parameters(x.READBACK, 'm2', x.K11_POST, 22, x.readback_plan(env.h2, host, 'POST', env.release, env.policy, env.override, 'M2P'),
                         [x.cite('PRECHECK', x.PRECHECK, sets['precheck'], env.H1), x.cite('M2P', x.READBACK, m2p)],
                         inputs={'release': env.inputs['release'], 'policy': env.inputs['policy']}, review=env.review,
                         siblings_tests={'document_file': env.review['document_file']})
    m2, prepared = bind(env, base, x.READBACK, value, 'bound-m2', x.SITTING, mode=b.REAL, reference=reference)
    gates = gates_file(base, install={'bound': str(m1), 'family': str(env.dirs[x.RELEASE])})
    assert b.check(m2, env.dirs[x.READBACK], gates, now=lambda: x.K11_POST + MIN)['verdict'] == 'VALID_WINDOW_OPEN'
    intent, proof, result, report = x.finish(m2, host, x.K11_POST + MIN, comment='5955151654')
    assert report['verified'] and report['outcome'] == x.b.POST_OUTCOME
    # M3 and M3', gated on M2's complete receipt
    k, host = x.activate_host(env.h2, env.release)
    value = x.parameters(x.ACTIVATE, 'm3', x.M3, 15, x.activate_plan(env.h2, host), [x.cite('M2P', x.READBACK, m2p, env.dirs[x.READBACK])], signature_model='PRE',
                         inputs={'policy': env.inputs['policy'], 'release': env.inputs['release'], 'override': env.inputs['override']}, review=env.review, linux_job=job)
    m3, prepared = bind(env, base, x.ACTIVATE, value, 'bound-m3', x.SITTING, mode=b.REAL, reference=reference)
    m3s, prepared = bind(env, base, x.ACTIVATE, dict(value, label='m3-spare', not_before=b.zulu(x.M3_SPARE), not_after=b.zulu(x.M3_SPARE + 15 * MIN),
                                                     spare_of={'bound': str(m3)}), 'bound-m3-spare', x.SITTING, mode=b.REAL, reference=reference)
    gates = gates_file(base, review=x.codex_review_of(m3), readback_post={'bound': str(m2), 'family': str(env.dirs[x.READBACK])})
    assert b.check(m3, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3 + 30 * SEC)['verdict'] == 'VALID_WINDOW_OPEN'
    intent, proof, result, report = x.finish(m3, host, x.M3 + MIN, comment='5955151654')
    assert report['verified'] and report['outcome'] == 'ACTIVATE_WORKER_RECREATED_AND_VERIFIED'
    assert b.check(m3s, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)['dispatch_gates']['failed'] == [
        'CODEX_REVIEW:DOES_NOT_NAME_THIS_REQUEST_AND_FINAL_PAYLOAD', 'SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS']
    # a rehearsal set is never evidence of a real request, nor the other way round
    attempt(env, base, 'EVIDENCE_SET_OF_THE_OTHER_MODE', x.ACTIVATE, dict(value, label='m3x', evidence=[x.cite('M2P', x.READBACK, m2p, env.dirs[x.READBACK])]),
            x.SITTING)


def hostops01_cites_the_a9_set(env, base, sets, done, host1, reference):
    """B3 (HOSTOPS01 readback, GATE) and B1 (install_units) may cite the A9 set by its family (K2a CONTRACT 6): the readback's
    catalog triple is then copied from that receipt and the image revision compared with the precheck's reading; a REAL
    readback that expects an INITIALISED catalog must cite it; the rehearsal's receipt, a second K2a receipt, a typed value
    of another inode, a NOT_YET expectation, and a family member on an item of the readback's own family are refused."""
    f1 = env.h1.family
    k1 = f1.load('readback')
    stored = {name: x.stdout_of(sets[name], name) for name in ('provision', 'install')}
    typed = f1.readback_fields(k1, host1, stored['provision'], stored['install'])
    plan = json.loads(json.dumps(typed))
    plan.update(provision={'receipt_sha256': x.frm('PROVISION', '/metadata_sha256')},
                install={'receipt_sha256': x.frm('INSTALL', '/metadata_sha256'), 'outcome': x.frm('INSTALL', '/outcome')},
                evidence_boot_id_sha256=x.frm('PRECHECK', '/items/boot/boot_id_sha256'), unit_directory=x.frm('PRECHECK', '/items/chains/UNIT_DIRECTORY/rows'),
                image_revision=x.frm('PRECHECK', '/items/image/revision_label'),
                catalog={'expected': 'INITIALISED', 'receipt_sha256': x.frm('A9', '/metadata_sha256'), 'device': x.frm('A9', '/script_line/device'),
                         'inode': x.frm('A9', '/script_line/inode')})
    own = [x.cite('PRECHECK', x.PRECHECK, sets['precheck']), x.cite('PROVISION', x.PROVISION, sets['provision']), x.cite('INSTALL', x.INSTALL, sets['install'])]
    a9 = x.cite('A9', x.CATALOG, done['a9'], env.dirs[x.CATALOG])
    start = x.SUNDAY.replace(hour=13, minute=0)

    def prepare(code, operation, value_plan, evidence, name):
        params = params_file(base, x.parameters(operation, name, start, 50 if operation == b.READBACK_OPERATION else 10, value_plan, evidence,
                                                **({} if operation == b.READBACK_OPERATION else {'review': env.review})))
        out = base / ('bound-' + name)
        if code is None:
            return b.prepare(env.H1, operation, params, reference, out, b.REAL, now=lambda: start)
        with h.refused(code):
            b.prepare(env.H1, operation, params, reference, out, b.REAL, now=lambda: start)
        assert not out.exists()
    prepared = prepare(None, b.READBACK_OPERATION, plan, own + [a9], 'b3')
    sheet = prepared['sheet']
    pointers = [item['plan_pointer'] for item in sheet['plan_values_equal_to_the_cited_receipts']]
    assert pointers[-4:] == ['/catalog/receipt_sha256', '/catalog/device', '/catalog/inode', '/image_revision'], pointers
    assert sheet['contract_section_12_checks']['catalog_4b_receipt_cited'] == 'A9' and sheet['evidence'][-1]['family']['family'] == 'HOSTOPS02_CATALOG_INIT'
    assert 'family' not in sheet['evidence'][0] and sheet['evidence'][-1]['outcome'] == 'CATALOG_READY_VERIFIED'
    request = json.loads((Path(prepared['bound']) / 'REQUEST.BOUND.json').read_bytes())
    a9_receipt = x.stdout_of(done['a9'], 'a9')
    assert request['plan']['catalog'] == {'expected': 'INITIALISED', 'receipt_sha256': a9_receipt['metadata_sha256'],
                                          'device': a9_receipt['script_line']['device'], 'inode': a9_receipt['script_line']['inode']}
    signed = b.sign(Path(prepared['bound']), prepared['prepare_json_sha256'], b.zulu(start), b.REAL_ANSWER, now=lambda: start)
    assert b.signed_state(Path(prepared['bound']))['sheet']['contract_section_12_checks']['catalog_4b_receipt_cited'] == 'A9' and signed['status'] == 'BOUND_NOT_DISPATCHED'
    # typed, without the 4b receipt: refused in REAL
    prepare('CATALOG_WITHOUT_THE_CITED_4B_RECEIPT', b.READBACK_OPERATION, dict(plan, catalog=typed['catalog']), own, 'b3-typed')
    # the rehearsal's receipt as the 4b receipt; two K2a receipts; another inode; NOT_YET with the 4b receipt cited
    a6_as_a9 = x.cite('A9', x.CATALOG, done['a6'], env.dirs[x.CATALOG])
    prepare('CATALOG_4B_RECEIPT_NOT_THE_COMPLETE_REAL_ONE', b.READBACK_OPERATION, plan, own + [a6_as_a9], 'b3-a6')
    prepare('CATALOG_4B_RECEIPT_NOT_ONE', b.READBACK_OPERATION, plan, own + [a9, x.cite('A9B', x.CATALOG, done['a9'], env.dirs[x.CATALOG])], 'b3-two')
    other_inode = json.loads(json.dumps(plan))
    other_inode['catalog']['inode'] = a9_receipt['script_line']['inode'] + 1
    prepare('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', b.READBACK_OPERATION, other_inode, own + [a9], 'b3-inode')
    other_revision = dict(plan, image_revision='e' * 40)
    prepare('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', b.READBACK_OPERATION, other_revision, own + [a9], 'b3-revision')
    not_yet = dict(plan, catalog={'expected': 'NOT_YET', 'receipt_sha256': None, 'device': None, 'inode': None})
    prepare('CATALOG_EXPECTATION_NOT_THE_CITED_4B', b.READBACK_OPERATION, not_yet, own + [a9], 'b3-not-yet')
    prepare('PARAMETERS_INVALID', b.READBACK_OPERATION, plan, [dict(own[0], family=env.H1)] + own[1:] + [a9], 'b3-family')
    # install_units (B1) may cite it too; the rehearsal's receipt never
    k1 = f1.load('install_units')
    install_plan = f1.install_fields(k1, host1, placement='A')
    install_plan.update(unit_directory=x.frm('PRECHECK', '/items/chains/UNIT_DIRECTORY/rows'), evidence_boot_id_sha256=x.frm('PRECHECK', '/items/boot/boot_id_sha256'))
    prepared = prepare(None, b.INSTALL_OPERATION, install_plan, own[:1] + [a9], 'b1-again')
    assert prepared['sheet']['contract_section_12_checks']['catalog_4b_receipt_cited'] == 'A9'
    prepare('CATALOG_4B_RECEIPT_NOT_THE_COMPLETE_REAL_ONE', b.INSTALL_OPERATION, install_plan, own[:1] + [a6_as_a9], 'b1-a6')
    prepare('PARAMETERS_INVALID', b.PROVISION_OPERATION, install_plan, own[:1] + [a9], 'a3-a9')          # the provision cites no K2a set


# ================================================================ revision 3 of the binder (2026-10-03): one test per accepted finding
NEW_SEALS = {'HOSTOPS02_CATALOG_INIT': '1ccaf83dbc3e901d476efe92d877cbee678caf29d2103008a694c155ea09b0f5',
             'HOSTOPS02_INSTALL_RELEASE': '2705134655d7e580f389a7b32178e18b22d8ca75f2d5b206de3c90483fb84b82',
             'HOSTOPS02_EPOCH_READBACK': 'b1a810fea1e695ba3ef25f7dc839136bbb0c9995f89eef777bc2f93215703c1f',
             'HOSTOPS02_ACTIVATE': '91366f446d977fac1e0d0fb6d88c2fa8d98c02ef084b0d4098ebb0467a352bad'}
NEW_CORE = '73fb546b9758718924b73200b48b7c0582a156a60da200ff83f4ca66e9e5c9b1'
SUPERSEDED = ('8b2bced33c01be75605838bf3a31e7f5dd3a65cd9cc34e245bbcd55fea3f38a9', '3f0eea45e6580f05a5490983a87dcc7b6677dc78911ee7e66afc6602c7f57373',
              'c13ce685ba0b09de53cae3221e940c47c3e35cac8c4f65d15b90b93fa9bd2f9f')
OLD_COPIES = Path('/offline/optional-references/hostops02')
NO_GO = b'Codex: NO-GO. I have NOT reviewed seal 8b2bced3; these bytes must not be signed.\n'


def test_blocker_the_accepted_seals_are_the_ones_sent_for_review_and_a_superseded_seal_is_never_bound(env, base):
    """BLOCKER (seals). The binder accepts the HOSTOPS02 seals of the bytes sent to Codex (with the green Linux run), paired
    with the resealed core, and none of the superseded ones; the sealed copy is made from the durable copy alone, nothing
    taken from a later source; a source that holds a superseded seal is refused whole."""
    seals = {item['family']: item for item in b.binder_identity()[1]}
    operational=json.loads(Path(os.environ['BIND_TEST_OPERATIONAL_SEALS']).read_bytes())
    assert {row['family']:row['sha256sums_sha256'] for row in operational['seals'] if row['family'] in NEW_SEALS}==NEW_SEALS
    expected=dict(NEW_SEALS);expected['HOSTOPS02_EPOCH_READBACK']=b.sha((x.HOSTOPS02_SOURCE/'epoch_readback/SHA256SUMS').read_bytes())
    assert {name: seals[name]['sha256sums_sha256'] for name in NEW_SEALS}==expected
    assert all(seals[name]['core'] == {'sha256sums_sha256': NEW_CORE, 'generation_sha256': '4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'}
               for name in NEW_SEALS)
    raw = (h.BIND / 'ACCEPTED_SEALS.json').read_text()
    assert all(old not in json.dumps([item for item in b.binder_identity()[1]]) for old in SUPERSEDED)
    assert x.sources() == [x.HOSTOPS02_SOURCE] and '73fb546b' in raw
    report = json.loads((env.copy / 'SEALED_COPY_REPORT.json').read_bytes())
    assert report['sources'] == [str(x.HOSTOPS02_SOURCE)] and all(item['files_taken_from_a_later_source'] == [] for item in report['directories'].values())
    assert {name: item['seal_sha256'] for name, item in report['directories'].items()} == {
        'core': NEW_CORE, 'catalog_init': NEW_SEALS['HOSTOPS02_CATALOG_INIT'], 'install_release': NEW_SEALS['HOSTOPS02_INSTALL_RELEASE'],
        'epoch_readback': expected['HOSTOPS02_EPOCH_READBACK'], 'activate': NEW_SEALS['HOSTOPS02_ACTIVATE']}
    # a working directory whose activate/ carries another seal: refused as a source, first or as a fallback
    stale = base / 'stale'
    shutil.copytree(str(env.copy), str(stale))
    sums = stale / 'activate' / 'SHA256SUMS'
    sums.write_bytes(b''.join(sorted(sums.read_bytes().splitlines(keepends=True), reverse=True)))
    for order in ([str(stale), str(env.copy)], [str(env.copy), str(stale)]):
        with refused('SEALED_COPY_SOURCE_HOLDS_A_SUPERSEDED_SEAL'):
            b.sealed_copy(base / ('copy-%d' % len(list(base.iterdir()))), order)
    # the verifiers' copies of the superseded seals, where they still exist: never a source, never bound
    if (OLD_COPIES / 'final-k6a' / 'activate').is_dir():
        with refused('SEALED_COPY_SOURCE_HOLDS_A_SUPERSEDED_SEAL'):
            b.sealed_copy(base / 'copy-old', [str(x.DURABLE_TIER), str(OLD_COPIES / 'final-k6a')])
    if (OLD_COPIES / 'final-k2a' / 'mine' / 'catalog_init').is_dir():
        with pytest.raises(b.Refused) as caught:          # an unaccepted seal: work/ is not skipped, and the seal is not accepted
            b.prepare(OLD_COPIES / 'final-k2a' / 'mine' / 'catalog_init', x.CATALOG, params_file(base, catalog_params(env, 'REHEARSAL')), env.reference,
                      base / 'rehearsal-old', b.REHEARSAL, now=lambda: x.A6)
        assert str(caught.value) in ('FAMILY_FILE_SET', 'FAMILY_SEAL_NOT_ACCEPTED') and not (base / 'rehearsal-old').exists()


def test_major_k11_carries_the_review_of_its_bytes_and_the_owner_reads_it(env, base):
    """MAJOR (K11 review). K11 starts a container: the order conditions it on "programa revisto" (A1 4.2, C4; K11 CONTRACT 1 and
    8 step 1). Its request must name the review; a document that does not name these bytes is refused; the question shows
    the review line; a sheet edited to drop it is refused when opened."""
    value = readback_params(env, 'PRE')
    attempt(env, base, 'REVIEW_OR_WAIVER_MISSING_FOR_A_CONTAINER_RUN', x.READBACK, {key: item for key, item in value.items() if key != 'review'}, x.K11_PRE)
    nogo = x.write(base / 'nogo.txt', NO_GO)
    attempt(env, base, 'REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES', x.READBACK, dict(value, review={'kind': 'CODEX_REVIEWED', 'document_file': str(nogo)}), x.K11_PRE)
    out, prepared = bind(env, base, x.READBACK, value, 'rehearsal-m2p', x.K11_PRE)
    sheet, question = prepared['sheet'], prepared['owner_question_pt']
    assert sheet['review']['names_these_bytes'] == ['final_payload_unbound', 'seal', 'source'] and 'review' in sheet['owner_signs_over']
    assert 'Revisão prévia do Codex sobre estes bytes: FEITA (documento sha256 %s).' % b.sha(Path(env.review['document_file']).read_bytes()) in question
    edited = json.loads((out / 'PREPARE.json').read_bytes())
    edited['review'] = None
    raw = b.pretty(edited)
    os.chmod(str(out / 'PREPARE.json'), 0o600)
    (out / 'PREPARE.json').write_bytes(raw)
    request = json.loads((out / 'REQUEST.BOUND.json').read_bytes())
    try:
        text = b.question_text(edited, b.sha(raw), json.loads((out / 'EFFECTS.json').read_bytes()), request['plan'])
    except TypeError:
        text = b'no question can be written without the review'
    (out / 'OWNER_QUESTION.txt').write_bytes(text)
    h.rewrite_sums(out)
    with pytest.raises(b.Refused):
        b.signed_state(out)


def test_major_the_review_and_the_waiver_name_these_bytes_and_a_write_waits_for_the_review_of_the_bound_set(env, base, monkeypatch):
    """MAJOR (review never checked). A review document that does not name the seal and the payload of these bytes (a NO-GO
    note, the review of a superseded seal, a seal without the payload) is refused; the waiver is the owner's own record,
    made before this request, of this operation, and the question never words the signature as the waiver; a write is
    gated at dispatch on Codex's written review of the BOUND set (request and final payload hashes) or his statement that
    the candidate's review suffices (operation, seal, payload)."""
    hashes, core = x.tier_hashes(env.copy)
    operation, seal, source, final = hashes['catalog_init']
    value = catalog_params(env, 'REHEARSAL')
    for name, raw in (('nogo', NO_GO), ('superseded', ('seal %s source %s\n' % (SUPERSEDED[0], source)).encode()),
                      ('seal-only', ('seal %s\n' % seal).encode()), ('payload-only', ('source %s final %s\n' % (source, final)).encode())):
        document = x.write(base / ('review-%s.txt' % name), raw)
        attempt(env, base, 'REVIEW_DOCUMENT_DOES_NOT_NAME_THESE_BYTES', x.CATALOG, dict(value, review={'kind': 'CODEX_REVIEWED', 'document_file': str(document)}), x.A6)
    by_final = x.write(base / 'review-final.txt', ('Codex: GO for %s, seal %s, final payload %s\n' % (operation, seal, final)).encode())
    out, prepared = bind(env, base, x.CATALOG, dict(value, review={'kind': 'CODEX_REVIEWED', 'document_file': str(by_final)}), 'rehearsal-a6-final', x.A6)
    assert prepared['sheet']['review']['names_these_bytes'] == ['final_payload_unbound', 'seal']
    # the waiver: the owner's own record, before this request, of this operation and these bytes
    for name, change in (('junk', None), ('other-operation', {'operation': x.ACTIVATE}), ('later', {'at': x.A6 + MIN}), ('real-owner', {'mode': b.REAL})):
        if change is None:
            waiver = {'kind': 'OWNER_WAIVED', 'document_file': str(x.write(base / 'waiver-junk.txt', b'the owner waives, says Fable\n'))}
        else:
            waiver = x.owner_waiver(base, env.copy, change.get('operation', x.CATALOG), change.get('at', x.A6 - MIN), change.get('mode', b.REHEARSAL),
                                    name='waiver-%s.json' % name)
        attempt(env, base, 'OWNER_WAIVER_NOT_A_SIGNED_RECORD_FOR_THESE_BYTES', x.CATALOG, dict(value, review=waiver), x.A6)
    waiver = x.owner_waiver(base, env.copy, x.CATALOG, x.A6 - MIN)
    out, prepared = bind(env, base, x.CATALOG, dict(value, label='a6-waived', review=waiver), 'rehearsal-a6-waived', x.A6)
    question = prepared['owner_question_pt']
    assert 'DISPENSADA por decisão sua registrada à parte (registro sha256 %s, resposta sua de sáb 03/10/2026 16:59:00 BRT). Esta assinatura não é a dispensa.' % (
        b.sha(Path(waiver['document_file']).read_bytes())) in question and 'Ao assinar você confirma' not in question
    assert prepared['sheet']['hostops02']['dispatch_gates'] == [] and prepared['sheet']['review']['owner_waiver_signed_at_utc'] == b.zulu(x.A6 - MIN)
    # the gate of the bound set's review
    a6, prepared = bind(env, base, x.CATALOG, value, 'rehearsal-a6', x.A6)
    other, _ = bind(env, base, x.CATALOG, dict(value, label='a6-other'), 'rehearsal-a6-other', x.A6)
    junk = x.write(base / 'junk-review.txt', b'nothing named here\n')
    no_name = x.write(base / 'candidate-without-name.txt', ('seal %s source %s\n' % (seal, source)).encode())
    at = x.A6 + 30 * SEC
    for review, failed in ((False, ['CODEX_REVIEW:NOT_GIVEN']),
                           (x.codex_review_of(other), ['CODEX_REVIEW:DOES_NOT_NAME_THIS_REQUEST_AND_FINAL_PAYLOAD']),
                           ({'document_file': str(junk), 'form': 'CANDIDATE_REVIEW_SUFFICES'}, ['CODEX_REVIEW:DOES_NOT_NAME_THESE_BYTES']),
                           ({'document_file': str(no_name), 'form': 'CANDIDATE_REVIEW_SUFFICES'}, ['CODEX_REVIEW:DOES_NOT_NAME_THESE_BYTES']),
                           ({'document_file': str(base / 'absent.txt'), 'form': 'BOUND_SET'}, ['CODEX_REVIEW:UNREADABLE']),
                           ({'document_file': str(junk), 'form': 'TRUST_ME'}, ['CODEX_REVIEW:INVALID']),
                           (x.codex_review_of(a6), []),
                           ({'document_file': env.review['document_file'], 'form': 'CANDIDATE_REVIEW_SUFFICES'}, [])):
        checked = b.check(a6, env.dirs[x.CATALOG], gates_file(base, review=review), now=lambda: at)
        assert checked['dispatch_gates']['failed'] == failed and checked['verdict'] == ('VALID_WINDOW_OPEN' if not failed else 'VALID_BUT_DISPATCH_GATES_NOT_MET'), review
    h.COVERED.add('CODEX_REVIEW_DOCUMENT_UNREADABLE')
    assert checked['dispatch_gates']['facts']['codex_review']['form'] == 'CANDIDATE_REVIEW_SUFFICES'


def w1_set_changed(env, base, name, label, now, change, mode=b.REHEARSAL):
    """x.w1_set with one more edit of the receipt before it is sealed again: what a host in that state would answer."""
    rows = env.precheck['items']['chains']['DATA_VOLUME']['rows']
    params = {'schema': b.PARAMETERS_SCHEMA, 'operation': x.W1, 'label': label, 'signature_model': 'IND', 'not_before': x.zulu(now),
              'not_after': x.zulu(now + 20 * MIN), 'candidates': {'release_directories': [x.RELEASE_LEAF], 'capacity_roots': []}}
    path = h.write_json(Path(base) / ('P-%s.json' % label), params)
    out = Path(base) / name
    prepared = b.prepare(env.families['w1'], x.W1, path, env.reference, out, mode, now=lambda: now)
    b.sign(out, prepared['prepare_json_sha256'], x.zulu(now), b.REHEARSAL_ANSWER, now=lambda: now)
    host = env.w1_harness.world()
    host.clock = (now + 3 * SEC).timestamp()

    def edit(receipt):
        for row, want in zip(receipt['observation']['sections']['data_volume']['ancestors'], rows):
            row.update(device=want['device'], inode=want['inode'], uid=want['uid'], gid=want['gid'], mode_octal='%04o' % want['mode'])
        change(receipt)
    intent, proof, result, report = x.finish(out, host, now, edit)
    assert report['verified'] is True, report
    return out


def test_major_a_pending_reboot_always_fails_the_a9_gate_and_the_a6_receipt_must_be_of_this_image_script_and_path(env, base):
    """MAJOR (reboot order). A pending reboot fails the A9 gate whatever file is named; a gates file that names an order is
    invalid (the owner's own act needs a new sheet). MINOR (grid read, A6 receipt): a partial grid read fails; the A6 receipt
    of another image, script or container path fails, at dispatch and, when given at prepare, before the signature."""
    a6, _ = bind(env, base, x.CATALOG, catalog_params(env, 'REHEARSAL'), 'rehearsal-a6', x.A6)
    k, host = x.catalog_host(env.h2, env.provision)
    x.finish(a6, host, x.A6 + 30 * SEC)
    a9, prepared = bind(env, base, x.CATALOG, catalog_params(env, 'REAL', 'a9', x.A9, rehearsal={'bound': str(a6)}), 'rehearsal-a9', x.A9)
    assert prepared['sheet']['hostops02']['rules']['rehearsal_receipt']['checks'] == sorted(b.k2a_rehearsal_checks({}, {'complete': False}, {}, {
        'evidence_boot_id_sha256': None, 'image_id': None, 'image_revision': None, 'script_sha256': None, 'container_journal_root': None}))
    pending = w1_set_changed(env, base, 'rehearsal-w1-pending', 'pending', x.GRID,
                             lambda receipt: receipt['observation']['sections']['security_controller'].update(reboot_pending=True))
    partial = w1_set_changed(env, base, 'rehearsal-w1-partial', 'partial', x.GRID, lambda receipt: receipt.update(status='PARTIAL_METADATA_REQUIRES_REVIEW'))
    review = x.codex_review_of(a9)
    rehearsal = {'bound': str(a6), 'family': str(env.dirs[x.CATALOG])}
    order = x.write(base / 'not-an-order.txt', b'anything at all\n')
    with refused('GATES_FILE_INVALID'):
        b.check(a9, env.dirs[x.CATALOG], gates_file(base, review=review, rehearsal=rehearsal, grid_read={'bound': str(pending), 'family': env.W1},
                                                    reboot_pending_order={'document_file': str(order)}), now=lambda: x.A9 + MIN)
    checked = b.check(a9, env.dirs[x.CATALOG], gates_file(base, review=review, rehearsal=rehearsal, grid_read={'bound': str(pending), 'family': env.W1}),
                      now=lambda: x.A9 + MIN)
    assert checked['dispatch_gates']['failed'] == ['K2A_GRID_READ:NO_REBOOT_PENDING'] and checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET'
    checked = b.check(a9, env.dirs[x.CATALOG], gates_file(base, review=review, rehearsal=rehearsal, grid_read={'bound': str(partial), 'family': env.W1}),
                      now=lambda: x.A9 + MIN)
    assert checked['dispatch_gates']['failed'] == ['K2A_GRID_READ:COMPLETE_READ']
    assert 'reinício pendente este pedido não é enviado' in prepared['owner_question_pt'] and 'ordem sua, por nome' not in prepared['owner_question_pt']
    # an A6 receipt of another image, script or container path (a loose file in a rehearsal), at prepare and at dispatch
    stored = x.stdout_of(a6, 'a6')
    for name, edit in (('image', lambda r: r['effects']['container'].update(image_id='sha256:' + 'e' * 64)),
                       ('script', lambda r: r['effects']['container']['standard_input'].update(sha256='e' * 64)),
                       ('path', lambda r: r['effects']['container']['bind'].update(target='/elsewhere'))):
        folder = base / ('a6-' + name)
        folder.mkdir()
        loose = x.write_receipt(folder / 'receipt.json', x.resealed(stored, change=edit))
        attempt(env, base, 'REHEARSAL_RECEIPT_NOT_THE_ONE_A9_NEEDS', x.CATALOG, catalog_params(env, 'REAL', 'a9x', x.A9, rehearsal={'receipt_file': str(loose)}), x.A9)
        checked = b.check(a9, env.dirs[x.CATALOG], gates_file(base, review=review, rehearsal={'receipt_file': str(loose), 'family': str(env.dirs[x.CATALOG])},
                                                              grid_read={'bound': str(env.w1['grid']), 'family': env.W1}), now=lambda: x.A9 + MIN)
        assert checked['dispatch_gates']['failed'][0].startswith('K2A_REHEARSAL_RECEIPT:SAME_'), checked['dispatch_gates']['failed']
        assert 'K2A_REHEARSAL_RECEIPT:NOT_THE_ONE_THE_OWNER_WAS_SHOWN' in checked['dispatch_gates']['failed']
    attempt(env, base, 'PARAMETERS_INVALID', x.CATALOG, catalog_params(env, 'REHEARSAL', 'a6x', rehearsal={'bound': str(a6)}), x.A6)


def test_major_the_dispatch_and_resume_verdicts_fold_the_minutes_to_avoid_and_blocks_6_and_9_enforce_them(env, base, monkeypatch):
    """MAJOR (runbook blocks 6 and 9). check folds the minute to avoid into its verdict (exit 1); --step resume is the
    verdict before the resume of every HOSTOPS02 set; blocks 6 and 9 run check themselves and stop without the right
    verdict, or when the sheet lists gates and run.env has no GATES. MINOR: a gate with fewer than three usable minutes
    is refused at prepare."""
    a6, _ = bind(env, base, x.CATALOG, catalog_params(env, 'REHEARSAL'), 'rehearsal-a6', x.A6)
    gates = gates_file(base, review=x.codex_review_of(a6))
    assert b.check(a6, env.dirs[x.CATALOG], gates, now=lambda: x.A6 + 2 * MIN)['verdict'] == 'VALID_WINDOW_OPEN'
    late = b.check(a6, env.dirs[x.CATALOG], gates, now=lambda: x.A6 + 6 * MIN)
    assert late['verdict'] == 'VALID_BUT_NOW_IS_A_MINUTE_TO_AVOID' and late['now_is_a_minute_to_avoid'] is True and late['dispatch_allowed_by_the_gates'] is True
    original = b.check
    monkeypatch.setattr(b, 'check', lambda *args, **kwargs: original(*args, now=lambda: x.A6 + 12 * MIN))
    assert b.main(['check', '--bound', str(a6), '--family', str(env.dirs[x.CATALOG]), '--gates', str(gates)]) == 1
    monkeypatch.setattr(b, 'check', lambda *args, **kwargs: original(*args, now=lambda: x.A6 + 3 * MIN))
    assert b.main(['check', '--bound', str(a6), '--family', str(env.dirs[x.CATALOG]), '--gates', str(gates)]) == 0
    monkeypatch.undo()
    assert b.check(a6, env.dirs[x.CATALOG], gates, 'resume', now=lambda: x.A6 + MIN)['verdict'] == 'VALID_BUT_NOTHING_TO_RESUME'
    assert x.dispatcher_prepare(a6, x.A6 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    b.publish_proof(a6, b.REHEARSAL_PUBLICATION, b.zulu(x.A6 + 31 * SEC), now=lambda: x.A6 + 32 * SEC)
    for moment, verdict in ((x.A6 + 40 * SEC, 'VALID_RESUME_ALLOWED_BY_THE_GATES'), (x.A6 + 6 * MIN, 'VALID_BUT_RESUME_GATES_NOT_MET'),
                            (x.A6 + 14 * MIN, 'VALID_BUT_RESUME_GATES_NOT_MET')):          # past the latest start (20:13:40)
        assert b.check(a6, env.dirs[x.CATALOG], gates, 'resume', now=lambda: moment)['verdict'] == verdict, moment
    assert b.check(a6, env.dirs[x.CATALOG], gates_file(base, review=False), 'resume', now=lambda: x.A6 + 40 * SEC)['verdict'] == 'VALID_BUT_RESUME_GATES_NOT_MET'
    # a gate of two usable minutes is refused at prepare (K11: 15:03 to 15:06:20, the last start 15:05:00; 15:05 is to be avoided)
    pre = readback_params(env, 'PRE')
    attempt(env, base, 'GATE_WINDOW_ONLY_IN_MINUTES_TO_AVOID', x.READBACK, dict(pre, not_before=b.zulu(x.K11_PRE.replace(minute=3)),
                                                                              not_after=b.zulu(x.K11_PRE.replace(minute=6, second=20))), x.K11_PRE.replace(minute=0))
    assert b.usable_minutes(x.K11_PRE.replace(minute=3), x.K11_PRE.replace(minute=5)) == 2
    # blocks 6 and 9, literally, on this A9 (it lists gates) and on a fresh A6: they stop before the dispatcher
    import runbook_blocks
    found = runbook_blocks.blocks()
    a9, _ = bind(env, base, x.CATALOG, catalog_params(env, 'REAL', 'a9', x.A9), 'rehearsal-a9', x.A9)
    fresh, _ = bind(env, base, x.CATALOG, catalog_params(env, 'REHEARSAL', 'a6b'), 'rehearsal-a6b', x.A6)
    runs = base / 'runs'
    # (a9: the sheet lists gates and run.env has none; a6b: a gates file without the review of the bound set, so that no clock
    # of the real day can open it) -> what block 6 and block 9 print, and nothing created under the claim root
    cases = (('a9', a9, None, {'dispatcher-prepare': 'PARADO: a folha lista portões de envio e o run.env não tem GATES (bloco 1a)',
                               'resume': 'PARADO: a folha lista portões de envio e o run.env não tem GATES; o resume não roda'}),
             ('a6b', fresh, gates_file(base, review=False), {'dispatcher-prepare': 'PARADO: o check não deu VALID_WINDOW_OPEN',
                                                            'resume': 'PORTÃO ANTES DO RESUME NÃO LIBERADO'}))
    for label, bound_set, gates_path, stops in cases:
        run = runs / label
        run.mkdir(parents=True, mode=0o700)
        lines = ['FAMILY=%s' % env.dirs[x.CATALOG], 'OP=%s' % x.CATALOG, 'MODE=rehearsal', 'PARAMS=%s' % (run / 'PARAMETERS.json'), 'OUT=%s' % bound_set]
        if gates_path is not None:
            lines.append('GATES=%s' % gates_path)
        (run / 'run.env').write_text('\n'.join(lines) + '\n')
        (run / 'sign.json').write_text(json.dumps({'config_sha256': b.sha(b.signed_state(bound_set)['config_raw'])}))
        for name, stop in sorted(stops.items()):
            body = found[name][1].replace('<label>', label)
            done = subprocess.run(['/bin/zsh', '-c', body], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
                                  env={'PATH': '/usr/bin:/bin', 'HOME': os.environ.get('HOME', '/'), 'RUN_BASE': str(runs), 'LANG': 'en_US.UTF-8','BIND_CANDIDATE_ROOT':str(h.BIND.parent),'BIND_WORK_ROOT':str(base/'optional-work')})
            text = done.stdout.decode('utf-8', 'replace')
            assert stop in text and 'Traceback' not in text, (name, text[-1500:])
            assert not list((bound_set / '.dispatch-root').iterdir()) and not (run / 'dispatch-prepare.json').exists(), (name, text[-800:])
            assert ('RESUME NÃO INICIADO' in text) if name == 'resume' else ('nada foi preparado: nenhum claim foi criado por este bloco' in text), text[-800:]


def test_major_the_owner_reads_what_partial_and_no_receipt_mean_for_each_operation(env, base):
    """MAJOR (outcome texts). K6a: worker not recreated means no epoch; recreated without verification, uncertain or no
    receipt means the worker may be stopped, the owner told at once, a read and never a second send, D2 open; after any send,
    no other activation request. K11 POST: partial, refused or no receipt means M3 is not sent and the epoch does not start,
    with the order's exception the owner's to invoke. K2a: no receipt is a burnt root; UNTOUCHED_NO_CONTAINER_STARTED blocks
    every later run of these bytes until the unit's docker directory is emptied."""
    m3, prepared = bind(env, base, x.ACTIVATE, activate_params(env), 'rehearsal-m3', x.SITTING)
    question = prepared['owner_question_pt']
    for text in ('Se o trabalhador NÃO foi recriado (PARCIAL, com a pasta e os arquivos criados): a ativação não aconteceu e, pela ordem, a época não começa',
                 'o trabalhador pode estar parado (em seis dos oito estados intermediários de uma recriação nenhum trabalhador roda); você é avisado na hora',
                 'nunca por um segundo envio; se a época começa assim é a decisão em aberto D2, sua e do Codex',
                 'Depois de qualquer envio desta ativação, nenhum outro pedido de ativação (principal ou reserva) é usado.'):
        assert text in question, text
    pre, prepared = bind(env, base, x.READBACK, readback_params(env, 'PRE'), 'rehearsal-m2p', x.K11_PRE)
    assert 'é um achado a corrigir antes de segunda' in prepared['owner_question_pt'] and 'isso é resultado válido, não falha' not in prepared['owner_question_pt']
    post, prepared = bind(env, base, x.READBACK, readback_params(env, 'POST', 'm2', x.K11_POST), 'rehearsal-m2', x.SITTING)
    question = prepared['owner_question_pt']
    assert ('Se for PARCIAL ou RECUSADO, ou se não houver recibo: a ativação não é enviada e, pela ordem, a época não começa' in question
            and 'essa exceção só você pode invocar' in question and 'é um achado a corrigir' not in question)
    a9, prepared = bind(env, base, x.CATALOG, catalog_params(env, 'REAL', 'a9', x.A9), 'rehearsal-a9', x.A9)
    question = prepared['owner_question_pt']
    assert ('UNTOUCHED_NO_CONTAINER_STARTED quer dizer pasta do journal intacta, mas a pasta de configuração do cliente docker da unidade não está vazia: '
            'toda execução seguinte destes bytes, inclusive a reserva, recusa' in question)
    assert 'Se não houver recibo: a pasta é tratada como não utilizável de novo' in question and 'vale o veredito da pasta no recibo; "não usar' not in question


def test_minor_one_spare_per_primary_a_primary_with_content_is_prepared_and_k2a_k6a_spares_follow_a1(env, base):
    """MINOR (spares). A spare is registered beside its primary and its gate needs that registry to name it; any content of the
    primary's claim root counts as prepared (a removed claim file with the attempt in place included); for K6a (and K2a) a
    primary that was only prepared and is past its latest start was provably never sent, and its spare may go; K10 keeps
    its contract's strict rule."""
    gates = gates_file(base, readback_post={'receipt_file': str(env.files['k11post']), 'family': str(env.dirs[x.READBACK])})
    m3, _ = bind(env, base, x.ACTIVATE, activate_params(env), 'rehearsal-m3', x.SITTING)
    spare, prepared = bind(env, base, x.ACTIVATE, activate_params(env, 'm3-spare', x.M3_SPARE, spare_of={'bound': str(m3)}), 'rehearsal-m3-spare', x.SITTING)
    assert 'o último início dele já passou, quando o dispatcher não o envia mais' in prepared['owner_question_pt']
    assert b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)['dispatch_gates']['failed'] == []
    assert x.dispatcher_prepare(m3, x.M3 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    # prepared and never sent, past its latest start (09:13:40): the K6a spare may go
    checked = b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)
    assert checked['dispatch_gates']['failed'] == [] and checked['dispatch_gates']['facts']['primary_claim_root'] == 'PREPARED_NEVER_SENT_PAST_ITS_LATEST_START'
    # ...but not before that latest start
    early = b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3 + 5 * MIN)
    assert 'SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS' in early['dispatch_gates']['failed']
    # the claim file removed with the attempt in place: prepared, whatever the clock
    root = m3 / '.dispatch-root'
    [claim] = [item for item in root.iterdir() if item.name.endswith('.claim')]
    claim.unlink()
    removed = b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)
    assert removed['dispatch_gates']['failed'] == ['SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS'] and removed['dispatch_gates']['facts']['primary_claim_root'] == 'OTHER'
    # the registry must name this spare
    registry = b.spare_registry(m3)
    saved = registry.read_bytes()
    registry.chmod(0o600)
    registry.write_bytes(b'not json')
    assert 'SPARE:NOT_THE_REGISTERED_SPARE_OF_ITS_PRIMARY' in b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)['dispatch_gates']['failed']
    h.COVERED.add('SPARE_REGISTRY_UNREADABLE')
    registry.write_bytes(saved.replace(str(spare).encode(), str(base / 'another').encode()))
    assert 'SPARE:NOT_THE_REGISTERED_SPARE_OF_ITS_PRIMARY' in b.check(spare, env.dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + 30 * SEC)['dispatch_gates']['failed']
    # K10: a primary prepared and past its latest start still blocks its spare (CONTRACT K10 6, step 15)
    m1, _ = bind(env, base, x.RELEASE, release_params(env), 'rehearsal-m1', x.SITTING)
    m1s, _ = bind(env, base, x.RELEASE, release_params(env, 'm1-spare', x.M1_SPARE, spare_of={'bound': str(m1)}), 'rehearsal-m1-spare', x.SITTING)
    assert x.dispatcher_prepare(m1, x.M1 + 30 * SEC)['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    k10 = b.check(m1s, env.dirs[x.RELEASE], gates_file(base, m0={'bound': str(env.w1['m0']), 'family': env.W1}), now=lambda: x.M1_SPARE + 30 * SEC)
    assert 'SPARE:PRIMARY_WAS_PREPARED_ITS_CLAIM_EXISTS' in k10['dispatch_gates']['failed']


def test_minor_k10_names_both_provisions_or_the_reason_and_k11_compares_the_worker_and_the_sibling_record(env, base):
    """MINOR (K10 host evidence (j); K11 typed values and sibling tests)."""
    value = release_params(env)
    one = dict(value, evidence=value['evidence'][:5])
    attempt(env, base, 'RELEASE_HOST_EVIDENCE_A4_NOT_CITED_AND_NO_REASON', x.RELEASE, one, x.SITTING)
    attempt(env, base, 'PARAMETERS_FREE_TEXT', x.RELEASE, dict(one, host_evidence_reason_pt='A4 cortado: ' + 'a' * 64), x.SITTING)
    out, prepared = bind(env, base, x.RELEASE, dict(one, host_evidence_reason_pt='A4 foi cortado com o tier 1 na sentada de sábado'), 'rehearsal-m1-reason', x.SITTING)
    assert 'Recibos de provisão citados: 1 (o contrato nomeia dois, A3 e A4). Motivo dado pelo operador: A4 foi cortado com o tier 1' in prepared['owner_question_pt']
    # K11: the sibling-test record must name the accepted seals
    pre = readback_params(env, 'PRE')
    hashes, core = x.tier_hashes(env.copy)
    partial = x.write(base / 'siblings-partial.txt', ('%s %s\n' % (hashes['epoch_readback'][1], hashes['activate'][1])).encode())
    attempt(env, base, 'SIBLINGS_TESTS_RECORD_NOT_OF_THE_ACCEPTED_SEALS', x.READBACK, dict(pre, siblings_tests={'document_file': str(partial)}), x.K11_PRE)
    attempt(env, base, 'SIBLINGS_TESTS_RECORD_UNREADABLE', x.READBACK, dict(pre, siblings_tests={'document_file': str(base / 'absent.txt')}), x.K11_PRE)
    # the worker and the image, compared with a cited W1 read of the same boot
    k, host = x.readback_host(env.h2, 'PRE', env.release)
    plan = x.readback_plan(env.h2, host, 'PRE', env.release, env.policy, env.override)
    worker = {'name': plan['worker']['container'], 'image_id': env.precheck['items']['image']['id'], 'image_reference': plan['image']['reference'],
              'mounts': [{'type': 'bind', 'source': plan['worker']['data_source'], 'destination': plan['worker']['data_target'], 'rw': True}]}

    def with_worker(**changes):
        def edit(receipt):
            rows = [row for row in receipt['observation']['sections']['containers']['rows'] if row.get('name') != worker['name']]
            receipt['observation']['sections']['containers']['rows'] = rows + [dict(worker, **changes)]
        return edit
    good = w1_set_changed(env, base, 'rehearsal-w1-worker', 'worker', x.SUNDAY, with_worker())
    other = w1_set_changed(env, base, 'rehearsal-w1-other-image', 'other-image', x.SUNDAY, with_worker(image_id='sha256:' + 'e' * 64))
    out, prepared = bind(env, base, x.READBACK, dict(pre, evidence=pre['evidence'] + [x.cite('W1', x.W1, good, env.W1)]), 'rehearsal-m2p-w1', x.K11_PRE)
    assert prepared['sheet']['hostops02']['rules']['worker_and_image_compared_with'] == ['W1']
    assert 'Trabalhador, imagem e montagem do volume de dados: conferidos com a leitura W1 citada (W1).' in prepared['owner_question_pt']
    attempt(env, base, 'WORKER_OR_IMAGE_NOT_THE_ONES_OF_THE_CITED_READ', x.READBACK, dict(pre, evidence=pre['evidence'] + [x.cite('W1', x.W1, other, env.W1)]), x.K11_PRE)
