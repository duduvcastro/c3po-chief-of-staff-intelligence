"""Binder revision 4 against revision 3 (the live binder, SHA256SUMS a4ddfe6e...), for every operation revision 3 binds:
the same inputs give the same bytes, each revision reads the other's signed sets byte for byte, and the rehearsal sets
revision 3 recorded on 2026-10-03 (01:34Z) are bound again by revision 4 from their own recorded parameters and compared.

Revision 3 is read from BIND_TEST_REV3 (the live S/bind) and executed from its bytes in memory (no bytecode is written
beside it; nothing in it is opened for writing). What legitimately differs is named and nothing else: the binder's own
identity on the sheet (the hash of bind_once.py), and what follows from the directory a set is bound in (its claim root:
path, device, inode; the attempt directory; and the sheet's hash, which the question quotes)."""
import json
import os
from pathlib import Path
import types

import pytest

import helpers as h
import hostops02_fixtures as x
from test_hostops02 import env, catalog_params, readback_params, release_params, activate_params          # noqa: F401 (env is a fixture)

b = h.b
REV3 = Path(os.environ.get('BIND_TEST_REV3', str(h.BIND.parent.parent / 'bind')))
REV3_SUMS = 'a4ddfe6e484be195a11f1ca3a1969fd023fbb587263ec598b25b7d39ed71cab1'
REV3_BINDER = '600475be7a4a0438dc8e54327b538ca5a274a260f478845791f341e4eccb7da0'
RECORDED = '20261003T013418Z'
VARYING = ('binder', 'claim_root_identity', 'attempt_directory')


@pytest.fixture(scope='module')
def rev3():
    if not (REV3 / 'bind_once.py').is_file():
        pytest.skip('revision 3 of the binder is not at hand (BIND_TEST_REV3)')
    assert b.sha((REV3 / 'SHA256SUMS').read_bytes()) == REV3_SUMS
    raw = (REV3 / 'bind_once.py').read_bytes()
    assert b.sha(raw) == REV3_BINDER
    module = types.ModuleType('bind_once_rev3')
    module.__file__ = str(REV3 / 'bind_once.py')          # its binder_identity() reads ACCEPTED_SEALS.json beside it
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    assert module.binder_identity()[0]['accepted_seals_sha256'] == b.binder_identity()[0]['accepted_seals_sha256']
    return module


def same_bytes(first, second):
    """Every file of two prepared sets: equal bytes, except the sheet (equal but for VARYING) and the question (equal but
    for its claim-root and sheet-hash lines)."""
    def names(root):
        return sorted(str(path.relative_to(root)) for path in Path(root).rglob('*') if path.is_file() and path.relative_to(root).parts[0] != '.dispatch-root'
                      and path.name not in ('SHA256SUMS',) and not path.name.startswith(('PUBLICATION.PROOF', 'DUDU_', 'REHEARSAL_NOT_THE_OWNER_'))
                      and path.name not in ('FINAL_PAYLOAD.BOUND.py', 'DISPATCH.BOUND.json', 'CLAIM_ROOT_IDENTITY.json'))
    listed = names(first)
    assert listed == names(second)
    differing = []
    for name in listed:
        one, two = (Path(first) / name).read_bytes(), (Path(second) / name).read_bytes()
        if name == 'PREPARE.json':
            one, two = json.loads(one), json.loads(two)
            assert set(one) == set(two)
            assert {key: value for key, value in one.items() if key not in VARYING} == {key: value for key, value in two.items() if key not in VARYING}
        elif name == 'OWNER_QUESTION.txt':
            def kept(text):
                return [line for line in text.decode('utf-8').splitlines() if not line.startswith(('- raiz local de uso único:', '- folha de assinatura (PREPARE.json)'))]
            assert kept(one) == kept(two)
        elif one != two:
            differing.append(name)
    assert differing == [], differing
    return listed


def prepare_both(rev3, base, family, operation, parameters, reference, now, mode=b.REHEARSAL):
    out = {}
    for label, module in (('rev3', rev3), ('rev4', b)):
        out[label] = Path(base) / (('rehearsal-' if mode == b.REHEARSAL else '') + label)
        module.prepare(family, operation, parameters, reference, out[label], mode, now=lambda: now)
    return out


def sign_both(rev3, out, now, mode=b.REHEARSAL):
    for label, module in (('rev3', rev3), ('rev4', b)):
        sheet = module.sha((out[label] / 'PREPARE.json').read_bytes())
        module.sign(out[label], sheet, b.zulu(now), h.answer_of(mode), now=lambda: now)


def cross_checked(rev3, out, family, now):
    """Each revision opens the other's signed set: documents and question rebuilt and compared byte for byte; the
    deterministic documents (authority, GO, payload, dispatch configuration) of the two sets differ only through the claim root."""
    for writer, reader in (('rev3', b), ('rev4', rev3)):
        state = reader.signed_state(out[writer])
        assert state['files']['OWNER_QUESTION.txt'] == (out[writer] / 'OWNER_QUESTION.txt').read_bytes()
        checked = reader.check(out[writer], family, now=lambda: now)
        assert checked['documents_are_the_deterministic_construction'] is True and checked['binder_unchanged_since_prepare'] is False
    reports = [module.status(out[label]) for label, module in (('rev3', rev3), ('rev4', b))]
    assert {key: value for key, value in reports[0].items() if key not in ('config_sha256', 'go_sha256', 'payload_sha256')} == \
           {key: value for key, value in reports[1].items() if key not in ('config_sha256', 'go_sha256', 'payload_sha256')}


