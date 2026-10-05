"""The real system calls of K3-K9, made by the source's own Native on a private temporary tree that stands in for "/":
the substitution of "/" and of the uid is made on the os module (the core's tests/oslevel.py), and every system call is
recorded with the arguments it received. Only NativeRunner.run is replaced (tests/nativehost.py): the three docker reads
are answered by the core's emulated engine, and no docker binary is started. One test makes the write of the second file
fail (a subclass whose write raises ENOSPC for that file: the creation, the removal by identity and the fsync that follow
are real). The last test runs the source in a child interpreter under an audit hook and scans everything it printed.

On the workstation this proves the real mkdir and exclusive creates relative to held descriptors, fsync of files and
directories, lstat of a symbolic link and a real second hard link, the readback by a new open, and the removal by
identity, as an ordinary user reported as root, with a marker bit for O_NOATIME; the kernel's O_NOATIME, Linux errno
values, real uid 0 and the kernel's prctl only when the suite runs as root on Linux (set 3, not run by the author)."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k3
import nativehost
import oslevel

CHILD=Path(__file__).resolve().parent/'native_child.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
LINUX=sys.platform.startswith('linux')

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755);return nativehost.build(root)

def run(root,host=None,after_signing=None):
    """One run in this process with the source's own Native whose docker reads are emulated."""
    k=k3.K();docs=f.Docs(k,nativehost.fields(root),now=k3.NOW)
    if after_signing is not None:after_signing()
    host=host or nativehost.native();old=os.umask(0o022)
    try:
        with nativehost.Substitute(root) as record:receipt=docs.run(host)
    finally:os.umask(old)
    assert f.sealed(receipt) and k3.leaks(k3.line(receipt))==[] and k3.leaks(json.dumps(record.plain()))==[]
    return k.m,receipt,record,host

def creating(record):return [entry for entry in record.of('open') if entry['flags']&WRITING]
def made_non_dumpable_first(calls):
    first=[(entry['call'],entry.get('options'),entry.get('option'),entry.get('arguments'),entry.get('result')) for entry in calls[:3]]
    assert first==[('dlopen',{'use_errno':True},None,[],None),('prctl',None,4,[0,0,0,0],0),('prctl',None,3,[0,0,0,0],0)],first
    assert [entry['call'] for entry in calls].count('prctl')==6

def test_complete_run_with_real_system_calls(tree):
    m,receipt,record,host=run(tree)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,m.COMPLETE_OUTCOME,None)
    made_non_dumpable_first(record.calls);assert receipt['process']=={'dumpable_disabled':True}
    secrets=tree/m.K9_SECRETS_DIRECTORY.lstrip('/')
    assert sorted(os.listdir(str(secrets)))==['emitter','provider.env','risk-db.env'] and os.listdir(str(secrets/'emitter'))==['password']
    for path,content in zip(m.TARGET_PATHS,(k3.provider_content(),k3.risk_content(),k3.PASSWORD.encode())):
        info=os.lstat(str(tree/path.lstrip('/')))
        assert (tree/path.lstrip('/')).read_bytes()==content and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,path
        row=receipt['files'][m.FILE_ROWS[m.TARGET_PATHS.index(path)]];assert (row['device'],row['inode'])==(info.st_dev,info.st_ino)
    assert stat.S_IMODE(os.lstat(str(secrets/'emitter')).st_mode)==0o700
    made=creating(record)
    assert [entry['path'] for entry in made]==list(m.TARGET_PATHS) and all(entry['by_dir_fd'] and entry['mode']==0o600 and
        entry['flags']==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC for entry in made)
    assert [(entry['path'],entry['mode'],entry['by_dir_fd']) for entry in record.of('mkdir')]==[(m.K9_EMITTER_DIRECTORY,0o700,True)]
    opens=record.of('open')
    assert all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    sources=[entry for entry in opens if entry['path'] in (m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME,m.EMITTER_SOURCE_DIRECTORY+'/'+m.EMITTER_SOURCE_NAME)]
    assert len(sources)==2 and all(entry['noatime'] and entry['flags']&os.O_NONBLOCK and not entry['flags']&WRITING for entry in sources)
    back=[entry for entry in opens if entry['path'] in m.TARGET_PATHS and not entry['flags']&WRITING]
    assert [entry['path'] for entry in back]==list(m.TARGET_PATHS) and all(entry['noatime'] for entry in back)
    assert record.of('unlink','remove','link')==[] and [entry['mask'] for entry in record.of('umask')]==[0o077]
    assert all(entry['follow_symlinks'] is False for entry in record.of('stat'))
    assert [entry['path'] for entry in record.done('fsync')]==[m.K9_EMITTER_DIRECTORY,m.K9_SECRETS_DIRECTORY,m.TARGET_PATHS[0],m.K9_SECRETS_DIRECTORY,
                                                               m.TARGET_PATHS[1],m.K9_SECRETS_DIRECTORY,m.TARGET_PATHS[2],m.K9_EMITTER_DIRECTORY]
    # the docker reads come before the first open of a file of September; the sources are as they were
    assert len(host.argv)==2
    assert (tree/(m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME).lstrip('/')).read_bytes()==(k3.url()+'\n').encode()

