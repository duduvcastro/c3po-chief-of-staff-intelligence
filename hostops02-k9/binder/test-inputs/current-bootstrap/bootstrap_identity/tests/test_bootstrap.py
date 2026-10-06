import copy,errno,json,os,stat,subprocess,sys
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
import fixtures as fx


def test_full_positive_observes_identity_and_creates_only_durable_epoch_claim():
    docs,host=fx.case();before=host.tree.snapshot();receipt=docs.run(host);m=docs.k.m
    assert receipt['status']==m.COMPLETE_STATUS,receipt
    assert receipt['outcome']==m.COMPLETE_OUTCOME and fx.f.sealed(receipt)
    assert receipt['boot_id_sha256']==fx.f.BOOT_SHA
    assert receipt['items']['worker']['container_id']==host.docker.container('c3po-r2d2-worker-1')['Id']
    assert receipt['claim']['state']=='VERIFIED' and receipt['claim']['usage_consumed'] is True
    assert all(receipt['claim'][name] is True for name in ('file_fsync','directory_fsync','readback_verified','parent_stable'))
    assert receipt['items']['directory:SECRETS']['entries']==0
    assert receipt['items']['directory:EMITTER']['absence_confirmed'] is True
    assert receipt['items']['secret:EMITTER/password']['code']=='ABSENT_PARENT_CONFIRMED'
    path=receipt['claim']['path'];node=host.tree.get(path)
    assert (node.kind,node.uid,node.gid,node.mode,node.nlink)==('file',0,0,0o600,1)
    assert json.loads(node.content)['request_sha256']==fx.sha(docs.raw()[0])
    assert before!=host.tree.snapshot()
    assert not host.docker.runs
    creates=[call for call in fx.mutations(host) if call[0]=='create']
    assert len(creates)==1 and creates[0][1]==path
    assert not [call for call in host.log if call[0] in ('unlink','mkdir','link','rename','chmod','chown')]
    opened_or_read=[call[1] for call in host.log if call[0] in ('open','read')]
    assert not {m.SOURCE_PATHS[1],m.SOURCE_PATHS[4]}&set(opened_or_read)
    assert not any(path.endswith(('/provider.env','/risk-db.env','/emitter/password')) for path in opened_or_read)
    assert fx.CANARY not in fx.f.line(receipt).decode()


def test_two_distinct_go_hashes_share_the_epoch_claim_and_second_cannot_write():
    docs,host=fx.case();first=docs.run(host);assert first['status']==docs.k.m.COMPLETE_STATUS
    second=fx.f.Docs(docs.k,copy.deepcopy(fx.fields(docs.k,host)),now=fx.NOW)
    second.authority['owner_evidence']='SYNTHETIC_DISTINCT_OWNER_RECORD';second.chain()
    assert docs.pins().go!=second.pins().go
    before=host.tree.snapshot();count=len(fx.mutations(host));receipt=second.run(host)
    assert receipt['status']=='REFUSED' and receipt['code']=='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',receipt
    assert receipt['claim']['key']==first['claim']['key'] and receipt['claim']['state']=='EXISTING'
    assert receipt['nothing_changed_by_this_run'] is True
    assert host.tree.snapshot()==before and len(fx.mutations(host))==count


@pytest.mark.parametrize('name', ['emitter','provider.env','risk-db.env','unrelated'])
def test_any_existing_entry_in_secrets_refuses_before_claim(name):
    docs,host=fx.case();host.tree.add(docs.k.m.K9_PLACEMENT['secrets']+'/'+name,kind='symlink' if name=='emitter' else 'file',mode=0o600)
    before=host.tree.snapshot();receipt=docs.run(host)
    assert receipt['status']=='REFUSED' and receipt['code']=='SECRETS_DIRECTORY_NOT_EMPTY'
    assert receipt['claim']['state']=='NOT_ATTEMPTED' and not fx.mutations(host)
    assert host.tree.snapshot()==before


