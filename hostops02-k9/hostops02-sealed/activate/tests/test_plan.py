"""Every refusal of K6a that can be decided from the signed bytes alone. Each is an AUTHENTICATION refusal: the
dispatcher meets it locally before any claim, and on the host nothing is touched (the run is given a host that fails
on any use). One case per code and per way of reaching it."""
import copy
from datetime import datetime,timedelta

import pytest

import family as f
import hostemu
import k6a

def change(path,value):
    def apply(plan,host):
        target=plan
        for key in path[:-1]:target=target[key]
        if value is ...:del target[path[-1]]
        else:target[path[-1]]=value
    return apply
def policy(**changes):
    def apply(plan,host):plan['policy']=k6a.policy_member(k6a.policy_bytes(**changes))
    return apply
def raw_policy(raw):
    def apply(plan,host):plan['policy']=k6a.policy_member(raw)
    return apply
def rows_of(path_key,path):
    def apply(plan,host):
        target=plan
        for key in path_key[:-1]:target=target[key]
        target[path_key[-1]]=hostemu.rows(host,path)
    return apply
def row(path_key,index,**members):
    def apply(plan,host):
        target=plan
        for key in path_key:target=target[key]
        target[index].update(members)
    return apply
def both(*steps):
    def apply(plan,host):
        for step in steps:step(plan,host)
    return apply
def with_release_in(parent):
    def apply(plan,host):plan['release']['parent']=hostemu.rows(host,parent)
    return apply
LONG='/'+'a'*190
def synthetic(path):
    """Rows of a path as a root-owned chain, whatever the host says (the checks from the bytes are pure)."""
    def apply(host):return [dict(item,uid=0,gid=0,mode=0o755) for item in hostemu.rows(host,path)]
    return apply
def rows_from(path_key,maker):
    def apply(plan,host):
        target=plan
        for key in path_key[:-1]:target=target[key]
        target[path_key[-1]]=maker(host)
    return apply
def long_parent(length):
    """The live directory in a parent whose path is long: what decides is the length of the paths below it."""
    def apply(plan,host):
        path=hostemu.DATA+'/'+'p'*length;host.tree.add(path,dev=hostemu.DATA_DEVICE);plan['live_parent']=hostemu.rows(host,path)
    return apply
def below_live(plan,host):
    plan['release']['parent']=hostemu.rows(host,k6a.LIVE_PARENT)+[{'path':k6a.LIVE,'device':hostemu.DATA_DEVICE,'inode':12345,'uid':0,'gid':0,'mode':0o700}]

