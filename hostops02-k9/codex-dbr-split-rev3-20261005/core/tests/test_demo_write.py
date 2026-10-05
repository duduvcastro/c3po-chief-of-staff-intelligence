"""The writing demonstration operation end to end on the emulated host: the order "everything is looked at, the lock,
the budget, then the effects", what each kind of failure leaves, and what the receipt says about it. This is the
integration test of the core: every part runs inside one assembled source, as it will inside a real operation."""
import copy
from datetime import timedelta
import json

import pytest

import demos
import family as f
import hostemu

K=lambda:f.load(demos.WRITE)
BASE=hostemu.DATA+'/'+demos.LEAF
LOCK=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME
def fresh(**options):
    docs,host=demos.case('selftest_write',**options);return docs.k.m,docs,host
def state_of(host):return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True)

def test_complete_run_and_the_literal_effects_the_signers_see():
    m,docs,host=fresh();plan=docs.plan;before=state_of(host);worker=host.docker.container(hostemu.WORKER)['Id']
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_CORE_SELFTEST_01',
        'parent':{'path':hostemu.DATA,'row':plan['parent'][-1],'chain_sha256':f.sha(f.canonical(plan['parent'])),'mount_point_by_device_change':hostemu.DATA},
        'open_root':hostemu.DATA,'directory':{'path':BASE,'mode_octal':'0700','expect':'ABSENT'},
        'files':[{'key':'POLICY','path':BASE+'/policy.json','sha256':f.sha(demos.POLICY),'bytes':len(demos.POLICY),'mode_octal':'0600'},
                 {'key':'OVERRIDE','path':BASE+'/compose.override.json','sha256':f.sha(demos.override()),'bytes':len(demos.override()),'mode_octal':'0600'}],
        'container':{'image_id':hostemu.BACKEND,'script_sha256':f.sha(demos.WRITE_SCRIPT),'bind':{'source':BASE,'target':'/selftest','read_only':False},
                     'arguments':['/selftest'],'creates':BASE+'/marker.json','network':'none'},
        'recreate':{'project':'c3po','env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE,BASE+'/compose.override.json'],'service':'r2d2-worker',
                    'container':hostemu.WORKER,'build_sha':hostemu.REVISION,'environment':demos.KEYS,'lock':LOCK,'lock_wait_seconds':20,
                    'lock_chain_sha256':f.sha(f.canonical(plan['recreate']['lock_directory'])),'lock_open_root':hostemu.DEPLOY},
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'activation':False}
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.COMPLETE_STATUS,'SELFTEST_ALL_EFFECTS_VERIFIED',None,'EFFECTS')
    assert receipt['mutating_calls']=={'issued':11,'succeeded':11,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==4
    assert receipt['commands_started']=={'READ':10,'CONTAINER':0,'EFFECT':2} and receipt['pre_existing_objects_modified'] is True
    assert sorted(host.tree.get(BASE).children)==['compose.override.json','marker.json','policy.json']
    assert host.docker.container(hostemu.WORKER)['Id']!=worker and host.lock_held(LOCK) is None and host.fds=={},'the lock is released and every descriptor closed'
    # the order of what changed the host
    order=[entry[0] if type(entry) is tuple else ' '.join(entry['argv'][1:3]) for entry in host.mutating()]
    assert order==['mkdir','create','write','link','unlink','create','write','link','unlink','container-write','compose-recreate','run --rm','compose --project-name']
    # and of everything: the lock is taken before the first creation and released after the last readback
    names=[entry[0] for entry in host.log];assert names.index('flock')<names.index('mkdir') and len(names)-1-names[::-1].index('flock')>names.index('compose-recreate')

def test_everything_is_looked_at_before_the_first_creation():
    """Each of these is found by the precheck: the run is REFUSED, nothing was created, nothing was started that changes anything."""
    def absent_image(host,docs):host.docker.images=[item for item in host.docker.images if item['Id']!=hostemu.BACKEND]
    def other_boot(host,docs):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    def present(host,docs):host.tree.add(BASE,dev=hostemu.DATA_DEVICE,mode=0o700)
    def moved_parent(host,docs):host.tree.get(hostemu.DATA).ino+=1
    def chmod_parent(host,docs):host.tree.get(hostemu.DATA).mode=0o775
    def no_lock(host,docs):host.tree.remove(LOCK)
    def stopped(host,docs):host.docker.container(hostemu.WORKER)['State'].update(Status='exited',Running=False)
    def other_revision(host,docs):del host.docker.compose.base['services']['r2d2-worker']['environment']['C3PO_BUILD_SHA']       # compose.yml no longer interpolates it
    def other_image(host,docs):host.docker.compose.base['services']['r2d2-worker']['image']='c3po/backend:rollback'
    def busy(host,docs):host.lock_holder[LOCK]='EX'
    def no_docker(host,docs):host.tree.remove('/usr/bin/docker')
    def hanging(host,docs):host.hang.add('docker')
    def not_root(host,docs):host.actor=(0,5)
    def listing_fails(host,docs):host.docker.ps_returncode=1
    for prepare,code in ((absent_image,'IMAGE_ABSENT_OR_UNREADABLE'),(other_boot,'EVIDENCE_FROM_EARLIER_BOOT'),(present,'DESTINATION_PRESENT'),(moved_parent,'PARENT_IDENTITY_MISMATCH'),
                         (chmod_parent,'PARENT_IDENTITY_MISMATCH'),(no_lock,'LOCK_FILE_ABSENT'),(stopped,'CONTAINER_NOT_RUNNING'),(other_revision,'RENDER_BUILD_REVISION'),
                         (other_image,'RENDER_IMAGE_CHANGED'),(busy,'DEPLOY_LOCK_BUSY'),(no_docker,'BINARY_UNAVAILABLE_OR_UNSAFE'),(hanging,'COMMAND_TIMEOUT'),
                         (not_root,'EXECUTOR_IDENTITY'),(listing_fails,'COMMAND_FAILED')):
        m,docs,host=fresh();prepare(host,docs);before=state_of(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,'PRECHECK'),code
        assert state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['issued']==0 and receipt['objects_left_by_this_run']==0
        assert host.lock_held(LOCK) is None and host.fds=={} and f.sealed(receipt)

def test_plan_refusals_are_authentication_refusals_and_nothing_is_touched():
    def change(path,value):
        def apply(plan):
            target=plan
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
        return apply
    cases=[(change(['directory_name'],'../x'),'PATH_INVALID'),(change(['directory_name'],'.hidden'),'PATH_INVALID'),(change(['open_root'],None),'CHAIN_ROW_UNSAFE'),
           (change(['parent'],None),'CHAIN_ROW_INVALID'),(change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['files'],[]),'FILES_INVALID'),
           (change(['files',0,'sha256'],'3'*64),'FILE_BYTES_NOT_THE_SIGNED_HASH'),(change(['files',0,'bytes'],1),'FILE_BYTES_NOT_THE_SIGNED_HASH'),
           (change(['files',0,'content_b64'],'not base64!'),'FILE_BYTES_NOT_THE_SIGNED_HASH'),(change(['files',0,'mode'],0o666),'FILES_INVALID'),
           (change(['files',1,'name'],'policy.json'),'FILES_INVALID'),(change(['container','image_id'],'c3po/backend:production'),'CONTAINER_PLAN_INVALID'),
           (change(['container','script_sha256'],'4'*64),'SCRIPT_NOT_THE_SIGNED_HASH'),(change(['container','arguments'],['; rm -rf /']),'RUN_COMMAND_INVALID'),
           (change(['container','arguments'],None),'RUN_COMMAND_INVALID'),(change(['container','target'],'/'),'MOUNT_INVALID'),
           (change(['recreate','service'],'api'),'RECREATE_PLAN_INVALID'),(change(['recreate','build_sha'],'development'),'RECREATE_PLAN_INVALID'),
           (change(['recreate','files'],[]),'COMPOSE_FILES'),(change(['recreate','files'],None),'COMPOSE_FILES'),(change(['recreate','project'],'C3PO'),'COMPOSE_PROJECT'),
           (change(['recreate','environment'],{'KEY':'a b'}),'ENVIRONMENT_EXPECTATION'),(change(['recreate','lock_wait_seconds'],21),'RECREATE_PLAN_INVALID'),
           (change(['recreate','lock_open_root'],None),'CHAIN_ROW_UNSAFE'),(change(['recreate','override_key'],'NO_SUCH_FILE'),'RECREATE_PLAN_INVALID')]
    for apply,code in cases:
        m,docs,host=fresh();apply(docs.plan);docs.chain()
        assert f.refusal(docs.authenticate)==code,code
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'AUTHENTICATION')

