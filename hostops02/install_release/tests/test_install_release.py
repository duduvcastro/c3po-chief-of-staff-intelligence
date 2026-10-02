"""K10, install_release, end to end on the emulated host: the literal effects the signers see, every refusal with
its code and the proof that nothing changed, every hostile state of the filesystem, every point at which the process
can die and what a later read finds there, expiry at every gate, and what the receipt says. Synthetic and in memory:
no SSH, no host, no credential, no docker binary, no GO."""
import copy
from datetime import datetime,timedelta,timezone
import errno
import json
import os
import stat

import pytest

import family as f
import hostemu
import k10

BASE,TARGET,DATA,PIN,NAME,LEAF=k10.BASE,k10.TARGET,k10.DATA,k10.PIN,k10.NAME,k10.LEAF
def fresh(**options):
    docs,host=k10.case(**options);return docs.k.m,docs,host
def utc(*parts):return datetime(*parts,tzinfo=timezone.utc)
def refused_untouched(receipt,host,before,code,phase='PRECHECK'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,phase),receipt['code']
    assert k10.state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run']==0 and receipt['installed'] is None and host.fds=={} and host.commands==[] and f.sealed(receipt)


# ---------------------------------------------------------------- the complete run
def test_complete_run_and_the_literal_effects_the_signers_see():
    m,docs,host=fresh();plan=docs.plan;before=k10.state_of(host)
    assert docs.go['effects']==docs.authority['effects']=={'operation':'GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01',
        'parent':{'path':DATA,'row':plan['parent'][-1],'chain_sha256':f.sha(f.canonical(plan['parent'])),'mount_point_by_device_change':DATA},
        'open_root':DATA,
        'directory':{'path':'/mnt/day-d-data/r2d2-v2-release-20261005','mode_octal':'0700','uid':0,'gid':0,'expect':'ABSENT'},
        'file':{'path':'/mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json','sha256':f.sha(k10.RELEASE),'bytes':len(k10.RELEASE),
                'mode_octal':'0600','uid':0,'gid':0,'links':1},
        'release':{'schema':'R2D2_V2_RELEASE_V3','mode':'CERTIFIED','epoch':'R2D2-V2-SHADOW-2026-10-05','first_session':'2026-10-05',
                   'code_revision':'0123456789abcdef0123456789abcdef01234567',
                   'implementation_package_sha':'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84','approved_at':'2026-10-03T19:40:00+00:00'},
        'release_file_in_the_worker':'/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json',
        'maintenance_pin':{'path':'/mnt/day-d-data/.r2d2-v2-pinned','required':'PRESENT_REGULAR_ROOT_OWNED'},
        'new_york_day_utc':['2026-10-05T04:00:00+00:00','2026-10-06T04:00:00+00:00'],
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'activation':False,'container_recreated':False,'process_started':False}
    assert docs.go['success_criterion']=='RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED' and f.sha(k10.RELEASE)==k10.RECORD['release_sha256']
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['readback'])==(
        m.COMPLETE_STATUS,'RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED',None,'EFFECTS','COMPLETE')
    assert receipt['mutating_calls']=={'issued':5,'succeeded':5,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==2
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
    # what is on the host now: one directory and one file, and nothing else is different
    directory=host.tree.get(BASE);assert (directory.kind,directory.uid,directory.gid,directory.mode,directory.dev)==('dir',0,0,0o700,hostemu.DATA_DEVICE)
    assert sorted(directory.children)==[NAME];installed=directory.children[NAME]
    assert (installed.kind,installed.uid,installed.gid,installed.mode,installed.nlink,installed.dev)==('file',0,0,0o600,1,hostemu.DATA_DEVICE)
    assert bytes(installed.content)==k10.RELEASE and installed.synced and directory.synced and host.tree.get(DATA).synced
    host.tree.remove(BASE);assert k10.state_of(host)==before,'nothing else changed'
    # the order of everything that changed the host, and of the fsyncs
    go16=docs.go16();temporary=BASE+'/.hostops-%s-0.partial'%go16
    assert [entry[:2] for entry in host.mutating()]==[('mkdir',BASE),('create',temporary),('write',temporary),('link',temporary),('unlink',temporary)]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[BASE,DATA,temporary,BASE,BASE]
    mkdir=[entry for entry in host.log if entry[0]=='mkdir'][0];create=[entry for entry in host.log if entry[0]=='create'][0]
    assert mkdir[2]==0o700 and create[3]==0o600 and create[2]&(os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW)==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
    assert [entry for entry in host.log if entry[0]=='link'][0][1:]==(temporary,TARGET) and [entry for entry in host.log if entry[0]=='write'][0][2]==len(k10.RELEASE)
    assert host.mask==0o077 and [entry for entry in host.log if entry[0]=='umask']==[('umask',0o077)]
    assert host.commands==[] and host.fds=={} and not [entry for entry in host.log if entry[0] in ('run','flock','pause','readlink')],'no process, no lock, no wait'
    # the receipt: what the gates read
    assert receipt['installed']=={'path':TARGET,'release_file_in_the_worker':'/app/day-d-data/'+LEAF+'/'+NAME,'sha256':f.sha(k10.RELEASE),'bytes':len(k10.RELEASE),
        'mode_octal':'0600','uid':0,'gid':0,'links':1,'directory_mode_octal':'0700','directory_entries':1,'bytes_equal_the_signed_bytes':True,
        'epoch':'R2D2-V2-SHADOW-2026-10-05','verified_with_the_application':False}
    row=receipt['ledger'][0];assert (row['state'],row['sha256_signed'],row['sha256_observed'],row['bytes'],row['temporary_removed'])==('INSTALLED_DURABLE',f.sha(k10.RELEASE),f.sha(k10.RELEASE),len(k10.RELEASE),True)
    assert (row['fsync_file'],row['fsync_directory_after_link'],row['fsync_directory_after_removal'],row['temporary_name'])==(True,True,True,'.hostops-%s-0.partial'%go16)
    assert (row['device'],row['inode'])==(installed.dev,installed.ino) and receipt['directories'][0]['state']=='CREATED_DURABLE'
    assert receipt['directories'][0]['observed']=={'type':'dir','uid':0,'gid':0,'mode_octal':'0700','device':directory.dev,'inode':directory.ino,'entries':0}
    assert receipt['parent']==plan['parent'] and receipt['precheck']=={'maintenance_pin':{'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1},
        'destination':{'exists':False,'found':None},'free_bytes':13200816*4096,'seconds_left_before_first_effect':60}
    assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects']) and receipt['observed_at']==docs.now.isoformat()

def test_receipt_names_the_bytes_by_hash_and_never_carries_them():
    m,docs,host=fresh();receipt=docs.run(host);line=f.line(receipt)
    assert k10.b64(k10.RELEASE).encode() not in line and b'SYNTHETIC_FIXTURE' not in line and len(line)<6000 and receipt['size_reductions']==[] and f.sealed(receipt)
    assert receipt['secret_bytes_in_receipt'] is False and hostemu.SECRET.encode() not in line

def test_source_carries_no_runner_no_process_and_no_lock():
    m=k10.K().m;report=k10.K().report
    assert report['parts']==['core','parents','files'] and not hasattr(m,'COMMANDS') and not hasattr(m,'NativeRunner') and not hasattr(m,'subprocess') and not hasattr(m,'fcntl')
    assert [base.__name__ for base in m.Native.__mro__[1:-1]]==['NativeRead','NativeFiles'] and not hasattr(m.Native,'run') and not hasattr(m.Native,'flock')
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS,m.DATES,m.EVIDENCE_OPERATIONS)==(True,False,'WRITE_FIRST_SESSION',('2026-10-05',),('GO_READONLY_HOSTOPS_PRECHECK_01',))
    assert m.DATES==(m.FIRST_SESSION,) and m.RELEASE_EPOCH=='R2D2-V2-SHADOW-'+m.FIRST_SESSION and m.EVIDENCE_REQUIRED is True and m.MAX_GATE_SPAN_SECONDS==900
    assert m.SCOPE['processes_started']==0 and m.SCOPE['paths']=={'data_volume':DATA,'release_directory':BASE,'release_file':TARGET,
        'release_file_in_the_worker':'/app/day-d-data/'+LEAF+'/'+NAME,'maintenance_pin':PIN}
    assert m.SCOPE['limits']=={'max_seconds':60,'max_gate_span_seconds':900,'receipt_bytes':60000,'release_bytes':32768,'free_bytes_floor':1048576,'write_allowance_seconds':15}
    assert (m.SCOPE['epoch'],m.SCOPE['first_session'],m.SCOPE['release'])==('R2D2-V2-SHADOW-2026-10-05','2026-10-05',{'schema':'R2D2_V2_RELEASE_V3','mode':'CERTIFIED','max_bytes':32768})

def test_no_command_answer_can_reach_this_run_because_it_starts_none():
    """A docker binary that is absent, hangs, or lies cannot change the result: the engine is never asked."""
    for prepare in (lambda host:host.tree.remove('/usr/bin/docker'),lambda host:host.hang.add('docker'),lambda host:host.absent.add('docker'),
                    lambda host:host.hang_after.add('systemctl'),lambda host:setattr(host.docker,'containers',[]),lambda host:setattr(host.docker,'images',[])):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and host.commands==[] and 'commands_started' not in receipt

def test_scope_and_statement_are_literally_what_the_signers_sign():
    m=k10.K().m
    assert m.SCOPE_STATEMENT==('Creates the private directory /mnt/day-d-data/r2d2-v2-release-20261005 (root:root 0700) in the pinned root of the data volume and, in it, '
        'the file release.CERTIFIED.json (root:root 0600) holding exactly the release bytes whose SHA-256 and size the request signs, for epoch '
        'R2D2-V2-SHADOW-2026-10-05 on its first session day only. Exclusive creation, fsync and a byte readback through a descriptor inside the run. '
        'Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its identity is '
        'proved. No process is started, no container is created or recreated, nothing is activated, and the release is not verified with '
        'the application here.')
    assert m.SCOPE=={'operation':'GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01','dates':['2026-10-05'],'statement':m.SCOPE_STATEMENT,'core_sha256':m.CORE_SHA256,
        'writes_allowed':True,'activation_allowed':False,'epoch':'R2D2-V2-SHADOW-2026-10-05','first_session':'2026-10-05',
        'new_york_day_utc':['2026-10-05T04:00:00+00:00','2026-10-06T04:00:00+00:00'],
        'release':{'schema':'R2D2_V2_RELEASE_V3','mode':'CERTIFIED','max_bytes':32768},
        'paths':{'data_volume':'/mnt/day-d-data','release_directory':'/mnt/day-d-data/r2d2-v2-release-20261005',
                 'release_file':'/mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json',
                 'release_file_in_the_worker':'/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json','maintenance_pin':'/mnt/day-d-data/.r2d2-v2-pinned'},
        'files':m.FILES_SCOPE,'evidence_operations_required':['GO_READONLY_HOSTOPS_PRECHECK_01'],
        'file_contents_read':['/proc/sys/kernel/random/boot_id','the release file this run delivered (readback inside the run)'],'processes_started':0,
        'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker','systemctl',
                 'a shell','a network connection','activation','a recreate of any container','a second attempt'],
        'limits':{'max_seconds':60,'max_gate_span_seconds':900,'receipt_bytes':60000,'release_bytes':32768,'free_bytes_floor':1048576,'write_allowance_seconds':15}}
    assert (m.OPERATION,m.PHASE,m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==(
        'GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01','WRITE_INSTALL_RELEASE_NO_ACTIVATION','RELEASE_INSTALLED_BYTES_READ_BACK_NOT_ACTIVATED','PARTIAL_REQUIRES_RECONCILIATION',
        'REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_REQUIRES_RECONCILIATION')
    assert m.PLAN_KEYS==frozenset(('parent','release','evidence_boot_id_sha256')) and m.RELEASE_KEYS==frozenset(('path','content_b64','sha256','bytes'))

def test_receipt_that_would_not_fit_is_reduced_by_flagged_steps_and_is_then_never_complete():
    m,docs,host=fresh();receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    def again(**padding):
        body={key:value for key,value in receipt.items() if key not in ('metadata_sha256','size_reductions')};body.update(padding);return m.seal(body)
    reduced=again(precheck={'pad':'x'*70000})
    assert (reduced['status'],reduced['outcome'],reduced['size_reductions'],reduced['precheck'])==(m.PARTIAL_STATUS,'RECEIPT_REDUCED_STATE_REQUIRES_READBACK',['PRECHECK_DROPPED'],{'reduced_for_size':True})
    assert reduced['parent']==receipt['parent'] and reduced['mutating_calls']==receipt['mutating_calls'] and f.sealed(reduced)
    reduced=again(precheck={'pad':'x'*70000},parent=[{'pad':'x'*30000},{'pad':'y'*40000}])
    assert (reduced['size_reductions'],reduced['parent'],reduced['precheck'])==(['PRECHECK_DROPPED','PARENT_REDUCED_TO_COUNT'],2,{'reduced_for_size':True}) and f.sealed(reduced)
    assert reduced['ledger']==receipt['ledger'] and reduced['objects_left_by_this_run']==2

def test_new_york_day_constants_are_midnight_to_midnight_in_new_york():
    zoneinfo=pytest.importorskip('zoneinfo')
    try:zone=zoneinfo.ZoneInfo('America/New_York')
    except Exception:pytest.skip('no time zone database on this machine')
    m=k10.K().m;start,end=[m.instant(value) for value in m.NEW_YORK_DAY_UTC]
    assert start==datetime(2026,10,5,0,0,tzinfo=zone) and end==datetime(2026,10,6,0,0,tzinfo=zone)
    assert start.astimezone(zone).date().isoformat()==m.FIRST_SESSION==(end-timedelta(microseconds=1)).astimezone(zone).date().isoformat()
    assert (start-timedelta(microseconds=1)).astimezone(zone).date().isoformat()=='2026-10-04' and end.astimezone(zone).date().isoformat()=='2026-10-06'

def test_release_directory_is_not_an_entry_the_security_guard_reads_and_the_file_meets_the_worker_reader():
    """guard: root-level entries named r2d2-v2-release-* with the suffix .json (scripts/c3po_security_guard.py:20).
    worker: regular, no group or other bit, at most 65536 bytes (r2d2_v2_shadow_worker.py:29-42)."""
    m=k10.K().m
    assert m.RELEASE_DIRECTORY_NAME.startswith('r2d2-v2-release-') and os.path.splitext(m.RELEASE_DIRECTORY_NAME)[1]!='.json'
    assert m.RELEASE_DIRECTORY_NAME=='r2d2-v2-release-'+m.FIRST_SESSION.replace('-','') and m.PRIVATE_FILE_MODE&0o077==0 and m.MAX_RELEASE_BYTES<=65536
    assert m.CONTAINER_RELEASE_PATH==m.RELEASE_PATH.replace(m.DATA_VOLUME,'/app/day-d-data',1) and m.MAINTENANCE_PIN==hostemu.PIN


# ---------------------------------------------------------------- everything is looked at before the first creation
def test_every_precheck_refusal_leaves_the_host_exactly_as_it_was():
    def other_boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    def boot_garbage(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'not a boot id\n')
    def parent_inode(host):host.tree.get(DATA).ino+=1
    def parent_mode(host):host.tree.get(DATA).mode=0o775
    def parent_owner(host):host.tree.get(DATA).uid=0
    def parent_group(host):host.tree.get(DATA).gid=0
    def unmounted(host):host.tree.get(DATA).dev=hostemu.ROOT_DEVICE                    # the mount point without its filesystem
    def mnt_inode(host):host.tree.get('/mnt').ino+=1
    def root_mode(host):host.tree.root.mode=0o777
    def volume_is_a_link(host):
        host.tree.remove(DATA);host.tree.add(DATA,kind='symlink',mode=0o777)
    def mnt_is_a_link(host):
        node=host.tree.get('/mnt');node.kind='symlink'
    def volume_is_a_file(host):
        host.tree.remove(DATA);host.tree.add(DATA,kind='file')
    def volume_missing(host):host.tree.remove(DATA)
    def no_pin(host):host.tree.remove(PIN)
    def pin_is_a_link(host):
        host.tree.remove(PIN);host.tree.add(PIN,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    def pin_is_a_directory(host):
        host.tree.remove(PIN);host.tree.add(PIN,kind='dir',mode=0o700,dev=hostemu.DATA_DEVICE)
    def pin_is_a_fifo(host):
        host.tree.remove(PIN);host.tree.add(PIN,kind='fifo',mode=0o600,dev=hostemu.DATA_DEVICE)
    def pin_owner(host):host.tree.get(PIN).uid=1000
    def pin_group(host):host.tree.get(PIN).gid=1000                                    # what group inheritance in this directory would look like
    def present_empty(host):host.tree.add(BASE,mode=0o700,dev=hostemu.DATA_DEVICE)
    def present_foreign(host):
        host.tree.add(BASE,uid=1000,gid=1000,dev=hostemu.DATA_DEVICE);host.tree.add(BASE+'/'+NAME,kind='file',uid=1000,dev=hostemu.DATA_DEVICE,content=b'foreign')
    def present_file(host):host.tree.add(BASE,kind='file',dev=hostemu.DATA_DEVICE,content=k10.RELEASE)
    def present_link(host):host.tree.add(BASE,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)      # dangling or not: a name that exists
    def present_fifo(host):host.tree.add(BASE,kind='fifo',dev=hostemu.DATA_DEVICE)
    def full(host):host.vfs[hostemu.DATA_DEVICE].f_bavail=255                           # 255 * 4096 < 1 MiB
    def statvfs_garbage(host):host.vfs[hostemu.DATA_DEVICE].f_frsize=0
    def no_noatime(host):host.noatime_available=False
    def not_root(host):host.actor=(0,5)
    cases=((other_boot,'EVIDENCE_FROM_EARLIER_BOOT'),(boot_garbage,'BOOT_ID_INVALID'),(parent_inode,'PARENT_IDENTITY_MISMATCH'),(parent_mode,'PARENT_IDENTITY_MISMATCH'),
           (parent_owner,'PARENT_IDENTITY_MISMATCH'),(parent_group,'PARENT_IDENTITY_MISMATCH'),(unmounted,'PARENT_IDENTITY_MISMATCH'),(mnt_inode,'PARENT_IDENTITY_MISMATCH'),
           (root_mode,'PARENT_IDENTITY_MISMATCH'),(volume_is_a_link,'PARENT_SYMLINK_COMPONENT'),(mnt_is_a_link,'PARENT_SYMLINK_COMPONENT'),
           (volume_is_a_file,'PARENT_NOT_DIRECTORY'),(volume_missing,'PARENT_MISSING'),(no_pin,'MAINTENANCE_PIN_ABSENT'),(pin_is_a_link,'MAINTENANCE_PIN_NOT_A_REGULAR_FILE'),
           (pin_is_a_directory,'MAINTENANCE_PIN_NOT_A_REGULAR_FILE'),(pin_is_a_fifo,'MAINTENANCE_PIN_NOT_A_REGULAR_FILE'),(pin_owner,'MAINTENANCE_PIN_NOT_ROOT_OWNED'),
           (pin_group,'MAINTENANCE_PIN_NOT_ROOT_OWNED'),(present_empty,'DESTINATION_PRESENT'),(present_foreign,'DESTINATION_PRESENT'),(present_file,'DESTINATION_PRESENT'),
           (present_link,'DESTINATION_PRESENT'),(present_fifo,'DESTINATION_PRESENT'),(full,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'),(statvfs_garbage,'STATVFS_INVALID'),
           (no_noatime,'NOATIME_UNAVAILABLE'),(not_root,'EXECUTOR_IDENTITY'))
    for prepare,code in cases:
        m,docs,host=fresh();prepare(host);before=k10.state_of(host);receipt=docs.run(host)
        refused_untouched(receipt,host,before,code)
        assert not [entry for entry in host.log if entry[0] in ('mkdir','create','write','link','unlink','fsync')],prepare.__name__
    # the free-space floor to the byte, and what the receipt shows of a destination that exists
    m,docs,host=fresh();host.vfs[hostemu.DATA_DEVICE].f_bavail=256;assert docs.run(host)['status']==m.COMPLETE_STATUS
    m,docs,host=fresh();present_foreign(host);receipt=docs.run(host)
    assert receipt['precheck']['destination']=={'exists':True,'found':{'type':'dir','uid':1000,'gid':1000,'mode_octal':'0755','links':1}}
    m,docs,host=fresh();pin_is_a_link(host);assert docs.run(host)['precheck']['maintenance_pin']['type']=='symlink'

def test_order_of_the_precheck_executor_first_then_the_day_then_the_boot_and_the_pin_before_the_destination():
    m,docs,host=fresh();host.actor=(1000,0);host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');receipt=docs.run(host)
    assert receipt['code']=='EXECUTOR_IDENTITY' and host.log==[],'nothing is looked at, not even the umask is set'
    m,docs,host=fresh();host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');host.tree.get(DATA).ino+=1
    assert docs.run(host)['code']=='BOOT_ID_INVALID'
    m,docs,host=fresh();host.tree.get(DATA).ino+=1;host.tree.remove(PIN);assert docs.run(host)['code']=='PARENT_IDENTITY_MISMATCH'
    m,docs,host=fresh();host.tree.remove(PIN);host.tree.add(BASE,dev=hostemu.DATA_DEVICE);assert docs.run(host)['code']=='MAINTENANCE_PIN_ABSENT'
    m,docs,host=fresh();host.tree.add(BASE,dev=hostemu.DATA_DEVICE);host.vfs[hostemu.DATA_DEVICE].f_bavail=0;assert docs.run(host)['code']=='DESTINATION_PRESENT'
    # the pin and the destination are looked at through the descriptor of the pinned parent, by name, never by a second walk
    m,docs,host=fresh();docs.run(host);names=[entry for entry in host.log if entry[0]=='lstat']
    assert ('lstat',PIN) in names and ('lstat',BASE) in names and names.index(('lstat',PIN))<names.index(('lstat',BASE))<[entry[0] for entry in host.log].index('mkdir')

def test_the_gate_is_asked_before_the_pin_and_before_the_destination_are_looked_at():
    """An expiry that falls between the walk of the parent and the two lstat calls stops the run before them."""
    for target in (PIN,BASE):
        m,docs,host=fresh();before=k10.state_of(host);plan,real=docs.authenticate()
        def gate():
            names=[entry for entry in host.log if entry[0] in ('lstat','fstat')]
            held=names[-2:]==[('fstat',DATA),('fstat',DATA)] if target==PIN else names[-1:]==[('lstat',PIN)]
            if held and not [entry for entry in host.log if entry==('lstat',target)]:raise m.Refused('GO_EXPIRED')
            return real()
        receipt=docs.perform(host,gate=gate);refused_untouched(receipt,host,before,'GO_EXPIRED')
        assert ('lstat',target) not in host.log and (target==PIN or ('lstat',PIN) in host.log)

def test_run_is_refused_outside_the_new_york_day_of_the_first_session_whatever_the_window_says():
    """The window is confined by the date class (one UTC day) and by validate_plan (the New York day). The run looks
    at its own clock as well, before anything on the host is read."""
    for instant,ok in ((utc(2026,10,5,3,59,59,999999),False),(utc(2026,10,5,4,0,0),True),(utc(2026,10,5,8,27),True),(utc(2026,10,6,3,59,59,999999),True),
                       (utc(2026,10,6,4,0,0),False),(utc(2026,10,4,23,0,0),False),(utc(2026,10,12,8,27),False)):
        m,docs,host=fresh();before=k10.state_of(host);receipt=docs.perform(host,clock=lambda:instant)
        if ok:assert receipt['status']==m.COMPLETE_STATUS,instant
        else:
            refused_untouched(receipt,host,before,'NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK')
            assert [entry[0] for entry in host.log]==['umask'],'refused before anything on the host is read'
    m,docs,host=fresh();before=k10.state_of(host)
    calls=[0]
    def naive():
        calls[0]+=1;return docs.now if calls[0]==1 else datetime(2026,10,5,8,27)       # a clock without a zone is not a clock
    receipt=docs.perform(host,clock=naive);assert receipt['code']=='PRECHECK_FAILED' and k10.state_of(host)==before

def test_budget_is_the_last_refusal_before_the_first_creation():
    """Fifteen seconds must be left when the first creation is about to start; one less and the run refuses."""
    for elapsed,ok in ((0.0,True),(45.0,True),(45.5,False),(59.0,False)):
        m,docs,host=fresh();before=k10.state_of(host);mono=[0.0];plan,gate=docs.authenticate(monotonic=lambda:mono[0]);mono[0]=elapsed
        receipt=docs.perform(host,gate=gate,monotonic=lambda:mono[0])
        if ok:assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['seconds_left_before_first_effect']==int(60-elapsed)
        else:
            refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            assert [entry[0] for entry in host.log][-1]=='fstatvfs' and receipt['precheck']['seconds_left_before_first_effect']==int(60-elapsed)
    # the end of the GO window bounds it as the deadline does
    m,docs,host=fresh();before=k10.state_of(host);late=docs.now+timedelta(minutes=4,seconds=50)
    receipt=docs.run(host,clock=lambda:late);refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def test_precheck_failure_of_any_kind_is_a_refusal_with_a_constant_code():
    for name,error,code in (('lstat',OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),('fstatvfs',OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                            ('umask',RuntimeError('injected'),'PRECHECK_FAILED'),('fstatvfs',RuntimeError('injected'),'PRECHECK_FAILED')):
        m,docs,host=fresh();before=k10.state_of(host)
        def hook(host,event,detail,calls,name=name,error=error):
            if event==name and (name!='lstat' or detail[0]==BASE):raise error
        host.hook=hook;receipt=docs.run(host);refused_untouched(receipt,host,before,code);assert 'injected' not in json.dumps(receipt)


# ---------------------------------------------------------------- the plan: refused from its bytes, before any claim
def change(path,value):
    def apply(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return apply
def release(raw):
    def apply(plan):plan['release']=k10.release_member(raw)
    return apply
def without(key):
    def apply(plan):del plan['release'][key]
    return apply
PADDED=k10.altered(authorization_ref='SYNTHETIC_FIXTURE_NOT_AN_AUTHORIZATION'+'x'*40000)
DUPLICATE=k10.RELEASE.rstrip()[:-1]+b',\n "epoch": "R2D2-V2-SHADOW-2026-10-05"\n}\n'
PLAN_CASES=[
    (change(['parent'],None),'CHAIN_ROW_INVALID'),(change(['parent'],[]),'CHAIN_ROW_INVALID'),(change(['parent',2,'path'],'/mnt/other-volume'),'CHAIN_ROW_INVALID'),
    (lambda plan:plan['parent'].pop(),'CHAIN_ROW_INVALID'),(lambda plan:plan['parent'].append(dict(plan['parent'][-1],path=k10.BASE)),'CHAIN_ROW_INVALID'),
    (change(['parent',2,'inode'],0),'CHAIN_ROW_INVALID'),(change(['parent',2,'device'],True),'CHAIN_ROW_INVALID'),(lambda plan:plan['parent'][2].pop('gid'),'CHAIN_ROW_INVALID'),
    (change(['parent',1,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['parent',1,'mode'],0o775),'CHAIN_ROW_UNSAFE'),(change(['parent',0,'mode'],0o757),'CHAIN_ROW_UNSAFE'),
    (change(['parent',2,'mode'],0o777),'CHAIN_ROW_WORLD_WRITABLE'),(change(['parent',2,'mode'],0o2755),'PARENT_SETGID'),
    (lambda plan:plan['parent'][2].update(device=plan['parent'][1]['device']),'DATA_VOLUME_NOT_A_MOUNT_POINT'),
    (change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
    (change(['release'],None),'RELEASE_PLAN_INVALID'),(change(['release','extra'],1),'RELEASE_PLAN_INVALID'),(without('path'),'RELEASE_PLAN_INVALID'),
    (without('bytes'),'RELEASE_PLAN_INVALID'),(change(['release','bytes'],0),'RELEASE_PLAN_INVALID'),(change(['release','bytes'],True),'RELEASE_PLAN_INVALID'),
    (change(['release','sha256'],'0'*64),'RELEASE_PLAN_INVALID'),(change(['release','sha256'],None),'RELEASE_PLAN_INVALID'),(release(PADDED),'RELEASE_PLAN_INVALID'),
    (change(['release','path'],k10.DATA+'/r2d2-v2-release-20261005.json'),'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT'),
    (change(['release','path'],k10.DATA+'/r2d2-v2-release-20260928/release.CERTIFIED.json'),'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT'),
    (change(['release','path'],'/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json'),'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT'),
    (change(['release','path'],None),'RELEASE_PATH_NOT_THE_SIGNED_CONSTANT'),
    (change(['release','sha256'],'3'*64),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),(change(['release','bytes'],len(k10.RELEASE)-1),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['release','content_b64'],'not base64!'),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),(change(['release','content_b64'],None),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['release','content_b64'],k10.b64(k10.RELEASE+b' ')),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['release','content_b64'],k10.b64(k10.RELEASE)[:8]+'\n'+k10.b64(k10.RELEASE)[8:]),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['release','content_b64'],' '+k10.b64(k10.RELEASE)),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),(change(['release','content_b64'],'é'+k10.b64(k10.RELEASE)),'RELEASE_BYTES_NOT_THE_SIGNED_HASH'),
    (release(b'not json at all\n'),'RELEASE_NOT_JSON'),(release(b'[]\n'),'RELEASE_NOT_JSON'),(release(DUPLICATE),'RELEASE_NOT_JSON'),
    (release(k10.RELEASE.replace(b'"CERTIFIED"',b'NaN')),'RELEASE_NOT_JSON'),
    (release(k10.altered(schema='R2D2_V2_RELEASE_V2')),'RELEASE_NOT_A_CERTIFIED_V3_RELEASE'),(release(k10.altered(mode='DIAGNOSTIC')),'RELEASE_NOT_A_CERTIFIED_V3_RELEASE'),
    (release(k10.altered(mode=...)),'RELEASE_NOT_A_CERTIFIED_V3_RELEASE'),
    (release(k10.altered(epoch='R2D2-V2-SHADOW-2026-09-28')),'RELEASE_EPOCH_NOT_THIS_EPOCH'),(release(k10.altered(epoch='R2D2-V2-DIAG-2026-10-05')),'RELEASE_EPOCH_NOT_THIS_EPOCH'),
    (release(k10.altered(epoch='R2D2-V2-SHADOW-2026-10-05 ')),'RELEASE_EPOCH_NOT_THIS_EPOCH'),(release(k10.altered(epoch=...)),'RELEASE_EPOCH_NOT_THIS_EPOCH'),
    (release(k10.altered(first_session='2026-10-06')),'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH'),(release(k10.altered(first_session=...)),'RELEASE_FIRST_SESSION_NOT_THIS_EPOCH'),
    (release(k10.altered(code_revision='development')),'RELEASE_FIELDS_INVALID'),(release(k10.altered(implementation_package_sha=...)),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(implementation_package_sha='0'*64)),'RELEASE_FIELDS_INVALID'),(release(k10.altered(approved_at=1759500000)),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(code_revision='DD4EC4BB8DAB4D8B0372B0F9EABC90BF6443E858')),'RELEASE_FIELDS_INVALID'),(release(k10.altered(code_revision='0123456789abcdef0123456789abcdef012345678')),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(code_revision='0123456789abcdef0123456789abcdef0123456')),'RELEASE_FIELDS_INVALID'),(release(k10.altered(code_revision=...)),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(implementation_package_sha='B5CE527A544CA0EB08F0718D83546D7B46F9E9774BE8E4351AFCE212E72BDB84')),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(approved_at='2026-10-03T19:40:00+00:00'+'0'*16)),'RELEASE_FIELDS_INVALID'),(release(k10.altered(approved_at='yesterday')),'RELEASE_FIELDS_INVALID'),
    (release(k10.altered(approved_at='')),'RELEASE_FIELDS_INVALID'),(release(k10.altered(approved_at=...)),'RELEASE_FIELDS_INVALID'),
]
@pytest.mark.parametrize('index',range(len(PLAN_CASES)))
def test_plan_refusals_are_authentication_refusals_nothing_is_touched_and_no_go_is_claimed(index,tmp_path):
    apply,code=PLAN_CASES[index];m,docs,host=fresh();apply(docs.plan);docs.chain()
    assert f.refusal(docs.authenticate)==code,code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['outcome'])==('REFUSED',code,'AUTHENTICATION','REFUSED_NOTHING_CHANGED')
    assert receipt['mutating_calls']['issued']==0 and f.sealed(receipt)
    # the dispatcher runs the same check locally before any claim: a plan like this cannot spend the single-use GO
    dispatch=f.Dispatch(docs,tmp_path);assert f.refusal(dispatch.prepare)==code and not dispatch.claims()

