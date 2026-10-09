"""Authorized local-folder observation; no installer or authority issuer.

REAL observes the elected server folder itself; it does not trust a supplied
empty boolean. The independently pinned authority callback must accept exact
static inputs and current runtime, or raise. No default REAL callback exists.
An empty read is evidence only at its actual timestamp, never a renewal.
"""
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
from dataclasses import dataclass
from typing import Callable
import veto_emitter as v
import finite_batch as batch
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York')

SCHEMA='L12_SUNDAY_FOLDER_VETO_SOURCE_V3'
OBSERVATION='L12_SUNDAY_FOLDER_OBSERVATION_V1'
D1_SHA='09de76e5a2ee54fdcdfa477b0f8df101fcda761b7f416e4308e29c0235e51c2a'


class Refused(ValueError):pass
def need(ok,code):
    if not ok:raise Refused(code)


def directory_identity(info):
    return [info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)]


def measure_folder(path):
    """Read-only measurement for an independently authorized election, not authority."""
    need(type(path)is str and Path(path).is_absolute()and str(Path(path))==path
         and '..'not in Path(path).parts,'FOLDER_PATH')
    names=['/']+[str(Path(*Path(path).parts[:i]))for i in range(2,len(Path(path).parts)+1)]
    rows=[]
    for name in names:
        info=os.lstat(name);need(stat.S_ISDIR(info.st_mode)and not stat.S_ISLNK(info.st_mode),'FOLDER_ANCESTOR')
        rows.append([name,directory_identity(info)])
    return rows


