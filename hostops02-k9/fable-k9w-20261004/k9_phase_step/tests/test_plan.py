"""K9W's plan, from its bytes alone: every refusal of validate_plan (run locally by the dispatcher before any claim, so
none of them spends a GO), the window refusals of perform (before anything is observed), the effects against literals
written here independently, the GO criterion per mode at both layers, the argv of every step, the attempt key against
the Act B's own function, the write operations against K9_OPERATIONS.json, and every write window of both grids of the
frozen note (aux/grid9.json) accepted by the window rule."""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest

import family as f
import hostemu
import k9w

WORK=Path(k9w.DIRECTORY).parent.parent
def load():return f.load(k9w.DIRECTORY)
def one(operation='commit_launch'):
    docs,host=k9w.case(operation);return docs.k.m,docs,host
def refused(docs,code):
    docs.chain();assert f.refusal(docs.authenticate)==code,code
    result=docs.run(f.Untouchable());assert (result['status'],result['code'])==('REFUSED',code)

# ---------------------------------------------------------------- the table, by command
def test_static_the_write_operations_are_those_of_k9_operations_json_and_the_note_is_the_pinned_one():
    m=load().m;interface=WORK/'fable-k9-interface-20261003-rev2';files=[interface/'K9_OPERATIONS.json',interface/'K9_INTERFACE_NOTE.md']
    if not all(path.is_file() for path in files):pytest.skip('the delivered K9 note is not beside this work tree')
    raw=files[0].read_bytes();operations=json.loads(raw)
    assert hashlib.sha256(raw).hexdigest()==m.K9W_OPERATIONS_SHA256 and hashlib.sha256(files[1].read_bytes()).hexdigest()==m.K9W_NOTE_SHA256
    writes={name:phase for phase,rows in operations['phases'].items() for name,kind in rows.items() if kind=='WRITE'}
    assert writes=={name:row['phase'] for name,row in m.K9W_STEPS.items()}=={name:row[0] for name,row in k9w.WRITE.items()}

