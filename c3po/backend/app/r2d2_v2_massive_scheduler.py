"""Bounded expiry scheduler driven by transport ticks, not provider traffic."""
from datetime import timedelta
from threading import RLock
from .r2d2_v2_sources import _require

class MinuteExpiry:
    def __init__(self,state,started_at):
        _require(started_at.utcoffset() is not None,'STREAM_CLOCK')
        self.state=state
        self.next_minute=started_at.replace(second=0,microsecond=0)
        self.last=started_at
        self.lock=RLock()

    def __call__(self,now):
        with self.lock:
            _require(now.utcoffset() is not None and now>=self.last,'STREAM_CLOCK_REVERSED')
            self.last=now
            # Bound any catch-up invocation; caller fails closed after long stalls.
            _require(now-self.next_minute<=timedelta(minutes=120),'STREAM_SCHEDULER_STALLED')
            count=0
            while now>self.next_minute+timedelta(seconds=90):
                self.state.expire_minute(self.next_minute,now)
                # Advance only after evidence persistence succeeds.
                self.next_minute+=timedelta(minutes=1)
                count+=1
            return count
