"""Bounded expiry scheduler driven by transport ticks, not provider traffic."""
from datetime import timedelta
from threading import RLock
from math import isfinite
from .r2d2_v2_sources import _require

class MinuteExpiry:
    def __init__(self,state,started_at,*,monotonic=None):
        _require(started_at.utcoffset() is not None,'STREAM_CLOCK')
        self.state=state
        self.next_minute=started_at.replace(second=0,microsecond=0)
        self.last=started_at
        self.started_at=started_at
        self.monotonic=monotonic
        self.started_mono=monotonic() if monotonic is not None else None
        self.last_mono=self.started_mono
        self.lock=RLock()

    def __call__(self,now):
        with self.lock:
            _require(now.utcoffset() is not None,'STREAM_CLOCK')
            due=now
            if self.monotonic is None:
                # Legacy direct callers retain their explicit UTC-only contract.
                _require(now>=self.last,'STREAM_CLOCK_REVERSED')
            else:
                current=self.monotonic()
                assert self.last_mono is not None and self.started_mono is not None
                _require(isfinite(current) and current>=self.last_mono,'STREAM_MONOTONIC_REVERSED')
                _require(current-self.last_mono<=7200,'STREAM_SCHEDULER_STALLED')
                self.last_mono=current
                # Both elapsed time and market UTC must cross the deadline.
                # A wall-clock rollback delays expiry; it never rewrites receipts.
                due=min(now,self.started_at+timedelta(seconds=current-self.started_mono))
            self.last=now
            # Bound any catch-up invocation; caller fails closed after long stalls.
            _require(due-self.next_minute<=timedelta(minutes=120),'STREAM_SCHEDULER_STALLED')
            count=0
            while due>self.next_minute+timedelta(seconds=150):
                self.state.expire_minute(self.next_minute,now)
                # Advance only after evidence persistence succeeds.
                self.next_minute+=timedelta(minutes=1)
                count+=1
            return count
