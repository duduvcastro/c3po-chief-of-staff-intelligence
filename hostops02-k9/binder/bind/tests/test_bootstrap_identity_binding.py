"""Offline synthetic receipts: first-night exception, identity/claim and K3 chain adversaries. No host proof."""
from datetime import datetime,timedelta,timezone
import copy,types,ast,stat,hashlib
from functools import lru_cache
from pathlib import Path
import pytest
import helpers as h
b=h.b
BOOT='b0'*32
WORKER='c1'*32
UTC=timezone.utc

def instant(value):return datetime.fromisoformat(value)
def item(**fields):return dict(status='COMPLETE',matches=True,findings=[],**fields)
def clock(start,end):return {'utc_start':'2026-10-06T'+start+'+00:00','utc_end':'2026-10-06T'+end+'+00:00'}
def chain(path,device=1):
    paths=['/']+['/'+('/'.join(path.strip('/').split('/')[:i])) for i in range(1,len(path.strip('/').split('/'))+1)]
    return [dict(path=value,device=device if i==len(paths)-1 else 1,inode=100+i,uid=0,gid=0,
                 mode=0o700 if i==len(paths)-1 or value==b.K9_ROOT else 0o755) for i,value in enumerate(paths)]

@lru_cache(maxsize=1)
def real_k9r248c_schema():
    """Evaluate only the exact producer expression with fake stat data; never instantiate/import the reader."""
    origin=Path(__file__).resolve().parents[2]/'test-inputs/k9r-real-248c2ae4'
    raw=(origin/'op.py').read_bytes();sums=(origin/'ORIGIN_SHA256SUMS').read_bytes()
    assert hashlib.sha256(sums).hexdigest()=='248c2ae45d096ec3dfa8a845ecff8d1032f8d02bb71ec6cdfc019d70c7710c66'
    assert hashlib.sha256(raw).hexdigest()=='09528cdb7bc2b15cb6f0a83be7fff9a9bedb610319b6949882f0de97d2f9cd5c'
    producer=(origin/'build/k9_phase_read.py').read_bytes()
    assert hashlib.sha256(producer).hexdigest()=='42521f6c17fe1a96ad07200b24c5786036b63ef4091753514f41e80ad3169d7f'
    parsed=ast.parse(raw);kinds=[n for n in ast.parse(producer).body if isinstance(n,ast.FunctionDef) and n.name=='kind']
    assert len(kinds)==1
    namespace={'stat':stat};exec(compile(ast.Module(body=kinds,type_ignores=[]),'K9R248C_PINNED_KIND','exec'),namespace)
    expected={'path','exists','type','device','inode','uid','gid','mode_octal','mtime_ns','ctime_ns','nlink','is_link'}
    components=[n for n in ast.walk(parsed) if isinstance(n,ast.Dict) and
                {x.value for x in n.keys if isinstance(x,ast.Constant)}==expected]
    assert len(components)==1
    return namespace['kind'],compile(ast.Expression(body=components[0]),'K9R248C_PINNED_COMPONENT','eval'),expected

def real_k9r248c_component(path,index):
    kind,expression,expected=real_k9r248c_schema();leaf=index in (1,4)
    found=types.SimpleNamespace(st_mode=(stat.S_IFREG|0o600) if leaf else (stat.S_IFDIR|0o700),
        st_dev=2,st_ino=200+index,st_uid=0,st_gid=0,st_mtime_ns=10,st_ctime_ns=20,st_nlink=1 if leaf else 2)
    row=eval(expression,{'stat':stat,'kind':kind,'found':found,'path':path,'link':False})
    assert set(row)==expected
    return row