def test_a_write_that_fails_is_withdrawn_by_identity_with_real_calls(tree):
    m=k3.K().m
    class Full(m.Native):
        def write(self,fd,data):
            if self.writes==1:raise OSError(errno.ENOSPC,'full')          # the second file's first write
            self.writes+=1;return m.Native.write(self,fd,data)
    host=nativehost.native(base=Full);host.writes=0
    m,receipt,record,host=run(tree,host)
    row=receipt['files']['risk_db_env']
    assert (receipt['status'],receipt['code'],row['state'],row['withdrawn'],row['fsync_directory_after_withdrawal'])==(m.PARTIAL_STATUS,'FILESYSTEM_FULL','WITHDRAWN',True,True)
    assert sorted(os.listdir(str(tree/m.K9_SECRETS_DIRECTORY.lstrip('/'))))==['emitter','provider.env']
    removed=record.done('unlink');assert len(removed)==1 and removed[0]['path']==m.TARGET_PATHS[1] and removed[0]['by_dir_fd']
    assert receipt['files']['provider_env']['state']=='PLACED_VERIFIED' and receipt['files']['emitter_password']['state']=='NOT_ATTEMPTED'

def test_a_second_hard_link_and_a_symbolic_link_are_refused_with_real_calls(tree,tmp_path):
    m=k3.K().m;url=tree/(m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME).lstrip('/')
    os.link(str(url),str(tree/'etc'/'second-name'))
    m,receipt,record,host=run(tree);assert (receipt['status'],receipt['code'])==('REFUSED','RISK_URL_FILE_LINKED') and creating(record)==[]
    os.unlink(str(tree/'etc'/'second-name'))     # the test's own link in its own temporary tree
    password=tree/m.EMITTER_SOURCE_DIRECTORY.lstrip('/');target=Path(str(tmp_path))/'elsewhere'
    def swap():password.rename(target);os.symlink(str(target),str(password))      # after the rows were read
    m,receipt,record,host=run(tree,after_signing=swap);assert (receipt['status'],receipt['code'])==('REFUSED','EMITTER_PASSWORD_COMPONENT_DIVERGES') and creating(record)==[]
    assert not [entry for entry in record.of('open') if entry['path']==m.EMITTER_SOURCE_DIRECTORY],'the link is never opened'
    assert record.of('mkdir')==[] and os.listdir(str(tree/m.K9_SECRETS_DIRECTORY.lstrip('/')))==[]

def test_a_secrets_directory_that_is_not_empty_is_refused_with_real_calls(tree):
    m=k3.K().m;(tree/m.K9_SECRETS_DIRECTORY.lstrip('/')/'provider.env').write_bytes(b'previous')
    m,receipt,record,host=run(tree);assert (receipt['status'],receipt['code'])==('REFUSED','SECRETS_DIRECTORY_NOT_EMPTY')
    assert host.argv==[] and creating(record)==[] and (tree/m.K9_SECRETS_DIRECTORY.lstrip('/')/'provider.env').read_bytes()==b'previous'

def test_a_child_interpreter_prints_nothing_of_any_value_and_changes_only_what_it_creates(tree,tmp_path):
    m=k3.K().m;path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(nativehost.fields(tree)).encode())
    done=subprocess.run([sys.executable,'-B',str(CHILD),str(tree),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    assert k3.leaks(done.stdout)==[] and k3.leaks(done.stderr)==[] and k3.LITERAL.encode() not in done.stdout
    result=json.loads(done.stdout);receipt=result['receipt']
    assert receipt['status']==m.COMPLETE_STATUS and len(result['docker'])==2
    events=result['events']
    assert [event for event in events if event[0]=='open-for-writing']==[['open-for-writing',name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC]
                                                                        for name in ('provider.env','risk-db.env','password')]
    assert [event[0] for event in events if event[0]!='open' and event[0]!='open-for-writing']==['os.mkdir']
    assert not [event for event in events if event[0] in ('subprocess.Popen','os.remove','os.rename','os.chmod','os.chown','os.putenv','socket.connect','os.posix_spawn')]
    made_non_dumpable_first(result['calls'])
    if LINUX:assert (result['dumpable_before'],result['dumpable_after'])==(1,0)
    else:assert (result['dumpable_before'],result['dumpable_after'])==(None,None)


def test_a_c_library_that_does_not_make_the_process_non_dumpable_is_a_refusal_before_anything_is_opened(tree):
    """The source's own Native and the core's dumps_disabled() against the C library of tests/oslevel.py made to fail:
    the first prctl returns -1, or the attribute reads back 1. Refused, and nothing opened or started after them."""
    Base=oslevel.Library
    class Failing(Base):
        def prctl(self,option,*arguments):
            result=Base.prctl(self,option,*arguments)
            if option==4:self.record.calls[-1]['result']=-1;self.dumpable=1;return -1
            return result
    class Stuck(Base):
        def prctl(self,option,*arguments):
            result=Base.prctl(self,option,*arguments);self.dumpable=1
            if option==3:self.record.calls[-1]['result']=1;return 1
            return result
    for library in (Failing,Stuck):
        saved=oslevel.Library;oslevel.Library=library
        try:m,receipt,record,host=run(tree)
        finally:oslevel.Library=saved
        assert (receipt['status'],receipt['code'],receipt['process'])==('REFUSED','PROCESS_DUMPABLE_NOT_DISABLED',{'dumpable_disabled':False})
        assert [entry['call'] for entry in record.calls if entry['call'] not in ('dlopen','prctl')]==[] and host.argv==[]
