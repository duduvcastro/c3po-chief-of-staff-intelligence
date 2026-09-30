"""An unready minute-bar session never blocks the published ones."""
from datetime import datetime, timezone
import os
import stat
import threading
import time
import pytest
from app import r2d2_v2_massive_sessions as sessions_module
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_sources import SourceUnavailable

EPOCH = 'R2D2-V2-SHADOW-READY-TEST'
OLD = '2026-09-28'
NEW = '2026-09-29'
NOW = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)


def root(tmp_path):
    return SessionJournalRoot(tmp_path, EPOCH, create=True)


def gap(day, symbol='AAPL', number=0):
    at = day + 'T14:00:00+00:00'
    return {'event': {'type': 'DATA_GAP', 'at': at, 'available_at': at, 'session': day,
                     'instrument_key': 'US:' + symbol, 'reason': 'fixture-' + str(number)}}


def delivered(journals):
    page = MassiveSessionEventSource(journals).prepare_events(NOW, {})
    assert not page['diagnostics'], page['diagnostics']
    return page


def refused(journals, code='RAW_APPEND_IN_PROGRESS'):
    page = MassiveSessionEventSource(journals).prepare_events(NOW, {})
    assert page == {'events': [], 'diagnostics': [{'code': code}], 'cursor': {}}


def test_mark_ready_waits_for_reader_shared_lock_then_backlog_flows(tmp_path):
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    child = journals.prepare_session(NEW, ['AAPL']); MassiveJournal(child)
    outcome = {}
    held = threading.Event()
    def poll():
        with journal_access(tmp_path):  # consumer poll in progress (shared)
            held.set(); time.sleep(0.4)
    reader = threading.Thread(target=poll); reader.start()
    try:
        assert held.wait(5)
        started = time.monotonic()
        journals.mark_ready(NEW)
        outcome['waited'] = time.monotonic() - started
    finally:
        reader.join()
    assert outcome['waited'] >= 0.2 and (child/'ready.json').exists()
    page = delivered(journals)
    assert len(page['events']) == 1 and page['cursor']['sessions'] == {OLD: 1, NEW: 0}


def test_mark_ready_times_out_cleanly_and_unready_session_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setattr(sessions_module, 'READY_LOCK_WAIT_SECONDS', 0.2)
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    child = journals.prepare_session(NEW, ['AAPL']); MassiveJournal(child)
    with journal_access(tmp_path):
        started = time.monotonic()
        with pytest.raises(SourceUnavailable, match='MASSIVE_MAINTENANCE_BUSY'):
            journals.mark_ready(NEW)
        assert 0.2 <= time.monotonic() - started < 5
    assert not (child/'ready.json').exists()
    page = delivered(journals)  # reviewer repro: old backlog was starved here
    assert len(page['events']) == 1 and page['cursor']['sessions'] == {OLD: 1}
    journals.mark_ready(NEW)
    assert delivered(journals)['cursor']['sessions'] == {OLD: 1, NEW: 0}


def test_crash_between_mkdir_and_manifest_does_not_block_other_sessions(tmp_path):
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    empty = tmp_path/('session_date=' + NEW); empty.mkdir(mode=0o700)
    page = delivered(journals)
    assert len(page['events']) == 1 and page['cursor']['sessions'] == {OLD: 1}
    assert list(empty.iterdir()) == []
    # The interrupted session is completed idempotently later.
    journals.ensure_session(NEW, ['MSFT'])(None, gap(NEW, 'MSFT'))
    later = MassiveSessionEventSource(journals).prepare_events(NOW, page['cursor'])
    assert not later['diagnostics'] and later['cursor']['sessions'] == {OLD: 1, NEW: 1}


def test_crash_leaving_temporary_manifest_or_empty_index_is_still_empty(tmp_path):
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    child = tmp_path/('session_date=' + NEW); child.mkdir(mode=0o700)
    fd = os.open(child/('.session.json.' + '0' * 16 + '.tmp'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, b'{"sch'); os.close(fd)
    fd = os.open(child/'sequence.sqlite3', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
    assert delivered(journals)['cursor']['sessions'] == {OLD: 1}


@pytest.mark.parametrize('content', ['receipt', 'raw', 'unknown', 'index_row'])
def test_unready_session_with_content_still_fails_closed(tmp_path, content):
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    child = journals.prepare_session(NEW, ['AAPL'])
    if content == 'index_row':
        MassiveJournal(child)(None, gap(NEW))
    else:
        MassiveJournal(child)
        name = {'receipt': 'receipts/x.json', 'raw': 'raw/x.bin', 'unknown': 'stray.bin'}[content]
        fd = os.open(child/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, b'x'); os.close(fd)
    refused(journals)
    assert not (child/'ready.json').exists()


def test_unready_session_with_invalid_manifest_is_not_skipped(tmp_path):
    journals = root(tmp_path)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    child = tmp_path/('session_date=' + NEW); child.mkdir(mode=0o700)
    fd = os.open(child/'session.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, b'{"schema"'); os.close(fd)
    refused(journals, 'MASSIVE_SESSION_SOURCE_UNVERIFIED')


def test_manifest_and_ready_are_published_atomically(tmp_path, monkeypatch):
    journals = root(tmp_path)
    child = journals.prepare_session(NEW, ['AAPL']); MassiveJournal(child)
    writes = []
    real_open, real_rename = os.open, os.rename
    def spy_open(path, flags, *args, **kwargs):
        writes.append(('open', str(path), flags & os.O_EXCL))
        return real_open(path, flags, *args, **kwargs)
    def spy_rename(source, target, **kwargs):
        # A reader at this instant sees either no ready.json or the whole file.
        assert not (child/target).exists() and (child/source).read_bytes()
        writes.append(('rename', source, target))
        return real_rename(source, target, **kwargs)
    monkeypatch.setattr(sessions_module.os, 'open', spy_open)
    monkeypatch.setattr(sessions_module.os, 'rename', spy_rename)
    journals.mark_ready(NEW)
    renames = [w for w in writes if w[0] == 'rename']
    assert len(renames) == 1 and renames[0][2] == 'ready.json'
    assert sessions_module._TEMPORARY.fullmatch(renames[0][1])
    assert ('open', 'ready.json', os.O_EXCL) not in writes
    assert sorted(p.name for p in child.iterdir() if p.name.endswith('.tmp')) == []
    assert (child/'ready.json').read_bytes() == b'{"epoch":"' + EPOCH.encode() + b'","session":"' + NEW.encode() + b'"}'
    assert oct((child/'ready.json').stat().st_mode & 0o777) == oct(0o600)
    manifest = (child/'session.json').read_bytes()
    journals.prepare_session(NEW, ['AAPL'])  # idempotent: same bytes, no second publish
    assert (child/'session.json').read_bytes() == manifest
    assert [w for w in writes if w[0] == 'rename'] == renames
    with pytest.raises(SourceUnavailable, match='MASSIVE_SESSION_MANIFEST_CHANGED'):
        journals.prepare_session(NEW, ['MSFT'])


def test_failed_atomic_write_leaves_no_published_file(tmp_path, monkeypatch):
    journals = root(tmp_path)
    child = tmp_path/('session_date=' + NEW)
    real_fsync = os.fsync
    def broken_fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('disk')  # the temporary manifest never becomes durable
        return real_fsync(fd)
    monkeypatch.setattr(sessions_module.os, 'fsync', broken_fsync)
    with pytest.raises(OSError):
        journals.prepare_session(NEW, ['AAPL'])
    monkeypatch.undo()
    assert not (child/'session.json').exists()
    assert [p.name for p in child.iterdir()] == []
