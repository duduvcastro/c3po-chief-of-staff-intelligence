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


def test_large_equal_receipt_group_progresses_in_bounded_persistent_pages(tmp_path):
 import sqlite3
 from app.r2d2_v2_sources import canonical, _load_json
 journal=MassiveJournal(tmp_path/'journal')
 received=MINUTE+timedelta(seconds=70)
 for index in range(4100):
  journal(None,{'event':{'type':'DATA_GAP','at':MINUTE.isoformat(),
   'available_at':received.isoformat(),'session':MINUTE.date().isoformat(),
   'instrument_key':'US:AAPL','reason':'persistent-adversary-'+str(index)}})
 source=MassiveEventSource(MassiveJournal.open_reader((tmp_path/'journal').resolve()))
 first=source.prepare_events(received,{})
 assert first['diagnostics']==[] and len(first['events'])==4096 and first['has_more']
 assert first['cursor']=={'massive_sequence':4096}
 assert first['page']['cutoff_received_at']==(received-timedelta(microseconds=1)).isoformat()
 # Simulate the durable consumer transaction. A rollback cannot acknowledge
 # the proposed page: a new reader must offer the exact same immutable input.
 dbpath=tmp_path/'consumer.sqlite3'
 with sqlite3.connect(dbpath) as db:
  db.execute('CREATE TABLE applied (event_id TEXT PRIMARY KEY)')
  db.execute('CREATE TABLE checkpoint (cursor BLOB NOT NULL)')
  db.execute('INSERT INTO checkpoint VALUES (?)',(canonical({}),))
 with sqlite3.connect(dbpath) as db:
  db.executemany('INSERT INTO applied VALUES (?)',[(event['event_id'],) for event in first['events']])
  db.execute('UPDATE checkpoint SET cursor=?',(canonical(first['cursor']),))
  db.rollback()
 with sqlite3.connect(dbpath) as db:
  cursor=_load_json(db.execute('SELECT cursor FROM checkpoint').fetchone()[0])
 with sqlite3.connect(dbpath) as db:
  assert db.execute('SELECT COUNT(*) FROM applied').fetchone()[0]==0
 restarted=MassiveEventSource(MassiveJournal.open_reader((tmp_path/'journal').resolve()))
 assert restarted.prepare_events(received,cursor,snapshot=first['snapshot'])==first
 with sqlite3.connect(dbpath) as db:
  db.executemany('INSERT INTO applied VALUES (?)',[(event['event_id'],) for event in first['events']])
  db.execute('UPDATE checkpoint SET cursor=?',(canonical(first['cursor']),))
 with sqlite3.connect(dbpath) as db:
  cursor=_load_json(db.execute('SELECT cursor FROM checkpoint').fetchone()[0])
  assert db.execute('SELECT COUNT(*) FROM applied').fetchone()[0]==4096
 tail=restarted.prepare_events(received,cursor,snapshot=first['snapshot'])
 assert tail['diagnostics']==[] and len(tail['events'])==4 and not tail['has_more']
 assert tail['cursor']=={'massive_sequence':4100}
 assert tail['page']['cutoff_received_at'] is None
 assert [event['sequence'] for page in (first,tail) for event in page['events']]==list(range(4100))
 # A corrupt tail cannot skip its failed record or consume the proposal.
 digest=journal.page(4096,limit=1)['records'][0]['receipt_sha256']
 (tmp_path/'journal'/'receipts'/(digest+'.json')).write_bytes(b'{}')
 failed=restarted.prepare_events(received,cursor,snapshot=first['snapshot'])
 assert failed['diagnostics'] and failed['events']==[] and failed['cursor']==cursor


def test_explicit_event_limit_splits_same_receipt_without_ack_skip(tmp_path):
 journal=MassiveJournal(tmp_path);received=MINUTE+timedelta(seconds=65)
 for number in range(20):
  journal(None,{'event':{'type':'DATA_GAP','at':MINUTE.isoformat(),'available_at':received.isoformat(),
   'session':MINUTE.date().isoformat(),'instrument_key':'US:AAPL','reason':'limit-'+str(number)}})
 source=MassiveEventSource(journal);cursor={};sequences=[]
 for size in (7,7,6):
  page=source.prepare_events(received,cursor,event_limit=7)
  assert not page['diagnostics'] and len(page['events'])==size
  sequences.extend(e['sequence'] for e in page['events'])
  if page['has_more']:
   assert page['page']['cutoff_received_at']==(received-timedelta(microseconds=1)).isoformat()
  cursor=page['cursor']
 assert sequences==list(range(20)) and cursor=={'massive_sequence':20}
 for invalid in (True,0,-1,4097):
  result=source.prepare_events(received,{},event_limit=invalid)
  assert result['diagnostics'] and not result['events'] and result['cursor']=={}
