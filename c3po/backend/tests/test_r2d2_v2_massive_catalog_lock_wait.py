"""Catalog create and session prepare wait a bounded time for a reader poll.

Real flock contention: every holder below is a second open file description
of the same maintenance.lock, exactly what another process would hold.
"""
import contextlib
from datetime import datetime, timezone
import os
import re
import signal
import threading
import time
from types import SimpleNamespace
import pytest
from app import r2d2_v2_massive_sessions as sessions_module
from app import r2d2_v2_massive_supervisor as supervisor_module
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_sources import SourceUnavailable
from test_r2d2_v2_minute_bars import calendar
from test_r2d2_v2_massive_supervisor import EPOCH as LAYOUT_EPOCH, UNIT_ROOT, claims, container, reader

EPOCH = 'R2D2-V2-SHADOW-LOCK-WAIT-TEST'
DAY = '2026-10-05'
NEXT = '2026-10-06'
NOW = datetime(2026, 10, 6, 15, tzinfo=timezone.utc)
BUSY = '^MASSIVE_MAINTENANCE_BUSY$'
# No wait in this file lasts longer than this. A wait that never ends must fail its test, not hang it.
WAIT_CEILING_SECONDS = 5.0
# That ceiling sits inside the patched sleep, so it only sees code that still sleeps. This one covers a whole
# test on the wall clock and needs nothing from the code under test: unmutated, the file takes a few seconds in all.
TEST_WALL_SECONDS = 20.0
# The alarm raises a failure into the test, and a loop that catches BaseException swallows it. If the same test is
# still running this long after the failure was raised, the alarm fires again and ends the process with this status.
HARD_EXIT_GRACE_SECONDS = 5.0
HARD_EXIT_STATUS = 70
# Accepted bound: the worst case is about TEST_WALL_SECONDS (20 s) per spinning test, because each one runs up to
# the alarm before it fails. One that also swallows the failure ends the whole run HARD_EXIT_GRACE_SECONDS later.
# Clock reads and attempts allowed on the fake clock, where nothing blocks (13 reads and 5 attempts at most unmutated).
FAKE_CLOCK_CEILING = 64


def _hard_exit(config, line):
    """End the process with HARD_EXIT_STATUS. os._exit raises nothing, so there is nothing for the code under
    test to catch. One line is written to stderr first, where that can be done."""
    try:
        try:
            capture = config.pluginmanager.getplugin('capturemanager')
            if capture is not None:
                capture.suspend_global_capture(in_=False)  # until then fd 2 is pytest's capture file
        finally:
            os.write(2, line.encode())
    finally:
        os._exit(HARD_EXIT_STATUS)


@contextlib.contextmanager
def _ceiling(config, name):
    """Arm the wall-clock alarm; on the way out put back the handler and the timer that were there.

    The first firing fails the test. A second firing while the same test is still running ends the process:
    the failure was swallowed, or the test took longer than the grace to unwind. Yields False, unarmed, where
    SIGALRM cannot be used: no SIGALRM or setitimer, another thread than the main one, or a current handler
    that was not installed from Python and so could not be put back."""
    if not (hasattr(signal, 'SIGALRM') and hasattr(signal, 'setitimer')
            and threading.current_thread() is threading.main_thread()
            and signal.getsignal(signal.SIGALRM) is not None):
        yield False
        return
    fired = []
    def expired(signum, frame):
        fired.append(1)
        if len(fired) > 1:
            _hard_exit(config, '%s: still running %.0f s after its wall-clock failure was raised, exit status %d\n'
                       % (name, HARD_EXIT_GRACE_SECONDS, HARD_EXIT_STATUS))
        pytest.fail('test still running after %.0f s on the wall clock' % TEST_WALL_SECONDS)
    began = time.monotonic()
    # The timer first: from here until the handler is in place no alarm is due for TEST_WALL_SECONDS.
    found = signal.setitimer(signal.ITIMER_REAL, TEST_WALL_SECONDS, HARD_EXIT_GRACE_SECONDS)
    previous = unset = object()
    try:
        previous = signal.signal(signal.SIGALRM, expired)
        yield True
    finally:
        try:
            if previous is not unset:
                signal.signal(signal.SIGALRM, signal.SIG_IGN)  # a firing from here on is dropped, not raised
        finally:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                try:
                    if previous is not unset:
                        signal.signal(signal.SIGALRM, previous)
                finally:
                    if found[0] > 0:
                        # A timer that was already armed runs on, less the time spent here; one that came
                        # due meanwhile fires at once.
                        left = max(found[0] - (time.monotonic() - began), 0.001)
                        signal.setitimer(signal.ITIMER_REAL, left, found[1])


