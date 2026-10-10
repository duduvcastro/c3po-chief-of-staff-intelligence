"""K9_STEP_PLAN_V1 files of k9_runner04 for D = 2026-10-12 (epoch R2D2-V2-SHADOW-2026-10-12, D1 route).

Offline, standard library only, Python 3.9+. No network, no host, no database. Every hash is computed here from bytes.

    python3 -I -B gen_k9_plans04.py check  --runner R --grid C|D|DRAFT3_REJECTED [--engine F]
    python3 -I -B gen_k9_plans04.py plans  --runner R --grid C|D --app-tree T --act-b F --release F --policy F --go F
                                           --out DIR [--engine F]
    python3 -I -B gen_k9_plans04.py plans  --runner R --grid C|D --app-tree T --synthetic --out DIR_WITH_SYNTHETIC_IN_ITS_NAME
                                           [--engine F]

`check` validates the compiled schedule of the named grid against every time rule below and prints it (no file).
`plans` writes, into a directory it creates (0700, must not exist), files created exclusively with mode 0600:

    plans/<op>.json                   one canonical K9_STEP_PLAN_V1 per runner operation (12)
    tools/k9_runner04-<sha256>.py     the runner, named by its hash (the name the runner requires)
    K9_04_STEP_SET_REQUEST.json       the request every plan's request_sha256 names (no plan hash inside: no cycle)
    K9_04_STEP_SET_MANIFEST.json      per operation: plan sha256, times, the L12-HOST K9STEP effect row, the core task

The literals of the plan ABI (EPOCH, DAYS, PACKAGE, REVISION, OPS, LIMITS, FLOOR, DB, the key sets) are read from the
runner file itself (top-level literal assignments, as Codex's K9ReceiptAdapter reads them), never restated here.
The risk source pins are recomputed from --app-tree (c3po/backend of the de96aee9 checkout) with the runner's rule and
must equal RISK_SOURCE_PINS_04; --go names the external GO/authorization original (open decision D-REQ in DESIGN04.md).
Nothing prints or stores a symbol: no list exists before the publish of Saturday.

Lots patch v3.4 (L-01; Codex ruling on P4: the start, the 60 s late tolerance and the 45 s effect latency lie wholly
before the next forbidden second; no relaxed guard, no retry; fixed minutes). The P/X minutes are a CLOSED, explicit
choice: `--grid` has no default and names one literal table of GRIDS:
    C                P1 14:26  P2 14:38  P3 14:53  P4 15:26  X1 15:38  X2 16:26 BRT (Saturday 10/10)
    D                the same six one hour later: 15:26  15:38  15:53  16:26  16:38  17:26 BRT
    DRAFT3_REJECTED  the previous grid (P4 12:03:00 BRT, 40 s before 12:03:40): `check` shows its refusal and `plans`
                     refuses it outright (GRID_REJECTED_BY_CODEX).
X3-X7 (21:26, 21:28, 21:38, 22:48, 23:26 BRT) and Monday's capture_launch (10:52 BRT) are FIXED, the same in every grid.
On top of the DRAFT3 on_grid rule and the order rules of timeline(), every start must leave its whole window
[at, at + LATE_SECONDS] plus EFFECT_LEAD_SECONDS allowed, second by second, by the L12-HOST ENGINE's own
`l12host_effect.start_minute_violation` (executed from the family file, never restated; --engine names another copy).
The grid id and its literal slot table are written into the request, into every plan's step_row and into the manifest,
so the signed bytes fix the minutes; the manifest also records the engine file's sha256 and every start's margin.
"""
import ast, hashlib, json, os, re, sys
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DAY = '2026-10-12'
PREVIOUS = '2026-10-09'
IMAGE_ID = 'sha256:bf37cec9f4f93e129543235a567a2de5daad0c8116086e2b176069e497defba3'
CONTRACT_SHA256 = '7c2252a810b0e951a5ff994be60801caa369beeaa8e6e3e3b96a471e5ad5f130'
# RISK_HOST_SOURCE_PINS_V1 over the 190 app/**/*.py of de96aee9 (the runner's pins() rule; faaa35a7... was dd4ec4bb)
RISK_SOURCE_PINS_04 = '3ceb9320547ce9472650c93c60338d6d82206514e12c39b934c644f4c3ba2d14'
BRT, NY, UTC = ZoneInfo('America/Sao_Paulo'), ZoneInfo('America/New_York'), timezone.utc
# SD-30: the -e04 family. K9 root on the root filesystem (R0: 593 GB free >= FLOOR 200 GiB; /mnt/day-d-data 53 GB).
K9_ROOT = '/var/lib/c3po/r2d2-v2-k9-20261012'
SOURCE_ROOT = '/var/lib/c3po/r2d2-v2-source-20261012'
SECRETS_ROOT = '/var/lib/c3po/r2d2-v2-k9-20261005/secrets'   # PLANO section 6 W10: the epoch-03 K9 secret roots, read by R0
CONTAINER_PREFIX = 'c3po-k9-e04-20261012-'
TARGETS = {'TOOLS': '/c3po-k9-tools', 'DAY': '/c3po-k9-day', 'SOURCE': '/c3po-source', 'EMITTER': '/c3po-k9-emitter'}
MOUNTS = {'TOOLS': (K9_ROOT + '/tools', TARGETS['TOOLS'], True), 'DAY': (K9_ROOT + '/days/' + DAY, TARGETS['DAY'], False),
          'DAY_READ_ONLY': (K9_ROOT + '/days/' + DAY, TARGETS['DAY'], True),
          'DAY_RECEIPTS': (K9_ROOT + '/days/' + DAY + '/receipts', TARGETS['DAY'] + '/receipts', False),
          'SOURCE': (SOURCE_ROOT, TARGETS['SOURCE'], False), 'EMITTER': (SECRETS_ROOT + '/emitter', TARGETS['EMITTER'], True)}
