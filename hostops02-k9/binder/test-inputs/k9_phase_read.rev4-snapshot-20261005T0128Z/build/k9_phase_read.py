"""OP_K9_PHASE_READ (K9R): the read program of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05.

Observations only. This source has no call that creates, changes or removes anything on the host's filesystem; it
does not carry the files part and its command table has no EFFECT row. Four signed modes. RESULT: the collect of one
detached K9 container: the launch record written by the write program, the container's state and exit code by a
docker inspect with this source's own fixed format (never its environment), the step's start marker and its one
receipt (the K9 runner's, or the packaged risk executor's in its spool), and the files the receipt names, hashed again
on the host. PROBE: the provider readiness of the previous session, read by one attached container of the signed image
ID with the provider environment file of the K9 tree, no bind and a read-only root filesystem, running a pinned
snippet (standard input) that calls only the image's certified producer code and prints counts and hashes. POLICY: the
installed live policy and release files read on the host, and the running worker's state and five environment names
as booleans. TREE: the weekly prerequisite read: the rows of every directory of the K9 tree and of the source root
from "/", the boot, and the metadata (never the content or size) of the secret files and the content hash of the
runner. Each item is observed on its own: a failed observation is UNAVAILABLE with a constant code, never an absence;
a mismatch is a finding that leaves every other item in the receipt. No value of an environment, no byte of a secret,
no symbol of an instrument and no provider payload leaves the run. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b'}
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

# ==== BEGIN OP_K9_PHASE_READ (this operation only) ====
import base64

OPERATION='GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'
PHASE='READONLY_K9_PHASE_READ'
REQUEST_SCHEMA='READONLY_HOSTOPS02_K9_PHASE_READ_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_K9_PHASE_READ_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_K9_PHASE_READ_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_K9_PHASE_READ_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K9_PHASE_READ_PLAN_V1'
SOURCE_NAME='k9_phase_read.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
# Exit 0 exists for one outcome per signed mode. RESULT is the mode of eight of the eleven K9 read operations.
COMPLETE_OUTCOME='K9_PHASE_RESULT_COMPLETE_ALL_OBSERVED'
K9_PROBE_OUTCOME='K9_READINESS_READY_ALL_OBSERVED'
K9_POLICY_OUTCOME='K9_POLICY_AND_WORKER_AS_EXPECTED_ALL_OBSERVED'
K9_TREE_OUTCOME='K9_TREE_AS_REQUIRED_ALL_OBSERVED'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
K9_MODES=('RESULT','PROBE','POLICY','TREE')
K9_SUCCESS={'RESULT':COMPLETE_OUTCOME,'PROBE':K9_PROBE_OUTCOME,'POLICY':K9_POLICY_OUTCOME,'TREE':K9_TREE_OUTCOME}
PLAN_KEYS=frozenset(('mode','epoch','day','k9_phase','k9_operation','slot','attempt_key','run_not_after','constants','parent_rows',
                     'evidence_boot_id_sha256','policy_read'))

# ---------------------------------------------------------------- the epoch and the frozen interface
K9_EPOCH='R2D2-V2-SHADOW-2026-10-05'
# The sessions whose eve runs the K9 chain: Monday 05/10 has no K9 list (K9_INTERFACE_NOTE.md section 5.5).
K9_DAYS=('2026-10-06','2026-10-07','2026-10-08','2026-10-09')
K9_NOTE_SHA256='ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'        # K9_INTERFACE_NOTE.md rev 2
K9_OPERATIONS_SHA256='bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'  # K9_OPERATIONS.json beside it
K9_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K9_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
K9_SLOTS=('PRIMARY','SPARE')
# The eleven READ operations of K9_OPERATIONS.json: (Act B phase, mode of this source, the launch a RESULT collects).
K9_READ_OPERATIONS={'readiness_probe':('causal_list','PROBE',None),'readiness_recheck':('causal_list','PROBE',None),
                    'collect_result':('causal_list','RESULT','collect_launch'),'commit_result':('causal_list','RESULT','commit_launch'),
                    'publish_result':('causal_list','RESULT','publish_launch'),'components_result':('components','RESULT','components_launch'),
                    'sources_result':('sources','RESULT','sources_launch'),'acquire_result':('risk','RESULT','acquire_launch'),
                    'execute_result':('risk','RESULT','execute_launch'),'capture_result':('capture','RESULT','capture_launch'),
                    'policy_read':('policy_readonly','POLICY',None)}
# Launches run by the packaged risk CLI (its own receipts in its spool) rather than by the K9 runner.
K9_PACKAGED_PHASES={'acquire_launch':'acquire','execute_launch':'execute'}

# ---------------------------------------------------------------- placement (N-8): Codex's decision of 2026-10-04
# (W/codex-n8-placement-20261004.txt, sha256 d30f7f90...2c53). The K9 tree lies under a chain controlled by root alone:
# no open root, no ancestor of uid 1000, nothing writable by group or other, no link. Codex's decision 6 (#429,
# comment 5985748037): the source root moves under the same root-only chain (no open root, gid 0, no setgid, 0700), on
# the filesystem of days/ (one floor). The data volume is read only for the September secret sources (lstat only, the
# volume as open root) and by POLICY (the files install_release and activate put there).
# Every host path this source reads is derived from these constants and from nothing else. They are fixed words of the
# sealed bytes (the env file is a fixed word of the probe row), so a change is a new payload hash and a new review.
K9_DATA_VOLUME='/mnt/day-d-data'
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
K9_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K9_PLACEMENT={'k9_root':K9_ROOT,'source_root':K9_SOURCE_ROOT,'days':K9_ROOT+'/days','tools':K9_ROOT+'/tools','claims':K9_ROOT+'/claims',
              'secrets':K9_ROOT+'/secrets','emitter':K9_ROOT+'/secrets/emitter','provider_env_file':K9_ROOT+'/secrets/provider.env',
              'risk_db_env_file':K9_ROOT+'/secrets/risk-db.env','emitter_password':K9_ROOT+'/secrets/emitter/password',
              'source_open_root':None,'k9_open_root':None,'september_open_root':K9_DATA_VOLUME,
              'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53','decision_6':'#429 comment 5985748037'}
# The chains every K9 request of the week signs (rows copied from the TREE receipt of the same boot); claims is K9W's.
K9_PARENT_CHAINS=('days','source_root','secrets','tools','claims')
K9_RECEIVES_ENTRY=('days','source_root','claims')
# What the TREE read walks: (item key, placement key). Every one is a private directory of root (0:0 0700).
K9_TREE_DIRECTORIES=(('K9_ROOT','k9_root'),('DAYS','days'),('TOOLS','tools'),('CLAIMS','claims'),('SECRETS','secrets'),
                     ('EMITTER','emitter'),('SOURCE_ROOT','source_root'))
K9_SECRET_FILES=(('SECRETS','provider.env'),('SECRETS','risk-db.env'),('EMITTER','password'))
# The two September secret sources K3-K9 copies from (its draft: RISK_URL_DIRECTORY, EMITTER_SOURCE_DIRECTORY), whose
# identity K3-K9 signs from this TREE read: every component below the data volume by lstat only (never opened past a
# directory, never a size, a length or a digest). The last entry of each chain is the secret file.
K9_SEPTEMBER_SOURCES=(('.r2d2-v2-risk-secrets','risk-database-url'),('.c3po-role-executor-20260908-r2','secret','password'))
K9_PRIVATE_DIRECTORY_MODE=0o700
# Codex (#429, comment 5984327121): 200 GiB available (f_bavail * f_frsize of fstatvfs on the open descriptor of days/,
# never f_bfree) on the filesystem that contains days/; below it: HOLD. The source root's capacity is reported apart.
K9_DISK_FLOOR_BYTES=214748364800
K9_PRIVATE_FILE_MODE=0o600

# ---------------------------------------------------------------- limits
K9_MAX_SMALL_FILE=262144                 # launch record, start marker, receipts
K9_MAX_PLAN_FILE=16777216                # HOST_PLAN.json and GO.json of the packaged risk plan
K9_MAX_REHASH_FILE=134217728             # one output file hashed again on the host
K9_MAX_REHASH_TOTAL=1073741824           # all output files of one receipt
K9_MAX_AGGREGATE_FILE=16777216           # one file of an aggregated directory
K9_MAX_AGGREGATE_ENTRIES=4096
K9_MAX_OUTPUTS=64
K9_MAX_AGGREGATES=8
K9_MAX_COUNTS=64
K9_MAX_RUNNER_FILE=4194304
K9_MAX_POLICY_FILE=8192
K9_MAX_RELEASE_FILE=65536
K9_MAX_COUNT=10000000
K9_MAX_FLOOR=1<<50
K9_MAX_LIMIT=1<<40
K9_ENTRY='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K9_OUTPUT_KEY=r'(day|source)(/[A-Za-z0-9][A-Za-z0-9._=-]{0,127}){1,8}'
# Names that cannot carry a ticker: a runner's count keys are lower-case snake case with at least one underscore; the
# packaged executor's count keys are a closed list (r2d2_v2_risk_runner.py:366-367, risk_host_executor.py:372,
# risk_executor.py:230); a failure code is upper-case snake case with at least one underscore (the packaged executor's
# one code without an underscore, INTERRUPTED, is named); a snippet code is that, or the CamelCase name of a class.
K9_COUNT_KEY='[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}'
K9_PACKAGED_COUNT_NAMES=('symbols','captured','coverage_verified','coverage_unknown','db_comparable','db_equal','db_different','http_attempts',
                         'b3_skipped','READY','COMPLETED_NULL')
K9_CONSTANT_CODE='[A-Z][A-Z0-9]{0,39}(_[A-Z0-9]{1,39}){1,8}'
K9_PACKAGED_CODES_WITHOUT_UNDERSCORE=('INTERRUPTED',)
K9_NETWORK_NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'
K9_DAY='[0-9]{4}-[0-9]{2}-[0-9]{2}'
K9_SNIPPET_CODE='[A-Z][A-Z0-9]{0,39}(_[A-Z0-9]{1,39}){1,8}|[A-Z][a-z][A-Za-z0-9]{0,78}'
K9_RISK_LIMIT_KEYS=('max_symbols','max_total_requests','max_body_bytes','max_total_bytes','max_elapsed_seconds')
K9_NETWORK_CLASSES=('PROVIDER','DATABASE','DATABASE_AND_PROVIDER')
K9_PROVIDER_NETWORK='bridge'
K9_READINESS_RULE={'numerator':95,'denominator':100,'minimum_eligible':4000}
# A degenerate registry is never READY: E28's rule had only eligible > 0. The producer's own measurement is 6,001 rows of
# the selectable classes (r2d2_v2_producer_daily.py, build_daily_contract); 4,000 is two thirds of it.
K9_MINIMUM_ELIGIBLE=K9_READINESS_RULE['minimum_eligible']
K9_CONSTANT_KEYS=frozenset(('k9_interface_note_sha256','act_b_sha256','package_sha256','code_revision','release_sha256','policy_sha256','image_id',
                            'runner_sha256','probe_snippet_sha256','networks','step_table_sha256','risk_source_pins_sha256','risk_limits',
                            'readiness_rule','disk_floor_bytes','placement'))
K9_EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
K9_WALK_FINDINGS=('PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY')
K9_ROW_FIELDS=('device','inode','uid','gid','mode')

# ---------------------------------------------------------------- the contracts of the files RESULT reads (K9W and k9_runner.py must write them so)
K9_RECORD_SCHEMA='K9_LAUNCH_RECORD_V1'
K9_RECORD_KEYS=frozenset(('schema','epoch','day','operation','slot','attempt_key','request_sha256','step_plan_sha256','container_id',
                          'container_name','created_at','started_at','timeout_seconds'))
K9_STARTED_SCHEMA='K9_STEP_STARTED_V1'
K9_STARTED_KEYS=frozenset(('schema','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at'))
K9_STEP_SCHEMA='K9_STEP_RECEIPT_V1'
K9_STEP_KEYS=frozenset(('schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at','completed_at',
                        'package_sha256','build_sha','outputs','aggregates','counts'))
K9_STEP_FAILED_STATUSES=('REFUSED','FAILED','DEADLINE')
K9_PACKAGED_RECEIPT_SCHEMA='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1'
K9_PACKAGED_RECEIPT_KEYS=frozenset(('schema','phase','status','manifest_sha256','go_sha256','namespace','session_date','started_at','completed_at',
                                    'previous_receipt_sha256','outputs','operation_activation','certification_granted'))
K9_PACKAGED_FAILED_SCHEMA='R2D2_V2_RISK_HOST_FAILED_V1'
K9_PACKAGED_STARTED_KEYS=frozenset(('phase','manifest_sha256','go_sha256','started_at'))
K9_RISK_NAMESPACES=('R2D2-V2-DIAG-R4-','R2D2-V2-SHADOW-')       # + D: the two forms the packaged executor admits (N-1)

# ---------------------------------------------------------------- the commands
# The format of the RESULT read: what decides a collect (state and exit code) and the two labels K9W gives its
# containers. Never the environment of the container.
K9_LAUNCHED_FORMAT=('{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"state":{{json .State.Status}},'
                    '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
                    '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
                    '"attempt_key":{{json (index .Config.Labels "c3po.k9.attempt_key")}},'
                    '"request_sha256":{{json (index .Config.Labels "c3po.k9.request_sha256")}}}')
K9_LAUNCHED_KEYS=frozenset(('name','id','image_id','state','running','exit_code','oom_killed','started_at','finished_at','attempt_key','request_sha256'))
# The probe: an attached container of the signed image with egress (the provider network class), the provider env
# file of the K9 tree read by the docker CLI on the host, the producers' switch, no bind, nothing writable.
K9_PROBE_TIMEOUT_SECONDS=36
K9_PROBE_ALARM_SECONDS=34
K9_PROBE_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network',K9_PROVIDER_NETWORK,'--read-only','--cap-drop','ALL',
                 '--security-opt','no-new-privileges','--memory','2g','--pids-limit','256','--env-file',K9_PLACEMENT['provider_env_file'],
                 '--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true']
K9_CONTAINER_PREFIX='c3po-k9-'
# The pinned snippet of the readiness probe. It runs in the container as `python -I -B - <D> <request sha256>` with the
# image's own code on /app. Its first statement arms an alarm two seconds inside the container's own timeout. It
# refuses unless the producers' switch is on and the image's implementation package is the certified one, builds the
# registry with the packaged build_registry from the provider's symbol list, reads the bulk end-of-day rows of D-1, and
# applies E28's rule (present >= 95/100 of the eligible names, conflicts and unusable rows diagnostics only), with
# the packaged fetcher at zero retries and 15 s per call (two calls). It prints ONE line of counts, two payload
# hashes and the request hash it was given. A code is the first token of a refusal of its own or of the producer's
# ProducerError, and otherwise the name of the exception's class: never a message, a symbol or a token.
K9_PROBE_SNIPPET=r'''import signal
signal.alarm(34)
import hashlib, json, os, re, sys
sys.path.insert(0, '/app')
PACKAGE = 'b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
NUMERATOR, DENOMINATOR = 95, 100
MINIMUM_ELIGIBLE = 4000
REGISTRY_PATH = '/api/exchange-symbol-list/US'
BULK_PATH = '/api/eod-bulk-last-day/US'
class Stop(Exception):
    pass
OWN = (Stop,)
calls = 0
echo = None
def code_of(error):
    value = error.args[0] if isinstance(error, OWN) and len(error.args) == 1 and type(error.args[0]) is str else ''
    value = value.split(':', 1)[0]
    return value if re.fullmatch('[A-Z][A-Z0-9]{0,39}(_[A-Z0-9]{1,39}){1,8}', value) else type(error).__name__[:80]
try:
    arguments = sys.argv[1:]
    if len(arguments) != 2 or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', arguments[0]) or not re.fullmatch('[0-9a-f]{64}', arguments[1]):
        raise Stop('ARGUMENTS_INVALID')
    echo = arguments[1]
    from datetime import date, datetime, timezone
    day = date.fromisoformat(arguments[0])
    if os.environ.get('C3PO_R2D2_V2_PRODUCERS_ENABLED', '').lower() != 'true':
        raise Stop('PRODUCERS_NOT_ENABLED')
    from app.r2d2_v2_earnings_package import implementation_package_sha
    if implementation_package_sha() != PACKAGE:
        raise Stop('PACKAGE_NOT_THE_CERTIFIED_ONE')
    from app import r2d2_v2_producer_daily as producer
    from app.config import get_settings
    OWN = (Stop, producer.ProducerError)
    settings = get_settings()
    previous = producer.previous_session(day)
    close = producer.session_close(previous)
    if not datetime.now(timezone.utc) > close:
        raise Stop('PREVIOUS_SESSION_NOT_CLOSED')
    fetch = producer.EodhdFetcher(settings.eodhd_base_url, settings.eodhd_api_token, timeout=15.0, retries=0)
    begun = datetime.now(timezone.utc)
    calls += 1
    registry_response = fetch(REGISTRY_PATH, {})
    if registry_response.received_at < begun:
        raise Stop('RECEIPT_TIME_INVALID')
    registry, _ = producer.build_registry(registry_response, previous_close=close)
    requested = previous.isoformat()
    calls += 1
    bulk = fetch(BULK_PATH, {'date': requested})
    if bulk.received_at < registry_response.received_at:
        raise Stop('RECEIPT_TIME_INVALID')
    eligible = {item['symbol'] for item in registry['instruments'] if item.get('security_type') in producer.DAILY_ELIGIBLE_TYPES}
    rows = bulk.json()
    if not isinstance(rows, list):
        raise Stop('BULK_INVALID')
    grouped = {}
    dated = 0
    for row in rows:
        if not isinstance(row, dict) or row.get('date') != requested:
            continue
        dated += 1
        code = row.get('code')
        if isinstance(code, str) and code in eligible:
            grouped.setdefault(code, []).append(row)
    usable = duplicates = conflicts = 0
    for group in grouped.values():
        distinct = producer._distinct(group)
        duplicates += len(group) - len(distinct)
        if len(distinct) != 1:
            conflicts += 1
            continue
        if producer._bar(distinct[0], previous, bulk.received_at) is not None:
            usable += 1
    present = len(grouped)
    denominator = len(eligible)
    ready = denominator >= MINIMUM_ELIGIBLE and DENOMINATOR * present >= NUMERATOR * denominator
    out = {'status': 'DONE', 'readiness': 'READY' if ready else 'NOT_READY', 'day': arguments[0], 'previous_session': requested,
           'registry_symbols': len(registry['instruments']), 'eligible_symbols': denominator, 'present_eligible_symbols': present,
           'required_minimum': (NUMERATOR * denominator + DENOMINATOR - 1) // DENOMINATOR, 'usable_eligible_symbols': usable,
           'conflicting_eligible_symbols': conflicts, 'duplicate_eligible_rows': duplicates, 'bulk_rows': len(rows), 'dated_rows': dated,
           'logical_fetch_calls': calls, 'registry_payload_sha256': registry_response.sha256, 'bulk_payload_sha256': bulk.sha256,
           'request_sha256': echo, 'python': '%d.%d.%d' % sys.version_info[:3]}
except BaseException as error:
    out = {'status': 'FAILED', 'code': code_of(error), 'logical_fetch_calls': calls, 'request_sha256': echo}
os.write(1, json.dumps(out, sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n')
raise SystemExit(0 if out['status'] == 'DONE' else 1)
'''
K9_PROBE_SNIPPET_SHA256=sha(K9_PROBE_SNIPPET.encode('ascii'))
K9_PROBE_COUNTS=('registry_symbols','eligible_symbols','present_eligible_symbols','required_minimum','usable_eligible_symbols',
                 'conflicting_eligible_symbols','duplicate_eligible_rows','bulk_rows','dated_rows')
K9_PROBE_DONE_KEYS=frozenset(K9_PROBE_COUNTS+('status','readiness','day','previous_session','logical_fetch_calls','registry_payload_sha256',
                                              'bulk_payload_sha256','request_sha256','python'))
K9_PROBE_FAILED_KEYS=frozenset(('status','code','logical_fetch_calls','request_sha256'))

BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the signed name of the worker container','QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then the worker container ID','QUICK','READ'),
          'launched':command_row('docker',['container','inspect','--format',K9_LAUNCHED_FORMAT],'the 64-hex ID the launch record names','QUICK','READ'),
          'probe':command_row('docker',K9_PROBE_PREFIX,'--name c3po-k9-<yyyymmdd of D>-<operation>, the signed image ID, timeout -s KILL 36 python -I -B - <D> <request sha256>','RUN','CONTAINER',stdin=True)}

SCOPE_STATEMENT=('Reads and changes nothing on the filesystem of the host. RESULT: the launch record of one detached K9 container, that '
                 'container\'s state and exit code by a docker inspect with a fixed format that never names its environment, its start '
                 'marker and its one receipt (the K9 runner\'s or the packaged risk executor\'s), and the files the receipt names hashed again '
                 'on the host. PROBE: one attached container of the signed image ID with the provider network, the provider environment file '
                 'of the K9 tree, no bind and a read-only root filesystem, running the pinned readiness snippet that calls only the certified '
                 'producer code of the image and prints counts and hashes. POLICY: the installed policy and release files read on the host and '
                 'the running worker\'s state and environment names as booleans. TREE: the rows of every directory of the K9 tree and of the '
                 'source root, the boot, the metadata of the secret files and the hash of the runner. It removes no container, writes no claim '
                 'and authorises nothing: only the outcome named as success criterion counts.')
SIDE_EFFECTS=['PROBE only: one attached docker run --rm named c3po-k9-<yyyymmdd of D>-<operation>; the engine creates it and removes it when its '
              'process ends; the command is timeout -s KILL %d and the snippet arms a %d s alarm, both inside the %d s limit of the docker CLI; '
              'a run whose CLI is killed first may leave the container to the engine until its process ends; this source lists no container'
              %(K9_PROBE_TIMEOUT_SECONDS,K9_PROBE_ALARM_SECONDS,COMMAND_CLASSES['RUN']['seconds']),
              'PROBE only: the docker CLI reads the provider environment file of the K9 tree as root and gives its values to that container; '
              'the container makes two HTTPS requests to the provider with them; nothing of the file reaches this process',
              'POLICY only: the values compared with the environment of the worker (two container paths, two hashes, the revision) travel '
              'in the argv of the docker CLI; none is a secret']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':dict(K9_SUCCESS),'epoch':K9_EPOCH,'days':list(K9_DAYS),'interface_note_sha256':K9_NOTE_SHA256,
       'operations_sha256':K9_OPERATIONS_SHA256,'read_operations':{name:list(row) for name,row in K9_READ_OPERATIONS.items()},
       'placement':K9_PLACEMENT,'parent_chains':list(K9_PARENT_CHAINS),
       'probe':{'snippet_sha256':K9_PROBE_SNIPPET_SHA256,'timeout_seconds':K9_PROBE_TIMEOUT_SECONDS,'alarm_seconds':K9_PROBE_ALARM_SECONDS,
                'network':K9_PROVIDER_NETWORK,'readiness_rule':K9_READINESS_RULE,'binds':'none','root_filesystem':'read-only',
                'command':['timeout','-s','KILL',str(K9_PROBE_TIMEOUT_SECONDS),'python','-I','-B','-','<D>','<request sha256>']},
       'contracts':{'launch_record':[K9_RECORD_SCHEMA,sorted(K9_RECORD_KEYS)],'start_marker':[K9_STARTED_SCHEMA,sorted(K9_STARTED_KEYS)],
                    'step_receipt':[K9_STEP_SCHEMA,sorted(K9_STEP_KEYS)],'packaged_receipt':[K9_PACKAGED_RECEIPT_SCHEMA,sorted(K9_PACKAGED_RECEIPT_KEYS)],
                    'output_key':K9_OUTPUT_KEY,'aggregate':'sha256 of the canonical JSON list of the sorted sha256 of every regular file of the directory'},
       'side_effects':SIDE_EFFECTS,
       'never':['a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','docker rm','docker ps','a claim',
                'a container with a bind','a shell','a pull','a systemctl verb','a value of an environment, a byte or size or digest of a secret file, '
                'a symbol of an instrument or a provider payload in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'small_file_bytes':K9_MAX_SMALL_FILE,'plan_file_bytes':K9_MAX_PLAN_FILE,'rehash_file_bytes':K9_MAX_REHASH_FILE,
                 'rehash_total_bytes':K9_MAX_REHASH_TOTAL,'aggregate_file_bytes':K9_MAX_AGGREGATE_FILE,'aggregate_entries':K9_MAX_AGGREGATE_ENTRIES,
                 'outputs':K9_MAX_OUTPUTS,'aggregates':K9_MAX_AGGREGATES,'runner_bytes':K9_MAX_RUNNER_FILE,'policy_bytes':K9_MAX_POLICY_FILE,
                 'release_bytes':K9_MAX_RELEASE_FILE,'standard_input_bytes':MAX_STDIN_BYTES,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


# ---------------------------------------------------------------- the signed plan (pure)
def k9_attempt_key(epoch,day,phase,operation):
    """The Act B single-use key: sha256 of the canonical list [epoch, day, phase, operation] (actb03_lib.attempt_key)."""
    return sha(canonical([epoch,day,phase,operation]))

def k9_previous_day(day):
    """The calendar day before D (not the previous session)."""
    return datetime.fromordinal(datetime.fromisoformat(day).toordinal()-1).date().isoformat()

def k9_days_before(day,count):
    return datetime.fromordinal(datetime.fromisoformat(day).toordinal()-count).date().isoformat()

def k9_container_name(day,operation):
    return K9_CONTAINER_PREFIX+day.replace('-','')+'-'+operation

def k9_parent_open_root(path):
    """The open root of a chain of the placement: the data volume for the source root, none for the K9 tree (N-8)."""
    return K9_DATA_VOLUME if inside(path,K9_DATA_VOLUME) else None

def k9_free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where none are counted."""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def k9_chain(item,path,open_root,receives_entry,code):
    """One signed directory: exactly {path, rows, open_root}; the path and the open root as compiled; rows from a read of the same boot."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and item['path']==path and item['open_root']==open_root and item['rows'] is not None,code)
    validate_chain(item['rows'],path,open_root,receives_entry)
    need(open_root is not None or k9_root_group_rows(item['rows']),'CHAIN_ROW_NOT_ROOT_GROUP')
    return item

def k9_free_chain(item,code):
    """A signed directory whose path the plan gives (the policy and the release directories)."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and type(item['path']) is str and clean_path(item['path']) and item['path']!='/'
         and item['rows'] is not None,code)
    root=item['open_root']
    need(root is None or (type(root) is str and clean_path(root) and root!='/' and inside(item['path'],root)),code)
    validate_chain(item['rows'],item['path'],root)
    return item