def test_window_must_lie_on_the_new_york_day_of_the_first_session():
    m,docs,host=fresh(now=utc(2026,10,5,3,58));assert f.refusal(docs.authenticate)=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK','AUTHENTICATION')
    m,docs,host=fresh(now=utc(2026,10,5,3,59,59,999999));assert f.refusal(docs.authenticate)=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'
    m,docs,host=fresh(now=utc(2026,10,5,4,0));assert docs.run(host)['status']==m.COMPLETE_STATUS,'Monday 00:00 in New York, 01:00 BRT'
    m,docs,host=fresh(now=utc(2026,10,5,8,27));assert docs.run(host)['status']==m.COMPLETE_STATUS,'the planned dispatch: 05:27 BRT'
    m,docs,host=fresh(now=utc(2026,10,5,23,54));assert docs.run(host)['status']==m.COMPLETE_STATUS,'the last window of the UTC day'
    # both ends are judged by validate_plan itself (the end cannot be reached through authenticate: the date class refuses first)
    m,docs,host=fresh();plan=copy.deepcopy(docs.plan);m.validate_plan(plan)
    plan['window']={'not_before':'2026-10-06T03:50:00+00:00','expires_at':'2026-10-06T04:00:00+00:00'};m.validate_plan(plan)
    plan['window']['expires_at']='2026-10-06T04:00:00.000001+00:00';assert f.refusal(lambda:m.validate_plan(plan))=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'
    plan['window']={'not_before':'2026-10-05T03:59:59+00:00','expires_at':'2026-10-05T04:05:00+00:00'};assert f.refusal(lambda:m.validate_plan(plan))=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'

