"""OP_K12_WINDOW: the capacity-day window of epoch R2D2-V2-SHADOW-2026-10-05, one signed mode per request.

LAUNCH (plan row D1): docker create and docker start of one detached container of the signed backend image, without
--rm, that runs the capacity-day writer (manifest_writer, delivered by hash into the capacity tree's config root) with
the exact arguments, binds, network and environment files of the documents tool's REQUEST for that window, which the
plan carries byte for byte, every bind source and every one of its ancestors controlled by root alone except the named read-only data
volume (its release file hashed before the create and after the start); the container
parks until its veto view. PERSIST (D3): docker logs, bounded in seconds and bytes, of the exited container identified
by ID, name and labels, with a known exit code; exactly one complete writer receipt consistent with that exit code, or
nothing is written; stored with the exit state in one private file (root:root 0600, created exclusively, fsync, read
back) in the capacity receipts directory. STOP (D4): docker stop of the parked container of that window before its
view. REMOVE (X3, Friday 09/10): docker rm, without -f or -v, of exited capacity-day containers whose private receipt
is on the host or which ended by a stop before their view. Every container is identified by its name, its two labels,
its image, its argv and its binds before anything is done to it. Everything is looked at before the first effect;
every effect is read back inside the run. This source never writes into the manifests directory, the capacity tree,
the journal or the data directory, never
reads or hashes the environment files beyond the metadata of the secret one, never prints a container's environment,
the manifest hash or the symbol count, never activates anything and never pulls an image. The caller authenticates
exact request/authority/GO/source bytes first. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba'}
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

# ==== BEGIN RUNNER (shared part, byte-identical in every source that carries it) ====
import selectors
import signal
import subprocess

# Seconds and captured bytes per class of command. Every row of an operation's COMMANDS table names one class; the
# table is carried by every signed scope. A command never runs longer than its class and never past the 60 s budget.
COMMAND_CLASSES={'QUICK':{'seconds':8,'output_bytes':65536},           # inspect, ps, info, version, systemctl show: the reviewed family's limit
                 'RENDER':{'seconds':15,'output_bytes':1048576},       # docker compose config: prints every service
                 'RUN_SHORT':{'seconds':20,'output_bytes':65536},      # an attached container that runs a short pinned snippet
                 'RUN':{'seconds':40,'output_bytes':65536},            # an attached container that imports the application
                 'RECREATE':{'seconds':30,'output_bytes':65536},       # docker compose up of one service
                 'SWITCH':{'seconds':30,'output_bytes':65536}}         # a systemctl verb that changes a unit or reloads the manager
# READ changes nothing. CONTAINER creates and removes one container that can write to no host path (read-only binds
# only). EFFECT changes the host or the engine and exists only in a source whose WRITES_ALLOWED is True.
COMMAND_KINDS=('READ','CONTAINER','EFFECT')
# Only a READ row with a fixed template is started directly. Every other row is started by the one helper that checks
# what the row is given: effect(), container_run(), and container_environment() for the row whose template is built
# at call time (its fixed words end with --format).
STARTED_THROUGH={'READ':None,'CONTAINER':'container_run','EFFECT':'effect'}
TEMPLATE_AT_CALL_TIME='container_environment'
ROW_KEYS=frozenset(('tool','argv','tail','middle','class','kind','stdin'))
# A CONTAINER or EFFECT command is not started unless its whole class time and this reserve for the readback after it
# fit in what is left of the budget: a command killed by the budget would leave its effect unknown.
AFTER_EFFECT_RESERVE_SECONDS=4
MAX_TOOL_TIMEOUTS=2
MAX_STDIN_BYTES=131072
MAX_ARGUMENTS=64
COMMAND_ENVIRONMENT={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}
COMMAND_DIRECTORY='/'
# The only variables a call may add to the fixed environment, each with the grammar of its value.
COMMAND_VARIABLES={'DOCKER_CONFIG':'/[A-Za-z0-9._/-]{1,199}','C3PO_BUILD_SHA':'[0-9a-f]{40}'}

class NotStarted(Refused):
    """Raised only while no process was created: nothing ran, so nothing can have changed."""

class NativeRunner:
    """Fixed-argv commands: absolute binary, no shell, fixed environment, working directory '/', stderr /dev/null,
    standard input /dev/null or the given bytes (written, then closed), bounded output and time. The runner of the
    reviewed family with three additions: bytes on standard input, a per-call time and output limit, and the two
    variables of COMMAND_VARIABLES. A process that cannot be created is NotStarted. The process leads a session and a
    process group of its own; a call that ends in any way but the return of the command (the time limit, the output
    limit, an expiry, an exception) kills that whole group, so nothing the command started as a process (the compose
    plugin of a docker CLI) goes on acting after the call. The container of an attached run is not a process of that
    group: the engine keeps it until its own process ends."""
    def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
        try:gate()
        except Refused as error:raise NotStarted(code_of(error,'COMMAND_NOT_STARTED')) from None
        environment=dict(COMMAND_ENVIRONMENT)
        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config
        if variables is not None:environment.update(variables)
        try:
            process=subprocess.Popen(argv,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                     stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,env=environment,cwd=COMMAND_DIRECTORY,
                                     start_new_session=True)
        except OSError:raise NotStarted('COMMAND_NOT_STARTED') from None
        output=bytearray();selector=selectors.DefaultSelector();sent=0
        try:
            until=time.monotonic()+min(seconds,gate())
            if capture:
                os.set_blocking(process.stdout.fileno(),False);selector.register(process.stdout,selectors.EVENT_READ)
            if stdin is not None:
                os.set_blocking(process.stdin.fileno(),False);selector.register(process.stdin,selectors.EVENT_WRITE)
            while selector.get_map():
                remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                for key,_ in selector.select(min(.2,remaining)):
                    if key.fileobj is process.stdin:
                        try:sent+=os.write(key.fd,stdin[sent:sent+65536])
                        except BrokenPipeError:sent=len(stdin)
                        except BlockingIOError:pass
                        if sent>=len(stdin):
                            selector.unregister(key.fileobj);process.stdin.close()
                        continue
                    block=os.read(key.fd,8192)
                    if not block:selector.unregister(key.fileobj);continue
                    output.extend(block);need(len(output)<=limit,'COMMAND_OUTPUT_LIMIT')
            while True:
                remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                try:code=process.wait(timeout=min(.2,remaining));break
                except subprocess.TimeoutExpired:pass
            gate();return code,bytes(output)
        finally:
            if process.returncode is None:
                # Not reaped yet, so the group it leads still carries its pid: the whole group, then the wait.
                try:os.killpg(process.pid,signal.SIGKILL)
                except OSError:pass
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            selector.close()
            if process.stdout is not None:process.stdout.close()
            if process.stdin is not None and not process.stdin.closed:
                try:process.stdin.close()
                except OSError:pass


def trusted_executable(host,path,check):
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    fd=host.open('/',flags)
    try:
        info=host.fstat(fd);parts=PurePosixPath(path).parts[1:]
        for index,part in enumerate(parts):
            if not (stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022):return False
            check()
            try:named=host.lstat(part,fd)
            except FileNotFoundError:return False
            if index==len(parts)-1:
                return bool(stat.S_ISREG(named.st_mode) and named.st_uid==0 and not named.st_mode&0o022 and named.st_mode&0o111)
            if not stat.S_ISDIR(named.st_mode):return False
            child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child;info=host.fstat(fd)
        return False
    finally:host.close(fd)

def binary(host,candidates,check):
    for candidate in candidates:
        if trusted_executable(host,candidate,check):return candidate
    raise Refused('BINARY_UNAVAILABLE_OR_UNSAFE')


def command_row(tool,argv,middle,klass,kind,tail=(),stdin=False):
    """One row of a COMMANDS table. A call starts: the trusted binary of tool, argv (fixed), the arguments the caller
    builds from signed values (described by middle, None when a call adds none), tail (fixed)."""
    return {'tool':tool,'argv':list(argv),'tail':list(tail),'middle':middle,'class':klass,'kind':kind,'stdin':stdin}

class Commands:
    """Starts only rows of the signed COMMANDS table. Everything it refuses before a process exists is NotStarted."""
    def __init__(self,host,gate):
        self.host,self.gate=host,gate;self.binaries={};self.timeouts={};self.calls=0
        self.started={kind:0 for kind in COMMAND_KINDS}
    def call(self,name,*middle,capture=True,docker_config=None,stdin=None,variables=None,through=None):
        row=COMMANDS[name];tool=row['tool'];limits=COMMAND_CLASSES[row['class']]
        try:
            # An EFFECT row exists only in a writing source and is started only through effect(), which counts it; a
            # CONTAINER row only through container_run(), which builds its arguments; the row that takes its template
            # at call time only through container_environment(), which builds that template; any other row directly.
            need(through==(TEMPLATE_AT_CALL_TIME if row['argv'][-1:]==['--format'] else STARTED_THROUGH[row['kind']])
                 and (row['kind']!='EFFECT' or WRITES_ALLOWED is True),'COMMAND_KIND')
            need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')
            need((row['middle'] is not None or not middle) and len(middle)<=MAX_ARGUMENTS
                 and all(type(item) is str and item and '\x00' not in item and len(item)<=8192 for item in middle),'COMMAND_ARGUMENTS')
            need((stdin is not None) is row['stdin'] and (stdin is None or (type(stdin) is bytes and 0<len(stdin)<=MAX_STDIN_BYTES)),'COMMAND_STDIN')
            need(docker_config is None or text(docker_config,COMMAND_VARIABLES['DOCKER_CONFIG']),'COMMAND_VARIABLES')
            need(variables is None or (type(variables) is dict and all(key in COMMAND_VARIABLES and key!='DOCKER_CONFIG'
                                                                       and text(value,COMMAND_VARIABLES[key]) for key,value in variables.items())),'COMMAND_VARIABLES')
            if tool not in self.binaries:
                try:self.binaries[tool]=binary(self.host,BINARIES[tool],self.gate)
                except Exception as error:self.binaries[tool]=Refused(safe(error)['code'])
            path=self.binaries[tool]
            if isinstance(path,Exception):raise Refused(str(path))
            remaining=self.gate()
            if row['kind']!='READ':need(remaining>=limits['seconds']+AFTER_EFFECT_RESERVE_SECONDS,'COMMAND_NOT_STARTED_BUDGET')
        except Refused as error:raise NotStarted(code_of(error,'COMMAND_NOT_STARTED')) from None
        self.calls+=1
        try:
            result=self.host.run([path]+list(row['argv'])+list(middle)+list(row['tail']),self.gate,limits['seconds'],capture,
                                 docker_config,stdin,variables,limits['output_bytes'])
        except NotStarted:raise
        except BaseException as error:
            self.started[row['kind']]+=1
            if isinstance(error,Refused) and str(error)=='COMMAND_TIMEOUT':self.timeouts[tool]=self.timeouts.get(tool,0)+1
            raise
        self.started[row['kind']]+=1;return result
    def output(self,name,*middle,docker_config=None,stdin=None,variables=None,through=None):
        code,raw=self.call(name,*middle,docker_config=docker_config,stdin=stdin,variables=variables,through=through)
        if code!=0:raise CommandFailed('COMMAND_FAILED',code)
        return raw

def effects_budget(*names):
    """Seconds that must be left before the FIRST effect of a run for every CONTAINER or EFFECT command named still to
    fit: the sum of their classes plus the reserve. A run that cannot fit them refuses while nothing has changed."""
    need(all(COMMANDS[name]['kind']!='READ' for name in names),'COMMAND_KIND')
    return sum(COMMAND_CLASSES[COMMANDS[name]['class']]['seconds'] for name in names)+AFTER_EFFECT_RESERVE_SECONDS

def effect(state,commands,name,*middle,capture=False,docker_config=None,stdin=None,variables=None):
    """The only way an EFFECT command is started: counted like every mutating call. Returns a dict.
      started False                 nothing ran; settled here as failed (nothing changed)
      started True, returned False  a timeout, an expiry or any failure after the process existed; settled here as
                                    unknown: the run can no longer be a refusal
      started True, returned True   the command ended with 'returncode'. NOT settled: the caller reads the result
                                    back and then calls exactly one of state.done(), state.fail() (a later read proved
                                    that nothing changed) or state.unknown(). Until it does, the call is uncertain."""
    need(COMMANDS[name]['kind']=='EFFECT','COMMAND_KIND')
    state.issue()
    try:returncode,output=commands.call(name,*middle,capture=capture,docker_config=docker_config,stdin=stdin,variables=variables,through='effect')
    except NotStarted as error:
        state.fail();return {'started':False,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_NOT_STARTED')}
    except Exception as error:
        state.unknown();return {'started':True,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_FAILED')}
    return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}
# ==== END RUNNER ====

# ==== BEGIN DOCKER (shared part, byte-identical in every source that carries it) ====
REVISION_LABEL='org.opencontainers.image.revision'
REFERENCE='[A-Za-z0-9_./:@-]{1,200}'
MAX_TAGS=8
# Same template as the reviewed read-only family: every optional key is reached through index, so it also runs in the
# CLI raw-JSON fallback (missingkey=error), the only inspect mode proven on this host.
IMAGE_FORMAT=('{"id":{{json .Id}},"repo_tags":{{json (index . "RepoTags")}},"revision":'
              '{{with index . "Config"}}{{with index . "Labels"}}{{json (index . "'+REVISION_LABEL+'")}}'
              '{{else}}null{{end}}{{else}}null{{end}}}')

def image_facts(commands,reference,docker_config=None):
    """docker image inspect of one ID or reference: local ID, tags, revision label. Nothing else is requested."""
    row=decode(commands.output('image',reference,docker_config=docker_config))
    need(set(row)=={'id','repo_tags','revision'} and text(row['id'],IMAGE_ID),'IMAGE_METADATA_INVALID')
    tags=row['repo_tags'];need(tags is None or type(tags) is list,'IMAGE_METADATA_INVALID')
    named=sorted(tag for tag in tags or [] if text(tag,REFERENCE));revision=row['revision']
    return {'id':row['id'],'repo_tags':named[:MAX_TAGS],'repo_tag_count':len(tags or []),
            'repo_tags_all_valid':len(named)==len(tags or []),'reference_among_repo_tags':reference in named,
            'revision_label':revision if revision in (None,'') or text(revision,'[0-9a-f]{40}') else None}


# ---------------------------------------------------------------- containers: metadata, never the environment's values
CONTAINER_ID='[0-9a-f]{64}'
CONTAINER_NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,127}'
CONTAINER_STATES=('created','running','paused','restarting','removing','exited','dead')
CONTAINER_KEYS=frozenset(('name','id','image_id','image_reference','running','state','started_at','host_pid','restarts','health'))
MAX_CONTAINERS=128
# The two templates of the read-only post-deploy family, byte for byte: both ran on this host.
CONTAINER_FORMAT='{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"image_reference":{{json .Config.Image}},"running":{{json .State.Running}},"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},"host_pid":{{json .State.Pid}},"restarts":{{json .RestartCount}},"health":{{if index .State "Health"}}{{json (index .State "Health" "Status")}}{{else}}null{{end}}}'
PS_FORMAT='{"id":{{json .ID}},"name":{{json .Names}},"state":{{json .State}}}'

def container_facts(commands,target,expected_name=None,docker_config=None):
    """docker container inspect of one container: identity, image, state, start instant, restart count, health.
    target is a 64-hex ID (the ID printed must be it) or a name (the name printed must be it); with expected_name the
    name printed must also be that name."""
    need(text(target,CONTAINER_NAME) and (expected_name is None or text(expected_name,CONTAINER_NAME)),'CONTAINER_TARGET')
    row=decode(commands.output('container',target,docker_config=docker_config))
    need(set(row)==set(CONTAINER_KEYS) and (row['id']==target if text(target,CONTAINER_ID) else row['name']=='/'+target)
         and (expected_name is None or row['name']=='/'+expected_name)
         and text(row['name'],'/'+CONTAINER_NAME) and text(row['id'],CONTAINER_ID) and text(row['image_id'],IMAGE_ID)
         and text(row['image_reference'],'[A-Za-z0-9_./:@-]{1,256}') and type(row['running']) is bool
         and integer(row['host_pid']) and integer(row['restarts']) and type(row['state']) is str and row['state'] in CONTAINER_STATES
         and (row['health'] is None or (type(row['health']) is str and row['health'] in ('starting','healthy','unhealthy')))
         and type(row['started_at']) is str and len(row['started_at'])<=64,'CONTAINER_METADATA_INVALID')
    return row

def container_list(commands,docker_config=None):
    """docker ps -a: every container the engine knows, as rows of (id, name, state), sorted by ID. A listing that
    fails is never an empty list."""
    rows=[]
    for line in commands.output('container_list',docker_config=docker_config).splitlines():
        if not line:continue
        row=decode(line)
        need(set(row)=={'id','name','state'} and text(row['id'],CONTAINER_ID) and text(row['name'],CONTAINER_NAME)
             and type(row['state']) is str and row['state'] in CONTAINER_STATES,'CONTAINER_LIST_INVALID')
        rows.append(row);need(len(rows)<=MAX_CONTAINERS,'CONTAINER_LIST_INVALID')
    need(len({row['id'] for row in rows})==len(rows),'CONTAINER_LIST_INVALID')
    return sorted(rows,key=lambda row:row['id'])

ENVIRONMENT_NAME='[A-Z][A-Z0-9_]{0,79}'
ENVIRONMENT_VALUE='[A-Za-z0-9_./:@+=-]{0,256}'
MAX_ENVIRONMENT_NAMES=16
def environment_format(expected):
    """A template that prints, for each signed name, whether the container's environment has it and whether its entry
    is exactly NAME=VALUE. Booleans only: no value of the environment is printed, and the values compared are the
    signed ones (paths, hashes, flags), which travel in the argv of the docker CLI; never pass a secret as expected.
    Only constructs the post-deploy family ran on this host: range over .Config.Env, split, index, eq, a variable
    declared before the range and assigned inside it, json. The text never begins with three braces."""
    need(type(expected) is dict and 0<len(expected)<=MAX_ENVIRONMENT_NAMES
         and all(text(key,ENVIRONMENT_NAME) and text(value,ENVIRONMENT_VALUE) for key,value in expected.items()),'ENVIRONMENT_EXPECTATION')
    fragments=[]
    for key in sorted(expected):
        fragments.append('{{ $p := false }}{{ $e := false }}{{ range .Config.Env }}{{ $pieces := split . "=" }}'
                         '{{ if eq (index $pieces 0) "'+key+'" }}{{ $p = true }}{{ if eq . "'+key+'='+expected[key]+'" }}{{ $e = true }}{{ end }}{{ end }}{{ end }}'
                         '"'+key+'":{"present":{{json $p}},"equal":{{json $e}}}')
    return '{{"{"}}'+','.join(fragments)+'}'

def container_environment(commands,target,expected,docker_config=None):
    """{name: {'present': bool, 'equal': bool}} for the signed names of one container (by 64-hex ID)."""
    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')
    row=decode(commands.output('container_environment',environment_format(expected),target,docker_config=docker_config,through=TEMPLATE_AT_CALL_TIME))
    need(set(row)==set(expected) and all(type(item) is dict and set(item)=={'present','equal'} and type(item['present']) is bool
                                         and type(item['equal']) is bool and (item['present'] or not item['equal']) for item in row.values()),
         'ENVIRONMENT_METADATA_INVALID')
    return row


# ---------------------------------------------------------------- one attached container run
# The argv of the supervisor README's catalog initialisation, option for option: removed on exit, standard input
# attached, never a pull, an init process, uid 0, no network, read-only root filesystem, no capability, no new privilege.
RUN_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges']
MOUNT_PATH='/[A-Za-z0-9._/-]{1,199}'
RUN_WORD='[A-Za-z0-9_./:@+=-]{1,200}'
MAX_MOUNTS=4
MAX_RUN_WORDS=16
# docker run's own exit statuses: the engine could not run the container, or the command could not be started in it.
RUN_ENGINE_STATUSES=(125,126,127)

def mount_argument(mount):
    """--mount value of one bind: type=bind,source=<host path>,target=<container path>[,readonly]."""
    need(type(mount) is dict and set(mount)=={'source','target','read_only'} and type(mount['read_only']) is bool
         and all(text(mount[key],MOUNT_PATH) and clean_path(mount[key]) for key in ('source','target')),'MOUNT_INVALID')
    return 'type=bind,source=%s,target=%s%s'%(mount['source'],mount['target'],',readonly' if mount['read_only'] else '')

def run_arguments(name,image_id,mounts,command,container_name=None):
    """What follows the row's fixed prefix: [--name N] (--mount M)* IMAGE-ID COMMAND... The image is an ID, never a
    reference. A CONTAINER row takes read-only binds only; a bind a container can write through needs an EFFECT row."""
    row=COMMANDS[name]
    need(row['tool']=='docker' and row['argv'][:2]==['run','--rm'] and row['kind'] in ('CONTAINER','EFFECT') and row['stdin'] is True,'COMMAND_KIND')
    need(text(image_id,IMAGE_ID),'IMAGE_ID')
    need(type(mounts) is list and len(mounts)<=MAX_MOUNTS,'MOUNT_INVALID')
    values=[mount_argument(mount) for mount in mounts]
    need(len({mount['target'] for mount in mounts})==len(mounts),'MOUNT_INVALID')
    need(row['kind']=='EFFECT' or all(mount['read_only'] for mount in mounts),'MOUNT_NOT_READ_ONLY')
    need(type(command) is list and 0<len(command)<=MAX_RUN_WORDS and all(text(word,RUN_WORD) for word in command)
         and not command[0].startswith('-'),'RUN_COMMAND_INVALID')
    need(container_name is None or text(container_name,'[a-z0-9][a-z0-9_.-]{0,62}'),'CONTAINER_TARGET')
    out=[] if container_name is None else ['--name',container_name]
    for value in values:out+=['--mount',value]
    return out+[image_id]+list(command)

def container_run(commands,name,image_id,mounts,command,stdin,docker_config=None,container_name=None):
    """One attached run through a CONTAINER row: the bytes on standard input, standard output captured. Returns the
    same dict as effect(): started, returned, returncode, output, code. It never raises for a failed command. A run
    that started and did not return may have left its container running: the docker CLI is killed, not the container
    (a caller that wants to say so lists the containers before and after)."""
    need(COMMANDS[name]['kind']=='CONTAINER','COMMAND_KIND')
    middle=run_arguments(name,image_id,mounts,command,container_name)
    try:returncode,output=commands.call(name,*middle,docker_config=docker_config,stdin=stdin,through='container_run')
    except NotStarted as error:return {'started':False,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_NOT_STARTED')}
    except Exception as error:return {'started':True,'returned':False,'returncode':None,'output':b'','code':code_of(error,'COMMAND_FAILED')}
    return {'started':True,'returned':True,'returncode':returncode,'output':output,'code':None}

def container_effect(state,commands,name,image_id,mounts,command,stdin,docker_config=None,container_name=None):
    """The same run through an EFFECT row (a bind the container writes through): counted by effect(), settled by the caller."""
    return effect(state,commands,name,*run_arguments(name,image_id,mounts,command,container_name),capture=True,docker_config=docker_config,stdin=stdin)

def single_line(raw):
    """The one JSON object a pinned snippet prints: exactly one line, canonical or not, no duplicate key."""
    need(type(raw) is bytes and raw.endswith(b'\n') and raw.count(b'\n')==1,'RUN_OUTPUT_NOT_ONE_LINE')
    return decode(raw[:-1])


# ---------------------------------------------------------------- docker compose: always an explicit file list
COMPOSE_PROJECT='[a-z0-9][a-z0-9_-]{0,62}'
COMPOSE_SERVICE='[a-z0-9][a-z0-9_-]{0,62}'
MAX_COMPOSE_FILES=4
COMPOSE_CONFIG_TAIL=['config','--format','json']
def compose_up_tail(service):
    """The recreate of 2026-09-28, word for word: one service, no dependency, no build, no pull."""
    need(text(service,COMPOSE_SERVICE),'COMPOSE_SERVICE')
    return ['up','-d','--no-deps','--no-build','--pull','never','--force-recreate',service]

def compose_arguments(project,env_file,files,standard_input_last=False):
    """--project-name P --env-file E -f F1 [-f F2 ...] [-f -]. The project name, the environment file and every
    compose file are named: nothing is taken from the working directory, from COMPOSE_FILE or from a default. An
    override that exists as a file is one more -f; one that is only rendered travels on standard input as the last."""
    need(text(project,COMPOSE_PROJECT),'COMPOSE_PROJECT')
    need(type(env_file) is str and clean_path(env_file) and env_file!='/' and type(files) is list and 0<len(files)<=MAX_COMPOSE_FILES
         and all(type(item) is str and clean_path(item) and item!='/' for item in files) and len(set(files))==len(files),'COMPOSE_FILES')
    out=['--project-name',project,'--env-file',env_file]
    for item in files:out+=['-f',item]
    return out+(['-f','-'] if standard_input_last else [])

def compose_render(commands,name,project,env_file,files,build_sha,override=None,docker_config=None):
    """docker compose config --format json of the explicit file list (plus the override bytes on standard input, as
    the last file, when given). Returns the decoded object. It carries every value of the environment file: nothing
    of it may reach a receipt except a boolean, or a value the caller has proved equal to a signed one."""
    row=COMMANDS[name]
    need(row['tool']=='docker' and row['argv']==['compose'] and row['tail']==COMPOSE_CONFIG_TAIL and row['kind']=='READ'
         and row['stdin'] is (override is not None),'COMMAND_KIND')
    raw=commands.output(name,*compose_arguments(project,env_file,files,override is not None),docker_config=docker_config,stdin=override,
                        variables={'C3PO_BUILD_SHA':build_sha})
    try:value=strict(raw,COMMAND_CLASSES[row['class']]['output_bytes'])
    except Refused:raise Refused('COMPOSE_RENDER_INVALID') from None
    need(type(value) is dict and type(value.get('services')) is dict,'COMPOSE_RENDER_INVALID')
    return value

def compose_service(rendered,service):
    """image and environment of one service of a render: {'image': str, 'environment': {name: str or None}}."""
    row=rendered['services'].get(service) if text(service,COMPOSE_SERVICE) else None
    need(type(row) is dict and type(row.get('image')) is str and row['image'] and type(row.get('environment',{})) is dict
         and all(type(key) is str and (value is None or type(value) is str) for key,value in row.get('environment',{}).items()),'COMPOSE_SERVICE_INVALID')
    return {'image':row['image'],'environment':dict(row.get('environment',{}))}

def compose_up(state,commands,name,project,env_file,files,build_sha,docker_config=None):
    """docker compose up of the one service the row's tail names, with the same explicit file list a render was made
    from. An EFFECT: counted by effect() and settled by the caller after it has read the containers back."""
    row=COMMANDS[name]
    need(row['tool']=='docker' and row['argv']==['compose'] and row['tail'][:1]==['up'] and row['tail']==compose_up_tail(row['tail'][-1])
         and row['stdin'] is False,'COMMAND_KIND')
    return effect(state,commands,name,*compose_arguments(project,env_file,files),capture=False,docker_config=docker_config,
                  variables={'C3PO_BUILD_SHA':build_sha})
# ==== END DOCKER ====

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

# ==== BEGIN OP_K12_WINDOW (this operation only) ====
import base64

OPERATION='GO_WRITE_HOSTOPS02_K12_WINDOW_01'
PHASE='WRITE_K12_CAPACITY_WINDOW_STEP'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K12_WINDOW_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K12_WINDOW_PLAN_V1'
SOURCE_NAME='k12_window.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# Tuesday 06/10 to Friday 09/10 hold every mode (the plan's day is one of K12_DAYS; REMOVE runs on Friday 09/10). The
# narrowest class of the core that holds those days is WRITE_SESSIONS (10-05 ... 10-10 UTC).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The signed rows of every directory this source walks come from a TREE read of k12_collect in the same boot.
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K12_COLLECT_01',)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K12_WINDOW_STEP_COMPLETE_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('mode','capacity_request','launch_request_sha256','removals','parent_rows','evidence_boot_id_sha256'))

# ---- K12 COMMON BEGIN (written by ../common_block.py; the same bytes in k12_window, k12_collect, k12_preflight) ----
# Epoch, days and the D6 clock of A2 rev3 section 7 (views 07:45:00, 08:45:00 and 09:45:00 BRT, valid 10 s; cutoff
# 10:20 BRT = 09:20 New York). The capacity days are Tuesday to Friday: A2 section 7 puts nothing of capacity on Monday.
# A window's SLOT is 1, 2 or 3 (primary, contingency 1, contingency 2): the documents tool's window_index + 1 (it counts
# from 0, capacity_day_documents.py view_schedule/enumerate). Names, views and receipts of this family use the slot.
K12_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K12_DAYS=('2026-10-06','2026-10-07','2026-10-08','2026-10-09')
K12_VIEW_UTC={1:'10:45:00',2:'11:45:00',3:'12:45:00'}
K12_CUTOFF_UTC='13:20:00'
K12_VIEW_SECONDS=10
K12_MAX_WAIT_SECONDS=900
K12_MAX_START_SECONDS=900
# Placement on the host (E2 provision of 2026-10-03, request once-e2-20261003-b; CAP README "What the host payload must
# provide"; pins.env and the docker CLI directory as A1/K4 place them). The capacity tree is bound at its top-level
# container path; the manifests directory at the same path inside; the receipts directory is never bound.
# Codex, #429 5985748037 (6): every bind source and every one of its ancestors is controlled by root alone (uid 0,
# gid 0, not writable by group or other, no setgid, no link: k12_root_chain on signed rows). ONE named exception
# (Codex, #429 5986698996, this epoch only): the legacy data volume /mnt/day-d-data (uid 1000) bound READ-ONLY at
# /app/day-d-data, exactly, to read the release M1 installed (K12_RELEASE_DIR/K12_RELEASE_FILE); its ancestors are
# root-controlled, it is a mount point, and the release directory in it is root:root 0700 (k12_data_chain). The
# release's bytes are hashed against the REQUEST's release_sha256 before every use and again after it (k12_release).
# The epoch's source root /var/lib/c3po/r2d2-v2-source-20261005 is never bound (the writer reads no source directory,
# CAP:109).
K12_CAPACITY_ROOT='/var/lib/c3po-capacity'
K12_CONFIG_ROOT=K12_CAPACITY_ROOT+'/config'
K12_CAPACITY_TARGET='/c3po-capacity'
K12_CONFIG_TARGET=K12_CAPACITY_TARGET+'/config'
K12_DATA_VOLUME='/mnt/day-d-data'
K12_DATA_TARGET='/app/day-d-data'
K12_RELEASE_DIR=K12_DATA_VOLUME+'/r2d2-v2-release-20261005'
K12_RELEASE_FILE='release.CERTIFIED.json'
K12_RELEASE_MAX_BYTES=1048576
K12_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K12_BAR_CONFIG='/etc/c3po-bar'
K12_MANIFESTS=K12_BAR_CONFIG+'/manifests'
K12_READER_CONFIG='/etc/c3po-reader'
K12_SECRET_ENV=K12_READER_CONFIG+'/secret.env'
K12_PINS_ENV=K12_READER_CONFIG+'/pins.env'
K12_DOCKER_CLI=K12_READER_CONFIG+'/docker-cli'
K12_READER_STATE='/var/lib/c3po-reader'
K12_RECEIPTS=K12_READER_STATE+'/capacity-receipts'
K12_JOURNAL_FORBIDDEN=(K12_DATA_VOLUME,K12_CAPACITY_ROOT,K12_BAR_CONFIG,K12_READER_CONFIG,K12_READER_STATE,K12_SOURCE_ROOT)
K12_WRITER_STEM='manifest_writer-'
K12_WRITER_MAX_BYTES=131072
K12_CONFIG_MAX_BYTES=65536
K12_PINS_MAX_BYTES=8192
K12_REQUEST_MAX_BYTES=16384
K12_STDOUT_MAX_BYTES=16384
K12_PERSISTED_MAX_BYTES=32768
K12_MANIFEST_MAX_BYTES=65536
# The documents tool's REQUEST of one window (capacity_day_documents.py at 4a6f767, request_document) and the writer's
# line (manifest_writer.py aeda5b12..., main/execute).
K12_CAPACITY_REQUEST_SCHEMA='R2D2_CAPACITY_DAY_ONCE_REQUEST_V1'
K12_CAPACITY_OPERATION='GO_CAPACITY_DAY_03'
K12_REQUEST_KEYS=frozenset(('schema','status','operation','epoch','day','window','window_index','window_count','phases','mode','view_mode',
                            'image_id','build_sha','release_sha256','package_sha256','capacity_config_file','capacity_config_sha256','network',
                            'mounts','env_files','inline_env','docker_config','writer_sha256','writer_argv','transport_watchdog_seconds',
                            'not_before','latest_start','not_after','view_opens_at','view_valid_until','cutoff_at','documentary',
                            'authority_sha256','host_binding_sha256','executor_uid'))
K12_DOCUMENTARY_KEYS=frozenset(('act_b_sha256','template_record_sha256','template_sha256','admission_go_sha256','admission_go_record_sha256',
                                'bar_manifest_go_sha256','bar_manifest_go_record_sha256','publication_sha256','veto_view_sha256',
                                'contract_sha256','causal_commitment_sha256','causal_list_sha256'))
K12_WRITER_SCHEMA='R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1'
K12_WRITER_STATUSES={'PUBLISHED_VERIFIED':(0,),'ALREADY_PUBLISHED_VERIFIED':(0,),'MATCH_VERIFIED':(0,),'PREFLIGHT_OK':(0,),
                     'ABSENT':(3,),'REFUSED':(3,),'UNVERIFIED':(1,),'PUBLISHED_UNVERIFIED':(1,3)}
K12_WRITER_PUBLISHED=('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED')
K12_WRITER_KEYS=frozenset(('schema','status','code','session','mode','epoch','owner_uid','release_sha256','capacity_config_sha256',
                           'package_sha256','build_sha','capacity_veto_mode','massive_bars_enabled','cutoff_at','stale_temporaries',
                           'repaired_temporaries','prepare_status','waited_seconds','view','go_sha256','go_mode','template_sha256','window',
                           'binding_sha256','symbol_count','manifest_sha256','published_at','file','checks','windows'))
K12_PREPARE_STATUSES=('ATTEMPTED','COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')
K12_COMMITTED=('COMMITTED','ALREADY_COMMITTED','PRECOMMITTED')
K12_WRITER_CODE='[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+'
K12_INSTANT='[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+]00:00'
# The container: deterministic names, two labels, and the one inspect format of the family (never .Config.Env).
K12_LABEL_REQUEST='c3po.k12.request_sha256'
K12_LABEL_CAPACITY='c3po.k12.capacity_request_sha256'
K12_PERSISTED_SCHEMA='K12_PERSISTED_WRITER_RECEIPT_V1'
K12_PERSISTED_KEYS=frozenset(('schema','epoch','day','window','window_slot','container_id','container_name','launch_request_sha256',
                              'capacity_request_sha256','persist_request_sha256','image_id','exit_code','oom_killed','started_at',
                              'finished_at','stdout_b64','stdout_sha256','stdout_bytes'))
K12_FORMAT=('{"id":{{json .Id}},"name":{{json .Name}},"image_id":{{json .Image}},"state":{{json .State.Status}},'
            '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
            '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
            '"request_label":{{json (index .Config.Labels "'+K12_LABEL_REQUEST+'")}},'
            '"capacity_label":{{json (index .Config.Labels "'+K12_LABEL_CAPACITY+'")}},'
            '"cmd":{{json .Config.Cmd}},"network_mode":{{json .HostConfig.NetworkMode}},"read_only_root":{{json .HostConfig.ReadonlyRootfs}},'
            '"auto_remove":{{json .HostConfig.AutoRemove}},"restart_policy":{{json .HostConfig.RestartPolicy.Name}},"mounts":{{json .Mounts}}}')
K12_INSPECT_KEYS=frozenset(('id','name','image_id','state','running','exit_code','oom_killed','started_at','finished_at','request_label',
                            'capacity_label','cmd','network_mode','read_only_root','auto_remove','restart_policy','mounts'))
K12_MOUNT_KEYS=frozenset(('Type','Name','Source','Destination','Driver','Mode','RW','Propagation'))
K12_NEVER_STARTED='0001-01-01T00:00:00Z'

def k12_compact(day):return day.replace('-','')
def k12_container_name(day,index):return 'c3po-k12-%s-w%d'%(k12_compact(day),index)
def k12_preflight_name(day):return 'c3po-k12-%s-preflight'%k12_compact(day)
def k12_persisted_name(day,index):return 'k12-%s-w%d.writer.json'%(day,index)
def k12_writer_name(digest):return K12_WRITER_STEM+digest+'.py'
def k12_at(day,clock):return '%sT%s+00:00'%(day,clock)

def k12_instant(value):
    """One instant of the REQUEST: exactly YYYY-MM-DDTHH:MM:SS+00:00 (what the documents tool writes)."""
    need(text(value,K12_INSTANT),'CAPACITY_REQUEST_INSTANT');return instant(value)

def k12_journal(mount):
    """The journal bind: a read-only bind of a host directory that is none of the others, contains none and lies in
    none of them, at a container path that is one component below '/' (CAP README, "The journal bind")."""
    source,target=mount['source'],mount['target']
    need(clean_path(source) and source!='/' and not any(inside(source,root) or inside(root,source) for root in K12_JOURNAL_FORBIDDEN)
         and text(target,'/[a-z0-9][a-z0-9._-]{0,62}') and target not in (K12_DATA_TARGET,K12_CAPACITY_TARGET,K12_MANIFESTS,'/app','/etc')
         and mount['readonly'] is True,'CAPACITY_REQUEST_JOURNAL')
    return {'source':source,'target':target}

def k12_data(mount):
    """The data bind (CAP:109, the release file read by the collector of --prepare-first): exactly the named exception,
    /mnt/day-d-data at /app/day-d-data, read-only (Codex #429 5986698996). Anything else is refused."""
    need(mount=={'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'readonly':True},'CAPACITY_REQUEST_DATA_BIND')
    return {'source':K12_DATA_VOLUME,'target':K12_DATA_TARGET}

def k12_data_chain(rows):
    """Signed rows from '/' to the release directory in the data volume: every component outside the volume root
    controlled by root alone (uid 0 and no group or other write by validate_chain; gid 0 and no setgid here); the volume root may be another uid
    (the named exception) but not world-writable; the volume is a mount point; the release directory root:root 0700."""
    validate_chain(rows,K12_RELEASE_DIR,open_root=K12_DATA_VOLUME)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows if not inside(row['path'],K12_DATA_VOLUME)),
         'CHAIN_NOT_ROOT_CONTROLLED')
    need(mount_point_of(rows)==K12_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,0o700),'RELEASE_DIRECTORY_NOT_ROOT_PRIVATE')
    return rows

