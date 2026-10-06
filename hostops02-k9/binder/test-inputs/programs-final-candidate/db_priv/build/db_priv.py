"""Separate DBR PRIV family; readonly, own operation, request, GO and reviewed seal. No action on import."""

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

# ==== BEGIN OP_DB_PRIV (this operation only) ====
OPERATION='GO_READONLY_HOSTOPS02_DB_PRIV_01'
PHASE='READONLY_DB_PRIV_CATALOG_ONLY'
REQUEST_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_DB_PRIV_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_DB_PRIV_PLAN_V1'
SOURCE_NAME='db_priv.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The run that placed the two credentials this source binds read-only into its container (K3-K9, N-5)
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_K3K9_SECRETS_01',)
MAX_GATE_SPAN_SECONDS=1800
# Separate program under A2 amendment 1 revision 3 E1-11; no shared PRIV/QUERIES runtime.
MODES=('PRIV',)
COMPLETE_OUTCOME='DB_READER_PRIVILEGES_PROVEN'          # mode QUERIES
PRIV_COMPLETE_OUTCOME='DB_READER_PRIVILEGES_PROVEN'                       # mode PRIV
MISMATCH_OUTCOME='DB_PRIV_OBSERVED_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='DB_PRIV_PARTIAL'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='DB_PRIV_PARTIAL'
ESCAPED_OUTCOME='DB_PRIV_PARTIAL'
PLAN_KEYS=frozenset(('mode','secrets_chain','image_id','image_revision','session','release_receipt_sha256','expected','priv_receipt',
                     'evidence_boot_id_sha256'))
PRIV_RECEIPT_KEYS=frozenset(('operation','mode','outcome','receipt_sha256','observed_at','boot_id_sha256'))
QUERIES_ONLY=('session','release_receipt_sha256','expected','priv_receipt')

DBR_EPOCH='R2D2-V2-SHADOW-2026-10-05'                  # ORD:7, EPOCH = NAMESPACE
DBR_SESSIONS=EPOCH_DAYS[3:8]                           # 2026-10-05 ... 2026-10-09
DBR_NETWORK='c3po_c3po_internal'                       # compose network c3po_internal (internal: true), where db resolves; no egress
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'            # K3-K9 placement, decision N-8
SECRETS_DIRECTORY=K9_ROOT+'/secrets'
RISK_ENV_NAME='risk-db.env'
EMITTER_DIRECTORY_NAME='emitter'
EMITTER_PASSWORD_NAME='password'
SECRETS_ENTRIES=3                                      # provider.env, risk-db.env, emitter (what K3-K9 leaves)
RISK_TARGET='/c3po-dbr-risk-db.env'                    # the one file bound, read-only
EMITTER_TARGET='/c3po-dbr-emitter'                     # the emitter directory bound, read-only (it holds only the password)
DBR_CONTAINER_PREFIX='hostops02-dbr-priv-'
DBR_RUN_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network',DBR_NETWORK,'--read-only','--cap-drop','ALL',
                '--security-opt','no-new-privileges']
EXPECTED_KEYS=frozenset(('epoch_rows','binding_committed'))
LINE_KEYS_OF_MODE={'PRIV':frozenset(('schema','mode','status','risk_url','reader_privileges')),
                   'QUERIES':frozenset(('schema','mode','queries','status','risk_url','emitter_password','epoch_row','binding','emitter'))}
PRIVILEGE_KEYS=('role_is_the_restricted_reader','role_restricted','transaction_read_only','database_connect','schema_usage','epochs_select',
                'journal_select')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'query':command_row('docker',DBR_RUN_PREFIX,'--name hostops02-dbr-<16 hex of the GO>; PRIV: the risk URL file bound read-only, the '
                              'signed image ID, python -I -B - PRIV and its container path; QUERIES: the risk URL file and the emitter directory '
                              'bound read-only, the signed image ID, python -I -B - QUERIES, the two container paths, the epoch, the signed session, '
                              'the signed release receipt sha256 (state.release_sha of the epoch row); the pinned snippet on standard input','RUN','CONTAINER',stdin=True)}
