"""The reader launcher of c3po/deployment/reader, loaded by path: it is a deployment script, not packaged code.

What is real here: the launcher file itself, the packaged calendar, session list and settings class, the
catalog lock, the worker module as a child process, child processes and signals of this operating system.
What is not: the clock of the phase tests (a fake clock that only sleep() advances), the children of the
phase tests (scripted objects), the collector's source and release in the pre-open test, and everything
about Docker, systemd and the host, which no test in this file touches.
"""
import ast
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_capacity_bound import CapacityBoundCollector
from app.r2d2_v2_capacity_wiring import CapacityLoader
from app.r2d2_v2_capacity_anchored import AnchoredRoot
from app.r2d2_v2_epoch_assembler import SESSIONS
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_shadow import EBAR_AMENDMENT_SHA, Release
from app.r2d2_v2_sources import SourceUnavailable
from app.r2d2_v2_store import MemoryShadowStore, utc
from tests.v2_earnings_fixtures import package_pins

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND.parent / 'deployment' / 'reader' / 'reader_launcher.py'
EPOCH = 'R2D2-V2-SHADOW-READER-LAUNCHER-TEST'
OPEN = datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc)    # 09:30 New York
CLOSE = datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc)    # 16:00 New York
PRIVATE_URL = 'postgresql://reader:NEVERPRINTED@db.invalid/c3po'
# No real wait in this file is allowed to last longer than this: a hang must fail, not block the run.
CEILING_SECONDS = 90.0


def load():
    """By path, and without leaving bytecode next to a deployment file."""
    spec = importlib.util.spec_from_file_location('c3po_reader_launcher', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    module.APP_ROOT = str(BACKEND)
    return module


launcher = load()


@pytest.fixture(scope='module')
def calendar():
    result = ShadowCalendar()
    details = result.details(date(2026, 10, 5))
    assert (details['open'], details['close']) == (OPEN, CLOSE)
    return result


def enabled(**changes):
    """The real settings class, with the reader's variables as the three environment files give them."""
    values = dict(r2d2_v2_shadow_enabled=True, r2d2_v2_massive_bars_enabled=True, database_url=PRIVATE_URL,
        r2d2_v2_massive_journal_dir='/app/day-d-data/journal-leaf', build_sha='a' * 40,
        r2d2_v2_shadow_release_sha='b' * 64, r2d2_v2_capacity_required=True, r2d2_v2_capacity_config_sha='c' * 64)
    return Settings(**{**values, **changes})


class Clock:
    """Time moves only when the launcher sleeps."""
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakeChild:
    def __init__(self, clock, phase, plan):
        self.clock, self.phase, self.plan = clock, phase, plan
        self.spawned_at, self.ended_at, self.code = clock.now, None, None
        self.stops = self.closes = 0

    def poll(self):
        if self.code is None and self.plan.get('exit_at') is not None and self.clock.now >= self.plan['exit_at']:
            self.code, self.ended_at = self.plan['exit_code'], self.clock.now
        return self.code

    def stop(self, grace=None):
        self.stops += 1
        if self.poll() is not None:
            return self.code, False, False
        code, by_parent, killed = self.plan.get('stop', (-signal.SIGTERM, True, False))
        self.code, self.ended_at = code, self.clock.now
        return code, by_parent, killed

    def close(self):
        self.closes += 1

    def failure(self):
        return dict(self.plan.get('failure', {}))

    def counts(self):
        return {'status_lines': 3, 'status_withheld': 0, 'dropped_lines': 1}


def run_day(calendar, start, *, plans=None, stop_at=None, ready_at=None, settings=None, sessions=SESSIONS,
            pin='', sha=None):
    clock = Clock(start); notices = []; children = []

    def spawn(phase):
        children.append(FakeChild(clock, phase, (plans or {}).get(phase, {})))
        return children[-1]

    status = launcher.supervise(utcnow=clock, sleep=clock.sleep, notice=notices.append, spawn=spawn,
        calendar=calendar, sessions=sessions, settings=settings or enabled,
        stop_requested=lambda: stop_at is not None and clock.now >= stop_at,
        ready=lambda journal, key: ready_at is not None and clock.now >= ready_at,
        launcher_sha=sha, launcher_pin=pin)
    # Whatever the outcome, no child is left running and every notice is one JSON line without the secret.
    assert all(child.code is not None and child.closes >= 1 for child in children)
    text = [json.dumps(item, sort_keys=True) for item in notices]
    assert not any('\n' in line or 'NEVERPRINTED' in line or '/app/' in line for line in text)
    return status, notices, children, clock


def codes(notices):
    return [(item['status'], item.get('phase'), item.get('code') or item.get('reason')) for item in notices]


def forbidden(*_args, **_kwargs):
    raise AssertionError('must not be reached')


# ---------------------------------------------------------------- refusals

@pytest.mark.parametrize('now,code', [
    (datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc), 'READER_SESSION'),    # an exchange session before the epoch
    (datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc), 'READER_SESSION'),    # Saturday
    (datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc), 'READER_SESSION'),   # an exchange session after the epoch
    # The New York date decides, not the UTC date.
    (datetime(2026, 10, 5, 3, 59, tzinfo=timezone.utc), 'READER_SESSION'),    # still Sunday the 4th in New York
    (datetime(2026, 10, 6, 3, 59, tzinfo=timezone.utc), 'READER_WINDOW'),     # still Monday the 5th, 23:59
    (datetime(2026, 10, 10, 3, 59, tzinfo=timezone.utc), 'READER_WINDOW'),    # still Friday the 9th, 23:59
])
def test_days_outside_the_code_sessions_are_refused_before_any_setting_is_read(calendar, now, code):
    status, notices, children, _ = run_day(calendar, now, settings=forbidden)
    assert (status, codes(notices), children) == (78, [('REFUSED', None, code)], [])
    assert notices[0]['restart_allowed'] is False
    assert SESSIONS == ('2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09')


