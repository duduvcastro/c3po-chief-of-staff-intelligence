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
 j=MassiveJournal(tmp_path);j(None,gap('2026-09-25',0));original=j.page
 def page(*args,**kwargs):
  result=original(*args,**kwargs)
  if args[0]==0:j(None,gap('2026-09-25',1))
  return result
 monkeypatch.setattr(j,'page',page)
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
