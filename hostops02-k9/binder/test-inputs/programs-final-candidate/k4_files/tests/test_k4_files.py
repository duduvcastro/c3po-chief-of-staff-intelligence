"""K4 modes CHAIN_STATIC (B5), PINS (B6) and LAUNCHER (A8) end to end on the emulated host: the literal effects the
signers see, every refusal with its code and the proof that nothing changed, hostile states after the precheck, every
point at which the process can die, expiry at every gate, and what the receipt says. Synthetic and in memory: no SSH,
no host, no credential, no docker binary, no GO."""
import copy
from datetime import timedelta
import errno
import json
import os
from pathlib import Path
import re

import pytest

import family as f
import hostemu
import k4f

MODES=('CHAIN_STATIC','PINS','LAUNCHER','WRITER')
ROOT=hostemu.ROOT_DEVICE
WORK=Path(__file__).resolve().parents[3]          # W: the parent of the deliverable directory
ACTB=Path(os.environ.get('HOSTOPS02_TEST_ACTB_DIRECTORY') or WORK/'fable-actb03-20261004')
OPSART=os.environ.get('HOSTOPS02_TEST_OPSART_DIRECTORY')     # a checkout of the operations repository (reader and capacity-day READMEs)
def fresh(mode='CHAIN_STATIC',**options):
    docs,host=k4f.case(mode=mode,**options);return docs.k.m,docs,host
def refused_untouched(receipt,host,before,code,phase='PRECHECK'):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,phase),receipt['code']
    assert k4f.state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0
    assert receipt['objects_left_by_this_run']==0 and receipt['delivered'] is None and host.fds=={} and host.commands==[] and f.sealed(receipt)
def partial(receipt,code,left):
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('PARTIAL_METADATA_REQUIRES_REVIEW','PARTIAL_REQUIRES_RECONCILIATION',code,'EFFECTS'),receipt['code']
    assert receipt['objects_left_by_this_run']==left and receipt['delivered'] is None and receipt['readback'] is None and f.sealed(receipt)
def on(event,path,action,once=True):
    done=[False]
    def hook(host,name,detail,calls):
        if name==event and detail and detail[0]==path and not (once and done[0]):
            done[0]=True;action(host)
    return hook
def chain_paths(m):return [k4f.DOCUMENTS+'/'+name for _,name,_,_,_ in m.K4_CHAIN_DOCUMENTS]
def targets(mode,m):
    return {'CHAIN_STATIC':chain_paths(m)+[k4f.STATIC],'PINS':[k4f.PINS],'LAUNCHER':[k4f.LAUNCHER_FILE],'WRITER':[k4f.writer_path(m)]}[mode]
def contents(mode,m,docs):
    if mode=='CHAIN_STATIC':return [m.chain_document_bytes(index) for index in range(7)]+[k4f.static_config(m)]
    if mode=='PINS':return [k4f.render(docs.plan['delivery']['values'],m)]
    if mode=='WRITER':return [m.writer_bytes()]
    return [k4f.LAUNCHER]


# ---------------------------------------------------------------- the compiled chain and the constants
def test_compiled_chain_is_the_signed_act_b_chain_in_the_tools_order():
    m=k4f.K().m
    assert [row[0] for row in m.K4_CHAIN_DOCUMENTS]==['CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU']
    assert [row[1] for row in m.K4_CHAIN_DOCUMENTS]==['CODEX_ORDEM_EPOCA_03_SIGNATURE.rev2.json','FABLE_ORDEM_EPOCA_03_SIGNATURE.rev2.json',
        'DUDU_ORDEM_EPOCA_03_SIGNATURE.rev2.json','ADENDO_EPOCA_03.md','B_CODEX_ADENDO_EPOCA_03.md','B_FABLE_ADENDO_EPOCA_03.md','B_DUDU_ADENDO_EPOCA_03.md']
    for index,(label,name,digest,size,_) in enumerate(m.K4_CHAIN_DOCUMENTS):
        raw=m.chain_document_bytes(index);assert f.sha(raw)==digest and len(raw)==size
    assert dict((row[0],row[2]) for row in m.K4_CHAIN_DOCUMENTS)['ACT_B']=='ab241993da959b22a91e840547c6ab1133491d558043756e3af532bd8d46aaaf'
    assert len({row[2] for row in m.K4_CHAIN_DOCUMENTS})==7 and len({row[1] for row in m.K4_CHAIN_DOCUMENTS})==7

def test_a_compiled_document_that_does_not_decode_to_its_hash_is_refused():
    m=k4f.K().m;saved=m.K4_CHAIN_DOCUMENTS
    try:
        row=saved[0];m.K4_CHAIN_DOCUMENTS=(row[:2]+('3'*64,)+row[3:],)+saved[1:]
        assert f.refusal(lambda:m.chain_document_bytes(0))=='CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH'
        m.K4_CHAIN_DOCUMENTS=(row[:3]+(row[3]+1,)+row[4:],)+saved[1:]
        assert f.refusal(lambda:m.chain_document_bytes(0))=='CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH'
    finally:m.K4_CHAIN_DOCUMENTS=saved

@pytest.mark.skipif(not (ACTB/'DURABLE_SHA256SUMS.20261004T171741Z').is_file(),reason='the Act B chain directory is not on this machine')
def test_the_chain_block_and_the_release_constants_are_the_ones_of_the_act_b_build_record():
    import subprocess,sys
    done=subprocess.run([sys.executable,'-B',str(k4f.DIRECTORY/'chain_block.py'),'check',str(ACTB)],stdout=subprocess.PIPE)
    assert done.returncode==0 and done.stdout.strip()==b'CHAIN_BLOCK_EQUAL'
    m=k4f.K().m;durable=(ACTB/'DURABLE_SHA256SUMS.20261004T171741Z').read_text()
    for _,name,digest,_,_ in m.K4_CHAIN_DOCUMENTS:assert digest+'  ' in durable and name in durable
    record=json.loads((ACTB/'chain'/'ACTB_BUILD_RECORD.json').read_bytes())
    assert record['release']['release_sha']==m.K4_RELEASE_SHA==record['policy']['release_sha'] and record['package_sha256']==m.K4_PACKAGE_SHA
    assert record['policy']['code_revision']==m.K4_CODE_REVISION and f.sha((ACTB/'policy'/'release.CERTIFIED.json').read_bytes())==m.K4_RELEASE_SHA
    assert json.loads((ACTB/'ORDER.RUNTIME.json').read_bytes())['authorized_sessions']==list(m.K4_SESSIONS)
    verify=json.loads((ACTB/'reports'/'VERIFY_FULL.json').read_bytes())
    assert verify['status']=='VERIFY_PASS' and verify['stand_in'] is None and verify['chain_pins']=={row[0]:row[2] for row in m.K4_CHAIN_DOCUMENTS}

def test_identity_flags_and_dates():
    k=k4f.K();m=k.m
    assert k.report['parts']==['core','parents','files'] and not hasattr(m,'COMMANDS') and not hasattr(m,'NativeRunner')
    assert [base.__name__ for base in m.Native.__mro__[1:-1]]==['NativeRead','NativeFiles'] and not hasattr(m.Native,'run') and not hasattr(m.Native,'flock')
    assert (m.WRITES_ALLOWED,m.ACTIVATION_ALLOWED,m.DATE_CLASS,m.DATES,m.EVIDENCE_OPERATIONS)==(True,False,'WRITE_EPOCH',
        ('2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10'),
        ('GO_READONLY_HOSTOPS_PRECHECK_01','GO_WRITE_SUPERVISOR_READER_PROVISION_01'))
    assert m.EVIDENCE_REQUIRED is True and m.MAX_GATE_SPAN_SECONDS==900 and m.SCOPE['processes_started']==0
    assert (m.OPERATION,m.PHASE,m.COMPLETE_OUTCOME,m.PARTIAL_OUTCOME,m.REFUSED_OUTCOME,m.REDUCED_OUTCOME,m.ESCAPED_OUTCOME)==(
        'GO_WRITE_HOSTOPS02_K4_FILES_01','WRITE_K4_FILES_PRIVATE_DELIVERY','K4_FILES_DELIVERED_READ_BACK','PARTIAL_REQUIRES_RECONCILIATION',
        'REFUSED_NOTHING_CHANGED','RECEIPT_REDUCED_STATE_REQUIRES_READBACK','PARTIAL_REQUIRES_RECONCILIATION')
    assert m.PLAN_KEYS==frozenset(('mode','delivery','evidence_boot_id_sha256')) and m.K4_MODES==MODES
    assert (m.K4_RELEASE_SHA,m.K4_PACKAGE_SHA,m.K4_CODE_REVISION)==(k4f.RELEASE,k4f.PACKAGE,k4f.REVISION)

def test_placement_named_in_one_place():
    m=k4f.K().m;own=(k4f.DIRECTORY/'op.py').read_text()
    for literal in ("'/etc/c3po-reader'","'/var/lib/c3po-capacity'","'/etc/systemd/system'"):assert own.count(literal)==1,literal
    assert own.index('# ---- PLACEMENT')<own.index("CAPACITY_ROOT='/var/lib/c3po-capacity'")<own.index('# ---- end of the placement')
    assert (m.DOCUMENTS_DIRECTORY,m.CAPACITY_CONFIG_DIRECTORY,m.LAUNCHER_DIRECTORY)==(k4f.DOCUMENTS,k4f.CONFIG,k4f.LAUNCHER_DIRECTORY)
    assert (m.STATIC_CONFIG_NAME,m.LAUNCHER_NAME,m.PINS_NAME,m.PRODUCER_UNIT_NAME,m.READER_UNIT_NAME)==(
        'week.static.capacity.json','reader_launcher.py','pins.env','c3po-massive.service','c3po-reader.service')
    assert m.PINS_NAMES==('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA','C3PO_R2D2_V2_SHADOW_SOURCE_DIR',
        'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR','C3PO_R2D2_V2_CAPACITY_REQUIRED','C3PO_R2D2_V2_CAPACITY_VETO_MODE',
        'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','C3PO_R2D2_V2_SHADOW_POLL_SECONDS','C3PO_READER_LAUNCHER_SHA256')

S_RDR=Path(OPSART or '/nonexistent')/'c3po'/'deployment'/'reader'/'README.md'
@pytest.mark.skipif(not S_RDR.is_file(),reason='the reader README is not on this machine')
def test_pins_names_are_the_twelve_lines_of_the_reader_readme_in_order():
    m=k4f.K().m;text=S_RDR.read_text();block=text.split('<!-- pins-env:begin -->')[1].split('<!-- pins-env:end -->')[0]
    names=[line.split('=')[0] for line in block.splitlines() if '=' in line and not line.startswith('`')]
    assert tuple(names)==m.PINS_NAMES and 'C3PO_R2D2_V2_SHADOW_POLL_SECONDS=1.0' in block and 'C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY' in block
    assert 'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/day-d-data/provider=eodhd/microstructure/raw' in block and 'C3PO_R2D2_V2_CAPACITY_REQUIRED=true' in block


