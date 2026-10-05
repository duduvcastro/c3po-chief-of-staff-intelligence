"""OP_PRECHECK: the baseline the write operations pin. Read-only.

Observations only. This source has no call that creates, changes or removes anything. It reads one row per
component of every parent directory the write operations pin, proves the absence or records the metadata of every
planned destination, scans the unit lookup directories, hashes the boot identifier, and reads the local ID and tags
of the production image. For a name that holds a secret only type, owner, mode and link count are reported, and
for a unit file found at a signed name no size. A failed observation is UNAVAILABLE with a constant code, never an
absence. The caller authenticates exact
request/authority/GO/source bytes first. No action on import.
"""

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
# One UTC day per run, named by the signed request and confined by a code set; each operation part names its set as DATES
# and its dispatcher carries the same literal. The two write operations stop one day earlier than the read-only ones:
# 2026-10-05 UTC begins on Sunday 21:00 BRT and holds the first live session.
READ_DATES=('2026-10-02','2026-10-03','2026-10-04','2026-10-05')
WRITE_DATES=('2026-10-02','2026-10-03','2026-10-04')
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
def strict(raw):
    need(type(raw) is bytes and 0<len(raw)<=65536,'DOCUMENT_SIZE')
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
    Returns (bytes, fstat). Used only for unit files, which hold no secret."""
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
    and for each operation name in EVIDENCE_OPERATIONS (the precheck, for the two write operations) at least one entry."""
    need(type(evidence) is list and len(evidence)<=16 and (evidence or not EVIDENCE_REQUIRED),'EVIDENCE_UNBOUND')
    for item in evidence:
        need(type(item) is dict and set(item)=={'role','operation','receipt_sha256'} and text(item['role'],'[A-Z][A-Z0-9_]{0,63}')
             and text(item['operation'],'[A-Z][A-Z0-9_]{0,79}') and hexpin(item['receipt_sha256']),'EVIDENCE_UNBOUND')
    need(all(any(item['operation']==name for item in evidence) for name in EVIDENCE_OPERATIONS),'EVIDENCE_PRECHECK_MISSING')

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
         and request['activation_allowed'] is False,'REQUEST_SCOPE')
    need(authority['schema']==AUTHORITY_SCHEMA and authority['operation']==OPERATION and authority['phase']==PHASE
         and authority['status']=='SIGNED' and authority['decision']=='APPROVED' and authority['execution_authorized'] is True
         and authority['request_sha256']==pins.request and authority['payload_sha256']==pins.payload
         and authority['writes_allowed'] is WRITES_ALLOWED and authority['activation_allowed'] is False
         and type(authority['owner_evidence']) is str and 0<len(authority['owner_evidence'])<=512
         and authority['owner_evidence']!='UNBOUND','AUTHORITY_UNBOUND')
    need(go['schema']==GO_SCHEMA and go['status']=='SIGNED' and go['action']=='GO' and go['phase']==PHASE
         and go['operation']==OPERATION and go['execution_authorized'] is True
         and go['writes_allowed'] is WRITES_ALLOWED and go['activation_allowed'] is False
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

def envelope(status,outcome,code,bound):
    receipt={'schema':RECEIPT_SCHEMA,'operation':OPERATION,'status':status,'outcome':outcome,'code':code,
             'scope_sha256':SCOPE_SHA256,'activation_performed':False,'daemon_reload_performed':False,
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
                                              'host_binding_sha256','scope_sha256','mutating_calls','objects_left_by_this_run')}
        was_refused=receipt.get('status')==REFUSED_STATUS
        receipt.clear();receipt.update(kept)
        receipt.update(status=REFUSED_STATUS if was_refused else PARTIAL_STATUS,
                       outcome=REFUSED_OUTCOME if was_refused else REDUCED_OUTCOME,code='RECEIPT_REDUCED_TO_MINIMUM',
                       size_reductions=['RECEIPT_REDUCED_TO_MINIMUM'],activation_performed=False,daemon_reload_performed=False,
                       secret_bytes_in_receipt=False,ready=False)
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
        return seal(envelope(PARTIAL_STATUS,ESCAPED_OUTCOME,code_of(error,'RUN_ESCAPED_STATE_UNKNOWN'),
                             dict(bound,phase_reached='ESCAPED',mutating_calls=state.counts())))
# ==== END CORE ====

# ==== BEGIN RUNNER (shared part, byte-identical in every source that carries it) ====
import selectors
import subprocess

