"""OP_K8_EVE: the eve delivery (E6) of one session day of epoch R2D2-V2-SHADOW-2026-10-05.

Into the capacity tree /var/lib/c3po-capacity, whose four roots (config, documents, go, payload) must already exist as
root:root 0700 directories: the twelve signed files of the day (template, two GO records, publication record and one
veto view per window into documents; the admission and bar_manifest GO files into go; one capacity config per window
into config), each holding exactly the bytes whose SHA-256 and size the request signs; and the payload file
session=<day>.json into payload, the canonical JSON of the signed contract and of the causal object of the day's
committed causal list, read by fixed path from the K9 tree (/var/lib/c3po/r2d2-v2-k9-20261005/days/<day>/causal) and
accepted only when its bytes are the ones the day's commit receipt names and its two hashes are the contract's causal
scope. Every file root:root 0600, by exclusive creation: a temporary file with unbuffered writes and fsync, exact
metadata, a link to the final name (a link never replaces anything), fsync of the directory, removal of the temporary
once its identity is proved; every file read back through descriptors inside the run. Everything is looked at before
the first creation: the executor, the window, the boot of the evidence, the signed chain to the K9 days, the capacity
tree, the commit receipt and the commitment, the seven chain documents the configs pin, the absence of every name, the
roots' identities, free space and the time left. This source starts no process, opens no socket, reads no environment
and no secret, writes no secret, never activates anything, never touches a container and never changes, renames or
removes an object that exists. No symbol and no hash or size of the payload file reaches its receipt. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba'}
# ==== END SEAL ====

# ==== BEGIN CORE (shared part, byte-identical in every source that carries it) ====
import errno
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone


class Refused(ValueError): pass
class CommandFailed(Refused):
    def __init__(self,code,returncode):
        Refused.__init__(self,code);self.returncode=returncode
def need(ok,code):
    if not ok:raise Refused(code)

COMPLETE_STATUS='METADATA_ONLY_REQUIRES_REVIEW'
PARTIAL_STATUS='PARTIAL_METADATA_REQUIRES_REVIEW'
REFUSED_STATUS='REFUSED'
# One UTC day per run, named by the signed request and confined by a code set. An operation part names one class of
# this table as DATE_CLASS and sets DATES=DATE_SETS[DATE_CLASS]; its dispatcher carries the same literal. A UTC day runs
# from 21:00 BRT of the previous day to 20:59:59 BRT, and every instant of a run's windows lies on that one day.
# 2026-10-05 UTC begins on Sunday 21:00 BRT and holds the first session; 2026-10-10 UTC ends on Saturday 20:59:59 BRT
# and holds the evening after the last session.
EPOCH_DAYS=('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')
DATE_SETS={'READ':EPOCH_DAYS,                                 # a source that changes nothing
           'WRITE_WEEKEND':EPOCH_DAYS[:3],                    # what must be over before the first-session day begins
           'WRITE_FIRST_SESSION':EPOCH_DAYS[3:4],             # install_release and activate: 2026-10-05 only
           'WRITE_SESSIONS':EPOCH_DAYS[3:],                   # daily writes and the end of the epoch
           'WRITE_EPOCH':EPOCH_DAYS[1:]}                      # a write that may fall on the weekend or on a session day
PRECHECK_OPERATION='GO_READONLY_HOSTOPS_PRECHECK_01'
MAX_SECONDS=60
MAX_DEPTH=16
RECEIPT_LIMIT=60000
SEAL_OVERHEAD=100
HEX64='[0-9a-f]{64}'
CODE='[A-Z][A-Z0-9_]{0,79}'
IMAGE_ID='sha256:[0-9a-f]{64}'
BOOT_ID_PATH='/proc/sys/kernel/random/boot_id'
REMOTE_COMMAND='sudo -n /usr/bin/python3 -I -B -'
REQUEST_KEYS=frozenset(('schema','status','operation','phase','date','not_before','not_after','host_binding_sha256',
                        'payload_sha256','scope_sha256','executor_uid','max_seconds','writes_allowed','activation_allowed',
                        'evidence','plan'))
AUTHORITY_KEYS=frozenset(('schema','status','operation','phase','owner','decision','execution_authorized','request_sha256',
                          'payload_sha256','effects','host_binding_sha256','not_before','not_after','writes_allowed',
                          'activation_allowed','owner_evidence'))
GO_KEYS=frozenset(('schema','status','operation','phase','owner','action','execution_authorized','request_sha256',
                   'authority_sha256','payload_sha256','effects','host_binding_sha256','not_before','not_after','writes_allowed',
                   'activation_allowed','claim_root_identity','transport_binding','scope_statement','success_criterion'))
PLAN_COMMON_KEYS=frozenset(('schema','status','phase','scope','window','host_binding_sha256','max_seconds'))
CHAIN_ROW_KEYS=frozenset(('path','device','inode','uid','gid','mode'))


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw,limit=65536):
    need(type(raw) is bytes and 0<len(raw)<=limit,'DOCUMENT_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'DUPLICATE_KEY');result[key]=value
        return result
    def constant(_):raise Refused('NONFINITE_JSON')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except Refused:raise
    except (ValueError,RecursionError):raise Refused('JSON_INVALID') from None
def decode(raw):
    value=strict(raw);need(type(value) is dict,'DOCUMENT_TYPE');return value
def document(raw):
    """A signed document is a JSON object in exactly its canonical bytes: one byte string per content, one hash."""
    value=decode(raw);need(canonical(value)==raw,'DOCUMENT_NOT_CANONICAL');return value
def exact(value,keys,code):
    need(type(value) is dict and set(value)==set(keys),code);return value
def instant(value):
    need(type(value) is str and len(value)<=40,'WINDOW_UNBOUND')
    try:point=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise Refused('WINDOW_UNBOUND') from None
    offset=point.utcoffset()
    need(point.tzinfo is not None and offset is not None and offset.total_seconds()==0,'WINDOW_NOT_UTC')
    return point
def text(value,pattern):return type(value) is str and re.fullmatch(pattern,value) is not None
def integer(value,low=0,high=None):
    return type(value) is int and value>=low and (high is None or value<=high)
def hexpin(value):return text(value,HEX64) and value!='0'*64
def clean_path(value):
    return (text(value,r'/[A-Za-z0-9._=/_-]{0,199}') and '//' not in value and str(PurePosixPath(value))==value
            and '..' not in PurePosixPath(value).parts and len(PurePosixPath(value).parts)<=MAX_DEPTH+1)
def inside(path,root):
    """True when path is root or lies below it (plain path arithmetic on clean paths)."""
    return path==root or path.startswith(root.rstrip('/')+'/')
def prefixes(path):
    """'/a/b' -> ['/', '/a', '/a/b']"""
    parts=PurePosixPath(path).parts;result=['/'];current=''
    for part in parts[1:]:
        current+='/'+part;result.append(current)
    return result
def kind(mode):
    if stat.S_ISDIR(mode):return 'dir'
    if stat.S_ISREG(mode):return 'file'
    if stat.S_ISLNK(mode):return 'symlink'
    return 'other'
def shape(info):
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
            'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'device':info.st_dev,'inode':info.st_ino}
def code_of(error,fallback):
    """Only a constant code ever leaves this process; raw exception text never does."""
    if isinstance(error,Refused) and text(str(error),CODE):return str(error)
    return fallback
def safe(error):
    if isinstance(error,Refused) and text(str(error),CODE):
        result={'status':'UNAVAILABLE','code':str(error)}
        if isinstance(error,CommandFailed) and type(error.returncode) is int:result['returncode']=error.returncode
        return result
    if isinstance(error,OSError):
        return {'status':'UNAVAILABLE','code':'OS_ERROR','errno':error.errno if type(error.errno) is int else None}
    return {'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'}
def attempt(action):
    try:return action()
    except Exception as error:return safe(error)
def combined(items):
    statuses=[item.get('status') for item in items]
    if statuses and all(value=='COMPLETE' for value in statuses):return 'COMPLETE'
    return 'UNAVAILABLE' if statuses and all(value=='UNAVAILABLE' for value in statuses) else 'PARTIAL'


class NativeRead:
    """Read-only host primitives shared by every source. A source's own Native adds only what its operation needs."""
    def identity(self):return os.geteuid(),os.getegid()
    def noatime(self):
        flag=getattr(os,'O_NOATIME',0);need(flag,'NOATIME_UNAVAILABLE');return flag
    def open(self,name,flags,dir_fd=None):
        return os.open(name,flags) if dir_fd is None else os.open(name,flags,dir_fd=dir_fd)
    def close(self,fd):os.close(fd)
    def fstat(self,fd):return os.fstat(fd)
    def lstat(self,name,dir_fd):return os.stat(name,dir_fd=dir_fd,follow_symlinks=False)
    def fstatvfs(self,fd):return os.fstatvfs(fd)
    def read(self,fd,size):return os.read(fd,size)
    def names(self,fd):
        with os.scandir(fd) as iterator:
            for entry in iterator:yield entry.name


# ---------------------------------------------------------------- pinned parents
def chain_rows(rows,path,code='CHAIN_ROW_INVALID'):
    """One signed row per component from '/': the observed identity, owner and mode of an existing parent. Nothing is assumed to be 0."""
    need(clean_path(path) and type(rows) is list and len(rows)==len(prefixes(path)),code)
    for row,prefix in zip(rows,prefixes(path)):
        need(type(row) is dict and set(row)==set(CHAIN_ROW_KEYS) and row['path']==prefix,code)
        need(integer(row['device']) and integer(row['inode'],1) and integer(row['uid']) and integer(row['gid'])
             and integer(row['mode'],0,0o7777),code)
    return rows
def row_root_safe(row):return row['uid']==0 and not row['mode']&0o022
def row_of(path,info):
    return {'path':path,'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
            'mode':stat.S_IMODE(info.st_mode)}
def mount_point_of(rows):
    """The mount point of the filesystem of the last row, as far as device numbers show it: the deepest component whose
    device differs from its parent's, "/" when none does. A bind mount of the same filesystem cannot be seen this way."""
    point=rows[0]['path']
    for previous,row in zip(rows,rows[1:]):
        if row['device']!=previous['device']:point=row['path']
    return point
def row_equal(seen,signed,compare_device=True):
    fields=('device','inode','uid','gid','mode') if compare_device else ('inode','uid','gid','mode')
    return all(seen[field]==signed[field] for field in fields)