def test_static_the_step_table_and_its_hash():
    m=load().m
    assert m.K9W_STEP_TABLE_SHA256==hashlib.sha256(json.dumps(m.K9W_STEP_TABLE,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert m.SCOPE['step_table_sha256']==m.K9W_STEP_TABLE_SHA256 and m.SCOPE['step_table'] is m.K9W_STEP_TABLE
    modes={name:row['mode'] for name,row in m.K9W_STEPS.items()};assert modes=={name:row[1] for name,row in k9w.WRITE.items()}
    rows={name:row['row'] for name,row in m.K9W_STEPS.items()}
    assert {name for name,row in rows.items() if row=='create'}=={name for name,mode in modes.items() if mode=='LAUNCH'}
    assert rows['bind']==rows['preflight']=='attached' and rows['stage']=='attached_short' and rows['capture_cleanup'] is None
    removes={name:row['removes'] for name,row in m.K9W_STEPS.items() if row['removes']}
    assert removes=={'commit_launch':'collect_launch','publish_launch':'commit_launch','components_launch':'publish_launch','sources_launch':'components_launch',
                     'acquire_launch':'sources_launch','execute_launch':'acquire_launch','stage':'execute_launch','capture_cleanup':'capture_launch'}
    assert {name:row['ceiling_seconds'] for name,row in m.K9W_STEPS.items() if row['mode']=='LAUNCH'}==k9w.CEILING
    assert {name:row['timeout_seconds'] for name,row in m.K9W_STEPS.items() if row['mode']=='ATTACHED'}=={'bind':35,'preflight':35,'stage':18}
    networks={name:row['network'] for name,row in m.K9W_STEPS.items()}
    assert networks=={'collect_launch':'PROVIDER','commit_launch':'DATABASE','publish_launch':'DATABASE','components_launch':'PROVIDER',
                      'sources_launch':'DATABASE_AND_PROVIDER','bind':'NONE','preflight':'NONE','acquire_launch':'DATABASE_AND_PROVIDER',
                      'execute_launch':'NONE','stage':'NONE','capture_launch':'PROVIDER','capture_cleanup':None}
    mounts={name:row['mounts'] for name,row in m.K9W_STEPS.items()}
    assert mounts=={'collect_launch':['TOOLS','DAY'],'commit_launch':['TOOLS','DAY','EMITTER'],'publish_launch':['TOOLS','DAY','SOURCE','EMITTER'],
                    'components_launch':['TOOLS','DAY','SOURCE'],'sources_launch':['TOOLS','DAY'],'bind':['TOOLS','DAY'],'preflight':['DAY'],
                    'acquire_launch':['DAY'],'execute_launch':['DAY'],'stage':['TOOLS','DAY_READ_ONLY','DAY_RECEIPTS','SOURCE'],
                    'capture_launch':['TOOLS','DAY','SOURCE'],'capture_cleanup':[]}
    # the source root is mounted read-write only where the note's table says so; never with the provider and the database together
    assert [name for name,row in m.K9W_STEPS.items() if 'SOURCE' in row['mounts'] and row['network']=='DATABASE_AND_PROVIDER']==[]
    env={name:row['env_files'] for name,row in m.K9W_STEPS.items() if row['env_files']}
    assert env=={'collect_launch':['PROVIDER'],'components_launch':['PROVIDER'],'sources_launch':['PROVIDER','RISK_DATABASE'],
                 'acquire_launch':['PROVIDER','RISK_DATABASE'],'capture_launch':['PROVIDER']}
    assert m.K9W_MOUNTS['DAY_READ_ONLY']['read_only'] is True and m.K9W_MOUNTS['TOOLS']['read_only'] is True and m.K9W_MOUNTS['EMITTER']['read_only'] is True
    assert m.K9W_MOUNTS['SOURCE']['read_only'] is False and m.K9W_MOUNTS['DAY']['read_only'] is False and m.K9W_MOUNTS['DAY_RECEIPTS']['read_only'] is False

def test_static_commands_and_their_classes():
    m=load().m;c=m.COMMANDS
    assert set(c)=={'image','launched','container_list','create','start','remove','attached','attached_short'}
    assert c['create']['argv']==['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no']
    assert (c['create']['class'],c['create']['kind'])==('QUICK','EFFECT') and (c['start']['class'],c['start']['kind'])==('RUN_SHORT','EFFECT')
    assert c['start']['argv']==['start'] and c['remove']['argv']==['rm'] and (c['remove']['class'],c['remove']['kind'])==('QUICK','EFFECT')
    assert c['attached']['argv']==c['attached_short']['argv']==['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only',
                                                                 '--cap-drop','ALL','--security-opt','no-new-privileges']
    assert (c['attached']['class'],c['attached_short']['class'])==('RUN','RUN_SHORT') and c['attached']['stdin'] is False
    assert all(c[name]['kind']=='READ' and c[name]['class']=='QUICK' for name in ('image','launched','container_list'))
    words=sum((row['argv']+row['tail'] for row in c.values()),[])
    assert not set(words)&{'-f','--force','-v','--volumes','--privileged','-d','--detach','--rm=false','exec','kill','stop'}
    k9r=Path(k9w.DIRECTORY).parent/'k9_phase_read'
    if (k9r/'build'/'ASSEMBLY.json').is_file():assert m.K9W_LAUNCHED_FORMAT==f.load(k9r).m.K9_LAUNCHED_FORMAT
    assert m.effects_budget('remove','create','start')==40 and m.effects_budget('create','start')==32 and m.effects_budget('attached')==44
    assert m.effects_budget('remove','attached_short')==32 and m.effects_budget('remove')==12 and m.K9W_FILES_ALLOWANCE_SECONDS==4

ACTB=WORK/'fable-actb03-20261004'/'tools'/'actb03_lib.py'
def test_attempt_key_is_the_act_b_one_by_its_own_function():
    m=load().m;cases=[(m.K9W_EPOCH,day,row['phase'],name) for day in m.K9W_DAYS for name,row in m.K9W_STEPS.items()]
    for case in cases:assert m.k9w_attempt_key(*case)==k9w.attempt_key(*case)
    if not ACTB.is_file():pytest.skip('actb03_lib.py is not beside this work tree')
    text=ACTB.read_text();start=text.index('def attempt_key(');end=text.index('\ndef ',start+1)
    namespace={'json':json,'sha_bytes':lambda raw:hashlib.sha256(raw).hexdigest()};exec(compile(text[start:end],str(ACTB),'exec'),namespace)
    for case in cases:assert m.k9w_attempt_key(*case)==namespace['attempt_key'](*case)

def test_the_placement_is_k9rs_byte_for_byte_and_the_constants_are_the_weeks():
    m=load().m;assert m.K9W_PLACEMENT==k9w.PLACEMENT
    k9r=Path(k9w.DIRECTORY).parent/'k9_phase_read'
    if not (k9r/'build'/'ASSEMBLY.json').is_file():pytest.skip('K9R is not beside this directory')
    r=f.load(k9r).m
    assert set(m.K9W_PLACEMENT)==set(r.K9_PLACEMENT) and m.K9W_CONSTANT_KEYS==r.K9_CONSTANT_KEYS and m.K9W_DISK_FLOOR_BYTES==r.K9_DISK_FLOOR_BYTES
    assert (m.K9W_RECORD_KEYS,m.K9W_STARTED_KEYS,m.K9W_STEP_KEYS)==(r.K9_RECORD_KEYS,r.K9_STARTED_KEYS,r.K9_STEP_KEYS)
    assert (m.K9W_RECORD_SCHEMA,m.K9W_STARTED_SCHEMA,m.K9W_STEP_SCHEMA)==(r.K9_RECORD_SCHEMA,r.K9_STARTED_SCHEMA,r.K9_STEP_SCHEMA)
    assert m.K9W_DAYS==r.K9_DAYS and m.K9W_EPOCH==r.K9_EPOCH and m.K9W_NOTE_SHA256==r.K9_NOTE_SHA256
    assert {key:value for key,value in m.K9W_PLACEMENT.items() if key not in ('source_root','source_open_root')}==\
           {key:value for key,value in r.K9_PLACEMENT.items() if key not in ('source_root','source_open_root')}

def test_the_placement_is_k9rs_byte_for_byte_at_decision_6():
    """The one object both programs sign. Skipped (and so recorded in VALIDATION.json) while K9R still compiles the
    source root of N-8 on the data volume: K9R must be rebuilt for decision 6 before either is bound."""
    m=load().m;k9r=Path(k9w.DIRECTORY).parent/'k9_phase_read'
    assert m.K9W_PLACEMENT['source_root']=='/var/lib/c3po/r2d2-v2-source-20261005' and m.K9W_PLACEMENT['source_open_root'] is None
    if not (k9r/'build'/'ASSEMBLY.json').is_file():pytest.skip('K9R is not beside this directory')
    r=f.load(k9r).m
    if r.K9_PLACEMENT['source_root']!=m.K9W_PLACEMENT['source_root']:pytest.skip('K9R_NOT_YET_AT_DECISION_6: K9R compiles '+r.K9_PLACEMENT['source_root'])
    assert m.K9W_PLACEMENT==r.K9_PLACEMENT

# ---------------------------------------------------------------- validate_plan: one per refusal
def test_mode_epoch_day_operation_slot_and_attempt_key():
    for value in (None,'launch','RESULT',['LAUNCH']):
        m,docs,_=one();docs.plan['mode']=value;refused(docs,'MODE_INVALID')
    m,docs,_=one();docs.plan['mode']='ATTACHED';refused(docs,'OPERATION_NOT_OF_THIS_MODE')
    m,docs,_=one();docs.plan['epoch']='R2D2-V2-SHADOW-2026-09-28';refused(docs,'EPOCH_INVALID')
    for value in ('2026-10-05','2026-10-10','2026-10-6',None,20261006):
        m,docs,_=one();docs.plan['day']=value;refused(docs,'DAY_INVALID')
    for value in ('collect_result','readiness_probe','policy_read','commit',None,'COMMIT_LAUNCH'):
        m,docs,_=one();docs.plan['k9_operation']=value;refused(docs,'OPERATION_INVALID')
    m,docs,_=one();docs.plan['k9_phase']='components';refused(docs,'OPERATION_NOT_OF_THIS_MODE')
    for value in ('primary',None,'SPARE2'):
        m,docs,_=one();docs.plan['slot']=value;refused(docs,'SLOT_INVALID')
    m,docs,_=one();docs.plan['attempt_key']=k9w.attempt_key(k9w.EPOCH,'2026-10-07','causal_list','commit_launch');refused(docs,'ATTEMPT_KEY_MISMATCH')
    m,docs,_=one();docs.plan['attempt_key']=k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list','collect_launch');refused(docs,'ATTEMPT_KEY_MISMATCH')
    m,docs,_=one();docs.plan['slot']='SPARE';docs.chain();docs.authenticate()        # the slot does not enter the key: one claim per attempt
    for value in (None,'0'*64,'A'*64):
        m,docs,_=one();docs.plan['evidence_boot_id_sha256']=value;refused(docs,'EVIDENCE_BOOT_UNBOUND')

def test_constants():
    def changed(code,**changes):
        m,docs,_=one();values=docs.plan['constants'];values.update(changes);refused(docs,code)
    m,docs,_=one();docs.plan['constants']['extra']=1;refused(docs,'CONSTANTS_INVALID')
    m,docs,_=one();del docs.plan['constants']['image_id'];refused(docs,'CONSTANTS_INVALID')
    m,docs,_=one();docs.plan['constants']=None;refused(docs,'CONSTANTS_INVALID')
    changed('CONSTANTS_NOT_THE_COMPILED_ONES',k9_interface_note_sha256='ab'*32)
    changed('CONSTANTS_NOT_THE_COMPILED_ONES',package_sha256='ab'*32)
    changed('CONSTANTS_NOT_THE_COMPILED_ONES',code_revision='ab'*20)
    changed('PLACEMENT_NOT_THE_COMPILED_ONE',placement=dict(k9w.PLACEMENT,k9_root='/var/lib/c3po/other'))
    changed('PLACEMENT_NOT_THE_COMPILED_ONE',placement=dict(k9w.PLACEMENT,k9_open_root='/var/lib'))
    for key in ('act_b_sha256','release_sha256','policy_sha256','runner_sha256','probe_snippet_sha256','risk_source_pins_sha256'):
        changed('CONSTANTS_INVALID',**{key:'0'*64});changed('CONSTANTS_INVALID',**{key:'AB'*32})
    changed('CONSTANTS_INVALID',step_table_sha256='0'*64)
    changed('STEP_TABLE_NOT_THE_COMPILED_ONE',step_table_sha256='ab'*32)
    changed('RUNNER_NOT_THE_COMPILED_ONE',runner_sha256='ab'*32)
    assert load().m.K9W_RUNNER_SHA256=='563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'
    changed('CONSTANTS_INVALID',image_id='c3po/backend:production');changed('CONSTANTS_INVALID',image_id='ab'*32)
    changed('CONSTANTS_INVALID',networks={'PROVIDER':'bridge','DATABASE':'c3po_c3po_internal'})
    changed('CONSTANTS_INVALID',networks=dict(k9w.NETWORKS,DATABASE='--privileged'))
    changed('CONSTANTS_INVALID',networks=dict(k9w.NETWORKS,DATABASE='a b'))
    changed('NETWORKS_NOT_THE_COMPILED_ONES',networks=dict(k9w.NETWORKS,PROVIDER='host'))
    changed('NETWORKS_NOT_THE_COMPILED_ONES',networks=dict(k9w.NETWORKS,PROVIDER='c3po_db_loopback'))
    changed('NETWORKS_NOT_THE_COMPILED_ONES',networks=dict(k9w.NETWORKS,DATABASE='host'))
    changed('NETWORKS_NOT_THE_COMPILED_ONES',networks=dict(k9w.NETWORKS,DATABASE_AND_PROVIDER='none'))
    changed('RISK_LIMITS_NOT_THE_COMPILED_ONES',risk_limits=dict(k9w.LIMITS,max_symbols=551))
    changed('RISK_LIMITS_NOT_THE_COMPILED_ONES',risk_limits=dict(k9w.LIMITS,max_symbols=550.0))
    changed('CONSTANTS_INVALID',readiness_rule={'numerator':95.0,'denominator':100})
    changed('CONSTANTS_INVALID',readiness_rule={'Numerator':95})
    changed('CONSTANTS_INVALID',readiness_rule={})
    changed('CONSTANTS_INVALID',readiness_rule=[95,100])
    changed('CONSTANTS_INVALID',readiness_rule={'numerator':True})
    m,docs,_=one();docs.plan['constants']['readiness_rule']={'numerator':95,'denominator':100,'minimum_eligible':4000};docs.chain();docs.authenticate()
    changed('DISK_FLOOR_NOT_THE_COMPILED_ONE',disk_floor_bytes=214748364799)
    changed('DISK_FLOOR_NOT_THE_COMPILED_ONE',disk_floor_bytes=214748364800.0)
    changed('DISK_FLOOR_NOT_THE_COMPILED_ONE',disk_floor_bytes=True)

def rows_of(docs,name):return docs.plan['parent_rows'][name]['rows']
def test_parent_rows():
    m,docs,_=one();del docs.plan['parent_rows']['claims'];refused(docs,'PARENT_ROWS_INVALID')
    m,docs,_=one();docs.plan['parent_rows']=None;refused(docs,'PARENT_ROWS_INVALID')
    m,docs,_=one();docs.plan['parent_rows']['days']['path']='/var/lib/c3po/r2d2-v2-k9-20261005/claims';refused(docs,'PARENT_ROWS_INVALID')
    m,docs,_=one();docs.plan['parent_rows']['days']['open_root']='/var/lib';refused(docs,'PARENT_ROWS_INVALID')       # no open root for the K9 tree
    m,docs,_=one();docs.plan['parent_rows']['source_root']['open_root']='/var/lib';refused(docs,'PARENT_ROWS_INVALID')   # no open root anywhere (decision 6)
    for name in ('days','secrets','tools','claims'):
        m,docs,_=one();rows_of(docs,name)[3]['mode']=0o775;refused(docs,'CHAIN_ROW_UNSAFE')         # /var/lib/c3po group-writable
        m,docs,_=one();rows_of(docs,name)[3]['uid']=1000;refused(docs,'CHAIN_ROW_UNSAFE')
        m,docs,_=one();rows_of(docs,name)[3]['gid']=1000;refused(docs,'CHAIN_ROW_GROUP_OR_SETGID')     # gid 0 everywhere (as K4-E0)
        m,docs,_=one();rows_of(docs,name)[2]['mode']=0o2755;refused(docs,'CHAIN_ROW_GROUP_OR_SETGID')
        m,docs,_=one();rows_of(docs,name)[-1]['mode']=0o755;refused(docs,'CHAIN_LEAF_NOT_ROOT_PRIVATE')
        m,docs,_=one();rows_of(docs,name)[-1]['mode']=0o750;refused(docs,'CHAIN_LEAF_NOT_ROOT_PRIVATE')
        m,docs,_=one();rows_of(docs,name).pop();refused(docs,'CHAIN_ROW_INVALID')
    for name in ('days','claims'):
        m,docs,_=one();rows_of(docs,name)[-1]['mode']=0o2700;refused(docs,'PARENT_SETGID')
    # decision 6: the source root under the same root-only chain as the K9 tree, on the filesystem of days/
    for index in (1,2,3,4):
        m,docs,_=one();rows_of(docs,'source_root')[index]['uid']=1000;refused(docs,'CHAIN_ROW_UNSAFE')
        m,docs,_=one();rows_of(docs,'source_root')[index]['gid']=1000;refused(docs,'CHAIN_ROW_GROUP_OR_SETGID')
        m,docs,_=one();rows_of(docs,'source_root')[index]['mode']|=0o020;refused(docs,'CHAIN_ROW_UNSAFE')
        m,docs,_=one();rows_of(docs,'source_root')[index]['mode']|=0o2000;refused(docs,'CHAIN_ROW_GROUP_OR_SETGID' if index<4 else 'PARENT_SETGID')
    m,docs,_=one();rows_of(docs,'source_root')[2]['mode']=0o1777;refused(docs,'CHAIN_ROW_UNSAFE')                     # sticky is no exception
    m,docs,_=one();rows_of(docs,'source_root')[-1]['mode']=0o750;refused(docs,'CHAIN_LEAF_NOT_ROOT_PRIVATE')
    m,docs,_=one();rows_of(docs,'source_root')[-1]['device']+=1;refused(docs,'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS')
    m,docs,_=one();docs.plan['parent_rows']['source_root']['path']='/mnt/day-d-data/r2d2-v2-source-20261005';refused(docs,'PARENT_ROWS_INVALID')

def test_run_not_after():
    for value in (None,'2026-10-05T22:07:59Z','2026-10-05T22:07:59+00','2026-10-05 22:07:59+00:00','2026-10-05T19:07:59-03:00',20261005):
        m,docs,_=one();docs.plan['run_not_after']=value;refused(docs,'RUN_NOT_AFTER_INVALID')
    m,docs,_=one('bind');docs.plan['run_not_after']='2026-10-06T02:40:00+00:00';refused(docs,'RUN_NOT_AFTER_INVALID')
    m,docs,_=one('capture_cleanup');docs.plan['run_not_after']='2026-10-06T14:40:00+00:00';refused(docs,'RUN_NOT_AFTER_INVALID')
    m,docs,_=one('capture_launch');docs.plan['run_not_after']='2026-10-06T14:03:01+00:00';refused(docs,'RUN_NOT_AFTER_INVALID')

def test_bind_member():
    m,docs,_=one();docs.plan['bind']=k9w.bind_member();refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');docs.plan['bind']=None;refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');docs.plan['bind']['extra']=1;refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');docs.plan['bind']['namespace']='R2D2-V2-SHADOW-2026-10-06';refused(docs,'BIND_NAMESPACE_NOT_THE_COMPILED_ONE')
    m,docs,_=one('bind');docs.plan['bind']['namespace']='R2D2-V2-DIAG-R4-2026-10-07';refused(docs,'BIND_NAMESPACE_NOT_THE_COMPILED_ONE')
    m,docs,_=one('bind');docs.plan['bind']['cutoff_at']='2026-10-06T02:26:00Z';refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');docs.plan['bind']['phase_windows']['acquire']['not_after']='2026-10-06T03:46:59Z';refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');del docs.plan['bind']['phase_windows']['execute'];refused(docs,'BIND_INVALID')
    m,docs,_=one('bind');docs.plan['bind']['phase_windows']['execute']['extra']=1;refused(docs,'BIND_INVALID')
    def windows(code,cutoff=k9w.CUTOFF,**changes):
        value=copy.deepcopy(k9w.WINDOWS)
        for key,item in changes.items():phase,edge=key.split('__');value[phase][edge]=item
        m,docs,_=one('bind');docs.plan['bind']=k9w.bind_member(cutoff=cutoff,windows=value);refused(docs,code)
    windows('BIND_WINDOWS_INVALID',preflight__not_after='2026-10-06T02:38:00+00:00')                    # empty
    windows('BIND_WINDOWS_INVALID',acquire__not_before='2026-10-06T02:37:00+00:00')                     # before preflight
    windows('BIND_WINDOWS_INVALID',execute__not_before='2026-10-06T02:40:00+00:00')                     # before acquire
    windows('BIND_WINDOWS_INVALID',execute__not_after='2026-10-06T03:40:00+00:00')                      # ends before acquire
    windows('BIND_WINDOWS_INVALID',execute__not_before='2026-10-06T02:45:00+00:00',execute__not_after='2026-10-06T03:00:00+00:00')   # inside acquire, ends first
    windows('BIND_WINDOWS_INVALID',cutoff='2026-10-06T02:41:01+00:00')                                  # after acquire opens
    windows('BIND_WINDOWS_INVALID',cutoff='2026-10-05T19:59:59+00:00')                                  # before the eve
    windows('BIND_WINDOWS_INVALID',execute__not_after='2026-10-06T13:30:01+00:00')                      # after the open of D
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']=k9w.owner_order().decode()+'\n';refused(docs,'BIND_ORDER_NOT_ASCII')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']=k9w.owner_order(cutoff='2026-10-06T02:25:00+00:00').decode();refused(docs,'BIND_ORDER_NOT_THE_DETERMINED_BYTES')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']=json.dumps(json.loads(k9w.owner_order()),sort_keys=True);refused(docs,'BIND_ORDER_NOT_THE_DETERMINED_BYTES')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']='{"café":1}';refused(docs,'BIND_ORDER_NOT_ASCII')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']='';refused(docs,'BIND_ORDER_NOT_ASCII')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_text']=None;refused(docs,'BIND_ORDER_NOT_ASCII')
    m,docs,_=one('bind');docs.plan['bind']['owner_order_sha256']='ab'*32;refused(docs,'BIND_ORDER_SHA256_MISMATCH')

