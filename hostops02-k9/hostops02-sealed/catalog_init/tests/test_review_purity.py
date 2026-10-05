"""The hostile cases of the reviewer of 2026-10-02 (lens: purity and authentication), taken into the candidate after
the repair. They are the reviewer's own text (review-purity/work/base/catalog_init/tests/test_review_purity.py, sha256
193671d80b745b8b9951ded4fe09bf0c2695b7acd24a8528ab32f67d5f9efaca) with these changes, each forced by a repair:
  - a rehearsal now reads the image and lists the containers under a directory it created first, so what those reads
    find is a PARTIAL in REHEARSAL and a refusal in REAL only;
  - a REAL run whose configuration directory cannot be counted after its reads is a PARTIAL whose root is untouched
    (it was a refusal), so the invariant "a REAL partial never calls the root untouched" names that one exception;
  - the codes of the layout floor replace REHEARSAL_ROOT_INSIDE_THE_PARENT_OF_THE_REAL_ROOT;
  - the five cases that answer the reviewer's surviving mutants moved to test_review_findings.py (F9, F13), and the
    lines that printed what a sweep saw are gone (the descriptors are asserted in test_review_findings.py, F12)."""
import copy,json,errno
from datetime import timedelta,datetime,timezone
import pytest
import family as f
import hostemu
import k2a

MODES=('REAL','REHEARSAL')
CANARY='REVIEWER-SECRET-CANARY-9f3a'
def fresh(mode):
    docs,host=k2a.case(mode);return docs.k.m,docs,host
def effect_started(host):
    # a mkdir that raised OSError is logged by the emulation but created nothing (the state comparison proves that)
    return [e for e in host.log if e[0] in hostemu.MUTATING and not (e[0]=='mkdir' and host.tree.get(e[1]) is None)] or [c for c in host.commands if c['argv'][1:2]==['run']]
def catalog_ok(host,mode,epoch):
    root=host.tree.get(k2a.root_of(mode))
    return (root is not None and sorted(root.children)==k2a.NAMES and bytes(root.children['epoch.json'].content)==k2a.expected_epoch_json(epoch,root.dev,root.ino)
            and all((c.kind,c.uid,c.gid,c.mode,c.nlink)==('file',0,0,0o600,1) for c in root.children.values()))
def check(mode,m,docs,host,before,receipt,label):
    line=f.line(receipt)
    assert f.sealed(receipt),label
    assert CANARY.encode() not in line and b'never-emit' not in line and b'injected' not in line,label
    status=receipt['status']
    if status=='REFUSED':
        # INVARIANT I: a refusal says nothing changed and no process of the run existed
        assert k2a.state_of(host)==before,(label,'REFUSED but the host changed')
        assert not effect_started(host),(label,'REFUSED but an effect was issued on the host')
        assert receipt.get('root_verdict','UNTOUCHED_NO_CONTAINER_STARTED')=='UNTOUCHED_NO_CONTAINER_STARTED',label
        assert all(entry['docker_config']==k2a.CONFIG for entry in host.commands) and mode=='REAL' or host.commands==[],(label,'a refused rehearsal started a docker command')
    elif status==m.COMPLETE_STATUS:
        # INVARIANT II: complete means verified on the host
        assert catalog_ok(host,mode,docs.plan['epoch']),(label,'COMPLETE without the exact catalog')
        assert sorted(host.tree.get(k2a.CONFIG).children)==[],label
        assert receipt['outcome']==m.success_of(docs.plan) and receipt['root_verdict']=='CATALOG_READY_VERIFIED',label
        assert receipt['mutating_calls']['uncertain']==0,label
    else:
        assert status==m.PARTIAL_STATUS,label
        assert receipt['outcome'] in (m.PARTIAL_OUTCOME,m.ESCAPED_OUTCOME,m.REDUCED_OUTCOME),label
        assert receipt.get('root_verdict')!='CATALOG_READY_VERIFIED',label
        # a REAL partial calls the root untouched in one case only: the directory of the unit is not known to be as it was after the reads
        unit=receipt.get('code') in ('DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS','DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS') and receipt.get('phase_reached')=='PRECHECK'
        assert receipt.get('root_verdict')!='UNTOUCHED_NO_CONTAINER_STARTED' or mode=='REHEARSAL' or receipt['outcome']!=m.PARTIAL_OUTCOME or unit,(label,'REAL partial that calls the root untouched')
        if unit and mode=='REAL':assert k2a.state_of(host)==before and not effect_started(host),(label,'the root or the engine changed')
    if mode=='REHEARSAL':
        assert sorted(host.tree.get(k2a.JOURNAL).children)==[] and sorted(host.tree.get(k2a.CONFIG).children)==[],(label,'a rehearsal wrote into the real root or into the directory of the unit')
        assert all(entry['docker_config']==k2a.REHEARSAL_CONFIG for entry in host.commands),(label,'a docker command of a rehearsal under another directory')
    return status

