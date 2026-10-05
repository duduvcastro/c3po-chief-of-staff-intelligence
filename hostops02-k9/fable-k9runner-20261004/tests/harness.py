"""Child process of the K9 runner tests: one container run, offline.

argv: <config.json>. Installs, before anything imports `datetime`: a clock shim (the configured instant, advancing at
`speed` x real time). Installs stand-ins for every network the release code would use: `httpx` (EODHD REST), `psycopg`
(the emitter role and the restricted risk reader, with a JSON file as the database), `websockets` (the us-quote feed),
and `build_opener` of app.r2d2_v2_risk_transport (EODHD/FMP for sources). Then loads the runner file under test with its
container paths pointed at the sandbox and calls main(argv) (mode run), or the packaged risk host executor (mode
packaged). Nothing here opens a socket."""
import sys, json, time as _time, datetime as _dt
import pandas, exchange_calendars  # noqa: F401  (loaded before the shim: their compiled code keeps the real class)
CFG = json.load(open(sys.argv[1]))
_BASE = _dt.datetime.fromisoformat(CFG['now'])
_R0 = _time.time()
_SPEED = CFG.get('speed', 1.0)
_REAL = _dt.datetime


class _Any(type):  # a real datetime (from pandas, psycopg, fromisoformat on the base class) is still a datetime
    def __instancecheck__(cls, value):
        return isinstance(value, _REAL)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL)


class _Shifted(_dt.datetime, metaclass=_Any):
    @classmethod
    def now(cls, tz=None):
        value = _BASE + _dt.timedelta(seconds=(_time.time() - _R0) * _SPEED)
        value = cls.fromisoformat(value.isoformat())
        return value.astimezone(tz) if tz is not None else value.astimezone(_dt.timezone.utc).replace(tzinfo=None)

    @classmethod
    def utcnow(cls):
        return cls.now(_dt.timezone.utc).replace(tzinfo=None)


_dt.datetime = _Shifted
sys.dont_write_bytecode = True

import asyncio, hashlib, importlib.util, os, types, urllib.parse
from datetime import datetime, timedelta, timezone

LOG = CFG['log']


def log(_kind, **fields):
    with open(LOG, 'a') as handle:
        handle.write(json.dumps({'kind': _kind, 'role': fields.pop('kind', None), **fields}, sort_keys=True, default=str) + '\n')


def sessions(first, last):
    import exchange_calendars
    cal = exchange_calendars.get_calendar('XNYS', start='1990-01-01')
    return [t.date().isoformat() for t in cal.sessions_in_range(first, last)]


P = CFG.get('provider', {})
SYMBOLS = P.get('symbols', [])


def bar(code, day, close=50.0):
    return {'code': code, 'date': day, 'open': close, 'high': close + 1, 'low': close - 1, 'close': close, 'volume': 1000000}


# ---------------------------------------------------------------- httpx stand-in (EODHD REST through EodhdFetcher)
import httpx  # the real module, with its network entry points replaced (no request can leave this process)
HTTPError, ConnectError = httpx.HTTPError, httpx.ConnectError


def _no_network(*a, **k):
    raise AssertionError('NETWORK_ATTEMPTED')


httpx.HTTPTransport.handle_request = _no_network
httpx.AsyncHTTPTransport.handle_async_request = _no_network


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


def _get(url, params=None, timeout=None, follow_redirects=None):
    params = dict(params or {})
    token = params.pop('api_token', None)
    path = urllib.parse.urlsplit(url).path
    log('httpx', path=path, params=params, token_ok=token == P.get('token'), timeout=timeout)
    if P.get('delay'):
        _time.sleep(P['delay'])
    for prefix in P.get('fail_paths', []):
        if path.startswith(prefix):
            raise ConnectError('connect failed for ' + url)
    if path == '/api/exchange-symbol-list/US':
        rows = [{'Code': s, 'Exchange': 'NYSE', 'Type': 'Common Stock'} for s in SYMBOLS] + [{'Code': 'ZZETF', 'Exchange': 'NYSE', 'Type': 'ETF'}]
        return _Response(json.dumps(rows).encode())
    if path == '/api/eod-bulk-last-day/US':
        if params.get('type') == 'splits':
            return _Response(b'[]')
        return _Response(json.dumps([bar(s, params['date']) for s in SYMBOLS]).encode())
    if path.startswith('/api/eod/'):
        code = path[len('/api/eod/'):-3]
        return _Response(json.dumps([dict(bar(code, d), date=d) for d in sessions(params['from'], params['to'])]).encode())
    if path.startswith('/api/splits/'):
        return _Response(b'[]')
    if path == '/api/calendar/earnings':
        return _Response(json.dumps({'earnings': [{'code': 'OTHERCO.US', 'report_date': params['from']}]}).encode())
    if path.startswith('/api/fundamentals/'):
        return _Response(b'{}')
    raise ConnectError('unexpected path')