def test_w1_and_hostops01_same_inputs_same_bytes(rev3, base, families, hostops_harness):
    reference = h.rehearsal_reference(base)
    out = prepare_both(rev3, base, families['w1'], h.W1, h.w1_parameters(base), reference, h.NOW)
    same_bytes(out['rev3'], out['rev4'])
    sign_both(rev3, out, h.NOW)
    cross_checked(rev3, out, families['w1'], h.NOW)
    executed = h.executed_reference(base, families['w1'])
    work = base / 'real'
    work.mkdir()
    out = prepare_both(rev3, work, families['w1'], h.W1, h.w1_parameters(base, name='P-real.json', label='real'), executed, h.NOW, mode=b.REAL)
    same_bytes(out['rev3'], out['rev4'])
    sign_both(rev3, out, h.NOW, mode=b.REAL)
    cross_checked(rev3, out, families['w1'], h.NOW)
    work = base / 'precheck'
    work.mkdir()
    out = prepare_both(rev3, work, families['hostops'], h.PRECHECK, h.precheck_parameters(base), reference, h.NOW)
    same_bytes(out['rev3'], out['rev4'])
    sign_both(rev3, out, h.NOW)
    cross_checked(rev3, out, families['hostops'], h.NOW)


@pytest.mark.parametrize('kind', ['catalog', 'readback', 'release', 'activate'])
def test_hostops02_same_inputs_same_bytes(rev3, env, base, kind):          # noqa: F811
    builders = {'catalog': (x.CATALOG, lambda: catalog_params(env, 'REHEARSAL'), x.A6),
                'readback': (x.READBACK, lambda: readback_params(env, 'PRE'), x.K11_PRE),
                'release': (x.RELEASE, lambda: release_params(env), x.M1),
                'activate': (x.ACTIVATE, lambda: activate_params(env), x.M3)}
    operation, build, now = builders[kind]
    parameters = h.write_json(Path(base) / 'P-equivalence.json', build())
    out = prepare_both(rev3, base, env.dirs[operation], operation, parameters, env.reference, now)
    same_bytes(out['rev3'], out['rev4'])
    sign_both(rev3, out, now)
    cross_checked(rev3, out, env.dirs[operation], now)


def recorded_sets():
    found = []
    for root in sorted(REV3.glob('rehearsal-*-%s' % RECORDED)) if REV3.is_dir() else []:
        found += sorted(path.parent for path in root.glob('*/PREPARE.json'))
    return found


def test_the_rehearsal_sets_recorded_by_revision_3_read_the_same_with_both_revisions(rev3):
    """Read-only: every signed set the revision 3 rehearsals left (2026-10-03, 01:34Z) is rebuilt by both revisions
    from its sheet, byte for byte, and status() reports the same."""
    sets = recorded_sets()
    if not sets:
        pytest.skip('the recorded rehearsals of revision 3 are not at hand')
    assert len(sets) == 13
    for bound in sets:
        states = [module.signed_state(bound) for module in (rev3, b)]
        assert all(states[0][key] == states[1][key] for key in ('config_raw', 'raws', 'payload', 'signed_at')), bound.name
        assert states[1]['sheet']['binder']['binder_sha256'] == REV3_BINDER          # bound by revision 3
        assert rev3.status(bound) == b.status(bound), bound.name


def recorded_parameters(bound, sheet):
    """The parameter file a recorded set was prepared from, found by its hash beside the rehearsal's sets."""
    directory = Path(sheet['hostops02']['parameters_directory']) if sheet.get('hostops02') else bound.parent
    found = [path for path in sorted(directory.glob('*.json')) if b.sha(path.read_bytes()) == sheet['parameters_sha256']]
    assert found, bound
    return found[0]


def recorded_family(bound, sheet):
    """The sealed directory the set was bound from: under the rehearsal's directory, the one whose seal the sheet names."""
    for path in sorted(bound.parent.glob('**/SHA256SUMS')):
        if path.parent != bound and b.sha(path.read_bytes()) == sheet['family']['sha256sums_sha256']:
            try:
                b.select_operation(b.verify_family(path.parent), sheet['operation'])
            except b.Refused:
                continue
            return path.parent
    raise AssertionError('family of %s not found' % bound)


def test_the_recorded_rehearsal_sets_are_bound_again_by_revision_4_to_the_same_bytes(rev3, base):
    """Each recorded set but the spares (whose primary already has its one spare) is prepared again by revision 4 from
    its own recorded parameters, family, transport reference and instant, into a new directory, and compared with the
    recorded one: the same files, the same bytes, but for the binder's identity and the claim root."""
    sets = [bound for bound in recorded_sets() if not bound.name.endswith('-spare')]
    if not sets:
        pytest.skip('the recorded rehearsals of revision 3 are not at hand')
    compared = []
    for bound in sets:
        sheet = json.loads((bound / 'PREPARE.json').read_bytes())
        out = Path(base) / ('rehearsal-again-%s-%s' % (bound.parent.name.split('-')[1], bound.name))
        b.prepare(recorded_family(bound, sheet), sheet['operation'], recorded_parameters(bound, sheet), sheet['transport_reference']['path'], out,
                  sheet['mode'], now=lambda: b.parse_utc(sheet['prepared_at_utc']))
        same_bytes(bound, out)
        compared.append(bound.parent.name + '/' + bound.name)
    assert len(compared) == 11, compared
