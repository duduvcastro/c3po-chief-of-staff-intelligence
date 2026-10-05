"""Shared fixtures of the HOSTOPS01 tests: module loading per operation directory, synthetic bound documents, and
request plans built from the emulated host exactly as a binder would copy them from a read-only receipt.
Nothing here is authoritative: owners, references and bindings are synthetic strings."""
import base64
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import hostemu

ROOT=Path(__file__).resolve().parent.parent
MODULES={'provision':'provision_dirs','install_units':'install_units','readback':'readback_readonly','precheck':'precheck_readonly'}
OPS=tuple(MODULES)
WRITE_OPS=('provision','install_units')
NOW=datetime(2026,10,3,17,tzinfo=timezone.utc)
HOST='1'*64
TRANSPORT_PIN='5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'
LEAF='r2d2-v2-massive-epoch03'
TAG='massive-supervisor-epoch03'
CAPACITY={'root_path':hostemu.DATA+'/c3po-capacity','receipt_directory_path':'/var/lib/c3po-reader/capacity-receipts'}
VALUES={'IMAGE_ID':hostemu.BACKEND,'HOST_JOURNAL_ROOT':hostemu.DATA+'/'+LEAF,'CONTAINER_JOURNAL_ROOT':'/app/day-d-data/'+LEAF,
        'HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor','HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'}
# The two journal placements of the supervisor README. VALUES above is placement B (a leaf of the data volume);
# placement A, the one signed for epoch R2D2-V2-SHADOW-2026-10-05, puts the journal root next to the state root.
# The write-operation fixtures default to B: its journal row hangs from the data volume chain, the one parent that
# is not root's. Placement A has its own tests in each file. The readback fixtures default to A.
A_LEAF='journal'
VALUES_A=dict(VALUES,HOST_JOURNAL_ROOT='/var/lib/c3po-bar/'+A_LEAF,CONTAINER_JOURNAL_ROOT='/c3po-bar-journal')
DEPLOY_TREE='/opt/chief-of-staff-digital'
def values_of(placement):return dict(VALUES_A if placement=='A' else VALUES)
def tree_of(placement):return DEPLOY_TREE if placement=='A' else None
README_SAMPLE={'IMAGE_ID':'sha256:'+'a'*64,'HOST_JOURNAL_ROOT':'/mnt/day-d-data/r2d2-v2-massive-epoch03',
               'CONTAINER_JOURNAL_ROOT':'/app/day-d-data/r2d2-v2-massive-epoch03','HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor',
               'HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'}
BOOT_SHA=hashlib.sha256(hostemu.BOOT.strip()).hexdigest()
SERVICE=(ROOT/'templates'/'c3po-massive.service').read_bytes()
TIMER=(ROOT/'templates'/'c3po-massive.timer').read_bytes()

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

_LOADED={}
def load(op):
    """The four runtime modules of one operation directory, under private names. The dispatcher imports its
    siblings by their plain names, so they are resolved with that directory first on the path and then detached."""
    if op in _LOADED:return _LOADED[op]
    directory=ROOT/op;plain=('launcher_stdin','transport_once','dispatch_once',MODULES[op])
    saved={name:sys.modules.pop(name,None) for name in plain};sys.path.insert(0,str(directory))
    try:
        spec=importlib.util.spec_from_file_location('dispatch_once',directory/'dispatch_once.py')
        d=importlib.util.module_from_spec(spec);sys.modules['dispatch_once']=d;spec.loader.exec_module(d)
        k=types.SimpleNamespace(op=op,dir=directory,d=d,m=sys.modules[MODULES[op]],l=sys.modules['launcher_stdin'],t=sys.modules['transport_once'],
                                source=(directory/(MODULES[op]+'.py')).read_bytes(),name=MODULES[op]+'.py')
    finally:
        sys.path.remove(str(directory))
        for name in plain:
            module=sys.modules.pop(name,None)
            if module is not None:sys.modules['%s__%s'%(name,op)]=module
            if saved[name] is not None:sys.modules[name]=saved[name]
    _LOADED[op]=k;return k

