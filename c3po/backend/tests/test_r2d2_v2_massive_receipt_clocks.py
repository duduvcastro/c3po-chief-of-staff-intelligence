"""Persistent sequence order may differ from the untouched wall receipt clock."""
import json
import sqlite3
from datetime import timedelta
import pytest
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_sources import canonical
from test_r2d2_v2_minute_bars import MINUTE, calendar
from test_r2d2_v2_massive_stream import bar


def fixture(tmp_path,calendar,session):
    if session:
        catalog=SessionJournalRoot(tmp_path,'clock-fixture',create=True)
        journal=catalog.ensure_session(MINUTE.date().isoformat(),['AAPL','MSFT'])
        source=MassiveSessionEventSource(catalog)
    else:
        journal=MassiveJournal(tmp_path)
        source=MassiveEventSource(journal)
    state=MassiveStreamState(['AAPL','MSFT'],calendar,journal)
    state.connected(MINUTE-timedelta(seconds=1))
    first=MINUTE+timedelta(seconds=65)
    second=first-timedelta(milliseconds=5)
    state.frame(json.dumps([bar()]).encode(),first)
    state.frame(json.dumps([{**bar(),'sym':'MSFT'}]).encode(),second)
    return journal,source,first,second


@pytest.mark.parametrize('session',[False,True])
def test_reversed_clock_prefix_horizon_is_suffix_min_and_restart_replays(tmp_path,calendar,session):
    root=tmp_path/'journal';root.mkdir(mode=0o700)
    journal,source,first,second=fixture(root,calendar,session)
    now=first+timedelta(seconds=200)
    hashes=[r['receipt_sha256'] for r in journal.page()['records']]
    one=source.prepare_events(now,{},event_limit=1)
    assert not one['diagnostics'] and len(one['events'])==1 and one['has_more']
    assert one['page']['cutoff_received_at']==(second-timedelta(microseconds=1)).isoformat()
    assert one['events'][0]['available_at']==first.isoformat()
    # Explicit rollback of consumer ACK leaves the entire first page replayable.
    consumer=tmp_path/'consumer.db'
    with sqlite3.connect(consumer) as db:
        db.execute('CREATE TABLE ack (payload BLOB)')
        db.execute('INSERT INTO ack VALUES (?)',(canonical({}),))
    with sqlite3.connect(consumer) as db:
        db.execute('UPDATE ack SET payload=?',(canonical(one['cursor']),))
        db.rollback()
    with sqlite3.connect(consumer) as db:
        cursor=json.loads(db.execute('SELECT payload FROM ack').fetchone()[0])
    if session:
        restarted=MassiveSessionEventSource(SessionJournalRoot(root,'clock-fixture'))
    else:
        restarted=MassiveEventSource(MassiveJournal.open_reader(journal.path.parent))
    assert restarted.prepare_events(now,cursor,event_limit=1,snapshot=one['snapshot'])==one
    two=restarted.prepare_events(now,one['cursor'],event_limit=1,snapshot=one['snapshot'])
    assert not two['diagnostics'] and len(two['events'])==1 and not two['has_more']
    assert two['events'][0]['available_at']==second.isoformat()
    assert [r['receipt_sha256'] for r in journal.page()['records']]==hashes
    # A cutoff between the two clocks cannot skip the first sequence to reach
    # the later-sequenced earlier clock; it must offer an empty unchanged prefix.
    held=restarted.prepare_events(now,{},receipt_cutoff=second,snapshot=one['snapshot'])
    assert not held['diagnostics'] and not held['events']
    assert held['page']['cutoff_received_at']==(second-timedelta(microseconds=1)).isoformat()


def test_suffix_min_covers_beyond_next_page_and_frozen_snapshot(tmp_path,calendar):
    journal,source,first,second=fixture(tmp_path,calendar,False)
    def gap(at,reason):
        return {'event':{'type':'DATA_GAP','at':MINUTE.isoformat(),'available_at':at.isoformat(),
                'session':MINUTE.date().isoformat(),'instrument_key':'US:AAPL','reason':reason}}
    earlier=first-timedelta(seconds=4)
    journal(None,gap(earlier,'deep-suffix'))
    one=source.prepare_events(first+timedelta(seconds=1),{},event_limit=1)
    assert one['page']['cutoff_received_at']==(earlier-timedelta(microseconds=1)).isoformat()
    journal(None,gap(first-timedelta(seconds=5),'after-frozen-head'))
    frozen=source.prepare_events(first+timedelta(seconds=1),{},event_limit=1,snapshot=one['snapshot'])
    assert frozen==one
    fresh=source.prepare_events(first+timedelta(seconds=1),{},event_limit=1)
    assert fresh['page']['cutoff_received_at']==(first-timedelta(seconds=5,microseconds=1)).isoformat()


def test_clock_and_sequence_transaction_roll_back_together_then_retry(tmp_path,calendar):
    journal=MassiveJournal(tmp_path)
    with journal._connect() as db:
        db.execute("CREATE TRIGGER refuse_clock BEFORE INSERT ON receipt_clocks BEGIN SELECT RAISE(ABORT,'clock-fixture'); END")
    receipt={'event':{'type':'DATA_GAP','at':MINUTE.isoformat(),'available_at':MINUTE.isoformat(),
        'session':MINUTE.date().isoformat(),'instrument_key':'US:AAPL','reason':'fixture'}}
    with pytest.raises(sqlite3.IntegrityError,match='clock-fixture'):journal(None,receipt)
    assert journal.page()['through']==0
    with journal._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM receipt_clocks').fetchone()[0]==0
        db.execute('DROP TRIGGER refuse_clock')
    reopened=MassiveJournal(tmp_path)
    assert reopened(None,receipt)==1
    assert len(MassiveEventSource(reopened).prepare_events(MINUTE,{})['events'])==1


def test_legacy_clock_migration_explicit_verified_and_atomic(tmp_path,calendar):
    journal,source,first,second=fixture(tmp_path,calendar,False)
    with journal._connect() as db:db.execute('DROP TABLE receipt_clocks')
    missing=source.prepare_events(first,{})
    assert missing['diagnostics'] and missing['cursor']=={} and not missing['events']
    records=journal.page()['records'];receipt_file=journal.path.parent/'receipts'/(records[1]['receipt_sha256']+'.json')
    original=receipt_file.read_bytes();receipt_file.write_bytes(b'{}')
    with pytest.raises(ValueError,match='HASH'):journal.migrate_receipt_clocks()
    with journal._connect() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='receipt_clocks'").fetchone()
    receipt_file.write_bytes(original)
    assert journal.migrate_receipt_clocks()==2
    assert source.prepare_events(first,{},event_limit=1)['page']['cutoff_received_at']==(second-timedelta(microseconds=1)).isoformat()
    with pytest.raises(ValueError,match='ALREADY_PRESENT'):journal.migrate_receipt_clocks()


@pytest.mark.parametrize('mutation',[
    'DELETE FROM receipt_clocks WHERE sequence=2',
    'UPDATE receipt_clocks SET received_us=received_us+1000 WHERE sequence=2',
    'UPDATE receipt_clocks SET received_us=received_us+2000000 WHERE sequence=2',
])
def test_missing_or_corrupt_suffix_clock_refuses_without_ack(tmp_path,calendar,mutation):
    journal,source,first,second=fixture(tmp_path,calendar,False)
    with journal._connect() as db:db.execute(mutation)
    result=source.prepare_events(first,{},event_limit=1)
    assert result['diagnostics'] and not result['events'] and result['cursor']=={}
