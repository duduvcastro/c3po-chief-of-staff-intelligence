"""Authority, once-dispatch, launcher and transport tests, for every operation of HOSTOPS01.
Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO.
Tests whose name contains "static" pin bytes and text; the mutation harness does not count them."""
import ast
from datetime import datetime,timedelta,timezone
import difflib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

import family as f
import hostemu

ROOT=f.ROOT
sys.path.insert(0,str(ROOT))
import assemble
sys.path.remove(str(ROOT))

OPS=f.OPS
WRITE_DAYS=('2026-10-02','2026-10-03','2026-10-04')
READ_DAYS=WRITE_DAYS+('2026-10-05',)
EXPECTED_LINES={True:[15,16,102,103,109,118,127,128,129,141,142,146,147,162,205,213,219,239],
                False:[15,16,102,103,109,118,127,128,129,141,146,147,162,205,213,219,239]}
ISOLATED=[sys.executable,'-I','-B','-']
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}

class Untouchable:
    def __getattr__(self,name):raise AssertionError('host touched: '+name)

def refusal(action):
    with pytest.raises(ValueError) as caught:action()
    assert type(caught.value).__name__=='Refused',repr(caught.value)
    return str(caught.value)

def auth_raw(k,raws,**extra):
    pins=k.m.Pins(payload=f.sha(k.source),request=f.sha(raws[0]),authority=f.sha(raws[1]),go=f.sha(raws[2]))
    options=dict(clock=lambda:f.NOW,monotonic=lambda:0,executor_uid=lambda:0);options.update(extra)
    return k.m.authenticate(*raws,pins=pins,payload_bytes=k.source,**options)

@pytest.fixture(params=OPS)
def case(request):
    docs,host=f.default_docs(request.param);return docs.k,docs,host


# ---------------------------------------------------------------- static pins (bytes and text)
@pytest.mark.parametrize('op',OPS)
def test_static_runtime_files_are_exactly_the_assembly_of_reviewed_bytes_and_parts(op):
    k=f.load(op);directory=ROOT/op
    assert assemble.source_bytes(op)==k.source
    dispatcher=(directory/'dispatch_once.py').read_bytes();assert assemble.dispatcher_bytes(op,k.m)==dispatcher
    assert (directory/'launcher_stdin.py').read_bytes()==assemble.launcher_bytes()
    assert (directory/'transport_once.py').read_bytes()==assemble.reviewed('transport_once.py') and f.sha(assemble.reviewed('transport_once.py'))==f.TRANSPORT_PIN
    base=assemble.reviewed('dispatch_once.py').decode().splitlines();new=dispatcher.decode().splitlines()
    assert len(base)==len(new) and [index+1 for index,(a,b) in enumerate(zip(base,new)) if a!=b]==EXPECTED_LINES[k.m.WRITES_ALLOWED]
    assert (directory/'DISPATCH_SCOPE_DELTA.diff').read_bytes()==assemble.diff(assemble.reviewed('dispatch_once.py'),dispatcher,
        'reviewed_supervisor_hostfacts/dispatch_once.py','hostops01/%s/dispatch_once.py'%op)

def test_static_launcher_delta_is_five_lines_and_templates_are_the_repository_bytes():
    base=assemble.reviewed('launcher_stdin.py').decode().splitlines();new=assemble.launcher_bytes().decode().splitlines()
    assert len(base)==len(new) and [index+1 for index,(a,b) in enumerate(zip(base,new)) if a!=b]==[30,32,33,35,38]
    assert (ROOT/'LAUNCHER_DELTA.diff').read_bytes()==assemble.diff(assemble.reviewed('launcher_stdin.py'),assemble.launcher_bytes(),
        'reviewed_supervisor_hostfacts/launcher_stdin.py','hostops01/launcher_stdin.py')
    assert f.sha(f.SERVICE)=='9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a'
    assert f.sha(f.TIMER)=='ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'

GENERATED=('dispatch_once.py','launcher_stdin.py','transport_once.py','DISPATCH_SCOPE_DELTA.diff','REQUEST.UNBOUND.json','AUTHORITY.UNBOUND.json',
           'GO.UNBOUND.json','DISPATCH.UNBOUND.json','PUBLICATION_PROOF.UNBOUND.json','FINAL_PAYLOAD.UNBOUND.py')
