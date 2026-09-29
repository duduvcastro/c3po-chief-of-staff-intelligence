"""Single-owner producer lifecycle; not a scheduled or auto-started service.

No network is opened until the caller invokes run_producer. Deployment and
provider-connection authorization are external prerequisites.
"""
from contextlib import contextmanager
import fcntl
import os
import re
import stat
from zoneinfo import ZoneInfo
from .r2d2_v2_sources import SourceUnavailable, _open_directory
from .r2d2_v2_massive_journal import MassiveJournal
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_massive_stream import MassiveStreamState
from .r2d2_v2_massive_recovery import restore_stream
from .r2d2_v2_massive_scheduler import MinuteExpiry
from .r2d2_v2_massive_transport import run_connection


MIN_SESSION_FREE_BYTES=50*1024**3
MAX_SESSION_EVIDENCE_BYTES=512*1024**2
MAX_SESSION_INDEX_BYTES=64*1024**2
MAX_SESSION_EVIDENCE_FILES=500_000


def _storage_usage(directory, *, sessions=False):
    """Descriptor-anchored actual file lengths/allocated blocks, without deletion."""
    from .r2d2_v2_sources import _require
    usage={name:0 for name in ('raw_bytes','receipt_bytes','index_bytes','wal_bytes',
                              'shm_bytes','rollback_bytes','other_bytes','allocated_bytes',
                              'evidence_files')}
    if sessions:usage['retained_sessions']=0
    capacity=os.fstatvfs(directory)
    usage['free_bytes']=capacity.f_bavail*capacity.f_frsize
    def account(info,key):
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink==1
                 and info.st_uid==os.geteuid(),'MASSIVE_SERVICE_STORAGE_UNSAFE')
        usage[key]+=info.st_size
        usage['allocated_bytes']+=info.st_blocks*512
    known={'sequence.sqlite3':'index_bytes','sequence.sqlite3-wal':'wal_bytes',
           'sequence.sqlite3-shm':'shm_bytes','sequence.sqlite3-journal':'rollback_bytes'}
    with os.scandir(directory) as entries:
        for entry in entries:
            if sessions and entry.name.startswith('session_date='):
                from datetime import date
                day=entry.name.removeprefix('session_date=')
                _require(date.fromisoformat(day).isoformat()==day,'MASSIVE_SERVICE_SESSION_PATH')
                usage['retained_sessions']+=1
                _require(usage['retained_sessions']<=256,'MASSIVE_SERVICE_STORAGE_SCAN_LIMIT')
                fd=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                try:child=_storage_usage(fd)
                finally:os.close(fd)
                for key in usage:
                    if key not in ('free_bytes','retained_sessions'):usage[key]+=child[key]
            elif not sessions and entry.name in ('raw','receipts'):
                fd=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory)
                try:
                    with os.scandir(fd) as evidence:
                        for item in evidence:
                            usage['evidence_files']+=1
                            _require(usage['evidence_files']<=MAX_SESSION_EVIDENCE_FILES+1,
                                     'MASSIVE_SERVICE_STORAGE_SCAN_LIMIT')
                            account(item.stat(follow_symlinks=False),
                                    'raw_bytes' if entry.name=='raw' else 'receipt_bytes')
                finally:
                    os.close(fd)
            else:
                account(entry.stat(follow_symlinks=False),known.get(entry.name,'other_bytes'))
    usage['total_bytes']=sum(usage[key] for key in
        ('raw_bytes','receipt_bytes','index_bytes','wal_bytes','shm_bytes','rollback_bytes','other_bytes'))
    return usage


def _storage_refusal(usage):
    if usage['free_bytes']<MIN_SESSION_FREE_BYTES:
        return 'MASSIVE_SERVICE_LOW_DISK'
    if (usage['raw_bytes']+usage['receipt_bytes']>=MAX_SESSION_EVIDENCE_BYTES
            or usage['evidence_files']>=MAX_SESSION_EVIDENCE_FILES):
        return 'MASSIVE_SERVICE_EVIDENCE_LIMIT'
    if sum(usage[key] for key in ('index_bytes','wal_bytes','shm_bytes','rollback_bytes'))>=MAX_SESSION_INDEX_BYTES:
        return 'MASSIVE_SERVICE_INDEX_LIMIT'
    return None