def walk_pinned(host,rows,check,observed,compare_device=True):
    """Open '/' and then each component by dir_fd without following a link. An lstat classifies the component before
    the open, so no errno is interpreted; after the open the held descriptor must equal the signed row on every value.
    Observed rows are appended as they are read, so a refusal carries what was seen. Returns the last descriptor."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check()
    try:fd=host.open('/',flags)
    except OSError:raise Refused('PARENT_MISSING') from None
    try:
        info=host.fstat(fd)
        for index,row in enumerate(rows):
            if index:
                name=PurePosixPath(row['path']).name;check()
                try:named=host.lstat(name,fd)
                except FileNotFoundError:raise Refused('PARENT_MISSING') from None
                except OSError:raise Refused('PARENT_UNREADABLE') from None
                if not stat.S_ISDIR(named.st_mode):
                    observed.append(dict(row_of(row['path'],named),type=kind(named.st_mode)))
                    raise Refused('PARENT_SYMLINK_COMPONENT' if stat.S_ISLNK(named.st_mode) else 'PARENT_NOT_DIRECTORY')
                check()
                try:child=host.open(name,flags,dir_fd=fd)
                except OSError:raise Refused('PARENT_CHANGED_DURING_WALK') from None
                host.close(fd);fd=child;info=host.fstat(fd)
                need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PARENT_CHANGED_DURING_WALK')
            seen=row_of(row['path'],info);observed.append(seen)
            need(stat.S_ISDIR(info.st_mode) and row_equal(seen,row,compare_device),'PARENT_IDENTITY_MISMATCH')
        check();return fd
    except BaseException:
        host.close(fd);raise

class Pinned:
    """A held directory descriptor whose way from '/' is proved again before each use.
    Either a signed chain (rows) or a child of another Pinned (parent, name) with the identity recorded when it was opened."""
    def __init__(self,host,fd,*,rows=None,parent=None,name=None,compare_device=True):
        self.host,self.fd,self.rows,self.parent,self.name,self.compare_device=host,fd,rows,parent,name,compare_device
        info=host.fstat(fd);self.identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
    def stamp(self,info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
    def verify(self,check):
        try:
            need(self.stamp(self.host.fstat(self.fd))==self.identity,'PARENT_REPLACED')
            if self.rows is not None:
                other=walk_pinned(self.host,self.rows,check,[],self.compare_device)
                try:need(self.stamp(self.host.fstat(other))==self.identity,'PARENT_REPLACED')
                finally:self.host.close(other)
            else:
                self.parent.verify(check);check()
                need(self.stamp(self.host.lstat(self.name,self.parent.fd))==self.identity,'PARENT_REPLACED')
        except Refused as error:
            raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED') else 'PARENT_REPLACED') from None
        except OSError:
            raise Refused('PARENT_REPLACED') from None
    def close(self):
        if self.fd is not None:self.host.close(self.fd);self.fd=None

def probe(host,path,check):
    """lstat of the leaf only; no component is followed. Absence is proved at the first missing component."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check();fd=host.open('/',flags)
    try:
        parts=PurePosixPath(path).parts[1:];prefix=''
        for index,part in enumerate(parts):
            prefix+='/'+part;check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:
                return {'status':'COMPLETE','exists':False,'absent_at':prefix,'absence_proved_at_read':True}
            if index==len(parts)-1:return {'status':'COMPLETE','exists':True,'links':named.st_nlink,**shape(named)}
            if stat.S_ISLNK(named.st_mode):
                return {'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','exists':None,'at':prefix}
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
        return {'status':'COMPLETE','exists':True,'links':host.fstat(fd).st_nlink,**shape(host.fstat(fd))}
    finally:host.close(fd)

def descend(host,path,check,rows=None):
    """Open a directory component by component, never following a link, with no signed expectation. Returns the
    descriptor. With rows, one observed row per component ('/' included) is appended in the format a request signs."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    check();fd=host.open('/',flags)
    try:
        if rows is not None:rows.append(row_of('/',host.fstat(fd)))
        prefix=''
        for part in PurePosixPath(path).parts[1:]:
            prefix+='/'+part;check();named=host.lstat(part,fd)
            need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT')
            need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd);need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED')
            if rows is not None:rows.append(row_of(prefix,held))
        check();return fd
    except BaseException:
        host.close(fd);raise

def count_entries(host,fd,check,limit=4096):
    """Number of entries of a held directory; names never leave this function."""
    count=0
    for _ in host.names(fd):
        count+=1
        if count%256==0:check()
        need(count<=limit,'ENTRY_LIMIT')
    return count

def read_regular(host,name,dir_fd,check,limit):
    """Bytes of one regular file opened by dir_fd without following a link, unchanged between two fstat calls.
    Returns (bytes, fstat). The bytes stay with the caller: of a file that may hold a secret nothing but a boolean
    (equal to a signed hash, unchanged since an earlier read of the same run) may reach a receipt."""
    check();fd=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|host.noatime(),dir_fd=dir_fd)
    try:
        before=host.fstat(fd)
        need(stat.S_ISREG(before.st_mode),'FILE_NOT_REGULAR');need(before.st_size<=limit,'FILE_TOO_LARGE')
        chunks=[];size=0
        while size<=limit:
            check();block=host.read(fd,min(65536,limit+1-size))
            if not block:break
            chunks.append(block);size+=len(block)
        after=host.fstat(fd)
        def signature(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns
        need(signature(before)==signature(after) and size==before.st_size,'FILE_CHANGED_DURING_READ')
        return b''.join(chunks),before
    finally:host.close(fd)

def boot_id_sha256(host,check):
    """SHA-256 of the kernel's boot identifier (a random UUID per boot, not a secret). A receipt whose rows were read
    in an earlier boot cannot pin device numbers: the request names the boot of its evidence and this is compared."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    parts=PurePosixPath(BOOT_ID_PATH).parts[1:]
    check();fd=host.open('/',flags)
    try:
        for part in parts[:-1]:
            check();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
        check();leaf=host.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:raw=host.read(leaf,64)
        finally:host.close(leaf)
    finally:host.close(fd)
    need(type(raw) is bytes and re.fullmatch(rb'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\n?',raw) is not None,'BOOT_ID_INVALID')
    return sha(raw.strip())


# ---------------------------------------------------------------- authority
@dataclass(frozen=True)
class Pins:
    payload:str
    request:str
    authority:str
    go:str
class Gate:
    def __init__(self,start,end,clock,monotonic):
        self.start,self.end,self.clock,self.monotonic=start,end,clock,monotonic
        self.wall,self.mono=clock(),monotonic();self.deadline=self.mono+MAX_SECONDS
        need(start<=self.wall<end,'OUTSIDE_GO_WINDOW')
    def __call__(self):
        wall,mono=self.clock(),self.monotonic()
        need(wall>=self.wall and mono>=self.mono,'CLOCK_REVERSED')
        self.wall,self.mono=wall,mono
        need(self.start<=wall<self.end and mono<self.deadline,'GO_EXPIRED')
        return min((self.end-wall).total_seconds(),self.deadline-mono)

def validate_evidence(evidence):
    """Names the prior receipts the pinned rows were copied from. The code cannot read them; it requires them to be named,
    and for each operation name in EVIDENCE_OPERATIONS (the operation's own constant) at least one entry."""
    need(type(evidence) is list and len(evidence)<=16 and (evidence or not EVIDENCE_REQUIRED),'EVIDENCE_UNBOUND')
    for item in evidence:
        need(type(item) is dict and set(item)=={'role','operation','receipt_sha256'} and text(item['role'],'[A-Z][A-Z0-9_]{0,63}')
             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}') and hexpin(item['receipt_sha256']),'EVIDENCE_UNBOUND')
    need(all(any(item['operation']==name for item in evidence) for name in EVIDENCE_OPERATIONS),'EVIDENCE_OPERATION_MISSING')

def validate_common(plan):
    exact(plan,PLAN_COMMON_KEYS|PLAN_KEYS,'PLAN_KEYS')
    need(plan['schema']==PLAN_SCHEMA and plan['status']=='BOUND','PLAN_UNBOUND')
    need(plan['phase']==PHASE,'PHASE_INVALID')
    need(type(plan['max_seconds']) is int and plan['max_seconds']==MAX_SECONDS,'LIMITS_INVALID')
    need(type(plan['scope']) is dict and canonical(plan['scope'])==canonical(SCOPE),'SCOPE_MISMATCH')
    exact(plan['window'],('not_before','expires_at'),'PLAN_WINDOW')

def authenticate(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
                 clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
                 executor_uid=os.geteuid):
    """Pure with respect to the host: reads two clocks and the effective uid, nothing else. Also run locally by the
    dispatcher before any claim, so a malformed document cannot spend the single-use GO."""
    for name,data in [('request',request_bytes),('authority',authority_bytes),('go',go_bytes),('payload',payload_bytes)]:
        pin=getattr(pins,name,None)
        need(hexpin(pin) and type(data) is bytes and sha(data)==pin,'PIN_MISMATCH')
    request,authority,go=map(document,(request_bytes,authority_bytes,go_bytes))
    exact(request,REQUEST_KEYS,'REQUEST_KEYS');exact(authority,AUTHORITY_KEYS,'AUTHORITY_KEYS');exact(go,GO_KEYS,'GO_KEYS')
    need(request['schema']==REQUEST_SCHEMA and request['status']=='BOUND'
         and request['operation']==OPERATION and request['phase']==PHASE
         and request['scope_sha256']==SCOPE_SHA256 and request['payload_sha256']==pins.payload
         and type(request['executor_uid']) is int and request['executor_uid']==0 and executor_uid()==0,'REQUEST_OR_EXECUTOR_UNBOUND')
    need(type(request['max_seconds']) is int and request['max_seconds']==MAX_SECONDS and request['writes_allowed'] is WRITES_ALLOWED
         and request['activation_allowed'] is ACTIVATION_ALLOWED,'REQUEST_SCOPE')
    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE
         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True
         and authority['request_sha256']==pins.request and authority['payload_sha256']==pins.payload
         and authority['writes_allowed'] is WRITES_ALLOWED and authority['activation_allowed'] is ACTIVATION_ALLOWED
         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512
         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')
    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE
         and go['operation']==OPERATION and go['execution_authorized'] is True
         and go['writes_allowed'] is WRITES_ALLOWED and go['activation_allowed'] is ACTIVATION_ALLOWED
         and go['request_sha256']==pins.request and go['authority_sha256']==pins.authority
         and go['payload_sha256']==pins.payload,'GO_UNBOUND')
    need(type(go['owner']) is str and go['owner'] not in ('','UNBOUND') and len(go['owner'])<=128
         and go['owner']==authority['owner'],'OWNER_UNBOUND')
    host=request['host_binding_sha256']
    need(hexpin(host) and host==authority['host_binding_sha256']==go['host_binding_sha256'],'HOST_BINDING')
    binding=go['transport_binding']
    need(type(binding) is dict and set(binding)=={'target','remote_command','command_sha256','runtime_sha256'}
         and type(binding['target']) is str and binding['target'] and hexpin(binding['command_sha256'])
         and binding['remote_command']==REMOTE_COMMAND and type(binding['runtime_sha256']) is dict
         and binding['runtime_sha256'].get(SOURCE_NAME)==pins.payload,'GO_TRANSPORT_UNBOUND')
    root=go['claim_root_identity']
    need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['path']) is str and root['path'].startswith('/')
         and integer(root['device']) and integer(root['inode'],1),'GO_CLAIM_ROOT_UNBOUND')
    need(type(request['date']) is str and request['date'] in DATES,'DATE_NOT_IN_SCOPE')
    starts=[instant(d['not_before']) for d in (request,authority,go)]
    ends=[instant(d['not_after']) for d in (request,authority,go)]
    need(all(point.date().isoformat()==request['date'] for point in starts+ends),'DATE_WINDOW_MISMATCH')
    start,end=max(starts),min(ends)
    need(start<end and (end-start).total_seconds()<=MAX_GATE_SPAN_SECONDS,'WINDOW_SPAN')
    gate=Gate(start,end,clock,monotonic);gate()
    plan=request['plan']
    need(type(plan) is dict and plan.get('host_binding_sha256')==host,'PLAN_BINDING')
    validate_common(plan)
    need(instant(plan['window']['not_before'])==starts[0] and instant(plan['window']['expires_at'])==ends[0],'PLAN_WINDOW')
    validate_evidence(request['evidence'])
    validate_plan(plan)
    effects=canonical(effects_of(plan))
    need(type(authority['effects']) is dict and type(go['effects']) is dict
         and canonical(authority['effects'])==effects==canonical(go['effects']),'EFFECTS_BINDING')
    need(go['scope_statement']==SCOPE_STATEMENT and go['success_criterion']==success_of(plan),'GO_CRITERION')
    return plan,gate


