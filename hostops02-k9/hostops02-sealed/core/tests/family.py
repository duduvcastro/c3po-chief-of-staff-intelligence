"""Shared fixtures of the HOSTOPS02 tests, for the core's own demonstration operations and for every operation built
on the core: loading of one operation's build directory, synthetic bound documents, the dispatcher-level files.
Nothing here is authoritative: owners, references and bindings are synthetic strings.

An operation's tests put this directory on sys.path and use:
  k=family.load(<operation directory>)            the four runtime modules of <operation directory>/build
  host=family.world(k)                            hostemu.world() wired to the source's exception classes
  docs=family.Docs(k,fields)                      one request/authority/GO set over the operation's own plan fields
  docs.run(host) / docs.authenticate() / docs.perform(host,gate=...,state=...)
  family.Dispatch(docs,tmp_path)                  the local files of one dispatch (prepare, proof, resume)
"""
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

import hostemu

CORE=Path(__file__).resolve().parent.parent
HOST='1'*64
TRANSPORT_PIN='5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'
LAUNCHER_PIN='ac4085e49dd1a7fcc0e64e3eaa5cd75b1a5f7f961f587e9eaf76c17d96f73caa'      # the launcher of HOSTOPS01, byte for byte
BOOT_SHA=hashlib.sha256(hostemu.BOOT.strip()).hexdigest()

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def assembler():
    """The core's assemble.py as a module (it is not on sys.path)."""
    name='_hostops02_core_assemble'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,CORE/'assemble.py');module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module;spec.loader.exec_module(module)
    return sys.modules[name]

_LOADED={}
def load(directory):
    """The four runtime modules of one operation's build directory, under private names. The dispatcher imports its
    siblings by their plain names, so they are resolved with that directory first on the path and then detached."""
    directory=Path(directory).resolve();build=directory/'build';key=str(build)
    if key in _LOADED:return _LOADED[key]
    report=json.loads((build/'ASSEMBLY.json').read_bytes());module=report['module'];tag=sha(key.encode())[:10]
    plain=('launcher_stdin','transport_once','dispatch_once',module)
    saved={name:sys.modules.pop(name,None) for name in plain};sys.path.insert(0,str(build))
    try:
        spec=importlib.util.spec_from_file_location('dispatch_once',build/'dispatch_once.py')
        d=importlib.util.module_from_spec(spec);sys.modules['dispatch_once']=d;spec.loader.exec_module(d)
        k=types.SimpleNamespace(op=report['name'],directory=directory,dir=build,d=d,m=sys.modules[module],l=sys.modules['launcher_stdin'],
                                t=sys.modules['transport_once'],source=(build/(module+'.py')).read_bytes(),name=module+'.py',report=report)
    finally:
        sys.path.remove(str(build))
        for name in plain:
            loaded=sys.modules.pop(name,None)
            if loaded is not None:sys.modules['%s__%s'%(name,tag)]=loaded
            if saved[name] is not None:sys.modules[name]=saved[name]
    _LOADED[key]=k;return k

def wire(k,host):
    """Give an emulated host the source's own exception classes (what its Native would raise)."""
    host.refused=k.m.Refused;host.not_started=getattr(k.m,'NotStarted',k.m.Refused);return host
def world(k,**options):return wire(k,hostemu.world(**options))

def moment(k,hour=17):
    """An instant on the first day of the operation's date set."""
    return datetime.fromisoformat(k.m.DATES[0]+'T%02d:00:00+00:00'%hour)

class Untouchable:
    """A host that fails on any use: what a refusal before any observation must never reach."""
    def __getattr__(self,name):raise AssertionError('host touched: '+name)

def refusal(action):
    """The constant code of the Refused that action() raises."""
    with pytest.raises(ValueError) as caught:action()
    assert type(caught.value).__name__ in ('Refused','NotStarted','CommandFailed'),repr(caught.value)
    return str(caught.value)