def run_producer(root,symbols,calendar,token,*,utcnow,monotonic,stop,connector=None,max_seconds=8*3600, session_monitor=None, journal_ready=None):
    with journal_access(root,create=True):
        return _run_producer(root,symbols,calendar,token,utcnow=utcnow,monotonic=monotonic,
                             stop=stop,connector=connector,max_seconds=max_seconds,session_monitor=session_monitor,journal_ready=journal_ready)


@contextmanager
def _producer_directory(root):
    directory=_open_directory(root)
    lock=None
    try:
        root_info=os.fstat(directory)
        if root_info.st_mode & 0o077 or root_info.st_uid!=os.geteuid():
            raise SourceUnavailable('MASSIVE_PRODUCER_ROOT_UNSAFE')
        try:
            lock=os.open('producer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,
                         0o600,dir_fd=directory)
        except OSError:
            raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_UNSAFE') from None
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid!=os.geteuid():
            raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_UNSAFE')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SourceUnavailable('MASSIVE_PRODUCER_ALREADY_RUNNING') from None
        if info.st_mode & 0o077:
            raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_UNSAFE')
        # Lock the same inode still named by the anchored root. A renamed lock
        # must not allow a second producer to enter on a new inode.
        try:
            named=os.stat('producer.lock',dir_fd=directory,follow_symlinks=False)
            root_check=_open_directory(root)
        except (OSError, SourceUnavailable):
            raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_CHANGED') from None
        try:
            opened_root=os.fstat(directory);current_root=os.fstat(root_check)
            if ((named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino)
                    or (opened_root.st_dev,opened_root.st_ino)!=(current_root.st_dev,current_root.st_ino)):
                raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_CHANGED')
        finally:
            os.close(root_check)
        yield directory
    finally:
        if lock is not None:os.close(lock)
        os.close(directory)


def _run_producer(root,symbols,calendar,token,*,utcnow,monotonic,stop,connector=None,max_seconds=8*3600, session_monitor=None, journal_ready=None):
    with _producer_directory(root) as directory:
        return _run_locked_producer(root,directory,symbols,calendar,token,utcnow=utcnow,
            monotonic=monotonic,stop=stop,connector=connector,max_seconds=max_seconds,
            session_monitor=session_monitor,journal_ready=journal_ready)


def _run_locked_producer(root,directory,symbols,calendar,token,*,utcnow,monotonic,stop,
                         connector,max_seconds,session_monitor,journal_ready):
    budget_before=None
    try:
        if session_monitor is not None:
            budget_session=utcnow().astimezone(ZoneInfo('America/New_York')).date().isoformat()
            try:
                budget_before=_storage_usage(directory)
            except (OSError,SourceUnavailable):
                pass
            if budget_before is None:
                session_monitor({'status':'DATA_GAP','reason':'MASSIVE_SERVICE_STORAGE_UNVERIFIED',
                                 'session':budget_session,'provider_connected':False})
                raise SourceUnavailable('MASSIVE_SERVICE_STORAGE_UNVERIFIED')
            reason=_storage_refusal(budget_before)
            if reason:
                session_monitor({'status':'DATA_GAP','reason':reason,
                                 'session':budget_session,
                                 'storage':budget_before,'provider_connected':False})
                raise SourceUnavailable(reason)
            session_monitor({'status':'BUDGET_START','session':budget_session,'storage':budget_before,
                             'review_after_sessions':3})
        journal=MassiveJournal(root)
        if journal_ready is not None:journal_ready()
        state=MassiveStreamState(symbols,calendar,journal)
        now=utcnow();session=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        recovered=restore_stream(state,journal,session=session,now=now,allow_prior_sessions=True)
        if recovered['records']:
            # Recovery proves retained evidence, never uninterrupted reception.
            state.gap(now,'MASSIVE_PRODUCER_RESTART')
        scheduler=MinuteExpiry(state,now)
        result=run_connection(state,token,utcnow=utcnow,monotonic=monotonic,
                              tick=scheduler,stop=stop,connector=connector,max_seconds=max_seconds)
        return {'status':result,'recovered_records':recovered['records']}
    finally:
        if budget_before is not None:
            after=None
            try:
                after=_storage_usage(directory)
            except (OSError,SourceUnavailable):
                pass
            if after is None:
                session_monitor({'status':'BUDGET_END','session':budget_session,
                                 'storage_verified':False})
                raise SourceUnavailable('MASSIVE_SERVICE_STORAGE_UNVERIFIED')
            session_monitor({'status':'BUDGET_END','session':budget_session,'storage':after,
                'measured_byte_delta':{name:after[name]-budget_before[name] for name in
                    ('raw_bytes','receipt_bytes','index_bytes','wal_bytes','shm_bytes',
                     'rollback_bytes','total_bytes','allocated_bytes')},
                'review_after_sessions':3})


