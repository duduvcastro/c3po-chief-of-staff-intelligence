"""Binder revision 4: the K9 host programs (K9_INTERFACE_NOTE.md rev 2, section 10.4). Synthetic only.

K9R (the read program) is bound end to end: a sealed copy of the tier (core and the four HOSTOPS02 operations) with K9R
and K4-E0 beside it, each from a snapshot taken by command (test-inputs/ beside the binder, or BIND_TEST_K9R and
BIND_TEST_K4E0); K9R's directory is sealed for the test with its own SHA256SUMS written here (K9R had not been sealed
again when these tests were written), and that seal and K4-E0's are accepted for the test by patching the binder's list
of accepted seals (ACCEPTED_SEALS.json itself is not changed). The receipts the K9 requests cite are PRODUCED by the cited
operations' own sealed sources on their own emulated hosts: the E0 receipt by K4-E0 (delivering the K9R fixtures'
synthetic runner), the TREE receipt by K9R, the K11 POST receipt by K11; they are bound to the rehearsal host and sealed
again, as the other tests do.

K9W does not exist as a sealed family yet: its rules (the K9W PLUG and the bind order) are exercised by calling k9_rules
on synthetic K9W plans with the binder's own context, never by a prepare. That is a gap, stated in DESIGN_REV4.md."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import types

import pytest

import helpers as h
from helpers import refused
import hostops02_fixtures as x

b = h.b
UTC = timezone.utc
SEC = timedelta(seconds=1)
INPUTS = h.BIND.parent / 'test-inputs'
K9R_SNAPSHOT = Path(os.environ.get('BIND_TEST_K9R', str(INPUTS / 'k9_phase_read.rev4-snapshot-20261005T0128Z')))
K4E0_SNAPSHOT = Path(os.environ.get('BIND_TEST_K4E0', str(INPUTS / 'k4_e0.sealed-63c75348')))
K9W_SNAPSHOT = Path(os.environ.get('BIND_TEST_K9W', str(INPUTS / 'k9_phase_step.sealed-92203431')))
RUNNER_FILE = Path(os.environ.get('BIND_TEST_RUNNER', str(INPUTS / 'k9_runner.rev2-563a4797' / 'k9_runner.py')))
K9W_SEAL = os.environ.get('BIND_TEST_K9W_SEAL', '922034314242dce519a716babe4ca03e5bba38463f09eb1f3f568c88e8d02344')          # revision 2 (decision 6)
K4E0_SEAL = os.environ.get('BIND_TEST_K4E0_SEAL', '63c75348fae02e3f0aa17278b62f0ea67e67f847828e9e25fb026ad40750ad4b')          # revision 4 (decision 6)
K9R, K9W, E0 = b.K9R_OPERATION, b.K9W_OPERATION, b.K4E0_OPERATION
DAY = '2026-10-06'
EVE_NOW = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)          # seg 05/10 15:00 BRT: before every window of the eve of 06/10
TREE_START = datetime(2026, 10, 5, 20, 38, tzinfo=UTC)      # seg 17:38 BRT (NOTE 6.2: TREE among the 17:38-18:03 sends)
CHAINS = {'days': 'DAYS', 'source_root': 'SOURCE_ROOT', 'secrets': 'SECRETS', 'tools': 'TOOLS', 'claims': 'CLAIMS'}
READ = {'readiness_probe': ('causal_list', 'PROBE'), 'readiness_recheck': ('causal_list', 'PROBE'), 'collect_result': ('causal_list', 'RESULT'),
        'commit_result': ('causal_list', 'RESULT'), 'publish_result': ('causal_list', 'RESULT'), 'components_result': ('components', 'RESULT'),
        'sources_result': ('sources', 'RESULT'), 'acquire_result': ('risk', 'RESULT'), 'execute_result': ('risk', 'RESULT'),
        'capture_result': ('capture', 'RESULT'), 'policy_read': ('policy_readonly', 'POLICY')}


def actb03_attempt_key(epoch, day, phase, operation):
    """actb03_lib.attempt_key, written out again (W/fable-actb03-draft-20261003-rev2/tools/actb03_lib.py:444-447)."""
    return b.sha(json.dumps([epoch, day, phase, operation], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def seal_directory(directory):
    """A test seal: SHA256SUMS over every file of the directory (the binder's verify_family reads exactly this)."""
    directory = Path(directory)
    names = sorted(str(path.relative_to(directory)) for path in directory.rglob('*') if path.is_file() and path.name != 'SHA256SUMS'
                   and '__pycache__' not in path.parts)
    raw = ''.join('%s  %s\n' % (b.sha((directory / name).read_bytes()), name) for name in names).encode()
    (directory / 'SHA256SUMS').write_bytes(raw)
    return b.sha(raw)


def grid_row(name, day, operation, slot='PRIMARY'):
    grid = json.loads((h.BIND / b.K9_GRID_FILE).read_bytes())
    entry = [item for item in grid[name] if item['day'] == day][0]
    row = [item for item in entry['rows'] if item['operation'] == operation and item['slot'] == slot][0]
    return row, entry


def launch_run_not_after(entry, row):
    launch = [item for item in entry['rows'] if item['operation'] == row['pred'] and item['track'] == row['track']][0]
    return b.parse_utc(launch['run_not_after']).isoformat()


def frm(role, pointer):
    return {'$from': {'evidence': role, 'pointer': pointer}}


@pytest.fixture(scope='session')
def k9env(tmp_path_factory, families):
    for path in (K9R_SNAPSHOT, K4E0_SNAPSHOT, K9W_SNAPSHOT):
        if not (path / 'op.py').is_file():
            pytest.skip('a K9 input snapshot is not at hand: %s' % path.name)
    root = h.resolved(tmp_path_factory.mktemp('k9'))
    copy = x.sealed_copy(root / 'tier')
    ignore = shutil.ignore_patterns('__pycache__', '.pytest_cache', 'work')
    shutil.copytree(str(K9R_SNAPSHOT), str(copy / 'k9_phase_read'), ignore=ignore)
    shutil.copytree(str(K4E0_SNAPSHOT), str(copy / 'k4_e0'), ignore=ignore)
    shutil.copytree(str(K9W_SNAPSHOT), str(copy / 'k9_phase_step'), ignore=ignore)
    assert b.sha((copy / 'k9_phase_step' / 'SHA256SUMS').read_bytes()) == K9W_SEAL          # K9W's own seal, unchanged
    k9r_seal = seal_directory(copy / 'k9_phase_read')
    assert b.sha((copy / 'k4_e0' / 'SHA256SUMS').read_bytes()) == K4E0_SEAL          # K4-E0's own seal, unchanged
    core = json.loads(json.dumps([item for item in json.loads((h.BIND / 'ACCEPTED_SEALS.json').read_bytes())['seals'] if 'core' in item][0]['core']))
    extra = [{'family': 'HOSTOPS02_K9_PHASE_READ', 'revision': 'TEST', 'sha256sums_sha256': k9r_seal, 'core': core},
             {'family': 'HOSTOPS02_K4_E0', 'revision': '4', 'sha256sums_sha256': K4E0_SEAL, 'core': core},
             {'family': 'HOSTOPS02_K9_PHASE_STEP', 'revision': 'SEALED', 'sha256sums_sha256': K9W_SEAL, 'core': core}]
    k9 = x.load_isolated([copy / 'core' / 'tests', copy / 'k9_phase_read' / 'tests'], ['family', 'hostemu', 'k9r']).k9r
    k4 = x.load_isolated([copy / 'core' / 'tests', copy / 'k4_e0' / 'tests'], ['family', 'hostemu', 'k4e0']).k4e0
    work = root / 'work'
    work.mkdir(mode=0o700)
    # the receipts, each produced by its operation's own sealed source on its emulated host
    runner = RUNNER_FILE.read_bytes()          # the reviewed runner (revision 2): K9W compiles its hash, so the fixtures use the real bytes
    assert b.sha(runner) == b.K9_RUNNER_SHA256
    docs, host = k4.case(now=datetime(2026, 10, 5, 20, 10, tzinfo=UTC), raw=runner)
    e0 = docs.run(host)
    assert e0['outcome'] == b.K4E0_OUTCOME and e0['delivered']['runner']['sha256'] == b.sha(runner), e0.get('code')
    # the week's constants as the TREE read runs under them: K9R's fixtures', with the sealed K9W's step table
    constants = k9.constants(step_table_sha256=b.K9_STEP_TABLE_SHA256, runner_sha256=b.sha(runner))
    docs, host = k9.case('TREE', constant=constants)
    k9.add_file(host, k9.PLACEMENT['tools'] + '/k9_runner-%s.py' % b.sha(runner), runner)          # E0 delivered it (above)
    tree = docs.run(host)
    assert tree['outcome'] == b.K9_TREE_OUTCOME and tree['mode'] == 'TREE', (tree.get('code'), tree.get('findings'))
    h2 = x.hostops02(copy)
    release = x.release_bytes(h2)
    policy = x.policy_bytes(h2, release)
    post = x.k11_receipt(h2, 'POST', x.K11_POST + timedelta(minutes=1), release, policy)
    files = {'e0': x.write_receipt(work / 'e0.receipt.json', x.resealed(e0)), 'tree': x.write_receipt(work / 'tree.receipt.json', x.resealed(tree)),
             'k11post': x.write_receipt(work / 'k11post.receipt.json', x.resealed(post))}
    k9r_dir = copy / 'k9_phase_read'
    source = (k9r_dir / 'build' / 'k9_phase_read.py').read_bytes()
    review = work / 'REVIEW_RECORD.K9.synthetic.txt'
    e0_dir = copy / 'k4_e0'
    k9w_dir = copy / 'k9_phase_step'
    review.write_text('SYNTHETIC TEST DOCUMENT, not a review. Names the bytes under test: K9R seal %s, source %s, final payload %s; K4-E0 seal %s, '
                      'source %s; K9W %s seal %s, source %s.\n' % (k9r_seal, b.sha(source), b.sha((k9r_dir / 'build' / 'FINAL_PAYLOAD.UNBOUND.py').read_bytes()),
                                                                K4E0_SEAL, b.sha((e0_dir / 'build' / 'k4_e0.py').read_bytes()), K9W, K9W_SEAL,
                                                                b.sha((k9w_dir / 'build' / 'k9_phase_step.py').read_bytes())))
    selected = b.select_operation(b.verify_family(k9w_dir, json.loads((h.BIND / 'ACCEPTED_SEALS.json').read_bytes())['seals'] + extra), K9W)
    k9w_m = b.load_runtime(selected['files'], selected['source_name'], selected['directory'])['source']
    # HOSTOPS01's precheck, produced on its own emulated host (the evidence of a K4-E0 request)
    h1 = x.hostops01(families['hostops'])
    precheck = x.hostops01_receipts(h1, h2.hostemu.REVISION)[0]
    files['precheck'] = x.write_receipt(work / 'precheck.receipt.json', x.resealed(precheck))
    files['runner'] = x.write(work / 'k9_runner.py', runner)
    reference = h.rehearsal_reference(work)
    return types.SimpleNamespace(root=root, copy=copy, k9r_dir=k9r_dir, extra=extra, k9=k9, k4=k4, h2=h2, e0=x.resealed(e0), tree=x.resealed(tree),
                                 post=x.resealed(post), files=files, review={'kind': 'CODEX_REVIEWED', 'document_file': str(review)}, reference=reference,
                                 work=work, COUNT=[0], precheck=x.resealed(precheck), H1=str(families['hostops']), constants=constants,
                                 k9w_dir=k9w_dir, k9w_m=k9w_m, runner=runner)


@pytest.fixture(autouse=True)
def k9_seals(request, monkeypatch):
    """The K9R test seal and K4-E0's seal accepted for the test (the binder's list, patched; the file is not changed)."""
    if 'k9env' not in request.fixturenames:
        return
    env = request.getfixturevalue('k9env')
    original = b.binder_identity

    def identity():
        found, seals = original()
        return found, json.loads(json.dumps(seals)) + json.loads(json.dumps(env.extra))
    monkeypatch.setattr(b, 'binder_identity', identity)
    # the week's risk source pins: the K9R fixtures' synthetic ones stand in for the compiled value (the runner is the real one)
    monkeypatch.setattr(b, 'K9_RISK_SOURCE_PINS_SHA256', env.k9.constants()['risk_source_pins_sha256'])
    # (the placement is NOT patched: K9R rev 4, K9W rev 2 and K4-E0 rev 4 all compile decision 6's paths)


def params(env, base, value):
    env.COUNT[0] += 1
    return h.write_json(Path(base) / ('P-k9-%d.json' % env.COUNT[0]), value)


def tree_params(env, label='k9-tree', start=TREE_START, minutes=6, evidence=None, **changes):
    plan = env.k9.tree_fields(constant=env.constants)
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': K9R, 'label': label, 'signature_model': 'EVE', 'not_before': b.zulu(start),
             'not_after': b.zulu(start + timedelta(minutes=minutes) - SEC), 'plan': plan,
             'evidence': evidence if evidence is not None else [x.cite('E0', E0, env.files['e0'], env.copy / 'k4_e0')], 'review': env.review}
    value.update(changes)
    return value


