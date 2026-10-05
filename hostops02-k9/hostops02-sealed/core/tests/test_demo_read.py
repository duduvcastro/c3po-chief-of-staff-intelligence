"""The reading demonstration operation end to end on the emulated host: each item observed on its own, a failed
observation never an absence, a mismatch a finding that keeps the rest, and nothing changed on the host in any case."""
import json

import pytest

import demos
import family as f
import hostemu

LOCK=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME
def fresh(**options):
    docs,host=demos.case('selftest_read',**options);return docs.k.m,docs,host
def state_of(host):return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)

def test_complete_run_changes_nothing_and_says_what_it_ran():
    m,docs,host=fresh();before=state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['findings'])==(m.COMPLETE_STATUS,'SELFTEST_ALL_OBSERVED_ALL_EXPECTATIONS_MET',None,[])
    assert state_of(host)==before and host.mutating()==[] and receipt['writes']==0 and receipt['containers_run']==1 and receipt['mutating_calls']['issued']==0
    assert receipt['commands_started']=={'READ':13,'CONTAINER':1,'EFFECT':0} and host.fds=={} and host.lock_held(LOCK) is None
    assert sorted(receipt['items'])==['boot','containers','directory:DATA','directory:DEPLOY','directory:ETC','directory:LOCKS','environment','file','image','lock','render','verify']
    assert receipt['items']['lock']=={'state':'FREE','status':'COMPLETE'} and receipt['items']['file']['bytes_equal_signed'] is True
    assert receipt['items']['directory:DATA']['bytes_available']==13200816*4096 and receipt['items']['verify']['as_expected'] is True
    assert receipt['items']['environment']['names']=={'C3PO_BUILD_SHA':{'present':True,'equal':True},'C3PO_SERVICE_NAME':{'present':True,'equal':True}}
    effects=docs.go['effects'];assert effects['writes']==0 and effects['containers_run']==1 and effects['verify']['bind']=={'source':hostemu.DATA,'target':'/selftest','read_only':True}
    assert effects['lock']==LOCK and effects['file']['path']==hostemu.DEPLOY+'/.deploy-version' and effects['render']['override_sha256']==f.sha(demos.override())
    # no open for writing, no creating call, and the one container had only a read-only bind
    assert all(not entry[2]&hostemu.WRITE_FLAGS for entry in host.log if entry[0]=='open') and host.docker.runs[0].mounts==[{'source':hostemu.DATA,'target':'/selftest','read_only':True}]

def test_a_mismatch_is_a_finding_that_keeps_every_other_item():
    def image_moved(host):host.docker.images[0]['RepoTags']=[];host.docker.images[3]['RepoTags'].append('c3po/backend:production')
    def revision(host):host.docker.images[0]['Config']['Labels']['org.opencontainers.image.revision']='0'*40
    def stopped(host):host.docker.container(hostemu.WORKER)['State'].update(Status='exited',Running=False)
    def restarted(host):host.docker.container('c3po-api-1')['RestartCount']=2
    def stray(host):host.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'x',[]))
    def environment(host):host.docker.container(hostemu.WORKER)['Config']['Env'].remove('C3PO_SERVICE_NAME=r2d2-worker')
    def other_boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    def moved(host):host.tree.get(hostemu.DATA).ino+=1
    def deployed(host):host.tree.get(hostemu.DEPLOY+'/.deploy-version').content=bytearray(b'0'*40+b'\n')
    def render(host):host.docker.compose.base['services']['r2d2-worker']['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA']='x'
    def listing(host):host.tree.add(hostemu.DATA+'/new-entry',dev=hostemu.DATA_DEVICE)
    for prepare,code,override in ((image_moved,'IMAGE_ID_MISMATCH',None),(revision,'IMAGE_REVISION_MISMATCH',None),(stopped,'CONTAINER_NOT_RUNNING',None),
                                  (restarted,'CONTAINER_RESTARTED',None),(stray,'CONTAINER_SET_NOT_THE_SIGNED_ONE',None),(environment,'ENVIRONMENT_NOT_AS_SIGNED',None),
                                  (other_boot,'EVIDENCE_FROM_EARLIER_BOOT',None),(moved,'PARENT_IDENTITY_MISMATCH',None),(deployed,'FILE_NOT_THE_SIGNED_BYTES',None),
                                  (listing,'VERIFY_RESULT_NOT_AS_SIGNED',None)):
        m,docs,host=fresh();prepare(host);before=state_of(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'OBSERVED_ALL_EXPECTATIONS_NOT_MET') and code in receipt['findings'],code
        assert state_of(host)==before and len(receipt['items'])==12 and all(item['status']=='COMPLETE' for item in receipt['items'].values()),'every item is still in the receipt'
    m,docs,host=fresh();docs.plan['render']['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA']='7'*64;docs.chain();receipt=docs.run(host)
    assert receipt['findings']==['RENDER_NOT_AS_SIGNED'] and receipt['items']['render']['environment_equal']=={'C3PO_R2D2_V2_LIVE_POLICY_FILE':True,'C3PO_R2D2_V2_LIVE_POLICY_SHA':False}

