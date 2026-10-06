"""The binder as extended for HOSTOPS02 against its revision 1 (SHA256SUMS 622bab88...), for W1 and HOSTOPS01: the same
inputs give the same bytes, and each revision reproduces, byte for byte, the documents and the question the other wrote.

Revision 1 is the copy kept beside this directory (bind.rev1-622bab88, or BIND_TEST_REV1). What legitimately differs is
named and nothing else: the binder's own identity on the sheet (the hash of bind_once.py and of ACCEPTED_SEALS.json), and
what follows from the directory a set is bound in (its claim root: path, device, inode; and the sheet's hash, which the
question quotes). Then: signed_state() of each revision on the other's signed set (it rebuilds AUTHORITY, GO, final
payload and dispatch configuration from the sheet and compares them byte for byte with the files, and the question with
OWNER_QUESTION.txt), check(), and status() of today's real W1 set by both revisions (read-only; nothing is printed)."""
import importlib.util
import json
import os
from pathlib import Path

import pytest

import helpers as h

b = h.b
REV1 = Path(os.environ.get('BIND_TEST_REV1', str(h.BIND.parent / 'bind.rev1-622bab88')))
REAL_W1 = Path(os.environ.get('BIND_TEST_REAL_W1', '/offline/optional-work/once-w1-20261002-a/bound'))
VARYING = ('binder', 'claim_root_identity', 'attempt_directory')