@pytest.fixture(autouse=True)
def wall_clock_ceiling(request):
    """Fail any test of this file that is still running after TEST_WALL_SECONDS.

    A retry loop with neither a deadline nor a sleep never reaches the patched sleep; the alarm
    interrupts it all the same. Yields False, unarmed, where SIGALRM cannot be used (see _ceiling)."""
    with _ceiling(request.config, request.node.nodeid) as armed:
        yield armed


def root(tmp_path):
    return SessionJournalRoot(tmp_path, EPOCH, create=True)


def reader_poll(path, finished):
    """A consumer poll in progress: the shared lock held on its own description."""
    held = threading.Event()
    def poll():
        with journal_access(path):
            held.set(); finished.wait(5)
    thread = threading.Thread(target=poll); thread.start()
    assert held.wait(5)
    return thread


def recorded_sleeps(monkeypatch, finished=None):
    """Every sleep of the catalog module, still slept for real on the real clock.

    With a poll in progress, the poll finishes only after the third refused
    attempt, so the wait is observed without depending on scheduling.
    A sleep that comes WAIT_CEILING_SECONDS after the first one fails the test:
    an unbounded wait is a failure here, never a hang."""
    waited = []; began = []
    def sleep(seconds):
        began.append(time.monotonic())
        if began[-1] - began[0] >= WAIT_CEILING_SECONDS:
            pytest.fail('catalog lock wait still sleeping %.1f s after its first sleep' % (began[-1] - began[0]))
        waited.append(seconds); time.sleep(seconds)
        if finished is not None and len(waited) == 3:
            finished.set()
    monkeypatch.setattr(sessions_module, 'time', SimpleNamespace(monotonic=time.monotonic, sleep=sleep))
    return waited


def no_sleeps(monkeypatch):
    """For the paths that must not wait at all: the first sleep fails the test at once."""
    waited = []
    def sleep(seconds):
        waited.append(seconds); pytest.fail('unexpected sleep of %r s on a path that must not wait' % (seconds,))
    monkeypatch.setattr(sessions_module, 'time', SimpleNamespace(monotonic=time.monotonic, sleep=sleep))
    return waited


def counted(monkeypatch, owner, name):
    calls = []
    real = getattr(owner, name)
    def spy(*args, **kwargs):
        calls.append(name)
        return real(*args, **kwargs)
    monkeypatch.setattr(owner, name, spy)
    return calls


def descriptors():
    return len(os.listdir('/dev/fd'))


def test_create_waits_for_reader_shared_lock_then_opens_the_same_catalog(tmp_path, monkeypatch):
    root(tmp_path); catalog = (tmp_path/'epoch.json').read_bytes()
    finished = threading.Event()
    waited = recorded_sleeps(monkeypatch, finished)
    verified = counted(monkeypatch, SessionJournalRoot, '_verify')
    poll = reader_poll(tmp_path, finished)
    try:
        journals = SessionJournalRoot(tmp_path, EPOCH, create=True)  # a producer restart
    finally:
        finished.set(); poll.join()
    assert len(waited) >= 3 and set(waited) == {sessions_module.CATALOG_LOCK_POLL_SECONDS}
    # Refused attempts stop at the lock: the work under it ran exactly once.
    assert verified == ['_verify']
    assert (tmp_path/'epoch.json').read_bytes() == catalog
    assert sorted(os.listdir(tmp_path)) == ['epoch.json', 'maintenance.lock'] and journals.sessions() == ()


