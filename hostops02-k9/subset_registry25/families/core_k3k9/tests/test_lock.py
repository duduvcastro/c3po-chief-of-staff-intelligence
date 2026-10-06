"""parts/lock.py: the deployment lock. On the emulated host (who holds it, for how long, what the budget allows) and
with the real flock of this machine on a private temporary file (two open file descriptions of one file exclude each
other exactly as two processes do)."""
import fcntl
import os
import time
import types

import pytest

import demos
import family as f
import hostemu

M=lambda:f.load(demos.WRITE).m
refusal=f.refusal
PATH=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME

class Bench:
    def __init__(self):
        self.m=m=M();self.host=host=f.wire(types.SimpleNamespace(m=m),hostemu.world());self.elapsed=0.0;self.budget=60.0
        rows=hostemu.rows(host,hostemu.LOCK_DIRECTORY);self.directory=m.Pinned(host,m.walk_pinned(host,rows,self.gate,[]),rows=rows)
        host.on_pause=lambda host:setattr(self,'elapsed',host.paused);host.log.clear()
    def gate(self):
        if self.budget-self.elapsed<=0:raise self.m.Refused('GO_EXPIRED')
        return self.budget-self.elapsed
    def open(self,name=hostemu.LOCK_NAME):return self.m.open_lock(self.host,name,self.directory,self.gate)
    def acquire(self,fd,wait=20,keep=34):return self.m.acquire_lock(self.host,fd,self.gate,wait,keep)

def test_lock_file_is_opened_read_only_by_descriptor_and_never_created():
    bench=Bench();fd=bench.open();opened=[entry for entry in bench.host.log if entry[0]=='open'][-1]
    assert opened[1]==PATH and opened[2]==os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK and bench.host.mutating()==[]
    assert refusal(lambda:bench.open('no-such.lock'))=='LOCK_FILE_ABSENT' and 'no-such.lock' not in bench.host.tree.get(hostemu.LOCK_DIRECTORY).children
    bench.host.tree.add(hostemu.LOCK_DIRECTORY+'/dir.lock');assert refusal(lambda:bench.open('dir.lock'))=='LOCK_FILE_NOT_REGULAR'
    bench.host.tree.add(hostemu.LOCK_DIRECTORY+'/link.lock',kind='symlink');assert refusal(lambda:bench.open('link.lock'))=='LOCK_FILE_NOT_REGULAR'
    bench.host.tree.get(PATH).nlink=2;assert refusal(bench.open)=='LOCK_FILE_NOT_REGULAR'
    # replaced between the lstat and the open: the descriptor is closed again and nothing is locked
    bench=Bench();count=len(bench.host.fds)
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]==PATH:host.tree.get(PATH).ino+=1
    bench.host.hook=hook;assert refusal(bench.open)=='LOCK_FILE_REPLACED' and len(bench.host.fds)==count

def test_free_lock_is_taken_at_once_held_until_released_and_released_by_close_as_well():
    bench=Bench();fd=bench.open();assert bench.acquire(fd)==1 and bench.host.lock_held(PATH)=='EX' and bench.host.paused==0
    assert [entry[2] for entry in bench.host.log if entry[0]=='flock']==[fcntl.LOCK_EX|fcntl.LOCK_NB]
    assert bench.m.lock_still_named(bench.host,hostemu.LOCK_NAME,bench.directory,fd) is True
    bench.m.release_lock(bench.host,fd);assert bench.host.lock_held(PATH) is None and fd not in bench.host.fds
    bench.m.release_lock(bench.host,fd)                                               # a second release never raises
    fd=bench.open();bench.acquire(fd);bench.host.close(fd);assert bench.host.lock_held(PATH) is None
    assert bench.host.mutating()==[] and bench.host.tree.get(PATH).content==bytearray()

def test_lock_on_a_file_that_was_replaced_excludes_nobody_and_is_reported():
    bench=Bench();fd=bench.open();bench.acquire(fd);bench.host.tree.get(hostemu.LOCK_DIRECTORY).children[hostemu.LOCK_NAME]=hostemu.Node('file',dev=hostemu.ROOT_DEVICE,ino=999999)
    assert bench.m.lock_still_named(bench.host,hostemu.LOCK_NAME,bench.directory,fd) is False
    bench.host.tree.remove(PATH);assert bench.m.lock_still_named(bench.host,hostemu.LOCK_NAME,bench.directory,fd) is False

def test_busy_lock_is_waited_for_in_quarter_seconds_and_taken_when_the_holder_lets_go():
    bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX';bench.host.lock_released_after=5
    assert bench.acquire(fd)==6 and bench.host.paused==1.25 and bench.host.lock_held(PATH)=='EX'
    assert [entry[1] for entry in bench.host.log if entry[0]=='pause']==[.25]*5

def test_wait_ends_after_the_signed_seconds_with_nothing_changed():
    for wait,attempts in ((20,80),(5,20),(1,4),(0,1)):
        bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX'
        assert refusal(lambda:bench.acquire(fd,wait=wait,keep=10))=='DEPLOY_LOCK_BUSY'
        assert len([entry for entry in bench.host.log if entry[0]=='flock'])==attempts and bench.host.lock_held(PATH) is None and wait-.25<=bench.host.paused<=wait
        assert bench.host.mutating()==[]