def baseline(mode):
    m,docs,host=fresh(mode);r=docs.run(host);assert r['status']==m.COMPLETE_STATUS;return host.calls

@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('kind',['oserror','runtime','death','eacces'])
def test_fault_at_every_host_call_keeps_both_invariants(mode,kind):
    total=baseline(mode);seen={}
    for index in range(1,total+1):
        m,docs,host=fresh(mode);before=k2a.state_of(host)
        def hook(host,name,detail,calls,index=index):
            if calls==index:
                if kind=='oserror':raise OSError(errno.EIO,CANARY)
                if kind=='eacces':raise PermissionError(errno.EACCES,CANARY)
                if kind=='runtime':raise RuntimeError(CANARY)
                raise hostemu.Death(CANARY)
        host.hook=hook;receipt=docs.run(host)
        s=check(mode,m,docs,host,before,receipt,(mode,kind,index));seen[s]=seen.get(s,0)+1
    assert 'REFUSED' in seen and m.PARTIAL_STATUS in seen

@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('which',['monotonic','wall','reversed'])
def test_expiry_at_every_clock_reading_keeps_both_invariants(mode,which):
    # count the clock readings of a complete run
    m,docs,host=fresh(mode);n=[0]
    def mono():n[0]+=1;return 0
    assert docs.run(host,monotonic=mono)['status']==m.COMPLETE_STATUS;total=n[0]
    seen={}
    for index in range(1,total+2):
        m,docs,host=fresh(mode);before=k2a.state_of(host);c=[0]
        def mono(index=index):
            c[0]+=1
            if which=='monotonic' and c[0]>=index:return 1000.0
            if which=='reversed' and c[0]==index:return -5.0
            return 0
        def wall(index=index):
            if which=='wall' and c[0]>=index:return docs.now+timedelta(minutes=30)
            return docs.now
        receipt=docs.run(host,monotonic=mono,clock=wall)
        s=check(mode,m,docs,host,before,receipt,(mode,which,index));seen[s]=seen.get(s,0)+1
        assert host.fds=={}
    assert 'REFUSED' in seen

# ---- hostile engine answers that carry text
def answer(host,words,code,out):
    original=host.docker.run
    def run(args,stdin=None,environment=None):
        if args[:len(words)]==words:return code,out
        return original(args,stdin,environment)
    host.docker.run=run