CALL_SECONDS=8
MAX_TOOL_TIMEOUTS=2
MAX_COMMAND_BYTES=64*1024
COMMAND_ENVIRONMENT={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'}

class NativeRunner:
    """Fixed-argv commands: absolute binary, no shell, stdin and stderr /dev/null, bounded output and time.
    The runner of the reviewed read-only family; the only addition is one optional DOCKER_CONFIG value."""
    def run(self,argv,gate,seconds,capture=True,docker_config=None):
        gate()
        environment=dict(COMMAND_ENVIRONMENT)
        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config
        process=subprocess.Popen(argv,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,env=environment)
        output=bytearray();selector=selectors.DefaultSelector()
        try:
            until=time.monotonic()+min(seconds,gate())
            if capture:
                os.set_blocking(process.stdout.fileno(),False);selector.register(process.stdout,selectors.EVENT_READ)
                while selector.get_map():
                    remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                    for key,_ in selector.select(min(.2,remaining)):
                        block=os.read(key.fd,8192)
                        if not block:selector.unregister(key.fileobj);continue
                        output.extend(block);need(len(output)<=MAX_COMMAND_BYTES,'COMMAND_OUTPUT_LIMIT')
            while True:
                remaining=min(gate(),until-time.monotonic());need(remaining>0,'COMMAND_TIMEOUT')
                try:code=process.wait(timeout=min(.2,remaining));break
                except subprocess.TimeoutExpired:pass
            gate();return code,bytes(output)
        finally:
            if process.poll() is None:
                process.kill()
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            selector.close()
            if process.stdout is not None:process.stdout.close()


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


class Commands:
    """Starts only rows of the signed COMMANDS table, with at most the arguments that row allows."""
    def __init__(self,host,gate):
        self.host,self.gate=host,gate;self.binaries={};self.timeouts={};self.calls=0
    def call(self,name,*extra,capture=True,docker_config=None):
        tool,arguments,_=COMMANDS[name]
        need(self.timeouts.get(tool,0)<MAX_TOOL_TIMEOUTS,'COMMAND_SKIPPED_AFTER_TIMEOUT')
        if tool not in self.binaries:
            try:self.binaries[tool]=binary(self.host,BINARIES[tool],self.gate)
            except Exception as error:self.binaries[tool]=Refused(safe(error)['code'])
        path=self.binaries[tool]
        if isinstance(path,Exception):raise Refused(str(path))
        self.calls+=1
        try:return self.host.run([path]+list(arguments)+list(extra),self.gate,CALL_SECONDS,capture,docker_config)
        except Refused as error:
            if str(error)=='COMMAND_TIMEOUT':self.timeouts[tool]=self.timeouts.get(tool,0)+1
            raise
    def output(self,name,*extra,docker_config=None):
        code,raw=self.call(name,*extra,docker_config=docker_config)
        if code!=0:raise CommandFailed('COMMAND_FAILED',code)
        return raw


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
# ==== END RUNNER ====

# ==== BEGIN LAYOUT (shared part, byte-identical in every source that carries it) ====
GROUPS=('SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY','RETENTION_TAG')
DIRECTORY_MODE=0o700
SUP_CONFIG='/etc/c3po-bar'
SUP_STATE_PARENT='/var/lib/c3po-bar'
SUP_STATE=SUP_STATE_PARENT+'/supervisor'
# Where the journal root of an epoch is created (supervisor README, "Journal placement"), signed per request:
#   A  <SUP_STATE_PARENT>/<leaf>, next to the state root on the host's root filesystem; the data volume is not touched
#   B  <data volume>/<leaf>, a leaf of the data volume
JOURNAL_PLACEMENTS=('A','B')
RDR_CONFIG='/etc/c3po-reader'
RDR_STATE='/var/lib/c3po-reader'
CHAIN_PATHS={'ETC':'/etc','VAR_LIB':'/var/lib','SUP_STATE_PARENT':SUP_STATE_PARENT}
CAPACITY_ROOTS=('config','documents','payload','go')
LEAF='[A-Za-z0-9][A-Za-z0-9._-]{0,63}'
# An entry of the data volume root named r2d2-v2-release-*.json that cannot be read as JSON holds the automatic security
# reboot and merges (scripts/c3po_security_guard.py). No directory created here may take such a name.
NAME_DENY=['r2d2-v2-release-.*']
# A parameterised path (data volume, capacity root) is never one of these or below one of them.
FORBIDDEN_ZONES=['/etc','/usr','/run','/proc','/sys','/dev','/boot','/bin','/sbin','/lib','/lib64','/var/run',
                 '/var/lib/docker','/var/lib/containerd','/var/lib/c3po-bar','/var/lib/c3po-reader']
# The fixed directories of this family. A parameterised path is never one of them and never above one of them: a
# data volume named /var or /var/lib would lift the code floor from the chain the fixed layout hangs from.
FIXED_PATHS=['/etc','/etc/systemd/system','/var/lib',SUP_CONFIG,SUP_STATE_PARENT,RDR_CONFIG,RDR_STATE]
REPOSITORY='c3po/backend'
TAG='massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
MAX_LEAVES=32

def leaf_name(value):
    return text(value,LEAF) and not any(re.fullmatch(pattern,value) for pattern in NAME_DENY)
def open_path(value):
    return (clean_path(value) and value!='/' and not any(inside(value,zone) for zone in FORBIDDEN_ZONES)
            and not any(inside(fixed,value) for fixed in FIXED_PATHS)
            and all(leaf_name(part) for part in PurePosixPath(value).parts[1:]))

def validate_parameters(groups,volume,leaf,existing,capacity,placement):
    """Everything the layout is instantiated from, before any host access. The data volume is a parameter only when
    something is created in it: a journal leaf under placement B, or the capacity tree."""
    need(type(groups) is list and groups and all(type(group) is str for group in groups)
         and groups==[group for group in GROUPS if group in groups],'GROUPS_INVALID')
    need(type(existing) is list and len(existing)<=MAX_LEAVES and all(leaf_name(name) for name in existing)
         and len(set(existing))==len(existing),'LEAF_INVALID')
    if 'JOURNAL_LEAF' in groups:need(type(placement) is str and placement in JOURNAL_PLACEMENTS,'PLACEMENT_UNKNOWN')
    else:need(placement is None,'PLACEMENT_UNKNOWN')
    if placement=='B' or 'CAPACITY' in groups:
        need(type(volume) is str and clean_path(volume),'PATH_INVALID');need(open_path(volume),'PATH_FORBIDDEN_ZONE')
    else:need(volume is None,'PATH_INVALID')
    if placement=='B':
        need(leaf_name(leaf) and leaf not in existing,'LEAF_INVALID')
        need(open_path(volume+'/'+leaf),'PATH_FORBIDDEN_ZONE')         # the composed path, not only its two halves
    elif placement=='A':
        need(leaf_name(leaf) and SUP_STATE_PARENT+'/'+leaf!=SUP_STATE,'LEAF_INVALID')      # a sibling of the state root, never the state root
    else:need(leaf is None,'LEAF_INVALID')
    if 'CAPACITY' in groups:
        need(type(capacity) is dict and set(capacity)=={'root_path','receipt_directory_path'},'PATH_INVALID')
        root,receipts=capacity['root_path'],capacity['receipt_directory_path']
        need(type(root) is str and clean_path(root) and type(receipts) is str and clean_path(receipts),'PATH_INVALID')
        need(open_path(root) and len(PurePosixPath(root).parts)>=3,'PATH_FORBIDDEN_ZONE')
        journals=[volume+'/'+name for name in existing+([leaf] if placement=='B' else [])]
        need(not any(inside(root,journal) or inside(journal,root) for journal in journals) and root!=volume
             and not inside(volume,root),'CAPACITY_JOURNAL_OVERLAP')
        parent=str(PurePosixPath(receipts).parent)
        need(leaf_name(PurePosixPath(receipts).name)
             and ((parent==root and PurePosixPath(receipts).name not in CAPACITY_ROOTS) or (parent==RDR_STATE and 'READER' in groups)),
             'CAPACITY_RECEIPTS_PARENT')
    else:need(capacity is None,'PATH_INVALID')

def layout(groups,volume,leaf,capacity,placement):
    """The whole table of what may be created, instantiated for the signed parameters, in creation order.
    Everything is a directory, root:root, mode 0700. A path outside this table is never created by this code."""
    rows=[]
    def add(key,path,parent):rows.append({'key':key,'path':path,'mode':DIRECTORY_MODE,'parent':parent})
    if 'SUPERVISOR' in groups:
        add('SUP_CONFIG',SUP_CONFIG,{'chain':'ETC'})
        add('SUP_MANIFESTS',SUP_CONFIG+'/manifests',{'entry':'SUP_CONFIG'})
        add('SUP_DOCKER_CLI',SUP_CONFIG+'/docker-cli',{'entry':'SUP_CONFIG'})
        add('SUP_STATE_PARENT',SUP_STATE_PARENT,{'chain':'VAR_LIB'})
        add('SUP_STATE',SUP_STATE,{'entry':'SUP_STATE_PARENT'})
    if 'JOURNAL_LEAF' in groups and placement=='A':
        # Below the private parent: created by this request, or (a later epoch) existing and pinned by its own chain.
        add('SUP_JOURNAL',SUP_STATE_PARENT+'/'+leaf,{'entry':'SUP_STATE_PARENT'} if 'SUPERVISOR' in groups else {'chain':'SUP_STATE_PARENT'})
    elif 'JOURNAL_LEAF' in groups:add('SUP_JOURNAL',volume+'/'+leaf,{'chain':'DATA_VOLUME'})
    if 'READER' in groups:
        add('RDR_CONFIG',RDR_CONFIG,{'chain':'ETC'})
        add('RDR_DOCKER_CLI',RDR_CONFIG+'/docker-cli',{'entry':'RDR_CONFIG'})
        add('RDR_STATE',RDR_STATE,{'chain':'VAR_LIB'})
    if 'CAPACITY' in groups:
        root,receipts=capacity['root_path'],capacity['receipt_directory_path']
        add('CAP_ROOT',root,{'chain':'DATA_VOLUME' if str(PurePosixPath(root).parent)==volume else 'CAPACITY_PARENT'})
        for name in CAPACITY_ROOTS:add('CAP_'+name.upper(),root+'/'+name,{'entry':'CAP_ROOT'})
        add('CAP_RECEIPTS',receipts,{'entry':'CAP_ROOT' if str(PurePosixPath(receipts).parent)==root else 'RDR_STATE'})
    return rows

def chain_paths(table,volume,capacity):
    """chain id -> the existing directory that chain ends at, for exactly the chains this table needs."""
    paths=dict(CHAIN_PATHS,DATA_VOLUME=volume)
    if capacity is not None:paths['CAPACITY_PARENT']=str(PurePosixPath(capacity['root_path']).parent)
    return {row['parent']['chain']:paths[row['parent']['chain']] for row in table if 'chain' in row['parent']}

def world_writable_without_sticky(row):return bool(row['mode']&0o002) and not row['mode']&stat.S_ISVTX
def row_accepted(row,volume):
    """None when a write operation accepts the signed row, otherwise the refusal code."""
    if row_root_safe(row):return None
    if volume is None or not inside(row['path'],volume):return 'CHAIN_ROW_UNSAFE'
    return 'CHAIN_ROW_WORLD_WRITABLE' if world_writable_without_sticky(row) else None

def validate_chains(chains,paths,volume):
    """Rows are observed values. Outside the data volume every component must be root-owned and not writable by
    group or other; at and below the data volume root the observed owner and mode are accepted as signed, except a
    directory any local user can write to without the sticky bit (there any user could rename what this run creates).
    The directory that receives a new entry must not be setgid: the kernel would hand its group and the bit to the child."""
    need(type(chains) is dict and set(chains)==set(paths),'CHAIN_MISSING')
    for name,path in paths.items():
        rows=chain_rows(chains[name],path)
        for row in rows:
            code=row_accepted(row,volume);need(code is None,code or 'CHAIN_ROW_UNSAFE')
        need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')

def volume_root_facts(chains,volume):
    """Two facts about the data volume root that the signers see literally in the effects, computed from the signed
    rows: whether any local user could rename an entry in it, and whether it is a mount point (its device differs
    from its parent's). On a volume that is not mounted the journal leaf would land on the parent's filesystem."""
    rows=(chains or {}).get('DATA_VOLUME')
    if volume is None or not rows or len(rows)<2:return {'world_writable_without_sticky':None,'device_differs_from_parent':None}
    return {'world_writable_without_sticky':world_writable_without_sticky(rows[-1]),'device_differs_from_parent':rows[-1]['device']!=rows[-2]['device']}
# ==== END LAYOUT ====

# ==== BEGIN SCAN (shared part, byte-identical in every source that carries it) ====
UNIT_DIRECTORY='/etc/systemd/system'
UNIT_NAME=r'c3po-[a-z0-9]+(-[a-z0-9]+)*\.(service|timer)'
MAX_UNITS=8
# The system manager's unit search path, highest priority first. /lib/systemd/system is left out on purpose: on a
# merged-/usr host /lib is a symbolic link to usr/lib, so it is the same directory as /usr/lib/systemd/system.
LOOKUP_DIRECTORIES=['/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',
                    '/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached',
                    '/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',
                    '/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late']
DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')
LEFTOVER=r'\.hostops-[0-9a-f]{16}-[0-9]{1,2}\.partial'
SCAN_NAME='[A-Za-z0-9@._:-]{1,128}'
MAX_SCAN_NAMES=4096
MAX_FINDINGS=64
# What the scan looks for; every source that carries the scan signs this text in its scope.
CONFLICT_SCAN_SCOPE={'lookup_directories':LOOKUP_DIRECTORIES,'dependency_suffixes':list(DEPENDENCY_SUFFIXES),
                     'drop_in_forms':['<name>.d','<type>.d','<dash-truncated prefix>-.<type>.d'],
                     'own_dependency_directories':['<name>.wants','<name>.requires','<name>.upholds'],
                     'alias_links':'a symbolic link named *.<type> whose text ends in a signed unit name; the text is read, the link is never followed',
                     'not_scanned':['/lib/systemd/system when /lib is a symbolic link (same directory as /usr/lib/systemd/system)',
                                    'a link inside a dependency directory whose own name is not a signed name but whose text ends in one',
                                    'user-manager directories']}

class NativeScan:
    """The one read primitive only the scan needs: the text of a symbolic link. The link is never followed."""
    def readlink(self,name,dir_fd):return os.readlink(name,dir_fd=dir_fd)

def unit_name(value):return text(value,UNIT_NAME) and len(value)<=64
def unit_names(value):
    return (type(value) is list and 0<len(value)<=MAX_UNITS and all(unit_name(name) for name in value)
            and len(set(value))==len(value))
def drop_in_names(name):
    """<name>.d, the type-level <type>.d, and each dash-truncated prefix form the manager also reads."""
    stem,_,suffix=name.rpartition('.');parts=stem.split('-')
    return [name+'.d',suffix+'.d']+['-'.join(parts[:index])+'-.'+suffix+'.d' for index in range(1,len(parts))]
def file_row(info):
    """Metadata of a unit file or of a leftover temporary of this family, size included. A caller that reports a file
    it did not prove to be the signed render removes the size (it would measure foreign content)."""
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
            'links':info.st_nlink,'size':info.st_size,'device':info.st_dev,'inode':info.st_ino}