# ---------------------------------------------------------------- effects, receipts, entry point
class Effects:
    """Counts the mutating calls of a run. issue() comes immediately before each call; exactly one of done(), fail()
    or unknown() follows. A call that was issued and never settled is uncertain. A run may be reported REFUSED only
    while nothing succeeded and nothing is uncertain."""
    def __init__(self):self.started=False;self.issued=0;self.succeeded=0;self.failed=0;self.pending=False
    def issue(self):self.issued+=1;self.pending=True
    def done(self):self.succeeded+=1;self.pending=False
    def fail(self):self.failed+=1;self.pending=False
    def unknown(self):self.pending=False
    def uncertain(self):return self.issued-self.succeeded-self.failed
    def clean(self):return self.succeeded==0 and self.uncertain()==0
    def counts(self):
        return {'issued':self.issued,'succeeded':self.succeeded,'failed_nothing_changed':self.failed,'uncertain':self.uncertain()}

def mutate(state,gate,action):
    """The only way a mutating call is made: gate, count, call. An OSError raised by the call itself means that call
    changed nothing (mkdir, exclusive open, link and unlink are atomic); any other exit leaves it uncertain."""
    gate();state.issue()
    try:result=action()
    except OSError:state.fail();raise
    state.done();return result

FILESYSTEM_CODES={errno.EROFS:'FILESYSTEM_READ_ONLY',errno.ENOSPC:'FILESYSTEM_FULL',errno.EDQUOT:'FILESYSTEM_FULL',
                  errno.EACCES:'FILESYSTEM_ACCESS_DENIED',errno.EPERM:'FILESYSTEM_ACCESS_DENIED'}
def filesystem_code(error):
    """errno of a failed creating call -> constant code. EEXIST is decided by the caller, which knows the name."""
    return FILESYSTEM_CODES.get(error.errno if type(error.errno) is int else -1,'FILESYSTEM_ERROR')

def digests(request_bytes,authority_bytes,go_bytes,payload_bytes):
    """Hashes computed here from the bytes received, never copied from a claim."""
    def one(raw):return sha(raw) if type(raw) is bytes else None
    return {'request_sha256':one(request_bytes),'authority_sha256':one(authority_bytes),'go_sha256':one(go_bytes),
            'payload_sha256':one(payload_bytes)}

def timing(begun,mark,clock,monotonic):
    """The clock member of a receipt; None when a clock fails (a receipt is still returned)."""
    try:
        ended,elapsed=clock(),monotonic()-mark
        return {'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
    except Exception:return None

def envelope(status,outcome,code,bound):
    """activation_performed and daemon_reload_performed speak of systemd units and of the manager only. They are False
    here; a source whose ACTIVATION_ALLOWED is True sets them through bound to what its run did."""
    receipt={'schema':RECEIPT_SCHEMA,'operation':OPERATION,'status':status,'outcome':outcome,'code':code,
             'scope_sha256':SCOPE_SHA256,'core_sha256':CORE_SHA256,'activation_performed':False,'daemon_reload_performed':False,
             'secret_bytes_in_receipt':False,'ready':False}
    receipt.update(bound);return receipt

def seal(receipt):
    """Fit the dispatcher's 64 KiB decode limit by explicit flagged reduction, then hash. Never raises. A reduced
    receipt is never reported complete; the record of mutating calls is never dropped."""
    def size():return len(canonical(receipt))+SEAL_OVERHEAD
    try:
        applied=[];receipt['size_reductions']=applied
        for name,step in REDUCTIONS:
            if size()<=RECEIPT_LIMIT:break
            applied.append(name)
            if receipt['status']==COMPLETE_STATUS:receipt['status']=PARTIAL_STATUS;receipt['outcome']=REDUCED_OUTCOME
            try:step(receipt)
            except Exception:applied.append(name+'_FAILED')
        need(size()<=RECEIPT_LIMIT,'RECEIPT_LIMIT')
    except Exception:
        kept={key:receipt.get(key) for key in ('schema','operation','request_sha256','authority_sha256','go_sha256','payload_sha256',
                                              'host_binding_sha256','scope_sha256','core_sha256','mutating_calls','objects_left_by_this_run',
                                              'activation_performed','daemon_reload_performed')}
        was_refused=receipt.get('status')==REFUSED_STATUS
        receipt.clear();receipt.update(kept)
        receipt.update(status=REFUSED_STATUS if was_refused else PARTIAL_STATUS,
                       outcome=REFUSED_OUTCOME if was_refused else REDUCED_OUTCOME,code='RECEIPT_REDUCED_TO_MINIMUM',
                       size_reductions=['RECEIPT_REDUCED_TO_MINIMUM'],secret_bytes_in_receipt=False,ready=False)
    receipt['metadata_sha256']=sha(canonical(receipt));return receipt

def run(request_bytes,authority_bytes,go_bytes,*,pins,payload_bytes,
        clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,executor_uid=os.geteuid,host=None):
    """Entry point of the stdin launcher. It never raises: a refusal is a returned object. The launcher treats an
    exception that escapes from here as a run of unknown state, never as a refusal."""
    state=Effects();bound=digests(request_bytes,authority_bytes,go_bytes,payload_bytes)
    try:
        try:plan,gate=authenticate(request_bytes,authority_bytes,go_bytes,pins=pins,payload_bytes=payload_bytes,
                                   clock=clock,monotonic=monotonic,executor_uid=executor_uid)
        except Refused as error:
            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'AUTHENTICATION_REFUSED'),
                                 dict(bound,phase_reached='AUTHENTICATION',mutating_calls=state.counts())))
        bound['host_binding_sha256']=plan['host_binding_sha256']
        return perform(plan,gate,host if host is not None else Native(),bound,clock,monotonic,state)
    except BaseException as error:
        # Last resort. With nothing started (or, for a write operation, nothing issued that could have changed the
        # host) this is a refusal; otherwise it is a partial whose state only a later read-only operation establishes.
        nothing=(not state.started) or (WRITES_ALLOWED and state.clean() and not state.pending)
        if nothing:
            return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code_of(error,'RUN_FAILED_BEFORE_ANY_EFFECT'),
                                 dict(bound,phase_reached='BEFORE_ANY_EFFECT',mutating_calls=state.counts())))
        # Whether a unit was switched is not known here; a source that may switch one says so instead of False.
        unknown={'activation_performed':None,'daemon_reload_performed':None} if ACTIVATION_ALLOWED else {}
        return seal(envelope(PARTIAL_STATUS,ESCAPED_OUTCOME,code_of(error,'RUN_ESCAPED_STATE_UNKNOWN'),
                             dict(bound,phase_reached='ESCAPED',mutating_calls=state.counts(),**unknown)))
# ==== END CORE ====

# ==== BEGIN PARENTS (shared part, byte-identical in every source that carries it) ====
# The acceptance of signed chain rows, as the reviewed family applies it. Outside an open root every component must be
# root-owned and not writable by group or other. At and below an open root (a directory the request names as owned by
# an operational account: the data volume root, the deploy tree) the observed owner and mode are accepted as signed,
# with one floor: a directory any local user can write to without the sticky bit is refused, because any user could
# then rename what a run creates in it.
def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX
def row_accepted(row,open_root):
    """None when the signed row is accepted, otherwise the refusal code."""
    if row_root_safe(row):return None
    if open_root is None or not inside(row['path'],open_root):return 'CHAIN_ROW_UNSAFE'
    return 'CHAIN_ROW_WORLD_WRITABLE' if world_writable_without_sticky(row) else None

def validate_chain(rows,path,open_root=None,receives_entry=False):
    """Signed rows of one existing directory, one per component from '/'. With receives_entry the directory must not be
    setgid: the kernel would hand its group and the bit to what is created in it. Returns the rows."""
    need(open_root is None or (type(open_root) is str and clean_path(open_root) and open_root!='/'),'PATH_INVALID')
    rows=chain_rows(rows,path)
    for row in rows:
        code=row_accepted(row,open_root);need(code is None,code or 'CHAIN_ROW_UNSAFE')
    need(not receives_entry or not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')
    return rows

def chain_effects(rows):
    """What the signers see of a pinned directory without opening the request: its own row, the hash of all its rows,
    and the mount point of its filesystem as the device numbers of the rows show it."""
    return {'path':rows[-1]['path'],'row':rows[-1],'chain_sha256':sha(canonical(rows)),'mount_point_by_device_change':mount_point_of(rows)}

def stat_signature(info):
    """What tells that a file or directory is the same object with the same content as at an earlier lstat or fstat of
    the same run, without reading it: identity, size, both change instants, owner and mode. For comparison inside the
    run only; of a file that may hold a secret none of these values goes into a receipt."""
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))

def free_bytes(host,fd):
    """Bytes available to a non-root writer on the filesystem of a held descriptor (f_bavail * f_frsize)."""
    numbers=host.fstatvfs(fd)
    need(integer(numbers.f_bavail) and integer(numbers.f_frsize,1),'STATVFS_INVALID')
    return numbers.f_bavail*numbers.f_frsize