ENV_FILES = {'PROVIDER': SECRETS_ROOT + '/provider.env', 'RISK_DATABASE': SECRETS_ROOT + '/risk-db.env'}
# Codex's K9ReceiptAdapter ALIASES (core operation -> runner operation); prove_launch is the proposed new row (D-ALIAS)
CORE_OF = {'prove_launch': 'prove', 'collect_launch': 'collect', 'commit_launch': 'commit_result', 'publish_launch': 'publish_launch',
           'capture_launch': 'capture_launch'}
# operation: (budget seconds, mounts, env files, lot), in the runner's chain order. run_not_after = start + budget - 30 s
# (the capture's is the fixed 14:03:00Z of D). The start of each operation comes from the grid (GRIDS + FIXED).
STEPS = {
    'prove_launch': (600, ('TOOLS', 'DAY'), ('PROVIDER',), 'UP'),
    'collect_launch': (900, ('TOOLS', 'DAY'), ('PROVIDER',), 'UP'),
    'commit_launch': (600, ('TOOLS', 'DAY', 'EMITTER'), (), 'UP'),
    'publish_launch': (600, ('TOOLS', 'DAY', 'SOURCE', 'EMITTER'), (), 'UP'),
    'components_launch': (2400, ('TOOLS', 'DAY', 'SOURCE'), ('PROVIDER',), 'UP'),
    'sources_launch': (4500, ('TOOLS', 'DAY'), ('PROVIDER', 'RISK_DATABASE'), 'UP'),
    'bind': (120, ('TOOLS', 'DAY'), (), 'UP'),
    'preflight': (300, ('TOOLS', 'DAY'), (), 'UP'),
    'acquire_launch': (4200, ('TOOLS', 'DAY'), ('PROVIDER', 'RISK_DATABASE'), 'UP'),
    'execute_launch': (1200, ('TOOLS', 'DAY'), (), 'UP'),
    'stage': (120, ('TOOLS', 'DAY_READ_ONLY', 'DAY_RECEIPTS', 'SOURCE'), (), 'UP'),
    'capture_launch': (690, ('TOOLS', 'DAY', 'SOURCE'), ('PROVIDER',), 'DOWN')}
# The L12-HOST slot names of the UP lot (P1-P4 core, X1-X7 extended) and of the DOWN capture (C1).
SLOT_OF = {'prove_launch': 'P1', 'collect_launch': 'P2', 'commit_launch': 'P3', 'publish_launch': 'P4',
           'components_launch': 'X1', 'sources_launch': 'X2', 'bind': 'X3', 'preflight': 'X4', 'acquire_launch': 'X5',
           'execute_launch': 'X6', 'stage': 'X7', 'capture_launch': 'C1'}
# L-01: the closed grid choice (local BRT starts of P1-P4, X1, X2). Literal tables, never computed.
GRIDS = {
    'C': {'prove_launch': '2026-10-10 14:26:00', 'collect_launch': '2026-10-10 14:38:00',
          'commit_launch': '2026-10-10 14:53:00', 'publish_launch': '2026-10-10 15:26:00',
          'components_launch': '2026-10-10 15:38:00', 'sources_launch': '2026-10-10 16:26:00'},
    'D': {'prove_launch': '2026-10-10 15:26:00', 'collect_launch': '2026-10-10 15:38:00',
          'commit_launch': '2026-10-10 15:53:00', 'publish_launch': '2026-10-10 16:26:00',
          'components_launch': '2026-10-10 16:38:00', 'sources_launch': '2026-10-10 17:26:00'},
    'DRAFT3_REJECTED': {'prove_launch': '2026-10-10 11:26:00', 'collect_launch': '2026-10-10 11:38:00',
                        'commit_launch': '2026-10-10 11:53:00', 'publish_launch': '2026-10-10 12:03:00',
                        'components_launch': '2026-10-10 12:26:00', 'sources_launch': '2026-10-10 13:26:00'}}
