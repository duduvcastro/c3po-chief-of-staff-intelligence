"""K9 runner, epoch R2D2-V2-SHADOW-2026-10-05: glue run inside the pinned backend image, calling only its certified code.
DESIGN.md (rev 2) is the contract. No action on import."""
import hashlib, json, os, re, signal, stat, sys, threading
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EPOCH = 'R2D2-V2-SHADOW-2026-10-05'
PACKAGE = 'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
REVISION = 'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
DAYS = ('2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09')
APP, DAY_ROOT, SOURCE, EMITTER = '/app', '/c3po-k9-day', '/c3po-source', '/c3po-k9-emitter'
QUIET = True
FLOOR = 214748364800
LIMITS = {'max_symbols': 550, 'max_total_requests': 2200, 'max_body_bytes': 16777216, 'max_total_bytes': 1073741824,
     'max_elapsed_seconds': 3600}
DB = {'host': 'db', 'port': 5432, 'dbname': 'c3po', 'role': 'c3po_v2_causal_emitter'}
# operation: (Act B phase, network class, seconds an ATTACHED step may run, None for a detached LAUNCH)
OPS = {'collect_launch': ('causal_list', 'PROVIDER', None), 'commit_launch': ('causal_list', 'DATABASE', None),
   'publish_launch': ('causal_list', 'DATABASE', None), 'components_launch': ('components', 'PROVIDER', None),
   'sources_launch': ('sources', 'DATABASE_AND_PROVIDER', None), 'bind': ('risk', 'NONE', 30),
   'stage': ('risk', 'NONE', 15), 'capture_launch': ('capture', 'PROVIDER', None)}
PACE_REQUESTS, PACE_BYTES = 2000, 1 << 30
MARGIN = 60  # a LAUNCH stops itself 60 s before run_not_after (K9W's in-container KILL comes at run_not_after - 5 s)
PLAN_KEYS = {'schema', 'epoch', 'day', 'k9_phase', 'k9_operation', 'slot', 'attempt_key', 'request_sha256', 'go_sha256',
      'run_not_after', 'constants', 'network_class', 'database', 'risk', 'step_row'}
CONST_KEYS = {'package_sha256', 'code_revision', 'act_b_sha256', 'release_sha256', 'policy_sha256', 'runner_sha256',
       'risk_source_pins_sha256', 'risk_limits', 'disk_floor_bytes'}
RISK_KEYS = {'namespace', 'cutoff_at', 'phase_windows', 'owner_order_text', 'owner_order_sha256'}
RECEIPT_KEYS = {'schema', 'status', 'code', 'epoch', 'day', 'phase', 'operation', 'attempt_key', 'step_plan_sha256',
        'started_at', 'completed_at', 'package_sha256', 'build_sha', 'outputs', 'aggregates', 'counts'}
PHASES = ('preflight', 'acquire', 'execute')
ACTIONS = ['READ_PROVIDERS', 'READ_DATABASE', 'WRITE_PRIVATE_RISK_ARTIFACTS']
HEX = re.compile('[0-9a-f]{64}')
# Failure codes are a closed set: the runner's own literals (Stop), these release codes passed through, and the
# five categories of code_of. Count keys are a closed set per operation (DESIGN.md section 4).
PASS = set('''PROVIDER_TOKEN_MISSING PROVIDER_REQUEST_FAILED PROVIDER_JSON_INVALID PREVIOUS_SESSION_NOT_CLOSED REGISTRY_EMPTY
REGISTRY_CAPTURED_BEFORE_CLOSE BULK_RECEIVED_BEFORE_SESSION_CLOSE BULK_RESPONSES_INCOMPLETE BULK_PAYLOAD_INVALID
BULK_SPLITS_PAYLOAD_INVALID DAILY_FALLBACK_BUDGET_EXCEEDED FALLBACK_RECEIVED_BEFORE_SESSION_CLOSE FALLBACK_PAYLOAD_INVALID
LAST_SESSION_NOT_OFFICIAL CALENDAR_WINDOW_INVALID LIQUIDITY_WINDOW_INVALID ATR_WINDOW_INVALID EOD_RECEIVED_BEFORE_SESSION_CLOSE
EOD_PAYLOAD_INVALID SPLITS_PAYLOAD_INVALID SYMBOL_INVALID CALENDAR_EMPTY_OR_INVALID CAUSAL_LIST_UNREADABLE CAUSAL_LIST_INVALID
CAPTURE_WINDOW_ALREADY_CLOSED QUOTE_FEED_AUTHORIZATION_FAILED CAUSAL_EMITTER_OFF EPOCH_INVALID CAUSAL_SESSION_INVALID
CAUSAL_TRANSACTION_REQUIRED CAUSAL_ROLE_NOT_RESTRICTED CAUSAL_TABLE_AUTHORITY_INVALID CAUSAL_APPEND_ONLY_TRIGGERS_INVALID
CAUSAL_STORED_COMMITMENT_HASH_MISMATCH CAUSAL_SLOT_INPUT_CONFLICT CAUSAL_COMMITMENT_MISMATCH CAUSAL_BUILD_RECEIPT_CONFLICT
CAUSAL_BUILD_CROSSED_CUTOFF CAUSAL_INPUT_NOT_STABLE_DURING_BUILD CAUSAL_AUDIT_EVENT_MISSING CAUSAL_AUDIT_EVENT_CONFLICT
CAUSAL_CONFIRMATION_CONFLICT CAUSAL_DATABASE_CLOCK_REVERSED CAUSAL_DATABASE_CLOCK_UNAVAILABLE
CAUSAL_COMMIT_NOT_CONFIRMED_BEFORE_CUTOFF CAUSAL_BUILD_REQUIRED CAUSAL_PUBLICATION_LATE CAUSAL_PUBLICATION_REFERENCE_INVALID
CAUSAL_PUBLICATION_RECEIPT_CONFLICT CAUSAL_PUBLIC_FIELDS CAUSAL_FILE_NOT_PRIVATE CAUSAL_FILE_HARDLINK CAUSAL_FILE_CONFLICT
CAUSAL_FILE_SIZE_LIMIT CAUSAL_PATH_INVALID CAUSAL_ROOT_INVALID CAUSAL_ENVELOPE_FIELDS CAUSAL_ENVELOPE_SIZE_LIMIT CAUSAL_LIST_LATE
CAUSAL_INPUT_SIZE_LIMIT CAUSAL_INPUT_SCHEMA CAUSAL_CALENDAR_INVALID CALENDAR_SESSION_INVALID REGISTRY_CAPTURE_NOT_D_MINUS_ONE
REGISTRY_COVERAGE_UNVERIFIED AUDIT_RECEIPT_UNVERIFIED PUBLICATION_RECEIPT_UNVERIFIED SOURCE_PIN_MISMATCH
SOURCE_PIN_CLOSURE_INCOMPLETE SOURCE_CHANGED SOURCE_NOT_REGULAR SOURCE_PATH_INVALID RUNTIME_SOURCE_ROOT_MISMATCH QUARTER_INVALID
CLOCK_INVALID TRANSPORT_BUDGET_INVALID'''.split())
CATEGORY = {'ProducerError': 'PRODUCER_FAILED', 'ShadowIntegrityError': 'CAUSAL_INTEGRITY_FAILED', 'SourceUnavailable': 'SOURCE_UNAVAILABLE'}
REASONS = ('DATA_INELIGIBLE', 'CLASSIFICATION_EXCLUDED', 'CLOSE_BELOW_5', 'ADV_BELOW_15000000', 'N_CUT_EXCLUDED', 'NOT_IN_CAUSAL_LIST')
TICKS = ('PAYLOAD_ERROR', 'NOT_JSON', 'NOT_OBJECT', 'SYMBOL_NOT_LISTED', 'TICK_CLOCK_INVALID', 'TICK_IN_FUTURE', 'TICK_REGRESSES')
DIAGNOSTICS = tuple(a + b for a in ('DAILY_', 'RISK_', 'EARNINGS_') for b in ('COMPONENT_ABSENT', 'DOCUMENT_INVALID', 'COMPONENT_INVALID')) + ('REGISTRY_ROW_ABSENT',)
FETCH = ('FETCH_OK', 'HTTP_FAILED', 'TRANSPORT_FAILED', 'BODY_REJECTED', 'JSON_INVALID')
SYM = re.compile('[A-Z0-9][A-Z0-9.-]{0,19}')
NAME = re.compile('[A-Za-z0-9][A-Za-z0-9._=-]{0,127}')
OUTKEY = re.compile(r'(day|source)(/[A-Za-z0-9][A-Za-z0-9._=-]{0,127}){1,8}')
COUNTKEY = re.compile('[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}')  # K9R's K9_COUNT_KEY
FL = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
MB = 1 << 20
OUT = 1


