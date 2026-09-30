"""Real PostgreSQL proof; opt-in disposable loopback database only, no fallback."""
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import pytest
import test_r2d2_v2_massive_collector as cases
from test_r2d2_v2_raw_source import source
from app.r2d2_v2_store import PostgresShadowStore

@pytest.fixture
def pg_factory():
 dsn=os.environ.get('C3PO_BAR_TEST_DATABASE_URL')
 if not dsn:pytest.skip('Disposable local PostgreSQL is not configured; no persistent-store proof')
 import psycopg
 from psycopg.conninfo import conninfo_to_dict
 from psycopg import sql
 info=conninfo_to_dict(dsn)
 if info.get('host') not in ('127.0.0.1','::1') or info.get('dbname')!='c3po_bar_test':
  pytest.fail('Only explicit loopback c3po_bar_test disposable database is allowed')
 schema='bar_proof_'+uuid4().hex
 with psycopg.connect(dsn) as conn:
  conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
  conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
  conn.execute((Path(__file__).parents[2]/'db/045_r2d2_v2_shadow.sql').read_text())
 @contextmanager
 def connect():
  with psycopg.connect(dsn) as conn:
   conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   yield conn
 try:yield connect
 finally:
  with psycopg.connect(dsn) as conn:
   conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

class InspectablePostgresStore(PostgresShadowStore):
 # Test convenience only; mutations use the unchanged production store.
 def journal(self,epoch):return self.read_with_journal(epoch)[1]

@pytest.mark.parametrize('interruption',['missing_minute','producer_restart'])
def test_persistent_550_ten_minute_cycle(tmp_path,record_property,source,interruption,pg_factory,monkeypatch):
 original=cases.setup_state
 def setup():
  collector,state,session=original()
  collector.store=InspectablePostgresStore(pg_factory)
  return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 cases.test_550_symbol_frames_real_cycle_over_90s_gap_and_late_bar(
  tmp_path,record_property,source,interruption,10)


def test_backend_loss_before_commit_rolls_back_cursor_and_receipts(tmp_path,pg_factory,monkeypatch):
 from datetime import timedelta
 original=cases.setup_state
 def setup():
  collector,state,session=original();collector.store=InspectablePostgresStore(pg_factory)
  return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 collector=cases.setup(tmp_path);epoch=collector.release.epoch
 before=collector.store.read_with_journal(epoch)
 @contextmanager
 def fail_before_commit():
  with pg_factory() as conn:
   class Connection:
    def execute(self,*a,**kw):return conn.execute(*a,**kw)
    def commit(self):
     pid=conn.info.backend_pid
     with pg_factory() as control:
      assert control.execute('SELECT pg_terminate_backend(%s)',(pid,)).fetchone()[0]
     conn.commit()
   yield Connection()
 collector.store=InspectablePostgresStore(fail_before_commit)
 import psycopg
 with pytest.raises(psycopg.Error):collector.cycle(cases.START+timedelta(seconds=66))
 collector.store=InspectablePostgresStore(pg_factory)
 assert collector.store.read_with_journal(epoch)==before
 collector.cycle(cases.START+timedelta(seconds=67))
 row,records=collector.store.read_with_journal(epoch)
 assert row['state']['raw_source_cursor']=={'massive_sequence':1}
 assert len([r for r in records if r['payload']['type']=='SOURCE_EVENT'])==1
 collector.store=InspectablePostgresStore(pg_factory)
 collector.cycle(cases.START+timedelta(seconds=68))
 assert len([r for r in collector.store.journal(epoch) if r['payload']['type']=='SOURCE_EVENT'])==1