def test_prepare_session_waits_for_reader_shared_lock_then_publishes_once(tmp_path, monkeypatch):
    journals = root(tmp_path)
    finished = threading.Event()
    waited = recorded_sleeps(monkeypatch, finished)
    published = counted(monkeypatch, sessions_module, '_atomic_immutable')
    poll = reader_poll(tmp_path, finished)
    try:
        child = journals.prepare_session(DAY, ['MSFT', 'AAPL'])
    finally:
        finished.set(); poll.join()
    assert len(waited) >= 3 and set(waited) == {sessions_module.CATALOG_LOCK_POLL_SECONDS}
    assert published == ['_atomic_immutable'] and child == tmp_path/('session_date=' + DAY)
    assert journals.manifest(DAY)['symbols'] == ['AAPL', 'MSFT']
    manifest = (child/'session.json').read_bytes()
    # Entering the body again is idempotent: same bytes, nothing republished.
    assert journals.prepare_session(DAY, ['AAPL', 'MSFT']) == child
    assert (child/'session.json').read_bytes() == manifest
    assert sorted(p.name for p in child.iterdir()) == ['session.json']


def test_contention_beyond_the_deadline_keeps_the_busy_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 0.2)
    journals = root(tmp_path)
    waited = recorded_sleeps(monkeypatch)  # fails past the ceiling instead of sleeping forever
    with journal_access(tmp_path):  # a reader that does not finish its poll in time
        opened = descriptors()
        for call in (lambda: SessionJournalRoot(tmp_path, EPOCH, create=True),
                     lambda: journals.prepare_session(DAY, ['AAPL'])):
            started = time.monotonic()
            with pytest.raises(SourceUnavailable, match=BUSY) as refused:
                call()
            assert 0.2 <= time.monotonic() - started < WAIT_CEILING_SECONDS
            assert type(refused.value) is SourceUnavailable and refused.value.args == ('MASSIVE_MAINTENANCE_BUSY',)
            # Bounded by the deadline: a 0.2 s wait holds about twenty 10 ms sleeps, never many more.
            assert waited and set(waited) == {sessions_module.CATALOG_LOCK_POLL_SECONDS} and len(waited) <= 25
            del refused, waited[:]
        assert descriptors() == opened  # no descriptor survives the refused attempts
        assert sorted(os.listdir(tmp_path)) == ['epoch.json', 'maintenance.lock']
    # Nothing was left half done: the next start proceeds from the same catalog.
    SessionJournalRoot(tmp_path, EPOCH, create=True).ensure_session(DAY, ['AAPL'])
    assert journals.ready_sessions() == (DAY,)


def test_zero_wait_is_the_previous_immediate_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 0.0)
    journals = root(tmp_path)
    waited = no_sleeps(monkeypatch)
    with journal_access(tmp_path):
        with pytest.raises(SourceUnavailable, match=BUSY):
            SessionJournalRoot(tmp_path, EPOCH, create=True)
        with pytest.raises(SourceUnavailable, match=BUSY):
            journals.prepare_session(DAY, ['AAPL'])
    assert waited == []


def spin():
    """A loop that never sleeps, itself bounded."""
    until = time.monotonic() + WAIT_CEILING_SECONDS
    while time.monotonic() < until:
        pass


def test_wall_clock_ceiling_fails_a_loop_that_never_sleeps_and_exits_if_that_is_swallowed(wall_clock_ceiling, request,
                                                                                          monkeypatch):
    if not wall_clock_ceiling:
        pytest.skip('SIGALRM is not available here')
    remaining, interval = signal.getitimer(signal.ITIMER_REAL)
    assert 0 < remaining <= TEST_WALL_SECONDS and interval == HARD_EXIT_GRACE_SECONDS
    exits = []
    class Exited(Exception):
        pass
    def exited(config, line):
        exits.append(line); raise Exited
    # The real exit is not taken here: it would end this run. Only the decision to take it is observed.
    monkeypatch.setitem(globals(), '_hard_exit', exited)
    # Each timer below is armed inside its block and fires once, so no firing can land outside the block.
    with pytest.raises(pytest.fail.Exception, match='still running after %.0f s on the wall clock' % TEST_WALL_SECONDS):
        signal.setitimer(signal.ITIMER_REAL, 0.05)  # the same handler, sooner
        spin()
    assert exits == []
    with pytest.raises(Exited):
        signal.setitimer(signal.ITIMER_REAL, 0.05)  # the second firing of the same test
        spin()
    assert len(exits) == 1 and exits[0].startswith(request.node.nodeid + ': still running')
    assert exits[0].endswith('exit status %d\n' % HARD_EXIT_STATUS) and exits[0].count('\n') == 1
    assert HARD_EXIT_STATUS not in range(6) and 0 < HARD_EXIT_STATUS < 126  # not one of pytest's own, not a signal