@pytest.fixture(scope='module')
def rev1():
    if not (REV1 / 'bind_once.py').is_file():
        pytest.skip('revision 1 of the binder is not at hand')
    raw = (REV1 / 'SHA256SUMS').read_bytes()
    assert b.sha(raw) == '622bab88dc54c068b8fe8b5795a14c32fdffa56f13703a017a0d457442ddf9a4'
    spec = importlib.util.spec_from_file_location('bind_once_rev1', str(REV1 / 'bind_once.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def same_bytes(first, second):
    """Every file of two prepared sets, compared: equal bytes, except the sheet (equal but for VARYING) and the question
    (equal but for its claim-root and sheet-hash lines)."""
    names = sorted(str(path.relative_to(first)) for path in first.rglob('*') if path.is_file() and path.relative_to(first).parts[0] != '.dispatch-root')
    assert names == sorted(str(path.relative_to(second)) for path in second.rglob('*') if path.is_file() and path.relative_to(second).parts[0] != '.dispatch-root')
    differing = []
    for name in names:
        one, two = (first / name).read_bytes(), (second / name).read_bytes()
        if name == 'PREPARE.json':
            one, two = json.loads(one), json.loads(two)
            assert {key: value for key, value in one.items() if key not in VARYING} == {key: value for key, value in two.items() if key not in VARYING}
            assert set(one) == set(two)
        elif name == 'OWNER_QUESTION.txt':
            def kept(text):
                return [line for line in text.decode('utf-8').splitlines() if not line.startswith(('- raiz local de uso único:', '- folha de assinatura (PREPARE.json)'))]
            assert kept(one) == kept(two)
        elif one != two:
            differing.append(name)
    assert differing == [], differing
    return names


def prepare_both(rev1, base, family, operation, parameters, reference, now, mode=b.REHEARSAL):
    out = {}
    for label, module in (('rev1', rev1), ('rev2', b)):
        name = ('rehearsal-' if mode == b.REHEARSAL else '') + label
        out[label] = base / name
        module.prepare(family, operation, parameters, reference, out[label], mode, now=lambda: now)
    return out


def sign_both(rev1, out, now, mode=b.REHEARSAL):
    for label, module in (('rev1', rev1), ('rev2', b)):
        sheet = module.sha((out[label] / 'PREPARE.json').read_bytes())
        module.sign(out[label], sheet, b.zulu(now), h.answer_of(mode), now=lambda: now)


def cross_checked(rev1, out, family, now):
    """Each revision opens the other's signed set: documents and question rebuilt and compared byte for byte."""
    for writer, reader in (('rev1', b), ('rev2', rev1)):
        state = reader.signed_state(out[writer])
        assert state['files']['OWNER_QUESTION.txt'] == (out[writer] / 'OWNER_QUESTION.txt').read_bytes()
        checked = reader.check(out[writer], family, now=lambda: now)
        assert checked['documents_are_the_deterministic_construction'] is True and checked['verdict'] in ('VALID_WINDOW_OPEN', 'VALID_WINDOW_NOT_YET_OPEN')
        assert checked['binder_unchanged_since_prepare'] is False          # the binder's identity on the sheet is the one of its writer


def test_w1_same_inputs_same_bytes_and_each_revision_reproduces_the_other(rev1, base, families):
    reference = h.rehearsal_reference(base)
    parameters = h.w1_parameters(base)
    out = prepare_both(rev1, base, families['w1'], h.W1, parameters, reference, h.NOW)
    same_bytes(out['rev1'], out['rev2'])
    sign_both(rev1, out, h.NOW)
    cross_checked(rev1, out, families['w1'], h.NOW)
    # REAL mode against a synthetic executed reference
    executed = h.executed_reference(base, families['w1'])
    out = prepare_both(rev1, base, families['w1'], h.W1, h.w1_parameters(base, name='P-real.json', label='real'), executed, h.NOW, mode=b.REAL)
    same_bytes(out['rev1'], out['rev2'])
    sign_both(rev1, out, h.NOW, mode=b.REAL)
    cross_checked(rev1, out, families['w1'], h.NOW)


def test_hostops01_precheck_and_provision_same_inputs_same_bytes(rev1, base, families, hostops_harness):
    reference = h.rehearsal_reference(base)
    out = prepare_both(rev1, base, families['hostops'], h.PRECHECK, h.precheck_parameters(base), reference, h.NOW)
    same_bytes(out['rev1'], out['rev2'])
    sign_both(rev1, out, h.NOW)
    cross_checked(rev1, out, families['hostops'], h.NOW)
    # a write citing a receipt: the provision with rows copied by pointer, the review, the effects listed for the owner
    f, hostemu = hostops_harness
    k = f.load('precheck')
    world = f.world(k)
    receipt = h.resealed(f.Docs(k, f.precheck_fields(k, world, placement='A')).run(world))
    receipt_file = h.receipt_file(base / 'precheck.receipt.json', receipt)
    k = f.load('provision')
    plan = f.provision_fields(k, f.world(k), placement='A')
    plan['chains'] = {key: {'$from': {'evidence': 'PRECHECK', 'pointer': '/items/chains/%s/rows' % key}} for key in plan['chains']}
    plan['evidence_boot_id_sha256'] = {'$from': {'evidence': 'PRECHECK', 'pointer': '/items/boot/boot_id_sha256'}}
    plan['retention_tag']['image_id'] = {'$from': {'evidence': 'PRECHECK', 'pointer': '/items/image/id'}}
    parameters = h.write_json(base / 'P-provision.json', {
        'schema': b.PARAMETERS_SCHEMA, 'operation': h.PROVISION, 'label': 'provision', 'signature_model': 'IND', 'not_before': b.zulu(h.HOSTOPS_NOW),
        'not_after': b.zulu(h.HOSTOPS_NOW + b.timedelta(minutes=10)), 'plan': plan, 'review': h.review_record(base),
        'evidence': [{'role': 'PRECHECK', 'operation': h.PRECHECK, 'receipt_file': str(receipt_file)}]})
    work = base / 'provision'
    work.mkdir()
    out = prepare_both(rev1, work, families['hostops'], h.PROVISION, parameters, reference, h.HOSTOPS_NOW)
    same_bytes(out['rev1'], out['rev2'])
    sign_both(rev1, out, h.HOSTOPS_NOW)
    cross_checked(rev1, out, families['hostops'], h.HOSTOPS_NOW)


def test_the_real_w1_set_of_today_reads_the_same_with_both_revisions(rev1):
    """Today's real W1 set (its archived copy): both revisions rebuild its documents from its sheet byte for byte, and
    status() gives the same report. Read-only; the report is compared, never printed."""
    if not (REAL_W1 / 'PREPARE.json').is_file():
        pytest.skip('the archived real W1 set is not at hand')
    reports = [module.status(REAL_W1) for module in (rev1, b)]
    assert reports[0] == reports[1] and reports[1]['verified'] is True
    states = [module.signed_state(REAL_W1) for module in (rev1, b)]
    assert all(states[0][key] == states[1][key] for key in ('config_raw', 'raws', 'payload', 'signed_at'))