def world(k):
    host=hostemu.world();host.refused=k.m.Refused;return host

def reference_render(values,template=SERVICE):
    """The repository's reference loop (test_r2d2_v2_massive_supervisor.py): independent of the candidate's renderer."""
    unit=template.decode('ascii')
    for name,value in values.items():unit=unit.replace('@'+name+'@',value)
    assert '@' not in unit;return unit.encode('ascii')


class Docs:
    """One synthetic request/authority/GO set for an operation. Mutate the dicts, then chain() to keep the hash chain
    (so the check under test is the one that decides), or leave the chain broken on purpose."""
    def __init__(self,k,fields,*,now=NOW,minutes=5,evidence=None):
        m=k.m;self.k=k;self.now=now
        self.window={'not_before':now.isoformat(),'not_after':(now+timedelta(minutes=minutes)).isoformat()}
        self.plan=dict(fields,schema=m.PLAN_SCHEMA,status='BOUND',phase=m.PHASE,scope=json.loads(canonical(m.SCOPE)),
                       window={'not_before':self.window['not_before'],'expires_at':self.window['not_after']},
                       host_binding_sha256=HOST,max_seconds=60)
        if evidence is None:
            evidence=[{'role':'PRECHECK','operation':'GO_READONLY_HOSTOPS_PRECHECK_01','receipt_sha256':'a'*64}] if m.EVIDENCE_REQUIRED else []
        self.request=dict(schema=m.REQUEST_SCHEMA,status='BOUND',operation=m.OPERATION,phase=m.PHASE,date=now.date().isoformat(),
                          host_binding_sha256=HOST,payload_sha256=sha(k.source),scope_sha256=m.SCOPE_SHA256,executor_uid=0,max_seconds=60,
                          writes_allowed=m.WRITES_ALLOWED,activation_allowed=False,evidence=evidence,plan=self.plan,**self.window)
        self.authority=dict(schema=m.AUTHORITY_SCHEMA,status='SIGNED',operation=m.OPERATION,phase=m.PHASE,owner='SYNTHETIC_NEVER_AUTHORITATIVE',
                            decision='APPROVED',execution_authorized=True,request_sha256=None,payload_sha256=sha(k.source),effects=None,
                            host_binding_sha256=HOST,writes_allowed=m.WRITES_ALLOWED,activation_allowed=False,
                            owner_evidence='SYNTHETIC_TEST_ONLY',**self.window)
        self.go=dict(schema=m.GO_SCHEMA,status='SIGNED',operation=m.OPERATION,phase=m.PHASE,owner='SYNTHETIC_NEVER_AUTHORITATIVE',action='GO',
                     execution_authorized=True,request_sha256=None,authority_sha256=None,payload_sha256=sha(k.source),effects=None,
                     host_binding_sha256=HOST,writes_allowed=m.WRITES_ALLOWED,activation_allowed=False,
                     claim_root_identity={'path':'/synthetic/claim-root','device':1,'inode':2},
                     transport_binding={'target':'fixture@unused.invalid','remote_command':'sudo -n /usr/bin/python3 -I -B -',
                                        'command_sha256':'2'*64,'runtime_sha256':{k.name:sha(k.source)}},
                     scope_statement=m.SCOPE_STATEMENT,success_criterion=None,**self.window)
        self.chain()
    def chain(self,effects=True,criterion=True):
        m=self.k.m
        if effects:
            try:computed=json.loads(canonical(m.effects_of(self.plan)))
            except Exception:computed={}
            self.authority['effects']=computed;self.go['effects']=json.loads(canonical(computed))
        if criterion:
            try:self.go['success_criterion']=m.success_of(self.plan)
            except Exception:self.go['success_criterion']=m.COMPLETE_OUTCOME
        self.authority['request_sha256']=sha(canonical(self.request))
        self.go['request_sha256']=self.authority['request_sha256'];self.go['authority_sha256']=sha(canonical(self.authority))
        return self
    def shift(self,start,end):
        for document in (self.request,self.authority,self.go):document.update(not_before=start.isoformat(),not_after=end.isoformat())
        self.plan['window']={'not_before':start.isoformat(),'expires_at':end.isoformat()};self.request['date']=start.date().isoformat()
        return self.chain()
    def raw(self):return [canonical(self.request),canonical(self.authority),canonical(self.go)]
    def pins(self):
        raw=self.raw();return self.k.m.Pins(payload=sha(self.k.source),request=sha(raw[0]),authority=sha(raw[1]),go=sha(raw[2]))
    def options(self,extra):
        options=dict(clock=lambda:self.now,monotonic=lambda:0,executor_uid=lambda:0);options.update(extra);return options
    def authenticate(self,**extra):
        return self.k.m.authenticate(*self.raw(),pins=self.pins(),payload_bytes=self.k.source,**self.options(extra))
    def run(self,host,**extra):
        return self.k.m.run(*self.raw(),pins=self.pins(),payload_bytes=self.k.source,host=host,**self.options(extra))
    def perform(self,host,gate=None,state=None):
        """The inner step, as run() calls it after authentication; lets a test inject its own gate or catch a death."""
        m=self.k.m;plan,real=self.authenticate()
        bound=m.digests(*self.raw(),self.k.source);bound['host_binding_sha256']=plan['host_binding_sha256']
        return m.perform(plan,gate or real,host,bound,lambda:self.now,lambda:0,state or m.Effects())

