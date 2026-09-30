"""Independent BAR barriers retain raw byte evidence and isolate names/sessions."""
from copy import deepcopy
from datetime import timedelta
import pytest
from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_source import MassiveEventSource
from test_r2d2_v2_raw_source import source,write,line,AT,NOW,PART
from test_r2d2_v2_composite_source import prior_bar


def tick(symbol, **kw):return line(**kw).replace(b'SYNTH',symbol.encode())


def test_missing_symbol_does_not_hold_other_name_or_advance_retention_floor(source,tmp_path):
    first=tick('AAPL');second=tick('MSFT')
    write(source,first+second)
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j))
    page=c.prepare_events(NOW,{})
    assert not page['diagnostics']
    quotes=[e for e in page['events'] if e['type']=='QUOTE']
    assert [e['instrument_key'] for e in quotes]==['US:MSFT']
    assert quotes[0]['sequence']==0
    cursor=page['cursor'];assert cursor['version']==3
    assert cursor['quote_trade']['files'][PART]['offset']==0
    assert cursor['barrier']['read_cursor']['files'][PART]['offset']==len(first+second)
    assert len(cursor['barrier']['pending_raw'])==1
    assert 'bp' not in str(cursor['barrier']['pending_raw'])
    assert page==c.prepare_events(NOW,{})  # rollback/reoffer
    assert not c.prepare_events(NOW,cursor)['events']
    prior_bar(j,instrument='US:AAPL')
    rebuilt=CompositeEventSource(source,MassiveEventSource(j))
    rest=rebuilt.prepare_events(NOW,cursor)
    assert not rest['diagnostics']
    assert [(e['instrument_key'],e['sequence']) for e in rest['events'] if e['type']=='QUOTE']==[('US:AAPL',0)]
    assert rest['cursor']['quote_trade']==rest['cursor']['barrier']['read_cursor']
    assert not rest['cursor']['barrier']['pending_raw']
    assert not rebuilt.prepare_events(NOW,rest['cursor'])['events']


def test_pending_raw_replayed_after_append_and_new_name_sequence_is_contiguous(source,tmp_path):
    path=write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));page=c.prepare_events(NOW,{})
    with path.open('ab') as f:f.write(tick('MSFT',received=AT+timedelta(seconds=1)))
    rest=c.prepare_events(NOW,page['cursor'])
    assert not rest['diagnostics']
    assert [(e['instrument_key'],e['sequence']) for e in rest['events']]==[('US:MSFT',1)]
    assert rest['cursor']['quote_trade']['files'][PART]['offset']==0


@pytest.mark.parametrize('mutation',['frame','inode','missing','locator','hash'])
def test_held_raw_is_reverified_and_corruption_never_advances(source,tmp_path,mutation):
    path=write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));cursor=c.prepare_events(NOW,{})['cursor']
    ref=next(iter(cursor['barrier']['pending_raw'].values()))
    if mutation=='frame':path.write_bytes(path.read_bytes().replace(b'AAPL',b'NVDA'))
    if mutation=='inode':
        other=path.with_suffix('.new');other.write_bytes(path.read_bytes());other.replace(path)
    if mutation=='missing':path.unlink()
    if mutation=='locator':ref['path']='../unsafe'
    if mutation=='hash':ref['raw_sha256']='0'*64
    original=deepcopy(cursor);page=c.prepare_events(NOW,cursor)
    assert page['diagnostics'] and not page['events'] and page['cursor']==original


def test_bounded_pending_backpressure_does_not_invent_data_gap(source,tmp_path,monkeypatch):
    write(source,tick('AAPL')+tick('AAPL',received=AT+timedelta(seconds=1)))
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    monkeypatch.setattr(c,'MAX_PENDING_RAW',1)
    held=c.prepare_events(NOW,{})
    assert not held['diagnostics'] and not held['events']
    assert not held['cursor']['barrier']['pending_raw']
    assert held['cursor']['barrier']['read_cursor']=={}
    end=AT.replace(second=0)
    released=c.prepare_events(end+timedelta(seconds=91),held['cursor'])
    assert not released['diagnostics']
    assert [e['type'] for e in released['events']].count('QUOTE')==2
    assert [e['type'] for e in released['events']].count('DATA_GAP')==1


