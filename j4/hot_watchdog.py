"""Independent prewarmed native-time group watchdog, no fact or effect issuer.

The approved worker forks this monitor BEFORE observation. A private inherited
pipe carries ONE actual T/deadline. Native code blocked in the image interpreter
cannot delay this monitor's clock. It shares the elected outer worker group and
kills the whole group at expiry. The outer supervisor retains independent
group-kill/reap duties. This does not constrain a malicious root process which
escapes that group; the real runtime verifier must exclude such descendants.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
import os
import select
import signal
import time

class Refused(ValueError):pass
def need(ok,code):
    if not ok:raise Refused(code)
def instant(value):
    need(type(value)is str and value.endswith('Z'),'DOG_TIME')
    try:return datetime.fromisoformat(value[:-1]+'+00:00')
    except Exception:raise Refused('DOG_TIME')from None
def utc_now():return datetime.now(timezone.utc)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
def kill_group(group):
    os.killpg(group,signal.SIGKILL)
    os._exit(97)

def monitor(read_fd,ready_fd,parent,group,outer_until):
    """No approved bridge or image Python callback runs inside this process."""
    try:
        need(os.getppid()==parent and os.getpgrp()==os.getsid(0)==group and os.getpgid(parent)==group,'DOG_GROUP')
        os.write(ready_fd,b'R');os.close(ready_fd);raw=b'';expiry=None;deadline=None
        while True:
            now,mono=utc_now(),time.monotonic()
            if os.getppid()!=parent or now>=outer_until:kill_group(group)
            if expiry is not None and(now>=expiry or mono>=deadline):kill_group(group)
            remaining=(outer_until-now).total_seconds()
            if expiry is not None:remaining=min(remaining,(expiry-now).total_seconds(),deadline-mono)
            ready=select.select([read_fd],[],[],max(0,min(.01,remaining)))[0]
            if not ready:continue
            data=os.read(read_fd,513)
            if not data:kill_group(group)
            raw+=data;need(len(raw)<=512,'DOG_MESSAGE_LIMIT')
            if not raw.endswith(b'\n'):continue
            body=json.loads(raw);need(canonical(body)+b'\n'==raw,'DOG_CANONICAL');raw=b''
            if body=={'cancel':True}:
                os._exit(0) # Only trusted terminal/abort cleanup owns this pipe.
            need(expiry is None and set(body)=={'observed_at','valid_until'},'DOG_OBSERVATION_ONCE')
            observed,expiry=instant(body['observed_at']),instant(body['valid_until']);now=utc_now()
            need(observed<=now<expiry<=outer_until and 0<(expiry-observed).total_seconds()<=10,'DOG_INTERVAL')
            deadline=time.monotonic()+(expiry-now).total_seconds()
    except BaseException:kill_group(group)

class ImageWatchdog:
    def __init__(self,outer_until,*,fixture_own_group=False):
        self.group=os.getpgrp();self.parent=os.getpid();self.fd=None;self.child=None;self.started=False
        need(os.getsid(0)==self.group and((fixture_own_group and self.parent==self.group)or self.parent!=self.group),'DOG_GROUP')
        read_fd,write_fd=os.pipe();ready_read,ready_write=os.pipe()
        try:
            pid=os.fork()
            if pid==0:
                os.close(write_fd);os.close(ready_read);monitor(read_fd,ready_write,self.parent,self.group,outer_until);os._exit(98)
            self.child,self.fd=pid,write_fd;os.close(read_fd);os.close(ready_write)
            ready=select.select([ready_read],[],[],min(2,max(0,(outer_until-utc_now()).total_seconds())))[0]
            need(bool(ready)and os.read(ready_read,2)==b'R','DOG_WARMUP_UNAVAILABLE');os.set_blocking(self.fd,False)
        except BaseException:self.close();raise
        finally:os.close(ready_read)
    def start(self,observed,until):
        need(not self.started and self.fd is not None and type(observed)is datetime and type(until)is datetime,'DOG_OBSERVATION_ONCE')
        raw=canonical({'observed_at':observed.isoformat().replace('+00:00','Z'),'valid_until':until.isoformat().replace('+00:00','Z')})+b'\n'
        need(len(raw)<=512 and os.write(self.fd,raw)==len(raw),'DOG_PIPE');self.started=True
    def close(self):
        if self.fd is not None:
            try:os.write(self.fd,b'{"cancel":true}\n')
            except OSError:pass
            os.close(self.fd);self.fd=None
        if self.child is not None:
            until=time.monotonic()+.25
            while time.monotonic()<until:
                try:pid,_=os.waitpid(self.child,os.WNOHANG)
                except ChildProcessError:pid=self.child
                if pid:break
                time.sleep(.002)
            else:
                try:os.kill(self.child,signal.SIGKILL)
                except ProcessLookupError:pass
                try:os.waitpid(self.child,0)
                except ChildProcessError:pass
            self.child=None