def k9_constants(plan):
    """The signed constants of the week: compared with the compiled values where this source has them, by grammar elsewhere."""
    values=plan['constants']
    need(type(values) is dict and set(values)==K9_CONSTANT_KEYS,'CONSTANTS_INVALID')
    need(values['k9_interface_note_sha256']==K9_NOTE_SHA256 and values['package_sha256']==K9_PACKAGE_SHA256
         and values['code_revision']==K9_CODE_REVISION,'CONSTANTS_NOT_THE_COMPILED_ONES')
    need(values['probe_snippet_sha256']==K9_PROBE_SNIPPET_SHA256 and values['readiness_rule']==K9_READINESS_RULE,'PROBE_CONSTANTS_NOT_THE_COMPILED_ONES')
    need(values['placement']==K9_PLACEMENT,'PLACEMENT_NOT_THE_COMPILED_ONE')
    need(all(hexpin(values[key]) for key in ('act_b_sha256','release_sha256','policy_sha256','runner_sha256','step_table_sha256','risk_source_pins_sha256'))
         and text(values['image_id'],IMAGE_ID),'CONSTANTS_INVALID')
    networks=values['networks']
    need(type(networks) is dict and set(networks)==set(K9_NETWORK_CLASSES) and all(text(value,K9_NETWORK_NAME) for value in networks.values()),'CONSTANTS_INVALID')
    need(networks['PROVIDER']==K9_PROVIDER_NETWORK,'NETWORKS_NOT_THE_COMPILED_ONES')
    limits=values['risk_limits']
    need(type(limits) is dict and set(limits)==set(K9_RISK_LIMIT_KEYS) and all(integer(value,1,K9_MAX_LIMIT) for value in limits.values()),'CONSTANTS_INVALID')
    need(integer(values['disk_floor_bytes'],0,K9_MAX_FLOOR),'CONSTANTS_INVALID')
    need(values['disk_floor_bytes']==K9_DISK_FLOOR_BYTES,'DISK_FLOOR_NOT_THE_COMPILED_ONE')
    return values