def test_a_listed_day_that_the_exchange_calendar_does_not_open_is_refused(calendar):
    saturday = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
    status, notices, children, _ = run_day(calendar, saturday, settings=forbidden, sessions=('2026-10-10',))
    assert (status, codes(notices), children) == (78, [('REFUSED', None, 'READER_SESSION')], [])


@pytest.mark.parametrize('now,accepted', [
    (OPEN - timedelta(hours=6, seconds=1), False), (OPEN - timedelta(hours=6), True),
    (CLOSE + timedelta(minutes=20, seconds=-1), True), (CLOSE + timedelta(minutes=20), False)])
def test_the_window_is_open_minus_six_hours_to_close_plus_twenty_minutes(calendar, now, accepted):
    if not accepted:
        status, notices, children, _ = run_day(calendar, now, settings=forbidden)
        assert (status, codes(notices), children) == (78, [('REFUSED', None, 'READER_WINDOW')], [])
        return
    status, notices, children, _ = run_day(calendar, now, ready_at=OPEN)
    assert status == 0 and notices[-1]['reason'] == 'END_OF_DAY' and children


@pytest.mark.parametrize('changes,code', [
    ({'r2d2_v2_shadow_enabled': False}, 'READER_DISABLED'),
    ({'r2d2_v2_massive_bars_enabled': False}, 'READER_DISABLED'),
    ({'r2d2_v2_massive_journal_dir': 'relative/journal'}, 'READER_JOURNAL_DIR')])
def test_flags_off_or_a_relative_journal_directory_refuse_without_a_child(calendar, changes, code):
    status, notices, children, _ = run_day(calendar, OPEN - timedelta(hours=5), settings=lambda: enabled(**changes))
    assert (status, codes(notices), children) == (78, [('REFUSED', None, code)], [])


def test_settings_that_do_not_load_are_a_terminal_refusal_and_their_text_is_never_printed(calendar):
    def broken():
        raise ValueError(PRIVATE_URL)
    status, notices, children, _ = run_day(calendar, OPEN - timedelta(hours=5), settings=broken)
    assert (status, codes(notices), children) == (78, [('REFUSED', None, 'READER_SETTINGS_INVALID')], [])
    with pytest.raises(Exception):
        Settings(r2d2_v2_shadow_poll_seconds=99)    # the real class does refuse an out-of-range pin


def test_the_optional_self_pin_refuses_other_launcher_bytes(calendar):
    start = OPEN - timedelta(hours=5)
    status, notices, children, _ = run_day(calendar, start, pin='d' * 64, sha='e' * 64, settings=forbidden)
    assert (status, codes(notices), children) == (78, [('REFUSED', None, 'READER_LAUNCHER_PIN')], [])
    status, notices, _, _ = run_day(calendar, start, pin='d' * 64, sha=None, settings=forbidden)
    assert (status, codes(notices)) == (78, [('REFUSED', None, 'READER_LAUNCHER_PIN')])
    status, notices, _, _ = run_day(calendar, start, pin='d' * 64, sha='d' * 64, ready_at=OPEN)
    assert status == 0 and notices[0]['launcher_pinned'] is True and notices[0]['launcher_sha256'] == 'd' * 64
    status, notices, _, _ = run_day(calendar, start, pin='', sha='d' * 64, ready_at=OPEN)
    assert status == 0 and notices[0]['launcher_pinned'] is False


# ---------------------------------------------------------------- phases

def test_one_day_pre_open_handover_ready_wait_session_end_of_day(calendar):
    start = OPEN - timedelta(hours=5, minutes=30)          # 04:00 New York, the first timer line
    ready_at = OPEN - timedelta(seconds=55)                # 09:29:05, after the producer's 09:29:00 start
    status, notices, children, clock = run_day(calendar, start, ready_at=ready_at)
    assert status == 0
    assert codes(notices) == [('STARTING', 'PRE_OPEN', None), ('HANDOVER', None, None), ('READY_OBSERVED', None, None),
                              ('STARTING', 'SESSION', None), ('STOPPED', 'SESSION', 'END_OF_DAY')]
    pre_open, session = children
    assert (pre_open.phase, pre_open.spawned_at, pre_open.ended_at) == ('PRE_OPEN', start, OPEN - timedelta(seconds=90))
    # Nothing polls the catalog from 09:28:30 until one second after the marker.
    assert (session.phase, session.spawned_at) == ('SESSION', ready_at + timedelta(seconds=1))
    assert session.ended_at == CLOSE + timedelta(minutes=20) == clock.now
    assert pre_open.stops == session.stops == 1
    assert notices[0]['until'] == (OPEN - timedelta(seconds=90)).isoformat()
    assert notices[3]['until'] == (CLOSE + timedelta(minutes=20)).isoformat()
    assert notices[1]['child_signal'] == 'SIGTERM' and notices[1]['killed'] is False and notices[1]['child_exit'] is None
    assert notices[2]['waited_seconds'] == 35.0
    pins = {key: notices[0][key] for key in ('build_sha', 'release_sha', 'capacity_required', 'capacity_config_sha',
                                             'launcher_sha256', 'launcher_pinned')}
    assert pins == {'build_sha': 'a' * 40, 'release_sha': 'b' * 64, 'capacity_required': True,
                    'capacity_config_sha': 'c' * 64, 'launcher_sha256': None, 'launcher_pinned': False}
    assert all(item['session'] == '2026-10-05' and utc(item['at']) for item in notices)


