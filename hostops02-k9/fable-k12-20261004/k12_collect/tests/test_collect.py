"""K12r behaviour on the emulated host: the plan's refusals, the window's verdict for every state a window can be left in,
TREE, and what never leaves the host. Synthetic only (tests/k12emu.py)."""
import copy
import json

import pytest

import family as f
import hostemu
import k12emu as e
import k12r

K=k12r.K()
M=K.m

def docs_for(mode='COLLECT',host=None,now=None,**options):
    k=K
    if host is None:
        host=e.world(k)
        if mode=='COLLECT':k12r.published(k,host)
    return f.Docs(k,k12r.fields(host,mode,**options),now=e.at(now or k12r.MOMENTS[mode])),host

def refusal(docs):return f.refusal(docs.authenticate)

def run(docs,host,**options):
    before=(host.tree.snapshot(),e.engine(host));receipt=docs.run(host,**options);text=json.dumps(receipt)
    assert f.sealed(receipt) and hostemu.SECRET not in text and e.MANIFEST_SHA not in text and 'SYNTHA' not in text and 'never-emit' not in text
    assert 'stdout_b64' not in text and '"symbol_count"' not in text and '"manifest_sha256"' not in text
    assert (host.tree.snapshot(),e.engine(host))==before and host.mutating()==[],'a read changed the host'
    assert not [entry for entry in host.log if entry[0] in ('open','read') and 'secret.env' in str(entry[1])]
    assert all(entry['argv'][1:4]==['container','inspect','--format'] or entry['argv'][1:3]==['ps','-a'] for entry in host.commands)
    return receipt

def verdict(docs,host,expected,reason,**options):
    receipt=run(docs,host,**options);assert (receipt['window_verdict'],receipt['window_reason'])==(expected,reason),(receipt['window_verdict'],receipt['window_reason'],receipt['items'])
    if expected=='VERIFIED':assert (receipt['status'],receipt['outcome'])==(M.COMPLETE_STATUS,M.COMPLETE_OUTCOME)
    else:assert (receipt['status'],receipt['outcome'],receipt['code'])==(M.PARTIAL_STATUS,M.PARTIAL_OUTCOME,None)
    assert receipt['contingency_allowed'] is (expected=='NOT_VERIFIED') and receipt['day_decided'] is (expected in ('VERIFIED','TERMINAL_EMPTY_LIST','STOPPED_BEFORE_THE_VIEW'))
    return receipt