def test_optional_steps_are_signed_as_absent_and_not_run():
    m,docs,host=fresh(container=False,recreate=False);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['commands_started']=={'READ':0,'CONTAINER':0,'EFFECT':0} and host.commands==[]
    assert docs.go['effects']['container'] is None and docs.go['effects']['recreate'] is None and receipt['objects_left_by_this_run']==3
    assert not [entry for entry in host.log if entry[0] in ('flock','run')]
    m,docs,host=fresh(recreate=False);receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and receipt['commands_started']['EFFECT']==1 and receipt['recreate'] is None

# ---------------------------------------------------------------- the budget: the last refusal before the first effect
def timed(seconds=0.0,**options):
    m,docs,host=fresh(**options);budget=f.Budget(docs.now,seconds).attach(host);return m,docs,host,budget

def test_run_refuses_before_the_first_effect_when_the_effects_would_not_fit():
    """The effects need 20 (script) + 30 (recreate) + 4 (reserve) + 2 (files) = 56 s. Reads that leave less refuse."""
    m,docs,host,budget=timed(0.5);receipt=docs.run(host,**budget.options())                 # five reads before the lock: 2.5 s, 57.5 s left
    assert receipt['status']==m.COMPLETE_STATUS
    m,docs,host,budget=timed(1.0);before=state_of(host);receipt=docs.run(host,**budget.options())             # 5 s of reads: 55 s left
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','LOCK_NOT_TAKEN_BUDGET','PRECHECK') and state_of(host)==before and host.mutating()==[]
    m,docs,host,budget=timed(0.5,recreate=False);before=state_of(host);budget.cost(40,'image','inspect');receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT') and state_of(host)==before

