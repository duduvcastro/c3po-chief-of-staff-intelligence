"""Trusted-child protocol for warm IMAGE10, never a Python hostile-code sandbox.

The caller sends no Python object, function, clock or output-attestation. Fixed
argv selects a pre-authorized registry; program and original bytes are read
through held descriptor chains before compilation. The approved bridge is code
inside this child, not a callback supplied over the transport. REAL authenticity
and physical image/authority verification remain that separately pinned bridge's
explicit duty. Same-server/root operation is supported; no external witness or
human cryptographic signature is required by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import time
from types import ModuleType, MappingProxyType, FunctionType

LIMIT=1024*1024
SCHEMA='R2D2_HOT_IMAGE10_REGISTRY_CANDIDATE_V1'
PROTOCOL='WARM_IMAGE10_ACTUAL_OBSERVATION'
GENERAL='R2D2_HOT_GENERAL_FACTUAL_ENVELOPE_V1'
_ACTIVE={}

class Refused(ValueError):pass
def need(value,code):
    if not value:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(value):return type(value)is str and len(value)==64 and set(value)<={'0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f'} and value not in {'0'*64,'0f'+'0'*62}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
def parse(raw):
    need(type(raw)is bytes and 0<len(raw)<=LIMIT,'HOT_BYTES')
    def pairs(items):
        out={}
        for k,v in items:need(k not in out,'HOT_DUPLICATE');out[k]=v
        return out
    try:value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in()).throw(ValueError()))
    except Refused:raise
    except Exception:raise Refused('HOT_JSON')from None
    need(type(value)is dict and canonical(value)==raw,'HOT_CANONICAL');return value
def utc_now():return datetime.now(timezone.utc)
def iso(value):return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def instant(value):
    need(type(value)is str and value.endswith('Z'),'HOT_TIME')
    try:out=datetime.fromisoformat(value[:-1]+'+00:00')
    except Exception:raise Refused('HOT_TIME')from None
    need(out.utcoffset().total_seconds()==0,'HOT_TIME');return out
def require_session(value,module_name):
    need(type(value)is HotSession and _ACTIVE.get(id(value))is value,'HOT_PROCESS_REQUIRED')
    value.check();need(value.loaded.spec['mode']=='REAL' and value.fixture_scope is False,'HOT_REAL_SESSION_REQUIRED')
    need(value.loaded.modules.get(module_name)is sys.modules.get(module_name),'HOT_MODULE_UNBOUND')
    return value
def directory(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
def file_identity(info):return directory(info)+(info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

class HeldFile:
    """Hold and recheck both descriptor and names; atime is not an identity pin."""
    def __init__(self,record,mode):
        need(type(record)is dict and set(record)=={'path','sha256','ancestors'},'HOT_FILE_RECORD')
        path=record['path'];need(type(path)is str and Path(path).is_absolute() and str(Path(path))==path and '..'not in Path(path).parts and '\x00'not in path,'HOT_FILE_PATH')
        need(pin(record['sha256']) and type(record['ancestors'])is list,'HOT_FILE_PIN')
        names=['/']+[str(Path(*Path(path).parent.parts[:i]))for i in range(2,len(Path(path).parent.parts)+1)]
        rows=record['ancestors'];need(len(rows)==len(names),'HOT_ANCESTORS')
        for name,row in zip(names,rows):
            need(type(row)is list and len(row)==2 and row[0]==name and type(row[1])is list and len(row[1])==5 and all(type(x)is int and x>=0 for x in row[1]),'HOT_ANCESTORS')
        need(mode in {'REAL','FIXTURE'} and rows[-1][1][4]==0o700 and (mode=='FIXTURE'or rows[-1][1][2]==0 and os.geteuid()==0),'HOT_ROOT_POLICY')
        self.record,self.mode,self.fds,self.fd=record,mode,[],None
        try:
            for index,(name,row)in enumerate(rows):
                fd=os.open('/'if index==0 else Path(name).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,**({}if index==0 else{'dir_fd':self.fds[-1]}))
                self.fds.append(fd);need(directory(os.fstat(fd))==tuple(row),'HOT_ROOT_CHANGED')
            self.fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fds[-1]);info=os.fstat(self.fd)
            need(stat.S_ISREG(info.st_mode)and info.st_nlink==1 and not(stat.S_IMODE(info.st_mode)&0o022)and 0<info.st_size<=LIMIT and(mode=='FIXTURE'or info.st_uid==0),'HOT_FILE_POLICY')
            self.identity=file_identity(info);self.raw=os.read(self.fd,LIMIT+1)
            need(len(self.raw)==info.st_size and sha(self.raw)==record['sha256'],'HOT_FILE_HASH');self.check()
        except BaseException:self.close();raise
    def check(self):
        need(self.fd is not None and file_identity(os.fstat(self.fd))==self.identity,'HOT_FILE_CHANGED')
        need(file_identity(os.stat(Path(self.record['path']).name,dir_fd=self.fds[-1],follow_symlinks=False))==self.identity,'HOT_FILE_CHANGED')
        for fd,(name,row)in zip(self.fds,self.record['ancestors']):
            named=os.lstat(name);need(stat.S_ISDIR(named.st_mode)and not stat.S_ISLNK(named.st_mode)and directory(named)==directory(os.fstat(fd))==tuple(row),'HOT_ROOT_CHANGED')
        os.lseek(self.fd,0,os.SEEK_SET);need(os.read(self.fd,LIMIT+1)==self.raw,'HOT_FILE_CHANGED')
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
        for fd in reversed(self.fds):os.close(fd)
        self.fds=[]

@dataclass(frozen=True)
class StaticInputs:
    registry_raw:bytes
    originals:tuple
    def get(self,name):
        rows=dict(self.originals);need(name in rows,'HOT_ORIGINAL_MISSING');return rows[name]

@dataclass(frozen=True)
class RuntimeBindings:
    """Constructed by measured bridge inside child, never deserialized from stdin."""
    authority:object
    folder_binding:object
    config_verifier:object
    config_loaded:object
    image:object
    base_settings:object

class LoadedSet:
    def __init__(self,registry_raw):
        self.raw=registry_raw;self.spec=parse(registry_raw);r=self.spec
        need(set(r)=={'schema','mode','protocol','epoch','day','programs','originals','bridge','ledger','outer_scope','authority_sha256','general_authority_sha256','general_source_identity','not_before','not_after'},'HOT_REGISTRY_FIELDS')
        need(r['schema']==SCHEMA and r['mode']in{'REAL','FIXTURE'} and r['protocol']==PROTOCOL and r['epoch']=='R2D2-V2-SHADOW-2026-10-12' and r['day']=='2026-10-12','HOT_REGISTRY_CONTEXT')
        need(pin(r['authority_sha256'])and pin(r['general_authority_sha256']) and type(r['general_source_identity'])is str and 0<len(r['general_source_identity'])<=96,'HOT_AUTHORITY_PINS')
        need(instant(r['not_before'])<instant(r['not_after']),'HOT_WINDOW')
        need(type(r['programs'])is dict and set(r['programs'])=={'hot_runtime','hot_worker','hot_watchdog','finite_batch','folder_veto','veto_emitter','config_finalizer','consumer_codec','j_slot','authority_bridge'},'HOT_PROGRAM_SET')
        names={'request','bound','owner','authority','runtime','rule','folder_spec','folder_authority','decision','folder_owner','config_base','template','veto_base','config_authority','act_b','machine_order'}
        need(type(r['originals'])is dict and set(r['originals'])==names,'HOT_ORIGINAL_SET')
        need(type(r['bridge'])is dict and set(r['bridge'])=={'bootstrap','authorize','general_read','general_verify'} and all(type(v)is str and v.isidentifier()for v in r['bridge'].values()),'HOT_BRIDGE_ABI')
        self.files={};self.modules={};self.functions={}
        try:
            for kind in ('programs','originals'):
                for name,record in r[kind].items():self.files[(kind,name)]=HeldFile(record,r['mode'])
            # All dependency bytes are frozen before any approved bridge executes.
            for name in ('hot_watchdog','finite_batch','veto_emitter','consumer_codec','config_finalizer','folder_veto','j_slot','authority_bridge'):
                held=self.files[('programs',name)];module=ModuleType(name);module.__file__=held.record['path'];sys.modules[name]=module
                exec(compile(held.raw,held.record['path'],'exec'),module.__dict__);self.modules[name]=module
            # Entrypoint/runtime are already running; compare exact measured source.
            need(self.files[('programs','hot_runtime')].raw==Path(__file__).read_bytes(),'HOT_RUNTIME_PIN')
            for name,module in self.modules.items():
                self.functions[name]={k:(v,v.__code__)for k,v in module.__dict__.items()if type(v)is FunctionType and v.__globals__ is module.__dict__}
            b=self.modules['authority_bridge'];need(getattr(b,'BRIDGE_MODE',None)==r['mode'],'HOT_BRIDGE_MODE')
            for method in r['bridge'].values():need(method in self.functions['authority_bridge'],'HOT_BRIDGE_FUNCTION')
            self.inputs=StaticInputs(registry_raw,tuple((name,self.files[('originals',name)].raw)for name in sorted(names)))
            self.check()
        except BaseException:self.close();raise
    def check(self):
        need(parse(self.raw)==self.spec,'HOT_REGISTRY_CHANGED')
        for held in self.files.values():held.check()
        for name,rows in self.functions.items():
            module=self.modules[name];need(sys.modules.get(name)is module,'HOT_MODULE_REPLACED')
            for key,(fn,code)in rows.items():need(getattr(module,key,None)is fn and fn.__code__ is code and fn.__globals__ is module.__dict__,'HOT_FUNCTION_CHANGED')
    def call(self,name,*args):
        self.check();module=self.modules['authority_bridge'];out=getattr(module,self.spec['bridge'][name])(*args);self.check();return out
    def close(self):
        for file in self.files.values():file.close()

class HotSession:
    """Private capability inside the approved child; never an external attestation."""
    def __init__(self,loaded,*,fixture_scope=False):
        need(type(loaded)is LoadedSet,'HOT_LOADER_REQUIRED');self.loaded=loaded;self.pid=os.getpid();self.parent=os.getppid();self.group=os.getpgrp();self.sid=os.getsid(0)
        self.fixture_scope=fixture_scope;self.warm_at=None;self.image_at=None;self.image_until=None;self.image_mark=None;self.last_wall=utc_now();self.last_mono=time.monotonic();self.general_raw=None;self.general=None;self.used=False;self.watchdog=None
        _ACTIVE[id(self)]=self;self.check()
    def check(self):
        need(_ACTIVE.get(id(self))is self and self.pid==os.getpid()and self.parent==os.getppid()and self.group==os.getpgrp()and self.sid==os.getsid(0)and threading.active_count()==1,'HOT_PROCESS_CHANGED')
        if self.loaded.spec['mode']=='REAL':need(self.group==self.sid and self.pid!=self.group
             and os.getpgid(self.parent)==self.group and os.geteuid()==0 and not self.fixture_scope,'HOT_OUTER_GROUP_REQUIRED')
        self.loaded.check();now,mono=utc_now(),time.monotonic();need(now>=self.last_wall and mono>=self.last_mono,'HOT_CLOCK_REGRESSION');self.last_wall,self.last_mono=now,mono
        need(instant(self.loaded.spec['not_before'])<=now<instant(self.loaded.spec['not_after']),'HOT_ATTEMPT_WINDOW')
        if self.image_at is not None:need(self.image_at<=now<self.image_until and mono-self.image_mark<(self.image_until-self.image_at).total_seconds(),'HOT_IMAGE10_EXPIRED')
        return now
    def authorize(self,phase):
        before=self.check();need(self.loaded.call('authorize',self.loaded.raw,self.loaded.inputs,phase,before)is None,'HOT_AUTHORITY_NOT_ATTESTED');self.check()
    def warm(self):
        need(self.warm_at is None and self.image_at is None,'HOT_WARM_ONCE');self.authorize('WARM_BEFORE_OBSERVATION')
        runtime=self.loaded.call('bootstrap',self.loaded.raw,self.loaded.inputs,MappingProxyType(self.loaded.modules));need(type(runtime)is RuntimeBindings,'HOT_RUNTIME_BINDINGS')
        if self.loaded.spec['mode']=='REAL':
            j=self.loaded.modules['j_slot'];need(type(runtime.image)is j.ImageBinding and runtime.image.mode=='REAL','HOT_IMAGE_BINDING')
            j.check_image(runtime.image);runtime.image.module.packaged()
            # Exact context(prepare_first=True) dependencies are imported before
            # T. The config, collector, store transaction and publication still
            # start only after the actual view and current authority exist.
            for name in ('app.r2d2_v2_document_format','app.r2d2_v2_capacity_bound',
                         'app.r2d2_v2_capacity_wiring','app.r2d2_v2_shadow_worker'):
                module=importlib.import_module(name)
                origin=str(Path(getattr(module,'__file__','')).resolve())
                app_root=str(Path(runtime.image.module.APPLICATION_ROOT).resolve())
                need(origin.startswith(app_root+'/'),'HOT_IMAGE_IMPORT_NAMESPACE')
        self.check();self.authorize('WARM_RUNTIME_LOADED');self.warm_at=self.check();self.refresh_general();return runtime
    def refresh_general(self):
        need(self.warm_at is not None,'HOT_NOT_WARM');self.authorize('GENERAL_FACTUAL_OBSERVATION');before=self.check()
        raw=self.loaded.call('general_read',self.loaded.raw,self.loaded.inputs,before);after=self.check();body=parse(raw)
        need(set(body)=={'schema','mode','epoch','day','purpose','source_identity','authority_sha256','registry_sha256','observed_at','valid_until','status','owner_veto','required_pins','revoked_shas'},'HOT_GENERAL_FIELDS')
        r=self.loaded.spec
        need(body['schema']==GENERAL and body['mode']==r['mode']and body['epoch']==r['epoch']and body['day']==r['day']and body['purpose']=='J_ADMISSION_WARM_IMAGE10' and body['status']=='ALLOW'and body['owner_veto']is False and body['source_identity']==r['general_source_identity']and body['authority_sha256']==r['general_authority_sha256']and body['registry_sha256']==sha(self.loaded.raw),'HOT_GENERAL_CONTEXT')
        observed,until=instant(body['observed_at']),instant(body['valid_until'])
        need(before<=observed<=after and self.warm_at<=observed<until and after<until and (after-observed).total_seconds()<=5,'HOT_GENERAL_STALE_OR_FUTURE')
        required=body['required_pins'];minimum={sha(self.loaded.raw),r['authority_sha256'],r['general_authority_sha256']}|{file.record['sha256']for file in self.loaded.files.values()}
        need(type(required)is list and required==sorted(set(required))and all(pin(x)for x in required)and minimum<=set(required),'HOT_GENERAL_REVOCATION_SCOPE')
        revoked=body['revoked_shas'];need(type(revoked)is list and revoked==sorted(set(revoked))and all(pin(x)for x in revoked)and not set(required)&set(revoked),'HOT_GENERAL_REVOKED')
        need(self.loaded.call('general_verify',self.loaded.raw,self.loaded.inputs,raw,after)is None,'HOT_GENERAL_NOT_ATTESTED');current=self.check()
        need(observed<=current<until and(current-observed).total_seconds()<=5,'HOT_GENERAL_STALE_OR_FUTURE');self.general_raw,self.general=raw,body;return raw
    def before_effect(self):
        """Reobserve actual general fact when needed; image T is never renewed."""
        now=self.check();need(self.general is not None,'HOT_GENERAL_ABSENT')
        observed=instant(self.general['observed_at']);until=instant(self.general['valid_until'])
        if not(observed<=now<until and(now-observed).total_seconds()<=5):self.refresh_general()
        self.authorize('IMMEDIATE_EFFECT');now=self.check()
        need(self.loaded.call('general_verify',self.loaded.raw,self.loaded.inputs,self.general_raw,now)is None,'HOT_GENERAL_NOT_ATTESTED')
        now=self.check();need(instant(self.general['observed_at'])<=now<instant(self.general['valid_until'])and(now-instant(self.general['observed_at'])).total_seconds()<=5,'HOT_GENERAL_STALE_OR_FUTURE');return now
    def effect_time_only(self):
        """No slow callback between this guard and a file's next effect syscall."""
        now,mono=utc_now(),time.monotonic()
        need(self.pid==os.getpid()and self.parent==os.getppid()and self.group==os.getpgrp()==self.sid==os.getsid(0),'HOT_PROCESS_CHANGED')
        need(self.general is not None and instant(self.general['observed_at'])<=now<instant(self.general['valid_until'])
             and(now-instant(self.general['observed_at'])).total_seconds()<=5,'HOT_GENERAL_STALE_OR_FUTURE')
        need(self.image_at is not None and self.image_at<=now<self.image_until and mono-self.image_mark<(self.image_until-self.image_at).total_seconds(),'HOT_IMAGE10_EXPIRED')
        return now
    def before_observation(self):
        need(self.warm_at is not None and self.image_at is None,'HOT_NOT_WARM')
        self.before_effect()
        if self.loaded.spec['mode']=='REAL':
            need(self.watchdog is None,'HOT_DOG_ONCE')
            self.watchdog=self.loaded.modules['hot_watchdog'].ImageWatchdog(instant(self.loaded.spec['not_after']))
            self.before_effect()
    def start_image(self,observed,until):
        need(self.warm_at is not None and self.image_at is None and type(observed)is datetime and type(until)is datetime,'HOT_IMAGE_ONCE')
        now=utc_now();need(self.warm_at<=observed<=now<until and 0<(until-observed).total_seconds()<=10,'HOT_IMAGE10_INTERVAL')
        self.image_at,self.image_until=observed,until
        # Account for all work since the actual original's T, including the
        # transition into this method. Native alarm is armed BEFORE callbacks.
        self.image_mark=time.monotonic()-(now-observed).total_seconds()
        if self.loaded.spec['mode']=='REAL':
            # Inherited outer worker group was verified above. The independent
            # outer supervisor also kills/reaps it at its own earlier deadline.
            def timeout(_signum,_frame):os.killpg(self.group,signal.SIGKILL)
            need(self.watchdog is not None,'HOT_DOG_NOT_WARM');self.watchdog.start(observed,until)
            previous=signal.getitimer(signal.ITIMER_REAL)[0];remaining=(until-utc_now()).total_seconds()
            need(remaining>0,'HOT_IMAGE10_EXPIRED');signal.signal(signal.SIGALRM,timeout)
            signal.setitimer(signal.ITIMER_REAL,min(remaining,previous)if previous>0 else remaining)
        self.check();self.before_effect()
    def close(self):
        if self.watchdog is not None:self.watchdog.close();self.watchdog=None
        _ACTIVE.pop(id(self),None)
