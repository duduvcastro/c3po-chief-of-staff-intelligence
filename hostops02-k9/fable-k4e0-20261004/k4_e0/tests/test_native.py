"""K4-E0 with the real system calls, made by the source's own unmodified Native, on a private temporary tree that stands
in for '/'. No host, no docker, no process started by the source. The substitution of '/' and of the uid is made on
the os module (tests/oslevel.py of the frozen core; the data volume device shift of tests/native_support.py, a
byte-identical copy of install_release's), and every system call is recorded with the arguments it received.
On the workstation this proves real mkdir/open/write/fsync/link/unlink by dir_fd, real O_EXCL|O_NOFOLLOW, real races and
a real process death, with macOS errno values as an ordinary user; the kernel's O_NOATIME, Linux errno values and real
uid 0 only when the suite is run as root on Linux (set 3, the Linux-root CI job: NOT RUN by the author)."""
import contextlib
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k4e0
import native_child
import native_space
import native_support

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
DATA='/mnt/day-d-data'
RELATIVE=[path[1:] for path in k4e0.ORDER]
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):
    """install_release's tree plus /var/lib (0755, the test user reported as root); /var/lib/c3po absent."""
    root=native_support.build_tree(tmp_path);(root/'var'/'lib').mkdir(parents=True);os.chmod(root/'var',0o755);os.chmod(root/'var'/'lib',0o755);return root

def fields(root,raw=k4e0.RUNNER):
    return {'parent':native_support.rows(root,'/var/lib'),'runner':k4e0.runner_member(raw),'evidence_boot_id_sha256':f.sha(native_support.BOOT.strip())}
def child(root,plan,tmp_path,point=None):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    command=[sys.executable,'-B',str(Path(native_child.__file__)),str(root),str(path)]+([point] if point else [])
    return subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