def daily_plan(env, operation, slot='PRIMARY', grid='G18', day=DAY, tree='TREE', **changes):
    phase, mode = READ[operation]
    row, entry = grid_row(grid, day, operation, slot)
    plan = {'mode': mode, 'epoch': b.K9_EPOCH, 'day': day, 'k9_phase': phase, 'k9_operation': operation, 'slot': slot,
            'attempt_key': actb03_attempt_key(b.K9_EPOCH, day, phase, operation),
            'run_not_after': launch_run_not_after(entry, row) if mode == 'RESULT' else None,
            'constants': frm(tree, '/effects/constants'),
            'parent_rows': {name: {'path': env.k9.PLACEMENT[name], 'rows': frm(tree, '/items/directory:%s/observed_rows' % key),
                                   'open_root': env.k9.open_root(name)} for name, key in CHAINS.items()},
            'evidence_boot_id_sha256': frm(tree, '/boot_id_sha256'), 'policy_read': None}
    if mode == 'POLICY':
        plan['policy_read'] = policy_read(env)
    plan.update(changes)
    return plan, row


def policy_read(env, typed=False):
    """The policy and release directories: the K11 POST receipt's observed rows of the live parent and of the release
    parent, copied by $from (typed: the same values, written out)."""
    post = env.post

    def chain(key):
        rows = post['items']['directory:%s' % key]['observed_rows']
        return {'path': rows[-1]['path'], 'rows': rows if typed else frm('K11_POST', '/items/directory:%s/observed_rows' % key), 'open_root': '/mnt/day-d-data'}
    # The tier's receipts record no observed row of the release directory itself (K11 POST: its parent, the data volume;
    # K10: the file): both directories are the live parent here, which is enough to test where the rows come from.
    return {'policy': {'directory': chain('LIVE_PARENT'), 'file_name': 'policy.json'}, 'release': {'directory': chain('LIVE_PARENT'), 'file_name': 'release.json'},
            'worker': {'container': env.k9.hostemu.WORKER, 'data_source': '/mnt/day-d-data', 'data_target': '/app/day-d-data'}}


def daily_params(env, operation, label, slot='PRIMARY', grid='G18', day=DAY, evidence=None, plan=None, row=None, **changes):
    if plan is None:
        plan, row = daily_plan(env, operation, slot, grid, day)
    elif row is None:
        row, _ = grid_row(grid, day, operation, slot)
    if evidence is None:
        evidence = [x.cite('TREE', K9R, env.files['tree'])]
        if READ[operation][1] == 'POLICY':
            evidence.append(x.cite('K11_POST', b.EPOCH_READBACK_OPERATION, env.files['k11post'], env.copy / 'epoch_readback'))
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': K9R, 'label': label, 'signature_model': 'PRE', 'not_before': row['not_before'],
             'not_after': row['not_after'], 'plan': plan, 'evidence': evidence, 'review': env.review, 'k9_grid': grid}
    value.update(changes)
    return value


def prepare(env, base, value, name, now=EVE_NOW):
    return b.prepare(env.k9r_dir, K9R, params(env, base, value), env.reference, Path(base) / name, b.REHEARSAL, now=lambda: now)


def bind(env, base, value, name, now=EVE_NOW):
    prepared = prepare(env, base, value, name, now)
    b.sign(Path(base) / name, prepared['prepare_json_sha256'], b.zulu(now), b.REHEARSAL_ANSWER, now=lambda: now)
    return Path(base) / name, prepared


def attempt(env, base, code, value, now=EVE_NOW):
    out = Path(base) / ('rehearsal-attempt-%d' % env.COUNT[0])
    with refused(code):
        prepare(env, base, value, out.name, now)
    assert not out.exists()


def resealed_file(env, name, receipt, change):
    value = json.loads(json.dumps(receipt))
    value.pop('metadata_sha256')
    change(value)
    value['metadata_sha256'] = b.sha(b.canonical(value))
    return x.write_receipt(env.work / name, value)


# ================================================================ the frozen interface, by command
def test_the_compiled_operation_list_and_grid_are_the_notes_byte_for_byte():
    note = Path('/offline/optional-work/fable-k9-interface-20261003-rev2')
    assert b.sha(b.canonical(b.K9_OPERATIONS)) == b.K9_OPERATIONS_SHA256 == 'bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'
    assert b.sha((h.BIND / b.K9_GRID_FILE).read_bytes()) == b.K9_GRID_SHA256
    if (note / 'K9_OPERATIONS.json').is_file():
        assert (note / 'K9_OPERATIONS.json').read_bytes() == b.canonical(b.K9_OPERATIONS)
        assert (note / 'aux' / 'grid9.json').read_bytes() == (h.BIND / b.K9_GRID_FILE).read_bytes()
        assert b.sha((note / 'K9_INTERFACE_NOTE.md').read_bytes()) == b.K9_NOTE_SHA256
    operations = b.k9_operation_list()
    assert len(operations) == 23 and sum(kind == 'READ' for _, kind in operations.values()) == 11
    assert b.k9_attempt_key(b.K9_EPOCH, DAY, 'causal_list', 'collect_launch') == actb03_attempt_key(b.K9_EPOCH, DAY, 'causal_list', 'collect_launch')