DBR_SNIPPET=r'''"""Separate DBR-PRIV: only catalog privileges of the existing restricted reader, rolled-back readonly transaction."""
import json
import os
import re
import stat
import sys
import time

RISK_KEY=b'C3PO_R2D2_RISK_DATABASE_URL='
RISK_URL=rb'postgresql://c3po_v2_risk_reader:[\x21-\x7e]{1,4000}'
READER_ROLE='c3po_v2_risk_reader'
DATABASE={'host':'db','port':5432,'dbname':'c3po'}
CODE=r'[A-Z][A-Z0-9_]{0,79}'
PRIVILEGE_SQL=("SELECT current_user,session_user,current_setting('transaction_read_only'),"
               "(SELECT NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolreplication OR r.rolbypassrls) "
               "FROM pg_catalog.pg_roles r WHERE r.rolname=current_user),"
               "pg_catalog.has_database_privilege(current_user,pg_catalog.current_database(),'CONNECT'),"
               "pg_catalog.has_schema_privilege(current_user,'public','USAGE'),"
               "pg_catalog.has_table_privilege(current_user,'public.r2d2_v2_shadow_epochs','SELECT'),"
               "pg_catalog.has_table_privilege(current_user,'public.r2d2_v2_shadow_journal','SELECT')")
BEGIN_READER="SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
TIMEOUT="SET LOCAL statement_timeout='3s'"
CONNECT_SECONDS=5

class Refusal(ValueError):pass
def need(ok,code):
    if not ok:raise Refusal(code)

def private_bytes(path,limit):
    """A private regular file: root, 0600, one link, at most limit bytes, opened without following a link."""
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except OSError:raise Refusal('FILE_UNAVAILABLE') from None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,'FILE_NOT_PRIVATE')
        need(info.st_size<=limit,'FILE_FORMAT')
        raw=os.read(fd,limit+1);need(len(raw)<=limit,'FILE_FORMAT');return raw
    finally:os.close(fd)

def risk_dsn(raw):
    """KEY=VALUE, one line, at most one trailing newline; the value names the restricted reader (a boolean, never echoed)."""
    body=raw[:-1] if raw.endswith(b'\n') else raw
    need(body.startswith(RISK_KEY) and b'\n' not in body,'RISK_URL_FORMAT')
    value=body[len(RISK_KEY):];need(re.fullmatch(RISK_URL,value) is not None,'RISK_URL_NOT_THE_RESTRICTED_READER')
    return value.decode('ascii')

def dsn_host_is_db(dsn):
    """Whether the host of the DSN is db, the name the database has on the compose network (a boolean; the host is
    the text between the last '@' and the next ':' or '/')."""
    rest=dsn.rsplit('@',1)[-1];return re.match(r'db(?:[:/]|$)',rest) is not None


def failure(error,fallback):
    """A constant code and, from the database driver, the SQLSTATE only. Never the text of an exception."""
    out={'status':'UNAVAILABLE','code':fallback}
    if isinstance(error,ValueError) and len(error.args)==1 and type(error.args[0]) is str and re.fullmatch(CODE,error.args[0]):out['code']=error.args[0]
    state=getattr(error,'sqlstate',None)
    if type(state) is str and re.fullmatch(r'[0-9A-Z]{5}',state):out['sqlstate']=state
    return out

def privileges_of(row):
    """The proof of statement 0: every member must be exactly True for queries 1 and 3 to run."""
    need(row is not None and len(row)==8,'PRIVILEGE_SHAPE')
    return {'status':'COMPLETE','role_is_the_restricted_reader':row[0]==READER_ROLE and row[1]==READER_ROLE,'role_restricted':row[3] is True,
            'transaction_read_only':row[2]=='on','database_connect':row[4] is True,'schema_usage':row[5] is True,
            'epochs_select':row[6] is True,'journal_select':row[7] is True}

def privileges_read(psycopg,dsn):
    """Mode PRIV: the one catalog read, in a read-only transaction that is rolled back."""
    try:
        connection=psycopg.connect(dsn,autocommit=False,connect_timeout=CONNECT_SECONDS,application_name='hostops02-dbr',options='-c default_transaction_read_only=on')
    except Exception as error:return failure(error,'READER_CONNECTION_FAILED')
    try:
        connection.execute(BEGIN_READER);connection.execute(TIMEOUT)
        return privileges_of(connection.execute(PRIVILEGE_SQL).fetchone())
    except Exception as error:return failure(error,'READER_PRIVILEGE_QUERY_FAILED')
    finally:
        try:connection.rollback()
        except Exception:pass
        try:connection.close()
        except Exception:pass



def main(arguments,psycopg,authority=None,read=private_bytes,monotonic=time.monotonic):
    out={'schema':'HOSTOPS02_DBR_SNIPPET_V2'}
    try:
        need(len(arguments)==2 and arguments[0]=='PRIV','ARGUMENTS')
        out['mode']='PRIV';risk_path=arguments[1]
    except Refusal as error:
        out.update(status='REFUSED',code=str(error));return out
    try:dsn=risk_dsn(read(risk_path,4096));out['risk_url']={'status':'COMPLETE','host_is_db':dsn_host_is_db(dsn)}
    except Exception as error:dsn=None;out['risk_url']=failure(error,'RISK_URL_UNAVAILABLE')
    out['reader_privileges']={'status':'UNAVAILABLE','code':'RISK_URL_UNAVAILABLE'} if dsn is None else privileges_read(psycopg,dsn)
    dsn=None;out['status']='DONE';return out

if __name__=='__main__':
    sys.path.insert(0,'/app')
    try:
        import psycopg
    except Exception:
        sys.stdout.write('{"code":"IMPORT_FAILED","schema":"HOSTOPS02_DBR_SNIPPET_V2","status":"REFUSED"}\n');raise SystemExit(3)
    result=main(sys.argv[1:],psycopg)
    sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n');sys.stdout.flush()
    raise SystemExit(0)
'''.encode('ascii')
DBR_SNIPPET_SHA256=sha(DBR_SNIPPET)
SCOPE_STATEMENT=('ORD:28 (M7, READONLY_PSQL_PREFLIGHT_ONLY), in two signed modes of these bytes, each its own request and GO. PRIV: the '
                 'read of the existing restricted reader role c3po_v2_risk_reader by catalog functions only (CONNECT, USAGE on public, '
                 'SELECT on r2d2_v2_shadow_epochs and r2d2_v2_shadow_journal, the role restricted, the session read-only), in one read-only '
                 'transaction, booleans only. QUERIES: exactly the three ORD:28 queries, and only with a PRIV receipt of the same boot and '
                 'UTC day that proved every privilege: query 1 the epoch row count, query 2 the emitter preconditions (the release check '
                 '_authority() as the emitter itself), query 3 whether the capacity binding of the signed session is committed. One '
                 'pinned snippet in one attached container of the signed backend image ID on the compose network c3po_c3po_internal '
                 '(database only, no egress), read-only root filesystem, no capability, read-only binds only of what K3-K9 placed under '
                 'the K9 root (PRIV: the reader URL file; QUERIES: it and the emitter password directory). No DDL, no administrator or '
                 'other credential, no inferred role. Changes nothing on the host; creates and removes one container. No credential, DSN '
                 'or value of the database state but its hashes and booleans reaches the receipt.')
