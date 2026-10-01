"""Capacity-day manifest writer (c3po/deployment/capacity-day/manifest_writer.py), loaded by path.

Synthetic offline documents and symbols only. Real assembler, documentary authority,
capacity binding, capacity config, release verification, supervisor and producer code.
No database, no provider, no container, no host: each test says what it replaces.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_capacity_authority import calendar_pin
from app.r2d2_v2_capacity_bound import derive_document
from app.r2d2_v2_document_authority import DocumentAuthority
from app.r2d2_v2_document_format import BEGIN, END, SCHEMA
from app.r2d2_v2_epoch_assembler import (DOCUMENT_ORDER_SHA, EPOCH, FIRST_SESSION, RUNTIME_ORDER_SHA, SESSIONS,
                                         canonical, digest, plan)
from app.r2d2_v2_store import canonical as store_canonical, digest as store_digest

BACKEND = Path(__file__).resolve().parents[1]
DEPLOYMENT = BACKEND.parent / 'deployment' / 'capacity-day'
SCRIPT = DEPLOYMENT / 'manifest_writer.py'
ROOT_LINE = "APPLICATION_ROOT = '/app'"


def load_script():
    spec = importlib.util.spec_from_file_location('capacity_day_manifest_writer', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.APPLICATION_ROOT = str(BACKEND)          # the checkout stands in for the image's /app
    return module


writer = load_script()

D1, D2 = SESSIONS[0], SESSIONS[1]
OWNER = 'a' * 64
BUILD = 'c' * 40
RULE = 'OPEN_FIRST_THEN_EXISTING_CAUSAL_ORDER_V1_PROPOSED'
PHASES = ['admission', 'bar_manifest', 'quote_refresh', 'quote_capture']
ORDER = {'owner_sha': OWNER, 'epoch': EPOCH, 'authorized_sessions': list(SESSIONS), 'capacity': 550}
RELEASE = SimpleNamespace(epoch=EPOCH, first_session=date.fromisoformat(FIRST_SESSION), receipt_sha='1' * 64,
                          implementation_package_sha='2' * 64)
# Sentinels: none can occur inside a hash, a key, a code or a clock of the receipt.
CAUSAL = ['ZZQB', 'ZZQA', 'ZZQ.C', 'ZZQ-D']
OPEN_ONLY = 'ZZQOPEN'
SENTINELS = CAUSAL + [OPEN_ONLY, 'ZZQEXTRA', 'ZZQLATE']
SECRET = 'ZZSECRETZZ'
HASHED = ('binding_sha256', 'symbol_count', 'manifest_sha256')


def at(day, hour, minute, second=0):
    return datetime(int(day[:4]), int(day[5:7]), int(day[8:]), hour, minute, second, tzinfo=timezone.utc)


@pytest.fixture(scope='module')
def calendar():
    return ShadowCalendar()


def policy(release):
    return {'schema': 'R2D2_V2_LIVE_POLICY_V1', 'mode': 'LIVE', 'epoch': EPOCH, 'capacity': 550,
            'order_sha': RUNTIME_ORDER_SHA, 'release_sha': release.receipt_sha,
            'package_sha': release.implementation_package_sha, 'code_revision': BUILD, 'c8_receipt_sha': '3' * 64,
            'head_go_sha': '4' * 64, 'valid_from': '2026-10-05T13:00:00+00:00',
            'valid_until': '2026-10-09T21:00:00+00:00'}


def template(day):
    return {'owner_sha': OWNER, 'epoch': EPOCH, 'day': day, 'phases': PHASES, 'rule': RULE}


def entry(day):
    return {'sha': digest(template(day)), 'epoch': EPOCH, 'first_session': FIRST_SESSION,
            'authorized_sessions': [day], 'phases': PHASES}


def document(kind, body):
    payload = canonical({'schema': SCHEMA, 'kind': kind, 'state': 'ISSUED', 'body': body}).decode()
    return f'# {kind}\n{BEGIN}\n```json\n{payload}\n```\n{END}\n'.encode()


def scope():
    return {'epoch': EPOCH, 'first_session': FIRST_SESSION, 'authorized_sessions': list(SESSIONS)}


class Root:
    def __init__(self):
        self.files = {}

    def read(self, name):
        return self.files[name]


def signed_chain(release):
    """Synthetic Act A and Act B chains in the real documentary format."""
    root, pins = Root(), {}

    def put(label, raw):
        name = label.lower().replace(':', '_') + '.md'
        root.files[name] = raw
        pins[label] = {'file': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous,
                'document_sha256': DOCUMENT_ORDER_SHA, **scope()}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino a ordem.', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:00:00+00:00'}
        put(role, document('APPROVAL', body))
        previous = pins[role]['sha256']
    templates = [entry(day) for day in SESSIONS]
    act = {'status': 'ACCEPTED', 'chain_head': pins['DUDU']['sha256'], 'order_sha': digest(ORDER),
           'template_shas': {day: digest(template(day)) for day in SESSIONS}, 'policy_sha': digest(policy(release)),
           'capacity': 550, 'cut_rule': RULE, 'subphases': {}, 'individual_go_issuers': ['FABLE'],
           'owner_countersign_phases': ['bar_merge_deploy_recertify', 'install_release', 'activate', 'wind_down_28'],
           'rollback_disposition': 'REVALIDATE_UNCOMMITTED_ONLY', **scope(),
           'causal_order': {'primary': 'ADV_DESC', 'tie_break': 'SYMBOL_ASC', 'cut': 'TAIL_NEW_ONLY'},
           'policy_epoch_validity': True, 'automatic_retry': False, 'document_order_sha': DOCUMENT_ORDER_SHA,
           'act_a_scope_map': {role: {'signature_sha': pins[role]['sha256'], 'document_sha256': DOCUMENT_ORDER_SHA,
                                      **scope()} for role in ('CODEX', 'FABLE', 'DUDU')},
           'templates': templates, 'template_set_sha': digest(templates)}
    put('ACT_B', document('ACT_B', act))
    previous = None
    for role in ('CODEX', 'FABLE', 'DUDU'):
        body = {'role': role, 'decision': 'APPROVED', 'previous_sha': previous, **scope(),
                'body_sha': pins['ACT_B']['sha256'], 'act_a_head': pins['DUDU']['sha256']}
        if role == 'DUDU':
            body['owner_evidence'] = {'verbatim': 'Assino o ato B', 'channel': 'synthetic',
                                      'signed_at_utc': '2026-10-01T11:30:00+00:00'}
        put('B_' + role, document('APPROVAL', body))
        previous = pins['B_' + role]['sha256']
    return DocumentAuthority(root=root, pins=pins), put, pins


class World:
    """One session day: contract, both GOs, a veto view and (optionally) the committed binding."""

    def __init__(self, calendar, tmp_path, *, day=D1, symbols=CAUSAL, open_symbol=OPEN_ONLY, committed=True,
                 mode='DELEGATED_ACT_B', notice_minutes=20, veto=False, go_day=None, go_phase='bar_manifest',
                 release=RELEASE):
        self.calendar, self.day, self.release = calendar, day, release
        self.policy = policy(release)
        self.now = at(day, 12, 45, 2)                       # 08:45:02 New York
        self.observed, self.until = at(day, 12, 45), at(day, 12, 45, 10)
        self.window = {'epoch': EPOCH, 'day': day, 'phase': 'bar_manifest',
                       'not_before': at(day, 12, 40).isoformat(), 'not_after': at(day, 13, 25).isoformat()}
        self.admission_window = {**self.window, 'phase': 'admission'}
        self.authority, self.put, self.pins = signed_chain(release)
        self.authority.revocation_reader = lambda _now: {
            'status': 'VERIFIED', 'observed_at': self.observed.isoformat(), 'valid_until': self.until.isoformat(),
            'owner_veto': veto, 'revoked_shas': []}
        self.contract, self.causal = self._contract(list(symbols))
        ledger = {'portfolio': {}, 'research': {}}
        if open_symbol:
            ledger['portfolio']['episode-1'] = {'status': 'OPEN', 'instrument_key': 'US:' + open_symbol}
        self.state = {'epoch': EPOCH, 'release_sha': release.receipt_sha, 'ledger': ledger, 'sessions': {},
                      'last_session': None, 'last_cycle_at': None}
        saved = {'state': self.state, 'state_sha': store_digest(self.state)}
        self.document = derive_document(release=release, day=day, causal=self.causal, saved=saved,
                                        observed_at=at(day, 12, 44), capacity=550,
                                        rule_sha=store_digest(self.contract['template']), contract=self.contract,
                                        calendar=calendar)
        self.binding = {'sha': store_digest(self.document), 'document': self.document}
        if committed:
            self.state['daily_capacity'] = {day: self.binding}
        self.gos = {'admission': self._go(day, 'admission', 'INDIVIDUAL', notice_minutes),
                    'bar_manifest': self._go(go_day or day, go_phase, mode, notice_minutes)}
        self.directory = Path(os.path.realpath(tmp_path)) / 'manifests'
        self.directory.mkdir(mode=0o700)
        self.sleeps, self.prepared, self.view_reads, self.gates = [], [], [], []
        self.row_present, self.view_is_pinned, self.view_appears_at = True, True, None
        self.payload = {'contract': self.contract, 'causal': self.causal}

    go = property(lambda self: self.gos['bar_manifest'],
                  lambda self, value: self.gos.__setitem__('bar_manifest', value))

    def _contract(self, symbols):
        day, calendar = self.day, self.calendar
        identity = {**scope(), 'namespace': EPOCH, 'document_order_sha': DOCUMENT_ORDER_SHA,
                    'runtime_order_sha': RUNTIME_ORDER_SHA}
        causal = {'epoch': EPOCH, 'session': day, 'commitment_sha256': '9' * 64, 'symbols': symbols,
                  'list_sha256': store_digest(symbols), 'status': 'AVAILABLE'}
        causal_scope = {key: causal[key] for key in ('epoch', 'session', 'commitment_sha256', 'list_sha256')}
        inputs = {'owner_sha': OWNER, 'order': ORDER, 'policy': self.policy, 'template': template(day),
                  'causal_scope': causal_scope}
        consumer = {'schema': 'CAPACITY_CONSUMER_INPUT_BINDING_V1', 'authority_inputs_sha': store_digest(inputs)}
        bindings = {'signed_epoch_order_sha': store_digest(ORDER), 'release_sha': self.policy['release_sha'],
                    'policy_sha': digest(self.policy), 'package_sha': self.policy['package_sha'],
                    'calendar_pin_sha': calendar_pin(calendar, identity), 'recertification_receipt_sha': '6' * 64,
                    'wind_down_28_receipt_sha': '7' * 64, 'template_sha': store_digest(template(day)),
                    'input_receipts_sha': '8' * 64, 'phase_window_sha': 'a' * 64}

        def planned(phase, window_sha):
            return plan(identity, day=day, phase=phase, bindings={**bindings, 'phase_window_sha': window_sha},
                        policy=self.policy, calendar=calendar, consumer_binding=consumer)

        body = {**inputs, 'assembler_plan': planned('admission', digest(self.admission_window)),
                'consumer_plans': {'bar_manifest': planned('bar_manifest', digest(self.window)),
                                   'quote_refresh': planned('quote_refresh', 'd' * 64),
                                   'quote_capture': planned('quote_capture', 'e' * 64)}}
        return body, causal

    def _go(self, day, phase, mode, notice_minutes):
        plan_ = (self.contract['assembler_plan'] if phase == 'admission'
                 else self.contract['consumer_plans']['bar_manifest'])
        window = {**self.window, 'day': day, 'phase': phase}
        published = (at(self.day, 12, 40) - timedelta(minutes=notice_minutes)).isoformat()
        receipts = {'phase_window': window}
        self.put('TEMPLATE', document('TEMPLATE', entry(day)))
        go = {'decision': 'GO', 'epoch': EPOCH, 'first_session': FIRST_SESSION, 'day': day, 'phase': phase,
              'proposal_sha': plan_['proposal_sha'], 'signed_order_sha': digest(ORDER),
              'template_sha': digest(template(day)), 'mode': mode, 'not_before': window['not_before'],
              'not_after': window['not_after'], 'automatic_retry': False, 'authority_receipts': receipts}
        record = {'go_sha': None, 'template_sha': go['template_sha'], 'decision': 'GO', 'role': 'FABLE',
                  'epoch': EPOCH, 'first_session': FIRST_SESSION, 'day': day, 'phase': phase}
        if mode == 'DELEGATED_ACT_B':
            self.put('PUBLICATION:' + phase, document('PUBLICATION', {
                'role': 'FABLE', 'template_sha': go['template_sha'], 'phase': phase, 'day': day,
                'published_at': published, 'epoch': EPOCH, 'first_session': FIRST_SESSION}))
            receipts.update(signed_act_b_sha=self.pins['ACT_B']['sha256'],
                            publication_receipt_sha=self.pins['PUBLICATION:' + phase]['sha256'],
                            published_at=published)
            record['published_at'] = published
        record['go_sha'] = digest(go)
        self.put('GO:' + phase, document('GO', record))
        return go

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)

    def read_go(self, day, phase):
        assert day == self.day
        if self.gos[phase] is None:
            raise writer.Refused('MANIFEST_GO_MISSING')
        return self.gos[phase]

    def veto_bounds(self, day):
        self.view_reads.append(self.now)
        if self.view_appears_at is not None and self.now < self.view_appears_at:
            raise FileNotFoundError('synthetic: the view was not delivered yet')
        return self.observed, self.until

    def verify_go(self, go, proposal):
        self.gates.append(self.now)
        return self.authority.verify_go(go, proposal, self.clock())

    def context(self, *, prepare=None):
        return writer.Context(
            release=self.release, calendar=self.calendar,
            read_state=lambda: {'state': self.state} if self.row_present else None,
            verify_binding=lambda doc: self.authority.verify_binding(doc, self.clock()), verify_go=self.verify_go,
            verify_chain=lambda day: self.authority.act_b(self.clock(), epoch=EPOCH, first=FIRST_SESSION, day=day),
            check_go=lambda go: writer.go_records(self.authority, go), read_go=self.read_go,
            read_payload=lambda day: json.loads(json.dumps(self.payload)),
            view_pinned=lambda day: day == self.day and self.view_is_pinned, veto_bounds=self.veto_bounds,
            prepare=prepare,
            pins={'release_sha256': self.release.receipt_sha, 'capacity_config_sha256': '5' * 64,
                  'package_sha256': self.release.implementation_package_sha, 'build_sha': BUILD})

    def commit(self, day):
        """Stand-in for prepare-capacity-day: stores the binding derived by the real derive_document."""
        self.prepared.append((day, self.now, len(self.gates)))
        self.state['daily_capacity'] = {day: self.binding}
        return {'status': 'COMMITTED', 'sha': self.binding['sha']}

    def run(self, *, prepare=None, **options):
        options.setdefault('directory', self.directory)
        return writer.execute(lambda: self.context(prepare=prepare), day=options.pop('day', self.day),
                              prepare_first=prepare is not None, clock=self.clock, sleep=self.sleep,
                              monotonic=lambda: 0.0, **options)

    @property
    def path(self):
        return self.directory / (self.day + '.json')

    def expected(self):
        return store_canonical({'epoch': EPOCH, 'session': self.day, 'owner_uid': os.geteuid(),
                                'symbols': self.document['monitored_symbols']})


def line(receipt):
    return json.dumps(receipt, sort_keys=True)


def entries(world):
    return sorted(os.listdir(world.directory))


def clean(text):
    return not any(name in text for name in SENTINELS) and SECRET not in text


def forbidden(*_args, **_kwargs):
    pytest.fail('must not be called')


# ---- the script itself ---------------------------------------------------------------------

def test_script_lives_outside_the_pinned_package_and_names_one_application_root():
    from app import r2d2_v2_earnings_package as package
    assert SCRIPT.is_file() and BACKEND / 'app' not in SCRIPT.parents
    assert 'manifest_writer.py' not in package.PACKAGE_FILES
    assert not any('manifest_writer' in name for name in package.PACKAGE_FILES)
    text = SCRIPT.read_text()
    assert text.count(ROOT_LINE) == 1 and text.index(ROOT_LINE) < text.index('def packaged')
    assert 'sys.path.insert(0, APPLICATION_ROOT)' in text
    assert 'late_recovery' not in text and 'late-recovery' not in text


def test_packaged_code_is_taken_from_the_application_root_only(monkeypatch):
    monkeypatch.setattr(writer, '_APP', None)
    monkeypatch.setattr(writer, 'APPLICATION_ROOT', str(BACKEND.parent))    # app is importable, but not from here
    monkeypatch.setattr(sys, 'path', list(sys.path))
    with pytest.raises(ValueError, match='MANIFEST_APPLICATION_ROOT'):
        writer.packaged()
    monkeypatch.setattr(writer, 'APPLICATION_ROOT', str(BACKEND))
    assert writer.packaged().private_bytes.__module__ == 'app.r2d2_v2_massive_supervisor'


def test_the_readme_pins_the_script_hash_and_names_every_code():
    import re
    readme, text = (DEPLOYMENT / 'README.md').read_text(), SCRIPT.read_text()
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() in readme
    codes = set(re.findall(r"'((?:MANIFEST|CAPACITY|GO|VETO|ROOT|PERSISTENT)_[A-Z0-9_]+)'", text))
    statuses = {'PUBLISHED_VERIFIED', 'ALREADY_PUBLISHED_VERIFIED', 'MATCH_VERIFIED', 'PREFLIGHT_OK', 'ABSENT',
                'REFUSED', 'UNVERIFIED', 'PUBLISHED_UNVERIFIED'}
    assert len(codes) > 50 and not [name for name in sorted(codes | statuses) if '`' + name + '`' not in readme]
    assert all("'" + name + "'" in text for name in statuses)
    for phrase in ('/app/day-d-data', '/c3po-capacity', '**Never mount `/etc/c3po-bar` itself.**', '## Open decisions',
                   '## Not verified', '**read-only**', '| D4 |', '| D6 |', '| D11 |', '| D1 |', '| D3 |'):
        assert phrase in readme


def _isolated(arguments, *, text=None, path=None, cwd):
    environment = {key: value for key, value in os.environ.items() if not key.startswith('C3PO_R2D2_V2')}
    command = [sys.executable, '-I', '-B', '-' if path is None else str(path), *arguments]
    return subprocess.run(command, input=text, capture_output=True, text=True, timeout=180, cwd=cwd,
                          env=environment)


def test_stdin_run_in_isolated_mode_adds_the_application_root_itself(tmp_path):
    """python -I -B - < script: the documented form. The root constant is the only edit."""
    text = SCRIPT.read_text().replace(ROOT_LINE, 'APPLICATION_ROOT = ' + repr(str(BACKEND)))
    done = _isolated(['--day', D1, '--manifest-directory', str(tmp_path)], text=text, cwd=tmp_path)
    assert (done.returncode, done.stderr) == (3, '') and done.stdout.count('\n') == 1
    assert json.loads(done.stdout) == {'schema': writer.RECEIPT_SCHEMA, 'status': 'REFUSED',
                                       'code': 'MANIFEST_SHADOW_OFF', 'session': D1, 'mode': 'PUBLISH'}
    assert os.listdir(tmp_path) == []


def test_file_run_without_the_application_is_one_constant_line(tmp_path):
    if Path('/app').exists():
        pytest.skip('this machine has an /app: the unmodified script would find an application')
    done = _isolated(['--day', D1, '--manifest-directory', str(tmp_path)], path=SCRIPT, cwd=BACKEND)
    assert (done.returncode, done.stderr) == (1, '') and done.stdout.count('\n') == 1
    assert json.loads(done.stdout)['code'] == 'MANIFEST_APPLICATION_UNAVAILABLE' and os.listdir(tmp_path) == []


# ---- publication ---------------------------------------------------------------------------

def test_publishes_the_canonical_manifest_of_the_committed_binding(calendar, tmp_path):
    world = World(calendar, tmp_path)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code'], receipt['mode']) == (0, 'PUBLISHED_VERIFIED', None, 'PUBLISH')
    raw = world.path.read_bytes()
    assert raw == world.expected() and not raw.endswith(b'\n')
    assert raw == json.dumps(json.loads(raw), sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    assert set(json.loads(raw)) == {'epoch', 'owner_uid', 'session', 'symbols'}
    assert json.loads(raw)['symbols'] == world.document['monitored_symbols'] == sorted(CAUSAL + [OPEN_ONLY])
    info = world.path.stat()
    assert (info.st_mode & 0o7777, info.st_nlink, info.st_uid) == (0o600, 1, os.geteuid())
    assert receipt['manifest_sha256'] == hashlib.sha256(raw).hexdigest() == store_digest(json.loads(raw))
    assert receipt['binding_sha256'] == world.binding['sha'] and receipt['symbol_count'] == 5
    assert receipt['prepare_status'] == 'PRECOMMITTED' and receipt['go_mode'] == 'DELEGATED_ACT_B'
    assert receipt['cutoff_at'] == at(D1, 13, 20).isoformat()          # 09:20 New York
    assert receipt['view'] == {'observed_at': world.observed.isoformat(), 'valid_until': world.until.isoformat()}
    assert receipt['file'] == {'uid': os.geteuid(), 'gid': info.st_gid, 'mode': '0600', 'nlink': 1,
                               'device': info.st_dev, 'inode': info.st_ino, 'size_within_limit': True}
    assert entries(world) == [D1 + '.json']


def test_receipt_never_carries_a_symbol(calendar, tmp_path):
    world = World(calendar, tmp_path)
    receipt, _ = world.run()
    assert clean(line(receipt))
    assert set(receipt) == {'schema', 'status', 'code', 'session', 'mode', 'epoch', 'owner_uid', 'cutoff_at',
                            'release_sha256', 'capacity_config_sha256', 'package_sha256', 'build_sha',
                            'stale_temporaries', 'repaired_temporaries', 'prepare_status', 'waited_seconds', 'view',
                            'go_sha256', 'go_mode', 'template_sha256', 'window', 'binding_sha256', 'symbol_count',
                            'manifest_sha256', 'published_at', 'file'}


@pytest.mark.parametrize('mask', [0o022, 0o077, 0o277])
def test_mode_is_exactly_0600_under_any_umask(calendar, tmp_path, mask):
    world = World(calendar, tmp_path)
    previous = os.umask(mask)
    try:
        receipt, code = world.run()
    finally:
        os.umask(previous)
    assert code == 0 and world.path.stat().st_mode & 0o7777 == 0o600


def supervise(world, monkeypatch, receipt):
    """The published file through the REAL supervisor and producer, up to the provider boundary.

    Replaced: the provider connection (raises), the token (synthetic file), the 50 GiB
    free-space floor (set to 0 so a development disk does not decide the test).
    """
    from app import r2d2_v2_massive_producer as producer
    from app import r2d2_v2_massive_supervisor as service
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from app.r2d2_v2_sources import _load_json
    raw = service.private_bytes(world.path, 65536)                 # the supervisor's own reader
    manifest = _load_json(raw)
    assert raw == world.expected() and manifest.get('session') == world.day
    assert manifest.get('owner_uid') == os.geteuid()               # the supervisor's two checks
    base = world.directory.parent / 'supervised'
    base.mkdir(mode=0o700)
    for name in ('journal', 'state'):
        (base / name).mkdir(mode=0o700)
    SessionJournalRoot(base / 'journal', EPOCH, create=True)
    token = base / 'token'
    token.write_text('synthetic\n')
    token.chmod(0o600)
    monkeypatch.setattr(producer, 'MIN_SESSION_FREE_BYTES', 0)
    reached, notices, ticks = [], [], [0.0]

    def connector(*_args, **_kwargs):
        reached.append(True)
        raise RuntimeError('synthetic stop at the provider boundary')

    def runner(root, manifest, cal, token_provider, **kwargs):
        return producer.run_session(root, manifest, cal, token_provider, connector=connector, **kwargs)

    code = service.supervised_attempt(base / 'journal', world.directory, token, base / 'state',
                                      calendar=world.calendar, utcnow=lambda: at(world.day, 13, 29, 30),
                                      monotonic=lambda: ticks[0], stop=lambda: False, notice=notices.append,
                                      runner=runner, sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds))
    claim = json.loads((base / 'state' / (world.day + '.attempt-1.json')).read_bytes())
    assert claim['manifest_sha256'] == receipt['manifest_sha256'] == hashlib.sha256(raw).hexdigest()
    assert reached and code == 1                       # stopped by the fake provider, not by the manifest
    session = json.loads((base / 'journal' / ('session_date=' + world.day) / 'session.json').read_bytes())
    assert session['symbols'] == world.document['monitored_symbols'] and session['epoch'] == EPOCH
    assert not any(str(n.get('code', '')).startswith(('MASSIVE_SERVICE_MANIFEST', 'MASSIVE_SERVICE_SYMBOLS',
                                                      'MASSIVE_SERVICE_OWNER', 'MASSIVE_SERVICE_EPOCH',
                                                      'MASSIVE_SERVICE_SESSION', 'SUPERVISOR_')) for n in notices)


def test_published_file_is_accepted_by_the_real_supervisor_and_producer(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    receipt, code = world.run()
    assert (code, receipt['status']) == (0, 'PUBLISHED_VERIFIED')
    supervise(world, monkeypatch, receipt)


def test_second_run_is_already_published_byte_identical_and_needs_no_authority(calendar, tmp_path):
    world = World(calendar, tmp_path)
    first, _ = world.run()
    before, info = world.path.read_bytes(), world.path.stat()
    world.now = at(D1, 13, 10)                          # next window: the view is long closed
    world.go, world.gos['admission'] = None, None       # no GO file is read
    context = world.context(prepare=forbidden)
    context.veto_bounds = context.verify_go = forbidden
    second, code = writer.execute(lambda: context, day=D1, directory=world.directory, prepare_first=True,
                                  clock=world.clock, sleep=forbidden)
    assert (code, second['status'], second['code']) == (0, 'ALREADY_PUBLISHED_VERIFIED', None)
    after = world.path.stat()
    assert world.path.read_bytes() == before
    assert (after.st_ino, after.st_mtime_ns, after.st_nlink) == (info.st_ino, info.st_mtime_ns, 1)
    assert {key: second[key] for key in HASHED} == {key: first[key] for key in HASHED}
    assert second['file'] == first['file'] and second['prepare_status'] == 'PRECOMMITTED'
    assert 'go_sha256' not in second and 'view' not in second and 'published_at' not in second
    assert entries(world) == [D1 + '.json']


def test_existing_different_bytes_are_never_replaced(calendar, tmp_path):
    world = World(calendar, tmp_path)
    foreign = store_canonical({'epoch': EPOCH, 'session': D1, 'owner_uid': os.geteuid(), 'symbols': ['ZZQA']})
    world.path.write_bytes(foreign)
    world.path.chmod(0o600)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_CONFLICT')
    assert world.path.read_bytes() == foreign and entries(world) == [D1 + '.json']
    assert not any(key in receipt for key in HASHED)


@pytest.mark.parametrize('prepare', ['mode', 'symlink', 'hardlink'])
def test_unsafe_existing_target_is_refused_untouched(calendar, tmp_path, prepare):
    world = World(calendar, tmp_path)
    if prepare == 'mode':
        world.path.write_bytes(world.expected())
        world.path.chmod(0o640)
    elif prepare == 'symlink':
        (world.directory / 'elsewhere').write_bytes(world.expected())
        (world.directory / 'elsewhere').chmod(0o600)
        world.path.symlink_to(world.directory / 'elsewhere')
    else:
        world.path.write_bytes(world.expected())
        world.path.chmod(0o600)
        os.link(world.path, world.directory / 'second-name')
    before = entries(world)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_EXISTING_UNVERIFIED') and entries(world) == before


# ---- the accepted prepare ------------------------------------------------------------------

def test_missing_prepare_is_refused_and_nothing_is_created(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_PREPARE_MISSING')
    assert entries(world) == [] and not any(key in receipt for key in HASHED)


def test_no_epoch_row_is_a_missing_prepare(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.row_present = False
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_PREPARE_MISSING') and entries(world) == []


def test_binding_sha_of_the_accepted_prepare_is_enforced(calendar, tmp_path):
    world = World(calendar, tmp_path)
    receipt, code = world.run(expect_sha='f' * 64)
    assert (code, receipt['code']) == (3, 'MANIFEST_BINDING_SHA_MISMATCH') and entries(world) == []
    receipt, code = world.run(expect_sha='F' * 64)
    assert (code, receipt['code']) == (3, 'MANIFEST_ARGUMENTS_INVALID')
    receipt, code = world.run(expect_sha=world.binding['sha'])
    assert (code, receipt['status']) == (0, 'PUBLISHED_VERIFIED')


def test_tampered_binding_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.state['daily_capacity'][D1]['document']['monitored_symbols'].append('ZZQEXTRA')
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'CAPACITY_RESTORE_HASH') and entries(world) == []


def test_rehashed_tampered_binding_is_refused_by_the_derivation(calendar, tmp_path):
    world = World(calendar, tmp_path)
    forged = json.loads(json.dumps(world.document))
    forged['monitored_symbols'] = sorted(forged['monitored_symbols'] + ['ZZQEXTRA'])
    world.state['daily_capacity'][D1] = {'sha': store_digest(forged), 'document': forged}
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'CAPACITY_DOCUMENT_DERIVED') and entries(world) == []
    assert clean(line(receipt))


def test_session_copy_that_differs_from_the_prepared_binding_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.state['sessions'][D1] = {'capacity_binding': {'sha': 'e' * 64, 'document': {}}}
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_BINDING_DIVERGED') and entries(world) == []


def test_open_position_outside_the_binding_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.state['ledger']['portfolio']['episode-2'] = {'status': 'OPEN', 'instrument_key': 'US:ZZQLATE'}
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'CAPACITY_UNCOVERED_OPEN') and entries(world) == []


def test_empty_universe_publishes_nothing(calendar, tmp_path):
    world = World(calendar, tmp_path, symbols=[], open_symbol=None)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_SYMBOLS_EMPTY') and entries(world) == []
    assert not any(key in receipt for key in HASHED)


def test_empty_universe_still_commits_the_admission_and_says_so(calendar, tmp_path):
    world = World(calendar, tmp_path, symbols=[], open_symbol=None, committed=False)
    receipt, code = world.run(prepare=world.commit)
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_SYMBOLS_EMPTY')
    assert receipt['prepare_status'] == 'COMMITTED' and receipt['binding_sha256'] == world.binding['sha']
    assert 'symbol_count' not in receipt and 'manifest_sha256' not in receipt and entries(world) == []


def test_prepare_first_commits_inside_the_view_after_the_first_gate_and_then_publishes(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 12, 44, 30)                      # 30 s before the view opens
    receipt, code = world.run(prepare=world.commit, view_opens_at=world.observed, max_wait=120)
    assert (code, receipt['status'], receipt['prepare_status']) == (0, 'PUBLISHED_VERIFIED', 'COMMITTED')
    (day, when, gates_before), = world.prepared
    assert day == D1 and world.observed <= when < world.until
    assert gates_before >= 1                            # the bar_manifest GO was verified in full before the commit
    assert len(world.gates) > gates_before              # and again before link()
    assert world.path.read_bytes() == world.expected() and receipt['waited_seconds'] == 30.0
    assert receipt['binding_sha256'] == world.binding['sha']


def test_prepare_first_does_not_prepare_twice(calendar, tmp_path):
    world = World(calendar, tmp_path)
    receipt, code = world.run(prepare=forbidden)
    assert (code, receipt['prepare_status']) == (0, 'PRECOMMITTED')


def test_prepare_that_reports_another_sha_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)

    def prepare(day):
        world.state['daily_capacity'] = {day: world.binding}
        return {'status': 'COMMITTED', 'sha': 'f' * 64}

    receipt, code = world.run(prepare=prepare)
    assert (code, receipt['code']) == (3, 'MANIFEST_PREPARE_UNCONFIRMED') and entries(world) == []
    assert receipt['prepare_status'] == 'COMMITTED' and not any(key in receipt for key in HASHED)


def test_binding_committed_from_another_contract_is_refused_after_the_commit(calendar, tmp_path):
    (tmp_path / 'other').mkdir()
    world, other = World(calendar, tmp_path, committed=False), World(calendar, tmp_path / 'other', symbols=CAUSAL[:2])
    assert other.binding['sha'] != world.binding['sha']

    def prepare(day):                                   # another process won the commit, from another payload
        world.state['daily_capacity'] = {day: other.binding}
        return {'status': 'ALREADY_COMMITTED', 'sha': other.binding['sha']}

    receipt, code = world.run(prepare=prepare)
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_CONTRACT_DIVERGED')
    assert receipt['prepare_status'] == 'ALREADY_COMMITTED' and receipt['binding_sha256'] == other.binding['sha']
    assert 'manifest_sha256' not in receipt and entries(world) == []


def test_view_expiring_after_the_commit_leaves_a_binding_without_a_manifest_until_the_next_window(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)

    def prepare(day):
        result = world.commit(day)
        world.now = at(D1, 12, 45, 11)                  # the commit outlived the 10-second view
        return result

    receipt, code = world.run(prepare=prepare, view_opens_at=world.observed)
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'AUTHORITY_UNVERIFIED_OR_VETOED')
    assert receipt['prepare_status'] == 'COMMITTED' and receipt['binding_sha256'] == world.binding['sha']
    assert entries(world) == []
    world.observed, world.until, world.now = at(D1, 13, 0), at(D1, 13, 0, 10), at(D1, 12, 59, 0)
    receipt, code = world.run(prepare=forbidden, view_opens_at=world.observed, max_wait=900)
    assert (code, receipt['status'], receipt['prepare_status']) == (0, 'PUBLISHED_VERIFIED', 'PRECOMMITTED')
    assert world.path.read_bytes() == world.expected()


# ---- pre-flight: every refusal comes before prepare ----------------------------------------

def _closed_view(world):
    world.now = world.until


def _early(world):
    world.now = at(D1, 12, 44)


def _before_window(world):
    world.now, world.observed, world.until = at(D1, 12, 39, 58), at(D1, 12, 39, 55), at(D1, 12, 40, 5)


def _foreign_file(world, mode=0o600):
    world.path.write_bytes(world.expected())
    world.path.chmod(mode)


def _foreign_leftover(world):
    _foreign_file(world)
    os.link(world.path, world.directory / ('.' + world.day + '.json.0123456789abcdef.tmp'))


def _drop_field(world, phase):
    world.gos[phase] = {key: value for key, value in world.gos[phase].items() if key != 'automatic_retry'}


def _tamper_document(world, label):
    world.authority.root.files[world.pins[label]['file']] += b'\n'


def _other_go_record(world):
    world.put('GO:bar_manifest', document('GO', {
        'go_sha': 'b' * 64, 'template_sha': world.go['template_sha'], 'decision': 'GO', 'role': 'FABLE',
        'epoch': EPOCH, 'first_session': FIRST_SESSION, 'day': D1, 'phase': 'bar_manifest',
        'published_at': world.go['authority_receipts']['published_at']}))


PREFLIGHT_REFUSALS = [
    ('previous evening', lambda w: setattr(w, 'now', at(D1, 3, 0)), {}, {}, 'MANIFEST_DAY_NOT_TODAY'),
    ('cutoff', lambda w: setattr(w, 'now', at(D1, 13, 20)), {}, {}, 'MANIFEST_CUTOFF_PASSED'),
    ('view declared past the cutoff', None, {}, {'view_opens_at': at(D1, 13, 20)}, 'MANIFEST_CUTOFF_PASSED'),
    ('directory not private', lambda w: w.directory.chmod(0o750), {}, {}, 'SOURCE_DIRECTORY_NOT_PRIVATE'),
    ('file without a binding', _foreign_file, {}, {}, 'MANIFEST_EXISTING_WITHOUT_BINDING'),
    ('unsafe file', lambda w: _foreign_file(w, 0o640), {}, {}, 'MANIFEST_EXISTING_UNVERIFIED'),
    ('two-link file without a binding', _foreign_leftover, {}, {}, 'MANIFEST_EXISTING_WITHOUT_BINDING'),
    ('payload fields', lambda w: w.payload.pop('causal'), {}, {}, 'CAPACITY_INPUT_FIELDS'),
    ('payload contract', lambda w: w.payload.__setitem__('contract', {**w.contract, 'owner_sha': 'b' * 64}), {}, {},
     'CAPACITY_CONSUMER_UNBOUND'),
    ('admission GO missing', lambda w: w.gos.__setitem__('admission', None), {}, {}, 'MANIFEST_GO_MISSING'),
    ('bar_manifest GO missing', lambda w: w.gos.__setitem__('bar_manifest', None), {}, {}, 'MANIFEST_GO_MISSING'),
    ('admission GO with 12 fields', lambda w: _drop_field(w, 'admission'), {}, {}, 'MANIFEST_GO_FIELDS'),
    ('bar_manifest GO with 12 fields', lambda w: _drop_field(w, 'bar_manifest'), {}, {}, 'MANIFEST_GO_FIELDS'),
    ('GO of another day', None, {'go_day': D2}, {}, 'GO_DAY_PHASE'),
    ('GO of another phase', None, {'go_phase': 'admission', 'mode': 'INDIVIDUAL'}, {}, 'GO_DAY_PHASE'),
    ('admission GO delegated', lambda w: w.gos['admission'].__setitem__('mode', 'DELEGATED_ACT_B'), {}, {},
     'GO_INDIVIDUAL_REQUIRED'),
    ('notice too short', None, {'notice_minutes': 14}, {}, 'GO_NOTICE_TOO_SHORT'),
    ('GO record of other bytes', _other_go_record, {}, {}, 'MANIFEST_GO_RECORD'),
    ('publication record unpinned', lambda w: w.pins.pop('PUBLICATION:bar_manifest'), {}, {}, 'MANIFEST_GO_RECORD'),
    ('Act B signature changed', lambda w: _tamper_document(w, 'B_DUDU'), {}, {}, 'DOCUMENT_HASH_MISMATCH'),
    ('Act A signature changed', lambda w: _tamper_document(w, 'CODEX'), {}, {}, 'DOCUMENT_HASH_MISMATCH'),
    ('view not pinned', lambda w: setattr(w, 'view_is_pinned', False), {}, {}, 'CAPACITY_VETO_DAY_UNBOUND'),
    ('declared view outside the GO window', _before_window, {}, {'view_opens_at': at(D1, 12, 39, 55), 'max_wait': 30},
     'MANIFEST_GO_WINDOW_VIEW'),
    ('pinned view outside the GO window', _before_window, {}, {}, 'MANIFEST_GO_WINDOW_VIEW'),
    ('view not open, no wait allowed', _early, {}, {'view_opens_at': at(D1, 12, 45)}, 'MANIFEST_VETO_WINDOW_NOT_OPEN'),
    ('view not open, wait too short', _early, {}, {'view_opens_at': at(D1, 12, 45), 'max_wait': 59},
     'MANIFEST_VETO_WINDOW_NOT_OPEN'),
    ('view not open, no instant declared', _early, {}, {}, 'MANIFEST_VETO_WINDOW_NOT_OPEN'),
    ('view closed', _closed_view, {}, {}, 'MANIFEST_VETO_WINDOW_MISSED'),
    ('declared instant is not the view', None, {}, {'view_opens_at': at(D1, 12, 45, 1)},
     'MANIFEST_VIEW_ARGUMENT_MISMATCH'),
    ('view never delivered', lambda w: setattr(w, 'view_appears_at', at(D1, 12, 46)), {},
     {'view_opens_at': at(D1, 12, 45)}, 'MANIFEST_VETO_VIEW_ABSENT'),
    ('view absent and no instant declared', lambda w: setattr(w, 'view_appears_at', at(D1, 12, 46)), {}, {},
     'MANIFEST_VETO_VIEW_ABSENT'),
    ('owner veto', None, {'veto': True}, {}, 'AUTHORITY_UNVERIFIED_OR_VETOED'),
]


@pytest.mark.parametrize('label,mutate,world_options,run_options,expected', PREFLIGHT_REFUSALS,
                         ids=[case[0] for case in PREFLIGHT_REFUSALS])
def test_prepare_is_not_called_on_any_preflight_refusal(calendar, tmp_path, label, mutate, world_options,
                                                         run_options, expected):
    world = World(calendar, tmp_path, committed=False, **world_options)
    if mutate is not None:
        mutate(world)
    before, mode = entries(world), world.directory.stat().st_mode
    receipt, code = world.run(prepare=forbidden, **run_options)
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', expected)
    assert entries(world) == before and world.directory.stat().st_mode == mode
    assert 'daily_capacity' not in world.state and 'prepare_status' not in receipt
    assert not any(key in receipt for key in HASHED) and clean(line(receipt))


def test_directory_owned_by_another_uid_is_refused_before_prepare(calendar, tmp_path, monkeypatch):
    import stat as stat_module
    world = World(calendar, tmp_path, committed=False)
    real = os.fstat

    class Foreign:
        def __init__(self, info):
            self._info = info

        def __getattr__(self, name):
            return os.geteuid() + 1 if name == 'st_uid' else getattr(self._info, name)

    monkeypatch.setattr(os, 'fstat', lambda fd: Foreign(real(fd)) if stat_module.S_ISDIR(real(fd).st_mode) else real(fd))
    receipt, code = world.run(prepare=forbidden)
    monkeypatch.undo()
    assert (code, receipt['code']) == (3, 'MANIFEST_DIRECTORY_OWNER') and entries(world) == []


def test_receipt_grows_only_as_gates_pass(calendar, tmp_path):
    base = {'schema', 'status', 'code', 'session', 'mode'}
    built = base | {'epoch', 'owner_uid', 'cutoff_at', 'release_sha256', 'capacity_config_sha256', 'package_sha256',
                    'build_sha'}
    world = World(calendar, tmp_path, committed=False)
    receipt, _ = world.run(prepare=forbidden, day='2026-10-10')              # refused before the directory
    assert set(receipt) == built - {'cutoff_at'} and receipt['code'] == 'MANIFEST_DAY_NOT_SESSION'
    receipt, _ = world.run(prepare=forbidden, max_wait=901)                  # refused before the context
    assert set(receipt) == base and receipt['code'] == 'MANIFEST_ARGUMENTS_INVALID'
    world.gos['bar_manifest'] = None
    receipt, _ = world.run(prepare=forbidden)                                # refused before the wait
    assert set(receipt) == built | {'stale_temporaries', 'repaired_temporaries'}
    world = World(calendar, tmp_path / 'veto' if (tmp_path / 'veto').mkdir() is None else None, committed=False,
                  veto=True)
    receipt, _ = world.run(prepare=forbidden)                                # refused by the first gate
    assert set(receipt) == built | {'stale_temporaries', 'repaired_temporaries', 'waited_seconds', 'view'}


# ---- authority, window, veto view, cutoff --------------------------------------------------

def test_individual_go_from_the_issuer_is_accepted(calendar, tmp_path):
    world = World(calendar, tmp_path, mode='INDIVIDUAL')
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['go_mode']) == (0, 'PUBLISHED_VERIFIED', 'INDIVIDUAL')


@pytest.mark.parametrize('options,expected', [
    ({'notice_minutes': 14}, 'GO_NOTICE_TOO_SHORT'),
    ({'veto': True}, 'AUTHORITY_UNVERIFIED_OR_VETOED'),
    ({'go_day': D2}, 'GO_DAY_PHASE'),
    ({'go_phase': 'admission', 'mode': 'INDIVIDUAL'}, 'GO_DAY_PHASE'),
])
def test_authority_refusals_publish_nothing(calendar, tmp_path, options, expected):
    world = World(calendar, tmp_path, **options)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', expected) and entries(world) == []
    assert not any(key in receipt for key in HASHED)


def test_static_check_never_stands_in_for_the_authority(calendar, tmp_path):
    """static_go accepts a vetoed GO (it has no authority); only _gate decides, and it refuses."""
    world = World(calendar, tmp_path, veto=True)
    plan_ = world.contract['consumer_plans']['bar_manifest']
    assert writer.static_go(world.go, plan_, day=D1, phase='bar_manifest') == (at(D1, 12, 40), at(D1, 13, 25))
    with pytest.raises(ValueError, match='AUTHORITY_UNVERIFIED_OR_VETOED'):
        writer._gate(world.context(), world.go, plan_, clock=world.clock, cutoff=at(D1, 13, 20))
    import ast
    tree = ast.parse(SCRIPT.read_text())
    users = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)
             and any(isinstance(inner, ast.Name) and inner.id == '_structure_only' for inner in ast.walk(node))}
    assert users == {'static_go'}                       # the stand-in is named in no other function


def test_revoked_pin_in_the_veto_view_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.authority.revocation_reader = lambda _now: {
        'status': 'VERIFIED', 'observed_at': world.observed.isoformat(), 'valid_until': world.until.isoformat(),
        'owner_veto': False, 'revoked_shas': [world.pins['GO:bar_manifest']['sha256']]}
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'AUTHORITY_UNVERIFIED_OR_VETOED') and entries(world) == []


def test_changed_go_bytes_are_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.go = {**world.go, 'not_after': at(D1, 20, 0).isoformat()}
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'PHASE_WINDOW_MISMATCH') and entries(world) == []


def test_view_already_closed_is_refused_with_its_own_code(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.now = at(D1, 12, 45, 10)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_VETO_WINDOW_MISSED') and entries(world) == []


def test_parks_until_the_declared_instant_only_within_the_limit(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.now = at(D1, 12, 44, 0)
    receipt, code = world.run(view_opens_at=world.observed)                  # default: no waiting at all
    assert (code, receipt['code']) == (3, 'MANIFEST_VETO_WINDOW_NOT_OPEN') and not world.sleeps
    receipt, code = world.run(view_opens_at=world.observed, max_wait=30)
    assert (code, receipt['code']) == (3, 'MANIFEST_VETO_WINDOW_NOT_OPEN') and not world.sleeps
    assert world.view_reads == []                                            # the view was never read early
    receipt, code = world.run(view_opens_at=world.observed, max_wait=120)
    assert (code, receipt['status'], receipt['waited_seconds']) == (0, 'PUBLISHED_VERIFIED', 60.0)
    assert world.sleeps and world.observed <= datetime.fromisoformat(receipt['published_at']) < world.until
    assert world.view_reads and min(world.view_reads) >= world.observed


def test_wait_cap_is_900_seconds(calendar, tmp_path):
    assert writer.MAX_WAIT_SECONDS == 900
    world = World(calendar, tmp_path)
    world.observed, world.until, world.now = at(D1, 13, 0), at(D1, 13, 0, 10), at(D1, 12, 45)
    receipt, code = world.run(view_opens_at=world.observed, max_wait=901)
    assert (code, receipt['code']) == (3, 'MANIFEST_ARGUMENTS_INVALID') and not world.sleeps
    receipt, code = world.run(view_opens_at=world.observed, max_wait=900)
    assert (code, receipt['status'], receipt['waited_seconds']) == (0, 'PUBLISHED_VERIFIED', 900.0)


def test_a_clock_that_does_not_advance_ends_the_wait(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.now = at(D1, 12, 44, 0)
    ticks = iter(range(0, 10 ** 6, 40))
    receipt, code = writer.execute(world.context, day=D1, directory=world.directory, view_opens_at=world.observed,
                                   max_wait=100, clock=world.clock, sleep=lambda _seconds: None,
                                   monotonic=lambda: float(next(ticks)))
    assert (code, receipt['code']) == (3, 'MANIFEST_WAIT_CLOCK') and entries(world) == []


def test_view_file_absent_before_the_window_then_present(calendar, tmp_path):
    """In-window emission: the view file does not exist while the process is parked."""
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 12, 44, 30)
    world.view_appears_at = at(D1, 12, 45, 2)           # delivered two seconds into the window
    receipt, code = world.run(prepare=world.commit, view_opens_at=world.observed, max_wait=60)
    assert (code, receipt['status'], receipt['prepare_status']) == (0, 'PUBLISHED_VERIFIED', 'COMMITTED')
    assert min(world.view_reads) >= world.observed      # never read while parked
    assert sum(1 for when in world.view_reads if when < world.view_appears_at) > 1    # absence was tolerated
    assert world.observed + timedelta(seconds=2) <= world.prepared[0][1] < world.until
    assert world.path.read_bytes() == world.expected()


def test_view_file_absent_beyond_the_grace_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 12, 44, 30)
    world.view_appears_at = at(D1, 12, 45, 6)
    receipt, code = world.run(prepare=forbidden, view_opens_at=world.observed, max_wait=60)
    assert (code, receipt['code']) == (3, 'MANIFEST_VETO_VIEW_ABSENT') and entries(world) == []
    assert world.now - world.observed <= timedelta(seconds=writer.VIEW_GRACE_SECONDS + 0.1)


def test_before_the_go_window_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    _before_window(world)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_GO_WINDOW_VIEW') and entries(world) == []


def test_cutoff_is_ten_minutes_before_the_open_even_inside_the_go_window(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.now, world.observed, world.until = at(D1, 13, 20, 0), at(D1, 13, 19, 58), at(D1, 13, 20, 8)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_CUTOFF_PASSED') and entries(world) == []
    world.now = at(D1, 13, 19, 59)
    receipt, code = world.run()
    assert (code, receipt['status']) == (0, 'PUBLISHED_VERIFIED')


def test_cutoff_reached_between_the_write_and_the_link_publishes_nothing(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    world.now, world.observed, world.until = at(D1, 13, 19, 59), at(D1, 13, 19, 55), at(D1, 13, 20, 5)
    real, calls = os.fsync, []

    def slow(fd):
        calls.append(fd)
        if len(calls) == 1:
            world.now = at(D1, 13, 20, 0)
        return real(fd)

    monkeypatch.setattr(os, 'fsync', slow)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_CUTOFF_PASSED')
    assert entries(world) == []


def test_there_is_no_late_recovery(calendar, tmp_path, capsys):
    world = World(calendar, tmp_path)
    with pytest.raises(TypeError):
        world.run(late_recovery=True)
    code = writer.main(['--day', D1, '--manifest-directory', str(world.directory), '--late-recovery'])
    output = capsys.readouterr()
    assert code == 3 and output.err == '' and output.out.count('\n') == 1
    assert json.loads(output.out)['code'] == 'MANIFEST_ARGUMENTS_INVALID' and entries(world) == []
    world.now, world.observed, world.until = at(D1, 13, 22, 0), at(D1, 13, 21, 58), at(D1, 13, 22, 8)
    receipt, code = world.run()                         # inside the signed window, after the cutoff
    assert (code, receipt['code']) == (3, 'MANIFEST_CUTOFF_PASSED') and entries(world) == []


def test_previous_evening_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path, day=D2)
    world.now = at(D1, 22, 0)                                     # 18:00 New York on the eve of D2
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_DAY_NOT_TODAY') and entries(world) == []


def test_authority_lost_between_write_and_link_publishes_nothing(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    real = os.fsync
    calls = []

    def slow(fd):
        calls.append(fd)
        if len(calls) == 1:
            world.now = at(D1, 12, 45, 11)                         # the view expires during the first fsync
        return real(fd)

    monkeypatch.setattr(os, 'fsync', slow)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'AUTHORITY_UNVERIFIED_OR_VETOED')
    assert entries(world) == [] and 'published_at' not in receipt


def test_each_day_uses_its_own_binding_and_template(calendar, tmp_path):
    hashes = set()
    for index, day in enumerate(SESSIONS):
        (tmp_path / day).mkdir()
        world = World(calendar, tmp_path / day, day=day, symbols=CAUSAL[:1 + index % len(CAUSAL)])
        receipt, code = world.run()
        assert (code, receipt['status'], receipt['session']) == (0, 'PUBLISHED_VERIFIED', day)
        assert json.loads(world.path.read_bytes())['session'] == day
        hashes.add(receipt['template_sha256'])
    assert len(hashes) == len(SESSIONS)


# ---- directory and crash behaviour ---------------------------------------------------------

def test_non_private_or_linked_directory_is_refused(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.directory.chmod(0o750)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'SOURCE_DIRECTORY_NOT_PRIVATE')
    world.directory.chmod(0o700)
    link = world.directory.parent / 'link'
    link.symlink_to(world.directory)
    receipt, code = world.run(directory=link)
    assert (code, receipt['status'], receipt['code']) == (1, 'UNVERIFIED', 'MANIFEST_FILE_UNAVAILABLE')
    receipt, code = world.run(directory=Path('relative'))
    assert (code, receipt['code']) == (3, 'MANIFEST_DIRECTORY_INVALID')
    receipt, code = world.run(directory=None)
    assert (code, receipt['code']) == (3, 'MANIFEST_ARGUMENTS_INVALID')
    assert entries(world) == []


def test_failed_link_leaves_no_file_and_no_temporary(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)

    def broken(*_args, **_kwargs):
        raise OSError('synthetic ZZQA')

    monkeypatch.setattr(os, 'link', broken)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (1, 'UNVERIFIED', 'MANIFEST_FILE_UNAVAILABLE')
    assert entries(world) == [] and clean(line(receipt))


def test_publication_interrupted_after_link_is_completed_by_the_next_publish_run_only(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.path.write_bytes(world.expected())
    world.path.chmod(0o600)
    leftover = world.directory / ('.' + D1 + '.json.0123456789abcdef.tmp')
    os.link(world.path, leftover)                                  # crash between link() and unlink()
    receipt, code = world.run(verify_only=True)                    # a readback never repairs
    assert (code, receipt['code']) == (3, 'MANIFEST_PUBLICATION_INTERRUPTED')
    assert leftover.exists() and world.path.stat().st_nlink == 2 and receipt['repaired_temporaries'] == 0
    world.now = at(D1, 13, 10)                                     # no view open, no GO needed for the repair
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['repaired_temporaries']) == (0, 'ALREADY_PUBLISHED_VERIFIED', 1)
    assert entries(world) == [D1 + '.json'] and world.path.stat().st_nlink == 1


def test_two_link_leftover_of_a_real_crash_is_repaired_by_a_publish_run(calendar, tmp_path, monkeypatch):
    """The process dies between link() and unlink(): simulated by an unlink that fails once."""
    from app import r2d2_v2_massive_supervisor as service
    world = World(calendar, tmp_path, committed=False)
    real = os.unlink

    def dying(name, **kwargs):
        if str(name).endswith('.tmp'):
            raise OSError('synthetic: killed before the temporary was removed')
        return real(name, **kwargs)

    monkeypatch.setattr(os, 'unlink', dying)
    receipt, code = world.run(prepare=world.commit)
    monkeypatch.setattr(os, 'unlink', real)
    assert (code, receipt['status'], receipt['code']) == (1, 'PUBLISHED_UNVERIFIED', 'MANIFEST_FILE_UNAVAILABLE')
    assert receipt['prepare_status'] == 'COMMITTED' and 'file' not in receipt
    assert len(entries(world)) == 2 and world.path.stat().st_nlink == 2
    with pytest.raises(ValueError, match='SUPERVISOR_PRIVATE_FILE'):       # the supervisor refuses two links
        service.private_bytes(world.path, 65536)
    before = entries(world)
    receipt, code = world.run(verify_only=True)
    assert (code, receipt['code']) == (3, 'MANIFEST_PUBLICATION_INTERRUPTED') and entries(world) == before
    world.observed, world.until, world.now = at(D1, 13, 0), at(D1, 13, 0, 10), at(D1, 12, 50)   # next window
    receipt, code = world.run(prepare=forbidden, view_opens_at=world.observed, max_wait=900)
    assert (code, receipt['status'], receipt['code']) == (0, 'ALREADY_PUBLISHED_VERIFIED', None)
    assert receipt['repaired_temporaries'] == 1 and receipt['prepare_status'] == 'PRECOMMITTED'
    assert not world.sleeps                                        # nothing to publish: it did not park
    assert entries(world) == [D1 + '.json'] and world.path.stat().st_nlink == 1
    assert service.private_bytes(world.path, 65536) == world.expected()
    supervise(world, monkeypatch, receipt)


def test_after_the_cutoff_a_publish_run_repairs_nothing(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.path.write_bytes(world.expected())
    world.path.chmod(0o600)
    leftover = world.directory / ('.' + D1 + '.json.0123456789abcdef.tmp')
    os.link(world.path, leftover)
    world.now = at(D1, 13, 20)
    receipt, code = world.run()
    assert (code, receipt['code']) == (3, 'MANIFEST_CUTOFF_PASSED')
    assert leftover.exists() and world.path.stat().st_nlink == 2 and 'repaired_temporaries' not in receipt


def test_foreign_temporary_is_counted_and_left_alone(calendar, tmp_path):
    world = World(calendar, tmp_path)
    stale = world.directory / ('.' + D1 + '.json.fedcba9876543210.tmp')
    stale.write_bytes(b'{}')
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['stale_temporaries']) == (0, 'PUBLISHED_VERIFIED', 1) and stale.exists()
    assert receipt['repaired_temporaries'] == 0


def test_concurrent_writer_that_wins_the_name_is_detected(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    real = os.link

    def raced(source, name, **kwargs):
        world.path.write_bytes(world.expected())
        world.path.chmod(0o600)
        return real(source, name, **kwargs)

    monkeypatch.setattr(os, 'link', raced)
    receipt, code = world.run()
    assert (code, receipt['status']) == (0, 'ALREADY_PUBLISHED_VERIFIED') and entries(world) == [D1 + '.json']
    assert 'published_at' not in receipt


def test_concurrent_writer_with_other_bytes_is_never_overwritten(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    foreign = store_canonical({'epoch': EPOCH, 'session': D1, 'owner_uid': os.geteuid(), 'symbols': ['ZZQA']})
    real = os.link

    def raced(source, name, **kwargs):
        world.path.write_bytes(foreign)                            # appears after the absence check
        world.path.chmod(0o600)
        return real(source, name, **kwargs)

    monkeypatch.setattr(os, 'link', raced)
    receipt, code = world.run()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_CONFLICT')
    assert world.path.read_bytes() == foreign and entries(world) == [D1 + '.json']


# ---- verify-only ---------------------------------------------------------------------------

def test_verify_only_never_writes_and_needs_no_go(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.go = None
    world.now = at(D1, 13, 31)                                     # after the open, for the post-open readback
    context = world.context()
    context.veto_bounds = context.verify_go = context.read_payload = forbidden

    def verify(**options):
        return writer.execute(lambda: context, day=D1, directory=world.directory, verify_only=True,
                              clock=world.clock, sleep=forbidden, **options)

    receipt, code = verify()
    assert (code, receipt['status'], receipt['code'], receipt['mode']) == (3, 'ABSENT', 'MANIFEST_ABSENT', 'VERIFY_ONLY')
    assert entries(world) == [] and not any(key in receipt for key in HASHED)
    world.path.write_bytes(world.expected())
    world.path.chmod(0o600)
    receipt, code = verify()
    assert (code, receipt['status'], receipt['code']) == (0, 'MATCH_VERIFIED', None)
    assert receipt['manifest_sha256'] == hashlib.sha256(world.expected()).hexdigest() and receipt['file']['nlink'] == 1
    world.path.write_bytes(world.expected() + b' ')
    receipt, code = verify()
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', 'MANIFEST_CONFLICT')
    assert not any(key in receipt for key in HASHED)
    for options in ({'prepare_first': True}, {'view_opens_at': world.observed}, {'max_wait': 1}, {'preflight': True}):
        receipt, code = verify(**options)
        assert (code, receipt['code']) == (3, 'MANIFEST_ARGUMENTS_INVALID')
    world.state.pop('daily_capacity')
    receipt, code = verify()
    assert (code, receipt['code']) == (3, 'MANIFEST_PREPARE_MISSING')


# ---- --preflight ---------------------------------------------------------------------------

def preflight(world, *, prepare=forbidden, **options):
    context = world.context(prepare=prepare)
    context.veto_bounds = context.verify_go = forbidden            # the view is never read, no gate runs
    return writer.execute(lambda: context, day=world.day, prepare_first=prepare is not None, preflight=True,
                          clock=world.clock, sleep=forbidden, monotonic=forbidden, **options)


def test_preflight_writes_and_commits_nothing(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 9, 5)                                       # 05:05 New York: hours before any window
    snapshot = json.dumps(world.state, sort_keys=True)
    receipt, code = preflight(world, directory=world.directory, view_opens_at=world.observed, max_wait=900)
    assert (code, receipt['status'], receipt['code'], receipt['mode']) == (0, 'PREFLIGHT_OK', None, 'PREFLIGHT')
    assert receipt['checks'] == {
        'state_row_present': True, 'binding_committed': False, 'act_b_chain_verified': True,
        'veto_view_pinned': True, 'day_is_today': True, 'before_cutoff': True, 'payload_contract_valid': True,
        'go_files_valid': ['admission', 'bar_manifest'], 'directory_checked': True, 'stale_temporaries': 0,
        'publication_interrupted': False, 'manifest_present': False}
    assert receipt['windows'] == {phase: {'not_before': world.gos[phase]['not_before'],
                                          'not_after': world.gos[phase]['not_after']} for phase in world.gos}
    assert (receipt['release_sha256'], receipt['capacity_config_sha256']) == (RELEASE.receipt_sha, '5' * 64)
    assert receipt['cutoff_at'] == at(D1, 13, 20).isoformat()
    assert not any(key in receipt for key in HASHED + ('prepare_status', 'view', 'waited_seconds', 'go_sha256'))
    assert entries(world) == [] and json.dumps(world.state, sort_keys=True) == snapshot
    assert not world.sleeps and not world.view_reads and not world.gates and clean(line(receipt))


def test_preflight_needs_no_manifest_directory_and_no_clock_in_the_window(calendar, tmp_path):
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 15, 0)                                      # after the cutoff: reported, not refused
    receipt, code = preflight(world)
    assert (code, receipt['status']) == (0, 'PREFLIGHT_OK')
    assert receipt['checks']['directory_checked'] is False and receipt['checks']['before_cutoff'] is False
    world.now = at(D1, 3, 0)
    receipt, code = preflight(world)
    assert (code, receipt['checks']['day_is_today']) == (0, False)


def test_preflight_of_a_committed_binding_and_of_an_interrupted_publication(calendar, tmp_path):
    world = World(calendar, tmp_path)
    world.gos['admission'], world.payload = None, {}               # neither is needed once the binding exists
    world.path.write_bytes(world.expected())
    world.path.chmod(0o600)
    leftover = world.directory / ('.' + D1 + '.json.0123456789abcdef.tmp')
    os.link(world.path, leftover)
    receipt, code = preflight(world, prepare=None, directory=world.directory, expect_sha=world.binding['sha'])
    assert (code, receipt['status']) == (0, 'PREFLIGHT_OK')
    assert receipt['checks']['binding_committed'] is receipt['checks']['binding_restored'] is True
    assert receipt['checks']['publication_interrupted'] is True and receipt['checks']['go_files_valid'] == ['bar_manifest']
    assert leftover.exists() and world.path.stat().st_nlink == 2   # reported, not repaired
    assert not any(key in receipt for key in HASHED)
    receipt, code = preflight(world, prepare=None, expect_sha='f' * 64)
    assert (code, receipt['code']) == (3, 'MANIFEST_BINDING_SHA_MISMATCH')


@pytest.mark.parametrize('label,mutate,options,expected', [
    ('no prepare flag', None, {'prepare': None}, 'MANIFEST_PREPARE_MISSING'),
    ('GO missing', lambda w: w.gos.__setitem__('bar_manifest', None), {}, 'MANIFEST_GO_MISSING'),
    ('admission GO fields', lambda w: _drop_field(w, 'admission'), {}, 'MANIFEST_GO_FIELDS'),
    ('chain', lambda w: _tamper_document(w, 'B_CODEX'), {}, 'DOCUMENT_HASH_MISMATCH'),
    ('payload', lambda w: w.payload.pop('contract'), {}, 'CAPACITY_INPUT_FIELDS'),
    ('view unpinned', lambda w: setattr(w, 'view_is_pinned', False), {}, 'CAPACITY_VETO_DAY_UNBOUND'),
    ('GO record', _other_go_record, {}, 'MANIFEST_GO_RECORD'),
    ('declared view outside the GO window', None, {'view_opens_at': at(D1, 12, 39, 59)}, 'MANIFEST_GO_WINDOW_VIEW'),
    ('declared view past the cutoff', None, {'view_opens_at': at(D1, 13, 20)}, 'MANIFEST_CUTOFF_PASSED'),
    ('not a session', None, {'day': '2026-10-10'}, 'MANIFEST_DAY_NOT_SESSION'),
], ids=lambda value: value if isinstance(value, str) else None)
def test_preflight_refusals(calendar, tmp_path, label, mutate, options, expected):
    world = World(calendar, tmp_path, committed=False)
    world.now = at(D1, 9, 5)
    if mutate is not None:
        mutate(world)
    if 'day' in options:
        world.day = options.pop('day')
    receipt, code = preflight(world, **options)
    assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', expected)
    assert entries(world) == [] and 'daily_capacity' not in world.state and 'checks' not in receipt


# ---- output hygiene ------------------------------------------------------------------------

@pytest.mark.parametrize('error,expected,exit_code', [
    (ValueError('ZZQA'), 'MANIFEST_UNVERIFIED', 1),                # a symbol can never become a code
    (KeyError('ZZQA'), 'MANIFEST_UNVERIFIED', 1),
    (ValueError('invalid literal: ZZQA'), 'MANIFEST_UNVERIFIED', 1),
    (ValueError('ZZQ_A', 'ZZQA'), 'MANIFEST_UNVERIFIED', 1),
    (RuntimeError('connection to postgresql://user:' + SECRET + '@db failed'), 'MANIFEST_UNVERIFIED', 1),
    (OSError(13, 'ZZQA'), 'MANIFEST_FILE_UNAVAILABLE', 1),
    (ImportError('ZZQA'), 'MANIFEST_APPLICATION_UNAVAILABLE', 1),
    (ValueError('GO_WINDOW'), 'GO_WINDOW', 3),
])
def test_error_text_is_reduced_to_constant_codes(calendar, tmp_path, error, expected, exit_code):
    world = World(calendar, tmp_path)
    context = world.context()

    def broken():
        raise error

    context.read_state = broken
    receipt, code = writer.execute(lambda: context, day=D1, directory=world.directory, clock=world.clock)
    assert (code, receipt['code']) == (exit_code, expected) and clean(line(receipt))
    assert receipt['status'] == ('REFUSED' if exit_code == 3 else 'UNVERIFIED')


def test_database_errors_have_their_own_code():
    error = type('OperationalError', (Exception,), {'__module__': 'psycopg.errors'})(SECRET)
    assert writer.refusal(error) == ('MANIFEST_DATABASE_UNAVAILABLE', 1)


def test_every_refusal_code_of_the_script_holds_an_underscore():
    import re
    text = SCRIPT.read_text()
    codes = set(re.findall(r"'((?:MANIFEST|CAPACITY|GO|VETO|ROOT|PERSISTENT)_[A-Z0-9_]+)'", text))
    assert len(codes) > 30 and all(writer._CODE.match(code) for code in codes)
    assert not any(writer._CODE.match(name) for name in SENTINELS + ['BRK.B', 'A', 'ZZQ-D'])


@pytest.mark.parametrize('day', ['2026-10-10', '2026-10-5', '20261005', '../2026-10-05', '', None, 20261005])
def test_invalid_or_non_session_day_is_refused(calendar, tmp_path, day):
    world = World(calendar, tmp_path)
    receipt, code = world.run(day=day)
    assert code == 3 and receipt['code'] in {'MANIFEST_DAY_INVALID', 'MANIFEST_DAY_NOT_SESSION'}
    assert receipt['session'] in (None, '2026-10-10') and entries(world) == []


def test_main_prints_one_line_and_refuses_while_off(monkeypatch, capsys, tmp_path):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(r2d2_v2_shadow_enabled=False))
    code = writer.main(['--day', D1, '--manifest-directory', str(tmp_path)])
    output = capsys.readouterr()
    assert code == 3 and output.err == '' and output.out.count('\n') == 1
    assert json.loads(output.out) == {'schema': writer.RECEIPT_SCHEMA, 'status': 'REFUSED',
                                      'code': 'MANIFEST_SHADOW_OFF', 'session': D1, 'mode': 'PUBLISH'}
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize('arguments', [[], ['--day'], ['--day', D1, '--max-wait-seconds', 'ZZQA'],
                                       ['--day', D1, '--unknown', 'ZZQA'], ['--day', D1],
                                       ['--day', D1, '--manifest-directory', '/x', '--verify'],
                                       ['--day', D1, '--manifest-dir', '/x'],
                                       ['--day', D1, '--manifest-directory', '/x', '--view-opens-at', 'ZZQA'],
                                       ['--day', D1, '--manifest-directory', '/x', '--view-opens-at',
                                        '2026-10-05T12:45:00']])
def test_argument_errors_are_one_json_line(monkeypatch, capsys, arguments):
    from app import config
    monkeypatch.setattr(config, 'get_settings', forbidden)
    code = writer.main(arguments)
    output = capsys.readouterr()
    assert code == 3 and output.err == '' and output.out.count('\n') == 1 and clean(output.out)
    assert json.loads(output.out)['code'] == 'MANIFEST_ARGUMENTS_INVALID'


# ---- wiring against the real pinned capacity configuration ---------------------------------

def _private(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def view_document(world, *, veto=False):
    return document('VETO_VIEW', {
        'status': 'VERIFIED', 'role': 'FABLE', 'epoch': EPOCH, 'day': world.day, 'order_sha': digest(ORDER),
        'observed_at': world.observed.isoformat(), 'valid_until': world.until.isoformat(), 'owner_veto': veto,
        'revoked_shas': [], 'evidence_sha': 'b' * 64})


def deliver(world, base, *, veto=False, view=True, package=None):
    """The capacity tree as the evening delivery leaves it: four private roots and a pinned config."""
    from app.r2d2_v2_capacity_anchored import AnchoredRoot
    from app.r2d2_v2_earnings_package import implementation_package_sha
    roots = {}
    for name in ('config', 'documents', 'payload', 'go'):
        (base / name).mkdir(mode=0o700)
        anchored = AnchoredRoot(base / name)
        roots[name] = {'path': str(base / name), 'identity': anchored.identity}
        anchored.close()
    for name, raw in world.authority.root.files.items():
        _private(base / 'documents' / name, raw)
    raw_view = view_document(world, veto=veto)
    if view:
        _private(base / 'documents' / 'veto.md', raw_view)
    for phase, go in world.gos.items():
        _private(base / 'go' / ('session=' + world.day + '.' + phase + '.json'), canonical({'go': go}))
    _private(base / 'payload' / ('session=' + world.day + '.json'), canonical(world.payload))
    identity = {**scope(), 'namespace': EPOCH, 'document_order_sha': DOCUMENT_ORDER_SHA,
                'runtime_order_sha': RUNTIME_ORDER_SHA}
    body = {'schema': 'R2D2_CAPACITY_BOOTSTRAP_V3', 'r2d2_v2_capacity_veto_mode': 'DISPATCH_AND_DERIVATION_ONLY',
            'identity': identity, 'calendar_pin_sha': calendar_pin(world.calendar, identity),
            'release_sha': world.release.receipt_sha, 'package_sha': package or implementation_package_sha(),
            'roots': {key: roots[key] for key in ('documents', 'payload', 'go')}, 'document_pins': world.pins,
            'veto_views': {world.day: {'file': 'veto.md', 'sha256': hashlib.sha256(raw_view).hexdigest()}},
            'restore_revocation': None}
    raw = canonical(body)
    _private(base / 'config' / 'capacity.json', raw)
    return str(base / 'config' / 'capacity.json'), hashlib.sha256(raw).hexdigest(), raw_view


def _stubbed_settings(world, base, monkeypatch, **delivery):
    """Real CapacityConfig, authority and pinned view. Replaced: release verification and the database."""
    from app import database, r2d2_v2_shadow, r2d2_v2_shadow_worker, r2d2_v2_store
    from app.r2d2_v2_earnings_package import implementation_package_sha
    path, sha, _ = deliver(world, base, **delivery)
    release = SimpleNamespace(epoch=EPOCH, first_session=RELEASE.first_session, receipt_sha=RELEASE.receipt_sha,
                              implementation_package_sha=implementation_package_sha())
    monkeypatch.setattr(r2d2_v2_shadow_worker, '_release_bytes', lambda _path: b'synthetic')
    monkeypatch.setattr(r2d2_v2_shadow.Release, 'verify', classmethod(lambda cls, *_a, **_k: release))
    monkeypatch.setattr(database, 'Database', lambda _settings: SimpleNamespace(connection=None))
    monkeypatch.setattr(r2d2_v2_store, 'PostgresShadowStore',
                        lambda _factory: SimpleNamespace(read=lambda epoch: {'state': world.state}))
    return SimpleNamespace(
        r2d2_v2_shadow_enabled=True, r2d2_v2_capacity_required=True,
        database_url='postgresql://synthetic:' + SECRET + '@db.invalid/synthetic',
        r2d2_v2_capacity_config_file=path, r2d2_v2_capacity_config_sha=sha,
        r2d2_v2_capacity_veto_mode='DISPATCH_AND_DERIVATION_ONLY', r2d2_v2_shadow_release_file='/unused',
        r2d2_v2_shadow_release_sha=RELEASE.receipt_sha, build_sha=BUILD)


def _wired(world, settings, **options):
    return writer.execute(lambda: writer.context(settings, now=world.clock(), prepare_first=False, clock=world.clock),
                          day=world.day, directory=world.directory, clock=world.clock, sleep=world.sleep,
                          monotonic=lambda: 0.0, **options)


def test_real_capacity_config_authority_and_pinned_veto_view(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    world.authority.revocation_reader = None                   # only the pinned files may answer
    settings = _stubbed_settings(world, Path(os.path.realpath(tmp_path)), monkeypatch)
    world.now = at(D1, 12, 44, 40)
    receipt, code = _wired(world, settings, view_opens_at=world.observed, max_wait=60)
    assert (code, receipt['status'], receipt['code']) == (0, 'PUBLISHED_VERIFIED', None)
    assert world.path.read_bytes() == world.expected() and world.sleeps
    assert receipt['capacity_config_sha256'] == settings.r2d2_v2_capacity_config_sha
    assert receipt['release_sha256'] == RELEASE.receipt_sha and receipt['build_sha'] == BUILD
    assert receipt['capacity_veto_mode'] == 'DISPATCH_AND_DERIVATION_ONLY' and receipt['massive_bars_enabled'] is False
    assert clean(line(receipt))


def test_real_config_refuses_owner_veto_missing_go_and_changed_config(calendar, tmp_path, monkeypatch):
    for label, expected in (('veto', 'AUTHORITY_UNVERIFIED_OR_VETOED'), ('go', 'MANIFEST_GO_MISSING'),
                            ('record', 'MANIFEST_GO_RECORD_MISSING'), ('config', 'CAPACITY_CONFIG_HASH')):
        base = Path(os.path.realpath(tmp_path)) / label
        base.mkdir()
        world = World(calendar, base)
        settings = _stubbed_settings(world, base, monkeypatch, veto=label == 'veto')
        if label == 'go':
            (base / 'go' / ('session=' + D1 + '.bar_manifest.json')).unlink()
        if label == 'record':
            (base / 'documents' / world.pins['PUBLICATION:bar_manifest']['file']).unlink()
        if label == 'config':
            _private(base / 'config' / 'capacity.json', b'{}')
        receipt, code = _wired(world, settings)
        assert (code, receipt['status'], receipt['code']) == (3, 'REFUSED', expected)
        assert entries(world) == []


def test_real_config_day_without_a_veto_view_is_refused(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path, day=D2)
    settings = _stubbed_settings(world, Path(os.path.realpath(tmp_path)), monkeypatch)
    body = json.loads((Path(settings.r2d2_v2_capacity_config_file)).read_bytes())
    body['veto_views'] = {D1: body['veto_views'][D2]}
    raw = canonical(body)
    _private(Path(settings.r2d2_v2_capacity_config_file), raw)
    settings.r2d2_v2_capacity_config_sha = hashlib.sha256(raw).hexdigest()
    receipt, code = _wired(world, settings)
    assert (code, receipt['code']) == (3, 'CAPACITY_VETO_DAY_UNBOUND') and entries(world) == []


def test_real_config_view_emitted_inside_the_window(calendar, tmp_path, monkeypatch):
    """D4 = in-window emission, on the real anchored root: absent, then half written, then the pinned bytes."""
    world = World(calendar, tmp_path)
    world.authority.revocation_reader = None
    base = Path(os.path.realpath(tmp_path))
    settings = _stubbed_settings(world, base, monkeypatch, view=False)
    raw_view, target, steps = view_document(world), base / 'documents' / 'veto.md', []
    world.now = at(D1, 12, 44, 50)
    advance = world.sleep

    def emitter(seconds):
        advance(seconds)
        if world.now >= world.observed + timedelta(seconds=1) and not steps:
            _private(target, raw_view[:40])                    # a writer that is not atomic
            steps.append('partial')
        elif world.now >= world.observed + timedelta(seconds=2) and steps == ['partial']:
            _private(target, raw_view)
            steps.append('complete')

    world.sleep = emitter
    assert not target.exists()
    receipt, code = _wired(world, settings, view_opens_at=world.observed, max_wait=60)
    assert steps == ['partial', 'complete']
    assert (code, receipt['status'], receipt['code']) == (0, 'PUBLISHED_VERIFIED', None)
    assert world.observed + timedelta(seconds=2) <= datetime.fromisoformat(receipt['published_at']) < world.until


def test_real_config_other_view_bytes_are_refused_after_the_grace(calendar, tmp_path, monkeypatch):
    world = World(calendar, tmp_path)
    base = Path(os.path.realpath(tmp_path))
    settings = _stubbed_settings(world, base, monkeypatch, view=False)
    _private(base / 'documents' / 'veto.md', view_document(world, veto=True))   # not the pinned bytes
    world.now = at(D1, 12, 45, 1)
    receipt, code = _wired(world, settings, view_opens_at=world.observed)
    assert (code, receipt['code']) == (3, 'VETO_HASH_MISMATCH') and entries(world) == []
    assert world.now >= world.observed + timedelta(seconds=writer.VIEW_GRACE_SECONDS)


# ---- one process, one veto view: prepare-capacity-day through the real build_collector ------

def certified_release(base, calendar):
    """Synthetic release bytes that the REAL Release.verify accepts for this epoch (EBAR, real package hashes)."""
    from app.r2d2_v2_shadow import (AMENDMENT_SHA, CONSENT_SCHEMA, EARNINGS_AMENDMENT_SHA,
                                    EARNINGS_CLOSED_MANIFEST_SHA, EBAR_AMENDMENT_SHA, RELEASE_SCHEMA,
                                    SIGNED_MANIFEST_SHA, Release, current_contract_sha, current_package_sha)
    body = {'schema': RELEASE_SCHEMA, 'manifest_sha': SIGNED_MANIFEST_SHA, 'signed_manifest_sha': SIGNED_MANIFEST_SHA,
            'amendment_sha': AMENDMENT_SHA, 'earnings_amendment_sha': EARNINGS_AMENDMENT_SHA,
            'earnings_closed_manifest_sha': EARNINGS_CLOSED_MANIFEST_SHA, 'ebar_amendment_sha': EBAR_AMENDMENT_SHA,
            'implementation_contract_sha': current_contract_sha(), 'implementation_package_sha': current_package_sha(),
            'epoch': EPOCH, 'mode': 'CERTIFIED', 'first_session': FIRST_SESSION,
            'approved_at': '2026-10-03T19:00:00+00:00', 'code_revision': BUILD, 'code_audit_sha': 'c' * 64,
            'authorization_ref': 'synthetic-not-an-authorization', 'calibration_status': 'ACCEPTED',
            'calibration_protocol': 'C3PO-V2-CAL-3', 'calibration_sha': 'd' * 64,
            'calibration_acceptance_sha': '1' * 64, 'source_audit_sha': 'e' * 64,
            'source_codex_signature_sha': '2' * 64, 'source_fable_signature_sha': '3' * 64, 'readiness_sha': '4' * 64,
            'readiness_at': '2026-10-03T18:00:00+00:00', 'readiness_publication_at': '2026-10-03T18:05:00+00:00',
            'deploy_completed_at': '2026-10-03T17:00:00+00:00'}
    bindings = {key: body[key] for key in (
        'earnings_amendment_sha', 'earnings_closed_manifest_sha', 'implementation_contract_sha',
        'implementation_package_sha', 'code_revision', 'code_audit_sha', 'source_audit_sha', 'readiness_sha',
        'ebar_amendment_sha')}
    body['package_consents'] = [{'schema': CONSENT_SCHEMA, 'party': party, 'approved': True,
                                 'approved_at': '2026-10-03T18:30:00+00:00',
                                 'receipt_ref': 'SYNTHETIC-ONLY-' + party + '-NOT-AUTHORIZATION',
                                 'receipt_sha': hashlib.sha256(('synthetic consent ' + party).encode()).hexdigest(),
                                 **bindings} for party in ('CODEX', 'FABLE', 'DUDU')]
    raw = store_canonical(body)
    path = base / 'release.json'
    _private(path, raw)
    sha = hashlib.sha256(raw).hexdigest()
    return path, sha, Release.verify(raw, sha, now=at(D1, 9, 0), build_sha=BUILD, calendar=calendar)


class Deployment:
    """The container's view, offline: release file, journal catalog, capacity tree, settings.

    Real: app.config.Settings, _release_bytes, Release.verify, CapacityConfig on anchored roots,
    ConfigAuthority with the pinned veto view file, build_collector, SessionJournalRoot (catalog
    created by the real code), CapacityBoundCollector, CapacityLoader.derive, prepare_capacity_day,
    MemoryShadowStore (the package's own in-memory store, with its journal chain).
    Replaced: PostgreSQL (Database is a stub that must never connect; PostgresShadowStore returns
    the MemoryShadowStore), the wall clock (CapacityConfig's datetime and the script's clock are
    the test clock), the release/Act A/Act B/GO documents and the symbols (synthetic).
    """

    def __init__(self, calendar, tmp_path, monkeypatch, **world_options):
        from app import config, database, r2d2_v2_capacity_bootstrap, r2d2_v2_shadow_worker, r2d2_v2_store
        from app.config import Settings
        from app.r2d2_v2_massive_sessions import SessionJournalRoot
        from app.r2d2_v2_store import MemoryShadowStore
        base = Path(os.path.realpath(tmp_path))
        release_path, release_sha, release = certified_release(base, calendar)
        self.world = world = World(calendar, base, committed=False, open_symbol=None, release=release,
                                   **world_options)
        world.authority.revocation_reader = None                   # only the pinned view file may answer
        (base / 'journal').mkdir(mode=0o700)
        SessionJournalRoot(base / 'journal', EPOCH, create=True)
        config_path, config_sha, _ = deliver(world, base)
        self.store = MemoryShadowStore()
        self.connections = []

        class NoDatabase:
            def __init__(inner, _settings):
                inner.connection = lambda: self.connections.append(True)

        monkeypatch.setattr(database, 'Database', NoDatabase)
        monkeypatch.setattr(r2d2_v2_shadow_worker, 'PostgresShadowStore', lambda _factory: self.store)
        monkeypatch.setattr(r2d2_v2_store, 'PostgresShadowStore', lambda _factory: self.store)
        monkeypatch.setattr(r2d2_v2_capacity_bootstrap, 'datetime',
                            SimpleNamespace(now=lambda _zone: world.clock()))
        self.settings = Settings(
            database_url='postgresql://synthetic:' + SECRET + '@db.invalid/synthetic', build_sha=BUILD,
            r2d2_v2_shadow_enabled=True, r2d2_v2_capacity_required=True, r2d2_v2_massive_bars_enabled=True,
            r2d2_v2_massive_journal_dir=base / 'journal', r2d2_v2_shadow_source_dir=base / 'absent-source',
            r2d2_microstructure_raw_dir=base / 'absent-raw', r2d2_v2_shadow_release_file=release_path,
            r2d2_v2_shadow_release_sha=release_sha, r2d2_v2_capacity_config_file=config_path,
            r2d2_v2_capacity_config_sha=config_sha)
        monkeypatch.setattr(config, 'get_settings', lambda: self.settings)
        self.base, self.release_sha, self.config_sha = base, release_sha, config_sha

    def main(self, capsys, *arguments):
        world = self.world
        code = writer.main(['--day', world.day, *arguments], clock=world.clock, sleep=world.sleep,
                           monotonic=lambda: 0.0)
        output = capsys.readouterr()
        assert output.err == '' and output.out.count('\n') == 1 and clean(output.out)
        return json.loads(output.out), code, output.out


def test_prepare_first_through_the_real_build_collector(calendar, tmp_path, monkeypatch, capsys):
    deployment = Deployment(calendar, tmp_path, monkeypatch)
    world, store = deployment.world, deployment.store
    directory = ['--manifest-directory', str(world.directory)]
    dispatch = ['--prepare-first', *directory, '--view-opens-at', world.observed.isoformat(),
                '--max-wait-seconds', '900']

    # 05:05 New York: the context-only run. Nothing is created anywhere.
    world.now = at(D1, 9, 5)
    receipt, code, _ = deployment.main(capsys, '--preflight', *dispatch)
    assert (code, receipt['status']) == (0, 'PREFLIGHT_OK')
    assert receipt['capacity_config_sha256'] == deployment.config_sha
    assert receipt['release_sha256'] == deployment.release_sha and receipt['massive_bars_enabled'] is True
    assert receipt['checks']['payload_contract_valid'] and receipt['checks']['state_row_present'] is False
    assert store.read(EPOCH) is None and entries(world) == [] and not world.sleeps

    # The dispatch: parked 10 minutes before the view, then prepare and manifest inside it.
    world.now = at(D1, 12, 35)
    receipt, code, _ = deployment.main(capsys, *dispatch)
    assert (code, receipt['status'], receipt['code']) == (0, 'PUBLISHED_VERIFIED', None)
    assert receipt['prepare_status'] == 'COMMITTED' and receipt['waited_seconds'] == 600.0
    row, journal = store.read_with_journal(EPOCH)
    committed = row['state']['daily_capacity'][D1]
    assert [record['journal_key'] for record in journal] == ['capacity-prepared:' + D1]
    assert receipt['binding_sha256'] == committed['sha'] == journal[0]['payload']['plan_sha']
    assert world.observed <= datetime.fromisoformat(journal[0]['payload']['at']) < world.until
    raw = world.path.read_bytes()
    assert json.loads(raw) == {'epoch': EPOCH, 'owner_uid': os.geteuid(), 'session': D1, 'symbols': sorted(CAUSAL)}
    assert committed['document']['monitored_symbols'] == sorted(CAUSAL)
    assert receipt['manifest_sha256'] == hashlib.sha256(raw).hexdigest() and receipt['symbol_count'] == len(CAUSAL)
    assert world.observed <= datetime.fromisoformat(receipt['published_at']) < world.until

    # A contingency window after success: nothing derived, nothing written, no parking.
    world.sleeps.clear()
    world.now = at(D1, 12, 50)
    again, code, _ = deployment.main(capsys, *dispatch[:-4], '--view-opens-at', at(D1, 13, 0).isoformat(),
                                     '--max-wait-seconds', '900')
    assert (code, again['status'], again['prepare_status']) == (0, 'ALREADY_PUBLISHED_VERIFIED', 'PRECOMMITTED')
    assert world.path.read_bytes() == raw and store.read(EPOCH)['version'] == row['version'] and not world.sleeps
    assert {key: again[key] for key in HASHED} == {key: receipt[key] for key in HASHED}

    # The readback after the open: the light context (no collector), read-only.
    world.now = at(D1, 13, 35)
    match, code, _ = deployment.main(capsys, '--verify-only', *directory, '--expect-binding-sha', committed['sha'])
    assert (code, match['status'], match['manifest_sha256']) == (0, 'MATCH_VERIFIED', receipt['manifest_sha256'])
    assert store.read(EPOCH)['version'] == row['version'] and entries(world) == [D1 + '.json']
    assert deployment.connections == []                 # the stub database was never asked for a connection
    supervise(world, monkeypatch, receipt)


def test_real_collector_refusals_commit_nothing(calendar, tmp_path, monkeypatch, capsys):
    deployment = Deployment(calendar, tmp_path, monkeypatch)
    world, store = deployment.world, deployment.store
    arguments = ['--prepare-first', '--manifest-directory', str(world.directory)]
    world.now = at(D1, 12, 45, 2)
    (deployment.base / 'go' / ('session=' + D1 + '.admission.json')).unlink()
    receipt, code, _ = deployment.main(capsys, *arguments)
    assert (code, receipt['code']) == (3, 'MANIFEST_GO_MISSING')
    assert store.read(EPOCH) is None and entries(world) == []
    receipt, code, _ = deployment.main(capsys, '--preflight', *arguments)
    assert (code, receipt['code']) == (3, 'MANIFEST_GO_MISSING')
    # The catalog is part of the context: without it the collector, hence the run, is refused.
    (deployment.base / 'journal' / 'epoch.json').unlink()
    receipt, code, _ = deployment.main(capsys, '--preflight', *arguments)
    assert (code, receipt['code']) == (3, 'MASSIVE_SESSION_ROOT_UNVERIFIED')
    assert set(receipt) == {'schema', 'status', 'code', 'session', 'mode'}
    assert store.read(EPOCH) is None and entries(world) == []


def test_database_failure_text_never_reaches_the_output(calendar, tmp_path, monkeypatch, capsys):
    deployment = Deployment(calendar, tmp_path, monkeypatch)
    world = deployment.world

    def broken(_epoch):
        raise RuntimeError('could not connect: ' + deployment.settings.database_url + ' ZZQA')

    monkeypatch.setattr(deployment.store, 'read', broken)
    receipt, code, out = deployment.main(capsys, '--prepare-first', '--manifest-directory', str(world.directory))
    assert (code, receipt['status'], receipt['code']) == (1, 'UNVERIFIED', 'MANIFEST_UNVERIFIED')
    assert 'synthetic' not in out and 'postgresql' not in out and entries(world) == []


SCENARIOS = ['published', 'preflight', 'verify', 'conflict', 'veto', 'tampered', 'uncovered', 'crash']


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_symbols_and_secret_never_appear_in_any_output(calendar, tmp_path, monkeypatch, capsys, caplog, scenario):
    """main() end to end on the real config wiring; stdout, stderr, log records and receipt are searched."""
    from app import config
    world = World(calendar, tmp_path, veto=scenario == 'veto')
    world.authority.revocation_reader = None
    settings = _stubbed_settings(world, Path(os.path.realpath(tmp_path)), monkeypatch, veto=scenario == 'veto')
    monkeypatch.setattr(config, 'get_settings', lambda: settings)
    arguments = ['--day', D1, '--manifest-directory', str(world.directory)]
    if scenario == 'preflight':
        arguments.append('--preflight')
    if scenario in ('verify', 'conflict'):
        world.path.write_bytes(world.expected() + (b' ' if scenario == 'conflict' else b''))
        world.path.chmod(0o600)
        arguments.append('--verify-only')
    if scenario == 'tampered':
        world.state['daily_capacity'][D1]['document']['monitored_symbols'].append('ZZQEXTRA')
    if scenario == 'uncovered':
        world.state['ledger']['portfolio']['episode-2'] = {'status': 'OPEN', 'instrument_key': 'US:ZZQLATE'}
    if scenario == 'crash':
        monkeypatch.setattr(os, 'link', lambda *_a, **_k: (_ for _ in ()).throw(OSError(5, 'ZZQA ' + SECRET)))
    code = writer.main(arguments, clock=world.clock, sleep=world.sleep, monotonic=lambda: 0.0)
    output = capsys.readouterr()
    receipt = json.loads(output.out)
    expected = {'published': (0, 'PUBLISHED_VERIFIED', None), 'preflight': (0, 'PREFLIGHT_OK', None),
                'verify': (0, 'MATCH_VERIFIED', None), 'conflict': (3, 'REFUSED', 'MANIFEST_CONFLICT'),
                'veto': (3, 'REFUSED', 'AUTHORITY_UNVERIFIED_OR_VETOED'),
                'tampered': (3, 'REFUSED', 'CAPACITY_RESTORE_HASH'),
                'uncovered': (3, 'REFUSED', 'CAPACITY_UNCOVERED_OPEN'),
                'crash': (1, 'UNVERIFIED', 'MANIFEST_FILE_UNAVAILABLE')}[scenario]
    assert (code, receipt['status'], receipt['code']) == expected
    assert output.err == '' and output.out.count('\n') == 1
    for text in (output.out, output.err, caplog.text, line(receipt), ' '.join(arguments)):
        assert clean(text)
    assert 'db.invalid' not in output.out and str(world.directory) not in output.out
    symbols = set(world.document['monitored_symbols'])
    assert symbols and all(name in SENTINELS for name in symbols)   # the sentinels are what would have leaked
