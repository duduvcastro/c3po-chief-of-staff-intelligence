"""The real system calls, made by the sources' own unmodified Native classes, on a private temporary tree that stands
in for '/'. No host, no docker, no systemd. Nothing of Native is overridden: the substitution of '/' and of the uid
is made on the os module (tests/oslevel.py), and every system call is recorded with the arguments it received.
What this proves depends on the machine it runs on: on the workstation the real mkdir/open/link/unlink/fsync by
dir_fd, real O_EXCL|O_NOFOLLOW, real symbolic links and real errno values of macOS as an ordinary user, with a marker
bit standing for O_NOATIME; the kernel's O_NOATIME, Linux errno values and real uid 0 only when the suite is run as
root on Linux (never done so far)."""
from datetime import timedelta
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import native_child
import oslevel

LEAF=f.LEAF
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('etc/systemd/system','var/lib','mnt/day-d-data','usr/lib/systemd/system','run/systemd/system','proc/sys/kernel/random','srv'):
        (root/path).mkdir(parents=True,mode=0o755)
    for path in root.rglob('*'):os.chmod(path,0o755)
    os.chmod(root,0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT);(root/'proc/sys/kernel/core_pattern').write_bytes(b'core\n')
    return root

rows=oslevel.rows
VOLUME='/mnt/day-d-data';CAPACITY={'root_path':'/srv/c3po-capacity','receipt_directory_path':'/var/lib/c3po-reader/capacity-receipts'}
GROUPS=['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY']
# The journal root in the placement signed for the first epoch (A: next to the state root) unless a test asks for B.
JOURNAL={'A':'var/lib/c3po-bar/'+f.A_LEAF,'B':'mnt/day-d-data/'+LEAF}
def expected(placement='A'):
    return ['etc/c3po-bar','etc/c3po-bar/manifests','etc/c3po-bar/docker-cli','var/lib/c3po-bar','var/lib/c3po-bar/supervisor',JOURNAL[placement],
            'etc/c3po-reader','etc/c3po-reader/docker-cli','var/lib/c3po-reader','srv/c3po-capacity','srv/c3po-capacity/config','srv/c3po-capacity/documents',
            'srv/c3po-capacity/payload','srv/c3po-capacity/go','var/lib/c3po-reader/capacity-receipts']
EXPECTED=expected()
BOOT_SHA=f.sha(BOOT.strip())
def values_of(placement):return dict(f.values_of(placement),HOST_JOURNAL_ROOT='/'+JOURNAL[placement])

def provision_fields(root,groups=GROUPS,placement='A'):
    m=f.load('provision').m;placement=placement if 'JOURNAL_LEAF' in groups else None
    volume=VOLUME if (placement=='B' or 'CAPACITY' in groups) else None
    leaf=(LEAF if placement=='B' else f.A_LEAF) if 'JOURNAL_LEAF' in groups else None;capacity=dict(CAPACITY) if 'CAPACITY' in groups else None
    table=m.layout(groups,volume,leaf,capacity,placement)
    return {'groups':list(groups),'journal_placement':placement,'data_volume_path':volume,'journal_leaf':leaf,'existing_journal_leaves':[],'capacity':capacity,
            'chains':{name:rows(root,path) for name,path in m.chain_paths(table,volume,capacity).items()},
            'creates':[dict(row,expect='ABSENT') for row in table],'retention_tag':None,'evidence_boot_id_sha256':BOOT_SHA}
def install_fields(root,placement='A'):
    return {'unit_directory':rows(root,'/etc/systemd/system'),'units':f.supervisor_units(values_of(placement)),'network_allowlist':['bridge'],
            'journal_placement':placement,'data_volume_path':VOLUME,'deploy_tree_path':f.tree_of(placement),
            'template_revision':'d7600b4d14f8a67694ffb37cde06b622f9a3bac3','acknowledged_leftovers':[],'daemon_reload_owner':'OPERATION_5_ACTIVATION_GO',
            'evidence_boot_id_sha256':BOOT_SHA}

