"""Real collector cycle and durable Massive reader; synthetic local data only.

This proves the standalone port transaction, not composite feed integration.
"""
import json
import time
from datetime import datetime,timedelta,timezone
import pytest
from tests.test_r2d2_v2_shadow_counterexamples import setup_state,INSTRUMENT
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from test_r2d2_v2_raw_source import source, line, PART
from app.r2d2_v2_composite_source import CompositeEventSource

START=datetime(2026,9,8,15,0,tzinfo=timezone.utc)


def setup(tmp_path):
 collector,state,_=setup_state()
 state['coverage_until'][INSTRUMENT]=START.isoformat()
 collector.store.atomic(collector.release.epoch,collector._initial(),lambda unused:(state,[],{}),START)
 journal=MassiveJournal(tmp_path)
 stream=MassiveStreamState(['SYNTH'],collector.calendar,journal);stream.connected(START-timedelta(seconds=1))
 stream.frame(json.dumps([dict(ev='AM',sym='SYNTH',s=int(START.timestamp()*1000),
   e=int((START+timedelta(minutes=1)).timestamp()*1000),o=100,h=101,l=99,c=100,v=10)]).encode(),START+timedelta(seconds=65))
 collector.source=MassiveEventSource(journal)
 return collector


def test_cycle_commits_receipts_and_cursor_and_reader_restart_deduplicates(tmp_path):
 collector=setup(tmp_path);now=START+timedelta(seconds=66)
 collector.cycle(now)
 saved=collector.store.read(collector.release.epoch)['state']
 assert saved['raw_source_cursor']=={'massive_sequence':1}
 records=collector.store.journal(collector.release.epoch)
 assert len([r for r in records if r['payload']['type']=='SOURCE_EVENT'])==1
 assert len([r for r in records if r['payload']['type']=='SOURCE_CURSOR'])==1
 collector.source=MassiveEventSource(MassiveJournal(tmp_path))
 collector.cycle(now+timedelta(seconds=1))
 assert len([r for r in collector.store.journal(collector.release.epoch) if r['payload']['type']=='SOURCE_EVENT'])==1


def test_failed_collector_transaction_keeps_input_replayable(tmp_path,monkeypatch):
 collector=setup(tmp_path);atomic=collector.store.atomic
 def fail(epoch,initial,transition,now):
  def rollback(state):
   transition(state)
   raise RuntimeError('fixture transaction failure')
  return atomic(epoch,initial,rollback,now)
 monkeypatch.setattr(collector.store,'atomic',fail)
 with pytest.raises(RuntimeError):collector.cycle(START+timedelta(seconds=66))
 assert collector.store.read(collector.release.epoch)['state'].get('raw_source_cursor',{})=={}
 monkeypatch.setattr(collector.store,'atomic',atomic)
 collector.cycle(START+timedelta(seconds=67))
 assert collector.store.read(collector.release.epoch)['state']['raw_source_cursor']=={'massive_sequence':1}


