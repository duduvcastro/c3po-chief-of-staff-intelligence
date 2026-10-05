"""K8 (E6, the eve delivery) end to end on the emulated host: the literal effects the signers see, the three synthetic
days (four names, the capacity of 550, an empty list), every refusal with its code and the proof that nothing changed,
hostile states after the precheck, every point at which the process can die and what a later read finds there, expiry
at every gate, and what the receipt says and never says. Synthetic and in memory: no SSH, no host, no credential, no
docker binary, no GO. The documents are the real tool's output over synthetic inputs (tests/k8.py)."""
import copy
from datetime import timedelta
import errno
import json
import os

import pytest

import family as f
import hostemu
import k8

DAY,FULL,EMPTY,WINDOWS,CAPACITY,DAYS=k8.DAY,k8.FULL,k8.EMPTY,k8.WINDOWS,k8.CAPACITY,k8.DAYS
ROOT=hostemu.ROOT_DEVICE
def fresh(**options):
    docs,host=k8.case(**options);return docs.k.m,docs,host
def refused_untouched(receipt,host,before,code,phase='PRECHECK'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,phase),receipt['code']
    assert k8.state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run']==0 and receipt['delivered'] is None and host.fds=={} and host.commands==[] and f.sealed(receipt)
def partial(receipt,code,left):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION',code,'EFFECTS'),receipt['code']
    assert receipt['objects_left_by_this_run']==left and receipt['delivered'] is None and receipt['readback'] is None and f.sealed(receipt)
def on(event,path,action,once=True):
    """A hook that runs action(host) right before the first (or every) call `event` on `path`."""
    done=[False]
    def hook(host,name,detail,calls):
        if name==event and detail and detail[0]==path and not (once and done[0]):
            done[0]=True;action(host)
    return hook
def day_path(*parts):return '/'.join((DAYS,DAY)+parts)
TABLE=k8.names()
PATHS=[k8.path_of(root,name) for _,root,name in TABLE]
PAYLOAD=PATHS[-1]
def temporary(docs,index):return k8.path_of(TABLE[index][1],'.hostops-%s-%d.partial'%(docs.go16(),index))
def no_symbol_in(receipt,day=DAY):
    """No instrument name and no hash or size of the payload file in a receipt (the commitment's digest is the public
    causal scope of the contract and of the publication record; it may appear)."""
    text=json.dumps(receipt,sort_keys=True);payload=k8.payload_of(day)
    for name in k8.symbols_of(day):assert '"%s"'%name not in text,name
    for value in (f.sha(payload),f.sha(k8.audit_of(day))):assert value not in text
    assert '"bytes":%d'%len(payload) not in text.replace(' ','')
    return True


# ---------------------------------------------------------------- the complete run
def expected_effects(plan,day=DAY):
    files=k8.files_of(day);contract=files['contract'];config=json.loads(files['capacity_config:'+WINDOWS[0]])
    payload=CAPACITY+'/payload/session=%s.json'%day
    return {'operation':'GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01','epoch':'R2D2-V2-SHADOW-2026-10-05','day':day,
            'eve':{'not_before':k8.EVE[day]+'T20:00:00+00:00','not_after':day+'T09:00:00+00:00'},'windows':WINDOWS,
            'capacity_tree':{'path':CAPACITY,'parent':'/var/lib','roots':{root:CAPACITY+'/'+root for root in k8.ROOTS},
                             'required':'EXISTING_DIRECTORY_NOT_A_LINK_UID_0_GID_0_MODE_0700_HELD_UNCHANGED','container_path':'/c3po-capacity'},
            'files':[{'key':key,'path':k8.path_of(root,name),'sha256':f.sha(files[key]),'bytes':len(files[key]),'mode_octal':'0600','uid':0,'gid':0,
                      'links':1,'expect':'ABSENT'} for key,root,name in k8.names(day)[:-1]],
            'contract':{'sha256':f.sha(contract),'bytes':len(contract),'written_as_its_own_file':False,'carried_whole_into':payload},
            'payload':{'path':payload,'mode_octal':'0600','uid':0,'gid':0,'links':1,'expect':'ABSENT','bytes':'CANONICAL_JSON_OF_CONTRACT_AND_CAUSAL_ASSEMBLED_ON_THE_HOST',
                       'causal_members':['commitment_sha256','epoch','list_sha256','session','status','symbols'],
                       'hash_and_size':'NOT_SIGNED_NOT_REPORTED_A_COMMITMENT_TO_THE_LIST'},
            'causal_scope':{'commitment_sha256':k8.FIXTURES['days'][day]['commitment_sha256'],'list_sha256':k8.FIXTURES['days'][day]['list_sha256']},
            'k9_inputs':{'days_parent':{'path':DAYS,'row':plan['days_parent'][-1],'chain_sha256':f.sha(f.canonical(plan['days_parent'])),
                                        'mount_point_by_device_change':'/'},
                         'day_directory':DAYS+'/'+day,'commit_receipt':DAYS+'/'+day+'/receipts/commit_launch.RECEIPT.json',
                         'commitment':DAYS+'/'+day+'/causal/commitment.private.json','audit_receipt':DAYS+'/'+day+'/causal/build_audit_receipt.json',
                         'commit_attempt_key':k8.attempt_key(day),'required':'COMPLETE_RECEIPT_OF_THIS_STEP_NAMING_BOTH_FILES_BY_SHA256'},
            'chain_documents':{role:{'path':CAPACITY+'/documents/'+pin['file'],'sha256':pin['sha256'],'required':'PRESENT_ROOT_0600_THESE_BYTES'}
                               for role,pin in config['document_pins'].items() if ':' not in role and role!='TEMPLATE'},
            'root_identities':{'rule':plan['identity_rule'],'pinned':{root:config['roots'][root]['identity'] for root in ('documents','go','payload')}},
            'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,'activation':False,
            'container_touched':False,'process_started':False,'symbols_in_receipt':False}

def test_complete_run_and_the_literal_effects_the_signers_see():
    m,docs,host=fresh();plan=docs.plan;before=k8.state_of(host)
    assert docs.go['effects']==docs.authority['effects']==expected_effects(plan)
    assert len(docs.go['effects']['chain_documents'])==7 and docs.go['success_criterion']=='EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK'
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['readback'])==(
        m.COMPLETE_STATUS,'EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK',None,'EFFECTS','COMPLETE')
    assert receipt['mutating_calls']=={'issued':52,'succeeded':52,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==13
    assert receipt['pre_existing_objects_modified'] is False and receipt['activation_performed'] is False
    files=k8.files_of();contents=[files[key] for key,_,_ in TABLE[:-1]]+[k8.payload_of()]
    for path,content in zip(PATHS,contents):
        node=host.tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,node.dev,node.synced)==('file',0,0,0o600,1,ROOT,True),path
        assert bytes(node.content)==content,path
    for path in PATHS:host.tree.remove(path)
    assert k8.state_of(host)==before,'nothing else changed'
    assert [entry[:2] for entry in host.mutating()]==[step for index,path in enumerate(PATHS) for step in
        (('create',temporary(docs,index)),('write',temporary(docs,index)),('link',temporary(docs,index)),('unlink',temporary(docs,index)))]
    assert all(entry[3]==0o600 for entry in host.log if entry[0]=='create') and host.mask==0o077
    create=[entry for entry in host.log if entry[0]=='create'][0]
    assert create[2]&(os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW)==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW
    assert [entry[1:] for entry in host.log if entry[0]=='link']==[(temporary(docs,index),path) for index,path in enumerate(PATHS)]
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[item for index,(_,root,_) in enumerate(TABLE) for item in
                                                                    (temporary(docs,index),CAPACITY+'/'+root,CAPACITY+'/'+root)]
    assert host.commands==[] and host.fds=={} and not [entry for entry in host.log if entry[0] in ('run','flock','pause','readlink','mkdir')]
    assert receipt['delivered']=={'epoch':'R2D2-V2-SHADOW-2026-10-05','day':DAY,'windows':WINDOWS,
        'files':{key:{'path':k8.path_of(root,name),'sha256':f.sha(files[key]),'bytes':len(files[key]),'mode_octal':'0600','uid':0,'gid':0,'links':1}
                 for key,root,name in TABLE[:-1]},
        'contract':{'sha256':f.sha(files['contract']),'carried_whole_into_the_payload_file':True},
        'payload':{'path':PAYLOAD,'mode_octal':'0600','uid':0,'gid':0,'links':1,'bytes_equal_the_assembled_bytes':True,'hash_and_size_withheld':True},
        'causal':{'commitment_is_the_commit_receipt_output':True,'commitment_and_list_are_the_contract_causal_scope':True,'list_empty':False},
        'root_identities_equal_the_config':{'documents':True,'go':True,'payload':True},'identity_rule':'REFUSE_ON_MISMATCH'}
    rows=receipt['ledger'];assert [row['key'] for row in rows]==[key for key,_,_ in TABLE] and all(row['state']=='INSTALLED_DURABLE' for row in rows)
    assert all(row['sha256_signed']==row['sha256_observed']==f.sha(content) for row,content in zip(rows[:-1],contents[:-1]))
    assert (rows[-1]['bytes'],rows[-1]['sha256_signed'],rows[-1]['sha256_observed'],rows[-1]['hash_and_size_withheld'])==(None,None,None,True)
    assert receipt['parent']==plan['days_parent'] and receipt['precheck']['destinations_present']==[] and receipt['precheck']['free_bytes']==145315507*4096
    assert receipt['precheck']['identities_equal']=={'documents':True,'go':True,'payload':True} and receipt['precheck']['seconds_left_before_first_effect']==60
    assert set(receipt['precheck']['capacity'])=={'c3po-capacity','config','documents','go','payload'} and set(receipt['precheck']['k9'])=={
        DAY,'receipts','causal','commit_launch.RECEIPT.json','commitment.private.json','build_audit_receipt.json'} and len(receipt['precheck']['chain'])==7
    assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects']) and receipt['observed_at']==docs.now.isoformat() and no_symbol_in(receipt)
    assert k8.classify(host,docs.go16())=='F00','every file removed above; nothing of the run is left'

