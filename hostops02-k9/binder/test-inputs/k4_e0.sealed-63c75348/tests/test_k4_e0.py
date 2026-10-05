"""K4-E0 (revision 4: both roots under /var/lib/c3po, Codex decision 6) end to end on the emulated host: the literal effects the signers see, both
states of /var/lib/c3po, every refusal with its code and the proof that nothing changed, hostile states after the
precheck, every point at which the process can die and what a later read finds there, expiry at every gate, and what
the receipt says. Synthetic and in memory: no SSH, no host, no credential, no docker binary, no GO. The runner bytes
are synthetic (tests/k4e0.py)."""
import copy
from datetime import timedelta
import errno
import json
import os

import pytest

import family as f
import hostemu
import k4e0

SOURCE,VAR_LIB,C3PO,K9,TOOLS,ORDER,KEYS=k4e0.SOURCE,k4e0.VAR_LIB,k4e0.C3PO,k4e0.K9,k4e0.TOOLS,k4e0.ORDER,k4e0.KEYS
RUNNER=k4e0.RUNNER
ROOT=hostemu.ROOT_DEVICE
def fresh(**options):
    docs,host=k4e0.case(**options);return docs.k.m,docs,host
def refused_untouched(receipt,host,before,code,phase='PRECHECK'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,phase),receipt['code']
    assert k4e0.state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run']==0 and receipt['delivered'] is None and host.fds=={} and host.commands==[] and f.sealed(receipt)
def partial(receipt,code,left):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION',code,'EFFECTS'),receipt['code']
    assert receipt['objects_left_by_this_run']==left and receipt['delivered'] is None and receipt['readback'] is None and f.sealed(receipt)
def on(event,path,action,once=True):
    """A hook that runs action(host) right before the first (or every) call `event` on `path`."""
    done=[False]
    def hook(host,name,detail,calls):
        if name==event and detail and detail[0]==path and not (once and done[0]):
            done[0]=True;action(host)
    return hook
def directory(path,entries):return {'path':path,'mode_octal':'0700','uid':0,'gid':0,'expect':'ABSENT','entries_after':entries}
SPACE={'free_bytes_floor':214748364800,'measured_on':'/var/lib/c3po if present (same filesystem as /var/lib required), else /var/lib'}
IF_ABSENT={'action':'CREATE','mode_octal':'0700','uid':0,'gid':0,'entries_after':2}
IF_PRESENT={'action':'USE_UNCHANGED','require':'DIRECTORY_NOT_A_LINK_UID_0_GID_0_NOT_GROUP_OR_OTHER_WRITABLE_NOT_SETGID_SAME_DEVICE_AS_VAR_LIB',
            'identity':'RECORDED_IN_THE_RECEIPT_AND_HELD_UNCHANGED_TO_THE_END'}