@pytest.mark.parametrize('mode',MODES)
def test_hostile_text_from_the_engine_or_the_container_never_reaches_the_receipt(mode):
    c=CANARY.encode()
    images=[b'{"id":"'+c+b'","repo_tags":[],"revision":null}\n',b'{"id":"sha256:'+b'fb'*32+b'","repo_tags":["'+c+b'"],"revision":"'+c+b'"}\n',
            c+b'\n',b'{"'+c+b'":1}\n',b'{"id":"sha256:'+b'fb'*32+b'","repo_tags":null,"revision":"'+c+b'","extra":"'+c+b'"}\n']
    for out in images:
        m,docs,host=fresh(mode);before=k2a.state_of(host);answer(host,['image','inspect'],0,out);receipt=docs.run(host)
        assert check(mode,m,docs,host,before,receipt,('image',out[:20]))==('REFUSED' if mode=='REAL' else m.PARTIAL_STATUS)
    lists=[b'{"id":"'+b'a'*64+b'","name":"x","state":"'+c+b'"}\n',b'{"id":"'+c+b'","name":"x","state":"running"}\n',c+b'\n',
           b'{"id":"'+b'a'*64+b'","name":"bad name '+c+b'","state":"running"}\n']
    for out in lists:
        m,docs,host=fresh(mode);before=k2a.state_of(host);answer(host,['ps','-a'],0,out);receipt=docs.run(host)
        assert check(mode,m,docs,host,before,receipt,('ps',out[:20]))==('REFUSED' if mode=='REAL' else m.PARTIAL_STATUS)
    runs=[(1,json.dumps({'status':'CATALOG_REFUSED','code':CANARY}).encode()+b'\n'),(1,json.dumps({'status':'CATALOG_REFUSED','code':CANARY,'detail':CANARY}).encode()+b'\n'),
          (0,json.dumps({'status':CANARY}).encode()+b'\n'),(0,c+b'\n'),(2,c*3),(0,json.dumps({'status':'CATALOG_READY','created':True,'epoch':CANARY,'device':CANARY,'inode':CANARY,'entries':[CANARY]}).encode()+b'\n'),
          (0,json.dumps({'status':'CATALOG_READY','created':CANARY,'epoch':CANARY,'device':1,'inode':1,'entries':[CANARY],CANARY:CANARY}).encode()+b'\n'),
          (0,b'{"status":"CATALOG_READY","created":true,"device":'+b'9'*3000+b',"entries":["epoch.json","maintenance.lock"],"epoch":"x","inode":1}\n'),
          (0,b'{"status":"CATALOG_READY","created":true,"device":1e999,"entries":["epoch.json","maintenance.lock"],"epoch":"x","inode":1}\n'),
          (0,b'['*5000+b']'*5000+b'\n')]
    for code,out in runs:
        m,docs,host=fresh(mode);before=k2a.state_of(host);host.docker.on_run=lambda call,code=code,out=out:(code,out);receipt=docs.run(host)
        assert check(mode,m,docs,host,before,receipt,('run',out[:30]))==m.PARTIAL_STATUS
        assert receipt['root_verdict']=='NOT_TO_BE_USED_AGAIN'
    # foreign names in the root and in the configuration directory after the run
    def leaves(call):
        result=k2a.container(call);call.docker.host.tree.add(call.mounts[0]['source']+'/'+CANARY,kind='file',mode=0o600)
        call.docker.host.tree.add(k2a.config_of(mode)+'/'+CANARY,kind='file',mode=0o600,content=c);return result
    m,docs,host=fresh(mode);before=k2a.state_of(host);host.docker.on_run=leaves;receipt=docs.run(host)
    assert check(mode,m,docs,host,before,receipt,'names')==m.PARTIAL_STATUS and receipt['code']=='CATALOG_READBACK_MISMATCH'
    # a secret-looking epoch.json content never leaves (only size and hash)
    def writes(call):
        result=k2a.container(call);call.node(call.command[4]+'/epoch.json').content=bytearray(c*5);return result
    m,docs,host=fresh(mode);before=k2a.state_of(host);host.docker.on_run=writes;receipt=docs.run(host)
    assert check(mode,m,docs,host,before,receipt,'content')==m.PARTIAL_STATUS

# ---- authentication: nothing foreign, nothing of the other mode
def clone(docs):
    d=f.Docs(docs.k,copy.deepcopy({key:docs.plan[key] for key in docs.k.m.PLAN_KEYS}),now=docs.now);return d
def raw_pins(m,raw,source):return m.Pins(payload=f.sha(source),request=f.sha(raw[0]),authority=f.sha(raw[1]),go=f.sha(raw[2]))
def auth(docs,raw=None):
    m=docs.k.m;raw=raw or docs.raw()
    return f.refusal(lambda:m.authenticate(*raw,pins=raw_pins(m,raw,docs.k.source),payload_bytes=docs.k.source,clock=lambda:docs.now,monotonic=lambda:0,executor_uid=lambda:0))