def conflict_scan(host,names,check):
    """lstat only, no content. In every lookup directory: a unit of the same name anywhere but the install directory,
    every drop-in directory form, the unit's own dependency directories (<name>.wants and the like, which add
    dependencies to the unit without any drop-in), the name inside every dependency directory, and every symbolic
    link of a unit type whose text ends in one of the names (an alias). In the install directory also the leftover
    temporaries of this family. A directory that cannot be read is UNAVAILABLE, never an absence. In a finding row
    "within" is the dependency directory the name was found in or, for an alias, the unit name the link text ends in."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    findings=[];leftovers=[];directories={}
    types=tuple(sorted({'.'+name.rpartition('.')[2] for name in names}))
    def present(name,fd):
        check()
        try:return host.lstat(name,fd)
        except FileNotFoundError:return None
    def add(code,directory,name,within=None):
        findings.append({'code':code,'directory':directory,'name':name,'within':within})
    def one(directory):
        try:fd=descend(host,directory,check)
        except FileNotFoundError:return {'status':'COMPLETE','exists':False}
        try:
            listed=[];issues=[]
            for name in host.names(fd):
                listed.append(name);need(len(listed)<=MAX_SCAN_NAMES,'SCAN_LIMIT')
                if len(listed)%256==0:check()
            for name in names:
                if directory!=UNIT_DIRECTORY and present(name,fd) is not None:add('UNIT_SHADOWED_IN_OTHER_PATH',directory,name)
                for candidate in drop_in_names(name):
                    if present(candidate,fd) is not None:add('DROP_IN_PRESENT',directory,candidate)
                for suffix in DEPENDENCY_SUFFIXES:
                    if present(name+suffix,fd) is not None:add('OWN_DEPENDENCY_DIRECTORY_PRESENT',directory,name+suffix)
            for entry in sorted(listed):
                if directory==UNIT_DIRECTORY and text(entry,LEFTOVER):
                    info=present(entry,fd)
                    if info is not None:leftovers.append(dict(file_row(info),name=entry))
                if entry.endswith(types) and entry not in names:
                    info=present(entry,fd)
                    if info is not None and stat.S_ISLNK(info.st_mode):
                        check();target=host.readlink(entry,fd)
                        need(type(target) is str,'LINK_TEXT_UNREADABLE')
                        if PurePosixPath(target).name in names:
                            add('ALIAS_LINK_PRESENT',directory,entry if text(entry,SCAN_NAME) else None,PurePosixPath(target).name)
                if not entry.endswith(DEPENDENCY_SUFFIXES):continue
                info=present(entry,fd)
                if info is None:continue
                label=entry if text(entry,SCAN_NAME) else None
                if not stat.S_ISDIR(info.st_mode):
                    issues.append('DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY');continue
                check();child=host.open(entry,flags,dir_fd=fd)
                try:
                    held=host.fstat(child);need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),'PATH_CHANGED')
                    for name in names:
                        if present(name,child) is not None:add('ENABLEMENT_LINK_PRESENT',directory,name,label)
                finally:host.close(child)
            return {'status':'COMPLETE' if not issues else 'UNAVAILABLE','exists':True,'entries':len(listed),
                    **({'code':issues[0]} if issues else {})}
        finally:host.close(fd)
    for directory in LOOKUP_DIRECTORIES:directories[directory]=attempt(lambda directory=directory:one(directory))
    status=combined(directories.values())
    return {'status':'COMPLETE' if status=='COMPLETE' else 'UNAVAILABLE','directories':directories,
            'findings':findings[:MAX_FINDINGS],'findings_truncated':len(findings)>MAX_FINDINGS,
            'finding_codes':sorted({item['code'] for item in findings}),'leftovers':leftovers[:MAX_FINDINGS],
            'leftover_count':len(leftovers)}
# ==== END SCAN ====

# ==== BEGIN LISTING (shared part, byte-identical in every source that carries it) ====
MAX_LISTING_ROWS=64
# Typed fields only. Never run by this family on this host before OP_PRECHECK; whether the ID printed here equals the
# inspect ID under the containerd image store is unverified, which is why a listing without the signed ID proves nothing.
LS_FORMAT='{"id":{{json .ID}},"repository":{{json .Repository}},"tag":{{json .Tag}}}'

def listing(commands):
    """docker image ls of the one repository: rows of (id, repository, tag). A failed listing is never an absence."""
    try:raw=commands.output('image_ls')
    except Refused as error:
        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','BINARY_UNAVAILABLE_OR_UNSAFE') else 'TAG_LISTING_UNAVAILABLE') from None
    rows=[]
    try:
        for line in raw.splitlines():
            if not line:continue
            row=decode(line)
            need(set(row)=={'id','repository','tag'} and text(row['id'],IMAGE_ID) and row['repository']==REPOSITORY
                 and text(row['tag'],'[A-Za-z0-9_.<>-]{1,128}'),'TAG_LISTING_UNAVAILABLE')
            rows.append(row);need(len(rows)<=MAX_LISTING_ROWS,'TAG_LISTING_UNAVAILABLE')
    except Refused:raise Refused('TAG_LISTING_UNAVAILABLE') from None
    return rows
# ==== END LISTING ====

# ==== BEGIN OP_PRECHECK (this operation only) ====
OPERATION='GO_READONLY_HOSTOPS_PRECHECK_01'
PHASE='READONLY_HOSTOPS_PRECHECK'
REQUEST_SCHEMA='READONLY_HOSTOPS_PRECHECK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS_PRECHECK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS_PRECHECK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS_PRECHECK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_PRECHECK_PLAN_V1'
SOURCE_NAME='precheck_readonly.py'
WRITES_ALLOWED=False
DATES=READ_DATES
EVIDENCE_REQUIRED=False
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='PRECHECK_ALL_OBSERVED'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
EXPIRED_OUTCOME='PARTIAL_OR_WINDOW_EXPIRED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
PLAN_KEYS=frozenset(('groups','journal_placement','data_volume_path','journal_leaf','existing_journal_leaves','capacity','unit_names','image_reference'))
PRODUCTION_REFERENCE=REPOSITORY+':production'
# Names that hold, or will hold, a secret: type, owner, mode and link count only. Never a size, a timestamp or an identity.
SECRET_BEARING=[RDR_CONFIG+'/secret.env',SUP_CONFIG+'/token']
PRESENCE_ONLY=['/etc/.git','/etc/.etckeeper','/run/reboot-required']
CORE_PATTERN_PATH='/proc/sys/kernel/core_pattern'
MAX_SCAN_ENTRIES=4096
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
# The exact fixed argv prefixes. The signed request carries this table. No command here changes anything.
COMMANDS={'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'the fixed reference '+PRODUCTION_REFERENCE],
          'image_ls':['docker',['image','ls','--no-trunc','--format',LS_FORMAT,REPOSITORY],None]}
SCOPE_STATEMENT=('Reads and changes nothing: one row (device, inode, owner, group, mode) per component of each parent directory the '
                 'write operations pin, the presence and metadata of every planned destination, the unit lookup directories, the '
                 'boot identifier hash, and the local ID and tags of '+PRODUCTION_REFERENCE+'. For names that hold a secret only '
                 'type, owner, mode and link count; for a unit file found at a signed name no size. Its rows are what the write '
                 'requests sign; it authorises no write.')
SIDE_EFFECTS=['every docker command: the Docker CLI loads the client configuration file of root when one exists; its content never reaches this process',
              'docker image ls was never run by this family on this host: this operation is its first run']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'binaries':BINARIES,'commands':COMMANDS,'command_environment':COMMAND_ENVIRONMENT,
       'chains':dict(CHAIN_PATHS,UNIT_DIRECTORY=UNIT_DIRECTORY,DATA_VOLUME='<data volume>',CAPACITY_PARENT='<parent of the capacity root>'),
       'layout':{'groups':[group for group in GROUPS if group!='RETENTION_TAG'],
                 'journal_placements':{'A':SUP_STATE_PARENT+'/<journal leaf>','B':'<data volume>/<journal leaf>'},
                 'table':layout(['SUPERVISOR','JOURNAL_LEAF','READER','CAPACITY'],'<data volume>','<journal leaf>',
                                {'root_path':'<capacity parent>/<capacity root>','receipt_directory_path':RDR_STATE+'/<receipts>'},'B')},
       'name_pattern':LEAF,'name_deny':NAME_DENY,'forbidden_zones':FORBIDDEN_ZONES,'fixed_paths_never_at_or_below_a_parameter':FIXED_PATHS,
       'unit_directory':UNIT_DIRECTORY,'unit_name_pattern':UNIT_NAME,
       'unit_files_reported':['exists','type','uid','gid','mode_octal','links','device','inode'],
       'conflict_scan':CONFLICT_SCAN_SCOPE,
       'secret_bearing_names':{'paths':SECRET_BEARING,'reported':['exists','type','uid','gid','mode_octal','links'],'opened':False},
       'presence_only':PRESENCE_ONLY,'image_reference':PRODUCTION_REFERENCE,
       'file_contents_read':[BOOT_ID_PATH,CORE_PATTERN_PATH+' (only whether its first byte is a pipe sign is reported)'],
       'side_effects':SIDE_EFFECTS,
       'never':['any write','file contents other than file_contents_read','a size, timestamp, device or inode of a secret-bearing name',
                'container environment','docker exec or run','systemctl','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'command_output_bytes':MAX_COMMAND_BYTES,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,
                 'scan_names':MAX_SCAN_NAMES,'directory_entries':MAX_SCAN_ENTRIES,'listing_rows':MAX_LISTING_ROWS,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeScan):
    """Read primitives and the fixed commands. This source has no call that creates, changes or removes anything."""


def validate_plan(plan):
    groups=plan['groups']
    need(type(groups) is list and 'RETENTION_TAG' not in groups,'GROUPS_INVALID')
    validate_parameters(groups,plan['data_volume_path'],plan['journal_leaf'],plan['existing_journal_leaves'],plan['capacity'],plan['journal_placement'])
    need(unit_names(plan['unit_names']),'UNIT_NAME_INVALID')
    need(plan['image_reference']==PRODUCTION_REFERENCE,'IMAGE_REFERENCE_INVALID')

def planned(plan):
    table=layout(plan['groups'],plan['data_volume_path'],plan['journal_leaf'],plan['capacity'],plan['journal_placement'])
    chains=dict(chain_paths(table,plan['data_volume_path'],plan['capacity']),UNIT_DIRECTORY=UNIT_DIRECTORY)
    return table,chains

def effects_of(plan):
    table,chains=planned(plan)
    return {'operation':OPERATION,'journal_placement':plan['journal_placement'],'existing_journal_leaves':plan['existing_journal_leaves'],
            'chains':chains,'destinations':[row['path'] for row in table],
            'unit_names':plan['unit_names'],'secret_bearing_names':SECRET_BEARING,'presence_only':PRESENCE_ONLY,
            'image_reference':plan['image_reference'],'writes':0,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def chain(host,path,gate,volume):
    """One observed row per component, in exactly the six-key form a write request signs, plus what a signer must
    see before signing it: type, setgid, whether the code would accept the row, and mount points by device change."""
    rows=[];fd=None
    try:fd=descend(host,path,gate,rows)
    except Exception as error:
        return dict(safe(error),path=path,rows=rows)
    try:
        notes=[];device=None
        for row in rows:
            notes.append({'path':row['path'],'mode_octal':'%04o'%row['mode'],'setgid':bool(row['mode']&stat.S_ISGID),
                          'root_owned_not_group_or_other_writable':row_root_safe(row),
                          'world_writable_without_sticky':world_writable_without_sticky(row),
                          'accepted_by_the_write_operations':row_accepted(row,volume) is None,
                          'mount_point_by_device_change':device is None or row['device']!=device})
            device=row['device']
        v=host.fstatvfs(fd)
        need(all(type(value) is int and value>=0 for value in (v.f_frsize,v.f_bavail)) and v.f_frsize>0,'STATVFS_INVALID')
        return {'status':'COMPLETE','path':path,'rows':rows,'notes':notes,
                'direct_parent_setgid':bool(rows[-1]['mode']&stat.S_ISGID),
                'bytes_available_to_non_root_f_bavail':v.f_bavail*v.f_frsize}
    finally:host.close(fd)

def destination(host,row,gate,table):
    """Proved absence (with the first missing component) or presence with metadata. A directory is also counted, and its
    entries are split into table-defined children and others; no name is reported."""
    found=probe(host,row['path'],gate);found.pop('links',None)
    result=dict(found,key=row['key'],path=row['path'])
    if found.get('status')=='COMPLETE' and found.get('exists') and found['type']=='dir':
        fd=descend(host,row['path'],gate)
        try:
            result['entries']=count_entries(host,fd,gate,MAX_SCAN_ENTRIES);defined=0
            for child in table:
                if child['parent'].get('entry')!=row['key']:continue
                gate()
                try:host.lstat(PurePosixPath(child['path']).name,fd);defined+=1
                except FileNotFoundError:pass
            result['table_defined_children']=defined;result['other_entries']=result['entries']-defined
        finally:host.close(fd)
        result['conforms_to_layout']=(found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%DIRECTORY_MODE)
    return result

def secret_bearing(host,path,gate):
    found=probe(host,path,gate)
    if found.get('status')!='COMPLETE':return {key:found.get(key) for key in ('status','code','at')}
    if not found['exists']:return {'status':'COMPLETE','exists':False,'absent_at':found['absent_at']}
    return {'status':'COMPLETE','exists':True,**{key:found[key] for key in ('type','uid','gid','mode_octal','links')}}

def presence(host,path,gate):
    found=probe(host,path,gate)
    if found.get('status')!='COMPLETE':return {key:found.get(key) for key in ('status','code','at')}
    return {'status':'COMPLETE','exists':found['exists']}

def unit_file(host,name,gate):
    fd=descend(host,UNIT_DIRECTORY,gate)
    try:
        gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:return {'status':'COMPLETE','exists':False}
        # No size: this operation cannot tell whether the file is the signed render, and the size of a foreign unit
        # with an inline secret would measure it.
        return {'status':'COMPLETE','exists':True,**{key:value for key,value in file_row(named).items() if key!='size'}}
    finally:host.close(fd)

def core_pattern(host,gate):
    """Whether the kernel pipes core dumps to a handler. Only that boolean is reported."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW;parts=PurePosixPath(CORE_PATTERN_PATH).parts[1:]
    gate();fd=host.open('/',flags)
    try:
        for part in parts[:-1]:
            gate();child=host.open(part,flags,dir_fd=fd);host.close(fd);fd=child
        gate();leaf=host.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:raw=host.read(leaf,1)
        finally:host.close(leaf)
    finally:host.close(fd)
    need(type(raw) is bytes and len(raw)==1,'CORE_PATTERN_UNREADABLE')
    return {'status':'COMPLETE','is_pipe':raw==b'|'}