# ---------------------------------------------------------------- the complete run, /var/lib/c3po absent
def test_complete_run_and_the_literal_effects_the_signers_see():
    m,docs,host=fresh();plan=docs.plan;before=k4e0.state_of(host);digest=f.sha(RUNNER);final=TOOLS+'/k9_runner-'+digest+'.py'
    assert docs.go['effects']==docs.authority['effects']=={'operation':'GO_WRITE_HOSTOPS02_K4_E0_01','epoch':'R2D2-V2-SHADOW-2026-10-05',
        'parent':{'path':VAR_LIB,'row':plan['parent'][-1],'chain_sha256':f.sha(f.canonical(plan['parent'])),'mount_point_by_device_change':'/'},
        'open_root':None,
        'c3po_directory':{'path':'/var/lib/c3po','if_absent':IF_ABSENT,'if_present':IF_PRESENT},
        'directories':{'SOURCE_ROOT':directory('/var/lib/c3po/r2d2-v2-source-20261005',0),'K9_ROOT':directory('/var/lib/c3po/r2d2-v2-k9-20261005',4),
                       'K9_TOOLS':directory('/var/lib/c3po/r2d2-v2-k9-20261005/tools',1),'K9_DAYS':directory('/var/lib/c3po/r2d2-v2-k9-20261005/days',0),
                       'K9_CLAIMS':directory('/var/lib/c3po/r2d2-v2-k9-20261005/claims',0),'K9_SECRETS':directory('/var/lib/c3po/r2d2-v2-k9-20261005/secrets',0)},
        'runner':{'path':final,'sha256':digest,'bytes':len(RUNNER),'mode_octal':'0600','uid':0,'gid':0,'links':1,
                  'path_in_k9_containers':'/c3po-k9-tools/k9_runner-'+digest+'.py'},
        'space':SPACE,
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,'activation':False,
        'container_touched':False,'process_started':False}
    assert docs.go['success_criterion']=='EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK'
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['readback'])==(
        m.COMPLETE_STATUS,'EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK',None,'EFFECTS','COMPLETE')
    assert receipt['mutating_calls']=={'issued':11,'succeeded':11,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==8
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
    for path in ORDER:
        node=host.tree.get(path)
        assert (node.kind,node.uid,node.gid,node.mode,node.dev,node.synced)==('dir',0,0,0o700,ROOT,True),path
    assert sorted(host.tree.get(C3PO).children)==['r2d2-v2-k9-20261005','r2d2-v2-source-20261005'] and sorted(host.tree.get(K9).children)==['claims','days','secrets','tools']
    assert host.tree.get(SOURCE).children=={} and sorted(host.tree.get(TOOLS).children)==['k9_runner-'+digest+'.py'];runner=host.tree.get(final)
    assert (runner.kind,runner.uid,runner.gid,runner.mode,runner.nlink,runner.dev,runner.synced)==('file',0,0,0o600,1,ROOT,True)
    assert bytes(runner.content)==RUNNER and host.tree.get(VAR_LIB).synced
    c3po=host.tree.get(C3PO);c3po_identity=(c3po.dev,c3po.ino)
    host.tree.remove(C3PO);assert k4e0.state_of(host)==before,'nothing else changed'
    temporary=TOOLS+'/.hostops-%s-0.partial'%docs.go16()
    assert [entry[:2] for entry in host.mutating()]==[('mkdir',path) for path in ORDER]+[('create',temporary),('write',temporary),('link',temporary),('unlink',temporary)]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[C3PO,VAR_LIB,SOURCE,C3PO,K9,C3PO,TOOLS,K9,K9+'/days',K9,K9+'/claims',K9,K9+'/secrets',K9,
                                                                    temporary,TOOLS,TOOLS]
    assert all(entry[2]==0o700 for entry in host.log if entry[0]=='mkdir') and [entry for entry in host.log if entry[0]=='create'][0][3]==0o600
    create=[entry for entry in host.log if entry[0]=='create'][0]
    assert create[2]&(os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW)==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
    assert [entry for entry in host.log if entry[0]=='link'][0][1:]==(temporary,final) and host.mask==0o077
    assert host.commands==[] and host.fds=={} and not [entry for entry in host.log if entry[0] in ('run','flock','pause','readlink')],'no process, no lock, no wait'
    assert receipt['c3po_directory']=={'state':'ABSENT','found':None,'created':True}
    assert receipt['delivered']=={'source_root':SOURCE,'k9_root':K9,'epoch':'R2D2-V2-SHADOW-2026-10-05',
        'c3po_directory':{'path':C3PO,'created_by_this_run':True,'device':c3po_identity[0],'inode':c3po_identity[1],'uid':0,'gid':0,'mode_octal':'0700'},
        'directories':{key:{'path':path,'mode_octal':'0700','uid':0,'gid':0,'entries':k4e0.ENTRIES[path]} for key,path in zip(KEYS,ORDER)},
        'runner':{'path':final,'path_in_k9_containers':'/c3po-k9-tools/k9_runner-'+digest+'.py','sha256':digest,'bytes':len(RUNNER),'mode_octal':'0600',
                  'uid':0,'gid':0,'links':1,'bytes_equal_the_signed_bytes':True}}
    row=receipt['ledger'][0];assert (row['key'],row['state'],row['sha256_signed'],row['sha256_observed'],row['temporary_removed'])==('K9_RUNNER','INSTALLED_DURABLE',digest,digest,True)
    assert [entry['key'] for entry in receipt['directories']]==KEYS and all(entry['state']=='CREATED_DURABLE' for entry in receipt['directories'])
    assert receipt['parent']==plan['parent']
    assert receipt['precheck']=={'free_bytes':145315507*4096,'free_bytes_measured_on':'/var/lib','seconds_left_before_first_effect':60}
    assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects']) and receipt['observed_at']==docs.now.isoformat()

# ---------------------------------------------------------------- the complete run, /var/lib/c3po present
def test_an_existing_root_private_c3po_directory_is_used_unchanged_and_its_identity_is_recorded():
    for mode in (0o755,0o700,0o711,0o1755):
        m,docs,host=fresh(c3po=True);node=host.tree.get(C3PO);node.mode=mode;host.tree.add(C3PO+'/other-tree',mode=0o700)
        identity=(node.dev,node.ino,node.uid,node.gid,node.mode,node.mtime,node.ctime);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS,(oct(mode),receipt['code'])
        assert receipt['mutating_calls']=={'issued':10,'succeeded':10,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==7
        assert [entry[:2] for entry in host.mutating()][:2]==[('mkdir',SOURCE),('mkdir',K9)] and not [entry for entry in host.mutating() if entry[1]==C3PO]
        assert (node.dev,node.ino,node.uid,node.gid,node.mode)==identity[:5] and sorted(node.children)==['other-tree','r2d2-v2-k9-20261005','r2d2-v2-source-20261005'],'used'
        found={'type':'dir','uid':0,'gid':0,'mode_octal':'%04o'%mode,'links':1,'device':node.dev,'inode':node.ino}
        assert receipt['c3po_directory']=={'state':'PRESENT','found':found,'created':False} and receipt['precheck']['free_bytes_measured_on']==C3PO
        assert receipt['precheck']['source_root']=={'exists':False,'found':None} and receipt['precheck']['k9_root']=={'exists':False,'found':None}
        assert receipt['delivered']['c3po_directory']=={'path':C3PO,'created_by_this_run':False,'device':node.dev,'inode':node.ino,'uid':0,'gid':0,'mode_octal':'%04o'%mode}
        assert [entry['key'] for entry in receipt['directories']]==[key for key in KEYS if key!='VAR_LIB_C3PO'] and 'VAR_LIB_C3PO' not in receipt['delivered']['directories']
        assert k4e0.classify(host,docs.go16(),c3po_existed=True)=='E_DELIVERED' and host.fds=={}
    m,docs,host=fresh(c3po=True);assert docs.go['effects']==fresh()[1].go['effects'],'the signed effects do not depend on the state of /var/lib/c3po'

def test_an_existing_c3po_directory_that_changes_during_the_run_stops_it():
    for change,code in ((lambda node:setattr(node,'mode',0o775),'PARENT_REPLACED'),(lambda node:setattr(node,'uid',1000),'PARENT_REPLACED')):
        m,docs,host=fresh(c3po=True);node=host.tree.get(C3PO)
        host.hook=on('mkdir',K9+'/days',lambda host:change(node));receipt=docs.run(host);partial(receipt,code,4)
        assert host.tree.get(K9+'/claims') is None,'the check before the next mkdir sees the change'
    # changed after the last check that walks through it (the runner's readback) and before the end: the final check
    # of the held directory sees it
    m,docs,host=fresh(c3po=True);node=host.tree.get(C3PO);armed=[False]
    def hook(host,name,detail,calls):
        if not armed[0] and name=='names' and detail[0]==K9+'/secrets' and 'unlink' in [entry[0] for entry in host.log]:armed[0]=True;node.mode=0o750
    host.hook=hook;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',7);assert armed[0]

def test_receipt_names_the_runner_by_hash_and_never_carries_its_bytes():
    m,docs,host=fresh();receipt=docs.run(host);line=f.line(receipt)
    assert k4e0.b64(RUNNER).encode() not in line and b'SYNTHETIC TEST BYTES' not in line and len(line)<14000 and receipt['size_reductions']==[] and f.sealed(receipt)
    assert receipt['secret_bytes_in_receipt'] is False and hostemu.SECRET.encode() not in line

def test_source_carries_no_runner_part_no_process_and_no_lock():
    k=k4e0.K();m=k.m
    assert k.report['parts']==['core','parents','files'] and not hasattr(m,'COMMANDS') and not hasattr(m,'NativeRunner') and not hasattr(m,'subprocess') and not hasattr(m,'fcntl')
    assert [base.__name__ for base in m.Native.__mro__[1:-1]]==['NativeRead','NativeFiles'] and not hasattr(m.Native,'run') and not hasattr(m.Native,'flock')
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS,m.DATES,m.EVIDENCE_OPERATIONS)==(True,False,'WRITE_SESSIONS',
        ('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10'),('GO_READONLY_HOSTOPS_PRECHECK_01',))
    assert m.EVIDENCE_REQUIRED is True and m.MAX_GATE_SPAN_SECONDS==900 and m.SCOPE['processes_started']==0

def test_no_command_answer_can_reach_this_run_because_it_starts_none():
    for prepare in (lambda host:host.tree.remove('/usr/bin/docker'),lambda host:host.hang.add('docker'),lambda host:host.absent.add('docker'),
                    lambda host:setattr(host.docker,'containers',[]),lambda host:setattr(host.docker,'images',[])):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and host.commands==[] and 'commands_started' not in receipt

def test_scope_and_statement_are_literally_what_the_signers_sign():
    m=k4e0.K().m
    assert m.SCOPE_STATEMENT==('Creates, once, under /var/lib, whose chain from "/" is controlled by root alone: the directory /var/lib/c3po only if it is absent '
        '(if present it must be a root:root directory on the filesystem of /var/lib, not a link, not writable by group or other, not setgid, and is used unchanged); '
        'in it the source root /var/lib/c3po/r2d2-v2-source-20261005 and the K9 root /var/lib/c3po/r2d2-v2-k9-20261005 with its four directories tools, days, claims '
        'and secrets (every directory created root:root 0700); and in tools the file k9_runner-<sha256>.py (root:root 0600) holding exactly the runner bytes whose '
        'SHA-256 and size the request signs, for epoch R2D2-V2-SHADOW-2026-10-05. Nothing is created unless that filesystem has 214748364800 bytes available. '
        'Exclusive creation, fsync and a readback of the bytes and of every directory through descriptors inside the run. Nothing that exists is overwritten, '
        'renamed, chmodded, chowned or removed, except the temporary of this run once its identity is proved. No process is started, no secret is read or written, '
        'no container is touched and nothing is activated.')
    row=lambda key,path,entries:{'key':key,'path':path,'mode_octal':'0700','entries_after':entries}
    assert m.SCOPE=={'operation':'GO_WRITE_HOSTOPS02_K4_E0_01','dates':['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10'],
        'statement':m.SCOPE_STATEMENT,'core_sha256':m.CORE_SHA256,'writes_allowed':True,'activation_allowed':False,'epoch':'R2D2-V2-SHADOW-2026-10-05',
        'placement':{'var_lib':'/var/lib','c3po_directory':'/var/lib/c3po','source_root':'/var/lib/c3po/r2d2-v2-source-20261005',
                     'k9_root':'/var/lib/c3po/r2d2-v2-k9-20261005','open_root':None},
        'c3po_directory':{'path':'/var/lib/c3po','if_absent':IF_ABSENT,'if_present':IF_PRESENT},
        'directories':[row('SOURCE_ROOT',SOURCE,0),row('K9_ROOT',K9,4),row('K9_TOOLS',TOOLS,1),row('K9_DAYS',K9+'/days',0),
                       row('K9_CLAIMS',K9+'/claims',0),row('K9_SECRETS',K9+'/secrets',0)],
        'runner':{'directory':TOOLS,'name':'k9_runner-<sha256>.py','mode_octal':'0600','max_bytes':40960,'directory_in_k9_containers':'/c3po-k9-tools'},
        'space':SPACE,'files':m.FILES_SCOPE,'evidence_operations_required':['GO_READONLY_HOSTOPS_PRECHECK_01'],
        'file_contents_read':['/proc/sys/kernel/random/boot_id','the runner file this run delivered (readback inside the run)'],'processes_started':0,
        'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker','systemctl',
                 'a shell','a network connection','a secret','activation','a container','a second attempt'],
        'limits':{'max_seconds':60,'max_gate_span_seconds':900,'receipt_bytes':60000,'runner_bytes':40960,'free_bytes_floor':214748364800,'write_allowance_seconds':15}}
    assert (m.OPERATION,m.PHASE,m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==(
        'GO_WRITE_HOSTOPS02_K4_E0_01','WRITE_K4_E0_EPOCH_ROOTS_AND_K9_RUNNER','EPOCH_ROOTS_CREATED_RUNNER_DELIVERED_READ_BACK','PARTIAL_REQUIRES_RECONCILIATION',
        'REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_REQUIRES_RECONCILIATION')
    assert m.PLAN_KEYS==frozenset(('parent','runner','evidence_boot_id_sha256')) and m.RUNNER_KEYS==frozenset(('path','content_b64','sha256','bytes'))

def test_placement_is_codex_decision_named_in_one_place_and_nothing_is_on_the_data_volume():
    """Codex N-8 (W/codex-n8-placement-20261004.txt) and decision 6 (#429 5985748037): the placement lines are the only
    literals of the roots, both roots are entries of /var/lib/c3po, and the data volume is named nowhere in the part."""
    m=k4e0.K().m;own=(k4e0.DIRECTORY/'op.py').read_text()
    assert (m.VAR_LIB,m.C3PO_NAME,m.SOURCE_ROOT_NAME,m.K9_ROOT_NAME)==('/var/lib','c3po','r2d2-v2-source-20261005','r2d2-v2-k9-20261005')
    for literal in ("'r2d2-v2-source-20261005'","'r2d2-v2-k9-20261005'","'/var/lib'","'c3po'"):assert own.count(literal)==1,literal
    assert 'day-d-data' not in own and 'DATA_VOLUME' not in own and 'MAINTENANCE_PIN' not in own and 'open_root=None' in own and 'open_root=VAR_LIB' not in own
    assert own.index('# ---- PLACEMENT.')<own.index("VAR_LIB='/var/lib'")<own.index('# ---- end of the placement')
    assert (m.SOURCE_ROOT,m.C3PO_DIRECTORY,m.K9_ROOT)==(SOURCE,C3PO,K9) and [row[1] for row in m.E0_DIRECTORIES]==[path for path in ORDER if path!=C3PO]
    assert m.SOURCE_ROOT.rsplit('/',1)[0]==m.K9_ROOT.rsplit('/',1)[0]==m.C3PO_DIRECTORY and all(row[1].startswith(m.K9_ROOT+'/') for row in m.E0_DIRECTORIES[2:])
    assert m.E0_EPOCH==k4e0.EPOCH and m.CONTAINER_TOOLS_DIRECTORY=='/c3po-k9-tools'

def test_receipt_that_would_not_fit_is_reduced_by_flagged_steps_and_is_then_never_complete():
    m,docs,host=fresh();receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    def again(**padding):
        body={key:value for key,value in receipt.items() if key not in ('metadata_sha256','size_reductions')};body.update(padding);return m.seal(body)
    reduced=again(precheck={'pad':'x'*70000})
    assert (reduced['status'],reduced['outcome'],reduced['size_reductions'],reduced['precheck'])==(m.PARTIAL_STATUS,'RECEIPT_REDUCED_STATE_REQUIRES_READBACK',['PRECHECK_DROPPED'],{'reduced_for_size':True})
    assert reduced['parent']==receipt['parent'] and reduced['mutating_calls']==receipt['mutating_calls'] and f.sealed(reduced)
    reduced=again(precheck={'pad':'x'*70000},parent=[{'pad':'y'*30000},{'pad':'z'*30000}])
    assert (reduced['size_reductions'],reduced['parent'],reduced['precheck'])==(['PRECHECK_DROPPED','PARENT_REDUCED_TO_COUNT'],2,{'reduced_for_size':True})
    assert f.sealed(reduced) and reduced['ledger']==receipt['ledger'] and reduced['objects_left_by_this_run']==8


# ---------------------------------------------------------------- everything is looked at before the first creation
def test_every_precheck_refusal_leaves_the_host_exactly_as_it_was():
    def other_boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    def boot_garbage(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'not a boot id\n')
    def root_mode(host):host.tree.root.mode=0o777
    def var_inode(host):host.tree.get('/var').ino+=1
    def var_group(host):host.tree.get('/var').gid=4
    def var_lib_inode(host):host.tree.get(VAR_LIB).ino+=1
    def var_lib_mode(host):host.tree.get(VAR_LIB).mode=0o775
    def var_lib_owner(host):host.tree.get(VAR_LIB).uid=1000
    def var_lib_group(host):host.tree.get(VAR_LIB).gid=4
    def var_lib_device(host):host.tree.get(VAR_LIB).dev=hostemu.DATA_DEVICE
    def var_lib_is_a_link(host):
        node=host.tree.get('/var');node.children['lib-real']=node.children.pop('lib');host.tree.add(VAR_LIB,kind='symlink',mode=0o777)
    def var_lib_missing(host):host.tree.remove(VAR_LIB)
    def c3po_link(host):host.tree.add(C3PO,kind='symlink',mode=0o777)
    def c3po_file(host):host.tree.add(C3PO,kind='file',content=b'x')
    def c3po_fifo(host):host.tree.add(C3PO,kind='fifo')
    def c3po_uid(host):k4e0.with_c3po(host,uid=1000)
    def c3po_gid(host):k4e0.with_c3po(host,gid=1000)
    def c3po_group_writable(host):k4e0.with_c3po(host,mode=0o775)
    def c3po_other_writable(host):k4e0.with_c3po(host,mode=0o757)
    def c3po_world_sticky(host):k4e0.with_c3po(host,mode=0o1777)
    def c3po_setgid(host):k4e0.with_c3po(host,mode=0o2755)
    def c3po_on_the_data_volume(host):k4e0.with_c3po(host);host.tree.get(C3PO).dev=hostemu.DATA_DEVICE
    def source_empty(host):k4e0.with_c3po(host);host.tree.add(SOURCE,mode=0o700)
    def source_link(host):k4e0.with_c3po(host);host.tree.add(SOURCE,kind='symlink',mode=0o777)
    def source_file(host):k4e0.with_c3po(host);host.tree.add(SOURCE,kind='file',content=b'x')
    def k9_present(host):k4e0.with_c3po(host);host.tree.add(K9,mode=0o700)
    def k9_link(host):k4e0.with_c3po(host);host.tree.add(K9,kind='symlink',mode=0o777)
    def full(host):host.vfs[ROOT].f_bavail=255
    def statvfs_garbage(host):host.vfs[ROOT].f_frsize=0
    def no_noatime(host):host.noatime_available=False
    def not_root(host):host.actor=(0,5)
    cases=((other_boot,'EVIDENCE_FROM_EARLIER_BOOT'),(boot_garbage,'BOOT_ID_INVALID'),(root_mode,'PARENT_IDENTITY_MISMATCH'),(var_inode,'PARENT_IDENTITY_MISMATCH'),
           (var_group,'PARENT_IDENTITY_MISMATCH'),(var_lib_inode,'PARENT_IDENTITY_MISMATCH'),(var_lib_mode,'PARENT_IDENTITY_MISMATCH'),
           (var_lib_owner,'PARENT_IDENTITY_MISMATCH'),(var_lib_group,'PARENT_IDENTITY_MISMATCH'),(var_lib_device,'PARENT_IDENTITY_MISMATCH'),
           (var_lib_is_a_link,'PARENT_SYMLINK_COMPONENT'),(var_lib_missing,'PARENT_MISSING'),
           (c3po_link,'C3PO_DIRECTORY_NOT_A_DIRECTORY'),(c3po_file,'C3PO_DIRECTORY_NOT_A_DIRECTORY'),(c3po_fifo,'C3PO_DIRECTORY_NOT_A_DIRECTORY'),
           (c3po_uid,'C3PO_DIRECTORY_NOT_ROOT_OWNED'),(c3po_gid,'C3PO_DIRECTORY_NOT_ROOT_OWNED'),(c3po_group_writable,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER'),
           (c3po_other_writable,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER'),(c3po_world_sticky,'C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER'),
           (c3po_setgid,'C3PO_DIRECTORY_SETGID'),(c3po_on_the_data_volume,'C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM'),
           (source_empty,'SOURCE_ROOT_PRESENT'),(source_link,'SOURCE_ROOT_PRESENT'),(source_file,'SOURCE_ROOT_PRESENT'),
           (k9_present,'K9_ROOT_PRESENT'),(k9_link,'K9_ROOT_PRESENT'),
           (full,'FREE_SPACE_BELOW_FLOOR'),(statvfs_garbage,'STATVFS_INVALID'),(no_noatime,'NOATIME_UNAVAILABLE'),(not_root,'EXECUTOR_IDENTITY'))
    for prepare,code in cases:
        m,docs,host=fresh();prepare(host);before=k4e0.state_of(host);receipt=docs.run(host)
        refused_untouched(receipt,host,before,code)
        assert not [entry for entry in host.log if entry[0] in ('mkdir','create','write','link','unlink','fsync')],prepare.__name__
    m,docs,host=fresh();c3po_uid(host);receipt=docs.run(host)
    assert receipt['c3po_directory']['found']['uid']==1000 and receipt['c3po_directory']['created'] is False and 'source_root' not in receipt['precheck']
    m,docs,host=fresh();k9_link(host);receipt=docs.run(host)
    assert receipt['precheck']['k9_root']['found']['type']=='symlink' and receipt['precheck']['source_root']=={'exists':False,'found':None}
    # nothing of the data volume is looked at: no open, lstat or statvfs below /mnt
    m,docs,host=fresh();docs.run(host);assert not [entry for entry in host.log if len(entry)>1 and isinstance(entry[1],str) and entry[1].startswith('/mnt')]
    m,docs,host=fresh();host.tree.remove(hostemu.DATA);host.tree.remove('/mnt');assert docs.run(host)['status']==m.COMPLETE_STATUS,'the data volume is not needed'

def test_order_of_the_precheck():
    m,docs,host=fresh();host.actor=(1000,0);host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');receipt=docs.run(host)
    assert receipt['code']=='EXECUTOR_IDENTITY' and host.log==[],'nothing is looked at, not even the umask is set'
    m,docs,host=fresh();host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');host.tree.get(VAR_LIB).ino+=1
    assert docs.run(host)['code']=='BOOT_ID_INVALID'
    m,docs,host=fresh();host.tree.get(VAR_LIB).ino+=1;k4e0.with_c3po(host,uid=1000);assert docs.run(host)['code']=='PARENT_IDENTITY_MISMATCH'
    m,docs,host=fresh();k4e0.with_c3po(host,mode=0o777);host.tree.add(SOURCE);host.vfs[ROOT].f_bavail=0;assert docs.run(host)['code']=='C3PO_DIRECTORY_WRITABLE_BY_GROUP_OR_OTHER'
    m,docs,host=fresh();k4e0.with_c3po(host);host.tree.add(SOURCE);host.tree.add(K9);assert docs.run(host)['code']=='SOURCE_ROOT_PRESENT'
    m,docs,host=fresh();k4e0.with_c3po(host);host.tree.add(K9);host.vfs[ROOT].f_bavail=0;assert docs.run(host)['code']=='K9_ROOT_PRESENT'
    m,docs,host=fresh();docs.run(host);calls=[entry[0] for entry in host.log]
    assert host.log.index(('lstat',C3PO))<calls.index('fstatvfs')<calls.index('mkdir') and ('lstat',SOURCE) not in host.log[:calls.index('mkdir')]
    m,docs,host=fresh(c3po=True);docs.run(host);names=[entry[:2] for entry in host.log if entry[0] in ('lstat','open')]
    assert names.index(('lstat',C3PO))<names.index(('open',C3PO))<names.index(('lstat',SOURCE))<names.index(('lstat',K9))

def test_the_gate_is_asked_before_each_lookup_and_before_the_open_of_c3po():
    m,docs,host=fresh();before=k4e0.state_of(host);plan,real=docs.authenticate()
    def gate():
        if [entry[:2] for entry in host.log][-2:]==[('fstat',VAR_LIB),('fstat',VAR_LIB)] and ('lstat',C3PO) not in host.log:raise m.Refused('GO_EXPIRED')
        return real()
    receipt=docs.perform(host,gate=gate);refused_untouched(receipt,host,before,'GO_EXPIRED');assert ('lstat',C3PO) not in host.log
    for target,after in ((('open',C3PO),('lstat',C3PO)),(('lstat',SOURCE),None),(('lstat',K9),('lstat',SOURCE))):
        m,docs,host=fresh(c3po=True);before=k4e0.state_of(host);plan,real=docs.authenticate()
        def gate(target=target,after=after):
            log=[entry[:2] for entry in host.log]
            if target not in log:
                if after is not None and log[-1:]==[after]:raise m.Refused('GO_EXPIRED')
                if after is None and ('open',C3PO) in log and log[-1:]==[('fstat',C3PO)]:raise m.Refused('GO_EXPIRED')
            return real()
        receipt=docs.perform(host,gate=gate);refused_untouched(receipt,host,before,'GO_EXPIRED');assert target not in [entry[:2] for entry in host.log],target

def test_budget_is_the_last_refusal_before_the_first_creation():
    for elapsed,ok in ((0.0,True),(45.0,True),(45.5,False),(59.0,False)):
        m,docs,host=fresh();before=k4e0.state_of(host);mono=[0.0];plan,gate=docs.authenticate(monotonic=lambda:mono[0]);mono[0]=elapsed
        receipt=docs.perform(host,gate=gate,monotonic=lambda:mono[0])
        if ok:assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['seconds_left_before_first_effect']==int(60-elapsed)
        else:
            refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            assert [entry[0] for entry in host.log][-1]=='fstatvfs'
    m,docs,host=fresh();before=k4e0.state_of(host);late=docs.now+timedelta(minutes=4,seconds=50)
    receipt=docs.run(host,clock=lambda:late);refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def test_precheck_failure_of_any_kind_is_a_refusal_with_a_constant_code():
    for name,target,error,code,c3po in (('lstat',C3PO,OSError(errno.EACCES,'injected'),'PRECHECK_OS_ERROR',False),('lstat',SOURCE,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR',True),
                                        ('lstat',K9,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR',True),('fstatvfs',None,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR',False),
                                        ('umask',None,RuntimeError('injected'),'PRECHECK_FAILED',False),('fstatvfs',None,RuntimeError('injected'),'PRECHECK_FAILED',True)):
        m,docs,host=fresh(c3po=c3po);before=k4e0.state_of(host)
        def hook(host,event,detail,calls,name=name,target=target,error=error):
            if event==name and (target is None or detail[0]==target):raise error
        host.hook=hook;receipt=docs.run(host);refused_untouched(receipt,host,before,code);assert 'injected' not in json.dumps(receipt)
    # the existing /var/lib/c3po cannot be opened, or is another object when it is opened
    for action in (lambda host:(_ for _ in ()).throw(OSError(errno.EACCES,'injected')),
                   lambda host:host.tree.get(C3PO).__setattr__('ino',host.tree.get(C3PO).ino+1000),
                   lambda host:host.tree.get(C3PO).__setattr__('mode',0o775),lambda host:host.tree.get(C3PO).__setattr__('uid',7)):
        m,docs,host=fresh(c3po=True);before=k4e0.state_of(host);armed=[False]
        def hook(host,event,detail,calls,action=action):
            if event=='open' and detail[0]==C3PO and not armed[0]:
                armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==('REFUSED','C3PO_DIRECTORY_CHANGED_DURING_PRECHECK') and host.mutating()==[] and host.fds=={}


# ---------------------------------------------------------------- the plan: refused from its bytes, before any claim
def change(path,value):
    def apply(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return apply
def without(key):
    def apply(plan):del plan['runner'][key]
    return apply
def rows_of(path):
    def apply(plan):
        host=f.world(k4e0.K());host.tree.add(path) if host.tree.get(path) is None else None;plan['parent']=hostemu.rows(host,path)
    return apply
PLAN_CASES=[
    (change(['parent'],None),'CHAIN_ROW_INVALID'),(change(['parent'],[]),'CHAIN_ROW_INVALID'),(lambda plan:plan['parent'].pop(),'CHAIN_ROW_INVALID'),
    (change(['parent',2,'path'],'/var/cache'),'CHAIN_ROW_INVALID'),(rows_of(hostemu.DATA),'CHAIN_ROW_INVALID'),(rows_of('/var/lib/c3po'),'CHAIN_ROW_INVALID'),
    (rows_of('/mnt'),'CHAIN_ROW_INVALID'),(change(['parent',2,'inode'],0),'CHAIN_ROW_INVALID'),
    (change(['parent',2,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['parent',1,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['parent',0,'uid'],1000),'CHAIN_ROW_UNSAFE'),
    (change(['parent',2,'mode'],0o775),'CHAIN_ROW_UNSAFE'),(change(['parent',2,'mode'],0o757),'CHAIN_ROW_UNSAFE'),(change(['parent',2,'mode'],0o1777),'CHAIN_ROW_UNSAFE'),
    (change(['parent',1,'mode'],0o777),'CHAIN_ROW_UNSAFE'),(change(['parent',2,'mode'],0o2755),'PARENT_SETGID'),
    (change(['parent',2,'gid'],1000),'CHAIN_NOT_ROOT_CONTROLLED'),(change(['parent',1,'gid'],4),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['parent',0,'gid'],1000),'CHAIN_NOT_ROOT_CONTROLLED'),(change(['parent',1,'mode'],0o2755),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['parent',0,'mode'],0o2755),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
    (change(['runner'],None),'RUNNER_PLAN_INVALID'),(change(['runner','extra'],1),'RUNNER_PLAN_INVALID'),(without('path'),'RUNNER_PLAN_INVALID'),
    (without('bytes'),'RUNNER_PLAN_INVALID'),(change(['runner','bytes'],0),'RUNNER_PLAN_INVALID'),(change(['runner','bytes'],True),'RUNNER_PLAN_INVALID'),
    (change(['runner','bytes'],40961),'RUNNER_PLAN_INVALID'),(change(['runner','sha256'],'0'*64),'RUNNER_PLAN_INVALID'),
    (change(['runner','sha256'],f.sha(RUNNER).upper()),'RUNNER_PLAN_INVALID'),
    (change(['runner','path'],TOOLS+'/k9_runner.py'),'RUNNER_PATH_NOT_CONTENT_ADDRESSED'),
    (change(['runner','path'],'/mnt/day-d-data/r2d2-v2-k9-20261005/tools/k9_runner-'+f.sha(RUNNER)+'.py'),'RUNNER_PATH_NOT_CONTENT_ADDRESSED'),
    (change(['runner','path'],K9+'/k9_runner-'+f.sha(RUNNER)+'.py'),'RUNNER_PATH_NOT_CONTENT_ADDRESSED'),
    (change(['runner','path'],'/c3po-k9-tools/k9_runner-'+f.sha(RUNNER)+'.py'),'RUNNER_PATH_NOT_CONTENT_ADDRESSED'),
    (change(['runner','sha256'],'3'*64),'RUNNER_PATH_NOT_CONTENT_ADDRESSED'),
    (lambda plan:plan['runner'].update(sha256='3'*64,path=TOOLS+'/k9_runner-'+'3'*64+'.py'),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['runner','bytes'],len(RUNNER)-1),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['runner','content_b64'],'not base64!'),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),(change(['runner','content_b64'],None),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['runner','content_b64'],k4e0.b64(RUNNER+b' ')),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['runner','content_b64'],k4e0.b64(RUNNER)[:8]+'\n'+k4e0.b64(RUNNER)[8:]),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['runner','content_b64'],'é'+k4e0.b64(RUNNER)),'RUNNER_BYTES_NOT_THE_SIGNED_HASH'),
]
@pytest.mark.parametrize('index',range(len(PLAN_CASES)))
def test_plan_refusals_are_authentication_refusals_nothing_is_touched_and_no_go_is_claimed(index,tmp_path):
    apply,code=PLAN_CASES[index];m,docs,host=fresh();apply(docs.plan);docs.chain()
    assert f.refusal(docs.authenticate)==code,code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['outcome'])==('REFUSED',code,'AUTHENTICATION','REFUSED_NOTHING_CHANGED')
    assert receipt['mutating_calls']['issued']==0 and f.sealed(receipt)
    dispatch=f.Dispatch(docs,tmp_path);assert f.refusal(dispatch.prepare)==code and not dispatch.claims()