def tree_receipt():
    items={key:item() for key in b.BOOTSTRAP_TREE_ITEMS}
    for key,name in b.BOOTSTRAP_TREE_DIRECTORIES:
        path=b.K9_PLACEMENT_PATHS[name]
        items['directory:'+key]=item(path=path,held=True,root_private=True,owner_uid=0,owner_gid=0,mode_octal='0700',
            observed_rows=chain(path),entries=0,rows_acceptable_to_the_k9_requests=True,components_not_root_controlled=[])
    secrets=items['directory:SECRETS']
    items['directory:EMITTER']=dict(status='COMPLETE',matches=False,findings=['PARENT_MISSING'],
        path=b.K9_PLACEMENT_PATHS['emitter'],held=False,observed_rows=copy.deepcopy(secrets['observed_rows']))
    for name in ('provider.env','risk-db.env'):
        items['secret:SECRETS/'+name]=dict(status='COMPLETE',matches=False,findings=['SECRET_FILE_ABSENT'],exists=False,name=name)
    items['secret:EMITTER/password']={'status':'UNAVAILABLE','code':'DIRECTORY_NOT_HELD','elapsed_ms':0}
    items['boot']=item(boot_id_sha256=BOOT)
    components=[]
    for i,path in enumerate(b.BOOTSTRAP_SOURCE_PATHS):
        components.append(real_k9r248c_component(path,i))
    items['september_sources']=item(data_volume_rows=chain(b.K9_DATA_VOLUME,device=2),components=components)
    items['directories_stable']=item(directories={key:True for key,_ in b.BOOTSTRAP_TREE_DIRECTORIES if key!='EMITTER'})
    return dict(operation=b.K9R_OPERATION,mode='TREE',status=b.RECEIPT_STATUS['KNOWN_PARTIAL'],outcome='PARTIAL_OBSERVED',
        boot_id_sha256=BOOT,findings=['PARENT_MISSING','SECRET_FILE_ABSENT'],items_not_complete=['secret:EMITTER/password'],
        items_omitted_by_the_plan=[],items=items,clock=clock('20:40:00','20:41:00'),effects={'mode':'TREE','reads':{
            'directories':{key:b.K9_PLACEMENT_PATHS[name] for key,name in b.BOOTSTRAP_TREE_DIRECTORIES},
            'secret_files_lstat_only':[b.K9_PLACEMENT_PATHS[key] for key in ('provider_env_file','risk_db_env_file','emitter_password')]}})

def fact(role,complete=True,**fields):
    return dict(role=role,complete=complete,not_complete_accepted_by_parameter=not complete,
        source='BOUND_SET',receipt_host_binding_is_the_one_of_this_set=True,
        receipt_payload_is_the_sealed_source_of_that_operation=True,exit_json_binds_these_bytes=True,
        bound_set={'stderr_empty':True,'exit_json_binds_config_request_go_and_output':True},**fields)

def add_receipt(ctx,role,operation,receipt,complete=True):
    ctx['entries'].append({'role':role,'operation':operation});ctx['receipts'][role]=receipt
    ctx['evidence_facts'].append(fact(role,complete))
    ctx['blobs'][role]={'source':'bound'}

def source_copy(ctx,target,role,source,**fields):
    ctx['copied'].append(dict(plan_pointer=target,evidence_role=role,receipt_pointer=source,**fields))

def context():
    tree=tree_receipt();start=instant('2026-10-06T20:43:00+00:00');end=start+timedelta(minutes=5)
    c={'operation':b.BOOTSTRAP_OPERATION,'mode':b.REHEARSAL,'params':{},'request':{'writes_allowed':True},'watchdog':80,
       'window':{'start':start,'end':end,'gate_start':start,'gate_end':end},'entries':[],'receipts':{},'evidence_facts':[],
       'copied':[],'blobs':{},'rt':{'source':types.SimpleNamespace(PLAN_KEYS=b.BOOTSTRAP_PLAN_KEYS,RECEIPT_SCHEMA=b.BOOTSTRAP_RECEIPT_SCHEMA)}}
    parents={name:{'path':b.K9_PLACEMENT_PATHS[name],'rows':copy.deepcopy(tree['items']['directory:'+key]['observed_rows']),
                   'open_root':None} for name,key in b.K9R_CHAINS}
    c['plan']={'mode':b.BOOTSTRAP_MODE,'epoch':b.K9_EPOCH,'slot':b.BOOTSTRAP_SLOT,'attempt_key':b.BOOTSTRAP_ATTEMPT_KEY,
        'evidence_boot_id_sha256':BOOT,'parent_rows':parents,
        'data_volume_chain':copy.deepcopy(tree['items']['september_sources']['data_volume_rows']),
        'source_rows':b.bootstrap_source_rows(tree['items']['september_sources']['components']),
        'constants':{'package_sha256':'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84','code_revision':'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858','release_sha256':'d1'*32,'policy_sha256':'e1'*32,
            'image_id':'sha256:'+'f1'*32,'runner_sha256':b.K9_RUNNER_SHA256,'disk_floor_bytes':b.K9_DISK_FLOOR_BYTES,
            'placement':dict(b.K9_PLACEMENT_PATHS,k9_open_root=None)},
        'policy_read':{'policy':{'directory':{'rows':chain('/fixture/policy')}},'release':{'directory':{'rows':chain('/fixture/release')}}}}
    add_receipt(c,'TREE_PRE',b.K9R_OPERATION,tree,False)
    add_receipt(c,'E0',b.K4E0_OPERATION,{'operation':b.K4E0_OPERATION,'outcome':b.K4E0_OUTCOME,
        'effects':{'evidence_boot_id_sha256':BOOT},'clock':clock('20:38:00','20:39:00')})
    add_receipt(c,'POST',b.EPOCH_READBACK_OPERATION,{'operation':b.EPOCH_READBACK_OPERATION,'mode':'POST','outcome':b.POST_OUTCOME,
        'effects':{'evidence_boot_id_sha256':BOOT},'clock':clock('20:38:00','20:39:00'),
        'items':{'policy':{'rows':chain('/fixture/policy')},'release':{'rows':chain('/fixture/release')}}})
    for name,key in b.K9R_CHAINS:source_copy(c,'/parent_rows/'+name+'/rows','TREE_PRE','/items/directory:'+key+'/observed_rows')
    source_copy(c,'/data_volume_chain','TREE_PRE','/items/september_sources/data_volume_rows')
    source_copy(c,'/source_rows','TREE_PRE','/items/september_sources/components',receipt_transformation='BOOTSTRAP_SOURCE_ROWS_V1')
    source_copy(c,'/evidence_boot_id_sha256','TREE_PRE','/boot_id_sha256')
    for key in ('policy','release'):source_copy(c,'/policy_read/'+key+'/directory/rows','POST','/items/'+key+'/rows')
    return c