def test_wall_clock_ceiling_puts_back_the_handler_and_the_timer_it_found(wall_clock_ceiling, request):
    if not wall_clock_ceiling:
        pytest.skip('SIGALRM is not available here')
    handler = signal.getsignal(signal.SIGALRM)
    before, interval = signal.getitimer(signal.ITIMER_REAL)
    with _ceiling(request.config, 'inner') as armed:  # a second one, inside the one of the fixture
        assert armed is True and signal.getsignal(signal.SIGALRM) is not handler
        assert signal.getitimer(signal.ITIMER_REAL)[1] == HARD_EXIT_GRACE_SECONDS
    after, again = signal.getitimer(signal.ITIMER_REAL)
    assert signal.getsignal(signal.SIGALRM) is handler and 0 < after <= before and again == interval
    # Another thread arms nothing and changes nothing.
    seen = []
    def elsewhere():
        with _ceiling(request.config, 'thread') as armed:
            seen.append((armed, signal.getsignal(signal.SIGALRM) is handler))
    thread = threading.Thread(target=elsewhere); thread.start(); thread.join(WAIT_CEILING_SECONDS)
    assert seen == [(False, True)] and signal.getitimer(signal.ITIMER_REAL)[1] == interval
    # No timer armed on the way in: none on the way out, also when the body raises.
    signal.setitimer(signal.ITIMER_REAL, 0)
    with pytest.raises(ValueError, match='^inside$'):
        with _ceiling(request.config, 'inner'):
            raise ValueError('inside')
    assert signal.getsignal(signal.SIGALRM) is handler and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_wait_is_bounded_by_the_monotonic_clock_and_reraises_the_last_refusal(monkeypatch):
    clock = [100.0]; waited = []; allowed = [8]; reads = []
    def spinning(what, count):
        # Nothing blocks on the fake clock. A retry that stopped sleeping, or that never ends, must fail
        # here: left alone it spins for ever and keeps every refusal it raised.
        if count > FAKE_CLOCK_CEILING:
            pytest.fail('%s number %d on the fake clock, at most %d expected' % (what, count, FAKE_CLOCK_CEILING))
    def monotonic():
        reads.append(1); spinning('clock read', len(reads))
        return clock[0]
    def sleep(seconds):
        # An unbounded or over-eager retry that still sleeps fails here.
        if len(waited) >= allowed[0]:
            pytest.fail('sleep number %d, at most %d expected' % (len(waited) + 1, allowed[0]))
        waited.append(seconds); clock[0] += seconds
    # No wall clock is available to the module here: only monotonic and sleep.
    monkeypatch.setattr(sessions_module, 'time', SimpleNamespace(monotonic=monotonic, sleep=sleep))
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 1.0)
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_POLL_SECONDS', 0.25)
    raised = []
    def busy():
        spinning('attempt', len(raised) + 1)
        raised.append(SourceUnavailable('MASSIVE_MAINTENANCE_BUSY')); raise raised[-1]
    with pytest.raises(SourceUnavailable) as refused:
        sessions_module._wait_exclusive(busy)
    assert refused.value is raised[-1] and len(raised) == 5 and waited == [0.25] * 4
    del waited[:]; attempts = []
    def released():
        attempts.append(clock[0]); spinning('attempt', len(attempts))
        if len(attempts) < 3:
            raise SourceUnavailable('MASSIVE_MAINTENANCE_BUSY')
        return 'entered'
    assert sessions_module._wait_exclusive(released) == 'entered' and waited == [0.25] * 2
    del waited[:]; allowed[0] = 0  # every other refusal: the first sleep already fails
    for error in (SourceUnavailable('MASSIVE_MAINTENANCE_UNSAFE'), SourceUnavailable('MASSIVE_MAINTENANCE_CHANGED'),
                  ValueError('MASSIVE_MAINTENANCE_BUSY'), OSError('MASSIVE_MAINTENANCE_BUSY')):
        calls = []
        def other():
            calls.append(1); spinning('attempt', len(calls)); raise error
        with pytest.raises(type(error)) as immediate:
            sessions_module._wait_exclusive(other)
        assert immediate.value is error and calls == [1] and waited == []
    assert len(reads) <= FAKE_CLOCK_CEILING // 2  # the ceiling keeps its margin over the real number of reads