def test_validate_plan_judges_the_runner_and_the_k9_chain_itself():
    m,docs,host=fresh();plan=copy.deepcopy(docs.plan);m.validate_plan(plan)
    plan['runner']=dict(k4e0.runner_member(),content_b64=k4e0.b64(RUNNER[:-1]+b'X'));assert f.refusal(lambda:m.validate_plan(plan))=='RUNNER_BYTES_NOT_THE_SIGNED_HASH'
    plan=copy.deepcopy(docs.plan);plan['parent'][2]['gid']=1000;assert f.refusal(lambda:m.validate_plan(plan))=='CHAIN_NOT_ROOT_CONTROLLED'
    plan=copy.deepcopy(docs.plan);plan['parent'][2]['mode']=0o750;m.validate_plan(plan)

def test_largest_runner_still_fits_one_signed_document_and_one_byte_more_is_refused():
    largest=(RUNNER*1100)[:40960];m,docs,host=fresh(raw=largest);size=len(docs.raw()[0])
    assert size<=65536-2048,size
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(k4e0.runner_path(largest)).content)==largest
    over=(RUNNER*1100)[:40961];m,docs,host=fresh(raw=over);assert f.refusal(docs.authenticate)=='RUNNER_PLAN_INVALID'

def test_accepted_plans_at_the_edges():
    m,docs,host=fresh();host.tree.get(VAR_LIB).mode=0o711;docs.plan['parent']=hostemu.rows(host,VAR_LIB);docs.chain();assert docs.run(host)['status']==m.COMPLETE_STATUS
    m,docs,host=fresh();host.tree.get(VAR_LIB).mode=0o700;docs.plan['parent']=hostemu.rows(host,VAR_LIB);docs.chain();assert docs.run(host)['status']==m.COMPLETE_STATUS