def test_every_window_of_both_grids_has_its_sendable_seconds_and_the_checker_agrees(tmp_path):
    """The binder's own send rule (A2 section 3, container rule, quiet bands) on all 232 windows; and on a window of the
    draft that the note's checker refused (components_launch 22:08 BRT), the binder refuses too."""
    grid = b.k9_grid()
    count = 0
    for name in b.K9_GRIDS:
        for entry in grid[name]:
            for row in entry['rows']:
                start, end = b.parse_utc(row['not_before']), b.parse_utc(row['not_after'])
                seconds = b.k9_sendable_seconds(start, end - timedelta(seconds=80), row['mode'] in b.K9_CONTAINER_MODES)
                assert seconds >= 180, row
                count += 1
    assert count == 232
    start = datetime(2026, 10, 6, 1, 8, tzinfo=UTC)          # 22:08 BRT, the draft's components_launch: only 40 sendable seconds
    assert b.k9_sendable_seconds(start, start + timedelta(minutes=6) - SEC - timedelta(seconds=80), True) < 180
    # the container rule: 18:58:40-19:25:59 BRT, never for a container step, always open for a result
    at = datetime(2026, 10, 5, 22, 0, tzinfo=UTC)          # 19:00:00 BRT
    assert not b.k9_sendable(at, True) and b.k9_sendable(at, False)
    quiet = datetime(2026, 10, 6, 3, 30, tzinfo=UTC)       # 00:30 BRT, the scan's band
    assert not b.k9_sendable(quiet, False)
    checker = Path('/offline/optional-work/fable-k9-interface-20261003-rev2/aux/check9.py')
    if checker.is_file():          # the note's checker against the binder of revision 3 (its pinned copy) and derive_daily03
        import subprocess
        rev3, tools = Path(os.environ.get('BIND_TEST_REV3', '')), Path('/offline/optional-work/fable-actb03-draft-20261003/tools')
        if (rev3 / 'bind_once.py').is_file() and (tools / 'derive_daily03.py').is_file():
            done = subprocess.run(['/usr/bin/python3', '-I', '-B', '-X', 'pycache_prefix=%s' % tmp_path, str(checker), str(h.BIND / b.K9_GRID_FILE), str(rev3), str(tools)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            assert done.returncode == 0 and json.loads(done.stdout.splitlines()[0])['status'] == 'GRID9_PASS', done.stderr[-500:]


def test_the_risk_order_is_the_notes_for_g18_and_g19():
    grid = b.k9_grid()
    order, raw, cutoff, windows = b.k9_risk_order(b.k9_rows_of_the_day(grid, 'G18', DAY), DAY, 'R2D2-V2-DIAG-R4-' + DAY)
    assert cutoff == '2026-10-06T02:26:00+00:00' and windows == {
        'preflight': {'not_before': '2026-10-06T02:38:00+00:00', 'not_after': '2026-10-06T02:44:59+00:00'},
        'acquire': {'not_before': '2026-10-06T02:41:00+00:00', 'not_after': '2026-10-06T03:46:59+00:00'},
        'execute': {'not_before': '2026-10-06T03:50:00+00:00', 'not_after': '2026-10-06T04:15:59+00:00'}}
    assert json.loads(raw) == {'schema': 'R2D2_V2_RISK_HOST_ORDER_V1', 'actions': ['READ_PROVIDERS', 'READ_DATABASE', 'WRITE_PRIVATE_RISK_ARTIFACTS'],
                               'scope': {'namespace': 'R2D2-V2-DIAG-R4-2026-10-06', 'session_date': DAY, 'cutoff_at': cutoff, 'phases': ['preflight', 'acquire', 'execute']}}
    order, raw, cutoff, windows = b.k9_risk_order(b.k9_rows_of_the_day(grid, 'G19', DAY), DAY, 'R2D2-V2-DIAG-R4-' + DAY)
    assert cutoff == '2026-10-06T03:46:00+00:00' and windows['preflight'] == {'not_before': '2026-10-06T03:53:00+00:00', 'not_after': '2026-10-06T03:59:59+00:00'}
    assert windows['acquire'] == {'not_before': '2026-10-06T03:56:00+00:00', 'not_after': '2026-10-06T05:01:59+00:00'}
    assert windows['execute'] == {'not_before': '2026-10-06T05:49:00+00:00', 'not_after': '2026-10-06T06:14:59+00:00'}


def test_frozen_interface_refusals(monkeypatch, tmp_path):
    with monkeypatch.context() as patch:
        patch.setitem(b.K9_OPERATIONS['phases']['risk'], 'stage', 'READ')
        with refused('K9_OPERATION_LIST_NOT_THE_FROZEN_ONE'):
            b.k9_operation_list()
    with monkeypatch.context() as patch:
        patch.setattr(b, 'K9_GRID_FILE', 'K9_GRID_ABSENT.json')
        with refused('K9_GRID_MISSING'):
            b.k9_grid()
    with monkeypatch.context() as patch:
        patch.setattr(b, 'K9_GRID_SHA256', 'f' * 64)
        with refused('K9_GRID_NOT_THE_NOTES'):
            b.k9_grid()
    grid = b.k9_grid()
    with refused('K9_NO_GRID_ROW'):
        b.k9_grid_row(grid, 'G18', DAY, 'readiness_probe', 'SPARE')
    with refused('K9_NO_GRID_ROW'):
        b.k9_rows_of_the_day(grid, 'G18', '2026-10-05')
    entry = b.k9_rows_of_the_day(grid, 'G18', DAY)
    with refused('K9_NO_GRID_ROW'):
        b.k9_launch_of(entry, {'pred': 'readiness_probe', 'track': 'P'})
    with refused('K9_NO_GRID_ROW'):
        b.k9_risk_order({'rows': [row for row in entry['rows'] if row['operation'] != 'preflight']}, DAY, 'R2D2-V2-DIAG-R4-' + DAY)


def test_the_day_window_rules_of_the_programs_are_refused_by_the_binder_first():
    """K9R DESIGN 7.2 and deviation 9: K9R refuses these windows only on the host, after the claim."""
    def at(text):
        return datetime.fromisoformat(text + '+00:00')
    b.k9_day_window(DAY, 'RESULT', at('2026-10-05T21:50:00'), at('2026-10-05T21:57:59'), at('2026-10-05T21:49:59'))
    with refused('K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'):
        b.k9_day_window(DAY, 'RESULT', at('2026-10-05T19:50:00'), at('2026-10-05T19:57:59'), None)          # before 20:00Z of D-1
    with refused('K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'):
        b.k9_day_window(DAY, 'POLICY', at('2026-10-06T15:00:00'), at('2026-10-06T15:05:59'), None)          # after 15:00Z of D
    with refused('K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'):
        b.k9_day_window(DAY, 'PROBE', at('2026-10-06T03:58:00'), at('2026-10-06T04:03:59'), None)           # a probe ending after 04:00Z
    with refused('K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'):
        b.k9_day_window(DAY, 'POLICY', at('2026-10-05T23:50:00'), at('2026-10-05T23:55:59'), None)          # a policy read before D
    with refused('K9_RUN_NOT_AFTER_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'):
        b.k9_day_window(DAY, 'RESULT', at('2026-10-05T21:50:00'), at('2026-10-05T21:57:59'), at('2026-10-05T19:59:59'))
    with refused('K9_RESULT_WINDOW_BEFORE_RUN_NOT_AFTER'):
        b.k9_day_window(DAY, 'RESULT', at('2026-10-05T21:49:00'), at('2026-10-05T21:57:59'), at('2026-10-05T21:49:59'))
    with refused('K9_DETACHED_RUN_LEAVES_THE_UTC_DAY_OF_ITS_LAUNCH'):
        b.k9_day_window(DAY, 'LAUNCH', at('2026-10-05T23:50:00'), at('2026-10-05T23:55:59'), at('2026-10-06T00:10:59'))


# ================================================================ K9R, end to end: TREE, then the daily reads
def test_tree_binds_with_the_runner_e0_delivered_and_the_owner_reads_it(k9env, base):
    env = k9env
    out, prepared = bind(env, base, tree_params(env), 'rehearsal-tree')
    sheet = prepared['sheet']
    k9 = sheet['hostops02']['rules']['k9']
    assert k9['mode'] == 'TREE' and k9['e0']['runner_sha256'] == b.sha(env.runner) and k9['runner_sha256'] == b.sha(env.runner)
    assert sheet['hostops02']['dispatch_gates'] == [] and sheet['writes_allowed'] is False
    question = prepared['owner_question_pt']
    assert 'PEDIDO DE ASSINATURA - K9 TREE: leitura semanal da árvore K9' in question and 'só de leitura, que não inicia contêiner' in question
    assert 'Executor k9 entregue pela E0' in question and b.sha(env.runner) in question
    checked = b.check(out, env.k9r_dir, now=lambda: EVE_NOW)
    assert checked['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN' and checked['documents_are_the_deterministic_construction'] is True
    state = b.signed_state(out)
    assert state['files']['OWNER_QUESTION.txt'] == (out / 'OWNER_QUESTION.txt').read_bytes()


def test_tree_refusals(k9env, base):
    env = k9env
    # the runner the request signs (the week's) is not the one E0 delivered (an E0 receipt of other runner bytes)
    def other_runner(value):
        for member in (value['delivered']['runner'], value['effects']['runner']):
            member['sha256'] = 'ab' * 32
        value['delivered']['runner']['path'] = b.K9_RUNNER_PATH % ('ab' * 32)
    other = resealed_file(env, 'e0-other-runner.json', env.e0, other_runner)
    attempt(env, base, 'K9_RUNNER_NOT_THE_ONE_E0_DELIVERED', tree_params(env, evidence=[x.cite('E0', E0, other, env.copy / 'k4_e0')]))
    # the runner the request signs is not the week's
    constants = dict(env.constants, runner_sha256='ab' * 32)
    attempt(env, base, 'K9_RUNNER_NOT_THE_REVIEWED_ONE', tree_params(env, plan=dict(env.k9.tree_fields(constant=env.constants), constants=constants)))
    # no E0 receipt (the TREE receipt cited instead), two E0 receipts, an E0 receipt that is not complete
    attempt(env, base, 'K9_TREE_WITHOUT_THE_E0_RECEIPT', tree_params(env, evidence=[x.cite('TREE', K9R, env.files['tree'])]))
    attempt(env, base, 'K9_E0_RECEIPT_NOT_ONE', tree_params(env, evidence=[x.cite('E0', E0, env.files['e0'], env.copy / 'k4_e0'),
                                                                           x.cite('E0_AGAIN', E0, env.files['e0'], env.copy / 'k4_e0')]))
    partial = resealed_file(env, 'e0-partial.json', env.e0, lambda value: value.update(outcome='EPOCH_ROOTS_PARTIAL', status='PARTIAL_METADATA_REQUIRES_REVIEW'))
    item = dict(x.cite('E0', E0, partial, env.copy / 'k4_e0'), accept_not_complete=True)
    attempt(env, base, 'K9_E0_RECEIPT_NOT_COMPLETE', tree_params(env, evidence=[item]))
    # a grid, a spare, a gate: none for the weekly read
    attempt(env, base, 'K9_TREE_PLAN_INVALID', tree_params(env, k9_grid='G18'))
    attempt(env, base, 'K9_GATE_IS_THE_GRID_WINDOW', tree_params(env, gate_not_before=b.zulu(TREE_START + timedelta(minutes=1)),
                                                                  gate_not_after=b.zulu(TREE_START + timedelta(minutes=6) - SEC)))
    # a window in the quiet band of the 00:17 scan (00:26-00:31 BRT): no sendable second
    attempt(env, base, 'K9_SENDABLE_SECONDS_BELOW_180', tree_params(env, start=datetime(2026, 10, 6, 3, 26, tzinfo=UTC)))


def test_every_daily_read_of_the_eve_and_morning_binds_on_g18_and_each_sheet_is_told_apart(k9env, base):
    env = k9env
    titles, keys = {}, set()
    for operation in sorted(READ):
        out, prepared = bind(env, base, daily_params(env, operation, 'k9-' + operation.replace('_', '-')), 'rehearsal-' + operation.replace('_', '-'))
        sheet = prepared['sheet']
        k9 = sheet['hostops02']['rules']['k9']
        row, entry = grid_row('G18', DAY, operation)
        assert (k9['grid'], k9['window_not_before'], k9['window_not_after'], k9['operation']) == ('G18', row['not_before'], row['not_after'], operation)
        assert k9['attempt_key'] == actb03_attempt_key(b.K9_EPOCH, DAY, READ[operation][0], operation)
        assert k9['tree']['receipt_sha256'] == env.tree['metadata_sha256'] and k9['tree']['runner_sha256'] == b.sha(env.runner)
        assert sheet['window']['not_before'] == row['not_before'] and sheet['window']['gate_not_after'] == row['not_after']
        if READ[operation][1] == 'RESULT':
            assert k9['run_not_after'] == launch_run_not_after(entry, row) and k9['launch'] == row['pred']
        # the rows, the boot and the constants were copied from the TREE receipt
        copied = {item['plan_pointer'] for item in sheet['plan_values_copied_from_receipts'] if item.get('evidence_role') == 'TREE'}
        assert {'/constants', '/evidence_boot_id_sha256'} | {'/parent_rows/%s/rows' % name for name in CHAINS} <= copied
        question = prepared['owner_question_pt']
        title = [line for line in question.splitlines() if line.startswith('PEDIDO DE ASSINATURA - ')][0]
        assert title.startswith('PEDIDO DE ASSINATURA - K9 %s' % operation) and 'sessão 2026-10-06, vaga PRIMÁRIA, grade G18' in title
        assert ('INICIA UM CONTÊINER' in title) == (READ[operation][1] == 'PROBE')
        assert 'Leitura TREE em que este pedido se apoia' in question and 'o K9R não grava reivindicação' in question
        titles[operation] = title
        keys.add(k9['attempt_key'])
        checked = b.check(out, env.k9r_dir, now=lambda: EVE_NOW)
        assert checked['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN' and checked['dispatch_gates']['required'] == []
    assert len(set(titles.values())) == len(READ) and len(keys) == len(READ)


def test_g19_the_other_days_and_typed_values_equal_to_the_tree_reads(k9env, base):
    env = k9env
    out, prepared = bind(env, base, daily_params(env, 'commit_result', 'g19-commit', grid='G19'), 'rehearsal-g19-commit')
    assert prepared['sheet']['hostops02']['rules']['k9']['window_not_before'] == '2026-10-05T23:08:00Z'
    for day in ('2026-10-07', '2026-10-08', '2026-10-09'):
        plan, row = daily_plan(env, 'execute_result', day=day)
        prepare(env, base, daily_params(env, 'execute_result', 'exe-' + day, day=day, plan=plan, row=row), 'rehearsal-exe-' + day)
    # the same values written out instead of copied: PLAN_SOURCES finds them equal to the TREE receipt's
    tree = env.tree
    plan, row = daily_plan(env, 'collect_result', constants=tree['effects']['constants'], evidence_boot_id_sha256=tree['boot_id_sha256'])
    plan['parent_rows'] = {name: dict(plan['parent_rows'][name], rows=tree['items']['directory:%s' % key]['observed_rows']) for name, key in CHAINS.items()}
    prepared = prepare(env, base, daily_params(env, 'collect_result', 'typed', plan=plan, row=row), 'rehearsal-typed')
    checked = {item['plan_pointer'] for item in prepared['sheet']['plan_values_equal_to_the_cited_receipts']}
    assert {'/evidence_boot_id_sha256'} | {'/parent_rows/%s/rows' % name for name in CHAINS} <= checked


def test_policy_read_takes_its_directory_rows_from_the_cited_k11_post(k9env, base):
    env = k9env
    plan, row = daily_plan(env, 'policy_read')
    # the K11 receipt's boot is the emulated host's: the same as the TREE read's in these fixtures
    assert env.post['effects']['evidence_boot_id_sha256'] == env.tree['boot_id_sha256']
    prepared = prepare(env, base, daily_params(env, 'policy_read', 'policy', plan=plan, row=row), 'rehearsal-policy', now=datetime(2026, 10, 6, 11, 0, tzinfo=UTC))
    assert set(prepared['sheet']['hostops02']['rules']['k9']['policy_rows']) == {'policy', 'release'}
    plan['policy_read'] = policy_read(env, typed=True)
    attempt(env, base, 'K9_POLICY_ROWS_NOT_COPIED_FROM_A_CITED_RECEIPT', daily_params(env, 'policy_read', 'policy-typed', plan=plan, row=row),
            now=datetime(2026, 10, 6, 11, 0, tzinfo=UTC))


def test_daily_read_refusals(k9env, base):
    env = k9env
    # no grid named; the window one minute off the grid's row; a window outside the eve and morning of D
    value = daily_params(env, 'collect_result', 'no-grid')
    value.pop('k9_grid')
    attempt(env, base, 'K9_GRID_NOT_NAMED', value)
    attempt(env, base, 'K9_GRID_NOT_NAMED', daily_params(env, 'collect_result', 'grid-g20', k9_grid='G20'))
    attempt(env, base, 'K9_WINDOW_NOT_THE_GRIDS', daily_params(env, 'collect_result', 'shifted', not_before='2026-10-05T21:51:00Z', not_after='2026-10-05T21:58:59Z'))
    attempt(env, base, 'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY', daily_params(env, 'collect_result', 'early', not_before='2026-10-05T19:50:00Z',
                                                                                      not_after='2026-10-05T19:57:59Z'))
    attempt(env, base, 'K9_RESULT_WINDOW_BEFORE_RUN_NOT_AFTER', daily_params(env, 'collect_result', 'before-run', not_before='2026-10-05T21:46:00Z',
                                                                             not_after='2026-10-05T21:53:59Z'))
    # a gate narrower than the grid's window
    attempt(env, base, 'K9_GATE_IS_THE_GRID_WINDOW', daily_params(env, 'collect_result', 'gate', gate_not_before='2026-10-05T21:51:00Z',
                                                                  gate_not_after='2026-10-05T21:57:59Z'))
    # run_not_after that is not the launch's (K9R itself accepts any instant there)
    plan, row = daily_plan(env, 'collect_result', run_not_after='2026-10-05T21:49:58+00:00')
    attempt(env, base, 'K9_RUN_NOT_AFTER_NOT_THE_GRIDS', daily_params(env, 'collect_result', 'rna', plan=plan, row=row))
    # constants that are not the TREE read's (K9R checks their grammar only for these)
    tree = env.tree
    plan, row = daily_plan(env, 'collect_result', constants=dict(tree['effects']['constants'], act_b_sha256='a2' * 32))
    attempt(env, base, 'K9_CONSTANTS_NOT_THE_TREE_READS', daily_params(env, 'collect_result', 'constants', plan=plan, row=row))
    # a TREE receipt that is not the complete TREE read (accepted as not complete by the parameter, then refused by the rule)
    partial = resealed_file(env, 'tree-partial.json', tree, lambda value: value.update(outcome='OBSERVED_ALL_EXPECTATIONS_NOT_MET',
                                                                                      status='PARTIAL_METADATA_REQUIRES_REVIEW'))
    attempt(env, base, 'K9_TREE_RECEIPT_NOT_THE_COMPLETE_TREE_READ', daily_params(env, 'collect_result', 'tree-partial', evidence=[
        dict(x.cite('TREE', K9R, partial), accept_not_complete=True)]))
    # a TREE read that did not find the signed runner (complete otherwise, as an edited receipt would say)
    unfound = resealed_file(env, 'tree-runner.json', tree, lambda value: value['items']['runner_file'].update(bytes_equal_signed=False))
    attempt(env, base, 'K9_TREE_READ_DID_NOT_FIND_THE_SIGNED_RUNNER', daily_params(env, 'collect_result', 'tree-runner', evidence=[x.cite('TREE', K9R, unfound)]))
    # a SPARE slot bound without its primary, and a PRIMARY that names a primary
    attempt(env, base, 'K9_SPARE_WITHOUT_ITS_PRIMARY', daily_params(env, 'collect_result', 'spare-alone', slot='SPARE'))
    attempt(env, base, 'K9_SPARE_WITHOUT_ITS_PRIMARY', daily_params(env, 'collect_result', 'primary-spare-of', spare_of={'bound': str(base)}))
    # a slot without a row of the grid: the probe has no SPARE (the recheck is a PRIMARY of the S track)
    plan, _ = daily_plan(env, 'collect_result')
    plan.update(k9_operation='readiness_probe', mode='PROBE', run_not_after=None, slot='SPARE',
                attempt_key=actb03_attempt_key(b.K9_EPOCH, DAY, 'causal_list', 'readiness_probe'))
    row, _ = grid_row('G18', DAY, 'readiness_probe')
    attempt(env, base, 'K9_NO_GRID_ROW', daily_params(env, 'readiness_probe', 'probe-spare', plan=plan, row=row, spare_of={'bound': str(base)}))


def test_spare_of_a_primary_on_the_s_track(k9env, base):
    env = k9env
    primary, _ = bind(env, base, daily_params(env, 'collect_result', 'collect-p'), 'rehearsal-collect-p')
    value = daily_params(env, 'collect_result', 'collect-s', slot='SPARE', spare_of={'bound': str(primary)})
    spare, prepared = bind(env, base, value, 'rehearsal-collect-s')
    h02 = prepared['sheet']['hostops02']
    assert h02['spare_of']['label'] == 'collect-p' and h02['dispatch_gates'] == ['SPARE_PRIMARY_NEVER_PREPARED']
    assert h02['spare_of']['replaces_a_prepared_primary_past_its_latest_start'] is True
    assert 'Este é o pedido RESERVA do pedido collect-p' in prepared['owner_question_pt'] and 'vaga RESERVA, grade G18' in prepared['owner_question_pt']
    checked = b.check(spare, env.k9r_dir, now=lambda: EVE_NOW)
    assert checked['dispatch_gates']['failed'] == [] and checked['dispatch_gates']['facts']['primary_claim_root'] == 'EMPTY'
    # a second spare of the same primary; a spare of a primary of another K9 operation; a spare on another grid
    attempt(env, base, 'SPARE_ALREADY_BOUND_FOR_THIS_PRIMARY', dict(value, label='collect-s2'))
    other, _ = bind(env, base, daily_params(env, 'readiness_probe', 'probe-p'), 'rehearsal-probe-p')
    attempt(env, base, 'K9_SPARE_NOT_OF_ITS_PRIMARY', daily_params(env, 'collect_result', 'collect-s3', slot='SPARE', spare_of={'bound': str(other)}))
    g19, _ = bind(env, base, daily_params(env, 'commit_result', 'commit-p-g19', grid='G19'), 'rehearsal-commit-p-g19')
    attempt(env, base, 'K9_SPARE_NOT_OF_ITS_PRIMARY', daily_params(env, 'commit_result', 'commit-s-g18', slot='SPARE', spare_of={'bound': str(g19)}))


# ================================================================ k9_rules on synthetic contexts: K9W (the PLUG) and what a prepare cannot reach
def k9w_plan(env, operation, slot='PRIMARY', grid='G18', day=DAY, **changes):
    phase = b.k9_operation_list()[operation][0]
    row, entry = grid_row(grid, day, operation, slot)
    tree = env.tree
    plan = {'mode': row['mode'], 'epoch': b.K9_EPOCH, 'day': day, 'k9_phase': phase, 'k9_operation': operation, 'slot': slot,
            'attempt_key': actb03_attempt_key(b.K9_EPOCH, day, phase, operation),
            'run_not_after': b.parse_utc(row['run_not_after']).isoformat() if row['mode'] == 'LAUNCH' else None,
            'constants': json.loads(json.dumps(tree['effects']['constants'])),
            'parent_rows': {name: {'path': env.k9.PLACEMENT[name], 'rows': tree['items']['directory:%s' % key]['observed_rows'], 'open_root': env.k9.open_root(name)}
                            for name, key in CHAINS.items()},
            'evidence_boot_id_sha256': tree['boot_id_sha256'], 'bind': None}
    if operation == 'bind':
        _, raw, cutoff, windows = b.k9_risk_order(entry, day, 'R2D2-V2-DIAG-R4-' + day)
        plan['bind'] = {'namespace': 'R2D2-V2-DIAG-R4-' + day, 'cutoff_at': cutoff, 'phase_windows': windows,
                        'owner_order_text': raw.decode('ascii'), 'owner_order_sha256': b.sha(raw)}
    plan.update(changes)
    return plan, row


def unit_ctx(env, operation, plan, row, params=None, watchdog=80, source=None, receipts=None, start=None, end=None):
    receipts = receipts if receipts is not None else {'TREE': (K9R, env.tree)}
    start = start or b.parse_utc(row['not_before'])
    end = end or b.parse_utc(row['not_after'])
    return {'operation': operation, 'plan': plan, 'params': params if params is not None else {'k9_grid': 'G18'},
            'rt': {'source': source or types.SimpleNamespace()}, 'window': {'start': start, 'end': end, 'gate_start': start, 'gate_end': end},
            'watchdog': watchdog, 'entries': [{'role': role, 'operation': op} for role, (op, _) in receipts.items()],
            'receipts': {role: receipt for role, (_, receipt) in receipts.items()},
            'evidence_facts': [{'role': role, 'complete': True} for role in receipts], 'copied': []}


def test_k9w_plug_every_step_of_the_eve_and_morning_passes_the_rules(k9env):
    env = k9env
    writes = sorted(name for name, (_, kind) in b.k9_operation_list().items() if kind == 'WRITE')
    assert len(writes) == 12
    for operation in writes:
        plan, row = k9w_plan(env, operation)
        rules = b.k9_rules(unit_ctx(env, K9W, plan, row))['k9']
        assert rules['program'] == 'K9W' and rules['operation'] == operation and rules['container_rule'] is True
        assert (rules['risk_order'] is not None) == (operation == 'bind')
        lines = b.k9_effects_lines(K9W, json.loads(b.canonical(env.k9w_m.effects_of(plan))), plan) + b.k9_question_lines(rules)
        assert all(line.isprintable() for line in lines)
        title = b.k9_title_pt(b.HOSTOPS02_TEXT_PT[K9W][operation][0], rules)
        assert title.startswith('K9 %s' % operation)
    rules = b.k9_rules(unit_ctx(env, K9W, *k9w_plan(env, 'bind')))['k9']
    assert rules['risk_order']['cutoff_at'] == '2026-10-06T02:26:00+00:00' and rules['risk_order']['namespace'] == 'R2D2-V2-DIAG-R4-2026-10-06'
    # the S track and G19
    for operation in ('collect_launch', 'commit_launch', 'publish_launch'):
        b.k9_rules(unit_ctx(env, K9W, *k9w_plan(env, operation, slot='SPARE'), params={'k9_grid': 'G18', 'spare_of': {}}))
        b.k9_rules(unit_ctx(env, K9W, *k9w_plan(env, operation, grid='G19'), params={'k9_grid': 'G19'}))


def test_k9w_plug_refusals(k9env):
    env = k9env

    def refuse(code, plan, row, **options):
        with refused(code):
            b.k9_rules(unit_ctx(env, K9W, plan, row, **options))
    plan, row = k9w_plan(env, 'bind')
    # the order: other bytes, another hash, another cutoff, other windows, another namespace (N-1), text not ASCII or not canonical
    order = json.loads(plan['bind']['owner_order_text'])
    order['scope']['cutoff_at'] = '2026-10-06T02:27:00+00:00'
    other = b.canonical(order)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], owner_order_text=other.decode('ascii'), owner_order_sha256=b.sha(other))), row)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], owner_order_sha256='c' * 64)), row)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], cutoff_at='2026-10-06T02:27:00+00:00')), row)
    windows = json.loads(json.dumps(plan['bind']['phase_windows']))
    windows['preflight']['not_after'] = '2026-10-06T02:43:59+00:00'
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], phase_windows=windows)), row)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], owner_order_text='caf\u00e9')), row)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind=dict(plan['bind'], owner_order_text=plan['bind']['owner_order_text'] + ' ')), row)
    refuse('K9_BIND_ORDER_NOT_THE_GRIDS', dict(plan, bind={'namespace': plan['bind']['namespace']}), row)
    shadow = dict(plan['bind'], namespace='R2D2-V2-SHADOW-' + DAY)
    refuse('K9_BIND_NAMESPACE_NOT_ACCEPTED', dict(plan, bind=shadow), row)
    plan, row = k9w_plan(env, 'preflight')
    refuse('K9_BIND_MEMBERS_OUTSIDE_BIND', dict(plan, bind=k9w_plan(env, 'bind')[0]['bind']), row)
    # K9W's own window rules (k9w_window_of on the host), refused first
    plan, row = k9w_plan(env, 'collect_launch')
    view = b.k9w_view(plan)

    def at(text):
        return datetime.fromisoformat(text + '+00:00')
    with refused('K9_WINDOW_NOT_OF_THE_STEP_CLASS'):
        b.k9w_window_rules(view, at('2026-10-06T13:26:00'), at('2026-10-06T13:31:59'), None)
    with refused('K9_WINDOW_NOT_OF_THE_STEP_CLASS'):
        b.k9w_window_rules(dict(view, operation='capture_launch'), at('2026-10-06T13:20:00'), at('2026-10-06T13:25:59'), None)
    with refused('K9_CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER'):
        b.k9w_window_rules(dict(view, operation='capture_cleanup'), at('2026-10-06T14:00:00'), at('2026-10-06T14:05:59'), None)
    with refused('K9_RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT'):
        b.k9w_window_rules(dict(view, operation='commit_launch'), at('2026-10-06T03:30:00'), at('2026-10-06T03:35:59'), at('2026-10-06T03:50:01'))
    with refused('K9_RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING'):
        b.k9w_window_rules(view, at('2026-10-05T21:29:00'), at('2026-10-05T21:34:59'), at('2026-10-05T21:49:58'))
    b.k9w_window_rules(dict(view, operation='capture_launch'), at('2026-10-06T13:50:00'), at('2026-10-06T13:59:59'), at('2026-10-06T14:03:00'),
                       at('2026-10-06T13:58:39'))
    with refused('K9_RUN_NOT_AFTER_TOO_CLOSE_TO_THE_LATEST_START'):          # a capture window ending at 14:01:59: 154 s left at its latest start
        b.k9w_window_rules(dict(view, operation='capture_launch'), at('2026-10-06T13:56:00'), at('2026-10-06T14:01:59'), at('2026-10-06T14:03:00'),
                           at('2026-10-06T14:00:39'))
    # run_not_after: a LAUNCH's is the grid's, an ATTACHED step has none
    refuse('K9_RUN_NOT_AFTER_NOT_THE_GRIDS', dict(plan, run_not_after='2026-10-05T21:49:58+00:00'), row)
    plan2, row2 = k9w_plan(env, 'stage')
    refuse('K9_RUN_NOT_AFTER_NOT_THE_GRIDS', dict(plan2, run_not_after='2026-10-06T04:34:59+00:00'), row2)
    # the mode of the program, the mode of the row, the operation of the program
    refuse('K9_MODE_NOT_OF_THIS_PROGRAM', dict(plan, mode='RESULT'), row)
    refuse('K9_GRID_ROW_NOT_OF_THIS_MODE', dict(plan, mode='ATTACHED'), row)
    refuse('K9_OPERATION_NOT_OF_THIS_PROGRAM', dict(plan, k9_operation='collect_result'), row)
    refuse('K9_OPERATION_NOT_OF_THIS_PROGRAM', dict(plan, k9_phase='sources'), row)
    # day, slot, key, epoch, constants
    refuse('K9_DAY_NOT_A_SESSION_WITH_A_K9_LIST', dict(plan, day='2026-10-05'), row)
    refuse('K9_SLOT_INVALID', dict(plan, slot='TERTIARY'), row)
    refuse('K9_ATTEMPT_KEY_NOT_RECOMPUTED', dict(plan, attempt_key=actb03_attempt_key(b.K9_EPOCH, '2026-10-07', 'causal_list', 'collect_launch')), row)
    refuse('K9_CONSTANTS_NOT_OF_THIS_INTERFACE', dict(plan, epoch='R2D2-V2-SHADOW-2026-09-28'), row)
    refuse('K9_CONSTANTS_NOT_OF_THIS_INTERFACE', dict(plan, constants=dict(plan['constants'], k9_interface_note_sha256='16d65f1a' + '0' * 56)), row)
    refuse('K9_CONSTANTS_NOT_THE_TREE_READS', dict(plan, constants=dict(plan['constants'], act_b_sha256='b3' * 32)), row)
    # the program's own interface, the watchdog, the gate
    refuse('K9_PROGRAM_NOT_OF_THIS_INTERFACE', plan, row, source=types.SimpleNamespace(K9_EPOCH='R2D2-V2-SHADOW-2026-09-28'))
    refuse('K9_PROGRAM_NOT_OF_THIS_INTERFACE', plan, row, source=types.SimpleNamespace(K9_DAYS=('2026-10-06',)))
    refuse('K9_WATCHDOG_NOT_THE_GRIDS', plan, row, watchdog=90)
    ctx = unit_ctx(env, K9W, plan, row)
    ctx['window']['gate_start'] += SEC
    with refused('K9_GATE_IS_THE_GRID_WINDOW'):
        b.k9_rules(ctx)
    # the TREE receipt: none, two, of another boot, rows not its rows
    refuse('K9_TREE_RECEIPT_NOT_CITED', plan, row, receipts={})
    refuse('K9_TREE_RECEIPT_NOT_CITED', plan, row, receipts={'TREE': (K9R, env.tree), 'TREE2': (K9R, env.tree)})
    refuse('EVIDENCE_NOT_OF_THE_SAME_BOOT', dict(plan, evidence_boot_id_sha256='d' * 64), row)
    rows = json.loads(json.dumps(plan['parent_rows']))
    rows['claims']['rows'][-1]['inode'] += 1
    refuse('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', dict(plan, parent_rows=rows), row)
    refuse('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT', dict(plan, parent_rows={'days': rows['days']}), row)
    # the window: no sendable second, not the grid's
    attached, attached_row = k9w_plan(env, 'preflight')          # no run_not_after: the window alone decides
    refuse('K9_SENDABLE_SECONDS_BELOW_180', attached, attached_row, watchdog=80, start=b.parse_utc(attached_row['not_before']),
           end=b.parse_utc(attached_row['not_before']) + timedelta(seconds=200))
    refuse('K9_WINDOW_NOT_THE_GRIDS', plan, row, start=b.parse_utc(row['not_before']) + SEC)
    # a cited E0 receipt whose runner is not the constants' (any K9 request that cites one)
    other_runner = json.loads(json.dumps(env.e0))
    other_runner['delivered']['runner']['sha256'] = other_runner['effects']['runner']['sha256'] = 'ee' * 32
    refuse('K9_RUNNER_NOT_THE_ONE_E0_DELIVERED', plan, row, receipts={'TREE': (K9R, env.tree), 'E0': (E0, other_runner)})
    b.k9_rules(unit_ctx(env, K9W, plan, row, receipts={'TREE': (K9R, env.tree), 'E0': (E0, env.e0)}))          # and the delivered one passes
    # a spare of another grid or operation: K9 spare equivalence
    primary_plan, _ = k9w_plan(env, 'collect_launch')
    spare_plan, spare_row = k9w_plan(env, 'collect_launch', slot='SPARE')
    ctx = unit_ctx(env, K9W, spare_plan, spare_row, params={'k9_grid': 'G18', 'spare_of': {}})
    rules = b.k9_rules(ctx)['k9']
    primary = {'files': {'REQUEST.BOUND.json': b.canonical({'plan': primary_plan})}, 'sheet': {'hostops02': {'rules': {'k9': dict(rules, slot='PRIMARY')}}}}
    b.k9_spare_of_its_primary(ctx, primary)
    with refused('K9_SPARE_NOT_OF_ITS_PRIMARY'):
        b.k9_spare_of_its_primary(ctx, {'files': {'REQUEST.BOUND.json': b.canonical({'plan': dict(primary_plan, constants={})})}, 'sheet': primary['sheet']})
    with refused('K9_SPARE_NOT_OF_ITS_PRIMARY'):
        b.k9_spare_of_its_primary(ctx, {'files': {}, 'sheet': primary['sheet']})


