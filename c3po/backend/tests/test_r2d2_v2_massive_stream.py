import json
from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE,calendar
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_sources import SourceUnavailable

def bar(s='AAPL',**changes):
 r=dict(ev='AM',sym=s,s=int(MINUTE.timestamp()*1000),e=int(MINUTE.timestamp()*1000)+60000,o=10,h=12,l=9,c=11,v=25);r.update(changes);return r

def state(calendar,symbols=None):
 output=[];s=MassiveStreamState(symbols or ['AAPL'],calendar,lambda raw,receipt:output.append((raw,receipt)));s.connected(MINUTE-timedelta(seconds=5));return s,output

def test_all_550_symbols_same_frame(calendar):
 names=['S'+str(i) for i in range(550)];s,out=state(calendar,names);raw=json.dumps([bar(n) for n in names]).encode()
 s.frame(raw,MINUTE+timedelta(seconds=65));assert len(out)==550
 assert all(x[0]==raw and x[1]['event']['type']=='BAR' for x in out)

def test_disconnect_gap_all_and_no_retroactive_fill(calendar):
 s,out=state(calendar,['AAPL','MSFT']);s.gap(MINUTE+timedelta(seconds=30),'DISCONNECTED');assert len(out)==2
 s.connected(MINUTE+timedelta(seconds=40))
 with pytest.raises(SourceUnavailable,match='CONNECTION_GAP'):s.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 assert len(out)==2

def test_duplicate_and_conflict(calendar):
 s,out=state(calendar);raw=json.dumps([bar()]).encode();at=MINUTE+timedelta(seconds=65)
 s.frame(raw,at);s.frame(raw,at);assert len(out)==1
 s.frame(json.dumps([bar(c=10)]).encode(),at);assert out[-1][1]['event']['reason']=='MASSIVE_BAR_CONFLICT'
 assert s.connected_at is not None

def test_sink_failure_not_acknowledged(calendar):
 s,out=state(calendar)
 def fail(*args):raise OSError('offline fixture')
 s.sink=fail
 with pytest.raises(OSError):s.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 assert not s.seen

def test_status_invalidates(calendar):
 s,out=state(calendar);s.frame(b'[{"ev":"status","status":"error"}]',MINUTE)
 assert out[0][1]['event']['type']=='DATA_GAP' and s.connected_at is None

def test_expiry_only_missing_and_never_backfills(calendar):
 s,out=state(calendar,['AAPL','MSFT'])
 s.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=91))
 assert len(out)==2 and out[-1][1]['event']['instrument_key']=='US:MSFT'
 assert out[-1][1]['event']['type']=='DATA_GAP'
 s.frame(json.dumps([bar('MSFT')]).encode(),MINUTE+timedelta(seconds=92))
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=93))
 assert len(out)==2

def test_expiry_does_not_shorten_90_second_window(calendar):
 s,out=state(calendar)
 with pytest.raises(SourceUnavailable,match='NOT_EXPIRED'):
  s.expire_minute(MINUTE,MINUTE+timedelta(seconds=90))
 assert not out and not s.sealed

def test_expiry_disk_failure_not_sealed(calendar):
 s,out=state(calendar)
 def fail(*args):raise OSError('disk full')
 s.sink=fail
 with pytest.raises(OSError):s.expire_minute(MINUTE,MINUTE+timedelta(seconds=91))
 assert not s.sealed

def test_expiry_outside_regular_session_emits_nothing(calendar):
 s,out=state(calendar)
 early=MINUTE.replace(hour=0)
 s.expire_minute(early,early+timedelta(seconds=91))
 assert not out

@pytest.mark.parametrize('status',['connected','auth_success','success'])
def test_benign_status_preserves_connection_and_following_bar(calendar,status):
 s,out=state(calendar);connected=s.connected_at
 s.frame(json.dumps([{'ev':'status','status':status},bar()]).encode(),MINUTE+timedelta(seconds=65))
 assert s.connected_at==connected
 assert len(out)==1 and out[0][1]['event']['type']=='BAR'