def child(op,root,fields,tmp_path):
    path=Path(str(tmp_path))/('fields-%s.json'%op);path.write_bytes(json.dumps(fields).encode())
    done=subprocess.run([sys.executable,'-B',str(Path(native_child.__file__)),op,str(root),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);return result['receipt'],result['events'],result['calls']
def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
def run(op,root,fields,host=None,now=f.NOW):
    """One run in this process with the module's own Native (host=None), or with a subclass of it that only adds a race."""
    k=f.load(op);old=os.umask(0o027)
    try:
        with oslevel.Substitute(root) as record:receipt=f.Docs(k,fields,now=now).run(host(record) if host else None)
    finally:os.umask(old)
    receipt['_calls']=record.calls;return receipt
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_primitives(calls):
    """What every source's read path must hand to the kernel, whatever the operation."""
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens),'every open is O_NOFOLLOW'
    assert all(not entry['flags']&READ_ONLY_OPEN for entry in opens),'a read open carries no write, create or truncate flag'
    assert [entry['path'] for entry in opens if not entry['by_dir_fd']]==['/']*len([entry for entry in opens if not entry['by_dir_fd']]),'only "/" is opened by absolute path'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat']
    assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats),'every stat is an lstat relative to a held descriptor'
    assert all(entry['path']!='?' for entry in calls if entry['call'] in ('fstat','fsync')),'fstat and fsync act on a descriptor this run opened'
    assert all(entry['by_fd'] for entry in calls if entry['call']=='scandir'),'directories are listed through a held descriptor'


# ---------------------------------------------------------------- the runner
@pytest.mark.parametrize('op',['provision','readback','precheck'])
def test_native_runner_fixed_environment_timeouts_and_expiry(op,tmp_path):
    m=f.load(op).m;native=m.Native();gate=lambda:30.0
    assert native.run(['/bin/echo','hello'],gate,5)==(0,b'hello\n') and native.run(['/bin/echo','hello'],gate,5,False)==(0,b'')
    assert native.run(['/usr/bin/false'],gate,5)[0]==1
    code,out=native.run(['/usr/bin/env'],gate,5);assert code==0 and sorted(out.decode().split())==['LANG=C','LC_ALL=C','PATH=/usr/bin:/bin']
    code,out=native.run(['/usr/bin/env'],gate,5,True,'/etc/c3po-bar/docker-cli')
    assert sorted(out.decode().split())==['DOCKER_CONFIG=/etc/c3po-bar/docker-cli','LANG=C','LC_ALL=C','PATH=/usr/bin:/bin']
    for capture in (True,False):
        with pytest.raises(m.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],gate,0.3,capture)
    with pytest.raises(FileNotFoundError):native.run(['/nonexistent/binary'],gate,5)
    def expired():raise m.Refused('GO_EXPIRED')
    with pytest.raises(m.Refused,match='GO_EXPIRED'):native.run(['/bin/echo','x'],expired,5)
    with pytest.raises(m.Refused,match='COMMAND_OUTPUT_LIMIT'):native.run(['/usr/bin/yes'],gate,5)
    assert native.identity()==(os.geteuid(),os.getegid())


@pytest.mark.parametrize('op',f.OPS)
def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(op,monkeypatch):
    m=f.load(op).m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()