# ==== END PARENTS ====

# ==== BEGIN FILES (shared part, byte-identical in every source that carries it) ====
PRIVATE_FILE_MODE=0o600
PRIVATE_DIRECTORY_MODE=0o700
DIRECTORY_MODES=(0o700,)
FILE_MODES=(0o600,0o644)
FILE_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
MAX_FILE_BYTES=1048576
MAX_DIRECTORY_ENTRIES=4096
# The temporary name of the reviewed unit installer: dot-prefixed, keyed by the first 16 hex of the GO hash and by the
# index of the file inside the run, so two runs and two files of one run never share it.
TEMPORARY='.hostops-%s-%d.partial'
LEFTOVER=r'\.hostops-[0-9a-f]{16}-[0-9]{1,2}\.partial'
FILE_STATES=('NOT_ATTEMPTED','NOT_CREATED','TEMPORARY_ONLY','LINKED_TEMPORARY_PRESENT','INSTALLED_NOT_DURABLE','INSTALLED_DURABLE')
DIRECTORY_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATED_UNVERIFIED','CREATED_METADATA_MISMATCH','CREATED_NOT_EMPTY','CREATED_NOT_DURABLE','CREATED_DURABLE')
FILES_SCOPE={'file':{'type':'regular file','uid':0,'gid':0,'links':1,'modes_octal':['%04o'%mode for mode in FILE_MODES],'max_bytes':MAX_FILE_BYTES,
                     'how':'exclusive temporary, unbuffered writes, fsync, exact metadata, link to the final name (a link never replaces anything), '
                           'fsync of the directory, removal of the temporary once its identity is proved, fsync of the directory',
                     'temporary_name':TEMPORARY%('<first 16 hex of the GO hash>',0),'leftover_pattern':LEFTOVER},
             'directory':{'type':'directory','uid':0,'gid':0,'modes_octal':['%04o'%mode for mode in DIRECTORY_MODES],'how':'one mkdir relative to a held descriptor of its pinned parent, then '
                          'identity, owner, mode and emptiness proved through a descriptor, fsync of the directory and of its parent'},
             'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created and proved by identity']}

class NativeFiles:
    """The seven calls with which a source creates private directories and files. Nothing here changes an object that exists."""
    def umask(self,mask):return os.umask(mask)
    def mkdir(self,name,mode,dir_fd):os.mkdir(name,mode,dir_fd=dir_fd)
    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)
    def write(self,fd,data):return os.write(fd,data)
    def fsync(self,fd):os.fsync(fd)
    def link(self,source,target,dir_fd):os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)
    def unlink(self,name,dir_fd):os.unlink(name,dir_fd=dir_fd)

def number(error):return error.errno if isinstance(error,OSError) and type(error.errno) is int else None

def named_in(path,parent):
    """True when path is a clean path whose directory is the one the pinned parent was walked to (checked where the
    parent carries its signed rows; a directory this run created is trusted to be what the caller says)."""
    return (type(path) is str and clean_path(path) and text(PurePosixPath(path).name,FILE_NAME)
            and (parent.rows is None or str(PurePosixPath(path).parent)==parent.rows[-1]['path']))

def file_request(name,content_sha256,size,mode):
    """The signed description of one file a request delivers: a plain name, the hash and size of its bytes, its mode."""
    return (text(name,FILE_NAME) and not text(name,LEFTOVER) and hexpin(content_sha256) and integer(size,1,MAX_FILE_BYTES)
            and type(mode) is int and mode in FILE_MODES)

def create_directory(key,path,mode,parent,host,gate,state,handles):
    """One mkdir and its proof. Returns the ledger row and leaves the held directory in handles[key]. Nothing is
    corrected: a created object that does not match is left in place and labelled. A failure after the mkdir
    succeeded is never reported as NOT_CREATED."""
    entry={'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'observed':None,
           'fsync_directory':False,'fsync_parent':False}
    if not (type(mode) is int and mode in DIRECTORY_MODES and named_in(path,parent)):
        entry['code']='DIRECTORY_REQUEST_INVALID';return entry
    name=PurePosixPath(path).name
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    try:parent.verify(gate)
    except Refused as error:
        entry['code']=code_of(error,'PARENT_REPLACED');return entry
    try:mutate(state,gate,lambda:host.mkdir(name,mode,parent.fd))
    except Refused as error:
        entry['code']=code_of(error,'GO_EXPIRED');return entry
    except OSError as error:
        entry.update(state='NOT_CREATED',errno=number(error),
                     code='DESTINATION_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
        return entry
    entry['state']='CREATED_UNVERIFIED'
    try:fd=host.open(name,flags,dir_fd=parent.fd)
    except Exception as error:
        entry.update(code='CREATED_OPEN_FAILED',errno=number(error));return entry
    try:
        handle=Pinned(host,fd,parent=parent,name=name);handles[key]=handle
        info=host.fstat(fd);named=host.lstat(name,parent.fd)
        entry['observed']=shape(info)
        if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):
            entry['code']='CREATED_NAME_REPLACED';return entry
        if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and info.st_gid==0
                and stat.S_IMODE(info.st_mode)==mode and info.st_dev==parent.identity[0]):
            entry.update(state='CREATED_METADATA_MISMATCH',code='CREATED_METADATA_MISMATCH');return entry
    except Exception as error:
        entry.update(code='CREATED_STAT_FAILED',errno=number(error));return entry
    try:entry['observed']['entries']=count_entries(host,fd,gate,MAX_DIRECTORY_ENTRIES)
    except Exception as error:
        entry.update(code='CREATED_LIST_FAILED',errno=number(error));return entry
    if entry['observed']['entries']:
        entry.update(state='CREATED_NOT_EMPTY',code='CREATED_NOT_EMPTY');return entry
    try:
        host.fsync(fd);entry['fsync_directory']=True
        host.fsync(parent.fd);entry['fsync_parent']=True
    except Exception as error:
        entry.update(state='CREATED_NOT_DURABLE',code='FSYNC_FAILED',errno=number(error));return entry
    entry['state']='CREATED_DURABLE';return entry

def readback_directory(path,mode,handle,host,gate,entries):
    """Inside the run: the path resolved again from '/' leads to the descriptor held; a directory, root:root, the
    signed mode, holding exactly the number of entries this run put in it. Returns a code, or None."""
    try:
        found=probe(host,path,gate)
        need(bool(found.get('exists')) and (found['device'],found['inode'])==handle.identity[:2] and found['type']=='dir'
             and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%mode)
             and count_entries(host,handle.fd,gate,MAX_DIRECTORY_ENTRIES)==entries,'READBACK_MISMATCH')
    except Exception as error:return code_of(error,'READBACK_UNAVAILABLE')
    return None

def remove_own_temporary(temp,fd,directory,host,gate,state,entry):
    """The single removal of the family: the temporary this run created, and only while the name still shows the
    inode of the descriptor held. Anything else at that name is left in place. Returns a code, or None; the errno of a
    failed removal goes to its own field, so the errno of the failure that led here is kept."""
    try:
        named=host.lstat(temp,directory.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino):return 'TEMPORARY_REPLACED'
        mutate(state,gate,lambda:host.unlink(temp,directory.fd))
        entry['temporary_removed']=True
    except Refused as error:return code_of(error,'GO_EXPIRED')
    except OSError as error:
        entry['temporary_removal_errno']=number(error);return 'TEMPORARY_REMOVAL_FAILED'
    try:host.fsync(directory.fd);entry['fsync_directory_after_removal']=True
    except OSError as error:
        entry['temporary_removal_errno']=number(error);return 'FSYNC_FAILED'
    return None

def create_file(index,key,path,content,mode,directory,host,gate,state,go16):
    """One file: exclusive temporary, unbuffered writes, fsync, exact metadata, link to the final name, fsync of the
    directory, removal of the temporary. Returns the ledger row. Nothing is repaired and nothing raises past here.
    The caller has set the umask so that mode survives it (0077 for 0600, 0022 for 0644) and has proved the final
    name absent; a name that appears afterwards is left alone (a link never replaces anything)."""
    entry={'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'bytes':None,
           'sha256_signed':sha(content) if type(content) is bytes else None,'sha256_observed':None,'mode_octal':None,'uid':None,'gid':None,'links':None,
           'device':None,'inode':None,'temporary_name':None,'temporary_removed':False,'temporary_removal_code':None,
           'temporary_removal_errno':None,'fsync_file':False,'fsync_directory_after_link':False,'fsync_directory_after_removal':False}
    def failed(code,error=None,**more):
        entry.update(code=code,**more)
        if error is not None:entry['errno']=number(error)
        return entry
    def withdrawn(code,error=None):
        """A failure before the final name exists (never the expiry and replaced-directory paths, which do not come
        here): the temporary of this run is withdrawn by the same gated removal as after the link, relative to the
        descriptor held, and only if the name still shows the file's descriptor. Otherwise it stays, labelled."""
        failed(code,error)
        entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
        if entry['temporary_removed']:entry['state']='NOT_CREATED'
        return entry
    if not (type(content) is bytes and 0<len(content)<=MAX_FILE_BYTES and type(mode) is int and mode in FILE_MODES
            and named_in(path,directory) and text(go16,'[0-9a-f]{16}') and integer(index,0,99)):return failed('FILE_REQUEST_INVALID')
    name=PurePosixPath(path).name;temp=entry['temporary_name']=TEMPORARY%(go16,index)
    try:directory.verify(gate)
    except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    try:fd=mutate(state,gate,lambda:host.create(temp,flags,mode,directory.fd))
    except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
    except OSError as error:
        return failed('TEMPORARY_NAME_OCCUPIED' if error.errno==errno.EEXIST else filesystem_code(error),error,state='NOT_CREATED')
    entry['state']='TEMPORARY_ONLY'
    try:
        written=0
        try:
            while written<len(content):
                size=mutate(state,gate,lambda:host.write(fd,content[written:written+65536]))
                if type(size) is not int or size<=0:return withdrawn('WRITE_INCOMPLETE')
                written+=size
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return withdrawn(filesystem_code(error),error)
        entry['bytes']=written
        try:host.fsync(fd);entry['fsync_file']=True
        except OSError as error:return withdrawn('FSYNC_FAILED',error)
        try:
            info=host.fstat(fd)
            entry.update(mode_octal='%04o'%stat.S_IMODE(info.st_mode),uid=info.st_uid,gid=info.st_gid,links=info.st_nlink,
                         device=info.st_dev,inode=info.st_ino)
            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_uid==0 and info.st_gid==0
                    and stat.S_IMODE(info.st_mode)==mode and info.st_size==len(content)
                    and info.st_dev==directory.identity[0]):return withdrawn('CREATED_METADATA_MISMATCH')
        except OSError as error:return withdrawn('CREATED_STAT_FAILED',error)
        try:directory.verify(gate)
        except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))
        # link() acts on the name, not on the descriptor held: the name is looked at again right before it. A swap
        # after this lstat is not excluded; it is caught after the link (TEMPORARY_REPLACED, in-run readback).
        try:
            gate();named=host.lstat(temp,directory.fd)
            if (named.st_dev,named.st_ino,named.st_nlink)!=(info.st_dev,info.st_ino,1):return failed('TEMPORARY_REPLACED')
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return failed('TEMPORARY_REPLACED',error)
        # Complete, fsynced bytes are the only thing that ever appears under the final name.
        try:mutate(state,gate,lambda:host.link(temp,name,directory.fd))
        except Refused as error:return failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:
            if error.errno!=errno.EEXIST:return withdrawn(filesystem_code(error),error)
            # Something took the name after the precheck. It is not touched; only this run's own temporary is withdrawn.
            failed('DESTINATION_APPEARED_AFTER_PRECHECK',error)
            entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
            if entry['temporary_removed']:entry['state']='NOT_CREATED'
            return entry
        entry['state']='LINKED_TEMPORARY_PRESENT'
        try:host.fsync(directory.fd);entry['fsync_directory_after_link']=True
        except OSError as error:return failed('FSYNC_FAILED',error)
        code=entry['temporary_removal_code']=remove_own_temporary(temp,fd,directory,host,gate,state,entry)
        if entry['temporary_removed']:entry['state']='INSTALLED_NOT_DURABLE'
        if code is not None:return failed(code,errno=entry['temporary_removal_errno'])
        try:entry['links']=host.fstat(fd).st_nlink
        except OSError as error:return failed('CREATED_STAT_FAILED',error)
        if entry['links']!=1:return failed('CREATED_METADATA_MISMATCH')
        entry['state']='INSTALLED_DURABLE';return entry
    finally:
        try:host.close(fd)
        except Exception:pass