def test_a_failed_observation_is_unavailable_with_a_constant_code_never_an_absence():
    def no_ps(host):host.docker.ps_returncode=1
    def no_image(host):host.docker.images=host.docker.images[1:]
    def no_file(host):host.tree.remove(hostemu.DEPLOY+'/.deploy-version')
    def no_lock(host):host.tree.remove(LOCK)
    def bad_render(host):host.docker.compose.config_output=b'not json'
    def link(host):host.tree.remove(hostemu.DEPLOY+'/.deploy-version');host.tree.add(hostemu.DEPLOY+'/.deploy-version',kind='symlink')
    for prepare,item,code in ((no_ps,'containers','COMMAND_FAILED'),(no_image,'image','COMMAND_FAILED'),(no_file,'file','OS_ERROR'),(no_lock,'lock','LOCK_FILE_ABSENT'),
                              (bad_render,'render','COMPOSE_RENDER_INVALID'),(link,'file','OS_ERROR')):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_OBSERVED','OBSERVATION_INCOMPLETE'),item
        assert receipt['items'][item]['status']=='UNAVAILABLE' and receipt['items'][item]['code']==code and len(receipt['items'])==12
    m,docs,host=fresh();host.lock_holder[LOCK]='EX';receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['items']['lock']['state']=='BUSY','a busy lock is an observation, reported as such'

def test_container_run_that_cannot_run_fails_or_times_out_is_reported_with_what_may_be_left():
    m,docs,host=fresh();host.hang.add(('run','--rm'));receipt=docs.run(host)
    assert receipt['items']['verify']=={'started':True,'returned':False,'returncode':None,'code':'COMMAND_TIMEOUT','container_may_still_exist':True,'status':'COMPLETE'}
    assert receipt['findings']==['VERIFY_RUN_NOT_COMPLETED'] and receipt['status']==m.PARTIAL_STATUS and receipt['containers_run']==1
    m,docs,host=fresh();host.absent.add(('run','--rm'));receipt=docs.run(host)
    assert receipt['items']['verify']['started'] is False and receipt['items']['verify']['container_may_still_exist'] is False and receipt['containers_run']==0
    m,docs,host=fresh();host.docker.on_run=lambda call:(1,b'{"status":"REFUSED"}\n');receipt=docs.run(host)
    assert (receipt['items']['verify']['returncode'],receipt['items']['verify']['as_expected'],receipt['items']['verify']['engine_failure'])==(1,False,False)
    m,docs,host=fresh();host.docker.images[0]['Id']='sha256:'+'ab'*32;receipt=docs.run(host)
    assert (receipt['items']['verify']['returncode'],receipt['items']['verify']['engine_failure'])==(125,True)
    # the container tried to write through its read-only bind: the kernel refuses, the host is unchanged
    m,docs,host=fresh();before=state_of(host)
    def writes(call):
        try:call.write('/selftest/x',b'x')
        except OSError as error:return 1,json.dumps({'errno':error.errno}).encode()+b'\n'
        return 0,b'{}\n'
    host.docker.on_run=writes;receipt=docs.run(host);assert receipt['items']['verify']['returncode']==1 and state_of(host)==before
    # with too little budget for the whole class the container is not started
    m,docs,host=fresh();budget=f.Budget(docs.now).attach(host).cost(40,'image','inspect');receipt=docs.run(host,**budget.options())
    assert receipt['items']['verify']['code']=='COMMAND_NOT_STARTED_BUDGET' and host.docker.runs==[]

def test_expiry_stops_the_run_and_keeps_what_was_observed():
    m,docs,host=fresh();budget=f.Budget(docs.now).attach(host).cost(70,'ps','-a');receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_OBSERVED','GO_EXPIRED')
    assert receipt['items']['containers']['status']=='COMPLETE' and receipt['items']['environment']=={'status':'UNAVAILABLE','code':'GO_EXPIRED'}
    assert 'render' not in receipt['items'] and 'lock' not in receipt['items'] and host.fds=={},'nothing is observed after the expiry'

