"""The real system calls, made by the sources' own unmodified Native classes, on a private temporary tree that stands
in for '/'. No host, no docker, no systemd. Nothing of Native is overridden: the substitution of '/' and of the uid is
made on the os module (tests/oslevel.py), and every system call is recorded with the arguments it received.
What this proves depends on the machine it runs on: on the workstation the real mkdir/open/link/unlink/fsync by
dir_fd, real O_EXCL|O_NOFOLLOW, the real flock, real symbolic links and the errno values of macOS as an ordinary user,
with a marker bit standing for O_NOATIME; the kernel's O_NOATIME, Linux errno values and real uid 0 only when the suite
is run as root on Linux (the job each operation's CI runs)."""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import demos
import family as f
import native_child
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
DATA='/mnt/day-d-data';DEPLOY='/opt/chief-of-staff-digital';LOCKS=DEPLOY+'/runtime/security'
rows=oslevel.rows

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('etc','var/lib','mnt/day-d-data','proc/sys/kernel/random','opt/chief-of-staff-digital/runtime/security','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT);(root/'opt/chief-of-staff-digital/.deploy-version').write_bytes((REVISION+'\n').encode())
    (root/'opt/chief-of-staff-digital/runtime/security/deployment.lock').write_bytes(b'');os.chmod(root/'opt/chief-of-staff-digital/runtime/security/deployment.lock',0o644)
    return root

def write_fields(root,leaf=demos.LEAF):
    files=[('POLICY','policy.json',demos.POLICY,0o600),('OVERRIDE','compose.override.json',demos.override(),0o600)]
    return {'parent':rows(root,DATA),'open_root':None,'directory_name':leaf,
            'files':[{'key':key,'name':name,'content_b64':demos.b64(raw),'sha256':f.sha(raw),'bytes':len(raw),'mode':mode} for key,name,raw,mode in files],
            'container':None,'recreate':None,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
def read_fields(root):
    return {'directories':[{'key':key,'rows':rows(root,path),'open_root':None} for key,path in (('DEPLOY',DEPLOY),('LOCKS',LOCKS),('DATA',DATA),('ETC','/etc'))],
            'image':None,'containers':None,'environment':None,'verify':None,'render':None,
            'file':{'directory_key':'DEPLOY','name':'.deploy-version','sha256':f.sha((REVISION+'\n').encode()),'bytes':41},
            'lock':{'directory_key':'LOCKS','name':'deployment.lock'},'evidence_boot_id_sha256':f.sha(BOOT.strip())}

def child(name,root,fields,tmp_path):
    path=Path(str(tmp_path))/('fields-%s.json'%name);path.write_bytes(json.dumps(fields).encode())
    done=subprocess.run([sys.executable,'-B',str(Path(native_child.__file__)),name,str(root),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);return result['receipt'],result['events'],result['calls']
def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
def run(name,root,fields,host=None):
    """One run in this process with the module's own Native (host=None), or with a subclass of it that only adds a race."""
    k=f.load(demos.DIRECTORIES[name]);old=os.umask(0o027)
    try:
        with oslevel.Substitute(root) as record:receipt=f.Docs(k,fields).run(host(record) if host else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_primitives(calls):
    """What every source's read path must hand to the kernel, whatever the operation."""
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


# ---------------------------------------------------------------- the writing source: a directory and two files, for real
def test_native_write_creates_the_directory_and_the_files_with_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);receipt,events,calls=child('selftest_write',tree,write_fields(tree),tmp_path);base=tree/'mnt/day-d-data'/demos.LEAF
    assert (receipt['status'],receipt['outcome'])==('METADATA_ONLY_REQUIRES_REVIEW','SELFTEST_ALL_EFFECTS_VERIFIED'),receipt
    assert sorted(item.name for item in base.iterdir())==['compose.override.json','policy.json']
    assert stat.S_IMODE(os.lstat(base).st_mode)==0o700 and (base/'policy.json').read_bytes()==demos.POLICY and (base/'compose.override.json').read_bytes()==demos.override()
    for name in ('policy.json','compose.override.json'):
        info=os.lstat(base/name);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode))==(0o600,1,True)
    assert_read_primitives(calls);go16=receipt['go_sha256'][:16];leaf='/mnt/day-d-data/'+demos.LEAF
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[('mkdir',leaf),
        ('open',leaf+'/.hostops-%s-0.partial'%go16),('link',leaf+'/policy.json'),('unlink',leaf+'/.hostops-%s-0.partial'%go16),
        ('open',leaf+'/.hostops-%s-1.partial'%go16),('link',leaf+'/compose.override.json'),('unlink',leaf+'/.hostops-%s-1.partial'%go16)]
    assert all(entry['by_dir_fd'] for entry in changing) and changing[0]['mode']==0o700
    for entry in changing:
        if entry['call']=='open':assert entry['flags']&(os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW)==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW and entry['mode']==0o600
        if entry['call']=='link':assert entry['follow_symlinks'] is False and entry['same_directory']
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    synced=[entry['path'] for entry in calls if entry['call']=='fsync']
    assert synced==[leaf,'/mnt/day-d-data',leaf+'/.hostops-%s-0.partial'%go16,leaf,leaf,leaf+'/.hostops-%s-1.partial'%go16,leaf,leaf]
    # the interpreter's own audit events: nothing but these creations, no process, no chmod, chown, rename or truncate
    kinds=sorted({event[0] for event in events});assert kinds==['open','open-for-writing','os.link','os.mkdir','os.remove'],kinds
    after=snapshot(tree);assert {name:value for name,value in after.items() if not name.startswith('mnt/day-d-data')}=={name:value for name,value in before.items() if not name.startswith('mnt/day-d-data')}
    assert sorted(set(after)-set(before))==['mnt/day-d-data/'+demos.LEAF,'mnt/day-d-data/%s/compose.override.json'%demos.LEAF,'mnt/day-d-data/%s/policy.json'%demos.LEAF]

def test_native_write_refuses_an_existing_destination_a_symbolic_link_in_the_chain_and_a_changed_parent(tree):
    fields=write_fields(tree);(tree/'mnt/day-d-data'/demos.LEAF).mkdir();before=snapshot(tree);receipt=run('selftest_write',tree,fields)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and snapshot(tree)==before and receipt['mutating_calls']['issued']==0
    (tree/'mnt/day-d-data'/demos.LEAF).rmdir();fields=write_fields(tree)
    os.rename(tree/'mnt/day-d-data',tree/'mnt/real');os.symlink('real',tree/'mnt/day-d-data');before=snapshot(tree);receipt=run('selftest_write',tree,fields)
    assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_SYMLINK_COMPONENT') and snapshot(tree)==before
    os.unlink(tree/'mnt/day-d-data');os.rename(tree/'mnt/real',tree/'mnt/day-d-data');os.chmod(tree/'mnt/day-d-data',0o700);receipt=run('selftest_write',tree,fields)
    assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_IDENTITY_MISMATCH')

def test_native_write_never_replaces_a_file_that_appears_and_withdraws_only_its_own_temporary(tree):
    """A name that appears between the precheck and the link, by a real race: the kernel's link() refuses, the file that
    appeared is untouched, the temporary of this run is removed, and the run is a partial that says so."""
    k=f.load(demos.WRITE);fields=write_fields(tree);base=tree/'mnt/day-d-data'/demos.LEAF
    def racing(record):
        class Racing(k.m.Native):
            def link(self,source,target,dir_fd):
                if target=='policy.json':
                    fd=record.real['open']('policy.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(fd,b'foreign');record.real['close'](fd)
                return k.m.Native.link(self,source,target,dir_fd)
        return Racing()
    receipt=run('selftest_write',tree,fields,racing)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert (base/'policy.json').read_bytes()==b'foreign' and sorted(item.name for item in base.iterdir())==['policy.json']
    assert receipt['ledger'][0]['state']=='NOT_CREATED' and receipt['ledger'][0]['temporary_removed'] is True and receipt['ledger'][1]['state']=='NOT_ATTEMPTED'

def test_native_write_on_a_tree_it_cannot_write_is_a_refusal_with_the_errno_of_this_kernel(tree):
    if os.geteuid()==0:pytest.skip('root writes anywhere')
    fields=write_fields(tree);os.chmod(tree/'mnt/day-d-data',0o555);fields['parent']=rows(tree,DATA)
    try:receipt=run('selftest_write',tree,fields)
    finally:os.chmod(tree/'mnt/day-d-data',0o755)
    assert (receipt['status'],receipt['code'],receipt['directories'][0]['state'])==('REFUSED','FILESYSTEM_ACCESS_DENIED','NOT_CREATED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}


# ---------------------------------------------------------------- the reading source: walks, a file, the lock, and nothing written
def test_native_read_observes_with_read_only_system_calls_and_leaves_no_trace(tree,tmp_path):
    before=snapshot(tree);receipt,events,calls=child('selftest_read',tree,read_fields(tree),tmp_path)
    assert (receipt['status'],receipt['outcome'],receipt['findings'])==('METADATA_ONLY_REQUIRES_REVIEW','SELFTEST_ALL_OBSERVED_ALL_EXPECTATIONS_MET',[]),receipt
    assert snapshot(tree)==before and receipt['items']['lock']['state']=='FREE' and receipt['items']['file']['bytes_equal_signed'] is True
    assert_read_primitives(calls)
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','umask')] and not [entry for entry in calls if entry['call']=='open' and entry['flags']&READ_ONLY_OPEN]
    assert [(entry['path'],entry['operation']) for entry in calls if entry['call']=='flock']==[(LOCKS+'/deployment.lock',fcntl.LOCK_SH|fcntl.LOCK_NB),(LOCKS+'/deployment.lock',fcntl.LOCK_UN)]
    assert sorted({event[0] for event in events})==['open'],'no file-changing and no process-starting event in the whole interpreter'
    assert receipt['items']['directory:DATA']['bytes_available']>0 and receipt['writes']==0

def test_native_read_sees_a_lock_another_descriptor_holds_and_a_file_that_differs(tree):
    fields=read_fields(tree);holder=os.open(str(tree/'opt/chief-of-staff-digital/runtime/security/deployment.lock'),os.O_RDONLY)
    try:
        fcntl.flock(holder,fcntl.LOCK_EX|fcntl.LOCK_NB);receipt=run('selftest_read',tree,fields)
        assert receipt['items']['lock']['state']=='BUSY' and receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    finally:os.close(holder)
    (tree/'opt/chief-of-staff-digital/.deploy-version').write_bytes(b'0'*40+b'\n');fields=read_fields(tree);fields['file']['sha256']=f.sha((REVISION+'\n').encode())
    receipt=run('selftest_read',tree,fields);assert receipt['findings']==['FILE_NOT_THE_SIGNED_BYTES'] and receipt['outcome']=='OBSERVED_ALL_EXPECTATIONS_NOT_MET'

@pytest.mark.parametrize('name',['selftest_read','selftest_write'])
def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(name,monkeypatch):
    m=f.load(demos.DIRECTORIES[name]).m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()


# ---------------------------------------------------------------- a real process behind the docker helpers
FAKE_DOCKER='''#!%s -B
import json,os,sys
data=sys.stdin.buffer.read()
environment={key:value for key,value in os.environ.items() if not key.startswith("__CF")}       # macOS gives every process one variable of its own
sys.stdout.write(json.dumps({"argv":sys.argv[1:],"stdin":data.decode("latin-1"),"environment":environment,"cwd":os.getcwd()},sort_keys=True)+"\\n")
'''
def test_helpers_reach_a_real_process_with_the_exact_argv_the_bytes_and_the_fixed_environment(tree):
    """Not docker: a program at <tree>/usr/bin/docker that prints what it was started with. The helpers of the core, the
    command table, the trusted-binary walk and the runner are the shipped ones; only the path of the binary is moved
    into the temporary tree."""
    k=f.load(demos.READ);m=k.m;script=tree/'usr/bin/docker';script.write_text(FAKE_DOCKER%sys.executable);os.chmod(script,0o755)
    with oslevel.Substitute(tree) as record:
        class Moved(m.Native):
            def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
        commands=m.Commands(Moved(),lambda:60.0)
        mount={'source':'/mnt/day-d-data','target':'/selftest','read_only':True}
        result=m.container_run(commands,'verify','sha256:'+'fb'*32,[mount],['python','-I','-B','-','/selftest','R2D2-V2-SHADOW-2026-10-05'],demos.READ_SCRIPT,
                               docker_config='/etc/c3po-bar/docker-cli')
        rendered=m.strict(commands.output('render',*m.compose_arguments('c3po',DEPLOY+'/.env',[DEPLOY+'/c3po/compose.yml'],True),stdin=demos.override(),
                                          variables={'C3PO_BUILD_SHA':REVISION}))
    assert result['returned'] and result['returncode']==0;seen=m.single_line(result['output'])
    assert seen['argv']==m.RUN_PREFIX+['--mount','type=bind,source=/mnt/day-d-data,target=/selftest,readonly','sha256:'+'fb'*32,'python','-I','-B','-','/selftest','R2D2-V2-SHADOW-2026-10-05']
    assert seen['stdin']==demos.READ_SCRIPT.decode() and seen['cwd']=='/'
    assert seen['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','DOCKER_CONFIG':'/etc/c3po-bar/docker-cli'}
    assert rendered['argv']==['compose','--project-name','c3po','--env-file',DEPLOY+'/.env','-f',DEPLOY+'/c3po/compose.yml','-f','-','config','--format','json']
    assert rendered['stdin']==demos.override().decode() and rendered['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','C3PO_BUILD_SHA':REVISION}
    # the binary is taken only if every directory above it and the file itself are root-owned and closed to group and other
    os.chmod(script,0o775)
    with oslevel.Substitute(tree):
        with pytest.raises(m.NotStarted,match='BINARY_UNAVAILABLE_OR_UNSAFE'):m.Commands(Moved(),lambda:60.0).call('image','x')