# ---------------------------------------------------------------- perform: the window of D, before anything is observed
def window_refused(operation,code,start,minutes=5,**plan_changes):
    docs,_=k9w.case(operation);docs.shift(start,start+timedelta(minutes=minutes))
    for key,value in plan_changes.items():docs.plan[key]=value
    docs.chain();docs.authenticate(clock=lambda:start);host=k9w.prepared(docs.k,operation);before=k9w.state_of(host)
    result=docs.run(host,clock=lambda:start);assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'PRECHECK'),(operation,result['code'])
    assert host.log==[] and k9w.state_of(host)==before                 # the identity only (not a logged call): nothing observed

def test_windows_of_the_day():
    at=k9w.at
    window_refused('commit_launch','WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY',at('2026-10-05T19:59:00+00:00'),run_not_after='2026-10-05T20:14:00+00:00')
    window_refused('commit_launch','WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY',at('2026-10-06T14:56:00+00:00'),run_not_after='2026-10-06T15:11:00+00:00')
    window_refused('commit_launch','WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY',at('2026-10-06T21:30:00+00:00'),run_not_after='2026-10-06T21:45:00+00:00')
    window_refused('components_launch','WINDOW_NOT_OF_THE_STEP_CLASS',at('2026-10-06T13:26:00+00:00'),run_not_after='2026-10-06T14:11:00+00:00')
    window_refused('capture_launch','WINDOW_NOT_OF_THE_STEP_CLASS',at('2026-10-06T13:29:00+00:00'))
    window_refused('capture_cleanup','CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER',at('2026-10-06T14:02:00+00:00'))
    window_refused('commit_launch','RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING',at('2026-10-05T21:52:00+00:00'),run_not_after='2026-10-05T22:07:01+00:00')
    window_refused('commit_launch','RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING',at('2026-10-05T21:52:00+00:00'),run_not_after='2026-10-05T22:06:59+00:00')
    window_refused('commit_launch','RUN_NOT_AFTER_OUTSIDE_THE_UTC_DAY',at('2026-10-05T23:50:00+00:00'),run_not_after='2026-10-06T00:05:00+00:00')
    window_refused('commit_launch','RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT',at('2026-10-06T03:40:00+00:00'),run_not_after='2026-10-06T03:55:00+00:00')
    window_refused('capture_launch','RUN_NOT_AFTER_TOO_CLOSE',at('2026-10-06T14:00:26+00:00'),minutes=1)      # 154 s < 90 + 5 + 60