ELECTABLE = ('C', 'D')                  # `plans` accepts only these; DRAFT3_REJECTED stays for `check` and the record
# X3-X7 (risk from Saturday 21:05 BRT) and Monday's capture: the same instants in every grid.
FIXED = {'bind': '2026-10-10 21:26:00', 'preflight': '2026-10-10 21:28:00', 'acquire_launch': '2026-10-10 21:38:00',
         'execute_launch': '2026-10-10 22:48:00', 'stage': '2026-10-10 23:26:00', 'capture_launch': '2026-10-12 10:52:00'}
# The start window the engine must allow wholly (Codex P4 ruling): the shell starts a slot up to at + 60 s
# (l12host_runtime LATE_SECONDS, read from the runtime next to the engine and required equal) and a K9 row reaches its
# effect up to 45 s after its instant (CONTRACT 9.3: budget - effect floor).
LATE_SECONDS = 60
EFFECT_LEAD_SECONDS = 45
START_WINDOW_SECONDS = LATE_SECONDS + EFFECT_LEAD_SECONDS
ENGINE_FILE, RUNTIME_FILE = 'l12host_effect.py', 'l12host_runtime.py'
# the runner's predecessor reads (pred / pred_bytes), plus the sequential order of the provider-heavy steps
NEEDS = {'collect_launch': ('prove_launch',), 'commit_launch': ('collect_launch',), 'publish_launch': ('commit_launch',),
         'components_launch': ('commit_launch', 'publish_launch'), 'sources_launch': ('publish_launch', 'components_launch'),
         'bind': ('sources_launch', 'publish_launch'), 'preflight': ('bind',), 'acquire_launch': ('preflight',),
         'execute_launch': ('acquire_launch',), 'stage': ('execute_launch', 'bind', 'publish_launch'), 'capture_launch': ('publish_launch', 'stage')}
CORE_LANE = ('prove_launch', 'collect_launch', 'commit_launch', 'publish_launch', 'capture_launch')
CORE_BUDGET = 1200                                  # finite_batch validate_plan: 0 < budget_seconds <= 1200
RISK_CUTOFF = '2026-10-11T00:05:00+00:00'           # Saturday 21:05 BRT: risk only from D-1 00:05Z
RISK_WINDOWS = {'preflight': ('2026-10-11T00:05:00+00:00', '2026-10-11T00:35:00+00:00'),
                'acquire': ('2026-10-11T00:05:00+00:00', '2026-10-11T01:50:00+00:00'),
                'execute': ('2026-10-11T00:05:00+00:00', '2026-10-11T02:15:00+00:00')}
PACKAGED = {'preflight': 'preflight', 'acquire_launch': 'acquire', 'execute_launch': 'execute'}
CAPTURE_RUN_NOT_AFTER = '2026-10-12T14:03:00+00:00'
ACTIONS = ['READ_PROVIDERS', 'READ_DATABASE', 'WRITE_PRIVATE_RISK_ARTIFACTS']
SYNTHETIC = {'act_b': 'a1' * 32, 'release': 'fc' * 32, 'policy': 'd2' * 32}
SYNTHETIC_GO = b'{"schema":"K9_04_SYNTHETIC_GO_NOT_AN_AUTHORIZATION"}'
HEX = re.compile('[0-9a-f]{64}')


class Refused(Exception):
    pass