# ---------------------------------------------------------------- the complete runs
def test_chain_documents_complete_run_and_its_literal_effects():
    m,docs,host=fresh('CHAIN_STATIC');plan=docs.plan;before=k4f.state_of(host);go16=docs.go16();config=k4f.static_config(m)
    files=[dict(path=k4f.DOCUMENTS+'/'+name,sha256=digest,bytes=size,mode_octal='0600',uid=0,gid=0,links=1,expect='ABSENT',key='CHAIN_'+label)
           for label,name,digest,size,_ in m.K4_CHAIN_DOCUMENTS]
    files.append(dict(path=k4f.STATIC,sha256=f.sha(config),bytes=len(config),mode_octal='0600',uid=0,gid=0,links=1,expect='ABSENT',key='STATIC_CONFIG'))
    assert docs.go['effects']==docs.authority['effects']=={'operation':'GO_WRITE_HOSTOPS02_K4_FILES_01','epoch':'R2D2-V2-SHADOW-2026-10-05',
        'mode':'CHAIN_STATIC','files':files,'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,
        'activation':False,'container_touched':False,'process_started':False,'directories':[],
        'documents_parent':m.chain_effects(plan['delivery']['documents_parent']),'config_parent':m.chain_effects(plan['delivery']['config_parent']),
        'static_config':{'release_sha':k4f.RELEASE,'package_sha':k4f.PACKAGE,'chain_pins':'EQUAL_TO_THE_SEVEN_DELIVERED_DOCUMENTS'}}
    host.tree.add(k4f.DOCUMENTS+'/session=2026-10-06.template.md',kind='file',mode=0o600,content=b'x');before=k4f.state_of(host)
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'],receipt['readback'],receipt['mode'])==(
        m.COMPLETE_STATUS,'K4_FILES_DELIVERED_READ_BACK',None,'EFFECTS','COMPLETE','CHAIN_STATIC')
    assert receipt['mutating_calls']=={'issued':32,'succeeded':32,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==8
    for path,raw in zip(targets('CHAIN_STATIC',m),contents('CHAIN_STATIC',m,docs)):
        node=host.tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content),node.synced)==('file',0,0,0o600,1,raw,True),path
    assert sorted(host.tree.get(k4f.DOCUMENTS).children)==sorted([name for _,name,_,_,_ in m.K4_CHAIN_DOCUMENTS]+['session=2026-10-06.template.md'])
    assert sorted(host.tree.get(k4f.CONFIG).children)==['week.static.capacity.json']
    for path in targets('CHAIN_STATIC',m):host.tree.remove(path)
    assert k4f.state_of(host)==before,'nothing else changed'
    mutating=[entry[:2] for entry in host.mutating()];expected=[]
    for index,path in enumerate(targets('CHAIN_STATIC',m)):
        temporary=path.rsplit('/',1)[0]+'/.hostops-%s-%d.partial'%(go16,index)
        expected+=[('create',temporary),('write',temporary),('link',temporary),('unlink',temporary)]
    assert mutating==expected and host.mask==0o077 and host.fds=={} and host.commands==[]
    assert receipt['precheck']['entries_before']=={'DOCUMENTS':1,'CONFIG':0} and receipt['delivered']['entries_after']=={'DOCUMENTS':8,'CONFIG':1}
    assert receipt['delivered']['files']==[{'key':row['key'],'path':row['path'],'sha256':row['sha256'],'bytes':row['bytes'],'mode_octal':'0600','uid':0,'gid':0,
                                          'links':1,'bytes_equal_the_signed_bytes':True,'created_by_this_run':True} for row in files]
    assert receipt['delivered']['directories']==[] and receipt['parent']=={'documents':plan['delivery']['documents_parent'],'config':plan['delivery']['config_parent']}
    assert all(row['state']=='INSTALLED_DURABLE' and row['sha256_observed']==row['sha256_signed'] for row in receipt['ledger'])
    assert receipt['precheck']['found']=={name:'ABSENT' for name in [row[1] for row in m.K4_CHAIN_DOCUMENTS]+['week.static.capacity.json']}
    assert receipt['precheck']['free_bytes']==[145315507*4096]*2 and receipt['precheck']['seconds_left_before_first_effect']==60

def test_pins_complete_run_and_its_literal_effects():
    m,docs,host=fresh('PINS');plan=docs.plan;item=plan['delivery'];raw=k4f.render(item['values'],m);before=k4f.state_of(host)
    assert raw.count(b'\n')==12 and raw.endswith(b'\n') and raw.split(b'\n')[11].startswith(b'C3PO_READER_LAUNCHER_SHA256=')
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_K4_FILES_01','epoch':'R2D2-V2-SHADOW-2026-10-05','mode':'PINS',
        'files':[{'path':k4f.PINS,'sha256':f.sha(raw),'bytes':len(raw),'mode_octal':'0600','uid':0,'gid':0,'links':1,'expect':'ABSENT','key':'PINS_ENV'}],
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,
        'process_started':False,'reader_parent':m.chain_effects(item['reader_parent']),'config_parent':m.chain_effects(item['config_parent']),
        'unit_parent':m.chain_effects(item['unit_parent']),'directories':[],'values':item['values'],
        'required_on_the_host':{'static_config':{'path':k4f.STATIC,'sha256':item['values']['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA']},
                                'launcher':{'path':k4f.LAUNCHER_FILE,'sha256':f.sha(k4f.LAUNCHER)},
                                'producer_unit':{'path':k4f.UNITS+'/c3po-massive.service','sha256':item['producer_unit_sha256']},
                                'reader_unit':{'path':k4f.UNITS+'/c3po-reader.service','sha256':item['reader_unit_sha256']},
                                'journal_bind':'SAME_SOURCE_IN_BOTH_UNITS_TARGET_/c3po-bar-journal',
                                'bind_sources':{'source_root':m.chain_effects(item['source_chain']),'journal':m.chain_effects(item['journal_chain']),
                                                'reader_binds_source_root_at':'/c3po-source'}}}
    receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['mode'])==(m.COMPLETE_STATUS,'K4_FILES_DELIVERED_READ_BACK',None,'PINS')
    node=host.tree.get(k4f.PINS);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==('file',0,0,0o600,1,raw)
    host.tree.remove(k4f.PINS);assert k4f.state_of(host)==before
    assert receipt['precheck']['read_and_equal_to_the_signed_bytes']==['LAUNCHER_FILE','STATIC_CONFIG_FILE','PRODUCER_UNIT','READER_UNIT']
    assert receipt['precheck']['journal_bind']=={'host_source':'/var/lib/c3po-bar/journal','container_target':'/c3po-bar-journal','same_in_both_units':True}
    assert receipt['mutating_calls']['succeeded']==4 and receipt['objects_left_by_this_run']==1 and sorted(receipt['parent'])==['config','journal','reader','source_root','units']
    line=f.line(receipt);assert k4f.LAUNCHER[:40] not in line and b'--journal-root' not in line and b'ExecStart' not in line

