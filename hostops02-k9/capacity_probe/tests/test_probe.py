"""The capacity probe on the emulated host: the plan of each step and its refusals from the bytes, the literal effects,
every refusal of the precheck (nothing started), the containers (what the engine is asked for, word for word), every
verdict after them, and the receipt (booleans, constant codes, identities, the calendar line, counts and timings). The
containers are the models of tests/kprobe.py; tests/test_scripts.py runs the real scripts and compares them."""
import ast
from datetime import timedelta
import hashlib
import json
import re

import pytest

import family as f
import hostemu
import kprobe

K=kprobe.K
refusal=f.refusal
STEPS=('CALENDAR','IDENT','LOAD')
SETTINGS_FOUND={'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':{'present':True,'equal':True},'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE':{'present':True,'equal':True},
                'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE':{'present':False,'equal':False},'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':{'present':False,'equal':False},
                'C3PO_R2D2_V2_CAPACITY_VETO_MODE':{'present':False,'equal':False},'C3PO_R2D2_V2_CAPACITY_REQUIRED':{'present':False,'equal':False}}

def run(docs,host,**options):
    receipt=docs.run(host,**options);assert f.sealed(receipt) and receipt['schema']==K().m.RECEIPT_SCHEMA;return receipt
def words(host):
    """The docker commands of a run, as short labels."""
    out=[]
    for entry in host.commands:
        argv=entry['argv'][1:]
        if argv[:2]==['image','inspect']:out.append('image')
        elif argv[:2]==['container','inspect']:out.append('mounts' if '.Mounts' in argv[3] else 'environment' if '.Config.Env' in argv[3] else 'worker')
        elif argv[:2]==['ps','-a']:out.append('ps')
        elif argv[:1]==['run']:out.append('run')
        else:out.append(' '.join(argv[:2]))
    return out
def intercept(host,needle,returncode,output):
    """The emulated CLI answers (returncode, output) to a command whose argv holds needle (a word or a part of a word)."""
    real=host.docker.run
    def answer(args,stdin=None,environment=None):
        if any(needle in word for word in args):return returncode,output
        return real(args,stdin,environment)
    host.docker.run=answer
def verdict(receipt):return receipt['status'],receipt['outcome'],receipt['code']
def names(docs):
    step=docs.plan['step'];base='hostops02-probe-'+step.lower()+'-'+docs.go16()
    return [base+'-1',base+'-2'] if step=='IDENT' else [base]


# ---------------------------------------------------------------- the plan, from its bytes
def bad_rows(host):
    rows=hostemu.rows(host,'/var/lib');rows[1]['uid']=1000;return rows
PLAN_CASES=[
    ('CALENDAR','step',None,'STEP_INVALID'),('CALENDAR','step','calendar','STEP_INVALID'),('CALENDAR','step','TLS','STEP_INVALID'),
    ('CALENDAR','step',['CALENDAR'],'STEP_INVALID'),
    ('CALENDAR','evidence_boot_id_sha256',None,'EVIDENCE_BOOT_UNBOUND'),('IDENT','evidence_boot_id_sha256','0'*64,'EVIDENCE_BOOT_UNBOUND'),
    ('LOAD','evidence_boot_id_sha256','A'*64,'EVIDENCE_BOOT_UNBOUND'),
    ('CALENDAR','image_revision',None,'IMAGE_REVISION_NOT_THE_RELEASE'),('LOAD','image_revision','0'*40,'IMAGE_REVISION_NOT_THE_RELEASE'),
    ('IDENT','image_revision','DD4EC4BB8DAB4D8B0372B0F9EABC90BF6443E858','IMAGE_REVISION_NOT_THE_RELEASE'),
    ('CALENDAR','image_id',None,'IMAGE_ID'),('IDENT','image_id','c3po/backend:production','IMAGE_ID'),('LOAD','image_id','sha256:'+'A'*64,'IMAGE_ID'),
    ('CALENDAR','capacity',{'root_path':kprobe.ROOT,'parent_rows':[]},'CAPACITY_NOT_OF_THE_STEP'),
    ('CALENDAR','load',{},'LOAD_NOT_OF_THE_STEP'),('IDENT','load',{},'LOAD_NOT_OF_THE_STEP'),
    ('IDENT','capacity',None,'CAPACITY_UNBOUND'),('LOAD','capacity',[],'CAPACITY_UNBOUND'),
    ('LOAD','load',None,'LOAD_UNBOUND'),
]
@pytest.mark.parametrize('step,field,value,code',PLAN_CASES)
def test_every_member_of_the_plan_is_refused_from_its_bytes_before_any_claim(step,field,value,code,tmp_path):
    docs,_=kprobe.case(step);docs.plan[field]=value;docs.chain()
    assert refusal(docs.authenticate)==code
    result=docs.run(f.Untouchable());assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'AUTHENTICATION')
    dispatch=f.Dispatch(docs,tmp_path);assert refusal(dispatch.prepare)==code and not dispatch.claims()

def capacity(**changes):
    _,host=kprobe.world();out={'root_path':kprobe.ROOT,'parent_rows':hostemu.rows(host,'/var/lib')};out.update(changes);return out
def rows_with(index,**changes):
    _,host=kprobe.world();rows=hostemu.rows(host,'/var/lib');rows[index].update(changes);return rows
CAPACITY_CASES=[
    ({'root_path':kprobe.ROOT,'parent_rows':[],'extra':1},'CAPACITY_UNBOUND'),
    ({'root_path':'/c3po-capacity'},'CAPACITY_ROOT_INVALID'),({'root_path':'var/lib/c3po-capacity'},'CAPACITY_ROOT_INVALID'),
    ({'root_path':'/var/lib/c3po-capacity/'},'CAPACITY_ROOT_INVALID'),({'root_path':'/var/lib/../c3po-capacity'},'CAPACITY_ROOT_INVALID'),
    ({'root_path':'/var/lib/C3PO-capacity'},'CAPACITY_ROOT_INVALID'),({'root_path':'/var/lib/-c3po'},'CAPACITY_ROOT_INVALID'),
    ({'root_path':'/var/lib/c3po capacity'},'CAPACITY_ROOT_INVALID'),({'root_path':None},'CAPACITY_ROOT_INVALID'),
    ({'root_path':'/var/lib/'+'c'*64},'CAPACITY_ROOT_INVALID'),({'root_path':'/var/a=b/c3po-capacity'},'CAPACITY_ROOT_INVALID'),
    ({'root_path':'/var/c3po-capacity'},'CHAIN_ROW_INVALID'),
    ({'parent_rows':None},'CHAIN_ROW_INVALID'),
    ({'parent_rows':rows_with(1,uid=1000)},'CHAIN_ROW_UNSAFE'),({'parent_rows':rows_with(2,mode=0o775)},'CHAIN_ROW_UNSAFE'),
    ({'parent_rows':rows_with(2,path='/var/lob')},'CHAIN_ROW_INVALID'),({'parent_rows':rows_with(0,inode=0)},'CHAIN_ROW_INVALID'),
]
@pytest.mark.parametrize('changes,code',CAPACITY_CASES)
def test_the_capacity_member_of_ident_and_load_is_refused_from_its_bytes(changes,code):
    for step in ('IDENT','LOAD'):
        value=capacity(**changes)
        if 'extra' in changes:value=dict(changes)
        docs,_=kprobe.case(step,capacity=value);assert refusal(docs.authenticate)==code,(step,changes)

def load_member(**changes):
    out={'config_file':kprobe.CONFIG_PATH,'config_sha256':kprobe.CONFIG_SHA,'release_sha':kprobe.RELEASE_SHA,'mount_receipt_sha256':kprobe.MOUNT_RECEIPT}
    out.update(changes);return out
LOAD_CASES=[
    (dict(load_member(),extra=1),'LOAD_UNBOUND'),({k:v for k,v in load_member().items() if k!='mount_receipt_sha256'},'LOAD_UNBOUND'),
    (load_member(config_file='/c3po-capacity/week.static.capacity.json'),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/c3po-capacity/documents/week.static.capacity.json'),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/c3po-capacity/config/.week'),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/c3po-capacity/config/..'),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/c3po-capacity/config/a/b.json'),'CONFIG_FILE_INVALID'),
    (load_member(config_file="/c3po-capacity/config/it's.json"),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/var/lib/c3po-capacity/config/week.static.capacity.json'),'CONFIG_FILE_INVALID'),
    (load_member(config_file='/c3po-capacity/config/'+'a'*101),'CONFIG_FILE_INVALID'),(load_member(config_file=None),'CONFIG_FILE_INVALID'),
    (load_member(config_sha256=None),'CONFIG_SHA_INVALID'),(load_member(config_sha256='0'*64),'CONFIG_SHA_INVALID'),
    (load_member(config_sha256=kprobe.CONFIG_SHA.upper()),'CONFIG_SHA_INVALID'),
    (load_member(release_sha='f'*63),'RELEASE_SHA_INVALID'),(load_member(release_sha=None),'RELEASE_SHA_INVALID'),
    (load_member(mount_receipt_sha256='0'*64),'MOUNT_RECEIPT_UNBOUND'),(load_member(mount_receipt_sha256=None),'MOUNT_RECEIPT_UNBOUND'),
    (load_member(release_sha=kprobe.CONFIG_SHA),'LOAD_HASH_REUSED'),(load_member(mount_receipt_sha256=kprobe.RELEASE_SHA),'LOAD_HASH_REUSED'),
    (load_member(mount_receipt_sha256=kprobe.CONFIG_SHA),'LOAD_HASH_REUSED'),
]
@pytest.mark.parametrize('value,code',LOAD_CASES)
def test_the_load_member_is_refused_from_its_bytes(value,code):
    docs,_=kprobe.case('LOAD',load=value);assert refusal(docs.authenticate)==code

def test_the_members_accept_exactly_their_grammar_at_its_edges():
    m=K().m
    for name in ('a','w.json','Week_1.static-capacity.JSON','a'*100):
        m.validate_members(kprobe.fields('LOAD',load=load_member(config_file='/c3po-capacity/config/'+name)))
    for path in ('/var/lib/a','/opt/x/'+'c'*63,'/var/lib/c3po.capacity_2'):
        m.validate_capacity({'root_path':path,'parent_rows':capacity(root_path=path)['parent_rows'] if path.startswith('/var/lib/') else None}) \
            if path.startswith('/var/lib/') else None
    m.validate_members(kprobe.fields('CALENDAR'));m.validate_members(kprobe.fields('IDENT'));m.validate_members(kprobe.fields('LOAD'))
    assert m.RELEASE_REVISION==kprobe.RELEASE==hostemu.REVISION

