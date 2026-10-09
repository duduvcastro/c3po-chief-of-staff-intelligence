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

SCHEMA='R2D2_EPOCH04_LOCAL_FOLDER_VETO_SOURCE_V1'
OBSERVATION='R2D2_EPOCH04_FOLDER_OBSERVATION_V1'
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
                'valid_from','valid_until','observe_not_before','observe_not_after','ttl_seconds','required_pins','veto_verifier'}
        need(type(spec)is dict and set(spec)==fields and v.canonical(spec)+b'\n'==raw,'FOLDER_SPEC_CANONICAL')
        need(spec['schema']==SCHEMA and spec['mode']in{'FIXTURE','REAL'},'FOLDER_SPEC_SCHEMA')
        c=spec['context'];need(type(c)is dict and set(c)=={'epoch','first_session','day','order_sha'}
            and c['epoch']=='R2D2-V2-SHADOW-2026-10-12'and c['first_session']==c['day']=='2026-10-12'
            and type(c['order_sha'])is str and v.SHA.fullmatch(c['order_sha']),'FOLDER_CONTEXT')
        for k in ('source_implementation_sha256','authority_sha256','owner_record_sha256','decision_document_sha256'):
            need(type(spec[k])is str and v.SHA.fullmatch(spec[k]),'FOLDER_SPEC_PIN')
        need(spec['decision_document_sha256']==D1_SHA,'FOLDER_D1_DOCUMENT')
        need(type(spec['source_identity'])is str and v.IDENTITY.fullmatch(spec['source_identity']),'FOLDER_SOURCE_IDENTITY')
        verifier=spec['authority_verifier'];need(type(verifier)is dict and set(verifier)=={'identity','implementation_sha256'}
            and type(verifier['identity'])is str and v.IDENTITY.fullmatch(verifier['identity'])
            and type(verifier['implementation_sha256'])is str and v.SHA.fullmatch(verifier['implementation_sha256']),'FOLDER_VERIFIER_PIN')
        emission_verifier=spec['veto_verifier']
        need(type(emission_verifier)is dict and set(emission_verifier)=={'identity','implementation_sha256','path','ancestors'}
            and type(emission_verifier['identity'])is str and v.IDENTITY.fullmatch(emission_verifier['identity'])
            and type(emission_verifier['implementation_sha256'])is str and v.SHA.fullmatch(emission_verifier['implementation_sha256'])
            and type(emission_verifier['path'])is str and type(emission_verifier['ancestors'])is list,'FOLDER_EMISSION_VERIFIER_PIN')
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
        need(af<=start<end<=au and type(spec['ttl_seconds'])is int and 0<spec['ttl_seconds']<=10,'FOLDER_CLOCK_POLICY')
        pins=spec['required_pins'];need(type(pins)is list and pins==sorted(set(pins))
            and all(type(x)is str and v.SHA.fullmatch(x)for x in pins)
            and {spec['source_implementation_sha256'],spec['authority_sha256'],spec['owner_record_sha256'],D1_SHA,
                 verifier['implementation_sha256'],emission_verifier['implementation_sha256'],c['order_sha']}<=set(pins),'FOLDER_REVOCATION_SCOPE')
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
        self.clock=clock;self.fds=[];self.original=None;self.original_body=None;self.binding=binding
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

    def authorize(self):
        check_authority(self.binding)
        now=v.now_utc(self.clock)
        need(v.instant(self.spec['valid_from'])<=now<v.instant(self.spec['valid_until']),'FOLDER_AUTHORITY_EXPIRED')
        try:accepted=self.binding.verify_current(self.raw,self.authority_raw,self.decision_raw,self.owner_raw,now)
        except Exception:raise Refused('FOLDER_AUTHORITY_REJECTED')from None
        need(accepted is None,'FOLDER_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION')
        check_authority(self.binding)
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

    def observe(self):
        need(self.original is None,'FOLDER_OBSERVATION_ALREADY_USED')
        self.authorize();self.check_empty();now=v.now_utc(self.clock)
        need(v.instant(self.spec['observe_not_before'])<=now<v.instant(self.spec['observe_not_after']),'FOLDER_OBSERVATION_WINDOW')
        until=min(now+timedelta(seconds=self.spec['ttl_seconds']),v.instant(self.spec['valid_until']),v.instant(self.spec['observe_not_after']))
        need(now<until,'FOLDER_OBSERVATION_NO_BUDGET')
        body={'schema':OBSERVATION,'mode':self.spec['mode'],'source_spec_sha256':self.sha,'context':self.spec['context'],
              'root':self.spec['root'],'observed_at':now.isoformat(),'valid_until':until.isoformat(),'entries_observed':0,'owner_veto':False}
        self.original_body=body;self.original=v.canonical(body)+b'\n'
        return self.original

    def current(self):
        need(self.original is not None,'FOLDER_OBSERVATION_ABSENT');self.authorize();self.check_empty();now=v.now_utc(self.clock)
        need(v.instant(self.original_body['observed_at'])<=now<v.instant(self.original_body['valid_until']),'FOLDER_OBSERVATION_STALE')
        return now

    def veto_verifier(self,veto_spec_raw,veto_authority_raw):
        """Actual folder verifier bound to one original and an authorized derived spec."""
        spec=v.read_spec(veto_spec_raw);ctx=self.spec['context']
        need(spec['mode']==self.spec['mode']and spec['context']==ctx
            and spec['source']=={'identity':self.spec['source_identity'],
                               'implementation_sha256':self.spec['source_implementation_sha256'],'observation_format':OBSERVATION}
            and spec['authority_sha256']==self.spec['authority_sha256']
            and spec['verifier']=={k:self.spec['veto_verifier'][k]for k in ('identity','implementation_sha256')}
            and set(self.spec['required_pins'])|{self.sha}==set(spec['required_pins']),'FOLDER_VETO_SPEC_BINDING')
        need(v.digest(veto_authority_raw)==self.spec['authority_sha256'],'FOLDER_VETO_AUTHORITY')
        program=self.spec['veto_verifier']
        try:ancestors=tuple((row[0],tuple(row[1]))for row in program['ancestors'])
        except Exception:raise Refused('FOLDER_EMISSION_VERIFIER_ROOTS')from None
        return v.load_verifier(program['path'],ancestors=ancestors,identity=program['identity'],
            implementation_sha256=program['implementation_sha256'],mode=self.spec['mode'],
            context=(self,veto_spec_raw,veto_authority_raw))

    def verified_observation(self,original,authority,raw,now):
        spec=v.read_spec(raw);ctx=self.spec['context'];body=self.original_body
        need(original==self.original and v.digest(authority)==self.spec['authority_sha256']
             and spec['context']==ctx and spec['source']['implementation_sha256']==self.spec['source_implementation_sha256']
             and spec['view_opens_at']==body['observed_at'],'FOLDER_VERIFIER_ORIGINAL')
        checked=self.current();need(now<=checked,'FOLDER_CLOCK_ROLLBACK')
        return v.VerifiedObservation(self.spec['mode'],self.spec['source_identity'],self.spec['source_implementation_sha256'],
            OBSERVATION,v.digest(original),self.spec['authority_sha256'],self.spec['valid_from'],self.spec['valid_until'],
            tuple(spec['required_pins']),'FABLE',True,True,True,ctx['epoch'],ctx['first_session'],ctx['day'],ctx['order_sha'],
            body['observed_at'],'VERIFIED',body['observed_at'],body['valid_until'],False,())