def test_without_the_marker_the_session_child_starts_one_second_after_open_minus_ten_seconds(calendar):
    status, notices, children, _ = run_day(calendar, OPEN - timedelta(hours=1))
    assert status == 0 and [item['status'] for item in notices][1:3] == ['HANDOVER', 'READY_NOT_OBSERVED']
    assert children[1].spawned_at == OPEN - timedelta(seconds=9)
    assert notices[2]['waited_seconds'] == 80.0


def test_a_start_at_the_second_timer_line_has_no_pre_open_phase_and_waits_for_the_marker(calendar):
    start = OPEN - timedelta(seconds=40)                   # 09:29:20
    status, notices, children, _ = run_day(calendar, start, ready_at=OPEN - timedelta(seconds=20))
    assert status == 0 and codes(notices)[:2] == [('READY_OBSERVED', None, None), ('STARTING', 'SESSION', None)]
    assert [child.phase for child in children] == ['SESSION']
    assert children[0].spawned_at == OPEN - timedelta(seconds=19)


def test_a_restart_during_the_session_looks_once_and_starts_after_the_settle_second(calendar):
    start = OPEN + timedelta(hours=2)
    for ready_at, expected in ((OPEN, 'READY_OBSERVED'), (None, 'READY_NOT_OBSERVED')):
        status, notices, children, _ = run_day(calendar, start, ready_at=ready_at)
        assert status == 0 and notices[0]['status'] == expected and notices[0]['waited_seconds'] == 0.0
        assert [child.spawned_at for child in children] == [start + timedelta(seconds=1)]


def test_the_real_marker_check_is_a_stat_and_takes_no_lock(tmp_path):
    root = tmp_path.resolve() / 'journal'; root.mkdir(mode=0o700)
    journals = SessionJournalRoot(root, EPOCH, create=True)
    assert launcher.ready_marker(str(root), '2026-10-05') is False
    journals.prepare_session('2026-10-05', ['SYNTH'])
    assert launcher.ready_marker(str(root), '2026-10-05') is False
    with journal_access(root, exclusive=True):
        # The producer holds the exclusive catalog lock here; the look neither waits nor fails.
        assert launcher.ready_marker(str(root), '2026-10-05') is False
    journals.ensure_session('2026-10-05', ['SYNTH'])       # the producer's own path to the ready marker
    assert launcher.ready_marker(str(root), '2026-10-05') is True
    assert launcher.ready_marker(str(root), '2026-10-06') is False
    (root / 'session_date=2026-10-05' / 'ready.json').unlink()
    (root / 'session_date=2026-10-05' / 'ready.json').symlink_to(root / 'epoch.json')
    assert launcher.ready_marker(str(root), '2026-10-05') is False
    source = SCRIPT.read_text()
    assert 'flock' not in source and 'journal_access' not in source and 'sqlite' not in source


# ---------------------------------------------------------------- stop requests

@pytest.mark.parametrize('start,stop_after,phase,spawned', [
    (OPEN - timedelta(hours=5), timedelta(0), 'START', 0),
    (OPEN - timedelta(hours=5), timedelta(seconds=100), 'PRE_OPEN', 1),
    (OPEN - timedelta(seconds=60), timedelta(seconds=30), 'READY_WAIT', 0),
    (OPEN - timedelta(seconds=9, milliseconds=500), timedelta(milliseconds=500), 'READY_WAIT', 0),
    (OPEN + timedelta(hours=1), timedelta(minutes=10), 'SESSION', 1)])
def test_a_stop_request_ends_the_child_and_exits_zero_in_every_phase(calendar, start, stop_after, phase, spawned):
    status, notices, children, clock = run_day(calendar, start, stop_at=start + stop_after)
    assert status == 0 and codes(notices)[-1] == ('STOPPED', phase, 'SIGNAL')
    assert len(children) == spawned and all(child.stops == 1 for child in children)
    assert clock.now - (start + stop_after) <= timedelta(seconds=1)
    if spawned:
        assert notices[-1]['child_signal'] == 'SIGTERM' and notices[-1]['status_lines'] == 3


def test_a_stop_request_exits_zero_even_when_the_child_had_already_failed(calendar):
    start = OPEN - timedelta(hours=5)
    plans = {'PRE_OPEN': {'stop': (1, False, False)}}
    status, notices, _, _ = run_day(calendar, start, stop_at=start + timedelta(seconds=5), plans=plans)
    assert status == 0 and codes(notices)[-1] == ('STOPPED', 'PRE_OPEN', 'SIGNAL') and notices[-1]['child_exit'] == 1


# ---------------------------------------------------------------- the child's own exit

@pytest.mark.parametrize('phase,start', [('PRE_OPEN', OPEN - timedelta(hours=5)), ('SESSION', OPEN + timedelta(hours=1))])
def test_a_child_that_exits_zero_by_itself_printed_off_and_is_a_terminal_refusal(calendar, phase, start):
    plans = {phase: {'exit_at': start + timedelta(seconds=10), 'exit_code': 0}}
    status, notices, children, _ = run_day(calendar, start, plans=plans, ready_at=OPEN)
    assert status == 78 and codes(notices)[-1] == ('REFUSED', phase, 'READER_DISABLED')
    assert len(children) == 1 and children[0].stops == 0 and notices[-1]['restart_allowed'] is False


@pytest.mark.parametrize('phase,start', [('PRE_OPEN', OPEN - timedelta(hours=5)), ('SESSION', OPEN + timedelta(hours=1))])
def test_any_other_exit_of_the_child_is_one_failed_notice_and_exit_one(calendar, phase, start):
    failure = {'error': 'ShadowIntegrityError', 'code': 'RELEASE_CHANGED'}
    plans = {phase: {'exit_at': start + timedelta(seconds=10), 'exit_code': 1, 'failure': failure}}
    status, notices, children, _ = run_day(calendar, start, plans=plans, ready_at=OPEN)
    failed = [item for item in notices if item['status'] == 'FAILED']
    assert status == 1 and len(failed) == 1 and notices[-1] is failed[0] and len(children) == 1
    assert {key: failed[0][key] for key in ('phase', 'child_exit', 'child_signal', 'error', 'code', 'restart_allowed')} == {
        'phase': phase, 'child_exit': 1, 'child_signal': None, 'error': 'ShadowIntegrityError',
        'code': 'RELEASE_CHANGED', 'restart_allowed': True}