@pytest.mark.parametrize('err', [errno.EACCES,errno.EIO,errno.ENOTDIR])
def test_absence_io_error_is_unavailable_not_confirmed_absence(err):
    docs,host=fx.case();path=docs.k.m.K9_PLACEMENT['emitter']
    def hook(host,name,detail,calls):
        if name=='lstat' and detail[0]==path:raise OSError(err,'synthetic failure')
    host.hook=hook;receipt=docs.run(host)
    assert receipt['status']=='REFUSED' and receipt['code']=='OS_ERROR',receipt
    assert receipt['items']['directory:EMITTER']['status']=='UNAVAILABLE'
    assert receipt['items']['directory:EMITTER']['errno']==err
    assert receipt['claim']['state']=='NOT_ATTEMPTED' and not fx.mutations(host)


@pytest.mark.parametrize('field,value', [('mode','POLICY'),('slot','SPARE'),('epoch','OTHER')])
def test_other_mode_slot_epoch_cannot_reach_host(field,value):
    docs,host=fx.case();docs.plan[field]=value;docs.chain();receipt=docs.run(fx.f.Untouchable())
    assert receipt['status']=='REFUSED' and receipt['phase_reached']=='AUTHENTICATION'


@pytest.mark.parametrize('change', ['boot','worker_image','worker_running','live','policy','release','runner','source_rows','parent_inode','parent_owner','parent_mode'])
def test_changed_identity_files_or_signed_parents_refuse_without_effect(change):
    docs,host=fx.case();m=docs.k.m
    if change=='boot':docs.plan['evidence_boot_id_sha256']='12'*32;docs.chain()
    elif change=='worker_image':host.docker.container('c3po-r2d2-worker-1')['Image']=fx.hostemu.OTHER
    elif change=='worker_running':host.docker.container('c3po-r2d2-worker-1')['State']['Running']=False
    elif change=='live':host.docker.container('c3po-r2d2-worker-1')['Config']['Env']=[s for s in host.docker.container('c3po-r2d2-worker-1')['Config']['Env'] if not s.startswith('C3PO_R2D2_V2_LIVE_POLICY_SHA=')]
    elif change in ('policy','release'):host.tree.get((fx.POLICY_DIRECTORY+'/policy.json') if change=='policy' else (fx.RELEASE_DIRECTORY+'/release.CERTIFIED.json')).content.extend(b'x')
    elif change=='runner':host.tree.get(m.K9_PLACEMENT['tools']+'/k9_runner-'+fx.sha(fx.RUNNER)+'.py').content.extend(b'x')
    elif change=='source_rows':host.tree.get(m.SOURCE_PATHS[1]).ino+=1
    elif change=='parent_inode':host.tree.get(m.K9_PLACEMENT['claims']).ino+=1
    elif change=='parent_owner':host.tree.get(m.K9_PLACEMENT['claims']).uid=1000
    elif change=='parent_mode':host.tree.get(m.K9_PLACEMENT['claims']).mode=0o755
    before=host.tree.snapshot();receipt=docs.run(host)
    assert receipt['status']=='REFUSED',receipt
    assert receipt['claim']['state']=='NOT_ATTEMPTED' and not fx.mutations(host)
    assert host.tree.snapshot()==before


@pytest.mark.parametrize('stage', ['create','write','file_fsync','directory_fsync'])
def test_unknown_or_io_failure_during_claim_is_consumed_partial_never_unlinked(stage):
    docs,host=fx.case();m=docs.k.m;path=m.K9_PLACEMENT['claims']+'/'+m.claim_name()
    def hook(host,name,detail,calls):
        target=(name=='create' and stage=='create') or (name=='write' and stage=='write') or (name=='fsync' and stage=='file_fsync' and detail[0]==path) or (name=='fsync' and stage=='directory_fsync' and detail[0]==m.K9_PLACEMENT['claims'])
        if target:raise OSError(errno.EIO,'synthetic unknown result')
    host.hook=hook;receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']==m.PARTIAL_OUTCOME,receipt
    assert receipt['claim']['usage_consumed'] is True and receipt['claim']['possible_creation'] is True
    assert receipt['claim']['state']!='VERIFIED' and receipt['claim']['errno']==errno.EIO
    assert receipt['dependents_hold'] is True and receipt['nothing_changed_by_this_run'] is False
    assert not [call for call in host.log if call[0]=='unlink']
    if stage!='create':assert host.tree.get(path) is not None