def test_other_refusals_are_raised_at_once_without_sleeping(tmp_path, monkeypatch):
    waited = no_sleeps(monkeypatch)
    def refused(code, call):
        started = time.monotonic()
        with pytest.raises(SourceUnavailable, match='^' + code + '$'):
            call()
        assert time.monotonic() - started < WAIT_CEILING_SECONDS and waited == []
    bound = tmp_path/'bound'; bound.mkdir(mode=0o700)
    journals = root(bound); journals.prepare_session(DAY, ['AAPL'])
    lock = bound/'maintenance.lock'
    # Create path: argument, epoch, root and lock refusals.
    refused('MASSIVE_SESSION_EPOCH', lambda: SessionJournalRoot(bound, 'not an epoch', create=True))
    refused('MASSIVE_SESSION_POLICY', lambda: SessionJournalRoot(bound, EPOCH, create=1))
    refused('MASSIVE_SESSION_MANIFEST_CHANGED', lambda: SessionJournalRoot(bound, 'OTHER', create=True))
    flat = tmp_path/'flat'; flat.mkdir(mode=0o700); (flat/('session_date=' + DAY)).mkdir(mode=0o700)
    refused('MASSIVE_SESSION_EPOCH_MISSING', lambda: SessionJournalRoot(flat, EPOCH, create=True))
    stray = tmp_path/'stray'; stray.mkdir(mode=0o700); (stray/'lost+found').mkdir(mode=0o700)
    refused('MASSIVE_SESSION_LAYOUT', lambda: SessionJournalRoot(stray, EPOCH, create=True))
    bound.chmod(0o750)
    try:
        refused('SOURCE_DIRECTORY_NOT_PRIVATE', lambda: SessionJournalRoot(bound, EPOCH, create=True))
    finally:
        bound.chmod(0o700)
    lock.chmod(0o640)
    try:
        refused('MASSIVE_MAINTENANCE_UNSAFE', lambda: SessionJournalRoot(bound, EPOCH, create=True))
        refused('MASSIVE_MAINTENANCE_UNSAFE', lambda: journals.prepare_session(DAY, ['AAPL']))
    finally:
        lock.chmod(0o600)
    # Prepare path: date, symbols, manifest, count limit, epoch and root identity.
    refused('MASSIVE_SESSION_DATE', lambda: journals.prepare_session('2026-10-5', ['AAPL']))
    refused('MASSIVE_SESSION_SYMBOLS', lambda: journals.prepare_session(DAY, ['aapl']))
    refused('MASSIVE_SESSION_SYMBOLS', lambda: journals.prepare_session(DAY, ['AAPL', 'AAPL']))
    refused('MASSIVE_SESSION_MANIFEST_CHANGED', lambda: journals.prepare_session(DAY, ['MSFT']))
    with monkeypatch.context() as limited:
        limited.setattr(sessions_module, 'MAX_SESSIONS', 1)
        refused('MASSIVE_SESSION_COUNT_LIMIT', lambda: journals.prepare_session(NEXT, ['AAPL']))
    with monkeypatch.context() as renamed:
        renamed.setattr(journals, 'epoch', 'OTHER')
        refused('MASSIVE_SESSION_EPOCH_MISMATCH', lambda: journals.prepare_session(NEXT, ['AAPL']))
    other = tmp_path/'other'; other.mkdir(mode=0o700); root(other)
    with monkeypatch.context() as repointed:
        repointed.setattr(journals, 'root', other)
        refused('MASSIVE_SESSION_ROOT_CHANGED', lambda: journals.prepare_session(NEXT, ['AAPL']))
    # A refusal decided before the lock does not wait for a reader either.
    with journal_access(bound):
        refused('MASSIVE_SESSION_SYMBOLS', lambda: journals.prepare_session(NEXT, []))
        refused('MASSIVE_SESSION_EPOCH', lambda: SessionJournalRoot(bound, '', create=True))
    assert sorted(os.listdir(bound)) == ['epoch.json', 'maintenance.lock', 'session_date=' + DAY]
    assert not (other/('session_date=' + NEXT)).exists() and waited == []