def test_550_mid_cycle_backend_loss_then_new_connection_replay(tmp_path,record_property,source,pg_factory,monkeypatch):
 import psycopg
 original=cases.setup_state
 injections=[]
 def setup():
  collector,state,session=original()
  collector.store=InspectablePostgresStore(pg_factory)
  cycle=collector.cycle
  calls=0
  def restarted_cycle(now):
   nonlocal calls
   calls+=1
   if calls!=5:return cycle(now)
   epoch=collector.release.epoch
   before=collector.store.read_with_journal(epoch)
   assert before[0]['state']['raw_source_cursor']['massive']['massive_sequence']==2200
   assert len(before[0]['state']['ledger']['research'])==550
   attempted=[]
   @contextmanager
   def interrupted():
    with pg_factory() as conn:
     class Connection:
      def execute(self,sql,params=None):
       if 'INSERT INTO r2d2_v2_shadow_journal' in sql:attempted.append(params)
       return conn.execute(sql,params)
      def commit(self):
       with pg_factory() as control:
        assert control.execute('SELECT pg_terminate_backend(%s)',(conn.info.backend_pid,)).fetchone()[0]
       conn.commit()
     yield Connection()
   collector.store=InspectablePostgresStore(interrupted)
   with pytest.raises(psycopg.Error):cycle(now)
   collector.store=InspectablePostgresStore(pg_factory)
   assert collector.store.read_with_journal(epoch)==before
   assert len(attempted)>=550
   replayed=[]
   @contextmanager
   def reconnected():
    with pg_factory() as conn:
     class Connection:
      def execute(self,sql,params=None):
       if 'INSERT INTO r2d2_v2_shadow_journal' in sql:replayed.append(params)
       return conn.execute(sql,params)
      def commit(self):conn.commit()
     yield Connection()
   collector.store=InspectablePostgresStore(reconnected)
   response=cycle(now)
   assert replayed==attempted # Sequence, clock, payload and hash chain identical.
   collector.store=InspectablePostgresStore(pg_factory)
   after=collector.store.read_with_journal(epoch)
   assert after[0]['state']['raw_source_cursor']['massive']['massive_sequence']==2750
   assert len(after[0]['state']['ledger']['research'])==550
   injections.append(len(replayed))
   return response
  collector.cycle=restarted_cycle
  return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 cases.test_550_symbol_frames_real_cycle_over_90s_gap_and_late_bar(tmp_path,record_property,source,'missing_minute',10)
 assert len(injections)==1
 record_property('rolled_back_and_exactly_replayed_journal_rows',injections[0])



def test_550_off_session_disconnect_reconnect_preserves_durable_gap(tmp_path,record_property,source,pg_factory,monkeypatch):
 import json
 from datetime import timedelta
 from app.r2d2_v2_massive_journal import MassiveJournal
 from app.r2d2_v2_massive_stream import MassiveStreamState
 from app.r2d2_v2_massive_recovery import restore_stream
 original=cases.setup_state;captured=[]
 def setup():
  collector,state,session=original();collector.store=InspectablePostgresStore(pg_factory)
  captured.append(collector);return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 cases.test_550_symbol_frames_real_cycle_over_90s_gap_and_late_bar(tmp_path,record_property,source,'missing_minute',10)
 collector=captured[0];epoch=collector.release.epoch
 names=['SYNTH']+['S'+str(i) for i in range(549)]
 journal=MassiveJournal(tmp_path/'massive')
 before=journal.page()['through']
 persisted_before=collector.store.read_with_journal(epoch)
 source_events_before=[r for r in persisted_before[1] if r['payload']['type']=='SOURCE_EVENT']
 off=cases.START.replace(hour=21)
 stream=MassiveStreamState(names,collector.calendar,journal)
 restore_stream(stream,journal,session=cases.START.date().isoformat(),now=off)
 stream.connected(off);stream.gap(off+timedelta(seconds=1),'DISCONNECTED')
 assert stream.connected_at is None and journal.page()['through']==before
 stream.connected(off+timedelta(seconds=2))
 missing=cases.START+timedelta(minutes=10)
 raw=json.dumps([dict(ev='AM',sym=n,s=int(missing.timestamp()*1000),e=int((missing+timedelta(minutes=1)).timestamp()*1000),o=100,h=101,l=99,c=100,v=10) for n in names]).encode()
 stream.frame(raw,off+timedelta(seconds=3))
 assert journal.page()['through']==before
 collector.cycle(off+timedelta(seconds=4))
 after,records=collector.store.read_with_journal(epoch)
 assert [r for r in records if r['payload']['type']=='SOURCE_EVENT']==source_events_before
 assert after['state']['raw_source_cursor']['massive']==persisted_before[0]['state']['raw_source_cursor']['massive']
 assert all(r['category']=='unobservable' for r in after['state']['ledger']['research'].values())
 record_property('off_session_new_source_events',0)
 record_property('durable_unobservable_episodes',550)