def test_create_can_raise_after_creating_and_still_reports_uncertainty():
    docs,host=fx.case();create=host.create
    def uncertain(*args,**kwargs):
        fd=create(*args,**kwargs);host.close(fd);raise OSError(errno.EIO,'synthetic postcreate failure')
    host.create=uncertain;receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['claim']['state']=='CREATE_UNCERTAIN'
    assert receipt['claim']['created_by_this_run'] is None and receipt['claim']['usage_consumed'] is True
    assert host.tree.get(receipt['claim']['path']) is not None
    assert not [call for call in host.log if call[0]=='unlink']


def test_claim_race_eexist_is_proven_no_effect_for_losing_run():
    docs,host=fx.case();m=docs.k.m;path=m.K9_PLACEMENT['claims']+'/'+m.claim_name()
    def race(host,name,detail,calls):
        if name=='create':host.tree.add(path,kind='file',mode=0o600,content=b'SYNTHETIC_WINNER')
    host.hook=race;receipt=docs.run(host)
    assert receipt['status']=='REFUSED' and receipt['code']=='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',receipt
    assert receipt['claim']['possible_creation'] is False and receipt['claim']['usage_consumed'] is True
    assert bytes(host.tree.get(path).content)==b'SYNTHETIC_WINNER'
    assert not [call for call in host.log if call[0] in ('write','fsync','unlink')]


def test_claim_metadata_mismatch_is_left_consumed_without_chmod_repair():
    docs,host=fx.case();host.mask=0o777;receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['code']=='CLAIM_METADATA_INVALID'
    assert host.tree.get(receipt['claim']['path']).mode==0
    assert receipt['claim']['usage_consumed'] is True
    assert not [call for call in host.log if call[0] in ('chmod','unlink','write','fsync')]


def test_native_exclusive_create_between_threads_has_exactly_one_winner(tmp_path):
    docs,_=fx.case();native=docs.k.m.NativeClaim();barrier=Barrier(2);parent=os.open(str(tmp_path),os.O_RDONLY|os.O_DIRECTORY)
    def contender():
        barrier.wait()
        try:fd=native.create(docs.k.m.claim_name(),docs.k.m.CLAIM_FLAGS,0o600,parent)
        except FileExistsError:return 'REFUSED'
        else:os.close(fd);return 'CREATED'
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:contender(),range(2)))
    finally:os.close(parent)
    assert sorted(results)==['CREATED','REFUSED']
    assert stat.S_IMODE((tmp_path/docs.k.m.claim_name()).stat().st_mode)==0o600


def test_payload_carries_own_core_and_no_unlink_primitive():
    docs,_=fx.case();m=docs.k.m
    assert 'claim' in m.CORE_PARTS and 'files' not in m.CORE_PARTS
    assert not hasattr(m.Native(),'unlink') and not hasattr(m.Native(),'mkdir')
    assert m.WRITES_ALLOWED is True and m.ACTIVATION_ALLOWED is False
    assert m.DATES==('2026-10-06',)

@pytest.mark.parametrize('name',['C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA','C3PO_BUILD_SHA'])
@pytest.mark.parametrize('same_value',[True,False])
def test_duplicate_approved_live_or_build_name_refuses_before_claim(name,same_value):
    docs,host=fx.case();worker=host.docker.container('c3po-r2d2-worker-1')
    original=next(value for value in worker['Config']['Env'] if value.startswith(name+'='))
    worker['Config']['Env'].append(original if same_value else name+'=SYNTHETIC_DIFFERENT_VALUE')
    receipt=docs.run(host)
    assert receipt['status']=='REFUSED',receipt
    assert receipt['items']['worker_environment']['names'][name]['equal'] is False
    assert receipt['claim']['state']=='NOT_ATTEMPTED' and not fx.mutations(host)


