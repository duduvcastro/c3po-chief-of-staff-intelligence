"""K8 with the real system calls, made by the source's own unmodified Native, on a private temporary tree that stands in
for '/'. No host, no docker, no process started by the source. The substitution of '/' and of the uid is made on the
os module (tests/oslevel.py of the frozen core), and every system call is recorded with the arguments it received.
On the workstation this proves real open/write/fsync/link/unlink by dir_fd, real O_EXCL|O_NOFOLLOW, real '=' names, real
races and a real process death, with macOS errno values as an ordinary user; the kernel's O_NOATIME, Linux errno values
and real uid 0 only when the suite is run as root on Linux (the Linux-root CI job: NOT RUN by the author).
The tree's device and inode numbers are not the ones the fixture configs pin, so these runs sign REPORT_ONLY and the
receipt says the three identities differ; the identity comparison itself is exercised on the emulated host."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k8
import native_child
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
DAY=k8.DAY
RELATIVE=[(root,name) for _,root,name in k8.names()]

@pytest.fixture
def tree(tmp_path):
    """A private tree that stands in for "/": the boot identifier, the capacity tree with the chain documents, the K9
    tree with the day's three files of the commit step. Every directory 0755 above /var/lib, 0700 below."""
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','var/lib'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    capacity=root/'var/lib/c3po-capacity';capacity.mkdir(mode=0o700)
    for name in k8.ROOTS:(capacity/name).mkdir(mode=0o700)
    for path in [capacity]+[capacity/name for name in k8.ROOTS]:os.chmod(path,0o700)
    for name,data in k8.chain().items():
        (capacity/'documents'/name).write_bytes(data);os.chmod(capacity/'documents'/name,0o600)
    c3po=root/'var/lib/c3po';c3po.mkdir();os.chmod(c3po,0o755)
    day=root/('var/lib/c3po/r2d2-v2-k9-20261005/days/'+DAY)
    for path in ('var/lib/c3po/r2d2-v2-k9-20261005','var/lib/c3po/r2d2-v2-k9-20261005/days','var/lib/c3po/r2d2-v2-k9-20261005/days/'+DAY,
                 'var/lib/c3po/r2d2-v2-k9-20261005/days/'+DAY+'/causal','var/lib/c3po/r2d2-v2-k9-20261005/days/'+DAY+'/receipts'):
        (root/path).mkdir(mode=0o700);os.chmod(root/path,0o700)
    for path,data in ((day/'causal'/'commitment.private.json',k8.commitment_of()),(day/'causal'/'build_audit_receipt.json',k8.audit_of()),
                      (day/'receipts'/'commit_launch.RECEIPT.json',k8.commit_receipt())):
        path.write_bytes(data);os.chmod(path,0o600)
    return root