def test_retention_ack_reads_real_committed_state_and_rejects_wrong_release(tmp_path,pg_factory,monkeypatch):
 from datetime import timedelta
 from app.r2d2_v2_massive_retention import read_committed_ack
 from app.r2d2_v2_sources import SourceUnavailable
 original=cases.setup_state
 def setup():
  collector,state,session=original();collector.store=InspectablePostgresStore(pg_factory)
  return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 collector=cases.setup(tmp_path);epoch=collector.release.epoch
 collector.cycle(cases.START+timedelta(seconds=66))
 before=collector.store.read_with_journal(epoch)
 release_sha=before[0]['state']['release_sha']
 ack=read_committed_ack(collector.store,epoch=epoch,release_sha=release_sha)
 assert ack['committed_sequence']==1
 assert ack['state_sha256']==before[0]['state_sha']
 assert ack['journal_head']==before[0]['journal_head']
 assert collector.store.read_with_journal(epoch)==before
 wrong=('0' if release_sha[0]!='0' else '1')+release_sha[1:]
 with pytest.raises(SourceUnavailable,match='RELEASE_MISMATCH'):
  read_committed_ack(collector.store,epoch=epoch,release_sha=wrong)


def test_retention_binds_local_evidence_not_just_equal_numeric_ack(tmp_path,pg_factory,monkeypatch):
 from datetime import timedelta
 from app.r2d2_v2_massive_retention import plan_committed_retention
 from app.r2d2_v2_massive_journal import MassiveJournal
 from app.r2d2_v2_sources import SourceUnavailable
 original=cases.setup_state
 def setup():
  collector,state,session=original();collector.store=InspectablePostgresStore(pg_factory)
  return collector,state,session
 monkeypatch.setattr(cases,'setup_state',setup)
 collector=cases.setup(tmp_path/'source');epoch=collector.release.epoch
 now=cases.START+timedelta(seconds=66);collector.cycle(now)
 before=collector.store.read_with_journal(epoch)
 kwargs=dict(epoch=epoch,release_sha=before[0]['state']['release_sha'],now=now,retain_from_session='2026-09-09')
 journal=collector.source.journal
 plan=plan_committed_retention(journal,collector.store,**kwargs)
 assert plan['verified_committed_receipts']==1 and plan['prune_through']==0
 assert plan['status']=='ONE_CONSUMER_BOUND_REVIEW_ONLY_NO_DELETION'
 assert collector.store.read_with_journal(epoch)==before
 receipt=journal.page()['records'][0]['receipt']
 raw=journal._read_evidence('raw',receipt['raw_sha256']+'.json',receipt['raw_bytes'],'FIXTURE_RAW')
 unrelated=MassiveJournal(tmp_path/'unrelated')
 assert unrelated(raw,{**receipt,'fixture_identity':'different'})==1
 with pytest.raises(SourceUnavailable,match='LOCAL_ACK_MISMATCH'):
  plan_committed_retention(unrelated,collector.store,**kwargs)
 assert unrelated.page()['through']==1 and journal.page()['through']==1