def test_uncontended_create_and_prepare_do_not_sleep(tmp_path, monkeypatch):
    waited = no_sleeps(monkeypatch)
    journals = root(tmp_path)          # first creation
    root(tmp_path)                     # idempotent creation
    child = journals.prepare_session(DAY, ['AAPL'])
    assert journals.prepare_session(DAY, ['AAPL']) == child
    journals.ensure_session(NEXT, ['MSFT'])
    assert journals.ready_sessions() == (NEXT,) and waited == []


def test_reader_open_under_an_exclusive_holder_still_refuses_at_once(tmp_path, monkeypatch):
    from app.r2d2_v2_store import ShadowIntegrityError
    journals = root(tmp_path); journals.ensure_session(DAY, ['AAPL'])
    waited = no_sleeps(monkeypatch)
    with journal_access(tmp_path, exclusive=True):  # the producer inside create, prepare or ready
        started = time.monotonic()
        for call in (lambda: SessionJournalRoot(tmp_path, EPOCH), journals.sessions, journals.ready_sessions,
                     lambda: journals.manifest(DAY), lambda: journals.open_session(DAY)):
            with pytest.raises(SourceUnavailable, match=BUSY):
                call()
        # The worker start and a poll keep their existing answers.
        with pytest.raises(ShadowIntegrityError, match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):
            reader(tmp_path, EPOCH)
        page = MassiveSessionEventSource(journals).prepare_events(NOW, {})
        assert page == {'events': [], 'diagnostics': [{'code': 'RAW_APPEND_IN_PROGRESS'}], 'cursor': {}}
        assert time.monotonic() - started < WAIT_CEILING_SECONDS and waited == []
    with journal_access(tmp_path):  # shared holders never exclude a reader
        assert SessionJournalRoot(tmp_path, EPOCH).ready_sessions() == (DAY,)
    assert waited == []


def test_supervised_start_during_a_reader_poll_does_not_burn_a_claim(container, monkeypatch):
    layout, produce = container; tree = layout('polled')
    SessionJournalRoot(tree.journal, LAYOUT_EPOCH, create=True)  # the catalog exists before the first start
    finished = threading.Event()
    waited = recorded_sleeps(monkeypatch, finished)
    poll = reader_poll(tree.journal, finished)
    try:
        code, notices, connects = produce(tree)
    finally:
        finished.set(); poll.join()
    assert code == 0 and len(connects) == 1 and len(waited) >= 3
    assert claims(tree) == [tree.day + '.attempt-1.json']
    assert not any(notice['status'] in ('FAILED', 'DATA_GAP') for notice in notices)
    assert (tree.journal/('session_date=' + tree.day)/'ready.json').exists()
    # Past the deadline the attempt fails as before: same code, no connection, the claim is spent.
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 0.2)
    late = layout('starved'); SessionJournalRoot(late.journal, LAYOUT_EPOCH, create=True)
    with journal_access(late.journal):
        code, notices, connects = produce(late)
    assert code == 1 and connects == [] and claims(late) == [late.day + '.attempt-1.json']
    assert notices[-1] == {'status': 'FAILED', 'session': late.day, 'reason': 'SUPERVISOR_PRODUCER_FAILURE',
                           'code': 'MASSIVE_MAINTENANCE_BUSY'}
    assert sorted(os.listdir(late.journal)) == ['epoch.json', 'maintenance.lock', 'producer.lock']