def test_a_child_killed_from_outside_is_a_failure_that_names_the_signal(calendar):
    start = OPEN + timedelta(hours=1)
    plans = {'SESSION': {'exit_at': start + timedelta(minutes=3), 'exit_code': -signal.SIGKILL}}
    status, notices, _, _ = run_day(calendar, start, plans=plans, ready_at=OPEN)
    assert status == 1 and notices[-1]['status'] == 'FAILED'
    assert (notices[-1]['child_exit'], notices[-1]['child_signal']) == (None, 'SIGKILL') and 'error' not in notices[-1]


@pytest.mark.parametrize('own,status,last', [((1, False, False), 1, 'FAILED'), ((0, False, False), 78, 'REFUSED')])
def test_a_child_that_ended_by_itself_at_the_phase_end_is_not_taken_for_a_normal_end(calendar, own, status, last):
    actual, notices, children, _ = run_day(calendar, OPEN - timedelta(hours=1), plans={'PRE_OPEN': {'stop': own}})
    assert actual == status and notices[-1]['status'] == last and len(children) == 1
    actual, notices, children, _ = run_day(calendar, OPEN + timedelta(hours=1), plans={'SESSION': {'stop': own}}, ready_at=OPEN)
    assert actual == status and notices[-1]['status'] == last and 'END_OF_DAY' not in json.dumps(notices)


def test_a_child_that_needed_the_kill_at_the_handover_is_reported_and_the_day_goes_on(calendar):
    plans = {'PRE_OPEN': {'stop': (-signal.SIGKILL, True, True)}}
    status, notices, children, _ = run_day(calendar, OPEN - timedelta(hours=1), plans=plans, ready_at=OPEN - timedelta(seconds=30))
    assert status == 0 and [child.phase for child in children] == ['PRE_OPEN', 'SESSION']
    assert (notices[1]['status'], notices[1]['child_signal'], notices[1]['killed']) == ('HANDOVER', 'SIGKILL', True)


def test_the_phase_constants_are_the_ones_of_the_plan():
    assert (launcher.PRE_OPEN_SECONDS, launcher.HANDOVER_BEFORE_OPEN_SECONDS, launcher.READY_DEADLINE_BEFORE_OPEN_SECONDS,
            launcher.READY_SETTLE_SECONDS, launcher.STOP_AFTER_CLOSE_SECONDS, launcher.CHILD_TERM_GRACE_SECONDS,
            launcher.TERMINAL_EXIT) == (21600, 90, 10, 1.0, 1200, 20.0, 78)
    # The child's grace must end before `docker stop -t 25` kills the container.
    assert launcher.CHILD_TERM_GRACE_SECONDS + launcher.TICK_SECONDS + launcher.DRAIN_JOIN_SECONDS < 25
    assert launcher.worker_argv() == [sys.executable, '-B', '-m', 'app.r2d2_v2_shadow_worker']
    assert load().APP_ROOT == str(BACKEND) and "APP_ROOT = '/app'\n" in SCRIPT.read_text()


# ---------------------------------------------------------------- signal handlers

def test_signal_handlers_only_set_a_flag():
    tree = ast.parse(SCRIPT.read_text())
    registered = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                  and ast.unparse(node.func) == 'signal.signal']
    assert len(registered) == 1 and ast.unparse(registered[0].args[1]) == '_request_stop'
    owner = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'install_signal_handlers')
    assert registered[0] in list(ast.walk(owner))
    loop = next(node for node in owner.body if isinstance(node, ast.For))
    assert ast.unparse(loop.iter) == '(signal.SIGTERM, signal.SIGINT)'
    handler = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_request_stop')
    assert [ast.unparse(statement) for statement in handler.body] == ['_Stop.requested = True']
    # Nothing else in the file touches signal delivery, raises from a handler or writes the flag.
    names = {ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Attribute)
             and isinstance(node.value, ast.Name) and node.value.id == 'signal'}
    assert names == {'signal.signal', 'signal.SIGTERM', 'signal.SIGINT', 'signal.SIGKILL', 'signal.Signals'}
    writes = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
              and 'requested' in ast.unparse(node).split('=')[0]]
    assert [ast.unparse(node) for node in writes] == ['requested = False', '_Stop.requested = True']
    assert not any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def test_the_script_imports_nothing_of_the_application_when_it_is_loaded():
    tree = ast.parse(SCRIPT.read_text())
    top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    modules = {alias.name for node in top if isinstance(node, ast.Import) for alias in node.names} | {
        node.module for node in top if isinstance(node, ast.ImportFrom)}
    assert modules <= set(sys.stdlib_module_names) and not any(name.startswith('app') for name in modules)
    packaged = sorted({node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module.startswith('app')})
    assert packaged == ['app.config', 'app.r2d2_v2_calendar', 'app.r2d2_v2_epoch_assembler']
    # The worker is never imported into this process: it is only named as the child's module.
    assert 'app.r2d2_v2_shadow_worker' not in packaged and "WORKER_MODULE = 'app.r2d2_v2_shadow_worker'" in SCRIPT.read_text()


# ---------------------------------------------------------------- the output filter