httpx.get = _get


# ---------------------------------------------------------------- psycopg stand-in (a JSON file is the database)
psycopg = types.ModuleType('psycopg')
pq = types.ModuleType('psycopg.pq')
pq.version = lambda: CFG.get('libpq', 160004)
psycopg.pq = pq


class OperationalError(Exception):
    pass


OperationalError.__module__ = 'psycopg'
psycopg.OperationalError = OperationalError
DB = CFG.get('db', {})


def _load():
    try:
        with open(DB['state']) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {'events': {}, 'artifacts': {}, 'confirmations': {}, 'publications': {}}


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class _Connection:
    autocommit = False

    def __init__(self, kind):
        self.kind, self.state = kind, _load()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        (self.rollback if kind else self.commit)()
        self.close()

    def commit(self):
        if self.kind == 'emitter':
            with open(DB['state'], 'w') as handle:
                json.dump(self.state, handle, sort_keys=True)

    def rollback(self):
        self.state = _load()

    def close(self):
        pass

    def execute(self, sql, params=()):
        now = datetime.now(timezone.utc)
        s = ' '.join(sql.split())
        log('sql', kind=self.kind, head=s[:60])
        if self.kind == 'reader':
            if 'FROM public.ir_events' in s:
                return _Cursor([])
            if s.startswith('SET ') or s.startswith('SELECT clock_timestamp()') or s.startswith('SELECT pg_catalog.transaction_timestamp()'):
                return _Cursor([(now,)])
            if 'pg_auth_members' in s:
                return _Cursor([tuple(DB.get('reader_role', ['c3po_v2_risk_reader', 'c3po_v2_risk_reader'])) + (True,) * 4])
            if "c.relname='ir_events'" in s:
                return _Cursor([('ir_events',) + (True,) * 6])
            if "c.relname='analysis_snapshots'" in s:
                return _Cursor([('analysis_snapshots',) + (True,) * 6])
            if s == 'SHOW transaction_read_only':
                return _Cursor([('on',)])
            if s == 'SHOW transaction_isolation':
                return _Cursor([('repeatable read',)])
            if 'FROM public.analysis_snapshots' in s:
                keys = params[0]
                return _Cursor([(k, '101', {'revenue': 1.0}, now - timedelta(days=3)) for k in keys[:2]])
            raise AssertionError('reader sql ' + s[:80])
        from app.r2d2_v2_causal_emitter import _APPEND_ONLY_BODY, _IMMUTABLE_TRIGGERS
        st = self.state
        if s.startswith('SELECT current_database()'):
            return _Cursor([tuple(DB.get('identity', ['c3po', 'c3po_v2_causal_emitter', 'c3po_v2_causal_emitter', 'origin']))])
        if s.startswith('SELECT current_user = session_user'):
            return _Cursor([(True,) * 5])
        if "has_table_privilege(current_user,c.oid,'SELECT')" in s:
            return _Cursor([(n,) + (True,) * 7 for n in _IMMUTABLE_TRIGGERS])
        if 'FROM pg_catalog.pg_trigger' in s:
            return _Cursor([(r, t, True, True, True, True, _APPEND_ONLY_BODY, True) for r, t in _IMMUTABLE_TRIGGERS.items()])
        if 'pg_advisory_xact_lock' in s:
            return _Cursor([])
        if s.startswith('SELECT clock_timestamp()'):
            return _Cursor([(now,)])
        if s.startswith('SELECT commitment,commitment_sha,build_event_id'):
            row = st['artifacts'].get(params[0] + '|' + str(params[1]))
            return _Cursor([(json.loads(row['commitment']), row['sha'], row['event'])] if row else [])
        if s.startswith('INSERT INTO public.audit_events'):
            event_id, actor, action, kind, subject, detail, at = params
            st['events'][event_id] = {'action': action, 'detail': detail, 'at': at.isoformat()}
            return _Cursor([])
        if s.startswith('INSERT INTO public.r2d2_v2_causal_artifacts'):
            epoch, session, commitment, sha, event = params
            st['artifacts'][epoch + '|' + str(session)] = {'commitment': commitment, 'sha': sha, 'event': event}
            return _Cursor([])
        if s.startswith('SELECT action,occurred_at,detail FROM public.audit_events'):
            e = st['events'].get(params[0])
            return _Cursor([(e['action'], datetime.fromisoformat(e['at']), json.loads(e['detail']))] if e else [])
        if s.startswith('SELECT event_sha,confirmed_at FROM public.r2d2_v2_causal_confirmations'):
            c = st['confirmations'].get(params[0])
            return _Cursor([(c['sha'], datetime.fromisoformat(c['at']))] if c else [])
        if s.startswith('INSERT INTO public.r2d2_v2_causal_confirmations'):
            st['confirmations'].setdefault(params[0], {'sha': params[1], 'at': params[2].isoformat()})
            return _Cursor([])
        if s.startswith('SELECT publication_event_id FROM public.r2d2_v2_causal_publications'):
            p = st['publications'].get(params[0])
            return _Cursor([(p,)] if p else [])
        if s.startswith('INSERT INTO public.r2d2_v2_causal_publications'):
            st['publications'][params[0]] = params[1]
            return _Cursor([])
        raise AssertionError('emitter sql ' + s[:80])


