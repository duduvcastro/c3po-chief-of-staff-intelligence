from datetime import timedelta
from test_r2d2_v2_raw_source import source,write,line,AT,NOW,PART
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_composite_source import CompositeEventSource


def test_real_readers_combine_and_reoffer_until_ack(source,tmp_path):
 write(source,line())
 j=MassiveJournal(tmp_path/'massive')
 j(None,{'event':{'type':'DATA_GAP','at':(AT.replace(second=0)-timedelta(minutes=1)).isoformat(),'available_at':AT.isoformat(),
    'session':AT.date().isoformat(),'instrument_key':'US:SYNTH','reason':'fixture'}})
 combined=CompositeEventSource(source,MassiveEventSource(j))
 first=combined.prepare_events(NOW,{})
 assert not first['diagnostics'] and {e['type'] for e in first['events']}=={'QUOTE','DATA_GAP'}
 assert first==combined.prepare_events(NOW,{})
 assert not combined.prepare_events(NOW,first['cursor'])['events']


def test_legacy_cursor_is_refused_without_silent_reset(source,tmp_path):
 c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
 cursor={'files':{}}
 result=c.prepare_events(NOW,cursor)
 assert result['diagnostics'] and result['cursor']==cursor


def test_raw_pagination_cannot_hide_later_bar_feed_receipt(source,tmp_path,monkeypatch):
 from app import r2d2_v2_raw_source as raw
 monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2)
 write(source,line()+line(received=AT+timedelta(seconds=1))+line(received=AT+timedelta(seconds=2)))
 j=MassiveJournal(tmp_path/'massive');received=AT+timedelta(seconds=1.5)
 j(None,{'event':{'type':'DATA_GAP','at':(AT.replace(second=0)-timedelta(minutes=1)).isoformat(),'available_at':received.isoformat(),
    'session':AT.date().isoformat(),'instrument_key':'US:SYNTH','reason':'fixture'}})
 c=CompositeEventSource(source,MassiveEventSource(j))
 first=c.prepare_events(NOW,{})
 assert not first['diagnostics'] and len(first['events'])==3
 assert first['cursor']['massive']=={'massive_sequence':1} and first['has_more']
 second=c.prepare_events(NOW,first['cursor'],snapshot=first['snapshot'])
 assert not second['diagnostics'] and len(second['events'])==1
 assert second['cursor']['massive']=={'massive_sequence':1} and not second['has_more']


def prior_bar(journal, *, instrument='US:SYNTH', start=None, received=NOW):
 start=start or AT.replace(second=0)-timedelta(minutes=1)
 raw=b'synthetic-am-proof'
 from hashlib import sha256
 journal(raw,{'raw_sha256':sha256(raw).hexdigest(),'raw_bytes':len(raw),'event':{'type':'BAR','at':start.isoformat(),'end_at':(start+timedelta(minutes=1)).isoformat(),
    'available_at':received.isoformat(),'session':start.date().isoformat(),'instrument_key':instrument,
    'open':100.,'high':101.,'low':99.,'close':100.,'regular':True,'coverage_complete':True}})


def test_trade_waits_across_restart_without_child_cursor_advance(source,tmp_path):
 write(source,line(feed='trade'),PART.replace('quote','trade'))
 j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j))
 held=c.prepare_events(NOW,{})
 assert not held['diagnostics'] and not held['events'] and not held['has_more']
 assert held['cursor']['quote_trade'].get('sequence',0)==0
 assert not held['raw_receipts']
 prior_bar(j)
 c=CompositeEventSource(source,MassiveEventSource(j))
 released=c.prepare_events(NOW,held['cursor'])
 assert not released['diagnostics'] and {e['type'] for e in released['events']}=={'BAR','TRADE'}
 assert released==c.prepare_events(NOW,held['cursor'])
 assert not c.prepare_events(NOW,released['cursor'])['events']


def test_timeout_is_explicit_gap_before_release_and_not_a_bar(source,tmp_path):
 write(source,line())
 c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
 deadline=AT.replace(second=0)+timedelta(seconds=90)
 held=c.prepare_events(deadline,{})
 assert not held['events']
 expired=deadline+timedelta(microseconds=1)
 released=c.prepare_events(expired,held['cursor'])
 assert not released['diagnostics']
 assert [e['type'] for e in released['events']]==['DATA_GAP','QUOTE']
 assert released['events'][0]['reason']=='BAR_WAIT_TIMEOUT'
 assert released['events'][0]['available_at']==deadline.isoformat()
 assert c.prepare_events(expired+timedelta(seconds=1),held['cursor'])['events']==released['events']
 assert not c.prepare_events(expired,released['cursor'])['events']


