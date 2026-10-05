"""Synthetic inputs and emulated hosts for binding the four HOSTOPS02 operations (K2a catalog_init, K10 install_release,
K11 epoch_readback, K6a activate), shared by the tests and by rehearse.py. Nothing here is a value of the real host.

- sealed copies: the frozen core and the four operation directories, only the files their seals list (CONTRACT K10 6.1:
  "a copy that holds only the files SHA256SUMS lists, SHA256SUMS itself and ../core");
- the families' own test modules, each family loaded in an isolated window of sys.modules (HOSTOPS01 and HOSTOPS02 both
  name their emulators `family` and `hostemu`);
- receipts of the cited operations PRODUCED by their own sealed sources on their families' emulated hosts (HOSTOPS01
  precheck, provision and install_units; K11 PRE and POST; K10), then bound to the host binding of the rehearsal sets and
  sealed again, as the binder's tests already do for HOSTOPS01;
- the emulated hosts the resumes run on, made to be the host those receipts describe (inode numbers of the provisioned
  directories, the revision label of the image);
- W1 bound sets (REHEARSAL) resumed on W1's own emulated host, the rows of the data volume set to the rows the HOSTOPS
  emulators use (the W1 emulator numbers its devices otherwise), sealed again;
- release, policy and override bytes: the shape and the constants of this epoch, marked as rehearsal bytes."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import types

HERE = Path(__file__).resolve().parent
BIND = HERE.parent
SCRATCH = BIND.parent
if str(BIND) not in sys.path:
    sys.path.insert(0, str(BIND))
import bind_once as b          # noqa: E402

# The durable copy of the tier as it went to the co-auditor on 2026-10-02 (NOTE_FOR_CODEX_TIER0.md), every file with its sealed hash.
DURABLE_TIER = Path('/offline/optional-work/fable-hostops02-tier0-20261002-r2')
HOSTOPS02_SOURCE = Path(os.environ.get('BIND_TEST_HOSTOPS02', str(DURABLE_TIER)))
DIRECTORIES = ('core', 'catalog_init', 'install_release', 'epoch_readback', 'activate')
CATALOG, RELEASE, READBACK, ACTIVATE = b.CATALOG_OPERATION, b.RELEASE_OPERATION, b.EPOCH_READBACK_OPERATION, b.ACTIVATE_OPERATION
PRECHECK, PROVISION, INSTALL, W1 = b.PRECHECK_OPERATION, b.PROVISION_OPERATION, b.INSTALL_OPERATION, b.W1_OPERATION
UTC = timezone.utc
# The instants of the weekend plan (MASTER_PLAN 2.2, 2.3, 2.5), in UTC. All synthetic; used with injected clocks.
S1 = datetime(2026, 10, 3, 12, 10, tzinfo=UTC)            # sáb 09:10 BRT: the HOSTOPS01 precheck
A3 = datetime(2026, 10, 3, 12, 45, tzinfo=UTC)            # sáb 09:45: the provision
B1 = datetime(2026, 10, 4, 12, 30, tzinfo=UTC)            # dom 09:30: the install of the units
A6 = datetime(2026, 10, 3, 20, 0, tzinfo=UTC)             # sáb 17:00: catalog rehearsal
GRID = datetime(2026, 10, 3, 20, 26, tzinfo=UTC)          # sáb 17:26: the grid read before A9
A9 = datetime(2026, 10, 3, 20, 38, tzinfo=UTC)            # sáb 17:38: the real catalog
K11_PRE = datetime(2026, 10, 4, 15, 15, tzinfo=UTC)       # dom 12:15: M2p
SUNDAY = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)         # dom 19:00: the W1 read of Sunday, then the sitting that signs M1 and M3
SITTING = datetime(2026, 10, 4, 22, 30, tzinfo=UTC)
M0 = datetime(2026, 10, 5, 8, 0, tzinfo=UTC)              # seg 05:00
M1 = datetime(2026, 10, 5, 8, 26, tzinfo=UTC)             # seg 05:26 to 05:41
M1_SPARE = datetime(2026, 10, 5, 8, 42, tzinfo=UTC)       # seg 05:42 to 05:57
K11_POST = datetime(2026, 10, 5, 8, 38, tzinfo=UTC)       # seg 05:38 (after M1's receipt), gate to 06:00
M3 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)              # seg 06:00 to 06:15 (gate after M2's)
M3_SPARE = datetime(2026, 10, 5, 9, 26, tzinfo=UTC)       # seg 06:26 to 06:41
ECHO = 'import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data);raise SystemExit(%d)'
RELEASE_LEAF = 'r2d2-v2-release-20261005'
REHEARSAL_HOST = b.host_binding(b.REHEARSAL_TARGET, b.sha(b.REHEARSAL_HOSTS))


def zulu(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def sources():
    """Where the sealed bytes are looked for: the durable copy of the tier (BIND_TEST_HOSTOPS02), which holds every file of
    the accepted seals with its sealed hash; no verifier's copy of a superseded seal is needed or accepted.
    BIND_TEST_HOSTOPS02_SOURCES (colon-separated) replaces the list."""
    if os.environ.get('BIND_TEST_HOSTOPS02_SOURCES'):
        return [Path(item) for item in os.environ['BIND_TEST_HOSTOPS02_SOURCES'].split(':') if item]
    return [HOSTOPS02_SOURCE]


def sealed_copy(destination):
    """The core and the four operation directories, each with only the files its seal lists and the list itself, every
    file with its sealed hash (bind_once.py sealed-copy)."""
    result = b.sealed_copy(Path(destination), [str(path) for path in sources()])
    (Path(destination) / 'SEALED_COPY_REPORT.json').write_text(json.dumps(result, indent=1, sort_keys=True), encoding='utf-8')
    return Path(destination)


def load_isolated(directories, names):
    """Modules imported by their plain names with `directories` first on sys.path, then detached from sys.modules (the
    previous holders of those names are put back): two families that both name a module `family` can be used side by side."""
    plain = set(names) | {'family', 'hostemu', 'oslevel', 'conformance', 'native_child'}
    saved = {name: sys.modules.pop(name, None) for name in plain}
    for directory in reversed(directories):
        sys.path.insert(0, str(directory))
    try:
        return types.SimpleNamespace(**{name: importlib.import_module(name) for name in names})
    finally:
        for directory in directories:
            sys.path.remove(str(directory))
        for name in plain:
            sys.modules.pop(name, None)
            if saved[name] is not None:
                sys.modules[name] = saved[name]


def hostops02(root):
    """family, hostemu (the core's) and the four operations' fixture modules, from a sealed copy."""
    root = Path(root)
    return load_isolated([root / 'core' / 'tests', root / 'catalog_init' / 'tests', root / 'install_release' / 'tests',
                          root / 'epoch_readback' / 'tests', root / 'activate' / 'tests'], ['family', 'hostemu', 'k2a', 'k10', 'k11', 'k6a'])


def hostops01(candidate):
    return load_isolated([Path(candidate) / 'tests'], ['family', 'hostemu'])


def w1_harness(candidate):
    spec = importlib.util.spec_from_file_location('w1_candidate_tests_for_hostops02', str(Path(candidate) / 'test_w1_preflight_once.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resealed(receipt, host=REHEARSAL_HOST, change=None):
    value = json.loads(json.dumps(receipt))
    value.pop('metadata_sha256')
    value['host_binding_sha256'] = host
    if change:
        change(value)
    value['metadata_sha256'] = b.sha(b.canonical(value))
    return value


def write_receipt(path, receipt):
    Path(path).write_bytes(b.canonical(receipt) + b'\n')
    Path(path).chmod(0o600)
    return Path(path)


def write(path, raw):
    Path(path).write_bytes(raw)
    Path(path).chmod(0o600)
    return Path(path)


# ---------------------------------------------------------------- HOSTOPS01: precheck, provision, install_units on one emulated host
def hostops01_receipts(h1, revision, with_host=False):
    """The three HOSTOPS01 receipts a weekend produces, in order, on ONE emulated host of that family whose production
    image carries `revision` (the HOSTOPS02 emulators' release revision): precheck S1, provision A3, install B1."""
    f, hostemu = h1.family, h1.hostemu
    k = f.load('precheck')
    host = f.world(k)
    for image in host.docker.images:
        image['Config']['Labels']['org.opencontainers.image.revision'] = revision
    precheck = f.Docs(k, f.precheck_fields(k, host, placement='A'), now=S1).run(host)
    assert precheck['outcome'] == 'PRECHECK_ALL_OBSERVED', precheck.get('code')
    k = f.load('provision')
    host.refused = k.m.Refused
    provision = f.Docs(k, f.provision_fields(k, host, placement='A'), now=A3).run(host)
    assert provision['outcome'] == 'PROVISIONED_ALL_VERIFIED_DURABLE', provision.get('code')
    k = f.load('install_units')
    host.refused = k.m.Refused
    install = f.Docs(k, f.install_fields(k, host, placement='A'), now=B1).run(host)
    assert install['status'] == 'METADATA_ONLY_REQUIRES_REVIEW', install.get('code')
    return (precheck, provision, install, host) if with_host else (precheck, provision, install)


def ledger_inodes(provision):
    return {row['path']: row['observed']['inode'] for row in provision['ledger'] if row.get('state') == 'CREATED_DURABLE'}


# ---------------------------------------------------------------- bytes of this epoch, marked as rehearsal bytes
def release_bytes(h2):
    """A release in the shape and with the constants of this epoch (the deployed revision and package, so that the K10
    tool and the K11 snippet's stand-in accept it), marked in its authorization reference as rehearsal bytes."""
    return h2.k11.release_bytes(authorization_ref='REHEARSAL_SYNTHETIC_NOT_A_RELEASE_NEVER_TO_BE_BOUND_FOR_REAL')


def policy_bytes(h2, release):
    return h2.k11.policy_bytes(release)


def override_bytes(h2, release, policy):
    return h2.k11.override_bytes(release, policy)


# ---------------------------------------------------------------- K11 receipts on K11's emulated host (evidence for K10 and K6a)
# The instants at which K11 checks the policy: the starts of M3's two gates, the first open, one second before the last close
# (CONTRACT K11 section 7).
VALID_AT = [M3.isoformat(), M3_SPARE.isoformat(), '2026-10-05T13:30:00+00:00', '2026-10-09T19:59:59+00:00']


def k11_receipt(h2, mode, now, release, policy, rows_in_receipt=True):
    k = h2.family.load(h2.k11.DIRECTORY)
    host = h2.k11.world(k, mode, release=release)
    fields = h2.k11.fields(host, mode, release=release, policy=policy, override=override_bytes(h2, release, policy) if mode == 'PRE' else None,
                           rows_in_receipt=rows_in_receipt, valid_at=VALID_AT)
    receipt = h2.family.Docs(k, fields, now=now, minutes=30).run(host)
    assert receipt['status'] == 'METADATA_ONLY_REQUIRES_REVIEW', (receipt.get('outcome'), receipt.get('code'), receipt.get('findings'))
    return receipt


def k10_receipt(h2, now, release):
    k = h2.family.load(h2.k10.DIRECTORY)
    host = h2.family.world(k)
    receipt = h2.family.Docs(k, h2.k10.fields(host, release), now=now, minutes=15).run(host)
    assert receipt['outcome'] == b.RELEASE_INSTALLED_OUTCOME, receipt.get('code')
    return receipt


# ---------------------------------------------------------------- the emulated hosts the resumes run on
def catalog_host(h2, provision):
    """K2a's emulated host after supervisor operation 2, its provisioned directories carrying the inode numbers the cited
    provision receipt observed (the two emulators number new directories differently)."""
    k, host = h2.k2a.world()
    for path, inode in ledger_inodes(provision).items():
        node = host.tree.get(path)
        if node is not None:
            node.ino = inode
    return k, host


def release_host(h2):
    k = h2.family.load(h2.k10.DIRECTORY)
    return k, h2.family.world(k)


def readback_host(h2, mode, release):
    k = h2.family.load(h2.k11.DIRECTORY)
    return k, h2.k11.world(k, mode, release=release)


def activate_host(h2, release):
    """K6a runs after the install: K11's emulated host in its POST state (the release installed, the live parent there,
    the worker's bind of the data volume in the render), the host K11's receipts describe."""
    k = h2.family.load(h2.k6a.DIRECTORY)
    host = h2.k11.world(h2.family.load(h2.k11.DIRECTORY), 'POST', release=release)
    host.refused = k.m.Refused
    host.not_started = getattr(k.m, 'NotStarted', k.m.Refused)
    return k, host


# ---------------------------------------------------------------- in-process dispatch of a bound set (injected clocks)
def dispatcher_prepare(bound, clock):
    state = b.signed_state(bound)
    return state['rt']['dispatch'].execute(str(Path(bound) / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='prepare',
                                           clock=lambda: clock, monotonic=lambda: 0.0, transport=never)


def never(*args, **kwargs):
    raise AssertionError('transport must not run')


def emulated_transport(bound, host, at, change=None):
    """The source of the bound set on an emulated host, target uid injected (what the remote side would answer), its line
    passed through the reviewed transport bytes of the set with a local echo child, exactly as the W1 rehearsal does."""
    state = b.signed_state(bound)
    m, t, raws, source = state['rt']['source'], state['rt']['transport'], state['raws'], state['rt']['source_bytes']
    calls = []

    def transport(payload, **kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'], kwargs['command_sha256']) is True
        calls.append(kwargs['command'][-2] if len(kwargs['command']) > 1 else None)
        pins = m.Pins(payload=b.sha(source), request=b.sha(raws[0]), authority=b.sha(raws[1]), go=b.sha(raws[2]))
        if b.profile_of(m) == 'core':
            receipt = m.run(raws[0], raws[1], raws[2], pins=pins, payload_bytes=source, host=host, clock=lambda: at, monotonic=lambda: 0,
                            executor_uid=lambda: 0)
        else:
            receipt = m.observe(raws[0], raws[1], raws[2], pins=pins, payload_bytes=source, clock=lambda: at, monotonic=lambda: 0,
                                executor_uid=lambda: 0, collector=lambda request, gate: m.collect(request, gate, host=host))
        if change:
            receipt.pop('metadata_sha256')
            change(receipt)
            receipt['metadata_sha256'] = b.sha(b.canonical(receipt))
        line = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        echo = [sys.executable, '-I', '-B', '-c', ECHO % (0 if receipt['status'] == 'METADATA_ONLY_REQUIRES_REVIEW' else 2)]
        return t.once(line, payload_sha256=b.sha(line), command=echo, command_sha256=t.command_pin(echo), authorize=lambda a, c: True, seconds=60)
    transport.calls = calls
    return transport


def finish(bound, host, at, change=None, comment=b.REHEARSAL_PUBLICATION):
    """dispatcher prepare -> publish-proof -> resume (once) -> status, with injected clocks one second apart."""
    intent = dispatcher_prepare(bound, at)
    assert intent['status'] == 'AWAITING_PUBLICATION_NO_SPAWN', intent
    proof = b.publish_proof(bound, comment, zulu(at + timedelta(seconds=1)), now=lambda: at + timedelta(seconds=2))
    state = b.signed_state(bound)
    transport = emulated_transport(bound, host, at + timedelta(seconds=3), change)
    result = state['rt']['dispatch'].execute(str(Path(bound) / 'DISPATCH.BOUND.json'), b.sha(state['config_raw']), phase='resume',
                                             publication_path=proof['publication_proof_path'], publication_sha256=proof['publication_proof_sha256'],
                                             clock=lambda: at + timedelta(seconds=3), monotonic=lambda: 0.0, transport=transport)
    return intent, proof, result, b.status(bound)


def stdout_of(bound, label):
    return json.loads((Path(bound) / '.dispatch-root' / (label + '-once') / 'stdout.private.json').read_bytes())


# ---------------------------------------------------------------- W1 reads (grid read, Sunday read, M0)
def w1_set(base, w1_family, harness, reference, name, label, now, rows, mode=b.REHEARSAL, candidates=(RELEASE_LEAF,)):
    """A W1 set bound, signed and resumed on W1's own emulated host at `now`; the three rows of the data volume set to
    `rows` (the rows the HOSTOPS emulators use) before the receipt is sealed again."""
    params = {'schema': b.PARAMETERS_SCHEMA, 'operation': W1, 'label': label, 'signature_model': 'IND', 'not_before': zulu(now),
              'not_after': zulu(now + timedelta(minutes=20)), 'candidates': {'release_directories': list(candidates), 'capacity_roots': []}}
    path = Path(base) / ('P-%s.json' % label)
    path.write_text(json.dumps(params, sort_keys=True), encoding='utf-8')
    out = Path(base) / name
    prepared = b.prepare(w1_family, W1, path, reference, out, mode, now=lambda: now)
    b.sign(out, prepared['prepare_json_sha256'], zulu(now), b.REAL_ANSWER if mode == b.REAL else b.REHEARSAL_ANSWER, now=lambda: now)
    host = harness.world()
    host.clock = (now + timedelta(seconds=3)).timestamp()

    def change(receipt):
        for row, want in zip(receipt['observation']['sections']['data_volume']['ancestors'], rows):
            row.update(device=want['device'], inode=want['inode'], uid=want['uid'], gid=want['gid'], mode_octal='%04o' % want['mode'])
    comment = b.REHEARSAL_PUBLICATION if mode == b.REHEARSAL else '5955151654'
    intent, proof, result, report = finish(out, host, now, change, comment)
    assert report['verified'] is True, report
    return out


# ---------------------------------------------------------------- parameter files, as the runbook's templates write them
def frm(role, pointer):
    return {'$from': {'evidence': role, 'pointer': pointer}}


def inp(name, form):
    return {'$input': name, 'as': form}


def inp_member(name, member):
    return {'$input': name, 'as': 'member', 'member': member}


def cite(role, operation, path, family=None):
    """An evidence item: a directory is cited as a bound set, a file as a loose receipt (rehearsals only)."""
    item = {'role': role, 'operation': operation, ('bound' if Path(path).is_dir() else 'receipt_file'): str(path)}
    if family is not None:
        item['family'] = str(family)
    return item


def parameters(operation, label, start, minutes, plan, evidence, signature_model='IND', **extra):
    value = {'schema': b.PARAMETERS_SCHEMA, 'operation': operation, 'label': label, 'signature_model': signature_model,
             'not_before': zulu(start), 'not_after': zulu(start + timedelta(minutes=minutes)), 'plan': plan, 'evidence': evidence}
    value.update(extra)
    return value


def ledger(path, key, role='PROVISION'):
    return {'$ledger_row': {'evidence': role, 'path': path, 'key': key}}


def catalog_plan(h2, host, mode, throwaway='c3po-bar-rehearsal-20261003a', diagnostic='R2D2-V2-DIAG-K2A-REHEARSAL-20261003'):
    """K2a's plan as the runbook's template writes it: every row by command from the cited receipts (the precheck's chains
    VAR_LIB and ETC, then the provision ledger's rows), the pinned script and the compiled epoch from the source. Only the
    mode, the throwaway name, the diagnostic epoch and the container path are decided on the sheet."""
    var_lib, etc = frm('PRECHECK', '/items/chains/VAR_LIB/rows'), frm('PRECHECK', '/items/chains/ETC/rows')
    journal = {'$concat': [var_lib, [ledger('/var/lib/c3po-bar', 'SUP_STATE_PARENT'), ledger('/var/lib/c3po-bar/journal', 'SUP_JOURNAL')]]}
    real = mode == 'REAL'
    return {'mode': mode, 'journal_chain': journal if real else var_lib, 'throwaway_name': None if real else throwaway,
            'reference_chain': None if real else journal, 'container_journal_root': '/c3po-bar-journal',
            'docker_config_chain': {'$concat': [etc, [ledger('/etc/c3po-bar', 'SUP_CONFIG'), ledger('/etc/c3po-bar/docker-cli', 'SUP_DOCKER_CLI')]]},
            'image_id': frm('PRECHECK', '/items/image/id'), 'image_revision': frm('PRECHECK', '/items/image/revision_label'),
            'epoch': {'$source': 'EPOCH_COMPILED'} if real else diagnostic, 'script_sha256': {'$source': 'CATALOG_SCRIPT_SHA256'},
            'evidence_boot_id_sha256': frm('PRECHECK', '/items/boot/boot_id_sha256')}


def readback_plan(h2, host, mode, release, policy, override, pre_role=None):
    """K11's plan. PRE (Sunday): the release parent's rows by pointer from the precheck; the other directories observed
    (rows null: walk, record, compare with nothing). POST (Monday): their rows by pointer from the cited full PRE."""
    plan = json.loads(json.dumps(h2.k11.fields(host, mode, release=release, policy=policy, override=override if mode == 'PRE' else None,
                                               rows_in_receipt=True, valid_at=VALID_AT)))
    plan['release'].update(sha256=inp('release', 'sha256'), bytes=inp('release', 'bytes'), content_b64=inp('release', 'b64') if mode == 'PRE' else None)
    plan['release']['parent']['rows'] = frm('PRECHECK', '/items/chains/DATA_VOLUME/rows')
    plan['policy'].update(sha256=inp('policy', 'sha256'), bytes=inp('policy', 'bytes'), content_b64=inp('policy', 'b64'))
    if plan['render'] is not None:
        plan['render'].update(override_b64=inp('override', 'b64'), override_sha256=inp('override', 'sha256'), override_bytes=inp('override', 'bytes'))
    for chain, name in ((plan['live']['parent'], 'LIVE_PARENT'), (plan['deploy']['tree'], 'DEPLOY_TREE'), (plan['deploy']['lock_directory'], 'LOCK_DIRECTORY')):
        chain['rows'] = frm(pre_role, '/items/directory:%s/observed_rows' % name) if pre_role else None
    if plan['bind_probe'] is not None:
        plan['bind_probe']['directory']['rows'] = None
    plan.update(evidence_boot_id_sha256=frm('PRECHECK', '/items/boot/boot_id_sha256'), revision=inp_member('release', 'code_revision'),
                package_sha256=inp_member('release', 'implementation_package_sha'))
    plan['image']['image_id'] = frm('PRECHECK', '/items/image/id')
    return plan


def release_plan(h2, host, release, precheck_role='PRECHECK'):
    plan = json.loads(json.dumps(h2.k10.fields(host, release)))
    plan['parent'] = frm(precheck_role, '/items/chains/DATA_VOLUME/rows')
    plan['evidence_boot_id_sha256'] = frm(precheck_role, '/items/boot/boot_id_sha256')
    plan['release'].update(path={'$source': 'RELEASE_PATH'}, content_b64=inp('release', 'b64'), sha256=inp('release', 'sha256'), bytes=inp('release', 'bytes'))
    return plan


def activate_plan(h2, host, pre_role='M2P'):
    """K6a's plan: the four chains, the boot, the image, the data bind by pointer from the cited full PRE; the policy and the
    release hash and size from their input files; names chosen by the signatories."""
    plan = json.loads(json.dumps(h2.k6a.fields(host)))
    plan.update(live_parent=frm(pre_role, '/items/directory:LIVE_PARENT/observed_rows'), deploy_directory=frm(pre_role, '/items/directory:DEPLOY_TREE/observed_rows'),
                evidence_boot_id_sha256=frm(pre_role, '/effects/evidence_boot_id_sha256'), data_root=frm(pre_role, '/effects/worker/data_source'))
    plan['release'].update(parent=frm(pre_role, '/items/directory:RELEASE_PARENT/observed_rows'), sha256=inp('release', 'sha256'), bytes=inp('release', 'bytes'))
    plan['lock']['directory'] = frm(pre_role, '/items/directory:LOCK_DIRECTORY/observed_rows')
    plan['worker'].update(image_id=frm(pre_role, '/effects/image/image_id'), mount_target=frm(pre_role, '/effects/worker/data_target'))
    plan['compose'] = {key: frm(pre_role, '/effects/render/' + key) for key in ('project', 'env_file', 'files')}
    plan['policy'] = {'name': 'policy.json', 'content_b64': inp('policy', 'b64'), 'sha256': inp('policy', 'sha256'), 'bytes': inp('policy', 'bytes')}
    return plan


README_COMMAND = (
    '```\n'
    'sha256sum catalog-init.py\n'
    'DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli docker run --rm -i --pull never --init --user 0:0 --network none --read-only \\\n'
    '  --cap-drop ALL --security-opt no-new-privileges \\\n'
    '  --mount type=bind,source=<HOST_JOURNAL_ROOT>,target=<CONTAINER_JOURNAL_ROOT> \\\n'
    '  <IMAGE_ID> python -I -B - <CONTAINER_JOURNAL_ROOT> "$epoch" < catalog-init.py\n'
    '```\n')


def release_tree(directory, h2, command=README_COMMAND):
    """A stand-in for a tree of the release (dd4ec4bb): the supervisor README with its command block (lines 336 to 339 as
    the release writes them) and the pinned script between its markers, and the epoch assembler's EPOCH line. Synthetic;
    for the comparisons of K2a CONTRACT 5 steps 2 and 4 only."""
    k = h2.family.load(h2.k2a.DIRECTORY)
    script = k.m.script_bytes().decode('utf-8')
    readme = Path(directory) / 'c3po' / 'deployment' / 'massive-supervisor' / 'README.md'
    readme.parent.mkdir(parents=True)
    readme.write_text('SYNTHETIC STAND-IN, NOT THE RELEASE\n\n**The command.**\n\n%s\n<!-- catalog-init-script:begin -->\n```python\n%s```\n'
                      '<!-- catalog-init-script:end -->\n' % (command, script), encoding='utf-8')
    assembler = Path(directory) / 'c3po' / 'backend' / 'app' / 'r2d2_v2_epoch_assembler.py'
    assembler.parent.mkdir(parents=True)
    assembler.write_text('"""SYNTHETIC STAND-IN"""\nEPOCH = %r\n' % k.m.EPOCH_COMPILED, encoding='utf-8')
    return Path(directory)


def linux_junit_pair(directory, h2, tests=333):
    """Two junit files in the shape of the K10 Linux job's, from that directory's own test helper (tests/test_linux_proof.py).
    A TEST INPUT, NEVER A PROOF: the hostname inside says so."""
    tlp = load_isolated([Path(h2.k10.DIRECTORY).parent / 'core' / 'tests', Path(h2.k10.HERE)], ['test_linux_proof']).test_linux_proof
    root = write(Path(directory) / 'TESTS.install_release.linux-root.xml', tlp.junit(tlp.record(), tests=tests))
    user = write(Path(directory) / 'TESTS.install_release.linux-user.xml', tlp.junit(tlp.record(**tlp.USER), label='user', tests=tests))
    return {'root_junit': str(root), 'user_junit': str(user)}


# ---------------------------------------------------------------- the review of the bytes, the waiver, the Linux job record (synthetic)
def tier_hashes(copy):
    """{directory: (operation, seal, source, unbound final payload)} of the four operations of a sealed copy, and the core seal."""
    copy = Path(copy)
    found = {}
    for name in DIRECTORIES[1:]:
        record = json.loads((copy / name / 'build' / 'ASSEMBLY.json').read_bytes())
        found[name] = (record['operation'], b.sha((copy / name / 'SHA256SUMS').read_bytes()), record['source_sha256'], record['final_payload_sha256'])
    return found, b.sha((copy / 'core' / 'CORE_SHA256SUMS').read_bytes())


def review_record(directory, copy, name='REVIEW_RECORD.synthetic.txt'):
    """The review member of a request, with a synthetic document that names, as a review of the tier would, each operation,
    its seal, its source and its unbound final payload, and the core's seal. It also serves as the synthetic Linux job
    record and sibling-test record (it names every seal). No review, no job and no test run happened here."""
    hashes, core = tier_hashes(copy)
    lines = ['SYNTHETIC TEST DOCUMENT: stands for the review of these bytes (and for the Linux job record). Not a review.', 'core %s' % core]
    lines += ['%s %s seal %s source %s final %s' % ((name,) + item) for name, item in sorted(hashes.items())]
    path = Path(directory) / name
    if not path.exists():
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return {'kind': 'CODEX_REVIEWED', 'document_file': str(path)}


def codex_review_of(bound, directory=None, form='BOUND_SET'):
    """The gates-file member of A1 section 8 for a bound set: a synthetic document that cites this set's request hash and
    final payload hash (form BOUND_SET)."""
    state = b.signed_state(bound)
    path = Path(directory or Path(bound).parent) / ('CODEX_REVIEW.%s.synthetic.txt' % Path(bound).name)
    if not path.exists():
        path.write_text('SYNTHETIC: stands for the written review of the bound set %s: request %s final payload %s\n'
                        % (state['sheet']['label'], state['sheet']['request_sha256'], b.sha(state['payload'])), encoding='utf-8')
    return {'document_file': str(path), 'form': form}


def owner_waiver(directory, copy, operation, at, mode=b.REHEARSAL, name='WAIVER.synthetic.json'):
    """An owner decision record waiving the co-auditor's review of one operation (synthetic, rehearsal owner and channel)."""
    hashes, core = tier_hashes(copy)
    item = [value for value in hashes.values() if value[0] == operation][0]
    record = {'schema': 'OWNER_DECISION_V1', 'owner': b.REAL_OWNER if mode == b.REAL else b.REHEARSAL_OWNER,
              'owner_answer_verbatim': 'Dispenso a revisão (SINTÉTICO)', 'decision': 'WAIVE_CODEX_REVIEW_FOR_ONE_OPERATION',
              'operation': operation, 'seal': item[1], 'source_sha256': item[2],
              'owner_evidence': {'channel': b.REAL_CHANNEL if mode == b.REAL else b.REHEARSAL_CHANNEL, 'signed_at_utc': zulu(at)}}
    path = write(Path(directory) / name, json.dumps(record, sort_keys=True).encode('utf-8'))
    return {'kind': 'OWNER_WAIVED', 'document_file': str(path)}