def _connect(*args, **kwargs):
    if args:  # the restricted reader's DSN (risk-db.env)
        log('connect', kind='reader', dsn_ok=args[0] == DB.get('dsn'), options=kwargs.get('options'))
        if args[0] != DB.get('dsn'):
            raise OperationalError('authentication failed')
        return _Connection('reader')
    log('connect', kind='emitter', user=kwargs.get('user'), host=kwargs.get('host'), dbname=kwargs.get('dbname'),
        password_ok=kwargs.get('password') == DB.get('password'), require_auth=kwargs.get('require_auth'))
    if kwargs.get('password') != DB.get('password') or DB.get('down'):
        raise OperationalError('password authentication failed for user')
    return _Connection('emitter')


psycopg.connect = _connect
sys.modules['psycopg'], sys.modules['psycopg.pq'] = psycopg, pq


# ---------------------------------------------------------------- websockets stand-in (us-quote feed)
websockets = types.ModuleType('websockets')


class _Socket:
    def __init__(self, url):
        self.sent, self.authorized, self.index = [], False, 0
        log('websocket', token_ok=url.endswith('api_token=' + P.get('token', '')))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, text):
        self.sent.append(text)

    async def recv(self):
        if not self.authorized:
            self.authorized = True
            return json.dumps({'status_code': 200})
        await asyncio.sleep(0.05)
        symbol = (SYMBOLS + ['NOTLISTED'])[self.index % (len(SYMBOLS) + 1)]
        self.index += 1
        return json.dumps({'s': symbol, 'bp': 49.9, 'ap': 50.1, 't': int(datetime.now(timezone.utc).timestamp() * 1000) - 5})


websockets.connect = lambda url, **kw: _Socket(url)
sys.modules['websockets'] = websockets


# ---------------------------------------------------------------- the runner, pointed at the sandbox
sys.path.insert(0, CFG['app'])
try:
    import app.r2d2_v2_risk_transport as _transport  # noqa: E402
except ImportError:  # a sandbox without the package (PACKAGE_UNAVAILABLE): nothing to patch
    _transport = types.SimpleNamespace()