def test_the_owner_texts_cover_every_k9_operation_and_are_fixed():
    operations = b.k9_operation_list()
    assert set(b.HOSTOPS02_TEXT_PT[K9R]) == {name for name, (_, kind) in operations.items() if kind == 'READ'} | {'TREE'}
    assert set(b.HOSTOPS02_TEXT_PT[K9W]) == {name for name, (_, kind) in operations.items() if kind == 'WRITE'}
    titles = [text[0] for program in (K9R, K9W) for text in b.HOSTOPS02_TEXT_PT[program].values()]
    assert len(set(titles)) == len(titles) == 24
    assert all(line.isprintable() for program in (K9R, K9W) for text in b.HOSTOPS02_TEXT_PT[program].values() for part in text for line in part.split('\n'))
    assert all(b.REAL_ANSWER.lower() not in part.lower() for program in (K9R, K9W) for text in b.HOSTOPS02_TEXT_PT[program].values() for part in text)
    for mode in ('RESULT', 'PROBE', 'POLICY', 'TREE'):
        assert (K9R, mode) in b.OUTCOME_TEXT_PT
    for mode in ('LAUNCH', 'ATTACHED', 'CLEANUP', None):
        assert (K9W, mode) in b.OUTCOME_TEXT_PT


def test_rev4_leaves_the_accepted_seals_file_as_it_was_and_ships_the_template():
    """The externally pinned current operative registry is unchanged by fixture projection; the historical template
    names the three families a K9 bind needs."""
    assert b.sha(Path(os.environ['BIND_TEST_OPERATIONAL_SEALS']).read_bytes()) == '78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72'
    template = json.loads((h.BIND / 'ACCEPTED_SEALS.K9-TEMPLATE.json').read_bytes())
    families = {item['family']: item for item in template['seals_to_add']}
    assert set(families) == {'HOSTOPS02_K4_E0', 'HOSTOPS02_K9_PHASE_READ', 'HOSTOPS02_K9_PHASE_STEP', 'HOSTOPS02_K3K9_SECRETS'}
    assert families['HOSTOPS02_K4_E0']['sha256sums_sha256'] == K4E0_SEAL and families['HOSTOPS02_K9_PHASE_STEP']['sha256sums_sha256'] == K9W_SEAL
    accepted = json.loads((h.BIND / 'ACCEPTED_SEALS.json').read_bytes())['seals']
    core = [item['core'] for item in accepted if 'core' in item][0]
    assert all(item['core'] == core for name, item in families.items() if name != 'HOSTOPS02_K3K9_SECRETS')
    assert families['HOSTOPS02_K3K9_SECRETS']['core'] != core          # its own core: see the template's note