def test_evidence_must_name_the_precheck_receipt_the_rows_were_copied_from():
    m,docs,host=fresh(evidence=[{'role':'SNAPSHOT','operation':'GO_READONLY_SOMETHING_ELSE_01','receipt_sha256':'a'*64}])
    assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_every_day_of_the_class_is_accepted_and_the_day_before_is_not():
    for day in (5,6,8,10):
        now=f.moment(k4e0.K()).replace(day=day,hour=21,minute=38);m,docs,host=fresh(now=now);assert docs.run(host)['status']==m.COMPLETE_STATUS,day
    now=f.moment(k4e0.K()).replace(day=4,hour=21);m,docs,host=fresh(now=now);assert f.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'


# ---------------------------------------------------------------- hostile states that appear after the precheck
@pytest.mark.parametrize('position',range(7))
def test_a_name_that_appears_before_its_mkdir_is_left_alone(position):
    m,docs,host=fresh();path=ORDER[position]
    host.hook=on('mkdir',path,lambda host:host.tree.add(path,uid=1000,gid=1000));receipt=docs.run(host)
    if position==0:
        assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','DESTINATION_APPEARED_AFTER_PRECHECK','EFFECTS')
        assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    else:
        partial(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK',position)
        assert receipt['mutating_calls']=={'issued':position+1,'succeeded':position,'failed_nothing_changed':1,'uncertain':0}
    assert [entry['state'] for entry in receipt['directories']]==['CREATED_DURABLE']*position+['NOT_CREATED']+['NOT_ATTEMPTED']*(6-position)
    assert receipt['ledger']==[{'key':'K9_RUNNER','path':k4e0.runner_path(),'state':'NOT_ATTEMPTED','code':None}]
    foreign=host.tree.get(path);assert (foreign.uid,foreign.children)==(1000,{}) and host.fds=={},'what appeared is not touched'
    assert receipt['c3po_directory']['created'] is (position>0)

@pytest.mark.parametrize('number,code',[(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR')])
def test_a_mkdir_the_kernel_refuses_changed_nothing_and_only_the_first_is_a_refusal(number,code):
    m,docs,host=fresh();before=k4e0.state_of(host)
    def hook(host,name,detail,calls):
        if name=='mkdir':raise OSError(number,'injected')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'EFFECTS') and k4e0.state_of(host)==before
    for target,left,state in ((SOURCE,1,'B1_C3PO'),(TOOLS,3,'B3_K9_ROOT')):
        m,docs,host=fresh()
        def at(host,name,detail,calls,target=target):
            if name=='mkdir' and detail[0]==target:raise OSError(number,'injected')
        host.hook=at;receipt=docs.run(host);partial(receipt,code,left);assert k4e0.classify(host,docs.go16())==state

def test_a_parent_replaced_between_the_precheck_and_the_first_mkdir_is_a_refusal():
    m,docs,host=fresh();armed=[False]
    def hook(host,name,detail,calls):
        if name=='fstatvfs' and not armed[0]:armed[0]=True;host.tree.get(VAR_LIB).ino+=7
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_REPLACED') and host.mutating()==[] and host.tree.get(C3PO) is None

def test_created_directory_that_is_not_what_was_signed_is_left_in_place_labelled_and_nothing_more_is_created():
    for prepare in (lambda host:setattr(host,'creator',(0,1000)),lambda host:setattr(host,'creator',(1000,1000)),lambda host:setattr(host,'created_device',hostemu.DATA_DEVICE)):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',1)
        assert [entry[0] for entry in host.mutating()]==['mkdir'] and host.fds=={} and host.tree.get(SOURCE) is None and receipt['c3po_directory']['created'] is False
    m,docs,host=fresh();host.hook=on('mkdir',SOURCE,lambda host:setattr(host,'creator',(0,1000)));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',2);assert receipt['c3po_directory']['created'] is True and host.tree.get(K9) is None
    m,docs,host=fresh();host.hook=on('mkdir',K9+'/days',lambda host:setattr(host,'creator',(0,1000)));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',5);assert host.tree.get(K9+'/claims') is None
    m,docs,host=fresh();host.hook=on('names',K9+'/claims',lambda host:host.tree.add(K9+'/claims/foreign.claim',kind='file'));receipt=docs.run(host)
    partial(receipt,'CREATED_NOT_EMPTY',6);assert sorted(host.tree.get(K9+'/claims').children)==['foreign.claim']
    for event,path,code,left in (('fsync',VAR_LIB,'FSYNC_FAILED',1),('fsync',C3PO,'FSYNC_FAILED',2),('fsync',K9,'FSYNC_FAILED',3),('open',TOOLS,'CREATED_OPEN_FAILED',4)):
        m,docs,host=fresh()
        def hook(host,name,detail,calls,event=event,path=path):
            if name==event and detail[0]==path and ('mkdir',ORDER[left-1]) in [entry[:2] for entry in host.log]:raise OSError(errno.EIO,'injected')
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,left);assert receipt['ledger'][0]['state']=='NOT_ATTEMPTED' and host.fds=={}

def test_a_root_swapped_after_its_creation_is_seen():
    """Both roots are under a chain of root alone; a swap there (which only root can make) is still seen: the source
    root by the readback from "/", the K9 root by the check before the next mkdir in it."""
    m,docs,host=fresh()
    def swap_source(host):
        node=host.tree.get(C3PO);host.tree.get(VAR_LIB).children['source-moved']=node.children.pop('r2d2-v2-source-20261005');host.tree.add(SOURCE,mode=0o700)
    host.hook=on('mkdir',K9,swap_source);receipt=docs.run(host);partial(receipt,'READBACK_MISMATCH',8)
    m,docs,host=fresh()
    def swap_k9(host):
        node=host.tree.get(C3PO);host.tree.get(VAR_LIB).children['k9-moved']=node.children.pop('r2d2-v2-k9-20261005');host.tree.add(K9,mode=0o700)
    host.hook=on('mkdir',K9+'/days',swap_k9);receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',5)
    assert host.tree.get(K9).children=={} and sorted(host.tree.get(VAR_LIB+'/k9-moved').children)==['days','tools']

def test_failures_while_the_runner_is_written_withdraw_only_the_temporary_of_this_run():
    def raising(event,number):
        seen=[0]
        def hook(host,name,detail,calls):
            if name==event and detail[0].startswith(TOOLS+'/'):
                seen[0]+=1
                if seen[0]==1:raise OSError(number,'injected')
        return hook
    for hook,code in ((raising('write',errno.ENOSPC),'FILESYSTEM_FULL'),(raising('fsync',errno.EIO),'FSYNC_FAILED'),(raising('fstat',errno.EIO),'CREATED_STAT_FAILED'),
                      (raising('create',errno.ENOSPC),'FILESYSTEM_FULL')):
        m,docs,host=fresh();host.hook=hook;receipt=docs.run(host);partial(receipt,code,7)
        assert receipt['ledger'][0]['state']=='NOT_CREATED' and host.tree.get(TOOLS).children=={} and k4e0.classify(host,docs.go16())=='B7_SECRETS' and host.fds=={},code
    m,docs,host=fresh();host.write=lambda fd,data:0;receipt=docs.run(host);partial(receipt,'WRITE_INCOMPLETE',7)
    m,docs,host=fresh();original=host.write;host.write=lambda fd,data:original(fd,data[:500]);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(k4e0.runner_path()).content)==RUNNER

def test_failures_after_the_link_leave_the_complete_runner_and_the_receipt_says_what_is_left():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='unlink':raise OSError(errno.EIO,'injected')
    host.hook=hook;receipt=docs.run(host);partial(receipt,'TEMPORARY_REMOVAL_FAILED',9)
    assert receipt['ledger'][0]['state']=='LINKED_TEMPORARY_PRESENT' and k4e0.classify(host,docs.go16())=='D_LINKED_TEMPORARY_PRESENT'
    m,docs,host=fresh();temporary=TOOLS+'/.hostops-%s-0.partial'%docs.go16()
    def last_fsync(host,name,detail,calls):
        if name=='fsync' and detail[0]==TOOLS and ('unlink',temporary) in [entry[:2] for entry in host.log]:raise OSError(errno.EIO,'injected')
    host.hook=last_fsync;receipt=docs.run(host);partial(receipt,'FSYNC_FAILED',8)
    assert receipt['ledger'][0]['state']=='INSTALLED_NOT_DURABLE' and k4e0.classify(host,docs.go16())=='E_DELIVERED'

def test_readback_inside_the_run_catches_what_changed_after_the_runner_was_delivered():
    final=k4e0.runner_path()
    def tamper(host):host.tree.get(final).content=bytearray(RUNNER[:-1]+b'Z')
    def foreign_in_days(host):host.tree.add(K9+'/days/2026-10-06')
    def foreign_in_c3po(host):host.tree.add(C3PO+'/other')
    def mode_of_secrets(host):host.tree.get(K9+'/secrets').mode=0o755
    def foreign_in_source(host):host.tree.add(SOURCE+'/causal_list')
    def var_mode(host):host.tree.get('/var').mode=0o711
    def var_lib_mode(host):host.tree.get(VAR_LIB).mode=0o711
    for action,code,when in ((tamper,'READBACK_HASH_MISMATCH',('open',final)),(foreign_in_days,'READBACK_MISMATCH',('names',K9+'/days')),
                             (foreign_in_c3po,'READBACK_MISMATCH',('open',final)),(mode_of_secrets,'READBACK_MISMATCH',('names',K9+'/claims')),
                             (foreign_in_source,'READBACK_MISMATCH',('names',SOURCE)),(var_mode,'PARENT_REPLACED',('names',K9+'/secrets')),
                             (var_lib_mode,'PARENT_REPLACED',('names',K9+'/secrets'))):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,when=when,action=action):
            if not armed[0] and ('unlink',TOOLS+'/.hostops-%s-0.partial'%docs.go16()) in [entry[:2] for entry in host.log] and (name,detail[0] if detail else None)==when:
                armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,8);assert armed[0],code
        assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and receipt['readback'] is None