def read_spec(raw):
    need(type(raw)is bytes and 0<len(raw)<=v.MAX_ORIGINAL_BYTES,'FOLDER_SPEC_BYTES')
    def pairs(items):
        out={}
        for k,x in items:need(k not in out,'FOLDER_SPEC_DUPLICATE');out[k]=x
        return out
    try:
        spec=json.loads(raw,object_pairs_hook=pairs)
        fields={'schema','mode','context','root','source_identity','source_implementation_sha256',
                'authority_sha256','authority_verifier','owner_record_sha256','decision_document_sha256',
                'valid_from','valid_until','observe_not_before','observe_not_after','ttl_seconds','required_pins','l12_scope','l12_authority_sha256','runtime_sha256','dependencies'}
        need(type(spec)is dict and set(spec)==fields and v.canonical(spec)+b'\n'==raw,'FOLDER_SPEC_CANONICAL')
        need(spec['schema']==SCHEMA and spec['mode']in{'FIXTURE','REAL'},'FOLDER_SPEC_SCHEMA')
        c=spec['context'];need(type(c)is dict and set(c)=={'epoch','first_session','target_session','factual_day','purpose'}
            and c['epoch']=='R2D2-V2-SHADOW-2026-10-12' and c['first_session']==c['target_session']=='2026-10-12'
            and c['factual_day']=='2026-10-11' and c['purpose']in{'UPSTREAM_P','E6_SUNDAY'},'FOLDER_CONTEXT')
        for k in ('source_implementation_sha256','authority_sha256','owner_record_sha256','decision_document_sha256'):
            need(type(spec[k])is str and v.SHA.fullmatch(spec[k]),'FOLDER_SPEC_PIN')
        need(spec['decision_document_sha256']==D1_SHA,'FOLDER_D1_DOCUMENT')
        need(type(spec['source_identity'])is str and v.IDENTITY.fullmatch(spec['source_identity']),'FOLDER_SOURCE_IDENTITY')
        verifier=spec['authority_verifier'];need(type(verifier)is dict and set(verifier)=={'identity','implementation_sha256'}
            and type(verifier['identity'])is str and v.IDENTITY.fullmatch(verifier['identity'])
            and type(verifier['implementation_sha256'])is str and v.SHA.fullmatch(verifier['implementation_sha256']),'FOLDER_VERIFIER_PIN')
        root=spec['root'];need(type(root)is dict and set(root)=={'path','ancestors','owner_uid'},'FOLDER_ROOT_FIELDS')
        need(type(root['path'])is str and Path(root['path']).is_absolute()and str(Path(root['path']))==root['path']
            and '..'not in Path(root['path']).parts and '\x00'not in root['path'],'FOLDER_PATH')
        expected=['/']+[str(Path(*Path(root['path']).parts[:i]))for i in range(2,len(Path(root['path']).parts)+1)]
        rows=root['ancestors'];need(type(rows)is list and len(rows)==len(expected),'FOLDER_ROOT_PINS')
        for row,name in zip(rows,expected):
            need(type(row)is list and len(row)==2 and row[0]==name and type(row[1])is list
                 and len(row[1])==5 and all(type(x)is int and x>=0 for x in row[1]),'FOLDER_ROOT_PINS')
        need(type(root['owner_uid'])is int and root['owner_uid']>=0 and root['owner_uid']==rows[-1][1][2]
             and rows[-1][1][4]==0o700 and (spec['mode']=='FIXTURE'or root['owner_uid']==0),'FOLDER_ROOT_POLICY')
        start,end=map(v.instant,(spec['observe_not_before'],spec['observe_not_after']))
        af,au=map(v.instant,(spec['valid_from'],spec['valid_until']))
        need(af<=start<end<=au and type(spec['ttl_seconds'])is int and 0<spec['ttl_seconds']<=5,'FOLDER_CLOCK_POLICY')
        dependencies=spec['dependencies']
        need(type(dependencies)is dict and set(dependencies)=={'finite_batch','veto_emitter'}
             and all(type(x)is str and v.SHA.fullmatch(x)for x in dependencies.values()),'FOLDER_DEPENDENCY_FIELDS')
        pins=spec['required_pins'];need(type(pins)is list and pins==sorted(set(pins))
            and all(type(x)is str and v.SHA.fullmatch(x)for x in pins)
            and {spec['source_implementation_sha256'],spec['authority_sha256'],spec['owner_record_sha256'],D1_SHA,
                 verifier['implementation_sha256'],spec['l12_authority_sha256'],spec['runtime_sha256'],*dependencies.values()}<=set(pins),'FOLDER_REVOCATION_SCOPE')
        need(all(type(spec[x])is str and v.SHA.fullmatch(spec[x])for x in ('l12_authority_sha256','runtime_sha256')),'FOLDER_L12_PINS')
        scope=spec['l12_scope'];need(type(scope)is dict and set(scope)=={'lane','track','previous_session','permitted_operations'},'FOLDER_L12_SCOPE')
        expected_lane='UPSTREAM_P'if c['purpose']=='UPSTREAM_P'else'DOWNSTREAM_AFTER_E6'
        need(scope['lane']==expected_lane and scope['track']=='P'and scope['previous_session']=='2026-10-09'
             and type(scope['permitted_operations'])is list and scope['permitted_operations']
             and len(scope['permitted_operations'])==len(set(scope['permitted_operations']))
             and all(x in (batch.UPSTREAM if c['purpose']=='UPSTREAM_P'else ('e6',))for x in scope['permitted_operations']),'FOLDER_L12_SCOPE')
        need(start.astimezone(NY).date().isoformat()==c['factual_day']
             and (end-timedelta(microseconds=1)).astimezone(NY).date().isoformat()==c['factual_day'],'FOLDER_FACTUAL_DAY_WINDOW')
        return spec
    except Refused:raise
    except Exception:raise Refused('FOLDER_SPEC_INVALID')from None


@dataclass(frozen=True)
class AuthorityBinding:
    identity:str
    implementation_sha256:str
    mode:str
    verify_current:Callable
    loaded:object=None


def check_authority(binding):
    if binding.mode=='REAL':
        v._check_loaded(binding.loaded)
        need(binding.loaded.mode=='REAL' and binding.loaded.identity==binding.identity
             and binding.loaded.implementation_sha256==binding.implementation_sha256
             and binding.verify_current is binding.loaded.verify_original,'FOLDER_AUTHORITY_NOT_LOADED')