SIDE_EFFECTS=['one attached docker run --rm on the network '+DBR_NETWORK+': the engine creates the container and removes it when its process ends; '
              'a run that times out may leave it until then (its name says so)',
              'two database sessions (the restricted reader, the causal emitter), each with one read-only transaction that is rolled back; '
              'the database logs the connections as it logs any other',
              'the docker CLI reads the two credential files only as bind sources; the snippet reads them inside the container, in memory']
SCOPE_STATEMENT='Separate PRIV program under A2 amendment 1 revision 3 E1-11; no shared-mode executable.'
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'epoch':DBR_EPOCH,'sessions':list(DBR_SESSIONS),'network':DBR_NETWORK,
       'modes':{'PRIV':{'success':PRIV_COMPLETE_OUTCOME,'binds':['risk_url_file'],'command':'python -I -B - PRIV <risk file>'},
                'QUERIES':{'success':COMPLETE_OUTCOME,'binds':['risk_url_file','emitter_directory'],
                           'command':'python -I -B - QUERIES <risk file> <password file> <epoch> <session> <release receipt sha256>',
                           'requires':'priv_receipt: a receipt of this operation in mode PRIV, outcome '+PRIV_COMPLETE_OUTCOME+', of the same boot '
                                      'and the same UTC day, observed before the window of the request'}},
       'snippet':{'sha256':DBR_SNIPPET_SHA256,'bytes':len(DBR_SNIPPET)},
       'binds':{'risk_url_file':{'source':SECRETS_DIRECTORY+'/'+RISK_ENV_NAME,'target':RISK_TARGET,'read_only':True},
                'emitter_directory':{'source':SECRETS_DIRECTORY+'/'+EMITTER_DIRECTORY_NAME,'target':EMITTER_TARGET,'read_only':True}},
       'database':{'host':'db','port':5432,'database':'c3po','reader_role':'c3po_v2_risk_reader','emitter_role':'c3po_v2_causal_emitter',
                   'emitter_authentication':'scram-sha-256 required (libpq 16 or later)'},
       'privileges':{'PRIV':'as the restricted reader, catalog functions only: current_user = session_user = c3po_v2_risk_reader, the role '
                             'restricted (no superuser, createrole, createdb, replication, bypassrls), the transaction read-only, '
                             'has_database_privilege CONNECT, has_schema_privilege public USAGE, has_table_privilege SELECT on '
                             'public.r2d2_v2_shadow_epochs and public.r2d2_v2_shadow_journal; never DDL, never another credential'},
       'queries':{                  '1_EPOCH_ROW':'as the restricted reader: the count of rows of r2d2_v2_shadow_epochs for the epoch, and of that row state_sha, '
                                'version, whether state.release_sha equals the signed release receipt sha256 (release.receipt_sha, r2d2_v2_shadow.py:381), whether journal_head is empty',
                  '2_EMITTER_PRECONDITIONS':'as c3po_v2_causal_emitter: app.r2d2_v2_causal_emitter._authority(connection) of the release '
                                            '(r2d2_v2_causal_emitter.py:79-128), then current_database, current_user, session_user, '
                                            'session_replication_role, transaction_read_only',
                  '3_BINDING_COMMITTED':'as the restricted reader: state.daily_capacity.<session>.sha of the epoch row, and the count of '
                                        'journal entries capacity-prepared:<session>',
                  'transactions':'PRIV: one SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; QUERIES, reader: queries 1 and 3 in one such transaction (a second only after a failed 1); '
                                 "emitter: SET TRANSACTION READ ONLY; both SET LOCAL statement_timeout='3s'; connections time out after 5 s; query 2 not begun after 20 s; "
                                 'every transaction rolled back'},
       'file_contents_read':[BOOT_ID_PATH],
       'metadata_only':['the secrets directory, the risk URL file, the emitter directory and its password file (lstat and entry counts; '
                        'never their content, size or digest, in this process)'],
       'side_effects':SIDE_EFFECTS,
       'bind_sources':'risk-db.env (0:0 0600, one link) and emitter/ (0:0 0700, only password 0:0 0600) under a chain from / in which every '
                      'component is root-owned and closed to group and other writes (no open root), the last two 0:0 0700; walked, held and '
                      'proved again just before the container (decision 6)',
       'never':['an administrator or any other database credential','a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','compose','systemctl','a shell','a pull',
                'a write bind','a DDL, an INSERT, an UPDATE, a DELETE or a SET ROLE','the provider tokens bound into the container',
                'a credential, a DSN or the text of an exception in the receipt','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT}}
# The reachable snippet and the documentary scope contain only this program's mode.
SCOPE['modes']={'PRIV':SCOPE['modes']['PRIV']}
SCOPE['statement']=SCOPE_STATEMENT
SCOPE['queries']={}
SCOPE['binds'].pop('emitter_directory')
SCOPE['side_effects']=['One readonly database session of the restricted reader, rolled back; one attached disposable container.']
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


def risk_source():return SECRETS_DIRECTORY+'/'+RISK_ENV_NAME
def emitter_source():return SECRETS_DIRECTORY+'/'+EMITTER_DIRECTORY_NAME
def mounts(plan):
    risk=[{'source':risk_source(),'target':RISK_TARGET,'read_only':True}]
    return risk if plan['mode']=='PRIV' else risk+[{'source':emitter_source(),'target':EMITTER_TARGET,'read_only':True}]
def run_words(plan):
    if plan['mode']=='PRIV':return ['python','-I','-B','-','PRIV',RISK_TARGET]
    return ['python','-I','-B','-','QUERIES',RISK_TARGET,EMITTER_TARGET+'/'+EMITTER_PASSWORD_NAME,DBR_EPOCH,plan['session'],plan['release_receipt_sha256']]

def validate_plan(plan):
    need(type(plan['mode']) is str and plan['mode'] in MODES,'MODE_INVALID')
    need(type(plan['secrets_chain']) is list,'CHAIN_ROW_INVALID')
    rows=validate_chain(plan['secrets_chain'],SECRETS_DIRECTORY)
    need(all((row['uid'],row['gid'],row['mode'])==(0,0,0o700) for row in rows[-2:]),'SECRETS_CHAIN_NOT_ROOT_0700')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_PLAN_INVALID')
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_PLAN_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if plan['mode']=='PRIV':
        need(all(plan[key] is None for key in QUERIES_ONLY),'PRIV_PLAN_CARRIES_QUERIES_MEMBERS')
    else:
        need(type(plan['session']) is str and plan['session'] in DBR_SESSIONS,'SESSION_NOT_OF_THE_EPOCH')
        need(hexpin(plan['release_receipt_sha256']),'RELEASE_SHA_INVALID')
        expected=plan['expected'];exact(expected,EXPECTED_KEYS,'EXPECTATION_INVALID')
        need(expected['epoch_rows'] is None or (type(expected['epoch_rows']) is int and expected['epoch_rows'] in (0,1)),'EXPECTATION_INVALID')
        need(expected['binding_committed'] is None or type(expected['binding_committed']) is bool,'EXPECTATION_INVALID')
        # the PRIV receipt that proved SELECT: this operation, mode PRIV, its success, the same boot, the same UTC day, earlier
        priv=plan['priv_receipt'];exact(priv,PRIV_RECEIPT_KEYS,'PRIV_RECEIPT_REQUIRED')
        need(priv['operation']==OPERATION and priv['mode']=='PRIV','PRIV_RECEIPT_NOT_OF_THIS_OPERATION')
        need(priv['outcome']==PRIV_COMPLETE_OUTCOME,'PRIV_RECEIPT_DID_NOT_PROVE_SELECT')
        need(hexpin(priv['receipt_sha256']),'PRIV_RECEIPT_REQUIRED')
        need(priv['boot_id_sha256']==plan['evidence_boot_id_sha256'],'PRIV_RECEIPT_OF_ANOTHER_BOOT')
        observed=instant(priv['observed_at']);start=instant(plan['window']['not_before'])
        need(observed.date()==start.date() and observed<start,'PRIV_RECEIPT_NOT_OF_THIS_DAY')
    run_arguments('query',plan['image_id'],mounts(plan),run_words(plan),DBR_CONTAINER_PREFIX+'0'*16)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'mode':plan['mode'],'secrets':chain_effects(plan['secrets_chain']),'image_id':plan['image_id'],
            'image_revision':plan['image_revision'],'network':DBR_NETWORK,'binds':mounts(plan),'command':run_words(plan),
            'snippet_sha256':DBR_SNIPPET_SHA256,'epoch':DBR_EPOCH,'session':plan['session'],'release_receipt_sha256':plan['release_receipt_sha256'],
            'expected':plan['expected'],'priv_receipt':plan['priv_receipt'],'queries':0 if plan['mode']=='PRIV' else 3,
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'writes':0,'containers_run':1,'activation':False}
def success_of(plan):return PRIV_COMPLETE_OUTCOME if plan['mode']=='PRIV' else COMPLETE_OUTCOME


