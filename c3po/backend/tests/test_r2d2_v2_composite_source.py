from datetime import timedelta
from test_r2d2_v2_raw_source import source,write,line,AT,NOW
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_composite_source import CompositeEventSource


def test_real_readers_combine_and_reoffer_until_ack(source,tmp_path):
 write(source,line())
 j=MassiveJournal(tmp_path/'massive')
 j(None,{'event':{'type':'DATA_GAP','at':AT.isoformat(),'available_at':AT.isoformat(),
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


def test_common_horizon_holds_back_later_bar_feed_receipt(source,tmp_path,monkeypatch):
 from app import r2d2_v2_raw_source as raw
 monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',2)
 write(source,line()+line(received=AT+timedelta(seconds=1))+line(received=AT+timedelta(seconds=2)))
 j=MassiveJournal(tmp_path/'massive');received=AT+timedelta(seconds=1.5)
 j(None,{'event':{'type':'DATA_GAP','at':received.isoformat(),'available_at':received.isoformat(),
    'session':AT.date().isoformat(),'instrument_key':'US:SYNTH','reason':'fixture'}})
 c=CompositeEventSource(source,MassiveEventSource(j))
 first=c.prepare_events(NOW,{})
 assert not first['diagnostics'] and len(first['events'])==2
 assert first['cursor']['massive']=={'massive_sequence':0} and first['has_more']
 second=c.prepare_events(NOW,first['cursor'],snapshot=first['snapshot'])
 assert not second['diagnostics'] and len(second['events'])==2
 assert second['cursor']['massive']=={'massive_sequence':1} and not second['has_more']