# ---------------------------------------------------------------- provision, real mkdir by dir_fd
@pytest.mark.parametrize('placement',['A','B'])
def test_native_provision_creates_real_directories_0700_exclusively_and_only_by_mkdir(tree,tmp_path,placement):
    EXPECTED=expected(placement)
    before=snapshot(tree);receipt,events,calls=child('provision',tree,provision_fields(tree,placement=placement),tmp_path)
    assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE',receipt.get('code')
    journal=receipt['effects']['journal'];assert (journal['placement'],journal['path'],journal['data_volume_touched_for_the_journal'])==(placement,'/'+JOURNAL[placement],placement=='B')
    if placement=='A':
        # the data volume is not touched at all: not walked, not opened, nothing created in it
        assert 'DATA_VOLUME' not in receipt['chains'] and not [entry for entry in calls if entry.get('path','').startswith('/mnt')]
        assert os.listdir(tree/'mnt/day-d-data')==[] and before['mnt/day-d-data']==snapshot(tree)['mnt/day-d-data']
    # the arguments the kernel received from the shipped Native lines
    assert_read_primitives(calls)
    made=[entry for entry in calls if entry['call']=='mkdir']
    assert [entry['path'] for entry in made]==['/'+path for path in EXPECTED] and all(entry['mode']==0o700 and entry['by_dir_fd'] for entry in made)
    synced=[entry['path'] for entry in calls if entry['call']=='fsync']
    assert synced==[path for created in EXPECTED for path in ('/'+created,os.path.dirname('/'+created))],'fsync of each new directory, then of its parent'
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077] and not [entry for entry in calls if entry['call'] in ('link','unlink','readlink')]
    created=sorted(set(snapshot(tree))-set(before));assert created==sorted(EXPECTED)
    for path in EXPECTED:
        info=os.lstat(tree/path);assert stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode)==0o700 and os.listdir(tree/path)==[name for name in os.listdir(tree/path)]
    assert all(before[name]==value for name,value in snapshot(tree).items() if name in before and name not in ('etc','var/lib','mnt/day-d-data','srv')),'nothing that existed changed'
    assert [event[0] for event in events if event[0]!='open']==['os.mkdir']*15 and [os.path.basename(event[1]) for event in events if event[0]=='os.mkdir']==[os.path.basename(path) for path in EXPECTED]
    assert not [event for event in events if event[0]=='open-for-writing'],'no file is ever opened for writing'
    ledger={row['key']:row for row in receipt['ledger']};info=os.lstat(tree/'etc/c3po-bar')
    assert (ledger['SUP_CONFIG']['observed']['device'],ledger['SUP_CONFIG']['observed']['inode'])==(info.st_dev,info.st_ino)
    # a second run under a new GO labels what exists and creates nothing
    now=snapshot(tree);again=run('provision',tree,provision_fields(tree,placement=placement))
    assert (again['status'],again['code'])==('REFUSED','ALL_DESTINATIONS_PRESENT') and snapshot(tree)==now
    assert_read_primitives(again['_calls'])
    assert not [entry for entry in again['_calls'] if entry['call'] in ('mkdir','fsync','link','unlink')]

@pytest.mark.parametrize('kind',['file','dir','dangling_symlink','symlink_to_dir'])
def test_native_provision_refuses_any_pre_existing_destination_and_leaves_it_intact(tree,kind):
    target=tree/'var/lib/c3po-bar'
    if kind=='file':target.write_bytes(b'foreign')
    elif kind=='dir':target.mkdir(mode=0o755)
    elif kind=='dangling_symlink':os.symlink('/nonexistent-target',target)
    else:os.symlink(str(tree/'srv'),target)
    before=snapshot(tree);receipt=run('provision',tree,provision_fields(tree))
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT_UNEXPECTED') and snapshot(tree)==before
    row={item['key']:item for item in receipt['precheck']}['SUP_STATE_PARENT']
    assert row['type']==('file' if kind=='file' else 'dir' if kind=='dir' else 'symlink') and not (tree/'srv/supervisor').exists()

def test_native_chain_walk_never_follows_a_real_symbolic_link(tree):
    fields=provision_fields(tree);os.rename(tree/'var/lib',tree/'var/lib.real');os.symlink(str(tree/'var/lib.real'),tree/'var/lib')
    before=snapshot(tree);receipt=run('provision',tree,fields)
    assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_SYMLINK_COMPONENT') and snapshot(tree)==before

