from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_stream import state
from app.r2d2_v2_massive_scheduler import MinuteExpiry
from app.r2d2_v2_sources import SourceUnavailable

def test_no_frames_still_emit_550_gaps_at_exact_missing_minute(calendar):
 s,out=state(calendar,['S'+str(i) for i in range(550)]);tick=MinuteExpiry(s,MINUTE)
 assert tick(MINUTE+timedelta(seconds=150))==0
 assert tick(MINUTE+timedelta(seconds=151))==1
 assert len(out)==550
 assert all(r['event']['at']==MINUTE.isoformat() and r['event']['available_at']==(MINUTE+timedelta(seconds=151)).isoformat() for _,r in out)
 assert tick(MINUTE+timedelta(seconds=152))==0 and len(out)==550

def test_failed_persistence_does_not_skip_minute(calendar):
 s,out=state(calendar);tick=MinuteExpiry(s,MINUTE);sink=s.sink
 def fail(*a):raise OSError('disk')
 s.sink=fail
 with pytest.raises(OSError):tick(MINUTE+timedelta(seconds=151))
 assert tick.next_minute==MINUTE
 s.sink=sink;assert tick(MINUTE+timedelta(seconds=152))==1 and len(out)==1

@pytest.mark.parametrize('delta,code',[(-1,'CLOCK_REVERSED'),(7300,'SCHEDULER_STALLED')])
def test_bad_clock_or_unbounded_catchup_fails_closed(calendar,delta,code):
 s,out=state(calendar);tick=MinuteExpiry(s,MINUTE)
 with pytest.raises(SourceUnavailable,match=code):tick(MINUTE+timedelta(seconds=delta))
 assert not out
