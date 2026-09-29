"""One supervised attempt; no network or installation on import.

systemd owns the 30-second restart backoff. Durable per-session claims cap even
manual service restarts at four attempts; existing claims are never deleted.
"""
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from zoneinfo import ZoneInfo

from .r2d2_v2_sources import SourceUnavailable, _load_json, _open_directory, _require
from .r2d2_v2_massive_producer import _producer_directory, run_session

MAX_ATTEMPTS = 4
TERMINAL_EXIT = 78


def private_bytes(path, maximum):
    path=Path(path)
    directory=_open_directory(path.parent)
    try:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            info=os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1
                     and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600
                     and 0<info.st_size<=maximum,'SUPERVISOR_PRIVATE_FILE')
            raw=os.read(fd,maximum+1)
            after=os.fstat(fd);named=os.stat(path.name,dir_fd=directory,follow_symlinks=False)
            identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink)
            _require(len(raw)==info.st_size and identity(info)==identity(after)==identity(named),
                     'SUPERVISOR_FILE_CHANGED')
            return raw
        finally:os.close(fd)
    finally:os.close(directory)


def supervised_attempt(journal_root,manifest_directory,token_file,state_root,*,calendar,
                       utcnow,monotonic,stop,notice,runner=run_session):
    """Exit 78 is terminal configuration/window/cap refusal; 1 requests restart.

    Claims persist across failures and reboots. The approved dated manifest is
    byte-bound on the first claim; changing it never resets the daily allowance.
    """
    provider_attempted=False
    day=utcnow().astimezone(ZoneInfo('America/New_York')).date()
    try:
        _require(calendar.is_session(day),'SUPERVISOR_SESSION')
        details=calendar.details(day)
        _require(details['open']-timedelta(seconds=60)<=utcnow()<details['close'],
                 'SUPERVISOR_WINDOW')
        manifest_raw=private_bytes(Path(manifest_directory)/(day.isoformat()+'.json'),65536)
        manifest=_load_json(manifest_raw)
        _require(manifest.get('session')==day.isoformat()
                 and manifest.get('owner_uid')==os.geteuid(),'SUPERVISOR_MANIFEST')
        binding=hashlib.sha256(manifest_raw).hexdigest()
        with _producer_directory(Path(state_root)) as directory:
            # All claims are exclusive and fsynced before secret loading/network.
            attempt=1
            while attempt<=MAX_ATTEMPTS:
                name=day.isoformat()+'.attempt-'+str(attempt)+'.json'
                try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
                except FileExistsError:
                    previous=_load_json(private_bytes(Path(state_root)/name,65536))
                    _require(previous.get('manifest_sha256')==binding,'SUPERVISOR_MANIFEST_CHANGED')
                    attempt+=1;continue
                with os.fdopen(fd,'wb') as output:
                    output.write(json.dumps({'session':day.isoformat(),'attempt':attempt,
                        'manifest_sha256':binding,'automatic_restart_limit':MAX_ATTEMPTS},sort_keys=True).encode())
                    output.flush();os.fsync(output.fileno())
                os.fsync(directory)
                break
            _require(attempt<=MAX_ATTEMPTS,'SUPERVISOR_ATTEMPTS_EXHAUSTED')
            token=private_bytes(token_file,4096).decode('utf-8').strip()
            _require(bool(token) and '\n' not in token and '\r' not in token,'SUPERVISOR_TOKEN')
            notice({'status':'ATTEMPT','session':day.isoformat(),'attempt':attempt,'maximum':MAX_ATTEMPTS})
            try:
                provider_attempted=True
                result=runner(Path(journal_root),manifest,calendar,lambda:token,
                    utcnow=utcnow,monotonic=monotonic,stop=stop,supervisor=notice)
                return 0 if result['status'] in ('STOPPED','SESSION_LIMIT') else 1
            except Exception:
                notice({'status':'FAILED','session':day.isoformat(),'reason':'SUPERVISOR_PRODUCER_FAILURE'})
                return 1
            finally:token=None
    except Exception:
        # No exception text, token, provider output or arbitrary file bytes.
        notice({'status':'DATA_GAP','session':day.isoformat(),'reason':'SUPERVISOR_REFUSED',
                'provider_connected':None if provider_attempted else False,'restart_allowed':False})
        return TERMINAL_EXIT


def main(argv=None):
    import argparse
    from datetime import datetime,timezone
    from threading import Event
    import signal
    import time
    from .r2d2_v2_calendar import ShadowCalendar
    parser=argparse.ArgumentParser(description='One bounded supervised Massive session attempt')
    for name in ('journal-root','manifest-directory','token-file','state-root'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args(argv);stopped=Event();previous={}
    try:
        for sig in (signal.SIGINT,signal.SIGTERM):
            previous[sig]=signal.signal(sig,lambda *_:stopped.set())
        return supervised_attempt(args.journal_root,args.manifest_directory,args.token_file,args.state_root,
            calendar=ShadowCalendar(),utcnow=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
            stop=stopped.is_set,notice=lambda event:print(json.dumps(event,sort_keys=True),flush=True))
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)


if __name__=='__main__':raise SystemExit(main())