class _Reply:
    def __init__(self, url, body):
        self.url, self.body, self.status, self.headers, self.offset = url, body, 200, {}, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return self.url

    def read1(self, n):
        chunk = self.body[self.offset:self.offset + n]
        self.offset += len(chunk)
        return chunk


class _Opener:
    def open(self, request, timeout=None):
        url = request.full_url
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        token = query.pop('api_token', None) or query.pop('apikey', None) or query.pop('token', None)
        log('risk_http', path=parts.path, params=query, token_ok=token in (P.get('token'), P.get('fmp_token'), P.get('finnhub_token')))
        if parts.path == '/api/v1/stock/insider-transactions':
            return _Reply(url, json.dumps({'data': [], 'symbol': query.get('symbol')}).encode())
        if parts.path.startswith('/api/v1.1/fundamentals/'):
            return _Reply(url, json.dumps({'General': {'Code': parts.path.rsplit('/', 1)[1].split('.')[0]}, 'Highlights': {}}).encode())
        return _Reply(url, b'[]')


_transport.build_opener = lambda *handlers: _Opener()

spec = importlib.util.spec_from_file_location('k9_runner', CFG['runner'])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
for name, value in CFG['paths'].items():
    setattr(runner, name, value)
runner.DAYS = tuple(CFG.get('days', runner.DAYS))
runner.QUIET = CFG.get('quiet', True)
# Controlled test-side capacity, not evidence of physical disk availability.
# The runner's compiled FLOOR and the signed plan's floor remain unchanged.
if 'filesystem_available_bytes' in CFG:
    _available=CFG['filesystem_available_bytes']
    assert type(_available) is int and _available>=0
    _native_fstatvfs=os.fstatvfs
    def _test_fstatvfs(fd):
        fields=list(_native_fstatvfs(fd))
        fields[1]=1
        fields[4]=_available
        return os.statvfs_result(fields)
    os.fstatvfs=_test_fstatvfs
if 'floor' in CFG:
    runner.FLOOR = CFG['floor']
for _name in ('PACE_REQUESTS', 'PACE_BYTES'):
    if _name in CFG:
        setattr(runner, _name, CFG[_name])
_code_of = runner.code_of


def _logged_code_of(error):  # test-side only: the exception behind a FAILED receipt, kept in the sandbox log
    import traceback
    log('exception', type=type(error).__name__, text=''.join(traceback.format_exception(type(error), error, error.__traceback__))[-1500:])
    return _code_of(error)


runner.code_of = _logged_code_of
if CFG.get('mode', 'run') == 'run':
    code = runner.main(CFG['argv'])
    log('exit', code=code)
    raise SystemExit(code)
# packaged: the risk host executor's own phase function, as K9W's packaged CLI rows would run it
from pathlib import Path  # noqa: E402
from app.r2d2_v2_risk_host_executor import run_host_phase, _run_host_phase  # noqa: E402
k = CFG['packaged']
if k.get('debug'):  # test-side diagnosis: the unwrapped exception of the packaged phase
    import traceback
    try:
        _run_host_phase(phase=k['phase'], manifest_path=Path(k['manifest']), manifest_sha256=k['manifest_sha256'], go_path=Path(k['go']),
                        go_sha256=k['go_sha256'], source_root=Path(CFG['app']), spool_root=Path(k['spool']),
                        previous_receipt_sha256=k.get('previous'), _failure_state={})
    except BaseException as error:
        log('exception', type=type(error).__name__, text=''.join(traceback.format_exception(type(error), error, error.__traceback__))[-2500:])
    raise SystemExit(9)
try:
    result = run_host_phase(phase=k['phase'], manifest_path=Path(k['manifest']), manifest_sha256=k['manifest_sha256'],
                            go_path=Path(k['go']), go_sha256=k['go_sha256'], source_root=Path(CFG['app']),
                            spool_root=Path(k['spool']), previous_receipt_sha256=k.get('previous'))
    log('packaged', status=result['status'], receipt_sha256=result['receipt_sha256'])
except Exception as error:
    log('packaged', status='FAILED', result=getattr(error, 'result', None))
    raise SystemExit(2)