def test_the_gate_is_asked_immediately_before_every_call_that_changes_the_host():
    for c3po in (False,True):
        m,docs,host=fresh(c3po=c3po);plan,real=docs.authenticate();asked=[]
        def gate():
            asked.append(len(host.log));return real()
        receipt=docs.perform(host,gate=gate);assert receipt['status']==m.COMPLETE_STATUS
        for index,entry in enumerate(host.log):
            if entry[0] in ('mkdir','create','write','link','unlink'):assert index in asked,entry


# ---------------------------------------------------------------- crash points and expiry
def total_calls(c3po=False):
    m,docs,host=fresh(c3po=c3po);names=[]
    def hook(host,name,detail,calls):names.append(name)
    host.hook=hook;assert docs.run(host)['status']==m.COMPLETE_STATUS;return len(names),names

@pytest.mark.parametrize('c3po',[False,True])
def test_process_death_at_every_host_call_leaves_one_of_the_ordered_states_that_a_later_read_tells_apart(c3po):
    total,names=total_calls(c3po);seen=[]
    for index in range(1,total+1):
        m,docs,host=fresh(c3po=c3po);before=k4e0.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);state=k4e0.classify(host,docs.go16(),c3po_existed=c3po);seen.append(state)
        assert (state=='A_NOTHING')==(k4e0.state_of(host)==before)
        assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and (receipt['status']!='REFUSED' or state=='A_NOTHING'),(index,names[index-1],state)
    order=[state for state in k4e0.STATES if not (c3po and state=='B1_C3PO')]
    assert [order.index(state) for state in seen]==sorted(order.index(state) for state in seen),'the states only move forward'
    assert set(seen)==set(order),'every state is reached by some crash point'
    first={state:names[seen.index(state)-1] if seen.index(state) else None for state in order}
    assert all(first[state]=='mkdir' for state in order if state.startswith('B'))
    assert (first['C_TEMPORARY_ONLY'],first['D_LINKED_TEMPORARY_PRESENT'],first['E_DELIVERED'])==('create','link','unlink')

