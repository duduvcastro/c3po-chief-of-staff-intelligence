from datetime import timedelta
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_events import record
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource


def test_source_read_is_not_acknowledgement_and_restart_reoffers(tmp_path,calendar):
 record(tmp_path,calendar);source=MassiveEventSource(MassiveJournal(tmp_path));now=MINUTE+timedelta(seconds=70)
 first=source.prepare_events(now,{})
 assert first['diagnostics']==[] and len(first['events'])==1
 assert MassiveEventSource(MassiveJournal(tmp_path)).prepare_events(now,{})==first
 assert not source.prepare_events(now,first['cursor'])['events']
 assert first['raw_receipts'][first['events'][0]['event_id']]==first['events'][0]['envelope_sha256']


def test_unrelated_cursor_not_silently_reset(tmp_path):
 source=MassiveEventSource(MassiveJournal(tmp_path));cursor={'files':{'existing':123}}
 result=source.prepare_events(MINUTE,cursor)
 assert result['diagnostics'] and result['cursor']==cursor and not result['events']


def test_missing_raw_preserves_cursor(tmp_path,calendar):
 r=record(tmp_path,calendar);(tmp_path/'raw'/(r['receipt']['raw_sha256']+'.json')).unlink()
 result=MassiveEventSource(MassiveJournal(tmp_path)).prepare_events(MINUTE+timedelta(seconds=70),{})
 assert result['diagnostics'] and result['cursor']=={} and result['events']==[]


def test_reversed_reception_across_pages_does_not_advance(tmp_path,calendar):
 record(tmp_path,calendar);j=MassiveJournal(tmp_path)
 j(None,{'event':{'type':'DATA_GAP','at':MINUTE.isoformat(),
   'available_at':(MINUTE+timedelta(seconds=64)).isoformat(),
   'session':MINUTE.date().isoformat(),'instrument_key':'US:AAPL','reason':'fixture'}})
 cursor={'massive_sequence':1}
 result=MassiveEventSource(j).prepare_events(MINUTE+timedelta(seconds=70),cursor)
 assert result['diagnostics'] and result['cursor']==cursor and not result['events']


def test_cursor_predecessor_corruption_refuses_following_page(tmp_path,calendar):
 r=record(tmp_path,calendar);j=MassiveJournal(tmp_path)
 (tmp_path/'receipts'/(r['receipt_sha256']+'.json')).write_bytes(b'{}')
 cursor={'massive_sequence':1}
 result=MassiveEventSource(j).prepare_events(MINUTE+timedelta(seconds=70),cursor)
 assert result['diagnostics'] and result['cursor']==cursor


def test_corrupt_journal_database_refuses_without_advancing_cursor(tmp_path,calendar):
 record(tmp_path,calendar)
 reader=MassiveJournal.open_reader(tmp_path.resolve())
 (tmp_path/'sequence.sqlite3').write_bytes(b'not a sqlite database')
 cursor={'massive_sequence':1}
 result=MassiveEventSource(reader).prepare_events(MINUTE+timedelta(seconds=70),cursor)
 assert result==dict(events=[],diagnostics=[{'code':'MASSIVE_SOURCE_UNVERIFIED'}],cursor=cursor)


def test_missing_journal_schema_refuses_without_advancing_cursor(tmp_path,calendar):
 import sqlite3
 record(tmp_path,calendar)
 reader=MassiveJournal.open_reader(tmp_path.resolve())
 with sqlite3.connect(tmp_path/'sequence.sqlite3') as db:
  db.execute('DROP TABLE receipts')
 cursor={'massive_sequence':1}
 result=MassiveEventSource(reader).prepare_events(MINUTE+timedelta(seconds=70),cursor)
 assert result==dict(events=[],diagnostics=[{'code':'MASSIVE_SOURCE_UNVERIFIED'}],cursor=cursor)
