"""Shared helpers of the bind_once tests. Everything is synthetic: no owner, no key, no host."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
BIND = HERE.parent
SCRATCH = BIND.parent
sys.path.insert(0, str(BIND))
sys.path.insert(0, str(HERE))
import bind_once as b          # noqa: E402

W1_SOURCE = Path(os.environ.get('BIND_TEST_W1', str(SCRATCH / 'w1preflight' / 'candidate')))
HOSTOPS_SOURCE = Path(os.environ.get('BIND_TEST_HOSTOPS', str(SCRATCH / 'hostops01' / 'candidate')))
NOW = datetime(2026, 10, 3, 13, tzinfo=timezone.utc)          # Saturday 03/10 10:00 BRT; inside every date set; the W1 fixtures' own instant
HOSTOPS_NOW = datetime(2026, 10, 3, 17, tzinfo=timezone.utc)   # the instant of the HOSTOPS01 fixtures
W1 = 'GO_READONLY_W1PREFLIGHT_01'
PRECHECK = 'GO_READONLY_HOSTOPS_PRECHECK_01'
PROVISION = 'GO_WRITE_SUPERVISOR_READER_PROVISION_01'
SYNTHETIC_TARGET = 'operator@bind-once-tests.example.net'       # a "real-looking" target that exists nowhere; never dispatched
DROP = object()
COVERED = set()
PRECHECK_PLAN = {
    'groups': ['SUPERVISOR', 'JOURNAL_LEAF', 'READER', 'CAPACITY'], 'journal_placement': 'A', 'data_volume_path': '/mnt/day-d-data',
    'journal_leaf': 'journal', 'existing_journal_leaves': [],
    'capacity': {'root_path': '/mnt/day-d-data/c3po-capacity', 'receipt_directory_path': '/var/lib/c3po-reader/capacity-receipts'},
    'unit_names': ['c3po-massive.service', 'c3po-massive.timer'], 'image_reference': 'c3po/backend:production'}


@contextmanager
def refused(code):
    """The call must be refused with exactly this constant code; the code is recorded for the coverage test."""
    with pytest.raises(b.Refused) as caught:
        yield
    assert str(caught.value) == code, 'refused with %s, expected %s' % (caught.value, code)
    COVERED.add(code)


def resolved(path):
    return Path(str(path)).resolve()


def copy_family(source, destination):
    shutil.copytree(str(source), str(destination), ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    return destination


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
    return Path(path)


def apply(value, changes):
    value = dict(value)
    for key, item in changes.items():
        if item is DROP:
            value.pop(key, None)
        else:
            value[key] = item
    return value


def w1_parameters(base, name='PARAMETERS.json', **changes):
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': W1, 'label': 'attempt', 'signature_model': 'IND', 'not_before': b.zulu(NOW),
             'not_after': b.zulu(NOW + timedelta(minutes=5)), 'candidates': {'release_directories': [], 'capacity_roots': []}}
    return write_json(base / name, apply(value, changes))


def precheck_parameters(base, name='PARAMETERS.json', **changes):
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': PRECHECK, 'label': 'precheck', 'signature_model': 'IND', 'not_before': b.zulu(NOW),
             'not_after': b.zulu(NOW + timedelta(minutes=50)), 'plan': json.loads(json.dumps(PRECHECK_PLAN)), 'evidence': []}
    return write_json(base / name, apply(value, changes))


def rehearsal_reference(base, name='rehearsal-transport'):
    return Path(b.rehearsal_reference(base / name)['reference'])


def runtime_of(family, operation):
    selected = b.select_operation(b.verify_family(family), operation)
    return b.load_runtime(selected['files'], selected['source_name'], selected['directory'])


def executed_reference(base, family, name='executed', **changes):
    """A synthetic stand-in for an executed bound set: real-looking target, files that are not keys, and the exit.json of one
    successful attempt of exactly this configuration. Used to exercise REAL mode without any value of the real host."""
    directory = base / name
    directory.mkdir(mode=0o700)
    files = {}
    for key, content in (('ssh_key', b'SYNTHETIC_TEST_FILE_NOT_A_KEY\n'), ('known_hosts', b'SYNTHETIC_TEST_FILE_NOT_KNOWN_HOSTS\n')):
        path = directory / key
        path.write_bytes(content)
        path.chmod(0o600)
        files[key] = {'path': str(path), 'sha256': b.sha(content)}
    attempt = directory / '.dispatch-root' / 'executed-once'
    attempt.mkdir(parents=True, mode=0o700)
    config = {'schema': 'SYNTHETICTEST_DISPATCH_AUTHORIZATION_V1', 'status': 'BOUND', 'decision': 'GO', 'operation': 'GO_SYNTHETIC_EXECUTED_01',
              'target': changes.pop('another_target', SYNTHETIC_TARGET),          # another synthetic host, consistently bound (unlike target=, applied after the bindings)
              'remote_command': b.REMOTE_COMMAND, 'ssh_key': files['ssh_key'], 'known_hosts': files['known_hosts'],
              'attempt_directory': str(attempt)}
    config['host_binding_sha256'] = b.host_binding(config['target'], files['known_hosts']['sha256'])
    rt = runtime_of(family, W1)
    config['command_sha256'] = rt['transport'].command_pin(rt['dispatch'].command(config))
    exit_changes = changes.pop('exit', {})
    skip_exit = changes.pop('skip_exit', False)
    config = apply(config, changes)
    raw = b.pretty(config)
    (directory / 'DISPATCH.BOUND.json').write_bytes(raw)
    (directory / 'DISPATCH.BOUND.json').chmod(0o600)
    time.sleep(0.02)                               # the last use is later than the creation of the two files
    result = apply({'config_sha256': b.sha(raw), 'status': 'KNOWN_COMPLETE', 'command_sha256': config.get('command_sha256'), 'attempts': 1,
                    'stderr_sha256': b.EMPTY_SHA256, 'finished_at': '2026-10-02T14:59:14.187876+00:00'}, exit_changes)
    for leaf, content in (('spawn.claim', b'{}'), ('exit.json', b.canonical(result))):
        if leaf == 'exit.json' and skip_exit:
            continue
        (attempt / leaf).write_bytes(content)
        (attempt / leaf).chmod(0o600)
    return directory / 'DISPATCH.BOUND.json'


def bind(base, family, operation, parameters, reference, mode=b.REHEARSAL, name=None, now=NOW, signed_at=None):
    out = base / (name or ('rehearsal-bound' if mode == b.REHEARSAL else 'bound'))
    prepared = b.prepare(family, operation, parameters, reference, out, mode, now=lambda: now)
    signed = b.sign(out, prepared['prepare_json_sha256'], signed_at or b.zulu(now), answer_of(mode), now=lambda: now)
    return out, prepared, signed


def answer_of(mode):
    """What sign accepts as the verbatim answer: the owner's word in a REAL set (here always a synthetic one, bound to a
    synthetic executed reference), and the rehearsal marker in a REHEARSAL set."""
    return b.REAL_ANSWER if mode == b.REAL else b.REHEARSAL_ANSWER


REHEARSAL_HOST = b.host_binding(b.REHEARSAL_TARGET, b.sha(b.REHEARSAL_HOSTS))


def resealed(receipt, change=None, host=REHEARSAL_HOST):
    """A receipt of the family's fixtures (bound there to the synthetic host 1111...), bound to another host binding and
    sealed again; `change` edits the body first. What the launcher would write: one canonical line."""
    value = json.loads(json.dumps(receipt))
    value.pop('metadata_sha256')
    if host is not None:
        value['host_binding_sha256'] = host
    if change:
        change(value)
    value['metadata_sha256'] = b.sha(b.canonical(value))
    return value


def receipt_file(path, receipt):
    Path(path).write_bytes(b.canonical(receipt) + b'\n')
    Path(path).chmod(0o600)
    return Path(path)


def review_record(base, kind='CODEX_REVIEWED', name='REVIEW_RECORD.synthetic.txt'):
    """The review-or-waiver member of a write request, with a synthetic document: no review and no waiver happened here."""
    path = Path(base) / name
    if not path.exists():
        path.write_text('SYNTHETIC TEST DOCUMENT: stands for the record of the review, or of the waiver, of a write. Not a review.\n')
    return {'kind': kind, 'document_file': str(path)}


def never(*args, **kwargs):
    raise AssertionError('transport must not run')


def dispatcher_prepare(bound, clock):
    """The family's dispatcher from the bound directory, phase prepare, with an injected clock and no transport."""
    state = b.signed_state(bound)
    return state['rt']['dispatch'].execute(str(Path(bound) / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='prepare',
                                           clock=lambda: clock, monotonic=lambda: 0.0, transport=never)


def dispatcher_resume(bound, proof, clock, transport):
    state = b.signed_state(bound)
    return state['rt']['dispatch'].execute(str(Path(bound) / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume',
                                           publication_path=proof['publication_proof_path'], publication_sha256=proof['publication_proof_sha256'],
                                           clock=lambda: clock, monotonic=lambda: 0.0, transport=transport)


def prepared_and_published(bound, comment_id=b.REHEARSAL_PUBLICATION, at=NOW):
    intent = dispatcher_prepare(bound, at + timedelta(seconds=1))
    assert intent['status'] == 'AWAITING_PUBLICATION_NO_SPAWN'
    proof = b.publish_proof(bound, comment_id, b.zulu(at + timedelta(seconds=2)), now=lambda: at + timedelta(seconds=3))
    assert proof['intent_sha256'] == intent['intent_sha256']
    return intent, proof


def fixed_transport(result, out, err=b''):
    def run(payload, **kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'], kwargs['command_sha256']) is True
        return dict(result), out, err
    return run


def finish(bound, transport, comment_id=b.REHEARSAL_PUBLICATION, at=NOW):
    intent, proof = prepared_and_published(bound, comment_id, at)
    return dispatcher_resume(bound, proof, at + timedelta(seconds=4), transport)


def rewrite_sums(bound):
    """After a deliberate edit of a signed set: SHA256SUMS made consistent again, so that the next check is the one under test."""
    bound = Path(bound)
    sums = {}
    for path in sorted(bound.rglob('*')):
        relative = path.relative_to(bound)
        if relative.parts[0] != b.CLAIM_ROOT and not path.is_dir() and relative.name != 'SHA256SUMS' and not b.re.fullmatch(b.PROOF_NAME, relative.name):
            sums[str(relative)] = b.sha(path.read_bytes())
    (bound / 'SHA256SUMS').write_bytes(''.join('%s  %s\n' % (sums[name], name) for name in sorted(sums)).encode())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def w1_receipt_line(harness, bound, world=None, clock=None, changes=None):
    """The W1 source on the emulated host of the candidate's own test file, target uid injected: the line the launcher would write."""
    p = harness.p
    state = b.signed_state(bound)
    raws, source = state['raws'], state['rt']['source_bytes']
    pins = p.Pins(payload=p.sha(source), request=p.sha(raws[0]), authority=p.sha(raws[1]), go=p.sha(raws[2]))
    host = world if world is not None else harness.world()
    receipt = p.observe(raws[0], raws[1], raws[2], pins=pins, payload_bytes=source, clock=lambda: clock or NOW + timedelta(seconds=4),
                        monotonic=lambda: 0, executor_uid=lambda: 0, collector=lambda request, gate: p.collect(request, gate, host=host))
    if changes:
        receipt.pop('metadata_sha256')
        receipt.update(changes)
        receipt['metadata_sha256'] = p.sha(p.canonical(receipt))
    return harness.line(receipt), receipt