def test_expiry_or_a_reversed_clock_at_every_gate_is_a_refusal_only_while_nothing_exists():
    m,docs,host=fresh();count=[0]
    def counting():
        count[0]+=1;return 0.0
    assert docs.run(host,monotonic=counting)['status']==m.COMPLETE_STATUS;total=count[0];assert total>60
    for expired,code in ((61.0,'GO_EXPIRED'),(-1.0,'CLOCK_REVERSED')):
        states=set()
        for index in range(4,total):
            m,docs,host=fresh();before=k4e0.state_of(host);count=[0]
            def monotonic(index=index):
                count[0]+=1;return expired if count[0]==index else (0.0 if count[0]<index else 61.0)
            receipt=docs.run(host,monotonic=monotonic);state=k4e0.classify(host,docs.go16());states.add((receipt['status'],state))
            assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and receipt['code'] in (code,'GO_EXPIRED'),(index,receipt['code'])
            assert (receipt['status']=='REFUSED')==(k4e0.state_of(host)==before)==(state=='A_NOTHING') and host.fds=={} and f.sealed(receipt)
        assert {state for _,state in states}>={'A_NOTHING','B1_C3PO','B2_SOURCE_ROOT','B7_SECRETS','C_TEMPORARY_ONLY','E_DELIVERED'},states