def test_lock_wait_is_bounded_by_the_signed_seconds_and_by_what_the_effects_need():
    m,docs,host,budget=timed(0.0);host.lock_holder[LOCK]='EX';host.lock_released_after=8;receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['lock_attempts']==9 and host.paused==2.0
    m,docs,host,budget=timed(0.0);host.lock_holder[LOCK]='EX';before=state_of(host);receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and 3.5<=host.paused<=4.0 and state_of(host)==before,'60 - 56 = 4 s of wait, not the signed 20'
    m,docs,host,budget=timed(0.0,container=False);host.lock_holder[LOCK]='EX';receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and 19.5<=host.paused<=20.0,'with 36 s of effects the signed 20 s is the limit'

def test_an_effect_that_does_not_fit_any_more_is_not_started_and_the_run_is_partial_only_for_what_exists():
    m,docs,host,budget=timed(0.0);budget.cost(28.0,'run','--rm');receipt=docs.run(host,**budget.options())     # the script took 28 s: 32 s left, the recreate needs 34
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','COMMAND_NOT_STARTED_BUDGET')
    assert receipt['recreate']=={'state':'NOT_STARTED','code':'COMMAND_NOT_STARTED_BUDGET','returncode':None,'recreated':False}
    assert receipt['mutating_calls']=={'issued':11,'succeeded':10,'failed_nothing_changed':1,'uncertain':0} and receipt['objects_left_by_this_run']==4
    assert not [entry for entry in host.commands if 'up' in entry['argv']] and receipt['container']['state']=='DONE_VERIFIED'

# ---------------------------------------------------------------- what each failure of an effect leaves
def test_container_that_fails_wrongly_or_times_out():
    def engine(call):return 125,b''
    def refuses(call):return 1,b'{"status":"REFUSED"}\n'
    def lies(call):return 0,f.canonical({'created':'marker.json','status':'DONE'})+b'\n'            # says done, created nothing
    def two_lines(call):
        call.write('/selftest/marker.json',b'{}');return 0,b'{"status":"DONE","created":"marker.json"}\nextra\n'
    def wrong_mode(call):
        call.write('/selftest/marker.json',b'{}',mode=0o644);return 0,f.canonical({'created':'marker.json','status':'DONE'})+b'\n'
    for behaviour,state,code,count in ((engine,'NOTHING_CREATED','SCRIPT_FAILED_NOTHING_CREATED',('failed_nothing_changed',1)),
                                       (refuses,'NOTHING_CREATED','SCRIPT_FAILED_NOTHING_CREATED',('failed_nothing_changed',1)),
                                       (lies,'NOTHING_CREATED','SCRIPT_FAILED_NOTHING_CREATED',('failed_nothing_changed',1)),
                                       (two_lines,'UNCERTAIN','SCRIPT_RESULT_NOT_VERIFIED',('uncertain',1)),(wrong_mode,'UNCERTAIN','SCRIPT_RESULT_NOT_VERIFIED',('uncertain',1))):
        m,docs,host=fresh();host.docker.on_run=behaviour;worker=host.docker.container(hostemu.WORKER)['Id'];receipt=docs.run(host)
        assert (receipt['status'],receipt['code'],receipt['container']['state'])==(m.PARTIAL_STATUS,code,state),behaviour.__name__
        assert receipt['mutating_calls'][count[0]]==count[1] and receipt['recreate'] is None and host.docker.container(hostemu.WORKER)['Id']==worker,'the recreate is not attempted'
    for group in ('hang','hang_after'):
        m,docs,host=fresh();getattr(host,group).add(('run','--rm'));receipt=docs.run(host)
        assert (receipt['status'],receipt['code'],receipt['container']['state'])==(m.PARTIAL_STATUS,'COMMAND_TIMEOUT','UNCERTAIN') and receipt['mutating_calls']['uncertain']==1
    m,docs,host=fresh();host.absent.add(('run','--rm'));receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['container']['state'])==(m.PARTIAL_STATUS,'COMMAND_NOT_STARTED','NOT_STARTED') and receipt['mutating_calls']['uncertain']==0