def worker_line(result):
    """The line the worker logs for one cycle result (app/r2d2_v2_shadow_worker.py, the loop of main)."""
    public = {key: value for key, value in json.loads(json.dumps(result)).items() if key not in {'last_cycle_at', 'observed_at'}}
    for session in public['sessions']:
        session.pop('snapshot_attempts', None)
    record = logging.LogRecord('__main__', logging.INFO, __file__, 1, 'V2 status %s', (json.dumps(public, sort_keys=True),), None)
    return logging.Formatter(logging.BASIC_FORMAT).format(record)


TRACEBACK = '''Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "/app/app/r2d2_v2_shadow_worker.py", line 157, in main
    recheck_release(settings, collector)
    ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/r2d2_v2_shadow_worker.py", line 52, in recheck_release
    raise ShadowIntegrityError("RELEASE_CHANGED")
app.r2d2_v2_store.ShadowIntegrityError: RELEASE_CHANGED'''

HOSTILE = [
    'AAPL', 'US:AAPL', 'BRK.B 412.10', 'INFO:__main__:AAPL bought', 'WARNING:root:quote for MSFT is stale',
    PRIVATE_URL, 'psycopg.OperationalError: connection to server at "db" failed: password authentication failed',
    '{"status":"OFF","collection":false}', '{"schema":"R2D2_V2_COLLECTOR_STATUS_V2"}', 'V2 status {}',
    'INFO:app.r2d2_v2_shadow_worker:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2"}',
    ' INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2"}',
    'INFO:__main__:V2 status', 'INFO:__main__:V2 status not json', 'INFO:__main__:V2 status []',
    'INFO:__main__:V2 status {"schema":"OTHER_SCHEMA_V1"}', 'INFO:__main__:V2 status {}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","symbol":"AAPL"}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","sessions":[{"universe":["US:AAPL"]}]}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","sessions":[{"reason_counts":{"MSFT":1}}]}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","names":["BRK.B","BF-B","X","7203"]}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","note":"aapl"}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","path":"/app/day-d-data/release.json"}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","url":"' + PRIVATE_URL + '"}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","Free Text":1}',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2"} AAPL',
    'INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","deep":' + '[' * 3000 + ']' * 3000 + '}',
]


def test_the_filter_forwards_no_line_that_is_not_a_worker_status_line():
    filtered = launcher.OutputFilter()
    lines = TRACEBACK.splitlines() + HOSTILE
    assert [filtered.feed(line) for line in lines] == [None] * len(lines)
    counts = filtered.counts()
    assert counts['status_lines'] == 0 and counts['status_withheld'] + counts['dropped_lines'] == len(lines)
    assert counts['status_withheld'] == sum(line.startswith('INFO:__main__:V2 status ') for line in lines)


def test_the_filter_forwards_real_status_lines_verbatim(calendar):
    collector, store, loader = capacity_collector(calendar)
    lines = [worker_line(collector.cycle(OPEN - timedelta(hours=5))), worker_line(collector.cycle(OPEN)),
             worker_line(collector.cycle(CLOSE + timedelta(minutes=5)))]
    assert lines[0] != lines[1] != lines[2] and '2026-10-05' in lines[1]
    filtered = launcher.OutputFilter()
    assert [filtered.feed(line) for line in lines] == lines
    assert filtered.counts() == {'status_lines': 3, 'status_withheld': 0, 'dropped_lines': 0}
    assert lines[0].startswith(launcher.STATUS_PREFIX) and launcher.STATUS_SCHEMA in lines[0]
    worker = (BACKEND / 'app' / 'r2d2_v2_shadow_worker.py').read_text()
    assert all(text in worker for text in ('logger = logging.getLogger(__name__)', 'logging.basicConfig(level=logging.INFO)',
        'logger.info("V2 status %s", json.dumps(public, sort_keys=True))', 'print(\'{"status":"OFF","collection":false}\')'))


@pytest.mark.parametrize('text,expected', [
    (TRACEBACK, {'error': 'ShadowIntegrityError', 'code': 'RELEASE_CHANGED'}),
    ('Traceback (most recent call last):\n  File "x", line 1\napp.r2d2_v2_sources.SourceUnavailable: MASSIVE_SESSION_ROOT_UNVERIFIED',
     {'error': 'SourceUnavailable', 'code': 'MASSIVE_SESSION_ROOT_UNVERIFIED'}),
    # A code is copied only for the two classes whose text is a constant, and only with an underscore.
    ('Traceback (most recent call last):\n  File "x", line 1\napp.r2d2_v2_store.ShadowIntegrityError: AAPL', {'error': 'ShadowIntegrityError'}),
    ('Traceback (most recent call last):\n  File "x", line 1\nValueError: RELEASE_CHANGED', {'error': 'ValueError'}),
    ('Traceback (most recent call last):\n  File "x", line 1\nKeyError: \'AAPL\'', {'error': 'KeyError'}),
    ("Traceback (most recent call last):\n  File \"x\", line 1\nPermissionError: [Errno 13] Permission denied: '/app/day-d-data/private'",
     {'error': 'PermissionError', 'errno': 'EACCES'}),
    ('Traceback (most recent call last):\n  File "x", line 1\npsycopg.OperationalError: connection failed: ' + PRIVATE_URL, {'error': 'OperationalError'}),
    ('Traceback (most recent call last):\n  File "x", line 1\nMemoryError', {'error': 'MemoryError'}),
    # The exception that ended the process is the last one of a chain.
    (TRACEBACK + '\n\nDuring handling of the above exception, another exception occurred:\n\n'
     'Traceback (most recent call last):\n  File "x", line 2\nOSError: [Errno 28] No space left on device',
     {'error': 'OSError', 'errno': 'ENOSPC'}),
    ('ShadowIntegrityError: RELEASE_CHANGED', {}),              # no traceback header before it
    ('Traceback (most recent call last):\n  File "x", line 1\n2026-10-05 not a class line: AAPL', {}),
])
def test_the_failure_notice_takes_the_class_name_and_a_constant_code_never_the_text(text, expected):
    filtered = launcher.OutputFilter()
    assert [filtered.feed(line) for line in text.splitlines()] == [None] * len(text.splitlines())
    assert filtered.failure() == expected
    assert 'NEVERPRINTED' not in json.dumps(filtered.failure()) and '/app' not in json.dumps(filtered.failure())