def test_real_collector_rollback_restart_and_scoped_sequence_receipts(source,tmp_path,monkeypatch):
    from test_r2d2_v2_raw_source import seed_collector
    write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j))
    collector=seed_collector(c)
    before=collector.store.read(collector.release.epoch)
    atomic=collector.store.atomic
    def fail(epoch,initial,transition,now):
        def wrapped(state):
            transition(state)
            raise RuntimeError('scoped rollback')
        return atomic(epoch,initial,wrapped,now)
    monkeypatch.setattr(collector.store,'atomic',fail)
    with pytest.raises(RuntimeError,match='scoped rollback'):collector.cycle(NOW)
    assert collector.store.read(collector.release.epoch)==before
    monkeypatch.setattr(collector.store,'atomic',atomic)
    collector.cycle(NOW)
    state=collector.store.read(collector.release.epoch)['state']
    assert len(state['raw_source_cursor']['barrier']['pending_raw'])==1
    assert not any(i['reason']=='EVENT_SEQUENCE_GAP' for i in state['data_issues'])
    records=collector.store.journal(collector.release.epoch)
    delivered=[r['payload']['source'] for r in records if r['payload']['type']=='SOURCE_EVENT']
    assert [e['instrument_key'] for e in delivered if e['type']=='QUOTE']==['US:MSFT']
    prior_bar(j,instrument='US:AAPL',received=NOW+timedelta(seconds=1))
    collector.source=CompositeEventSource(source,MassiveEventSource(j))
    collector.cycle(NOW+timedelta(seconds=2))
    state=collector.store.read(collector.release.epoch)['state']
    assert not state['raw_source_cursor']['barrier']['pending_raw']
    assert not any(i['reason']=='EVENT_SEQUENCE_GAP' for i in state['data_issues'])
    records=collector.store.journal(collector.release.epoch)
    delivered=[r['payload']['source'] for r in records if r['payload']['type']=='SOURCE_EVENT']
    assert [e['instrument_key'] for e in delivered if e['type']=='QUOTE']==['US:MSFT','US:AAPL']
    assert state['event_receipts']=={}


@pytest.mark.parametrize('malformation',[None,'retention_floor','read_ahead','missing_ref','scope_bool','frame_range'])
def test_retention_accepts_only_accounted_committed_scoped_cursor(source,tmp_path,malformation):
    from test_r2d2_v2_massive_retention import ack_snapshot_fixture
    from app.r2d2_v2_massive_retention import read_committed_ack
    from app.r2d2_v2_sources import SourceUnavailable
    write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));cursor=c.prepare_events(NOW,{})['cursor']
    if malformation=='retention_floor':cursor['quote_trade']=deepcopy(cursor['barrier']['read_cursor'])
    if malformation=='read_ahead':cursor['barrier']['read_cursor']['files'][PART]['sequence']+=1
    if malformation=='missing_ref':cursor['barrier']['pending_raw']={}
    if malformation=='scope_bool':
        key=next(iter(cursor['barrier']['scope_sequences']));cursor['barrier']['scope_sequences'][key]=True
    if malformation=='frame_range':next(iter(cursor['barrier']['pending_raw'].values()))['offset']=10**9
    store,_,_=ack_snapshot_fixture(cursor)
    if malformation:
        with pytest.raises(SourceUnavailable):read_committed_ack(store,epoch='epoch',release_sha='a'*64)
    else:
        ack=read_committed_ack(store,epoch='epoch',release_sha='a'*64)
        assert ack['committed_sequence']==1


def test_same_symbol_sessions_have_independent_barriers_and_sequences(source,tmp_path):
    tomorrow=AT+timedelta(days=1)
    write(source,tick('AAPL'))
    next_part=PART.replace('2026-09-08','2026-09-09')
    (source.raw_root/next_part).parent.mkdir()
    write(source,tick('AAPL',at=tomorrow),next_part)
    j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j))
    page=c.prepare_events(tomorrow+timedelta(seconds=1),{})
    assert not page['diagnostics']
    old=[e for e in page['events'] if e['type']=='QUOTE']
    assert len(old)==1 and old[0]['session']=='2026-09-08' and old[0]['sequence']==0
    assert {r['session'] for r in page['cursor']['barrier']['pending_raw'].values()}=={'2026-09-09'}
    prior_bar(j,instrument='US:AAPL',start=tomorrow.replace(second=0)-timedelta(minutes=1),received=tomorrow)
    rest=c.prepare_events(tomorrow+timedelta(seconds=2),page['cursor'])
    assert not rest['diagnostics']
    new=[e for e in rest['events'] if e['type']=='QUOTE']
    assert len(new)==1 and new[0]['session']=='2026-09-09' and new[0]['sequence']==0
    assert old[0]['source_id']!=new[0]['source_id']


