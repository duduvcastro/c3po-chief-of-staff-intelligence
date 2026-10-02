"""Capacity-day document tool (c3po/deployment/capacity-day/capacity_day_documents.py).

Synthetic offline documents only. The tool is loaded by path; what it writes is delivered
into private temporary roots and read back by the REAL packaged code: the assembler's
plan and validate_go, validate_contract, DocumentAuthority, CapacityConfig, CapacityLoader
and prepare_capacity_day. No database, no provider, no host, no container.

What is synthetic here: the seven chain documents (signatures and Act B), every hash that
stands for a release, a receipt, an authority or a host fact, the store (in memory), the
release object and the short list of instrument names, which exists only in the payload
file this test assembles the way the host would. The tool never receives that list.
"""
import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_capacity_anchored import AnchoredRoot
from app.r2d2_v2_capacity_authority import calendar_pin, validate_contract
from app.r2d2_v2_capacity_bootstrap import CapacityConfig
from app.r2d2_v2_capacity_bound import DailyCapacityBinding
from app.r2d2_v2_capacity_wiring import build_capacity_collector, prepare_capacity_day
from app.r2d2_v2_document_authority import DocumentAuthority
from app.r2d2_v2_document_format import BEGIN, END, SCHEMA, normalize_document
from app.r2d2_v2_earnings_package import implementation_package_sha
from app.r2d2_v2_epoch_assembler import (DOCUMENT_ORDER_SHA, EPOCH, FIRST_SESSION, REQUIRED_BINDINGS,
                                         RUNTIME_ORDER_SHA, SESSIONS, canonical, digest, plan, validate_go)
from app.r2d2_v2_shadow import (EARNINGS_AMENDMENT_SHA, EARNINGS_CLOSED_MANIFEST_SHA, current_contract_sha,
                                current_package_sha)
from app.r2d2_v2_store import MemoryShadowStore, digest as store_digest

DIRECTORY = Path(__file__).resolve().parents[2] / 'deployment' / 'capacity-day'
SCRIPT = DIRECTORY / 'capacity_day_documents.py'
README = DIRECTORY / 'README.documents.md'


def load_tool():
    spec = importlib.util.spec_from_file_location('capacity_day_documents_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def h(label):
    """A synthetic SHA-256 that no reader could take for a real pin of this epoch."""
    return hashlib.sha256(('synthetic:' + label).encode()).hexdigest()


PACKAGE = implementation_package_sha()
RELEASE_SHA = h('release')
REVISION = h('revision')[:40]
ORDER = {'owner_sha': h('owner'), 'epoch': EPOCH, 'authorized_sessions': list(SESSIONS), 'capacity': 550}
POLICY = {'schema': 'R2D2_V2_LIVE_POLICY_V1', 'mode': 'LIVE', 'epoch': EPOCH, 'capacity': 550,
          'order_sha': RUNTIME_ORDER_SHA, 'release_sha': RELEASE_SHA, 'package_sha': PACKAGE,
          'code_revision': REVISION, 'c8_receipt_sha': h('c8'), 'head_go_sha': h('head'),
          'valid_from': '2026-10-05T13:00:00+00:00', 'valid_until': '2026-10-09T21:00:00+00:00'}
WINDOWS = [{'name': 'primary', 'start_not_before': '06:15:00', 'view_opens_at': '06:30:00'},
           {'name': 'contingency_1', 'start_not_before': '07:15:00', 'view_opens_at': '07:30:00'},
           {'name': 'contingency_2', 'start_not_before': '08:15:00', 'view_opens_at': '08:30:00'}]
WINDOW_NAMES = [window['name'] for window in WINDOWS]
# Instrument-shaped names that exist only in the payload file assembled by this test.
SYMBOLS = ['ZZQB', 'ZZQA', 'ZZQ.C', 'ZZQ-D']
DAY_FILES = ('template', 'go_admission_record', 'go_bar_manifest_record', 'publication_bar_manifest',
             'go_admission', 'go_bar_manifest', 'contract')


_CALENDAR = []


def shared_calendar():
    if not _CALENDAR:
        _CALENDAR.append(ShadowCalendar())
    return _CALENDAR[0]


@pytest.fixture(scope='module')
def calendar():
    return shared_calendar()


def evidence(kind, body):
    payload = canonical({'schema': SCHEMA, 'kind': kind, 'state': 'ISSUED', 'body': body}).decode()
    return f'# {kind}\n{BEGIN}\n```json\n{payload}\n```\n{END}\n'.encode()


def scope():
    return {'epoch': EPOCH, 'first_session': FIRST_SESSION, 'authorized_sessions': list(SESSIONS)}


def run(*argv):
    """One invocation of the tool's main(): exit status and the single JSON line it printed."""
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = tool.main([str(item) for item in argv])
    lines = out.getvalue().splitlines()
    assert len(lines) == 1 and err.getvalue() == ''
    return code, json.loads(lines[0])


def write_json(path, value):
    path.write_bytes(json.dumps(value, indent=1, sort_keys=True).encode() + b'\n')
    return path


def tree(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in sorted(Path(directory).rglob('*')) if path.is_file()}


def signed_chain(templates, *, order=ORDER, policy=POLICY):
    """Seven synthetic chain documents. Act B carries the template map printed by the tool."""
    files, pins = {}, {}

    def put(label, raw):
        name = 'chain.' + label.lower() + '.md'
        files[name] = raw
        pins[label] = {'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous,
                'document_sha256': DOCUMENT_ORDER_SHA, **scope()}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino a ordem.', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:00:00+00:00'}
        put(role, evidence('APPROVAL', body))
        previous = pins[role]['sha256']
    act = {'status': 'ACCEPTED', 'chain_head': pins['DUDU']['sha256'], 'order_sha': digest(order),
           'template_shas': templates['template_shas'], 'policy_sha': digest(policy), 'capacity': 550,
           'cut_rule': templates['cut_rule'], 'subphases': {}, 'individual_go_issuers': ['FABLE'],
           'owner_countersign_phases': ['bar_merge_deploy_recertify', 'install_release', 'activate', 'wind_down_28'],
           'rollback_disposition': 'REVALIDATE_UNCOMMITTED_ONLY', **scope(),
           'causal_order': {'primary': 'ADV_DESC', 'tie_break': 'SYMBOL_ASC', 'cut': 'TAIL_NEW_ONLY'},
           'policy_epoch_validity': True, 'automatic_retry': False, 'document_order_sha': DOCUMENT_ORDER_SHA,
           'act_a_scope_map': {role: {'signature_sha': pins[role]['sha256'], 'document_sha256': DOCUMENT_ORDER_SHA,
                                      **scope()} for role in ('CODEX', 'FABLE', 'DUDU')},
           'templates': templates['templates'], 'template_set_sha': templates['template_set_sha']}
    put('ACT_B', evidence('ACT_B', act))
    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous, **scope(),
                'body_sha': pins['ACT_B']['sha256'], 'act_a_head': pins['DUDU']['sha256']}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino o ato B', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:30:00+00:00'}
        put('B_' + role, evidence('APPROVAL', body))
        previous = pins['B_' + role]['sha256']
    return files, pins


@pytest.fixture(scope='module')
def templates(tmp_path_factory):
    base = tmp_path_factory.mktemp('templates')
    code, line = run('templates', '--order-file', write_json(base / 'order.json', ORDER),
                     '--output-directory', base / 'out')
    assert (code, line['status'], line['kind']) == (0, 'WRITTEN', 'ACT_B_TEMPLATES')
    body = json.loads((base / 'out' / 'ACT_B_TEMPLATES.json').read_bytes())
    assert line['template_set_sha'] == body['template_set_sha'] and line['order_sha'] == digest(ORDER)
    return body


@pytest.fixture(scope='module')
def chain(templates):
    return signed_chain(templates)


def image_receipt():
    """The line the calendar-pin script prints in the image; here, what this interpreter computes."""
    return {'status': 'CALENDAR_PIN', 'epoch': EPOCH, 'calendar_version': shared_calendar().version,
            'calendar_pin_sha': calendar_pin(shared_calendar(), {'authorized_sessions': list(SESSIONS)}),
            'package_sha': PACKAGE, 'document_order_sha': DOCUMENT_ORDER_SHA}


def static_inputs(epoch):
    """What exists on the weekend: the config part of the epoch inputs and nothing of the dispatch or D11."""
    return {**{key: epoch[key] for key in tool.STATIC_KEYS}, 'schema': 'R2D2_CAPACITY_DAY_STATIC_INPUTS_V1'}


def epoch_inputs(pins, roots=None):
    capacity = roots or {'config': {'path': '/c3po-capacity/config'},
                         **{name: {'path': '/c3po-capacity/' + name, 'identity': h('identity:' + name)}
                            for name in ('documents', 'payload', 'go')}}
    parent = os.path.dirname(capacity['config']['path'])
    return {
        'schema': 'R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1', 'order': ORDER, 'policy': POLICY,
        'policy_sha': digest(POLICY), 'release_sha': RELEASE_SHA, 'package_sha': PACKAGE,
        'calendar_pin_receipt': image_receipt(),
        'act_b_sha256': pins['ACT_B']['sha256'], 'chain_pins': pins, 'capacity_roots': capacity,
        'd11': {'recertification_receipt_sha': h('recertification'), 'wind_down_28_receipt_sha': h('wind-down-28'),
                'input_receipts_sha': h('input-receipts'),
                'quote_refresh': {'not_before': '09:25:00', 'not_after': '16:00:00'},
                'quote_capture': {'not_before': '09:55:00', 'not_after': '10:05:00'}},
        'phase_windows': {'admission': {'not_before': '06:15:00', 'not_after': '09:20:00'},
                          'bar_manifest': {'not_before': '06:15:00', 'not_after': '09:20:00'}},
        'd4_view_mode': 'PRE_DELIVERED', 'd6_windows': WINDOWS, 'view_valid_seconds': 10, 'max_wait_seconds': 900,
        'dispatch': {
            'authority_sha256': h('authority-a2'), 'payload_sha256': h('host-payload'),
            'writer_sha256': h('writer'), 'writer_require_go_mode': 'NOT_REQUIRED',
            'image_id': 'sha256:' + h('image'), 'build_sha': REVISION,
            'network': 'c3po_internal', 'host_binding_sha256': h('host-binding'),
            'pins_env': {'path': '/etc/c3po-reader/pins.env', 'sha256': h('pins-env')},
            'secret_env_path': '/etc/c3po-reader/secret.env', 'docker_config': '/etc/c3po-reader/docker-cli',
            'manifest_directory': '/etc/c3po-bar/manifests',
            'mounts': [{'source': '/mnt/day-d-data', 'target': '/app/day-d-data', 'readonly': True},
                       {'source': '/srv/c3po-capacity', 'target': parent, 'readonly': True},
                       {'source': '/etc/c3po-bar/manifests', 'target': '/etc/c3po-bar/manifests',
                        'readonly': False}]}}


def session_inputs(day):
    eve = datetime.fromisoformat(day + 'T01:30:00+00:00')       # 21:30 New York on the evening before
    return {'schema': 'R2D2_CAPACITY_DAY_SESSION_INPUTS_V1', 'day': day,
            'causal_scope': {'commitment_sha256': h('commitment:' + day), 'list_sha256': store_digest(SYMBOLS)},
            'bar_manifest_published_at': eve.isoformat(),
            'view_evidence_sha': {name: h('view-evidence:' + day + ':' + name) for name in WINDOW_NAMES}}


def copy(value):
    return json.loads(json.dumps(value))


def raw_sha(data):
    return hashlib.sha256(data).hexdigest()


EMPTY_INPUT = raw_sha(b'')                  # what `cat absent | shasum -a 256` prints


def relist(out):
    """Someone who changed a file and wrote SHA256SUMS again."""
    (out / 'SHA256SUMS').write_bytes(tool.sums({name: raw for name, raw in tree(out).items() if name != 'SHA256SUMS'}))


def change_json(out, path, edit):
    body = json.loads((out / path).read_bytes())
    edit(body)
    (out / path).write_bytes(canonical(body))
    return body