GRID9=WORK/'fable-k9-interface-20261003-rev2'/'aux'/'grid9.json'
def test_every_write_window_of_both_grids_of_the_note_passes_the_window_rule():
    """G18 and G19, four eves each: every WRITE row (window, run_not_after) as the binder would sign it is accepted by
    k9w_window_of at the first and at the last second of its window, and a run_not_after one second off is refused."""
    if not GRID9.is_file():pytest.skip('aux/grid9.json is not beside this work tree')
    m=load().m;grid=json.loads(GRID9.read_bytes());seen=0
    for name in ('G18','G19'):
        for eve in grid[name]:
            for row in eve['rows']:
                if row['kind']!='WRITE':continue
                start,end=row['not_before'].replace('Z','+00:00'),row['not_after'].replace('Z','+00:00')
                limit=row.get('run_not_after','').replace('Z','+00:00') or None
                plan={'day':eve['day'],'k9_operation':row['operation'],'run_not_after':limit,'window':{'not_before':start,'expires_at':end}}
                assert m.K9W_STEPS[row['operation']]['mode']==row['mode']
                if 'ceiling_seconds' in row:assert m.K9W_STEPS[row['operation']]['ceiling_seconds']==row['ceiling_seconds']
                for now in (start,end):m.k9w_window_of(plan,k9w.at(now))
                if limit and row['operation']!='capture_launch':
                    late=(k9w.at(limit)+timedelta(seconds=1)).isoformat()
                    with pytest.raises(ValueError):m.k9w_window_of(dict(plan,run_not_after=late),k9w.at(start))
                seen+=1
    assert seen>=2*4*12

