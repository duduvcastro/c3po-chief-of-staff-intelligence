"""K10 with the real system calls, made by the source's own unmodified Native, on a private temporary tree that stands
in for '/'. No host, no docker, no process started by the source. Nothing of Native is overridden for the runs that
count: the substitution of '/' and of the uid is made on the os module (tests/oslevel.py of the frozen core), the data
volume's own device by tests/native_support.py, and every system call is recorded with the arguments it received.
What this proves depends on the machine: on the workstation the real mkdir/open/write/fsync/link/unlink by dir_fd,
real O_EXCL|O_NOFOLLOW, real symbolic links, a real race, a real process death and the errno values of macOS as an
ordinary user, with a marker bit standing for O_NOATIME; the kernel's O_NOATIME, Linux errno values and real uid 0
only when the suite is run as root on Linux (the Linux job of the core, with this directory as its argument).
With a checkout of the release (HOSTOPS02_TEST_RELEASE_REPOSITORY) and the application's dependencies, the file this
source wrote is then read by the application's own reader and verified by the application's own Release.verify."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k10
import native_child
import native_support

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
DATA='/mnt/day-d-data'
LEAF=DATA+'/'+k10.LEAF
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

@pytest.fixture
def tree(tmp_path):return native_support.build_tree(tmp_path)

def fields(root,raw=k10.RELEASE):
    return {'parent':native_support.rows(root,DATA),'release':k10.release_member(raw),'evidence_boot_id_sha256':f.sha(native_support.BOOT.strip())}
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
    """One run in this process with the module's own Native (host=None), or with a subclass of it that only adds a race."""
    k=k10.K();old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record:receipt=f.Docs(k,plan).run(host(record) if host else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt


# ---------------------------------------------------------------- the install, for real
def test_native_install_creates_the_directory_and_the_file_with_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls'];base=tree/'mnt/day-d-data'/k10.LEAF
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED',None),receipt
    assert sorted(item.name for item in base.iterdir())==[k10.NAME] and (base/k10.NAME).read_bytes()==k10.RELEASE
    info=os.lstat(base/k10.NAME);assert (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode),info.st_size)==(0o600,1,True,len(k10.RELEASE))
    assert stat.S_IMODE(os.lstat(base).st_mode)==0o700 and stat.S_ISDIR(os.lstat(base).st_mode)
    assert receipt['installed']['sha256']==f.sha(k10.RELEASE) and receipt['ledger'][0]['inode']==info.st_ino and receipt['precheck']['free_bytes']>=1048576
    # what the read path hands to the kernel
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(not entry['flags']&READ_ONLY_OPEN for entry in opens)
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat'];assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats)
    assert all(entry['path']!='?' for entry in calls if entry['call'] in ('fstat','fsync')) and all(entry['by_fd'] for entry in calls if entry['call']=='scandir')
    # what changes the tree: one mkdir, one exclusive create, one link, one unlink, all relative to a held descriptor
    temporary=LEAF+'/.hostops-%s-0.partial'%result['go16']
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[('mkdir',LEAF),('open',temporary),('link',LEAF+'/'+k10.NAME),('unlink',temporary)]
    assert all(entry['by_dir_fd'] for entry in changing) and changing[0]['mode']==0o700 and changing[1]['mode']==0o600
    wanted=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC;assert changing[1]['flags']&wanted==wanted and not changing[1]['flags']&(os.O_TRUNC|os.O_APPEND)
    assert changing[2]['follow_symlinks'] is False and changing[2]['same_directory'] and changing[2]['source']==temporary
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    assert [entry['path'] for entry in calls if entry['call']=='fsync']==[LEAF,DATA,temporary,LEAF,LEAF]
    readback=[entry for entry in opens if entry['path']==LEAF+'/'+k10.NAME];assert len(readback)==1 and readback[0]['flags']&os.O_NONBLOCK and readback[0]['by_dir_fd']
    # the interpreter's own audit events: nothing but these creations, no process, no chmod, chown, rename or truncate
    assert sorted({event[0] for event in events})==['open','open-for-writing','os.link','os.mkdir','os.remove']
    assert [event[0] for event in events if event[0]!='open']==['os.mkdir','open-for-writing','os.link','os.remove']
    after=snapshot(tree);outside=lambda items:{name:value for name,value in items.items() if not name.startswith('mnt/day-d-data')}
    assert outside(after)==outside(before) and sorted(set(after)-set(before))==['mnt/day-d-data/'+k10.LEAF,'mnt/day-d-data/'+k10.LEAF+'/'+k10.NAME]
    assert after['mnt/day-d-data/.r2d2-v2-pinned']==before['mnt/day-d-data/.r2d2-v2-pinned'],'the pin is looked at, never touched'

