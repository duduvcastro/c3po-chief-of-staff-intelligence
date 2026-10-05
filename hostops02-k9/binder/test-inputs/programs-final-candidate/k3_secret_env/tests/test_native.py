"""The real system calls of K3, made by the source's own Native on a private temporary tree that stands in for "/": the
substitution of "/" and of the uid is made on the os module (the core's tests/oslevel.py), and every system call is
recorded with the arguments it received. Only NativeRunner.run is replaced (tests/nativehost.py): the four docker reads
are answered by the core's emulated engine, and no docker binary is started. One test makes the write fail (a subclass
whose write raises ENOSPC: the creation, the removal by identity and the fsync that follow are real). The last tests run
the source in a child interpreter under an audit hook and scan everything it printed, in the two canary worlds.

On the workstation this proves the real exclusive create relative to a held descriptor, fsync of the file and of the
directory, the readback by a new open and real reads compared in memory, lstat of a symbolic link, and the removal by
identity, as an ordinary user reported as root, with a marker bit for O_NOATIME; the kernel's O_NOATIME, Linux errno
values, real uid 0 and the kernel's prctl only when the suite runs as root on Linux (not run by the author)."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k3env as e
import nativehost
import oslevel

CHILD=Path(__file__).resolve().parent/'native_child.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
LINUX=sys.platform.startswith('linux')
CONFIG='/etc/c3po-reader'
TARGET='/etc/c3po-reader/secret.env'

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755);return nativehost.build(root)

def run(root,host=None,value=e.VALUE,signed=None):
    """One run in this process with the source's own Native whose docker reads are emulated (signed: the plan fields as
    a binder copied them earlier; by default read from the tree now)."""
    k=e.K();docs=f.Docs(k,signed or nativehost.fields(root),now=e.NOW)
    host=host or nativehost.native(value);old=os.umask(0o022)
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(host)
    finally:os.umask(old)
    assert f.sealed(receipt) and e.leaks(e.line(receipt))==[] and e.leaks(json.dumps(record.plain()))==[]
    if value in (e.VALUE_A,e.VALUE_B):
        assert e.length_leaks(e.line(receipt),(value,))==[] and e.length_leaks(json.dumps(record.plain()),(value,))==[]
    return k.m,receipt,record,host

def creating(record):return [entry for entry in record.of('open') if entry['flags']&WRITING]
def made_non_dumpable_first(calls):
    first=[(entry['call'],entry.get('options'),entry.get('option'),entry.get('arguments'),entry.get('result')) for entry in calls[:3]]
    assert first==[('dlopen',{'use_errno':True},None,[],None),('prctl',None,4,[0,0,0,0],0),('prctl',None,3,[0,0,0,0],0)],first
    assert [entry['call'] for entry in calls].count('prctl')==2

@pytest.mark.parametrize('value',[e.VALUE,e.VALUE_A,e.VALUE_B])
def test_complete_run_with_real_system_calls(tree,value):
    m,receipt,record,host=run(tree,value=value)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,m.COMPLETE_OUTCOME,None)
    made_non_dumpable_first(record.calls);assert receipt['process']=={'dumpable_disabled':True}
    config=tree/CONFIG.lstrip('/')
    assert sorted(os.listdir(str(config)))==['docker-cli','secret.env'] and os.listdir(str(config/'docker-cli'))==[]
    info=os.lstat(str(config/'secret.env'))
    assert (config/'secret.env').read_bytes()==e.line_of(value) and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
    row=receipt['secret_env'];assert (row['device'],row['inode'])==(info.st_dev,info.st_ino)
    assert all(row[name] is True for name in m.READBACK_FACTS+m.METADATA_FACTS)
    made=creating(record)
    assert [entry['path'] for entry in made]==[TARGET] and all(entry['by_dir_fd'] and entry['mode']==0o600 and
        entry['flags']==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC for entry in made)
    opens=record.of('open')
    assert all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    back=[entry for entry in opens if entry['path']==TARGET and not entry['flags']&WRITING]
    assert len(back)==1 and back[0]['noatime'] and back[0]['flags']&os.O_NONBLOCK
    assert record.of('unlink','remove','link','mkdir')==[] and [entry['mask'] for entry in record.of('umask')]==[0o077]
    assert all(entry['follow_symlinks'] is False for entry in record.of('stat'))
    assert [entry['path'] for entry in record.done('fsync')]==[TARGET,CONFIG]
    assert len(host.argv)==6 and host.reads[-2:]==[m.READBACK_REQUEST]*2

def test_the_reads_ask_the_same_sizes_whatever_the_value(tree,tmp_path):
    sizes=[]
    for value in (e.VALUE_A,e.VALUE_B):
        root=Path(str(tmp_path)).resolve()/('root-%d'%len(sizes));root.mkdir(mode=0o755);nativehost.build(root)
        m,receipt,record,host=run(root,value=value);assert receipt['status']==m.COMPLETE_STATUS;sizes.append(host.reads)
    assert sizes[0]==sizes[1] and not set(sizes[0])&(e.lengths(e.VALUE_A)|e.lengths(e.VALUE_B))

def test_a_write_that_fails_is_withdrawn_by_identity_with_real_calls(tree):
    m=e.K().m
    class Full(m.Native):
        def write(self,fd,data):raise OSError(errno.ENOSPC,'full')
    host=nativehost.native(base=Full)
    m,receipt,record,host=run(tree,host)
    row=receipt['secret_env']
    assert (receipt['status'],receipt['code'],row['state'],row['withdrawn'],row['fsync_directory_after_withdrawal'])==(m.PARTIAL_STATUS,'FILESYSTEM_FULL','WITHDRAWN',True,True)
    assert sorted(os.listdir(str(tree/CONFIG.lstrip('/'))))==['docker-cli']
    removed=record.done('unlink');assert len(removed)==1 and removed[0]['path']==TARGET and removed[0]['by_dir_fd']

@pytest.mark.parametrize('content',[b'',b'C3PO_DATABASE_URL=old\n',e.line_of(e.VALUE_A)])
def test_a_secret_env_present_is_refused_with_real_calls_and_its_size_never_said(tree,content):
    target=tree/TARGET.lstrip('/');target.write_bytes(content);os.chmod(str(target),0o600)
    m,receipt,record,host=run(tree);assert (receipt['status'],receipt['code'])==('REFUSED','SECRET_ENV_PRESENT')
    assert receipt['existing_secret_env']=={'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1} and host.argv==[] and creating(record)==[]
    assert target.read_bytes()==content and e.length_leaks(e.line(receipt))==[]
    assert not [entry for entry in record.of('open') if entry['path']==TARGET]

def test_a_symbolic_link_at_the_name_is_refused_without_being_followed(tree,tmp_path):
    elsewhere=Path(str(tmp_path))/'elsewhere';elsewhere.write_bytes(b'not to be touched')
    os.symlink(str(elsewhere),str(tree/TARGET.lstrip('/')))
    m,receipt,record,host=run(tree);assert (receipt['status'],receipt['code'])==('REFUSED','SECRET_ENV_PRESENT')
    assert receipt['existing_secret_env']['type']=='symlink' and elsewhere.read_bytes()==b'not to be touched' and creating(record)==[]

def test_a_leftover_and_a_replaced_directory_are_refused_with_real_calls(tree,tmp_path):
    leftover=tree/(CONFIG+'/.hostops-0123456789abcdef-00.partial').lstrip('/');leftover.write_bytes(b'');os.chmod(str(leftover),0o600)
    m,receipt,record,host=run(tree);assert (receipt['status'],receipt['code'])==('REFUSED','SECRET_ENV_LEFTOVER_PRESENT') and creating(record)==[]
    assert leftover.is_file()
    signed=nativehost.fields(tree);config=tree/CONFIG.lstrip('/');moved=Path(str(tmp_path))/'moved';config.rename(moved);config.mkdir(mode=0o700)
    m,receipt,record,host=run(tree,signed=signed);assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_IDENTITY_MISMATCH') and creating(record)==[]

@pytest.mark.parametrize('value',[e.VALUE_A,e.VALUE_B])
def test_a_child_interpreter_prints_nothing_of_the_value_and_changes_only_what_it_creates(tree,tmp_path,value):
    m=e.K().m;path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(nativehost.fields(tree)).encode())
    secret=Path(str(tmp_path))/'value.txt';secret.write_bytes(value.encode())
    done=subprocess.run([sys.executable,'-B',str(CHILD),str(tree),str(path),str(secret)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    assert e.leaks(done.stdout)==[] and e.leaks(done.stderr)==[] and e.LITERAL.encode() not in done.stdout
    assert e.length_leaks(done.stdout,(value,))==[]
    result=json.loads(done.stdout);receipt=result['receipt']
    assert receipt['status']==m.COMPLETE_STATUS and len(result['docker'])==6 and result['reads'][-2:]==[m.READBACK_REQUEST]*2
    assert not set(e.integers(result))&e.lengths(value)
    events=result['events']
    assert [event for event in events if event[0]=='open-for-writing']==[['open-for-writing','secret.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC]]
    assert [event[0] for event in events if event[0] not in ('open','open-for-writing')]==[]
    made_non_dumpable_first(result['calls'])
    if LINUX:assert (result['dumpable_before'],result['dumpable_after'])==(1,0)
    else:assert (result['dumpable_before'],result['dumpable_after'])==(None,None)
    assert (tree/TARGET.lstrip('/')).read_bytes()==e.line_of(value)

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