def run_session(root, manifest, calendar, token_provider, *, utcnow, monotonic,
                stop, supervisor, connector=None):
    """Run one explicitly invoked daily session under the producer lock.

    The caller supplies a reviewed daily manifest, an external secret loader and
    a supervisor receiving credential-free lifecycle events. Nothing schedules,
    installs or restarts this service. The manifest owner is the effective OS
    uid; provider entitlement and deployment authorization remain external.
    """
    from datetime import datetime, timedelta
    from .r2d2_v2_sources import _require
    from .r2d2_v2_minute_bars import _SYMBOL

    _require(type(manifest) is dict and set(manifest)=={'epoch','session','symbols','owner_uid'},
             'MASSIVE_SERVICE_MANIFEST')
    _require(type(manifest['owner_uid']) is int and manifest['owner_uid']==os.geteuid(),
             'MASSIVE_SERVICE_OWNER')
    _require(type(manifest['epoch']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',manifest['epoch']) is not None,
             'MASSIVE_SERVICE_EPOCH')
    epoch=manifest['epoch']
    symbols=manifest['symbols']
    _require(type(symbols) is list and 0<len(symbols)<=550 and
             all(type(s) is str and _SYMBOL.fullmatch(s) for s in symbols) and
             len(set(symbols))==len(symbols), 'MASSIVE_SERVICE_SYMBOLS')
    symbols=list(symbols)  # Freeze the approved daily list before secret loading.
    now=utcnow()
    _require(isinstance(now,datetime) and now.utcoffset() is not None,'MASSIVE_SERVICE_CLOCK')
    day=now.astimezone(ZoneInfo('America/New_York')).date()
    _require(manifest['session']==day.isoformat() and calendar.is_session(day),
             'MASSIVE_SERVICE_SESSION')
    details=calendar.details(day)
    # Keep receiving through the final bar's 90-second post-close allowance.
    deadline=details['close']+timedelta(seconds=91)
    seconds=(deadline-now).total_seconds()
    _require(now<details['close'] and 0<seconds<=8*3600,'MASSIVE_SERVICE_WINDOW')
    _require(callable(token_provider) and callable(supervisor),'MASSIVE_SERVICE_DEPENDENCIES')
    if stop():
        supervisor({'status':'STOPPED','session':day.isoformat()})
        return {'status':'STOPPED','recovered_records':0}
    token=None
    try:
        token=token_provider()
    except Exception:
        pass
    _require(isinstance(token,str) and bool(token) and len(token)<=4096,'STREAM_AUTH_REQUIRED')
    supervisor({'status':'STARTING','session':day.isoformat(),
                'symbols':len(symbols),'deadline':deadline.isoformat()})
    result=None
    try:
        result=_run_session_root(root,epoch,day.isoformat(),symbols,calendar,token,
            utcnow=utcnow,monotonic=monotonic,stop=lambda:stop() or utcnow()>=deadline,
            connector=connector,max_seconds=seconds,supervisor=supervisor)
    except Exception:
        pass
    finally:
        token=None
    if result is None:
        supervisor({'status':'FAILED','session':day.isoformat()})
        raise SourceUnavailable('MASSIVE_SERVICE_FAILURE')
    supervisor({'status':result['status'],'session':day.isoformat()})
    return result


def _run_session_root(root,epoch,session,symbols,calendar,token,*,utcnow,monotonic,
                      stop,connector,max_seconds,supervisor):
    from .r2d2_v2_massive_sessions import SessionJournalRoot
    # This parent lock prevents concurrent processes opening different daily
    # children. Child producer/maintenance locks retain their existing semantics.
    with _producer_directory(root) as directory:
        before=None
        try:
            before=_storage_usage(directory,sessions=True)
        except (OSError,SourceUnavailable,ValueError):
            pass
        if before is None or before['free_bytes']<MIN_SESSION_FREE_BYTES:
            reason='MASSIVE_SERVICE_STORAGE_UNVERIFIED' if before is None else 'MASSIVE_SERVICE_LOW_DISK'
            supervisor({'status':'DATA_GAP','reason':reason,'epoch':epoch,'session':session,
                        'storage':before,'provider_connected':False})
            raise SourceUnavailable(reason)
        supervisor({'status':'RETAINED_BUDGET_START','epoch':epoch,'session':session,
                    'storage':before,'review_after_sessions':3})
        try:
            journals=SessionJournalRoot(root,epoch,create=True)
            child=journals.prepare_session(session,symbols)
            return run_producer(child,symbols,calendar,token,utcnow=utcnow,monotonic=monotonic,
                stop=stop,connector=connector,max_seconds=max_seconds,session_monitor=supervisor,
                journal_ready=lambda:journals.mark_ready(session))
        finally:
            after=None
            try:
                after=_storage_usage(directory,sessions=True)
            except (OSError,SourceUnavailable,ValueError):
                pass
            supervisor({'status':'RETAINED_BUDGET_END','epoch':epoch,'session':session,
                'storage':after,'storage_verified':after is not None,'review_after_sessions':3,
                'measured_byte_delta':None if after is None else {
                    key:after[key]-before[key] for key in
                    ('raw_bytes','receipt_bytes','index_bytes','wal_bytes','shm_bytes',
                     'rollback_bytes','total_bytes','allocated_bytes')}})
            if after is None:raise SourceUnavailable('MASSIVE_SERVICE_STORAGE_UNVERIFIED')


def main(argv=None):
    """Explicit one-session process entrypoint for an external supervisor."""
    import argparse
    import json
    import signal
    import time
    from datetime import datetime, timezone
    from threading import Event
    from .r2d2_v2_calendar import ShadowCalendar
    from .r2d2_v2_sources import _load_json, _require

    parser=argparse.ArgumentParser(description='Run one approved Massive daily session')
    parser.add_argument('--journal-root',required=True)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--token-env',default='MASSIVE_API_KEY')
    args=parser.parse_args(argv)
    stopped=Event()
    previous={}
    def notice(event):
        print(json.dumps(event,sort_keys=True),flush=True)
    try:
        # Private regular manifest, bounded read, no symlink/FIFO following.
        fd=os.open(args.manifest,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info=os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
                     and not info.st_mode&0o022 and info.st_size<=65536,
                     'MASSIVE_SERVICE_MANIFEST')
            manifest=_load_json(os.read(fd,65537))
        finally:
            os.close(fd)
        for sig in (signal.SIGINT,signal.SIGTERM):
            previous[sig]=signal.signal(sig,lambda *_:stopped.set())
        result=run_session(args.journal_root,manifest,ShadowCalendar(),
                           lambda:os.environ.get(args.token_env),
                           utcnow=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
                           stop=stopped.is_set,supervisor=notice)
        return 0 if result['status'] in ('STOPPED','SESSION_LIMIT') else 1
    except Exception:
        # Never serialize exceptions, their traceback, manifest or credentials.
        notice({'status':'FAILED','reason':'MASSIVE_SERVICE_FAILURE'})
        return 1
    finally:
        for sig,handler in previous.items():
            signal.signal(sig,handler)


if __name__=='__main__':
    raise SystemExit(main())