def test_escape_after_an_effect_is_partial_and_before_any_is_a_refusal():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='mkdir' and detail[0]==SOURCE:raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    assert receipt['mutating_calls']=={'issued':2,'succeeded':1,'failed_nothing_changed':0,'uncertain':1}
    m,docs,host=fresh()
    def early(host,name,detail,calls):
        if name=='fstatvfs':raise KeyboardInterrupt()
    host.hook=early;before=k4e0.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and k4e0.state_of(host)==before


# ---------------------------------------------------------------- once per epoch: there is no second attempt
def test_second_request_after_a_complete_or_a_partial_run_is_refused_and_changes_nothing():
    m,docs,host=fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS
    again=f.Docs(docs.k,k4e0.fields(host),now=docs.now+timedelta(minutes=15));before=k4e0.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','SOURCE_ROOT_PRESENT') and k4e0.state_of(host)==before and receipt['mutating_calls']['issued']==0
    # only the K9 tree left (the source root removed by hand): the K9 root inside the now existing /var/lib/c3po refuses
    host.tree.remove(SOURCE);again=f.Docs(docs.k,k4e0.fields(host),now=docs.now+timedelta(minutes=15));before=k4e0.state_of(host)
    assert again.run(host)['code']=='K9_ROOT_PRESENT' and k4e0.state_of(host)==before
    m,docs,host=fresh();host.hook=on('mkdir',TOOLS,lambda host:setattr(host,'creator',(0,7)));assert docs.run(host)['status']==m.PARTIAL_STATUS;host.creator=(0,0);host.hook=None
    again=f.Docs(docs.k,k4e0.fields(host),now=docs.now+timedelta(minutes=15));before=k4e0.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','SOURCE_ROOT_PRESENT') and k4e0.state_of(host)==before

def test_a_run_that_died_after_creating_only_c3po_can_be_completed_by_a_new_request():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='mkdir' and detail[0]==SOURCE:raise hostemu.Death('dead')
    host.hook=hook;assert docs.run(host)['status']==m.PARTIAL_STATUS and k4e0.classify(host,docs.go16())=='B1_C3PO';host.hook=None
    again=f.Docs(docs.k,k4e0.fields(host),now=docs.now+timedelta(minutes=15));receipt=again.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['c3po_directory']['state']=='PRESENT' and receipt['c3po_directory']['found']['mode_octal']=='0700'

def test_two_requests_over_the_same_bytes_differ_only_in_what_is_signed_per_request():
    k=k4e0.K();host=f.world(k);fields=k4e0.fields(host)
    first=f.Docs(k,fields);second=f.Docs(k,fields,now=first.now+timedelta(minutes=16))
    assert first.authority['effects']==second.authority['effects'] and first.request['payload_sha256']==second.request['payload_sha256']
    assert first.run(host)['status']==k.m.COMPLETE_STATUS and second.run(host)['code']=='SOURCE_ROOT_PRESENT'


# ---------------------------------------------------------------- revision 3: the space of days/, the device of /var/lib/c3po
def test_one_floor_of_200_gib_on_the_filesystem_that_holds_both_roots():
    """214748364800 bytes = 52428800 blocks of 4096: to the byte, measured by fstatvfs on the held /var/lib/c3po when it
    exists, else on /var/lib. Nothing of the data volume counts (it is not even looked at)."""
    for blocks,ok in ((52428800,True),(52428799,False),(0,False)):
        m,docs,host=fresh();host.vfs[ROOT].f_bavail=blocks;host.vfs[hostemu.DATA_DEVICE].f_bavail=10**12;before=k4e0.state_of(host);receipt=docs.run(host)
        if ok:assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['free_bytes']==214748364800
        else:refused_untouched(receipt,host,before,'FREE_SPACE_BELOW_FLOOR');assert receipt['precheck']['free_bytes']==blocks*4096
    for c3po,where in ((False,VAR_LIB),(True,C3PO)):
        m,docs,host=fresh(c3po=c3po);receipt=docs.run(host);calls=[entry for entry in host.log if entry[0]=='fstatvfs']
        assert [entry[1] for entry in calls]==[where] and receipt['precheck']['free_bytes_measured_on']==where,calls

def test_an_existing_c3po_directory_must_be_on_the_filesystem_of_var_lib():
    m,docs,host=fresh(c3po=True);host.tree.get(C3PO).dev=hostemu.DATA_DEVICE;before=k4e0.state_of(host);receipt=docs.run(host)
    refused_untouched(receipt,host,before,'C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM')
    assert receipt['c3po_directory']=={'state':'PRESENT','found':{'type':'dir','uid':0,'gid':0,'mode_octal':'0755','links':1,'device':hostemu.DATA_DEVICE,
                                                                  'inode':host.tree.get(C3PO).ino},'created':False}
    m,docs,host=fresh(c3po=True);host.tree.get(C3PO).dev=999;assert docs.run(host)['code']=='C3PO_DIRECTORY_ON_ANOTHER_FILESYSTEM'
    m,docs,host=fresh();host.actor=(5,5);receipt=docs.run(host);assert receipt['c3po_directory']=={'state':None,'found':None,'created':False},'not looked at'


# ---------------------------------------------------------------- what the carried core rows need on E0's paths
def _after(host,event,path):
    return (event,path) in [entry[:2] for entry in host.log]
def test_walk_compares_the_group_of_every_component_and_the_lstat_with_the_descriptor():
    for path in (VAR_LIB,'/var'):
        m,docs,host=fresh();host.tree.get(path).gid=4;before=k4e0.state_of(host);refused_untouched(docs.run(host),host,before,'PARENT_IDENTITY_MISMATCH')
    m,docs,host=fresh();plan,real=docs.authenticate();done=[False]
    def gate():
        if not done[0] and host.log and host.log[-1]==('lstat',VAR_LIB):      # between the lstat of the component and its open
            done[0]=True;node=host.tree.get('/var');old=node.children.pop('lib');node.children['lib-old']=old
            host.tree.add(VAR_LIB,uid=old.uid,gid=old.gid,mode=old.mode)
        return real()
    receipt=docs.perform(host,gate=gate)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','PARENT_CHANGED_DURING_WALK','PRECHECK') and host.mutating()==[] and host.fds=={}

def test_an_ancestor_changed_after_the_precheck_is_seen_by_the_fresh_walk():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='fsync' and detail[0]==VAR_LIB and _after(host,'mkdir',C3PO):host.tree.get('/var').mode=0o777
    host.hook=hook;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',1);assert host.tree.get(SOURCE) is None

def test_a_created_name_swapped_before_its_proof_is_seen():
    m,docs,host=fresh();armed=[False]
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==SOURCE and _after(host,'mkdir',SOURCE) and not armed[0]:
            armed[0]=True;node=host.tree.get(C3PO);host.tree.get(VAR_LIB).children['moved']=node.children.pop('r2d2-v2-source-20261005')
            host.tree.add(SOURCE,mode=0o700)
    host.hook=hook;receipt=docs.run(host);partial(receipt,'CREATED_NAME_REPLACED',2)

def test_a_created_directory_with_another_mode_is_never_used():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='open' and detail[0]==TOOLS and _after(host,'mkdir',TOOLS):host.tree.get(TOOLS).mode=0o755
    host.hook=hook;receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',4)