def test_wait_never_eats_the_time_the_effect_needs():
    """keep is what must be left when the lock is held. With 60 s of budget and 49 to keep, the wait is 11 s whatever
    the signed wait says; with less than keep left, the lock is not even asked for."""
    bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX'
    assert refusal(lambda:bench.acquire(fd,wait=20,keep=49))=='DEPLOY_LOCK_BUSY' and 10.5<=bench.host.paused<=11 and bench.gate()>=49
    bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX';bench.host.lock_released_after=40       # released after 10 s
    assert bench.acquire(fd,wait=20,keep=49)==41 and bench.gate()>=49
    bench=Bench();fd=bench.open();bench.budget=30.0
    assert refusal(lambda:bench.acquire(fd,wait=20,keep=34))=='LOCK_NOT_TAKEN_BUDGET' and [entry for entry in bench.host.log if entry[0]=='flock']==[]
    bench=Bench();fd=bench.open();bench.budget=34.0;assert refusal(lambda:bench.acquire(fd,wait=20,keep=34))=='LOCK_NOT_TAKEN_BUDGET'
    bench=Bench();fd=bench.open();bench.budget=34.1;assert bench.acquire(fd,wait=20,keep=34)==1,'a free lock needs no wait'

def test_a_clock_that_stands_still_cannot_make_the_wait_endless():
    bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX';bench.host.on_pause=None            # the budget never falls
    assert refusal(lambda:bench.acquire(fd,wait=20,keep=10))=='DEPLOY_LOCK_BUSY' and len([entry for entry in bench.host.log if entry[0]=='flock'])==81

def test_wait_arguments_and_other_lock_errors():
    bench=Bench();fd=bench.open()
    for wait,keep in ((21,10),(-1,10),(20.0,10),(True,10),(20,61),(20,-1),(None,10),(20,None)):assert refusal(lambda:bench.acquire(fd,wait=wait,keep=keep))=='LOCK_WAIT_INVALID'
    def hook(host,name,detail,calls):
        if name=='flock':raise OSError(5,'injected')
    bench.host.hook=hook;assert refusal(lambda:bench.acquire(fd))=='LOCK_UNAVAILABLE' and refusal(lambda:bench.m.probe_lock(bench.host,fd))=='LOCK_UNAVAILABLE'
    bench=Bench();fd=bench.open();bench.host.lock_holder[PATH]='EX';bench.budget=45.0
    def expire(host):bench.elapsed=100.0
    bench.host.on_pause=expire;assert refusal(lambda:bench.acquire(fd,wait=20,keep=10))=='GO_EXPIRED'

def test_probe_says_free_or_busy_and_holds_nothing_afterwards():
    bench=Bench();fd=bench.open();assert bench.m.probe_lock(bench.host,fd)=='FREE' and bench.host.lock_held(PATH) is None
    assert [entry[2] for entry in bench.host.log if entry[0]=='flock']==[fcntl.LOCK_SH|fcntl.LOCK_NB,fcntl.LOCK_UN]
    bench.host.lock_holder[PATH]='EX';assert bench.m.probe_lock(bench.host,fd)=='BUSY' and bench.host.lock_held(PATH) is None
    bench.host.lock_holder[PATH]='SH';assert bench.m.probe_lock(bench.host,fd)=='FREE','a shared holder does not make the lock busy for a deploy that is not running'


# ---------------------------------------------------------------- the real flock of this machine
class Real:
    """The module's own NativeLock and NativeRead on a private temporary file."""
    def __init__(self,tmp_path):
        self.m=m=M();self.native=m.Native();self.path=tmp_path/'deployment.lock';self.path.write_bytes(b'');self.path.chmod(0o644)
    def open(self):return os.open(str(self.path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)

def test_real_flock_on_a_read_only_descriptor_excludes_another_open_of_the_same_file(tmp_path):
    real=Real(tmp_path);m=real.m;mine=real.open();theirs=real.open();before=(real.path.stat().st_mtime_ns,real.path.stat().st_size)
    try:
        assert m.acquire_lock(real.native,mine,lambda:60.0,0,10)==1
        assert m.probe_lock(real.native,theirs)=='BUSY'
        started=time.monotonic()
        with pytest.raises(m.Refused,match='DEPLOY_LOCK_BUSY'):m.acquire_lock(real.native,theirs,lambda:60.0,1,10)
        assert .7<=time.monotonic()-started<=2.5,'four attempts a quarter second apart'
        fcntl.flock(mine,fcntl.LOCK_UN);assert m.probe_lock(real.native,theirs)=='FREE' and m.acquire_lock(real.native,theirs,lambda:60.0,0,10)==1
        assert m.probe_lock(real.native,mine)=='BUSY'
    finally:
        os.close(mine);m.release_lock(real.native,theirs)
    with pytest.raises(OSError):os.fstat(theirs)                                       # released and closed
    assert (real.path.stat().st_mtime_ns,real.path.stat().st_size)==before,'taking the lock changes nothing of the file'

def test_real_lock_is_not_inherited_by_a_command_the_runner_starts(tmp_path):
    """The descriptor that holds the lock is not passed to a child: the child cannot keep the lock after this process ends."""
    real=Real(tmp_path);m=real.m;mine=real.open()
    try:
        m.acquire_lock(real.native,mine,lambda:60.0,0,10)
        code,out=real.native.run(['/bin/sh','-c','ls /dev/fd'],lambda:30.0,10)
        assert code==0 and str(mine).encode() not in out.split() and os.get_inheritable(mine) is False
    finally:m.release_lock(real.native,mine)

def test_real_lock_waits_until_the_other_holder_releases(tmp_path):
    import threading
    real=Real(tmp_path);m=real.m;mine=real.open();theirs=real.open();fcntl.flock(theirs,fcntl.LOCK_EX|fcntl.LOCK_NB)
    timer=threading.Timer(0.6,lambda:fcntl.flock(theirs,fcntl.LOCK_UN));timer.start()
    try:
        started=time.monotonic();attempts=m.acquire_lock(real.native,mine,lambda:60.0,5,10)
        assert 2<=attempts<=6 and .4<=time.monotonic()-started<=2.5
    finally:
        timer.cancel();m.release_lock(real.native,mine);os.close(theirs)
