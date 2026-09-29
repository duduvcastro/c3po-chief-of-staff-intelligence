import pytest
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_retention import plan_retention
from app.r2d2_v2_sources import SourceUnavailable
from test_r2d2_v2_massive_spool import evidence


def gap(session, i):
 return {'event': {'type':'DATA_GAP','session':session,'fixture':i}}


def test_plan_keeps_ack_predecessor_and_all_unacknowledged_receipts(tmp_path):
 j=MassiveJournal(tmp_path)
 for i in range(5):j(None,gap('2026-09-25',i))
 before=j.path.read_bytes()
 p=plan_retention(j,committed_sequence=3,retain_from_session='2026-09-27')
 assert p['prune_through']==2 and len(p['receipt_sha256s'])==2
 assert p['verified_records']==5 and p['status']=='REVIEW_ONLY_NO_DELETION'
 assert j.path.read_bytes()==before and j.page()['through']==5
 assert len(list((tmp_path/'receipts').iterdir()))==5


def test_plan_keeps_recent_sessions_and_shared_raw(tmp_path):
 j=MassiveJournal(tmp_path);raw,r=evidence()
 old={**r,'event':{**r['event'],'session':'2026-09-24'}}
 recent={**r,'event':{**r['event'],'session':'2026-09-26'}}
 j(raw,old);j(raw,recent);j(None,gap('2026-09-27',1))
 p=plan_retention(j,committed_sequence=3,retain_from_session='2026-09-26')
 assert p['prune_through']==1 and p['raw_sha256s']==[]


def test_plan_lists_unreferenced_raw_only(tmp_path):
 j=MassiveJournal(tmp_path);raw,r=evidence()
 j(raw,{**r,'event':{**r['event'],'session':'2026-09-24'}})
 j(None,gap('2026-09-27',1))
 p=plan_retention(j,committed_sequence=2,retain_from_session='2026-09-26')
 assert p['raw_sha256s']==[r['raw_sha256']]
 assert (tmp_path/'raw'/(r['raw_sha256']+'.json')).exists()


@pytest.mark.parametrize('ack',[True,-1,4])
def test_invalid_or_ahead_ack_refuses(tmp_path,ack):
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-25',0))
 with pytest.raises(SourceUnavailable,match='RETENTION_ACK'):
  plan_retention(j,committed_sequence=ack,retain_from_session='2026-09-26')


def test_zero_ack_removes_nothing(tmp_path):
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-25',0))
 assert plan_retention(j,committed_sequence=0,retain_from_session='2026-09-26')['prune_through']==0


def test_reversed_session_refuses(tmp_path):
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-26',0));j(None,gap('2026-09-25',1))
 with pytest.raises(SourceUnavailable,match='SESSION_REVERSED'):
  plan_retention(j,committed_sequence=2,retain_from_session='2026-09-27')


def test_append_during_plan_refuses(tmp_path,monkeypatch):
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-25',0));original=j._page_locked
 def page(*args,**kwargs):
  result=original(*args,**kwargs)
  if args[0]==0:j(None,gap('2026-09-25',1))
  return result
 monkeypatch.setattr(j,'_page_locked',page)
 with pytest.raises(SourceUnavailable,match='SNAPSHOT_CHANGED'):
  plan_retention(j,committed_sequence=1,retain_from_session='2026-09-27')


def test_record_budget_refuses(tmp_path):
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-25',0));j(None,gap('2026-09-25',1))
 with pytest.raises(SourceUnavailable,match='RETENTION_LIMIT'):
  plan_retention(j,committed_sequence=2,retain_from_session='2026-09-27',max_records=1)


def prune_fixture(journal, through):
 # Fixture-only simulation of a future atomic maintenance transaction.
 with journal._connect() as db:
  db.execute('DELETE FROM receipts WHERE sequence<=?',(through,))
  db.execute('UPDATE retention_state SET pruned_through=? WHERE singleton=1',(through,))


def test_retained_floor_refuses_old_cursor_and_preserves_monotonic_ids(tmp_path):
 j=MassiveJournal(tmp_path)
 for i in range(5):j(None,gap('2026-09-25',i))
 prune_fixture(j,2)
 assert j.retention_floor()==2
 with pytest.raises(ValueError,match='CURSOR_PRUNED'):j.page(0)
 assert [r['sequence'] for r in j.page(2)['records']]==[3,4,5]
 assert j(None,gap('2026-09-26',6))==6
 p=plan_retention(j,committed_sequence=5,retain_from_session='2026-09-26')
 assert p['previous_floor']==2 and p['prune_through']==4
 assert len(p['receipt_sha256s'])==2


