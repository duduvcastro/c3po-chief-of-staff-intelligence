"""K9R's signed plan: every refusal of validate_plan (run by the dispatcher before any claim), the refusals perform
makes from the bytes before it observes anything (the window of D), the effects against independently written
literals, the success criterion per mode at both layers, and the constants of the frozen interface pinned by value."""
import copy
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

import family as f
import hostemu
import k9r

refusal=f.refusal
def one(operation='collect_result',**options):
    docs,host=k9r.case(operation,**options);return docs.k.m,docs,host
def refused(docs,code):
    docs.chain();assert refusal(docs.authenticate)==code

# ---------------------------------------------------------------- the frozen interface, pinned by value
def test_static_constants_of_the_interface_are_the_frozen_ones():
    m=f.load(k9r.DIRECTORY).m
    assert m.OPERATION=='GO_READONLY_HOSTOPS02_K9_PHASE_READ_01' and m.PLAN_SCHEMA=='HOSTOPS02_K9_PHASE_READ_PLAN_V1'
    assert m.WRITES_ALLOWED is False and m.ACTIVATION_ALLOWED is False and m.DATE_CLASS=='READ' and m.MAX_GATE_SPAN_SECONDS==3600
    assert m.K9_EPOCH=='R2D2-V2-SHADOW-2026-10-05' and m.K9_DAYS==('2026-10-06','2026-10-07','2026-10-08','2026-10-09')
    assert m.K9_NOTE_SHA256==k9r.NOTE and m.K9_PACKAGE_SHA256==k9r.PACKAGE and m.K9_CODE_REVISION=='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
    assert m.K9_OPERATIONS_SHA256=='bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'
    assert m.K9_PLACEMENT==k9r.PLACEMENT and m.K9_PARENT_CHAINS==k9r.CHAINS
    assert {name:tuple(row) for name,row in m.K9_READ_OPERATIONS.items()}==k9r.READ
    assert m.K9_PACKAGED_PHASES=={'acquire_launch':'acquire','execute_launch':'execute'}
    assert m.K9_READINESS_RULE=={'numerator':95,'denominator':100,'minimum_eligible':4000} and m.K9_PROBE_TIMEOUT_SECONDS==36 and m.K9_PROBE_ALARM_SECONDS==34
    assert m.K9_PROBE_PREFIX==['run','--rm','-i','--pull','never','--init','--user','0:0','--network','bridge','--read-only','--cap-drop','ALL',
                               '--security-opt','no-new-privileges','--memory','2g','--pids-limit','256',
                               '--env-file','/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env',
                               '--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true']
    assert set(m.COMMANDS)=={'image','container','container_environment','launched','probe'}
    assert m.COMMANDS['probe']['kind']=='CONTAINER' and m.COMMANDS['probe']['class']=='RUN' and m.COMMANDS['probe']['stdin'] is True
    assert all(row['kind']=='READ' and row['class']=='QUICK' for name,row in m.COMMANDS.items() if name!='probe')
    assert 'Env' not in m.K9_LAUNCHED_FORMAT and 'OOMKilled' in m.K9_LAUNCHED_FORMAT and 'ExitCode' in m.K9_LAUNCHED_FORMAT

OPERATIONS_FILES=[Path(k9r.DIRECTORY).parent.parent/'fable-k9-interface-20261003-rev2'/'K9_OPERATIONS.json',
                  Path(k9r.DIRECTORY).parent.parent/'fable-k9-interface-20261003-rev2'/'K9_INTERFACE_NOTE.md']
def test_static_the_read_operations_are_those_of_k9_operations_json_and_the_note_is_the_pinned_one():
    """The table of the frozen note's K9_OPERATIONS.json, read by command when it stands where it was delivered."""
    if not all(path.is_file() for path in OPERATIONS_FILES):pytest.skip('the delivered K9 note is not beside this work tree')
    m=f.load(k9r.DIRECTORY).m;raw=OPERATIONS_FILES[0].read_bytes();operations=json.loads(raw)
    assert hashlib.sha256(raw).hexdigest()==m.K9_OPERATIONS_SHA256 and hashlib.sha256(OPERATIONS_FILES[1].read_bytes()).hexdigest()==m.K9_NOTE_SHA256
    assert operations['k9_interface_note_sha256']==m.K9_NOTE_SHA256
    reads={name:phase for phase,rows in operations['phases'].items() for name,kind in rows.items() if kind=='READ'}
    assert reads=={name:row[0] for name,row in m.K9_READ_OPERATIONS.items()}
    writes={name for rows in operations['phases'].values() for name,kind in rows.items() if kind=='WRITE'}
    assert {row[2] for row in m.K9_READ_OPERATIONS.values() if row[2]}<=writes and set(m.K9_PACKAGED_PHASES)<=writes