def test_real_scoped_spool_with_550_name_bar_backlog_respects_combined_byte_budget(source,monkeypatch):
    from test_r2d2_v2_composite_backpressure import MassiveBacklog,BASE
    from app import r2d2_v2_raw_source as raw
    from app.r2d2_v2_sources import canonical
    monkeypatch.setattr(raw,'MAX_CYCLE_EVENTS',10)
    massive=MassiveBacklog()
    for event in massive.rows:
        for key in ('at','end_at','available_at','session'):
            event[key]=event[key].replace('2026-09-28','2026-09-08')
    base=BASE.replace(day=8)
    write(source,b''.join(tick('S0',at=base+timedelta(seconds=70+n)) for n in range(1000)))
    c=CompositeEventSource(source,massive);cursor={};ids=set()
    for _ in range(130):
        page=c.prepare_events(base+timedelta(minutes=45),cursor)
        assert not page['diagnostics']
        assert len(canonical(page['cursor']))<=c.MAX_CURSOR_BYTES
        assert not any(e['type']=='DATA_GAP' for e in page['events'])
        for event in page['events']:
            assert event['event_id'] not in ids
            ids.add(event['event_id'])
        assert page['cursor']!=cursor or not page['has_more']
        cursor=page['cursor']
        if not page['has_more']:break
    else:raise AssertionError('scoped spool backlog did not drain')
    assert len(ids)==23000
    assert not cursor['barrier']['pending_raw']


def test_sqlite_durable_cursor_and_receipts_rollback_close_reopen(source,tmp_path):
    import sqlite3
    from app.r2d2_v2_sources import canonical,_load_json
    write(source,tick('AAPL')+tick('MSFT'))
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));dbpath=tmp_path/'scoped-consumer.sqlite'
    db=sqlite3.connect(dbpath)
    db.execute('CREATE TABLE cursor (body BLOB NOT NULL)')
    db.execute('CREATE TABLE receipts (id TEXT PRIMARY KEY, sha TEXT NOT NULL)')
    db.execute('INSERT INTO cursor VALUES (?)',(canonical({}),));db.commit()
    offered=c.prepare_events(NOW,{})
    def persist(page):
        db.execute('UPDATE cursor SET body=?',(canonical(page['cursor']),))
        db.executemany('INSERT INTO receipts VALUES (?,?)',page['raw_receipts'].items())
    persist(offered);db.rollback()
    assert _load_json(db.execute('SELECT body FROM cursor').fetchone()[0])=={}
    assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==0
    assert c.prepare_events(NOW,{})==offered
    persist(offered);db.commit();db.close()
    db=sqlite3.connect(dbpath)
    durable=_load_json(db.execute('SELECT body FROM cursor').fetchone()[0])
    c=CompositeEventSource(source,MassiveEventSource(MassiveJournal(tmp_path/'massive')))
    assert not c.prepare_events(NOW,durable)['events']
    prior_bar(j,instrument='US:AAPL')
    rest=c.prepare_events(NOW,durable);persist(rest);db.commit();db.close()
    db=sqlite3.connect(dbpath)
    final=_load_json(db.execute('SELECT body FROM cursor').fetchone()[0])
    assert not final['barrier']['pending_raw']
    assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==4
    assert not c.prepare_events(NOW,final)['events']
    db.close()