def test_missing_prefix_without_retention_state_is_corruption(tmp_path):
 j=MassiveJournal(tmp_path)
 for i in range(3):j(None,gap('2026-09-25',i))
 with j._connect() as db:db.execute('DELETE FROM receipts WHERE sequence=1')
 with pytest.raises(ValueError,match='SEQUENCE_GAP'):j.page(1)


def test_missing_retention_row_is_not_silently_zero(tmp_path):
 j=MassiveJournal(tmp_path)
 with j._connect() as db:db.execute('DELETE FROM retention_state')
 with pytest.raises(ValueError,match='RETENTION_STATE'):j.page()
 with pytest.raises(ValueError,match='RETENTION_STATE'):MassiveJournal(tmp_path)


def test_old_source_cursor_refuses_without_advancement(tmp_path):
 from app.r2d2_v2_massive_source import MassiveEventSource
 from test_r2d2_v2_minute_bars import MINUTE
 j=MassiveJournal(tmp_path)
 for i in range(3):j(None,gap('2026-09-25',i))
 prune_fixture(j,1)
 cursor={'massive_sequence':0}
 result=MassiveEventSource(j).prepare_events(MINUTE,cursor)
 assert result['events']==[] and result['cursor']==cursor
 assert result['diagnostics']==[{'code':'MASSIVE_SOURCE_UNVERIFIED'}]


def test_ack_older_than_retention_floor_refuses(tmp_path):
 j=MassiveJournal(tmp_path)
 for i in range(3):j(None,gap('2026-09-25',i))
 prune_fixture(j,1)
 with pytest.raises(SourceUnavailable,match='ACK_PRUNED'):
  plan_retention(j,committed_sequence=0,retain_from_session='2026-09-26')


def test_ack_requires_persistent_verified_store():
 from app.r2d2_v2_massive_retention import read_committed_ack
 from app.r2d2_v2_store import MemoryShadowStore
 with pytest.raises(SourceUnavailable,match='PERSISTENT_STORE_REQUIRED'):
  read_committed_ack(MemoryShadowStore(),epoch='not-used',release_sha='0'*64)


def test_durable_session_cutoff_rejects_old_reingestion_before_spool(tmp_path,monkeypatch):
 j=MassiveJournal(tmp_path)
 for i in range(3):j(None,gap('2026-09-25',i))
 with j._connect() as db:
  db.execute('DELETE FROM receipts WHERE sequence<=2')
  db.execute("UPDATE retention_state SET pruned_through=2,retain_from_session='2026-09-26'")
 reopened=MassiveJournal(tmp_path);original_spool=reopened.spool
 def forbidden(*args):pytest.fail('old receipt reached spool')
 monkeypatch.setattr(reopened,'spool',forbidden)
 with pytest.raises(ValueError,match='SESSION_PRUNED'):reopened(None,gap('2026-09-25',0))
 monkeypatch.setattr(reopened,'spool',original_spool)
 assert reopened.page(2)['through']==3
 fresh=MassiveJournal(tmp_path)
 assert fresh(None,gap('2026-09-26',4))==4
 assert fresh.page(2)['records'][0]['receipt']['event']['session']=='2026-09-25'


@pytest.mark.parametrize('cutoff',['2026-99-99','not-a-date',20260926])
def test_invalid_cutoff_refuses_reopen(tmp_path,cutoff):
 j=MassiveJournal(tmp_path)
 with j._connect() as db:db.execute('UPDATE retention_state SET retain_from_session=?',(cutoff,))
 with pytest.raises(ValueError,match='RETENTION_STATE'):MassiveJournal(tmp_path)


@pytest.mark.parametrize('requested',['2026-09-25','2026-09-26','2026-09-27'])
def test_retention_cutoff_cannot_move_backwards(tmp_path,requested):
 j=MassiveJournal(tmp_path)
 j(None,gap('2026-09-26',0))
 with j._connect() as db:
  db.execute("UPDATE retention_state SET retain_from_session='2026-09-26'")
 if requested<'2026-09-26':
  with pytest.raises(ValueError,match='CUTOFF_REVERSED'):
   plan_retention(j,committed_sequence=1,retain_from_session=requested)
 else:
  plan=plan_retention(j,committed_sequence=1,retain_from_session=requested)
  assert plan['previous_cutoff']=='2026-09-26'
 assert j.retention_cutoff()=='2026-09-26'
 assert j.retention_floor()==0


def test_retention_plan_under_exclusive_boundary_reads_raw_and_rejects_other_reader(tmp_path):
 from app.r2d2_v2_massive_maintenance import journal_access
 from app.r2d2_v2_massive_retention import _plan_retention_locked
 j=MassiveJournal(tmp_path);raw,r=evidence()
 j(raw,{**r,'event':{**r['event'],'session':'2026-09-24'}})
 j(None,gap('2026-09-27',1))
 reader=MassiveJournal.open_reader(tmp_path)
 before=j.path.read_bytes()
 with journal_access(tmp_path,exclusive=True):
  plan=_plan_retention_locked(j,committed_sequence=2,retain_from_session='2026-09-26')
  assert plan['prune_through']==1 and plan['raw_sha256s']==[r['raw_sha256']]
  with pytest.raises(SourceUnavailable,match='MAINTENANCE_BUSY'):reader.page()
 assert j.path.read_bytes()==before
 assert reader.page()['through']==2