class World:
    """A private capacity tree on this machine, laid out like the one bound at /c3po-capacity."""

    def __init__(self, base, chain, *, edit=None):
        self.base = Path(os.path.realpath(base))
        self.chain_files, self.pins = chain
        self.capacity = self.base / 'capacity'
        self.capacity.mkdir(mode=0o700)
        roots = {'config': {'path': str(self.capacity / 'config')}}
        for name in ('config', 'documents', 'payload', 'go'):
            (self.capacity / name).mkdir(mode=0o700)
            if name != 'config':
                anchored = AnchoredRoot(self.capacity / name)
                roots[name] = {'path': str(self.capacity / name), 'identity': anchored.identity}
                anchored.close()
        self.epoch = copy(epoch_inputs(self.pins, roots))
        if edit is not None:
            edit(self.epoch)
        self.inputs = self.base / 'inputs'
        self.inputs.mkdir()
        self.chain_directory = self.base / 'chain'
        self.chain_directory.mkdir()
        for name, raw in self.chain_files.items():
            (self.chain_directory / name).write_bytes(raw)

    def build(self, day, window, *, name=None, chained=True, session=None):
        out = self.base / (name or 'out-' + day + '-' + window)
        argv = ['day', '--epoch-inputs', write_json(self.inputs / 'epoch.json', self.epoch),
                '--session-inputs', write_json(self.inputs / (day + '.json'), session or session_inputs(day)),
                '--window', window, '--output-directory', out]
        argv += ['--chain-directory', self.chain_directory] if chained else ['--draft-without-chain']
        code, line = run(*argv)
        return code, line, out

    @staticmethod
    def private(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def deliver_chain(self):
        for name, raw in self.chain_files.items():
            self.private(self.capacity / 'documents' / name, raw)

    def deliver(self, out, day):
        """The evening delivery, and the payload file assembled where the list lives."""
        summary = json.loads((out / 'SUMMARY.json').read_bytes())
        self.deliver_chain()
        for role, path in summary['roles'].items():
            folder, name = path.split('/')
            if folder in ('documents', 'emitter'):
                self.private(self.capacity / 'documents' / name, (out / path).read_bytes())
            elif folder in ('go', 'config'):
                self.private(self.capacity / folder / name, (out / path).read_bytes())
        contract = json.loads((out / summary['roles']['contract']).read_bytes())
        causal = {'epoch': EPOCH, 'session': day, 'status': 'AVAILABLE', 'symbols': list(SYMBOLS),
                  'list_sha256': store_digest(SYMBOLS), 'commitment_sha256': h('commitment:' + day)}
        assert contract['causal_scope'] == {key: causal[key] for key in
                                            ('epoch', 'session', 'commitment_sha256', 'list_sha256')}
        self.private(self.capacity / 'payload' / ('session=' + day + '.json'),
                     canonical({'contract': contract, 'causal': causal}))
        return summary, contract, causal

    def settings(self, summary, *, sha=None):
        name = summary['roles']['capacity_config'].split('/')[1]
        return SimpleNamespace(r2d2_v2_capacity_config_file=str(self.capacity / 'config' / name),
                               r2d2_v2_capacity_config_sha=sha or summary['hashes']['capacity_config_sha256'],
                               r2d2_v2_capacity_veto_mode='DISPATCH_AND_DERIVATION_ONLY',
                               r2d2_v2_shadow_release_sha=RELEASE_SHA)


def release():
    return SimpleNamespace(
        epoch=EPOCH, mode='CERTIFIED', first_session=date.fromisoformat(FIRST_SESSION), receipt_sha=RELEASE_SHA,
        code_revision=REVISION, readiness_sha=h('readiness'), ebar_amendment_sha=None,
        earnings_amendment_sha=EARNINGS_AMENDMENT_SHA, earnings_closed_manifest_sha=EARNINGS_CLOSED_MANIFEST_SHA,
        implementation_contract_sha=current_contract_sha(), implementation_package_sha=current_package_sha())


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def prepare(world, summary, calendar, clock, *, sha=None):
    """The real path of prepare-capacity-day: CapacityConfig, CapacityLoader, the packaged transaction."""
    config = CapacityConfig(world.settings(summary, sha=sha), clock=clock)
    try:
        store = MemoryShadowStore()
        collector = build_capacity_collector(store=store, source=object(), release=release(), calendar=calendar,
                                             config=config.collector_config(release(), store))
        result = prepare_capacity_day(store, collector, summary['day'])
        return config, store, result
    except BaseException:
        config.close()
        raise


def bar_gate(config, contract, day, clock):
    """The bar_manifest gate as the writer runs it: GO from the go root, plan from the binding."""
    go = config.roots['go'].json('session=' + day + '.bar_manifest.json')['go']
    return validate_go(go, contract['consumer_plans']['bar_manifest'], now=clock(),
                       authority_verifier=lambda g, p: config.authority.verify_go(g, p, clock()))


def code_of(call):
    with pytest.raises(ValueError) as error:
        call()
    return str(error.value)


# ---- round trip through the packaged code, five sessions by three windows -----------------------

@pytest.mark.parametrize('window', WINDOW_NAMES)
@pytest.mark.parametrize('day', SESSIONS)
def test_output_passes_the_packaged_plan_go_authority_and_config(day, window, tmp_path, chain, calendar):
    world = World(tmp_path, chain)
    code, line, out = world.build(day, window)
    assert (code, line['status'], line['documentary_authority']) == (0, 'WRITTEN', 'VERIFIED')
    summary, contract, causal = world.deliver(out, day)
    assert line['capacity_config_sha256'] == summary['hashes']['capacity_config_sha256']
    assert line['sha256sums_sha256'] == hashlib.sha256((out / 'SHA256SUMS').read_bytes()).hexdigest()
    opens = datetime.fromisoformat(summary['clocks']['view_opens_at'])
    assert opens == datetime.fromisoformat(day + 'T' + WINDOWS[WINDOW_NAMES.index(window)]['view_opens_at']
                                           + '-04:00')
    clock = Clock(opens + timedelta(seconds=2))

    # plan: every plan in the contract is what the real assembler computes from its own bindings.
    identity = contract['assembler_plan']['proposal']['identity']
    plans = {'admission': contract['assembler_plan'], **contract['consumer_plans']}
    assert set(plans) == set(tool.PHASES)
    for phase, stored in plans.items():
        bindings = stored['proposal']['bindings']
        assert set(bindings) == set(REQUIRED_BINDINGS) and stored['status'] == 'BOUND_FOR_REVIEW_ONLY'
        fresh = plan(identity, day=day, phase=phase, bindings=bindings, policy=contract['policy'],
                     calendar=calendar, consumer_binding=stored['proposal']['consumer_capacity_binding'])
        assert fresh == stored and stored['proposal_sha'] == summary['hashes']['proposal_sha'][phase]
        assert (bindings['recertification_receipt_sha'], bindings['wind_down_28_receipt_sha'],
                bindings['input_receipts_sha']) == (h('recertification'), h('wind-down-28'), h('input-receipts'))
    assert validate_contract(contract, release=release(), day=day, causal=causal, calendar=calendar) == contract

    # CapacityConfig on anchored private roots, then the packaged prepare-capacity-day transaction.
    config, store, result = prepare(world, summary, calendar, clock)
    try:
        assert isinstance(config.authority, DocumentAuthority) and config.sha == line['capacity_config_sha256']
        assert result['status'] == 'COMMITTED'
        committed = store.read(EPOCH)['state']['daily_capacity'][day]
        assert committed['sha'] == result['sha'] and committed['document']['contract'] == contract
        assert committed['document']['monitored_symbols'] == sorted(SYMBOLS)
        # validate_go + DocumentAuthority for both phases, with the GO files read from the go root.
        admission = config.roots['go'].json('session=' + day + '.admission.json')['go']
        checked = validate_go(admission, contract['assembler_plan'], now=clock(),
                              authority_verifier=lambda g, p: config.authority.verify_go(g, p, clock()))
        assert checked['go_sha'] == summary['hashes']['admission_go_sha256'] and admission['mode'] == 'INDIVIDUAL'
        assert bar_gate(config, committed['document']['contract'], day, clock)['go_sha'] \
            == summary['hashes']['bar_manifest_go_sha256']
        assert config.authority.verify_binding(committed['document'], clock()) is True
        restored = DailyCapacityBinding.restore(committed, release=release(), calendar=calendar,
                                                authority_verifier=lambda doc: config.authority.verify_binding(doc, clock()))
        assert restored.sha == committed['sha']
        # One second after the view closes the same GO is refused: the view is the window's own.
        clock.now = opens + timedelta(seconds=11)
        assert code_of(lambda: bar_gate(config, contract, day, clock)) == 'AUTHORITY_UNVERIFIED_OR_VETOED'
    finally:
        config.close()
    for raw in tree(out).values():
        assert not any(name.encode() in raw for name in SYMBOLS)
    assert not any(name in json.dumps(line) for name in SYMBOLS)


def test_template_map_is_accepted_by_the_packaged_act_b(templates, chain):
    files, pins = chain
    body = normalize_document('ACT_B', files[pins['ACT_B']['file']])
    assert body['template_shas'] == templates['template_shas'] and set(body['template_shas']) == set(SESSIONS)
    authority = DocumentAuthority(root=SimpleNamespace(read=lambda name: files[name]), pins=pins)
    now = datetime.fromisoformat('2026-10-05T10:30:00+00:00')
    for day in SESSIONS:
        assert authority.act_b(now, day=day)['template_shas'][day] == digest(templates['contract_templates'][day])
        assert [entry for entry in body['templates'] if entry['authorized_sessions'] == [day]] \
            == [{'sha': templates['template_shas'][day], 'epoch': EPOCH, 'first_session': FIRST_SESSION,
                 'authorized_sessions': [day], 'phases': list(tool.PHASES)}]
    assert templates['order_sha'] == digest(ORDER) == store_digest(ORDER)


# ---- determinism --------------------------------------------------------------------------------

def test_two_runs_are_byte_identical_and_day_files_do_not_depend_on_the_window(tmp_path, chain):
    world = World(tmp_path, chain)
    trees = {}
    for window in WINDOW_NAMES:
        for attempt in ('a', 'b'):
            code, line, out = world.build(SESSIONS[0], window, name=window + '-' + attempt)
            assert code == 0
            trees[window, attempt] = tree(out)
        assert trees[window, 'a'] == trees[window, 'b']
    summaries = {window: json.loads(trees[window, 'a']['SUMMARY.json']) for window in WINDOW_NAMES}
    for role in DAY_FILES:
        versions = {trees[window, 'a'][summaries[window]['roles'][role]] for window in WINDOW_NAMES}
        assert len(versions) == 1
    for role in ('veto_view', 'capacity_config', 'request', 'dispatch_go'):
        assert len({trees[window, 'a'][summaries[window]['roles'][role]] for window in WINDOW_NAMES}) == 3
    first = trees['primary', 'a']
    assert sorted(first) == sorted(set(summaries['primary']['roles'].values()) | {'SUMMARY.json', 'SHA256SUMS'})
    listed = dict(reversed(row.split('  ')) for row in first['SHA256SUMS'].decode().splitlines())
    assert listed == {path: hashlib.sha256(raw).hexdigest() for path, raw in first.items() if path != 'SHA256SUMS'}
    for path, raw in first.items():
        if path.endswith('.json'):
            assert raw == canonical(json.loads(raw)) and not raw.endswith(b'\n')


# ---- refusals: a required input that is missing or malformed ------------------------------------

def refused(tmp_path, chain, *, edit=None, session=None, window='primary', day=SESSIONS[0], chained=False):
    world = World(tmp_path, chain, edit=edit)
    inputs = session_inputs(day)
    if session is not None:
        session(inputs)
    code, line, out = world.build(day, window, chained=chained, session=inputs)
    assert not out.exists()
    assert set(line) == {'status', 'code'}
    return code, line['status'], line['code']


@pytest.mark.parametrize('key', sorted(tool.EPOCH_KEYS))
def test_every_epoch_input_is_required(key, tmp_path, chain):
    assert refused(tmp_path, chain, edit=lambda e: e.pop(key)) == (3, 'REFUSED', 'DOCUMENTS_EPOCH_FIELDS')


@pytest.mark.parametrize('key', sorted(tool.SESSION_KEYS))
def test_every_session_input_is_required(key, tmp_path, chain):
    assert refused(tmp_path, chain, session=lambda s: s.pop(key)) == (3, 'REFUSED', 'DOCUMENTS_SESSION_FIELDS')


def test_no_input_has_a_default(tmp_path, chain):
    world = World(tmp_path, chain)
    body = world.epoch
    for key in sorted(tool.EPOCH_KEYS):
        for value in (None, ''):
            world.epoch = {**body, key: value}
            code, line, out = world.build(SESSIONS[0], 'primary', chained=False)
            assert (code, line['status']) == (3, 'REFUSED') and not out.exists()
    world.epoch = {**body, 'unexpected': 1}
    code, line, out = world.build(SESSIONS[0], 'primary', chained=False)
    assert (code, line['code']) == (3, 'DOCUMENTS_EPOCH_FIELDS') and not out.exists()
    inputs = session_inputs(SESSIONS[0])
    world.epoch = body
    for key in sorted(tool.SESSION_KEYS):
        for value in (None, ''):
            code, line, out = world.build(SESSIONS[0], 'primary', chained=False, session={**inputs, key: value})
            assert (code, line['status']) == (3, 'REFUSED') and not out.exists()


def set_at(*path, value):
    def edit(body):
        for key in path[:-1]:
            body = body[key]
        if value is KeyError:
            del body[path[-1]]
        else:
            body[path[-1]] = value
    return edit


MALFORMED_EPOCH = [
    (('d11', 'recertification_receipt_sha'), None, 'DOCUMENTS_INPUT_RECERTIFICATION_RECEIPT_SHA'),
    (('d11', 'wind_down_28_receipt_sha'), 'A' * 64, 'DOCUMENTS_INPUT_WIND_DOWN_28_RECEIPT_SHA'),
    (('d11', 'input_receipts_sha'), '6' * 64, 'DOCUMENTS_INPUT_INPUT_RECEIPTS_SHA'),      # one digit, 64 times
    (('d11', 'recertification_receipt_sha'), EMPTY_INPUT, 'DOCUMENTS_INPUT_RECERTIFICATION_RECEIPT_SHA'),
    (('d11', 'wind_down_28_receipt_sha'), raw_sha(b'\n'), 'DOCUMENTS_INPUT_WIND_DOWN_28_RECEIPT_SHA'),
    (('d11', 'input_receipts_sha'), 'deadbeef' * 8, 'DOCUMENTS_INPUT_INPUT_RECEIPTS_SHA'),
    (('d11', 'input_receipts_sha'), '0123456789abcdef' * 4, 'DOCUMENTS_INPUT_INPUT_RECEIPTS_SHA'),
    (('d11', 'quote_refresh'), {'phase_window_sha': EMPTY_INPUT}, 'DOCUMENTS_INPUT_D11_PHASE_WINDOW_SHA'),
    (('release_sha',), raw_sha(b'[]'), 'DOCUMENTS_INPUT_RELEASE_SHA'),
    (('capacity_roots', 'go', 'identity'), raw_sha(b'null'), 'DOCUMENTS_INPUT_CAPACITY_ROOT_IDENTITY'),
    (('chain_pins', 'CODEX', 'sha256'), raw_sha(b'{}\n'), 'DOCUMENTS_INPUT_CHAIN_PINS'),
    (('dispatch', 'pins_env', 'sha256'), EMPTY_INPUT, 'DOCUMENTS_INPUT_DISPATCH_PINS_ENV'),
    (('dispatch', 'image_id'), 'sha256:' + EMPTY_INPUT, 'DOCUMENTS_INPUT_DISPATCH_IMAGE_ID'),
    (('dispatch', 'payload_sha256'), raw_sha(b'{}'), 'DOCUMENTS_INPUT_DISPATCH_PAYLOAD_SHA256'),
    (('dispatch', 'host_binding_sha256'), raw_sha(b'""'), 'DOCUMENTS_INPUT_DISPATCH_HOST_BINDING_SHA256'),
    (('dispatch', 'writer_require_go_mode'), 'INDIVIDUAL', 'DOCUMENTS_INPUT_DISPATCH_WRITER_REQUIRE_GO_MODE'),
    (('dispatch', 'writer_require_go_mode'), None, 'DOCUMENTS_INPUT_DISPATCH_WRITER_REQUIRE_GO_MODE'),
    (('d11', 'input_receipts_sha'), KeyError, 'DOCUMENTS_INPUT_D11'),
    (('d11', 'quote_refresh'), {'not_before': '09:25:00'}, 'DOCUMENTS_INPUT_D11_PHASE_WINDOW'),
    (('d11', 'quote_capture'), {'not_before': '10:05:00', 'not_after': '09:55:00'},
     'DOCUMENTS_INPUT_D11_PHASE_WINDOW'),
    (('d11', 'quote_capture'), {'phase_window_sha': '0' * 64}, 'DOCUMENTS_INPUT_D11_PHASE_WINDOW_SHA'),
    (('d4_view_mode',), 'AUTO', 'DOCUMENTS_INPUT_D4_VIEW_MODE'),
    (('d6_windows',), [], 'DOCUMENTS_INPUT_D6_WINDOWS'),
    (('d6_windows', 0, 'view_opens_at'), '6:30', 'DOCUMENTS_INPUT_D6_WINDOWS'),
    (('d6_windows', 0, 'view_opens_at'), '2026-10-05T10:30:00+00:00', 'DOCUMENTS_INPUT_D6_WINDOWS'),
    (('d6_windows', 0, 'name'), 'PRIMARY', 'DOCUMENTS_INPUT_D6_WINDOWS'),
    (('d6_windows', 1, 'name'), 'primary', 'DOCUMENTS_INPUT_D6_WINDOWS'),
    (('d6_windows', 0, 'start_not_before'), '06:14:59', 'DOCUMENTS_WINDOW_WAIT'),
    (('d6_windows', 0), {'name': 'primary', 'start_not_before': '07:00:01', 'view_opens_at': '07:14:55'},
     'DOCUMENTS_WINDOWS_OVERLAP'),
    (('d6_windows', 2, 'view_opens_at'), '09:19:55', 'DOCUMENTS_WINDOW_WAIT'),
    (('d6_windows', 2), {'name': 'contingency_2', 'start_not_before': '09:10:00', 'view_opens_at': '09:19:55'},
     'DOCUMENTS_VIEW_OUTSIDE_PHASE_WINDOW'),
    (('phase_windows', 'admission', 'not_before'), '09:30:01', 'DOCUMENTS_INPUT_PHASE_WINDOWS'),
    (('phase_windows', 'bar_manifest', 'not_before'), '06:30:01', 'DOCUMENTS_VIEW_OUTSIDE_PHASE_WINDOW'),
    (('phase_windows', 'bar_manifest'), {'not_before': '06:15:00'}, 'DOCUMENTS_INPUT_PHASE_WINDOWS'),
    (('view_valid_seconds',), 11, 'DOCUMENTS_INPUT_VIEW_VALID_SECONDS'),
    (('view_valid_seconds',), True, 'DOCUMENTS_INPUT_VIEW_VALID_SECONDS'),
    (('max_wait_seconds',), 901, 'DOCUMENTS_INPUT_MAX_WAIT_SECONDS'),
    (('release_sha',), h('another release'), 'DOCUMENTS_POLICY_SCOPE'),
    (('release_sha',), 'unbound', 'DOCUMENTS_INPUT_RELEASE_SHA'),
    (('policy_sha',), h('another policy'), 'DOCUMENTS_POLICY_HASH'),
    (('package_sha',), h('another package'), 'DOCUMENTS_POLICY_SCOPE'),
    (('act_b_sha256',), h('another act b'), 'DOCUMENTS_ACT_B_HASH'),
    (('calendar_pin_receipt', 'calendar_pin_sha'), h('the pin of another calendar library version'),
     'DOCUMENTS_CALENDAR_PIN'),
    (('calendar_pin_receipt', 'calendar_version'), '0.0', 'DOCUMENTS_CALENDAR_PIN'),
    (('calendar_pin_receipt', 'package_sha'), h('the package of another image'), 'DOCUMENTS_CALENDAR_RECEIPT'),
    (('calendar_pin_receipt', 'document_order_sha'), h('another order'), 'DOCUMENTS_CALENDAR_RECEIPT'),
    (('calendar_pin_receipt', 'status'), 'CALENDAR_PIN_REFUSED', 'DOCUMENTS_CALENDAR_RECEIPT'),
    (('calendar_pin_receipt', 'calendar_version'), KeyError, 'DOCUMENTS_INPUT_CALENDAR_PIN_RECEIPT'),
    (('calendar_pin_receipt',), h('the pin alone, without the line it came in'), 'DOCUMENTS_INPUT_CALENDAR_PIN_RECEIPT'),
    (('chain_pins', 'B_DUDU'), KeyError, 'DOCUMENTS_INPUT_CHAIN_PINS'),
    (('chain_pins', 'ACT_B', 'file'), '../act-b.md', 'DOCUMENTS_INPUT_CHAIN_PINS'),
    (('capacity_roots', 'go', 'identity'), None, 'DOCUMENTS_INPUT_CAPACITY_ROOT_IDENTITY'),
    (('capacity_roots', 'payload', 'path'), 'c3po-capacity/payload', 'DOCUMENTS_INPUT_CAPACITY_ROOTS'),
    (('capacity_roots', 'payload', 'path'), '/outside/payload', 'DOCUMENTS_DISPATCH_CAPACITY_MOUNT'),
    (('order', 'capacity'), 551, 'DOCUMENTS_ORDER_SCOPE'),
    (('order', 'owner_sha'), 'a' * 64, 'DOCUMENTS_INPUT_ORDER_OWNER_SHA'),
    (('order', 'note'), 'café', 'DOCUMENTS_INPUT_NOT_ASCII'),
    (('order', 'weight'), 0.5, 'DOCUMENTS_INPUT_JSON'),
    (('dispatch', 'image_id'), 'c3po/backend:production', 'DOCUMENTS_INPUT_DISPATCH_IMAGE_ID'),
    (('dispatch', 'build_sha'), 'f' * 40, 'DOCUMENTS_BUILD_REVISION'),
    (('dispatch', 'network'), 'host', 'DOCUMENTS_INPUT_DISPATCH_NETWORK'),
    (('dispatch', 'authority_sha256'), None, 'DOCUMENTS_INPUT_DISPATCH_AUTHORITY_SHA256'),
    (('dispatch', 'writer_sha256'), KeyError, 'DOCUMENTS_INPUT_DISPATCH'),
    (('dispatch', 'mounts', 0, 'readonly'), False, 'DOCUMENTS_DISPATCH_WRITABLE_MOUNT'),
    (('dispatch', 'manifest_directory'), '/etc/c3po-bar', 'DOCUMENTS_DISPATCH_WRITABLE_MOUNT'),
]


@pytest.mark.parametrize('path,value,expected', MALFORMED_EPOCH, ids=[
    '.'.join(str(part) for part in row[0]) + '=' + str(index) for index, row in enumerate(MALFORMED_EPOCH)])
def test_malformed_epoch_input_is_refused_and_nothing_is_written(path, value, expected, tmp_path, chain):
    assert refused(tmp_path, chain, edit=set_at(*path, value=value)) == (3, 'REFUSED', expected)


MALFORMED_SESSION = [
    (('day',), '2026-10-12', 'DOCUMENTS_DAY_NOT_AUTHORIZED'),
    (('day',), '2026-10-04', 'DOCUMENTS_DAY_NOT_AUTHORIZED'),
    (('causal_scope', 'list_sha256'), None, 'DOCUMENTS_INPUT_CAUSAL_LIST_SHA256'),
    (('causal_scope', 'commitment_sha256'), '9' * 64, 'DOCUMENTS_INPUT_CAUSAL_COMMITMENT_SHA256'),
    (('causal_scope', 'symbols'), ['ZZQA'], 'DOCUMENTS_INPUT_CAUSAL_SCOPE'),
    (('bar_manifest_published_at',), '2026-10-05T10:01:00+00:00', 'DOCUMENTS_GO_NOTICE'),       # 14 minutes
    (('bar_manifest_published_at',), '2026-09-28T01:30:00+00:00', 'DOCUMENTS_GO_NOTICE'),       # a week early
    (('bar_manifest_published_at',), '2026-10-04 21:30', 'DOCUMENTS_INPUT_BAR_MANIFEST_PUBLISHED_AT'),
    (('bar_manifest_published_at',), '2026-10-04T21:30:00-04:00', 'DOCUMENTS_INPUT_BAR_MANIFEST_PUBLISHED_AT'),
    (('view_evidence_sha', 'contingency_2'), KeyError, 'DOCUMENTS_INPUT_VIEW_EVIDENCE_SHA'),
    (('view_evidence_sha', 'primary'), 'b' * 64, 'DOCUMENTS_INPUT_VIEW_EVIDENCE_SHA'),
    (('view_evidence_sha', 'primary'), EMPTY_INPUT, 'DOCUMENTS_INPUT_VIEW_EVIDENCE_SHA'),
    (('causal_scope', 'commitment_sha256'), EMPTY_INPUT, 'DOCUMENTS_INPUT_CAUSAL_COMMITMENT_SHA256'),
    (('causal_scope', 'list_sha256'), raw_sha(b'[]\n'), 'DOCUMENTS_INPUT_CAUSAL_LIST_SHA256'),
    (('causal_scope', 'list_sha256'), h('commitment:' + SESSIONS[0]), 'DOCUMENTS_INPUT_HASH_REUSED'),
    (('causal_scope', 'commitment_sha256'), RELEASE_SHA, 'DOCUMENTS_INPUT_HASH_REUSED'),
]


@pytest.mark.parametrize('path,value,expected', MALFORMED_SESSION, ids=[
    '.'.join(row[0]) + '=' + str(index) for index, row in enumerate(MALFORMED_SESSION)])
def test_malformed_session_input_is_refused_and_nothing_is_written(path, value, expected, tmp_path, chain):
    assert refused(tmp_path, chain, session=set_at(*path, value=value)) == (3, 'REFUSED', expected)


def late_admission(e):
    e['phase_windows']['admission'] = {'not_before': '09:30:01', 'not_after': '09:45:00'}


def view_after_cutoff(e):
    for phase in ('admission', 'bar_manifest'):
        e['phase_windows'][phase]['not_after'] = '09:30:00'
    e['d6_windows'][2] = {'name': 'contingency_2', 'start_not_before': '09:10:00', 'view_opens_at': '09:19:55'}


def same_quote_windows(e):
    e['d11']['quote_refresh'] = e['d11']['quote_capture'] = {'phase_window_sha': h('one window for two phases')}


@pytest.mark.parametrize('edit,expected', [(late_admission, 'DOCUMENTS_ADMISSION_WINDOW_LATE'),
                                           (view_after_cutoff, 'DOCUMENTS_VIEW_AFTER_CUTOFF'),
                                           (same_quote_windows, 'DOCUMENTS_PHASE_WINDOWS_NOT_DISTINCT')])
def test_windows_the_packaged_code_or_the_writer_would_refuse_are_refused_here(edit, expected, tmp_path, chain):
    assert refused(tmp_path, chain, edit=edit) == (3, 'REFUSED', expected)


def with_policy(**changes):
    def edit(e):
        e['policy'].update(changes)
        e['policy_sha'] = digest(e['policy'])
    return edit


def all_d11(e):
    for key in ('recertification_receipt_sha', 'wind_down_28_receipt_sha', 'input_receipts_sha'):
        e['d11'][key] = e['release_sha']


REUSED = {
    'the three D11 slots are the release hash': all_d11,
    'two D11 slots are one hash': lambda e: e['d11'].update(wind_down_28_receipt_sha=e['d11']['recertification_receipt_sha']),
    'a D11 slot is the authority hash': lambda e: e['d11'].update(input_receipts_sha=e['dispatch']['authority_sha256']),
    'a D11 window digest is the release hash': lambda e: e['d11'].update(quote_capture={'phase_window_sha': e['release_sha']}),
    'writer and authority': lambda e: e['dispatch'].update(writer_sha256=e['dispatch']['authority_sha256']),
    'pins.env and payload': lambda e: e['dispatch']['pins_env'].update(sha256=e['dispatch']['payload_sha256']),
    'image and release': lambda e: e['dispatch'].update(image_id='sha256:' + e['release_sha']),
    'host binding and Act B': lambda e: e['dispatch'].update(host_binding_sha256=e['act_b_sha256']),
    'the writer hash is this tool': lambda e: e['dispatch'].update(writer_sha256=tool.tool_sha256()),
    'two roots, one identity': lambda e: e['capacity_roots']['go'].update(identity=e['capacity_roots']['payload']['identity']),
    'a root identity is the package hash': lambda e: e['capacity_roots']['go'].update(identity=e['package_sha']),
    'policy receipts are one hash': with_policy(head_go_sha=POLICY['c8_receipt_sha']),
    'a policy receipt is the release hash': with_policy(c8_receipt_sha=RELEASE_SHA),
}


@pytest.mark.parametrize('name', sorted(REUSED))
def test_one_hash_in_two_slots_that_name_different_things_is_refused(name, tmp_path, chain):
    assert refused(tmp_path, chain, edit=REUSED[name]) == (3, 'REFUSED', 'DOCUMENTS_INPUT_HASH_REUSED')


def test_placeholders_in_the_policy_are_refused_and_d11_may_name_a_policy_receipt(tmp_path, chain):
    for name, edit, expected in (
            ('a', with_policy(c8_receipt_sha='a' * 64, head_go_sha='b' * 64), 'DOCUMENTS_INPUT_POLICY_C8_RECEIPT_SHA'),
            ('b', with_policy(head_go_sha=EMPTY_INPUT), 'DOCUMENTS_INPUT_POLICY_HEAD_GO_SHA'),
            ('c', with_policy(c8_receipt_sha='deadbeef' * 8), 'DOCUMENTS_INPUT_POLICY_C8_RECEIPT_SHA')):
        (tmp_path / name).mkdir()
        assert refused(tmp_path / name, chain, edit=edit) == (3, 'REFUSED', expected)
    # D11 is open: the recertification slot may be closed as the receipt the policy already names.
    (tmp_path / 'd').mkdir()
    world = World(tmp_path / 'd', chain,
                  edit=lambda e: e['d11'].update(recertification_receipt_sha=e['policy']['c8_receipt_sha']))
    code, line, out = world.build(SESSIONS[0], 'primary')
    assert (code, line['status'], line['documentary_authority']) == (0, 'WRITTEN', 'VERIFIED')
    # What the guard is: typing and empty commands. A wrong hash that looks real is not told from the right one.
    for value in ('f' * 64, '0' * 63 + '1', 'ab' * 32, 'deadbeef' * 8, '0123456789abcdef' * 4, EMPTY_INPUT,
                  raw_sha(b'\n'), raw_sha(b'[]'), raw_sha(b'{}'), raw_sha(b'null'), 'A' * 64, None, 5):
        with pytest.raises(ValueError) as error:
            tool.real_sha(tool.app(), value, 'X')
        assert str(error.value) == 'DOCUMENTS_INPUT_X'
    assert tool.real_sha(tool.app(), h('any other value'), 'X') == h('any other value')


def test_d12_a_day_with_an_empty_list_is_built_and_says_so(tmp_path, chain, monkeypatch):
    world = World(tmp_path, chain)
    day = SESSIONS[0]
    inputs = session_inputs(day)
    inputs['causal_scope']['list_sha256'] = store_digest([])
    assert store_digest([]) == raw_sha(b'[]')                   # refused in every other slot
    code, line, out = world.build(day, 'primary', name='empty', session=inputs)
    assert (code, line['status'], line['list']) == (0, 'WRITTEN', 'EMPTY')
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    assert summary['list'] == 'EMPTY' and summary['self_check']['contract'] == 'VALIDATED_WITH_EMPTY_LIST'
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory)[1]['list'] == 'EMPTY'
    code, line, out = world.build(day, 'primary', name='full')
    assert (code, line['list']) == (0, 'NOT_EMPTY')
    assert json.loads((out / 'SUMMARY.json').read_bytes())['self_check']['contract'] == 'VALIDATED_UP_TO_LIST_HASH'
    # With a list that is not empty the stand-in MUST fail at the last line; a check that passes is a defect.
    monkeypatch.setattr(tool.app(), 'validate_contract', lambda contract, **_: contract)
    code, line, out = world.build(day, 'primary', name='defect')
    assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SELF_CHECK_CONTRACT'}) and not out.exists()