def k9_policy_read(plan):
    """POLICY: the installed policy and release files (directory rows signed, file names) and the worker's data bind."""
    value=plan['policy_read']
    need(type(value) is dict and set(value)=={'policy','release','worker'},'POLICY_READ_INVALID')
    worker=value['worker']
    need(type(worker) is dict and set(worker)=={'container','data_source','data_target'} and text(worker['container'],CONTAINER_NAME)
         and not text(worker['container'],CONTAINER_ID)
         and all(type(worker[key]) is str and clean_path(worker[key]) and worker[key]!='/' for key in ('data_source','data_target')),'POLICY_READ_INVALID')
    need(worker['data_source']==K9_DATA_VOLUME,'POLICY_READ_NOT_THE_DATA_VOLUME')
    for key in ('policy','release'):
        item=value[key]
        need(type(item) is dict and set(item)=={'directory','file_name'} and text(item['file_name'],K9_ENTRY),'POLICY_READ_INVALID')
        k9_free_chain(item['directory'],'POLICY_READ_INVALID')
        need(inside(item['directory']['path'],worker['data_source']) and item['directory']['path']!=worker['data_source'],'POLICY_READ_OUTSIDE_THE_DATA_VOLUME')
        need(clean_path(k9_in_worker(plan,key)) and len(k9_in_worker(plan,key))<=256,'POLICY_READ_INVALID')
    return value

def k9_host_file(plan,key):
    item=plan['policy_read'][key];return item['directory']['path']+'/'+item['file_name']
def k9_in_worker(plan,key):
    """A host file on the data volume as the worker sees it through its bind."""
    worker=plan['policy_read']['worker'];path=k9_host_file(plan,key);return worker['data_target']+path[len(worker['data_source']):]

def k9_expected_environment(plan):
    """The five names of the running worker after activate, with the values activate wrote (C3PO_R2D2_V2_*) and the revision."""
    values=plan['constants']
    return {'C3PO_R2D2_V2_LIVE_POLICY_FILE':k9_in_worker(plan,'policy'),'C3PO_R2D2_V2_LIVE_POLICY_SHA':values['policy_sha256'],
            'C3PO_R2D2_V2_SHADOW_RELEASE_FILE':k9_in_worker(plan,'release'),'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':values['release_sha256'],
            'C3PO_BUILD_SHA':values['code_revision']}

def k9_probe_command(day,request_sha256):
    return ['timeout','-s','KILL',str(K9_PROBE_TIMEOUT_SECONDS),'python','-I','-B','-',day,request_sha256]

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in K9_MODES,'MODE_INVALID')
    need(plan['epoch']==K9_EPOCH,'EPOCH_INVALID')
    values=k9_constants(plan)
    if mode=='TREE':
        need(all(plan[key] is None for key in ('day','k9_phase','k9_operation','slot','attempt_key','run_not_after','parent_rows',
                                               'evidence_boot_id_sha256','policy_read')),'TREE_PLAN_INVALID')
        return
    day=plan['day'];need(type(day) is str and day in K9_DAYS,'DAY_INVALID')
    operation=plan['k9_operation'];need(type(operation) is str and operation in K9_READ_OPERATIONS,'OPERATION_INVALID')
    phase,needed,launch=K9_READ_OPERATIONS[operation]
    need(needed==mode and plan['k9_phase']==phase,'OPERATION_NOT_OF_THIS_MODE')
    need(type(plan['slot']) is str and plan['slot'] in K9_SLOTS,'SLOT_INVALID')
    need(plan['attempt_key']==k9_attempt_key(K9_EPOCH,day,phase,operation),'ATTEMPT_KEY_MISMATCH')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    rows=plan['parent_rows']
    need(type(rows) is dict and set(rows)==set(K9_PARENT_CHAINS),'PARENT_ROWS_INVALID')
    for name in K9_PARENT_CHAINS:
        path=K9_PLACEMENT[name];k9_chain(rows[name],path,k9_parent_open_root(path),name in K9_RECEIVES_ENTRY,'PARENT_ROWS_INVALID')
    if mode=='RESULT':
        try:point=instant(plan['run_not_after'])
        except Refused:raise Refused('RUN_NOT_AFTER_INVALID') from None
        need(point.isoformat()==plan['run_not_after'],'RUN_NOT_AFTER_INVALID')
    else:need(plan['run_not_after'] is None,'RUN_NOT_AFTER_INVALID')
    if mode=='POLICY':k9_policy_read(plan)
    else:need(plan['policy_read'] is None,'POLICY_READ_INVALID')
    if mode=='PROBE':
        run_arguments('probe',values['image_id'],[],k9_probe_command(day,'0'*64),k9_container_name(day,operation))
        need(0<len(K9_PROBE_SNIPPET.encode('ascii'))<=MAX_STDIN_BYTES,'PROBE_SNIPPET_TOO_LARGE')