def test_multiple_held_same_clock_replay_is_physical_and_canonical(source,tmp_path):
    from app.r2d2_v2_sources import canonical,_load_json
    write(source,b''.join(tick('AAPL',price=price) for price in range(100,110)))
    j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j))
    held=c.prepare_events(NOW,{})['cursor']
    prior_bar(j,instrument='US:AAPL')
    canonical_cursor=_load_json(canonical(held))
    reversed_cursor=deepcopy(canonical_cursor)
    reversed_cursor['barrier']['pending_raw']=dict(reversed(list(canonical_cursor['barrier']['pending_raw'].items())))
    left=c.prepare_events(NOW,canonical_cursor);right=c.prepare_events(NOW,reversed_cursor)
    assert not left['diagnostics'] and not right['diagnostics']
    assert canonical(left)==canonical(right)
    quotes=[e for e in left['events'] if e['type']=='QUOTE']
    assert [e['bid'] for e in quotes]==list(range(100,110))
    assert [e['sequence'] for e in quotes]==list(range(10))


@pytest.mark.parametrize('files',[2500,4000])
def test_many_files_with_one_bar_progresses_without_relaxing_limits(source,tmp_path,files):
    write(source,tick('AAPL'))
    directory=source.raw_root/'session_date=2026-09-08'
    for number in range(2,files+1):
        path=directory/('feed=quote-part-'+str(number).zfill(5)+'.ndjson')
        path.touch(mode=0o600)
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:AAPL')
    c=CompositeEventSource(source,MassiveEventSource(j))
    page=c.prepare_events(NOW,{})
    assert not page['diagnostics']
    assert {e['type'] for e in page['events']}=={'BAR','QUOTE'}
    assert not page['has_more'] and not page['cursor']['barrier']['pending_raw']
    assert c.MAX_CURSOR_BYTES==2_000_000 and c.MAX_PROOFS==16384


def test_replay_plus_new_same_receipt_suffix_is_ordered_by_original_sequence(source,tmp_path):
    from app.r2d2_v2_sources import canonical,_load_json
    path=write(source,b''.join(tick('AAPL',price=price) for price in range(100,110)))
    j=MassiveJournal(tmp_path/'massive');c=CompositeEventSource(source,MassiveEventSource(j))
    held=_load_json(canonical(c.prepare_events(NOW,{})['cursor']))
    with path.open('ab') as out:out.write(tick('AAPL',price=110))
    prior_bar(j,instrument='US:AAPL')
    page=c.prepare_events(NOW,held)
    assert not page['diagnostics']
    quotes=[e for e in page['events'] if e['type']=='QUOTE']
    assert [e['bid'] for e in quotes]==list(range(100,111))
    assert [e['sequence'] for e in quotes]==list(range(11))
    assert page==c.prepare_events(NOW,held)


def test_regressed_receipt_cannot_pass_earlier_physical_held_tick(source,tmp_path):
    older=AT-timedelta(minutes=1)
    write(source,tick('AAPL',price=100)+tick('AAPL',price=101,at=older))
    j=MassiveJournal(tmp_path/'massive')
    prior_bar(j,instrument='US:AAPL',start=older.replace(second=0)-timedelta(minutes=1))
    c=CompositeEventSource(source,MassiveEventSource(j));held=c.prepare_events(NOW,{})
    assert not held['diagnostics'] and not any(e['type']=='QUOTE' for e in held['events'])
    assert len(held['cursor']['barrier']['pending_raw'])==2
    prior_bar(j,instrument='US:AAPL')
    page=c.prepare_events(NOW,held['cursor'])
    assert not page['diagnostics']
    assert [(e['bid'],e['sequence']) for e in page['events'] if e['type']=='QUOTE']==[(100,0),(101,1)]


def test_actual_unrepresentable_cursor_refuses_explicitly_instead_of_retry_loop(source,tmp_path):
    write(source,b''.join(tick('AAPL',price=100+i) for i in range(800)))
    directory=source.raw_root/'session_date=2026-09-08'
    for number in range(2,4001):
        (directory/('feed=quote-part-'+str(number).zfill(5)+'.ndjson')).touch(mode=0o600)
    j=MassiveJournal(tmp_path/'massive');prior_bar(j,instrument='US:MSFT')
    c=CompositeEventSource(source,MassiveEventSource(j));page=c.prepare_events(NOW,{})
    assert page['diagnostics']==[{'code':'COMPOSITE_CURSOR_CAPACITY'}]
    assert page['cursor']=={} and not page['events'] and not page.get('has_more')
    assert c.MAX_CURSOR_BYTES==2_000_000