def item_of(findings=(),**facts):return dict(facts,status='COMPLETE',findings=sorted(set(findings)))
CODE_OR_NONE='[A-Z][A-Z0-9_]{0,79}'
def checked_part(value,keys):
    """One part of the snippet's line: COMPLETE with exactly its keys, or UNAVAILABLE with a constant code (and a SQLSTATE)."""
    need(type(value) is dict and value.get('status') in ('COMPLETE','UNAVAILABLE'),'SNIPPET_LINE_INVALID')
    if value['status']=='UNAVAILABLE':
        need(set(value)<={'status','code','sqlstate'} and text(value.get('code'),CODE_OR_NONE)
             and ('sqlstate' not in value or text(value['sqlstate'],'[0-9A-Z]{5}')),'SNIPPET_LINE_INVALID')
        return value
    need(set(value)==set(keys)|{'status'},'SNIPPET_LINE_INVALID');return value
def snippet_line(raw,plan):
    """The one line the snippet prints, every member typed; nothing in it is copied to the receipt unchecked."""
    line=single_line(raw);mode=plan['mode']
    need(set(line)==set(LINE_KEYS_OF_MODE[mode]) and line['schema']=='HOSTOPS02_DBR_SNIPPET_V2' and line['mode']==mode and line['status']=='DONE','SNIPPET_LINE_INVALID')
    risk=checked_part(line['risk_url'],('host_is_db',))
    if risk['status']=='COMPLETE':need(type(risk['host_is_db']) is bool,'SNIPPET_LINE_INVALID')
    if mode=='PRIV':
        privileges=checked_part(line['reader_privileges'],PRIVILEGE_KEYS)
        if privileges['status']=='COMPLETE':need(all(type(privileges[key]) is bool for key in PRIVILEGE_KEYS),'SNIPPET_LINE_INVALID')
        return line
    need(line['queries']==3,'SNIPPET_LINE_INVALID');checked_part(line['emitter_password'],())
    row=checked_part(line['epoch_row'],('rows','state_sha','version','release_sha_equal','journal_head_empty'))
    if row['status']=='COMPLETE':
        need(type(row['rows']) is int and row['rows'] in (0,1),'SNIPPET_LINE_INVALID')
        present=row['rows']==1
        need((row['state_sha'] is None or hexpin(row['state_sha'])) and (row['version'] is None or integer(row['version']))
             and all((type(row[key]) is bool) if present else (row[key] is None) for key in ('release_sha_equal','journal_head_empty')),'SNIPPET_LINE_INVALID')
    binding=checked_part(line['binding'],('session','committed','binding_sha256','journal_entries'))
    if binding['status']=='COMPLETE':
        need(binding['session']==plan['session'] and type(binding['committed']) is bool and integer(binding['journal_entries'])
             and (hexpin(binding['binding_sha256']) if binding['committed'] else binding['binding_sha256'] is None),'SNIPPET_LINE_INVALID')
    emitter=checked_part(line['emitter'],('authority_passed','database_is_c3po','current_user_is_the_emitter','session_user_equal',
                                          'replication_role_origin','transaction_read_only'))
    if emitter['status']=='COMPLETE':need(all(type(value) is bool for key,value in emitter.items() if key!='status'),'SNIPPET_LINE_INVALID')
    return line