def line(receipt):
    """Exactly what the stdin launcher writes."""
    return json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
def sealed(receipt):
    body=dict(receipt);pin=body.pop('metadata_sha256');return sha(canonical(body))==pin


# ---------------------------------------------------------------- request plans, built as a binder would build them
def provision_fields(k,host,*,groups=None,leaf=None,capacity=CAPACITY,tag=TAG,image=hostemu.BACKEND,existing=(),placement='B'):
    m=k.m;groups=list(m.GROUPS) if groups is None else list(groups)
    placement=placement if 'JOURNAL_LEAF' in groups else None
    volume=hostemu.DATA if (placement=='B' or 'CAPACITY' in groups) else None
    leaf=(leaf or (A_LEAF if placement=='A' else LEAF)) if 'JOURNAL_LEAF' in groups else None;capacity=dict(capacity) if 'CAPACITY' in groups else None
    table=m.layout(groups,volume,leaf,capacity,placement)
    chains={name:hostemu.rows(host,path) for name,path in m.chain_paths(table,volume,capacity).items()}
    return {'groups':groups,'journal_placement':placement,'data_volume_path':volume,'journal_leaf':leaf,'existing_journal_leaves':list(existing),'capacity':capacity,
            'chains':chains,'creates':[dict(row,expect='ABSENT') for row in table],
            'retention_tag':{'repository':'c3po/backend','tag':tag,'image_id':image,'expect':'ABSENT'} if 'RETENTION_TAG' in groups else None,
            'evidence_boot_id_sha256':BOOT_SHA}

def unit(key,name,profile,template,placeholders,rendered):
    return {'key':key,'destination_name':name,'mode':420,'profile':profile,'template_b64':base64.b64encode(template).decode('ascii'),
            'template_sha256':sha(template),'placeholders':placeholders,'rendered_sha256':sha(rendered),'rendered_bytes':len(rendered),
            'expect':'ABSENT'}
def supervisor_units(values=None):
    values=dict(VALUES if values is None else values)
    return [unit('SUPERVISOR_SERVICE','c3po-massive.service','MASSIVE_SUPERVISOR_SERVICE_V1',SERVICE,values,reference_render(values)),
            unit('SUPERVISOR_TIMER','c3po-massive.timer','MASSIVE_SUPERVISOR_TIMER_V1',TIMER,{},TIMER)]