class FolderSource:
    """Held descriptor chain, original observation, current rechecks; no file writes."""
    def __init__(self,spec_raw,authority_raw,decision_raw,owner_raw,*,spec_sha256,binding,clock):
        need(type(spec_sha256)is str and v.digest(spec_raw)==spec_sha256,'FOLDER_SPEC_HASH')
        self.spec=read_spec(spec_raw);self.raw=spec_raw;self.sha=spec_sha256
        self.authority_raw=authority_raw;self.decision_raw=decision_raw;self.owner_raw=owner_raw
        self.clock=clock;self.fds=[];self.original=None;self.original_body=None;self.binding=binding;self.current_view=None;self.view_context=None;self.used=set()
        need(type(authority_raw)is bytes and v.digest(authority_raw)==self.spec['authority_sha256'],'FOLDER_AUTHORITY_HASH')
        need(type(decision_raw)is bytes and v.digest(decision_raw)==D1_SHA,'FOLDER_D1_HASH')
        need(type(owner_raw)is bytes and v.digest(owner_raw)==self.spec['owner_record_sha256'],'FOLDER_OWNER_HASH')
        # Validate the pinned original owner record; hashes alone do not verify transport/runtime.
        try:owner=json.loads(owner_raw)
        except Exception:raise Refused('FOLDER_OWNER_INVALID')from None
        need(type(owner)is dict and set(owner)=={'schema','answer','channel','document','document_sha256','recorded_at_utc','scope'}
            and owner['schema']=='DUDU_OWNER_SIGNATURE_V1'and owner['answer']=='Assino (Recomendado)'
            and owner['channel']=='chat Fable (AskUserQuestion)'and owner['document_sha256']==D1_SHA
            and owner['scope']=='época R2D2-V2-SHADOW-2026-10-12 (12 a 16/10)','FOLDER_OWNER_SCOPE')
        signed=v.instant(owner['recorded_at_utc']);need(signed<v.instant(self.spec['observe_not_before']),'FOLDER_OWNER_NOT_PRIOR')
        need(type(binding)is AuthorityBinding and callable(binding.verify_current)
            and binding.mode==self.spec['mode']and binding.identity==self.spec['authority_verifier']['identity']
            and binding.implementation_sha256==self.spec['authority_verifier']['implementation_sha256'],'FOLDER_AUTHORITY_UNBOUND')
        need(self.spec['mode']=='FIXTURE' or clock is v.real_clock,'FOLDER_REAL_CLOCK_REQUIRED')
        check_authority(binding)
        own=Path(__file__).read_bytes();need(v.digest(own)==self.spec['source_implementation_sha256'],'FOLDER_IMPLEMENTATION_PIN')
        self.check_dependencies()
        self.authorize()
        try:
            self.fds.append(os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW))
            for i,(name,row)in enumerate(self.spec['root']['ancestors']):
                if i:self.fds.append(os.open(Path(name).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.fds[-1]))
                need(directory_identity(os.fstat(self.fds[-1]))==row,'FOLDER_IDENTITY_CHANGED')
            self.check_empty()
        except BaseException:self.close();raise

    def close(self):
        for fd in reversed(self.fds):os.close(fd)
        self.fds=[]

    def check_dependencies(self):
        for name,module in (('finite_batch',batch),('veto_emitter',v)):
            need(v.digest(Path(module.__file__).read_bytes())==self.spec['dependencies'][name],'FOLDER_DEPENDENCY_PIN')

    def authorize(self,q=None,task=None):
        self.check_dependencies()
        check_authority(self.binding)
        now=v.now_utc(self.clock)
        need(v.instant(self.spec['valid_from'])<=now<v.instant(self.spec['valid_until']),'FOLDER_AUTHORITY_EXPIRED')
        try:accepted=self.binding.verify_current(self.raw,self.authority_raw,self.decision_raw,self.owner_raw,q,task,now)
        except Exception:raise Refused('FOLDER_AUTHORITY_REJECTED')from None
        need(accepted is None,'FOLDER_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION')
        check_authority(self.binding)
        self.check_dependencies()
        after=v.now_utc(self.clock);need(now<=after<v.instant(self.spec['valid_until']),'FOLDER_AUTHORITY_DELAY')

    def check_empty(self):
        need(len(self.fds)==len(self.spec['root']['ancestors']),'FOLDER_NOT_HELD')
        for fd,(name,row)in zip(self.fds,self.spec['root']['ancestors']):
            named=os.lstat(name)
            need(stat.S_ISDIR(named.st_mode) and not stat.S_ISLNK(named.st_mode)
                 and directory_identity(os.fstat(fd))==row and directory_identity(named)==row,'FOLDER_IDENTITY_CHANGED')
        fd=self.fds[-1];before=os.fstat(fd)
        with os.scandir(fd)as listing:present=next(listing,None)is not None
        after=os.fstat(fd)
        need((before.st_mtime_ns,before.st_ctime_ns)==(after.st_mtime_ns,after.st_ctime_ns),'FOLDER_CHANGED_DURING_OBSERVATION')
        need(not present,'FOLDER_VETO_PRESENT')
        for fd,(name,row)in zip(self.fds,self.spec['root']['ancestors']):
            named=os.lstat(name)
            need(stat.S_ISDIR(named.st_mode) and not stat.S_ISLNK(named.st_mode)
                 and directory_identity(os.fstat(fd))==directory_identity(named)==row,'FOLDER_IDENTITY_CHANGED')
        return after

    def _observe(self,q,task):
        self.authorize(q,task);self.check_empty();now=v.now_utc(self.clock)
        need(v.instant(self.spec['observe_not_before'])<=now<v.instant(self.spec['observe_not_after']),'FOLDER_OBSERVATION_WINDOW')
        until=min(now+timedelta(seconds=self.spec['ttl_seconds']),v.instant(self.spec['valid_until']),v.instant(self.spec['observe_not_after']))
        need(batch.instant(task['not_before'])<=now<batch.instant(task['not_after']),'L12_VETO_ACTUAL_TASK_WINDOW')
        until=min(until,batch.instant(task['not_after']))
        need(now<until,'FOLDER_OBSERVATION_NO_BUDGET')
        body={'schema':OBSERVATION,'mode':self.spec['mode'],'source_spec_sha256':self.sha,'context':self.spec['context'],
              'root':self.spec['root'],'l12_context':batch.context(q),'operation':task['operation'],'observed_at':now.isoformat(),'valid_until':until.isoformat(),'entries_observed':0,'owner_veto':False}
        self.original_body=body;self.original=v.canonical(body)+b'\n'
        return self.original

    def _current(self,q,task):
        need(self.original is not None,'FOLDER_OBSERVATION_ABSENT');self.authorize(q,task);self.check_empty();now=v.now_utc(self.clock)
        need(v.instant(self.original_body['observed_at'])<=now<v.instant(self.original_body['valid_until']),'FOLDER_OBSERVATION_STALE')
        return now


    def _scope(self,q,task):
        need(type(q)is dict and type(task)is dict,'L12_VETO_CONTEXT')
        need(batch.validate_plan(batch.canonical(q))==q and type(q.get('tasks'))is list
             and sum(t==task for t in q['tasks'])==1,'L12_VETO_PLAN_OR_TASK')
        c=self.spec['context'];scope=self.spec['l12_scope']
        need(q.get('epoch')==c['epoch'] and q.get('session')==c['target_session']
             and q.get('previous_session')==scope['previous_session'] and q.get('track')==scope['track']
             and q.get('lane')==scope['lane'] and q.get('authority_sha256')==self.spec['l12_authority_sha256']
             and q.get('runtime_sha256')==self.spec['runtime_sha256']
             and q.get('veto_authority_sha256')==self.spec['authority_sha256']
             and task.get('operation')in scope['permitted_operations'],'L12_VETO_CONTEXT')
        now=v.now_utc(self.clock)
        need(now.astimezone(NY).date().isoformat()==c['factual_day'],'L12_VETO_FACTUAL_DAY')
        need(batch.instant(task['not_before'])<=now<batch.instant(task['not_after']),'L12_VETO_ACTUAL_TASK_WINDOW')
        return v.digest(batch.canonical(q)),v.digest(batch.canonical(task))

    def veto_read(self,q,task,supplied_now):
        context=self._scope(q,task);op=task['operation']
        # A new observation is allowed for each distinct authorized effect,
        # never for a retry or renewal of the same operation.
        need(op not in self.used,'L12_VETO_OPERATION_ALREADY_OBSERVED');self.used.add(op)
        self._observe(q,task);self.view_context=context
        self.current_view=batch.VetoView(self.original,self.spec['authority_sha256'],'ALLOW',
            v.instant(self.original_body['observed_at']),v.instant(self.original_body['valid_until']))
        return self.current_view

    def veto_verify(self,view,q,task,supplied_now):
        need(type(view)is batch.VetoView and view is self.current_view and view.raw==self.original
             and self._scope(q,task)==self.view_context,'L12_VETO_ORIGINAL')
        now=self._current(q,task)
        need(self._scope(q,task)==self.view_context,'L12_VETO_CONTEXT_CHANGED_AFTER_AUTHORITY')
        need(view.authority_sha256==self.spec['authority_sha256'] and view.verdict=='ALLOW'
             and view.observed_at<=now<view.valid_until
             and 0<(view.valid_until-view.observed_at).total_seconds()<=5,'L12_VETO_STALE')
        return None

    def before_effect(self,q,task):
        """Mandatory final hook in the independently pinned executor, no renewal."""
        need(self.current_view is not None,'L12_VETO_ORIGINAL')
        self.veto_verify(self.current_view,q,task,v.now_utc(self.clock))
        # Returning None is the accepted Services verifier convention;
        # this method itself never calls the host/app/executor.
        return None