def judged(line,plan):
    """The findings of a valid line: unconditional rules, then (QUERIES) the signed expectations."""
    findings=[]
    parts=('risk_url','reader_privileges') if plan['mode']=='PRIV' else ('risk_url','emitter_password','epoch_row','binding','emitter')
    for key in parts:
        if line[key]['status']!='COMPLETE':findings.append('QUERY_UNAVAILABLE_'+key.upper())
    if line['risk_url']['status']=='COMPLETE' and line['risk_url']['host_is_db'] is not True:findings.append('RISK_URL_HOST_IS_NOT_DB')
    if plan['mode']=='PRIV':
        privileges=line['reader_privileges']
        if privileges['status']=='COMPLETE' and not all(privileges[key] is True for key in PRIVILEGE_KEYS):findings.append('READER_PRIVILEGE_NOT_PROVEN')
        return findings
    expected=plan['expected'];row,binding,emitter=line['epoch_row'],line['binding'],line['emitter']
    if row['status']=='COMPLETE':
        if expected['epoch_rows'] is not None and row['rows']!=expected['epoch_rows']:findings.append('EPOCH_ROW_COUNT_NOT_AS_SIGNED')
        if row['rows']==1 and row['release_sha_equal'] is not True:findings.append('EPOCH_RELEASE_SHA_MISMATCH')
        if row['rows']==1 and row['version']==0 and row['journal_head_empty'] is not True:findings.append('EPOCH_ZERO_VERSION_JOURNAL')
    if binding['status']=='COMPLETE':
        if expected['binding_committed'] is not None and binding['committed']!=expected['binding_committed']:findings.append('BINDING_NOT_AS_SIGNED')
        if binding['committed']!=(binding['journal_entries']==1):findings.append('BINDING_AND_JOURNAL_DISAGREE')
    if emitter['status']=='COMPLETE':
        if not all(value is True for key,value in emitter.items() if key!='status'):findings.append('EMITTER_IDENTITY_NOT_AS_REQUIRED')
    return findings