def test_window_and_arguments_and_existing_output_are_refused(tmp_path, chain):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    assert refused(tmp_path / 'a', chain, window='contingency_3') == (3, 'REFUSED', 'DOCUMENTS_WINDOW_UNKNOWN')
    world = World(tmp_path / 'b', chain)
    code, line, out = world.build(SESSIONS[0], 'primary')
    assert code == 0
    before = tree(out)
    code, line, again = world.build(SESSIONS[0], 'primary')
    assert (code, line, tree(again)) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_OUTPUT_EXISTS'}, before)
    marker = 'postgresql://reader:hunter2@db/c3po'
    day_argv = ['day', '--epoch-inputs', world.inputs / 'epoch.json', '--session-inputs',
                world.inputs / (SESSIONS[0] + '.json'), '--window', 'primary', '--output-directory', tmp_path / 'never']
    order = write_json(tmp_path / 'order.json', ORDER)
    for argv in (['day', '--epoch-inputs', world.inputs / 'epoch.json'], ['day', '--database-url', marker],
                 [], ['publish'], ['verify'], ['-h'], ['--help'], ['day', '-h'], ['templates', '--help'],
                 ['verify', '-h'], ['static-config', '-h'],
                 # no abbreviated option
                 ['templates', '--order', order, '--output', tmp_path / 'never'],
                 ['verify', '--dir', out],
                 # a day is built over the signed chain, or it is asked for as a draft: one of the two, in words
                 day_argv, day_argv + ['--chain-directory', world.chain_directory, '--draft-without-chain'],
                 ['static-config', '--epoch-inputs', world.inputs / 'epoch.json', '--day', SESSIONS[0], '--window',
                  'primary', '--view-evidence-sha', h('x'), '--output-directory', tmp_path / 'never']):
        assert run(*argv) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_ARGUMENTS_INVALID'})
    assert not (tmp_path / 'never').exists()
    # Only the last component of the output path is created; a missing parent has its own code.
    assert run('templates', '--order-file', order, '--output-directory', tmp_path / 'absent' / 'out') \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_OUTPUT_PARENT'})
    assert not (tmp_path / 'absent').exists()
    link = tmp_path / 'order-link.json'
    link.symlink_to(order)
    assert run('templates', '--order-file', link, '--output-directory', tmp_path / 'never') \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_INPUT_FILE'})
    assert run('verify', '--directory', tmp_path / marker.replace('/', '_')) \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_INPUT_FILE'})
    duplicate = world.inputs / 'duplicate.json'
    duplicate.write_bytes(b'{"schema":"x","schema":"R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1"}')
    assert run('day', '--epoch-inputs', duplicate, '--session-inputs', world.inputs / (SESSIONS[0] + '.json'),
               '--window', 'primary', '--output-directory', tmp_path / 'never', '--draft-without-chain') \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_INPUT_JSON'})
    assert not (tmp_path / 'never').exists()


