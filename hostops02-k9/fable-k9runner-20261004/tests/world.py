"""Sandboxes for the K9 runner tests: the container's mounts as private directories, K9W's step plans, a virtual clock.

Everything is created under the scratchpad (K9_TEST_WORK/<run>/), outside the deliverable; the release export is
only read, with bytecode writing off. The runner under test is always a copy named by its hash, k9_runner-<sha256>.py,
as E0 delivers it."""
import hashlib, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNNER = ROOT / 'k9_runner.py'
# Everything machine-specific comes from the environment (no workstation path in these files):
#   K9_RELEASE_TREE  the c3po/backend directory of the release export dd4ec4bb (required; the tests skip without it)
#   K9_TEST_PYTHON   an interpreter with the release's libraries (default: this one)
#   K9_TEST_WORK     where the sandboxes are created (default: the system temporary directory), outside the deliverable
PYTHON = os.environ.get('K9_TEST_PYTHON', sys.executable)
APP = os.environ.get('K9_RELEASE_TREE', '')
SCRATCH = os.environ.get('K9_TEST_WORK') or os.path.join(tempfile.gettempdir(), 'k9runner-work')
WORK = Path(SCRATCH) / os.environ.get('K9_TEST_RUN', datetime.now().strftime('%Y%m%dT%H%M%S'))
EPOCH = 'R2D2-V2-SHADOW-2026-10-05'
PACKAGE = 'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
REVISION = 'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
DAY = '2026-10-06'
EVE = datetime.fromisoformat('2026-10-05T22:30:00+00:00')
SYMBOLS = ['ZQAA', 'ZQBB', 'ZQCC', 'ZQDD', 'ZQEE', 'ZQFF', 'ZQGG', 'ZQHH', 'ZQII', 'ZQJJ']
CANARY = 'CANARYTOKEN7f3a9c'
PASSWORD = 'CANARYPASS7f3a9c'
DSN = 'postgresql://c3po_v2_risk_reader:CANARYDSN7f3a9c@db:5432/c3po'
PHASE = {'collect_launch': 'causal_list', 'commit_launch': 'causal_list', 'publish_launch': 'causal_list',
         'components_launch': 'components', 'sources_launch': 'sources', 'bind': 'risk', 'stage': 'risk', 'capture_launch': 'capture'}
NETWORK = {'collect_launch': 'PROVIDER', 'commit_launch': 'DATABASE', 'publish_launch': 'DATABASE', 'components_launch': 'PROVIDER',
           'sources_launch': 'DATABASE_AND_PROVIDER', 'bind': 'NONE', 'stage': 'NONE', 'capture_launch': 'PROVIDER'}