def test_documents_of_the_other_mode_never_authorise_this_one():
    m,real,_=fresh('REAL');m,reh,_=fresh('REHEARSAL')
    rr,ra,rg=real.raw();hr,ha,hg=reh.raw()
    for raw in ([rr,ha,hg],[hr,ra,rg],[rr,ra,hg],[rr,ha,rg],[hr,ha,rg],[hr,ra,hg]):
        assert auth(real,raw) in ('AUTHORITY_UNBOUND','GO_UNBOUND'),raw
    # the rehearsal's signed effects and criterion under a REAL request, hash chain kept
    d=clone(real);d.authority['effects']=copy.deepcopy(reh.authority['effects']);d.go['effects']=copy.deepcopy(reh.go['effects']);d.chain(effects=False);assert auth(d)=='EFFECTS_BINDING'
    d=clone(real);d.go['success_criterion']=reh.go['success_criterion'];d.chain(criterion=False);assert auth(d)=='GO_CRITERION'
    # a REAL request built from a rehearsal's plan by changing the mode only, and the reverse
    d=clone(reh);d.plan['mode']='REAL';d.chain();assert auth(d)=='MODE_MEMBERS_INVALID'
    d=clone(reh);d.plan.update(mode='REAL',throwaway_name=None,reference_chain=None);d.chain();assert auth(d) in ('JOURNAL_ROOT_NOT_PRIVATE','EPOCH_NOT_THE_COMPILED_CONSTANT')
    d=clone(reh);d.plan.update(mode='REAL',throwaway_name=None,journal_chain=d.plan['reference_chain'],reference_chain=None);d.chain();assert auth(d)=='EPOCH_NOT_THE_COMPILED_CONSTANT'
    d=clone(real);d.plan['mode']='REHEARSAL';d.chain();assert auth(d)=='THROWAWAY_PARENT_NOT_THE_FIXED_ONE'
    d=clone(real);d.plan.update(mode='REHEARSAL',throwaway_name=k2a.THROWAWAY,reference_chain=d.plan['journal_chain'],epoch=k2a.DIAG);d.chain()
    assert auth(d)=='THROWAWAY_PARENT_NOT_THE_FIXED_ONE','a rehearsal may not create its throwaway inside the real root'

FOREIGN=[('request','schema','WRITE_SUPERVISOR_READER_PROVISION_REQUEST_V1'),('request','schema','WRITE_HOSTOPS02_ACTIVATE_REQUEST_V1'),('request','schema','READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1'),
         ('request','operation','GO_WRITE_SUPERVISOR_READER_PROVISION_01'),('request','operation','GO_READONLY_HOSTOPS_PRECHECK_01'),('request','operation','GO_WRITE_HOSTOPS02_INSTALL_RELEASE_01'),
         ('request','operation','GO_WRITE_HOSTOPS02_CATALOG_INIT_02'),('request','phase','WRITE_PROVISION'),('request','scope_sha256','4'*64),('request','payload_sha256','5'*64),
         ('request','writes_allowed',False),('request','activation_allowed',True),('request','executor_uid',1000),('request','executor_uid',False),('request','status','UNBOUND'),('request','max_seconds',61),
         ('authority','schema','WRITE_SUPERVISOR_READER_PROVISION_AUTHORITY_V1'),('authority','operation','GO_WRITE_HOSTOPS02_ACTIVATE_01'),('authority','phase','WRITE_X'),('authority','payload_sha256','5'*64),
         ('authority','writes_allowed',False),('authority','activation_allowed',True),('authority','decision','REJECTED'),('authority','execution_authorized',1),('authority','status','UNBOUND'),
         ('go','schema','WRITE_SUPERVISOR_READER_PROVISION_GO_V1'),('go','operation','GO_WRITE_HOSTOPS02_ACTIVATE_01'),('go','phase','WRITE_X'),('go','payload_sha256','5'*64),('go','action','NO_GO'),
         ('go','writes_allowed',False),('go','activation_allowed',True),('go','execution_authorized',1),('go','status','UNBOUND'),('go','scope_statement','another statement'),('go','owner','SOMEONE_ELSE'),
         ('go','host_binding_sha256','7'*64),('authority','host_binding_sha256','7'*64),('request','host_binding_sha256','7'*64),('request','date','2026-10-05'),('request','date','2026-10-01')]