FREE_FORM = {
    # what the reviewer's probes put into the two objects that are copied into the contract
    'order: a list of names': (lambda e: e['order'].update(watch=['ZZQA', 'ZZQB']), 'DOCUMENTS_FREE_FORM_VALUE'),
    'order: names joined by commas': (lambda e: e['order'].update(watch='ZZQA,ZZQB,ZZQ.C,ZZQ-D'),
                                     'DOCUMENTS_FREE_FORM_VALUE'),
    'order: names joined by dots': (lambda e: e['order'].update(watch='ZZQA.ZZQB.ZZQC.ZZQD.ZZQE'),
                                   'DOCUMENTS_FREE_FORM_VALUE'),
    'order: lower-case names': (lambda e: e['order'].update(watch=['zzqa', 'zzqb']), 'DOCUMENTS_FREE_FORM_VALUE'),
    'order: names that are also constants': (lambda e: e['order'].update(watch=['GO', 'LIVE', 'BOUND']),
                                            'DOCUMENTS_FREE_FORM_VALUE'),
    'order: one name': (lambda e: e['order'].update(watch='ZZQA'), 'DOCUMENTS_FREE_FORM_VALUE'),
    'order: names under writer_argv': (lambda e: e['order'].update(writer_argv=['ZZQA', 'ZZQB', 'ZZQ.C']),
                                      'DOCUMENTS_FREE_FORM_VALUE'),
    'order: names one object down': (lambda e: e['order'].update(notes={'first': 'ZZQA'}), 'DOCUMENTS_FREE_FORM_VALUE'),
    'order: a name as a key': (lambda e: e['order'].update(notes={'ZZQA': True}), 'DOCUMENTS_FREE_FORM_KEY'),
    'order: a list of hashes': (lambda e: e['order'].update(receipts=[h('one'), h('two')]), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: names joined by spaces': (with_policy(universe='ZZQA ZZQB ZZQ.C'), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: exchange-qualified names': (with_policy(monitored=['XNAS:ZZQA', 'XNYS:ZZQB']), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: names under writer_argv': (with_policy(writer_argv=['ZZQA', 'ZZQB']), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: a database address': (with_policy(dsn='postgresql://reader:hunter2@db/c3po'), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: an account value': (with_policy(equity_usd=1234567), 'DOCUMENTS_FREE_FORM_VALUE'),
    'policy: a key with a space': (with_policy(**{'Watch List': True}), 'DOCUMENTS_FREE_FORM_KEY'),
}


@pytest.mark.parametrize('name', sorted(FREE_FORM))
def test_order_and_policy_carry_only_hashes_clocks_and_constants_beyond_their_known_keys(name, tmp_path, chain):
    edit, expected = FREE_FORM[name]
    assert refused(tmp_path, chain, edit=edit) == (3, 'REFUSED', expected)
    if name.startswith('order'):
        order = copy(ORDER)
        edit({'order': order})
        assert run('templates', '--order-file', write_json(tmp_path / 'order.json', order), '--output-directory',
                   tmp_path / 'templates') == (3, {'status': 'REFUSED', 'code': expected})
        assert not (tmp_path / 'templates').exists()


def test_order_and_policy_may_carry_hashes_clocks_and_constants(tmp_path):
    """Whatever the frozen order turns out to carry beyond its four known keys, in the shapes the tool accepts."""
    order = {**ORDER, 'frozen_document_sha': h('order document'), 'signed_at': '2026-10-02T15:00:00+00:00',
             'signed_on': '2026-10-02', 'cut': 'TAIL_NEW_ONLY', 'countersigned': True, 'superseded_by': None,
             'revision': REVISION, 'epoch_again': EPOCH, 'evidence': {'owner_receipt_sha': h('owner receipt'),
                                                                      'at': '2026-10-02T15:00:01Z'}}
    policy = {**POLICY, 'issued_at': '2026-10-04T20:00:00+00:00', 'issuer_receipt_sha': h('issuer'), 'dry_run': False}
    chain = signed_chain(tool.act_b_templates(tool.app(), order), order=order, policy=policy)
    world = World(tmp_path, chain, edit=lambda e: e.update(order=order, policy=policy, policy_sha=digest(policy)))
    code, line, out = world.build(SESSIONS[0], 'primary')
    assert (code, line['status'], line['documentary_authority']) == (0, 'WRITTEN', 'VERIFIED')
    contract = json.loads((out / 'contract' / ('session=' + SESSIONS[0] + '.contract.json')).read_bytes())
    assert contract['order'] == order and contract['policy'] == policy


def test_a_list_of_instruments_cannot_ride_along(tmp_path, chain, templates, monkeypatch):
    """The tripwire behind the input check: every string of every output, under every key."""
    proof = {**POLICY, 'symbols': ['ZZQA', 'ZZQB']}
    for name, edit, expected in (
            ('a', lambda e: e.update(policy=proof, policy_sha=digest(proof)), 'DOCUMENTS_POLICY_SCOPE'),
            ('b', lambda e: e['policy'].update(mode='PROOF'), 'DOCUMENTS_POLICY_SCOPE')):
        (tmp_path / name).mkdir()
        assert refused(tmp_path / name, chain, edit=edit) == (3, 'REFUSED', expected)
    for value in ({'order': {'watch': ['ZZQA']}}, {'order': {'writer_argv': ['ZZQA', 'ZZQB']}},
                  {'writer_argv': ['ZZQA']}, {'policy': {'deep': {'writer_argv': 'ZZQ.C'}}}, {'ZZQA': 1}):
        with pytest.raises(ValueError) as error:
            tool.scan(value)
        assert str(error.value) == 'DOCUMENTS_SYMBOL_SHAPED_VALUE'
    tool.scan({'writer_argv': ['--day', '2026-10-05', 'GO'], 'epoch': EPOCH})
    # With the input check out of the way (a defect, or an order whose Act B was signed for it), names
    # under any key of the order or the policy stop the run at the tripwire: no key is exempt.
    monkeypatch.setattr(tool, 'closed', lambda *_: None)
    for index, key in enumerate(('watch', 'writer_argv')):
        order = {**ORDER, key: ['ZZQA', 'ZZQB', 'ZZQ.C']}
        (tmp_path / ('order' + str(index))).mkdir()
        world = World(tmp_path / ('order' + str(index)), signed_chain(tool.act_b_templates(tool.app(), order), order=order),
                      edit=lambda e: e.update(order=order))
        code, line, out = world.build(SESSIONS[0], 'primary')
        assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SYMBOL_SHAPED_VALUE'}) and not out.exists()
        policy = {**POLICY, key: ['ZZQA', 'ZZQB']}
        (tmp_path / ('policy' + str(index))).mkdir()
        world = World(tmp_path / ('policy' + str(index)), signed_chain(templates, policy=policy),
                      edit=lambda e: e.update(policy=policy, policy_sha=digest(policy)))
        code, line, out = world.build(SESSIONS[0], 'primary')
        assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SYMBOL_SHAPED_VALUE'}) and not out.exists()


def test_package_of_the_checkout_must_be_the_package_of_the_inputs(tmp_path, chain):
    other = h('package of another revision')
    policy = {**POLICY, 'package_sha': other}
    assert refused(tmp_path, chain, edit=lambda e: e.update(policy=policy, policy_sha=digest(policy),
                                                             package_sha=other)) \
        == (3, 'REFUSED', 'DOCUMENTS_PACKAGE_MISMATCH')
    assert tool.app().package_sha == implementation_package_sha()


# ---- the signed chain, when the reviewer supplies it ---------------------------------------------

def test_chain_directory_is_checked_by_hash_and_by_the_packaged_authority(tmp_path, chain, templates):
    (tmp_path / 'plain').mkdir()
    world = World(tmp_path / 'plain', chain)
    code, line, out = world.build(SESSIONS[1], 'primary', chained=False)
    assert (code, line['documentary_authority']) == (0, 'NOT_CHECKED')
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    assert summary['self_check']['documentary_authority'] == 'NOT_CHECKED'
    assert summary['self_check']['capacity_config'] == 'NOT_LOADED_OFFLINE'
    assert summary['self_check']['envelope'] == 'NO_PACKAGED_VALIDATOR'
    assert summary['self_check']['plans'] == 'EQUAL_TO_PACKAGED_ASSEMBLER'
    # The pin of the image is an input: equal to what this interpreter computes, its origin not checked.
    assert summary['calendar_pin_receipt'] == image_receipt()
    assert summary['self_check']['calendar_pin'] == 'EQUAL_TO_LOCAL_PROVENANCE_NOT_CHECKED'
    assert run('verify', '--directory', out)[1]['documentary_authority'] == 'NOT_CHECKED'
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory)[1]['documentary_authority'] \
        == 'VERIFIED'
    # The inputs the packaged authority refuses on the host are refused here only when the chain is at hand,
    # which is why a build without it has to be asked for as a draft.
    swapped = copy(world.pins)
    swapped['B_CODEX'], swapped['B_FABLE'] = swapped['B_FABLE'], swapped['B_CODEX']
    world.epoch['chain_pins'] = swapped
    code, line, out = world.build(SESSIONS[1], 'primary', name='swapped-draft', chained=False)
    assert (code, line['status'], line['documentary_authority']) == (0, 'WRITTEN', 'NOT_CHECKED')
    code, line, out = world.build(SESSIONS[1], 'primary', name='swapped')
    assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENT_APPROVAL'}) and not out.exists()
    world.epoch['chain_pins'] = copy(world.pins)

    (world.chain_directory / world.pins['ACT_B']['file']).write_bytes(b'changed')
    code, line, out = world.build(SESSIONS[1], 'primary', name='changed')
    assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_CHAIN_HASH'}) and not out.exists()

    # An Act B signed for another order: every pin matches, the packaged authority refuses the binding.
    other = {**ORDER, 'owner_sha': h('another owner')}
    foreign = signed_chain(tool.act_b_templates(tool.app(), other), order=other)
    (tmp_path / 'foreign').mkdir()
    world = World(tmp_path / 'foreign', foreign)
    code, line, out = world.build(SESSIONS[1], 'primary')
    assert (code, line) == (3, {'status': 'REFUSED', 'code': 'DOCUMENT_BINDING'}) and not out.exists()
    # An Act B whose template map is not the tool's: the day's GO cannot bind its template.
    stale = copy(templates)
    stale['templates'] = [{**entry, 'phases': ['admission']} for entry in stale['templates']]
    stale['template_set_sha'] = digest(stale['templates'])
    (tmp_path / 'stale').mkdir()
    world = World(tmp_path / 'stale', signed_chain(stale))
    code, line, out = world.build(SESSIONS[1], 'primary')
    assert (code, line) == (3, {'status': 'REFUSED', 'code': 'AUTHORITY_UNVERIFIED_OR_VETOED'}) and not out.exists()


# ---- tampering: the packaged validators reject a changed output ----------------------------------

def swap(raw, old, new):
    assert raw.count(old) >= 1 and old != new
    return raw.replace(old, new)


def delivered(tmp_path, chain, calendar, day=SESSIONS[2], window='contingency_1'):
    world = World(tmp_path, chain)
    code, line, out = world.build(day, window)
    assert code == 0
    summary, contract, causal = world.deliver(out, day)
    clock = Clock(datetime.fromisoformat(summary['clocks']['view_opens_at']) + timedelta(seconds=1))
    return world, summary, contract, clock


def rewrite(world, path, edit):
    body = json.loads(path.read_bytes())
    edit(body)
    world.private(path, canonical(body))


TAMPERED_DOCUMENT = [
    ('veto_view', b'"role":"FABLE"', b'"role":"DUDU"', 'prepare', 'VETO_HASH_MISMATCH'),
    ('template', b'"phases":["admission",', b'"phases":[', 'prepare', 'AUTHORITY_UNVERIFIED_OR_VETOED'),
    ('go_admission_record', b'"role":"FABLE"', b'"role":"DUDU"', 'prepare', 'AUTHORITY_UNVERIFIED_OR_VETOED'),
    ('go_bar_manifest_record', b'"role":"FABLE"', b'"role":"DUDU"', 'bar', 'AUTHORITY_UNVERIFIED_OR_VETOED'),
    ('publication_bar_manifest', b'T01:30:00+00:00', b'T01:29:59+00:00', 'bar', 'AUTHORITY_UNVERIFIED_OR_VETOED'),
]


@pytest.mark.parametrize('role,old,new,stage,expected', TAMPERED_DOCUMENT, ids=[row[0] for row in TAMPERED_DOCUMENT])
def test_tampered_pinned_document_is_rejected_by_the_packaged_authority(role, old, new, stage, expected, tmp_path,
                                                                        chain, calendar):
    world, summary, contract, clock = delivered(tmp_path, chain, calendar)
    path = world.capacity / 'documents' / summary['roles'][role].split('/')[1]
    world.private(path, swap(path.read_bytes(), old, new))
    if stage == 'prepare':
        assert code_of(lambda: prepare(world, summary, calendar, clock)) == expected
    else:
        config, store, result = prepare(world, summary, calendar, clock)
        try:
            assert result['status'] == 'COMMITTED'
            assert code_of(lambda: bar_gate(config, contract, summary['day'], clock)) == expected
        finally:
            config.close()


def later(go):
    go['go']['not_after'] = go['go']['not_after'].replace('T13:20:00', 'T13:25:00')


def later_with_its_window(go):
    later(go)
    go['go']['authority_receipts']['phase_window']['not_after'] = go['go']['not_after']


def other_commitment(payload):
    payload['contract']['causal_scope']['commitment_sha256'] = h('another commitment')
    payload['causal']['commitment_sha256'] = h('another commitment')


def other_receipt(payload):
    payload['contract']['assembler_plan']['proposal']['bindings']['wind_down_28_receipt_sha'] = h('another receipt')


def other_release(config):
    config['release_sha'] = h('another release')


TAMPERED_FILE = [
    ('go', 'session={day}.admission.json', later, 'PHASE_WINDOW_MISMATCH'),
    ('go', 'session={day}.admission.json', later_with_its_window, 'PHASE_WINDOW_HASH'),
    ('payload', 'session={day}.json', other_commitment, 'CAPACITY_CONSUMER_UNBOUND'),
    ('payload', 'session={day}.json', other_receipt, 'GO_PLAN_HASH'),
    ('config', None, other_release, 'CAPACITY_CONFIG_HASH'),
]


@pytest.mark.parametrize('folder,name,edit,expected', TAMPERED_FILE, ids=[row[2].__name__ for row in TAMPERED_FILE])
def test_tampered_go_contract_or_config_is_rejected_by_the_packaged_validators(folder, name, edit, expected,
                                                                                tmp_path, chain, calendar):
    world, summary, contract, clock = delivered(tmp_path, chain, calendar)
    name = (name or summary['roles']['capacity_config'].split('/')[1]).format(day=summary['day'])
    rewrite(world, world.capacity / folder / name, edit)
    assert code_of(lambda: prepare(world, summary, calendar, clock)) == expected


def test_tampered_bar_manifest_go_is_rejected_at_its_own_gate(tmp_path, chain, calendar):
    world, summary, contract, clock = delivered(tmp_path, chain, calendar)
    day = summary['day']

    def individual(go):
        go['go']['mode'] = 'INDIVIDUAL'
    rewrite(world, world.capacity / 'go' / ('session=' + day + '.bar_manifest.json'), individual)
    config, store, result = prepare(world, summary, calendar, clock)      # admission is not concerned
    try:
        assert result['status'] == 'COMMITTED'
        assert code_of(lambda: bar_gate(config, contract, day, clock)) == 'AUTHORITY_UNVERIFIED_OR_VETOED'
    finally:
        config.close()


def test_repinned_view_with_an_owner_veto_is_refused(tmp_path, chain, calendar):
    """Someone rewrites the view AND the config that pins it: the veto itself still refuses."""
    world, summary, contract, clock = delivered(tmp_path, chain, calendar)
    view = world.capacity / 'documents' / summary['roles']['veto_view'].split('/')[1]
    changed = swap(view.read_bytes(), b'"owner_veto":false', b'"owner_veto":true')
    world.private(view, changed)
    path = world.capacity / 'config' / summary['roles']['capacity_config'].split('/')[1]
    body = json.loads(path.read_bytes())
    body['veto_views'][summary['day']]['sha256'] = hashlib.sha256(changed).hexdigest()
    world.private(path, canonical(body))
    assert code_of(lambda: prepare(world, summary, calendar, clock)) == 'CAPACITY_CONFIG_HASH'
    repinned = hashlib.sha256(canonical(body)).hexdigest()
    assert repinned != summary['hashes']['capacity_config_sha256']          # the dispatch names the old hash
    assert code_of(lambda: prepare(world, summary, calendar, clock, sha=repinned)) == 'AUTHORITY_REVOKED_OR_VETOED'


def test_verify_rejects_a_changed_directory(tmp_path, chain):
    world = World(tmp_path, chain)
    code, line, out = world.build(SESSIONS[3], 'contingency_2')
    assert code == 0

    def verify(directory=out):
        return run('verify', '--directory', directory, '--chain-directory', world.chain_directory)
    assert verify() == (0, {**line, 'status': 'VERIFIED', 'summary': 'REBUILT_EQUAL', 'inputs': 'NOT_COMPARED'})
    # A directory that says VERIFIED is verified over the chain again, or not at all.
    assert run('verify', '--directory', out) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_CHAIN_REQUIRED'})
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    for role, path in sorted(summary['roles'].items()):
        original = (out / path).read_bytes()
        (out / path).write_bytes(original.replace(b'2026', b'2027', 1) if b'2026' in original else original + b' ')
        assert verify() == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SUMS_MISMATCH'})
        (out / path).write_bytes(original)
    (out / 'documents' / 'extra.md').write_bytes(b'x')
    assert verify() == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SUMS_FILE_SET'})
    (out / 'documents' / 'extra.md').unlink()
    view = out / summary['roles']['veto_view']
    saved = view.read_bytes()
    view.unlink()
    assert verify() == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SUMS_FILE_SET'})
    # A listed file that is a symbolic link to the same bytes is not that file.
    (tmp_path / 'elsewhere.md').write_bytes(saved)
    view.symlink_to(tmp_path / 'elsewhere.md')
    assert verify() == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SUMS_FILE_SET'})
    view.unlink()
    view.write_bytes(saved)
    assert verify()[0] == 0
    # A consistent re-listing does not help: the packaged contract check behind verify reads the content.
    contract = out / summary['roles']['contract']
    contract.write_bytes(swap(contract.read_bytes(), h('wind-down-28').encode(), h('another receipt').encode()))
    relist(out)
    assert verify() == (3, {'status': 'REFUSED', 'code': 'CAPACITY_ASSEMBLER_MISMATCH'})


def rebuilt(world, tmp_path, name, day=SESSIONS[3], window='contingency_2', chained=True):
    code, line, out = world.build(day, window, name=name, chained=chained)
    assert code == 0
    return line, out, json.loads((out / 'SUMMARY.json').read_bytes())


def carry(out, summary):
    """The forger's bookkeeping after a change of the REQUEST: its hash in the GO, both in SUMMARY, the listing."""
    roles = summary['roles']
    go = change_json(out, roles['dispatch_go'],
                     lambda body: body.update(request_sha256=raw_sha((out / roles['request']).read_bytes())))
    summary['hashes'].update(request_sha256=go['request_sha256'],
                             dispatch_go_sha256=raw_sha((out / roles['dispatch_go']).read_bytes()))
    (out / 'SUMMARY.json').write_bytes(canonical(summary))
    relist(out)


PLAN_FIELDS = {
    # fields of a plan that no packaged code reads: the package accepts each of these changes
    'admission plan says execution is authorized': lambda c: c['assembler_plan'].update(execution_authorized=True),
    'consumer plan says execution is authorized':
        lambda c: c['consumer_plans']['bar_manifest'].update(execution_authorized=True),
    'a foreign diff': lambda c: c['consumer_plans']['quote_refresh'].update(diff=[{'field': 'phase', 'before': 'x_y',
                                                                                 'after': 'bar_manifest'}]),
    'another plan schema': lambda c: c['consumer_plans']['quote_capture'].update(schema='ANOTHER_PLAN_V9'),
    'an extra plan key': lambda c: c['assembler_plan'].update(note_sha=h('note')),
    'missing bindings named in a consumer plan':
        lambda c: c['consumer_plans']['bar_manifest'].update(missing_bindings=['policy_document']),
}


@pytest.mark.parametrize('name', sorted(PLAN_FIELDS))
def test_verify_compares_every_plan_in_full_with_the_packaged_assembler(name, tmp_path, chain, calendar):
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'out')
    contract = change_json(out, summary['roles']['contract'], PLAN_FIELDS[name])
    # carried along consistently: the contract hash in the REQUEST, the REQUEST hash in the GO, SUMMARY, the listing
    sha = raw_sha((out / summary['roles']['contract']).read_bytes())
    change_json(out, summary['roles']['request'], lambda body: body['documentary'].update(contract_sha256=sha))
    summary['hashes']['contract_sha256'] = sha
    carry(out, summary)
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SELF_CHECK_PLANS'})
    # The packaged contract check does not read these fields: on the host only the contract's hash would differ.
    day = summary['day']
    causal = {'epoch': EPOCH, 'session': day, 'symbols': list(SYMBOLS), 'list_sha256': store_digest(SYMBOLS),
              'commitment_sha256': h('commitment:' + day)}
    assert validate_contract(contract, release=release(), day=day, causal=causal, calendar=calendar) == contract
    assert sha != line['sha256sums_sha256'] and raw_sha((out / 'SHA256SUMS').read_bytes()) != line['sha256sums_sha256']


def carry_config(out, summary):
    """The forger's bookkeeping after a change of the config: its hash in the REQUEST, and everything after it."""
    sha = raw_sha((out / summary['roles']['capacity_config']).read_bytes())

    def name_it(request):
        request['capacity_config_sha256'] = request['inline_env']['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'] = sha
    change_json(out, summary['roles']['request'], name_it)
    summary['hashes']['capacity_config_sha256'] = sha
    carry(out, summary)


CONFIG_CHANGES = {
    'a second key in a chain pin': (lambda c: c['document_pins']['ACT_B'].update(note_sha=h('note')),
                                    'DOCUMENTS_SELF_CHECK_PINS'),
    'a second key in a record pin': (lambda c: c['document_pins']['TEMPLATE'].update(note_sha=h('note')),
                                     'DOCUMENTS_SELF_CHECK_PINS'),
    'a chain pin of another document': (lambda c: c['document_pins']['FABLE'].update(sha256=h('another signature')),
                                        'DOCUMENTS_CHAIN_HASH'),
    'a second key in a root': (lambda c: c['roots']['go'].update(note_sha=h('note')), 'DOCUMENTS_SELF_CHECK_CONFIG'),
    'a fourth root': (lambda c: c['roots'].update(config={'path': '/c3po-capacity/config', 'identity': h('config')}),
                      'DOCUMENTS_SELF_CHECK_CONFIG'),
    'a root identity that is no hash': (lambda c: c['roots']['go'].update(identity='unbound'),
                                        'DOCUMENTS_SELF_CHECK_CONFIG'),
    'another release': (lambda c: c.update(release_sha=h('another release')), 'DOCUMENTS_SELF_CHECK_RECORDS'),
    'another calendar pin': (lambda c: c.update(calendar_pin_sha=h('another pin')), 'DOCUMENTS_SELF_CHECK_CONFIG'),
    'another veto mode': (lambda c: c.update(r2d2_v2_capacity_veto_mode='OFF_NOW'), 'DOCUMENTS_SELF_CHECK_CONFIG'),
    'a view pin for another day': (lambda c: c['veto_views'].update({SESSIONS[0]: c['veto_views'][SESSIONS[3]]}),
                                   'DOCUMENTS_SELF_CHECK_PINS'),
}


@pytest.mark.parametrize('name', sorted(CONFIG_CHANGES))
def test_verify_compares_the_config_with_the_documents(name, tmp_path, chain):
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'out')
    edit, expected = CONFIG_CHANGES[name]
    change_json(out, summary['roles']['capacity_config'], edit)
    carry_config(out, summary)
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) \
        == (3, {'status': 'REFUSED', 'code': expected})