# ---------------------------------------------------------------- the plan
@pytest.mark.parametrize('change,code',[(dict(mode='TREES'),'MODE_INVALID'),(dict(tree_journal=e.JOURNAL),'MODE_MEMBERS_INVALID'),
    (dict(launch_request_sha256=None),'MODE_MEMBERS_INVALID'),(dict(launch_request_sha256='0'*64),'MODE_MEMBERS_INVALID'),
    (dict(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),(dict(parent_rows={}),'PARENT_ROWS_INVALID'),(dict(parent_rows=[]),'PARENT_ROWS_INVALID'),
    (dict(capacity_request=None),'CAPACITY_REQUEST_INVALID')])
def test_collect_plan(change,code):
    docs,_=docs_for();docs.plan.update(change);docs.chain();assert refusal(docs)==code

def test_collect_chains():
    for name,index,change,code in (('receipts',-1,dict(mode=0o750),'DIRECTORY_NOT_ROOT_PRIVATE'),('manifests',-1,dict(uid=5),'CHAIN_ROW_UNSAFE'),
                                   ('manifests',-1,dict(gid=5),'CHAIN_NOT_ROOT_CONTROLLED'),('receipts',1,dict(mode=0o777),'CHAIN_ROW_UNSAFE'),
                                   ('receipts',2,dict(gid=1000),'CHAIN_NOT_ROOT_CONTROLLED'),('receipts',-1,dict(mode=0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),
                                   ('manifests',0,dict(mode=0o3755),'CHAIN_NOT_ROOT_CONTROLLED')):
        docs,_=docs_for();docs.plan['parent_rows'][name][index].update(change);docs.chain();assert refusal(docs)==code,(name,change)
    docs,host=docs_for();docs.plan['parent_rows']['journal']=e.rows(host,e.JOURNAL);docs.chain();assert refusal(docs)=='PARENT_ROWS_INVALID'

@pytest.mark.parametrize('change,code',[(dict(capacity_request=e.member(e.capacity_request())),'MODE_MEMBERS_INVALID'),
    (dict(launch_request_sha256='5e'*32),'MODE_MEMBERS_INVALID'),(dict(parent_rows={}),'MODE_MEMBERS_INVALID'),
    (dict(evidence_boot_id_sha256='1'*64),'MODE_MEMBERS_INVALID'),(dict(tree_journal=None),'TREE_BINDS_INVALID'),
    (dict(tree_journal='/mnt/day-d-data/journal'),'TREE_BINDS_INVALID'),(dict(tree_journal='/'),'TREE_BINDS_INVALID'),
    (dict(tree_journal='/var/lib/c3po-capacity'),'TREE_BINDS_INVALID'),(dict(tree_journal='var/lib/x'),'TREE_BINDS_INVALID'),
    (dict(tree_journal=5),'TREE_BINDS_INVALID'),(dict(tree_journal='/var/lib/c3po/r2d2-v2-source-20261005/j'),'TREE_BINDS_INVALID'),
    (dict(tree_journal=e.RELEASE),'TREE_BINDS_INVALID')])
def test_tree_plan(change,code):
    docs,_=docs_for('TREE');docs.plan.update(change);docs.chain();assert refusal(docs)==code

def test_effects_literal():
    docs,_=docs_for();effects=docs.go['effects'];raw=f.canonical(e.capacity_request())
    assert effects['reads']=={'container':['container','inspect','--format','<K12_FORMAT>','c3po-k12-20261006-w1'],
                              'persisted':'/var/lib/c3po-reader/capacity-receipts/k12-2026-10-06-w1.writer.json','manifest':'/etc/c3po-bar/manifests/2026-10-06.json'}
    assert (effects['mode'],effects['day'],effects['window'],effects['window_slot'],effects['capacity_request_sha256'],effects['launch_request_sha256'])==(
        'COLLECT','2026-10-06','primary',1,e.sha(raw),'5e'*32)
    assert effects['not_before']=='2026-10-06T10:45:00+00:00 + 60 s' and set(effects['chains'])=={'manifests','receipts','data'}
    assert (effects['writes'],effects['containers_started_stopped_or_removed'],effects['secret_files_opened'],effects['activation'])==(0,0,0,False)
    assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and effects['epoch']=='R2D2-V2-SHADOW-2026-10-05' and effects['operation']=='GO_READONLY_HOSTOPS02_K12_COLLECT_01'
    docs,_=docs_for('TREE');effects=docs.go['effects']
    assert effects['reads']['directories']=={'capacity_root':'/var/lib/c3po-capacity','config':'/var/lib/c3po-capacity/config','manifests':'/etc/c3po-bar/manifests',
        'reader_config':'/etc/c3po-reader','docker_cli':'/etc/c3po-reader/docker-cli','journal':e.JOURNAL,'data':e.RELEASE,
        'receipts':'/var/lib/c3po-reader/capacity-receipts'}
    assert effects['reads']['metadata_only']==['/etc/c3po-reader/secret.env','/etc/c3po-reader/pins.env',e.JOURNAL+'/epoch.json',e.JOURNAL+'/maintenance.lock',
                                              e.RELEASE+'/release.CERTIFIED.json']
    assert effects['reads']['boot']=='/proc/sys/kernel/random/boot_id' and effects['mode']=='TREE' and 'chains' not in effects
    assert effects['reads']['chain_rule']=='ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK'


# ---------------------------------------------------------------- before any observation
def test_collect_window_and_boot():
    docs,host=docs_for(now=e.utc(e.DAY,'10:45:59'));receipt=run(docs,host);assert (receipt['status'],receipt['code'])==('REFUSED','COLLECT_BEFORE_THE_VIEW_AND_A_MINUTE')
    docs,host=docs_for(now=e.utc(e.DAY,'10:46:00'));verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK')
    docs,host=docs_for(now='2026-10-07T10:46:30+00:00');receipt=run(docs,host);assert receipt['code']=='RUN_NOT_ON_THE_DAY_OF_THE_WINDOW'
    docs,host=docs_for();docs.plan['evidence_boot_id_sha256']='ab'*32;docs.chain();receipt=run(docs,host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','EVIDENCE_FROM_EARLIER_BOOT','BEFORE_OBSERVATION')
    docs,host=docs_for('TREE',now='2026-10-02T03:00:00+00:00');assert run(docs,host)['status']==M.COMPLETE_STATUS


# ---------------------------------------------------------------- the verdict, state by state
def test_published_and_read_back():
    docs,host=docs_for();receipt=verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK')
    line=receipt['writer_line'];assert line['status']=='PUBLISHED_VERIFIED' and line['binding_sha256']==e.label('binding') and line['go_mode']=='DELEGATED_ACT_B'
    assert line['manifest_sha256_present'] is True and line['symbol_count_present'] is True and receipt['manifest_sha256_equals_the_line'] is True
    assert receipt['binding_may_be_committed'] is True and receipt['container_name']=='c3po-k12-20261006-w1'
    item=host.docker.container('c3po-k12-20261006-w1');assert receipt['container_id']==item['Id'] and receipt['items']['container']['ours'] is True
    assert receipt['items']['manifest']=={'present':True,'temporaries':0,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1,'private':True,
                                          'bytes_within_limit':True,'status':'COMPLETE'}
    assert receipt['items']['persisted']['line_valid'] is True and receipt['items']['persisted']['of_this_container'] is True and receipt['findings']==[]

def window(line=None,code=0,publish=True,persist=True,two_links=False,index=1,body=None,host=None):
    host=host or e.world(K);k12r.published(K,host,index=index,line=line,code=code,publish=publish,persist=persist,two_links=two_links)
    now=e.utc(e.DAY,{1:'10:46:30',2:'11:46:30',3:'12:46:30'}[index])
    return docs_for(host=host,now=now,body=body or e.capacity_request(index=index))

def test_verdicts_from_the_writer_line():
    for line,code,publish,expected,reason in (
        (e.writer_line('ALREADY_PUBLISHED_VERIFIED'),0,True,'VERIFIED','PUBLISHED_AND_READ_BACK'),
        (e.writer_line(**e.EMPTY_LIST),3,False,'TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY'),
        (e.writer_line(**dict(e.EMPTY_LIST,prepare_status='PRECOMMITTED')),3,False,'TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY'),
        (e.writer_line(**dict(e.EMPTY_LIST,prepare_status='ATTEMPTED')),3,False,'NOT_VERIFIED','WRITER_REFUSED'),
        (e.writer_line('REFUSED','MANIFEST_VETO_WINDOW_MISSED'),3,False,'NOT_VERIFIED','WRITER_REFUSED'),
        (e.writer_line('UNVERIFIED','MANIFEST_DATABASE_UNAVAILABLE'),1,False,'NOT_VERIFIED','WRITER_UNVERIFIED'),
        (e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'),1,True,'NOT_VERIFIED','WRITER_PUBLISHED_UNVERIFIED'),
        (e.writer_line('PUBLISHED_UNVERIFIED','MANIFEST_READBACK_FAILED'),3,True,'NOT_VERIFIED','WRITER_PUBLISHED_UNVERIFIED'),
        (e.writer_line('ABSENT','MANIFEST_ABSENT',mode='PUBLISH'),3,False,'NOT_VERIFIED','WRITER_ABSENT'),
        (e.writer_line(),3,True,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),(e.writer_line('REFUSED','MANIFEST_X_Y'),0,False,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),
        (e.writer_line('UNVERIFIED','MANIFEST_UNVERIFIED'),3,False,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),
        (e.writer_line('MATCH_VERIFIED',mode='VERIFY_ONLY'),0,True,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),
        (e.writer_line(mode='VERIFY_ONLY'),0,True,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),
        (e.writer_line('REFUSED','MANIFEST_ARGUMENTS_INVALID',session=None,mode=None),3,False,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT'),
        (e.writer_line(owner_uid=1000),0,True,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'),
        (e.writer_line(capacity_config_sha256='1'*64),0,True,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'),
        (e.writer_line(release_sha256='1'*64),0,True,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'),
        (e.writer_line(package_sha256='1'*64),0,True,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'),
        (e.writer_line(build_sha='a'*40),0,True,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES'),
        (e.writer_line(go_mode='INDIVIDUAL'),0,True,'UNCERTAIN','GO_MODE_NOT_THE_AUTHORISED_ONE'),
        (e.writer_line(manifest_sha256='1'*64),0,True,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS'),
        (e.writer_line(),0,False,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS'),
        (b'',143,False,'UNCERTAIN','ENDED_WITHOUT_A_LINE'),(b'Traceback\n',1,False,'UNCERTAIN','WRITER_LINE_INVALID'),
        (e.writer_line()+e.writer_line(),0,True,'UNCERTAIN','WRITER_LINE_NOT_ONE_LINE')):
        docs,host=window(line,code,publish);verdict(docs,host,expected,reason)

def test_the_code_of_a_line_that_is_not_one():
    for line,exit_code,code in ((b'',143,'ENDED_WITHOUT_A_LINE'),(b'',1,'ENDED_WITHOUT_A_LINE'),(e.writer_line()+e.writer_line(),0,'WRITER_LINE_NOT_ONE_LINE'),
                      (e.writer_line()[:-1],0,'WRITER_LINE_NOT_ONE_LINE'),(b'Traceback\n',1,'WRITER_LINE_INVALID'),
                      (b'{"schema":"\xff"}\n',1,'WRITER_LINE_NOT_ASCII'),(b'[1]\n',1,'WRITER_LINE_INVALID'),
                      (e.writer_line(extra=1),0,'WRITER_LINE_INVALID'),(b'x'*16383+b'\n',1,'WRITER_LINE_INVALID')):
        docs,host=window(line,exit_code,False);receipt=verdict(docs,host,'UNCERTAIN',code)
        assert receipt['items']['persisted']['line_code']==code and receipt['items']['persisted']['line_valid'] is False,(line[:20],code)

@pytest.mark.parametrize('changes',[dict(code='MANIFEST_X_Y'),dict(code='manifest_lower'),dict(code='NOUNDERSCORE'),dict(code=5),
    dict(session='2026-10-07'),dict(mode='OTHER'),dict(release_sha256='xyz'),dict(capacity_config_sha256='0'*64),dict(binding_sha256='A'*64),
    dict(manifest_sha256=None),dict(owner_uid=-1),dict(owner_uid=True),dict(build_sha='dd4ec4bb'),dict(prepare_status='DONE'),dict(go_mode='DELEGATED'),
    dict(symbol_count=551),dict(symbol_count=-1),dict(repaired_temporaries=5000),dict(massive_bars_enabled='yes'),dict(capacity_veto_mode='lower'),
    dict(waited_seconds=1001),dict(waited_seconds='1'),dict(cutoff_at='tomorrow'),dict(published_at=5),dict(view=[]),dict(window='w'),dict(file=None),
    dict(checks=[]),dict(windows='x'),dict(schema='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V2'),dict(status='DONE')])
def test_every_member_of_the_line_in_its_grammar(changes):
    docs,host=window(e.writer_line(**changes),0,True);receipt=verdict(docs,host,'UNCERTAIN','WRITER_LINE_INVALID')
    assert receipt['items']['persisted']['line_code']=='WRITER_LINE_INVALID'

def test_more_of_the_lines_grammar_and_its_public_part():
    docs,host=window(e.writer_line('REFUSED','NOUNDERSCORE'),3,False);verdict(docs,host,'UNCERTAIN','WRITER_LINE_INVALID')
    docs,host=window(e.writer_line()+b'X',0,True);receipt=verdict(docs,host,'UNCERTAIN','WRITER_LINE_NOT_ONE_LINE')
    assert receipt['items']['persisted']['stdout_bytes']==len(e.writer_line())+1
    docs,host=window(e.writer_line('REFUSED','MANIFEST_GO_INVALID'),3,False);receipt=verdict(docs,host,'NOT_VERIFIED','WRITER_REFUSED')
    assert receipt['writer_line']['manifest_sha256_present'] is False and receipt['writer_line']['symbol_count_present'] is False
    assert receipt['binding_may_be_committed'] is False and receipt['items']['persisted']['stdout_bytes']==len(e.writer_line('REFUSED','MANIFEST_GO_INVALID'))
    docs,host=window(e.writer_line('REFUSED','MANIFEST_DATABASE_X',prepare_status='ATTEMPTED'),3,False);receipt=verdict(docs,host,'NOT_VERIFIED','WRITER_REFUSED')
    assert receipt['binding_may_be_committed'] is True
    docs,host=window(e.writer_line('REFUSED','MANIFEST_X_Y',session=None),3,False);verdict(docs,host,'UNCERTAIN','WRITER_RECEIPT_INCONSISTENT')
    for key in ('owner_uid','capacity_config_sha256','release_sha256','package_sha256','build_sha'):
        line=json.loads(e.writer_line());line.pop(key)
        docs,host=window((json.dumps(line,sort_keys=True,separators=(',',':'))+'\n').encode(),0,True);verdict(docs,host,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES')

def test_the_code_of_a_persisted_receipt_that_is_not_one():
    path=e.RECEIPTS+'/k12-2026-10-06-w1.writer.json'
    docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');value=e.persisted(host,K,item)
    host.tree.get(path).content=bytearray(json.dumps(value).encode());receipt=verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')
    assert receipt['items']['persisted']['code']=='PERSISTED_RECEIPT_INVALID'
    docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');e.persisted(host,K,item,stdout_b64='@@')
    receipt=verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID');assert receipt['items']['persisted']['code']=='PERSISTED_RECEIPT_INVALID'

def test_a_refusal_line_has_a_code_and_a_success_none():
    line=json.loads(e.writer_line('REFUSED','MANIFEST_GO_INVALID'));line['code']=None
    docs,host=window((json.dumps(line,sort_keys=True,separators=(',',':'))+'\n').encode(),3,False);verdict(docs,host,'UNCERTAIN','WRITER_LINE_INVALID')
    for key in ('schema','status','code','session','mode'):
        line=json.loads(e.writer_line());line.pop(key)
        docs,host=window((json.dumps(line,sort_keys=True,separators=(',',':'))+'\n').encode(),0,True);verdict(docs,host,'UNCERTAIN','WRITER_LINE_INVALID')

def test_an_inspect_line_with_a_mount_that_is_not_a_bind():
    for change in (dict(Type='volume'),dict(RW='false'),dict(Extra=1)):
        docs,host=docs_for();host.docker.containers[-1]['Mounts'][0].update(change);receipt=verdict(docs,host,'UNCERTAIN','CONTAINER_UNAVAILABLE')
        assert receipt['items']['container']['code']=='K12_INSPECT_INVALID'
    docs,host=docs_for();del host.docker.containers[-1]['Mounts'][0]['Source'];verdict(docs,host,'UNCERTAIN','CONTAINER_UNAVAILABLE')

def test_already_published_reads_no_go_and_a_request_without_the_go_mode_accepts_either():
    docs,host=window(e.writer_line('ALREADY_PUBLISHED_VERIFIED',go_mode='INDIVIDUAL'));verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK')
    body=e.capacity_request(go_mode=None);host=e.world(K)
    item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA,body=body);e.at_view(host,item['Name'][1:],line=e.writer_line(go_mode='INDIVIDUAL'))
    e.persisted(host,K,item,body=body);docs,host=docs_for(host=host,body=body);verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK')

def test_the_manifest_on_the_host():
    docs,host=window(two_links=True);receipt=verdict(docs,host,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS')
    assert receipt['items']['manifest']['links']==2 and receipt['items']['manifest']['temporaries']==1
    docs,host=window();host.tree.get(e.MANIFESTS+'/2026-10-06.json').mode=0o644;verdict(docs,host,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS')
    docs,host=window();host.tree.get(e.MANIFESTS+'/2026-10-06.json').uid=1000;verdict(docs,host,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS')
    docs,host=window();host.tree.get(e.MANIFESTS+'/2026-10-06.json').content=bytearray(e.MANIFEST_BYTES+b' ')
    receipt=verdict(docs,host,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS');assert receipt['manifest_sha256_equals_the_line'] is False
    docs,host=window();host.tree.remove(e.MANIFESTS+'/2026-10-06.json');host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='symlink')
    verdict(docs,host,'UNCERTAIN','MANIFEST_NOT_AS_THE_LINE_SAYS')
    docs,host=window();host.tree.get(e.MANIFESTS+'/2026-10-06.json').content=bytearray(b'x'*65537)
    receipt=verdict(docs,host,'UNCERTAIN','MANIFEST_UNAVAILABLE');assert receipt['items']['manifest']['code']=='FILE_TOO_LARGE'
    docs,host=window()
    for name in ('2026-10-05.json','.2026-10-05.json.%s.tmp'%('ab'*8),'.2026-10-06.json.%s.tmp'%('cd'*8),'.2026-10-06.json.x.tmp'):
        host.tree.add(e.MANIFESTS+'/'+name,kind='file',mode=0o600)
    receipt=verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK');assert receipt['items']['manifest']['temporaries']==1

def test_verdicts_from_the_container():
    host=e.world(K);docs,host=docs_for(host=host);receipt=verdict(docs,host,'NOT_VERIFIED','CONTAINER_ABSENT')
    assert receipt['items']['container']=={'present':False,'code':'CONTAINER_ABSENT','status':'COMPLETE'} and receipt['container_id'] is None
    host=e.world(K);host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600);docs,host=docs_for(host=host)
    verdict(docs,host,'UNCERTAIN','MANIFEST_PRESENT_WITHOUT_THIS_WINDOW')
    host=e.world(K);e.launched(host,K,request_sha=k12r.LAUNCH_SHA,state='created');node=host.tree.add(e.MANIFESTS+'/2026-10-06.json',kind='file',mode=0o600)
    node.nlink=2;docs,host=docs_for(host=host);verdict(docs,host,'UNCERTAIN','MANIFEST_PRESENT_WITHOUT_THIS_WINDOW')
    host=e.world(K);docs,host=docs_for(host=host);docs.plan['parent_rows']['manifests'][-1]['inode']+=1;docs.chain()
    verdict(docs,host,'UNCERTAIN','MANIFEST_UNAVAILABLE')
    docs,host=docs_for();host.docker.inspect_returncode=1;receipt=verdict(docs,host,'UNCERTAIN','CONTAINER_UNAVAILABLE')
    assert receipt['items']['container']['code']=='CONTAINER_UNREADABLE'
    docs,host=docs_for();host.docker.inspect_returncode=1;host.docker.ps_returncode=1;receipt=verdict(docs,host,'UNCERTAIN','CONTAINER_UNAVAILABLE')
    assert receipt['items']['container']['code']=='COMMAND_FAILED'
    docs,host=docs_for();host.docker.containers[-1]['State']['Status']='unknown';verdict(docs,host,'UNCERTAIN','CONTAINER_UNAVAILABLE')
    docs,host=docs_for();host.docker.containers[-1]['Config']['Labels']['c3po.k12.request_sha256']='1'*64;verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_OF_THIS_WINDOW')
    docs,host=docs_for();host.docker.containers[-1]['Mounts'].pop();verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_OF_THIS_WINDOW')
    docs,host=docs_for();host.docker.containers[-1]['State'].update(Status='running',Running=True);verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_SETTLED')
    docs,host=docs_for();host.docker.containers[-1]['State'].update(Running=True);verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_SETTLED')
    for state in ('paused','restarting','dead','removing'):
        docs,host=docs_for();host.docker.containers[-1]['State']['Status']=state;verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_SETTLED')
    host=e.world(K);e.launched(host,K,request_sha=k12r.LAUNCH_SHA,state='created');docs,host=docs_for(host=host);verdict(docs,host,'NOT_VERIFIED','NEVER_STARTED')
    docs,host=docs_for();host.docker.containers[-1]['State'].update(Status='created');verdict(docs,host,'UNCERTAIN','CONTAINER_NOT_SETTLED')
    # rev 2: PERSIST keeps nothing of a stop; the stopped container itself (inspect) is the verdict
    host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.do_stop(['-t','5',item['Id']])
    docs,host=docs_for(host=host);receipt=verdict(docs,host,'STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW')
    assert receipt['exit_code']==143 and receipt['manifest_on_host']=={'present':False,'private_one_link':False} and receipt['writer_line'] is None
    for code,oom,finished in ((143,True,'2026-10-06T10:41:30Z'),(3,False,'2026-10-06T10:41:30Z'),(143,False,'2026-10-06T10:45:00Z'),(137,False,'x')):
        host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.exit(item,code,b'',oom=oom,finished=finished)
        docs,host=docs_for(host=host);verdict(docs,host,'PENDING_PERSIST','LINE_NOT_YET_PERSISTED')
    host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.exit(item,137,b'',finished='2026-10-06T10:44:59.9Z')
    docs,host=docs_for(host=host);verdict(docs,host,'STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW')
    host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.do_stop(['-t','5',item['Id']])
    docs,host=docs_for(host=host);host.tree.get(e.RECEIPTS).mode=0o755;docs.plan['parent_rows']['receipts'][-1]['mode']=0o755;docs.chain()
    assert refusal(docs)=='DIRECTORY_NOT_ROOT_PRIVATE'

def test_verdicts_from_the_persisted_receipt():
    docs,host=window(persist=False);receipt=verdict(docs,host,'PENDING_PERSIST','LINE_NOT_YET_PERSISTED')
    assert receipt['exit_code']==0 and receipt['manifest_on_host']=={'present':True,'private_one_link':True} and receipt['writer_line'] is None
    path=e.RECEIPTS+'/k12-2026-10-06-w1.writer.json'
    docs,host=window();host.tree.get(path).mode=0o640;verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_NOT_PRIVATE')
    docs,host=window();host.tree.get(path).nlink=2;verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_NOT_PRIVATE')
    docs,host=window();host.tree.get(path).content=bytearray(b'{"a":1}');receipt=verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')
    assert receipt['items']['persisted']['code']=='PERSISTED_RECEIPT_INVALID'
    docs,host=window();host.tree.remove(path);host.tree.add(path,kind='symlink');verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_UNAVAILABLE')
    for change in (dict(window='contingency_1'),dict(window_slot=2),dict(container_name='c3po-k12-20261006-w2'),dict(launch_request_sha256='1'*64),
                   dict(capacity_request_sha256='1'*64),dict(image_id=hostemu.OTHER),dict(epoch='R2D2-V2-SHADOW-2026-09-28'),
                   dict(schema='K12_PERSISTED_WRITER_RECEIPT_V2'),dict(stdout_sha256='1'*64),dict(stdout_bytes=3),dict(stdout_b64='@@'),
                   dict(exit_code='0'),dict(oom_killed=0),dict(persist_request_sha256='0'*64),dict(container_id='A'*64)):
        docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');e.persisted(host,K,item,**change)
        verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')
    for change in (dict(container_id='ab'*32),dict(exit_code=3),dict(oom_killed=True),dict(finished_at='2026-10-06T10:45:05Z'),dict(started_at='x')):
        docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');e.persisted(host,K,item,**change)
        verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_NOT_OF_THIS_CONTAINER')
    docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');value=e.persisted(host,K,item)
    raw=bytes(host.tree.get(path).content);host.tree.get(path).content=bytearray(json.dumps(value).encode());verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')
    docs,host=window(persist=False);item=host.docker.container('c3po-k12-20261006-w1');value=e.persisted(host,K,item)
    host.tree.get(path).content=bytearray(f.canonical(dict(value,day='2026-10-07')));verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')
    host.tree.get(path).content=bytearray(f.canonical(dict(value,extra=1)));verdict(docs,host,'UNCERTAIN','PERSISTED_RECEIPT_INVALID')

def test_a_window_stopped_before_its_view_decides_the_day():
    host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.do_stop(['-t','5',item['Id']]);e.persisted(host,K,item)
    docs,host=docs_for(host=host);receipt=verdict(docs,host,'STOPPED_BEFORE_THE_VIEW','STOPPED_WITHOUT_A_LINE')
    assert receipt['exit_code']==143 and receipt['items']['persisted']['ended']=='STOPPED' and receipt['writer_line'] is None
    for code,oom,finished,reason in ((143,True,'2026-10-06T10:41:30Z','ENDED_WITHOUT_A_LINE'),(1,False,'2026-10-06T10:41:30Z','ENDED_WITHOUT_A_LINE'),
                                     (143,False,'2026-10-06T10:45:00Z','ENDED_WITHOUT_A_LINE'),(137,False,'2026-10-06T10:44:59.9Z','STOPPED'),
                                     (143,False,'garbage','ENDED_WITHOUT_A_LINE')):
        host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.exit(item,code,b'',oom=oom,finished=finished);e.persisted(host,K,item)
        docs,host=docs_for(host=host)
        if reason=='STOPPED':verdict(docs,host,'STOPPED_BEFORE_THE_VIEW','STOPPED_WITHOUT_A_LINE')
        else:verdict(docs,host,'UNCERTAIN',reason)

def test_a_stopped_contingency_is_judged_at_its_own_view():
    for finished,expected in (('2026-10-06T11:41:30Z',('STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW')),('2026-10-06T11:45:00Z',('PENDING_PERSIST','LINE_NOT_YET_PERSISTED'))):
        host=e.world(K);item=e.launched(host,K,index=2,request_sha=k12r.LAUNCH_SHA,body=e.capacity_request(index=2))
        host.docker.exit(item,143,b'',finished=finished)
        docs,host=docs_for(host=host,now=e.utc(e.DAY,'11:46:30'),body=e.capacity_request(index=2));verdict(docs,host,*expected)

def test_the_empty_list_is_terminal_only_with_the_signed_pins_and_no_manifest():
    docs,host=window(e.writer_line(**e.EMPTY_LIST),3,True);verdict(docs,host,'UNCERTAIN','MANIFEST_PRESENT_WITH_AN_EMPTY_LIST')
    docs,host=window(e.writer_line(**dict(e.EMPTY_LIST,capacity_config_sha256='1'*64)),3,False);verdict(docs,host,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES')
    docs,host=window(e.writer_line(**dict(e.EMPTY_LIST,owner_uid=7)),3,False);verdict(docs,host,'UNCERTAIN','LINE_PINS_NOT_THE_SIGNED_ONES')
    line=json.loads(e.writer_line(**e.EMPTY_LIST))
    for key in ('release_sha256','package_sha256','build_sha','capacity_config_sha256','owner_uid'):line.pop(key)
    raw=(json.dumps(line,sort_keys=True,separators=(',',':'))+'\n').encode();docs,host=window(raw,3,False);verdict(docs,host,'TERMINAL_EMPTY_LIST','MANIFEST_SYMBOLS_EMPTY')
    docs,host=window(e.writer_line(**e.EMPTY_LIST),3,False);docs.plan['parent_rows']['manifests'][-1]['inode']+=1;docs.chain()
    verdict(docs,host,'UNCERTAIN','MANIFEST_UNAVAILABLE')

def test_a_contingency_window_is_collected_by_its_own_name():
    host=e.world(K);first=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.exit(first,3,e.writer_line('REFUSED','MANIFEST_GO_INVALID'))
    e.persisted(host,K,first)
    docs,host=window(index=2,host=host);receipt=verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK');assert receipt['container_name']=='c3po-k12-20261006-w2'

def test_directories_that_move_during_the_read_and_a_run_that_expires():
    docs,host=docs_for()
    def hook(host,name,detail,calls):
        if name=='names':host.tree.get(e.RECEIPTS).mode=0o755
    host.hook=hook;receipt=docs.run(host)
    assert receipt['findings']==['DIRECTORIES_NOT_STABLE'] and receipt['status']==M.PARTIAL_STATUS and receipt['window_verdict']=='VERIFIED'
    assert receipt['items']['directories_stable']['code']=='PARENT_REPLACED'
    docs,host=docs_for();budget=f.Budget(docs.now).attach(host);budget.cost(61,'container','inspect');receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['window_verdict'])==(M.PARTIAL_STATUS,M.ESCAPED_OUTCOME,'GO_EXPIRED','UNCERTAIN')
    docs,host=docs_for();docs.plan['parent_rows']['receipts'][-1]['inode']+=1;docs.chain();receipt=run(docs,host)
    assert receipt['items']['directory:receipts']['code']=='PARENT_IDENTITY_MISMATCH' and receipt['items']['persisted']['code']=='DIRECTORY_NOT_HELD'
    assert receipt['window_verdict']=='UNCERTAIN' and receipt['window_reason']=='PERSISTED_RECEIPT_UNAVAILABLE'
    docs,host=docs_for();docs.plan['parent_rows']['manifests'][-1]['inode']+=1;docs.chain();receipt=run(docs,host)
    assert receipt['items']['manifest']['code']=='DIRECTORY_NOT_HELD' and receipt['window_reason']=='MANIFEST_UNAVAILABLE'


# ---------------------------------------------------------------- TREE
def test_tree_reads_the_rows_a_binder_copies():
    docs,host=docs_for('TREE');receipt=run(docs,host);assert (receipt['status'],receipt['outcome'])==(M.COMPLETE_STATUS,M.COMPLETE_OUTCOME)
    rows=receipt['observed_rows']
    for name,path in (('capacity_root',e.CAPACITY),('config',e.CONFIG),('manifests',e.MANIFESTS),('reader_config',e.READER),('docker_cli',e.DOCKER_CLI),
                      ('journal',e.JOURNAL),('data',e.RELEASE),('receipts',e.RECEIPTS)):
        assert rows[name]==e.rows(host,path),name
    assert receipt['boot_id_sha256']==f.BOOT_SHA and host.commands==[] and receipt['findings']==[]
    assert receipt['items']['files']=={'secret.env':{'present':True,'private':True},'pins.env':{'present':True,'private':True},
                                       'epoch.json':{'present':True,'private':True},'maintenance.lock':{'present':True,'private':True},
                                       'release.CERTIFIED.json':{'present':True,'private':True},
                                       'docker_cli_entries':0,'status':'COMPLETE'}
    # the rows of TREE make requests of the three families that authenticate
    docs2,_=docs_for(host=host);docs2.plan['parent_rows']={key:rows[key] for key in ('manifests','receipts','data')};docs2.chain();docs2.authenticate()

@pytest.mark.parametrize('action,finding',[
    (lambda host:setattr(host.tree.get(e.CONFIG),'mode',0o755),'DIRECTORY_NOT_ROOT_PRIVATE:config'),
    (lambda host:setattr(host.tree.get(e.RECEIPTS),'uid',1000),'DIRECTORY_NOT_ROOT_PRIVATE:receipts'),
    (lambda host:setattr(host.tree.get('/var/lib/c3po-reader'),'mode',0o777),'CHAIN_ROW_UNSAFE:receipts'),
    (lambda host:setattr(host.tree.get('/etc/c3po-bar'),'uid',1000),'CHAIN_ROW_UNSAFE:manifests'),
    (lambda host:setattr(host.tree.get('/var/lib'),'gid',1000),'CHAIN_NOT_ROOT_CONTROLLED:receipts'),
    (lambda host:setattr(host.tree.get('/mnt'),'gid',1000),'CHAIN_NOT_ROOT_CONTROLLED:data'),
    (lambda host:setattr(host.tree.get('/var'),'mode',0o2755),'CHAIN_NOT_ROOT_CONTROLLED:capacity_root'),
    (lambda host:setattr(host.tree.get(e.JOURNAL),'gid',4),'CHAIN_NOT_ROOT_CONTROLLED:journal'),
    (lambda host:setattr(host.tree.get(e.READER+'/secret.env'),'mode',0o644),'FILE_NOT_ROOT_PRIVATE:secret.env'),
    (lambda host:setattr(host.tree.get(e.READER+'/pins.env'),'uid',1000),'FILE_NOT_ROOT_PRIVATE:pins.env'),
    (lambda host:host.tree.remove(e.JOURNAL+'/epoch.json'),'FILE_NOT_ROOT_PRIVATE:epoch.json'),
    (lambda host:setattr(host.tree.get(e.JOURNAL+'/maintenance.lock'),'nlink',2),'FILE_NOT_ROOT_PRIVATE:maintenance.lock'),
    (lambda host:host.tree.add(e.DOCKER_CLI+'/config.json',kind='file'),'DOCKER_CLI_DIRECTORY_NOT_EMPTY'),
    (lambda host:(host.tree.remove(e.READER+'/secret.env'),host.tree.add(e.READER+'/secret.env',kind='dir',mode=0o600)),'FILE_NOT_ROOT_PRIVATE:secret.env'),
    (lambda host:setattr(host.tree.get(e.RELEASE),'mode',0o777),'CHAIN_ROW_WORLD_WRITABLE:data'),
    (lambda host:setattr(host.tree.get(e.RELEASE),'uid',1000),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE:data'),
    (lambda host:setattr(host.tree.get(e.RELEASE),'mode',0o755),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE:data'),
    (lambda host:setattr(host.tree.get(e.DATA),'mode',0o777),'CHAIN_ROW_WORLD_WRITABLE:data'),
    (lambda host:setattr(host.tree.get(e.DATA),'dev',801),'DATA_VOLUME_NOT_A_MOUNT_POINT:data'),
    (lambda host:setattr(host.tree.get('/mnt'),'uid',1000),'CHAIN_ROW_UNSAFE:data'),
    (lambda host:setattr(host.tree.get('/mnt'),'mode',0o2755),'CHAIN_NOT_ROOT_CONTROLLED:data'),
    (lambda host:setattr(host.tree.get(e.RELEASE+'/release.CERTIFIED.json'),'mode',0o644),'FILE_NOT_ROOT_PRIVATE:release.CERTIFIED.json')])
def test_tree_findings(action,finding):
    docs,host=docs_for('TREE');action(host);receipt=run(docs,host)
    assert finding in receipt['findings'] and (receipt['status'],receipt['outcome'])==(M.PARTIAL_STATUS,M.PARTIAL_OUTCOME)

def test_tree_reads_of_the_data_volume_are_the_release_directory_only():
    """Codex #429 5986698996: no other tree of the volume is read (the walk goes / -> mnt -> day-d-data -> the release
    directory; only the release file is looked at, by lstat)."""
    docs,host=docs_for('TREE');receipt=run(docs,host);assert receipt['findings']==[] and receipt['status']==M.COMPLETE_STATUS
    names=[str(entry) for entry in host.log if 'provider=synthetic' in str(entry) or 'lost+found' in str(entry) or '.r2d2-v2-pinned' in str(entry)]
    assert names==[],names

def test_collect_reads_the_release_and_refuses_a_change():
    docs,host=docs_for();receipt=verdict(docs,host,'VERIFIED','PUBLISHED_AND_READ_BACK');assert receipt['items']['release']=={'as_signed':True,'status':'COMPLETE'}
    for action,reason in ((lambda host:host.tree.get(e.RELEASE+'/release.CERTIFIED.json').content.extend(b' '),'RELEASE_NOT_THE_SIGNED_BYTES'),
                          (lambda host:host.tree.remove(e.RELEASE+'/release.CERTIFIED.json'),'RELEASE_NOT_THE_SIGNED_BYTES'),
                          (lambda host:setattr(host.tree.get(e.RELEASE+'/release.CERTIFIED.json'),'mode',0o644),'RELEASE_NOT_THE_SIGNED_BYTES')):
        docs,host=docs_for();action(host);receipt=verdict(docs,host,'UNCERTAIN',reason)
    docs,host=docs_for();host.tree.get(e.RELEASE+'/release.CERTIFIED.json').content=bytearray(b'x'*1048577)
    receipt=verdict(docs,host,'UNCERTAIN','RELEASE_NOT_THE_SIGNED_BYTES');assert receipt['items']['release']['code']=='FILE_TOO_LARGE'
    docs,host=docs_for();docs.plan['parent_rows']['data'][-1]['inode']+=1;docs.chain();receipt=run(docs,host)
    assert receipt['items']['release']['code']=='DIRECTORY_NOT_HELD' and receipt['window_reason']=='RELEASE_UNAVAILABLE'
    host=e.world(K);item=e.launched(host,K,request_sha=k12r.LAUNCH_SHA);host.docker.do_stop(['-t','5',item['Id']])
    host.tree.remove(e.RELEASE+'/release.CERTIFIED.json');docs,host=docs_for(host=host);verdict(docs,host,'STOPPED_BEFORE_THE_VIEW','STOPPED_BEFORE_ITS_VIEW')

def test_collect_data_chain():
    for index,change,code in ((-1,dict(mode=0o755),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE'),(1,dict(gid=4),'CHAIN_NOT_ROOT_CONTROLLED'),
                              (2,dict(device=801),'DATA_VOLUME_NOT_A_MOUNT_POINT'),(2,dict(mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
                              (0,dict(uid=1000),'CHAIN_ROW_UNSAFE'),(-1,dict(path='/x'),'CHAIN_ROW_INVALID')):
        docs,_=docs_for();docs.plan['parent_rows']['data'][index].update(change);docs.chain();assert refusal(docs)==code,(index,change)

def test_tree_links_and_absences_are_unavailable_items():
    docs,host=docs_for('TREE');host.tree.remove(e.RECEIPTS);host.tree.add(e.RECEIPTS,kind='symlink');receipt=run(docs,host)
    assert receipt['items']['directory:receipts']['code']=='SYMLINK_COMPONENT' and receipt['observed_rows']['receipts'] is None and receipt['status']==M.PARTIAL_STATUS
    docs,host=docs_for('TREE');host.tree.remove(e.READER+'/docker-cli');receipt=run(docs,host)
    assert receipt['items']['files']['code']=='DIRECTORY_NOT_HELD' and receipt['items']['directory:docker_cli']['status']=='UNAVAILABLE'
    docs,host=docs_for('TREE',journal='/srv/journal');receipt=run(docs,host)
    assert receipt['items']['directory:journal']['status']=='UNAVAILABLE' and receipt['status']==M.PARTIAL_STATUS


# ---------------------------------------------------------------- the fixed words
def test_the_only_command_is_the_inspect_of_this_family():
    assert set(M.COMMANDS)=={'inspect','container_list'} and M.COMMANDS['inspect']['argv']==['container','inspect','--format',M.K12_FORMAT]
    assert M.COMMANDS['container_list']['argv']==['ps','-a','--no-trunc','--format',M.PS_FORMAT] and M.COMMANDS['container_list']['kind']=='READ'
    assert M.COMMANDS['inspect']['kind']=='READ' and M.COMMANDS['inspect']['class']=='QUICK' and 'Env' not in M.K12_FORMAT
    assert M.WRITES_ALLOWED is False and M.DATE_CLASS=='READ' and M.MAX_GATE_SPAN_SECONDS==3600
