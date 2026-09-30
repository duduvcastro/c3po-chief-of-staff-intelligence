"""Independent counterexamples: calendar-free folding and order-free gap IDs."""
from datetime import timedelta
from hashlib import sha256
import json
import pytest
from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_sources import canonical
from app.r2d2_v2_shadow import ShadowCollector
from test_r2d2_v2_raw_source import source,write,line,AT,PART


@pytest.mark.parametrize('day',['2026-09-12','2026-11-26'])
def test_empty_weekend_or_holiday_directory_cannot_wedge(source,tmp_path,day):
    path=source.raw_root/PART.replace('2026-09-08',day)
    path.parent.mkdir();path.write_bytes(b'');path.chmod(0o600)
    write(source,line())
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    now=AT.replace(month=int(day[5:7]),day=int(day[8:10]))+timedelta(days=1)
    offered=c.prepare_events(now,{})
    assert not offered['diagnostics'] and any(e['type']=='QUOTE' for e in offered['events'])
    assert not c.prepare_events(now,json.loads(canonical(offered['cursor'])))['diagnostics']


def test_gap_hash_does_not_depend_on_other_timeouts_becoming_due(source,tmp_path):
    paths=[PART.replace('00001',f'{i:05}') for i in range(3)]
    paths.sort(key=lambda p:sha256(p.encode()).hexdigest())
    early=AT.replace(hour=15,minute=0,second=0,microsecond=0)
    write(source,line(at=early+timedelta(minutes=1)).replace(b'SYNTH',b'LATER'),paths[0])
    write(source,line(at=early).replace(b'SYNTH',b'FIRST'),paths[-1])
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    first=c.prepare_events(early+timedelta(seconds=91),{})
    later=c.prepare_events(early+timedelta(seconds=151),{},snapshot=first['snapshot'])
    assert not first['diagnostics'] and not later['diagnostics']
    gap=next(e for e in first['events'] if e['type']=='DATA_GAP')
    replay=next(e for e in later['events'] if e['event_id']==gap['event_id'])
    assert gap==replay and gap['sequence']==0
    assert len([e for e in later['events'] if e['type']=='DATA_GAP'])==2
    state={'event_receipts':{gap['event_id']:gap['envelope_sha256']},'event_sequences':{gap['source_id']:0}}
    missing,_=ShadowCollector._sequence_gap(state,[e for e in later['events'] if e['type']=='DATA_GAP'])
    assert not missing


def test_intraday_many_parts_fold_under_low_scope_cap(source,tmp_path,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    at=AT.replace(hour=15,minute=0,second=0,microsecond=0)
    cursor={};seen=set()
    for index in range(15):
        path=PART.replace('00001',f'{index:05}')
        write(source,b''.join(line(at=at).replace(b'SYNTH',symbol) for symbol in (b'AAPL',b'MSFT')),path)
        now=at+timedelta(seconds=91)
        offered=c.prepare_events(now,cursor)
        assert not offered['diagnostics']
        assert offered==c.prepare_events(now,json.loads(canonical(cursor)))
        delivered=[e for e in offered['events'] if e['type']=='QUOTE']
        assert len(delivered)==2
        assert not seen.intersection(e['event_id'] for e in delivered)
        seen.update(e['event_id'] for e in delivered)
        cursor=json.loads(canonical(offered['cursor']))
        assert not cursor['barrier']['scope_sequences']
        assert len(cursor['barrier']['file_bases'])==index+1
    assert len(seen)==30


@pytest.mark.parametrize('batch_parts',[1,15])
def test_intraday_550_names_15_quote_trade_parts_stays_bounded(source,tmp_path,batch_parts):
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    at=AT.replace(hour=15,minute=0,second=0,microsecond=0)
    cursor={};delivered=set()
    for start in range(0,15,batch_parts):
        for part in range(start,start+batch_parts):
            for feed in ('quote','trade'):
                path=PART.replace('quote',feed).replace('00001',f'{part:05}')
                write(source,b''.join(line(feed=feed,at=at).replace(b'SYNTH',f'S{i:04}'.encode()) for i in range(550)),path)
        offered=c.prepare_events(at+timedelta(seconds=91),cursor)
        assert not offered['diagnostics']
        ticks=[e for e in offered['events'] if e['type'] in ('QUOTE','TRADE')]
        assert len(ticks)==1100*batch_parts
        delivered.update(e['event_id'] for e in ticks)
        cursor=json.loads(canonical(offered['cursor']))
        assert len(cursor['barrier']['scope_sequences'])<=8192
        assert len(canonical(cursor))<=2_000_000
    assert len(delivered)==16500 and 0<len(cursor['barrier']['file_bases'])<=30


def test_550_names_40_minutes_keep_1100_raw_sources_without_poll_generations(source):
    from test_r2d2_v2_composite_backpressure import MassiveBacklog,BASE
    massive=MassiveBacklog();all_rows=massive.rows
    for event in all_rows:
        for key in ('at','end_at','available_at','session'):
            event[key]=event[key].replace('2026-09-28','2026-09-08')
    c=CompositeEventSource(source,massive);base=BASE.replace(day=8);cursor={};sources=set();ticks=0
    for minute in range(40):
        massive.rows=all_rows[:(minute+1)*550]
        at=base+timedelta(seconds=70,minutes=minute)
        for feed in ('quote','trade'):
            path=source.raw_root/PART.replace('quote',feed)
            with path.open('ab') as stream:
                stream.write(b''.join(line(feed=feed,at=at).replace(b'SYNTH',f'S{i}'.encode()) for i in range(550)))
            path.chmod(0o600)
        page=c.prepare_events(at+timedelta(seconds=2),cursor)
        assert not page['diagnostics'] and not any(e['type']=='DATA_GAP' for e in page['events'])
        raw=[e for e in page['events'] if e['type'] in ('QUOTE','TRADE')]
        assert len(raw)==1100
        assert all(e['sequence']==minute for e in raw)
        sources.update(e['source_id'] for e in raw);ticks+=len(raw)
        cursor=page['cursor']
        assert not cursor['barrier'].get('file_bases')
        assert len(canonical(cursor))<=2_000_000
    assert ticks==44000 and len(sources)==1100
    assert len(cursor['barrier']['scope_sequences'])==1100
    assert set(cursor['barrier']['scope_sequences'].values())=={40}