def test_production_bound_is_pinned_and_fits_inside_the_first_retry_delay():
    # The other tests shorten the wait; these are the values the producer runs with.
    assert (sessions_module.CATALOG_LOCK_WAIT_SECONDS, sessions_module.CATALOG_LOCK_POLL_SECONDS) == (30.0, 0.01)
    assert (sessions_module.READY_LOCK_WAIT_SECONDS, sessions_module.READY_LOCK_POLL_SECONDS) == (30.0, 0.01)
    assert all(type(getattr(sessions_module, name)) is float for name in ('CATALOG_LOCK_WAIT_SECONDS',
        'CATALOG_LOCK_POLL_SECONDS', 'READY_LOCK_WAIT_SECONDS', 'READY_LOCK_POLL_SECONDS'))
    # One expired wait never costs more time than the retry the supervisor would have made anyway.
    assert supervisor_module.RETRY_DELAYS == (0, 30, 60, 120, 240)
    assert sessions_module.CATALOG_LOCK_WAIT_SECONDS <= supervisor_module.RETRY_DELAYS[1]


def test_readme_worst_case_figures_follow_the_constants():
    readme = (UNIT_ROOT/'README.md').read_text(); unit = (UNIT_ROOT/'c3po-massive.service').read_text()
    restart = re.search(r'^RestartSec=(\d+)s$', unit, re.M)
    assert restart is not None
    # Three waits per start: catalog open, session preparation, ready marker.
    waits = 2 * sessions_module.CATALOG_LOCK_WAIT_SECONDS + sessions_module.READY_LOCK_WAIT_SECONDS
    assert waits == 90
    plain = []; delayed = []; at = 0
    for number, delay in enumerate(supervisor_module.RETRY_DELAYS, 1):
        at += delay + (int(restart.group(1)) if number > 1 else 0)
        plain.append(at); delayed.append(at + number * int(waits))
    assert plain == [0, 31, 92, 213, 454] and delayed == [90, 211, 362, 573, 904]
    spoken = lambda values, last: ', '.join(map(str, values[:-1])) + last + str(values[-1]) + ' seconds'
    assert all(value in readme for value in (spoken(plain, ' and '), spoken(delayed, ' and '),
        'delayed by up to %d seconds' % waits,
        'three lock waits of at most %d seconds each' % sessions_module.CATALOG_LOCK_WAIT_SECONDS,
        'retrying every %d ms' % round(sessions_module.CATALOG_LOCK_POLL_SECONDS * 1000),
        '(' + spoken(supervisor_module.RETRY_DELAYS[1:], ' or ') + ', by attempt number)'))
    assert 'the next attempt comes 30 seconds later' not in readme
    # One expired wait on the first attempt already costs the 09:30 minute: the wait, RestartSec and the
    # backoff of the second attempt are longer than the 60 seconds between the 09:29:00 start and the open.
    assert 'OnCalendar=Mon..Fri *-*-* 09:29:00 America/New_York' in (UNIT_ROOT/'c3po-massive.timer').read_text()
    expired = (int(min(sessions_module.CATALOG_LOCK_WAIT_SECONDS, sessions_module.READY_LOCK_WAIT_SECONDS))
               + int(restart.group(1)) + supervisor_module.RETRY_DELAYS[1])
    assert expired == 61 > 60 and 'add up to %d seconds, more than the 60 the start had' % expired in readme
    # What the document says about the ceilings of this file follows the constants at its top, and claims no more.
    assert all(value in readme for value in ('the patched sleep fails past %d seconds' % WAIT_CEILING_SECONDS,
        'the fake clock fails past %d reads or attempts' % FAKE_CLOCK_CEILING,
        'an alarm fails any test still running after %d seconds' % TEST_WALL_SECONDS,
        'if the same test is still running %d seconds later' % HARD_EXIT_GRACE_SECONDS,
        'not a proof that the file cannot hang'))