# ---------------------------------------------------------------- real child processes

def wait_for(path, process):
    deadline = time.monotonic() + CEILING_SECONDS
    while not path.exists() or not path.read_text():
        assert process.poll() is None, 'the process ended before it reported'
        assert time.monotonic() < deadline, 'the process never reported'
        time.sleep(0.02)
    return path.read_text()


HOLD_SHARED_LOCK = textwrap.dedent('''
    import signal, sys, time
    from pathlib import Path
    from app.r2d2_v2_massive_maintenance import journal_access
    if sys.argv[3] == 'ignore':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with journal_access(Path(sys.argv[1])):
        Path(sys.argv[2]).write_text('held')
        time.sleep(600)
''')


@pytest.mark.parametrize('disposition,grace,expected', [
    ('default', 20.0, (-signal.SIGTERM, True, False)), ('ignore', 0.5, (-signal.SIGKILL, True, True))])
def test_a_real_child_holding_the_catalog_shared_lock_is_stopped_and_the_exclusive_lock_is_free_at_once(
        tmp_path, disposition, grace, expected):
    root = tmp_path.resolve() / 'journal'; root.mkdir(mode=0o700)
    SessionJournalRoot(root, EPOCH, create=True)
    flag = tmp_path / 'held'; forwarded = []
    child = launcher.WorkerChild([sys.executable, '-B', '-c', HOLD_SHARED_LOCK, str(root), str(flag), disposition],
                                 cwd=str(BACKEND), forward=forwarded.append)
    try:
        wait_for(flag, child)
        # The real reader lock: while the child lives, the producer's exclusive request is refused.
        with pytest.raises(SourceUnavailable, match='^MASSIVE_MAINTENANCE_BUSY$'):
            with journal_access(root, exclusive=True):
                pass
        assert child.poll() is None
        began = time.monotonic()
        assert child.stop(grace) == expected
        # No retry and no wait: one non-blocking request, right after the child was reaped.
        with journal_access(root, exclusive=True):
            pass
        assert time.monotonic() - began < grace + 5
        SessionJournalRoot(root, EPOCH, create=True).ensure_session('2026-10-05', ['SYNTH'])
        assert child.stop() == (expected[0], False, False)        # a second stop finds it gone
    finally:
        child.close()
    assert forwarded == [] and sorted(entry.name for entry in root.iterdir())[:2] == ['epoch.json', 'maintenance.lock']


NOISY_CHILD = textwrap.dedent('''
    import sys
    status = sys.argv[1]
    print('{"status":"OFF","collection":false}', flush=True)
    print('WARNING:root:quote for AAPL is stale', file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status ' + status, file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status ' + status.replace('"CERTIFIED"', '"AAPL"'), file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status ' + status.replace('"CERTIFIED"', '"MSFT"'), file=sys.stderr, flush=True)
    sys.stderr.write('x' * (2 * 1024 * 1024) + ' AAPL\\n')
    sys.stderr.buffer.write(b'\\xff\\xfe not text AAPL\\n')
    sys.stderr.flush()
    raise RuntimeError('NEVERPRINTED US:AAPL /app/day-d-data/private')
''')


def test_a_real_child_reaches_the_journal_only_through_the_filter(calendar):
    collector, _, _ = capacity_collector(calendar)
    line = worker_line(collector.cycle(OPEN))
    forwarded = []; withheld = []
    child = launcher.WorkerChild([sys.executable, '-B', '-c', NOISY_CHILD, line[len(launcher.STATUS_PREFIX):]],
                                 cwd=str(BACKEND), forward=forwarded.append, on_withheld=lambda: withheld.append(1))
    deadline = time.monotonic() + CEILING_SECONDS
    while child.poll() is None:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    child.close()
    assert child.poll() == 1 and forwarded == [line] and withheld == [1]
    assert child.failure() == {'error': 'RuntimeError'}
    counts = child.counts()
    assert (counts['status_lines'], counts['status_withheld']) == (1, 2) and counts['dropped_lines'] >= 6


def test_an_output_failure_in_this_process_does_not_stop_the_drain_of_the_child():
    def broken(_line):
        raise OSError('standard error is gone')
    program = "import sys\nfor _ in range(4000): print('INFO:__main__:V2 status {\"schema\":\"R2D2_V2_COLLECTOR_STATUS_V2\"}', file=sys.stderr)\n"
    child = launcher.WorkerChild([sys.executable, '-B', '-c', program], cwd=str(BACKEND), forward=broken)
    deadline = time.monotonic() + CEILING_SECONDS
    while child.poll() is None:      # a stalled drain would leave the child blocked on a full pipe
        assert time.monotonic() < deadline
        time.sleep(0.02)
    child.close()
    assert child.poll() == 0 and child.counts()['status_lines'] == 4000