def k9_window_of(plan):
    """Pure, from the signed bytes, checked by perform before anything is observed (not by validate_plan: the core's
    conformance suite moves the window of one plan across every day of the date class). The window lies in the eve or
    the morning of D: from 20:00Z of D-1 (17:00 BRT) to 15:00Z of D (12:00 BRT). A probe ends before 04:00Z of D (the
    causal build's limit, 00:00 New York); the policy read is on D; a result opens at or after its launch's run_not_after."""
    if plan['mode']=='TREE':return None
    day=plan['day'];start,end=instant(plan['window']['not_before']),instant(plan['window']['expires_at'])
    low,high=instant(k9_previous_day(day)+'T20:00:00+00:00'),instant(day+'T15:00:00+00:00')
    need(low<=start and end<=high,'WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    if plan['mode']=='PROBE':need(end<=instant(day+'T04:00:00+00:00'),'WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    if plan['mode']=='POLICY':need(start>=instant(day+'T00:00:00+00:00'),'WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    if plan['mode']=='RESULT':
        limit=instant(plan['run_not_after']);need(low<=limit<=high,'RUN_NOT_AFTER_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
        need(start>=limit,'RESULT_WINDOW_BEFORE_RUN_NOT_AFTER')
    return {'not_before':start.isoformat(),'expires_at':end.isoformat()}

def k9_chain_effects(item):
    return dict(chain_effects(item['rows']),open_root=item['open_root'])

def k9_reads_of(plan):
    """What each mode reads, as the signers see it."""
    mode=plan['mode'];values=plan['constants']
    if mode=='TREE':
        return {'directories':{key:K9_PLACEMENT[name] for key,name in K9_TREE_DIRECTORIES},
                'secret_files_lstat_only':[K9_PLACEMENT[{'SECRETS':'secrets','EMITTER':'emitter'}[key]]+'/'+name for key,name in K9_SECRET_FILES],
                'runner_file':K9_PLACEMENT['tools']+'/k9_runner-'+values['runner_sha256']+'.py',
                'september_sources_lstat_only':['/'.join((K9_DATA_VOLUME,)+chain[:index+1]) for chain in K9_SEPTEMBER_SOURCES for index in range(len(chain))],'disk_floor_bytes':values['disk_floor_bytes'],
                'rows_in_receipt':True,'boot_id_sha256_in_receipt':True}
    day,operation=plan['day'],plan['k9_operation'];phase,_,launch=K9_READ_OPERATIONS[operation]
    if mode=='RESULT':
        packaged=K9_PACKAGED_PHASES.get(launch)
        return {'launch':launch,'launch_attempt_key':k9_attempt_key(K9_EPOCH,day,phase,launch),'container_name':k9_container_name(day,launch),
                'image_id':values['image_id'],'launch_record':K9_PLACEMENT['days']+'/'+day+'/launches/'+launch+'.json',
                'receipts':'PACKAGED_RISK_SPOOL' if packaged else 'K9_RUNNER',
                'receipt_directory':(K9_PLACEMENT['days']+'/'+day+'/risk/spool/<sha256 of risk/plan/HOST_PLAN.json>') if packaged
                                    else K9_PLACEMENT['days']+'/'+day+'/receipts','packaged_phase':packaged,
                'outputs_hashed_again':'every file and aggregate the receipt names, below days/<D> (day/) or the source root (source/)' if not packaged
                                       else ('acquired/acquired.json' if packaged=='acquire' else 'assessment/<manifest>, risk-output/MANIFEST.json, risk-output/risk.json'),
                'run_not_after':plan['run_not_after']}
    if mode=='PROBE':
        return {'image_id':values['image_id'],'container_name':k9_container_name(day,operation),'network':K9_PROVIDER_NETWORK,
                'env_file':K9_PLACEMENT['provider_env_file'],'command':k9_probe_command(day,'<request sha256>'),
                'snippet_sha256':K9_PROBE_SNIPPET_SHA256,'timeout_seconds':K9_PROBE_TIMEOUT_SECONDS,'alarm_seconds':K9_PROBE_ALARM_SECONDS,
                'readiness_rule':K9_READINESS_RULE,'binds':[]}
    value=plan['policy_read']
    return {'policy_file':k9_host_file(plan,'policy'),'release_file':k9_host_file(plan,'release'),
            'policy_directory':k9_chain_effects(value['policy']['directory']),'release_directory':k9_chain_effects(value['release']['directory']),
            'worker':value['worker'],'expected_environment':k9_expected_environment(plan),'image_id':values['image_id']}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    rows=plan['parent_rows']
    return {'operation':OPERATION,'mode':plan['mode'],'epoch':plan['epoch'],'day':plan['day'],'k9_phase':plan['k9_phase'],
            'k9_operation':plan['k9_operation'],'slot':plan['slot'],'attempt_key':plan['attempt_key'],'run_not_after':plan['run_not_after'],
            'constants':plan['constants'],'parent_rows':None if rows is None else {name:k9_chain_effects(rows[name]) for name in K9_PARENT_CHAINS},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'reads':k9_reads_of(plan),
            'writes':0,'claims':0,'containers_removed':0,'containers_run':1 if plan['mode']=='PROBE' else 0,'activation':False}
def success_of(plan):
    return K9_SUCCESS.get(plan['mode'],COMPLETE_OUTCOME)


# ---------------------------------------------------------------- observations
def k9_item(status='COMPLETE',findings=(),**fields):
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

def k9_child(host,parent_fd,name,gate):
    """A directory entry of a held directory, classified by lstat and opened without following a link: (fd, fstat)."""
    gate();named=host.lstat(name,parent_fd)
    need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT');need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent_fd)
    try:
        info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED');return fd,info
    except BaseException:
        host.close(fd);raise

def k9_descend(host,base_fd,parts,gate):
    """The directory reached from a held one by the given names (each opened without following a link). The caller
    closes what is returned; nothing is returned for no name (the held one itself)."""
    fd=None
    try:
        for part in parts:
            child,_=k9_child(host,base_fd if fd is None else fd,part,gate)
            if fd is not None:host.close(fd)
            fd=child
        return fd
    except BaseException:
        if fd is not None:host.close(fd)
        raise

def k9_read(host,base_fd,parts,gate,limit):
    """(bytes, fstat) of a regular file below a held directory. FileNotFoundError when a component or the file is absent."""
    fd=k9_descend(host,base_fd,parts[:-1],gate)
    try:
        gate();named=host.lstat(parts[-1],base_fd if fd is None else fd)
        need(stat.S_ISREG(named.st_mode),'FILE_NOT_REGULAR')
        raw,info=read_regular(host,parts[-1],base_fd if fd is None else fd,gate,limit)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'FILE_CHANGED_DURING_READ');return raw,info
    finally:
        if fd is not None:host.close(fd)

def k9_private(info,mode):
    return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink==1)

def k9_document(raw,code):
    try:value=strict(raw,K9_MAX_PLAN_FILE)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

def k9_counts(value,depth=0):
    """A runner's counts: integer values, keys in K9_COUNT_KEY, two levels. A receipt with anything else there (a name of
    an instrument, a path) is not a receipt of this step."""
    return (type(value) is dict and len(value)<=K9_MAX_COUNTS
            and all(text(key,K9_COUNT_KEY) and (integer(item,0,K9_MAX_COUNT) or (depth==0 and k9_counts(item,1))) for key,item in value.items()))

def k9_packaged_counts(value):
    """The packaged executor's counts: its own closed list of names, integer values."""
    return type(value) is dict and all(key in K9_PACKAGED_COUNT_NAMES and integer(item,0,K9_MAX_COUNT) for key,item in value.items())

def k9_docker_instant(value):
    """A docker StartedAt/FinishedAt (RFC 3339, nanoseconds, Z) as an instant; None when it is not one."""
    found=re.fullmatch(r'([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\.[0-9]{1,9})?Z',value) if type(value) is str else None
    if found is None:return None
    try:return instant(found.group(1)+(found.group(2) or '')[:7]+'+00:00')
    except Refused:return None

def k9_root_group_rows(rows):
    """Every component of a K9 chain in the group of root and not setgid (K4-E0's rule for the same chain)."""
    return all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows)

def k9_launched_facts(commands,target):
    """The RESULT read of one container by its 64-hex ID with this source's own format."""
    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')
    row=decode(commands.output('launched',target))
    need(set(row)==K9_LAUNCHED_KEYS and row['id']==target and text(row['name'],'/'+CONTAINER_NAME) and text(row['image_id'],IMAGE_ID)
         and type(row['state']) is str and row['state'] in CONTAINER_STATES and type(row['running']) is bool and type(row['oom_killed']) is bool
         and integer(row['exit_code'],-1,255) and all(type(row[key]) is str and len(row[key])<=64 for key in ('started_at','finished_at'))
         and all(row[key] in ('',None) or text(row[key],HEX64) for key in ('attempt_key','request_sha256')),'LAUNCHED_METADATA_INVALID')    # a missing label: '' typed, null raw
    return row

def k9_probe_line(raw,returncode,plan,request_sha256):
    """The one line the snippet prints, member by member. None when a run that failed printed nothing readable."""
    try:line=single_line(raw)
    except Refused:
        need(returncode!=0,'PROBE_OUTPUT_INVALID');return None
    if returncode!=0:
        ok=(set(line)==K9_PROBE_FAILED_KEYS and line['status']=='FAILED' and text(line['code'],K9_SNIPPET_CODE) and integer(line['logical_fetch_calls'],0,2)
            and line['request_sha256'] in (None,request_sha256))
        return line if ok else None
    need(set(line)==K9_PROBE_DONE_KEYS and line['status']=='DONE' and line['request_sha256']==request_sha256 and line['day']==plan['day']
         and line['logical_fetch_calls']==2 and all(integer(line[key],0,K9_MAX_COUNT) for key in K9_PROBE_COUNTS)
         and text(line['previous_session'],K9_DAY) and k9_days_before(plan['day'],7)<=line['previous_session']<plan['day']
         and all(text(line[key],HEX64) for key in ('registry_payload_sha256','bulk_payload_sha256'))
         and text(line['python'],r'[0-9]{1,2}\.[0-9]{1,3}\.[0-9]{1,3}'),'PROBE_OUTPUT_INVALID')
    eligible,present=line['eligible_symbols'],line['present_eligible_symbols']
    numerator,denominator=K9_READINESS_RULE['numerator'],K9_READINESS_RULE['denominator']
    ready=eligible>=K9_MINIMUM_ELIGIBLE and denominator*present>=numerator*eligible
    need(present<=eligible<=line['registry_symbols'] and line['usable_eligible_symbols']+line['conflicting_eligible_symbols']<=present
         and line['dated_rows']<=line['bulk_rows'] and line['required_minimum']==(numerator*eligible+denominator-1)//denominator
         and line['readiness']==('READY' if ready else 'NOT_READY'),'PROBE_OUTPUT_INVALID')
    return line