# ================================================================ rev 4b: the week's compiled constants, K4-E0 and K3-K9
def test_the_compiled_runner_is_the_runner_file_and_the_constants_are_checked(k9env, monkeypatch):
    runner = Path('/offline/optional-work/fable-k9runner-20261004/k9_runner.py')
    monkeypatch.undo()          # the compiled values themselves, not the fixtures' stand-ins
    if runner.is_file():
        raw = runner.read_bytes()
        assert len(raw) == 40618 <= 40960 and b.sha(raw) == b.K9_RUNNER_SHA256 == '563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'
    assert b.K9_RISK_SOURCE_PINS_SHA256 == 'faaa35a7905076231f1847616c600968193c69ce064b6bd1db9cdbd6b77852bb' and b.K9_DISK_FLOOR_BYTES == 214748364800
    assert b.K9_PLACEMENT_PATHS['source_root'] == '/var/lib/c3po/r2d2-v2-source-20261005' and b.K9_PLACEMENT_PATHS['k9_root'] == '/var/lib/c3po/r2d2-v2-k9-20261005'
    assert set(b.K9_PLACEMENT_PATHS) < set(k9env.k9.PLACEMENT)
    good = dict(k9env.constants, runner_sha256=b.K9_RUNNER_SHA256, risk_source_pins_sha256=b.K9_RISK_SOURCE_PINS_SHA256)
    good['placement'] = dict(good['placement'], **b.K9_PLACEMENT_PATHS)
    b.k9_compiled_constants(good)
    with refused('K9_RUNNER_NOT_THE_REVIEWED_ONE'):
        b.k9_compiled_constants(dict(good, runner_sha256='ab' * 32))
    for change in ({'risk_source_pins_sha256': 'c3' * 32}, {'step_table_sha256': 'b2' * 32}, {'disk_floor_bytes': 1 << 30}, {'placement': dict(good['placement'], k9_root='/var/lib/x')},
                   {'placement': dict(good['placement'], source_root='/mnt/day-d-data/r2d2-v2-source-20261005')}, {'placement': dict(good['placement'], k9_open_root='/var')},
                   {'placement': None}):
        with refused('K9_CONSTANTS_NOT_THE_COMPILED_ONES'):
            b.k9_compiled_constants(dict(good, **change))


