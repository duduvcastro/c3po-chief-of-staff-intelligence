"""K10 against documents that are not its own, and what leaves the run. A reviewer's hostile cases (review of
2026-10-02, lens: purity and authentication), made part of the suite.

Other operations. The two demonstration operations of the frozen core are always used. Every other set of documents is
named by the caller, because none of them is part of this directory and some exist on one machine only:
  HOSTOPS02_TEST_OTHER_OPERATIONS   directories separated by the path separator. Each is either an operation directory
                                    of this family (it holds build/ASSEMBLY.json) or a directory that holds
                                    REQUEST|AUTHORITY|GO.UNBOUND.json of an earlier family.
  HOSTOPS02_TEST_BOUND_POSTDEPLOY   the directory of the bound, owner-signed POSTDEPLOY rev5 set (real documents).
Without them those cases are skipped and say so. Offline, synthetic; nothing is contacted."""
import base64
from datetime import datetime,timedelta,timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

import family as f
import hostemu
import k10

def sha(b):return hashlib.sha256(b).hexdigest()
def can(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def named(variable):return [Path(item).resolve() for item in os.environ.get(variable,'').split(os.pathsep) if item]
def templates(directory):
    """Where the UNBOUND documents of one named directory are: its build/ for an operation of this family."""
    return directory/'build' if (directory/'build'/'ASSEMBLY.json').is_file() else directory
OTHERS=named('HOSTOPS02_TEST_OTHER_OPERATIONS')
DEMOS=[f.CORE/'tests'/'demo_read',f.CORE/'tests'/'demo_write']
SIBLINGS=[templates(directory) for directory in DEMOS+OTHERS]
OPERATIONS=[directory for directory in OTHERS if (directory/'build'/'ASSEMBLY.json').is_file()]
BOUND_POSTDEPLOY=(named('HOSTOPS02_TEST_BOUND_POSTDEPLOY') or [None])[0]
def auth(k,raws,now,payload=None):
    payload=k.source if payload is None else payload
    pins=k.m.Pins(payload=sha(payload),request=sha(raws[0]),authority=sha(raws[1]),go=sha(raws[2]))
    return k.m.authenticate(*raws,pins=pins,payload_bytes=payload,clock=lambda:now,monotonic=lambda:0,executor_uid=lambda:0)

# ------------------------------------------------------------------ (4) documents of other families / operations
def bind_like(template_dir,mine):
    """Their UNBOUND request/authority/GO made 'bound' with every null filled from MY valid documents (their names kept)."""
    out=[]
    their={name:json.loads((template_dir/(name.upper()+'.UNBOUND.json')).read_bytes()) for name in ('request','authority','go')}
    for name,mydoc in (('request',mine.request),('authority',mine.authority),('go',mine.go)):
        doc=their[name]
        for key,value in mydoc.items():
            if key in ('schema','operation','phase','scope_sha256','scope_statement','success_criterion','writes_allowed','activation_allowed'):continue
            if key=='plan':
                plan=dict(doc.get('plan') or {})
                for pk,pv in mydoc['plan'].items():
                    if pk in ('schema','phase','scope'):continue
                    plan[pk]=pv
                plan['status']='BOUND';doc['plan']=plan;continue
            doc[key]=value
        doc['status']='BOUND' if name=='request' else 'SIGNED'
        out.append(doc)
    req,aut,go=out
    aut['request_sha256']=sha(can(req));go['request_sha256']=aut['request_sha256'];go['authority_sha256']=sha(can(aut))
    return [can(req),can(aut),can(go)]

@pytest.mark.parametrize('directory',SIBLINGS,ids=lambda p:p.parent.name+'/'+p.name if p.name=='build' else p.name)
def test_documents_of_every_sibling_operation_are_refused_whole_and_one_by_one(directory):
    if not (directory/'REQUEST.UNBOUND.json').is_file():pytest.skip('no templates there')
    docs,host=k10.case();k=docs.k;mine=docs.raw();docs.authenticate()
    theirs=bind_like(directory,docs)
    assert f.refusal(lambda:auth(k,theirs,docs.now)) in ('REQUEST_OR_EXECUTOR_UNBOUND','REQUEST_KEYS','AUTHORITY_KEYS','GO_KEYS')
    # one foreign document among two of mine, re-chained so that only the names differ
    aut=json.loads(theirs[1]);aut['request_sha256']=sha(mine[0])
    assert f.refusal(lambda:auth(k,[mine[0],can(aut),mine[2]],docs.now)) in ('AUTHORITY_UNBOUND','AUTHORITY_KEYS')
    go=json.loads(theirs[2]);go['request_sha256']=sha(mine[0]);go['authority_sha256']=sha(mine[1])
    assert f.refusal(lambda:auth(k,[mine[0],mine[1],can(go)],docs.now)) in ('GO_UNBOUND','GO_KEYS')
    # the run itself, on a host that must not be touched
    pins=k.m.Pins(payload=sha(k.source),request=sha(theirs[0]),authority=sha(theirs[1]),go=sha(theirs[2]))
    receipt=k.m.run(*theirs,pins=pins,payload_bytes=k.source,host=f.Untouchable(),clock=lambda:docs.now,monotonic=lambda:0,executor_uid=lambda:0)
    assert receipt['status']=='REFUSED' and receipt['phase_reached']=='AUTHENTICATION' and receipt['mutating_calls']['issued']==0

def test_real_bound_documents_of_postdeploy_rev5_are_refused_by_k10_at_both_layers(tmp_path):
    bound=BOUND_POSTDEPLOY
    if bound is None or not bound.is_dir():pytest.skip('HOSTOPS02_TEST_BOUND_POSTDEPLOY is not set: the bound, owner-signed set exists on one machine only')
    raws=[(bound/'REQUEST.BOUND.json').read_bytes(),(bound/'DUDU_POSTDEPLOY01_AUTHORITY_REV5_20261002_DD4EC4BB.json').read_bytes(),
          (bound/'DUDU_POSTDEPLOY01_GO_REV5_20261002_DD4EC4BB.json').read_bytes()]
    docs,host=k10.case();k=docs.k
    for now in (docs.now,datetime(2026,10,2,16,0,tzinfo=timezone.utc)):
        code=f.refusal(lambda:auth(k,raws,now));assert code in ('REQUEST_KEYS','AUTHORITY_KEYS','GO_KEYS','REQUEST_OR_EXECUTOR_UNBOUND','DOCUMENT_NOT_CANONICAL'),code
        # with THEIR payload bytes pinned as the payload (what their config would do)
        code=f.refusal(lambda:auth(k,raws,now,payload=(bound/'disk_readonly.py').read_bytes()));assert code in ('REQUEST_KEYS','AUTHORITY_KEYS','GO_KEYS','REQUEST_OR_EXECUTOR_UNBOUND','DOCUMENT_NOT_CANONICAL'),code
    # my request with their GO / authority (transplant)
    mine=docs.raw()
    for raws2 in ([mine[0],raws[1],mine[2]],[mine[0],mine[1],raws[2]],[raws[0],mine[1],mine[2]]):
        assert f.refusal(lambda:auth(k,raws2,docs.now)) in ('REQUEST_KEYS','AUTHORITY_KEYS','GO_KEYS','REQUEST_OR_EXECUTOR_UNBOUND','AUTHORITY_UNBOUND','GO_UNBOUND','DOCUMENT_NOT_CANONICAL')
    # the dispatcher of K10 with a config whose blobs are PD's: refused before any claim
    dispatch=f.Dispatch(docs,tmp_path)
    for key,raw in zip(('request','authority','go'),raws):dispatch.config[key]=dispatch.put(key,raw)
    dispatch.pin=dispatch.put('config',f.canonical(dispatch.config))
    with pytest.raises(Exception):dispatch.prepare()
    assert not dispatch.claims()

def test_k10_documents_are_refused_by_the_dispatcher_of_each_sibling_built_here(tmp_path):
    if not OPERATIONS:pytest.skip('HOSTOPS02_TEST_OTHER_OPERATIONS names no operation of this family')
    docs,host=k10.case()
    for directory in OPERATIONS:
        other=f.load(directory)
        assert f.refusal(lambda:auth(other,docs.raw(),docs.now,payload=docs.k.source)) in ('REQUEST_OR_EXECUTOR_UNBOUND','REQUEST_KEYS')
        assert f.refusal(lambda:auth(other,docs.raw(),docs.now)) in ('REQUEST_OR_EXECUTOR_UNBOUND','REQUEST_KEYS')

def test_names_are_disjoint_from_every_sibling_and_every_older_family():
    m=k10.K().m;mine={m.OPERATION,m.PHASE,m.REQUEST_SCHEMA,m.AUTHORITY_SCHEMA,m.GO_SCHEMA,m.RECEIPT_SCHEMA,m.PLAN_SCHEMA}
    seen=set()
    for directory in SIBLINGS:
        for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF'):
            path=directory/(name+'.UNBOUND.json')
            if not path.is_file():continue
            doc=json.loads(path.read_bytes())
            seen|={doc.get(key) for key in ('schema','operation','phase') if doc.get(key)}
            if type(doc.get('plan')) is dict:seen|={doc['plan'].get('schema'),doc['plan'].get('phase')}
    assert seen and not mine&seen,mine&seen
    d=(k10.DIRECTORY/'build'/'dispatch_once.py').read_text()
    for directory in SIBLINGS:
        other=directory/'dispatch_once.py'
        if other.is_file():
            claim=re.findall(r"'([A-Z0-9_]+_GO_CLAIM_V1)'",other.read_text());mineclaim=re.findall(r"'([A-Z0-9_]+_GO_CLAIM_V1)'",d)
            assert claim and mineclaim and claim!=mineclaim

# ------------------------------------------------------------------ (4) date / window / executor / spare
def test_window_edges_of_monday_m1_and_the_spare_and_exact_900_seconds():
    for start,end in (('2026-10-05T08:26:00+00:00','2026-10-05T08:41:00+00:00'),('2026-10-05T08:42:00+00:00','2026-10-05T08:57:00+00:00')):
        a,b=datetime.fromisoformat(start),datetime.fromisoformat(end)
        docs,host=k10.case(now=a);docs.shift(a,b);docs.authenticate(clock=lambda:a);docs.authenticate(clock=lambda:b-timedelta(microseconds=1))
        assert f.refusal(lambda:docs.authenticate(clock=lambda:b))=='OUTSIDE_GO_WINDOW'
        assert f.refusal(lambda:docs.authenticate(clock=lambda:a-timedelta(microseconds=1)))=='OUTSIDE_GO_WINDOW'
        docs.now=a;receipt=docs.run(host);assert receipt['status']==docs.k.m.COMPLETE_STATUS
    # 901 s refused; a window on Sunday 21:00 BRT (UTC Monday 00:00) refused: New York is still on Sunday
    a=datetime.fromisoformat('2026-10-05T08:26:00+00:00');docs,_=k10.case(now=a);docs.shift(a,a+timedelta(seconds=901));assert f.refusal(lambda:docs.authenticate(clock=lambda:a))=='WINDOW_SPAN'
    a=datetime.fromisoformat('2026-10-05T00:00:00+00:00');docs,_=k10.case(now=a);docs.shift(a,a+timedelta(seconds=900))
    assert f.refusal(lambda:docs.authenticate(clock=lambda:a))=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'
    a=datetime.fromisoformat('2026-10-05T03:50:00+00:00');docs,_=k10.case(now=a);docs.shift(a,a+timedelta(seconds=900))
    assert f.refusal(lambda:docs.authenticate(clock=lambda:a+timedelta(minutes=11)))=='WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK'
    for day in ('2026-10-04','2026-10-06','2026-10-03','2026-09-28'):
        a=datetime.fromisoformat(day+'T08:26:00+00:00');docs,_=k10.case(now=a)
        assert f.refusal(lambda:docs.authenticate(clock=lambda:a))=='DATE_NOT_IN_SCOPE'
        r=docs.run(f.Untouchable(),clock=lambda:a);assert (r['status'],r['code'])==('REFUSED','DATE_NOT_IN_SCOPE')

def test_authority_or_go_window_reaching_before_the_new_york_day_cannot_open_the_gate_earlier():
    a=datetime.fromisoformat('2026-10-05T04:00:00+00:00');docs,host=k10.case(now=a);docs.shift(a,a+timedelta(seconds=900))
    early='2026-10-05T00:00:01+00:00'
    docs.authority['not_before']=early;docs.go['not_before']=early;docs.chain()
    docs.authenticate(clock=lambda:a)
    assert f.refusal(lambda:docs.authenticate(clock=lambda:a-timedelta(seconds=1)))=='OUTSIDE_GO_WINDOW'

def test_other_executors_and_a_changed_payload_byte_are_refused():
    docs,host=k10.case();k=docs.k
    for uid in (1,501,1000,-1,True,0.0,'0',None):
        r=docs.run(f.Untouchable(),executor_uid=lambda:uid)
        if uid is True or uid==0.0:
            # equal to 0 for Python: must still never be accepted as an int 0 from a document; os.geteuid() returns int
            continue
        assert (r['status'],r['code'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND'),uid
    changed=k.source.replace(b"RELEASE_EPOCH='R2D2-V2-SHADOW-2026-10-05'",b"RELEASE_EPOCH='R2D2-V2-SHADOW-2026-10-06'")
    assert changed!=k.source
    raws=docs.raw();pins=k.m.Pins(payload=sha(k.source),request=sha(raws[0]),authority=sha(raws[1]),go=sha(raws[2]))
    assert f.refusal(lambda:k.m.authenticate(*raws,pins=pins,payload_bytes=changed,clock=lambda:docs.now,monotonic=lambda:0,executor_uid=lambda:0))=='PIN_MISMATCH'
    pins2=k.m.Pins(payload=sha(changed),request=sha(raws[0]),authority=sha(raws[1]),go=sha(raws[2]))
    assert f.refusal(lambda:k.m.authenticate(*raws,pins=pins2,payload_bytes=changed,clock=lambda:docs.now,monotonic=lambda:0,executor_uid=lambda:0))=='REQUEST_OR_EXECUTOR_UNBOUND'

def test_spare_and_primary_differ_in_request_authority_go_and_claim_and_second_is_refused_on_the_host():
    a=datetime.fromisoformat('2026-10-05T08:26:00+00:00');b=datetime.fromisoformat('2026-10-05T08:42:00+00:00')
    d1,host=k10.case(now=a);d1.shift(a,a+timedelta(seconds=900));d2=f.Docs(d1.k,k10.fields(host),now=b);d2.shift(b,b+timedelta(seconds=900))
    r1,r2=d1.raw(),d2.raw();assert all(x!=y for x,y in zip(r1,r2)) and d1.go16()!=d2.go16()
    # each document of one set with the other two of the other set
    for i in range(3):
        mixed=list(r1);mixed[i]=r2[i]
        assert f.refusal(lambda:auth(d1.k,mixed,a)) in ('AUTHORITY_UNBOUND','GO_UNBOUND','WINDOW_SPAN','OUTSIDE_GO_WINDOW','PLAN_WINDOW','EFFECTS_BINDING')
    first=d1.run(host);assert first['status']==d1.k.m.COMPLETE_STATUS
    before=k10.state_of(host);second=d2.run(host)
    assert (second['status'],second['code'],second['mutating_calls']['issued'])==('REFUSED','DESTINATION_PRESENT',0) and k10.state_of(host)==before

# ------------------------------------------------------------------ (2) nothing nominal or secret leaves
CANARY='zzCANARYzz'
def test_free_text_of_the_documents_and_of_the_release_never_reaches_any_receipt_or_launcher_line():
    body=json.loads(k10.RELEASE)
    body['authorization_ref']=CANARY+'-authorization';body['package_consents'][0]['receipt_ref']=CANARY+'-receipt';body['extra_member']=CANARY+'-extra'
    raw=(json.dumps(body,indent=1,sort_keys=True)+'\n').encode()
    seen=[]
    def scenario(prepare=None,hook=None,**run):
        docs,host=k10.case(raw=raw)
        docs.authority['owner']=docs.go['owner']=CANARY+'-owner';docs.authority['owner_evidence']=CANARY+'-evidence'
        docs.go['transport_binding']['target']=CANARY+'@target.invalid';docs.go['claim_root_identity']['path']='/'+CANARY+'/claim'
        docs.request['evidence'][0]['receipt_sha256']='c'*64;docs.chain()
        if prepare:prepare(host)
        if hook:host.hook=hook
        receipt=docs.run(host,**run);line=f.line(receipt);seen.append((receipt['status'],receipt['code']))
        assert CANARY.encode() not in line,(receipt['status'],receipt['code'])
        assert base64.b64encode(raw)[:64] not in line and raw[:48] not in line and hostemu.BOOT.strip() not in line
        assert 'c'*64 not in line.decode()          # the evidence hash is not echoed either
        for value in walk(receipt):
            if type(value) is str:assert re.fullmatch(r'[A-Za-z0-9_./:+=<> ,()\'"-]*',value) is not None and len(value)<=1300,value
        return receipt
    def walk(value):
        if type(value) is dict:
            for item in value.values():
                for x in walk(item):yield x
        elif type(value) is list:
            for item in value:
                for x in walk(item):yield x
        else:yield value
    scenario()
    scenario(prepare=lambda host:host.tree.add(k10.BASE,dev=hostemu.DATA_DEVICE))
    scenario(prepare=lambda host:host.tree.remove(k10.PIN))
    scenario(executor_uid=lambda:501)
    # every host call fails once with an exception whose text is a canary (four kinds)
    k=k10.K()
    docs0,host0=k10.case(raw=raw);docs0.run(host0);total=host0.calls
    class Odd(Exception):pass
    for n in range(1,total+1):
        for make in (lambda:OSError(errno.EIO,CANARY+' /mnt/'+CANARY),lambda:Odd(CANARY),lambda:k.m.Refused(CANARY),lambda:k.m.Refused('X'*90),lambda:KeyboardInterrupt(CANARY),lambda:ValueError('CANARY_CODE_LOOKING')):
            def hook(host,name,detail,calls,n=n,make=make):
                if calls==n:raise make()
            r=scenario(hook=hook)
            assert r['code']!='CANARY_CODE_LOOKING'
    assert {'METADATA_ONLY_REQUIRES_REVIEW','REFUSED','PARTIAL_METADATA_REQUIRES_REVIEW'}=={status for status,_ in seen}

def test_authentication_refusal_codes_are_constants_whatever_the_documents_hold():
    docs,host=k10.case();k=docs.k
    hostile=[('request','date',CANARY),('request','operation',CANARY),('request','schema',{'x':CANARY}),('request','evidence',[{'role':CANARY,'operation':CANARY,'receipt_sha256':CANARY}]),
             ('go','scope_statement',CANARY),('go','success_criterion',CANARY),('go','effects',{'x':CANARY}),('authority','effects',[CANARY]),('request','plan',CANARY),
             ('request','plan',{'host_binding_sha256':f.HOST}),('request','not_before',CANARY),('go','transport_binding',{'target':CANARY})]
    for target,field,value in hostile:
        d,_=k10.case();getattr(d,target)[field]=value;d.chain()
        receipt=d.run(f.Untouchable());line=f.line(receipt)
        assert receipt['status']=='REFUSED' and CANARY.encode() not in line and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',receipt['code'])
    # hostile plan members
    for member,value in (('parent',CANARY),('parent',[{'path':'/','device':CANARY,'inode':1,'uid':0,'gid':0,'mode':0o755}]*3),('evidence_boot_id_sha256',CANARY),
                         ('release',CANARY),('release',{'path':CANARY,'content_b64':CANARY,'sha256':CANARY,'bytes':CANARY})):
        d,_=k10.case();d.plan[member]=value;d.chain()
        receipt=d.run(f.Untouchable());line=f.line(receipt)
        assert receipt['status']=='REFUSED' and CANARY.encode() not in line and re.fullmatch('[A-Z][A-Z0-9_]{0,79}',receipt['code']),(member,receipt)

def test_release_fields_shown_to_the_signers_cannot_carry_free_text():
    m=k10.K().m
    for field,value in (('approved_at','2026-10-03 19:40:00+00:00'),('approved_at','x'*10),('approved_at','2026-10-03T19:40:00+00:00\n'),('approved_at',''),('approved_at',None),('approved_at',20261003),
                        ('code_revision','DD4EC4BB8DAB4D8B0372B0F9EABC90BF6443E858'),('code_revision','dd4ec4bb'),('code_revision',None),
                        ('implementation_package_sha','0'*64),('implementation_package_sha','B5'*32),('implementation_package_sha',None),
                        ('epoch','R2D2-V2-SHADOW-2026-10-05 '),('epoch','R2D2-V2-SHADOW-2026-10-05\x00'),('epoch',['R2D2-V2-SHADOW-2026-10-05']),('first_session','2026-10-05T00:00:00'),
                        ('mode','certified'),('mode','DIAGNOSTIC'),('schema','R2D2_V2_RELEASE_V2')):
        raw=k10.altered(**{field:value})
        with pytest.raises(m.Refused):m.release_facts(raw)

def test_end_to_end_bound_payload_under_isolated_python_prints_one_line_and_nothing_on_stderr(tmp_path):
    """The exact stdin bytes, as a non-root user: a refusal with exit 1, one JSON line, empty stderr, no canary."""
    docs,host=k10.case();k=docs.k;docs.authority['owner']=docs.go['owner']=CANARY+'-owner';docs.chain();raws=docs.raw()
    payload=k.l.build(k.source,*raws,expected_payload_sha256=sha(k.source),expected_request_sha256=sha(raws[0]),expected_authority_sha256=sha(raws[1]),expected_go_sha256=sha(raws[2]))
    for extra in ([],['-W','error']):
        done=subprocess.run([sys.executable,'-I','-B']+extra+['-'],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin'},timeout=120)
        assert done.stderr==b'' and done.returncode==1,done.stderr[-800:]
        lines=done.stdout.splitlines();assert len(lines)==1 and CANARY.encode() not in done.stdout
        out=json.loads(lines[0]);assert out['status']=='REFUSED' and out['code'] in ('REQUEST_OR_EXECUTOR_UNBOUND','OUTSIDE_GO_WINDOW')

# ------------------------------------------------------------------ (3) refusal ordering: nothing mutating, nothing even fsynced, before a listed refusal
BEFORE=[('MAINTENANCE_PIN_ABSENT',lambda h,d:h.tree.remove(k10.PIN)),
        ('DESTINATION_PRESENT',lambda h,d:h.tree.add(k10.BASE,dev=hostemu.DATA_DEVICE,mode=0o700)),
        ('DESTINATION_PRESENT',lambda h,d:h.tree.add(k10.BASE,kind='symlink',dev=hostemu.DATA_DEVICE,mode=0o777,target='nowhere')),
        ('EVIDENCE_FROM_EARLIER_BOOT',lambda h,d:h.tree.get('/proc/sys/kernel/random/boot_id').content.__setitem__(slice(0,1),b'1')),
        ('PARENT_IDENTITY_MISMATCH',lambda h,d:setattr(h.tree.get('/mnt/day-d-data'),'ino',99999)),
        ('PARENT_IDENTITY_MISMATCH',lambda h,d:setattr(h.tree.get('/mnt/day-d-data'),'dev',hostemu.ROOT_DEVICE)),
        ('PARENT_IDENTITY_MISMATCH',lambda h,d:setattr(h.tree.get('/mnt'),'mode',0o775)),
        ('PARENT_IDENTITY_MISMATCH',lambda h,d:setattr(h.tree.get('/'),'gid',5)),
        ('EXECUTOR_IDENTITY',lambda h,d:setattr(h,'actor',(0,1000))),
        ('DATA_VOLUME_FREE_SPACE_BELOW_FLOOR',lambda h,d:setattr(h.vfs[hostemu.DATA_DEVICE],'f_bavail',255))]
@pytest.mark.parametrize('index',range(len(BEFORE)))
def test_each_listed_refusal_precedes_the_first_effect_and_even_the_umask_is_the_only_process_change(index):
    code,prepare=BEFORE[index];docs,host=k10.case();prepare(host,docs);before=k10.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,'PRECHECK'),receipt['code']
    assert k10.state_of(host)==before and host.mutating()==[] and not [e for e in host.log if e[0] in ('fsync','mkdir','create','write','link','unlink')]
    assert receipt['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==0 and host.fds=={}

def test_bytes_that_differ_from_the_signed_hash_and_another_epoch_are_refused_before_the_claim_and_before_any_host_call(tmp_path):
    for index,change in enumerate((lambda d:d.plan['release'].update(sha256=sha(b'other')),
                   lambda d:d.plan['release'].update(content_b64=k10.b64(k10.RELEASE[:-1]+b' ')),
                   lambda d:d.plan['release'].update(k10.release_member(k10.altered(epoch='R2D2-V2-SHADOW-2026-09-28'))),
                   lambda d:d.plan['release'].update(k10.release_member(k10.altered(epoch='R2D2-V2-DIAG-2026-10-05',mode='DIAGNOSTIC'))),
                   lambda d:d.plan['release'].update(k10.release_member(k10.altered(first_session='2026-10-06'))),
                   lambda d:d.plan['release'].update(bytes=len(k10.RELEASE)+1))):
        docs,host=k10.case();change(docs);docs.chain()
        receipt=docs.run(f.Untouchable());assert receipt['status']=='REFUSED' and receipt['phase_reached']=='AUTHENTICATION',receipt
        directory=tmp_path/str(index);directory.mkdir();dispatch=f.Dispatch(docs,directory)
        with pytest.raises(ValueError):dispatch.prepare()
        assert not dispatch.claims()

def test_only_the_five_creating_calls_and_five_fsyncs_touch_the_host_and_all_inside_the_signed_paths():
    docs,host=k10.case();receipt=docs.run(host);effects=docs.go['effects']
    changing=[e for e in host.log if e[0] in hostemu.MUTATING or e[0]=='fsync' or e[0]=='umask']
    kinds=[e[0] for e in changing];assert kinds==['umask','mkdir','fsync','fsync','create','write','fsync','link','fsync','unlink','fsync']
    directory=effects['directory']['path'];final=effects['file']['path']
    for e in changing:
        if e[0]=='umask':continue
        assert e[1]==effects['parent']['path'] or e[1]==directory or e[1].startswith(directory+'/')
    link=[e for e in host.log if e[0]=='link'][0];assert link[2]==final
    # no write-capable open anywhere else, nothing opened for writing but the temporary
    assert [e for e in host.log if e[0]=='create']==[('create',directory+'/.hostops-%s-0.partial'%docs.go16(),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)]