def bootstrap_receipt():
    items={key:item() for key in b.BOOTSTRAP_COMPLETE_ITEMS}
    items['boot']=item(equal_to_the_evidence=True);items['boot_stable']=item(equal_to_first=True)
    items['worker']=item(container_id=WORKER,running=True,state='running',image_id_equal_signed=True)
    items['worker_stable']=copy.deepcopy(items['worker'])
    items['image']=item(id_equal_signed=True,revision_equal_signed=True)
    items['directory:SECRETS']=item(path=b.K9_PLACEMENT_PATHS['secrets'],held=True,pinned=True,root_private=True,entries=0,
        observed_rows=chain(b.K9_PLACEMENT_PATHS['secrets']))
    items['directory:EMITTER']=item(path=b.K9_PLACEMENT_PATHS['emitter'],exists=False,held=False,absence_confirmed=True,
        parent_item='directory:SECRETS',code='ABSENT_FROM_HELD_SECRETS',errno=2)
    items['secret:EMITTER/password']=item(path=b.K9_PLACEMENT_PATHS['emitter_password'],exists=False,
        parent_absent_confirmed=True,parent_item='directory:EMITTER',code='ABSENT_PARENT_CONFIRMED')
    for name,key in (('provider.env','provider_env_file'),('risk-db.env','risk_db_env_file')):
        items['secret:SECRETS/'+name]=item(path=b.K9_PLACEMENT_PATHS[key],name=name,exists=False,absence_confirmed=True,
            parent_item='directory:SECRETS',code='ABSENT_ENTRY_CONFIRMED',errno=2)
    items['directories_stable']=item(directories={key:True for key,_ in b.BOOTSTRAP_TREE_DIRECTORIES if key!='EMITTER'}|{'POLICY':True,'RELEASE':True})
    for key in b.BOOTSTRAP_POSTCLAIM_ITEMS:items[key+'_postclaim']=copy.deepcopy(items[key])
    items['boot_postclaim']=item(equal_to_first=True)
    name='bootstrap-'+b.BOOTSTRAP_ATTEMPT_KEY+'.claim'
    claim=dict(state='VERIFIED',key=b.BOOTSTRAP_ATTEMPT_KEY,name=name,path=b.K9_PLACEMENT_PATHS['claims']+'/'+name,code=None,errno=None,
        possible_creation=True,created_by_this_run=True,usage_consumed=True,file_fsync=True,directory_fsync=True,readback_verified=True,
        parent_stable=True,metadata=dict(type='file',uid=0,gid=0,mode_octal='0600',links=1,device=1,inode=500))
    r=dict(operation=b.BOOTSTRAP_OPERATION,schema=b.BOOTSTRAP_RECEIPT_SCHEMA,mode=b.BOOTSTRAP_MODE,
        status=b.RECEIPT_STATUS['KNOWN_COMPLETE'],outcome=b.BOOTSTRAP_OUTCOME,epoch=b.K9_EPOCH,slot=b.BOOTSTRAP_SLOT,
        attempt_key=b.BOOTSTRAP_ATTEMPT_KEY,boot_id_sha256=BOOT,request_sha256='11'*32,go_sha256='22'*32,payload_sha256='33'*32,
        metadata_sha256='44'*32,effects={'evidence_boot_id_sha256':BOOT},findings=[],items_not_complete=[],expectations_met=True,
        dependents_hold=False,secret_contents_opened=False,phase_reached='CLAIM',nothing_changed_by_this_run=False,
        items=items,claim=claim,clock=clock('20:43:00','20:43:15'))
    content={key:r[key] for key in ('epoch','slot','attempt_key','request_sha256','go_sha256','payload_sha256','boot_id_sha256')}
    content.update(schema='HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1',worker_container_id=WORKER);claim['content_sha256']=b.sha(b.canonical(content))
    return r