class Docs:
    """One synthetic request/authority/GO set for an operation. Mutate the dicts, then chain() to keep the hash chain
    (so the check under test is the one that decides), or leave the chain broken on purpose."""
    def __init__(self,k,fields,*,now=None,minutes=5,evidence=None):
        m=k.m;self.k=k;self.now=now=moment(k) if now is None else now
        self.window={'not_before':now.isoformat(),'not_after':(now+timedelta(minutes=minutes)).isoformat()}
        self.plan=dict(fields,schema=m.PLAN_SCHEMA,status='BOUND',phase=m.PHASE,scope=json.loads(canonical(m.SCOPE)),
                       window={'not_before':self.window['not_before'],'expires_at':self.window['not_after']},
                       host_binding_sha256=HOST,max_seconds=60)
        if evidence is None:
            evidence=[{'role':'EVIDENCE_%d'%index,'operation':name,'receipt_sha256':'a'*64} for index,name in enumerate(m.EVIDENCE_OPERATIONS)]
            if m.EVIDENCE_REQUIRED and not evidence:evidence=[{'role':'PRIOR','operation':'GO_READONLY_SYNTHETIC_PRIOR_01','receipt_sha256':'a'*64}]
        self.request=dict(schema=m.REQUEST_SCHEMA,status='BOUND',operation=m.OPERATION,phase=m.PHASE,date=now.date().isoformat(),
                          host_binding_sha256=HOST,payload_sha256=sha(k.source),scope_sha256=m.SCOPE_SHA256,executor_uid=0,max_seconds=60,
                          writes_allowed=m.WRITES_ALLOWED,activation_allowed=m.ACTIVATION_ALLOWED,evidence=evidence,plan=self.plan,**self.window)
        self.authority=dict(schema=m.AUTHORITY_SCHEMA,status='SIGNED',operation=m.OPERATION,phase=m.PHASE,owner='SYNTHETIC_NEVER_AUTHORITATIVE',
                            decision='APPROVED',execution_authorized=True,request_sha256=None,payload_sha256=sha(k.source),effects=None,
                            host_binding_sha256=HOST,writes_allowed=m.WRITES_ALLOWED,activation_allowed=m.ACTIVATION_ALLOWED,
                            owner_evidence='SYNTHETIC_TEST_ONLY',**self.window)
        self.go=dict(schema=m.GO_SCHEMA,status='SIGNED',operation=m.OPERATION,phase=m.PHASE,owner='SYNTHETIC_NEVER_AUTHORITATIVE',action='GO',
                     execution_authorized=True,request_sha256=None,authority_sha256=None,payload_sha256=sha(k.source),effects=None,
                     host_binding_sha256=HOST,writes_allowed=m.WRITES_ALLOWED,activation_allowed=m.ACTIVATION_ALLOWED,
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
    def go16(self):return sha(self.raw()[2])[:16]
    def options(self,extra):
        options=dict(clock=lambda:self.now,monotonic=lambda:0,executor_uid=lambda:0);options.update(extra);return options
    def authenticate(self,**extra):
        return self.k.m.authenticate(*self.raw(),pins=self.pins(),payload_bytes=self.k.source,**self.options(extra))
    def run(self,host,**extra):
        return self.k.m.run(*self.raw(),pins=self.pins(),payload_bytes=self.k.source,host=host,**self.options(extra))
    def perform(self,host,gate=None,state=None,clock=None,monotonic=None):
        """The inner step, as run() calls it after authentication; lets a test inject its own gate or catch a death."""
        m=self.k.m;plan,real=self.authenticate()
        bound=m.digests(*self.raw(),self.k.source);bound['host_binding_sha256']=plan['host_binding_sha256']
        return m.perform(plan,gate or real,host,bound,clock or (lambda:self.now),monotonic or (lambda:0),state or m.Effects())

def line(receipt):
    """Exactly what the stdin launcher writes."""
    return json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
def sealed(receipt):
    body=dict(receipt);pin=body.pop('metadata_sha256');return sha(canonical(body))==pin

class Budget:
    """A clock for runs whose time matters: the emulated host's pauses and a cost per command advance one monotonic
    clock and the wall clock together. Use as docs.run(host,**budget.options()) after budget.attach(host)."""
    def __init__(self,now,command_seconds=0.0):
        self.now,self.elapsed,self.command_seconds=now,0.0,command_seconds;self.costs={}
    def attach(self,host):
        previous=host.hook
        def hook(host,name,detail,calls):
            if name=='pause':self.elapsed+=detail[0]
            elif name=='run':
                argv=detail[0];cost=self.command_seconds
                for words,seconds in self.costs.items():
                    if all(word in argv for word in words):cost=seconds
                self.elapsed+=cost
            if previous is not None:previous(host,name,detail,calls)
        host.hook=hook;return self
    def cost(self,seconds,*words):
        """A command whose argv holds every one of words takes this long."""
        self.costs[tuple(words)]=seconds;return self
    def monotonic(self):return self.elapsed
    def clock(self):return self.now+timedelta(seconds=self.elapsed)
    def options(self):return {'clock':self.clock,'monotonic':self.monotonic}


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