class K9Reader:
    """The observations of one run. Each method is one item of the receipt and fails on its own."""
    def __init__(self,plan,host,gate,commands,bound,clock,monotonic):
        self.plan,self.host,self.gate,self.commands,self.clock,self.monotonic=plan,host,gate,commands,clock,monotonic
        self.mode=plan['mode'];self.values=plan['constants'];self.held={};self.same_boot=True;self.request_sha256=bound['request_sha256']
        self.image_ok=False;self.record=None;self.launched=None;self.receipt=None;self.receipt_ok=False;self.manifest=None;self.worker_id=None;self.boot_hash=None;self.env_ok=False
        if self.mode in ('RESULT','PROBE','POLICY'):
            self.day=plan['day'];self.operation=plan['k9_operation'];self.phase,_,self.launch=K9_READ_OPERATIONS[self.operation]
        if self.mode=='RESULT':
            self.launch_key=k9_attempt_key(K9_EPOCH,self.day,self.phase,self.launch);self.packaged=K9_PACKAGED_PHASES.get(self.launch)

    def boot(self):
        self.boot_hash=boot_id_sha256(self.host,self.gate)
        if self.mode=='TREE':return k9_item(boot_id_sha256=self.boot_hash)     # the boot the week's requests will sign
        self.same_boot=self.boot_hash==self.plan['evidence_boot_id_sha256']
        return k9_item(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=self.same_boot,device_numbers_compared=self.same_boot)

    def directory(self,key,path,spec=None,private=True):
        """One directory walked from "/" without following a link and held to the end of the run: against the signed
        rows when there are, otherwise recorded (TREE) with its rows in the receipt."""
        host=self.host;observed=[];findings=[];fd=None
        try:
            if spec is None:fd=descend(host,path,self.gate,observed)
            else:fd=walk_pinned(host,spec['rows'],self.gate,observed,self.same_boot)
        except FileNotFoundError:findings.append('PARENT_MISSING')
        except Refused as error:
            if str(error) not in K9_WALK_FINDINGS:raise
            findings.append(str(error))
        facts={'path':path,'rows_signed':spec is not None,'components_observed':len(observed),'held':fd is not None}
        if fd is None:
            if spec is not None and findings==['PARENT_IDENTITY_MISMATCH']:
                facts['fields_that_differ']={field:observed[-1][field]!=spec['rows'][len(observed)-1][field] for field in K9_ROW_FIELDS}
            if spec is None:facts['observed_rows']=observed
            return k9_item(findings=findings,**facts)
        try:self.held[key]=Pinned(host,fd,rows=[dict(row) for row in observed] if spec is None else spec['rows'],compare_device=spec is None or self.same_boot)
        except BaseException:
            host.close(fd);raise
        leaf=observed[-1];open_root=k9_parent_open_root(path)
        try:validate_chain([dict(row) for row in observed],path,open_root);acceptable=open_root is not None or k9_root_group_rows(observed)
        except Refused:acceptable=False
        on_volume=None if open_root is None else mount_point_of(observed)==K9_DATA_VOLUME
        root_private=(leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,K9_PRIVATE_DIRECTORY_MODE)
        if private and not root_private:findings.append('DIRECTORY_NOT_ROOT_PRIVATE')
        if spec is None and not acceptable:findings.append('ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS')
        if spec is None and on_volume is False:findings.append('DATA_VOLUME_NOT_A_MOUNT_POINT')
        # every component from "/": owned by root and closed to group and other writes (outside an open root)
        loose=[row['path'] for row in observed if (not row_root_safe(row) or (open_root is None and not k9_root_group_rows([row])))
               and (open_root is None or not inside(row['path'],open_root))]
        available=free_bytes(host,fd)
        facts.update(as_signed=None if spec is None else True,owner_uid=leaf['uid'],owner_gid=leaf['gid'],mode_octal='%04o'%leaf['mode'],
                     root_private=root_private,rows_acceptable_to_the_k9_requests=acceptable,mount_point_is_the_data_volume=on_volume,
                     open_root=open_root,components_not_root_controlled=loose,
                     mount_point_by_device_change=mount_point_of(observed),bytes_available=available,
                     entries=count_entries(host,fd,self.gate,K9_MAX_COUNT))
        if spec is None:facts['observed_rows']=observed
        return k9_item(findings=findings,**facts)

    def k9_filesystem(self,floor):
        """The filesystem of the K9 tree: one device for k9_root and every directory below it (no mount inside the tree),
        the source root on the filesystem of days/ (decision 6: one floor), free bytes of days/ against the signed floor
        and free inodes."""
        root=self.held.get('K9_ROOT');need(root is not None,'DIRECTORY_NOT_HELD');root.verify(self.gate)
        device=root.identity[0];keys=[key for key,_ in K9_TREE_DIRECTORIES if key not in ('K9_ROOT','SOURCE_ROOT')]
        held=[key for key in keys if key in self.held];spans=[key for key in held if self.held[key].identity[0]!=device]
        source=self.held.get('SOURCE_ROOT')
        days=self.held.get('DAYS');need(days is not None,'DIRECTORY_NOT_HELD');days.verify(self.gate)
        # the floor is judged on the filesystem that contains days/, by fstatvfs of its own open descriptor (f_bavail * f_frsize)
        available,inodes=free_bytes(self.host,days.fd),k9_free_inodes(self.host,days.fd)
        if source is not None:source.verify(self.gate)
        together=None if source is None else source.identity[0]==days.identity[0]
        findings=(['K9_TREE_SPANS_FILESYSTEMS'] if spans else [])+(['SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS'] if together is False else [])
        if available<floor:findings.append('DISK_FREE_BELOW_FLOOR')
        return k9_item(findings=findings,directories_compared=len(held),directories_on_another_device=spans,
                       source_root_on_the_filesystem_of_days=together,days_bytes_available=available,floor_bytes=floor,hold=available<floor,
                       days_inodes_available=inodes,
                       filesystem_type='NOT_EXPOSED_BY_THE_CORE')

    def september_sources(self):
        """The September secret sources, below the data volume walked from "/" (the volume's open root, its rows in the
        receipt): per component its identity, owner, mode, both change instants, links and whether it is a link, by
        lstat in the held parent; a directory is opened by descriptor without following a link to reach the next; the
        file at the end is never opened. Never a size, a length or a digest."""
        rows=[];volume=descend(self.host,K9_DATA_VOLUME,self.gate,rows)
        try:
            device=self.host.fstat(volume).st_dev;findings=[];components=[]
            try:validate_chain([dict(row) for row in rows],K9_DATA_VOLUME,K9_DATA_VOLUME);acceptable=True
            except Refused:acceptable=False
            if not acceptable:findings.append('DATA_VOLUME_ROWS_NOT_ACCEPTABLE')
            if mount_point_of(rows)!=K9_DATA_VOLUME:findings.append('DATA_VOLUME_NOT_A_MOUNT_POINT')
            for chain in K9_SEPTEMBER_SOURCES:
                fd=None;path=K9_DATA_VOLUME
                try:
                    for index,name in enumerate(chain):
                        path+='/'+name;self.gate()
                        try:found=self.host.lstat(name,volume if fd is None else fd)
                        except FileNotFoundError:
                            findings.append('SEPTEMBER_SOURCE_ABSENT');components.append({'path':path,'exists':False});break
                        link=stat.S_ISLNK(found.st_mode);directory=stat.S_ISDIR(found.st_mode)
                        components.append({'path':path,'exists':True,'type':kind(found.st_mode),'device':found.st_dev,'inode':found.st_ino,'uid':found.st_uid,
                                           'gid':found.st_gid,'mode_octal':'%04o'%stat.S_IMODE(found.st_mode),'mtime_ns':found.st_mtime_ns,
                                           'ctime_ns':found.st_ctime_ns,'nlink':found.st_nlink,'is_link':link})
                        if link:findings.append('SEPTEMBER_SOURCE_IS_A_LINK');break
                        if found.st_dev!=device:findings.append('SEPTEMBER_SOURCE_ON_ANOTHER_DEVICE')
                        last=index==len(chain)-1
                        if directory and found.st_mode&0o022:findings.append('SEPTEMBER_DIRECTORY_GROUP_OR_WORLD_WRITABLE')
                        if last:
                            if not stat.S_ISREG(found.st_mode):findings.append('SEPTEMBER_SOURCE_NOT_A_REGULAR_FILE')
                            break
                        if not directory:findings.append('SEPTEMBER_SOURCE_NOT_A_DIRECTORY');break
                        child,_=k9_child(self.host,volume if fd is None else fd,name,self.gate)
                        if fd is not None:self.host.close(fd)
                        fd=child
                finally:
                    if fd is not None:self.host.close(fd)
            return k9_item(findings=findings,data_volume_rows=rows,data_volume_rows_acceptable=acceptable,data_volume_device=device,components=components)
        finally:self.host.close(volume)

    def secret_file(self,key,name):
        """lstat only: type, owner, mode, links. Never the content, the size, a digest or the identity of a secret."""
        parent=self.held.get(key);need(parent is not None,'DIRECTORY_NOT_HELD')
        parent.verify(self.gate);self.gate()
        try:found=self.host.lstat(name,parent.fd)
        except FileNotFoundError:return k9_item(findings=['SECRET_FILE_ABSENT'],name=name,exists=False)
        regular=stat.S_ISREG(found.st_mode);private=regular and k9_private(found,K9_PRIVATE_FILE_MODE)
        return k9_item(findings=[] if private else ['SECRET_FILE_NOT_PRIVATE'],name=name,exists=True,type=kind(found.st_mode),owner_uid=found.st_uid,
                       owner_gid=found.st_gid,mode_octal='%04o'%stat.S_IMODE(found.st_mode),links=found.st_nlink,private=private)

    def runner_file(self):
        """The content-addressed runner of the tools directory: its bytes hash to the signed runner hash; root's, private."""
        parent=self.held.get('TOOLS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(self.gate)
        name='k9_runner-'+self.values['runner_sha256']+'.py'
        try:raw,info=k9_read(self.host,parent.fd,[name],self.gate,K9_MAX_RUNNER_FILE)
        except FileNotFoundError:return k9_item(findings=['RUNNER_FILE_ABSENT'],exists=False)
        equal=sha(raw)==self.values['runner_sha256'];private=k9_private(info,K9_PRIVATE_FILE_MODE)
        return k9_item(findings=([] if equal else ['RUNNER_BYTES_NOT_THE_SIGNED_ONES'])+([] if private else ['RUNNER_FILE_NOT_PRIVATE']),
                       exists=True,bytes_equal_signed=equal,private=private,owner_uid=info.st_uid,owner_gid=info.st_gid,
                       mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink,size=info.st_size)

    # -------------------------------------------------------------- RESULT
    def day_directory(self):
        """days/<D>: created 0700 by the first launch of the eve; held for the reads below."""
        days=self.held.get('DAYS');need(days is not None,'DIRECTORY_NOT_HELD');days.verify(self.gate)
        try:fd,info=k9_child(self.host,days.fd,self.day,self.gate)
        except FileNotFoundError:return k9_item(exists=False)
        try:self.held['DAY']=Pinned(self.host,fd,parent=days,name=self.day)
        except BaseException:
            self.host.close(fd);raise
        private=k9_private(info,K9_PRIVATE_DIRECTORY_MODE)
        return k9_item(findings=[] if private else ['DAY_DIRECTORY_NOT_PRIVATE'],exists=True,private=private,
                       on_the_device_of_days=info.st_dev==days.identity[0])

    def launch_record(self):
        """launches/<launch>.json, written by K9W after start: which container this step is."""
        day=self.held.get('DAY')
        if day is None:return k9_item(exists=False,valid=False,day_directory_held=False)
        day.verify(self.gate)
        try:raw,info=k9_read(self.host,day.fd,['launches',self.launch+'.json'],self.gate,K9_MAX_SMALL_FILE)
        except FileNotFoundError:return k9_item(exists=False,valid=False)
        record=k9_document(raw,'LAUNCH_RECORD_INVALID');plan=self.plan
        valid=(set(record)==K9_RECORD_KEYS and record['schema']==K9_RECORD_SCHEMA and record['epoch']==K9_EPOCH and record['day']==self.day
               and record['operation']==self.launch and record['attempt_key']==self.launch_key and record['slot'] in K9_SLOTS
               and hexpin(record['request_sha256']) and hexpin(record['step_plan_sha256']) and text(record['container_id'],CONTAINER_ID)
               and record['container_name']==k9_container_name(self.day,self.launch) and integer(record['timeout_seconds'],1,7200))
        if valid:
            try:valid=instant(record['created_at'])<=instant(record['started_at'])<=instant(plan['run_not_after'])
            except Refused:valid=False
        if valid:self.record=record
        private=k9_private(info,K9_PRIVATE_FILE_MODE)
        return k9_item(findings=([] if valid else ['LAUNCH_RECORD_INVALID'])+([] if private else ['LAUNCH_RECORD_NOT_PRIVATE']),exists=True,valid=valid,
                       private=private,record_sha256=sha(raw),slot=record.get('slot') if valid else None,
                       container_id=record['container_id'] if valid else None,timeout_seconds=record['timeout_seconds'] if valid else None)

    def launched_container(self):
        """The container the record names, by its ID: identity, state, exit code, OOM kill; the labels K9W set."""
        record=self.record
        if record is None:return k9_item(observed=False)
        row=k9_launched_facts(self.commands,record['container_id']);self.launched=row
        as_recorded=(row['name']=='/'+record['container_name'] and row['image_id']==self.values['image_id']
                     and row['attempt_key']==self.launch_key and row['request_sha256']==record['request_sha256'])
        exited=row['state']=='exited' and row['running'] is False
        findings=([] if as_recorded else ['LAUNCHED_CONTAINER_NOT_AS_RECORDED'])+([] if exited else ['LAUNCHED_CONTAINER_NOT_EXITED'])
        return k9_item(findings=findings,observed=True,as_recorded=as_recorded,name_equal=row['name']=='/'+record['container_name'],
                       image_equal_signed=row['image_id']==self.values['image_id'],labels_equal=row['attempt_key']==self.launch_key and row['request_sha256']==record['request_sha256'],
                       state=row['state'],running=row['running'],exit_code=row['exit_code'],oom_killed=row['oom_killed'],
                       started_at=row['started_at'],finished_at=row['finished_at'])

    def _marker(self,base,parts,limit=K9_MAX_SMALL_FILE):
        try:raw,info=k9_read(self.host,base,parts,self.gate,limit)
        except FileNotFoundError:return None
        return raw,info

    def step_receipts(self):
        """The start marker and the one receipt of the step: the K9 runner's in days/<D>/receipts, or the packaged risk
        executor's in its spool directory named by the hash of the signed host plan."""
        day=self.held.get('DAY')
        if day is None:return k9_item(observed=False)
        day.verify(self.gate)
        return self._packaged(day) if self.packaged else self._runner(day)

    def _identity_ok(self,document,keys,schema):
        record=self.record
        return (set(document)==keys and document['schema']==schema and document['epoch']==K9_EPOCH and document['day']==self.day
                and document['phase']==self.phase and document['operation']==self.launch and document['attempt_key']==self.launch_key
                and record is not None and document['step_plan_sha256']==record['step_plan_sha256'])

    def _times_ok(self,first,second):
        try:return instant(first)<=instant(second)<=self.clock()
        except Refused:return False

    def _tied(self,started,completed=None):
        """A step file belongs to this launch in time: it starts at or after the record's created_at and the container's
        StartedAt, and it completes at or before the container's FinishedAt."""
        record,row=self.record,self.launched
        if record is None or row is None:return False
        try:
            begun=instant(started);created=instant(record['created_at'])
            ended=None if completed is None else instant(completed)
        except Refused:return False
        container_start,container_end=k9_docker_instant(row['started_at']),k9_docker_instant(row['finished_at'])
        if container_start is None or begun<created or begun<container_start:return False
        return ended is None or (container_end is not None and ended<=container_end)

    def _runner(self,day):
        base=day.fd;found={}
        for name,suffix in (('started','STARTED'),('receipt','RECEIPT'),('failed','FAILED')):
            found[name]=self._marker(base,['receipts',self.launch+'.'+suffix+'.json'])
        facts={'observed':True,'source':'K9_RUNNER','started':found['started'] is not None,'receipt':found['receipt'] is not None,
               'failed':found['failed'] is not None,'started_valid':None,'receipt_valid':None,'failed_valid':None,'failed_status':None,'receipt_sha256':None}
        findings=[];documents={}
        for name in ('started','receipt','failed'):
            if found[name] is None:continue
            raw,info=found[name];document=k9_document(raw,'STEP_RECEIPT_INVALID');documents[name]=document
            if not k9_private(info,K9_PRIVATE_FILE_MODE):findings.append('STEP_FILE_NOT_PRIVATE')
            if name=='started':
                facts['started_valid']=(self._identity_ok(document,K9_STARTED_KEYS,K9_STARTED_SCHEMA) and self._times_ok(document['started_at'],document['started_at'])
                                        and self._tied(document['started_at']))
                continue
            ok=(self._identity_ok(document,K9_STEP_KEYS,K9_STEP_SCHEMA) and document['package_sha256']==K9_PACKAGE_SHA256
                and document['build_sha']==K9_CODE_REVISION and self._times_ok(document['started_at'],document['completed_at'])
                and k9_outputs_ok(document['outputs'],document['aggregates']) and k9_counts(document['counts'])
                and self._tied(document['started_at'],document['completed_at']))
            if name=='receipt':ok=ok and document['status']=='COMPLETE' and document['code'] is None
            else:
                ok=ok and document['status'] in K9_STEP_FAILED_STATUSES and text(document['code'],K9_CONSTANT_CODE)
                facts['failed_status']=document.get('status') if ok else None;facts['failed_code']=document.get('code') if ok else None
            facts[name+'_valid']=ok;facts[name+'_sha256']=sha(raw)
            if ok:facts[name+'_counts']=document['counts']
        self.receipt=documents;self.receipt_ok=facts['receipt_valid'] is True
        return k9_item(findings=findings,**facts)

    def _packaged(self,day):
        """The packaged CLI's own files (risk_host_executor.py): phase.STARTED/RECEIPT/FAILED.json in spool/<manifest sha256>."""
        base=day.fd;phase=self.packaged
        plan_raw=self._marker(base,['risk','plan','HOST_PLAN.json'],K9_MAX_PLAN_FILE);go_raw=self._marker(base,['risk','plan','GO.json'],K9_MAX_PLAN_FILE)
        facts={'observed':True,'source':'PACKAGED_RISK_SPOOL','phase':phase,'host_plan_present':plan_raw is not None,'go_present':go_raw is not None,
               'started':False,'receipt':False,'failed':False,'started_valid':None,'receipt_valid':None,'failed_valid':None,'failed_status':None,'receipt_sha256':None}
        if plan_raw is None or go_raw is None:return k9_item(**facts)
        manifest,go=sha(plan_raw[0]),sha(go_raw[0]);facts.update(manifest_sha256=manifest,go_sha256=go)
        found={}
        for name,suffix in (('started','STARTED'),('receipt','RECEIPT'),('failed','FAILED')):
            found[name]=self._marker(base,['risk','spool',manifest,phase+'.'+suffix+'.json'],K9_MAX_PLAN_FILE)
            facts[name]=found[name] is not None
        documents={};namespaces=[prefix+self.day for prefix in K9_RISK_NAMESPACES]
        # the packaged chain: the receipt names the hash of the previous phase's receipt in the same spool
        prior=self._marker(base,['risk','spool',manifest,{'acquire':'preflight','execute':'acquire'}[phase]+'.RECEIPT.json'],K9_MAX_PLAN_FILE)
        previous=None if prior is None else sha(prior[0]);facts['previous_receipt_present']=prior is not None
        for name in ('started','receipt','failed'):
            if found[name] is None:continue
            raw=found[name][0];document=k9_document(raw,'STEP_RECEIPT_INVALID');documents[name]=document
            bound=document.get('manifest_sha256')==manifest and document.get('go_sha256')==go and document.get('phase')==phase
            if name=='started':
                facts['started_valid']=bool(set(document)==K9_PACKAGED_STARTED_KEYS and bound and type(document['started_at']) is str
                                            and self._times_ok(document['started_at'],document['started_at']) and self._tied(document['started_at']));continue
            if name=='receipt':
                ok=(set(document)==K9_PACKAGED_RECEIPT_KEYS and document['schema']==K9_PACKAGED_RECEIPT_SCHEMA and bound and document['status']=='COMPLETE'
                    and document['session_date']==self.day and document['namespace'] in namespaces and document['operation_activation'] is False
                    and document['certification_granted'] is False and type(document['outputs']) is dict
                    and type(document['started_at']) is str and type(document['completed_at']) is str and self._times_ok(document['started_at'],document['completed_at'])
                    and self._tied(document['started_at'],document['completed_at']) and k9_packaged_counts(document['outputs'].get('counts',{}))
                    and previous is not None and document['previous_receipt_sha256']==previous)
                if ok:
                    facts['namespace_form']='DIAG_R4' if document['namespace']==namespaces[0] else 'SHADOW'
                    facts['receipt_counts']=document['outputs'].get('counts')
            else:
                ok=(document.get('schema')==K9_PACKAGED_FAILED_SCHEMA and bound and document.get('status') in ('UNCERTAIN','REFUSED')
                    and (text(document.get('code'),K9_CONSTANT_CODE) or document.get('code') in K9_PACKAGED_CODES_WITHOUT_UNDERSCORE)
                    and document.get('previous_receipt_sha256') in (None,previous))
                facts['failed_status']=document.get('status') if ok else None;facts['failed_code']=document.get('code') if ok else None
            facts[name+'_valid']=bool(ok);facts[name+'_sha256']=sha(raw)
        self.receipt=documents;self.manifest=manifest;self.receipt_ok=facts['receipt_valid'] is True
        return k9_item(**facts)

    def outputs(self):
        """The files the receipt names, read again on the host and hashed; directories aggregated as the receipt says.
        Names of files never leave this method: only counts and booleans."""
        documents=self.receipt or {};receipt=documents.get('receipt')
        if receipt is None or not self.receipt_ok:return k9_item(applicable=False,all_equal=None)
        day=self.held.get('DAY');need(day is not None,'DIRECTORY_NOT_HELD')
        expected={};aggregates={}
        if self.packaged:
            outputs=receipt['outputs'];prefix=['risk','spool',self.manifest]
            try:
                if self.packaged=='acquire':
                    reference=outputs['acquired_manifest'];need(reference['path']=='acquired.json' and text(reference['sha256'],HEX64),'OUTPUT_REFERENCE_INVALID')
                    expected[('day',tuple(prefix+['acquired','acquired.json']))]=reference['sha256']
                else:
                    reference=outputs['assessment_manifest'];need(text(reference['path'],K9_ENTRY) and text(reference['sha256'],HEX64),'OUTPUT_REFERENCE_INVALID')
                    expected[('day',tuple(prefix+['assessment',reference['path']]))]=reference['sha256']
                    need(text(outputs['output_manifest_sha256'],HEX64) and text(outputs['risk_sha256'],HEX64),'OUTPUT_REFERENCE_INVALID')
                    expected[('day',tuple(prefix+['risk-output','MANIFEST.json']))]=outputs['output_manifest_sha256']
                    expected[('day',tuple(prefix+['risk-output','risk.json']))]=outputs['risk_sha256']
            except (KeyError,TypeError):raise Refused('OUTPUT_REFERENCE_INVALID') from None
        else:
            for key,value in receipt['outputs'].items():
                parts=key.split('/');expected[(parts[0],tuple(parts[1:]))]=value
            for key,value in receipt['aggregates'].items():
                parts=key.split('/');aggregates[(parts[0],tuple(parts[1:]))]=value
        source=self.held.get('SOURCE_ROOT')
        if any(root=='source' for root,_ in list(expected)+list(aggregates)):need(source is not None,'DIRECTORY_NOT_HELD')
        total=0;equal=absent=other=0
        for (root,parts),digest in sorted(expected.items()):
            base=day if root=='day' else source;base.verify(self.gate)
            try:
                raw,_=k9_read(self.host,base.fd,list(parts),self.gate,K9_MAX_REHASH_FILE)
                total+=len(raw);need(total<=K9_MAX_REHASH_TOTAL,'OUTPUT_BYTES_LIMIT')
                if sha(raw)==digest:equal+=1
                else:other+=1
            except FileNotFoundError:absent+=1
            except Refused as error:
                if str(error) not in ('FILE_NOT_REGULAR','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY'):raise
                other+=1
        aggregate_equal=aggregate_other=0
        for (root,parts),value in sorted(aggregates.items()):
            base=day if root=='day' else source;base.verify(self.gate)
            if self._aggregate(base.fd,list(parts),value):aggregate_equal+=1
            else:aggregate_other+=1
        ok=absent==0 and other==0 and aggregate_other==0
        return k9_item(findings=[] if ok else ['OUTPUT_NOT_AS_THE_RECEIPT_SAYS'],applicable=True,all_equal=ok,files=len(expected),files_equal=equal,
                       files_absent=absent,files_different_or_not_regular=other,aggregates=len(aggregates),aggregates_equal=aggregate_equal,bytes_hashed=total)

    def _aggregate(self,base_fd,parts,value):
        """A directory the receipt describes as {files, sha256}: every entry a regular file, the sorted hashes hashed."""
        try:fd=k9_descend(self.host,base_fd,parts,self.gate)
        except FileNotFoundError:return False
        except Refused as error:
            if str(error) in ('SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY'):return False
            raise
        try:
            digests=[];names=list(self.host.names(fd));need(len(names)<=K9_MAX_AGGREGATE_ENTRIES,'ENTRY_LIMIT')
            for name in names:
                self.gate();named=self.host.lstat(name,fd)
                if not stat.S_ISREG(named.st_mode):return False
                raw,_=read_regular(self.host,name,fd,self.gate,K9_MAX_AGGREGATE_FILE);digests.append(sha(raw))
            return len(digests)==value['files'] and sha(canonical(sorted(digests)))==value['sha256']
        finally:self.host.close(fd)

    # -------------------------------------------------------------- PROBE
    def provider_env(self):
        found=self.secret_file('SECRETS','provider.env');self.env_ok=found['status']=='COMPLETE' and found.get('private') is True;return found

    def probe_run(self):
        """The one container of PROBE: started only when the provider env file is the private regular file of root in the
        held secrets directory and the signed image ID is present with the signed revision (the QUICK read before it).
        A CONTAINER row needs its whole class time and 4 s: 44 s, which the 60 s budget still holds after one QUICK read."""
        secrets=self.held.get('SECRETS')
        if secrets is None or not self.env_ok:
            return {'status':'UNAVAILABLE','code':'PROBE_NOT_STARTED_ENV_FILE_NOT_AS_REQUIRED','started':False,'returned':False,'container_may_still_exist':False}
        if not self.image_ok:
            return {'status':'UNAVAILABLE','code':'PROBE_NOT_STARTED_IMAGE_NOT_AS_SIGNED','started':False,'returned':False,'container_may_still_exist':False}
        secrets.verify(self.gate)
        name=k9_container_name(self.day,self.operation);command=k9_probe_command(self.day,self.request_sha256)
        result=container_run(self.commands,'probe',self.values['image_id'],[],command,K9_PROBE_SNIPPET.encode('ascii'),container_name=name)
        facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'container_name':name,
               'snippet_sha256':K9_PROBE_SNIPPET_SHA256}
        if not result['returned']:
            return dict(facts,status='UNAVAILABLE',code=result['code'] if text(result['code'],CODE) else 'PROBE_RUN_NOT_COMPLETED',
                        container_may_still_exist=result['started'])
        code=result['returncode'];facts['engine_failure']=code in RUN_ENGINE_STATUSES
        try:line=k9_probe_line(result['output'],code,self.plan,self.request_sha256)
        except Refused as error:return dict(facts,status='UNAVAILABLE',code=code_of(error,'PROBE_OUTPUT_INVALID'),container_may_still_exist=False)
        if code!=0:
            if facts['engine_failure']:return k9_item(findings=['PROBE_ENGINE_FAILURE'],readiness=None,**facts)
            if line is None:return k9_item(findings=['PROBE_RUN_FAILED'],readiness=None,**facts)
            return k9_item(findings=['PROBE_SNIPPET_FAILED'],readiness=None,snippet_code=line['code'],logical_fetch_calls=line['logical_fetch_calls'],**facts)
        counts={key:line[key] for key in K9_PROBE_COUNTS}
        return k9_item(findings=[] if line['readiness']=='READY' else ['PROVIDER_NOT_READY'],readiness=line['readiness'],previous_session=line['previous_session'],
                       logical_fetch_calls=line['logical_fetch_calls'],registry_payload_sha256=line['registry_payload_sha256'],
                       bulk_payload_sha256=line['bulk_payload_sha256'],python=line['python'],**dict(counts,**facts))

    def image(self):
        found=image_facts(self.commands,self.values['image_id']);equal=found['id']==self.values['image_id'];revision=found['revision_label']==K9_CODE_REVISION
        self.image_ok=equal and revision
        return k9_item(findings=([] if equal else ['IMAGE_ID_MISMATCH'])+([] if revision else ['IMAGE_REVISION_MISMATCH']),id_equal_signed=equal,
                       revision_equal_signed=revision,repo_tag_count=found['repo_tag_count'])

    # -------------------------------------------------------------- POLICY
    def installed(self,key):
        """The installed policy or release file, read on the host: its hash is the Act B's, it is root's and private;
        for the policy, the instant of the read lies in its window. Nothing of its content leaves."""
        directory=self.held.get(key.upper());need(directory is not None,'DIRECTORY_NOT_HELD');directory.verify(self.gate)
        item=self.plan['policy_read'][key];limit=K9_MAX_POLICY_FILE if key=='policy' else K9_MAX_RELEASE_FILE
        try:raw,info=k9_read(self.host,directory.fd,[item['file_name']],self.gate,limit)
        except FileNotFoundError:return k9_item(findings=[key.upper()+'_FILE_ABSENT'],exists=False)
        except Refused as error:
            if str(error)!='FILE_TOO_LARGE':raise
            return k9_item(findings=[key.upper()+'_FILE_TOO_LARGE'],exists=True)
        equal=sha(raw)==self.values[key+'_sha256'];private=k9_private(info,K9_PRIVATE_FILE_MODE)
        findings=([] if equal else [key.upper()+'_SHA_NOT_THE_SIGNED_ONE'])+([] if private else [key.upper()+'_FILE_NOT_PRIVATE'])
        facts={'exists':True,'bytes_equal_signed':equal,'private':private}
        if key=='policy':
            try:
                body=k9_document(raw,'POLICY_UNREADABLE');start,end=instant(body.get('valid_from')),instant(body.get('valid_until'));now=self.clock()
                inside_window=start<=now<end;facts.update(window_readable=True,inside_its_window=inside_window)
                if not inside_window:findings.append('POLICY_OUTSIDE_ITS_WINDOW')
            except Refused:
                facts.update(window_readable=False,inside_its_window=None);findings.append('POLICY_WINDOW_UNREADABLE')
        return k9_item(findings=findings,**facts)

    def worker(self):
        signed=self.plan['policy_read']['worker'];found=container_facts(self.commands,signed['container'])
        self.worker_id=found['id'];equal=found['image_id']==self.values['image_id'];running=found['running'] and found['state']=='running'
        return k9_item(findings=([] if equal else ['WORKER_IMAGE_NOT_THE_SIGNED_ONE'])+([] if running else ['WORKER_NOT_RUNNING']),
                       container=signed['container'],image_id_equal_signed=equal,running=running,state=found['state'],restarts=found['restarts'],
                       health=found['health'],started_at=found['started_at'])

    def worker_environment(self):
        """Booleans only: the four live names with the values activate wrote, and the revision."""
        need(self.worker_id is not None,'WORKER_NOT_OBSERVED')
        expected=k9_expected_environment(self.plan);values=container_environment(self.commands,self.worker_id,expected)
        live=[key for key in sorted(expected) if key!='C3PO_BUILD_SHA'];build=values['C3PO_BUILD_SHA']['equal']
        equal=all(values[key]['equal'] for key in live)
        return k9_item(findings=([] if equal else ['WORKER_LIVE_NAMES_NOT_AS_SIGNED'])+([] if build else ['WORKER_BUILD_REVISION_MISMATCH']),
                       live_names_present=len([key for key in live if values[key]['present']]),live_names_equal=len([key for key in live if values[key]['equal']]),
                       build_revision_equal_signed=build,names={key:values[key] for key in sorted(values)})

    def stable(self):
        """Every directory held is still the one its way from "/" shows."""
        result={}
        for key in sorted(self.held):
            try:self.held[key].verify(self.gate);result[key]=True
            except Refused as error:
                if str(error) in K9_EXPIRED:raise
                result[key]=False
        return k9_item(findings=[] if all(result.values()) else ['DIRECTORY_REPLACED_DURING_RUN'],directories=result)

    def close(self):
        for handle in self.held.values():
            try:handle.close()
            except Exception:pass