def k3_context():
    c=context();c['operation']=b.K3K9_OPERATION;tree=c['receipts']['TREE_PRE']
    c['plan']={'evidence_boot_id_sha256':BOOT,'worker_container_id':WORKER,
        'secrets_chain':copy.deepcopy(tree['items']['directory:SECRETS']['observed_rows']),
        'data_volume_chain':copy.deepcopy(tree['items']['september_sources']['data_volume_rows']),
        'source_rows':b.bootstrap_source_rows(tree['items']['september_sources']['components'])}
    start=instant('2026-10-06T20:48:00+00:00');end=start+timedelta(minutes=6)
    c['window']={'start':start,'end':end,'gate_start':start,'gate_end':end}
    c['copied']=[row for row in c['copied'] if row['plan_pointer'] in ('/source_rows','/data_volume_chain')]
    source_copy(c,'/secrets_chain','TREE_PRE','/items/directory:SECRETS/observed_rows')
    add_receipt(c,'BOOTSTRAP',b.BOOTSTRAP_OPERATION,bootstrap_receipt())
    source_copy(c,'/worker_container_id','BOOTSTRAP','/items/worker/container_id')
    source_copy(c,'/evidence_boot_id_sha256','BOOTSTRAP','/boot_id_sha256')
    return c

def env_context():
    c=k3_context();c['operation']='GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01'
    c['plan']={'worker_container_id':WORKER,'evidence_boot_id_sha256':BOOT}
    start=instant('2026-10-06T20:55:00+00:00');end=start+timedelta(minutes=6)
    c['window']={'start':start,'end':end,'gate_start':start,'gate_end':end}
    request={'operation':b.K3K9_OPERATION,'not_before':'2026-10-06T20:48:00+00:00','not_after':'2026-10-06T20:54:00+00:00',
        'plan':dict(c['plan']),'evidence':[{'role':'BOOTSTRAP','operation':b.BOOTSTRAP_OPERATION,'receipt_sha256':'44'*32}]}
    raw=b.canonical(request)
    row=dict(state='PLACED_VERIFIED',code=None,**{key:True for key in ('created','fsync_file','fsync_directory','regular','uid_0','gid_0',
        'mode_0600','single_link','on_the_device_of_the_directory','readback_same_inode','readback_metadata_as_created')})
    receipt={'operation':b.K3K9_OPERATION,'status':b.RECEIPT_STATUS['KNOWN_COMPLETE'],'outcome':'K9_SECRETS_PLACED_METADATA_VERIFIED',
        'readback':'COMPLETE','request_sha256':b.sha(raw),'effects':{'evidence_boot_id_sha256':BOOT,'values':{'provider_env':{'container_id':WORKER}}},
        'worker':dict(one_container_with_the_name=True,id_equal_signed=True,running=True,read_twice_equal=True),
        'process':{'dumpable_disabled':True},'secrets_directory':{'pinned':True,'empty':True},
        'directory_readbacks':{'secrets_directory':None,'emitter_directory':None},
        'files':{key:copy.deepcopy(row) for key in ('provider_env','risk_db_env','emitter_password')},'clock':clock('20:48:05','20:48:15')}
    add_receipt(c,'K3',b.K3K9_OPERATION,receipt)
    c['evidence_facts'][-1].update(source='BOUND_SET',bound_set={'stderr_empty':True,'exit_json_binds_config_request_go_and_output':True})
    c['blobs']['K3']={'source':'bound','request':raw,'sheet':{'operation':b.K3K9_OPERATION,'mode':b.REHEARSAL,
        'hostops02':{'rules':{'k9_prerequisite':{'bootstrap_role':'BOOTSTRAP','identity_source':'BOOTSTRAP_IDENTITY_OBSERVED'}}},
        'plan_values_copied_from_receipts':[row for row in c['copied'] if row['plan_pointer'] in ('/worker_container_id','/evidence_boot_id_sha256')]}}
    c['copied']=[]
    source_copy(c,'/worker_container_id','K3','/effects/values/provider_env/container_id')
    source_copy(c,'/evidence_boot_id_sha256','K3','/effects/evidence_boot_id_sha256')
    return c