@pytest.mark.parametrize('change',['worker','environment','boot','secrets','policy','release','runner','source','floor','claims_parent'])
def test_change_during_claim_fsync_cannot_report_complete(change):
    docs,host=fx.case();m=docs.k.m;claims=m.K9_PLACEMENT['claims'];changed=[]
    def hook(host,name,detail,calls):
        if name!='fsync' or detail[0]!=claims or changed:return
        changed.append(True)
        if change=='worker':host.docker.container('c3po-r2d2-worker-1')['Id']='12'*32
        elif change=='environment':host.docker.container('c3po-r2d2-worker-1')['Config']['Env'].append('C3PO_BUILD_SHA=BAD')
        elif change=='boot':host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'11111111-2222-3333-4444-555555555555\n')
        elif change=='secrets':host.tree.add(m.K9_PLACEMENT['secrets']+'/provider.env',kind='file',mode=0o600,content=b'SYNTHETIC')
        elif change=='policy':host.tree.get(fx.POLICY_DIRECTORY+'/policy.json').content.extend(b'x')
        elif change=='release':host.tree.get(fx.RELEASE_DIRECTORY+'/release.CERTIFIED.json').content.extend(b'x')
        elif change=='runner':host.tree.get(m.K9_PLACEMENT['tools']+'/k9_runner-'+fx.sha(fx.RUNNER)+'.py').content.extend(b'x')
        elif change=='source':host.tree.get(m.SOURCE_PATHS[1]).ino+=1
        elif change=='floor':host.vfs[fx.hostemu.ROOT_DEVICE].f_bavail=1
        elif change=='claims_parent':host.tree.get(claims).ino+=1
    host.hook=hook;receipt=docs.run(host)
    assert changed and receipt['status']==m.PARTIAL_STATUS,receipt
    assert receipt['claim']['created_by_this_run'] is True and receipt['claim']['usage_consumed'] is True
    assert receipt['dependents_hold'] is True and receipt['expectations_met'] is False
    assert not [call for call in host.log if call[0]=='unlink']


def test_final_clock_failure_after_cleanup_keeps_consumed_claim_and_holds():
    docs,host=fx.case();m=docs.k.m;path=m.K9_PLACEMENT['claims']+'/'+m.claim_name()
    def clock():
        if host.tree.get(path) is not None and not host.fds:raise OSError(errno.EIO,'synthetic clock failure')
        return fx.NOW
    receipt=docs.run(host,clock=clock)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['code']=='BOOTSTRAP_FINAL_CLOCK_INVALID',receipt
    assert receipt['clock'] is None and receipt['claim']['state']=='VERIFIED'
    assert receipt['items']['final_clock_failure']['errno']==errno.EIO
    assert receipt['dependents_hold'] is True and receipt['nothing_changed_by_this_run'] is False


def test_zero_byte_write_leaves_claim_consumed_and_never_repairs():
    docs,host=fx.case();host.write=lambda fd,data:0;receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['code']=='CLAIM_WRITE_INCOMPLETE'
    assert receipt['claim']['state']=='CREATED' and receipt['claim']['usage_consumed'] is True
    assert host.tree.get(receipt['claim']['path']) is not None
    assert not [call for call in host.log if call[0]=='unlink']


def test_claim_close_failure_is_not_silently_ignored():
    docs,host=fx.case();original=host.close;path=docs.k.m.K9_PLACEMENT['claims']+'/'+docs.k.m.claim_name()
    def close(fd):
        if host.path_of(fd)==path and host.fds[fd][1]&os.O_WRONLY:raise OSError(errno.EIO,'synthetic close failure')
        return original(fd)
    host.close=close;receipt=docs.run(host)
    assert receipt['status']==docs.k.m.PARTIAL_STATUS and receipt['code']=='CLAIM_DESCRIPTOR_CLOSE_FAILED'
    assert receipt['claim']['close_error']['errno']==errno.EIO
    assert receipt['claim']['state']!='VERIFIED' and receipt['dependents_hold'] is True


