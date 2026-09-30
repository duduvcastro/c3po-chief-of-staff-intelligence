"""Pressure-triggered scope compaction keeps physical accounting and source generations."""
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_massive_source import MassiveEventSource
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_retention import read_committed_ack
from app.r2d2_v2_sources import canonical
from test_r2d2_v2_raw_source import source, write, line, PART, AT, NOW
from test_r2d2_v2_composite_scoped import tick
from test_r2d2_v2_composite_source import prior_bar
from test_r2d2_v2_massive_retention import ack_snapshot_fixture


def test_closed_sessions_fold_below_small_scope_cap_and_replay(source,tmp_path,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j));cursor={}
    ids=[]
    for day in range(3):
        at=AT+timedelta(days=day);part=PART.replace('2026-09-08',at.date().isoformat())
        (source.raw_root/part).parent.mkdir(exist_ok=True)
        write(source,tick('AAPL',at=at)+tick('MSFT',at=at),part)
        prior_bar(j,instrument='US:AAPL',start=at.replace(second=0)-timedelta(minutes=1),received=at)
        prior_bar(j,instrument='US:MSFT',start=at.replace(second=0)-timedelta(minutes=1),received=at)
        page=c.prepare_events(at+timedelta(seconds=1),cursor)
        assert not page['diagnostics']
        assert page==c.prepare_events(at+timedelta(seconds=1),json.loads(canonical(cursor)))
        cursor=json.loads(canonical(page['cursor']))
        assert len(cursor['barrier']['scope_sequences'])==0
        assert len(cursor['barrier'].get('file_bases',{}))==day+1
        CompositeEventSource._validate_scoped(cursor['barrier'],retained=cursor['quote_trade'])
        ids.extend(e['source_id'] for e in page['events'] if e['type']=='QUOTE')
        c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    assert len(ids)==len(set(ids))==6
    store,_,_=ack_snapshot_fixture(cursor)
    assert read_committed_ack(store,epoch='fixture',release_sha='a'*64)['committed_sequence']==6


def test_late_append_after_fold_uses_committed_generation(source,tmp_path,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    write(source,line());j=MassiveJournal(tmp_path/'massive');prior_bar(j)
    c=CompositeEventSource(source,MassiveEventSource(j));first=c.prepare_events(NOW,{})
    original=next(e for e in first['events'] if e['type']=='QUOTE')
    closed=AT.replace(hour=20,minute=1,second=0)
    folded=c.prepare_events(closed,first['cursor'])
    assert not folded['diagnostics'] and folded['cursor']['barrier']['scope_sequences']=={}
    assert folded['cursor']['barrier']['file_bases']=={PART:1}
    with (source.raw_root/PART).open("ab") as stream:stream.write(line(price=102))
    restored=json.loads(canonical(folded['cursor']))
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    late=c.prepare_events(closed+timedelta(seconds=1),restored)
    assert not late['diagnostics']
    assert late==c.prepare_events(closed+timedelta(seconds=1),restored)
    quote=next(e for e in late['events'] if e['type']=='QUOTE')
    assert quote['sequence']==0 and quote['source_id']!=original['source_id']
    assert quote['event_id']!=original['event_id']
    assert late['cursor']['barrier']['file_bases']=={PART:2}
    assert late['cursor']['quote_trade']==late['cursor']['barrier']['read_cursor']
    assert not c.prepare_events(closed+timedelta(seconds=2),late['cursor'])['events']


def test_pending_reference_prevents_fold(source,tmp_path,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));page=c.prepare_events(NOW,{})
    b=page['cursor']['barrier'];scopes=deepcopy(b['scope_sequences']);bases={}
    c._fold_scopes(scopes,bases,b['pending_raw'],b['read_cursor'],AT+timedelta(days=1))
    assert scopes==b['scope_sequences'] and bases=={}
    assert page['cursor']['quote_trade']['files'][PART]['offset']==0
    c._fold_scopes(scopes,bases,{},b['read_cursor'],NOW)
    assert scopes=={} and bases=={PART:1}


@pytest.mark.parametrize('change',['count','unknown_file','boolean'])
def test_folded_accounting_tampering_refuses(source,tmp_path,change,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    write(source,line());j=MassiveJournal(tmp_path/'massive');prior_bar(j)
    c=CompositeEventSource(source,MassiveEventSource(j));now=AT+timedelta(hours=1)
    cursor=c.prepare_events(now,{})['cursor']
    if change=='count':cursor['barrier']['file_bases'][PART]+=1
    elif change=='boolean':cursor['barrier']['file_bases'][PART]=True
    else:cursor['barrier']['file_bases']['unknown']=1
    page=c.prepare_events(now,cursor)
    assert page['diagnostics'] and page['events']==[] and page['cursor']==cursor


def test_file_base_cap_refuses_without_advance(source,tmp_path,monkeypatch):
    write(source,line());j=MassiveJournal(tmp_path/'massive');prior_bar(j)
    c=CompositeEventSource(source,MassiveEventSource(j))
    monkeypatch.setattr(CompositeEventSource,'MAX_FILE_BASES',0)
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    refused=c.prepare_events(AT+timedelta(hours=1),{})
    assert refused['diagnostics']==[{'code':'COMPOSITE_FILE_BASE_LIMIT'}]
    assert refused['events']==[] and refused['cursor']=={}


def test_reoffer_crossing_close_preserves_existing_scope_event_identity(source,tmp_path,monkeypatch):
    monkeypatch.setattr(CompositeEventSource,'MAX_RAW_SCOPES',2)
    write(source,line());j=MassiveJournal(tmp_path/'massive');prior_bar(j)
    c=CompositeEventSource(source,MassiveEventSource(j));first=c.prepare_events(NOW,{})
    with (source.raw_root/PART).open('ab') as stream:stream.write(line(price=102))
    before=c.prepare_events(NOW,first['cursor'])
    after=c.prepare_events(AT+timedelta(hours=1),first['cursor'],snapshot=before['snapshot'])
    assert not before['diagnostics'] and not after['diagnostics']
    assert before['events']==after['events']
    assert next(e for e in after['events'] if e['type']=='QUOTE')['sequence']==0