def test_first_prepare_accepts_only_completed_components_without_future_bootstrap():
    c=context();before=copy.deepcopy(c);result=b.bootstrap_program_rules(c)['bootstrap_identity']
    assert result['tree_role']=='TREE_PRE' and result['tree_complete'] is False
    assert not b.complete_role(c,'TREE_PRE') and not b.cited(c,b.BOOTSTRAP_OPERATION)
    assert result['claim_limits']=='BOOTSTRAP_EXECUTION_ONLY_NOT_RECEIPT_CITATION'
    assert c==before

def test_first_k3_and_secret_env_follow_one_observation_without_mutating_receipts():
    c=k3_context();before=copy.deepcopy(c);result=b.k3k9_rules(c)['k9_prerequisite']
    assert result['identity_source']=='BOOTSTRAP_IDENTITY_OBSERVED' and result['tree_complete'] is False and c==before
    c=env_context();before=copy.deepcopy(c);result=b.reader_install_rules(c)
    assert result['identity_observed_role']=='BOOTSTRAP' and result['k3_role']=='K3'
    assert result['k3_effects_are_independent_observation'] is False and c==before

@pytest.mark.parametrize('damage,code',[
    ('daily','BOOTSTRAP_TREE_NOT_ALLOWED_FOR_OPERATION'),('role','BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ'),
    ('complete','BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ'),('extra_item','BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ'),
    ('gap','BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ'),('wrong_path','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),
    ('password_permission','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),('password_generic','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),
    ('emitter_link','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),('secrets_not_empty','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),
    ('provider_io','BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT'),('unavailable_other','BOOTSTRAP_TREE_PRE_OTHER_ITEMS_NOT_COMPLETE'),
    ('changed_parent','BOOTSTRAP_TREE_PRE_OTHER_ITEMS_NOT_COMPLETE'),('boot','EVIDENCE_NOT_OF_THE_SAME_BOOT'),
    ('clock','BOOTSTRAP_PREDECESSOR_CLOCK_INVALID'),('late','BOOTSTRAP_PREDECESSOR_NOT_FINISHED')])
def test_partial_tree_exception_is_item_path_and_state_specific(damage,code):
    c=context();r=c['receipts']['TREE_PRE'];items=r['items']
    if damage=='daily':c['operation']=b.K9R_OPERATION
    if damage=='role':c['entries'][0]['role']='TREE';c['receipts']['TREE']=c['receipts'].pop('TREE_PRE')
    if damage=='complete':c['evidence_facts'][0]['complete']=True
    if damage=='extra_item':items['made_up']=item()
    if damage=='gap':r['items_not_complete'].append('runner_file')
    if damage=='wrong_path':r['effects']['reads']['directories']['EMITTER']='/elsewhere'
    if damage=='password_permission':items['secret:EMITTER/password']['code']='OS_ERROR'
    if damage=='password_generic':items['secret:EMITTER/password']['errno']=13
    if damage=='emitter_link':items['directory:EMITTER']['findings']=['PARENT_SYMLINK_COMPONENT']
    if damage=='secrets_not_empty':items['directory:SECRETS']['entries']=1
    if damage=='provider_io':items['secret:SECRETS/provider.env']['findings']=['OS_ERROR']
    if damage=='unavailable_other':items['runner_file']['status']='UNAVAILABLE'
    if damage=='changed_parent':items['directories_stable']['directories']['TOOLS']=False
    if damage=='boot':r['boot_id_sha256']='aa'*32
    if damage=='clock':r['clock']['utc_start']='2026-10-06T20:40:00'
    if damage=='late':r['clock']['utc_end']='2026-10-06T21:00:00+00:00'
    with h.refused(code):b.bootstrap_tree_pre(c)

@pytest.mark.parametrize('damage,code',[
    ('typed','BOOTSTRAP_HOST_IDENTITY_NOT_FROM_COMPLETE_COMPONENT'),('whole_partial','BOOTSTRAP_HOST_IDENTITY_NOT_FROM_COMPLETE_COMPONENT'),
    ('rows','BOOTSTRAP_TREE_ROWS_NOT_EXACT_COPIES'),('source_link','BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'),
    ('source_mode','BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'),('source_links','BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'),
    ('program','BOOTSTRAP_PROGRAM_CONTRACT_MISMATCH'),('future','BOOTSTRAP_PREPARE_CANNOT_CITE_BOOTSTRAP'),
    ('window','BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT'),('post_partial','BOOTSTRAP_PREDECESSORS_NOT_COMPLETE'),
    ('post_late','BOOTSTRAP_PREDECESSOR_NOT_FINISHED'),('linux','LINUX_JOB_RECORD_REQUIRED')])
def test_prepare_refuses_typed_partial_borrowing_and_circular_future_dependencies(damage,code):
    c=context()
    if damage=='typed':c['copied']=[row for row in c['copied'] if row['plan_pointer']!='/policy_read/policy/directory/rows']
    if damage=='whole_partial':
        c['copied']=[row for row in c['copied'] if row['plan_pointer']!='/parent_rows/days/rows']
        source_copy(c,'/parent_rows/days/rows','TREE_PRE','/items')
    if damage=='rows':c['plan']['parent_rows']['days']['path']='/wrong'
    if damage.startswith('source_'):
        row=c['receipts']['TREE_PRE']['items']['september_sources']['components'][1]
        if damage=='source_link':row['is_link']=True
        if damage=='source_mode':row['mode_octal']='600'
        if damage=='source_links':row['nlink']=2
    if damage=='program':c['rt']['source'].PLAN_KEYS=frozenset()
    if damage=='future':add_receipt(c,'future',b.BOOTSTRAP_OPERATION,bootstrap_receipt())
    if damage=='window':c['window']['start']-=timedelta(days=1)
    if damage=='post_partial':c['evidence_facts'][2]['complete']=False
    if damage=='post_late':c['receipts']['POST']['clock']['utc_end']='2026-10-06T20:40:30+00:00'
    if damage=='linux':c['mode']=b.REAL
    action=b.bootstrap_metadata_provenance if damage in ('typed','whole_partial') else b.bootstrap_program_rules
    with h.refused(code):action(c,'TREE_PRE') if action is b.bootstrap_metadata_provenance else action(c)

@pytest.mark.parametrize('damage,code',[
    ('missing','BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ'),('partial','BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ'),
    ('reduced','BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ'),('boot','BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'),
    ('worker','BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'),('worker_changed','BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'),
    ('password','BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED'),('provider_errno','BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED'),
    ('claim_uncertain','BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE'),('claim_fsync','BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE'),
    ('claim_key','BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE'),('claim_links','BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE'),
    ('claim_digest','BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE'),('mixed_copies','BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES'),
    ('late','BOOTSTRAP_PREDECESSOR_NOT_FINISHED'),('night','BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT'),
    ('corroboration','BOOTSTRAP_TREE_PRE_NOT_CORROBORATED')])
def test_k3_requires_complete_observed_identity_positive_absence_and_durable_claim(damage,code):
    c=k3_context();r=c['receipts']['BOOTSTRAP']
    if damage=='missing':c['entries']=[row for row in c['entries'] if row['operation']!=b.BOOTSTRAP_OPERATION]
    if damage=='partial':c['evidence_facts'][-1]['complete']=False
    if damage=='reduced':r['items'].pop('runner_file')
    if damage=='boot':r['boot_id_sha256']='aa'*32
    if damage=='worker':r['items']['worker']['running']=False
    if damage=='worker_changed':r['items']['worker_stable']['container_id']='aa'*32
    if damage=='password':r['items']['secret:EMITTER/password']['code']='DIRECTORY_NOT_HELD'
    if damage=='provider_errno':r['items']['secret:SECRETS/provider.env']['errno']=13
    if damage=='claim_uncertain':r['claim']['state']='CREATE_UNCERTAIN'
    if damage=='claim_fsync':r['claim']['directory_fsync']=False
    if damage=='claim_key':r['claim']['key']='aa'*32
    if damage=='claim_links':r['claim']['metadata']['links']=2
    if damage=='claim_digest':r['claim']['content_sha256']='aa'*32
    if damage=='mixed_copies':c['copied'][-1]['evidence_role']='TREE_PRE'
    if damage=='late':c['window']['start']=instant('2026-10-06T20:43:05+00:00')
    if damage=='night':c['window']['start']+=timedelta(days=1);c['window']['end']+=timedelta(days=1)
    if damage=='corroboration':r['items']['directory:SECRETS']['observed_rows'][-1]['inode']+=1
    action=b.bootstrap_complete_identity if damage=='late' else b.bootstrap_k3k9_rules
    with h.refused(code):action(c)

@pytest.mark.parametrize('damage,code',[
    ('k3_missing','BOOTSTRAP_K3_CHAIN_NOT_COMPLETE'),('k3_partial','BOOTSTRAP_K3_CHAIN_NOT_COMPLETE'),
    ('k3_readback','BOOTSTRAP_K3_CHAIN_NOT_COMPLETE'),('k3_worker','BOOTSTRAP_K3_CHAIN_NOT_COMPLETE'),
    ('k3_file','BOOTSTRAP_K3_CHAIN_NOT_COMPLETE'),('identity','BOOTSTRAP_K3_CHAIN_NOT_SAME_IDENTITY'),
    ('loose','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),('stderr','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),
    ('request_changed','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),('legacy_sheet','BOOTSTRAP_K3_CHAIN_NOT_BOUND'),
    ('wrong_bootstrap','BOOTSTRAP_K3_CHAIN_NOT_LINKED'),('sheet_copy','BOOTSTRAP_K3_CHAIN_NOT_LINKED'),
    ('reordered','BOOTSTRAP_K3_CHAIN_NOT_LINKED'),('late','BOOTSTRAP_PREDECESSOR_NOT_FINISHED'),
    ('direct_bootstrap_copy','BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES')])
def test_secret_env_traces_bound_k3_to_one_bootstrap_instead_of_assuming_effects_are_observed(damage,code):
    c=env_context();r=c['receipts']['K3'];blob=c['blobs']['K3']
    if damage=='k3_missing':c['entries']=[row for row in c['entries'] if row['operation']!=b.K3K9_OPERATION]
    if damage=='k3_partial':c['evidence_facts'][-1]['complete']=False
    if damage=='k3_readback':r['readback']=None
    if damage=='k3_worker':r['worker']['id_equal_signed']=False
    if damage=='k3_file':r['files']['provider_env']['state']='LEFT_UNVERIFIED'
    if damage=='identity':r['effects']['values']['provider_env']['container_id']='aa'*32
    if damage=='loose':blob['source']='receipt_file'
    if damage=='stderr':c['evidence_facts'][-1]['bound_set']['stderr_empty']=False
    if damage=='request_changed':blob['request']+=b' '
    if damage=='legacy_sheet':blob['sheet']['hostops02']['rules']['k9_prerequisite']['identity_source']='POLICY'
    if damage=='wrong_bootstrap':c['receipts']['BOOTSTRAP']['metadata_sha256']='aa'*32
    if damage=='sheet_copy':blob['sheet']['plan_values_copied_from_receipts'][0]['receipt_pointer']='/effects/signed_value'
    if damage=='reordered':r['clock']=clock('20:43:01','20:43:02')
    if damage=='late':c['window']['start']=instant('2026-10-06T20:48:10+00:00')
    if damage=='direct_bootstrap_copy':c['copied'][0].update(evidence_role='BOOTSTRAP',receipt_pointer='/items/worker/container_id')
    with h.refused(code):b.bootstrap_k3env_identity(c)

def test_explicit_source_rows_marker_projects_only_the_fixed_schema_and_has_no_legacy_permission():
    c=context();source=types.SimpleNamespace(OPERATION=b.BOOTSTRAP_OPERATION)
    ctx={'inputs':{},'used':[],'copied':[],'receipts':c['receipts'],'source':source,
         'operations':{entry['role']:entry['operation'] for entry in c['entries']}}
    marker={'$bootstrap_source_rows':{'evidence':'TREE_PRE','receipt_pointer':'/items/september_sources/components'}}
    result=b.resolve_hostops02(marker,ctx,'/source_rows')
    assert result==c['plan']['source_rows'] and all(set(row)=={'path','device','inode','uid','gid','mode','mtime_ns','ctime_ns'} for row in result)
    assert ctx['copied'][0]['receipt_transformation']=='BOOTSTRAP_SOURCE_ROWS_V1'
    source.OPERATION=b.K9R_OPERATION
    with h.refused('BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'):b.resolve_hostops02(marker,ctx,'/source_rows')
    source.OPERATION=b.K3K9_OPERATION
    with h.refused('BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'):b.resolve_hostops02(marker,ctx,'/source_rows')
    ctx['receipts']['BOOTSTRAP']=bootstrap_receipt()
    assert b.resolve_hostops02(marker,ctx,'/source_rows')==result

def test_daily_complete_receipt_provenance_and_policy_identity_keep_their_old_requirements():
    from test_policy_identity_binding import context as policy_context
    c=policy_context();assert b.policy_worker_identity(c)['evidence_role']=='R'
    c=context()
    with h.refused('SEALED_HOST_IDENTITY_NOT_FROM_PROVED_RECEIPT'):b.sealed_metadata_provenance(c)
    # Calling the original common rule still refuses the partial predecessor.
    c['operation']='GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
    c['rt']['source']=types.SimpleNamespace(EVIDENCE_OPERATIONS=(b.K9R_OPERATION,))
    with h.refused('SEALED_PROGRAM_EVIDENCE_NOT_COMPLETE'):b.sealed_program_rules(c)


@pytest.mark.parametrize('role',['TREE_PRE','E0','POST','BOOTSTRAP'])
@pytest.mark.parametrize('damage',['loose','stderr','source','exit'])
def test_bootstrap_paths_require_the_verified_bound_exit_go_stderr_and_source(role,damage):
    c=k3_context() if role=='BOOTSTRAP' else context()
    row=next(row for row in c['evidence_facts'] if row['role']==role)
    if damage=='loose':row['source']='RECEIPT_FILE'
    if damage=='stderr':row['bound_set']['stderr_empty']=False
    if damage=='source':row['receipt_payload_is_the_sealed_source_of_that_operation']=False
    if damage=='exit':row['bound_set']['exit_json_binds_config_request_go_and_output']=False
    action=b.bootstrap_complete_identity if role=='BOOTSTRAP' else b.bootstrap_program_rules
    with h.refused('BOOTSTRAP_EVIDENCE_NOT_BOUND'):action(c)

@pytest.mark.parametrize('damage',['missing','worker','boot','emitter','password','provider','stable'])
def test_postclaim_observations_are_required_and_must_confirm_identity_absence_and_stability(damage):
    c=k3_context();r=c['receipts']['BOOTSTRAP'];items=r['items']
    code='BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED'
    if damage=='missing':items.pop('boot_postclaim');code='BOOTSTRAP_IDENTITY_NOT_ONE_COMPLETE_READ'
    if damage=='worker':items['worker_postclaim']['container_id']='aa'*32;code='BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'
    if damage=='boot':items['boot_postclaim']['equal_to_first']=False;code='BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT'
    if damage=='emitter':items['directory:EMITTER_postclaim']['absence_confirmed']=False
    if damage=='password':items['secret:EMITTER/password_postclaim']['parent_absent_confirmed']=False
    if damage=='provider':items['secret:SECRETS/provider.env_postclaim']['errno']=13
    if damage=='stable':items['directories_stable_postclaim']['directories']['CLAIMS']=False
    with h.refused(code):b.bootstrap_complete_identity(c)


@pytest.mark.parametrize('kind',['prepare','k3','env'])
def test_bootstrap_path_does_not_accept_an_extra_cited_receipt_of_a_different_boot(kind):
    c={'prepare':context,'k3':k3_context,'env':env_context}[kind]()
    add_receipt(c,'OTHER','GO_READONLY_OTHER_01',{'operation':'GO_READONLY_OTHER_01','boot_id_sha256':'aa'*32})
    action={'prepare':b.bootstrap_program_rules,'k3':b.bootstrap_k3k9_rules,'env':b.bootstrap_k3env_identity}[kind]
    with h.refused('EVIDENCE_NOT_OF_THE_SAME_BOOT'):action(c)


@pytest.mark.parametrize('directory_index',[0,2,3])
def test_real_k9r248c_schema_projects_dir_and_refuses_directory(directory_index):
    c=context();components=c['receipts']['TREE_PRE']['items']['september_sources']['components']
    assert [r['type'] for r in components]==['dir','file','dir','dir','file']
    assert b.bootstrap_source_rows(components)==c['plan']['source_rows']
    assert b.bootstrap_program_rules(c)['bootstrap_identity']['tree_complete'] is False
    components[directory_index]['type']='directory'
    with h.refused('BOOTSTRAP_SOURCE_ROWS_TRANSFORM_INVALID'):b.bootstrap_program_rules(c)