def test_validate_plan_judges_the_release_itself_not_only_through_the_effects():
    """authenticate() computes the effects after validate_plan and would refuse a foreign release there too; the plan
    check must not rely on that."""
    m,docs,host=fresh();plan=copy.deepcopy(docs.plan);m.validate_plan(plan)
    plan['release']=k10.release_member(k10.altered(epoch='R2D2-V2-SHADOW-2026-09-28'));assert f.refusal(lambda:m.validate_plan(plan))=='RELEASE_EPOCH_NOT_THIS_EPOCH'
    plan['release']=dict(k10.release_member(),sha256='3'*64);assert f.refusal(lambda:m.validate_plan(plan))=='RELEASE_BYTES_NOT_THE_SIGNED_HASH'

def test_accepted_plans_at_the_edges():
    """A sticky world-writable volume root, the largest release, a release in canonical bytes without a final newline."""
    m,docs,host=fresh();host.tree.get(DATA).mode=0o1777;docs.plan['parent']=hostemu.rows(host,DATA);docs.chain();assert docs.run(host)['status']==m.COMPLETE_STATUS
    m,docs,host=fresh();host.tree.get(DATA).mode=0o775;docs.plan['parent']=hostemu.rows(host,DATA);docs.chain();assert docs.run(host)['status']==m.COMPLETE_STATUS,'group-writable, as signed'
    body=json.loads(k10.RELEASE);body['authorization_ref']='';size=len((json.dumps(body,indent=1,sort_keys=True)+'\n').encode())
    largest=k10.altered(authorization_ref='x'*(32768-size));assert len(largest)==32768
    m,docs,host=fresh(raw=largest);assert len(docs.raw()[0])<=65536,'the bound request with the largest release is still one signed document'
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(TARGET).content)==largest and receipt['installed']['bytes']==32768
    over=k10.altered(authorization_ref='x'*(32769-size));m,docs,host=fresh(raw=over);assert len(over)==32769 and f.refusal(docs.authenticate)=='RELEASE_PLAN_INVALID'
    compact=f.canonical(json.loads(k10.RELEASE));m,docs,host=fresh(raw=compact);assert docs.run(host)['status']==m.COMPLETE_STATUS and bytes(host.tree.get(TARGET).content)==compact