def test_verify_refuses_a_go_file_with_other_bytes_for_the_same_go(tmp_path, chain):
    world = World(tmp_path, chain)
    for index, edit in enumerate((lambda raw: canonical({**json.loads(raw), 'note_sha': h('note')}),
                                  lambda raw: json.dumps(json.loads(raw), indent=1, sort_keys=True).encode())):
        line, out, summary = rebuilt(world, tmp_path, 'out' + str(index))
        for role in ('go_admission', 'go_bar_manifest'):
            path = out / summary['roles'][role]
            saved = path.read_bytes()
            path.write_bytes(edit(saved))
            relist(out)
            assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) == (3, {
                'status': 'REFUSED', 'code': ('DOCUMENTS_SELF_CHECK_GO_FILE', 'DOCUMENTS_SELF_CHECK_CANONICAL')[index]})
            path.write_bytes(saved)


def other_instant(value):
    return value.replace(':00+00:00', ':01+00:00') if value.endswith(':00+00:00') else value.replace('+00:00', 'Z')


REQUEST_CHANGES = {
    'day': lambda r: r.update(day=SESSIONS[2]),
    'epoch': lambda r: r.update(epoch='R2D2-V2-SHADOW-2026-10-12'),
    'operation': lambda r: r.update(operation='GO_CAPACITY_DAY_04'),
    'status': lambda r: r.update(status='NOT_BOUND'),
    'window': lambda r: r.update(window='primary'),
    'mode': lambda r: r.update(mode='PREPARE_ONLY'),
    'phases': lambda r: r.update(phases=['bar_manifest']),
    'executor_uid': lambda r: r.update(executor_uid=1000),
    'window_index': lambda r: r.update(window_index=3),
    'capacity_config_file': lambda r: r.update(capacity_config_file=r['capacity_config_file'].replace('contingency_2',
                                                                                                      'primary')),
    'capacity_config_sha256': lambda r: r.update(capacity_config_sha256=h('another config')),
    'inline_env flag': lambda r: r['inline_env'].update(C3PO_R2D2_V2_MASSIVE_BARS_ENABLED='false'),
    'inline_env config file': lambda r: r['inline_env'].update(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/x.json'),
    'inline_env config hash': lambda r: r['inline_env'].update(C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=h('another config')),
    'inline_env extra name': lambda r: r['inline_env'].update(C3PO_R2D2_V2_CAPACITY_REQUIRED='false'),
    'release': lambda r: r.update(release_sha256=h('another release')),
    'package': lambda r: r.update(package_sha256=h('another package')),
    'build': lambda r: r.update(build_sha='f' * 40),
    'not_before after the view': lambda r: r.update(not_before=r['view_valid_until']),
    'not_before too early for the wait': lambda r: r.update(not_before=r['not_before'].replace('T12:15', 'T12:14')),
    'latest_start': lambda r: r.update(latest_start=other_instant(r['latest_start'])),
    'view_opens_at': lambda r: r.update(view_opens_at=other_instant(r['view_opens_at'])),
    'view_valid_until': lambda r: r.update(view_valid_until=other_instant(r['view_valid_until'])),
    'not_after': lambda r: r.update(not_after=r['cutoff_at']),
    'cutoff_at': lambda r: r.update(cutoff_at=other_instant(r['cutoff_at'])),
    'watchdog': lambda r: r.update(transport_watchdog_seconds=86400),
    'writer_argv day': lambda r: r['writer_argv'].__setitem__(1, SESSIONS[2]),
    'writer_argv view instant': lambda r: r['writer_argv'].__setitem__(6, other_instant(r['writer_argv'][6])),
    'writer_argv wait': lambda r: r['writer_argv'].__setitem__(8, '0900'),
    'writer_argv without prepare': lambda r: r['writer_argv'].remove('--prepare-first'),
    'writer_argv extra option': lambda r: r['writer_argv'].extend(['--verify-only']),
    'writer_argv names': lambda r: r['writer_argv'].extend(['ZZQA', 'ZZQB']),
    'writer_argv other directory': lambda r: r['writer_argv'].__setitem__(3, '/etc/c3po-bar'),
    'a second writable mount': lambda r: r['mounts'][0].update(readonly=False),
    'network of the host': lambda r: r.update(network='host'),
    'image by name': lambda r: r.update(image_id='c3po/backend:production'),
    'documentary view': lambda r: r['documentary'].update(veto_view_sha256=h('another view')),
    'documentary contract': lambda r: r['documentary'].update(contract_sha256=h('another contract')),
    'documentary list': lambda r: r['documentary'].update(causal_list_sha256=h('another list')),
    'documentary extra': lambda r: r['documentary'].update(note_sha256=h('note')),
    'an extra key': lambda r: r.update(note_sha256=h('note')),
    'a missing key': lambda r: r.pop('docker_config'),
}


@pytest.mark.parametrize('name', sorted(REQUEST_CHANGES))
def test_verify_compares_the_request_with_the_documents(name, tmp_path, chain):
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'out')
    change_json(out, summary['roles']['request'], REQUEST_CHANGES[name])
    carry(out, summary)
    expected = {'a missing key': 'DOCUMENTS_SELF_CHECK_SHAPE', 'window': 'DOCUMENTS_SELF_CHECK_ROLES'}
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) \
        == (3, {'status': 'REFUSED', 'code': expected.get(name, 'DOCUMENTS_SELF_CHECK_ENVELOPE')})


