"""K12w behaviour on the emulated host: the plan's refusals (before any claim), each mode's prechecks (nothing changed),
each effect and its readback, and what never leaves the host. Synthetic only (tests/k12emu.py)."""
import base64
import copy
import json
from datetime import timedelta

import pytest

import family as f
import hostemu
import k12emu as e
import k12w

K=k12w.K()
M=K.m

def docs_for(mode='LAUNCH',host=None,now=None,**options):
    if host is None:return k12w.case(mode,e.at(now) if now else None,**options)
    return f.Docs(K,k12w.fields(host,mode,**options),now=e.at(now or k12w.MOMENTS[mode])),host

def refusal(docs):return f.refusal(docs.authenticate)

def with_request(docs,body=None,raw=None):
    docs.plan['capacity_request']=e.raw_member(raw) if raw is not None else e.member(body);docs.chain();return docs

def run(docs,host,**options):
    before=(host.tree.snapshot(),e.engine(host));receipt=docs.run(host,**options)
    assert f.sealed(receipt) and hostemu.SECRET not in json.dumps(receipt) and e.MANIFEST_SHA not in json.dumps(receipt)
    assert 'SYNTHA' not in json.dumps(receipt) and 'never-emit' not in json.dumps(receipt)
    if receipt['status']=='REFUSED':assert (host.tree.snapshot(),e.engine(host))==before,'a refusal changed the host'
    return receipt

def refused(docs,host,code,**options):
    receipt=run(docs,host,**options);assert (receipt['status'],receipt['code'])==('REFUSED',code),(receipt['code'],receipt.get('detail'))
    return receipt

def partial(docs,host,code):
    receipt=run(docs,host);assert (receipt['status'],receipt['outcome'],receipt['code'])==(M.PARTIAL_STATUS,M.PARTIAL_OUTCOME,code),(receipt['code'],receipt.get('detail'))
    return receipt

def complete(docs,host):
    receipt=run(docs,host);assert (receipt['status'],receipt['outcome'],receipt['code'])==(M.COMPLETE_STATUS,M.COMPLETE_OUTCOME,None),(receipt['code'],receipt.get('detail'))
    return receipt