@pytest.mark.parametrize('minutes',[3,10])
@pytest.mark.parametrize('interruption',['missing_minute','producer_restart'])
def test_550_symbol_frames_real_cycle_over_90s_gap_and_late_bar(tmp_path,record_property,source,interruption,minutes):
 from app.r2d2_v2_portfolio import PortfolioBatch
 from tests.test_r2d2_v2_shadow_counterexamples import geometry
 collector,state,session=setup_state()
 names=['SYNTH']+['S'+str(i) for i in range(549)]
 batch=PortfolioBatch(state['ledger'])
 for name in names[1:]:
  key='fixture-'+name;instrument='US:'+name
  batch.register(episode_key=key,instrument_key=instrument,session=START.date().isoformat(),
    opened_at=START.isoformat(),maturity_at='2026-09-08T19:55:00+00:00',geometry=geometry(),arm='ELIGIBLE')
  state['watch_episodes'][key]=instrument
  state['instrument_episodes'][instrument]=[key]
 state['ledger']=batch.finish()
 session['universe']=['US:'+name for name in names]
 for name in names:state['coverage_until']['US:'+name]=START.isoformat()
 collector.store.atomic(collector.release.epoch,collector._initial(),lambda unused:(state,[],{}),START)
 massive_root=tmp_path/'massive'
 journal=MassiveJournal(massive_root)
 stream=MassiveStreamState(names,collector.calendar,journal);stream.connected(START-timedelta(seconds=1))
 collector.source=CompositeEventSource(source,MassiveEventSource(journal))
 def frame(minute):
  return json.dumps([dict(ev='AM',sym=name,s=int(minute.timestamp()*1000),
   e=int((minute+timedelta(minutes=1)).timestamp()*1000),o=100,h=101,l=99,c=100,v=10) for name in names]).encode()
 from app.r2d2_v2_massive_scheduler import MinuteExpiry
 expiry=MinuteExpiry(stream,START)
 for i in range(minutes):
  minute=START+timedelta(minutes=i);received=minute+timedelta(seconds=65)
  for feed in ('quote','trade'):
   path=source.raw_root/PART.replace('quote',feed)
   with path.open('ab') as output:output.write(line(100,feed=feed,at=received))
   path.chmod(0o600)
  raw=frame(minute);started=time.perf_counter()
  stream.frame(raw,received);expiry(received);collector.cycle(received+timedelta(seconds=1))
  elapsed=time.perf_counter()-started
  record_property('local_frame550_cycle_seconds_'+str(i),elapsed)
  assert elapsed < 24, 'local frame-to-cycle budget exceeded'
  assert len(stream.seen)+len(stream.sealed)<=550*4
  saved=collector.store.read(collector.release.epoch)['state']
  assert saved['raw_source_cursor']['massive']=={'massive_sequence':550*(i+1)}
  assert saved['ledger']['research']['synthetic-entry'].get('category')!='unobservable', (saved['data_issues'],saved['ledger']['research']['synthetic-entry'])
  assert len(saved['ledger']['research'])==550
  assert all(r.get('category')!='unobservable' and r['status']=='OPEN' for r in saved['ledger']['research'].values())
  assert not saved['data_issues']
 record_property('indexed_bar_receipts',550*minutes)
 record_property('spool_bytes',journal.spool.used_bytes)
 record_property('spool_files',journal.spool.used_files)
 record_property('index_bytes',journal.path.stat().st_size)
 assert journal.spool.used_bytes<=512*1024*1024
 assert journal.spool.used_files<=500000
 assert journal.path.stat().st_size<=64*1024*1024
 missing=START+timedelta(minutes=minutes);detected=missing+timedelta(seconds=91)
 if interruption=='producer_restart':
  from app.r2d2_v2_massive_producer import run_producer
  class StoppedSocket:
   def send(self,value):pass
   def close(self):pass
  result=run_producer(massive_root.resolve(),names,collector.calendar,'offline-fixture',
    utcnow=lambda:detected,monotonic=lambda:0,stop=lambda:True,
    connector=lambda *args,**kwargs:StoppedSocket())
  assert result=={'status':'STOPPED','recovered_records':550*minutes}
  collector.source=CompositeEventSource(source,MassiveEventSource(MassiveJournal.open_reader(massive_root.resolve())))
 else:
  stream.expire_minute(missing,detected)
 collector.cycle(detected+timedelta(seconds=1))
 saved=collector.store.read(collector.release.epoch)['state']
 assert all(r['category']=='unobservable' for r in saved['ledger']['research'].values())
 consumed_before=len([r for r in collector.store.journal(collector.release.epoch) if r['payload']['type']=='SOURCE_EVENT'])
 collector.cycle(detected+timedelta(seconds=2))
 assert len([r for r in collector.store.journal(collector.release.epoch) if r['payload']['type']=='SOURCE_EVENT'])==consumed_before
 before=journal.page()['through']
 if interruption=='producer_restart':
  from app.r2d2_v2_massive_recovery import restore_stream
  from app.r2d2_v2_sources import SourceUnavailable
  stream=MassiveStreamState(names,collector.calendar,journal)
  restore_stream(stream,journal,session=START.date().isoformat(),now=detected)
  stream.connected(detected)
  with pytest.raises(SourceUnavailable,match='MINUTE_CONNECTION_GAP'):
   stream.frame(frame(missing),detected+timedelta(seconds=2))
 else:
  stream.frame(frame(missing),detected+timedelta(seconds=2))
 assert journal.page()['through']==before
 collector.cycle(detected+timedelta(seconds=3))
 assert collector.store.read(collector.release.epoch)['state']['ledger']['research']['synthetic-entry']['category']=='unobservable'