def test_recreate_that_fails_cleanly_fails_after_its_effect_or_times_out():
    # compose says no and the container is the same one: failed, nothing changed by it
    m,docs,host=fresh();host.docker.compose.up_returncode=1;host.docker.compose.up_effect=False;worker=host.docker.container(hostemu.WORKER)['Id'];receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'RECREATE_FAILED_CONTAINER_UNCHANGED') and receipt['recreate']['state']=='NOT_RECREATED'
    assert host.docker.container(hostemu.WORKER)['Id']==worker and receipt['mutating_calls']=={'issued':11,'succeeded':10,'failed_nothing_changed':1,'uncertain':0}
    assert receipt['pre_existing_objects_modified'] is False
    # compose says no but the container was replaced: never "nothing changed"
    m,docs,host=fresh();host.docker.compose.up_returncode=1;receipt=docs.run(host)
    assert (receipt['status'],receipt['recreate']['state'],receipt['recreate']['recreated'])==(m.PARTIAL_STATUS,'UNCERTAIN',True) and receipt['mutating_calls']['uncertain']==1
    assert receipt['pre_existing_objects_modified'] is True
    # the new container restarts in a loop, or lacks a signed value: recreated, not verified
    def loops(compose,new):new['RestartCount']=3;new['State'].update(Status='restarting')
    def other_value(compose,new):new['Config']['Env']=[item for item in new['Config']['Env'] if not item.startswith('C3PO_R2D2_V2_LIVE_POLICY_SHA=')]+['C3PO_R2D2_V2_LIVE_POLICY_SHA='+'6'*64]
    def touches_another(compose,new):compose.docker.containers[0]['State']['Status']='exited'
    for after_up,member in ((loops,'restarts'),(other_value,'environment_as_signed'),(touches_another,'others_unchanged')):
        m,docs,host=fresh();host.docker.compose.after_up=after_up;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,'RECREATE_NOT_VERIFIED','UNCERTAIN'),member
        assert receipt['recreate'][member]==(3 if member=='restarts' else False) and receipt['mutating_calls']['uncertain']==1
    # a timeout: unknown whatever the readback shows, and whether or not the effect happened
    for group,recreated in (('hang',False),('hang_after',True)):
        m,docs,host=fresh();getattr(host,group).add(('compose','up'));receipt=docs.run(host)
        assert (receipt['status'],receipt['code'],receipt['recreate']['state'],receipt['recreate']['recreated'])==(m.PARTIAL_STATUS,'COMMAND_TIMEOUT','UNCERTAIN',recreated)
        assert receipt['mutating_calls']=={'issued':11,'succeeded':10,'failed_nothing_changed':0,'uncertain':1}
    # something else changed a container while the files were being written: the recreate is not started
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='container-write':pass
    original=host.docker.on_run
    def run_and_disturb(call):
        result=original(call);host.docker.containers[0]['State']['Status']='exited';return result
    host.docker.on_run=run_and_disturb;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,'CONTAINER_SET_CHANGED','NOT_STARTED') and not [entry for entry in host.commands if 'up' in entry['argv']]

def test_lock_is_released_whatever_happens_and_no_descriptor_is_left():
    for prepare in (lambda host:None,lambda host:host.hang_after.add(('compose','up')),lambda host:host.hang.add(('run','--rm')),lambda host:setattr(host,'readonly',True)):
        m,docs,host=fresh();prepare(host);docs.run(host);assert host.lock_held(LOCK) is None and host.fds=={} and host.locks=={}

def test_receipt_never_carries_a_value_of_the_environment_file_and_fits_the_limit():
    for prepare in (lambda host:None,lambda host:host.docker.compose.__setattr__('up_returncode',1),lambda host:host.lock_holder.__setitem__(LOCK,'EX')):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host);line=f.line(receipt)
        assert hostemu.SECRET.encode() not in line and b'never-emit' not in line and len(line)<=m.RECEIPT_LIMIT and f.sealed(receipt)
        assert receipt['secret_bytes_in_receipt'] is False and demos.POLICY not in line,'the bytes delivered are named by hash, not carried'

def test_escape_after_an_effect_is_partial_and_before_any_is_a_refusal():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='mkdir':raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1},'a call that was issued and never settled is uncertain'
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='run':raise KeyboardInterrupt()
    host.hook=hook;receipt=docs.run(host);assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT')