def test_the_real_worker_module_as_a_child_with_collection_off_ends_in_78(calendar, monkeypatch):
    for name in ('C3PO_R2D2_V2_SHADOW_ENABLED', 'C3PO_R2D2_V2_MASSIVE_BARS_ENABLED'):
        monkeypatch.delenv(name, raising=False)
    frozen = OPEN - timedelta(hours=5); notices = []; forwarded = []; children = []
    began = time.monotonic()

    def spawn(phase):
        children.append(launcher.WorkerChild(launcher.worker_argv(), cwd=launcher.APP_ROOT, forward=forwarded.append))
        return children[-1]

    def sleep(seconds):
        assert time.monotonic() - began < CEILING_SECONDS, 'the worker child never ended'
        time.sleep(seconds)

    # The launcher's own settings say enabled; the child reads the environment, where collection is off.
    status = launcher.supervise(utcnow=lambda: frozen, sleep=sleep, notice=notices.append, spawn=spawn,
        calendar=calendar, sessions=SESSIONS, settings=enabled, stop_requested=lambda: False)
    assert status == 78 and codes(notices) == [('STARTING', 'PRE_OPEN', None), ('REFUSED', 'PRE_OPEN', 'READER_DISABLED')]
    assert len(children) == 1 and children[0].poll() == 0 and forwarded == []
    assert children[0].process.args == [sys.executable, '-B', '-m', 'app.r2d2_v2_shadow_worker']
    # Its only output was the OFF line, on standard output, which the filter dropped.
    counts = children[0].counts()
    assert (counts['status_lines'], counts['status_withheld']) == (0, 0) and counts['dropped_lines'] >= 1


DRIVER = textwrap.dedent('''
    import importlib.util, sys
    from datetime import datetime, timezone
    spec = importlib.util.spec_from_file_location('c3po_reader_launcher', sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.APP_ROOT = sys.argv[2]
    frozen = datetime.fromisoformat(sys.argv[3]) if sys.argv[3] else None
    child = [sys.executable, '-B', '-c', sys.argv[4], sys.argv[5]] if sys.argv[4] else None
    raise SystemExit(module.main([], utcnow=(lambda: frozen) if frozen else None, child_argv=child))
''')

SLEEPING_CHILD = textwrap.dedent('''
    import os, sys, time
    from pathlib import Path
    print('Traceback (most recent call last):', file=sys.stderr)
    print('ValueError: US:AAPL NEVERPRINTED', file=sys.stderr)
    print('INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","mode":"CERTIFIED"}', file=sys.stderr, flush=True)
    Path(sys.argv[1]).write_text(str(os.getpid()))
    time.sleep(600)
''')


def reader_environment(tmp_path, **changes):
    keep = {key: value for key, value in os.environ.items() if not key.startswith(('C3PO_', 'PYTHON'))}
    return {**keep, 'C3PO_DATABASE_URL': '', 'C3PO_R2D2_V2_SHADOW_ENABLED': 'true',
            'C3PO_R2D2_V2_MASSIVE_BARS_ENABLED': 'true', 'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR': str(tmp_path / 'journal'),
            'C3PO_BUILD_SHA': 'a' * 40, **changes}


def test_sigterm_to_the_real_parent_is_forwarded_and_the_parent_exits_zero(tmp_path):
    """Real process, real handler, real packaged calendar and settings; only the clock is frozen at 04:00
    New York of the first session and the child is a sleeping program instead of the worker."""
    pidfile = tmp_path / 'child.pid'
    frozen = (OPEN - timedelta(hours=5, minutes=30)).isoformat()
    parent = subprocess.Popen([sys.executable, '-I', '-B', '-c', DRIVER, str(SCRIPT), str(BACKEND), frozen,
        SLEEPING_CHILD, str(pidfile)], cwd=str(tmp_path), env=reader_environment(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    child_pid = None
    try:
        child_pid = int(wait_for(pidfile, parent))
        os.kill(child_pid, 0)                                  # the child is running
        time.sleep(0.5)                                        # past at least one tick of the parent's loop
        assert parent.poll() is None
        parent.send_signal(signal.SIGTERM)
        out, err = parent.communicate(timeout=CEILING_SECONDS)
    finally:
        if parent.poll() is None:
            parent.kill(); parent.communicate()
            if child_pid is not None:
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
    assert parent.returncode == 0
    notices = [json.loads(line) for line in out.splitlines()]
    assert codes(notices) == [('STARTING', 'PRE_OPEN', None), ('STOPPED', 'PRE_OPEN', 'SIGNAL')]
    assert (notices[1]['child_signal'], notices[1]['killed'], notices[1]['status_lines'], notices[1]['dropped_lines']) == (
        'SIGTERM', False, 1, 2)
    assert notices[0]['build_sha'] == 'a' * 40 and notices[0]['session'] == '2026-10-05'
    assert len(notices[0]['launcher_sha256']) == 64
    # Standard error carries the status line and nothing else of what the child printed.
    assert err.splitlines() == ['INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","mode":"CERTIFIED"}']
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)                                  # reaped by the parent: the pid is gone


def test_the_real_parent_under_isolated_mode_refuses_today_with_one_line(tmp_path):
    """`python -I` with the real clock: the application is found only through APP_ROOT. Whatever the day
    this runs, the end is 78: outside the epoch's days, outside the window, or with the flags off."""
    environment = reader_environment(tmp_path, C3PO_R2D2_V2_SHADOW_ENABLED='false')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', DRIVER, str(SCRIPT), str(BACKEND), '', '', ''],
        cwd=str(tmp_path), env=environment, capture_output=True, text=True, timeout=CEILING_SECONDS)
    assert result.returncode == 78 and result.stderr == ''
    notice, = [json.loads(line) for line in result.stdout.splitlines()]
    assert notice['status'] == 'REFUSED' and notice['restart_allowed'] is False
    assert notice['code'] in {'READER_SESSION', 'READER_WINDOW', 'READER_DISABLED'}