def test_native_mkdir_is_exclusive_against_an_object_that_appears_after_the_precheck(tree):
    k=f.load('provision');planted=[]
    def racing(record):
        class Racing(k.m.Native):
            def mkdir(self,name,mode,dir_fd):
                if name=='c3po-reader' and not planted:
                    fd=record.real['open'](name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644,dir_fd=dir_fd);os.write(fd,b'foreign bytes');record.real['close'](fd);planted.append(name)
                return k.m.Native.mkdir(self,name,mode,dir_fd)
        return Racing()
    receipt=run('provision',tree,provision_fields(tree),host=racing)
    row={item['key']:item for item in receipt['ledger']}['RDR_CONFIG']
    assert (row['state'],row['code'],row['errno'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST)
    assert (tree/'etc/c3po-reader').read_bytes()==b'foreign bytes' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert sorted(path for path in EXPECTED if (tree/path).is_dir())==sorted(EXPECTED[:6])

@pytest.mark.skipif(os.geteuid()==0,reason='root is not stopped by directory permissions')
def test_native_permission_error_has_its_own_code_and_is_a_refusal_when_nothing_was_created(tree):
    fields=provision_fields(tree,['READER']);os.chmod(tree/'etc',0o555);fields['chains']['ETC'][-1]['mode']=0o555
    try:receipt=run('provision',tree,fields)
    finally:os.chmod(tree/'etc',0o755)
    assert (receipt['status'],receipt['code'],receipt['ledger'][0]['errno'])==('REFUSED','FILESYSTEM_ACCESS_DENIED',errno.EACCES)


# ---------------------------------------------------------------- install, real exclusive create, link and removal
def test_native_install_writes_real_files_through_a_temporary_and_a_link_and_starts_no_process(tree,tmp_path):
    before=snapshot(tree);receipt,events,calls=child('install_units',tree,install_fields(tree),tmp_path)
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',receipt.get('code')
    # the arguments the kernel received from the shipped Native lines
    assert_read_primitives(calls);names=['c3po-massive.service','c3po-massive.timer'];temps=[row['temporary_name'] for row in receipt['ledger']]
    creates=[entry for entry in calls if entry['call']=='open' and entry['flags']&os.O_CREAT]
    assert [entry['path'] for entry in creates]==['/etc/systemd/system/'+name for name in temps]
    assert all(entry['flags']&os.O_EXCL and entry['flags']&os.O_NOFOLLOW and entry['flags']&os.O_WRONLY and not entry['flags']&os.O_TRUNC
               and entry['mode']==0o644 and entry['by_dir_fd'] for entry in creates)
    links=[entry for entry in calls if entry['call']=='link']
    assert [(entry['source'],entry['path']) for entry in links]==[('/etc/systemd/system/'+temp,'/etc/systemd/system/'+name) for temp,name in zip(temps,names)]
    assert all(entry['follow_symlinks'] is False and entry['by_dir_fd'] and entry['same_directory'] for entry in links),'link never follows a symbolic link'
    assert [entry['path'] for entry in calls if entry['call']=='unlink']==['/etc/systemd/system/'+temp for temp in temps]
    assert all(entry['by_dir_fd'] for entry in calls if entry['call']=='unlink')
    order=[(entry['call'],entry['path']) for entry in calls if entry['call'] in ('fsync','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert order==[step for temp,name in zip(temps,names) for step in (('open','/etc/systemd/system/'+temp),('fsync','/etc/systemd/system/'+temp),
        ('link','/etc/systemd/system/'+name),('fsync','/etc/systemd/system'),('unlink','/etc/systemd/system/'+temp),('fsync','/etc/systemd/system'))]
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o022] and not [entry for entry in calls if entry['call']=='mkdir']
    units=tree/'etc/systemd/system';assert sorted(os.listdir(units))==['c3po-massive.service','c3po-massive.timer']
    rendered=f.reference_render(values_of('A'))
    for name,content in (('c3po-massive.service',rendered),('c3po-massive.timer',f.TIMER)):
        info=os.lstat(units/name);assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o644 and info.st_nlink==1 and (units/name).read_bytes()==content
    kinds=[event[0] for event in events if event[0]!='open']
    assert kinds==['open-for-writing','os.link','os.remove']*2,'exactly: exclusive temporary, link, removal of that temporary; per unit'
    writes=[event for event in events if event[0]=='open-for-writing']
    assert all(event[1].startswith('.hostops-') and event[1].endswith('.partial') and event[2]&os.O_EXCL and event[2]&os.O_NOFOLLOW and event[2]&os.O_CREAT for event in writes)
    assert [event[1] for event in events if event[0]=='os.remove']==[event[1] for event in writes]
    assert not [event for event in events if event[0] in ('subprocess.Popen','os.system','os.exec','os.fork','os.posix_spawn','os.spawn','os.chmod','os.chown','os.rename')]
    again=run('install_units',tree,install_fields(tree),now=f.NOW+timedelta(seconds=1));assert (again['status'],again['code'])==('REFUSED','ALL_UNITS_PRESENT')