class Stop(BaseException):  # never swallowed by the release code's `except Exception`
  def __init__(self, code, status='REFUSED'):
    super().__init__(code)
    self.code, self.status = code, status


class Deadline(BaseException):
  pass


def need(ok, code, status='REFUSED'):
  if not ok:
    raise Stop(code, status)


def fail(ok, code):
  need(ok, code, 'FAILED')


def now():
  return datetime.now(timezone.utc)


def iso(t):
  return t.astimezone(timezone.utc).isoformat()


def instant(v):
  need(isinstance(v, str) and len(v) <= 40, 'PLAN_INVALID')
  try:
    t = datetime.fromisoformat(v.replace('Z', '+00:00'))
  except ValueError:
    raise Stop('PLAN_INVALID') from None
  need(t.utcoffset() is not None and t.utcoffset().total_seconds() == 0, 'PLAN_INVALID')
  return t


def canon(v):
  return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def enc(v):
  return canon(v) + b'\n'


def sha(b):
  return hashlib.sha256(b).hexdigest()


def strict(raw):
  def pairs(items):
    d = {}
    for k, v in items:
      if k in d:
        raise ValueError('DUPLICATE_JSON_KEY')
      d[k] = v
    return d

  def bad(_):
    raise ValueError('NON_FINITE_JSON')
  return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def akey(day, phase, op):
  return sha(json.dumps([EPOCH, day, phase, op], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def code_of(e):
  if isinstance(e, Stop):
    return e.code
  a = getattr(e, 'args', ())
  t = a[0].split(':', 1)[0] if a and isinstance(a[0], str) else ''
  if t in PASS:
    return t
  if (type(e).__module__ or '').startswith('psycopg'):
    return 'DATABASE_FAILURE'
  return 'FILESYSTEM_FAILURE' if isinstance(e, OSError) else CATEGORY.get(type(e).__name__, 'UNCLASSIFIED_FAILURE')


def pick(d, names):
  """Counts in K9R's grammar with a closed key set: `names` maps each source key to its constant count name (every name
  present, an integer 0..10^7, 0 when absent)."""
  d = d if isinstance(d, dict) else {}
  return {n: min(d[k], 10 ** 7) if type(d.get(k)) is int and d[k] >= 0 else 0 for k, n in names.items()}


def bucket(d, names, other):
  """Counts keyed by the producer's constant codes: the listed codes lower-cased, everything else summed under `other`."""
  o = dict.fromkeys([n.lower() for n in names] + [other], 0)
  for k, v in (d.items() if isinstance(d, dict) else ()):
    if type(v) is int and v >= 0:
      k = k.lower() if k in names else other
      o[k] = min(o[k] + v, 10 ** 7)
  return o


def okcounts(d, depth=0):
  """K9R's k9_counts: at most 64 keys in K9_COUNT_KEY, integers 0..10^7, one nested level."""
  return type(d) is dict and len(d) <= 64 and all(isinstance(k, str) and COUNTKEY.fullmatch(k) and (
    (type(v) is int and 0 <= v <= 10 ** 7) or (depth == 0 and okcounts(v, 1))) for k, v in d.items())


def pins():
  """RISK_HOST_SOURCE_PINS_V1 over every /app/app/**/*.py (the executor's _source_pins set), standard library only."""
  r = Path(APP)
  return enc({'schema': 'RISK_HOST_SOURCE_PINS_V1', 'files': {q.relative_to(r).as_posix(): sha(q.read_bytes()) for q in (r / 'app').rglob('*.py')}})


# ---------------------------------------------------------------- files: descriptors only, never following a link
def child(fd, name, make=False, exclusive=False):
  need(isinstance(name, str) and NAME.fullmatch(name) is not None, 'PATH_INVALID')
  if make:
    try:
      os.mkdir(name, 0o700, dir_fd=fd)
    except FileExistsError:
      need(not exclusive, 'OUTPUT_ALREADY_PRESENT')
  c = os.open(name, FL, dir_fd=fd)
  s = os.fstat(c)
  if s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o700:
    os.close(c)
    raise Stop('DIRECTORY_NOT_PRIVATE')
  return c


def walk(fd, parts, make=False):
  cur = os.dup(fd)
  try:
    for p in parts:
      n = child(cur, p, make)
      os.close(cur)
      cur = n
    return cur
  except BaseException:
    os.close(cur)
    raise


def root(path):
  """A mount point of the container: ancestors opened without following a link, the mount itself private."""
  parts = [p for p in path.split('/') if p]
  fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
  try:
    for p in parts[:-1]:
      n = os.open(p, FL, dir_fd=fd)
      os.close(fd)
      fd = n
    return child(fd, parts[-1])
  finally:
    os.close(fd)


def readat(base, parts, limit=128 * MB):
  fd = walk(base, parts[:-1])
  try:
    return readf(fd, parts[-1], limit)
  finally:
    os.close(fd)


def exists(fd, name):
  try:
    os.stat(name, dir_fd=fd, follow_symlinks=False)
    return True
  except FileNotFoundError:
    return False


def readf(fd, name, limit=128 * MB):
  f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
  try:
    a = os.fstat(f)
    need(stat.S_ISREG(a.st_mode) and a.st_size <= limit, 'INPUT_FILE_INVALID')
    need(a.st_uid == os.geteuid() and not a.st_mode & 0o077 and a.st_nlink == 1, 'INPUT_FILE_NOT_PRIVATE')
    chunks, n = [], 0
    while True:
      b = os.read(f, 4 * MB)
      if not b:
        break
      chunks.append(b)
      n += len(b)
      need(n <= limit, 'INPUT_FILE_INVALID')
    z = os.fstat(f)
    need((a.st_ino, a.st_size, a.st_mtime_ns) == (z.st_ino, z.st_size, z.st_mtime_ns) and n == a.st_size, 'INPUT_CHANGED')
    return b''.join(chunks)
  finally:
    os.close(f)


def put(fd, name, data):
  """Exclusive, durable creation (private temporary, fsync, link: never a partial file under the name)."""
  need(NAME.fullmatch(name) is not None, 'PATH_INVALID')
  t = '.k9-' + os.urandom(8).hex()
  f = os.open(t, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
  try:
    with os.fdopen(f, 'wb') as h:
      h.write(data)
      h.flush()
      os.fsync(h.fileno())
    os.link(t, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
  finally:
    os.unlink(t, dir_fd=fd)
  os.fsync(fd)
  return sha(data)


def put_same(fd, name, data):
  try:
    return put(fd, name, data)
  except FileExistsError:
    fail(readf(fd, name) == data, 'OUTPUT_CONFLICT')
    return sha(data)


def aggregate(fd, name):
  """K9R's aggregate: sha256 of the canonical JSON list of the sorted sha256 of every regular file of the directory."""
  d = walk(fd, [name])
  try:
    digests = []
    for n in sorted(os.listdir(d)):
      fail(stat.S_ISREG(os.stat(n, dir_fd=d, follow_symlinks=False).st_mode), 'AGGREGATE_NOT_REGULAR')
      digests.append(sha(readf(d, n, 16 * MB)))
    return {'files': len(digests), 'sha256': sha(canon(sorted(digests)))}, sorted(digests)
  finally:
    os.close(d)


def silence():
  global OUT
  OUT = os.dup(1)
  n = os.open(os.devnull, os.O_WRONLY)
  os.dup2(n, 1)
  os.dup2(n, 2)
  os.close(n)
  import logging, warnings
  logging.disable(logging.CRITICAL)
  warnings.simplefilter('ignore')
  sys.excepthook = lambda *a: None
  threading.excepthook = lambda a: None


# ---------------------------------------------------------------- one run
class Run:
  def __init__(self, plan, psha, op):
    self.plan, self.psha, self.op, self.day = plan, psha, op, plan['day']
    self.D = date.fromisoformat(self.day)
    self.phase = OPS[op][0]
    self.calls, self.counts, self.progress, self.pkg, self._src = 0, {}, {}, '0' * 64, None
    self.stop = None
    self.dd = root(DAY_ROOT)
    try:  # opened first: stage's Dd is read-only with receipts/ mounted writable over it
      self.rec = child(self.dd, 'receipts')
    except FileNotFoundError:
      self.rec = child(self.dd, 'receipts', make=True)

  @property
  def src(self):
    if self._src is None:
      self._src = root(SOURCE)
    return self._src

  def check(self):
    if self.stop is not None and now() >= self.stop:
      raise Deadline()

  def validate(self):
    p, op = self.plan, self.op
    need(set(p) == PLAN_KEYS and p['slot'] in ('PRIMARY', 'SPARE') and isinstance(p['step_row'], dict), 'PLAN_INVALID')
    need(all(isinstance(p[k], str) and HEX.fullmatch(p[k]) for k in ('request_sha256', 'go_sha256')), 'PLAN_INVALID')
    self.rna = instant(p['run_not_after'])
    c = p['constants']
    need(isinstance(c, dict) and set(c) == CONST_KEYS, 'PLAN_INVALID')
    need(c['package_sha256'] == PACKAGE and c['code_revision'] == REVISION and c['risk_limits'] == LIMITS
      and c['disk_floor_bytes'] == FLOOR, 'CONSTANTS_NOT_THE_COMPILED_ONES')
    need(all(isinstance(c[k], str) and HEX.fullmatch(c[k]) for k in
        ('act_b_sha256', 'release_sha256', 'policy_sha256', 'runner_sha256', 'risk_source_pins_sha256')), 'PLAN_INVALID')
    need(p['network_class'] == OPS[op][1], 'NETWORK_CLASS_NOT_OF_THIS_OPERATION')
    need(p['database'] == (DB if op in ('commit_launch', 'publish_launch') else None), 'DATABASE_NOT_OF_THIS_OPERATION')
    need((op == 'bind') == isinstance(p['risk'], dict) and (p['risk'] is None or set(p['risk']) == RISK_KEYS), 'PLAN_INVALID')
    with open(__file__, 'rb') as h:
      mine = sha(h.read())
    m = re.fullmatch('k9_runner-([0-9a-f]{64})[.]py', os.path.basename(__file__))
    need(m is not None and m.group(1) == mine == c['runner_sha256'], 'RUNNER_NOT_THE_SIGNED_ONE')

  def pred(self, op):
    """A predecessor's COMPLETE runner receipt, by fixed path."""
    try:
      need(not exists(self.rec, op + '.FAILED.json'), 'PREDECESSOR_NOT_COMPLETE')
      raw = readf(self.rec, op + '.RECEIPT.json', 256 * 1024)
      d = strict(raw)
      ph = OPS[op][0]
      need(isinstance(d, dict) and set(d) == RECEIPT_KEYS and d['schema'] == 'K9_STEP_RECEIPT_V1'
        and d['status'] == 'COMPLETE' and d['code'] is None and d['epoch'] == EPOCH and d['day'] == self.day
        and d['operation'] == op and d['phase'] == ph and d['attempt_key'] == akey(self.day, ph, op)
        and d['package_sha256'] == PACKAGE and d['build_sha'] == REVISION and isinstance(d['outputs'], dict),
        'PREDECESSOR_NOT_COMPLETE')
      return raw, d
    except (OSError, ValueError):
      raise Stop('PREDECESSOR_NOT_COMPLETE') from None

  def pred_bytes(self, d, key):
    """A file a predecessor's receipt names, read again; its bytes must be the ones the receipt hashed."""
    need(key in d['outputs'], 'PREDECESSOR_NOT_COMPLETE')
    try:
      raw = self.at(key)
    except FileNotFoundError:
      raise Stop('PREDECESSOR_OUTPUT_ABSENT') from None
    need(sha(raw) == d['outputs'][key], 'PREDECESSOR_OUTPUT_CHANGED')
    return raw

  def at(self, key):
    parts = key.split('/')
    return readat(self.dd if parts[0] == 'day' else self.src, parts[1:])

  def symbols(self, publish):
    raw = self.pred_bytes(publish, 'day/control/symbols.txt')
    names = raw.decode('ascii').split('\n')
    need(names[-1] == '', 'LIST_INVALID')
    names = names[:-1]
    need(0 < len(names) <= 550 and len(set(names)) == len(names) and all(SYM.fullmatch(n) for n in names), 'LIST_INVALID')
    return names

  def producers(self):
    need(os.environ.get('C3PO_R2D2_V2_PRODUCERS_ENABLED', '').lower() == 'true', 'PRODUCERS_NOT_ENABLED')

  def fetcher(self):
    """Exactly as the packaged main() builds it (retries 2, the settings' timeout), counted and bound to the deadline."""
    from app.config import get_settings
    from app.r2d2_v2_producer_daily import EodhdFetcher
    s = get_settings()
    f = EodhdFetcher(s.eodhd_base_url, s.eodhd_api_token, timeout=s.market_data_timeout_seconds)
    lock = threading.Lock()

    def fetch(path, params):
      self.check()
      with lock:
        self.calls += 1
        self.progress['logical_fetch_calls'] = self.calls
      r = f(path, params)
      self.check()
      return r
    return fetch

  def factory(self):
    """The emitter's own restricted role; password from the mounted private file; no DSN taken from the environment."""
    import psycopg
    from psycopg import pq
    need(pq.version() >= 160000, 'LIBPQ16_REQUIRED')
    need(not any(k.startswith('PG') or k in ('C3PO_CAUSAL_EMITTER_DSN', 'C3PO_DATABASE_URL', 'C3PO_R2D2_RISK_DATABASE_URL')
          for k in os.environ), 'EMITTER_ENVIRONMENT_NOT_CLEAN')
    fd = root(EMITTER)
    try:
      pw = readf(fd, 'password', 1024)
    finally:
      os.close(fd)
    pw = pw[:-1] if pw.endswith(b'\n') else pw
    need(pw and all(32 < c < 127 for c in pw), 'EMITTER_PASSWORD_INVALID')
    pw = pw.decode('ascii')

    def connect():
      self.check()
      c = psycopg.connect(host=DB['host'], port=DB['port'], dbname=DB['dbname'], user=DB['role'], password=pw,
                require_auth='scram-sha-256', options='', autocommit=False, connect_timeout=10,
                application_name='c3po-k9-runner')
      try:
        r = c.execute("SELECT current_database(), current_user, session_user, "
               "current_setting('session_replication_role')").fetchone()
        fail(tuple(r) == (DB['dbname'], DB['role'], DB['role'], 'origin'), 'EMITTER_IDENTITY_MISMATCH')
        c.rollback()
        return c
      except BaseException:
        c.close()
        raise
    return connect

  # ------------------------------------------------------------ causal list
  def op_collect_launch(self):
    self.producers()
    from app.r2d2_v2_producer_daily import produce_causal_inputs
    os.close(child(self.dd, 'inputs', make=True, exclusive=True))
    r = produce_causal_inputs(self.fetcher(), session_date=self.D, output_dir=Path(DAY_ROOT) / 'inputs')
    raw = {n: readat(self.dd, ['inputs', n]) for n in ('registry.json', 'registry.receipt.json', 'daily_contract.json', 'daily_contract.receipt.json')}
    out = {'day/inputs/' + n: sha(b) for n, b in raw.items()}
    fail(out['day/inputs/registry.json'] == r['registry_sha256'] and out['day/inputs/daily_contract.json'] == r['daily_contract_sha256']
      and out['day/inputs/registry.receipt.json'] == r['registry_receipt_sha256']
      and out['day/inputs/daily_contract.receipt.json'] == r['daily_contract_receipt_sha256'], 'OUTPUT_CHANGED')
    self.counts = {'registry_symbols': r['registry_symbols'], 'complete_bars': r['complete_bars'], 'bar_conflicts': r['bar_conflicts'],
           'logical_fetch_calls': self.calls, 'registry_counts': pick(strict(raw['registry.receipt.json'])['counts'], {'provider_rows': 'provider_rows',
           'kept': 'kept_rows', 'skipped_exchange': 'skipped_exchange', 'skipped_symbol': 'skipped_symbol', 'duplicates': 'duplicate_rows'}),
           'daily_counts': pick(strict(raw['daily_contract.receipt.json'])['counts'], {'symbols': 'daily_symbols', **{x: x for x in (
           'complete_bars', 'bar_conflicts', 'fallback_symbols', 'fallback_bars_filled', 'fallback_symbols_unresolved',
           'symbols_with_unreadable_splits', 'unattributable_split_rows')}})}
    return out, {}

  def op_commit_launch(self):
    _, c = self.pred('collect_launch')
    reg = self.pred_bytes(c, 'day/inputs/registry.json')
    daily = self.pred_bytes(c, 'day/inputs/daily_contract.json')
    need(now() < datetime.combine(self.D, dtime(), ZoneInfo('America/New_York')) - timedelta(minutes=10), 'COMMIT_AFTER_ITS_LATEST_START')
    cf = child(self.dd, 'causal', make=True)
    try:
      need(not exists(cf, 'commitment.private.json') and not exists(cf, 'build_audit_receipt.json'), 'OUTPUT_ALREADY_PRESENT')
      from app.r2d2_v2_calendar import ShadowCalendar
      from app.r2d2_v2_causal_emitter import PostgresCausalListEmitter
      from app.r2d2_v2_store import canonical
      fac = self.factory()
      built = PostgresCausalListEmitter(fac, ShadowCalendar(), enabled=True).build(
        epoch=EPOCH, day=self.D, registry_bytes=reg, daily_bytes=daily)
      cm, au = built['commitment'], built['audit_receipt']
      fail(cm['epoch'] == EPOCH and cm['session'] == self.day and cm['registry_sha256'] == sha(reg)
        and cm['daily_contract_sha256'] == sha(daily), 'COMMITMENT_NOT_OF_THIS_STEP')
      out = {'day/causal/commitment.private.json': put(cf, 'commitment.private.json', canonical(cm)),
         'day/causal/build_audit_receipt.json': put(cf, 'build_audit_receipt.json', canonical(au))}
    finally:
      os.close(cf)
    k = cm['counts']
    self.counts = {'n_cut': cm['n_cut'], 'commit_confirmed': 1, 'commitment_counts': pick(k, {'registry': 'registry_rows', 'filtered': 'filtered_symbols',
           'liquidity_passed': 'liquidity_passed', 'selected': 'selected_symbols'}), 'exclusion_reasons': bucket(k.get('reasons'), REASONS, 'other_reasons'),
           'list_coverage': pick(cm['coverage'], {'numerator': 'coverage_numerator', 'denominator': 'coverage_denominator'})}
    return out, {}

  def op_publish_launch(self):
    _, c = self.pred('commit_launch')
    cm_raw = self.pred_bytes(c, 'day/causal/commitment.private.json')
    os.close(child(self.dd, 'relay', make=True))
    self.src
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_causal_emitter import PostgresCausalListEmitter, ConfirmedCausalReceiptVerifier
    from app.r2d2_v2_causal_files import FileRelaySink, write_private_envelope
    from app.r2d2_v2_sources import FileShadowSource
    from app.r2d2_v2_store import canonical
    fac, cal = self.factory(), ShadowCalendar()
    env = PostgresCausalListEmitter(fac, cal, enabled=True).publish(epoch=EPOCH, day=self.D, sink=FileRelaySink(Path(DAY_ROOT) / 'relay'))
    fail(canonical(env['commitment']) == cm_raw, 'COMMITMENT_CHANGED')
    write_private_envelope(Path(SOURCE), env)
    with fac() as conn:
      t = conn.execute('SELECT clock_timestamp()').fetchone()[0]
    got = FileShadowSource(SOURCE, causal_receipt_verifier=ConfirmedCausalReceiptVerifier(fac)).causal_list(EPOCH, self.D, t, cal)
    need(got.get('status') == 'AVAILABLE' and not got.get('diagnostics') and got.get('commitment_sha256') == sha(cm_raw),
      'CAUSAL_READBACK_REFUSED', 'FAILED')
    names = got['symbols']
    fail(isinstance(names, list) and 0 < len(names) <= 550 and len(set(names)) == len(names)
      and all(isinstance(n, str) and SYM.fullmatch(n) for n in names), 'LIST_INVALID')
    ctl = child(self.dd, 'control', make=True)
    cf = walk(self.dd, ['causal'])
    try:
      out = {'day/control/symbols.txt': put_same(ctl, 'symbols.txt', ('\n'.join(names) + '\n').encode('ascii')),
         'day/causal/publication_receipt.json': put_same(cf, 'publication_receipt.json', canonical(env['publication_receipt']))}
    finally:
      os.close(ctl)
      os.close(cf)
    for key in ('source/causal_list/%s/%s.json' % (EPOCH, self.day), 'day/relay/causal_publications/%s/%s.json' % (EPOCH, self.day)):
      out[key] = sha(self.at(key))
    self.counts = {'selected_count': len(names), 'readback_available': 1, 'channel_relay': 1}
    return out, {}

  # ------------------------------------------------------------ components of the committed list
  def op_components_launch(self):
    self.producers()
    _, c = self.pred('commit_launch')
    _, p = self.pred('publish_launch')
    cm = strict(self.pred_bytes(c, 'day/causal/commitment.private.json'))
    names = self.symbols(p)
    need(names == cm['list'], 'LIST_NOT_THE_COMMITTED_ONE')
    reg = readat(self.dd, ['inputs', 'registry.json'])
    need(sha(reg) == cm['registry_sha256'], 'REGISTRY_NOT_THE_COMMITTED_ONE')
    from app.r2d2_v2_producer_daily import produce_instrument_components
    from app.r2d2_v2_producer_earnings import produce_earnings
    comp = child(self.src, 'components', make=True)
    try:
      dfd = child(comp, self.day, make=True, exclusive=True)
    finally:
      os.close(comp)
    base = Path(SOURCE) / 'components' / self.day
    k = 'source/components/%s/' % self.day
    try:
      out = {k + 'registry.json': put(dfd, 'registry.json', reg)}
      fetch = self.fetcher()
      r = produce_instrument_components(fetch, names, session_date=self.D, output_dir=base)
      e = produce_earnings(fetch, names, session_date=self.D, output_dir=base)
      agg, digests = aggregate(dfd, 'daily_61')
      fail(digests == sorted(r['component_sha256'].values()) and len(digests) == len(names), 'OUTPUT_CHANGED')
      out[k + 'earnings.json'] = sha(readf(dfd, 'earnings.json'))
      fail(out[k + 'earnings.json'] == e['sha256'], 'OUTPUT_CHANGED')
    finally:
      os.close(dfd)
    self.counts = {'daily_components': {'component_symbols': len(names), 'incomplete_components': len(r['incomplete'])},
           'earnings_counts': pick({x.lower(): v for x, v in e['counts'].items()}, {'symbols': 'earnings_symbols', 'live_symbols': 'live_symbols',
           'covered': 'covered_symbols', 'with_events': 'with_events', 'excluded': 'excluded_symbols', **{x.lower(): x.lower() for x in (
           'EARNINGS_WITHIN_HORIZON', 'EARNINGS_EXPECTED_WITHIN_HORIZON', 'EARNINGS_NOT_TRACKED', 'EARNINGS_LAST_REPORT_UNKNOWN',
           'EARNINGS_EVIDENCE_INVALID', 'EARNINGS_SOURCE_UNAVAILABLE')}}), 'logical_fetch_calls': self.calls}
    return out, {k + 'daily_61': agg}

  # ------------------------------------------------------------ sources (port of E28 operations/sources.py acquire + official_reader)
  def official(self, names, check):
    import psycopg
    from app.r2d2_v2_risk_runner import ReadOnlyInsiderDatabaseReader as R
    dsn = os.environ.get('C3PO_R2D2_RISK_DATABASE_URL')
    need(bool(dsn), 'RESTRICTED_DSN_REQUIRED')
    check()
    with psycopg.connect(dsn, connect_timeout=15, options='-c default_transaction_read_only=on') as c:
      c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
      c.execute("SET LOCAL statement_timeout='15s'")
      role = c.execute(R.ROLE_SQL).fetchone()
      old = c.execute(R.ACL_SQL).fetchall()
      new = c.execute(R.ACL_SQL.replace("c.relname='ir_events'", "c.relname='analysis_snapshots'")).fetchall()
      fail(tuple(role[:2]) == ('c3po_v2_risk_reader', 'c3po_v2_risk_reader') and all(x is True for x in role[2:]), 'ROLE_NOT_RESTRICTED')
      fail(all(len(rows) == 1 and all(x is True for x in rows[0][1:]) for rows in (old, new)), 'ACL_NOT_RESTRICTED')
      fail(c.execute('SHOW transaction_read_only').fetchone()[0] == 'on'
        and c.execute('SHOW transaction_isolation').fetchone()[0] == 'repeatable read', 'TRANSACTION_NOT_READONLY_REPEATABLE')
      observed = c.execute('SELECT clock_timestamp()').fetchone()[0]
      rows = c.execute("SELECT DISTINCT ON(entity_key) entity_key,id::text,outputs,published_at FROM public.analysis_snapshots "
              "WHERE analysis_type='official_fundamentals' AND entity_key=ANY(%s) AND published_at<=%s "
              "ORDER BY entity_key,published_at DESC,id DESC", (['US:' + n for n in names], observed)).fetchall()
      completed = c.execute('SELECT clock_timestamp()').fetchone()[0]
      c.rollback()
    check()
    return {r[0]: r for r in rows}, observed, {'transaction_read_only': True, 'role_verified': True, 'rows': len(rows),
                         'query_started_at': observed.isoformat(), 'query_completed_at': completed.isoformat()}

  def op_sources_launch(self):
    import time
    _, p = self.pred('publish_launch')
    names = self.symbols(p)
    need(all(re.fullmatch(r'[A-Z][A-Z0-9.-]{0,14}', n) and not n.endswith('.SA') for n in names), 'LIST_INVALID')
    v = os.fstatvfs(self.dd)
    need(v.f_bavail * v.f_frsize >= FLOOR, 'DISK_FREE_BELOW_FLOOR')
    from app.config import get_settings
    from app.r2d2_v2_risk_acquisition import RiskAcquirer
    from app.r2d2_v2_risk_transport import BoundedRiskTransport
    from app.market_data.fmp import FmpClient
    st = get_settings()
    conf = {'eodhd': st.eodhd_api_token, 'fmp': st.fmp_api_token}
    transport = BoundedRiskTransport(lambda q: conf[q], max_requests=2000, requests_per_minute=60, timeout=15)
    ns = 'R2D2-V2-DIAG-R4-' + self.day
    risk = child(self.dd, 'risk', make=True)
    plan = child(risk, 'plan', make=True, exclusive=True)
    blobs = child(plan, 'sources', make=True, exclusive=True)
    os.close(risk)
    size = [0]
    check = self.check

    def store(name, value, fd=blobs, prefix='sources/'):
      raw = value if isinstance(value, bytes) else enc(value)
      size[0] += len(raw)
      fail(size[0] <= LIMITS['max_total_bytes'], 'SPOOL_BUDGET')
      self.progress['bytes_written_kib'] = size[0] >> 10
      return {'path': prefix + name, 'sha256': put(fd, name, raw)}

    progress = self.progress

    class Pace:  # E28's pacing: 50 requests per 61 s, at most 2,000 requests and 1 GiB of bodies; stops are BaseException
      times, count, bytes = [], 0, 0

      def __call__(self, request):
        fail(request.provider in ('eodhd', 'fmp'), 'PROVIDER_NOT_ALLOWED')
        fail(self.bytes <= PACE_BYTES, 'BODY_BUDGET')
        check()
        t = time.monotonic()
        self.times = [x for x in self.times if t - x < 61]
        if len(self.times) >= 50:
          time.sleep(max(0, 61 - (t - self.times[0])))
          check()
          t = time.monotonic()
          self.times = [x for x in self.times if t - x < 61]
        fail(len(self.times) < 50 and self.count < PACE_REQUESTS, 'REQUEST_BUDGET')
        self.times.append(t)
        self.count += 1
        progress['http_attempts'] = self.count
        reply = transport(request)
        self.bytes += len(reply.body)
        progress['http_kib'] = self.bytes >> 10
        check()
        fail(self.bytes <= PACE_BYTES, 'BODY_BUDGET')
        return reply

    def clock():
      check()
      return now()
    try:
      started = now()
      mapping, observed, proof = self.official(names, check)
      dbref = store('database.READONLY.json', proof)
      pace = Pace()
      acq = RiskAcquirer(pace, clock)
      year, quarter = FmpClient.latest_reportable_13f_quarter(clock().date())
      entries, census, timings = [], [], []
      counts = {k: {} for k in ('fundamentals', 'grades', 'institutional')}
      for i, n in enumerate(names):
        at = clock()
        srcs, failed = {}, []
        ov = mapping.get('US:' + n)
        off = {'symbol': n, 'market': 'US', 'outputs': ov[2] if ov else None, 'absence_proven': ov is None, 'query_receipt': dbref}
        if ov:
          off.update(snapshot_id=ov[1], available_at=ov[3].isoformat(), source_at=ov[3].isoformat())
        srcs['official'] = {'body': store('%04d.official.json' % i, off), 'received_at': observed.isoformat(),
                  'source_id': 'RESTRICTED_ROLE_REPEATABLE_READ_READ_ONLY'}
        for m in ('fundamentals', 'grades', 'institutional'):
          res = acq.institutional(n, year=year, quarter=quarter) if m == 'institutional' else getattr(acq, m)(n)
          fail(len(res.receipts) == 1, 'RECEIPT_COUNT')
          r = res.receipts[0]
          body = store('%04d.%s.body' % (i, m), r.body)
          rec = store('%04d.%s.receipt.json' % (i, m), {
            'request': {'provider': r.request.provider, 'path': r.request.path, 'parameters': dict(r.request.parameters)},
            'started_at': r.started_at.isoformat(), 'received_at': r.received_at.isoformat(), 'status': r.status,
            'payload_sha256': r.payload_sha256, 'diagnostic': r.diagnostic})
          fail(r.payload_sha256 == body['sha256'], 'SOURCE_INTEGRITY')
          s = r.diagnostic if r.diagnostic in FETCH else 'HTTP_FAILED' if r.diagnostic or r.status != 200 else 'FETCH_OK'
          if s == 'FETCH_OK':
            try:
              strict(r.body)
            except (ValueError, UnicodeError):
              s = 'JSON_INVALID'
          counts[m][s] = counts[m].get(s, 0) + 1
          if s != 'FETCH_OK':
            failed.append(m)
          srcs[m] = {'body': body, 'receipt': rec}
        entries.append({'symbol': n, 'market': 'US', 'sources': srcs})
        census.append({'entry_sha256': sha(n.encode()), 'complete': not failed, 'failed_methods': failed})
        timings.append({'entry_sha256': sha(n.encode()), 'elapsed_seconds': (clock() - at).total_seconds()})
      bad = sum(not x['complete'] for x in census)
      cref = store('census.json', {'symbols': len(names), 'complete': len(names) - bad, 'failed': bad, 'methods': counts,
                    'entries': census, 'original_symbols_sha256': sha(('\n'.join(names) + '\n').encode()),
                    'inventory_preserved': True, 'subset_selection_allowed': False})
      tref = store('timings.json', {'entries': timings, 'started_at': started.isoformat(), 'completed_at': clock().isoformat(),
                     'http_attempts': pace.count, 'http_bytes': pace.bytes})
      adm = store('risk-input-names.private.json', {'namespace': ns, 'session_date': self.day, 'symbols': names}, plan, '')
      rp = store('replay.private.json', {'schema': 'V2_RISK_REPLAY_MANIFEST_V1', 'namespace': ns, 'session_date': self.day,
                       'mode': 'OFFLINE_REPLAY', 'phase_pending': 0, 'admission': adm, 'symbols': entries,
                       'decision_at': clock().isoformat(), 'assessment_clocks_pending_host_executor': True}, plan, '')
    finally:
      os.close(blobs)
      os.close(plan)
    k = 'day/risk/plan/'
    out = {k + 'replay.private.json': rp['sha256'], k + 'risk-input-names.private.json': adm['sha256'],
       k + cref['path']: cref['sha256'], k + tref['path']: tref['sha256'], k + dbref['path']: dbref['sha256']}
    self.counts = {'list_symbols': len(names), 'complete_symbols': len(names) - bad, 'failed_symbols': bad, 'http_attempts': pace.count,
           'http_kib': pace.bytes >> 10, 'bytes_written_kib': size[0] >> 10, 'database_rows': proof['rows'],
           'database_readonly': 1, 'role_verified': 1, 'elapsed_seconds': int((now() - started).total_seconds()),
           **{m + '_fetch': bucket(x, FETCH, 'other_failure') for m, x in counts.items()}}
    return out, {}

  # ------------------------------------------------------------ risk: bind and stage
  def op_bind(self):
    r, ns = self.plan['risk'], 'R2D2-V2-DIAG-R4-' + self.day
    need(r['namespace'] == ns, 'NAMESPACE_NOT_THE_DECIDED_ONE')
    pw = r['phase_windows']
    need(isinstance(pw, dict) and set(pw) == set(PHASES)
      and all(isinstance(pw[x], dict) and set(pw[x]) == {'not_before', 'not_after'} for x in PHASES), 'RISK_WINDOWS_INVALID')
    cut = instant(r['cutoff_at'])
    w = {x: (instant(pw[x]['not_before']), instant(pw[x]['not_after'])) for x in PHASES}
    lo, hi = datetime.combine(self.D - timedelta(days=1), dtime(), timezone.utc), datetime.combine(self.D, dtime(13, 30), timezone.utc)
    need(all(a < b for a, b in w.values()) and cut <= w['acquire'][0] and cut <= w['execute'][0]
      and all(lo <= t <= hi for t in [cut] + [t for ab in w.values() for t in ab]), 'RISK_WINDOWS_INVALID')
    need(isinstance(r['owner_order_text'], str) and r['owner_order_text'].isascii(), 'OWNER_ORDER_INVALID')
    ob = r['owner_order_text'].encode('ascii')
    need(sha(ob) == r['owner_order_sha256'], 'OWNER_ORDER_NOT_THE_SIGNED_BYTES')
    o = strict(ob)
    scope = {'namespace': ns, 'session_date': self.day, 'cutoff_at': r['cutoff_at'], 'phases': list(PHASES)}
    need(isinstance(o, dict) and o.get('schema') == 'R2D2_V2_RISK_HOST_ORDER_V1' and o.get('scope') == scope
      and o.get('actions') == ACTIONS, 'OWNER_ORDER_SCOPE_MISMATCH')
    src_raw, s = self.pred('sources_launch')
    _, p = self.pred('publish_launch')
    names = self.symbols(p)
    rp = self.pred_bytes(s, 'day/risk/plan/replay.private.json')
    nm = self.pred_bytes(s, 'day/risk/plan/risk-input-names.private.json')
    adm = {'path': 'risk-input-names.private.json', 'sha256': sha(nm)}
    rep = strict(rp)
    need(rep.get('schema') == 'V2_RISK_REPLAY_MANIFEST_V1' and rep.get('namespace') == ns and rep.get('session_date') == self.day
      and rep.get('phase_pending') == 0 and rep.get('admission') == adm
      and [(e.get('symbol'), e.get('market')) for e in rep['symbols']] == [(n, 'US') for n in names], 'REPLAY_NOT_OF_THIS_LIST')
    need(strict(nm) == {'namespace': ns, 'session_date': self.day, 'symbols': names}, 'NAMES_DOCUMENT_NOT_OF_THIS_LIST')
    from app.r2d2_v2_risk_host_executor import _source_pins
    pb = self.pins  # checked against the signed constant before any import from app
    pins = json.loads(pb)
    _source_pins(Path(APP), pins)
    lb = enc({'namespace': ns, 'session_date': self.day, 'symbols': [{'symbol': n, 'market': 'US'} for n in names]})

    def ref(n, b):
      return {'path': n, 'sha256': sha(b)}
    hb = enc({'schema': 'R2D2_V2_RISK_HOST_PLAN_V1', 'namespace': ns, 'session_date': self.day, 'cutoff_at': r['cutoff_at'],
         'phase_windows': pw, 'limits': LIMITS, 'runtime_source_root': APP, 'spool_root': DAY_ROOT + '/risk/spool',
         'source_pins': ref('SOURCE_PINS.json', pb), 'owner_order': ref('OWNER_ORDER.json', ob), 'list': ref('list.private.json', lb),
         'admission': adm, 'replay_manifest': ref('replay.private.json', rp), 'sources_receipt_sha256': sha(src_raw)})
    gb = enc({'schema': 'R2D2_V2_RISK_HOST_GO_V1', 'verdict': 'GO', 'scope': 'RISK_ARTIFACT_ONLY', 'issuer': 'FABLE',
         'binding': {'manifest_sha256': sha(hb), 'owner_order_sha256': sha(ob), 'source_pins_sha256': sha(pb),
               'list_sha256': sha(lb), 'admission_sha256': adm['sha256'], **scope, 'phase_windows': pw},
         'k9_bind_request_sha256': self.plan['request_sha256'], 'k9_attempt_key': self.plan['attempt_key']})
    rk = walk(self.dd, ['risk'])
    pl = walk(rk, ['plan'])
    try:
      files = (('SOURCE_PINS.json', pb), ('OWNER_ORDER.json', ob), ('list.private.json', lb), ('HOST_PLAN.json', hb), ('GO.json', gb))
      need(not any(exists(pl, n) for n, _ in files) and not exists(rk, 'spool'), 'OUTPUT_ALREADY_PRESENT')
      out = {'day/risk/plan/' + n: put(pl, n, b) for n, b in files}
      os.close(child(rk, 'spool', make=True, exclusive=True))
    finally:
      os.close(pl)
      os.close(rk)
    out['day/risk/plan/replay.private.json'] = sha(rp)
    out['day/risk/plan/risk-input-names.private.json'] = sha(nm)
    self.counts = {'list_symbols': len(names), 'source_pins_files': len(pins['files'])}
    return out, {}

  def op_stage(self):
    _, p = self.pred('publish_launch')
    names = self.symbols(p)
    _, b = self.pred('bind')
    hb, gb = self.pred_bytes(b, 'day/risk/plan/HOST_PLAN.json'), self.pred_bytes(b, 'day/risk/plan/GO.json')
    m = sha(hb)
    try:
      sp = ['risk', 'spool', m]
      need(not exists(self.dd, '/'.join(sp + ['execute.FAILED.json'])), 'PREDECESSOR_NOT_COMPLETE')
      er = strict(readat(self.dd, sp + ['execute.RECEIPT.json'], 16 * MB))
    except (OSError, ValueError):
      raise Stop('PREDECESSOR_NOT_COMPLETE') from None
    o = er.get('outputs') if isinstance(er, dict) else None
    need(isinstance(o, dict) and er.get('schema') == 'R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1' and er.get('phase') == 'execute'
      and er.get('status') == 'COMPLETE' and er.get('manifest_sha256') == m and er.get('go_sha256') == sha(gb)
      and er.get('session_date') == self.day and er.get('namespace') == 'R2D2-V2-DIAG-R4-' + self.day,
      'PREDECESSOR_NOT_COMPLETE')
    mb, rb = (readat(self.dd, sp + ['risk-output', n], 16 * MB) for n in ('MANIFEST.json', 'risk.json'))
    fail(sha(mb) == o.get('output_manifest_sha256') and sha(rb) == o.get('risk_sha256')
      and strict(mb).get('files', {}).get('risk.json') == sha(rb), 'RISK_OUTPUT_NOT_AS_THE_RECEIPT_SAYS')
    rk = strict(rb)
    fail(rk.get('schema') == 'V2_RISK_COMPONENTS_V1' and rk.get('session_date') == self.day and isinstance(rk.get('symbols'), dict)
      and set(rk['symbols']) == set(names), 'RISK_NAMES_NOT_THE_LIST')
    comp = child(self.src, 'components', make=True)
    try:
      d = child(comp, self.day, make=True)
    finally:
      os.close(comp)
    try:
      need(not exists(d, 'risk.json'), 'OUTPUT_ALREADY_PRESENT')
      out = {'source/components/%s/risk.json' % self.day: put(d, 'risk.json', rb)}
    finally:
      os.close(d)
    k = o.get('counts') if isinstance(o.get('counts'), dict) else {}
    self.counts = {'list_symbols': len(names), 'risk_staged': 1, **pick(k, {'READY': 'ready_symbols', 'COMPLETED_NULL': 'completed_null'})}
    return out, {}

  # ------------------------------------------------------------ capture: the packaged snapshot CLI, wrapped
  def op_capture_launch(self):
    import contextlib, io
    self.producers()
    _, p = self.pred('publish_launch')
    self.pred_bytes(p, 'source/causal_list/%s/%s.json' % (EPOCH, self.day))
    from app import r2d2_v2_producer_snapshot as snap
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
      rc = snap.main(['--epoch', EPOCH, '--session-date', self.day, '--root', SOURCE])
    lines = buf.getvalue().splitlines()
    fail(len(lines) == 1, 'CAPTURE_SUMMARY_INVALID')
    sm = strict(lines[0])
    fail(isinstance(sm, dict) and 'status' in sm, 'CAPTURE_SUMMARY_INVALID')
    self.counts = {'capture_complete': int(sm['status'] == 'CAPTURED'), 'consumer_failed': int(bool(sm.get('consumer_error'))),
           **pick(sm, {'publications': 'snapshot_publications', 'quoted_symbols': 'quoted_symbols', 'symbols': 'list_symbols'}),
           'rejected_ticks': bucket(sm.get('rejected_ticks'), TICKS, 'other_reason'),
           'component_diagnostics': bucket(sm.get('component_diagnostics'), DIAGNOSTICS, 'other_diagnostic')}
    fail(rc == 0 and sm['status'] == 'CAPTURED', 'CAPTURE_NOT_CAPTURED')
    out = {'source/snapshot.json': sha(self.at('source/snapshot.json'))}
    out['source/tape/%s.us-quote.ndjson' % self.day] = sha(self.at('source/tape/%s.us-quote.ndjson' % self.day))
    return out, {}

  # ------------------------------------------------------------ the receipts
  def doc(self, status, code, outputs, aggregates, counts):
    return {'schema': 'K9_STEP_RECEIPT_V1', 'status': status, 'code': code, 'epoch': EPOCH, 'day': self.day, 'phase': self.phase,
        'operation': self.op, 'attempt_key': self.plan['attempt_key'], 'step_plan_sha256': self.psha, 'started_at': iso(self.started),
        'completed_at': iso(max(now(), self.started)), 'package_sha256': self.pkg,
        'build_sha': REVISION if os.environ.get('C3PO_BUILD_SHA') == REVISION else '',
        'outputs': outputs, 'aggregates': aggregates, 'counts': counts}

  def execute(self):
    put(self.rec, self.op + '.STARTED.json', canon({
      'schema': 'K9_STEP_STARTED_V1', 'epoch': EPOCH, 'day': self.day, 'phase': self.phase, 'operation': self.op,
      'attempt_key': self.plan['attempt_key'], 'step_plan_sha256': self.psha, 'started_at': iso(self.started)}))
    try:
      try:
        c = self.plan.get('constants')
        need(isinstance(c, dict) and isinstance(c.get('risk_source_pins_sha256'), str) and HEX.fullmatch(c['risk_source_pins_sha256']), 'PLAN_INVALID')
        self.pins = pins()  # every source the operations import, hashed before anything is imported from app
        need(sha(self.pins) == c['risk_source_pins_sha256'], 'SOURCE_PINS_NOT_THE_SIGNED_ONES')
        sys.path.insert(0, APP)
        try:
          from app.r2d2_v2_earnings_package import implementation_package_sha
          p = implementation_package_sha()
        except Exception:
          raise Stop('PACKAGE_UNAVAILABLE') from None
        self.pkg = p if isinstance(p, str) and HEX.fullmatch(p) else self.pkg
        need(p == PACKAGE, 'PACKAGE_NOT_THE_CERTIFIED_ONE')
        self.validate()
        need(os.environ.get('C3PO_BUILD_SHA') == REVISION, 'BUILD_SHA_NOT_THE_PINNED_ONE')
        budget = OPS[self.op][2]
        self.stop = min(self.rna, self.started + timedelta(seconds=budget)) if budget else self.rna - timedelta(seconds=MARGIN)
        need(now() < self.stop, 'RUN_NOT_AFTER_PASSED')
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, max(0.01, (self.stop - now()).total_seconds()))
        outputs, aggregates = getattr(self, 'op_' + self.op)()
        signal.setitimer(signal.ITIMER_REAL, 0)
        self.check()
      finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
      d = self.doc('COMPLETE', None, outputs, aggregates, self.counts)
      fail(len(outputs) <= 64 and len(aggregates) <= 8 and all(OUTKEY.fullmatch(x) and '/.' not in x for x in list(outputs) + list(aggregates))
        and all(HEX.fullmatch(v) for v in outputs.values()) and okcounts(self.counts), 'RECEIPT_GRAMMAR')
      name, raw = '.RECEIPT.json', canon(d)
    except BaseException as e:
      c = {**self.progress, **self.counts}  # what was counted before the stop
      d = self.doc('DEADLINE' if isinstance(e, Deadline) else e.status if isinstance(e, Stop) else 'FAILED',
             'RUN_NOT_AFTER_REACHED' if isinstance(e, Deadline) else code_of(e), {}, {}, c if okcounts(c) else {})
      name, raw = '.FAILED.json', canon(d)
    try:
      put(self.rec, self.op + name, raw)
    except BaseException:  # the exit code follows the file on disk, never the failed fsync
      try:
        if readf(self.rec, self.op + name, MB) != raw:
          return 3
      except BaseException:
        return 3
    if OPS[self.op][2]:
      try:
        os.write(OUT, raw + b'\n')
      except BaseException:
        pass
    return 0 if d['status'] == 'COMPLETE' else 1


def _alarm(signum, frame):
  raise Deadline()


def main(argv=None):
  entered = now()  # the container clock at entry: STARTED.started_at (after K9W's created_at)
  argv = sys.argv[1:] if argv is None else argv
  try:
    if QUIET:
      silence()
  except BaseException:
    return 2
  try:
    need(len(argv) == 4 and argv[0] == '--plan' and argv[2] == '--plan-sha256' and HEX.fullmatch(argv[3]) is not None, 'ARGUMENTS_INVALID')
    m = re.fullmatch(re.escape(DAY_ROOT) + '/plans/([a-z_]+)[.]json', argv[1])
    need(m is not None and m.group(1) in OPS, 'ARGUMENTS_INVALID')
    op = m.group(1)
    dd = root(DAY_ROOT)
    try:
      raw = readat(dd, ['plans', op + '.json'], 256 * 1024)
    finally:
      os.close(dd)
    need(sha(raw) == argv[3], 'PLAN_HASH_MISMATCH')
    plan = strict(raw)
    need(isinstance(plan, dict) and canon(plan) == raw and plan.get('schema') == 'K9_STEP_PLAN_V1' and plan.get('epoch') == EPOCH
      and plan.get('day') in DAYS and plan.get('k9_operation') == op and plan.get('k9_phase') == OPS[op][0]
      and plan.get('attempt_key') == akey(plan['day'], OPS[op][0], op), 'PLAN_IDENTITY_INVALID')
    run = Run(plan, argv[3], op)
    run.started = entered
    for suffix in ('.STARTED.json', '.RECEIPT.json', '.FAILED.json'):
      if exists(run.rec, op + suffix):
        return 3
  except BaseException:
    return 2
  try:
    return run.execute()
  except BaseException:
    return 3


if __name__ == '__main__':
  raise SystemExit(main())