def test_static_assembly_yields_the_same_bytes_at_any_other_path_and_no_generated_file_names_a_path(tmp_path):
    """assemble.py, run in a copy of its inputs somewhere else, writes exactly the bytes of this directory: nothing
    generated depends on where the candidate lies, and nothing generated shows it."""
    copy=Path(str(tmp_path)).resolve()/'elsewhere'/'a copy';copy.mkdir(parents=True)
    for name in ('parts','reviewed_base','templates'):shutil.copytree(str(ROOT/name),str(copy/name))
    shutil.copy(str(ROOT/'assemble.py'),str(copy/'assemble.py'))
    done=subprocess.run([sys.executable,'-B','-W','error::SyntaxWarning',str(copy/'assemble.py')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        env=ENV,cwd=str(copy),timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    names=['LAUNCHER_DELTA.diff']+[op+'/'+name for op in OPS for name in GENERATED+(f.MODULES[op]+'.py',)]
    written=sorted(path.relative_to(copy).as_posix() for path in copy.rglob('*') if path.is_file() and path.relative_to(copy).parts[0] not in ('parts','reviewed_base','templates'))
    assert written==sorted(names+['assemble.py']),'every file the assembly writes is compared below'
    for name in names:
        raw=(ROOT/name).read_bytes();assert (copy/name).read_bytes()==raw,name
        # where this candidate lies, where the copy lies, and the top-level directories a workstation or a runner keeps its users in
        for word in (str(ROOT).encode(),str(copy).encode())+tuple(b'/'+top+b'/' for top in (b'Users',b'home',b'private')):assert word not in raw,(name,word)
    for op in OPS:
        config=json.loads((ROOT/op/'DISPATCH.UNBOUND.json').read_bytes())
        for key in ('source','request','authority','go','payload'):
            assert set(config[key])=={'path','sha256'} and config[key]['path'] is None and re.fullmatch('[0-9a-f]{64}',config[key]['sha256'])

@pytest.mark.parametrize('op',OPS)
def test_shipped_unbound_dispatch_template_is_refused_by_its_dispatcher_and_a_null_path_is_no_path(op,tmp_path):
    """The template names no file. The dispatcher refuses it as it is, before any claim; and a config that is bound
    in every other respect but still carries a null blob path is refused too."""
    k=f.load(op);root=Path(str(tmp_path)).resolve()/'template';root.mkdir(mode=0o700)
    raw=(ROOT/op/'DISPATCH.UNBOUND.json').read_bytes();path=root/'config';path.write_bytes(raw);path.chmod(0o600)
    for phase in ('prepare','resume'):
        assert refusal(lambda:k.d.execute(str(path),f.sha(raw),phase=phase,transport=f.never,clock=lambda:f.NOW,monotonic=lambda:0))=='DISPATCH_UNBOUND'
    assert sorted(item.name for item in root.iterdir())==['config'],'no claim and no attempt directory'
    docs,_=f.default_docs(op);directory=Path(str(tmp_path))/'bound';directory.mkdir()
    for key in ('source','request','authority','go','payload'):
        dispatch=f.Dispatch(docs,directory);dispatch.config[key]={'path':None,'sha256':dispatch.config[key]['sha256']}
        dispatch.pin=dispatch.put('config',f.canonical(dispatch.config))
        assert refusal(dispatch.prepare)=='LOCAL_PATH' and not dispatch.claims(),key

def blocks(source):
    return {name:body for name,body in re.findall(r'# ==== BEGIN ([A-Z_]+) \([^)]*\) ====\n(.*?)\n# ==== END \1 ====\n',source.decode(),re.S)}
def test_static_shared_parts_are_byte_identical_in_every_source_that_carries_them():
    seen={}
    for op in OPS:
        found=blocks(f.load(op).source);assert list(found)==[name.upper() for name in assemble.OPS[op]['parts']]
        for name,body in found.items():
            assert body==assemble.part(name.lower()).rstrip('\n')
            if not name.startswith('OP_'):assert seen.setdefault(name,body)==body
    assert set(seen)=={'CORE','RUNNER','LAYOUT','LISTING','SCAN','RENDER'}

ALLOWED_IMPORTS={'provision':{'dataclasses','datetime','errno','hashlib','json','os','pathlib','re','selectors','stat','subprocess','time'},
                 'install_units':{'base64','dataclasses','datetime','errno','hashlib','json','os','pathlib','re','stat','time'},
                 'readback':{'base64','dataclasses','datetime','errno','hashlib','json','os','pathlib','re','selectors','stat','subprocess','time'},
                 'precheck':{'dataclasses','datetime','errno','hashlib','json','os','pathlib','re','selectors','stat','subprocess','time'}}
READ={'O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK','O_RDONLY','close','fstat','fstatvfs','getegid','geteuid','open','read','scandir','stat'}
ALLOWED_OS={'provision':READ|{'set_blocking','fsync','mkdir','umask'},
            'install_units':READ|{'O_CLOEXEC','O_CREAT','O_EXCL','O_WRONLY','fsync','link','unlink','umask','write','readlink'},
            'readback':READ|{'set_blocking','readlink'},'precheck':READ|{'set_blocking','readlink'}}
SUBPROCESS={'DEVNULL','PIPE','Popen','TimeoutExpired'}
@pytest.mark.parametrize('op',OPS)
def test_static_source_is_stdlib_only_shell_free_and_calls_only_what_its_operation_needs(op):
    """By syntax tree, not by text: the exact import set, the exact set of os members, and the exact command tables."""
    k=f.load(op);tree=ast.parse(k.source.decode('ascii'))
    imports=set();attributes=set();names=set();process=set();keywords=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports|={alias.name for alias in node.names}
        elif isinstance(node,ast.ImportFrom):imports.add(node.module)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='os':attributes.add(node.attr)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='subprocess':process.add(node.attr)
        elif isinstance(node,ast.Name):names.add(node.id)
        elif isinstance(node,ast.keyword):keywords.add(node.arg)
        assert not isinstance(node,(ast.NamedExpr,ast.AsyncFunctionDef,ast.Await)),'python 3.7 syntax only'
    assert imports==ALLOWED_IMPORTS[op] and attributes==ALLOWED_OS[op]
    assert not names&{'eval','exec','compile','__import__','open','input','breakpoint','print','shutil','socket','ctypes'}
    assert 'shell' not in keywords and process==(SUBPROCESS if 'subprocess' in imports else set())
    if op=='install_units':assert not hasattr(k.m,'COMMANDS') and not hasattr(k.m,'Commands') and not hasattr(k.m.Native,'run')
    if not k.m.WRITES_ALLOWED:
        assert not [name for name in dir(k.m.Native) if name in ('mkdir','create','write','fsync','link','unlink','umask')]
    if op=='provision':assert not [name for name in dir(k.m.Native) if name in ('create','write','link','unlink')]
    # the only argv any source can start are rows of its signed table
    for name,(tool,arguments,_) in getattr(k.m,'COMMANDS',{}).items():
        assert tool in k.m.BINARIES and (tool!='systemctl' or arguments[0] in ('--version','show','is-enabled'))
        assert tool!='docker' or arguments[:2] in (['image','inspect'],['image','ls'],['image','tag'],['info','--format'],['version','--format'])
        assert (arguments[:2]==['image','tag'])==(op=='provision' and name=='image_tag')
    assert 'Env' not in ''.join(str(row) for row in getattr(k.m,'COMMANDS',{}).values())

@pytest.mark.parametrize('op',OPS)
def test_static_unbound_templates_hash_chain_and_null_bindings(op):
    k=f.load(op);directory=ROOT/op;m=k.m
    q,a,g,c,proof=[json.loads((directory/(name+'.UNBOUND.json')).read_bytes()) for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF')]
    digest=lambda name:f.sha((directory/name).read_bytes())
    assert a['request_sha256']==g['request_sha256']==c['request']['sha256']==digest('REQUEST.UNBOUND.json')
    assert g['authority_sha256']==c['authority']['sha256']==digest('AUTHORITY.UNBOUND.json')
    assert g['payload_sha256']==q['payload_sha256']==a['payload_sha256']==c['source']['sha256']==f.sha(k.source)
    assert c['go']['sha256']==proof['go_sha256']==digest('GO.UNBOUND.json') and proof['config_sha256']==digest('DISPATCH.UNBOUND.json')
    assert c['payload']['sha256']==digest('FINAL_PAYLOAD.UNBOUND.py')
    assert g['transport_binding']['runtime_sha256']==c['runtime_sha256']=={name:digest(name) for name in ('dispatch_once.py','transport_once.py','launcher_stdin.py',k.name)}
    assert c['runtime_sha256']['transport_once.py']==f.TRANSPORT_PIN
    assert q['scope_sha256']==m.SCOPE_SHA256 and m.canonical(q['plan']['scope'])==m.canonical(m.SCOPE)
    assert set(q)==set(m.REQUEST_KEYS) and set(a)==set(m.AUTHORITY_KEYS) and set(g)==set(m.GO_KEYS)
    assert set(q['plan'])==set(m.PLAN_COMMON_KEYS|m.PLAN_KEYS)
    for document,keys in ((q,('date','host_binding_sha256','not_before','not_after')),
                          (a,('owner','decision','effects','owner_evidence','host_binding_sha256','not_before','not_after')),
                          (g,('action','owner','effects','host_binding_sha256','not_before','not_after')),
                          (c,('attempt_directory','authorization_ref','command_sha256','host_binding_sha256','latest_start','not_before','not_after','owner','target')),
                          (proof,('intent_sha256','owner','publication_ref','published_at'))):
        assert all(document[key] is None for key in keys) and document['status']=='UNBOUND'
    assert q['plan']['status']=='UNBOUND' and q['plan']['host_binding_sha256'] is None and q['plan']['window']=={'expires_at':None,'not_before':None}
    assert q['evidence']==[] and g['claim_root_identity']==c['local_root_identity']=={'device':None,'inode':None,'path':None}
    # nothing that is observed on the host or decided by a signatory is pre-filled: only constants of the signed scope are
    if op in ('provision','precheck'):assert q['plan']['existing_journal_leaves'] is None and q['plan']['journal_leaf'] is None
    if op=='readback':
        assert q['plan']['mode'] is None and q['plan']['install']=={'outcome':None,'receipt_sha256':None} and g['success_criterion'] is None
        assert q['plan']['image_revision'] is None and q['plan']['sessions_retained'] is None and q['plan']['free_space_floor_bytes'] is None
    else:assert g['success_criterion']==m.COMPLETE_OUTCOME
    assert c['ssh_key']==c['known_hosts']=={'path':None,'sha256':None} and g['transport_binding']['target'] is None
    assert g['transport_binding']['command_sha256'] is None and a['execution_authorized'] is g['execution_authorized'] is False
    assert q['writes_allowed'] is a['writes_allowed'] is g['writes_allowed'] is m.WRITES_ALLOWED and q['activation_allowed'] is False
    for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF'):
        raw=(directory/(name+'.UNBOUND.json')).read_bytes();assert raw==m.canonical(json.loads(raw)) and b'SIGNED' not in raw and b'"BOUND"' not in raw
    raws=[(directory/(name+'.UNBOUND.json')).read_bytes() for name in ('REQUEST','AUTHORITY','GO')]
    assert k.l.build(k.source,*raws,expected_payload_sha256=f.sha(k.source),expected_request_sha256=f.sha(raws[0]),
                     expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))==(directory/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()

@pytest.mark.parametrize('op',OPS)
def test_static_dispatcher_date_set_is_the_source_date_set_and_names_are_disjoint(op):
    k=f.load(op);text=(ROOT/op/'dispatch_once.py').read_text()
    literal=re.search(r"start\.date\(\)\.isoformat\(\) in (\([^)]*\))",text).group(1)
    assert ast.literal_eval(literal)==k.m.DATES==(WRITE_DAYS if k.m.WRITES_ALLOWED else READ_DAYS)
    assert k.m.PRECHECK_OPERATION==f.load('precheck').m.OPERATION=='GO_READONLY_HOSTOPS_PRECHECK_01'
    mine={k.m.OPERATION,k.m.PHASE,k.m.REQUEST_SCHEMA,k.m.AUTHORITY_SCHEMA,k.m.GO_SCHEMA,k.m.RECEIPT_SCHEMA,k.m.PLAN_SCHEMA}
    for other in OPS:
        if other==op:continue
        o=f.load(other).m
        assert not mine&{o.OPERATION,o.PHASE,o.REQUEST_SCHEMA,o.AUTHORITY_SCHEMA,o.GO_SCHEMA,o.RECEIPT_SCHEMA,o.PLAN_SCHEMA}
    assert not any('HOSTFACTS' in name or 'PREFLIGHT' in name or 'POSTDEPLOY' in name for name in mine)


# ---------------------------------------------------------------- the shipped unbound payload
@pytest.mark.parametrize('op',OPS)
def test_shipped_unbound_documents_refuse_before_anything_is_touched(op):
    k=f.load(op);directory=ROOT/op
    raws=[(directory/(name+'.UNBOUND.json')).read_bytes() for name in ('REQUEST','AUTHORITY','GO')]
    pins=k.m.Pins(payload=f.sha(k.source),request=f.sha(raws[0]),authority=f.sha(raws[1]),go=f.sha(raws[2]))
    for uid in (0,501):
        result=k.m.run(*raws,pins=pins,payload_bytes=k.source,executor_uid=lambda:uid,host=Untouchable())
        assert (result['status'],result['code'],result['outcome'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND',k.m.REFUSED_OUTCOME)
        assert result['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0} and result['ready'] is False
        assert result['request_sha256']==pins.request and result['go_sha256']==pins.go and f.sealed(result)

@pytest.mark.parametrize('op',OPS)
def test_final_unbound_stdin_payload_refuses_under_isolated_python_and_through_the_reviewed_transport(op):
    k=f.load(op);payload=(ROOT/op/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()
    done=subprocess.run(ISOLATED,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    result=json.loads(done.stdout)
    assert done.returncode==1 and done.stderr==b'' and (result['status'],result['code'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND')
    assert result['schema']==k.m.RECEIPT_SCHEMA and result['mutating_calls']['issued']==0
    outcome,out,err=k.t.once(payload,payload_sha256=f.sha(payload),command=ISOLATED,command_sha256=k.t.command_pin(ISOLATED),
                             authorize=lambda a,b:True,seconds=60)
    assert outcome['status']=='KNOWN_REFUSAL' and err==b'' and json.loads(out)==result


# ---------------------------------------------------------------- the bound fixture and the envelope
def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(case):
    k,docs,host=case;m=k.m;receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.COMPLETE_OUTCOME and receipt['code'] is None and f.sealed(receipt)
    assert receipt['schema']==m.RECEIPT_SCHEMA and receipt['operation']==m.OPERATION and receipt['scope_sha256']==m.SCOPE_SHA256
    assert (receipt['request_sha256'],receipt['authority_sha256'],receipt['go_sha256'],receipt['payload_sha256'])==(
        docs.pins().request,docs.pins().authority,docs.pins().go,f.sha(k.source)) and receipt['host_binding_sha256']==f.HOST
    assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False and receipt['ready'] is False
    assert receipt['size_reductions']==[] and len(f.line(receipt))<20000
    assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects'])
    if not m.WRITES_ALLOWED:assert host.mutating()==[] and receipt['writes']==0

STUB='''
from dataclasses import dataclass
import hashlib,json
@dataclass(frozen=True)
class Pins:
    payload:str
    request:str
    authority:str
    go:str
def run(request,authority,go,*,pins,payload_bytes):
    MODE=%r
    if MODE=='raise_value':raise ValueError('CODE_LOOKING_REFUSAL')
    if MODE=='raise_key':return {}['missing']
    if MODE=='not_a_dict':return ['REFUSED']
    if MODE=='exit':raise SystemExit(1)
    result={'status':{'refused':'REFUSED','partial':'PARTIAL_METADATA_REQUIRES_REVIEW','complete':'METADATA_ONLY_REQUIRES_REVIEW'}[MODE],'table':[1,2]}
    if MODE!='refused':result['metadata_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return result
'''
@pytest.mark.parametrize('mode,status,returncode',[('refused','KNOWN_REFUSAL',1),('partial','KNOWN_PARTIAL',2),('complete','KNOWN_COMPLETE',0),
                                                   ('raise_value','UNCERTAIN',3),('raise_key','UNCERTAIN',3),('not_a_dict','UNCERTAIN',3),
                                                   ('exit','UNCERTAIN',1)])
def test_launcher_files_an_exception_that_escapes_run_as_uncertain_never_as_a_refusal(mode,status,returncode):
    """The payload is entered with exit code 3. Only a returned object can become exit 0, 1 or 2."""
    k=f.load('provision');source=(STUB%mode).encode();blobs=[b'{"a":1}',b'{"b":2}',b'{"c":3}']
    payload=k.l.build(source,*blobs,expected_payload_sha256=f.sha(source),expected_request_sha256=f.sha(blobs[0]),
                      expected_authority_sha256=f.sha(blobs[1]),expected_go_sha256=f.sha(blobs[2]))
    outcome,out,err=k.t.once(payload,payload_sha256=f.sha(payload),command=ISOLATED,command_sha256=k.t.command_pin(ISOLATED),
                             authorize=lambda a,b:True,seconds=60)
    assert (outcome['status'],outcome['returncode'])==(status,returncode)
    if status=='UNCERTAIN' and mode!='exit':assert json.loads(out)['status']=='RUN_RAISED_STATE_UNKNOWN' and err==b''

def test_launcher_refuses_wrong_pins_at_build_and_on_stdin():
    k=f.load('precheck');docs,_=f.default_docs('precheck');raws=docs.raw()
    with pytest.raises(ValueError,match='BUILD_PIN'):
        k.l.build(k.source,*raws,expected_payload_sha256='0'*64,expected_request_sha256=f.sha(raws[0]),
                  expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))
    payload=k.l.build(k.source,*raws,expected_payload_sha256=f.sha(k.source),expected_request_sha256=f.sha(raws[0]),
                      expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))
    tampered=payload.replace(f.sha(raws[2]).encode(),b'f'*64)
    done=subprocess.run(ISOLATED,input=tampered,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==1 and json.loads(done.stdout)=={'schema':'HOSTOPS_STDIN_RESULT_V1','status':'REFUSED','code':'STDIN_DOCUMENT_PIN'}


# ---------------------------------------------------------------- documents: bytes, keys, names
def test_pins_must_match_the_bytes(case):
    k,docs,_=case;raws=docs.raw()
    for name in ('payload','request','authority','go'):
        for bad in ('0'*64,'f'*64,None,'F'*64):
            values={field:getattr(docs.pins(),field) for field in ('payload','request','authority','go')};values[name]=bad
            assert refusal(lambda:k.m.authenticate(*raws,pins=k.m.Pins(**values),payload_bytes=k.source,clock=lambda:f.NOW,
                                                   monotonic=lambda:0,executor_uid=lambda:0))=='PIN_MISMATCH'

@pytest.mark.parametrize('index,code',[(0,'REQUEST_KEYS'),(1,'AUTHORITY_KEYS'),(2,'GO_KEYS')])
def test_each_document_has_exactly_its_keys(case,index,code):
    k,docs,_=case;document=(docs.request,docs.authority,docs.go)[index]
    for key in sorted(document):
        saved=document.pop(key);assert refusal(lambda:auth_raw(k,docs.raw()))==code;document[key]=saved
    document['extra']=1;assert refusal(lambda:auth_raw(k,docs.raw()))==code;del document['extra']
    docs.plan['extra']=1;docs.chain();assert refusal(docs.authenticate)=='PLAN_KEYS';del docs.plan['extra']
    for key in sorted(k.m.PLAN_KEYS|k.m.PLAN_COMMON_KEYS):
        if key=='host_binding_sha256':continue
        saved=docs.plan.pop(key);docs.chain();assert refusal(docs.authenticate)=='PLAN_KEYS';docs.plan[key]=saved
    docs.chain();docs.authenticate()

def test_documents_are_decoded_from_bytes_and_must_be_canonical(case):
    k,docs,_=case;raws=docs.raw()
    spaced=json.dumps(docs.request,sort_keys=True).encode();assert refusal(lambda:auth_raw(k,[spaced,raws[1],raws[2]]))=='DOCUMENT_NOT_CANONICAL'
    reordered=json.dumps(dict(reversed(list(docs.go.items()))),separators=(',',':')).encode()
    assert json.loads(reordered)==docs.go and refusal(lambda:auth_raw(k,[raws[0],raws[1],reordered]))=='DOCUMENT_NOT_CANONICAL'
    duplicate=raws[1][:-1]+b',"status":"SIGNED"}';assert refusal(lambda:auth_raw(k,[raws[0],duplicate,raws[2]]))=='DUPLICATE_KEY'
    assert refusal(lambda:auth_raw(k,[raws[0],raws[1],raws[2][:-1]+b',"x":NaN}']))=='NONFINITE_JSON'
    assert refusal(lambda:auth_raw(k,[raws[0],raws[1],b'{not json']))=='JSON_INVALID'
    assert refusal(lambda:auth_raw(k,[raws[0],b'[]',raws[2]]))=='DOCUMENT_TYPE'
    assert refusal(lambda:auth_raw(k,[b'{"a":"'+b'x'*65536+b'"}',raws[1],raws[2]]))=='DOCUMENT_SIZE'

@pytest.mark.parametrize('document,field,value,code',[
    ('request','status','UNBOUND','REQUEST_OR_EXECUTOR_UNBOUND'),('request','executor_uid',1000,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','executor_uid',False,'REQUEST_OR_EXECUTOR_UNBOUND'),('request','executor_uid',0.0,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','scope_sha256','3'*64,'REQUEST_OR_EXECUTOR_UNBOUND'),('request','payload_sha256','3'*64,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','max_seconds',61,'REQUEST_SCOPE'),('request','max_seconds',True,'REQUEST_SCOPE'),('request','max_seconds',60.0,'REQUEST_SCOPE'),
    ('request','activation_allowed',True,'REQUEST_SCOPE'),
    ('request','writes_allowed',None,'REQUEST_SCOPE'),('request','date',None,'DATE_NOT_IN_SCOPE'),
    ('authority','status','UNBOUND','AUTHORITY_UNBOUND'),('authority','decision','REJECTED','AUTHORITY_UNBOUND'),
    ('authority','decision',None,'AUTHORITY_UNBOUND'),('authority','execution_authorized',1,'AUTHORITY_UNBOUND'),
    ('authority','payload_sha256','3'*64,'AUTHORITY_UNBOUND'),('authority','activation_allowed',True,'AUTHORITY_UNBOUND'),
    ('authority','owner_evidence',None,'AUTHORITY_UNBOUND'),('authority','owner_evidence','','AUTHORITY_UNBOUND'),
    ('authority','owner_evidence','UNBOUND','AUTHORITY_UNBOUND'),('authority','owner_evidence','x'*513,'AUTHORITY_UNBOUND'),
    ('authority','owner','OTHER','OWNER_UNBOUND'),('authority','owner',None,'OWNER_UNBOUND'),
    ('go','status','UNBOUND','GO_UNBOUND'),('go','action','NO_GO','GO_UNBOUND'),('go','action',None,'GO_UNBOUND'),
    ('go','execution_authorized',False,'GO_UNBOUND'),('go','activation_allowed',True,'GO_UNBOUND'),('go','payload_sha256','3'*64,'GO_UNBOUND'),
    ('go','owner','UNBOUND','OWNER_UNBOUND'),('go','owner','','OWNER_UNBOUND'),('go','owner',None,'OWNER_UNBOUND'),
    ('go','scope_statement','anything else','GO_CRITERION'),('go','scope_statement',None,'GO_CRITERION'),
    ('go','success_criterion','PARTIAL_REQUIRES_RECONCILIATION','GO_CRITERION'),('go','success_criterion',None,'GO_CRITERION'),
    ('go','claim_root_identity',None,'GO_CLAIM_ROOT_UNBOUND'),('go','claim_root_identity',{'path':None,'device':None,'inode':None},'GO_CLAIM_ROOT_UNBOUND'),
    ('go','transport_binding',None,'GO_TRANSPORT_UNBOUND'),
    ('plan','status','UNBOUND','PLAN_UNBOUND'),('plan','schema','OTHER_PLAN_V1','PLAN_UNBOUND'),('plan','phase','READONLY_HOSTFACTS','PHASE_INVALID'),
    ('plan','max_seconds',61,'LIMITS_INVALID'),('plan','host_binding_sha256','2'*64,'PLAN_BINDING'),('plan','host_binding_sha256',None,'PLAN_BINDING'),
    ('plan','window',{'not_before':None},'PLAN_WINDOW'),('plan','window',None,'PLAN_WINDOW'),('plan','window',{'not_before':None,'expires_at':None},'WINDOW_UNBOUND'),
    ('plan','scope',None,'SCOPE_MISMATCH'),('request','evidence',None,'EVIDENCE_UNBOUND'),('authority','effects',None,'EFFECTS_BINDING'),('go','effects',None,'EFFECTS_BINDING'),
    ('request','not_before',None,'WINDOW_UNBOUND'),('authority','not_after',None,'WINDOW_UNBOUND'),('go','not_before',None,'WINDOW_UNBOUND'),
    ('request','host_binding_sha256',None,'HOST_BINDING'),
])
def test_every_unbound_or_foreign_member_has_its_constant_refusal(case,document,field,value,code):
    k,docs,_=case
    target={'request':docs.request,'authority':docs.authority,'go':docs.go,'plan':docs.plan}[document]
    if field=='writes_allowed':value=not k.m.WRITES_ALLOWED
    target[field]=value;docs.chain(effects=False,criterion=False)
    assert refusal(docs.authenticate)==code
    result=docs.run(Untouchable());assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'AUTHENTICATION')

def test_owner_is_bound_and_equal_in_authority_and_go(case):
    k,docs,_=case
    for value in ('UNBOUND','',None,7,'x'*129):
        docs.go['owner']=value;docs.authority['owner']=value;docs.chain();assert refusal(docs.authenticate)=='OWNER_UNBOUND'

def test_transport_binding_and_writes_flag_in_every_document(case):
    k,docs,_=case
    for field,value in (('target',None),('target',''),('command_sha256',None),('command_sha256','0'*64),('remote_command','sudo -n /bin/sh'),
                        ('runtime_sha256',None),('runtime_sha256',{k.name:'3'*64}),('runtime_sha256',{})):
        saved=docs.go['transport_binding'][field];docs.go['transport_binding'][field]=value;docs.chain()
        assert refusal(docs.authenticate)=='GO_TRANSPORT_UNBOUND';docs.go['transport_binding'][field]=saved
    for document,code in ((docs.authority,'AUTHORITY_UNBOUND'),(docs.go,'GO_UNBOUND')):
        document['writes_allowed']=not k.m.WRITES_ALLOWED;docs.chain();assert refusal(docs.authenticate)==code
        document['writes_allowed']=k.m.WRITES_ALLOWED
    docs.chain();docs.authenticate()

def test_hash_chain_between_the_three_documents(case):
    k,docs,_=case
    docs.authority['request_sha256']='3'*64;docs.go['authority_sha256']=f.sha(f.canonical(docs.authority))
    assert refusal(docs.authenticate)=='AUTHORITY_UNBOUND';docs.chain()
    docs.go['request_sha256']='3'*64;assert refusal(docs.authenticate)=='GO_UNBOUND';docs.chain()
    docs.go['authority_sha256']='3'*64;assert refusal(docs.authenticate)=='GO_UNBOUND';docs.chain();docs.authenticate()

def test_host_binding_is_one_non_null_value_in_three_documents_and_the_plan(case):
    k,docs,_=case
    for target in (docs.authority,docs.go):
        target['host_binding_sha256']='2'*64;docs.chain();assert refusal(docs.authenticate)=='HOST_BINDING';target['host_binding_sha256']=f.HOST
    for value in (None,'0'*64,'A'*64,'1'*63):
        for target in (docs.request,docs.authority,docs.go,docs.plan):target['host_binding_sha256']=value
        docs.chain();assert refusal(docs.authenticate)=='HOST_BINDING'

def test_effects_are_literal_in_authority_and_go_and_recomputed_from_the_plan(case):
    k,docs,_=case;assert docs.authority['effects']==docs.go['effects'] and docs.go['effects']['operation']==k.m.OPERATION
    for target in (docs.authority,docs.go):
        for change in (None,{},dict(target['effects'],operation='OTHER'),dict(target['effects'],extra=1)):
            saved=target['effects'];target['effects']=change;docs.chain(effects=False)
            assert refusal(docs.authenticate)=='EFFECTS_BINDING';target['effects']=saved
    docs.chain();docs.authenticate()

def test_effects_equal_in_authority_and_go_but_not_those_of_the_plan_are_refused(case):
    """The comparison is with what the code recomputes from the plan, not between the two documents."""
    k,docs,_=case;good=json.loads(f.canonical(docs.go['effects']))
    for key in sorted(good):
        changed={name:value for name,value in good.items() if name!=key}
        docs.authority['effects']=changed;docs.go['effects']=json.loads(f.canonical(changed));docs.chain(effects=False)
        assert refusal(docs.authenticate)=='EFFECTS_BINDING',key
    for changed in (dict(good,extra=1),dict(good,activation=True),dict(good,operation='GO_OF_ANOTHER_OPERATION')):
        docs.authority['effects']=changed;docs.go['effects']=json.loads(f.canonical(changed));docs.chain(effects=False)
        assert refusal(docs.authenticate)=='EFFECTS_BINDING'
    docs.chain();docs.authenticate()

def test_claim_root_identity_transport_binding_and_plan_window_member_by_member(case):
    k,docs,_=case;good=dict(docs.go['claim_root_identity'])
    for change in ({'path':None},{'path':'relative/root'},{'path':7},{'path':''},{'device':None},{'device':-1},{'device':True},{'device':'1'},
                   {'inode':None},{'inode':0},{'inode':'2'},{'extra':1}):
        docs.go['claim_root_identity']=dict(good,**change);docs.chain();assert refusal(docs.authenticate)=='GO_CLAIM_ROOT_UNBOUND',change
    for key in good:
        docs.go['claim_root_identity']={name:value for name,value in good.items() if name!=key};docs.chain()
        assert refusal(docs.authenticate)=='GO_CLAIM_ROOT_UNBOUND'
    docs.go['claim_root_identity']=good;binding=dict(docs.go['transport_binding'])
    docs.go['transport_binding']=dict(binding,extra='x');docs.chain();assert refusal(docs.authenticate)=='GO_TRANSPORT_UNBOUND'
    for key in binding:
        docs.go['transport_binding']={name:value for name,value in binding.items() if name!=key};docs.chain()
        assert refusal(docs.authenticate)=='GO_TRANSPORT_UNBOUND'
    docs.go['transport_binding']=binding;docs.chain();docs.authenticate()
    for field,moment in (('not_before',f.NOW-timedelta(seconds=1)),('not_before',f.NOW+timedelta(seconds=1)),('expires_at',f.NOW+timedelta(minutes=4))):
        saved=docs.plan['window'][field];docs.plan['window'][field]=moment.isoformat();docs.chain()
        assert refusal(docs.authenticate)=='PLAN_WINDOW';docs.plan['window'][field]=saved
    docs.chain();docs.authenticate()

def test_write_requests_name_a_precheck_receipt_among_their_evidence(case):
    """The rows a write request signs come from an OP_PRECHECK receipt; a request that cites only other receipts is refused."""
    k,docs,_=case;other=[{'role':'HOSTFACTS','operation':'GO_READONLY_SUPERVISOR_HOSTFACTS_01','receipt_sha256':'a'*64}]
    assert k.m.EVIDENCE_OPERATIONS==(('GO_READONLY_HOSTOPS_PRECHECK_01',) if k.m.WRITES_ALLOWED else ())
    docs.request['evidence']=other;docs.chain()
    if not k.m.WRITES_ALLOWED:
        docs.authenticate();return
    assert refusal(docs.authenticate)=='EVIDENCE_PRECHECK_MISSING'
    result=docs.run(Untouchable());assert (result['status'],result['code'])==('REFUSED','EVIDENCE_PRECHECK_MISSING')
    docs.request['evidence']=[{'role':'PRECHECK','operation':'GO_READONLY_HOSTOPS_PRECHECK_0','receipt_sha256':'b'*64}];docs.chain()
    assert refusal(docs.authenticate)=='EVIDENCE_PRECHECK_MISSING'
    docs.request['evidence']=other+[{'role':'PRECHECK','operation':'GO_READONLY_HOSTOPS_PRECHECK_01','receipt_sha256':'b'*64}];docs.chain();docs.authenticate()

def test_scope_is_fixed_by_the_source_and_signed(case):
    k,docs,_=case
    docs.plan['scope']['limits']['max_seconds']=61;docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
    docs.plan['scope']=json.loads(k.m.canonical(k.m.SCOPE));docs.plan['scope']['never']=[];docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
    docs.plan['scope']=None;docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
    assert k.m.SCOPE['statement']==k.m.SCOPE_STATEMENT and k.m.SCOPE['dates']==list(k.m.DATES)
    if hasattr(k.m,'COMMANDS'):assert k.m.SCOPE['commands'] is k.m.COMMANDS and all(tool in k.m.BINARIES for tool,_,_ in k.m.COMMANDS.values())

def test_evidence_names_the_prior_receipts(case):
    k,docs,_=case
    for bad in (None,'x',[{'role':'PRECHECK','operation':'X','receipt_sha256':'0'*64}],[{'role':'PRECHECK','operation':'X'}],
                [{'role':'lower','operation':'X','receipt_sha256':'a'*64}],[{'role':'A','operation':'X','receipt_sha256':None}],
                [{'role':'A','operation':'X','receipt_sha256':'a'*64}]*17):
        docs.request['evidence']=bad;docs.chain();assert refusal(docs.authenticate)=='EVIDENCE_UNBOUND'
    docs.request['evidence']=[];docs.chain()
    if k.m.EVIDENCE_REQUIRED:assert refusal(docs.authenticate)=='EVIDENCE_UNBOUND'
    else:docs.authenticate()


# ---------------------------------------------------------------- one operation never accepts another's documents
@pytest.mark.parametrize('donor',OPS)
@pytest.mark.parametrize('taker',OPS)
def test_documents_of_one_operation_are_refused_by_every_other_source(donor,taker):
    if donor==taker:return
    theirs,_=f.default_docs(donor);mine,_=f.default_docs(taker);k=mine.k
    assert refusal(lambda:auth_raw(k,theirs.raw()))=='REQUEST_OR_EXECUTOR_UNBOUND'
    raws=mine.raw()
    assert refusal(lambda:auth_raw(k,[raws[0],theirs.raw()[1],raws[2]]))=='AUTHORITY_UNBOUND'
    assert refusal(lambda:auth_raw(k,[raws[0],raws[1],theirs.raw()[2]]))=='GO_UNBOUND'
    # their GO re-pointed at my request, authority and payload still carries their names
    go=dict(theirs.go,request_sha256=mine.go['request_sha256'],authority_sha256=mine.go['authority_sha256'],payload_sha256=mine.go['payload_sha256'],
            effects=mine.go['effects'],transport_binding=mine.go['transport_binding'])
    assert refusal(lambda:auth_raw(k,[raws[0],raws[1],f.canonical(go)]))=='GO_UNBOUND'
    for field in ('schema','operation','phase'):
        for target,code in ((mine.request,'REQUEST_OR_EXECUTOR_UNBOUND'),(mine.authority,'AUTHORITY_UNBOUND'),(mine.go,'GO_UNBOUND')):
            saved=target[field];target[field]={'request':theirs.request,'authority':theirs.authority,'go':theirs.go}[
                'request' if target is mine.request else 'authority' if target is mine.authority else 'go'][field]
            mine.chain();assert refusal(mine.authenticate)==code;target[field]=saved
    mine.chain();mine.authenticate()

OLD=[('READONLY_POSTDEPLOY01_GO_V1','GO_READONLY_POSTDEPLOY_01','READONLY_POSTDEPLOY'),
     ('READONLY_SUPERVISOR_PREFLIGHT_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_01','READONLY_PREFLIGHT'),
     ('READONLY_SUPERVISOR_PREFLIGHT_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','READONLY_PREFLIGHT'),
     ('READONLY_SUPERVISOR_HOSTFACTS_GO_V1','GO_READONLY_SUPERVISOR_HOSTFACTS_01','READONLY_HOSTFACTS'),
     ('SUPERVISOR_INSTALL_FABLE_GO_V2','OP3_INSTALL_UNITS_NO_ACTIVATION','OP3_INSTALL_UNITS_NO_ACTIVATION')]
@pytest.mark.parametrize('schema,operation,phase',OLD)
def test_names_of_every_earlier_operation_are_refused_at_both_layers(case,tmp_path,schema,operation,phase):
    k,docs,_=case
    for fields,code,local in ((dict(schema=schema),'GO_UNBOUND','INNER_AUTHORITY'),(dict(operation=operation),'GO_UNBOUND',None),
                              (dict(phase=phase),'GO_UNBOUND',None),(dict(schema=schema,operation=operation,phase=phase),'GO_UNBOUND','INNER_AUTHORITY')):
        saved=dict(docs.go);docs.go.update(fields);docs.chain()
        assert refusal(docs.authenticate)==code
        dispatch=f.Dispatch(docs,tmp_path)
        found=refusal(dispatch.prepare);assert found==(local or found) and found in ('INNER_AUTHORITY','GO_UNBOUND','READONLY_SCOPE','WRITE_SCOPE')
        assert not dispatch.claims();docs.go.clear();docs.go.update(saved)
    for target,code in ((docs.request,'REQUEST_OR_EXECUTOR_UNBOUND'),(docs.authority,'AUTHORITY_UNBOUND')):
        saved=dict(target);target.update(schema=schema.replace('_GO_','_REQUEST_' if target is docs.request else '_AUTHORITY_'),operation=operation)
        docs.chain();assert refusal(docs.authenticate)==code
        dispatch=f.Dispatch(docs,tmp_path);assert refusal(dispatch.prepare)=='INNER_AUTHORITY' and not dispatch.claims()
        target.clear();target.update(saved)

# Bytes of earlier operations that exist only on the build workstation: signed documents, installer drafts, reviewed
# sources. Where they are is given by the environment; no path of that machine is carried by this file. Where a variable
# is not set (a CI runner, a reviewer's copy) the test that needs it is skipped and says so.
def elsewhere(variable,default=None):
    value=os.environ.get(variable);return Path(value) if value else (default or Path('/nonexistent/hostops01-optional-input'))
REAL=elsewhere('HOSTOPS_TEST_SIGNED_2026_10_01_DIR')
DRAFTS=elsewhere('HOSTOPS_TEST_INSTALLER_DRAFTS_DIR')
@pytest.mark.skipif(not (REAL/'GO.SIGNED.json').is_file(),reason='the signed documents of 2026-10-01 are not on this machine')
def test_real_signed_documents_of_2026_10_01_are_refused(case):
    """Bytes are read only to be refused; nothing from the files is copied into the candidate."""
    k,docs,_=case;raws=docs.raw();real=[(REAL/name).read_bytes() for name in ('REQUEST.BOUND.json','AUTHORITY.SIGNED.json','GO.SIGNED.json')]
    assert refusal(lambda:auth_raw(k,[raws[0],raws[1],real[2]]))=='GO_KEYS'
    assert refusal(lambda:auth_raw(k,[raws[0],real[1],raws[2]]))=='AUTHORITY_KEYS'
    assert refusal(lambda:auth_raw(k,real))=='REQUEST_KEYS'
    for moment in (f.NOW,datetime(2026,10,1,17,tzinfo=timezone.utc)):
        assert refusal(lambda:auth_raw(k,real,clock=lambda:moment)) in ('REQUEST_KEYS','DOCUMENT_NOT_CANONICAL')

@pytest.mark.skipif(not (DRAFTS/'OP3.GO.DRAFT.json').is_file(),reason='the installer drafts are not on this machine')
def test_drafts_of_the_installer_candidate_are_refused(case):
    k,docs,_=case;raws=docs.raw()
    for name,index,codes in (('OP3.GO.DRAFT.json',2,('GO_KEYS','DOCUMENT_NOT_CANONICAL')),('OP4.GO.DRAFT.json',2,('GO_KEYS','DOCUMENT_NOT_CANONICAL')),
                             ('OP3.AUTHORITY.DRAFT.json',1,('AUTHORITY_KEYS','DOCUMENT_NOT_CANONICAL')),
                             ('OP4.AUTHORITY.DRAFT.json',1,('AUTHORITY_KEYS','DOCUMENT_NOT_CANONICAL')),
                             ('REQUEST.UNBOUND.json',0,('REQUEST_KEYS','DOCUMENT_NOT_CANONICAL'))):
        blobs=list(raws);blobs[index]=(DRAFTS/name).read_bytes()
        assert refusal(lambda:auth_raw(k,blobs)) in codes

HOSTFACTS=elsewhere('HOSTOPS_TEST_HOSTFACTS_SOURCE',ROOT.parent.parent/'hostfacts01'/'candidate'/'hostfacts_readonly.py')
PREFLIGHT=elsewhere('HOSTOPS_TEST_PREFLIGHT_SOURCE')
@pytest.mark.parametrize('path',[HOSTFACTS,PREFLIGHT])
def test_reviewed_earlier_sources_refuse_the_documents_of_this_family(case,path):
    """The reverse direction: bytes of the reviewed read-only sources, loaded read-only, offered a GO of this family."""
    if not path.is_file():pytest.skip('reviewed source not on this machine')
    k,docs,_=case;spec=importlib.util.spec_from_file_location('_reviewed_'+path.stem,path)
    old=importlib.util.module_from_spec(spec);sys.modules[spec.name]=old;spec.loader.exec_module(old)
    raws=docs.raw();source=path.read_bytes()
    for day in (f.NOW,datetime(2026,10,2,17,tzinfo=timezone.utc),datetime(2026,10,1,17,tzinfo=timezone.utc)):
        with pytest.raises(old.Refused):
            old.authenticate(*raws,pins=old.Pins(payload=f.sha(source),request=f.sha(raws[0]),authority=f.sha(raws[1]),go=f.sha(raws[2])),
                             payload_bytes=source,clock=lambda:day,monotonic=lambda:0,executor_uid=lambda:0)


# ---------------------------------------------------------------- executor, window, clocks
def test_effective_uid_and_gid_must_be_root(case):
    k,docs,host=case
    assert refusal(lambda:docs.authenticate(executor_uid=lambda:501))=='REQUEST_OR_EXECUTOR_UNBOUND'
    result=docs.run(Untouchable(),executor_uid=lambda:501);assert (result['status'],result['code'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND')
    for actor in ((0,1000),(1000,0)):
        host.actor=actor;result=docs.run(host)
        if k.m.WRITES_ALLOWED:
            assert (result['status'],result['code'],result['outcome'])==('REFUSED','EXECUTOR_IDENTITY','REFUSED_NOTHING_CREATED')
            assert host.mutating()==[] and not any(entry[0] in ('lstat','read','run') for entry in host.log)
        else:assert result['status']!=k.m.COMPLETE_STATUS or k.op=='precheck'

def utc(*parts):return datetime(*parts,tzinfo=timezone.utc)
def test_window_boundaries_span_and_strict_utc(case):
    k,docs,_=case;start,end=f.NOW,f.NOW+timedelta(minutes=5)
    for moment,code in ((start-timedelta(microseconds=1),'OUTSIDE_GO_WINDOW'),(end,'OUTSIDE_GO_WINDOW'),(end+timedelta(hours=1),'OUTSIDE_GO_WINDOW')):
        assert refusal(lambda:docs.authenticate(clock=lambda:moment))==code
    for moment in (start,end-timedelta(microseconds=1)):docs.authenticate(clock=lambda:moment)
    for target in (docs.request,docs.authority,docs.go):
        for field in ('not_before','not_after'):
            saved=target[field]
            for value,code in ((None,'WINDOW_UNBOUND'),('yesterday','WINDOW_UNBOUND'),(1759510800,'WINDOW_UNBOUND'),('2026-10-03T17:00:00','WINDOW_NOT_UTC'),
                               ('2026-10-03T14:00:00-03:00','WINDOW_NOT_UTC'),('2026-10-03T18:00:00+01:00','WINDOW_NOT_UTC')):
                target[field]=value;docs.chain();assert refusal(docs.authenticate)==code
            target[field]=saved
    docs.chain();docs.authenticate()
    # the gate is the latest start and the earliest end of the three documents
    docs.go['not_after']=(f.NOW+timedelta(minutes=1)).isoformat();docs.chain()
    assert refusal(lambda:docs.authenticate(clock=lambda:f.NOW+timedelta(minutes=2)))=='OUTSIDE_GO_WINDOW'
    docs.go['not_after']=docs.request['not_after'];docs.authority['not_before']=(f.NOW+timedelta(minutes=1)).isoformat();docs.chain()
    assert refusal(docs.authenticate)=='OUTSIDE_GO_WINDOW'
    # a window as long as the UTC day is not a short window
    cap=k.m.MAX_GATE_SPAN_SECONDS;assert cap==(900 if k.m.WRITES_ALLOWED else 3600)
    docs.shift(f.NOW,f.NOW+timedelta(seconds=cap));docs.authenticate()
    docs.shift(f.NOW,f.NOW+timedelta(seconds=cap+1));assert refusal(docs.authenticate)=='WINDOW_SPAN'
    docs.shift(f.NOW,f.NOW);assert refusal(docs.authenticate)=='WINDOW_SPAN'
    docs.shift(f.NOW,f.NOW+timedelta(minutes=5));docs.plan['window']['expires_at']=(f.NOW+timedelta(minutes=4)).isoformat();docs.chain()
    assert refusal(docs.authenticate)=='PLAN_WINDOW'

def test_gate_is_bounded_by_the_latest_start_and_the_earliest_end_whichever_document_holds_them(case):
    k,docs,_=case;early=(f.NOW+timedelta(minutes=1)).isoformat();late=early
    for holder in ('request','authority','go'):
        docs.shift(f.NOW,f.NOW+timedelta(minutes=5));getattr(docs,holder)['not_after']=early
        if holder=='request':docs.plan['window']['expires_at']=early
        docs.chain();docs.authenticate(clock=lambda:f.NOW+timedelta(seconds=59))
        for moment in (f.NOW+timedelta(minutes=1),f.NOW+timedelta(minutes=2)):
            assert refusal(lambda:docs.authenticate(clock=lambda:moment))=='OUTSIDE_GO_WINDOW',holder
        docs.shift(f.NOW,f.NOW+timedelta(minutes=5));getattr(docs,holder)['not_before']=late
        if holder=='request':docs.plan['window']['not_before']=late
        docs.chain();docs.authenticate(clock=lambda:f.NOW+timedelta(seconds=60))
        for moment in (f.NOW,f.NOW+timedelta(seconds=59)):
            assert refusal(lambda:docs.authenticate(clock=lambda:moment))=='OUTSIDE_GO_WINDOW',holder

def test_every_instant_of_the_three_windows_lies_on_the_signed_day(case):
    k,docs,_=case
    # a window that begins on the previous day, the signed date being the day it ends on: 2026-10-01 is in no date set
    for start,end in ((utc(2026,10,1,23,58),utc(2026,10,2,0,2)),(utc(2026,10,2,23,58),utc(2026,10,3,0,2))):
        docs.shift(start,end);docs.request['date']=end.date().isoformat();docs.chain()
        for moment in (start,end-timedelta(seconds=1)):
            assert refusal(lambda:docs.authenticate(clock=lambda:moment))=='DATE_WINDOW_MISMATCH'
    # one instant alone on another day, in each document
    for holder in ('request','authority','go'):
        for field,value in (('not_before',utc(2026,10,2,23,59,59)),('not_after',utc(2026,10,4,0,0))):
            docs.shift(f.NOW,f.NOW+timedelta(minutes=5));getattr(docs,holder)[field]=value.isoformat()
            if holder=='request':docs.plan['window']['not_before' if field=='not_before' else 'expires_at']=value.isoformat()
            docs.chain();assert refusal(docs.authenticate)=='DATE_WINDOW_MISMATCH',(holder,field)

def test_write_operations_stop_before_the_first_session_day_at_both_layers(case,tmp_path):
    """Literal sets, not the module's own: 2026-10-05 UTC (Sunday 21:00 BRT onward) is a day for reading only."""
    k,docs,_=case;expected=WRITE_DAYS if k.m.WRITES_ALLOWED else READ_DAYS;assert k.m.DATES==expected and k.m.SCOPE['dates']==list(expected)
    for day in READ_DAYS:
        moment=datetime.fromisoformat(day+'T12:00:00+00:00');docs.shift(moment,moment+timedelta(minutes=5))
        directory=tmp_path/day;directory.mkdir();fresh,_=f.default_docs(k.op,now=moment);dispatch=f.Dispatch(fresh,directory)
        if day in expected:
            docs.authenticate(clock=lambda:moment);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
        else:
            assert refusal(lambda:docs.authenticate(clock=lambda:moment))=='DATE_NOT_IN_SCOPE'
            result=docs.run(Untouchable(),clock=lambda:moment);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
            assert refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()

def test_date_scope_is_a_signed_day_of_the_code_set(case):
    k,docs,_=case
    for day in k.m.DATES:
        moment=datetime.fromisoformat(day+'T12:00:00+00:00');docs.shift(moment,moment+timedelta(minutes=5));docs.authenticate(clock=lambda:moment)
    for day in ('2026-10-01','2026-10-06','2027-10-03'):
        moment=datetime.fromisoformat(day+'T12:00:00+00:00');docs.shift(moment,moment+timedelta(minutes=5))
        assert refusal(lambda:docs.authenticate(clock=lambda:moment))=='DATE_NOT_IN_SCOPE'
    late=utc(2026,10,3,23,58);docs.shift(late,utc(2026,10,4,0,2));assert refusal(lambda:docs.authenticate(clock=lambda:late))=='DATE_WINDOW_MISMATCH'
    docs.shift(f.NOW,f.NOW+timedelta(minutes=5));docs.request['date']='2026-10-04';docs.chain()
    assert refusal(docs.authenticate)=='DATE_WINDOW_MISMATCH'
    for value in (None,20261003,['2026-10-03']):
        docs.request['date']=value;docs.chain();assert refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'

def test_gate_monotonic_deadline_and_clock_reversal():
    for op in OPS:
        m=f.load(op).m;wall=[f.NOW];mono=[100.0]
        gate=m.Gate(f.NOW,f.NOW+timedelta(minutes=5),lambda:wall[0],lambda:mono[0])
        assert gate()==60.0
        mono[0]=159.0;assert gate()==1.0
        mono[0]=160.0;assert refusal(gate)=='GO_EXPIRED'
        mono[0]=120.0;assert refusal(gate)=='CLOCK_REVERSED'
        gate=m.Gate(f.NOW,f.NOW+timedelta(minutes=5),lambda:wall[0],lambda:mono[0])
        wall[0]=f.NOW+timedelta(seconds=10);assert gate()==60.0
        wall[0]=f.NOW+timedelta(seconds=9);assert refusal(gate)=='CLOCK_REVERSED'
        wall[0]=f.NOW+timedelta(minutes=5);assert refusal(gate)=='GO_EXPIRED'
        wall[0]=f.NOW+timedelta(minutes=4,seconds=30);gate=m.Gate(f.NOW,f.NOW+timedelta(minutes=5),lambda:wall[0],lambda:mono[0]);assert gate()==30.0
        assert refusal(lambda:m.Gate(f.NOW,f.NOW+timedelta(minutes=5),lambda:f.NOW-timedelta(seconds=1),lambda:0))=='OUTSIDE_GO_WINDOW'

def test_dry_gate_stops_before_anything_is_observed(case):
    """The binding step validates with a gate that raises: nothing may be touched and the exception must surface."""
    k,docs,_=case
    class Dry(Exception):pass
    def gate():raise Dry()
    with pytest.raises(Dry):docs.perform(Untouchable(),gate=gate)
    state=k.m.Effects()
    with pytest.raises(Dry):docs.perform(Untouchable(),gate=gate,state=state)
    assert state.started is False and state.issued==0

def test_expiry_before_the_first_observation_is_a_refusal_with_nothing_touched(case):
    k,docs,host=case;wall=[f.NOW]
    def clock():
        value=wall[0];wall[0]=f.NOW+timedelta(minutes=6);return value          # in the window for authentication only
    result=docs.run(host,clock=clock)
    assert (result['status'],result['code'],result['outcome'])==('REFUSED','GO_EXPIRED',k.m.REFUSED_OUTCOME)
    assert host.log==[] and result['mutating_calls']['issued']==0


# ---------------------------------------------------------------- run() never raises, and never calls a changed host untouched
def test_any_failure_inside_the_run_is_a_returned_object_never_an_exception_and_never_a_false_refusal(case):
    k,docs,host=case;m=k.m
    baseline=docs.run(host);total=host.calls;assert baseline['status']==m.COMPLETE_STATUS
    step=1 if total<=200 else max(1,total//200)
    for kind in (RuntimeError,OSError,hostemu.Death,KeyboardInterrupt):
        for index in list(range(1,total+1,step)):
            docs,host=f.default_docs(k.op)
            def hook(host,name,detail,calls,index=index,kind=kind):
                if calls==index:raise kind(5,'injected') if kind is OSError else kind('injected')
            host.hook=hook;before=host.tree.snapshot();tags=json.dumps(host.docker.images)
            result=docs.run(host)
            assert type(result) is dict and result['status'] in ('REFUSED',m.PARTIAL_STATUS,m.COMPLETE_STATUS) and f.sealed(result)
            assert 'injected' not in json.dumps(result)
            changed=host.tree.snapshot()!=before or json.dumps(host.docker.images)!=tags
            if result['status']=='REFUSED':assert not changed,(kind,index)
            if changed:assert m.WRITES_ALLOWED and result['status'] in (m.PARTIAL_STATUS,m.COMPLETE_STATUS)
            if not m.WRITES_ALLOWED:assert not changed and host.mutating()==[]
            if result['status']==m.COMPLETE_STATUS:assert kind is OSError or kind is RuntimeError   # a tolerated read (for example a retried probe) only


# ---------------------------------------------------------------- dispatcher: once, local claim, bindings
def test_prepare_does_not_spawn_then_resume_once_and_the_go_is_single_use(case,tmp_path):
    k,docs,_=case;dispatch=f.Dispatch(docs,tmp_path)
    prepared=dispatch.prepare();assert prepared['status']=='AWAITING_PUBLICATION_NO_SPAWN' and prepared['retry'] is False
    claim=dispatch.claims();assert len(claim)==1 and claim[0].name=='.go-'+dispatch.config['go']['sha256']+'.claim'
    published=dispatch.proof(prepared)
    assert dispatch.resume(published,dispatch.fake())['status']=='KNOWN_PARTIAL'
    with pytest.raises(FileExistsError):dispatch.resume(published,f.never)
    with pytest.raises(FileExistsError):dispatch.prepare()
    # a new attempt directory under the same GO is still refused: the claim is keyed by the GO hash
    dispatch.config['attempt_directory']=str(dispatch.root/'second');dispatch.save(rebind=False)
    with pytest.raises(FileExistsError):dispatch.prepare()
    assert not (dispatch.root/'second').exists()

def test_dispatcher_refuses_unsigned_foreign_or_transplanted_documents_before_any_claim(case,tmp_path):
    k,docs,_=case;m=k.m
    for index,(document,local) in enumerate(((docs.authority,'AUTHORITY_UNSIGNED'),(docs.go,'GO_UNSIGNED'))):
        document['status']='UNBOUND';directory=tmp_path/('unsigned%d'%index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
        assert refusal(dispatch.prepare)==local and not dispatch.claims();document['status']='SIGNED'
    directory=tmp_path/'config';directory.mkdir();dispatch=f.Dispatch(docs,directory)
    for field,value,code in (('schema','SUPERVISOR_HOSTFACTS_DISPATCH_AUTHORIZATION_V1','DISPATCH_UNBOUND'),('operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','DISPATCH_UNBOUND'),
                             ('status','UNBOUND','DISPATCH_UNBOUND'),('decision','UNBOUND','DISPATCH_UNBOUND'),('single_use',False,'DISPATCH_UNBOUND'),
                             ('retry',True,'DISPATCH_UNBOUND'),('owner','UNBOUND','DISPATCH_AUTHORITY'),('authorization_ref',None,'DISPATCH_AUTHORITY'),
                             ('executor_uid',1000,'REMOTE_UID'),('executor_uid',True,'REMOTE_UID'),('watchdog_seconds',79,'LATEST_START_BINDING'),
                             ('finalize_local_receipts_after_window',False,'LOCAL_FINALIZATION_AUTHORITY'),('host_binding_sha256','2'*64,'HOST_BINDING'),
                             ('remote_command','sudo -n /usr/bin/python3 -','GO_TRANSPORT_BINDING')):
        saved=dispatch.config[field];dispatch.config[field]=value;dispatch.save(rebind=False)
        assert refusal(dispatch.prepare)==code and not dispatch.claims();dispatch.config[field]=saved
    for other in OPS:
        if other==k.op:continue
        o=f.load(other).m;saved=(dispatch.config['schema'],dispatch.config['operation'])
        dispatch.config['schema']=json.loads((ROOT/other/'DISPATCH.UNBOUND.json').read_bytes())['schema'];dispatch.config['operation']=o.OPERATION
        dispatch.save(rebind=False);assert refusal(dispatch.prepare)=='DISPATCH_UNBOUND';dispatch.config['schema'],dispatch.config['operation']=saved
    # target transplant and claim root relocation after the GO was signed
    dispatch.config['target']='changed@unused.invalid';dispatch.config['command_sha256']=k.t.command_pin(k.d.command(dispatch.config))
    dispatch.save(rebind=False);assert refusal(dispatch.prepare)=='GO_TRANSPORT_BINDING'
    dispatch.config['target']='fixture@unused.invalid';dispatch.config['command_sha256']=k.t.command_pin(k.d.command(dispatch.config))
    other=directory/'other';other.mkdir(mode=0o700)
    dispatch.config['local_root_identity']={'path':str(other),'device':other.stat().st_dev,'inode':other.stat().st_ino}
    dispatch.config['attempt_directory']=str(other/'attempt');dispatch.save(rebind=False)
    assert refusal(dispatch.prepare)=='GO_CLAIM_ROOT_BINDING' and list(other.iterdir())==[] and not dispatch.claims()

def test_dispatcher_write_scope_date_scope_and_late_start(case,tmp_path):
    k,docs,_=case;m=k.m;label='WRITE_SCOPE' if m.WRITES_ALLOWED else 'READONLY_SCOPE'
    for index,document in enumerate((docs.request,docs.authority,docs.go)):
        directory=tmp_path/('scope%d'%index);directory.mkdir()
        document['writes_allowed']=not m.WRITES_ALLOWED;dispatch=f.Dispatch(docs,directory)
        assert refusal(dispatch.prepare)==label and not dispatch.claims();document['writes_allowed']=m.WRITES_ALLOWED
    docs.chain();directory=tmp_path/'dates';directory.mkdir();dispatch=f.Dispatch(docs,directory)
    def window(start,end,date=None):
        docs.shift(start,end)
        if date is not None:docs.request['date']=date
        dispatch.config.update(not_before=start.isoformat(),not_after=end.isoformat(),latest_start=(end-timedelta(seconds=80)).isoformat())
        dispatch.docs.now=start;dispatch.save();return dispatch
    for day in ('2026-10-01','2026-10-06'):
        moment=datetime.fromisoformat(day+'T12:00:00+00:00')
        assert refusal(window(moment,moment+timedelta(minutes=5)).prepare)=='DISPATCH_DATE'
    assert refusal(window(utc(2026,10,3,23,58),utc(2026,10,4,0,2)).prepare)=='DISPATCH_DATE'
    assert refusal(window(f.NOW,f.NOW+timedelta(minutes=5),date='2026-10-04').prepare)=='INNER_AUTHORITY'
    window(f.NOW,f.NOW+timedelta(minutes=5));assert not dispatch.claims()
    assert refusal(lambda:dispatch.prepare(clock=lambda:f.NOW+timedelta(seconds=221)))=='WINDOW_WITH_WATCHDOG' and not dispatch.claims()
    dispatch.config['latest_start']=(f.NOW+timedelta(seconds=219)).isoformat();dispatch.save(rebind=False)
    assert refusal(dispatch.prepare)=='LATEST_START_BINDING' and not dispatch.claims()
    for day in m.DATES:
        directory=tmp_path/day;directory.mkdir();moment=datetime.fromisoformat(day+'T12:00:00+00:00')
        fresh,_=f.default_docs(k.op,now=moment);assert f.Dispatch(fresh,directory).prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'

def test_dispatcher_validates_the_whole_inner_authority_locally_before_the_claim(case,tmp_path):
    """A malformed plan cannot spend the single-use GO: the source's own authenticate runs before any claim."""
    k,docs,_=case
    docs.plan['scope']['limits']['max_seconds']=61;dispatch=f.Dispatch(docs,tmp_path)
    assert refusal(dispatch.prepare)=='SCOPE_MISMATCH' and not dispatch.claims()
    docs.plan['scope']=json.loads(k.m.canonical(k.m.SCOPE));docs.authority['effects']={'operation':'x'};dispatch.save(rebind=False)
    docs.chain(effects=False);docs.go['claim_root_identity']=dispatch.config['local_root_identity']
    docs.go['transport_binding']={key:dispatch.config[key] for key in ('target','remote_command','command_sha256','runtime_sha256')}
    docs.chain(effects=False);dispatch.save(rebind=False)
    assert refusal(dispatch.prepare)=='EFFECTS_BINDING' and not dispatch.claims()

def test_publication_and_receipt_bindings(case,tmp_path):
    k,docs,_=case;m=k.m;dispatch=f.Dispatch(docs,tmp_path);prepared=dispatch.prepare();published=dispatch.proof(prepared)
    body=json.loads(Path(published['path']).read_bytes())
    for field,value in (('intent_sha256','0'*64),('schema','SUPERVISOR_HOSTFACTS_INTENT_PUBLICATION_V1'),('status','UNBOUND'),('owner','OTHER'),
                        ('go_sha256','3'*64),('config_sha256','3'*64),('publication_ref','UNBOUND')):
        changed=dispatch.put('bad-publication',f.canonical(dict(body,**{field:value})))
        with pytest.raises(ValueError):dispatch.resume(changed,f.never)
    assert not (Path(dispatch.config['attempt_directory'])/'spawn.claim').exists()
    big=f.canonical({'schema':m.RECEIPT_SCHEMA,'request_sha256':dispatch.config['request']['sha256'],'go_sha256':dispatch.config['go']['sha256'],
                     'payload_sha256':dispatch.config['source']['sha256'],'pad':'x'*65536})
    result=dispatch.resume(published,dispatch.fake(out=big,status='KNOWN_COMPLETE'))
    assert result['status']=='UNCERTAIN' and result['code']=='TRANSPORT_OR_RECEIPT_REFUSED' and result['retry_allowed'] is False
    stored=json.loads((Path(dispatch.config['attempt_directory'])/'exit.json').read_bytes());assert stored['status']=='UNCERTAIN'

@pytest.mark.parametrize('schema',['READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1','OTHER'])
def test_receipt_of_another_operation_is_filed_uncertain(case,tmp_path,schema):
    k,docs,_=case;dispatch=f.Dispatch(docs,tmp_path);published=dispatch.proof(dispatch.prepare())
    names=[f.load(other).m.RECEIPT_SCHEMA for other in OPS if other!=k.op]+[schema]
    foreign=f.canonical({'schema':names[0] if schema=='OTHER' else schema,'request_sha256':dispatch.config['request']['sha256'],
                         'go_sha256':dispatch.config['go']['sha256'],'payload_sha256':dispatch.config['source']['sha256']})
    assert dispatch.resume(published,dispatch.fake(out=foreign))['status']=='UNCERTAIN'

def test_cli_never_spawns_on_prepare_and_exits_zero_only_for_known_complete(case,tmp_path,monkeypatch,capsys):
    k,docs,_=case;dispatch=f.Dispatch(docs,tmp_path)
    done=subprocess.run([sys.executable,'-B',str(k.dir/'dispatch_once.py'),'--config',dispatch.pin['path'],'--config-sha256',dispatch.pin['sha256'],
                         '--phase','prepare'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    assert done.returncode==2 and done.stderr==b'' and json.loads(done.stdout)['status'] in ('REFUSED_OR_UNCERTAIN','AWAITING_PUBLICATION_NO_SPAWN')
    assert not (Path(dispatch.config['attempt_directory'])/'spawn.claim').exists()
    for status,code in (('KNOWN_COMPLETE',0),('KNOWN_PARTIAL',2),('AWAITING_PUBLICATION_NO_SPAWN',2),('UNCERTAIN',2),('KNOWN_REFUSAL',2)):
        monkeypatch.setattr(k.d,'execute',lambda *args,**kwargs:{'status':status});monkeypatch.setattr(sys,'argv',['dispatch_once.py','--config','/x','--config-sha256','0'*64])
        assert k.d.main()==code
    capsys.readouterr()

def test_end_to_end_through_the_reviewed_transport_with_the_bound_payload_as_non_root(case,tmp_path):
    """The whole local chain with real processes: the bound payload under isolated python refuses for the effective uid
    (the test user is not root), the reviewed transport files it KNOWN_REFUSAL and the dispatcher stores it."""
    if os.geteuid()==0:pytest.skip('as root the payload would act on this machine')
    k,docs,_=case;dispatch=f.Dispatch(docs,tmp_path)
    real=datetime.now(timezone.utc)
    if real.date().isoformat() not in k.m.DATES:pytest.skip('outside the code date set: the payload refuses for the date instead')
    done=subprocess.run(ISOLATED,input=dispatch.payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
    result=json.loads(done.stdout);assert done.returncode==1 and done.stderr==b'' and result['status']=='REFUSED'
    assert result['code'] in ('REQUEST_OR_EXECUTOR_UNBOUND',) and result['mutating_calls']['issued']==0