def test_plan_refusals_of_the_reading_source():
    def change(path,value):
        def apply(plan):
            target=plan
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
        return apply
    for path,value,code in ((['directories'],[],'DIRECTORIES_INVALID'),(['directories',2,'open_root'],None,'CHAIN_ROW_UNSAFE'),(['directories',0,'key'],'LOCKS','DIRECTORIES_INVALID'),
                            (['image','image_id'],'c3po/backend:production','IMAGE_PLAN_INVALID'),(['containers'],['a b'],'CONTAINERS_INVALID'),
                            (['environment','container'],'not-listed','ENVIRONMENT_PLAN_INVALID'),(['environment','expected'],{'k':'v'},'ENVIRONMENT_EXPECTATION'),
                            (['verify','script_sha256'],'3'*64,'SCRIPT_NOT_THE_SIGNED_HASH'),(['verify','directory_key'],'NOPE','VERIFY_PLAN_INVALID'),
                            (['verify','target'],'/a/../b','MOUNT_INVALID'),(['render','override_sha256'],'3'*64,'OVERRIDE_NOT_THE_SIGNED_HASH'),
                            (['render','files'],['relative.yml'],'COMPOSE_FILES'),(['render','build_sha'],'x','RENDER_PLAN_INVALID'),
                            (['file','name'],'../x','FILE_PLAN_INVALID'),(['file','bytes'],0,'FILE_PLAN_INVALID'),(['lock','directory_key'],'NOPE','LOCK_PLAN_INVALID'),
                            (['evidence_boot_id_sha256'],'0'*64,'EVIDENCE_BOOT_UNBOUND')):
        m,docs,host=fresh();change(path,value)(docs.plan);docs.chain();assert f.refusal(docs.authenticate)==code,path
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['outcome'])==('REFUSED',code,'REFUSED_NOTHING_OBSERVED')

def test_receipt_is_reduced_by_flagged_steps_and_a_reduced_receipt_is_never_complete(monkeypatch):
    m,docs,host=fresh();monkeypatch.setattr(m,'RECEIPT_LIMIT',4000);receipt=docs.run(host)
    assert receipt['size_reductions']==['RECEIPT_REDUCED_TO_MINIMUM'] and receipt['status']==m.PARTIAL_STATUS and f.sealed(receipt)
    assert receipt['code']=='RECEIPT_REDUCED_TO_MINIMUM' and receipt['outcome']=='PARTIAL_OBSERVED' and receipt['core_sha256']==m.CORE_SHA256
    assert receipt['activation_performed'] is False and receipt['request_sha256']==docs.pins().request and len(f.line(receipt))<4000
    monkeypatch.setattr(m,'RECEIPT_LIMIT',9000);m2,docs,host=fresh();receipt=docs.run(host)
    assert receipt['size_reductions']==['DIRECTORY_ROWS_REDUCED_TO_COUNTS'] and (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'PARTIAL_OBSERVED')
    assert receipt['items']['directory:DATA']['observed']==3 and 'containers' in receipt['items']

def test_a_source_that_may_switch_a_unit_says_unknown_not_false_when_it_escapes(monkeypatch):
    """The core's envelope for a switching source, exercised on the writing demonstration with the flag turned on."""
    k=f.load(demos.WRITE);m=k.m;docs,host=demos.case('selftest_write');docs.authenticate();monkeypatch.setattr(m,'ACTIVATION_ALLOWED',True)
    assert f.refusal(docs.authenticate)=='REQUEST_SCOPE','documents that say false are refused by a source that switches'
    for document,code in ((docs.request,'AUTHORITY_UNBOUND'),(docs.authority,'GO_UNBOUND'),(docs.go,None)):
        document['activation_allowed']=True;docs.chain()
        if code is None:docs.authenticate()
        else:assert f.refusal(docs.authenticate)==code
    def hook(host,name,detail,calls):
        if name=='mkdir':raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert receipt['phase_reached']=='ESCAPED' and receipt['activation_performed'] is None and receipt['daemon_reload_performed'] is None
    docs,host=demos.case('selftest_write');assert docs.request['activation_allowed'] is True
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and receipt['activation_performed'] is False,'the envelope default, until the source says otherwise'
    refused=docs.run(f.Untouchable(),executor_uid=lambda:501);assert refused['activation_performed'] is False and refused['status']=='REFUSED'
