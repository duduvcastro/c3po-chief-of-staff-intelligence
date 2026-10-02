"""The real system calls of K6a, made by the source's own unmodified Native on a private temporary tree that stands in
for '/' (the core's tests/oslevel.py records every call with the arguments the kernel received). The docker CLI alone
is answered by the emulated engine (tests/native_engine.py). On the workstation this proves the real mkdir, open, link,
unlink, fsync, flock and sleep with the errno values of macOS as an ordinary user reported as root; the kernel's
O_NOATIME, Linux errno values and real uid 0 only when this suite runs as root on Linux (the CI job)."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import hostemu
import k6a
import native_child
import native_engine
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
LIVE=k6a.LIVE;LOCK=k6a.LOCK

@pytest.fixture
def tree(tmp_path):return native_engine.build(Path(str(tmp_path)).resolve()/'root')

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
def run(root,change=None,real=False):
    """One run in this process: the real Native for every file call; no real pause unless asked."""
    k=k6a.load();fields=native_engine.fields(root);pauses=[]
    if change is not None:change(fields)
    host,emulated=native_engine.engine(k,root,pause=None if real else pauses);old=os.umask(0o027);docs=f.Docs(k,fields)
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(host,**(native_engine.real_clocks(docs) if real else {}))
    finally:os.umask(old)
    receipt['_calls']=record.calls;receipt['_pauses']=pauses;receipt['_engine']=emulated;return receipt
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_primitives(calls):
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens),'every open is O_NOFOLLOW'
    assert all(not entry['flags']&READ_ONLY_OPEN for entry in opens),'a read open carries no write, create or truncate flag'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat']
    assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats),'every stat is an lstat relative to a held descriptor'
    assert all(entry['path']!='?' for entry in calls if entry['call'] in ('fstat','fsync','flock')),'fstat, fsync and flock act on a descriptor this run opened'
    assert all(entry['by_fd'] for entry in calls if entry['call']=='scandir'),'directories are listed through a held descriptor'

def test_native_complete_run_makes_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(native_engine.fields(tree)).encode())
    done=subprocess.run([sys.executable,'-B',str(Path(native_child.__file__)),str(tree),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','ACTIVATE_WORKER_RECREATED_AND_VERIFIED',None),receipt
    assert receipt['recreate']['facts']['settle_pause_taken'] is True and receipt['recreate']['facts']['milliseconds_between_checks']>=3000,'a real pause of three seconds'
    base=tree/LIVE[1:];assert sorted(item.name for item in base.iterdir())==['compose.override.json','policy.json'] and stat.S_IMODE(os.lstat(base).st_mode)==0o700
    for name,raw in (('policy.json',k6a.POLICY),('compose.override.json',k6a.override())):
        info=os.lstat(base/name);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode),(base/name).read_bytes())==(0o600,1,True,raw)
    assert_read_primitives(calls);go16=receipt['go_sha256'][:16]
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[('mkdir',LIVE),
        ('open',LIVE+'/.hostops-%s-0.partial'%go16),('link',LIVE+'/policy.json'),('unlink',LIVE+'/.hostops-%s-0.partial'%go16),
        ('open',LIVE+'/.hostops-%s-1.partial'%go16),('link',LIVE+'/compose.override.json'),('unlink',LIVE+'/.hostops-%s-1.partial'%go16)]
    assert all(entry['by_dir_fd'] for entry in changing) and changing[0]['mode']==0o700
    for entry in changing:
        if entry['call']=='open':assert entry['flags']&(os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW)==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW and entry['mode']==0o600
        if entry['call']=='link':assert entry['follow_symlinks'] is False and entry['same_directory']
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    # the lock: one read-only open of the lock file, one exclusive non-blocking request before the mkdir, one release after the last call on the files
    locks=[(index,entry) for index,entry in enumerate(calls) if entry['call']=='flock']
    assert [(entry['path'],entry['operation']) for _,entry in locks]==[(LOCK,fcntl.LOCK_EX|fcntl.LOCK_NB),(LOCK,fcntl.LOCK_UN)]
    first=[index for index,entry in enumerate(calls) if entry['call']=='mkdir'][0];last=max(index for index,entry in enumerate(calls) if entry['call'] in ('fsync','unlink','link'))
    assert locks[0][0]<first and locks[1][0]>last
    opened=[entry for entry in calls if entry['call']=='open' and entry['path']==LOCK]
    assert len(opened)==1 and opened[0]['flags']&(os.O_WRONLY|os.O_RDWR|os.O_CREAT)==0 and opened[0]['flags']&os.O_NOFOLLOW
    # the files that are read and never written: opened without a write flag, and exactly as they were afterwards
    for path in (hostemu.ENV_FILE,hostemu.DEPLOY+'/.deploy-version',k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME):
        found=[entry for entry in calls if entry['call']=='open' and entry['path']==path]
        assert found and all(not entry['flags']&READ_ONLY_OPEN and entry['flags']&os.O_NOFOLLOW and entry['flags']&os.O_NONBLOCK for entry in found),path
    # the interpreter's own audit events: nothing but these creations; no process, no chmod, chown, rename or truncate
    kinds=sorted({event[0] for event in events});assert kinds==['open-for-writing','os.link','os.mkdir','os.remove'],kinds
    after=snapshot(tree);inside=LIVE[1:]
    assert {name:value for name,value in after.items() if not name.startswith(inside) and name!=k6a.LIVE_PARENT[1:]}=={name:value for name,value in before.items() if name!=k6a.LIVE_PARENT[1:]}
    assert sorted(set(after)-set(before))==[inside,inside+'/compose.override.json',inside+'/policy.json']
    assert result['commands'][8]==['compose','--project-name'] and len(result['commands'])==13

def test_native_refusals_on_real_links_fifos_and_hard_links(tree):
    data=tree/hostemu.DATA[1:];release=tree/k6a.RELEASE_DIRECTORY[1:];deploy=tree/hostemu.DEPLOY[1:]
    def refused(code,signed=None):
        before=snapshot(tree);receipt=run(tree,change=None if signed is None else lambda fields:fields.update(signed))
        assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'PRECHECK'),receipt['code']
        assert snapshot(tree)==before and receipt['mutating_calls']['issued']==0 and not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink')]
        assert not [entry for entry in receipt['_engine'].commands if 'up' in entry['argv']]
    # the destination exists
    (tree/LIVE[1:]).mkdir();refused('DESTINATION_PRESENT');(tree/LIVE[1:]).rmdir()
    os.symlink('elsewhere',tree/LIVE[1:]);refused('DESTINATION_PRESENT');os.unlink(tree/LIVE[1:])
    # the release: a link to a directory with the same bytes, a fifo, a second hard link, a file open to others
    os.rename(release,data/'real');os.symlink('real',release);refused('RELEASE_DIRECTORY_NOT_AS_INSTALLED');os.unlink(release);os.rename(data/'real',release)
    name=release/k6a.RELEASE_NAME
    os.rename(name,release/'kept');os.mkfifo(name,0o600);refused('RELEASE_FILE_NOT_AS_INSTALLED');os.unlink(name)
    os.symlink('kept',name);refused('RELEASE_FILE_NOT_AS_INSTALLED');os.unlink(name);os.rename(release/'kept',name)
    os.link(name,release/'second');refused('RELEASE_FILE_NOT_AS_INSTALLED');os.unlink(release/'second')
    os.chmod(name,0o644);refused('RELEASE_FILE_NOT_AS_INSTALLED');os.chmod(name,0o600)
    os.chmod(release,0o755);refused('RELEASE_DIRECTORY_NOT_AS_INSTALLED');os.chmod(release,0o700)
    # the environment file: a fifo (never opened: a read would block), a link
    env=deploy/'.env';os.rename(env,deploy/'kept.env')
    os.mkfifo(env,0o600);refused('ENV_FILE_NOT_REGULAR');os.unlink(env)
    os.symlink('kept.env',env);refused('ENV_FILE_NOT_REGULAR');os.unlink(env);os.rename(deploy/'kept.env',env)
    # the lock file: a link
    lock=tree/LOCK[1:];os.rename(lock,str(lock)+'.kept');os.symlink('deployment.lock.kept',lock);refused('LOCK_FILE_NOT_REGULAR');os.unlink(lock);os.rename(str(lock)+'.kept',lock)
    # a symbolic link in a signed chain: the rows are signed while the data root is a directory, and the link takes its
    # place afterwards. Rows read from the link itself would carry the link's own mode (0777 on Linux, whatever the
    # umask), which the plan refuses before any walk (CHAIN_ROW_WORLD_WRITABLE): another case, test_plan.py's
    signed=native_engine.fields(tree)
    os.rename(data,tree/'mnt/real');os.symlink('real',data);refused('PARENT_SYMLINK_COMPONENT',signed);os.unlink(data);os.rename(tree/'mnt/real',data)
    # the pin
    os.unlink(data/'.r2d2-v2-pinned');refused('MAINTENANCE_PIN_ABSENT');(data/'.r2d2-v2-pinned').write_bytes(b'')
    # a reboot marker
    (tree/'run/c3po-security').mkdir(parents=True);(tree/'run/c3po-security/reboot.pending').write_bytes(b'');refused('SECURITY_REBOOT_PENDING')
    os.unlink(tree/'run/c3po-security/reboot.pending')
    receipt=run(tree);assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['_pauses']==[3],'and with everything put back the run completes'

def test_native_lock_held_by_another_open_file_description_is_waited_for_and_then_refused(tree):
    """A real flock held through another descriptor: the request of this run fails with the errno of this kernel, the
    wait is the signed one (1 s here, with real sleeps), and nothing is created."""
    holder=os.open(tree/LOCK[1:],os.O_RDONLY);fcntl.flock(holder,fcntl.LOCK_EX)
    try:
        before=snapshot(tree);receipt=run(tree,real=True)
        asked=[entry for entry in receipt['_calls'] if entry['call']=='flock' and entry['operation']==fcntl.LOCK_EX|fcntl.LOCK_NB]
        assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and snapshot(tree)==before
        assert 2<=len(asked)<=5 and all('errno' in entry for entry in asked) and 0.5<=receipt['clock']['monotonic_elapsed_ms']/1000<=5
    finally:
        fcntl.flock(holder,fcntl.LOCK_UN);os.close(holder)
    receipt=run(tree);assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['precheck']['lock_attempts']==1

def test_native_first_creation_on_a_tree_it_cannot_write_is_a_refusal_with_the_errno_of_this_kernel(tree):
    if os.geteuid()==0:pytest.skip('root writes anywhere')
    parent=tree/k6a.LIVE_PARENT[1:];os.chmod(parent,0o555)
    try:receipt=run(tree)
    finally:os.chmod(parent,0o755)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['directories'][0]['state'])==('REFUSED','FILESYSTEM_ACCESS_DENIED','EFFECTS','NOT_CREATED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and not (tree/LIVE[1:]).exists()