def k9_outputs_ok(outputs,aggregates):
    """The grammar of what a runner receipt names: relative paths below days/<D> (day/) or the source root (source/),
    no dot component, a hash each; aggregates {files, sha256}."""
    def keys_ok(value,limit):
        return type(value) is dict and len(value)<=limit and all(text(key,K9_OUTPUT_KEY) for key in value)      # no component begins with a dot
    return (keys_ok(outputs,K9_MAX_OUTPUTS) and all(text(value,HEX64) for value in outputs.values()) and keys_ok(aggregates,K9_MAX_AGGREGATES)
            and all(type(value) is dict and set(value)=={'files','sha256'} and integer(value['files'],0,K9_MAX_AGGREGATE_ENTRIES) and text(value['sha256'],HEX64)
                    for value in aggregates.values()))

def k9_phase_result(items):
    """(COMPLETE | FAILED | UNCERTAIN, reason) of the step a RESULT collects, from what was observed and nothing else."""
    def complete(label):
        item=items.get(label);return item is not None and item.get('status')=='COMPLETE'
    for label in ('day_directory','launch_record','launched_container','step_receipts'):
        if not complete(label):return 'UNCERTAIN','OBSERVATION_INCOMPLETE'
    if not items['day_directory']['exists']:return 'UNCERTAIN','DAY_DIRECTORY_ABSENT'
    if not items['launch_record']['exists']:return 'UNCERTAIN','LAUNCH_RECORD_ABSENT'
    if not items['launch_record']['valid']:return 'UNCERTAIN','LAUNCH_RECORD_INVALID'
    container,receipts=items['launched_container'],items['step_receipts']
    if not container['as_recorded']:return 'UNCERTAIN','CONTAINER_NOT_AS_RECORDED'
    if container['state']!='exited' or container['running']:return 'UNCERTAIN','CONTAINER_NOT_EXITED'
    if receipts['receipt'] and receipts['failed']:return 'UNCERTAIN','RECEIPT_AND_FAILED_BOTH_PRESENT'
    if receipts['started'] and not receipts['started_valid']:return 'UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP'
    if receipts['receipt']:
        if not receipts['receipt_valid']:return 'UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP'
        if not receipts['started']:return 'UNCERTAIN','RECEIPT_WITHOUT_START_MARKER'
        if container['exit_code']!=0 or container['oom_killed']:return 'UNCERTAIN','EXIT_CODE_CONTRADICTS_THE_RECEIPT'
        if not complete('outputs') or items['outputs'].get('all_equal') is not True:return 'UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS'
        return 'COMPLETE',None
    if receipts['failed']:
        if not receipts['failed_valid']:return 'UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP'
        if receipts['failed_status'] in ('DEADLINE','UNCERTAIN'):return 'UNCERTAIN','STEP_REPORTS_DEADLINE_OR_UNCERTAIN'
        return 'FAILED','STEP_REPORTS_FAILED_OR_REFUSED'
    if receipts['started']:return 'UNCERTAIN','STARTED_WITHOUT_RECEIPT'
    if container['exit_code']==0:return 'UNCERTAIN','EXIT_ZERO_WITHOUT_RECEIPT'
    return 'FAILED','EXITED_BEFORE_ITS_START_MARKER'