def readback_file(entry,content,mode,directory,host,gate):
    """Inside the run: the final name opened again without following a link; the inode this run created, one link,
    root:root, the signed mode, bytes equal to the signed bytes. Returns a code, or None; the observed hash goes
    into the ledger row."""
    try:
        directory.verify(gate)
        raw,info=read_regular(host,PurePosixPath(entry['path']).name,directory.fd,gate,MAX_FILE_BYTES)
        entry['sha256_observed']=sha(raw)
        need(raw==content and (info.st_dev,info.st_ino)==(entry['device'],entry['inode']) and info.st_uid==0 and info.st_gid==0
             and stat.S_IMODE(info.st_mode)==mode and info.st_nlink==1,'READBACK_HASH_MISMATCH')
    except Exception as error:return code_of(error,'READBACK_UNAVAILABLE')
    return None

def objects_left(directories,files):
    """How many objects the ledger rows say this run left on the host (a linked file whose temporary is still present counts twice)."""
    left=sum(1 for row in directories if row['state'].startswith('CREATED'))
    left+=sum(1 for row in files if row['state'] in ('TEMPORARY_ONLY','INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'))
    return left+2*sum(1 for row in files if row['state']=='LINKED_TEMPORARY_PRESENT')
# ==== END FILES ====

# ==== BEGIN OP_K8_EVE (this operation only) ====
import base64

OPERATION='GO_WRITE_HOSTOPS02_K8_EVE_DELIVERY_01'
PHASE='WRITE_K8_EVE_DELIVERY_DAY_DOCUMENTS_AND_PAYLOAD'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K8_EVE_DELIVERY_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K8_EVE_DELIVERY_PLAN_V1'
SOURCE_NAME='k8_eve.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# E6 runs on the eve of a session, after the causal list of that session is committed (K9 note 5.7 rule 9): from 20:00Z
# of D-1 to 09:00Z of D, which is UTC day D-1 or D. The narrowest class of the core that holds 10-05 ... 10-09 is
# WRITE_SESSIONS; the eve band (A2 row E6) is the binder's and is checked again by perform (K8_EVE).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('day','windows','contract','files','days_parent','identity_rule','evidence_boot_id_sha256'))

# ---- the epoch and its five sessions; the four days that have an eve with a committed causal list (K9 note 5.5: Monday
# ---- 05/10 has no K9 list). The day before each is its eve.
K8_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K8_EVES={'2026-10-06':'2026-10-05','2026-10-07':'2026-10-06','2026-10-08':'2026-10-07','2026-10-09':'2026-10-08'}
K8_EVE_FROM='T20:00:00+00:00'            # on the eve: 17:00 BRT
K8_EVE_UNTIL='T09:00:00+00:00'           # on the day: 06:00 BRT, before D0 (07:26) and the first capacity window (07:38)
K8_PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K8_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'

# ---- the capacity tree, as the reader-and-capacity provisioning created it on 03/10 (request beb45945..., KNOWN_COMPLETE:
# ---- /var/lib/c3po-capacity and its four roots, root:root 0700, on the root filesystem) and as the reader, the compose
# ---- worker and the capacity-day writer bind it read-only at /c3po-capacity (capacity-day README, "Mounts").
K8_VAR_LIB='/var/lib'
K8_CAPACITY_NAME='c3po-capacity'
K8_CAPACITY_ROOT=K8_VAR_LIB+'/'+K8_CAPACITY_NAME
K8_CAPACITY_ROOTS=('config','documents','go','payload')
K8_IDENTITY_ROOTS=('documents','go','payload')      # the three roots whose AnchoredRoot identity every capacity config pins
K8_CONTAINER_CAPACITY='/c3po-capacity'

# ---- the K9 tree (Codex's N-8 placement, W/codex-n8-placement-20261004.txt) and what the commit step leaves in it
K8_K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
K8_K9_DAYS=K8_K9_ROOT+'/days'
K8_CAUSAL='causal'
K8_RECEIPTS='receipts'
K8_COMMITMENT='commitment.private.json'
K8_AUDIT='build_audit_receipt.json'
K8_COMMIT_RECEIPT='commit_launch.RECEIPT.json'
K8_COMMIT_OUTPUTS=('day/causal/'+K8_COMMITMENT,'day/causal/'+K8_AUDIT)
K8_STEP_RECEIPT_KEYS=frozenset(('schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at',
                                'completed_at','package_sha256','build_sha','outputs','aggregates','counts'))
K8_COMMITMENT_SCHEMA='V2_CAUSAL_LIST_COMMITMENT_V1'
K8_BUILT_EVENT='r2d2.v2.causal_list_built'
K8_AUDIT_KEYS=frozenset(('event_id','event_type','occurred_at','payload'))
K8_CAPACITY=550
K8_SYMBOL='[A-Z0-9][A-Z0-9.-]{0,19}'

# ---- the day's documents (capacity_day_documents.py, layout(); D4 = PRE_DELIVERED: the views go with the rest)
K8_CHAIN_ROLES=('CODEX','FABLE','DUDU','ACT_B','B_CODEX','B_FABLE','B_DUDU')
K8_RECORD_PINS=(('template','TEMPLATE'),('go_admission_record','GO:admission'),('go_bar_manifest_record','GO:bar_manifest'),
                ('publication_bar_manifest','PUBLICATION:bar_manifest'))
K8_GO_FILES=(('go_admission','admission'),('go_bar_manifest','bar_manifest'))
K8_CONTRACT_KEYS=frozenset(('assembler_plan','policy','order','template','owner_sha','causal_scope','consumer_plans'))
K8_WINDOW_NAME='[a-z][a-z0-9_]{0,31}'
K8_MAX_WINDOWS=3                          # a primary window and up to two contingencies (ORD:16)
K8_FILE_NAME='session=2026-10-0[6-9][.][a-z][A-Za-z0-9._-]{0,99}'
K8_CHAIN_FILE_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K8_IDENTITY_RULES=('REFUSE_ON_MISMATCH','REPORT_ONLY')

# ---- limits
K8_DELIVERY_MAX_BYTES=40960               # the contract and the twelve files; base64 of them plus the rest of the request stays below 65536
K8_RECEIPT_MAX_BYTES=262144               # the runner reads its own receipts with this limit
K8_COMMITMENT_MAX_BYTES=67108864          # MAX_CAUSAL_ENVELOPE_BYTES of r2d2_v2_causal_list.py
K8_AUDIT_MAX_BYTES=65536
K8_CHAIN_MAX_BYTES=1048576
K8_FREE_BYTES_FLOOR=4194304               # free bytes on the capacity tree's filesystem before the first creation
K8_WRITE_ALLOWANCE_SECONDS=15             # what must be left of the budget before the first creation (the writes take milliseconds)
K8_FILE_MODE=0o600
K8_DIRECTORY_MODE=0o700

def k8_layout(day,windows):
    """(key, root, name) of the signed files of one day, in creation order (six, and two per window: twelve with three
    windows); the payload file is created after them."""
    stem='session='+day
    table=[('template','documents',stem+'.template.md'),('go_admission_record','documents',stem+'.go-admission.md'),
           ('go_bar_manifest_record','documents',stem+'.go-bar_manifest.md'),('publication_bar_manifest','documents',stem+'.publication-bar_manifest.md')]
    table+=[('veto_view:'+window,'documents',stem+'.view-'+window+'.md') for window in windows]
    table+=[('go_admission','go',stem+'.admission.json'),('go_bar_manifest','go',stem+'.bar_manifest.json')]
    table+=[('capacity_config:'+window,'config',stem+'.'+window+'.capacity.json') for window in windows]
    return table
def k8_payload_name(day):return 'session='+day+'.json'
def k8_path(root,name):return K8_CAPACITY_ROOT+'/'+root+'/'+name
def k8_commit_key(day):
    """The Act B single-use key of the day's commit_launch: sha256 of the canonical [epoch, day, phase, operation]."""
    return sha(canonical([K8_EPOCH,day,'causal_list','commit_launch']))
def k8_named_in(path,directory):
    """K8's name rule for k8_create_file: a clean path whose name is one of the day's names ('session=<day>.' and a
    suffix) and whose directory, where the held parent carries signed rows, is the one the parent was walked to."""
    return (type(path) is str and clean_path(path) and text(PurePosixPath(path).name,K8_FILE_NAME)
            and (directory.rows is None or str(PurePosixPath(path).parent)==directory.rows[-1]['path']))

