"""Massive wire envelope through real calendar and motor validation, offline."""
import hashlib,json
from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE,calendar,row,convert
from app.r2d2_v2_sources import SourceUnavailable

def envelope(rows=None,**changes):
 r=row();r.pop('s');r.pop('i')
 rows=[r] if rows is None else rows
 return dict(dict(status='OK',ticker='AAPL',adjusted=False,resultsCount=len(rows),results=rows),**changes)
def run(calendar,doc=None,**changes):
 return convert(calendar,raw=json.dumps(envelope() if doc is None else doc).encode(),provider='massive',**changes)
def test_massive_exact_bytes_and_provenance(calendar):
 doc=envelope();raw=json.dumps(doc).encode();got=run(calendar,doc)
 assert got['event']['type']=='BAR' and got['event']['close']==101
 assert got['raw_sha256']==hashlib.sha256(raw).hexdigest()
 assert got['provenance']=='MASSIVE_REST_UNADJUSTED_MINUTE_AGGREGATES_V1'
@pytest.mark.parametrize('delta',[{'status':'DELAYED'},{'status':'NOT_AUTHORIZED'},{'ticker':'MSFT'}, {'adjusted':True},{'next_url':'another-page'},{'resultsCount':0},{'resultsCount':True}])
def test_envelope_refuses(calendar,delta):
 with pytest.raises(SourceUnavailable):run(calendar,envelope(**delta))
def test_massive_absence_remains_gap(calendar):
 got=run(calendar,envelope([]));assert got['event']['reason']=='MINUTE_ABSENT'
 assert 'coverage_complete' not in got['event'] and 'close' not in got['event']
@pytest.mark.parametrize('volume',[0,-1,True,float('nan')])
def test_invalid_volume(calendar,volume):
 d=envelope();d['results'][0]['v']=volume
 with pytest.raises(SourceUnavailable):run(calendar,d)
def test_fractional_provider_volume_preserved(calendar):
 d=envelope();d['results'][0]['v']=25.5
 assert run(calendar,d)['volume']==25.5
@pytest.mark.parametrize('seconds',[150.000001,151,180])
def test_stale_massive_not_rehabilitated(calendar,seconds):
 assert run(calendar,now=MINUTE+timedelta(seconds=seconds))['event']['reason']=='MINUTE_LATE'
def test_massive_open_minute_refused(calendar):
 d=envelope();d['results'][0]['t']+=60000
 with pytest.raises(SourceUnavailable,match='PROVIDER_OPEN_BAR'):run(calendar,d)
def test_massive_duplicate_refused(calendar):
 d=envelope();d['results']*=2;d['resultsCount']=2
 with pytest.raises(SourceUnavailable,match='DUPLICATE'):run(calendar,d)
def test_otc_refused(calendar):
 d=envelope();d['results'][0]['otc']=True
 with pytest.raises(SourceUnavailable,match='OTC'):run(calendar,d)

from app.r2d2_v2_minute_bars import massive_stream_minute

def stream(calendar,**changes):
 r=envelope()['results'][0];r['s']=r.pop('t');r.update(e=r['s']+60000,ev='AM',sym='AAPL')
 r.update(changes.pop('row_changes',{}))
 raw=json.dumps([r]).encode()
 args=dict(symbol='AAPL',minute=MINUTE,received_at=MINUTE+timedelta(seconds=63),now=MINUTE+timedelta(seconds=64),calendar=calendar,connected_at=MINUTE-timedelta(seconds=60))
 args.update(changes)
 return massive_stream_minute(raw,**args),raw

def test_stream_receipt_bound_to_original_frame(calendar):
 got,raw=stream(calendar)
 assert got['raw_sha256']==hashlib.sha256(raw).hexdigest()
 assert got['raw_bytes']==len(raw) and got['provenance']=='MASSIVE_WEBSOCKET_AM_V1'
 assert got['event']['available_at']==(MINUTE+timedelta(seconds=63)).isoformat()
 assert 'request_started' not in got
@pytest.mark.parametrize('changes',[{'ev':'A'},{'sym':'MSFT'},{'e':int(MINUTE.timestamp()*1000)+59999},{'otc':True}])
def test_stream_invalid_intervals_and_identity(calendar,changes):
 with pytest.raises(SourceUnavailable):stream(calendar,row_changes=changes)
def test_reconnect_does_not_backfill_live(calendar):
 with pytest.raises(SourceUnavailable,match='CONNECTION_GAP'):stream(calendar,connected_at=MINUTE+timedelta(seconds=1))
def test_stream_open_minute_refused(calendar):
 with pytest.raises(SourceUnavailable,match='NOT_CLOSED'):stream(calendar,received_at=MINUTE+timedelta(seconds=59))
def test_stream_late_is_gap(calendar):
 got,_=stream(calendar,now=MINUTE+timedelta(seconds=150,microseconds=1));assert got['event']['type']=='DATA_GAP'

@pytest.mark.parametrize('seconds',[91,120,150])
def test_massive_valid_until_ninety_seconds_after_minute_end(calendar,seconds):
 assert run(calendar,now=MINUTE+timedelta(seconds=seconds))['event']['type']=='BAR'

@pytest.mark.parametrize('seconds',[91,120,150])
def test_stream_valid_until_ninety_seconds_after_minute_end(calendar,seconds):
 got,_=stream(calendar,now=MINUTE+timedelta(seconds=seconds))
 assert got['event']['type']=='BAR'