ACTB=Path(k9r.DIRECTORY).parent.parent/'fable-actb03-20261004'/'tools'/'actb03_lib.py'
def test_attempt_key_is_the_act_b_one_by_its_own_function():
    m=f.load(k9r.DIRECTORY).m;cases=[(m.K9_EPOCH,day,row[0],name) for day in m.K9_DAYS for name,row in m.K9_READ_OPERATIONS.items()]
    for case in cases:assert m.k9_attempt_key(*case)==k9r.attempt_key(*case)
    if not ACTB.is_file():pytest.skip('actb03_lib.py is not beside this work tree')
    text=ACTB.read_text();start=text.index('def attempt_key(');end=text.index('\ndef ',start+1)
    namespace={'json':json,'sha_bytes':lambda raw:hashlib.sha256(raw).hexdigest()};exec(compile(text[start:end],str(ACTB),'exec'),namespace)
    for case in cases:assert m.k9_attempt_key(*case)==namespace['attempt_key'](*case)

# ---------------------------------------------------------------- validate_plan: one per refusal
def test_mode_epoch_and_the_operation_table():
    m,docs,_=one()
    for value in (None,'result','WRITE',['RESULT']):docs.plan['mode']=value;refused(docs,'MODE_INVALID')
    m,docs,_=one();docs.plan['epoch']='R2D2-V2-SHADOW-2026-09-28';refused(docs,'EPOCH_INVALID')
    m,docs,_=one()
    for value in ('2026-10-05','2026-10-10','2026-10-6',None,20261006):docs.plan['day']=value;refused(docs,'DAY_INVALID')
    m,docs,_=one()
    for value in ('collect_launch','stage','bind','policy',None):docs.plan['k9_operation']=value;refused(docs,'OPERATION_INVALID')
    m,docs,_=one();docs.plan['k9_operation']='readiness_probe';refused(docs,'OPERATION_NOT_OF_THIS_MODE')
    m,docs,_=one();docs.plan['k9_phase']='components';refused(docs,'OPERATION_NOT_OF_THIS_MODE')
    m,docs,_=one()
    for value in ('P','primary',None,'SPARE '):docs.plan['slot']=value;refused(docs,'SLOT_INVALID')
    m,docs,_=one();docs.plan['slot']='SPARE';docs.chain();docs.authenticate()                       # one key for both slots
    m,docs,_=one()
    for value in (k9r.attempt_key(k9r.EPOCH,'2026-10-07','causal_list','collect_result'),k9r.attempt_key(k9r.EPOCH,k9r.DAY,'causal_list','collect_launch'),'0'*64,None):
        docs.plan['attempt_key']=value;refused(docs,'ATTEMPT_KEY_MISMATCH')
    m,docs,_=one()
    for value in (None,'0'*64,'A'*64):docs.plan['evidence_boot_id_sha256']=value;refused(docs,'EVIDENCE_BOOT_UNBOUND')