def test_k9_chains_must_be_root_controlled(k9env):
    env = k9env
    plan, row = k9w_plan(env, 'collect_launch')
    b.k9_root_controlled(plan['parent_rows']['days']['rows'])
    rows = json.loads(json.dumps(plan['parent_rows']['days']['rows']))
    rows[1]['gid'] = 1000
    with refused('K9_CHAIN_NOT_ROOT_CONTROLLED'):
        b.k9_root_controlled(rows)
    rows[1]['gid'], rows[1]['mode'] = 0, rows[1]['mode'] | 0o2000
    with refused('K9_CHAIN_NOT_ROOT_CONTROLLED'):
        b.k9_root_controlled(rows)
    opened = json.loads(json.dumps(plan['parent_rows']))
    opened['tools']['open_root'] = '/var/lib'
    with refused('K9_CHAIN_NOT_ROOT_CONTROLLED'):
        b.k9_rules(unit_ctx(env, K9W, dict(plan, parent_rows=opened), row))


E0_START = datetime(2026, 10, 5, 20, 38, tzinfo=UTC)


def e0_params(env, label='e0', start=E0_START, minutes=6, runner_file=None, **changes):
    plan = {'parent': frm('PRECHECK', '/items/chains/VAR_LIB/rows'),
            'runner': {'path': b.K9_RUNNER_PATH % b.sha(env.runner), 'content_b64': {'$input': 'runner', 'as': 'b64'},
                       'sha256': {'$input': 'runner', 'as': 'sha256'}, 'bytes': {'$input': 'runner', 'as': 'bytes'}},
            'evidence_boot_id_sha256': frm('PRECHECK', '/items/boot/boot_id_sha256')}
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': E0, 'label': label, 'signature_model': 'EVE', 'not_before': b.zulu(start),
             'not_after': b.zulu(start + timedelta(minutes=minutes) - SEC), 'plan': plan,
             'evidence': [x.cite('PRECHECK', b.PRECHECK_OPERATION, env.files['precheck'], env.H1)], 'review': env.review,
             'inputs': {'runner': str(runner_file or env.files['runner'])}}
    value.update(changes)
    return value


def test_k4e0_binds_with_the_runner_file_of_the_week(k9env, base):
    env = k9env
    out = Path(base) / 'rehearsal-e0'
    prepared = b.prepare(env.copy / 'k4_e0', E0, params(env, base, e0_params(env)), env.reference, out, b.REHEARSAL, now=lambda: EVE_NOW)
    b.sign(out, prepared['prepare_json_sha256'], b.zulu(EVE_NOW), b.REHEARSAL_ANSWER, now=lambda: EVE_NOW)
    sheet = prepared['sheet']
    rules = sheet['hostops02']['rules']['k9_prerequisite']
    assert rules['program'] == 'K4E0' and rules['runner_sha256'] == b.sha(env.runner) and sheet['hostops02']['dispatch_gates'] == ['CODEX_REVIEW_OF_THE_BOUND_SET']
    assert sheet['hostops02']['bind_inputs'] == {'runner': {'sha256': b.sha(env.runner), 'bytes': len(env.runner)}}
    question = prepared['owner_question_pt']
    assert 'PEDIDO DE ASSINATURA - K4 E0: cria a árvore K9 e entrega o executor k9 (GRAVAÇÃO)' in question and b.sha(env.runner) in question
    checked = b.check(out, env.copy / 'k4_e0', now=lambda: EVE_NOW)
    assert checked['documents_are_the_deterministic_construction'] is True


def test_k4e0_refusals(k9env, base):
    env = k9env

    def attempt_e0(code, value):
        out = Path(base) / ('rehearsal-e0-attempt-%d' % env.COUNT[0])
        with refused(code):
            b.prepare(env.copy / 'k4_e0', E0, params(env, base, value), env.reference, out, b.REHEARSAL, now=lambda: EVE_NOW)
        assert not out.exists()
    other = x.write(env.work / 'k9_runner.other.py', env.runner + b'# another byte\n')
    value = e0_params(env, runner_file=other)
    value['plan']['runner']['path'] = b.K9_RUNNER_PATH % b.sha(env.runner + b'# another byte\n')
    attempt_e0('K9_RUNNER_NOT_THE_REVIEWED_ONE', value)
    attempt_e0('K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND', e0_params(env, start=datetime(2026, 10, 5, 19, 38, tzinfo=UTC)))
    ctx = {'rt': {'source': types.SimpleNamespace()}, 'plan': {'runner': {'sha256': b.sha(env.runner), 'path': '/var/lib/c3po/elsewhere/k9_runner.py'}, 'parent': []},
           'inputs': {'runner': env.runner}, 'entries': [{'role': 'PRECHECK', 'operation': b.PRECHECK_OPERATION}], 'receipts': {'PRECHECK': env.precheck},
           'evidence_facts': [{'role': 'PRECHECK', 'complete': True}]}
    with refused('K4E0_RUNNER_PATH_NOT_CONTENT_ADDRESSED'):
        b.k4e0_rules(ctx)
    # (two cited prechecks are refused before the rule, by PLAN_SOURCES; a precheck that is not complete, by the rule)
    with refused('K4E0_EVIDENCE_NOT_ONE_COMPLETE_PRECHECK'):
        b.k4e0_rules(dict(ctx, evidence_facts=[{'role': 'PRECHECK', 'complete': False}]))
    with refused('K4E0_EVIDENCE_NOT_ONE_COMPLETE_PRECHECK'):
        b.k4e0_rules(dict(ctx, entries=[]))


