"""Catalog create and session prepare wait a bounded time for a reader poll.

Real flock contention: every holder below is a second open file description
of the same maintenance.lock, exactly what another process would hold.
"""
from datetime import datetime, timezone
import os
import threading
import time
from types import SimpleNamespace
import pytest
from app import r2d2_v2_massive_sessions as sessions_module
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_sources import SourceUnavailable
from test_r2d2_v2_minute_bars import calendar
from test_r2d2_v2_massive_supervisor import EPOCH as LAYOUT_EPOCH, claims, container, reader

EPOCH = 'R2D2-V2-SHADOW-LOCK-WAIT-TEST'
DAY = '2026-10-05'
NEXT = '2026-10-06'
NOW = datetime(2026, 10, 6, 15, tzinfo=timezone.utc)
BUSY = '^MASSIVE_MAINTENANCE_BUSY$'


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
    attempt, so the wait is observed without depending on scheduling."""
    waited = []
    def sleep(seconds):
        waited.append(seconds); time.sleep(seconds)
        if finished is not None and len(waited) == 3:
            finished.set()
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
    with journal_access(tmp_path):  # a reader that does not finish its poll in time
        opened = descriptors()
        for call in (lambda: SessionJournalRoot(tmp_path, EPOCH, create=True),
                     lambda: journals.prepare_session(DAY, ['AAPL'])):
            started = time.monotonic()
            with pytest.raises(SourceUnavailable, match=BUSY) as refused:
                call()
            assert 0.2 <= time.monotonic() - started < 5
            assert type(refused.value) is SourceUnavailable and refused.value.args == ('MASSIVE_MAINTENANCE_BUSY',)
            del refused
        assert descriptors() == opened  # no descriptor survives the refused attempts
        assert sorted(os.listdir(tmp_path)) == ['epoch.json', 'maintenance.lock']
    # Nothing was left half done: the next start proceeds from the same catalog.
    SessionJournalRoot(tmp_path, EPOCH, create=True).ensure_session(DAY, ['AAPL'])
    assert journals.ready_sessions() == (DAY,)


def test_zero_wait_is_the_previous_immediate_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 0.0)
    journals = root(tmp_path)
    waited = recorded_sleeps(monkeypatch)
    with journal_access(tmp_path):
        with pytest.raises(SourceUnavailable, match=BUSY):
            SessionJournalRoot(tmp_path, EPOCH, create=True)
        with pytest.raises(SourceUnavailable, match=BUSY):
            journals.prepare_session(DAY, ['AAPL'])
    assert waited == []


def test_wait_is_bounded_by_the_monotonic_clock_and_reraises_the_last_refusal(monkeypatch):
    clock = [100.0]; waited = []
    def sleep(seconds):
        waited.append(seconds); clock[0] += seconds
    # No wall clock is available to the module here: only monotonic and sleep.
    monkeypatch.setattr(sessions_module, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_WAIT_SECONDS', 1.0)
    monkeypatch.setattr(sessions_module, 'CATALOG_LOCK_POLL_SECONDS', 0.25)
    raised = []
    def busy():
        raised.append(SourceUnavailable('MASSIVE_MAINTENANCE_BUSY')); raise raised[-1]
    with pytest.raises(SourceUnavailable) as refused:
        sessions_module._wait_exclusive(busy)
    assert refused.value is raised[-1] and len(raised) == 5 and waited == [0.25] * 4
    del waited[:]; attempts = []
    def released():
        attempts.append(clock[0])
        if len(attempts) < 3:
            raise SourceUnavailable('MASSIVE_MAINTENANCE_BUSY')
        return 'entered'
    assert sessions_module._wait_exclusive(released) == 'entered' and waited == [0.25] * 2
    del waited[:]
    for error in (SourceUnavailable('MASSIVE_MAINTENANCE_UNSAFE'), SourceUnavailable('MASSIVE_MAINTENANCE_CHANGED'),
                  ValueError('MASSIVE_MAINTENANCE_BUSY'), OSError('MASSIVE_MAINTENANCE_BUSY')):
        calls = []
        def other():
            calls.append(1); raise error
        with pytest.raises(type(error)) as immediate:
            sessions_module._wait_exclusive(other)
        assert immediate.value is error and calls == [1] and waited == []


def test_other_refusals_are_raised_at_once_without_sleeping(tmp_path, monkeypatch):
    waited = recorded_sleeps(monkeypatch)
    def refused(code, call):
        started = time.monotonic()
        with pytest.raises(SourceUnavailable, match='^' + code + '$'):
            call()
        assert time.monotonic() - started < 5 and waited == []
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
    waited = recorded_sleeps(monkeypatch)
    journals = root(tmp_path)          # first creation
    root(tmp_path)                     # idempotent creation
    child = journals.prepare_session(DAY, ['AAPL'])
    assert journals.prepare_session(DAY, ['AAPL']) == child
    journals.ensure_session(NEXT, ['MSFT'])
    assert journals.ready_sessions() == (NEXT,) and waited == []


def test_reader_open_under_an_exclusive_holder_still_refuses_at_once(tmp_path, monkeypatch):
    from app.r2d2_v2_store import ShadowIntegrityError
    journals = root(tmp_path); journals.ensure_session(DAY, ['AAPL'])
    waited = recorded_sleeps(monkeypatch)
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
        assert time.monotonic() - started < 5 and waited == []
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