def filesystem_type(path):
    """The type of the filesystem that holds path, from this process's mount table (Linux); UNKNOWN elsewhere."""
    try:lines=Path('/proc/self/mountinfo').read_text(encoding='utf-8',errors='replace').splitlines()
    except OSError:return 'UNKNOWN'
    target=os.path.realpath(str(path));best=('','UNKNOWN')
    for line in lines:
        left,separator,right=line.partition(' - ');fields_,tail=left.split(' '),right.split(' ')
        if separator!=' - ' or len(fields_)<5 or not tail[0]:continue
        point=fields_[4].replace('\\040',' ')
        if (target==point or target.startswith(point.rstrip('/')+'/')) and len(point)>=len(best[0]):best=(point,tail[0])
    return best[1]

RECORD_PREFIX='k10_'
def test_native_run_records_where_it_ran_for_the_linux_proof(tree,tmp_path,request):
    """One real install, and what it ran on, written into the junit file as properties of this test case. They are
    what binding/linux_proof.py reads: the Linux job proves the mutating path as real root only if this test ran there
    with effective uid 0, the kernel's O_NOATIME, and created a directory and a file that the kernel itself made
    root:root (no substitution: the values below are read with the unpatched os module after the run)."""
    euid,egid=os.geteuid(),os.getegid();done=child(tree,fields(tree),tmp_path);assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt=result['receipt'];base=tree/'mnt/day-d-data'/k10.LEAF
    assert (receipt['status'],receipt['outcome'])==('METADATA_ONLY_REQUIRES_REVIEW','RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED'),receipt
    directory,leaf=os.lstat(base),os.lstat(base/k10.NAME);assert (base/k10.NAME).read_bytes()==k10.RELEASE
    assert (stat.S_IMODE(directory.st_mode),stat.S_IMODE(leaf.st_mode),leaf.st_nlink)==(0o700,0o600,1) and (directory.st_uid,leaf.st_uid)==(euid,euid)
    sums=k10.DIRECTORY/'SHA256SUMS'
    facts={'payload_sha256':f.sha(k10.K().source),'sha256sums_sha256':f.sha(sums.read_bytes()) if sums.is_file() else 'ABSENT',
           'euid':euid,'egid':egid,'platform':sys.platform,'python':'%d.%d.%d'%sys.version_info[:3],
           'noatime_is_the_kernel_flag':bool(result['noatime_is_the_kernel_flag']),'filesystem_type':filesystem_type(tree),
           'created_directory':'%d:%d:%04o'%(directory.st_uid,directory.st_gid,stat.S_IMODE(directory.st_mode)),
           'created_file':'%d:%d:%04o:%d'%(leaf.st_uid,leaf.st_gid,stat.S_IMODE(leaf.st_mode),leaf.st_nlink),
           'receipt_status':receipt['status'],'mutating_calls_succeeded':receipt['mutating_calls']['succeeded'],
           'linked_and_unlinked_by_dir_fd':[entry['call'] for entry in result['calls'] if entry['call'] in ('link','unlink') and entry['by_dir_fd']]==['link','unlink']}
    for name,value in sorted(facts.items()):request.node.user_properties.append((RECORD_PREFIX+name,value))
    if euid==0 and sys.platform.startswith('linux'):
        assert facts['noatime_is_the_kernel_flag'] and facts['created_directory']=='0:0:0700' and facts['created_file']=='0:0:0600:1',facts

