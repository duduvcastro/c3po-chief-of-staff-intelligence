#!/usr/bin/env python3
"""rehearse.py - full rehearsal of bind_once.py on scratch copies, with a fake transport. Never contacts a host.

  rehearse.py w1        --family DIR --workspace DIR [--real-reference FILE]
  rehearse.py precheck  --family DIR --workspace DIR [--real-reference FILE]

The workspace must not exist and its name must start with "rehearsal-". Everything is created below it:
  family-copy/          a scratch copy of the sealed family (its SHA256SUMS is verified by the binder)
  rehearsal-transport/  the fake transport reference (target in the reserved .invalid domain, marker files, no key)
  rehearsal-bound/      the bound set, mode REHEARSAL
  PARAMETERS.json, TRANSCRIPT.json, REHEARSAL_MARKER.txt

Steps: prepare -> sign with a synthetic time and the rehearsal marker as answer (no owner is asked; the owner's word is
refused) -> check -> the family's dispatcher, phase prepare, through its real command line with a fresh, empty pycache
prefix (exit 2 and AWAITING_PUBLICATION_NO_SPAWN) -> check again (VALID_ALREADY_PREPARED, exit 1) -> publish-proof -> status.
For w1 only, resume follows, in a child process of this script: the family's dispatcher with its transport REPLACED by the
family's own local test harness (the source on the emulated host of test_w1_preflight_once.py, the receipt passed through
the reviewed transport bytes with a local echo child). The ssh command of the configuration is never started; the resume
child refuses any set that is not a REHEARSAL set with the fake target. A last check then says VALID_GO_SPENT.
--real-reference, when given, is only used to show that the binder refuses it for a rehearsal (nothing is created).

  rehearse.py hostops02-catalog|hostops02-readback|hostops02-release|hostops02-activate
              --hostops02 DIR [--hostops02 DIR ...] --hostops01 DIR --w1 DIR --workspace DIR

HOSTOPS02 (K2a, K11, K10, K6a). These operations are dated 2026-10-02..2026-10-05 and their requests cite receipts of
other families: the flow runs IN THIS PROCESS, through the binder's own functions and each family's dispatcher, with
INJECTED clocks at the instants of the weekend plan (MASTER_PLAN 2.2, 2.3, 2.5), and only `check` and `status` are also run
through the binder's command line (real clock). Below the workspace: hostops02/ (bind_once.py sealed-copy of the core and
the four operation directories from the --hostops02 roots, in order: a file edited after its seal is taken, by its sealed
hash, from a later root), family copies of HOSTOPS01 and W1, the rehearsal transport, the cited receipts (produced by the
cited operations' own sealed sources on their families' emulated hosts and bound to the rehearsal host: tests/
hostops02_fixtures.py), the input files, the bound sets (rehearsal-*), the gates files, TRANSCRIPT.json. Each set goes
prepare -> sign (rehearsal marker) -> check -> the family's dispatcher prepare -> publish-proof -> resume, the source run on
its own emulated host and its line passed through the reviewed transport bytes with a local echo child -> status.
  catalog   A6 (mode REHEARSAL), then A9 (mode REAL of the operation, the same bytes) gated on A6's receipt and a W1 grid read
  readback  M2p (PRE FULL), then M2 (POST) citing M2p's set, gated on an install receipt
  release   M1 and its spare M1' (Sunday gate on a W1 read at prepare; Monday gate on M0 at check; the spare refused once M1's
            dispatcher prepare made its claim; the resume gate)
  activate  M3 and its spare M3', citing the full PRE, gated on the POST readback
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
BINDER = HERE / 'bind_once.py'
PYTHON = '/usr/bin/python3'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': tempfile.gettempdir()}
ANSWER = 'REHEARSAL_NO_OWNER_ANSWER'          # what sign accepts on a rehearsal set; "Assino" is refused there
W1 = 'GO_READONLY_W1PREFLIGHT_01'
PRECHECK = 'GO_READONLY_HOSTOPS_PRECHECK_01'
PRECHECK_PLAN = {        # synthetic values, the ones of the family's own fixtures (placement A); nothing here was read on a host
    'groups': ['SUPERVISOR', 'JOURNAL_LEAF', 'READER', 'CAPACITY'], 'journal_placement': 'A', 'data_volume_path': '/mnt/day-d-data',
    'journal_leaf': 'journal', 'existing_journal_leaves': [],
    'capacity': {'root_path': '/mnt/day-d-data/c3po-capacity', 'receipt_directory_path': '/var/lib/c3po-reader/capacity-receipts'},
    'unit_names': ['c3po-massive.service', 'c3po-massive.timer'], 'image_reference': 'c3po/backend:production'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def zulu(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


class Transcript:
    def __init__(self, path):
        self.path, self.steps = path, []

    def run(self, name, argv, expect_exit, expect_status=None):
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, timeout=300)
        try:
            answer = json.loads(done.stdout)
        except ValueError:
            answer = {'unparsed_stdout_bytes': len(done.stdout)}
        if type(answer) is dict:
            answer.pop('owner_question_pt', None)
        step = {'step': name, 'argv': argv, 'exit': done.returncode, 'stderr_bytes': len(done.stderr), 'stdout': answer,
                'at_utc': zulu(datetime.now(timezone.utc))}
        self.steps.append(step)
        self.save()
        ok = done.returncode == expect_exit and done.stderr == b'' and (expect_status is None or answer.get('status') == expect_status)
        print('%-44s exit=%d %s%s' % (name, done.returncode, answer.get('status') or answer.get('verdict') or '',
                                      (' ' + str(answer.get('code'))) if answer.get('code') else ''), flush=True)
        if not ok:
            self.note('REHEARSAL STOPPED: step %s did not end as expected (wanted exit %d, status %s)' % (name, expect_exit, expect_status))
            raise SystemExit(1)
        return answer

    def note(self, text):
        self.steps.append({'note': text})
        self.save()
        print(text, flush=True)

    def save(self):
        self.path.write_text(json.dumps(self.steps, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        os.chmod(str(self.path), 0o600)


def binder(*arguments):
    return [PYTHON, '-B', str(BINDER)] + [str(item) for item in arguments]


def rehearse(kind, family, workspace, real_reference):
    workspace = Path(workspace)
    if not workspace.is_absolute() or not workspace.name.startswith('rehearsal-') or os.path.lexists(str(workspace)):
        raise SystemExit('the workspace must be an absolute path that does not exist and whose name starts with rehearsal-')
    os.umask(0o077)
    workspace.mkdir(mode=0o700)
    workspace = workspace.resolve()
    (workspace / 'REHEARSAL_MARKER.txt').write_text(
        'REHEARSAL ONLY. Nothing below this directory was signed by the owner; the transport is fake (target in the reserved '
        '.invalid domain, marker files instead of a key); no document here can be dispatched to the real host.\n')
    transcript = Transcript(workspace / 'TRANSCRIPT.json')
    copy = workspace / 'family-copy'
    shutil.copytree(str(family), str(copy), ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    transcript.note('scratch copy of the family: %s' % copy)
    operation = W1 if kind == 'w1' else PRECHECK
    label = '%s-rehearsal' % kind
    bound = workspace / 'rehearsal-bound'
    reference = workspace / 'rehearsal-transport' / 'REHEARSAL_TRANSPORT_REFERENCE.json'
    transcript.run('rehearsal-reference', binder('rehearsal-reference', '--out', workspace / 'rehearsal-transport'), 0, 'REHEARSAL_REFERENCE_WRITTEN')

    now = datetime.now(timezone.utc).replace(microsecond=0)
    end = min(now + timedelta(minutes=50), now.replace(hour=23, minute=59, second=59))
    parameters = {'schema': 'BIND_ONCE_PARAMETERS_V1', 'operation': operation, 'label': label, 'signature_model': 'IND', 'not_before': zulu(now), 'not_after': zulu(end),
                  'purpose_pt': 'ENSAIO do binder em cópias de rascunho; nenhum dono é consultado e nenhum servidor é contactado.'}
    if kind == 'w1':
        parameters['candidates'] = {'release_directories': [], 'capacity_roots': []}
    else:
        parameters.update(plan=PRECHECK_PLAN, evidence=[])
    (workspace / 'PARAMETERS.json').write_text(json.dumps(parameters, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')

    # the two crossings that must be refused, before anything is bound
    transcript.run('refusal: real mode, rehearsal transport',
                   binder('prepare', '--family', copy, '--operation', operation, '--params', workspace / 'PARAMETERS.json', '--reference', reference,
                          '--out', workspace / 'would-be-real', '--mode', 'real'), 2, 'REFUSED')
    if real_reference:
        answer = transcript.run('refusal: rehearsal mode, executed (real) transport',
                                binder('prepare', '--family', copy, '--operation', operation, '--params', workspace / 'PARAMETERS.json',
                                       '--reference', real_reference, '--out', workspace / 'rehearsal-with-real-transport', '--mode', 'rehearsal'), 2, 'REFUSED')
        if answer.get('code') != 'REHEARSAL_SET_WITH_REAL_TRANSPORT' or os.path.lexists(str(workspace / 'rehearsal-with-real-transport')):
            raise SystemExit('the binder did not refuse a real transport for a rehearsal as expected')
    if os.path.lexists(str(workspace / 'would-be-real')):
        raise SystemExit('a refused prepare created something')

    prepared = transcript.run('prepare', binder('prepare', '--family', copy, '--operation', operation, '--params', workspace / 'PARAMETERS.json',
                                                '--reference', reference, '--out', bound, '--mode', 'rehearsal'), 0, 'PREPARED_AWAITING_OWNER_SIGNATURE')
    sheet_sha = prepared['prepare_json_sha256']
    at = prepared['sheet']['prepared_at_utc']
    transcript.run('refusal: sign with another sheet hash', binder('sign', '--bound', bound, '--sheet-sha256', 'f' * 64, '--signed-at', at, '--owner-answer', ANSWER),
                   2, 'REFUSED')
    answer = transcript.run("refusal: the owner's word on a rehearsal set", binder('sign', '--bound', bound, '--sheet-sha256', sheet_sha, '--signed-at', at,
                                                                                '--owner-answer', 'Assino'), 2, 'REFUSED')
    if answer.get('code') != 'OWNER_ANSWER_IS_NOT_THE_SIGNATURE' or answer.get('created_by_this_run'):
        raise SystemExit('a rehearsal set took the owner word, or a refused sign wrote something')
    signed = transcript.run('sign (synthetic time, no owner)', binder('sign', '--bound', bound, '--sheet-sha256', sheet_sha, '--signed-at', at, '--owner-answer', ANSWER),
                            0, 'BOUND_NOT_DISPATCHED')
    transcript.run('refusal: sign twice', binder('sign', '--bound', bound, '--sheet-sha256', sheet_sha, '--signed-at', at, '--owner-answer', ANSWER), 2, 'REFUSED')
    checked = transcript.run('check', binder('check', '--bound', bound, '--family', copy), 0, 'CHECKED')
    if checked.get('verdict') != 'VALID_WINDOW_OPEN':
        raise SystemExit('check did not find the window open')
    config_sha = signed['config_sha256']
    # The dispatcher imports its siblings by name: a fresh, empty, private directory as pycache prefix leaves the interpreter no
    # cached bytecode to run in place of the pinned sources (as blocks 6 and 9 of the runbook do).
    prefix = workspace / 'pycache-prefix-must-stay-empty'
    prefix.mkdir(mode=0o700)
    dispatcher = [PYTHON, '-B', '-X', 'pycache_prefix=%s' % prefix, str(bound / 'dispatch_once.py'), '--config', str(bound / 'DISPATCH.BOUND.json'),
                  '--config-sha256', config_sha]
    if signed['prepare_command'][:4] != [PYTHON, '-B', '-X', 'pycache_prefix=<fresh-empty-0700-directory>'] or signed['prepare_command'][4:] != dispatcher[4:] + ['--phase', 'prepare']:
        raise SystemExit('the command the binder prints is not the one run here')
    intent = transcript.run('dispatcher prepare (family CLI)', dispatcher + ['--phase', 'prepare'], 2, 'AWAITING_PUBLICATION_NO_SPAWN')
    transcript.run('refusal: dispatcher prepare twice', dispatcher + ['--phase', 'prepare'], 2, 'REFUSED_OR_UNCERTAIN')
    if list(prefix.iterdir()):
        raise SystemExit('the pycache prefix did not stay empty')
    again = transcript.run('check after the dispatcher prepare', binder('check', '--bound', bound, '--family', copy), 1, 'CHECKED')
    if again.get('verdict') != 'VALID_ALREADY_PREPARED' or again.get('a_new_dispatcher_prepare_would_reach_the_claim_and') != 'BE_REFUSED':
        raise SystemExit('check did not say that the claim exists')
    started = json.loads((bound / '.dispatch-root' / (label + '-once') / 'intent.json').read_bytes())['started_at']
    while datetime.now(timezone.utc).replace(microsecond=0) < datetime.fromisoformat(started):
        time.sleep(0.2)
    created = zulu(datetime.now(timezone.utc))
    transcript.run('refusal: a real comment id on a rehearsal set', binder('publish-proof', '--bound', bound, '--comment-id', '5955151654',
                                                                         '--created-at', created), 2, 'REFUSED')
    proof = transcript.run('publish-proof', binder('publish-proof', '--bound', bound, '--comment-id', 'REHEARSAL-NO-PUBLICATION', '--created-at', created),
                           0, 'PROOF_WRITTEN_NOT_DISPATCHED')
    if proof['intent_sha256'] != intent['intent_sha256']:
        raise SystemExit('the proof does not carry the intent hash the dispatcher printed')
    transcript.run('status before resume', binder('status', '--bound', bound), 1, 'PREPARED_PROOF_WRITTEN_RESUME_NOT_RUN')
    if kind != 'w1':
        transcript.note('STOP before resume, as planned for this family: the rehearsal ends with the claim and intent.json in place.')
        return workspace
    resumed = transcript.run('resume (family harness instead of ssh)',
                             [PYTHON, '-B', '-X', 'pycache_prefix=%s' % prefix, str(Path(__file__).resolve()), 'resume-w1-with-harness', '--bound', str(bound), '--family', str(copy),
                              '--config-sha256', config_sha, '--proof', proof['publication_proof_path'], '--proof-sha256', proof['publication_proof_sha256']],
                             0)
    if resumed.get('status') not in ('KNOWN_COMPLETE', 'KNOWN_PARTIAL') or resumed.get('second_resume') != 'REFUSED_FileExistsError':
        raise SystemExit('the harness resume did not end with a receipt, or a second resume was not refused')
    final = transcript.run('status after resume', binder('status', '--bound', bound), 0, resumed['status'])
    if not final.get('verified'):
        raise SystemExit('status did not verify the receipt')
    spent = transcript.run('check after resume', binder('check', '--bound', bound, '--family', copy), 1, 'CHECKED')
    if spent.get('verdict') != 'VALID_GO_SPENT' or list(prefix.iterdir()):
        raise SystemExit('check did not say that the GO is spent, or the pycache prefix did not stay empty')
    transcript.note('REHEARSAL COMPLETE: %s, receipt verified by status; ssh was never started.' % resumed['status'])
    return workspace


def load_plain(directory, names):
    """The modules of one directory under their plain names (the dispatcher imports its siblings by name)."""
    for name in names:
        sys.modules.pop(name, None)
    loaded = {}
    for name in names:
        if name in sys.modules:
            loaded[name] = sys.modules[name]
            continue
        spec = importlib.util.spec_from_file_location(name, str(Path(directory) / (name + '.py')))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


def resume_w1_with_harness(bound, family, config_sha256, proof, proof_sha256):
    sys.path.insert(0, str(HERE))
    import bind_once
    bound, family = Path(bound).resolve(), Path(family).resolve()
    sheet = json.loads((bound / 'PREPARE.json').read_bytes())
    config = json.loads((bound / 'DISPATCH.BOUND.json').read_bytes())
    if (sheet.get('mode') != bind_once.REHEARSAL or config.get('target') != bind_once.REHEARSAL_TARGET
            or not bound.name.startswith(bind_once.REHEARSAL_PREFIX) or config.get('owner') != bind_once.REHEARSAL_OWNER):
        print(json.dumps({'status': 'REFUSED', 'code': 'HARNESS_RESUME_IS_FOR_REHEARSAL_SETS_ONLY'}))
        return 2
    # the family's own test file, loaded from the scratch copy: its emulated host and its helpers are the harness
    spec = importlib.util.spec_from_file_location('w1_family_tests', str(family / 'test_w1_preflight_once.py'))
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    source = (bound / 'w1_preflight_readonly.py').read_bytes()
    raws = [Path(config[key]['path']).read_bytes() for key in ('request', 'authority', 'go')]
    payload_on_disk = Path(config['payload']['path']).read_bytes()
    calls = []

    def transport(payload, *, payload_sha256, command, command_sha256, authorize, seconds, monotonic):
        calls.append(command[0])
        assert authorize(payload_sha256, command_sha256) is True          # the dispatcher's own last authorisation, as the real transport asks it
        assert payload == payload_on_disk and command[-2] == bind_once.REHEARSAL_TARGET
        p = harness.p
        pins = p.Pins(payload=p.sha(source), request=p.sha(raws[0]), authority=p.sha(raws[1]), go=p.sha(raws[2]))
        receipt = p.observe(raws[0], raws[1], raws[2], pins=pins, payload_bytes=source, executor_uid=lambda: 0,
                            collector=lambda request, gate: p.collect(request, gate, host=harness.world()))
        line = harness.line(receipt)
        echo = [sys.executable, '-I', '-B', '-c', harness.ECHO % (0 if receipt['status'] == 'METADATA_ONLY_REQUIRES_REVIEW' else 2)]
        return harness.t.once(line, payload_sha256=p.sha(line), command=echo, command_sha256=harness.t.command_pin(echo),
                              authorize=lambda a, b: True, seconds=30)
    dispatch = load_plain(bound, ('w1_preflight_readonly', 'launcher_stdin', 'transport_once', 'dispatch_once'))['dispatch_once']
    result = dispatch.execute(str(bound / 'DISPATCH.BOUND.json'), config_sha256, phase='resume', publication_path=proof,
                              publication_sha256=proof_sha256, transport=transport)
    try:
        dispatch.execute(str(bound / 'DISPATCH.BOUND.json'), config_sha256, phase='resume', publication_path=proof,
                         publication_sha256=proof_sha256, transport=transport)
        second = 'ACCEPTED'
    except BaseException as error:
        second = 'REFUSED_' + type(error).__name__
    report = {key: result.get(key) for key in ('status', 'code', 'returncode', 'config_sha256', 'request_sha256', 'go_sha256', 'stdout_sha256',
                                               'stderr_sha256', 'finished_at')}
    report.update(transport_calls=len(calls), ssh_started=False, second_resume=second,
                  harness='w1 source on the emulated host of test_w1_preflight_once.py; receipt through the reviewed transport with a local echo child')
    print(json.dumps(report, sort_keys=True))
    return 0


# ================================================================ HOSTOPS02 (in process, injected clocks)
HOSTOPS02_KINDS = ('catalog', 'readback', 'release', 'activate')


class Steps:
    """The transcript of an in-process rehearsal: each step a call of the binder's own function (or of the family's
    dispatcher), its result reduced to what is compared, and the expectation it had to meet."""

    def __init__(self, path):
        self.path, self.steps = path, []

    def save(self):
        self.path.write_text(json.dumps(self.steps, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        os.chmod(str(self.path), 0o600)

    def note(self, text):
        self.steps.append({'note': text})
        self.save()
        print(text, flush=True)

    def call(self, name, function, expect=None, refused=None):
        import bind_once as b
        try:
            value = function()
            code = None
        except b.Refused as error:
            value, code = None, str(error)
        shown = {key: value.get(key) for key in ('status', 'verdict', 'outcome', 'verified', 'code', 'prepare_json_sha256', 'request_sha256', 'go_sha256',
                                                 'config_sha256', 'intent_sha256', 'publication_proof_sha256', 'success_criterion', 'remote_code')
                 if key in value} if type(value) is dict else {}
        if type(value) is dict and type(value.get('dispatch_gates')) is dict:
            shown['dispatch_gates'] = {key: value['dispatch_gates'][key] for key in ('required', 'failed', 'step')}
        if type(value) is dict and 'sheet' in value:
            shown['sheet'] = {key: value['sheet'].get(key) for key in ('mode', 'operation', 'success_criterion', 'signature_model', 'host_binding_sha256')}
            shown['sheet']['hostops02'] = {key: value['sheet']['hostops02'][key] for key in ('dispatch_gates', 'bind_inputs', 'spare_of')}
        step = {'step': name, 'refused': code, 'result': shown, 'at_utc': zulu(datetime.now(timezone.utc))}
        self.steps.append(step)
        self.save()
        ok = (code == refused) if refused else (code is None and all(shown.get(key) == wanted for key, wanted in (expect or {}).items()))
        print('%-58s %s' % (name, ('REFUSED ' + code) if code else ' '.join('%s=%s' % (key, shown.get(key)) for key in sorted(expect or {}) if key in shown)), flush=True)
        if not ok:
            self.note('REHEARSAL STOPPED: step %s did not end as expected (%s)' % (name, refused or expect))
            raise SystemExit(1)
        return value

    def cli(self, name, argv, expect_exit, expect=None):
        done = subprocess.run([PYTHON, '-B', str(BINDER)] + [str(item) for item in argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, timeout=300)
        answer = json.loads(done.stdout)
        answer.pop('owner_question_pt', None)
        self.steps.append({'step': name, 'argv': [str(item) for item in argv], 'exit': done.returncode, 'stderr_bytes': len(done.stderr),
                           'stdout': {key: answer.get(key) for key in ('status', 'verdict', 'verified', 'code', 'outcome', 'window_verdict')},
                           'at_utc': zulu(datetime.now(timezone.utc))})
        self.save()
        print('%-58s exit=%d %s' % (name, done.returncode, answer.get('verdict') or answer.get('status')), flush=True)
        if done.returncode != expect_exit or done.stderr != b'' or any(answer.get(key) != value for key, value in (expect or {}).items()):
            self.note('REHEARSAL STOPPED: command-line step %s did not end as expected' % name)
            raise SystemExit(1)
        return answer


def rehearse_hostops02(kind, sources, hostops01, w1, workspace):
    """One HOSTOPS02 operation, rehearsed in full (see the module text)."""
    workspace = Path(workspace)
    if kind not in HOSTOPS02_KINDS or not workspace.is_absolute() or not workspace.name.startswith('rehearsal-') or os.path.lexists(str(workspace)):
        raise SystemExit('the workspace must be an absolute path that does not exist and whose name starts with rehearsal-')
    os.umask(0o077)
    workspace.mkdir(mode=0o700)
    workspace = workspace.resolve()
    (workspace / 'REHEARSAL_MARKER.txt').write_text(
        'REHEARSAL ONLY. Nothing below this directory was signed by the owner; the transport is fake (target in the reserved .invalid domain, '
        'marker files instead of a key); the receipts cited are synthetic, produced on emulated hosts; the clocks are injected; no document here '
        'can be dispatched to the real host.\n')
    sys.path.insert(0, str(HERE / 'tests'))
    sys.path.insert(0, str(HERE))
    import bind_once as b
    import hostops02_fixtures as x
    steps = Steps(workspace / 'TRANSCRIPT.json')
    copy = workspace / 'hostops02'
    sealed = steps.call('sealed-copy of the core and the four operations', lambda: b.sealed_copy(copy, [str(Path(item).resolve()) for item in sources]),
                        {'status': 'SEALED_COPY_WRITTEN'})
    steps.note('files taken from a later source (edited after their seal in the first): %s' % json.dumps(
        {name: item['files_taken_from_a_later_source'] for name, item in sealed['directories'].items() if item['files_taken_from_a_later_source']}))
    families = workspace / 'family-copies'
    families.mkdir(mode=0o700)
    h1_dir, w1_dir = families / 'hostops01', families / 'w1'
    shutil.copytree(str(hostops01), str(h1_dir), ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    shutil.copytree(str(w1), str(w1_dir), ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    h2 = x.hostops02(copy)
    h1 = x.hostops01(h1_dir)
    harness = x.w1_harness(w1_dir)
    reference = Path(steps.call('rehearsal-reference', lambda: b.rehearsal_reference(workspace / 'rehearsal-transport'),
                                {'status': 'REHEARSAL_REFERENCE_WRITTEN'})['reference'])
    precheck, provision, install = x.hostops01_receipts(h1, h2.hostemu.REVISION)
    receipts = workspace / 'cited-receipts'
    receipts.mkdir(mode=0o700)
    files = {name: x.write_receipt(receipts / ('%s.receipt.json' % name), x.resealed(receipt))
             for name, receipt in (('precheck', precheck), ('provision', provision), ('install', install))}
    steps.note('HOSTOPS01 receipts produced on that family\'s emulated host (precheck %s, provision %s, install %s), bound to the rehearsal host'
               % tuple(json.loads(path.read_bytes())['metadata_sha256'][:16] for path in (files['precheck'], files['provision'], files['install'])))
    release, policy = x.release_bytes(h2), None
    policy = x.policy_bytes(h2, release)
    override = x.override_bytes(h2, release, policy)
    inputs_dir = workspace / 'inputs'
    inputs_dir.mkdir(mode=0o700)
    inputs = {'release': str(x.write(inputs_dir / 'release.REHEARSAL.json', release)), 'policy': str(x.write(inputs_dir / 'policy.REHEARSAL.json', policy)),
              'override': str(x.write(inputs_dir / 'override.REHEARSAL.json', override))}
    # a synthetic document naming each operation, its seal, its source and its unbound final payload, and the core's seal: the
    # review member of every HOSTOPS02 request (the binder refuses one that does not name these bytes)
    review = x.review_record(workspace, copy, 'REVIEW_RECORD.REHEARSAL.txt')
    H1, W1F = str(h1_dir), str(w1_dir)
    dirs = {x.CATALOG: copy / 'catalog_init', x.RELEASE: copy / 'install_release', x.READBACK: copy / 'epoch_readback', x.ACTIVATE: copy / 'activate'}
    count = [0]

    def write_params(value):
        count[0] += 1
        path = workspace / ('PARAMETERS-%02d-%s.json' % (count[0], value['label']))
        path.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        return path

    def bound_set(operation, value, now, sign_at=None):
        out = workspace / ('rehearsal-' + value['label'])
        prepared = steps.call('prepare %s' % value['label'], lambda: b.prepare(dirs[operation], operation, write_params(value), reference, out, b.REHEARSAL,
                                                                              now=lambda: now), {'status': 'PREPARED_AWAITING_OWNER_SIGNATURE'})
        steps.call('refusal: the owner\'s word on a rehearsal set (%s)' % value['label'],
                   lambda: b.sign(out, prepared['prepare_json_sha256'], zulu(sign_at or now), 'Assino', now=lambda: sign_at or now), refused='OWNER_ANSWER_IS_NOT_THE_SIGNATURE')
        steps.call('sign %s (rehearsal marker, synthetic time)' % value['label'],
                   lambda: b.sign(out, prepared['prepare_json_sha256'], zulu(sign_at or now), b.REHEARSAL_ANSWER, now=lambda: sign_at or now),
                   {'status': 'BOUND_NOT_DISPATCHED'})
        # with the real clock: exit 0 while the window is open or not yet open; 1 past the latest start, or while the gates the sheet
        # names have not been given (this call gives none)
        late = datetime.now(timezone.utc) > b.parse_utc(prepared['sheet']['window']['latest_start'])
        steps.cli('check %s through the command line (real clock)' % value['label'], ['check', '--bound', out, '--family', dirs[operation]],
                  1 if late or prepared['sheet']['hostops02']['dispatch_gates'] else 0)
        return out, prepared

    def dispatch(out, label, host, at, gates=None, family=None, resume_gate=False):
        """[check] -> dispatcher prepare -> publish-proof -> check --step resume -> resume -> status, the clocks one second apart
        (block 6 and block 9 of the runbook run check first, for every HOSTOPS02 set)."""
        steps.call('check %s before the dispatcher prepare (block 6)' % label, lambda: b.check(out, family, gates, now=lambda: at),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        intent = steps.call('dispatcher prepare %s (the family\'s execute, phase prepare)' % label, lambda: x.dispatcher_prepare(out, at),
                            {'status': 'AWAITING_PUBLICATION_NO_SPAWN'})
        steps.call('refusal: a real comment id on a rehearsal set (%s)' % label,
                   lambda: b.publish_proof(out, '5955151654', zulu(at + timedelta(seconds=1)), now=lambda: at + timedelta(seconds=2)),
                   refused='REHEARSAL_SET_WITH_A_REAL_PUBLICATION')
        proof = steps.call('publish-proof %s' % label, lambda: b.publish_proof(out, b.REHEARSAL_PUBLICATION, zulu(at + timedelta(seconds=1)),
                                                                              now=lambda: at + timedelta(seconds=2)), {'status': 'PROOF_WRITTEN_NOT_DISPATCHED'})
        later = at + timedelta(seconds=150 if resume_gate else 3)
        steps.call('check %s --step resume (block 9: the gates, the minute and the latest start before the resume)' % label,
                   lambda: b.check(out, family, gates, 'resume', now=lambda: later), {'verdict': 'VALID_RESUME_ALLOWED_BY_THE_GATES'})
        state = b.signed_state(out)
        transport = x.emulated_transport(out, host, later)
        steps.call('resume %s (source on the emulated host, reviewed transport with an echo child; ssh never started)' % label,
                   lambda: state['rt']['dispatch'].execute(str(out / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume',
                                                           publication_path=proof['publication_proof_path'], publication_sha256=proof['publication_proof_sha256'],
                                                           clock=lambda: later, monotonic=lambda: 0.0, transport=transport), {'status': 'KNOWN_COMPLETE'})
        try:
            state['rt']['dispatch'].execute(str(out / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume', publication_path=proof['publication_proof_path'],
                                            publication_sha256=proof['publication_proof_sha256'], clock=lambda: later, monotonic=lambda: 0.0, transport=transport)
            second = 'ACCEPTED'
        except BaseException as error:
            second = 'REFUSED_' + type(error).__name__
        steps.note('a second resume of %s: %s; transport calls: %d' % (label, second, len(transport.calls)))
        if second == 'ACCEPTED' or len(transport.calls) != 1:
            raise SystemExit('a second resume was not refused')
        report = steps.call('status %s' % label, lambda: b.status(out), {'status': 'KNOWN_COMPLETE', 'verified': True})
        steps.cli('status %s through the command line' % label, ['status', '--bound', out], 0, {'verified': True})
        return report

    def gates_file(name, **items):
        path = workspace / name
        path.write_text(json.dumps(dict({'schema': b.GATES_SCHEMA}, **items), indent=1, sort_keys=True) + '\n', encoding='utf-8')
        return path

    def codex(out):
        """A1 section 8 at dispatch: a synthetic written review of THIS bound set (its request and final payload hashes)."""
        return x.codex_review_of(out, workspace)

    rows = precheck['items']['chains']['DATA_VOLUME']['rows']
    steps.call('refusal: a real set with the rehearsal transport', lambda: b.prepare(
        dirs[x.CATALOG], x.CATALOG, write_params(x.parameters(x.CATALOG, 'refused-real', x.A6, 15, x.catalog_plan(h2, x.catalog_host(h2, provision)[1], 'REHEARSAL'),
                                                             [], review=review)), reference, workspace / 'would-be-real', b.REAL, now=lambda: x.A6),
        refused='REAL_SET_WITH_REHEARSAL_TRANSPORT')
    if kind == 'catalog':
        evidence = [x.cite('PRECHECK', x.PRECHECK, files['precheck'], H1), x.cite('PROVISION', x.PROVISION, files['provision'], H1)]
        k, host = x.catalog_host(h2, provision)
        a6, prepared = bound_set(x.CATALOG, x.parameters(x.CATALOG, 'a6', x.A6, 15, x.catalog_plan(h2, host, 'REHEARSAL'), evidence, review=review), x.A6)
        steps.call('check a6 without the review of the bound set', lambda: b.check(a6, dirs[x.CATALOG], now=lambda: x.A6 + timedelta(seconds=20)),
                   {'verdict': 'VALID_BUT_DISPATCH_GATES_NOT_MET'})
        gates6 = gates_file('GATES-a6.json', codex_review=codex(a6))
        steps.call('check a6 --gates (the review of the bound set)', lambda: b.check(a6, dirs[x.CATALOG], gates6, now=lambda: x.A6 + timedelta(seconds=20)),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        steps.call('check a6 at 17:06 BRT (a minute to avoid)', lambda: b.check(a6, dirs[x.CATALOG], gates6, now=lambda: x.A6 + timedelta(minutes=6)),
                   {'verdict': 'VALID_BUT_NOW_IS_A_MINUTE_TO_AVOID'})
        dispatch(a6, 'a6', x.catalog_host(h2, provision)[1], x.A6 + timedelta(seconds=30), gates6, dirs[x.CATALOG])
        grid = x.w1_set(workspace, w1_dir, harness, reference, 'rehearsal-w1-grid', 'grid', x.GRID, rows)
        steps.note('the grid read before A9: a W1 set bound, signed and resumed on W1\'s own emulated host (%s)' % grid.name)
        a9, prepared = bound_set(x.CATALOG, x.parameters(x.CATALOG, 'a9', x.A9, 15, x.catalog_plan(h2, host, 'REAL'), evidence, review=review,
                                                         rehearsal={'bound': str(a6)}), x.A9)
        steps.note('a9 prepared with the A6 receipt checked at prepare: %s' % json.dumps(prepared['sheet']['hostops02']['rules']['rehearsal_receipt'], sort_keys=True))
        steps.call('check a9 without its gates', lambda: b.check(a9, dirs[x.CATALOG], now=lambda: x.A9 + timedelta(minutes=1)),
                   {'verdict': 'VALID_BUT_DISPATCH_GATES_NOT_MET'})
        gates = gates_file('GATES-a9.json', rehearsal={'bound': str(a6), 'family': str(dirs[x.CATALOG])}, grid_read={'bound': str(grid), 'family': W1F},
                           codex_review=codex(a9))
        steps.call('check a9 --gates (A6 receipt, grid read, review of the bound set)', lambda: b.check(a9, dirs[x.CATALOG], gates, now=lambda: x.A9 + timedelta(minutes=1)),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        dispatch(a9, 'a9', x.catalog_host(h2, provision)[1], x.A9 + timedelta(minutes=1), gates, dirs[x.CATALOG])
        steps.call('check a9 after the resume', lambda: b.check(a9, dirs[x.CATALOG], gates, now=lambda: x.A9 + timedelta(minutes=2)), {'verdict': 'VALID_GO_SPENT'})
    elif kind == 'readback':
        k, host = x.readback_host(h2, 'PRE', release)
        pre, prepared = bound_set(x.READBACK, x.parameters(x.READBACK, 'm2p', x.K11_PRE, 60, x.readback_plan(h2, host, 'PRE', release, policy, override),
                                                           [x.cite('PRECHECK', x.PRECHECK, files['precheck'], H1)], inputs=dict(inputs), review=review,
                                                           siblings_tests={'document_file': review['document_file']}), x.K11_PRE)
        steps.call('check m2p', lambda: b.check(pre, dirs[x.READBACK], now=lambda: x.K11_PRE + timedelta(minutes=12)), {'verdict': 'VALID_WINDOW_OPEN'})
        dispatch(pre, 'm2p', host, x.K11_PRE + timedelta(minutes=12), None, dirs[x.READBACK])
        k, host = x.readback_host(h2, 'POST', release)
        post, prepared = bound_set(x.READBACK, x.parameters(x.READBACK, 'm2', x.K11_POST, 22, x.readback_plan(h2, host, 'POST', release, policy, override, 'M2P'),
                                                            [x.cite('PRECHECK', x.PRECHECK, files['precheck'], H1), x.cite('M2P', x.READBACK, pre)],
                                                            inputs={'release': inputs['release'], 'policy': inputs['policy']}, review=review,
                                                            siblings_tests={'document_file': review['document_file']}), x.SITTING)
        install_receipt = x.write_receipt(receipts / 'k10.receipt.json', x.resealed(x.k10_receipt(h2, x.M1 + timedelta(minutes=3), release)))
        gates = gates_file('GATES-m2.json', install={'receipt_file': str(install_receipt), 'family': str(dirs[x.RELEASE])})
        steps.call('check m2 --gates (M1 complete with these bytes)', lambda: b.check(post, dirs[x.READBACK], gates, now=lambda: x.K11_POST + timedelta(minutes=1)),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        dispatch(post, 'm2', host, x.K11_POST + timedelta(minutes=1), gates, dirs[x.READBACK])
    elif kind == 'release':
        sunday = x.w1_set(workspace, w1_dir, harness, reference, 'rehearsal-w1-sunday', 'sunday', x.SUNDAY, rows)
        m0 = x.w1_set(workspace, w1_dir, harness, reference, 'rehearsal-w1-m0', 'm0', x.M0, rows)
        steps.note('W1 sets: the Sunday read (%s) and M0 (%s), each bound, signed and resumed on W1\'s own emulated host' % (sunday.name, m0.name))
        pre_receipt = x.write_receipt(receipts / 'k11pre.receipt.json', x.resealed(x.k11_receipt(h2, 'PRE', x.K11_PRE + timedelta(minutes=12), release, policy)))
        evidence = [x.cite('S1_PRECHECK', x.PRECHECK, files['precheck'], H1), x.cite('A3_PROVISION', x.PROVISION, files['provision'], H1),
                    x.cite('B1_INSTALL', x.INSTALL, files['install'], H1), x.cite('SUNDAY_W1', x.W1, sunday, W1F),
                    x.cite('M2P', x.READBACK, pre_receipt, dirs[x.READBACK]), x.cite('A4_PROVISION', x.PROVISION, files['provision'], H1)]
        k, host = x.release_host(h2)
        value = x.parameters(x.RELEASE, 'm1', x.M1, 15, x.release_plan(h2, host, release, 'S1_PRECHECK'), evidence, signature_model='PRE',
                             inputs={'release': inputs['release']}, review=review)
        m1, prepared = bound_set(x.RELEASE, value, x.SITTING)
        spare, prepared = bound_set(x.RELEASE, dict(value, label='m1-spare', not_before=zulu(x.M1_SPARE), not_after=zulu(x.M1_SPARE + timedelta(minutes=15)),
                                                    spare_of={'bound': str(m1)}), x.SITTING)
        gates = gates_file('GATES-m1.json', m0={'bound': str(m0), 'family': W1F}, codex_review={'document_file': review['document_file'], 'form': 'CANDIDATE_REVIEW_SUFFICES'})
        for name, out in (('m1', m1), ('m1-spare', spare)):
            steps.call('check %s --gates (M0 through binding/predispatch.py), 05:21 BRT' % name,
                       lambda: b.check(out, dirs[x.RELEASE], gates, now=lambda: x.M1 - timedelta(minutes=5)), {'verdict': 'VALID_WINDOW_NOT_YET_OPEN'})
        at = x.M1 + timedelta(seconds=30)
        intent = steps.call('dispatcher prepare m1', lambda: x.dispatcher_prepare(m1, at), {'status': 'AWAITING_PUBLICATION_NO_SPAWN'})
        steps.call('check m1-spare once the primary\'s claim exists', lambda: b.check(spare, dirs[x.RELEASE], gates, now=lambda: at + timedelta(seconds=5)),
                   {'verdict': 'VALID_BUT_DISPATCH_GATES_NOT_MET'})
        proof = steps.call('publish-proof m1', lambda: b.publish_proof(m1, b.REHEARSAL_PUBLICATION, zulu(at + timedelta(seconds=1)), now=lambda: at + timedelta(seconds=2)),
                           {'status': 'PROOF_WRITTEN_NOT_DISPATCHED'})
        steps.call('check m1 --step resume too early', lambda: b.check(m1, dirs[x.RELEASE], gates, 'resume', now=lambda: at + timedelta(seconds=30)),
                   {'verdict': 'VALID_BUT_RESUME_GATES_NOT_MET'})
        later = at + timedelta(seconds=150)
        steps.call('check m1 --step resume', lambda: b.check(m1, dirs[x.RELEASE], gates, 'resume', now=lambda: later), {'verdict': 'VALID_RESUME_ALLOWED_BY_THE_GATES'})
        state = b.signed_state(m1)
        transport = x.emulated_transport(m1, x.release_host(h2)[1], later)
        steps.call('resume m1 (source on the emulated host, reviewed transport with an echo child; ssh never started)',
                   lambda: state['rt']['dispatch'].execute(str(m1 / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume',
                                                           publication_path=proof['publication_proof_path'], publication_sha256=proof['publication_proof_sha256'],
                                                           clock=lambda: later, monotonic=lambda: 0.0, transport=transport), {'status': 'KNOWN_COMPLETE'})
        steps.call('status m1', lambda: b.status(m1), {'status': 'KNOWN_COMPLETE', 'verified': True})
        steps.cli('status m1 through the command line', ['status', '--bound', m1], 0, {'verified': True})
    else:
        pre_receipt = x.write_receipt(receipts / 'k11pre.receipt.json', x.resealed(x.k11_receipt(h2, 'PRE', x.K11_PRE + timedelta(minutes=12), release, policy)))
        post_receipt = x.write_receipt(receipts / 'k11post.receipt.json', x.resealed(x.k11_receipt(h2, 'POST', x.K11_POST + timedelta(minutes=1), release, policy)))
        k, host = x.activate_host(h2, release)
        value = x.parameters(x.ACTIVATE, 'm3', x.M3, 15, x.activate_plan(h2, host), [x.cite('M2P', x.READBACK, pre_receipt, dirs[x.READBACK])],
                             signature_model='PRE', inputs={'policy': inputs['policy'], 'release': inputs['release'], 'override': inputs['override']}, review=review)
        m3, prepared = bound_set(x.ACTIVATE, value, x.SITTING)
        spare, prepared = bound_set(x.ACTIVATE, dict(value, label='m3-spare', not_before=zulu(x.M3_SPARE), not_after=zulu(x.M3_SPARE + timedelta(minutes=15)),
                                                     spare_of={'bound': str(m3)}), x.SITTING)
        gates = gates_file('GATES-m3.json', readback_post={'receipt_file': str(post_receipt), 'family': str(dirs[x.READBACK])},
                           codex_review={'document_file': review['document_file'], 'form': 'CANDIDATE_REVIEW_SUFFICES'})
        steps.call('check m3 --gates (M2 complete, no leftover)', lambda: b.check(m3, dirs[x.ACTIVATE], gates, now=lambda: x.M3 + timedelta(seconds=30)),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        steps.call('check m3-spare --gates before the primary', lambda: b.check(spare, dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + timedelta(seconds=30)),
                   {'verdict': 'VALID_WINDOW_OPEN'})
        dispatch(m3, 'm3', host, x.M3 + timedelta(seconds=40), gates, dirs[x.ACTIVATE])
        steps.call('check m3-spare --gates after the primary', lambda: b.check(spare, dirs[x.ACTIVATE], gates, now=lambda: x.M3_SPARE + timedelta(seconds=30)),
                   {'verdict': 'VALID_BUT_DISPATCH_GATES_NOT_MET'})
    steps.note('REHEARSAL COMPLETE: %s; every resume ran the sealed source on its own emulated host; ssh was never started.' % kind)
    return workspace


def main():
    parser = argparse.ArgumentParser(description='Rehearsal of bind_once.py on scratch copies; never contacts a host.', allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    for kind in ('w1', 'precheck'):
        sub = commands.add_parser(kind, allow_abbrev=False)
        sub.add_argument('--family', required=True)
        sub.add_argument('--workspace', required=True)
        sub.add_argument('--real-reference')
    for kind in HOSTOPS02_KINDS:
        sub = commands.add_parser('hostops02-' + kind, allow_abbrev=False)
        sub.add_argument('--hostops02', required=True, action='append')
        sub.add_argument('--hostops01', required=True)
        sub.add_argument('--w1', required=True)
        sub.add_argument('--workspace', required=True)
    resume = commands.add_parser('resume-w1-with-harness', allow_abbrev=False)
    for name in ('--bound', '--family', '--config-sha256', '--proof', '--proof-sha256'):
        resume.add_argument(name, required=True)
    args = parser.parse_args()
    if args.command == 'resume-w1-with-harness':
        return resume_w1_with_harness(args.bound, args.family, args.config_sha256, args.proof, args.proof_sha256)
    if args.command.startswith('hostops02-'):
        workspace = rehearse_hostops02(args.command[len('hostops02-'):], args.hostops02, args.hostops01, args.w1, args.workspace)
        print('workspace: %s' % workspace)
        return 0
    workspace = rehearse(args.command, args.family, args.workspace, args.real_reference)
    print('workspace: %s' % workspace)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