# ---------------------------------------------------------------- the plan: refused before any claim
@pytest.mark.parametrize('change,code',[
    (dict(mode='LAUNCHED'),'MODE_INVALID'),(dict(mode=None),'MODE_INVALID'),
    (dict(launch_request_sha256='5e'*32),'MODE_MEMBERS_INVALID'),(dict(removals=[]),'MODE_MEMBERS_INVALID'),
    (dict(evidence_boot_id_sha256='0'*64),'EVIDENCE_BOOT_UNBOUND'),(dict(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),
    (dict(capacity_request=None),'CAPACITY_REQUEST_INVALID'),(dict(capacity_request={'b64':'@@','sha256':'1'*64}),'CAPACITY_REQUEST_INVALID'),
    (dict(capacity_request={'b64':'e30=','sha256':'1'*64,'x':1}),'CAPACITY_REQUEST_INVALID'),
    (dict(capacity_request={'b64':'e30=','sha256':'1'*64}),'CAPACITY_REQUEST_NOT_THE_SIGNED_BYTES'),
    (dict(parent_rows={}),'PARENT_ROWS_INVALID'),(dict(parent_rows=None),'PARENT_ROWS_INVALID')])
def test_plan_members_are_refused_before_any_claim(change,code):
    docs,_=docs_for();docs.plan.update(change);docs.chain();assert refusal(docs)==code

def test_mode_run_is_not_a_mode():
    docs,_=docs_for();docs.plan['mode']='RUN';docs.chain();assert refusal(docs)=='MODE_INVALID'

def test_the_evidence_must_name_the_k12_tree_read():
    docs,_=docs_for();docs.request['evidence']=[{'role':'PRIOR','operation':'GO_READONLY_SYNTHETIC_PRIOR_01','receipt_sha256':'a'*64}];docs.chain()
    assert refusal(docs)=='EVIDENCE_OPERATION_MISSING'

def test_plan_members_of_each_mode():
    for mode,change in (('PERSIST',dict(launch_request_sha256=None)),('STOP',dict(launch_request_sha256='x')),('PERSIST',dict(removals=[])),
                        ('REMOVE',dict(capacity_request=e.member(e.capacity_request()))),('REMOVE',dict(launch_request_sha256='5e'*32))):
        docs,_=docs_for(mode);docs.plan.update(change);docs.chain();assert refusal(docs)=='MODE_MEMBERS_INVALID',(mode,change)

def test_request_bytes_must_be_canonical_and_small():
    docs,_=docs_for();body=e.capacity_request()
    assert refusal(with_request(docs,raw=json.dumps(body,indent=1).encode()))=='CAPACITY_REQUEST_INVALID'
    assert refusal(with_request(docs,raw=f.canonical(body)+b'\n'))=='CAPACITY_REQUEST_INVALID'
    assert refusal(with_request(docs,raw=b' '*16385))=='CAPACITY_REQUEST_NOT_THE_SIGNED_BYTES'
    big=dict(body,network='x'*60);big['documentary']=dict(body['documentary']);raw=f.canonical(body)
    assert len(raw)<16384;assert refusal(with_request(docs,raw=f.canonical(dict(body,pad='p'*16000))))=='CAPACITY_REQUEST_NOT_THE_SIGNED_BYTES'

def mutated(**changes):
    body=e.capacity_request();body.update(changes);return body
MOUNTS=e.mounts()
def mounts_with(index,**change):
    out=copy.deepcopy(MOUNTS);out[index].update(change);return out

@pytest.mark.parametrize('body,code',[
    (dict(extra=1),'CAPACITY_REQUEST_KEYS'),
    (dict(schema='R2D2_CAPACITY_DAY_ONCE_REQUEST_V2'),'CAPACITY_REQUEST_IDENTITY'),(dict(status='UNBOUND'),'CAPACITY_REQUEST_IDENTITY'),
    (dict(operation='GO_CAPACITY_DAY_02'),'CAPACITY_REQUEST_IDENTITY'),(dict(epoch='R2D2-V2-SHADOW-2026-09-28'),'CAPACITY_REQUEST_IDENTITY'),
    (dict(executor_uid=1000),'CAPACITY_REQUEST_IDENTITY'),(dict(executor_uid=False),'CAPACITY_REQUEST_IDENTITY'),
    (dict(day='2026-10-05'),'CAPACITY_REQUEST_DAY'),(dict(day='2026-10-10'),'CAPACITY_REQUEST_DAY'),(dict(day=None),'CAPACITY_REQUEST_DAY'),
    (dict(window='Primary'),'CAPACITY_REQUEST_WINDOW'),(dict(window_index=3),'CAPACITY_REQUEST_WINDOW'),(dict(window_index=-1),'CAPACITY_REQUEST_WINDOW'),
    (dict(window_count=0),'CAPACITY_REQUEST_WINDOW'),(dict(window_count=4),'CAPACITY_REQUEST_WINDOW'),(dict(window_index=True),'CAPACITY_REQUEST_WINDOW'),
    (dict(window_count=1,window_index=1),'CAPACITY_REQUEST_WINDOW'),(dict(window_index=1),'CAPACITY_REQUEST_CLOCK'),
    (dict(phases=['admission']),'CAPACITY_REQUEST_MODE'),(dict(mode='PUBLISH_ONLY'),'CAPACITY_REQUEST_MODE'),(dict(view_mode='LATE'),'CAPACITY_REQUEST_MODE'),
    (dict(image_id='c3po/backend:production'),'CAPACITY_REQUEST_PINS'),(dict(build_sha='dd4ec4bb'),'CAPACITY_REQUEST_PINS'),
    (dict(release_sha256='0'*64),'CAPACITY_REQUEST_PINS'),(dict(package_sha256='A'*64),'CAPACITY_REQUEST_PINS'),
    (dict(capacity_config_sha256=None),'CAPACITY_REQUEST_PINS'),(dict(writer_sha256='1'*63),'CAPACITY_REQUEST_PINS'),
    (dict(authority_sha256=''),'CAPACITY_REQUEST_PINS'),(dict(host_binding_sha256=None),'CAPACITY_REQUEST_PINS'),
    (dict(capacity_config_file='/c3po-capacity/config/session=2026-10-06.contingency_1.capacity.json'),'CAPACITY_REQUEST_CONFIG_FILE'),
    (dict(capacity_config_file='/var/lib/c3po-capacity/config/session=2026-10-06.primary.capacity.json'),'CAPACITY_REQUEST_CONFIG_FILE'),
    (dict(network='host'),'CAPACITY_REQUEST_NETWORK'),(dict(network='none'),'CAPACITY_REQUEST_NETWORK'),(dict(network='bridge'),'CAPACITY_REQUEST_NETWORK'),
    (dict(network='default'),'CAPACITY_REQUEST_NETWORK'),(dict(network='-net'),'CAPACITY_REQUEST_NETWORK'),
    (dict(env_files={'secret_path':'/etc/c3po-bar/token','pins':{'path':'/etc/c3po-reader/pins.env','sha256':'1'*64}}),'CAPACITY_REQUEST_ENV_FILES'),
    (dict(env_files={'secret_path':'/etc/c3po-reader/secret.env','pins':{'path':'/etc/c3po-reader/pins2.env','sha256':'1'*64}}),'CAPACITY_REQUEST_ENV_FILES'),
    (dict(env_files={'secret_path':'/etc/c3po-reader/secret.env','pins':{'path':'/etc/c3po-reader/pins.env','sha256':'0'*64}}),'CAPACITY_REQUEST_ENV_FILES'),
    (dict(env_files={'secret_path':'/etc/c3po-reader/secret.env'}),'CAPACITY_REQUEST_ENV_FILES'),
    (dict(docker_config='/root/.docker'),'CAPACITY_REQUEST_DOCKER_CONFIG'),
    (dict(writer_argv=None),'CAPACITY_REQUEST_WRITER_ARGV'),(dict(transport_watchdog_seconds=0),'CAPACITY_REQUEST_WATCHDOG'),
    (dict(transport_watchdog_seconds=3601),'CAPACITY_REQUEST_WATCHDOG'),
    (dict(documentary={}),'CAPACITY_REQUEST_DOCUMENTARY')])
def test_capacity_request_members(body,code):
    docs,_=docs_for();assert refusal(with_request(docs,mutated(**body)))==code

def test_inline_environment_must_be_exactly_the_four_values():
    base=e.capacity_request()
    for key,value in (('C3PO_R2D2_V2_SHADOW_ENABLED','false'),('C3PO_R2D2_V2_MASSIVE_BARS_ENABLED','1'),('C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','1'*64),
                      ('C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','/c3po-capacity/config/x.json'),('C3PO_DATABASE_URL','postgresql://x')):
        inline=dict(base['inline_env']);inline[key]=value;docs,_=docs_for()
        assert refusal(with_request(docs,mutated(inline_env=inline)))=='CAPACITY_REQUEST_INLINE_ENV',key

@pytest.mark.parametrize('mounts,code',[
    (MOUNTS[:3],'CAPACITY_REQUEST_MOUNTS'),(MOUNTS+[{'source':'/tmp','target':'/tmp','readonly':True}],'CAPACITY_REQUEST_MOUNTS'),
    (mounts_with(0,readonly=False),'CAPACITY_REQUEST_DATA_BIND'),(mounts_with(0,source='/mnt/day-d-data/r2d2-v2-release-20261005'),'CAPACITY_REQUEST_DATA_BIND'),
    (mounts_with(0,source='/mnt/day-d-data/'),'CAPACITY_REQUEST_DATA_BIND'),(mounts_with(0,source='/mnt'),'CAPACITY_REQUEST_DATA_BIND'),
    (mounts_with(0,source='/var/lib/c3po-day-release'),'CAPACITY_REQUEST_DATA_BIND'),(mounts_with(0,source='/var/lib/c3po/r2d2-v2-source-20261005'),'CAPACITY_REQUEST_DATA_BIND'),
    ([dict(item,extra=1) if index==0 else item for index,item in enumerate(MOUNTS)],'CAPACITY_REQUEST_MOUNTS'),
    (mounts_with(1,source='/var/lib/c3po/r2d2-v2-source-20261005/j'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(3,readonly=True),'CAPACITY_REQUEST_MOUNTS'),
    (mounts_with(2,target='/c3po-capacity-tree'),'CAPACITY_REQUEST_MOUNTS'),(mounts_with(0,target='/data'),'CAPACITY_REQUEST_MOUNTS'),
    (mounts_with(3,source='/etc/c3po-bar'),'CAPACITY_REQUEST_MOUNTS'),
    (mounts_with(1,readonly=False),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,source='/mnt/day-d-data/journal'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,source='/var/lib'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,source='/etc/c3po-bar/journal'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,source='/var/lib/c3po-reader/journal'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,source='/var/lib/c3po-capacity/j'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,source='/etc/c3po-reader'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,source='/'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,source='/var/lib/c3po-bar/../x'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,target='/c3po/journal'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,target='/app'),'CAPACITY_REQUEST_JOURNAL'),
    (mounts_with(1,target='/etc'),'CAPACITY_REQUEST_JOURNAL'),(mounts_with(1,target='/C3PO'),'CAPACITY_REQUEST_JOURNAL'),
    ([dict(item,extra=1) if index==1 else item for index,item in enumerate(MOUNTS)],'CAPACITY_REQUEST_MOUNTS'),
    ([dict(item,readonly='true') if index==1 else item for index,item in enumerate(MOUNTS)],'CAPACITY_REQUEST_MOUNTS')])
def test_the_four_binds(mounts,code):
    docs,_=docs_for();assert refusal(with_request(docs,mutated(mounts=mounts)))==code

def test_the_journal_bind_may_be_any_root_owned_directory_outside_the_others_and_the_binds_keep_their_order():
    for source in ('/var/lib/c3po-bar/journal','/srv/journal'):
        body=mutated(mounts=mounts_with(1,source=source));derived=M.k12_capacity_request(e.member(body))[2]
        assert derived['journal']=={'source':source,'target':'/c3po-journal'}
    reordered=[MOUNTS[3],MOUNTS[1],MOUNTS[0],MOUNTS[2]];derived=M.k12_capacity_request(e.member(mutated(mounts=reordered)))[2]
    words=M.k12_container_words(derived,'n',[]);assert [words[index+1] for index,word in enumerate(words) if word=='--mount']==[M.k12_mount_word(item) for item in reordered]

@pytest.mark.parametrize('change',[dict(view_opens_at='2026-10-06T10:30:00+00:00'),dict(latest_start='2026-10-06T10:44:00+00:00'),
    dict(view_valid_until='2026-10-06T10:45:11+00:00'),dict(not_after='2026-10-06T10:45:11+00:00'),dict(cutoff_at='2026-10-06T13:30:00+00:00'),
    dict(not_before='2026-10-06T10:45:00+00:00'),dict(not_before='2026-10-06T10:29:59+00:00'),dict(not_before='2026-10-05T10:38:00+00:00'),
    dict(not_before='2026-10-06T10:38:00Z'),dict(not_before='2026-10-06T10:38:00.5+00:00'),dict(cutoff_at='2026-10-06T13:20:00-03:00'),
    dict(view_opens_at='2026-10-06T11:45:00+00:00',latest_start='2026-10-06T11:45:00+00:00')])
def test_the_clock_of_the_window(change):
    docs,_=docs_for();code=refusal(with_request(docs,mutated(**change)))
    assert code in ('CAPACITY_REQUEST_CLOCK','CAPACITY_REQUEST_INSTANT','CAPACITY_REQUEST_WRITER_ARGV'),code

def test_every_instant_is_written_as_the_documents_tool_writes_it():
    for key in ('not_before','latest_start','not_after','view_opens_at','view_valid_until','cutoff_at'):
        body=e.capacity_request();body[key]=body[key].replace('+00:00','Z');docs,_=docs_for()
        assert refusal(with_request(docs,body))=='CAPACITY_REQUEST_INSTANT',key

def test_the_three_windows_are_the_a2_views_and_the_window_start_may_be_up_to_fifteen_minutes_before():
    for index,clock in ((1,'10:45:00'),(2,'11:45:00'),(3,'12:45:00')):
        derived=M.k12_capacity_request(e.member(e.capacity_request(index=index)))[2];assert derived['view_opens_at']=='2026-10-06T%s+00:00'%clock
    body=e.capacity_request(not_before='2026-10-06T10:30:00+00:00');M.k12_capacity_request(e.member(body))
    body=e.capacity_request(not_before='2026-10-06T10:44:59+00:00');M.k12_capacity_request(e.member(body))

@pytest.mark.parametrize('argv',[
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900','--prepare-first'],
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','0900'],
    ['--day','2026-10-07','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900'],
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900'],
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900','--require-go-mode','INDIVIDUAL'],
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900','--verify-only','--x'],
    ['--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at','2026-10-06T10:45:00+00:00','--max-wait-seconds','900','--preflight']])
def test_the_writer_argv_is_exactly_the_documents_tool_argv(argv):
    docs,_=docs_for();assert refusal(with_request(docs,mutated(writer_argv=argv)))=='CAPACITY_REQUEST_WRITER_ARGV'

def test_the_wait_is_the_requests_own_and_covers_the_window_start():
    for wait,code in ((600,None),(420,None),(419,'CAPACITY_REQUEST_CLOCK'),(901,'CAPACITY_REQUEST_WRITER_ARGV'),(1,'CAPACITY_REQUEST_CLOCK')):
        body=e.capacity_request(max_wait=wait);docs,_=docs_for()
        if code is None:
            docs=with_request(docs,body);docs.authenticate();assert docs.go['effects']['create'][-3]==str(wait)
        else:assert refusal(with_request(docs,body))==code,wait
    body=e.capacity_request();body['writer_argv'][8]=900;docs,_=docs_for();assert refusal(with_request(docs,body))=='CAPACITY_REQUEST_WRITER_ARGV'

def test_without_the_go_mode_argument_the_argv_has_nine_words():
    derived=M.k12_capacity_request(e.member(e.capacity_request(go_mode=None)))[2]
    assert derived['require_go_mode'] is None and len(derived['writer_argv'])==9

def test_documentary_hashes():
    body=e.capacity_request();body['documentary']=dict(body['documentary'],contract_sha256='0'*64);docs,_=docs_for()
    assert refusal(with_request(docs,body))=='CAPACITY_REQUEST_DOCUMENTARY'
    body=e.capacity_request();body['documentary']=dict(body['documentary'],extra='1'*64);docs,_=docs_for()
    assert refusal(with_request(docs,body))=='CAPACITY_REQUEST_DOCUMENTARY'

def test_chains_are_root_controlled_private_and_each_mode_names_its_own():
    docs,host=docs_for();rows=docs.plan['parent_rows']
    for name in rows:
        docs,_=docs_for();del docs.plan['parent_rows'][name];docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID',name
    docs,_=docs_for();docs.plan['parent_rows']['extra']=rows['config'];docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID'
    for name,index,change,code in (('config',2,dict(mode=0o775),'CHAIN_ROW_UNSAFE'),('config',3,dict(uid=1000),'CHAIN_ROW_UNSAFE'),
                                   ('config',-1,dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),('manifests',-1,dict(gid=1),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('manifests',-1,dict(mode=0o770),'CHAIN_ROW_UNSAFE'),('manifests',-1,dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),('config',1,dict(gid=1000),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('config',0,dict(mode=0o2755),'CHAIN_NOT_ROOT_CONTROLLED'),('docker_cli',2,dict(mode=0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('reader_config',-1,dict(mode=0o755),'DIRECTORY_NOT_ROOT_PRIVATE'),('docker_cli',-1,dict(mode=0o711),'DIRECTORY_NOT_ROOT_PRIVATE'),
                                   ('journal',-1,dict(mode=0o701),'DIRECTORY_NOT_ROOT_PRIVATE'),('receipts',-1,dict(mode=0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('receipts',-1,dict(mode=0o701),'DIRECTORY_NOT_ROOT_PRIVATE'),('data',-1,dict(mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
                                   ('data',-1,dict(mode=0o755),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),('data',-1,dict(uid=1000),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),
                                   ('data',-1,dict(gid=1000),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),('data',1,dict(gid=4),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('data',1,dict(mode=0o2755),'CHAIN_NOT_ROOT_CONTROLLED'),('data',1,dict(uid=1000,gid=1000),'CHAIN_ROW_UNSAFE'),
                                   ('data',0,dict(gid=7),'CHAIN_NOT_ROOT_CONTROLLED'),('data',2,dict(mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
                                   ('data',2,dict(device=801),'DATA_VOLUME_NOT_A_MOUNT_POINT'),
                                   ('journal',2,dict(gid=1000),'CHAIN_NOT_ROOT_CONTROLLED'),('journal',1,dict(path='/x'),'CHAIN_ROW_INVALID'),
                                   ('data',1,dict(path='/x'),'CHAIN_ROW_INVALID')):
        docs,_=docs_for();docs.plan['parent_rows'][name][index].update(change);docs.chain();assert refusal(docs)==code,(name,change)
    # the named exception: the volume root may be another uid with 2775-free bits (uid 1000, 0755), not world-writable
    docs,_=docs_for();assert docs.plan['parent_rows']['data'][2]['uid']==1000;docs.authenticate()
    docs,_=docs_for();docs.plan['parent_rows']['data'][2].update(gid=5,mode=0o2775);docs.chain();docs.authenticate()
    docs,host=docs_for('STOP');assert set(docs.plan['parent_rows'])=={'manifests'}
    docs.plan['parent_rows']['receipts']=e.chains(host,['receipts'])['receipts'];docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID'

def test_journal_rows_follow_the_journal_of_the_request():
    docs,host=docs_for();host.tree.add('/srv/journal',mode=0o700);body=mutated(mounts=mounts_with(1,source='/srv/journal'))
    with_request(docs,body);assert refusal(docs)=='CHAIN_ROW_INVALID'
    docs.plan['parent_rows']['journal']=e.rows(host,'/srv/journal');docs.chain();docs.authenticate()

@pytest.mark.parametrize('change',[[],[None],'x',[{}]])
def test_removals_shape(change):
    docs,_=docs_for('REMOVE');docs.plan['removals']=change;docs.chain();assert refusal(docs)=='REMOVALS_INVALID'

def test_removals_members_and_distinct():
    docs,host=docs_for('REMOVE');items=docs.plan['removals']
    for key,value in (('day','2026-10-05'),('window_slot',4),('container_id','A'*64),('image_id','c3po/backend:production'),
                      ('launch_request_sha256','0'*64),('capacity_request_sha256',None)):
        docs,_=docs_for('REMOVE');docs.plan['removals'][0][key]=value;docs.chain();assert refusal(docs)=='REMOVALS_INVALID',key
    docs,_=docs_for('REMOVE');docs.plan['removals'][1]['container_id']=docs.plan['removals'][0]['container_id'];docs.chain();assert refusal(docs)=='REMOVALS_INVALID'
    docs,_=docs_for('REMOVE');docs.plan['removals'][1].update(day='2026-10-06',window_slot=1);docs.chain();assert refusal(docs)=='REMOVALS_INVALID'
    docs,_=docs_for('REMOVE');docs.plan['removals']=items*4+[items[0]];docs.chain();assert refusal(docs)=='REMOVALS_INVALID'
    docs,_=docs_for('REMOVE');docs.plan['removals'][0]['extra']=1;docs.chain();assert refusal(docs)=='REMOVALS_INVALID'


# ---------------------------------------------------------------- effects: literal, as written independently here
def test_effects_of_launch_are_the_literal_argv_the_signers_read():
    docs,host=docs_for();effects=docs.authority['effects'];body=e.capacity_request();raw=f.canonical(body)
    view='2026-10-06T10:45:00+00:00';config='/c3po-capacity/config/session=2026-10-06.primary.capacity.json';config_sha=body['capacity_config_sha256']
    expected=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no',
              '--name','c3po-k12-20261006-w1','--label',"c3po.k12.request_sha256=<this request's sha256>",'--label','c3po.k12.capacity_request_sha256='+e.sha(raw),
              '--network','c3po_c3po_internal','--env-file','/etc/c3po-reader/secret.env','--env-file','/etc/c3po-reader/pins.env',
              '--env','C3PO_R2D2_V2_SHADOW_ENABLED=true','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',
              '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+config,'--env','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+config_sha,
              '--mount','type=bind,source=/mnt/day-d-data,target=/app/day-d-data,readonly',
              '--mount','type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-journal,readonly',
              '--mount','type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly',
              '--mount','type=bind,source=/etc/c3po-bar/manifests,target=/etc/c3po-bar/manifests',
              e.IMAGE,'python','-I','-B','/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER),
              '--day','2026-10-06','--manifest-directory','/etc/c3po-bar/manifests','--prepare-first','--view-opens-at',view,'--max-wait-seconds','900',
              '--require-go-mode','DELEGATED_ACT_B']
    assert effects['create']==expected and effects['start']==['start','<the 64-hex ID create printed>']
    assert effects['container']=={'removed_on_exit':False,'restart':'no','parks_until':view} and effects['docker_config']=='/etc/c3po-reader/docker-cli'
    assert effects['writer']=={'path':'/var/lib/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER),'sha256':e.sha(e.WRITER),'require':'ROOT_0600_ONE_LINK'}
    assert effects['capacity_config']=={'path':'/var/lib/c3po-capacity/config/session=2026-10-06.primary.capacity.json','sha256':config_sha,'require':'ROOT_0600_ONE_LINK'}
    assert effects['pins_env']=={'path':'/etc/c3po-reader/pins.env','sha256':e.sha(e.PINS),'require':'ROOT_0600_ONE_LINK'}
    assert effects['secret_env']=={'path':'/etc/c3po-reader/secret.env','require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'}
    assert effects['journal']=={'path':'/var/lib/c3po-bar/journal','target':'/c3po-journal','require':'ROOT_0700_CATALOG_ROOT_0600'}
    assert (effects['day'],effects['window'],effects['window_slot'],effects['container_name'])==('2026-10-06','primary',1,'c3po-k12-20261006-w1')
    assert (effects['view_opens_at'],effects['cutoff_at'],effects['capacity_request_sha256'])==(view,'2026-10-06T13:20:00+00:00',e.sha(raw))
    assert effects['earlier_windows']=='EXITED_WITH_PRIVATE_RECEIPT_AND_ONE_VALID_LINE_NOT_TERMINAL_OR_NEVER_STARTED_OR_ABSENT'
    assert effects['manifest_of_the_day']=='ABSENT_OR_TWO_LINKS_OR_AFTER_AN_EARLIER_WINDOW_WITH_A_LINE'
    assert (effects['mode'],effects['epoch'],effects['operation'])==('LAUNCH','R2D2-V2-SHADOW-2026-10-05','GO_WRITE_HOSTOPS02_K12_WINDOW_01')
    assert effects['writes_into_manifests_capacity_journal_or_data'] is False and effects['environment_printed'] is False and effects['activation'] is False
    assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and set(effects['chains'])=={'config','manifests','reader_config','docker_cli','journal','data','receipts'}
    assert effects['chains']['journal']['path']=='/var/lib/c3po-bar/journal' and effects['chains']['data']['path']==e.RELEASE
    assert effects['data']=={'path':'/mnt/day-d-data','target':'/app/day-d-data','read_only':True,'exception':'CODEX_429_5986698996',
        'release':{'path':e.RELEASE+'/release.CERTIFIED.json','sha256':e.sha(e.RELEASE_BYTES),'require':'ROOT_0600_ONE_LINK',
                   'checked':'BEFORE_THE_CREATE_AND_AFTER_THE_START'}}
    assert effects['chain_rule']=='ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK'
    assert effects['earlier_window_stopped_before_its_view']=='REFUSED_DAY_STOPPED'

def test_effects_of_the_other_modes():
    docs,_=docs_for('PERSIST');effects=docs.go['effects']
    assert effects['read']==['logs','<the 64-hex ID of that exited container>'] and effects['launch_request_sha256']=='5e'*32
    assert effects['creates']=={'path':'/var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json','mode_octal':'0600','uid':0,'gid':0,
                                'schema':'K12_PERSISTED_WRITER_RECEIPT_V1','expect':'ABSENT'}
    assert effects['logs_bounds']=={'class':'QUICK','seconds':8,'stdout_bytes':16384,'follow':False,'tail':False}
    assert effects['requires']=='EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE_NOT_OOM'
    docs,_=docs_for('STOP');effects=docs.go['effects']
    assert effects['stop']==['stop','-t','5','<the 64-hex ID of that running container>'] and effects['not_later_than_seconds_before_the_view']==25
    assert effects['launch_request_sha256']=='5e'*32 and effects['container_name']=='c3po-k12-20261006-w1'
    docs,_=docs_for('REMOVE');effects=docs.go['effects'];items=docs.plan['removals']
    assert effects['command']==['rm']+[item['container_id'] for item in items] and effects['force'] is False and effects['volumes'] is False
    assert [row['container_name'] for row in effects['removals']]==['c3po-k12-20261006-w1','c3po-k12-20261007-w1','c3po-k12-20261007-w2']
    assert all(row['require']=='EXITED_WITH_ITS_PRIVATE_RECEIPT_OR_STOPPED_BEFORE_ITS_VIEW_OR_NEVER_STARTED' for row in effects['removals'])
    assert effects['removals'][0]['labels']=={'c3po.k12.request_sha256':items[0]['launch_request_sha256'],'c3po.k12.capacity_request_sha256':items[0]['capacity_request_sha256']}
    assert effects['removals'][0]['image_id']==e.IMAGE and effects['removals'][0]['container_id']==items[0]['container_id']
    assert 'create' not in effects and 'capacity_request_sha256' not in effects
    for mode in ('PERSIST','STOP','REMOVE'):assert docs_for(mode)[0].go['effects']['mode']==mode

def test_a_changed_effect_is_refused_at_both_layers():
    docs,_=docs_for();docs.authority['effects']['create'][-1]='INDIVIDUAL';docs.go['effects']=copy.deepcopy(docs.authority['effects'])
    docs.chain(effects=False);assert refusal(docs)=='EFFECTS_BINDING'


# ---------------------------------------------------------------- LAUNCH
def test_launch_creates_and_starts_one_parked_container_exactly_as_signed():
    docs,host=docs_for();receipt=complete(docs,host)
    created=[entry for entry in host.commands if entry['argv'][1:2]==['create']];started=[entry for entry in host.commands if entry['argv'][1:2]==['start']]
    assert len(created)==1 and len(started)==1 and [entry['argv'][1] for entry in host.commands].count('stop')==0
    expected=[word.replace("<this request's sha256>",receipt['request_sha256']) for word in docs.go['effects']['create']]
    assert created[0]['argv'][1:]==expected and created[0]['capture'] is True and created[0]['seconds']==8
    item=host.docker.container('c3po-k12-20261006-w1')
    assert started[0]['argv'][1:]==['start',item['Id']] and started[0]['seconds']==20 and item['State']['Running'] is True
    assert all(entry['docker_config']=='/etc/c3po-reader/docker-cli' and entry['variables']=={} for entry in host.commands)
    assert item['Config']['Labels']=={'c3po.k12.request_sha256':receipt['request_sha256'],'c3po.k12.capacity_request_sha256':docs.plan['capacity_request']['sha256']}
    assert host.docker.environment_of[item['Id']]['C3PO_DATABASE_URL']==e.SECRET_URL     # the CLI read the env file; the source never did
    assert not [entry for entry in host.log if entry[0] in ('open','read') and 'secret.env' in str(entry[1])]
    assert host.mutating()==[] and receipt['container_id']==item['Id'] and receipt['detail']['launched']['parks_until']=='2026-10-06T10:45:00+00:00'
    assert receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0} and receipt['commands_started']['EFFECT']==2
    assert receipt['detail']['manifest_before']=={'present':False,'links':None} and receipt['detail']['day_containers']==[]

def test_a_writer_that_ends_at_once_is_still_a_complete_launch():
    docs,host=docs_for();host.docker.on_start=lambda item:(3,e.writer_line('REFUSED','MANIFEST_GO_INVALID'))
    receipt=complete(docs,host);assert receipt['detail']['launched']['state']=='exited' and receipt['detail']['launched']['running'] is False

def change(host,path,**attributes):
    node=host.tree.get(path)
    for key,value in attributes.items():setattr(node,key,value)

WRITER_PATH=e.CONFIG+'/manifest_writer-'+e.sha(e.WRITER)+'.py'
CONFIG_PATH=e.CONFIG+'/session=2026-10-06.primary.capacity.json'
@pytest.mark.parametrize('action,code',[
    (lambda host:host.tree.remove(WRITER_PATH),'WRITER_FILE_ABSENT'),
    (lambda host:change(host,WRITER_PATH,mode=0o644),'WRITER_FILE_NOT_PRIVATE'),(lambda host:change(host,WRITER_PATH,uid=1000),'WRITER_FILE_NOT_PRIVATE'),
    (lambda host:change(host,WRITER_PATH,gid=1000),'WRITER_FILE_NOT_PRIVATE'),(lambda host:change(host,WRITER_PATH,nlink=2),'WRITER_FILE_NOT_PRIVATE'),
    (lambda host:change(host,WRITER_PATH,content=bytearray(e.WRITER+b'#')),'WRITER_BYTES_NOT_THE_SIGNED_ONES'),
    (lambda host:host.tree.remove(CONFIG_PATH),'CAPACITY_CONFIG_ABSENT'),(lambda host:change(host,CONFIG_PATH,mode=0o640),'CAPACITY_CONFIG_NOT_PRIVATE'),
    (lambda host:change(host,CONFIG_PATH,content=bytearray(b'{}')),'CAPACITY_CONFIG_NOT_THE_SIGNED_BYTES'),
    (lambda host:host.tree.remove(e.READER+'/pins.env'),'PINS_ENV_ABSENT'),(lambda host:change(host,e.READER+'/pins.env',mode=0o644),'PINS_ENV_NOT_PRIVATE'),
    (lambda host:change(host,e.READER+'/pins.env',content=bytearray(e.PINS+b'X=1\n')),'PINS_ENV_NOT_THE_SIGNED_BYTES'),
    (lambda host:host.tree.remove(e.READER+'/secret.env'),'SECRET_ENV_ABSENT'),(lambda host:change(host,e.READER+'/secret.env',mode=0o640),'SECRET_ENV_NOT_PRIVATE'),
    (lambda host:change(host,e.READER+'/secret.env',uid=1000),'SECRET_ENV_NOT_PRIVATE'),(lambda host:change(host,e.READER+'/secret.env',nlink=2),'SECRET_ENV_NOT_PRIVATE'),
    (lambda host:host.tree.add(e.DOCKER_CLI+'/config.json',kind='file',mode=0o600),'DOCKER_CLI_DIRECTORY_NOT_EMPTY'),
    (lambda host:host.tree.remove(e.JOURNAL+'/epoch.json'),'JOURNAL_CATALOG_NOT_AS_REQUIRED'),
    (lambda host:change(host,e.JOURNAL+'/maintenance.lock',mode=0o644),'JOURNAL_CATALOG_NOT_AS_REQUIRED'),
    (lambda host:change(host,e.JOURNAL+'/epoch.json',uid=1000),'JOURNAL_CATALOG_NOT_AS_REQUIRED'),
    (lambda host:host.docker.images.__setitem__(0,dict(host.docker.images[0],Config={'Labels':{'org.opencontainers.image.revision':'a'*40}})),'IMAGE_REVISION_MISMATCH'),
    (lambda host:host.docker.images.pop(0),'COMMAND_FAILED'),
    (lambda host:host.tree.add(e.MANIFESTS+'/x',kind='symlink'),None),
    (lambda host:change(host,e.CONFIG,ino=99999),'PARENT_IDENTITY_MISMATCH'),(lambda host:change(host,e.JOURNAL,mode=0o755),'PARENT_IDENTITY_MISMATCH'),
    (lambda host:change(host,e.RECEIPTS,uid=1000),'PARENT_IDENTITY_MISMATCH')])
def test_launch_prechecks_refuse_with_nothing_changed(action,code):
    docs,host=docs_for();action(host)
    if code is None:complete(docs,host);return
    refused(docs,host,code)

def test_launch_refuses_an_image_answer_of_another_id():
    docs,host=docs_for();real=host.docker.images[0];other=dict(real,Id=hostemu.OTHER,RepoTags=[e.IMAGE]);host.docker.images[0]=other
    refused(docs,host,'IMAGE_ID_MISMATCH')

def test_launch_refuses_a_writer_file_above_its_limit():
    docs,host=docs_for();change(host,WRITER_PATH,content=bytearray(b'#'*131073));refused(docs,host,'FILE_TOO_LARGE')

def test_a_failure_inside_an_effect_step_is_partial_with_its_own_code():
    docs,host=docs_for();runs=[0]
    def hook(host,name,detail,calls):
        if name=='run' and detail[0][1:3]==['container','inspect'] and any(entry['argv'][1:2]==['create'] for entry in host.commands):
            raise RuntimeError('injected')
    host.hook=hook;receipt=partial(docs,host,'EFFECT_STEP_FAILED');assert receipt['mutating_calls']['uncertain']==1

def test_friday_is_a_capacity_day_and_saturday_is_not():
    M.k12_capacity_request(e.member(e.capacity_request('2026-10-09')))
    docs,_=docs_for();assert refusal(with_request(docs,e.capacity_request('2026-10-10')))=='CAPACITY_REQUEST_DAY'

def test_launch_symbolic_links_are_never_followed():
    docs,host=docs_for();host.tree.remove(WRITER_PATH);host.tree.add(WRITER_PATH,kind='symlink');refused(docs,host,'PRECHECK_OS_ERROR')
    docs,host=docs_for();host.tree.remove(e.READER+'/secret.env');host.tree.add(e.READER+'/secret.env',kind='symlink');refused(docs,host,'SECRET_ENV_NOT_PRIVATE')

def test_launch_and_the_manifest_of_the_day():
    docs,host=docs_for();host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600,content=b'{}')
    receipt=refused(docs,host,'MANIFEST_PRESENT_WITHOUT_AN_EARLIER_WINDOW');assert receipt['detail']['manifest_before']=={'present':True,'links':1}
    docs,host=docs_for();node=host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600,content=b'{}');node.nlink=2
    receipt=complete(docs,host);assert receipt['detail']['manifest_before']=={'present':True,'links':2}
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,1,e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'))
    e.persisted(host,K,first,index=1);host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600,content=b'{}');complete(docs,host)
    docs,host=contingency();e.launched(host,K,index=1,state='created');host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600)
    refused(docs,host,'MANIFEST_PRESENT_WITHOUT_AN_EARLIER_WINDOW')

def test_launch_clock():
    for now,code in (('10:37:59','RUN_BEFORE_THE_WINDOW_START'),('10:44:16','TOO_CLOSE_TO_THE_VIEW'),('10:44:15',None),('10:38:00',None)):
        docs,host=docs_for(now=e.utc(e.DAY,now))
        if code is None:complete(docs,host)
        else:
            refused(docs,host,code);assert host.commands==[] and not [entry for entry in host.log if entry[0] in ('open','lstat')],'the clock is judged before anything is observed'
    docs,host=docs_for(now='2026-10-07T10:40:00+00:00');refused(docs,host,'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')

def test_launch_refuses_another_boot():
    docs,host=docs_for();docs.plan['evidence_boot_id_sha256']='ab'*32;docs.chain();refused(docs,host,'EVIDENCE_FROM_EARLIER_BOOT')

def test_launch_budget_before_the_first_effect():
    docs,host=docs_for();budget=f.Budget(docs.now,command_seconds=0).attach(host);budget.cost(18.5,'ps','-a')
    receipt=refused(docs,host,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',**budget.options());assert receipt['detail']['seconds_left_before_first_effect']==41
    docs,host=docs_for();budget=f.Budget(docs.now,command_seconds=0).attach(host);budget.cost(18,'ps','-a');complete_receipt=docs.run(host,**budget.options())
    assert complete_receipt['status']==M.COMPLETE_STATUS,complete_receipt['code']

def test_launch_lead_is_checked_again_just_before_the_create():
    docs,host=docs_for(now=e.utc(e.DAY,'10:44:00'));budget=f.Budget(docs.now).attach(host);budget.cost(16,'ps','-a')
    refused(docs,host,'TOO_CLOSE_TO_THE_VIEW',**budget.options())

def test_launch_the_preflight_container_still_there_is_a_refusal():
    docs,host=docs_for();host.docker.containers.append(hostemu.container('c3po-k12-20261006-preflight',e.IMAGE,e.IMAGE,[]))
    refused(docs,host,'PREFLIGHT_CONTAINER_PRESENT')

# -- earlier windows of the same day
def contingency(index=2):
    docs,host=docs_for(now=e.utc(e.DAY,'11:40:00'),body=e.capacity_request(index=index));return docs,host

def test_launch_of_a_contingency_after_a_window_that_did_not_publish():
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,3,e.writer_line('REFUSED','MANIFEST_GO_INVALID'))
    e.persisted(host,K,first,index=1);receipt=complete(docs,host)
    assert receipt['detail']['day_containers']==[{'name':'c3po-k12-20261006-w1','state':'exited'}]
    assert host.docker.container('c3po-k12-20261006-w2')['State']['Running'] is True

def test_launch_of_a_contingency_after_a_primary_that_never_started_or_never_existed():
    docs,host=contingency();e.launched(host,K,index=1,state='created');complete(docs,host)
    docs,host=docs_for(now=e.utc(e.DAY,'12:40:00'),body=e.capacity_request(index=3));complete(docs,host)

@pytest.mark.parametrize('line,exit_code,code',[(e.writer_line(),0,'DAY_ALREADY_PUBLISHED'),(e.writer_line('ALREADY_PUBLISHED_VERIFIED'),0,'DAY_ALREADY_PUBLISHED'),
    (e.writer_line(**e.EMPTY_LIST),3,'DAY_TERMINAL_EMPTY_LIST'),(e.writer_line(**dict(e.EMPTY_LIST,prepare_status='PRECOMMITTED')),3,'DAY_TERMINAL_EMPTY_LIST'),
    (e.writer_line(**dict(e.EMPTY_LIST,prepare_status='ALREADY_COMMITTED')),3,'DAY_TERMINAL_EMPTY_LIST'),
    (e.writer_line(**dict(e.EMPTY_LIST,prepare_status='ATTEMPTED')),3,None),(e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'),3,None),
    (e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'),1,None),(e.writer_line('UNVERIFIED','MANIFEST_X_Y'),1,None),
    (e.writer_line('REFUSED','MANIFEST_X_Y'),3,None),
    (e.writer_line('MATCH_VERIFIED',mode='VERIFY_ONLY'),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),(b'',3,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
    (b'garbage\n',3,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),(e.writer_line(extra=1),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
    (e.writer_line(mode='VERIFY_ONLY'),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),(e.writer_line(session=None),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
    (e.writer_line(),3,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),(e.writer_line('REFUSED','MANIFEST_X_Y'),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
    (e.writer_line(stale_temporaries=5000),0,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE')])
def test_launch_after_an_earlier_window_with_its_line(line,exit_code,code):
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,exit_code,line)
    e.persisted(host,K,first,index=1)
    if code is None:complete(docs,host)
    else:refused(docs,host,code)

def test_launch_after_a_window_stopped_before_its_view_without_a_receipt():
    """Rev 2: PERSIST keeps nothing of a stop (empty output), so the stopped container itself, read by inspect, is
    what stops the day; an exited container without a receipt that does not show the stop is not settled."""
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.do_stop(['-t','5',first['Id']]);refused(docs,host,'DAY_STOPPED_BEFORE_A_VIEW')
    for code,oom,finished in ((143,True,'2026-10-06T10:41:30.000000000Z'),(3,False,'2026-10-06T10:41:30.000000000Z'),
                              (143,False,'2026-10-06T10:45:00.000000000Z'),(137,False,'garbage'),(143,False,'1999'),(143,False,'2026-10-06T11:00:00Z')):
        docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,code,b'',oom=oom,finished=finished)
        refused(docs,host,'EARLIER_WINDOW_RECEIPT_NOT_PERSISTED')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,137,b'',finished='2026-10-06T10:44:59.900000000Z')
    refused(docs,host,'DAY_STOPPED_BEFORE_A_VIEW')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.do_stop(['-t','5',first['Id']]);host.docker.inspect_returncode=1
    refused(docs,host,'EARLIER_WINDOW_RECEIPT_NOT_PERSISTED')        # an inspect that fails is never a proof of the stop

def test_launch_after_a_window_stopped_before_its_view_is_refused_for_the_whole_day():
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.do_stop(['-t','5',first['Id']]);e.persisted(host,K,first,index=1)
    refused(docs,host,'DAY_STOPPED_BEFORE_A_VIEW')
    docs,host=docs_for(now=e.utc(e.DAY,'12:40:00'),body=e.capacity_request(index=3));first=e.launched(host,K,index=1);host.docker.do_stop(['-t','5',first['Id']])
    e.persisted(host,K,first,index=1);refused(docs,host,'DAY_STOPPED_BEFORE_A_VIEW')
    for change in (dict(oom=True),dict(code=1),dict(code=137,finished='2026-10-06T10:45:01.000000000Z')):
        docs,host=contingency();first=e.launched(host,K,index=1)
        host.docker.exit(first,change.get('code',143),b'',oom=change.get('oom',False),finished=change.get('finished','2026-10-06T10:41:30.000000000Z'))
        e.persisted(host,K,first,index=1);refused(docs,host,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,137,b'',finished='2026-10-06T10:44:59.900000000Z')
    e.persisted(host,K,first,index=1);refused(docs,host,'DAY_STOPPED_BEFORE_A_VIEW')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,143,b'',finished='2026-10-06T10:41:30.000000000Z')
    e.persisted(host,K,first,index=1,finished_at=5);refused(docs,host,'EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE')

def test_what_counts_as_a_stop_before_the_view():
    for code,stdout,finished,expected in ((143,b'','2026-10-06T10:45:00.500000000Z','EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
                                          (143,b'garbage\n','2026-10-06T10:41:30.000000000Z','EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE'),
                                          (143,b'','2026-10-06T10:44:59.999999999Z','DAY_STOPPED_BEFORE_A_VIEW')):
        docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,code,stdout,finished=finished);e.persisted(host,K,first,index=1)
        refused(docs,host,expected)

def test_launch_after_an_earlier_window_whose_state_is_not_known():
    docs,host=contingency();first=e.launched(host,K,index=1);refused(docs,host,'CAPACITY_CONTAINER_OF_THE_DAY_NOT_SETTLED')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,3,b'');refused(docs,host,'EARLIER_WINDOW_RECEIPT_NOT_PERSISTED')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,3,b'');e.persisted(host,K,first,index=1)
    change(host,e.RECEIPTS+'/k12-2026-10-06-w1.writer.json',mode=0o644);refused(docs,host,'EARLIER_WINDOW_RECEIPT_NOT_PRIVATE')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,3,b'');e.persisted(host,K,first,index=1,container_id='ab'*32)
    refused(docs,host,'PERSISTED_RECEIPT_INVALID')
    docs,host=contingency();first=e.launched(host,K,index=1);host.docker.exit(first,3,b'');e.persisted(host,K,first,index=1,window_slot=2)
    refused(docs,host,'PERSISTED_RECEIPT_INVALID')
    for state in ('paused','restarting','dead','removing'):
        docs,host=contingency();first=e.launched(host,K,index=1);first['State']['Status']=state;refused(docs,host,'CAPACITY_CONTAINER_OF_THE_DAY_NOT_SETTLED')

def test_launch_refuses_its_own_name_taken_or_a_later_window_present():
    docs,host=docs_for();e.launched(host,K,index=1,state='created');refused(docs,host,'CONTAINER_NAME_TAKEN')
    docs,host=docs_for();item=e.launched(host,K,index=2);host.docker.exit(item,3,b'');refused(docs,host,'CAPACITY_CONTAINER_OF_THE_DAY_NOT_EARLIER')
    docs,host=docs_for();host.docker.containers.append(hostemu.container('c3po-k12-20261006-w9',e.IMAGE,e.IMAGE,[],running=False))
    refused(docs,host,'CAPACITY_CONTAINER_OF_THE_DAY_NOT_EARLIER')

def test_launch_refuses_a_capacity_container_of_another_day_that_is_not_settled():
    docs,host=docs_for();item=hostemu.container('c3po-k12-20261005-w1',e.IMAGE,e.IMAGE,[]);host.docker.containers.append(item)
    refused(docs,host,'CAPACITY_CONTAINER_OF_ANOTHER_DAY_NOT_SETTLED')
    docs,host=docs_for();host.docker.containers.append(hostemu.container('c3po-k12-20261005-w1',e.IMAGE,e.IMAGE,[],running=False));complete(docs,host)
    docs,host=docs_for();item=hostemu.container('c3po-k12-20261005-w2',e.IMAGE,e.IMAGE,[],running=False);item['State']['Status']='created'
    host.docker.containers.append(item);complete(docs,host)
    docs,host=docs_for();item=hostemu.container('c3po-k12-20261005-w3',e.IMAGE,e.IMAGE,[],running=False);item['State']['Status']='paused'
    host.docker.containers.append(item);refused(docs,host,'CAPACITY_CONTAINER_OF_ANOTHER_DAY_NOT_SETTLED')

def test_launch_records_the_lead_at_the_create():
    docs,host=docs_for(now=e.utc(e.DAY,'10:43:00'));receipt=complete(docs,host);assert receipt['detail']['seconds_to_the_view_before_create']==120

def test_launch_ignores_the_family_containers_of_other_days():
    docs,host=docs_for(now='2026-10-07T10:40:00+00:00',body=e.capacity_request('2026-10-07'))
    host.tree.add(e.CONFIG+'/session=2026-10-07.primary.capacity.json',kind='file',mode=0o600,content=e.config_bytes('2026-10-07','primary'))
    old=e.launched(host,K,index=1);host.docker.exit(old,0,e.writer_line())
    receipt=complete(docs,host);assert receipt['detail']['day_containers']==[]

# -- the effects of LAUNCH
def test_create_that_never_starts_is_a_refusal():
    docs,host=docs_for();host.absent={('create','--pull')};receipt=refused(docs,host,'COMMAND_NOT_STARTED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}

def test_create_that_fails_without_a_container_is_a_refusal():
    docs,host=docs_for();host.docker.create_returncode=125;refused(docs,host,'CREATE_FAILED')

def test_create_that_hangs_is_uncertain():
    docs,host=docs_for();host.hang_after={('create','--pull')};receipt=partial(docs,host,'CREATE_UNCERTAIN')
    assert receipt['detail']['after_create']['name']=='/c3po-k12-20261006-w1' and receipt['mutating_calls']['uncertain']==1
    docs,host=docs_for();host.hang={('create','--pull')};receipt=partial(docs,host,'CREATE_UNCERTAIN');assert receipt['detail']['after_create'] is None

def test_create_that_failed_while_the_listing_cannot_prove_the_absence():
    docs,host=docs_for();host.docker.create_returncode=125;original=host.docker.do_create
    def create(arguments):
        out=original(arguments);host.docker.ps_returncode=1;return out
    host.docker.do_create=create;receipt=partial(docs,host,'CREATE_FAILED_STATE_UNKNOWN');assert receipt['mutating_calls']['uncertain']==1
    docs,host=docs_for();host.docker.create_returncode=125;original=host.docker.do_create
    def appears(arguments):
        out=original(arguments);host.docker.containers.append(hostemu.container('c3po-k12-20261006-w1',e.IMAGE,e.IMAGE,[],running=False));return out
    host.docker.do_create=appears;host.docker.inspect_returncode=0
    def no_inspect(host_,name,detail,calls):
        if name=='run' and detail[0][1:3]==['container','inspect']:host_.docker.inspect_returncode=1
    host.hook=no_inspect;partial(docs,host,'CREATE_FAILED_STATE_UNKNOWN')

def test_create_whose_output_is_not_its_id():
    docs,host=docs_for();host.docker.create_output=b'warning\n';partial(docs,host,'CREATE_RETURNED_WITHOUT_ITS_ID')
    docs,host=docs_for();host.docker.create_output=b'';host.docker.create_effect=False;refused(docs,host,'CREATE_FAILED')
    docs,host=docs_for();host.docker.create_output=b'A'*64+b'\n';partial(docs,host,'CREATE_RETURNED_WITHOUT_ITS_ID')

def test_create_whose_container_has_another_name():
    docs,host=docs_for();original=host.docker.do_create
    def renamed(arguments):
        code,out=original(arguments);host.docker.containers[-1]['Name']='/c3po-k12-20261006-w9';return code,out
    host.docker.do_create=renamed;partial(docs,host,'CREATED_CONTAINER_NOT_AS_SIGNED')

def test_create_whose_container_is_not_as_signed():
    docs,host=docs_for();original=host.docker.do_create
    def tampered(arguments):
        code,out=original(arguments);host.docker.containers[-1]['HostConfig']['AutoRemove']=True;return code,out
    host.docker.do_create=tampered;partial(docs,host,'CREATED_CONTAINER_NOT_AS_SIGNED')
    docs,host=docs_for();original=host.docker.do_create
    def started(arguments):
        code,out=original(arguments);host.docker.containers[-1]['State'].update(Status='running',Running=True);return code,out
    host.docker.do_create=started;partial(docs,host,'CREATED_CONTAINER_NOT_AS_SIGNED')
    docs,host=docs_for();original=host.docker.do_create
    def other(arguments):
        code,out=original(arguments);return code,(hostemu.container('x',e.IMAGE,e.IMAGE,[])['Id']+'\n').encode()
    host.docker.do_create=other;partial(docs,host,'CREATED_CONTAINER_NOT_AS_SIGNED')

def test_start_failures():
    docs,host=docs_for();host.absent={('start',)};receipt=partial(docs,host,'COMMAND_NOT_STARTED')
    assert host.docker.container('c3po-k12-20261006-w1')['State']['Status']=='created' and receipt['mutating_calls']['succeeded']==1
    docs,host=docs_for();host.docker.start_returncode=1;host.docker.start_effect=False;receipt=partial(docs,host,'START_FAILED')
    assert receipt['mutating_calls']=={'issued':2,'succeeded':1,'failed_nothing_changed':1,'uncertain':0}
    docs,host=docs_for();host.docker.start_returncode=1;partial(docs,host,'START_RETURNED_NONZERO')
    docs,host=docs_for();host.hang_after={('start',)};receipt=partial(docs,host,'START_UNCERTAIN');assert receipt['detail']['after_start']['running'] is True
    docs,host=docs_for();host.hang={('start',)};receipt=partial(docs,host,'START_UNCERTAIN');assert receipt['detail']['after_start']['started'] is False

def test_start_read_back_that_is_not_the_container():
    docs,host=docs_for();original=host.docker.do_start
    def gone(arguments):
        code,out=original(arguments);host.docker.containers.pop();return code,out
    host.docker.do_start=gone;partial(docs,host,'STARTED_CONTAINER_NOT_READ_BACK')
    docs,host=docs_for();original=host.docker.do_start
    def odd(arguments):
        code,out=original(arguments);host.docker.containers[-1]['State'].update(Status='exited',StartedAt=e.NEVER);return code,out
    host.docker.do_start=odd;partial(docs,host,'STARTED_CONTAINER_NOT_READ_BACK')


# ---------------------------------------------------------------- PERSIST
def persisted_file(host):return bytes(host.tree.get(e.RECEIPTS+'/k12-2026-10-06-w1.writer.json').content)

def test_persist_stores_the_line_and_the_exit_state_exactly():
    docs,host=docs_for('PERSIST');receipt=complete(docs,host);item=host.docker.container('c3po-k12-20261006-w1');stdout=e.writer_line()
    expected={'schema':'K12_PERSISTED_WRITER_RECEIPT_V1','epoch':e.EPOCH,'day':'2026-10-06','window':'primary','window_slot':1,'container_id':item['Id'],
              'container_name':'c3po-k12-20261006-w1','launch_request_sha256':'5e'*32,'capacity_request_sha256':docs.plan['capacity_request']['sha256'],
              'persist_request_sha256':receipt['request_sha256'],'image_id':e.IMAGE,'exit_code':0,'oom_killed':False,
              'started_at':item['State']['StartedAt'],'finished_at':item['State']['FinishedAt'],'stdout_b64':base64.b64encode(stdout).decode(),
              'stdout_sha256':e.sha(stdout),'stdout_bytes':len(stdout)}
    raw=persisted_file(host);assert raw==f.canonical(expected)
    node=host.tree.get(e.RECEIPTS+'/k12-2026-10-06-w1.writer.json');assert (node.uid,node.gid,node.mode,node.nlink)==(0,0,0o600,1)
    assert sorted(host.tree.get(e.RECEIPTS).children)==['k12-2026-10-06-w1.writer.json']
    assert [entry['argv'][1:] for entry in host.commands if entry['argv'][1]=='logs']==[['logs',item['Id']]]
    line=receipt['detail']['writer_line'];assert line['valid'] is True and line['terminal']=='PUBLISHED' and line['public']['binding_sha256']==e.label('binding')
    assert line['public']['manifest_sha256_present'] is True and line['public']['symbol_count_present'] is True and 'symbol_count' not in line['public']
    assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and receipt['mutating_calls']['failed_nothing_changed']==1
    assert receipt['ledger'][0]['sha256_observed']==e.sha(raw)==receipt['ledger'][0]['sha256_signed']
    assert e.engine(host)==e.engine(host) and host.docker.container(item['Id']) is not None

def persist_with(stdout,exit_code=0,oom=False):
    docs,host=docs_for('PERSIST');item=host.docker.container('c3po-k12-20261006-w1');host.docker.stdout[item['Id']]=stdout
    item['State'].update(ExitCode=exit_code,OOMKilled=oom);return docs,host

def padded(size):
    """A complete writer line of exactly `size` bytes (the pad in its checks object)."""
    base=e.writer_line(checks={'pad':''});return e.writer_line(checks={'pad':'a'*(size-len(base))})

def test_persist_keeps_one_complete_receipt_consistent_with_the_exit_code():
    docs,host=persist_with(e.writer_line('REFUSED','MANIFEST_GO_INVALID'),3);receipt=complete(docs,host)
    assert __import__('json').loads(persisted_file(host))['exit_code']==3 and receipt['detail']['writer_line']['terminal'] is None
    docs,host=persist_with(e.writer_line(**e.EMPTY_LIST),3);receipt=complete(docs,host);assert receipt['detail']['writer_line']['terminal']=='EMPTY_LIST'
    docs,host=persist_with(e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'),1);complete(docs,host)
    docs,host=persist_with(e.writer_line('UNVERIFIED','MANIFEST_X_Y'),1);complete(docs,host)
    docs,host=persist_with(padded(16384),0);receipt=complete(docs,host);assert receipt['detail']['writer_line']['stdout_bytes']==16384

@pytest.mark.parametrize('stdout,exit_code,code',[(b'',0,'WRITER_LINE_NOT_ONE_LINE'),(b'',143,'WRITER_LINE_NOT_ONE_LINE'),
    (e.writer_line()[:-1],0,'WRITER_LINE_NOT_ONE_LINE'),(e.writer_line()[:200],0,'WRITER_LINE_NOT_ONE_LINE'),
    (e.writer_line()+e.writer_line(),0,'WRITER_LINE_NOT_ONE_LINE'),(e.writer_line()+b'x',0,'WRITER_LINE_NOT_ONE_LINE'),
    (b'\n'+e.writer_line(),0,'WRITER_LINE_NOT_ONE_LINE'),(e.writer_line()[:200]+b'\n',0,'WRITER_LINE_INVALID'),(b'Traceback\n',1,'WRITER_LINE_INVALID'),
    (e.writer_line().replace(b'"status"',b'"\xc3\xa9tatus"'),0,'WRITER_LINE_NOT_ASCII'),(e.writer_line(day='2026-10-07'),0,'WRITER_LINE_INVALID'),
    (e.writer_line(),1,'WRITER_RECEIPT_INCONSISTENT'),(e.writer_line(),3,'WRITER_RECEIPT_INCONSISTENT'),
    (e.writer_line('REFUSED','MANIFEST_X_Y'),0,'WRITER_RECEIPT_INCONSISTENT'),(e.writer_line('UNVERIFIED','MANIFEST_X_Y'),3,'WRITER_RECEIPT_INCONSISTENT'),
    (e.writer_line(mode='VERIFY_ONLY'),0,'WRITER_RECEIPT_INCONSISTENT'),(e.writer_line(mode='PREFLIGHT'),0,'WRITER_RECEIPT_INCONSISTENT'),
    (e.writer_line(mode=None),0,'WRITER_RECEIPT_INCONSISTENT'),(e.writer_line(session=None),0,'WRITER_RECEIPT_INCONSISTENT'),
    (e.writer_line('REFUSED','MANIFEST_ARGUMENTS_INVALID',session=None,mode=None),3,'WRITER_RECEIPT_INCONSISTENT')])
def test_persist_refuses_anything_but_one_complete_consistent_receipt(stdout,exit_code,code):
    """Codex 2: truncated, duplicated or inconsistent output is never persisted; nothing is written, and the run is a
    refusal (docker logs only reads)."""
    docs,host=persist_with(stdout,exit_code);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED',code),(receipt['code'],receipt.get('detail'))
    assert host.tree.get(e.RECEIPTS).children=={} and receipt['detail']['writer_line']['valid'] is False
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    assert e.MANIFEST_SHA not in str(receipt) and 'public' not in receipt['detail']['writer_line']

def test_persist_requires_a_known_exit():
    docs,host=persist_with(e.writer_line(),0,oom=True);refused(docs,host,'CONTAINER_EXIT_NOT_KNOWN')
    docs,host=persist_with(e.writer_line(),256);refused(docs,host,'CONTAINER_EXIT_NOT_KNOWN')
    docs,host=persist_with(e.writer_line(),-1);refused(docs,host,'CONTAINER_EXIT_NOT_KNOWN')
    docs,host=persist_with(e.writer_line(),0);host.docker.container('c3po-k12-20261006-w1')['State']['StartedAt']=e.NEVER
    refused(docs,host,'CONTAINER_EXIT_NOT_KNOWN')
    docs,host=persist_with(e.writer_line('REFUSED','MANIFEST_X_Y'),255);refused(docs,host,'WRITER_RECEIPT_INCONSISTENT')

@pytest.mark.parametrize('action,code',[
    (lambda host:host.tree.add(e.RECEIPTS+'/k12-2026-10-06-w1.writer.json',kind='file',mode=0o600),'PERSISTED_RECEIPT_PRESENT'),
    (lambda host:host.docker.containers.pop(),'CONTAINER_ABSENT'),
    (lambda host:host.docker.containers[-1]['Config']['Labels'].update({'c3po.k12.request_sha256':'6e'*32}),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['Config']['Labels'].update({'c3po.k12.capacity_request_sha256':'6e'*32}),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['Config']['Cmd'].append('--verify-only'),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['Mounts'][3].update(RW=False),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['Mounts'].append({'Type':'bind','Source':'/etc/c3po-bar','Destination':'/x','RW':False}),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1].update(Image=hostemu.OTHER),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1].update(Name='/c3po-k12-20261006-w2'),'CONTAINER_ABSENT'),
    (lambda host:host.docker.containers[-1]['HostConfig'].update(NetworkMode='bridge'),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['HostConfig'].update(ReadonlyRootfs=False),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['HostConfig'].update(AutoRemove=True),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['HostConfig'].update(RestartPolicy={'Name':'always'}),'CONTAINER_NOT_OF_THIS_WINDOW'),
    (lambda host:host.docker.containers[-1]['State'].update(Status='running',Running=True),'CONTAINER_NOT_EXITED'),
    (lambda host:host.docker.containers[-1]['State'].update(Running=True),'CONTAINER_NOT_EXITED'),
    (lambda host:host.docker.containers[-1]['State'].update(Status='created',StartedAt=e.NEVER),'CONTAINER_NEVER_STARTED'),
    (lambda host:host.docker.containers[-1]['State'].update(Status='paused'),'CONTAINER_NOT_EXITED'),
    (lambda host:setattr(host.docker,'inspect_returncode',1),'CONTAINER_ABSENT'),
    (lambda host:change(host,e.RECEIPTS,mode=0o755),'PARENT_IDENTITY_MISMATCH')])
def test_persist_prechecks(action,code):
    docs,host=docs_for('PERSIST');action(host);refused(docs,host,code)

def test_persist_clock_and_budget():
    docs,host=docs_for('PERSIST',now=e.utc(e.DAY,'10:45:59'));refused(docs,host,'PERSIST_BEFORE_THE_VIEW_AND_A_MINUTE')
    docs,host=docs_for('PERSIST',now=e.utc(e.DAY,'10:46:00'));complete(docs,host)
    docs,host=docs_for('PERSIST',now='2026-10-07T10:46:30+00:00');refused(docs,host,'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
    docs,host=docs_for('PERSIST');budget=f.Budget(docs.now).attach(host);budget.cost(36.5,'container','inspect')
    refused(docs,host,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',**budget.options())
    docs,host=docs_for('PERSIST');budget=f.Budget(docs.now).attach(host);budget.cost(36,'container','inspect')
    assert docs.run(host,**budget.options())['detail']['seconds_left_before_first_effect']==24

def test_persist_effect_failures():
    docs,host=docs_for('PERSIST');host.docker.logs_returncode=1;refused(docs,host,'LOGS_FAILED')
    docs,host=docs_for('PERSIST');host.absent={('logs',)};refused(docs,host,'COMMAND_NOT_STARTED')
    docs,host=docs_for('PERSIST');host.hang={('logs',)};receipt=partial(docs,host,'LOGS_UNCERTAIN');assert receipt['objects_left_by_this_run']==0
    docs,host=docs_for('PERSIST');item=host.docker.container('c3po-k12-20261006-w1');host.docker.stdout[item['Id']]=b'x'*16385
    refused(docs,host,'STDOUT_TOO_LARGE')
    docs,host=persist_with(padded(16385));refused(docs,host,'STDOUT_TOO_LARGE')
    docs,host=docs_for('PERSIST');host.readonly=True;refused(docs,host,'FILESYSTEM_READ_ONLY')

def test_persist_refuses_a_container_that_changed_while_its_output_was_read():
    for mutation in (lambda item:item['State'].update(FinishedAt='2026-10-06T10:50:00Z'),lambda item:item['State'].update(ExitCode=9),
                     lambda item:item['State'].update(Status='running')):
        docs,host=docs_for('PERSIST');item=host.docker.container('c3po-k12-20261006-w1');original=host.docker.do_logs
        def logs(arguments,mutation=mutation,item=item):
            out=original(arguments);mutation(item);return out
        host.docker.do_logs=logs;receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','CONTAINER_CHANGED_DURING_PERSIST')
        assert host.tree.get(e.RECEIPTS).children=={} and receipt['mutating_calls']['failed_nothing_changed']==1
    docs,host=docs_for('PERSIST');item=host.docker.container('c3po-k12-20261006-w1');original=host.docker.do_logs
    def logs(arguments):
        out=original(arguments);host.docker.containers.remove(item);return out
    host.docker.do_logs=logs;receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','CONTAINER_CHANGED_DURING_PERSIST')


# ---------------------------------------------------------------- STOP
def test_stop_stops_the_parked_container_before_its_view():
    docs,host=docs_for('STOP');receipt=complete(docs,host);item=host.docker.container('c3po-k12-20261006-w1')
    assert item['State']['Status']=='exited' and [entry['argv'][1:] for entry in host.commands if entry['argv'][1]=='stop']==[['stop','-t','5',item['Id']]]
    assert receipt['detail']['manifest_names_before']==receipt['detail']['manifest_names_after']=={'manifest_present':False,'temporaries':0}
    assert host.tree.get(e.MANIFESTS).children=={} and receipt['mutating_calls']=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0}

def test_stop_prechecks_and_clock():
    docs,host=docs_for('STOP');item=host.docker.container('c3po-k12-20261006-w1');host.docker.exit(item,3,b'');refused(docs,host,'CONTAINER_NOT_RUNNING')
    docs,host=docs_for('STOP');host.docker.containers[-1]['State'].update(Running=False);refused(docs,host,'CONTAINER_NOT_RUNNING')
    docs,host=docs_for('STOP');host.docker.containers[-1]['Config']['Labels']['c3po.k12.request_sha256']='1'*64;refused(docs,host,'CONTAINER_NOT_OF_THIS_WINDOW')
    docs,host=docs_for('STOP',now=e.utc(e.DAY,'10:44:36'));refused(docs,host,'TOO_CLOSE_TO_THE_VIEW');assert host.commands==[]
    docs,host=docs_for('STOP',now=e.utc(e.DAY,'10:44:35'));complete(docs,host)
    docs,host=docs_for('STOP',now=e.utc(e.DAY,'10:37:00'));refused(docs,host,'RUN_BEFORE_THE_WINDOW_START')
    docs,host=docs_for('STOP',now=e.utc(e.DAY,'10:43:00'));budget=f.Budget(docs.now).attach(host);budget.cost(36,'container','inspect')
    refused(docs,host,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',**budget.options())
    docs,host=docs_for('STOP',now=e.utc(e.DAY,'10:44:30'));budget=f.Budget(docs.now).attach(host);budget.cost(6,'container','inspect')
    refused(docs,host,'TOO_CLOSE_TO_THE_VIEW',**budget.options())

def test_stop_effects():
    docs,host=docs_for('STOP');host.docker.stop_returncode=1;host.docker.stop_effect=False;refused(docs,host,'STOP_FAILED')
    docs,host=docs_for('STOP');host.docker.stop_returncode=1;partial(docs,host,'STOP_RETURNED_NONZERO')
    docs,host=docs_for('STOP');host.hang={('stop','-t')};partial(docs,host,'STOP_UNCERTAIN')
    docs,host=docs_for('STOP');host.absent={('stop','-t')};refused(docs,host,'COMMAND_NOT_STARTED')
    docs,host=docs_for('STOP');original=host.docker.do_stop
    def published(arguments):
        out=original(arguments);host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600,content=b'{}');return out
    host.docker.do_stop=published;partial(docs,host,'MANIFEST_DIRECTORY_CHANGED_DURING_STOP')
    docs,host=docs_for('STOP');original=host.docker.do_stop
    def temporary(arguments):
        out=original(arguments);host.tree.add(e.MANIFESTS+'/.2026-10-06.json.%s.tmp'%('cd'*8),kind='file',mode=0o600);return out
    host.docker.do_stop=temporary;partial(docs,host,'MANIFEST_DIRECTORY_CHANGED_DURING_STOP')
    docs,host=docs_for('STOP');original=host.docker.do_stop
    def gone(arguments):
        out=original(arguments);host.docker.containers.pop();return out
    host.docker.do_stop=gone;partial(docs,host,'STOPPED_CONTAINER_NOT_READ_BACK')

def test_stop_and_remove_readbacks_that_fail_with_an_error_of_the_host():
    docs,host=docs_for('STOP');seen=[0]
    def hook(host,name,detail,calls):
        if name=='names':
            seen[0]+=1
            if seen[0]==2:raise OSError(5,'injected')
    host.hook=hook;partial(docs,host,'READBACK_UNAVAILABLE')
    docs,host=docs_for('REMOVE')
    def ps(host,name,detail,calls):
        if name=='run' and detail[0][1:3]==['ps','-a'] and any(entry['argv'][1:2]==['rm'] for entry in host.commands):raise RuntimeError('injected')
    host.hook=ps;receipt=partial(docs,host,'READBACK_UNAVAILABLE');assert receipt['mutating_calls']['uncertain']==1

def test_stop_counts_only_the_days_manifest_and_temporaries():
    docs,host=docs_for('STOP')
    for name in ('2026-10-05.json','.2026-10-05.json.%s.tmp'%('ab'*8),'.2026-10-06.json.short.tmp','2026-10-06.json.bak'):host.tree.add(e.MANIFESTS+'/'+name,kind='file',mode=0o600)
    host.tree.add(e.MANIFESTS+'/.2026-10-06.json.%s.tmp'%('ab'*8),kind='file',mode=0o600)
    docs.plan['parent_rows']=e.chains(host,['manifests']);docs.chain();receipt=complete(docs,host)
    assert receipt['detail']['manifest_names_before']=={'manifest_present':False,'temporaries':1}
    host2=docs_for('STOP')[1];host2.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600)
    docs2=f.Docs(K,k12w.fields(host2,'STOP'),now=e.at(k12w.MOMENTS['STOP']));receipt=complete(docs2,host2)
    assert receipt['detail']['manifest_names_before']=={'manifest_present':True,'temporaries':0}


# ---------------------------------------------------------------- REMOVE
def test_remove_removes_exactly_the_named_containers_without_force():
    docs,host=docs_for('REMOVE');other=hostemu.container('c3po-k12-20261008-w1',e.IMAGE,e.IMAGE,[],running=False);host.docker.containers.append(other)
    names=[item['Name'] for item in host.docker.containers];receipt=complete(docs,host)
    removed=[entry['argv'][1:] for entry in host.commands if entry['argv'][1]=='rm']
    assert removed==[['rm']+[item['container_id'] for item in docs.plan['removals']]]
    assert sorted(item['Name'] for item in host.docker.containers)==sorted(name for name in names if not name.startswith('/c3po-k12-2026100'+'6') and name not in
                                                                          ('/c3po-k12-20261007-w1','/c3po-k12-20261007-w2'))
    assert receipt['detail']['family_containers_not_named']==['c3po-k12-20261008-w1'] and receipt['detail']['removed']==3

def test_remove_prechecks():
    for action,code in ((lambda host,items:host.docker.containers.remove(host.docker.container(items[0]['container_id'])),'CONTAINER_ABSENT'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['State'].update(Status='running',Running=True),'CONTAINER_NOT_STOPPED'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['State'].update(Running=True),'CONTAINER_NOT_STOPPED'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['State'].update(Status='paused'),'CONTAINER_NOT_STOPPED'),
                        (lambda host,items:host.docker.container(items[2]['container_id'])['State'].update(StartedAt='2026-10-07T11:40:00Z'),'CONTAINER_NOT_STOPPED'),
                        (lambda host,items:host.tree.remove(e.RECEIPTS+'/k12-2026-10-06-w1.writer.json'),'PERSISTED_RECEIPT_MISSING'),
                        (lambda host,items:change(host,e.RECEIPTS+'/k12-2026-10-06-w1.writer.json',mode=0o640),'PERSISTED_RECEIPT_NOT_PRIVATE'),
                        (lambda host,items:change(host,e.RECEIPTS+'/k12-2026-10-06-w1.writer.json',content=bytearray(b'{}')),'PERSISTED_RECEIPT_INVALID'),
                        # rev 2: an exited container without a receipt is removed only when it shows D4's stop before its view
                        (lambda host,items:host.docker.container(items[1]['container_id'])['State'].update(ExitCode=1),'PERSISTED_RECEIPT_MISSING'),
                        (lambda host,items:host.docker.container(items[1]['container_id'])['State'].update(OOMKilled=True),'PERSISTED_RECEIPT_MISSING'),
                        (lambda host,items:host.docker.container(items[1]['container_id'])['State'].update(FinishedAt='2026-10-07T10:45:00Z'),'PERSISTED_RECEIPT_MISSING'),
                        (lambda host,items:host.tree.add(e.RECEIPTS+'/k12-2026-10-07-w1.writer.json',kind='file',mode=0o600,content=b'{}'),'PERSISTED_RECEIPT_INVALID'),
                        (lambda host,items:host.tree.add(e.RECEIPTS+'/k12-2026-10-07-w1.writer.json',kind='file',mode=0o644,content=b'{}'),'PERSISTED_RECEIPT_NOT_PRIVATE'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['Config']['Labels'].update({'c3po.k12.request_sha256':'1'*64}),'CONTAINER_NOT_OF_THIS_FAMILY'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['Config']['Labels'].update({'c3po.k12.capacity_request_sha256':'1'*64}),'CONTAINER_NOT_OF_THIS_FAMILY'),
                        (lambda host,items:host.docker.container(items[0]['container_id']).update(Name='/c3po-k12-20261006-w2'),'CONTAINER_NOT_OF_THIS_FAMILY'),
                        (lambda host,items:host.docker.container(items[0]['container_id']).update(Image=hostemu.OTHER),'CONTAINER_NOT_OF_THIS_FAMILY'),
                        (lambda host,items:host.docker.container(items[0]['container_id'])['HostConfig'].update(AutoRemove=True),'CONTAINER_NOT_OF_THIS_FAMILY')):
        docs,host=docs_for('REMOVE');action(host,docs.plan['removals']);refused(docs,host,code)
    docs,host=docs_for('REMOVE');items=docs.plan['removals']
    e.persisted(host,K,host.docker.container(items[1]['container_id']),'2026-10-07',1,launch_sha='1'*64);refused(docs,host,'PERSISTED_RECEIPT_INVALID')
    docs,host=docs_for('REMOVE');items=docs.plan['removals']
    e.persisted(host,K,host.docker.container(items[1]['container_id']),'2026-10-07',1,container_id='ab'*32);refused(docs,host,'PERSISTED_RECEIPT_INVALID')

def test_remove_a_stopped_contingency_is_judged_at_its_own_view():
    host,items=k12w.remove_world(K)
    host.docker.stop_finished='2026-10-08T11:41:30.000000000Z';item=e.launched(host,K,'2026-10-08',2);host.docker.do_stop(['-t','5',item['Id']])
    items=items+[k12w.removal(item,'2026-10-08',2)];docs=f.Docs(K,k12w.fields(host,'REMOVE',removals=items),now=e.at(k12w.MOMENTS['REMOVE']))
    receipt=complete(docs,host);assert receipt['detail']['removed']==4
    host,items=k12w.remove_world(K)
    host.docker.stop_finished='2026-10-08T11:46:30.000000000Z';item=e.launched(host,K,'2026-10-08',2);host.docker.do_stop(['-t','5',item['Id']])
    items=items+[k12w.removal(item,'2026-10-08',2)];docs=f.Docs(K,k12w.fields(host,'REMOVE',removals=items),now=e.at(k12w.MOMENTS['REMOVE']))
    refused(docs,host,'PERSISTED_RECEIPT_MISSING')

RELEASE_FILE=e.RELEASE+'/release.CERTIFIED.json'
@pytest.mark.parametrize('action,code',[(lambda host:host.tree.remove(RELEASE_FILE),'RELEASE_ABSENT'),
    (lambda host:change(host,RELEASE_FILE,mode=0o644),'RELEASE_NOT_PRIVATE'),(lambda host:change(host,RELEASE_FILE,uid=1000),'RELEASE_NOT_PRIVATE'),
    (lambda host:change(host,RELEASE_FILE,content=bytearray(b'{}')),'RELEASE_NOT_THE_SIGNED_BYTES'),
    (lambda host:change(host,RELEASE_FILE,content=bytearray(b'x'*1048577)),'FILE_TOO_LARGE'),
    (lambda host:(host.tree.remove(RELEASE_FILE),host.tree.add(RELEASE_FILE,kind='symlink')),'PRECHECK_OS_ERROR')])
def test_launch_hashes_the_release_before_the_create(action,code):
    docs,host=docs_for();action(host);refused(docs,host,code);assert host.docker.created==[]

def test_launch_hashes_the_release_again_after_the_start():
    docs,host=docs_for();original=host.docker.do_start
    def start(arguments):
        out=original(arguments);change(host,RELEASE_FILE,content=bytearray(b'{"changed":1}'));return out
    host.docker.do_start=start;receipt=partial(docs,host,'RELEASE_CHANGED_DURING_LAUNCH');assert receipt['mutating_calls']['uncertain']==0
    docs,host=docs_for();original2=host.docker.do_start
    def gone(arguments):
        out=original2(arguments);host.tree.remove(RELEASE_FILE);return out
    host.docker.do_start=gone;partial(docs,host,'RELEASE_CHANGED_DURING_LAUNCH')

def test_launch_reads_nothing_else_of_the_data_volume():
    docs,host=docs_for();complete(docs,host)
    assert not [entry for entry in host.log if 'provider=synthetic' in str(entry) or 'lost+found' in str(entry) or '.r2d2-v2-pinned' in str(entry)]

def test_remove_command_keeps_the_plan_order():
    host,items=k12w.remove_world(K)
    for order in (items,list(reversed(items)),[items[1],items[0],items[2]],[items[2],items[0],items[1]]):
        docs=f.Docs(K,k12w.fields(host,'REMOVE',removals=order),now=e.at(k12w.MOMENTS['REMOVE']))
        assert docs.go['effects']['command']==['rm']+[item['container_id'] for item in order]

def test_remove_only_on_friday_evening():
    for now,code in (('2026-10-09T19:59:59+00:00','REMOVE_OUTSIDE_FRIDAY_EVENING'),('2026-10-08T20:40:00+00:00','REMOVE_OUTSIDE_FRIDAY_EVENING'),
                     ('2026-10-10T00:40:00+00:00','REMOVE_OUTSIDE_FRIDAY_EVENING'),('2026-10-09T20:00:00+00:00',None)):
        docs,host=docs_for('REMOVE',now=now)
        if code is None:complete(docs,host)
        else:refused(docs,host,code)

def test_remove_effects():
    docs,host=docs_for('REMOVE');host.docker.rm_fail={docs.plan['removals'][1]['container_id']};receipt=partial(docs,host,'REMOVE_INCOMPLETE')
    assert (receipt['detail']['removed'],receipt['detail']['left'])==(2,1)
    docs,host=docs_for('REMOVE');host.docker.rm_fail={item['container_id'] for item in docs.plan['removals']};refused(docs,host,'REMOVE_INCOMPLETE')
    docs,host=docs_for('REMOVE');host.docker.rm_returncode=1;partial(docs,host,'REMOVE_RETURNED_NONZERO')
    docs,host=docs_for('REMOVE');host.hang_after={('rm',)};receipt=partial(docs,host,'REMOVE_UNCERTAIN');assert receipt['detail']['removed']==3
    docs,host=docs_for('REMOVE');host.absent={('rm',)};refused(docs,host,'COMMAND_NOT_STARTED')
    docs,host=docs_for('REMOVE');host.docker.ps_returncode=0;original=host.docker.do_rm
    def broken(arguments):
        out=original(arguments);host.docker.ps_returncode=1;return out
    host.docker.do_rm=broken;receipt=partial(docs,host,'COMMAND_FAILED');assert receipt['mutating_calls']['uncertain']==1
    docs,host=docs_for('REMOVE');budget=f.Budget(docs.now).attach(host);budget.cost(44.5,'ps','-a')
    refused(docs,host,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',**budget.options())


# ---------------------------------------------------------------- the fixed words
def test_command_rows_are_the_signed_table():
    rows=M.COMMANDS
    assert rows['create']['argv']==['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no']
    assert (rows['create']['class'],rows['create']['kind'])==('QUICK','EFFECT') and (rows['start']['argv'],rows['start']['class'])==(['start'],'RUN_SHORT')
    assert (rows['stop']['argv'],rows['stop']['class'])==(['stop','-t','5'],'RUN_SHORT') and (rows['logs']['argv'],rows['logs']['class'])==(['logs'],'QUICK')
    assert (rows['remove']['argv'],rows['remove']['class'])==(['rm'],'QUICK') and rows['inspect']['argv'][:3]==['container','inspect','--format']
    assert 'Env' not in rows['inspect']['argv'][3] and set(rows)=={'image','container_list','inspect','create','start','stop','logs','remove'}
    assert all(row['stdin'] is False and row['tail']==[] for row in rows.values())
    assert M.effects_budget('create','start')==32 and M.effects_budget('logs')==12 and M.effects_budget('stop')==24 and M.effects_budget('remove')==12