def test_native_refusals_leave_the_real_tree_exactly_as_it_was(tree):
    volume=tree/'mnt/day-d-data';base=volume/k10.LEAF
    def refused(plan,code):
        before=snapshot(tree);receipt=run(tree,plan)
        assert (receipt['status'],receipt['code'])==('REFUSED',code) and snapshot(tree)==before and receipt['mutating_calls']['issued']==0
        assert not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink','fsync') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    plan=fields(tree);base.mkdir();refused(plan,'DESTINATION_PRESENT');base.rmdir()
    os.symlink('provider=synthetic',base);refused(plan,'DESTINATION_PRESENT');os.unlink(base)
    os.symlink('nowhere',base);refused(plan,'DESTINATION_PRESENT');os.unlink(base)                       # a dangling link is a name that exists
    base.write_bytes(k10.RELEASE);refused(plan,'DESTINATION_PRESENT');os.unlink(base)
    pin=volume/'.r2d2-v2-pinned';os.unlink(pin);refused(plan,'MAINTENANCE_PIN_ABSENT')
    os.symlink('provider=synthetic',pin);refused(plan,'MAINTENANCE_PIN_NOT_A_REGULAR_FILE');os.unlink(pin)
    pin.mkdir();refused(plan,'MAINTENANCE_PIN_NOT_A_REGULAR_FILE');pin.rmdir();pin.write_bytes(b'');os.chmod(pin,0o600)
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(b'1f8fad5b-d9cb-469f-a165-70867728950e\n');refused(plan,'EVIDENCE_FROM_EARLIER_BOOT')
    (tree/'proc/sys/kernel/random/boot_id').write_bytes(native_support.BOOT)
    os.chmod(volume,0o700);refused(plan,'PARENT_IDENTITY_MISMATCH');os.chmod(volume,0o755)
    os.rename(volume,tree/'mnt/real');os.symlink('real',volume);refused(plan,'PARENT_SYMLINK_COMPONENT');os.unlink(volume)
    (tree/'mnt/day-d-data').mkdir(mode=0o755);os.chmod(tree/'mnt/day-d-data',0o755);refused(plan,'PARENT_IDENTITY_MISMATCH')    # another directory at the path: another inode
    os.rmdir(tree/'mnt/day-d-data');os.rename(tree/'mnt/real',volume)
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',receipt['code']

def test_native_a_volume_that_is_not_a_mount_point_is_refused_from_the_signed_rows(tree):
    """Rows read without the device substitution are those of an unmounted volume: one filesystem from "/" down."""
    import oslevel
    plan=fields(tree);plan['parent']=oslevel.rows(tree,DATA);docs=f.Docs(k10.K(),plan)
    assert f.refusal(docs.authenticate)=='DATA_VOLUME_NOT_A_MOUNT_POINT'

