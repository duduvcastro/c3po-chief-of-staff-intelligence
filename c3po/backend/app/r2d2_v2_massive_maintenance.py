"""Cooperative maintenance exclusion primitive; no file deletion or scheduling."""
from contextlib import contextmanager
import fcntl
import os
import stat
from .r2d2_v2_sources import _open_directory, SourceUnavailable


@contextmanager
def journal_access(root, *, exclusive=False, create=False):
    """Fail immediately if another cooperating user holds an incompatible lock.

    Readers open only an existing lock; initialization is explicit. All producer
    and reader call sites must participate before this can protect pruning.
    """
    if type(exclusive) is not bool or type(create) is not bool:
        raise SourceUnavailable('MASSIVE_MAINTENANCE_POLICY')
    directory = _open_directory(root)
    lock = None
    try:
        root_info=os.fstat(directory)
        if root_info.st_mode & 0o077 or root_info.st_uid != os.geteuid():
            raise SourceUnavailable('MASSIVE_MAINTENANCE_ROOT')
        flags=(os.O_RDWR | os.O_CREAT) if create else os.O_RDONLY
        try:
            lock=os.open('maintenance.lock',flags|os.O_NOFOLLOW|os.O_NONBLOCK,
                         0o600,dir_fd=directory)
            info=os.fstat(lock)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1
                    or info.st_mode & 0o077 or info.st_uid!=os.geteuid()):
                raise SourceUnavailable('MASSIVE_MAINTENANCE_UNSAFE')
            fcntl.flock(lock,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SourceUnavailable('MASSIVE_MAINTENANCE_BUSY') from None
        except OSError:
            raise SourceUnavailable('MASSIVE_MAINTENANCE_UNSAFE') from None
        def verify():
            named=os.stat('maintenance.lock',dir_fd=directory,follow_symlinks=False)
            check=_open_directory(root)
            try:
                current=os.fstat(check)
                if ((named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino)
                        or (current.st_dev,current.st_ino)!=(root_info.st_dev,root_info.st_ino)
                        or not stat.S_ISREG(named.st_mode) or named.st_nlink!=1
                        or named.st_mode & 0o077):
                    raise SourceUnavailable('MASSIVE_MAINTENANCE_CHANGED')
            finally:
                os.close(check)
        verify()
        yield
        verify()
    finally:
        if lock is not None:os.close(lock)
        os.close(directory)
