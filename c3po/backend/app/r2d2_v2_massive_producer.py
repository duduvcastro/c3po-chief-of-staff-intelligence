"""Single-owner producer lifecycle; not a scheduled or auto-started service.

No network is opened until the caller invokes run_producer. Deployment and
provider-connection authorization are external prerequisites.
"""
import fcntl
import os
import stat
from zoneinfo import ZoneInfo
from .r2d2_v2_sources import SourceUnavailable, _open_directory
from .r2d2_v2_massive_journal import MassiveJournal
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_massive_stream import MassiveStreamState
from .r2d2_v2_massive_recovery import restore_stream
from .r2d2_v2_massive_scheduler import MinuteExpiry
from .r2d2_v2_massive_transport import run_connection


def run_producer(root,symbols,calendar,token,*,utcnow,monotonic,stop,connector=None,max_seconds=3600):
    with journal_access(root,create=True):
        return _run_producer(root,symbols,calendar,token,utcnow=utcnow,monotonic=monotonic,
                             stop=stop,connector=connector,max_seconds=max_seconds)


def _run_producer(root,symbols,calendar,token,*,utcnow,monotonic,stop,connector=None,max_seconds=3600):
    directory=_open_directory(root)
    lock=None
    try:
        try:
            lock=os.open('producer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,
                         0o600,dir_fd=directory)
        except OSError:
            raise SourceUnavailable('MASSIVE_PRODUCER_LOCK_UNSAFE') from None
        info=os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
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
        journal=MassiveJournal(root)
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
        if lock is not None:os.close(lock)
        os.close(directory)
