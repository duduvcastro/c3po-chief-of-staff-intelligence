"""Offline daily-service and midminute continuity regressions."""
import json
import os
from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE, calendar
from test_r2d2_v2_massive_stream import bar, state
from test_r2d2_v2_massive_transport import Socket, State
from app.r2d2_v2_massive_producer import run_session
from app.r2d2_v2_massive_transport import pump, run_connection
from app.r2d2_v2_sources import SourceUnavailable


def test_midminute_gap_preserves_next_minute_and_raw_evidence(calendar):
    stream, output=state(calendar)
    stream.connected(MINUTE+timedelta(seconds=20))
    raw=json.dumps([bar()]).encode()
    stream.frame(raw,MINUTE+timedelta(seconds=65))
    stream.frame(raw,MINUTE+timedelta(seconds=66))
    next_row=dict(bar(),s=int((MINUTE+timedelta(minutes=1)).timestamp()*1000),
                  e=int((MINUTE+timedelta(minutes=2)).timestamp()*1000))
    stream.frame(json.dumps([next_row]).encode(),MINUTE+timedelta(seconds=125))
    assert [receipt['event']['type'] for _,receipt in output]==['DATA_GAP','BAR']
    assert output[0][0]==raw
    receipt=output[0][1]
    assert receipt['event']['at']==MINUTE.isoformat()
    assert receipt['event']['reason']=='MINUTE_CONNECTION_GAP'
    assert receipt['frame_index']==0 and receipt['raw_bytes']==len(raw)
    assert stream.connected_at==MINUTE+timedelta(seconds=20)


def test_midminute_gap_sink_failure_remains_unsealed(calendar):
    stream, _=state(calendar)
    stream.connected(MINUTE+timedelta(seconds=20))
    def fail(*args):raise OSError('disk full')
    stream.sink=fail
    with pytest.raises(OSError):
        stream.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
    assert not stream.sealed and not stream.seen


@pytest.mark.parametrize('phase',['connect','receive'])
def test_secret_exception_has_no_context_or_cause(phase):
    secret='fixture-private-token'
    def connect(*args,**kwargs):
        if phase=='connect':raise RuntimeError(secret)
        return Socket([RuntimeError(secret)])
    with pytest.raises(SourceUnavailable) as error:
        run_connection(State(),secret,utcnow=lambda:MINUTE,monotonic=lambda:0,
                       tick=lambda at:None,stop=lambda:False,connector=connect)
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert secret not in str(error.value)


def test_default_transport_survives_one_hour_and_covers_full_session():
    clock=[0];ws=Socket([]);stream=State();ticks=[]
    def recv(timeout):
        clock[0]+=60
        return '[{"ev":"status","status":"auth_success"}]'
    ws.recv=recv
    result=pump(ws,stream,'fixture',utcnow=lambda:MINUTE+timedelta(seconds=clock[0]),
                monotonic=lambda:clock[0],tick=ticks.append,stop=lambda:clock[0]>=6.5*3600)
    assert result=='STOPPED' and len(ticks)==391
    assert 'MASSIVE_SESSION_LIMIT' not in stream.gaps


def invoke(tmp_path, calendar, monkeypatch, **changes):
    manifest={'epoch':'offline-epoch','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()}
    manifest.update(changes)
    calls=[];notices=[]
    def producer(root,epoch,session,symbols,calendar,token,**kwargs):
        calls.append(((root,symbols,calendar,token),kwargs))
        return {'status':'STOPPED','recovered_records':0}
    monkeypatch.setattr('app.r2d2_v2_massive_producer._run_session_root',producer)
    run_session(tmp_path,manifest,calendar,lambda:'fixture',utcnow=lambda:MINUTE,
                monotonic=lambda:0,stop=lambda:False,supervisor=notices.append)
    return calls,notices


def test_daily_manifest_drives_calendar_deadline_and_supervision(tmp_path,calendar,monkeypatch):
    calls,notices=invoke(tmp_path,calendar,monkeypatch)
    deadline=calendar.details(MINUTE.date())['close']+timedelta(seconds=91)
    assert calls[0][0][1]==['AAPL']
    assert calls[0][1]['max_seconds']==(deadline-MINUTE).total_seconds()>3600
    assert [n['status'] for n in notices]==['STARTING','STOPPED']
    assert all('fixture' not in str(n) for n in notices)


@pytest.mark.parametrize('changes',[
    {'session':'2020-01-01'}, {'owner_uid':-1}, {'symbols':[]},
    {'symbols':['AAPL','AAPL']}, {'symbols':['AM.*']}, {'owner_uid':True},
    {'epoch':'../invalid'}, {'epoch':''},
])
def test_bad_manifest_refuses_before_secret_or_network(tmp_path,calendar,changes):
    manifest={'epoch':'offline-epoch','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()}
    manifest.update(changes)
    def forbidden(*args,**kwargs):pytest.fail('preflight touched secret or network')
    with pytest.raises(SourceUnavailable):
        run_session(tmp_path,manifest,calendar,forbidden,utcnow=lambda:MINUTE,
                    monotonic=lambda:0,stop=lambda:False,supervisor=lambda x:None,connector=forbidden)


def test_service_failure_supervised_without_secret_context(tmp_path,calendar,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('fixture-private-token')
    monkeypatch.setattr('app.r2d2_v2_massive_producer._run_session_root',fail)
    notices=[]
    with pytest.raises(SourceUnavailable) as error:
        run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),'symbols':['AAPL'],
                    'owner_uid':os.geteuid()},calendar,lambda:'fixture-private-token',
                    utcnow=lambda:MINUTE,monotonic=lambda:0,stop=lambda:False,supervisor=notices.append)
    assert error.value.__context__ is None and error.value.__cause__ is None
    assert [n['status'] for n in notices]==['STARTING','FAILED']
    assert 'fixture-private-token' not in str(notices)