def test_native_exclusive_create_and_link_never_follow_or_replace(tree):
    k=f.load('install_units');units=tree/'etc/systemd/system'
    def symlinked(record):
        class Symlinked(k.m.Native):
            def create(self,name,flags,mode,dir_fd):
                os.symlink(str(tree/'srv/target'),name,dir_fd=dir_fd);return k.m.Native.create(self,name,flags,mode,dir_fd)
        return Symlinked()
    receipt=run('install_units',tree,install_fields(tree),host=symlinked)
    assert (receipt['status'],receipt['code'])==('REFUSED','TEMPORARY_NAME_OCCUPIED') and not (tree/'srv/target').exists(),'O_EXCL|O_NOFOLLOW: the link is not followed'
    leftover=[name for name in os.listdir(units)];assert len(leftover)==1 and os.path.islink(units/leftover[0]);os.unlink(units/leftover[0])
    def racing(record):
        class Racing(k.m.Native):
            def link(self,source,target,dir_fd):
                if target=='c3po-massive.service':
                    fd=record.real['open'](target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=dir_fd);os.write(fd,b'foreign bytes');record.real['close'](fd)
                return k.m.Native.link(self,source,target,dir_fd)
        return Racing()
    receipt=run('install_units',tree,install_fields(tree),host=racing)
    row=receipt['ledger'][0];assert (row['state'],row['code'],row['errno'],row['temporary_removed'])==('NOT_CREATED','DESTINATION_APPEARED_AFTER_PRECHECK',errno.EEXIST,True)
    assert (units/'c3po-massive.service').read_bytes()==b'foreign bytes' and os.listdir(units)==['c3po-massive.service']
    os.unlink(units/'c3po-massive.service');os.symlink('/nonexistent-target',units/'c3po-massive.timer');before=snapshot(tree)
    receipt=run('install_units',tree,install_fields(tree))
    assert (receipt['status'],receipt['code'])==('REFUSED','UNIT_NAME_OCCUPIED') and snapshot(tree)==before