def install_fields(k,host,*,units=None,allowlist=('bridge',),volume=hostemu.DATA,placement='B'):
    """placement applies to the supervisor pair; a list of other units (units given) signs neither it nor a deploy tree."""
    placement=placement if units is None else None
    return {'unit_directory':hostemu.rows(host,'/etc/systemd/system'),'units':supervisor_units(values_of(placement)) if units is None else units,
            'network_allowlist':list(allowlist),'journal_placement':placement,'data_volume_path':volume,'deploy_tree_path':tree_of(placement),
            'template_revision':'d7600b4d14f8a67694ffb37cde06b622f9a3bac3',
            'acknowledged_leftovers':[],'daemon_reload_owner':'OPERATION_5_ACTIVATION_GO','evidence_boot_id_sha256':BOOT_SHA}

def precheck_fields(k,host,*,groups=('SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY'),leaf=None,capacity=CAPACITY,placement='B',existing=()):
    groups=list(groups);placement=placement if 'JOURNAL_LEAF' in groups else None
    volume=hostemu.DATA if (placement=='B' or 'CAPACITY' in groups) else None;leaf=leaf or (A_LEAF if placement=='A' else LEAF)
    return {'groups':groups,'journal_placement':placement,'data_volume_path':volume,'journal_leaf':leaf if 'JOURNAL_LEAF' in groups else None,
            'existing_journal_leaves':list(existing),'capacity':dict(capacity) if 'CAPACITY' in groups else None,
            'unit_names':['c3po-massive.service','c3po-massive.timer'],'image_reference':'c3po/backend:production'}

def provisioned(host,placement='B'):
    """Run the real OP_PROVISION against the emulated host and return its receipt (state for the later operations)."""
    k=load('provision');host.refused=k.m.Refused
    receipt=Docs(k,provision_fields(k,host,placement=placement)).run(host);assert receipt['outcome']=='PROVISIONED_ALL_VERIFIED_DURABLE',receipt
    return receipt
def installed(host,placement='B'):
    k=load('install_units');host.refused=k.m.Refused
    receipt=Docs(k,install_fields(k,host,placement=placement)).run(host);assert receipt['outcome']=='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED',receipt
    return receipt

# Space freed on the data volume under another authorisation: what a gate readback under placement B would need. On the
# data volume as the HOSTFACTS_01 receipt read it, no floor of the README formula is met; on the root filesystem
# (placement A) the five-session floor is met with nothing freed (see the readback tests).
FREED_BYTES=4*1024**3
def floor_bytes(sessions,allowance=0):
    """README "Activation gate" item 4, written out here independently of the candidate's constants."""
    return 53687091200+603979776*sessions+allowance

def ready_host(k=None,*,token=True,catalog=True,loaded=True,placement='A',freed=0):
    """A host after operations 2, 4b, the token delivery and 3: what the readback is meant to find. Free space is what
    the HOSTFACTS_01 receipt read, unless freed says how much was freed on the data volume."""
    host=hostemu.world();provision=provisioned(host,placement);install=installed(host,placement)
    if freed:hostemu.free_space(host,freed)
    if token:host.tree.add('/etc/c3po-bar/token',kind='file',mode=0o600,content=b'never-emit-token-canary-0123456789\n')
    journal=values_of(placement)['HOST_JOURNAL_ROOT']
    if catalog:
        for name in ('epoch.json','maintenance.lock'):
            host.tree.add(journal+'/'+name,kind='file',mode=0o600,dev=host.tree.get(journal).dev,content=b'{}' if name.endswith('json') else b'')
    host.is_enabled['c3po-massive.timer']='disabled'
    if loaded:
        base={'LoadState':'loaded','ActiveState':'inactive','SubState':'dead'}
        host.units['c3po-massive.service']=dict(base,Id='c3po-massive.service',UnitFileState='static',
                                                FragmentPath='/etc/systemd/system/c3po-massive.service',TriggeredBy='c3po-massive.timer')
        host.units['c3po-massive.timer']=dict(base,Id='c3po-massive.timer',UnitFileState='disabled',
                                              FragmentPath='/etc/systemd/system/c3po-massive.timer')
    if k is not None:host.refused=k.m.Refused
    host.log.clear();host.commands.clear();host.calls=0
    return host,provision,install