def test_native_never_replaces_a_name_that_appears_and_withdraws_only_its_own_temporary(tree):
    """Real races: a directory that appears between the precheck and the mkdir, and a file that appears between the
    precheck and the link. The kernel refuses both calls; what appeared is untouched."""
    k=k10.K();base=tree/'mnt/day-d-data'/k10.LEAF
    def racing_mkdir(record):
        class Racing(k.m.Native):
            def mkdir(self,name,mode,dir_fd):
                record.real['mkdir'](name,0o755,dir_fd=dir_fd);return k.m.Native.mkdir(self,name,mode,dir_fd)
        return Racing()
    receipt=run(tree,fields(tree),racing_mkdir)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CHANGED','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert list(base.iterdir())==[] and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    assert (receipt['directories'][0]['state'],receipt['directories'][0]['errno'])==('NOT_CREATED',errno.EEXIST) and receipt['objects_left_by_this_run']==0
    base.rmdir()
    def racing_link(record):
        class Racing(k.m.Native):
            def link(self,source,target,dir_fd):
                fd=record.real['open'](target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(fd,b'foreign');record.real['close'](fd)
                return k.m.Native.link(self,source,target,dir_fd)
        return Racing()
    receipt=run(tree,fields(tree),racing_link)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION','DESTINATION_APPEARED_AFTER_PRECHECK')
    assert (base/k10.NAME).read_bytes()==b'foreign' and sorted(item.name for item in base.iterdir())==[k10.NAME]
    assert receipt['ledger'][0]['state']=='NOT_CREATED' and receipt['ledger'][0]['temporary_removed'] is True and receipt['installed'] is None

def test_native_on_a_volume_it_cannot_write_is_a_refusal_with_the_errno_of_this_kernel(tree):
    if os.geteuid()==0:pytest.skip('root writes anywhere')
    volume=tree/'mnt/day-d-data';os.chmod(volume,0o555);plan=fields(tree);before=snapshot(tree)
    try:receipt=run(tree,plan)
    finally:os.chmod(volume,0o755)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['directories'][0]['state'])==('REFUSED','FILESYSTEM_ACCESS_DENIED','EFFECTS','NOT_CREATED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and not (volume/k10.LEAF).exists()

def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(monkeypatch):
    m=k10.K().m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()


# ---------------------------------------------------------------- a real process death at each point, and what is found afterwards
@pytest.mark.parametrize('point,names,links',[('after_mkdir',[],None),('in_write',['TEMPORARY'],1),('after_write',['TEMPORARY'],1),
                                               ('after_link',['FINAL','TEMPORARY'],2),('after_unlink',['FINAL'],1)])
def test_native_process_death_leaves_a_state_a_later_read_tells_apart_and_a_second_run_never_repairs(tree,tmp_path,point,names,links):
    plan=fields(tree);go16=f.Docs(k10.K(),plan).go16();done=child(tree,plan,tmp_path,point)
    assert done.returncode==137 and done.stdout==b'','the process died: no receipt exists'
    base=tree/'mnt/day-d-data'/k10.LEAF;temporary=base/('.hostops-%s-0.partial'%go16);final=base/k10.NAME
    assert stat.S_IMODE(os.lstat(base).st_mode)==0o700 and sorted(item.name for item in base.iterdir())==sorted({'TEMPORARY':temporary.name,'FINAL':final.name}[name] for name in names)
    if 'FINAL' in names:
        info=os.lstat(final);assert final.read_bytes()==k10.RELEASE and (stat.S_IMODE(info.st_mode),info.st_nlink)==(0o600,links),'only complete bytes ever stand under the final name'
    if 'TEMPORARY' in names:
        info=os.lstat(temporary);assert stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==links
        assert temporary.read_bytes()==(k10.RELEASE[:len(k10.RELEASE)//2] if point=='in_write' else k10.RELEASE)
    if names==['FINAL','TEMPORARY']:assert os.lstat(final).st_ino==os.lstat(temporary).st_ino
    # there is no second attempt: a new request finds the directory and refuses, and nothing is repaired or removed
    before=snapshot(tree);receipt=run(tree,fields(tree))
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and snapshot(tree)==before


# ---------------------------------------------------------------- the application reads what this source wrote
APP_CHECK='''
import hashlib,json,sys
sys.path.insert(0,sys.argv[1])
from datetime import datetime
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_shadow import Release
from app.r2d2_v2_shadow_worker import _release_bytes
from app.r2d2_v2_store import ShadowIntegrityError
data=_release_bytes(sys.argv[2])                       # the worker's own reader: O_NOFOLLOW, regular, no group or other bit, at most 65536 bytes
out={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
release=Release.verify(data,out["sha256"],now=datetime.fromisoformat(sys.argv[4]),build_sha=sys.argv[3],calendar=ShadowCalendar())
out.update(mode=release.mode,epoch=release.epoch,first_session=release.first_session.isoformat(),receipt_sha=release.receipt_sha)
try:Release.verify(data,out["sha256"],now=datetime.fromisoformat(sys.argv[4]),build_sha=sys.argv[5],calendar=ShadowCalendar());out["deployed_build"]="VERIFIED"
except ShadowIntegrityError as error:out["deployed_build"]=str(error)
print(json.dumps(out,sort_keys=True))
'''
@pytest.fixture(scope='module')
def application(tmp_path_factory):
    """c3po/backend/app of the release, extracted from a checkout that holds it (read-only: git archive)."""
    repository=os.environ.get('HOSTOPS02_TEST_RELEASE_REPOSITORY')
    if not repository:pytest.skip('HOSTOPS02_TEST_RELEASE_REPOSITORY is not set: no checkout of the release on this machine')
    if importlib.util.find_spec('exchange_calendars') is None:pytest.skip('this interpreter has no exchange_calendars: the application cannot build its calendar')
    target=tmp_path_factory.mktemp('release-tree')
    archive=subprocess.run(['git','-C',repository,'archive',REVISION,'c3po/backend/app'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    if archive.returncode!=0:pytest.skip('the checkout does not hold the release revision')
    done=subprocess.run(['tar','-x','-C',str(target)],input=archive.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120);assert done.returncode==0
    return target/'c3po'/'backend'

def test_native_the_file_written_is_read_by_the_workers_own_reader_and_verified_by_the_applications_release_verify(tree,tmp_path,application):
    """The whole point of the layout: the bytes this source left on a real filesystem are accepted by
    r2d2_v2_shadow_worker._release_bytes and by r2d2_v2_shadow.Release.verify of the release itself (the fixture's
    synthetic build revision; with the deployed revision the application refuses the fixture, as it must)."""
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    path=tree/'mnt/day-d-data'/k10.LEAF/k10.NAME
    done=subprocess.run([sys.executable,'-B','-c',APP_CHECK,str(application),str(path),k10.RECORD['build_revision_used'],k10.RECORD['verified_at_instant'],REVISION],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=300)
    assert done.returncode==0,done.stderr.decode()[-3000:]
    result=json.loads(done.stdout)
    assert result=={'bytes':len(k10.RELEASE),'sha256':receipt['installed']['sha256'],'mode':'CERTIFIED','epoch':'R2D2-V2-SHADOW-2026-10-05','first_session':'2026-10-05',
                    'receipt_sha':f.sha(k10.RELEASE),'deployed_build':'RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED'}

def test_native_the_fixture_record_is_the_fixture_and_the_release_package_of_the_checkout(application):
    """The package hash the fixture carries is the one the release tree computes for itself."""
    done=subprocess.run([sys.executable,'-B','-c','import sys;sys.path.insert(0,sys.argv[1]);from app.r2d2_v2_earnings_package import implementation_package_sha as p;print(p())',
                         str(application)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=300)
    assert done.returncode==0 and done.stdout.decode().strip()==k10.RECORD['implementation_package_sha']==json.loads(k10.RELEASE)['implementation_package_sha']
    assert k10.RECORD['release_sha256']==f.sha(k10.RELEASE) and k10.RECORD['release_bytes']==len(k10.RELEASE)


# ---------------------------------------------------------------- the security guard and the directory this source creates
def test_native_release_directory_does_not_hold_the_security_routine_by_itself_and_the_pin_still_does(tree,tmp_path):
    """scripts/c3po_security_guard.py of the release, run on the real tree after the install: with the pin it says a
    trial is present (the pin); without the pin the release DIRECTORY alone does not (the guard reads root-level
    r2d2-v2-release-*.json files); the same release as a root-level .json file would."""
    repository=os.environ.get('HOSTOPS02_TEST_RELEASE_REPOSITORY')
    if not repository:pytest.skip('HOSTOPS02_TEST_RELEASE_REPOSITORY is not set: no checkout of the release on this machine')
    shown=subprocess.run(['git','-C',repository,'show',REVISION+':scripts/c3po_security_guard.py'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    if shown.returncode!=0:pytest.skip('the checkout does not hold the release revision')
    guard=tmp_path/'c3po_security_guard.py';guard.write_bytes(shown.stdout)
    receipt=run(tree,fields(tree));assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW';volume=tree/'mnt/day-d-data'
    def present():
        code='import sys;sys.path.insert(0,sys.argv[1]);from datetime import datetime;from pathlib import Path;import c3po_security_guard as g;print(g.trial_present(datetime(2026,10,9,22,0),Path(sys.argv[2])))'
        done=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path),str(volume)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
        assert done.returncode==0,done.stderr.decode();return done.stdout.decode().strip()
    assert present()=='True';os.unlink(volume/'.r2d2-v2-pinned');assert present()=='False'
    (volume/'r2d2-v2-release-20261005.json').write_bytes(k10.RELEASE);assert present()=='True'