def test_the_payload_file_is_what_the_capacity_loader_reads():
    """{contract, causal}: the contract's bytes whole, causal = the six members the loader and the binding read
    (r2d2_v2_capacity_wiring.py derive, r2d2_v2_capacity_authority.py validate_contract), canonical."""
    for day in (DAY,FULL,EMPTY):
        m,docs,host=fresh(day=day);receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS,day
        raw=bytes(host.tree.get(CAPACITY+'/payload/session=%s.json'%day).content);payload=json.loads(raw)
        assert raw==k8.payload_of(day) and m.canonical(payload)==raw and set(payload)=={'contract','causal'}
        assert m.canonical(payload['contract'])==k8.contract_of(day),'the contract, byte for byte'
        causal=payload['causal'];names=k8.symbols_of(day)
        assert causal=={'epoch':'R2D2-V2-SHADOW-2026-10-05','session':day,'status':'AVAILABLE','symbols':names,
                        'list_sha256':f.sha(f.canonical(names)),'commitment_sha256':f.sha(k8.commitment_of(day))}
        scope=payload['contract']['causal_scope']
        assert scope=={key:causal[key] for key in ('epoch','session','commitment_sha256','list_sha256')},'CAPACITY_CAUSAL_SCOPE would pass'
        assert receipt['delivered']['causal']['list_empty'] is (day==EMPTY) and no_symbol_in(receipt,day)
    assert len(k8.symbols_of(FULL))==550 and k8.symbols_of(EMPTY)==[]

def test_one_window_and_two_windows_are_deliveries_of_their_own_sizes():
    for windows in (['primary'],['primary','contingency_1']):
        k=k8.K();host=k8.world(k);docs=f.Docs(k,k8.fields(host,windows=windows),now=k8.moment())
        receipt=docs.run(host);assert receipt['status']==k.m.COMPLETE_STATUS and receipt['objects_left_by_this_run']==7+2*len(windows)
        assert sorted(receipt['delivered']['files'])==sorted(k for k in k8.LAYOUT_KEYS if ':' not in k or k.split(':')[1] in windows)

def test_report_only_delivers_and_says_the_identities_differ_refuse_does_not():
    for rule,code in (('REPORT_ONLY',None),('REFUSE_ON_MISMATCH','CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')):
        for root in ('documents','go','payload'):
            m,docs,host=fresh(rule=rule);host.tree.get(CAPACITY+'/'+root).ino+=1;before=k8.state_of(host);receipt=docs.run(host)
            assert docs.go['effects']['root_identities']['rule']==rule
            if code is None:
                assert receipt['status']==m.COMPLETE_STATUS and receipt['delivered']['root_identities_equal_the_config']=={
                    name:name!=root for name in ('documents','go','payload')} and receipt['delivered']['identity_rule']=='REPORT_ONLY'
            else:refused_untouched(receipt,host,before,code);assert receipt['precheck']['identities_equal'][root] is False
    m,docs,host=fresh(rule='REPORT_ONLY');host.tree.get(CAPACITY).ino+=1;receipt=docs.run(host)
    assert receipt['delivered']['root_identities_equal_the_config']=={'documents':False,'go':False,'payload':False},'the root of the tree is in every identity'

def test_receipt_never_carries_a_name_of_the_list_or_a_hash_that_commits_to_it():
    for day in (DAY,FULL):
        m,docs,host=fresh(day=day);receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and no_symbol_in(receipt,day)
        assert 'symbols' not in receipt and 'symbol_count' not in json.dumps(receipt),'no member named for the list'
    m,docs,host=fresh();host.tree.get(day_path('causal','commitment.private.json')).content=bytearray(b'{"list":["ZZQB"]}')
    receipt=docs.run(host);assert receipt['code']=='COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT' and 'ZZQB' not in json.dumps(receipt)

def test_receipt_that_would_not_fit_is_reduced_by_flagged_steps_and_is_then_never_complete():
    m,docs,host=fresh();receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS
    def again(**padding):
        body={key:value for key,value in receipt.items() if key not in ('metadata_sha256','size_reductions')};body.update(padding);return m.seal(body)
    reduced=again(precheck={'pad':'x'*70000})
    assert (reduced['status'],reduced['outcome'],reduced['size_reductions'],reduced['precheck'])==(m.PARTIAL_STATUS,'RECEIPT_REDUCED_STATE_REQUIRES_READBACK',['PRECHECK_DROPPED'],{'reduced_for_size':True})
    reduced=again(precheck={'pad':'x'*70000},parent=[{'pad':'x'*30000},{'pad':'y'*20000}])
    assert (reduced['size_reductions'],reduced['parent'],reduced['precheck'])==(['PRECHECK_DROPPED','PARENT_REDUCED_TO_COUNT'],2,{'reduced_for_size':True})
    assert f.sealed(reduced) and reduced['ledger']==receipt['ledger'] and reduced['objects_left_by_this_run']==13

def test_source_starts_no_process_and_carries_no_runner_or_lock_part():
    k=k8.K();source=k.source.decode('ascii')
    assert k.report['parts']==['core','parents','files'] and 'NativeRunner' not in source and 'NativeLock' not in source
    assert k.m.Native.__mro__[1:3]==(k.m.NativeRead,k.m.NativeFiles) and not hasattr(k.m,'Commands')
    assert k.m.SCOPE['processes_started']==0 and k.m.WRITES_ALLOWED is True and k.m.ACTIVATION_ALLOWED is False and k.m.DATE_CLASS=='WRITE_SESSIONS'


# ---------------------------------------------------------------- everything is looked at before the first creation
def edit(path,**values):
    def apply(host):
        node=host.tree.get(path)
        for key,value in values.items():setattr(node,key,value)
    return apply
def removed(path):return lambda host:host.tree.remove(path)
def replaced(path,kind='symlink',**values):
    def apply(host):
        host.tree.remove(path);host.tree.add(path,kind=kind,**values)
    return apply
def content(path,data):return edit(path,content=bytearray(data))
def receipt_with(**changes):return content(day_path('receipts','commit_launch.RECEIPT.json'),k8.commit_receipt(**changes))
def receipt_without(key):
    body=json.loads(k8.commit_receipt());del body[key];return content(day_path('receipts','commit_launch.RECEIPT.json'),f.canonical(body))
def commitment_edit(change,rebind_receipt=True):
    """A commitment changed, its bytes canonical again, and (by default) the commit receipt rewritten to name the new
    bytes: so that the check under test is the one that decides."""
    def apply(host):
        body=json.loads(k8.commitment_of());change(body);data=f.canonical(body)
        host.tree.get(day_path('causal','commitment.private.json')).content=bytearray(data)
        if rebind_receipt:host.tree.get(day_path('receipts','commit_launch.RECEIPT.json')).content=bytearray(k8.commit_receipt(commitment=data))
    return apply
def audit_edit(change):
    def apply(host):
        body=json.loads(k8.audit_of());change(body);data=f.canonical(body)
        host.tree.get(day_path('causal','build_audit_receipt.json')).content=bytearray(data)
        host.tree.get(day_path('receipts','commit_launch.RECEIPT.json')).content=bytearray(k8.commit_receipt(audit=data))
    return apply
def setter(key,value):
    def change(body):body[key]=value
    return change
def payload_setter(key,value):
    def change(body):body['payload'][key]=value
    return change
def other_list(body):
    body['list']=['ZZQA','ZZQB','ZZQ.C','ZZQ-D'];body['list_sha256']=f.sha(f.canonical(body['list']))
def appended(body):
    body['list']=body['list']+['ZZQE'];body['list_sha256']=f.sha(f.canonical(body['list']))
def other_commitment_same_list(body):body['built_at']='2026-10-06T00:31:00+00:00'
def listed(value):
    """The commitment's list replaced and its own list hash made to match, so that only the list check can decide."""
    def change(body):body['list']=value;body['list_sha256']=f.sha(f.canonical(value))
    return change