# ---------------------------------------------------------------- effects, criterion
def test_effects_are_the_literal_step_with_independently_written_argv():
    expected={
        'collect_launch':['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no',
                          '--name','c3po-k9-20261006-collect_launch','--label','c3po.k9.attempt_key='+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list','collect_launch'),
                          '--label','c3po.k9.request_sha256='+'1'*64,'--network','bridge','--env-file',k9w.K9_ROOT+'/secrets/provider.env',
                          '--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true','--env','C3PO_BUILD_SHA='+k9w.REVISION,
                          '--mount','type=bind,source=%s/tools,target=/c3po-k9-tools,readonly'%k9w.K9_ROOT,
                          '--mount','type=bind,source=%s/days/2026-10-06,target=/c3po-k9-day'%k9w.K9_ROOT,hostemu.BACKEND,
                          'timeout','-s','KILL','90','python','-I','/c3po-k9-tools/k9_runner-%s.py'%k9w.RUNNER_SHA256,'--plan','/c3po-k9-day/plans/collect_launch.json',
                          '--plan-sha256','2'*64],
        'acquire_launch':['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no',
                          '--name','c3po-k9-20261006-acquire_launch','--label','c3po.k9.attempt_key='+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'risk','acquire_launch'),
                          '--label','c3po.k9.request_sha256='+'1'*64,'--network','c3po_db_loopback','--env-file',k9w.K9_ROOT+'/secrets/provider.env',
                          '--env-file',k9w.K9_ROOT+'/secrets/risk-db.env','--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true','--env','C3PO_BUILD_SHA='+k9w.REVISION,
                          '--mount','type=bind,source=%s/days/2026-10-06,target=/c3po-k9-day'%k9w.K9_ROOT,hostemu.BACKEND,
                          'timeout','-s','KILL','90','python','-m','app.r2d2_v2_risk_host_executor','acquire','--manifest','/c3po-k9-day/risk/plan/HOST_PLAN.json',
                          '--manifest-sha256','3'*64,'--go','/c3po-k9-day/risk/plan/GO.json','--go-sha256','4'*64,'--source-root','/app','--spool-root',
                          '/c3po-k9-day/risk/spool','--previous-receipt-sha256','5'*64],
        'preflight':['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                     '--name','c3po-k9-20261006-preflight','--label','c3po.k9.attempt_key='+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'risk','preflight'),
                     '--label','c3po.k9.request_sha256='+'1'*64,'--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true','--env','C3PO_BUILD_SHA='+k9w.REVISION,
                     '--mount','type=bind,source=%s/days/2026-10-06,target=/c3po-k9-day'%k9w.K9_ROOT,hostemu.BACKEND,
                     'timeout','-s','KILL','35','python','-m','app.r2d2_v2_risk_host_executor','preflight','--manifest','/c3po-k9-day/risk/plan/HOST_PLAN.json',
                     '--manifest-sha256','3'*64,'--go','/c3po-k9-day/risk/plan/GO.json','--go-sha256','4'*64,'--source-root','/app','--spool-root','/c3po-k9-day/risk/spool'],
        'stage':['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                 '--name','c3po-k9-20261006-stage','--label','c3po.k9.attempt_key='+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'risk','stage'),
                 '--label','c3po.k9.request_sha256='+'1'*64,'--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true','--env','C3PO_BUILD_SHA='+k9w.REVISION,
                 '--mount','type=bind,source=%s/tools,target=/c3po-k9-tools,readonly'%k9w.K9_ROOT,
                 '--mount','type=bind,source=%s/days/2026-10-06,target=/c3po-k9-day,readonly'%k9w.K9_ROOT,
                 '--mount','type=bind,source=%s/days/2026-10-06/receipts,target=/c3po-k9-day/receipts'%k9w.K9_ROOT,
                 '--mount','type=bind,source=%s,target=/c3po-source'%k9w.SOURCE_ROOT,hostemu.BACKEND,
                 'timeout','-s','KILL','18','python','-I','/c3po-k9-tools/k9_runner-%s.py'%k9w.RUNNER_SHA256,'--plan','/c3po-k9-day/plans/stage.json',
                 '--plan-sha256','2'*64]}
    for operation,argv in expected.items():
        m,docs,_=one(operation);effects=m.effects_of(docs.plan)
        assert effects['step']['argv']==argv,operation
        assert len(argv)-len(m.COMMANDS['create' if operation.endswith('_launch') else 'attached']['argv'])<=m.MAX_ARGUMENTS
    m,docs,_=one('execute_launch');e=m.effects_of(docs.plan)
    assert e['step']['argv'][e['step']['argv'].index('--network')+1]=='none' and '--env-file' not in e['step']['argv']
    m,docs,_=one('commit_launch');e=m.effects_of(docs.plan)
    assert e['step']['argv'][e['step']['argv'].index('--network')+1]=='c3po_c3po_internal' and '--env-file' not in e['step']['argv']
    assert 'type=bind,source=%s/secrets/emitter,target=/c3po-k9-emitter,readonly'%k9w.K9_ROOT in e['step']['argv']
    assert e['step']['removal_record_file']==k9w.K9_ROOT+'/days/2026-10-06/launches/collect_launch.json'
    assert e['step']['claim_file']==k9w.K9_ROOT+'/claims/'+docs.plan['attempt_key']+'.claim'
    assert (e['claims'],e['containers_created'],e['containers_removed_at_most'],e['files_created_at_most'],e['directories_created_at_most'],e['activation'])==(1,1,2,3,0,False)
    assert e['step']['withdrawal_argv'][0]=='rm'
    m,docs,_=one('collect_launch');e=m.effects_of(docs.plan)
    assert e['step']['directories_created']==[k9w.K9_ROOT+'/days/2026-10-06']+[k9w.K9_ROOT+'/days/2026-10-06/'+name for name in ('plans','launches','receipts')]
    assert (e['containers_removed_at_most'],e['directories_created_at_most'])==(1,4)
    for operation,count in (('bind',0),('preflight',0),('stage',1),('capture_launch',1),('acquire_launch',2)):
        m,docs,_=one(operation);e=m.effects_of(docs.plan);assert e['containers_removed_at_most']==count,operation
        assert (e['step']['withdrawal_argv'] is None)==(operation in ('bind','preflight','stage'))
    m,docs,_=one('capture_cleanup');e=m.effects_of(docs.plan)
    assert e['step']['argv'] if 'argv' in e['step'] else True
    assert 'argv' not in e['step'] and (e['containers_created'],e['containers_removed_at_most'],e['files_created_at_most'])==(0,1,1)
    m,docs,_=one('bind');e=m.effects_of(docs.plan);assert e['bind']==docs.plan['bind'] and e['step']['launch_record_file'] is None
    m,docs,_=one('commit_launch');e=m.effects_of(docs.plan)
    for name in k9w.CHAINS:
        rows=docs.plan['parent_rows'][name]['rows'];seen=e['parent_rows'][name]
        assert seen['chain_sha256']==k9w.sha(k9w.canonical(rows)) and seen['row']==rows[-1] and seen['path']==k9w.PLACEMENT[name] and seen['open_root']==k9w.open_root(name)