GO_CHANGES = {
    'retry': lambda g: g.update(retry=True), 'issuer': lambda g: g.update(issuer='CODEX'),
    'status': lambda g: g.update(status='SIGNED_NOW'), 'day': lambda g: g.update(day=SESSIONS[2]),
    'window': lambda g: g.update(window='primary'), 'not_before': lambda g: g.update(not_before=other_instant(g['not_before'])),
    'not_after': lambda g: g.update(not_after=other_instant(g['not_after'])),
    'individual go': lambda g: g.update(individual_go_for_admission=False),
    'admission go': lambda g: g.update(admission_go_sha256=h('another go')),
    'authority': lambda g: g.update(authority_sha256=h('another authority')),
    'host binding': lambda g: g.update(host_binding_sha256=h('another host')),
    'request': lambda g: g.update(request_sha256=h('another request')),
    'payload placeholder': lambda g: g.update(payload_sha256=EMPTY_INPUT),
    'an extra key': lambda g: g.update(note_sha256=h('note')),
}


@pytest.mark.parametrize('name', sorted(GO_CHANGES))
def test_verify_compares_the_dispatch_go_with_the_request(name, tmp_path, chain):
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'out')
    change_json(out, summary['roles']['dispatch_go'], GO_CHANGES[name])
    summary['hashes']['dispatch_go_sha256'] = raw_sha((out / summary['roles']['dispatch_go']).read_bytes())
    (out / 'SUMMARY.json').write_bytes(canonical(summary))
    relist(out)
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SELF_CHECK_ENVELOPE'})