def test_constants_are_the_compiled_ones_or_in_their_grammar():
    cases=[('k9_interface_note_sha256','1'*64,'CONSTANTS_NOT_THE_COMPILED_ONES'),('package_sha256','1'*64,'CONSTANTS_NOT_THE_COMPILED_ONES'),
           ('code_revision','0'*40,'CONSTANTS_NOT_THE_COMPILED_ONES'),('probe_snippet_sha256','1'*64,'PROBE_CONSTANTS_NOT_THE_COMPILED_ONES'),
           ('readiness_rule',{'numerator':90,'denominator':100},'PROBE_CONSTANTS_NOT_THE_COMPILED_ONES'),
           ('placement',dict(k9r.PLACEMENT,k9_root='/var/lib/c3po-k9'),'PLACEMENT_NOT_THE_COMPILED_ONE'),
           ('networks',{'PROVIDER':'host','DATABASE':'a','DATABASE_AND_PROVIDER':'b'},'NETWORKS_NOT_THE_COMPILED_ONES'),
           ('networks',{'PROVIDER':'bridge','DATABASE':'a'},'CONSTANTS_INVALID'),('networks',{'PROVIDER':'bridge','DATABASE':'a b','DATABASE_AND_PROVIDER':'b'},'CONSTANTS_INVALID'),
           ('image_id','c3po/backend:production','CONSTANTS_INVALID'),('disk_floor_bytes',-1,'CONSTANTS_INVALID'),('disk_floor_bytes',True,'CONSTANTS_INVALID'),
           ('disk_floor_bytes',1<<51,'CONSTANTS_INVALID'),('disk_floor_bytes',1<<30,'DISK_FLOOR_NOT_THE_COMPILED_ONE'),('disk_floor_bytes',214748364799,'DISK_FLOOR_NOT_THE_COMPILED_ONE'),('risk_limits',{'max_symbols':550},'CONSTANTS_INVALID'),
           ('risk_limits',dict(k9r.constants()['risk_limits'],max_symbols=0),'CONSTANTS_INVALID')]
    for key in ('act_b_sha256','release_sha256','policy_sha256','runner_sha256','step_table_sha256','risk_source_pins_sha256'):
        cases+=[(key,'0'*64,'CONSTANTS_INVALID'),(key,'g'*64,'CONSTANTS_INVALID'),(key,None,'CONSTANTS_INVALID')]
    for operation in ('collect_result','TREE'):
        for key,value,code in cases:
            m,docs,_=one(operation);docs.plan['constants'][key]=value;refused(docs,code)
        m,docs,_=one(operation);docs.plan['constants']['extra']=1;refused(docs,'CONSTANTS_INVALID')
        m,docs,_=one(operation);del docs.plan['constants']['networks'];refused(docs,'CONSTANTS_INVALID')
        m,docs,_=one(operation);docs.plan['constants']=None;refused(docs,'CONSTANTS_INVALID')

def test_tree_signs_no_day_no_rows_and_no_boot():
    for key,value in (('day',k9r.DAY),('k9_phase','causal_list'),('k9_operation','collect_result'),('slot','PRIMARY'),('attempt_key','1'*64),
                      ('run_not_after','2026-10-05T21:00:00+00:00'),('parent_rows',{}),('evidence_boot_id_sha256',f.BOOT_SHA),('policy_read',{})):
        m,docs,_=one('TREE');docs.plan[key]=value;refused(docs,'TREE_PLAN_INVALID')

def test_parent_rows_are_the_five_chains_of_the_placement_with_rows_of_the_tree():
    m,docs,host=one()
    for change in (lambda rows:rows.pop('claims'),lambda rows:rows.update(extra=rows['days']),lambda rows:rows['days'].update(path=k9r.PLACEMENT['tools']),
                   lambda rows:rows['days'].update(open_root=k9r.DATA),lambda rows:rows['source_root'].update(open_root=k9r.DATA),lambda rows:rows['days'].update(rows=None),lambda rows:rows['days'].update(extra=1)):
        m,docs,host=one();change(docs.plan['parent_rows']);refused(docs,'PARENT_ROWS_INVALID')
    m,docs,host=one();docs.plan['parent_rows']=None;refused(docs,'PARENT_ROWS_INVALID')
    m,docs,host=one();docs.plan['parent_rows']['secrets']['rows'][-1]['mode']=0o777;refused(docs,'CHAIN_ROW_UNSAFE')        # no open root in the K9 tree (N-8)
    m,docs,host=one();docs.plan['parent_rows']['source_root']['rows'][-1]['mode']=0o777;refused(docs,'CHAIN_ROW_UNSAFE')            # decision 6: no open root
    m,docs,host=one();docs.plan['parent_rows']['tools']['rows'][1]['uid']=1000;refused(docs,'CHAIN_ROW_UNSAFE')      # /mnt is outside the open root
    m,docs,host=one();docs.plan['parent_rows']['days']['rows'][-1]['mode']=0o2700;refused(docs,'PARENT_SETGID')
    m,docs,host=one();docs.plan['parent_rows']['tools']['rows'][-1]['mode']=0o2700;refused(docs,'CHAIN_ROW_NOT_ROOT_GROUP')   # setgid anywhere in a K9 chain
    m,docs,host=one();docs.plan['parent_rows']['tools']['rows'][2]['gid']=1000;refused(docs,'CHAIN_ROW_NOT_ROOT_GROUP')       # /var/lib of another group
    m,docs,host=one();docs.plan['parent_rows']['source_root']['rows'][-1]['gid']=1000;refused(docs,'CHAIN_ROW_NOT_ROOT_GROUP')   # decision 6
    m,docs,host=one();docs.plan['parent_rows']['days']['rows'].pop();refused(docs,'CHAIN_ROW_INVALID')