def run(root,plan,host=None,space=True):
    k=k4e0.K();old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record,(native_space.Space() if space else contextlib.nullcontext()) as substitute:
            receipt=f.Docs(k,plan).run(host(record) if host else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;receipt['_space_substituted']=bool(space and substitute.substituted);return receipt


def test_native_e0_creates_the_seven_directories_and_the_runner_with_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK',None),receipt
    for relative in RELATIVE:
        info=os.lstat(tree/relative);assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700,relative
    k9=tree/RELATIVE[2];assert sorted(item.name for item in k9.iterdir())==['claims','days','secrets','tools']
    runner=k9/'tools'/k4e0.runner_name();assert sorted(item.name for item in (k9/'tools').iterdir())==[runner.name] and runner.read_bytes()==k4e0.RUNNER
    info=os.lstat(runner);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode),info.st_size)==(0o600,1,True,len(k4e0.RUNNER))
    assert list((tree/RELATIVE[1]).iterdir())==[] and receipt['ledger'][0]['inode']==info.st_ino and receipt['delivered']['runner']['sha256']==f.sha(k4e0.RUNNER)
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(not entry['flags']&READ_ONLY_OPEN for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat'];assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats)
    temporary=k4e0.TOOLS+'/.hostops-%s-0.partial'%result['go16']
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[('mkdir',path) for path in k4e0.ORDER]+[('open',temporary),('link',k4e0.runner_path()),('unlink',temporary)]
    assert all(entry['by_dir_fd'] for entry in changing) and all(entry['mode']==0o700 for entry in changing[:7]) and changing[7]['mode']==0o600
    wanted=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC;assert changing[7]['flags']&wanted==wanted and not changing[7]['flags']&(os.O_TRUNC|os.O_APPEND)
    assert changing[8]['follow_symlinks'] is False and changing[8]['same_directory'] and changing[8]['source']==temporary
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    assert sorted({event[0] for event in events})==['open','open-for-writing','os.link','os.mkdir','os.remove']
    assert [event[0] for event in events if event[0]!='open']==['os.mkdir']*7+['open-for-writing','os.link','os.remove']
    after=snapshot(tree);outside=lambda items:{name:value for name,value in items.items() if not name.startswith(('mnt/day-d-data','var/lib'))}
    assert outside(after)==outside(before) and sorted(set(after)-set(before))==sorted(RELATIVE+[RELATIVE[3]+'/'+runner.name])
    assert {name:value for name,value in after.items() if name.startswith('mnt')}=={name:value for name,value in before.items() if name.startswith('mnt')},'the data volume is untouched'
    assert not [entry for entry in calls if str(entry.get('path','')).startswith('/mnt')],'and never even looked at'

def test_native_run_records_where_it_ran_for_the_linux_proof(tree,tmp_path,request):
    """One real run, and what it ran on, written into the junit file as properties of this test case (the same shape
    as install_release's record, prefix k4e0_). On Linux as root it also asserts what the kernel made."""
    euid,egid=os.geteuid(),os.getegid();done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt=result['receipt'];runner=tree/RELATIVE[3]/k4e0.runner_name()
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt
    infos=[os.lstat(tree/relative) for relative in RELATIVE];leaf=os.lstat(runner)
    sums=k4e0.DIRECTORY/'SHA256SUMS'
    facts={'payload_sha256':f.sha(k4e0.K().source),'sha256sums_sha256':f.sha(sums.read_bytes()) if sums.is_file() else 'ABSENT',
           'euid':euid,'egid':egid,'platform':sys.platform,'python':'%d.%d.%d'%sys.version_info[:3],
           'noatime_is_the_kernel_flag':bool(result['noatime_is_the_kernel_flag']),
           'created_directories':['%d:%d:%04o'%(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) for info in infos],
           'created_file':'%d:%d:%04o:%d'%(leaf.st_uid,leaf.st_gid,stat.S_IMODE(leaf.st_mode),leaf.st_nlink),
           'receipt_status':receipt['status'],'mutating_calls_succeeded':receipt['mutating_calls']['succeeded'],'space_substituted':result['space_substituted']}
    for name,value in sorted(facts.items()):request.node.user_properties.append(('k4e0_'+name,value))
    if euid==0 and sys.platform.startswith('linux'):
        assert facts['noatime_is_the_kernel_flag'] and facts['created_directories']==['0:0:0700']*7 and facts['created_file']=='0:0:0600:1',facts

def test_native_refusals_leave_the_real_tree_exactly_as_it_was(tree):
    c3po=tree/RELATIVE[0];source=tree/RELATIVE[1];k9=tree/RELATIVE[2];var_lib=tree/'var'/'lib'
    def refused(plan,code):
        before=snapshot(tree);receipt=run(tree,plan)
        assert (receipt['status'],receipt['code'])==('REFUSED',code) and snapshot(tree)==before and receipt['mutating_calls']['issued']==0
        assert not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink','fsync') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    plan=fields(tree)
    c3po.mkdir();os.chmod(c3po,0o755)
    source.mkdir();refused(plan,'SOURCE_ROOT_PRESENT');source.rmdir()
    os.symlink('nowhere',source);refused(plan,'SOURCE_ROOT_PRESENT');os.unlink(source)
    k9.mkdir();refused(plan,'K9_ROOT_PRESENT');k9.rmdir()
    os.symlink('../..',k9);refused(plan,'K9_ROOT_PRESENT');os.unlink(k9)
    k9.write_bytes(b'x');refused(plan,'K9_ROOT_PRESENT');os.unlink(k9)
    os.chmod(c3po,0o775);refused(plan,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER');os.chmod(c3po,0o2755);refused(plan,'C3PO_DIRECTORY_SETGID')
    os.rmdir(c3po);os.symlink('../../mnt',c3po);refused(plan,'C3PO_DIRECTORY_NOT_A_DIRECTORY');os.unlink(c3po)
    c3po.write_bytes(b'x');refused(plan,'C3PO_DIRECTORY_NOT_A_DIRECTORY');os.unlink(c3po)
    os.chmod(var_lib,0o775);refused(plan,'PARENT_IDENTITY_MISMATCH');os.chmod(var_lib,0o755)
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(b'1f8fad5b-d9cb-469f-a165-70867728950e\n');refused(plan,'EVIDENCE_FROM_EARLIER_BOOT')
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(native_support.BOOT)
    os.rename(var_lib,tree/'var/real');os.symlink('real',var_lib);refused(plan,'PARENT_SYMLINK_COMPONENT');os.unlink(var_lib);os.rename(tree/'var/real',var_lib)
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt['code']

def test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary(tree):
    """Real races: a directory that appears at the mkdir of /var/lib/c3po (nothing changed: a refusal), one at the mkdir
    of the source root (/var/lib/c3po exists: partial), and a file at the runner's final name before the link."""
    k=k4e0.K();c3po=tree/RELATIVE[0];source=tree/RELATIVE[1];k9=tree/RELATIVE[2];tools=tree/RELATIVE[3]
    def racing_mkdir(target):
        def make(record):
            class Racing(k.m.Native):
                def mkdir(self,name,mode,dir_fd):
                    if name==target:record.real['mkdir'](name,0o755,dir_fd=dir_fd)
                    return k.m.Native.mkdir(self,name,mode,dir_fd)
            return Racing()
        return make
    receipt=run(tree,fields(tree),racing_mkdir(c3po.name))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CHANGED','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert list(c3po.iterdir())==[] and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    assert (receipt['directories'][0]['state'],receipt['directories'][0]['errno'])==('NOT_CREATED',errno.EEXIST) and receipt['objects_left_by_this_run']==0
    c3po.rmdir()
    receipt=run(tree,fields(tree),racing_mkdir(source.name))
    assert (receipt['status'],receipt['code'],receipt['objects_left_by_this_run'])==('PARTIAL_METADATA_REQUIRES_REVIEW','DESTINATION_APPEARED_AFTER_PRECHECK',1)
    assert stat.S_IMODE(os.lstat(c3po).st_mode)==0o700 and list(source.iterdir())==[] and not k9.exists()
    assert [entry['state'] for entry in receipt['directories']][:3]==['CREATED_DURABLE','NOT_CREATED','NOT_ATTEMPTED']
    os.rmdir(source);os.rmdir(c3po)
    def racing_link(record):
        class Racing(k.m.Native):
            def link(self,source_name,target,dir_fd):
                fd=record.real['open'](target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(fd,b'foreign');record.real['close'](fd)
                return k.m.Native.link(self,source_name,target,dir_fd)
        return Racing()
    receipt=run(tree,fields(tree),racing_link)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert (tools/k4e0.runner_name()).read_bytes()==b'foreign' and sorted(item.name for item in tools.iterdir())==[k4e0.runner_name()]
    assert receipt['ledger'][0]['state']=='NOT_CREATED' and receipt['ledger'][0]['temporary_removed'] is True and receipt['delivered'] is None

def test_native_where_it_cannot_write_is_a_refusal_with_the_errno_of_this_kernel(tree):
    if os.geteuid()==0:pytest.skip('root writes anywhere')
    var_lib=tree/'var'/'lib';os.chmod(var_lib,0o555);plan=fields(tree)
    try:receipt=run(tree,plan)
    finally:os.chmod(var_lib,0o755)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['directories'][0]['state'])==('REFUSED','FILESYSTEM_ACCESS_DENIED','EFFECTS','NOT_CREATED')
    assert not (tree/RELATIVE[0]).exists()

@pytest.mark.parametrize('point,made,names,links',[('after_mkdir_1',1,None,None),('after_mkdir_2',2,None,None),('after_mkdir_3',3,None,None),('after_mkdir_4',4,[],None),('after_mkdir_7',7,[],None),
                                                    ('in_write',7,['TEMPORARY'],1),('after_write',7,['TEMPORARY'],1),('after_link',7,['FINAL','TEMPORARY'],2),
                                                    ('after_unlink',7,['FINAL'],1)])
def test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs_a_root(tree,tmp_path,point,made,names,links):
    plan=fields(tree);go16=f.Docs(k4e0.K(),plan).go16();done=child(tree,plan,tmp_path,point)
    assert done.returncode==137 and done.stdout==b'','the process died: no receipt exists'
    present=[relative for relative in RELATIVE if os.path.lexists(str(tree/relative))];assert present==RELATIVE[:made]
    assert all(stat.S_IMODE(os.lstat(tree/relative).st_mode)==0o700 for relative in present)
    tools=tree/RELATIVE[3];temporary=tools/('.hostops-%s-0.partial'%go16);final=tools/k4e0.runner_name()
    if names is not None:
        assert sorted(item.name for item in tools.iterdir())==sorted({'TEMPORARY':temporary.name,'FINAL':final.name}[name] for name in names)
    if names and 'FINAL' in names:
        info=os.lstat(final);assert final.read_bytes()==k4e0.RUNNER and (stat.S_IMODE(info.st_mode),info.st_nlink)==(0o600,links),'only complete bytes ever stand under the final name'
    if names and 'TEMPORARY' in names:
        assert temporary.read_bytes()==(k4e0.RUNNER[:len(k4e0.RUNNER)//2] if point=='in_write' else k4e0.RUNNER)
    before=snapshot(tree);receipt=run(tree,fields(tree))
    if made==1:     # only /var/lib/c3po exists (root:root 0700): neither root does, so a new request completes and uses it unchanged
        assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['c3po_directory']['state']=='PRESENT' and receipt['c3po_directory']['created'] is False
    else:assert (receipt['status'],receipt['code'])==('REFUSED','SOURCE_ROOT_PRESENT') and snapshot(tree)==before

def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(monkeypatch):
    m=k4e0.K().m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()

def test_native_an_existing_root_c3po_directory_is_used_unchanged(tree,tmp_path):
    c3po=tree/'var/lib/c3po';c3po.mkdir();os.chmod(c3po,0o755);(c3po/'other').mkdir();before=os.lstat(c3po)
    done=child(tree,fields(tree),tmp_path);assert done.returncode==0,done.stderr.decode()[-2000:]
    receipt=json.loads(done.stdout)['receipt'];after=os.lstat(c3po)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['c3po_directory']['created'] is False,receipt['code']
    assert (after.st_ino,stat.S_IMODE(after.st_mode))==(before.st_ino,0o755) and sorted(item.name for item in c3po.iterdir())==['other','r2d2-v2-k9-20261005','r2d2-v2-source-20261005']
    assert receipt['delivered']['c3po_directory']['inode']==before.st_ino and receipt['mutating_calls']['succeeded']==10

def test_native_space_floor_is_judged_on_the_real_free_space_of_the_k9_filesystem(tree):
    """Without the substitution: the real f_bavail * f_frsize of the filesystem that holds the test tree decides."""
    real=os.statvfs(str(tree));available=real.f_bavail*real.f_frsize;receipt=run(tree,fields(tree),space=False)
    if available>=native_space.FLOOR:assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt['code']
    else:assert (receipt['status'],receipt['code'],receipt['mutating_calls']['issued'])==('REFUSED','K9_FILESYSTEM_FREE_SPACE_BELOW_FLOOR',0)
    assert receipt['_space_substituted'] is False

def test_native_identity_is_the_effective_uid_and_gid_and_fsync_reaches_the_kernel(tree):
    """No substitution: Native.identity() is the process's own effective uid and gid; and in a real run every fsync of
    the source is a call of os.fsync (recorded by the core's os-level record)."""
    m=k4e0.K().m;assert tuple(m.Native().identity())==(os.geteuid(),os.getegid())
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    synced=[entry['path'] for entry in receipt['_calls'] if entry['call']=='fsync']
    assert len(synced)==17 and k4e0.TOOLS in synced and '/var/lib' in synced and k4e0.C3PO in synced and not [path for path in synced if path.startswith('/mnt')]
