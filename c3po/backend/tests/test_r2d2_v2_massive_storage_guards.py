from datetime import datetime, timedelta, timezone
import json
import pytest
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_session_source import MassiveSessionEventSource
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_massive_recovery import restore_stream

NOW=datetime(2026,9,29,14,1,5,tzinfo=timezone.utc)
OLD=NOW.replace(day=28,minute=0,second=0)


def test_previous_session_frame_becomes_current_causal_gap_without_poisoning_reader(tmp_path):
    catalog=SessionJournalRoot(tmp_path,'storage-fixture',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL'])
    stream=MassiveStreamState(['AAPL'],ShadowCalendar(),journal)
    stream.connected(NOW-timedelta(seconds=66))
    raw=json.dumps([{'ev':'AM','sym':'AAPL','s':int(OLD.timestamp()*1000),
        'e':int((OLD+timedelta(minutes=1)).timestamp()*1000),'o':10,'h':12,'l':9,'c':11,'v':25}]).encode()
    stream.frame(raw,NOW)
    source=MassiveSessionEventSource(catalog)
    page=source.prepare_events(NOW,{})
    assert not page['diagnostics'] and len(page['events'])==1
    event=page['events'][0]
    assert event['type']=='DATA_GAP' and event['reason']=='MASSIVE_CROSS_SESSION_BAR'
    assert event['session']=='2026-09-29' and event['at']==event['available_at']==NOW.isoformat()
    assert not stream.seen
    restarted=MassiveStreamState(['AAPL'],ShadowCalendar(),journal)
    assert restore_stream(restarted,journal,session='2026-09-29',now=NOW)['records']==1
    assert restarted.seen==stream.seen=={} and restarted.sealed==stream.sealed==set()
    # A valid current minute remains admissible on both live and recovered
    # paths; rejected_minute cannot seal the receipt clock's current minute.
    current=NOW.replace(second=0)
    valid=json.dumps([{'ev':'AM','sym':'AAPL','s':int(current.timestamp()*1000),
        'e':int((current+timedelta(minutes=1)).timestamp()*1000),'o':10,'h':12,'l':9,'c':11,'v':25}]).encode()
    restarted.connected(current)
    stream.frame(valid,current+timedelta(seconds=65))
    restarted.frame(valid,current+timedelta(seconds=65))
    assert restarted.seen==stream.seen and len(restarted.seen)==1
    assert not restarted.sealed and not stream.sealed
    assert not source.prepare_events(NOW,page['cursor'],snapshot=page['snapshot'])['events']


def test_session_journal_refuses_foreign_receipt_before_writing_any_evidence(tmp_path):
    catalog=SessionJournalRoot(tmp_path,'storage-fixture',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL'])
    receipt={'event':{'type':'DATA_GAP','at':OLD.isoformat(),'available_at':NOW.isoformat(),
        'session':'2026-09-28','instrument_key':'US:AAPL','reason':'fixture'}}
    before=journal.path.read_bytes()
    with pytest.raises(ValueError,match='JOURNAL_RECEIPT_SESSION_MISMATCH'):journal(None,receipt)
    assert not list((journal.path.parent/'receipts').iterdir())
    assert not list((journal.path.parent/'raw').iterdir())
    assert journal.path.read_bytes()==before
    assert journal.page()['through']==0


@pytest.mark.parametrize('capacity',['spool_bytes','spool_files','index'])
def test_550_terminal_gaps_survive_full_sink_atomically_and_are_consumable(tmp_path,capacity):
    from app.r2d2_v2_massive_journal import MassiveJournal
    from app.r2d2_v2_sources import SourceUnavailable
    names=['S'+str(n) for n in range(550)]
    catalog=SessionJournalRoot(tmp_path,'capacity-fixture',create=True)
    journal=catalog.ensure_session('2026-09-29',names)
    if capacity=='index':
        # Real SQLITE_FULL with only32KiB available for normal receipts; the
        # terminal reserve remains within this deliberately SMALLER index cap.
        journal.max_index_bytes=(550+2)*4*4096+32768
    journal.configure_storage_reserve(names,session='2026-09-29')
    if capacity=='spool_bytes':journal.spool.max_bytes=1
    if capacity=='spool_files':journal.spool.max_files=1
    number=0
    while True:
        receipt={'event':{'type':'DATA_GAP','at':NOW.isoformat(),'available_at':NOW.isoformat(),
            'session':'2026-09-29','instrument_key':'US:S0','reason':'ordinary-'+str(number)}}
        try:journal(None,receipt)
        except SourceUnavailable as exc:
            assert str(exc)=='MASSIVE_STORAGE_CAPACITY';break
        number+=1
        assert number<1000,'index limit did not exhaust'
    with journal._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM terminal_receipts').fetchone()[0]==550
        assert db.execute('PRAGMA page_count').fetchone()[0]*db.execute('PRAGMA page_size').fetchone()[0]<=journal.max_index_bytes
    source=MassiveSessionEventSource(SessionJournalRoot(tmp_path,'capacity-fixture'))
    page=source.prepare_events(NOW,{})
    assert not page['diagnostics'] and len(page['events'])==number+550
    gaps=[e for e in page['events'] if e.get('reason')=='MASSIVE_STORAGE_CAPACITY']
    assert len(gaps)==550 and {e['instrument_key'] for e in gaps}=={'US:'+n for n in names}
    assert all(e['type']=='DATA_GAP' and e['at']==e['available_at']==NOW.isoformat() for e in gaps)
    assert not any(e['type']=='BAR' for e in page['events'])
    assert source.prepare_events(NOW,{})==page  # no read-side ACK
    assert not source.prepare_events(NOW,page['cursor'])['events']
    restarted=MassiveStreamState(names,ShadowCalendar(),MassiveJournal.open_reader(journal.path.parent))
    restore_stream(restarted,restarted.sink,session='2026-09-29',now=NOW)
    assert restarted.storage_stopped
    # No terminal receipt depends on the normal receipt-file sink.
    normal_files=list((journal.path.parent/'receipts').iterdir())
    assert len(normal_files)<=number+1
    count_before=journal.page()['through']
    with pytest.raises(SourceUnavailable,match='MASSIVE_STORAGE_CAPACITY'):journal(None,receipt)
    assert journal.page()['through']==count_before


def test_terminal_batch_transaction_rolls_back_as_a_unit_then_can_retry(tmp_path):
    from app.r2d2_v2_sources import SourceUnavailable
    catalog=SessionJournalRoot(tmp_path,'atomic-capacity',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL','MSFT'])
    journal.configure_storage_reserve(['AAPL','MSFT'],session='2026-09-29')
    journal.spool.max_bytes=1
    with journal._connect() as db:
        db.execute("CREATE TRIGGER refuse_second BEFORE INSERT ON terminal_receipts WHEN NEW.sequence=2 BEGIN SELECT RAISE(ABORT,'fixture'); END")
    receipt={'event':{'type':'DATA_GAP','at':NOW.isoformat(),'available_at':NOW.isoformat(),
        'session':'2026-09-29','instrument_key':'US:AAPL','reason':'ordinary'}}
    with pytest.raises(Exception,match='fixture'):journal(None,receipt)
    assert journal.page()['through']==0
    with journal._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM terminal_receipts').fetchone()[0]==0
        db.execute('DROP TRIGGER refuse_second')
    with pytest.raises(SourceUnavailable,match='MASSIVE_STORAGE_CAPACITY'):journal(None,receipt)
    assert journal.page()['through']==2


def test_producer_restart_after_terminal_storage_gap_never_connects(tmp_path):
    from app.r2d2_v2_massive_producer import run_producer
    from app.r2d2_v2_sources import SourceUnavailable
    catalog=SessionJournalRoot(tmp_path,'restart-capacity',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL'])
    journal.configure_storage_reserve(['AAPL'],session='2026-09-29')
    journal.spool.max_bytes=1
    receipt={'event':{'type':'DATA_GAP','at':NOW.isoformat(),'available_at':NOW.isoformat(),
        'session':'2026-09-29','instrument_key':'US:AAPL','reason':'ordinary'}}
    with pytest.raises(SourceUnavailable):journal(None,receipt)
    connections=[]
    with pytest.raises(SourceUnavailable,match='MASSIVE_STORAGE_CAPACITY'):
        run_producer(journal.path.parent,['AAPL'],ShadowCalendar(),'fixture',utcnow=lambda:NOW,
            monotonic=lambda:0,stop=lambda:False,connector=lambda *a,**k:connections.append(1))
    assert not connections and journal.page()['through']==1


def test_transport_closes_after_capacity_failure_and_keeps_one_durable_gap_batch(tmp_path):
    from app.r2d2_v2_massive_transport import pump
    from app.r2d2_v2_sources import SourceUnavailable
    catalog=SessionJournalRoot(tmp_path,'transport-capacity',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL','MSFT'])
    journal.configure_storage_reserve(['AAPL','MSFT'],session='2026-09-29')
    journal.spool.max_bytes=1
    stream=MassiveStreamState(['AAPL','MSFT'],ShadowCalendar(),journal)
    minute=NOW.replace(minute=0,second=0)
    frames=[b'[{"ev":"status","status":"auth_success"}]',json.dumps([{
        'ev':'AM','sym':'AAPL','s':int(minute.timestamp()*1000),
        'e':int((minute+timedelta(minutes=1)).timestamp()*1000),
        'o':10,'h':12,'l':9,'c':11,'v':25}]).encode()]
    class Socket:
        closed=False
        def send(self,value):pass
        def recv(self,timeout):return frames.pop(0)
        def close(self):self.closed=True
    socket=Socket()
    with pytest.raises(SourceUnavailable,match='^MASSIVE_STORAGE_CAPACITY$') as failure:
        pump(socket,stream,'private-token',utcnow=lambda:NOW,monotonic=lambda:0,
             tick=lambda at:None,stop=lambda:False)
    assert socket.closed and journal.storage_stopped
    assert failure.value.__context__ is None
    # Transport exits directly after the durable sink flag; no fallback gap
    # call is needed to mutate the stream's in-memory mirror.
    page=journal.page()
    assert page['through']==2
    assert {record['receipt']['event']['instrument_key'] for record in page['records']}=={'US:AAPL','US:MSFT'}
    assert all(record['receipt']['event']['reason']=='MASSIVE_STORAGE_CAPACITY' for record in page['records'])
    assert not frames


def test_terminal_receipt_corruption_is_unverifiable_without_cursor_advance(tmp_path):
    from app.r2d2_v2_sources import SourceUnavailable
    catalog=SessionJournalRoot(tmp_path,'corrupt-capacity',create=True)
    journal=catalog.ensure_session('2026-09-29',['AAPL'])
    journal.configure_storage_reserve(['AAPL'],session='2026-09-29')
    journal.spool.max_bytes=1
    receipt={'event':{'type':'DATA_GAP','at':NOW.isoformat(),'available_at':NOW.isoformat(),
        'session':'2026-09-29','instrument_key':'US:AAPL','reason':'ordinary'}}
    with pytest.raises(SourceUnavailable):journal(None,receipt)
    with journal._connect() as db:
        db.execute('UPDATE terminal_receipts SET payload=?',(b'{}',))
    source=MassiveSessionEventSource(catalog)
    page=source.prepare_events(NOW,{})
    assert page['diagnostics'] and not page['events']
    assert page['cursor']=={}


def test_unready_empty_reserve_skipped_but_unpublished_terminal_evidence_defers(tmp_path):
    from app.r2d2_v2_massive_journal import MassiveJournal
    from app.r2d2_v2_sources import SourceUnavailable
    catalog=SessionJournalRoot(tmp_path,'ready-capacity',create=True)
    journal=MassiveJournal(catalog.prepare_session('2026-09-29',['AAPL']))
    journal.configure_storage_reserve(['AAPL'],session='2026-09-29')
    assert catalog.ready_sessions()==()
    source=MassiveSessionEventSource(catalog)
    empty=source.prepare_events(NOW,{})
    assert not empty['diagnostics'] and not empty['events']
    journal.spool.max_bytes=1
    receipt={'event':{'type':'DATA_GAP','at':NOW.isoformat(),'available_at':NOW.isoformat(),
        'session':'2026-09-29','instrument_key':'US:AAPL','reason':'ordinary'}}
    with pytest.raises(SourceUnavailable):journal(None,receipt)
    deferred=source.prepare_events(NOW,{})
    assert deferred['diagnostics']==[{'code':'RAW_APPEND_IN_PROGRESS'}]
    assert not deferred['events'] and deferred['cursor']=={}
    catalog.mark_ready('2026-09-29')
    page=source.prepare_events(NOW,{})
    assert not page['diagnostics'] and len(page['events'])==1
    assert page['events'][0]['reason']=='MASSIVE_STORAGE_CAPACITY'