@pytest.mark.parametrize('at',[MINUTE.replace(hour=0),MINUTE-timedelta(days=2)])
def test_disconnect_outside_session_does_not_emit_research_gap(calendar,at):
 s,out=state(calendar);s.gap(at,'DISCONNECTED')
 assert s.connected_at is None and not out

@pytest.mark.parametrize('irrelevant', [bar('OTHER'), dict(bar(),s=int(MINUTE.replace(hour=0).timestamp()*1000))])
def test_irrelevant_row_preserves_following_selected_bar(calendar, irrelevant):
 s,out=state(calendar);connected=s.connected_at
 s.frame(json.dumps([irrelevant,bar()]).encode(),MINUTE+timedelta(seconds=65))
 assert s.connected_at==connected
 assert len(out)==1 and out[0][1]['event']['type']=='BAR'
 assert out[0][1]['frame_index']==1

@pytest.mark.parametrize('timestamp', [10**30, -(10**30)])
def test_extreme_provider_timestamp_is_typed_refusal(calendar,timestamp):
 s,out=state(calendar)
 with pytest.raises(SourceUnavailable,match='STREAM_TIMESTAMP'):
  s.frame(json.dumps([dict(bar(),s=timestamp)]).encode(),MINUTE+timedelta(seconds=65))
 assert not out and not s.seen


def test_bad_price_invalidates_only_its_symbol_and_seals_minute(calendar):
 s,out=state(calendar,['AAPL','MSFT']);connected=s.connected_at;at=MINUTE+timedelta(seconds=65)
 raw=json.dumps([bar(o=-1),bar('MSFT')]).encode()
 s.frame(raw,at)
 assert s.connected_at==connected
 assert [(x[1]['event']['instrument_key'],x[1]['event']['type']) for x in out]==[('US:AAPL','DATA_GAP'),('US:MSFT','BAR')]
 assert all(x[0]==raw for x in out)
 s.frame(json.dumps([bar()]).encode(),at+timedelta(seconds=1))
 assert len(out)==2


def test_invalid_row_storage_failure_does_not_seal(calendar):
 s,out=state(calendar)
 def fail(*args):raise OSError('disk full')
 s.sink=fail
 with pytest.raises(OSError):s.frame(json.dumps([bar(o=-1)]).encode(),MINUTE+timedelta(seconds=65))
 assert not s.sealed and not s.seen


def test_conflict_preserves_other_symbol_and_original_observation(calendar):
 s,out=state(calendar,['AAPL','MSFT']);at=MINUTE+timedelta(seconds=65)
 s.frame(json.dumps([bar()]).encode(),at);original=dict(s.seen)
 s.frame(json.dumps([bar(c=10),bar('MSFT')]).encode(),at+timedelta(seconds=1))
 assert [x[1]['event']['type'] for x in out]==['BAR','DATA_GAP','BAR']
 assert out[1][1]['event']['instrument_key']=='US:AAPL'
 assert all(s.seen[k]==v for k,v in original.items())
 s.frame(json.dumps([bar(c=10)]).encode(),at+timedelta(seconds=2))
 assert len(out)==3


def test_conflict_persistence_failure_does_not_seal(calendar):
 s,out=state(calendar);at=MINUTE+timedelta(seconds=65)
 s.frame(json.dumps([bar()]).encode(),at);original=dict(s.seen)
 def fail(*args):raise OSError('disk full')
 s.sink=fail
 with pytest.raises(OSError):s.frame(json.dumps([bar(c=10)]).encode(),at)
 assert not s.sealed and s.seen==original


def test_expiry_prunes_550_minute_state_without_allowing_old_fill(calendar):
 names=['S'+str(i) for i in range(550)];s,out=state(calendar,names)
 for i in range(10):
  minute=MINUTE+timedelta(minutes=i)
  s.expire_minute(minute,minute+timedelta(seconds=91))
 assert len(s.sealed)==1650 and not s.seen
 assert len(out)==5500
 s.frame(json.dumps([bar(n) for n in names]).encode(),MINUTE+timedelta(minutes=11))
 s.expire_minute(MINUTE,MINUTE+timedelta(minutes=11))
 assert len(out)==5500