def test_go_criterion_follows_the_mode_at_both_layers():
    for operation,outcome in (('commit_launch','K9_STEP_LAUNCHED_DETACHED_READ_BACK'),('bind','K9_STEP_RAN_ATTACHED_RECEIPT_COMPLETE'),
                              ('capture_cleanup','K9_CONTAINER_REMOVED_READ_BACK')):
        m,docs,_=one(operation);assert m.success_of(docs.plan)==outcome==docs.go['success_criterion']
        for other in ('K9_STEP_LAUNCHED_DETACHED_READ_BACK','K9_STEP_RAN_ATTACHED_RECEIPT_COMPLETE','K9_CONTAINER_REMOVED_READ_BACK','K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE'):
            if other==outcome:continue
            docs.go['success_criterion']=other;docs.chain(criterion=False);assert f.refusal(docs.authenticate)=='GO_CRITERION'

def test_argv_words_are_bounded_and_in_the_core_grammar():
    m=load().m
    for operation in m.K9W_STEPS:
        if m.K9W_STEPS[operation]['row'] is None:continue
        _,docs,_=one(operation)
        for timeout in (90,m.K9W_STEPS[operation]['ceiling_seconds'] or 35):
            words=m.k9w_container_arguments(docs.plan,'1'*64,'2'*64,timeout,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})
            assert len(words)<=m.MAX_ARGUMENTS and all(len(word)<=8192 for word in words)
        with pytest.raises(ValueError):m.k9w_container_arguments(docs.plan,'0'*64,'2'*64,90,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})
        with pytest.raises(ValueError):m.k9w_container_arguments(docs.plan,'1'*64,'2'*64,7201,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})