def test_the_unit_command_form_finds_the_application_only_at_the_application_root(tmp_path):
    """`python -I -B <script>` exactly as the unit runs it, from the backend directory. Isolated mode keeps
    the working directory off the import path, so on a machine without /app the import fails and the notice
    carries the class name only; inside the image the same command ends in a refusal."""
    result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], cwd=str(BACKEND),
        env=reader_environment(tmp_path, C3PO_R2D2_V2_SHADOW_ENABLED='false'),
        capture_output=True, text=True, timeout=CEILING_SECONDS)
    notice, = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.stderr == ''
    if Path('/app/app/r2d2_v2_shadow_worker.py').exists():
        assert result.returncode == 78 and notice['status'] == 'REFUSED'
    else:
        assert result.returncode == 1
        assert {key: notice[key] for key in ('status', 'phase', 'error', 'restart_allowed')} == {
            'status': 'FAILED', 'phase': 'LAUNCHER', 'error': 'ModuleNotFoundError', 'restart_allowed': True}
    result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), '--once'], cwd=str(BACKEND),
        env=reader_environment(tmp_path), capture_output=True, text=True, timeout=CEILING_SECONDS)
    assert result.returncode == 78 and json.loads(result.stdout)['code'] == 'READER_ARGUMENTS'


def test_the_launcher_reports_the_hash_of_its_own_bytes():
    import hashlib
    assert launcher.own_sha256() == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert launcher.LAUNCHER_PIN_ENV == 'C3PO_READER_LAUNCHER_SHA256'
    # An extra C3PO_ variable does not disturb the packaged settings (extra="ignore").
    assert Settings.model_config.get('extra') == 'ignore'


# ---------------------------------------------------------------- pre-open cycles and the capacity admission

class EmptySource:
    """A source with nothing to deliver; the collector, store, calendar and loader below are the real ones."""
    minute_bar_enabled = True

    def __init__(self):
        self.calls = []

    def causal_list(self, *args):
        self.calls.append('causal_list')
        raise AssertionError('the causal list is only read inside the capture window')

    def snapshot(self, now):
        raise AssertionError('no snapshot outside the capture window')

    def prepare_events(self, now, cursor, **_):
        self.calls.append('prepare_events')
        return dict(events=[], diagnostics=[], cursor=cursor, raw_receipts={}, has_more=False, page={'cutoff_received_at': None})


class RecordingLoader(CapacityLoader):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = []

    def derive(self, day, state, causal=None):
        self.calls.append(day)
        return super().derive(day, state, causal)


def capacity_collector(calendar, tmp_path=None):
    """The real CapacityBoundCollector over the real loader, with no committed binding and no delivery."""
    release = Release(EPOCH, 'CERTIFIED', date(2026, 10, 5), utc('2026-10-03T18:00:00Z'), 'a' * 40, 'b' * 64,
                      **package_pins(), ebar_amendment_sha=EBAR_AMENDMENT_SHA)
    store = MemoryShadowStore()
    if tmp_path is None:
        roots = SimpleNamespace(json=forbidden_root, verify=lambda: None)
        loader = RecordingLoader(root=roots, go_root=roots, release=release, calendar=calendar, authority=None,
                                 clock=forbidden, binding_reader=lambda day: None)
    else:
        for name in ('payload', 'go'):
            (tmp_path / name).mkdir(mode=0o700)
        loader = RecordingLoader(root=AnchoredRoot(tmp_path / 'payload'), go_root=AnchoredRoot(tmp_path / 'go'),
            release=release, calendar=calendar, authority=None, clock=forbidden, binding_reader=lambda day: None)
    return CapacityBoundCollector(store, EmptySource(), release, calendar=calendar, capacity_loader=loader), store, loader


def forbidden_root(name):
    raise FileNotFoundError(name)


def journal_types(store):
    return [record['payload'].get('type') for record in store.journal(EPOCH)]


def test_a_pre_open_cycle_with_no_committed_binding_does_not_block_the_capacity_admission(calendar, tmp_path):
    """Monday's order (reader activation at 06:15 BRT, capacity dispatch at 07:30 BRT) rests on this: the
    PRE_OPEN child cycles for hours before the day's binding is committed."""
    collector, store, loader = capacity_collector(calendar, tmp_path.resolve())
    for before in (timedelta(hours=6), timedelta(hours=3, minutes=15), timedelta(seconds=91), timedelta(seconds=90),
                   timedelta(seconds=10), timedelta(microseconds=1)):
        result = collector.cycle(OPEN - before)
        assert result['sessions'] == [] and result['cohort_clock_started'] is False
        saved = store.read(EPOCH)
        # No session of the day exists yet, so there is nothing a block could be written on.
        assert saved['state']['sessions'] == {} and 'daily_capacity' not in saved['state']
        assert 'capacity_admission_blocked' not in json.dumps(saved['state'])
    assert loader.calls == [] and journal_types(store) == [] and collector.source.calls == ['prepare_events'] * 6
    # The contrast: the first cycle at the open, still with no binding and no delivery, does block the day.
    collector.cycle(OPEN)
    state = store.read(EPOCH)['state']
    assert loader.calls == ['2026-10-05']
    assert state['sessions']['2026-10-05']['capacity_admission_blocked'] == 'CAPACITY_ADMISSION_UNAVAILABLE'
    assert 'CAPACITY_ADMISSION_BLOCKED' in journal_types(store)


def test_a_pre_open_cycle_of_a_later_day_does_not_create_or_block_that_day(calendar):
    collector, store, loader = capacity_collector(calendar)
    collector.cycle(OPEN + timedelta(hours=1))
    assert list(store.read(EPOCH)['state']['sessions']) == ['2026-10-05'] and loader.calls == ['2026-10-05']
    tuesday = calendar.details(date(2026, 10, 6))['open']
    for before in (timedelta(hours=5, minutes=30), timedelta(seconds=91), timedelta(microseconds=1)):
        collector.cycle(tuesday - before)
        assert list(store.read(EPOCH)['state']['sessions']) == ['2026-10-05']
    assert loader.calls == ['2026-10-05']
    assert journal_types(store).count('CAPACITY_ADMISSION_BLOCKED') == 1