def test_evidence_must_name_the_precheck_receipt_the_rows_were_copied_from():
    m,docs,host=fresh(evidence=[{'role':'SNAPSHOT','operation':'GO_READONLY_SOMETHING_ELSE_01','receipt_sha256':'a'*64}])
    assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'
    m,docs,host=fresh(evidence=[{'role':'DATA_VOLUME_ROWS','operation':'GO_READONLY_HOSTOPS_PRECHECK_01','receipt_sha256':'a'*64},
                                {'role':'SUNDAY_SNAPSHOT','operation':'GO_READONLY_SOMETHING_ELSE_01','receipt_sha256':'b'*64}])
    assert docs.run(host)['status']==m.COMPLETE_STATUS


# ---------------------------------------------------------------- hostile states that appear after the precheck
def on(event,path,action,once=True):
    """A hook that runs action(host) right before the first (or every) call `event` on `path`."""
    done=[False]
    def hook(host,name,detail,calls):
        if name==event and detail and detail[0]==path and not (once and done[0]):
            done[0]=True;action(host)
    return hook

def test_a_name_that_appears_between_the_precheck_and_the_mkdir_is_left_alone_and_the_run_is_a_refusal():
    m,docs,host=fresh()
    host.hook=on('mkdir',BASE,lambda host:host.tree.add(BASE,uid=1000,gid=1000,dev=hostemu.DATA_DEVICE));receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED','DESTINATION_APPEARED_AFTER_PRECHECK','EFFECTS')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and receipt['objects_left_by_this_run']==0
    assert receipt['directories'][0]['state']=='NOT_CREATED' and receipt['ledger']==[{'key':'RELEASE','path':TARGET,'state':'NOT_ATTEMPTED','code':None}]
    foreign=host.tree.get(BASE);assert (foreign.uid,foreign.children)==(1000,{}) and host.fds=={},'what appeared is not touched'