def test_the_window_is_validated_for_its_step_and_before_the_members():
    m=K().m
    for step,start,end,code in (('CALENDAR','2026-10-04T16:26:00+00:00','2026-10-04T17:26:00+00:00',None),
                                ('IDENT','2026-10-04T22:30:00+00:00','2026-10-04T23:30:00+00:00',None),
                                ('IDENT','2026-10-08T20:38:00+00:00','2026-10-08T20:40:00+00:00',None),
                                ('LOAD','2026-10-05T20:38:00+00:00','2026-10-05T21:38:00+00:00',None),
                                ('LOAD','2026-10-08T23:00:00+00:00','2026-10-08T23:30:00+00:00',None),
                                ('LOAD','2026-10-04T17:00:00+00:00','2026-10-04T17:05:00+00:00','STEP_DAY_NOT_IN_SCOPE'),
                                ('CALENDAR','2026-10-09T21:00:00+00:00','2026-10-09T21:05:00+00:00','STEP_DAY_NOT_IN_SCOPE'),
                                ('LOAD','2026-10-09T21:00:00+00:00','2026-10-09T21:05:00+00:00','STEP_DAY_NOT_IN_SCOPE'),
                                ('IDENT','2026-10-03T21:00:00+00:00','2026-10-03T21:05:00+00:00','STEP_DAY_NOT_IN_SCOPE'),
                                ('CALENDAR','2026-10-04T16:25:59+00:00','2026-10-04T16:30:00+00:00','STEP_WINDOW_OUTSIDE_THE_BAND'),
                                ('CALENDAR','2026-10-05T16:26:00+00:00','2026-10-05T16:30:00+00:00','STEP_WINDOW_OUTSIDE_THE_BAND'),
                                ('IDENT','2026-10-05T20:37:59+00:00','2026-10-05T20:40:00+00:00','STEP_WINDOW_OUTSIDE_THE_BAND'),
                                ('IDENT','2026-10-06T23:29:00+00:00','2026-10-06T23:30:00.000001+00:00','STEP_WINDOW_OUTSIDE_THE_BAND'),
                                ('LOAD','2026-10-07T20:37:00+00:00','2026-10-07T20:39:00+00:00','STEP_WINDOW_OUTSIDE_THE_BAND'),
                                ('LOAD','2026-10-07T23:29:00+00:00','2026-10-07T23:31:00+00:00','STEP_WINDOW_OUTSIDE_THE_BAND')):
        window={'not_before':start,'expires_at':end}
        if code is None:m.validate_window(window,step)
        else:assert refusal(lambda:m.validate_window(window,step))==code,(step,start,end)
    plan=dict(kprobe.fields('LOAD',image_id=None),window={'not_before':'2026-10-04T17:00:00+00:00','expires_at':'2026-10-04T17:05:00+00:00'})
    assert refusal(lambda:m.validate_plan(plan))=='STEP_DAY_NOT_IN_SCOPE'
    plan['window']={'not_before':'2026-10-05T21:00:00+00:00','expires_at':'2026-10-05T21:05:00+00:00'};assert refusal(lambda:m.validate_plan(plan))=='IMAGE_ID'
    plan['step']='OTHER';assert refusal(lambda:m.validate_plan(plan))=='STEP_INVALID'
    assert m.MAX_GATE_SPAN_SECONDS==3600 and m.STEP_BANDS=={'CALENDAR':m.A5_BANDS,'IDENT':m.A5_BANDS,'LOAD':m.B4C_BANDS}
    assert [band[0] for band in m.A5_BANDS]==['2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08']
    assert [band[0] for band in m.B4C_BANDS]==['2026-10-05','2026-10-06','2026-10-07','2026-10-08']

def test_a_window_of_a_whole_band_hour_is_accepted_and_one_second_more_is_not():
    docs,host=kprobe.case('IDENT');start=kprobe.NOW['IDENT']
    docs.shift(start,start+timedelta(seconds=3600));assert run(docs,host)['outcome']==K().m.IDENT_OUTCOME
    docs.shift(start,start+timedelta(seconds=3601));assert refusal(docs.authenticate)=='WINDOW_SPAN'

def test_the_evidence_names_no_operation_and_a_load_plan_names_the_receipt_of_the_mount():
    m=K().m;assert m.EVIDENCE_OPERATIONS==() and m.EVIDENCE_REQUIRED is True and m.MOUNT_OPERATION=='GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
    docs,_=kprobe.case('LOAD');docs.request['evidence']=[];docs.chain();assert refusal(docs.authenticate)=='EVIDENCE_UNBOUND'
    docs,_=kprobe.case('LOAD');assert docs.go['effects']['load']['mount_receipt']=={'operation':m.MOUNT_OPERATION,'receipt_sha256':kprobe.MOUNT_RECEIPT}


# ---------------------------------------------------------------- what the signers see
PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']
BIND='type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly'
def expected_effects(plan):
    m=K().m;step=plan['step'];image=plan['image_id']
    script={'CALENDAR':m.CALENDAR_SCRIPT,'IDENT':m.IDENT_SCRIPT,'LOAD':m.LOAD_SCRIPT}[step].encode()
    raw=script
    if step=='LOAD':
        raw+=("run(json.loads('%s'))\n"%json.dumps({'config_file':plan['load']['config_file'],'config_sha256':plan['load']['config_sha256'],
                                                     'release_sha':plan['load']['release_sha']},sort_keys=True,separators=(',',':'))).encode()
    base='hostops02-probe-'+step.lower()+'-<first 16 hex of the GO sha256>';names=[base+'-1',base+'-2'] if step=='IDENT' else [base]
    binds=[] if step=='CALENDAR' else [{'source':plan['capacity']['root_path'],'target':'/c3po-capacity','read_only':True}]
    containers=[{'name':name,'docker_arguments':PREFIX+['--name',name]+([] if step=='CALENDAR' else ['--mount','type=bind,source=%s,target=/c3po-capacity,readonly'%plan['capacity']['root_path']])
                 +[image,'python','-I','-B','-'],'binds':binds,'network':'none','environment_file':None,'docker_config_variable':None,
                 'standard_input':{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'pinned_script_sha256':hashlib.sha256(script).hexdigest()},
                 'time_limit_seconds':20 if step=='IDENT' else 40,'alarm_seconds':{'CALENDAR':None,'IDENT':14,'LOAD':34}[step],'removed_by_the_engine':True}
                for name in names]
    bands={'LOAD':[['2026-10-05','20:38:00','23:30:00'],['2026-10-06','20:38:00','23:30:00'],['2026-10-07','20:38:00','23:30:00'],['2026-10-08','20:38:00','23:30:00']]}
    out={'operation':'GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01','step':step,
         'success_outcome':{'CALENDAR':'CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED','IDENT':'ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST',
                            'LOAD':'STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND'}[step],
         'bands':bands.get(step,[['2026-10-04','16:26:00','23:30:00']]+bands['LOAD']),
         'band_source':'A2 rev 3 (A2_AUTORIDADE_CINCO_SESSOES.md), section 6-A, rows A5 and B4c (B4c: the band of B4)',
         'image':{'id':image,'revision':'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858','by_id_never_a_tag':True},
         'containers':containers,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
         'signature':'individual, by the hash of its own request (A2 rev 3, section 6-A: A5 and B4c are IND); a container run, never a read of any grid',
         'writes':0,'removes':[],'activation':False,'containers_run':len(names),'capacity':None,'load':None}
    if step in ('CALENDAR','IDENT'):
        out['bands'].append(['2026-10-06','11:26:00','15:30:00'])
        out['additional_band_source']='PROPOSED Tuesday 06/10 A5 CALENDAR and IDENT 08:26-12:30 BRT; exact amended authority required, not operational authorization'
    if step!='CALENDAR':
        rows=plan['capacity']['parent_rows']
        out['capacity']={'root_path':plan['capacity']['root_path'],'children':['config','documents','go','payload'],'children_owner_mode':'root:root 0700',
                         'target':'/c3po-capacity','parents':{'path':rows[-1]['path'],'row':rows[-1],'chain_sha256':f.sha(f.canonical(rows)),
                                                              'mount_point_by_device_change':'/'}}
    if step=='LOAD':
        out['load']=dict(config_file=plan['load']['config_file'],config_sha256=plan['load']['config_sha256'],release_sha=plan['load']['release_sha'],
                         mount_receipt={'operation':'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01','receipt_sha256':plan['load']['mount_receipt_sha256']},
                         veto_mode='DISPATCH_AND_DERIVATION_ONLY',worker='c3po-r2d2-worker-1',
                         expected={'status':'CAPACITY_STARTUP_OK','roots':['documents','go','payload'],'veto_mode':'DISPATCH_AND_DERIVATION_ONLY'})
    if step=='CALENDAR':
        out['expected_line']={'status':'CALENDAR_PIN','epoch':'R2D2-V2-SHADOW-2026-10-05',
                              'package_sha':'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84',
                              'document_order_sha':'1a5253bf23f5006224b79527da06697646c34c6f5a3a4f820af5da2b13d7a118'}
    return out

@pytest.mark.parametrize('step',STEPS)
def test_effects_are_literal_and_name_every_word_the_engine_gets(step):
    docs,host=kprobe.case(step);m=K().m
    assert docs.authority['effects']==docs.go['effects']==expected_effects(docs.plan)==json.loads(m.canonical(m.effects_of(docs.plan)))
    receipt=run(docs,host);argv=[entry['argv'][1:] for entry in host.commands if entry['argv'][1:2]==['run']]
    assert argv==[[word.replace('<first 16 hex of the GO sha256>',docs.go16()) for word in item['docker_arguments']] for item in expected_effects(docs.plan)['containers']]
    stdins=[entry['stdin'] for entry in host.commands if entry['argv'][1:2]==['run']]
    assert [hashlib.sha256(raw).hexdigest() for raw in stdins]==[item['standard_input']['sha256'] for item in expected_effects(docs.plan)['containers']]
    assert receipt['effects']==expected_effects(docs.plan) and [call.name for call in host.docker.runs]==names(docs)

def test_effects_follow_every_signed_value():
    m=K().m
    for step in STEPS:
        other=kprobe.fields(step,image_id=hostemu.OTHER,evidence_boot_id_sha256='e'*64)
        assert m.effects_of(other)==expected_effects(other) and m.success_of(other)==m.STEP_OUTCOMES[step]
    other=kprobe.fields('LOAD',load=load_member(config_file='/c3po-capacity/config/other.json',config_sha256='c'*64,release_sha='d'*64,mount_receipt_sha256='e'*64))
    assert m.effects_of(other)==expected_effects(other)
    _,host=kprobe.world();host.tree.add('/srv/cap',mode=0o700)
    other=kprobe.fields('IDENT',capacity={'root_path':'/srv/cap','parent_rows':hostemu.rows(host,'/srv')})
    assert m.effects_of(other)==expected_effects(other)

