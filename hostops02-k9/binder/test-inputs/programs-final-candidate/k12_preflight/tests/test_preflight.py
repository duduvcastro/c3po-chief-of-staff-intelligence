"""K12p behaviour on the emulated host: the plan, the prechecks it shares with the launch, the one attached run, the proof
that nothing was left, and the reading of the preflight's line. Synthetic only (tests/k12emu.py)."""
import copy
import json

import pytest

import family as f
import hostemu
import k12emu as e
import k12p

K=k12p.K()
M=K.m

def docs_for(now=None,code=0,line=None,body=None):
    host=k12p.world(K,code,line);return f.Docs(K,k12p.fields(host,body),now=e.at(now or k12p.MOMENT)),host

def refusal(docs):return f.refusal(docs.authenticate)

def run(docs,host,**options):
    before=host.tree.snapshot();receipt=docs.run(host,**options);text=json.dumps(receipt)
    assert f.sealed(receipt) and hostemu.SECRET not in text and 'never-emit' not in text and 'SYNTHA' not in text
    assert not [entry for entry in host.log if entry[0] in ('open','read') and 'secret.env' in str(entry[1])]
    if receipt['status']=='REFUSED':assert host.tree.snapshot()==before
    return receipt

def refused(docs,host,code,**options):
    receipt=run(docs,host,**options);assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED',M.REFUSED_OUTCOME,code),(receipt['code'],receipt.get('detail'))
    return receipt

def partial(docs,host,code):
    receipt=run(docs,host);assert (receipt['status'],receipt['outcome'],receipt['code'])==(M.PARTIAL_STATUS,M.PARTIAL_OUTCOME,code),(receipt['code'],receipt.get('detail'))
    return receipt