def _never_complete(receipt):
    """A receipt reduced for size says of itself that it is not the success of its mode."""
    receipt['expectations_met']=False
    if receipt.get('code') is None:receipt['code']='RECEIPT_REDUCED_FOR_SIZE'
def _drop_rows(receipt):
    _never_complete(receipt)
    for item in (receipt.get('items') or {}).values():
        if type(item) is dict and type(item.get('observed_rows')) is list:item['observed_rows']=len(item['observed_rows'])
def _reduce_items(receipt):
    _never_complete(receipt)
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('OBSERVED_ROWS_REDUCED_TO_COUNTS',_drop_rows),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);reader=K9Reader(plan,host,gate,commands,bound,clock,monotonic)        # pure: nothing is touched
    mode=plan['mode'];items={};omitted=[];facts_only=set()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    def observe(label,action,gated=True):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE."""
        started=monotonic()
        if not gated:facts_only.add(label)
        try:
            gate();found=action()
        except Exception as error:found=safe(error)
        found['elapsed_ms']=int((monotonic()-started)*1000);items[label]=found
        if found.get('status')=='UNAVAILABLE' and found.get('code') in K9_EXPIRED:raise Refused(found['code'])
    def finish(stop=None):
        summary={}
        seen=sorted({code for item in items.values() for code in item.get('findings') or []})
        gaps=[label for label,item in items.items() if item.get('status')!='COMPLETE' and label not in facts_only]
        if mode=='RESULT':
            result,reason=('UNCERTAIN','RUN_STOPPED') if stop is not None else k9_phase_result(items)
            # a source root or a K9 directory that is not the signed one, another boot, a replaced directory, any other
            # finding or gap: the step's answer cannot be COMPLETE (CONTRACT section 4; N-8)
            if result=='COMPLETE' and gaps:result,reason='UNCERTAIN','OBSERVATION_INCOMPLETE'
            if result=='COMPLETE' and seen:result,reason='UNCERTAIN','FINDINGS_BESIDE_THE_STEP'
            container=items.get('launched_container') or {};receipts=items.get('step_receipts') or {}
            summary={'phase_result':result,'phase_reason':reason,'launch_exit_code':container.get('exit_code'),
                     'step_receipt_sha256':receipts.get('receipt_sha256') or receipts.get('failed_sha256'),
                     'counts':receipts.get('receipt_counts') or receipts.get('failed_counts')}
        if mode=='PROBE':
            item=items.get('probe') or {};readiness=item.get('readiness') or 'UNKNOWN'    # only a COMPLETE probe item carries one
            if stop is not None or gaps or [code for code in seen if code!='PROVIDER_NOT_READY']:readiness='UNKNOWN'
            summary={'readiness':readiness}
        if mode=='TREE':summary={'boot_id_sha256':reader.boot_hash}
        findings=sorted({code for item in items.values() for code in item.get('findings') or []}|
                        ({'PHASE_RESULT_'+summary['phase_result']} if mode=='RESULT' and stop is None and summary['phase_result']!='COMPLETE' else set()))
        incomplete=sorted(label for label,item in items.items() if item.get('status')!='COMPLETE')
        deciding=[label for label in incomplete if label not in facts_only]
        if stop is not None:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,stop
        elif deciding:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,findings[0] if findings else 'OBSERVATION_INCOMPLETE'
        elif findings:status,outcome,code=PARTIAL_STATUS,MISMATCH_OUTCOME,findings[0]
        else:status,outcome,code=COMPLETE_STATUS,success_of(plan),None
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=mode,day=plan['day'],k9_operation=plan['k9_operation'],
            slot=plan['slot'],effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),
            mutating_calls=state.counts(),items=items,findings=findings,items_not_complete=incomplete,items_omitted_by_the_plan=omitted,
            expectations_met=status==COMPLETE_STATUS,writes=0,containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION',**summary)))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                  # first, before anything is looked at
            k9_window_of(plan)                                                        # pure: the window belongs to D
            observe('boot',reader.boot)
            rows=plan['parent_rows']
            if mode=='TREE':
                for key,name in K9_TREE_DIRECTORIES:
                    observe('directory:'+key,lambda key=key,name=name:reader.directory(key,K9_PLACEMENT[name]))
                observe('k9_filesystem',lambda:reader.k9_filesystem(plan['constants']['disk_floor_bytes']))
                for key,name in K9_SECRET_FILES:
                    observe('secret:'+key+'/'+name,lambda key=key,name=name:reader.secret_file(key,name))
                observe('runner_file',reader.runner_file)
                observe('september_sources',reader.september_sources)
            elif mode=='RESULT':
                observe('directory:DAYS',lambda:reader.directory('DAYS',K9_PLACEMENT['days'],rows['days']))
                observe('directory:SOURCE_ROOT',lambda:reader.directory('SOURCE_ROOT',K9_PLACEMENT['source_root'],rows['source_root']))
                observe('day_directory',reader.day_directory)
                observe('launch_record',reader.launch_record)
                observe('launched_container',reader.launched_container)
                observe('step_receipts',reader.step_receipts)
                observe('outputs',reader.outputs)
            elif mode=='PROBE':
                observe('directory:SECRETS',lambda:reader.directory('SECRETS',K9_PLACEMENT['secrets'],rows['secrets']))
                observe('secret:SECRETS/provider.env',reader.provider_env)
                observe('image',reader.image)                                        # the image first: no secret-bearing container otherwise
                observe('probe',reader.probe_run)
            else:
                read=plan['policy_read']
                observe('directory:POLICY',lambda:reader.directory('POLICY',read['policy']['directory']['path'],read['policy']['directory'],private=False))
                observe('directory:RELEASE',lambda:reader.directory('RELEASE',read['release']['directory']['path'],read['release']['directory'],private=False))
                observe('policy_file',lambda:reader.installed('policy'))
                observe('release_file',lambda:reader.installed('release'))
                observe('worker',reader.worker)
                observe('worker_environment',reader.worker_environment)
                observe('image',reader.image)
            observe('directories_stable',reader.stable)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:
                return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mode=mode,
                                                                             mutating_calls=state.counts(),writes=0)))
            return finish(code)
        return finish()
    finally:reader.close()
# ==== END OP_K9_PHASE_READ ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