def readback_fields(k,host,provision,install,*,mode='GATE',catalog='INITIALISED',sessions=5,allowance=0,revision=hostemu.REVISION):
    """The placement is the one the two receipts were made under."""
    placement=install['effects']['journal_placement'];VALUES=values_of(placement)
    ledger={row['key']:row for row in provision['ledger']};units={row['key']:row for row in install['ledger']}
    journal=host.tree.get(VALUES['HOST_JOURNAL_ROOT'])
    def unit_file(key,template,rendered):
        return {'template_b64':base64.b64encode(template).decode('ascii'),'rendered_sha256':sha(rendered),'rendered_bytes':len(rendered),
                'device':units[key]['device'],'inode':units[key]['inode']}
    return {'mode':mode,'install':{'receipt_sha256':install['metadata_sha256'],'outcome':install['outcome']},
            'provision':{'receipt_sha256':provision['metadata_sha256']},'evidence_boot_id_sha256':BOOT_SHA,
            'unit_directory':hostemu.rows(host,'/etc/systemd/system'),
            'service':unit_file('SUPERVISOR_SERVICE',SERVICE,reference_render(VALUES)),'timer':unit_file('SUPERVISOR_TIMER',TIMER,TIMER),
            'substitutions':dict(VALUES),'network_allowlist':['bridge'],'journal_placement':placement,'deploy_tree_path':tree_of(placement),
            'journal_mount_point':provision['effects']['journal']['mount_point_by_device_change'],      # "/" under A, the data volume root under B
            'data_volume':{'path':hostemu.DATA,'rows':hostemu.rows(host,hostemu.DATA) if placement=='B' else None},
            'layout':{key:{'device':ledger[key]['observed']['device'],'inode':ledger[key]['observed']['inode']} for key in k.m.LAYOUT_KEYS},
            'retention_reference':'c3po/backend:'+TAG,'image_revision':revision,
            'free_space_floor_bytes':floor_bytes(sessions,allowance),'sessions_retained':sessions,'other_writers_allowance_bytes':allowance,
            'catalog':{'expected':catalog,'receipt_sha256':'c'*64 if catalog=='INITIALISED' else None,
                       'device':journal.dev if catalog=='INITIALISED' else None,'inode':journal.ino if catalog=='INITIALISED' else None}}