def test_explicit_entrypoint_loads_private_manifest_and_external_token(tmp_path,monkeypatch,capsys):
    from app import r2d2_v2_massive_producer as producer
    manifest=tmp_path/'daily.json'
    payload={'epoch':'offline-epoch','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()}
    manifest.write_text(json.dumps(payload));manifest.chmod(0o600)
    monkeypatch.setenv('OFFLINE_TEST_MASSIVE_KEY','private-fixture')
    calls=[]
    def session(root,selected,calendar,token_provider,**kwargs):
        calls.append((root,selected,token_provider()))
        kwargs['supervisor']({'status':'STOPPED'})
        return {'status':'STOPPED','recovered_records':0}
    monkeypatch.setattr(producer,'run_session',session)
    assert producer.main(['--manifest',str(manifest),'--journal-root',str(tmp_path),
                          '--token-env','OFFLINE_TEST_MASSIVE_KEY'])==0
    assert calls==[(str(tmp_path),payload,'private-fixture')]
    assert 'private-fixture' not in capsys.readouterr().out


def test_entrypoint_rejects_writable_manifest_before_service(tmp_path,monkeypatch,capsys):
    from app import r2d2_v2_massive_producer as producer
    manifest=tmp_path/'daily.json';manifest.write_text('{}');manifest.chmod(0o666)
    monkeypatch.setattr(producer,'run_session',lambda *a,**k:pytest.fail('unsafe manifest reached service'))
    assert producer.main(['--manifest',str(manifest),'--journal-root',str(tmp_path)])==1
    assert 'MASSIVE_SERVICE_FAILURE' in capsys.readouterr().out


@pytest.mark.parametrize('exit_kind',['stop','limit'])
def test_silent_am_connection_ticks_and_seals_final_session_minute(tmp_path,calendar,exit_kind):
    from app.r2d2_v2_massive_journal import MassiveJournal
    from app.r2d2_v2_massive_stream import MassiveStreamState
    from app.r2d2_v2_massive_scheduler import MinuteExpiry
    close=calendar.details(MINUTE.date())['close']
    last_minute=close-timedelta(minutes=1)
    clock=[last_minute]
    deadline=close+timedelta(seconds=91)
    journal=MassiveJournal(tmp_path)
    stream=MassiveStreamState(['AAPL'],calendar,journal)
    scheduler=MinuteExpiry(stream,last_minute)
    socket=Socket([]);calls=[0]
    def recv(timeout):
        calls[0]+=1
        if calls[0]==1:return '[{"ev":"status","status":"auth_success"}]'
        clock[0]+=timedelta(seconds=1)
        raise TimeoutError()
    socket.recv=recv
    result=pump(socket,stream,'fixture',utcnow=lambda:clock[0],
                monotonic=lambda:(clock[0]-last_minute).total_seconds(),tick=scheduler,
                stop=lambda:exit_kind=='stop' and clock[0]>=deadline,
                max_seconds=151 if exit_kind=='limit' else 8*3600)
    assert result==('STOPPED' if exit_kind=='stop' else 'SESSION_LIMIT')
    records=journal.page()['records']
    assert len(records)==1
    event=records[0]['receipt']['event']
    assert event['reason']=='MASSIVE_MINUTE_NOT_OBSERVED'
    assert event['at']==last_minute.isoformat()
    assert event['available_at']==deadline.isoformat()
    assert calls[0]>75 and socket.closed


def test_storage_measurement_includes_exact_spool_index_and_sidecars(tmp_path):
    from app.r2d2_v2_massive_producer import _storage_usage
    (tmp_path/'raw').mkdir();(tmp_path/'receipts').mkdir()
    sizes={'raw/frame.json':17,'receipts/receipt.json':31,'sequence.sqlite3':101,
           'sequence.sqlite3-wal':103,'sequence.sqlite3-shm':107,'sequence.sqlite3-journal':109}
    for name,size in sizes.items():(tmp_path/name).write_bytes(b'x'*size)
    fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
    try:usage=_storage_usage(fd)
    finally:os.close(fd)
    assert usage['raw_bytes']==17 and usage['receipt_bytes']==31
    assert usage['index_bytes']==101 and usage['wal_bytes']==103
    assert usage['shm_bytes']==107 and usage['rollback_bytes']==109
    assert usage['total_bytes']==sum(sizes.values()) and usage['evidence_files']==2
    assert usage['allocated_bytes']==sum((tmp_path/name).stat().st_blocks*512 for name in sizes)


@pytest.mark.parametrize('kind',['free','evidence','index','wal'])
def test_session_storage_limit_refuses_before_network_with_declared_gap(tmp_path,calendar,monkeypatch,kind):
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    child=SessionJournalRoot(tmp_path,'offline-epoch',create=True).prepare_session(MINUTE.date().isoformat(),['AAPL'])
    if kind in ('index','wal'):
        target=child/('sequence.sqlite3' if kind=='index' else 'sequence.sqlite3-wal')
        with target.open('wb') as out:out.truncate(producer.MAX_SESSION_INDEX_BYTES)
    elif kind=='evidence':
        (child/'raw').mkdir()
        with (child/'raw'/'fixture.json').open('wb') as out:
            out.truncate(producer.MAX_SESSION_EVIDENCE_BYTES)
    from types import SimpleNamespace
    free=producer.MIN_SESSION_FREE_BYTES-(1 if kind=='free' else 0)
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(f_bavail=free,f_frsize=1))
    notices=[]
    def forbidden(*a,**k):pytest.fail('budget refusal opened provider')
    with pytest.raises(SourceUnavailable):
        producer.run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
            'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
            utcnow=lambda:MINUTE,monotonic=lambda:0,stop=lambda:False,
            supervisor=notices.append,connector=forbidden)
    gaps=[n for n in notices if n['status']=='DATA_GAP']
    assert len(gaps)==1 and gaps[0]['provider_connected'] is False
    assert gaps[0]['reason'].endswith({'free':'LOW_DISK','evidence':'EVIDENCE_LIMIT',
                                      'index':'INDEX_LIMIT','wal':'INDEX_LIMIT'}[kind])
    if kind not in ('index','wal'):assert not (child/'sequence.sqlite3').exists()