def _reduce_scan(receipt):
    scan=receipt['items'].get('conflicts')
    if type(scan) is dict and type(scan.get('directories')) is dict:
        scan['directories']={name:item.get('status') for name,item in scan['directories'].items()}
def _reduce_notes(receipt):
    for item in (receipt['items'].get('chains') or {}).values():
        if type(item) is dict:item.pop('notes',None)
def _reduce_items(receipt):
    receipt['items']={name:{'status':item.get('status') if type(item) is dict and 'status' in item else 'REDUCED'}
                      for name,item in receipt['items'].items()}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('CHAIN_NOTES_DROPPED',_reduce_notes),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def statuses(value,found):
    if type(value) is dict:
        if 'status' in value:found.append((value['status'],value.get('code')))
        for item in value.values():statuses(item,found)
    elif type(value) is list:
        for item in value:statuses(item,found)

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    table,chains=planned(plan);commands=Commands(host,gate);items={};volume=plan['data_volume_path']
    def run(name,action):
        try:
            gate();items[name]=action()
        except Exception as error:items[name]=safe(error)
    def each(names,action):
        return {name:attempt(lambda name=name:action(name)) for name in names}
    items['actor']=attempt(lambda:dict(zip(('uid','gid'),host.identity()),status='COMPLETE'))
    run('boot',lambda:{'status':'COMPLETE','boot_id_sha256':boot_id_sha256(host,gate)})
    run('chains',lambda:{name:chain(host,chains[name],gate,volume) for name in sorted(chains)})
    run('destinations',lambda:{row['key']:attempt(lambda row=row:destination(host,row,gate,table)) for row in table})
    run('secret_bearing_names',lambda:each(SECRET_BEARING,lambda path:secret_bearing(host,path,gate)))
    run('presence_only',lambda:each(PRESENCE_ONLY,lambda path:presence(host,path,gate)))
    run('unit_files',lambda:each(plan['unit_names'],lambda name:unit_file(host,name,gate)))
    run('conflicts',lambda:conflict_scan(host,plan['unit_names'],gate))
    run('core_pattern',lambda:core_pattern(host,gate))
    def image():
        try:facts=image_facts(commands,plan['image_reference'])
        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None
        return dict(facts,status='COMPLETE' if facts['repo_tags_all_valid'] and facts['reference_among_repo_tags'] else 'PARTIAL',
                    reference=plan['image_reference'],
                    binds='this ID binds only if it is read after the deploy of the merged revision; it is specific to this image store')
    run('image',image)
    def listed():
        rows=listing(commands);inspected=items.get('image',{}).get('id')
        return {'status':'COMPLETE','rows':rows,'contains_inspected_id':None if inspected is None else any(row['id']==inspected for row in rows),
                'retention_tags_present':sorted(row['tag'] for row in rows if re.fullmatch(TAG,row['tag']))}
    run('image_listing',listed)
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        items['clock']={'status':'COMPLETE','utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
    except Exception as error:items['clock']=safe(error)
    found=[];statuses(items,found)
    problems=sorted({code for status,code in found if status!='COMPLETE' and type(code) is str})
    incomplete=any(status!='COMPLETE' for status,_ in found);expired=any(code in EXPIRED for _,code in found)
    try:gate()
    except Refused:expired=True
    outcome=EXPIRED_OUTCOME if expired else PARTIAL_OUTCOME if incomplete else COMPLETE_OUTCOME
    status=COMPLETE_STATUS if outcome==COMPLETE_OUTCOME else PARTIAL_STATUS
    receipt=envelope(status,outcome,None if status==COMPLETE_STATUS else (problems+['ITEMS_NOT_COMPLETE'])[0],
        dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),items=items,problems=problems[:32],
             commands_started=commands.calls,mutating_calls=state.counts(),writes=0,secret_bytes_read=0,
             file_contents_read=[BOOT_ID_PATH,CORE_PATTERN_PATH],installation_authorized=False,activation_authorized=False))
    return seal(receipt)
# ==== END OP_PRECHECK ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