LIMITS = {'max_symbols': 550, 'max_total_requests': 2200, 'max_body_bytes': 16777216, 'max_total_bytes': 1073741824, 'max_elapsed_seconds': 3600}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def canon(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def akey(day, phase, op):
    return sha(json.dumps([EPOCH, day, phase, op], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


_PINS = {}


def source_pins_sha256(app=APP, cache=True):
    """RISK_HOST_SOURCE_PINS_V1 over every app/**/*.py, as bind writes it (canonical JSON + newline)."""
    if app not in _PINS or not cache:
        root = Path(app)
        files = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in (root / 'app').rglob('*.py')}
        _PINS[app] = sha(canon({'schema': 'RISK_HOST_SOURCE_PINS_V1', 'files': files}) + b'\n')
    return _PINS[app]


def mkdir(path, mode=0o700):
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)
    return path


class World:
    def __init__(self, name):
        self.base = mkdir(WORK / name)
        self.day = mkdir(self.base / 'day')
        mkdir(self.day / 'plans')
        self.source = mkdir(self.base / 'source')
        self.emitter = mkdir(self.base / 'emitter')
        pw = self.emitter / 'password'
        if not pw.exists():
            pw.write_bytes(PASSWORD.encode() + b'\n')
            os.chmod(pw, 0o600)
        self.tools = mkdir(self.base / 'tools')
        data = RUNNER.read_bytes()
        self.runner = self.tools / ('k9_runner-%s.py' % sha(data))
        if not self.runner.exists():
            self.runner.write_bytes(data)
            os.chmod(self.runner, 0o600)
        self.log = self.base / 'log.ndjson'
        self.clock = EVE
        self.runs = 0

    def copy_from(self, other, *parts):
        for part in parts:
            src, dst = other.base / part, self.base / part
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=shutil.copy2)
            else:
                shutil.copy2(src, dst)
        return self

    def plan(self, op, day=DAY, **over):
        constants = {'package_sha256': PACKAGE, 'code_revision': REVISION, 'act_b_sha256': 'a1' * 32, 'release_sha256': 'fc' * 32,
                     'policy_sha256': 'd2' * 32, 'runner_sha256': sha(RUNNER.read_bytes()), 'risk_source_pins_sha256': source_pins_sha256(),
                     'risk_limits': dict(LIMITS), 'disk_floor_bytes': 214748364800}
        constants.update(over.pop('constants', {}))
        plan = {'schema': 'K9_STEP_PLAN_V1', 'epoch': EPOCH, 'day': day, 'k9_phase': PHASE[op], 'k9_operation': op, 'slot': 'PRIMARY',
                'attempt_key': akey(day, PHASE[op], op), 'request_sha256': 'e1' * 32, 'go_sha256': 'e2' * 32,
                'run_not_after': (self.clock + timedelta(minutes=30)).isoformat(), 'constants': constants, 'network_class': NETWORK[op],
                'database': {'host': 'db', 'port': 5432, 'dbname': 'c3po', 'role': 'c3po_v2_causal_emitter'} if op in ('commit_launch', 'publish_launch') else None,
                'risk': None, 'step_row': {'operation': op}}
        if op == 'bind':
            plan['risk'] = self.risk(day)
        raw = over.pop('_raw', None)
        plan.update(over)
        raw = raw or canon(plan)
        path = self.day / 'plans' / (op + '.json')
        if path.exists():
            os.chmod(path, 0o600)
        path.write_bytes(raw)
        os.chmod(path, 0o600)
        return sha(raw)

    def risk(self, day=DAY, cutoff=None):
        cutoff = cutoff or (self.clock - timedelta(minutes=1)).isoformat()
        windows = {'preflight': [self.clock - timedelta(minutes=1), self.clock + timedelta(minutes=20)],
                   'acquire': [self.clock - timedelta(minutes=1), self.clock + timedelta(minutes=60)],
                   'execute': [self.clock - timedelta(minutes=1), self.clock + timedelta(minutes=90)]}
        pw = {k: {'not_before': a.isoformat(), 'not_after': b.isoformat()} for k, (a, b) in windows.items()}
        order = canon({'schema': 'R2D2_V2_RISK_HOST_ORDER_V1', 'actions': ['READ_PROVIDERS', 'READ_DATABASE', 'WRITE_PRIVATE_RISK_ARTIFACTS'],
                       'scope': {'namespace': 'R2D2-V2-DIAG-R4-' + day, 'session_date': day, 'cutoff_at': cutoff,
                                 'phases': ['preflight', 'acquire', 'execute']}, 'status': 'SIGNED_BY_THE_OWNER_ON_THE_BIND_SHEET'}).decode()
        return {'namespace': 'R2D2-V2-DIAG-R4-' + day, 'cutoff_at': cutoff, 'phase_windows': pw, 'owner_order_text': order,
                'owner_order_sha256': sha(order.encode())}

    def config(self, op, psha, **over):
        cfg = {'filesystem_available_bytes': 274877906944, 'now': self.clock.isoformat(), 'speed': 1.0, 'runner': str(self.runner), 'app': APP, 'log': str(self.log),
               'paths': {'APP': APP, 'DAY_ROOT': str(self.day), 'SOURCE': str(self.source),
                         'EMITTER': str(self.emitter)},
               'argv': ['--plan', str(self.day / 'plans' / (op + '.json')), '--plan-sha256', psha],
               'provider': {'symbols': SYMBOLS, 'token': CANARY, 'fmp_token': CANARY + 'FMP', 'finnhub_token': CANARY + 'FH'},
               'db': {'state': str(self.base / 'db.json'), 'password': PASSWORD, 'dsn': DSN}}
        for key, value in over.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
        return cfg

    def env(self, op=None, **over):
        """The container environment K9W gives `op`: the two fixed words, provider.env and risk-db.env as the step table says."""
        env = {'PATH': '/usr/bin:/bin', 'C3PO_R2D2_V2_PRODUCERS_ENABLED': 'true', 'C3PO_BUILD_SHA': REVISION, 'PYTHONDONTWRITEBYTECODE': '1'}
        if op in (None, 'collect_launch', 'components_launch', 'capture_launch', 'sources_launch'):
            env.update({'C3PO_EODHD_API_TOKEN': CANARY, 'C3PO_FINNHUB_API_TOKEN': CANARY + 'FH', 'C3PO_FMP_API_TOKEN': CANARY + 'FMP'})
        if op in (None, 'sources_launch'):
            env['C3PO_R2D2_RISK_DATABASE_URL'] = DSN
        for key, value in over.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def run(self, op, plan=None, env=None, advance=5, **cfg):
        """One container run of `op`: returns (exit code, stdout bytes, stderr bytes)."""
        psha = plan if plan is not None else self.plan(op)
        self.runs += 1
        path = self.base / ('config-%02d-%s.json' % (self.runs, op))
        path.write_text(json.dumps(self.config(op, psha, **cfg)))
        done = subprocess.run([PYTHON, '-B', '-I', str(HERE / 'harness.py'), str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env if env is not None else self.env(op), timeout=600, cwd=str(self.base))
        self.clock += timedelta(minutes=advance)
        return done.returncode, done.stdout, done.stderr

    def packaged(self, phase, previous=None, debug=False):
        plan = self.day / 'risk' / 'plan'
        cfg = self.config('bind', '0' * 64, mode='packaged', packaged={
            'phase': phase, 'manifest': str(plan / 'HOST_PLAN.json'), 'manifest_sha256': sha((plan / 'HOST_PLAN.json').read_bytes()),
            'go': str(plan / 'GO.json'), 'go_sha256': sha((plan / 'GO.json').read_bytes()), 'spool': str(self.day / 'risk' / 'spool'),
            'previous': previous, 'debug': debug})
        self.runs += 1
        path = self.base / ('config-%02d-packaged-%s.json' % (self.runs, phase))
        path.write_text(json.dumps(cfg))
        done = subprocess.run([PYTHON, '-B', '-I', str(HERE / 'harness.py'), str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=self.env(), timeout=600, cwd=str(self.base))
        self.clock += timedelta(minutes=1)
        return done.returncode

    def receipt(self, op, kind):
        path = self.day / 'receipts' / ('%s.%s.json' % (op, kind))
        return json.loads(path.read_bytes()) if path.exists() else None

    def logs(self, kind=None):
        if not self.log.exists():
            return []
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [r for r in rows if kind is None or r['kind'] == kind]