def test_run_not_after_only_in_result_and_in_the_one_spelling():
    for value in (None,'2026-10-05T21:49:59Z','2026-10-05T21:49:59','2026-10-05T18:49:59-03:00','2026-10-05 21:49:59+00:00',1759700999):
        m,docs,_=one();docs.plan['run_not_after']=value;refused(docs,'RUN_NOT_AFTER_INVALID' if value is not None else 'RUN_NOT_AFTER_INVALID')
    for operation in ('readiness_probe','policy_read'):
        m,docs,_=one(operation);docs.plan['run_not_after']='2026-10-05T21:49:59+00:00';refused(docs,'RUN_NOT_AFTER_INVALID')

def test_policy_read_only_in_policy_and_as_required():
    m,docs,_=one();docs.plan['policy_read']={};refused(docs,'POLICY_READ_INVALID')
    m,docs,_=one('readiness_probe');docs.plan['policy_read']={};refused(docs,'POLICY_READ_INVALID')
    def change(action,code):
        m,docs,_=one('policy_read');action(docs.plan['policy_read']);refused(docs,code)
    change(lambda value:value.pop('worker'),'POLICY_READ_INVALID')
    change(lambda value:value['worker'].update(container='a'*64),'POLICY_READ_INVALID')
    change(lambda value:value['worker'].update(container='-x'),'POLICY_READ_INVALID')
    change(lambda value:value['worker'].update(data_source='/'),'POLICY_READ_INVALID')
    change(lambda value:value['worker'].update(data_target='app'),'POLICY_READ_INVALID')
    change(lambda value:value['policy'].update(file_name='../policy.json'),'POLICY_READ_INVALID')
    change(lambda value:value['policy'].update(file_name='.hidden'),'POLICY_READ_INVALID')
    change(lambda value:value['release'].pop('file_name'),'POLICY_READ_INVALID')
    change(lambda value:value['release']['directory'].update(rows=None),'POLICY_READ_INVALID')
    change(lambda value:value['release']['directory'].update(open_root='/opt'),'POLICY_READ_INVALID')
    change(lambda value:value['policy']['directory']['rows'][-1].update(mode=0o777),'CHAIN_ROW_WORLD_WRITABLE')
    change(lambda value:value['worker'].update(data_source='/mnt'),'POLICY_READ_NOT_THE_DATA_VOLUME')
    m,docs,host=one('policy_read');value=docs.plan['policy_read']
    value['release']['directory']={'path':'/opt','rows':hostemu.rows(host,'/opt'),'open_root':None};refused(docs,'POLICY_READ_OUTSIDE_THE_DATA_VOLUME')
    m,docs,host=one('policy_read');value=docs.plan['policy_read']
    value['policy']['directory']={'path':k9r.DATA,'rows':hostemu.rows(host,k9r.DATA),'open_root':k9r.DATA};refused(docs,'POLICY_READ_OUTSIDE_THE_DATA_VOLUME')

def test_probe_needs_an_image_id():
    m,docs,_=one('readiness_probe');docs.plan['constants']['image_id']='sha256:'+'A'*64;refused(docs,'CONSTANTS_INVALID')

def test_a_malformed_plan_spends_no_claim(tmp_path):
    m,docs,_=one();docs.plan['attempt_key']='1'*64;docs.chain();dispatch=f.Dispatch(docs,tmp_path)
    assert refusal(dispatch.prepare)=='ATTEMPT_KEY_MISMATCH' and not dispatch.claims()

# ---------------------------------------------------------------- perform: the window belongs to D, before anything is observed
def window_refusal(operation,start,minutes=5,run_not_after=None):
    options={} if run_not_after is None else {'run_not_after':run_not_after}
    m,docs,host=one(operation,**options);docs.shift(start,start+timedelta(minutes=minutes))
    before=k9r.state_of(host);result=docs.run(host,clock=lambda:start)
    assert host.log==[] and k9r.state_of(host)==before and result['mutating_calls']['issued']==0
    return result['status'],result['code'],result.get('phase_reached')