def test_launcher_complete_run_and_its_literal_effects():
    m,docs,host=fresh('LAUNCHER');plan=docs.plan;before=k4f.state_of(host)
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_K4_FILES_01','epoch':'R2D2-V2-SHADOW-2026-10-05','mode':'LAUNCHER',
        'files':[{'path':k4f.LAUNCHER_FILE,'sha256':f.sha(k4f.LAUNCHER),'bytes':len(k4f.LAUNCHER),'mode_octal':'0600','uid':0,'gid':0,'links':1,
                  'expect':'ABSENT','key':'LAUNCHER'}],
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,
        'process_started':False,'reader_parent':m.chain_effects(plan['delivery']['reader_parent']),
        'directories':[{'path':k4f.LAUNCHER_DIRECTORY,'mode_octal':'0700','uid':0,'gid':0,'expect':'ABSENT','entries_after':1}]}
    receipt=docs.run(host);temporary=k4f.LAUNCHER_DIRECTORY+'/.hostops-%s-0.partial'%docs.go16()
    assert (receipt['status'],receipt['code'],receipt['mode'])==(m.COMPLETE_STATUS,None,'LAUNCHER')
    assert [entry[:2] for entry in host.mutating()]==[('mkdir',k4f.LAUNCHER_DIRECTORY),('create',temporary),('write',temporary),('link',temporary),('unlink',temporary)]
    node=host.tree.get(k4f.LAUNCHER_DIRECTORY);assert (node.kind,node.uid,node.gid,node.mode,sorted(node.children))==('dir',0,0,0o700,['reader_launcher.py'])
    node=host.tree.get(k4f.LAUNCHER_FILE);assert (node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==(0,0,0o600,1,k4f.LAUNCHER)
    assert receipt['delivered']['directories']==[{'path':k4f.LAUNCHER_DIRECTORY,'mode_octal':'0700','uid':0,'gid':0,'entries':1}]
    assert [entry['state'] for entry in receipt['directories']]==['CREATED_DURABLE'] and receipt['objects_left_by_this_run']==2
    host.tree.remove(k4f.LAUNCHER_DIRECTORY);assert k4f.state_of(host)==before
    assert [entry[1] for entry in host.log if entry[0]=='fsync']==[k4f.LAUNCHER_DIRECTORY,k4f.READER,temporary,k4f.LAUNCHER_DIRECTORY,k4f.LAUNCHER_DIRECTORY]

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_receipt_never_carries_the_bytes_and_stays_small(mode):
    m,docs,host=fresh(mode);receipt=docs.run(host);line=f.line(receipt)
    for raw in contents(mode,m,docs):
        assert k4f.b64(raw)[:64].encode() not in line
        if mode!='PINS':
            for start in range(0,len(raw)-40,max(1,len(raw)//50)):
                piece=json.dumps(raw[start:start+40].decode('utf-8','replace'))[1:-1]
                if not re.search('[0-9a-f]{16}',piece):assert piece.encode() not in line,piece      # hashes the documents carry are signed elsewhere
    assert len(line)<20000 and receipt['size_reductions']==[] and receipt['secret_bytes_in_receipt'] is False and hostemu.SECRET.encode() not in line

def test_scope_statement_is_literally_what_the_signers_sign():
    m=k4f.K().m
    assert m.SCOPE_STATEMENT==('Delivers, for epoch R2D2-V2-SHADOW-2026-10-05, exactly one of four signed modes. CHAIN_STATIC: the seven chain documents '
        'compiled into this source into /var/lib/c3po-capacity/documents and the static capacity config week.static.capacity.json whose bytes the request '
        'signs into /var/lib/c3po-capacity/config. PINS: /etc/c3po-reader/pins.env, twelve lines rendered from the signed values, only after the static '
        'config, the launcher and the two installed units it names are read on the host and found to be the signed bytes, and the host sources of the '
        'source-root and journal binds are walked as root-controlled chains. LAUNCHER: the directory '
        '/etc/c3po-reader/launcher and in it reader_launcher.py holding the bytes the request signs. WRITER: in /var/lib/c3po-capacity/config the '
        'capacity-day manifest writer compiled into this source, under the content-addressed name manifest_writer-<sha256>.py. Every file root:root 0600 and every directory '
        'root:root 0700, by exclusive creation relative to a held descriptor of a parent walked from "/" against signed rows, fsync, and a readback of '
        'the bytes and of the directories through descriptors inside the run. Nothing that exists is overwritten, renamed, chmodded, chowned or removed, '
        'except the temporary of this run once its identity is proved. No process is started, no secret is read or written, no container is touched and '
        'nothing is activated.')
    assert m.SCOPE['modes']==list(MODES) and m.SCOPE['placement']['open_roots'] is None and m.SCOPE['pins_env']['constants']==m.PINS_CONSTANTS
    assert m.SCOPE['chain_documents']==[{'label':row[0],'file':row[1],'sha256':row[2],'bytes':row[3]} for row in m.K4_CHAIN_DOCUMENTS]
    assert m.SCOPE['limits']=={'max_seconds':60,'max_gate_span_seconds':900,'receipt_bytes':60000,'static_config_bytes':16384,'launcher_bytes':32768,
                               'free_bytes_floor':1048576,'write_allowance_seconds':15}
    assert m.SCOPE['static_config']=={'directory':k4f.CONFIG,'name':'week.static.capacity.json','schema':'R2D2_CAPACITY_BOOTSTRAP_V3','max_bytes':16384,
                                      'release_sha':k4f.RELEASE,'package_sha':k4f.PACKAGE,'veto_mode':'DISPATCH_AND_DERIVATION_ONLY'}
    assert m.SCOPE['never']==['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker',
                              'systemctl','a shell','a network connection','a secret','activation','a container','a second attempt']
    assert m.PINS_CONSTANTS=={'C3PO_BUILD_SHA':k4f.REVISION,'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':k4f.RELEASE,
        'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR':'/app/day-d-data/provider=eodhd/microstructure/raw','C3PO_R2D2_V2_CAPACITY_REQUIRED':'true',
        'C3PO_R2D2_V2_CAPACITY_VETO_MODE':'DISPATCH_AND_DERIVATION_ONLY','C3PO_R2D2_V2_SHADOW_POLL_SECONDS':'1.0'}

def test_a_request_of_one_mode_is_another_document_than_the_same_files_under_another_mode():
    m,docs,host=fresh('LAUNCHER');other=copy.deepcopy(docs.plan);other['mode']='PINS'
    assert f.refusal(lambda:m.validate_plan(other))=='DELIVERY_INVALID'
    other['mode']='CHAIN_STATIC';assert f.refusal(lambda:m.validate_plan(other))=='DELIVERY_INVALID'


# ---------------------------------------------------------------- the plan, refused from its bytes, before any claim
def change(path,value):
    def apply(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return apply
def config_change(m_unused=None,**changes):
    def apply(plan):
        m=k4f.K().m;raw=k4f.static_config(m,**changes);plan['delivery']['static_config']=k4f.member(raw)
    return apply
def config_raw(raw):
    def apply(plan):plan['delivery']['static_config']=k4f.member(raw)
    return apply
def config_mutate(mutation):
    def apply(plan):
        m=k4f.K().m;value=json.loads(k4f.static_config(m));mutation(value);plan['delivery']['static_config']=k4f.member(f.canonical(value))
    return apply
def rows_of(key,path):
    def apply(plan):
        k,host=k4f.world('CHAIN_STATIC');host.tree.add(path,mode=0o700) if host.tree.get(path) is None else None;plan['delivery'][key]=hostemu.rows(host,path)
    return apply
CHAIN_STATIC_CASES=[
    (change(['mode'],None),'MODE_INVALID'),(change(['mode'],'chain_static'),'MODE_INVALID'),(change(['mode'],'E0'),'MODE_INVALID'),
    (change(['delivery'],None),'DELIVERY_INVALID'),(change(['delivery','extra'],1),'DELIVERY_INVALID'),(lambda plan:plan['delivery'].pop('config_parent'),'DELIVERY_INVALID'),
    (change(['evidence_boot_id_sha256'],None),'EVIDENCE_BOOT_UNBOUND'),(change(['evidence_boot_id_sha256'],'0'*64),'EVIDENCE_BOOT_UNBOUND'),
    (change(['delivery','documents_parent'],None),'CHAIN_ROW_INVALID'),(lambda plan:plan['delivery']['documents_parent'].pop(),'CHAIN_ROW_INVALID'),
    (rows_of('documents_parent',k4f.CAPACITY+'/payload'),'CHAIN_ROW_INVALID'),(rows_of('config_parent',k4f.DOCUMENTS),'CHAIN_ROW_INVALID'),
    (change(['delivery','documents_parent',4,'uid'],1000),'CHAIN_ROW_UNSAFE'),(change(['delivery','documents_parent',2,'mode'],0o775),'CHAIN_ROW_UNSAFE'),
    (change(['delivery','config_parent',3,'mode'],0o757),'CHAIN_ROW_UNSAFE'),(change(['delivery','documents_parent',4,'mode'],0o2700),'PARENT_SETGID'),
    (change(['delivery','documents_parent',1,'gid'],4),'CHAIN_NOT_ROOT_CONTROLLED'),(change(['delivery','config_parent',3,'mode'],0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['delivery','documents_parent',4,'mode'],0o750),'PARENT_NOT_ROOT_0700'),(change(['delivery','config_parent',4,'mode'],0o755),'PARENT_NOT_ROOT_0700'),
    (change(['delivery','config_parent',4,'gid'],0o1),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['delivery','config_parent',3,'inode'],99),'CAPACITY_CHAIN_DIVERGES'),
    (change(['delivery','static_config'],None),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','static_config','sha256'],'3'*64),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','static_config','bytes'],16385),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','static_config','content_b64'],'not base64!'),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','static_config','content_b64'],'é'),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (config_raw(b'{"a":1}'),'STATIC_CONFIG_INVALID'),(config_raw(b'[1]'),'STATIC_CONFIG_INVALID'),(config_raw(b'not json'),'STATIC_CONFIG_INVALID'),
    (config_raw(b'{"a":1,"a":2}'),'STATIC_CONFIG_INVALID'),
    (config_mutate(lambda value:value.update(extra=1)),'STATIC_CONFIG_INVALID'),
    (lambda plan:plan['delivery'].update(static_config=k4f.member(json.dumps(json.loads(k4f.static_config(k4f.K().m)),sort_keys=True).encode())),'STATIC_CONFIG_INVALID'),
    (lambda plan:plan['delivery']['static_config'].update(bytes=plan['delivery']['static_config']['bytes']-1),'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH'),
    (config_mutate(lambda value:(value['document_pins']['TEMPLATE'].update(file='session=2026-10-12.template.md'),
                                 value.update(veto_views={'2026-10-12':{'file':'session=2026-10-12.view-primary.md','sha256':k4f.label('view')}}))),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value.update(veto_views={'2026-10-06':{'file':'session=2026-10-06.view-primary.md','sha256':k4f.label('view')}})),'STATIC_CONFIG_ANCHOR'),(config_mutate(lambda value:value.pop('roots')),'STATIC_CONFIG_INVALID'),
    (config_change(schema='R2D2_CAPACITY_BOOTSTRAP_V2'),'STATIC_CONFIG_INVALID'),(config_change(r2d2_v2_capacity_veto_mode='OFF'),'STATIC_CONFIG_INVALID'),
    (config_change(restore_revocation={}),'STATIC_CONFIG_INVALID'),(config_change(calendar_pin_sha='0'*64),'STATIC_CONFIG_INVALID'),
    (config_mutate(lambda value:value['identity'].update(epoch='R2D2-V2-SHADOW-2026-09-28')),'STATIC_CONFIG_IDENTITY'),
    (config_mutate(lambda value:value['identity'].update(namespace='X')),'STATIC_CONFIG_IDENTITY'),
    (config_mutate(lambda value:value['identity'].update(first_session='2026-10-06')),'STATIC_CONFIG_IDENTITY'),
    (config_mutate(lambda value:value['identity']['authorized_sessions'].pop()),'STATIC_CONFIG_IDENTITY'),
    (config_change(identity=None),'STATIC_CONFIG_IDENTITY'),
    (config_change(release_sha='3'*64),'STATIC_CONFIG_RELEASE'),(config_change(package_sha='3'*64),'STATIC_CONFIG_RELEASE'),
    (config_mutate(lambda value:value['document_pins'].pop('B_DUDU')),'STATIC_CONFIG_CHAIN_PINS'),
    (config_mutate(lambda value:value['document_pins'].update(EXTRA={'file':'x','sha256':'3'*64})),'STATIC_CONFIG_CHAIN_PINS'),
    (config_mutate(lambda value:value['document_pins']['ACT_B'].update(sha256='3'*64)),'STATIC_CONFIG_CHAIN_PINS'),
    (config_mutate(lambda value:value['document_pins']['CODEX'].update(file='other.json')),'STATIC_CONFIG_CHAIN_PINS'),
    (config_mutate(lambda value:value['document_pins'].update(B_CODEX=value['document_pins']['B_FABLE'])),'STATIC_CONFIG_CHAIN_PINS'),
    (config_change(document_pins=None),'STATIC_CONFIG_CHAIN_PINS'),
    (config_mutate(lambda value:value['document_pins']['TEMPLATE'].update(file='session=2026-10-12.template.md')),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['document_pins']['TEMPLATE'].update(sha256='0'*64)),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['document_pins']['TEMPLATE'].update(extra=1)),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value.update(veto_views={'2026-10-06':value['veto_views']['2026-10-05']})),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value.update(veto_views={})),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['veto_views']['2026-10-05'].update(file='session=2026-10-06.view-primary.md')),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['veto_views']['2026-10-05'].update(file='session=2026-10-05.view-a/b.md')),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['veto_views']['2026-10-05'].update(sha256='x')),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['veto_views']['2026-10-05'].update(extra=1)),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['veto_views'].update({'2026-10-06':value['veto_views']['2026-10-05']})),'STATIC_CONFIG_ANCHOR'),
    (config_mutate(lambda value:value['roots'].pop('go')),'STATIC_CONFIG_ROOTS'),
    (config_mutate(lambda value:value['roots']['payload'].update(path='/app/day-d-data/payload')),'STATIC_CONFIG_ROOTS'),
    (config_mutate(lambda value:value['roots']['documents'].update(extra=1)),'STATIC_CONFIG_ROOTS'),
    (config_mutate(lambda value:value['roots'].update(config={'path':'/c3po-capacity/config','identity':'x'})),'STATIC_CONFIG_ROOTS'),
]
def pins_change(**changes):
    def apply(plan):
        m=k4f.K().m;values=dict(plan['delivery']['values'],**changes);raw=k4f.render(values,m)
        plan['delivery'].update(values=values,sha256=f.sha(raw),bytes=len(raw))
    return apply