def fields(root,rule='REPORT_ONLY'):
    files=k8.files_of()
    return {'day':DAY,'windows':list(k8.WINDOWS),'contract':k8.blob(files['contract']),
            'files':{key:k8.blob(data) for key,data in files.items() if key!='contract'},'days_parent':oslevel.rows(root,k8.DAYS),
            'identity_rule':rule,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
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
def run(root,plan,host=None):
    k=k8.K();old=os.umask(0o027)
    try:
        with oslevel.Substitute(root) as record:receipt=f.Docs(k,plan,now=k8.moment()).run(host(record) if host else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt
def delivered(root):
    return [(root_,name) for root_,name in RELATIVE if os.path.lexists(str(root/'var/lib/c3po-capacity'/root_/name))]
CONTENTS=[k8.files_of()[key] for key,_,_ in k8.names()[:-1]]+[k8.payload_of()]


def test_native_k8_delivers_the_thirteen_files_with_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK',None),receipt
    capacity=tree/'var/lib/c3po-capacity'
    for (root,name),data in zip(RELATIVE,CONTENTS):
        info=os.lstat(capacity/root/name);assert (stat.S_ISREG(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink)==(True,0o600,1),name
        assert (capacity/root/name).read_bytes()==data,name
    assert receipt['delivered']['root_identities_equal_the_config']=={'documents':False,'go':False,'payload':False} and receipt['delivered']['identity_rule']=='REPORT_ONLY'
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(not entry['flags']&(os.O_WRONLY|os.O_RDWR|os.O_TRUNC|os.O_APPEND) for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat'];assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats)
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    wanted=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    expected=[]
    for index,(root,name) in enumerate(RELATIVE):
        temporary='/var/lib/c3po-capacity/%s/.hostops-%s-%d.partial'%(root,result['go16'],index)
        expected+=[('open',temporary),('link','/var/lib/c3po-capacity/%s/%s'%(root,name)),('unlink',temporary)]
    assert [(entry['call'],entry['path']) for entry in changing]==expected
    assert all(entry['by_dir_fd'] for entry in changing) and all(entry['flags']&wanted==wanted and entry['mode']==0o600 for entry in changing if entry['call']=='open')
    assert all(entry['follow_symlinks'] is False and entry['same_directory'] for entry in changing if entry['call']=='link')
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    assert sorted({event[0] for event in events})==['open','open-for-writing','os.link','os.remove']
    assert [event[0] for event in events if event[0]!='open']==['open-for-writing','os.link','os.remove']*13
    after=snapshot(tree);new=sorted(set(after)-set(before))
    assert new==sorted('var/lib/c3po-capacity/%s/%s'%item for item in RELATIVE)
    for name in before:
        if not name.startswith('var/lib/c3po-capacity/') or name.count('/')>3:assert after[name][:4]==before[name][:4],name
    k9=[name for name in before if name.startswith('var/lib/c3po/')];assert all(after[name]==before[name] for name in k9),'the K9 tree is read, never touched'

def test_native_run_records_where_it_ran_for_the_linux_proof(tree,tmp_path,request):
    """One real run, and what it ran on, written into the junit file as properties of this test case (prefix k8_). On
    Linux as root it also asserts what the kernel made."""
    euid,egid=os.geteuid(),os.getegid();done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt=result['receipt'];assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt
    infos=[os.lstat(tree/'var/lib/c3po-capacity'/root/name) for root,name in RELATIVE];sums=k8.DIRECTORY/'SHA256SUMS'
    facts={'payload_sha256':f.sha(k8.K().source),'sha256sums_sha256':f.sha(sums.read_bytes()) if sums.is_file() else 'ABSENT',
           'euid':euid,'egid':egid,'platform':sys.platform,'python':'%d.%d.%d'%sys.version_info[:3],
           'noatime_is_the_kernel_flag':bool(result['noatime_is_the_kernel_flag']),
           'created_files':['%d:%d:%04o:%d'%(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink) for info in infos],
           'receipt_status':receipt['status'],'mutating_calls_succeeded':receipt['mutating_calls']['succeeded']}
    for name,value in sorted(facts.items()):request.node.user_properties.append(('k8_'+name,value))
    if euid==0 and sys.platform.startswith('linux'):
        assert facts['noatime_is_the_kernel_flag'] and facts['created_files']==['0:0:0600:1']*13,facts

def test_native_refusals_leave_the_real_tree_exactly_as_it_was(tree):
    capacity=tree/'var/lib/c3po-capacity';day=tree/('var/lib/c3po/r2d2-v2-k9-20261005/days/'+DAY)
    def refused(plan,code):
        before=snapshot(tree);receipt=run(tree,plan)
        assert (receipt['status'],receipt['code'])==('REFUSED',code) and snapshot(tree)==before and receipt['mutating_calls']['issued']==0,receipt['code']
        assert not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink','fsync') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    plan=fields(tree)
    refused(fields(tree,'REFUSE_ON_MISMATCH'),'CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')
    payload=capacity/'payload'/('session=%s.json'%DAY);payload.write_bytes(b'x');os.chmod(payload,0o600);refused(plan,'DESTINATION_PRESENT');os.unlink(payload)
    os.symlink('nowhere',payload);refused(plan,'DESTINATION_PRESENT');os.unlink(payload)
    os.chmod(capacity/'go',0o755);refused(plan,'CAPACITY_DIRECTORY_NOT_PRIVATE');os.chmod(capacity/'go',0o700)
    name=sorted(k8.chain())[0];data=(capacity/'documents'/name).read_bytes();(capacity/'documents'/name).write_bytes(data+b' ')
    refused(plan,'CHAIN_DOCUMENT_NOT_AS_PINNED');(capacity/'documents'/name).write_bytes(data)
    os.chmod(capacity/'documents'/name,0o644);refused(plan,'CHAIN_DOCUMENT_NOT_PRIVATE');os.chmod(capacity/'documents'/name,0o600)
    commitment=day/'causal'/'commitment.private.json';commitment.write_bytes(k8.commitment_of()+b'\n');refused(plan,'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')
    commitment.write_bytes(k8.commitment_of())
    receipt_file=day/'receipts'/'commit_launch.RECEIPT.json';receipt_file.write_bytes(k8.commit_receipt(status='FAILED'));refused(plan,'COMMIT_RECEIPT_NOT_COMPLETE')
    receipt_file.write_bytes(k8.commit_receipt())
    os.rename(day/'causal',day/'causal-real');os.symlink('causal-real',day/'causal');refused(plan,'K9_DIRECTORY_NOT_PRIVATE')
    os.unlink(day/'causal');os.rename(day/'causal-real',day/'causal')
    os.chmod(tree/'var/lib/c3po',0o775);refused(plan,'PARENT_IDENTITY_MISMATCH');os.chmod(tree/'var/lib/c3po',0o755)
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(b'1f8fad5b-d9cb-469f-a165-70867728950e\n');refused(plan,'EVIDENCE_FROM_EARLIER_BOOT')
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt['code']

def test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary(tree):
    k=k8.K();capacity=tree/'var/lib/c3po-capacity'
    def racing_link(position):
        def make(record):
            count=[-1]
            class Racing(k.m.Native):
                def link(self,source_name,target,dir_fd):
                    count[0]+=1
                    if count[0]==position:
                        fd=record.real['open'](target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(fd,b'foreign');record.real['close'](fd)
                    return k.m.Native.link(self,source_name,target,dir_fd)
            return Racing()
        return make
    receipt=run(tree,fields(tree),racing_link(8))
    assert (receipt['status'],receipt['code'],receipt['objects_left_by_this_run'])==('PARTIAL_METADATA_REQUIRES_REVIEW','DESTINATION_APPEARED_AFTER_PRECHECK',8)
    root,name=RELATIVE[8];assert (capacity/root/name).read_bytes()==b'foreign' and sorted(item.name for item in (capacity/root).iterdir())==sorted(
        n for r,n in RELATIVE[:9] if r==root)
    assert receipt['ledger'][8]['state']=='NOT_CREATED' and receipt['ledger'][8]['temporary_removed'] is True and receipt['ledger'][8]['errno']==errno.EEXIST
    assert delivered(tree)==RELATIVE[:9] and receipt['delivered'] is None

@pytest.mark.parametrize('point,count,linked',[('in_write_0',0,None),('after_link_0',1,True),('after_unlink_0',1,False),('in_write_7',7,None),
                                               ('after_link_12',13,True),('after_unlink_12',13,False)])
def test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs(tree,tmp_path,point,count,linked):
    plan=fields(tree);go16=f.Docs(k8.K(),plan,now=k8.moment()).go16();done=child(tree,plan,tmp_path,point)
    assert done.returncode==137 and done.stdout==b'','the process died: no receipt exists'
    assert delivered(tree)==RELATIVE[:count]
    capacity=tree/'var/lib/c3po-capacity'
    for (root,name),data in zip(RELATIVE[:count],CONTENTS):
        info=os.lstat(capacity/root/name);assert (capacity/root/name).read_bytes()==data and stat.S_IMODE(info.st_mode)==0o600,'only complete bytes ever stand under a final name'
    temporaries=sorted(str(path.relative_to(capacity)) for path in capacity.rglob('.hostops-*'))
    if point.startswith('in_write'):
        index=int(point.rsplit('_',1)[1]);root,_=RELATIVE[index]
        assert temporaries==['%s/.hostops-%s-%d.partial'%(root,go16,index)] and (capacity/temporaries[0]).read_bytes()==CONTENTS[index][:len(CONTENTS[index])//2]
    elif linked:
        index=count-1;root,name=RELATIVE[index];assert temporaries==['%s/.hostops-%s-%d.partial'%(root,go16,index)] and os.lstat(capacity/root/name).st_nlink==2
    else:assert temporaries==[]
    before=snapshot(tree);receipt=run(tree,fields(tree))
    if count:assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','DESTINATION_PRESENT','PRECHECK') and snapshot(tree)==before
    else:
        # the same request again: its temporary name is the one the dead run left, and an exclusive creation refuses it
        assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','TEMPORARY_NAME_OCCUPIED','EFFECTS') and snapshot(tree)==before

def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(monkeypatch):
    m=k8.K().m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()

def test_native_identity_is_the_effective_uid_and_gid_and_fsync_reaches_the_kernel(tree):
    m=k8.K().m;assert tuple(m.Native().identity())==(os.geteuid(),os.getegid())
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    synced=[entry['path'] for entry in receipt['_calls'] if entry['call']=='fsync']
    assert len(synced)==13*3 and synced.count('/var/lib/c3po-capacity/payload')==2 and synced.count('/var/lib/c3po-capacity/documents')==14

def test_native_free_space_is_the_real_free_space_of_the_capacity_filesystem(tree):
    real=os.statvfs(str(tree));receipt=run(tree,fields(tree))
    if real.f_bavail*real.f_frsize>=4194304:assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['precheck']['free_bytes']>=4194304
    else:assert receipt['code']=='CAPACITY_FREE_SPACE_BELOW_FLOOR'
