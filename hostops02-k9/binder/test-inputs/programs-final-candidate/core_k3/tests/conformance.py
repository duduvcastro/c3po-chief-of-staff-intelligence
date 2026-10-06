"""The family's conformance suite: authority, envelope, once-dispatch, launcher and transport, for ANY operation
assembled from the HOSTOPS02 core. Synthetic local tests only. No SSH, host, real credential, docker binary or GO.

An operation's test file subclasses Conformance and gives two things:

    import conformance
    class TestConformance(conformance.Conformance):
        DIRECTORY=<the operation directory (holds spec.py, op.py, build/)>
        @staticmethod
        def case(now=None):
            # a bound fixture that COMPLETES on a fresh emulated host: (family.Docs, hostemu.FakeHost).
            # now=None means family.moment(k); the suite also asks for other instants of the operation's date set.
            ...
        OTHERS=(...)          # optional: more operation directories whose documents this one must refuse
                              # (the two demonstration operations of the core are always included)

Tests whose name contains "static" pin bytes and text; a mutation harness deselects them (-k "not static").
These are the tests of HOSTOPS01's tests/test_family.py, made independent of the operation."""
import ast
from datetime import datetime,timedelta,timezone
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

CORE=f.CORE
DEMOS=(CORE/'tests'/'demo_read',CORE/'tests'/'demo_write')
EXPECTED_LINES={True:[15,16,102,103,109,118,127,128,129,141,142,146,147,162,205,213,219,239],
                False:[15,16,102,103,109,118,127,128,129,141,146,147,162,205,213,219,239]}
ISOLATED=[sys.executable,'-I','-B','-']
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
EPOCH_DAYS=('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')
DATE_SETS={'READ':EPOCH_DAYS,'WRITE_WEEKEND':EPOCH_DAYS[:3],'WRITE_FIRST_SESSION':('2026-10-05',),'WRITE_SESSIONS':EPOCH_DAYS[3:],'WRITE_EPOCH':EPOCH_DAYS[1:]}
GENERATED=('dispatch_once.py','launcher_stdin.py','transport_once.py','DISPATCH_SCOPE_DELTA.diff','LAUNCHER_DELTA.diff','REQUEST.UNBOUND.json',
           'AUTHORITY.UNBOUND.json','GO.UNBOUND.json','DISPATCH.UNBOUND.json','PUBLICATION_PROOF.UNBOUND.json','FINAL_PAYLOAD.UNBOUND.py','ASSEMBLY.json')
# Names of every earlier operation of this host's once families: none may be accepted by a source of this one.
OLD=[('READONLY_POSTDEPLOY01_GO_V1','GO_READONLY_POSTDEPLOY_01','READONLY_POSTDEPLOY'),
     ('READONLY_SUPERVISOR_PREFLIGHT_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_01','READONLY_PREFLIGHT'),
     ('READONLY_SUPERVISOR_HOSTFACTS_GO_V1','GO_READONLY_SUPERVISOR_HOSTFACTS_01','READONLY_HOSTFACTS'),
     ('WRITE_HOSTOPS_PROVISION_GO_V1','GO_WRITE_SUPERVISOR_READER_PROVISION_01','WRITE_PROVISION_DIRECTORIES_AND_RETENTION_TAG'),
     ('WRITE_HOSTOPS_INSTALL_UNITS_GO_V1','GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01','WRITE_INSTALL_UNITS_NO_ACTIVATION'),
     ('READONLY_HOSTOPS_READBACK_GO_V1','GO_READONLY_SUPERVISOR_READBACK_01','READONLY_SUPERVISOR_READBACK'),
     ('READONLY_HOSTOPS_PRECHECK_GO_V1','GO_READONLY_HOSTOPS_PRECHECK_01','READONLY_HOSTOPS_PRECHECK')]
UNBOUND_MEMBERS=[
    ('request','status','UNBOUND','REQUEST_OR_EXECUTOR_UNBOUND'),('request','executor_uid',1000,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','executor_uid',False,'REQUEST_OR_EXECUTOR_UNBOUND'),('request','executor_uid',0.0,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','scope_sha256','3'*64,'REQUEST_OR_EXECUTOR_UNBOUND'),('request','payload_sha256','3'*64,'REQUEST_OR_EXECUTOR_UNBOUND'),
    ('request','max_seconds',61,'REQUEST_SCOPE'),('request','max_seconds',True,'REQUEST_SCOPE'),('request','max_seconds',60.0,'REQUEST_SCOPE'),
    ('request','activation_allowed','FLIP','REQUEST_SCOPE'),('request','activation_allowed',None,'REQUEST_SCOPE'),
    ('request','writes_allowed','FLIP','REQUEST_SCOPE'),('request','writes_allowed',None,'REQUEST_SCOPE'),('request','date',None,'DATE_NOT_IN_SCOPE'),
    ('authority','status','UNBOUND','AUTHORITY_UNBOUND'),('authority','decision','REJECTED','AUTHORITY_UNBOUND'),
    ('authority','decision',None,'AUTHORITY_UNBOUND'),('authority','execution_authorized',1,'AUTHORITY_UNBOUND'),
    ('authority','payload_sha256','3'*64,'AUTHORITY_UNBOUND'),('authority','activation_allowed','FLIP','AUTHORITY_UNBOUND'),
    ('authority','activation_allowed',None,'AUTHORITY_UNBOUND'),('authority','writes_allowed','FLIP','AUTHORITY_UNBOUND'),
    ('authority','owner_evidence',None,'AUTHORITY_UNBOUND'),('authority','owner_evidence','','AUTHORITY_UNBOUND'),
    ('authority','owner_evidence','UNBOUND','AUTHORITY_UNBOUND'),('authority','owner_evidence','x'*513,'AUTHORITY_UNBOUND'),
    ('authority','owner','OTHER','OWNER_UNBOUND'),('authority','owner',None,'OWNER_UNBOUND'),
    ('go','status','UNBOUND','GO_UNBOUND'),('go','action','NO_GO','GO_UNBOUND'),('go','action',None,'GO_UNBOUND'),
    ('go','execution_authorized',False,'GO_UNBOUND'),('go','activation_allowed','FLIP','GO_UNBOUND'),('go','activation_allowed',None,'GO_UNBOUND'),
    ('go','writes_allowed','FLIP','GO_UNBOUND'),('go','payload_sha256','3'*64,'GO_UNBOUND'),
    ('go','owner','UNBOUND','OWNER_UNBOUND'),('go','owner','','OWNER_UNBOUND'),('go','owner',None,'OWNER_UNBOUND'),
    ('go','scope_statement','anything else','GO_CRITERION'),('go','scope_statement',None,'GO_CRITERION'),
    ('go','success_criterion','SOME_OTHER_OUTCOME','GO_CRITERION'),('go','success_criterion',None,'GO_CRITERION'),
    ('go','claim_root_identity',None,'GO_CLAIM_ROOT_UNBOUND'),('go','claim_root_identity',{'path':None,'device':None,'inode':None},'GO_CLAIM_ROOT_UNBOUND'),
    ('go','transport_binding',None,'GO_TRANSPORT_UNBOUND'),
    ('plan','status','UNBOUND','PLAN_UNBOUND'),('plan','schema','OTHER_PLAN_V1','PLAN_UNBOUND'),('plan','phase','READONLY_HOSTFACTS','PHASE_INVALID'),
    ('plan','max_seconds',61,'LIMITS_INVALID'),('plan','host_binding_sha256','2'*64,'PLAN_BINDING'),('plan','host_binding_sha256',None,'PLAN_BINDING'),
    ('plan','window',{'not_before':None},'PLAN_WINDOW'),('plan','window',None,'PLAN_WINDOW'),('plan','window',{'not_before':None,'expires_at':None},'WINDOW_UNBOUND'),
    ('plan','scope',None,'SCOPE_MISMATCH'),('request','evidence',None,'EVIDENCE_UNBOUND'),('authority','effects',None,'EFFECTS_BINDING'),('go','effects',None,'EFFECTS_BINDING'),
    ('request','not_before',None,'WINDOW_UNBOUND'),('authority','not_after',None,'WINDOW_UNBOUND'),('go','not_before',None,'WINDOW_UNBOUND'),
    ('request','host_binding_sha256',None,'HOST_BINDING'),
]
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