def test_the_window_lies_in_the_eve_or_the_morning_of_d():
    at=k9r.at;eve='WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY'
    assert window_refusal('collect_result',at('2026-10-05T21:50:00+00:00'),run_not_after='2026-10-05T19:58:00+00:00')[:2]==('REFUSED','RUN_NOT_AFTER_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    assert window_refusal('collect_result',at('2026-10-04T21:50:00+00:00'))==('REFUSED',eve,'BEFORE_ANY_OBSERVATION')
    assert window_refusal('capture_result',at('2026-10-06T14:56:00+00:00'))==('REFUSED',eve,'BEFORE_ANY_OBSERVATION')
    assert window_refusal('collect_result',at('2026-10-06T21:50:00+00:00'))[1]==eve
    assert window_refusal('readiness_probe',at('2026-10-06T03:56:00+00:00'))[1]==eve                # the probe ends before 04:00Z of D
    assert window_refusal('policy_read',at('2026-10-05T23:50:00+00:00'))[1]==eve                    # the policy read is on D
    assert window_refusal('collect_result',at('2026-10-05T21:49:58+00:00'))[1]=='RESULT_WINDOW_BEFORE_RUN_NOT_AFTER'
    m,docs,host=one('collect_result');assert docs.run(host)['status']==m.COMPLETE_STATUS                     # starts exactly at run_not_after + 1 s
    m,docs,host=one('collect_result',run_not_after='2026-10-05T21:50:00+00:00');assert docs.run(host)['status']==m.COMPLETE_STATUS
    m,docs,host=one('readiness_probe',now=k9r.at('2026-10-06T03:55:00+00:00'));assert docs.run(host)['outcome']==m.K9_PROBE_OUTCOME
    m,docs,host=one('TREE',now=k9r.at('2026-10-02T12:00:00+00:00'));assert docs.run(host)['outcome']==m.K9_TREE_OUTCOME   # TREE is any READ day

def test_executor_must_be_root_before_the_window_is_judged():
    m,docs,host=one();host.actor=(1000,0);result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED','EXECUTOR_IDENTITY') and host.log==[]

# ---------------------------------------------------------------- effects, success, scope
def test_effects_of_a_result_are_the_literal():
    m,docs,host=one('components_result');plan=docs.plan;rows=plan['parent_rows']
    def chain(name):
        rows_=rows[name]['rows'];return {'path':rows_[-1]['path'],'row':rows_[-1],'chain_sha256':f.sha(f.canonical(rows_)),
                                         'mount_point_by_device_change':'/','open_root':k9r.open_root(name)}
    expected={'operation':'GO_READONLY_HOSTOPS02_K9_PHASE_READ_01','mode':'RESULT','epoch':k9r.EPOCH,'day':'2026-10-06','k9_phase':'components',
              'k9_operation':'components_result','slot':'PRIMARY','attempt_key':k9r.attempt_key(k9r.EPOCH,'2026-10-06','components','components_result'),
              'run_not_after':'2026-10-06T00:45:59+00:00','constants':k9r.constants(),'parent_rows':{name:chain(name) for name in k9r.CHAINS},
              'evidence_boot_id_sha256':f.BOOT_SHA,
              'reads':{'launch':'components_launch','launch_attempt_key':k9r.attempt_key(k9r.EPOCH,'2026-10-06','components','components_launch'),
                       'container_name':'c3po-k9-20261006-components_launch','image_id':hostemu.BACKEND,
                       'launch_record':k9r.K9_ROOT+'/days/2026-10-06/launches/components_launch.json','receipts':'K9_RUNNER',
                       'receipt_directory':k9r.K9_ROOT+'/days/2026-10-06/receipts','packaged_phase':None,
                       'outputs_hashed_again':'every file and aggregate the receipt names, below days/<D> (day/) or the source root (source/)',
                       'run_not_after':'2026-10-06T00:45:59+00:00'},
              'writes':0,'claims':0,'containers_removed':0,'containers_run':0,'activation':False}
    assert m.effects_of(plan)==expected==docs.go['effects']==docs.authority['effects']
    m,docs,host=one('execute_result');reads=m.effects_of(docs.plan)['reads']
    assert reads['receipts']=='PACKAGED_RISK_SPOOL' and reads['packaged_phase']=='execute' and reads['receipt_directory'].endswith('/risk/spool/<sha256 of risk/plan/HOST_PLAN.json>')

def test_effects_of_a_probe_policy_and_tree_are_the_literal():
    m,docs,host=one('readiness_recheck');reads=m.effects_of(docs.plan)['reads']
    assert reads=={'image_id':hostemu.BACKEND,'container_name':'c3po-k9-20261006-readiness_recheck','network':'bridge',
                   'env_file':'/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env',
                   'command':['timeout','-s','KILL','36','python','-I','-B','-','2026-10-06','<request sha256>'],
                   'snippet_sha256':m.K9_PROBE_SNIPPET_SHA256,'timeout_seconds':36,'alarm_seconds':34,'readiness_rule':{'numerator':95,'denominator':100,'minimum_eligible':4000},'binds':[]}
    assert m.effects_of(docs.plan)['containers_run']==1
    m,docs,host=one('policy_read');reads=m.effects_of(docs.plan)['reads']
    assert reads['policy_file']==k9r.POLICY_DIRECTORY+'/policy.json' and reads['release_file']==k9r.RELEASE_DIRECTORY+'/release.CERTIFIED.json'
    assert reads['expected_environment']=={'C3PO_R2D2_V2_LIVE_POLICY_FILE':'/app/day-d-data/r2d2-v2-live/2026-10-05/policy.json',
                                           'C3PO_R2D2_V2_LIVE_POLICY_SHA':f.sha(k9r.POLICY),
                                           'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':'/app/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json',
                                           'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':f.sha(k9r.RELEASE),'C3PO_BUILD_SHA':k9r.REVISION}
    m,docs,host=one('TREE');effects=m.effects_of(docs.plan);reads=effects['reads']
    assert effects['parent_rows'] is None and effects['day'] is None and effects['containers_run']==0
    assert reads['secret_files_lstat_only']==[k9r.K9_ROOT+'/secrets/provider.env',k9r.K9_ROOT+'/secrets/risk-db.env',k9r.K9_ROOT+'/secrets/emitter/password']
    assert reads['runner_file']==k9r.K9_ROOT+'/tools/k9_runner-'+f.sha(k9r.RUNNER)+'.py' and reads['rows_in_receipt'] is True
    assert reads['september_sources_lstat_only']==['/mnt/day-d-data/.r2d2-v2-risk-secrets','/mnt/day-d-data/.r2d2-v2-risk-secrets/risk-database-url',
                                                  '/mnt/day-d-data/.c3po-role-executor-20260908-r2','/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret',
                                                  '/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret/password']

@pytest.mark.parametrize('operation,outcome',[('collect_result','K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED'),('readiness_probe','K9_READINESS_READY_ALL_OBSERVED'),
                                              ('policy_read','K9_POLICY_AND_WORKER_AS_EXPECTED_ALL_OBSERVED'),('TREE','K9_TREE_AS_REQUIRED_ALL_OBSERVED')])
def test_the_go_criterion_is_the_outcome_of_the_signed_mode_at_both_layers(operation,outcome,tmp_path):
    m,docs,_=one(operation);assert m.success_of(docs.plan)==outcome==docs.go['success_criterion']
    for other in sorted(set(m.K9_SUCCESS.values())-{outcome}):
        directory=tmp_path/other;directory.mkdir();dispatch=f.Dispatch(docs,directory)
        docs.go['success_criterion']=other;docs.chain(criterion=False);assert refusal(docs.authenticate)=='GO_CRITERION'
        dispatch.save(rebind=False);assert refusal(dispatch.prepare)=='GO_CRITERION' and not dispatch.claims()
        docs.chain()

def test_scope_names_the_placement_the_snippet_and_never_a_write():
    m=f.load(k9r.DIRECTORY).m;scope=m.SCOPE
    assert scope['placement']==k9r.PLACEMENT and scope['probe']['snippet_sha256']==m.K9_PROBE_SNIPPET_SHA256 and scope['writes_allowed'] is False
    assert {'docker rm','docker ps','a claim','a container with a bind'}<=set(scope['never'])
    assert scope['contracts']['launch_record'][0]=='K9_LAUNCH_RECORD_V1' and scope['contracts']['step_receipt'][0]=='K9_STEP_RECEIPT_V1'