# ---------------------------------------------------------------- dispatcher level: private files and a pinned config
class Dispatch:
    """Synthetic local files for one dispatch: the five blobs, a config that pins them, and the prepare/resume calls.
    The key and known-hosts files are plain synthetic strings in a private test directory, not keys."""
    def __init__(self,docs,tmp_path):
        self.docs,self.k=docs,docs.k;self.root=Path(str(tmp_path)).resolve();self.root.chmod(0o700)
        k=self.k;m=k.m;now=docs.now
        self.config={'schema':None,'status':'BOUND','decision':'GO','operation':m.OPERATION,'single_use':True,'retry':False,
                     'owner':docs.go['owner'],'authorization_ref':'SYNTHETIC_TEST_ONLY','executor_uid':0,
                     'not_before':docs.window['not_before'],'not_after':docs.window['not_after'],
                     'latest_start':(now+timedelta(seconds=220)).isoformat(),'watchdog_seconds':80,
                     'finalize_local_receipts_after_window':True,'host_binding_sha256':HOST,'target':'fixture@unused.invalid',
                     'remote_command':'sudo -n /usr/bin/python3 -I -B -','attempt_directory':str(self.root/'attempt'),
                     'local_root_identity':{'path':str(self.root),'device':self.root.stat().st_dev,'inode':self.root.stat().st_ino}}
        self.config['schema']=json.loads((k.dir/'DISPATCH.UNBOUND.json').read_bytes())['schema']
        self.config['ssh_key']=self.put('synthetic-key',b'NOT_A_KEY_SYNTHETIC')
        self.config['known_hosts']=self.put('synthetic-hosts',b'NOT_HOSTS_SYNTHETIC')
        self.config['command_sha256']=k.t.command_pin(k.d.command(self.config))
        self.config['runtime_sha256']={name:sha((k.dir/name).read_bytes()) for name in ('dispatch_once.py','transport_once.py','launcher_stdin.py',k.name)}
        self.save()
    def put(self,name,raw):
        path=self.root/name;path.write_bytes(raw);path.chmod(0o600);return {'path':str(path),'sha256':sha(raw)}
    def save(self,rebind=True):
        k,docs=self.k,self.docs
        if rebind:
            docs.go.update(claim_root_identity=self.config['local_root_identity'],
                           transport_binding={key:self.config[key] for key in ('target','remote_command','command_sha256','runtime_sha256')})
            docs.chain()
        raw=docs.raw()
        payload=k.l.build(k.source,*raw,expected_payload_sha256=sha(k.source),expected_request_sha256=sha(raw[0]),
                          expected_authority_sha256=sha(raw[1]),expected_go_sha256=sha(raw[2]))
        for key,blob in [('source',k.source),('request',raw[0]),('authority',raw[1]),('go',raw[2]),('payload',payload)]:
            self.config[key]=self.put(key,blob)
        self.payload=payload;self.pin=self.put('config',canonical(self.config));return self
    def prepare(self,transport=None,**extra):
        options=dict(clock=lambda:self.docs.now,monotonic=lambda:0);options.update(extra)
        return self.k.d.execute(self.pin['path'],self.pin['sha256'],phase='prepare',transport=transport or never,**options)
    def proof(self,intent):
        return self.put('publication',canonical({'schema':self.config['schema'].replace('DISPATCH_AUTHORIZATION','INTENT_PUBLICATION'),
            'status':'PUBLISHED','owner':self.config['owner'],'publication_ref':'SYNTHETIC_TEST_ONLY','go_sha256':self.config['go']['sha256'],
            'config_sha256':self.pin['sha256'],'intent_sha256':intent['intent_sha256'],'published_at':self.docs.now.isoformat()}))
    def resume(self,publication,transport,**extra):
        options=dict(clock=lambda:self.docs.now,monotonic=lambda:0);options.update(extra)
        return self.k.d.execute(self.pin['path'],self.pin['sha256'],phase='resume',publication_path=publication['path'],
                                publication_sha256=publication['sha256'],transport=transport,**options)
    def claims(self):return list(self.root.glob('.go-*.claim'))
    def fake(self,out=None,status='KNOWN_PARTIAL'):
        config,m=self.config,self.k.m
        def run(payload,**kwargs):
            assert kwargs['authorize'](kwargs['payload_sha256'],kwargs['command_sha256']) is True
            receipt=canonical({'schema':m.RECEIPT_SCHEMA,'request_sha256':config['request']['sha256'],'go_sha256':config['go']['sha256'],
                               'payload_sha256':config['source']['sha256']}) if out is None else out
            return {'status':status,'retry_allowed':False},receipt,b''
        return run

def never(*args,**kwargs):raise AssertionError('transport must not run')

def default_fields(k,host):
    """A valid plan for any operation on a fresh emulated host (for the authority tests, which do not care which)."""
    if k.op=='provision':return provision_fields(k,host)
    if k.op=='install_units':return install_fields(k,host)
    if k.op=='precheck':return precheck_fields(k,host)
    raise AssertionError('readback needs a prepared host: use ready_host and readback_fields')
def default_docs(op,placement=None,**options):
    k=load(op)
    if op=='readback':
        host,provision,install=ready_host(k,placement=placement or 'A',freed=FREED_BYTES if placement=='B' else 0)
        return Docs(k,readback_fields(k,host,provision,install),**options),host
    host=world(k);return Docs(k,default_fields(k,host),**options),host