@pytest.mark.parametrize('number,code',[(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EDQUOT,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),
                                         (errno.EPERM,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR')])
def test_a_mkdir_the_kernel_refuses_changed_nothing_and_the_run_is_a_refusal(number,code):
    m,docs,host=fresh();before=k10.state_of(host)
    def hook(host,name,detail,calls):
        if name=='mkdir':raise OSError(number,'injected')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'EFFECTS') and k10.state_of(host)==before
    assert receipt['directories'][0]['errno']==number and receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    m,docs,host=fresh();host.readonly=True;before=k10.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','FILESYSTEM_READ_ONLY') and k10.state_of(host)==before

def test_a_parent_replaced_between_the_precheck_and_the_mkdir_is_a_refusal():
    m,docs,host=fresh();before=None
    def swap(host):host.tree.get(DATA).mode=0o775
    host.hook=on('fstatvfs',DATA,swap);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','PARENT_REPLACED','EFFECTS') and host.mutating()==[] and host.tree.get(BASE) is None
    assert receipt['directories'][0]['state']=='NOT_ATTEMPTED' and receipt['mutating_calls']['issued']==0

def partial(receipt,code,left):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION',code,'EFFECTS'),receipt['code']
    assert receipt['objects_left_by_this_run']==left and receipt['installed'] is None and receipt['readback'] is None and f.sealed(receipt)

def test_created_directory_that_is_not_what_was_signed_is_left_in_place_labelled_and_no_file_is_written():
    def inherits_group(host):host.grpid=True
    def other_owner(host):host.creator=(1000,1000)
    def other_device(host):host.created_device=hostemu.ROOT_DEVICE
    for prepare in (inherits_group,other_owner,other_device):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',1)
        assert receipt['directories'][0]['state']=='CREATED_METADATA_MISMATCH' and receipt['ledger'][0]['state']=='NOT_ATTEMPTED' and host.tree.get(BASE).children=={}
        assert [entry[0] for entry in host.mutating()]==['mkdir'] and host.fds=={},'nothing is repaired and nothing is removed'
    m,docs,host=fresh();host.hook=on('names',BASE,lambda host:host.tree.add(BASE+'/foreign',kind='file',dev=hostemu.DATA_DEVICE));receipt=docs.run(host)
    partial(receipt,'CREATED_NOT_EMPTY',1);assert sorted(host.tree.get(BASE).children)==['foreign']
    for event,path,code,state in (('fsync',BASE,'FSYNC_FAILED','CREATED_NOT_DURABLE'),('fsync',DATA,'FSYNC_FAILED','CREATED_NOT_DURABLE'),('open',BASE,'CREATED_OPEN_FAILED','CREATED_UNVERIFIED')):
        m,docs,host=fresh()
        def hook(host,name,detail,calls,event=event,path=path):
            if name==event and detail[0]==path and any(entry[0]=='mkdir' for entry in host.log):raise OSError(errno.EIO,'injected')
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,1)
        assert receipt['directories'][0]['state']==state and receipt['ledger'][0]['state']=='NOT_ATTEMPTED' and host.fds=={}

def test_directory_swapped_after_its_creation_stops_the_run_before_any_byte_is_written():
    """The volume root belongs to the operational account: that account can rename what root created in it."""
    m,docs,host=fresh()
    def swap(host):
        node=host.tree.get(DATA);node.children['moved-away']=node.children.pop(LEAF);host.tree.add(BASE,uid=1000,gid=1000,mode=0o700,dev=hostemu.DATA_DEVICE)
    host.hook=on('fsync',DATA,swap);receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',1)
    assert receipt['ledger'][0]['state']=='NOT_ATTEMPTED' and host.tree.get(BASE).children=={} and host.tree.get(DATA+'/moved-away').children=={}
    assert [entry[0] for entry in host.mutating()]==['mkdir']

def test_failures_while_the_file_is_written_withdraw_only_the_temporary_of_this_run():
    go16=lambda docs:docs.go16()
    def raising(event,number,index=1):
        seen=[0]
        def hook(host,name,detail,calls):
            if name==event and detail[0].startswith(BASE+'/'):
                seen[0]+=1
                if seen[0]==index:raise OSError(number,'injected')
        return hook
    for hook,code in ((raising('write',errno.ENOSPC),'FILESYSTEM_FULL'),(raising('write',errno.EIO),'FILESYSTEM_ERROR'),(raising('fsync',errno.EIO),'FSYNC_FAILED'),
                      (raising('fstat',errno.EIO),'CREATED_STAT_FAILED')):
        m,docs,host=fresh();host.hook=hook;receipt=docs.run(host);partial(receipt,code,1);row=receipt['ledger'][0]
        assert (row['state'],row['temporary_removed'],row['temporary_removal_code'])==('NOT_CREATED',True,None) and host.tree.get(BASE).children=={},code
        assert k10.classify(host,go16(docs))=='B_DIRECTORY_ONLY' and host.fds=={}
    # the temporary could not be created at all
    for number,code in ((errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED')):
        m,docs,host=fresh()
        def hook(host,name,detail,calls,number=number):
            if name=='create':raise OSError(number,'injected')
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,1);assert receipt['ledger'][0]['state']=='NOT_CREATED' and host.tree.get(BASE).children=={}
    # a write that makes no progress, and one that writes less than asked each time
    m,docs,host=fresh();host.write=lambda fd,data:0;receipt=docs.run(host);partial(receipt,'WRITE_INCOMPLETE',1);assert host.tree.get(BASE).children=={}
    m,docs,host=fresh();original=host.write;host.write=lambda fd,data:original(fd,data[:1000]);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(TARGET).content)==k10.RELEASE and len([entry for entry in host.log if entry[0]=='write'])==6
    assert receipt['mutating_calls']=={'issued':10,'succeeded':10,'failed_nothing_changed':0,'uncertain':0}
    # the mode or the owner the kernel gave the file is not the signed one: withdrawn before the final name exists
    for prepare in (lambda host:setattr(host,'creator',(0,7)),lambda host:setattr(host,'created_device',hostemu.ROOT_DEVICE)):
        m,docs,host=fresh();host.hook=on('create',BASE+'/.hostops-%s-0.partial'%go16(docs),prepare);receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',1)
        assert receipt['ledger'][0]['state']=='NOT_CREATED' and host.tree.get(BASE).children=={}

def test_failures_after_the_link_leave_the_complete_file_and_the_receipt_says_exactly_what_is_left():
    """The final name exists and holds the complete bytes; what failed is the durability or the removal of the temporary.
    Never complete: the ledger state says which of the two names exist."""
    def nth_fsync_of_the_directory(number):
        seen=[0]
        def hook(host,name,detail,calls):
            if name=='fsync' and detail[0]==BASE:
                seen[0]+=1
                if seen[0]==number:raise OSError(errno.EIO,'injected')
        return hook
    def unlink_fails(host,name,detail,calls):
        if name=='unlink':raise OSError(errno.EIO,'injected')
    for hook,code,state,left,links,names in ((nth_fsync_of_the_directory(2),'FSYNC_FAILED','LINKED_TEMPORARY_PRESENT',3,2,2),
                                             (unlink_fails,'TEMPORARY_REMOVAL_FAILED','LINKED_TEMPORARY_PRESENT',3,2,2),
                                             (nth_fsync_of_the_directory(3),'FSYNC_FAILED','INSTALLED_NOT_DURABLE',2,1,1)):
        m,docs,host=fresh();host.hook=hook;receipt=docs.run(host);partial(receipt,code,left);row=receipt['ledger'][0]
        assert row['state']==state and bytes(host.tree.get(TARGET).content)==k10.RELEASE and host.tree.get(TARGET).nlink==links and len(host.tree.get(BASE).children)==names
        assert row['sha256_observed'] is None and host.fds=={},'the readback is not run on a file that is not known durable'
        assert k10.classify(host,docs.go16())==('D_LINKED_TEMPORARY_PRESENT' if names==2 else 'E_INSTALLED')

def test_names_that_appear_inside_the_new_directory_are_never_replaced():
    m,docs,host=fresh();temporary=BASE+'/.hostops-%s-0.partial'%docs.go16()
    host.hook=on('create',temporary,lambda host:host.tree.add(temporary,kind='file',uid=1000,dev=hostemu.DATA_DEVICE,content=b'foreign'));receipt=docs.run(host)
    partial(receipt,'TEMPORARY_NAME_OCCUPIED',1);assert bytes(host.tree.get(temporary).content)==b'foreign' and receipt['ledger'][0]['state']=='NOT_CREATED'
    m,docs,host=fresh();temporary=BASE+'/.hostops-%s-0.partial'%docs.go16()
    host.hook=on('link',temporary,lambda host:host.tree.add(TARGET,kind='file',uid=1000,dev=hostemu.DATA_DEVICE,content=b'foreign'));receipt=docs.run(host)
    partial(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK',1);row=receipt['ledger'][0]
    assert bytes(host.tree.get(TARGET).content)==b'foreign' and sorted(host.tree.get(BASE).children)==[NAME] and (row['state'],row['temporary_removed'])==('NOT_CREATED',True)
    # the temporary itself is swapped before the link: nothing is linked, and what stands at its name is not removed
    m,docs,host=fresh();temporary=BASE+'/.hostops-%s-0.partial'%docs.go16();name=temporary.rsplit('/',1)[1]
    def swap(host):
        host.tree.get(BASE).children.pop(name);host.tree.add(temporary,kind='file',uid=1000,dev=hostemu.DATA_DEVICE,content=b'foreign')
    seen=[0]
    def hook(host,event,detail,calls):
        if event=='lstat' and detail[0]==temporary:
            seen[0]+=1
            if seen[0]==1:swap(host)
    host.hook=hook;receipt=docs.run(host);partial(receipt,'TEMPORARY_REPLACED',2)
    assert sorted(host.tree.get(BASE).children)==[name] and bytes(host.tree.get(temporary).content)==b'foreign' and receipt['ledger'][0]['state']=='TEMPORARY_ONLY'

def test_hostile_changes_between_two_steps_of_the_install_are_seen_and_nothing_foreign_is_touched():
    """What only root, or the owner of the volume root, could do while the run is in progress. Each is found by the
    step that follows it; the receipt names the state, and what is not this run's is left where it is."""
    def temporary_of(docs):return BASE+'/.hostops-%s-0.partial'%docs.go16()
    def swap_directory(host):
        node=host.tree.get(DATA);node.children['moved-away']=node.children.pop(LEAF);host.tree.add(BASE,mode=0o700,dev=hostemu.DATA_DEVICE)
    # the new directory is replaced between the mkdir and its proof
    m,docs,host=fresh();seen=[0]
    def after_mkdir(host,name,detail,calls):
        if name=='lstat' and detail[0]==BASE and any(entry[0]=='mkdir' for entry in host.log):
            seen[0]+=1
            if seen[0]==1:swap_directory(host)
    host.hook=after_mkdir;receipt=docs.run(host);partial(receipt,'CREATED_NAME_REPLACED',1)
    assert receipt['directories'][0]['state']=='CREATED_UNVERIFIED' and receipt['ledger'][0]['state']=='NOT_ATTEMPTED' and [entry[0] for entry in host.mutating()]==['mkdir']
    # the directory is swapped while the temporary is written: found before the link, the temporary stays where it was written
    m,docs,host=fresh();host.hook=on('fsync',temporary_of(docs),swap_directory);receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',2)
    assert receipt['ledger'][0]['state']=='TEMPORARY_ONLY' and host.tree.get(BASE).children=={} and not [entry for entry in host.log if entry[0] in ('link','unlink')]
    assert bytes(host.tree.get(DATA+'/moved-away').children[temporary_of(docs).rsplit('/',1)[1]].content)==k10.RELEASE
    # the temporary gets a second link before the link to the final name: nothing is linked
    m,docs,host=fresh();temporary=temporary_of(docs);seen=[0]
    def second_link(host,name,detail,calls):
        if name=='lstat' and detail[0]==temporary:
            seen[0]+=1
            if seen[0]==1:host.tree.get(temporary).nlink=2
    host.hook=second_link;receipt=docs.run(host);partial(receipt,'TEMPORARY_REPLACED',2);assert NAME not in host.tree.get(BASE).children and receipt['ledger'][0]['state']=='TEMPORARY_ONLY'
    # the kernel reports two links right after the creation, or another mode than asked
    for change in (lambda host:setattr(host.tree.get(temporary_holder[0]),'nlink',2),lambda host:setattr(host.tree.get(temporary_holder[0]),'mode',0o640)):
        m,docs,host=fresh();temporary_holder=[temporary_of(docs)];host.hook=on('fsync',temporary_holder[0],change);receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',1)
        assert receipt['ledger'][0]['state']=='NOT_CREATED' and host.tree.get(BASE).children=={}
    # after the link: the temporary is swapped before its removal (nothing foreign is removed), or the file keeps a second link
    m,docs,host=fresh();temporary=temporary_of(docs);name=temporary.rsplit('/',1)[1];seen=[0]
    def before_removal(host,event,detail,calls):
        if event=='lstat' and detail[0]==temporary:
            seen[0]+=1
            if seen[0]==2:
                host.tree.get(BASE).children.pop(name);host.tree.add(temporary,kind='file',uid=1000,dev=hostemu.DATA_DEVICE,content=b'foreign')
    host.hook=before_removal;receipt=docs.run(host);partial(receipt,'TEMPORARY_REPLACED',3)
    assert bytes(host.tree.get(temporary).content)==b'foreign' and bytes(host.tree.get(TARGET).content)==k10.RELEASE and not [entry for entry in host.log if entry[0]=='unlink']
    assert receipt['ledger'][0]['state']=='LINKED_TEMPORARY_PRESENT'
    m,docs,host=fresh();host.hook=on('unlink',temporary_of(docs),lambda host:setattr(host.tree.get(TARGET),'nlink',3));receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',2)
    assert receipt['ledger'][0]['state']=='INSTALLED_NOT_DURABLE' and receipt['ledger'][0]['links']==2
    # the file changes while the readback reads it
    m,docs,host=fresh()
    def touch(host):host.tree.get(TARGET).ctime+=1
    host.hook=on('read',TARGET,touch);receipt=docs.run(host);partial(receipt,'FILE_CHANGED_DURING_READ',2);assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE'

def test_a_component_swapped_between_its_lstat_and_its_open_is_seen_by_the_walk():
    m,docs,host=fresh();before=None;plan,real=docs.authenticate();done=[False]
    def gate():
        if not done[0] and host.log and host.log[-1]==('lstat',DATA):
            done[0]=True;node=host.tree.get('/mnt');old=node.children.pop('day-d-data');node.children['aside']=old
            host.tree.add(DATA,uid=1000,gid=1000,dev=hostemu.DATA_DEVICE);host.tree.add(PIN,kind='file',mode=0o600,dev=hostemu.DATA_DEVICE)
        return real()
    receipt=docs.perform(host,gate=gate)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','PARENT_CHANGED_DURING_WALK','PRECHECK') and host.mutating()==[] and host.fds=={}

def test_the_gate_is_asked_immediately_before_every_call_that_changes_the_host():
    """For each of the five mutating calls of a complete run there is a look at the clock with nothing between it
    and the call; an expiry at that look means the call is not made."""
    m,docs,host=fresh();plan,real=docs.authenticate();lengths=[]
    def recording():
        lengths.append(len(host.log));return real()
    assert docs.perform(host,gate=recording)['status']==m.COMPLETE_STATUS
    positions=[index for index,entry in enumerate(host.log) if entry[0] in ('mkdir','create','write','link','unlink')];assert len(positions)==5
    for position in positions:
        assert position in lengths,'no gate call immediately before '+host.log[position][0]
        call=max(index for index,length in enumerate(lengths) if length==position);event=host.log[position][0]
        m,docs,again=fresh();plan,real=docs.authenticate();count=[-1]
        def gate():
            count[0]+=1
            if count[0]==call:raise m.Refused('GO_EXPIRED')
            return real()
        before=k10.state_of(again);receipt=docs.perform(again,gate=gate)
        assert not [entry for entry in again.log[position:] if entry[0]==event],event
        assert receipt['code']=='GO_EXPIRED' and (receipt['status']=='REFUSED')==(k10.state_of(again)==before)==(event=='mkdir')

def test_native_identity_is_the_effective_uid_and_gid_of_the_process():
    m=k10.K().m;assert m.Native().identity()==(os.geteuid(),os.getegid())

def installed_then(action):
    """A hook that runs action(host) once, after the temporary was removed and before the readback opens the final name."""
    done=[False]
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==BASE and not done[0] and any(entry[0]=='unlink' for entry in host.log):
            done[0]=True;action(host)
    return hook

def test_readback_inside_the_run_catches_what_changed_after_the_link():
    """Each of these happens after the file is complete under its final name: the run is a partial that says what it
    saw, and it never says that the release is installed."""
    def tamper(host):host.tree.get(TARGET).content[0:1]=b'['
    def truncate(host):del host.tree.get(TARGET).content[100:]
    def replace_by_a_copy(host):
        host.tree.get(BASE).children.pop(NAME);host.tree.add(TARGET,kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=k10.RELEASE)
    def replace_by_a_link(host):
        host.tree.get(BASE).children.pop(NAME);host.tree.add(TARGET,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    def remove(host):host.tree.get(BASE).children.pop(NAME)
    def chmod(host):host.tree.get(TARGET).mode=0o644
    def chown(host):host.tree.get(TARGET).uid=1000
    def second_link(host):host.tree.get(TARGET).nlink=2
    for action,code in ((tamper,'READBACK_HASH_MISMATCH'),(truncate,'READBACK_HASH_MISMATCH'),(replace_by_a_copy,'READBACK_HASH_MISMATCH'),(chmod,'READBACK_HASH_MISMATCH'),
                        (chown,'READBACK_HASH_MISMATCH'),(second_link,'READBACK_HASH_MISMATCH'),(replace_by_a_link,'READBACK_UNAVAILABLE'),(remove,'READBACK_UNAVAILABLE')):
        m,docs,host=fresh();host.hook=installed_then(action);receipt=docs.run(host);partial(receipt,code,2)
        assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and host.fds=={},action.__name__
    m,docs,host=fresh();host.hook=installed_then(tamper);receipt=docs.run(host)
    assert receipt['ledger'][0]['sha256_observed']!=receipt['ledger'][0]['sha256_signed']==f.sha(k10.RELEASE),'the receipt shows the hash it read'
    # the directory, read again from "/": a foreign entry, another mode, another directory at the path, a changed parent
    def foreign_entry(host):host.tree.add(BASE+'/foreign',kind='file',dev=hostemu.DATA_DEVICE)
    def directory_mode(host):host.tree.get(BASE).mode=0o755
    def directory_swapped(host):
        node=host.tree.get(DATA);node.children['moved-away']=node.children.pop(LEAF);host.tree.add(BASE,mode=0o700,dev=hostemu.DATA_DEVICE)
    def parent_mode(host):host.tree.get(DATA).mode=0o775
    reads=lambda host:len([entry for entry in host.log if entry[0]=='read' and entry[1]==TARGET])
    for action,code in ((foreign_entry,'READBACK_MISMATCH'),(directory_mode,'READBACK_MISMATCH'),(directory_swapped,'READBACK_MISMATCH')):
        m,docs,host=fresh();done=[False]
        def hook(host,name,detail,calls,action=action,done=done):
            if name=='lstat' and detail[0]=='/mnt' and reads(host) and not done[0]:
                done[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,2);assert receipt['ledger'][0]['sha256_observed']==f.sha(k10.RELEASE)
    m,docs,host=fresh();host.hook=on('names',BASE,parent_mode,once=False);receipt=docs.run(host)
    # (the first listing is the emptiness proof of the new directory: the parent's fsync follows it and the next step verifies the parent)
    partial(receipt,'PARENT_REPLACED',1)
    m,docs,host=fresh();count=[0]
    def late(host,name,detail,calls):
        if name=='names' and detail[0]==BASE:
            count[0]+=1
            if count[0]==2:parent_mode(host)
    host.hook=late;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',2);assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE'


# ---------------------------------------------------------------- crash points: what a later read finds
def total_calls():
    m,docs,host=fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS;return host.calls,[entry[0] for entry in host.log]

def test_process_death_at_every_host_call_leaves_one_of_five_states_that_a_later_read_tells_apart():
    """The process dies at call n (nothing after it happens; on the host there is then no receipt at all). Whatever n
    is: the tree is in one of five states, they come in this order, and the final name never holds anything but the
    complete signed bytes."""
    total,names=total_calls();seen=[];order=['A_NOTHING','B_DIRECTORY_ONLY','C_TEMPORARY_ONLY','D_LINKED_TEMPORARY_PRESENT','E_INSTALLED']
    for index in range(1,total+1):
        m,docs,host=fresh();before=k10.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);state=k10.classify(host,docs.go16());seen.append(state)
        assert (state=='A_NOTHING')==(k10.state_of(host)==before)
        # what run() would have printed had it lived to print: never a refusal once something exists, never complete
        assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and (receipt['status']!='REFUSED' or state=='A_NOTHING'),(index,names[index-1],state)
        if receipt['status']==m.PARTIAL_STATUS:assert (receipt['code'],receipt['outcome'],receipt['phase_reached'])==('RUN_ESCAPED_STATE_UNKNOWN','PARTIAL_REQUIRES_RECONCILIATION','ESCAPED')
    assert [order.index(state) for state in seen]==sorted(order.index(state) for state in seen),'the states only move forward'
    assert set(seen)==set(order),'every state is reached by some crash point'
    # the calls at which each state begins: the five mutating calls, in order
    first={state:names[seen.index(state)-1] if seen.index(state) else None for state in order}
    assert first=={'A_NOTHING':None,'B_DIRECTORY_ONLY':'mkdir','C_TEMPORARY_ONLY':'create','D_LINKED_TEMPORARY_PRESENT':'link','E_INSTALLED':'unlink'}

def test_death_inside_a_write_leaves_a_temporary_with_a_prefix_of_the_bytes_and_no_final_name():
    m,docs,host=fresh();original=host.write;host.write=lambda fd,data:original(fd,data[:1000]);count=[0]
    def hook(host,name,detail,calls):
        if name=='write':
            count[0]+=1
            if count[0]==4:raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host);temporary=host.tree.get(BASE).children['.hostops-%s-0.partial'%docs.go16()]
    assert k10.classify(host,docs.go16())=='C_TEMPORARY_ONLY' and bytes(temporary.content)==k10.RELEASE[:3000] and (temporary.mode,temporary.uid)==(0o600,0)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['mutating_calls']['uncertain']==1

def test_expiry_or_a_reversed_clock_at_every_gate_is_a_refusal_only_while_nothing_exists():
    """The budget or the GO window ends at the n-th look at the clock. Never complete; REFUSED exactly when the host is
    as it was; and the final name, when it exists, holds the complete bytes."""
    m,docs,host=fresh();count=[0]
    def counting():
        count[0]+=1;return 0.0
    assert docs.run(host,monotonic=counting)['status']==m.COMPLETE_STATUS;total=count[0];assert total>40
    for expired,code in ((61.0,'GO_EXPIRED'),(-1.0,'CLOCK_REVERSED')):
        states=set()
        for index in range(4,total):                              # 1 and 2 are authentication, 3 is the start mark, the last is the receipt's clock
            m,docs,host=fresh();before=k10.state_of(host);count=[0]
            def monotonic(index=index):
                count[0]+=1;return expired if count[0]==index else (0.0 if count[0]<index else 61.0)
            receipt=docs.run(host,monotonic=monotonic);state=k10.classify(host,docs.go16());states.add((receipt['status'],state))
            assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and receipt['code'] in (code,'GO_EXPIRED'),(index,receipt['code'])
            assert (receipt['status']=='REFUSED')==(k10.state_of(host)==before)==(state=='A_NOTHING') and host.fds=={} and f.sealed(receipt)
            if index==4:                                          # the first gate of the run, before anything is observed: the last resort of run()
                assert (receipt['status'],receipt['phase_reached'],host.log)==('REFUSED','BEFORE_ANY_EFFECT',[]);continue
            assert receipt['installed'] is None and receipt['objects_left_by_this_run']=={'A_NOTHING':0,'B_DIRECTORY_ONLY':1,'C_TEMPORARY_ONLY':2,
                                                                                         'D_LINKED_TEMPORARY_PRESENT':3,'E_INSTALLED':2}[state]
            assert receipt['phase_reached'] in ('PRECHECK','EFFECTS') and (receipt['phase_reached']=='PRECHECK')<=(state=='A_NOTHING')
        assert ('REFUSED','A_NOTHING') in states and (m.PARTIAL_STATUS,'E_INSTALLED') in states and (m.PARTIAL_STATUS,'B_DIRECTORY_ONLY') in states

def test_escape_after_an_effect_is_partial_and_before_any_is_a_refusal():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='mkdir':raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1},'a call that was issued and never settled is uncertain'
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='fstatvfs':raise KeyboardInterrupt()
    host.hook=hook;before=k10.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and k10.state_of(host)==before