CASES=[
    # the data root and the evidence
    ('data root null',change(['data_root'],None),'PATH_INVALID'),('data root is /',change(['data_root'],'/'),'PATH_INVALID'),
    ('data root relative',change(['data_root'],'mnt/day-d-data'),'PATH_INVALID'),('data root with ..',change(['data_root'],'/mnt/../mnt/day-d-data'),'PATH_INVALID'),
    ('data root with a trailing slash',change(['data_root'],hostemu.DATA+'/'),'PATH_INVALID'),
    ('boot unbound',change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),('boot zero',change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
    # the parent the directory is created in
    ('live parent null',change(['live_parent'],None),'CHAIN_ROW_INVALID'),('live parent empty',change(['live_parent'],[]),'CHAIN_ROW_INVALID'),
    ('live parent row without a member',change(['live_parent',1,'inode'],...),'CHAIN_ROW_INVALID'),('live parent row with a boolean',change(['live_parent',1,'uid'],False),'CHAIN_ROW_INVALID'),
    ('live parent a mapping',change(['live_parent'],{'path':'/mnt'}),'CHAIN_ROW_INVALID'),('live parent rows that are not objects',change(['live_parent'],[1,2]),'CHAIN_ROW_INVALID'),
    ('live parent lacks a component',lambda plan,host:plan['live_parent'].pop(1),'CHAIN_ROW_INVALID'),
    ('a component above the data root is not root-owned',row(['live_parent'],1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('a component above the data root is group-writable',row(['live_parent'],1,mode=0o775),'CHAIN_ROW_UNSAFE'),
    ('live parent world-writable without the sticky bit',row(['live_parent'],-1,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
    ('live parent setgid',row(['live_parent'],-1,mode=0o2755),'PARENT_SETGID'),
    ('live parent outside the data root',rows_of(['live_parent'],'/etc'),'LIVE_PARENT_OUTSIDE_DATA_ROOT'),
    ('live path longer than a clean path',both(long_parent(150),change(['directory_name'],'d'*40)),'DIRECTORY_NAME_INVALID'),
    ('policy path longer than a clean path',both(long_parent(150),change(['directory_name'],'d'*25),change(['override_name'],'o.json')),'FILE_PATH_INVALID'),
    ('override path longer than a clean path',both(long_parent(150),change(['directory_name'],'d'*25),lambda plan,host:plan.__setitem__('policy',k6a.policy_member(name='p.json'))),'FILE_PATH_INVALID'),
    ('directory name null',change(['directory_name'],None),'DIRECTORY_NAME_INVALID'),('directory name with a slash',change(['directory_name'],'a/b'),'DIRECTORY_NAME_INVALID'),
    ('directory name ..',change(['directory_name'],'..'),'DIRECTORY_NAME_INVALID'),('directory name hidden',change(['directory_name'],'.hidden'),'DIRECTORY_NAME_INVALID'),
    # the release an earlier operation installed
    ('release null',change(['release'],None),'RELEASE_REQUEST_INVALID'),('release lacks a member',change(['release','bytes'],...),'RELEASE_REQUEST_INVALID'),
    ('release with one more member',change(['release','mode'],0o600),'RELEASE_REQUEST_INVALID'),('release hash zero',change(['release','sha256'],'0'*64),'RELEASE_REQUEST_INVALID'),
    ('release hash upper case',change(['release','sha256'],'A'*64),'RELEASE_REQUEST_INVALID'),('release empty',change(['release','bytes'],0),'RELEASE_REQUEST_INVALID'),
    ('release larger than the worker accepts',change(['release','bytes'],65537),'RELEASE_REQUEST_INVALID'),('release size a boolean',change(['release','bytes'],True),'RELEASE_REQUEST_INVALID'),
    ('release directory name a path',change(['release','directory_name'],'a/b'),'RELEASE_REQUEST_INVALID'),('release file name hidden',change(['release','file_name'],'.release'),'RELEASE_REQUEST_INVALID'),
    ('release parent null',change(['release','parent'],None),'CHAIN_ROW_INVALID'),
    ('release parent with a component that is not root-owned',row(['release','parent'],1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('release parent world-writable without the sticky bit',row(['release','parent'],-1,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
    ('release parent lacks a component',lambda plan,host:plan['release']['parent'].pop(1),'CHAIN_ROW_INVALID'),
    ('release outside the data root',with_release_in('/etc'),'RELEASE_OUTSIDE_DATA_ROOT'),
    ('live directory inside the release directory',rows_of(['live_parent'],k6a.RELEASE_DIRECTORY),'PATHS_OVERLAP'),
    ('release directory inside the live directory',below_live,'PATHS_OVERLAP'),
    ('release directory is the live directory',both(with_release_in(k6a.LIVE_PARENT),change(['release','directory_name'],k6a.LEAF)),'PATHS_OVERLAP'),
    # the live policy: its bytes
    ('policy null',change(['policy'],None),'POLICY_REQUEST_INVALID'),('policy lacks a member',change(['policy','bytes'],...),'POLICY_REQUEST_INVALID'),
    ('policy with a mode member',change(['policy','mode'],0o644),'POLICY_REQUEST_INVALID'),('policy name hidden',change(['policy','name'],'.policy.json'),'POLICY_REQUEST_INVALID'),
    ('policy name a path',change(['policy','name'],'a/policy.json'),'POLICY_REQUEST_INVALID'),('policy name of a leftover',change(['policy','name'],'x'),None),
    ('policy content not text',change(['policy','content_b64'],None),'POLICY_REQUEST_INVALID'),('policy size above the limit',raw_policy(b'{"a":"'+b'x'*16400+b'"}'),'POLICY_REQUEST_INVALID'),
    ('policy size zero',change(['policy','bytes'],0),'POLICY_REQUEST_INVALID'),('policy hash zero',change(['policy','sha256'],'0'*64),'POLICY_REQUEST_INVALID'),
    ('policy hash of other bytes',change(['policy','sha256'],'3'*64),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),('policy size of other bytes',change(['policy','bytes'],7),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),
    ('policy not base64',change(['policy','content_b64'],'not base64!'),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),('policy base64 not ascii',change(['policy','content_b64'],'éééé'),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),
    ('policy base64 with a line break',lambda plan,host:plan['policy'].update(content_b64=plan['policy']['content_b64'][:40]+'\n'+plan['policy']['content_b64'][40:]),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),
    ('policy base64 with a space',lambda plan,host:plan['policy'].update(content_b64=' '+plan['policy']['content_b64']),'POLICY_BYTES_NOT_THE_SIGNED_HASH'),
    ('policy not json',raw_policy(b'not json'),'POLICY_JSON_INVALID'),('policy a list',raw_policy(b'[1]'),'POLICY_JSON_INVALID'),
    ('policy with a duplicate key',raw_policy(b'{"schema":"a","schema":"b"}'),'POLICY_JSON_INVALID'),
    # the live policy: what the controller and the assembler of the release will require
    ('policy schema',policy(schema='R2D2_V2_LIVE_POLICY_V2'),'POLICY_SCHEMA'),('policy mode PROOF',policy(mode='PROOF'),'POLICY_SCHEMA'),('policy mode missing',policy(mode=...),'POLICY_SCHEMA'),
    ('policy of another epoch',policy(epoch='R2D2-V2-SHADOW-2026-09-28'),'POLICY_IDENTITY'),('policy of another release',policy(release_sha='9'*64),'POLICY_IDENTITY'),
    ('policy without a release',policy(release_sha=...),'POLICY_IDENTITY'),
    ('policy of another runtime order',policy(order_sha='1'*64),'POLICY_RUNTIME_ORDER'),('policy of another package',policy(package_sha='2'*64),'POLICY_PACKAGE'),
    ('policy of another revision',policy(code_revision='4de7095ad51bce19ea4b685d5c708d0a72986d76'),'POLICY_REVISION'),('policy without a revision',policy(code_revision=...),'POLICY_REVISION'),
    ('policy capacity zero',policy(capacity=0),'POLICY_CAPACITY'),('policy capacity 551',policy(capacity=551),'POLICY_CAPACITY'),('policy capacity a boolean',policy(capacity=True),'POLICY_CAPACITY'),
    ('policy capacity text',policy(capacity='550'),'POLICY_CAPACITY'),('policy capacity a float',policy(capacity=550.0),'POLICY_CAPACITY'),
    ('policy without the capacity receipt',policy(c8_receipt_sha=...),'POLICY_RECERTIFICATION'),('policy head GO zero',policy(head_go_sha='0'*64),'POLICY_RECERTIFICATION'),
    ('policy head GO short',policy(head_go_sha='d'*63),'POLICY_RECERTIFICATION'),
    ('policy without a start',policy(valid_from=...),'POLICY_WINDOW'),('policy start not an instant',policy(valid_from='monday'),'POLICY_WINDOW'),
    ('policy start without a zone',policy(valid_from='2026-10-05T00:00:00'),'POLICY_WINDOW'),('policy start not UTC',policy(valid_from='2026-10-04T21:00:00-03:00'),'POLICY_WINDOW'),
    ('policy end before its start',policy(valid_until='2026-10-04T00:00:00+00:00'),'POLICY_WINDOW'),('policy end equal to its start',policy(valid_until='2026-10-05T00:00:00+00:00'),'POLICY_WINDOW'),
    ('policy longer than ninety days',policy(valid_until='2027-01-03T00:00:01+00:00'),'POLICY_WINDOW'),
    ('policy starts after the first open',policy(valid_from='2026-10-05T13:30:01+00:00'),'POLICY_NOT_EPOCH_WIDE'),
    ('policy ends before the last close',policy(valid_until='2026-10-09T19:59:59+00:00'),'POLICY_NOT_EPOCH_WIDE'),
    # the override
    ('override name null',change(['override_name'],None),'OVERRIDE_NAME_INVALID'),('override name is the policy name',change(['override_name'],'policy.json'),'OVERRIDE_NAME_INVALID'),
    ('override name of the worker status file',change(['override_name'],'policy.json.status.json'),'OVERRIDE_NAME_INVALID'),
    ('override name a path',change(['override_name'],'a/b.json'),'OVERRIDE_NAME_INVALID'),('override name hidden',change(['override_name'],'.override.json'),'OVERRIDE_NAME_INVALID'),
    # the worker
    ('worker null',change(['worker'],None),'WORKER_REQUEST_INVALID'),('worker image by reference',change(['worker','image_id'],'c3po/backend:production'),'WORKER_REQUEST_INVALID'),
    ('worker with a container member',change(['worker','container'],'c3po-api-1'),'WORKER_REQUEST_INVALID'),('worker mount target /',change(['worker','mount_target'],'/'),'WORKER_REQUEST_INVALID'),
    ('worker mount target relative',change(['worker','mount_target'],'app/day-d-data'),'WORKER_REQUEST_INVALID'),('worker mount target null',change(['worker','mount_target'],None),'WORKER_REQUEST_INVALID'),
    ('a value longer than the template grammar',both(change(['worker','mount_target'],LONG),change(['directory_name'],'d'*100)),'ENVIRONMENT_EXPECTATION'),
    # the compose project: the file list of the deploy and nothing else
    ('compose null',change(['compose'],None),'COMPOSE_REQUEST_INVALID'),('compose with a service member',change(['compose','service'],'api'),'COMPOSE_REQUEST_INVALID'),
    ('compose project upper case',change(['compose','project'],'C3PO'),'COMPOSE_PROJECT'),('compose project null',change(['compose','project'],None),'COMPOSE_PROJECT'),
    ('compose files empty',change(['compose','files'],[]),'COMPOSE_FILES'),('compose files null',change(['compose','files'],None),'COMPOSE_FILES'),
    ('compose environment file relative',change(['compose','env_file'],'.env'),'COMPOSE_FILES'),('compose file repeated',change(['compose','files'],[hostemu.COMPOSE_FILE]*2),'COMPOSE_FILES'),
    ('compose with four files, no room for the override',change(['compose','files'],[hostemu.COMPOSE_FILE,'/a/b.yml','/a/c.yml','/a/d.yml']),'COMPOSE_FILES'),
    ('compose with a second file',change(['compose','files'],[hostemu.COMPOSE_FILE,hostemu.DEPLOY+'/c3po/other.yml']),'COMPOSE_NOT_THE_DEPLOY_LAYOUT'),
    ('compose file of the legacy project',change(['compose','files'],[hostemu.DEPLOY+'/docker-compose.yml']),'COMPOSE_NOT_THE_DEPLOY_LAYOUT'),
    ('compose environment file elsewhere',change(['compose','env_file'],hostemu.DEPLOY+'/c3po/.env'),'COMPOSE_NOT_THE_DEPLOY_LAYOUT'),
    ('compose project that is not the directory of the file',change(['compose','project'],'other'),'COMPOSE_NOT_THE_DEPLOY_LAYOUT'),
    # the deploy tree and the lock
    ('deploy directory null',change(['deploy_directory'],None),'CHAIN_ROW_INVALID'),('deploy directory row without a path',change(['deploy_directory',-1,'path'],...),'CHAIN_ROW_INVALID'),
    ('deploy directory world-writable',row(['deploy_directory'],-1,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
    ('a component above the deploy tree not root-owned',row(['deploy_directory'],1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('deploy tree inside the data root',both(change(['data_root'],'/opt'),rows_of(['live_parent'],'/opt'),with_release_in('/opt')),'PATHS_OVERLAP'),
    ('data root inside the deploy tree',both(change(['data_root'],hostemu.DEPLOY+'/runtime'),rows_from(['live_parent'],synthetic(hostemu.DEPLOY+'/runtime')),
                                             rows_from(['release','parent'],synthetic(hostemu.DEPLOY+'/runtime'))),'PATHS_OVERLAP'),
    ('lock null',change(['lock'],None),'LOCK_REQUEST_INVALID'),('lock with a name member',change(['lock','name'],'deployment.lock'),'LOCK_REQUEST_INVALID'),
    ('lock wait above twenty seconds',change(['lock','wait_seconds'],21),'LOCK_REQUEST_INVALID'),('lock wait negative',change(['lock','wait_seconds'],-1),'LOCK_REQUEST_INVALID'),
    ('lock wait a boolean',change(['lock','wait_seconds'],True),'LOCK_REQUEST_INVALID'),('lock wait a float',change(['lock','wait_seconds'],20.0),'LOCK_REQUEST_INVALID'),
    ('lock directory null',change(['lock','directory'],None),'CHAIN_ROW_INVALID'),
    ('lock in another directory of the deploy tree',rows_of(['lock','directory'],hostemu.DEPLOY+'/runtime'),'LOCK_NOT_THE_DEPLOYMENT_LOCK'),
    ('lock outside the deploy tree',rows_of(['lock','directory'],'/etc'),'LOCK_NOT_THE_DEPLOYMENT_LOCK'),
    ('lock directory world-writable',row(['lock','directory'],-1,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
]
CASES=[case for case in CASES if case[2] is not None]

@pytest.mark.parametrize('label,apply,code',CASES,ids=[case[0] for case in CASES])
def test_plan_refusals_are_authentication_refusals_and_nothing_is_touched(label,apply,code):
    m,docs,host=k6a.fresh();apply(docs.plan,host);docs.chain()
    assert f.refusal(docs.authenticate)==code,label
    receipt=docs.run(f.Untouchable())
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,'AUTHENTICATION')
    assert receipt['mutating_calls']['issued']==0 and f.sealed(receipt)

def test_the_whole_window_of_the_run_must_lie_inside_the_window_of_the_policy():
    """The controller refuses a policy outside its window at every step, so a GO that opens before the policy does is
    refused from the bytes. (A policy that ends before the GO does cannot be epoch-wide: that end is POLICY_NOT_EPOCH_WIDE.)"""
    early=datetime.fromisoformat('2026-10-05T08:45:00+00:00')
    m,docs,host=k6a.fresh(early);assert docs.run(host)['status']==m.COMPLETE_STATUS,'05:45 BRT with a policy valid from 00:00 UTC'
    for start,refused in (('2026-10-05T08:45:00+00:00',False),('2026-10-05T08:45:00.000001+00:00',True),('2026-10-05T08:47:00+00:00',True),('2026-10-05T13:30:00+00:00',True)):
        m,docs,host=k6a.fresh(early);docs.plan['policy']=k6a.policy_member(k6a.policy_bytes(valid_from=start));docs.chain()
        if refused:
            assert f.refusal(docs.authenticate)=='POLICY_WINDOW_DOES_NOT_COVER_THE_GO',start
            assert docs.run(f.Untouchable())['code']=='POLICY_WINDOW_DOES_NOT_COVER_THE_GO'
        else:assert docs.run(host)['status']==m.COMPLETE_STATUS,start

def test_policy_that_is_not_in_canonical_bytes_is_delivered_as_signed_and_its_digest_is_shown():
    """The file pin is the hash of the bytes; Act B pins the digest of the canonical form. The signers see both."""
    import json
    loose=json.dumps(k6a.policy_object(),indent=1).encode()+b'\n';assert loose!=k6a.POLICY
    m,docs,host=k6a.fresh();docs.plan['policy']=k6a.policy_member(loose);docs.chain();effects=docs.go['effects']
    assert effects['files'][0]['sha256']==f.sha(loose) and effects['policy']['content_digest_sha256']==f.sha(k6a.POLICY)!=f.sha(loose)
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(k6a.LIVE+'/policy.json').content)==loose
    assert effects['recreate']['environment']['C3PO_R2D2_V2_LIVE_POLICY_SHA']==f.sha(loose)

def test_request_must_name_a_receipt_of_the_epoch_readback_and_no_other_operation_name_stands_in_for_it():
    """The rows and the boot this run trusts come from K11 (its dry run of the same boot): the request must cite one
    of its receipts. A precheck of the earlier family, a host-facts read, a write receipt or any other name does not
    satisfy the code; they may be cited besides."""
    K11='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
    m,docs,host=k6a.fresh();assert m.EVIDENCE_REQUIRED is True and m.EVIDENCE_OPERATIONS==(K11,)
    assert [item['operation'] for item in docs.request['evidence']]==[K11]
    docs.request['evidence']=[];docs.chain();assert f.refusal(docs.authenticate)=='EVIDENCE_UNBOUND' and docs.run(f.Untouchable())['code']=='EVIDENCE_UNBOUND'
    for name in ('GO_READONLY_HOSTOPS_PRECHECK_01','GO_READONLY_SUPERVISOR_HOSTFACTS_01','GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01','ANYTHING',K11[:-1],K11+'X','GO_WRITE'+K11[len('GO_READONLY'):]):
        docs.request['evidence']=[{'role':'ROWS','operation':name,'receipt_sha256':'b'*64}];docs.chain()
        assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING',name
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','EVIDENCE_OPERATION_MISSING','AUTHENTICATION')
    docs.request['evidence']=[{'role':'W1','operation':'GO_READONLY_HOSTOPS_PRECHECK_01','receipt_sha256':'c'*64},{'role':'ROWS','operation':K11,'receipt_sha256':'b'*64}];docs.chain()
    assert docs.run(host)['status']==m.COMPLETE_STATUS,'other receipts may be cited besides'

def test_policy_digest_is_the_one_the_assembler_of_the_release_computes_also_for_text_that_is_not_ascii():
    """Act B pins digest(policy) of r2d2_v2_epoch_assembler.py: sorted keys, compact separators, ensure_ascii=False.
    For an ASCII policy that is the digest of the family's canonical form; for any other it is not, and the figure
    the signers compare in binding step 5 must be the assembler's."""
    import hashlib,json
    def assembler(policy):return hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    m,docs,host=k6a.fresh();assert docs.go['effects']['policy']['content_digest_sha256']==assembler(k6a.policy_object())==f.sha(f.canonical(k6a.policy_object()))
    for note in ('caf\u00e9','\u65e5\u672c','\U0001f600'):
        policy=k6a.policy_object(note=note)
        for raw in (f.canonical(policy),json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')):      # escaped, and as itself
            m,docs,host=k6a.fresh();docs.plan['policy']=k6a.policy_member(raw);docs.chain();digest=docs.go['effects']['policy']['content_digest_sha256']
            assert digest==assembler(policy)==m.policy_digest(policy) and digest!=f.sha(f.canonical(policy)),note.encode('unicode_escape')
            assert docs.run(host)['status']==m.COMPLETE_STATUS and bytes(host.tree.get(k6a.LIVE+'/policy.json').content)==raw
    # a text that cannot be encoded: no digest exists, so the request is refused from its bytes
    raw=f.canonical(k6a.policy_object()).replace(b'"automatic_retry":false',b'"automatic_retry":false,"note":"\\ud800"');assert json.loads(raw)['note']=='\ud800'
    m,docs,host=k6a.fresh();docs.plan['policy']=k6a.policy_member(raw);docs.chain()
    assert f.refusal(docs.authenticate)=='POLICY_JSON_INVALID' and docs.run(f.Untouchable())['code']=='POLICY_JSON_INVALID'
    assert f.refusal(lambda:m.policy_digest({'note':'\ud800'}))=='POLICY_JSON_INVALID'

def test_nothing_of_the_environment_is_free_each_value_follows_from_another_signed_member():
    m,docs,host=k6a.fresh();plan=docs.plan
    assert m.environment_of(plan)==k6a.environment() and m.override_of(plan)==k6a.override()
    assert m.worker_name(plan)==hostemu.WORKER and m.pin_path(plan)==hostemu.PIN and m.lock_path(plan)==k6a.LOCK
    other=copy.deepcopy(plan);other['directory_name']='2026-10-05-b'
    assert m.environment_of(other)['C3PO_R2D2_V2_LIVE_POLICY_FILE']=='/app/day-d-data/r2d2-v2-live/2026-10-05-b/policy.json'
    other=copy.deepcopy(plan);other['worker']['mount_target']='/app/elsewhere'
    assert m.environment_of(other)['C3PO_R2D2_V2_SHADOW_RELEASE_FILE']=='/app/elsewhere/r2d2-v2-release-20261005/release.CERTIFIED.json'
    # the live directory may lie directly in the data root; the release may lie deeper
    m,docs,host=k6a.fresh();docs.plan['live_parent']=hostemu.rows(host,hostemu.DATA);docs.chain();receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and host.tree.get(hostemu.DATA+'/'+k6a.LEAF) is not None

def test_effects_change_with_every_signed_member_so_no_member_can_be_swapped_under_a_signature():
    """EFFECTS_BINDING: a plan member changed after the authority and the GO were written no longer matches them."""
    def swap(path,value):
        m,docs,host=k6a.fresh();before=m.canonical(m.effects_of(docs.plan));target=docs.plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value(host) if callable(value) else value
        docs.chain(effects=False);return f.refusal(docs.authenticate),m.canonical(m.effects_of(docs.plan))!=before
    other=k6a.policy_bytes(capacity=549)
    for path,value in ((['directory_name'],'2026-10-05-b'),(['override_name'],'compose.proof.json'),(['policy'],k6a.policy_member(other)),
                       (['policy','name'],'live.json'),(['worker','image_id'],hostemu.OTHER),(['worker','mount_target'],'/app/other'),
                       (['lock','wait_seconds'],5),(['evidence_boot_id_sha256'],'7'*64),(['release','directory_name'],'r2d2-v2-release-b'),
                       (['release','file_name'],'release.json'),(['release','bytes'],len(k6a.RELEASE)+1),
                       (['live_parent',-1,'inode'],77),(['release','parent',-1,'inode'],78),(['deploy_directory',-1,'inode'],79),(['lock','directory',-1,'inode'],80)):
        code,differs=swap(path,value);assert (code,differs)==('EFFECTS_BINDING',True),path
