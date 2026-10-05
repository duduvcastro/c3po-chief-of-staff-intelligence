"""The K9 runner against the release's own modules (dd4ec4bb export), with stand-ins for HTTP, the database and the
websocket only. Every receipt any test produces is checked against K9R's own grammar functions (imported from the
assembled K9R source) and scanned for secrets, symbols and paths."""
import ast, hashlib, importlib.util, json, os, re, shutil, stat, subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import world as W
from world import World, sha, DAY, SYMBOLS, CANARY, PASSWORD, DSN

if not W.APP or not (Path(W.APP) / 'app' / 'r2d2_v2_earnings_package.py').is_file():
    pytest.skip('K9_RELEASE_TREE (c3po/backend of the release export dd4ec4bb) is not set', allow_module_level=True)
# K9R's assembled source, whose own grammar functions judge every file the runner writes (K9R_ASSEMBLED, or the sibling
# directory of this deliverable)
K9R_PATH = Path(os.environ.get('K9R_ASSEMBLED') or W.ROOT.parent / 'fable-k9r-20261004' / 'k9_phase_read' / 'build' / 'k9_phase_read.py')
if not K9R_PATH.is_file():
    pytest.skip('K9R_ASSEMBLED (build/k9_phase_read.py of K9R) is not available', allow_module_level=True)
_spec = importlib.util.spec_from_file_location('k9r_assembled', K9R_PATH)
K9R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K9R)

# The closed count-key sets per operation (DESIGN.md section 4): top-level key -> None (integer) or the nested key set.
FETCH = {'fetch_ok', 'http_failed', 'transport_failed', 'body_rejected', 'json_invalid', 'other_failure'}
EXPECTED_COUNTS = {
    'collect_launch': {'registry_symbols': None, 'complete_bars': None, 'bar_conflicts': None, 'logical_fetch_calls': None,
                       'registry_counts': {'provider_rows', 'kept_rows', 'skipped_exchange', 'skipped_symbol', 'duplicate_rows'},
                       'daily_counts': {'daily_symbols', 'complete_bars', 'bar_conflicts', 'fallback_symbols', 'fallback_bars_filled',
                                        'fallback_symbols_unresolved', 'symbols_with_unreadable_splits', 'unattributable_split_rows'}},
    'commit_launch': {'n_cut': None, 'commit_confirmed': None,
                      'commitment_counts': {'registry_rows', 'filtered_symbols', 'liquidity_passed', 'selected_symbols'},
                      'exclusion_reasons': {'data_ineligible', 'classification_excluded', 'close_below_5', 'adv_below_15000000', 'n_cut_excluded',
                                            'not_in_causal_list', 'other_reasons'}, 'list_coverage': {'coverage_numerator', 'coverage_denominator'}},
    'publish_launch': {'selected_count': None, 'readback_available': None, 'channel_relay': None},
    'components_launch': {'daily_components': {'component_symbols', 'incomplete_components'}, 'logical_fetch_calls': None,
                          'earnings_counts': {'earnings_symbols', 'live_symbols', 'covered_symbols', 'with_events', 'excluded_symbols',
                                              'earnings_within_horizon', 'earnings_expected_within_horizon', 'earnings_not_tracked',
                                              'earnings_last_report_unknown', 'earnings_evidence_invalid', 'earnings_source_unavailable'}},
    'sources_launch': {'list_symbols': None, 'complete_symbols': None, 'failed_symbols': None, 'http_attempts': None, 'http_kib': None,
                       'bytes_written_kib': None, 'database_rows': None, 'database_readonly': None, 'role_verified': None, 'elapsed_seconds': None,
                       'fundamentals_fetch': FETCH, 'grades_fetch': FETCH, 'institutional_fetch': FETCH},
    'bind': {'list_symbols': None, 'source_pins_files': None},
    'stage': {'list_symbols': None, 'risk_staged': None, 'ready_symbols': None, 'completed_null': None},
    'capture_launch': {'capture_complete': None, 'consumer_failed': None, 'snapshot_publications': None, 'quoted_symbols': None, 'list_symbols': None,
                       'rejected_ticks': {'payload_error', 'not_json', 'not_object', 'symbol_not_listed', 'tick_clock_invalid', 'tick_in_future',
                                          'tick_regresses', 'other_reason'},
                       'component_diagnostics': {a + b for a in ('daily_', 'risk_', 'earnings_') for b in ('component_absent', 'document_invalid',
                                                 'component_invalid')} | {'registry_row_absent', 'other_diagnostic'}}}
EXPECTED_OUTPUTS = {
    'collect_launch': {'day/inputs/registry.json', 'day/inputs/registry.receipt.json', 'day/inputs/daily_contract.json', 'day/inputs/daily_contract.receipt.json'},
    'commit_launch': {'day/causal/commitment.private.json', 'day/causal/build_audit_receipt.json'},
    'publish_launch': {'day/control/symbols.txt', 'day/causal/publication_receipt.json', 'source/causal_list/%s/%s.json' % (W.EPOCH, DAY),
                       'day/relay/causal_publications/%s/%s.json' % (W.EPOCH, DAY)},
    'components_launch': {'source/components/%s/registry.json' % DAY, 'source/components/%s/earnings.json' % DAY},
    'sources_launch': {'day/risk/plan/replay.private.json', 'day/risk/plan/risk-input-names.private.json', 'day/risk/plan/sources/census.json',
                       'day/risk/plan/sources/timings.json', 'day/risk/plan/sources/database.READONLY.json'},
    'bind': {'day/risk/plan/' + n for n in ('HOST_PLAN.json', 'GO.json', 'OWNER_ORDER.json', 'SOURCE_PINS.json', 'list.private.json',
                                             'replay.private.json', 'risk-input-names.private.json')},
    'stage': {'source/components/%s/risk.json' % DAY},
    'capture_launch': {'source/snapshot.json', 'source/tape/%s.us-quote.ndjson' % DAY}}