RUNNER=WORK/'fable-k9runner-20261004'/'k9_runner.py'
def test_the_step_plan_is_the_runners_by_its_own_tables():
    """The runner's own constants (read from its delivered bytes by the syntax tree, never executed): the step plan's
    keys, the constants' keys, the bind's risk keys, the emitter's connection names, and per operation the network class
    and the attached budget, which must end before this source's container limit."""
    if not RUNNER.is_file():pytest.skip('the runner is not beside this work tree')
    import ast
    raw=RUNNER.read_bytes();tree=ast.parse(raw);values={}
    assert hashlib.sha256(raw).hexdigest()==load().m.K9W_RUNNER_SHA256,'the delivered runner is not the compiled one'
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('PLAN_KEYS','CONST_KEYS','RISK_KEYS','DB','OPS','EPOCH','DAYS'):
            values[node.targets[0].id]=ast.literal_eval(node.value)
    m=load().m
    assert values['PLAN_KEYS']==set(m.K9W_STEP_PLAN_KEYS) and values['CONST_KEYS']==set(m.K9W_STEP_PLAN_CONSTANTS)
    assert values['RISK_KEYS']=={'namespace','cutoff_at','phase_windows','owner_order_text','owner_order_sha256'} and values['DB']==m.K9W_EMITTER_DATABASE
    assert values['EPOCH']==m.K9W_EPOCH and tuple(values['DAYS'])==m.K9W_DAYS
    runner_ops={name for name,row in m.K9W_STEPS.items() if row['command']=='RUNNER'};assert set(values['OPS'])==runner_ops
    for name,(phase,network,seconds) in values['OPS'].items():
        row=m.K9W_STEPS[name];assert row['phase']==phase and row['network']==network,name
        assert (seconds is None)==(row['mode']=='LAUNCH') and (seconds is None or seconds<row['timeout_seconds']),name
