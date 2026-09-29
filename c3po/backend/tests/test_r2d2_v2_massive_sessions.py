"""Real local indexes and immutable evidence; no host/provider or deletion."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import pytest
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_sources import SourceUnavailable

EPOCH = 'R2D2-V2-SHADOW-SESSION-TEST'
OLD = '2026-09-28'
NEW = '2026-09-29'
NOW = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)


def root(tmp_path):
    return SessionJournalRoot(tmp_path, EPOCH, create=True)


def gap(day, symbol='AAPL', number=0):
    at = day + 'T14:00:00+00:00'
    return {'event': {'type': 'DATA_GAP', 'at': at, 'available_at': at, 'session': day,
                     'instrument_key': 'US:' + symbol, 'reason': 'fixture-' + str(number)}}


def test_two_sessions_local_sequences_and_uncommitted_backlog_survive_restart(tmp_path):
    journals = root(tmp_path)
    old = journals.ensure_session(OLD, ['AAPL']); old(None, gap(OLD))
    first = MassiveSessionEventSource(journals).prepare_events(NOW, {})
    assert not first['diagnostics'] and first['cursor']['sessions'] == {OLD: 1}
    new = journals.ensure_session(NEW, ['MSFT']); new(None, gap(NEW, 'MSFT'))
    before = {p: p.read_bytes() for p in (old.path.parent/'receipts').iterdir()}
    restarted = MassiveSessionEventSource(SessionJournalRoot(tmp_path, EPOCH))
    reoffer = restarted.prepare_events(NOW, {}, snapshot=first['snapshot'])
    assert reoffer == first  # Reading the original proposal was not an ACK.
    old_again = restarted.prepare_events(NOW, {})
    assert old_again['events'] == first['events'] and old_again['has_more']
    assert old_again['cursor']['sessions'] == {OLD: 1, NEW: 0}
    next_page = restarted.prepare_events(NOW, old_again['cursor'], snapshot=old_again['snapshot'])
    assert not next_page['diagnostics'] and not next_page['has_more']
    assert next_page['cursor']['sessions'] == {OLD: 1, NEW: 1}
    assert next_page['events'][0]['sequence'] == first['events'][0]['sequence'] == 0
    assert next_page['events'][0]['source_id'] != first['events'][0]['source_id']
    assert not restarted.prepare_events(NOW, next_page['cursor'])['events']
    assert all(p.read_bytes() == data for p, data in before.items())


def test_snapshot_new_session_is_visible_only_on_next_poll(tmp_path):
    journals = root(tmp_path); journals.ensure_session(OLD, ['AAPL'])
    source = MassiveSessionEventSource(journals)
    frozen = source.prepare_events(NOW, {})
    journals.ensure_session(NEW, ['MSFT'])(None, gap(NEW, 'MSFT'))
    same = source.prepare_events(NOW, frozen['cursor'], snapshot=frozen['snapshot'])
    assert not same['events'] and same['snapshot'] == frozen['snapshot']
    later = source.prepare_events(NOW, same['cursor'])
    assert len(later['events']) == 1 and later['cursor']['sessions'] == {OLD: 0, NEW: 1}


def test_append_to_previously_acknowledged_old_session_is_not_skipped(tmp_path):
    journals = root(tmp_path)
    old = journals.ensure_session(OLD, ['AAPL']); old(None, gap(OLD))
    new = journals.ensure_session(NEW, ['MSFT']); new(None, gap(NEW, 'MSFT'))
    source = MassiveSessionEventSource(journals)
    one = source.prepare_events(NOW, {})
    two = source.prepare_events(NOW, one['cursor'])
    old(None, gap(OLD, number=1))
    three = source.prepare_events(NOW, two['cursor'])
    assert len(three['events']) == 1 and three['events'][0]['session'] == OLD
    assert three['events'][0]['sequence'] == 1 and three['cursor']['sessions'] == {OLD: 2, NEW: 1}


@pytest.mark.parametrize('mutation', ['wrong_epoch', 'legacy', 'bool', 'missing', 'ahead', 'extra'])
def test_invalid_cursor_never_advances(tmp_path, mutation):
    journals = root(tmp_path); journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    cursor = {'version': 2, 'epoch': EPOCH, 'sessions': {OLD: 0}}
    if mutation == 'wrong_epoch': cursor['epoch'] = 'OTHER'
    if mutation == 'legacy': cursor = {'massive_sequence': 0}
    if mutation == 'bool': cursor['sessions'][OLD] = True
    if mutation == 'missing': cursor['sessions'][NEW] = 0
    if mutation == 'ahead': cursor['sessions'][OLD] = 2
    if mutation == 'extra': cursor['extra'] = 1
    original = deepcopy(cursor)
    result = MassiveSessionEventSource(journals).prepare_events(NOW, cursor)
    assert result['diagnostics'] and not result['events'] and result['cursor'] == original == cursor


def test_wrong_session_or_daily_universe_receipt_is_not_consumed(tmp_path):
    journals = root(tmp_path); old = journals.ensure_session(OLD, ['AAPL'])
    old(None, gap(OLD, 'MSFT'))
    source = MassiveSessionEventSource(journals)
    refused = source.prepare_events(NOW, {})
    assert refused['diagnostics'] and not refused['events'] and refused['cursor'] == {}
    new = journals.ensure_session(NEW, ['MSFT']); new(None, gap(OLD, 'MSFT'))
    refused = source.prepare_events(NOW, {'version': 2, 'epoch': EPOCH, 'sessions': {OLD: 1}})
    assert refused['diagnostics'] and not refused['events']


def test_manifest_list_and_epoch_cannot_be_reassigned(tmp_path):
    journals = root(tmp_path); path = journals.prepare_session(OLD, ['AAPL'])
    original = (path/'session.json').read_bytes()
    with pytest.raises(SourceUnavailable): journals.prepare_session(OLD, ['MSFT'])
    with pytest.raises(SourceUnavailable): SessionJournalRoot(tmp_path, 'OTHER', create=True)
    assert (path/'session.json').read_bytes() == original
    assert not (path/'sequence.sqlite3').exists()


def test_missing_parent_epoch_cannot_adopt_old_children(tmp_path):
    journals = root(tmp_path); journals.ensure_session(OLD, ['AAPL'])
    (tmp_path/'epoch.json').unlink()
    with pytest.raises(SourceUnavailable, match='EPOCH_MISSING'):
        SessionJournalRoot(tmp_path, EPOCH, create=True)
    assert not (tmp_path/'epoch.json').exists()


def test_unready_session_defers_without_mutation(tmp_path):
    journals = root(tmp_path); path = journals.prepare_session(OLD, ['AAPL'])
    result = MassiveSessionEventSource(journals).prepare_events(NOW, {})
    assert result == {'events': [], 'diagnostics': [{'code': 'RAW_APPEND_IN_PROGRESS'}], 'cursor': {}}
    assert not (path/'sequence.sqlite3').exists()


@pytest.mark.parametrize('mutation', ['symlink', 'missing', 'corrupt'])
def test_session_replacement_or_corruption_refuses_whole_page(tmp_path, mutation):
    journals = root(tmp_path); journal = journals.ensure_session(OLD, ['AAPL'])
    journal(None, gap(OLD)); source = MassiveSessionEventSource(journals)
    first = source.prepare_events(NOW, {})
    if mutation == 'corrupt':
        next((journal.path.parent/'receipts').iterdir()).write_bytes(b'{}')
    else:
        journal.path.parent.rename(tmp_path/'moved')
        # Keep unrelated replacement outside the allowed parent catalog.
        (tmp_path/'moved').rename(tmp_path.parent/(tmp_path.name+'-moved'))
        if mutation == 'symlink':
            journal.path.parent.symlink_to(tmp_path.parent/(tmp_path.name+'-moved'))
    refused = source.prepare_events(NOW, {}, snapshot=first['snapshot'])
    assert refused['diagnostics'] and not refused['events'] and refused['cursor'] == {}


def test_split_large_receipt_group_keeps_raw_horizon_and_session_positions(tmp_path):
    journals = root(tmp_path); journal = journals.ensure_session(OLD, ['AAPL'])
    for number in range(4100): journal(None, gap(OLD, number=number))
    journals.ensure_session(NEW, ['MSFT'])(None, gap(NEW, 'MSFT'))
    source = MassiveSessionEventSource(journals)
    one = source.prepare_events(NOW, {})
    assert not one['diagnostics'] and len(one['events']) == 4096 and one['has_more']
    assert one['page']['cutoff_received_at'] == '2026-09-28T13:59:59.999999+00:00'
    two = source.prepare_events(NOW, one['cursor'], snapshot=one['snapshot'])
    assert not two['diagnostics'] and len(two['events']) == 4 and two['has_more']
    assert two['page']['cutoff_received_at'] == '2026-09-28T14:00:00+00:00'
    three = source.prepare_events(NOW, two['cursor'], snapshot=one['snapshot'])
    assert not three['diagnostics'] and len(three['events']) == 1 and not three['has_more']
    assert three['cursor']['sessions'] == {OLD: 4100, NEW: 1}


def test_persistent_session_checkpoint_and_evidence_commit_or_rollback_together(tmp_path):
    import sqlite3
    from app.r2d2_v2_sources import canonical, _load_json
    parent = tmp_path/'journals'; parent.mkdir(mode=0o700)
    journals = root(parent)
    journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    journals.ensure_session(NEW, ['MSFT'])(None, gap(NEW, 'MSFT'))
    source = MassiveSessionEventSource(journals)
    first = source.prepare_events(NOW, {})
    dbpath = tmp_path/'consumer.sqlite3'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE cursor (body BLOB NOT NULL)')
        db.execute('CREATE TABLE events (id TEXT PRIMARY KEY, receipt TEXT NOT NULL)')
        db.execute('INSERT INTO cursor VALUES (?)', (canonical(first['cursor']),))
        db.executemany('INSERT INTO events VALUES (?,?)', first['raw_receipts'].items())
    second = source.prepare_events(NOW, first['cursor'], snapshot=first['snapshot'])
    with sqlite3.connect(dbpath) as db:
        db.execute('UPDATE cursor SET body=?', (canonical(second['cursor']),))
        db.executemany('INSERT INTO events VALUES (?,?)', second['raw_receipts'].items())
        db.rollback()
    with sqlite3.connect(dbpath) as db:
        committed = _load_json(db.execute('SELECT body FROM cursor').fetchone()[0])
        assert committed['sessions'] == {OLD: 1, NEW: 0}
        assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1
    restarted = MassiveSessionEventSource(SessionJournalRoot(parent, EPOCH))
    reoffered = restarted.prepare_events(NOW, committed, snapshot=first['snapshot'])
    assert reoffered == second
    with sqlite3.connect(dbpath) as db:
        db.execute('UPDATE cursor SET body=?', (canonical(reoffered['cursor']),))
        db.executemany('INSERT INTO events VALUES (?,?)', reoffered['raw_receipts'].items())
    with sqlite3.connect(dbpath) as db:
        committed = _load_json(db.execute('SELECT body FROM cursor').fetchone()[0])
        assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 2
    assert not restarted.prepare_events(NOW, committed)['events']


def test_initialized_index_is_not_published_before_ready_marker(tmp_path):
    from app.r2d2_v2_massive_journal import MassiveJournal
    journals = root(tmp_path); child = journals.prepare_session(OLD, ['AAPL'])
    journal = MassiveJournal(child); journal(None, gap(OLD))
    source = MassiveSessionEventSource(journals)
    held = source.prepare_events(NOW, {})
    assert held['diagnostics'] == [{'code': 'RAW_APPEND_IN_PROGRESS'}] and held['cursor'] == {}
    journals.mark_ready(OLD)
    ready = source.prepare_events(NOW, {})
    assert not ready['diagnostics'] and len(ready['events']) == 1


def test_reader_does_not_open_new_provider_or_create_missing_catalog(tmp_path):
    with pytest.raises((OSError, SourceUnavailable)):
        SessionJournalRoot(tmp_path, EPOCH)
    assert list(tmp_path.iterdir()) == []


def test_copied_session_directory_is_not_silently_adopted_after_restart(tmp_path):
    import shutil
    journals = root(tmp_path); journal = journals.ensure_session(OLD, ['AAPL'])
    journal(None, gap(OLD)); first = MassiveSessionEventSource(journals).prepare_events(NOW, {})
    backup = tmp_path.parent/(tmp_path.name+'-original')
    journal.path.parent.rename(backup)
    shutil.copytree(backup, journal.path.parent)
    reopened = MassiveSessionEventSource(SessionJournalRoot(tmp_path, EPOCH))
    result = reopened.prepare_events(NOW, first['cursor'])
    assert result['diagnostics'] and result['cursor'] == first['cursor'] and not result['events']
    with pytest.raises(SourceUnavailable): journals.prepare_session(OLD, ['AAPL'])


def test_copied_epoch_root_requires_explicit_migration(tmp_path):
    import shutil
    parent = tmp_path/'original'; parent.mkdir(mode=0o700)
    journals = root(parent); journals.ensure_session(OLD, ['AAPL'])(None, gap(OLD))
    copied = tmp_path/'copied'; shutil.copytree(parent, copied)
    for create in (False, True):
        with pytest.raises(SourceUnavailable): SessionJournalRoot(copied, EPOCH, create=create)


def test_session_source_event_limit_preserves_group_horizon_and_frozen_head(tmp_path):
 journals=root(tmp_path);journal=journals.ensure_session(OLD,['AAPL'])
 for n in range(20):journal(None,gap(OLD,number=n))
 source=MassiveSessionEventSource(journals);cursor={};snapshot=None;seen=[]
 for size in (7,7,6):
  page=source.prepare_events(NOW,cursor,snapshot=snapshot,event_limit=7)
  assert not page['diagnostics'] and len(page['events'])==size
  seen.extend(e['sequence'] for e in page['events'])
  if page['has_more']:assert page['page']['cutoff_received_at']=='2026-09-28T13:59:59.999999+00:00'
  cursor=page['cursor'];snapshot=page['snapshot']
 assert seen==list(range(20)) and cursor['sessions']=={OLD:20}
 for invalid in (True,0,-1,4097):
  page=source.prepare_events(NOW,{},event_limit=invalid)
  assert page['diagnostics'] and not page['events'] and page['cursor']=={}