def test_session_reports_measured_storage_delta_at_exact_free_floor(tmp_path,calendar,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    from types import SimpleNamespace
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(
        f_bavail=producer.MIN_SESSION_FREE_BYTES,f_frsize=1))
    clock=[0];notices=[];socket=Socket([])
    # Stop after entry, so the real producer writes a durable local gap only.
    def stop():clock[0]+=1;return clock[0]>1
    result=producer.run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
        'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
        utcnow=lambda:MINUTE,monotonic=lambda:0,stop=stop,supervisor=notices.append,
        connector=lambda *a,**k:socket)
    assert result['status']=='STOPPED'
    before=next(n for n in notices if n['status']=='BUDGET_START')
    after=next(n for n in notices if n['status']=='BUDGET_END')
    assert before['storage']['free_bytes']==producer.MIN_SESSION_FREE_BYTES
    assert after['measured_byte_delta']['receipt_bytes']>0
    assert after['measured_byte_delta']['index_bytes']==(tmp_path/('session_date='+MINUTE.date().isoformat())/'sequence.sqlite3').stat().st_size
    assert after['storage']['total_bytes']==sum(p.stat().st_size for p in (tmp_path/('session_date='+MINUTE.date().isoformat())).rglob('*') if p.is_file())
    assert after['review_after_sessions']==3