PINS_CASES=[
    (change(['delivery','reader_parent',2,'mode'],0o755),'PARENT_NOT_ROOT_0700'),(change(['delivery','reader_parent',1,'uid'],1000),'CHAIN_ROW_UNSAFE'),
    (change(['delivery','unit_parent',3,'mode'],0o775),'CHAIN_ROW_UNSAFE'),(change(['delivery','unit_parent',2,'gid'],4),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['delivery','unit_parent',3,'mode'],0o2755),'CHAIN_NOT_ROOT_CONTROLLED'),(change(['delivery','unit_parent'],[]),'CHAIN_ROW_INVALID'),
    (change(['delivery','config_parent',4,'mode'],0o711),'PARENT_NOT_ROOT_0700'),
    (change(['delivery','values'],None),'PINS_VALUES_INVALID'),(lambda plan:plan['delivery']['values'].pop('C3PO_READER_LAUNCHER_SHA256'),'PINS_VALUES_INVALID'),
    (lambda plan:plan['delivery']['values'].update(C3PO_DATABASE_URL='postgresql://x'),'PINS_VALUES_INVALID'),
    (change(['delivery','values','C3PO_R2D2_V2_SHADOW_POLL_SECONDS'],1.0),'PINS_VALUES_INVALID'),
    (pins_change(C3PO_BUILD_SHA='3'*40),'PINS_CONSTANT_MISMATCH'),(pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_SHA='3'*64),'PINS_CONSTANT_MISMATCH'),
    (pins_change(C3PO_R2D2_MICROSTRUCTURE_RAW_DIR='/app/day-d-data/raw'),'PINS_CONSTANT_MISMATCH'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_REQUIRED='false'),'PINS_CONSTANT_MISMATCH'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_VETO_MODE='DISPATCH_ONLY'),'PINS_CONSTANT_MISMATCH'),(pins_change(C3PO_R2D2_V2_SHADOW_POLL_SECONDS='1'),'PINS_CONSTANT_MISMATCH'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/release.json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/a/b/release.json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/../etc/release.json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/mnt/day-d-data/a/release.json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/a/release json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/a/'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/./release.json'),'PINS_RELEASE_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-data/a/b'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-data/r2d2-v2-source-20261005'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-capacity'),'PINS_SOURCE_DIR'),(pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-reader'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-bar-journal'),'PINS_SOURCE_DIR'),
    (change(['delivery','source_chain',4,'mode'],0o755),'PARENT_NOT_ROOT_0700'),(change(['delivery','source_chain',3,'uid'],1000),'CHAIN_ROW_UNSAFE'),
    (change(['delivery','source_chain',2,'gid'],1000),'CHAIN_NOT_ROOT_CONTROLLED'),(lambda plan:plan['delivery']['source_chain'].pop(),'CHAIN_ROW_INVALID'),
    (change(['delivery','journal_chain',4,'mode'],0o750),'PARENT_NOT_ROOT_0700'),(change(['delivery','journal_chain',3,'mode'],0o2700),'CHAIN_NOT_ROOT_CONTROLLED'),
    (change(['delivery','journal_chain'],None),'CHAIN_ROW_INVALID'),(pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-data'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-data/a$b'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/app/day-d-data/journal'),'PINS_JOURNAL_DIR'),
    (pins_change(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/c3po-capacity'),'PINS_JOURNAL_DIR'),(pins_change(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/c3po-reader'),'PINS_JOURNAL_DIR'),
    (pins_change(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/c3po-a/b'),'PINS_JOURNAL_DIR'),(pins_change(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/etc'),'PINS_JOURNAL_DIR'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/documents/week.static.capacity.json'),'PINS_CONFIG_FILE'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/config/a/b.json'),'PINS_CONFIG_FILE'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/xonfig/week.static.capacity.json'),'PINS_CONFIG_FILE'),
    (pins_change(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-dataX/source'),'PINS_SOURCE_DIR'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/config/'),'PINS_CONFIG_FILE'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='/c3po-capacity/config/.hostops-0123456789abcdef-1.partial'),'PINS_CONFIG_FILE'),
    (pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='0'*64),'PINS_HASH_INVALID'),(pins_change(C3PO_READER_LAUNCHER_SHA256='A'*64),'PINS_HASH_INVALID'),
    (pins_change(C3PO_READER_LAUNCHER_SHA256=k4f.RELEASE),'PINS_HASH_REUSED'),(pins_change(C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=k4f.RELEASE),'PINS_HASH_REUSED'),
    (lambda plan:pins_change(C3PO_READER_LAUNCHER_SHA256=plan['delivery']['values']['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'])(plan),'PINS_HASH_REUSED'),
    (change(['delivery','sha256'],'3'*64),'PINS_BYTES_NOT_THE_SIGNED_HASH'),(lambda plan:plan['delivery'].update(bytes=plan['delivery']['bytes']+1),'PINS_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','bytes'],True),'PINS_BYTES_NOT_THE_SIGNED_HASH'),(change(['delivery','bytes'],5000),'PINS_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','sha256'],None),'PINS_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','producer_unit_sha256'],'0'*64),'UNIT_HASH_INVALID'),(change(['delivery','reader_unit_sha256'],None),'UNIT_HASH_INVALID'),
    (lambda plan:plan['delivery'].update(reader_unit_sha256=plan['delivery']['producer_unit_sha256']),'UNIT_HASH_INVALID'),
]
LAUNCHER_CASES=[
    (change(['delivery','reader_parent',2,'mode'],0o711),'PARENT_NOT_ROOT_0700'),(change(['delivery','reader_parent',2,'uid'],1000),'CHAIN_ROW_UNSAFE'),
    (change(['delivery','reader_parent',2,'gid'],1000),'CHAIN_NOT_ROOT_CONTROLLED'),(change(['delivery','reader_parent',2,'mode'],0o2700),'PARENT_SETGID'),
    (change(['delivery','reader_parent',0,'mode'],0o777),'CHAIN_ROW_UNSAFE'),(lambda plan:plan['delivery']['reader_parent'].pop(),'CHAIN_ROW_INVALID'),
    (change(['delivery','launcher'],None),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),(change(['delivery','launcher','extra'],1),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','launcher','bytes'],32769),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),(change(['delivery','launcher','bytes'],0),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),(change(['delivery','launcher','bytes'],len(k4f.LAUNCHER)-1),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','launcher','sha256'],f.sha(k4f.LAUNCHER).upper()),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','launcher','content_b64'],k4f.b64(k4f.LAUNCHER+b' ')),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','launcher','content_b64'],k4f.b64(k4f.LAUNCHER)[:8]+'\n'+k4f.b64(k4f.LAUNCHER)[8:]),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (change(['delivery','launcher','content_b64'],None),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
    (lambda plan:plan['delivery'].update(launcher=k4f.member(b'x'*32769)),'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH'),
]
WRITER_CASES=[
    (change(['delivery','writer_sha256'],'3'*64),'WRITER_NOT_THE_COMPILED_HASH'),(change(['delivery','writer_sha256'],None),'WRITER_NOT_THE_COMPILED_HASH'),
    (change(['delivery','config_parent',4,'mode'],0o755),'PARENT_NOT_ROOT_0700'),(change(['delivery','config_parent',1,'uid'],1000),'CHAIN_ROW_UNSAFE'),
    (change(['delivery','config_parent',2,'gid'],5),'CHAIN_NOT_ROOT_CONTROLLED'),(rows_of('config_parent',k4f.DOCUMENTS),'CHAIN_ROW_INVALID'),
    (change(['delivery','extra'],1),'DELIVERY_INVALID'),(lambda plan:plan['delivery'].pop('writer_sha256'),'DELIVERY_INVALID'),
]
ALL_CASES=[('CHAIN_STATIC',)+case for case in CHAIN_STATIC_CASES]+[('PINS',)+case for case in PINS_CASES]+[('LAUNCHER',)+case for case in LAUNCHER_CASES]+[
    ('WRITER',)+case for case in WRITER_CASES]
@pytest.mark.parametrize('index',range(len(ALL_CASES)))
def test_plan_refusals_are_authentication_refusals_nothing_is_touched_and_no_go_is_claimed(index,tmp_path):
    mode,apply,code=ALL_CASES[index];m,docs,host=fresh(mode);apply(docs.plan);docs.chain()
    assert f.refusal(docs.authenticate)==code,code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'],receipt['phase_reached'],receipt['outcome'])==('REFUSED',code,'AUTHENTICATION','REFUSED_NOTHING_CHANGED')
    assert receipt['mutating_calls']['issued']==0 and f.sealed(receipt)
    dispatch=f.Dispatch(docs,tmp_path);assert f.refusal(dispatch.prepare)==code and not dispatch.claims()