CHAIN=sorted(k8.FIXTURES['chain'])
PRECHECK_CASES=[
    (edit('/proc/sys/kernel/random/boot_id',content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')),'EVIDENCE_FROM_EARLIER_BOOT'),
    (edit('/var/lib',ino=9999),'PARENT_IDENTITY_MISMATCH'),(edit(DAYS,mode=0o755),'PARENT_IDENTITY_MISMATCH'),(edit(k8.K9,ino=9999),'PARENT_IDENTITY_MISMATCH'),
    (edit(k8.C3PO,uid=0,mode=0o711),'PARENT_IDENTITY_MISMATCH'),(removed(DAYS+'/'+DAY+'/inputs'),None),
    (replaced(DAYS),'PARENT_SYMLINK_COMPONENT'),(removed(k8.K9),'PARENT_MISSING'),
    (removed(CAPACITY+'/go'),'CAPACITY_DIRECTORY_ABSENT'),(replaced(CAPACITY),'CAPACITY_DIRECTORY_NOT_PRIVATE'),
    (replaced(CAPACITY+'/payload',mode=0o777),'CAPACITY_DIRECTORY_NOT_PRIVATE'),(replaced(CAPACITY+'/config',kind='file'),'CAPACITY_DIRECTORY_NOT_PRIVATE'),
    (edit(CAPACITY,mode=0o755),'CAPACITY_DIRECTORY_NOT_PRIVATE'),(edit(CAPACITY+'/documents',mode=0o750),'CAPACITY_DIRECTORY_NOT_PRIVATE'),
    (edit(CAPACITY+'/go',uid=1000),'CAPACITY_DIRECTORY_NOT_PRIVATE'),(edit(CAPACITY+'/payload',gid=1000),'CAPACITY_DIRECTORY_NOT_PRIVATE'),
    (edit(CAPACITY+'/config',mode=0o2700),'CAPACITY_DIRECTORY_NOT_PRIVATE'),(removed(CAPACITY),'CAPACITY_DIRECTORY_ABSENT'),
    (replaced(CAPACITY+'/go',kind='file',mode=0o700),'CAPACITY_DIRECTORY_NOT_PRIVATE'),(replaced(CAPACITY+'/go',mode=0o700),'CAPACITY_DIRECTORY_NOT_PRIVATE'),
    (replaced(day_path('causal'),kind='file',mode=0o700),'K9_DIRECTORY_NOT_PRIVATE'),
    (removed(DAYS+'/'+DAY),'K9_DIRECTORY_ABSENT'),(removed(day_path('causal')),'K9_DIRECTORY_ABSENT'),(removed(day_path('receipts')),'K9_DIRECTORY_ABSENT'),
    (edit(DAYS+'/'+DAY,mode=0o755),'K9_DIRECTORY_NOT_PRIVATE'),(replaced(day_path('causal')),'K9_DIRECTORY_NOT_PRIVATE'),
    (edit(day_path('receipts'),gid=1000),'K9_DIRECTORY_NOT_PRIVATE'),
    (removed(day_path('receipts','commit_launch.RECEIPT.json')),'COMMIT_RECEIPT_ABSENT'),
    (edit(day_path('receipts','commit_launch.RECEIPT.json'),mode=0o644),'K9_FILE_NOT_PRIVATE'),
    (edit(day_path('receipts','commit_launch.RECEIPT.json'),uid=1000),'K9_FILE_NOT_PRIVATE'),
    (edit(day_path('receipts','commit_launch.RECEIPT.json'),nlink=2),'K9_FILE_NOT_PRIVATE'),
    (replaced(day_path('receipts','commit_launch.RECEIPT.json'),mode=0o600),'K9_FILE_NOT_PRIVATE'),
    (replaced(day_path('receipts','commit_launch.RECEIPT.json'),kind='fifo',mode=0o600),'K9_FILE_NOT_PRIVATE'),
    (content(day_path('receipts','commit_launch.RECEIPT.json'),b'not json'),'COMMIT_RECEIPT_INVALID'),
    (content(day_path('receipts','commit_launch.RECEIPT.json'),b'[]'),'COMMIT_RECEIPT_INVALID'),
    (receipt_with(schema='K9_STEP_RECEIPT_V2'),'COMMIT_RECEIPT_INVALID'),(receipt_with(extra=1),'COMMIT_RECEIPT_INVALID'),
    (receipt_without('aggregates'),'COMMIT_RECEIPT_INVALID'),
    (receipt_with(status='FAILED'),'COMMIT_RECEIPT_NOT_COMPLETE'),(receipt_with(code='DEADLINE_REACHED'),'COMMIT_RECEIPT_NOT_COMPLETE'),
    (receipt_with(epoch='R2D2-V2-SHADOW-2026-09-28'),'COMMIT_RECEIPT_NOT_OF_THIS_STEP'),(receipt_with(day='2026-10-07'),'COMMIT_RECEIPT_NOT_OF_THIS_STEP'),
    (receipt_with(phase='components'),'COMMIT_RECEIPT_NOT_OF_THIS_STEP'),(receipt_with(operation='collect_launch'),'COMMIT_RECEIPT_NOT_OF_THIS_STEP'),
    (receipt_with(attempt_key=k8.attempt_key('2026-10-07')),'COMMIT_RECEIPT_NOT_OF_THIS_STEP'),
    (receipt_with(package_sha256='5'*64),'COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE'),(receipt_with(build_sha='6'*40),'COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE'),
    (receipt_with(outputs={}),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT'),(receipt_with(outputs=None),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT'),
    (receipt_with(outputs=[k8.COMMITMENT_KEY,k8.AUDIT_KEY]),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT'),
    (receipt_with(outputs={k8.COMMITMENT_KEY:f.sha(k8.commitment_of())}),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT'),
    (receipt_with(outputs={k8.COMMITMENT_KEY:'0'*64,k8.AUDIT_KEY:f.sha(k8.audit_of())}),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT'),
    (removed(day_path('causal','commitment.private.json')),'COMMITMENT_ABSENT'),(removed(day_path('causal','build_audit_receipt.json')),'COMMITMENT_ABSENT'),
    (edit(day_path('causal','commitment.private.json'),mode=0o640),'K9_FILE_NOT_PRIVATE'),
    (edit(day_path('causal','build_audit_receipt.json'),gid=5),'K9_FILE_NOT_PRIVATE'),
    (commitment_edit(other_list,rebind_receipt=False),'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT'),
    (receipt_with(outputs={k8.COMMITMENT_KEY:f.sha(k8.commitment_of()),k8.AUDIT_KEY:f.sha(b'x')}),'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT'),
    (lambda host:(content(day_path('causal','commitment.private.json'),k8.commitment_of()+b'\n')(host),
                  receipt_with(outputs={k8.COMMITMENT_KEY:f.sha(k8.commitment_of()+b'\n'),k8.AUDIT_KEY:f.sha(k8.audit_of())})(host)),'COMMITMENT_INVALID'),
    (commitment_edit(setter('schema','V2_CAUSAL_LIST_COMMITMENT_V2')),'COMMITMENT_INVALID'),
    (commitment_edit(setter('session','2026-10-07')),'COMMITMENT_NOT_OF_THIS_DAY'),(commitment_edit(setter('epoch','R2D2-V2-SHADOW-2026-09-28')),'COMMITMENT_NOT_OF_THIS_DAY'),
    (commitment_edit(listed(['zzqb'])),'COMMITMENT_LIST_INVALID'),(commitment_edit(listed(['ZZQB','ZZQB'])),'COMMITMENT_LIST_INVALID'),
    (commitment_edit(listed('ZQB')),'COMMITMENT_LIST_INVALID'),(commitment_edit(listed(['ZQ%04d'%i for i in range(551)])),'COMMITMENT_LIST_INVALID'),
    (commitment_edit(listed(['ZZQB',5])),'COMMITMENT_LIST_INVALID'),(commitment_edit(listed(['ZZQB','Z'*21])),'COMMITMENT_LIST_INVALID'),
    (commitment_edit(listed({'ZZQB':1})),'COMMITMENT_LIST_INVALID'),(commitment_edit(setter('list_sha256','7'*64)),'COMMITMENT_LIST_INVALID'),
    (commitment_edit(other_commitment_same_list),'COMMITMENT_NOT_THE_CONTRACT_SCOPE'),(commitment_edit(appended),'COMMITMENT_NOT_THE_CONTRACT_SCOPE'),
    (audit_edit(setter('event_type','r2d2.v2.causal_list_published')),'AUDIT_RECEIPT_NOT_BOUND'),(audit_edit(setter('extra',1)),'AUDIT_RECEIPT_NOT_BOUND'),
    (audit_edit(setter('occurred_at','2026-10-06T00:31:00+00:00')),'AUDIT_RECEIPT_NOT_BOUND'),
    (audit_edit(payload_setter('commitment_sha256','8'*64)),'AUDIT_RECEIPT_NOT_BOUND'),(audit_edit(payload_setter('list_sha256','8'*64)),'AUDIT_RECEIPT_NOT_BOUND'),
    (audit_edit(payload_setter('session','2026-10-07')),'AUDIT_RECEIPT_NOT_BOUND'),(audit_edit(payload_setter('epoch','X')),'AUDIT_RECEIPT_NOT_BOUND'),
    (audit_edit(setter('payload',None)),'AUDIT_RECEIPT_NOT_BOUND'),
    (removed(CAPACITY+'/documents/'+CHAIN[0]),'CHAIN_DOCUMENT_ABSENT'),(edit(CAPACITY+'/documents/'+CHAIN[3],mode=0o644),'CHAIN_DOCUMENT_NOT_PRIVATE'),
    (replaced(CAPACITY+'/documents/'+CHAIN[1]),'CHAIN_DOCUMENT_NOT_PRIVATE'),
    (content(CAPACITY+'/documents/'+CHAIN[6],b'# another document\n'),'CHAIN_DOCUMENT_NOT_AS_PINNED'),
    (lambda host:host.tree.add(PATHS[0],kind='file',mode=0o600,content=b'x'),'DESTINATION_PRESENT'),
    (lambda host:host.tree.add(PATHS[7],kind='symlink',mode=0o777),'DESTINATION_PRESENT'),
    (lambda host:host.tree.add(PATHS[9],mode=0o700),'DESTINATION_PRESENT'),(lambda host:host.tree.add(PAYLOAD,kind='file',mode=0o600),'DESTINATION_PRESENT'),
    (lambda host:setattr(host.vfs[ROOT],'f_bavail',1023),'CAPACITY_FREE_SPACE_BELOW_FLOOR'),(lambda host:setattr(host.vfs[ROOT],'f_frsize',0),'STATVFS_INVALID'),
    (lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),(lambda host:setattr(host,'actor',(0,5)),'EXECUTOR_IDENTITY'),
]
@pytest.mark.parametrize('index',range(len(PRECHECK_CASES)))
def test_every_precheck_refusal_leaves_the_host_exactly_as_it_was(index):
    prepare,code=PRECHECK_CASES[index];m,docs,host=fresh();prepare(host);before=k8.state_of(host);receipt=docs.run(host)
    if code is None:assert receipt['status']==m.COMPLETE_STATUS;return            # a foreign entry beside the K9 files is not this run's concern
    refused_untouched(receipt,host,before,code)
    assert not [entry for entry in host.log if entry[0] in ('mkdir','create','write','link','unlink','fsync')]

def test_a_contract_whose_list_hash_is_not_the_committed_list_is_refused():
    m,docs,host=fresh();body=json.loads(k8.contract_of());body['causal_scope']['list_sha256']=f.sha(f.canonical(['ZZQB']))
    docs.plan['contract']=k8.blob(f.canonical(body));docs.chain();before=k8.state_of(host)
    refused_untouched(docs.run(host),host,before,'LIST_NOT_THE_CONTRACT_SCOPE')

def test_a_held_directory_that_cannot_be_opened_is_a_change_during_the_precheck():
    for path,code in ((CAPACITY+'/go','CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),(day_path('receipts'),'K9_DIRECTORY_CHANGED_DURING_PRECHECK')):
        m,docs,host=fresh();before=k8.state_of(host)
        def hook(host,event,detail,calls,path=path):
            if event=='open' and detail[0]==path:raise OSError(errno.EACCES,'injected')
        host.hook=hook;refused_untouched(docs.run(host),host,before,code)

def test_a_k9_file_is_judged_by_its_lstat_before_it_is_opened():
    """A file that is not private when looked at is refused before it is opened, even if it becomes private at the open."""
    for member,bad,good in (('mode',0o644,0o600),('nlink',2,1),('uid',1000,0),('gid',1000,0)):
        m,docs,host=fresh();path=day_path('receipts','commit_launch.RECEIPT.json');setattr(host.tree.get(path),member,bad);before=k8.state_of(host)
        def hook(host,event,detail,calls,path=path,member=member,good=good):
            if event=='open' and detail[0]==path:setattr(host.tree.get(path),member,good)
        host.hook=hook;receipt=docs.run(host);host.hook=None;setattr(host.tree.get(path),member,bad)
        refused_untouched(receipt,host,before,'K9_FILE_NOT_PRIVATE');assert ('open',path) not in [entry[:2] for entry in host.log],member

def test_a_signed_file_larger_than_the_core_admits_is_refused_from_its_bytes():
    m,docs,host=fresh();data=b'x'*1048577
    assert f.refusal(lambda:m.k8_blob(k8.blob(data),'DELIVERY_FILE_INVALID'))=='DELIVERY_FILE_INVALID'
    assert m.k8_blob(k8.blob(data[:1048576]),'DELIVERY_FILE_INVALID')==data[:1048576]

def test_scope_is_literally_what_the_signers_sign():
    m,docs,host=fresh();scope=m.SCOPE
    assert scope['days']==['2026-10-06','2026-10-07','2026-10-08','2026-10-09'] and scope['eve']=={'from':'D-1T20:00:00+00:00','until':'DT09:00:00+00:00'}
    assert scope['capacity_tree']=={'path':CAPACITY,'roots':['config','documents','go','payload'],'directory_mode_octal':'0700','container_path':'/c3po-capacity',
                                    'identity_roots':['documents','go','payload'],'identity_rules':['REFUSE_ON_MISMATCH','REPORT_ONLY']}
    assert scope['files']['payload']=='session=<day>.json' and scope['files']['mode_octal']=='0600' and scope['files']['max_windows']==3
    assert scope['k9_inputs']=={'days':DAYS,'commitment':'causal/commitment.private.json','audit_receipt':'causal/build_audit_receipt.json',
                                'commit_receipt':'receipts/commit_launch.RECEIPT.json','receipt_outputs':[k8.COMMITMENT_KEY,k8.AUDIT_KEY],
                                'package_sha256':k8.PACKAGE,'build_sha':k8.REVISION}
    assert scope['evidence_operations_required']==['GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'] and scope['processes_started']==0
    assert scope['never'][-2:]==['a symbol in the receipt','the hash or the size of the payload file in the receipt'] and 'a second attempt' in scope['never']
    assert scope['limits']=={'max_seconds':60,'max_gate_span_seconds':900,'receipt_bytes':60000,'delivery_bytes':40960,'commit_receipt_bytes':262144,
                             'commitment_bytes':67108864,'audit_receipt_bytes':65536,'chain_document_bytes':1048576,'payload_bytes':1048576,
                             'free_bytes_floor':4194304,'write_allowance_seconds':15,'capacity':550}
    assert scope['statement']==m.SCOPE_STATEMENT and 'session=<day>.json' in m.SCOPE_STATEMENT and docs.plan['scope']==json.loads(m.canonical(scope))

def test_free_space_floor_is_four_mebibytes_and_one_block_less_refuses():
    m,docs,host=fresh();host.vfs[ROOT].f_bavail=1024;assert docs.run(host)['status']==m.COMPLETE_STATUS
    m,docs,host=fresh();host.vfs[ROOT].f_bavail=1023;assert docs.run(host)['code']=='CAPACITY_FREE_SPACE_BELOW_FLOOR'

def test_every_name_present_is_named_in_the_refusal():
    m,docs,host=fresh();host.tree.add(PATHS[2],kind='file',mode=0o600);host.tree.add(PAYLOAD,kind='file',mode=0o600);receipt=docs.run(host)
    assert receipt['code']=='DESTINATION_PRESENT' and receipt['precheck']['destinations_present']==['go_bar_manifest_record','payload']

def test_order_of_the_precheck():
    m,docs,host=fresh();host.actor=(1000,0);host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');receipt=docs.run(host)
    assert receipt['code']=='EXECUTOR_IDENTITY' and host.log==[],'nothing is looked at, not even the umask is set'
    m,docs,host=fresh(now=k8.moment(hour=17));receipt=docs.run(host);assert receipt['code']=='WINDOW_NOT_IN_THE_EVE_OF_THE_DAY' and host.log==[]
    m,docs,host=fresh();host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');host.tree.get(DAYS).ino+=1
    assert docs.run(host)['code']=='BOOT_ID_INVALID'
    m,docs,host=fresh();host.tree.get(DAYS).ino+=1;host.tree.remove(CAPACITY);assert docs.run(host)['code']=='PARENT_IDENTITY_MISMATCH'
    m,docs,host=fresh();host.tree.remove(CAPACITY+'/payload');host.tree.remove(DAYS+'/'+DAY);assert docs.run(host)['code']=='CAPACITY_DIRECTORY_ABSENT'
    m,docs,host=fresh();host.tree.remove(day_path('receipts'));host.tree.remove(day_path('causal','commitment.private.json'))
    assert docs.run(host)['code']=='K9_DIRECTORY_ABSENT','receipts before causal is used'
    m,docs,host=fresh();content(day_path('receipts','commit_launch.RECEIPT.json'),b'not json')(host);host.tree.remove(day_path('causal'))
    assert docs.run(host)['code']=='K9_DIRECTORY_ABSENT','both K9 directories are held before any K9 file is read'
    m,docs,host=fresh();receipt_with(status='FAILED')(host);host.tree.remove(day_path('causal','commitment.private.json'))
    assert docs.run(host)['code']=='COMMIT_RECEIPT_NOT_COMPLETE','the receipt before the commitment'
    m,docs,host=fresh();commitment_edit(appended)(host);host.tree.remove(CAPACITY+'/documents/'+CHAIN[0])
    assert docs.run(host)['code']=='COMMITMENT_NOT_THE_CONTRACT_SCOPE','the commitment before the chain'
    m,docs,host=fresh();host.tree.remove(CAPACITY+'/documents/'+CHAIN[0]);host.tree.add(PAYLOAD,kind='file',mode=0o600)
    assert docs.run(host)['code']=='CHAIN_DOCUMENT_ABSENT'
    m,docs,host=fresh();host.tree.add(PAYLOAD,kind='file',mode=0o600);host.tree.get(CAPACITY+'/go').ino+=1;host.vfs[ROOT].f_bavail=0
    assert docs.run(host)['code']=='DESTINATION_PRESENT'
    m,docs,host=fresh();host.tree.get(CAPACITY+'/go').ino+=1;host.vfs[ROOT].f_bavail=0;assert docs.run(host)['code']=='CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG'
    m,docs,host=fresh();docs.run(host);calls=[entry[:2] for entry in host.log]
    looked=[calls.index(('lstat',path)) for path in (CAPACITY,DAYS+'/'+DAY,day_path('receipts','commit_launch.RECEIPT.json'),
                                                     day_path('causal','commitment.private.json'),CAPACITY+'/documents/'+CHAIN[0],PATHS[0],PAYLOAD)]
    assert looked==sorted(looked) and looked[-1]<[entry[0] for entry in host.log].index('fstatvfs')<[entry[0] for entry in host.log].index('create')

def test_the_eve_window_is_judged_before_anything_is_looked_at():
    for now,ok in ((k8.moment(hour=20,minute=0),True),(k8.moment(hour=19,minute=59),False),
                   (k8.moment(hour=23,minute=50),True),(k8.moment().replace(day=6,hour=8,minute=55),True),
                   (k8.moment().replace(day=6,hour=8,minute=56),False),(k8.moment().replace(day=6,hour=10,minute=38),False)):
        m,docs,host=fresh(now=now);before=k8.state_of(host);receipt=docs.run(host)
        if ok:assert receipt['status']==m.COMPLETE_STATUS,now
        else:refused_untouched(receipt,host,before,'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY');assert host.log==[],now
    m,docs,host=fresh(day=FULL,now=k8.moment(DAY));before=k8.state_of(host);refused_untouched(docs.run(host),host,before,'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')

def test_the_gate_is_asked_immediately_before_each_thing_the_precheck_looks_at():
    m,docs,host=fresh();plan,real=docs.authenticate();asked=[]
    def gate():
        asked.append(len(host.log));return real()
    receipt=docs.perform(host,gate=gate);assert receipt['status']==m.COMPLETE_STATUS
    targets=[CAPACITY]+[CAPACITY+'/'+root for root in k8.ROOTS]+[DAYS+'/'+DAY,day_path('receipts'),day_path('causal'),
             day_path('receipts','commit_launch.RECEIPT.json'),day_path('causal','commitment.private.json'),day_path('causal','build_audit_receipt.json')]
    targets+=[CAPACITY+'/documents/'+name for name in CHAIN]+PATHS
    for target in targets:
        index=[entry[:2] for entry in host.log].index(('lstat',target));assert index in asked,target
    for target in [CAPACITY]+[CAPACITY+'/'+root for root in k8.ROOTS]+[DAYS+'/'+DAY,day_path('receipts'),day_path('causal')]:
        index=[entry[:2] for entry in host.log].index(('open',target));assert index in asked,('open',target)
    reads=[index for index,entry in enumerate(host.log) if entry[0]=='read' and not entry[1].startswith('/proc/')]
    assert len(reads)>=20 and [index for index in reads if index not in asked]==[]

def test_budget_is_the_last_refusal_before_the_first_creation():
    for elapsed,ok in ((0.0,True),(45.0,True),(45.5,False),(59.0,False)):
        m,docs,host=fresh();before=k8.state_of(host);mono=[0.0];plan,gate=docs.authenticate(monotonic=lambda:mono[0]);mono[0]=elapsed
        receipt=docs.perform(host,gate=gate,monotonic=lambda:mono[0])
        if ok:assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['seconds_left_before_first_effect']==int(60-elapsed)
        else:
            refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');assert [entry[0] for entry in host.log][-1]=='fstatvfs'
    m,docs,host=fresh();before=k8.state_of(host);late=docs.now+timedelta(minutes=4,seconds=50)
    receipt=docs.run(host,clock=lambda:late);refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def test_precheck_failure_of_any_kind_is_a_refusal_with_a_constant_code():
    for name,target,error,code in (('lstat',CAPACITY+'/go',OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                                   ('read',day_path('causal','commitment.private.json'),OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                                   ('open',day_path('receipts','commit_launch.RECEIPT.json'),OSError(errno.EACCES,'injected'),'PRECHECK_OS_ERROR'),
                                   ('fstatvfs',None,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),('umask',None,RuntimeError('injected'),'PRECHECK_FAILED'),
                                   ('read',CAPACITY+'/documents/'+CHAIN[2],RuntimeError('injected'),'PRECHECK_FAILED')):
        m,docs,host=fresh();before=k8.state_of(host)
        def hook(host,event,detail,calls,name=name,target=target,error=error):
            if event==name and (target is None or detail[0]==target):raise error
        host.hook=hook;receipt=docs.run(host);refused_untouched(receipt,host,before,code);assert 'injected' not in json.dumps(receipt)
    # a held directory or a K9 file that is another object when it is opened, or changes while it is read
    for path,code in ((CAPACITY+'/documents','CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),(day_path('causal'),'K9_DIRECTORY_CHANGED_DURING_PRECHECK'),
                      (day_path('receipts','commit_launch.RECEIPT.json'),'K9_FILE_NOT_PRIVATE'),(CAPACITY+'/documents/'+CHAIN[4],'CHAIN_DOCUMENT_NOT_PRIVATE')):
        for change in (lambda node:setattr(node,'ino',node.ino+1000),lambda node:setattr(node,'mode',0o640 if node.kind=='file' else 0o750)):
            m,docs,host=fresh();before=k8.state_of(host);armed=[False]
            def hook(host,event,detail,calls,path=path,change=change):
                if event=='open' and detail[0]==path and not armed[0]:armed[0]=True;change(host.tree.get(path))
            host.hook=hook;receipt=docs.run(host)
            assert (receipt['status'],receipt['code'])==('REFUSED',code) and host.mutating()==[] and host.fds=={},(path,receipt['code'])
    m,docs,host=fresh()
    def grow(host,event,detail,calls):
        if event=='read' and detail[0]==day_path('causal','commitment.private.json'):host.tree.get(detail[0]).mtime+=1
    host.hook=grow;assert docs.run(host)['code']=='FILE_CHANGED_DURING_READ'


# ---------------------------------------------------------------- the plan: refused from its bytes, before any claim
def change(path,value):
    def apply(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return apply
def file_edit(key,data):
    def apply(plan):plan['files'][key]=k8.blob(data)
    return apply
def json_file_edit(key,edit_):
    def apply(plan):
        body=json.loads(k8.raw(plan['files'][key]['content_b64']));edit_(body);plan['files'][key]=k8.blob(f.canonical(body))
    return apply
def contract_edit(edit_):
    def apply(plan):
        body=json.loads(k8.contract_of());edit_(body);plan['contract']=k8.blob(f.canonical(body))
    return apply
def config_pin(label,member,value,window=WINDOWS[0]):
    def edit_(body):body['document_pins'][label][member]=value
    return json_file_edit('capacity_config:'+window,edit_)
def config_pin_all(label,member,value):
    def apply(plan):
        for window in WINDOWS:config_pin(label,member,value,window)(plan)
    return apply
def json_all(edit_):
    def apply(plan):
        for window in WINDOWS:json_file_edit('capacity_config:'+window,edit_)(plan)
    return apply
def config_set(member,value,window=WINDOWS[0]):
    def edit_(body):body[member]=value
    return json_file_edit('capacity_config:'+window,edit_)
def config_root(root,member,value,window=WINDOWS[0]):
    def edit_(body):body['roots'][root][member]=value
    return json_file_edit('capacity_config:'+window,edit_)
def days_rows_of(path):
    def apply(plan):
        host=k8.world();host.tree.add(path) if host.tree.get(path) is None else None;plan['days_parent']=hostemu.rows(host,path)
    return apply
def swap_files(first,second):
    def apply(plan):plan['files'][first],plan['files'][second]=plan['files'][second],plan['files'][first]
    return apply
def other_day_file(key):
    def apply(plan):plan['files'][key]=k8.blob(k8.files_of(FULL)[key])
    return apply
def without_scope_member(body):del body['causal_scope']['list_sha256']
PLAN_CASES=[
    (change(['day'],'2026-10-05'),'DAY_INVALID'),(change(['day'],'2026-10-10'),'DAY_INVALID'),(change(['day'],None),'DAY_INVALID'),
    (change(['day'],'2026-10-07'),'CONTRACT_NOT_OF_THIS_DAY'),(change(['day'],'2026-10-09'),'CONTRACT_NOT_OF_THIS_DAY'),
    (change(['windows'],[]),'WINDOWS_INVALID'),(change(['windows'],None),'WINDOWS_INVALID'),(change(['windows'],WINDOWS+['contingency_3']),'WINDOWS_INVALID'),
    (change(['windows'],['primary','primary']),'WINDOWS_INVALID'),(change(['windows'],['Primary']),'WINDOWS_INVALID'),
    (change(['windows'],['primary','contingency_1']),'DELIVERY_FILES_NOT_THE_LAYOUT'),(change(['windows'],'primary'),'WINDOWS_INVALID'),
    (change(['windows'],['primary','contingency.1','contingency_2']),'WINDOWS_INVALID'),(change(['windows'],{name:1 for name in WINDOWS}),'WINDOWS_INVALID'),
    (change(['windows'],list(reversed(WINDOWS))),None),
    (change(['files'],None),'DELIVERY_FILES_NOT_THE_LAYOUT'),(lambda plan:plan['files'].pop('template'),'DELIVERY_FILES_NOT_THE_LAYOUT'),
    (lambda plan:plan['files'].update(extra=k8.blob(b'x')),'DELIVERY_FILES_NOT_THE_LAYOUT'),
    (change(['files','template','sha256'],'0'*64),'DELIVERY_FILE_INVALID'),(change(['files','template','bytes'],0),'DELIVERY_FILE_INVALID'),
    (change(['files','template','bytes'],True),'DELIVERY_FILE_INVALID'),(change(['files','template','content_b64'],'not base64!'),'DELIVERY_FILE_INVALID'),
    (change(['files','template','content_b64'],None),'DELIVERY_FILE_INVALID'),(change(['files','template','extra'],1),'DELIVERY_FILE_INVALID'),
    (change(['files','template','sha256'],'3'*64),'DELIVERY_FILE_INVALID'),(change(['files','template','bytes'],452),'DELIVERY_FILE_INVALID'),
    (change(['files','template','content_b64'],'\xe9'+k8.b64(b'x')),'DELIVERY_FILE_INVALID'),(change(['files','template'],[]),'DELIVERY_FILE_INVALID'),
    (change(['files','template','bytes'],1048577),'DELIVERY_FILE_INVALID'),
    (lambda plan:plan['files']['template'].update(content_b64=plan['files']['template']['content_b64'][:8]+'\n'+plan['files']['template']['content_b64'][8:]),'DELIVERY_FILE_INVALID'),
    (change(['contract'],None),'CONTRACT_INVALID'),(change(['contract','sha256'],'3'*64),'CONTRACT_INVALID'),
    (lambda plan:plan.update(contract=k8.blob(k8.contract_of()+b'\n')),'CONTRACT_INVALID'),
    (lambda plan:plan.update(contract=k8.blob(b'[]')),'CONTRACT_INVALID'),(contract_edit(lambda body:body.pop('policy')),'CONTRACT_INVALID'),
    (contract_edit(lambda body:body.update(extra=1)),'CONTRACT_INVALID'),
    (contract_edit(lambda body:body['causal_scope'].update(session='2026-10-07')),'CONTRACT_NOT_OF_THIS_DAY'),
    (contract_edit(lambda body:body['causal_scope'].update(epoch='X')),'CONTRACT_NOT_OF_THIS_DAY'),
    (contract_edit(lambda body:body['causal_scope'].update(commitment_sha256='0'*64)),'CONTRACT_NOT_OF_THIS_DAY'),
    (contract_edit(lambda body:body['causal_scope'].update(list_sha256='ABC')),'CONTRACT_NOT_OF_THIS_DAY'),
    (contract_edit(without_scope_member),'CONTRACT_NOT_OF_THIS_DAY'),(contract_edit(lambda body:body['causal_scope'].update(extra='x')),'CONTRACT_NOT_OF_THIS_DAY'),
    (contract_edit(lambda body:body.update(causal_scope=sorted(body['causal_scope']))),'CONTRACT_NOT_OF_THIS_DAY'),(contract_edit(lambda body:body.update(causal_scope=[])),'CONTRACT_NOT_OF_THIS_DAY'),
    (lambda plan:plan.update(contract=k8.blob(k8.contract_of(FULL))),'CONTRACT_NOT_OF_THIS_DAY'),
    (lambda plan:plan['files'].update({'veto_view:primary':k8.blob(b'x'*10700)}),'DELIVERY_TOO_LARGE'),
    (file_edit('capacity_config:primary',b'{}\n'),'CONFIG_INVALID'),(file_edit('capacity_config:primary',b'[]'),'CONFIG_INVALID'),(file_edit('capacity_config:primary',b'not json'),'CONFIG_INVALID'),
    (config_set('document_pins',None),'CONFIG_PINS_INVALID'),(json_file_edit('capacity_config:primary',lambda body:body['document_pins'].pop('ACT_B')),'CONFIG_PINS_INVALID'),
    (json_file_edit('capacity_config:primary',lambda body:body['document_pins'].update(EXTRA={'file':'x.md','sha256':'1'*64})),'CONFIG_PINS_INVALID'),
    (config_pin_all('ACT_B','sha256','0'*64),'CONFIG_PINS_INVALID'),(config_pin_all('ACT_B','file','../x.md'),'CONFIG_PINS_INVALID'),
    (config_pin_all('ACT_B','file','chain/act_b.md'),'CONFIG_PINS_INVALID'),(config_pin_all('B_DUDU','file','session=2026-10-06.json'),'CONFIG_PINS_INVALID'),
    (json_all(lambda body:body['document_pins']['FABLE'].update(extra=1)),'CONFIG_PINS_INVALID'),
    (config_pin('CODEX','sha256','4'*64,window=WINDOWS[2]),'CONFIG_PINS_INVALID'),
    (config_pin('TEMPLATE','sha256','4'*64),'DELIVERY_NOT_CONSISTENT'),(config_pin('GO:admission','file','session=2026-10-06.go-x.md'),'DELIVERY_NOT_CONSISTENT'),
    (config_pin('GO:bar_manifest','sha256','4'*64,window=WINDOWS[1]),'DELIVERY_NOT_CONSISTENT'),
    (config_pin('PUBLICATION:bar_manifest','sha256','4'*64),'DELIVERY_NOT_CONSISTENT'),
    (file_edit('go_admission_record',b'# another record\n'),'DELIVERY_NOT_CONSISTENT'),(file_edit('veto_view:contingency_2',b'# another view\n'),'DELIVERY_NOT_CONSISTENT'),
    (swap_files('veto_view:primary','veto_view:contingency_1'),'DELIVERY_NOT_CONSISTENT'),
    (swap_files('capacity_config:primary','capacity_config:contingency_2'),'DELIVERY_NOT_CONSISTENT'),
    (config_set('veto_views',{}),'DELIVERY_NOT_CONSISTENT'),(other_day_file('template'),'DELIVERY_NOT_CONSISTENT'),
    (config_set('roots',None),'CONFIG_ROOTS_INVALID'),(config_root('go','path','/c3po-capacity/config'),'CONFIG_ROOTS_INVALID'),
    (config_root('payload','identity','0'*64),'CONFIG_ROOTS_INVALID'),
    (json_all(lambda body:body['roots']['go'].update(path='/c3po-capacity/config')),'CONFIG_ROOTS_INVALID'),
    (json_all(lambda body:body['roots']['payload'].update(identity='0'*64)),'CONFIG_ROOTS_INVALID'),(config_root('documents','identity','9'*64,window=WINDOWS[1]),'CONFIG_ROOTS_INVALID'),
    (json_file_edit('capacity_config:primary',lambda body:body['roots'].pop('go')),'CONFIG_ROOTS_INVALID'),
    (json_file_edit('capacity_config:primary',lambda body:body['roots']['go'].update(extra=1)),'CONFIG_ROOTS_INVALID'),
    (json_all(lambda body:body['roots']['go'].update(extra=1)),'CONFIG_ROOTS_INVALID'),
    (json_all(lambda body:body['roots'].update(config={'path':'/c3po-capacity/config','identity':'5'*64})),'CONFIG_ROOTS_INVALID'),
    (file_edit('go_admission',b'{}'),'GO_FILE_INVALID'),(file_edit('go_bar_manifest',b'{"go":[]}'),'GO_FILE_INVALID'),
    (json_file_edit('go_admission',lambda body:body.update(extra=1)),'GO_FILE_INVALID'),
    (json_file_edit('go_admission',lambda body:body['go'].update(day='2026-10-07')),'GO_FILE_NOT_OF_THIS_DAY'),
    (json_file_edit('go_bar_manifest',lambda body:body['go'].update(phase='admission')),'GO_FILE_NOT_OF_THIS_DAY'),
    (json_file_edit('go_bar_manifest',lambda body:body['go'].update(epoch='X')),'GO_FILE_NOT_OF_THIS_DAY'),
    (swap_files('go_admission','go_bar_manifest'),'GO_FILE_NOT_OF_THIS_DAY'),
    (change(['identity_rule'],None),'IDENTITY_RULE_INVALID'),(change(['identity_rule'],'REFUSE'),'IDENTITY_RULE_INVALID'),
    (change(['days_parent'],None),'CHAIN_ROW_INVALID'),(lambda plan:plan['days_parent'].pop(),'CHAIN_ROW_INVALID'),
    (days_rows_of('/var/lib/c3po/r2d2-v2-k9-20261005'),'CHAIN_ROW_INVALID'),(days_rows_of('/var/lib/c3po-capacity'),'CHAIN_ROW_INVALID'),
    (change(['days_parent',2,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['days_parent',3,'mode'],0o775),'CHAIN_ROW_UNSAFE'),
    (change(['days_parent',5,'mode'],0o1777),'CHAIN_ROW_UNSAFE'),(change(['days_parent',4,'gid'],1000),'K9_CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['days_parent',3,'mode'],0o2755),'K9_CHAIN_NOT_ROOT_CONTROLLED'),(change(['days_parent',5,'mode'],0o2700),'K9_CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
]
@pytest.mark.parametrize('index',range(len(PLAN_CASES)))
def test_plan_refusals_are_authentication_refusals_nothing_is_touched_and_no_go_is_claimed(index,tmp_path):
    apply,code=PLAN_CASES[index];m,docs,host=fresh();apply(docs.plan);docs.chain()
    if code is None:
        docs.authenticate();return
    assert f.refusal(docs.authenticate)==code,code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['outcome'])==('REFUSED',code,'AUTHENTICATION','REFUSED_NOTHING_CHANGED')
    assert receipt['mutating_calls']['issued']==0 and f.sealed(receipt)
    dispatch=f.Dispatch(docs,tmp_path);assert f.refusal(dispatch.prepare)==code and not dispatch.claims()

def test_validate_plan_judges_the_signed_bytes_itself():
    m,docs,host=fresh();plan=copy.deepcopy(docs.plan);m.validate_plan(plan)
    plan['files']['template']=k8.blob(b'# another template\n');assert f.refusal(lambda:m.validate_plan(plan))=='DELIVERY_NOT_CONSISTENT'
    plan=copy.deepcopy(docs.plan);plan['contract']=k8.blob(k8.contract_of(FULL));assert f.refusal(lambda:m.validate_plan(plan))=='CONTRACT_NOT_OF_THIS_DAY'

def test_windows_in_another_order_deliver_the_same_files_and_create_them_in_the_signed_order():
    k=k8.K();host=k8.world(k);order=list(reversed(WINDOWS));docs=f.Docs(k,k8.fields(host,windows=order),now=k8.moment())
    receipt=docs.run(host);assert receipt['status']==k.m.COMPLETE_STATUS
    assert [row['key'] for row in receipt['ledger']]==[key for key,_,_ in k8.names(windows=order)]

def test_largest_delivery_still_fits_one_signed_document_and_one_byte_more_is_refused():
    m,docs,host=fresh();used=sum(item['bytes'] for item in docs.plan['files'].values())+docs.plan['contract']['bytes']
    pad=40960-used;view=k8.files_of()['veto_view:primary']
    docs.plan['files']['veto_view:primary']=k8.blob(view+b'#'*pad);docs.chain()
    assert f.refusal(docs.authenticate)=='DELIVERY_NOT_CONSISTENT','the size check passes; the view is no longer the pinned one'
    largest=dict(docs.plan);size=len(f.canonical(dict(docs.request,plan=largest)))
    assert size<=65536-2048,size
    docs.plan['files']['veto_view:primary']=k8.blob(view+b'#'*(pad+1));docs.chain();assert f.refusal(docs.authenticate)=='DELIVERY_TOO_LARGE'

def test_evidence_must_name_the_k9_tree_read_the_rows_were_copied_from():
    m,docs,host=fresh();docs.request['evidence']=[{'role':'PRECHECK','operation':'GO_READONLY_HOSTOPS_PRECHECK_01','receipt_sha256':'a'*64}];docs.chain()
    assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_every_day_with_an_eve_is_accepted_at_its_eve_and_the_day_before_the_class_is_not():
    for day in (DAY,FULL,EMPTY):
        m,docs,host=fresh(day=day);assert docs.run(host)['status']==m.COMPLETE_STATUS,day
    for now in (k8.moment().replace(day=6,hour=1),k8.moment().replace(day=6,hour=8,minute=50)):
        m,docs,host=fresh(now=now);assert docs.run(host)['status']==m.COMPLETE_STATUS,'the eve after 21:00 BRT is UTC day D'
    m,docs,host=fresh(now=k8.moment().replace(day=4,hour=21));assert f.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'


# ---------------------------------------------------------------- hostile states that appear after the precheck
@pytest.mark.parametrize('position',[0,1,6,12])
def test_a_name_that_appears_before_its_link_is_left_alone(position):
    m,docs,host=fresh();path=PATHS[position]
    host.hook=on('link',temporary(docs,position),lambda host:host.tree.add(path,kind='file',uid=1000,gid=1000,mode=0o644,content=b'foreign'));receipt=docs.run(host)
    rows=receipt['ledger'];assert rows[position]['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' and rows[position]['state']=='NOT_CREATED'
    partial(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK',position)
    assert [row['state'] for row in rows]==['INSTALLED_DURABLE']*position+['NOT_CREATED']+['NOT_ATTEMPTED']*(12-position)
    foreign=host.tree.get(path);assert (foreign.uid,bytes(foreign.content))==(1000,b'foreign') and host.fds=={},'what appeared is not touched'

@pytest.mark.parametrize('number,code',[(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR')])
def test_a_creation_the_kernel_refuses_changed_nothing_and_only_the_first_is_a_refusal(number,code):
    m,docs,host=fresh();before=k8.state_of(host)
    def hook(host,name,detail,calls):
        if name=='create':raise OSError(number,'injected')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'EFFECTS') and k8.state_of(host)==before
    for position in (4,12):
        m,docs,host=fresh()
        def at(host,name,detail,calls,position=position):
            if name=='create' and detail[0]==temporary(docs,position):raise OSError(number,'injected')
        host.hook=at;receipt=docs.run(host);partial(receipt,code,position);assert k8.classify(host,docs.go16())=='F%02d'%position

def test_a_root_replaced_between_the_precheck_and_the_first_creation_is_a_refusal():
    for path in (CAPACITY+'/documents',CAPACITY,'/var/lib'):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,path=path):
            if name=='fstatvfs' and not armed[0]:armed[0]=True;host.tree.get(path).ino+=7
        host.hook=hook;before=k8.state_of(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_REPLACED') and host.mutating()==[],path
    m,docs,host=fresh();armed=[False]
    def later(host,name,detail,calls):
        if name=='unlink' and detail[0]==temporary(docs,3) and not armed[0]:armed[0]=True;host.tree.get(CAPACITY+'/go').ino+=7
    host.hook=later;receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',7);assert k8.classify(host,docs.go16())=='F07'

def test_created_file_that_is_not_what_was_signed_is_withdrawn_and_nothing_more_is_created():
    for prepare in (lambda host:setattr(host,'creator',(1000,1000)),lambda host:setattr(host,'creator',(0,1000)),lambda host:setattr(host,'created_device',ROOT+5)):
        m,docs,host=fresh();prepare(host);receipt=docs.run(host)
        partial(receipt,'CREATED_METADATA_MISMATCH',0);assert receipt['ledger'][0]['state']=='NOT_CREATED'
        assert k8.classify(host,docs.go16())=='F00' and host.fds=={}
    m,docs,host=fresh();host.hook=on('create',temporary(docs,9),lambda host:setattr(host,'creator',(0,1000)));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',9);assert k8.classify(host,docs.go16())=='F09'

def test_failures_while_a_file_is_written_withdraw_only_the_temporary_of_this_run():
    def raising(event,number,index):
        def hook(host,name,detail,calls):
            if name==event and detail[0]==hook.target and not hook.done:
                hook.done=True;raise OSError(number,'injected')
        hook.done=False;hook.index=index;return hook
    for event,number,code in (('write',errno.ENOSPC,'FILESYSTEM_FULL'),('fsync',errno.EIO,'FSYNC_FAILED'),('fstat',errno.EIO,'CREATED_STAT_FAILED')):
        for index in (0,5,12):
            m,docs,host=fresh();hook=raising(event,number,index);hook.target=temporary(docs,index);host.hook=hook;receipt=docs.run(host)
            partial(receipt,code,index)
            assert receipt['ledger'][index]['state']=='NOT_CREATED' and k8.classify(host,docs.go16())=='F%02d'%index and host.fds=={},(event,index)
    m,docs,host=fresh();host.write=lambda fd,data:0;receipt=docs.run(host);partial(receipt,'WRITE_INCOMPLETE',0);assert k8.classify(host,docs.go16())=='F00'
    m,docs,host=fresh();original=host.write;host.write=lambda fd,data:original(fd,data[:500]);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and bytes(host.tree.get(PAYLOAD).content)==k8.payload_of()

def test_failures_after_the_link_leave_the_complete_file_and_the_receipt_says_what_is_left():
    for index in (0,12):
        m,docs,host=fresh()
        def hook(host,name,detail,calls,index=index):
            if name=='unlink' and detail[0]==temporary(docs,index):raise OSError(errno.EIO,'injected')
        host.hook=hook;receipt=docs.run(host);partial(receipt,'TEMPORARY_REMOVAL_FAILED',index+2)
        assert receipt['ledger'][index]['state']=='LINKED_TEMPORARY_PRESENT' and k8.classify(host,docs.go16())=='F%02d_LINKED'%(index+1)
    m,docs,host=fresh()
    def last_fsync(host,name,detail,calls):
        if name=='fsync' and detail[0]==CAPACITY+'/payload' and ('unlink',temporary(docs,12)) in [entry[:2] for entry in host.log]:raise OSError(errno.EIO,'injected')
    host.hook=last_fsync;receipt=docs.run(host);partial(receipt,'FSYNC_FAILED',13)
    assert receipt['ledger'][12]['state']=='INSTALLED_NOT_DURABLE' and k8.classify(host,docs.go16())=='F13'
    assert receipt['ledger'][12]['hash_and_size_withheld'] is True and no_symbol_in(receipt)

def test_readback_inside_the_run_catches_what_changed_after_the_files_were_delivered():
    def tamper(path):return lambda host:setattr(host.tree.get(path),'content',bytearray(b'changed'))
    def mode(path):return lambda host:setattr(host.tree.get(path),'mode',0o644)
    def swap_root(host):host.tree.get(CAPACITY+'/config').ino+=11
    def var_lib(host):host.tree.get('/var/lib').mode=0o711
    def k9_day(host):host.tree.get(DAYS+'/'+DAY).mode=0o750
    for action,code in ((tamper(PATHS[0]),'READBACK_HASH_MISMATCH'),(tamper(PAYLOAD),'READBACK_HASH_MISMATCH'),(mode(PATHS[8]),'READBACK_HASH_MISMATCH'),
                        (swap_root,'PARENT_REPLACED'),(var_lib,'PARENT_REPLACED'),(k9_day,'PARENT_REPLACED')):
        m,docs,host=fresh();armed=[False]
        def hook(host,name,detail,calls,action=action):
            if not armed[0] and ('unlink',temporary(docs,12)) in [entry[:2] for entry in host.log] and name=='open':
                armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host);partial(receipt,code,13);assert armed[0],code
        assert all(row['state']=='INSTALLED_DURABLE' for row in receipt['ledger']) and receipt['readback'] is None and no_symbol_in(receipt)

def after(host,event,path):
    return (event,path) in [entry[:2] for entry in host.log]
def test_the_copy_checks_what_the_core_checks_between_the_write_and_the_link():
    """k8_create_file, through the run: the created file's links and mode; the directory and the temporary looked at
    again right before the link; the fsync of the directory after it; the link count after the temporary is removed."""
    index=4;root=CAPACITY+'/'+TABLE[index][1]
    def at(event,path,action,guard=None):
        done=[False]
        def hook(host,name,detail,calls):
            if not done[0] and name==event and detail and detail[0]==path and (guard is None or guard(host)):
                done[0]=True;action(host)
        return hook
    # a second link of the temporary appears while it is written: refused by the fstat, the temporary withdrawn
    m,docs,host=fresh();temp=temporary(docs,index)
    host.hook=at('write',temp,lambda host:setattr(host.tree.get(temp),'nlink',2));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',index);assert receipt['ledger'][index]['state']=='NOT_CREATED'
    # the mode is not the one asked for (another umask under the run): refused by the fstat
    m,docs,host=fresh();temp=temporary(docs,index)
    host.hook=at('create',temp,lambda host:setattr(host,'mask',0o277));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',index);assert receipt['ledger'][index]['state']=='NOT_CREATED'
    # the directory replaced after the fstat, before the link: nothing is linked, the temporary stays, labelled
    m,docs,host=fresh();temp=temporary(docs,index)
    host.hook=at('fstat',temp,lambda host:setattr(host.tree.get(root),'ino',host.tree.get(root).ino+9))
    receipt=docs.run(host);partial(receipt,'PARENT_REPLACED',index+1)
    assert receipt['ledger'][index]['state']=='TEMPORARY_ONLY' and host.tree.get(PATHS[index]) is None
    # the temporary swapped, or given a second link, after the fstat and before the link: nothing is linked
    for change in (lambda host:host.tree.get(root).children.__setitem__(TABLE_TEMP[0],hostemu.Node('file',mode=0o600,ino=99991,content=b'other')),
                   lambda host:setattr(host.tree.get(TABLE_TEMP[1]),'nlink',2)):
        m,docs,host=fresh();temp=temporary(docs,index);TABLE_TEMP[:]=[temp.rsplit('/',1)[1],temp]
        host.hook=at('lstat',root,change,guard=lambda host,temp=temp:after(host,'fstat',temp));receipt=docs.run(host)
        assert receipt['code']=='TEMPORARY_REPLACED' and host.tree.get(PATHS[index]) is None and receipt['ledger'][index]['state']=='TEMPORARY_ONLY',receipt['code']
    # the directory fsync after the link fails: the file is linked and its temporary is still its second name
    m,docs,host=fresh();temp=temporary(docs,index)
    def fail(host,name,detail,calls):
        if name=='fsync' and detail[0]==root and after(host,'link',temp) and not after(host,'unlink',temp):raise OSError(errno.EIO,'injected')
    host.hook=fail;receipt=docs.run(host);partial(receipt,'FSYNC_FAILED',index+2)
    assert receipt['ledger'][index]['state']=='LINKED_TEMPORARY_PRESENT'
    # a second link of the delivered file appears after its temporary was removed
    m,docs,host=fresh();temp=temporary(docs,index)
    host.hook=at('unlink',temp,lambda host:setattr(host.tree.get(temp),'nlink',3));receipt=docs.run(host)
    partial(receipt,'CREATED_METADATA_MISMATCH',index+1);assert receipt['ledger'][index]['state']=='INSTALLED_NOT_DURABLE'
TABLE_TEMP=[None,None]

def test_the_gate_is_asked_immediately_before_every_call_that_changes_the_host():
    m,docs,host=fresh();plan,real=docs.authenticate();asked=[]
    def gate():
        asked.append(len(host.log));return real()
    receipt=docs.perform(host,gate=gate);assert receipt['status']==m.COMPLETE_STATUS
    for index,entry in enumerate(host.log):
        if entry[0] in ('mkdir','create','write','link','unlink'):assert index in asked,entry


# ---------------------------------------------------------------- crash points and expiry
def total_calls():
    m,docs,host=fresh();names=[]
    def hook(host,name,detail,calls):names.append(name)
    host.hook=hook;assert docs.run(host)['status']==m.COMPLETE_STATUS;return len(names),names

def test_process_death_at_every_host_call_leaves_one_of_the_ordered_states_that_a_later_read_tells_apart():
    total,names=total_calls();seen=[]
    for index in range(1,total+1):
        m,docs,host=fresh();before=k8.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);state=k8.classify(host,docs.go16());seen.append(state)
        assert (state=='F00')==(k8.state_of(host)==before),(index,state)
        assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and (receipt['status']!='REFUSED' or state=='F00'),(index,names[index-1],state)
    order=['F00']+[item for n in range(13) for item in ('F%02d_TEMPORARY'%n,'F%02d_LINKED'%(n+1),'F%02d'%(n+1))]
    assert [order.index(state) for state in seen]==sorted(order.index(state) for state in seen),'the states only move forward'
    assert set(seen)==set(order),'every state is reached by some crash point'

def test_expiry_or_a_reversed_clock_at_every_gate_is_a_refusal_only_while_nothing_exists():
    m,docs,host=fresh();count=[0]
    def counting():
        count[0]+=1;return 0.0
    assert docs.run(host,monotonic=counting)['status']==m.COMPLETE_STATUS;total=count[0];assert total>100
    for expired,code in ((61.0,'GO_EXPIRED'),(-1.0,'CLOCK_REVERSED')):
        states=set()
        for index in range(4,total,3 if expired>0 else 7):
            m,docs,host=fresh();before=k8.state_of(host);count=[0]
            def monotonic(index=index):
                count[0]+=1;return expired if count[0]==index else (0.0 if count[0]<index else 61.0)
            receipt=docs.run(host,monotonic=monotonic);state=k8.classify(host,docs.go16());states.add((receipt['status'],state))
            assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and receipt['code'] in (code,'GO_EXPIRED'),(index,receipt['code'])
            assert (receipt['status']=='REFUSED')==(k8.state_of(host)==before)==(state=='F00') and host.fds=={} and f.sealed(receipt)
        assert {state for _,state in states}>={'F00','F01','F12','F13'},states

def test_escape_after_an_effect_is_partial_and_before_any_is_a_refusal():
    m,docs,host=fresh()
    def hook(host,name,detail,calls):
        if name=='create' and detail[0]==temporary(docs,1):raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    m,docs,host=fresh()
    def early(host,name,detail,calls):
        if name=='fstatvfs':raise KeyboardInterrupt()
    host.hook=early;before=k8.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and k8.state_of(host)==before


# ---------------------------------------------------------------- once per day: there is no second attempt
def test_second_request_after_a_complete_or_a_partial_run_is_refused_and_changes_nothing():
    m,docs,host=fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS
    again=f.Docs(docs.k,k8.fields(host),now=docs.now+timedelta(minutes=15));before=k8.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and k8.state_of(host)==before and len(receipt['precheck']['destinations_present'])==13
    m,docs,host=fresh();host.hook=on('create',temporary(docs,5),lambda host:setattr(host,'creator',(0,7)));assert docs.run(host)['status']==m.PARTIAL_STATUS
    host.creator=(0,0);host.hook=None;again=f.Docs(docs.k,k8.fields(host),now=docs.now+timedelta(minutes=15));before=k8.state_of(host);receipt=again.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_PRESENT') and k8.state_of(host)==before and len(receipt['precheck']['destinations_present'])==5

def test_two_days_are_two_deliveries_into_the_same_tree():
    k=k8.K();host=k8.world(k)
    first=f.Docs(k,k8.fields(host),now=k8.moment());assert first.run(host)['status']==k.m.COMPLETE_STATUS
    for path in (DAYS+'/'+FULL,DAYS+'/'+FULL+'/causal',DAYS+'/'+FULL+'/receipts'):host.tree.add(path,mode=0o700)
    host.tree.add(DAYS+'/'+FULL+'/causal/commitment.private.json',kind='file',mode=0o600,content=k8.commitment_of(FULL))
    host.tree.add(DAYS+'/'+FULL+'/causal/build_audit_receipt.json',kind='file',mode=0o600,content=k8.audit_of(FULL))
    host.tree.add(DAYS+'/'+FULL+'/receipts/commit_launch.RECEIPT.json',kind='file',mode=0o600,content=k8.commit_receipt(FULL))
    second=f.Docs(k,k8.fields(host,FULL),now=k8.moment(FULL));receipt=second.run(host)
    assert receipt['status']==k.m.COMPLETE_STATUS and len(host.tree.get(CAPACITY+'/payload').children)==2
    assert sorted(host.tree.get(CAPACITY+'/go').children)==sorted('session=%s.%s.json'%(day,phase) for day in (DAY,FULL) for phase in ('admission','bar_manifest'))