@pytest.mark.parametrize('mode',MODES)
def test_each_foreign_member_alone_is_refused_before_anything_is_touched(mode):
    for document,key,value in FOREIGN:
        m,docs,host=fresh(mode);getattr(docs,document)[key]=value;docs.chain(effects=False,criterion=False)
        code=auth(docs);assert code and code!='',(document,key)
        receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['phase_reached'])==('REFUSED','AUTHENTICATION'),(document,key,value)
    for key,value in (('schema','HOSTOPS02_ACTIVATE_PLAN_V1'),('phase','WRITE_X'),('status','UNBOUND'),('host_binding_sha256','7'*64),('max_seconds',59)):
        m,docs,host=fresh(mode);docs.plan[key]=value;docs.chain();receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['phase_reached'])==('REFUSED','AUTHENTICATION'),key
    m,docs,host=fresh(mode);docs.plan['scope']['core_sha256']='8'*64;docs.chain();assert auth(docs)=='SCOPE_MISMATCH'
    m,docs,host=fresh(mode);docs.plan['scope']['dates'].append('2026-10-05');docs.chain();assert auth(docs)=='SCOPE_MISMATCH'
    m,docs,host=fresh(mode);docs.go['transport_binding']['runtime_sha256']={'activate.py':f.sha(docs.k.source)};docs.chain();assert auth(docs)=='GO_TRANSPORT_UNBOUND'
    m,docs,host=fresh(mode);docs.go['transport_binding']['remote_command']='sudo -n /usr/bin/python3 -';docs.chain();assert auth(docs)=='GO_TRANSPORT_UNBOUND'

@pytest.mark.parametrize('mode',MODES)
def test_dates_and_windows(mode):
    m,docs,host=fresh(mode)
    for day in m.DATES:
        start=datetime.fromisoformat(day+'T12:00:00+00:00');d=clone(docs);d.now=start;d.shift(start,start+timedelta(minutes=5));assert d.authenticate()
    assert tuple(m.DATES)==('2026-10-02','2026-10-03','2026-10-04')
    for day in ('2026-10-01','2026-10-05','2026-10-06','2026-10-10'):
        start=datetime.fromisoformat(day+'T12:00:00+00:00');d=clone(docs);d.now=start;d.shift(start,start+timedelta(minutes=5));assert auth(d)=='DATE_NOT_IN_SCOPE'
    # a window that crosses into Monday UTC
    start=datetime.fromisoformat('2026-10-04T23:58:00+00:00');d=clone(docs);d.now=start;d.shift(start,start+timedelta(minutes=5));assert auth(d)=='DATE_WINDOW_MISMATCH'
    # the documents of Saturday presented on Sunday
    start=datetime.fromisoformat('2026-10-03T12:00:00+00:00');d=clone(docs);d.shift(start,start+timedelta(minutes=5));d.now=start+timedelta(days=1);assert auth(d)=='OUTSIDE_GO_WINDOW'
    d.now=start+timedelta(minutes=5);assert auth(d)=='OUTSIDE_GO_WINDOW'
    d.now=start-timedelta(seconds=1);assert auth(d)=='OUTSIDE_GO_WINDOW'
    # too long a window
    d=clone(docs);d.shift(docs.now,docs.now+timedelta(seconds=901));assert auth(d)=='WINDOW_SPAN'

@pytest.mark.parametrize('mode',MODES)
def test_another_host_is_refused_before_any_docker_command(mode):
    m,docs,host=fresh(mode);host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'aaaaaaaa-d9cb-469f-a165-70867728950e\n');before=k2a.state_of(host)
    receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','EVIDENCE_FROM_EARLIER_BOOT') and host.commands==[] and k2a.state_of(host)==before
    m,docs,host=fresh(mode);receipt=docs.run(host,executor_uid=lambda:1000);assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','REQUEST_OR_EXECUTOR_UNBOUND','AUTHENTICATION') and host.log==[]
