"""Independent real-journal proof: suffix receipt rollback must prevent early timeout."""
from datetime import timedelta
import pytest
from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_sources import canonical,_load_json
from test_r2d2_v2_raw_source import source,write,line,AT
from test_r2d2_v2_composite_source import prior_bar


class OneRecord:
    minute_bar_enabled=True
    def __init__(self,reader):self.reader=reader
    def prepare_events(self,*args,**kwargs):
        kwargs['event_limit']=1
        return self.reader.prepare_events(*args,**kwargs)


@pytest.mark.parametrize('indexed',[False,True])
def test_unread_suffix_minimum_receipt_prevents_early_gap_through_restart(source,tmp_path,indexed):
    minute=AT.replace(hour=14,minute=0,second=0,microsecond=0)
    deadline=minute+timedelta(seconds=150)
    now=deadline+timedelta(seconds=5)
    write(source,line(at=minute+timedelta(seconds=60)))
    if indexed:
        root=tmp_path/'indexed';root.mkdir(mode=0o700)
        journals=SessionJournalRoot(root,'clock-review',create=True)
        journal=journals.ensure_session(minute.date().isoformat(),['SYNTH','MSFT'])
        def reader():return MassiveSessionEventSource(SessionJournalRoot(root,'clock-review'))
    else:
        root=tmp_path/'scalar';journal=MassiveJournal(root)
        def reader():return MassiveEventSource(MassiveJournal(root))
    # The next receipt is NOT the suffix minimum: the target BAR is two pages
    # ahead and arrives 5 ms before its deadline after a receipt-clock rollback.
    for number,receipt in enumerate((deadline,deadline+timedelta(seconds=1))):
        journal(None,{'event':{'type':'DATA_GAP','at':minute.isoformat(),
            'available_at':receipt.isoformat(),'session':minute.date().isoformat(),
            'instrument_key':'US:MSFT','reason':'UNRELATED-'+str(number)}})
    target_received=deadline-timedelta(milliseconds=5)
    prior_bar(journal,start=minute,received=target_received)
    cursor={};offers=[]
    for index in range(3):
        composite=CompositeEventSource(source,OneRecord(reader()))
        page=composite.prepare_events(now,cursor)
        assert not page['diagnostics']
        assert not any(e.get('reason')=='BAR_WAIT_TIMEOUT' for e in page['events'])
        assert page==composite.prepare_events(now,cursor)  # read is not ACK
        if index<2:
            assert not any(e['type']=='QUOTE' for e in page['events'])
            assert len(page['cursor']['barrier']['pending_raw'])==1 and page['has_more']
        else:
            assert {e['type'] for e in page['events']}=={'BAR','QUOTE'}
            actual=next(e for e in page['events'] if e['type']=='BAR')
            assert actual['available_at']==target_received.isoformat()  # never clamp the clock
            assert not page['cursor']['barrier']['pending_raw'] and not page['has_more']
        offers.extend(page['events'])
        cursor=_load_json(canonical(page['cursor']))  # durable JSON/reopen seam
    assert len(offers)==4


def test_paused_bar_reader_keeps_hidden_earlier_suffix_horizon(source,tmp_path,monkeypatch):
    minute=AT.replace(hour=14,minute=0,second=0,microsecond=0)
    deadline=minute+timedelta(seconds=150);now=deadline+timedelta(seconds=5)
    write(source,line(at=minute+timedelta(seconds=60)))
    journal=MassiveJournal(tmp_path/'paused')
    journal(None,{'event':{'type':'DATA_GAP','at':minute.isoformat(),
        'available_at':(deadline+timedelta(seconds=1)).isoformat(),
        'session':minute.date().isoformat(),'instrument_key':'US:MSFT','reason':'UNRELATED'}})
    prior_bar(journal,start=minute,received=deadline-timedelta(milliseconds=5))
    composite=CompositeEventSource(source,OneRecord(MassiveEventSource(journal)))
    fits=composite._fits
    # Model exhausted BAR ingestion headroom while keeping room for retained
    # references/gap records. Limits and actual frontier logic remain unchanged.
    monkeypatch.setattr(composite,'_fits',lambda *a,ingest=False,**k:False if ingest else fits(*a,**k))
    paused=composite.prepare_events(now,{})
    assert not paused['diagnostics']
    assert not paused['events']  # Offered receipt >deadline is not the unread minimum.
    assert len(paused['cursor']['barrier']['pending_raw'])==1 and paused['has_more']
    assert paused['cursor']['massive']=={}
    monkeypatch.setattr(composite,'_fits',fits)
    first=composite.prepare_events(now,_load_json(canonical(paused['cursor'])))
    assert not first['diagnostics'] and not any(e.get('reason')=='BAR_WAIT_TIMEOUT' for e in first['events'])
    final=composite.prepare_events(now,_load_json(canonical(first['cursor'])))
    assert not final['diagnostics'] and {e['type'] for e in final['events']}=={'BAR','QUOTE'}
    assert not final['cursor']['barrier']['pending_raw']