def test_other_instrument_or_session_bar_cannot_unblock(source,tmp_path):
 write(source,line())
 j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j))
 prior_bar(j,instrument='US:OTHER')
 prior_bar(j,start=AT.replace(second=0)-timedelta(days=1,minutes=1))
 held=c.prepare_events(NOW,{})
 assert not held['diagnostics'] and all(e['type']=='BAR' for e in held['events'])
 assert not held['raw_receipts'].keys() - {e['event_id'] for e in held['events']}


def test_child_append_deferral_is_preserved_without_advancing_any_cursor(source,tmp_path):
 write(source,line()[:-4])
 c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
 result=c.prepare_events(NOW,{})
 assert result['diagnostics']==[{'code':'RAW_APPEND_IN_PROGRESS'}]
 assert result['cursor']=={} and not result['events']


def test_cursor_limits_and_version_are_fail_closed(source,tmp_path):
 c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
 for barrier in ({'resolved':{},'sequence':True},{'resolved':{'x':'bad'},'sequence':0}):
  cursor={'version':2,'quote_trade':{},'massive':{},'barrier':barrier}
  result=c.prepare_events(NOW,cursor)
  assert result['diagnostics'] and result['cursor']==cursor


def test_split_receipt_group_holds_quote_until_tail_and_retains_bounded_proofs(source):
 write(source,line(received=NOW))
 start=(AT.replace(second=0)-timedelta(minutes=1)).isoformat()
 class MassivePages:
  def prepare_events(self,now,cursor,**kwargs):
   first=not cursor
   numbers=range(4096) if first else range(4096,4100) if cursor['massive_sequence']==4096 else []
   events=[{'event_id':f'gap-{n}','type':'DATA_GAP','instrument_key':'US:SYNTH' if n==0 else f'US:NAME{n}',
       'session':AT.date().isoformat(),'at':start,'available_at':NOW.isoformat(),
       'envelope_sha256':'a'*64,'reason':'fixture'} for n in numbers]
   return {'events':events,'diagnostics':[],'cursor':{'massive_sequence':4096 if first else 4100},
       'snapshot':{'massive_through':4100},'has_more':first,'raw_receipts':{},
       'page':{'cutoff_received_at':(NOW-timedelta(microseconds=1)).isoformat() if first else None}}
 c=CompositeEventSource(source,MassivePages())
 first=c.prepare_events(NOW,{})
 assert not first['diagnostics'] and len(first['events'])==4096
 assert all(e['type']=='DATA_GAP' for e in first['events']) and first['has_more']
 assert len(first['cursor']['barrier']['resolved'])==4096
 second=c.prepare_events(NOW,first['cursor'],snapshot=first['snapshot'])
 assert not second['diagnostics'] and len(second['events'])==5
 assert sum(e['type']=='QUOTE' for e in second['events'])==1 and not second['has_more']


def test_session_root_adapter_preserves_local_cursors_and_cannot_cross_unblock(source,tmp_path):
 from app.r2d2_v2_massive_sessions import SessionJournalRoot
 from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
 root=tmp_path/'sessions';root.mkdir(mode=0o700)
 epoch='R2D2-V2-SHADOW-SESSION-FIXTURE'
 journals=SessionJournalRoot(root,epoch,create=True)
 old=journals.ensure_session('2026-09-04',['SYNTH'])
 previous=(AT.replace(second=0)-timedelta(days=4,minutes=1))
 old(None,{'event':{'type':'DATA_GAP','session':'2026-09-04','at':previous.isoformat(),
     'available_at':previous.isoformat(),'instrument_key':'US:SYNTH','reason':'synthetic-old-gap'}})
 current=journals.ensure_session(AT.date().isoformat(),['SYNTH'])
 write(source,line())
 c=CompositeEventSource(source,MassiveSessionEventSource(journals))
 first=c.prepare_events(NOW,{})
 assert not first['diagnostics'] and len(first['events'])==1
 assert first['events'][0]['session']=='2026-09-04'
 assert first['cursor']['massive']['sessions']['2026-09-04']==1
 assert all(e['type']!='QUOTE' for e in first['events'])
 prior_bar(current)
 rebuilt=CompositeEventSource(source,MassiveSessionEventSource(SessionJournalRoot(root,epoch)))
 second=rebuilt.prepare_events(NOW,first['cursor'])
 assert not second['diagnostics'] and {e['type'] for e in second['events']}=={'BAR','QUOTE'}
 assert second['cursor']['massive']['sessions']=={'2026-09-04':1,'2026-09-08':1}
 assert not rebuilt.prepare_events(NOW,second['cursor'])['events']
 assert old.page()['through']==1 and current.page()['through']==1