SUMMARY_CHANGES = {
    'a GO digest': (lambda s: s['hashes'].update(admission_go_sha256=h('x')), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'the other GO digest': (lambda s: s['hashes'].update(bar_manifest_go_sha256=h('y')), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'a proposal hash': (lambda s: s['hashes']['proposal_sha'].update(admission=h('z')), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'the order hash': (lambda s: s['hashes'].update(order_sha=h('o')), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'the view clock': (lambda s: s['clocks'].update(view_opens_at='2026-10-08T12:00:00+00:00'),
                       'DOCUMENTS_SELF_CHECK_INDEX'),
    'a phase clock': (lambda s: s['clocks']['admission'].update(not_after='2026-10-08T20:00:00+00:00'),
                      'DOCUMENTS_SELF_CHECK_INDEX'),
    'the publication clock': (lambda s: s['clocks'].update(bar_manifest_published_at='2026-10-08T01:00:00+00:00'),
                              'DOCUMENTS_SELF_CHECK_INDEX'),
    'the window position': (lambda s: s.update(window_index=0), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'the list state': (lambda s: s.update(list='EMPTY'), 'DOCUMENTS_SELF_CHECK_INDEX'),
    'the tool hash': (lambda s: s.update(tool_sha256=h('w')), 'DOCUMENTS_SUMMARY_TOOL'),
    'the calendar pin': (lambda s: s['calendar_pin_receipt'].update(calendar_pin_sha=h('v')),
                         'DOCUMENTS_SUMMARY_MISMATCH'),
    'the calendar version': (lambda s: s['calendar_pin_receipt'].update(calendar_version='0.0'),
                             'DOCUMENTS_SUMMARY_MISMATCH'),
    'a config said to be loaded': (lambda s: s['self_check'].update(capacity_config='LOADED'),
                                   'DOCUMENTS_SUMMARY_MISMATCH'),
    'a contract said to be complete': (lambda s: s['self_check'].update(contract='VALIDATED'),
                                       'DOCUMENTS_SUMMARY_MISMATCH'),
    'an extra key': (lambda s: s.update(note_sha256=h('note')), 'DOCUMENTS_SUMMARY_MISMATCH'),
    'an input hash that is no hash': (lambda s: s['inputs'].update(epoch_inputs_sha256='unbound'),
                                      'DOCUMENTS_SUMMARY_SCOPE'),
}


@pytest.mark.parametrize('name', sorted(SUMMARY_CHANGES))
def test_verify_rebuilds_the_summary_from_the_files(name, tmp_path, chain):
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'out')
    edit, expected = SUMMARY_CHANGES[name]
    edit(summary)
    (out / 'SUMMARY.json').write_bytes(canonical(summary))
    relist(out)
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory) \
        == (3, {'status': 'REFUSED', 'code': expected})


def test_what_verify_cannot_tell_is_named_in_its_line(tmp_path, chain):
    """A draft that calls itself verified; host facts and input hashes with nothing to compare them with."""
    world = World(tmp_path, chain)
    line, out, summary = rebuilt(world, tmp_path, 'draft', chained=False)
    assert line['documentary_authority'] == 'NOT_CHECKED'
    summary['self_check']['documentary_authority'] = 'VERIFIED'
    (out / 'SUMMARY.json').write_bytes(canonical(summary))
    relist(out)
    assert run('verify', '--directory', out) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_CHAIN_REQUIRED'})
    # Over the chain the claim is checked, not believed: this directory's GOs do verify.
    assert run('verify', '--directory', out, '--chain-directory', world.chain_directory)[1]['documentary_authority'] \
        == 'VERIFIED'
    # A host fact of the REQUEST and the hash of an input file, changed and carried along: nothing in the
    # directory contradicts them. The line says the inputs were not compared, and the listing hash is not
    # the one the build printed, which is the comparison the reviewer has to make.
    line, out, summary = rebuilt(world, tmp_path, 'facts')
    change_json(out, summary['roles']['request'], lambda r: r.update(network='another_network',
                                                                     writer_sha256=h('another writer')))
    summary['inputs']['epoch_inputs_sha256'] = h('another inputs file')
    carry(out, summary)
    code, answer = run('verify', '--directory', out, '--chain-directory', world.chain_directory)
    assert (code, answer['status'], answer['inputs']) == (0, 'VERIFIED', 'NOT_COMPARED')
    assert answer['sha256sums_sha256'] != line['sha256sums_sha256']
    # The same for a root identity inside the config, with the config hash carried through the REQUEST.
    line, out, summary = rebuilt(world, tmp_path, 'roots')
    change_json(out, summary['roles']['capacity_config'], lambda c: c['roots']['go'].update(identity=h('another root')))
    carry_config(out, summary)
    code, answer = run('verify', '--directory', out, '--chain-directory', world.chain_directory)
    assert (code, answer['status']) == (0, 'VERIFIED')
    assert answer['sha256sums_sha256'] != line['sha256sums_sha256']
    assert answer['capacity_config_sha256'] != line['capacity_config_sha256']


def test_without_the_chain_the_records_must_still_agree_with_the_go(tmp_path, chain):
    """A record that is not the record of the GO file, pinned consistently: refused with no chain at hand."""
    world = World(tmp_path, chain)
    code, line, out = world.build(SESSIONS[1], 'primary', chained=False)
    assert (code, line['documentary_authority']) == (0, 'NOT_CHECKED')
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    for role, old in (('publication_bar_manifest', b'T01:30:00+00:00'), ('go_bar_manifest_record', b'T01:30:00+00:00'),
                      ('go_admission_record', summary['hashes']['admission_go_sha256'].encode())):
        saved = tree(out)
        path = out / summary['roles'][role]
        changed = swap(path.read_bytes(), old, b'T01:29:59+00:00' if old.startswith(b'T') else h('other go').encode())
        path.write_bytes(changed)
        config = out / summary['roles']['capacity_config']
        body = json.loads(config.read_bytes())
        body['document_pins'][tool.DAY_ROLES[role]]['sha256'] = hashlib.sha256(changed).hexdigest()
        config.write_bytes(canonical(body))
        (out / 'SHA256SUMS').write_bytes(tool.sums({name: raw for name, raw in tree(out).items()
                                                    if name != 'SHA256SUMS'}))
        assert run('verify', '--directory', out) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SELF_CHECK_RECORDS'})
        for name, raw in saved.items():
            (out / name).write_bytes(raw)
        assert run('verify', '--directory', out)[0] == 0


# ---- the open decisions are switches --------------------------------------------------------------

def test_d4_in_window_view_has_the_same_bytes_and_goes_to_the_emitter(tmp_path, chain, calendar):
    (tmp_path / 'pre').mkdir()
    (tmp_path / 'emitted').mkdir()
    pre = World(tmp_path / 'pre', chain)
    emitted = World(tmp_path / 'emitted', chain, edit=lambda e: e.update(d4_view_mode='IN_WINDOW'))
    day = SESSIONS[4]
    views = []
    for world, folder in ((pre, 'documents'), (emitted, 'emitter')):
        code, line, out = world.build(day, 'primary')
        assert code == 0
        summary = json.loads((out / 'SUMMARY.json').read_bytes())
        assert summary['roles']['veto_view'].split('/')[0] == folder and summary['view_mode'] in tool.VIEW_MODES
        request = json.loads((out / summary['roles']['request']).read_bytes())
        assert request['view_mode'] == summary['view_mode']
        views.append((out / summary['roles']['veto_view']).read_bytes())
    assert views[0] == views[1]
    # In-window emission: the view file is absent until its instant; the same prepare then passes.
    summary, contract, causal = emitted.deliver(out, day)
    view = emitted.capacity / 'documents' / summary['roles']['veto_view'].split('/')[1]
    view.unlink()
    clock = Clock(datetime.fromisoformat(summary['clocks']['view_opens_at']))
    with pytest.raises(FileNotFoundError):
        prepare(emitted, summary, calendar, clock)
    emitted.private(view, views[1])
    config, store, result = prepare(emitted, summary, calendar, clock)
    config.close()
    assert result['status'] == 'COMMITTED'


def test_d6_number_of_windows_and_d11_window_form_are_parameters(tmp_path, chain, calendar):
    def one_window(e):
        e['d6_windows'] = [WINDOWS[0]]
        e['d11']['quote_refresh'] = {'phase_window_sha': h('quote-refresh window')}
    world = World(tmp_path, chain, edit=one_window)
    day = SESSIONS[0]
    inputs = session_inputs(day)
    inputs['view_evidence_sha'] = {'primary': h('view-evidence')}
    code, line, out = world.build(day, 'primary', session=inputs)
    assert code == 0
    summary, contract, causal = world.deliver(out, day)
    assert (summary['window_index'], summary['window_count']) == (0, 1)
    assert contract['consumer_plans']['quote_refresh']['proposal']['bindings']['phase_window_sha'] \
        == h('quote-refresh window')
    config, store, result = prepare(world, summary, calendar,
                                    Clock(datetime.fromisoformat(summary['clocks']['view_opens_at'])))
    config.close()
    assert result['status'] == 'COMMITTED'
    code, line, out = world.build(day, 'contingency_1', name='absent', session=inputs)
    assert (code, line['code']) == (3, 'DOCUMENTS_WINDOW_UNKNOWN')


# ---- envelope: constants and hashes -----------------------------------------------------------------

def test_envelope_names_the_documents_of_the_day_and_the_writer_arguments(tmp_path, chain):
    world = World(tmp_path, chain)
    day = SESSIONS[0]
    code, line, out = world.build(day, 'contingency_1')
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    files = tree(out)
    request = json.loads(files[summary['roles']['request']])
    go = json.loads(files[summary['roles']['dispatch_go']])
    config_raw = files[summary['roles']['capacity_config']]
    sha = lambda role: hashlib.sha256(files[summary['roles'][role]]).hexdigest()
    assert request['operation'] == go['operation'] == 'GO_CAPACITY_DAY_03' and request['status'] == 'BOUND'
    assert request['phases'] == ['admission', 'bar_manifest'] and request['executor_uid'] == 0
    assert (request['window'], request['window_index'], request['window_count']) == ('contingency_1', 1, 3)
    assert request['capacity_config_sha256'] == hashlib.sha256(config_raw).hexdigest() == sha('capacity_config')
    assert request['capacity_config_file'] == world.epoch['capacity_roots']['config']['path'] + '/' \
        + summary['roles']['capacity_config'].split('/')[1]
    assert request['inline_env'] == {
        'C3PO_R2D2_V2_SHADOW_ENABLED': 'true', 'C3PO_R2D2_V2_MASSIVE_BARS_ENABLED': 'true',
        'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE': request['capacity_config_file'],
        'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA': request['capacity_config_sha256']}
    from app.config import Settings
    assert {name[len('C3PO_'):].lower() for name in request['inline_env']} <= set(Settings.model_fields)
    assert 'DATABASE' not in json.dumps(request).upper() and 'DATABASE_URL' not in SCRIPT.read_text().upper()
    documentary = request['documentary']
    assert documentary['act_b_sha256'] == world.pins['ACT_B']['sha256']
    assert documentary['template_record_sha256'] == sha('template')
    assert documentary['admission_go_record_sha256'] == sha('go_admission_record')
    assert documentary['bar_manifest_go_record_sha256'] == sha('go_bar_manifest_record')
    assert documentary['publication_sha256'] == sha('publication_bar_manifest')
    assert documentary['veto_view_sha256'] == sha('veto_view') and documentary['contract_sha256'] == sha('contract')
    assert documentary['admission_go_sha256'] == digest(json.loads(files[summary['roles']['go_admission']])['go']) \
        == go['admission_go_sha256']
    assert go['request_sha256'] == sha('request') and go['status'] == 'UNSIGNED' and go['retry'] is False
    assert go['individual_go_for_admission'] is True and go['authority_sha256'] == h('authority-a2')
    # New York 07:15 / 07:30 / 09:20 on a daylight-time day.
    assert (request['not_before'], request['latest_start'], request['view_opens_at'], request['view_valid_until'],
            request['not_after'], request['cutoff_at']) == (
        day + 'T11:15:00+00:00', day + 'T11:30:00+00:00', day + 'T11:30:00+00:00', day + 'T11:30:10+00:00',
        day + 'T11:30:10+00:00', day + 'T13:20:00+00:00')
    assert request['transport_watchdog_seconds'] == 990
    assert request['writer_argv'] == ['--day', day, '--manifest-directory', '/etc/c3po-bar/manifests',
                                      '--prepare-first', '--view-opens-at', day + 'T11:30:00+00:00',
                                      '--max-wait-seconds', '900']
    writer = DIRECTORY / 'manifest_writer.py'
    if writer.exists():                      # the sibling script owns these option names
        text = writer.read_text()
        assert all("add_argument('" + flag + "'" in text for flag in request['writer_argv'] if flag.startswith('--'))
    # The switch for the writer's --require-go-mode: two more arguments, nothing else in the day changes.
    world.epoch['dispatch']['writer_require_go_mode'] = 'DELEGATED_ACT_B'
    code, line, required = world.build(day, 'contingency_1', name='required')
    assert code == 0
    other = tree(required)
    assert json.loads(other[summary['roles']['request']])['writer_argv'] \
        == request['writer_argv'] + ['--require-go-mode', 'DELEGATED_ACT_B']
    assert {path for path in files if files[path] != other[path]} \
        == {summary['roles']['request'], summary['roles']['dispatch_go'], 'SUMMARY.json', 'SHA256SUMS'}


# ---- cross-check with the script that reads these documents in the container ----------------------

@pytest.mark.parametrize('window,mode', [(name, 'NOT_REQUIRED') for name in WINDOW_NAMES]
                         + [('primary', 'DELEGATED_ACT_B')])
def test_manifest_writer_publishes_from_these_documents_with_the_envelope_arguments(window, mode, tmp_path, chain,
                                                                                    calendar, monkeypatch):
    """The sibling deployment script, driven by the REQUEST this tool wrote. Skipped if it is not there.

    Its own wiring (context) and its whole run (pre-flight, parking, gate, prepare, gate, link) are
    real; replaced are the collector factory (the packaged capacity collector over an in-memory
    store, without release file, sources or journal catalog), the clock and the manifest directory.
    """
    script = DIRECTORY / 'manifest_writer.py'
    if not script.exists():
        pytest.skip('manifest_writer.py is not in this checkout')
    spec = importlib.util.spec_from_file_location('manifest_writer_cross_check', script)
    writer = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, writer)        # its dataclass resolves annotations by module
    spec.loader.exec_module(writer)
    writer.APPLICATION_ROOT = str(Path(__file__).resolve().parents[1])
    day = SESSIONS[3]
    world = World(tmp_path, chain, edit=lambda e: e['dispatch'].update(writer_require_go_mode=mode))
    code, line, out = world.build(day, window)
    assert code == 0
    summary, contract, causal = world.deliver(out, day)
    request = json.loads((out / summary['roles']['request']).read_bytes())
    argv = request['writer_argv']
    options = dict(zip(argv[0:4:2], argv[1:4:2]))
    options.update(zip(argv[5::2], argv[6::2]))
    assert argv[4] == '--prepare-first' and options['--day'] == day
    extra = {}
    if mode != 'NOT_REQUIRED':
        if "add_argument('--require-go-mode'" not in script.read_text():
            pytest.skip('this manifest_writer.py has no --require-go-mode')
        extra['require_go_mode'] = options['--require-go-mode']
    manifests = world.base / 'manifests'
    manifests.mkdir(mode=0o700)

    clock = Clock(datetime.fromisoformat(request['not_before']))          # the dispatch starts when its window opens
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        clock.now += timedelta(seconds=seconds)
    config = CapacityConfig(world.settings(summary), clock=clock)
    try:
        store = MemoryShadowStore()
        collector = build_capacity_collector(store=store, source=object(), release=release(), calendar=calendar,
                                             config=config.collector_config(release(), store))
        from app import r2d2_v2_shadow_worker
        monkeypatch.setattr(r2d2_v2_shadow_worker, 'build_collector', lambda settings, now: collector)
        settings = SimpleNamespace(r2d2_v2_shadow_enabled=True, r2d2_v2_capacity_required=True,
                                   r2d2_v2_massive_bars_enabled=True, database_url='synthetic', build_sha=REVISION)
        receipt, status = writer.execute(
            lambda: writer.context(settings, now=clock(), prepare_first=True, clock=clock), day=options['--day'],
            directory=manifests, prepare_first=True, view_opens_at=options['--view-opens-at'],
            max_wait=int(options['--max-wait-seconds']), clock=clock, sleep=sleep,
            monotonic=lambda: clock.now.timestamp(), **extra)
        assert (status, receipt['status'], receipt['code']) == (0, 'PUBLISHED_VERIFIED', None)
        assert receipt['capacity_config_sha256'] == request['capacity_config_sha256'] and slept
        assert datetime.fromisoformat(request['view_opens_at']) <= clock() \
            < datetime.fromisoformat(request['view_valid_until'])
        committed = store.read(EPOCH)['state']['daily_capacity'][day]
        assert receipt['binding_sha256'] == committed['sha'] and committed['document']['contract'] == contract
        manifest = json.loads((manifests / (day + '.json')).read_bytes())
        assert manifest == {'epoch': EPOCH, 'session': day, 'owner_uid': os.geteuid(), 'symbols': sorted(SYMBOLS)}
        assert not any(name in json.dumps(receipt) for name in SYMBOLS)
    finally:
        config.close()


# ---- the reader's static config (D2, D3) --------------------------------------------------------

def test_static_config_restores_any_day_with_the_chain_documents_alone(tmp_path, chain, calendar):
    bindings = {}
    for day in (SESSIONS[0], SESSIONS[4]):
        (tmp_path / day).mkdir()
        world, summary, contract, clock = delivered(tmp_path / day, chain, calendar, day=day, window='primary')
        config, store, result = prepare(world, summary, calendar, clock)
        config.close()
        bindings[day] = (store.read(EPOCH)['state']['daily_capacity'][day], summary)
    (tmp_path / 'static').mkdir()
    world = World(tmp_path / 'static', chain)
    out = world.base / 'static-out'
    # The weekend's inputs: nothing of the dispatch, of D11, of D4 or of the policy exists yet, and the
    # hash of pins.env cannot exist, because pins.env carries the hash this command prints.
    weekend = static_inputs(world.epoch)
    assert not {'dispatch', 'd11', 'd4_view_mode', 'policy', 'policy_sha', 'act_b_sha256'} & set(weekend)
    argv = ['--day', SESSIONS[0], '--window', 'primary', '--view-evidence-sha',
            h('view-evidence:' + SESSIONS[0] + ':primary')]
    code, line = run('static-config', '--static-inputs', write_json(world.inputs / 'static.json', weekend), *argv,
                     '--output-directory', out)
    assert (code, line['status'], line['kind']) == (0, 'WRITTEN', 'STATIC_CONFIG')
    summary = json.loads((out / 'SUMMARY.json').read_bytes())
    assert summary['inputs'] == {'static_inputs_sha256': raw_sha((world.inputs / 'static.json').read_bytes())}
    assert summary['calendar_pin_receipt'] == image_receipt()
    # The epoch inputs are not an input of this command: a file with later values in it is refused whole.
    epoch_file = write_json(world.inputs / 'epoch.json', world.epoch)
    assert run('static-config', '--static-inputs', epoch_file, *argv, '--output-directory', world.base / 'no') \
        == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_STATIC_FIELDS'})
    for key in sorted(tool.STATIC_KEYS):
        short = {name: value for name, value in weekend.items() if name != key}
        assert run('static-config', '--static-inputs', write_json(world.inputs / 'short.json', short), *argv,
                   '--output-directory', world.base / 'no') == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_STATIC_FIELDS'})
    for edit, expected in ((lambda s: s.update(release_sha=EMPTY_INPUT), 'DOCUMENTS_INPUT_RELEASE_SHA'),
                           (lambda s: s['capacity_roots']['go'].update(identity=s['release_sha']),
                            'DOCUMENTS_INPUT_HASH_REUSED'),
                           (lambda s: s['order'].update(watch=['ZZQA', 'ZZQB']), 'DOCUMENTS_FREE_FORM_VALUE'),
                           (lambda s: s.update(schema='R2D2_CAPACITY_DAY_EPOCH_INPUTS_V1'), 'DOCUMENTS_STATIC_SCHEMA')):
        changed = copy(weekend)
        edit(changed)
        assert run('static-config', '--static-inputs', write_json(world.inputs / 'changed.json', changed), *argv,
                   '--output-directory', world.base / 'no') == (3, {'status': 'REFUSED', 'code': expected})
    assert run('static-config', '--static-inputs', world.inputs / 'static.json', '--day', SESSIONS[0], '--window',
               'primary', '--view-evidence-sha', EMPTY_INPUT, '--output-directory', world.base / 'no')[1]['code'] \
        == 'DOCUMENTS_INPUT_VIEW_EVIDENCE_SHA'
    assert not (world.base / 'no').exists()
    raw = (out / 'config' / 'week.static.capacity.json').read_bytes()
    body = json.loads(raw)
    assert set(body['document_pins']) == set(tool.CHAIN) | {'TEMPLATE'} and set(body['veto_views']) == {SESSIONS[0]}
    world.deliver_chain()                                    # the seven chain documents and nothing else
    world.private(world.capacity / 'config' / 'week.static.capacity.json', raw)
    settings = SimpleNamespace(r2d2_v2_capacity_config_file=str(world.capacity / 'config' / 'week.static.capacity.json'),
                               r2d2_v2_capacity_config_sha=line['capacity_config_sha256'],
                               r2d2_v2_capacity_veto_mode='DISPATCH_AND_DERIVATION_ONLY',
                               r2d2_v2_shadow_release_sha=RELEASE_SHA)
    assert summary['capacity_config_file'] == settings.r2d2_v2_capacity_config_file
    now = datetime.fromisoformat('2026-10-07T15:00:00+00:00')
    static = CapacityConfig(settings, clock=lambda: now)
    try:
        static.release(release())
        for day, (committed, day_summary) in bindings.items():
            restored = DailyCapacityBinding.restore(
                committed, release=release(), calendar=calendar,
                authority_verifier=lambda doc: static.authority.verify_binding(doc, now))
            assert restored.sha == committed['sha']
        # Its two extra pins are the anchor day's own TEMPLATE record and view, byte for byte.
        monday = bindings[SESSIONS[0]][1]['hashes']
        assert body['document_pins']['TEMPLATE']['sha256'] == monday['template_record_sha256'] \
            == summary['template_record_sha256']
        assert body['veto_views'][SESSIONS[0]]['sha256'] == monday['veto_view_sha256'] == summary['veto_view_sha256']
    finally:
        static.close()
    assert run('verify', '--directory', out) == (0, {
        'status': 'VERIFIED', 'kind': 'STATIC_CONFIG', 'files': 3, 'content': 'LISTING_ONLY',
        'sha256sums_sha256': line['sha256sums_sha256']})
    (out / 'config' / 'week.static.capacity.json').write_bytes(raw + b' ')
    assert run('verify', '--directory', out) == (3, {'status': 'REFUSED', 'code': 'DOCUMENTS_SUMS_MISMATCH'})
    assert run('static-config', '--static-inputs', world.inputs / 'static.json', '--day', '2026-10-12', '--window',
               'primary', '--view-evidence-sha', h('x'), '--output-directory', world.base / 'no')[1]['code'] \
        == 'DOCUMENTS_DAY_NOT_AUTHORIZED'


# ---- the script itself ----------------------------------------------------------------------------

def test_script_runs_isolated_and_prints_one_line(tmp_path):
    order = write_json(tmp_path / 'order.json', ORDER)
    done = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), 'templates', '--order-file', str(order),
                           '--output-directory', str(tmp_path / 'out')], capture_output=True, cwd=str(tmp_path),
                          env={'PATH': os.environ.get('PATH', ''), 'PYTHONPATH': '/nonexistent'}, timeout=120)
    assert done.returncode == 0 and done.stderr == b''
    lines = done.stdout.decode().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])['status'] == 'WRITTEN'
    assert json.loads((tmp_path / 'out' / 'ACT_B_TEMPLATES.json').read_bytes())['order_sha'] == digest(ORDER)
    # templates needs the order alone and hands out no calendar pin: that value is read in the image.
    assert set(json.loads((tmp_path / 'out' / 'SUMMARY.json').read_bytes())) == {
        'schema', 'epoch', 'tool_sha256', 'package_sha256', 'document_order_sha', 'inputs', 'order_sha',
        'template_set_sha', 'act_b_templates_sha256'}
    for argv in (['-h'], ['day', '--help'], ['templates', '--order', str(order), '--output', str(tmp_path / 'no')]):
        asked = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), *argv], capture_output=True,
                               cwd=str(tmp_path), env={'PATH': os.environ.get('PATH', '')}, timeout=120)
        assert asked.returncode == 3 and asked.stderr == b''
        assert json.loads(asked.stdout) == {'status': 'REFUSED', 'code': 'DOCUMENTS_ARGUMENTS_INVALID'}
        assert len(asked.stdout.splitlines()) == 1 and not (tmp_path / 'no').exists()
    refused_run = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), 'templates', '--order-file',
                                  str(tmp_path / 'absent.json'), '--output-directory', str(tmp_path / 'no')],
                                 capture_output=True, cwd=str(tmp_path), env={'PATH': os.environ.get('PATH', '')},
                                 timeout=120)
    assert refused_run.returncode == 3 and refused_run.stderr == b''
    assert json.loads(refused_run.stdout) == {'status': 'REFUSED', 'code': 'DOCUMENTS_INPUT_FILE'}