# ---------------------------------------------------------------- one install per host: there is no second attempt
def test_second_request_after_a_complete_or_a_partial_run_is_refused_and_changes_nothing():
    m,docs,host=fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS
    again=f.Docs(docs.k,k10.fields(host),now=docs.now+timedelta(minutes=15));before=k10.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and k10.state_of(host)==before and receipt['mutating_calls']['issued']==0
    assert receipt['precheck']['destination']['found']=={'type':'dir','uid':0,'gid':0,'mode_octal':'0700','links':1}
    m,docs,host=fresh();host.grpid=True;assert docs.run(host)['status']==m.PARTIAL_STATUS;host.grpid=False
    again=f.Docs(docs.k,k10.fields(host),now=docs.now+timedelta(minutes=15));before=k10.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and k10.state_of(host)==before,'a leftover of a partial run is never repaired by a second one'

def test_two_requests_over_the_same_bytes_differ_only_in_what_is_signed_per_request():
    """The primary and the spare (M1, M1'): the same payload, the same effects, other windows and hashes."""
    k=k10.K();host=f.world(k);first=f.Docs(k,k10.fields(host),now=utc(2026,10,5,8,26),minutes=15);spare=f.Docs(k,k10.fields(host),now=utc(2026,10,5,8,42),minutes=15)
    assert first.go['effects']==spare.go['effects'] and first.pins().payload==spare.pins().payload and first.pins().request!=spare.pins().request
    assert first.go16()!=spare.go16() and spare.run(host,clock=lambda:utc(2026,10,5,8,43))['status']==k.m.COMPLETE_STATUS