def need(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    need(value.utcoffset() == timedelta(0), 'CLOCK_NOT_UTC')
    return value


def iso(value):
    return value.astimezone(UTC).isoformat()


def brt(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M:%S').replace(tzinfo=BRT)


def schedule(grid):
    """The compiled schedule of one grid: {op: (local BRT start, budget, mounts, env files, lot)} in the runner's order
    (the shape of the former SCHEDULE literal)."""
    need(isinstance(grid, str) and grid in GRIDS, 'GRID_NOT_IN_THE_CLOSED_CHOICE')
    starts = dict(GRIDS[grid])
    starts.update(FIXED)
    need(set(starts) == set(STEPS) and len(starts) == len(GRIDS[grid]) + len(FIXED), 'GRID_TABLE_INCOMPLETE')
    return {op: (starts[op],) + STEPS[op] for op in STEPS}


def grid_block(grid):
    """The grid id and its literal slot table, as written into the request, every plan's step_row and the manifest."""
    rows = [{'slot': SLOT_OF[op], 'operation': op, 'lot': lot, 'starts_at_brt': start, 'starts_at_utc': iso(brt(start)),
             'budget_seconds': budget} for op, (start, budget, _mounts, _envs, lot) in schedule(grid).items()]
    return {'id': grid, 'late_tolerance_seconds': LATE_SECONDS, 'effect_lead_seconds': EFFECT_LEAD_SECONDS,
            'slots': rows, 'slots_sha256': sha(canon(rows))}


def engine_rule(path=None):
    """(start_minute_violation, sha256 of the executed engine bytes). The ENGINE's own rule, executed from the family's
    l12host_effect.py (this file lives in <family>/lots/k9tools/) or from --engine; the shell's LATE_SECONDS is read
    from the l12host_runtime.py next to it (AST, never executed) and must be this generator's LATE_SECONDS."""
    p = Path(path) if path else Path(__file__).resolve().parents[2] / ENGINE_FILE
    try:
        raw = p.read_bytes()
        runtime_raw = (p.parent / RUNTIME_FILE).read_bytes()
    except OSError:
        raise Refused('ENGINE_RULE_UNAVAILABLE') from None
    namespace = {'__name__': 'l12host_effect_start_minute_rule', '__file__': str(p)}
    exec(compile(raw, str(p), 'exec'), namespace)          # the engine's import is inert (its own docstring)
    rule = namespace.get('start_minute_violation')
    need(callable(rule), 'ENGINE_RULE_UNAVAILABLE')
    late = []
    for node in ast.parse(runtime_raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple) \
                and [getattr(e, 'id', None) for e in node.targets[0].elts] == ['EARLY_SECONDS', 'LATE_SECONDS']:
            late.append(ast.literal_eval(node.value)[1])
    need(late == [LATE_SECONDS], 'ENGINE_LATE_TOLERANCE_NOT_THE_RULED_ONE')
    return rule, sha(raw)


def start_margin(at, rule, horizon=6 * 3600):
    """Seconds from the instant `at` to the first second the engine refuses (`horizon` when none within it)."""
    for k in range(horizon):
        if rule(at + timedelta(seconds=k)) is not None:
            return k
    return horizon


def runner_literals(raw):
    """The plan ABI as the runner compiles it: its top-level literal assignments (each exactly once)."""
    wanted = {'EPOCH', 'DAYS', 'PACKAGE', 'REVISION', 'OPS', 'RECEIPT_KEYS', 'PLAN_KEYS', 'CONST_KEYS', 'LIMITS', 'FLOOR', 'DB',
              'PRESENCE', 'PHASES', 'ACTIONS'}
    found = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted:
            need(node.targets[0].id not in found, 'RUNNER_LITERAL_DUPLICATED')
            found[node.targets[0].id] = ast.literal_eval(node.value)
    need(set(found) == wanted, 'RUNNER_LITERALS_MISSING')
    need(found['EPOCH'] == 'R2D2-V2-SHADOW-2026-10-12' and DAY in found['DAYS'], 'RUNNER_NOT_OF_EPOCH_04')
    need(set(found['OPS']) == set(STEPS), 'SCHEDULE_NOT_THE_RUNNER_OPERATIONS')
    need(list(found['ACTIONS']) == ACTIONS and tuple(found['PHASES']) == tuple(RISK_WINDOWS), 'RUNNER_RISK_LITERALS')
    return found


def source_pins(app_tree):
    """The runner's pins(): canonical {schema, files} + newline over app/**/*.py of the tree, by bytes."""
    root = Path(app_tree)
    files = {q.relative_to(root).as_posix(): sha(q.read_bytes()) for q in (root / 'app').rglob('*.py')}
    return sha(canon({'schema': 'RISK_HOST_SOURCE_PINS_V1', 'files': files}) + b'\n'), len(files)


def on_grid(local):
    """Signed ORDEM revM3 section 5 (BRT): starts only at HH:00:00-03:39, HH:26:00-33:39 or HH:38:00-58:39; never 06:58:40-07:25:59,
    12:58:40-13:25:59, 18:58:40-19:25:59; never in the quiet bands 00:15-00:45:59 and 02:15-02:45:59."""
    s = local.minute * 60 + local.second
    t = local.hour * 3600 + s
    grid = s <= 219 or 1560 <= s <= 2019 or 2280 <= s <= 3519
    barred = any(a <= t <= b for a, b in ((6 * 3600 + 3520, 7 * 3600 + 1559), (12 * 3600 + 3520, 13 * 3600 + 1559),
                                          (18 * 3600 + 3520, 19 * 3600 + 1559), (900, 2759), (2 * 3600 + 900, 2 * 3600 + 2759)))
    return grid and not barred


def timeline(literals, grid, rule):
    """Every step's start, budget and run_not_after of the grid, checked against the image's and the runner's time rules
    and, for every start, the engine's whole start window (L-01)."""
    rows = {}
    for op, (start, budget, mounts, envs, lot) in schedule(grid).items():
        at = brt(start).astimezone(UTC)
        rna = utc(CAPTURE_RUN_NOT_AFTER) if op == 'capture_launch' else at + timedelta(seconds=budget - 30)
        need(at + timedelta(seconds=budget - 30) == rna, 'CAPTURE_BUDGET_NOT_THE_FIXED_RUN_NOT_AFTER')
        need(on_grid(brt(start)), 'START_NOT_ON_THE_DRAFT3_GRID:' + op)
        margin = start_margin(at, rule)
        need(margin > START_WINDOW_SECONDS, 'START_WINDOW_NOT_ALLOWED:' + op)
        attached = literals['OPS'][op][2]
        need(rna - at >= timedelta(seconds=(attached or 0) + 35 if attached else 120), 'RUN_NOT_AFTER_TOO_CLOSE:' + op)
        if op in CORE_LANE:
            need(0 < budget <= CORE_BUDGET, 'CORE_BUDGET_EXCEEDED:' + op)
        rows[op] = {'at': at, 'budget': budget, 'run_not_after': rna, 'stop': rna if attached else rna - timedelta(seconds=60),
                    'margin': margin}
    d, prev = date.fromisoformat(DAY), date.fromisoformat(PREVIOUS)
    after_close = datetime.combine(prev, dtime(16), NY).astimezone(UTC)        # XNYS close of Friday 09/10 (no early close)
    cutoff = datetime.combine(d, dtime(), NY).astimezone(UTC)                   # causal_list: after_close < built_at < cutoff
    decision = datetime.combine(d, dtime(10), NY).astimezone(UTC)               # publication deadline
    need(after_close < rows['prove_launch']['at'], 'P_CHAIN_BEFORE_THE_PREVIOUS_CLOSE')
    need(rows['commit_launch']['run_not_after'] <= cutoff - timedelta(minutes=10), 'COMMIT_AFTER_ITS_LATEST_START')
    need(all(rows[op]['run_not_after'] < cutoff for op in ('prove_launch', 'collect_launch', 'commit_launch', 'publish_launch')),
         'P_CHAIN_CROSSES_THE_CAUSAL_CUTOFF')
    need(rows['publish_launch']['run_not_after'] < decision, 'PUBLISH_AFTER_THE_DECISION')
    lo = datetime.combine(d - timedelta(days=1), dtime(), UTC)
    hi = datetime.combine(d, dtime(13, 30), UTC)
    cut = utc(RISK_CUTOFF)
    windows = {k: (utc(a), utc(b)) for k, (a, b) in RISK_WINDOWS.items()}
    need(cut >= lo + timedelta(minutes=5) and all(a < b for a, b in windows.values()) and cut <= windows['acquire'][0]
         and cut <= windows['execute'][0] and all(lo <= t <= hi for t in [cut] + [t for ab in windows.values() for t in ab]),
         'RISK_WINDOWS_INVALID')
    need(rows['bind']['at'] >= cut, 'BIND_BEFORE_THE_RISK_CUTOFF')
    for op, phase in PACKAGED.items():
        a, b = windows[phase]
        need(a <= rows[op]['at'] and rows[op]['run_not_after'] <= b, 'PACKAGED_PHASE_OUTSIDE_ITS_WINDOW:' + op)
    open_at = datetime.combine(d, dtime(10), NY).astimezone(UTC)
    close_at = datetime.combine(d, dtime(10, 1), NY).astimezone(UTC)
    cap = rows['capture_launch']
    need(utc('2026-10-12T04:00:00+00:00') <= cap['at'] < open_at - timedelta(seconds=30) and cap['stop'] > close_at, 'CAPTURE_WINDOW')
    order = list(STEPS)                        # relative rules last: each absolute rule above is reported as itself
    for op, preds in NEEDS.items():
        for p in preds:
            need(rows[op]['at'] >= rows[p]['run_not_after'] + timedelta(seconds=30), 'STARTS_BEFORE_ITS_PREDECESSOR_ENDS:' + op)
    for a, b in zip(order, order[1:]):
        need(rows[b]['at'] >= rows[a]['run_not_after'] + timedelta(seconds=30), 'STEPS_OVERLAP:' + b)
    return rows


def owner_order(namespace):
    return canon({'schema': 'R2D2_V2_RISK_HOST_ORDER_V1', 'epoch': 'R2D2-V2-SHADOW-2026-10-12', 'actions': ACTIONS,
                  'scope': {'namespace': namespace, 'session_date': DAY, 'cutoff_at': RISK_CUTOFF,
                            'phases': ['preflight', 'acquire', 'execute']},
                  'status': 'BOUND_BY_THE_OWNER_ASSINO_OF_THE_LOT_THAT_PINS_THE_BIND_PLAN'}).decode('ascii')


def risk_block():
    namespace = 'R2D2-V2-DIAG-R4-' + DAY
    text = owner_order(namespace)
    return {'namespace': namespace, 'cutoff_at': RISK_CUTOFF,
            'phase_windows': {k: {'not_before': a, 'not_after': b} for k, (a, b) in RISK_WINDOWS.items()},
            'owner_order_text': text, 'owner_order_sha256': sha(text.encode('ascii'))}


def attempt_key(epoch, phase, op):
    return sha(json.dumps([epoch, DAY, phase, op], separators=(',', ':'), ensure_ascii=True).encode('ascii'))


def plan_doc(op, literals, rows, constants, request_sha256, go_sha256, grid):
    phase, network, attached = literals['OPS'][op]
    row = rows[op]
    doc = {'schema': 'K9_STEP_PLAN_V1', 'epoch': literals['EPOCH'], 'day': DAY, 'k9_phase': phase, 'k9_operation': op, 'slot': 'PRIMARY',
           'attempt_key': attempt_key(literals['EPOCH'], phase, op), 'request_sha256': request_sha256, 'go_sha256': go_sha256,
           'run_not_after': iso(row['run_not_after']), 'constants': constants, 'network_class': network,
           'database': literals['DB'] if op in ('commit_launch', 'publish_launch') else None,
           'risk': risk_block() if op == 'bind' else None,
           'step_row': {'operation': op, 'lot': STEPS[op][3], 'core_operation': CORE_OF.get(op), 'mode': 'ATTACHED' if attached else 'LAUNCH',
                        'starts_at': iso(row['at']), 'budget_seconds': row['budget'], 'grid': grid_block(grid)}}
    need(set(doc) == literals['PLAN_KEYS'] and set(constants) == literals['CONST_KEYS'], 'PLAN_ABI')
    return canon(doc)


def constants_of(literals, runner_sha256, pins, act_b, release, policy):
    values = {'package_sha256': literals['PACKAGE'], 'code_revision': literals['REVISION'], 'act_b_sha256': act_b,
              'release_sha256': release, 'policy_sha256': policy, 'runner_sha256': runner_sha256, 'risk_source_pins_sha256': pins,
              'risk_limits': literals['LIMITS'], 'disk_floor_bytes': literals['FLOOR']}
    need(all(isinstance(values[k], str) and HEX.fullmatch(values[k]) and values[k] != '0' * 64 for k in
             ('act_b_sha256', 'release_sha256', 'policy_sha256', 'runner_sha256', 'risk_source_pins_sha256')), 'CONSTANT_NOT_A_PIN')
    return values


def request_doc(literals, rows, constants, synthetic, grid):
    """What every plan's request_sha256 names: the step set without any plan hash (no cycle)."""
    risk = risk_block()
    return canon({'schema': 'K9_04_STEP_SET_REQUEST_V1', 'epoch': literals['EPOCH'], 'day': DAY, 'previous_session': PREVIOUS,
                  'synthetic': synthetic, 'image': {'id': IMAGE_ID, 'revision': literals['REVISION'], 'package_sha256': literals['PACKAGE'],
                                                    'contract_sha256': CONTRACT_SHA256},
                  'constants': constants, 'presence_rule': list(literals['PRESENCE']),
                  'layout': {'k9_root': K9_ROOT, 'source_root': SOURCE_ROOT, 'secrets_root': SECRETS_ROOT, 'container_prefix': CONTAINER_PREFIX},
                  'risk': {k: risk[k] for k in ('namespace', 'cutoff_at', 'phase_windows', 'owner_order_sha256')},
                  'grid': grid_block(grid),
                  'steps': [{'operation': op, 'starts_at': iso(r['at']), 'budget_seconds': r['budget'], 'run_not_after': iso(r['run_not_after']),
                             'lot': STEPS[op][3], 'core_operation': CORE_OF.get(op)} for op, r in rows.items()]})


def l12_effect(op, literals, plan_sha256, runner_name, timeout):
    """The K9STEP row in L12-HOST's own shape (l12host_effect.validate_docker / validate_receipt_spec): the fixed prefix
    (--rm, --pull never, --init, --user 0:0, --read-only, --cap-drop ALL, no-new-privileges, the c3po.l12 labels) and
    `IMAGE timeout -s KILL <timeout_seconds>` are the engine's; `network` is the lot's (not compiled here: null)."""
    docker = {'mode': 'ATTACHED', 'name': CONTAINER_PREFIX + op.replace('_', '-'),
              'labels': [['c3po.k9.operation', op], ['c3po.k9.plan', plan_sha256]], 'network': None,
              'env_files': [ENV_FILES[n] for n in STEPS[op][2]],
              'env': [['C3PO_R2D2_V2_PRODUCERS_ENABLED', 'true'], ['C3PO_BUILD_SHA', literals['REVISION']]],
              'mounts': [{'source': MOUNTS[n][0], 'target': MOUNTS[n][1], 'readonly': MOUNTS[n][2]} for n in STEPS[op][1]],
              'tmpfs': False, 'workdir': None, 'image_id': IMAGE_ID, 'timeout_seconds': timeout,
              'command': ['python', '-I', TARGETS['TOOLS'] + '/' + runner_name, '--plan', TARGETS['DAY'] + '/plans/' + op + '.json',
                          '--plan-sha256', plan_sha256]}
    receipt = {'source': 'FILE', 'path': K9_ROOT + '/days/' + DAY + '/receipts/' + op + '.RECEIPT.json', 'schemas': ['K9_STEP_RECEIPT_V1'],
               'status_field': 'status', 'complete_statuses': ['COMPLETE']}
    return {'kind': 'K9STEP', 'docker': docker, 'receipt': receipt}


def kill_limit(op, literals, rows):
    """In-container KILL: an ATTACHED step's own cap + 5 s; a LAUNCH's run_not_after - start - 5 s (the runner stops at
    run_not_after - 60 s and needs < 55 s to write its DEADLINE receipt)."""
    attached = literals['OPS'][op][2]
    return attached + 5 if attached else int((rows[op]['run_not_after'] - rows[op]['at']).total_seconds()) - 5


def write_exclusive(path, data, mode=0o600):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.fchmod(fd, mode)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def build(runner_raw, app_tree, act_b, release, policy, go_raw, synthetic, grid, engine=None):
    need(grid in GRIDS, 'GRID_NOT_IN_THE_CLOSED_CHOICE')
    need(grid in ELECTABLE, 'GRID_REJECTED_BY_CODEX:' + grid)
    rule, engine_sha = engine_rule(engine)
    literals = runner_literals(runner_raw)
    pins, count = source_pins(app_tree)
    need(pins == RISK_SOURCE_PINS_04 and count == 190, 'SOURCE_PINS_NOT_THE_DE96AEE9_ONES')
    rows = timeline(literals, grid, rule)
    runner_sha = sha(runner_raw)
    constants = constants_of(literals, runner_sha, pins, act_b, release, policy)
    request = request_doc(literals, rows, constants, synthetic, grid)
    go_sha = sha(go_raw)
    need(go_sha != sha(request), 'GO_IS_THE_REQUEST')
    plans = {op: plan_doc(op, literals, rows, constants, sha(request), go_sha, grid) for op in STEPS}
    runner_name = 'k9_runner04-%s.py' % runner_sha
    steps = {}
    for op, raw in plans.items():
        r = rows[op]
        phase, network, attached = literals['OPS'][op]
        steps[op] = {'plan_sha256': sha(raw), 'plan_bytes': len(raw), 'host_plan_path': K9_ROOT + '/days/' + DAY + '/plans/' + op + '.json',
                     'lot': STEPS[op][3], 'core_operation': CORE_OF.get(op), 'phase': phase, 'network_class': network,
                     'mode': 'ATTACHED' if attached else 'LAUNCH', 'starts_at_utc': iso(r['at']),
                     'starts_at_brt': r['at'].astimezone(BRT).strftime('%Y-%m-%d %H:%M:%S'), 'budget_seconds': r['budget'],
                     'run_not_after': iso(r['run_not_after']), 'runner_stops_at': iso(r['stop']), 'kill_seconds': kill_limit(op, literals, rows),
                     'l12_effect': l12_effect(op, literals, sha(raw), runner_name, kill_limit(op, literals, rows)),
                     'l12_task': {'operation': CORE_OF.get(op), 'not_before': iso(r['at']), 'not_after': iso(r['at'] + timedelta(seconds=r['budget'])),
                                  'budget_seconds': r['budget']} if op in CORE_LANE else None,
                     'receipts': {k: K9_ROOT + '/days/' + DAY + '/receipts/' + op + '.' + k + '.json' for k in ('STARTED', 'RECEIPT', 'FAILED')},
                     'packaged_phase': PACKAGED.get(op), 'requires': list(NEEDS.get(op, ())),
                     'slot': SLOT_OF[op], 'start_margin_seconds': r['margin']}
    manifest = canon({'schema': 'K9_04_STEP_SET_MANIFEST_V1', 'epoch': literals['EPOCH'], 'day': DAY, 'synthetic': synthetic,
                      'request_sha256': sha(request), 'go_sha256': go_sha, 'runner': {'name': runner_name, 'sha256': runner_sha,
                      'bytes': len(runner_raw), 'host_path': K9_ROOT + '/tools/' + runner_name}, 'risk_source_pins_sha256': pins,
                      'image_id': IMAGE_ID, 'steps': steps, 'network_names': None, 'grid': grid_block(grid),
                      'engine_rule': {'file': ENGINE_FILE, 'function': 'start_minute_violation', 'sha256': engine_sha,
                                      'late_tolerance_seconds': LATE_SECONDS, 'effect_lead_seconds': EFFECT_LEAD_SECONDS}})
    return {'plans': plans, 'request': request, 'manifest': manifest, 'runner_name': runner_name, 'rows': rows, 'literals': literals}


def arguments(argv):
    out, flags, i = {}, {'--synthetic'}, 0
    while i < len(argv):
        need(argv[i].startswith('--'), 'ARGUMENTS_INVALID')
        if argv[i] in flags:
            out[argv[i]] = True
            i += 1
        else:
            need(i + 1 < len(argv) and argv[i] not in out, 'ARGUMENTS_INVALID')
            out[argv[i]] = argv[i + 1]
            i += 2
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        need(argv and argv[0] in ('check', 'plans'), 'ARGUMENTS_INVALID')
        a = arguments(argv[1:])
        need('--grid' in a, 'GRID_REQUIRED')                       # explicit, closed choice: no default grid
        grid = a['--grid']
        need(grid in GRIDS, 'GRID_NOT_IN_THE_CLOSED_CHOICE')
        need(argv[0] == 'check' or grid in ELECTABLE, 'GRID_REJECTED_BY_CODEX:' + grid)
        given = set(a) - {'--engine'}
        if argv[0] == 'check':
            need(given == {'--runner', '--grid'}, 'ARGUMENTS_INVALID')
            runner_raw = Path(a['--runner']).read_bytes()
            rule, engine_sha = engine_rule(a.get('--engine'))
            literals = runner_literals(runner_raw)
            rows = timeline(literals, grid, rule)
            for op, r in rows.items():
                print('%-3s %-18s %s BRT  %s  budget %5d  run_not_after %s  margin %5d s' % (
                    SLOT_OF[op], op, r['at'].astimezone(BRT).strftime('%a %d/%m %H:%M:%S'), iso(r['at']), r['budget'],
                    iso(r['run_not_after']), r['margin']))
            print('GRID %s slots_sha256=%s start_window=[at, at+%d s]+%d s' % (grid, grid_block(grid)['slots_sha256'],
                                                                             LATE_SECONDS, EFFECT_LEAD_SECONDS))
            print('SCHEDULE_OK runner_sha256=%s grid=%s engine_sha256=%s' % (sha(runner_raw), grid, engine_sha))
            return 0
        synthetic = a.get('--synthetic', False)
        out = Path(a['--out'])
        if synthetic:
            need(given == {'--runner', '--grid', '--app-tree', '--synthetic', '--out'} and 'SYNTHETIC' in out.name,
                 'SYNTHETIC_OUTPUT_MUST_SAY_SO')
            hashes, go_raw = dict(SYNTHETIC), SYNTHETIC_GO
        else:
            need(given == {'--runner', '--grid', '--app-tree', '--act-b', '--release', '--policy', '--go', '--out'}
                 and 'SYNTHETIC' not in out.name, 'ARGUMENTS_INVALID')
            hashes = {k: sha(Path(a['--' + k.replace('_', '-')]).read_bytes()) for k in ('act_b', 'release', 'policy')}
            go_raw = Path(a['--go']).read_bytes()
        runner_raw = Path(a['--runner']).read_bytes()
        result = build(runner_raw, a['--app-tree'], hashes['act_b'], hashes['release'], hashes['policy'], go_raw, synthetic,
                       grid, a.get('--engine'))
        os.mkdir(str(out), 0o700)
        os.mkdir(str(out / 'plans'), 0o700)
        os.mkdir(str(out / 'tools'), 0o700)
        for op, raw in result['plans'].items():
            write_exclusive(out / 'plans' / (op + '.json'), raw)
        write_exclusive(out / 'tools' / result['runner_name'], runner_raw)
        write_exclusive(out / 'K9_04_STEP_SET_REQUEST.json', result['request'])
        write_exclusive(out / 'K9_04_STEP_SET_MANIFEST.json', result['manifest'])
        print('PLANS_OK request_sha256=%s go_sha256=%s manifest_sha256=%s runner=%s synthetic=%s grid=%s' % (
            sha(result['request']), sha(go_raw), sha(result['manifest']), result['runner_name'], synthetic, grid))
        return 0
    except Refused as error:
        print('REFUSED %s' % error)
        return 2
    except (OSError, KeyError, ValueError) as error:
        print('REFUSED %s' % type(error).__name__)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