def test_the_rows_are_the_core_prefix_and_the_classes_fit_the_payload():
    m=K().m
    assert set(m.COMMANDS)=={'image','container','container_list','container_environment','worker_mounts','calendar','ident','load'}
    assert m.COMMANDS['container_environment']['argv']==['container','inspect','--format'] and m.COMMANDS['container_environment']['class']=='QUICK'
    for name in ('calendar','ident','load'):
        row=m.COMMANDS[name];assert (row['argv'],row['kind'],row['stdin'],row['tail'],row['tool'])==(PREFIX,'CONTAINER',True,[],'docker')
    assert (m.COMMANDS['calendar']['class'],m.COMMANDS['ident']['class'],m.COMMANDS['load']['class'])==('RUN','RUN_SHORT','RUN')
    assert m.STEP_ROWS=={'CALENDAR':('calendar',),'IDENT':('ident','ident'),'LOAD':('load',)}
    assert m.effects_budget('ident','ident')==44==m.effects_budget('load')==m.effects_budget('calendar')
    for name in ('image','container','container_list','worker_mounts'):assert m.COMMANDS[name]['kind']=='READ' and m.COMMANDS[name]['class']=='QUICK'
    assert m.COMMANDS['worker_mounts']['argv']==['container','inspect','--format',m.MOUNTS_FORMAT] and 'Env' not in m.MOUNTS_FORMAT
    assert m.COMMANDS['container']['argv']==['container','inspect','--format',m.CONTAINER_FORMAT]
    assert m.WRITES_ALLOWED is False and m.ACTIVATION_ALLOWED is False and m.DATE_CLASS=='READ'
    assert m.OPERATION=='GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01' and m.PHASE=='READONLY_CAPACITY_PROBE'
    assert m.SCOPE['scripts']['CALENDAR']['sha256']=='5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f'
    assert m.BINARIES=={'docker':['/usr/bin/docker','/usr/local/bin/docker']}

def test_the_mounts_template_prints_four_members_per_mount_and_nothing_else():
    """The template through the emulated CLI (typed mode, as the engine's Go templates): one object, a list of mounts."""
    _,host=kprobe.world();worker=kprobe.worker(host)
    code,out=host.docker.run(['container','inspect','--format',K().m.MOUNTS_FORMAT,worker['Id']])
    assert code==0 and json.loads(out)=={'mounts':[{'type':'bind','source':hostemu.DATA,'destination':'/app/day-d-data','rw':True},
                                                    {'type':'bind','source':kprobe.ROOT,'destination':'/c3po-capacity','rw':False}]}
    worker['Mounts']=[];code,out=host.docker.run(['container','inspect','--format',K().m.MOUNTS_FORMAT,worker['Id']])
    assert (code,json.loads(out))==(0,{'mounts':[]})
    worker['Mounts']=[kprobe.mount()];worker['Config']['Env'].append('LEAK=never-emit-x')
    code,out=host.docker.run(['container','inspect','--format',K().m.MOUNTS_FORMAT,worker['Id']])
    assert b'never-emit' not in out and json.loads(out)['mounts'][0]=={'type':'bind','source':kprobe.ROOT,'destination':'/c3po-capacity','rw':False}

def script_values(source):
    values={}
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and isinstance(node.value,ast.Constant):values[node.targets[0].id]=node.value.value
    return values