@pytest.mark.parametrize('reverses',['wall','monotonic','submillisecond'])
def test_final_clock_cannot_regress_after_last_successful_gate(reverses):
    docs,host=fx.case();m=docs.k.m;path=m.K9_PLACEMENT['claims']+'/'+m.claim_name()
    def clock():
        seconds=10.0001 if host.tree.get(path) is not None else 0
        if seconds and not host.fds and reverses=='wall':seconds=5
        return fx.NOW+timedelta(seconds=seconds)
    def mono():
        seconds=10.0001 if host.tree.get(path) is not None else 0
        if seconds and not host.fds and reverses=='monotonic':seconds=5
        if seconds and not host.fds and reverses=='submillisecond':seconds=10.0000
        return seconds
    receipt=docs.run(host,clock=clock,monotonic=mono)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['code']=='BOOTSTRAP_FINAL_CLOCK_INVALID',receipt
    assert receipt['claim']['state']=='VERIFIED' and receipt['claim']['usage_consumed'] is True
    assert receipt['dependents_hold'] is True and receipt['expectations_met'] is False
    assert receipt['clock']['monotonic_elapsed_ms']>=0


def test_process_death_after_durable_native_claim_does_not_reopen_epoch_slot(tmp_path):
    docs,_=fx.case();m=docs.k.m;name=m.claim_name();raw=b'SYNTHETIC_DURABLE_CLAIM'
    program="""import os,runpy,sys
module=runpy.run_path(sys.argv[1]);native=module['NativeClaim']()
parent=os.open(sys.argv[2],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
fd=native.create(sys.argv[3],module['CLAIM_FLAGS'],0o600,parent)
assert native.write(fd,b'SYNTHETIC_DURABLE_CLAIM')==len(b'SYNTHETIC_DURABLE_CLAIM')
native.fsync(fd);native.fsync(parent)
os._exit(73)
"""
    result=subprocess.run([sys.executable,'-I','-B','-c',program,str(fx.DIRECTORY/'build'/'bootstrap_identity.py'),str(tmp_path),name],capture_output=True,timeout=20)
    assert result.returncode==73,(result.stdout,result.stderr)
    parent=os.open(str(tmp_path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        with pytest.raises(FileExistsError) as failure:m.NativeClaim().create(name,m.CLAIM_FLAGS,0o600,parent)
        assert failure.value.errno==errno.EEXIST
    finally:os.close(parent)
    assert (tmp_path/name).read_bytes()==raw
    assert stat.S_IMODE((tmp_path/name).stat().st_mode)==0o600


@pytest.mark.parametrize('after_claim',[False,True])
def test_command_timeout_refuses_or_holds_according_to_claim_effect(after_claim):
    docs,host=fx.case();m=docs.k.m;path=m.K9_PLACEMENT['claims']+'/'+m.claim_name()
    original=host.run
    def run(*args,**kwargs):
        if (host.tree.get(path) is not None)==after_claim:raise m.Refused('COMMAND_TIMEOUT')
        return original(*args,**kwargs)
    host.run=run;receipt=docs.run(host)
    assert receipt['code']=='COMMAND_TIMEOUT',receipt
    assert receipt['commands_started']['READ']>0
    assert receipt['dependents_hold'] is True and receipt['expectations_met'] is False
    if after_claim:
        assert receipt['status']==m.PARTIAL_STATUS and receipt['claim']['usage_consumed'] is True
        assert host.tree.get(path) is not None and not receipt['nothing_changed_by_this_run']
    else:
        assert receipt['status']=='REFUSED' and receipt['nothing_changed_by_this_run'] is True
        assert receipt['claim']['state']=='NOT_ATTEMPTED' and not fx.mutations(host)


def test_native_runner_timeout_reaps_the_started_local_process(monkeypatch):
    docs,_=fx.case();m=docs.k.m;real=m.subprocess.Popen;started=[]
    def launch(*args,**kwargs):
        process=real(*args,**kwargs);started.append(process);return process
    monkeypatch.setattr(m.subprocess,'Popen',launch)
    with pytest.raises(m.Refused,match='^COMMAND_TIMEOUT$'):
        m.NativeRunner().run([sys.executable,'-I','-B','-c','import time;time.sleep(30)'],lambda:60,0.08)
    assert len(started)==1 and started[0].poll() is not None
    assert started[0].returncode<0