def k3k9_ctx(env, tree=None, plan_changes=None, copied=None, receipts=None, start=datetime(2026, 10, 5, 20, 50, tzinfo=UTC), facts=None):
    tree = tree or env.tree
    volume = [{'path': '/', 'device': 1, 'inode': 2, 'uid': 0, 'gid': 0, 'mode': 0o755}, {'path': '/mnt', 'device': 1, 'inode': 3, 'uid': 0, 'gid': 0, 'mode': 0o755},
              {'path': '/mnt/day-d-data', 'device': 811, 'inode': 2, 'uid': 1000, 'gid': 1000, 'mode': 0o755}]          # synthetic: copied ($from) in K3-K9's plan
    plan = {'secrets_chain': tree['items']['directory:SECRETS']['observed_rows'], 'data_volume_chain': volume,
            'source_rows': [{'path': '/mnt/day-d-data/x'}], 'worker_container_id': 'a' * 64, 'evidence_boot_id_sha256': tree['boot_id_sha256']}
    plan.update(plan_changes or {})
    receipts = receipts if receipts is not None else {'E0': (E0, env.e0), 'POST': (b.EPOCH_READBACK_OPERATION, env.post), 'TREE': (K9R, tree)}
    policy={'operation':K9R,'mode':'POLICY','boot_id_sha256':tree['boot_id_sha256'],'findings':[],
            'effects':{'mode':'POLICY','evidence_boot_id_sha256':tree['boot_id_sha256']},
            'items':{'worker':{'status':'COMPLETE','running':True,'state':'running','image_id_equal_signed':True,'container_id':'a'*64},'boot':{'status':'COMPLETE','equal_to_the_evidence':True}},
            'clock':{'utc_start':(start-timedelta(seconds=40)).isoformat(),'utc_end':(start-timedelta(seconds=20)).isoformat()}}
    tree=json.loads(json.dumps(tree));tree['clock']={'utc_end':(start-timedelta(seconds=50)).isoformat()}
    if 'TREE' in receipts:receipts['TREE']=(K9R,tree)
    receipts=dict(receipts,POLICY=(K9R,policy))
    if copied is not None:copied=list(copied)+[{'plan_pointer':'/evidence_boot_id_sha256','evidence_role':'POLICY','receipt_pointer':'/boot_id_sha256'}]
    end = start + timedelta(minutes=6) - SEC
    return {'operation': b.K3K9_OPERATION, 'plan': plan, 'params': {}, 'window': {'start': start, 'end': end, 'gate_start': start, 'gate_end': end},
            'watchdog': 80, 'entries': [{'role': role, 'operation': op} for role, (op, _) in receipts.items()],
            'receipts': {role: receipt for role, (_, receipt) in receipts.items()},
            'evidence_facts': facts or [{'role': role, 'complete': receipt.get('outcome') not in ('OBSERVED_ALL_EXPECTATIONS_NOT_MET',)} for role, (_, receipt) in receipts.items()],
            'copied': copied if copied is not None else [{'plan_pointer': '/source_rows', 'evidence_role': 'TREE', 'receipt_pointer': '/items/sources'},
                                                         {'plan_pointer': '/data_volume_chain', 'evidence_role': 'TREE', 'receipt_pointer': '/items/volume'},
                                                         {'plan_pointer': '/worker_container_id', 'evidence_role': 'POLICY', 'receipt_pointer': '/items/worker/container_id'},
                                                         {'plan_pointer':'/evidence_boot_id_sha256','evidence_role':'POLICY','receipt_pointer':'/boot_id_sha256'}]}


def test_k3k9_plug_rules(k9env):
    """K3-K9 is being revised (its plan reads the September rows from the TREE read): its rules run on synthetic contexts."""
    env = k9env
    assert env.post['effects']['evidence_boot_id_sha256'] == env.e0['effects']['evidence_boot_id_sha256'] == env.tree['boot_id_sha256']
    rules = b.k3k9_rules(k3k9_ctx(env))['k9_prerequisite']
    assert rules['program'] == 'K3K9' and rules['tree_complete'] is True
    # a TREE read taken before the secrets exist: its only findings are the absent secret files
    early = json.loads(json.dumps(env.tree))
    early.update(outcome='OBSERVED_ALL_EXPECTATIONS_NOT_MET', findings=['SECRET_FILE_ABSENT'])
    assert b.k3k9_rules(k3k9_ctx(env, tree=early))['k9_prerequisite']['tree_complete'] is False
    other = dict(early, findings=['SECRET_FILE_ABSENT', 'DISK_FREE_BELOW_FLOOR'])
    with refused('K3K9_TREE_READ_NOT_ACCEPTABLE'):
        b.k3k9_rules(k3k9_ctx(env, tree=other))
    with refused('K3K9_EVIDENCE_NOT_E0_POST_AND_TREE'):
        b.k3k9_rules(k3k9_ctx(env, receipts={'E0': (E0, env.e0), 'TREE': (K9R, env.tree)}))
    with refused('K3K9_EVIDENCE_NOT_COMPLETE'):
        b.k3k9_rules(k3k9_ctx(env, receipts={'E0': (E0, env.e0), 'POST': (b.EPOCH_READBACK_OPERATION, dict(env.post, mode='PRE')), 'TREE': (K9R, env.tree)}))
    with refused('EVIDENCE_NOT_OF_THE_SAME_BOOT'):
        b.k3k9_rules(k3k9_ctx(env, plan_changes={'evidence_boot_id_sha256': 'd' * 64}))
    with refused('PLAN_VALUE_NOT_THE_ONE_OF_THE_CITED_RECEIPT'):
        b.k3k9_rules(k3k9_ctx(env, plan_changes={'data_volume_chain': env.tree['items']['directory:SOURCE_ROOT']['observed_rows']}))          # does not end at the volume
    with refused('K3K9_SOURCE_ROWS_NOT_COPIED_FROM_THE_TREE_READ'):
        b.k3k9_rules(k3k9_ctx(env, copied=[{'plan_pointer': '/data_volume_chain', 'evidence_role': 'TREE'}, {'plan_pointer': '/worker_container_id', 'evidence_role': 'POST'}]))
    with refused('POLICY_IDENTITY_NOT_EXACT_COPIES'):
        b.k3k9_rules(k3k9_ctx(env, copied=[{'plan_pointer': '/source_rows', 'evidence_role': 'TREE'}, {'plan_pointer': '/data_volume_chain', 'evidence_role': 'TREE'},
                                           {'plan_pointer': '/worker_container_id', 'evidence_role': 'TREE'}]))
    with refused('K3K9_SOURCE_ROWS_NOT_COPIED_FROM_THE_TREE_READ'):          # the data volume chain typed
        b.k3k9_rules(k3k9_ctx(env, copied=[{'plan_pointer': '/source_rows', 'evidence_role': 'TREE'},
                                           {'plan_pointer': '/worker_container_id', 'evidence_role': 'POST'}]))
    with refused('K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND'):
        b.k3k9_rules(k3k9_ctx(env, start=datetime(2026, 10, 9, 20, 50, tzinfo=UTC)))
    with refused('K9_SENDABLE_SECONDS_BELOW_180'):
        b.k3k9_rules(k3k9_ctx(env, start=datetime(2026, 10, 5, 21, 4, tzinfo=UTC)))          # 18:04-18:09:59 BRT: only :08:00-:08:39 sendable


@pytest.mark.parametrize('bad_clock', [{'utc_end': '2026-10-05T20:49:30+00:00'}, {}, {'utc_end': '2026-10-05T20:49:00'}])
def test_k3k9_policy_identity_must_follow_tree(k9env, bad_clock):
    ctx = k3k9_ctx(k9env)
    ctx['receipts']['TREE']['clock'] = bad_clock
    with refused('POLICY_IDENTITY_NOT_AFTER_TREE'):
        b.k3k9_rules(ctx)



# ================================================================ rev 4c: K9W sealed (165330a6...), bound end to end
def k9w_params(env, operation, label, slot='PRIMARY', grid='G18', day=DAY, **changes):
    phase = b.k9_operation_list()[operation][0]
    row, entry = grid_row(grid, day, operation, slot)
    plan = {'mode': row['mode'], 'epoch': b.K9_EPOCH, 'day': day, 'k9_phase': phase, 'k9_operation': operation, 'slot': slot,
            'attempt_key': actb03_attempt_key(b.K9_EPOCH, day, phase, operation),
            'run_not_after': b.parse_utc(row['run_not_after']).isoformat() if row['mode'] == 'LAUNCH' else None,
            'constants': frm('TREE', '/effects/constants'),
            'parent_rows': {name: {'path': env.k9.PLACEMENT[name], 'rows': frm('TREE', '/items/directory:%s/observed_rows' % key),
                                   'open_root': env.k9.open_root(name)} for name, key in CHAINS.items()},
            'evidence_boot_id_sha256': frm('TREE', '/boot_id_sha256'), 'bind': None}
    if operation == 'bind':
        _, raw, cutoff, windows = b.k9_risk_order(entry, day, 'R2D2-V2-DIAG-R4-' + day)
        plan['bind'] = {'namespace': 'R2D2-V2-DIAG-R4-' + day, 'cutoff_at': cutoff, 'phase_windows': windows,
                        'owner_order_text': raw.decode('ascii'), 'owner_order_sha256': b.sha(raw)}
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': K9W, 'label': label, 'signature_model': 'PRE', 'not_before': row['not_before'],
             'not_after': row['not_after'], 'plan': plan, 'evidence': [x.cite('TREE', K9R, env.files['tree'], env.k9r_dir)], 'review': env.review,
             'k9_grid': grid}
    value.update(changes)
    return value