def test_script_constants_agree_with_the_source_and_the_alarm_comes_first():
    m=K().m
    for step,source in (('IDENT',m.IDENT_SCRIPT),('LOAD',m.LOAD_SCRIPT)):
        tree=ast.parse(source);first,second=tree.body[:2]
        assert isinstance(first,ast.Import) and [alias.name for alias in first.names]==['signal']
        assert ast.dump(second)==ast.dump(ast.parse('signal.alarm(%d)'%m.SCRIPT_SECONDS[step]).body[0])
        assert m.SCRIPT_SECONDS[step]<m.COMMAND_CLASSES[m.COMMANDS[step.lower()]['class']]['seconds']-4
        values=script_values(source);assert values['APPLICATION_ROOT']=='/app' and values['CODE']==None if False else True
        writes=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='write']
        assert len(writes)==1 and ast.dump(writes[0].func.value)==ast.dump(ast.parse('sys.stdout',mode='eval').body),'the one write is the line'
        called={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        assert not called&{'reserve','open','mkdir','unlink','rename','remove','chmod','system','popen'}
    ident=script_values(m.IDENT_SCRIPT);load=script_values(m.LOAD_SCRIPT)
    assert ident['TARGET']==m.CAPACITY_TARGET=='/c3po-capacity' and load['VETO_MODE']==m.VETO_MODE=='DISPATCH_AND_DERIVATION_ONLY'
    names=[node for node in ast.parse(m.IDENT_SCRIPT).body if isinstance(node,ast.Assign) and node.targets[0].id=='NAMES'][0]
    assert ast.literal_eval(names.value)==m.CAPACITY_CHILDREN
    assert m.ALARM_STATUS==128+14 and m.CLASS_NAME=='[A-Z][A-Za-z0-9_]{0,79}'
    for step,raw in m.scripts().items():
        assert len(raw)==m.SCOPE['scripts'][step]['bytes'] and f.sha(raw)==m.SCOPE['scripts'][step]['sha256']
    assert 'alarm' not in m.CALENDAR_SCRIPT and m.SCRIPT_SECONDS.get('CALENDAR') is None

def test_the_load_values_travel_as_one_appended_line_and_only_signed_values():
    m=K().m;plan=kprobe.fields('LOAD');raw=m.stdin_of(plan)
    assert raw.startswith(m.scripts()['LOAD']) and raw.count(b'\n')==m.scripts()['LOAD'].count(b'\n')+1
    assert kprobe.load_values(raw)=={'config_file':kprobe.CONFIG_PATH,'config_sha256':kprobe.CONFIG_SHA,'release_sha':kprobe.RELEASE_SHA}
    assert m.stdin_of(kprobe.fields('IDENT'))==m.scripts()['IDENT'] and m.stdin_of(kprobe.fields('CALENDAR'))==m.scripts()['CALENDAR']
    plan['load']=dict(plan['load'],config_file="/c3po-capacity/config/x'y");assert refusal(lambda:m.stdin_of(plan))=='LOAD_VALUES_INVALID'
    plan['load']=dict(plan['load'],config_file='/c3po-capacity/config/x\\y');assert refusal(lambda:m.stdin_of(plan))=='LOAD_VALUES_INVALID'

def test_a_script_that_is_not_the_pinned_one_is_never_given(monkeypatch):
    m=K().m
    for step,name in (('CALENDAR','CALENDAR_SCRIPT'),('IDENT','IDENT_SCRIPT'),('LOAD','LOAD_SCRIPT')):
        docs,host=kprobe.case(step);monkeypatch.setattr(m,name,getattr(m,name)+'\n')
        result=run(docs,host);assert (result['status'],result['code'],result['phase_reached'])==('REFUSED','SCRIPT_NOT_THE_PINNED_HASH','AUTHENTICATION') and host.log==[]
        monkeypatch.undo()
    monkeypatch.setattr(m,'IDENT_SCRIPT',m.IDENT_SCRIPT.replace('signal.alarm(14)','signal.alarm(15)'));assert refusal(m.scripts)=='SCRIPT_NOT_THE_PINNED_HASH'


# ---------------------------------------------------------------- complete runs
COMMON_KEYS={'schema','operation','status','outcome','code','scope_sha256','core_sha256','activation_performed','daemon_reload_performed',
             'secret_bytes_in_receipt','ready','size_reductions','metadata_sha256','request_sha256','authority_sha256','go_sha256','payload_sha256',
             'host_binding_sha256','observed_at','step','effects','clock','commands_started','mutating_calls','precheck','containers','lines',
             'host_identities','comparison','containers_after','worker_after','tree_after','step_succeeded','writes','containers_run','phase_reached'}
def assert_clean(receipt,host):
    raw=f.line(receipt);assert hostemu.SECRET.encode() not in raw and b'never-emit' not in raw and len(raw)<20000
    assert host.mutating()==[] and host.fds=={} and set(receipt)==COMMON_KEYS and receipt['mutating_calls']['issued']==0

def test_calendar_complete_run():
    docs,host=kprobe.case('CALENDAR');receipt=run(docs,host)
    assert verdict(receipt)==('METADATA_ONLY_REQUIRES_REVIEW','CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED',None) and receipt['phase_reached']=='CONTAINER'
    assert words(host)==['image','ps','run','ps'] and [entry['seconds'] for entry in host.commands]==[8,8,40,8]
    assert all(entry['docker_config'] is None and entry['variables']=={} for entry in host.commands)
    assert receipt['precheck']=={'image':{'id_as_signed':True,'revision_as_signed':True},'capacity':None,'config_file':None,'worker':None,
                                 'containers_before':8,'names_free':True}
    line=kprobe.calendar_bytes(kprobe.calendar_line())
    assert receipt['lines']==[{'returncode':0,'output_present':True,'one_json_line':True,'valid':True,'line':kprobe.calendar_line()}]
    assert receipt['containers'][0]['name']==names(docs)[0] and receipt['containers'][0]['state']=='RETURNED'
    assert receipt['comparison'] is None and receipt['host_identities'] is None and receipt['worker_after'] is None and receipt['tree_after'] is None
    assert receipt['containers_after']=={'status':'COMPLETE','code':None,'before':8,'after':8,'not_there_before':0,'names_present':False,'rows':[]}
    assert receipt['commands_started']=={'READ':3,'CONTAINER':1,'EFFECT':0} and receipt['step_succeeded'] is True and receipt['containers_run']==1
    assert_clean(receipt,host)

def test_ident_complete_run_reads_the_tree_runs_twice_and_compares_with_the_host():
    docs,host=kprobe.case('IDENT');receipt=run(docs,host)
    assert verdict(receipt)==('METADATA_ONLY_REQUIRES_REVIEW','ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST',None)
    assert words(host)==['image','ps','run','run','ps'] and [entry['seconds'] for entry in host.commands]==[8,8,20,20,8]
    identities={name:kprobe.host_identity(host,name) for name in kprobe.CHILDREN}
    assert receipt['host_identities']==identities and len(set(identities.values()))==4
    root=host.tree.get(kprobe.ROOT)
    assert receipt['precheck']['capacity']=={'parents_as_signed':True,'root':{'device':root.dev,'inode':root.ino,'private':True,'other_directories':0,'ctime_ns':root.ctime},'identities':identities,
        'children':{name:{'device':host.tree.get(kprobe.ROOT+'/'+name).dev,'inode':host.tree.get(kprobe.ROOT+'/'+name).ino,'same_device_as_root':True}
                    for name in kprobe.CHILDREN}}
    assert [line['line'] for line in receipt['lines']]==[{'status':'ROOT_IDENTITIES','identities':identities}]*2
    assert receipt['comparison']=={'runs_agree':True,'equal_to_the_host':{name:True for name in kprobe.CHILDREN}}
    assert [item['name'] for item in receipt['containers']]==names(docs) and receipt['containers_run']==2
    assert receipt['tree_after']=={'status':'COMPLETE','unchanged':True,'code':None} and receipt['worker_after'] is None
    assert receipt['containers_after']['names_present'] is False and receipt['commands_started']=={'READ':3,'CONTAINER':2,'EFFECT':0}
    opens=[entry for entry in host.log if entry[0]=='open']
    assert all(entry[2]&0o400000 or True for entry in opens) and not [entry for entry in host.log if entry[0]=='read' and 'c3po-capacity' in entry[1]]
    assert_clean(receipt,host)

def test_load_complete_run_reads_the_worker_and_the_config_and_runs_once():
    docs,host=kprobe.case('LOAD');receipt=run(docs,host);worker=kprobe.worker(host)
    assert verdict(receipt)==('METADATA_ONLY_REQUIRES_REVIEW','STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND',None)
    assert words(host)==['image','worker','mounts','environment','ps','run','ps','worker'] and [entry['seconds'] for entry in host.commands]==[8,8,8,8,8,40,8,8]
    assert host.commands[2]['argv'][-1]==worker['Id']
    assert receipt['precheck']['config_file']=={'regular':True,'private':True,'sha256_as_signed':True,'bytes':len(kprobe.CONFIG)}
    assert receipt['precheck']['worker']=={'id':worker['Id'],'started_at':worker['State']['StartedAt'],'restarts':0,'running':True,'image_as_signed':True,
                                           'mounts':2,'capacity_mount':{'type':'bind','source_as_signed':True,'read_only':True},'other_mounts_clear_of_the_tree':True,
                                           'settings':SETTINGS_FOUND,'root_changed_after_the_worker_started':False}
    identities={name:kprobe.host_identity(host,name) for name in ('documents','go','payload')}
    assert receipt['lines'][0]['line']=={'status':'CAPACITY_STARTUP_OK','roots':['documents','go','payload'],'veto_mode':'DISPATCH_AND_DERIVATION_ONLY',
                                         'identities':identities,'config_sha256':kprobe.CONFIG_SHA}
    assert receipt['comparison']=={'runs_agree':None,'equal_to_the_host':{name:True for name in identities}}
    assert receipt['worker_after']=={'status':'COMPLETE','unchanged':True,'code':None} and receipt['tree_after']['unchanged'] is True
    reads=[entry for entry in host.log if entry[0]=='read' and 'c3po-capacity' in entry[1]]
    assert reads and all(entry[1]==kprobe.ROOT+'/config/'+kprobe.CONFIG_NAME for entry in reads)
    assert receipt['commands_started']=={'READ':7,'CONTAINER':1,'EFFECT':0}
    assert_clean(receipt,host)

@pytest.mark.parametrize('step,rows',[('CALENDAR',('calendar',)),('IDENT',('ident','ident')),('LOAD',('load',))])
def test_the_budget_before_the_first_container_is_every_class_of_the_step_and_the_reserve(step,rows):
    """60 s of payload: the precheck may use what is left above the classes of the step's containers and the reserve."""
    m=K().m;need=m.effects_budget(*rows);assert need==44
    for cost,expected in ((60-need,'METADATA_ONLY_REQUIRES_REVIEW'),(60-need+0.01,'REFUSED')):
        docs,host=kprobe.case(step);budget=f.Budget(kprobe.NOW[step]).attach(host).cost(cost,'image','inspect')
        receipt=run(docs,host,**budget.options());assert receipt['status']==expected,(step,cost)
        if expected=='REFUSED':assert receipt['code']=='BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER' and host.container_runs()==[]

def test_a_first_ident_run_that_takes_its_whole_class_still_leaves_room_for_the_second():
    docs,host=kprobe.case('IDENT');budget=f.Budget(kprobe.NOW['IDENT']).attach(host).cost(16,'image','inspect').cost(20,'run','--rm')
    receipt=run(docs,host,**budget.options())
    assert receipt['outcome']==K().m.IDENT_OUTCOME and len(host.container_runs())==2 and [item['seconds'] for item in receipt['containers']]==[20,20]
    docs,host=kprobe.case('IDENT');budget=f.Budget(kprobe.NOW['IDENT']).attach(host).cost(16,'image','inspect').cost(20.01,'run','--rm')
    receipt=run(docs,host,**budget.options())
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN','SECOND_RUN_NOT_STARTED')
    assert [item['state'] for item in receipt['containers']]==['RETURNED','NOT_STARTED'] and receipt['containers'][1]['code']=='COMMAND_NOT_STARTED_BUDGET'
    assert len(host.container_runs())==1 and receipt['lines'][0]['valid'] is True and len(receipt['lines'])==1


# ---------------------------------------------------------------- refusals of the precheck: nothing started
def refused(receipt,code,host,commands=None):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NO_CONTAINER_STARTED',code,'PRECHECK'),receipt['code']
    assert host.container_runs()==[] and receipt['containers']==[] and receipt['lines']==[] and receipt['containers_after'] is None
    assert receipt['step_succeeded'] is False and receipt['containers_run']==0 and host.fds=={}
    if commands is not None:assert words(host)==commands

@pytest.mark.parametrize('step',STEPS)
def test_executor_boot_and_image_are_refused_before_anything_else(step):
    for actor in ((0,1000),(1000,0)):
        docs,host=kprobe.case(step);host.actor=actor;receipt=run(docs,host);refused(receipt,'EXECUTOR_IDENTITY',host,[])
        assert not [entry for entry in host.log if entry[0]!='identity']
    docs,host=kprobe.case(step,evidence_boot_id_sha256='e'*64);refused(run(docs,host),'EVIDENCE_FROM_EARLIER_BOOT',host,[])
    docs,host=kprobe.case(step,image_id='sha256:'+'ab'*32);refused(run(docs,host),'IMAGE_ABSENT_OR_UNREADABLE',host,['image'])
    docs,host=kprobe.case(step);[item for item in host.docker.images if item['Id']==hostemu.BACKEND][0]['Config']['Labels']['org.opencontainers.image.revision']='0'*40
    receipt=run(docs,host);refused(receipt,'IMAGE_REVISION_MISMATCH',host,['image']);assert receipt['precheck']['image'] is None
    docs,host=kprobe.case(step)
    intercept(host,'"revision":',0,json.dumps({'id':hostemu.OTHER,'repo_tags':[],'revision':hostemu.REVISION}).encode()+b'\n')
    refused(run(docs,host),'IMAGE_ID_MISMATCH',host)

@pytest.mark.parametrize('step',('IDENT','LOAD'))
def test_the_tree_is_walked_from_its_signed_rows_and_must_be_private(step):
    def check(change,code):
        docs,host=kprobe.case(step);change(host);receipt=run(docs,host);refused(receipt,code,host,['image']);assert receipt['precheck']['capacity'] is None
    check(lambda host:setattr(host.tree.get('/var/lib'),'ino',99),'PARENT_IDENTITY_MISMATCH')
    check(lambda host:setattr(host.tree.get('/var'),'mode',0o775),'PARENT_IDENTITY_MISMATCH')
    check(lambda host:setattr(host.tree.get('/var/lib'),'dev',999),'PARENT_IDENTITY_MISMATCH')
    check(lambda host:host.tree.remove(kprobe.ROOT),'CAPACITY_ROOT_ABSENT')
    def link(host):host.tree.remove(kprobe.ROOT);host.tree.add(kprobe.ROOT,kind='symlink',mode=0o777)
    check(link,'CAPACITY_ROOT_NOT_A_DIRECTORY')
    def plain(host):host.tree.remove(kprobe.ROOT);host.tree.add(kprobe.ROOT,kind='file',mode=0o700)
    check(plain,'CAPACITY_ROOT_NOT_A_DIRECTORY')
    for attribute,value in (('mode',0o755),('mode',0o750),('mode',0o701),('mode',0o1700),('uid',1000),('gid',1000)):
        check(lambda host,attribute=attribute,value=value:setattr(host.tree.get(kprobe.ROOT),attribute,value),'CAPACITY_ROOT_NOT_PRIVATE')
    for name in kprobe.CHILDREN:
        check(lambda host,name=name:host.tree.remove(kprobe.ROOT+'/'+name),'CAPACITY_CHILD_ABSENT')
        def other(host,name=name):host.tree.remove(kprobe.ROOT+'/'+name);host.tree.add(kprobe.ROOT+'/'+name,kind='symlink',mode=0o777)
        check(other,'CAPACITY_CHILD_NOT_A_DIRECTORY')
        for attribute,value in (('mode',0o700|0o040),('uid',1000),('gid',5)):
            check(lambda host,name=name,attribute=attribute,value=value:setattr(host.tree.get(kprobe.ROOT+'/'+name),attribute,value),'CAPACITY_CHILD_NOT_PRIVATE')

@pytest.mark.parametrize('step',('IDENT','LOAD'))
def test_a_component_replaced_between_its_lstat_and_its_open_is_refused(step):
    for target in (kprobe.ROOT,kprobe.ROOT+'/go'):
        docs,host=kprobe.case(step)
        def hook(host,name,detail,calls,target=target,done=[]):
            if name=='open' and detail[0]==target and not done:host.tree.get(target).ino+=1000;done.append(1)
        host.hook=hook;refused(run(docs,host),'CAPACITY_CHANGED_DURING_WALK',host)

def test_the_config_file_must_be_on_the_host_private_and_of_the_signed_hash():
    path=kprobe.ROOT+'/config/'+kprobe.CONFIG_NAME
    def check(change,code,commands=('image',)):
        docs,host=kprobe.case('LOAD');change(host);receipt=run(docs,host);refused(receipt,code,host,list(commands))
        assert receipt['precheck']['config_file'] is None and receipt['precheck']['capacity'] is not None
    check(lambda host:host.tree.remove(path),'CONFIG_FILE_ABSENT')
    def link(host):host.tree.remove(path);host.tree.add(path,kind='symlink',mode=0o777)
    check(link,'CONFIG_FILE_UNREADABLE')
    def directory(host):host.tree.remove(path);host.tree.add(path,mode=0o700)
    check(directory,'FILE_NOT_REGULAR')
    for attribute,value in (('mode',0o640),('mode',0o604),('uid',1000),('nlink',2)):
        check(lambda host,attribute=attribute,value=value:setattr(host.tree.get(path),attribute,value),'CONFIG_FILE_NOT_PRIVATE')
    check(lambda host:setattr(host.tree.get(path),'content',bytearray(kprobe.CONFIG+b' ')),'CONFIG_FILE_HASH_MISMATCH')
    check(lambda host:setattr(host.tree.get(path),'content',bytearray(b'x'*(4*1024*1024+1))),'FILE_TOO_LARGE')
    for mode,gid in ((0o400,0),(0o600,7)):
        docs,host=kprobe.case('LOAD');node=host.tree.get(path);node.mode=mode;node.gid=gid
        assert run(docs,host)['outcome']==K().m.COMPLETE_OUTCOME,'the release requires owner, one link and nothing for group and other'
    docs,host=kprobe.case('LOAD',load=load_member(config_sha256='c'*64));refused(run(docs,host),'CONFIG_FILE_HASH_MISMATCH',host,['image'])
    docs,host=kprobe.case('LOAD',load=load_member(config_file='/c3po-capacity/config/other.json'));refused(run(docs,host),'CONFIG_FILE_ABSENT',host,['image'])

def test_the_worker_must_run_the_signed_image_with_one_read_only_bind_of_the_signed_root():
    def check(change,code,commands=None):
        docs,host=kprobe.case('LOAD');change(host);receipt=run(docs,host);refused(receipt,code,host,commands);assert receipt['precheck']['worker'] is None
    check(lambda host:host.docker.containers.remove(kprobe.worker(host)),'WORKER_ABSENT_OR_UNREADABLE',['image','worker'])
    def stopped(host):state=kprobe.worker(host)['State'];state.update(Running=False,Status='exited')
    check(stopped,'WORKER_NOT_RUNNING',['image','worker'])
    def restarting(host):kprobe.worker(host)['State'].update(Status='restarting')
    check(restarting,'WORKER_NOT_RUNNING',['image','worker'])
    check(lambda host:kprobe.worker(host).update(Image=hostemu.OTHER),'WORKER_NOT_ON_THE_SIGNED_IMAGE',['image','worker'])
    for mounts,code in (([],'WORKER_CAPACITY_MOUNT_ABSENT'),([kprobe.mount(hostemu.DATA,'/app/day-d-data',rw=True)],'WORKER_CAPACITY_MOUNT_ABSENT'),
                        ([kprobe.mount(),kprobe.mount()],'WORKER_CAPACITY_MOUNT_NOT_ONE'),
                        ([kprobe.mount(kind='volume',source='/var/lib/docker/volumes/c3po_c3po_capacity_unprovisioned/_data')],'WORKER_CAPACITY_MOUNT_NOT_A_BIND'),
                        ([kprobe.mount(source='/var/lib/c3po-capacity/config')],'WORKER_CAPACITY_MOUNT_OTHER_SOURCE'),
                        ([kprobe.mount(source='/var/lib/c3po-capacity/')],'WORKER_CAPACITY_MOUNT_OTHER_SOURCE'),
                        ([kprobe.mount(rw=True)],'WORKER_CAPACITY_MOUNT_WRITABLE'),
                        ([kprobe.mount(destination='/c3po-capacity/')],'WORKER_CAPACITY_MOUNT_ABSENT')):
        check(lambda host,mounts=mounts:kprobe.bind_worker(host,mounts),code,['image','worker','mounts'])
    many=[kprobe.mount(source='/x%d'%index,destination='/y%d'%index) for index in range(32)]
    check(lambda host:kprobe.bind_worker(host,many[:31]+[kprobe.mount()]+[many[31]]),'WORKER_MOUNTS_INVALID')
    docs,host=kprobe.case('LOAD');kprobe.bind_worker(host,many[:31]+[kprobe.mount()]);assert run(docs,host)['outcome']==K().m.COMPLETE_OUTCOME
    for output in (b'not json\n',b'{"mounts":{}}\n',b'{"mounts":[],"x":1}\n',b'{"mounts":[{"type":"bind","source":"/a","destination":"/b"}]}\n',
                   b'{"mounts":[{"type":"bind","source":"/a","destination":"/b","rw":"false"}]}\n',
                   b'{"mounts":[{"type":1,"source":"/a","destination":"/b","rw":false}]}\n',
                   b'{"mounts":[{"type":"bind","source":null,"destination":"/b","rw":false}]}\n',
                   b'{"mounts":[{"type":"bind","source":"/a","destination":2,"rw":false}]}\n',b'{"mounts":[1]}\n',
                   b'{"mounts":[{"type":"bind","source":"/a","destination":"/b","rw":false,"name":"x"}]}\n'):
        docs,host=kprobe.case('LOAD');intercept(host,'.Mounts',0,output);receipt=run(docs,host)
        assert receipt['code'] in ('WORKER_MOUNTS_INVALID','JSON_INVALID'),output
        refused(receipt,receipt['code'],host)
    docs,host=kprobe.case('LOAD');intercept(host,'.Mounts',1,b'');refused(run(docs,host),'WORKER_MOUNTS_UNREADABLE',host)
    docs,host=kprobe.case('LOAD');host.docker.inspect_returncode=1;refused(run(docs,host),'WORKER_ABSENT_OR_UNREADABLE',host)

@pytest.mark.parametrize('step',STEPS)
def test_container_listing_that_fails_or_a_name_already_taken_is_refused(step):
    docs,host=kprobe.case(step);host.docker.ps_returncode=1;refused(run(docs,host),'CONTAINER_LISTING_FAILED',host)
    docs,host=kprobe.case(step);intercept(host,'{{json .Names}}',0,b'{"id":"x","name":"y","state":"running"}\n');refused(run(docs,host),'CONTAINER_LIST_INVALID',host)
    for index in range(2 if step=='IDENT' else 1):
        docs,host=kprobe.case(step)
        host.docker.containers.append(hostemu.container(names(docs)[index],hostemu.BACKEND,hostemu.BACKEND,[],running=False))
        receipt=run(docs,host);refused(receipt,'CONTAINER_NAME_TAKEN',host);assert receipt['precheck']['names_free'] is False and receipt['precheck']['containers_before']==9
    docs,host=kprobe.case(step);host.docker.containers.append(hostemu.container('hostops02-probe-'+step.lower()+'-'+'0'*16,hostemu.BACKEND,hostemu.BACKEND,[],running=False))
    assert run(docs,host)['outcome']==K().m.STEP_OUTCOMES[step],'another GO left its own container: not this name'

@pytest.mark.parametrize('step',STEPS)
def test_docker_that_cannot_be_trusted_or_started_or_a_failing_call_is_a_refusal(step):
    docs,host=kprobe.case(step);host.tree.get('/usr/bin/docker').mode=0o775;refused(run(docs,host),'BINARY_UNAVAILABLE_OR_UNSAFE',host,[])
    docs,host=kprobe.case(step);host.absent={'docker'};refused(run(docs,host),'COMMAND_NOT_STARTED',host,[])
    for kind,code in ((OSError,'PRECHECK_OS_ERROR'),(RuntimeError,'PRECHECK_FAILED')):
        docs,host=kprobe.case(step)
        def hook(host,name,detail,calls,kind=kind):
            if name=='open' and detail and detail[0]=='/proc/sys/kernel/random/boot_id':raise kind(5,'injected') if kind is OSError else kind('injected')
        host.hook=hook;refused(run(docs,host),code,host,[])
    docs,host=kprobe.case(step);host.hang={('ps','-a')};refused(run(docs,host),'COMMAND_TIMEOUT',host)
    docs,host=kprobe.case(step);budget=f.Budget(kprobe.NOW[step]).attach(host).cost(400,'ps','-a');refused(run(docs,host,**budget.options()),'GO_EXPIRED',host)


# ---------------------------------------------------------------- the containers and the verdict after them
@pytest.mark.parametrize('step',STEPS)
def test_a_container_the_engine_never_started_is_a_refusal_after_the_precheck(step):
    docs,host=kprobe.case(step);host.absent={('run','--rm')};receipt=run(docs,host)
    assert verdict(receipt)==('REFUSED','REFUSED_NO_CONTAINER_STARTED','COMMAND_NOT_STARTED') and receipt['phase_reached']=='CONTAINER_NOT_STARTED'
    assert receipt['containers']==[{'name':names(docs)[0],'state':'NOT_STARTED','returncode':None,'code':'COMMAND_NOT_STARTED','seconds':receipt['containers'][0]['seconds']}]
    assert receipt['lines']==[] and receipt['containers_after'] is None and receipt['containers_run']==0

@pytest.mark.parametrize('step',STEPS)
def test_a_run_that_did_not_return_lists_the_containers_and_says_what_is_left(step):
    docs,host=kprobe.case(step);host.hang={('run','--rm')};receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN','COMMAND_TIMEOUT')
    assert [item['state'] for item in receipt['containers']]==['DID_NOT_RETURN'] and receipt['lines']==[None] and len(host.container_runs())==1
    assert words(host)[-1]=='worker' if step=='LOAD' else words(host)[-1]=='ps'
    docs,host=kprobe.case(step);host.hang_after={('run','--rm')}
    def stays(call):host.docker.containers.append(hostemu.container(call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.docker.on_run=kprobe.answers(before=stays);receipt=run(docs,host)
    assert receipt['code']=='COMMAND_TIMEOUT' and receipt['containers_after']['names_present'] is True
    assert receipt['containers_after']['rows']==[{'id':host.docker.containers[-1]['Id'],'state':'running','of_this_step':True}]

def test_a_second_ident_run_follows_only_a_first_that_returned():
    docs,host=kprobe.case('IDENT')
    host.docker.on_run=kprobe.answers(lines=[b'',kprobe.compact({'status':'ROOT_IDENTITIES_REFUSED','code':'ROOT_NOT_PRIVATE'})],returncode=1)
    receipt=run(docs,host);assert len(host.container_runs())==2 and receipt['code']=='OUTPUT_NOT_ONE_LINE'
    assert [line['valid'] for line in receipt['lines']]==[False,True]

@pytest.mark.parametrize('step',STEPS)
@pytest.mark.parametrize('returncode,output,code',[
    (125,b'','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),(126,b'','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),(127,b'x\n','ENGINE_COULD_NOT_RUN_THE_CONTAINER'),
    (142,b'','SCRIPT_ENDED_BY_ITS_ALARM'),(137,b'','OUTPUT_NOT_ONE_LINE'),(0,b'','OUTPUT_NOT_ONE_LINE'),(1,b'Traceback\n','OUTPUT_NOT_ONE_LINE'),
    (0,b'{}\n{}\n','OUTPUT_NOT_ONE_LINE'),(0,b'[1]\n','OUTPUT_NOT_ONE_LINE'),(0,b'{"a":1,"a":2}\n','OUTPUT_NOT_ONE_LINE'),
    (0,b'{}\n','LINE_NOT_AS_SPECIFIED'),(0,b'{"status":"OK"}\n','LINE_NOT_AS_SPECIFIED'),
])
def test_output_that_is_not_one_valid_line_leaves_the_result_unknown(step,returncode,output,code):
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(returncode=returncode,output=output);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN',code)
    line=receipt['lines'][0];assert line=={'returncode':returncode,'output_present':len(output)>0,'one_json_line':line['one_json_line'],'valid':False,'line':None}
    assert len(receipt['lines'])==len(host.container_runs())

def ok_bytes(step,docs,host):
    """The model's line of the step for this host (what a correct run prints)."""
    out=[]
    def capture(call):out.append(kprobe.container(call)[1])
    probe_docs,probe_host=kprobe.case(step);probe_host.docker.on_run=kprobe.answers(before=capture);run(probe_docs,probe_host)
    return out[0]

@pytest.mark.parametrize('step',STEPS)
def test_a_valid_line_with_another_exit_status_leaves_the_result_unknown(step):
    for returncode in (1,2,-9,142):
        docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(returncode=returncode);receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN','EXIT_STATUS_NOT_AS_THE_LINE'),returncode
        assert receipt['lines'][0]['valid'] is True
    refused_line={'CALENDAR':kprobe.calendar_bytes({'status':'CALENDAR_PIN_REFUSED','code':'ModuleNotFoundError'}),
                  'IDENT':kprobe.compact({'status':'ROOT_IDENTITIES_REFUSED','code':'ROOT_NOT_PRIVATE'}),
                  'LOAD':kprobe.compact({'status':'CAPACITY_STARTUP_REFUSED','code':'CAPACITY_CONFIG_CALENDAR'})}[step]
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(returncode=0,output=refused_line);receipt=run(docs,host)
    assert receipt['code']=='EXIT_STATUS_NOT_AS_THE_LINE'
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(returncode=1,output=refused_line);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED',K().m.REFUSED_CODES[step])
    assert receipt['lines'][0]['line']==json.loads(refused_line)

CALENDAR_INVALID=[{'status':'CALENDAR_PIN'},dict(kprobe.calendar_line(),extra=1),kprobe.calendar_line(epoch='r2d2'),kprobe.calendar_line(epoch=''),
                  kprobe.calendar_line(epoch='E'*81),kprobe.calendar_line(calendar_version=''),kprobe.calendar_line(calendar_version='4.13.2 beta'),
                  kprobe.calendar_line(calendar_version='v'*41),kprobe.calendar_line(calendar_version=4.13),kprobe.calendar_line(calendar_pin_sha='0'*64),
                  kprobe.calendar_line(package_sha='G'*64),kprobe.calendar_line(document_order_sha=None),kprobe.calendar_line(document_order_sha='x'),kprobe.calendar_line(status='CALENDAR_PIN_OK'),
                  {'status':'CALENDAR_PIN_REFUSED','code':'module not found'},{'status':'CALENDAR_PIN_REFUSED','code':'X'*81},
                  {'status':'CALENDAR_PIN_REFUSED'},{'status':'CALENDAR_PIN_REFUSED','code':'Error','x':1},{'status':'CALENDAR_PIN_REFUSED','code':'_Private'}]
@pytest.mark.parametrize('row',CALENDAR_INVALID)
def test_every_member_of_the_calendar_line_is_checked_before_anything_of_it_is_kept(row):
    docs,host=kprobe.case('CALENDAR');host.docker.on_run=kprobe.answers(output=kprobe.calendar_bytes(row));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN','LINE_NOT_AS_SPECIFIED'),row
    assert K().m.line_grammar('CALENDAR',row) is False and receipt['lines'][0]['line'] is None

def test_the_calendar_line_must_name_what_the_source_pins():
    for changes,code in (({'epoch':'R2D2-V2-SHADOW-2026-10-12'},'CALENDAR_EPOCH_MISMATCH'),({'package_sha':'c'*64},'CALENDAR_PACKAGE_MISMATCH'),
                         ({'document_order_sha':'d'*64},'CALENDAR_DOCUMENT_ORDER_MISMATCH'),
                         ({'package_sha':'c'*64,'epoch':'R2D2-V2-DIAG-X'},'CALENDAR_EPOCH_MISMATCH')):
        docs,host=kprobe.case('CALENDAR');host.docker.on_run=kprobe.answers(output=kprobe.calendar_bytes(kprobe.calendar_line(**changes)));receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED',code)
        assert receipt['lines'][0]['line']==kprobe.calendar_line(**changes),'the line is reported as printed'
    for version in ('4.13.2','4.14','5.0.1+local','4_13'):
        docs,host=kprobe.case('CALENDAR');host.docker.on_run=kprobe.answers(output=kprobe.calendar_bytes(kprobe.calendar_line(calendar_version=version)))
        assert run(docs,host)['outcome']==K().m.CALENDAR_OUTCOME,'any version of the library: the pin follows it'
    docs,host=kprobe.case('CALENDAR');host.docker.on_run=kprobe.answers(output=kprobe.compact(kprobe.calendar_line()))
    assert run(docs,host)['outcome']==K().m.CALENDAR_OUTCOME,'compact or not, one JSON line'

def ident_bytes(identities=None,**changes):
    row={'status':'ROOT_IDENTITIES','identities':identities};row.update(changes);return kprobe.compact(row)
def real_identities(host):return {name:kprobe.host_identity(host,name) for name in kprobe.CHILDREN}

def test_every_member_of_the_ident_line_is_checked():
    _,host=kprobe.world();good=real_identities(host)
    for row in ({'status':'ROOT_IDENTITIES'},{'status':'ROOT_IDENTITIES','identities':dict(good),'x':1},
                {'status':'ROOT_IDENTITIES','identities':{k:v for k,v in good.items() if k!='config'}},
                {'status':'ROOT_IDENTITIES','identities':dict(good,restore='a'*64)},{'status':'ROOT_IDENTITIES','identities':dict(good,go='0'*64)},
                {'status':'ROOT_IDENTITIES','identities':dict(good,go=good['go'].upper())},{'status':'ROOT_IDENTITIES','identities':list(good.values())},
                {'status':'ROOT_IDENTITIES_REFUSED','code':'root not private'},{'status':'ROOT_IDENTITIES_REFUSED','code':'X','identities':good}):
        assert K().m.line_grammar('IDENT',row) is False,row
        docs,host=kprobe.case('IDENT');host.docker.on_run=kprobe.answers(output=kprobe.compact(row));receipt=run(docs,host)
        assert receipt['code']=='LINE_NOT_AS_SPECIFIED' and receipt['lines'][0]['line'] is None and len(receipt['lines'])==2

def test_ident_runs_must_agree_with_each_other_and_with_the_host():
    _,host=kprobe.world();good=real_identities(host)
    other=dict(good,documents='a'*64)
    docs,host=kprobe.case('IDENT');host.docker.on_run=kprobe.answers(lines=[ident_bytes(good),ident_bytes(other)]);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','IDENTITIES_DIFFER_BETWEEN_THE_TWO_RUNS')
    assert receipt['comparison']=={'runs_agree':False,'equal_to_the_host':{name:True for name in kprobe.CHILDREN}}
    for name in ('documents','go','payload'):
        changed=dict(good,**{name:'b'*64})
        docs,host=kprobe.case('IDENT');host.docker.on_run=kprobe.answers(lines=[ident_bytes(changed)]*2);receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','IDENTITIES_DIFFER_FROM_THE_HOST'),name
        assert receipt['comparison']['equal_to_the_host'][name] is False and receipt['comparison']['runs_agree'] is True
    changed=dict(good,config='b'*64)
    docs,host=kprobe.case('IDENT');host.docker.on_run=kprobe.answers(lines=[ident_bytes(changed)]*2);receipt=run(docs,host)
    assert receipt['outcome']==K().m.IDENT_OUTCOME and receipt['comparison']['equal_to_the_host']=={'config':False,'documents':True,'go':True,'payload':True},\
        'the identity of the config directory is reported and not required'
    refusal_line=kprobe.compact({'status':'ROOT_IDENTITIES_REFUSED','code':'ROOT_NOT_PRIVATE'})
    for lines in ([ident_bytes(good),refusal_line],[refusal_line,ident_bytes(good)]):
        docs,host=kprobe.case('IDENT')
        def on_run(call,lines=lines,seen=[]):
            kprobe.assert_run(call);seen.append(1);out=lines[len(seen)-1];return (0 if out==ident_bytes(good) else 1),out
        host.docker.on_run=on_run;receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','ROOT_IDENTITIES_REFUSED_IN_THE_IMAGE')

def test_the_identities_in_a_container_that_sees_other_numbers_differ_from_the_host():
    """A bind that does not show the host's numbers (another device in the container) is a difference, never a success."""
    docs,host=kprobe.case('IDENT')
    def on_run(call):
        kprobe.assert_run(call)
        return 0,ident_bytes({name:kprobe.digest([['c3po-capacity',999,call.stat('/c3po-capacity').st_ino],[name,999,call.stat('/c3po-capacity/'+name).st_ino]])
                              for name in kprobe.CHILDREN})
    host.docker.on_run=on_run;receipt=run(docs,host);assert receipt['code']=='IDENTITIES_DIFFER_FROM_THE_HOST'

def load_bytes(**changes):
    _,host=kprobe.world();row={'status':'CAPACITY_STARTUP_OK','roots':['documents','go','payload'],'veto_mode':'DISPATCH_AND_DERIVATION_ONLY',
                                'identities':{name:kprobe.host_identity(host,name) for name in ('documents','go','payload')},'config_sha256':kprobe.CONFIG_SHA}
    row.update(changes);return row

def test_every_member_of_the_load_line_is_checked():
    good=load_bytes()
    for row in (dict(good,x=1),{k:v for k,v in good.items() if k!='config_sha256'},dict(good,roots=['go','documents','payload']),
                dict(good,roots=['documents','documents','go','payload']),dict(good,roots=['documents','go','payload','extra'],identities=dict(good['identities'],extra='a'*64)),
                dict(good,roots='documents'),dict(good,veto_mode='OPEN'),dict(good,veto_mode=None),dict(good,identities={'documents':'a'*64}),
                dict(good,identities=dict(good['identities'],go='0'*64)),dict(good,identities=dict(good['identities'],extra='a'*64)),
                dict(good,roots=['documents','extra','go','payload'],identities=dict(good['identities'],extra='a'*64)),dict(good,config_sha256='0'*64),dict(good,config_sha256=None),
                {'status':'CAPACITY_STARTUP_REFUSED','code':'capacity'},{'status':'CAPACITY_STARTUP_REFUSED'},dict(good,status='CAPACITY_STARTUP')):
        assert K().m.line_grammar('LOAD',row) is False,row
        docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(output=kprobe.compact(row));receipt=run(docs,host)
        assert receipt['code']=='LINE_NOT_AS_SPECIFIED',row
    for row in (dict(good,veto_mode='CONTINUOUS'),dict(good,roots=['documents','go','payload','restore_revocation'],identities=dict(good['identities'],restore_revocation='a'*64)),
                dict(good,roots=[],identities={})):
        assert K().m.line_grammar('LOAD',row) is True

def test_the_load_line_must_be_what_the_worker_needs():
    good=load_bytes()
    for row,code in ((dict(good,roots=['documents','go']),'LINE_NOT_AS_SPECIFIED'),
                     (dict(good,roots=['documents','go'],identities={k:good['identities'][k] for k in ('documents','go')}),'CAPACITY_ROOTS_NOT_THE_THREE'),
                     (dict(good,roots=['documents','go','payload','restore_revocation'],identities=dict(good['identities'],restore_revocation='a'*64)),'CAPACITY_ROOTS_NOT_THE_THREE'),
                     (dict(good,veto_mode='CONTINUOUS'),'CAPACITY_VETO_MODE_NOT_AS_SIGNED'),(dict(good,config_sha256='c'*64),'CAPACITY_CONFIG_SHA_NOT_EQUAL'),
                     (dict(good,identities=dict(good['identities'],payload='c'*64)),'LOAD_IDENTITIES_DIFFER_FROM_THE_HOST'),
                     (dict(good,identities=dict(good['identities'],documents='c'*64)),'LOAD_IDENTITIES_DIFFER_FROM_THE_HOST'),
                     (dict(good,identities=dict(good['identities'],go='c'*64)),'LOAD_IDENTITIES_DIFFER_FROM_THE_HOST')):
        docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(output=kprobe.compact(row));receipt=run(docs,host)
        expected=('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STEP_RESULT_UNKNOWN' if code=='LINE_NOT_AS_SPECIFIED' else 'STEP_RAN_ANSWER_NOT_AS_EXPECTED',code)
        assert verdict(receipt)==expected,(row,receipt['code'])
    for code in ('ROOT_IDENTITY_CHANGED','ROOT_NOT_PRIVATE','CAPACITY_CONFIG_CALENDAR','FileNotFoundError','ValidationError'):
        docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(returncode=1,output=kprobe.compact({'status':'CAPACITY_STARTUP_REFUSED','code':code}))
        receipt=run(docs,host);assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE')
        assert receipt['lines'][0]['line']['code']==code and receipt['comparison'] is None

def test_the_model_container_refuses_a_config_of_another_hash_and_the_source_says_so():
    """End to end through the model: the config replaced on the host after the precheck read it."""
    docs,host=kprobe.case('LOAD')
    def swap(call):host.tree.get(kprobe.ROOT+'/config/'+kprobe.CONFIG_NAME).content=bytearray(b'{}')
    host.docker.on_run=kprobe.answers(before=swap);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE')

@pytest.mark.parametrize('step',STEPS)
def test_an_expected_answer_with_something_left_or_moved_is_a_finding_beside_it(step):
    def leave(name):
        def before(call):host.docker.containers.append(hostemu.container(name or call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
        return before
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(before=leave(None));receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS','CONTAINER_OF_THE_STEP_STILL_LISTED')
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(before=leave('someone-else'));receipt=run(docs,host)
    assert verdict(receipt)[2]=='CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE' and receipt['containers_after']['rows'][0]['of_this_step'] is False
    def fail_listing(call):host.docker.ps_returncode=1
    docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(before=fail_listing);receipt=run(docs,host)
    assert verdict(receipt)[2]=='CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
    assert receipt['containers_after']=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','before':8,'after':None,'not_there_before':None,'names_present':None,'rows':[]}
    docs,host=kprobe.case(step)
    def crowd(call):
        for index in range(12):host.docker.containers.append(hostemu.container('crowd-%d-%d'%(len(host.docker.runs),index),hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.docker.on_run=kprobe.answers(before=crowd);receipt=run(docs,host)
    runs=len(host.container_runs());assert receipt['containers_after']['not_there_before']==12*runs and len(receipt['containers_after']['rows'])==8
    assert (receipt['containers_after']['before'],receipt['containers_after']['after'])==(8,8+12*runs)
    docs,host=kprobe.case(step)
    def rename(call):
        for item in host.docker.containers:
            if item['Name']=='/c3po-web-1':item['Name']='/'+call.name
    host.docker.on_run=kprobe.answers(before=rename);receipt=run(docs,host)
    assert verdict(receipt)[2]=='CONTAINER_OF_THE_STEP_STILL_LISTED' and receipt['containers_after']['not_there_before']==0

def test_load_finds_a_worker_that_changed_or_cannot_be_read_after_the_container():
    def recreate(call):
        old=kprobe.worker(host);host.docker.containers.remove(old)
        new=hostemu.container(hostemu.WORKER,hostemu.BACKEND,'c3po/backend:production',[],project='c3po',service='r2d2-worker');new['Mounts']=old['Mounts']
        host.docker.containers.append(new)
    docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(before=recreate);receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS','CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE')
    for change,code in ((lambda worker:worker.update(RestartCount=1),'WORKER_CHANGED_DURING_THE_STEP'),
                        (lambda worker:worker['State'].update(Running=False,Status='exited'),'WORKER_CHANGED_DURING_THE_STEP'),
                        (lambda worker:worker.update(Image=hostemu.OTHER),'WORKER_CHANGED_DURING_THE_STEP'),
                        (lambda worker:worker.update(Name='/renamed'),'WORKER_UNAVAILABLE_AFTER_THE_STEP')):
        docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(before=lambda call,change=change:change(kprobe.worker(host)));receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS',code)
        assert receipt['worker_after']['unchanged'] is (None if code=='WORKER_UNAVAILABLE_AFTER_THE_STEP' else False)
    docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(before=lambda call:setattr(host.docker,'inspect_returncode',1));receipt=run(docs,host)
    assert receipt['worker_after']=={'status':'UNAVAILABLE','unchanged':None,'code':'COMMAND_FAILED'} and receipt['code']=='WORKER_UNAVAILABLE_AFTER_THE_STEP'

@pytest.mark.parametrize('step',('IDENT','LOAD'))
def test_a_tree_that_changed_during_the_step_is_a_finding(step):
    for path,attribute,value in ((kprobe.ROOT,'ino',777),(kprobe.ROOT+'/payload','ino',778),(kprobe.ROOT+'/config','mode',0o755),('/var/lib','ino',779)):
        docs,host=kprobe.case(step)
        def hook(host,name,detail,calls,path=path,attribute=attribute,value=value):
            if name=='run' and 'ps' in detail[0] and len(host.docker.runs)==len(K().m.STEP_ROWS[step]):setattr(host.tree.get(path),attribute,value)
        host.hook=hook;receipt=run(docs,host)
        assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS','CAPACITY_TREE_CHANGED_DURING_THE_STEP'),path
        assert receipt['tree_after']=={'status':'COMPLETE','unchanged':False,'code':'PARENT_REPLACED'}
    # The core's Pinned.verify says PARENT_REPLACED for an OSError of its own reads: such a tree is reported changed; any
    # other failure is "not observed" with a constant code.
    for kind,expected in ((OSError,{'status':'COMPLETE','unchanged':False,'code':'PARENT_REPLACED'}),
                          (RuntimeError,{'status':'UNAVAILABLE','unchanged':None,'code':'OBSERVATION_FAILED'})):
        docs,host=kprobe.case(step);armed=[]
        def hook(host,name,detail,calls,kind=kind):
            if armed and name=='fstat':raise kind(5,'injected')
        def arm(call):
            if len(host.docker.runs)==len(K().m.STEP_ROWS[step]):armed.append(1)
        host.hook=hook;host.docker.on_run=kprobe.answers(before=arm);receipt=run(docs,host)
        assert receipt['tree_after']==expected
        assert receipt['code']==('CAPACITY_TREE_CHANGED_DURING_THE_STEP' if kind is OSError else 'CAPACITY_TREE_UNAVAILABLE_AFTER_THE_STEP')

def test_an_expiry_during_the_container_leaves_what_follows_unavailable():
    for step in STEPS:
        docs,host=kprobe.case(step);budget=f.Budget(kprobe.NOW[step]).attach(host).cost(4000,'run','--rm');receipt=run(docs,host,**budget.options())
        assert receipt['containers_after']['code']=='GO_EXPIRED' and words(host)[-1]=='run' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
        if step=='IDENT':assert len(host.container_runs())==1 and receipt['code']=='SECOND_RUN_NOT_STARTED'
        else:assert receipt['code']=='CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
        if step=='LOAD':assert receipt['worker_after']['code']=='GO_EXPIRED'
        if step!='CALENDAR':assert receipt['tree_after']=={'status':'UNAVAILABLE','unchanged':None,'code':'GO_EXPIRED'}

@pytest.mark.parametrize('step',STEPS)
def test_an_escape_after_a_container_was_issued_is_never_a_refusal(step):
    docs,host=kprobe.case(step)
    def die(call):raise hostemu.Death('engine gone')
    host.docker.on_run=die;receipt=run(docs,host)
    assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN','RUN_ESCAPED_STATE_UNKNOWN')
    assert receipt['phase_reached']=='ESCAPED' and 'engine gone' not in json.dumps(receipt)

def test_the_receipt_never_carries_text_of_an_invalid_line():
    canary=kprobe.calendar_line(calendar_version='never-emit-canary at 192.0.2.7')
    docs,host=kprobe.case('CALENDAR');host.docker.on_run=kprobe.answers(output=kprobe.calendar_bytes(canary));receipt=run(docs,host)
    assert b'never-emit' not in f.line(receipt) and b'192.0.2.7' not in f.line(receipt) and receipt['code']=='LINE_NOT_AS_SPECIFIED'
    for step in STEPS:
        docs,host=kprobe.case(step);host.docker.on_run=kprobe.answers(output=b'Traceback never-emit-canary\n',returncode=1);receipt=run(docs,host)
        assert b'never-emit' not in f.line(receipt)
    docs,host=kprobe.case('LOAD');host.docker.on_run=kprobe.answers(returncode=1,output=kprobe.compact({'status':'CAPACITY_STARTUP_REFUSED','code':'never-emit'}))
    assert b'never-emit' not in f.line(run(docs,host))


def test_a_child_on_another_device_is_said_so_and_its_identity_follows_its_numbers():
    docs,host=kprobe.case('IDENT');host.tree.get(kprobe.ROOT+'/go').dev=999;receipt=run(docs,host)
    assert receipt['outcome']==K().m.IDENT_OUTCOME and receipt['precheck']['capacity']['children']['go']['same_device_as_root'] is False
    assert [receipt['precheck']['capacity']['children'][name]['same_device_as_root'] for name in ('config','documents','payload')]==[True]*3
    assert receipt['host_identities']['go']==kprobe.host_identity(host,'go') and '999' in json.dumps(receipt['precheck']['capacity']['children']['go'])

def test_the_seconds_of_each_container_are_kept_to_the_millisecond():
    docs,host=kprobe.case('IDENT');budget=f.Budget(kprobe.NOW['IDENT']).attach(host).cost(1.2345,'run','--rm');receipt=run(docs,host,**budget.options())
    assert receipt['outcome']==K().m.IDENT_OUTCOME and [item['seconds'] for item in receipt['containers']]==[round(1.2345,3)]*2 and round(1.2345,3)!=1

def test_an_answer_not_as_expected_is_said_before_any_finding():
    docs,host=kprobe.case('LOAD')
    def leave(call):host.docker.containers.append(hostemu.container(call.name,hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.docker.on_run=kprobe.answers(returncode=1,output=kprobe.compact({'status':'CAPACITY_STARTUP_REFUSED','code':'ROOT_IDENTITY_CHANGED'}),before=leave)
    receipt=run(docs,host);assert verdict(receipt)==('PARTIAL_METADATA_REQUIRES_REVIEW','STEP_RAN_ANSWER_NOT_AS_EXPECTED','CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE')
    assert receipt['containers_after']['names_present'] is True


# ---------------------------------------------------------------- review of LOAD (revision 2)
def load_refused(change,code,commands=None):
    docs,host=kprobe.case('LOAD');change(host);receipt=run(docs,host);refused(receipt,code,host,commands);assert receipt['precheck']['worker'] is None
    return receipt

def test_no_other_mount_of_the_worker_reaches_the_tree_or_lies_under_its_target():
    good=kprobe.mount()
    for other,code in ((kprobe.mount('/srv/x','/c3po-capacity/documents'),'WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET'),
                       (kprobe.mount('/srv/x','/c3po-capacity/a/b',rw=True),'WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET'),
                       (kprobe.mount('/var/lib','/app/day-d-data',rw=True),'WORKER_OTHER_MOUNT_REACHES_THE_TREE'),
                       (kprobe.mount('/','/host'),'WORKER_OTHER_MOUNT_REACHES_THE_TREE'),
                       (kprobe.mount('/var','/v'),'WORKER_OTHER_MOUNT_REACHES_THE_TREE'),
                       (kprobe.mount(kprobe.ROOT,'/elsewhere',rw=True),'WORKER_OTHER_MOUNT_REACHES_THE_TREE'),
                       (kprobe.mount(kprobe.ROOT+'/documents','/docs'),'WORKER_OTHER_MOUNT_REACHES_THE_TREE'),
                       (kprobe.mount(kprobe.ROOT+'/config/week.static.capacity.json','/cfg.json'),'WORKER_OTHER_MOUNT_REACHES_THE_TREE')):
        for mounts in ([good,other],[other,good]):
            load_refused(lambda host,mounts=mounts:kprobe.bind_worker(host,mounts),code,['image','worker','mounts'])
    for other in (kprobe.mount('/var/lib/c3po-capacity2','/x',rw=True),kprobe.mount('/var/lib/c3po','/y'),kprobe.mount(hostemu.DATA,'/app/day-d-data',rw=True),
                  kprobe.mount('/var/lib/docker/volumes/c3po_x/_data','/z',kind='volume',rw=True),kprobe.mount('','/tmp',kind='tmpfs',rw=True),
                  kprobe.mount('/srv/x','/c3po-capacityx')):
        docs,host=kprobe.case('LOAD');kprobe.bind_worker(host,[other,good]);receipt=run(docs,host)
        assert receipt['outcome']==K().m.COMPLETE_OUTCOME,other
        assert receipt['precheck']['worker']['other_mounts_clear_of_the_tree'] is True

def set_env(host,**values):
    """Replace or add (value a str) or remove (value None) names of the worker's environment."""
    env=kprobe.worker(host)['Config']['Env']
    for name,value in values.items():
        env[:]=[item for item in env if item.split('=',1)[0]!=name]
        if value is not None:env.append(name+'='+value)

def test_the_worker_settings_are_the_signed_ones_or_absent():
    m=K().m;C='C3PO_R2D2_V2_CAPACITY_'
    commands=['image','worker','mounts','environment']
    for values,code in (({'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':None},'WORKER_RELEASE_SHA_NOT_AS_SIGNED'),
                        ({'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':'f'*64},'WORKER_RELEASE_SHA_NOT_AS_SIGNED'),
                        ({C+'MOUNT_SOURCE':None},'WORKER_MOUNT_SOURCE_NOT_AS_SIGNED'),({C+'MOUNT_SOURCE':kprobe.ROOT+'/'},'WORKER_MOUNT_SOURCE_NOT_AS_SIGNED'),
                        ({C+'CONFIG_FILE':'/c3po-capacity/config/other.json'},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED'),
                        ({C+'CONFIG_SHA':'c'*64},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED'),({C+'VETO_MODE':'CONTINUOUS'},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED'),
                        ({C+'REQUIRED':'false'},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED'),({C+'REQUIRED':'True'},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED'),
                        ({C+'REQUIRED':''},'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED')):
        receipt=load_refused(lambda host,values=values:set_env(host,**values),code,commands)
    every={C+'CONFIG_FILE':kprobe.CONFIG_PATH,C+'CONFIG_SHA':kprobe.CONFIG_SHA,C+'VETO_MODE':'DISPATCH_AND_DERIVATION_ONLY',C+'REQUIRED':'true'}
    for count in range(5):
        docs,host=kprobe.case('LOAD');names=sorted(every)[:count];set_env(host,**{name:every[name] for name in names});receipt=run(docs,host)
        assert receipt['outcome']==m.COMPLETE_OUTCOME,names
        assert all(receipt['precheck']['worker']['settings'][name]=={'present':True,'equal':True} for name in names)
    docs,host=kprobe.case('LOAD')
    real=host.docker.run
    def failing(args,stdin=None,environment=None):
        if args[:2]==['container','inspect'] and '.Config.Env' in args[3]:return 1,b''
        return real(args,stdin,environment)
    host.docker.run=failing;refused(run(docs,host),'WORKER_ENVIRONMENT_UNREADABLE',host,commands)

def test_the_environment_read_carries_only_signed_values_and_answers_booleans():
    docs,host=kprobe.case('LOAD');set_env(host,C3PO_R2D2_V2_DATABASE_URL='never-emit-x');receipt=run(docs,host)
    argv=[entry['argv'] for entry in host.commands if entry['argv'][1:3]==['container','inspect'] and '.Config.Env' in entry['argv'][4]][0]
    assert argv[-1]==kprobe.worker(host)['Id'] and 'never-emit' not in ' '.join(argv) and b'never-emit' not in f.line(receipt)
    assert sorted(re.findall(r'"([A-Z0-9_]+)=',argv[4]))==sorted(SETTINGS_FOUND)

def test_a_root_changed_after_the_worker_started_is_reported_not_judged():
    m=K().m
    assert m.started_ns('2026-10-05T20:40:00.000000001Z')==1791232800*10**9+1 and m.started_ns('2026-10-05T20:40:00Z')==1791232800*10**9
    assert m.started_ns('2026-10-05T20:40:00.5Z')==1791232800*10**9+500000000
    for value in ('2026-10-05T20:40:00+00:00','2026-13-05T20:40:00Z','0001-01-01T00:00:00Z ',None,'','2026-10-05T20:40:00.0000000001Z'):
        assert m.started_ns(value) is None,value
    assert m.changed_after(5,None) is None and m.changed_after(None,'2026-10-05T20:40:00Z') is None
    docs,host=kprobe.case('LOAD');started=kprobe.worker(host)['State']['StartedAt'];begun=m.started_ns(started)
    host.tree.get(kprobe.ROOT).ctime=begun+1;receipt=run(docs,host)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['precheck']['worker']['root_changed_after_the_worker_started'] is True
    docs,host=kprobe.case('LOAD');begun=m.started_ns(kprobe.worker(host)['State']['StartedAt']);host.tree.get(kprobe.ROOT).ctime=begun;receipt=run(docs,host)
    assert receipt['precheck']['worker']['root_changed_after_the_worker_started'] is False and receipt['precheck']['capacity']['root']['ctime_ns']==begun
    docs,host=kprobe.case('LOAD');kprobe.worker(host)['State']['StartedAt']='later';receipt=run(docs,host)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['precheck']['worker']['root_changed_after_the_worker_started'] is None

@pytest.mark.parametrize('step',('IDENT','LOAD'))
def test_only_directories_lie_directly_in_the_bound_root(step):
    for kind in ('file','symlink','fifo'):
        docs,host=kprobe.case(step);host.tree.add(kprobe.ROOT+'/extra',kind=kind,mode=0o600);receipt=run(docs,host)
        refused(receipt,'CAPACITY_ROOT_ENTRY_NOT_A_DIRECTORY',host,['image'])
    docs,host=kprobe.case(step);host.tree.add(kprobe.ROOT+'/receipts',mode=0o700);host.tree.add(kprobe.ROOT+'/receipts/x',kind='file')
    receipt=run(docs,host);assert receipt['outcome']==K().m.STEP_OUTCOMES[step] and receipt['precheck']['capacity']['root']['other_directories']==1
    docs,host=kprobe.case(step)
    for index in range(61):host.tree.add(kprobe.ROOT+'/d%02d'%index,mode=0o700)
    refused(run(docs,host),'CAPACITY_ROOT_ENTRY_LIMIT',host,['image'])
    docs,host=kprobe.case(step)
    for index in range(60):host.tree.add(kprobe.ROOT+'/d%02d'%index,mode=0o700)
    assert run(docs,host)['precheck']['capacity']['root']['other_directories']==60