SECRETS = [CANARY, PASSWORD, 'CANARYDSN', 'CANARY']


def closed_codes():
    """Every failure code the runner can write: its Stop literals, PASS, and the five categories of code_of."""
    tree = ast.parse((W.ROOT / 'src' / 'k9_runner.readable.py').read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) in ('need', 'fail', 'Stop'):
            for arg in node.args[:2] if getattr(node.func, 'id', None) == 'Stop' else node.args[1:2]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
    spec = importlib.util.spec_from_file_location('k9_runner_codes', W.RUNNER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return (found - {'REFUSED', 'FAILED'}) | set(m.PASS) | set(m.CATEGORY.values()) | {'DATABASE_FAILURE', 'FILESYSTEM_FAILURE',
                                                                                      'UNCLASSIFIED_FAILURE', 'RUN_NOT_AFTER_REACHED'}


CODES = closed_codes()


def conform(w, op, psha):
    """K9R's checks of the runner files (_runner/_identity_ok/k9_outputs_ok/k9_counts) on what this run left."""
    rec = w.day / 'receipts'
    files = {k: rec / ('%s.%s.json' % (op, k)) for k in ('STARTED', 'RECEIPT', 'FAILED')}
    assert files['STARTED'].exists()
    assert files['RECEIPT'].exists() != files['FAILED'].exists()
    docs = {}
    for kind, path in files.items():
        if not path.exists():
            continue
        info = os.lstat(path)
        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
        raw = path.read_bytes()
        assert raw == W.canon(json.loads(raw))
        for secret in SECRETS + SYMBOLS + [str(w.base)]:
            assert secret.encode() not in raw, (kind, secret)
        d = docs[kind] = json.loads(raw)
        phase = W.PHASE[op]
        keys = K9R.K9_STARTED_KEYS if kind == 'STARTED' else K9R.K9_STEP_KEYS
        assert set(d) == keys and d['epoch'] == W.EPOCH and d['day'] == DAY and d['phase'] == phase and d['operation'] == op
        assert d['attempt_key'] == K9R.k9_attempt_key(W.EPOCH, DAY, phase, op) and d['step_plan_sha256'] == psha
        assert d['schema'] == (K9R.K9_STARTED_SCHEMA if kind == 'STARTED' else K9R.K9_STEP_SCHEMA)
        K9R.instant(d['started_at'])
        if kind == 'STARTED':
            continue
        # the observed values, by design: a FAILED of another image (or one refused before the package was computed) is
        # read by K9R as not of this step (UNCERTAIN), never as COMPLETE
        if d['package_sha256'] != K9R.K9_PACKAGE_SHA256:
            assert d['code'] in ('PACKAGE_NOT_THE_CERTIFIED_ONE', 'PACKAGE_UNAVAILABLE', 'SOURCE_PINS_NOT_THE_SIGNED_ONES', 'PLAN_INVALID')
            assert re.fullmatch('[0-9a-f]{64}', d['package_sha256'])
        if d['build_sha'] != K9R.K9_CODE_REVISION:
            assert d['build_sha'] == '' and d['code'] in ('BUILD_SHA_NOT_THE_PINNED_ONE', 'SOURCE_PINS_NOT_THE_SIGNED_ONES', 'PACKAGE_UNAVAILABLE',
                                                          'PACKAGE_NOT_THE_CERTIFIED_ONE', 'PLAN_INVALID')
        assert K9R.instant(d['started_at']) <= K9R.instant(d['completed_at']) and d['started_at'] == docs['STARTED']['started_at']
        assert K9R.k9_outputs_ok(d['outputs'], d['aggregates']) and K9R.k9_counts(d['counts'])
        if kind == 'RECEIPT':
            assert d['status'] == 'COMPLETE' and d['code'] is None
        else:
            assert d['status'] in K9R.K9_STEP_FAILED_STATUSES and K9R.text(d['code'], K9R.K9_CONSTANT_CODE) and d['code'] in CODES, d['code']
            assert d['outputs'] == {} and d['aggregates'] == {}
            assert set(d['counts']) <= set(EXPECTED_COUNTS[op]), d['counts']          # partial counts, closed set
    return docs.get('RECEIPT') or docs['FAILED']


def run(w, op, expect_exit=None, plan=None, **kw):
    psha = plan if plan is not None else w.plan(op)
    code, out, err = w.run(op, plan=psha, **kw)
    assert err == b''                                         # the runner silences stderr (QUIET)
    if expect_exit is not None:
        assert code == expect_exit, (code, w.logs('exception')[-1:])
    if code in (0, 1):
        d = conform(w, op, psha)
        if W.NETWORK[op] == 'NONE':                               # attached: the terminal receipt is the one result line
            assert out == (w.day / 'receipts' / ('%s.%s.json' % (op, 'RECEIPT' if code == 0 else 'FAILED'))).read_bytes() + b'\n'
        else:
            assert out == b''
        return d
    assert out == b''
    return None


def rehash(w, receipt):
    for key, digest in receipt['outputs'].items():
        parts = key.split('/')
        base = w.day if parts[0] == 'day' else w.source
        assert sha((base / '/'.join(parts[1:])).read_bytes()) == digest, key
    for key, value in receipt['aggregates'].items():
        parts = key.split('/')
        directory = (w.day if parts[0] == 'day' else w.source) / '/'.join(parts[1:])
        digests = sorted(sha(p.read_bytes()) for p in directory.iterdir())
        assert value == {'files': len(digests), 'sha256': sha(W.canon(digests))}


def closed_counts(op, counts):
    expected = EXPECTED_COUNTS[op]
    assert set(counts) == set(expected), (op, set(counts) ^ set(expected))
    for key, nested in expected.items():
        if nested is None:
            assert type(counts[key]) is int
        else:
            assert set(counts[key]) == nested and all(type(v) is int for v in counts[key].values()), key


# ---------------------------------------------------------------- the whole eve and morning, once
CHAIN = {}


@pytest.fixture(scope='module')
def chain():
    if CHAIN:
        return CHAIN
    w = World('chain')
    for op in ('collect_launch', 'commit_launch', 'publish_launch', 'components_launch', 'sources_launch', 'bind'):
        CHAIN[op] = run(w, op, 0)
    spool = w.day / 'risk' / 'spool' / sha((w.day / 'risk' / 'plan' / 'HOST_PLAN.json').read_bytes())
    assert w.packaged('preflight') == 0
    assert w.packaged('acquire', sha((spool / 'preflight.RECEIPT.json').read_bytes())) == 0
    assert w.packaged('execute', sha((spool / 'acquire.RECEIPT.json').read_bytes())) == 0
    CHAIN['stage'] = run(w, 'stage', 0)
    w.clock = datetime.fromisoformat('2026-10-06T13:59:56+00:00')
    CHAIN['capture_launch'] = run(w, 'capture_launch', 0, plan=w.plan('capture_launch', run_not_after='2026-10-06T14:03:00+00:00'), speed=8.0)
    CHAIN['world'] = w
    return CHAIN


@pytest.mark.parametrize('op', ['collect_launch', 'commit_launch', 'publish_launch', 'components_launch', 'sources_launch', 'bind', 'stage',
                                'capture_launch'])
def test_happy_path_receipt(chain, op):
    receipt = chain[op]
    assert receipt['status'] == 'COMPLETE'
    assert set(receipt['outputs']) == EXPECTED_OUTPUTS[op]
    rehash(chain['world'], receipt)
    closed_counts(op, receipt['counts'])


def test_chain_facts(chain):
    w = chain['world']
    assert chain['collect_launch']['counts']['logical_fetch_calls'] == 41                       # 1 registry + 20 bulk + 20 splits
    assert chain['commit_launch']['counts']['commitment_counts']['selected_symbols'] == len(SYMBOLS)
    assert (w.day / 'control' / 'symbols.txt').read_text().split() == sorted(SYMBOLS)
    assert chain['components_launch']['aggregates']['source/components/%s/daily_61' % DAY]['files'] == len(SYMBOLS)
    assert chain['components_launch']['counts']['logical_fetch_calls'] == 2 * len(SYMBOLS) + 1 + len(SYMBOLS)
    assert chain['sources_launch']['counts']['http_attempts'] == 3 * len(SYMBOLS)
    capture = chain['capture_launch']['counts']
    assert capture['capture_complete'] == 1 and capture['quoted_symbols'] == len(SYMBOLS) and sum(capture['component_diagnostics'].values()) == 0
    # the commitment file is the confirmed commitment build returned, hashed as the emitter's digest
    commitment = json.loads((w.day / 'causal' / 'commitment.private.json').read_bytes())
    assert sha(W.canon(commitment)) == chain['commit_launch']['outputs']['day/causal/commitment.private.json']
    # the GO is recomputed by the packaged executor (preflight/acquire/execute COMPLETE above); its K9 bindings
    go = json.loads((w.day / 'risk' / 'plan' / 'GO.json').read_bytes())
    assert go['k9_attempt_key'] == W.akey(DAY, 'risk', 'bind') and go['binding']['namespace'] == 'R2D2-V2-DIAG-R4-' + DAY
    assert [p['status'] for p in w.logs('packaged')] == ['COMPLETE'] * 3
    # staged risk.json is the executor's, byte for byte
    spool = w.day / 'risk' / 'spool' / sha((w.day / 'risk' / 'plan' / 'HOST_PLAN.json').read_bytes())
    assert (w.source / 'components' / DAY / 'risk.json').read_bytes() == (spool / 'risk-output' / 'risk.json').read_bytes()


def test_provider_calls_as_packaged(chain):
    w = chain['world']
    calls = w.logs('httpx')
    assert calls and all(c['token_ok'] and c['timeout'] == 15.0 for c in calls)        # settings.market_data_timeout_seconds
    assert all(c['token_ok'] for c in w.logs('risk_http'))
    emitter = [c for c in w.logs('connect') if c['role'] == 'emitter']
    assert emitter and all(c['user'] == 'c3po_v2_causal_emitter' and c['host'] == 'db' and c['dbname'] == 'c3po' and c['password_ok']
                           and c['require_auth'] == 'scram-sha-256' for c in emitter)
    readers = [c for c in w.logs('connect') if c['role'] == 'reader']
    assert readers and all(c['dsn_ok'] and c['options'] == '-c default_transaction_read_only=on' for c in readers)


def test_no_secret_symbol_or_path_in_any_step_file(chain):
    w = chain['world']
    for path in (w.day / 'receipts').iterdir():
        raw = path.read_bytes()
        for needle in SECRETS + SYMBOLS + [str(w.base), '/c3po-']:
            assert needle.encode() not in raw, (path.name, needle)


# ---------------------------------------------------------------- refusals before anything is written (exit 2)
def fresh(name, chain=None, *parts):
    w = World(name)
    if chain is not None:
        src = chain['world']
        for part in parts:
            s, d = src.base / part, w.base / part
            W.mkdir(d.parent)                                       # a private directory, as K9W and the runner make them
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    return w


def nothing_written(w, op):
    rec = w.day / 'receipts'
    return not rec.exists() or not any(p.name.startswith(op + '.') for p in rec.iterdir())


@pytest.mark.parametrize('case', ['attempt_key', 'hash', 'not_canonical', 'day', 'argv', 'other_plan', 'epoch', 'schema'])
def test_plan_identity_refusals_write_nothing(case):
    w = fresh('identity-' + case)
    op = 'collect_launch'
    if case == 'attempt_key':
        psha = w.plan(op, attempt_key='ab' * 32)
    elif case == 'hash':
        w.plan(op)
        psha = 'cd' * 32
    elif case == 'not_canonical':
        w.plan(op)
        psha = w.plan(op, _raw=json.dumps(json.loads((w.day / 'plans' / (op + '.json')).read_bytes()), indent=1).encode())
    elif case == 'day':
        psha = w.plan(op, day='2026-10-05', attempt_key=W.akey('2026-10-05', 'causal_list', op))
    elif case == 'epoch':
        psha = w.plan(op, epoch='R2D2-V2-SHADOW-2026-10-06')
    elif case == 'schema':
        psha = w.plan(op, schema='K9_STEP_PLAN_V2')
    else:
        psha = w.plan(op)
    cfg = {}
    if case == 'argv':
        cfg['argv'] = ['--plan', str(w.day / 'plans' / (op + '.json')), '--plan-sha256', psha, '--extra']
    if case == 'other_plan':
        w.plan('commit_launch')
        cfg['argv'] = ['--plan', str(w.day / 'plans' / 'commit_launch.json'), '--plan-sha256', psha]
    assert run(w, op, 2, plan=psha, **cfg) is None
    assert nothing_written(w, op) and w.logs('httpx') == []


@pytest.mark.parametrize('kind', ['STARTED', 'RECEIPT', 'FAILED'])
def test_exclusive_create_collision(kind):
    w = fresh('collision-' + kind)
    rec = W.mkdir(w.day / 'receipts')
    marker = rec / ('collect_launch.%s.json' % kind)
    marker.write_bytes(b'{"prior":true}')
    os.chmod(marker, 0o600)
    assert run(w, 'collect_launch', 3) is None
    assert marker.read_bytes() == b'{"prior":true}'
    assert sorted(p.name for p in rec.iterdir()) == [marker.name] and w.logs('httpx') == []


def test_started_collision_during_the_race(chain):
    """A second container of the same step finds the first one's marker at its own exclusive create: exit 3, no receipt."""
    w = fresh('collision-race')
    rec = W.mkdir(w.day / 'receipts')
    psha = w.plan('collect_launch')
    # the marker appears between the pre-check and the exclusive create: emulated by a directory entry that is a link
    os.symlink('elsewhere', rec / 'collect_launch.STARTED.json')
    assert run(w, 'collect_launch', 3, plan=psha) is None
    assert os.path.islink(rec / 'collect_launch.STARTED.json') and len(list(rec.iterdir())) == 1


# ---------------------------------------------------------------- refusals and failures with a FAILED receipt (exit 1)
def failed(w, op, code, status='REFUSED', **kw):
    d = run(w, op, 1, **kw)
    assert d['status'] == status and d['code'] == code, (d['status'], d['code'], w.logs('exception')[-1:])
    return d


def copied_app(w, change=None):
    app = w.base / 'app-copy'
    shutil.copytree(W.APP + '/app', app / 'app')
    if change:
        with open(app / 'app' / change, 'a') as handle:
            handle.write('\n# a byte that is not the certified package\n')
    return app


@pytest.mark.parametrize('op', ['collect_launch', 'commit_launch', 'sources_launch', 'bind', 'stage', 'capture_launch'])
def test_source_pins_refused_before_any_import_from_app(op):
    """M1: every operation hashes /app/app/**/*.py with the standard library first; a byte changed in any module the
    operations import (here the emitter) is refused before the package is computed (zeros) and before any call."""
    w = fresh('pins-' + op)
    app = copied_app(w, 'r2d2_v2_causal_emitter.py')
    d = failed(w, op, 'SOURCE_PINS_NOT_THE_SIGNED_ONES', app=str(app), paths={'APP': str(app)})
    assert d['package_sha256'] == '0' * 64 and d['counts'] == {}
    assert w.logs('httpx') == [] and w.logs('connect') == [] and w.logs('risk_http') == []


def test_package_sha_mismatch():
    """The package check stays: a tree whose pins are the signed ones but whose package hash is not."""
    w = fresh('package')
    app = copied_app(w, 'config.py')
    d = failed(w, 'collect_launch', 'PACKAGE_NOT_THE_CERTIFIED_ONE', app=str(app), paths={'APP': str(app)},
               plan=w.plan('collect_launch', constants={'risk_source_pins_sha256': W.source_pins_sha256(str(app))}))
    assert d['package_sha256'] not in (W.PACKAGE, '0' * 64) and w.logs('httpx') == []


def test_package_unavailable():
    w = fresh('package-absent')
    empty = W.mkdir(w.base / 'no-app')
    W.mkdir(empty / 'app')
    d = failed(w, 'collect_launch', 'PACKAGE_UNAVAILABLE', paths={'APP': str(empty)}, app=str(empty),
               plan=w.plan('collect_launch', constants={'risk_source_pins_sha256': W.source_pins_sha256(str(empty))}))
    assert d['package_sha256'] == '0' * 64


def test_runner_file_not_named_by_its_hash():
    """(7) the running file must be k9_runner-<sha256>.py with that content."""
    w = fresh('runner-name')
    other = w.tools / 'k9_runner.py'
    other.write_bytes(w.runner.read_bytes())
    failed(w, 'collect_launch', 'RUNNER_NOT_THE_SIGNED_ONE', runner=str(other))
    w = fresh('runner-name-content')
    wrong = w.tools / ('k9_runner-%s.py' % ('ab' * 32))
    wrong.write_bytes(w.runner.read_bytes())
    failed(w, 'collect_launch', 'RUNNER_NOT_THE_SIGNED_ONE', runner=str(wrong))


@pytest.mark.parametrize('case,code', [
    ('runner', 'RUNNER_NOT_THE_SIGNED_ONE'), ('limits', 'CONSTANTS_NOT_THE_COMPILED_ONES'), ('floor', 'CONSTANTS_NOT_THE_COMPILED_ONES'),
    ('package', 'CONSTANTS_NOT_THE_COMPILED_ONES'), ('network', 'NETWORK_CLASS_NOT_OF_THIS_OPERATION'),
    ('database', 'DATABASE_NOT_OF_THIS_OPERATION'), ('slot', 'PLAN_INVALID'), ('extra', 'PLAN_INVALID'), ('risk', 'PLAN_INVALID'),
    ('run_not_after', 'PLAN_INVALID'), ('request', 'PLAN_INVALID')])
def test_plan_refusals(case, code):
    w = fresh('plan-' + case)
    over = {'runner': {'constants': {'runner_sha256': 'ab' * 32}}, 'limits': {'constants': {'risk_limits': dict(W.LIMITS, max_symbols=551)}},
            'floor': {'constants': {'disk_floor_bytes': 1}}, 'package': {'constants': {'package_sha256': 'ab' * 32}},
            'network': {'network_class': 'DATABASE'}, 'database': {'database': {'host': 'db', 'port': 5432, 'dbname': 'c3po', 'role': 'x'}},
            'slot': {'slot': 'THIRD'}, 'extra': {'unexpected': 1}, 'risk': {'risk': {}}, 'run_not_after': {'run_not_after': '2026-10-05T22:59:00-03:00'},
            'request': {'request_sha256': 'XYZ'}}[case]
    failed(w, 'collect_launch', code, plan=w.plan('collect_launch', **over))
    assert w.logs('httpx') == []


def test_build_sha_mismatch():
    w = fresh('build-sha')
    failed(w, 'collect_launch', 'BUILD_SHA_NOT_THE_PINNED_ONE', env=w.env('collect_launch', C3PO_BUILD_SHA='0' * 40))


def test_run_not_after_passed():
    w = fresh('rna-passed')
    failed(w, 'collect_launch', 'RUN_NOT_AFTER_PASSED', plan=w.plan('collect_launch', run_not_after=(w.clock + timedelta(seconds=30)).isoformat()))
    assert w.logs('httpx') == []


def test_deadline_interrupts_an_http_call():
    """(6) one provider call that would block 40 s: the alarm at run_not_after - 60 s interrupts it inside the call."""
    w = fresh('deadline')
    started = datetime.now()
    d = failed(w, 'collect_launch', 'RUN_NOT_AFTER_REACHED', status='DEADLINE',
               plan=w.plan('collect_launch', run_not_after=(w.clock + timedelta(seconds=70)).isoformat()), provider={'delay': 40})
    elapsed = (datetime.now() - started).total_seconds()
    assert elapsed < 20, elapsed                                                  # far below the 40 s the call would take
    assert len(w.logs('httpx')) == 1 and d['counts'] == {'logical_fetch_calls': 1}  # counts gathered so far are kept


def test_deadline_between_calls_keeps_counts():
    w = fresh('deadline-loop')
    d = failed(w, 'collect_launch', 'RUN_NOT_AFTER_REACHED', status='DEADLINE',
               plan=w.plan('collect_launch', run_not_after=(w.clock + timedelta(seconds=72)).isoformat()), provider={'delay': 1.0})
    assert 0 < d['counts']['logical_fetch_calls'] == len(w.logs('httpx')) < 41


def test_producers_off():
    w = fresh('producers-off')
    failed(w, 'collect_launch', 'PRODUCERS_NOT_ENABLED', env=w.env('collect_launch', C3PO_R2D2_V2_PRODUCERS_ENABLED='false'))
    assert w.logs('httpx') == []


def test_provider_failure_is_retried_twice_then_fails():
    w = fresh('provider-fails')
    failed(w, 'collect_launch', 'PROVIDER_REQUEST_FAILED', status='FAILED', provider={'fail_paths': ['/api/exchange-symbol-list']})
    assert len(w.logs('httpx')) == 3                                                             # retries=2, packaged default


def test_provider_token_missing():
    w = fresh('token-missing')
    failed(w, 'collect_launch', 'PROVIDER_TOKEN_MISSING', status='FAILED', env=w.env('commit_launch'))


def test_previous_session_not_closed():
    w = fresh('not-closed')
    w.clock = datetime.fromisoformat('2026-10-05T19:30:00+00:00')
    failed(w, 'collect_launch', 'PREVIOUS_SESSION_NOT_CLOSED', status='FAILED')


def test_collect_inputs_present():
    w = fresh('inputs-present')
    W.mkdir(w.day / 'inputs')
    failed(w, 'collect_launch', 'OUTPUT_ALREADY_PRESENT')


COLLECTED = ('day/inputs', 'day/receipts/collect_launch.STARTED.json', 'day/receipts/collect_launch.RECEIPT.json')
COMMITTED = COLLECTED + ('db.json', 'day/causal', 'day/receipts/commit_launch.STARTED.json', 'day/receipts/commit_launch.RECEIPT.json')
PUBLISHED = COMMITTED + ('day/control', 'day/relay', 'source/causal_list', 'day/receipts/publish_launch.STARTED.json',
                         'day/receipts/publish_launch.RECEIPT.json')


def published_world(name, chain, *more):
    w = fresh(name, chain, *(PUBLISHED + more))
    (w.day / 'causal' / 'publication_receipt.json').exists()
    return w


def test_commit_without_collect(chain):
    failed(fresh('commit-alone'), 'commit_launch', 'PREDECESSOR_NOT_COMPLETE')


def test_commit_with_failed_collect(chain):
    w = fresh('commit-failed-pred', chain, *COLLECTED)
    (w.day / 'receipts' / 'collect_launch.FAILED.json').write_bytes(b'{}')
    failed(w, 'commit_launch', 'PREDECESSOR_NOT_COMPLETE')


def test_commit_input_changed(chain):
    w = fresh('commit-input-changed', chain, *COLLECTED)
    path = w.day / 'inputs' / 'registry.json'
    path.write_bytes(path.read_bytes() + b' ')
    failed(w, 'commit_launch', 'PREDECESSOR_OUTPUT_CHANGED')


def test_commit_predecessor_receipt_forged(chain):
    w = fresh('commit-forged', chain, *COLLECTED)
    path = w.day / 'receipts' / 'collect_launch.RECEIPT.json'
    doc = json.loads(path.read_bytes())
    doc['package_sha256'] = 'ab' * 32
    path.write_bytes(W.canon(doc))
    failed(w, 'commit_launch', 'PREDECESSOR_NOT_COMPLETE')


@pytest.mark.parametrize('case,code,status', [
    ('password', 'DATABASE_FAILURE', 'FAILED'), ('pgenv', 'EMITTER_ENVIRONMENT_NOT_CLEAN', 'REFUSED'),
    ('dsnenv', 'EMITTER_ENVIRONMENT_NOT_CLEAN', 'REFUSED'), ('identity', 'EMITTER_IDENTITY_MISMATCH', 'FAILED'),
    ('libpq', 'LIBPQ16_REQUIRED', 'REFUSED'), ('late', 'COMMIT_AFTER_ITS_LATEST_START', 'REFUSED'),
    ('password_file', 'INPUT_FILE_NOT_PRIVATE', 'REFUSED'), ('present', 'OUTPUT_ALREADY_PRESENT', 'REFUSED')])
def test_commit_refusals(chain, case, code, status):
    w = fresh('commit-' + case, chain, *COLLECTED)
    kw = {}
    if case == 'password':
        kw['db'] = {'password': 'another'}
    elif case == 'pgenv':
        kw['env'] = w.env('commit_launch', PGPASSWORD='x')
    elif case == 'dsnenv':
        kw['env'] = w.env('commit_launch', C3PO_R2D2_RISK_DATABASE_URL=DSN)
    elif case == 'identity':
        kw['db'] = {'identity': ['c3po', 'postgres', 'postgres', 'origin']}
    elif case == 'libpq':
        kw['libpq'] = 150004
    elif case == 'late':
        w.clock = datetime.fromisoformat('2026-10-06T03:51:00+00:00')
        kw['plan'] = w.plan('commit_launch')
    elif case == 'password_file':
        os.chmod(w.emitter / 'password', 0o644)
    elif case == 'present':
        W.mkdir(w.day / 'causal')
        (w.day / 'causal' / 'commitment.private.json').write_bytes(b'{}')
    d = failed(w, 'commit_launch', code, status=status, **kw)
    assert not (w.base / 'db.json').exists() or case == 'present'
    for secret in (PASSWORD, 'another', DSN):
        assert secret.encode() not in W.canon(d)


def test_commit_slot_conflict_with_other_inputs(chain):
    """The database already holds this day's commitment built from other bytes (an earlier PRIMARY): the emitter refuses."""
    w = fresh('commit-conflict', chain, *COLLECTED, 'db.json')
    path = w.day / 'inputs' / 'daily_contract.json'
    receipt = w.day / 'receipts' / 'collect_launch.RECEIPT.json'
    doc = json.loads(receipt.read_bytes())
    data = path.read_bytes().replace(b'"source_at"', b'"source_at"', 1)
    obj = json.loads(data)
    obj['instruments'] = obj['instruments'][:-1]
    path.write_bytes(W.canon(obj))
    doc['outputs']['day/inputs/daily_contract.json'] = sha(path.read_bytes())
    receipt.write_bytes(W.canon(doc))
    failed(w, 'commit_launch', 'CAUSAL_SLOT_INPUT_CONFLICT', status='FAILED')


def test_publish_without_commit(chain):
    failed(fresh('publish-alone', chain, *COLLECTED), 'publish_launch', 'PREDECESSOR_NOT_COMPLETE')


def test_publish_database_down(chain):
    w = fresh('publish-down', chain, *COMMITTED)
    failed(w, 'publish_launch', 'DATABASE_FAILURE', status='FAILED', db={'down': True})


def test_publish_commitment_file_changed(chain):
    w = fresh('publish-changed', chain, *COMMITTED)
    path = w.day / 'causal' / 'commitment.private.json'
    path.write_bytes(path.read_bytes()[:-1] + b' }')
    failed(w, 'publish_launch', 'PREDECESSOR_OUTPUT_CHANGED')


def test_components_symbols_changed(chain):
    w = published_world('components-symbols', chain)
    path = w.day / 'control' / 'symbols.txt'
    os.chmod(path, 0o600)
    path.write_bytes(path.read_bytes().replace(b'ZQAA\n', b''))
    failed(w, 'components_launch', 'PREDECESSOR_OUTPUT_CHANGED')


def test_components_already_present(chain):
    w = published_world('components-present', chain)
    W.mkdir(W.mkdir(w.source / 'components') / DAY)
    failed(w, 'components_launch', 'OUTPUT_ALREADY_PRESENT')
    assert w.logs('httpx') == []


def test_components_without_publish(chain):
    failed(fresh('components-alone', chain, *COMMITTED), 'components_launch', 'PREDECESSOR_NOT_COMPLETE')


@pytest.mark.parametrize('case,code,status', [
    ('role', 'ROLE_NOT_RESTRICTED', 'FAILED'), ('dsn', 'RESTRICTED_DSN_REQUIRED', 'REFUSED'), ('wrong_dsn', 'DATABASE_FAILURE', 'FAILED'),
    ('present', 'OUTPUT_ALREADY_PRESENT', 'REFUSED'), ('floor', 'DISK_FREE_BELOW_FLOOR', 'REFUSED')])
def test_sources_refusals(chain, case, code, status):
    w = published_world('sources-' + case, chain)
    kw = {}
    if case == 'role':
        kw['db'] = {'reader_role': ['c3po_admin', 'c3po_admin']}
    elif case == 'dsn':
        kw['env'] = w.env('sources_launch', C3PO_R2D2_RISK_DATABASE_URL=None)
    elif case == 'wrong_dsn':
        kw['db'] = {'dsn': 'postgresql://someone-else'}
    elif case == 'present':
        W.mkdir(W.mkdir(w.day / 'risk') / 'plan')
    elif case == 'floor':
        kw['plan'] = w.plan('sources_launch', constants={'disk_floor_bytes': 1 << 60})
        kw['floor'] = 1 << 60
    d = failed(w, 'sources_launch', code, status=status, **kw)
    assert w.logs('risk_http') == []


BOUND_INPUTS = PUBLISHED + ('day/risk', 'day/receipts/sources_launch.STARTED.json', 'day/receipts/sources_launch.RECEIPT.json')


def sourced_world(name, chain):
    """A world holding the chain's state up to sources (its plan directory without bind's five files)."""
    w = fresh(name, chain, *PUBLISHED, 'day/receipts/sources_launch.STARTED.json', 'day/receipts/sources_launch.RECEIPT.json')
    src = chain['world'].day / 'risk' / 'plan'
    dst = W.mkdir(W.mkdir(w.day / 'risk') / 'plan')
    for path in src.iterdir():
        if path.name in ('replay.private.json', 'risk-input-names.private.json'):
            shutil.copy2(path, dst / path.name)
    shutil.copytree(src / 'sources', dst / 'sources')
    return w


@pytest.mark.parametrize('case,code', [
    ('order_hash', 'OWNER_ORDER_NOT_THE_SIGNED_BYTES'), ('order_scope', 'OWNER_ORDER_SCOPE_MISMATCH'), ('namespace', 'NAMESPACE_NOT_THE_DECIDED_ONE'),
    ('pins', 'SOURCE_PINS_NOT_THE_SIGNED_ONES'), ('windows_day', 'RISK_WINDOWS_INVALID'), ('windows_order', 'RISK_WINDOWS_INVALID'),
    ('cutoff_after', 'RISK_WINDOWS_INVALID'), ('replay_changed', 'PREDECESSOR_OUTPUT_CHANGED'), ('no_sources', 'PREDECESSOR_NOT_COMPLETE'),
    ('already', 'OUTPUT_ALREADY_PRESENT')])
def test_bind_refusals(chain, case, code):
    w = sourced_world('bind-' + case, chain)
    risk = w.risk()
    over = {}
    if case == 'order_hash':
        risk['owner_order_sha256'] = 'ab' * 32
    elif case == 'order_scope':
        order = json.loads(risk['owner_order_text'])
        order['scope']['cutoff_at'] = (w.clock - timedelta(minutes=2)).isoformat()
        risk['owner_order_text'] = W.canon(order).decode()
        risk['owner_order_sha256'] = sha(risk['owner_order_text'].encode())
    elif case == 'namespace':
        risk['namespace'] = 'R2D2-V2-SHADOW-' + DAY
    elif case == 'pins':
        over['constants'] = {'risk_source_pins_sha256': 'ab' * 32}
    elif case == 'windows_day':
        risk['phase_windows']['execute']['not_after'] = '2026-10-06T15:00:00+00:00'
    elif case == 'windows_order':
        risk['phase_windows']['acquire']['not_after'] = risk['phase_windows']['acquire']['not_before']
    elif case == 'cutoff_after':
        risk = w.risk(cutoff=(w.clock + timedelta(minutes=5)).isoformat())
    elif case == 'replay_changed':
        path = w.day / 'risk' / 'plan' / 'replay.private.json'
        path.write_bytes(path.read_bytes() + b' ')
    elif case == 'no_sources':
        (w.day / 'receipts' / 'sources_launch.RECEIPT.json').rename(w.day / 'receipts' / 'sources_launch.RECEIPT.json.aside')
    elif case == 'already':
        W.mkdir(w.day / 'risk' / 'spool')
    failed(w, 'bind', code, plan=w.plan('bind', risk=risk, **over))
    assert not (w.day / 'risk' / 'plan' / 'GO.json').exists()


def test_bind_risk_absent_is_a_plan_refusal(chain):
    w = sourced_world('bind-norisk', chain)
    failed(w, 'bind', 'PLAN_INVALID', plan=w.plan('bind', risk=None))


def staged_world(name, chain):
    return fresh(name, chain, *PUBLISHED, 'day/risk', 'day/receipts/bind.STARTED.json', 'day/receipts/bind.RECEIPT.json')


def test_stage_refusals(chain):
    w = staged_world('stage-no-execute', chain)
    spool = w.day / 'risk' / 'spool' / sha((w.day / 'risk' / 'plan' / 'HOST_PLAN.json').read_bytes())
    (spool / 'execute.RECEIPT.json').rename(spool / 'execute.RECEIPT.json.aside')
    failed(w, 'stage', 'PREDECESSOR_NOT_COMPLETE')
    w = staged_world('stage-risk-changed', chain)
    spool = w.day / 'risk' / 'spool' / sha((w.day / 'risk' / 'plan' / 'HOST_PLAN.json').read_bytes())
    path = spool / 'risk-output' / 'risk.json'
    path.write_bytes(path.read_bytes() + b' ')
    failed(w, 'stage', 'RISK_OUTPUT_NOT_AS_THE_RECEIPT_SAYS', status='FAILED')
    w = staged_world('stage-present', chain)
    W.mkdir(W.mkdir(w.source / 'components') / DAY)
    (w.source / 'components' / DAY / 'risk.json').write_bytes(b'{}')
    failed(w, 'stage', 'OUTPUT_ALREADY_PRESENT')
    w = staged_world('stage-go-changed', chain)                       # (8) HOST_PLAN/GO tied to bind's receipt
    path = w.day / 'risk' / 'plan' / 'GO.json'
    path.write_bytes(path.read_bytes() + b' ')
    failed(w, 'stage', 'PREDECESSOR_OUTPUT_CHANGED')
    w = staged_world('stage-no-bind', chain)
    (w.day / 'receipts' / 'bind.RECEIPT.json').rename(w.day / 'receipts' / 'bind.RECEIPT.json.aside')
    failed(w, 'stage', 'PREDECESSOR_NOT_COMPLETE')
    w = staged_world('stage-shadow', chain)                           # (8) N-1: DIAG-R4 only
    spool = w.day / 'risk' / 'spool' / sha((w.day / 'risk' / 'plan' / 'HOST_PLAN.json').read_bytes())
    path = spool / 'execute.RECEIPT.json'
    doc = json.loads(path.read_bytes())
    doc['namespace'] = 'R2D2-V2-SHADOW-' + DAY
    path.write_bytes(json.dumps(doc).encode())
    failed(w, 'stage', 'PREDECESSOR_NOT_COMPLETE')


def test_capture_refusals(chain):
    w = published_world('capture-off', chain)
    w.clock = datetime.fromisoformat('2026-10-06T13:50:00+00:00')
    failed(w, 'capture_launch', 'PRODUCERS_NOT_ENABLED', plan=w.plan('capture_launch', run_not_after='2026-10-06T14:03:00+00:00'),
           env=w.env('capture_launch', C3PO_R2D2_V2_PRODUCERS_ENABLED=None))
    w = published_world('capture-closed', chain)
    w.clock = datetime.fromisoformat('2026-10-06T14:01:30+00:00')
    failed(w, 'capture_launch', 'CAPTURE_WINDOW_ALREADY_CLOSED', status='FAILED', plan=w.plan('capture_launch', run_not_after='2026-10-06T14:30:00+00:00'))
    w = fresh('capture-alone', chain, *COMMITTED)
    w.clock = datetime.fromisoformat('2026-10-06T13:50:00+00:00')
    failed(w, 'capture_launch', 'PREDECESSOR_NOT_COMPLETE', plan=w.plan('capture_launch', run_not_after='2026-10-06T14:03:00+00:00'))


def test_capture_deadline_before_the_window_closes(chain):
    """run_not_after inside the capture window: the runner stops itself 60 s before it and writes DEADLINE."""
    w = published_world('capture-deadline', chain, 'source/components')
    w.clock = datetime.fromisoformat('2026-10-06T13:59:50+00:00')
    failed(w, 'capture_launch', 'RUN_NOT_AFTER_REACHED', status='DEADLINE', plan=w.plan('capture_launch', run_not_after='2026-10-06T14:01:05+00:00'))


# ---------------------------------------------------------------- the bytes
def test_build_is_the_compaction_of_the_readable_source():
    done = subprocess.run([W.PYTHON, '-B', str(W.ROOT / 'build.py'), 'check'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert done.returncode == 0 and done.stdout.startswith(b'BUILD_OK'), done.stderr
    assert len(W.RUNNER.read_bytes()) <= 40960


def test_runner_imports_only_the_standard_library_at_module_level():
    tree = ast.parse(W.RUNNER.read_text())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = {a.name.split('.')[0] for n in top if isinstance(n, ast.Import) for a in n.names} | {n.module.split('.')[0] for n in top if isinstance(n, ast.ImportFrom)}
    assert names <= {'hashlib', 'json', 'os', 're', 'signal', 'stat', 'sys', 'threading', 'datetime', 'pathlib', 'zoneinfo'}
    text = W.RUNNER.read_text()
    for word in ('subprocess', 'socket', 'eval(', 'exec(', 'print(', 'shutil', 'rmtree', 'unlink(name', 'remove('):
        assert word not in text, word


def test_every_failure_code_is_constant_and_every_count_key_in_k9r_grammar():
    for code in CODES:
        assert K9R.text(code, K9R.K9_CONSTANT_CODE), code
    for op, keys in EXPECTED_COUNTS.items():
        for key, nested in keys.items():
            assert K9R.text(key, K9R.K9_COUNT_KEY), (op, key)
            for inner in nested or ():
                assert K9R.text(inner, K9R.K9_COUNT_KEY), (op, inner)


def test_receipts_directory_not_private_writes_nothing():
    w = fresh('receipts-open')
    rec = (w.day / 'receipts')
    rec.mkdir()
    os.chmod(rec, 0o755)
    assert run(w, 'collect_launch', 2) is None and list(rec.iterdir()) == [] and w.logs('httpx') == []


@pytest.mark.parametrize('limit,code,calls', [('PACE_REQUESTS', 'REQUEST_BUDGET', 5), ('PACE_BYTES', 'BODY_BUDGET', 1)])
def test_sources_budget_stops_the_loop(chain, limit, code, calls):
    """M2: a budget stop is a BaseException: RiskAcquirer._read cannot swallow it as TRANSPORT_FAILED, the loop stops."""
    w = published_world('sources-budget-' + limit, chain)
    d = failed(w, 'sources_launch', code, status='FAILED', **{limit: 5 if limit == 'PACE_REQUESTS' else 10})
    assert len(w.logs('risk_http')) == calls and d['counts']['http_attempts'] == calls
    assert not (w.day / 'risk' / 'plan' / 'replay.private.json').exists()