def test_the_temporary_is_proved_before_the_link_and_before_its_removal():
    temp=lambda docs:TOOLS+'/.hostops-%s-0.partial'%docs.go16()
    # another mode, another device, a second link: proved after the write, withdrawn, never linked
    for change in (lambda node:setattr(node,'mode',0o644),lambda node:setattr(node,'dev',hostemu.DATA_DEVICE),lambda node:setattr(node,'nlink',2)):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,change=change):
            if name=='fsync' and detail[0]==temp(docs) and not armed[0]:armed[0]=True;change(host.tree.get(temp(docs)))
        host.hook=hook;receipt=docs.run(host);assert receipt['code']=='CREATED_METADATA_MISMATCH' and not _after(host,'link',temp(docs))
    # swapped or linked twice between its proof and the link: TEMPORARY_REPLACED, the temporary left and counted
    for change in ('swap','second'):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,change=change):
            if name=='lstat' and detail[0]==temp(docs) and not armed[0]:
                armed[0]=True
                if change=='second':host.tree.get(temp(docs)).nlink=2
                else:
                    node=host.tree.get(TOOLS);node.children.pop(temp(docs).rsplit('/',1)[1]);host.tree.add(temp(docs),kind='file',mode=0o600,content=b'x')
        host.hook=hook;receipt=docs.run(host);partial(receipt,'TEMPORARY_REPLACED',8)
        assert receipt['ledger'][0]['state']=='TEMPORARY_ONLY' and not _after(host,'link',temp(docs))
    # swapped between the link and its removal: never removed
    m,docs,host=fresh();armed=[False]
    def swap_before_removal(host,name,detail,calls):
        if name=='lstat' and detail[0]==temp(docs) and _after(host,'link',temp(docs)) and not armed[0]:
            armed[0]=True;node=host.tree.get(TOOLS);node.children.pop(temp(docs).rsplit('/',1)[1]);host.tree.add(temp(docs),kind='file',mode=0o600,content=b'x')
    host.hook=swap_before_removal;receipt=docs.run(host);assert receipt['code']=='TEMPORARY_REPLACED' and not _after(host,'unlink',temp(docs))
    # the fsync of tools after the link fails; the removal fails with its own errno, the first errno is kept
    m,docs,host=fresh()
    def fsync_after_link(host,name,detail,calls):
        if name=='fsync' and detail[0]==TOOLS and _after(host,'link',temp(docs)):raise OSError(errno.EIO,'injected')
    host.hook=fsync_after_link;receipt=docs.run(host);partial(receipt,'FSYNC_FAILED',9);assert receipt['ledger'][0]['state']=='LINKED_TEMPORARY_PRESENT'
    m,docs,host=fresh()
    def write_and_unlink_fail(host,name,detail,calls):
        if name=='write':raise OSError(errno.ENOSPC,'injected')
        if name=='unlink':raise OSError(errno.EIO,'injected')
    host.hook=write_and_unlink_fail;receipt=docs.run(host);row=receipt['ledger'][0]
    assert (row['code'],row['errno'],row['temporary_removal_errno'],row['state'])==('FILESYSTEM_FULL',errno.ENOSPC,errno.EIO,'TEMPORARY_ONLY')
    partial(receipt,'FILESYSTEM_FULL',8)
    # a second link to the final name appears after the removal of the temporary
    m,docs,host=fresh()
    def second_link(host,name,detail,calls):
        if name=='fsync' and detail[0]==TOOLS and _after(host,'unlink',temp(docs)):host.tree.get(k4e0.runner_path()).nlink=2
    host.hook=second_link;receipt=docs.run(host);partial(receipt,'CREATED_METADATA_MISMATCH',8);assert receipt['ledger'][0]['state']=='INSTALLED_NOT_DURABLE'

def test_tools_changed_before_the_temporary_or_before_the_link_stops_the_runner():
    temp=lambda docs:TOOLS+'/.hostops-%s-0.partial'%docs.go16()
    m,docs,host=fresh()
    def before_temporary(host,name,detail,calls):
        if name=='fsync' and detail[0]==K9 and _after(host,'mkdir',K9+'/secrets'):host.tree.get(TOOLS).mode=0o750
    host.hook=before_temporary;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',7);assert host.tree.get(TOOLS).children=={}
    m,docs,host=fresh()
    def before_link(host,name,detail,calls):
        if name=='fsync' and detail[0]==temp(docs):host.tree.get(TOOLS).mode=0o750
    host.hook=before_link;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',8);assert receipt['ledger'][0]['state']=='TEMPORARY_ONLY'

def test_the_readback_compares_identity_owner_mode_links_and_stability_of_the_runner():
    final=k4e0.runner_path()
    def copy_of(host):
        node=host.tree.get(TOOLS);node.children.pop(final.rsplit('/',1)[1]);host.tree.add(final,kind='file',mode=0o600,content=RUNNER)
    for action,code,event in ((copy_of,'READBACK_HASH_MISMATCH','lstat'),(lambda host:setattr(host.tree.get(final),'uid',7),'READBACK_HASH_MISMATCH','lstat'),
                              (lambda host:setattr(host.tree.get(final),'mode',0o644),'READBACK_HASH_MISMATCH','lstat'),
                              (lambda host:setattr(host.tree.get(final),'nlink',2),'READBACK_HASH_MISMATCH','lstat'),
                              (lambda host:setattr(host.tree.get(TOOLS),'mode',0o750),'PARENT_REPLACED','fsync'),
                              (lambda host:setattr(host.tree.get(final),'content',bytearray(b'x'*1048577)),'FILE_TOO_LARGE','lstat')):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,action=action,event=event):
            # 'lstat': the first lstat of tools after the removal of the temporary (the readback proving tools again,
            # before it opens the runner); 'fsync': the last fsync of the creation, before the readback begins
            if not armed[0] and _after(host,'unlink',TOOLS+'/.hostops-%s-0.partial'%docs.go16()) and name==event and (event=='fsync' or detail[0]==TOOLS):
                armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,8);assert armed[0]
    # changed while it is read: same bytes, another modification instant between the two fstat calls
    m,docs,host=fresh();armed=[False]
    def during(host,name,detail,calls):
        if name=='read' and detail[0]==final and not armed[0]:armed[0]=True;host.tree.get(final).mtime+=1
    host.hook=during;receipt=docs.run(host);partial(receipt,'FILE_CHANGED_DURING_READ',8)

def test_a_created_directory_replaced_by_an_identical_one_is_seen_by_the_readback():
    m,docs,host=fresh();armed=[False]
    def hook(host,name,detail,calls):
        if not armed[0] and name=='open' and detail[0]==k4e0.runner_path():
            # the old one moved out of the K9 root (so no entry count changes), an identical empty root 0700 one in its place
            armed[0]=True;node=host.tree.get(K9);host.tree.get(VAR_LIB).children['claims-old']=node.children.pop('claims');host.tree.add(K9+'/claims',mode=0o700)
    host.hook=hook;receipt=docs.run(host);partial(receipt,'READBACK_MISMATCH',8)
    assert sorted(host.tree.get(K9).children)==['claims','days','secrets','tools'] and host.tree.get(K9+'/claims').children=={}

def test_the_minimum_receipt_keeps_the_core_hash_and_a_failing_clock_still_gives_a_receipt():
    m,docs,host=fresh();receipt=docs.run(host)
    body={key:value for key,value in receipt.items() if key not in ('metadata_sha256','size_reductions')};body['directories']=[{'pad':'x'*70000}]
    reduced=m.seal(body);assert reduced['code']=='RECEIPT_REDUCED_TO_MINIMUM' and reduced['core_sha256']==m.CORE_SHA256 and f.sealed(reduced)
    # timing() never raises: a broken clock gives a null clock member, not an exception that would lose the receipt
    def broken():raise RuntimeError('broken clock')
    assert m.timing(docs.now,0.0,lambda:docs.now,broken) is None and m.timing(docs.now,0.0,broken,lambda:0.0) is None
    # and a run whose wall clock breaks after the last creation still returns a sealed receipt (clock member null)
    m,docs,host=fresh();plan,gate=docs.authenticate();bound=m.digests(*docs.raw(),docs.k.source);bound['host_binding_sha256']=plan['host_binding_sha256']
    calls=[0]
    def clock():                       # perform() reads this clock twice: at its start and for the receipt's clock member
        calls[0]+=1
        if calls[0]>=2:raise RuntimeError('broken clock')
        return docs.now
    receipt=m.perform(plan,gate,host,bound,clock,lambda:0.0,m.Effects())
    assert (receipt['status'],receipt['clock'],calls[0])==(m.COMPLETE_STATUS,None,2) and f.sealed(receipt)