def k12_release(host,held,gate,derived):
    """The release M1 installed, opened without following a link and hashed over the bytes read: root 0600 one link,
    SHA-256 = the REQUEST's release_sha256. Raises Refused. The bytes stay here."""
    raw,facts=k12_file(host,K12_RELEASE_FILE,held,gate,K12_RELEASE_MAX_BYTES)
    need(raw is not None,'RELEASE_ABSENT');need(k12_private(facts),'RELEASE_NOT_PRIVATE')
    need(sha(raw)==derived['release_sha256'],'RELEASE_NOT_THE_SIGNED_BYTES')
    return True

def k12_root_chain(rows,path):
    """Signed rows of a directory whose every component from '/' is controlled by root alone: uid 0 and not writable
    by group or other (validate_chain with no open root), and gid 0 and no setgid bit on every component (Codex 6).
    A link anywhere is refused by the walk itself (O_NOFOLLOW by dir_fd). Returns the rows."""
    validate_chain(rows,path)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')
    return rows

def k12_capacity_request(member):
    """The member {'b64','sha256'} of a plan: the documents tool's REQUEST of one window, carried byte for byte. Every
    value this family puts on the engine is derived here and nowhere else. Pure; raises Refused."""
    need(type(member) is dict and set(member)=={'b64','sha256'} and type(member['b64']) is str and hexpin(member['sha256']),'CAPACITY_REQUEST_INVALID')
    try:raw=base64.b64decode(member['b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('CAPACITY_REQUEST_INVALID') from None
    need(0<len(raw)<=K12_REQUEST_MAX_BYTES and sha(raw)==member['sha256'],'CAPACITY_REQUEST_NOT_THE_SIGNED_BYTES')
    try:request=document(raw)
    except Refused:raise Refused('CAPACITY_REQUEST_INVALID') from None
    exact(request,K12_REQUEST_KEYS,'CAPACITY_REQUEST_KEYS')
    need(request['schema']==K12_CAPACITY_REQUEST_SCHEMA and request['status']=='BOUND' and request['operation']==K12_CAPACITY_OPERATION
         and request['epoch']==K12_EPOCH and type(request['executor_uid']) is int and request['executor_uid']==0,'CAPACITY_REQUEST_IDENTITY')
    day=request['day'];need(type(day) is str and day in K12_DAYS,'CAPACITY_REQUEST_DAY')
    position,count=request['window_index'],request['window_count']
    need(text(request['window'],'[a-z][a-z0-9_]{0,31}') and integer(position,0,2) and integer(count,1,3) and position<count,'CAPACITY_REQUEST_WINDOW')
    index=position+1
    need(request['phases']==['admission','bar_manifest'] and request['mode']=='PREPARE_AND_PUBLISH'
         and request['view_mode'] in ('PRE_DELIVERED','IN_WINDOW'),'CAPACITY_REQUEST_MODE')
    need(text(request['image_id'],IMAGE_ID) and text(request['build_sha'],'[0-9a-f]{40}') and hexpin(request['release_sha256'])
         and hexpin(request['package_sha256']) and hexpin(request['capacity_config_sha256']) and hexpin(request['writer_sha256'])
         and hexpin(request['authority_sha256']) and hexpin(request['host_binding_sha256']),'CAPACITY_REQUEST_PINS')
    config='session=%s.%s.capacity.json'%(day,request['window'])
    need(request['capacity_config_file']==K12_CONFIG_TARGET+'/'+config,'CAPACITY_REQUEST_CONFIG_FILE')
    need(text(request['network'],'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}') and request['network'] not in ('host','none','bridge','default'),
         'CAPACITY_REQUEST_NETWORK')
    files=request['env_files']
    need(type(files) is dict and set(files)=={'secret_path','pins'} and files['secret_path']==K12_SECRET_ENV and type(files['pins']) is dict
         and set(files['pins'])=={'path','sha256'} and files['pins']['path']==K12_PINS_ENV and hexpin(files['pins']['sha256']),'CAPACITY_REQUEST_ENV_FILES')
    need(request['inline_env']=={'C3PO_R2D2_V2_SHADOW_ENABLED':'true','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED':'true',
                                 'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE':request['capacity_config_file'],
                                 'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':request['capacity_config_sha256']},'CAPACITY_REQUEST_INLINE_ENV')
    need(request['docker_config']==K12_DOCKER_CLI,'CAPACITY_REQUEST_DOCKER_CONFIG')
    mounts=request['mounts']
    need(type(mounts) is list and len(mounts)==4 and all(type(item) is dict and set(item)=={'source','target','readonly'}
                                                        and type(item['readonly']) is bool for item in mounts),'CAPACITY_REQUEST_MOUNTS')
    fixed=[{'source':K12_CAPACITY_ROOT,'target':K12_CAPACITY_TARGET,'readonly':True},{'source':K12_MANIFESTS,'target':K12_MANIFESTS,'readonly':False}]
    others=[item for item in mounts if item not in fixed]
    datas=[item for item in others if item['target']==K12_DATA_TARGET];journals=[item for item in others if item['target']!=K12_DATA_TARGET]
    need(all(item in mounts for item in fixed) and len(datas)==1 and len(journals)==1,'CAPACITY_REQUEST_MOUNTS')
    k12_data(datas[0]);journal=k12_journal(journals[0])     # the journal lies neither in nor around the volume
    view=k12_at(day,K12_VIEW_UTC[index]);until=instant(view).timestamp()+K12_VIEW_SECONDS
    starts=k12_instant(request['not_before'])
    for key in ('latest_start','not_after','view_opens_at','view_valid_until','cutoff_at'):k12_instant(request[key])
    need(request['view_opens_at']==view and request['latest_start']==view and k12_instant(request['view_valid_until']).timestamp()==until
         and request['not_after']==request['view_valid_until'] and request['cutoff_at']==k12_at(day,K12_CUTOFF_UTC)
         and starts.date().isoformat()==day,'CAPACITY_REQUEST_CLOCK')
    given=request['writer_argv'];mode=None
    need(type(given) is list and len(given) in (9,11) and type(given[8]) is str and text(given[8],'[1-9][0-9]{0,2}')
         and int(given[8])<=K12_MAX_WAIT_SECONDS,'CAPACITY_REQUEST_WRITER_ARGV')
    wait=int(given[8])
    need(0<instant(view).timestamp()-starts.timestamp()<=min(wait,K12_MAX_START_SECONDS),'CAPACITY_REQUEST_CLOCK')
    argv=['--day',day,'--manifest-directory',K12_MANIFESTS,'--prepare-first','--view-opens-at',view,'--max-wait-seconds',str(wait)]
    if len(given)==11:mode=given[10];argv+=['--require-go-mode',mode]
    need(given==argv and mode in (None,'DELEGATED_ACT_B'),'CAPACITY_REQUEST_WRITER_ARGV')
    need(integer(request['transport_watchdog_seconds'],1,3600),'CAPACITY_REQUEST_WATCHDOG')
    documentary=request['documentary']
    need(type(documentary) is dict and set(documentary)==set(K12_DOCUMENTARY_KEYS) and all(hexpin(value) for value in documentary.values()),
         'CAPACITY_REQUEST_DOCUMENTARY')
    return raw,request,{'sha256':member['sha256'],'day':day,'window':request['window'],'index':index,'position':position,'count':count,'image_id':request['image_id'],
                        'build_sha':request['build_sha'],'network':request['network'],'mounts':[dict(item) for item in mounts],'journal':journal,
                        'config_name':config,'config_sha256':request['capacity_config_sha256'],'pins_sha256':files['pins']['sha256'],
                        'writer_sha256':request['writer_sha256'],'writer_argv':list(argv),'require_go_mode':mode,'not_before':request['not_before'],
                        'view_opens_at':view,'view_valid_until':request['view_valid_until'],'cutoff_at':request['cutoff_at'],
                        'release_sha256':request['release_sha256'],'package_sha256':request['package_sha256']}

def k12_mount_word(item):
    """--mount value of one bind of the REQUEST (the core's own grammar and form)."""
    return mount_argument({'source':item['source'],'target':item['target'],'read_only':item['readonly']})

def k12_container_words(derived,name,labels):
    """What follows a create or run row's fixed prefix: --name, the labels, --network, the two env files (the docker
    CLI reads them on the host; they are never mounted, opened or hashed here), the four inline values, the four binds
    in the REQUEST's order, the image ID, and the writer by its content-addressed path in the config root, with the
    REQUEST's argv. Every word is a value of the signed REQUEST or a compiled constant."""
    words=['--name',name]
    for key,value in labels:words+=['--label','%s=%s'%(key,value)]
    words+=['--network',derived['network'],'--env-file',K12_SECRET_ENV,'--env-file',K12_PINS_ENV,
            '--env','C3PO_R2D2_V2_SHADOW_ENABLED=true','--env','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true',
            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE='+K12_CONFIG_TARGET+'/'+derived['config_name'],
            '--env','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+derived['config_sha256']]
    for item in derived['mounts']:words+=['--mount',k12_mount_word(item)]
    return words+[derived['image_id'],'python','-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+list(derived['writer_argv'])

def k12_expected_mounts(derived):
    """The mount list a container of this family must show in `docker inspect` (Type bind, RW the opposite of readonly)."""
    return sorted([{'source':item['source'],'destination':item['target'],'rw':not item['readonly']} for item in derived['mounts']],
                  key=lambda item:item['destination'])

def k12_inspect(raw):
    """One line of K12_FORMAT, member by member. Raises Refused('K12_INSPECT_INVALID')."""
    row=decode(raw)
    need(set(row)==set(K12_INSPECT_KEYS) and text(row['id'],CONTAINER_ID) and text(row['name'],'/'+CONTAINER_NAME) and text(row['image_id'],IMAGE_ID)
         and type(row['state']) is str and row['state'] in CONTAINER_STATES and type(row['running']) is bool and type(row['exit_code']) is int
         and type(row['oom_killed']) is bool and all(type(row[key]) is str and len(row[key])<=64 for key in ('started_at','finished_at'))
         and all(row[key] in (None,'') or hexpin(row[key]) for key in ('request_label','capacity_label'))
         and type(row['cmd']) is list and len(row['cmd'])<=64 and all(type(word) is str and len(word)<=8192 for word in row['cmd'])
         and type(row['network_mode']) is str and len(row['network_mode'])<=128 and type(row['read_only_root']) is bool
         and type(row['auto_remove']) is bool and type(row['restart_policy']) is str and len(row['restart_policy'])<=32
         and type(row['mounts']) is list and len(row['mounts'])<=16,'K12_INSPECT_INVALID')
    mounts=[]
    for item in row['mounts']:
        need(type(item) is dict and set(item)<=K12_MOUNT_KEYS and item.get('Type')=='bind' and type(item.get('Source')) is str
             and type(item.get('Destination')) is str and type(item.get('RW')) is bool,'K12_INSPECT_INVALID')
        mounts.append({'source':item['Source'],'destination':item['Destination'],'rw':item['RW']})
    row['mounts']=sorted(mounts,key=lambda item:item['destination']);return row

def k12_ours(row,derived,name,request_sha256):
    """True when the inspected container is the one this family created for that window and launch request: name,
    image, the two labels, the writer's argv and the binds of the REQUEST, the network, a read-only root, no --rm and
    no restart policy. A container that is not ours is never stopped, read for its output or removed."""
    return (row['name']=='/'+name and row['image_id']==derived['image_id'] and row['request_label']==request_sha256
            and row['capacity_label']==derived['sha256'] and row['network_mode']==derived['network'] and row['read_only_root'] is True
            and row['auto_remove'] is False and row['restart_policy'] in ('no','') and row['mounts']==k12_expected_mounts(derived)
            and row['cmd']==['python','-I','-B',K12_CONFIG_TARGET+'/'+k12_writer_name(derived['writer_sha256'])]+derived['writer_argv'])

def k12_writer_line(raw,day):
    """The writer's one line (README "Receipt"): exactly one JSON object on one line, its schema, a known status with its
    code, the session, and the type of every member this family copies or compares. Returns the object. Raises Refused."""
    need(type(raw) is bytes and 0<len(raw)<=K12_STDOUT_MAX_BYTES and raw.endswith(b'\n') and raw.count(b'\n')==1,'WRITER_LINE_NOT_ONE_LINE')
    try:raw.decode('ascii')
    except UnicodeDecodeError:raise Refused('WRITER_LINE_NOT_ASCII') from None
    try:line=strict(raw[:-1],K12_STDOUT_MAX_BYTES)
    except Refused:raise Refused('WRITER_LINE_INVALID') from None
    need(type(line) is dict and set(line)<=K12_WRITER_KEYS and {'schema','status','code','session','mode'}<=set(line)
         and line['schema']==K12_WRITER_SCHEMA and line['status'] in K12_WRITER_STATUSES,'WRITER_LINE_INVALID')
    need((line['code'] is None)==(line['status'] in ('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED','MATCH_VERIFIED','PREFLIGHT_OK'))
         and (line['code'] is None or text(line['code'],K12_WRITER_CODE)),'WRITER_LINE_INVALID')
    need(line['session'] in (day,None) and line['mode'] in (None,'PUBLISH','VERIFY_ONLY','PREFLIGHT'),'WRITER_LINE_INVALID')
    for key in ('release_sha256','capacity_config_sha256','package_sha256','go_sha256','template_sha256','binding_sha256','manifest_sha256'):
        need(key not in line or hexpin(line[key]),'WRITER_LINE_INVALID')
    need(('owner_uid' not in line or integer(line['owner_uid'])) and ('build_sha' not in line or text(line['build_sha'],'[0-9a-f]{40}'))
         and ('prepare_status' not in line or line['prepare_status'] in K12_PREPARE_STATUSES)
         and ('go_mode' not in line or line['go_mode'] in ('DELEGATED_ACT_B','INDIVIDUAL'))
         and ('symbol_count' not in line or integer(line['symbol_count'],0,550))
         and all(key not in line or integer(line[key],0,4096) for key in ('stale_temporaries','repaired_temporaries'))
         and ('massive_bars_enabled' not in line or type(line['massive_bars_enabled']) is bool)
         and ('capacity_veto_mode' not in line or text(line['capacity_veto_mode'],'[A-Z][A-Z0-9_]{0,63}'))
         and ('waited_seconds' not in line or (type(line['waited_seconds']) in (int,float) and 0<=line['waited_seconds']<=1000))
         and all(key not in line or text(line[key],'[0-9T:.+-]{10,40}') for key in ('cutoff_at','published_at'))
         and all(key not in line or type(line[key]) is dict for key in ('view','window','file','checks','windows')),'WRITER_LINE_INVALID')
    return line

def k12_line_public(line):
    """What of the writer's line may leave the host (CAP README, "Private and public"): status, code, binding hash,
    prepare status, the GO it verified, the pins it loaded, counts of temporaries, clocks. Never the manifest hash or
    the symbol count (together an unsalted commitment to the list): only whether they were present."""
    keep=('status','code','session','mode','owner_uid','prepare_status','binding_sha256','go_sha256','go_mode','template_sha256',
          'release_sha256','capacity_config_sha256','package_sha256','build_sha','capacity_veto_mode','massive_bars_enabled',
          'stale_temporaries','repaired_temporaries','waited_seconds','published_at','cutoff_at')
    public={key:line[key] for key in keep if key in line}
    public.update(manifest_sha256_present='manifest_sha256' in line,symbol_count_present='symbol_count' in line)
    return public

def k12_persisted(raw,expected):
    """The persisted writer receipt (written by k12_window PERSIST): canonical JSON with exactly K12_PERSISTED_KEYS, its
    members equal to the expected ones, and the standard output it carries equal to its own hash and size. Returns
    (document, stdout bytes). Raises Refused('PERSISTED_RECEIPT_INVALID')."""
    try:value=document(raw)
    except Refused:raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(set(value)==set(K12_PERSISTED_KEYS) and value['schema']==K12_PERSISTED_SCHEMA
         and all(value[key]==expected[key] for key in expected),'PERSISTED_RECEIPT_INVALID')
    need(type(value['stdout_b64']) is str and hexpin(value['stdout_sha256']) and integer(value['stdout_bytes'],0,K12_STDOUT_MAX_BYTES)
         and type(value['exit_code']) is int and type(value['oom_killed']) is bool and text(value['container_id'],CONTAINER_ID)
         and hexpin(value['persist_request_sha256']),'PERSISTED_RECEIPT_INVALID')
    try:stdout=base64.b64decode(value['stdout_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('PERSISTED_RECEIPT_INVALID') from None
    need(len(stdout)==value['stdout_bytes'] and sha(stdout)==value['stdout_sha256'],'PERSISTED_RECEIPT_INVALID')
    return value,stdout

def k12_entry(host,name,parent,gate):
    """One lstat of a plain name in a held directory; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}

def k12_file(host,name,parent,gate,limit):
    """(bytes, metadata) of one regular file of a held directory read without following a link, or (None, None) when
    the name does not exist. The bytes stay with the caller."""
    try:raw,info=read_regular(host,name,parent.fd,gate,limit)
    except FileNotFoundError:return None,None
    return raw,{'type':'file','uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}

def k12_private(facts):
    """A regular file of root:root, mode 0600, one link."""
    return facts is not None and facts['type']=='file' and (facts['uid'],facts['gid'],facts['mode_octal'],facts['links'])==(0,0,'0600',1)

def k12_line_of(value,stdout,day):
    """The writer's line from a persisted receipt, or (None, code) when it is not one valid line."""
    try:return k12_writer_line(stdout,day),None
    except Refused as error:return None,code_of(error,'WRITER_LINE_INVALID')

def k12_stopped(exit_code,oom_killed,finished,view):
    """The end of D4's stop (a veto): exit 143 or 137 (the signal of docker stop through docker-init), not OOM,
    finished before the view (the writer prints its line only at its own end, after the view)."""
    finished=finished if type(finished) is str else ''
    return (exit_code in (137,143) and oom_killed is False and text(finished[:19],'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}')
            and finished[:19]<view[:19])

def k12_receipt_line(stdout,day,exit_code):
    """PERSIST's strict reading of the logs (Codex 2): exactly one complete writer receipt, consistent with the exit code
    of the container (README status table), of this session and of a publish run. Raises Refused; truncated,
    duplicated or inconsistent output is never a receipt."""
    line=k12_writer_line(stdout,day)
    need(type(exit_code) is int and exit_code in K12_WRITER_STATUSES[line['status']] and line['session']==day and line['mode']=='PUBLISH',
         'WRITER_RECEIPT_INCONSISTENT')
    return line

def k12_ended(value,stdout,day,view):
    """How a window's container ended, from its persisted receipt: ('LINE', line) for one complete receipt consistent
    with the exit code (k12_receipt_line); ('STOPPED', None) for no output at all and the signature of D4's stop
    (k12_stopped), a veto, which holds for the whole day (ORD:17); ('UNKNOWN', code) for anything else: never a ground
    for another window. (PERSIST stores nothing but a complete receipt; the other cases are kept for a file that is
    not what PERSIST wrote.)"""
    try:return 'LINE',k12_receipt_line(stdout,day,value['exit_code'])
    except Refused as error:code=code_of(error,'WRITER_LINE_INVALID')
    if stdout==b'' and k12_stopped(value['exit_code'],value['oom_killed'],value['finished_at'],view):return 'STOPPED',None
    return 'UNKNOWN','ENDED_WITHOUT_A_LINE' if stdout==b'' else code

def k12_terminal(line):
    """'PUBLISHED' when the window published and verified (README outcome rule), 'EMPTY_LIST' for the empty monitored
    list with a committed binding (terminal for the day, D12), None otherwise. Its line is always one complete receipt
    of this day's publish run (k12_receipt_line), so neither None nor another mode reaches it."""
    if line['status'] in K12_WRITER_PUBLISHED:return 'PUBLISHED'
    if line['code']=='MANIFEST_SYMBOLS_EMPTY' and line.get('prepare_status') in K12_COMMITTED:return 'EMPTY_LIST'
    return None
# ---- K12 COMMON END ----

W_MODES=('LAUNCH','PERSIST','STOP','REMOVE')
# Which held directories each mode walks from "/" against signed rows, and the path of each.
# The journal's and the data bind's paths are the REQUEST's (w_path). Every chain is root-controlled (k12_root_chain).
W_PATHS={'config':K12_CONFIG_ROOT,'manifests':K12_MANIFESTS,'reader_config':K12_READER_CONFIG,'docker_cli':K12_DOCKER_CLI,
         'receipts':K12_RECEIPTS,'data':K12_RELEASE_DIR}
W_PRIVATE=('config','manifests','reader_config','docker_cli','journal','receipts')   # leaf root:root 0700
W_CHAINS={'LAUNCH':('config','manifests','reader_config','docker_cli','journal','data','receipts'),
          'PERSIST':('receipts',),'STOP':('manifests',),'REMOVE':('receipts',)}
W_LAUNCH_LEAD_SECONDS=45                  # LAUNCH: the view must still be this far when the container is created
W_STOP_LEAD_SECONDS=25                    # STOP: the stop must start this long before the view (its class is 20 s)
W_PERSIST_AFTER_VIEW_SECONDS=60           # PERSIST: not before the view + 60 s (MASTER_PLAN D2: "view + 60 s")
W_REMOVE_DAY='2026-10-09'
W_REMOVE_NOT_BEFORE='20:00:00'            # Friday after the close (17:00 BRT)
W_ALLOWANCE_SECONDS=4                     # STOP, REMOVE: one effect, nothing between effects
W_ALLOWANCE_LAUNCH_SECONDS=10             # LAUNCH: one inspect (QUICK, 8 s) between create and start, and 2 s
W_ALLOWANCE_PERSIST_SECONDS=12            # PERSIST: one inspect (8 s) after the logs, and the file (4 s)
W_MAX_REMOVALS=12                         # four days of three windows
W_STOP_SECONDS='5'
K12_CREATE_PREFIX=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                   '--restart','no']
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'inspect':command_row('docker',['container','inspect','--format',K12_FORMAT],'one container name of this family or one 64-hex ID','QUICK','READ'),
          'create':command_row('docker',K12_CREATE_PREFIX,'--name, two --label, --network, two --env-file, four --env, the four --mount of the '
                               'signed REQUEST, the signed image ID, python -I -B <the writer in the config root> and the REQUEST\'s writer argv',
                               'QUICK','EFFECT'),
          'start':command_row('docker',['start'],'exactly the 64-hex ID that create printed','RUN_SHORT','EFFECT'),
          'stop':command_row('docker',['stop','-t',W_STOP_SECONDS],'exactly one 64-hex ID: the running container of that window, identified',
                             'RUN_SHORT','EFFECT'),
          'logs':command_row('docker',['logs'],'exactly one 64-hex ID: the exited container of that window, identified (standard output only; '
                             'the container\'s standard error goes to /dev/null with the CLI\'s)','QUICK','EFFECT'),
          'remove':command_row('docker',['rm'],'1 to 12 64-hex IDs: exited or never-started containers of this family, each identified and with '
                               'its private receipt on the host when it ran','QUICK','EFFECT')}

SCOPE_STATEMENT=('The capacity-day window of epoch '+K12_EPOCH+', one signed mode per request. LAUNCH: docker create (no --rm, --restart no, '
                 '--pull never, --init, --user 0:0, --read-only, --cap-drop ALL, no-new-privileges) and docker start of one container named '
                 'c3po-k12-<yyyymmdd>-w<index>, labelled with this request and with the documents tool REQUEST it carries byte for byte, '
                 'running python -I -B on the writer delivered by hash in '+K12_CONFIG_ROOT+' with that REQUEST\'s argv, network, two '
                 'environment files and four binds ('+K12_DATA_VOLUME+' at '+K12_DATA_TARGET+', the journal and '+K12_CAPACITY_ROOT
                 +' read-only, '+K12_MANIFESTS+' read-write), every bind source and every ancestor of it controlled by root alone '
                 '(uid 0, gid 0, no group or other write, no setgid, no link) except the named read-only data volume (Codex #429 '
                 '5986698996: ancestors root-controlled, a mount point, the release directory root 0700, the release file hashed '
                 'against the REQUEST before the create and again after the start); the container '
                 'parks until its view. PERSIST: docker logs (no follow, no tail; QUICK class: bounded in seconds and bytes) of that '
                 'exited container, identified by its ID, name and two labels, with a known exit code and not OOM-killed; the output '
                 'must be exactly one complete writer receipt of this day and of a publish run, consistent with the exit code, or '
                 'nothing is written; that receipt and the exit state go into one new private file (root:root 0600, exclusive '
                 'creation, fsync, read back) in '+K12_RECEIPTS+'. STOP: docker stop of that running container before its view. '
                 'REMOVE: docker rm without -f or -v of exited or never-started containers of this family whose private receipt is on '
                 'the host or which ended by a stop before their view. A container is acted on only after its name, labels, image, '
                 'argv and binds were read and found to be this family\'s. Nothing is written into the manifests directory, the '
                 'capacity tree, the journal or the data directory by this process; no environment is printed; the manifest hash and '
                 'the symbol count never leave the host.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K12_EPOCH,'days':list(K12_DAYS),
       'modes':list(W_MODES),'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,
       'command_environment':COMMAND_ENVIRONMENT,'command_variables':COMMAND_VARIABLES,
       'clock':{'views_utc':{str(key):value for key,value in sorted(K12_VIEW_UTC.items())},'cutoff_utc':K12_CUTOFF_UTC,'view_seconds':K12_VIEW_SECONDS,
                'launch_lead_seconds':W_LAUNCH_LEAD_SECONDS,'stop_lead_seconds':W_STOP_LEAD_SECONDS,
                'persist_after_view_seconds':W_PERSIST_AFTER_VIEW_SECONDS,'remove_day':W_REMOVE_DAY,'remove_not_before_utc':W_REMOVE_NOT_BEFORE},
       'placement':{'capacity_root':K12_CAPACITY_ROOT,'config_root':K12_CONFIG_ROOT,'capacity_target':K12_CAPACITY_TARGET,
                    'data_target':K12_DATA_TARGET,'data_volume_read_only_exception':K12_DATA_VOLUME,
                    'release':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'source_root_never_bound':K12_SOURCE_ROOT,
                    'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK','manifests':K12_MANIFESTS,'secret_env':K12_SECRET_ENV,
                    'pins_env':K12_PINS_ENV,'docker_cli':K12_DOCKER_CLI,'receipts':K12_RECEIPTS,'writer_name':k12_writer_name('<sha256>'),
                    'journal_forbidden':list(K12_JOURNAL_FORBIDDEN)},
       'container':{'name':'c3po-k12-<yyyymmdd>-w<index>','labels':[K12_LABEL_REQUEST,K12_LABEL_CAPACITY],'inspect_format':K12_FORMAT,
                    'create_prefix':K12_CREATE_PREFIX},
       'persisted':{'directory':K12_RECEIPTS,'name':'k12-<day>-w<index>.writer.json','schema':K12_PERSISTED_SCHEMA,
                    'keys':sorted(K12_PERSISTED_KEYS),'mode_octal':'0600','content':'EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE'},
       'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'never':['--rm on the launched container','-d on a run','a pull','-f or -v on rm','docker exec','a write into the manifests directory, '
                'the capacity tree, the journal or the data directory by this process','a bind source not controlled by root alone other than the named read-only data volume','a read of the data volume other than the release file','the environment of a container','the content of secret.env',
                'the manifest hash or the symbol count in a receipt','an existing file overwritten, renamed, chmodded, chowned or removed',
                'a container that is not this family\'s','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'allowance_seconds':{'LAUNCH':W_ALLOWANCE_LAUNCH_SECONDS,'PERSIST':W_ALLOWANCE_PERSIST_SECONDS,'STOP':W_ALLOWANCE_SECONDS,
                                      'REMOVE':W_ALLOWANCE_SECONDS},'max_removals':W_MAX_REMOVALS,'stdout_bytes':K12_STDOUT_MAX_BYTES,
                 'request_bytes':K12_REQUEST_MAX_BYTES,'writer_bytes':K12_WRITER_MAX_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """The read primitives, the fixed-argv runner and the creating calls of the files part (PERSIST's one file)."""


# ---------------------------------------------------------------- the plan (pure)
def w_path(name,derived):
    return derived['journal']['source'] if name=='journal' else W_PATHS[name]

def w_chains(plan,derived):
    """The signed rows of every directory the mode walks, validated: every chain controlled by root alone, every
    component from '/' (k12_root_chain, Codex 6), and the leaf of each private directory root:root 0700."""
    rows=plan['parent_rows'];names=W_CHAINS[plan['mode']]
    need(type(rows) is dict and set(rows)==set(names),'PARENT_ROWS_INVALID')
    for name in names:
        if name=='data':k12_data_chain(rows[name]);continue           # the named read-only exception
        k12_root_chain(rows[name],w_path(name,derived))
        leaf=rows[name][-1]
        need(name not in W_PRIVATE or (leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,0o700),'DIRECTORY_NOT_ROOT_PRIVATE')
    return rows

def w_removals(plan):
    """REMOVE: 1 to 12 rows {day, window_slot, container_id, image_id, launch_request_sha256, capacity_request_sha256},
    distinct by container and by window."""
    items=plan['removals']
    need(type(items) is list and items,'REMOVALS_INVALID')        # at most 12: four days x three slots, distinct below
    for item in items:
        need(type(item) is dict and set(item)=={'day','window_slot','container_id','image_id','launch_request_sha256','capacity_request_sha256'}
             and item['day'] in K12_DAYS and integer(item['window_slot'],1,3) and text(item['container_id'],CONTAINER_ID)
             and text(item['image_id'],IMAGE_ID) and hexpin(item['launch_request_sha256']) and hexpin(item['capacity_request_sha256']),'REMOVALS_INVALID')
    need(len({item['container_id'] for item in items})==len(items) and len({(item['day'],item['window_slot']) for item in items})==len(items),
         'REMOVALS_INVALID')
    return items

def w_derived(plan):
    """Everything the run will put on the engine, from the signed plan alone."""
    mode=plan['mode'];need(mode in W_MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if mode=='REMOVE':
        need(plan['capacity_request'] is None and plan['launch_request_sha256'] is None,'MODE_MEMBERS_INVALID')
        w_removals(plan);derived={'journal':{'source':None}}
    else:
        need(plan['removals'] is None and ((plan['launch_request_sha256'] is None) if mode=='LAUNCH' else hexpin(plan['launch_request_sha256'])),
             'MODE_MEMBERS_INVALID')
        derived=k12_capacity_request(plan['capacity_request'])[2]
    w_chains(plan,derived)
    return derived

def validate_plan(plan):w_derived(plan)

def w_labels(derived,request_sha256):return [(K12_LABEL_REQUEST,request_sha256),(K12_LABEL_CAPACITY,derived['sha256'])]

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared. For
    LAUNCH the create argv carries the label of this request's own hash, which no plan can hold: it is shown with the
    placeholder <this request's sha256>."""
    derived=w_derived(plan);mode=plan['mode']
    out={'operation':OPERATION,'mode':mode,'epoch':K12_EPOCH,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
         'chains':{name:chain_effects(plan['parent_rows'][name]) for name in W_CHAINS[mode]},
         'writes_into_manifests_capacity_journal_or_data':False,'chain_rule':'ROOT_CONTROLLED_UID0_GID0_NO_GROUP_OR_OTHER_WRITE_NO_SETGID_NO_LINK','environment_printed':False,'activation':False}
    if mode=='REMOVE':
        out['removals']=[{'container_name':k12_container_name(item['day'],item['window_slot']),'container_id':item['container_id'],
                          'image_id':item['image_id'],'labels':{K12_LABEL_REQUEST:item['launch_request_sha256'],K12_LABEL_CAPACITY:item['capacity_request_sha256']},
                          'require':'EXITED_WITH_ITS_PRIVATE_RECEIPT_OR_STOPPED_BEFORE_ITS_VIEW_OR_NEVER_STARTED'} for item in plan['removals']]
        out['command']=['rm']+[item['container_id'] for item in plan['removals']]
        out['force']=False;out['volumes']=False
        return out
    name=k12_container_name(derived['day'],derived['index'])
    out.update(capacity_request_sha256=derived['sha256'],day=derived['day'],window=derived['window'],window_slot=derived['index'],
               container_name=name,view_opens_at=derived['view_opens_at'],cutoff_at=derived['cutoff_at'])
    if mode=='LAUNCH':
        out['create']=K12_CREATE_PREFIX+k12_container_words(derived,name,w_labels(derived,'<this request\'s sha256>'))
        out['start']=['start','<the 64-hex ID create printed>']
        out['docker_config']=K12_DOCKER_CLI
        out['writer']={'path':K12_CONFIG_ROOT+'/'+k12_writer_name(derived['writer_sha256']),'sha256':derived['writer_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['capacity_config']={'path':K12_CONFIG_ROOT+'/'+derived['config_name'],'sha256':derived['config_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['pins_env']={'path':K12_PINS_ENV,'sha256':derived['pins_sha256'],'require':'ROOT_0600_ONE_LINK'}
        out['secret_env']={'path':K12_SECRET_ENV,'require':'ROOT_0600_ONE_LINK','read':'METADATA_ONLY'}
        out['journal']={'path':derived['journal']['source'],'target':derived['journal']['target'],'require':'ROOT_0700_CATALOG_ROOT_0600'}
        out['data']={'path':K12_DATA_VOLUME,'target':K12_DATA_TARGET,'read_only':True,'exception':'CODEX_429_5986698996',
                     'release':{'path':K12_RELEASE_DIR+'/'+K12_RELEASE_FILE,'sha256':derived['release_sha256'],'require':'ROOT_0600_ONE_LINK',
                                'checked':'BEFORE_THE_CREATE_AND_AFTER_THE_START'}}
        out['container']={'removed_on_exit':False,'restart':'no','parks_until':derived['view_opens_at']}
        out['earlier_windows']='EXITED_WITH_PRIVATE_RECEIPT_AND_ONE_VALID_LINE_NOT_TERMINAL_OR_NEVER_STARTED_OR_ABSENT'
        out['earlier_window_stopped_before_its_view']='REFUSED_DAY_STOPPED'
        out['manifest_of_the_day']='ABSENT_OR_TWO_LINKS_OR_AFTER_AN_EARLIER_WINDOW_WITH_A_LINE'
    elif mode=='PERSIST':
        out['launch_request_sha256']=plan['launch_request_sha256']
        out['read']=['logs','<the 64-hex ID of that exited container>']
        out['logs_bounds']={'class':'QUICK','seconds':COMMAND_CLASSES['QUICK']['seconds'],'stdout_bytes':K12_STDOUT_MAX_BYTES,'follow':False,'tail':False}
        out['requires']='EXACTLY_ONE_COMPLETE_WRITER_RECEIPT_CONSISTENT_WITH_THE_EXIT_CODE_NOT_OOM'
        out['creates']={'path':K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index']),'mode_octal':'0600','uid':0,'gid':0,
                        'schema':K12_PERSISTED_SCHEMA,'expect':'ABSENT'}
    else:
        out['launch_request_sha256']=plan['launch_request_sha256']
        out['stop']=['stop','-t',W_STOP_SECONDS,'<the 64-hex ID of that running container>']
        out['not_later_than_seconds_before_the_view']=W_STOP_LEAD_SECONDS
    return out
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the run
def w_clock(plan,derived,begun):
    """The instant of the run against the window of the mode (pure; before anything is observed)."""
    mode=plan['mode']
    if mode=='REMOVE':
        need(begun.date().isoformat()==W_REMOVE_DAY and begun>=instant(k12_at(W_REMOVE_DAY,W_REMOVE_NOT_BEFORE)),'REMOVE_OUTSIDE_FRIDAY_EVENING')
        return
    view=instant(derived['view_opens_at'])
    need(begun.date().isoformat()==derived['day'],'RUN_NOT_ON_THE_DAY_OF_THE_WINDOW')
    if mode=='PERSIST':
        need((begun-view).total_seconds()>=W_PERSIST_AFTER_VIEW_SECONDS,'PERSIST_BEFORE_THE_VIEW_AND_A_MINUTE');return
    need(begun>=instant(derived['not_before']),'RUN_BEFORE_THE_WINDOW_START')
    lead=W_LAUNCH_LEAD_SECONDS if mode=='LAUNCH' else W_STOP_LEAD_SECONDS
    need((view-begun).total_seconds()>=lead,'TOO_CLOSE_TO_THE_VIEW')

def w_hold(host,rows,gate,observed):return Pinned(host,walk_pinned(host,rows,gate,observed),rows=rows)

def w_inspect(commands,target):return k12_inspect(commands.output('inspect',target,docker_config=K12_DOCKER_CLI))

def w_try_inspect(commands,target):
    """The container's row, or None when docker inspect does not answer it (absent or broken: one case)."""
    try:return w_inspect(commands,target)
    except CommandFailed:return None

def w_listed_without(commands,name):
    """True only when a listing of every container succeeded and does not hold that name (an inspect that fails is not a
    proof of absence: the daemon may not have answered)."""
    try:return name not in [row['name'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)]
    except Exception:return False

def w_summary(row):
    if row is None:return None
    return {'id':row['id'],'name':row['name'],'state':row['state'],'running':row['running'],'exit_code':row['exit_code'],
            'oom_killed':row['oom_killed'],'started':row['started_at']!=K12_NEVER_STARTED,'finished_at':row['finished_at']}

def w_earlier(ctx,containers):
    """LAUNCH: the containers of this family for the same day, against the window being launched. A later window's
    container, any of them not settled, an earlier one that ran without its private receipt, or an earlier receipt that
    shows the day decided (published, or the empty list) is a refusal (ORD:16; CAP outcome rule; S1D)."""
    derived=ctx['derived'];day=derived['day'];prefix='c3po-k12-%s-'%k12_compact(day);seen=[]
    need(not [row for row in containers if row['name'].startswith('c3po-k12-') and not row['name'].startswith(prefix) and row['state']!='exited'
              and row['state']!='created'],'CAPACITY_CONTAINER_OF_ANOTHER_DAY_NOT_SETTLED')
    for row in containers:
        if not row['name'].startswith(prefix):continue
        seen.append({'name':row['name'],'state':row['state']})
        need(row['name']!=k12_container_name(day,derived['index']),'CONTAINER_NAME_TAKEN')
        need(row['state'] in ('exited','created'),'CAPACITY_CONTAINER_OF_THE_DAY_NOT_SETTLED')
        need(row['name'] in [k12_container_name(day,index) for index in range(1,derived['index'])],'CAPACITY_CONTAINER_OF_THE_DAY_NOT_EARLIER')
    ctx['detail']['day_containers']=seen
    for index in range(1,derived['index']):
        name=k12_container_name(day,index);found=[row for row in containers if row['name']==name]
        if not found or found[0]['state']=='created':continue
        raw,facts=k12_file(ctx['host'],k12_persisted_name(day,index),ctx['handles']['receipts'],ctx['gate'],K12_PERSISTED_MAX_BYTES)
        if raw is None:
            # PERSIST keeps nothing but a complete receipt: an earlier container without one either ended by D4's stop
            # before its view (the day is stopped, ORD:17) or is not settled.
            row=w_try_inspect(ctx['commands'],found[0]['id'])
            need(not (row is not None and k12_stopped(row['exit_code'],row['oom_killed'],row['finished_at'],k12_at(day,K12_VIEW_UTC[index]))),
                 'DAY_STOPPED_BEFORE_A_VIEW')
        need(raw is not None,'EARLIER_WINDOW_RECEIPT_NOT_PERSISTED')
        need(k12_private(facts),'EARLIER_WINDOW_RECEIPT_NOT_PRIVATE')
        value,stdout=k12_persisted(raw,{'epoch':K12_EPOCH,'day':day,'window_slot':index,'container_id':found[0]['id'],'container_name':name})
        ended,line=k12_ended(value,stdout,day,k12_at(day,K12_VIEW_UTC[index]))
        need(ended!='STOPPED','DAY_STOPPED_BEFORE_A_VIEW')
        need(ended=='LINE','EARLIER_WINDOW_ENDED_WITHOUT_A_VALID_LINE')
        terminal=k12_terminal(line);ctx['earlier_line']=True       # a LINE is of a publish run (k12_receipt_line)
        need(terminal!='PUBLISHED','DAY_ALREADY_PUBLISHED')
        need(terminal!='EMPTY_LIST','DAY_TERMINAL_EMPTY_LIST')

def w_launch_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    for name in W_CHAINS['LAUNCH']:
        observed=detail['parents'].setdefault(name,[]);handles[name]=w_hold(host,ctx['plan']['parent_rows'][name],gate,observed)
    raw,facts=k12_file(host,k12_writer_name(derived['writer_sha256']),handles['config'],gate,K12_WRITER_MAX_BYTES)
    need(raw is not None,'WRITER_FILE_ABSENT');need(k12_private(facts),'WRITER_FILE_NOT_PRIVATE')
    need(sha(raw)==derived['writer_sha256'],'WRITER_BYTES_NOT_THE_SIGNED_ONES')
    raw,facts=k12_file(host,derived['config_name'],handles['config'],gate,K12_CONFIG_MAX_BYTES)
    need(raw is not None,'CAPACITY_CONFIG_ABSENT');need(k12_private(facts),'CAPACITY_CONFIG_NOT_PRIVATE')
    need(sha(raw)==derived['config_sha256'],'CAPACITY_CONFIG_NOT_THE_SIGNED_BYTES')
    raw,facts=k12_file(host,'pins.env',handles['reader_config'],gate,K12_PINS_MAX_BYTES)
    need(raw is not None,'PINS_ENV_ABSENT');need(k12_private(facts),'PINS_ENV_NOT_PRIVATE')
    need(sha(raw)==derived['pins_sha256'],'PINS_ENV_NOT_THE_SIGNED_BYTES')
    k12_release(host,handles['data'],gate,derived)
    found=k12_entry(host,'secret.env',handles['reader_config'],gate)         # metadata only: never opened, never hashed
    need(found is not None,'SECRET_ENV_ABSENT');need(k12_private(found),'SECRET_ENV_NOT_PRIVATE')
    need(count_entries(host,handles['docker_cli'].fd,gate)==0,'DOCKER_CLI_DIRECTORY_NOT_EMPTY')
    for name in ('epoch.json','maintenance.lock'):
        need(k12_private(k12_entry(host,name,handles['journal'],gate)),'JOURNAL_CATALOG_NOT_AS_REQUIRED')
    present=k12_entry(host,derived['day']+'.json',handles['manifests'],gate)
    detail['manifest_before']={'present':present is not None,'links':None if present is None else present['links']}
    image=image_facts(ctx['commands'],derived['image_id'],docker_config=K12_DOCKER_CLI)
    need(image['id']==derived['image_id'],'IMAGE_ID_MISMATCH');need(image['revision_label']==derived['build_sha'],'IMAGE_REVISION_MISMATCH')
    containers=container_list(ctx['commands'],docker_config=K12_DOCKER_CLI)
    detail['containers_listed']=len(containers)
    need(not [row for row in containers if row['name']==k12_preflight_name(derived['day'])],'PREFLIGHT_CONTAINER_PRESENT')
    w_earlier(ctx,containers)
    # A published manifest of the day (one link) that no earlier window of this family explains: never a new window.
    # Two links is the interrupted publication the next window completes (ORD:33(a)): allowed.
    need(not (present is not None and present['links']==1 and not ctx.get('earlier_line')),'MANIFEST_PRESENT_WITHOUT_AN_EARLIER_WINDOW')
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('create','start')+W_ALLOWANCE_LAUNCH_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
    lead=(instant(derived['view_opens_at'])-ctx['clock']()).total_seconds();detail['seconds_to_the_view_before_create']=int(lead)
    need(lead>=W_LAUNCH_LEAD_SECONDS,'TOO_CLOSE_TO_THE_VIEW')

def w_launch(ctx):
    derived,state,commands,detail=ctx['derived'],ctx['state'],ctx['commands'],ctx['detail']
    name=k12_container_name(derived['day'],derived['index'])
    words=k12_container_words(derived,name,w_labels(derived,ctx['bound']['request_sha256']))
    result=effect(state,commands,'create',*words,capture=True,docker_config=K12_DOCKER_CLI)
    detail['create']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'CREATE_NOT_STARTED'
    if not result['returned']:
        detail['after_create']=w_summary(w_try_inspect(commands,name));return 'CREATE_UNCERTAIN'
    output=result['output']
    if result['returncode']!=0 or not (len(output)==65 and text(output[:64].decode('ascii','replace'),CONTAINER_ID) and output[64:]==b'\n'):
        row=w_try_inspect(commands,name);detail['after_create']=w_summary(row)
        if row is None and w_listed_without(commands,name):state.fail();return 'CREATE_FAILED'
        state.unknown();return 'CREATE_RETURNED_WITHOUT_ITS_ID' if row is not None else 'CREATE_FAILED_STATE_UNKNOWN'
    identifier=output[:64].decode('ascii');row=w_try_inspect(commands,identifier);detail['after_create']=w_summary(row)
    if row is None or row['id']!=identifier or not k12_ours(row,derived,name,ctx['bound']['request_sha256']):
        state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'
    if row['state']!='created' or row['started_at']!=K12_NEVER_STARTED:state.unknown();return 'CREATED_CONTAINER_NOT_AS_SIGNED'
    state.done();ctx['container_id']=identifier
    result=effect(state,commands,'start',identifier,docker_config=K12_DOCKER_CLI)
    detail['start']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'START_NOT_STARTED'
    row=w_try_inspect(commands,identifier);detail['after_start']=w_summary(row)
    if not result['returned']:return 'START_UNCERTAIN'
    if row is None or not k12_ours(row,derived,name,ctx['bound']['request_sha256']):state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'
    if row['started_at']==K12_NEVER_STARTED and row['state']=='created':state.fail();return 'START_FAILED'
    if row['started_at']==K12_NEVER_STARTED:state.unknown();return 'STARTED_CONTAINER_NOT_READ_BACK'
    state.done()
    try:k12_release(ctx['host'],ctx['handles']['data'],ctx['gate'],derived)       # the bytes the writer read are still the signed ones
    except Exception as error:return 'RELEASE_CHANGED_DURING_LAUNCH'
    if result['returncode']!=0:return 'START_RETURNED_NONZERO'
    detail['launched']={'container_id':identifier,'container_name':name,'running':row['running'],'state':row['state'],
                        'parks_until':derived['view_opens_at']}
    return None

def w_identified(ctx,target):
    """The container of this window and launch request, by its deterministic name; refused unless it is ours."""
    derived=ctx['derived'];name=k12_container_name(derived['day'],derived['index'])
    row=w_try_inspect(ctx['commands'],target or name)
    need(row is not None,'CONTAINER_ABSENT')
    need(k12_ours(row,derived,name,ctx['plan']['launch_request_sha256']),'CONTAINER_NOT_OF_THIS_WINDOW')
    return row

def w_persist_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    handles['receipts']=w_hold(host,ctx['plan']['parent_rows']['receipts'],gate,detail['parents'].setdefault('receipts',[]))
    need(k12_entry(host,k12_persisted_name(derived['day'],derived['index']),handles['receipts'],gate) is None,'PERSISTED_RECEIPT_PRESENT')
    row=w_identified(ctx,None);detail['container']=w_summary(row)
    need(row['state']!='created','CONTAINER_NEVER_STARTED')
    need(row['state']=='exited' and row['running'] is False,'CONTAINER_NOT_EXITED')
    need(row['oom_killed'] is False and integer(row['exit_code'],0,255) and row['started_at']!=K12_NEVER_STARTED,'CONTAINER_EXIT_NOT_KNOWN')
    ctx['row']=row
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('logs')+W_ALLOWANCE_PERSIST_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def w_persist(ctx):
    derived,state,commands,detail,row=ctx['derived'],ctx['state'],ctx['commands'],ctx['detail'],ctx['row']
    result=effect(state,commands,'logs',row['id'],capture=True,docker_config=K12_DOCKER_CLI)
    detail['logs']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'LOGS_NOT_STARTED'
    if not result['returned']:return 'LOGS_UNCERTAIN'
    state.fail()                    # docker logs reads; the core counts it as an effect: settled as "nothing changed"
    if result['returncode']!=0:return 'LOGS_FAILED'
    stdout=result['output']
    if len(stdout)>K12_STDOUT_MAX_BYTES:return 'STDOUT_TOO_LARGE'
    again=w_try_inspect(commands,row['id'])
    if again is None or (again['id'],again['state'],again['finished_at'],again['exit_code'])!=(row['id'],row['state'],row['finished_at'],row['exit_code']):
        return 'CONTAINER_CHANGED_DURING_PERSIST'
    try:line=k12_receipt_line(stdout,derived['day'],row['exit_code'])
    except Refused as error:
        # nothing written: only one complete receipt is ever persisted (the code goes on to perform; the logs read is settled)
        detail['writer_line']={'valid':False,'code':str(error),'stdout_bytes':len(stdout)};raise
    detail['writer_line']={'valid':True,'code':None,'public':k12_line_public(line),'terminal':k12_terminal(line),'stdout_bytes':len(stdout)}
    body={'schema':K12_PERSISTED_SCHEMA,'epoch':K12_EPOCH,'day':derived['day'],'window':derived['window'],'window_slot':derived['index'],
          'container_id':row['id'],'container_name':row['name'][1:],'launch_request_sha256':ctx['plan']['launch_request_sha256'],
          'capacity_request_sha256':derived['sha256'],'persist_request_sha256':ctx['bound']['request_sha256'],'image_id':row['image_id'],
          'exit_code':row['exit_code'],'oom_killed':row['oom_killed'],'started_at':row['started_at'],'finished_at':row['finished_at'],
          'stdout_b64':base64.b64encode(stdout).decode('ascii'),'stdout_sha256':sha(stdout),'stdout_bytes':len(stdout)}
    content=canonical(body);path=K12_RECEIPTS+'/'+k12_persisted_name(derived['day'],derived['index'])
    entry=create_file(0,'PERSISTED_WRITER_RECEIPT',path,content,PRIVATE_FILE_MODE,ctx['handles']['receipts'],ctx['host'],ctx['gate'],state,ctx['go16'])
    ctx['ledger'].append(entry)
    if entry['state']!='INSTALLED_DURABLE':return entry['code'] or 'PERSIST_FAILED'
    return readback_file(entry,content,PRIVATE_FILE_MODE,ctx['handles']['receipts'],ctx['host'],ctx['gate'])

def w_stop_precheck(ctx):
    host,gate,derived,handles,detail=ctx['host'],ctx['gate'],ctx['derived'],ctx['handles'],ctx['detail']
    handles['manifests']=w_hold(host,ctx['plan']['parent_rows']['manifests'],gate,detail['parents'].setdefault('manifests',[]))
    detail['manifest_names_before']=w_manifest_state(ctx)
    row=w_identified(ctx,None);detail['container']=w_summary(row)
    need(row['state']=='running' and row['running'] is True,'CONTAINER_NOT_RUNNING')
    ctx['row']=row
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('stop')+W_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
    need((instant(derived['view_opens_at'])-ctx['clock']()).total_seconds()>=W_STOP_LEAD_SECONDS,'TOO_CLOSE_TO_THE_VIEW')

def w_manifest_state(ctx):
    """The day's manifest and the writer's temporaries of the day in the manifests directory: two counts and a flag.
    Names of other days and of other files are not reported."""
    day=ctx['derived']['day'];present=0;temporaries=0;pattern=r'\.'+re.escape(day+'.json')+r'\.[0-9a-f]{16}\.tmp'
    for name in ctx['host'].names(ctx['handles']['manifests'].fd):
        if name==day+'.json':present+=1
        elif re.fullmatch(pattern,name):temporaries+=1
    return {'manifest_present':present==1,'temporaries':temporaries}

def w_stop(ctx):
    state,commands,detail,row=ctx['state'],ctx['commands'],ctx['detail'],ctx['row']
    result=effect(state,commands,'stop',row['id'],docker_config=K12_DOCKER_CLI)
    detail['stop']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'STOP_NOT_STARTED'
    after=w_try_inspect(commands,row['id']);detail['after_stop']=w_summary(after)
    if not result['returned']:return 'STOP_UNCERTAIN'
    if after is not None and after['id']==row['id'] and after['state']=='exited' and after['running'] is False:state.done()
    elif after is not None and after['id']==row['id'] and after['running'] is True:
        state.fail();return 'STOP_FAILED'
    else:
        state.unknown();return 'STOPPED_CONTAINER_NOT_READ_BACK'
    try:
        ctx['handles']['manifests'].verify(ctx['gate']);detail['manifest_names_after']=w_manifest_state(ctx)
    except Exception as error:return code_of(error,'READBACK_UNAVAILABLE')
    if detail['manifest_names_after']!=detail['manifest_names_before']:return 'MANIFEST_DIRECTORY_CHANGED_DURING_STOP'
    if result['returncode']!=0:return 'STOP_RETURNED_NONZERO'
    return None

def w_remove_precheck(ctx):
    host,gate,handles,detail,commands=ctx['host'],ctx['gate'],ctx['handles'],ctx['detail'],ctx['commands']
    handles['receipts']=w_hold(host,ctx['plan']['parent_rows']['receipts'],gate,detail['parents'].setdefault('receipts',[]))
    rows=[]
    for item in ctx['plan']['removals']:
        name=k12_container_name(item['day'],item['window_slot'])
        row=w_try_inspect(commands,item['container_id'])
        need(row is not None,'CONTAINER_ABSENT')
        need(row['id']==item['container_id'] and row['name']=='/'+name and row['image_id']==item['image_id']
             and row['request_label']==item['launch_request_sha256'] and row['capacity_label']==item['capacity_request_sha256']
             and row['auto_remove'] is False,'CONTAINER_NOT_OF_THIS_FAMILY')
        need(row['running'] is False and row['state'] in ('exited','created'),'CONTAINER_NOT_STOPPED')
        need(row['state']=='exited' or row['started_at']==K12_NEVER_STARTED,'CONTAINER_NOT_STOPPED')
        if row['state']=='exited':
            raw,facts=k12_file(host,k12_persisted_name(item['day'],item['window_slot']),handles['receipts'],gate,K12_PERSISTED_MAX_BYTES)
            if raw is None and k12_stopped(row['exit_code'],row['oom_killed'],row['finished_at'],k12_at(item['day'],K12_VIEW_UTC[item['window_slot']])):
                rows.append(w_summary(row));continue        # ended by D4's stop before its view: no receipt was ever printed
            need(raw is not None,'PERSISTED_RECEIPT_MISSING');need(k12_private(facts),'PERSISTED_RECEIPT_NOT_PRIVATE')
            k12_persisted(raw,{'epoch':K12_EPOCH,'day':item['day'],'window_slot':item['window_slot'],'container_id':item['container_id'],
                               'container_name':name,'launch_request_sha256':item['launch_request_sha256'],
                               'capacity_request_sha256':item['capacity_request_sha256'],'image_id':item['image_id']})
        rows.append(w_summary(row))
    detail['containers']=rows
    listed=container_list(commands,docker_config=K12_DOCKER_CLI);named={item['container_id'] for item in ctx['plan']['removals']}
    detail['family_containers_not_named']=sorted(row['name'] for row in listed if row['name'].startswith('c3po-k12-') and row['id'] not in named)
    left=gate();detail['seconds_left_before_first_effect']=int(left)
    need(left>=effects_budget('remove')+W_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def w_remove(ctx):
    state,commands,detail=ctx['state'],ctx['commands'],ctx['detail']
    identifiers=[item['container_id'] for item in ctx['plan']['removals']]
    result=effect(state,commands,'remove',*identifiers,capture=True,docker_config=K12_DOCKER_CLI)
    detail['remove']={key:result[key] for key in ('started','returned','returncode','code')}
    if not result['started']:return result['code'] or 'REMOVE_NOT_STARTED'
    try:listed={row['id'] for row in container_list(commands,docker_config=K12_DOCKER_CLI)}
    except Exception as error:
        if result['returned']:state.unknown()
        return code_of(error,'READBACK_UNAVAILABLE')
    removed=[identifier for identifier in identifiers if identifier not in listed]
    detail['removed']=len(removed);detail['left']=len(identifiers)-len(removed)
    if not result['returned']:return 'REMOVE_UNCERTAIN'
    if removed:state.done()
    else:state.fail()
    if len(removed)!=len(identifiers):return 'REMOVE_INCOMPLETE'
    if result['returncode']!=0:return 'REMOVE_RETURNED_NONZERO'
    return None

W_STEPS={'LAUNCH':(w_launch_precheck,w_launch),'PERSIST':(w_persist_precheck,w_persist),'STOP':(w_stop_precheck,w_stop),
         'REMOVE':(w_remove_precheck,w_remove)}

def _reduce_parents(receipt):receipt['parents']={key:len(value) for key,value in (receipt.get('parents') or {}).items()}
def _reduce_detail(receipt):receipt['detail']={'reduced_for_size':True}
REDUCTIONS=[('PARENTS_REDUCED_TO_COUNT',_reduce_parents),('DETAIL_DROPPED',_reduce_detail)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    derived=w_derived(plan)                   # pure: everything the run will put on the engine, and nothing else
    gate()                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);ledger=[];handles={}
    detail={'parents':{}}
    ctx={'plan':plan,'derived':derived,'host':host,'gate':gate,'commands':commands,'state':state,'bound':bound,'clock':clock,
         'handles':handles,'detail':detail,'ledger':ledger,'go16':bound['go_sha256'][:16]}
    def finish(status,outcome,code,extra):
        parents=detail.pop('parents',{})
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=plan['mode'],
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),parents=parents,
            detail=detail,ledger=ledger,objects_left_by_this_run=objects_left([],ledger),pre_existing_objects_modified=False,**extra)))
    precheck,step=W_STEPS[plan['mode']]
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            w_clock(plan,derived,begun)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            precheck(ctx)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        try:stop=step(ctx)
        except Exception as error:
            stop=code_of(error,'EFFECT_STEP_FAILED')
            if state.pending:state.unknown()
        extra={'phase_reached':'EFFECTS','container_id':ctx.get('container_id')}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in handles.values():
            try:handle.close()
            except Exception:pass
# ==== END OP_K12_WINDOW ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