@pytest.mark.parametrize('flag_present',[False,True])
def test_flag_off_cycle_state_and_journal_are_byte_identical(tmp_path,monkeypatch,flag_present):
    from types import SimpleNamespace
    from tests.test_r2d2_v2_shadow_counterexamples import setup_state,source_event,INSTRUMENT
    from app.r2d2_v2_shadow_worker import _with_massive_source
    from app.r2d2_v2_sources import canonical
    from app.r2d2_v2_store import utc
    from app.r2d2_v2_massive_journal import MassiveJournal
    def forbidden(*a,**k):pytest.fail('FLAG_OFF touched Massive')
    monkeypatch.setattr(MassiveJournal,'open_reader',forbidden)
    first=utc('2026-09-08T15:00:00Z')
    class Feed:
        def events(self,now):
            return [source_event('TRADE',at=now.isoformat(),
                sequence=int((now-first).total_seconds()),price=100,regular=True)]
    traces=[]
    for wrapped in (False,True):
        collector,state,_=setup_state()
        state['coverage_until'][INSTRUMENT]=first.isoformat()
        collector.store.atomic(collector.release.epoch,collector._initial(),
                               lambda unused:(state,[],{}),first)
        source=Feed()
        settings=SimpleNamespace(r2d2_v2_massive_journal_dir=tmp_path/'must-not-exist')
        if flag_present:settings.r2d2_v2_massive_bars_enabled=False
        collector.source=_with_massive_source(settings,source,collector.release) if wrapped else source
        results=[collector.cycle(first+timedelta(seconds=i)) for i in (1,30,60)]
        traces.append(canonical({'results':results,'state':collector.store.read(collector.release.epoch),
                                  'journal':collector.store.journal(collector.release.epoch)}))
    assert traces[0]==traces[1] and not (tmp_path/'must-not-exist').exists()


def test_session_measures_actual_persisted_bar_frame_bytes(tmp_path,calendar,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    from types import SimpleNamespace
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(
        f_bavail=producer.MIN_SESSION_FREE_BYTES,f_frsize=1))
    clock=[MINUTE-timedelta(seconds=5)];notices=[]
    raw=json.dumps([bar()]).encode();socket=Socket([]);counter=[0]
    def recv(timeout):
        counter[0]+=1
        if counter[0]==1:return '[{"ev":"status","status":"auth_success"}]'
        clock[0]=MINUTE+timedelta(seconds=65)
        return raw
    socket.recv=recv
    result=producer.run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
        'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
        utcnow=lambda:clock[0],monotonic=lambda:(clock[0]-MINUTE).total_seconds(),
        stop=lambda:clock[0]>MINUTE,supervisor=notices.append,connector=lambda *a,**k:socket)
    assert result['status']=='STOPPED'
    after=next(n for n in notices if n['status']=='BUDGET_END')
    assert after['measured_byte_delta']['raw_bytes']==len(raw)
    assert after['storage']['index_bytes']==(tmp_path/('session_date='+MINUTE.date().isoformat())/'sequence.sqlite3').stat().st_size


def test_unverified_storage_declares_gap_before_provider(tmp_path,calendar,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    def fail(fd):raise OSError('filesystem unavailable')
    monkeypatch.setattr(producer.os,'fstatvfs',fail)
    notices=[]
    with pytest.raises(SourceUnavailable):
        producer.run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
            'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
            utcnow=lambda:MINUTE,monotonic=lambda:0,stop=lambda:False,supervisor=notices.append,
            connector=lambda *a,**k:pytest.fail('unverified storage opened provider'))
    assert any(n['status']=='DATA_GAP' and n['reason']=='MASSIVE_SERVICE_STORAGE_UNVERIFIED'
               for n in notices)