SCOPE_STATEMENT=('Delivers, once per session day of epoch '+K8_EPOCH+' and on its eve, after the causal list of that day is committed: into the '
                 'capacity tree '+K8_CAPACITY_ROOT+' (roots config, documents, go and payload, each a root:root 0700 directory held by descriptor) '
                 'the twelve signed files of the day (template, two GO records, publication record and one veto view per window into documents; '
                 'the admission and bar_manifest GO files into go; one capacity config per window into config), each root:root 0600 holding '
                 'exactly the bytes whose SHA-256 and size the request signs; and the payload file session=<day>.json into payload, assembled on '
                 'the host as the canonical JSON of the signed contract (the thirteenth signed file, carried whole in the payload file) and the '
                 'causal object of the commitment that the day\'s K9 commit step left in '+K8_K9_DAYS+'/<day>/causal, read by fixed path and '
                 'accepted only if its bytes are the ones the commit receipt names and its two hashes are the contract\'s causal scope. Every '
                 'name must be absent; the seven chain documents the configs pin must be in documents with their pinned bytes. Exclusive '
                 'creation, fsync and a readback of every file through descriptors inside the run. Nothing that exists is overwritten, renamed, '
                 'chmodded, chowned or removed, except the temporary of this run once its identity is proved. No symbol and no hash or size of '
                 'the payload file reaches the receipt (the commitment\'s digest is the public causal scope of the contract). No process is '
                 'started, no secret is read or written, no container is touched and nothing is activated.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K8_EPOCH,'days':sorted(K8_EVES),
       'eve':{'from':'D-1'+K8_EVE_FROM,'until':'D'+K8_EVE_UNTIL},
       'capacity_tree':{'path':K8_CAPACITY_ROOT,'roots':list(K8_CAPACITY_ROOTS),'directory_mode_octal':'%04o'%K8_DIRECTORY_MODE,
                        'container_path':K8_CONTAINER_CAPACITY,'identity_roots':list(K8_IDENTITY_ROOTS),'identity_rules':list(K8_IDENTITY_RULES)},
       'files':{'names':['session=<day>.template.md','session=<day>.go-admission.md','session=<day>.go-bar_manifest.md',
                         'session=<day>.publication-bar_manifest.md','session=<day>.view-<window>.md','session=<day>.admission.json',
                         'session=<day>.bar_manifest.json','session=<day>.<window>.capacity.json'],
                'payload':'session=<day>.json','mode_octal':'%04o'%K8_FILE_MODE,'max_windows':K8_MAX_WINDOWS,'how':FILES_SCOPE['file']['how'],
                'temporary_name':FILES_SCOPE['file']['temporary_name'],'leftover_pattern':LEFTOVER},
       'k9_inputs':{'days':K8_K9_DAYS,'commitment':K8_CAUSAL+'/'+K8_COMMITMENT,'audit_receipt':K8_CAUSAL+'/'+K8_AUDIT,
                    'commit_receipt':K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,'receipt_outputs':list(K8_COMMIT_OUTPUTS),'package_sha256':K8_PACKAGE,
                    'build_sha':K8_REVISION},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the commit receipt, the commitment and its audit receipt of the day (K9 tree)',
                             'the seven chain documents the capacity configs pin (capacity tree, documents root)',
                             'every file this run delivered (readback inside the run)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker',
                'systemctl','a shell','a network connection','a secret','activation','a container','a second attempt','a symbol in the receipt',
                'the hash or the size of the payload file in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'delivery_bytes':K8_DELIVERY_MAX_BYTES,'commit_receipt_bytes':K8_RECEIPT_MAX_BYTES,'commitment_bytes':K8_COMMITMENT_MAX_BYTES,
                 'audit_receipt_bytes':K8_AUDIT_MAX_BYTES,'chain_document_bytes':K8_CHAIN_MAX_BYTES,'payload_bytes':MAX_FILE_BYTES,
                 'free_bytes_floor':K8_FREE_BYTES_FLOOR,'write_allowance_seconds':K8_WRITE_ALLOWANCE_SECONDS,'capacity':K8_CAPACITY}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the seven creating calls. No process."""


# ---------------------------------------------------------------- the signed bytes, judged without the host (pure)
def k8_blob(item,code):
    """One signed file of the request: strict base64 of bytes whose SHA-256 and size the request signs."""
    need(type(item) is dict and set(item)=={'sha256','bytes','content_b64'},code)
    need(hexpin(item['sha256']) and integer(item['bytes'],1,MAX_FILE_BYTES) and type(item['content_b64']) is str,code)
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)
    return raw

def k8_json(raw,limit,code):
    """A JSON object in exactly its canonical bytes (the store's canonical(): sorted keys, compact, ASCII)."""
    try:value=strict(raw,limit)
    except Refused:raise Refused(code) from None
    need(type(value) is dict and canonical(value)==raw,code)
    return value

def k8_pin(value,code):
    need(type(value) is dict and set(value)=={'file','sha256'} and text(value['file'],K8_CHAIN_FILE_NAME) and hexpin(value['sha256']),code)
    return value

def k8_delivery(plan):
    """Everything the request carries about the day, decoded and judged: the thirteen signed files, their names, their
    hashes against each other (every window's config pins the day's four records and its own view, all windows pin the
    same seven chain documents and the same three roots), the contract's causal scope and the two GO files' day."""
    day=plan['day'];windows=plan['windows']
    need(day in K8_EVES,'DAY_INVALID')
    need(type(windows) is list and 1<=len(windows)<=K8_MAX_WINDOWS and all(text(name,K8_WINDOW_NAME) for name in windows)
         and len(set(windows))==len(windows),'WINDOWS_INVALID')
    layout=k8_layout(day,windows);names={key:name for key,_,name in layout}
    need(type(plan['files']) is dict and set(plan['files'])==set(names),'DELIVERY_FILES_NOT_THE_LAYOUT')
    raws={key:k8_blob(plan['files'][key],'DELIVERY_FILE_INVALID') for key,_,_ in layout}
    contract_raw=k8_blob(plan['contract'],'CONTRACT_INVALID')
    need(len(contract_raw)+sum(len(raw) for raw in raws.values())<=K8_DELIVERY_MAX_BYTES,'DELIVERY_TOO_LARGE')
    contract=k8_json(contract_raw,MAX_FILE_BYTES,'CONTRACT_INVALID')
    need(set(contract)==K8_CONTRACT_KEYS,'CONTRACT_INVALID')
    scope=contract['causal_scope']
    need(type(scope) is dict and set(scope)=={'epoch','session','commitment_sha256','list_sha256'} and scope['epoch']==K8_EPOCH
         and scope['session']==day and hexpin(scope['commitment_sha256']) and hexpin(scope['list_sha256']),'CONTRACT_NOT_OF_THIS_DAY')
    chain=None;roots=None
    for window in windows:
        config=k8_json(raws['capacity_config:'+window],MAX_FILE_BYTES,'CONFIG_INVALID')
        pins=config.get('document_pins');views=config.get('veto_views');found=config.get('roots')
        need(type(pins) is dict and set(pins)==set(K8_CHAIN_ROLES)|{label for _,label in K8_RECORD_PINS},'CONFIG_PINS_INVALID')
        this={role:k8_pin(pins[role],'CONFIG_PINS_INVALID') for role in K8_CHAIN_ROLES}
        need(chain is None or this==chain,'CONFIG_PINS_INVALID');chain=this
        for key,label in K8_RECORD_PINS:
            need(pins[label]=={'file':names[key],'sha256':sha(raws[key])},'DELIVERY_NOT_CONSISTENT')
        need(views=={day:{'file':names['veto_view:'+window],'sha256':sha(raws['veto_view:'+window])}},'DELIVERY_NOT_CONSISTENT')
        need(type(found) is dict and set(found)==set(K8_IDENTITY_ROOTS) and all(
            type(found[root]) is dict and set(found[root])=={'path','identity'} and found[root]['path']==K8_CONTAINER_CAPACITY+'/'+root
            and hexpin(found[root]['identity']) for root in K8_IDENTITY_ROOTS),'CONFIG_ROOTS_INVALID')
        need(roots is None or found==roots,'CONFIG_ROOTS_INVALID');roots=found
    for key,phase in K8_GO_FILES:
        go=k8_json(raws[key],MAX_FILE_BYTES,'GO_FILE_INVALID')
        need(set(go)=={'go'} and type(go['go']) is dict,'GO_FILE_INVALID')
        need((go['go'].get('epoch'),go['go'].get('day'),go['go'].get('phase'))==(K8_EPOCH,day,phase),'GO_FILE_NOT_OF_THIS_DAY')
    return {'layout':layout,'raws':raws,'contract_raw':contract_raw,'contract':contract,'scope':scope,'chain':chain,'roots':roots}

def k8_root_controlled(row):
    """What the K9 chain needs beyond validate_chain without an open root (uid 0 and no write bit for group or other on
    every component): group 0, and no setgid bit on any component (as K4 mode E0 required of the same chain)."""
    return row['gid']==0 and not row['mode']&stat.S_ISGID

def validate_plan(plan):
    k8_delivery(plan)
    need(plan['identity_rule'] in K8_IDENTITY_RULES,'IDENTITY_RULE_INVALID')
    validate_chain(plan['days_parent'],K8_K9_DAYS,open_root=None,receives_entry=False)
    need(all(k8_root_controlled(row) for row in plan['days_parent']),'K9_CHAIN_NOT_ROOT_CONTROLLED')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    delivery=k8_delivery(plan);day=plan['day'];scope=delivery['scope']
    return {'operation':OPERATION,'epoch':K8_EPOCH,'day':day,'eve':{'not_before':K8_EVES[day]+K8_EVE_FROM,'not_after':day+K8_EVE_UNTIL},
            'windows':list(plan['windows']),
            'capacity_tree':{'path':K8_CAPACITY_ROOT,'parent':K8_VAR_LIB,'roots':{root:K8_CAPACITY_ROOT+'/'+root for root in K8_CAPACITY_ROOTS},
                             'required':'EXISTING_DIRECTORY_NOT_A_LINK_UID_0_GID_0_MODE_0700_HELD_UNCHANGED','container_path':K8_CONTAINER_CAPACITY},
            'files':[{'key':key,'path':k8_path(root,name),'sha256':sha(delivery['raws'][key]),'bytes':len(delivery['raws'][key]),
                      'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'} for key,root,name in delivery['layout']],
            'contract':{'sha256':sha(delivery['contract_raw']),'bytes':len(delivery['contract_raw']),'written_as_its_own_file':False,
                        'carried_whole_into':k8_path('payload',k8_payload_name(day))},
            'payload':{'path':k8_path('payload',k8_payload_name(day)),'mode_octal':'%04o'%K8_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT',
                       'bytes':'CANONICAL_JSON_OF_CONTRACT_AND_CAUSAL_ASSEMBLED_ON_THE_HOST',
                       'causal_members':['commitment_sha256','epoch','list_sha256','session','status','symbols'],
                       'hash_and_size':'NOT_SIGNED_NOT_REPORTED_A_COMMITMENT_TO_THE_LIST'},
            'causal_scope':{'commitment_sha256':scope['commitment_sha256'],'list_sha256':scope['list_sha256']},
            'k9_inputs':{'days_parent':chain_effects(plan['days_parent']),'day_directory':K8_K9_DAYS+'/'+day,
                         'commit_receipt':K8_K9_DAYS+'/'+day+'/'+K8_RECEIPTS+'/'+K8_COMMIT_RECEIPT,
                         'commitment':K8_K9_DAYS+'/'+day+'/'+K8_CAUSAL+'/'+K8_COMMITMENT,'audit_receipt':K8_K9_DAYS+'/'+day+'/'+K8_CAUSAL+'/'+K8_AUDIT,
                         'commit_attempt_key':k8_commit_key(day),'required':'COMPLETE_RECEIPT_OF_THIS_STEP_NAMING_BOTH_FILES_BY_SHA256'},
            'chain_documents':{role:{'path':k8_path('documents',pin['file']),'sha256':pin['sha256'],'required':'PRESENT_ROOT_0600_THESE_BYTES'}
                               for role,pin in delivery['chain'].items()},
            'root_identities':{'rule':plan['identity_rule'],'pinned':{root:delivery['roots'][root]['identity'] for root in K8_IDENTITY_ROOTS}},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'secret_written':False,'activation':False,'container_touched':False,'process_started':False,
            'symbols_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the core's create_file for names with "=" (derived, tests/k8copy.py)
def k8_create_file(index,key,path,content,mode,directory,host,gate,state,go16):
    """The core's create_file (parts/files.py of generation 4c24c5cf...) for the capacity loader's names, which hold
    an '=' that the core's FILE_NAME refuses. Derived mechanically (tests/k8copy.py): this docstring, k8_named_in for
    named_in, and nine local names prefixed k8. Same states, codes, calls and order as the core's function."""
    k8entry={'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'bytes':None,
           'sha256_signed':sha(content) if type(content) is bytes else None,'sha256_observed':None,'mode_octal':None,'uid':None,'gid':None,'links':None,
           'device':None,'inode':None,'temporary_name':None,'temporary_removed':False,'temporary_removal_code':None,
           'temporary_removal_errno':None,'fsync_file':False,'fsync_directory_after_link':False,'fsync_directory_after_removal':False}
    def k8failed(code,error=None,**more):
        k8entry.update(code=code,**more)
        if error is not None:k8entry['errno']=number(error)
        return k8entry
    def k8withdrawn(code,error=None):
        """A failure before the final name exists (never the expiry and replaced-directory paths, which do not come
        here): the temporary of this run is k8withdrawn by the same gated removal as after the link, relative to the
        descriptor held, and only if the name still shows the file's descriptor. Otherwise it stays, labelled."""
        k8failed(code,error)
        k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
        if k8entry['temporary_removed']:k8entry['state']='NOT_CREATED'
        return k8entry
    if not (type(content) is bytes and 0<len(content)<=MAX_FILE_BYTES and type(mode) is int and mode in FILE_MODES
            and k8_named_in(path,directory) and text(go16,'[0-9a-f]{16}') and integer(index,0,99)):return k8failed('FILE_REQUEST_INVALID')
    name=PurePosixPath(path).name;k8temp=k8entry['temporary_name']=TEMPORARY%(go16,index)
    try:directory.verify(gate)
    except Refused as error:return k8failed(code_of(error,'PARENT_REPLACED'))
    k8flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    try:fd=mutate(state,gate,lambda:host.create(k8temp,k8flags,mode,directory.fd))
    except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
    except OSError as error:
        return k8failed('TEMPORARY_NAME_OCCUPIED' if error.errno==errno.EEXIST else filesystem_code(error),error,state='NOT_CREATED')
    k8entry['state']='TEMPORARY_ONLY'
    try:
        k8written=0
        try:
            while k8written<len(content):
                k8size=mutate(state,gate,lambda:host.write(fd,content[k8written:k8written+65536]))
                if type(k8size) is not int or k8size<=0:return k8withdrawn('WRITE_INCOMPLETE')
                k8written+=k8size
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return k8withdrawn(filesystem_code(error),error)
        k8entry['bytes']=k8written
        try:host.fsync(fd);k8entry['fsync_file']=True
        except OSError as error:return k8withdrawn('FSYNC_FAILED',error)
        try:
            k8info=host.fstat(fd)
            k8entry.update(mode_octal='%04o'%stat.S_IMODE(k8info.st_mode),uid=k8info.st_uid,gid=k8info.st_gid,links=k8info.st_nlink,
                         device=k8info.st_dev,inode=k8info.st_ino)
            if not (stat.S_ISREG(k8info.st_mode) and k8info.st_nlink==1 and k8info.st_uid==0 and k8info.st_gid==0
                    and stat.S_IMODE(k8info.st_mode)==mode and k8info.st_size==len(content)
                    and k8info.st_dev==directory.identity[0]):return k8withdrawn('CREATED_METADATA_MISMATCH')
        except OSError as error:return k8withdrawn('CREATED_STAT_FAILED',error)
        try:directory.verify(gate)
        except Refused as error:return k8failed(code_of(error,'PARENT_REPLACED'))
        # link() acts on the name, not on the descriptor held: the name is looked at again right before it. A swap
        # after this lstat is not excluded; it is caught after the link (TEMPORARY_REPLACED, in-run readback).
        try:
            gate();k8named=host.lstat(k8temp,directory.fd)
            if (k8named.st_dev,k8named.st_ino,k8named.st_nlink)!=(k8info.st_dev,k8info.st_ino,1):return k8failed('TEMPORARY_REPLACED')
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:return k8failed('TEMPORARY_REPLACED',error)
        # Complete, fsynced bytes are the only thing that ever appears under the final name.
        try:mutate(state,gate,lambda:host.link(k8temp,name,directory.fd))
        except Refused as error:return k8failed(code_of(error,'GO_EXPIRED'))
        except OSError as error:
            if error.errno!=errno.EEXIST:return k8withdrawn(filesystem_code(error),error)
            # Something took the name after the precheck. It is not touched; only this run's own temporary is k8withdrawn.
            k8failed('DESTINATION_APPEARED_AFTER_PRECHECK',error)
            k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
            if k8entry['temporary_removed']:k8entry['state']='NOT_CREATED'
            return k8entry
        k8entry['state']='LINKED_TEMPORARY_PRESENT'
        try:host.fsync(directory.fd);k8entry['fsync_directory_after_link']=True
        except OSError as error:return k8failed('FSYNC_FAILED',error)
        code=k8entry['temporary_removal_code']=remove_own_temporary(k8temp,fd,directory,host,gate,state,k8entry)
        if k8entry['temporary_removed']:k8entry['state']='INSTALLED_NOT_DURABLE'
        if code is not None:return k8failed(code,errno=k8entry['temporary_removal_errno'])
        try:k8entry['links']=host.fstat(fd).st_nlink
        except OSError as error:return k8failed('CREATED_STAT_FAILED',error)
        if k8entry['links']!=1:return k8failed('CREATED_METADATA_MISMATCH')
        k8entry['state']='INSTALLED_DURABLE';return k8entry
    finally:
        try:host.close(fd)
        except Exception:pass



# ---------------------------------------------------------------- the host: held directories and private files
def k8_entry(host,name,parent,gate):
    """One lstat of a plain name in a held parent; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,
            'device':info.st_dev,'inode':info.st_ino}

def k8_hold(host,name,parent,gate,codes,seen):
    """An existing directory that must be a real directory, root:root, mode 0700 exactly: looked at by lstat, opened by
    the held parent without following a link, and held; the descriptor must be the object the lstat saw. codes =
    (absent, not as required, changed between the two). Returns the Pinned child."""
    found=k8_entry(host,name,parent,gate);seen[name]=found
    need(found is not None,codes[0])
    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%K8_DIRECTORY_MODE),codes[1])
    gate()
    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    except OSError:raise Refused(codes[2]) from None
    try:held=Pinned(host,fd,parent=parent,name=name)
    except BaseException:
        host.close(fd);raise
    if held.identity!=(found['device'],found['inode'],0,0,K8_DIRECTORY_MODE):
        held.close();raise Refused(codes[2])
    return held

def k8_read(host,name,parent,gate,limit,codes,seen):
    """The bytes of an existing private file of a held directory: a regular file, root:root, mode 0600, one link, read
    by descriptor without following a link and unchanged during the read. codes = (absent, not as required)."""
    found=k8_entry(host,name,parent,gate);seen[name]=found
    need(found is not None,codes[0])
    need(found['type']=='file' and (found['uid'],found['gid'],found['mode_octal'],found['links'])==(0,0,'%04o'%K8_FILE_MODE,1),codes[1])
    raw,info=read_regular(host,name,parent.fd,gate,limit)
    need((info.st_dev,info.st_ino)==(found['device'],found['inode']) and info.st_uid==0 and info.st_gid==0
         and stat.S_IMODE(info.st_mode)==K8_FILE_MODE and info.st_nlink==1,codes[1])
    return raw

def k8_commit_outputs(raw,day):
    """The day's commit receipt (K9_STEP_RECEIPT_V1, the member set K9R and the runner use): COMPLETE, of this epoch,
    day, phase, operation and Act B key, of the pinned package and revision, naming both files of Dd/causal by hash."""
    try:receipt=strict(raw,K8_RECEIPT_MAX_BYTES)
    except Refused:raise Refused('COMMIT_RECEIPT_INVALID') from None
    need(type(receipt) is dict and set(receipt)==K8_STEP_RECEIPT_KEYS and receipt['schema']=='K9_STEP_RECEIPT_V1','COMMIT_RECEIPT_INVALID')
    need(receipt['status']=='COMPLETE' and receipt['code'] is None,'COMMIT_RECEIPT_NOT_COMPLETE')
    need((receipt['epoch'],receipt['day'],receipt['phase'],receipt['operation'],receipt['attempt_key'])==
         (K8_EPOCH,day,'causal_list','commit_launch',k8_commit_key(day)),'COMMIT_RECEIPT_NOT_OF_THIS_STEP')
    need((receipt['package_sha256'],receipt['build_sha'])==(K8_PACKAGE,K8_REVISION),'COMMIT_RECEIPT_NOT_OF_THIS_PACKAGE')
    outputs=receipt['outputs']
    need(type(outputs) is dict and all(hexpin(outputs.get(key)) for key in K8_COMMIT_OUTPUTS),'COMMIT_RECEIPT_WITHOUT_THE_COMMITMENT')
    return outputs

def k8_causal(commitment_raw,audit_raw,outputs,day,scope):
    """The causal object of the payload file, from the commitment the commit step left: its bytes and those of its audit
    receipt are the ones the commit receipt names; it is of this epoch and day; its list is a list of distinct names of
    the producer's grammar, at most the capacity, whose digest it carries; its digest and its list's digest are the
    contract's causal scope; the audit receipt is the build event of exactly this commitment. Pure."""
    need(sha(commitment_raw)==outputs[K8_COMMIT_OUTPUTS[0]] and sha(audit_raw)==outputs[K8_COMMIT_OUTPUTS[1]],'COMMITMENT_NOT_THE_COMMIT_RECEIPT_OUTPUT')
    commitment=k8_json(commitment_raw,K8_COMMITMENT_MAX_BYTES,'COMMITMENT_INVALID')
    need(commitment.get('schema')==K8_COMMITMENT_SCHEMA,'COMMITMENT_INVALID')
    need(commitment.get('epoch')==K8_EPOCH and commitment.get('session')==day,'COMMITMENT_NOT_OF_THIS_DAY')
    names=commitment.get('list')
    need(type(names) is list and len(names)<=K8_CAPACITY and all(text(name,K8_SYMBOL) for name in names) and len(set(names))==len(names),
         'COMMITMENT_LIST_INVALID')
    list_sha=sha(canonical(names));commitment_sha=sha(commitment_raw)
    need(commitment.get('list_sha256')==list_sha,'COMMITMENT_LIST_INVALID')
    need(commitment_sha==scope['commitment_sha256'],'COMMITMENT_NOT_THE_CONTRACT_SCOPE')
    need(list_sha==scope['list_sha256'],'LIST_NOT_THE_CONTRACT_SCOPE')
    audit=k8_json(audit_raw,K8_AUDIT_MAX_BYTES,'AUDIT_RECEIPT_NOT_BOUND')
    payload=audit.get('payload')
    need(set(audit)==K8_AUDIT_KEYS and audit['event_type']==K8_BUILT_EVENT and audit['occurred_at']==commitment.get('built_at')
         and type(payload) is dict and payload.get('commitment_sha256')==commitment_sha and payload.get('list_sha256')==list_sha
         and payload.get('epoch')==K8_EPOCH and payload.get('session')==day,'AUDIT_RECEIPT_NOT_BOUND')
    return {'epoch':K8_EPOCH,'session':day,'status':'AVAILABLE','symbols':names,'list_sha256':list_sha,'commitment_sha256':commitment_sha}

def k8_identity(capacity,held):
    """The AnchoredRoot identity a container computes for /c3po-capacity/<root> when the tree is bound at /c3po-capacity:
    the digest of [[name, device, inode], ...] of the components below '/', with the host's numbers (a bind mount shows
    the device and inode of its source; unverified on the host, hence the signed rule)."""
    return sha(canonical([[K8_CAPACITY_NAME,capacity.identity[0],capacity.identity[1]],[held.name,held.identity[0],held.identity[1]]]))

def k8_withheld(row):
    """The ledger row of the payload file without what would commit to the list: no hash, no size."""
    return dict(row,bytes=None,sha256_signed=None,sha256_observed=None,hash_and_size_withheld=True)

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']=len(receipt.get('parent') or [])
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    delivery=k8_delivery(plan)                                 # pure: the signed bytes that will be written, and no others
    day=plan['day'];layout=delivery['layout'];payload_name=k8_payload_name(day)
    start,end=instant(plan['window']['not_before']),instant(plan['window']['expires_at'])
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':[],'precheck':{'capacity':{},'k9':{},'chain':{},'destinations_present':[],'identities_equal':{}}}
    ledger=[];held={};pinned=[];go16=bound['go_sha256'][:16];summary={'list_empty':None}
    def finish(status,outcome,code,extra):
        rows=[k8_withheld(row) if row['key']=='payload' else row for row in ledger]
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            ledger=rows,objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            need(instant(K8_EVES[day]+K8_EVE_FROM)<=start and end<=instant(day+K8_EVE_UNTIL),'WINDOW_NOT_IN_THE_EVE_OF_THE_DAY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            days=Pinned(host,walk_pinned(host,plan['days_parent'],gate,detail['parent']),rows=plan['days_parent']);pinned.append(days)
            var_lib=Pinned(host,walk_pinned(host,plan['days_parent'][:3],gate,[]),rows=plan['days_parent'][:3]);pinned.append(var_lib)
            # the capacity tree: the root and its four roots, each root:root 0700, held to the end
            capacity=k8_hold(host,K8_CAPACITY_NAME,var_lib,gate,('CAPACITY_DIRECTORY_ABSENT','CAPACITY_DIRECTORY_NOT_PRIVATE',
                             'CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),detail['precheck']['capacity']);held['capacity']=capacity
            for root in K8_CAPACITY_ROOTS:
                held[root]=k8_hold(host,root,capacity,gate,('CAPACITY_DIRECTORY_ABSENT','CAPACITY_DIRECTORY_NOT_PRIVATE',
                                   'CAPACITY_DIRECTORY_CHANGED_DURING_PRECHECK'),detail['precheck']['capacity'])
            # the day's K9 directory and what the commit step left in it, by fixed path
            k9=('K9_DIRECTORY_ABSENT','K9_DIRECTORY_NOT_PRIVATE','K9_DIRECTORY_CHANGED_DURING_PRECHECK')
            held['day']=k8_hold(host,day,days,gate,k9,detail['precheck']['k9'])
            held['receipts']=k8_hold(host,K8_RECEIPTS,held['day'],gate,k9,detail['precheck']['k9'])
            held['causal']=k8_hold(host,K8_CAUSAL,held['day'],gate,k9,detail['precheck']['k9'])
            outputs=k8_commit_outputs(k8_read(host,K8_COMMIT_RECEIPT,held['receipts'],gate,K8_RECEIPT_MAX_BYTES,
                                              ('COMMIT_RECEIPT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9']),day)
            commitment_raw=k8_read(host,K8_COMMITMENT,held['causal'],gate,K8_COMMITMENT_MAX_BYTES,('COMMITMENT_ABSENT','K9_FILE_NOT_PRIVATE'),
                                   detail['precheck']['k9'])
            audit_raw=k8_read(host,K8_AUDIT,held['causal'],gate,K8_AUDIT_MAX_BYTES,('COMMITMENT_ABSENT','K9_FILE_NOT_PRIVATE'),detail['precheck']['k9'])
            causal=k8_causal(commitment_raw,audit_raw,outputs,day,delivery['scope'])
            summary['list_empty']=not causal['symbols']
            # at most 40960 bytes of contract and 550 names of at most 20 characters: far below MAX_FILE_BYTES, which
            # k8_create_file enforces again (FILE_REQUEST_INVALID) before anything is created
            payload=canonical({'contract':delivery['contract'],'causal':causal})
            commitment_raw=audit_raw=None
            # the seven chain documents every config pins: present in documents, private, with the pinned bytes
            for role,pin in sorted(delivery['chain'].items()):
                raw=k8_read(host,pin['file'],held['documents'],gate,K8_CHAIN_MAX_BYTES,('CHAIN_DOCUMENT_ABSENT','CHAIN_DOCUMENT_NOT_PRIVATE'),
                            detail['precheck']['chain'])
                need(sha(raw)==pin['sha256'],'CHAIN_DOCUMENT_NOT_AS_PINNED')
            # every name this run creates is absent (all looked at, then one refusal naming them)
            for key,root,name in layout+[('payload','payload',payload_name)]:
                if k8_entry(host,name,held[root],gate) is not None:detail['precheck']['destinations_present'].append(key)
            need(not detail['precheck']['destinations_present'],'DESTINATION_PRESENT')
            for root in K8_IDENTITY_ROOTS:
                detail['precheck']['identities_equal'][root]=k8_identity(capacity,held[root])==delivery['roots'][root]['identity']
            need(plan['identity_rule']=='REPORT_ONLY' or all(detail['precheck']['identities_equal'].values()),'CAPACITY_ROOT_IDENTITY_NOT_THE_CONFIG')
            free=free_bytes(host,held['payload'].fd);detail['precheck']['free_bytes']=free
            need(free>=K8_FREE_BYTES_FLOOR,'CAPACITY_FREE_SPACE_BELOW_FLOOR')
            # the last refusal that costs nothing on the host: the time the creations and the readback may take
            left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
            need(left>=K8_WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;table=[(key,root,name,delivery['raws'][key]) for key,root,name in layout]+[('payload','payload',payload_name,payload)]
        for index,(key,root,name,content) in enumerate(table):
            if stop is not None:
                ledger.append({'key':key,'path':k8_path(root,name),'state':'NOT_ATTEMPTED','code':None});continue
            row=k8_create_file(index,key,k8_path(root,name),content,K8_FILE_MODE,held[root],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        # ---- the readback inside the run: every file through a descriptor, every held directory proved again
        for (key,root,name,content),row in zip(table,ledger):
            if stop is None:stop=readback_file(row,content,K8_FILE_MODE,held[root],host,gate)
        for key in ('capacity',)+K8_CAPACITY_ROOTS+('day','causal','receipts'):
            if stop is None:
                try:held[key].verify(gate)
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        # (the two pinned chains need no walk of their own here: the capacity root's verify walks /var/lib's rows and the
        # day directory's walks the rows to days)
        delivered=None
        if stop is None:
            files={row['key']:{'path':row['path'],'sha256':row['sha256_observed'],'bytes':row['bytes'],'mode_octal':row['mode_octal'],'uid':row['uid'],
                               'gid':row['gid'],'links':row['links']} for row in ledger[:-1]}
            last=ledger[-1]
            delivered={'epoch':K8_EPOCH,'day':day,'windows':list(plan['windows']),'files':files,
                       'contract':{'sha256':sha(delivery['contract_raw']),'carried_whole_into_the_payload_file':True},
                       'payload':{'path':last['path'],'mode_octal':last['mode_octal'],'uid':last['uid'],'gid':last['gid'],'links':last['links'],
                                  'bytes_equal_the_assembled_bytes':True,'hash_and_size_withheld':True},
                       'causal':{'commitment_is_the_commit_receipt_output':True,'commitment_and_list_are_the_contract_causal_scope':True,
                                 'list_empty':summary['list_empty']},
                       'root_identities_equal_the_config':dict(detail['precheck']['identities_equal']),'identity_rule':plan['identity_rule']}
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None,'delivered':delivered}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for key in ('causal','receipts','day')+tuple(reversed(K8_CAPACITY_ROOTS))+('capacity',):
            if key in held:
                try:held[key].close()
                except Exception:pass
        for handle in pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_K8_EVE ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