def test_the_plan():
    docs,_=docs_for(body=e.capacity_request(index=2));assert refusal(docs)=='NOT_THE_PRIMARY_WINDOW'
    for change,code in ((dict(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),(dict(parent_rows={}),'PARENT_ROWS_INVALID'),
                        (dict(capacity_request=None),'CAPACITY_REQUEST_INVALID')):
        docs,_=docs_for();docs.plan.update(change);docs.chain();assert refusal(docs)==code
    for name,change,code in (('config',dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),('docker_cli',dict(uid=3),'CHAIN_ROW_UNSAFE'),
                             ('journal',dict(gid=4),'CHAIN_NOT_ROOT_CONTROLLED'),('journal',dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),
                             ('data',dict(mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),('data',dict(uid=1000),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),
                             ('data',dict(mode=0o750),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),
                             ('receipts',dict(mode=0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),('receipts',dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),
                             ('manifests',dict(gid=5),'CHAIN_NOT_ROOT_CONTROLLED'),('reader_config',dict(mode=0o720),'CHAIN_ROW_UNSAFE')):
        docs,_=docs_for();docs.plan['parent_rows'][name][-1].update(change);docs.chain();assert refusal(docs)==code,name
    for name in k12p.CHAINS:
        docs,_=docs_for();docs.plan['parent_rows'][name][1].update(gid=1000);docs.chain();assert refusal(docs)=='CHAIN_NOT_ROOT_CONTROLLED',name
        docs,_=docs_for();del docs.plan['parent_rows'][name];docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID',name
    docs,_=docs_for();docs.plan['parent_rows']['data'][2].update(device=801);docs.chain();assert refusal(docs)=='DATA_VOLUME_NOT_A_MOUNT_POINT'
    docs,host=docs_for();docs.plan['parent_rows']['extra']=e.rows(host,e.RECEIPTS);docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID'
    body=e.capacity_request();body['mounts'][0]['source']=e.RELEASE;docs,_=docs_for(body=body);assert refusal(docs)=='CAPACITY_REQUEST_DATA_BIND'

def test_effects_are_the_literal_run():
    docs,_=docs_for();effects=docs.go['effects'];body=e.capacity_request();raw=f.canonical(body)
    expected=['run','--rm','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
              '--name','c3po-k12-20261006-preflight','--label',"c3po.k12.request_sha256=<this request's sha256>",'--label','c3po.k12.capacity_request_sha256='+e.sha(raw),
              '--network','c3po_c3po_internal','--env-file','/etc/c3po-reader/secret.env','--env-file','/etc/c3po-reader/pins.env',
              '--env','C3PO_R2D2_V2_SHADOW_ENABLED=true','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',
              '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+body['capacity_config_file'],'--env','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+body['capacity_config_sha256'],
              '--mount','type=bind,source=/mnt/day-d-data,target=/app/day-d-data,readonly','--mount','type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-journal,readonly',
              '--mount','type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly','--mount','type=bind,source=/etc/c3po-bar/manifests,target=/etc/c3po-bar/manifests',
              e.IMAGE,'python','-I','-B','/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER)]+body['writer_argv']+['--preflight']
    assert effects['run']==expected and effects['container_name']=='c3po-k12-20261006-preflight' and effects['before']=='2026-10-06T10:38:00+00:00'
    assert effects['after']=={'container':'ABSENT','manifests_directory':'UNCHANGED'} and effects['files_created_by_this_process']==1
    assert effects['secret_env']=={'path':'/etc/c3po-reader/secret.env','require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'}
    assert effects['writer']['sha256']==e.sha(e.WRITER) and effects['pins_env']['sha256']==e.sha(e.PINS) and effects['capacity_config']['sha256']==body['capacity_config_sha256']
    assert set(effects['chains'])=={'config','manifests','reader_config','docker_cli','journal','data','receipts'} and effects['docker_config']==e.DOCKER_CLI
    assert (effects['day'],effects['window'],effects['window_slot'],effects['capacity_request_sha256'])==('2026-10-06','primary',1,e.sha(raw))

def test_every_member_of_the_effects():
    docs,host=docs_for();effects=docs.go['effects'];body=e.capacity_request()
    assert set(effects)=={'operation','epoch','evidence_boot_id_sha256','capacity_request_sha256','day','window','window_slot','run','docker_config',
                          'container_name','before','chains','writer','capacity_config','pins_env','secret_env','after','files_created_by_this_process','activation',
                          'journal','data','chain_rule','creates','manifests'}
    assert (effects['operation'],effects['epoch'],effects['evidence_boot_id_sha256'])==('GO_WRITE_HOSTOPS02_K12_PREFLIGHT_01','R2D2-V2-SHADOW-2026-10-05',f.BOOT_SHA)
    assert effects['writer']=={'path':'/var/lib/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER),'sha256':e.sha(e.WRITER),'require':'ROOT_0600_ONE_LINK'}
    assert effects['capacity_config']=={'path':'/var/lib/c3po-capacity/config/session=2026-10-06.primary.capacity.json','sha256':body['capacity_config_sha256'],
                                        'require':'ROOT_0600_ONE_LINK'}
    assert effects['pins_env']=={'path':'/etc/c3po-reader/pins.env','sha256':e.sha(e.PINS),'require':'ROOT_0600_ONE_LINK'}
    assert effects['activation'] is False and effects['files_created_by_this_process']==1 and effects['window_slot']==1
    assert effects['chains']['journal']['path']==e.JOURNAL and effects['chains']['data']['path']==e.RELEASE
    assert effects['journal']=={'path':e.JOURNAL,'target':'/c3po-journal','require':'ROOT_0700_CATALOG_ROOT_0600'}
    assert effects['data']=={'path':'/mnt/day-d-data','target':'/app/day-d-data','read_only':True,'exception':'CODEX_429_5986698996',
        'release':{'path':e.RELEASE+'/release.CERTIFIED.json','sha256':e.sha(e.RELEASE_BYTES),'require':'ROOT_0600_ONE_LINK',
                   'checked':'BEFORE_THE_RUN_AND_AFTER_IT'}}
    assert effects['chain_rule']=='ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK'
    assert effects['creates']=={'path':k12p.CLAIM,'mode_octal':'0600','uid':0,'gid':0,'schema':'K12_PREFLIGHT_CLAIM_V1','expect':'ABSENT','before':'THE_RUN'}
    assert effects['manifests']=={'path':e.MANIFESTS,'bound':'READ_WRITE_AS_IN_THE_DISPATCH','effects':'CLOSED',
                                  'proof':'LSTAT_SIGNATURE_OF_EVERY_ENTRY_AND_FSTAT_SIGNATURE_OF_THE_DIRECTORY_EQUAL_BEFORE_AND_AFTER'}

def test_the_evidence_must_name_the_k12_tree_read():
    docs,host=docs_for();docs.request['evidence']=[{'role':'PRIOR','operation':'GO_READONLY_SYNTHETIC_PRIOR_01','receipt_sha256':'a'*64}];docs.chain()
    assert refusal(docs)=='EVIDENCE_OPERATION_MISSING'
    docs,host=docs_for();docs.request['evidence']=[{'role':'TREE','operation':'GO_READONLY_HOSTOPS02_K12_COLLECT_01','receipt_sha256':'b'*64}];docs.chain()
    docs.authenticate()

def test_the_preflight_runs_once_in_the_dispatch_layout_and_leaves_nothing():
    docs,host=docs_for();receipt=run(docs,host);assert (receipt['status'],receipt['outcome'],receipt['code'])==(M.COMPLETE_STATUS,M.COMPLETE_OUTCOME,None)
    runs=[entry for entry in host.commands if entry['argv'][1:2]==['run']];assert len(runs)==1 and runs[0]['seconds']==40 and runs[0]['stdin'] is None
    assert runs[0]['argv'][1:]==[word.replace("<this request's sha256>",receipt['request_sha256']) for word in docs.go['effects']['run']]
    assert all(entry['docker_config']==e.DOCKER_CLI for entry in host.commands)
    call=host.preflight_calls[0];assert call['binds'][3]=={'source':e.MANIFESTS,'target':e.MANIFESTS,'read_only':False} and call['command'][-1]=='--preflight'
    assert receipt['preflight']['ok'] is True and receipt['preflight']['checks']['directory_checked'] is True and receipt['preflight']['status']=='PREFLIGHT_OK'
    assert receipt['detail']['container_left'] is False and receipt['detail']['manifests_after']==receipt['detail']['manifests_before']=={'entries':0,'manifest_present':False}
    assert receipt['detail']['manifests_unchanged'] is True and '_signature' not in json.dumps(receipt)
    assert receipt['mutating_calls']['uncertain']==0 and receipt['mutating_calls']['failed_nothing_changed']==1 and host.docker.container('c3po-k12-20261006-preflight') is None
    assert receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and receipt['ledger'][0]['key']=='PREFLIGHT_CLAIM' and receipt['objects_left_by_this_run']==1
    node=host.tree.get(k12p.CLAIM);claim=json.loads(bytes(node.content))
    assert (node.uid,node.gid,node.mode,node.nlink)==(0,0,0o600,1) and claim=={'schema':'K12_PREFLIGHT_CLAIM_V1','epoch':'R2D2-V2-SHADOW-2026-10-05',
        'day':'2026-10-06','window':'primary','capacity_request_sha256':e.sha(f.canonical(e.capacity_request())),
        'preflight_request_sha256':receipt['request_sha256'],'container_name':'c3po-k12-20261006-preflight'}
    assert set(host.tree.get(e.RECEIPTS).children)=={'k12-2026-10-06-preflight.claim.json'}

def test_one_preflight_per_day_by_its_claim():
    docs,host=docs_for();assert run(docs,host)['status']==M.COMPLETE_STATUS
    again=f.Docs(K,k12p.fields(host),now=e.at(k12p.MOMENT));receipt=refused(again,host,'PREFLIGHT_ALREADY_CLAIMED');assert len(host.preflight_calls)==1
    docs,host=docs_for();host.tree.add(k12p.CLAIM,kind='file',mode=0o600,content=b'{}');refused(docs,host,'PREFLIGHT_ALREADY_CLAIMED')
    docs,host=docs_for();host.tree.add(k12p.CLAIM,kind='symlink');refused(docs,host,'PREFLIGHT_ALREADY_CLAIMED')
    docs,host=docs_for();host.tree.add(e.RECEIPTS+'/k12-2026-10-07-preflight.claim.json',kind='file',mode=0o600);assert run(docs,host)['status']==M.COMPLETE_STATUS

def test_the_claim_comes_before_the_run_and_its_failure_stops_it():
    docs,host=docs_for();seen=[]
    def watch(call):
        seen.append(host.tree.get(k12p.CLAIM) is not None);return 0,k12p.preflight_line()
    host.docker.on_preflight=watch;assert run(docs,host)['status']==M.COMPLETE_STATUS and seen==[True]
    docs,host=docs_for();host.readonly=True;receipt=refused(docs,host,'FILESYSTEM_READ_ONLY');assert host.preflight_calls==[] and receipt['ledger'][0]['state']!='INSTALLED_DURABLE'

RELEASE_FILE=e.RELEASE+'/release.CERTIFIED.json'
def test_the_release_before_and_after_the_run():
    for action,code in ((lambda host:host.tree.remove(RELEASE_FILE),'RELEASE_ABSENT'),(lambda host:change(host,RELEASE_FILE,mode=0o640),'RELEASE_NOT_PRIVATE'),
                        (lambda host:change(host,RELEASE_FILE,content=bytearray(b'{}')),'RELEASE_NOT_THE_SIGNED_BYTES')):
        docs,host=docs_for();action(host);refused(docs,host,code);assert host.preflight_calls==[]
    def changes(call):
        change(host,RELEASE_FILE,content=bytearray(b'{"changed":1}'));return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=changes;receipt=partial(docs,host,'RELEASE_CHANGED_DURING_PREFLIGHT')
    assert receipt['mutating_calls']['uncertain']==0 and receipt['preflight'] is None

def test_the_claim_is_read_back():
    docs,host=docs_for()
    def hook(host_,name,detail,calls):
        node=host_.tree.get(k12p.CLAIM)
        if name=='unlink' and node is not None:node.content.extend(b' ')
    host.hook=hook;receipt=partial(docs,host,'READBACK_HASH_MISMATCH');assert host.preflight_calls==[]

def test_closed_effects_on_the_manifests_directory():
    """Every entry's lstat signature and the directory's own: a change to an existing entry during the run (content,
    mode, owner, a new link, its removal) is something left, even with the same number of entries."""
    for action in (lambda node:node.content.extend(b' '),lambda node:setattr(node,'mode',0o644),lambda node:setattr(node,'uid',1000),
                   lambda node:setattr(node,'ctime',node.ctime+1),lambda node:setattr(node,'mtime',node.mtime+1),lambda node:setattr(node,'gid',5)):
        docs,host=docs_for();host.tree.add(e.MANIFESTS+'/2026-10-05.json',kind='file',mode=0o600,content=b'{}')
        def touch(call,action=action):
            action(host.tree.get(e.MANIFESTS+'/2026-10-05.json'));return 0,k12p.preflight_line()
        host.docker.on_preflight=touch;receipt=partial(docs,host,'PREFLIGHT_LEFT_SOMETHING')
        assert receipt['detail']['manifests_unchanged'] is False and receipt['detail']['manifests_after']==receipt['detail']['manifests_before']=={'entries':1,'manifest_present':False}
    docs,host=docs_for();host.tree.add(e.MANIFESTS+'/2026-10-05.json',kind='file',mode=0o600,content=b'{}')
    def swap(call):
        host.tree.remove(e.MANIFESTS+'/2026-10-05.json');host.tree.add(e.MANIFESTS+'/2026-10-04.json',kind='file',mode=0o600,content=b'{}');return 0,k12p.preflight_line()
    host.docker.on_preflight=swap;partial(docs,host,'PREFLIGHT_LEFT_SOMETHING')
    docs,host=docs_for();host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600,content=b'{}')
    def gone(call):
        host.tree.remove(e.MANIFESTS+'/2026-10-06.json');return 0,k12p.preflight_line()
    host.docker.on_preflight=gone;receipt=partial(docs,host,'PREFLIGHT_LEFT_SOMETHING');assert receipt['detail']['manifests_before']=={'entries':1,'manifest_present':True}
    docs,host=docs_for()
    def directory(call):
        host.tree.get(e.MANIFESTS).mtime+=1;return 0,k12p.preflight_line()
    host.docker.on_preflight=directory;partial(docs,host,'PREFLIGHT_LEFT_SOMETHING')
    docs,host=docs_for();host.tree.add(e.MANIFESTS+'/2026-10-05.json',kind='file',mode=0o600,content=b'{}');assert run(docs,host)['status']==M.COMPLETE_STATUS

def change(host,path,**attributes):
    node=host.tree.get(path)
    for key,value in attributes.items():setattr(node,key,value)

WRITER_PATH=e.CONFIG+'/manifest_writer-'+e.sha(e.WRITER)+'.py'
@pytest.mark.parametrize('action,code',[
    (lambda host:host.tree.remove(WRITER_PATH),'WRITER_FILE_ABSENT'),(lambda host:change(host,WRITER_PATH,mode=0o400),'WRITER_FILE_NOT_PRIVATE'),
    (lambda host:change(host,WRITER_PATH,content=bytearray(b'x')),'WRITER_BYTES_NOT_THE_SIGNED_ONES'),
    (lambda host:host.tree.remove(e.CONFIG+'/session=2026-10-06.primary.capacity.json'),'CAPACITY_CONFIG_ABSENT'),
    (lambda host:change(host,e.CONFIG+'/session=2026-10-06.primary.capacity.json',gid=4),'CAPACITY_CONFIG_NOT_PRIVATE'),
    (lambda host:change(host,e.CONFIG+'/session=2026-10-06.primary.capacity.json',content=bytearray(b'{}')),'CAPACITY_CONFIG_NOT_THE_SIGNED_BYTES'),
    (lambda host:host.tree.remove(e.READER+'/pins.env'),'PINS_ENV_ABSENT'),(lambda host:change(host,e.READER+'/pins.env',nlink=3),'PINS_ENV_NOT_PRIVATE'),
    (lambda host:change(host,e.READER+'/pins.env',content=bytearray(b'')),'PINS_ENV_NOT_THE_SIGNED_BYTES'),
    (lambda host:host.tree.remove(e.READER+'/secret.env'),'SECRET_ENV_ABSENT'),(lambda host:change(host,e.READER+'/secret.env',mode=0o604),'SECRET_ENV_NOT_PRIVATE'),
    (lambda host:host.tree.add(e.DOCKER_CLI+'/x',kind='file'),'DOCKER_CLI_DIRECTORY_NOT_EMPTY'),
    (lambda host:change(host,e.JOURNAL+'/epoch.json',mode=0o640),'JOURNAL_CATALOG_NOT_AS_REQUIRED'),
    (lambda host:host.tree.remove(e.JOURNAL+'/maintenance.lock'),'JOURNAL_CATALOG_NOT_AS_REQUIRED'),
    (lambda host:host.docker.images.__setitem__(0,dict(host.docker.images[0],Config={'Labels':{}})),'IMAGE_REVISION_MISMATCH'),
    (lambda host:host.docker.containers.append(hostemu.container('c3po-k12-20261006-preflight',e.IMAGE,e.IMAGE,[])),'PREFLIGHT_CONTAINER_PRESENT'),
    (lambda host:host.docker.containers.append(hostemu.container('c3po-k12-20261006-w1',e.IMAGE,e.IMAGE,[],running=False)),'CAPACITY_CONTAINER_OF_THE_DAY_PRESENT'),
    (lambda host:change(host,e.MANIFESTS,ino=4),'PARENT_IDENTITY_MISMATCH')])
def test_prechecks(action,code):
    docs,host=docs_for();action(host);refused(docs,host,code)

def test_an_image_answer_of_another_id_is_refused():
    docs,host=docs_for();real=host.docker.images[0];host.docker.images[0]=dict(real,Id=hostemu.OTHER,RepoTags=[e.IMAGE]);refused(docs,host,'IMAGE_ID_MISMATCH')

def test_containers_of_other_days_do_not_matter():
    docs,host=docs_for();host.docker.containers.append(hostemu.container('c3po-k12-20261007-w1',e.IMAGE,e.IMAGE,[],running=False))
    assert run(docs,host)['status']==M.COMPLETE_STATUS

def test_clock_boot_and_budget():
    docs,host=docs_for(now=e.utc(e.DAY,'10:38:00'));refused(docs,host,'PREFLIGHT_NOT_BEFORE_THE_PRIMARY_WINDOW')
    docs,host=docs_for(now=e.utc(e.DAY,'10:37:59'));assert run(docs,host)['status']==M.COMPLETE_STATUS
    docs,host=docs_for(now='2026-10-05T10:30:00+00:00');refused(docs,host,'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
    docs,host=docs_for();docs.plan['evidence_boot_id_sha256']='cd'*32;docs.chain();refused(docs,host,'EVIDENCE_FROM_EARLIER_BOOT')
    docs,host=docs_for();budget=f.Budget(docs.now).attach(host);budget.cost(8.5,'ps','-a');refused(docs,host,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',**budget.options())
    docs,host=docs_for();budget=f.Budget(docs.now).attach(host);budget.cost(8,'ps','-a');assert run(docs,host,**budget.options())['status']==M.COMPLETE_STATUS

@pytest.mark.parametrize('line,code',[
    (k12p.preflight_line(status='REFUSED',code='MANIFEST_DIRECTORY_NOT_WRITABLE'),3),(k12p.preflight_line(),3),
    (k12p.preflight_line(mode='PUBLISH'),0),(k12p.preflight_line(session=None),0),(k12p.preflight_line(owner_uid=1),0),
    (k12p.preflight_line(capacity_config_sha256='1'*64),0),(k12p.preflight_line(release_sha256='1'*64),0),(k12p.preflight_line(package_sha256='1'*64),0),
    (k12p.preflight_line(build_sha='b'*40),0),(k12p.preflight_line(massive_bars_enabled=False),0),
    (k12p.preflight_line(checks=dict(k12p.CHECKS,directory_checked=False)),0),(k12p.preflight_line(checks={'release_verified':True}),0),
    (k12p.preflight_line(status='MATCH_VERIFIED',mode='VERIFY_ONLY'),0),(k12p.preflight_line(status='MATCH_VERIFIED'),0),
    (k12p.preflight_line(status='ALREADY_PUBLISHED_VERIFIED'),0)])
def test_a_preflight_that_is_not_ok_is_partial_with_its_line_and_its_claim(line,code):
    docs,host=docs_for(code=code,line=line);receipt=partial(docs,host,'PREFLIGHT_NOT_OK');assert receipt['preflight']['ok'] is False
    assert host.tree.get(k12p.CLAIM) is not None and receipt['mutating_calls']['uncertain']==0

def test_lines_that_are_not_one_line():
    for line,code in ((b'',3,),(b'not json\n',1),(k12p.preflight_line()*2,0),(b'\xff\n',1)):
        docs,host=docs_for(code=code,line=line);receipt=run(docs,host);assert receipt['status']==M.PARTIAL_STATUS and receipt['code'].startswith('WRITER_LINE_'),receipt['code']
    docs,host=docs_for(code=125,line=b'');partial(docs,host,'PREFLIGHT_ENGINE_FAILURE')
    docs,host=docs_for(code=127,line=k12p.preflight_line());partial(docs,host,'PREFLIGHT_ENGINE_FAILURE')

def test_checks_copied_are_booleans_and_counts_only():
    line=k12p.preflight_line(checks=dict(k12p.CHECKS,note='text',Upper=True,nested={'a':1},big=10**7));docs,host=docs_for(line=line)
    receipt=run(docs,host);assert receipt['status']==M.COMPLETE_STATUS and receipt['preflight']['checks']==dict(sorted(k12p.CHECKS.items()))

def test_the_run_that_does_not_end_or_leaves_something():
    docs,host=docs_for();host.hang={('run','--rm')};receipt=partial(docs,host,'PREFLIGHT_UNCERTAIN');assert receipt['detail']['container_left'] is False
    docs,host=docs_for();host.hang_after={('run','--rm')};partial(docs,host,'PREFLIGHT_UNCERTAIN')
    docs,host=docs_for();host.absent={('run','--rm')};receipt=partial(docs,host,'COMMAND_NOT_STARTED');assert host.tree.get(k12p.CLAIM) is not None
    def stays(call):
        host.docker.containers.append(hostemu.container('c3po-k12-20261006-preflight',e.IMAGE,e.IMAGE,[]));return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=stays;receipt=partial(docs,host,'PREFLIGHT_LEFT_SOMETHING');assert receipt['detail']['container_left'] is True
    assert receipt['mutating_calls']['uncertain']==1 and receipt['mutating_calls']['failed_nothing_changed']==0
    def writes(call):
        host.tree.add(e.MANIFESTS+'/.2026-10-06.json.%s.tmp'%('ab'*8),kind='file',mode=0o600);return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=writes;partial(docs,host,'PREFLIGHT_LEFT_SOMETHING')
    def other(call):
        host.tree.add(e.MANIFESTS+'/note',kind='file',mode=0o600);return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=other;partial(docs,host,'PREFLIGHT_LEFT_SOMETHING')
    def moved(call):
        host.tree.get(e.MANIFESTS).mode=0o755;return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=moved;receipt=partial(docs,host,'PARENT_REPLACED');assert receipt['mutating_calls']['uncertain']==1
    docs,host=docs_for();seen=[0]
    def names(host_,name,detail,calls):
        if name=='names':
            seen[0]+=1
            if seen[0]==3:raise OSError(5,'injected')
    host.hook=names;receipt=partial(docs,host,'READBACK_UNAVAILABLE');assert receipt['mutating_calls']['uncertain']==1
    def breaks(call):
        host.docker.ps_returncode=1;return 0,k12p.preflight_line()
    docs,host=docs_for();host.docker.on_preflight=breaks;partial(docs,host,'COMMAND_FAILED')

def test_the_row_is_an_attached_run_that_never_stays():
    row=M.COMMANDS['preflight']
    assert row['argv']==['run','--rm','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges']
    assert (row['class'],row['kind'],row['stdin'])==('RUN','EFFECT',False) and set(M.COMMANDS)=={'image','container_list','preflight'}
    assert M.effects_budget('preflight')==44 and M.WRITES_ALLOWED is True and M.ACTIVATION_ALLOWED is False and M.DATE_CLASS=='WRITE_SESSIONS'
