"""K6b, every refusal from the signed bytes (validate_plan, run by the dispatcher before any claim): one case per code
and per way of reaching it; and the binding of every member of the plan into the effects the signers read."""
import copy
import json

import pytest

import family as f
import hostemu
import k6b

def refused(change,mode='MOUNT'):
    m,docs,host=k6b.fresh(mode);change(docs.plan);docs.chain()
    code=f.refusal(lambda:docs.authenticate())
    receipt=docs.run(f.Untouchable())                       # never reaches the host
    assert receipt['status']=='REFUSED' and receipt['code']==code
    return code

def setter(path,value):
    def change(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return change

CASES=[
    ('MODE_INVALID',setter(('mode',),'ENABLE_AND_MOUNT'),'MOUNT'),
    ('MODE_INVALID',setter(('mode',),None),'MOUNT'),
    ('EVIDENCE_BOOT_UNBOUND',setter(('evidence_boot_id_sha256',),'0'*64),'MOUNT'),
    ('EVIDENCE_BOOT_UNBOUND',setter(('evidence_boot_id_sha256',),None),'MOUNT'),
    ('PATH_INVALID',setter(('data_root',),'/mnt/day-d-data/'),'MOUNT'),
    ('PATH_INVALID',setter(('data_root',),'relative'),'MOUNT'),
    ('CAPACITY_REQUEST_INVALID',setter(('capacity','config_name'),'../escape.json'),'MOUNT'),
    ('CAPACITY_REQUEST_INVALID',setter(('capacity','config_name'),'with space.json'),'ENABLE'),
    ('CAPACITY_REQUEST_INVALID',setter(('capacity','config_sha256'),'0'*64),'ENABLE'),
    ('CAPACITY_REQUEST_INVALID',setter(('capacity','config_sha256'),'A'*64),'DISABLE_FAST'),
    ('CAPACITY_REQUEST_INVALID',setter(('capacity','extra'),1),'MOUNT'),
    ('OVERRIDE_REQUEST_INVALID',setter(('override','name'),'a/b'),'MOUNT'),
    ('OVERRIDE_REQUEST_INVALID',setter(('override','extra'),1),'MOUNT'),
    ('OVERRIDE_REQUEST_INVALID',setter(('override','environment'),dict(list(k6b.ACTIVATION.items())[:3])),'MOUNT'),
    ('OVERRIDE_REQUEST_INVALID',setter(('override','environment'),dict(k6b.ACTIVATION,EXTRA='x')),'MOUNT'),
    ('OVERRIDE_REQUEST_INVALID',setter(('override','environment'),None),'MOUNT'),
    ('WORKER_REQUEST_INVALID',setter(('worker','image_id'),'c3po/backend:production'),'MOUNT'),
    ('WORKER_REQUEST_INVALID',setter(('worker','extra'),1),'MOUNT'),
    ('COMPOSE_REQUEST_INVALID',setter(('compose','extra'),1),'MOUNT'),
    ('COMPOSE_NOT_THE_DEPLOY_LAYOUT',setter(('compose','env_file'),hostemu.DEPLOY+'/other.env'),'MOUNT'),
    ('COMPOSE_NOT_THE_DEPLOY_LAYOUT',setter(('compose','files'),[hostemu.DEPLOY+'/c3po/compose.override.yml']),'MOUNT'),
    ('COMPOSE_PROJECT',setter(('compose','project'),'C3PO'),'MOUNT'),
    ('LOCK_REQUEST_INVALID',setter(('lock','wait_seconds'),21),'MOUNT'),
    ('LOCK_REQUEST_INVALID',setter(('lock','wait_seconds'),True),'MOUNT'),
    ('LOCK_REQUEST_INVALID',setter(('lock','extra'),1),'MOUNT'),
    ('LOAD_EVIDENCE_INVALID',setter(('probe_load_receipt_sha256',),None),'ENABLE'),
    ('LOAD_EVIDENCE_INVALID',setter(('probe_load_receipt_sha256',),'0'*64),'ENABLE'),
    ('LOAD_EVIDENCE_INVALID',setter(('probe_load_receipt_sha256',),'9'*64),'MOUNT'),
    ('LOAD_EVIDENCE_INVALID',setter(('probe_load_receipt_sha256',),'9'*64),'DISABLE_FAST'),
    ('ENVIRONMENT_EXPECTATION',setter(('override','environment',k6b.KEYS[0]),'/app/day-d-data/a b'),'MOUNT'),
]

@pytest.mark.parametrize('code,change,mode',CASES)
def test_refused_from_the_bytes(code,change,mode):
    assert refused(change,mode)==code

def rows_of(host,path):return hostemu.rows(host,path)

def test_the_capacity_tree_must_be_root_owned_from_the_root_and_placed_away_from_both_trees():
    def writable(plan):plan['capacity']['root'][-1]['mode']=0o770
    assert refused(writable)=='CHAIN_ROW_UNSAFE'
    def foreign(plan):plan['capacity']['root'][-1]['uid']=1000
    assert refused(foreign)=='CHAIN_ROW_UNSAFE'
    m,docs,host=k6b.fresh('MOUNT');host.tree.add(hostemu.DATA+'/c3po-capacity',dev=hostemu.DATA_DEVICE,mode=0o700)
    under_data=rows_of(host,hostemu.DATA+'/c3po-capacity')
    assert refused(setter(('capacity','root'),under_data))=='CHAIN_ROW_UNSAFE'              # uid 1000 above it: not root-owned from '/'
    host.tree.add('/opt/chief-of-staff-digital-capacity',mode=0o700);host.tree.add(hostemu.DEPLOY+'/capacity',mode=0o700,uid=0,gid=0)
    # a root-owned directory inside the deploy tree is still refused, by its placement (the deploy tree is uid 1000)
    assert refused(setter(('capacity','root'),rows_of(host,hostemu.DEPLOY+'/capacity')))=='CHAIN_ROW_UNSAFE'
    assert refused(setter(('capacity','root'),[rows_of(host,'/')[0]]))=='CAPACITY_REQUEST_INVALID'

def test_the_override_lies_in_the_data_root_and_is_not_the_root():
    m,docs,host=k6b.fresh('MOUNT')
    assert refused(setter(('override','directory'),rows_of(host,hostemu.DATA)))=='OVERRIDE_OUTSIDE_DATA_ROOT'
    host.tree.add('/srv/live',mode=0o700)
    assert refused(setter(('override','directory'),rows_of(host,'/srv/live')))=='OVERRIDE_OUTSIDE_DATA_ROOT'

def test_the_deploy_tree_and_the_lock():
    m,docs,host=k6b.fresh('MOUNT')
    host.tree.add(hostemu.DEPLOY+'/runtime/other',uid=1000,gid=1000)
    assert refused(setter(('lock','directory'),rows_of(host,hostemu.DEPLOY+'/runtime/other')))=='LOCK_NOT_THE_DEPLOYMENT_LOCK'

def test_paths_overlap_and_tree_placement_are_reached():
    """Signed rows that are internally consistent and reach exactly these two codes."""
    m,docs,host=k6b.fresh('MOUNT')
    # a root-owned data root that holds the deploy tree (every chain consistent with the ownership rule)
    host.tree.add('/srv',mode=0o755);host.tree.add('/srv/data',mode=0o755);host.tree.add('/srv/data/live',mode=0o700)
    host.tree.add('/srv/data/deploy',uid=1000,gid=1000);host.tree.add('/srv/data/deploy/runtime',uid=1000,gid=1000)
    host.tree.add('/srv/data/deploy/runtime/security',uid=1000,gid=1000)
    def overlap(plan):
        plan['data_root']='/srv/data';plan['override']['directory']=rows_of(host,'/srv/data/live')
        plan['deploy_directory']=rows_of(host,'/srv/data/deploy');plan['lock']['directory']=rows_of(host,'/srv/data/deploy/runtime/security')
        plan['compose']=dict(plan['compose'],env_file='/srv/data/deploy/.env',files=['/srv/data/deploy/c3po/compose.yml'])
    assert refused(overlap)=='PATHS_OVERLAP'
    # a root-owned capacity tree that holds the data root
    host.tree.add('/srv',mode=0o755);host.tree.add('/srv/cap',mode=0o700);host.tree.add('/srv/cap/data',uid=1000,gid=1000);host.tree.add('/srv/cap/data/live',mode=0o700)
    def holds(plan):
        plan['capacity']['root']=rows_of(host,'/srv/cap');plan['data_root']='/srv/cap/data';plan['override']['directory']=rows_of(host,'/srv/cap/data/live')
    assert refused(holds)=='CAPACITY_TREE_PLACEMENT'

def test_every_member_of_the_plan_is_bound_into_the_effects():
    """Each member, changed alone in a way validate_plan accepts, changes effects_of(): the signers see it."""
    m,docs,host=k6b.fresh('ENABLE');base=json.dumps(m.effects_of(docs.plan),sort_keys=True)
    host.tree.add('/var/lib/c3po-capacity-2',mode=0o700)
    changes=[('mode','DISABLE_FULL'),('data_root',hostemu.DATA),('worker',{'image_id':'sha256:'+'ab'*32}),('probe_load_receipt_sha256','8'*64),
             ('capacity',dict(docs.plan['capacity'],config_name='other.json')),('capacity',dict(docs.plan['capacity'],config_sha256='6'*64)),
             ('capacity',dict(docs.plan['capacity'],root=rows_of(host,'/var/lib/c3po-capacity-2'))),
             ('override',dict(docs.plan['override'],name='other.json')),
             ('override',dict(docs.plan['override'],environment=dict(k6b.ACTIVATION,**{k6b.KEYS[1]:'4'*64}))),
             ('lock',dict(docs.plan['lock'],wait_seconds=7)),('evidence_boot_id_sha256','3'*64)]
    for key,value in changes:
        plan=copy.deepcopy(docs.plan);plan[key]=value
        if key=='mode':plan['probe_load_receipt_sha256']=None
        if key!='data_root':assert json.dumps(m.effects_of(plan),sort_keys=True)!=base,key
    rows=copy.deepcopy(docs.plan);rows['deploy_directory'][-1]['inode']+=1
    assert json.dumps(m.effects_of(rows),sort_keys=True)!=base
    rows=copy.deepcopy(docs.plan);rows['lock']['directory'][-1]['inode']+=1
    assert json.dumps(m.effects_of(rows),sort_keys=True)!=base
    rows=copy.deepcopy(docs.plan);rows['override']['directory'][-1]['inode']+=1
    assert json.dumps(m.effects_of(rows),sort_keys=True)!=base

def test_effects_say_the_edit_literally():
    m,docs,host=k6b.fresh('DISABLE_FULL');e=m.effects_of(docs.plan)
    assert e['environment_file']['trailing_capacity_block_before_one_of']==[k6b.BLOCK[:1],k6b.BLOCK[:4],k6b.BLOCK[:5]]
    assert e['environment_file']['trailing_capacity_block_after']==[] and e['worker_after']['environment_absent']==k6b.CAPACITY_NAMES
    assert e['worker_after']['capacity_mount']=={'type':'volume','name':'c3po_c3po_capacity_unprovisioned','target':'/c3po-capacity','read_only':True}
    assert e['recreate']['files']==[hostemu.COMPOSE_FILE,k6b.OVERRIDE_FILE] and e['override']['sha256']==f.sha(k6b.override_bytes())
    assert e['capacity_tree']['read'] is False and e['required']['worker_running_before'] is False
    m,docs,host=k6b.fresh('ENABLE');e=m.effects_of(docs.plan)
    assert e['environment_file']['trailing_capacity_block_before_one_of']==[k6b.BLOCK[:1]] and e['environment_file']['trailing_capacity_block_after']==k6b.BLOCK
    assert e['worker_after']['environment_present']==dict(line.split('=',1) for line in k6b.BLOCK)
    assert e['worker_after']['capacity_mount']=={'type':'bind','source':k6b.CAPACITY,'target':'/c3po-capacity','read_only':True}
    assert e['required']['probe_load_receipt_sha256']=='9'*63+'4' and e['capacity_tree']['read'] is True
    assert e['editor']['mounts']==[{'source':hostemu.ENV_FILE,'target':'/c3po-env/.env','read_only':False}] and e['editor']['image_id']==hostemu.BACKEND
    assert e['pre_existing_objects_modified']=='THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED' and e['activation'] is False

def test_the_order_of_the_block_is_the_fast_disable_s():
    """REQUIRED is the last line: the fast disable cuts exactly that line and keeps the mount and the three settings."""
    m,docs,host=k6b.fresh('DISABLE_FAST')
    assert m.CAPACITY_KEYS[-1]=='C3PO_R2D2_V2_CAPACITY_REQUIRED' and m.MODES=={'MOUNT':{'before':(0,),'after':1},'ENABLE':{'before':(1,),'after':5},
        'DISABLE_FAST':{'before':(5,),'after':4},'DISABLE_FULL':{'before':(1,4,5),'after':0}}
    spec=m.edit_spec(docs.plan);assert spec['before']==[k6b.BLOCK] and spec['after']==k6b.BLOCK[:4]

def literal_effects(m,docs,host,mode):
    """effects_of() computed here from the fixture's constants alone (the script bytes are the source's: they are pinned
    by their own hash, test_editor_native.py)."""
    count=k6b.AFTER[mode];befores=(1,4,5) if mode=='DISABLE_FULL' else (k6b.BEFORE[mode],)
    spec={'before':[k6b.BLOCK[:c] for c in befores],'after':k6b.BLOCK[:count],'owner':[1000,1000],'mode':384}
    stdin=(m.ENV_EDIT_SCRIPT+'raise SystemExit(main(json.loads(%s)))\n'%json.dumps(json.dumps(spec,sort_keys=True,separators=(',',':')))).encode()
    override=k6b.override_bytes();rows=lambda path:hostemu.rows(host,path)
    values=dict(line.split('=',1) for line in k6b.BLOCK)
    return {'operation':'GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01','mode':mode,'epoch':'R2D2-V2-SHADOW-2026-10-05','revision':hostemu.REVISION,
            'environment_file':{'path':hostemu.ENV_FILE,'owner':[1000,1000],'mode_octal':'0600','trailing_capacity_block_before_one_of':spec['before'],
                                'trailing_capacity_block_after':spec['after'],'rule':'no capacity line outside the trailing block; every other byte unchanged; same object'},
            'editor':{'row':'edit_env','argv_prefix':['run','--rm','-i','--pull','never','--init','--user','1000:1000','--network','none','--read-only',
                                                     '--cap-drop','ALL','--security-opt','no-new-privileges'],
                      'image_id':hostemu.BACKEND,'mounts':[{'source':hostemu.ENV_FILE,'target':'/c3po-env/.env','read_only':False}],
                      'command':['python','-I','-B','-'],'script_sha256':f.sha(m.ENV_EDIT_SCRIPT.encode()),'stdin_sha256':f.sha(stdin),'stdin_bytes':len(stdin),
                      'container_name':'hostops02-k6b-<first 16 hex of the GO hash>[-withdraw]'},
            'withdrawal':{'authorized':True,'row':'edit_env','container_name':'hostops02-k6b-<first 16 hex of the GO hash>-withdraw',
                          'stdin_sha256_by_block_found':{str(c):f.sha((m.ENV_EDIT_SCRIPT+'raise SystemExit(main(json.loads(%s)))\n'%json.dumps(json.dumps(
                              {'before':[k6b.BLOCK[:count]],'after':k6b.BLOCK[:c],'owner':[1000,1000],'mode':384},sort_keys=True,separators=(',',':')))).encode())
                                                           for c in befores},
                          'when':'only if authorized here; only BEFORE the recreate is started, after an edit the editor confirmed and the host read back, '
                                 'while the lock file is still the one held; never after the recreate was started, whatever it did',
                          'effect':'the inverse edit of E1, by the same row: the trailing block found before is put back; every other byte unchanged'},
            'process':{'dumpable':0,'when':'first, before the deploy directory or the environment file is opened; the editor before it opens the file',
                       'core_dump':'none, to a file or through a pipe'},
            'core_exception':{'rule_4_preserved':False,'core_sha256':m.CORE_SHA256,'exception':'IN_PLACE_EDIT_EXCEPTION of this core generation: row edit_env of '
                              'source capacity_switch edits <deploy>/.env in place (append to, or cut the end of, the trailing capacity block)'},
            'bind_source_chain':{'rows':[{'path':row['path'],'uid':row['uid'],'gid':row['gid'],'mode':row['mode']} for row in rows(hostemu.DEPLOY)]+
                                        [{'path':hostemu.ENV_FILE,'uid':1000,'gid':1000,'mode':384}],
                                 'all_root_controlled':False,
                                 'note':'decision 6 asks every bind source and its ancestors to be root-controlled; this one is not (open item)'},
            'override':{'path':k6b.OVERRIDE_FILE,'sha256':f.sha(override),'bytes':len(override),'directory':m.chain_effects(rows(k6b.LIVE)),
                        'environment':dict(k6b.ACTIVATION),'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'},
            'capacity_tree':{'host_path':k6b.CAPACITY,'root':m.chain_effects(rows(k6b.CAPACITY)),'container_target':'/c3po-capacity',
                             'config_file':'/c3po-capacity/config/'+k6b.CONFIG_NAME,'config_sha256':k6b.CONFIG_SHA,'read':mode in ('MOUNT','ENABLE'),
                             'expect':'READ_NEVER_WRITTEN'},
            'recreate':{'project':'c3po','env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE,k6b.OVERRIDE_FILE],'service':'r2d2-worker',
                        'container':'c3po-r2d2-worker-1','image_id':hostemu.BACKEND,'build_sha':hostemu.REVISION,'lock':k6b.LOCK,'lock_wait_seconds':20,
                        'lock_chain_sha256':f.sha(f.canonical(rows(hostemu.LOCK_DIRECTORY))),'deploy_directory':m.chain_effects(rows(hostemu.DEPLOY))},
            'worker_after':{'environment_present':{key:values[key] for key in k6b.CAPACITY_NAMES[:count]},'environment_absent':k6b.CAPACITY_NAMES[count:],
                            'activation_environment':dict(k6b.ACTIVATION),
                            'capacity_mount':({'type':'bind','source':k6b.CAPACITY,'target':'/c3po-capacity','read_only':True} if count else
                                              {'type':'volume','name':'c3po_c3po_capacity_unprovisioned','target':'/c3po-capacity','read_only':True}),
                            'data_mount':{'type':'bind','source':hostemu.DATA,'target':'/app/day-d-data'}},
            'required':{'reboot_pending_marker_absent':'/run/c3po-security/reboot.pending','deploy_version':hostemu.REVISION,
                        'probe_load_receipt_sha256':'9'*63+'4' if mode=='ENABLE' else None,'worker_running_before':mode in ('MOUNT','ENABLE')},
            'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED',
            'activation':False}

@pytest.mark.parametrize('mode',('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL'))
def test_effects_of_is_this_literal(mode):
    m,docs,host=k6b.fresh(mode)
    assert json.loads(f.canonical(m.effects_of(docs.plan)))==json.loads(f.canonical(literal_effects(m,docs,host,mode)))

def test_the_scope_says_what_the_source_is():
    m=k6b.load().m;s=m.SCOPE
    assert (s['operation'],s['dates'],s['writes_allowed'],s['activation_allowed'])==('GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01',
        ['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10'],True,False)
    assert s['capacity_keys_in_block_order']==k6b.CAPACITY_NAMES and s['veto_mode']=='DISPATCH_AND_DERIVATION_ONLY' and s['required_value']=='true'
    assert s['capacity_target']=='/c3po-capacity' and s['capacity_subdirectories']==['config','documents','go','payload'] and s['placeholder_volume']=='c3po_capacity_unprovisioned'
    assert sorted(s['worker_targets'])==['/app/day-d-data','/c3po-capacity','/run/c3po-maintenance'] and s['data_target']=='/app/day-d-data'
    assert s['editor']=={'owner':[1000,1000],'mode':384,'target':'/c3po-env/.env','command':['python','-I','-B','-'],'script_sha256':m.ENV_EDIT_SCRIPT_SHA256,
                         'statuses':['ENV_EDIT_DONE','ENV_EDIT_REFUSED','ENV_EDIT_FAILED']}
    assert s['evidence_operations_required']==['GO_WRITE_HOSTOPS02_ACTIVATE_01'] and s['mounts_format']=='{{json .Mounts}}'
    assert s['partial_outcomes']==['PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED','PARTIAL_ENV_EDIT_WITHDRAWN_RECREATE_NOT_STARTED',
                                   'PARTIAL_ENV_FILE_EDITED_RECREATE_FAILED_WORKER_UNCHANGED',
                                   'PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED','PARTIAL_UNCERTAIN_REQUIRES_READBACK','PARTIAL_REQUIRES_RECONCILIATION']
    assert s['failure_phases']==['BEFORE_THE_EDIT','BEFORE_THE_RECREATE','AFTER_THE_RECREATE_STARTED']
    assert m.CORE_SHA256=='4bb3b3babd292096893fceb335cb4fb8f85fd4c38117e30d779da8669d26c10e'
    assert s['process']['dumpable']==0 and 'EDITOR_DUMPABLE_NOT_DISABLED' in s['process']['editor']
    assert (m.MAX_GATE_SPAN_SECONDS,m.EVIDENCE_REQUIRED,m.COMPLETE_OUTCOME,m.REFUSED_OUTCOME)==(900,True,'CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED','REFUSED_NOTHING_CHANGED')
    assert s['limits']['environment_file_bytes']==1048576 and s['limits']['override_bytes']==4096 and s['limits']['config_bytes']==1048576 and s['limits']['mounts_listed']==32

# ---------------------------------------------------------------- what the mutation list asked for, one case each
@pytest.mark.parametrize('rows',[None,[],[None],[{'path':5}],'rows',5,{'path':'/x'}])
def test_malformed_chain_rows(rows):
    assert refused(setter(('capacity','root'),rows))=='CHAIN_ROW_INVALID'

@pytest.mark.parametrize('member,code',[('capacity','CAPACITY_REQUEST_INVALID'),('override','OVERRIDE_REQUEST_INVALID'),('worker','WORKER_REQUEST_INVALID'),
                                        ('compose','COMPOSE_REQUEST_INVALID'),('lock','LOCK_REQUEST_INVALID')])
def test_a_member_given_as_the_list_of_its_keys(member,code):
    def change(plan):plan[member]=sorted(plan[member])
    assert refused(change,'ENABLE')==code

def test_names_and_paths_of_the_tree():
    assert refused(setter(('capacity','config_name'),'sub/file.json'))=='CAPACITY_REQUEST_INVALID'          # a clean path, not a file name
    m,docs,host=k6b.fresh('MOUNT');host.tree.add('/var/lib/c3po=capacity',mode=0o700)
    assert refused(setter(('capacity','root'),rows_of(host,'/var/lib/c3po=capacity')))=='CAPACITY_REQUEST_INVALID'   # clean, not a mount path

def root_owned_layout(host,base):
    """A data root and a deploy tree under one root-owned directory, every chain consistent with the ownership rule."""
    host.tree.add(base,mode=0o755)
    return host

def test_paths_overlap_a_data_root_inside_a_root_owned_deploy_tree():
    m,docs,host=k6b.fresh('MOUNT')
    for path,uid in (('/srv',0),('/srv/deploy',0),('/srv/deploy/data',1000),('/srv/deploy/runtime',1000),('/srv/deploy/runtime/security',1000)):
        host.tree.add(path,uid=uid,gid=uid,mode=0o755)
    host.tree.add('/srv/deploy/data/live',mode=0o700)
    def change(plan):
        plan['data_root']='/srv/deploy/data';plan['override']['directory']=rows_of(host,'/srv/deploy/data/live')
        plan['deploy_directory']=rows_of(host,'/srv/deploy');plan['lock']['directory']=rows_of(host,'/srv/deploy/runtime/security')
        plan['compose']=dict(plan['compose'],env_file='/srv/deploy/.env',files=['/srv/deploy/c3po/compose.yml'])
    assert refused(change)=='PATHS_OVERLAP'

def test_the_tree_inside_a_root_owned_data_root_or_deploy_tree_or_holding_the_deploy_tree():
    m,docs,host=k6b.fresh('MOUNT')
    for path,uid,mode in (('/srv',0,0o755),('/srv/data',0,0o755),('/srv/data/cap',0,0o700),('/srv/data/live',0,0o700),
                          ('/srv/dep',0,0o755),('/srv/dep/cap',0,0o700),('/srv/dep/runtime',1000,0o755),('/srv/dep/runtime/security',1000,0o755),
                          ('/srv/t',0,0o700),('/srv/t/dep',0,0o755),('/srv/t/dep/runtime',1000,0o755),('/srv/t/dep/runtime/security',1000,0o755)):
        host.tree.add(path,uid=uid,gid=uid,mode=mode)
    def data(plan):
        plan['data_root']='/srv/data';plan['override']['directory']=rows_of(host,'/srv/data/live');plan['capacity']['root']=rows_of(host,'/srv/data/cap')
    assert refused(data)=='CAPACITY_TREE_PLACEMENT'
    def deploy(base,cap):
        def change(plan):
            plan['deploy_directory']=rows_of(host,base);plan['lock']['directory']=rows_of(host,base+'/runtime/security')
            plan['compose']=dict(plan['compose'],env_file=base+'/.env',files=[base+'/c3po/compose.yml']);plan['capacity']['root']=rows_of(host,cap)
        return change
    assert refused(deploy('/srv/dep','/srv/dep/cap'))=='CAPACITY_TREE_PLACEMENT'
    assert refused(deploy('/srv/t/dep','/srv/t'))=='CAPACITY_TREE_PLACEMENT'

def test_unsafe_rows_of_each_signed_chain():
    def override(plan):plan['override']['directory'][-1]['mode']=0o777
    assert refused(override)=='CHAIN_ROW_WORLD_WRITABLE'
    def lock(plan):plan['lock']['directory'][1]['mode']=0o775                  # /opt, above the deploy tree
    assert refused(lock)=='CHAIN_ROW_UNSAFE'
    def deploy(plan):plan['deploy_directory'][1]['mode']=0o775
    assert refused(deploy)=='CHAIN_ROW_UNSAFE'

def test_a_deploy_tree_whose_path_the_editor_cannot_bind():
    m,docs,host=k6b.fresh('MOUNT')
    for path in ('/srv','/srv/de=ploy','/srv/de=ploy/runtime','/srv/de=ploy/runtime/security'):host.tree.add(path,uid=0 if path=='/srv' else 1000,gid=0 if path=='/srv' else 1000)
    def change(plan):
        plan['deploy_directory']=rows_of(host,'/srv/de=ploy');plan['lock']['directory']=rows_of(host,'/srv/de=ploy/runtime/security')
        plan['compose']=dict(plan['compose'],env_file='/srv/de=ploy/.env',files=['/srv/de=ploy/c3po/compose.yml'])
    assert refused(change)=='MOUNT_INVALID'


def test_the_success_criterion_is_the_complete_outcome():
    for mode in ('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL'):
        m,docs,host=k6b.fresh(mode)
        assert m.success_of(docs.plan)=='CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED'==docs.go['success_criterion']


def test_the_withdrawal_is_signed_and_may_be_refused():
    m,docs,host=k6b.fresh('ENABLE');docs.plan['withdrawal_authorized']=False;e=m.effects_of(docs.plan)
    assert e['withdrawal']['authorized'] is False and e['withdrawal']['stdin_sha256_by_block_found']=={}
    for value in (None,'yes',1):
        assert refused(setter(('withdrawal_authorized',),value))=='WITHDRAWAL_REQUEST_INVALID'