def ack_snapshot_fixture(cursor, *, matching=True):
 # Isolate parser checks behind a synthetic verified-read boundary. This is
 # not a PostgreSQL durability/provenance proof.
 import hashlib
 from app.r2d2_v2_store import PostgresShadowStore
 from app.r2d2_v2_sources import canonical
 store=PostgresShadowStore(lambda:pytest.fail('read-only parser must not connect/write'))
 row={'state':{'release_sha':'a'*64,'raw_source_cursor':cursor},'state_sha':'b'*64,'journal_head':'c'*64}
 records=[{'payload':{'type':'SOURCE_CURSOR','cursor':cursor,
  'cursor_sha256':hashlib.sha256(canonical(cursor)).hexdigest()},'record_sha':'d'*64}] if matching else []
 store.read_with_journal=lambda epoch:(row,records)
 return store,row,records


def v2_ack_cursor():
 return {'version':2,'quote_trade':{'files':{}},'massive':{'massive_sequence':3},
  'barrier':{'sequence':0,'resolved':{'US:AAPL|2026-09-28|2026-09-28T14:00:00+00:00':{
   'end_at':'2026-09-28T14:01:00+00:00','event_id':'massive-fixture','envelope_sha256':'e'*64}}}}


@pytest.mark.parametrize('version',[0,1,2])
def test_ack_extractor_preserves_standalone_v1_and_strict_v2(version):
 from app.r2d2_v2_massive_retention import read_committed_ack
 cursor=v2_ack_cursor()
 if version==1:cursor.pop('barrier');cursor['version']=1
 if version==0:cursor=cursor['massive']
 store,_,_=ack_snapshot_fixture(cursor)
 ack=read_committed_ack(store,epoch='fixture',release_sha='a'*64)
 assert ack['committed_sequence']==3 and ack['ack_record_sha256']=='d'*64
 assert ack['status']=='VERIFIED_ACK_OBSERVATION_NOT_DELETION_AUTHORITY'


@pytest.mark.parametrize('malformation',[
 'extra','boolean_version','negative_ack','boolean_ack','extra_massive','missing_barrier',
 'extra_barrier','boolean_barrier_sequence','bad_proof','bad_hash','bad_end','bad_raw','bad_file','missing_ack_record'])
def test_malformed_v2_ack_cannot_start_retention_plan_or_mutate_journal(tmp_path,monkeypatch,malformation):
 import copy
 from datetime import datetime,timezone
 from app import r2d2_v2_massive_retention as retention
 cursor=v2_ack_cursor();proof=next(iter(cursor['barrier']['resolved'].values()))
 if malformation=='extra':cursor['extra']=True
 elif malformation=='boolean_version':cursor['version']=True
 elif malformation=='negative_ack':cursor['massive']['massive_sequence']=-1
 elif malformation=='boolean_ack':cursor['massive']['massive_sequence']=True
 elif malformation=='extra_massive':cursor['massive']['extra']=0
 elif malformation=='missing_barrier':cursor.pop('barrier')
 elif malformation=='extra_barrier':cursor['barrier']['extra']=0
 elif malformation=='boolean_barrier_sequence':cursor['barrier']['sequence']=True
 elif malformation=='bad_proof':proof['extra']=0
 elif malformation=='bad_hash':proof['envelope_sha256']='bad'
 elif malformation=='bad_end':proof['end_at']='2026-09-28T14:02:00+00:00'
 elif malformation=='bad_raw':cursor['quote_trade']=[]
 elif malformation=='bad_file':cursor['quote_trade']={'files':{'file':{'offset':True}}}
 store,row,records=ack_snapshot_fixture(cursor,matching=malformation!='missing_ack_record')
 snapshot=copy.deepcopy((row,records))
 journal=MassiveJournal(tmp_path);journal(None,gap('2026-09-25',0))
 before=journal.path.read_bytes()
 monkeypatch.setattr(retention,'_plan_retention_locked',lambda *a,**k:pytest.fail('invalid ACK reached planner'))
 with pytest.raises(SourceUnavailable):
  retention.plan_committed_retention(journal,store,epoch='fixture',release_sha='a'*64,
   now=datetime(2026,9,29,tzinfo=timezone.utc),retain_from_session='2026-09-26')
 assert (row,records)==snapshot and journal.path.read_bytes()==before
 assert journal.page()['through']==1 and journal.retention_floor()==0