def test_session_index_backend_loss_reoffers_two_local_sequences_and_restart(tmp_path,source,pg_factory):
 """Opt-in real PostgreSQL; session-local1/1 survive one atomic rollback."""
 from datetime import timedelta
 import psycopg
 from app.r2d2_v2_shadow import ShadowCollector
 from app.r2d2_v2_composite_source import CompositeEventSource
 from app.r2d2_v2_massive_sessions import SessionJournalRoot
 from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
 from app.r2d2_v2_massive_retention import read_committed_ack,plan_committed_retention
 from test_r2d2_v2_shadow_counterexamples import setup_state,DAY
 from test_r2d2_v2_raw_source import write
 write(source,b'')  # Observed empty capture; no missing-source diagnostic.
 collector,state,session=setup_state(position=False)
 epoch=collector.release.epoch
 state['ledger']['session']=DAY
 collector.store=InspectablePostgresStore(pg_factory)
 collector.store.atomic(epoch,collector._initial(),lambda unused:(state,[],{}),cases.START)
 root=tmp_path/'session-journals';root.mkdir(mode=0o700)
 catalog=SessionJournalRoot(root,epoch,create=True)
 days=['2026-09-04',DAY]
 journals={}
 for day in days:
  journal=catalog.ensure_session(day,['SYNTH']);journals[day]=journal
  at=day+'T14:00:00+00:00'
  assert journal(None,{'event':{'type':'DATA_GAP','session':day,'instrument_key':'US:SYNTH',
      'at':at,'available_at':at,'reason':'synthetic-session-proof'}})==1
 collector.source=CompositeEventSource(source,MassiveSessionEventSource(catalog))
 before=collector.store.read_with_journal(epoch)
 now=cases.START+timedelta(seconds=66)
 proposed=collector.source.prepare_events(now,{})
 assert not proposed['diagnostics'] and len(proposed['events'])==1 and proposed['has_more']
 assert proposed['events'][0]['sequence']==0
 assert proposed['cursor']['massive']=={'version':2,'epoch':epoch,'sessions':{days[0]:1,DAY:0}}
 attempted=[]
 @contextmanager
 def interrupt_commit():
  with pg_factory() as conn:
   class Connection:
    def execute(self,sql,params=None):
     if 'INSERT INTO r2d2_v2_shadow_journal' in sql:attempted.append(params)
     return conn.execute(sql,params)
    def commit(self):
     with pg_factory() as control:
      assert control.execute('SELECT pg_terminate_backend(%s)',(conn.info.backend_pid,)).fetchone()[0]
     conn.commit()
   yield Connection()
 collector.store=InspectablePostgresStore(interrupt_commit)
 with pytest.raises(psycopg.Error):collector.cycle(now)
 collector.store=InspectablePostgresStore(pg_factory)
 assert collector.store.read_with_journal(epoch)==before
 assert collector.source.prepare_events(now,{})==proposed
 replayed=[]
 @contextmanager
 def reconnect():
  with pg_factory() as conn:
   class Connection:
    def execute(self,sql,params=None):
     if 'INSERT INTO r2d2_v2_shadow_journal' in sql:replayed.append(params)
     return conn.execute(sql,params)
    def commit(self):conn.commit()
   yield Connection()
 collector.store=InspectablePostgresStore(reconnect)
 collector.cycle(now)
 assert attempted and replayed==attempted
 collector.store=InspectablePostgresStore(pg_factory)
 committed,records=collector.store.read_with_journal(epoch)
 assert committed['state']['raw_source_cursor']==proposed['cursor']
 events=[record for record in records if record['payload']['type']=='SOURCE_EVENT']
 assert len(events)==1
 restarted=ShadowCollector(InspectablePostgresStore(pg_factory),
     CompositeEventSource(source,MassiveSessionEventSource(SessionJournalRoot(root,epoch))),
     collector.release,calendar=collector.calendar)
 tail=restarted.source.prepare_events(now+timedelta(seconds=1),proposed['cursor'])
 assert not tail['diagnostics'] and len(tail['events'])==1 and not tail['has_more']
 assert tail['events'][0]['sequence']==0
 assert tail['events'][0]['source_id']!=proposed['events'][0]['source_id']
 restarted.cycle(now+timedelta(seconds=1))
 after,records=restarted.store.read_with_journal(epoch)
 assert after['state']['raw_source_cursor']['massive']=={'version':2,'epoch':epoch,'sessions':{day:1 for day in days}}
 events=[record for record in records if record['payload']['type']=='SOURCE_EVENT']
 assert len(events)==2 and {record['payload']['source']['sequence'] for record in events}=={0}
 assert len({record['payload']['source']['source_id'] for record in events})==2
 ack=read_committed_ack(restarted.store,epoch=epoch,release_sha=collector.release.receipt_sha)
 assert ack['committed_sessions']=={day:1 for day in days} and 'committed_sequence' not in ack
 for day in days:
  plan=plan_committed_retention(journals[day],restarted.store,epoch=epoch,
      release_sha=collector.release.receipt_sha,now=now+timedelta(seconds=1),retain_from_session='2026-09-09',session=day)
  assert plan['verified_committed_receipts']==1 and plan['committed_sequence']==1
  assert plan['journal_session']==day and plan['prune_through']==0
 restarted.cycle(now+timedelta(seconds=2))
 final,records=restarted.store.read_with_journal(epoch)
 assert final['state']['raw_source_cursor']['massive']==after['state']['raw_source_cursor']['massive']
 assert len([record for record in records if record['payload']['type']=='SOURCE_EVENT'])==2
 assert all(journal.page()['through']==1 for journal in journals.values())