def test_daily_indexes_preserve_prior_bytes_and_measure_aggregate(tmp_path,calendar,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_journal import MassiveJournal
    from types import SimpleNamespace
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(
        f_bavail=producer.MIN_SESSION_FREE_BYTES,f_frsize=1))
    notices=[]
    def daily(now,symbol):
        stops=[0]
        def stop():stops[0]+=1;return stops[0]>1
        return producer.run_session(tmp_path,{'epoch':'offline-epoch','session':now.date().isoformat(),
            'symbols':[symbol],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
            utcnow=lambda:now,monotonic=lambda:0,stop=stop,supervisor=notices.append,
            connector=lambda *a,**k:Socket([]))
    daily(MINUTE,'AAPL')
    first=tmp_path/('session_date='+MINUTE.date().isoformat())
    original={p.name:p.read_bytes() for p in first.rglob('*') if p.is_file()}
    # Each child fits; their retained aggregate may exceed one child's index cap.
    monkeypatch.setattr(producer,'MAX_SESSION_INDEX_BYTES',(first/'sequence.sqlite3').stat().st_size+1)
    tomorrow=MINUTE+timedelta(days=1)
    daily(tomorrow,'MSFT')
    second=tmp_path/('session_date='+tomorrow.date().isoformat())
    assert {p.name:p.read_bytes() for p in first.rglob('*') if p.is_file()}==original
    assert (first/'sequence.sqlite3').stat().st_ino!=(second/'sequence.sqlite3').stat().st_ino
    for path,symbol in ((first,'AAPL'),(second,'MSFT')):
        records=MassiveJournal.open_reader(path).page()['records']
        assert len(records)==1 and records[0]['sequence']==1
        assert records[0]['receipt']['event']['instrument_key']=='US:'+symbol
    aggregate=[n for n in notices if n['status']=='RETAINED_BUDGET_END'][-1]
    assert aggregate['storage']['retained_sessions']==2
    assert aggregate['storage']['index_bytes']==sum((p/'sequence.sqlite3').stat().st_size for p in (first,second))
    assert aggregate['storage']['total_bytes']==sum(p.stat().st_size for p in tmp_path.rglob('*') if p.is_file())
    assert aggregate['storage']['index_bytes']>producer.MAX_SESSION_INDEX_BYTES


@pytest.mark.parametrize('change',[{'epoch':'different-epoch'},{'symbols':['MSFT']}])
def test_same_session_manifest_change_refuses_without_provider_or_mutation(tmp_path,calendar,monkeypatch,change):
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from types import SimpleNamespace
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(
        f_bavail=producer.MIN_SESSION_FREE_BYTES,f_frsize=1))
    child=SessionJournalRoot(tmp_path,'offline-epoch',create=True).prepare_session(MINUTE.date().isoformat(),['AAPL'])
    original=(child/'session.json').read_bytes()
    manifest={'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
              'symbols':['AAPL'],'owner_uid':os.geteuid()};manifest.update(change)
    with pytest.raises(SourceUnavailable):
        producer.run_session(tmp_path,manifest,calendar,lambda:'fixture',utcnow=lambda:MINUTE,
            monotonic=lambda:0,stop=lambda:False,supervisor=lambda n:None,
            connector=lambda *a,**k:pytest.fail('changed identity opened provider'))
    assert (child/'session.json').read_bytes()==original and not (child/'sequence.sqlite3').exists()


def test_parent_producer_lock_blocks_other_session_service(tmp_path,calendar,monkeypatch):
    import fcntl
    from app import r2d2_v2_massive_producer as producer
    manifest={'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
              'symbols':['AAPL'],'owner_uid':os.geteuid()}
    lock=tmp_path/'producer.lock';lock.touch(mode=0o600)
    with lock.open('r') as fd:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(SourceUnavailable):
            producer.run_session(tmp_path,manifest,calendar,lambda:'fixture',utcnow=lambda:MINUTE,
                monotonic=lambda:0,stop=lambda:False,supervisor=lambda n:None,
                connector=lambda *a,**k:pytest.fail('second producer opened provider'))
    assert not (tmp_path/'epoch.json').exists()


def test_session_ready_publication_exposes_complete_journal_to_reader(tmp_path,calendar,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from types import SimpleNamespace
    monkeypatch.setattr(producer.os,'fstatvfs',lambda fd:SimpleNamespace(
        f_bavail=producer.MIN_SESSION_FREE_BYTES,f_frsize=1))
    stops=[0]
    def stop():stops[0]+=1;return stops[0]>1
    producer.run_session(tmp_path,{'epoch':'offline-epoch','session':MINUTE.date().isoformat(),
        'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'fixture',
        utcnow=lambda:MINUTE,monotonic=lambda:0,stop=stop,supervisor=lambda n:None,
        connector=lambda *a,**k:Socket([]))
    catalog=SessionJournalRoot(tmp_path,'offline-epoch')
    records=catalog.open_session(MINUTE.date().isoformat()).page()['records']
    assert len(records)==1 and records[0]['sequence']==1
    assert (catalog.session_path(MINUTE.date().isoformat())/'ready.json').is_file()


def test_ready_publication_failure_never_connects_or_changes_existing_evidence(tmp_path,calendar):
    from app.r2d2_v2_massive_producer import run_producer
    from app.r2d2_v2_massive_journal import MassiveJournal
    journal=MassiveJournal(tmp_path)
    before=(tmp_path/'sequence.sqlite3').read_bytes()
    def fail():raise OSError('readiness publication unavailable')
    with pytest.raises(OSError,match='readiness publication unavailable'):
        run_producer(tmp_path,['AAPL'],calendar,'fixture',utcnow=lambda:MINUTE,
            monotonic=lambda:0,stop=lambda:False,journal_ready=fail,
            connector=lambda *a,**k:pytest.fail('failed readiness opened provider'))
    assert (tmp_path/'sequence.sqlite3').read_bytes()==before
    assert journal.page()['records']==[]
