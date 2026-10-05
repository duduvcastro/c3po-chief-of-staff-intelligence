import fcntl

# The deployment lock of this host is an advisory flock on one file of the deploy tree; the pipeline's deploy job and
# the security controller take it exclusively before they touch the compose project. A run that recreates a
# container holds it for the time of the effect; a read-only run may only ask whether it is free.
LOCK_POLL_SECONDS=.25
MAX_LOCK_WAIT_SECONDS=20
LOCK_SCOPE={'kind':'flock on a descriptor opened read-only and without following a link; the file is never created, written or removed',
            'max_wait_seconds':MAX_LOCK_WAIT_SECONDS,'poll_seconds':LOCK_POLL_SECONDS,
            'released':'explicitly, and in any case when the process ends',
            'probe':'a shared, non-blocking request released at once: it fails only while another process holds the lock exclusively; '
                    'for that instant a non-blocking exclusive request of another process fails as well'}

class NativeLock:
    """The two calls of the lock: a non-blocking flock on a held descriptor, and the pause between two attempts."""
    def flock(self,fd,operation):fcntl.flock(fd,operation)
    def pause(self,seconds):time.sleep(seconds)

def open_lock(host,name,directory,check):
    """The lock file, opened read-only by dir_fd without following a link: a regular file with one link that the name
    still shows. Returns the descriptor. The file is never created here: an absent lock file is a refusal."""
    check()
    try:named=host.lstat(name,directory.fd)
    except FileNotFoundError:raise Refused('LOCK_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1,'LOCK_FILE_NOT_REGULAR')
    check();fd=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory.fd)
    try:
        held=host.fstat(fd)
        need(stat.S_ISREG(held.st_mode) and (held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'LOCK_FILE_REPLACED')
        return fd
    except BaseException:
        host.close(fd);raise

def lock_still_named(host,name,directory,fd):
    """True while the name still shows the file whose descriptor holds the lock (a lock on a replaced file excludes nobody)."""
    try:
        named=host.lstat(name,directory.fd);held=host.fstat(fd)
        return bool(stat.S_ISREG(named.st_mode) and (named.st_dev,named.st_ino)==(held.st_dev,held.st_ino))
    except OSError:return False

def acquire_lock(host,fd,gate,wait_seconds,keep_seconds):
    """Exclusive lock, asked for without blocking and again every LOCK_POLL_SECONDS. It gives up, with nothing
    changed, after wait_seconds or as soon as less than keep_seconds of the budget would be left for what the lock
    is taken for. Returns the number of attempts. Taking the lock changes nothing on disk; the caller releases it."""
    need(integer(wait_seconds,0,MAX_LOCK_WAIT_SECONDS) and integer(keep_seconds,0,MAX_SECONDS),'LOCK_WAIT_INVALID')
    budget=gate();need(budget>keep_seconds,'LOCK_NOT_TAKEN_BUDGET')
    limit=budget-min(wait_seconds,budget-keep_seconds);attempts=0;most=int(wait_seconds/LOCK_POLL_SECONDS)+1
    while True:
        attempts+=1
        try:host.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return attempts
        except OSError as error:
            need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')
        # The budget only falls: once another pause would take it to the limit, the wait is over. The number of
        # attempts is bounded as well, so a clock that stands still cannot make the wait endless.
        need(attempts<most and gate()-LOCK_POLL_SECONDS>limit,'DEPLOY_LOCK_BUSY')
        host.pause(LOCK_POLL_SECONDS)

def release_lock(host,fd):
    """Unlock and close. Never raises: the lock ends with the descriptor in any case."""
    try:host.flock(fd,fcntl.LOCK_UN)
    except Exception:pass
    try:host.close(fd)
    except Exception:pass

def probe_lock(host,fd):
    """'FREE' or 'BUSY': a shared, non-blocking request, released at once. For a source that changes nothing."""
    try:host.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
    except OSError as error:
        need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')
        return 'BUSY'
    host.flock(fd,fcntl.LOCK_UN);return 'FREE'