def test_accepted_plans_at_the_edges():
    m,docs,host=fresh('CHAIN_STATIC');host.tree.get('/var/lib').mode=0o711
    docs.plan['delivery']['documents_parent']=hostemu.rows(host,k4f.DOCUMENTS);docs.plan['delivery']['config_parent']=hostemu.rows(host,k4f.CONFIG);docs.chain()
    assert docs.run(host)['status']==m.COMPLETE_STATUS
    for day in k4f.SESSIONS:
        m,docs,host=fresh('CHAIN_STATIC');value=json.loads(k4f.static_config(m));value['document_pins']['TEMPLATE']['file']='session=%s.template.md'%day
        value['veto_views']={day:{'file':'session=%s.view-w2.md'%day,'sha256':k4f.label('v')}};raw=f.canonical(value)
        m.static_config_of(raw)
    largest=(k4f.LAUNCHER*100)[:32768];m,docs,host=fresh('LAUNCHER');docs.plan['delivery']['launcher']=k4f.member(largest);docs.chain()
    assert len(docs.raw()[0])<=65536-2048 and docs.run(host)['status']==m.COMPLETE_STATUS and bytes(host.tree.get(k4f.LAUNCHER_FILE).content)==largest
    m=k4f.K().m;m.pins_lines(k4f.pins_values(m,C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/x/y'))
    m.pins_lines(k4f.pins_values(m,C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/c3po-journal'))
    m.pins_lines(k4f.pins_values(m,C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-r2d2-sources'))

def test_evidence_must_name_the_precheck_and_the_provisioning():
    for names in (['GO_READONLY_HOSTOPS_PRECHECK_01'],['GO_WRITE_SUPERVISOR_READER_PROVISION_01']):
        m,docs,host=fresh(evidence=[{'role':'R%d'%index,'operation':name,'receipt_sha256':'a'*64} for index,name in enumerate(names)])
        assert f.refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_every_day_of_the_class_is_accepted_and_the_day_before_is_not():
    for day in (3,4,5,9,10):
        now=f.moment(k4f.K()).replace(day=day,hour=21,minute=38);m,docs,host=fresh(now=now);assert docs.run(host)['status']==m.COMPLETE_STATUS,day
    now=f.moment(k4f.K()).replace(day=2,hour=21);m,docs,host=fresh(now=now);assert f.refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'


# ---------------------------------------------------------------- everything is looked at before the first creation
def precheck_cases(mode,m):
    def other_boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')
    def not_root(host):host.actor=(0,5)
    def no_noatime(host):host.noatime_available=False
    def full(host):host.vfs[ROOT].f_bavail=255
    def statvfs_garbage(host):host.vfs[ROOT].f_frsize=0
    common=[(other_boot,'EVIDENCE_FROM_EARLIER_BOOT'),(not_root,'EXECUTOR_IDENTITY'),(no_noatime,'NOATIME_UNAVAILABLE'),(full,'FREE_SPACE_BELOW_FLOOR'),
            (statvfs_garbage,'STATVFS_INVALID')]
    if mode=='CHAIN_STATIC':
        def documents_mode(host):host.tree.get(k4f.DOCUMENTS).mode=0o755
        def config_inode(host):host.tree.get(k4f.CONFIG).ino+=1
        def capacity_link(host):
            node=host.tree.get('/var/lib');node.children['c3po-capacity-real']=node.children.pop('c3po-capacity');host.tree.add(k4f.CAPACITY,kind='symlink',mode=0o777)
        def present(index):
            def apply(host):host.tree.add(chain_paths(m)[index],kind='file',mode=0o600,content=b'x')
            return apply
        def present_link(host):host.tree.add(chain_paths(m)[3],kind='symlink',mode=0o777)
        def config_present(host):host.tree.add(k4f.STATIC,kind='file',mode=0o644,content=k4f.static_config(m))
        def document_two_links(host):host.tree.add(chain_paths(m)[1],kind='file',mode=0o600,content=m.chain_document_bytes(1)).nlink=2
        return common+[(documents_mode,'PARENT_IDENTITY_MISMATCH'),(config_inode,'PARENT_IDENTITY_MISMATCH'),(capacity_link,'PARENT_SYMLINK_COMPONENT'),
                       (present(0),'CHAIN_DOCUMENT_PRESENT'),(present(6),'CHAIN_DOCUMENT_PRESENT'),(present_link,'CHAIN_DOCUMENT_PRESENT'),
                       (config_present,'STATIC_CONFIG_PRESENT'),(document_two_links,'CHAIN_DOCUMENT_PRESENT')]
    if mode=='WRITER':
        def other_bytes(host):host.tree.add(k4f.writer_path(m),kind='file',mode=0o600,content=b'x')
        def wrong_mode(host):host.tree.add(k4f.writer_path(m),kind='file',mode=0o644,content=m.writer_bytes())
        def config_mode(host):host.tree.get(k4f.CONFIG).mode=0o750
        return common+[(other_bytes,'WRITER_PRESENT'),(wrong_mode,'WRITER_PRESENT'),(config_mode,'PARENT_IDENTITY_MISMATCH')]
    if mode=='LAUNCHER':
        def present(host):host.tree.add(k4f.LAUNCHER_DIRECTORY,mode=0o700);host.tree.add(k4f.LAUNCHER_DIRECTORY+'/other',kind='file',mode=0o600)
        def present_other_bytes(host):host.tree.add(k4f.LAUNCHER_DIRECTORY,mode=0o700);host.tree.add(k4f.LAUNCHER_FILE,kind='file',mode=0o600,content=b'x')
        def present_extra(host):
            host.tree.add(k4f.LAUNCHER_DIRECTORY,mode=0o700);host.tree.add(k4f.LAUNCHER_FILE,kind='file',mode=0o600,content=k4f.LAUNCHER)
            host.tree.add(k4f.LAUNCHER_DIRECTORY+'/x',kind='file',mode=0o600)
        def present_open(host):host.tree.add(k4f.LAUNCHER_DIRECTORY,mode=0o755)
        def present_file(host):host.tree.add(k4f.LAUNCHER_DIRECTORY,kind='file')
        def reader_mode(host):host.tree.get(k4f.READER).mode=0o750
        return common+[(present,'LAUNCHER_DIRECTORY_PRESENT'),(present_other_bytes,'LAUNCHER_DIRECTORY_PRESENT'),(present_extra,'LAUNCHER_DIRECTORY_PRESENT'),
                       (present_open,'LAUNCHER_DIRECTORY_PRESENT_INVALID'),(present_file,'LAUNCHER_DIRECTORY_PRESENT_INVALID'),(reader_mode,'PARENT_IDENTITY_MISMATCH')]
    def pins_present(host):host.tree.add(k4f.PINS,kind='file',mode=0o600,content=b'x')
    def no_launcher_directory(host):host.tree.remove(k4f.LAUNCHER_DIRECTORY)
    def launcher_directory_mode(host):host.tree.get(k4f.LAUNCHER_DIRECTORY).mode=0o755
    def launcher_directory_link(host):
        host.tree.remove(k4f.LAUNCHER_DIRECTORY);host.tree.add(k4f.LAUNCHER_DIRECTORY,kind='symlink',mode=0o777)
    def launcher_directory_owner(host):host.tree.get(k4f.LAUNCHER_DIRECTORY).uid=1000
    def launcher_directory_file(host):
        host.tree.remove(k4f.LAUNCHER_DIRECTORY);host.tree.add(k4f.LAUNCHER_DIRECTORY,kind='file',mode=0o700)
    def no_launcher(host):host.tree.remove(k4f.LAUNCHER_FILE)
    def launcher_bytes(host):host.tree.get(k4f.LAUNCHER_FILE).content=bytearray(k4f.LAUNCHER+b'#')
    def launcher_mode(host):host.tree.get(k4f.LAUNCHER_FILE).mode=0o644
    def launcher_links(host):host.tree.get(k4f.LAUNCHER_FILE).nlink=2
    def launcher_group(host):host.tree.get(k4f.LAUNCHER_FILE).gid=1000
    def launcher_link(host):
        host.tree.remove(k4f.LAUNCHER_FILE);host.tree.add(k4f.LAUNCHER_FILE,kind='symlink',mode=0o777)
    def launcher_fifo(host):
        host.tree.remove(k4f.LAUNCHER_FILE);host.tree.add(k4f.LAUNCHER_FILE,kind='fifo',mode=0o600)
    def no_config(host):host.tree.remove(k4f.STATIC)
    def config_bytes(host):host.tree.get(k4f.STATIC).content=bytearray(b'{}')
    def config_owner(host):host.tree.get(k4f.STATIC).uid=1000
    def config_large(host):host.tree.get(k4f.STATIC).content=bytearray(b' '*16385)
    def no_producer(host):host.tree.remove(k4f.UNITS+'/c3po-massive.service')
    def producer_bytes(host):host.tree.get(k4f.UNITS+'/c3po-massive.service').content+=b'#'
    def producer_mode(host):host.tree.get(k4f.UNITS+'/c3po-massive.service').mode=0o664
    def reader_bytes(host):host.tree.get(k4f.UNITS+'/c3po-reader.service').content+=b'#'
    def reader_unit_mode(host):host.tree.get(k4f.UNITS+'/c3po-reader.service').mode=0o600
    def no_reader_unit(host):host.tree.remove(k4f.UNITS+'/c3po-reader.service')
    def units_mode(host):host.tree.get(k4f.UNITS).mode=0o775
    def source_root_replaced(host):host.tree.get(k4f.SOURCE_ROOT).ino+=1
    def source_root_missing(host):host.tree.remove(k4f.SOURCE_ROOT)
    def journal_mode(host):host.tree.get(k4f.JOURNAL_HOST).mode=0o755
    return common+[(pins_present,'PINS_ENV_PRESENT'),(no_launcher_directory,'LAUNCHER_DIRECTORY_ABSENT'),(launcher_directory_mode,'LAUNCHER_DIRECTORY_INVALID'),
                   (launcher_directory_link,'LAUNCHER_DIRECTORY_INVALID'),(launcher_directory_owner,'LAUNCHER_DIRECTORY_INVALID'),(launcher_directory_file,'LAUNCHER_DIRECTORY_INVALID'),
                   (no_launcher,'LAUNCHER_FILE_ABSENT'),(launcher_bytes,'LAUNCHER_FILE_NOT_THE_SIGNED_BYTES'),(launcher_mode,'LAUNCHER_FILE_METADATA'),
                   (launcher_links,'LAUNCHER_FILE_METADATA'),(launcher_group,'LAUNCHER_FILE_METADATA'),(launcher_link,'PRECHECK_OS_ERROR'),
                   (launcher_fifo,'LAUNCHER_FILE_METADATA'),(no_config,'STATIC_CONFIG_FILE_ABSENT'),(config_bytes,'STATIC_CONFIG_FILE_NOT_THE_SIGNED_BYTES'),
                   (config_owner,'STATIC_CONFIG_FILE_METADATA'),(config_large,'STATIC_CONFIG_FILE_METADATA'),(no_producer,'PRODUCER_UNIT_ABSENT'),
                   (producer_bytes,'PRODUCER_UNIT_NOT_THE_SIGNED_BYTES'),(producer_mode,'PRODUCER_UNIT_METADATA'),(reader_bytes,'READER_UNIT_NOT_THE_SIGNED_BYTES'),
                   (reader_unit_mode,'READER_UNIT_METADATA'),(no_reader_unit,'READER_UNIT_ABSENT'),(units_mode,'PARENT_IDENTITY_MISMATCH'),(source_root_replaced,'PARENT_IDENTITY_MISMATCH'),
                   (source_root_missing,'PARENT_MISSING'),(journal_mode,'PARENT_IDENTITY_MISMATCH')]

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_every_precheck_refusal_leaves_the_host_exactly_as_it_was(mode):
    m=k4f.K().m
    for prepare,code in precheck_cases(mode,m):
        m,docs,host=fresh(mode);prepare(host);before=k4f.state_of(host);receipt=docs.run(host)
        refused_untouched(receipt,host,before,code)
        assert not [entry for entry in host.log if entry[0] in ('mkdir','create','write','link','unlink','fsync')],prepare.__name__
    m,docs,host=fresh(mode);host.vfs[ROOT].f_bavail=256;assert docs.run(host)['status']==m.COMPLETE_STATUS

def unit_world(producer=None,reader=None):
    k,host=k4f.world('CHAIN_STATIC');host=k4f.delivered_before_pins(host,k.m,producer=producer,reader=reader)
    return f.Docs(k,k4f.fields(host,'PINS',k.m)),host

def test_the_two_unit_texts_must_bind_the_same_journal_and_the_delivered_trees():
    cases=[(k4f.producer_unit(source='/var/lib/c3po-bar/other'),None,'JOURNAL_BIND_MISMATCH'),
           (None,k4f.reader_unit(source='/var/lib/c3po-bar/other'),'JOURNAL_BIND_MISMATCH'),
           (k4f.producer_unit(journal='/c3po-journal'),None,'JOURNAL_BIND_MISMATCH'),(None,k4f.reader_unit(journal='/c3po-journal'),'JOURNAL_BIND_MISMATCH'),
           (k4f.producer_unit().replace(b'--journal-root /c3po-bar-journal ',b'--journal-root /c3po-other '),None,'JOURNAL_BIND_MISMATCH'),
           (None,k4f.reader_unit().replace(b'/c3po-bar-journal,readonly',b'/c3po-bar-journal'),'JOURNAL_BIND_MISMATCH'),
           (k4f.producer_unit()+k4f.producer_unit(),None,'JOURNAL_BIND_MISMATCH'),
           (k4f.producer_unit().replace(b'target=/c3po-bar-journal \\\n',b'target=/c3po-bar-journal2 \\\n'),None,'JOURNAL_BIND_MISMATCH'),
           (None,k4f.reader_unit(capacity='/var/lib/c3po-capacity-other'),'READER_UNIT_MOUNTS_MISMATCH'),
           (None,k4f.reader_unit(source_root='/mnt/day-d-data/r2d2-v2-source-20261005'),'READER_UNIT_MOUNTS_MISMATCH'),
           (None,k4f.reader_unit(source_target='/c3po-sources'),'READER_UNIT_MOUNTS_MISMATCH'),
           (k4f.producer_unit(source='/mnt/day-d-data/journal'),k4f.reader_unit(source='/mnt/day-d-data/journal'),'JOURNAL_BIND_MISMATCH'),
           (None,k4f.reader_unit(launcher='/etc/c3po-reader'),'READER_UNIT_MOUNTS_MISMATCH'),
           (None,k4f.reader_unit().replace(b'target=/c3po-capacity,readonly',b'target=/c3po-capacity'),'READER_UNIT_MOUNTS_MISMATCH'),
           (None,k4f.reader_unit().replace(b'target=/c3po-reader,readonly',b'target=/c3po-reader'),'READER_UNIT_MOUNTS_MISMATCH'),
           (k4f.producer_unit()+b'\xff',None,'JOURNAL_BIND_MISMATCH'),(None,k4f.reader_unit()+b'\xc3\xa9','JOURNAL_BIND_MISMATCH')]
    for producer,reader,code in cases:
        docs,host=unit_world(producer,reader);before=k4f.state_of(host);receipt=docs.run(host);refused_untouched(receipt,host,before,code)

S_RENDER=WORK/'once-e3-20261004-a'/'PARAMETERS.json'
S_READER_UNIT=S_RDR.parent/'c3po-reader.service'
@pytest.mark.skipif(not (S_RENDER.is_file() and S_READER_UNIT.is_file()),reason='the installed producer render and the reader template are not on this machine')
def test_the_real_templates_rendered_with_this_epoch_s_values_pass_the_unit_guards():
    import base64 as b64
    m=k4f.K().m;parameters=json.loads(S_RENDER.read_bytes())['plan']['units'][0];text=b64.b64decode(parameters['template_b64']).decode()
    values=dict(parameters['placeholders'],IMAGE_ID='sha256:'+'1'*64)
    for name,value in values.items():text=text.replace('@'+name+'@',value)
    assert '@' not in text and '@' not in json.dumps(parameters['placeholders'])
    reader=S_READER_UNIT.read_text()
    for name,value in (('IMAGE_ID','sha256:'+'1'*64),('HOST_DATA_ROOT','/mnt/day-d-data'),('HOST_JOURNAL_ROOT','/var/lib/c3po-bar/journal'),
                       ('CONTAINER_JOURNAL_ROOT','/c3po-bar-journal'),('HOST_CAPACITY_ROOT','/var/lib/c3po-capacity'),('HOST_CONFIG_DIR','/etc/c3po-reader'),
                       ('NETWORK','bridge')):reader=reader.replace('@'+name+'@',value)
    # the reader template as it stands has no bind of the source root (decision 6 moved it off the data volume): refused
    assert f.refusal(lambda:m.journal_and_mounts(text,reader,k4f.pins_values(m),'/var/lib/c3po-capacity'))=='READER_UNIT_MOUNTS_MISMATCH'
    line='  --mount type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly \\\n'
    assert reader.count(line)==1
    reader=reader.replace(line,'  --mount type=bind,source=/var/lib/c3po/r2d2-v2-source-20261005,target=/c3po-source,readonly \\\n'+line)
    assert m.journal_and_mounts(text,reader,k4f.pins_values(m),'/var/lib/c3po-capacity')=='/var/lib/c3po-bar/journal'
    assert f.refusal(lambda:m.journal_and_mounts(text,reader,k4f.pins_values(m,C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/c3po-journal'),'/var/lib/c3po-capacity'))=='JOURNAL_BIND_MISMATCH'

def test_order_of_the_precheck():
    m,docs,host=fresh('PINS');host.actor=(1000,0);host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'x');receipt=docs.run(host)
    assert receipt['code']=='EXECUTOR_IDENTITY' and host.log==[]
    m,docs,host=fresh('PINS');host.tree.add(k4f.PINS,kind='file');host.tree.remove(k4f.LAUNCHER_FILE);assert docs.run(host)['code']=='PINS_ENV_PRESENT'
    m,docs,host=fresh('PINS');host.tree.remove(k4f.LAUNCHER_FILE);host.tree.remove(k4f.STATIC);assert docs.run(host)['code']=='LAUNCHER_FILE_ABSENT'
    m,docs,host=fresh('PINS');host.tree.remove(k4f.STATIC);host.tree.remove(k4f.UNITS+'/c3po-massive.service');assert docs.run(host)['code']=='STATIC_CONFIG_FILE_ABSENT'
    m,docs,host=fresh('PINS');host.tree.remove(k4f.UNITS+'/c3po-massive.service');host.tree.remove(k4f.UNITS+'/c3po-reader.service')
    assert docs.run(host)['code']=='PRODUCER_UNIT_ABSENT'
    m,docs,host=fresh('PINS');host.tree.get(k4f.UNITS+'/c3po-reader.service').content+=b'#';host.vfs[ROOT].f_bavail=0
    assert docs.run(host)['code']=='READER_UNIT_NOT_THE_SIGNED_BYTES'
    m,docs,host=fresh('CHAIN_STATIC');host.tree.add(k4f.STATIC,kind='file');host.tree.add(chain_paths(m)[2],kind='file');assert docs.run(host)['code']=='CHAIN_DOCUMENT_PRESENT'
    m,docs,host=fresh('CHAIN_STATIC');host.tree.add(k4f.STATIC,kind='file');host.vfs[ROOT].f_bavail=0;assert docs.run(host)['code']=='STATIC_CONFIG_PRESENT'
    m,docs,host=fresh('CHAIN_STATIC');host.tree.get(k4f.CONFIG).ino+=1;host.tree.add(chain_paths(m)[0],kind='file');assert docs.run(host)['code']=='PARENT_IDENTITY_MISMATCH'
    m,docs,host=fresh('LAUNCHER');host.tree.add(k4f.LAUNCHER_DIRECTORY);host.vfs[ROOT].f_bavail=0;assert docs.run(host)['code']=='LAUNCHER_DIRECTORY_PRESENT_INVALID'

def test_the_gate_is_asked_before_each_name_is_looked_at_and_each_file_is_read():
    for mode,target in (('CHAIN_STATIC',('lstat',k4f.STATIC)),('LAUNCHER',('lstat',k4f.LAUNCHER_DIRECTORY)),('PINS',('lstat',k4f.PINS)),
                        ('PINS',('open',k4f.LAUNCHER_DIRECTORY)),('PINS',('open',k4f.LAUNCHER_FILE)),('PINS',('open',k4f.UNITS+'/c3po-reader.service'))):
        m,docs,host=fresh(mode);before=k4f.state_of(host);plan,real=docs.authenticate()
        seen=[]
        def checking():
            seen.append(len(host.log));return real()
        receipt=docs.perform(host,gate=checking);assert receipt['status']==m.COMPLETE_STATUS
        index=[entry[:2] for entry in host.log].index(target);assert index in seen,(mode,target)

def test_budget_is_the_last_refusal_before_the_first_creation():
    for mode in MODES:
        for elapsed,ok in ((0.0,True),(45.0,True),(45.5,False)):
            m,docs,host=fresh(mode);before=k4f.state_of(host);mono=[0.0];plan,gate=docs.authenticate(monotonic=lambda:mono[0]);mono[0]=elapsed
            receipt=docs.perform(host,gate=gate,monotonic=lambda:mono[0])
            if ok:assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['seconds_left_before_first_effect']==int(60-elapsed)
            else:refused_untouched(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT');assert [entry[0] for entry in host.log][-1]=='fstatvfs'

def test_precheck_failure_of_any_kind_is_a_refusal_with_a_constant_code():
    for mode,name,target,error,code in (('CHAIN_STATIC','lstat',k4f.STATIC,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                                        ('CHAIN_STATIC','names',k4f.DOCUMENTS,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                                        ('PINS','read',None,OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),
                                        ('PINS','open',k4f.LAUNCHER_DIRECTORY,OSError(errno.EACCES,'injected'),'LAUNCHER_DIRECTORY_CHANGED_DURING_PRECHECK'),
                                        ('LAUNCHER','umask',None,RuntimeError('injected'),'PRECHECK_FAILED'),
                                        ('LAUNCHER','fstatvfs',None,RuntimeError('injected'),'PRECHECK_FAILED')):
        m,docs,host=fresh(mode);before=k4f.state_of(host)
        def hook(host,event,detail,calls,name=name,target=target,error=error):
            if event==name and (target is None or detail[0]==target):raise error
        host.hook=hook;receipt=docs.run(host);refused_untouched(receipt,host,before,code);assert 'injected' not in json.dumps(receipt)
    for action in (lambda host:host.tree.get(k4f.LAUNCHER_DIRECTORY).__setattr__('ino',host.tree.get(k4f.LAUNCHER_DIRECTORY).ino+1000),
                   lambda host:host.tree.get(k4f.LAUNCHER_DIRECTORY).__setattr__('mode',0o755)):
        m,docs,host=fresh('PINS');armed=[False]
        def hook(host,event,detail,calls,action=action):
            if event=='open' and detail[0]==k4f.LAUNCHER_DIRECTORY and not armed[0]:armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==('REFUSED','LAUNCHER_DIRECTORY_CHANGED_DURING_PRECHECK') and host.mutating()==[] and host.fds=={}
    m,docs,host=fresh('PINS');armed=[False]
    def changed(host,event,detail,calls):
        if event=='read' and not armed[0] and ('open',k4f.STATIC) in [entry[:2] for entry in host.log]:
            armed[0]=True;host.tree.get(k4f.STATIC).mtime+=1
    host.hook=changed;receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','STATIC_CONFIG_FILE_METADATA')


# ---------------------------------------------------------------- after the precheck
@pytest.mark.parametrize('position',range(8))
def test_chain_documents_a_name_that_appears_before_its_creation_is_left_alone(position):
    m,docs,host=fresh('CHAIN_STATIC');path=targets('CHAIN_STATIC',m)[position]
    host.hook=on('link',path.rsplit('/',1)[0]+'/.hostops-%s-%d.partial'%(docs.go16(),position),lambda host:host.tree.add(path,kind='file',uid=1000,content=b'foreign'))
    receipt=docs.run(host)
    partial(receipt,'DESTINATION_APPEARED_AFTER_PRECHECK',position)     # the own temporary was created and withdrawn: never a refusal
    assert receipt['ledger'][position]['temporary_removed'] is True
    assert [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*position+['NOT_CREATED']+['NOT_ATTEMPTED']*(7-position)
    assert bytes(host.tree.get(path).content)==b'foreign' and host.tree.get(path).uid==1000 and host.fds=={}
    for later in targets('CHAIN_STATIC',m)[position+1:]:assert host.tree.get(later) is None

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_failures_while_a_file_is_written_withdraw_only_the_temporary_of_this_run(mode):
    for event,number,code in (('write',errno.ENOSPC,'FILESYSTEM_FULL'),('fsync',errno.EIO,'FSYNC_FAILED'),('create',errno.EROFS,'FILESYSTEM_READ_ONLY')):
        m,docs,host=fresh(mode);first=targets(mode,m)[0].rsplit('/',1)[0];seen=[0]
        def hook(host,name,detail,calls,event=event,number=number,first=first):
            if name==event and detail and detail[0].startswith(first+'/.hostops-'):
                seen[0]+=1
                if seen[0]==1:raise OSError(number,'injected')
        host.hook=hook;receipt=docs.run(host)
        if mode=='LAUNCHER':partial(receipt,code,1);assert host.tree.get(k4f.LAUNCHER_DIRECTORY).children=={}
        elif event=='create':
            assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'EFFECTS'),(mode,event,receipt['code'])
        else:partial(receipt,code,0);assert receipt['ledger'][0]['temporary_removed'] is True    # created and withdrawn: never a refusal
        assert receipt['ledger'][0]['state']=='NOT_CREATED' and all(row['state']=='NOT_ATTEMPTED' for row in receipt['ledger'][1:])
        assert host.fds=={} and not [name for name in host.tree.get(first).children if name.startswith('.hostops-')]

def test_launcher_directory_that_is_not_what_was_signed_stops_the_run_before_the_file():
    for prepare,code in ((lambda host:setattr(host,'creator',(0,1000)),'CREATED_METADATA_MISMATCH'),
                         (lambda host:setattr(host,'created_device',hostemu.DATA_DEVICE),'CREATED_METADATA_MISMATCH')):
        m,docs,host=fresh('LAUNCHER');prepare(host);receipt=docs.run(host);partial(receipt,code,1)
        assert receipt['ledger']==[{'key':'LAUNCHER','path':k4f.LAUNCHER_FILE,'state':'NOT_ATTEMPTED','code':None}] and host.tree.get(k4f.LAUNCHER_DIRECTORY).children=={}
    m,docs,host=fresh('LAUNCHER')
    def hook(host,name,detail,calls):
        if name=='mkdir':raise OSError(errno.ENOSPC,'injected')
    host.hook=hook;receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','FILESYSTEM_FULL') and host.tree.get(k4f.LAUNCHER_DIRECTORY) is None
    m,docs,host=fresh('LAUNCHER');host.hook=on('mkdir',k4f.LAUNCHER_DIRECTORY,lambda host:host.tree.add(k4f.LAUNCHER_DIRECTORY,uid=1000));receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_APPEARED_AFTER_PRECHECK') and host.tree.get(k4f.LAUNCHER_DIRECTORY).uid==1000

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_readback_inside_the_run_catches_what_changed_after_delivery(mode):
    m=k4f.K().m;last=targets(mode,m)[-1];directory=last.rsplit('/',1)[0]
    def tamper(host):host.tree.get(last).content=bytearray(b'tampered')
    def foreign(host):host.tree.add(directory+'/foreign',kind='file')
    def parent_mode(host):host.tree.get({'CHAIN_STATIC':k4f.CONFIG,'PINS':k4f.READER,'LAUNCHER':k4f.READER,'WRITER':k4f.CONFIG}[mode]).mode=0o750
    cases=[(tamper,'READBACK_HASH_MISMATCH',('open',last)),(parent_mode,'READBACK_MISMATCH' if mode in ('CHAIN_STATIC','WRITER') else 'PARENT_REPLACED',('open',last))]
    if mode!='PINS':cases.append((foreign,'READBACK_MISMATCH',('names',directory)))
    for action,code,when in cases:
        m,docs,host=fresh(mode);armed=[False];unlinks=len(targets(mode,m))
        def hook(host,name,detail,calls,when=when,action=action):
            if not armed[0] and len([entry for entry in host.log if entry[0]=='unlink'])==unlinks and (name,detail[0] if detail else None)==when:
                armed[0]=True;action(host)
        host.hook=hook;receipt=docs.run(host)
        assert armed[0],(mode,code);partial(receipt,code,len(targets(mode,m))+(mode=='LAUNCHER'))
        assert all(row['state']=='INSTALLED_DURABLE' for row in receipt['ledger'])

def test_the_gate_is_asked_immediately_before_every_call_that_changes_the_host():
    for mode in MODES:
        m,docs,host=fresh(mode);plan,real=docs.authenticate();asked=[]
        def gate():
            asked.append(len(host.log));return real()
        receipt=docs.perform(host,gate=gate);assert receipt['status']==m.COMPLETE_STATUS
        for index,entry in enumerate(host.log):
            if entry[0] in ('mkdir','create','write','link','unlink'):assert index in asked,entry


# ---------------------------------------------------------------- crash points and expiry
def total_calls(mode):
    m,docs,host=fresh(mode);names=[]
    def hook(host,name,detail,calls):names.append(name)
    host.hook=hook;assert docs.run(host)['status']==m.COMPLETE_STATUS;return len(names)

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_process_death_at_every_host_call_is_a_refusal_only_while_nothing_exists(mode):
    total=total_calls(mode);statuses=set()
    for index in range(1,total+1):
        m,docs,host=fresh(mode);before=k4f.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);unchanged=k4f.state_of(host)==before;statuses.add(receipt['status'])
        assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and (receipt['status']!='REFUSED' or unchanged),(mode,index)
        for path,raw in zip(targets(mode,m),contents(mode,m,docs)):
            node=host.tree.get(path)
            if node is not None:assert bytes(node.content)==raw and (node.uid,node.gid,node.mode)==(0,0,0o600),'a final name only ever holds the signed bytes'
    assert statuses=={'REFUSED',m.PARTIAL_STATUS}

@pytest.mark.parametrize('mode',MODES,ids=['chain','pins','launcher','writer'])
def test_expiry_or_a_reversed_clock_at_every_gate_is_a_refusal_only_while_nothing_exists(mode):
    m,docs,host=fresh(mode);count=[0]
    def counting():
        count[0]+=1;return 0.0
    assert docs.run(host,monotonic=counting)['status']==m.COMPLETE_STATUS;total=count[0]
    for expired,code in ((61.0,'GO_EXPIRED'),(-1.0,'CLOCK_REVERSED')):
        for index in range(4,total,max(1,total//60)):
            m,docs,host=fresh(mode);before=k4f.state_of(host);count=[0]
            def monotonic(index=index):
                count[0]+=1;return expired if count[0]==index else (0.0 if count[0]<index else 61.0)
            receipt=docs.run(host,monotonic=monotonic)
            assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS) and receipt['code'] in (code,'GO_EXPIRED'),(index,receipt['code'])
            assert (receipt['status']=='REFUSED')==(k4f.state_of(host)==before) and host.fds=={} and f.sealed(receipt)

def test_escape_after_an_effect_is_partial_and_before_any_is_a_refusal():
    m,docs,host=fresh('CHAIN_STATIC');second=chain_paths(m)[1].rsplit('/',1)[0]+'/.hostops-%s-1.partial'%docs.go16()
    def hook(host,name,detail,calls):
        if name=='create' and detail[0]==second:raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
    m,docs,host=fresh('PINS')
    def early(host,name,detail,calls):
        if name=='fstatvfs':raise KeyboardInterrupt()
    host.hook=early;before=k4f.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and k4f.state_of(host)==before


# ---------------------------------------------------------------- no second attempt; the chain B5 -> A8 -> B6
def test_a_second_request_changes_nothing_and_the_three_modes_chain_on_one_host():
    """Files an earlier run of the same signed bytes delivered are found equal and kept (PRESENT_EQUAL); nothing is
    created, nothing replaced. The order B5 -> A8 -> B6 on one host, pins.env naming what the two earlier runs made."""
    k,host=k4f.world('CHAIN_STATIC');m=k.m
    host.tree.add(k4f.UNITS+'/c3po-massive.service',kind='file',mode=0o644,content=k4f.producer_unit())
    host.tree.add(k4f.UNITS+'/c3po-reader.service',kind='file',mode=0o644,content=k4f.reader_unit())
    first=f.Docs(k,k4f.fields(host,'CHAIN_STATIC',m));assert first.run(host)['status']==m.COMPLETE_STATUS
    for minutes,mode in ((10,'CHAIN_STATIC'),(20,'LAUNCHER'),(25,'LAUNCHER'),(30,'PINS'),(35,'PINS')):
        docs=f.Docs(k,k4f.fields(host,mode,m),now=first.now+timedelta(minutes=minutes));before=k4f.state_of(host);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS,(mode,receipt['code'])
        if minutes in (10,25,35):
            assert k4f.state_of(host)==before and receipt['mutating_calls']['issued']==0 and receipt['objects_left_by_this_run']==0
            assert all(row['state']=='PRESENT_EQUAL' for row in receipt['ledger']) and not any(row['created_by_this_run'] for row in receipt['delivered']['files'])
    raw=bytes(host.tree.get(k4f.PINS).content)
    assert (b'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+f.sha(bytes(host.tree.get(k4f.STATIC).content)).encode()+b'\n') in raw
    assert (b'C3PO_READER_LAUNCHER_SHA256='+f.sha(bytes(host.tree.get(k4f.LAUNCHER_FILE).content)).encode()+b'\n') in raw

@pytest.mark.parametrize('kept',[1,4,7])
def test_a_partial_chain_delivery_is_completed_by_the_same_bytes_without_touching_what_is_there(kept):
    m,docs,host=fresh('CHAIN_STATIC');paths=targets('CHAIN_STATIC',m);raws=contents('CHAIN_STATIC',m,docs)
    for path,raw in list(zip(paths,raws))[:kept]:host.tree.add(path,kind='file',mode=0o600,content=raw)
    host.tree.add(k4f.DOCUMENTS+'/.hostops-0123456789abcdef-%d.partial'%kept,kind='file',mode=0o600,content=b'half')     # the leftover of the step that died
    nodes=[host.tree.get(path) for path in paths[:kept]];identities=[(node.ino,node.mtime) for node in nodes]
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS,receipt['code']
    assert [row['state'] for row in receipt['ledger']]==['PRESENT_EQUAL']*kept+['INSTALLED_DURABLE']*(8-kept)
    assert [(node.ino,node.mtime) for node in nodes]==identities and receipt['objects_left_by_this_run']==8-kept
    assert receipt['mutating_calls']['succeeded']==4*(8-kept) and receipt['delivered']['entries_after']=={'DOCUMENTS':8,'CONFIG':1}
    assert [row['created_by_this_run'] for row in receipt['delivered']['files']]==[False]*kept+[True]*(8-kept)
    for path,raw in zip(paths,raws):assert bytes(host.tree.get(path).content)==raw

def test_a_partial_launcher_delivery_is_completed():
    m,docs,host=fresh('LAUNCHER');host.tree.add(k4f.LAUNCHER_DIRECTORY,mode=0o700);node=host.tree.get(k4f.LAUNCHER_DIRECTORY)
    receipt=docs.run(host);assert receipt['status']==m.COMPLETE_STATUS and receipt['directories']==[] and host.tree.get(k4f.LAUNCHER_DIRECTORY) is node
    assert receipt['precheck']['launcher_directory']=='PRESENT_PRIVATE' and [entry[0] for entry in host.mutating()]==['create','write','link','unlink']
    assert bytes(host.tree.get(k4f.LAUNCHER_FILE).content)==k4f.LAUNCHER

def test_a_file_found_equal_that_changes_before_the_readback_is_seen():
    m,docs,host=fresh('CHAIN_STATIC');paths=targets('CHAIN_STATIC',m);raws=contents('CHAIN_STATIC',m,docs)
    host.tree.add(paths[0],kind='file',mode=0o600,content=raws[0])
    def change(host):host.tree.get(paths[0]).content=bytearray(b'changed')
    host.hook=on('create',k4f.CONFIG+'/.hostops-%s-7.partial'%docs.go16(),change)
    receipt=docs.run(host);partial(receipt,'READBACK_HASH_MISMATCH',7)

def test_pins_inputs_that_change_after_they_were_read_are_seen():
    for path in (k4f.LAUNCHER_FILE,k4f.STATIC,k4f.UNITS+'/c3po-massive.service',k4f.UNITS+'/c3po-reader.service'):
        m,docs,host=fresh('PINS')
        def change(host,path=path):host.tree.get(path).ctime+=1
        host.hook=on('link',k4f.READER+'/.hostops-%s-0.partial'%docs.go16(),change);receipt=docs.run(host)
        partial(receipt,'PINS_INPUT_CHANGED',1);assert bytes(host.tree.get(k4f.PINS).content)==k4f.render(docs.plan['delivery']['values'],m)

def test_pins_judges_the_capacity_config_it_reads_on_the_host():
    k,host=k4f.world('CHAIN_STATIC');m=k.m
    for config,code in ((k4f.static_config(m,release_sha='3'*64),'STATIC_CONFIG_RELEASE'),(b'{"x":1}','STATIC_CONFIG_INVALID')):
        k,host=k4f.world('CHAIN_STATIC');k4f.delivered_before_pins(host,m,config=config);docs=f.Docs(k,k4f.fields(host,'PINS',m))
        values=k4f.pins_values(m,config=config);raw=k4f.render(values,m)
        docs.plan['delivery'].update(values=values,sha256=f.sha(raw),bytes=len(raw));docs.chain();before=k4f.state_of(host)
        refused_untouched(docs.run(host),host,before,code)

def test_capacity_config_identity_and_roots_are_judged_as_the_packaged_loader_does():
    m=k4f.K().m;base=json.loads(k4f.static_config(m))
    def judged(change):
        value=copy.deepcopy(base);change(value);return f.refusal(lambda:m.static_config_of(f.canonical(value)))
    assert judged(lambda value:value['identity'].update(extra='x'))=='STATIC_CONFIG_IDENTITY'
    assert judged(lambda value:value['identity'].pop('runtime_order_sha'))=='STATIC_CONFIG_IDENTITY'
    assert judged(lambda value:value['identity'].update(document_order_sha='0'*64))=='STATIC_CONFIG_IDENTITY'
    assert judged(lambda value:value['identity'].update(runtime_order_sha='x'))=='STATIC_CONFIG_IDENTITY'
    assert judged(lambda value:value['roots']['go'].update(identity=None))=='STATIC_CONFIG_ROOTS'
    assert judged(lambda value:value['roots']['documents'].update(identity='0'*64))=='STATIC_CONFIG_ROOTS'

def test_unit_guards_read_only_the_command_lines():
    commented=k4f.reader_unit().replace(b'  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal,readonly \\\n',b'')
    commented+=b'#  --mount type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal,readonly \\\n'
    docs,host=unit_world(None,commented);before=k4f.state_of(host);refused_untouched(docs.run(host),host,before,'JOURNAL_BIND_MISMATCH')
    doubled=k4f.reader_unit().replace(b'  --mount type=bind,source=/var/lib/c3po-capacity,',
                                      b'  --mount type=bind,source=/var/lib/c3po-bar/other,target=/c3po-bar-journal,readonly \\\n  --mount type=bind,source=/var/lib/c3po-capacity,')
    docs,host=unit_world(None,doubled);before=k4f.state_of(host);refused_untouched(docs.run(host),host,before,'JOURNAL_BIND_MISMATCH')
    twice=k4f.producer_unit()+b'# --journal-root /c3po-other \n'
    docs,host=unit_world(twice,None);before=k4f.state_of(host);refused_untouched(docs.run(host),host,before,'JOURNAL_BIND_MISMATCH')

def test_pins_refused_while_the_capacity_config_on_the_host_is_not_the_signed_one():
    k,host=k4f.world('CHAIN_STATIC');m=k.m;k4f.delivered_before_pins(host,m)
    other=k4f.static_config(m,calendar_pin_sha=k4f.label('another calendar'));docs=f.Docs(k,k4f.fields(host,'PINS',m))
    docs.plan['delivery']['values']['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA']=f.sha(other);raw=k4f.render(docs.plan['delivery']['values'],m)
    docs.plan['delivery'].update(sha256=f.sha(raw),bytes=len(raw));docs.chain();before=k4f.state_of(host)
    refused_untouched(docs.run(host),host,before,'STATIC_CONFIG_FILE_NOT_THE_SIGNED_BYTES')


def test_free_space_is_checked_on_every_filesystem_that_receives_a_file():
    k,host=k4f.world('CHAIN_STATIC');m=k.m;host.tree.get(k4f.CONFIG).dev=hostemu.DATA_DEVICE
    docs=f.Docs(k,k4f.fields(host,'CHAIN_STATIC',m));host.vfs[hostemu.DATA_DEVICE].f_bavail=255;before=k4f.state_of(host)
    refused_untouched(docs.run(host),host,before,'FREE_SPACE_BELOW_FLOOR')
    host.vfs[hostemu.DATA_DEVICE].f_bavail=256;assert docs.run(host)['precheck']['free_bytes']==[145315507*4096,256*4096]


def test_writer_complete_run_and_its_literal_effects():
    m,docs,host=fresh('WRITER');raw=m.writer_bytes();path=k4f.writer_path(m);before=k4f.state_of(host)
    assert f.sha(raw)=='aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387' and len(raw)==46977
    assert docs.go['effects']=={'operation':'GO_WRITE_HOSTOPS02_K4_FILES_01','epoch':'R2D2-V2-SHADOW-2026-10-05','mode':'WRITER',
        'files':[{'path':path,'sha256':f.sha(raw),'bytes':len(raw),'mode_octal':'0600','uid':0,'gid':0,'links':1,'expect':'ABSENT','key':'WRITER'}],
        'evidence_boot_id_sha256':f.BOOT_SHA,'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,
        'process_started':False,'config_parent':m.chain_effects(docs.plan['delivery']['config_parent']),'directories':[],
        'writer':{'path_in_containers':'/c3po-capacity/config/manifest_writer-'+f.sha(raw)+'.py','compiled':True}}
    assert len(docs.raw()[0])<20000,'the writer travels in the source, not in the request'
    receipt=docs.run(host);assert (receipt['status'],receipt['code'],receipt['mode'])==(m.COMPLETE_STATUS,None,'WRITER')
    node=host.tree.get(path);assert (node.kind,node.uid,node.gid,node.mode,node.nlink,bytes(node.content))==('file',0,0,0o600,1,raw)
    assert receipt['delivered']['entries_after']=={'CONFIG':1} and receipt['precheck']['entries_before']=={'CONFIG':0}
    host.tree.remove(path);assert k4f.state_of(host)==before
    m,docs,host=fresh('WRITER');host.tree.add(path,kind='file',mode=0o600,content=raw);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['mutating_calls']['issued']==0 and receipt['ledger'][0]['state']=='PRESENT_EQUAL'

def test_writer_block_is_the_reviewed_writer_of_the_capacity_day_readme():
    m=k4f.K().m;readme=Path(OPSART or '/nonexistent')/'c3po'/'deployment'/'capacity-day'/'README.md'
    if readme.is_file():assert m.K4_WRITER[0] in readme.read_text()
    saved=m.K4_WRITER
    try:
        m.K4_WRITER=('3'*64,)+saved[1:];assert f.refusal(m.writer_bytes)=='WRITER_NOT_THE_COMPILED_HASH'
        m.K4_WRITER=(saved[0],saved[1]+1,saved[2]);assert f.refusal(m.writer_bytes)=='WRITER_NOT_THE_COMPILED_HASH'
    finally:m.K4_WRITER=saved