def test_script_touches_no_settings_network_or_process():
    source = SCRIPT.read_text()
    module = ast.parse(source)
    imported = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported == {'argparse', 'hashlib', 'json', 'os', 're', 'stat', 'sys', 'datetime', 'types', 'app',
                        'app.r2d2_v2_calendar', 'app.r2d2_v2_capacity_authority', 'app.r2d2_v2_document_authority',
                        'app.r2d2_v2_earnings_package'}
    assert not any(word in source for word in ('environ', 'get_settings', 'subprocess', 'socket', 'urllib'))
    roots = [node for node in module.body if isinstance(node, ast.Assign)
             and [target.id for target in node.targets if isinstance(target, ast.Name)] == ['APP_ROOT']]
    assert len(roots) == 1 and Path(tool.APP_ROOT).resolve() == Path(__file__).resolve().parents[1]
    assert tool.refusal(RuntimeError('postgresql://reader:hunter2@db/c3po')) \
        == ({'status': 'UNVERIFIED', 'code': 'DOCUMENTS_UNVERIFIED'}, 1)
    assert tool.refusal(ValueError('ZZQA')) == ({'status': 'UNVERIFIED', 'code': 'DOCUMENTS_UNVERIFIED'}, 1)
    assert tool.refusal(OSError(2, 'No such file', '/private/path'))[0]['code'] == 'DOCUMENTS_FILE_UNAVAILABLE'


def test_readme_states_the_open_decisions_the_commands_and_what_is_unverified():
    text = README.read_text()
    head = text[:text.index('## What the tool writes')]
    assert 'Offline candidate' in head and '**Unverified on the host.**' in head and '## Open decisions' in head
    for decision in ('D1', 'D3', 'D4', 'D6', 'D11', 'D12', 'Order object', "Writer's GO mode"):
        assert '| **' + decision + '** |' in head
    assert '**Nothing can check these three hashes**' in head and '**Nothing in the repository defines either.**' in head
    for command in ('templates', 'day', 'static-config', 'verify'):
        assert 'python -I -B c3po/deployment/capacity-day/capacity_day_documents.py ' + command + ' ' in text
    for phrase in ('evening before', 'SHA256SUMS', 'assembled on the host', '## Not verified',
                   '## Inputs that only exist after the weekend'.replace('## ', '### '), 'release hash',
                   'policy hash', 'package hash', 'Act B hash', 'capacity root identities',
                   'no code in this repository reads either file'):
        assert phrase in text
    for key in sorted(tool.EPOCH_KEYS | tool.SESSION_KEYS | tool.D11_KEYS | tool.DISPATCH_KEYS
                      | set(tool.RECEIPT_KEYS)):
        assert '`' + key + '`' in text
    for name in ('EPOCH_INPUTS_SCHEMA', 'SESSION_INPUTS_SCHEMA', 'STATIC_INPUTS_SCHEMA', 'OPERATION'):
        assert '`' + getattr(tool, name) + '`' in text
    # The static inputs are marked key by key, and the command line of each subcommand names its own file.
    rows = dict(re.findall(r'^\| `([a-z0-9_]+)` \| (S?) ?\| ', text, re.M))
    assert {key for key, mark in rows.items() if mark == 'S'} == tool.STATIC_KEYS and tool.EPOCH_KEYS <= set(rows)
    assert '--static-inputs "$WORK/STATIC.json"' in text and '--epoch-inputs "$WORK/EPOCH.json"' in text
    assert 'mkdir -m 700 "$WORK/OUT"' in text and '--chain-directory "$WORK/CHAIN"' in text
    assert '`--draft-without-chain`' in text
    assert '**Only a directory whose line says `documentary_authority` `VERIFIED` may be delivered**' in text
    # What the document says the checks are, no more: the sentences the review found false are gone.
    for gone in ('cannot reach a signed document unnoticed', 'The guarantee is structural',
                 'the same package validates everything again', 'The whole epoch inputs file is still required',
                 'every string of every output is compared', 'a consistently re-listed change by content',
                 'It is optional.', 'has no input that carries the list'):
        assert gone not in text
    for said in ('**No check can tell a wrong hash that looks real from the right one.**',
                 '**Where the line came from cannot be checked offline.**', '**What `verify` cannot tell**',
                 'It does **not** read the other fields of a plan'):
        assert said in text
    # The counts the document gives are the counts of the cases above.
    assert len(MALFORMED_EPOCH) + len(MALFORMED_SESSION) > 80 and 'more than eighty malformed values' in text
    for count, cases, phrase in ((13, REUSED, 'thirteen pairs'), (16, FREE_FORM, 'Sixteen shapes'),
                                 (6, PLAN_FIELDS, 'six changes of plan fields'),
                                 (42, REQUEST_CHANGES, 'forty-two changes of the REQUEST'),
                                 (14, GO_CHANGES, 'fourteen of the dispatch GO'),
                                 (16, SUMMARY_CHANGES, 'sixteen changes of `SUMMARY.json`')):
        assert len(cases) == count and phrase in text
    # Every code the tool can raise by itself is named, by itself or by its family.
    families = ('DOCUMENTS_INPUT_', 'DOCUMENTS_SELF_CHECK_', 'DOCUMENTS_SUMS_')
    codes = set(re.findall(r"'(DOCUMENTS_[A-Z0-9_]+)'", SCRIPT.read_text()))
    assert len(codes) > 30
    for code in sorted(codes):
        assert '`' + code + '`' in text or code.startswith(families) or code.rstrip('_') + '_' in families, code


def test_readme_calendar_pin_script_prints_the_pin_this_checkout_computes(capsys, monkeypatch, calendar):
    """Executes the exact script text of the document, as `python -I -B -` would receive it."""
    text = README.read_text()
    found = re.findall(r'^<!-- calendar-pin-script:begin -->\n```python\n(.*?)```\n<!-- calendar-pin-script:end -->$',
                       text, re.S | re.M)
    assert len(found) == 1
    script = found[0]
    assert script.endswith('\n') and len(script.splitlines()) <= 20
    assert 'Its SHA-256 is `' + hashlib.sha256(script.encode()).hexdigest() + '`' in text
    assert script.splitlines()[1] == "APPLICATION_ROOT = '/app'"
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'argv', ['-'])
        patch.setattr(sys, 'path', list(sys.path))
        exec(compile(script, 'calendar-pin.py', 'exec'), {'__name__': '__main__'})
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        'status': 'CALENDAR_PIN', 'epoch': EPOCH, 'calendar_version': calendar.version,
        'calendar_pin_sha': calendar_pin(calendar, {'authorized_sessions': list(SESSIONS)}),
        'package_sha': implementation_package_sha(), 'document_order_sha': DOCUMENT_ORDER_SHA}
    assert json.loads(lines[0])['calendar_pin_sha'] == tool.app().calendar_pin(tool.app().calendar, tool.identity(tool.app()))