def test_native_conflict_scan_reads_real_link_text_by_descriptor_and_finds_alias_and_own_dependency_directory(tree):
    units=tree/'etc/systemd/system'
    os.symlink('c3po-massive.service',units/'backup.service')                     # dangling until the unit exists: an alias afterwards
    os.symlink('/usr/lib/systemd/system/docker.service',units/'unrelated.service')
    (tree/'usr/lib/systemd/system/c3po-massive.timer.wants').mkdir();before=snapshot(tree)
    receipt=run('install_units',tree,install_fields(tree));calls=receipt['_calls']
    assert (receipt['status'],receipt['code'])==('REFUSED','OWN_DEPENDENCY_DIRECTORY_PRESENT') and snapshot(tree)==before
    assert receipt['precheck']['conflicts']['finding_codes']==['ALIAS_LINK_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT']
    assert {'code':'ALIAS_LINK_PRESENT','directory':'/etc/systemd/system','name':'backup.service','within':'c3po-massive.service'} in receipt['precheck']['conflicts']['findings']
    links=[entry for entry in calls if entry['call']=='readlink']
    assert sorted(entry['path'] for entry in links)==['/etc/systemd/system/backup.service','/etc/systemd/system/unrelated.service'] and all(entry['by_dir_fd'] for entry in links)
    assert_read_primitives(calls);assert not [entry for entry in calls if entry['call'] in ('mkdir','fsync','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    (tree/'usr/lib/systemd/system/c3po-massive.timer.wants').rmdir();receipt=run('install_units',tree,install_fields(tree),now=f.NOW+timedelta(seconds=1))
    assert (receipt['status'],receipt['code'])==('REFUSED','ALIAS_LINK_PRESENT')
    os.unlink(units/'backup.service');receipt=run('install_units',tree,install_fields(tree),now=f.NOW+timedelta(seconds=2))
    assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'

def test_native_temporary_swapped_for_a_link_right_before_link_is_never_given_the_unit_name(tree):
    """The run looks at the temporary's name again before link(); os.link itself is called without following."""
    k=f.load('install_units');units=tree/'etc/systemd/system';(tree/'srv/foreign.service').write_bytes(b'[Service]\nExecStart=/bin/false\n')
    swapped=[]
    def racing(record):
        class Racing(k.m.Native):
            def lstat(self,name,dir_fd):
                if name.startswith('.hostops-') and not swapped:              # the first look at the temporary's name is the one before link()
                    swapped.append(name);record.real['unlink'](str(units/name));os.symlink(str(tree/'srv/foreign.service'),str(units/name))
                return k.m.Native.lstat(self,name,dir_fd)
        return Racing()
    receipt=run('install_units',tree,install_fields(tree),host=racing);row=receipt['ledger'][0]
    assert (row['state'],row['code'],receipt['status'])==('TEMPORARY_ONLY','TEMPORARY_REPLACED','PARTIAL_METADATA_REQUIRES_REVIEW')
    assert not (units/'c3po-massive.service').exists() and not os.path.lexists(units/'c3po-massive.service')
    assert not [entry for entry in receipt['_calls'] if entry['call'] in ('link','unlink')],'no name is given to the foreign object and it is not removed'
    assert swapped==[row['temporary_name']] and os.path.islink(units/row['temporary_name'])


# ---------------------------------------------------------------- the read-only operations on the real tree
def test_native_read_only_operations_change_nothing_and_never_open_the_token(tree,tmp_path):
    assert run('provision',tree,provision_fields(tree))['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE'
    install=run('install_units',tree,install_fields(tree));assert install['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
    token=tree/'etc/c3po-bar/token';fd=os.open(str(token),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,b'never-emit-token-canary\n');os.close(fd)
    values=values_of('A');rendered=f.reference_render(values);units={row['key']:row for row in install['ledger']}
    import base64
    def identity(path):
        info=os.lstat(tree/path);return {'device':info.st_dev,'inode':info.st_ino}
    fields={'mode':'GATE','install':{'receipt_sha256':install['metadata_sha256'],'outcome':install['outcome']},'provision':{'receipt_sha256':'b'*64},
            'evidence_boot_id_sha256':BOOT_SHA,'unit_directory':rows(tree,'/etc/systemd/system'),
            'service':{'template_b64':base64.b64encode(f.SERVICE).decode(),'rendered_sha256':f.sha(rendered),'rendered_bytes':len(rendered),
                       'device':units['SUPERVISOR_SERVICE']['device'],'inode':units['SUPERVISOR_SERVICE']['inode']},
            'timer':{'template_b64':base64.b64encode(f.TIMER).decode(),'rendered_sha256':f.sha(f.TIMER),'rendered_bytes':len(f.TIMER),
                     'device':units['SUPERVISOR_TIMER']['device'],'inode':units['SUPERVISOR_TIMER']['inode']},
            'substitutions':values,'network_allowlist':['bridge'],'journal_placement':'A','journal_mount_point':'/','deploy_tree_path':f.DEPLOY_TREE,'data_volume':{'path':VOLUME,'rows':None},
            'layout':{'SUP_CONFIG':identity('etc/c3po-bar'),'SUP_MANIFESTS':identity('etc/c3po-bar/manifests'),'SUP_DOCKER_CLI':identity('etc/c3po-bar/docker-cli'),
                      'SUP_STATE_PARENT':identity('var/lib/c3po-bar'),'SUP_STATE':identity('var/lib/c3po-bar/supervisor'),'SUP_JOURNAL':identity(JOURNAL['A'])},
            'retention_reference':'c3po/backend:'+f.TAG,'image_revision':'69c8e632802a06f81c32edc825462a6d2efe6485',
            'free_space_floor_bytes':f.floor_bytes(1),'sessions_retained':1,'other_writers_allowance_bytes':0,
            'catalog':{'expected':'NOT_YET','receipt_sha256':None,'device':None,'inode':None}}
    before=snapshot(tree);token_before=os.lstat(token);receipt,events,calls=child('readback',tree,fields,tmp_path)
    assert_read_primitives(calls)
    assert not [entry for entry in calls if entry['call'] in ('mkdir','fsync','link','unlink','umask') or (entry['call']=='open' and entry['flags']&READ_ONLY_OPEN)]
    assert [entry for entry in calls if entry['call']=='stat' and entry['path']=='/etc/c3po-bar/token'] and not [entry for entry in calls if entry['call']=='open' and 'token' in entry['path']]
    assert snapshot(tree)==before and os.lstat(token).st_atime_ns==token_before.st_atime_ns
    assert not [event for event in events if event[0]!='open'],'no creating, changing, removing or process event at all'
    assert not [event for event in events if event[0]=='open' and 'token' in event[1]],'the token is never opened'
    items=receipt['items']
    for name in ('units','values','layout','token','catalog','conflicts','boot'):assert items[name]['status']=='COMPLETE',(name,items[name])
    assert items['values']['extracted']==values and items['token']['size_within_1_4096'] is True and 'canary' not in json.dumps(receipt)
    filesystem=items['layout']['journal_filesystem'];assert (filesystem['mount_point_by_device_change'],filesystem['journal_root_is_a_mount_point'],filesystem['device'])==('/',False,os.lstat(tree).st_dev)
    assert items['layout']['data_volume']['read'] is False and not [entry for entry in calls if entry.get('path','').startswith('/mnt')],'placement A: the data volume is not read'
    assert items['units']['findings']==[] and items['layout']['findings']==[] and items['token']['findings']==[] and items['catalog']['findings']==[]
    # no docker or systemctl exists in the temporary tree: those items are unavailable with a code, never guessed
    assert items['image']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE' and items['systemd_version']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE'
    assert receipt['outcome']=='PARTIAL_OBSERVED' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    fields={'groups':GROUPS,'journal_placement':'A','data_volume_path':VOLUME,'journal_leaf':f.A_LEAF,'existing_journal_leaves':[],'capacity':dict(CAPACITY),
            'unit_names':['c3po-massive.service','c3po-massive.timer'],'image_reference':'c3po/backend:production'}
    before=snapshot(tree);receipt,events,calls=child('precheck',tree,fields,tmp_path)
    assert_read_primitives(calls)
    assert not [entry for entry in calls if entry['call'] in ('mkdir','fsync','link','unlink','umask') or (entry['call']=='open' and entry['flags']&READ_ONLY_OPEN)]
    assert snapshot(tree)==before and not [event for event in events if event[0]!='open'] and not [event for event in events if 'token' in event[1]]
    items=receipt['items'];assert items['chains']['ETC']['rows']==rows(tree,'/etc') and items['chains']['CAPACITY_PARENT']['rows']==rows(tree,'/srv')
    assert sorted(items['chains'])==['CAPACITY_PARENT','ETC','UNIT_DIRECTORY','VAR_LIB'],'under placement A the data volume is not read either'
    assert items['destinations']['SUP_CONFIG']['entries']==3 and items['destinations']['SUP_CONFIG']['other_entries']==1
    assert items['secret_bearing_names']['/etc/c3po-bar/token']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}
    assert items['unit_files']['c3po-massive.service']['links']==1 and 'size' not in items['unit_files']['c3po-massive.service']
    assert items['core_pattern']=={'status':'COMPLETE','is_pipe':False}