def test_the_binders_k9w_block_is_the_sealed_k9w(k9env):
    m = k9env.k9w_m
    assert m.OPERATION == K9W and m.K9W_STEP_TABLE_SHA256 == b.K9_STEP_TABLE_SHA256 == b.K9W_STEP_TABLE_SHA256
    assert sorted(m.PLAN_KEYS) == sorted(set(b.K9W_PLUG['members'].values()) | {'bind'})
    assert tuple(m.K9W_MODES) == b.K9W_PLUG['modes'] and m.K9W_RISK_NAMESPACE in b.K9W_PLUG['risk_namespace_prefixes']
    assert {name: step['ceiling_seconds'] for name, step in m.K9W_STEPS.items() if step['mode'] == 'LAUNCH' and name != 'capture_launch'} == b.K9W_PLUG['ceiling_seconds']
    assert {name: step['latest_run_not_after_utc_of_d'] for name, step in m.K9W_STEPS.items() if step['latest_run_not_after_utc_of_d']} == b.K9W_PLUG['latest_run_not_after']
    assert sorted(name for name, step in m.K9W_STEPS.items() if step['window_class'] == 'IN_SESSION') == sorted(b.K9W_PLUG['in_session_operations'])
    assert m.K9W_CAPTURE_RUN_NOT_AFTER == b.K9W_PLUG['cleanup_starts_after'][1]
    assert m.K9W_MIN_TIMEOUT_SECONDS + m.K9W_LAUNCH_MARGIN_SECONDS + m.MAX_SECONDS == b.K9W_PLUG['seconds_left_at_the_latest_start']
    assert all(m.K9W_PLACEMENT[key] == value for key, value in b.K9_PLACEMENT_PATHS.items()) and m.K9W_DISK_FLOOR_BYTES == b.K9_DISK_FLOOR_BYTES
    grid = b.k9_grid()
    for name in b.K9_GRIDS:
        for entry in grid[name]:
            _, raw, cutoff, _ = b.k9_risk_order(entry, entry['day'], m.K9W_RISK_NAMESPACE + entry['day'])
            assert raw == m.k9w_owner_order(entry['day'], cutoff)          # the binder's order bytes are K9W's own construction
            for row in entry['rows']:
                if row['mode'] == 'LAUNCH' and row['operation'] != 'capture_launch':
                    assert row['ceiling_seconds'] == m.K9W_STEPS[row['operation']]['ceiling_seconds']


@pytest.mark.parametrize('operation', ['collect_launch', 'bind', 'capture_cleanup'])
def test_a_k9w_step_binds_end_to_end_from_the_tree_receipt(k9env, base, operation):
    """The sealed K9W: prepare, sign and check, its plan copied from a synthetic TREE receipt (produced by K9R on its emulated
    host); the K9W source's own authenticate and dispatcher accept the bound bytes (prepare's proofs)."""
    env = k9env
    now = EVE_NOW if operation != 'capture_cleanup' else datetime(2026, 10, 6, 11, 0, tzinfo=UTC)
    out = Path(base) / ('rehearsal-k9w-' + operation.replace('_', '-'))
    prepared = b.prepare(env.k9w_dir, K9W, params(env, base, k9w_params(env, operation, 'k9w-' + operation.replace('_', '-'))), env.reference, out,
                         b.REHEARSAL, now=lambda: now)
    b.sign(out, prepared['prepare_json_sha256'], b.zulu(now), b.REHEARSAL_ANSWER, now=lambda: now)
    sheet = prepared['sheet']
    k9 = sheet['hostops02']['rules']['k9']
    row, _ = grid_row('G18', DAY, operation)
    assert k9['program'] == 'K9W' and k9['operation'] == operation and (k9['window_not_before'], k9['window_not_after']) == (row['not_before'], row['not_after'])
    assert sheet['writes_allowed'] is True and sheet['hostops02']['dispatch_gates'] == ['CODEX_REVIEW_OF_THE_BOUND_SET']
    assert sheet['family']['sha256sums_sha256'] == K9W_SEAL and sheet['success_criterion'] == env.k9w_m.K9W_SUCCESS[row['mode']]
    question = prepared['owner_question_pt']
    assert ('PEDIDO DE ASSINATURA - K9 %s' % operation) in question and 'sessão 2026-10-06, vaga PRIMÁRIA, grade G18' in question
    assert 'Preciso da sua assinatura para UMA execução' in question and 'o K9W cria no servidor' in question
    if operation == 'bind':
        assert k9['risk_order']['owner_order_sha256'] in question and k9['risk_order']['cutoff_at'] == '2026-10-06T02:26:00+00:00'
    if operation == 'collect_launch':
        assert 'docker create' in question and '/var/lib/c3po/r2d2-v2-k9-20261005/days/2026-10-06' in question
    checked = b.check(out, env.k9w_dir, now=lambda: now)
    assert checked['documents_are_the_deterministic_construction'] is True and checked['verdict'] == 'VALID_BUT_DISPATCH_GATES_NOT_MET'
    gates = h.write_json(Path(base) / 'GATES-k9w.json', {'schema': b.GATES_SCHEMA, 'codex_review': {'document_file': env.review['document_file'],
                                                                                                   'form': 'CANDIDATE_REVIEW_SUFFICES'}})
    checked = b.check(out, env.k9w_dir, gates, now=lambda: now)
    assert checked['verdict'] == 'VALID_WINDOW_NOT_YET_OPEN' and checked['dispatch_gates']['failed'] == []


def test_k9w_end_to_end_refusals(k9env, base):
    env = k9env

    def attempt_k9w(code, value, now=EVE_NOW):
        out = Path(base) / ('rehearsal-k9w-attempt-%d' % env.COUNT[0])
        with refused(code):
            b.prepare(env.k9w_dir, K9W, params(env, base, value), env.reference, out, b.REHEARSAL, now=lambda: now)
        assert not out.exists()
    attempt_k9w('K9_WINDOW_NOT_THE_GRIDS', k9w_params(env, 'preflight', 'preflight-shifted', not_before='2026-10-06T02:39:00Z', not_after='2026-10-06T02:44:59Z'))
    value = k9w_params(env, 'commit_launch', 'commit-ceiling')
    attempt_k9w('K9_RUN_NOT_AFTER_NOT_THE_GRIDS', dict(value, plan=dict(value['plan'], run_not_after='2026-10-05T22:08:59+00:00')))
    value = k9w_params(env, 'bind', 'bind-shadow')
    value['plan']['bind'] = dict(value['plan']['bind'])
    attempt_k9w('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER', dict(value, plan=dict(value['plan'], bind={'namespace': 'x'})))
    shadow = dict(value['plan']['bind'], namespace='R2D2-V2-SHADOW-' + DAY)          # the sealed K9W refuses it itself
    attempt_k9w('FAMILY_REFUSES_THE_REQUEST_BIND_NAMESPACE_NOT_THE_COMPILED_ONE', dict(value, plan=dict(value['plan'], bind=shadow)))
    attempt_k9w('K9_SPARE_WITHOUT_ITS_PRIMARY', k9w_params(env, 'collect_launch', 'collect-s', slot='SPARE'))



# ================================================================ rev 4d: Codex decision 6 (the source root under the root-only chain)
def test_decision_6_the_placement_refuses_n8_bytes_and_requires_root_control(k9env, base):
    """The binder's placement (decision 6): K9R rev 4, K9W rev 2 and K4-E0 rev 4 bind with it (the other tests); constants that
    carry N-8's source root are refused; the bytes sealed under N-8 (K4-E0 revision 2, 394f1b27...) are refused; a chain of the
    K9 tree (the source root's included) with an open root, or a row of another group, is refused."""
    env = k9env
    assert env.constants['placement']['source_root'] == DECISION_6['source_root'] == '/var/lib/c3po/r2d2-v2-source-20261005'
    n8 = dict(env.constants, placement=dict(env.constants['placement'], source_root='/mnt/day-d-data/r2d2-v2-source-20261005'))
    # K9R rev 4 refuses them itself (its compiled placement); the binder's own refusal is test_the_compiled_runner_...'s
    attempt(env, base, 'FAMILY_REFUSES_THE_REQUEST_PLACEMENT_NOT_THE_COMPILED_ONE', tree_params(env, plan=dict(env.k9.tree_fields(constant=env.constants), constants=n8)))
    old_e0 = INPUTS / 'k4_e0.snapshot-394f1b27'
    if old_e0.is_dir():
        directory = env.root / 'tier-n8' / 'k4_e0'
        directory.parent.mkdir()
        shutil.copytree(str(env.copy / 'core'), str(directory.parent / 'core'))
        shutil.copytree(str(old_e0), str(directory), ignore=shutil.ignore_patterns('__pycache__', 'work'))
        seal = b.sha((directory / 'SHA256SUMS').read_bytes())
        original = b.binder_identity
        try:
            b.binder_identity = lambda: (original()[0], original()[1] + [dict(env.extra[0], family='HOSTOPS02_K4_E0', revision='2', sha256sums_sha256=seal)])
            out = Path(base) / 'rehearsal-e0-n8'
            review = env.work / 'REVIEW_RECORD.K4E0-rev2.synthetic.txt'
            review.write_text('SYNTHETIC, not a review: K4-E0 revision 2 seal %s source %s\n' % (seal, b.sha((directory / 'build' / 'k4_e0.py').read_bytes())))
            value = e0_params(env, review={'kind': 'CODEX_REVIEWED', 'document_file': str(review)})
            value['plan'] = {'source_parent': frm('PRECHECK', '/items/chains/DATA_VOLUME/rows'), 'k9_parent': frm('PRECHECK', '/items/chains/VAR_LIB/rows'),
                             'runner': value['plan']['runner'], 'evidence_boot_id_sha256': value['plan']['evidence_boot_id_sha256']}
            with refused('EFFECTS_NOT_LISTABLE_FOR_THE_OWNER'):          # its plan (source_parent, k9_parent) is not revision 4's
                b.prepare(directory, E0, params(env, base, value), env.reference, out, b.REHEARSAL, now=lambda: EVE_NOW)
            assert not out.exists()
        finally:
            b.binder_identity = original
    with refused('K9_PROGRAM_NOT_OF_THIS_PLACEMENT'):          # a K4-E0 whose compiled source root is N-8's
        b.k4e0_rules({'rt': {'source': types.SimpleNamespace(SOURCE_ROOT='/mnt/day-d-data/r2d2-v2-source-20261005')}, 'plan': {}})
    plan, row = k9w_plan(env, 'collect_launch')
    for chain in ('source_root', 'days'):
        rows = json.loads(json.dumps(plan['parent_rows']))
        rows[chain]['open_root'] = '/var/lib'
        with refused('K9_CHAIN_NOT_ROOT_CONTROLLED'):
            b.k9_rules(unit_ctx(env, K9W, dict(plan, parent_rows=rows), row))
    tree = json.loads(json.dumps(env.tree))
    tree['items']['directory:SOURCE_ROOT']['observed_rows'][-1]['gid'] = 1000
    rows = json.loads(json.dumps(plan['parent_rows']))
    rows['source_root']['rows'] = tree['items']['directory:SOURCE_ROOT']['observed_rows']
    with refused('K9_CHAIN_NOT_ROOT_CONTROLLED'):
        b.k9_rules(unit_ctx(env, K9W, dict(plan, parent_rows=rows), row, receipts={'TREE': (K9R, tree)}))


DECISION_6 = dict(b.K9_PLACEMENT_PATHS)          # the compiled values, read at import (before any test patches them)