refusal=f.refusal
Untouchable=f.Untouchable
def utc(*parts):return datetime(*parts,tzinfo=timezone.utc)
def noon(day):return datetime.fromisoformat(day+'T12:00:00+00:00')
def auth_raw(k,raws,now,**extra):
    pins=k.m.Pins(payload=f.sha(k.source),request=f.sha(raws[0]),authority=f.sha(raws[1]),go=f.sha(raws[2]))
    options=dict(clock=lambda:now,monotonic=lambda:0,executor_uid=lambda:0);options.update(extra)
    return k.m.authenticate(*raws,pins=pins,payload_bytes=k.source,**options)
def blocks(source):
    return {name:body for name,body in re.findall(r'# ==== BEGIN ([A-Z0-9_]+) \([^)]*\) ====\n(.*?)\n# ==== END \1 ====\n',source.decode(),re.S)}
def engine_state(host):
    """Everything a run could change on the emulated host: the tree, the image tags, the containers."""
    return host.tree.snapshot(),json.dumps(host.docker.images,sort_keys=True),json.dumps(host.docker.containers,sort_keys=True)


class Conformance:
    DIRECTORY=None
    OTHERS=()
    @staticmethod
    def case(now=None):raise NotImplementedError('give a bound fixture that completes: (family.Docs, hostemu.FakeHost)')

    # -- plumbing
    def one(self,now=None):
        docs,host=self.case(now) if now is not None else self.case();return docs.k,docs,host
    def others(self):
        mine=Path(self.DIRECTORY).resolve();return [Path(item).resolve() for item in DEMOS+tuple(self.OTHERS) if Path(item).resolve()!=mine]

    # ---------------------------------------------------------------- static pins (bytes and text)
    def test_static_build_is_exactly_the_assembly_of_the_frozen_core_and_the_operation_part(self):
        k=f.load(self.DIRECTORY);a=f.assembler();files=a.build(self.DIRECTORY)
        assert sorted(files)==sorted(path.name for path in k.dir.iterdir() if path.is_file()) and set(GENERATED)|{k.name}==set(files)
        for name,raw in files.items():assert (k.dir/name).read_bytes()==raw,name
        assert files[k.name]==k.source and f.sha(files['transport_once.py'])==f.TRANSPORT_PIN and f.sha(files['launcher_stdin.py'])==f.LAUNCHER_PIN
        base=a.reviewed('dispatch_once.py').decode().splitlines();new=files['dispatch_once.py'].decode().splitlines()
        assert len(base)==len(new) and [index+1 for index,(x,y) in enumerate(zip(base,new)) if x!=y]==EXPECTED_LINES[k.m.WRITES_ALLOWED]
        base=a.reviewed('launcher_stdin.py').decode().splitlines();new=files['launcher_stdin.py'].decode().splitlines()
        assert len(base)==len(new) and [index+1 for index,(x,y) in enumerate(zip(base,new)) if x!=y]==[30,32,33,35,38]
        report=json.loads(files['ASSEMBLY.json'])
        assert report['core_sha256']==a.core_sha256()==k.m.CORE_SHA256==f.sha((CORE/'assemble.py').read_bytes()) and report['source_sha256']==f.sha(k.source)

    def test_static_source_carries_the_sealed_parts_unchanged_and_meets_every_rule(self):
        k=f.load(self.DIRECTORY);a=f.assembler();found=blocks(k.source);spec=a.load_spec(self.DIRECTORY)
        assert list(found)==['SEAL']+[name.upper() for name in spec.PARTS]+['OP_'+spec.NAME.upper()]
        for name in spec.PARTS:
            assert found[name.upper()]==a.part(name).rstrip('\n') and k.m.CORE_PARTS[name]==f.sha((CORE/'parts'/(name+'.py')).read_bytes())
        assert found['OP_'+spec.NAME.upper()]==(Path(self.DIRECTORY)/'op.py').read_text(encoding='ascii').rstrip('\n')
        assert a.lint(spec,k.source,k.m)==[]
        tree=ast.parse(k.source.decode('ascii'));assert all(not isinstance(node,(ast.NamedExpr,ast.AsyncFunctionDef,ast.Await)) for node in ast.walk(tree))

    def test_static_assembly_yields_the_same_bytes_at_any_other_path_and_no_generated_file_names_a_path(self,tmp_path):
        """assemble.py, run from a copy of the core on a copy of the operation directory somewhere else, writes exactly
        the bytes of build/: nothing generated depends on where either lies, and nothing generated shows it."""
        k=f.load(self.DIRECTORY);copy=Path(str(tmp_path)).resolve()/'elsewhere'/'a copy';copy.mkdir(parents=True)
        for name in ('parts','reviewed_base'):shutil.copytree(str(CORE/name),str(copy/'core'/name))
        shutil.copy(str(CORE/'assemble.py'),str(copy/'core'/'assemble.py'));(copy/'op').mkdir()
        for name in ('spec.py','op.py'):shutil.copy(str(Path(self.DIRECTORY)/name),str(copy/'op'/name))
        done=subprocess.run([sys.executable,'-B','-W','error::SyntaxWarning',str(copy/'core'/'assemble.py'),str(copy/'op')],stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,env=ENV,cwd=str(copy),timeout=120)
        assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
        written=sorted(path.name for path in (copy/'op'/'build').iterdir());assert written==sorted(GENERATED+(k.name,))
        for name in written:
            raw=(k.dir/name).read_bytes();assert (copy/'op'/'build'/name).read_bytes()==raw,name
            for word in (str(CORE).encode(),str(Path(self.DIRECTORY).resolve()).encode(),str(copy).encode())+tuple(b'/'+top+b'/' for top in (b'Users',b'home',b'private')):
                assert word not in raw,(name,word)
        check=subprocess.run([sys.executable,'-B',str(copy/'core'/'assemble.py'),'--check',str(copy/'op')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
        assert check.returncode==0 and check.stdout.strip()==b'BUILD_EQUAL'

    def test_static_unbound_templates_hash_chain_and_null_bindings(self):
        k=f.load(self.DIRECTORY);directory=k.dir;m=k.m
        q,a,g,c,proof=[json.loads((directory/(name+'.UNBOUND.json')).read_bytes()) for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF')]
        digest=lambda name:f.sha((directory/name).read_bytes())
        assert a['request_sha256']==g['request_sha256']==c['request']['sha256']==digest('REQUEST.UNBOUND.json')
        assert g['authority_sha256']==c['authority']['sha256']==digest('AUTHORITY.UNBOUND.json')
        assert g['payload_sha256']==q['payload_sha256']==a['payload_sha256']==c['source']['sha256']==f.sha(k.source)
        assert c['go']['sha256']==proof['go_sha256']==digest('GO.UNBOUND.json') and proof['config_sha256']==digest('DISPATCH.UNBOUND.json')
        assert c['payload']['sha256']==digest('FINAL_PAYLOAD.UNBOUND.py')
        assert g['transport_binding']['runtime_sha256']==c['runtime_sha256']=={name:digest(name) for name in ('dispatch_once.py','transport_once.py','launcher_stdin.py',k.name)}
        assert c['runtime_sha256']['transport_once.py']==f.TRANSPORT_PIN and c['runtime_sha256']['launcher_stdin.py']==f.LAUNCHER_PIN
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
        assert g['success_criterion'] in (None,m.COMPLETE_OUTCOME)
        assert c['ssh_key']==c['known_hosts']=={'path':None,'sha256':None} and g['transport_binding']['target'] is None
        assert g['transport_binding']['command_sha256'] is None and a['execution_authorized'] is g['execution_authorized'] is False
        assert q['writes_allowed'] is a['writes_allowed'] is g['writes_allowed'] is m.WRITES_ALLOWED
        assert q['activation_allowed'] is a['activation_allowed'] is g['activation_allowed'] is m.ACTIVATION_ALLOWED
        for key in ('source','request','authority','go','payload'):
            assert set(c[key])=={'path','sha256'} and c[key]['path'] is None and re.fullmatch('[0-9a-f]{64}',c[key]['sha256'])
        for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF'):
            raw=(directory/(name+'.UNBOUND.json')).read_bytes();assert raw==m.canonical(json.loads(raw)) and b'SIGNED' not in raw and b'"BOUND"' not in raw
        raws=[(directory/(name+'.UNBOUND.json')).read_bytes() for name in ('REQUEST','AUTHORITY','GO')]
        assert k.l.build(k.source,*raws,expected_payload_sha256=f.sha(k.source),expected_request_sha256=f.sha(raws[0]),
                         expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))==(directory/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()

    def test_static_date_set_is_one_class_of_the_core_at_both_layers_and_names_are_disjoint(self):
        k=f.load(self.DIRECTORY);m=k.m;text=(k.dir/'dispatch_once.py').read_text()
        literal=re.search(r"start\.date\(\)\.isoformat\(\) in (\([^)]*\))",text).group(1)
        assert ast.literal_eval(literal)==m.DATES==DATE_SETS[m.DATE_CLASS] and m.DATE_SETS==DATE_SETS and m.SCOPE['dates']==list(m.DATES)
        assert (m.DATE_CLASS=='READ')==(not m.WRITES_ALLOWED) and (m.WRITES_ALLOWED or not m.ACTIVATION_ALLOWED)
        mine={m.OPERATION,m.PHASE,m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA}
        for other in self.others():
            o=f.load(other).m
            assert not mine&{o.OPERATION,o.PHASE,o.REQUEST_SCHEMA,o.AUTHORITY_SCHEMA,o.GO_SCHEMA,o.RECEIPT_SCHEMA,o.PLAN_SCHEMA}
        assert all('HOSTOPS02' in name for name in mine-{m.PHASE}) and not any(name in mine for row in OLD for name in row)

    # ---------------------------------------------------------------- the shipped unbound payload
    def test_shipped_unbound_dispatch_template_is_refused_by_its_dispatcher_and_a_null_path_is_no_path(self,tmp_path):
        """The template names no file. The dispatcher refuses it as it is, before any claim; and a config that is bound
        in every other respect but still carries a null blob path is refused too."""
        k,docs,_=self.one();root=Path(str(tmp_path)).resolve()/'template';root.mkdir(mode=0o700)
        raw=(k.dir/'DISPATCH.UNBOUND.json').read_bytes();path=root/'config';path.write_bytes(raw);path.chmod(0o600)
        for phase in ('prepare','resume'):
            assert refusal(lambda:k.d.execute(str(path),f.sha(raw),phase=phase,transport=f.never,clock=lambda:docs.now,monotonic=lambda:0))=='DISPATCH_UNBOUND'
        assert sorted(item.name for item in root.iterdir())==['config'],'no claim and no attempt directory'
        directory=Path(str(tmp_path))/'bound';directory.mkdir()
        for key in ('source','request','authority','go','payload'):
            dispatch=f.Dispatch(docs,directory);dispatch.config[key]={'path':None,'sha256':dispatch.config[key]['sha256']}
            dispatch.pin=dispatch.put('config',f.canonical(dispatch.config))
            assert refusal(dispatch.prepare)=='LOCAL_PATH' and not dispatch.claims(),key

    def test_shipped_unbound_documents_refuse_before_anything_is_touched(self):
        k=f.load(self.DIRECTORY)
        raws=[(k.dir/(name+'.UNBOUND.json')).read_bytes() for name in ('REQUEST','AUTHORITY','GO')]
        pins=k.m.Pins(payload=f.sha(k.source),request=f.sha(raws[0]),authority=f.sha(raws[1]),go=f.sha(raws[2]))
        for uid in (0,501):
            result=k.m.run(*raws,pins=pins,payload_bytes=k.source,executor_uid=lambda:uid,host=Untouchable())
            assert (result['status'],result['code'],result['outcome'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND',k.m.REFUSED_OUTCOME)
            assert result['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0} and result['ready'] is False
            assert result['request_sha256']==pins.request and result['go_sha256']==pins.go and f.sealed(result)

    def test_final_unbound_stdin_payload_refuses_under_isolated_python_and_through_the_reviewed_transport(self):
        k=f.load(self.DIRECTORY);payload=(k.dir/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()
        done=subprocess.run(ISOLATED,input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
        result=json.loads(done.stdout)
        assert done.returncode==1 and done.stderr==b'' and (result['status'],result['code'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND')
        assert result['schema']==k.m.RECEIPT_SCHEMA and result['mutating_calls']['issued']==0
        outcome,out,err=k.t.once(payload,payload_sha256=f.sha(payload),command=ISOLATED,command_sha256=k.t.command_pin(ISOLATED),
                                 authorize=lambda a,b:True,seconds=60)
        assert outcome['status']=='KNOWN_REFUSAL' and err==b'' and json.loads(out)==result

    # ---------------------------------------------------------------- the bound fixture and the envelope
    def test_bound_fixture_completes_and_the_reviewed_transport_accepts_the_sealed_receipt(self):
        k,docs,host=self.one();m=k.m;before=engine_state(host);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.COMPLETE_OUTCOME and receipt['code'] is None and f.sealed(receipt)
        assert receipt['schema']==m.RECEIPT_SCHEMA and receipt['operation']==m.OPERATION and receipt['scope_sha256']==m.SCOPE_SHA256
        assert receipt['core_sha256']==m.CORE_SHA256==f.assembler().core_sha256()
        assert (receipt['request_sha256'],receipt['authority_sha256'],receipt['go_sha256'],receipt['payload_sha256'])==(
            docs.pins().request,docs.pins().authority,docs.pins().go,f.sha(k.source)) and receipt['host_binding_sha256']==f.HOST
        assert receipt['ready'] is False and receipt['secret_bytes_in_receipt'] is False
        if not m.ACTIVATION_ALLOWED:assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
        assert receipt['size_reductions']==[] and len(f.line(receipt))<=m.RECEIPT_LIMIT+m.SEAL_OVERHEAD
        assert m.canonical(receipt['effects'])==m.canonical(docs.go['effects'])
        assert hostemu.SECRET.encode() not in f.line(receipt) and b'never-emit' not in f.line(receipt),'no value of an environment reaches a receipt'
        if not m.WRITES_ALLOWED:assert host.mutating()==[] and engine_state(host)==before
        # exactly what the launcher prints is what the reviewed transport accepts as a complete result
        value=json.loads(f.line(receipt));claimed=value.pop('metadata_sha256');assert f.sha(f.canonical(value))==claimed

    @pytest.mark.parametrize('mode,status,returncode',[('refused','KNOWN_REFUSAL',1),('partial','KNOWN_PARTIAL',2),('complete','KNOWN_COMPLETE',0),
                                                       ('raise_value','UNCERTAIN',3),('raise_key','UNCERTAIN',3),('not_a_dict','UNCERTAIN',3),
                                                       ('exit','UNCERTAIN',1)])
    def test_launcher_files_an_exception_that_escapes_run_as_uncertain_never_as_a_refusal(self,mode,status,returncode):
        """The payload is entered with exit code 3. Only a returned object can become exit 0, 1 or 2."""
        k=f.load(self.DIRECTORY);source=(STUB%mode).encode();blobs=[b'{"a":1}',b'{"b":2}',b'{"c":3}']
        payload=k.l.build(source,*blobs,expected_payload_sha256=f.sha(source),expected_request_sha256=f.sha(blobs[0]),
                          expected_authority_sha256=f.sha(blobs[1]),expected_go_sha256=f.sha(blobs[2]))
        outcome,out,err=k.t.once(payload,payload_sha256=f.sha(payload),command=ISOLATED,command_sha256=k.t.command_pin(ISOLATED),
                                 authorize=lambda a,b:True,seconds=60)
        assert (outcome['status'],outcome['returncode'])==(status,returncode)
        if status=='UNCERTAIN' and mode!='exit':assert json.loads(out)['status']=='RUN_RAISED_STATE_UNKNOWN' and err==b''

    def test_launcher_refuses_wrong_pins_at_build_and_on_stdin(self):
        k,docs,_=self.one();raws=docs.raw()
        with pytest.raises(ValueError,match='BUILD_PIN'):
            k.l.build(k.source,*raws,expected_payload_sha256='0'*64,expected_request_sha256=f.sha(raws[0]),
                      expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))
        payload=k.l.build(k.source,*raws,expected_payload_sha256=f.sha(k.source),expected_request_sha256=f.sha(raws[0]),
                          expected_authority_sha256=f.sha(raws[1]),expected_go_sha256=f.sha(raws[2]))
        tampered=payload.replace(f.sha(raws[2]).encode(),b'f'*64)
        done=subprocess.run(ISOLATED,input=tampered,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
        assert done.returncode==1 and json.loads(done.stdout)=={'schema':'HOSTOPS_STDIN_RESULT_V1','status':'REFUSED','code':'STDIN_DOCUMENT_PIN'}

    # ---------------------------------------------------------------- documents: bytes, keys, names
    def test_pins_must_match_the_bytes(self):
        k,docs,_=self.one();raws=docs.raw()
        for name in ('payload','request','authority','go'):
            for bad in ('0'*64,'f'*64,None,'F'*64):
                values={field:getattr(docs.pins(),field) for field in ('payload','request','authority','go')};values[name]=bad
                assert refusal(lambda:k.m.authenticate(*raws,pins=k.m.Pins(**values),payload_bytes=k.source,clock=lambda:docs.now,
                                                       monotonic=lambda:0,executor_uid=lambda:0))=='PIN_MISMATCH'

    @pytest.mark.parametrize('index,code',[(0,'REQUEST_KEYS'),(1,'AUTHORITY_KEYS'),(2,'GO_KEYS')])
    def test_each_document_has_exactly_its_keys(self,index,code):
        k,docs,_=self.one();document=(docs.request,docs.authority,docs.go)[index]
        for key in sorted(document):
            saved=document.pop(key);assert refusal(lambda:auth_raw(k,docs.raw(),docs.now))==code;document[key]=saved
        document['extra']=1;assert refusal(lambda:auth_raw(k,docs.raw(),docs.now))==code;del document['extra']
        docs.plan['extra']=1;docs.chain();assert refusal(docs.authenticate)=='PLAN_KEYS';del docs.plan['extra']
        for key in sorted(k.m.PLAN_KEYS|k.m.PLAN_COMMON_KEYS):
            if key=='host_binding_sha256':continue
            saved=docs.plan.pop(key);docs.chain();assert refusal(docs.authenticate)=='PLAN_KEYS';docs.plan[key]=saved
        docs.chain();docs.authenticate()

    def test_documents_are_decoded_from_bytes_and_must_be_canonical(self):
        k,docs,_=self.one();raws=docs.raw();now=docs.now
        spaced=json.dumps(docs.request,sort_keys=True).encode();assert refusal(lambda:auth_raw(k,[spaced,raws[1],raws[2]],now))=='DOCUMENT_NOT_CANONICAL'
        reordered=json.dumps(dict(reversed(list(docs.go.items()))),separators=(',',':')).encode()
        assert json.loads(reordered)==docs.go and refusal(lambda:auth_raw(k,[raws[0],raws[1],reordered],now))=='DOCUMENT_NOT_CANONICAL'
        duplicate=raws[1][:-1]+b',"status":"SIGNED"}';assert refusal(lambda:auth_raw(k,[raws[0],duplicate,raws[2]],now))=='DUPLICATE_KEY'
        assert refusal(lambda:auth_raw(k,[raws[0],raws[1],raws[2][:-1]+b',"x":NaN}'],now))=='NONFINITE_JSON'
        assert refusal(lambda:auth_raw(k,[raws[0],raws[1],b'{not json'],now))=='JSON_INVALID'
        assert refusal(lambda:auth_raw(k,[raws[0],b'[]',raws[2]],now))=='DOCUMENT_TYPE'
        assert refusal(lambda:auth_raw(k,[b'{"a":"'+b'x'*65536+b'"}',raws[1],raws[2]],now))=='DOCUMENT_SIZE'

    @pytest.mark.parametrize('document,field,value,code',UNBOUND_MEMBERS)
    def test_every_unbound_or_foreign_member_has_its_constant_refusal(self,document,field,value,code):
        k,docs,_=self.one()
        target={'request':docs.request,'authority':docs.authority,'go':docs.go,'plan':docs.plan}[document]
        if value=='FLIP':value=not target[field]
        target[field]=value;docs.chain(effects=False,criterion=False)
        assert refusal(docs.authenticate)==code
        result=docs.run(Untouchable());assert (result['status'],result['code'],result['phase_reached'])==('REFUSED',code,'AUTHENTICATION')
        assert result['outcome']==k.m.REFUSED_OUTCOME and f.sealed(result)

    def test_activation_flag_is_the_constant_of_the_source_in_all_three_documents(self):
        """A source that switches no unit accepts no document that allows an activation, and the reverse."""
        k,docs,_=self.one();flag=k.m.ACTIVATION_ALLOWED;assert type(flag) is bool and (not flag or k.m.WRITES_ALLOWED)
        for document in (docs.request,docs.authority,docs.go):document['activation_allowed']=not flag
        docs.chain();assert refusal(docs.authenticate)=='REQUEST_SCOPE'
        for document in (docs.request,docs.authority,docs.go):document['activation_allowed']=flag
        docs.chain();docs.authenticate()
        for value in (0,1,'false','true',None):
            if value is flag:continue
            docs.request['activation_allowed']=value;docs.chain();assert refusal(docs.authenticate)=='REQUEST_SCOPE'
        docs.request['activation_allowed']=flag

    def test_owner_is_bound_and_equal_in_authority_and_go(self):
        k,docs,_=self.one()
        for value in ('UNBOUND','',None,7,'x'*129):
            docs.go['owner']=value;docs.authority['owner']=value;docs.chain();assert refusal(docs.authenticate)=='OWNER_UNBOUND'

    def test_transport_binding_and_writes_flag_in_every_document(self):
        k,docs,_=self.one()
        for field,value in (('target',None),('target',''),('command_sha256',None),('command_sha256','0'*64),('remote_command','sudo -n /bin/sh'),
                            ('runtime_sha256',None),('runtime_sha256',{k.name:'3'*64}),('runtime_sha256',{})):
            saved=docs.go['transport_binding'][field];docs.go['transport_binding'][field]=value;docs.chain()
            assert refusal(docs.authenticate)=='GO_TRANSPORT_UNBOUND';docs.go['transport_binding'][field]=saved
        for document,code in ((docs.authority,'AUTHORITY_UNBOUND'),(docs.go,'GO_UNBOUND')):
            document['writes_allowed']=not k.m.WRITES_ALLOWED;docs.chain();assert refusal(docs.authenticate)==code
            document['writes_allowed']=k.m.WRITES_ALLOWED
        docs.chain();docs.authenticate()

    def test_hash_chain_between_the_three_documents(self):
        k,docs,_=self.one()
        docs.authority['request_sha256']='3'*64;docs.go['authority_sha256']=f.sha(f.canonical(docs.authority))
        assert refusal(docs.authenticate)=='AUTHORITY_UNBOUND';docs.chain()
        docs.go['request_sha256']='3'*64;assert refusal(docs.authenticate)=='GO_UNBOUND';docs.chain()
        docs.go['authority_sha256']='3'*64;assert refusal(docs.authenticate)=='GO_UNBOUND';docs.chain();docs.authenticate()

    def test_host_binding_is_one_non_null_value_in_three_documents_and_the_plan(self):
        k,docs,_=self.one()
        for target in (docs.authority,docs.go):
            target['host_binding_sha256']='2'*64;docs.chain();assert refusal(docs.authenticate)=='HOST_BINDING';target['host_binding_sha256']=f.HOST
        for value in (None,'0'*64,'A'*64,'1'*63):
            for target in (docs.request,docs.authority,docs.go,docs.plan):target['host_binding_sha256']=value
            docs.chain();assert refusal(docs.authenticate)=='HOST_BINDING'

    def test_effects_are_literal_in_authority_and_go_and_recomputed_from_the_plan(self):
        k,docs,_=self.one();assert docs.authority['effects']==docs.go['effects'] and docs.go['effects']['operation']==k.m.OPERATION
        for target in (docs.authority,docs.go):
            for change in (None,{},dict(target['effects'],operation='OTHER'),dict(target['effects'],extra=1)):
                saved=target['effects'];target['effects']=change;docs.chain(effects=False)
                assert refusal(docs.authenticate)=='EFFECTS_BINDING';target['effects']=saved
        docs.chain();docs.authenticate()

    def test_effects_equal_in_authority_and_go_but_not_those_of_the_plan_are_refused(self):
        """The comparison is with what the code recomputes from the plan, not between the two documents."""
        k,docs,_=self.one();good=json.loads(f.canonical(docs.go['effects']))
        for key in sorted(good):
            changed={name:value for name,value in good.items() if name!=key}
            docs.authority['effects']=changed;docs.go['effects']=json.loads(f.canonical(changed));docs.chain(effects=False)
            assert refusal(docs.authenticate)=='EFFECTS_BINDING',key
        for changed in (dict(good,extra=1),dict(good,operation='GO_OF_ANOTHER_OPERATION')):
            docs.authority['effects']=changed;docs.go['effects']=json.loads(f.canonical(changed));docs.chain(effects=False)
            assert refusal(docs.authenticate)=='EFFECTS_BINDING'
        docs.chain();docs.authenticate()

    def test_claim_root_identity_transport_binding_and_plan_window_member_by_member(self):
        k,docs,_=self.one();good=dict(docs.go['claim_root_identity']);now=docs.now
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
        for field,instant in (('not_before',now-timedelta(seconds=1)),('not_before',now+timedelta(seconds=1)),('expires_at',now+timedelta(minutes=4))):
            saved=docs.plan['window'][field];docs.plan['window'][field]=instant.isoformat();docs.chain()
            assert refusal(docs.authenticate)=='PLAN_WINDOW';docs.plan['window'][field]=saved
        docs.chain();docs.authenticate()

    def test_evidence_names_the_prior_receipts_and_the_operations_the_source_requires(self):
        k,docs,_=self.one();m=k.m
        for bad in (None,'x',[{'role':'PRECHECK','operation':'X','receipt_sha256':'0'*64}],[{'role':'PRECHECK','operation':'X'}],
                    [{'role':'lower','operation':'X','receipt_sha256':'a'*64}],[{'role':'A','operation':'X','receipt_sha256':None}],
                    [{'role':'A','operation':'X','receipt_sha256':'a'*64}]*17):
            docs.request['evidence']=bad;docs.chain();assert refusal(docs.authenticate)=='EVIDENCE_UNBOUND'
        docs.request['evidence']=[];docs.chain()
        if m.EVIDENCE_REQUIRED:assert refusal(docs.authenticate)=='EVIDENCE_UNBOUND'
        else:docs.authenticate()
        other=[{'role':'OTHER','operation':'GO_READONLY_SOMETHING_ELSE_01','receipt_sha256':'a'*64}]
        for index,name in enumerate(m.EVIDENCE_OPERATIONS):
            rest=[{'role':'R%d'%number,'operation':item,'receipt_sha256':'b'*64} for number,item in enumerate(m.EVIDENCE_OPERATIONS) if item!=name]
            docs.request['evidence']=other+rest;docs.chain();assert refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'
            result=docs.run(Untouchable());assert (result['status'],result['code'])==('REFUSED','EVIDENCE_OPERATION_MISSING')
            docs.request['evidence']=other+rest+[{'role':'NEAR','operation':name[:-1],'receipt_sha256':'b'*64}];docs.chain()
            assert refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'
        docs.request['evidence']=other+[{'role':'R%d'%number,'operation':item,'receipt_sha256':'b'*64} for number,item in enumerate(m.EVIDENCE_OPERATIONS)]
        docs.chain();docs.authenticate()

    def test_scope_is_fixed_by_the_source_and_signed(self):
        k,docs,_=self.one();m=k.m
        docs.plan['scope']['limits']['max_seconds']=61;docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
        docs.plan['scope']=json.loads(m.canonical(m.SCOPE));docs.plan['scope']['never']=[];docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
        docs.plan['scope']=json.loads(m.canonical(m.SCOPE));docs.plan['scope']['core_sha256']='3'*64;docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
        docs.plan['scope']=None;docs.chain();assert refusal(docs.authenticate)=='SCOPE_MISMATCH'
        assert m.SCOPE['statement']==m.SCOPE_STATEMENT and m.SCOPE['dates']==list(m.DATES) and m.SCOPE['core_sha256']==m.CORE_SHA256
        if hasattr(m,'COMMANDS'):
            assert m.SCOPE['commands'] is m.COMMANDS and m.SCOPE['command_classes'] is m.COMMAND_CLASSES and all(row['tool'] in m.BINARIES for row in m.COMMANDS.values())

    # ---------------------------------------------------------------- one operation never accepts another's documents
    def test_documents_of_another_operation_are_refused_in_both_directions(self):
        mine_k,mine,_=self.one();raws=mine.raw()
        for directory in self.others():
            k=f.load(directory);their_now=f.moment(k)
            theirs=types_docs(k,their_now)
            assert refusal(lambda:auth_raw(mine_k,theirs.raw(),mine.now))=='REQUEST_OR_EXECUTOR_UNBOUND'
            assert refusal(lambda:auth_raw(mine_k,[raws[0],theirs.raw()[1],raws[2]],mine.now))=='AUTHORITY_UNBOUND'
            assert refusal(lambda:auth_raw(mine_k,[raws[0],raws[1],theirs.raw()[2]],mine.now))=='GO_UNBOUND'
            # the reverse direction: their source, offered my documents (pinned as its own would be)
            assert refusal(lambda:auth_raw(k,raws,mine.now))=='REQUEST_OR_EXECUTOR_UNBOUND'
            # their GO re-pointed at my request, authority and payload still carries their names
            go=dict(theirs.go,request_sha256=mine.go['request_sha256'],authority_sha256=mine.go['authority_sha256'],payload_sha256=mine.go['payload_sha256'],
                    effects=mine.go['effects'],transport_binding=mine.go['transport_binding'])
            assert refusal(lambda:auth_raw(mine_k,[raws[0],raws[1],f.canonical(go)],mine.now))=='GO_UNBOUND'
            for field in ('schema','operation','phase'):
                for target,source,code in ((mine.request,theirs.request,'REQUEST_OR_EXECUTOR_UNBOUND'),(mine.authority,theirs.authority,'AUTHORITY_UNBOUND'),(mine.go,theirs.go,'GO_UNBOUND')):
                    saved=target[field];target[field]=source[field]
                    mine.chain();assert refusal(mine.authenticate)==code;target[field]=saved
            mine.chain();mine.authenticate()

    @pytest.mark.parametrize('schema,operation,phase',OLD)
    def test_names_of_every_earlier_operation_are_refused_at_both_layers(self,tmp_path,schema,operation,phase):
        k,docs,_=self.one()
        for index,(fields,code,local) in enumerate(((dict(schema=schema),'GO_UNBOUND','INNER_AUTHORITY'),(dict(operation=operation),'GO_UNBOUND',None),
                                  (dict(phase=phase),'GO_UNBOUND',None),(dict(schema=schema,operation=operation,phase=phase),'GO_UNBOUND','INNER_AUTHORITY'))):
            saved=dict(docs.go);docs.go.update(fields);docs.chain()
            assert refusal(docs.authenticate)==code
            directory=tmp_path/('go%d'%index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
            found=refusal(dispatch.prepare);assert found==(local or found) and found in ('INNER_AUTHORITY','GO_UNBOUND','READONLY_SCOPE','WRITE_SCOPE')
            assert not dispatch.claims();docs.go.clear();docs.go.update(saved)
        for index,(target,code) in enumerate(((docs.request,'REQUEST_OR_EXECUTOR_UNBOUND'),(docs.authority,'AUTHORITY_UNBOUND'))):
            saved=dict(target);target.update(schema=schema.replace('_GO_','_REQUEST_' if target is docs.request else '_AUTHORITY_'),operation=operation)
            docs.chain();assert refusal(docs.authenticate)==code
            directory=tmp_path/('doc%d'%index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
            assert refusal(dispatch.prepare)=='INNER_AUTHORITY' and not dispatch.claims()
            target.clear();target.update(saved)

    # ---------------------------------------------------------------- executor, window, clocks
    def test_effective_uid_and_gid_must_be_root_before_anything_is_looked_at(self):
        k,docs,host=self.one()
        assert refusal(lambda:docs.authenticate(executor_uid=lambda:501))=='REQUEST_OR_EXECUTOR_UNBOUND'
        result=docs.run(Untouchable(),executor_uid=lambda:501);assert (result['status'],result['code'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND')
        for actor in ((0,1000),(1000,0)):
            k,docs,host=self.one();host.actor=actor;before=engine_state(host);result=docs.run(host)
            assert (result['status'],result['code'],result['outcome'])==('REFUSED','EXECUTOR_IDENTITY',k.m.REFUSED_OUTCOME)
            assert host.mutating()==[] and engine_state(host)==before and not any(entry[0] in ('lstat','read','run','open') for entry in host.log)

    def test_window_boundaries_span_and_strict_utc(self):
        k,docs,_=self.one();now=docs.now;start,end=now,now+timedelta(minutes=5);day=now.date().isoformat()
        for instant,code in ((start-timedelta(microseconds=1),'OUTSIDE_GO_WINDOW'),(end,'OUTSIDE_GO_WINDOW'),(end+timedelta(hours=1),'OUTSIDE_GO_WINDOW')):
            assert refusal(lambda:docs.authenticate(clock=lambda:instant))==code
        for instant in (start,end-timedelta(microseconds=1)):docs.authenticate(clock=lambda:instant)
        for target in (docs.request,docs.authority,docs.go):
            for field in ('not_before','not_after'):
                saved=target[field]
                for value,code in ((None,'WINDOW_UNBOUND'),('yesterday','WINDOW_UNBOUND'),(1759510800,'WINDOW_UNBOUND'),(day+'T17:00:00','WINDOW_NOT_UTC'),
                                   (day+'T14:00:00-03:00','WINDOW_NOT_UTC'),(day+'T18:00:00+01:00','WINDOW_NOT_UTC')):
                    target[field]=value;docs.chain();assert refusal(docs.authenticate)==code
                target[field]=saved
        docs.chain();docs.authenticate()
        # the gate is the latest start and the earliest end of the three documents
        docs.go['not_after']=(now+timedelta(minutes=1)).isoformat();docs.chain()
        assert refusal(lambda:docs.authenticate(clock=lambda:now+timedelta(minutes=2)))=='OUTSIDE_GO_WINDOW'
        docs.go['not_after']=docs.request['not_after'];docs.authority['not_before']=(now+timedelta(minutes=1)).isoformat();docs.chain()
        assert refusal(docs.authenticate)=='OUTSIDE_GO_WINDOW'
        # a window as long as the UTC day is not a short window
        cap=k.m.MAX_GATE_SPAN_SECONDS;assert 0<cap<=(900 if k.m.WRITES_ALLOWED else 3600)
        docs.shift(now,now+timedelta(seconds=cap));docs.authenticate()
        docs.shift(now,now+timedelta(seconds=cap+1));assert refusal(docs.authenticate)=='WINDOW_SPAN'
        docs.shift(now,now);assert refusal(docs.authenticate)=='WINDOW_SPAN'
        docs.shift(now,now+timedelta(minutes=5));docs.plan['window']['expires_at']=(now+timedelta(minutes=4)).isoformat();docs.chain()
        assert refusal(docs.authenticate)=='PLAN_WINDOW'

    def test_gate_is_bounded_by_the_latest_start_and_the_earliest_end_whichever_document_holds_them(self):
        k,docs,_=self.one();now=docs.now;early=(now+timedelta(minutes=1)).isoformat();late=early
        for holder in ('request','authority','go'):
            docs.shift(now,now+timedelta(minutes=5));getattr(docs,holder)['not_after']=early
            if holder=='request':docs.plan['window']['expires_at']=early
            docs.chain();docs.authenticate(clock=lambda:now+timedelta(seconds=59))
            for instant in (now+timedelta(minutes=1),now+timedelta(minutes=2)):
                assert refusal(lambda:docs.authenticate(clock=lambda:instant))=='OUTSIDE_GO_WINDOW',holder
            docs.shift(now,now+timedelta(minutes=5));getattr(docs,holder)['not_before']=late
            if holder=='request':docs.plan['window']['not_before']=late
            docs.chain();docs.authenticate(clock=lambda:now+timedelta(seconds=60))
            for instant in (now,now+timedelta(seconds=59)):
                assert refusal(lambda:docs.authenticate(clock=lambda:instant))=='OUTSIDE_GO_WINDOW',holder

    def test_every_instant_of_the_three_windows_lies_on_the_signed_day(self):
        k,docs,_=self.one();now=docs.now;day=now.date();midnight=datetime(day.year,day.month,day.day,tzinfo=timezone.utc)
        # a window that crosses midnight into the signed day, and one that crosses out of it
        for start,end,signed in ((midnight-timedelta(minutes=2),midnight+timedelta(minutes=2),day),(midnight+timedelta(hours=23,minutes=58),midnight+timedelta(hours=24,minutes=2),day)):
            docs.shift(start,end);docs.request['date']=signed.isoformat();docs.chain()
            for instant in (start,end-timedelta(seconds=1)):
                assert refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_WINDOW_MISMATCH'
        # one instant alone on another day, in each document
        for holder in ('request','authority','go'):
            for field,value in (('not_before',midnight-timedelta(seconds=1)),('not_after',midnight+timedelta(days=1))):
                docs.shift(now,now+timedelta(minutes=5));getattr(docs,holder)[field]=value.isoformat()
                if holder=='request':docs.plan['window']['not_before' if field=='not_before' else 'expires_at']=value.isoformat()
                docs.chain();assert refusal(docs.authenticate)=='DATE_WINDOW_MISMATCH',(holder,field)

    def test_date_scope_is_the_class_of_the_source_at_both_layers(self,tmp_path):
        """Literal sets, not the module's own. A day of the epoch outside the class, the day before the epoch and the
        day after it are refused by the source and by the dispatcher; every day of the class passes both."""
        k,docs,_=self.one();expected=DATE_SETS[k.m.DATE_CLASS];assert k.m.DATES==expected
        for day in ('2026-10-01',)+EPOCH_DAYS+('2026-10-11','2027-10-05'):
            instant=noon(day);docs.shift(instant,instant+timedelta(minutes=5))
            directory=tmp_path/day;directory.mkdir();fresh,_=self.case(instant);dispatch=f.Dispatch(fresh,directory)
            if day in expected:
                docs.authenticate(clock=lambda:instant);assert dispatch.prepare()['status']=='AWAITING_PUBLICATION_NO_SPAWN'
            else:
                assert refusal(lambda:docs.authenticate(clock=lambda:instant))=='DATE_NOT_IN_SCOPE'
                result=docs.run(Untouchable(),clock=lambda:instant);assert (result['status'],result['code'])==('REFUSED','DATE_NOT_IN_SCOPE')
                assert refusal(dispatch.prepare)=='DISPATCH_DATE' and not dispatch.claims()
        instant=noon(expected[0]);docs.shift(instant,instant+timedelta(minutes=5))
        for value in (None,20261003,[expected[0]]):
            docs.request['date']=value;docs.chain();assert refusal(docs.authenticate)=='DATE_NOT_IN_SCOPE'
        other=[day for day in EPOCH_DAYS+('2026-10-11',) if day!=expected[0]][0]
        docs.request['date']=other;docs.chain();assert refusal(lambda:docs.authenticate(clock=lambda:instant)) in ('DATE_WINDOW_MISMATCH','DATE_NOT_IN_SCOPE')

    def test_gate_monotonic_deadline_and_clock_reversal(self):
        k,docs,_=self.one();m=k.m;now=docs.now;wall=[now];mono=[100.0]
        gate=m.Gate(now,now+timedelta(minutes=5),lambda:wall[0],lambda:mono[0])
        assert gate()==60.0
        mono[0]=159.0;assert gate()==1.0
        mono[0]=160.0;assert refusal(gate)=='GO_EXPIRED'
        mono[0]=120.0;assert refusal(gate)=='CLOCK_REVERSED'
        gate=m.Gate(now,now+timedelta(minutes=5),lambda:wall[0],lambda:mono[0])
        wall[0]=now+timedelta(seconds=10);assert gate()==60.0
        wall[0]=now+timedelta(seconds=9);assert refusal(gate)=='CLOCK_REVERSED'
        wall[0]=now+timedelta(minutes=5);assert refusal(gate)=='GO_EXPIRED'
        wall[0]=now+timedelta(minutes=4,seconds=30);gate=m.Gate(now,now+timedelta(minutes=5),lambda:wall[0],lambda:mono[0]);assert gate()==30.0
        assert refusal(lambda:m.Gate(now,now+timedelta(minutes=5),lambda:now-timedelta(seconds=1),lambda:0))=='OUTSIDE_GO_WINDOW'

    def test_dry_gate_stops_before_anything_is_observed(self):
        """The binding step validates with a gate that raises: nothing may be touched and the exception must surface."""
        k,docs,_=self.one()
        class Dry(Exception):pass
        def gate():raise Dry()
        with pytest.raises(Dry):docs.perform(Untouchable(),gate=gate)
        state=k.m.Effects()
        with pytest.raises(Dry):docs.perform(Untouchable(),gate=gate,state=state)
        assert state.started is False and state.issued==0

    def test_expiry_before_the_first_observation_is_a_refusal_with_nothing_touched(self):
        k,docs,host=self.one();now=docs.now;wall=[now]
        def clock():
            value=wall[0];wall[0]=now+timedelta(minutes=6);return value          # in the window for authentication only
        result=docs.run(host,clock=clock)
        assert (result['status'],result['code'],result['outcome'])==('REFUSED','GO_EXPIRED',k.m.REFUSED_OUTCOME)
        assert host.log==[] and result['mutating_calls']['issued']==0

    # ---------------------------------------------------------------- run() never raises, and never calls a changed host untouched
    def test_any_failure_inside_the_run_is_a_returned_object_never_an_exception_and_never_a_false_refusal(self):
        """Every call the run makes on the host fails once, in four ways (an ordinary exception, an OS error, the death
        of the process, an interrupt). Whatever happens: run() returns a sealed object; a REFUSED receipt means that
        nothing changed; a host that changed is PARTIAL or COMPLETE; nothing of the injected failure is printed."""
        k,docs,host=self.one();m=k.m
        baseline=docs.run(host);total=host.calls;assert baseline['status']==m.COMPLETE_STATUS
        step=1 if total<=200 else max(1,total//200)
        for kind in (RuntimeError,OSError,hostemu.Death,KeyboardInterrupt):
            for index in list(range(1,total+1,step)):
                k,docs,host=self.one()
                def hook(host,name,detail,calls,index=index,kind=kind):
                    if calls==index:raise kind(5,'injected') if kind is OSError else kind('injected')
                previous=host.hook
                def both(host,name,detail,calls,hook=hook,previous=previous):
                    if previous is not None:previous(host,name,detail,calls)
                    hook(host,name,detail,calls)
                host.hook=both;before=engine_state(host)
                result=docs.run(host)
                assert type(result) is dict and result['status'] in ('REFUSED',m.PARTIAL_STATUS,m.COMPLETE_STATUS) and f.sealed(result)
                assert 'injected' not in json.dumps(result) and hostemu.SECRET not in json.dumps(result)
                changed=engine_state(host)!=before
                if result['status']=='REFUSED':assert not changed,(kind,index)
                if changed:assert m.WRITES_ALLOWED and result['status'] in (m.PARTIAL_STATUS,m.COMPLETE_STATUS)
                if not m.WRITES_ALLOWED:assert not changed and host.mutating()==[]
                if result['status']==m.COMPLETE_STATUS:assert kind is OSError or kind is RuntimeError   # a tolerated read only

    # ---------------------------------------------------------------- dispatcher: once, local claim, bindings
    def test_prepare_does_not_spawn_then_resume_once_and_the_go_is_single_use(self,tmp_path):
        k,docs,_=self.one();dispatch=f.Dispatch(docs,tmp_path)
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

    def test_dispatcher_refuses_unsigned_foreign_or_transplanted_documents_before_any_claim(self,tmp_path):
        k,docs,_=self.one();m=k.m
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
        for other in self.others():
            o=f.load(other);saved=(dispatch.config['schema'],dispatch.config['operation'])
            dispatch.config['schema']=json.loads((o.dir/'DISPATCH.UNBOUND.json').read_bytes())['schema'];dispatch.config['operation']=o.m.OPERATION
            dispatch.save(rebind=False);assert refusal(dispatch.prepare)=='DISPATCH_UNBOUND';dispatch.config['schema'],dispatch.config['operation']=saved
        # target transplant and claim root relocation after the GO was signed
        dispatch.config['target']='changed@unused.invalid';dispatch.config['command_sha256']=k.t.command_pin(k.d.command(dispatch.config))
        dispatch.save(rebind=False);assert refusal(dispatch.prepare)=='GO_TRANSPORT_BINDING'
        dispatch.config['target']='fixture@unused.invalid';dispatch.config['command_sha256']=k.t.command_pin(k.d.command(dispatch.config))
        other=directory/'other';other.mkdir(mode=0o700)
        dispatch.config['local_root_identity']={'path':str(other),'device':other.stat().st_dev,'inode':other.stat().st_ino}
        dispatch.config['attempt_directory']=str(other/'attempt');dispatch.save(rebind=False)
        assert refusal(dispatch.prepare)=='GO_CLAIM_ROOT_BINDING' and list(other.iterdir())==[] and not dispatch.claims()

    def test_dispatcher_write_scope_date_scope_and_late_start(self,tmp_path):
        k,docs,_=self.one();m=k.m;label='WRITE_SCOPE' if m.WRITES_ALLOWED else 'READONLY_SCOPE';now=docs.now
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
        for day in ('2026-10-01','2026-10-11'):
            assert refusal(window(noon(day),noon(day)+timedelta(minutes=5)).prepare)=='DISPATCH_DATE'
        last=noon(m.DATES[-1]).replace(hour=23,minute=58)
        assert refusal(window(last,last+timedelta(minutes=4)).prepare)=='DISPATCH_DATE'
        wrong=[day for day in EPOCH_DAYS+('2026-10-11',) if day!=now.date().isoformat()][0]
        assert refusal(window(now,now+timedelta(minutes=5),date=wrong).prepare)=='INNER_AUTHORITY'
        window(now,now+timedelta(minutes=5));assert not dispatch.claims()
        assert refusal(lambda:dispatch.prepare(clock=lambda:now+timedelta(seconds=221)))=='WINDOW_WITH_WATCHDOG' and not dispatch.claims()
        dispatch.config['latest_start']=(now+timedelta(seconds=219)).isoformat();dispatch.save(rebind=False)
        assert refusal(dispatch.prepare)=='LATEST_START_BINDING' and not dispatch.claims()

    def test_dispatcher_validates_the_whole_inner_authority_locally_before_the_claim(self,tmp_path):
        """A malformed plan cannot spend the single-use GO: the source's own authenticate runs before any claim."""
        k,docs,_=self.one()
        docs.plan['scope']['limits']['max_seconds']=61;dispatch=f.Dispatch(docs,tmp_path)
        assert refusal(dispatch.prepare)=='SCOPE_MISMATCH' and not dispatch.claims()
        docs.plan['scope']=json.loads(k.m.canonical(k.m.SCOPE));docs.authority['effects']={'operation':'x'};dispatch.save(rebind=False)
        docs.chain(effects=False);docs.go['claim_root_identity']=dispatch.config['local_root_identity']
        docs.go['transport_binding']={key:dispatch.config[key] for key in ('target','remote_command','command_sha256','runtime_sha256')}
        docs.chain(effects=False);dispatch.save(rebind=False)
        assert refusal(dispatch.prepare)=='EFFECTS_BINDING' and not dispatch.claims()
        for document in (docs.request,docs.authority,docs.go):document['activation_allowed']=not k.m.ACTIVATION_ALLOWED
        docs.chain();dispatch.save();assert refusal(dispatch.prepare)=='REQUEST_SCOPE' and not dispatch.claims()

    def test_publication_and_receipt_bindings(self,tmp_path):
        k,docs,_=self.one();m=k.m;dispatch=f.Dispatch(docs,tmp_path);prepared=dispatch.prepare();published=dispatch.proof(prepared)
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

    def test_the_real_receipt_of_the_bound_fixture_is_accepted_by_the_dispatcher(self,tmp_path):
        """Not a stand-in: the sealed receipt of a complete emulated run, as the launcher prints it, passes the
        dispatcher's own bindings (schema and the three hashes) and its 64 KiB decode limit."""
        k,docs,host=self.one();dispatch=f.Dispatch(docs,tmp_path);receipt=docs.run(host);assert receipt['status']==k.m.COMPLETE_STATUS
        result=dispatch.resume(dispatch.proof(dispatch.prepare()),dispatch.fake(out=f.line(receipt),status='KNOWN_COMPLETE'))
        assert result['status']=='KNOWN_COMPLETE' and result['stdout_sha256']==f.sha(f.line(receipt))

    def test_receipt_of_another_operation_is_filed_uncertain(self,tmp_path):
        k,docs,_=self.one()
        names=[f.load(other).m.RECEIPT_SCHEMA for other in self.others()]+['READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1','WRITE_HOSTOPS_PROVISION_RECEIPT_V1']
        for index,schema in enumerate(names):
            directory=tmp_path/str(index);directory.mkdir();fresh,_=self.case();dispatch=f.Dispatch(fresh,directory);published=dispatch.proof(dispatch.prepare())
            foreign=f.canonical({'schema':schema,'request_sha256':dispatch.config['request']['sha256'],
                                 'go_sha256':dispatch.config['go']['sha256'],'payload_sha256':dispatch.config['source']['sha256']})
            assert dispatch.resume(published,dispatch.fake(out=foreign))['status']=='UNCERTAIN'

    def test_cli_never_spawns_on_prepare_and_exits_zero_only_for_known_complete(self,tmp_path,monkeypatch,capsys):
        k,docs,_=self.one();dispatch=f.Dispatch(docs,tmp_path)
        done=subprocess.run([sys.executable,'-B',str(k.dir/'dispatch_once.py'),'--config',dispatch.pin['path'],'--config-sha256',dispatch.pin['sha256'],
                             '--phase','prepare'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
        assert done.returncode==2 and done.stderr==b'' and json.loads(done.stdout)['status'] in ('REFUSED_OR_UNCERTAIN','AWAITING_PUBLICATION_NO_SPAWN')
        assert not (Path(dispatch.config['attempt_directory'])/'spawn.claim').exists()
        for status,code in (('KNOWN_COMPLETE',0),('KNOWN_PARTIAL',2),('AWAITING_PUBLICATION_NO_SPAWN',2),('UNCERTAIN',2),('KNOWN_REFUSAL',2)):
            monkeypatch.setattr(k.d,'execute',lambda *args,**kwargs:{'status':status});monkeypatch.setattr(sys,'argv',['dispatch_once.py','--config','/x','--config-sha256','0'*64])
            assert k.d.main()==code
        capsys.readouterr()

    def test_end_to_end_with_the_bound_payload_under_isolated_python_as_non_root(self,tmp_path):
        """The whole local chain with real processes: the bound payload under isolated python refuses for the effective
        uid (the test user is not root) or, outside the code date set, for the date; never anything else."""
        if os.geteuid()==0:pytest.skip('as root the payload would act on this machine')
        k,docs,_=self.one();dispatch=f.Dispatch(docs,tmp_path)
        done=subprocess.run(ISOLATED,input=dispatch.payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=60)
        result=json.loads(done.stdout);assert done.returncode==1 and done.stderr==b'' and result['status']=='REFUSED'
        assert result['code']=='REQUEST_OR_EXECUTOR_UNBOUND' and result['mutating_calls']['issued']==0 and result['schema']==k.m.RECEIPT_SCHEMA


def types_docs(k,now):
    """A syntactically bound document set of another operation, for the cross-refusal tests: its plan need not be
    valid, because every check under test comes before the plan is read."""
    fields={key:None for key in k.m.PLAN_KEYS};return f.Docs(k,fields,now=now)