def _reduce_line(receipt):
    if type(receipt.get('items')) is dict and type(receipt['items'].get('query')) is dict:receipt['items']['query'].pop('line',None)
REDUCTIONS=[('SNIPPET_LINE_DROPPED',_reduce_line)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);items={};findings=[];held={};go16=bound['go_sha256'][:16];name=DBR_CONTAINER_PREFIX+go16
    def observe(key,action):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE."""
        try:
            items[key]=action();findings.extend(items[key].get('findings',[]))
        except Exception as error:
            items[key]=safe(error)
            if items[key].get('code') in ('GO_EXPIRED','CLOCK_REVERSED'):raise
    def finish(status,outcome,code):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,findings=sorted(set(findings)),writes=0,
            containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION')))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            def boot():
                same=boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256']
                return item_of(findings=[] if same else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=same)
            observe('boot',boot)
            def secrets():
                held['SECRETS']=Pinned(host,walk_pinned(host,plan['secrets_chain'],gate,[]),rows=plan['secrets_chain'])
                fd=held['SECRETS'].fd;entries=count_entries(host,fd,gate);facts={'entries':entries};found=[]
                if entries!=SECRETS_ENTRIES:found.append('SECRETS_DIRECTORY_NOT_AS_PLACED')
                for key,named,want,mode in (('risk_url_file',RISK_ENV_NAME,'file',0o600),('emitter_directory',EMITTER_DIRECTORY_NAME,'dir',0o700)):
                    gate()
                    try:info=host.lstat(named,fd)
                    except FileNotFoundError:facts[key]={'exists':False};found.append('CREDENTIAL_ABSENT');continue
                    facts[key]={'exists':True,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}
                    if (kind(info.st_mode),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(want,0,0,mode) or (want=='file' and info.st_nlink!=1):
                        found.append('CREDENTIAL_NOT_PRIVATE')
                if not found:
                    gate();held['EMITTER']=Pinned(host,host.open(EMITTER_DIRECTORY_NAME,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=fd),
                                                  parent=held['SECRETS'],name=EMITTER_DIRECTORY_NAME)
                    inner=count_entries(host,held['EMITTER'].fd,gate);facts['emitter_entries']=inner
                    try:info=host.lstat(EMITTER_PASSWORD_NAME,held['EMITTER'].fd)
                    except FileNotFoundError:info=None
                    facts['emitter_password_file']={'exists':info is not None}
                    if info is None:found.append('CREDENTIAL_ABSENT')
                    else:
                        facts['emitter_password_file'].update(type=kind(info.st_mode),uid=info.st_uid,gid=info.st_gid,mode_octal='%04o'%stat.S_IMODE(info.st_mode),links=info.st_nlink)
                        if (kind(info.st_mode),info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)!=('file',0,0,0o600,1):found.append('CREDENTIAL_NOT_PRIVATE')
                    if inner!=1:found.append('EMITTER_DIRECTORY_NOT_AS_PLACED')
                return item_of(findings=found,**facts)
            observe('secrets',secrets)
            def image():
                facts=image_facts(commands,plan['image_id']);found=[]
                if facts['id']!=plan['image_id']:found.append('IMAGE_ID_MISMATCH')
                if facts['revision_label']!=plan['image_revision']:found.append('IMAGE_REVISION_MISMATCH')
                return item_of(findings=found,id_equal=facts['id']==plan['image_id'],revision_equal=facts['revision_label']==plan['image_revision'])
            observe('image',image)
            listed=[]
            def before():
                listed.extend(container_list(commands))
                return item_of(findings=['DBR_CONTAINER_NAME_PRESENT'] if [row for row in listed if row['name']==name] else [],containers=len(listed))
            observe('containers_before',before)
            # the container only when nothing it would read is in doubt: credentials as placed, image as signed, name free
            ready=all(items.get(key,{}).get('status')=='COMPLETE' and not items[key]['findings'] for key in ('boot','secrets','image','containers_before'))
            ran=[False]
            def query():
                if not ready:return {'status':'UNAVAILABLE','code':'NOT_STARTED_PRECONDITIONS'}
                for handle in held.values():handle.verify(gate)
                result=container_run(commands,'query',plan['image_id'],mounts(plan),run_words(plan),DBR_SNIPPET,container_name=name)
                ran[0]=result['started']
                facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],
                       'container_may_still_exist':result['started'] and not result['returned']}
                if not result['returned']:return dict(facts,status='UNAVAILABLE',code=result['code'] or 'QUERY_RUN_NOT_COMPLETED')
                facts['engine_failure']=result['returncode'] in RUN_ENGINE_STATUSES
                if result['returncode']!=0:return dict(facts,status='UNAVAILABLE',code='QUERY_RUN_FAILED')
                line=snippet_line(result['output'],plan)
                return item_of(findings=judged(line,plan),line={key:value for key,value in line.items() if key not in ('schema','status')},**facts)
            observe('query',query)
            def after():
                rows=container_list(commands)
                left=bool([row for row in rows if row['name']==name])
                return item_of(findings=['DBR_CONTAINER_LEFT'] if left else [],containers=len(rows),dbr_container_present=left)
            if ran[0]:observe('containers_after',after)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mutating_calls=state.counts(),writes=0)))
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code)
        status=combined(items.values())
        if status!='COMPLETE':return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'OBSERVATION_INCOMPLETE')
        if findings:return finish(PARTIAL_STATUS,MISMATCH_OUTCOME,sorted(set(findings))[0])
        return finish(COMPLETE_STATUS,success_of(plan),None)
    finally:
        for handle in list(held.values())[::-1]:
            try:handle.close()
            except Exception:pass
# ==== END OP_DB_PRIV ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
